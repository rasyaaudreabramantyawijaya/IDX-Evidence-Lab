import json
import io
from urllib.error import HTTPError
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from idx_evidence_lab.openrouter_live import OpenRouterError, OpenRouterSearchAdapter
from idx_evidence_lab.schemas import SourceClass
from idx_evidence_lab.web_app import build_local_index, load_tickers, build_issuer_research, build_source_report


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class OpenRouterSearchTest(unittest.TestCase):
    @patch('idx_evidence_lab.openrouter_live.urlopen')
    def test_rate_limit_is_safe_and_reports_retry_delay(self, mocked_urlopen):
        mocked_urlopen.side_effect=HTTPError('https://openrouter.ai',429,'limit',{'Retry-After':'45'},io.BytesIO(b'{"error":{"metadata":{"provider_name":"ModelRun","raw":"SECRET"}}}'))
        with self.assertRaises(OpenRouterError) as caught:
            OpenRouterSearchAdapter('test-key').interpret('berita akuisisi',['BBCA'])
        self.assertEqual(caught.exception.status_code,429)
        self.assertEqual(caught.exception.retry_after,45)
        self.assertNotIn('SECRET',str(caught.exception))
        self.assertIn('45',str(caught.exception))

    @patch("idx_evidence_lab.openrouter_live.urlopen")
    def test_research_composes_cited_sections_without_sending_private_legal_text(self, mocked_urlopen):
        sections = [
            {"heading": "Temuan", "text": "Proposal tercatat.", "kind": "fact", "source_ids": ["S1"]},
            {"heading": "Batas", "text": "Belum membuktikan pelaksanaan.", "kind": "inference", "source_ids": ["S1"]},
        ]
        mocked_urlopen.return_value = FakeResponse({"choices": [{"message": {"content": json.dumps({"sections": sections})}}]})
        evidence = [{"title": "Filing BBCA", "excerpt": "Proposal HMETD", "source_id": "filing.json",
                     "source_class": SourceClass.SECTORS_SOURCE_DATA.value},
                    {"title": "Privat", "excerpt": "PRIVATE_TEXT", "source_id": "legal.pdf",
                     "source_class": SourceClass.PRIVATE_LEGAL_REFERENCE.value}]
        result = OpenRouterSearchAdapter("test-key").compose_research("BBCA", "HMETD?", evidence)
        self.assertEqual(result["sources"], [{"id": "S1", "source_id": "filing.json"}])
        self.assertEqual(result["source_class"], "model_inference")
        body = json.loads(mocked_urlopen.call_args.args[0].data)
        self.assertNotIn("PRIVATE_TEXT", json.dumps(body))
        self.assertEqual(len(json.loads(body["messages"][1]["content"])["sources"]), 1)

    @patch("idx_evidence_lab.openrouter_live.urlopen")
    def test_research_rejects_fabricated_source_ids(self, mocked_urlopen):
        section = {"heading": "Claim", "text": "Unsupported", "kind": "fact", "source_ids": ["S99"]}
        mocked_urlopen.return_value = FakeResponse({"choices": [{"message": {"content": json.dumps({"sections": [section, section]})}}]})
        evidence = [{"title": "Filing", "excerpt": "Proposal", "source_id": "filing.json",
                     "source_class": SourceClass.SECTORS_SOURCE_DATA.value}]
        with self.assertRaises(OpenRouterError):
            OpenRouterSearchAdapter("test-key").compose_research("BBCA", "HMETD?", evidence)

    @patch("idx_evidence_lab.openrouter_live.urlopen")
    def test_research_without_public_evidence_makes_no_network_request(self, mocked_urlopen):
        with self.assertRaises(OpenRouterError):
            OpenRouterSearchAdapter("test-key").compose_research("BBCA", "HMETD?", [])
        mocked_urlopen.assert_not_called()

    @patch("idx_evidence_lab.openrouter_live.urlopen")
    def test_adapter_sends_constrained_query_and_filters_unknown_tickers(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "intent": "FIND_EVIDENCE",
                "search_query": "BBCA foreign flow",
                "entities": ["BBCA", "FAKE"],
                "needs_clarification": False,
            })}}]
        })
        adapter = OpenRouterSearchAdapter("test-key")
        result = adapter.interpret("cek flow BCA", ["BBCA"])
        self.assertEqual(result["provider"], "OpenRouter")
        self.assertEqual(result["model"], "qwen/qwen3.8-27b:free")
        self.assertEqual(result["source_class"], SourceClass.MODEL_INFERENCE.value)
        self.assertEqual(result["entities"], ["BBCA"])
        request = mocked_urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "qwen/qwen3.8-27b:free")
        self.assertEqual(body["temperature"], 0)
        self.assertNotIn("evidence", body["messages"][1]["content"].casefold())

    def test_adapter_requires_key_without_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                OpenRouterSearchAdapter()

    def test_local_index_indexes_docs_and_only_legal_pdf_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "note.md").write_text("IHSG benchmark example", encoding="utf-8")
            legal = root / "Business & Corporate Law"
            legal.mkdir()
            (legal / "POJK Example.pdf").write_bytes(b"private PDF content must not be read")
            index = build_local_index(root)
            records = index.as_records()
            self.assertEqual(len(records), 2)
            legal_record = next(record for record in records if "POJK" in record["title"])
            self.assertEqual(legal_record["source_class"], SourceClass.PRIVATE_LEGAL_REFERENCE)
            self.assertNotIn("private PDF content", legal_record["text"])

    def test_daily_json_is_indexed_as_readable_summary_not_raw_dump(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            daily = root / "data" / "raw" / "sectors" / "daily" / "BBCA"
            daily.mkdir(parents=True)
            (daily / "BBCA_2026-03-12_2026-03-16.json").write_text(json.dumps([
                {"symbol": "BBCA.JK", "date": "2026-03-12", "close": 6900, "volume": 100},
                {"symbol": "BBCA.JK", "date": "2026-03-16", "close": 6775, "volume": 120},
            ]), encoding="utf-8")
            record = build_local_index(root).as_records()[0]
            self.assertIn("2 observasi", record["text"])
            self.assertIn("2026-03-16: close 6775", record["text"])
            self.assertNotIn('{"symbol"', record["text"])

    def test_tickers_load_only_from_lq45_universe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            universe = root / "data" / "raw" / "sectors"
            universe.mkdir(parents=True)
            (universe / "lq45-universe.json").write_text(json.dumps({"results": [
                {"symbol": "BBCA.JK", "query_values": {"indices": ["LQ45"]}},
                {"symbol": "FAKE.JK", "query_values": {"indices": ["IDX30"]}},
            ]}), encoding="utf-8")
            self.assertEqual(load_tickers(root), ("BBCA",))

    def test_issuer_research_retrieves_ticker_linked_local_news(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            universe = root / "data" / "raw" / "sectors"
            universe.mkdir(parents=True)
            (universe / "lq45-universe.json").write_text(json.dumps({"results": [
                {"symbol": "BBCA.JK", "query_values": {"indices": ["LQ45"]}},
            ]}), encoding="utf-8")
            news = universe / "news"
            news.mkdir()
            (news / "idx_snapshot.json").write_text(json.dumps({"results": [{
                "title": "BBCA considers rights issue",
                "body": "Issuer filing about HMETD proposal",
                "timestamp": "2026-09-20T00:00:00Z",
                "symbols": ["BBCA"],
            }]}), encoding="utf-8")
            index = build_local_index(root)
            result = build_issuer_research(root, "BBCA", "rights issue HMETD", index)
            self.assertEqual(result["retrieval"]["sectors_snapshots"], 1)
            self.assertEqual(result["evidence"][0]["category"], "berita")
            self.assertIn("HMETD", result["evidence"][0]["excerpt"])

    def test_source_report_excludes_metadata_sidecars_and_reports_endpoint_patterns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            daily = root / "data" / "raw" / "sectors" / "daily" / "BBCA"
            daily.mkdir(parents=True)
            (daily / "snapshot.json").write_text("[]", encoding="utf-8")
            (daily / "snapshot.metadata.json").write_text("{}", encoding="utf-8")
            (daily / "_meta.json").write_text("{}", encoding="utf-8")
            report = build_source_report(root)
            self.assertEqual(report["counts"]["daily_snapshots"], 1)
            self.assertIn("/v2/daily/{ticker}/", report["endpoints"]["Daily OHLCV"])


if __name__ == "__main__":
    unittest.main()
