"""Local search over curated legal PDFs (kept apart from the HTTP layer so research code can use it)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.schemas import SourceClass

TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def search_legal_corpus(root: Path, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Search text extracted locally from curated PDFs; no PDF content leaves this process."""
    try:
        import fitz
    except ImportError:
        return []
    terms = {token.casefold() for token in TOKEN_RE.split(query) if len(token) > 2}
    if not terms:
        return []
    matches = []
    legal_root = root / "Business & Corporate Law"
    for path in sorted(legal_root.rglob("*.pdf")) if legal_root.exists() else []:
        try:
            with fitz.open(path) as pdf:
                pages = [pdf.load_page(i).get_text("text") for i in range(min(pdf.page_count, 100))]
        except Exception:
            continue
        text = " ".join(pages)
        tokens = {token.casefold() for token in TOKEN_RE.split(text) if len(token) > 2}
        title_tokens = {token.casefold() for token in TOKEN_RE.split(path.stem + " " + path.parent.name) if len(token) > 2}
        score = len(terms & tokens) + 3 * len(terms & title_tokens)
        if score < 1:
            continue
        lower_text = text.casefold()
        offsets = [lower_text.find(term) for term in sorted(terms) if lower_text.find(term) >= 0]
        offset = min(offsets) if offsets else 0
        start = max(0, offset - 140)
        excerpt = " ".join(text[start:start + 420].split())
        matches.append({
            "title": path.stem.replace("_", " "),
            "excerpt": excerpt or "Teks PDF tidak dapat diekstrak; hanya nama berkas yang tersedia.",
            "source_id": path.relative_to(root).as_posix(),
            "source_class": SourceClass.PRIVATE_LEGAL_REFERENCE.value,
            "category": "rujukan_hukum_lokal",
            "score": float(score),
        })
    return sorted(matches, key=lambda item: (-item["score"], item["source_id"]))[:limit]
