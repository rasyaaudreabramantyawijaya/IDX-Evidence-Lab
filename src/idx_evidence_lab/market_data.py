"""Compatibility alias: this module now lives in idx_evidence_lab.market.market_data."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("idx_evidence_lab.market.market_data")
