"""Guards for the generated legacy UI (frontend/legacy -> docs/prototypes/app.{css,js})."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "frontend" / "legacy"
PROTOTYPES = ROOT / "docs" / "prototypes"


def test_generated_files_match_the_chunks():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_legacy_ui.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["styles", "scripts"])
def test_chunk_prefixes_are_unique_and_increasing(kind):
    names = sorted(p.name for p in (CHUNKS / kind).iterdir() if p.is_file())
    prefixes = [re.match(r"(\d+)-", name) for name in names]
    assert all(prefixes), names
    numbers = [int(m.group(1)) for m in prefixes]
    assert numbers == sorted(set(numbers)), f"duplicate or unordered prefixes in {kind}: {names}"


def test_page_has_no_inline_script_or_style_and_loads_the_built_files():
    html = (PROTOTYPES / "idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would be blocked by CSP"
    assert "<style" not in html
    assert not re.search(r"\son(click|change|input|submit|load|error)=", html)
    assert html.index("/docs/prototypes/studies-ui.js") < html.index("/docs/prototypes/app.js")
    assert 'href="/docs/prototypes/app.css"' in html


def test_built_script_parses_and_stylesheet_is_balanced():
    css = (PROTOTYPES / "app.css").read_text(encoding="utf-8")
    assert css.count("{") == css.count("}")
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required to syntax-check app.js")
    result = subprocess.run([node, "--check", str(PROTOTYPES / "app.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_image_ships_the_built_files():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert "COPY docs/prototypes ./docs/prototypes" in dockerfile
    assert not {"docs", "docs/prototypes", "docs/prototypes/app.js", "app.js", "*.js", "*.css"} & set(ignore)
