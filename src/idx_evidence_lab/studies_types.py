"""Canonical, JSON-safe Studies request contract."""
from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class StudyRequest:
    widget_id: str
    target_kind: str
    targets: tuple[str, ...]
    entities: tuple[str, ...]
    window: str
    params: dict
    cutoff: str | None = None
    portfolio_artifact_ref: str | None = None


def request_fingerprint(request: StudyRequest, source_hashes: list[str], *, formula_version: str | None = None) -> str:
    payload = {'request': asdict(request), 'sources': sorted(set(source_hashes)),
               'contract_version': 'studies-v1', 'formula_version':formula_version}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()
