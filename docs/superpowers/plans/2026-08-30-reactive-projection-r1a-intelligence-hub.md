# Intelligence Hub Market Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one page-complete, honestly labelled regular-session Market Pulse for the exact rendered Intelligence Hub roster without changing intelligence authority or perturbing Terminal users' extended-hours demand.

**Architecture:** R1A is one user capability delivered through two ordered modifying children. R1A-T extends the canonical Terminal `/quotes` owner with a non-disruptive `view=regular` option. After that contract is merged, deployed and proven, R1A-M adds the Macro batch projection, durable markup, one route-scoped controller and production browser proof. Streaming remains R1B.

**Tech Stack:** Node.js 18+ built-in tests, existing Terminal Quote Hub, Python 3, FastAPI, Jinja2, vanilla JavaScript, pytest, existing browser/evidence harnesses.

**Spec:** `docs/superpowers/specs/2026-08-30-reactive-projection-platform-design.md`

## Global constraints

- R0 architecture must be accepted and merged before either implementation child STARTs.
- R1A-T and R1A-M use separate operation keys and GitHub carriers; neither inherits START.
- R1A-M is blocked until R1A-T is merged, deployed and production-proven on the actual Terminal host.
- Terminal Quote Plane remains the sole current-US-quote owner.
- No second quote source, store, cache service, event bus, scheduler, retry plane, identity plane or correction ledger.
- The exact R1A roster is `command[:30] + emerging[:14] + discovery_shown[:14]`, ordered and deduplicated: at most 58 unique symbols.
- Macro route cap is 60 unique symbols; browser refuses more than 58 rendered unique symbols.
- Every occurrence of one symbol is one visual unit and commits in the same animation frame.
- R1A-T `view=regular` must spend zero ExtFeed demand/LRU capacity.
- R1A-M must explicitly request `view=regular`; no fallback to default/full view.
- Nightly selection, order, score, stage, stance, Prophet state, entry state, allocation and trade authority are immutable.
- One route-scoped controller owns R1A nodes; generic `live.js` cannot own the same DOM.
- One browser request and one Terminal upstream request per refresh; no per-card calls and no retry.
- Macro access is deliberately public quote-only; this decision is printed and tested.
- Controller asset must be public in both `config/site_access.yml` and `app/deploy/Caddyfile`.
- Rate limits are symbol-weighted.
- Freshness, session and coverage are orthogonal.
- Stateless snapshot only: no server sequence, cursor or correction store.
- Browser request ordering uses local generation; item ordering uses source time plus revision equality.
- `chg` is percentage, not dollars; derive absolute move.
- Unknown basis/session/clock fails downward.
- Public output contains no provider/source/basis/anchor-source/internal-host/path/raw exception.
- UI evidence: dark/light × EN/ZH × 1440/390, plus overflow, console, interaction and degraded-state proof.
- TDD is mandatory: RED before implementation, then GREEN and mutation/discriminator proof.
- Each child stops at its own acceptance boundary and returns an exact continuation handoff.

---

# Child R1A-T — Terminal regular-only quote view

**Repository:** `mastermindx-market-intelligence/mastermind-terminal`  
**Preferred avenue:** `CTO Sol`  
**Why:** bounded but architecture-sensitive quote-owner work with global-demand side effects and host deployment proof.  
**Why not Fable:** product and authority boundaries are frozen; no principal cross-program ambiguity remains.  
**Initial archaeology pin:** `86a75b68c273a592a41af5e322f95aab242b8297`

## Task T1: Freeze the regular-view parser and demand contract with RED tests

**Files:**
- Modify: `hub/tests/quotes.test.js`
- Later modify: `hub/lib/quotes.js`

**Interfaces:**
- Produces future pure interface:
  - `parseQuoteView(rawValues: unknown) -> "full" | "regular" | null`
  - `applyDemand(syms, nowMs, deps, {includeExtended})`
  - `buildQuotesResponse(syms, nowMs, deps, {includeExtended})`

- [ ] **Step 1: Add the missing parser import and failing tests**

Add `parseQuoteView` to the test import before implementation:

```javascript
const {
  parseQuoteView,
  applyDemand,
  buildQuotesResponse,
} = require("../lib/quotes");
```

Add:

