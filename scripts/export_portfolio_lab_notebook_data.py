"""Package saved, approved Sectors snapshots for the offline Portfolio Lab notebook.

No API request is made. Existing raw snapshots are only read, never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


MODULES = (
    # Real implementations (the notebooks import through these packages).
    "__init__.py", "core/__init__.py", "core/schemas.py", "market/__init__.py", "market/market_data.py",
    "market/news_analysis.py", "portfolio/__init__.py", "portfolio/portfolio_data.py",
    "portfolio/portfolio_analytics.py", "portfolio/portfolio_optimization.py",
    "portfolio/portfolio_scenarios.py", "portfolio/portfolio_factors.py", "portfolio/portfolio_amounts.py",
    # Old import paths, kept as aliases of the modules above.
    "market_data.py", "portfolio_data.py", "portfolio_analytics.py", "portfolio_optimization.py",
    "portfolio_scenarios.py", "portfolio_factors.py", "portfolio_amounts.py",
)


def export_portfolio_notebook_bundle(root: Path, output_path: Path) -> dict[str, Any]:
    """Create a fresh ZIP of the current LQ45 inputs, companion metadata, and shared code."""
    root = root.resolve(strict=True)
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing bundle: {output_path}")
    base = root / "data" / "raw" / "sectors"
    universe_path = base / "lq45-universe.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    tickers = sorted({str(row.get("symbol", "")).removesuffix(".JK").upper()
                      for row in universe.get("results", [])
                      if isinstance(row, dict) and "LQ45" in row.get("query_values", {}).get("indices", [])})
    if not tickers or len(tickers) > 45 or any(not ticker.isalnum() for ticker in tickers):
        raise ValueError("Current LQ45 universe is missing or malformed")

    paths = [universe_path, base / "lq45-universe.metadata.json"]
    for module in MODULES:
        paths.append(root / "src" / "idx_evidence_lab" / module)
    paths.append(root / "requirements-portfolio.txt")
    for ticker in tickers:
        paths.extend((base / "daily" / ticker).glob(f"{ticker}_*.json"))
        report = base / "company_report" / ticker / "company_report.json"
        paths.extend((report, report.with_suffix(".metadata.json")))
    for index in ("ihsg", "lq45"):
        paths.extend((base / "index_daily" / index).glob(f"{index}_*.json"))

    relative_paths = sorted({path.relative_to(root) for path in paths})
    for relative in relative_paths:
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"Required bundle input missing or symlinked: {relative}")
    manifest: dict[str, Any] = {
        "product": "IDX Evidence Lab Portfolio Lab offline research bundle",
        "provider": "Sectors.app", "universe": "current LQ45 snapshot",
        "ticker_count": len(tickers), "tickers": tickers,
        "file_count": len(relative_paths),
        "hash_algorithm": "sha256",
        "source_files": {relative.as_posix(): hashlib.sha256((root / relative).read_bytes()).hexdigest()
                         for relative in relative_paths},
        "limitations": ["Current membership is not historical membership",
                        "Universe snapshot metadata hash must be rechecked by the loader",
                        "Prices are not verified corporate-action/dividend adjusted"],
        "external_api_calls": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in relative_paths:
            archive.write(root / relative, relative.as_posix())
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / "data" / "processed" / "portfolio_lab_bundle.zip"
    manifest = export_portfolio_notebook_bundle(args.root, output)
    print(f"Created {output} with {manifest['file_count']} files for {manifest['ticker_count']} tickers")


if __name__ == "__main__":
    main()
