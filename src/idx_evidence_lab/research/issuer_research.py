"""Evidence retrieval for a single issuer question."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.schemas import SourceClass
from ..core.search import LocalSearchIndex
from .legal_corpus import search_legal_corpus
from .local_index import _snippet


QUERY_EXPANSIONS = {
    "right issue": "right issue HMETD penambahan modal hak memesan efek terlebih dahulu",
    "rights issue": "rights issue HMETD penambahan modal hak memesan efek terlebih dahulu",
    "akuisisi": "akuisisi pengambilalihan perusahaan pengendali tender offer merger",
    "merger": "merger penggabungan usaha akuisisi pengambilalihan",
    "buyback": "buyback pembelian kembali saham",
    "aksi korporasi": "corporate action rights issue buyback dividend merger acquisition",
    "pengambilalihan": "acquisition takeover tender offer",
}


def build_issuer_research(root: Path, ticker: str, question: str,
                          index: LocalSearchIndex) -> dict[str, Any]:
    """Retrieve only matching local issuer snapshots and concise private-PDF excerpts."""
    query = question.strip()[:500]
    expanded = query.casefold()
    for phrase, expansion in QUERY_EXPANSIONS.items():
        if phrase in expanded:
            query += " " + expansion
    matches = index.search(query, ticker=ticker, limit=12)
    evidence = []
    seen = set()
    for document, score in matches:
        if document.metadata.get("kind") == "navigation":
            continue
        source_id = document.document_id if document.metadata.get("kind") == "news_record" else document.source_id
        if source_id in seen:
            continue
        seen.add(source_id)
        lower_path = source_id.casefold()
        category = (
            "filing" if "/filings/" in lower_path else
            "aksi_korporasi" if "/corporate_actions/" in lower_path else
            "berita" if "/news/" in lower_path else
            "laporan_emiten" if "/company_report/" in lower_path else
            "data_lokal"
        )
        evidence.append({
            "title": document.title,
            "excerpt": _snippet(document.text, query, 380),
            "source_id": source_id,
            "source_class": document.source_class.value,
            "category": category,
            "score": score,
        })
    legal = search_legal_corpus(root, query, limit=5) if re.search(r'hukum|aturan|pasal|pojk|regulasi', query, re.I) else []
    evidence.extend(legal)
    evidence.sort(key=lambda item: (-item.get("score", 0), item["source_id"]))
    sectors_count = sum(item["source_class"] == SourceClass.SECTORS_SOURCE_DATA.value for item in evidence)
    legal_count = sum(item["source_class"] == SourceClass.PRIVATE_LEGAL_REFERENCE.value for item in evidence)
    if sectors_count == 0 and legal_count == 0:
        synthesis = "Belum ditemukan sumber lokal yang cocok dengan pertanyaan ini. Tidak ada kesimpulan atau perkiraan yang dibuat. Coba sebut ticker, nama aksi korporasi, atau istilah peraturan yang lebih spesifik."
        status = "INSUFFICIENT_EVIDENCE"
    else:
        synthesis = (
            f"Retrieval lokal menemukan {sectors_count} potongan snapshot Sectors dan {legal_count} rujukan korpus hukum yang cocok. "
            "Baca tanggal dan kutipan tiap sumber di bawah. Kecocokan kata bukan bukti bahwa aksi korporasi akan terjadi. "
            "Penilaian prospektif perlu filing terbaru yang spesifik, dokumen aturan yang berlaku, serta verifikasi applicability; "
            "tanpa itu statusnya tetap belum cukup untuk memperkirakan kejadian."
        )
        status = "PROVISIONAL_EVIDENCE_REVIEW"
    return {
        "ticker": ticker,
        "question": question.strip(),
        "answer": synthesis,
        "evidence_state": status,
        "evidence": evidence,
        "retrieval": {"sectors_snapshots": sectors_count, "private_legal_documents": legal_count},
        "as_of": "2026-09-24 for daily/index snapshots; each event/report retains its own source date",
        "source_boundary": "Sectors.app snapshots and manually curated local legal PDFs only; no web search or model-generated facts.",
        "analysis_boundary": "This prototype retrieves evidence; it does not estimate event probabilities or provide legal clearance.",
    }
