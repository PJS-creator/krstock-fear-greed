from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PortfolioRecord:
    owner_id: str
    portfolio_name: str
    payload_json: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


class PortfolioStoreError(RuntimeError):
    pass


class PortfolioStore(Protocol):
    def list_portfolios(self, owner_id: str) -> list[PortfolioRecord]:
        ...

    def get_portfolio(self, owner_id: str, portfolio_name: str) -> PortfolioRecord | None:
        ...

    def save_portfolio(
        self,
        owner_id: str,
        portfolio_name: str,
        payload_json: Mapping[str, Any],
    ) -> PortfolioRecord:
        ...

    def delete_portfolio(self, owner_id: str, portfolio_name: str) -> bool:
        ...
