"""Preliminary acquisition readiness checklist, not a legal opinion."""

from __future__ import annotations

from typing import Mapping, Sequence

from .schemas import AcquisitionCheck, AcquisitionReadiness


CHECK_LABELS = {
    "AUDITED_HISTORY": "Required audited financial history is present",
    "OWNERSHIP_STRUCTURE": "Ownership and control structure is documented",
    "MATERIALITY": "Material transaction applicability was assessed",
    "AFFILIATE_CONFLICT": "Affiliate/conflict-of-interest applicability was assessed",
    "APPROVALS": "Required shareholder/regulator approvals are evidenced",
    "DISCLOSURE": "Public disclosure documents are complete",
    "SECTOR_LICENSE": "Sector licences and regulatory dependencies are evidenced",
    "LIABILITIES": "Debt, liens, litigation and contingent liabilities are reviewed",
}


def assess_acquisition_readiness(evidence: Mapping[str, bool], *, required: Sequence[str] | None = None) -> AcquisitionReadiness:
    codes = list(required or CHECK_LABELS)
    checks = []
    for code in codes:
        present = bool(evidence.get(code, False))
        checks.append(AcquisitionCheck(
            code=code,
            label=CHECK_LABELS.get(code, code),
            status="SUPPORTED" if present else "MISSING",
            evidence_ids=[code] if present else [],
            reason=None if present else "Required evidence is not available in the approved corpus",
        ))
    missing = [check for check in checks if check.status == "MISSING"]
    status = "GREEN" if not missing else ("RED" if len(missing) >= 3 else "AMBER")
    return AcquisitionReadiness(status=status, checks=checks)
