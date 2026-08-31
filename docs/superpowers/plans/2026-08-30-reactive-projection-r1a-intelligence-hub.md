# Intelligence Hub Market Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one page-complete, honestly labelled, batched current-price-and-move projection to the existing Intelligence Hub without changing any intelligence authority.

**Architecture:** Reuse the Terminal Quote Plane through Macro's existing loopback public-projection pattern. Extract shared quote semantics once, expose one deliberately public bounded batch API, hydrate durable Intelligence Hub markup through one route-scoped controller, open only that controller asset through the existing serving boundary, and prove normal/degraded product behavior. Do not build streaming or a generic platform in this wave.

**Tech Stack:** Python 3, FastAPI, Jinja2, vanilla JavaScript, pytest, existing browser/evidence harnesses.

**Spec:** `docs/superpowers/specs/2026-08-30-reactive-projection-platform-design.md`

## Global Constraints

- Implement only R1A. SSE/WebSocket/ordered-delta transport is R1B and is prohibited here.
- Terminal Quote Plane remains the sole current-US-quote owner.
- Nightly Intelligence Hub selection/order/score/stage/stance/entry state is immutable in this wave.
- One browser controller owns R1A quote nodes; generic `live.js` must not own the same DOM.
- One batch route call per refresh, 1–80 unique symbols, one upstream read, no retry.
- The route is deliberately public quote-only access; the decision is printed and tested.
- The controller asset must be public in both `config/site_access.yml` and the matching Caddy boundary.
- Rate limits are symbol-weighted; an 80-symbol request cannot cost one ordinary request slot.
- Feed freshness, market session and coverage are separate facts.
- R1A is stateless: no server sequence, cursor or correction ledger.
- Browser request order uses a local generation; item order uses source time plus revision equality.
- Source/market time, optional receive time, projection time and baseline time remain distinct.
- `chg` is percentage, not dollars; absolute move is derived.
- Freshness is session-aware and fails downward.
- Provider/source/basis/anchor names are not public payload/UI.
- No new database, event bus, scheduler, retry daemon, identity plane or runtime stylesheet.
- All user-facing work requires dark/light × EN/ZH × 1440/390 evidence.
- Use TDD: every behavioral change begins with a failing test and ends with discriminating proof.
- One PR owns producer + consumer + UI + tests + production proof.

---

### Task 1: Extract one shared public quote semantic owner

**Files:**
- Create: `app/public_quote_projection.py`
- Modify: `app/dossier_quote.py`
- Test: `tests/test_public_quote_projection.py`
- Test: `tests/test_dossier_quote_api.py`

**Interfaces:**
- Consumes: one raw Terminal Quote Plane row, canonical `ticker`, injected `now`.
- Produces:
  - `project_regular_quote(row: Mapping[str, Any], *, ticker: str, now: float) -> PublicQuote`
  - `ProjectionError(code: str)`
  - `PublicQuote.to_dict() -> dict[str, Any]`
- Existing dossier route must preserve its public schema and status behavior.

- [ ] **Step 1: Freeze the existing dossier behavior with focused regression fixtures**

Add assertions covering:

```python
def test_shared_projection_treats_chg_as_percent():
    projected = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW)
    assert projected.change_abs == pytest.approx(
        HUB_NVDA_RTH["last"] - HUB_NVDA_RTH["prevClose"]
    )
    assert projected.change_pct == pytest.approx(HUB_NVDA_RTH["chg"])


def test_shared_projection_keeps_settled_close_valid_after_hours():
    projected = project_regular_quote(HUB_NVDA_CLOSED, ticker="NVDA", now=CLOSED_NOW)
    assert projected.session == "closed"
    assert projected.freshness != "stale"


def test_extended_move_never_replaces_regular_move():
    projected = project_regular_quote(HUB_OPPOSITE_SIGNS, ticker="NVDA", now=NOW)
    assert projected.change_pct > 0
    assert HUB_OPPOSITE_SIGNS["extChg"] < 0
```

- [ ] **Step 2: Run the new suite to verify it fails before extraction**

```bash
python3 -m pytest tests/test_public_quote_projection.py -q
```

Expected: collection/import failure because the shared module/interface does not yet exist.

- [ ] **Step 3: Implement the minimal pure module**

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

Rules:

- `revision` is a deterministic equality fingerprint over source identity/time and projected values; it is not a monotonic counter.
- `received_at` is null unless the current upstream exposes a trustworthy receive clock.
- `published_at` is supplied by the route assembler, not used to classify freshness.
- Never add `correction=true` unless the canonical upstream actually supplies a correction fact. R1A infers equal-time changed-content correction client-side.

