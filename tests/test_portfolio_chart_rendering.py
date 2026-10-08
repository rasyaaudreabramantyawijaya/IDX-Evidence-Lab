"""Execute chart renderers so syntax-only checks cannot miss broken branches."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


def render(function_name, call):
    if not shutil.which("node"):
        pytest.skip("Node required to execute frontend chart rendering")
    source = HTML.read_text()
    start = source.index(f"      function {function_name}(")
    end = source.index("      function ", start + 16)
    function = source[start:end]
    script = "const escapeHTML=s=>String(s); const portfolioPct=v=>(v*100).toFixed(1)+'%';\n" + function + "\nconsole.log(" + call + ");"
    return subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout


def test_market_history_renderer_supports_a_single_series():
    rows = json.dumps([{"date":"2026-01-01", "wealth":1.0}, {"date":"2026-01-02", "wealth":.9}])
    output = render("portfolioLineChart", f"portfolioLineChart({rows}, [], 'IHSG · harga relatif')")
    assert 'data-label="IHSG · harga relatif"' in output
    assert 'Bobot sama · buy-and-hold' not in output
    assert 'NaN' not in output


def test_scenario_quantiles_stay_inside_svg_and_show_actual_valid_count():
    output = render("drawdownDistribution", "drawdownDistribution({max_drawdown:{p10:-.25,p50:-.16,p90:-.09,valid_paths:300}},120)")
    widths = [float(x) for x in re.findall(r'width:([\d.]+)%', output)]
    assert widths == pytest.approx([100, 64, 36])
    assert '0% · batas sumbu' in output
    assert 'bukan hasil maximum drawdown' in output
    assert '300 lintasan' in output


def test_scenario_drawdown_summary_keeps_history_separate_and_handles_zero():
    output = render('drawdownDistribution', 'drawdownDistribution({max_drawdown:{p10:-.25,p50:-.16,p90:-.09,valid_paths:300}},120,-.30)')
    assert 'MDD historis: -30.0%' in output
    widths = [float(x) for x in re.findall(r'width:([\d.]+)%', output)]
    assert all(0 <= x <= 100 for x in widths)
    zero = render('drawdownDistribution', 'drawdownDistribution({max_drawdown:{p10:0,p50:0,p90:0,valid_paths:300}},120)')
    assert 'NaN' not in zero
    assert 'width:0.000%' in zero


def test_scenario_drawdown_rejects_missing_or_impossible_quantiles():
    missing = render('drawdownDistribution', 'drawdownDistribution({max_drawdown:{p10:null,p50:null,p90:null}},120)')
    assert 'belum tersedia' in missing
    invalid = render('drawdownDistribution', 'drawdownDistribution({max_drawdown:{p10:-.1,p50:-.2,p90:.1}},120)')
    assert 'tidak valid' in invalid
