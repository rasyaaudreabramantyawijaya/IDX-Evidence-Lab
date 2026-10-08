"""Local search index over snapshots and curated documents."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..core.paths import ROOT
from ..core.schemas import SearchDocument, SourceClass
from ..core.search import LocalSearchIndex
from ..market.market_data import load_lq45_universe


MAX_INDEX_DOCUMENTS = 3000


MAX_INDEX_FILE_BYTES = 200_000


TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


APPLICATION_PAGES = (
    ("dashboard", "Dashboard", "Ringkasan pasar IHSG berita emiten"),
    ("screener", "Screener", "Filter saham ticker sektor metrik valuasi"),
    ("watchlist", "Watchlist", "Daftar pantauan saham"),
    ("studies", "Studies", "Studi riset evidence dossier"),
    ("research", "Riset emiten", "Pertanyaan akuisisi aksi korporasi HMETD OpenRouter"),
    ("portfolio-lab", "Portfolio Lab", "Portofolio portfolio optimasi alokasi risiko Sharpe drawdown faktor simulasi"),
    ("market", "Market overview", "IHSG pasar sektor heatmap volatilitas EVT"),
    ("news-universe", "News Universe", "Berita news emiten"),
    ("sources", "Sumber & metode PDF", "Provenance snapshot dokumen hukum sumber metodologi"),
    ("settings", "Settings", "Pengaturan koneksi API key OpenRouter"),
)


def load_tickers(root: Path = ROOT) -> tuple[str, ...]:
    universe_path = root / "data" / "raw" / "sectors" / "lq45-universe.json"
    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return tuple(sorted({
        str(item.get("symbol", "")).split(".")[0].upper()
        for item in results
        if isinstance(item, dict)
        and "LQ45" in item.get("query_values", {}).get("indices", [])
        and item.get("symbol")
    }))


def build_local_index(root: Path = ROOT) -> LocalSearchIndex:
    """Build a bounded index from local docs, approved snapshot files, and legal filenames."""
    documents: list[SearchDocument] = []
    tickers = load_tickers(root)
    pages = APPLICATION_PAGES if (root / "docs/prototypes/idx-evidence-lab-user-journey.html").exists() else ()
    for page, title, description in pages:
        documents.append(SearchDocument(
            document_id=f"app/page/{page}", title=title, text=description,
            source_class=SourceClass.PRODUCT_METADATA, source_id=f"app/page/{page}",
            scopes=["PRODUCT"], metadata={"page": page, "kind": "navigation"}))
    for issuer in load_lq45_universe(root).get("symbols", []):
        symbol = issuer["ticker"]
        documents.append(SearchDocument(
            document_id=f"app/issuer/{symbol}", title=f"{symbol} · {issuer['company']}",
            text=f"{symbol} {issuer['company']} · Buka profil emiten, harga historis, berita dan dossier snapshot lokal.",
            source_class=SourceClass.SECTORS_SOURCE_DATA,
            source_id="data/raw/sectors/lq45-universe.json", ticker=symbol,
            scopes=["EMITEN"], metadata={"page": "issuer", "kind": "navigation"}))
    for folder in (root / "docs", root / "data" / "raw" / "sectors"):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if len(documents) >= MAX_INDEX_DOCUMENTS:
                break
            if not path.is_file() or path.name.endswith((".metadata.json", "_meta.json")):
                continue
            if path.suffix.casefold() not in {".json", ".md", ".txt", ".html"}:
                continue
            try:
                if path.stat().st_size > MAX_INDEX_FILE_BYTES:
                    continue
                raw_text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = _searchable_text(path, raw_text)[:8000]
            relative = path.relative_to(root).as_posix()
            ticker = next((t for t in tickers if re.search(rf"\b{re.escape(t)}\b", relative.upper())), None)
            source_class = SourceClass.PRODUCT_METADATA if relative.startswith("docs/") else SourceClass.SECTORS_SOURCE_DATA
            scopes = ["PRODUCT"] if source_class is SourceClass.PRODUCT_METADATA else ["EVIDENCE", "EMITEN"]
            if "ihsg" in relative.casefold():
                scopes.extend(["MARKET", "IHSG"])
            documents.append(SearchDocument(
                document_id=relative,
                title=path.stem.replace("_", " "),
                text=text,
                source_class=source_class,
                source_id=relative,
                ticker=ticker,
                scopes=scopes,
                metadata={"path": relative, "kind": path.suffix.lstrip(".")},
            ))
            if relative.startswith("data/raw/sectors/news/"):
                documents.extend(_news_documents(path, root, tickers))

    # The legal corpus remains local: index filenames only, never PDF contents.
    legal_root = root / "Business & Corporate Law"
    if legal_root.exists():
        for path in sorted(legal_root.rglob("*.pdf")):
            if len(documents) >= MAX_INDEX_DOCUMENTS:
                break
            relative = path.relative_to(root).as_posix()
            documents.append(SearchDocument(
                document_id=relative,
                title=path.stem.replace("_", " "),
                text=f"Dokumen hukum lokal; folder {path.parent.name}; nama berkas {path.name}",
                source_class=SourceClass.PRIVATE_LEGAL_REFERENCE,
                source_id=relative,
                scopes=["LEGAL_CORPUS", "FIND_RULE"],
                metadata={"path": relative, "kind": "private_pdf_filename_only"},
            ))
    return LocalSearchIndex(documents)


def _snippet(text: str, query: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    query_tokens = [t for t in TOKEN_RE.split(query.casefold()) if len(t) > 2]
    lower = compact.casefold()
    offset = next((lower.find(token) for token in query_tokens if lower.find(token) >= 0), 0)
    start = max(0, offset - 100)
    return ("…" if start else "") + compact[start:start + limit].strip() + ("…" if start + limit < len(compact) else "")


def _searchable_text(path: Path, raw_text: str) -> str:
    """Return a compact, human-readable search representation; never expose JSON dumps."""
    if path.suffix.casefold() != ".json":
        return raw_text
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return f"{path.stem.replace('_', ' ')} JSON document; content could not be parsed"

    records = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        for key in ("results", "data", "observations", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
    rows = [row for row in records if isinstance(row, dict)]
    if rows and all("date" in row and "close" in row for row in rows):
        ticker = next((str(row.get("symbol", "")).replace(".JK", "") for row in rows if row.get("symbol")), path.parent.name)
        dates = [str(row["date"]) for row in rows if row.get("date")]
        recent = sorted(rows, key=lambda row: str(row.get("date", "")))[-3:]
        observations = "; ".join(
            f"{row.get('date')}: close {row.get('close')}"
            + (f", volume {row.get('volume')}" if row.get("volume") is not None else "")
            for row in recent
        )
        date_range = f"{min(dates)}–{max(dates)}" if dates else "tanggal tidak tersedia"
        return (f"Daily OHLCV {ticker} • {len(rows)} observasi • {date_range}. "
                f"Contoh observasi terbaru: {observations}. Field: symbol, date, close, open, high, low, volume, market_cap.")

    # Keep useful metadata/record values searchable but bounded and readable.
    values: list[str] = []
    skipped = {"sha256", "raw", "payload", "content", "authorization", "api_key", "token"}

    def collect(value: Any, depth: int = 0) -> None:
        if len(values) >= 50 or depth > 2:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).casefold() in skipped:
                    continue
                if isinstance(item, (str, int, float, bool)) and len(str(item)) < 180:
                    values.append(f"{key}: {item}")
                elif isinstance(item, (dict, list)):
                    collect(item, depth + 1)
                if len(values) >= 50:
                    break
        elif isinstance(value, list):
            values.append(f"records: {len(value)}")
            for item in value[:3]:
                collect(item, depth + 1)

    collect(payload)
    return f"{path.stem.replace('_', ' ')} • " + ("; ".join(values) if values else "JSON document")


def _news_documents(path: Path, root: Path, tickers: tuple[str, ...]) -> list[SearchDocument]:
    """Index bounded news rows individually so issuer research can retrieve them."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    relative = path.relative_to(root).as_posix()
    documents = []
    for index, row in enumerate(rows[:500]):
        if not isinstance(row, dict):
            continue
        symbols = row.get("symbols") or row.get("symbol") or row.get("tickers") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        normalized = {str(value).upper().replace(".JK", "") for value in symbols if value}
        title = str(row.get("title") or row.get("headline") or row.get("news_title") or "Berita Sectors")
        body = str(row.get("content") or row.get("body") or row.get("description") or row.get("summary") or "")
        if not normalized:
            haystack = f"{title} {body}".upper()
            normalized = {symbol for symbol in tickers if re.search(rf"\b{re.escape(symbol)}\b", haystack)}
        if not normalized:
            continue
        article_text = " ".join((
            f"title: {title}", f"date: {row.get('published_at') or row.get('date') or row.get('timestamp') or 'tanggal tidak tersedia'}",
            f"symbols: {', '.join(sorted(normalized))}", f"description: {body[:2400]}",
        ))
        for symbol in sorted(normalized & set(tickers)):
            documents.append(SearchDocument(
                document_id=f"{relative}#news-{index}-{symbol}", title=title,
                text=article_text, source_class=SourceClass.SECTORS_SOURCE_DATA,
                source_id=relative, ticker=symbol, scopes=["EVIDENCE", "EMITEN", "NEWS"],
                metadata={"path": relative, "record_index": index, "kind": "news_record",
                          "published_at": row.get('published_at') or row.get('date') or row.get('timestamp')},
            ))
    return documents
