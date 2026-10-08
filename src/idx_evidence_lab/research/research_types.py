"""Text-only research contracts. Data provenance is distinct from model inference."""
from dataclasses import asdict, dataclass, field
import re

SCOPES = {'issuer', 'comparison', 'sector', 'market', 'portfolio', 'concept'}
CATEGORIES = {'price_risk', 'valuation', 'fundamental', 'flow', 'events', 'news', 'legal', 'market', 'portfolio', 'method'}
CLAIMS = {'concept', 'observation', 'derived_metric', 'inference', 'scenario', 'historical_frequency', 'forecast', 'predictive_probability'}


class JsonRecord:
    def to_dict(self):
        return asdict(self)


@dataclass
class ResearchContext(JsonRecord):
    entities: list[str] = field(default_factory=list)
    scope: str = 'concept'
    topic: str = 'method'
    period: dict = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.scope not in SCOPES or self.topic not in CATEGORIES:
            raise ValueError('Invalid research scope/topic')
        if not isinstance(self.entities, list) or len(self.entities) > (64 if self.scope == 'sector' else 10) or any(
            not isinstance(t, str) or not re.fullmatch(r'[A-Z][A-Z0-9]{2,9}', t) for t in self.entities
        ):
            raise ValueError('Invalid entities')


@dataclass
class ResearchPlan(JsonRecord):
    context: ResearchContext
    categories: list[str]
    clarification: str | None = None
    wants_forecast: bool = False
    wants_probability: bool = False
    query: str = ''

    def __post_init__(self):
        if any(c not in CATEGORIES for c in self.categories):
            raise ValueError('Invalid categories')


@dataclass
class EvidenceItem(JsonRecord):
    id: str
    source_id: str
    source_class: str
    title: str
    excerpt: str
    entities: list[str] = field(default_factory=list)
    category: str = 'fundamental'
    source_date: str | None = None
    period: dict = field(default_factory=dict)
    source_hash: str | None = None
    access_class: str = 'public'
    limits: list[str] = field(default_factory=list)


@dataclass
class MetricRecord(JsonRecord):
    id: str
    name: str
    value: float | int | str
    unit: str
    entities: list[str] = field(default_factory=list)
    period: dict = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    artifact_id: str = ''
    formula_version: str = ''
    validation_status: str = 'PROVISIONAL'
    claim_kind: str = 'derived_metric'
    limits: list[str] = field(default_factory=list)
    forecast_metadata: dict | None = None


@dataclass
class EvidencePack(JsonRecord):
    items: list[EvidenceItem] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class AnswerBlock(JsonRecord):
    kind: str = 'text'
    claim_kind: str = 'concept'
    text: str = ''
    evidence_ids: list[str] = field(default_factory=list)
    metric_ids: list[str] = field(default_factory=list)
    numeric_claims: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class ResearchReply(JsonRecord):
    status: str
    blocks: list[AnswerBlock]
    evidence: list[EvidenceItem]
    metrics: list[MetricRecord]
    coverage: dict
    missing_inputs: list[str]
    model_status: dict
    context: ResearchContext
