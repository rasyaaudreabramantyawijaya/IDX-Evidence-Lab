"""Interaction contracts for date-indexed charts: observed values only."""

from pathlib import Path
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


def test_shared_historical_interaction_helper_uses_observed_metadata_and_no_interpolation():
    source = HTML.read_text(encoding="utf-8")
    assert "function mountHistoricalChartInteraction(root,options)" in source
    assert "options.observations" in source
    assert "options.formatter" in source
    assert "closestObserved" in source
    assert "interpolat" not in source[source.index("function mountHistoricalChartInteraction"):source.index("function ", source.index("function mountHistoricalChartInteraction") + 10)].lower()


def test_historical_chart_markup_exposes_exact_dates_values_and_crosshair_layers():
    source = HTML.read_text(encoding="utf-8")
    for token in ("data-chart-interaction", "data-chart-point", "historical-crosshair-x",
                  "historical-crosshair-y", "chart-interaction-tooltip", "role=\"status\""):
        assert token in source
    assert "data-date=\"${escapeHTML(point.date)}\" data-label=\"Drawdown\"" in source
    assert "data-date=\"${escapeHTML(point.date)}\" data-label=\"${escapeHTML(label)}\"" in source


def test_historical_interaction_mounts_after_renders_without_replacing_app_shell():
    source = HTML.read_text(encoding="utf-8")
    assert "mountHistoricalChartInteraction(root" in source
    assert "main.innerHTML" in source
    assert "requestAnimationFrame" in source


def test_sortino_distribution_points_are_actual_dated_returns_not_kde_interpolations():
    source = HTML.read_text(encoding="utf-8")
    assert "observations=path.map((point,index)=>({date:point.date,value:" in source
    assert 'data-label="Return aktual"' in source
    assert "data-date=\"${escapeHTML(point.date)}\"" in source
    assert "Titik hover menunjukkan tanggal dan return aktual" in source
