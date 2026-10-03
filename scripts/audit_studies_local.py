"""Read-only audit of 16 Studies dispatches across the saved issuer universe.

Run: PYTHONPATH=src python3 scripts/audit_studies_local.py
Coverage/readiness audit only; numerical correctness comes from reference fixtures.
"""
import json
from collections import Counter
from pathlib import Path
from idx_evidence_lab.market_data import load_lq45_universe
from idx_evidence_lab.studies_registry import WIDGETS,parse_study_request
from idx_evidence_lab.studies_service import run_study

ROOT=Path(__file__).resolve().parents[1]
universe=load_lq45_universe(ROOT)
if not universe['ok']: raise ValueError('Local universe unavailable')
print(json.dumps({'universe_quality':universe['data_quality'],'issues':universe['issues']}),flush=True)
tickers=[row['ticker'] for row in universe['symbols']]
for widget in WIDGETS:
    counts=Counter();errors=[]
    for ticker in tickers:
        try:
            request=parse_study_request({'widget_id':widget,'targets':[ticker]},known_tickers=tickers,sectors={})
            result=run_study(ROOT,request)
            counts[result['status']]+=1
            if result['status']=='ERROR': errors.append({'ticker':ticker,'error':'ERROR_STATUS'})
        except Exception as error:
            counts['ERROR']+=1;errors.append({'ticker':ticker,'error':type(error).__name__})
    print(json.dumps({'widget':widget,'issuers':len(tickers),'statuses':dict(counts),'errors':errors}),flush=True)
