"""3D chart coordinate and stale-hover contracts."""

from pathlib import Path
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


def test_both_3d_charts_have_explicit_axis_titles_and_observed_hover_values():
    source = HTML.read_text(encoding="utf-8")
    for field in ("tanggal akhir bulan", "kuantil loss empiris", "ambang kerugian return harian",
                  "X · Value", "Y · Momentum", "Z · Quality", "Harga as-of:", "Trailing "):
        assert field in source
    assert "closest={p,yi,xi}" in source
    assert "projected=points.map(point=>({...point,p:project(point.x,point.y,point.z)}))" in source


def test_hover_state_is_suppressed_during_rotation_and_crosshair_is_rendered():
    source = HTML.read_text(encoding="utf-8")
    assert "evt-hover-crosshair" in source
    assert "tip.hidden=true;hoveredVertex=null" in source
    assert "tooltip.hidden=true;hoveredPoint=null;drag={x:event.clientX,y:event.clientY}" in source
