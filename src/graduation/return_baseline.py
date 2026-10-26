"""Bounded past-episode means; this changes gradient weights, never rewards."""
import math


class RunningReturnBaseline:
    """Independent history for each training slot and construction-step index."""

    def __init__(self):
        self._records = {}

    def _check(self, key, returns):
        if type(key) is not str or not 1 <= len(key) <= 128 or not key.strip():
            raise ValueError('Expected a bounded nonempty training key')
        if (type(returns) is not tuple or not 1 <= len(returns) <= 28
                or any(type(value) is not float or not math.isfinite(value) for value in returns)):
            raise ValueError('Returns must be an immutable tuple of1..28 finite floats')
        if key not in self._records:
            if len(self._records) >= 16:
                raise ValueError('Baseline supports at most16 training slots')
            return {'count': 0, 'means': (0.0,)*len(returns)}
        record = self._records[key]
        if len(record['means']) != len(returns):
            raise ValueError('Construction length changed for the training slot')
        return record

    def center(self, key: str, returns: tuple[float, ...]) -> dict:
        """Read PAST means without inserting or updating any history."""
        record = self._check(key, returns)
        advantages = tuple(value - mean for value, mean in zip(returns, record['means']))
        if not all(math.isfinite(value) for value in advantages):
            raise ValueError('Centered gradient weights must remain finite')
        return {'baselines': record['means'], 'advantages': advantages, 'count': record['count']}

    def observe(self, key: str, returns: tuple[float, ...]) -> None:
        """Atomically record original returns after a successful complete update."""
        old = self._check(key, returns)
        if old['count'] >= 64:
            raise ValueError('Baseline supports at most64 completed visits per slot')
        count = old['count'] + 1
        means = tuple(mean*(old['count']/count) + value/count for mean, value in zip(old['means'], returns))
        if not all(math.isfinite(value) for value in means):
            raise ValueError('Baseline means must remain finite')
        self._records[key] = {'count': count, 'means': means}

    def snapshot(self) -> dict:
        return {key: {'count': value['count'], 'means': tuple(value['means'])}
                for key, value in self._records.items()}
