from idx_evidence_lab.studies_artifacts import StudyArtifactStore


def test_artifacts_are_server_owned_bounded_and_expire(tmp_path):
    now=[0.]
    store=StudyArtifactStore(clock=lambda:now[0],limit=2,ttl=10)
    file=tmp_path/'daily.json';file.write_text('[]')
    data={'selection':{'tickers':['BBCA']},'provenance':{'sources':{'daily':{'BBCA':['daily.json']}}}}
    ref=store.save(tmp_path,data)
    data['selection']['tickers'].append('AADI')
    assert store.get(ref)['selection']['tickers']==['BBCA']
    assert store.get(ref)['studies_sources'][0]['sha256']
    newer=store.save(tmp_path,data)
    newest=store.save(tmp_path,data)
    assert store.get(ref) is None
    assert store.get(newer) and store.get(newest)
    now[0]=11
    assert store.get(newest) is None
