"""Offline 2ANJ conversion candidate, checked against its public product profile."""
import math

MODE_TO_HA = {1: 'cool', 2: 'heat', 3: 'fan_only', 4: 'dry'}
# 2ANJ's published profile contains gears 2, 3, 4 only.
FAN_TO_HA = {2: '低', 3: '中', 4: '高'}


def command(state, field, payload):
    if state is None or state.state in ('unknown', 'unavailable'):
        raise ValueError('air conditioner is unavailable')
    if field == 'temperature':
        value = payload.get('target')
        if isinstance(value, bool):
            raise ValueError('invalid temperature')
        value = float(value)
        low = max(16, state.attributes.get('min_temp', 16))
        high = min(32, state.attributes.get('max_temp', 32))
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('temperature outside device range')
        step = state.attributes.get('target_temp_step', 1)
        if abs((value - low) / step - round((value - low) / step)) > 1e-6:
            raise ValueError('temperature does not match device step')
        return 'set_temperature', {'temperature': value}
    if field == 'fan_mode':
        value = FAN_TO_HA.get(payload.get('gear'))
        if value not in state.attributes.get('fan_modes', []):
            raise ValueError('unsupported fan gear')
        return 'set_fan_mode', {'fan_mode': value}
    if field == 'state':
        value = MODE_TO_HA.get(payload.get('mode'))
        if value not in state.attributes.get('hvac_modes', []):
            raise ValueError('unsupported HVAC mode')
        return 'set_hvac_mode', {'hvac_mode': value}
    raise ValueError('unsupported climate field')


def report(state, field, char_name):
    if state is None or state.state in ('unknown', 'unavailable', ''):
        return None
    if char_name == 'on':
        return {'on': 0 if state.state == 'off' else 1}
    if field == 'state':
        value = next((k for k, v in MODE_TO_HA.items() if v == state.state), None)
    elif field == 'fan_mode':
        value = next((k for k, v in FAN_TO_HA.items() if v == state.attributes.get(field)), None)
    else:
        value = state.attributes.get(field)
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return None
    return {char_name: value}
