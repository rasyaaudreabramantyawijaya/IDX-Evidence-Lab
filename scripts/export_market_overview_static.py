#!/usr/bin/env python3
"""Export locally verified Sectors snapshots for the Live Server prototype."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from idx_evidence_lab.market_data import (  # noqa: E402
    load_ihsg_snapshot,
    load_lq45_index_snapshot,
    load_issuer_daily,
    load_lq45_universe,
    load_sector_heatmap,
)
from idx_evidence_lab.market_overview_analytics import load_foreign_flow, load_valuation_snapshot  # noqa: E402
from idx_evidence_lab.signal_baseline import build_signal_baseline  # noqa: E402
from idx_evidence_lab.screener_analysis import analyze_bundle  # noqa: E402


def build_payload() -> dict[str, object]:
    ihsg = load_ihsg_snapshot(ROOT)
    signal_baseline = build_signal_baseline(ihsg)
    ihsg["series_fingerprint"] = signal_baseline.get("source_fingerprint")
    universe = load_lq45_universe(ROOT)
    symbols = [row["ticker"] for row in universe.get("symbols", [])]
    daily: dict[str, object] = {}
    for symbol in symbols:
        result = load_issuer_daily(ROOT, symbol)
        daily[symbol] = {
            "ok": result["ok"],
            "data_quality": result["data_quality"],
            "coverage_start": result["coverage_start"],
            "coverage_end": result["coverage_end"],
            "series": [
                {"date": row["date"], "close": row["close"], "volume": row["volume"]}
                for row in result["series"]
            ],
        }
    payload = {
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "generated_from_local_snapshots": True,
        "universe": universe,
        "ihsg": ihsg,
        "signal_baseline": signal_baseline,
        "lq45_index": load_lq45_index_snapshot(ROOT),
        "lq45_daily": daily,
        "foreign_flow": load_foreign_flow(ROOT, symbols),
        "valuation_readiness": load_valuation_snapshot(ROOT, symbols),
        "sectorHeatmap": load_sector_heatmap(ROOT),
    }
    payload["screener_analysis"] = analyze_bundle(payload, ROOT)
    return payload


def main() -> int:
    payload = build_payload()
    if not payload["ihsg"]["ok"] or not payload["lq45_index"]["ok"] or not payload["universe"]["ok"]:
        raise SystemExit("IHSG/LQ45 index snapshot or LQ45 universe failed local validation; export stopped.")
    output = ROOT / "docs" / "prototypes" / "market-overview-data.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(payload['lq45_daily'])} LQ45 daily series to {output.relative_to(ROOT)}")
    print(f"IHSG: {payload['ihsg']['observation_count']} observations; {payload['ihsg']['coverage_start']}–{payload['ihsg']['coverage_end']}")
    print(f"LQ45: {payload['lq45_index']['observation_count']} observations; {payload['lq45_index']['coverage_start']}–{payload['lq45_index']['coverage_end']}")
    # Keep per-issuer artifacts in sync with the source fingerprint just exported.
    from export_issuer_dossiers import main as export_dossiers
    export_dossiers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
