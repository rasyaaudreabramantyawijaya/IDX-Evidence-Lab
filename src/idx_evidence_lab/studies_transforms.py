"""Trailing transforms on an explicit session calendar; never bridge gaps."""
from datetime import date
import math
from statistics import mean, median, stdev

from .studies_registry import FIELDS, TRANSFORMS


def transform_series(rows: list[dict], *, field: str, transform: str, window: int,
                     calendar: list[str], unit: str, expanding: bool = False) -> dict:
    if field not in FIELDS or transform not in TRANSFORMS:
        raise ValueError('Unsupported field or transform')
    if type(window) is not int or window < 1 or (transform == 'rolling_std' and window < 2):
        raise ValueError('Invalid rolling window')
    if transform == 'pct_change' and field == 'foreign_net_flow':
        raise ValueError('Percent change is not applicable to signed flow')
    if calendar != sorted(set(calendar)):
        raise ValueError('Calendar must be unique and chronological')
    for day in calendar:
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError('Calendar must use ISO dates')
    days = [row['date'] for row in rows]
    if days != sorted(set(days)) or not set(days) <= set(calendar):
        raise ValueError('Rows must be unique, chronological and within calendar')
    values = {}
    for row in rows:
        value = row.get(field)
        if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
            raise ValueError('Non-finite or non-numeric input')
        values[row['date']] = value
    series = []
    width = 2 if transform in ('difference', 'pct_change') else window
    for index, day in enumerate(calendar):
        value, reason = None, None
        effective_width=index+1 if expanding and transform not in ('difference','pct_change') else width
        trailing = [values.get(d) for d in calendar[max(0, index-effective_width+1):index+1]]
        if len(trailing) < effective_width or transform=='rolling_std' and len(trailing)<2:
            reason = 'WARMUP'
        elif any(v is None for v in trailing):
            reason = 'MISSING_WINDOW'
        elif transform == 'difference':
            value = trailing[-1] - trailing[-2]
        elif transform == 'pct_change':
            if trailing[-2] <= 0 or trailing[-1] <= 0:
                reason = 'NONPOSITIVE_BASE'
            else:
                value = trailing[-1] / trailing[-2] - 1
        elif transform == 'rolling_mean':
            value = mean(trailing)
        elif transform == 'rolling_std':
            value = stdev(trailing)
        else:
            center = median(trailing)
            mad = median(abs(v-center) for v in trailing)
            if mad == 0:
                reason = 'ZERO_MAD'
            else:
                value = (trailing[-1]-center) / (1.4826*mad)
        if value is not None and not math.isfinite(value):
            value, reason = None, 'NONFINITE_RESULT'
        series.append({'date': day, 'value': value, 'reason': reason})
    valid = sum(row['value'] is not None for row in series)
    return {'series': series, 'unit': 'fraction' if transform == 'pct_change' else
            'dimensionless' if transform == 'robust_z' else unit,
            'formula_version': 'custom-trailing-v1-ddof1', 'window': 'expanding' if expanding else width,
            'coverage': {'valid': valid, 'total': len(series)},
            'status': 'INSUFFICIENT_DATA' if not valid else 'PARTIAL' if valid < len(series) else 'READY'}
