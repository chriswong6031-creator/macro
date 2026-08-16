import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../templates/fundamental_forensics.js', import.meta.url), 'utf8');

function element() {
  const classes = new Set();
  const attrs = {};
  return {
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    hidden: true,
    innerHTML: '',
    textContent: '',
    setAttribute: (key, value) => {
      attrs[key] = String(value);
    },
    removeAttribute: (key) => {
      delete attrs[key];
    },
    getAttribute: (key) => (Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : null),
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
  };
}

function harness() {
  const nodes = {
    'ff-evidence': element(),
    'ff-workspace': element(),
    'ff-scrim': element(),
    'ff-evidence-close': element(),
    'ff-run-meta': element(),
    'ff-freshness-status': element(),
    'ff-as-of': element(),
    'ff-source-snapshot': element(),
    'ff-source-label': element(),
    'ff-main': element(),
  };
  const body = { classList: { add() {}, remove() {} } };
  const documentObject = {
    readyState: 'loading',
    addEventListener() {},
    getElementById: (id) => nodes[id] || element(),
    querySelector() { return element(); },
    querySelectorAll() { return []; },
    body,
    documentElement: { getAttribute() { return 'en'; } },
    activeElement: null,
  };
  const windowObject = {
    location: { hostname: 'contract.test' },
    matchMedia: () => ({ matches: true, addEventListener() {}, addListener() {} }),
    __FF_WORKBENCH_TEST__: true,
    requestAnimationFrame(fn) { fn(); },
  };
  const context = vm.createContext({
    window: windowObject,
    document: documentObject,
    console,
    URL,
    URLSearchParams,
  });
  vm.runInContext(source, context, { filename: 'fundamental_forensics.js' });
  const api = windowObject.__FF_WORKBENCH_TEST__;
  api.cacheUi();
  api.ui.evidence = nodes['ff-evidence'];
  api.ui.workspace = nodes['ff-workspace'];
  api.ui.scrim = nodes['ff-scrim'];
  api.ui.evidenceClose = nodes['ff-evidence-close'];
  api.ui.main = nodes['ff-main'];
  api.ui.siteNav = element();
  api.ui.runMeta = nodes['ff-run-meta'];
  api.ui.freshnessStatus = nodes['ff-freshness-status'];
  api.ui.asOf = nodes['ff-as-of'];
  api.ui.sourceSnapshot = nodes['ff-source-snapshot'];
  api.ui.sourceLabel = nodes['ff-source-label'];
  return { api, nodes };
}

test('CTA opens analysis drawer on desktop', () => {
  const { api, nodes } = harness();
  assert.equal(nodes['ff-evidence'].classList.contains('is-open'), false);
  api.openAnalysisDrawer();
  assert.equal(nodes['ff-evidence'].classList.contains('is-open'), true);
  assert.equal(nodes['ff-workspace'].getAttribute('data-analysis-open'), 'true');
  assert.equal(nodes['ff-scrim'].hidden, false);
  assert.equal(nodes['ff-evidence'].getAttribute('role'), 'dialog');
});

test('health states paint without using evaluation time as source freshness', () => {
  const { api, nodes } = harness();
  api.applyHealth({
    status: 'stale',
    evaluated_at: '2026-08-16T00:00:00Z',
    clocks: {
      latest_source_filing_date: '2026-07-12',
      broad_source_at: '2026-07-12T11:23:15Z',
      composed_state_at: '2026-07-12T11:23:15Z',
    },
  });
  assert.equal(nodes['ff-run-meta'].getAttribute('data-freshness'), 'stale');
  assert.match(nodes['ff-freshness-status'].innerHTML, /Stale/);
  assert.equal(nodes['ff-as-of'].textContent, '2026-07-12');
  assert.equal(nodes['ff-source-snapshot'].textContent, '2026-07-12');
  assert.doesNotMatch(nodes['ff-source-snapshot'].textContent, /2026-08-16/);
  assert.doesNotMatch(nodes['ff-freshness-status'].innerHTML, /Last refreshed/);

  api.applyHealth({ status: 'current', clocks: { latest_source_filing_date: '2026-08-15', broad_source_at: '2026-08-15T12:00:00Z' } });
  assert.equal(nodes['ff-run-meta'].getAttribute('data-freshness'), 'current');
  assert.match(nodes['ff-freshness-status'].innerHTML, /Current/);

  api.applyHealth({ status: 'degraded', clocks: { latest_source_filing_date: '2026-07-12', broad_source_at: '2026-07-12T11:23:15Z' } });
  assert.equal(nodes['ff-run-meta'].getAttribute('data-freshness'), 'degraded');
  assert.match(nodes['ff-freshness-status'].innerHTML, /Degraded/);

  api.applyHealth({ status: 'unavailable', clocks: {} });
  assert.equal(nodes['ff-run-meta'].getAttribute('data-freshness'), 'unavailable');
  assert.match(nodes['ff-freshness-status'].innerHTML, /Unavailable/);
});
