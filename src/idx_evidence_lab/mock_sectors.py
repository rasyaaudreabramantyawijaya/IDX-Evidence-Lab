"""Deterministic local substitute for Sectors.app during offline development."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Iterable, List, Optional

from .schemas import IssuerRecord, Provenance, SectorsSnapshot, SourceClass


DEFAULT_ISSUERS = (
    IssuerRecord(
        "BBCA", "Bank Central Asia", "Financials", "Banks",
        ["BCA", "Bank Central Asia Tbk"],
        Provenance(SourceClass.SECTORS_SOURCE_DATA, "mock-issuers", "Sectors.app", observed_at="2026-01-02"),
    ),
    IssuerRecord(
        "BBRI", "Bank Rakyat Indonesia", "Financials", "Banks",
        ["BRI", "Bank Rakyat Indonesia Tbk"],
        Provenance(SourceClass.SECTORS_SOURCE_DATA, "mock-issuers", "Sectors.app", observed_at="2026-01-02"),
    ),
    IssuerRecord(
        "TLKM", "Telkom Indonesia", "Infrastructure", "Telecommunication",
        ["Telkom", "Telkom Indonesia Tbk"],
        Provenance(SourceClass.SECTORS_SOURCE_DATA, "mock-issuers", "Sectors.app", observed_at="2026-01-02"),
    ),
)


class MockSectorsProvider:
    """Offline-only provider; it deliberately has no HTTP implementation."""

    provider_name = "Sectors.app"

    def __init__(self, issuers: Iterable[IssuerRecord] = DEFAULT_ISSUERS):
        self._issuers = {item.ticker: item for item in issuers}

    def list_issuers(self) -> List[IssuerRecord]:
        return list(self._issuers.values())

    def get_issuer(self, ticker: str) -> Optional[IssuerRecord]:
        return self._issuers.get(ticker.upper())

    def snapshot(self, snapshot_id: str = "mock-snapshot-001", as_of: str = "2026-01-02") -> SectorsSnapshot:
        records = [
            {
                "ticker": issuer.ticker,
                "name": issuer.name,
                "sector": issuer.sector,
                "subsector": issuer.subsector,
                "price": 100.0 + index * 10,
                "flow_5d": 1.2 - index * 0.2,
            }
            for index, issuer in enumerate(self._issuers.values())
        ]
        return SectorsSnapshot(
            snapshot_id=snapshot_id,
            as_of=as_of,
            records=deepcopy(records),
            source=Provenance(SourceClass.SECTORS_SOURCE_DATA, snapshot_id, self.provider_name, observed_at=as_of),
        )
