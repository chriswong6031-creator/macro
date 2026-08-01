# Unrun-test census — CI coverage triage

**Regenerate:** `python3 scripts/audit_unrun_tests.py` (add `--tier P1`, `--json out.json`).

This document records the systemic version of the hole PR #3595 fixed for six suites: test
suites that exist, pass locally, and are executed by **no CI job at all**.

## The two independent holes

A suite only protects something if a change can both *start* the workflow and *reach* the
assertion. Those are separate failures, and the census measures them separately.

| | meaning | why it is invisible |
|---|---|---|
| **UNRUN** | the filename appears in no `run:` step in any of the 51 workflows | there is no broad `pytest tests/` anywhere — every invocation carries an explicit file list, so an unnamed suite is never executed |
| **UNTRIGGERABLE** | nothing that changes the verdict is matched by `ci.yml`'s `on.pull_request.paths` | the workflow never fires, so even a wired job never runs |

A suite that is both is **strictly dark**: no possible edit produces a signal. Wiring a suite
into a job while leaving its subject untriggerable rebuilds the #3488 shape — *a guard the
guarded change cannot trigger is not a guard*.

Two measurement traps, both of which materially change the numbers:

- **Match paths as globs, not exact strings.** `engine/**` is a broad catch-all in `ci.yml`.
  Exact-membership checks report engine-backed suites as untriggerable when they are not.
  `tests/**` is *not* broad, so test files still need explicit entries.
- **Resolve `from pkg import a, b` to `pkg/a.py`, not `pkg/__init__.py`.** Resolving only the
  package collapsed 478 suites onto `engine/__init__.py` and overstated the dark set by 12.

A third trap is now guarded by a comment in `ci.yml`: the census tests *`name in
workflow_text`*, so **naming an unwired suite in a workflow comment makes it look covered.**

A fourth trap runs the other way and produces **false positives**: `audit_unrun_tests.py`
derives a suite's subjects from its **imports**, so a *source-scanning guard* — one that
imports nothing from the repo and instead reads a file as text and regexes it — reports
`subjects: []` and is labelled **untriggerable**. `tests/test_signup_email_validation.py`
(2026-07-27) reads `templates/onboard.js`; `templates/**` has always matched it, so only the
*unrun* half of its "strictly dark" verdict was real. Before treating a dark verdict as
ground truth, check whether the suite references its subject as a **path string** rather than
an import.

## Blast-radius ranking

Ranked so the top tier is where a silent break changes shipped numbers with no signal at all:
modules on the nightly/render publish path, then forward-ledger writers, then the rest.

| tier | before | on `main` | after P1 | meaning |
|---|---|---|---|---|
| **P0** | **30** | **0** | 0 | unrun + untriggerable + on a publish pipeline |
| **P1** | 142 | 140 | **2** | unrun, on a publish pipeline (triggerable) |
| **P2** | **42** | **0** | 0 | unrun + untriggerable + writes a `data/` ledger |
| **P3** | **60** | **0** | 0 | unrun + untriggerable (other) |
| P4 | 415 | 416 | 416 | unrun, writes a `data/` ledger (triggerable) |
| P5 | 446 | 445 | 445 | unrun (remainder) |
| **total unrun** | **1135** / 1491 | **998** / 1499 | **862** / 1499 | |
| **strictly dark** | **132** | **0** | 0 | |

Two passes so far. #3636 closed the strictly-dark subset — the class where no signal was
possible. This one closes **P1**, the triggerable-but-unrun suites on a publish pipeline,
leaving 2 of them deliberately unwired because they are red for reasons that need a program
decision (see *Red on arrival — P1*). Two others left that set the same day: the warnings
ratchet, once its 37-file migration landed (*The import-time warnings ratchet* below), and
the all-null claims benchmark set, once it was adjudicated (*Resolved — the claims benchmark
set* below). `P4`/`P5` remain deliberate backlog, not oversight:
wiring all of them at once would blow the ci-pack budget. (The "before" column was measured
at 1491 suites; the total is 1497 on current `main` as other PRs land, and the arrivals came
already wired, so they do not move the unrun count.)

#3636 left two dark; #3645 closed them the same day, emptying the strictly-dark set. It is
**not a one-time cleanup** — a new suite arrives dark whenever it is added without a `paths`
entry, and one did on 2026-07-26 (see *The strictly-dark set reopened, and closed again*).
Re-run the auditor rather than trusting these snapshots.
Measured in CI, the nine jobs cost **~3 min** of pack wall — pack 1 ran its five lanes
13:36→13:37 and pack 0 its four 13:40→13:42 — against a 180-min timeout.

### What P0 was

The 30 P0 suites guarded these publish-path modules, none of which could start `ci.yml`:

| module | suites | what a silent break moves |
|---|---|---|
| `scripts/build_vector.py` | 4 | renders `site/vector.html` nightly in 6 workflows |
| `scripts/grade_us_board.py` | 3 | US board outcome ledgers + tenure stamps (shipped verdicts) |
| `scripts/oracle_nightly.py` | 2 | oracle nightly writer + turn desk |
| `scripts/calibrate_vector.py` | 1 | the deflated-Sharpe trial budget that haircuts a live sizing signal |
| `scripts/fetch_r2.py`, `audit_r2.py` | 2 | the R2 transport the repo snapshot heals from |
| 20 further builders | 20 | demand, odds, M2 profiles, polygon universe, confluence screener, … |

## Wiring: nine lanes, one shared venv

The 130 wired suites run in nine `unrun-*` jobs in `ci.yml`. All nine declare a
**byte-identical** dependency install, so `run_ci_pack.py` builds **one** shared venv for the
whole set rather than one per job (it recreates the venv only when the install string differs).

