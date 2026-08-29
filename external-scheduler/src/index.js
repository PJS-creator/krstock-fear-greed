const ENSURE_CRON = "50 22 * * *";
const WATCHDOG_CRON = "20 23 * * *";

const STRATEGIES = [
  {
    key: "official",
    label: "공식 메타전략",
    issueNumber: 127,
    workflow: "meta-strategy-daily.yml",
    notificationPrefix: "meta-strategy-notification",
    githubSchedule: "07:37 / 07:57 KST",
  },
  {
    key: "alternative",
    label: "대안 shadow v3.0 전략",
    issueNumber: 130,
    workflow: "alternative-strategy-daily.yml",
    notificationPrefix: "alternative-strategy-notification",
    githubSchedule: "07:47 / 08:07 KST",
  },
];

function requiredEnv(env, key) {
  const value = String(env[key] ?? "").trim();
  if (!value) {
    throw new Error(`Missing Worker setting: ${key}`);
  }
  return value;
}

export function kstDate(epochMilliseconds) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(epochMilliseconds));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function notificationMarker(strategy, date) {
  return `<!-- ${strategy.notificationPrefix}:${date}:`;
}

export function watchdogMarker(strategy, date) {
  return `<!-- strategy-schedule-watchdog:${date}:${strategy.key} -->`;
}

function githubHeaders(env) {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${requiredEnv(env, "GITHUB_TOKEN")}`,
    "User-Agent": "jisungport-strategy-scheduler",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function repositoryBase(env) {
  const owner = requiredEnv(env, "GITHUB_OWNER");
  const repository = requiredEnv(env, "GITHUB_REPOSITORY");
  return `https://api.github.com/repos/${owner}/${repository}`;
}

async function githubRequest(env, pathOrUrl, init, fetchImpl) {
  const url = pathOrUrl.startsWith("https://")
    ? pathOrUrl
    : `${repositoryBase(env)}${pathOrUrl}`;
  const response = await fetchImpl(url, {
    ...init,
    headers: {
      ...githubHeaders(env),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error(`GitHub API ${response.status} for ${url}: ${detail}`);
  }
  return response;
}

function nextPageUrl(linkHeader) {
  for (const segment of String(linkHeader ?? "").split(",")) {
    const match = segment.match(/<([^>]+)>;\s*rel="next"/);
    if (match) {
      return match[1];
    }
  }
  return null;
}

function startOfKstDateUtc(date) {
  return new Date(`${date}T00:00:00+09:00`).toISOString();
}

async function listDailyComments(env, strategy, date, fetchImpl) {
  const since = encodeURIComponent(startOfKstDateUtc(date));
  let url = `/issues/${strategy.issueNumber}/comments?per_page=100&since=${since}`;
  const comments = [];
  while (url) {
    const response = await githubRequest(env, url, { method: "GET" }, fetchImpl);
    const page = await response.json();
    if (!Array.isArray(page)) {
      throw new Error(`Unexpected comments response for issue ${strategy.issueNumber}`);
    }
    comments.push(...page);
    url = nextPageUrl(response.headers.get("link"));
  }
  return comments;
}

function includesMarker(comments, marker) {
  return comments.some((comment) => String(comment?.body ?? "").includes(marker));
}

async function dispatchStrategy(env, strategy, runSlot, fetchImpl) {
  const ref = requiredEnv(env, "GITHUB_REF");
  await githubRequest(
    env,
    `/actions/workflows/${strategy.workflow}/dispatches`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref, inputs: { run_slot: runSlot } }),
    },
    fetchImpl,
  );
}

function watchdogBody(env, strategy, date) {
  const owner = requiredEnv(env, "GITHUB_OWNER");
  const repository = requiredEnv(env, "GITHUB_REPOSITORY");
  const recipient = requiredEnv(env, "GITHUB_RECIPIENT");
  const workflowUrl = `https://github.com/${owner}/${repository}/actions/workflows/${strategy.workflow}`;
  return `${watchdogMarker(strategy, date)}
@${recipient}

## ${strategy.label} 알림 미수신 · ${date} KST

**08:20 KST까지 당일 판정 알림을 확인하지 못했습니다.**

- GitHub 예약 실행: ${strategy.githubSchedule}
- 외부 보충 실행: 07:50 KST
- 08:20 감시 재호출: 요청됨
- 확인 위치: [${strategy.label} Actions](${workflowUrl})

GitHub Actions 실행이 지연 중일 수 있습니다. 당일 판정이 게시될 때까지 직전 검증 완료 값을 최신 판정으로 오인하지 마세요.
`;
}

async function postWatchdogAlert(env, strategy, date, fetchImpl) {
  await githubRequest(
    env,
    `/issues/${strategy.issueNumber}/comments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: watchdogBody(env, strategy, date) }),
    },
    fetchImpl,
  );
}

export async function ensureSignals(env, date, fetchImpl = fetch) {
  const results = [];
  for (const strategy of STRATEGIES) {
    const comments = await listDailyComments(env, strategy, date, fetchImpl);
    const received = includesMarker(comments, notificationMarker(strategy, date));
    if (!received) {
      await dispatchStrategy(env, strategy, "external-0750-kst", fetchImpl);
    }
    results.push({ strategy: strategy.key, received, dispatched: !received });
  }
  return results;
}

export async function runWatchdog(env, date, fetchImpl = fetch) {
  const results = [];
  for (const strategy of STRATEGIES) {
    const comments = await listDailyComments(env, strategy, date, fetchImpl);
    const received = includesMarker(comments, notificationMarker(strategy, date));
    const alertMarker = watchdogMarker(strategy, date);
    const alreadyAlerted = includesMarker(comments, alertMarker);
    if (!received) {
      await dispatchStrategy(env, strategy, "external-watchdog-0820-kst", fetchImpl);
      if (!alreadyAlerted) {
        await postWatchdogAlert(env, strategy, date, fetchImpl);
      }
    }
    results.push({
      strategy: strategy.key,
      received,
      dispatched: !received,
      alerted: !received && !alreadyAlerted,
    });
  }
  return results;
}

export async function handleScheduled(controller, env, fetchImpl = fetch) {
  const date = kstDate(controller.scheduledTime ?? Date.now());
  if (controller.cron === ENSURE_CRON) {
    const results = await ensureSignals(env, date, fetchImpl);
    console.log(JSON.stringify({ event: "ensure-signals", date, results }));
    return results;
  }
  if (controller.cron === WATCHDOG_CRON) {
    const results = await runWatchdog(env, date, fetchImpl);
    console.log(JSON.stringify({ event: "watchdog", date, results }));
    return results;
  }
  throw new Error(`Unsupported cron expression: ${controller.cron}`);
}

export default {
  async scheduled(controller, env, context) {
    context.waitUntil(handleScheduled(controller, env));
  },

  async fetch() {
    return Response.json({
      service: "jisungport-strategy-scheduler",
      schedules: ["07:50 KST ensure-signals", "08:20 KST watchdog"],
    });
  },
};

export { ENSURE_CRON, STRATEGIES, WATCHDOG_CRON };
