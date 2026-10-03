"""Read-only domain adapters using existing verified local analytics."""
import hashlib
import json
import math
from statistics import mean
from pathlib import Path

from .market_data import _read_snapshot, load_issuer_daily, load_ihsg_snapshot, load_news_universe
from .market_overview_analytics import load_foreign_flow
from .issuer_dossier import documents
from .screener_analysis import analyze_issuer, VERSION as EVENT_VERSION
from .portfolio_factors import _artifact_fingerprint, _source_fingerprint
from .studies_indicators import technical_series


def source(root, name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Invalid source reference')
    return {'id': name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def add_metric(result, key, value, unit='fraction', reason=None):
    if type(value) not in (int,float) or not math.isfinite(value): value=None
    result['metrics'].append({'id':key,'value':value,'unit':unit,
        'status':'READY' if value is not None else 'INSUFFICIENT_DATA',
        'reason':None if value is not None else reason or 'REQUIRED_INPUT_UNAVAILABLE'})


def summarize_events(data):
    excluded=data.get('excluded',{})
    return {'detected':data.get('event_count',0), 'mature_5d':data.get('sample_5d',0),
            'mature_20d':data.get('sample_20d',0), 'immature_5d':excluded.get('immature_5d',0),
            'immature_20d':excluded.get('immature_20d',0), 'overlap':excluded.get('overlapping_events',0),
            'invalid_5d':excluded.get('invalid_5d',0), 'invalid_20d':excluded.get('invalid_20d',0)}


def verified_flow(root, ticker):
    data=load_foreign_flow(root,[ticker])
    sources=[]
    for path in sorted((root/f'data/raw/sectors/foreign_flow/{ticker}').glob('*.json')):
        if path.name.endswith('.metadata.json'): continue
        _,meta,issues=_read_snapshot(path,root)
        if not issues and meta.get('ticker')==ticker and f'/foreign-flow/{ticker}/' in meta.get('endpoint',''):
            sources.append(source(root,path.relative_to(root).as_posix()))
    return data,sources


def finish(result):
    has_output=bool(result['tables'] or any(m['value'] is not None for m in result['metrics']) or
                    any(p['value'] is not None for s in result['series'] for p in s['points']))
    missing=any(m['value'] is None for m in result['metrics'])
    incomplete=result['coverage']['usable_issuers']<result['coverage']['requested_issuers']
    result['status']='INSUFFICIENT_DATA' if not has_output else 'PARTIAL' if missing or incomplete or result['warnings'] else 'READY'
    result['sources']=list({s['id']:s for s in result['sources']}.values())
    return result


def execute_domain(root, request, result, *, portfolio_artifact=None):
    widget=request.widget_id
    if widget in ('portfolio_risk','capm_benchmark'):
        if not portfolio_artifact:
            result['warnings'].append({'reason':'MATCHING_PORTFOLIO_ARTIFACT_REQUIRED'})
            return finish(result)
        selection=portfolio_artifact.get('selection',{})
        source_rows=portfolio_artifact.get('studies_sources',[])
        end=selection.get('sample_end')
        matches=(set(selection.get('tickers',[]))==set(request.entities) and
                 (not request.cutoff or end==request.cutoff) and source_rows and
                 all(source(root,s['id'])['sha256']==s['sha256'] for s in source_rows))
        rate=portfolio_artifact.get('metrics',{}).get('assumptions',{}).get('risk_free_annual')
        if 'risk_free_annual' in request.params and request.params['risk_free_annual'] != rate: matches=False
        if request.window!='available' and portfolio_artifact.get('metrics',{}).get('sample_count')!=int(request.window): matches=False
        if not matches:
            result['status']='STALE';result['warnings'].append({'reason':'PORTFOLIO_ARTIFACT_MISMATCH'})
            return result
        result['sources']=source_rows
        result['period']={'start':selection.get('sample_start'),'end':end};result['cutoff']=end
        metrics=portfolio_artifact.get('metrics',{}) if widget=='portfolio_risk' else portfolio_artifact.get('historical_capm',{})
        names=('sharpe','sortino','calmar','max_drawdown') if widget=='portfolio_risk' else ('beta','capm_hurdle','capm_alpha')
        for name in names:
            value=metrics.get(name)
            add_metric(result,name,value.get('value') if isinstance(value,dict) else value,
                       'ratio' if name in ('sharpe','sortino','calmar','beta') else 'fraction')
            if isinstance(value,dict):
                result['metrics'][-1]['status']=value.get('status',result['metrics'][-1]['status'])
                result['metrics'][-1]['reason']=value.get('reason')
        if widget=='portfolio_risk':
            result['series']=[{'id':'drawdown','ticker':'PORTFOLIO','unit':'fraction','points':[
                {'date':p['date'],'value':p['drawdown'],'reason':None} for p in metrics.get('path',[])]}]
        result['tables'].append({'scope':'Existing Portfolio Lab artifact; weights unchanged',**selection,
            'weights':portfolio_artifact.get('allocation',{}).get('weights'),
            'assumptions':metrics.get('assumptions') if widget=='portfolio_risk' else
                {k:metrics.get(k) for k in ('risk_free_annual','market_premium_annual','market_return_arithmetic_annual','source')},
            'metrics_scope':portfolio_artifact.get('metrics_scope') if widget=='portfolio_risk' else 'ALIGNED_HISTORICAL_BENCHMARK_MANUAL_RF',
            'sample_count':metrics.get('sample_count'), 'benchmark':selection.get('benchmark')})
        result['coverage']['usable_issuers']=len(request.entities)
        return finish(result)
    if widget in ('quality_valuation','fragility','factor_exposure','issuer_compare'):
        path=root/'docs/prototypes/portfolio-factor-zoo-data.json'
        if not path.is_file():
            result['warnings'].append({'reason':'VERIFIED_FACTOR_ARTIFACT_REQUIRED'});return finish(result)
        factor=json.loads(path.read_text())
        files=factor.get('sources',{}).get('files',[])
        safe=bool(files) and all((root/f).resolve().is_relative_to(root.resolve()) and (root/f).is_file() for f in files)
        if not safe or factor.get('artifact_fingerprint')!=_artifact_fingerprint(factor) or factor.get('sources',{}).get('sha256')!=_source_fingerprint(root,files):
            result['warnings'].append({'reason':'FACTOR_ARTIFACT_STALE_OR_INVALID'});return finish(result)
        selected=[r for r in factor.get('records',[]) if r['ticker'] in request.entities]
        if request.cutoff:
            # Report price-as-of is not publication/availability time. Current-only until point-in-time inputs exist.
            result['warnings'].append({'reason':'SNAPSHOT_AFTER_CUTOFF'});return finish(result)
        result['sources']=[source(root,f) for f in files]+[source(root,path.relative_to(root).as_posix())]
        result['formula_version']=factor['formula_version']
        result['period']={'start':factor['as_of'].get('price'),'end':factor['as_of'].get('price')}
        result['cutoff']=result['period']['end']
        result['warnings'].append({'reason':'CURRENT_REPORT_SNAPSHOT_PUBLICATION_TIME_UNVERIFIED'})
        groups={r.get('peer_group') for r in selected}
        years={tuple(str(r.get('financial_ratio_years',{}).get(k)) for k in ('roe','debt_to_equity')) for r in selected}
        if widget=='issuer_compare' and (len(groups)>1 or len(years)>1):
            result['warnings'].append({'reason':'NONCOMPARABLE_PEER_GROUPS' if len(groups)>1 else 'NONCOMPARABLE_FISCAL_YEARS'})
        for row in selected:
            ticker=row['ticker'];result['coverage']['usable_issuers']+=1
            result['tables'].append({'ticker':ticker,'sector':row.get('sector'),'peer_group':row.get('peer_group'),
                                     'report_as_of':row.get('report_as_of'),'financial_years':row.get('financial_ratio_years',{})})
            fields=('debt_to_equity','roe') if widget=='fragility' else ('earnings_yield','dividend_yield','roe','debt_to_equity')
            if widget=='factor_exposure':
                for name,score in row.get('scores',{}).items():
                    add_metric(result,ticker+'.'+name,score.get('score'),'z-score',score.get('status'))
                result['warnings'].append({'ticker':ticker,'reason':'DESCRIPTIVE_CHARACTERISTICS_NOT_RETURN_FACTORS'})
            else:
                for name in fields:
                    if widget=='issuer_compare' and name in ('roe','debt_to_equity'):
                        field_years={r.get('financial_ratio_years',{}).get(name) for r in selected}
                        reason='NONCOMPARABLE_PEER_GROUPS' if len(groups)>1 else 'NONCOMPARABLE_FISCAL_YEAR' if len(field_years)>1 else 'FISCAL_YEAR_UNAVAILABLE' if None in field_years else None
                        if reason:
                            add_metric(result,ticker+'.'+name,None,'ratio' if name=='debt_to_equity' else 'fraction',reason)
                            continue
                    component=row.get('components',{}).get(name,{})
                    add_metric(result,ticker+'.'+name,component.get('value'),'ratio' if name=='debt_to_equity' else 'fraction',component.get('reason'))
                if widget=='fragility':
                    report_path=root/f'data/raw/sectors/company_report/{ticker}/company_report.json'
                    report,meta,issues=_read_snapshot(report_path,root)
                    annual=(report or {}).get('financials',{}).get('historical_financials',[]) if not issues else []
                    for record in annual:
                        if isinstance(record,dict):
                            result['tables'].append({'ticker':ticker,'year':record.get('year'),
                                **{k:record.get(k) for k in ('operating_cash_flow','revenue','net_income','total_debt','cash')}})
        if widget=='issuer_compare':
            # Price comparison is aligned independently of incomparable report ratios.
            maps={}
            for ticker in request.entities:
                daily=load_issuer_daily(root,ticker)
                maps[ticker]={r['date']:r['close'] for r in daily.get('series',[])
                              if not request.cutoff or r['date']<=request.cutoff} if daily.get('data_quality')=='VERIFIED' else {}
            common=sorted(set.intersection(*(set(m) for m in maps.values()))) if maps else []
            common=common if request.window=='available' else common[-int(request.window):]
            if len(common)>1:
                for ticker,prices in maps.items():
                    add_metric(result,ticker+'.common_period_return',prices[common[-1]]/prices[common[0]]-1)
                result['tables'].append({'common_price_start':common[0],'common_price_end':common[-1],'aligned_observations':len(common)})
                result['period']={'start':common[0],'end':common[-1]}
        return finish(result)
    benchmark=load_ihsg_snapshot(root)
    market=[r for r in benchmark.get('series',[]) if not request.cutoff or r['date']<=request.cutoff] if benchmark.get('data_quality')=='VERIFIED' else []
    result['sources']=[source(root,f) for f in benchmark.get('source_files',[])] if market else []
    if market:
        result['period']={'start':market[0]['date'],'end':market[-1]['date']};result['cutoff']=request.cutoff or market[-1]['date']
    if widget=='market_context':
        rows=[{'date':r['date'],'close':r['price']} for r in market]
        width=len(rows) if request.window=='available' else int(request.window)
        for period in (50,200):
            values=technical_series(rows,period=period)['sma']
            add_metric(result,f'IHSG.sma{period}',values[-1] if values else None,'index_points')
        add_metric(result,'IHSG.close',market[-1]['price'] if market else None,'index_points')
        result['series']=[{'id':'IHSG','ticker':'IHSG','unit':'index_points','points':[
            {'date':r['date'],'value':r['price'],'reason':None} for r in market[-width:]]}]
        result['tables'].append({'scope':'Technical descriptive context, not validated regime forecast'})
        result['coverage']['usable_issuers']=len(request.entities) if market else 0
        return finish(result)
    if widget=='market_breadth':
        counts={'advancers':0,'decliners':0,'unchanged':0,'above_sma20':0,'above_sma50':0};valid=0;ma_valid={20:0,50:0}
        for ticker in request.entities:
            daily=load_issuer_daily(root,ticker)
            if daily.get('data_quality')!='VERIFIED' or len(market)<2: continue
            prices={r['date']:r['close'] for r in daily['series']}
            a,b=market[-2]['date'],market[-1]['date']
            if a not in prices or b not in prices: continue
            result['sources'].extend(source(root,f) for f in daily['source_files']);valid+=1
            counts['advancers' if prices[b]>prices[a] else 'decliners' if prices[b]<prices[a] else 'unchanged']+=1
            for period in (20,50):
                sample=[prices.get(r['date']) for r in market[-period:]]
                if len(sample)==period and all(x is not None for x in sample):
                    ma_valid[period]+=1;counts[f'above_sma{period}']+=prices[b]>mean(sample)
        result['coverage']['usable_issuers']=valid
        for name,count in counts.items(): add_metric(result,name,count,'issuers')
        result['tables'].append({'target_count':len(request.entities),'valid_price_pairs':valid,
                                'valid_sma20':ma_valid[20],'valid_sma50':ma_valid[50], 'membership':'current snapshot, not historical'})
        if valid/len(request.entities)<.7:
            result['metrics']=[];result['status']='INSUFFICIENT_DATA';result['warnings'].append({'reason':'COVERAGE_BELOW_70_PERCENT'});return result
        if valid<len(request.entities) or min(ma_valid.values())<valid: result['warnings'].append({'reason':'PARTIAL_BREADTH_COVERAGE'})
        return finish(result)
    news=load_news_universe(root) if widget=='event_timeline' else {}
    for ticker in request.entities:
        daily=load_issuer_daily(root,ticker)
        rows=[r for r in daily.get('series',[]) if not request.cutoff or r['date']<=request.cutoff]
        if daily.get('data_quality')!='VERIFIED': rows=[]
        result['sources'].extend(source(root,f) for f in daily.get('source_files',[]) if rows)
        if widget=='event_timeline':
            width=len(market) if request.window=='available' else int(request.window)
            timeline_start=market[-width]['date'] if len(market)>=width and width else market[0]['date'] if market else None
            effective_cutoff=request.cutoff or result['cutoff']
            result['period']['start']=timeline_start
            docs=documents(root,ticker)
            result['sources'].extend({'id':s['file'],'sha256':s['sha256']} for s in docs['sources'])
            for kind in ('filings','corporate_actions','suspensions'):
                for item in docs[kind]:
                    day=str(item.get('timestamp') or item.get('ex_date') or item.get('agm_date') or '')[:10]
                    if not day or effective_cutoff and day>effective_cutoff or timeline_start and day<timeline_start: continue
                    result['tables'].append({'ticker':ticker,'kind':kind,'date':day or None,'title':item.get('title') or item.get('type') or kind})
            for article in news.get('articles',[]):
                if ticker not in article.get('symbols',[]): continue
                day=article.get('timestamp','')[:10]
                if not day or effective_cutoff and day>effective_cutoff or timeline_start and day<timeline_start: continue
                result['tables'].append({'ticker':ticker,'kind':'news','date':day,'title':article.get('title')})
                name=article.get('source_file')
                if name: result['sources'].append(source(root,name))
            result['coverage']['usable_issuers']+=1
            if docs['issues']: result['warnings'].append({'ticker':ticker,'reason':'PARTIAL_DOCUMENT_COVERAGE'})
            continue
        flow,sources=verified_flow(root,ticker);result['sources'].extend(sources)
        flows=[r for r in flow['issuer_daily'].get(ticker,[]) if not request.cutoff or r['date']<=request.cutoff]
        if not flows or not rows or not market:
            result['warnings'].append({'ticker':ticker,'reason':'ALIGNED_FLOW_PRICE_IHSG_REQUIRED'});continue
        event_start=None
        if widget=='event_outcomes':
            width=len(market) if request.window=='available' else min(int(request.window),len(market))
            event_start=market[-width]['date']
            result['period']['start']=event_start
        data=analyze_issuer(ticker,rows,flows,market,event_start=event_start)
        result['coverage']['usable_issuers']+=1;result['formula_version']=EVENT_VERSION+('-cohort-window-v1' if widget=='event_outcomes' else '')
        if widget=='issuer_flow':
            width=len(flows) if request.window=='available' else int(request.window)
            result['series'].append({'id':'foreign_net_flow','ticker':ticker,'unit':'IDR','points':[
                {'date':r['date'],'value':r['net'],'reason':None} for r in flows[-width:]]})
            add_metric(result,ticker+'.flow_strength_z20',data['flow_strength_z20'],'z-score')
            result['warnings'].append({'ticker':ticker,'reason':'BROKER_PROVENANCE_PARTIAL_FOREIGN_FLOW_ONLY'})
        else:
            result['tables'].append({'ticker':ticker,**summarize_events(data)})
            for name in ('outcome_5d','outcome_20d','baseline_delta_20d','hit_rate'):
                add_metric(result,ticker+'.'+name,data[name])
            for name in ('mae','mfe'):
                add_metric(result,ticker+'.'+name,None,reason='EXCURSION_FORMULA_NOT_REFERENCE_VERIFIED')
            for event in data['events']:
                result['tables'].append({'ticker':ticker,**event})
            result['warnings'].append({'ticker':ticker,'reason':'DESCRIPTIVE_EVENT_SAMPLE_NOT_FORECAST'})
    return finish(result)
