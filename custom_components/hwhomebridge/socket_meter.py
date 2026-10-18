"""124U power units and durable increments from HA total-increasing energy."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import tempfile


def number(state):
    if state is None:
        return None
    try:
        value = Decimal(str(state.state))
        return value if value.is_finite() and value >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def power(state, scale='1'):
    value = number(state)
    if value is None:
        return None
    watts = value * Decimal(str(scale))
    if watts > 6000:
        return None
    # The 124U profile and card use integer W, not centiwatts.
    return {'current': int(watts.quantize(Decimal('1'), rounding=ROUND_HALF_UP))}


def energy_wh(state):
    value = number(state)
    if value is None:
        return None
    attrs = state.attributes
    if attrs.get('state_class') != 'total_increasing':
        return None
    scale = {'kWh': 1000, 'Wh': 1}.get(attrs.get('unit_of_measurement'))
    if scale is None:
        return None
    return int((value * scale).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class EnergyCounter:
    """Report only new Wh; initial historic totals are not invented as today's usage."""

    def __init__(self, path):
        self.path = Path(path)
        self.baselines = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if not isinstance(self.baselines, dict) or any(type(v) is not int or v < 0 for v in self.baselines.values()):
            raise ValueError('Invalid energy baselines')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, staged = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.baselines, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, self.path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)

    def pending(self, sn, total):
        if total is None:
            return None
        previous = self.baselines.get(sn)
        if previous is None:
            self.baselines[sn] = total
            self.save()
            return (0, total)
        # HA total_increasing defines a decrease as a counter reset.
        base = 0 if total < previous else previous
        amount = min(total - base, 1000)
        return (amount, base + amount) if amount > 0 else None

    def acknowledge(self, sn, baseline):
        before = dict(self.baselines)
        self.baselines[sn] = baseline
        try:
            self.save()
        except Exception:
            self.baselines = before
            raise
