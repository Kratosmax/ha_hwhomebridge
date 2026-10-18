"""2ANJ adapter for the observed HA climate entity. Original products stay intact."""
import asyncio
from collections import deque
import ctypes
import hashlib
import json
import time
from pathlib import Path

from . import hwbridge as bridge
from .aircon_conversion import command, report
from .native_log_probe import NativeLogProbe
from .native_async import submit_callback, submit_native
from .product_registry import ProductDef, ServiceDef, HAMapping, AdapterDef, ModelExactMatch
from .service_router import ServiceRouter
from .virtual_device import SNManager

LAB = None
SETTINGS = {}
_INSTALLED = False
ENTITY = None
MODEL = 'lumi.acpartner.mcn02'
PID = '009'
CANDIDATE_SHA = '7b04a5a732a00ac301c73719f4e8f4caa0ebf0317df8f510a4a930aaa977d404'
STATUS = {'phase': 'prepared', 'actual_cloud_actions': 0, 'test_actions': 0}
PROBE = None
TEMPERATURE_TRACE = deque(maxlen=24)


def snapshot(state):
    if state is None or state.state in ('unknown', 'unavailable'):
        return {}
    fields = [('switch', 'state', 'on'), ('mode', 'state', 'mode'),
              ('fan', 'fan_mode', 'gear')]
    output = {}
    for service, field, characteristic in fields:
        value = report(state, field, characteristic)
        if value is not None:
            output.setdefault(service, {}).update(value)
    value = report(state, 'temperature', 'target')
    if value is not None:
        target = value['target']
        # 2ANJ defines both fields as integer characteristics. As requested,
        # both represent the HA setpoint, never an unrelated room sensor.
        if not isinstance(target, bool) and isinstance(target, (int, float)) and target == int(target):
            output['temperature'] = {'current': int(target), 'target': int(target)}
    return output


def send_temperature(router, sn, value):
    TEMPERATURE_TRACE.append({'kind': 'report_submitted', 'time': time.time(), 'value': dict(value)})
    future = submit_native(router._lib.UpdateHAStatus, router._c_char_p(sn),
                           router._c_char_p('temperature'), router._c_char_p(json.dumps(value)))
    def completed(result):
        entry = {'kind': 'report_completed', 'time': time.time(), 'value': dict(value)}
        try:
            entry['sdk_result'] = result.result()
        except Exception as exc:
            entry['error_type'] = type(exc).__name__
        TEMPERATURE_TRACE.append(entry)
    future.add_done_callback(completed)
    return future


