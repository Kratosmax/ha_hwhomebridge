"""Local-only climate selection; never store deployment identities in source."""
import json
import logging
import platform
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
SUPPORTED_MODEL = 'lumi.acpartner.mcn02'


def load_settings(path):
    source = Path(path)
    if not source.exists():
        return {}
    data = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('hwhomebridge_local.json must contain an object')
    entity_id = data.get('entity_id')
    if entity_id is not None and (not isinstance(entity_id, str) or not entity_id.startswith('climate.')):
        raise ValueError('entity_id must select a climate entity')
    for key in ('enabled', 'capture_native_events', 'thermohygrometer_enabled', 'contact_moisture_enabled', 'gas_sensor_enabled', 'gas_sensor_registered', 'socket_test_enabled', 'socket_test_registered'):
        if key in data and type(data[key]) is not bool:
            raise ValueError(f'{key} must be boolean')
    revision = data.get('gas_sensor_identity_version', 1)
    if type(revision) is not int or revision not in (1, 2):
        raise ValueError('gas_sensor_identity_version must be 1 or 2')
    registered = data.get('sensor_registered_sns', [])
    if (not isinstance(registered, list) or any(not isinstance(sn, str) or not sn or len(sn)>39 for sn in registered)
            or len(set(registered)) != len(registered)):
        raise ValueError('sensor_registered_sns must contain distinct sensor serials')
    return data


def resolve_entity(hass, settings):
    if not settings.get('enabled', True):
        return None
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        _LOGGER.info('Air conditioner extension requires amd64; standard bridge retained')
        return None
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    candidates = []
    for entity in entities.entities.values():
        if not entity.entity_id.startswith('climate.') or entity.disabled_by:
            continue
        device = devices.devices.get(entity.device_id)
        if device and device.model == SUPPORTED_MODEL:
            candidates.append(entity.entity_id)
    selected = settings.get('entity_id')
    if selected:
        if selected not in candidates:
            _LOGGER.warning('Configured climate is unavailable or unsupported; standard bridge retained')
            return None
        return selected
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        _LOGGER.warning('Multiple supported climates; select entity_id in local settings')
    return None
