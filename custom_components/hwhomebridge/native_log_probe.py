"""Forward native stdout unchanged; persist only allowlisted numeric diagnostics."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import threading


def parse_line(line):
    events = []
    patterns = (
        ('batch_bind_request', r'POST /device/v3/batchBind, count\[(\d+)\]'),
        ('cloud_error', r'cloud resp err:(\d+) count:'),
        ('batch_success_count', r'batch add resp succ dev num\[(\d+)\]'),
        ('batch_failure_count', r'bridge dev batch add resp failure dev num\[(\d+)\]'),
        ('metadata_failure', r'BatchGetSubDevInfo failed, err\[(-?\d+)\]'),
        ('room_info_failure', r'BatchGetSubDevRoomInfo error\[(-?\d+)\]'),
        ('sync_payload_failure', r'Fill Batch Sync info for cloud failed, err\[(-?\d+)\]'),
        ('cloud_add_start_index', r'Start add dev in cloud, dev index=\[(\d+)\]'),
        ('cloud_online_start_index', r'Start online dev\[(\d+)\]'),
        ('cloud_sync_start_index', r'Start synDev dev\[(\d+)\]'),
    )
    for kind, pattern in patterns:
        match = re.search(pattern, line)
        if match:
            events.append({'kind': kind, 'value': int(match[1])})
    if 'add dev cloud resp sucess' in line:
        events.append({'kind': 'cloud_add_success_marker'})
    match = re.search(r'Recv cloud authCode\((Normal|Empty)\) devId:([^,\s]+), authCodeId:', line)
    if match:
        events.append({'kind': 'cloud_auth_state', 'present': match[1] == 'Normal',
                       'device_fingerprint': hashlib.sha256(match[2].encode()).hexdigest()})
    for marker, kind in (
        ('uid hash not exist!', 'cloud_user_hash_missing'),
        ('notify cloudsetup auth info failed!', 'cloud_auth_notification_failed'),
        ('notify brg sub dev auth info failed!', 'subdevice_auth_notification_failed'),
        ('notify auth code failed', 'auth_notification_failed'),
    ):
        if marker in line:
            events.append({'kind': kind})
    # Some SDK builds print the JSON response; retain schema evidence only.
    # Neither a raw response nor any authentication field is persisted here.
    if '"successList"' in line or '"failureList"' in line:
        for start in (m.start() for m in re.finditer(r'\{', line)):
            try:
                response, _ = json.JSONDecoder().raw_decode(line[start:])
            except (ValueError, TypeError):
                continue
            if not isinstance(response, dict):
                continue
            if not any(k in response for k in ('successList', 'failureList')):
                continue
            for key, success in (('successList', True), ('failureList', False)):
                items = response.get(key)
                if not isinstance(items, list):
                    continue
                events.append({'kind': 'cloud_bind_response_count', 'success': success,
                               'value': len(items)})
                for item in items[:64]:
                    if not isinstance(item, dict):
                        continue
                    auth = item.get('authCodeInfo')
                    event = {'kind': 'cloud_bind_response_item', 'success': success,
                             'device_id_present': isinstance(item.get('devId'), str) and bool(item['devId']),
                             'auth_code_present': isinstance(auth, dict) and bool(auth.get('authCode'))}
                    if event['device_id_present']:
                        event['device_fingerprint'] = hashlib.sha256(item['devId'].encode()).hexdigest()
                    events.append(event)
            break
    match = re.search(r'subdev Cresp dev\[(\d+)\] status:(\d+)', line)
    if match:
        events.append({'kind': 'cloud_response_index', 'index': int(match[1]), 'status': int(match[2])})
    if 'HBAC' in line:
        if '[BatchGetSubDevInfo]' in line:
            events.append({'kind': 'test_metadata_query'})
        if 'prodid is 2ANJ' in line:
            events.append({'kind': 'test_product_2ANJ'})
        if 'HilinkGetBrgDevCharState' in line:
            events.append({'kind': 'test_state_query', 'null_service': '(null)' in line})
    if 'prodId=2ANJ' in line:
        match = re.search(r'devType=([0-9A-Fa-f]{3})\b', line)
        if match:
            events.append({'kind': 'aircon_metadata', 'device_type': match[1]})
    # Store only public endpoint names, never their requests/responses or IDs.
    for endpoint in ('batchDelete', 'batchUnbind', 'batchSync', 'batchDel'):
        if '/device/v3/' + endpoint in line:
            events.append({'kind': 'cleanup_or_sync_endpoint', 'endpoint': endpoint})
    return events


class NativeLogProbe:
    def __init__(self, path):
        self.path = Path(path)
        self.events = []
        self.error = None
        self.thread = None
        self.original = None

    def _record(self, line):
        for event in parse_line(line.decode('utf-8', errors='replace')):
            event['sequence'] = len(self.events)
            self.events.append(event)
            try:
                with self.path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event) + '\n')
            except Exception as error:
                # A failed diagnostic write must not stop draining HA stdout.
                self.error = type(error).__name__

    def _read(self, descriptor, destination):
        pending = b''
        forwarding = True
        try:
            while True:
                data = os.read(descriptor, 8192)
                if not data:
                    break
                if forwarding:
                    try:
                        remainder = memoryview(data)
                        while remainder:
                            written = os.write(destination, remainder)
                            if not written:
                                raise OSError('Stdout destination closed')
                            remainder = remainder[written:]
                    except OSError as error:
                        self.error = type(error).__name__
                        forwarding = False
                pending += data
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    self._record(line)
                if len(pending) > 65536:
                    pending = pending[-4096:]
            if pending:
                self._record(pending)
        except Exception as error:
            self.error = type(error).__name__
        finally:
            os.close(descriptor)
            os.close(destination)

    def start(self):
        if self.thread is not None:
            raise RuntimeError('Probe already started')
        self.path.touch(exist_ok=False)
        read_fd, write_fd = os.pipe()
        self.original = os.dup(1)
        forward_fd = os.dup(1)
        self.thread = threading.Thread(target=self._read, args=(read_fd, forward_fd),
                                       name='hwhomebridge_numeric_log_probe', daemon=True)
        self.thread.start()
        os.dup2(write_fd, 1)
        os.close(write_fd)

    def close(self):
        if self.original is None:
            return
        try:
            if os.name != 'nt':
                ctypes.CDLL(None).fflush(None)
        finally:
            os.dup2(self.original, 1)
            os.close(self.original)
            self.original = None
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.error = 'ReaderDidNotStop'
