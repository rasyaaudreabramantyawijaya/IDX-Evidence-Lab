"""Export one small local dossier per issuer from the current source bundle."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from idx_evidence_lab.issuer_dossier import build_dossier
from idx_evidence_lab.broker_archive import load_broker_rankings

def main():
    # Refresh this bundle with export_market_overview_static.py before this exporter.
    bundle = json.loads((ROOT/"docs/prototypes/market-overview-data.json").read_text())
    output = ROOT/"docs/prototypes/issuer-dossiers"
    output.mkdir(exist_ok=True)
    counts = {"issuers":0,"analogs":0,"events20":0,"filings":0,"actions":0}
    broker_rankings=load_broker_rankings(ROOT,[row['ticker'] for row in bundle['screener_analysis']['rows']])
    for row in bundle["screener_analysis"]["rows"]:
        dossier = build_dossier(bundle,row["ticker"],ROOT)
        dossier['broker']=broker_rankings[row['ticker']]
        (output/f"{row['ticker']}.json").write_text(json.dumps(dossier,ensure_ascii=False,separators=(",",":")))
        counts["issuers"] += 1
        counts["analogs"] += dossier["analog"]["sample"]
        counts["events20"] += row["sample_20d"]
        counts["filings"] += len(dossier["documents"]["filings"])
        counts["actions"] += len(dossier["documents"]["corporate_actions"])
    print(json.dumps(counts))

if __name__ == "__main__":
    main()
