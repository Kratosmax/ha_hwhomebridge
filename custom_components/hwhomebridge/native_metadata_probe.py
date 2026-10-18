"""Read fixed product metadata in a separate Linux process, with networking denied.

Does not start SDK main(), read gateway bindings, register devices, or control HA.
Private addresses are permitted only for the verified original amd64 binary.
"""
import ctypes as c
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
LIB = Path('/config/custom_components/hwhomebridge/hilink_bridge/lib/amd64/libhilink_bridge.so')
EXPECTED = '0579e6f3cee0320d1533e5a96cc6d72a065a43050eff4edcb7afd6a9a52c7b58'
DIAGNOSTIC = {'stage': 'starting', 'checks': {}}


def require(condition, stage, **details):
    DIAGNOSTIC['stage'] = stage
    DIAGNOSTIC['checks'][stage] = details
    if not condition:
        raise AssertionError(stage)


class Filter(c.Structure):
    _fields_ = [('code', c.c_ushort), ('jt', c.c_ubyte), ('jf', c.c_ubyte), ('k', c.c_uint)]


class Program(c.Structure):
    _fields_ = [('len', c.c_ushort), ('filter', c.POINTER(Filter))]


def tunnel_state(name):
    import fcntl
    import socket
    import struct

    request = struct.pack('256s', name.encode('ascii'))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
        flags = struct.unpack_from('H', fcntl.ioctl(handle, 0x8913, request), 16)[0]
        hardware_type = struct.unpack_from('H', fcntl.ioctl(handle, 0x8927, request), 16)[0]
        try:
            fcntl.ioctl(handle, 0x8915, request)
            has_ipv4 = True
        except OSError as error:
            if error.errno != errno.EADDRNOTAVAIL:
                raise
            has_ipv4 = False
    ipv6 = Path('/proc/net/if_inet6')
    has_ipv6 = ipv6.exists() and any(
        line.split()[-1] == name for line in ipv6.read_text().splitlines() if line.split())
    return {'up': bool(flags & 1), 'hardware_type': hardware_type,
            'has_ipv4': has_ipv4, 'has_ipv6': has_ipv6}


def deny_network():
    # x86_64 socket/connect/send/receive/bind/listen/accept/socketpair syscalls.
    denied = (41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 53, 288, 299, 307)
    rules = [Filter(0x20, 0, 0, 0)]  # BPF_LD nr
    for number in denied:
        rules += [Filter(0x15, 0, 1, number), Filter(0x06, 0, 0, 0x50000 | errno.EPERM)]
    rules.append(Filter(0x06, 0, 0, 0x7fff0000))
    array = (Filter * len(rules))(*rules)
    program = Program(len(rules), array)
    libc = c.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [c.c_int, c.c_ulong, c.c_void_p, c.c_ulong, c.c_ulong]
    libc.prctl.restype = c.c_int
    code = libc.prctl(38, 1, None, 0, 0)
    require(code == 0, 'enable_no_new_privs', return_code=code, errno=c.get_errno() if code else 0)
    code = libc.prctl(22, 2, c.byref(program), 0, 0)
    filter_errno = c.get_errno() if code else 0
    DIAGNOSTIC['checks']['enable_network_filter'] = {'return_code': code, 'errno': filter_errno}
    if code == 0:
        return 'seccomp'
    require(filter_errno in (errno.EINVAL, errno.ENOSYS), 'network_filter_unsupported', errno=filter_errno)
    # Some NAS kernels lack filter support. Isolate this process only; never
    # change the running HA process, the host interfaces, or global settings.
    original_namespace = os.readlink('/proc/self/ns/net')
    libc.unshare.argtypes = [c.c_int]
    libc.unshare.restype = c.c_int
    code = libc.unshare(0x40000000)  # CLONE_NEWNET
    require(code == 0, 'create_isolated_network_namespace',
            return_code=code, errno=c.get_errno() if code else 0)
    current_namespace = os.readlink('/proc/self/ns/net')
    interfaces = [line.split(':', 1)[0].strip()
                  for line in Path('/proc/net/dev').read_text().splitlines()[2:] if ':' in line]
    route_rows = [line for line in Path('/proc/net/route').read_text().splitlines()[1:] if line.strip()]
    require(current_namespace != original_namespace and set(interfaces) <= {'lo', 'sit0'} and not route_rows,
            'verify_isolated_network_namespace', namespace_changed=current_namespace != original_namespace,
            interfaces=interfaces, ipv4_route_count=len(route_rows))
    if 'sit0' in interfaces:
        status = tunnel_state('sit0')
        require(not status['up'] and status['hardware_type'] == 776
                and not status['has_ipv4'] and not status['has_ipv6'],
                'verify_inactive_default_tunnel', **status)
    return 'empty_network_namespace'


