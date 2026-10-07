"""Chronological event study and issuer-specific regime guards."""
from copy import deepcopy
from datetime import date, timedelta
import math
import json
from pathlib import Path

from idx_evidence_lab.screener_analysis import analyze_issuer, analyze_bundle, build_screener_analysis, wilson_interval


def inputs(count=260):
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(count)]
    market = [{"date": day, "price": 100 + i} for i, day in enumerate(days)]
    daily = [{"date": day, "close": 100 + 2*i} for i, day in enumerate(days)]
    flow = [{"date": day, "net": 100 if i in (30, 35, 80, 240, 255) else (-1)**i} for i, day in enumerate(days)]
    return daily, flow, market


def test_next_close_entry_exact_horizons_and_nonoverlap():
    daily, flow, market = inputs()
    result = analyze_issuer("TEST", daily, flow, market)
    events = result["events"]
    assert [e["event_date"] for e in events] == [market[i]["date"] for i in (30, 80, 240)]
    first = events[0]
    assert first["entry_date"] == market[31]["date"]
    assert first["outcomes"]["5"]["exit_date"] == market[36]["date"]
    assert first["outcomes"]["20"]["exit_date"] == market[51]["date"]
    assert math.isclose(first["outcomes"]["20"]["stock_return"], 202/162-1)
    assert result["sample_5d"] == 3 and result["sample_20d"] == 2
    assert result["excluded"]["immature_20d"] == 1
    assert result["hit_rate"] == 1
    assert 0 < result["hit_rate_ci95"][0] < 1


def test_future_changes_do_not_change_past_features_or_event_selection():
    daily, flow, market = inputs()
    original = analyze_issuer("T", daily, flow, market)
    altered = deepcopy(flow)
    altered[200]["net"] = 99999
    changed = analyze_issuer("T", daily, altered, market)
    assert original["events"][:2] == changed["events"][:2]
    truncated = analyze_issuer("T", daily[:100], flow[:100], market[:100])
    assert original["events"][0] == truncated["events"][0]


def test_missing_sessions_and_corporate_action_jumps_not_bridged():
    daily, flow, market = inputs()
    daily.pop(40)
    result = analyze_issuer("T", daily, flow, market)
    assert result["sample_20d"] == 1
    assert result["excluded"]["invalid_20d"] == 1
    daily, flow, market = inputs()
    daily[40]["close"] *= 2
    result = analyze_issuer("T", daily, flow, market)
    assert result["sample_20d"] == 1
    assert result["excluded"]["invalid_20d"] == 1
    # Missing one previous flow session invalidates z, rather than shortening the window.
    daily, flow, market = inputs()
    flow.pop(20)
    assert analyze_issuer("T", daily, flow, market)["events"][0]["event_date"] == market[80]["date"]


def test_empty_constant_flow_and_regime_are_not_fabricated():
    daily, flow, market = inputs()
    for row in flow: row["net"] = 0
    result = analyze_issuer("T", daily, flow, market)
    assert result["flow_strength_z20"] is None
    assert result["sample_20d"] == 0
    assert result["outcome_20d"] is None and result["hit_rate_ci95"] is None
    assert result["regime"]["label"] == "Tren menguat"
    falling = [{**row, "close": 1000-i} for i, row in enumerate(daily)]
    assert analyze_issuer("T", falling, flow, market)["regime"]["label"] == "Tren melemah"
    assert analyze_issuer("T", daily[-100:], flow, market)["regime"]["label"] == "Belum dihitung"
    assert wilson_interval(0, 0) is None
    assert wilson_interval(0, 5)[0] == 0


def test_hit_rate_denominator_and_market_delta_reconcile():
    daily, flow, market = inputs()
    result = analyze_issuer("T", daily, flow, market)
    measured = [e["outcomes"]["20"] for e in result["events"] if "20" in e["outcomes"]]
    assert math.isclose(result["baseline_delta_20d"], sum(e["excess_return"] for e in measured)/len(measured))
    assert math.isclose(result["outcome_20d"]-result["baseline_20d"], result["baseline_delta_20d"])
    assert result["hit_count"] == sum(e["excess_return"] > 0 for e in measured)


def test_zero_volume_path_is_not_a_tradable_outcome():
    daily, flow, market = inputs()
    for row in daily: row['volume'] = 100
    daily[40]['volume'] = 0
    result = analyze_issuer('T', daily, flow, market)
    assert result['sample_20d'] == 1
    assert result['excluded']['invalid_20d'] == 1


def assert_same_up_to_float_noise(published, fresh, path='root'):
    """Exact for structure, strings and ints; floats may differ in the last digits.

    Different numpy/scipy releases (e.g. on Python 3.10 vs 3.13) change float results by ~1e-16,
    which an exact == comparison reports as a stale snapshot.
    """
    if isinstance(published, dict) and isinstance(fresh, dict):
        assert published.keys() == fresh.keys(), path
        for key in published:
            assert_same_up_to_float_noise(published[key], fresh[key], f'{path}/{key}')
    elif isinstance(published, list) and isinstance(fresh, list):
        assert len(published) == len(fresh), path
        for index, (a, b) in enumerate(zip(published, fresh)):
            assert_same_up_to_float_noise(a, b, f'{path}[{index}]')
    elif isinstance(published, float) and isinstance(fresh, float):
        assert math.isclose(published, fresh, rel_tol=1e-9, abs_tol=1e-12), f'{path}: {published!r} != {fresh!r}'
    else:
        assert published == fresh and type(published) is type(fresh), f'{path}: {published!r} != {fresh!r}'


def test_float_noise_helper_tolerates_rounding_but_not_real_differences():
    assert_same_up_to_float_noise({'a': [1.0000000000000002, 'x', None, 3]}, {'a': [1.0, 'x', None, 3]})
    for changed in ({'a': [1.001, 'x', None, 3]}, {'a': [1.0, 'y', None, 3]}, {'a': [1.0, 'x', None, 4]},
                    {'a': [1.0, 'x', None]}, {'b': [1.0, 'x', None, 3]}):
        try:
            assert_same_up_to_float_noise(changed, {'a': [1.0, 'x', None, 3]})
        except AssertionError:
            continue
        raise AssertionError(f'real difference was not detected: {changed}')


def test_published_snapshot_matches_fresh_local_recalculation():
    root = Path(__file__).resolve().parents[1]
    bundle = json.loads((root/'docs/prototypes/market-overview-data.json').read_text())
    fresh = build_screener_analysis(root)
    assert_same_up_to_float_noise(bundle['screener_analysis'], fresh)
    assert fresh['summary']['computed_count'] == 45
    assert len({r['regime']['label'] for r in fresh['rows']}) > 1
    assert sum(fresh['summary']['regimes'].values()) == 45
    assert fresh['issues']  # Retain the known universe-sidecar issue.
    # A partial source is never allowed to quietly manufacture outcomes.
    bundle['foreign_flow']['data_quality'] = 'PARTIAL'
    blocked = analyze_bundle(bundle, root)
    assert blocked['summary']['computed_count'] == 0
    assert all(r['outcome_20d'] is None for r in blocked['rows'])


def test_local_api_serves_real_study_without_external_requests():
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen
    from idx_evidence_lab.web_app import SearchHandler
    server = ThreadingHTTPServer(('127.0.0.1',0),SearchHandler)
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/screener-analysis') as response:
            result = json.load(response)
        assert result['summary']['computed_count'] == 45
        assert result['method']['confidence_interval'].startswith('CI95')
    finally:
        server.shutdown(); worker.join(timeout=2); server.server_close()