- [ ] **Step 4: Replace dossier-internal duplicate semantics with the shared function**

Keep dossier-specific HTTP, rate limiting and schema assembly in `app/dossier_quote.py`; remove only logic now owned by `public_quote_projection.py`.

- [ ] **Step 5: Run shared + dossier tests**

```bash
python3 -m pytest \
  tests/test_public_quote_projection.py \
  tests/test_dossier_quote_api.py \
  tests/test_dossier_live_quote_surface.py -q
```

Expected: all pass; existing dossier response fixtures remain semantically unchanged.

- [ ] **Step 6: Mutation-check the load-bearing guards**

Each mutation must red a targeted test:

```text
read chg as absolute dollars
classify freshness from projection time
apply regular-session stale bound while closed
allow unknown basis to be live
use extChg as day move
accept prevClose == 0 for percentage derivation
fabricate received_at from request time
```

Restore exact code and rerun the three suites green.

- [ ] **Step 7: Commit**

```bash
git add app/public_quote_projection.py app/dossier_quote.py \
  tests/test_public_quote_projection.py tests/test_dossier_quote_api.py
git commit -m "refactor(quotes): share honest public quote projection"
```

---

### Task 2: Add the deliberately public bounded batch API

**Files:**
- Create: `app/intelligence_hub_market_pulse.py`
- Modify: `app/main.py`
- Modify only if current owner inspection disproves the existing `app/*.py` trigger: `app/deploy/update.sh`
- Test: `tests/test_intelligence_hub_market_pulse_api.py`

**Interfaces:**
- Consumes:
  - `project_regular_quote(...)` from Task 1.
  - loopback Quote Hub `GET /quotes?syms=...`.
- Produces:
  - `GET /api/intelligence-hub/market-pulse?symbols=...`
  - schema `intelligence_hub.market_pulse.v1`.

- [ ] **Step 1: Write API tests before the route**

Create a fake single-call upstream reader and assert:

```python
def test_batch_route_reads_upstream_once_for_thirty_symbols(client, fake_hub):
    symbols = ",".join(f"T{i:02d}" for i in range(30))
    response = client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}")
    assert response.status_code == 200
    assert fake_hub.calls == 1
    assert fake_hub.last_symbols == [f"T{i:02d}" for i in range(30)]


def test_partial_response_keeps_freshness_and_coverage_orthogonal(client, fake_hub):
    response = client.get(
        "/api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT"
    )
    body = response.json()
    assert body["state"] == {
        "availability": "available",
        "freshness": "live",
        "coverage": "partial",
    }
    assert body["coverage"] == {
        "requested": 3,
        "resolved": 2,
        "live": 2,
        "delayed": 0,
        "stale": 0,
        "missing": 1,
    }
    assert [row["symbol"] for row in body["items"]] == ["NVDA", "MSFT"]
    assert body["errors"] == [{"symbol": "AAPL", "code": "quote_unavailable"}]
    assert "sequence" not in body
```

Also test:

- anonymous access succeeds and is documented as intentional;
- signed-in access has the same quote semantics;
- 0, >80, duplicate/order, invalid symbol;
- no usable rows;
- redirect, timeout, oversize, malformed JSON;
- unknown basis/session/clock;
- provider-field absence;
- no retry;
- no server cursor/sequence/correction state;
- symbol-weighted normal cadence and exhaustion.

- [ ] **Step 2: Run the API suite red**

```bash
python3 -m pytest tests/test_intelligence_hub_market_pulse_api.py -q
```

Expected: import/route failures.

- [ ] **Step 3: Implement input normalization**

Use the existing safe ticker validator. Preserve first occurrence order, reject invalid members and reject >80 unique symbols. Do not silently drop invalid input.

- [ ] **Step 4: Implement symbol-weighted rate limiting**

Use the existing edge-resolved client and peer identity pattern, but store bounded rolling `(timestamp, symbol_units)` entries. Each unique symbol costs one unit. Expire old units before admission and cap identity cardinality. Print exact client/peer budgets as constants and test:

```text
largest intended page request at 60-second cadence + reasonable manual refreshes -> allowed
repeated 80-symbol amplification -> 429
one-symbol dossier behavior -> unchanged
```

Do not rewrite the global rate limiter or create persistent quota state.

- [ ] **Step 5: Implement one bounded loopback read**

```text
default base: http://127.0.0.1:3100
timeout: 2.5 seconds
maximum bytes: 262144
redirects: refused
attempts: exactly one
```

Assert loopback per request so a bad environment disables only this route.

- [ ] **Step 6: Build the stateless envelope**