```javascript
describe("parseQuoteView — closed endpoint vocabulary", () => {
  it("defaults only an absent value to full", () => {
    assert.equal(parseQuoteView([]), "full");
  });

  it("accepts exactly one full or regular value", () => {
    assert.equal(parseQuoteView(["full"]), "full");
    assert.equal(parseQuoteView(["regular"]), "regular");
  });

  it("rejects unknown, blank and repeated values", () => {
    for (const raw of [[""], ["all"], ["regular", "regular"], ["full", "regular"], null]) {
      assert.equal(parseQuoteView(raw), null);
    }
  });
});
```

- [ ] **Step 2: Add a demand spy that includes SnapshotFeed**

Use:

```javascript
function demandSpies() {
  const seen = { snapshot: [], polygon: [], anchor: [], ext: [], macro: [] };
  return {
    seen,
    deps: {
      snapshotFeed: { demand: (s) => seen.snapshot.push(s) },
      polygon: {
        isHealthy: () => true,
        ensureSubscribed: (s) => seen.polygon.push(s),
      },
      anchorCache: { resolve: async (s) => { seen.anchor.push(s); } },
      extFeed: { demand: (s) => seen.ext.push(s) },
      macroFeed: { demand: (s) => seen.macro.push(s) },
    },
  };
}
```

- [ ] **Step 3: Add the regular-demand RED test**

```javascript
it("regular view preserves regular demand and spends zero ext slots", () => {
  const { seen, deps } = demandSpies();
  applyDemand(["AAPL", "NVDA"], NOW, deps, { includeExtended: false });
  assert.deepEqual(seen.snapshot, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.polygon, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.anchor, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.ext, []);
});
```

- [ ] **Step 4: Add the default-full compatibility test**

```javascript
it("default/full view keeps existing ext demand", () => {
  for (const options of [undefined, { includeExtended: true }]) {
    const { seen, deps } = demandSpies();
    applyDemand(["AAPL"], NOW, deps, options);
    assert.deepEqual(seen.snapshot, ["AAPL"]);
    assert.deepEqual(seen.polygon, ["AAPL"]);
    assert.deepEqual(seen.anchor, ["AAPL"]);
    assert.deepEqual(seen.ext, ["AAPL"]);
  }
});
```

- [ ] **Step 5: Add the response-assembly RED test**

```javascript
it("regular response passes no ext feed into Store and strips legacy ext keys", () => {
  let seenExt = "unset";
  const store = {
    getQuotes(_syms, _now, extFeed) {
      seenExt = extFeed;
      return {
        AAPL: {
          sym: "AAPL",
          last: 200,
          prevClose: 198,
          chg: 1.0101,
          ts: TS,
          live: true,
          source: "polygon-live",
          basis: "LIVE",
          // legacy/poisoned row: the regular view must strip these at the
          // response boundary even though no ExtFeed was consulted
          extPrice: 201,
          extChg: 1.5,
          extTs: TS,
          extSession: "post",
          extSource: "webull",
          extBasis: "EXT",
        },
      };
    },
  };
  const out = buildQuotesResponse(
    ["AAPL"], NOW, { store, extFeed: { getExt() { throw new Error("must not run"); } } },
    { includeExtended: false }
  );
  assert.equal(seenExt, null);
  for (const key of ["extPrice", "extChg", "extTs", "extSession", "extSource", "extBasis"]) {
    assert.equal(key in out.AAPL, false);
  }
});
```

- [ ] **Step 6: Run RED**

```bash
cd hub
node --test tests/quotes.test.js
```

Expected: failures because `parseQuoteView` and the options contract do not exist and ExtFeed is still passed.

- [ ] **Step 7: Commit RED tests only**

```bash
git add hub/tests/quotes.test.js
git commit -m "test(hub): pin regular-only quote demand"
```

## Task T2: Implement the pure regular-view owner contract

**Files:**
- Modify: `hub/lib/quotes.js`
- Modify: `hub/hub.js`
- Test: `hub/tests/quotes.test.js`

**Interfaces:**
- Consumes the RED tests from T1.
- Produces the closed `view=full|regular` behavior.

- [ ] **Step 1: Implement `parseQuoteView`**

In `hub/lib/quotes.js`:

```javascript
function parseQuoteView(rawValues) {
  if (!Array.isArray(rawValues)) return null;
  if (rawValues.length === 0) return "full";
  if (rawValues.length !== 1) return null;
  const value = String(rawValues[0] || "").trim().toLowerCase();
  return value === "full" || value === "regular" ? value : null;
}
```

