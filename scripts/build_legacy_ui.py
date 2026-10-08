#!/usr/bin/env python3
"""Build the legacy page's stylesheet and script from the ordered chunks in frontend/legacy/.

    python scripts/build_legacy_ui.py           # write docs/prototypes/app.css and app.js
    python scripts/build_legacy_ui.py --check   # fail if the committed files differ from a fresh build (CI)

The chunks are consecutive slices of one script (they share a single closure and several function names are
declared twice, the last declaration wins), so file order is behavior: they are joined in file-name order and
must not be reordered. Edit a chunk, run this script, commit the chunk and the generated files together.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "legacy"
OUT = ROOT / "docs" / "prototypes"


def build() -> dict[Path, str]:
    css = "".join(path.read_text(encoding="utf-8") for path in sorted((SRC / "styles").glob("*.css")))
    inner = "".join(path.read_text(encoding="utf-8") for path in sorted((SRC / "scripts").glob("*.js")))
    return {OUT / "app.css": css, OUT / "app.js": "    (()=>{\n" + inner + "    })();\n"}


def main(argv: list[str]) -> int:
    outputs = build()
    if "--check" in argv:
        stale = [p.relative_to(ROOT) for p, text in outputs.items()
                 if not p.is_file() or p.read_bytes() != text.encode("utf-8")]
        if stale:
            print("Out of date, run `python scripts/build_legacy_ui.py`:", *map(str, stale), sep="\n  ")
            return 1
        print("legacy UI build is up to date")
        return 0
    for path, text in outputs.items():
        path.write_bytes(text.encode("utf-8"))  # always LF: the golden master hashes these bytes
        print(f"wrote {path.relative_to(ROOT)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
