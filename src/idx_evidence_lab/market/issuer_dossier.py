"""Deterministic offline issuer dossiers. No forecasting, fitting or API calls."""
from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
from statistics import mean, median, pstdev
from .market_data import _read_snapshot
from .screener_analysis import wilson_interval

VERSION = "issuer-dossier-v1"
METHOD = {
    "disclosures": "Publication date from provider metadata, not independently audited original PDF. Entry at close of the first full IHSG session strictly after publication date; 5/20-session price response versus same-date IHSG. Intraday timestamp/timezone availability unverified. Overlapping disclosure events are not pooled into a strategy or causal effect.",
    "analog": "Same issuer, same close/SMA50/SMA200 regime and Z20 bucket (<-1, -1..1, >1) as latest observation. Features use only current/past data. 20-session horizon, next-session close entry. Candidates spaced >21 sessions; selection/cooldown before outcome guards. Only matured, complete positive-price/volume paths, no >40% jumps. Historical matched conditions, not a forecast.",
    "evaluation": "Chronological quarterly monitoring of fixed net-buy-positive/Z20>=2 events from Screener, next-close entry, non-overlap. Prior sample counts include only events whose 20D exit precedes the quarter. No fitted model or genuine prospective holdout: retrospective fixed-rule walk-forward diagnostic, not validated alpha.",
    "cost": "0/10/25 bps per side on both issuer and same-date IHSG proxy: (1+gross)*(1-c)/(1+c)-1. These are sensitivity assumptions, not observed execution fees. No leverage, dividends, impact or executable index product.",
    "limits": "Current LQ45 membership, not historical membership; raw price adjustment unverified. Small dependent samples; Wilson hit-rate CI is exploratory, not return CI or prediction probability. Report snapshot values are not historical features. Filings response is provider text, not independently audited source-document content. No legal clearance inferred.",
}


def net_return(gross: float, bps: int) -> float:
    c = bps / 10000
    return (1 + gross) * (1 - c) / (1 + c) - 1


def summarize(outcomes: list[dict]) -> dict:
    count = len(outcomes)
    hits = sum(o["stock_return"] > o["market_return"] for o in outcomes)
    values = sorted(o["stock_return"] for o in outcomes)
    def quantile(q):
        if not values:
            return None
        position = (count - 1) * q
        low = int(position)
        return values[low] + (values[min(low + 1, count - 1)] - values[low]) * (position - low)
    return {"sample": count, "mean": mean(values) if count else None,
            "median": median(values) if count else None, "p10": quantile(.1), "p90": quantile(.9),
            "baseline": mean(o["market_return"] for o in outcomes) if count else None,
            "delta": mean(o["stock_return"] - o["market_return"] for o in outcomes) if count else None,
            "hit_rate": hits/count if count else None, "ci95": wilson_interval(hits, count)}


def _features(index, calendar, prices, flows):
    if index < 199:
        return None
    window = [prices.get(d) for d in calendar[index-199:index+1]]
    past = [flows.get(d) for d in calendar[index-20:index]]
    day = calendar[index]
    if any(not r or not isinstance(r.get("close"), (int, float)) or r["close"] <= 0 for r in window):
        return None
    if day not in flows or any(v is None for v in past) or not pstdev(past):
        return None
    sma200, sma50 = mean(r["close"] for r in window), mean(r["close"] for r in window[-50:])
    close = window[-1]["close"]
    regime = "Tren menguat" if close > sma200 and sma50 > sma200 else "Tren melemah" if close < sma200 and sma50 < sma200 else "Tren campuran"
    z = (flows[day] - mean(past))/pstdev(past)
    return {"regime": regime, "z20": z, "bucket": "Z < −1" if z < -1 else "Z > 1" if z > 1 else "−1 ≤ Z ≤ 1"}


def historical_analogs(daily, flow_rows, market):
    prices = {r["date"]: r for r in daily}
    flows = {r["date"]: r["net"] for r in flow_rows if isinstance(r.get("net"), (int, float)) and math.isfinite(r["net"])}
    calendar = [r["date"] for r in market]
    benchmark = {r["date"]: r["price"] for r in market}
    current = _features(len(calendar)-1, calendar, prices, flows) if calendar else None
    matches, rejected, last_selected = [], 0, -100
    if current:
        for i in range(199, len(calendar)-21):
            f = _features(i, calendar, prices, flows)
            if not f or (f["regime"], f["bucket"]) != (current["regime"], current["bucket"]) or i <= last_selected+21:
                continue
            last_selected = i  # selection cannot depend on future path validity
            path = [prices.get(d) for d in calendar[i:i+22]]
            if any(not r or r["close"] <= 0 or r.get("volume", 1) <= 0 for r in path) or any(abs(b["close"]/a["close"]-1) > .4 for a,b in zip(path,path[1:])):
                rejected += 1
                continue
            entry, exit_day = calendar[i+1], calendar[i+21]
            matches.append({"event_date": calendar[i], "entry_date": entry, "exit_date": exit_day,
                            "z20": f["z20"], "stock_return": prices[exit_day]["close"]/prices[entry]["close"]-1,
                            "market_return": benchmark[exit_day]/benchmark[entry]-1})
    return {"current": current, "matches": matches, "rejected": rejected, **summarize(matches)}


