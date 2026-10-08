"""Bounded, issuer-linked evidence selection; navigation is never evidence."""
import hashlib
import re
from pathlib import Path
from .research_types import EvidenceItem, ResearchPlan
from ..core.schemas import SourceClass
from ..core.search import LocalSearchIndex
from .task_navigation import TOPICS

CATEGORY_PATTERNS = {
    'price_risk': r'daily|harga|price|volatil|drawdown|risk|return',
    'valuation': r'valu|earnings|dividend.yield|pe.ratio|pb.ratio',
    'fundamental': r'company.report|financial|laba|profit|revenue|pendapatan|fundamental',
    'flow': r'broker|foreign|flow|asing', 'events': r'filing|corporate.action|akuisisi|merger|dividen|buyback|hmetd',
    'news': r'news|berita', 'market': r'ihsg|market|pasar', 'portfolio': r'portfolio|portofolio',
    'method': r'method|metode|rumus',
}


def linked_excerpt(text, entities):
    """For multi-issuer roundups, retain only segments mentioning requested issuers."""
    # Do not split decimal numbers or company initials. Sentence boundaries require whitespace.
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    mentioned = set(re.findall(r'\b[A-Z]{4}\b', text))
    if entities and len(mentioned) > 1:
        parts = [p for p in parts if any(re.search(rf'\b{re.escape(t)}\b', p, re.I) for t in entities)
                 and not any(t not in entities and re.search(rf'\b{t}\b', p) for t in mentioned)]
    return ' '.join(parts).strip()


def retrieve_research_evidence(root: Path, index: LocalSearchIndex, plan: ResearchPlan, *, limit: int = 16):
    candidates = []
    seen = set()
    event_words = next((words for words in TOPICS.values() if any(w in plan.query.casefold() for w in words)), ())
    for row in index.as_records():
        meta = row['metadata']
        if meta.get('kind') == 'navigation' or row['source_class'] != SourceClass.SECTORS_SOURCE_DATA:
            continue
        if plan.context.entities and row['ticker'] not in plan.context.entities:
            continue
        # Whole news response summaries are not article-level evidence.
        if '/news/' in row['source_id'] and meta.get('kind') != 'news_record':
            continue
        excerpt = linked_excerpt(row['text'], plan.context.entities)
        if not excerpt:
            continue
        haystack = (row['source_id'] + ' ' + excerpt).casefold()
        if event_words and not any(w in excerpt.casefold() for w in event_words):
            continue
        category = next((c for c in plan.categories if c in CATEGORY_PATTERNS and re.search(CATEGORY_PATTERNS[c], haystack)), None)
        if not category:
            continue
        content_hash = hashlib.sha256(' '.join(excerpt.casefold().split()).encode()).hexdigest()
        if content_hash in seen:
            continue
        seen.add(content_hash)
        source_hash = None
        local_path = (root / row['source_id'].split('#')[0]).resolve()
        if local_path.is_relative_to(root.resolve()) and local_path.is_file():
            source_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
        # A date inside the body may be a future event, not the source publication.
        date = re.match(r'\d{4}-\d{2}-\d{2}', str(meta.get('published_at') or ''))
        candidates.append(EvidenceItem(
            id='E' + hashlib.sha256(row['document_id'].encode()).hexdigest()[:16],
            source_id=row['document_id'], source_class=SourceClass.SECTORS_SOURCE_DATA.value,
            title=row['title'], excerpt=excerpt[:1200], entities=[row['ticker']] if row['ticker'] else [],
            category=category, source_date=date[0] if date else None, source_hash=source_hash,
            limits=['Snapshot lokal, bukan konfirmasi kejadian atau data live.'] +
                   (['Cuplikan dipotong.'] if len(excerpt) > 1200 else [])))
    if 'legal' in plan.categories:
        from .legal_corpus import search_legal_corpus
        for row in search_legal_corpus(root, plan.query, limit=5):
            candidates.append(EvidenceItem(
                id='L' + hashlib.sha256(row['source_id'].encode()).hexdigest()[:16],
                source_id=row['source_id'], source_class=row['source_class'], title=row['title'], excerpt=row['excerpt'],
                category='legal', access_class='private', limits=['Applicability dan status berlaku belum diverifikasi.']
            ))
    return candidates[:max(0, limit)]
