from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import json
from typing import Mapping, Protocol, Sequence
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class StrategySchedule:
    key: str
    label: str
    issue_number: int
    workflow: str
    notification_prefix: str
    github_schedule: str


STRATEGIES = (
    StrategySchedule(
        key="official",
        label="공식 메타전략",
        issue_number=127,
        workflow="meta-strategy-daily.yml",
        notification_prefix="meta-strategy-notification",
        github_schedule="07:37 / 07:57 KST",
    ),
    StrategySchedule(
        key="alternative",
        label="대안 shadow v3.0 전략",
        issue_number=130,
        workflow="alternative-strategy-daily.yml",
        notification_prefix="alternative-strategy-notification",
        github_schedule="07:47 / 08:07 KST",
    ),
)


class SchedulerClient(Protocol):
    def list_issue_comments(self, issue_number: int, notification_date: date) -> list[Mapping[str, object]]:
        ...

    def dispatch_workflow(self, workflow: str, *, ref: str, run_slot: str) -> None:
        ...

    def post_issue_comment(self, issue_number: int, body: str) -> None:
        ...


def kst_date(now: datetime | None = None) -> date:
    current = now or datetime.now(tz=KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return current.astimezone(KST).date()


def notification_marker(strategy: StrategySchedule, notification_date: date | str) -> str:
    return f"<!-- {strategy.notification_prefix}:{notification_date}:"


def watchdog_marker(strategy: StrategySchedule, notification_date: date | str) -> str:
    return f"<!-- strategy-schedule-watchdog:{notification_date}:{strategy.key} -->"


def _includes_marker(comments: Sequence[Mapping[str, object]], marker: str) -> bool:
    return any(marker in str(comment.get("body") or "") for comment in comments)


def _next_link(link_header: str | None) -> str | None:
    for segment in str(link_header or "").split(","):
        sections = [item.strip() for item in segment.split(";")]
        if len(sections) < 2 or 'rel="next"' not in sections[1:]:
            continue
        if sections[0].startswith("<") and sections[0].endswith(">"):
            return sections[0][1:-1]
    return None


class GitHubSchedulerClient:
    def __init__(self, *, repository: str, token: str, api_version: str = "2022-11-28") -> None:
        owner, separator, name = repository.partition("/")
        if not separator or not owner.strip() or not name.strip():
            raise ValueError("repository must use the owner/name format")
        if not token.strip():
            raise ValueError("GitHub token is required")
        self._base_url = f"https://api.github.com/repos/{owner.strip()}/{name.strip()}"
        self._token = token.strip()
        self._api_version = api_version

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        payload: Mapping[str, object] | None = None,
    ) -> tuple[object | None, Mapping[str, str]]:
        url = path_or_url if path_or_url.startswith("https://") else f"{self._base_url}{path_or_url}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "jisungport-external-strategy-watchdog",
            "X-GitHub-Api-Version": self._api_version,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"GitHub API {exc.code} for {url}: {detail}") from exc
        if not raw:
            return None, response_headers
        return json.loads(raw.decode("utf-8")), response_headers

    def list_issue_comments(self, issue_number: int, notification_date: date) -> list[Mapping[str, object]]:
        since = datetime.combine(notification_date, time.min, tzinfo=KST).isoformat()
        query = urlencode({"per_page": 100, "since": since})
        next_url: str | None = f"/issues/{issue_number}/comments?{query}"
        comments: list[Mapping[str, object]] = []
        while next_url:
            payload, headers = self._request("GET", next_url)
            if not isinstance(payload, list):
                raise RuntimeError(f"Unexpected issue comments response for issue {issue_number}")
            comments.extend(item for item in payload if isinstance(item, Mapping))
            next_url = _next_link(headers.get("Link"))
        return comments

    def dispatch_workflow(self, workflow: str, *, ref: str, run_slot: str) -> None:
        workflow_id = quote(workflow, safe="")
        self._request(
            "POST",
            f"/actions/workflows/{workflow_id}/dispatches",
            payload={"ref": ref, "inputs": {"run_slot": run_slot}},
        )

    def post_issue_comment(self, issue_number: int, body: str) -> None:
        self._request("POST", f"/issues/{issue_number}/comments", payload={"body": body})


def _watchdog_body(
    *,
    repository: str,
    recipient: str,
    strategy: StrategySchedule,
    notification_date: date,
) -> str:
    workflow_url = f"https://github.com/{repository}/actions/workflows/{strategy.workflow}"
    return f"""{watchdog_marker(strategy, notification_date)}
@{recipient}

## {strategy.label} 알림 미수신 · {notification_date} KST

**08:20 KST까지 당일 판정 알림을 확인하지 못했습니다.**

- GitHub 예약 실행: {strategy.github_schedule}
- cron-job.org 보충 실행: 07:50 KST
- 08:20 감시 재호출: 요청됨
- 확인 위치: [{strategy.label} Actions]({workflow_url})

GitHub Actions 실행이 지연 중일 수 있습니다. 당일 판정이 게시될 때까지 직전 검증 완료 값을 최신 판정으로 오인하지 마세요.
"""


def run_external_strategy_watchdog(
    *,
    client: SchedulerClient,
    mode: str,
    repository: str,
    target_ref: str,
    recipient: str,
    notification_date: date | None = None,
) -> list[dict[str, object]]:
    if mode not in {"ensure", "watchdog"}:
        raise ValueError(f"Unsupported watchdog mode: {mode}")
    effective_date = notification_date or kst_date()
    run_slot = "external-0750-kst" if mode == "ensure" else "external-watchdog-0820-kst"
    results: list[dict[str, object]] = []

    for strategy in STRATEGIES:
        comments = client.list_issue_comments(strategy.issue_number, effective_date)
        received = _includes_marker(comments, notification_marker(strategy, effective_date))
        alert_marker = watchdog_marker(strategy, effective_date)
        already_alerted = _includes_marker(comments, alert_marker)
        dispatched = False
        alerted = False

        if not received:
            client.dispatch_workflow(strategy.workflow, ref=target_ref, run_slot=run_slot)
            dispatched = True
            if mode == "watchdog" and not already_alerted:
                client.post_issue_comment(
                    strategy.issue_number,
                    _watchdog_body(
                        repository=repository,
                        recipient=recipient,
                        strategy=strategy,
                        notification_date=effective_date,
                    ),
                )
                alerted = True

        results.append(
            {
                "strategy": strategy.key,
                "received": received,
                "dispatched": dispatched,
                "alerted": alerted,
            }
        )

    return results


__all__ = [
    "GitHubSchedulerClient",
    "KST",
    "STRATEGIES",
    "StrategySchedule",
    "kst_date",
    "notification_marker",
    "run_external_strategy_watchdog",
    "watchdog_marker",
]
