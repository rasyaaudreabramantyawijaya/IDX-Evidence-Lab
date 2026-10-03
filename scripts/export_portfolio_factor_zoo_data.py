#!/usr/bin/env python3
"""Build the offline Factor Zoo artifact shared by MATLAB and the prototype."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from idx_evidence_lab.portfolio_factors import export_factor_zoo_artifact  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Hackathon Sectors checkout containing local snapshots")
    parser.add_argument("--output", type=Path, help="Optional artifact output path; default is the prototype data path")
    args = parser.parse_args()
    manifest = export_factor_zoo_artifact(args.root, args.output)
    print("Wrote {} ({} issuers; source {})".format(
        manifest["path"], manifest["issuer_count"], manifest["source_fingerprint"]))


if __name__ == "__main__":
    main()
