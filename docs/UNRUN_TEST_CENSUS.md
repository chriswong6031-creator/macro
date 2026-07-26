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
leaving 3 of them deliberately unwired because they are red for reasons that need a program
decision (see *Red on arrival — P1*; the warnings ratchet was the 4th until its 37-file
migration landed — *The import-time warnings ratchet* below). `P4`/`P5` remain deliberate backlog, not oversight:
wiring all of them at once would blow the ci-pack budget. (The "before" column was measured
at 1491 suites; the total is 1497 on current `main` as other PRs land, and the arrivals came
already wired, so they do not move the unrun count.)

#3636 left two dark; #3645 closed them the same day, so the strictly-dark set is now **empty**.
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
below the strictly-dark set. 137 are now wired across thirteen lanes; three are held back.

| job | suites | measured (clean venv) |
|---|---|---|
| `unrun-site-surfaces` | 14 | 234 tests / 18s |
| `unrun-release-forecast` | 8 | 307 / 46s |
| `unrun-brain-desks` | 13 | 190 / 11s |
| `unrun-neuralweb-cortex` | 9 | 215 / 7s |
| `unrun-vector-baskets` | 8 | 146 / 6s |
| `unrun-picks-boards` | 11 | 445 / 20s |
| `unrun-intl-collectors` | 11 | 198 / 30s |
| `unrun-russell-breadth` | 1 | 11 / 12s |
| `unrun-macro-panels` | 19 | 739 / 63s |
| `unrun-market-plumbing` | 22 | 682 / 25s |
| `unrun-publish-ops` | 19 | 507 / 27s |
| `unrun-inline-js-guard` | 1 | 14 / 2s |
| `unrun-import-hygiene` | 1 | 4 / 48s |
| **total** | **137** | **3692 / 318s** |

Twelve of the thirteen repeat the nine P0 lanes' `pip install` line **byte-for-byte**, so
`run_ci_pack.py` still builds ONE venv across all twenty-two `unrun-*` jobs. The dependency set
was re-derived empirically — every suite run in a fresh venv carrying exactly that install
and nothing else — which turned up **one** gap: `collectors/russell_breadth` imports
`yfinance` at module scope. That suite gets its own lane with `yfinance` appended rather
than adding the wheel to all twenty-two; `execute_pack` sorts jobs by install string, so a
second dependency set costs exactly one extra venv per pack.

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
| `test_release_forecast_producer.py` | **live defect, see below** | **NOT wired** |
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

## Staged remainder

`P4` (416, ledger writers) and `P5` (445) are what is left. Wire them in blast-radius order,
in batches small enough to keep the ci-pack budget sane, run each batch **serially** in a
clean venv first, and expect ~5% red.

## Why the existing meta-guard did not catch this

`scripts/check_house_law_registry.py` censuses `scripts/check_*.py` and requires each to
declare its CI wiring. Its own docstring names the gap: *"Census only auto-covers
scripts/check_*.py — guard-shaped pytest files and harness"* are a documented blind spot.
Every suite in this census lives in that blind spot.
