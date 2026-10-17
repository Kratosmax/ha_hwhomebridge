"""Reproduce the fixed-version amd64 candidate without private device data."""
import hashlib
import json
from pathlib import Path


def build(source, output, patch_path):
    patch = json.loads(Path(patch_path).read_text(encoding='utf-8'))
    data = bytearray(Path(source).read_bytes())
    if hashlib.sha256(data).hexdigest() != patch['source_sha256']:
        raise ValueError('Unsupported source library; refusing to patch')
    for edit in patch['edits']:
        offset = edit['offset']
        before, after = bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
        if len(before) != len(after) or data[offset:offset + len(before)] != before:
            raise ValueError('Patch precondition failed')
        data[offset:offset + len(after)] = after
    if hashlib.sha256(data).hexdigest() != patch['candidate_sha256']:
        raise ValueError('Candidate checksum mismatch')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(data)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    component = root / 'custom_components' / 'hwhomebridge' / 'hilink_bridge'
    build(component / 'lib/amd64/libhilink_bridge.so',
          root / 'temp/rebuilt-aircon.so', Path(__file__).with_name('aircon-amd64-patch.json'))
    print('Candidate rebuilt and checksum verified in temp/')
