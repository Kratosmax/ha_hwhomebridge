"""Opt-in single-socket test card; existing breaker devices keep their identity."""
import asyncio
from collections import deque
from ctypes import string_at, memmove, memset
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from . import hwbridge as bridge, contact_moisture_runtime
from .native_async import submit_native, queue_diagnostics
from .product_registry import ProductDef
from .socket_delay import CountdownStore, decode
from .socket_meter import power, energy_wh, EnergyCounter
from .virtual_device import VirtualDevice, ServiceEntry, SNManager
from .service_router import ServiceRouter

PID = '014'
LIBRARY_SHA = 'afbd689f2b9f10137428a51898cf83dad72de87a51cf9f9c09f493bbc9861a12'
GAS_LIBRARY_SHA = 'a96d53ea538146c4572c5e07d86979cc2b27e7af53c35a50093974c21f829138'
STATUS = {'phase': 'prepared', 'reporting_enabled': False}
TRACE = deque(maxlen=50)
QUERY_TRACE = deque(maxlen=200)
SOURCE_TRACE = deque(maxlen=200)
ENTITY = None
DEVICE = None
STORE = None
LOCK = None
DEVICES = {}
ENTITIES = {}
SELECTIONS = []
REPORT_RESULTS = {}
METERS = {}
ENERGY = None
ENERGY_LOCK = None
PAUSED = set()


def now():
    return datetime.now(timezone.utc)


def binding(sn=None):
    if sn is None or (DEVICE is not None and sn == DEVICE.sn):
        return DEVICE, ENTITY
    return DEVICES.get(sn), ENTITIES.get(sn)


def values(hass, sn=None):
    device, entity = binding(sn)
    state = hass.states.get(entity) if entity else None
    result = {}
    if state and state.state in ('on', 'off'):
        result['switch'] = {'on': int(state.state == 'on')}
    meter = METERS.get(device.sn) if device else None
    if meter and meter.get('power_entity'):
        reading = power(hass.states.get(meter['power_entity']), meter.get('power_scale', '1'))
        if reading is not None:
            result['power'] = reading
    if meter and meter.get('energy_entity'):
        result['consumption'] = {'consumption': 0}
    if STORE is not None and device is not None:
        result.update(STORE.state(device.sn))
        result['timer'] = {'num': 0, 'timer': []}
        result['timerInfo'] = {'num': 0, 'timerInfo': []}
    return result


def report(hass, sn=None, periodic=False, services=None):
    device, entity = binding(sn)
    if device is None:
        return
    if not STATUS['reporting_enabled'] or not bridge.bridge_work or device.sn in PAUSED:
        return
    router = bridge.service_router
    futures = []
    for sid, value in values(hass, device.sn).items():
        if sid not in ('switch', 'delay', 'power'):
            continue
        if services is not None and sid not in services:
            continue
        # State changes and countdown commands always report. Only the idle
        # heartbeat omits delay; failed reports are retried on the next beat.
        if (periodic and sid == 'delay'
                and REPORT_RESULTS.get((device.sn, sid)) == 0):
            continue
        future = submit_native(router._lib.UpdateHAStatus, router._c_char_p(device.sn),
            router._c_char_p(sid), router._c_char_p(json.dumps(value)))
        futures.append(future)
        def complete(result, service=sid, sn=device.sn, payload=value):
            item = {'kind': 'report', 'sn': sn, 'service': service, 'value': payload, 'time': time.time()}
            try:
                item['sdk_result'] = result.result()
                REPORT_RESULTS[(sn, service)] = item['sdk_result']
            except Exception as exc:
                item['error_type'] = type(exc).__name__
            TRACE.append(item)
        future.add_done_callback(complete)
    return futures


def command(payload):
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ValueError('Expected a command object')
    if set(data) == {'switch'}:
        data = data['switch']
    if isinstance(data, dict) and set(data) == {'on'}:
        if type(data['on']) is not int or data['on'] not in (0, 1):
            raise ValueError('Invalid socket switch value')
        return 'switch', bool(data['on'])
    if set(data) == {'action', 'delay'}:
        data = {'delay': data}
    decode(data, now())
    return 'delay', data


