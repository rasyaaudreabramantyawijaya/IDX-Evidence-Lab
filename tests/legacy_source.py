"""Source of the legacy single-page app for tests that assert on it.

The page is split into `idx-evidence-lab-user-journey.html` (markup), `app.css` and `app.js` (generated from
`frontend/legacy/`, see scripts/build_legacy_ui.py). Tests that look for strings or functions in "the page"
read all three, in the order the browser applies them.
"""
from pathlib import Path

PROTOTYPES = Path(__file__).resolve().parents[1] / "docs" / "prototypes"
HTML_PATH = PROTOTYPES / "idx-evidence-lab-user-journey.html"


class LegacyPage:
    """Path-like stand-in: `.read_text()` returns markup + stylesheet + script."""

    @property
    def parents(self):
        return HTML_PATH.parents

    def read_text(self, encoding: str = "utf-8") -> str:
        parts = (HTML_PATH, PROTOTYPES / "app.css", PROTOTYPES / "app.js")
        return "\n".join(p.read_text(encoding=encoding) for p in parts)


LEGACY_PAGE = LegacyPage()
