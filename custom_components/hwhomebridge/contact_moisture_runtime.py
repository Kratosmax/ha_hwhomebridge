"""Local door/leak adapter; validates native metadata before selecting the DLL."""
import asyncio
from collections import deque
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
import uuid

from . import hwbridge as bridge, thermohygrometer_runtime
from .contact_moisture_conversion import snapshot
from .native_async import submit_native
from .product_registry import ProductDef, ServiceDef, HAMapping, AdapterDef, ModelExactMatch
from .service_router import ServiceRouter
from .virtual_device import SNManager

_LOGGER = logging.getLogger(__name__)
LIBRARY_SHA = 'ea844c3bd54d324f116ca69bf0dc3ed94e3987f3f6946a8cceea32aa5be88de0'
PRODUCTS = {'011': ('isa.magnet.dw2hl', '门窗传感器（113B）', 'doorSensor', 'status', 'door', 2),
            '012': ('lumi.flood.bmcn01', '水浸传感器（2GB5）', 'warterAlarm', 'alarm', 'moisture', 6)}
STATUS = {'phase': 'prepared', 'reporting_enabled': False}
TRACE = deque(maxlen=40)
LAST = {}
REGISTERED = set()
WATER_TRIALS = set()
_INSTALLED = False
_DISABLE_GAS = None


def disable_gas():
    """Undo the optional gas hooks before the SDK starts after failed validation."""
    if _DISABLE_GAS is not None:
        _DISABLE_GAS()


def registration_statuses(pid, registered=False):
    # DEV_ONLINE can overwrite a pending DEV_ADD before SDK dispatch.
    if pid in ('011', '012', '013'):
        return (1,) if registered else (3,)
    return (3, 1)


def registration_devices(devices, pid, target_sn=None):
    selected = [d for d in devices if d.product.pid == pid and d.online]
    if target_sn is not None:
        selected = [d for d in selected if d.sn == target_sn]
        if len(selected) != 1:
            raise ValueError('Selected sensor is unavailable or belongs to another product')
    return selected


def gas_identity_sn(device_id, revision):
    if type(revision) is not int or revision not in (1, 2):
        raise ValueError('Unsupported gas identity version')
    identity = device_id if revision == 1 else device_id + ':2MXG:2'
    return SNManager.generate_sn(identity)


def selected(router, sn):
    device = router.sn_manager.get_by_sn(sn)
    return device if device and device.product.pid in PRODUCTS else None


def readings(hass, device):
    def state(name):
        entity_id = device.get_entity_for_service(name)
        return hass.states.get(entity_id) if entity_id else None
    return snapshot(device.product.pid, state('state'),
                    state('concentration' if device.product.pid == '013' else 'battery'))


def send(router, device):
    if not STATUS['reporting_enabled'] or not bridge.bridge_work:
        return False
    if device.product.pid == '013' and STATUS.get('gas_blocked'):
        return False
    if device.product.pid == '012' and device.sn not in REGISTERED and device.sn not in WATER_TRIALS:
        return False
    values = readings(router._hass, device)
    for sid, value in values.items():
        key = (device.sn, sid)
        previous = LAST.get(key)
        if previous == value:
            continue
        payload = dict(value)
        if sid == 'doorSensor' and previous is not None and previous.get('status') != value['status']:
            payload['event'] = value['status']
        LAST[key] = dict(value)
        TRACE.append({'kind': 'report_submitted', 'time': time.time(), 'product': device.product.pid,
                      'service': sid, 'value': payload})
        future = submit_native(router._lib.UpdateHAStatus, router._c_char_p(device.sn),
                               router._c_char_p(sid), router._c_char_p(json.dumps(payload)))
        def completed(result, pid=device.product.pid, sid=sid, payload=payload, key=key):
            entry = {'kind': 'report_completed', 'time': time.time(), 'product': pid,
                     'service': sid, 'value': payload}
            try:
                entry['sdk_result'] = result.result()
                if entry['sdk_result'] != 0:
                    LAST.pop(key, None)
            except Exception as exc:
                entry['error_type'] = type(exc).__name__
                LAST.pop(key, None)
            TRACE.append(entry)
        future.add_done_callback(completed)
    return bool(values)


