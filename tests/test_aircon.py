import ast
import concurrent.futures
import importlib.util
import json
import pathlib
import tempfile
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/hwhomebridge'


def load(name):
    spec = importlib.util.spec_from_file_location(name, COMPONENT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conversion = load('aircon_conversion')
settings = load('aircon_settings')
scope = {'json': json, 'command': conversion.command, 'report': conversion.report}
tree = ast.parse((COMPONENT / 'aircon_runtime.py').read_text(encoding='utf-8'))
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('snapshot', 'translate', 'send_temperature')]
exec(compile(ast.Module(body=functions, type_ignores=[]), 'runtime-pure-functions', 'exec'), scope)


class ClimateTests(unittest.TestCase):
    def setUp(self):
        self.state = types.SimpleNamespace(state='cool', attributes={
            'temperature': 25, 'current_temperature': 22, 'fan_mode': '低',
            'min_temp': 16, 'max_temp': 30, 'target_temp_step': 1,
            'fan_modes': ['自动', '低', '中', '高'],
            'hvac_modes': ['auto', 'cool', 'heat', 'dry', 'fan_only', 'off'],
        })

    def test_huawei_temperature_fields_use_integer_setpoint(self):
        snapshot = scope['snapshot'](self.state)
        self.assertEqual(snapshot['temperature'], {'current': 25, 'target': 25})
        self.state.attributes['temperature'] = 27.0
        actual = scope['snapshot'](self.state)['temperature']
        self.assertEqual(actual, {'current': 27, 'target': 27})
        self.assertTrue(all(type(value) is int for value in actual.values()))

    def test_missing_room_temperature_does_not_block_setpoint(self):
        self.state.attributes['current_temperature'] = None
        self.assertEqual(scope['snapshot'](self.state)['temperature'], {'current': 25, 'target': 25})
        for target in [None, True, 26.5, float('nan'), float('inf')]:
            self.state.attributes['temperature'] = target
            self.assertNotIn('temperature', scope['snapshot'](self.state))

    def test_profile_mode_order(self):
        self.assertEqual(conversion.command(self.state, 'state', {'mode': 3}), ('set_hvac_mode', {'hvac_mode': 'fan_only'}))
        self.assertEqual(conversion.command(self.state, 'state', {'mode': 4}), ('set_hvac_mode', {'hvac_mode': 'dry'}))

    def test_unsupported_automatic_fan_is_not_mapped_to_low(self):
        self.state.attributes['fan_mode'] = '自动'
        self.assertNotIn('fan', scope['snapshot'](self.state))
        with self.assertRaises(ValueError):
            conversion.command(self.state, 'fan_mode', {'gear': 1})

    def test_temperature_validation(self):
        for value in [True, 15, 31, 16.5, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                conversion.command(self.state, 'temperature', {'target': value})
        self.assertEqual(conversion.command(self.state, 'temperature', {'target': 24}), ('set_temperature', {'temperature': 24.0}))

    def test_temperature_report_records_sdk_completion_and_integer_payload(self):
        for return_code in (0, -40):
            future = concurrent.futures.Future()
            submitted = []
            scope.update(time=time, TEMPERATURE_TRACE=[],
                         submit_native=lambda *args: submitted.append(args) or future)
            router = types.SimpleNamespace(_lib=types.SimpleNamespace(UpdateHAStatus=object()),
                                           _c_char_p=lambda value: value)
            payload = scope['snapshot'](self.state)['temperature']
            self.assertIs(scope['send_temperature'](router, 'test-device', payload), future)
            self.assertEqual(json.loads(submitted[0][-1]), {'current': 25, 'target': 25})
            self.assertEqual(len(scope['TEMPERATURE_TRACE']), 1)
            future.set_result(return_code)
            self.assertEqual(scope['TEMPERATURE_TRACE'][-1]['sdk_result'], return_code)
            self.assertNotIn('test-device', json.dumps(scope['TEMPERATURE_TRACE']))

    def test_flat_nested_and_sid_commands(self):
        for payload in [{'target': 24}, {'temperature': {'target': 24}}, {'sid': 'temperature', 'data': {'target': 24}}]:
            self.assertEqual(scope['translate'](self.state, payload), [('set_temperature', {'temperature': 24.0})])

    def test_multiple_services_and_invalid_switch(self):
        result = scope['translate'](self.state, {'switch': {'on': 1}, 'fan': {'gear': 4}})
        self.assertEqual(result, [('turn_on', {}), ('set_fan_mode', {'fan_mode': '高'})])
        for value in [True, '1', 2]:
            with self.assertRaises(ValueError):
                scope['translate'](self.state, {'on': value})

    def test_unavailable_rejects_commands_and_reports(self):
        self.state.state = 'unavailable'
        self.assertEqual(scope['snapshot'](self.state), {})
        with self.assertRaises(ValueError):
            scope['translate'](self.state, {'on': 1})

    def test_local_settings_validation(self):
        (ROOT / 'temp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            path = pathlib.Path(folder) / 'settings.json'
            self.assertEqual(settings.load_settings(path), {})
            for value in [[], {'entity_id': 'switch.example'}, {'enabled': 'yes'}]:
                path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):
                    settings.load_settings(path)
            path.write_text('{"entity_id":"climate.example"}', encoding='utf-8')
            self.assertEqual(settings.load_settings(path)['entity_id'], 'climate.example')

    def test_log_probe_never_saves_raw_credentials(self):
        probe = load('native_log_probe')
        self.assertEqual(probe.parse_line('unrelated credential and personal text'), [])
        self.assertEqual(probe.parse_line('cloud resp err:15013 count:1'), [{'kind': 'cloud_error', 'value': 15013}])


if __name__ == '__main__':
    unittest.main()
