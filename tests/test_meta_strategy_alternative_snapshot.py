import json

import pytest

from portfolio.meta_strategy_alternative import STRATEGY_ID
from portfolio.meta_strategy_alternative_snapshot import (
    AlternativeSnapshotError,
    fetch_alternative_snapshot,
    parse_alternative_snapshot,
)


def _snapshot():
    return {
        "status": "VALIDATED",
        "strategy_kind": "ALTERNATIVE_SHADOW",
        "strategy_id": STRATEGY_ID,
        "strategy_spec_version": "3.0",
        "resolved_execution_target": "QQQ",
        "a1_overlay": {"event": "HOLD", "active": True},
    }


def test_alternative_snapshot_accepts_only_validated_v3_payload():
    assert parse_alternative_snapshot(json.dumps(_snapshot()))["strategy_id"] == STRATEGY_ID

    stale = _snapshot()
    stale["strategy_id"] = "qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1"
    with pytest.raises(AlternativeSnapshotError, match="v3.0"):
        parse_alternative_snapshot(stale)


def test_fetch_alternative_snapshot_uses_json_request_and_timeout():
    calls = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        @staticmethod
        def read():
            return json.dumps(_snapshot()).encode("utf-8")

    def opener(request, *, timeout):
        calls["url"] = request.full_url
        calls["accept"] = request.headers.get("Accept")
        calls["timeout"] = timeout
        return _Response()

    result = fetch_alternative_snapshot(
        url="https://example.test/shadow.json",
        timeout_seconds=2.5,
        opener=opener,
    )

    assert result["resolved_execution_target"] == "QQQ"
    assert calls == {
        "url": "https://example.test/shadow.json",
        "accept": "application/json",
        "timeout": 2.5,
    }
