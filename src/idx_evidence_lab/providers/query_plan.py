"""Deterministic query-plan builder used before any optional LLM call."""

from __future__ import annotations

import re
from typing import Iterable, List

from ..core.schemas import QueryPlan


def build_query_plan(query: str, known_tickers: Iterable[str] = ()) -> QueryPlan:
    text = query.strip()
    lowered = text.casefold()
    tickers = {ticker.upper() for ticker in known_tickers}
    entities = sorted({ticker for ticker in tickers if re.search(rf"\b{re.escape(ticker.casefold())}\b", lowered)})

    if any(word in lowered for word in ("bandingkan", "compare", "vs", "versus")):
        intent, scopes = "COMPARE", ["EMITEN", "EVIDENCE"]
    elif any(word in lowered for word in ("aturan", "pasal", "pojk", "uu ", "regulasi")):
        intent, scopes = "FIND_RULE", ["LEGAL_CORPUS"]
    elif any(word in lowered for word in ("akuisisi", "merger", "tender offer", "blocker")):
        intent, scopes = "ASSESS_EVENT", ["LEGAL_CORPUS", "EMITEN", "EVIDENCE"]
    elif any(word in lowered for word in ("buka", "open", "lihat", "show")):
        intent, scopes = "NAVIGATE", ["PRODUCT"]
    elif (
        any(word in lowered for word in ("supported", "screener", "filter"))
        or ("flow" in lowered and any(word in lowered for word in ("positif", "positive", "negatif", "negative")))
    ):
        intent, scopes = "FILTER_SCREEN", ["SCREENER"]
    elif any(word in lowered for word in ("bukti", "evidence", "melemahkan", "kontradiksi")):
        intent, scopes = "FIND_EVIDENCE", ["EVIDENCE", "LEDGER"]
    elif any(word in lowered for word in ("apa itu", "jelaskan", "definisi")):
        intent, scopes = "EXPLAIN_METRIC", ["DOCUMENTATION"]
    else:
        intent, scopes = "UNKNOWN", ["ALL"]

    filters = {}
    horizon = re.search(r"\b(1|5|10|20|60)d\b", lowered)
    if horizon:
        filters["horizon"] = f"{horizon.group(1)}D"
    if "positif" in lowered or "positive" in lowered:
        filters["direction"] = "POSITIVE"
    if "negatif" in lowered or "negative" in lowered:
        filters["direction"] = "NEGATIVE"

    return QueryPlan(
        intent=intent,
        query=text,
        entities=entities,
        scopes=scopes,
        filters=filters,
        needs_clarification=intent == "UNKNOWN" and not entities,
    )
