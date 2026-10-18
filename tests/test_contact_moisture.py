import ast
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import time
import types
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / 'custom_components/hwhomebridge'
spec = importlib.util.spec_from_file_location('binary_conversion', COMPONENT / 'contact_moisture_conversion.py')
conversion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conversion)


def state(value):
    return types.SimpleNamespace(state=value)


class BinarySensorTests(unittest.TestCase):
    def test_gas_alarm_fault_and_unknown_are_distinct(self):
        normal = conversion.snapshot('013', state('监测正常'), state('0'))
        self.assertEqual(normal['alarm'], {'alarm': 0})
        self.assertEqual(normal['gasSensor'], {'current': 0, 'level': 1})
        alarm = conversion.snapshot('013', state('天然气泄漏报警'), state('18'))
        self.assertEqual(alarm['alarm'], {'alarm': 1})
        self.assertEqual(alarm['gasSensor'], {'current': 18, 'level': 3})
        for value, code in [('设备故障', 1), ('传感器寿命到期', 2)]:
            result = conversion.snapshot('013', state(value), state('0'))
            self.assertEqual(result, {'commonFaultDetection': {'status': 1, 'code': code}})
            self.assertNotIn('alarm', result)
        for value in ['预热', 'unknown', 'unavailable', '其他状态']:
            self.assertEqual(conversion.snapshot('013', state(value), state('0')), {})
        self.assertEqual(conversion.snapshot('013', state('自检')), {'selfCheck': {'on': 1}})

    def test_open_closed_and_leak_alarm_direction(self):
        for source, value in [('on', 1), ('off', 0)]:
            self.assertEqual(conversion.snapshot('011', state(source)), {'doorSensor': {'status': value}})
            self.assertEqual(conversion.snapshot('012', state(source)), {'warterAlarm': {'alarm': value}})

    def test_unknown_never_becomes_closed_or_no_leak(self):
        for source in ['unknown', 'unavailable', '', '1', None]:
            for pid in ('011', '012'):
                self.assertEqual(conversion.snapshot(pid, state(source)), {})

    def test_battery_percent_does_not_invent_alarm_or_tamper(self):
        self.assertEqual(conversion.snapshot('012', state('on'), state('70')),
                         {'warterAlarm': {'alarm': 1}, 'battery': {'level': 70}})
        for source in ['unknown', 'nan', '101', '-1']:
            self.assertNotIn('battery', conversion.snapshot('012', state('off'), state(source)))
        self.assertNotIn('battery', conversion.snapshot('011', state('on'), state('100')))

    def test_initial_door_sync_is_not_a_fake_open_event(self):
        tree = ast.parse((COMPONENT / 'contact_moisture_runtime.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'send']
        current = {'doorSensor': {'status': 0}}
        submitted = []
        def submit(*args):
            submitted.append(json.loads(args[-1]))
            future = concurrent.futures.Future()
            future.set_result(0)
            return future
        scope = {'STATUS': {'reporting_enabled': True}, 'bridge': types.SimpleNamespace(bridge_work=True),
                 'LAST': {}, 'TRACE': [], 'time': time, 'json': json, 'submit_native': submit,
                 'readings': lambda hass, device: current}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'binary-send', 'exec'), scope)
        device = types.SimpleNamespace(sn='test-sensor', product=types.SimpleNamespace(pid='011'))
        router = types.SimpleNamespace(_hass=None, _lib=types.SimpleNamespace(UpdateHAStatus=object()),
                                       _c_char_p=lambda value: value)
        scope['send'](router, device)
        scope['send'](router, device)
        self.assertEqual(submitted, [{'status': 0}])
        current['doorSensor']['status'] = 1
        scope['send'](router, device)
        self.assertEqual(submitted[-1], {'status': 1, 'event': 1})
        self.assertNotIn('test-sensor', json.dumps(scope['TRACE']))