Export it.

- [ ] **Step 2: Add `includeExtended` to demand without changing default**

```javascript
function applyDemand(syms, nowMs, deps = {}, options = {}) {
  const includeExtended = options.includeExtended !== false;
  // existing routing unchanged
  // ...
  if (includeExtended && extFeed) extFeed.demand(sym);
}
```

Do not clock-gate this branch. Regular view suppresses ext demand in every session.

- [ ] **Step 3: Add `includeExtended` to response assembly**

```javascript
function buildQuotesResponse(syms, nowMs, deps = {}, options = {}) {
  const includeExtended = options.includeExtended !== false;
  // ...
  const served = store.getQuotes(
    storeSyms,
    nowMs,
    includeExtended ? extFeed : null,
    snapshotFeed
  );
  if (!includeExtended) {
    for (const sym of Object.keys(served)) {
      const row = served[sym];
      const clean = {};
      for (const key of Object.keys(row)) {
        if (!key.startsWith("ext")) clean[key] = row[key];
      }
      served[sym] = clean;
    }
  }
}
```

Default behavior remains full. The `ext*` strip runs over whatever the Store
returned, so the response boundary stays closed even for a legacy or poisoned
Store row that never touched ExtFeed; it copies rather than mutating rows the
Store may share.

- [ ] **Step 4: Wire `hub.js`**

In `handleQuotes`:

```javascript
const view = parseQuoteView(url.searchParams.getAll("view"));
if (view == null) return sendJSON(res, 400, { error: "invalid view" });
const options = { includeExtended: view === "full" };
applyDemand(syms, now, deps, options);
const out = buildQuotesResponse(syms, now, deps, options);
```

Import/re-export `parseQuoteView` as needed. Do not add another endpoint.

- [ ] **Step 5: Run focused GREEN**

```bash
cd hub
node --test tests/quotes.test.js tests/extfeed.test.js
```

Expected: all existing and new tests pass.

- [ ] **Step 6: Run the complete Hub suite**

```bash
cd hub
npm test
```

Expected: zero failures.

- [ ] **Step 7: Mutation-check load-bearing branches**

For each mutation, run `node --test tests/quotes.test.js` and prove RED, then restore:

```text
remove includeExtended guard around extFeed.demand
always pass extFeed to Store
skip the regular-view ext-key strip over Store rows
make unknown view default to full
make regular view skip SnapshotFeed
make default view regular
```

- [ ] **Step 8: Verify no accidental source expansion**

```bash
git diff --check
git diff --name-only <PICKUP_BASE>...HEAD
```

Expected changed paths at this task boundary:

```text
hub/hub.js
hub/lib/quotes.js
hub/tests/quotes.test.js
```

- [ ] **Step 9: Commit GREEN**

```bash
git add hub/hub.js hub/lib/quotes.js hub/tests/quotes.test.js
git commit -m "feat(hub): add non-disruptive regular quote view"
```

## Task T3: Review, deploy and prove the Terminal owner extension

**Files:**
- No new implementation path expected.
- Update existing repo documentation only if current terminal repository law requires endpoint documentation in the same PR.

- [ ] **Step 1: Reconcile current Terminal master and open path owners**

Pin:

```text
master SHA
branch head
merge base
open PRs touching hub/hub.js, hub/lib/quotes.js, hub/tests/quotes.test.js
VPS/live host code identity
```

Any overlapping semantic writer or unknown host drift returns to Sol.

- [ ] **Step 2: Open one R1A-T PR**

PR body must state:

```text
machine capability: regular-only canonical quote view
no new endpoint/source/store
zero ExtFeed demand in regular view
default full behavior unchanged
no Macro/user-facing completion claim
exact tests and mutation receipts
host deployment/proof plan
```

Keep HOLD-FOR-SOL until independent review and exact-head checks conclude.

- [ ] **Step 3: Independent exact-head review**

Reviewer must verify:

- default/full compatibility;
- regular demand still reaches SnapshotFeed/Polygon/AnchorCache;
- zero ExtFeed demand and merge;
- unknown view refusal;
- no second source/endpoint/store;
- test discrimination;
- host rollout reversibility.

- [ ] **Step 4: Merge only after current exact-head approval**

