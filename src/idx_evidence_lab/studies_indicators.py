"""Trailing SMA, SMA-seeded EMA, Wilder RSI/ATR; gaps restart warmup."""
import math
from statistics import mean


def _number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def technical_series(rows: list[dict], *, period: int = 14) -> dict:
    if type(period) is not int or period < 2:
        raise ValueError('Indicator period must be >=2')
    out={name:[] for name in ('sma','ema','rsi','atr')}
    closes=[]; gains=[]; losses=[]; ranges=[]
    ema=avg_gain=avg_loss=atr=None
    previous=None
    for row in rows:
        close=_number(row.get('close'));high=_number(row.get('high'));low=_number(row.get('low'))
        if close is None or close <= 0:
            closes=[];gains=[];losses=[];ranges=[];ema=avg_gain=avg_loss=atr=previous=None
            for values in out.values(): values.append(None)
            continue
        closes.append(close)
        sma=mean(closes[-period:]) if len(closes)>=period else None
        if ema is None: ema=sma
        else: ema=close*(2/(period+1))+ema*(1-2/(period+1))
        if previous is not None:
            delta=close-previous;gain=max(delta,0);loss=max(-delta,0)
            gains.append(gain);losses.append(loss)
            if avg_gain is None and len(gains)>=period:
                avg_gain=mean(gains[-period:]);avg_loss=mean(losses[-period:])
            elif avg_gain is not None:
                avg_gain=(avg_gain*(period-1)+gain)/period
                avg_loss=(avg_loss*(period-1)+loss)/period
        rsi=None if avg_gain is None else 50 if avg_gain==avg_loss==0 else 100 if avg_loss==0 else 100-100/(1+avg_gain/avg_loss)
        if high is None or low is None or high < max(close, low) or low > close:
            ranges=[];atr=None
        else:
            tr=max(high-low,abs(high-previous),abs(low-previous)) if previous is not None else high-low
            ranges.append(tr)
            if atr is None and len(ranges)>=period: atr=mean(ranges[-period:])
            elif atr is not None: atr=(atr*(period-1)+tr)/period
        out['sma'].append(sma);out['ema'].append(ema);out['rsi'].append(rsi);out['atr'].append(atr)
        previous=close
    return out
