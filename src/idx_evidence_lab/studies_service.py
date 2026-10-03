"""Offline Studies orchestration. Unsupported domains stay explicitly unavailable."""
import hashlib
import json
import math
from pathlib import Path
from statistics import stdev

from .market_data import load_issuer_daily, load_ihsg_snapshot
from .studies_transforms import transform_series
from .studies_types import StudyRequest, request_fingerprint
from .studies_adapters import execute_domain, verified_flow, add_metric
from .studies_indicators import technical_series
from .studies_verification import verification_for


def run_study(root: Path, request: StudyRequest, *, portfolio_artifact=None) -> dict:
    result = {'widget_id': request.widget_id, 'target': {'kind': request.target_kind,
              'targets': list(request.targets), 'entities': list(request.entities)},
              'status': 'UNSUPPORTED', 'verification': 'NOT_TESTED',
              'formula_version': 'studies-daily-v1', 'period': {'start': None, 'end': None},
              'cutoff': request.cutoff, 'sources': [], 'coverage': {
                  'requested_issuers': len(request.entities), 'usable_issuers': 0},
              'metrics': [], 'series': [], 'tables': [], 'warnings': []}
    if request.widget_id not in ('custom_engineering', 'price_risk', 'trend_momentum', 'liquidity_proxy', 'evidence_trace'):
        result=execute_domain(root,request,result,portfolio_artifact=portfolio_artifact)
    else:
        benchmark = load_ihsg_snapshot(root)
        session_dates = [r['date'] for r in benchmark.get('series', [])] if benchmark.get('data_quality') == 'VERIFIED' else []
        if session_dates:
            for name in benchmark.get('source_files', []):
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    raise ValueError('Invalid calendar source reference')
                result['sources'].append({'id': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        usable = 0
        partial = False
        all_dates = []
        for ticker in request.entities:
            snapshot = load_issuer_daily(root, ticker)
            if not snapshot.get('ok') or snapshot.get('data_quality') != 'VERIFIED':
                result['warnings'].append({'ticker': ticker, 'reason': 'VERIFIED_DAILY_REQUIRED'})
                continue
            rows = [r for r in snapshot['series'] if not request.cutoff or r['date'] <= request.cutoff]
            if not rows:
                result['warnings'].append({'ticker': ticker, 'reason': 'NO_DATA_AT_CUTOFF'})
                continue
            sources = []
            for name in snapshot.get('source_files', []):
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    raise ValueError('Invalid daily source reference')
                sources.append({'id': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            result['sources'].extend(sources)
            if request.widget_id=='liquidity_proxy' or request.widget_id=='custom_engineering' and request.params.get('field')=='volume':
                missing_volume=set()
                for name in snapshot.get('source_files',[]):
                    payload=json.loads((root/name).read_text())
                    if isinstance(payload,list):
                        for raw in payload:
                            if isinstance(raw,dict) and (raw.get('volume') is None or isinstance(raw.get('volume'),bool)):
                                missing_volume.add(raw.get('date'))
                if missing_volume:
                    rows=[{**r,'volume':None} if r['date'] in missing_volume else r for r in rows]
                    result['warnings'].append({'ticker':ticker,'reason':'MISSING_RAW_VOLUME_NOT_ZERO_FILLED'})
            index_dates = [d for d in session_dates if rows[0]['date'] <= d <= rows[-1]['date']]
            issuer_dates = [r['date'] for r in rows]
            calendar = sorted(set(index_dates) | set(issuer_dates))
            if session_dates and set(issuer_dates) - set(session_dates):
                result['warnings'].append({'ticker': ticker, 'reason': 'ISSUER_SESSIONS_ABSENT_FROM_IHSG',
                                           'count': len(set(issuer_dates)-set(session_dates))})
            # An explicit calendar is reported even when only issuer observations exist.
            if not session_dates:
                result['warnings'].append({'ticker': ticker, 'reason': 'OBSERVED_ISSUER_CALENDAR_ONLY'})
            width = len(calendar) if request.window == 'available' else int(request.window)
            display_dates = calendar[-width:]
            all_dates.extend(display_dates)
            usable += 1
            if request.widget_id == 'evidence_trace':
                result['tables'].append({'ticker': ticker, 'source_count': len(sources),
                                         'observations': len(rows), 'calendar_basis': 'IHSG' if session_dates else 'issuer_observed'})
                continue
            rows_by_date={r['date']:r for r in rows}
            aligned_rows = [{**rows_by_date.get(d, {}), 'date':d} for d in calendar]
            indicators=technical_series(aligned_rows,period=14)
            if request.widget_id == 'trend_momentum':
                long=technical_series(aligned_rows,period=26)['ema']
                short=technical_series(aligned_rows,period=12)['ema']
                macd=[a-b if a is not None and b is not None else None for a,b in zip(short,long)]
                for key,values,unit in [('sma14',indicators['sma'],'IDR'),('ema14',indicators['ema'],'IDR'),
                                        ('rsi14',indicators['rsi'],'0–100'),('macd12_26',macd,'IDR')]:
                    points=[{'date':day,'value':value,'reason':None if value is not None else 'WARMUP_OR_GAP'} for day,value in zip(calendar,values)][-width:]
                    result['series'].append({'ticker':ticker,'id':key,'unit':unit,'points':points})
                    partial |= any(p['value'] is None for p in points)
                result['formula_version']='technical-sma-seeded-ema-wilder-rsi-atr-v1'
                if not any(p['value'] is not None for s in result['series'] if s['ticker']==ticker for p in s['points']):
                    usable-=1
                continue
            if request.widget_id == 'liquidity_proxy':
                selected=aligned_rows[-width:]
                values=[r.get('close')*r.get('volume') if r.get('close') is not None and r.get('volume') is not None else None for r in selected]
                result['series'].append({'ticker':ticker,'id':'close_volume_turnover_proxy','unit':'IDR proxy',
                    'points':[{'date':r['date'],'value':v,'reason':None if v is not None else 'MISSING_SESSION'} for r,v in zip(selected,values)]})
                add_metric(result,ticker+'.mean_turnover_proxy',sum(values)/len(values) if values and all(v is not None for v in values) else None,'IDR proxy')
                result['warnings'].append({'ticker':ticker,'reason':'CLOSE_TIMES_VOLUME_PROXY_NOT_ORDER_BOOK_OR_ACTUAL_TRANSACTION_VALUE'})
                partial=True
                if not any(v is not None for v in values): usable-=1
                continue
            if request.widget_id == 'custom_engineering':
                field = request.params.get('field', 'close')
                transform = request.params.get('transform', 'rolling_mean')
                if field == 'foreign_net_flow':
                    flow,flow_sources=verified_flow(root,ticker)
                    result['sources'].extend(flow_sources)
                    rows=[{'date':r['date'],'foreign_net_flow':r['net']} for r in flow['issuer_daily'].get(ticker,[]) if r['date'] in calendar]
                    if flow['data_quality']!='VERIFIED':
                        partial=True
                        result['warnings'].append({'ticker':ticker,'reason':'PARTIAL_FLOW_COVERAGE'})
                transformed = transform_series(rows, field=field, transform=transform,
                                               window=max(2,width) if transform=='rolling_std' else width, calendar=calendar,
                                               expanding=request.window=='available',
                                               unit='shares' if field == 'volume' else 'IDR')
                result['formula_version']=transformed['formula_version']
                points = transformed['series'][-width:]
                if not any(p['value'] is not None for p in points):
                    usable -= 1
                    result['warnings'].append({'ticker': ticker, 'reason': 'NO_COMPUTABLE_TRANSFORM_VALUES'})
                result['series'].append({'ticker': ticker, 'id': transform, 'unit': transformed['unit'],
                                         'points': points, 'formula_version': transformed['formula_version']})
                partial |= any(p['value'] is None for p in points)
                continue
            prices = {r['date']: r['close'] for r in rows}
            closes = [prices.get(d) for d in display_dates]
            returns = [b/a-1 if a is not None and b is not None else None for a,b in zip(closes, closes[1:])]
            metrics = {}
            if len(closes) >= 2 and all(v is not None for v in closes):
                metrics['cumulative_return'] = (closes[-1]/closes[0]-1, 'fraction')
                peak, drawdowns = closes[0], []
                for value in closes:
                    peak = max(peak, value)
                    drawdowns.append(value/peak-1)
                metrics['max_drawdown'] = (min(drawdowns), 'fraction')
                if len(returns) >= 2:
                    metrics['volatility_annualized'] = (stdev(returns)*math.sqrt(252), 'fraction/year^0.5')
            for key in ('cumulative_return', 'max_drawdown', 'volatility_annualized'):
                value, unit = metrics.get(key, (None, 'fraction'))
                result['metrics'].append({'id': ticker+'.'+key, 'value': value, 'unit': unit,
                                          'status': 'READY' if value is not None else 'INSUFFICIENT_DATA',
                                          'reason': None if value is not None else 'ALIGNED_HISTORY_REQUIRED'})
            result['series'].append({'ticker': ticker, 'id': 'close', 'unit': 'IDR',
                                     'points': [{'date': d, 'value': prices.get(d), 'reason': None if d in prices else 'MISSING_SESSION'} for d in display_dates]})
            add_metric(result,ticker+'.downside_deviation_annualized',
                math.sqrt(sum(min(r,0)**2 for r in returns)/len(returns)*252) if returns and all(r is not None for r in returns) else None,'fraction/year^0.5')
            add_metric(result,ticker+'.atr14',indicators['atr'][-1] if indicators['atr'] else None,'IDR','VERIFIED_OHLC_AND_14_SESSION_WARMUP_REQUIRED')
            partial |= any(m['value'] is None for m in result['metrics'] if m['id'].startswith(ticker+'.'))
        result['coverage']['usable_issuers'] = usable
        result['status'] = 'INSUFFICIENT_DATA' if not usable else 'PARTIAL' if partial or usable < len(request.entities) else 'READY'
        if all_dates:
            result['period'] = {'start': min(all_dates), 'end': max(all_dates)}
        result['cutoff'] = request.cutoff or result['period']['end']
    result['request_fingerprint'] = request_fingerprint(request, [s['sha256'] for s in result['sources']],formula_version=result['formula_version'])
    result['verification'],result['verification_scope']=verification_for(root,request.widget_id)
    return result
