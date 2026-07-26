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

## Blast-radius ranking

Ranked so the top tier is where a silent break changes shipped numbers with no signal at all:
modules on the nightly/render publish path, then forward-ledger writers, then the rest.

| tier | before | after | meaning |
|---|---|---|---|
| **P0** | **30** | **0** | unrun + untriggerable + on a publish pipeline |
| P1 | 142 | 142 | unrun, on a publish pipeline (triggerable) |
| **P2** | **42** | **0** | unrun + untriggerable + writes a `data/` ledger |
| **P3** | **60** | **2** | unrun + untriggerable (other) |
| P4 | 415 | 415 | unrun, writes a `data/` ledger (triggerable) |
| P5 | 446 | 446 | unrun (remainder) |
| **total unrun** | **1135** / 1491 | **1005** / 1495 | |
| **strictly dark** | **132** | **2** | |

This PR closes the strictly-dark subset — the class where no signal was possible — and leaves
the 1003 triggerable-but-unrun suites staged below. Wiring all of them would blow the ci-pack
budget, so the remainder is deliberate backlog, not oversight. (The "before" column was
measured at 1491 suites; the total grew to 1495 across a rebase, and those four arrived
already wired, so the unrun count is unchanged by them.)

The two remaining dark suites are excluded on purpose; see *Red on arrival* below.
Measured in CI, the nine jobs cost **~9 min** of pack wall (pack 0 ran 12:36→13:00, pack 1
12:36→13:05, both well inside the 180-min timeout).

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
nothing ran them. Five were repaired here; two are excluded because the fix is a product call.
An **eighth** was found only once CI ran it, and is platform-dependent rather than rotted (see
*Green on macOS, red on ubuntu* below).

| suite | root cause | disposition |
|---|---|---|
| `test_settled_close_tape.py` (P0) | `_cum_2d` and `_load_theme_flow` grew a `market` parameter; the monkeypatch stubs did not. `_attach_day_flow` swallows the resulting `TypeError`, so `day_flow` silently never attached. 6 failures. | **fixed** — stubs track the real signatures |
| `test_no_lookahead.py` | the look-ahead tripwire scanned raw text, so every module docstring promising *"no `center=True`"* tripped the guard on its own prose. 6 false positives; the guard has never been able to pass. | **fixed** — blank comment/string tokens before matching, plus a new test proving the stripping hides prose only, never real code |
| `test_btc_vector_w1.py` | asserted a frozen literal `dof_cost == 3`; `config.yml` legitimately declares **6** (W2 confirm window +1, W4 staged re-entry +2). | **fixed** — now asserts the ledger's charged dof equals the registry's declared dof, which cannot rot |
| `test_import_equitydesk_backfill.py` | the seed artifact moved to `data/stage_analysis/backfill/earnings_seed.parquet`; the test still read `data/earnings_calls/scores.parquet`. The importer's own docstring was stale too. | **fixed** — both repointed |
| `test_build_measurement_evidence_gap.py` | asserted the literal word *"overlapping"*; the §0.5.8 caveat now says *"correlated"*. Substance intact. | **fixed** — asserts the disclosed dependence, not one synonym |
| the two FTR template-markup suites | assert markers (`Strategic horizon`, `ftr-dtp-full`) that exist **nowhere** in `templates/` or `site/`, and `basketdata/baskets.json` moved from `allocation.html.j2` to `dashboard.html.j2`. | **NOT wired** — whether the feature or the assertion is wrong is a product decision, not test rot |

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

## Staged remainder

`P1` (142) is the next lane: unrun suites on the publish path that *are* triggerable. A
29-suite probe of its highest-value modules ran **4 red out of 29** (14%), against 7/144 (5%)
for the dark set — so P1 needs its own repair pass before wiring, not a bulk add:

- `test_no_module_level_logging_disable.py` · `test_okx_retail.py`
- `test_release_forecast_producer.py` · `test_release_integration_2a.py`

Highest-value P1 concentrations: `build_site.py` (11 suites), `build_release_forecast.py` (9),
`neuralweb/cortex.py` (5), `build_vector.py` (4), `calibrate_vector.py` (4).

`P4` (415, ledger writers) and `P5` (446) follow. Wire them in blast-radius order, in batches
small enough to keep the ci-pack budget sane, and **run each batch locally first** — the red
rate on never-run suites is high enough that a bulk add lands red on `main`.

## Why the existing meta-guard did not catch this

`scripts/check_house_law_registry.py` censuses `scripts/check_*.py` and requires each to
declare its CI wiring. Its own docstring names the gap: *"Census only auto-covers
scripts/check_*.py — guard-shaped pytest files and harness"* are a documented blind spot.
Every suite in this census lives in that blind spot.
