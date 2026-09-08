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


class PortfolioConflictError(PortfolioStoreError):
    """The stored version changed after this session loaded it."""


PORTFOLIO_CONFLICT_MESSAGE = "다른 화면에서 포트폴리오가 변경되어 저장을 중단했습니다. 현재 입력은 보존되어 있습니다."


class PortfolioStore(Protocol):
    def save_portfolio_if_unchanged(
        self, owner_id: str, portfolio_name: str, payload_json: Mapping[str, Any],
        *, expected_updated_at: str | None,
    ) -> PortfolioRecord:
        ...

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
