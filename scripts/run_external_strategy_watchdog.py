from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio.external_strategy_scheduler import (  # noqa: E402
    GitHubSchedulerClient,
    run_external_strategy_watchdog,
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the externally triggered strategy schedule watchdog.")
    parser.add_argument("--mode", required=True, choices=("ensure", "watchdog"))
    args = parser.parse_args()

    repository = _required_env("GITHUB_REPOSITORY")
    token = _required_env("GITHUB_TOKEN")
    target_ref = os.environ.get("GITHUB_TARGET_REF", "main").strip() or "main"
    recipient = os.environ.get("GITHUB_RECIPIENT", "PJS-creator").strip() or "PJS-creator"
    client = GitHubSchedulerClient(repository=repository, token=token)
    results = run_external_strategy_watchdog(
        client=client,
        mode=args.mode,
        repository=repository,
        target_ref=target_ref,
        recipient=recipient,
    )
    print(json.dumps({"mode": args.mode, "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
