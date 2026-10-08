"""Issuer-scoped descriptive rankings of the supplied four-broker cache.

Integrity hashes do not establish endpoint origin or all-broker coverage.
This partial archive is NOT used as a validated signal or foreign-flow fallback.
"""
from __future__ import annotations
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def rank_window(records, codes, requested_sessions):
    """Compare only explicit complete records on identical dates, never fill zero."""
    date_sets = [set(records.get(code, {})) for code in codes]
    common = sorted(set.intersection(*date_sets)) if date_sets else []
    dates = common[-requested_sessions:] if requested_sessions else common
    if not dates:
        return {"requested_sessions":requested_sessions,"sessions":0,"start":None,"end":None,"rows":[],"buyers":[],"sellers":[],"sources":[]}
    rows, sources = [], {}
    for code in codes:
        chosen = [records[code][day] for day in dates]
        buy, sell = sum(r["bval"] for r in chosen), sum(r["sval"] for r in chosen)
        rows.append({"code":code,"buy":buy,"sell":sell,"net":buy-sell,"gross":buy+sell,"sessions":len(chosen)})
        for row in chosen:
            for source in row.get("sources",[]):
                sources[source["file"]] = source
    gross = sum(row["gross"] for row in rows)
    for row in rows:
        row["share_sample_gross"] = row["gross"]/gross if gross else None
    rows.sort(key=lambda r:(-r["net"],r["code"]))
    buyers = sorted((r for r in rows if r["net"]>0),key=lambda r:(-r["net"],r["code"]))
    sellers = sorted((r for r in rows if r["net"]<0),key=lambda r:(r["net"],r["code"]))
    return {"requested_sessions":requested_sessions,"sessions":len(dates),"dates":dates,"start":dates[0],"end":dates[-1],
            "rows":rows,"buyers":buyers,"sellers":sellers,"sources":list(sources.values())}


def load_broker_rankings(root: Path, tickers: list[str]):
    base=root/"data/raw/sectors/cache_lq45"
    try:
        manifest=json.loads((base/"cache_manifest.json").read_text())
    except (OSError,ValueError):
        return {t:{"status":"MISSING","cases":[],"reason":"Inventaris arsip broker belum tersedia."} for t in tickers}
    entries=[e for e in manifest.get("entries",[]) if e.get("category")=="broker_flow"]
    observed=defaultdict(lambda:defaultdict(dict)); conflicts=defaultdict(set)
    wanted=set(tickers); codes=set(); problems=[]; hashes=[]; file_count=0
    for entry in entries:
        # Paths must resolve inside the manifest's cache folder.
        path=(base/entry["file"]).resolve()
        if not path.is_relative_to(base.resolve()):
            problems.append("Manifest path outside cache folder")
            continue
        try:
            raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if digest!=entry.get("sha256") or entry.get("http_status")!=200:
                problems.append(f"{entry['file']}: integrity/status mismatch")
                continue
            payload=json.loads(raw)
            if payload.get("status")!=200:
                problems.append(f"{entry['file']}: response status mismatch")
                continue
            body=payload.get("body",{});code=body.get("broker_code")
            if not isinstance(code,str) or not code:
                problems.append(f"{entry['file']}: missing broker code")
                continue
            codes.add(code);hashes.append((entry['file'],digest));file_count+=1
            source={"file":path.relative_to(root).as_posix(),"sha256":digest,"retrieved_at":entry.get("retrieved_at"),
                    "endpoint":None,"status":"PARTIAL_ENDPOINT_PROVENANCE"}
            for session in body.get("data",[]):
                day=session.get("date")
                if not isinstance(day,str) or len(day)!=10 or not body.get("start",day)<=day<=body.get("end",day):
                    problems.append(f"{entry['file']}: invalid date")
                    continue
                for row in session.get("summary",[]):
                    symbol=str(row.get("symbol","")).removesuffix(".JK")
                    if symbol not in wanted:
                        continue
                    b,s=row.get("bval"),row.get("sval")
                    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in (b,s)):
                        conflicts[symbol].add((code,day));continue
                    net=row.get("nval",b-s)
                    if not isinstance(net,(int,float)) or not math.isfinite(net) or abs(net-(b-s))>max(1,abs(b-s)*1e-8):
                        conflicts[symbol].add((code,day));continue
                    record={"bval":b,"sval":s,"sources":[source]}
                    prior=observed[symbol][code].get(day)
                    if prior and (prior['bval'],prior['sval'])!=(b,s):
                        conflicts[symbol].add((code,day))
                    elif prior:
                        prior['sources'].append(source)  # identical duplicate counted once
                    else:
                        observed[symbol][code][day]=record
        except (OSError,ValueError,TypeError) as error:
            problems.append(f"{entry['file']}: {type(error).__name__}")
    fingerprint=hashlib.sha256(json.dumps(sorted(hashes),separators=(",",":")).encode()).hexdigest()
    result={}
    for ticker in tickers:
        records=observed[ticker]
        for code,day in conflicts[ticker]:
            records[code].pop(day,None)
        cases=[rank_window(records,sorted(codes),count) for count in (1,5,20,0)]
        result[ticker]={"status":"PARTIAL_ARCHIVE" if cases[0]['sessions'] else "INSUFFICIENT_ALIGNED_RECORDS",
            "codes":sorted(codes),"file_count":file_count,"fingerprint":fingerprint,"cases":cases,
            "excluded_conflicts":len(conflicts[ticker]),"issues":problems,
            "reason":"Ranking deskriptif hanya untuk kode broker dalam arsip lokal. Hash file cocok dengan inventaris, tetapi endpoint asal belum tercatat dan cakupan bukan seluruh broker. Kode broker bukan identitas pemilik manfaat.",
            "method":"Net = sum(bval) − sum(sval). Pembeli: net positif terbesar; penjual: net negatif terbesar secara absolut. Periode memakai tanggal record yang tersedia pada semua kode broker; missing tidak diisi nol. Porsi = (beli+jual broker)/sum(beli+jual seluruh broker dalam sampel), bukan pangsa seluruh pasar; transaksi antarbroker dapat terhitung pada kedua sisi."}
    return result