Use current repository merge law. Green CI is necessary, not sufficient.

- [ ] **Step 5: Deploy through the existing Terminal Hub owner**

Do not invent a new daemon or deployment path. Verify the running Hub code/commit identity after deployment.

- [ ] **Step 6: Run loopback default compatibility probe**

```bash
curl --fail --silent --show-error \
  'http://127.0.0.1:3100/quotes?syms=AAPL&view=full'
curl --fail --silent --show-error \
  'http://127.0.0.1:3100/quotes?syms=AAPL'
```

Normalize only nondeterministic timestamps and verify semantic equality.

- [ ] **Step 7: Prove regular response and zero LRU effect**

Capture `/health` ExtFeed membership/size evidence using the existing accepted diagnostic surface, then issue one request containing 58 safe US symbols:

```bash
curl --fail --silent --show-error \
  'http://127.0.0.1:3100/quotes?syms=<58_URL_ENCODED_SYMBOLS>&view=regular'
```

Verify:

```text
response is flat present-entries-only object
no extPrice/extChg/extTs/extSession/extSource/extBasis anywhere
ExtFeed membership/order/size unchanged by the request
regular SnapshotFeed/Polygon demand remains observable
unknown view returns HTTP 400
```

If existing `/health` does not expose exact membership, use one temporary read-only host probe against the running process's existing diagnostic seam; do not add a production registry merely to prove the PR.

- [ ] **Step 8: Return R1A-T result and STOP**

Return exact head, merge SHA, deployed identity, commands/results, before/after demand proof, failures, and capability state:

```text
R1A-T = PROVEN_LIVE
R1A-M = NOT_BUILT
R1A product = NOT_BUILT
```

The worker child then receives explicit terminal STOP. No Macro START is inherited.

---

# Child R1A-M — Macro Intelligence Hub Market Pulse

**Repository:** `mastermindx-market-intelligence/macro`  
**Preferred avenue:** `CTO Sol`  
**Why:** bounded cross-layer implementation with API, template, browser, access and production proof after architecture freeze.  
**Why not Fable:** R1A-T proof and this plan remove the cross-system ambiguity; one specialist can execute the frozen vertical.

## Task M0: Prove prerequisites before START

- [ ] **Step 1: Re-pin current protected Skillpack**

Load INDEX and all required skills from one current protected SHA.

- [ ] **Step 2: Verify R1A-T production proof**

Require all of:

```text
Terminal PR merged
running Terminal Hub commit identified
view=regular accepted
unknown view refused
58-symbol regular request produced zero ExtFeed LRU change
default full behavior unchanged
```

Missing proof means `BLOCKED / R1A_T_NOT_PROVEN`; do not emulate the contract in Macro.

- [ ] **Step 3: Reconcile current Macro paths and owners**

Census expected paths, current `app/dossier_quote.py`, Intelligence Hub builder/template, site-access/Caddy owners, CI packs and open PR overlaps. A real semantic collision returns to Sol.

- [ ] **Step 4: Emit separate START**

Only after M0 gates clear. Use one branch/PR carrier for R1A-M.

## Task M1: Extract one shared public regular quote projector

**Files:**
- Create: `app/public_quote_projection.py`
- Modify: `app/dossier_quote.py`
- Test: `tests/test_public_quote_projection.py`
- Test: `tests/test_dossier_quote_api.py`
- Test: `tests/test_dossier_live_quote_surface.py`

**Interfaces:**

```python
project_regular_quote(
    row: Mapping[str, Any],
    *,
    ticker: str,
    now: float,
    published_at: str,
) -> PublicQuote
```

```python
@dataclass(frozen=True)
class PublicQuote:
    symbol: str
    price: float
    change_abs: float | None
    change_pct: float | None
    currency: str | None
    session: Literal["regular", "pre", "post", "closed"]
    freshness: Literal["live", "delayed", "stale"]
    observed_at: str
    received_at: str | None
    published_at: str
    regular_session_date: str | None
    revision: str
```

- [ ] **Step 1: Write RED shared-semantic fixtures**

