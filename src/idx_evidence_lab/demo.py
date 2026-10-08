"""Tiny offline smoke demo for the package."""

from .providers.mock_sectors import MockSectorsProvider
from .providers.query_plan import build_query_plan
from .core.search import EntityResolver, LocalSearchIndex
from .core.schemas import SearchDocument, SourceClass


def build_demo_index() -> LocalSearchIndex:
    return LocalSearchIndex([
        SearchDocument("page-screener", "Evidence Screener", "filter ticker flow evidence state", SourceClass.PRODUCT_METADATA, "page-screener", scopes=["SCREENER"]),
        SearchDocument("bbca-flow", "BBCA broker flow", "Bank Central Asia broker flow persistence and price response", SourceClass.SECTORS_SOURCE_DATA, "mock-bbca-flow", ticker="BBCA", scopes=["EMITEN", "FLOW"]),
    ])


def smoke() -> dict:
    provider = MockSectorsProvider()
    resolver = EntityResolver(provider.list_issuers())
    plan = build_query_plan("buka broker flow BBCA 5D", [item.ticker for item in provider.list_issuers()])
    results = build_demo_index().search("broker flow BBCA", ticker="BBCA")
    return {
        "resolved": resolver.resolve("Bank Central Asia"),
        "query_plan": plan.to_dict(),
        "result_ids": [item.document_id for item, _ in results],
    }
