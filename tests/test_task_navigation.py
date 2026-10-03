"""User intentions must become safe, executable workspace state."""
import pytest
from idx_evidence_lab import web_app


@pytest.mark.parametrize('query,page,mode,topic',[
    ('BBCA','issuer','',''),
    ('Ingin mencari saham volatilitas rendah','screener','low_volatility',''),
    ('Cari saham undervalue','screener','value',''),
    ('Ingin mengalokasikan portofolio BBCA BMRI','portfolio-lab','',''),
    ('Berita saham tentang BBCA','news-universe','',''),
    ('Berita seputar akuisisi','news-universe','','acquisition'),
    ('Studies feature engineering risiko BBCA','studies','',''),
])
def test_direct_workspace_routing(query,page,mode,topic):
    build=getattr(web_app,'build_navigation',lambda *_args,**_kwargs: {})
    plan=build(query,['BBCA','BMRI'])
    assert plan.get('page') == page
    assert plan.get('screen_mode','') == mode
    assert plan.get('news_topic','') == topic
    if 'BBCA' in query: assert 'BBCA' in plan['tickers']


def test_studies_only_selects_allowed_features():
    build=getattr(web_app,'build_navigation',lambda *_args,**_kwargs: {})
    plan=build('Studies risiko BBCA',['BBCA'],{'page':'studies','widgets':['execute_shell','price_risk']})
    assert plan.get('widgets') == ['price_risk','evidence_trace']


def test_model_cannot_navigate_to_arbitrary_url_or_unknown_ticker():
    build=getattr(web_app,'build_navigation',lambda *_args,**_kwargs: {})
    plan=build('berita BBCA',['BBCA'],{'page':'https://evil.test','tickers':['FAKE']})
    assert plan.get('page') == 'news-universe'
    assert plan['tickers'] == ['BBCA']


def test_malformed_model_fields_fall_back_without_crashing():
    plan=web_app.build_navigation('berita BBCA',['BBCA'],{'page':[],'screen_mode':{},'news_topic':[],'widgets':None,'tickers':None})
    assert plan['page']=='news-universe'
    assert plan['tickers']==['BBCA']