async def execute(hass, sn, turn_on):
    device, entity = binding(sn)
    if device is None or not entity:
        raise ValueError('Unknown socket device')
    state = hass.states.get(entity)
    if not state or state.state not in ('on', 'off'):
        raise ValueError('Socket unavailable; action skipped')
    await hass.services.async_call('switch', 'turn_on' if turn_on else 'turn_off',
                                   {'entity_id': entity}, blocking=True)


async def apply(hass, operation, sn=None):
    device, entity = binding(sn)
    if device is None:
        return
    async with LOCK:
        try:
            kind, payload = operation
            if kind == 'switch':
                await execute(hass, device.sn, payload)
            else:
                await hass.async_add_executor_job(STORE.apply, device.sn, payload, now())
            TRACE.append({'kind': 'command_applied', 'sn': device.sn, 'operation': kind, 'time': time.time()})
        except Exception as exc:
            TRACE.append({'kind': 'command_failed', 'error_type': type(exc).__name__, 'time': time.time()})
        report(hass, device.sn)


async def tick(hass, instant):
    async with LOCK:
        try:
            due = (await hass.async_add_executor_job(STORE.take_due, instant)
                   if STORE.tasks else [])
        except Exception as exc:
            TRACE.append({'kind': 'storage_failed', 'error_type': type(exc).__name__})
            return
        for sn, turn_on in due:
            try:
                await execute(hass, sn, turn_on)
                TRACE.append({'kind': 'countdown_executed', 'sn': sn, 'turn_on': turn_on, 'time': time.time()})
            except Exception as exc:
                TRACE.append({'kind': 'countdown_failed', 'error_type': type(exc).__name__})
        for sn, _ in due:
            report(hass, sn)
        if instant.timestamp() - STATUS.get('last_refresh_time', 0) >= 60:
            STATUS['last_refresh_time'] = instant.timestamp()
            for sn in DEVICES:
                report(hass, sn, periodic=True)


async def energy_refresh(hass, selected_sn=None):
    if ENERGY is None or ENERGY_LOCK.locked() or not STATUS['reporting_enabled']:
        return
    async with ENERGY_LOCK:
        router = bridge.service_router
        for sn, meter in METERS.items():
            if selected_sn is not None and sn != selected_sn:
                continue
            if sn in PAUSED or not meter.get('energy_entity'):
                continue
            total = energy_wh(hass.states.get(meter['energy_entity']))
            pending = await hass.async_add_executor_job(ENERGY.pending, sn, total)
            if pending is None:
                continue
            amount, baseline = pending
            future = submit_native(router._lib.UpdateHAStatus, router._c_char_p(sn),
                router._c_char_p('consumption'), router._c_char_p(json.dumps({'consumption': amount})))
            try:
                code = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), 45)
                if code == 0:
                    await hass.async_add_executor_job(ENERGY.acknowledge, sn, baseline)
                TRACE.append({'kind': 'energy_report', 'sn': sn, 'new_wh': amount, 'sdk_result': code})
            except Exception as exc:
                TRACE.append({'kind': 'energy_report_failed', 'sn': sn, 'error_type': type(exc).__name__})


