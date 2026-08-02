from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio.alternative_strategy_notification import (  # noqa: E402
    render_alternative_strategy_notification,
)
from portfolio.meta_strategy_notification import should_publish_notification  # noqa: E402


def _read_json(path: Path, *, required: bool) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            raise
        return None
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the daily alternative shadow notification.")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--run-slot", required=True)
    parser.add_argument("--update-exit-code", type=int, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--recipient", default="PJS-creator")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    latest_run = _read_json(args.data_root / "runs" / "latest_run.json", required=True)
    assert latest_run is not None
    if not should_publish_notification(
        run_slot=args.run_slot,
        update_exit_code=args.update_exit_code,
        latest_run=latest_run,
    ):
        args.output.unlink(missing_ok=True)
        return 0

    signal = _read_json(args.data_root / "signals" / "latest_validated.json", required=False)
    notification_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    content = render_alternative_strategy_notification(
        latest_run=latest_run,
        signal=signal,
        notification_date=notification_date,
        recipient=args.recipient,
        repository=args.repository,
        run_url=args.run_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
