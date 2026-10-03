"""The Factor Zoo page must preserve the approved horizontal-to-results hierarchy."""

from pathlib import Path
import subprocess


HTML = Path(__file__).resolve().parents[1] / "docs/prototypes/idx-evidence-lab-user-journey.html"


def test_factor_zoo_layout_has_unnumbered_horizontal_controls_then_chart_then_results():
    source = HTML.read_text(encoding="utf-8")
    start = source.index("function renderPortfolioLab()")
    end = source.index("function mountPortfolioCapitalField()", start)
    panel = source[start:end]
    controls = panel.index("portfolio-controls-row")
    chart = panel.index("factorMarkup")
    results = panel.index("factorResults")
    assert controls < chart < results
    assert "1 · Pilih" not in panel and "2 · Pilih" not in panel and "3 · Asumsi" not in panel
    assert ".portfolio-controls-row{display:grid" in source
    assert "@media(max-width:1050px)" in source
    assert "class=\"section factor-zoo-panel\"" in source
    assert '<details class="portfolio-picker-details" open>' in panel


def test_factor_zoo_chart_maps_axes_color_and_highlights_selection():
    source = HTML.read_text(encoding="utf-8")
    for behavior in ("async function loadFactorZooData()", "function renderFactorZooExplorer(data)",
                     "portfolioApiUrl('/api/portfolio-factor-zoo-data')", "pollFactorZooViewState()",
                     "portfolioApiUrl('/api/portfolio-factor-zoo-view')", "value.score", "momentum.score",
                     "quality.score", "low_volatility.score", "portfolioState.selected"):
        assert behavior in source
    assert "factor-zoo-canvas" in source
    assert "aria-label=\"Factor Zoo 3D" in source


def test_factor_zoo_replica_matches_matlab_axes_grid_ticks_and_axis_titles():
    source = HTML.read_text(encoding="utf-8")
    assert "function drawFactorZooAxes" in source
    assert "const factorZooTicks=[-3,-2,-1,0,1,2,3]" in source
    assert "X · Value · earnings/dividend yield" in source
    assert "Y · Momentum · 12-1 return / MA200" in source
    assert "Z · Quality · ROE / inverse DER" in source
    assert "project(tick,-3,-3)" in source


def test_factor_zoo_replica_uses_matlab_parula_scale_and_numeric_colorbar():
    source = HTML.read_text(encoding="utf-8")
    for tick in ("-3", "-2", "-1", "0", "1", "2", "3"):
        assert f'<span>{tick}</span>' in source
    assert "function factorZooParulaColor" in source
    assert "#352a87" in source and "#f9e721" in source
    matlab = (Path(__file__).resolve().parents[1] / "scripts/build_portfolio_factor_zoo.m").read_text()
    assert "86, lowVol(validIndices)" in matlab
    assert "colormap(ax, parula(256))" in matlab and "cb.Ticks = -3:1:3" in matlab


def test_invalid_or_stale_factor_artifact_keeps_last_valid_state():
    source = HTML.read_text(encoding="utf-8")
    assert "last-known-good" in source
    assert "artifact_fingerprint" in source
    assert "SYNC_ERROR" in source
    assert "Sudut MATLAB menunggu" in source
    assert "Faktor parsial tidak masuk leaderboard" in source


def test_factor_zoo_api_failure_names_proxy_and_retry_resets_failed_attempt():
    source = HTML.read_text(encoding="utf-8")
    assert "localApiFailureMessage('/api/portfolio-factor-zoo-data',error)" in source
    assert "IDX Evidence Lab: Local API (5501)" in source
    assert "factorZooState.attempted=false;factorZooState.error=null" in source
    assert "data-action=\"factor-zoo-retry\"" in source


def test_factor_zoo_hover_names_xyz_scores_and_snapshot_date_and_hides_on_drag():
    source = HTML.read_text(encoding="utf-8")
    assert "X · Value ${factorScoreLabel(s.value.score)}σ" in source
    assert "Y · Momentum ${factorScoreLabel(s.momentum.score)}σ" in source
    assert "Z · Quality ${factorScoreLabel(s.quality.score)}σ" in source
    check = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const text=fs.readFileSync('docs/prototypes/idx-evidence-lab-user-journey.html','utf8');
const fn=text.match(/function factorTooltipDates\(data,r\)\{[^\n]+\}/);
assert(fn,'Date formatter missing');vm.runInThisContext(fn[0]);
const out=factorTooltipDates({as_of:{price:'2026-09-24'}},{report_as_of:'2026-09-25',data_quality:{daily_coverage_start:'2024-12-05',daily_coverage_end:'2026-09-23'}});
assert(out.includes('IHSG: 2026-09-24'));
assert(out.includes('2024-12-05–2026-09-23'));
assert(out.includes('laporan harga as-of: 2026-09-25'));
"""
    executed=subprocess.run(['node','-e',check],cwd=HTML.parents[2],capture_output=True,text=True)
    assert executed.returncode==0,executed.stderr
    assert "tooltip.hidden=true;hoveredPoint=null;drag={x:event.clientX,y:event.clientY}" in source