```text
zero usable -> 503
otherwise availability=available
freshness = worst(live, delayed, stale)
coverage = complete iff missing == 0 else partial
```

Validate both arithmetic identities. `snapshot_id` is opaque identity only. Do not add a server sequence/cursor or correction map.

- [ ] **Step 7: Register through the existing app owner**

Add one direct router import/include in `app/main.py`, matching the dossier precedent. The module docstring must say “deliberately public quote-only projection” and explain why. Confirm current `app/deploy/update.sh` already restarts on `app/*.py`; change it only if fresh inspection proves otherwise.

- [ ] **Step 8: Run API + app import tests**

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_api.py \
  tests/test_dossier_quote_api.py -q
python3 -c "import app.main; print('app import ok')"
```

Expected: pass and exactly one route registration.

- [ ] **Step 9: Mutation-check access, one-call, debrand and state axes**

Mutations that must fail:

```text
loop over symbols and read upstream N times
drop missing symbols from requested denominator
collapse partial coverage into freshness
let a majority of live rows hide one delayed/stale row
forward source/basis/anchor_source
retry once after timeout
call a non-loopback URL
mark unknown basis live
count every batch as one rate unit
add/accept a server sequence field
```

- [ ] **Step 10: Commit**

```bash
git add app/intelligence_hub_market_pulse.py app/main.py \
  app/deploy/update.sh tests/test_intelligence_hub_market_pulse_api.py
git commit -m "feat(intel-hub): add batched market pulse projection"
```

Omit `app/deploy/update.sh` if unchanged.

---

### Task 3: Render durable Market Pulse markup in both art directions

**Files:**
- Modify: `templates/intelligence_hub.html.j2`
- Test: `tests/test_intelligence_hub_market_pulse_surface.py`
- Generated by the normal builder, never hand-edit as source: `site/intelligence_hub.html`

**Interfaces:**
- Consumes: current Intelligence Hub `hub` view model and nightly price fields.
- Produces:
  - `[data-ihmp-root]`
  - `[data-ihmp-availability]`
  - `[data-ihmp-freshness]`
  - `[data-ihmp-session]`
  - `[data-ihmp-coverage]`
  - `[data-ihmp-symbol]`
  - `[data-ihmp-price]`
  - `[data-ihmp-abs]`
  - `[data-ihmp-pct]`
  - `[data-ihmp-baseline-at]`.

- [ ] **Step 1: Write surface tests**

Assert durable markup, `aria-live="polite"`, exact symbols, all quote slots, all state-axis slots, and no R1A target carrying generic `.nb-px`/`.nb-chg` ownership.

Add invariance tests snapshotting command ticker order, opportunity score, stage, entry badge and stance before/after the markup change.

- [ ] **Step 2: Run the surface suite red**

```bash
python3 -m pytest tests/test_intelligence_hub_market_pulse_surface.py -q
```

Expected: missing markup.

- [ ] **Step 3: Add the compact page-level state instrument**

Tier-1 phrases combine the orthogonal facts:

```text
Baseline: Prices from the latest settled build
Loading: Checking current prices
Live + complete: Live market pulse · 30/30 names
Live + partial: Live prices for 27/30 names
Delayed + complete: Delayed market pulse · 30/30 names
Delayed + partial: Delayed prices · 27/30 names
Settled: Settled close · 30/30 names
Stale: Market pulse has stopped updating
Unavailable: Current prices temporarily unavailable
```

Provide equally plain Chinese. Technical clocks and error codes belong in `data-tip-en/zh`.

- [ ] **Step 4: Add stable row quote clusters**

Render baseline price and, when references exist, coherent absolute/percent moves. Do not make the cluster a second ticker link or change `.tk` labels.

- [ ] **Step 5: Author governed dark and light CSS**

```text
DARK: graphite instrument, luminance step, restrained page-level semantic pulse.
LIGHT: white research material, cool canvas contrast, hairline + small shadow, quiet rail; no glow translation.
```

Use `--ink-up`/`--ink-down`; no literal directional colors and no JS stylesheet injection.

- [ ] **Step 6: Run render and surface guards**

```bash
python3 -m scripts.build_intel_hub
python3 -m pytest tests/test_intelligence_hub_market_pulse_surface.py -q
python3 scripts/check_template_site_sync.py
python3 scripts/check_title_i18n.py
python3 scripts/check_validated_claims.py
```

- [ ] **Step 7: Commit**

```bash
git add templates/intelligence_hub.html.j2 \
  tests/test_intelligence_hub_market_pulse_surface.py \
  site/intelligence_hub.html
