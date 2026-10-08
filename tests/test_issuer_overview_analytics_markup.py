import unittest
from pathlib import Path
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


class IssuerOverviewAnalyticsMarkupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_header_has_accessible_in_app_back_and_forward_controls(self):
        self.assertIn('data-action="history-back"', self.source)
        self.assertIn('data-action="history-forward"', self.source)
        self.assertIn('aria-label="Back"', self.source)
        self.assertIn('aria-label="Forward"', self.source)

    def test_issuer_overview_wires_measured_panels(self):
        start = self.source.index("function issuerOverview()")
        end = self.source.index("function ", start + len("function issuerOverview()"))
        overview = self.source[start:end]
        self.assertIn("activeDossier()", overview)
        self.assertIn("dossierForeignChart(flows,rows.map(r=>r.date))", overview)
        self.assertIn("dossierAnalogPanel(d,true)", overview)
        self.assertIn("dossierEvaluationPanel(d,true)", overview)
        self.assertIn("dossierBrokerPanel(d,true)", overview)

    def test_top_broker_contribution_is_scoped_and_ranked_by_absolute_net(self):
        self.assertIn("Top Broker Contribution", self.source)
        self.assertIn("Math.abs(b.net)-Math.abs(a.net)", self.source)
        self.assertIn("total>0?Math.abs(r.net)/total:null", self.source)
        self.assertIn("data-top-broker-contribution", self.source)
        self.assertIn("Kontribusi = |net broker|", self.source)

    def test_overview_has_no_stale_not_run_or_hardcoded_issuer_claims(self):
        start = self.source.index("function issuerOverview()")
        end = self.source.index("function ", start + len("function issuerOverview()"))
        overview = self.source[start:end]
        self.assertNotIn("NOT RUN", overview)
        self.assertNotIn("AADI mulai", overview)
        self.assertNotIn("186 periods", overview)
        self.assertNotIn("412.3", overview)


if __name__ == "__main__":
    unittest.main()
