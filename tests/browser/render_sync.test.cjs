const test = require('node:test');
const assert = require('node:assert/strict');
const { scrollDetailIntoView } = require('./render_sync.cjs');

function fakePage(failures) {
  let resolutions = 0;
  return {
    get resolutions() { return resolutions; },
    locator() {
      const failure = failures[resolutions++];
      return { filter: () => ({ first: () => ({
        waitFor: async () => {},
        scrollIntoViewIfNeeded: async () => { if (failure) throw new Error(failure); },
      }) }) };
    },
  };
}

test('a detached node is resolved again before scrolling', async () => {
  const page = fakePage(['Element is not attached to the DOM']);
  await scrollDetailIntoView(page, '.table');
  assert.equal(page.resolutions, 2);
});

test('persistent detachment fails after three attempts', async () => {
  const page = fakePage(Array(3).fill('Element is not attached to the DOM'));
  await assert.rejects(scrollDetailIntoView(page, '.table'), /not attached/);
  assert.equal(page.resolutions, 3);
});

test('unrelated browser failures are not suppressed or retried', async () => {
  const page = fakePage(['Timeout while waiting for a visible table']);
  await assert.rejects(scrollDetailIntoView(page, '.table'), /Timeout/);
  assert.equal(page.resolutions, 1);
});