def translate(state, payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected an object')
    if 'sid' in payload:
        sid = payload['sid']
        body = payload.get('data', {k: v for k, v in payload.items() if k != 'sid'})
    else:
        nested = [(k, v) for k, v in payload.items() if k in ('switch', 'mode', 'temperature', 'fan') and isinstance(v, dict)]
        if len(nested) == 1:
            sid, body = nested[0]
        elif len(nested) > 1:
            result = []
            for sid, body in nested:
                result.extend(translate(state, {'sid': sid, 'data': body}))
            return result
        else:
            body = payload
            sid = next((s for key, s in [('on', 'switch'), ('mode', 'mode'), ('target', 'temperature'), ('gear', 'fan')] if key in body), None)
    if state is None or state.state in ('unknown', 'unavailable'):
        raise ValueError('Climate unavailable')
    if sid == 'switch':
        value = body.get('on')
        if type(value) is not int or value not in (0, 1):
            raise ValueError('Invalid switch value')
        return [('turn_on' if value else 'turn_off', {})]
    field = {'mode': 'state', 'temperature': 'temperature', 'fan': 'fan_mode'}.get(sid)
    if field is None:
        raise ValueError('Unsupported service')
    return [command(state, field, body)]


def save():
    temporary = LAB / 'actual-aircon-status.tmp'
    temporary.write_text(json.dumps(STATUS, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(LAB / 'actual-aircon-status.json')


def is_aircon(router, sn):
    device = router.sn_manager.get_by_sn(sn)
    return device is not None and device.product.pid == PID


def install(hass, settings):
    global PROBE, LAB, ENTITY, SETTINGS, _INSTALLED
    if _INSTALLED:
        return True
    SETTINGS = settings
    ENTITY = settings['entity_id']
    LAB = Path(hass.config.path('.storage', 'hwhomebridge', 'aircon'))
    LAB.mkdir(parents=True, exist_ok=True)
    runtime_path = Path(__file__).parent / 'hilink_bridge' / 'aircon'
    candidate = runtime_path / 'lib/amd64/libhilink_bridge.so'
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != CANDIDATE_SHA:
        raise RuntimeError('Candidate version differs')
    bridge.hilink_bridge_path = str(runtime_path)
    old_index = bridge._get_pid_index
    bridge._get_pid_index = lambda pid: 5 if pid == PID else old_index(pid)
    old_generate = SNManager.generate_sn
    # Only the actual climate's device gets a separate product-specific SN.
    from homeassistant.helpers import entity_registry as er
    original_load = ServiceRouter.load_product_registry

    async def load(router, path):
        result = await original_load(router, path)
        product = ProductDef(PID, '空调（2ANJ）')
        for service, char in [('switch', 'on'), ('mode', 'mode'), ('temperature', 'target'), ('fan', 'gear')]:
            product.services[service] = ServiceDef(service, service, char,
                ha_mapping=HAMapping(domain='climate'))
        router.registry._products[PID] = product
        router.registry._adapters.insert(0, AdapterDef(PID,
            match_rules=[ModelExactMatch(model=MODEL)],
            services={s: {'domain': 'climate'} for s in product.services}))
        return result
    ServiceRouter.load_product_registry = load
    original_set = ServiceRouter.set_hass

    def set_hass(router, hass):
        original_set(router, hass)
        entry = er.async_get(hass).async_get(ENTITY)
        if entry is None or not entry.device_id:
            raise RuntimeError('Actual climate entity not registered')
        target_device = entry.device_id
        SNManager.generate_sn = staticmethod(lambda device_id:
            'HBAC' + hashlib.sha256((device_id + ':2ANJ-v2').encode()).hexdigest()[:12]
            if device_id == target_device else old_generate(device_id))
        STATUS['target_device_id'] = target_device
    ServiceRouter.set_hass = set_hass
    original_route = ServiceRouter.route_action

    def route(router, sn, payload):
        if not is_aircon(router, sn):
            return original_route(router, sn, payload)
        try:
            body = json.loads(payload) if isinstance(payload, str) else payload
            operations = translate(router._hass.states.get(ENTITY), body)
        except (ValueError, TypeError, KeyError, AttributeError):
            return False
        async def apply():
            for action, data in operations:
                await router._hass.services.async_call('climate', action,
                    {'entity_id': ENTITY, **data}, blocking=True)
            STATUS['last_control_actions'] = [action for action, _ in operations]
            await router._hass.async_add_executor_job(save)
        router._hass.add_job(apply)
        STATUS['actual_cloud_actions'] += 1
        return True
    ServiceRouter.route_action = route
    original_query = ServiceRouter.get_char_state

    def query(router, sn, sid):
        if not is_aircon(router, sn):
            return original_query(router, sn, sid)
        state = snapshot(router._hass.states.get(ENTITY))
        value = state if not sid else state.get(sid)
        if sid in ('', 'temperature'):
            TEMPERATURE_TRACE.append({'kind': 'sdk_query', 'time': time.time(),
                                      'value': dict(state.get('temperature', {}))})
        return json.dumps(value) if value else None
    ServiceRouter.get_char_state = query
    # ctypes c_char_p callbacks warn/leak when returning Python bytes.
    # Return addresses of buffers whose lifetime is owned by this module.
    buffers = {}
    def char_state(sn, sid):
        value = bridge.OnGetCharStateCB(sn, sid)
        if value is None:
            return None
        key = (sn, sid)
        buffers[key] = ctypes.create_string_buffer(value)
        return ctypes.addressof(buffers[key])
    bridge.pGetCharStateCB = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p)(char_state)
    original_report = ServiceRouter.report_state

    def report_state(router, sn, entity_id, entity_state):
        if not is_aircon(router, sn):
            return original_report(router, sn, entity_id, entity_state)
        if not bridge.bridge_work or not STATUS.get('state_reporting_enabled'):
            return False
        for service, value in snapshot(entity_state).items():
            if service == 'temperature':
                send_temperature(router, sn, value)
            else:
                router._update_hw_bridge_status(sn, service, value)
        return True
    ServiceRouter.report_state = report_state
    original_register = ServiceRouter.register_device_to_hilink
    def register(router, sn, status):
        if is_aircon(router, sn) and not STATUS.get('registration_enabled'):
            # The existing saved HA device would otherwise get status=1 first.
            # A new product-specific SN must begin with status=3 after login.
            STATUS['initial_aircon_registration_deferred'] = True
            return True
        return original_register(router, sn, status)
    ServiceRouter.register_device_to_hilink = register
    old_status = bridge._handle_bridge_status

    def handle_status(value):
        if bridge.lib.HILINK_GetDevStatus() == 9:
            bridge.bridge_work = False
            return
        old_status(value)
    def status(value):
        submit_callback(handle_status, value)
    bridge.pBridgeStatusCB = bridge.BRG_NOTIFYSTATUS_FUNC(status)
    save()
    if settings.get('capture_native_events', False):
        PROBE = NativeLogProbe(LAB / ('native-events-' + str(time.time_ns()) + '.jsonl'))
        PROBE.start()
    else:
        PROBE = DisabledProbe()
    _INSTALLED = True
    return True


class DisabledProbe:
    def __init__(self):
        self.events = []
        self.error = None

    def close(self):
        pass


async def start(hass):
    from homeassistant.core import SupportsResponse

    async def diagnostics(call):
        router = bridge.service_router
        devices = router.sn_manager.get_all_devices()
        climate = next((d for d in devices if d.product.pid == PID), None)
        return {**STATUS, 'gateway_status': bridge.lib.HILINK_GetDevStatus(),
                'temperature_trace': list(TEMPERATURE_TRACE),
                'bridge_device_online': climate.online if climate else None,
                'devices': [{'sn': d.sn, 'product': d.product.pid,
                             'services': {s: e.entity_id for s, e in d.service_entries.items()}}
                            for d in devices],
                'actual_climate_state': snapshot(hass.states.get(ENTITY)),
                'climate_attributes': {k: hass.states.get(ENTITY).attributes.get(k)
                                       for k in ('hvac_modes', 'fan_modes', 'temperature', 'current_temperature', 'min_temp', 'max_temp')},
                'aircon_sn': climate.sn if climate else None}
    hass.services.async_register('hwhomebridge', 'aircon_diagnostics', diagnostics,
                                  supports_response=SupportsResponse.ONLY)

    async def sync_temperature(call):
        router = bridge.service_router
        climate = next((d for d in router.sn_manager.get_all_devices() if d.product.pid == PID), None)
        value = snapshot(hass.states.get(ENTITY)).get('temperature')
        if climate is None or not value or not STATUS.get('state_reporting_enabled'):
            return {'submitted': False}
        future = send_temperature(router, climate.sn, value)
        try:
            result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), 5)
            return {'submitted': True, 'value': value, 'sdk_result': result}
        except TimeoutError:
            return {'submitted': True, 'value': value, 'pending': True}
    hass.services.async_register('hwhomebridge', 'aircon_sync_temperature', sync_temperature,
                                  supports_response=SupportsResponse.ONLY)

    async def idempotent_control_test(call):
        # Test actual routing without turning an appliance on or changing settings.
        state = hass.states.get(ENTITY)
        if state is None or state.state != 'off':
            return {'passed': False, 'reason': 'Idempotent off test requires already-off climate'}
        router = bridge.service_router
        device = next((d for d in router.sn_manager.get_all_devices() if d.product.pid == PID), None)
        if device is None:
            return {'passed': False, 'reason': 'Actual aircon not registered'}
        previous = STATUS['actual_cloud_actions']
        accepted = router.route_action(device.sn, {'switch': {'on': 0}})
        STATUS['actual_cloud_actions'] = previous
        STATUS['test_actions'] += 1
        await asyncio.sleep(2)
        result = {'route_accepted': accepted, 'after_state': hass.states.get(ENTITY).state,
                  'actual_cloud_downlink_tested': False,
                  'ha_control_routing_passed': accepted and hass.states.get(ENTITY).state == 'off'}
        STATUS['control_test'] = result
        await hass.async_add_executor_job(save)
        return result
    hass.services.async_register('hwhomebridge', 'aircon_test_off', idempotent_control_test,
                                  supports_response=SupportsResponse.ONLY)
    deadline = asyncio.get_running_loop().time() + 180
    while not (bridge.start_work and bridge.lib.HILINK_GetDevStatus() == 1):
        if asyncio.get_running_loop().time() > deadline:
            STATUS['phase'] = 'gateway_timeout'
            await hass.async_add_executor_job(save)
            await hass.async_add_executor_job(PROBE.close)
            return
        await asyncio.sleep(2)
    await asyncio.sleep(60)
    router = bridge.service_router
    devices = router.sn_manager.get_all_devices()
    if any(d.product.pid == '006' for d in devices):
        STATUS['phase'] = 'slot5_collision'
        await hass.async_add_executor_job(save)
        await hass.async_add_executor_job(PROBE.close)
        return
    climate = next((d for d in devices if d.product.pid == PID), None)
    if climate is None or set(climate.service_entries) != {'switch', 'mode', 'temperature', 'fan'}:
        STATUS['phase'] = 'actual_climate_mapping_missing'
        await hass.async_add_executor_job(save)
        await hass.async_add_executor_job(PROBE.close)
        return
    probe = PROBE
    try:
        STATUS['phase'] = 'registering_actual_climate'
        STATUS['aircon_sn'] = climate.sn
        STATUS['registration_enabled'] = True
        await hass.async_add_executor_job(save)
        await hass.async_add_executor_job(router.register_device_to_hilink, climate.sn, 3)
        await hass.async_add_executor_job(router.register_device_to_hilink, climate.sn, 1)
        await asyncio.sleep(60)
        STATUS['native_events'] = list(probe.events)
        STATUS['native_probe_error'] = probe.error
        STATUS['state_reporting_enabled'] = True
        STATUS['sdk_add_success_observed'] = any(e['kind'] == 'cloud_add_success_marker' for e in probe.events)
        STATUS['cloud_error_codes'] = [e['value'] for e in probe.events if e['kind'] == 'cloud_error']
        STATUS['phase'] = 'actual_climate_active_awaiting_app_verification'
        for d in devices:
            if d.product.pid == '008':
                await hass.async_add_executor_job(router.register_device_to_hilink, d.sn, 1)
        router.sync_device_state(climate)
        await hass.async_add_executor_job(save)
    finally:
        await hass.async_add_executor_job(probe.close)
        STATUS['native_events'] = list(probe.events)
        STATUS['native_probe_error'] = probe.error
        await hass.async_add_executor_job(save)
