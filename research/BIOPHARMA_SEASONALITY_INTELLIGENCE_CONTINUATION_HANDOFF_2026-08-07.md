# Biopharma Seasonality Intelligence — continuation handoff (2026-08-07)

| Field | Binding value |
|---|---|
| Status | Waves 1–7 implemented; authority remains shadow/unapproved |
| Supersedes | The current-state and remaining-work sections of `BIOPHARMA_SEASONALITY_INTELLIGENCE_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md` |
| Still authoritative in the 08-06 file | §1 binding gates, §13 exclusions, and the statistical/product law. **Those are unchanged and still govern.** |
| Detailed product/statistical spec | `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md` |
| Cross-program seam | `research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md` |
| Authority ceiling | Shadow/context only. **Unchanged.** No availability flag moved. |

> The 08-06 handoff said the program was "not at foundation only." That is now
> literally true: every engine in the dependency graph exists. What does **not**
> exist is evidence, and no amount of further building creates it.

---

## 0. What changed on 2026-08-07

Nine PRs. The engine layer of Waves 1–7 is implemented and every one of them is
**dark, shadow, or explicitly unavailable** — by construction, not by omission.

| PR | Wave | What it is |
|---|---|---|
| #4805 | W2A0 | `biopharma.event.v2` — typed source temporals; fabricated precision is structurally impossible |
| #4852 | W2A | `event_clock.py` — dark, pure, fail-closed BioCatalyst→v2 adapter + 28 adversarial fixtures |
| #4860 | W1A/W1C | `universe.py` — point-in-time reads that answer "unavailable" instead of guessing |
| #4869 | W6 | `prophet_bridge.py` — post-selection overlay keyed on `plan_id`; the plan cannot move |
| #4885 | W2C/W3 | Catalyst mode — an evidence-boundary surface, not a placeholder |
| #4868 | W2B | `event_study.py` + Reality Check / SPA in `engine/validation.py` |
| #4895 | W5 | Neural Web state v2 — multi-clock, dual-read, `forecast` forbidden |
| #4896 | W4 | `model.py` / `calibration.py` / `regime.py` — shadow, forward-chained |
| #4903 | W7 | `screener.py` + `app/seasonality.py` — a browser that refuses to become a score |

### The defects worth remembering

Adversarial review found these **before** they merged. Each is the kind that
ships green and reads plausible:

1. **Precision laundering (W2A0).** `upgrade_event_v1_to_v2` discarded v1's
   `date_precision`, so a `quarter`-precision row became an `exact_time` instant
   with a **0-second span** — and `downgrade` then *succeeded*, erasing the only
   evidence the instant was fabricated. A one-way precision ratchet.
2. **A DST span hole (W2A0).** Calendar spans used `fold=0` at `23:59:59.999999`,
   so in **138 zone/date pairs since 2015** whose transition lands at midnight,
   an hour of wall clock belonged to no period at all.
3. **One bad row killed the batch (W2A).** A non-scalar `event_type` raised
   `TypeError` out of the adapter — a correctly-signed packet with one malformed
   row returned no ledger and no counts. 119 of 4,000 fuzz trials.
4. **Ex-ante leakage through the front door (W2B).** A feature measured fifteen
   days *after* the readout came back as a clean tradable row, because nothing
   required the decision cutoff to precede the event.
5. **Post-event bars in the beta fit (W2B).** The guard checked the event
   *window*, not the event. Measured β delta **+0.162** against a control of 0.
6. **An anti-conservative CI at the module's own floor (W2B).** Raw percentile
   cluster bootstrap rejected at **7.2–9.6%** against a nominal 5% at 20
   clusters — and `BUILD_FLOORS` *is* 20.
7. **A wrong security from the committed roster (W1A).** The store carries a row
   whose symbol is the literal string `"nan"`; a case-folded match on `"NaN"`
   collided and `.iloc[0]` silently returned the wrong one.
8. **Top-N-by-metric via composition (W7).** Sorting by `*_edge` plus a small
   page size *is* a fused ranking; it surfaced `n=1` above `n=6`.
9. **A colour token that made a market call (W2C).** The "2 connected" chip wore
   `sx-chip-up`, which the 红涨绿跌 swap flips to red — turning a coverage count
   into a direction. Caught only in the Chinese screenshot.

### Two wiring holes closed

- `read_seasonality_state` was **dispatchable but unnamed in the cortex system
  prompt** — whitelisted, invisible, never called. The `read_china_flows` shape.
- `tests/test_seasonality_shadow_state.py` was named by **no CI job**: the Lane 6
  emitter had never executed in CI since #4370.

**Standing lesson:** `.github/ci/legacy-jobs.yml` file lists are **explicit**. A
new suite that no job names never runs. `if: ${{ false }}` is the *required*
convention (`run_ci_pack.py:131` only picks up jobs carrying it) — its presence
is **not** evidence a suite is dark. Register every new suite in the same PR.

---

## 1. What is genuinely blocked — and cannot be unblocked by building

