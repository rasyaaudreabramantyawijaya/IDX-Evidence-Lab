"""Evidence state rules; no predictive claim is made by this module."""

from __future__ import annotations

from .schemas import EvidenceState


def classify_evidence(*, sample_size: int, data_completeness: float,
                      supports: int, contradicts: int,
                      invalidated: bool = False, minimum_sample: int = 30) -> EvidenceState:
    if invalidated:
        return EvidenceState.INVALIDATED
    if sample_size < minimum_sample or data_completeness < 0.7:
        return EvidenceState.INSUFFICIENT
    if supports and contradicts:
        return EvidenceState.MIXED
    if supports >= 2 and data_completeness >= 0.9:
        return EvidenceState.SUPPORTED
    return EvidenceState.WEAK
