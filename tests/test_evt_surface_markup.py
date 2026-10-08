"""Observable axis and hover semantics for the empirical tail-loss surface."""

from pathlib import Path
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


def test_evt_surface_hover_snaps_to_observed_vertex_and_reports_axis_coordinates():
    source = HTML.read_text(encoding="utf-8")
    assert "projected=[],hoveredVertex=null" in source
    assert "closest={p,yi,xi}" in source
    assert "hoveredVertex=closest" in source
    assert "Kuantil loss ${level.toFixed(level%1?1:0)}%" in source
    assert "Trailing ${Number(surface.lookback_sessions)} sesi" in source
    assert "tanggal akhir bulan" in source
    assert "kuantil loss empiris" in source
    assert "ambang kerugian return harian" in source


def test_evt_surface_clears_stale_hover_while_rotating_and_draws_guides():
    source = HTML.read_text(encoding="utf-8")
    assert "evt-hover-crosshair" in source
    assert "tip.hidden=true;hoveredVertex=null" in source
