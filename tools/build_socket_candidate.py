"""Build a 124U metadata-only experiment in temp; never deploy an active DLL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'ea844c3bd54d324f116ca69bf0dc3ed94e3987f3f6946a8cceea32aa5be88de0'

# SDK consumers use BrgDevSvcInfo with 64 entries (IDs at 0x800).
# The vendor callbacks keep their private 20-entry source tables, but must
# write the public output structure and batch stride using the SDK layout.
SERVICE_ABI_PATCHES = [
    (0xe34f, '4c8da380020000', '4c8da300080000'),
    (0xe78a, '4c8da580020000', '4c8da500080000'),
    (0xe828, '488144241080070000', '488144241000180000'),
]


def build(profile_path, output):
    component = ROOT / 'custom_components/hwhomebridge'
    source = component / 'hilink_bridge/binary_sensors/lib/amd64/libhilink_bridge.so'
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA:
        raise ValueError('Unsupported binary baseline')
    profile = json.loads(Path(profile_path).read_text(encoding='utf-8'))
    if any(profile.get(key) != value for key, value in {
        'prodId': '124U', 'deviceModel': '1.0', 'manufacturerId': '19c',
        'deviceTypeId': '01D', 'protocolType': 'WiFi'}.items()):
        raise ValueError('Unexpected socket profile')
    services = [s['serviceId'] for s in profile['services']]
    service_types = [s['serviceType'] for s in profile['services']]
    if not services or len(services) > 20 or any(len(s.encode('ascii')) >= 32 for s in services):
        raise ValueError('Unsupported native service table size')
    data = bytearray(original)
    for offset, before, after in SERVICE_ABI_PATCHES:
        before, after = bytes.fromhex(before), bytes.fromhex(after)
        if data[offset:offset + len(before)] != before:
            raise ValueError('Service ABI instruction precondition failed')
        data[offset:offset + len(before)] = after
    # Fixed-version relocations point at the slot0 spare metadata record.
    for offset, before, after in [(10472, 0x1e34c4, 0x223644),
                                  (10664, 0x1e34e4, 0x223648)]:
        if struct.unpack_from('<Q', data, offset)[0] != before:
            raise ValueError('Relocation precondition failed')
        struct.pack_into('<Q', data, offset, after)
    record = bytearray(64)
    record[0:4] = b'19c\0'
    record[4:8] = b'1.0\0'
    record[36:40] = b'01D\0'
    record[40:45] = b'124U\0'
    data[0x222620:0x222660] = record
    if any(not s or len(s.encode('ascii')) >= 32 for s in service_types):
        raise ValueError('Unsupported native service type')
    for offset, size, stride, names in [(0x220020, 0x280, 32, service_types),
                                       (0x2202a0, 0x500, 64, services)]:
        table = bytearray(size)
        for index, name in enumerate(names):
            table[index * stride:index * stride + len(name)] = name.encode('ascii')
        data[offset:offset + size] = table
    struct.pack_into('<I', data, 0x1e34a0, 1)
    baseline = json.loads((component / 'hilink_bridge/binary_sensors/metadata-plan.json').read_text(
        encoding='utf-8'))['expected_metadata']
    expected = json.loads(json.dumps(baseline))
    expected[0] = {'index': 0, 'product_id': '124U', 'sub_product_id': '00', 'model': '1.0',
        'device_type': '01D', 'manufacturer': '19c', 'protocol_type': 1, 'service_names': service_types,
        'service_ids': services}
    output = Path(output)
    for name in ('baseline', 'candidate', 'plans'):
        (output / name).mkdir(parents=True, exist_ok=True)
    (output / 'baseline/libhilink_bridge.so').write_bytes(original)
    (output / 'candidate/libhilink_bridge.so').write_bytes(data)
    plan = {'source_sha256': SOURCE_SHA, 'candidate_sha256': hashlib.sha256(data).hexdigest(),
        'candidate_service_capacity': 64,
        'source_relative': 'baseline/libhilink_bridge.so',
        'candidate_relative': 'candidate/libhilink_bridge.so', 'baseline_metadata': baseline,
        'expected_metadata': expected, 'expected_unchanged_slots': list(range(1, 8))}
    (output / 'plans/socket.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    shutil.copyfile(component / 'native_metadata_probe.py', output / 'native_metadata_probe.py')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    args = parser.parse_args()
    plan = build(args.profile, ROOT / 'temp/socket-native-probe')
    print('Isolated socket candidate:', plan['candidate_sha256'])
