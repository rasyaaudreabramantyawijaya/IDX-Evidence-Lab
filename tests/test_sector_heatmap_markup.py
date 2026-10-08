import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
import json

from idx_evidence_lab import web_app
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


class SectorHeatmapMarkupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_market_overview_adds_heatmap_without_removing_existing_sections(self):
        start = self.source.index("function market()")
        end = self.source.index("function ", start + len("function market()"))
        market = self.source[start:end]
        self.assertIn("sectorHeatmapPanel", self.source)
        self.assertIn("market:()=>{loadSectorHeatmap();return market()+sectorHeatmapPanel()}", self.source)
        self.assertIn("Last IHSG", market)
        self.assertIn("Breadth & regime", market)
        self.assertIn("Provenance IHSG", market)
        self.assertIn("Return harian equal-weighted", self.source)

    def test_heatmap_displays_coverage_and_unavailable_without_zero_fallback(self):
        start = self.source.index("function sectorHeatmapPanel")
        end = self.source.index("async function loadSectorHeatmap", start)
        panel = self.source[start:end]
        self.assertIn("monthly_heatmap", panel)
        self.assertIn("window_calendar_days", panel)
        self.assertIn("observation_count", panel)
        self.assertIn("INSUFFICIENT_EVIDENCE", panel)
        self.assertIn("start_date", panel)
        self.assertIn("return_pct", panel)
        self.assertNotIn(" title=", panel)
        self.assertIn("data-sector-row", panel)
        self.assertIn("data-sector-day", panel)
        self.assertIn("sector-heatmap-tooltip", panel)
        self.assertIn("pointerover", panel)
        self.assertIn("mountSectorHeatmap();mountIhsgEvtSurface()", self.source)
        self.assertIn("member_tickers", panel)
        self.assertNotIn("Number(item.return_pct||0)", panel)

    def test_read_only_route_returns_local_aggregation(self):
        expected = {"provider": "Sectors.app local snapshots", "data_quality": "PARTIAL", "sectors": []}
        with patch.object(web_app, "ROOT", Path("/local/test/root")), patch.object(
            web_app, "load_sector_heatmap", return_value=expected
        ) as loader:
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/sector-heatmap") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(payload, expected)
                loader.assert_called_once_with(Path("/local/test/root"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
