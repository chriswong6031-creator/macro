# R2 — Adversarial Red-Team: ARCHITECTURE, MIGRATION & OPS

Reviewer lens: flag-day risk · narrative re-keying under basis flip · build-cost vs 67-min render & the
serialized weekly lane · storage/data-volume · inter-pillar ordering/circular deps · i18n dual-span + zh
color-flip · generated-JS buildability · operational fragility (feed-down, fail-open vs fail-closed).

All claims below are grounded against `/tmp/macro-cycle-fable-main/` (main). Verified facts first, then
attacks, contradictions, second-order problems, gaps.

---

## 0. Verified ground truth (what I confirmed in code before attacking)

| Claim under test | Verdict | Evidence |
|---|---|---|
| `_project_next` floors central at `max(0.05, med−since)` from `base_x=_yf(last_ts)` (today) | **TRUE** | sector_cycles.py:204-206; and `low`/`high` ALSO re-anchor from `base_x` → the WHOLE cone walks forward, not just central |
| Range-stochastic osc; confirmed peaks span 17.6–99.7 | **TRUE** | `_detrended_osc` uses `rolling(win).min()/max()` (sector_cycles.py:98-101); live `sector_cycles_data.js` XLK turns show osc 17.6, 38.9, 93.8, 97.7, 99.4, 99.7 |
| `_classify_phase(...,above200)` never reads `above200` | **TRUE** (D1-NP-5) | sector_cycles.py:160-189 |
| "identical hues/labels to cycle_data.js" comment is false | **TRUE** (D1-NP-3) | py Trough `#5b9bf0`/Recovery `#2dd4bf`/Expansion `#45b873` vs js `#e06464`/`#45b873`/`#3da564`; shorts differ too. Both live in committed artifacts |
| ZigZag unknown-leg seeding is downward-only | **TRUE** (D1-NP-6) | sector_cycles.py:132-133 `if p < ref_px` only |
| `build_cycle.py` is a shell-copier; cycle_data.js is committed site/ source | **TRUE** | build_cycle.py docstring + PAGE_ASSETS=("cycle.css","mm_charts.js","cycle_data.js","cycle_app.js") |
| markets/country filename: audit's `intl_cycles.html` is phantom; canonical is `country_cycles.html` | **TRUE** (D3-NP-1) | country_cycles.py:26-27 stale docstring says build_intl_cycles.py→site/intl_cycles.html; neither exists; site/country_cycles.html + site/markets.html exist |
| `sector_cycles.compute(asof=)` slices PIT-clean; `_record_core` price-pure | **TRUE** | S2 verified; sector_cycles.py:533-534 |
| China Shenwan already price-basis (D4-N1) | **PLAUSIBLE** | china_sectors.py docstring; 801010.parquet base 1000 (S1); not independently re-derived here |
| `regime_history.parquet` = 14,478 rows 1971→2026 w/ `quad` | **TRUE** | read directly; cols include quad, raw_quad, growth_*, inflation_* |
| No scipy/sklearn in RENDER path (but sklearn+hmmlearn ARE deps, scipy present) | **TRUE, nuanced** | requirements.txt declares scikit-learn (meta_label only) + hmmlearn; scipy imported in engine/theme_discovery, btc_regime_ledger. The doctrine is *render-path*-free, not repo-free |
| Data delivered as `window.X={...}` via `<script src=*_data.js>`, NOT runtime `fetch()` | **TRUE** | sector_cycles.html.j2:97-101; sector_cycles.js:18; zero `fetch(` in site/*.js |
| **Weekly lane is a serialized 120-min queue on a 2-core self-hosted runner** | **TRUE, load-bearing** | weekly.yml: `concurrency: group: pipeline-batch, cancel-in-progress:false`; timeout 120m; runs-on [self-hosted, macstudio]; backfill.yml + special-sits share the SAME group → they serialize behind each other |
| yahoo store size | **246 parquets / 18MB / ~959k total rows / schema [close,volume]** | measured; NOT the "~1,500 parquets, GB-scale" D4 claims |
| render.yml timeout | 75 min; build_site reads COMMITTED regime/latest.json (no engine.run) | render.yml:66,200 |

---

## 1. FATAL / SERIOUS ATTACKS

### A1 [SERIOUS] D3 §3.1 + D1 §5 + D2 §3.4: the "one build process" reality breaks the naive pillar wave-independence
`scripts/build_site.py::main()` is ONE python process calling `build_*` functions in-process (not
subprocess-per-page). `build_cycle.py` and `build_country_cycles.py` are *separate* entrypoints in the
weekly lane, not called from build_site. The designs assume each page builder is independently shippable, but
D1's generated `cycle_ontology.js` must be regenerated BEFORE any consumer builder runs, and the consumers
(sector_cycles, country_cycles, china) are built by DIFFERENT scripts at DIFFERENT points in `weekly.yml`
(build_site vs build_china vs a country builder). If `gen_ontology_js.py` runs only inside build_site but
china pages build later via `build_china`, a stale committed `cycle_ontology.js` can be consumed by the china
render → the exact drift D1 claims to abolish, re-created at the workflow level.
**Fix:** make `gen_ontology_js.py` a FIRST step in weekly.yml (its own `run_py`), before ALL of
build_site/build_china/build_country_cycles, and add the `--check` gate as a *separate* CI step in `ci.yml`
(not only a pytest) so a stale generated JS fails the batch lane, not just local tests.

### A2 [SERIOUS] D4 §2.2/§13: storage estimate wrong by ~12×; "GB-scale git-LFS-free" is fiction
D4 states "~1,500 yahoo parquets × ~8k rows × 8 bytes ≈ 96 MB … trivial in a git-LFS-free parquet repo (the
store is already ~GB-scale)." Measured: **246 parquets, 18 MB total, ~959k rows, avg 3,897 rows**, `[close,
volume]` schema, all git-COMMITTED. Adding `close_price` float64 ≈ 959k×8 ≈ **7.7 MB**, not 96 MB. The
direction (trivial) survives, but two consequences bite: (a) the author estimated instead of measuring the
substrate they own — undercuts confidence in D4-N2 (byte-safe invariance) which was ALSO only spot-checked on
one US symbol (AAPL); (b) the store is committed to git, so every `close_price` backfill + every monthly
`--full` re-pull that "fully overwrites" (§2.3) rewrites committed parquets → **git history bloat** on a
2-core self-hosted runner already at 120-min timeout. The overwrite-heals-split strategy means large periodic
diffs.
**Fix:** re-measure; state the real 18 MB→~26 MB; and specify that the monthly `--full` re-pull writes only
CHANGED rows (upsert, not full-frame overwrite) or the git repo grows unboundedly. Re-verify §2.3 byte-safety
on ≥1 non-US ETF (e.g. EWJ) and ≥1 index (^GSPC) before staking the migration on it.

### A3 [SERIOUS] D5 §3.1 (regime_prior) + D2 §3.4 (measurement.html): "JS pages fetch the JSON" violates the verified static-site delivery pattern
Every cycle page loads data as `window.X={...}` via `<script src="*_data.js">` (verified: no `fetch(` exists
anywhere in site/*.js; sector_cycles.html.j2 uses script tags). D5 writes `site/regimedata/regime_prior.json`
and says "JS pages fetch it — static-site constraint respected." A runtime `fetch()` (a) breaks under
`file://` preview and any non-HTTP context, (b) introduces async load-order races the current synchronous
script-tag model never has, and (c) diverges from the one pattern the whole platform uses. D2's
measurement.html "renders committed JSONs" — if via fetch, same problem.
**Fix:** emit `site/regimedata/regime_prior.js` (`window.REGIME_PRIOR={...}`) loaded by a `<script src>` tag,
exactly like `cycle_ontology.js` and `*_data.js`. Same for any measurement.html data. D1 already gets this
right (generates .js); D5/D2 must match.

### A4 [SERIOUS] Weekly-lane budget: the designs' "out-of-band cron, doesn't touch the 67-min render" is only half-true — they land in a serialized 120-min queue that is already congested
D2 backfill (~10-11 min), D3 flagship backfill (~3.4 min), D5 hazard panel+fit+walk-forward+lead-lag
(single-digit to tens of minutes each, ×2 direction models ×N walk-forward folds ×isotonic ×bootstrap 2000
draws ×the leadlag ~1,590-pair Stage-A FDR screen), D2/D5 quarterly refits, cond_forward monthly rebuild.
These do NOT hit render.yml (75 min) — correct. But they hit `weekly.yml` (120-min timeout, 2-core
self-hosted macstudio) which ALREADY runs 30 `run_py` steps (collectors + every calibration + every dashboard
build) and shares `concurrency group: pipeline-batch` with backfill.yml (120 min) and special-sits-backfill —
so they SERIALIZE. The comment on weekly.yml already warns "45m was too tight." Piling five pillars of
fitting into that same lane risks timeout eviction (cancel-in-progress:false means a timeout kills the run;
next week retries from scratch).
**Fix:** the designs must NAME which workflow lane each cron script runs in and its measured wall-time on a
2-core box (not "single-digit minutes offline" hand-waves). Add a NEW dedicated workflow (e.g.
`cycle-calibration.yml`) with its own concurrency group and a realistic timeout, OR gate the heavy fits to
`backfill.yml`'s window. The lead-lag ~1,590-pair × 6-lag × 2000-bootstrap screen especially needs a measured
budget — that is not "single-digit minutes."

### A5 [SERIOUS] Narrative re-keying: THREE incompatible schemes across D1/D2/D3/D4 — the N2 "solution" is itself un-reconciled
- D1 §3.3: keys = `turn_id = "{series}:{kind}:{YYYY-MM}"`, month-quantized, `match_turns(tol=±60d)`, orphans
  to a `"orphaned"` section, version-stamp gate in `.meta.detector_version`.
- D2 §5.3: `rekey_narratives.py`, `tol_bars=15`, emits `narratives.<basis_version>.json`, loader selects by
  `basis_version`.
- D3 §5.3: keys = `"{kind}:{YYYY-MM}"` of the HAND turn (human-owned, stable), `match_turn(tol=max(3mo,
  0.25×half))`, NO re-key on basis change ("nothing re-keys" — matching just re-runs), rekey_report md.
- D4 §3.3: `turn_id = "<ticker>__<kind>__<newdate>"` (EXACT DATE, not month), `TOL_DAYS=45`, classes
  exact/shifted/orphaned/new, `prev_key` chain, emits `narratives.v2.json`.
These are FOUR different key formats (`series:kind:YYYY-MM` vs `kind:YYYY-MM` vs `ticker__kind__date`), TWO
different tolerances (±60d vs 15 bars vs 45d vs 3mo), and TWO different file-versioning schemes
(`narratives.<basis_version>.json` vs `narratives.v2.json`). D4-W3 even flags "align turn_id scheme with
ontology-pillar" as an open TODO. If shipped as written, the migration produces mutually unreadable narrative
files.
**Fix:** ONE re-keying utility owned by ONE pillar (D1 owns turn identity — put `match_turns` + `turn_id` +
the migrator there). D2/D3/D4 all IMPORT it. Freeze the key format (`series:kind:YYYY-MM`), the tolerance
(scaled-by-half-cycle, one formula), and the file scheme (`narratives.<basis_version>.json`) before any wave
runs. This is a fatal-if-unfixed coordination bug masquerading as four independent solutions.

### A6 [SERIOUS] Does re-keying actually SURVIVE the basis flip? Partially — but D3's "hand keys never re-date" contradicts D4's "turn_id = new engine date"
D3 §5.3 anchors keys on the HAND turn date (stable, never re-dated) and re-runs fuzzy matching on basis
change. D4 §3.3 anchors keys on the NEW ENGINE turn date (`<ticker>__<kind>__<newdate>`), so a basis flip
CHANGES the key and requires the `prev_key` chain. These cannot both be the contract. Worse: D1 quantizes to
MONTH deliberately "so most re-detections keep the same id"; D4 keys on exact date so most re-detections
CHANGE the id. On a real basis flip (TR→price), a 14%-ZigZag pivot commonly shifts by days-to-weeks (dividend
drag is monotone, so peaks move earlier/troughs later by fractions of the leg). Month-quantization (D1)
absorbs most of that; exact-date keying (D4) orphans most of it. D4's own §3.3 admits `shifted` (7d<Δ≤TOL) is
common. So D4's scheme maximizes orphans exactly where D1's minimizes them.
**Fix:** adopt D1's month-quantized `turn_id` as THE key everywhere; delete D4's exact-date key. Verify
empirically on ONE engine (compute turns on `close` vs `close_price` for XLK, count month-bucket collisions)
BEFORE committing the migration design — this is cheap and currently un-done.

### A7 [SERIOUS] Circular / mis-ordered dependency: D4 says "flip basis BEFORE D5 backfills"; D5 says "backfill on TR now, re-key later"; D2 backfills too — who is authoritative and when?
- D4 §10/T4: "D5 must not backfill any engine's log until that engine's D4 basis-flip + re-key has merged"
  (encoded as `basis_version_homogeneous` HARD gate).
- D5 §1.10: "v0 (now): panel + model on existing TR closes … Everything runs; grades accrue." i.e. D5
  explicitly backfills/fits on TR BEFORE the basis flip.
- D2 §1.2/W3: backfill "can run on tr_v0 first … then re-run" on basis bump.
So D4 forbids exactly what D5 and D2 plan to do first. Under D4's `basis_version_homogeneous` HARD gate, a
D5/D2 TR-basis backfill would either (a) be blocked by the gate, or (b) the gate is not yet wired when they
run, and later trips on the mixed store. The pillars disagree on whether TR-first is honest-with-a-version-key
(D5/D2) or forbidden (D4).
**Fix:** decide ONE rule. Recommended: TR-first IS allowed (D5/D2 are right — version-keyed TR grades are
honest and un-idle the work), and D4's gate must be `single-basis-PER-turn_def_version`, not
`single-basis-globally`. Rewrite D4's gate to key on `turn_def_version`/`basis_version` (allow multiple
versions to coexist archived; forbid MIXING within one grade run), matching D5's version-key discipline.

### A8 [SERIOUS] D4 §8.2: the `.attrs['price_basis']` enforcement primitive is known-fragile and the design admits it, yet makes it a HARD gate path
D4 itself notes "`.attrs` can be lost by some pandas ops (a known caveat)". pandas drops `.attrs` on the
majority of operations (any `.rolling`, `.ewm`, arithmetic between two Series, `.reindex`, `.dropna` in older
versions, groupby, etc.). `_detect_swings` does `close.dropna().to_numpy()` immediately — `.attrs` is gone
before the guard even runs meaningfully, and `_detrended_osc` does `.ewm().mean()` chains that strip attrs.
So the runtime tripwire will EITHER false-negative (attrs already stripped → guard passes a TR series) OR the
`None` grace makes it a no-op during the entire rollout. The "belt and suspenders" is one broken belt plus a
static AST scan.
**Fix:** drop the `.attrs` runtime tripwire as a *gate* (keep only as a dev-aid log if wanted). Make the AST
scan authoritative AND add a positive test: a golden fixture where `_record_core(basis='price')` produces
turn dates that DIFFER from `basis='tr'` on a dividend-heavy ETF (proves the flip took effect end-to-end),
which no `.attrs` check can give you.

### A9 [SERIOUS] D5 §3.1 regime_prior consumes `data/regime/latest.json` at BUILD, but P-D5-3/P-D5-1 admit its history is un-PIT and leak-prone — and render.yml reads the COMMITTED latest.json (no engine.run)
render.yml:200 explicitly notes "build_site reads the COMMITTED regime/latest.json (no engine.run needed)".
So `regime_prior.json` must be produced in a step that has a FRESH `latest.json` — i.e. the weekly lane after
regime recompute, NOT the render lane. But D5 wires `regime_prior.json` write into `engine/run.py`
(§3.1) — is `engine.run` in the weekly lane or the render lane? If render reads a stale committed latest.json
and regime_prior is written by engine.run in a different lane, the reconciliation banner can fire on a
staleness the user can't act on (the "live regime engine" is itself a committed snapshot up to a week old on
the render path).
**Fix:** name the exact lane/step that writes `regime_prior.js` and assert it runs AFTER regime recompute in
weekly.yml; make the staleness rule (>3 trading days) measure against the COMMITTED asof, and disclose in the
banner that on the render path the "live" engine is the last weekly recompute.

### A10 [SERIOUS] Flag-day risk: D1-M3 "axis flips to pos_v2 simultaneously on all five pages in one commit"
D1 §7-M3 is an explicit flag-day: five sibling pages' position axis semantics change in a single commit after
an acceptance study. The design calls this "one commit — the axis semantic must never be mixed across sibling
pages." But those five pages are built by at least THREE different scripts (build_site→sector pages,
build_china, build_country_cycles) landing at different points in the serialized weekly lane. A single git
commit does not make the RENDERED artifacts flip atomically — if the batch lane times out mid-run (it can,
per A4), you ship a half-flipped site (US sectors on pos_v2, China on legacy) — exactly the mixed-axis state
D1 forbids, caused by the ops reality D1 didn't model.
**Fix:** gate the axis flip behind a single committed constant (`ONTOLOGY_AXIS=v2`) read by ALL page builders
at build time, so a partial batch-lane run either renders all-v2 or all-legacy depending on the committed
constant at that build — never a mix. The "one commit" must be a data/config flip, not five code edits.

---

## 2. MINOR ATTACKS

### A11 [MINOR] D2 §6 / D4 / D5 say "20-field" experiments schema; actual is 18 fields
registry_seed.json entries have 18 keys (id,name,kind,priority,cadence,what,source,storage,track_json,hook,
started,come_back_on,come_back_note,maturation,status,state,next_step,phase_hint). Cosmetic, but three
pillars cite "20-field" → none counted. Fix: cite 18, or the exact field list.

### A12 [MINOR] D3 §1.4/NP-7 FRED deep-history seed committed to git compounds A2's git-bloat
CSUSHPISA/DCOILWTICO/DHHNGSP 30y monthly seeds are small, but the pattern (commit deep-history parquets) plus
D4's overwrite re-pulls means the committed-data repo grows. Fix: quantify the committed seed size; confirm it
is one-shot not re-pulled.

### A13 [MINOR] D3 §6.4 markets.html redirect stub uses `<meta http-equiv="refresh">` — SEO/i18n
The stub ships for one release with a meta-refresh + canonical. Fine, but the visible dual-span link must be
real l-en/l-zh spans (house rule), and meta-refresh with content="0" can be flagged by crawlers. Minor;
canonical link mitigates. Ensure the stub's visible text is dual-span, not English-only.

### A14 [MINOR] D1 §2.3 stance vocabulary tones vs zh up/down flip — check the flip actually triggers
D1 maps 9 stances to `tone ∈ {bullish,bearish,neutral,anticipatory,caution}` → "existing root color tokens".
But the zh flip is specifically up→red/down→green at ROOT (memory: zh-updown-token-flip). A `tone:bullish`
chip that renders GREEN in en must render RED in zh only if it maps to an up/down token; a "BUY" (bullish)
that stays green in zh would be a bug. D1 asserts "zero new color logic" — verify each tone maps to a token
that participates in the root flip, or bullish/bearish chips won't flip and will read wrong in zh.
**Fix:** enumerate tone→CSS-var and confirm each is a flip-participating token in the 3 theme files.

### A15 [MINOR] D3 §7 wall-clock TODAY patch edits COMMITTED site/*.js directly (cycle_app.js, markets_app.js)
Correct per PAGE_ASSETS (these are committed site/ sources, no templates copy) — but the house doctrine is
"theme assets source is templates". D3 correctly notes cycle_app.js is a site/-canonical exception. Just
ensure the D3-W0 diff doesn't get clobbered by a future `build_cycle.py` copy-from-templates if someone later
promotes these to templates/. Low risk; flag for the wave.

### A16 [MINOR] D5 §4 lead-lag Stage A ~1,590 within-family pairs × 6 lags × 2000-block-bootstrap — compute unquantified
Called "single-digit minutes offline" nowhere; §4.2 gives no wall-time. On a 2-core box this could be the
dominant cron cost. Fix: measure and state it; it gates whether W6 fits in any lane.

---

## 3. CONTRADICTIONS BETWEEN DESIGNS

1. **turn_id / re-key format** (A5): D1 `series:kind:YYYY-MM` (month) vs D4 `ticker__kind__exactdate` vs D3
   `kind:YYYY-MM` (hand) vs D2 `narratives.<basis_version>.json`. Four schemes, unreconciled.
2. **Basis-first ordering** (A7): D4 forbids D5/D2 backfilling before the per-engine basis flip; D5 §1.10 and
   D2 §1.2 explicitly backfill TR-first. The `basis_version_homogeneous` (D4) HARD gate is globally-scoped;
   D5's `turn_def_version` keying is version-scoped. Direct conflict.
3. **Which pillar owns `cone_coverage`**: D2 §3.2 defines `cone_coverage` in grading_stats; D5 §1.8 ALSO
   defines `cone_coverage` in grading_stats with a DIFFERENT signature (D2: `(stamps, truth, nominal=0.80)`
   returning recal multiplier from timing-error quantile; D5: `(events, nominal=0.5)` returning frac in
   [lo,hi]). Two functions, same name, same file, different contracts, different nominal defaults (0.80 vs
   0.50). Collision.
4. **Nominal cone coverage**: D2 uses 80% cones; D5 uses the S∈[0.25,0.75] → 50% band. A card can't show both
   "78% cone" (D2) and "50% coverage" (D5) for the same projection without confusing the user.
5. **Who owns `grading_stats.py` extraction**: D2-W1 extracts it and refactors the china grader; D5-W1 says
   "Wilson/boot ports land here if D4 hasn't already"; D4 references it too. Three pillars assume they seed the
   same file first. Needs a single owner + hard dependency edge.
6. **`_project_next` floor removal**: claimed by BOTH D1 §4.5 (NP-1, "implemented in this pillar") AND D5 §1.7
   (P-D5-4, "must land with W3"). Two pillars edit the same function; whoever merges second conflicts.
   Assign to ONE (D1 owns projection semantics; D5 consumes).
7. **cycles.analyze `price=` kwarg**: D4-W4 depends on "the ontology pillar owning cycles.py" for a `price=`
   kwarg; D1 explicitly keeps `cycles.py` ontology-FREE ("no cycle imports the other way … cycles.py stays
   ontology-free to avoid an import loop"). So the pillar D4 hands the kwarg to disclaims ownership of that
   change. Orphaned dependency.
8. **markets.html disposition**: D3 §6 folds markets.html into country_cycles.html (SPY row added). D1 §1.4
   and §5.3 still list `markets.html`/`markets_app.js` as live adoption targets for pos_v2 and phase-meta.
   After D3-W6 markets.html is a redirect stub — D1's markets.html waves target a dead page.

---

## 4. SECOND-ORDER PROBLEMS THE DESIGNS CREATE

1. **Committed-data git bloat** (A2/A12): backfill.parquet (D2), panel.parquet (D5), basket_levels/*.parquet
   (D4), close_price columns on 246 committed parquets, FRED deep-history seeds (D3), monthly `--full`
   overwrites — all land in a git-committed data repo processed on a 2-core self-hosted runner. Cumulative
   repo growth + large weekly diffs slow clone/checkout in the batch lane. Nobody budgets total committed
   bytes added.
2. **Fail-open vs fail-closed of the new gates is unspecified.** D3 `registry_report` "build FAILS if a
   measured cycle's tape is >7d stale" (fail-CLOSED) — but the weekly lane has `cancel-in-progress:false` and
   a resilient `run_py` wrapper that logs-and-continues on step failure. A fail-closed raise inside build_cycle
   may just be swallowed by the wrapper and skip the page (fail-open in practice) → stale cycle.html ships
   silently. Same for D2's `validated`-token grep test (is it in ci.yml or only pytest?), D4's audit HARD
   fails (do they gate the batch lane or just write a json?). Each new gate must declare: does it abort the
   batch lane, or log-and-skip?
3. **Feed-down behavior of tripwires** (D3 §4.2): "leg whose series is >5 trading days stale → DATA_MISSING."
   Good — but a WEEKLY-lane build means daily-stale-by-construction on non-trading days; the 5-day window and
   the weekly cadence interact. A tripwire evaluated Saturday on Friday data is 1 day stale; on a holiday week
   it flips DATA_MISSING for armed tripwires the user is trading on. Define staleness in trading days measured
   against the LAST BUILD, not wall-clock.
4. **Latched FIRED with no auto-recovery** (D3 §4.2): "un-firing requires a human to publish v(N+1)." If a
   feed glitch fires a tripwire (single bad print sustained by a data error), the card is stuck REFUTED +
   grayed projection until a human intervenes — on a page the user trades. Needs a "FIRED-on-suspect-data"
   auto-review path or a fast human loop, else one bad tick freezes a flagship.
5. **isotonic/hazard model staleness → mass degradation** (D5-W3 acceptance): "model.json missing/stale
   (>100 days) → all cards degrade to prior + build warning." If the quarterly refit fails in the batch lane
   (timeout, A4) for two quarters, EVERY measured cycle silently reverts to the KM prior. The degradation is
   correct but the trigger (one failed cron in a congested lane) is fragile. Add an alert on degradation, not
   just a build warning.
6. **Backfill re-runs invalidate the accruing experiments' come-back dates** (D2 §1.6, N4): every basis/zz
   bump re-runs backfill under a new version → the experiments registry entries that say "backfill cohort
   matured day-one (n_eff=182)" become stale on re-key, but the registry entry isn't auto-updated. The N4
   "don't float free" goal is undermined if re-keys don't re-stamp the registry.
7. **Two graders reading the same forward_log with different basis expectations** during the migration window:
   until every engine flips, `load_graded_log` merges live (TR) + backfill (could be price_v1) — the provenance
   column distinguishes them but the GRADE pools them unless every grader checks basis_version per row. One
   forgotten check = a silent TR/price grade mix.

---

## 5. MISSING / UNADDRESSED

1. **No pillar owns the workflow (.github/workflows) changes.** Every "runs in cron outside render" claim
   requires editing weekly.yml/backfill.yml or adding a workflow. Not one wave lists a `.github/workflows/*`
   file. The single most important ops surface is unowned.
2. **No total-wall-time budget for the batch lane after all pillars.** Individual "~10 min" / "~3.4 min" /
   "single-digit minutes" estimates never summed against the 120-min serialized budget already near-full.
3. **preview/QA gotchas** (memory: preview-screenshot-scroll0-only, mobile-fit@375): D1-W3/D2-W5/D3 add cards,
   badges, banners, DUAL-band stacks — none reference the scroll-0-only screenshot limitation or the 375px
   mobile-fit gate for the NEW UI. The DUAL-card stack (D3 §3.3, +64px secular strip) especially risks mobile
   overflow.
4. **`check_nav_mega` / `check_nav_gap` for measurement.html + folded markets nav** (D2-W5, D3-W6): D3-W6
   references the nav guards; D2-W5 adds a new nav entry for measurement.html but doesn't mention the guards.
   A new nav item that skips the guard freezes the two-row menu (memory: nav-chrome-architecture).
5. **The `validated`-token grep (D2 §4.3) must scan zh too** — it greps "validated"/"已验证" but the zh
   dual-span for "validated" may be a different string; and it must cover generated `*_data.js`, not just
   templates.
6. **No rollback story for the basis flip beyond `_migration_archive/`.** If price-basis turns are WORSE
   (fewer clean turns on some instrument), the design archives old logs but doesn't specify how to revert the
   flipped `_record_core` call site without another full re-key cycle. D1's "reversible" claim is asserted, not
   mechanized.
7. **D4-N4 (India local index shorter than ETF) generalizes**: the max-coverage rule is stated for India, but
   the design never enumerates which of the 8 local-index markets actually LOSE history vs their ETF — so the
   country_cycles "30y survivorship-free history" advertisement may silently shrink for several markets.
8. **i18n for the age-dial / structural frame primitive (D3 §3.3)** is a NEW display vocabulary ("year 14.4 of
   a 15–20y upswing"). The number interpolation inside a dual-span is exactly where `t()`-in-attributes / split
   l-en/l-zh spans go wrong. D3 §11-Q1 defers ownership to D1 but no wave builds it. The most novel UI string
   has no home.

---

## 6. NET

The five pillars are individually strong and evidence-grounded (I verified their load-bearing code claims —
NP-1/3/5/6, the projection floor, the range-stochastic peaks, the filename phantom, the Shenwan price-basis
scope reduction all check out). The failures are at the SEAMS: four incompatible re-key schemes, a
basis-ordering contradiction (D4 forbids what D5/D2 do first), two `cone_coverage` signatures colliding in one
file, an ops model that treats "cron" as free when it's a serialized 120-min 2-core queue already at capacity,
a data-delivery assumption (fetch JSON) that contradicts the verified script-tag pattern, and a git-committed
data store whose growth nobody budgets. None is fatal to the vision; several are fatal to a clean
same-day-squash-merge rollout if shipped as written. Fix the seams (single re-key owner, version-scoped basis
gate, one cone_coverage, a dedicated calibration workflow with a measured budget, .js-not-.json delivery)
before any wave runs.