| job | suites | measured |
|---|---|---|
| `unrun-vector-dsr` | 7 | 10s |
| `unrun-oracle-desk` | 9 | 9s |
| `unrun-grading-board` | 6 | 9s |
| `unrun-intl-libraries` | 10 | 7s |
| `unrun-data-plane` | 13 | 7s |
| `unrun-factor-research` | 19 | 14s |
| `unrun-serving-admin` | 5 | 5s |
| `unrun-builders-render` | 19 | 19s |
| `unrun-builders-stores` | 42 | 15s |
| **total** | **130** (2443 tests) | **~150s local** |

This table records the **#3636 pass**, not a live total — later PRs add suites to these lanes,
so re-derive from `ci.yml` rather than reading a count off it. Known arrivals since: 2026-07-26
`unrun-serving-admin` gained a 6th suite (75 tests, 17s local), the `admin/*.py` import +
`status()`/`panel()` smoke — another zero-workflow orphan, found while auditing
`neural-web-core` for missing transitive imports (#3717). Its subjects reached the same lane's
`paths` block, `admin/*.py` included: the suite parametrizes off that glob, so a *new* admin
module has to be able to start the workflow.

Budget: ci-pack runs two packs under a 180-minute timeout each. The nine jobs add 290 to a
1637 total balancing weight (+18%, 819/818 → 964/963) and split 5/4 across the packs. Note
the weight is only the pack **balancer**, not a time estimate: the real budget is wall clock,
and the heaviest pre-existing job (`engine-render-guards`) is 481s on its own. ~150s of local
wall for all nine — call it 4–5 min on the slower hosted runners, split across two packs — is
comfortably inside budget.

Both halves of every entry are listed in `on.pull_request.paths`: the 130 test files **and**
the 101 subject modules that were previously unmatched (`paths` grows 647 → 878).

## Red on arrival

Seven of the 132 dark suites were **already failing** on `main` — invisible precisely because
nothing ran them. Five were repaired here; two were deferred as a product call and have since
been resolved in #3645 (*The FTR product call*, below).
An **eighth** was found only once CI ran it, and is platform-dependent rather than rotted (see
*Green on macOS, red on ubuntu* below).

| suite | root cause | disposition |
|---|---|---|
| `test_settled_close_tape.py` (P0) | `_cum_2d` and `_load_theme_flow` grew a `market` parameter; the monkeypatch stubs did not. `_attach_day_flow` swallows the resulting `TypeError`, so `day_flow` silently never attached. 6 failures. | **fixed** — stubs track the real signatures |
| `test_no_lookahead.py` | the look-ahead tripwire scanned raw text, so every module docstring promising *"no `center=True`"* tripped the guard on its own prose. 6 false positives; the guard has never been able to pass. | **fixed** — blank comment/string tokens before matching, plus a new test proving the stripping hides prose only, never real code |
| `test_btc_vector_w1.py` | asserted a frozen literal `dof_cost == 3`; `config.yml` legitimately declares **6** (W2 confirm window +1, W4 staged re-entry +2). | **fixed** — now asserts the ledger's charged dof equals the registry's declared dof, which cannot rot |
| `test_import_equitydesk_backfill.py` | the seed artifact moved to `data/stage_analysis/backfill/earnings_seed.parquet`; the test still read `data/earnings_calls/scores.parquet`. The importer's own docstring was stale too. | **fixed** — both repointed |
| `test_build_measurement_evidence_gap.py` | asserted the literal word *"overlapping"*; the §0.5.8 caveat now says *"correlated"*. Substance intact. | **fixed** — asserts the disclosed dependence, not one synonym |
| the two FTR template-markup suites | assert markers (`Strategic horizon`, `ftr-dtp-full`) that exist **nowhere** in `templates/` or `site/`, plus a `basketdata/baskets.json` literal no longer in `allocation.html.j2`. | left unwired by #3636 — whether the feature or the assertion was wrong is a product decision. **Resolved by #3645**, which re-pinned the three assertions to the shipped surface and wired both suites; they pass on `main`. Detail: *The FTR product call* below |

### The FTR product call — resolved (#3645)

The verdict was **marker rot, not lost UI**: every feature is still on the page, and each
missing literal was moved by a deliberate, merged change. Two of the three assertions were
demanding a fixed bug back.

| marker | moved by | why |
|---|---|---|
| `Strategic horizon` | #2635 (07-16) | Law-2 copy port. The label `<div>` and its `<!-- FT-R11 horizon label -->` comment are untouched — only the sentence changed, from *"skip-month momentum by construction"* (a `DESIGN_DOCTRINE.md` Law-2 banned construction-that-needs-a-manual) to plain words. Re-asserting the old string would pin the violation back in place. |
| `ftr-dtp-full` | #2267 (07-11) | **Bug fix.** Its body: *"Flat `#dtp-full` / `#ftr-dtp-full` container + CSS removed"* — the flat container sat in a two-column CSS grid, so auto-flow interleaved the expansion (rank 1 left, 2 right, 3 left…) and restated every preview row. Continuation moved into per-column `.dtp-colmore` blocks. |
| `basketdata/baskets.json` | #2380 (07-12) | **Bug fix.** Made region-aware because HK/CN/CA rows read the US-only dir and *"fell back to slug names"* — the exact failure `test_display_names_not_slugs` exists to catch. The literal now only appears post-render; the source carries the region map. (It did **not** migrate to `dashboard.html.j2`; that file's occurrence is an unrelated usage.) |

Assertions were re-pinned to the substance rather than the wording, plus an inverse pin
(`assert "ftr-dtp-full" not in src`) so the fixed bug cannot silently return. Each rewritten
assertion was **mutation-tested** — 8/8 planted regressions go red — because a re-pin that
cannot fail is the same vacuity the census exists to find. No `templates/` or `site/` file was
touched. Both suites now run in the `ftr-tape-surfaces` job.

**Method note — the pickaxe cannot answer this question in this repo.** The clone is shallow
(boundary `e9324058fa0`, 2026-07-18), so `git log -S "<marker>"` returns nothing, or
mis-attributes to the graft commit; `gh search prs` does not index diffs either, so a token
that only ever lived in code returns `[]`. What works: list the file's commits via
`gh api "repos/<o>/<r>/commits?path=<file>&since=<iso>"`, then bisect
`gh api ".../contents/<file>?ref=<sha>"` for the 1→0 transition, and read that commit's
`.files[].patch` for the rationale.

### Green on macOS, red on ubuntu — a platform-dependent contract

`tests/test_tech_parity_fixtures.py` passed every local run and then failed in CI. Its
`TestFixtureDeterminism` class regenerates the Tech-Lab parity fixtures and demands
**byte-identity** with the committed copies. Two of six fail on `ubuntu-latest` —
`expected_ribbon.json` and `expected_bollinger.json`, the two built from rolling std / EMA
accumulation — because the committed fixtures were generated on macOS and a different
numpy/BLAS build lands different float tails. `ohlcv`, `ichimoku`, `rsi` and `m2` happen to
agree, which is luck rather than a guarantee.

`docs/TECH_LAB_TESTING.md` states byte-identity as a contract and calls these
"cross-platform" fixtures, so **the contract itself is platform-dependent** — regenerating on
ubuntu would only move the failure to macOS and the Mac Studio nightly. Choosing between a
numeric tolerance, a pinned numpy, and per-platform fixtures is an owner decision.

Disposition: the **24 structural checks run** (fields, warmup nulls, RSI range, band
ordering, value-area ≥70% — all platform-independent); `TestFixtureDeterminism` is
`--deselect`ed with the reason inline in `ci.yml`. So the byte-identity gate remains unrun —
that is the honest status quo, not a fix.

**Generalisation: a local green does not predict a CI green for any suite that compares
regenerated floats byte-wise.** Run such suites on the target OS, or expect to discover this
the way it was discovered here.

### Pre-existing reds surfaced, not caused

Editing `ci.yml` puts every job in the run (`paths` is workflow-level and there are no
job-level filters), so this PR's first CI run also lit up `chronicle-suite` —
`test_chronicle.py::test_rebuild_from_committed_sources_reproduces_committed_store`, a stale
committed store from #3588. It reproduces on a tree where this branch changes nothing under
`tests/test_chronicle.py`, `data/chronicle/` or `engine/chronicle/` (`git diff origin/main`
touches zero of them). Not this PR's signal; don't attribute it to the diff.

### Known-stale shipped number (not fixed here)

`test_btc_vector_w1.py` going red exposed a second, separate defect that this PR does **not**
correct: `engine/signal_lab.py` hardcodes user-facing copy reading `n=68 = 65 base + 3 override
dof_cost` (EN and ZH, plus a `DSR gated / raw` row), while the live ledger
`data/vector/trial_log.json` says `n_trials_declared=71` (65 + 6). The published DSR figures
(0.9945 / 0.9986) were computed under the smaller trial budget. Correcting them requires
re-running `calibrate_vector`, which is engine work outside this PR — the numbers must be
recomputed, never edited by hand.

## P1: unrun but triggerable, on a publish pipeline

P1 was the 142 suites (139 by the time this landed — three were wired by unrelated PRs in
between) that no workflow ran even though `ci.yml` *could* be triggered by a change to them
or their subject. Blast radius is the same as P0 — these guard
`build_site`, `build_release_forecast`, `neuralweb/cortex`, `build_vector`, `grade_us_board`
and 70 further publish-path modules — but a signal was at least *possible*, so they ranked
below the strictly-dark set. 144 are now wired across thirteen lanes (138 in the original census plus the three added by the GEX modeling-core amendment and the three added by the OIP E3 amendment below); two are held back.

| job | suites | measured (clean venv) |
|---|---|---|
| `unrun-site-surfaces` | 14 | 234 tests / 18s |
| `unrun-release-forecast` | 9 | 382 / 52s |
| `unrun-brain-desks` | 13 | 190 / 11s |
| `unrun-neuralweb-cortex` | 9 | 215 / 7s |
| `unrun-vector-baskets` | 8 | 146 / 6s |
| `unrun-picks-boards` | 11 | 445 / 20s |
| `unrun-intl-collectors` | 11 | 198 / 30s |
| `unrun-russell-breadth` | 1 | 11 / 12s |
| `unrun-macro-panels` | 19 | 739 / 63s |
| `unrun-market-plumbing` | 28 (22 + 3 GEX core + 3 OIP E3) | 682 / 25s + 42 / 3s + 188 / 11s |
| `unrun-publish-ops` | 19 | 507 / 27s |
| `unrun-inline-js-guard` | 1 | 14 / 2s |
| `unrun-import-hygiene` | 1 | 4 / 48s |
| **total** | **144** | **3997 / 338s** |

Twelve of the thirteen repeat the nine P0 lanes' `pip install` line **byte-for-byte**, so
`run_ci_pack.py` still builds ONE venv across all twenty-two `unrun-*` jobs. The dependency set
was re-derived empirically — every suite run in a fresh venv carrying exactly that install
and nothing else — which turned up **one** gap: `collectors/russell_breadth` imports
`yfinance` at module scope. That suite gets its own lane with `yfinance` appended rather
than adding the wheel to all twenty-two; `execute_pack` sorts jobs by install string, so a
second dependency set costs exactly one extra venv per pack.

**GEX modeling-core amendment (2026-07-29).** `unrun-market-plumbing` gained a second
`run:` step carrying the three remaining **strictly dark** suites in the GEX family:
`tests/test_gex_model.py` (the walls/surface/smile/term model layer),
`tests/test_gex_engine.py` (finite-difference-verified greeks + dealer-sign engine math),
and `tests/test_polygon_gex.py` (the Polygon per-strike chain accrual every options read
now depends on). All three were named by no `run:` step in any workflow AND matched by no
path pattern, so no possible edit could start `ci.yml` for them; the OIP E3 wave wired its
own three and flagged this family as the follow-up, without naming the filenames per this
file's rule. Measured 42 tests / 3s serial, all green on main at wiring time; the lane's
6-minute timeout comfortably holds 25s + 3s. Import closure re-derived empirically with
scipy, sklearn, jinja2, plotly, requests, bs4, openpyxl, statsmodels, matplotlib and
fastapi all blocked via a `builtins.__import__` shim: the only miss is `requests`
(module-scope through `collectors/base`, which the accrual collector rides), so the
closure is `pytest pandas numpy pyarrow pyyaml requests` — all inside the lane's existing
install line, shared venv unchanged, other nine wheels confirmed unused. Subject modules
were already path-covered (`engine/**`, `collectors/**`, the `scripts/*.py` catch-all);
the three test paths are the other half of the #3488 rule, added so a suite-only edit can
still start the workflow.

**OIP E3 amendment (2026-07-29).** `unrun-market-plumbing` gained a third `run:` step
carrying three suites: the OIP E3 positioning-persistence suite (new with that wave) plus
the gex_state emitter and index dealer-gamma reconstruction suites, both of which were in
the **strictly dark** class — named by no `run:` step and matched by no path pattern, so
no possible edit could start `ci.yml` for them. The E3 wave edits both, so shipping the
edits unverified would have rebuilt the exact hole this census exists to close. Measured
188 tests / 11s serial (re-measured 2026-07-30 on the rebased head — the 136/5s in the
first draft of this amendment predated the review round, which added tests to all three
suites); import closure re-derived against the lane's existing install line
with scipy, sklearn, jinja2, plotly, requests, bs4, openpyxl, statsmodels, matplotlib and
fastapi all blocked — `pytest pandas numpy pyarrow pyyaml` suffices, so the shared venv is
unchanged. The three follow-up suites this wave flagged (the gex model layer, the gex
engine math, the polygon accrual collector) were closed by the GEX modeling-core amendment
above, which landed on `main` first; nothing in the GEX family is dark any more.

Budget: ci-pack goes 109 → 121 legacy jobs and the balancing weight 1978 → 2280
(+302, +15%), splitting 6/6 across the packs at `[1140, 1140]`. Weight is the pack
*balancer*, not a time estimate — 270s of measured local wall on an idle box (520s when
the box was running three other agents' suites, which is what the per-lane numbers above
should be read against) versus a 180-minute per-pack timeout whose heaviest single job
(`engine-render-guards`) is 481s.

`paths` grows 889 → 1099: the 135 unmatched test files **and** the 75 subject modules that
nothing else glob-matched. Wiring one half without the other rebuilds the #3488 shape.
`unrun-import-hygiene` adds five more entries on the same rule — its suite, plus `.py` globs
over `scripts/` and `research/`, whose *whole trees* are that ratchet's subject.

### `test_check_inline_js.py` — wired minus two duplicated full-tree scans

Two of its 16 tests (`test_real_site_is_clean`, `test_real_tree_handlers_and_curly_clean`)
call `find_bad_scripts` / `find_bad_handlers` / `find_curly_contamination` across the whole
`site/` + `templates/` tree — byte-for-byte the scans the pre-existing `inline-js` job
already runs as `check_inline_js.py site templates`. They cost **204s**; the other 14 (the
hermetic guard-the-guard round-trips that were genuinely unrun) cost **2.5s**. They are
`--deselect`ed, so the lane adds the missing coverage without buying the same tree scan
twice per PR. Splitting the full-tree assertions out of the unit file is the real fix.

## Red on arrival — P1

The pre-flight probe in the previous PR extrapolated 4/29 (14%) from the highest-value
modules. Running **all 142** gives **7 real reds (4.9%)** — the probe oversampled the
hot modules. An **eighth** (`test_brain_gateway.py`) landed on `main` while this was in
flight and is red for its own reasons; it is listed below and not wired. It also flushed
out a measurement trap worth recording:

> **Run the census suites SERIALLY.** `MM_DATA_GUARD` compares the repo tree at pytest
> session end against session start, so under a parallel sweep it blames whichever suite
> happened to finish in a tree that *another* suite dirtied. Three of ten apparent reds
> (`test_check_inline_js`, `test_til_nw_citizenship`, `test_track_ledger_emitters`) were
> this artifact and are green in isolation. One — `test_ticker_pages` — was the real
> culprit for all of them.

| suite | root cause | disposition |
|---|---|---|
| `test_ticker_pages.py` | `build_ticker_pages` bound `OG_DIR`/`LOGO_DIR`/`_LOGO_ATTEMPTS_PATH` off `_ROOT`/`SITE` **at import**, so `run(site=tmp)` still wrote its share cards to the real tree. Every run rewrote `site/og/stocks/*.png` and `data/marketing/share_cards/logo_attempts.json`. | **fixed** — `run()` derives all three from the site/root it was given; production path unchanged (`site` defaults to `SITE`) |
| `test_action_board_lane_split.py` | asserted a raw fixture literal `"RRR"`, but the chip renders `td(x.name)` and `td()` prettifies unglossed labels → `"Rrr"`. | **fixed** — pins the chip against `td()`'s own output, inside the hot chip, with a glossed sector so the EN+ZH pair is exercised |
| `test_earnings_w5.py` | frozen `TODAY = 2026-07-14` vs `audit()`'s `datetime.now(utc)`: the "fresh store, no warnings" case had an expiry date and had already walked past the 2-td SLA. | **fixed** — freshness fixtures read the auditor's own clock; `next_date` windows stay pinned so the bdate_range tests stay deterministic |
| `test_release_integration_2a.py` | the mocked event calendar returned frozen dates while `build()` runs off the real clock; the PPI event (2026-07-14) had walked into the past and dropped out of `upcoming`. | **fixed** — mock honours the `today` it is handed |
| `test_release_forecast_producer.py` | **live defect, see below** | **fixed + wired** — adjudicated in favour of *both* candidate fixes; runs in `unrun-release-forecast` |
| `test_no_module_level_logging_disable.py` | **ratchet drift, see below** | **fixed and wired** — the 37 drifted files were migrated under `__main__`; lane `unrun-import-hygiene` |
| `test_okx_retail.py` | `test_bilingual_render` slices the OKX chip out of `vector.html.j2` and renders it with a hand-copied `t` macro. The markup now also calls `qmark()` → `UndefinedError`. Slicing the template's real macro header fixes the crash, and then **five of its six copy assertions still fail**: the chip copy was deliberately rewritten (`"crowded longs (contrarian caution, not a buy)"` → `"many traders long"`). | **NOT wired** — deciding what the chip must say is a design call under the plain-word doctrine, not test rot |
| `test_brain_gateway.py` | arrived on `main` mid-flight (2026-07-26). Two blockers, not one: its FastAPI route tests need `fastapi` + starlette's `TestClient` (`httpx`), which the shared `unrun-*` install deliberately lacks, **and** it appended to the real `data/ai_costs/usage.jsonl` on every run — the suite patches `record_usage` at 51 call sites, but anything reaching the recorder outside one of those wrappers wrote to the repo's own ledger, so MM_DATA_GUARD would have failed the lane even with the wheels added. | **fixed and wired** — one autouse fixture redirects `_write_ledger_path` (the single funnel every append goes through) to `tmp_path`, which closes all 51 escape routes at once; the lane declares `fastapi httpx` on top of the shared install |

### Shipped claims cards carry an all-null benchmark set

`test_release_forecast_producer.py` has 73 passing tests and 2 failures, and the 2 are
right. `site/macrodata/release_forecast.json` ships every `claims` card as:

```json
"benchmark_set": {"naive_prior": null, "trailing_4w": null, "ar_model": null,
                  "cleveland_nowcast": null, "market_implied": null},
"projection": {"mode": "benchmark_only", "reason": "... §6 kill rule triggered ..."}
```

`benchmark_only` is the §6 adjudication: the point forecast lost to the naive benchmark and
was killed, leaving the **benchmarks** as the card's entire content. They are all null.

Root cause: `engine/release_components_nfp.py::project_claims` opens with

```python
if icsa.empty or ic4wsa.empty:
    return _empty_claims_projection(asof, "insufficient_data")
```

`data/fred_vintage/vintages.parquet` carries **895 ICSA rows and zero IC4WSA rows**, so the
guard fires on every call. But only `point`/quantiles need IC4WSA — `naive_prior` is the
last ICSA initial print and `trailing_4w` the mean of the last four, both computable from
the ICSA that *is* there. The kill rule and the guard compose into an empty card.

Two candidate fixes, and choosing between them is a program call, not test rot:
backfill IC4WSA into the vintage store (it is already listed in `build_release_forecast.py`'s
ALFRED series set, so this is a collection gap), or decouple the ICSA-only benchmarks from
the IC4WSA guard. Until one lands the suite stays unwired, and 73 good tests stay dark
with it — the cost of not papering over a real red.

### Resolved — the claims benchmark set (adjudication: both fixes, in that order)

The two candidates are not alternatives — they answer different questions, and shipping only
one leaves a hole. **(b) decouple** is the invariant: it must hold whether or not the store
is complete, and it is what makes the card correct *today*. **(a) backfill** is the
collection repair: without it the point/quantile path stays dead and the store keeps lying
about what ALFRED serves. Both landed.

**(b)** `project_claims` now guards on `icsa.empty` alone. IC4WSA feeds `point`, the
quantiles and `n_residuals`; `naive_prior`/`trailing_4w`/`ar_model` are pure ICSA reads and
no longer degrade with it. The degradation is *disclosed* rather than silent — the absent
series moves into `pit_provenance.absent_legs` with a plain-word note, `vintaged_legs` is
declared so MRI-R26 coverage flags stop reading a vacuous `0.0` off an empty denominator,
and `input_completeness` reports `0.5` (one of two declared legs) instead of `1.0`/`0.0`.

**(a)** Root cause of the gap was *not* the ALFRED fetch. `config.yml`'s
`fred.vintage_series` **overrides** `collectors/fred.py:DEFAULT_VINTAGE_SERIES` rather than
extending it, and `fetch_vintages()` rewrites `vintages.parquet` **wholesale** — so a series
missing from the override is deleted from the store on the next keyed collect, silently,
because the collector warns on fetch errors and never on omissions. IC4WSA and CCSA were
present at #809 (891 / 876 rows) and gone by the 2026-07-16 collection. Both are restored to
the override; the rows land on the next `FRED_API_KEY` collect, which also closes the
permanently-absent `claims_survey_week_ccsa` leg on the shipped **NFP** card.

Three further `DEFAULT_VINTAGE_SERIES` members are still missing the same way — `PPIFES`,
`ECIALLCIV`, `ECIWAG`. `PPIFES` holds the CPI bridge's `core_goods_pipeline` block off the
PIT path. Restoring them moves shipped inflation-lane numbers, so it is left to that lane
rather than folded into a claims fix; the omission is recorded inline in `config.yml`.

Recomputed for the 2026-07-30 card (asof 2026-07-26): `naive_prior` `null → 187.0`,
`trailing_4w` `null → 206.25`, `ar_model` `null → 167.88`, all in thousands.
`projection.mode` stays `benchmark_only` — the §6 kill is untouched; it now has something to
show. The suite runs in `unrun-release-forecast` (75/75 green) and both halves are listed in
`on.pull_request.paths`.

### The import-time warnings ratchet had drifted 37 files — migrated and wired

`test_no_module_level_logging_disable.py` carries an allowlist frozen 2026-07-03 that "MUST
ONLY SHRINK". Three of its four tests passed. The fourth reported **37 files** that had added
module-level `warnings.filterwarnings("ignore")` / `simplefilter("ignore")` since — mostly
`scripts/*_phase0.py`, `scripts/_bt_*.py` and `research/entry_intel/**` one-off runners. The
ratchet never ran, so nothing pushed back.

The test forbids re-baselining ("Do NOT add to the allowlist") and prescribes the fix, which
is what landed: each silencer moved under `if __name__ == "__main__":` (the
`research/signal_engine/walk_forward.py` idiom), **in place** — so the CLI path still
installs the filter before the code that follows it, while a plain `import` no longer
mutates the process-global filter list. No engine module was involved, so no
`catch_warnings` scoping was needed, and **the allowlist did not move**: none of the 37 were
on it, and no allowlisted file stopped offending (`test_warnings_ignore_allowlist_only_shrinks`
fails on that too, so the tree and the list have to move together).

The migration was verified three ways rather than by eyeball, because 37 mechanical edits to
scripts with no coverage of their own is exactly where a silent breakage hides:

1. **AST equivalence** — for every file, deleting the inserted `if` and splicing its single
   statement back reproduces the original parse tree exactly. Nothing else moved.
2. **Control-differenced runtime probe** — each file's module prefix was executed three
   ways: as `__main__`, as an importer, and as an importer with the silencer deleted
   outright. `import` must equal the control and `__main__` must differ from it. Comparing
   against a control is what makes this meaningful: `import pandas` *itself* pushes three
   narrow `ignore` filters to the front of `warnings.filters`, so a naive "is `filters[0]`
   an ignore?" probe reports 27 false positives.
3. **CLI smoke** — `--help` on the six files that parse arguments; the other 31 have no
   argument parsing, and 8 of them (the straight-line `research/entry_intel` runners)
   execute their whole study at module scope, so importing them is not a smoke test but a
   study run. Those are covered by (1) and (2).

Wired as `unrun-import-hygiene`. The lane also carries the older `logging.disable` half of
the ratchet, which was green but equally unrun. `paths` gains the suite plus `scripts/*.py`,
`scripts/**/*.py`, `research/*.py`, `research/**/*.py` — the subject half: the ratchet scans
`engine/`, `lib/`, `scripts/` and `research/`, and while `engine/**` and `lib/**` were
already broad catch-alls, `scripts/` was covered file-by-file (443 of 968 `.py`) and
`research/` barely at all (1 of 87). A new module-level silencer in any of the other 611
files could not have started this workflow.

## The strictly-dark set reopened, and closed again (2026-07-26)

`tests/test_render_intl_scope.py` landed on `main` alongside the international-dashboard
render work (#3718) and took the strictly-dark count 0 → 1 — the first regression since
#3645 emptied the set. It was P3: unrun by any `run:` step, and its own path unmatched by
`on.pull_request.paths`, so no edit anywhere produced a signal.

It is green on arrival (2 tests, 1.4s) — no rot, just unwired.

**Its subject is a workflow, not a module**, which is why the auditor prints `(none)`:

```python
WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "render.yml").read_text()
```

`_subject_modules` finds subjects two ways — first-party `import`s, and repo-relative path
*literals* under `engine|scripts|app|collectors|lib|admin|site|templates|config`. This suite
has neither: it imports only `pathlib`, and assembles its one subject from path components,
so there is no literal to match and `.github/` is outside the prefix set anyway. Read
`(none)` as *"the auditor could not resolve a subject"*, never as *"this suite guards
nothing"*. The bias is one-directional and therefore safe — an unresolved subject can only
make a suite look **darker** than it is — but it does mean the subject half has to be worked
out by hand for any suite that reads a workflow, or that builds a path componentwise.

Worked out by hand, the subject is `.github/workflows/render.yml` and nothing else — the
suite's five assertions all read that one file, and none of them touch
`scripts/build_intl.py` or `templates/intl.html.j2` except as string literals *inside* it
(deleting the builder does not move this suite's verdict; unwiring it from `render.yml`
does). That half was **already** covered: `.github/workflows/**` has been a broad catch-all
in `paths` since the W5a DAG-conformance entry. Only the test file needed adding — `tests/**`
is deliberately not a catch-all.

Wired into the **`workflow-yaml`** job, which already carries `check_workflow_yaml.py` and
`tests/test_ci_pack.py` — the workflow-contract guards. That is the lane whose subject *is*
`.github/workflows/**`, so the suite sits with the things it actually guards rather than in
an `unrun-*` census lane it only ever belonged to by accident of how it was found.

**Mutation-tested, 6/6.** A wiring PR that only proves the suite passes has proved nothing —
the census exists to find guards that cannot fail. Each of the five assertions was inverted
in `render.yml` in turn (drop `intl` from the scope choices; unmap
`templates/intl.html.j2|scripts/build_intl.py`; drop `intl` from the region loop; point the
dispatch at a different module; empty the `intl)` arm; drop `intl` from the `all` fan-out)
and the suite goes red on every one. `render.yml` was restored byte-identically afterwards.

### It was wired twice — the census attracts duplicate fixes

Two sessions ran the auditor within the same hour, both saw strictly-dark go 0 → 1, and both
wired the same suite: #3731 into `workflow-yaml`, #3729 into `unrun-publish-ops`. The
insertions were at different points in a 4800-line file, so **git merged them cleanly and
main ran the suite twice** — two `on.pull_request.paths` entries and two `run:` steps, with
nothing red to say so. #3741 removed the `unrun-publish-ops` copy and kept `workflow-yaml`.

Two things this class needs:

- **A visible signal is a magnet.** A census that names exactly one regression is a to-do
  list every session can read, so check `docs/ACTIVE_BUILD_MAP.md` and open PRs for the
  suite's filename *before* wiring it, not just the tier count. `audit_unrun_tests.py`
  reports repo state, and an open PR is not repo state.
- **Duplicate wiring is silent by construction.** Every gate here — the auditor, the pack
  validator, `check_workflow_yaml.py`, `test_ci_pack.py` — is satisfied by a suite being
  wired *at least* once; none of them count. The census can go 0 while a suite runs twice
  per PR. Grep `ci.yml` for the filename after wiring.

**Put a census suite in the lane that owns its subject.** Both placements were green and
both were defensible in isolation, but only one is right: `workflow-yaml` owns
`.github/workflows/**`. The `unrun-*` lanes are a wiring vehicle for suites with no natural
home, not a home in themselves — being *found* by the census says nothing about where a
suite belongs.

## Staged remainder

`P4` (416, ledger writers) and `P5` (445) are what is left. Wire them in blast-radius order,
in batches small enough to keep the ci-pack budget sane, run each batch **serially** in a
clean venv first.

## Red on arrival — the P4/P5 sweep (2026-07-27)

The census above measures *whether a suite runs*. It never measured **whether the unrun ones
still pass**, and an unrun suite that rots is invisible indefinitely. All 870 then-unrun
suites were executed, one pytest process per suite (so a crash or hang costs one suite, not
the batch), in a throwaway worktree with the `MM_DATA_GUARD` session tripwire armed.

**Result: 846 passed, 24 did not — but only 10 are genuinely red on `main`.**

| outcome | n | meaning |
|---|---|---|
| pass | 846 | |
| **red on `main`** | **10** | fails in a fresh checkout; see the table below |
| local-env only | 14 | green once `fastapi` / `stripe` / `hmmlearn` is installed |
| **total unrun** | **870** | |

Two measurement traps worth repeating, both of which would have inflated the red count:

- **A missing third-party dep is not rot.** 13 suites failed on `ModuleNotFoundError`
  (`fastapi` ×11, `stripe`, `hmmlearn`) and a 14th — a `hmmlearn` consumer that *fail-softs
  to `None`* rather than raising — failed an `assert ... is not None`. All 14 pass with the
  dep present. They are unwired because the shared `unrun-*` install does not carry those
  deps, and adding one costs an extra venv per pack; that is a budget decision, not rot.
- **`-x` hides siblings.** Stopping at the first failure understates damage:
  `test_fix43_analyst_and_whitehouse.py` reported one failure and actually had three.
  Re-run each red suite without `-x` before triaging it.

The doc previously estimated "~5% red" for this remainder. Measured, it is **1.1%**.

### The dominant failure class: migrations that silently un-hermeticize a test

Three of the ten (`test_etf_pulse`, `test_fix43_analyst_and_whitehouse`, and in effect
`test_regime_one`) share one shape, and it is worse than a plain red:

> A migration adds a **preferred** data source in front of an existing one and keeps the old
> path as a fallback. Any test that monkeypatched the old path is now stranded on a dead
> branch. It does not fail loudly — it stops reading its fixture and starts asserting against
> the **committed production store**, so its verdict moves with the market instead of with
> the code.

`data/` is committed, so this reproduces in CI rather than being a local-only artifact. The
tell is an assertion failing against values that appear nowhere in the fixture (`XLV` where
the fixture only defines `XLK`/`XLE`/`SMH`; real tickers where the fixture defines `A`/`B`).
Both migrations also shipped their **new** branch with no coverage at all, which is why
nothing caught the stranding. Fix in two parts: pin the branch each test exercises, **and**
add the missing coverage for the branch the migration actually made primary.

### The ten

| suite | cause | class | disposition |
|---|---|---|---|
| `test_etf_pulse` | W1 PR2 made `world_state` primary; test patches only the legacy `config.data_dir` → asserts against the live store | non-hermetic | fixed + new coverage for the `world_state` branch (batch A) |
| `test_fix43_analyst_and_whitehouse` | `analyst_trends()` prefers the revisions store; test patches only legacy `_finnhub` → asserts against the live store (3 tests, not 1) | non-hermetic | fixed + new coverage for the revisions branch (batch A) |
| `test_spotlight` | W9-B (#1143) set the **US** tailwind weight to `0.0`; test still asserts a US tilt moves `composite_z` | stale assertion | retargeted to the markets that still carry the axis; US demotion now guarded (batch A) |
| `test_sector_central` | XSR-R2/R9 re-sorts the board by rotation rank; test still asserts a plain conviction sort | stale assertion | asserts whichever order `compute()` declares (batch A) |
| `test_okx_retail` | template slice gained a `qmark` macro the test env does not define; copy also rewritten underneath | fixture rot | fixed (batch B) |
| `test_w5b_edge_chips` | chip deliberately renamed `Sleeve ×N` → plain-word "Risk backdrop" (jargon ban); **3 sibling absence tests went vacuously green** | stale assertion | fixed (batch B) |
| `test_w4_us_board` (1 test) | W9-A sector-cap chip **deleted** by prophet card v1 (`fe7a7426c49`) | **obsolete** | test deleted (batch B) |
| `test_stock_personality_wiring` | stamper floors at the `2026-07-06` wire-in date; fixture uses `2024-06-03`, so nothing is written (3 tests, not 1) | fixture rot | fixed — fixture straddles the floor (batch C) |
| `test_setup_tier` (probe class) | asserts a live CN name's technicals (`stoch` was 24, is now 45) | **non-hermetic by design** | fixed — frozen 2026-07-03 tape fixture (batch C) |
| `test_group_flow` | #3458 removed the `{% if flow %}` marker its fragment slicing needs | fixture rot | owned by #3788 — not touched here |

### The second failure class: a rename disarms every absence test keyed to the old name

Fixing the template suites surfaced something the red count does not show — a **vacuous
green**, which is more dangerous than a red because it reads as coverage:

`test_w5b_edge_chips` has one presence test (`"Sleeve" in html`) and three absence tests
(`"Sleeve ×" not in html`) that check the chip degrades when `sleeve_chip` is `None`, when
`radar_state` is `None`, and when the page is in macro mode. The chip was renamed to the
plain-word "Risk backdrop". **Only the presence test went red.** The three absence tests
went trivially true and kept passing — they could no longer catch a chip leaking into macro
mode at all. All four now key off one shared sentinel.

The general rule: **when a presence marker is renamed, re-point every absence assertion in
the same edit** — otherwise the rename silently disarms them, and the suite's own red gives
no hint that it happened. Grep for the old marker, not just for the failing test.

Copy assertions on these surfaces should pin the load-bearing **noun** or the honesty
invariant, never a sentence: the house style actively rewrites prose into plain words
(`DESIGN_DOCTRINE.md`'s jargon ban), so a pinned sentence is a scheduled failure. Three
separate suites here (`test_okx_retail`, `test_w5b_edge_chips`, `test_group_flow`) rotted on
exactly that.

### The third failure class: a fixture that encodes a moment, not a contract

Batch C's two suites were red for one underlying reason — each fixture recorded *when it was
written* rather than *what the code promises*.

`test_setup_tier`'s probe class read the **live** `data/china_search/closes.parquet` and
asserted relationships about three real tickers ("`300725` must be in 2W stoch washout").
Its own docstring claimed the relationships "pass on any panel update that keeps the same
structural setup story" — but the structural story is the market's to change, not the
repo's. `300725`'s 2W stoch had recovered out of the washout band (24 → 45) and `688306`'s
2W MACD was no longer approaching up. **A relationship about a live tape is still a claim
about the market.** Scanning cutoffs showed all six probes hold together only up to
**2026-07-03** — the tape they were authored against — so the suite now reads a committed
33 KB three-ticker slice frozen at that date. It tests the engine, which is what it was
always for, and cannot decay again.

The same suite also carried a `skip_if_no_data` guard for the store being absent. That is
gone with the live read: **a skip that fires in CI is a pass you cannot see** — the failure
mode `scripts/check_skip_only_suites.py` (#3768) exists to catch.

`test_stock_personality_wiring` dated its fires `2024-06-03`. The stamper clamps its scan to
`max(build_date - 30d, "2026-07-06")` — the ledger wire-in date, before which it never
backfills — so the fixture matched nothing, the writer returned early, and the test failed
on a **missing parquet**. That presents as a broken writer rather than a stale date, which
is why it needs saying: when a producer grows a floor, every fixture below the floor stops
exercising it and starts failing for an unrelated-looking reason. Its dates now straddle the
floor on purpose, so the no-backfill rule is *asserted* rather than tripped over.

That suite also showed the mirror of the vacuous-green problem: its "wrong date" row sat one
day before `build_date`, from when the filter was same-day. The filter later became a 30-day
lookback (fires land in `track_record` retroactively, so a same-day filter would match
nothing, ever) — which made that row legitimately *in* window, proving nothing.

### The strictly-dark set reopened TWICE on the day of the sweep

Re-running the auditor after the three fix batches turned up a strictly-dark suite:
`tests/test_signup_email_validation.py`, landed hours earlier by #3776 with the public
account-creation email gate and named by no workflow. It is the highest-risk shape the
census tracks — a security-adjacent guard on the signup path, run by nothing — and it passed,
so nothing would ever have complained.

Re-running it again one batch later turned up **a second one**: `tests/test_gh_quota_guard.py`
(36 tests), landed by #3797 — the shared-GitHub-quota hook, itself written because two
watchers on one endpoint drained the 5,000/hr REST pool to zero and 403'd every session. Also
named by no workflow. **Two suites arrived dark in a single day**, which is the strongest
available evidence that this is a standing leak and not a backlog to be drained once.

This is the third reopening (#3636 emptied the set, #3645 emptied it again the same day).
The count is a **snapshot, not a state**: re-run `audit_unrun_tests.py` rather than trusting
any number written down here. Both are now wired as `unrun-dark-guards`, with every half pinned in `paths` — the two
suites and the two files they inspect. They are the examples behind the fourth measurement
trap above, and they sharpen it: **neither suite imports its subject.** One reads
`templates/onboard.js` as text; the other runs `.claude/hooks/gh_quota_guard.py` as a
*subprocess*. Check how a suite reaches its subject before believing a dark verdict.

### Byproducts worth their own tickets

- **`sector_capitulating` is a dead producer field.** `scripts/build_stock_library.py`
  still computes the W9-A marker and ships it into `site/factordata/us_standouts.json`, and
  `.nb-sector-cap` still exists in `templates/dashboard.html.j2` — but nothing renders it,
  because prophet card v1 deleted the chip. The deletion also dropped a stop-out safety
  disclosure ("−2.7pp deep panel / −3.5pp OOS, sign-stable"); whether the prophet card
  re-surfaces that is a product question, not a test-wiring one.
- **A fail-soft optional dep converts a hard failure into a wrong answer.**
  `engine/regime_one.py` logs `hmmlearn unavailable` and returns `None`, so its suite reads
  as an ordinary assertion failure rather than a missing dependency. Same family as the
  swallowed-`ImportError` freshness SLAs fixed in #3779.
- **The Leverage-state card lost its display-only disclosure.** `test_okx_retail` asserted a
  bilingual "display-only positioning context" / "不参与仓位或评分" caveat in
  `templates/vector.html.j2`. #1337 ("Simplify dashboard copy and footers") deleted that
  sentence and **no equivalent card-level disclosure replaced it** — the honesty statement
  now survives only inside the per-metric "?" notes. The *code* invariant is intact and
  still enforced (`allocation` / `compute_all` / `composite_*` must not read `okx_*`), so
  this is a doctrine question about what the card tells the user, not test rot. The suite no
  longer asserts prose that ships nowhere.

## Why the existing meta-guard did not catch this

`scripts/check_house_law_registry.py` censuses `scripts/check_*.py` and requires each to
declare its CI wiring. Its own docstring names the gap: *"Census only auto-covers
scripts/check_*.py — guard-shaped pytest files and harness"* are a documented blind spot.
Every suite in this census lives in that blind spot.
