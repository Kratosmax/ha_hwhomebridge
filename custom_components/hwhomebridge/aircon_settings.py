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
    for key in ('enabled', 'capture_native_events'):
        if key in data and type(data[key]) is not bool:
            raise ValueError(f'{key} must be boolean')
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
