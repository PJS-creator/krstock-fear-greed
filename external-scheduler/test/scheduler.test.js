import assert from "node:assert/strict";
import test from "node:test";

import {
  STRATEGIES,
  ensureSignals,
  kstDate,
  notificationMarker,
  runWatchdog,
  watchdogMarker,
} from "../src/index.js";

const ENV = {
  GITHUB_TOKEN: "test-token",
  GITHUB_OWNER: "PJS-creator",
  GITHUB_REPOSITORY: "krstock-fear-greed",
  GITHUB_REF: "main",
  GITHUB_RECIPIENT: "PJS-creator",
};

function jsonResponse(body, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fakeGitHub(commentBodiesByIssue) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url, init });
    const commentsMatch = url.match(/\/issues\/(\d+)\/comments\?/);
    if (init.method === "GET" && commentsMatch) {
      const bodies = commentBodiesByIssue[Number(commentsMatch[1])] ?? [];
      return jsonResponse(bodies.map((body) => ({ body })));
    }
    if (url.endsWith("/dispatches") && init.method === "POST") {
      return jsonResponse(null, 204);
    }
    if (/\/issues\/\d+\/comments$/.test(url) && init.method === "POST") {
      return jsonResponse({ id: 1 }, 201);
    }
    throw new Error(`Unexpected request: ${init.method} ${url}`);
  };
  return { calls, fetchImpl };
}

test("kstDate converts the external UTC cron time to the intended KST date", () => {
  assert.equal(kstDate(Date.parse("2026-08-28T22:50:00Z")), "2026-08-29");
  assert.equal(kstDate(Date.parse("2026-08-28T23:20:00Z")), "2026-08-29");
});

test("07:50 fallback dispatches only a strategy without its daily notification", async () => {
  const date = "2026-08-29";
  const official = STRATEGIES.find((item) => item.key === "official");
  const { calls, fetchImpl } = fakeGitHub({
    127: [`${notificationMarker(official, date)}VALIDATED -->`],
    130: [],
  });

  const result = await ensureSignals(ENV, date, fetchImpl);

  assert.deepEqual(result, [
    { strategy: "official", received: true, dispatched: false },
    { strategy: "alternative", received: false, dispatched: true },
  ]);
  const dispatches = calls.filter((call) => call.url.endsWith("/dispatches"));
  assert.equal(dispatches.length, 1);
  assert.match(dispatches[0].url, /alternative-strategy-daily\.yml/);
  assert.deepEqual(JSON.parse(dispatches[0].init.body), {
    ref: "main",
    inputs: { run_slot: "external-0750-kst" },
  });
});

test("08:20 watchdog re-dispatches and posts one direct GitHub alert", async () => {
  const date = "2026-08-29";
  const alternative = STRATEGIES.find((item) => item.key === "alternative");
  const { calls, fetchImpl } = fakeGitHub({
    127: [],
    130: [`${notificationMarker(alternative, date)}VALIDATED -->`],
  });

  const result = await runWatchdog(ENV, date, fetchImpl);

  assert.deepEqual(result, [
    { strategy: "official", received: false, dispatched: true, alerted: true },
    { strategy: "alternative", received: true, dispatched: false, alerted: false },
  ]);
  const posts = calls.filter(
    (call) => /\/issues\/127\/comments$/.test(call.url) && call.init.method === "POST",
  );
  assert.equal(posts.length, 1);
  const body = JSON.parse(posts[0].init.body).body;
  assert.match(body, /08:20 KST까지/);
  assert.match(body, /@PJS-creator/);
  assert.match(body, /strategy-schedule-watchdog:2026-08-29:official/);
});

test("watchdog marker prevents duplicate alerts while retaining recovery dispatch", async () => {
  const date = "2026-08-29";
  const official = STRATEGIES.find((item) => item.key === "official");
  const alternative = STRATEGIES.find((item) => item.key === "alternative");
  const { calls, fetchImpl } = fakeGitHub({
    127: [watchdogMarker(official, date)],
    130: [`${notificationMarker(alternative, date)}VALIDATED -->`],
  });

  const result = await runWatchdog(ENV, date, fetchImpl);

  assert.equal(result[0].dispatched, true);
  assert.equal(result[0].alerted, false);
  assert.equal(
    calls.filter((call) => /\/issues\/127\/comments$/.test(call.url) && call.init.method === "POST").length,
    0,
  );
});
