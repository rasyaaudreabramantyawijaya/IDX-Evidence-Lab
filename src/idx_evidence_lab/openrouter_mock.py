"""Offline OpenRouter-shaped adapter.

It never performs HTTP. The live adapter must be implemented separately and
approval-gated; this class exists so the product can be tested without a key.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .query_plan import build_query_plan
from .schemas import SourceClass
from .source_policy import SourcePolicy, SourcePolicyError


class MockOpenRouterAdapter:
    provider_name = "OpenRouter"
    source_class = SourceClass.MODEL_INFERENCE

    def __init__(self, *, live: bool = False, policy: SourcePolicy | None = None):
        if live:
            raise SourcePolicyError("Live OpenRouter calls are disabled in the offline adapter")
        self.policy = policy or SourcePolicy()
        self.policy.validate(self.source_class, self.provider_name, network=False)

    def parse_query(self, query: str, known_tickers: list[str]) -> Dict[str, Any]:
        plan = build_query_plan(query, known_tickers)
        return {"source_class": self.source_class.value, "provider": self.provider_name, **plan.to_dict()}

    def compose_grounded_answer(self, question: str, evidence: list[Mapping[str, Any]]) -> Dict[str, Any]:
        if not evidence:
            return {
                "answer": "Evidence is insufficient for a grounded answer.",
                "evidence_state": "INSUFFICIENT",
                "citations": [],
                "source_class": self.source_class.value,
            }
        citations = [str(item.get("document_id", "unknown")) for item in evidence]
        return {
            "answer": f"Offline grounded draft for: {question}",
            "evidence_state": "PROVISIONAL",
            "citations": citations,
            "source_class": self.source_class.value,
            "disclaimer": "Model inference; verify against source records.",
        }
