"""Small, dependency-free schemas shared by offline components."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceClass(str, Enum):
    SECTORS_SOURCE_DATA = "sectors_source_data"
    DERIVED_METRIC = "derived_metric"
    PRIVATE_LEGAL_REFERENCE = "private_legal_reference"
    USER_CONTENT = "user_content"
    PRODUCT_METADATA = "product_metadata"
    MODEL_INFERENCE = "model_inference"


class EvidenceState(str, Enum):
    SUPPORTED = "SUPPORTED"
    MIXED = "MIXED"
    WEAK = "WEAK"
    INSUFFICIENT = "INSUFFICIENT"
    INVALIDATED = "INVALIDATED"


class DataQuality(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    STALE = "stale"
    MISSING = "missing"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Provenance:
    source_class: SourceClass
    source_id: str
    provider: str
    observed_at: Optional[str] = None
    available_at: Optional[str] = None
    schema_version: str = "1"
    formula_version: Optional[str] = None
    document_hash: Optional[str] = None
    citation: Optional[str] = None
    access_class: str = "internal"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["source_class"] = self.source_class.value
        return data


@dataclass(frozen=True)
class IssuerRecord:
    ticker: str
    name: str
    sector: str
    subsector: str = ""
    aliases: List[str] = field(default_factory=list)
    source: Provenance = field(
        default_factory=lambda: Provenance(
            SourceClass.SECTORS_SOURCE_DATA, "mock", "Sectors.app"
        )
    )


@dataclass(frozen=True)
class SectorsSnapshot:
    snapshot_id: str
    as_of: str
    records: List[Dict[str, Any]]
    source: Provenance
    data_quality: DataQuality = DataQuality.VERIFIED


@dataclass(frozen=True)
class SearchDocument:
    document_id: str
    title: str
    text: str
    source_class: SourceClass
    source_id: str
    ticker: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    freshness: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    query: str
    entities: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    requested_metrics: List[str] = field(default_factory=list)
    needs_clarification: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AcquisitionCheck:
    code: str
    label: str
    status: str
    evidence_ids: List[str] = field(default_factory=list)
    reason: Optional[str] = None


@dataclass(frozen=True)
class AcquisitionReadiness:
    status: str
    checks: List[AcquisitionCheck]
    disclaimer: str = "Preliminary decision-support analysis; not legal clearance."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "checks": [asdict(check) for check in self.checks],
            "disclaimer": self.disclaimer,
        }