```python
def test_chg_is_percent_and_absolute_move_is_derived():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.change_abs == pytest.approx(HUB_NVDA_RTH["last"] - HUB_NVDA_RTH["prevClose"])
    assert q.change_pct == pytest.approx(HUB_NVDA_RTH["chg"])


def test_closed_regular_print_is_settled_not_immediately_stale():
    q = project_regular_quote(HUB_NVDA_CLOSED, ticker="NVDA", now=CLOSED_NOW, published_at=PUBLISHED)
    assert q.session == "closed"
    assert q.freshness != "stale"


def test_extended_fields_cannot_replace_regular_tuple():
    q = project_regular_quote(HUB_OPPOSITE_SIGNS, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.change_pct > 0
    assert HUB_OPPOSITE_SIGNS["extChg"] < 0
```

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/test_public_quote_projection.py -q
```

- [ ] **Step 3: Implement pure deterministic projector**

Preserve dossier behavior. `revision` is a deterministic equality fingerprint over source identity/time and projected values. `received_at` is null unless upstream supplies a trustworthy receive clock. Projection time cannot determine freshness.

- [ ] **Step 4: Replace dossier duplicate semantics**

Keep dossier-specific HTTP/schema/rate ownership in `app/dossier_quote.py`.

- [ ] **Step 5: Run GREEN and mutations**

```bash
python3 -m pytest \
  tests/test_public_quote_projection.py \
  tests/test_dossier_quote_api.py \
  tests/test_dossier_live_quote_surface.py -q
```

Mutations that must red:

```text
read chg as dollars
freshen from published_at
apply RTH stale bound while closed
allow unknown basis live
use extChg
fabricate received_at
```

- [ ] **Step 6: Commit**

```bash
git add app/public_quote_projection.py app/dossier_quote.py \
  tests/test_public_quote_projection.py tests/test_dossier_quote_api.py
git commit -m "refactor(quotes): share regular public projection"
```

## Task M2: Add the deliberate public bounded batch API

**Files:**
- Create: `app/intelligence_hub_market_pulse.py`
- Modify: `app/main.py`
- Modify only if current trigger disproves ownership: `app/deploy/update.sh`
- Test: `tests/test_intelligence_hub_market_pulse_api.py`

**Public contract:**

```http
GET /api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT
```

- [ ] **Step 1: Write RED API tests**

Required fixture:

```python
def test_route_uses_one_regular_view_upstream_call(client, fake_hub):
    symbols = ",".join(f"T{i:02d}" for i in range(58))
    response = client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}")
    assert response.status_code == 200
    assert fake_hub.calls == 1
    assert fake_hub.last_query["view"] == "regular"
    assert fake_hub.last_symbols == [f"T{i:02d}" for i in range(58)]
```

Also pin:

```python
def test_regular_view_ext_field_leak_is_503(client, fake_hub):
    fake_hub.rows["AAPL"]["extPrice"] = 201.0
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503
    assert r.json() == {"detail": "quote_projection_unavailable"}
```

Test deliberate anonymous access, signed-in parity, 0/>60/invalid, order/dedupe, complete/partial/no usable, exact arithmetic, redirect/timeout/oversize/malformed, debranding, no retry, no sequence/cursor/correction store, and symbol-weighted budgets.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/test_intelligence_hub_market_pulse_api.py -q
```

- [ ] **Step 3: Implement input and roster-safe bounds**

Preserve first occurrence, reject invalid members, dedupe, and reject more than 60 unique symbols. Do not silently drop invalid input.

- [ ] **Step 4: Implement symbol-weighted limiter**

Reuse existing edge-resolved client/peer identity pattern with bounded in-memory rolling `(timestamp, units)` entries. Each unique symbol costs one unit. Test normal 58-name 60-second cadence plus manual/resume margin and high-rate amplification refusal.

- [ ] **Step 5: Implement exactly one loopback call**

```text
base: http://127.0.0.1:3100
path: /quotes
view: regular
timeout: 2.5s
max bytes: 262144
redirects: no
attempts: one
```

Never omit the view or fall back to full/default.

- [ ] **Step 6: Reject regular-view contract violations**

Any response row containing a key with the frozen extended-field vocabulary is an upstream contract failure. Do not strip and continue.

- [ ] **Step 7: Build stateless envelope**

```text
zero usable -> 503
otherwise availability=available
freshness=worst(live, delayed, stale)
coverage=complete iff missing=0 else partial
source_view=regular
```

No server sequence/cursor/correction map.

- [ ] **Step 8: Register in existing app owner**

Module docstring says “deliberately public quote-only projection” and why. Confirm `app/*.py` restart ownership before touching deploy script.

