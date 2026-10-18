"""Gas candidate must preserve the working slots and reject occupied slots."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gas_builder', ROOT / 'tools/build_gas_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class GasCandidateTests(unittest.TestCase):
    def test_binding_diagnostics_never_persist_credentials(self):
        spec = importlib.util.spec_from_file_location('binding_log_probe', ROOT / 'custom_components/hwhomebridge/native_log_probe.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        line = 'Recv cloud authCode(Normal) devId:private-device, authCodeId:private-auth-id, userIdHash:private-user'
        events = module.parse_line(line)
        self.assertEqual(events[0]['kind'], 'cloud_auth_state')
        self.assertTrue(events[0]['present'])
        self.assertEqual(events[0]['device_fingerprint'], hashlib.sha256(b'private-device').hexdigest())
        payload = {'successList': [{'devId':'private-device','authCodeInfo':{'authCode':'private-key'}}],
                   'failureList':[{'sn':'private-serial','errorMessage':'private-message'}]}
        events += module.parse_line('response: ' + json.dumps(payload))
        self.assertTrue(any(e.get('auth_code_present') is True for e in events))
        self.assertTrue(any(e.get('success') is False for e in events))
        serialized = json.dumps(events)
        for private in ('private-device','private-auth-id','private-user','private-key','private-serial','private-message'):
            self.assertNotIn(private, serialized)
        self.assertEqual(module.parse_line('response: {"successList": broken'), [])

    def test_identity_override_only_applies_to_enabled_gas_model(self):
        tree = ast.parse((ROOT / 'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'register_device')
        calls = []
        def original(*args, **kwargs):
            calls.append(kwargs['reuse_sn'])
            return object()
        scope = {'gas_enabled': True, 'identity_revision': 2,
                 'gas_identity_sn': lambda *args: 'fresh-gas', 'old_device_register': original}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'gas-register-wrapper','exec'),scope)
        register = scope['register_device']
        register(None,'device','name',[],model='unrelated.light',reuse_sn='existing-light')
        register(None,'device','name',[],model='lumi.sensor_gas.mcn02',reuse_sn='old-gas')
        scope['gas_enabled'] = False
        register(None,'device','name',[],model='lumi.sensor_gas.mcn02',reuse_sn='old-gas')
        self.assertEqual(calls, ['existing-light','fresh-gas','old-gas'])

    def test_native_stage_logs_keep_numeric_index_without_private_text(self):
        spec = importlib.util.spec_from_file_location('gas_log_probe', ROOT / 'custom_components/hwhomebridge/native_log_probe.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.parse_line('subdev Cresp dev[29] status:14 sn=PRIVATE'),
                         [{'kind':'cloud_response_index','index':29,'status':14}])
        self.assertEqual(module.parse_line('Start add dev in cloud, dev index=[29]'),
                         [{'kind':'cloud_add_start_index','value':29}])

    def test_gas_identity_is_stable_and_revisions_are_distinct(self):
        tree = ast.parse((ROOT / 'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'gas_identity_sn')
        manager = types.SimpleNamespace(generate_sn=lambda text: 'HB' + hashlib.sha256(text.encode()).hexdigest()[:14])
        scope = {'SNManager': manager}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'gas-identity','exec'),scope)
        generate = scope['gas_identity_sn']
        self.assertEqual(generate('lab-device', 1), manager.generate_sn('lab-device'))
        self.assertEqual(generate('lab-device', 2), generate('lab-device', 2))
        self.assertNotEqual(generate('lab-device', 1), generate('lab-device', 2))
        self.assertNotEqual(generate('another-device', 2), generate('lab-device', 2))
        for revision in (0,3,True,'2'):
            with self.assertRaises(ValueError): generate('lab-device', revision)

    def test_bad_gas_candidate_restores_baseline_before_sdk_starts(self):
        tree = ast.parse((ROOT / 'custom_components/hwhomebridge/__init__.py').read_text(encoding='utf-8'))
        setup = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'async_setup'][-1]
        settings = {'enabled': True, 'thermohygrometer_enabled': True,
                    'contact_moisture_enabled': True, 'socket_test_enabled': True,
                    'gas_sensor_enabled': True}
        events = []
        async def start(*args):
            pass
        def socket_install(hass, current):
            if current['gas_sensor_enabled']:
                events.append('gas-validation-failed')
                raise ValueError('Bad candidate')
            events.append('baseline-installed')
        def disable_gas():
            events.append('gas-disabled')
        async def sdk_start(hass, config):
            events.append('sdk-started')
            self.assertEqual(events[:3], ['gas-validation-failed','gas-disabled','baseline-installed'])
            return True
        package = types.ModuleType('gas_setup_test')
        package.__path__ = []
        modules = {'gas_setup_test': package}
        for name in ('aircon_runtime','thermohygrometer_runtime','contact_moisture_runtime','socket_runtime'):
            module = types.ModuleType('gas_setup_test.' + name)
            module.install = socket_install if name == 'socket_runtime' else lambda *args: True
            module.start = start
            module.disable_gas = disable_gas
            setattr(package, name, module)
            modules[module.__name__] = module
        module = types.ModuleType('gas_setup_test.aircon_settings')
        module.load_settings = lambda path: settings.copy()
        module.resolve_entity = lambda *args: 'climate.test'
        modules[module.__name__] = module
        class Hass:
            config = types.SimpleNamespace(path=lambda *args: 'unused')
            data = {'hwhomebridge': {}}
            async def async_add_executor_job(self, function, *args):
                return function(*args)
            def async_create_background_task(self, coroutine, name):
                coroutine.close()
                return name
        scope = {'__package__':'gas_setup_test','_official_aircon_setup':sdk_start,
                 'DOMAIN':'hwhomebridge','_LOGGER':Mock()}
        with patch.dict(sys.modules, modules):
            exec(compile(ast.Module(body=[setup],type_ignores=[]),'gas-setup','exec'),scope)
            self.assertTrue(asyncio.run(scope['async_setup'](Hass(), {})))
        self.assertEqual(events, ['gas-validation-failed','gas-disabled','baseline-installed','sdk-started'])

    def test_gas_add_is_not_immediately_overwritten_by_online(self):
        tree = ast.parse((ROOT / 'custom_components/hwhomebridge/contact_moisture_runtime.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'registration_statuses')
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'registration-policy', 'exec'), scope)
        self.assertEqual(scope['registration_statuses']('013'), (3,))
        self.assertEqual(scope['registration_statuses']('013', True), (1,))
        self.assertEqual(scope['registration_statuses']('011'), (3,))
        self.assertEqual(scope['registration_statuses']('011', True), (1,))
        self.assertEqual(scope['registration_statuses']('012'), (3,))
        self.assertEqual(scope['registration_statuses']('012', True), (1,))

    def test_retired_breaker_guard_runs_before_native_or_bridge_changes(self):
        tree = ast.parse((ROOT / 'custom_components/hwhomebridge/socket_runtime.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install')
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            folder = Path(folder)
            excluded = folder / '.storage/hwhomebridge/config/excluded_devices.txt'
            excluded.parent.mkdir(parents=True)
            excluded.write_text('retired-socket\n', encoding='utf-8')
            class Config:
                def path(self, *parts):
                    return str(folder.joinpath(*parts))
            class Hass:
                config = Config()
            scope = {'Path': Path, 'json': json, '__file__': str(folder / 'missing/socket_runtime.py')}
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'socket-install', 'exec'), scope)
            for selections in ([{'entity_id': 'switch.test'}],
                               [{'entity_id': 'switch.test', 'old_sn': 'still-active'}]):
                with self.assertRaisesRegex(ValueError, 'former breakers'):
                    scope['install'](Hass(), {'socket_test_entity': 'switch.test',
                        'socket_entities': selections, 'gas_sensor_enabled': True})
            # With a retired source, reach plan validation. There is no bridge
            # or native object in scope, so neither path can have been touched.
            scope.update(GAS_LIBRARY_SHA='verified', LIBRARY_SHA='baseline')
            with self.assertRaises(FileNotFoundError):
                scope['install'](Hass(), {'socket_test_entity': 'switch.test',
                    'socket_entities': [{'entity_id': 'switch.test', 'old_sn': 'retired-socket'}],
                    'gas_sensor_enabled': True})

    def test_unverified_baseline_cannot_build(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            folder = Path(folder)
            source = folder / 'unverified.so'
            source.write_bytes(b'not the verified running library')
            with self.assertRaisesRegex(ValueError, 'baseline'):
                builder.build(source, folder / 'missing-profile', folder / 'output', folder / 'missing-plan')
            self.assertFalse((folder / 'output').exists())
