"""Notebook delivery must be visible, reproducible, and source-bound."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from idx_evidence_lab.portfolio_analytics import calculate_portfolio_metrics
from idx_evidence_lab.portfolio_data import load_portfolio_inputs
from idx_evidence_lab.portfolio_optimization import optimize_portfolio
from idx_evidence_lab.portfolio_scenarios import simulate_portfolio_scenarios

from scripts.export_portfolio_lab_notebook_data import export_portfolio_notebook_bundle


NOTEBOOK = ROOT / "notebooks" / "portfolio_lab_optimization_and_risk.ipynb"


def test_notebook_has_visible_ordered_research_sections_and_no_outputs():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert cells[0]["cell_type"] == "markdown"
    sections = ["Sumber dan provenance", "Penyiapan data", "EDA", "Baseline",
                "Optimasi", "Metrik historis", "Walk-forward", "Skenario", "Kesimpulan", "Manifest"]
    text = "\n".join("".join(cell["source"]) for cell in cells if cell["cell_type"] == "markdown")
    assert [text.index('## ' + section) for section in sections] == sorted(text.index('## ' + section) for section in sections)
    for cell in cells:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            assert cell["execution_count"] is None
            compile("".join(cell["source"]), "portfolio_lab_notebook_cell", "exec")
    assert "Colab" in text and "Kaggle" in text
    assert "portfolio_lab_bundle.zip" in text


def test_notebook_uses_shared_calculations_and_no_live_market_api():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code")
    for expected in ("load_portfolio_inputs", "optimize_portfolio", "calculate_portfolio_metrics",
                     "run_walk_forward", "simulate_portfolio_scenarios"):
        assert expected in code
    for forbidden in ("requests.get", "urllib.request", "api.sectors.app", "/Users/", "openrouter"):
        assert forbidden not in code


def test_bundle_exports_exact_source_tree_with_hash_manifest(tmp_path):
    output = tmp_path / "portfolio_lab_bundle.zip"
    manifest = export_portfolio_notebook_bundle(ROOT, output)
    assert output.is_file()
    assert manifest["provider"] == "Sectors.app"
    assert manifest["file_count"] > 45
    import zipfile
    with zipfile.ZipFile(output) as archive:
        members = set(archive.namelist())
        assert "manifest.json" in members
        assert "src/idx_evidence_lab/portfolio_optimization.py" in members
        assert "src/idx_evidence_lab/portfolio_factors.py" in members
        assert "data/raw/sectors/lq45-universe.json" in members
        assert "data/raw/sectors/company_report/BBCA/company_report.json" in members
        assert any(name.startswith("data/raw/sectors/daily/BBCA/") for name in members)
        assert "data/raw/sectors/index_daily/ihsg/ihsg_2023-09-25_2023-12-23.json" in members
        for name in members:
            assert not name.startswith("/") and ".." not in Path(name).parts
        embedded = json.loads(archive.read("manifest.json"))
        assert embedded == manifest
        assert "src/idx_evidence_lab/portfolio_factors.py" in embedded["source_files"]
        assert "data/raw/sectors/company_report/BBCA/company_report.json" in embedded["source_files"]
        archive.extractall(tmp_path / "unpacked")
    inputs = load_portfolio_inputs(tmp_path / "unpacked", ["BBCA", "BBRI", "BMRI"])
    assert inputs["status"] == "READY"
    assert inputs["coverage"]["eligible_return_sessions"] >= 126


def test_web_notebook_formula_import_parity_on_synthetic_fixture():
    returns = [[0.01, -0.005], [0.003, 0.007], [-0.012, 0.004],
               [0.008, 0.002], [0.004, -0.003], [0.006, 0.001]]
    tickers = ["AAA", "BBB"]
    allocation = optimize_portfolio(returns, tickers, "hrp", "aggressive", {"max_weight": 1.0})
    assert allocation["status"] in {"READY", "OUTSIDE_PROFILE_BUDGET"}
    weights = [allocation["weights"][ticker] for ticker in tickers]
    series = [sum(r * w for r, w in zip(row, weights)) for row in returns]
    dates = [f"2026-01-{day:02d}" for day in range(1, 7)]
    metrics = calculate_portfolio_metrics(dates, series)
    scenarios = simulate_portfolio_scenarios(returns, weights, horizons=(2, 3), simulations=20, seed=7)
    assert metrics["sample_count"] == len(series)
    assert scenarios["simulations"] == 20