git commit -m "feat(intel-hub): render durable market pulse surface"
```

Commit the generated file only if current repository law requires it for this page.

---

### Task 4: Add one atomic route-scoped controller and public asset boundary

**Files:**
- Create: `site/assets/js/intelligence-hub-market-pulse.js`
- Modify: `templates/intelligence_hub.html.j2`
- Modify: `config/site_access.yml`
- Modify: `app/deploy/Caddyfile`
- Test: `tests/test_intelligence_hub_market_pulse_client.py`
- Test: `tests/test_site_access_boundary.py`
- Test: `tests/test_lens_nested_control_taps.py` only if shared click routing needs an explicit regression

**Interfaces:**
- Consumes: Task 2 endpoint and Task 3 data attributes.
- Produces: `window.IntelligenceHubMarketPulse.refresh/pause/resume/state`.

- [ ] **Step 1: Write client contract tests**

Prove:

```text
30 row nodes -> one fetch
partial coverage -> resolved nodes update in one RAF, missing stays baked
old local request generation resolves after new -> old response ignored
older source-time item -> suppressed and coverage recomputed
same source time + equal revision -> idempotent
same source time + changed revision in later generation -> correction accepted
snapshot_id changes -> no ordering effect
document.hidden -> no refresh
visibility resume -> exactly one refresh
live setting disabled -> zero fetches
malformed schema/state/coverage -> zero DOM mutation
score/order/stage nodes -> unchanged
```

- [ ] **Step 2: Write serving-boundary tests red**

Prove the exact controller path must exist in both `config/site_access.yml` and Caddy's public asset exclusion, and that no signal-bearing JSON path is newly public.

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_site_access_boundary.py -q
```

Expected: controller/boundary missing.

- [ ] **Step 3: Implement immutable response validation**

Validate exact schema/projection, three state axes, finite values, allowlisted session/freshness, requested unique symbols, coverage arithmetic and timestamps. Reject the whole response before any DOM write when envelope-level truth is malformed.

- [ ] **Step 4: Implement local lifecycle and one-request refresh**

Use one `AbortController`, local generation and in-flight guard. Do not create a queue. Schedule the next refresh only after completion and visibility check.

- [ ] **Step 5: Implement per-item correction/order handling**

Maintain an in-memory map of last committed `{observedAt, revision}`. Suppress older source times. Treat equal-time changed revision on a later local generation as correction. Recompute resolved/missing/freshness/coverage from accepted items before paint; never show the server's original complete count after suppressing one item.

- [ ] **Step 6: Implement atomic paint**

Inside one `requestAnimationFrame`:

1. update every accepted row's price/move/class/data state;
2. retain baked values for missing/suppressed rows;
3. update feed freshness, session, coverage and clock;
4. publish one polite live-region change.

No intermediate page state may combine response A prices with response B status.

- [ ] **Step 7: Open only the controller presentation asset**

Add `/assets/js/intelligence-hub-market-pulse.js` to both existing public lists, in matching order/bytes as required by the boundary test. Do not open `site/intel_hub/hub.json`, other signal artifacts or broad `/assets/` prefixes.

- [ ] **Step 8: Preserve Terminal interaction**

Keep `.tk` and `theme.js` ownership untouched. The quote cluster must not swallow the ticker action.

- [ ] **Step 9: Run focused tests and duplicate-owner audit**

```bash
python3 -m pytest \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_intelligence_hub_market_pulse_surface.py \
  tests/test_site_access_boundary.py \
  tests/test_lens_nested_control_taps.py -q
grep -n "data-ihmp" templates/live.js site/live.js || true
```

Expected: all pass; generic `live.js` has no R1A selector/ownership.

- [ ] **Step 10: Mutation-check atomicity/order/access**

Mutations that must fail:

```text
remove local generation check
use snapshot_id for ordering
paint rows before full validation
omit requestAnimationFrame atomic commit
allow duplicate response symbol
let partial clear missing row
ignore live-disabled setting
remove asset from one public-list owner
open a broad assets/data prefix
```

- [ ] **Step 11: Commit**

```bash
git add site/assets/js/intelligence-hub-market-pulse.js \
  templates/intelligence_hub.html.j2 \
  config/site_access.yml app/deploy/Caddyfile \
  tests/test_intelligence_hub_market_pulse_client.py \
  tests/test_site_access_boundary.py \
  tests/test_lens_nested_control_taps.py
git commit -m "feat(intel-hub): hydrate public market pulse atomically"
```

Omit unchanged test files.

---

### Task 5: Integrate CI, build output and evidence requirements