def install(hass, settings):
    global ENTITY, SELECTIONS
    entity = settings.get('socket_test_entity')
    if not isinstance(entity, str) or not entity.startswith('switch.'):
        raise ValueError('Select one socket switch entity')
    selections = settings.get('socket_entities') or [{'entity_id': entity, 'name': '智能插座',
        'registered': settings.get('socket_test_registered', False)}]
    if not isinstance(selections, list) or not selections:
        raise ValueError('Select socket entities')
    entities = [item.get('entity_id') for item in selections]
    if any(not isinstance(e, str) or not e.startswith('switch.') for e in entities) or len(set(entities)) != len(entities):
        raise ValueError('Invalid or duplicate socket entities')
    SELECTIONS = selections
    gas_enabled = settings.get('gas_sensor_enabled', False)
    if gas_enabled:
        retired = {s.get('old_sn') for s in selections if s.get('old_sn')}
        excluded_file = Path(hass.config.path('.storage', 'hwhomebridge', 'config', 'excluded_devices.txt'))
        excluded = set(excluded_file.read_text(encoding='utf-8').splitlines())
        if not retired or len(retired) != len(selections) or not retired <= excluded:
            raise ValueError('Gas slot requires all selected former breakers to be retired')
    expected_hash = GAS_LIBRARY_SHA if gas_enabled else LIBRARY_SHA
    folder = Path(hass.config.path('temp', 'hwhomebridge-native-probe'))
    folder.mkdir(parents=True, exist_ok=True)
    component = Path(__file__).parent
    assets = component / 'hilink_bridge'
    plan_path = assets / ('plans/gas.json' if gas_enabled else 'plans/socket.json')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    library = assets / plan['candidate_relative']
    if plan['candidate_sha256'] != expected_hash or hashlib.sha256(library.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Unverified socket test library')
    # A second fresh isolated probe guards installation, not just the prior report.
    nonce = uuid.uuid4().hex
    output = folder / ('install-result-' + nonce + '.json')
    result = subprocess.run([sys.executable, str(component / 'native_metadata_probe.py'),
        '--plan', str(plan_path), '--result', str(output), '--nonce', nonce],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
    verified = json.loads(output.read_text(encoding='utf-8'))
    if result.returncode or not verified.get('success') or verified.get('nonce') != nonce:
        raise ValueError('Socket native installation probe failed')
    candidate_root = Path(__file__).parent / ('hilink_bridge/gas_test' if gas_enabled else 'hilink_bridge/socket_test')
    if hashlib.sha256((candidate_root / 'lib/amd64/libhilink_bridge.so').read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Socket runtime library differs from isolated candidate')
    ENTITY = entity
    bridge.hilink_bridge_path = str(candidate_root)
    old_index = bridge._get_pid_index
    bridge._get_pid_index = lambda pid: 0 if pid == PID else old_index(pid)
    old_room = bridge.OnGetRoomInfoCB
    def room_info(sn_ptr, room_ptr, name_ptr):
        old_room(sn_ptr, room_ptr, name_ptr)
        if sn_ptr and name_ptr:
            sn = string_at(sn_ptr).decode('utf-8', errors='replace')
            if binding(sn)[0] is not None:
                selection = next(s for s in SELECTIONS if s['entity_id'] == ENTITIES[sn])
                if room_ptr and selection.get('room_name'):
                    raw = selection['room_name'].encode('utf-8')
                    if len(raw) > 39:
                        raise ValueError('Room name exceeds native buffer')
                    memset(room_ptr, 0, 40)
                    memmove(room_ptr, raw, len(raw))
                name = string_at(name_ptr, 64).split(b'\0', 1)[0].decode('utf-8', errors='replace')
                room = string_at(room_ptr, 40).split(b'\0', 1)[0].decode('utf-8', errors='replace') if room_ptr else ''
                TRACE.append({'kind': 'name_supplied', 'sn': sn, 'name': name, 'room': room, 'time': time.time()})
    bridge.pRoomInfoCB = bridge.ROOM_INFO_FUNC(room_info)
    old_query = ServiceRouter.get_char_state
    def query(router, sn, sid):
        if binding(sn)[0] is None:
            return old_query(router, sn, sid)
        result = values(hass, sn)
        item = {'kind': 'sdk_query', 'sn': sn, 'service': sid, 'value': result, 'time': time.time()}
        TRACE.append(item)
        QUERY_TRACE.append(item)
        value = result if not sid else result.get(sid)
        return json.dumps(value) if value is not None else None
    ServiceRouter.get_char_state = query
    old_route = ServiceRouter.route_action
    def route(router, sn, payload):
        if binding(sn)[0] is None:
            return old_route(router, sn, payload)
        if not STATUS['reporting_enabled'] or sn in PAUSED:
            return False
        try:
            operation = command(payload)
        except (ValueError, TypeError):
            TRACE.append({'kind': 'command_rejected', 'time': time.time()})
            return False
        hass.loop.call_soon_threadsafe(lambda: hass.async_create_task(apply(hass, operation, sn)))
        return True
    ServiceRouter.route_action = route
    old_register = ServiceRouter.register_device_to_hilink
    legacy = {s.get('old_sn') for s in SELECTIONS if s.get('old_sn')}
    def register(router, sn, status):
        if sn in legacy and sn in bridge._excluded_device_sns:
            return False
        return old_register(router, sn, status)
    ServiceRouter.register_device_to_hilink = register


async def retire_legacy(hass, requested):
    if not isinstance(requested, list) or any(not isinstance(sn, str) for sn in requested):
        raise ValueError('Expected an explicit list of legacy socket serials')
    allowed = {s['old_sn']: s for s in SELECTIONS if s.get('old_sn')}
    if not set(requested) <= set(allowed):
        raise ValueError('Only selected legacy sockets may be removed')
    router = bridge.service_router
    results = []
    for sn in requested:
        selection = allowed[sn]
        replacement = next((d for d in DEVICES.values()
            if ENTITIES[d.sn] == selection['entity_id']), None)
        original = router.sn_manager.get_by_sn(sn)
        if (not STATUS['reporting_enabled'] or replacement is None or original is None
            or original.product.pid != '008' or sn == replacement.sn
            or original.get_entity_for_service('switch') != selection['entity_id']
            or not replacement.online
            or any(REPORT_RESULTS.get((replacement.sn, sid)) != 0 for sid in ('switch', 'delay'))):
            results.append({'old_sn': sn, 'retired': False, 'reason': 'ReplacementNotReady'})
            continue
        if sn not in bridge._excluded_device_sns:
            await hass.async_add_executor_job(bridge._write_excluded_device_to_file, sn)
            bridge._excluded_device_sns.add(sn)
        future = submit_native(router._lib.HilinkSyncBrgDevStatus, router._c_char_p(sn), 2)
        code = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), 45)
        if code == 0:
            original.online = False
            bridge._remove_bridge_device_entry_async(sn)
        results.append({'old_sn': sn, 'retired': code == 0, 'sdk_result': code})
    return {'results': results}


async def recreate_metadata(hass, requested, confirmed=False):
    """Explicitly authorized cloud-card recreation; never operate HA switches."""
    if confirmed is not True:
        raise ValueError('Cloud-card recreation requires explicit confirmation')
    if not isinstance(requested, list) or not requested or not set(requested) <= set(DEVICES):
        raise ValueError('Only current socket cards may be recreated')
    if not STATUS['reporting_enabled']:
        raise ValueError('Socket bridge not ready')
    async with LOCK:
        if any(STORE.state(sn)['delay']['num'] for sn in requested):
            raise ValueError('A pending countdown must not be lost')
        if any(DEVICES[sn].product.pid != PID for sn in requested):
            raise ValueError('Wrong device type')
        PAUSED.update(requested)
        router = bridge.service_router
        results = []
        async def submit(sn, status):
            future = submit_native(router._lib.HilinkSyncBrgDevStatus, router._c_char_p(sn), status)
            code = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), 45)
            results.append({'sn': sn, 'status': status, 'sdk_result': code})
            if code != 0:
                raise RuntimeError('Cloud-card metadata recreation failed')
        try:
            for sn in requested:
                await submit(sn, 2)
            await asyncio.sleep(10)
            for sn in requested:
                await submit(sn, 3)
                await submit(sn, 1)
            await asyncio.sleep(75)
        finally:
            PAUSED.difference_update(requested)
        for sn in requested:
            report(hass, sn)
        return {'results': results, 'physical_switch_commands': False,
                'metadata_callbacks': [e for e in TRACE if e.get('kind') == 'name_supplied' and e.get('sn') in requested]}


