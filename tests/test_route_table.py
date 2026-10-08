"""The handler's route tables must stay in sync with the methods and the golden-master coverage."""
import json
from pathlib import Path

from idx_evidence_lab import web_app

GOLDEN = Path(__file__).parent / "golden"


def test_every_route_points_to_an_existing_method():
    handler = web_app.SearchHandler
    for table in (handler.GET_ROUTES, handler.POST_ROUTES):
        for route, name in table.items():
            assert route.startswith("/api/")
            assert callable(getattr(handler, name)), f"{route} -> {name}"


def test_costly_routes_are_real_post_routes():
    assert web_app.COSTLY_POST_ROUTES <= set(web_app.SearchHandler.POST_ROUTES)


def test_every_route_is_exercised_by_the_golden_master():
    seen = set()
    for path in GOLDEN.glob("*.json*"):
        if path.name == "README.md":
            continue
        text = path.read_bytes()
        if path.suffix == ".gz":
            import gzip
            text = gzip.decompress(text)
        seen.add(json.loads(text).get("request", {}).get("path", "").split("?")[0])
    routes = set(web_app.SearchHandler.GET_ROUTES) | set(web_app.SearchHandler.POST_ROUTES)
    assert routes <= seen, sorted(routes - seen)
