"""Reject common deployment secrets in the public Git working tree."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'JWT': rb'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}',
    'GitHub token': rb'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'LAN address': rb'(?<![0-9])(?:192\.168\.[0-9]{1,3}\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})(?![0-9])',
    'device-specific entity': rb'(?:climate|switch|sensor|light)\.[a-z]+_cn_[0-9]{6,}',
    'device serial': rb'HB(?:AC)?[0-9a-f]{12,16}\b',
    'personal Windows path': rb'[A-Za-z]:[\\/](?:Users[\\/]|04_tmp[\\/]|homeassistant[\\/])',
}


def check():
    result = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    failures = []
    for name in set(result.decode('utf-8').split('\0')) - {''}:
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        for kind, pattern in PATTERNS.items():
            if re.search(pattern, data):
                failures.append((name, kind))
        if any(part in ('.storage', '__pycache__', 'temp') for part in Path(name).parts):
            failures.append((name, 'runtime/generated directory'))
    if failures:
        for name, kind in failures:
            print(f'REJECT {name}: {kind}')
        raise SystemExit(1)
    print('Privacy scan passed: public working-tree files only; no matching credentials or deployment identifiers')


if __name__ == '__main__':
    check()
