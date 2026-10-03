import hashlib
import json
from pathlib import Path

import pytest

from idx_evidence_lab.broker_archive import load_broker_rankings, rank_window


def test_rank_same_dates_and_both_sides():
    records = {
        'AK': {'2026-09-01': {'bval': 100, 'sval': 20}, '2026-09-02': {'bval': 90, 'sval': 10}},
        'XL': {'2026-09-01': {'bval': 10, 'sval': 80}},
    }
    case = rank_window(records, ['AK', 'XL'], 20)
    assert case['dates'] == ['2026-09-01']  # Missing XL Sep 2 is not zero.
    assert [(r['code'], r['net']) for r in case['rows']] == [('AK', 80), ('XL', -70)]
    assert case['buyers'][0]['code'] == 'AK'
    assert case['sellers'][0]['code'] == 'XL'
    assert sum(r['share_sample_gross'] for r in case['rows']) == pytest.approx(1)
    assert case['rows'][0]['share_sample_gross'] == pytest.approx(120 / 210)


def test_latest_window_and_zero_denominator():
    records = {'AK': {f'2026-09-{n:02d}': {'bval': 0, 'sval': 0} for n in range(1, 7)}}
    assert rank_window(records, ['AK'], 5)['dates'][0] == '2026-09-02'
    case = rank_window(records, ['AK'], 1)
    assert case['rows'][0]['share_sample_gross'] is None
    assert case['buyers'] == case['sellers'] == []
    assert rank_window({}, ['AK'], 1)['sessions'] == 0


def fixture_archive(root, values, corrupt_hash=False):
    base = root / 'data/raw/sectors/cache_lq45'
    base.mkdir(parents=True)
    entries = []
    for i, (buy, sell, net) in enumerate(values):
        raw = json.dumps({'status': 200, 'body': {'broker_code': 'AK', 'start': '2026-09-01', 'end': '2026-09-01',
            'data': [{'date': '2026-09-01', 'summary': [{'symbol': 'AADI.JK', 'bval': buy, 'sval': sell, 'nval': net}]}]}}).encode()
        (base / f'{i}.json').write_bytes(raw)
        entries.append({'category': 'broker_flow', 'file': f'{i}.json', 'http_status': 200,
            'sha256': 'bad' if corrupt_hash else hashlib.sha256(raw).hexdigest()})
    (base / 'cache_manifest.json').write_text(json.dumps({'entries': entries}))


def test_identical_duplicate_counted_once(tmp_path):
    fixture_archive(tmp_path, [(100, 20, 80), (100, 20, 80)])
    result = load_broker_rankings(tmp_path, ['AADI'])['AADI']
    assert result['cases'][0]['rows'][0]['net'] == 80
    assert len(result['cases'][0]['sources']) == 2
    assert result['status'] == 'PARTIAL_ARCHIVE'
    assert all(s['endpoint'] is None for s in result['cases'][0]['sources'])


@pytest.mark.parametrize('values', [[(100, 20, 80), (110, 20, 90)], [(100, 20, 99)], [(-1, 20, -21)]])
def test_conflicting_or_invalid_records_excluded(tmp_path, values):
    fixture_archive(tmp_path, values)
    result = load_broker_rankings(tmp_path, ['AADI'])['AADI']
    assert result['excluded_conflicts'] == 1
    assert result['cases'][0]['rows'] == []


def test_hash_mismatch_excluded(tmp_path):
    fixture_archive(tmp_path, [(100, 20, 80)], corrupt_hash=True)
    result = load_broker_rankings(tmp_path, ['AADI'])['AADI']
    assert result['file_count'] == 0
    assert result['issues']
    assert result['cases'][0]['sessions'] == 0


def test_exported_all_45_integrity():
    root = Path(__file__).resolve().parents[1]
    dossiers = list((root / 'docs/prototypes/issuer-dossiers').glob('*.json'))
    assert len(dossiers) == 45
    for path in dossiers:
        broker = json.loads(path.read_text())['broker']
        assert broker['codes'] == ['AK', 'XL', 'YP', 'ZP']
        for case in broker['cases']:
            assert len(case['rows']) == 4
            assert case['sessions'] == len(case['dates'])
            assert sum(r['share_sample_gross'] for r in case['rows']) == pytest.approx(1)
            assert all(r['net'] == r['buy'] - r['sell'] for r in case['rows'])
            assert case['rows'] == sorted(case['rows'], key=lambda r: (-r['net'], r['code']))