- [ ] **Step 9: Run GREEN and mutation matrix**

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_api.py \
  tests/test_dossier_quote_api.py -q
python3 -c "import app.main; print('app import ok')"
```

Mutations that must red:

```text
N upstream calls
omit view=regular
fallback to full after failure
strip ext leak instead of refusing
drop missing denominator
collapse partial into freshness
majority hides delayed/stale
forward source/basis/anchor_source
retry once
non-loopback URL
one unit per batch
server sequence field
```

- [ ] **Step 10: Commit**

```bash
git add app/intelligence_hub_market_pulse.py app/main.py \
  tests/test_intelligence_hub_market_pulse_api.py
git commit -m "feat(intel-hub): add regular market pulse projection"
```

Add `app/deploy/update.sh` only if changed by current evidence.

## Task M3: Render the exact durable roster and multi-target markup

**Files:**
- Modify: `templates/intelligence_hub.html.j2`
- Modify only if the builder needs an explicit presentation list: `scripts/build_intel_hub.py`
- Test: `tests/test_intelligence_hub_market_pulse_surface.py`
- Generated by normal builder when repo law requires: `site/intelligence_hub.html`

**Selectors:**

```text
[data-ihmp-root]
[data-ihmp-availability]
[data-ihmp-freshness]
[data-ihmp-session]
[data-ihmp-coverage]
[data-ihmp-symbol]
[data-ihmp-price]
[data-ihmp-abs]
[data-ihmp-pct]
[data-ihmp-baseline-at]
```

- [ ] **Step 1: Write RED roster tests**

Prove:

```python
assert roster == ordered_unique(command[:30] + emerging[:14] + discovery_shown[:14])
assert len(roster) <= 58
assert hidden_discovery_symbol not in roster
assert exhausted_symbol not in roster
```

Render a duplicate symbol in two panels and prove two `data-ihmp-symbol="AAPL"` targets exist while the unique request roster contains AAPL once.

- [ ] **Step 2: Add invariance tests**

Snapshot order, opportunity score, stage, entry badge and stance before/after the markup change.

- [ ] **Step 3: Run RED**

```bash
python3 -m pytest tests/test_intelligence_hub_market_pulse_surface.py -q
```

- [ ] **Step 4: Render one compact page-level instrument**

Tier-1 EN copy:

```text
Prices from the latest settled build
Checking current prices
Live market pulse · 30/30 names
Live prices for 27/30 names
Delayed market pulse · 30/30 names
Delayed prices · 27/30 names
Settled close · 30/30 names
Market pulse has stopped updating
Current prices temporarily unavailable
```

Provide plain equivalent Chinese; technical clocks/errors live in tooltips.

- [ ] **Step 5: Render stable quote clusters for every eligible occurrence**

Do not create a second ticker link or change `.tk`. R1A nodes must not match generic `.nb-px[data-sym]`/`.nb-chg[data-sym]` ownership.

- [ ] **Step 6: Author governed dark/light CSS**

Dark: graphite instrument and restrained page-level luminance. Light: white research material, cool canvas, hairline and small shadow, no copied glow. Use semantic tokens and `--ink-up`/`--ink-down`; no runtime stylesheet.

- [ ] **Step 7: Run render and house guards**

```bash
python3 -m scripts.build_intel_hub
python3 -m pytest tests/test_intelligence_hub_market_pulse_surface.py -q
python3 scripts/check_template_site_sync.py
python3 scripts/check_title_i18n.py
python3 scripts/check_validated_claims.py
```

- [ ] **Step 8: Commit**

```bash
git add templates/intelligence_hub.html.j2 \
  scripts/build_intel_hub.py \
  tests/test_intelligence_hub_market_pulse_surface.py \
  site/intelligence_hub.html
