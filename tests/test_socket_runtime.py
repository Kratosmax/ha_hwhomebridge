import ast
import asyncio
import concurrent.futures
from collections import deque
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/hwhomebridge'
spec = importlib.util.spec_from_file_location('socket_runtime_delay_test', COMPONENT / 'socket_delay.py')
delay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = delay
spec.loader.exec_module(delay)
meter_spec = importlib.util.spec_from_file_location('socket_runtime_meter_test', COMPONENT / 'socket_meter.py')
meter = importlib.util.module_from_spec(meter_spec)
meter_spec.loader.exec_module(meter)


class SocketRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'temp')
        self.instant = datetime(2026, 10, 18, 4, tzinfo=timezone.utc)
        self.calls = []
        self.reports = []
        self.state = types.SimpleNamespace(state='off')
        async def call(domain, action, data, blocking):
            self.calls.append((domain, action, data, blocking))
        async def executor(func, *args):
            return await asyncio.to_thread(func, *args)
        self.hass = types.SimpleNamespace(states=types.SimpleNamespace(get=lambda entity: self.state),
            services=types.SimpleNamespace(async_call=call), async_add_executor_job=executor)
        self.scope = dict(datetime=datetime, timezone=timezone, json=json, time=time,
            ENTITY='switch.test_socket', DEVICE=types.SimpleNamespace(sn='test-socket'),
            STORE=delay.CountdownStore(Path(self.folder.name) / 'tasks.json', self.instant),
            LOCK=asyncio.Lock(), TRACE=deque(maxlen=50), decode=delay.decode,
            DEVICES={}, ENTITIES={}, METERS={}, PAUSED=set(), ENERGY=None, ENERGY_LOCK=asyncio.Lock(),
            power=meter.power, energy_wh=meter.energy_wh,
            STATUS={'last_refresh_time': self.instant.timestamp()},
            now=lambda: self.instant, report=lambda hass, *args, **kwargs: self.reports.append(True))
        tree = ast.parse((COMPONENT / 'socket_runtime.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name in ('binding', 'values', 'command', 'execute', 'apply', 'tick', 'energy_refresh')]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'socket-runtime', 'exec'), self.scope)

    async def asyncTearDown(self):
        self.folder.cleanup()

    async def test_nested_and_flat_switch_commands_use_only_selected_entity(self):
        for payload in [{'on': 1}, {'switch': {'on': 0}}]:
            operation = self.scope['command'](json.dumps(payload))
            await self.scope['apply'](self.hass, operation)
        self.assertEqual([c[1] for c in self.calls], ['turn_on', 'turn_off'])
        self.assertTrue(all(c[0] == 'switch' and c[2] == {'entity_id': 'switch.test_socket'}
                            and c[3] is True for c in self.calls))
        for bad in [{'on': True}, {'on': 0.5}, {'on': 2}, {'on': 1, 'delay': []}]:
            with self.assertRaises(ValueError):
                self.scope['command'](bad)

    async def test_countdown_creation_never_switches_now_and_cancel_prevents_execution(self):
        operation = self.scope['command']({'action': 1, 'delay': [
            {'sid': 'switch', 'para': 'on', 'start': '20261018T043000Z'}]})
        await self.scope['apply'](self.hass, operation)
        self.assertEqual(self.calls, [])
        state = self.scope['values'](self.hass)
        task_id = state['delay']['delay'][0]['id']
        await self.scope['apply'](self.hass, self.scope['command']({'delay': {
            'action': 2, 'delay': [{'id': task_id, 'para': 'on'}]}}))
        await self.scope['tick'](self.hass, self.instant + timedelta(hours=1))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.scope['values'](self.hass)['delay']['num'], 0)

    async def test_due_countdown_switches_once_and_unavailable_socket_is_skipped(self):
        operation = self.scope['command']({'delay': {'action': 1, 'delay': [
            {'sid': 'switch', 'para': 'on', 'end': '20261018T043000Z'}]}})
        await self.scope['apply'](self.hass, operation)
        await self.scope['tick'](self.hass, self.instant + timedelta(minutes=30))
        await self.scope['tick'](self.hass, self.instant + timedelta(hours=1))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1], 'turn_off')
        await self.scope['apply'](self.hass, operation)
        self.state.state = 'unavailable'
        await self.scope['tick'](self.hass, self.instant + timedelta(hours=1))
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('switch', self.scope['values'](self.hass))
        self.assertEqual(self.scope['TRACE'][-1]['kind'], 'countdown_failed')

    async def test_multiple_sockets_keep_commands_and_countdowns_separate(self):
        second = types.SimpleNamespace(sn='second-socket')
        self.scope['DEVICES']['second-socket'] = second
        self.scope['ENTITIES']['second-socket'] = 'switch.second_socket'
        await self.scope['apply'](self.hass, ('switch', True), second.sn)
        self.assertEqual(self.calls[-1][2], {'entity_id': 'switch.second_socket'})
        operation = self.scope['command']({'action': 1, 'delay': [
            {'sid': 'switch', 'para': 'on', 'end': '20261018T043000Z'}]})
        await self.scope['apply'](self.hass, operation, 'test-socket')
        await self.scope['apply'](self.hass, operation, second.sn)
        first = self.scope['values'](self.hass, 'test-socket')['delay']['delay'][0]
        other = self.scope['values'](self.hass, second.sn)['delay']['delay'][0]
        self.assertNotEqual(first['id'], other['id'])
        cancel = ('delay', {'delay': {'action': 2, 'delay': [{'id': first['id'], 'para': 'on'}]}})
        await self.scope['apply'](self.hass, cancel, 'test-socket')
        await self.scope['tick'](self.hass, self.instant + timedelta(hours=1))
        self.assertEqual(self.calls[-1][1:3], ('turn_off', {'entity_id': 'switch.second_socket'}))
        self.assertEqual(len(self.calls), 2)

    async def test_periodic_refresh_reports_real_state_without_switch_commands(self):
        self.scope['DEVICES']['test-socket'] = self.scope['DEVICE']
        self.scope['ENTITIES']['test-socket'] = 'switch.test_socket'
        snapshots = []
        self.scope['report'] = lambda hass, sn, **kwargs: snapshots.append(self.scope['values'](hass, sn))
        self.state.state = 'on'
        await self.scope['tick'](self.hass, self.instant + timedelta(seconds=59))
        self.assertEqual(snapshots, [])
        await self.scope['tick'](self.hass, self.instant + timedelta(seconds=60))
        self.assertEqual(snapshots[0]['switch'], {'on': 1})
        await self.scope['tick'](self.hass, self.instant + timedelta(seconds=61))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(self.calls, [])

    async def test_delay_deduplication_keeps_switch_heartbeat_changes_and_failed_retries(self):
        packets = []
        results = []
        countdown = {'num': 0, 'delay': []}
        self.scope['STORE'] = types.SimpleNamespace(state=lambda sn: {'delay': countdown})
        self.scope['METERS']['test-socket'] = {'deduplicate_delay_reports': True}
        self.scope.update(REPORT_RESULTS={},
            STATUS={'reporting_enabled': True}, bridge=types.SimpleNamespace(bridge_work=True,
                service_router=types.SimpleNamespace(_lib=types.SimpleNamespace(UpdateHAStatus=object()),
                    _c_char_p=lambda v: v)))
        def submit(func, sn, sid, payload):
            packets.append((sn, sid, json.loads(payload)))
            future = concurrent.futures.Future()
            future.set_result(results.pop(0) if results else 0)
            return future
        self.scope['submit_native'] = submit
        tree = ast.parse((COMPONENT / 'socket_runtime.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'report')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'socket-report', 'exec'), self.scope)
        report = self.scope['report']
        report(self.hass)
        report(self.hass, periodic=True)
        self.assertEqual([sid for _, sid, _ in packets], ['switch', 'delay', 'switch'])
        countdown = {'num': 1, 'delay': [{'id': 1, 'end': '20261018T043000Z'}]}
        results[:] = [0, -12]
        report(self.hass)
        report(self.hass, periodic=True)
        self.assertEqual([sid for _, sid, _ in packets[-4:]], ['switch', 'delay', 'switch', 'delay'])
        countdown = {'num': 0, 'delay': []}
        self.state.state = 'on'
        report(self.hass)
        self.assertEqual(packets[-2:], [('test-socket', 'switch', {'on': 1}),
                                       ('test-socket', 'delay', {'num': 0, 'delay': []})])
        self.scope['METERS']['test-socket'] = {}
        report(self.hass, periodic=True)
        self.assertEqual(packets[-1][1], 'switch')
        report(self.hass, services={'power'})
        self.assertEqual(packets[-1][1], 'switch')
        self.assertEqual(self.calls, [])

    async def test_meter_reports_deltas_without_operating_switches(self):
        states = {'switch.test_socket': types.SimpleNamespace(state='on'),
            'sensor.power': types.SimpleNamespace(state='223'),
            'sensor.energy': types.SimpleNamespace(state='0.2', attributes={
                'unit_of_measurement': 'kWh', 'state_class': 'total_increasing'})}
        self.hass.states.get = states.get
        self.scope['METERS']['test-socket'] = {'power_entity': 'sensor.power',
            'energy_entity': 'sensor.energy', 'power_scale': '1'}
        self.scope['ENERGY'] = meter.EnergyCounter(Path(self.folder.name) / 'meter.json')
        self.scope['STATUS']['reporting_enabled'] = True
        packets = []
        router = types.SimpleNamespace(_lib=types.SimpleNamespace(UpdateHAStatus=object()), _c_char_p=lambda value: value)
        self.scope['bridge'] = types.SimpleNamespace(service_router=router)
        def submit(func, sn, sid, value):
            packets.append((sn, sid, json.loads(value)))
            result = concurrent.futures.Future()
            result.set_result(0)
            return result
        self.scope.update(submit_native=submit, asyncio=asyncio)
        self.assertEqual(self.scope['values'](self.hass)['power'], {'current': 223})
        await self.scope['energy_refresh'](self.hass)
        self.assertEqual(packets, [('test-socket', 'consumption', {'consumption': 0})])
        states['sensor.energy'].state = '0.21'
        await self.scope['energy_refresh'](self.hass)
        await self.scope['energy_refresh'](self.hass)
        self.assertEqual(packets, [('test-socket', 'consumption', {'consumption': 0}),
                                   ('test-socket', 'consumption', {'consumption': 10})])
        self.assertEqual(self.calls, [])

    async def test_idle_tick_does_not_dispatch_worker_jobs(self):
        jobs = []
        async def executor(func, *args):
            jobs.append(func)
            return func(*args)
        self.hass.async_add_executor_job = executor
        await self.scope['tick'](self.hass, self.instant + timedelta(seconds=1))
        self.assertEqual(jobs, [])
        self.assertEqual(self.calls, [])

    async def test_retire_only_selected_legacy_socket_after_replacement_is_ready(self):
        removed, excluded, native = [], [], []
        old = types.SimpleNamespace(sn='old-socket', product=types.SimpleNamespace(pid='008'), online=True,
            get_entity_for_service=lambda service: 'switch.test_socket')
        replacement = self.scope['DEVICE']
        replacement.online = True
        router = types.SimpleNamespace(sn_manager=types.SimpleNamespace(get_by_sn=lambda sn: old),
            _lib=types.SimpleNamespace(HilinkSyncBrgDevStatus=object()), _c_char_p=lambda sn: sn)
        self.scope.update(SELECTIONS=[{'old_sn': old.sn, 'entity_id': 'switch.test_socket'}],
            DEVICES={replacement.sn: replacement}, ENTITIES={replacement.sn: 'switch.test_socket'},
            STATUS={'reporting_enabled': True}, REPORT_RESULTS={},
            bridge=types.SimpleNamespace(service_router=router, _excluded_device_sns=set(),
                _write_excluded_device_to_file=excluded.append,
                _remove_bridge_device_entry_async=removed.append))
        def submit(func, sn, status):
            native.append((sn, status))
            future = concurrent.futures.Future()
            future.set_result(0)
            return future
        self.scope.update(submit_native=submit, asyncio=asyncio)
        source = ast.parse((COMPONENT / 'socket_runtime.py').read_text(encoding='utf-8'))
        nodes = [n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'retire_legacy']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'retire-legacy', 'exec'), self.scope)
        retire = self.scope['retire_legacy']
        with self.assertRaises(ValueError):
            await retire(self.hass, ['unrelated-device'])
        self.assertEqual(native, [])
        result = await retire(self.hass, [old.sn])
        self.assertFalse(result['results'][0]['retired'])
        self.assertEqual(excluded, [])
        self.scope['REPORT_RESULTS'].update({(replacement.sn, 'switch'): 0, (replacement.sn, 'delay'): 0})
        result = await retire(self.hass, [old.sn])
        self.assertTrue(result['results'][0]['retired'])
        self.assertEqual(native, [('old-socket', 2)])
        self.assertEqual(removed, ['old-socket'])
        self.assertEqual(excluded, ['old-socket'])
        self.assertEqual(self.calls, [])

    async def test_metadata_recreation_requires_confirmation_and_never_switches(self):
        requests = []
        device = self.scope['DEVICE']
        device.product = types.SimpleNamespace(pid='014')
        self.scope['DEVICES'][device.sn] = device
        self.scope['STATUS']['reporting_enabled'] = True
        router = types.SimpleNamespace(_lib=types.SimpleNamespace(HilinkSyncBrgDevStatus=object()),
            _c_char_p=lambda sn: sn)
        def submit(func, sn, status):
            requests.append((sn, status))
            future = concurrent.futures.Future()
            future.set_result(0)
            return future
        async def no_wait(seconds):
            pass
        async_tools = types.SimpleNamespace(wait_for=asyncio.wait_for, shield=asyncio.shield,
            wrap_future=asyncio.wrap_future, sleep=no_wait)
        self.scope.update(bridge=types.SimpleNamespace(service_router=router),
            submit_native=submit, asyncio=async_tools, PID='014')
        tree = ast.parse((COMPONENT / 'socket_runtime.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'recreate_metadata']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'metadata-recreation', 'exec'), self.scope)
        recreate = self.scope['recreate_metadata']
        with self.assertRaises(ValueError):
            await recreate(self.hass, [device.sn])
        with self.assertRaises(ValueError):
            await recreate(self.hass, ['unrelated'], True)
        self.assertEqual(requests, [])
        result = await recreate(self.hass, [device.sn], True)
        self.assertEqual(requests, [(device.sn, 2), (device.sn, 3), (device.sn, 1)])
        self.assertFalse(result['physical_switch_commands'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.scope['PAUSED'], set())