def inspect(library=LIB, expected_hash=EXPECTED, expected_products=None, service_capacity=20):
    machine = platform.machine().lower()
    require(machine in ('x86_64', 'amd64'), 'verify_architecture', machine=machine)
    actual_hash = hashlib.sha256(library.read_bytes()).hexdigest()
    require(actual_hash == expected_hash, 'verify_library', sha256=actual_hash)
    isolation = deny_network()
    # Keep native printf out of the normal HA log. Only the result JSON is saved.
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.close(sink)
    DIAGNOSTIC['stage'] = 'load_library'
    lib = c.CDLL(str(library))
    base = None
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 6 and Path(fields[-1]).resolve() == library.resolve() and int(fields[2], 16) == 0:
            base = int(fields[0].split('-')[0], 16)
            break
    require(base is not None, 'find_library_mapping', found=base is not None)
    active_index = [0]
    type_callback = c.CFUNCTYPE(c.c_int, c.c_char_p)(lambda sn: active_index[0])
    lib.RegHomeAssistantPyCB.argtypes = [c.c_void_p] * 5
    lib.RegHomeAssistantPyCB(None, c.cast(type_callback, c.c_void_p), None, None, None)
    get_info = c.CFUNCTYPE(c.c_int, c.c_char_p, c.c_void_p)(base + 0xe010)
    get_services = c.CFUNCTYPE(c.c_int, c.c_char_p, c.c_void_p, c.POINTER(c.c_uint))(base + 0xe270)
    get_batch = c.CFUNCTYPE(c.c_int, c.c_uint, c.c_void_p, c.c_void_p, c.c_void_p)(base + 0xe460)
    rows = []
    require(service_capacity in (20, 64), 'verify_service_abi', capacity=service_capacity)
    service_size = service_capacity * (32 + 64)
    id_offset = service_capacity * 32
    DIAGNOSTIC['products_completed'] = rows
    for index in range(8):
        active_index[0] = index
        info = c.create_string_buffer(4096)
        services = c.create_string_buffer(service_size)
        count = c.c_uint(0)
        sn = f'LABMETA{index:09d}'.encode()
        DIAGNOSTIC['stage'] = f'query_product_{index}'
        code = get_info(sn, info)
        require(code == 0, f'query_product_{index}', return_code=code)
        DIAGNOSTIC['stage'] = f'query_services_{index}'
        code = get_services(sn, services, c.byref(count))
        require(code == 0, f'query_services_{index}', return_code=code, service_count=count.value)
        require(0 < count.value <= 20, f'verify_service_count_{index}', count=count.value)
        def text(buffer, start, length):
            return buffer.raw[start:start + length].split(b'\0', 1)[0].decode('ascii')
        row = {'index': index, 'product_id': text(info, 40, 5),
               'sub_product_id': text(info, 45, 3), 'model': text(info, 48, 32),
               'device_type': text(info, 80, 4), 'manufacturer': text(info, 84, 4),
               'protocol_type': int.from_bytes(info.raw[344:348], 'little'),
               'service_names': [text(services, n * 32, 32) for n in range(count.value)]}
        expected_pid = (expected_products[index]['product_id'] if expected_products is not None else
                        ['9MTL', '9MU7', '9MTJ', '9MTM', '9MTR', '9MTV', '9MTW', '9MTX'][index])
        require(row['product_id'] == expected_pid, f'verify_product_layout_{index}',
                actual_product_id=row['product_id'], expected_product_id=expected_pid)
        if expected_products is not None:
            if 'service_ids' in expected_products[index]:
                row['service_ids'] = [text(services, id_offset + n * 64, 64) for n in range(count.value)]
            require(row == expected_products[index], f'verify_candidate_product_{index}',
                    actual=row, expected=expected_products[index])
        # Registration uses this batch getter, so check that it returns the same
        # metadata as the standalone getter. No registration function is called.
        batch_info = c.create_string_buffer(4096)
        sn_array = c.create_string_buffer(40)
        sn_array.value = sn
        DIAGNOSTIC['stage'] = f'query_batch_metadata_{index}'
        code = get_batch(1, sn_array, batch_info, None)
        require(code == 0, f'query_batch_metadata_{index}', return_code=code)
        fields_to_check = [('product_id', 40, 5), ('sub_product_id', 45, 3),
                           ('model', 48, 32), ('device_type', 80, 4), ('manufacturer', 84, 4)]
        batch_values = {name: text(batch_info, offset, size) for name, offset, size in fields_to_check}
        batch_values['protocol_type'] = int.from_bytes(batch_info.raw[344:348], 'little')
        require(all(batch_values[name] == row[name] for name in batch_values),
                f'verify_batch_metadata_{index}', actual=batch_values)
        # The SDK also requests service metadata in batches. A null fourth
        # argument misses both the ID offset and the output-record stride.
        serials = c.create_string_buffer(80)
        for record in range(2):
            c.memmove(c.addressof(serials) + record * 40, sn, len(sn))
        pair_info = c.create_string_buffer(2 * 348)
        pair_services = c.create_string_buffer(2 * service_size)
        code = get_batch(2, serials, pair_info, pair_services)
        single_ids = [text(services, id_offset + n * 64, 64) for n in range(count.value)]
        require(code == 0 and all(single_ids), f'verify_service_ids_{index}', ids=single_ids)
        for record in range(2):
            batch_ids = [text(pair_services, record * service_size + id_offset + n * 64, 64)
                         for n in range(count.value)]
            batch_types = [text(pair_services, record * service_size + n * 32, 32)
                           for n in range(count.value)]
            require(batch_ids == single_ids and batch_types == row['service_names'],
                    f'verify_batch_service_abi_{index}_{record}', ids=batch_ids)
        rows.append(row)
    return {'network_isolation': isolation, 'network_denied_by_seccomp': isolation == 'seccomp',
            'sdk_main_called': False,
            'gateway_binding_read': False, 'device_registration_called': False,
            'batch_metadata_verified': True, 'products': rows}



if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--result', required=True)
    parser.add_argument('--nonce', required=True)
    args = parser.parse_args()
    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    root = plan_path.parent.parent
    try:
        baseline = inspect(root / plan['source_relative'], plan['source_sha256'], plan['baseline_metadata'],
                           plan.get('source_service_capacity', 20))
        candidate = inspect(root / plan['candidate_relative'], plan['candidate_sha256'], plan['expected_metadata'],
                            plan.get('candidate_service_capacity', 20))
        unchanged = [i for i in range(8) if baseline['products'][i] == candidate['products'][i]]
        assert unchanged == plan['expected_unchanged_slots']
        result = {**candidate, 'success': True, 'unchanged_slots': unchanged,
                  'candidate_sha256': plan['candidate_sha256'], 'nonce': args.nonce}
    except Exception as error:
        result = {'success': False, 'error_type': type(error).__name__, 'diagnostic': DIAGNOSTIC,
                  'nonce': args.nonce}
    Path(args.result).write_text(json.dumps(result, indent=2), encoding='utf-8')
    raise SystemExit(0 if result['success'] else 1)
