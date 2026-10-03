"""Offline-first building blocks for IDX Evidence Lab.

This package deliberately contains no network client. Live Sectors and
OpenRouter adapters are approval-gated and are not part of the offline MVP.
"""

__version__ = "0.1.0-offline"

from .schemas import EvidenceState, SourceClass

__all__ = ["EvidenceState", "SourceClass"]
