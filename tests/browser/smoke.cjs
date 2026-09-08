// Standalone CI browser checks. Never points at the production application.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { waitForFixtureRender, scrollDetailIntoView } = require('./render_sync.cjs');

const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'test-results/browser');
fs.mkdirSync(output, { recursive: true });
const port = process.env.UI_TEST_PORT || '8591';
const base = `http://127.0.0.1:${port}`;
const server = spawn(process.env.UI_TEST_PYTHON || 'python', [
  '-m', 'streamlit', 'run', 'tests/browser/fixture_app.py', '--server.headless=true',
  `--server.port=${port}`, '--browser.gatherUsageStats=false',
], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
const log = fs.createWriteStream(path.join(output, 'streamlit.log'));
server.stdout.pipe(log, { end: false });
server.stderr.pipe(log, { end: false });

async function assertScreen(page, name, expected, { hasDetail = true } = {}) {
  const revision = await waitForFixtureRender(page, expected);
  console.log(`Checking ${name}, completed render ${revision}`);
  await page.locator('[data-testid="stAppViewContainer"]').waitFor();
  assert.equal(await page.locator('[data-testid="stException"]').count(), 0, name);
  assert.equal(await page.getByText('이 영역을 불러오는 중 문제가 발생했습니다.', { exact: true }).count(), 0, name);
  assert.equal(await page.getByText('CachedWidgetWarning', { exact: false }).count(), 0, name);
  assert.equal(await page.locator('pre code').filter({ hasText: 'summary-split-card' }).count(), 0, `${name}: raw HTML rendered as code`);
  const overflow = await page.evaluate(() => {
    const main = document.querySelector('[data-testid="stMain"]');
    return main ? main.scrollWidth - main.clientWidth : document.documentElement.scrollWidth - innerWidth;
  });
  assert.ok(overflow <= 2, `${name}: horizontal overflow ${overflow}px`);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  if (hasDetail) {
    const selector = expected.section === 'chart_analysis' ? '.chart-analysis-table' : '.summary-table-wrap';
    await scrollDetailIntoView(page, selector);
    await page.screenshot({ path: path.join(output, `${name}-detail.png`), fullPage: false });
  }
  return revision;
}

(async () => {
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 60; i++) {
      if (server.exitCode !== null) throw new Error('Streamlit fixture exited');
      try { ready = (await fetch(`${base}/_stcore/health`)).ok; } catch (_) {}
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.ok(ready, 'Streamlit fixture did not start');
    browser = await chromium.launch({ headless: true, ...(process.env.UI_TEST_BROWSER ? { channel: process.env.UI_TEST_BROWSER } : {}) });
    for (const width of [1440, 768, 390]) {
      for (const theme of ['dark', 'light']) {
        const page = await browser.newPage({ viewport: { width, height: 900 } });
        await page.goto(`${base}/?theme=${theme}&scenario=ready`);
        let revision = await assertScreen(page, `${width}-${theme}-summary`, { theme, section: 'summary' });
        await page.getByRole('radiogroup', { name: '화면 선택', exact: true }).getByText('차트분석', { exact: true }).click();
        revision = await assertScreen(page, `${width}-${theme}-chart`, { after: revision, theme, section: 'chart_analysis' });
        const nextTheme = theme === 'dark' ? 'light' : 'dark';
        await page.getByRole('radiogroup', { name: '테마', exact: true }).getByText(nextTheme === 'light' ? '라이트' : '다크', { exact: true }).click();
        await assertScreen(page, `${width}-${theme}-theme-switch`, { after: revision, theme: nextTheme, section: 'chart_analysis' });
        assert.ok(await page.getByRole('radio', { name: '차트분석', exact: true }).isChecked());
        await page.close();
      }
    }
    for (const scenario of ['login', 'empty', 'partial']) {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.goto(`${base}/?scenario=${scenario}&theme=light`);
      await page.getByRole('radiogroup', { name: '테마', exact: true }).getByText('라이트', { exact: true }).waitFor();
      if (scenario === 'login') await page.getByRole('checkbox', { name: '로그인 유지', exact: true }).waitFor({ state: 'attached' });
      else if (scenario === 'partial') await page.getByText(/부분 평가: 1개/).waitFor();
      else await page.getByText('아직 포트폴리오 데이터가 없습니다.', { exact: true }).waitFor();
      await assertScreen(page, `390-${scenario}`, { theme: 'light', section: 'summary' }, { hasDetail: scenario === 'partial' });
      await page.close();
    }
    console.log('Browser regression checks passed: 3 viewports, 2 themes, theme persistence and login/empty/partial states.');
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.once('exit', resolve); });
    log.end();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
