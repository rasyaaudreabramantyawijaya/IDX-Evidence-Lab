"""Offline foreign-flow event study; descriptive, not a fitted trading model.

All horizons follow the official IHSG session calendar. Entry is the next
session's close, not the close used to observe foreign flow. No network I/O.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

VERSION = "foreign-net-buy-z20-v1"
METHOD = {
    "flow_strength": "Z20 = (net asing hari t − mean net 20 sesi IHSG sebelumnya) / population std sebelumnya; bertanda, bukan skor broker.",
    "event": "Event tetap: net asing > 0 dan Z20 >= 2. Semua saham memakai aturan sama, tidak dituning pada outcome. Bukan analog dari flow terbaru yang negatif.",
    "timing": "Event diamati sesudah close t; entry close t+1; exit close t+1+H, H=5 atau 20 sesi IHSG. Availability intraday provider tidak diketahui; tidak mengklaim live execution.",
    "overlap": "Event berikutnya harus setelah exit 20D event terdahulu (jarak >21 sesi). Cooldown ditetapkan saat event, terlepas dari outcome/maturity.",
    "sample": "Sample ditampilkan n5/n20: event non-overlap dengan seluruh sesi harga tersedia, volume positif, dan benchmark tanggal identik; event belum matang tidak masuk denominator.",
    "outcomes": "5D/20D = rata-rata simple price return saham dari entry ke exit, bruto tanpa biaya/dividen. IHSG baseline = rata-rata return indeks pada pasangan tanggal identik.",
    "hit_rate": "Hit Rate = jumlah event 20D dengan return saham > return IHSG / n20; seri sama persis dengan Baseline Delta.",
    "confidence_interval": "CI95 = Wilson score interval Hit Rate, z=1.959963984540054. Bukan interval return, bukan probabilitas prediksi. Berlaku per emiten, tanpa koreksi 45 pengujian; ketergantungan residual dapat membuat cakupan nominal optimistis.",
    "baseline_delta": "Rata-rata return saham 20D − rata-rata return IHSG 20D pada event yang sama; satuan percentage points (pp).",
    "regime": "Regime emiten: close>SMA200 dan SMA50>SMA200 → Tren menguat; keduanya di bawah → Tren melemah; selainnya Tren campuran. Wajib 200 sesi IHSG berturut-turut, as-of sama; deskriptif, bukan ramalan.",
    "guards": "Tidak mengisi missing dengan nol. Blok outcome bila ada sesi saham hilang/nonaktif atau lompatan absolute close-to-close >40% di event–exit; ini guard kasar, bukan verifikasi adjustment corporate action.",
    "limitations": [
        "Universe LQ45 adalah membership saat ini, bukan historis; survivorship/selection bias belum dihilangkan.",
        "Harga mentah belum terverifikasi split/dividen/rights; return bukan total return.",
        "Studi event historis eksploratoris; tidak melatih model, tidak membuktikan kausalitas/alpha atau strategi siap trading. Tidak ada forecast atau order.",
        "Sampel <10 diberi label kecil; n=0 menghasilkan angka tidak tersedia, bukan 0%.",
        "CI Wilson mengasumsikan event cukup independen; cooldown mengurangi overlap, tidak menghapus serial dependence. Tidak ada multiple-testing correction.",
        "History flow hanya sepanjang snapshot provider yang tersedia. Data tidak real-time.",
    ],
}


def wilson_interval(hits: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = 1.959963984540054
    rate = hits / count
    denominator = 1 + z*z/count
    center = (rate + z*z/(2*count))/denominator
    half = z*math.sqrt(rate*(1-rate)/count + z*z/(4*count*count))/denominator
    return [max(0, center-half), min(1, center+half)]


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def analyze_issuer(ticker: str, daily: list[dict], flows: list[dict], market: list[dict], *, event_start: str | None = None) -> dict:
    """Evaluate one issuer from verified, unique, chronological source records."""
    prices = {r["date"]: r for r in daily}
    net = {r["date"]: r["net"] for r in flows if isinstance(r.get("net"), (int, float)) and math.isfinite(r["net"])}
    calendar = [r["date"] for r in market]
    benchmark = {r["date"]: r["price"] for r in market}
    excluded: Counter = Counter()
    events: list[dict] = []
    last_event = -100
    latest_z = None
    for index, day in enumerate(calendar):
        in_scope=event_start is None or day>=event_start
        if index < 20 or day not in net:
            continue
        previous = [net.get(d) for d in calendar[index-20:index]]
        if any(v is None for v in previous) or pstdev(previous) == 0:
            if in_scope: excluded["missing_or_constant_flow_window"] += 1
            continue
        z20 = (net[day] - mean(previous))/pstdev(previous)
        if index == len(calendar)-1:
            latest_z = z20
        if z20 < 2 or net[day] <= 0:
            continue
        if index <= last_event + 21:
            if in_scope: excluded["overlapping_events"] += 1
            continue
        last_event = index
        # Older detections still establish cooldown; only requested event dates enter the cohort.
        if not in_scope: continue
        entry = index + 1
        event = {"event_date": day, "net": net[day], "z20": z20,
                 "entry_date": calendar[entry] if entry < len(calendar) else None,
                 "outcomes": {}}
        for horizon in (5, 20):
            exit_index = entry + horizon
            if exit_index >= len(calendar):
                excluded[f"immature_{horizon}d"] += 1
                continue
            path = [prices.get(d) for d in calendar[index:exit_index+1]]
            valid = all(r is not None and _positive(r.get("close")) and
                        ("volume" not in r or _positive(r["volume"])) for r in path)
            if valid:
                valid = all(abs(b["close"]/a["close"]-1) <= .4 for a, b in zip(path, path[1:]))
            if not valid:
                excluded[f"invalid_{horizon}d"] += 1
                continue
            stock_return = prices[calendar[exit_index]]["close"]/prices[calendar[entry]]["close"]-1
            market_return = benchmark[calendar[exit_index]]/benchmark[calendar[entry]]-1
            event["outcomes"][str(horizon)] = {
                "exit_date": calendar[exit_index], "stock_return": stock_return,
                "market_return": market_return, "excess_return": stock_return-market_return,
            }
        events.append(event)
    outcomes5 = [e["outcomes"]["5"] for e in events if "5" in e["outcomes"]]
    outcomes20 = [e["outcomes"]["20"] for e in events if "20" in e["outcomes"]]
    hits = sum(o["excess_return"] > 0 for o in outcomes20)
    trend = {"label": "Belum dihitung", "as_of": calendar[-1] if calendar else None,
             "close": None, "sma50": None, "sma200": None}
    window = [prices.get(d) for d in calendar[-200:]]
    if len(window) == 200 and all(r and _positive(r.get("close")) for r in window):
        close, sma50, sma200 = window[-1]["close"], mean(r["close"] for r in window[-50:]), mean(r["close"] for r in window)
        trend.update(close=close, sma50=sma50, sma200=sma200,
                     label="Tren menguat" if close > sma200 and sma50 > sma200 else
                           "Tren melemah" if close < sma200 and sma50 < sma200 else "Tren campuran")
    return {
        "ticker": ticker, "as_of": calendar[-1] if calendar else None,
        "flow_strength_z20": latest_z, "latest_net": net.get(calendar[-1]) if calendar else None,
        "flow_start": min(net, default=None), "flow_end": max(net, default=None),
        "sample_5d": len(outcomes5), "sample_20d": len(outcomes20), "event_count": len(events),
        "outcome_5d": mean(o["stock_return"] for o in outcomes5) if outcomes5 else None,
        "outcome_20d": mean(o["stock_return"] for o in outcomes20) if outcomes20 else None,
        "baseline_20d": mean(o["market_return"] for o in outcomes20) if outcomes20 else None,
        "baseline_delta_20d": mean(o["excess_return"] for o in outcomes20) if outcomes20 else None,
        "hit_count": hits, "hit_rate": hits/len(outcomes20) if outcomes20 else None,
        "hit_rate_ci95": wilson_interval(hits, len(outcomes20)), "regime": trend,
        "sample_status": "NO_MATURE_EVENTS" if not outcomes20 else "SMALL_SAMPLE" if len(outcomes20)<10 else "DESCRIPTIVE",
        "excluded": dict(excluded), "events": events,
    }


def analyze_bundle(bundle: dict, root: Path) -> dict:
    """Cross-check current membership against individually verified reports."""
    from .market_data import _read_snapshot
    market = bundle.get("ihsg", {})
    foreign = bundle.get("foreign_flow", {})
    rows = []
    issues = list(bundle.get("universe", {}).get("issues", []))
    for issuer in bundle.get("universe", {}).get("symbols", []):
        ticker = issuer["ticker"]
        report, meta, problems = _read_snapshot(root / f"data/raw/sectors/company_report/{ticker}/company_report.json", root)
        membership_ok = not problems and isinstance(report, dict) and report.get("symbol") == ticker+".JK" and meta.get("symbol") == ticker and "LQ45" in (report.get("overview", {}).get("indices") or [])
        daily = bundle.get("lq45_daily", {}).get(ticker, {})
        verified = membership_ok and market.get("data_quality") == "VERIFIED" and foreign.get("data_quality") == "VERIFIED" and daily.get("data_quality") == "VERIFIED"
        row = analyze_issuer(ticker, daily.get("series", []) if verified else [],
                             foreign.get("issuer_daily", {}).get(ticker, []) if verified else [],
                             market.get("series", []) if market.get("data_quality") == "VERIFIED" else [])
        row.update(company=issuer.get("company", ticker), data_quality="VERIFIED" if verified else "BLOCKED",
                   issues=problems if problems else [] if verified else ["Source quality or current LQ45 membership not verified."])
        rows.append(row)
    canonical_daily = {t: {"data_quality": d.get("data_quality"),
                           "series": [{"date": r["date"], "close": r["close"], "volume": r.get("volume")}
                                      for r in d.get("series", [])]}
                       for t, d in bundle.get("lq45_daily", {}).items()}
    source_data = {"ihsg": market.get("series", []), "daily": canonical_daily,
                   "flows": foreign.get("issuer_daily", {}), "symbols": bundle.get("universe", {}).get("symbols", [])}
    fingerprint = hashlib.sha256(json.dumps(source_data, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"ok": bool(rows) and any(r["data_quality"] == "VERIFIED" for r in rows),
            "formula_version": VERSION, "provider": "Sectors.app", "method": METHOD,
            "as_of": market.get("coverage_end"), "source_fingerprint": fingerprint,
            "membership_status": "Reports cross-checked; universe metadata issues retained",
            "issues": issues, "rows": rows,
            "summary": {"issuer_count": len(rows), "computed_count": sum(r["data_quality"] == "VERIFIED" for r in rows),
                        "regimes": dict(Counter(r["regime"]["label"] for r in rows)),
                        "small_sample_count": sum(r["sample_status"] == "SMALL_SAMPLE" for r in rows)}}


def build_screener_analysis(root: Path) -> dict:
    from .market_data import load_ihsg_snapshot, load_issuer_daily, load_lq45_universe
    from .market_overview_analytics import load_foreign_flow
    universe = load_lq45_universe(root)
    tickers = [r["ticker"] for r in universe.get("symbols", [])]
    return analyze_bundle({"universe": universe, "ihsg": load_ihsg_snapshot(root),
                           "lq45_daily": {t: load_issuer_daily(root, t) for t in tickers},
                           "foreign_flow": load_foreign_flow(root, tickers)}, root)
