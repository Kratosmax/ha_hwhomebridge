"""Read-only 113B door and 2BE7 leak states, checked against their H5 cards."""
import math


def snapshot(pid, state, battery=None):
    if pid == '013':
        return gas_snapshot(state, battery)
    result = {}
    if state is not None and state.state in ('on', 'off'):
        value = 1 if state.state == 'on' else 0
        if pid == '011':
            result['doorSensor'] = {'status': value}
        elif pid == '012':
            result['warterAlarm'] = {'alarm': value}
    if pid == '012' and battery is not None:
        try:
            value = float(battery.state)
            if math.isfinite(value) and 0 <= value <= 100:
                result['battery'] = {'level': int(value + 0.5)}
        except (TypeError, ValueError):
            pass
    return result


def gas_snapshot(status, concentration):
    if status is None or status.state in ('unknown', 'unavailable', ''):
        return {}
    state = status.state
    if state == '监测正常':
        result = {'alarm': {'alarm': 0}, 'commonFaultDetection': {'status': 0, 'code': 0}}
    elif state == '天然气泄漏报警':
        result = {'alarm': {'alarm': 1}, 'commonFaultDetection': {'status': 0, 'code': 0}}
    elif state in ('设备故障', '传感器寿命到期'):
        return {'commonFaultDetection': {'status': 1, 'code': 2 if state == '传感器寿命到期' else 1}}
    elif state == '自检':
        return {'selfCheck': {'on': 1}}
    else:
        # Preheating and unrecognised states do not mean safe/no gas.
        return {}
    if concentration is not None:
        try:
            value = float(concentration.state)
            if math.isfinite(value) and 0 <= value <= 100:
                result['gasSensor'] = {'current': int(value + 0.5),
                    'level': 1 if value <= 8 else (2 if value <= 15 else 3)}
        except (ValueError, TypeError):
            pass
    return result
