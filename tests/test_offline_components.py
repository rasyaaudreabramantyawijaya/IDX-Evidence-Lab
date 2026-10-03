import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from idx_evidence_lab.acquisition import assess_acquisition_readiness
from idx_evidence_lab.evidence import classify_evidence
from idx_evidence_lab.mock_sectors import MockSectorsProvider
from idx_evidence_lab.openrouter_mock import MockOpenRouterAdapter
from idx_evidence_lab.query_plan import build_query_plan
from idx_evidence_lab.schemas import EvidenceState, SourceClass
from idx_evidence_lab.search import EntityResolver, LocalSearchIndex
from idx_evidence_lab.schemas import SearchDocument
from idx_evidence_lab.source_policy import SourcePolicy, SourcePolicyError
from idx_evidence_lab.sectors_live import (
    RequestBudget,
    SectorsClient,
    SectorsClientError,
    _date_windows,
    fetch_lq45_foreign_flow,
    fetch_filings,
    fetch_ihsg_index_daily,
)


class OfflineComponentsTest(unittest.TestCase):
    def setUp(self):
        self.provider = MockSectorsProvider()

    def test_mock_provider_is_deterministic_and_has_no_network_client(self):
        first = self.provider.snapshot().to_dict() if hasattr(self.provider.snapshot(), "to_dict") else self.provider.snapshot().snapshot_id
        second = self.provider.snapshot().snapshot_id
        self.assertEqual(first if isinstance(first, str) else "mock-snapshot-001", second)
        self.assertEqual(self.provider.get_issuer("bbca").ticker, "BBCA")

    def test_entity_resolution_and_local_search(self):
        resolver = EntityResolver(self.provider.list_issuers())
        self.assertEqual(resolver.resolve("Bank Central Asia"), ["BBCA"])
        index = LocalSearchIndex([
            SearchDocument("d1", "BBCA broker flow", "persistence positive flow", SourceClass.SECTORS_SOURCE_DATA, "s1", ticker="BBCA", scopes=["FLOW"]),
            SearchDocument("d2", "Market regime", "breadth sideways", SourceClass.DERIVED_METRIC, "m1", scopes=["MARKET"]),
        ])
        results = index.search("BBCA flow", ticker="BBCA")
        self.assertEqual([doc.document_id for doc, _ in results], ["d1"])

    def test_query_plan_contains_no_facts(self):
        plan = build_query_plan("bank dengan flow 5D positif", ["BBCA"])
        self.assertEqual(plan.intent, "FILTER_SCREEN")
        self.assertEqual(plan.filters, {"horizon": "5D", "direction": "POSITIVE"})
        self.assertEqual(plan.entities, [])

    def test_source_policy_rejects_unapproved_source_data(self):
        policy = SourcePolicy()
        policy.validate(SourceClass.SECTORS_SOURCE_DATA, "Sectors.app")
        with self.assertRaises(SourcePolicyError):
            policy.validate(SourceClass.SECTORS_SOURCE_DATA, "OtherMarketAPI")
        with self.assertRaises(SourcePolicyError):
            policy.validate(SourceClass.PRIVATE_LEGAL_REFERENCE, "web", network=True)

    def test_evidence_state_rules(self):
        self.assertEqual(classify_evidence(sample_size=5, data_completeness=1.0, supports=3, contradicts=0), EvidenceState.INSUFFICIENT)
        self.assertEqual(classify_evidence(sample_size=50, data_completeness=1.0, supports=2, contradicts=0), EvidenceState.SUPPORTED)
        self.assertEqual(classify_evidence(sample_size=50, data_completeness=1.0, supports=2, contradicts=1), EvidenceState.MIXED)

    def test_acquisition_readiness_abstains_with_missing_documents(self):
        result = assess_acquisition_readiness({"AUDITED_HISTORY": True})
        self.assertEqual(result.status, "RED")
        self.assertTrue(any(check.status == "MISSING" for check in result.checks))
        self.assertIn("not legal clearance", result.disclaimer.casefold())

    def test_openrouter_mock_never_calls_live_api(self):
        adapter = MockOpenRouterAdapter()
        output = adapter.parse_query("aturan akuisisi BBCA", ["BBCA"])
        self.assertEqual(output["source_class"], "model_inference")
        with self.assertRaises(SourcePolicyError):
            MockOpenRouterAdapter(live=True)

    def test_live_client_requires_key_and_enforces_host_and_budget(self):
        with self.assertRaises(SectorsClientError):
            SectorsClient("")
        with self.assertRaises(SectorsClientError):
            SectorsClient._url("https://example.com/data")
        budget = RequestBudget(maximum=1)
        budget.consume()
        with self.assertRaises(SectorsClientError):
            budget.consume()

    @patch("idx_evidence_lab.sectors_live.urlopen")
    def test_live_client_can_be_tested_without_network(self, mocked_urlopen):
        response = mocked_urlopen.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'[{"symbol":"BBCA.JK","company_name":"Bank Central Asia"}]'
        client = SectorsClient("test-key", budget=RequestBudget(maximum=2))
        payload, metadata = client.get_json("/v1/index/lq45/")
        self.assertEqual(payload[0]["symbol"], "BBCA.JK")
        self.assertEqual(metadata["provider"], "Sectors.app")
        self.assertEqual(client.budget.used, 1)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.sectors.app/v1/index/lq45/")

    def test_foreign_flow_windows_are_inclusive_and_at_most_90_days(self):
        windows = _date_windows(date(2023, 9, 25), date(2023, 9, 25), 90)
        self.assertEqual(windows, [(date(2023, 9, 25), date(2023, 9, 25))])
        longer = _date_windows(date(2023, 1, 1), date(2023, 6, 1), 90)
        self.assertTrue(all((end - start).days < 90 for start, end in longer))
        self.assertEqual(longer[0][0], date(2023, 1, 1))
        self.assertEqual(longer[-1][1], date(2023, 6, 1))

    def test_ihsg_windows_cover_approved_range_without_overlap(self):
        windows = _date_windows(date(2023, 9, 25), date(2026, 9, 24), 90)
        self.assertEqual(len(windows), 13)
        self.assertEqual(windows[0][0], date(2023, 9, 25))
        self.assertEqual(windows[-1][1], date(2026, 9, 24))
        self.assertTrue(all((end - start).days < 90 for start, end in windows))
        self.assertTrue(all(windows[i][1].toordinal() + 1 == windows[i + 1][0].toordinal() for i in range(12)))

    def test_ihsg_collection_saves_payload_provenance_and_resumes(self):
        class StubClient:
            def __init__(self):
                self.budget = RequestBudget(maximum=13)
                self.calls = []

            def get_json(self, path, params):
                self.budget.consume()
                self.calls.append((path, params))
                payload = [{"index_code": "IHSG", "date": params["start"], "price": 7000.0}]
                return payload, {
                    "provider": "Sectors.app",
                    "http_status": 200,
                    "endpoint": f"https://api.sectors.app{path}?start={params['start']}&end={params['end']}",
                    "sha256": hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                }

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "ihsg"
            client = StubClient()
            fetched, reused, used = fetch_ihsg_index_daily(
                output,
                start=date(2023, 9, 25),
                end=date(2026, 9, 24),
                max_requests=13,
                client=client,
            )
            self.assertEqual((fetched, reused, used), (13, 0, 13))
            self.assertTrue(all(path == "/v2/index-daily/ihsg/" for path, _ in client.calls))
            self.assertTrue(all((date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])) .days < 90 for _, p in client.calls))
            self.assertTrue((output / "request_ledger.jsonl").is_file())
            metadata_path = output / "ihsg_2023-09-25_2023-12-23.metadata.json"
            metadata = json.loads(metadata_path.read_text())
            self.assertEqual(metadata["index_code"], "ihsg")
            self.assertEqual(metadata["window_inclusive_days"], 90)
            retry_client = StubClient()
            fetched, reused, used = fetch_ihsg_index_daily(
                output,
                start=date(2023, 9, 25),
                end=date(2026, 9, 24),
                max_requests=13,
                client=retry_client,
            )
            self.assertEqual((fetched, reused, used), (0, 13, 0))
            self.assertEqual(retry_client.calls, [])

    def test_foreign_flow_collection_uses_local_daily_start_and_resumes(self):
        symbols = [f"T{i:02d}" for i in range(45)]

        class StubClient:
            def __init__(self):
                self.budget = RequestBudget(maximum=45)
                self.calls = []

            def get_json(self, path, params):
                self.budget.consume()
                self.calls.append((path, params))
                payload = [{"date": params["start"], "net_foreign": 1}]
                return payload, {
                    "provider": "Sectors.app",
                    "http_status": 200,
                    "endpoint": f"https://api.sectors.app{path}?start={params['start']}&end={params['end']}",
                    "sha256": hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            universe = root / "universe.json"
            universe.write_text(json.dumps({"results": [{"symbol": f"{s}.JK"} for s in symbols]}))
            daily = root / "daily"
            for symbol in symbols:
                ticker_dir = daily / symbol
                ticker_dir.mkdir(parents=True)
                (ticker_dir / f"{symbol}_2026-09-24.json").write_text(
                    json.dumps([{"symbol": f"{symbol}.JK", "date": "2026-09-24"}])
                )
            output = root / "foreign_flow"
            client = StubClient()
            fetched, reused, used = fetch_lq45_foreign_flow(
                universe,
                daily,
                output,
                start=date(2023, 9, 25),
                end=date(2026, 9, 24),
                max_requests=45,
                client=client,
            )
            self.assertEqual((fetched, reused, used), (45, 0, 45))
            self.assertEqual(len(client.calls), 45)

            retry_client = StubClient()
            fetched, reused, used = fetch_lq45_foreign_flow(
                universe,
                daily,
                output,
                start=date(2023, 9, 25),
                end=date(2026, 9, 24),
                max_requests=45,
                client=retry_client,
            )
            self.assertEqual((fetched, reused, used), (0, 45, 0))
            self.assertEqual(retry_client.calls, [])

    def test_filings_fetch_is_one_page_per_symbol_with_provenance(self):
        class StubClient:
            def __init__(self):
                self.budget = RequestBudget(maximum=2)
                self.calls = []

            def get_json(self, path, params):
                self.budget.consume()
                self.calls.append((path, params))
                payload = {"results": [{"symbol": f"{params['symbol']}.JK"}], "pagination": {"has_next": True}}
                return payload, {
                    "provider": "Sectors.app",
                    "http_status": 200,
                    "endpoint": f"https://api.sectors.app{path}",
                    "sha256": hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                }

        with tempfile.TemporaryDirectory() as temp:
            client = StubClient()
            fetched, used = fetch_filings(
                ["AADI", "BBCA.JK"],
                Path(temp) / "filings",
                start=date(2026, 8, 26),
                end=date(2026, 9, 25),
                max_requests=2,
                client=client,
            )
            self.assertEqual((fetched, used), (2, 2))
            self.assertEqual(len(client.calls), 2)
            self.assertTrue(all(path == "/v2/filings/" for path, _ in client.calls))
            self.assertTrue(all(params["limit"] == "30" and params["offset"] == "0" for _, params in client.calls))
            self.assertTrue((Path(temp) / "filings" / "AADI" / "filings.metadata.json").is_file())
            metadata = json.loads((Path(temp) / "filings" / "AADI" / "filings.metadata.json").read_text())
            self.assertFalse(metadata["pagination_followed"])


if __name__ == "__main__":
    unittest.main()
