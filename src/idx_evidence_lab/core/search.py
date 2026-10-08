"""Dependency-free local lexical search and issuer/entity resolution."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Dict, Iterable, List, Sequence, Tuple

from .schemas import IssuerRecord, SearchDocument


TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def tokenize(text: str) -> List[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


class EntityResolver:
    def __init__(self, issuers: Iterable[IssuerRecord]):
        self._lookup: Dict[str, str] = {}
        for issuer in issuers:
            names = [issuer.ticker, issuer.name, *issuer.aliases]
            for name in names:
                self._lookup[" ".join(tokenize(name))] = issuer.ticker

    def resolve(self, text: str) -> List[str]:
        normalized = " ".join(tokenize(text))
        found = []
        for alias, ticker in sorted(self._lookup.items(), key=lambda item: -len(item[0])):
            if alias and (alias == normalized or re.search(rf"\b{re.escape(alias)}\b", normalized)):
                if ticker not in found:
                    found.append(ticker)
        return found


class LocalSearchIndex:
    def __init__(self, documents: Iterable[SearchDocument] = ()):
        self._documents: Dict[str, SearchDocument] = {}
        self.add_many(documents)

    def add(self, document: SearchDocument) -> None:
        self._documents[document.document_id] = document

    def add_many(self, documents: Iterable[SearchDocument]) -> None:
        for document in documents:
            self.add(document)

    def search(self, query: str, *, scope: str | None = None, ticker: str | None = None,
               limit: int = 10) -> List[Tuple[SearchDocument, float]]:
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []
        ranked: List[Tuple[SearchDocument, float]] = []
        for document in self._documents.values():
            if scope and scope not in document.scopes:
                continue
            if ticker and document.ticker != ticker.upper():
                continue
            title_tokens = set(tokenize(document.title))
            body_tokens = set(tokenize(document.text))
            title_hits = len(query_tokens & title_tokens)
            body_hits = len(query_tokens & body_tokens)
            if not title_hits and not body_hits:
                continue
            score = (title_hits * 3.0) + body_hits + (0.25 if document.ticker else 0)
            if document.metadata.get("kind") == "navigation":
                score += 10
                if document.ticker and document.ticker.casefold() in query_tokens:
                    score += 20
            ranked.append((document, score))
        ranked.sort(key=lambda item: (-item[1], item[0].document_id))
        return ranked[: max(0, limit)]

    def as_records(self) -> List[dict]:
        return [asdict(document) for document in self._documents.values()]
