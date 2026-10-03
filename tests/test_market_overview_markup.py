import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketOverviewPrototypeTests(unittest.TestCase):
    def test_live_server_has_static_market_data_fallback(self):
        source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
        self.assertIn("fetch('./market-overview-data.json'", source)
        self.assertIn("function marketRsiPanel()", source)
        self.assertIn("data-action=\"market-rsi-period\"", source)
        self.assertIn("function wilderRsi(closes,period)", source)

    def test_forward_pe_snapshot_omits_positive_distribution_chart(self):
        source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
        self.assertNotIn("const peDistribution=", source)
        self.assertNotIn("class=\"pe-distribution\"", source)

    def test_valuation_cards_keep_intrinsic_left_heights_and_forward_panel_matches_the_stack(self):
        source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
        self.assertIn("class=\"market-valuation-pair\"><div class=\"market-valuation-stack\">${monthlyForeignPanel()}${ratioPanel}</div>${pePanel}</div>", source)
        self.assertIn(".market-valuation-pair{grid-column:1/-1;position:relative;display:block;min-width:0", source)
        self.assertIn(".market-valuation-stack{display:grid;width:calc(50% - 6px);grid-template-rows:max-content max-content;align-content:start", source)
        self.assertIn(".market-valuation-pair>.forward-pe-panel{position:absolute;top:0;right:0;bottom:0;width:calc(50% - 6px);align-self:stretch;min-height:0", source)
        self.assertIn(".market-valuation-pair>.forward-pe-panel{position:static;width:auto;min-height:0}", source)
        self.assertIn(".forward-pe-panel .pe-detail-scroll{flex:1;min-height:0;", source)
        self.assertIn("overflow-x:auto;overflow-y:scroll", source)
        self.assertIn("class=\"valuation-compare pe-detail-scroll\" role=\"region\"", source)
        self.assertIn("aria-label=\"Rincian forward P/E semua emiten yang dapat digulir\"", source)
        self.assertNotIn("<details class=\"valuation-compare\"", source)

    def test_market_snapshot_has_verified_daily_series_and_explicit_gaps(self):
        payload = json.loads((ROOT / "docs/prototypes/market-overview-data.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["ihsg"]["data_quality"], "VERIFIED")
        self.assertEqual(payload["ihsg"]["observation_count"], 708)
        self.assertEqual(payload["lq45_index"]["data_quality"], "VERIFIED")
        self.assertEqual(payload["lq45_index"]["observation_count"], 708)
        self.assertEqual(payload["lq45_index"]["coverage_start"], "2023-09-25")
        self.assertEqual(payload["lq45_index"]["coverage_end"], "2026-09-24")
        self.assertEqual(len(payload["lq45_daily"]), 45)
        self.assertTrue(all(item["data_quality"] == "VERIFIED" for item in payload["lq45_daily"].values()))
        self.assertEqual(payload["sectorHeatmap"]["data_quality"], "PARTIAL")

    def test_issuer_tabs_stay_inside_dossier_and_flow_is_ticker_scoped(self):
        source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
        self.assertNotIn('data-page="flow"', source)
        self.assertIn("if(a==='issuer-tab'){issuerTab=b.dataset.tab;page='issuer';dossierReport=false;render()", source)
        self.assertIn('role="tabpanel"', source)
        for tab in ("Overview", "Flow", "Evidence", "Historical Analog", "Event Study", "Outcomes"):
            self.assertIn(f"issuerTab==='{tab}'", source)
        self.assertIn("issuer_daily[ticker]", source)
        self.assertIn("dashboardData.lq45_daily[ticker].series", source)
        payload = json.loads((ROOT / "docs/prototypes/market-overview-data.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["foreign_flow"]["issuer_daily"]), 45)
        self.assertTrue(payload["foreign_flow"]["issuer_daily"]["AADI"])


if __name__ == "__main__":
    unittest.main()
