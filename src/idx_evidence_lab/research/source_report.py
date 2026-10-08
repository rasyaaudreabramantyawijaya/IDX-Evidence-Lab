"""Dataset provenance and coverage report behind /api/source-report."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..market.screener_analysis import build_screener_analysis
from ..portfolio.portfolio_factors import build_factor_zoo_payload


def build_source_report(root: Path) -> dict[str, Any]:
    """Describe dataset use, coverage, and local provenance for the in-app PDF."""
    sectors = root / "data" / "raw" / "sectors"
    dashboard_summary: list[dict[str, str]] = []
    bundle_path = root / "docs" / "prototypes" / "market-overview-data.json"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        bundle = {}

    universe = bundle.get("universe", {})
    ihsg = bundle.get("ihsg", {})
    dashboard_summary.append({
        "topic": "Universe LQ45",
        "status": str(universe.get("data_quality", "TIDAK TERSEDIA")),
        "coverage": f"{universe.get('symbol_count', 0)}/{universe.get('expected_count', 45)} emiten",
        "details": "; ".join(universe.get("issues", [])) or "Snapshot universe lokal.",
    })
    dashboard_summary.append({
        "topic": "Sumber IHSG",
        "status": str(ihsg.get("data_quality", "TIDAK TERSEDIA")),
        "coverage": f"{ihsg.get('observation_count', 0)} observasi · {ihsg.get('coverage_start', '—')}–{ihsg.get('coverage_end', '—')}",
        "details": "; ".join(ihsg.get("issues", [])) or f"{ihsg.get('snapshot_count', 0)} snapshot lokal Sectors.app.",
    })

    baseline = bundle.get("signal_baseline", {})
    baseline_case = next((case for case in baseline.get("cases", []) if case.get("cost_bps") == 10), None)
    baseline_interval = baseline_case.get("interval", {}) if baseline_case else {}
    dashboard_summary.append({
        "topic": "Signal vs Market Baseline",
        "status": "UJI HISTORIS · EKSPLORATORIS" if baseline.get("ok") else "BELUM TERSEDIA",
        "coverage": f"{baseline.get('source_coverage_start', '—')}–{baseline.get('source_coverage_end', '—')} · {baseline_case.get('sessions', 0)} return" if baseline_case else "—",
        "details": (f"Aturan close>SMA200 dan SMA50>SMA200, jeda satu sesi, biaya 10 bps; sinyal {baseline_case.get('signal', {}).get('cumulative_return', 0):.1%} vs IHSG {baseline_case.get('market', {}).get('cumulative_return', 0):.1%}; MDD {baseline_case.get('signal', {}).get('max_drawdown', 0):.1%} vs {baseline_case.get('market', {}).get('max_drawdown', 0):.1%}. Interval 95% selisih tahunan {baseline_interval.get('lower', 0):.1%}–{baseline_interval.get('upper', 0):.1%}; melintasi nol, jadi keunggulan belum jelas." if baseline_case else "Artefak hitungan tidak tersedia atau tidak cocok."),
    })

    prices = [float(row["price"]) for row in ihsg.get("series", []) if row.get("price") is not None]
    if len(prices) >= 200:
        latest, sma50, sma200 = prices[-1], sum(prices[-50:]) / 50, sum(prices[-200:]) / 200
        regime = "Tren menguat" if latest > sma200 and sma50 > sma200 else "Tren melemah" if latest < sma200 and sma50 < sma200 else "Tren campuran"
        dashboard_summary.append({
            "topic": "Regime IHSG",
            "status": "DESKRIPTIF",
            "coverage": str(ihsg.get("coverage_end", "—")),
            "details": f"{regime}; close {latest:,.2f}, SMA50 {sma50:,.2f}, SMA200 {sma200:,.2f}. Aturan teknikal deskriptif, bukan prediksi.",
        })
    else:
        dashboard_summary.append({"topic": "Regime IHSG", "status": "DATA TIDAK CUKUP", "coverage": "—", "details": "Memerlukan minimal 200 observasi harian."})

    daily, index_series = bundle.get("lq45_daily", {}), bundle.get("lq45_index", {}).get("series", [])
    index_dates = sorted(row.get("date") for row in index_series if row.get("date"))
    if len(index_dates) >= 2:
        prior_date, current_date = index_dates[-2:]
        changes = []
        for source in daily.values():
            closes = {row.get("date"): float(row["close"]) for row in source.get("series", []) if row.get("close") and float(row["close"]) > 0}
            if prior_date in closes and current_date in closes:
                changes.append(closes[current_date] / closes[prior_date] - 1)
        advancers, decliners = sum(value > 0 for value in changes), sum(value < 0 for value in changes)
        dashboard_summary.append({
            "topic": "Market Breadth LQ45",
            "status": "DESKRIPTIF" if len(changes) >= 32 else "CAKUPAN DI BAWAH 70%",
            "coverage": f"{len(changes)}/45 · {prior_date}–{current_date}",
            "details": f"{advancers} naik · {len(changes) - advancers - decliners} tetap · {decliners} turun. Snapshot universe saat ini, bukan membership historis.",
        })
    else:
        dashboard_summary.append({"topic": "Market Breadth LQ45", "status": "DATA TIDAK CUKUP", "coverage": "—", "details": "Memerlukan dua tanggal indeks dan harga konstituen selaras."})

    valuation = bundle.get("valuation_readiness", {})
    dashboard_summary.append({
        "topic": "Kapitalisasi pasar LQ45",
        "status": "SNAPSHOT",
        "coverage": f"{valuation.get('market_cap_coverage', 0)}/{valuation.get('universe_count', 45)} emiten",
        "details": f"Rp {float(valuation.get('market_cap_idr') or 0) / 1e12:,.1f} triliun; harga laporan dapat berbeda tanggal dari data harian, dan bukan kapitalisasi seluruh IDX.",
    })

    foreign = bundle.get("foreign_flow", {})
    unusual = foreign.get("unusual_foreign_flow", [])
    dashboard_summary.append({
        "topic": "Unusual foreign flow",
        "status": "DESKRIPTIF",
        "coverage": f"{foreign.get('coverage_end', '—')} · {len(unusual)} emiten melewati ambang",
        "details": "Anomali arus asing |Z| ≥ 2 terhadap 20 sesi; bukan broker issuer-level atau rekomendasi.",
    })

    factor_report: dict[str, Any] = {
        "status": "NOT_AVAILABLE",
        "reason": "Factor Zoo tidak dapat dihitung dari snapshot lokal yang tersedia.",
        "issuer_rows": [],
    }
    try:
        factor_payload = build_factor_zoo_payload(root)
        factor_labels = {
            "value": "Value", "quality": "Quality", "momentum": "Momentum",
            "low_volatility": "Low Volatility",
        }
        factor_rows = []
        for record in factor_payload.get("records", []):
            component_gaps = []
            for component_name, component in record.get("components", {}).items():
                if component.get("status") != "AVAILABLE":
                    reason = component.get("reason") or component.get("status") or "Tidak tersedia"
                    component_gaps.append(f"{component_name}: {reason}")
            daily_quality = record.get("data_quality", {})
            factor_rows.append({
                "ticker": record.get("ticker", "—"),
                "company": record.get("company", "—"),
                "peer_group": record.get("peer_group", "—"),
                "company_report_status": daily_quality.get("company_report", "—"),
                "report_price_as_of": record.get("report_as_of") or "—",
                "daily_status": daily_quality.get("daily", "—"),
                "daily_observation_count": daily_quality.get("daily_observation_count", 0),
                "daily_coverage_start": daily_quality.get("daily_coverage_start") or "—",
                "daily_coverage_end": daily_quality.get("daily_coverage_end") or "—",
                "aligned_ihsg_returns": daily_quality.get("aligned_ihsg_returns", 0),
                "factors": {
                    key: {
                        "label": factor_labels[key],
                        "status": record.get("scores", {}).get(key, {}).get("status", "UNAVAILABLE"),
                        "score": record.get("scores", {}).get(key, {}).get("score"),
                    }
                    for key in factor_labels
                },
                "missing_components": component_gaps,
                "daily_issues": daily_quality.get("daily_issues", []),
            })
        factor_report = {
            "status": "AVAILABLE",
            "schema_version": factor_payload.get("schema_version"),
            "formula_version": factor_payload.get("formula_version"),
            "provider": factor_payload.get("provider"),
            "universe": factor_payload.get("universe", {}),
            "as_of": factor_payload.get("as_of", {}),
            "sources": factor_payload.get("sources", {}),
            "method": factor_payload.get("method", {}),
            "coverage": factor_payload.get("coverage", {}),
            "issuer_rows": factor_rows,
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        factor_report["reason"] = f"{type(exc).__name__}: {exc}"

    def response_json_files(folder: Path) -> list[Path]:
        return [
            path for path in folder.rglob("*.json")
            if not path.name.endswith((".metadata.json", "_meta.json"))
            and "collection_summary" not in path.name.casefold()
            and "manifest" not in path.name.casefold()
        ] if folder.exists() else []

    counts = {
        "universe": 1 if (sectors / "lq45-universe.json").exists() else 0,
        "company_reports": len(list((sectors / "company_report").glob("*/company_report.json"))),
        "daily_snapshots": len(response_json_files(sectors / "daily")),
        "index_daily_snapshots": len(response_json_files(sectors / "index_daily")),
        "filing_snapshots": len(response_json_files(sectors / "filings")),
        "foreign_flow_snapshots": len(response_json_files(sectors / "foreign_flow")),
        "corporate_action_snapshots": len(response_json_files(sectors / "corporate_actions")),
        "news_snapshots": len(response_json_files(sectors / "news")),
        "suspension_snapshots": len(response_json_files(sectors / "suspensions")),
        "private_legal_pdfs": len(list((root / "Business & Corporate Law").rglob("*.pdf"))),
    }
    endpoints = {
        "Universe LQ45": "/v2/companies/ (filter index=LQ45)",
        "Daily OHLCV": "/v2/daily/{ticker}/",
        "Indeks harian IHSG & LQ45": "/v2/index-daily/{index_code}/",
        "Laporan perusahaan": "/v2/company/report/{ticker}/",
        "Foreign flow": "/v2/foreign-flow/{ticker}/",
        "Filings": "/v2/filings/?symbol={ticker}&start=...&end=...",
        "Aksi korporasi": "/v2/company/corporate-actions/{ticker}/",
        "Suspensions": "/v2/suspensions/?symbol={ticker}&start=...&end=...",
        "News snapshots": "/v2/news/?extension=idx&symbols=...&start=...&end=...",
    }
    definitions = [
        ("universe", "LQ45 universe", "universe", "Menentukan emiten pada screener, Riset emiten, dan Portfolio Lab.", "Snapshot anggota saat ini; bukan keanggotaan historis."),
        ("daily", "Daily OHLCV", "daily_snapshots", "Return, RSI, tren harga, risiko portofolio, momentum Factor Zoo, dan heatmap sektor.", "Data harian; histori tiap emiten berbeda. AADI mulai 5 Des 2024."),
        ("index_daily", "Indeks IHSG & LQ45", "index_daily_snapshots", "Konteks pasar, benchmark portofolio, Signal vs Market Baseline (regime SMA 50/200), dan surface tail-loss IHSG.", "708 observasi per indeks; membership historis LQ45 tidak direkonstruksi. Baseline regime memakai jeda satu sesi penuh, kas 0%, dan sensitivitas biaya; bukan sinyal terverifikasi untuk trading."),
        ("company_report", "Laporan perusahaan", "company_reports", "Rasio fundamental, coverage forward P/E, dan sumbu Value/Quality Factor Zoo.", "Snapshot laporan; field bervariasi. Tanggal laporan/harga dapat berbeda dari daily."),
        ("foreign_flow", "Foreign flow", "foreign_flow_snapshots", "Konteks transaksi asing harian dan anomali deskriptif Market Overview.", "Histori provider mulai 2 Jan 2025; bukan data intraday atau total semua broker."),
        ("filings", "Filings", "filing_snapshots", "Timeline peristiwa dan bahan retrieval Riset emiten.", "Arsip mengikuti jendela pengambilan; filing bukan bukti dampak harga."),
        ("corporate_actions", "Corporate actions", "corporate_action_snapshots", "Timeline aksi korporasi dan konteks penyesuaian emiten.", "Cakupan mengikuti respons dan snapshot tersimpan."),
        ("suspensions", "Suspensions", "suspension_snapshots", "Riwayat suspensi pada konteks emiten.", "Deskriptif; bukan prediksi suspensi."),
        ("news", "News", "news_snapshots", "Konteks berita berticker pada News Universe dan Riset emiten.", "Jendela query terpilih; bukan arsip berita lengkap."),
    ]
    datasets: list[dict[str, Any]] = []
    snapshot_manifest: list[dict[str, Any]] = []
    for folder_name, label, count_key, usage, limitation in definitions:
        folder = sectors if folder_name == "universe" else sectors / folder_name
        universe_snapshot = sectors / "lq45-universe.json"
        snapshots = [universe_snapshot] if folder_name == "universe" and universe_snapshot.is_file() else response_json_files(folder)
        metadata_rows = []
        endpoint_example = None
        for snapshot in snapshots:
            metadata_candidates = (
                snapshot.with_name(snapshot.stem + ".metadata.json"),
                snapshot.with_name(snapshot.stem + "_meta.json"),
            )
            metadata_path = next((path for path in metadata_candidates if path.is_file()), None)
            metadata: dict[str, Any] = {}
            if metadata_path:
                try:
                    loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata = loaded if isinstance(loaded, dict) else {}
                except (OSError, json.JSONDecodeError):
                    metadata = {}
            endpoint_example = endpoint_example or metadata.get("endpoint")
            ticker = metadata.get("ticker") or metadata.get("symbol") or metadata.get("index_code")
            if not ticker and snapshot.parent != folder:
                ticker = snapshot.parent.name
            start = metadata.get("start") or metadata.get("requested_start") or metadata.get("coverage_start")
            end = metadata.get("end") or metadata.get("requested_end") or metadata.get("coverage_end")
            retrieved = metadata.get("retrieved_at")
            digest = metadata.get("sha256") or metadata.get("snapshot_sha256")
            row = {
                "dataset": label,
                "file": snapshot.relative_to(root).as_posix(),
                "ticker": str(ticker) if ticker else "—",
                "period_start": str(start) if start else "—",
                "period_end": str(end) if end else "—",
                "retrieved_at": str(retrieved) if retrieved else "—",
                "http_status": metadata.get("http_status", "—"),
                "sha256": str(digest) if digest else "—",
            }
            metadata_rows.append(row)
            snapshot_manifest.append(row)
        starts = [row["period_start"] for row in metadata_rows if row["period_start"] != "—"]
        ends = [row["period_end"] for row in metadata_rows if row["period_end"] != "—"]
        latest = max((row["retrieved_at"] for row in metadata_rows if row["retrieved_at"] != "—"), default="—")
        tickers = {row["ticker"] for row in metadata_rows if row["ticker"] != "—"}
        if folder_name == "universe" and snapshots:
            try:
                universe_payload = json.loads(snapshots[0].read_text(encoding="utf-8"))
                universe_rows = universe_payload.get("results", []) if isinstance(universe_payload, dict) else universe_payload
                if isinstance(universe_rows, list):
                    tickers.update(str(item.get("symbol") or item.get("ticker")) for item in universe_rows if isinstance(item, dict) and (item.get("symbol") or item.get("ticker")))
            except (OSError, json.JSONDecodeError):
                pass
        endpoint_key = {"LQ45 universe": "Universe LQ45", "Indeks IHSG & LQ45": "Indeks harian IHSG & LQ45"}.get(label, label)
        datasets.append({
            "name": label,
            "status": "TERSEDIA" if snapshots else "TIDAK TERSEDIA",
            "snapshot_count": counts[count_key],
            "entity_count": len(tickers),
            "coverage_start": min(starts, default="—"),
            "coverage_end": max(ends, default="—"),
            "latest_retrieved_at": latest,
            "hash_count": sum(row["sha256"] != "—" for row in metadata_rows),
            "endpoint": str(endpoint_example or endpoints.get(endpoint_key, "—")),
            "used_for": usage,
            "limitations": limitation,
        })
    datasets.extend([
        {"name": "Broker activity per emiten", "status": "BELUM TERSEDIA", "snapshot_count": 0, "entity_count": 0, "coverage_start": "—", "coverage_end": "—", "latest_retrieved_at": "—", "hash_count": 0, "endpoint": "—", "used_for": "Belum dipakai sebagai metrik issuer-level.", "limitations": "Arsip empat broker tidak mewakili cakupan transaksi seluruh emiten LQ45."},
        {"name": "PDF hukum lokal", "status": "KOLEKSI LOKAL", "snapshot_count": counts["private_legal_pdfs"], "entity_count": 0, "coverage_start": "—", "coverage_end": "—", "latest_retrieved_at": "—", "hash_count": 0, "endpoint": "Koleksi manual lokal · bukan API Sectors.app", "used_for": "Rujukan dokumen pada Riset emiten; tidak menjadi fakta pasar.", "limitations": "Status berlaku dan relevansi dokumen memerlukan review manusia."},
    ])
    verified_hashes = sum(row["sha256"] != "—" for row in snapshot_manifest)
    return {
        "track": "Sectors Hackathon 2026 · Track 03 Market Intelligence",
        "provider": "Sectors.app",
        "local_root": "data/raw/sectors/",
        "counts": counts,
        "endpoints": endpoints,
        "datasets": datasets,
        "dashboard_summary": dashboard_summary,
        "factor_report": factor_report,
        "screener_analysis": build_screener_analysis(root),
        "snapshot_manifest": snapshot_manifest,
        "provenance_summary": {"snapshot_files": len(snapshot_manifest), "sha256_records": verified_hashes},
        "external_source_policy": "Semua snapshot pasar dan emiten berasal dari Sectors.app v2. Tidak ada API data pasar alternatif.",
        "legal_corpus_policy": "PDF hukum adalah koleksi lokal privat yang terpisah dari Sectors.app; keberlakuan dan applicability belum dipastikan.",
        "storage_note": "Sidecar metadata lokal mencatat endpoint, jendela request, waktu pengambilan, status HTTP, dan SHA-256 bila tersedia.",
        "limits": [
            "Cakupan mengikuti snapshot yang berhasil disimpan dan universe LQ45 saat ini; keanggotaan indeks historis tidak direkonstruksi.",
            "Broker activity issuer-level belum tersedia; arsip empat broker tidak dipakai sebagai pengganti data seluruh LQ45.",
            "News hanya mencakup jendela query yang dipilih. Foreign flow adalah harian dan histori provider mulai 2 Jan 2025.",
            "Daftar input dan snapshot tidak berarti fitur sudah dihitung atau divalidasi untuk keputusan investasi.",
        ],
    }
