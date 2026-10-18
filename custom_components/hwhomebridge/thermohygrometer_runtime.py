"""Local opt-in 113D thermohygrometer bridge on an unused native slot."""
import asyncio
from collections import deque
import hashlib
import json
from pathlib import Path
import time

from . import aircon_runtime, hwbridge as bridge
from .native_async import submit_native
from .product_registry import ProductDef, ServiceDef, HAMapping, AdapterDef, ModelExactMatch
from .service_router import ServiceRouter
from .thermohygrometer_conversion import snapshot

PID = '010'
MODEL = 'miaomiaoce.sensor_ht.t2'
LIBRARY_SHA = 'd8401ae4db1307a7e5e3b7b1c3b4af0316eccc6b23643ffa83ee28b0816dcb58'
STATUS = {'phase': 'prepared', 'reporting_enabled': False}
TRACE = deque(maxlen=24)
_DEFERRED_NEW = set()
_INSTALLED = False


def selected(router, sn):
    device = router.sn_manager.get_by_sn(sn)
    return device if device and device.product.pid == PID else None


def readings(hass, device):
    def state(name):
        entity_id = device.get_entity_for_service(name)
        return hass.states.get(entity_id) if entity_id else None
    return snapshot(state('temperature'), state('humidity'))


def send(router, device):
    values = readings(router._hass, device)
    if not STATUS['reporting_enabled'] or not values or not bridge.bridge_work:
        return False
    payload = values['airDetector']
    TRACE.append({'kind': 'report_submitted', 'time': time.time(), 'value': payload})
    future = submit_native(router._lib.UpdateHAStatus, router._c_char_p(device.sn),
                           router._c_char_p('airDetector'), router._c_char_p(json.dumps(payload)))
    def completed(result):
        entry = {'kind': 'report_completed', 'time': time.time(), 'value': payload}
        try:
            entry['sdk_result'] = result.result()
        except Exception as exc:
            entry['error_type'] = type(exc).__name__
        TRACE.append(entry)
    future.add_done_callback(completed)
    return True


def install(hass):
    global _INSTALLED
    if _INSTALLED:
        return
    library_path = Path(__file__).parent / 'hilink_bridge' / 'sensors'
    library = library_path / 'lib/amd64/libhilink_bridge.so'
    if hashlib.sha256(library.read_bytes()).hexdigest() != LIBRARY_SHA:
        raise RuntimeError('Thermohygrometer library checksum differs')
    # The candidate keeps the working aircon and seven baseline slots intact.
    # Slot3 replaces the unused pressure product; never map pressure to 113D.
    bridge.hilink_bridge_path = str(library_path)
    old_index = bridge._get_pid_index
    bridge._get_pid_index = lambda pid: 3 if pid == PID else old_index(pid)
    old_load = ServiceRouter.load_product_registry

    async def load(router, path):
        result = await old_load(router, path)
        router.registry._products.pop('004', None)
        router.registry._adapters[:] = [a for a in router.registry._adapters if a.pid != '004']
        product = ProductDef(PID, '温湿度计（113D）')
        for name in ('temperature', 'humidity'):
            product.services[name] = ServiceDef(name, 'airDetector', name,
                c_service_id='airDetector', value_type='int',
                ha_mapping=HAMapping(domain='sensor', device_class=name))
        router.registry._products[PID] = product
        router.registry._adapters.insert(0, AdapterDef(PID,
            match_rules=[ModelExactMatch(model=MODEL)],
            services={name: {'domain': 'sensor', 'device_class': name}
                      for name in ('temperature', 'humidity')}))
        return result
    ServiceRouter.load_product_registry = load
    old_route = ServiceRouter.route_action
    def route(router, sn, payload):
        return False if selected(router, sn) else old_route(router, sn, payload)
    ServiceRouter.route_action = route
    old_query = ServiceRouter.get_char_state
    def query(router, sn, sid):
        device = selected(router, sn)
        if device is None:
            return old_query(router, sn, sid)
        values = readings(router._hass, device)
        value = values if not sid else values.get(sid)
        TRACE.append({'kind': 'sdk_query', 'time': time.time(), 'value': values})
        return json.dumps(value) if value else None
    ServiceRouter.get_char_state = query
    old_report = ServiceRouter.report_state
    def report(router, sn, entity_id, entity_state):
        device = selected(router, sn)
        return send(router, device) if device else old_report(router, sn, entity_id, entity_state)
    ServiceRouter.report_state = report
    old_register = ServiceRouter.register_device_to_hilink
    def register(router, sn, status):
        if selected(router, sn) and not STATUS.get('registration_enabled'):
            if status == 3:
                _DEFERRED_NEW.add(sn)
            return True
        return old_register(router, sn, status)
    ServiceRouter.register_device_to_hilink = register
    _INSTALLED = True


async def start(hass):
    from homeassistant.core import SupportsResponse
    router = bridge.service_router
    def devices():
        return [d for d in router.sn_manager.get_all_devices() if d.product.pid == PID]
    async def diagnostics(call):
        return {**STATUS, 'trace': list(TRACE),
                'devices': [{'sn': d.sn, 'online': d.online, 'values': readings(hass, d),
                             'services': {s: e.entity_id for s, e in d.service_entries.items()}}
                            for d in devices()]}
    hass.services.async_register('hwhomebridge', 'thermohygrometer_diagnostics', diagnostics,
                                  supports_response=SupportsResponse.ONLY)
    deadline = asyncio.get_running_loop().time() + 240
    while not aircon_runtime.STATUS.get('state_reporting_enabled'):
        if asyncio.get_running_loop().time() >= deadline:
            STATUS['phase'] = 'gateway_wait_timeout'
            return
        await asyncio.sleep(2)
    if not devices():
        STATUS['phase'] = 'no_matching_sensor'
        return
    STATUS.update(phase='registering', registration_enabled=True)
    for device in devices():
        if not device.online:
            continue
        if device.sn in _DEFERRED_NEW:
            router.register_device_to_hilink(device.sn, 3)
            _DEFERRED_NEW.discard(device.sn)
            TRACE.append({'kind': 'startup_registration', 'status': 3, 'time': time.time()})
        router.register_device_to_hilink(device.sn, 1)
        TRACE.append({'kind': 'startup_registration', 'status': 1, 'time': time.time()})
    await asyncio.sleep(60)
    STATUS.update(phase='active_awaiting_app_verification', reporting_enabled=True)
    for device in devices():
        if device.online:
            send(router, device)
