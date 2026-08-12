# `engine-render-guards` timing receipt — Wave C §7.1

**Status:** measurement only. No lane is split by this document.
**Measured:** 2026-08-12 against `origin/main` @ `68942ccc514` (Wave A #5385 and Wave B #5394 both merged).
**Why it exists:** Wave C §7.1 requires a timing receipt *before* any split, and §10 lists "split the giant render lane before timing it" as an explicit non-goal. The measurement below says the split axis §7.2 proposed is the wrong one, which is exactly what a receipt is for.

---

## 0. The finding, first

`engine-render-guards` is **not** twelve steps of comparable weight. It is one step wearing a job:

| | |
|---|---|
| whole lane, measured | **427.6 s** |
| step 10 alone | **356.8 s — 83.4 % of the lane** |
| the other ten executable steps combined | **70.8 s — 16.6 %** |
| suites in step 10 | **125 of the lane's 145** |
| tests in step 10 | 4 189 passed / 25 skipped |

And step 10 is itself dominated by three whole-tree scans:

| seconds | test |
|---|---|
| 67.9 | `tests/test_aibrief_w4_panels.py::TestBuildMain::test_no_validated_on_visible_tier` |
| 65.4 | `tests/test_validated_claims_surfaces.py::test_the_live_tree_is_clean` |
| 7.2 | `tests/test_validated_claims_engine.py::test_the_live_engine_tree_is_clean` |
| **140.5** | **= 39 % of step 10, 33 % of the entire lane, in three tests** |

The next slowest test in the lane is 5.1 s. There is no gentle slope here: it is three full-repo sweeps and then a long tail of sub-second unit tests.

## 1. Why this lane is the critical path

`engine-render-guards` is **alone in its pack**. At this revision `partition_jobs` puts it in `ci-pack-0` as the pack's only member, weight 481 against ~250–310 for the other eleven packs. So the pack IS the lane, and no amount of outer-matrix work can shorten it — which is what makes it the floor Wave B's dynamic matrix explicitly could not lower (see the `ci-plan` comment block in `.github/workflows/ci.yml`).

## 2. Per-step measurement

Wall time, share, suite count, and local exit code for every step. Step 1 is the dependency install and was deliberately **not** run — CI builds a fresh venv, and mutating this host's interpreter to imitate that would corrupt every other session on the box.

| step | wall (s) | share | suites | rc | local result |
|---|---|---|---|---|---|
| 1 install minimal deps | — | — | — | — | not run; 14 packages (see §4) |
| 2 ETF tier-preview builder assertions | 7.0 | 1.6 % | 2 | 1 | 2 failed, 80 passed |
| 3 group-flow display-only detector | 2.6 | 0.6 % | 1 | 0 | 17 passed, 2 skipped |
| 4 theme deep-link + sector-intelligence | 1.5 | 0.4 % | 2 | 0 | 35 passed |
| 5 flow-velocity + flow-desk staleness | 2.0 | 0.5 % | 2 | 0 | 30 passed |
| 6 B4D-A offline materialization | 9.6 | 2.2 % | 5 | 0 | 91 passed |
| 7 attested-history operator | 3.8 | 0.9 % | 1 | 0 | 23 passed |
| 8 attested-history serving boundary | 7.8 | 1.8 % | 1 | 0 | 43 passed |
| 9 B4F AAPL pilot + seed safety | 3.5 | 0.8 % | 3 | 0 | 51 passed |
| **10 render-guard + engine-contract (rot sweep)** | **356.8** | **83.4 %** | **125** | 1 | 46 failed, 4 189 passed, 25 skipped, 4 errors |
| 11 statement-tape schema guard | 0.0 | 0.0 % | 0 | 1 | script step, failed instantly locally |
| 12 prophet-live P0 | 33.0 | 7.7 % | 5 | 0 | 283 passed |

## 3. Caveats — read these before using the numbers

- **The local failures are environmental, not main being red.** `engine-render-guards` sits alone in `ci-pack-0`, and `ci-pack-0` concluded **green** on both #5385 and #5394. The cause is specific and reproducible: this build worktree's sparse cone omits `data/`, so tracked artifacts the guards read are simply absent. The clean demonstration is `scripts/check_validated_claims.py`, which fails here with `654 UNEARNED 'validated' claim(s)` — every one in `templates/`, none in any file this receipt adds — purely because `data/regime/validated_claims_allowlist.json` is tracked on `origin/main` but not materialised locally. A guard whose allowlist is missing reports the whole repository as unearned. Do not cite the 46, or that 654, as a main-red.
- **Therefore the 356.8 s is a FLOOR, not a ceiling.** A test that fails early does less work than one that passes, so the true green-path cost of step 10 is ≥ what is recorded here. This strengthens the finding rather than weakening it.
- **`site/` AND `data/` must both be present, and a partial `data/` is worse than none.** This worktree's sparse cone excluded both. Adding `site` (752 MB) turned a false failure in `tests/test_ship_loop_guard.py::test_the_pair_list_is_the_ci_gate_s_own_enumeration` green. `data/` is the sharper trap, because its absence does not announce itself — it produces a plausible WRONG ANSWER:

  > `engine/session_anchor.py` needs `data/hk/_HSI.parquet` to anchor HK bucketing and raises `FileNotFoundError` without it. `engine.signal_gate.gate()` is deliberately self-degrading ("self-degrades to `insufficient history` on thin names instead of crashing"), so it swallows that and returns a verdict whose every field is `None`. Measured 2026-08-12: with `data/hk_search/` materialised but `data/hk/` still absent, all **157** tickers returned `None` verdicts and `scripts/regen_hk_g1_fixture.py` refused with "157 blocking finding(s): derived drift with unchanged closes" — a signature indistinguishable, from the outside, from a real engine regression. Materialising all of `data/` (2.3 GB) turned `tests/test_hk_board_rank.py` from 16 failures to **195 passed**.

  The lesson generalises past this lane: a sparse cone plus a self-degrading engine yields confident, specific, wrong diagnoses. Materialise `site/` and `data/` before drawing any conclusion from a local run here.
- **One host, one sample.** These are relative shares on an M-series Mac, not hosted-runner absolutes. The 83 % concentration is far too large to be sampling noise, but a per-step second-count is not a CI SLA.
- Reproduce with `scripts`-free tooling: the harness used is `time_render_guards.py` in this session's scratchpad; its raw output is `render_guards_timing.json`. Neither is committed — the numbers above are the receipt.

## 4. §7.2's required attributes, as they stand today

Wave C §7.2 says each new lane must carry an explicit test list, a conservative derived scope, clean workspace isolation, a correct dependency declaration, no shared generated-file collision, and an independent timeout. Measured against the current job:

- **explicit test list** — present, but 125 of 145 suites are in a single step named "rot sweep 2026-07-02".
- **derived scope** — the job declares **no `paths:` key**; its scope is inferred by `infer_job_scopes`, which is what makes it always-on-ish and broad.
- **independent timeout** — **absent.** `engine-render-guards` declares no `timeout-minutes`, so it inherits the pack's 180. A split would need one per new lane.
- **dependency declaration** — one install step, 14 packages: `pytest pandas numpy pyarrow pyyaml jinja2 plotly pillow requests beautifulsoup4 fastapi httpx jsonschema boto3`. Splitting this job into N lanes multiplies that install N times unless the lanes share a dependency group — `run_ci_pack.py` already groups byte-identical install commands, so keeping the install line identical across the children is load-bearing for cost.
- **shared generated-file collision** — not yet audited. Step 10's suites include full-tree scanners that read the rendered `site/`; whether any of them WRITE is the open question a split must answer first.

## 5. What the measurement implies for §7.2

§7.2 proposes six contract families (`render-contract-core`, `render-public-surfaces`, `render-market-boards`, `render-prophet-surfaces`, `render-governance-and-registry`, `render-forensics-and-api`). The measurement says that axis, applied to the job's **steps**, is close to a no-op: ten of the twelve steps are 70.8 s combined, so a family split that leaves step 10 intact moves ~17 % of the lane and leaves an indivisible ~357 s behind.

Two things follow, and they are ordered:

1. **The split must be INSIDE step 10.** It is the only unit with enough mass to matter, and its 125 suites are the population the six families should actually be drawn from.
2. **The first lever is the three whole-tree scanners, not a family split at all.** `test_the_live_tree_is_clean`, `test_the_live_engine_tree_is_clean` and `test_no_validated_on_visible_tier` are 140.5 s — a third of the lane — and they are full-repo sweeps by construction, so they will land in whichever family they are assigned and immediately dominate it. Isolating those three into their own lane is a larger, simpler, lower-risk win than a six-way partition, and it can be measured on its own.

§7.2's own instruction — "likely groups, **subject to measurement**" — is satisfied by revising the plan, not by executing the guess.

**Not recommended as the first lever:** `pytest-xdist`, per §7.2. Step 10's suites share the rendered `site/` tree and their hermeticity with respect to files, caches and module globals is unproven; §4 above lists that audit as still open.

## 6. What this receipt does NOT do

It does not split anything, add a lane, change a scope, or touch `.github/ci/legacy-jobs.yml`. Wave C's build step remains unstarted and is now unblocked by the gate §7.1 asked for.
