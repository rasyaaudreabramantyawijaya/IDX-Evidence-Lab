from pathlib import Path
from idx_evidence_lab.studies_verification import verification_for

ROOT=Path(__file__).resolve().parents[1]


def test_measured_reference_manifest_matches_code_and_run():
    for widget in ('custom_engineering','trend_momentum','price_risk'):
        status,scope=verification_for(ROOT,widget)
        assert status=='REFERENCE_VERIFIED'
        assert scope['passed_cases']==scope['reference_cases']
    assert verification_for(ROOT,'factor_exposure')[0]=='NOT_TESTED'


def test_missing_manifest_not_verified(tmp_path):
    assert verification_for(tmp_path,'custom_engineering')==('NOT_TESTED',None)
