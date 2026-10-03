import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from idx_evidence_lab import market_data
from idx_evidence_lab.market_data import load_ihsg_snapshot, load_index_daily_snapshot, load_issuer_daily, load_local_news, load_lq45_universe


ROOT = Path(__file__).resolve().parents[1]


class LocalMarketDataTest(unittest.TestCase):
    def _write_sector_report(self, root, ticker, sector="Financials", *, valid_hash=True, indices=None):
        folder = root / "data/raw/sectors/company_report" / ticker
        folder.mkdir(parents=True, exist_ok=True)
        snapshot = folder / "company_report.json"
        payload = {
            "symbol": ticker + ".JK",
            "company_name": ticker,
            "overview": {"sector": sector, "indices": indices or ["LQ45"]},
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        snapshot.write_bytes(raw)
        metadata = {
            "provider": "Sectors.app", "endpoint": f"https://api.sectors.app/v2/company/report/{ticker}/",
            "http_status": 200, "symbol": ticker,
            "snapshot_sha256": hashlib.sha256(raw).hexdigest() if valid_hash else "bad-hash",
        }
        snapshot.with_name("company_report.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def _write_sector_daily(self, root, ticker, rows, *, valid_hash=True):
        folder = root / "data/raw/sectors/daily" / ticker
        folder.mkdir(parents=True, exist_ok=True)
        snapshot = folder / f"{ticker}_2026-09-23_2026-09-24.json"
        raw = json.dumps(rows, separators=(",", ":")).encode()
        snapshot.write_bytes(raw)
        metadata = {
            "provider": "Sectors.app", "endpoint": f"/v2/daily/{ticker}/", "ticker": ticker,
            "start": "2026-09-23", "end": "2026-09-24", "retrieved_at": "2026-09-24T12:00:00",
            "http_status": 200, "observations_count": len(rows),
            "sha256": hashlib.sha256(raw).hexdigest() if valid_hash else "bad-hash",
        }
        snapshot.with_name(snapshot.stem + "_meta.json").write_text(json.dumps(metadata), encoding="utf-8")

    @staticmethod
    def _write_news_snapshot(root, name, rows, *, valid_hash=True, provider="Sectors.app"):
        folder = root / "data/raw/sectors/news"
        folder.mkdir(parents=True, exist_ok=True)
        snapshot = folder / name
        raw = json.dumps({"results": rows}, separators=(",", ":")).encode()
        snapshot.write_bytes(raw)
        metadata = {
            "provider": provider,
            "endpoint": "https://api.sectors.app/v2/news/?extension=idx",
            "http_status": 200,
            "extension": "idx",
            "date_end": "2026-09-24",
            "retrieved_at": "2026-09-24T12:00:00",
            "snapshot_sha256": hashlib.sha256(raw).hexdigest() if valid_hash else "bad-hash",
        }
        snapshot.with_suffix(".metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    @staticmethod
    def _daily_rows(ticker, closes):
        return [
            {"symbol": ticker + ".JK", "date": day, "close": close, "open": close, "high": close, "low": close, "volume": 100}
            for day, close in zip(("2026-09-23", "2026-09-24"), closes)
        ]

    def test_sector_heatmap_uses_equal_weighted_returns_on_one_shared_date_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_report(root, "BBCA")
            self._write_sector_report(root, "BBRI")
            self._write_sector_daily(root, "BBCA", self._daily_rows("BBCA", (100, 110)))
            self._write_sector_daily(root, "BBRI", self._daily_rows("BBRI", (200, 210)))

            result = market_data.load_sector_heatmap(root)

        financials = next(row for row in result["sectors"] if row["sector"] == "Financials")
        self.assertAlmostEqual(financials["return_pct"], 7.5)
        self.assertEqual(financials["as_of"], "2026-09-24")
        self.assertEqual(financials["previous_date"], "2026-09-23")
        self.assertEqual(financials["observation_count"], 2)
        self.assertEqual(financials["coverage_pct"], 1.0)
        self.assertEqual(financials["data_quality"], "VERIFIED")
        self.assertIn("equal-weighted", result["methodology"])

    def test_sector_heatmap_marks_coverage_below_seventy_percent_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for ticker in ("BBCA", "BBRI", "BBNI"):
                self._write_sector_report(root, ticker)
            for ticker, closes in (("BBCA", (100, 110)), ("BBRI", (200, 220))):
                self._write_sector_daily(root, ticker, self._daily_rows(ticker, closes))

            result = market_data.load_sector_heatmap(root)

        financials = next(row for row in result["sectors"] if row["sector"] == "Financials")
        self.assertIsNone(financials["return_pct"])
        self.assertEqual(financials["data_quality"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(financials["coverage_pct"], 2 / 3)

    def test_sector_heatmap_requires_two_constituents_with_aligned_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_report(root, "BBCA")
            self._write_sector_report(root, "BBRI")
            self._write_sector_daily(root, "BBCA", self._daily_rows("BBCA", (100, 110)))
            # BBRI has only the as-of observation, so its return cannot use a mismatched date pair.
            self._write_sector_daily(root, "BBRI", self._daily_rows("BBRI", (200, 220))[1:])

            result = market_data.load_sector_heatmap(root)

        financials = next(row for row in result["sectors"] if row["sector"] == "Financials")
        self.assertIsNone(financials["return_pct"])
        self.assertEqual(financials["observation_count"], 1)
        self.assertEqual(financials["data_quality"], "INSUFFICIENT_EVIDENCE")

    def test_single_constituent_healthcare_is_shown_as_partial_issuer_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_report(root, "KLBF", sector="Healthcare")
            self._write_sector_daily(root, "KLBF", self._daily_rows("KLBF", (100, 105)))

            result = market_data.load_sector_heatmap(root)

        healthcare = next(row for row in result["sectors"] if row["sector"] == "Healthcare")
        self.assertAlmostEqual(healthcare["return_pct"], 5.0)
        self.assertEqual(healthcare["data_quality"], "PARTIAL")
        self.assertEqual(healthcare["member_tickers"], ["KLBF"])
        self.assertIn("single-issuer", healthcare["issues"][0])

    def test_sector_heatmap_includes_daily_equal_weighted_returns_for_month_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_report(root, "BBCA")
            self._write_sector_report(root, "BBRI")
            for ticker, closes in (("BBCA", (100, 110, 121)), ("BBRI", (200, 180, 198))):
                rows = [
                    {"symbol": ticker + ".JK", "date": day, "close": close, "open": close, "high": close, "low": close, "volume": 100}
                    for day, close in zip(("2026-09-22", "2026-09-23", "2026-09-24"), closes)
                ]
                self._write_sector_daily(root, ticker, rows)

            result = market_data.load_sector_heatmap(root)

        monthly = result["monthly_heatmap"]
        financials = next(row for row in monthly["sectors"] if row["sector"] == "Financials")
        self.assertEqual(monthly["window_calendar_days"], 30)
        self.assertEqual(monthly["dates"], ["2026-09-22", "2026-09-23", "2026-09-24"])
        self.assertIsNone(financials["cells"][0]["return_pct"])
        self.assertAlmostEqual(financials["cells"][1]["return_pct"], 0.0)
        self.assertAlmostEqual(financials["cells"][2]["return_pct"], 10.0)
        self.assertTrue(all(cell["data_quality"] == "VERIFIED" for cell in financials["cells"][1:]))
        self.assertEqual(financials["cells"][1]["observed_tickers"], ["BBCA", "BBRI"])

    def test_sector_heatmap_rejects_unverified_report_mapping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_report(root, "BBCA", valid_hash=False)
            self._write_sector_report(root, "BBRI")
            self._write_sector_daily(root, "BBCA", self._daily_rows("BBCA", (100, 110)))
            self._write_sector_daily(root, "BBRI", self._daily_rows("BBRI", (200, 220)))

            result = market_data.load_sector_heatmap(root)

        self.assertTrue(any("hash" in issue.casefold() for issue in result["issues"]))
        self.assertFalse(any(row["sector"] == "Financials" and row["return_pct"] is not None for row in result["sectors"]))

    def test_sector_heatmap_keeps_other_sectors_when_one_has_invalid_price(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for ticker, sector in (("BBCA", "Financials"), ("BBRI", "Financials"), ("TLKM", "Telecommunications"), ("EXCL", "Telecommunications")):
                self._write_sector_report(root, ticker, sector)
            self._write_sector_daily(root, "BBCA", self._daily_rows("BBCA", (100, 110)))
            self._write_sector_daily(root, "BBRI", self._daily_rows("BBRI", (200, 210)))
            self._write_sector_daily(root, "TLKM", self._daily_rows("TLKM", (100, -1)))
            self._write_sector_daily(root, "EXCL", self._daily_rows("EXCL", (200, 220)))

            result = market_data.load_sector_heatmap(root)

        by_sector = {row["sector"]: row for row in result["sectors"]}
        self.assertAlmostEqual(by_sector["Financials"]["return_pct"], 7.5)
        self.assertIsNone(by_sector["Telecommunications"]["return_pct"])
        self.assertTrue(any("invalid" in issue.casefold() for issue in by_sector["Telecommunications"]["issues"]))

    def test_issuer_daily_loader_returns_verified_prices(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "data/raw/sectors/daily/BBCA"
            folder.mkdir(parents=True)
            snapshot = folder / "BBCA_2026-09-23_2026-09-24.json"
            raw = b'[{"symbol":"BBCA.JK","date":"2026-09-23","close":6300,"open":6200,"high":6300,"low":6200,"volume":100},{"symbol":"BBCA.JK","date":"2026-09-24","close":6225,"open":6250,"high":6275,"low":6225,"volume":90}]'
            snapshot.write_bytes(raw)
            metadata = {
                "provider": "Sectors.app", "endpoint": "/v2/daily/BBCA/", "ticker": "BBCA",
                "start": "2026-09-23", "end": "2026-09-24", "retrieved_at": "2026-09-24T12:00:00",
                "http_status": 200, "observations_count": 2, "sha256": hashlib.sha256(raw).hexdigest(),
            }
            snapshot.with_name(snapshot.stem + "_meta.json").write_text(json.dumps(metadata), encoding="utf-8")

            result = load_issuer_daily(root, "BBCA")

        self.assertEqual(result["data_quality"], "VERIFIED")
        self.assertEqual(result["ticker"], "BBCA")
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(result["coverage_end"], "2026-09-24")
        self.assertEqual(result["series"][-1]["close"], 6225)
        self.assertEqual(result["issues"], [])

    def test_issuer_daily_loader_preserves_verified_market_cap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_sector_daily(root, "BBCA", [{
                "symbol": "BBCA.JK", "date": "2026-09-24", "close": 6225,
                "volume": 90, "market_cap": 900_000_000,
            }])
            result = load_issuer_daily(root, "BBCA")
        self.assertEqual(result["data_quality"], "VERIFIED")
        self.assertEqual(result["series"][0]["market_cap"], 900_000_000)

    def test_issuer_daily_loader_rejects_records_for_another_ticker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "data/raw/sectors/daily/BBCA"
            folder.mkdir(parents=True)
            snapshot = folder / "BBCA_2026-09-24_2026-09-24.json"
            raw = b'[{"symbol":"BBRI.JK","date":"2026-09-24","close":5000}]'
            snapshot.write_bytes(raw)
            metadata = {
                "provider": "Sectors.app", "endpoint": "/v2/daily/BBCA/", "ticker": "BBCA",
                "start": "2026-09-24", "end": "2026-09-24", "retrieved_at": "2026-09-24T12:00:00",
                "http_status": 200, "observations_count": 1, "sha256": hashlib.sha256(raw).hexdigest(),
            }
            snapshot.with_name(snapshot.stem + "_meta.json").write_text(json.dumps(metadata), encoding="utf-8")

            result = load_issuer_daily(root, "BBCA")

        self.assertEqual(result["data_quality"], "PARTIAL")
        self.assertEqual(result["observation_count"], 0)
        self.assertTrue(any("symbol" in issue.casefold() for issue in result["issues"]))

    def test_saved_ihsg_series_is_available_and_provenance_verified(self):
        result = load_ihsg_snapshot(ROOT)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "Sectors.app")
        self.assertEqual(result["data_quality"], "VERIFIED")
        self.assertGreaterEqual(result["snapshot_count"], 1)
        self.assertEqual(result["observation_count"], len(result["series"]))
        self.assertEqual(result["coverage_end"], result["series"][-1]["date"])
        self.assertIsNotNone(result["daily_change_pct"])

    def test_saved_lq45_index_series_is_available_and_provenance_verified(self):
        result = load_index_daily_snapshot(ROOT, "lq45")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data_quality"], "VERIFIED")
        self.assertEqual(result["endpoint"], "/v2/index-daily/lq45/")
        self.assertEqual(result["observation_count"], 708)
        self.assertEqual(result["coverage_start"], "2023-09-25")
        self.assertEqual(result["coverage_end"], "2026-09-24")
        self.assertEqual(result["series"][-1]["index_code"], "LQ45")

    def test_index_daily_loader_flags_metadata_code_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "data/raw/sectors/index_daily/lq45"
            folder.mkdir(parents=True)
            snapshot = folder / "lq45_2026-09-24_2026-09-24.json"
            raw = b'[{"index_code":"IHSG","date":"2026-09-24","price":6298.607}]'
            snapshot.write_bytes(raw)
            snapshot.with_name(snapshot.stem + ".metadata.json").write_text(json.dumps({
                "provider": "Sectors.app", "endpoint": "https://api.sectors.app/v2/index-daily/lq45/",
                "http_status": 200, "index_code": "lq45", "retrieved_at": "2026-09-24T12:00:00Z",
                "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            }), encoding="utf-8")
            result = load_index_daily_snapshot(root, "lq45")
        self.assertEqual(result["data_quality"], "MISSING")
        self.assertEqual(result["observation_count"], 0)
        self.assertTrue(any("index code" in issue.casefold() for issue in result["issues"]))

    def test_saved_lq45_universe_is_exposed_without_masking_hash_issue(self):
        result = load_lq45_universe(ROOT)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "Sectors.app")
        self.assertEqual(len(result["symbols"]), 45)
        # Current metadata hash does not match the saved JSON bytes; preserve that warning.
        self.assertIn(result["data_quality"], {"PARTIAL", "VERIFIED"})
        if result["data_quality"] == "PARTIAL":
            self.assertTrue(result["issues"])

    def test_local_news_snapshots_are_source_linked(self):
        result = load_local_news(ROOT)
        self.assertEqual(result["provider"], "Sectors.app")
        self.assertTrue(result["ok"])
        self.assertTrue(result["articles"])
        self.assertTrue(all(item["source"].startswith("https://") for item in result["articles"]))

    def test_news_universe_returns_full_source_backed_fields_and_stable_id(self):
        article = {"title": "Issuer update", "body": "Important disclosure", "source": "https://news.example/story", "timestamp": "2026-09-24T10:00:00", "sector": "banking", "sub_sector": ["banks"], "symbols": ["BBCA.JK"], "tags": ["results"], "dimension": {"financials": 1}}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_news_snapshot(root, "idx_lq45_day.json", [article])
            first = market_data.load_news_universe(root)
            second = market_data.load_news_universe(root)
        row = first["articles"][0]
        self.assertEqual(row["news_id"], second["articles"][0]["news_id"])
        self.assertEqual(row["body"], "Important disclosure")
        self.assertEqual(row["symbols"], ["BBCA"])
        self.assertEqual(row["sub_sector"], ["banks"])
        self.assertEqual(row["dimensions"], {"financials": 1})
        self.assertEqual(row["data_quality"], "VERIFIED")
        self.assertEqual(row["source_file"], "data/raw/sectors/news/idx_lq45_day.json")

    def test_news_universe_excludes_unverified_snapshot_rows(self):
        article = {"title": "Untrusted", "source": "https://news.example/story", "timestamp": "2026-09-24T10:00:00"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_news_snapshot(root, "idx_lq45_bad.json", [article], valid_hash=False)
            self._write_news_snapshot(root, "idx_lq45_wrong-provider.json", [article], provider="Other")
            result = market_data.load_news_universe(root)
        self.assertEqual(result["articles"], [])
        self.assertEqual(result["data_quality"], "MISSING")
        self.assertTrue(result["issues"])

    def test_news_universe_handles_missing_optional_fields_and_caps_body(self):
        article = {"title": "Long story", "body": "x" * 6500, "source": "https://news.example/story", "timestamp": "2026-09-24T10:00:00"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_news_snapshot(root, "idx_lq45_optional.json", [article])
            result = market_data.load_news_universe(root)
        row = result["articles"][0]
        self.assertEqual(len(row["body"]), 6000)
        self.assertEqual(row["symbols"], [])
        self.assertEqual(row["tags"], [])
        self.assertEqual(row["dimensions"], {})

    def test_news_universe_deduplicates_overlapping_snapshots_and_keeps_provenance(self):
        article = {"title": "Same story", "body": "Details", "source": "https://news.example/story", "timestamp": "2026-09-24T10:00:00"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_news_snapshot(root, "idx_lq45_a.json", [article])
            self._write_news_snapshot(root, "idx_lq45_b.json", [article])
            result = market_data.load_news_universe(root)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(len(result["articles"][0]["source_files"]), 2)

    def test_news_universe_does_not_fetch_article_links(self):
        article = {"title": "Local story", "source": "https://news.example/story", "timestamp": "2026-09-24T10:00:00"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_news_snapshot(root, "idx_lq45_local.json", [article])
            with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network request")):
                result = market_data.load_news_universe(root)
        self.assertEqual(len(result["articles"]), 1)


if __name__ == "__main__":
    unittest.main()