### 1.1 There is no event data
`clinicaltrials_gov_v2` is the only source with `production_ingest_allowed: true`
and it is globally dark (`BIOCATALYST_ENABLED default_enabled: false`). No
`biocatalyst_seasonality_event_projection.v1` exists — 49 schemas in
`contracts/biocatalyst/`, none seasonality.

**Owner: the BioCatalyst program, not Seasonality.** `event_clock.py` is written
against a *consumer-side declared expectation* and refuses wholesale anything
whose `contract_id`/`schema_version` does not match exactly. When W1B lands, a
short reconciliation PR pins the real version and hash. Until then the adapter's
failure mode is "reads nothing", never "reads it wrong".

### 1.2 Point-in-time identity spans three weeks, the panel spans 25 years
`data/symbol_directory/snapshots/` starts **2026-07-13**. The schema is
`date, symbol, security_name, exchange, etf, test_issue, is_preferred, source` —
**no stable security id, no sector, no price, no volume**. So:

- identity before 2026-07-13 → `unavailable`, never today's roster;
- corporate actions → `unavailable` **always**, blocker
  `complete_point_in_time_security_and_corporate_actions_contract`;
- price adjustment → `current_vendor_vintage`; `data/yahoo/*.parquet` is
  retroactively adjusted, so no `asof(D)` price question is answerable.

`foundation.py`'s two disclosure booleans stay as they are. Replay proof does not
exist, so nothing closes them.

### 1.3 The forward ledger has zero matured grades
28 registrations, 0 grades. **Nothing is promotable.** Product completion is not
promotion evidence — that was true in the 08-06 handoff and is still true.

### 1.4 Known measurement limits, published rather than hidden
- RC/SPA run **12.6% / 14.6%** empirical size on a 120-observation AR(1) ρ=0.5
  panel with the cube-root auto block (iid with a matched block gives 5.5/5.6%).
  That is the block bootstrap's cost. Any wiring PR pointing these at a short
  loss panel inherits it — the module documents a working threshold.
- Corrado is mildly conservative at short ranking periods (3.9% at 120 days,
  4.9% at 250). Longer ranking period is the fix.

---

## 2. What the next session should do

### 2.1 Merge-state check first
Four PRs were armed `merge-on-green` at handoff: **#4868 (W2B), #4895 (W5),
#4896 (W4), #4903 (W7)**. #4896 is stacked on #4868 — the parent merges first.
Confirm all four landed and that `origin/main` carries
`engine/seasonality/{event_study,model,calibration,regime,screener}.py` and
`app/seasonality.py` before building on them.

### 2.2 The three small follow-ups this session deliberately did not bundle
1. **`foundation.py:100` names `spa_reality_check`**; the shipped symbols are
   `reality_check` and `spa_test`. If that manifest string is ever resolved to a
   callable it needs a mapping. Naming-only — no behaviour depends on it today.
2. **`config/synapse.yml`'s `notes:` block** for
   `data-neuralweb-biopharma-seasonality-state` still describes v1 states. The
   artifact envelope is genuinely unchanged (a `state_schema` field self-describes
   the contents), so the registry is not lying — but the prose is stale.
3. **The Catalyst mode's `site/stock_seasonality.html`** is render-lane-owned. The
   `.css`/`.js` plain-copy pairs shipped; the HTML re-renders on the next lane run.
   Verify the mode switch is live before claiming it is.

### 2.3 The workflow-order defect (W6 prerequisite)
`build_prophet` runs **before** `build_stock_seasonality`/`seasonality_shadow` in
`daily.yml`. `prophet_bridge.py` does not depend on that order and writes nowhere,
so nothing is broken today — but a same-night overlay needs a reviewed dependency
change in a small rebased wiring PR. Do not bundle it with engine work.

### 2.4 What NOT to do
- Do not flip `live_event_graph`, `live_forecasts`, or `live_screener`. Code
  merging is not production proof.
- Do not solve a missing identity or transport dependency with a temporary local
  ticker map, an authenticated self-scrape, or a second collector.
- Do not re-run the Seasonax investigation, build a second calendar engine, a
  Seasonality-owned security master, or a second Prophet selector.
- Do not treat "the engines exist" as evidence. §1 of the 08-06 handoff still
  governs every promotion question.

---

## 3. Definition of completion, restated honestly

The 08-06 handoff named three finish lines. Their status:

1. **Product completion** — contracts, engines, adapters, interfaces, and honest
   unavailable states exist and run. **Substantially reached** for Waves 1–7.
   W8 (options-implied geometry, analogue integration, portfolio clustering,
   enterprise workflows) is untouched and was always gated on real ledgers.
2. **Evidence accrual** — **not started in earnest.** The forward ledger needs
   matured grades, which needs nightly time, which no PR can shorten.
3. **Authority promotion** — **not reached, and not close.** Every decision
   boolean is false and every gauntlet is unpassed.

A system that says "I do not know" precisely, for a reason a reader can check, is
what was buildable this session. That is a superior research and context product,
and it says so plainly — which is exactly what §16 of the 08-06 handoff asked for
when it said full product completion does not automatically authorize promotion.
