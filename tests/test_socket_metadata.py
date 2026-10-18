"""Verify native service type and ID tables independently, without loading SDK."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('socket_metadata_builder', ROOT / 'tools/build_socket_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SocketMetadataTests(unittest.TestCase):
    def test_service_types_and_ids_are_distinct_and_other_bytes_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            folder = Path(folder)
            profile = folder / 'profile.json'
            profile.write_text(json.dumps({'prodId': '124U', 'deviceModel': '1.0',
                'manufacturerId': '19c', 'deviceTypeId': '01D', 'protocolType': 'WiFi',
                'services': [{'serviceId': 'switch', 'serviceType': 'binarySwitch'},
                             {'serviceId': 'update', 'serviceType': 'devOta'}]}), encoding='utf-8')
            plan = builder.build(profile, folder / 'output')
            candidate = (folder / 'output/candidate/libhilink_bridge.so').read_bytes()
            self.assertEqual(candidate[0x220020:0x220040].split(b'\0')[0], b'binarySwitch')
            self.assertEqual(candidate[0x220040:0x220060].split(b'\0')[0], b'devOta')
            self.assertEqual(candidate[0x2202a0:0x2202e0].split(b'\0')[0], b'switch')
            self.assertEqual(candidate[0x2202e0:0x220320].split(b'\0')[0], b'update')
            row = plan['expected_metadata'][0]
            self.assertEqual(row['service_names'], ['binarySwitch', 'devOta'])
            self.assertEqual(row['service_ids'], ['switch', 'update'])
            baseline = (folder / 'output/baseline/libhilink_bridge.so').read_bytes()
            allowed = [(10472, 10480), (10664, 10672), (0x222620, 0x222660),
                       (0x220020, 0x2207a0), (0x1e34a0, 0x1e34a4)]
            allowed += [(offset, offset + len(bytes.fromhex(before)))
                        for offset, before, after in builder.SERVICE_ABI_PATCHES]
            self.assertEqual(plan['candidate_service_capacity'], 64)
            for offset, before, after in builder.SERVICE_ABI_PATCHES:
                self.assertEqual(candidate[offset:offset + len(bytes.fromhex(after))], bytes.fromhex(after))
            self.assertEqual(len(candidate), len(baseline))
            self.assertTrue(all(any(start <= i < end for start, end in allowed)
                for i, (a, b) in enumerate(zip(baseline, candidate)) if a != b))