**Files:**
- Modify: `.github/ci/legacy-jobs.yml`
- Modify: `.github/workflows/ci.yml` only when its current path filter must name a new R1A subject
- Modify: `config/unrun_test_baseline.json` only if the current audit workflow requires reconciliation
- Create: `mockups/evidence/reactive-projection/r1a-intelligence-hub/EVIDENCE.yml`
- Create: `mockups/evidence/reactive-projection/r1a-intelligence-hub/manifest.json`
- Create: screenshots under that evidence directory
- Test: all R1A suites

- [ ] **Step 1: Determine current owning CI from current main**

Read `.github/workflows/ci.yml`, `.github/ci/*`, `scripts/audit_unrun_tests.py` and existing Intelligence Hub registration. Do not create a second broad CI job.

- [ ] **Step 2: Add tests and all production subjects to the same owner**

Include API modules, template, controller, site-access and Caddy paths so the guarded change can trigger the guard.

- [ ] **Step 3: Run exact focused and house guards**

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

Run any additional current house guards named by `AGENTS.md`/CI for touched paths.

- [ ] **Step 4: Capture browser matrix**

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

Record viewport, theme, language, feed freshness, session, coverage, source fixture, no-overflow, console result and screenshot path. Include live, partial, delayed/settled and unavailable across the evidence set; both art directions need degraded proof.

- [ ] **Step 5: Verify behavioral network evidence**

```text
anonymous shell loads controller asset
anonymous quote-only route returns no provider/private fields
exactly one market-pulse call per refresh
no per-symbol route calls
symbol-unit limiter allows normal cadence and blocks amplification
response values and rendered tuple agree
all rows/state change in one committed frame
Terminal ticker action works after repaint
background pause/resume works
live disabled makes no call
```

- [ ] **Step 6: Commit CI/evidence changes**

```bash
git add .github/ci/legacy-jobs.yml .github/workflows/ci.yml \
  config/unrun_test_baseline.json \
  mockups/evidence/reactive-projection/r1a-intelligence-hub/
git commit -m "test(intel-hub): enforce market pulse proof matrix"
```

Omit unchanged CI/baseline files; the evidence directory is mandatory for material UI work.

---

### Task 6: PR, adversarial review, merge, deploy and production acceptance

**Files/records after implementation proof:**
- Update: `agentos/workstreams/WS-BREATHING-PLATFORM.md` only at the accepted wave boundary
- Create: `agentos/handoffs/BREATHING-PLATFORM-2026-08-31-reactive-projection-r1a.md`
- Create a DSC only for a genuinely reusable falsifiable discovery.

- [ ] **Step 1: Reconcile exact branch/head and changed paths**

Confirm no unrelated source/data/render churn. Join current main according to repo law; never force over concurrent work.

- [ ] **Step 2: Open one PR with exact boundary**

PR body states:

```text
R1A observation-only
Terminal Quote Plane canonical owner
deliberately public quote-only access
public controller asset boundary only
no rank/score/stage/Prophet/trade changes
no server sequence/correction store
no streaming
tests, mutations, browser matrix and deploy proof
```

- [ ] **Step 3: Obtain independent review**

Reviewer checks duplicate-owner risk, quote semantics, access/rights, weighted abuse controls, one-call/one-DOM-owner, local ordering/correction, degraded product behavior and intelligence invariance. Builder cannot self-approve.

- [ ] **Step 4: Wait for every binding check to conclude**

Pending is not green. Any excluded nonbinding check needs current evidence.

- [ ] **Step 5: Merge and verify deployment**

After accepted exact-head review:

```text
merge
confirm deployed API running commit
confirm static asset/page cache stamp
confirm public asset-list/Caddy parity
confirm anonymous route from public origin
confirm no provider fields
```

- [ ] **Step 6: Run real production normal-state proof**

Capture canonical upstream tuple, public route tuple, visible page tuple, source/session/freshness clocks, coverage, one-call receipt, symbol-unit usage and unchanged intelligence fingerprint.

- [ ] **Step 7: Run production-safe degraded proof**

Use an accepted reversible canary/fixture/feature gate—not vendor sabotage—to prove partial/unavailable fallback, then restore and prove recovery.

- [ ] **Step 8: Close capability ledger truthfully**

```text
R0 architecture: accepted/merged
R1A implementation: PROVEN_LIVE
R1B: NOT_BUILT
broader reactive platform: PARTIAL
```

Only after the user journey and access boundary are real.

- [ ] **Step 9: Write Agent OS handoff and explicit dialogue STOP**

Record head/merge/deploy/browser receipts, discoveries, remaining R1B gate and exact next action. Terminally stop the worker child and disarm only its exact watcher source.

- [ ] **Step 10: Stop**

Do not absorb R1B, other pages, personalized projections, broad orchestration or material intelligence deltas into the R1A PR.
