"""Offline-first building blocks for IDX Evidence Lab.

Everything runs offline by default. The live Sectors client and the OpenRouter
adapter (openrouter_live) only make network calls when their keys are configured
on the local server; without a key the app answers from local evidence.
"""

__version__ = "0.1.0-offline"

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from .core.schemas import EvidenceState, SourceClass

__all__ = ["EvidenceState", "SourceClass"]
