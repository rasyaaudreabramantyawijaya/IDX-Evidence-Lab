"""Read-only artifact context. Never rebuild analytics to conceal missing results."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .research_types import EvidencePack, MetricRecord


def _read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _sources_valid(root, sources):
    if not sources:
        return False
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get('file'), str):
            return False
        path = (root / source['file']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != source.get('sha256'):
            return False
    return True


def load_research_metrics(root: Path, plan, artifact_refs):
    allowed = {'market:current', 'factor-zoo:current', *('issuer:' + t for t in plan.context.entities)}
    if any(not isinstance(ref, str) or ref not in allowed for ref in artifact_refs):
        raise ValueError('UNKNOWN_ARTIFACT_REF')
    metrics = []
    market = _read(root / 'docs/prototypes/market-overview-data.json')
    if 'market' in plan.categories or 'market:current' in artifact_refs:
        from ..market.market_data import _read_snapshot
        ihsg = market.get('ihsg', {})
        source_files = ihsg.get('source_files', [])
        observations, valid = {}, bool(source_files) and ihsg.get('data_quality') == 'VERIFIED'
        for name in source_files:
            path = (root / name).resolve() if isinstance(name, str) else root.resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                valid = False
                break
            payload, _metadata, issues = _read_snapshot(path, root)
            if issues or not isinstance(payload, list):
                valid = False
                break
            for row in payload:
                if isinstance(row, dict) and row.get('index_code', '').upper() == 'IHSG':
                    observations[row.get('date')] = {'date': row.get('date'), 'price': row.get('price'), 'index_code': 'IHSG'}
        series = ihsg.get('series', [])
        if valid and series and all(observations.get(row.get('date')) == row for row in series):
            latest = series[-1].get('price')
            if isinstance(latest, (int, float)) and not isinstance(latest, bool) and math.isfinite(latest) and latest == ihsg.get('latest_price'):
                metrics.append(MetricRecord('M:IHSG:latest_price', 'IHSG latest_price', latest, 'index_points', [],
                    {'start': series[0]['date'], 'end': series[-1]['date']}, source_files, 'market:current',
                    'source-observation-v1', 'VERIFIED_OBSERVATION', claim_kind='observation',
                    limits=['Snapshot indeks lokal, bukan harga live atau target masa depan.']))
    for ticker in plan.context.entities:
        data = _read(root / f'docs/prototypes/issuer-dossiers/{ticker}.json')
        if data.get('ticker') != ticker or data.get('analysis', {}).get('data_quality') != 'VERIFIED':
            continue
        if not data.get('source_fingerprint') or data['source_fingerprint'] != market.get('screener_analysis', {}).get('source_fingerprint'):
            continue
        sources = data.get('documents', {}).get('sources', [])
        if not _sources_valid(root, sources):
            continue
        summary = data.get('summary', {})
        period = {'start': summary.get('price_start'), 'end': summary.get('price_end')}
        fields = {}
        if 'price_risk' in plan.categories:
            fields.update(volatility='fraction/year', max_drawdown='fraction', return_20d='fraction', close='IDR/share')
        if 'flow' in plan.categories:
            fields.update(net_5d='IDR', net_20d='IDR')
        for name, unit in fields.items():
            value = summary.get(name)
            if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value):
                metrics.append(MetricRecord('M:' + ticker + ':' + name, name, value, unit, [ticker], period,
                    [s['file'] for s in sources], 'issuer:' + ticker, data['version'], 'DESCRIPTIVE',
                    limits=[data.get('method', {}).get('limits', 'Raw price adjustment and historical membership may be unverified.')]))
    if set(plan.categories) & {'valuation', 'fundamental', 'price_risk'}:
        factor = _read(root / 'docs/prototypes/portfolio-factor-zoo-data.json')
        if factor:
            from ..portfolio.portfolio_factors import _artifact_fingerprint, _source_fingerprint
            source_files = factor.get('sources', {}).get('files', [])
            safe_files = all(isinstance(f, str) and (root / f).resolve().is_relative_to(root.resolve()) and (root / f).is_file() for f in source_files)
            if safe_files and source_files and factor.get('artifact_fingerprint') == _artifact_fingerprint(factor) and factor.get('sources', {}).get('sha256') == _source_fingerprint(root, source_files):
                names = {'valuation': ['earnings_yield', 'dividend_yield'], 'fundamental': ['roe', 'debt_to_equity'], 'price_risk': ['beta_ihsg', 'idiosyncratic_volatility']}
                for row in factor.get('records', []):
                    if row.get('ticker') not in plan.context.entities:
                        continue
                    for category in plan.categories:
                        for name in names.get(category, []):
                            component = row.get('components', {}).get(name, {})
                            value = component.get('value')
                            if component.get('status') != 'AVAILABLE' or not isinstance(value, (int, float)) or not math.isfinite(value):
                                continue
                            unit = 'fraction/day' if name == 'idiosyncratic_volatility' else 'ratio' if name in {'beta_ihsg', 'debt_to_equity'} else 'fraction'
                            metrics.append(MetricRecord('F:' + row['ticker'] + ':' + name, name, value, unit, [row['ticker']],
                                {'price_end': factor.get('as_of', {}).get('price'), 'report_date': row.get('report_as_of'), 'fiscal_year': row.get('financial_ratio_years', {}).get(name)},
                                source_files, 'factor-zoo:current', factor['formula_version'], 'DESCRIPTIVE', limits=['Sector comparability required; descriptive characteristic, not intrinsic valuation or calibrated forecast.']))
    return metrics


def build_evidence_pack(items, metrics):
    bounded_items = deepcopy(items[:16])
    truncated = len(items) > 16 or len(metrics) > 40
    for item in bounded_items:
        if len(item.excerpt) > 1200:
            truncated = True
            item.excerpt = item.excerpt[:1200]
    bounded_metrics = deepcopy(metrics[:40])
    periods = {json.dumps(m.period, sort_keys=True) for m in bounded_metrics}
    missing = [] if items or metrics else ['Belum ada bukti lokal relevan.']
    if len(periods) > 1:
        missing.append('periode_tidak_selaras')
    coverage = {'categories': sorted({i.category for i in bounded_items}), 'source_dates': sorted({i.source_date for i in bounded_items if i.source_date}),
                'unknown_source_dates': sum(i.source_date is None for i in bounded_items), 'truncated': truncated}
    pack = EvidencePack(bounded_items, bounded_metrics, coverage, missing, truncated)
    # Include both public and local-only evidence in the total bound, never silently overflow.
    while len(json.dumps(pack.to_dict(), ensure_ascii=False).encode()) > 48 * 1024 and (pack.items or pack.metrics):
        if pack.metrics and any(i.source_class == 'user_owned_research' for i in pack.items):
            pack.metrics.pop()
        elif pack.items:
            pack.items.pop()
        else:
            pack.metrics.pop()
        pack.truncated = pack.coverage['truncated'] = True
    pack.coverage.update(categories=sorted({i.category for i in pack.items}),
                         source_dates=sorted({i.source_date for i in pack.items if i.source_date}),
                         unknown_source_dates=sum(i.source_date is None for i in pack.items))
    return pack


def public_model_context(pack):
    public = deepcopy(pack.to_dict())
    public['items'] = [i for i in public['items'] if i['access_class'] == 'public']
    public['private_evidence_omitted'] = any(i.access_class != 'public' for i in pack.items)
    return public
