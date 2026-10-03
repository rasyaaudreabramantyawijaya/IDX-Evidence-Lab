"""Export the verified local news snapshot for the static Live Server prototype."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from idx_evidence_lab.market_data import load_news_universe


TARGET = ROOT / "docs" / "prototypes" / "news-universe.json"


def main() -> None:
    payload = load_news_universe(ROOT)
    if not payload.get("articles"):
        raise SystemExit("No verified local news articles were found; export was not written.")
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(payload['articles'])} articles from {payload['snapshot_count']} verified snapshots to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
