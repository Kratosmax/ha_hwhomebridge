"""Correct only slot 6 service types in the verified gas/socket library."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

SOURCE_SHA = 'efa49bee73df8a975fd4ce170d6e2d0b1aa927d91781c264424e9cb96f6d33a4'
SLOT = 6


def build(source, profile_path, baseline_plan, output):
    original = Path(source).read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA:
        raise ValueError('Unverified water baseline')
    profile = json.loads(Path(profile_path).read_text(encoding='utf-8'))
    if any(profile.get(k) != v for k, v in {
        'prodId': '2GB5', 'deviceModel': 'MIR-WA100', 'deviceTypeId': '03C',
        'manufacturerId': '2b0', 'protocolType': 'Mesh'}.items()):
        raise ValueError('Unexpected water profile')
    baseline = json.loads(Path(baseline_plan).read_text(encoding='utf-8'))['expected_metadata']
    if baseline[SLOT]['product_id'] != profile['prodId']:
        raise ValueError('Water slot differs from the expected product')
    ids = [s['serviceId'] for s in profile['services']]
    types = [s['serviceType'] for s in profile['services']]
    if len(ids) != len(baseline[SLOT]['service_names']) or not 0 < len(ids) <= 20:
        raise ValueError('Unexpected water service count')
    offset = 0x220020 + SLOT * 0x780
    for i, sid in enumerate(ids):
        actual = original[offset + 0x280 + i * 64:offset + 0x280 + (i+1) * 64].split(b'\0',1)[0]
        if actual != sid.encode('ascii'):
            raise ValueError('Water service ID precondition failed')
    block = bytearray(0x280)
    for i, service_type in enumerate(types):
        raw = service_type.encode('ascii')
        if not raw or len(raw) >= 32:
            raise ValueError('Invalid water service type')
        block[i*32:i*32+len(raw)] = raw
    data = bytearray(original)
    data[offset:offset+len(block)] = block
    expected = json.loads(json.dumps(baseline))
    expected[SLOT].update(service_names=types, service_ids=ids)
    output = Path(output)
    for name in ('baseline','candidate','plans'):
        (output/name).mkdir(parents=True,exist_ok=True)
    (output/'baseline/libhilink_bridge.so').write_bytes(original)
    (output/'candidate/libhilink_bridge.so').write_bytes(data)
    plan = {'source_sha256':SOURCE_SHA,'candidate_sha256':hashlib.sha256(data).hexdigest(),
        'source_relative':'baseline/libhilink_bridge.so','candidate_relative':'candidate/libhilink_bridge.so',
        'source_service_capacity':64,'candidate_service_capacity':64,'baseline_metadata':baseline,
        'expected_metadata':expected,'expected_unchanged_slots':[i for i in range(8) if i!=SLOT]}
    (output/'plans/socket.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'custom_components/hwhomebridge/native_metadata_probe.py',output/'native_metadata_probe.py')
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--profile',required=True)
    parser.add_argument('--baseline-plan',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(build(args.source,args.profile,args.baseline_plan,args.output)['candidate_sha256'])
