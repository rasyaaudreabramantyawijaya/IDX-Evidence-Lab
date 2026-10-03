"""Factor Zoo notebook is a visible, offline, reproducible user deliverable."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "portfolio_factor_zoo.ipynb"


def test_factor_notebook_has_complete_visible_research_trace_and_no_outputs():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert cells[0]["cell_type"] == "markdown"
    markdown = "\n".join("".join(cell["source"]) for cell in cells if cell["cell_type"] == "markdown")
    sections = ["Sumber dan provenance", "Lampirkan bundle lokal", "Kualitas dan cakupan",
                "EDA", "Definisi faktor", "Standardisasi", "Leaderboard", "Eksposur portofolio",
                "Batas interpretasi", "Manifest"]
    positions = [markdown.index(section) for section in sections]
    assert positions == sorted(positions)
    assert "Colab" in markdown and "Kaggle" in markdown
    assert "portfolio_lab_bundle.zip" in markdown
    assert "PENDING" in markdown or "belum dijalankan" in markdown
    for cell in cells:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            assert cell["execution_count"] is None
            compile("".join(cell["source"]), "factor_zoo_notebook_cell", "exec")


def test_factor_notebook_calls_shared_factor_module_without_external_market_data():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code")
    for expected in ("build_factor_zoo_payload", "portfolio_factors", "leaderboards", "coverage", "manifest.json"):
        assert expected in code
    for forbidden in ("requests.get", "urllib.request", "api.sectors.app", "/Users/", "openrouter"):
        assert forbidden not in code
