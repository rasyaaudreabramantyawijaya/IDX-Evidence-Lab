"""Source-policy firewall for the offline product boundary."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.schemas import SourceClass


class SourcePolicyError(ValueError):
    """Raised when a provider/source combination violates product policy."""


@dataclass(frozen=True)
class SourcePolicy:
    """Allow only approved providers for each source class.

    This module does not make requests. It only validates metadata before a
    future adapter is allowed to run.
    """

    sectors_provider: str = "Sectors.app"
    llm_provider: str = "OpenRouter"

    def validate(self, source_class: SourceClass, provider: str, *, network: bool = False) -> None:
        provider_norm = provider.strip().casefold()
        sectors_norm = self.sectors_provider.casefold()
        llm_norm = self.llm_provider.casefold()

        if source_class is SourceClass.SECTORS_SOURCE_DATA:
            if provider_norm != sectors_norm:
                raise SourcePolicyError("Source data may only come from Sectors.app")
            return
        if source_class is SourceClass.MODEL_INFERENCE:
            if provider_norm != llm_norm:
                raise SourcePolicyError("Model inference provider must be OpenRouter")
            return
        if source_class is SourceClass.PRIVATE_LEGAL_REFERENCE:
            if provider_norm not in {"local", "private_file", "private_corpus"}:
                raise SourcePolicyError("Legal references must come from the private local corpus")
            if network:
                raise SourcePolicyError("Private legal corpus cannot be fetched over the network")
            return
        if network:
            raise SourcePolicyError(f"Network access is not allowed for {source_class.value}")

    def assert_no_fallback(self, provider: str) -> None:
        if provider.strip().casefold() not in {self.sectors_provider.casefold(), self.llm_provider.casefold()}:
            raise SourcePolicyError(f"Unapproved provider: {provider}")