git commit -m "feat(intel-hub): render exact market pulse roster"
```

Omit unchanged/generated-unrequired paths.

## Task M4: Add one atomic multi-target controller and serving boundary

**Files:**
- Create: `site/assets/js/intelligence-hub-market-pulse.js`
- Modify: `templates/intelligence_hub.html.j2`
- Modify: `config/site_access.yml`
- Modify: `app/deploy/Caddyfile`
- Test: `tests/test_intelligence_hub_market_pulse_client.py`
- Test: `tests/test_site_access_boundary.py`
- Test only if needed: `tests/test_lens_nested_control_taps.py`

- [ ] **Step 1: Write RED client tests**

Prove:

```text
58 unique symbols with duplicate DOM occurrences -> one fetch
controller maps symbol to all targets
partial response updates accepted targets in one RAF and leaves missing baked
old local generation ignored
older source time suppressed with coverage recomputed
equal time/equal revision idempotent
equal time/changed revision accepted as correction
snapshot_id never orders
hidden tab pauses
visibility resume makes one request
live setting disabled makes zero requests
malformed source_view/state/arithmetic/duplicate/ext field makes zero DOM mutation
score/order/stage nodes unchanged
```

- [ ] **Step 2: Write serving-boundary RED tests**

The exact controller path must be in both public lists. No broad assets/data prefix or signal JSON is opened.

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_site_access_boundary.py -q
```

- [ ] **Step 3: Implement target discovery**

Build:

```javascript
const targetsBySymbol = new Map();
const orderedSymbols = [];
```

Traverse `[data-ihmp-symbol]` in DOM order. Add every node to the symbol's array, but add each symbol to `orderedSymbols` once. Refuse activation if `orderedSymbols.length > 58`.

- [ ] **Step 4: Implement immutable response validation**

Require exact schema/projection/source_view, allowlisted state axes/session/freshness, finite values, requested unique identities, exact arithmetic and no forbidden ext/source/provider fields. Build a candidate model before DOM writes.

- [ ] **Step 5: Implement lifecycle and ordering**

One `AbortController`, one in-flight request and local generation. Maintain page-lifetime `{observedAt, revision}` per symbol. Suppress older items and recompute coverage/state before paint.

- [ ] **Step 6: Implement atomic multi-target paint**

Inside one `requestAnimationFrame`:

1. update every node array for each accepted symbol with the same tuple;
2. retain baked values for missing/suppressed symbols;
3. update availability/freshness/session/coverage/time;
4. emit one polite live-region change.

No response may partially paint one panel before another.

- [ ] **Step 7: Add exact controller asset to both serving owners**

Open only:

```text
/assets/js/intelligence-hub-market-pulse.js
```

in `config/site_access.yml` and `app/deploy/Caddyfile`, preserving byte/order parity.

- [ ] **Step 8: Preserve ticker-to-Terminal interaction**

Do not change `.tk`/`theme.js` ownership. Quote clusters cannot swallow pointer/keyboard action.

- [ ] **Step 9: Run GREEN and mutations**

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_intelligence_hub_market_pulse_surface.py \
  tests/test_site_access_boundary.py \
  tests/test_lens_nested_control_taps.py -q
grep -n "data-ihmp" templates/live.js site/live.js || true
```

Mutations that must red:

```text
one target per symbol instead of all
remove generation check
use snapshot_id to order
paint before complete validation
remove RAF transaction
partial clears missing
ignore live-disabled
remove one serving-list entry
open broad asset/data prefix
```

- [ ] **Step 10: Commit**

```bash
git add site/assets/js/intelligence-hub-market-pulse.js \
  templates/intelligence_hub.html.j2 \
  config/site_access.yml app/deploy/Caddyfile \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_site_access_boundary.py \
  tests/test_lens_nested_control_taps.py
git commit -m "feat(intel-hub): paint market pulse atomically"
```

Omit unchanged files.

## Task M5: CI, visual evidence and behavior proof

**Files:**
- Modify current owning CI pack only: `.github/ci/legacy-jobs.yml` and/or current planner-owned file proven by archaeology
- Modify `.github/workflows/ci.yml` only when current path filter requires it
- Modify `config/unrun_test_baseline.json` only when current audit requires it
- Create: `mockups/evidence/reactive-projection/r1a-intelligence-hub/EVIDENCE.yml`
- Create: `mockups/evidence/reactive-projection/r1a-intelligence-hub/manifest.json`
- Create screenshots in that directory

- [ ] **Step 1: Bind all tests to the existing CI owner**

No second broad CI job. Include every production subject so UI/access/API changes cannot dark their tests.

- [ ] **Step 2: Run exact focused matrix**

```bash
python3 -m pytest \
  tests/test_public_quote_projection.py \
  tests/test_dossier_quote_api.py \
  tests/test_dossier_live_quote_surface.py \
  tests/test_intelligence_hub_market_pulse_api.py \
  tests/test_intelligence_hub_market_pulse_surface.py \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_site_access_boundary.py \
  tests/test_lens_nested_control_taps.py -q
