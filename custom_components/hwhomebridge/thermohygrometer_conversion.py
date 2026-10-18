"""113D H5 displays integer wire values divided by 100."""
import math


def measurement(state, low, high):
    if state is None or state.state in ('unknown', 'unavailable', ''):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or not low <= value <= high:
        return None
    scaled = value * 100
    return math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)


def snapshot(temperature, humidity):
    result = {}
    for name, state, low, high in [('temperature', temperature, -20, 100),
                                    ('humidity', humidity, 0, 100)]:
        value = measurement(state, low, high)
        if value is not None:
            result[name] = value
    return {'airDetector': result} if result else {}
