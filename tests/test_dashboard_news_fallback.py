"""Latest News survives an unavailable API and a stale static bundle."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html"


def test_static_market_export_includes_source_linked_latest_news():
    spec = importlib.util.spec_from_file_location(
        "market_export", ROOT / "scripts/export_market_overview_static.py"
    )
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    payload = exporter.build_payload()
    news = payload.get("news", {})
    assert news.get("ok") is True
    assert len(news["articles"]) == 6
    assert all(article["source"].startswith("https://") for article in news["articles"])


@pytest.mark.parametrize("api_available", [True, False])
def test_dashboard_uses_api_news_or_static_news_when_api_is_down(api_available):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for browser loader regression")
    source = PROTOTYPE.read_text(encoding="utf-8")
    loader = "async function refreshDashboardData" + source.rsplit(
        "async function refreshDashboardData", 1
    )[1].split("async function loadSectorHeatmap", 1)[0]
    program = """
let dashboardData={loading:false},evtSurfaceFingerprint='',page='test';
const getEvtSurfaceFingerprint=()=>'',render=()=>{},toast=()=>{};
const news=title=>({ok:true,articles:[{title,source:'https://example.org/article'}]});
async function fetch(url){
  if(url==='/api/dashboard-data')return {ok:API_AVAILABLE,status:500,json:async()=>({news:news('API article')})};
  if(url==='./market-overview-data.json')return {ok:true,json:async()=>({news:news('Static article')})};
  return {ok:false,status:404};
}
""".replace("API_AVAILABLE", json.dumps(api_available))
    program += loader + "\nrefreshDashboardData(true).then(()=>console.log(JSON.stringify(dashboardData.news)));"
    result = subprocess.run([node, "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    news = json.loads(result.stdout)
    assert news["articles"][0]["title"] == ("API article" if api_available else "Static article")
