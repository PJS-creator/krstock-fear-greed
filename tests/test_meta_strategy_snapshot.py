import json

import pytest

from portfolio.meta_strategy import unavailable_meta_strategy_result
from portfolio.meta_strategy_snapshot import (
    OfficialSnapshotError,
    official_snapshot_to_app_view,
    parse_official_snapshot,
)


def _snapshot():
    return {
        "status": "VALIDATED",
        "signal_hash": "abc",
        "pipeline_version": "v1",
        "ruleset_version": "rules",
        "router_target": "GLD",
        "overall_execution_target": "GLD",
        "entry_advice": {"mode": "IMMEDIATE_100"},
        "rsi_reference": {"latest_rsi14": 62.0},
        "legacy_view": {
            "status": "updated",
            "market_regime": "bear",
            "market_regime_label": "약세장",
            "active_strategy_label": "RED Router-S1",
            "applied_ticker": "GLD",
        },
    }


def test_official_snapshot_becomes_primary_app_view_and_keeps_preview():
    preview = unavailable_meta_strategy_result("preview failed")

    view = official_snapshot_to_app_view(_snapshot(), preview=preview)

    assert view["data_mode"] == "official"
    assert view["applied_ticker"] == "GLD"
    assert view["router_target"] == "GLD"
    assert view["preview"]["status"] == "failed"


def test_unvalidated_snapshot_is_rejected():
    payload = _snapshot()
    payload["status"] = "SOURCE_FAILED"

    with pytest.raises(OfficialSnapshotError):
        parse_official_snapshot(json.dumps(payload))
