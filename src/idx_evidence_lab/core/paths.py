"""Repository root, shared by modules that default to the checked-out data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
