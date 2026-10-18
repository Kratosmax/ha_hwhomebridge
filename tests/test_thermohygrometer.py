import ast
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import types
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('thermo_conversion', ROOT / 'custom_components/hwhomebridge/thermohygrometer_conversion.py')
conversion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conversion)


def state(value):
    return types.SimpleNamespace(state=value)


class ThermohygrometerTests(unittest.TestCase):
    def test_startup_preserves_new_vs_known_registration(self):
        component = ROOT / 'custom_components/hwhomebridge'
        source = ast.parse((component / 'thermohygrometer_runtime.py').read_text(encoding='utf-8'))
        nodes = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name in ('install', 'start')]
        async def no_wait(seconds):
            pass
        async def load_registry(*args):
            pass
        core = types.ModuleType('homeassistant.core')
        core.SupportsResponse = types.SimpleNamespace(ONLY=1)
        for is_new in (True, False):
            with self.subTest(is_new=is_new):
                calls = []
                device = types.SimpleNamespace(sn='test-sensor', product=types.SimpleNamespace(pid='010'), online=True)
                Router = type('Router', (), {'load_product_registry': load_registry,
                    'route_action': lambda *args: None, 'get_char_state': lambda *args: None,
                    'report_state': lambda *args: None,
                    'register_device_to_hilink': lambda self, sn, status: calls.append((sn, status))})
                router = Router()
                router.sn_manager = types.SimpleNamespace(get_by_sn=lambda sn: device,
                    get_all_devices=lambda: [device])
                bridge = types.SimpleNamespace(service_router=router, _get_pid_index=lambda pid: 99)
                scope = dict(_INSTALLED=False, _DEFERRED_NEW=set(), STATUS={}, TRACE=[],
                    __file__=str(component / 'thermohygrometer_runtime.py'), hashlib=hashlib, Path=Path,
                    bridge=bridge, ServiceRouter=Router, PID='010',
                    LIBRARY_SHA='d8401ae4db1307a7e5e3b7b1c3b4af0316eccc6b23643ffa83ee28b0816dcb58',
                    selected=lambda r, sn: device, send=lambda *args: True,
                    aircon_runtime=types.SimpleNamespace(STATUS={'state_reporting_enabled': True}),
                    time=types.SimpleNamespace(time=lambda: 1),
                    asyncio=types.SimpleNamespace(get_running_loop=asyncio.get_running_loop, sleep=no_wait))
                exec(compile(ast.Module(body=nodes, type_ignores=[]), 'thermo-startup', 'exec'), scope)
                scope['install'](None)
                if is_new:
                    router.register_device_to_hilink(device.sn, 3)
                router.register_device_to_hilink(device.sn, 1)
                self.assertEqual(calls, [])
                hass = types.SimpleNamespace(services=types.SimpleNamespace(async_register=lambda *a, **kw: None))
                with patch.dict(sys.modules, {'homeassistant.core': core}):
                    asyncio.run(scope['start'](hass))
                expected = [(device.sn, 3), (device.sn, 1)] if is_new else [(device.sn, 1)]
                self.assertEqual(calls, expected)
                self.assertFalse(scope['_DEFERRED_NEW'])

    def test_product_merge_keeps_both_sensor_bindings_and_rejects_writes(self):
        component = ROOT / 'custom_components/hwhomebridge'
        tree = ast.parse((component / 'product_registry.py').read_text(encoding='utf-8'))
        tree.body = [node for node in tree.body if not (isinstance(node, ast.Import) and
                     any(alias.name == 'aiofiles' for alias in node.names))]
        module = types.ModuleType('thermo_registry_test')
        sys.modules[module.__name__] = module
        exec(compile(tree, 'product_registry.py', 'exec'), module.__dict__)
        async def load_registry(self, path):
            return True
        Router = type('Router', (), {'load_product_registry': load_registry,
            'route_action': lambda *args: 'legacy', 'get_char_state': lambda *args: None,
            'report_state': lambda *args: None, 'register_device_to_hilink': lambda *args: None})
        bridge = types.SimpleNamespace(_get_pid_index=lambda pid: 5 if pid == '009' else 99)
        scope = {name: getattr(module, name) for name in
                 ['ProductDef', 'ServiceDef', 'HAMapping', 'AdapterDef', 'ModelExactMatch']}
        scope.update(_INSTALLED=False, __file__=str(component / 'thermohygrometer_runtime.py'),
            hashlib=hashlib, Path=Path, bridge=bridge, ServiceRouter=Router, PID='010',
            MODEL='miaomiaoce.sensor_ht.t2',
            LIBRARY_SHA='d8401ae4db1307a7e5e3b7b1c3b4af0316eccc6b23643ffa83ee28b0816dcb58',
            selected=lambda router, sn: router.sn_manager.get_by_sn(sn))
        source = ast.parse((component / 'thermohygrometer_runtime.py').read_text(encoding='utf-8'))
        nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'install']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'sensor-install', 'exec'), scope)
        scope['install'](None)
        router = Router()
        router.registry = module.ProductRegistry()
        asyncio.run(router.load_product_registry('unused'))
        adapter = router.registry._adapters[0]
        merged = router.registry.merge(router.registry._products['010'], adapter)
        for name in ('temperature', 'humidity'):
            self.assertEqual(merged.services[name].ha_mapping.device_class, name)
            self.assertEqual(merged.services[name].ha_mapping.domain, 'sensor')
            self.assertEqual(merged.services[name].c_service_id, 'airDetector')
        router.sn_manager = types.SimpleNamespace(get_by_sn=lambda sn: object() if sn == 'sensor' else None)
        self.assertFalse(router.route_action('sensor', {'on': 1}))
        self.assertEqual(router.route_action('other', {'on': 1}), 'legacy')
        self.assertEqual(bridge._get_pid_index('010'), 3)
        self.assertEqual(bridge._get_pid_index('009'), 5)

    def test_profile_integer_measurements_and_negative_rounding(self):
        result = conversion.snapshot(state('23.8'), state('95'))
        self.assertEqual(result, {'airDetector': {'temperature': 2380, 'humidity': 9500}})
        self.assertTrue(all(type(v) is int for v in result['airDetector'].values()))
        self.assertEqual(result['airDetector']['temperature'] / 100, 23.8)
        self.assertEqual(result['airDetector']['humidity'] / 100, 95)
        self.assertEqual(conversion.snapshot(state('-2.5'), state('0')),
                         {'airDetector': {'temperature': -250, 'humidity': 0}})

    def test_missing_measurement_does_not_erase_other_measurement(self):
        self.assertEqual(conversion.snapshot(state('unavailable'), state('42')),
                         {'airDetector': {'humidity': 4200}})
        self.assertEqual(conversion.snapshot(state('21'), None),
                         {'airDetector': {'temperature': 2100}})

    def test_bad_or_unavailable_states_are_never_defaulted(self):
        for value in ['unknown', 'unavailable', '', 'nan', 'inf', '-inf', 'invalid', None]:
            self.assertEqual(conversion.snapshot(state(value), state(value)), {})
        self.assertEqual(conversion.snapshot(state('-21'), state('101')), {})
        self.assertEqual(conversion.snapshot(state('101'), state('-1')), {})


if __name__ == '__main__':
    unittest.main()
