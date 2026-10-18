"""The release must validate sockets without pre-staged HA temp assets."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/hwhomebridge'


class ReleaseAssetTests(unittest.TestCase):
    def test_clean_install_uses_packaged_probe_and_verified_libraries(self):
        tree = ast.parse((COMPONENT / 'socket_runtime.py').read_text(encoding='utf-8'))
        install = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install')
        constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                     if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                     and n.targets[0].id in ('LIBRARY_SHA', 'GAS_LIBRARY_SHA')}
        class ProbeReached(Exception):
            pass
        for gas in (False, True):
            with self.subTest(gas=gas), tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
                folder = Path(folder)
                excluded = folder / '.storage/hwhomebridge/config/excluded_devices.txt'
                excluded.parent.mkdir(parents=True)
                excluded.write_text('retired-source\n', encoding='utf-8')
                hass = types.SimpleNamespace(config=types.SimpleNamespace(
                    path=lambda *parts: str(folder.joinpath(*parts))))
                def probe(args, **kwargs):
                    self.assertEqual(Path(args[1]), COMPONENT / 'native_metadata_probe.py')
                    plan_path = Path(args[args.index('--plan') + 1])
                    plan = json.loads(plan_path.read_text(encoding='utf-8'))
                    assets = plan_path.parent.parent
                    for kind in ('source', 'candidate'):
                        library = assets / plan[kind + '_relative']
                        self.assertTrue(library.is_relative_to(COMPONENT))
                        self.assertEqual(hashlib.sha256(library.read_bytes()).hexdigest(),
                                         plan[kind + '_sha256'])
                    expected = constants['GAS_LIBRARY_SHA' if gas else 'LIBRARY_SHA']
                    self.assertEqual(plan['candidate_sha256'], expected)
                    self.assertEqual(plan['candidate_service_capacity'], 64)
                    result = Path(args[args.index('--result') + 1])
                    self.assertTrue(result.parent.is_dir())
                    self.assertTrue(result.is_relative_to(folder))
                    raise ProbeReached
                scope = dict(constants, Path=Path, json=json, hashlib=hashlib, sys=sys,
                             uuid=uuid, subprocess=types.SimpleNamespace(run=probe, DEVNULL=-3),
                             __file__=str(COMPONENT / 'socket_runtime.py'))
                exec(compile(ast.Module(body=[install], type_ignores=[]), 'release-install', 'exec'), scope)
                with self.assertRaises(ProbeReached):
                    scope['install'](hass, {'socket_test_entity': 'switch.test',
                        'socket_entities': [{'entity_id': 'switch.test', 'old_sn': 'retired-source'}],
                        'gas_sensor_enabled': gas})
