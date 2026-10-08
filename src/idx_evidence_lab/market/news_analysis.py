"""Deterministic offline news triage and explicitly hypothetical cause paths.

This module derives only from text already present in verified local news
snapshots. It does not call a model or external source and does not claim that
co-mention establishes causality.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any


DRIVER_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Bank Indonesia / suku bunga", (r"\bbi\b", r"bank indonesia", r"suku bunga", r"rate cut", r"rate hike", r"bunga acuan"), "monetary_policy"),
    ("Kementerian Keuangan / fiskal", (r"purbaya", r"sri mulyani", r"kementerian keuangan", r"kemenkeu", r"menteri keuangan", r"anggaran negara", r"apbn", r"subsidi"), "fiscal_policy"),
    ("Rupiah / nilai tukar", (r"rupiah", r"nilai tukar", r"kurs", r"dolar amerika", r"\busd\b"), "fx"),
    ("Komoditas", (r"batu bara", r"coal", r"nikel", r"nickel", r"minyak", r"crude", r"emas", r"gold", r"cpo", r"palm oil", r"tembaga", r"copper"), "commodity"),
    ("Regulasi / otoritas", (r"ojk", r"idx", r"bursa efek indonesia", r"bei", r"peraturan", r"regulasi", r"aturan baru", r"deregulasi"), "regulation"),
    ("Aksi korporasi / transaksi", (r"akuisisi", r"acquisition", r"merger", r"dividen", r"dividend", r"restrukturisasi", r"restructuring", r"kepemilikan", r"ownership", r"capex", r"belanja modal", r"rights issue", r"buyback"), "corporate_event"),
    ("Kinerja / prospek usaha", (r"laba", r"profit", r"pendapatan", r"revenue", r"penjualan", r"sales", r"proyeksi", r"forecast", r"target produksi", r"ekspansi"), "business_performance"),
    ("Teknologi / infrastruktur", (r"data center", r"pusat data", r"5g", r"telekomunikasi", r"infrastruktur", r"pembangkit", r"jaringan"), "infrastructure"),
)

MATERIAL_TERMS = re.compile(
    r"\b(acquire|acquisition|akuisisi|merger|dividen|dividend|restrukturisasi|restructuring|profit|laba|revenue|pendapatan|sales|penjualan|capex|rights issue|buyback|ownership|kepemilikan|rate cut|suku bunga|apbn|subsidi|regulasi|peraturan|forecast|proyeksi|expansion|ekspansi)\b",
    re.I,
)


def _snippet(text: str, pattern: str, radius: int = 72) -> str:
    match = re.search(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])", text, re.I)
    if not match:
        return ""
    left, right = max(0, match.start() - radius), min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip(" .;,:—-")


def analyze_news_article(article: dict[str, Any]) -> dict[str, Any]:
    """Create an explainable mention map and a separate set of hypotheses."""
    title = str(article.get("title") or "")
    body = str(article.get("body") or "")
    text = f"{title}. {body}"
    symbols = list(dict.fromkeys(str(s).upper().replace(".JK", "") for s in article.get("symbols", []) if s))
    sector = str(article.get("sector") or "").strip()
    nodes: list[dict[str, Any]] = [{"id": "story", "label": title, "kind": "source_article", "evidence": title, "x": 0, "y": 0, "z": 0}]
    edges: list[dict[str, Any]] = []
    observations: list[str] = []
    hypotheses: list[str] = []
    drivers: list[tuple[str, str, str]] = []

    if symbols:
        for index, symbol in enumerate(symbols[:20]):
            node_id = f"issuer-{index}"
            nodes.append({"id": node_id, "label": symbol, "kind": "mentioned_issuer", "evidence": f"Ticker tertaut pada record Sectors: {symbol}", "x": 138, "y": (index - (min(len(symbols), 20) - 1) / 2) * 52, "z": (index % 3 - 1) * 28})
            edges.append({"source": "story", "target": node_id, "kind": "source_mention", "label": "ticker tertaut"})
        observations.append("Emiten tertaut pada record berita: " + ", ".join(symbols[:20]))
    else:
        observations.append("Snapshot tidak menautkan ticker emiten secara langsung.")

    if sector:
        nodes.append({"id": "sector", "label": sector, "kind": "observed_sector", "evidence": "Klasifikasi sektor pada snapshot Sectors.app", "x": -138, "y": 0, "z": 0})
        edges.append({"source": "story", "target": "sector", "kind": "source_metadata", "label": "metadata sektor"})
        observations.append("Sektor pada metadata snapshot: " + sector)

    for label, patterns, kind in DRIVER_RULES:
        found = next((pattern for pattern in patterns if re.search(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])", text, re.I)), None)
        if not found:
            continue
        excerpt = _snippet(text, found)
        drivers.append((label, kind, excerpt))

    for index, (label, kind, excerpt) in enumerate(drivers[:12]):
        node_id = f"driver-{index}"
        nodes.append({"id": node_id, "label": label, "kind": "observed_driver", "evidence": excerpt or label, "x": -92, "y": (index - (min(len(drivers), 12) - 1) / 2) * 62, "z": ((index % 3) - 1) * 42})
        edges.append({"source": "story", "target": node_id, "kind": "source_text", "label": "disebut dalam teks"})
        if sector or symbols:
            target_id = "sector" if sector else "issuer-0"
            hypothesis_id = f"hypothesis-{index}"
            hypothesis_label = f"Hipotesis: {label} → {sector or symbols[0]}"
            nodes.append({"id": hypothesis_id, "label": hypothesis_label, "kind": "hypothesis", "evidence": f"Pemicu dan tujuan sama-sama muncul/tertaut pada record; hubungan kausal belum dibuktikan. Cuplikan: {excerpt}", "x": 95, "y": (index - (min(len(drivers), 12) - 1) / 2) * 62 + 28, "z": ((index % 3) - 1) * 54})
            edges.append({"source": node_id, "target": hypothesis_id, "kind": "hypothesis", "label": "jalur untuk diuji"})
            hypotheses.append(hypothesis_label + "; belum diverifikasi oleh data dampak/harga atau sumber independen.")

    if not drivers:
        observations.append("Tidak ada pemicu BI/suku bunga, fiskal, kurs, komoditas, regulasi, atau aksi usaha yang terdeteksi dari kamus istilah offline pada teks tersimpan.")

    matches = list(dict.fromkeys(word.casefold() for word in MATERIAL_TERMS.findall(text)))
    score = (3 if symbols else 0) + min(len(matches), 4) + (2 if len(symbols) > 1 else 0) + (1 if len(drivers) > 1 else 0)
    reasons = []
    if symbols:
        reasons.append("ticker tertaut langsung")
    if matches:
        reasons.append("istilah material tertulis: " + ", ".join(matches[:4]))
    if len(symbols) > 1:
        reasons.append("menyebut lebih dari satu emiten")
    if len(drivers) > 1:
        reasons.append("mengandung lebih dari satu tema pemicu yang terdeteksi")
    if not reasons:
        reasons.append("cakupan simbol/istilah material terbatas; prioritas heuristik rendah")

    source_host = urlparse(str(article.get("source") or "")).hostname or "domain tidak tersedia"
    return {
        "method": "offline_keyword_heuristic_v1",
        "status": "OFFLINE_HYPOTHESIS",
        "source_domain": source_host.removeprefix("www."),
        "priority_score": score,
        "priority_reasons": reasons,
        "matched_material_terms": matches,
        "observations": observations,
        "hypotheses": hypotheses,
        "drivers": [{"label": label, "kind": kind, "evidence": excerpt} for label, kind, excerpt in drivers],
        "graph": {"nodes": nodes, "edges": edges},
        "limitations": "Rule-based dari teks snapshot; co-mention bukan sebab-akibat. Bukan ranking dampak pasar dan belum memakai data harga/event untuk menguji hipotesis.",
    }


def analyze_news_universe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach offline analysis to each news item and rank transparently."""
    for article in articles:
        article["offline_analysis"] = analyze_news_article(article)
    return sorted(
        articles,
        key=lambda item: (
            -item["offline_analysis"]["priority_score"],
            str(item.get("timestamp", "")),
            str(item.get("news_id", "")),
        ),
        reverse=False,
    )
