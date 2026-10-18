import importlib.util
from pathlib import Path
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('socket_meter_test',
    ROOT / 'custom_components/hwhomebridge/socket_meter.py')
meter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meter)


def state(value, **attributes):
    return types.SimpleNamespace(state=value, attributes=attributes)


class MeterTests(unittest.TestCase):
    def test_ha_watts_are_not_rescaled_from_a_misleading_property_name(self):
        reading = state('180', unit_of_measurement='W', friendly_name='电功率(单位0.01w)')
        self.assertEqual(meter.power(reading), {'current': 180})
        self.assertEqual(meter.power(state('190', unit_of_measurement='W')), {'current': 190})

    def test_centiwatt_source_and_integer_watt_card_are_not_confused(self):
        self.assertEqual(meter.power(state('223'), '0.01'), {'current': 2})
        self.assertEqual(meter.power(state('1'), '0.01'), {'current': 0})
        self.assertEqual(meter.power(state('250'), '0.01'), {'current': 3})
        self.assertIsNone(meter.power(state('600001'), '0.01'))
        for value in ('unavailable', 'unknown', 'nan', 'inf', '-1'):
            self.assertIsNone(meter.power(state(value)))

    def test_kwh_conversion_requires_total_increasing_and_known_unit(self):
        self.assertEqual(meter.energy_wh(state('0.2', state_class='total_increasing', unit_of_measurement='kWh')), 200)
        self.assertIsNone(meter.energy_wh(state('0.2', state_class='measurement', unit_of_measurement='kWh')))

    def test_repeated_total_and_restart_do_not_duplicate_energy(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            path = Path(folder) / 'energy.json'
            counter = meter.EnergyCounter(path)
            self.assertEqual(counter.pending('one', 200), (0, 200))
            self.assertIsNone(counter.pending('one', 200))
            self.assertEqual(counter.pending('one', 210), (10, 210))
            self.assertEqual(counter.pending('one', 210), (10, 210))
            counter.acknowledge('one', 210)
            counter = meter.EnergyCounter(path)
            self.assertIsNone(counter.pending('one', 210))
            self.assertEqual(counter.pending('two', 500), (0, 500))
            self.assertEqual(counter.pending('one', 225), (15, 225))
            self.assertIsNone(counter.pending('two', 500))

    def test_resets_and_profile_limit_preserve_unreported_remainder(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            counter = meter.EnergyCounter(Path(folder) / 'energy.json')
            counter.pending('one', 200)
            self.assertEqual(counter.pending('one', 5), (5, 5))
            counter.acknowledge('one', 5)
            self.assertEqual(counter.pending('one', 2505), (1000, 1005))
            counter.acknowledge('one', 1005)
            self.assertEqual(counter.pending('one', 2505), (1000, 2005))
            counter.acknowledge('one', 2005)
            self.assertEqual(counter.pending('one', 2505), (500, 2505))
