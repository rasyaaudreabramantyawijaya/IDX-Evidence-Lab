import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from idx_evidence_lab import web_app
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


class NewsUniverseMarkupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_news_universe_is_a_market_destination_and_keeps_market_overview(self):
        self.assertIn('data-page="news-universe"', self.source)
        self.assertIn("Market overview", self.source)
        self.assertIn("News Universe", self.source)
        self.assertIn("news-universe", self.source[self.source.index("const views="):])

    def test_news_page_has_pending_briefing_expandable_list_and_local_filters(self):
        self.assertIn("Top 5 · You Must Know in 10 Minutes", self.source)
        self.assertIn("PENDING_MODEL_APPROVAL", self.source)
        self.assertIn("Tampilkan semua", self.source)
        self.assertIn("newsFilters", self.source)
        self.assertIn("sector", self.source)
        self.assertIn("symbols", self.source)
        self.assertIn("coverage_end", self.source)

    def test_ui_does_not_call_external_search_or_openrouter(self):
        self.assertNotIn("openrouter.ai", self.source.casefold())
        self.assertNotIn("google.com/search", self.source.casefold())
        self.assertIn("fetch('/api/news-universe'", self.source)

    def test_news_universe_route_returns_local_data_without_external_provider_call(self):
        expected = {"provider": "Sectors.app", "data_quality": "PARTIAL", "snapshot_count": 3, "coverage_end": "2026-09-24", "articles": [], "issues": []}
        with patch.object(web_app, "ROOT", Path("/local/test/root")), patch.object(
            web_app, "load_news_universe", return_value=expected
        ) as loader:
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/news-universe") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(payload, expected)
                loader.assert_called_once_with(Path("/local/test/root"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_story_selection_synchronizes_selected_detail_and_graph_id(self):
        self.assertIn("function selectNewsStory(newsId)", self.source)
        self.assertIn("selectedNewsId=newsId", self.source)
        self.assertIn("newsGraph.news_id=newsId", self.source)
        self.assertIn("newsGraph.status='PENDING_MODEL_APPROVAL'", self.source)
        self.assertIn("newsGraph.edges=[]", self.source)
        self.assertIn("selectNewsStory(b.dataset.newsId)", self.source)
        self.assertIn("graph.dataset.graphNewsId=newsGraph.news_id", self.source)

    def test_missing_body_is_disclosed_and_graph_has_no_generated_causal_branches(self):
        self.assertIn("Isi artikel tidak tersedia pada snapshot lokal.", self.source)
        self.assertIn("PENDING_MODEL_APPROVAL", self.source)
        self.assertIn("newsGraph.edges=[]", self.source)

    def test_graph_renderer_has_3d_controls_limits_and_accessible_tree(self):
        for contract in ("function drawNewsGraph(canvas,graph)", "GRAPH_NODE_LIMIT=1000", "rotateX", "rotateY", "graphOffsetX", "graphOffsetY", "news-zoom-in", "news-zoom-out", "news-graph-reset", "news-pan-toggle", "Accessible cause-map tree", "requestAnimationFrame", "1,000", "drawNewsGraph(canvas,newsGraph)"):
            self.assertIn(contract, self.source)


if __name__ == "__main__":
    unittest.main()
