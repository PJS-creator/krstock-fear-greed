from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from portfolio.history.models import PortfolioHistoryRecord

from .storage import (
    PortfolioRecord,
    PortfolioStore,
    PortfolioStoreError,
    deserialize_portfolio_payload_v2,
    serialize_portfolio_payload,
)


PORTFOLIO_COLLECTION_FIELDS = (
    "holdings",
    "transactions",
    "cash_ledger",
    "target_allocations",
    "journal_notes",
)


def _cash_balance_has_value(payload: Mapping[str, Any]) -> bool:
    balances = payload.get("cash_balances")
    if not isinstance(balances, Mapping):
        return False
    for currency in ("KRW", "USD"):
        try:
            if float(balances.get(currency) or 0.0) != 0.0:
                return True
        except (TypeError, ValueError):
            return False
    return False


def portfolio_payload_has_data(payload: Mapping[str, Any] | None) -> bool:
    """Return whether a validated payload contains user-owned portfolio data."""

    if not isinstance(payload, Mapping):
        return False
    try:
        clean = deserialize_portfolio_payload_v2(payload)
    except ValueError:
        return False
    if any(bool(clean.get(field)) for field in PORTFOLIO_COLLECTION_FIELDS):
        return True
    return _cash_balance_has_value(clean)


def _history_record_matches(
    record: PortfolioHistoryRecord,
    *,
    owner_id: str | None,
    portfolio_name: str | None,
) -> bool:
    if owner_id is not None and record.owner_id != owner_id:
        return False
    if portfolio_name is not None and record.portfolio_name != portfolio_name:
        return False
    return True


def _legacy_history_payload(record: PortfolioHistoryRecord) -> dict[str, object] | None:
    payload = record.payload_json
    holdings = payload.get("holdings")
    if not isinstance(holdings, list):
        return None
    cash_balances = payload.get("cash_balances")
    if not isinstance(cash_balances, Mapping):
        cash_balances = {"KRW": record.cash_krw, "USD": record.cash_usd}
    try:
        recovered = serialize_portfolio_payload(
            holdings,
            usd_krw=payload.get("usd_krw") or record.usd_krw,
            cash_krw=cash_balances.get("KRW", record.cash_krw),
            cash_usd=cash_balances.get("USD", record.cash_usd),
        )
    except ValueError:
        return None
    return recovered if portfolio_payload_has_data(recovered) else None


def recover_portfolio_payload_from_history(
    records: Iterable[PortfolioHistoryRecord],
    *,
    owner_id: str | None = None,
    portfolio_name: str | None = None,
) -> dict[str, object] | None:
    """Recover the newest non-empty account payload from portfolio history."""

    matching = [
        record
        for record in records
        if _history_record_matches(record, owner_id=owner_id, portfolio_name=portfolio_name)
    ]
    matching.sort(key=lambda record: record.captured_at, reverse=True)
    for record in matching:
        backup = record.payload_json.get("portfolio_backup")
        if isinstance(backup, Mapping) and portfolio_payload_has_data(backup):
            return deserialize_portfolio_payload_v2(backup)
        legacy = _legacy_history_payload(record)
        if legacy is not None:
            return legacy
    return None


def portfolio_payloads_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    try:
        return deserialize_portfolio_payload_v2(left) == deserialize_portfolio_payload_v2(right)
    except ValueError:
        return False


def save_portfolio_with_verification(
    store: PortfolioStore,
    owner_id: str,
    portfolio_name: str,
    payload: Mapping[str, Any],
) -> PortfolioRecord:
    """Persist a portfolio and verify that the same user-scoped row can be read back."""

    clean_payload = deserialize_portfolio_payload_v2(payload)
    store.save_portfolio(owner_id, portfolio_name, clean_payload)
    confirmed = store.get_portfolio(owner_id, portfolio_name)
    if confirmed is None:
        raise PortfolioStoreError("저장 결과를 다시 확인할 수 없습니다")
    if confirmed.owner_id != owner_id or confirmed.portfolio_name != portfolio_name:
        raise PortfolioStoreError("저장된 포트폴리오의 사용자 정보를 확인할 수 없습니다")
    if not portfolio_payloads_match(clean_payload, confirmed.payload_json):
        raise PortfolioStoreError("저장된 포트폴리오 내용이 일치하지 않습니다")
    return confirmed
