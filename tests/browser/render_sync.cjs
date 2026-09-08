async function waitForFixtureRender(page, { after = 0, theme, section }) {
  // A retained title or checked radio can belong to the previous Streamlit run.
  const handle = await page.waitForFunction(({ after, theme, section }) => {
    const app = document.querySelector('[data-testid="stApp"]');
    const markers = document.querySelectorAll('[data-qa-render]');
    const marker = markers[markers.length - 1];
    if (!marker || app?.getAttribute('data-test-script-state') !== 'notRunning') return false;
    const revision = Number(marker.getAttribute('data-qa-render'));
    return revision > after
      && marker.getAttribute('data-qa-theme') === theme
      && marker.getAttribute('data-qa-section') === section
      ? revision : false;
  }, { after, theme, section }, { timeout: 30000 });
  const revision = await handle.jsonValue();
  await handle.dispose();
  return revision;
}

async function scrollDetailIntoView(page, selector) {
  for (let attempt = 0; attempt < 3; attempt++) {
    // Re-resolve the node if React replaced it between visibility and scrolling.
    const detail = page.locator(selector).filter({ visible: true }).first();
    await detail.waitFor({ state: 'visible', timeout: 10000 });
    try {
      await detail.scrollIntoViewIfNeeded({ timeout: 10000 });
      return;
    } catch (error) {
      if (attempt === 2 || !/Element is not attached to the DOM/i.test(error.message)) throw error;
    }
  }
}

module.exports = { waitForFixtureRender, scrollDetailIntoView };
