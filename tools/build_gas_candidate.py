"""Build a gas candidate from the verified socket library; never deploy it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'afbd689f2b9f10137428a51898cf83dad72de87a51cf9f9c09f493bbc9861a12'
SLOT = 7  # Only usable after every former breaker has been retired.


def build(source, profile_path, output, baseline_plan):
    original = Path(source).read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA:
        raise ValueError('Unverified socket baseline')
    profile = json.loads(Path(profile_path).read_text(encoding='utf-8'))
    expected = {'prodId': '2MXG', 'deviceModel': 'JT-GA01-PLC',
                'deviceTypeId': '03A', 'manufacturerId': '2b0', 'protocolType': 'PLC'}
    if any(profile.get(k) != v for k, v in expected.items()):
        raise ValueError('Unexpected gas profile')
    ids = [s['serviceId'] for s in profile['services']]
    types = [s['serviceType'] for s in profile['services']]
    if not 0 < len(ids) <= 20:
        raise ValueError('Unsupported service count')
    data = bytearray(original)
    # Slot 7's own preallocated spare record; do not touch socket slot 0.
    record_offset = 0x2227e0
    record_address = record_offset + 0x1000
    for offset, before, after in [(0x2990, 0x1e34e0, record_address + 36),
                                  (0x2a50, 0x1e3507, record_address + 40)]:
        if struct.unpack_from('<Q', data, offset)[0] != before:
            raise ValueError('Gas relocation precondition failed')
        struct.pack_into('<Q', data, offset, after)
    record = bytearray(64)
    for offset, value, limit in [(0, '2b0', 4), (4, 'JT-GA01-PLC', 32),
                                 (36, '03A', 4), (40, '2MXG', 5)]:
        raw = value.encode('ascii')
        if len(raw) >= limit:
            raise ValueError('Native field too long')
        record[offset:offset + len(raw)] = raw
    data[record_offset:record_offset + 64] = record
    table = 0x220020 + SLOT * 0x780
    for offset, size, stride, values in [(table, 0x280, 32, types),
                                        (table + 0x280, 0x500, 64, ids)]:
        block = bytearray(size)
        for index, value in enumerate(values):
            raw = value.encode('ascii')
            if not raw or len(raw) >= stride:
                raise ValueError('Invalid native service field')
            block[index * stride:index * stride + len(raw)] = raw
        data[offset:offset + size] = block
    struct.pack_into('<I', data, 0x1e34a0 + SLOT * 4, 5)
    baseline = json.loads(Path(baseline_plan).read_text(encoding='utf-8'))['expected_metadata']
    products = json.loads(json.dumps(baseline))
    products[SLOT] = {'index': SLOT, 'product_id': '2MXG', 'sub_product_id': '00',
        'model': 'JT-GA01-PLC', 'device_type': '03A', 'manufacturer': '2b0',
        'protocol_type': 5, 'service_names': types, 'service_ids': ids}
    output = Path(output)
    for name in ('baseline', 'candidate', 'plans'):
        (output / name).mkdir(parents=True, exist_ok=True)
    (output / 'baseline/libhilink_bridge.so').write_bytes(original)
    (output / 'candidate/libhilink_bridge.so').write_bytes(data)
    plan = {'source_sha256': SOURCE_SHA, 'candidate_sha256': hashlib.sha256(data).hexdigest(),
        'source_relative': 'baseline/libhilink_bridge.so', 'candidate_relative': 'candidate/libhilink_bridge.so',
        'source_service_capacity': 64, 'candidate_service_capacity': 64,
        'baseline_metadata': baseline, 'expected_metadata': products,
        'expected_unchanged_slots': list(range(7))}
    (output / 'plans/socket.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    shutil.copyfile(ROOT / 'custom_components/hwhomebridge/native_metadata_probe.py',
                    output / 'native_metadata_probe.py')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--baseline-plan', required=True)
    args = parser.parse_args()
    plan = build(args.source, args.profile, ROOT / 'temp/gas-v2/native', args.baseline_plan)
    print(plan['candidate_sha256'])