def walk_forward(events, bps):
    mature = [dict(e["outcomes"]["20"], event_date=e["event_date"], entry_date=e["entry_date"]) for e in events if "20" in e["outcomes"]]
    periods = sorted({e["event_date"][:4]+"-Q"+str((int(e["event_date"][5:7])-1)//3+1) for e in mature})
    rows = []
    for period in periods:
        year, q = period.split("-Q")
        start = f"{year}-{(int(q)-1)*3+1:02d}-01"
        selected = [e for e in mature if e["event_date"][:4]+"-Q"+str((int(e["event_date"][5:7])-1)//3+1) == period]
        adjusted = [{**e, "stock_return": net_return(e["stock_return"],bps), "market_return": net_return(e["market_return"],bps)} for e in selected]
        rows.append({"period": period, "prior_mature_sample": sum(e["exit_date"] < start for e in mature),
                     "first_event": selected[0]["event_date"], "last_exit": max(e["exit_date"] for e in selected), **summarize(adjusted)})
    adjusted = [{**e,"stock_return": net_return(e["stock_return"],bps),"market_return": net_return(e["market_return"],bps)} for e in mature]
    return {"cost_bps": bps, "periods": rows, "events": adjusted, **summarize(adjusted)}


def documents(root, ticker):
    sources, issues, result = [], [], {"filings": [], "corporate_actions": [], "suspensions": []}
    for kind in result:
        for path in sorted((root/"data/raw/sectors"/kind/ticker).glob("*.json")):
            if path.name.endswith(".metadata.json") or "summary" in path.name:
                continue
            payload, meta, errors = _read_snapshot(path, root)
            issues.extend(errors)
            if errors or not isinstance(payload, dict):
                continue
            if str(meta.get("symbol", "")).replace(".JK", "") != ticker:
                issues.append(f"{path.name}: symbol mismatch")
                continue
            sources.append({"file": path.relative_to(root).as_posix(), "endpoint": meta["endpoint"],
                            "sha256": meta["snapshot_sha256"], "retrieved_at": meta.get("retrieved_at"),
                            "requested_start": meta.get("requested_start"), "requested_end": meta.get("requested_end")})
            if kind == "corporate_actions":
                if payload.get("symbol", "").replace(".JK", "") != ticker:
                    issues.append(f"{path.name}: payload symbol mismatch")
                    continue
                for category, rows in payload.get("corporate_actions", {}).items():
                    for row in rows or []:
                        if isinstance(row, dict):
                            result[kind].append({"type": category, **row})
            else:
                for row in payload.get("results", []):
                    if str(row.get("symbol", "")).replace(".JK", "") == ticker:
                        result[kind].append(row)
    for kind in result:
        unique = {json.dumps(row, sort_keys=True):row for row in result[kind]}
        result[kind] = sorted(unique.values(), key=lambda r: str(r.get("timestamp", r.get("ex_date", r.get("agm_date", "")))), reverse=True)
    return {**result, "sources": sources, "issues": issues}


def disclosure_outcomes(filings, daily, market):
    """Provider publication-date alignment, conservative next-full-session entry."""
    prices = {r["date"]:r for r in daily}
    calendar = [r["date"] for r in market]
    index = {day:i for i,day in enumerate(calendar)}
    benchmark = {r["date"]:r["price"] for r in market}
    results = []
    for filing in filings:
        release = str(filing.get("timestamp", ""))[:10]
        if not release or not calendar or release < calendar[0] or release > calendar[-1]:
            continue
        entry = next((d for d in calendar if d > release), None)
        outcomes = {}
        for horizon in (5,20):
            if not entry or index[entry]+horizon >= len(calendar):
                continue
            dates = calendar[index[entry]:index[entry]+horizon+1]
            path = [prices.get(d) for d in dates]
            if any(not r or r["close"] <= 0 or r.get("volume",1) <= 0 for r in path) or any(abs(b["close"]/a["close"]-1)>.4 for a,b in zip(path,path[1:])):
                continue
            end = dates[-1]
            stock = prices[end]["close"]/prices[entry]["close"]-1
            base = benchmark[end]/benchmark[entry]-1
            outcomes[str(horizon)] = {"exit_date":end,"stock_return":stock,"market_return":base,"excess_return":stock-base}
        results.append({"title":filing.get("title"),"source":filing.get("source"),"release":release,"entry_date":entry,"outcomes":outcomes})
    return results


def build_dossier(bundle, ticker, root):
    analysis = next(r for r in bundle["screener_analysis"]["rows"] if r["ticker"] == ticker)
    daily = bundle["lq45_daily"][ticker]
    flows = bundle["foreign_flow"]["issuer_daily"].get(ticker, [])
    series = daily["series"]
    closes = [r["close"] for r in series]
    returns = [b/a-1 for a,b in zip(closes, closes[1:])]
    peak, drawdown = closes[0], 0
    for close in closes:
        peak = max(peak, close)
        drawdown = min(drawdown, close/peak-1)
    report, meta, problems = _read_snapshot(root/f"data/raw/sectors/company_report/{ticker}/company_report.json", root)
    if report and str(report.get("symbol", "")).replace(".JK", "") != ticker:
        problems.append("company report symbol mismatch")
    report_summary = {key: (report or {}).get(key, {}) for key in ("overview", "valuation", "dividend")} if not problems else {}
    # Avoid exporting large historical/forecast blocks as current measured facts.
    report_summary = {key:{k:v for k,v in obj.items() if not isinstance(v,(list,dict))} for key,obj in report_summary.items()}
    docs = documents(root, ticker)
    if not problems:
        docs["sources"].append({"file": f"data/raw/sectors/company_report/{ticker}/company_report.json", "endpoint": meta["endpoint"], "sha256": meta["snapshot_sha256"], "retrieved_at": meta.get("retrieved_at")})
    docs["issues"].extend(problems)
    for folder in (root/f"data/raw/sectors/daily/{ticker}",root/f"data/raw/sectors/foreign_flow/{ticker}",root/"data/raw/sectors/index_daily/ihsg"):
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".metadata.json"):
                continue
            try:
                metadata=json.loads(path.with_suffix(".metadata.json").read_text())
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                if digest not in (metadata.get("sha256"),metadata.get("snapshot_sha256")) or metadata.get("provider")!="Sectors.app" or metadata.get("http_status")!=200:
                    continue
                docs["sources"].append({"file":path.relative_to(root).as_posix(),"endpoint":metadata.get("endpoint"),"sha256":digest,"retrieved_at":metadata.get("retrieved_at")})
            except (OSError,ValueError):
                continue
    paths = []
    price_map = {r["date"]:r["close"] for r in series}
    market = bundle["ihsg"]["series"]
    for event in analysis["events"]:
        if "20" not in event["outcomes"]:
            continue
        entry, end = event["entry_date"], event["outcomes"]["20"]["exit_date"]
        selected = [r for r in market if entry <= r["date"] <= end]
        paths.append({"event_date":event["event_date"],"path":[{"date":r["date"],"stock":price_map[r["date"]]/price_map[entry]-1,"market":r["price"]/selected[0]["price"]-1} for r in selected]})
    valid = analysis.get("data_quality") == "VERIFIED"
    return {"ticker":ticker,"version":VERSION,"as_of":analysis["as_of"],"source_fingerprint":bundle["screener_analysis"]["source_fingerprint"],
            "method":METHOD,"analysis":analysis,"report":report_summary,"documents":docs,
            "summary":{"close":closes[-1],"daily_change":returns[-1] if returns else None,
                       "volume":series[-1].get("volume"),"return_20d":closes[-1]/closes[-21]-1 if len(closes)>20 else None,
                       "volatility":pstdev(returns)*math.sqrt(252) if len(returns)>1 else None,"max_drawdown":drawdown,
                       "price_start":series[0]["date"],"price_end":series[-1]["date"],"sessions":len(series),
                       "net_5d":sum(r["net"] for r in flows[-5:]) if len(flows)>=5 else None,
                       "net_20d":sum(r["net"] for r in flows[-20:]) if len(flows)>=20 else None},
            "analog":historical_analogs(series,flows,market) if valid else {"sample":0,"matches":[],"current":None},
            "walk_forward":[walk_forward(analysis["events"],bps) for bps in (0,10,25)] if valid else [],
            "event_paths":paths if valid else [],
            "disclosure_events":disclosure_outcomes(docs["filings"],series,market) if valid else [],
            "broker":{"status":"PARTIAL_PROVENANCE","reason":"Arsip empat kode broker ada, tetapi endpoint provenance belum direkonsiliasi; tidak dihitung sebagai total flow atau ranking seluruh broker."}}
