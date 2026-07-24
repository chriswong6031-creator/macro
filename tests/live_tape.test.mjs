// Offline DOM-stub test of templates/live.js's Live Tape (/ws/tape) client path.
// Proves the shared patch fn + the ^TNX display transform END TO END through the
// REAL code (no re-implementation): it stubs just enough of window/document/
// WebSocket, loads live.js, fires a synthetic ws message, and asserts the DOM.
//
// Run: node tests/live_tape.test.mjs   (node 18+). Mirrors the standalone idiom
// of worker/quotes.worker.test.mjs (no jsdom / no test-runner dependency).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(HERE, "..", "templates", "live.js"), "utf8");

// --------------------------------------------------------------------------- //
// Minimal DOM stub — only what live.js touches.
// --------------------------------------------------------------------------- //
function makeEl(attrs, cls) {
  const a = Object.assign({}, attrs);
  const classes = new Set((cls || "").split(/\s+/).filter(Boolean));
  return {
    _attrs: a,
    textContent: "",
    title: "",
    parentNode: null,
    getAttribute: (k) => (k in a ? a[k] : null),
    setAttribute: (k, v) => { a[k] = String(v); },
    hasAttribute: (k) => k in a,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (x) => classes.has(x),
    },
    querySelector: () => null,
    appendChild: () => {},
    _classes: classes,
  };
}

// The six tape tiles' price + delta nodes we assert on.
const tnxPx = makeEl({ "data-sym": "^TNX", "data-mkt": "us", "data-fmt": "tnx", "data-bare": "" }, "mx5-mkt-price nb-px");
const tnxChg = makeEl({ "data-sym": "^TNX", "data-mkt": "us", "data-fmt": "tnx" }, "mx5-mkt-delta nb-chg");
const esPx = makeEl({ "data-sym": "ES=F", "data-mkt": "us", "data-bare": "" }, "mx5-mkt-price nb-px");
const esChg = makeEl({ "data-sym": "ES=F", "data-mkt": "us" }, "mx5-mkt-delta nb-chg");
const ALL = [tnxPx, tnxChg, esPx, esChg];

function matchSel(sel) {
  // live.js uses ".nb-px[data-sym]", ".nb-chg[data-sym]", and the union.
  const wantPx = sel.includes("nb-px");
  const wantChg = sel.includes("nb-chg");
  return ALL.filter((el) => {
    const isPx = el._classes.has("nb-px");
    const isChg = el._classes.has("nb-chg");
    return (wantPx && isPx) || (wantChg && isChg);
  });
}

let wsInstance = null;
class FakeWebSocket {
  constructor(url) { this.url = url; wsInstance = this; setTimeout(() => this.onopen && this.onopen(), 0); }
  close() {}
}

const listeners = {};
const documentStub = {
  readyState: "complete",
  hidden: false,
  documentElement: { getAttribute: () => "en" },
  head: { appendChild: () => {} },
  getElementById: () => null,
  createElement: () => ({ id: "", textContent: "", setAttribute: () => {} }),
  querySelectorAll: (sel) => matchSel(sel),
  addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
};

const windowStub = {
  LIVE_ENABLED: true,
  LIVE_POLL_SEC: 999999,      // effectively disable the poll timer during the test
  LIVE_DELAYED_MIN: 0,        // allow the live pulse for a ws 'quote' basis
  LIVE_WS_TAPE: true,
  WebSocket: FakeWebSocket,
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
  location: { protocol: "https:", host: "www.example.com" },
  localStorage: { removeItem: () => {}, getItem: () => null, setItem: () => {} },
};
windowStub.window = windowStub;

// The poller's fetch is stubbed to a benign empty result so the ws path is what
// we exercise; "AbortController" is absent from windowStub so getJSON skips the
// abort timer entirely.
const fetchStub = async () => ({ ok: true, json: async () => null });

const ctx = {
  window: windowStub,
  document: documentStub,
  WebSocket: FakeWebSocket,
  fetch: fetchStub,
  setInterval: windowStub.setInterval,
  clearInterval: windowStub.clearInterval,
  setTimeout: windowStub.setTimeout,
  clearTimeout: windowStub.clearTimeout,
  location: windowStub.location,
  Date,
  Math,
  Number,
  JSON,
  Promise,
  Object,
  console,
};
vm.createContext(ctx);
vm.runInContext(SRC, ctx);

// live.js ran start() synchronously (readyState !== "loading"); the FakeWebSocket
// was constructed. Fire a synthetic ^TNX tick and an ES=F tick.
await new Promise((r) => setTimeout(r, 5));
assert.ok(wsInstance, "live.js should have opened a /ws/tape socket");
assert.ok(wsInstance.url.endsWith("/ws/tape"), `ws url wrong: ${wsInstance.url}`);
assert.ok(wsInstance.url.startsWith("wss://"), "https page must use wss://");

// ^TNX: raw quote 42.5 (yield×10) with prevClose 42.25 -> display 4.25%, delta in bps.
// bps = (42.5 - 42.25) * 10 = +2.5 -> rounds to "+2 bps" (toFixed(0) of 2.5 = "3"?).
// 2.5.toFixed(0) === "3" (round-half-to-even is NOT used by toFixed) -> "+3 bps".
wsInstance.onmessage({ data: JSON.stringify({ sym: "^TNX", price: 42.5, chgPct: 0.59, prevClose: 42.25, ts: Date.now(), basis: "quote" }) });
wsInstance.onmessage({ data: JSON.stringify({ sym: "ES=F", price: 5432.25, chgPct: 0.85, ts: Date.now(), basis: "quote" }) });

// ^TNX price transform: 42.5 / 10 => "4.25%".
assert.equal(tnxPx.textContent, "4.25%", `tnx price transform wrong: ${tnxPx.textContent}`);
// ^TNX delta in bps: (42.5-42.25)*10 = 2.5 -> "+3 bps" (toFixed(0)).
assert.equal(tnxChg.textContent, "+3 bps", `tnx bps delta wrong: ${tnxChg.textContent}`);
assert.ok(tnxChg._classes.has("up"), "tnx positive delta should be 'up'");

// ES=F price: no tnx, data-bare => no "$" prefix, thousands sep, 2dp.
assert.equal(esPx.textContent, "5,432.25", `ES=F price wrong: ${esPx.textContent}`);
assert.equal(esChg.textContent, "+0.85%", `ES=F delta wrong: ${esChg.textContent}`);
assert.ok(esPx.getAttribute("data-live") === "1", "ES=F fresh quote should be live");

// Negative tnx move -> bps sign + 'down'.
wsInstance.onmessage({ data: JSON.stringify({ sym: "^TNX", price: 42.0, chgPct: -1.2, prevClose: 42.25, ts: Date.now() + 1, basis: "quote" }) });
assert.equal(tnxPx.textContent, "4.20%", `tnx price update wrong: ${tnxPx.textContent}`);
assert.equal(tnxChg.textContent, "-3 bps", `tnx negative bps wrong: ${tnxChg.textContent}`); // (42.0-42.25)*10 = -2.5 -> "-3"
assert.ok(tnxChg._classes.has("down"), "tnx negative delta should be 'down'");

// Out-of-order (older ts) ws frame must NOT overwrite.
wsInstance.onmessage({ data: JSON.stringify({ sym: "^TNX", price: 99.9, chgPct: 0, prevClose: 42.25, ts: 1, basis: "quote" }) });
assert.equal(tnxPx.textContent, "4.20%", "out-of-order ws frame must be dropped");

console.log("live_tape.test.mjs: all assertions passed");