def install(hass, settings=None):
    global _INSTALLED, _DISABLE_GAS
    if _INSTALLED:
        return True
    REGISTERED.update((settings or {}).get('sensor_registered_sns', []))
    component = Path(__file__).parent
    library_path = component / 'hilink_bridge/binary_sensors'
    gas_enabled = (settings or {}).get('gas_sensor_enabled', False)
    # The final combined library is validated/selected by socket_runtime.
    # Never restore the obsolete gas candidate that replaced socket slot 0.
    expected_hash = LIBRARY_SHA
    if hashlib.sha256((library_path / 'lib/amd64/libhilink_bridge.so').read_bytes()).hexdigest() != expected_hash:
        return False
    folder = Path(hass.config.path('temp', 'hwhomebridge-contact-moisture'))
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / 'probe-result.json'
    nonce = uuid.uuid4().hex
    try:
        completed = subprocess.run([sys.executable, str(component / 'native_metadata_probe.py'),
            '--plan', str(library_path / 'metadata-plan.json'), '--result', str(result_path),
            '--nonce', nonce], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if completed.returncode or not result.get('success') or result.get('nonce') != nonce or result.get('candidate_sha256') != expected_hash:
            raise RuntimeError('Native metadata probe failed')
    except Exception as exc:
        _LOGGER.error('Door/leak native validation failed (%s); retaining working bridge library', type(exc).__name__)
        return False
    STATUS['native_metadata_verified'] = True
    if gas_enabled:
        PRODUCTS['013'] = ('lumi.sensor_gas.mcn02', '天然气传感器（2MXG）', 'alarm', 'alarm', 'enum', 7)
        STATUS['gas_registered'] = (settings or {}).get('gas_sensor_registered', False)
    def turn_off_gas():
        nonlocal gas_enabled
        gas_enabled = False
        PRODUCTS.pop('013', None)
        STATUS['gas_blocked'] = 'CandidateValidationFailed'
    _DISABLE_GAS = turn_off_gas
    identity_revision = (settings or {}).get('gas_sensor_identity_version', 1)
    STATUS['gas_identity_version'] = identity_revision
    old_device_register = ServiceRouter.register_device
    def register_device(router, device_id, device_name, entity_list, model='', manufacturer='', reuse_sn=None):
        if gas_enabled and model == 'lumi.sensor_gas.mcn02' and identity_revision == 2:
            reuse_sn = gas_identity_sn(device_id, identity_revision)
        return old_device_register(router, device_id, device_name, entity_list,
                                   model=model, manufacturer=manufacturer, reuse_sn=reuse_sn)
    ServiceRouter.register_device = register_device
    bridge.hilink_bridge_path = str(library_path)
    old_index = bridge._get_pid_index
    bridge._get_pid_index = lambda pid: (-1 if gas_enabled and pid == '008' else
        PRODUCTS[pid][5] if pid in PRODUCTS else old_index(pid))
    old_load = ServiceRouter.load_product_registry
    async def load(router, path):
        result = await old_load(router, path)
        replaced = ('003', '007')
        for pid in replaced:
            router.registry._products.pop(pid, None)
        router.registry._adapters[:] = [a for a in router.registry._adapters if a.pid not in replaced]
        for pid, (model, name, sid, char, device_class, _) in PRODUCTS.items():
            product = ProductDef(pid, name)
            product.services['state'] = ServiceDef('state', sid, char, c_service_id=sid)
            mappings = {'state': {'domain': 'binary_sensor', 'device_class': device_class}}
            if pid == '013':
                mappings['state'] = {'domain': 'sensor', 'name_keywords': ['工作状态']}
                product.services['concentration'] = ServiceDef('concentration', 'gasSensor', 'current', c_service_id='gasSensor')
                mappings['concentration'] = {'domain': 'sensor', 'name_keywords': ['天然气浓度']}
            if pid == '012':
                product.services['battery'] = ServiceDef('battery', 'battery', 'level')
                mappings['battery'] = {'domain': 'sensor', 'device_class': 'battery'}
            router.registry._products[pid] = product
            router.registry._adapters.insert(0, AdapterDef(pid,
                match_rules=[ModelExactMatch(model=model)], services=mappings))
        return result
    ServiceRouter.load_product_registry = load
    old_route = ServiceRouter.route_action
    ServiceRouter.route_action = lambda router, sn, payload: False if selected(router, sn) else old_route(router, sn, payload)
    old_query = ServiceRouter.get_char_state
    def query(router, sn, sid):
        device = selected(router, sn)
        if device is None:
            return old_query(router, sn, sid)
        values = readings(router._hass, device)
        value = values if not sid else values.get(sid)
        TRACE.append({'kind': 'sdk_query', 'time': time.time(), 'product': device.product.pid, 'value': values})
        return json.dumps(value) if value else None
    ServiceRouter.get_char_state = query
    old_report = ServiceRouter.report_state
    def report(router, sn, entity_id, entity_state):
        device = selected(router, sn)
        return send(router, device) if device else old_report(router, sn, entity_id, entity_state)
    ServiceRouter.report_state = report
    old_register = ServiceRouter.register_device_to_hilink
    def register(router, sn, status):
        device = router.sn_manager.get_by_sn(sn)
        if gas_enabled and device and device.product.pid == '008':
            return False  # Slot 7 now describes gas; retired breakers stay excluded.
        if device and device.product.pid == '013' and STATUS.get('gas_blocked'):
            return False
        if selected(router, sn) and not STATUS.get('registration_enabled'):
            return True
        if device and device.product.pid == '013':
            TRACE.append({'kind': 'registration_submitted', 'product': '013',
                          'status': status, 'time': time.time()})
            future = submit_native(router._lib.HilinkSyncBrgDevStatus, router._c_char_p(sn), status)
            def completed(result):
                entry = {'kind': 'registration_completed', 'product': '013',
                         'status': status, 'time': time.time()}
                try:
                    entry['sdk_result'] = result.result()
                except Exception as exc:
                    entry['error_type'] = type(exc).__name__
                TRACE.append(entry)
            future.add_done_callback(completed)
            return True
        return old_register(router, sn, status)
    ServiceRouter.register_device_to_hilink = register
    _INSTALLED = True
    return True


async def start(hass):
    from homeassistant.core import SupportsResponse
    router = bridge.service_router
    def devices():
        return [d for d in router.sn_manager.get_all_devices() if d.product.pid in PRODUCTS]
    async def diagnostics(call):
        return {**STATUS, 'trace': list(TRACE), 'devices': [
            {'sn': d.sn, 'product': d.product.pid, 'online': d.online, 'values': readings(hass, d),
             'services': {s: e.entity_id for s, e in d.service_entries.items()}} for d in devices()]}
    hass.services.async_register('hwhomebridge', 'contact_moisture_diagnostics', diagnostics,
                                  supports_response=SupportsResponse.ONLY)
    async def retry_registration(pid, services, target_sn=None):
        from .native_log_probe import NativeLogProbe
        targets = registration_devices(devices(), pid, target_sn)
        folder = Path(hass.config.path('temp', 'hwhomebridge-contact-moisture'))
        probe = NativeLogProbe(folder / ('registration-' + pid + '-' + str(time.time_ns()) + '.jsonl'))
        await hass.async_add_executor_job(probe.start)
        try:
            if pid == '012':
                WATER_TRIALS.update(d.sn for d in targets)
            for device in targets:
                registered = device.sn in REGISTERED if pid in ('011', '012') else STATUS.get('gas_registered', False)
                for status in registration_statuses(pid, registered):
                    router.register_device_to_hilink(device.sn, status)
            await asyncio.sleep(75)
            for device in targets:
                for sid in services:
                    LAST.pop((device.sn, sid), None)
                send(router, device)
            await asyncio.sleep(5)
            return {'native_events': list(probe.events), 'probe_error': probe.error}
        finally:
            if pid == '012':
                WATER_TRIALS.difference_update(d.sn for d in targets)
            await hass.async_add_executor_job(probe.close)
    async def retry_water(call):
        return await retry_registration('012', ('warterAlarm', 'battery'), call.data.get('sn'))
    async def retry_gas(call):
        return await retry_registration('013', ('alarm', 'commonFaultDetection', 'gasSensor'))
    hass.services.async_register('hwhomebridge', 'contact_moisture_retry_gas', retry_gas,
                                  supports_response=SupportsResponse.ONLY)
    hass.services.async_register('hwhomebridge', 'contact_moisture_retry_water', retry_water,
                                  supports_response=SupportsResponse.ONLY)
    deadline = asyncio.get_running_loop().time() + 300
    while not thermohygrometer_runtime.STATUS.get('reporting_enabled'):
        if asyncio.get_running_loop().time() >= deadline:
            STATUS['phase'] = 'gateway_wait_timeout'
            return
        await asyncio.sleep(2)
    from .native_log_probe import NativeLogProbe
    probe = NativeLogProbe(Path(hass.config.path('temp', 'hwhomebridge-contact-moisture')) /
                           ('startup-registration-' + str(time.time_ns()) + '.jsonl'))
    await hass.async_add_executor_job(probe.start)
    try:
        STATUS.update(phase='registering', registration_enabled=True)
        if '013' in PRODUCTS:
            collisions = [d for d in router.sn_manager.get_all_devices()
                          if d.product.pid == '008' and d.sn not in bridge._excluded_device_sns]
            if collisions:
                STATUS['gas_blocked'] = 'SlotInUse'
        for device in devices():
            if device.online:
                if device.product.pid == '012' and device.sn not in REGISTERED:
                    continue
                if device.product.pid == '013' and STATUS.get('gas_blocked'):
                    continue
                registered = device.sn in REGISTERED if device.product.pid in ('011', '012') else STATUS.get('gas_registered', False)
                for status in registration_statuses(device.product.pid, registered):
                    router.register_device_to_hilink(device.sn, status)
        await asyncio.sleep(60)
    finally:
        await hass.async_add_executor_job(probe.close)
        STATUS['startup_native_events'] = list(probe.events)
        STATUS['startup_probe_error'] = probe.error
    STATUS.update(phase='active_awaiting_app_verification', reporting_enabled=True)
    for device in devices():
        if device.online:
            send(router, device)