async def start(hass, settings):
    global DEVICE, STORE, LOCK, ENERGY, ENERGY_LOCK
    from homeassistant.core import SupportsResponse
    from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
    from .native_log_probe import NativeLogProbe
    router = bridge.service_router
    async def diagnostics(call):
        return {**STATUS, 'native_queue': queue_diagnostics(),
                'trace': list(TRACE), 'query_trace': list(QUERY_TRACE),
                'source_trace': list(SOURCE_TRACE), 'values': values(hass),
                'sn': DEVICE.sn if DEVICE else None, 'entity_id': ENTITY,
                'devices': [{'sn': d.sn, 'entity_id': ENTITIES[d.sn], 'name': d.product.name,
                    'online': d.online, 'values': values(hass, d.sn),
                    'report_results': {sid: REPORT_RESULTS.get((d.sn, sid)) for sid in ('switch', 'delay', 'power')
                        if sid != 'power' or METERS[d.sn].get('power_entity')}}
                    for d in DEVICES.values()]}
    hass.services.async_register('hwhomebridge', 'socket_test_diagnostics', diagnostics,
                                 supports_response=SupportsResponse.ONLY)
    async def refresh(call):
        if not STATUS['reporting_enabled']:
            return {'refreshed': False, 'reason': 'SocketsNotReady'}
        futures = []
        for sn in DEVICES:
            futures.extend(report(hass, sn) or [])
        results = await asyncio.gather(*(asyncio.wrap_future(f) for f in futures), return_exceptions=True)
        await energy_refresh(hass)
        return {'refreshed': True, 'sdk_results': [r if isinstance(r, int) else type(r).__name__ for r in results],
                'values': {sn: values(hass, sn) for sn in DEVICES}}
    hass.services.async_register('hwhomebridge', 'socket_refresh_state', refresh,
                                 supports_response=SupportsResponse.ONLY)
    async def retire(call):
        return await retire_legacy(hass, call.data.get('old_sns', []))
    hass.services.async_register('hwhomebridge', 'socket_retire_legacy', retire,
                                 supports_response=SupportsResponse.ONLY)
    async def recreate(call):
        return await recreate_metadata(hass, call.data.get('sns', []), call.data.get('confirm_recreate', False))
    hass.services.async_register('hwhomebridge', 'socket_recreate_metadata', recreate,
                                 supports_response=SupportsResponse.ONLY)
    deadline = asyncio.get_running_loop().time() + 420
    while not contact_moisture_runtime.STATUS.get('reporting_enabled'):
        if asyncio.get_running_loop().time() > deadline:
            STATUS['phase'] = 'existing_devices_wait_timeout'
            return
        await asyncio.sleep(2)
    if any(d.product.pid == '001' for d in router.sn_manager.get_all_devices()):
        STATUS['phase'] = 'slot0_collision'
        return
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    entries = hass.config_entries.async_entries('hwhomebridge')
    entry_id = entries[0].entry_id if entries else None
    store = await hass.async_add_executor_job(CountdownStore,
        hass.config.path('temp', 'hwhomebridge-socket', 'countdowns.json'), now())
    for selection in SELECTIONS:
        entity = selection['entity_id']
        state = hass.states.get(entity)
        if not state or state.state not in ('on', 'off'):
            TRACE.append({'kind': 'socket_skipped_unavailable', 'entity_id': entity})
            continue
        identity = 'hwhomebridge-socket-test:' + entity
        name = selection.get('name') or '智能插座'
        device = VirtualDevice(sn=SNManager.generate_sn(identity), product=ProductDef(PID, name),
                               ha_device_id=identity)
        device.add_service_entry('switch', ServiceEntry(entity_id=entity, domain='switch', service_name='switch'))
        device.online = True
        if not router.sn_manager.register(device):
            raise ValueError('Socket SN conflict')
        DEVICES[device.sn], ENTITIES[device.sn] = device, entity
        METERS[device.sn] = selection
        bridge._create_bridge_device_entry_async(device, name, '124U', 'HA Bridge')
        if entry_id:
            registered = registry.async_get_device(identifiers={('hwhomebridge', entry_id, device.sn)})
            original_entity = entity_registry.async_get(entity)
            original_device = registry.devices.get(original_entity.device_id) if original_entity else None
            area_id = (original_entity.area_id if original_entity else None) or (original_device.area_id if original_device else None)
            if registered:
                registry.async_update_device(registered.id, name_by_user=name, area_id=area_id)
    if not DEVICES:
        STATUS['phase'] = 'all_sockets_unavailable'
        return
    DEVICE = next(iter(DEVICES.values()))
    STORE, LOCK = store, asyncio.Lock()
    ENERGY = await hass.async_add_executor_job(EnergyCounter,
        hass.config.path('temp', 'hwhomebridge-socket', 'energy-baselines.json'))
    ENERGY_LOCK = asyncio.Lock()
    folder = Path(hass.config.path('temp', 'hwhomebridge-native-probe'))
    probe = NativeLogProbe(folder / ('socket-registration-' + str(time.time_ns()) + '.jsonl'))
    await hass.async_add_executor_job(probe.start)
    try:
        STATUS['phase'] = 'registering'
        for device in DEVICES.values():
            selection = next(s for s in SELECTIONS if s['entity_id'] == ENTITIES[device.sn])
            if not selection.get('registered', False):
                router.register_device_to_hilink(device.sn, 3)
            router.register_device_to_hilink(device.sn, 1)
        await asyncio.sleep(75)
    finally:
        await hass.async_add_executor_job(probe.close)
        STATUS['native_events'] = list(probe.events)
        STATUS['probe_error'] = probe.error
    STATUS.update(phase='active_awaiting_app_verification', reporting_enabled=True,
                  last_refresh_time=time.time())
    async def on_time(instant):
        await tick(hass, instant)
    async def on_state(event):
        old, new = event.data.get('old_state'), event.data.get('new_state')
        if old is not None and new is not None and old.state == new.state:
            return
        SOURCE_TRACE.append({'kind': 'source_state', 'entity_id': event.data['entity_id'],
            'old': old.state if old else None, 'new': new.state if new else None, 'time': time.time()})
        for device in DEVICES.values():
            meter = METERS[device.sn]
            if event.data['entity_id'] not in (ENTITIES[device.sn], meter.get('power_entity'), meter.get('energy_entity')):
                continue
            state = hass.states.get(ENTITIES[device.sn])
            online = bool(state and state.state in ('on', 'off'))
            if device.online != online:
                device.online = online
                router.register_device_to_hilink(device.sn, int(online))
            changed = event.data['entity_id']
            if changed == ENTITIES[device.sn]:
                report(hass, device.sn, services={'switch'})
            if changed == meter.get('power_entity'):
                report(hass, device.sn, services={'power'})
            if changed == meter.get('energy_entity'):
                await energy_refresh(hass, device.sn)
    async def on_energy_time(instant):
        await energy_refresh(hass)
    tracked_entities = set(ENTITIES.values()) | {v[k] for v in METERS.values()
        for k in ('power_entity', 'energy_entity') if v.get(k)}
    runtime_data = hass.data.setdefault('hwhomebridge', {})
    for unsubscribe in runtime_data.pop('socket_test_listeners', []):
        unsubscribe()
    runtime_data['socket_test_listeners'] = [
        async_track_time_interval(hass, on_time, timedelta(seconds=1)),
        async_track_time_interval(hass, on_energy_time, timedelta(seconds=60)),
        async_track_state_change_event(hass, list(tracked_entities), on_state)]
    for sn in DEVICES:
        report(hass, sn)
    await energy_refresh(hass)
