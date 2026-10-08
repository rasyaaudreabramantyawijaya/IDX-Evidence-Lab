"""Closed Studies capabilities; no arbitrary code or client-defined membership."""
from datetime import date
import math
import re

from .studies_types import StudyRequest

WIDGETS = ('price_risk', 'trend_momentum', 'liquidity_proxy', 'portfolio_risk',
           'quality_valuation', 'fragility', 'issuer_flow', 'event_timeline',
           'market_context', 'market_breadth', 'capm_benchmark', 'factor_exposure',
           'issuer_compare', 'event_outcomes', 'custom_engineering', 'evidence_trace')
FIELDS = ('close', 'volume', 'foreign_net_flow')
TRANSFORMS = ('difference', 'pct_change', 'rolling_mean', 'rolling_std', 'robust_z')


def catalog() -> list[dict]:
    return [{'id': widget, 'verification': 'NOT_TESTED'} for widget in WIDGETS]


def parse_study_request(payload: dict, *, known_tickers: list[str],
                        sectors: dict[str, list[str]]) -> StudyRequest:
    allowed = {'widget_id', 'target_kind', 'targets', 'window', 'params', 'cutoff', 'portfolio_artifact_ref'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('Unknown Studies request fields')
    widget = payload.get('widget_id')
    if widget not in WIDGETS:
        raise ValueError('Unknown Studies widget')
    kind = payload.get('target_kind', 'issuer')
    targets = payload.get('targets', [])
    if kind not in ('issuer', 'sector', 'universe') or not isinstance(targets, list):
        raise ValueError('Invalid target kind or targets')
    if any(not isinstance(t, str) or not t.strip() for t in targets) or len(targets) > 45:
        raise ValueError('Invalid targets')
    known = set(known_tickers)
    if kind == 'issuer':
        targets = sorted(set(t.strip().upper() for t in targets))
        if not targets or not set(targets) <= known:
            raise ValueError('Issuer target missing or unknown')
        entities = targets
    elif kind == 'sector':
        if len(targets) != 1 or targets[0] not in sectors:
            raise ValueError('One known sector is required')
        entities = sorted(set(sectors[targets[0]]))
        if not set(entities) <= known or not entities or len(entities) > 45:
            raise ValueError('Invalid server sector membership')
    else:
        if targets:
            raise ValueError('Universe cannot specify issuer targets')
        entities = sorted(known)
        if not entities or len(entities) > 45:
            raise ValueError('Invalid universe')
    window = payload.get('window', '20')
    if not isinstance(window, str) or window not in ('5', '20', '60', 'available'):
        raise ValueError('Unsupported window')
    params = payload.get('params', {})
    keys = {'field', 'transform'} if widget == 'custom_engineering' else {'risk_free_annual'} if widget in ('portfolio_risk', 'capm_benchmark') else set()
    if not isinstance(params, dict) or set(params) - keys:
        raise ValueError('Unknown widget parameters')
    params = dict(params)
    if widget == 'custom_engineering':
        params.setdefault('field', 'close')
        params.setdefault('transform', 'rolling_std')
        if params['field'] not in FIELDS or params['transform'] not in TRANSFORMS:
            raise ValueError('Unsupported field or transform')
        if params['field'] == 'foreign_net_flow' and params['transform'] == 'pct_change':
            raise ValueError('Percent change is not applicable to signed flow')
    if 'risk_free_annual' in params:
        value = params['risk_free_annual']
        if type(value) not in (int, float) or not math.isfinite(value) or not -1 < value <= 1:
            raise ValueError('Invalid annual risk-free assumption')
    cutoff = payload.get('cutoff')
    if cutoff is not None:
        if not isinstance(cutoff, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', cutoff):
            raise ValueError('Cutoff must be ISO date')
        date.fromisoformat(cutoff)
    ref = payload.get('portfolio_artifact_ref')
    if ref is not None and (widget not in ('portfolio_risk', 'capm_benchmark', 'factor_exposure') or
                            not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ref)):
        raise ValueError('Invalid portfolio artifact reference')
    return StudyRequest(widget, kind, tuple(targets), tuple(entities), window, params, cutoff, ref)
