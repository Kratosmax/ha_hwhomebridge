import ast
import asyncio
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('water_builder',ROOT/'tools/build_water_candidate.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WaterMetadataTests(unittest.TestCase):
    def test_startup_reuses_registered_doors_and_does_not_retry_failed_water(self):
        import sys
        tree=ast.parse((ROOT/'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('start','registration_statuses','registration_devices')]
        def device(sn,pid):return types.SimpleNamespace(sn=sn,product=types.SimpleNamespace(pid=pid),online=True)
        devices=[device('door-existing','011'),device('door-new','011'),device('water-existing','012'),device('water-unregistered','012'),device('gas','013')]
        registrations=[]
        router=types.SimpleNamespace(sn_manager=types.SimpleNamespace(get_all_devices=lambda:devices),
            register_device_to_hilink=lambda sn,status:registrations.append((sn,status)))
        class Probe:
            def __init__(self,*args):self.events=[];self.error=None
            def start(self):pass
            def close(self):pass
        class Hass:
            config=types.SimpleNamespace(path=lambda *parts:'unused-probe-path')
            services=types.SimpleNamespace(async_register=lambda *args,**kwargs:None)
            async def async_add_executor_job(self,fn,*args):return fn(*args)
        async def no_wait(*args):pass
        core=types.ModuleType('homeassistant.core')
        core.SupportsResponse=types.SimpleNamespace(ONLY=object())
        package=types.ModuleType('sensor_startup_test');package.__path__=[]
        native=types.ModuleType('sensor_startup_test.native_log_probe');native.NativeLogProbe=Probe
        scope={'__package__':'sensor_startup_test','bridge':types.SimpleNamespace(service_router=router,_excluded_device_sns=set()),
            'PRODUCTS':{'011':None,'012':None,'013':None},'REGISTERED':{'door-existing','water-existing'},
            'STATUS':{'gas_registered':True},'TRACE':[],'Path':Path,'time':time,
            'thermohygrometer_runtime':types.SimpleNamespace(STATUS={'reporting_enabled':True}),
            'asyncio':types.SimpleNamespace(get_running_loop=asyncio.get_running_loop,sleep=no_wait),
            'send':lambda *args:None}
        with patch.dict(sys.modules,{'homeassistant':types.ModuleType('homeassistant'),'homeassistant.core':core,
                                     'sensor_startup_test':package,'sensor_startup_test.native_log_probe':native}):
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'sensor-startup','exec'),scope)
            asyncio.run(scope['start'](Hass()))
        self.assertEqual(registrations,[('door-existing',1),('door-new',3),('water-existing',1),('gas',1)])

    def test_unregistered_water_does_not_keep_submitting_failed_reports(self):
        tree=ast.parse((ROOT/'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='send')
        calls=[]
        def submit(*args):
            calls.append(args)
            future=concurrent.futures.Future();future.set_result(0)
            return future
        scope={'STATUS':{'reporting_enabled':True},'bridge':types.SimpleNamespace(bridge_work=True),
               'REGISTERED':set(),'WATER_TRIALS':set(),'LAST':{},'TRACE':[],
               'readings':lambda *args:{'warterAlarm':{'alarm':0}},'submit_native':submit,'json':json,'time':time}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'water-send','exec'),scope)
        device=types.SimpleNamespace(sn='water-a',product=types.SimpleNamespace(pid='012'))
        router=types.SimpleNamespace(_hass=None,_lib=types.SimpleNamespace(UpdateHAStatus=object()),_c_char_p=lambda v:v)
        self.assertFalse(scope['send'](router,device))
        self.assertFalse(calls)
        scope['WATER_TRIALS'].add('water-a')
        self.assertTrue(scope['send'](router,device))
        self.assertEqual(len(calls),1)
        scope['WATER_TRIALS'].clear();scope['LAST'].clear()
        self.assertFalse(scope['send'](router,device))
        self.assertEqual(len(calls),1)

    def test_wrong_baseline_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'temp') as folder:
            folder=Path(folder)
            (folder/'source').write_bytes(b'wrong baseline')
            with self.assertRaisesRegex(ValueError,'baseline'):
                builder.build(folder/'source',folder/'profile',folder/'plan',folder/'output')
            self.assertFalse((folder/'output').exists())

    def test_service_type_repair_preserves_ids_and_every_other_byte(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'temp') as folder:
            folder=Path(folder)
            ids=['warterAlarm','battery','commonFaultDetection','update','netInfo']
            service_types=['alarm','battery','fault','ota','netInfo']
            raw=bytearray(0x224000)
            table=0x220020+6*0x780
            for i,sid in enumerate(ids):
                raw[table+i*32:table+i*32+len(sid)]=sid.encode()
                raw[table+0x280+i*64:table+0x280+i*64+len(sid)]=sid.encode()
            (folder/'source').write_bytes(raw)
            profile={'prodId':'2GB5','deviceModel':'MIR-WA100','deviceTypeId':'03C','manufacturerId':'2b0','protocolType':'Mesh',
                     'services':[{'serviceId':sid,'serviceType':st} for sid,st in zip(ids,service_types)]}
            (folder/'profile').write_text(json.dumps(profile),encoding='utf-8')
            baseline=[{'index':i,'product_id':'2GB5' if i==6 else 'other','service_names':ids if i==6 else ['unchanged']} for i in range(8)]
            (folder/'plan').write_text(json.dumps({'expected_metadata':baseline}),encoding='utf-8')
            with patch.object(builder,'SOURCE_SHA',hashlib.sha256(raw).hexdigest()):
                plan=builder.build(folder/'source',folder/'profile',folder/'plan',folder/'output')
            fixed=(folder/'output/candidate/libhilink_bridge.so').read_bytes()
            self.assertEqual(fixed[:table],raw[:table])
            self.assertEqual(fixed[table+0x280:],raw[table+0x280:])
            self.assertEqual(plan['expected_metadata'][6]['service_names'],service_types)
            self.assertEqual(plan['expected_metadata'][6]['service_ids'],ids)
            self.assertEqual(plan['expected_unchanged_slots'],[0,1,2,3,4,5,7])

    def test_single_sensor_retry_cannot_register_other_devices(self):
        tree=ast.parse((ROOT/'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='registration_devices')
        scope={}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'sensor-selection','exec'),scope)
        def device(sn,pid,online=True):return types.SimpleNamespace(sn=sn,product=types.SimpleNamespace(pid=pid),online=online)
        devices=[device('water-a','012'),device('water-b','012'),device('gas','013'),device('offline','012',False)]
        select=scope['registration_devices']
        self.assertEqual([d.sn for d in select(devices,'012','water-a')],['water-a'])
        for target in ('gas','offline','missing'):
            with self.assertRaises(ValueError):select(devices,'012',target)