python3 scripts/audit_unrun_tests.py
python3 scripts/check_design_system.py --mode enforce-added
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_ui_visual_evidence.py
python3 scripts/check_template_site_sync.py
```

Run every additional current house guard selected for touched paths.

- [ ] **Step 3: Capture the eight-cell matrix**

```text
dark EN 1440
dark ZH 1440
light EN 1440
light ZH 1440
dark EN 390
dark ZH 390
light EN 390
light ZH 390
```

Across evidence, include live, partial, delayed or settled, and unavailable states. Both art directions need degraded proof. Record requested/applied locale/theme/viewport, console, overflow, network and screenshot path.

- [ ] **Step 4: Capture behavior receipts**

Prove:

```text
anonymous shell loads controller
anonymous route contains no provider/private fields
one browser call and one Terminal view=regular call per refresh
no full-view fallback
no per-symbol route call
58-symbol roster bound
all duplicate occurrences match
one committed frame
normal cadence passes weighted budget; amplification fails
background pause/resume works
live-disabled no request
ticker opens Terminal
intelligence fingerprint unchanged
```

- [ ] **Step 5: Commit CI/evidence**

```bash
git add .github/ci/legacy-jobs.yml .github/workflows/ci.yml \
  config/unrun_test_baseline.json \
  mockups/evidence/reactive-projection/r1a-intelligence-hub/
git commit -m "test(intel-hub): enforce regular pulse proof matrix"
```

Omit unchanged CI/baseline files. Evidence is mandatory for material UI work.

## Task M6: PR, review, deployment and production acceptance

**Durable records after proof:**
- Update `agentos/workstreams/WS-BREATHING-PLATFORM.md` only at accepted boundary.
- Create `agentos/handoffs/BREATHING-PLATFORM-2026-08-31-reactive-projection-r1a.md`.
- Add a discovery only for a genuinely reusable falsifiable fact; do not create a status diary.

- [ ] **Step 1: Reconcile exact branch and current main**

Confirm one carrier, no unrelated generated/data churn, no same-path writer and current R1A-T deployed proof.

- [ ] **Step 2: Open one R1A-M PR**

Body prints:

```text
observation-only
Terminal view=regular canonical owner
zero ext-demand inherited proof
deliberately public quote-only route
exact rendered roster and multi-target atomicity
no rank/score/stage/Prophet/trade mutation
no server sequence/correction store
no streaming
local/hosted/mutation/browser/deploy proof
```

- [ ] **Step 3: Independent exact-head review**

Review duplicate-source/DOM risks, regular-view enforcement, quote semantics, public rights/access, weighted abuse, multi-target ordering/correction, degraded product behavior and intelligence invariance.

- [ ] **Step 4: Consume every binding check**

Pending is not green. A nonbinding exclusion requires current evidence.

- [ ] **Step 5: Merge and deploy through existing owners**

Verify:

```text
Macro API running commit
static controller/page cache stamp
site-access/Caddy parity
anonymous controller and route
one known tuple against Terminal regular view
no provider/ext fields
```

- [ ] **Step 6: Run real production normal proof**

Capture the same source tuple through Terminal regular view, Macro projection and visible page; include clocks, state axes, unique coverage, one-call network receipt, weighted units, duplicate-target equality and unchanged intelligence fingerprint.

- [ ] **Step 7: Run reversible degraded proof**

Use an accepted feature/canary/fixture seam, not vendor sabotage, to prove partial, unsupported/malformed regular view and unavailable fallback. Restore and prove recovery.

- [ ] **Step 8: Adjudicate capability state**

Only after real proof:

```text
R0 = accepted/merged
R1A-T = PROVEN_LIVE
R1A-M = PROVEN_LIVE
R1A user capability = PROVEN_LIVE
R1B = NOT_BUILT
broader reactive platform = PARTIAL
```

- [ ] **Step 9: Durable handoff and explicit STOP**

Record exact heads/merges/deployments/browser receipts, residuals and the held R1B gate. Send terminal STOP to the worker and remove only that child watcher source. No successor inherits START.

- [ ] **Step 10: Stop**

Do not absorb R1B, other pages, personalization, broad orchestration or material intelligence deltas.
