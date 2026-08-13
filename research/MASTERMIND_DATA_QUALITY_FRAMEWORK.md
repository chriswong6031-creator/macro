# Mastermind Data OS — data quality framework (§D8)

Status: specification. Implements `DESIGN_SPEC.md` §D8 (nine check families × four severities) and the
parts of §D5 (`quality_checks`, `freshness_sla`) and §D7 (conflict states) that quality enforcement owns.
Scope is the market-data plane in this repo. The user-data plane (Supabase/RLS, owned by
`charting-app`, `user_state_owner: terminal_supabase` per `config/sector_intelligence_ownership.yml:6-13`)
is governed differently and is out of scope here.

**Evidence convention.** VERIFIED = a command was run in this session and its output is quoted. INFERRED =
reasoned from cited code. Where a number came from the census's adversarial verifier rather than from this
session, it says so. Standing adjudications are cited as `DNR:<KEY>`.

**One caveat that bounds several numbers below.** Measurements over `data/` were taken in the materialized
checkout `/Users/chriswong/Documents/Cluade/Macro Dashboard`, which the completeness critic found to be on a
detached HEAD, ~1,119 commits behind, with an unresolved conflict in `config/dag.yml` and 4,560 dirty
entries. **Any claim resting on that checkout's file mtimes or git log is not usable** and is not made here.
Claims resting on *file contents* (column values, JSON fields, ratios between two committed frames) are
usable and are marked VERIFIED — but absolute tip DATES from that tree must never be read as production
staleness. Where a `data/` file's content is load-bearing, it was read through the worktree's own git objects
(`git show HEAD:data/...`), which are on fresh `origin/main`.

---

## 0. The finding that orders this work: freshness is implemented at least fifteen times and measured nowhere

Every recommendation below is second to this one. The house does not lack freshness detection — it has more
freshness detection than any other kind of quality check, built independently, with no shared constant, no
shared vocabulary, and no coverage measurement over the estate it is supposed to cover.

### 0.1 The five the census named — all five VERIFIED

| # | Site | Threshold, as coded | What it can see | What it structurally cannot |
|---|---|---|---|---|
| 1 | `app/main.py:558` `@app.get("/api/status")`, `app/main.py:570` `def age_min(p)` | **none** — emits `age_min` as a float and no verdict at all | file mtime age of 8 VPS live artifacts (`overlay.json`, `risk_state.json`, `quotes.json`, …), `app/main.py:589-597` | anything about content; the reader must supply the threshold, and no reader does |
| 2 | `admin/health.py:15` `_STALE_HOURS = 96.0` | 96 h on `run_status.last_run`; `admin/health.py:151` `is_stale` | pipeline-level death, per-source status buckets (`admin/health.py:123`) | per-dataset staleness — it reads only `data/run_status.json` plus 12 `latest.json` mtimes (`admin/health.py:21-33`) |
| 3 | `scripts/freshness_sentinel.py` (1,346 lines) | `:194 BAKE_BUDGET_HOURS = 26.0`, `:191 REALERT_HOURS = 6.0`, `:188 BLIND_AFTER = 6`, `:221 PROPHET_MAX_SESSIONS_BEHIND = 1`, per-surface `delay_budget_days` 4 (us_stocks) / 12 (china) at `:245-268` | the **user-visible** estate from outside GitHub, incl. the re-stamp trap (`:33-42`) | only 6 declared surfaces (`SURFACES`, `:245`); it is a page/artifact sentinel, not a store sentinel |
| 4 | `lib/project_runtime_state.py:68-81` `_CADENCE_SPECS` | `every_minute: 300s`, `every_3_minutes: 600s`, `every_30_minutes: 3600s`, `hourly: 9000s`, `daily_2130_utc: 172800s` | runtime **units** (services, timers) against `config/production_topology.yml` | data content — its state enum `lib/project_runtime_state.py:30-34` (`healthy/degraded/failed/stale/missing/indeterminate/…`) describes processes, not datasets |
| 5 | `engine/neuralweb/market_packet.py:173` `QUOTES_STALE_MIN = 45.0` | 45 min on quotes in an open session; `:1187` sets `stale_warn`, `:284` `_STALE_PREFIX` prepends "STALE — treat as last known, not current: " | the chat/grounding packet's quote leg | its own other blocks. The module docstring at `:27` claims "every rendered section starts with its own as-of stamp"; the census found `as_of` extraction present only at `:1060,1077,1187,1290,1292` and absent from the block-registration loop at `:1200-1210` — 7 of ~15 blocks carry no per-block age |

Five sites, five different units (minutes, hours, seconds, sessions, days), zero shared symbols. Verified by
opening each file at the cited line.

### 0.2 The census undercounts: the census names five, there are at least ten more

Ten further independently-coded freshness surfaces exist, each with its own threshold and its own verdict
vocabulary. Fifteen implementations total:

| Site | Threshold | Grain |
|---|---|---|
| `scripts/check_surface_freshness.py:82` `ESCALATE_SESSIONS_BEHIND = 2` | 2 sessions | site artifact `as_of` vs NYSE calendar; warn-only, always exits 0 (`:9-15`) |
| `scripts/check_price_store_freshness.py` | exchange-calendar assertion, no numeric slack (docstring `:1-14`) | SPY in `data/yahoo`, gating the engine lane |
| `scripts/check_membership_snapshot_freshness.py:84,89` `CADENCE_MAX_DAYS = 4`, `SCRAPE_MAX_DAYS = 10` | 4 d / 10 d | CN THS membership snapshot plane |
| `scripts/check_hazard_model_freshness.py` | `--max-stale-days` default 100, against the model's embedded `built_at`, explicitly never file mtime (`:8-13`) | fitted model artifact |
| `engine/tushare_freshness.py:32` `DEFAULT_MAX_LAG_SESSIONS = 1` | 1 session | gated-vs-free source preference |
| `engine/hk_freshness.py` | 6 checks → page verdict `ok \| degraded \| stale` (`:33-35`) | HK page |
| `collectors/base.py:174` `detect_stale_series(..., multiplier=3.0)` | `cadence_days × 3` | per-series frozen tail |
| `collectors/base.py:241` `detect_dark_columns` + `ColumnContract.max_dark_days` (`:69`) | per-column | per-column death behind a live sibling |
| `scripts/fetch_basket_ohlcv.py:162` `STALE_SESSIONS = 3` | 3 sessions | basket member tape lag |
| `scripts/audit_common.py:48` `macro_stale_days: 45`, `:55` `massive_stale_bdays: 5`, `:60` `stocks_stale_calendar_days: 7` | 45 d / 5 bd / 7 d | store-level, via the `audit_*` family |

**The good news is in that last row.** `scripts/audit_common.py:43-62` already IS a shared, config-overridable
threshold table (16 named defaults) with a two-level gate contract — `abort_fail_pct: 5.0` /
`warn_fail_pct: 1.0` (`:50-51`) — consumed by `scripts/collect.py:409` `run_quality_audits`. That is the
primitive to extend. It covers the `audit_*` lane and nothing else: none of the five serving-tier surfaces in
§0.1 reads it.

### 0.3 The one freshness registry covers 45% of the estate and is unmeasured

VERIFIED, this session, over `/Users/chriswong/Documents/Cluade/Macro Dashboard`:

```
$ python3 -c "import json; d=json.load(open('data/run_status.json')); ..."
n_sources 149
checked_at histogram: [('2026-07-05', 1), ('2026-07-08', 41), ('2026-07-09', 107)]
last_run 2026-07-09T06:48:30.036519+00:00
top-level keys: ['last_run','sources','circuit_breaker','circuit_breaker_probe','stale_series']
$ ls -1 data | wc -l   →  332      # entries
$ ls -1d data/*/ | wc -l →  329    # directories
```

149 tracked sources against 329 top-level `data/` directories = **45% coverage**, and every tracked source's
`checked_at` in this checkout falls in a five-day window ending 2026-07-09.

Honesty note the brief demands: *frozen in this checkout* is VERIFIED from file content. *Frozen in
production* is **INFERRED and unconfirmed** — this checkout is ~1,119 commits behind, so the file's age here
is at least partly the checkout's age. That ambiguity is itself the finding: **the estate's only freshness
registry is a git-committed JSON file, so its own freshness is indistinguishable from the freshness of
whatever tree you read it in.** A quality framework cannot be built on an artifact with that property.

### 0.4 Why coverage is 45%: the bolt-on bypass

`run_status.json` is written from one loop over `FetchResult`s: `scripts/collect.py:880-882`
(`for r in results: sources[r.source] = {...}`). Only `Adapter` subclasses reach that loop. Everything else
in `collect.py` is a bolt-on `try/except` — **28 occurrences of the comment `additive, never fatal`**
(VERIFIED: `grep -c "additive, never fatal" scripts/collect.py` → 28), at `:135, 607, 698, 711, 745, 754,
766, 786, 806, 816, 825, 849, 860, 1062, 1074, 1195, 1207, 1219, 1229, 1235, 1247, 1259, 1267, 1276, 1289`
and three prose lines. A bolt-on that fails logs a warning and registers **no freshness entry at all**.

The house already discovered this and patched exactly two cases by hand:
`scripts/collect.py:883-891` registers `polygon_gex_accrual` and `options_flow_creds` with the comment
"These run outside the FetchResult loop above (they are not Adapter subclasses), so they would otherwise be
invisible in `run_status.json`." Two of ~19 bolt-ons. The rest — `sec_ftd` (`:1188-1196`, a bare
`try: from collectors.sec_ftd import incremental` … `except: log.warning`, "Additive, never fatal"),
the basket-OHLCV refresh (`:789-806`), the intraday accrual (`:853-860`) — remain invisible by
construction. (`sec_ftd`'s range corrected here 2026-08-12: `:860-868` is the Polygon-intraday /
options-flow-creds block, not `sec_ftd`.)

### 0.5 What §0 obliges, before any new check family is written

| ID | Requirement | Done when |
|---|---|---|
| FR-0 | One freshness primitive. `lib/dataos/quality.py:206 check_freshness` is it; every site in §0.1–§0.2 becomes a caller, not a reimplementation. | `grep -rnE "STALE_(HOURS\|MIN\|SESSIONS)\|BUDGET_HOURS\|_stale_days" engine scripts lib app admin collectors` returns only `lib/dataos/` and `scripts/audit_common.py` |
| FR-1 | Freshness thresholds are **declared in the registry, not in the checker.** `freshness_sla` is in the §D5 field list but appears **0 times** in `config/dataset_registry.yml` (VERIFIED: `grep -c freshness_sla config/dataset_registry.yml` → 0). Add the block (§3.2). | every `status: PRODUCED` row carries `freshness_sla` |
| FR-2 | Coverage is itself a measured, published number. The health report prints `datasets_registered / data_dirs_present` and fails its own check when registered coverage drops. | `mastermind data health --coverage` prints both, non-zero on regression |
| FR-3 | No producer may write to `data/` without registering a status entry. The bolt-on bypass is closed by making `run_status` emission a decorator/context manager the bolt-ons can wrap, not a property of being an `Adapter` subclass. | a new bolt-on with no status entry fails a registry-conformance test |
| FR-4 | The freshness registry stops being a committed JSON blob whose age is the tree's age. It carries `produced_by_run` + `commit_sha` (the pattern `engine/capital_structure/share_count_r2_conformance.py:750` already enforces), so a reader can tell "stale data" from "stale checkout". | `run_status.json` carries a provenance block |

FR-0 through FR-4 are Phase 0 of §11. Nothing else in this document is worth building first: a framework
whose own coverage is 45% and whose coverage number is not printed anywhere is a framework that will report
green while an untracked store dies.

---

## 1. Primitive — extend `lib/dataos/quality.py`, do not write a second one

`lib/dataos/quality.py` (15,792 bytes) already implements the §D8 model: `Severity` (`:61-68`),
`CheckFamily` with all nine names (`:70-82`), `Finding` carrying structured `evidence` (`:85-98`), and six of
the nine checks as pure functions with injected `now`. **Three families are declared in the enum and have no
implementation:** `CONTINUITY`, `DISTRIBUTION`, `CROSS_SOURCE`. That is the exact gap §3.5, §3.6 and §4 fill.

Standing caveat, and it is a blocker, not a footnote: the completeness critic found `lib/dataos/` and
`config/dataset_registry.yml` **untracked** (`git status --porcelain` → `?? lib/dataos/`,
`?? config/dataset_registry.yml`; `git ls-files lib/dataos/` → empty). Re-verified this session: the files are
present on disk (`lib/dataos/quality.py`, 15,792 B, mtime 2026-08-12 13:50). Until they are committed, no CI
lane has ever run the checks this document specifies (VERIFIED this session: `wc -l tests/test_dataos_*.py` →
6 files, 1,729 lines — the sibling lane has grown the set past the critic's 5 files / 1,360 lines), and every "already exists" claim in §1–§6 means
"exists in the working tree." Commit before extending.

Design properties to preserve, all already true of the module and all load-bearing:

- **Pure functions, injected clock.** `check_temporal_integrity` takes `now` keyword-only with no default,
  and says why: "a default would read the wall clock and make the function impure, and an impure quality
  check cannot be a unit test" (`lib/dataos/quality.py:308-322`). Every new family follows this.
- **Findings carry machine evidence, not prose.** `Finding.evidence` is a mapping because "a finding whose
  proof is only in its message cannot be re-checked, deduplicated, or counted" (`:86-91`).
- **A bad row is a finding, not a crash** (`:330-337`). The `audit_*` family has the same rule
  (`scripts/audit_common.py:13-14`, "log, don't fail") and `scripts/audit_price_basis.py:40-41` states it
  outright: an audit's own crash must never abort the collect.
- **Severity is declared by the caller, not inferred by the checker** (`:18-22`): "the same missing row is
  INFO on a research scratch table and BLOCK on a published tape, and only the contract knows which."

---

## 2. The four severities — what each one DOES

Severity is not a label. It is a contract about two consequences: what happens to the nightly render, and
what the user sees.

| Severity | Nightly render | User-facing surface | Annotation level | Escalates when |
|---|---|---|---|---|
| `INFO` | proceeds; finding recorded in the run receipt | nothing | `::notice` (`lib/dataos/quality.py:366`) | never |
| `WARN` | proceeds; finding recorded **and** annotated in the Actions summary | nothing | `::warning` (`:367`) | ≥3 consecutive nightly runs → `DEGRADED` |
| `DEGRADED` | proceeds and **publishes**, with the degradation state written into the artifact the page reads | a plain-word disclosure on every surface fed by the affected dataset (§9) | `::warning` (`:368`) | ≥3 consecutive nightly runs → open an incident (§7); the streak rule already exists at `scripts/check_nw_health_escalation.py:5-8`, keyed by run date not data vintage |
| `BLOCK` | the dataset is **not published**; the last-good artifact is served unchanged and marked stale | the same disclosure as DEGRADED, plus the surface stops claiming currency | `::error` (`:369`) | immediate incident |

Three rules that make this honest rather than decorative:

**R2.1 — DEGRADED must reach the user or it is WARN.** A severity whose only consumer is a CI log is a WARN
with a scarier name. The existing proof that this works: `engine/hk_freshness.py:406` sets
`verdict = "degraded"` and `:419-475` composes the bilingual banner the page renders. If a dataset has no
path to a user-visible degradation state, its checks may not be declared `DEGRADED`.

**R2.2 — BLOCK serves last-good, never nothing and never zero.** This is §D7's escalation rule
(`DISCREPANT_MAJOR` quarantines the value and serves last-good) applied to quality. The house has the
primitive in two shapes: the per-collector circuit breaker (`collectors/base.py:438-470` `_breaker_state`,
`:536-559` `update_breaker`, `CIRCUIT_BREAKER_FAILS = 3` at `:20`, half-open retry documented at `:22-26`) and the quarantine-with-provenance file
(`scripts/chain_snapshot_poller.py:36-38` writes `{ROOT}/{date}.corrupt-{ts}.parquet` and surfaces it in
`_meta.json "quarantined"`). Blocking must never fall back to `0` — §D6's law, and the reason
`collectors/china_connect.py:21-31` coerces upstream's fake `0` to `NaN` on a cumulative holdings level.

**R2.3 — a run-aborting gate stays where it already is.** `scripts/collect.py` already has a hard gate:
`abort_fail_pct: 5.0` / `warn_fail_pct: 1.0` (`scripts/audit_common.py:50-51`), "> 5% of a universe failing
aborts the run; 1-5% warns" (`scripts/audit_common.py:11-14`). `BLOCK` maps onto that existing gate; it does
not get a second one.

---

## 3. The nine check families

Each family below gives: the definition, the callable, the threshold **and where the number comes from**, the
default severity, and the in-repo prior art. Where the answer is "extend X", it says so.

### 3.1 Completeness — every expected row and column is present and non-null

- **Callable:** `lib/dataos/quality.py:242 check_completeness(rows, expected_keys, ...)` — row-grain.
- **Missing half:** universe-grain completeness. "Every *expected* member is present" needs the expected set,
  which is the Security Master (§5), not the file listing.
- **Thresholds:** `universe_min_bars: 250` (`scripts/audit_common.py:49`) for "a configured ticker with fewer
  rows is short"; `massive_min_files: 100` (`:57`) to distinguish "store absent (CI checkout)" from "store
  broken" — that distinction is mandatory for any check that runs in a sparse agent worktree.
- **Severity:** `WARN` per-row; `DEGRADED` when the missing fraction of a declared universe exceeds
  `warn_fail_pct`; `BLOCK` above `abort_fail_pct`.
- **Prior art / hazard:** `collectors/yahoo.py:168-169` — `if len(frames) < len(tickers) * 0.7: raise`. A
  **30% silent loss** is inside tolerance. Its own docstring records the cost of a noisy version of the same
  check: "A warning that is always on is a warning nobody reads, which is how CTRA/TPH sat frozen for three
  months" (`collectors/yahoo.py:39-42`). The framework keeps the 70% raise as a floor and adds a
  per-name completeness finding so a 25% loss is not silent.
- **Worked hazard, VERIFIED this session:** `data/stocks` has **7 distinct tip dates** across 229 files, from
  2026-06-18 to 2026-07-08, with 220 names at the max and 9 names behind it — the worst at 2026-06-18 against a store max of
  2026-07-08. An `as_of`
  read at the store max silently drops those 9. This is completeness at the cross-section grain, and no
  existing check sees it (`scripts/audit_prices.py` checks interior gaps only; a frozen tail has no interior
  gap to find — stated at `scripts/audit_stocks_freshness.py:13-16`).

### 3.2 Freshness — the newest observation is inside a declared SLA

- **Callable:** `lib/dataos/quality.py:206 check_freshness(newest_ts, sla_hours, now, ...)`. Default severity
  in the module is `DEGRADED` (`:212`), which is right: a stale store is servable with a disclosure.
- **The SLA is registry data, not a constant.** Proposed `freshness_sla` block, per dataset:

```yaml
freshness_sla:
  anchor: newest_observation      # newest_observation | producer_stamp | served_file
  clock: sessions                 # sessions | business_days | calendar_days | hours
  calendar: XNYS                  # XNYS | XSHG | XHKG | XTSE | none
  warn_after: 1
  degrade_after: 2
  block_after: 5
  absent_ok: false                # true for legitimately-intermittent artifacts
```

  Four fields are not decoration; each closes a defect the repo has already paid for:

  - `anchor` — `scripts/freshness_sentinel.py:274-280` sets `bake_budget_hours: None` for the Prophet surface
    ON PURPOSE, because the served file's mtime is set by an rsync and "an unchanged file legitimately keeps
    an old mtime while a touched-but-frozen one gets a fresh stamp: exactly the re-stamp trap this surface
    exists to defeat." A producer stamp and an observation watermark are different anchors and must be
    declared, never guessed.
  - `clock` + `calendar` — `scripts/audit_stocks_freshness.py:95-101` records the 2026-08-03 correction:
    the *threshold*, not the anchor, must absorb weekends and holidays. A `days` SLA on a session-grain
    dataset fires every Monday.
  - `absent_ok` — `scripts/freshness_sentinel.py:302-314` names this "load-bearing": the evening board
    artifact is legitimately absent most of the day, and without the exemption a missing file "would count
    toward the blindness escalation and page 'the sentinel is blind' every single morning by construction —
    the false-positive factory the module's own falsifier law forbids."
  - `block_after` — an absent store in a sparse checkout must be `INDETERMINATE`, never a breach. Same rule
    as `scripts/freshness_sentinel.py:56-60` ("A missing or unreadable file is INDETERMINATE (the sentinel is
    blind), never a breach") and `massive_min_files: 100`.

- **Seed values, taken from what already ships rather than invented:** daily equity bars
  `sessions/XNYS, warn 1, degrade 2, block 5` — `degrade 2` is `ESCALATE_SESSIONS_BEHIND = 2`
  (`scripts/check_surface_freshness.py:82`); `block 5` is NEW here and sits inside
  `stocks_stale_calendar_days: 7` (`scripts/audit_common.py:60`), whose comment records 7 as the worst
  structural NYSE closure 2000-2026; macro releases
  `calendar_days, degrade 45` (`macro_stale_days: 45`, `scripts/audit_common.py:48`); live quotes
  `hours, degrade 0.75` (`QUOTES_STALE_MIN = 45.0`, `engine/neuralweb/market_packet.py:173`); page bakes
  `hours, degrade 26` (`BAKE_BUDGET_HOURS = 26.0`, `scripts/freshness_sentinel.py:194`); per-column
  liveness stays with `ColumnContract.max_dark_days` (`collectors/base.py:69`).

- **Two grains that must both run.** Frame-grain freshness cannot see a dead column behind a live sibling —
  the china_connect defect, where "the death of net/buy/sell sat unnoticed for ~2 years behind a live
  turnover" (`collectors/china_connect.py:33-36`). `detect_dark_columns` (`collectors/base.py:241`) is the
  fix and stays. Column-grain freshness cannot see a store that never lands at all — hence the store-level
  tripwire at `scripts/collect.py:916-920`.

### 3.3 Uniqueness — every grain key appears at most once

- **Callable:** `lib/dataos/quality.py:109 check_uniqueness(rows, key_cols, ...)`, default `BLOCK` (`:114`),
  with the correct justification at `:117-119`: "a duplicated grain key silently multiplies whatever a
  consumer sums, and there is no downstream check that can see it."
- **Threshold:** none. Any duplicate on a declared `grain` is a defect. Tolerance would be nonsense here.
- **Prior art:** `engine/ledger_identity.py:18-36` — the SATS/ECHO case, which is the reference failure:
  128 rows each, identical `(date, type)` key sets, 39 identity columns byte-identical, "conclusive that
  these are one physical fire logged twice," so "every per-row statistic over the ledger … weights EchoStar
  TWICE." Its `:38-42` explains why the existing guard missed it — `_blocked_by_era_floor` is scoped
  per-ticker-**string**, so a rename produces two strings and the guard sees no duplicate.
- **Consequence for the framework:** uniqueness must be checked on the **resolved identity** (`msec_id`
  per §D2), not the stored symbol. A uniqueness check keyed on a symbol column cannot see a rename-induced
  duplicate — by construction, in exactly the way that already shipped.

### 3.4 Validity — a value is internally possible

- **Callable:** `lib/dataos/quality.py:159 check_validity_ohlc(...)` — `high >= low`, `high >= open/close`.
- **Extend with, per registry column:** `dtype`, `unit`, `currency`, `range`, `nullable`, `null_reasons`,
  `zero_is_meaningful` (§D6). The registry already carries `dtype`/`basis`/`renames_to`
  (`config/dataset_registry.yml:58-63`).
- **Thresholds:** `price_move_alert_pct: 20.0` (`scripts/audit_common.py:45`) as a FLAG, never a fail;
  `macro_outlier_z: 5.0` (`:52`) likewise. A 20% single-day move is real often enough that failing on it
  would be a false-positive factory.
- **The `zero_is_meaningful` clause, and a correction to §D6.** DESIGN_SPEC §D6 says "a validator flags
  `fillna(0)` on any column where `zero_is_meaningful` is false," citing 635 sites. **Do not implement that
  as stated.** The adversarial verifier adjudicated a 15-site sample: ~13% are genuine null-as-zero, 53% are
  semantically correct zeros, 20% are arithmetically inert because they sit one line above an
  availability-weighted denominator (`engine/china_conditions.py:334-336`, `engine/axes.py:78-79`), and one
  was a `fillna(0.5)` false positive (`engine/active_commodity.py:119`). A class-wide flag would fire on ~87% of ~636 in-tree sites (INFERRED: the sample rate
  applied to the verifier's strict count), and by `collectors/yahoo.py:39-42`'s own law that is a warning nobody reads.
  **Implement the two high-yield idioms instead:**
  1. `(1 + <returns>.fillna(0)).cumprod()` — 22 sites, only 2 with an aliveness guard
     (`engine/indicators.py:55` `.where(closes[cols].notna().any(axis=1))`,
     `engine/oracle/timemachine.py:247` `.where(alive)`). The other 20 compound a halted / suspended /
     not-yet-listed session as a flat day, so the index continues through a period where the constituent did
     not trade: `engine/baskets_intl.py:100`, `engine/china_sector_index.py:98,215`,
     `engine/commodity_index.py:182`, `engine/momentum_crash_gate.py:108`, `scripts/build_intl.py:675`,
     `scripts/oracle_nightly.py:763`, `scripts/oracle_reversion_screen.py:323,668`, and others.
     The guarded/unguarded split is the detector: **the check is "a cumulative-return construction over a
     `fillna(0)` return series with no aliveness mask on the same expression."** Severity `DEGRADED` — the
     index is servable but its constituent count is a lie.
  2. The volume cluster: `engine/stock_technicals.py:345` `vol = volume.fillna(0.0)`,
     `engine/stock_technicals.py:258`, `engine/volume_signature.py:89`, `engine/leader_lifecycle.py:547`
     `obv = signed_vol.fillna(0).cumsum()`, `engine/basket_tape.py:184`. A missing-volume session becomes a
     zero-volume session, which is a **different market state** (no trades vs no data) flowing into
     OBV/CMF/accumulation. Aggravating structural fact: `data/yahoo` stores volume as int64 while
     `data/stocks` stores float64, so a missing bar cannot even be represented as null in the yahoo store —
     which makes this a registry `nullable: false` + `null_reasons` problem, not a call-site fix.

### 3.5 Continuity — no unexplained hole in a series that should be dense

- **Not implemented.** `CheckFamily.CONTINUITY` exists at `lib/dataos/quality.py:77` with no function.
- **Definition:** given a dataset with a declared `calendar` and `frequency`, every expected period between
  `first_obs` and `newest_obs` has a row, or carries a declared null-reason from §D6's vocabulary
  (`HALTED`, `PRE_INCEPTION`, `POST_DELISTING`, `NO_COVERAGE`, …).
- **Thresholds, from shipped code:** `price_max_gap_days: 4` business days
  (`scripts/audit_common.py:44`, "tolerates holidays"), `massive_max_gap_bdays: 5` (`:54`, a **fail**),
  `massive_recent_window_bdays: 90` (`:58` — continuity judged over the trailing window only, "a deeper gap
  flags (descriptive, not tonight's feed)"). That recent-window scoping is right and must be kept:
  `scripts/audit_prices.py:16,28-29` explains that historical gaps "would false-abort every run forever."
- **Severity:** `WARN` inside the recent window, `DEGRADED` when a gap crosses `massive_max_gap_bdays`,
  `INFO` outside the window.
- **Why this family is not optional, VERIFIED:** `data/massive_stock_day/_manifest.json` reads
  `n_processed_days: 471` with `coverage.first_day 2021-07-06 / last_day 2026-07-02` and
  `max_missing_run_weekdays: 832`; the SPY anchor reads `n_rows: 454` with `max_gap_calendar_days: 1165`.
  The store's own manifest declares a 3-year hole in its anchor. This is the store §D4 nominates as the
  `_raw` basis, so a naive "use raw for structure math" rule would move structure calculations onto the
  gappiest plane in the estate.
- **The halt hazard this family must expose rather than hide.** No halt store exists (`ls data | grep -iE
  'halt|luld|auction|suspend'` returns only `treasury_auctions`, an unrelated Treasury issuance store).
  Halts are inferred as zero-variance and then **dropped**: `engine/theme_crowding.py:47` ("zero-variance (halted) members first so one constant column can't NaN the
  matrix") and `engine/group_flow.py:91` ("all-NaN AND zero-variance (halted / constant-price) members
  first");
  `engine/synthetic_control.py:454` and `engine/bar_derive.py:365` route around them. Silent exclusion is a
  daily-grain survivorship mechanism inside every cross-sectional statistic the site publishes. The
  continuity check does not fix it — it **counts** it, and the count is the finding.

### 3.6 Distribution — a value is possible *given the dataset's own history*

- **Not implemented.** `CheckFamily.DISTRIBUTION` at `lib/dataos/quality.py:78`.
- **Definition:** three sub-checks, all descriptive-first:
  1. **Level shift.** `|z|` of the latest change against a trailing window > `macro_outlier_z: 5.0`
     (`scripts/audit_common.py:52`) → FLAG.
  2. **Silent revision of settled history.** A value more than `n` periods old changing by more than
     `macro_revision_alert_pct: 5.0` (`scripts/audit_common.py:47`) vs a stored baseline → **fail**, not
     flag. This is the only threshold in the family that blocks, and correctly: settled history moving is
     either a real revision (which must appear in the revision chain, §D3 `revision_seq`) or a bug.
  3. **Detector-went-blind.** A checked population *shrinking* is as suspicious as it growing.
     `scripts/audit_price_basis.py:33-36` already encodes the shape: `price_basis_divergence` is a FLAG on
     "count / max reldiff of close vs close_price across the ETF universe (trend it — **a collapse toward 0
     means the basis silently reverted**)." Generalize: every distribution check publishes its own
     denominator, and a denominator that falls is a finding.
- **Severity:** `INFO`/`WARN` for (1) and (3); `BLOCK` for (2) on a `PRODUCED` published dataset.
- **Idempotence carve-out to preserve:** `scripts/audit_common.py:7-9` notes the macro revision baseline is
  the one deliberately non-idempotent audit — "a revision is caught once, then the baseline absorbs it and a
  re-run is clean." Keep that; a revision check that re-fires forever is a revision check nobody reads.

### 3.7 Cross-source reconciliation — §4, in full

### 3.8 Referential integrity — §5

### 3.9 Temporal integrity — §6

---

## 4. Cross-source reconciliation: the four US price stores, worked

`CheckFamily.CROSS_SOURCE` is declared (`lib/dataos/quality.py:79`) and unimplemented. This section defines
it, because the estate's largest measured defect lives here and because the naive implementation — one
relative-difference epsilon — cannot distinguish expected disagreement (different declared bases) from a real
defect (same declared basis, different adjustment vintage), and so fires on every dividend payer forever
while still missing nothing it could act on. §4.2 and §4.3 are that distinction.

### 4.1 The measurement

VERIFIED this session, `python3` + pandas over `/Users/chriswong/Documents/Cluade/Macro Dashboard/data`:

```
counts stocks/yahoo/baskets/massive: 229 824 2519 20476     (per-ticker parquet files)
```

HON, one ticker, two dates, every store that carries it:

| Store / column | 2025-09-25 | 2026-06-29 |
|---|---|---|
| `data/stocks/HON.parquet` `close` | 192.573517 | 227.800003 |
| `data/yahoo/HON.parquet` `close` | 192.419067 | 227.800003 |
| `data/yahoo/HON.parquet` `close_price` | 195.758713 | 227.800003 |
| `data/baskets/ohlcv/HON.parquet` `close` | 201.964905 | 227.800003 |
| `data/massive_stock_day/HON.parquet` `close` | 207.700000 | 227.800000 |

**Five distinct numbers for one (ticker, date), converging to exact agreement at the tape tip.** The census
verifier reported four (it did not include `massive_stock_day` for HON); the fifth reading is reproduced
above. Cross-check on NVDA 2025-09-25 gives 177.463654 / 177.463669 / 177.690002 / 177.670502 / 177.690000 —
the same five stores, disagreeing by less, which is why the defect reads as rounding noise unless probed by
name.

The stores' declared bases are not folklore — `collectors/yahoo.py:6-11` documents the dual-basis store:
`close` = total return (Adj Close, `auto_adjust=False`); `close_price` = split-adjusted, dividend-unadjusted,
"the correct basis for all structure math."

### 4.2 The two axes are different defects and need different verdicts

**BASIS divergence** — the stores are measuring different quantities, correctly. `close_price` (split-adj)
*should* exceed `close` (total-return) going back through dividends for a payer; `massive_stock_day`'s raw
print *should* exceed both. This is expected disagreement. A relative-difference epsilon fires on it every
night, on every dividend payer, forever.

**VINTAGE divergence** — two stores claim the **same** basis and disagree, because one has back-adjusted
through a corporate action the other has not. §D4 already names the fix (`adjustment_asof` on every adjusted
dataset); this is the check that detects the absence of it.

VERIFIED, and this is the number that justifies the family. `data/stocks.close` and `data/yahoo.close` are
**both** total-return by declaration. Over their 170 co-covered tickers:

```
TR-vs-TR over 170 co-covered names: 30 exceed tol=1e-3, 140 within
worst 8 (max |rel diff|, %): SPGI 5.700, HON 5.172, MO 1.496, CMCSA 1.363,
                             BMY 1.129, NKE 0.887, USB 0.856, MDLZ 0.838
```

**30 of 170 (17.6%) of co-covered names in `data/stocks` (133 reader files, per the verifier's
`grep -rl 'data/stocks' engine scripts collectors lib app`) and `data/yahoo` disagree with each other on a
column both declare to be the same quantity**, by up to 5.7%.

The divergence has a diagnostic shape. HON, `data/stocks.close / data/baskets.close` over 3,140 overlapping
dates: the ratio clusters at **exactly two levels** — ≈`0.95350` and ≈`1.00282` (5 distinct values at
6-dp rounding, i.e. float noise around two levels) — and the last date on which the two frames disagree is
2026-06-26, after which they are identical. Two adjustment events separate the two
frames. Against `data/yahoo.close`, 739 of 750 overlapping dates differ, ratio at the last differing date
1.0028154 — a dividend-sized step.

### 4.3 The verdict rule

```
declared_basis(A) ≠ declared_basis(B)
    → the comparison is a CATEGORY ERROR, not a discrepancy.
      Check only that the ratio is CONSISTENT with the declared relationship
      (monotone in the expected direction going backwards, steps only at ex-dates).
      Verdict: AGREE if consistent, DISCREPANT_MINOR if not.  Severity INFO/WARN.

declared_basis(A) = declared_basis(B), adjustment_asof(A) = adjustment_asof(B)
    → tolerance is EXACT: |A/B - 1| <= 1e-6 on every overlapping date.
      Any break is DISCREPANT_MAJOR.  Severity DEGRADED, and BLOCK if both stores
      sit on the same resolution ladder for one study.

declared_basis(A) = declared_basis(B), adjustment_asof(A) ≠ adjustment_asof(B)
    → VINTAGE divergence.  Verdict WITHIN_TOLERANCE only if the ratio is a step
      function whose breaks all fall on ex-dates between the two vintages.
      Absent a corporate-action event store, that condition CANNOT BE EVALUATED
      → verdict UNRESOLVED.  Severity DEGRADED.  Never AGREE.
```

The tolerance numbers use `#D7`'s state vocabulary (`AGREE · WITHIN_TOLERANCE · DISCREPANT_MINOR ·
DISCREPANT_MAJOR · UNRESOLVED`) and the third branch is the one that matters most, because it is where the
repo actually is:

**No corporate-action event store exists, and the repo's own contract declares it.**
`contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:246` pins
`"point_in_time_corporate_actions": {"const": false}` (and `:247` `"total_return": {"const": false}`), with
both names in the `required` list at `:232-233`. CN is the same by choice —
`collectors/china_tushare_spine.py:47` declares "``daily`` is unadjusted nominal price authority" and `:2573`
stamps `price_source_basis = "tushare.daily_unadjusted_nominal"`, while `:4736` lists
"pro_bar adjusted-price construction" under the manifest's `not_tested` array;
`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:51` states "`pro_bar` is not used" and `:294` lists
"adjusted `pro_bar`" under Not tested. Therefore
**basis divergence and vintage divergence are not distinguishable from prices alone**, and the honest verdict
for a same-basis cross-store disagreement today is `UNRESOLVED`, not `DISCREPANT_MAJOR`. Reporting
`UNRESOLVED` is the whole point: it names the missing input (an event table) instead of asserting which store
is wrong.

### 4.4 The detector already exists — it is just never pointed across stores

`lib/store.py:106 basis_shifted(group, name, new, col="close", tol=1e-3)` is an adjustment-vintage detector.
Its docstring (`:108-126`) is the clearest statement of the problem anywhere in the repo: "yfinance
re-adjusts the WHOLE series at every fetch, so splicing a short re-based window onto stored history strands
every pre-window row on a stale basis … (measured: `data/yahoo/SPY.parquet` uniformly +0.2576% off a fresh
fetch on all 8,382 rows before 2026-05-18 — exactly one dividend of drift)." It even records that
`upsert(overwrite_overlap=True)` cannot repair the class.

It compares **stored vs freshly-fetched, within one store**. The 30-of-170 result in §4.2 is the same
function's tolerance (`1e-3`) applied **across** stores, which nothing does. Cross-source reconciliation V1 is
therefore not new code — it is `basis_shifted` generalized to a `(dataset_A, dataset_B, column, tol)` signature
plus the §4.3 verdict table.

Second existing piece, and it should be generalized rather than re-derived:
`scripts/reconcile_prophet_live.py:110-130` already solves vintage-safe comparison for one lane, by freezing
an anchor on the event's own session — `px_adj_factor = close_same_day / cross_basis_close`, with the
explicit law "NO ANCHOR ⇒ NO CLAIM" (`:129-131`). That is the correct pattern for any historical cross-source
comparison and belongs in the shared module.

### 4.5 Store choice is a declared input to a statistic, not an implementation detail

The strongest in-repo evidence that this is not theoretical: `engine/washout_turn.py:55-72` documents that
its `_load_close` prefers `data/baskets/ohlcv/`, splices deeper history from `data/stocks/` then
`data/yahoo/` with boundary ratio-alignment, and states outright that "recent-close disagreements between
stores are real (split/dividend adjustment epochs differ …) — so the SIGNAL legs … keep reading the preferred
store's values unchanged." Measured consequence in the same docstring: "the 2026-07-31 MCD cross read depth
8.6 / n=8; off the full store it reads 6.3 / n=36 (same state, same since)." A published percentile moved
from 6.3/n=36 to 8.6/n=8 **purely by store choice.**

`engine/price_ladder.py` is the de-facto resolution contract and its central premise is measurably false:
`ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")` (`:104`) treats three of
those as one interchangeable adjusted family and returns `adjusted=True` for all of them, while §4.2 shows
30/170 of two of them disagree past its own house tolerance. The module DID measure one pair — "on all 400
names carried by BOTH extras and baskets/ohlcv the two frames are bit-identical, max relative difference
0.00e+00" (`:92-95`) — and never measured the other pairs.

**Requirement CS-1:** every derived statistic records the `dataset_id` and `adjustment_asof` of the price
series each leg resolved to. `engine/price_ladder.py` already stamps the source per row and already discloses
its coverage hole honestly ("recovers ZERO of the 154 board-admitted names that still fall through to the raw
cache … 20.6% of freshly-graded us_board rows", `:97-101`) — extend that stamp with the vintage, do not build
a second ladder.

---

## 5. Referential integrity — against the Security Master

- **Callable:** `lib/dataos/quality.py:271 check_referential(rows, id_col, known_ids, ...)`. The `known_ids`
  set is the §D2 Security Master. Until that exists, this family is PROPOSED, not PRODUCED.
- **Rule:** every id-bearing column in every dataset resolves to a live `msec_id` in the master, at the row's
  own `known_at` (a delisted security resolves for dates before its delisting and not after).
- **Severity:** `BLOCK` on a published tape; `DEGRADED` on a research table.
- **Mandatory opt-out with a stated reason.** `collectors/biocatalyst/drugs_at_fda.py:647,661` turns FKs OFF
  deliberately — "foreign key is enforced because source-native orphans are facts to retain" /
  `PRAGMA foreign_keys=OFF`. A framework without a declared opt-out breaks that store. Registry field:
  `referential_opt_out: <reason>`; a bare `true` is not accepted.

**What exists today, and why it is not integrity:** three unconnected checks for the same violation class
("a declared member has no price series"), each reporting differently.

| Implementation | Reports | Blind to |
|---|---|---|
| `scripts/fetch_basket_ohlcv.py:167,296` — `"{n} basket member(s) have NO price series on any store rung"` | basket members dark across all `FALLBACK_RUNGS` (`:170-176`) | non-basket universes |
| `engine/prophet_stage_fusion.py:25,1280` + `scripts/run_prophet_stage_fusion.py:189` | SP1500 PIT members that traded but have no price source | everything else |
| `collectors/yahoo.py:167-169` | a 30%-loss threshold, raise below 70% | any loss under 30% |

Two places enforce FK-style integrity inside a store: `engine/context_index/schema.py:70`
(`PRAGMA foreign_keys=ON`) and `scripts/check_entity_thesis_registry.py:12,193-196` (`ETM-C7 referential
integrity`). **Nothing performs a cross-store integrity check.** Nothing verifies that every ticker in a
membership snapshot, ledger, basket, or watchlist has a resolvable row in the price plane.

The measured cost of that absence is the MMC incident, documented in `lib/ticker_aliases.py:19-27`: the
`MMC → MRSH` alias lived in `scripts/fetch_basket_extras` and not in `scripts/fetch_basket_ohlcv`, so
`data/baskets/ohlcv/MMC.parquet` never existed, and the `insurance` basket rendered on 18/19 members and
`us_sector_financials` on 75/76 **for seven months**. A cross-store referential check against a master would
have surfaced it on night one.

---

## 6. Temporal integrity — future information in past records

- **Callable:** `lib/dataos/quality.py:300 check_temporal_integrity(rows, profile, now=...)`, default `BLOCK`
  (`:306`). Two invariants implemented: `known_at` may not exceed the injected `now` (`:335-341`), and
  `effective_at` may not precede `period_end` (`:352-362`). Rationale at `:309-311` — "both of which a silent
  violation of makes a backtest LOOK better."
- **Three more invariants this family owes, none implemented:**
  1. **Grading clock ≥ origination clock.** A forward-outcome row whose `close_date` predates the plan's own
     origination is graded on bars the plan was never live for.
  2. **PIT read refusal.** §D3's law — a dataset whose `temporal_profile` lacks the clock needed to answer
     `known_at` must RAISE on an `as_of(t)` read, never silently return the latest vintage.
  3. **Vintage ≤ as-of.** An adjusted price series read `as_of(t)` must carry `adjustment_asof <= t`. This is
     the §4 defect expressed as a leak — today's back-adjustment applied to a 2024 backtest is future
     information in a past record. (INFERRED that this is the mechanism behind the SPGI/HON divergences in
     §4.2; it cannot be VERIFIED in-repo precisely because no corporate-action event store exists to check
     the ex-dates against.)
- **Where the house already got this right, and it is the model:** `data/prophet/ledger_quarantine.json`
  (VERIFIED via `git show HEAD:data/prophet/ledger_quarantine.json` in the worktree — this file is absent
  from the broken materialized checkout). Schema `prophet.ledger_quarantine/v1`, `quarantined_on 2026-08-06`,
  `count 11`, rule verbatim:

  > "a forward-ledger row whose close_date strictly predates the plan's own origination date (plan.asof) — the
  > outcome was scanned from the base formation anchor, so it was graded on bars the plan was never live for"

  Effect, verbatim: "the row STAYS in ledger.jsonl (append-only); every reader that summarises the record
  excludes these ids from both numerator and denominator." Worst row: `KKR-BULL-20260318`,
  `close_date 2026-05-04` vs `origination_date 2026-07-14` — a 71-day predate.

  **That is the reference implementation of BLOCK-with-last-good for an append-only store**: nothing is
  deleted, the defect is named per-row, and the exclusion is a stated contract on readers rather than a
  mutation. Generalize this shape; do not invent a second one.
- **One census smell to drop.** The macro lane's "`lag_bd` vs `lag_bd_measured` leak inside the leak-fix" does
  not exist: `engine/pit.py:181-191 _effective_lag_bd()` already prefers config override > learned > measured
  > prior, documented at `engine/pit.py:106-107` and called at `:230,323`.

---

## 7. Data incidents

### 7.1 What is an incident

**A data incident is a period during which a named dataset served values that a consumer would not have
accepted had the defect been known, bounded by a start and (once healed) an end.**

Three properties distinguish an incident from a finding:

1. It has a **time interval**, not a timestamp. "Store X was wrong between date A and date B for reason R" is
   the only form that lets a consumer invalidate a cached backtest.
2. It is **addressed to consumers**, not to operators. A finding tells you to fix something. An incident tells
   everyone downstream what they must re-run.
3. It **outlives the fix.** The repair closes the finding; the incident record stays forever, because a study
   run during the interval is still wrong after the fix lands.

A finding escalates to an incident when: any `BLOCK`; a `DEGRADED` streak of ≥3 consecutive nightly runs; a
`DISCREPANT_MAJOR` or `UNRESOLVED` on a canonical field (§D7); or any defect that has already been **served**
to a user or written into an append-only ledger.

### 7.2 Severity ladder

| Level | Meaning | Obligation |
|---|---|---|
| `I4 — SILENT-SERVED` | wrong values reached users or an append-only ledger and nothing disclosed it | disclose on the affected surface (§9); quarantine the affected rows; the interval is published |
| `I3 — SERVED-DEGRADED` | wrong or absent values reached users **with** a disclosure already showing | fix; keep the disclosure until healed; interval published |
| `I2 — CONTAINED` | detected before publication; last-good served | fix; no user-facing disclosure required; interval recorded |
| `I1 — LATENT` | a defect proven present but with no demonstrated consumer effect | recorded; a coverage claim ("latent, nothing ships") is a claim about the whole corpus and must be swept before it is made |

`I4` and `I3` are the only levels that reach a user. `I1` exists to force a corpus sweep before the claim is
made: "latent, nothing ships" is a statement about every consumer of the dataset, and the framework treats it
as a claim requiring evidence rather than a default.

### 7.3 The incident record

One JSON object per incident, append-only, one file per incident under `data/incidents/<id>.json` (PROPOSED —
no such directory exists today: `ls research/ | grep -iE incident` returns nothing, and no `data/` directory
matches an incident registry).

```
incident_id           INC-YYYYMMDD-<slug>              stable, never reused
class                 one of the eight in §7.4
level                 I1 | I2 | I3 | I4
datasets              [dataset_id]                     registry ids, never paths
interval              {first_bad, last_bad|null}       null = still open
detected_at           when a check first fired
detected_by           the check family + call site, or "human"
root_cause            one paragraph, mechanical
blast_radius          {rows, entities, surfaces[], downstream_dataset_ids[]}
consumer_action       what a downstream reader must RE-RUN, in the imperative
remediation           {kind: heal|quarantine|retire|accept, ref: PR or commit}
disclosure            {surfaces[], copy_en, copy_zh} | null
receipt               {commit_sha, run_id} of the run that closed it
supersedes            incident_id | null
```

`interval.first_bad` is the field the whole record exists for. `blast_radius.downstream_dataset_ids` is
resolvable from the §D9 registry DAG with no new store.

### 7.4 The eight classes — detection, and whether the repo has already had one

All eight have already happened here. Each is cited.

| Class | Already happened? | Evidence |
|---|---|---|
| Missing universe | **Yes, twice** | MMC: 7-month basket hole, `lib/ticker_aliases.py:19-27`. CTRA/TPH: "sat frozen for three months," `collectors/yahoo.py:39-42` |
| Stale realtime feed | **Yes** | `scripts/freshness_sentinel.py:4-6` — "The 2026-08-06 outage left the boards frozen for six days because every alarm lived inside GitHub Actions — the thing that was failing" |
| Price mismatch | **Yes, live now** | §4.2: 30/170 co-covered names disagree past `1e-3` on a same-declared-basis column; HON five-way at 2025-09-25 |
| Time-shifted bars | **Yes** | `scripts/migrate_polygon_gex_session_stamps.py:1-31` |
| Duplicate observations | **Yes, twice** | SATS/ECHO double-count, `engine/ledger_identity.py:18-36`. `scripts/migrate_polygon_gex_session_stamps.py:33` — "13 collision losers -> removed (pure duplicates of a kept session)" |
| Incorrect corporate-action adjustment | **Yes** | `engine/price_ladder.py:38-44` — the cache re-base |
| Point-in-time leakage | **Yes** | 11 quarantined Prophet rows, `data/prophet/ledger_quarantine.json` (§6) |
| Wrong security mapping | **Yes** | MMC→MRSH and SATS→ECHO, above; `collectors/edgar_deadnames.py:7` — "of the 1,083 dead-only tickers in" `data/breadth/sp1500_pit_membership.parquet`, none carry fundamentals, because `edgar.py` cannot map a delisted CIK back to its old ticker |

Per class, the detection that must exist:

**Missing universe.** Referential integrity (§5) of the declared universe against the Security Master, plus
completeness at the universe grain. Detection today is the 70% raise at `collectors/yahoo.py:168-169` and the
per-basket dark report at `scripts/fetch_basket_ohlcv.py:296`; neither runs against a master.
*Incident-worthy because:* the insurance basket rendered 18/19 and `us_sector_financials` 75/76 for seven
months with no user-visible tell, and every coverage receipt "quietly rounds down"
(`scripts/fetch_basket_ohlcv.py:296-300`).

**Stale realtime feed.** Freshness (§3.2) with `anchor: served_file` and a clock-time SLA, checked from
outside the producing infrastructure. `scripts/freshness_sentinel.py` is the correct architecture and should
not be rebuilt — extend `SURFACES` (`:245`). Its own docstring records the trap a naive check falls into
(`:20-26`): during the Jul-31→Aug-6 freeze "the nightly re-baked the page every single day while the board
froze, so `Last-Modified` stayed green throughout." Bake stamps and content watermarks are different anchors.

**Price mismatch.** §4. Detector = `lib/store.py:106 basis_shifted` generalized cross-store, run nightly over
every co-covered pair among the four US stores, verdicts per §4.3.

**Time-shifted bars.** Temporal integrity plus a session-stamp conformance check: every dated artifact's
stamp must equal `nyse_calendar.expected_last_session` of its accrual instant, never
`datetime.now(timezone.utc).date()` and never `session_date()`. The polygon_gex postmortem states both
mistakes precisely (`scripts/migrate_polygon_gex_session_stamps.py:4-21`): the run-date stamp put the store
"one session forward of the market it measures," the write-side `is_session` gate then "REFUSED every
Saturday-UTC run — which is a Friday-evening ET accrual. That is why Fridays are missing from the store," and
`session_date()` "calls the whole ET calendar day 'the session'." The repair is already applied at the write
site: `scripts/collect.py:843-848` now passes an instant, with a comment explaining that this is load-bearing.
The **verification method** in that migration is the reusable part and should become the check: compare
`abs(close(session) - spot)/spot` **across the cross-section**, not on one anchor — "SPY alone called the
08-06 file '0.175% — fine' while 59% of its names disagreed" (`:23-26`).

**Duplicate observations.** Uniqueness (§3.3) on the **resolved identity**, plus the identity-drift guard
`scripts/check_symbol_rename_drift.py`. The SATS/ECHO case proves that a uniqueness check keyed on a symbol
string cannot see a rename duplicate (`engine/ledger_identity.py:38-42`).

**Incorrect corporate-action adjustment.** The vintage branch of §4.3, plus an immutability rule on graded
history. `engine/price_ladder.py:36-44` is the receipt: "`PNC` at 2026-06-22 read `234.71` in the
2026-07-01 commit and `232.85` on 2026-08-06 … re-running `scripts/grade_us_board.py` against the shipped
ledger would have moved **75 already-published rows, 19 of them materially (worst −1.94pp on `LPG`
2026-06-18 H5)**. That is why callers stamp the basis on the row and why an already graded row is never
re-priced." The measured drift window is stated too (`:31-32`): rebuild dates cluster at p05 `2026-05-13` /
median `2026-06-01`, "so a window that closes before the last rebuild carries ZERO bias and a June–July 2026
window carries all of it." **That per-row prose stamp is exactly the seam to formalize as `adjustment_asof`**,
and it must cover the adjusted family, not only the unadjusted cache fallback.

**Point-in-time leakage.** Temporal integrity (§6). The Prophet quarantine is the model for both detection
and remediation.

**Wrong security mapping.** Referential integrity plus alias-table conformance. The specific detector: two
identity surfaces disagreeing. Today at least ten exist and they demonstrably do disagree —
`engine/ledger_identity.py` knows SATS/ECHO; `lib/ticker_aliases.py` (2 entries) does not;
`config/theme_graph_identity_breaks.yml` mints a third collision convention (`co:<market>:<SYMBOL>#2`) while
CN uses `CN-XSHG-600519`. A conformance check that every alias surface agrees with the master is mechanical
and would have caught all three of the incidents in this row.

**One class the brief does not name and the estate needs:** *undisclosed mixture*. The verifier's correction
to the `data/stocks` "no open" claim lands here — opens **are** obtainable, from `data/baskets/ohlcv` (2,519
names, real `open`, cited in-repo at `engine/marketing/chart_render.py:254` ("the baskets parquet carries a REAL `open` column, which data/stocks/ …")
and `engine/marketing/hot_tape_pack.py:13,62`) or synthesized as `open := prior close` by
`engine/ohlc_reconstruct.py`, whose own docstring warns at `:23` that the reconstructed "high/low should NOT
be trusted for tail-risk stop sizing." The defect is not absence; it is that a gap feature built from a baskets `open`
against a stocks `close` crosses two adjustment vintages and **nothing stamps which open the caller got**.
Detection: a derived dataset whose inputs resolve to more than one `dataset_id` for the same field must
declare the mixture in its receipt, or it is a finding.

### 7.5 Where the registry lives, and why prose is not it

Today: seven free-text postmortems in `research/` (`POSTMORTEM_20260714_…`, `POSTMORTEM_20260716_…`,
`POSTMORTEM_20260722_…`, `POSTMORTEM_20260723_…`, `POSTMORTEM_20260803_…`, `MAG7_TURN_POSTMORTEM_BY_FABLE.md`,
`RISK_ON_REGIME_SHIFT_POSTMORTEM_2026-06-29_TO_2026-07-08.md`), six `ops/*_RUNBOOK.md` files (VERIFIED: `ls ops/*RUNBOOK.md | wc -l` → 6), and the rest as docstring prose in
the modules cited in §7.4. Detection in this repo is genuinely good; **memory is the
gap.** No reader can ask "was `data/stocks` trustworthy in June 2026" and get an answer.

The incident registry is a **store**, not a document: `data/incidents/*.json` + an index, queried by
`dataset_id` and by interval. It does not replace postmortems — a postmortem is the narrative, the incident
record is the machine-readable interval a consumer joins against. Routing on open/close reuses
`engine/alert_triage.py:1233 push_ops_alert(source, type_, message, severity, lane, …)`; no second alerting
spine.

---

## 8. `mastermind data health`

One command, three modes, no daemon. It reads artifacts that already exist plus the registry; it computes
nothing itself.

```
$ python -m scripts.data_health                # summary
$ python -m scripts.data_health --dataset equity.bars.daily.stocks
$ python -m scripts.data_health --coverage     # FR-2: what is NOT measured
$ python -m scripts.data_health --json         # machine form, for the site build
```

### 8.1 Summary output

Illustrative shape. The `DATASETS` line carries the two measured numbers (7 registry rows, 329 `data/`
directories, §0.3); the `FINDINGS`/`INCIDENTS` counts are placeholders, and the individual findings shown are
real defects from §3–§7 rendered in the proposed format.

```
mastermind data health · 2026-08-12T14:02Z · commit 5e607da · registry dataset_registry.v1

  DATASETS      7 registered / 329 data dirs present          COVERAGE 2%   ← FR-2
  FINDINGS      3 BLOCK · 11 DEGRADED · 24 WARN · 61 INFO
  INCIDENTS     1 open (I3) · 7 closed

BLOCK
  equity.bars.daily.stocks     uniqueness    2 duplicate (ticker,date) keys after
                               identity resolution — SATS/ECHO
                               → engine/ledger_identity.py:18
  us.prophet.ledger            temporal      1 row known_at in the future
  equity.bars.daily.massive    continuity    832-weekday gap run, anchor SPY

DEGRADED
  equity.bars.daily.stocks     cross_source  30/170 names disagree with
                               equity.bars.daily.yahoo past 1e-3 on a
                               same-declared-basis column; verdict UNRESOLVED
                               (no corporate-action store) — worst SPGI 5.70%
  equity.bars.daily.stocks     freshness     9/229 names behind the store tip,
                               worst 2026-06-18 vs tip 2026-07-08
  ...

UNMEASURED  (no registry row — these produce nothing and prove nothing)
  data/options_flow  data/options_entry  data/options_exit  data/china_stocks_raw
  ... 318 more                                            → --coverage for the list
```

The `UNMEASURED` block is not a nicety. It is the honest form of the §0.3 finding, and it is the number that
must fall over time. A health report that lists only what it measures reports 100% green on a 2%-covered
estate.

### 8.2 What feeds it

| Section | Source | Exists today |
|---|---|---|
| dataset roster + SLAs | `config/dataset_registry.yml` | yes (7 rows, untracked) |
| findings | `lib/dataos/quality.py` checks run by the nightly, persisted to `data/quality/<dataset_id>.json` | the directory exists — 11 audit JSONs including `price_basis_audit.json`, `price_store_freshness.json`, `membership_reconcile.json` |
| collector status + breaker | `data/run_status.json` (`sources`, `circuit_breaker`, `stale_series`) | yes, 45% coverage |
| live-artifact ages | `app/main.py:558 /api/status` | yes |
| external estate | `scripts/freshness_sentinel.py` state dir | yes |
| incidents | `data/incidents/*.json` | **PROPOSED** |
| coverage denominator | `ls data/*/` vs registry rows | trivial |

`--json` output is what the site build reads to render the user-facing state (§9); the two must not diverge,
so the JSON is the artifact and the text is a rendering of it.

### 8.3 Exit codes

`0` clean or INFO/WARN only · `1` any DEGRADED · `2` any BLOCK · `3` the report could not be produced
(registry unreadable). `3` is distinct on purpose: a health report that cannot run is not a green health
report — the same INDETERMINATE-is-not-a-pass rule as `scripts/freshness_sentinel.py:56-60`.

---

## 9. How DEGRADED reaches the user honestly

The house already has the correct pattern in two places. Copy it; do not design a third.

**Precedent 1 — `engine/hk_freshness.py:410-475`.** Its comment block at `:411-417` states the copy law
better than a spec could: "PLAIN WORDS ONLY (User-First Design Doctrine, Tier 1). No internal vocabulary — no
store slugs (cache/bellwether/southbound), no 'snapshot', no 'incoherent'. The mechanical per-store details
stay in `stores` for the Tier-2 data-feeds panel. Copy shape: one lead sentence stating what it means for the
reader, then ONE short specific clause (a date) so it isn't vague." Shipped copy, degraded case (`:456-466`):

> EN: "Some background feeds are a step behind — prices and picks are current. (prices current as of {date})"
> ZH: "部分后台数据来源稍有滞后 — 价格和选股仍是最新的。（价格截至 {date} 为最新）"

**Precedent 2 — `templates/china.html.j2:1538-1542`,** the CN board-delayed banner, and its US twin at
`templates/dashboard.html.j2:15713-15714`. Note `templates/china.html.j2:1531-1535`: the English phrase
"prices as of YYYY-MM-DD" is **load-bearing** — `scripts/freshness_sentinel.py:17-26` describes parsing it to
measure the board's self-reported lag against a per-surface `delay_budget_days` (`:245-268`). Degradation copy is a machine contract as well as user copy; revising the wording
without revising the sentinel breaks the external dead-man switch.

**The eight laws for degradation copy:**

1. **State, then consequence, then one date.** Never a mechanism, never a slug, never a dataset_id.
2. **Bilingual in both spans** (`l-en` / `l-zh`), and never in a `title=` attribute — CI-guarded by
   `scripts/check_title_i18n.py`.
3. **Never falsifier or refutation language on a user surface.** No "falsifier fired", "thesis refuted",
   "证伪", no study names. Operator ruling 2026-07-27 (#3821), recorded in `CLAUDE.md` § House laws → Design. Full verdicts live below the fold on the
   Calibration Lab; user surfaces show what is being watched and a quiet "read being updated" state.
4. **Never the word "validated" without a backing artifact** — mechanically enforced by
   `scripts/check_validated_claims.py`, in EN and ZH, with negated/hedged uses correctly exempt (`:18-23`).
5. **One page, one verdict.** `templates/china.html.j2:1554-1559` explains why: the freshness pill's
   `delayed` leg exists "to keep this pill from reading 'Fresh' directly above the delayed-board banner at
   the top of the grid."
6. **Degrade toward less confidence, never toward more.** `research/PERCEPTION_CONTRACTS.md:21-25`:
   "wrong data DEGRADES, never sharpens (P2). A missing input must widen distributions toward uniform / lower
   confidence / mark the object degraded. The inverse — missing data silently reading as full-confidence — is
   the exact `missing-stockdata → confluence=1.0` failure."
7. **Disclosure is placed where the watcher looks, not where the code is tidy.**
   `templates/china.html.j2:1527-1530` — the banner is deliberately OUTSIDE the page's mode split, because
   "a disclosure nested in the stocks-only block would leave the watched page silent during exactly the
   freeze it exists to announce."
8. **Tier-2 carries the mechanics.** Store names, ages, verdicts, incident ids go in the hover/detail panel
   (`engine/hk_freshness.py:229-230` `stores` + `banner_message`), never the glance tier.

**Artifact contract.** Every DEGRADED/BLOCK dataset writes `degraded: true` + `degrade_reason` into the
artifact its page reads — the field names `research/PERCEPTION_CONTRACTS.md:21` already standardizes — plus
`incident_id` when one is open. The page renders from those fields; it never re-derives a verdict.

**One state the user must be able to see and cannot today:** `UNRESOLVED` (§4.3). When two stores disagree and
we cannot say which is right, the honest surface is not silence and not a chosen number. The compliant form
is the existing null-disclosure shape: a plain-word statement that the figure is being reconciled, with the
Tier-2 receipt naming both readings. That is `DEGRADED` with a disclosure, not `BLOCK`.

---

## 10. Emission

Every annotation is a bare `print` at column 0 with `flush=True`, never through a logger:

```python
print(f"::warning title={slug}::{message}", flush=True)
```

`lib/dataos/quality.py:373 annotation_line` renders the line and `:386 emit_annotations` prints it, with the
reason inline at `:388-391`. The severity→level map is `lib/dataos/quality.py:365-370`
(`INFO → notice`, `WARN → warning`, `DEGRADED → warning`, `BLOCK → error`).

The guard is `tests/test_gh_annotation_line_start.py`, whose docstring states the failure mode exactly:
`log.warning("::warning …")` emits `WARNING ::warning …` and "GitHub silently drops it. The call looks like
an alarm in code review, runs without error, and produces NOTHING in the Actions summary." It shipped dead
five times — the test docstring names #3487, #3515, #3563, #3570 and #3562, "which merged a fresh one on
2026-07-26, the same day the others were being fixed" (`tests/test_gh_annotation_line_start.py:16-18`); the
69-site sweep in #3587 is recorded in `CLAUDE.md` § House laws. `flush` is load-bearing because stdout is
block-buffered when piped in CI.

Live example of the correct form in this repo: `scripts/collect.py:908-911`.

Two operational notes:

- **Modules that never run inside an Actions step are exempt** and are listed in that test — FastAPI request
  paths (`brain_gateway`, `download_quota`, `view_ratelimit`). `mastermind data health` run on the VPS is in
  that category; it prints a human report, not annotations.
- **Converting a site breaks any test asserting via `caplog`.** Switch such a test to `capsys` and assert
  `line.startswith("::")`, so the test pins the defect rather than the wording.

---

## 11. Order of work

| Phase | Work | Depends on | Why here |
|---|---|---|---|
| Q0 | Commit `lib/dataos/` + `config/dataset_registry.yml` + the 6 `tests/test_dataos_*.py` files | ownership resolution with the sibling lane | VERIFIED `wc -l tests/test_dataos_*.py` → 1,729 lines across 6 files, none of which CI has ever run; the whole framework is one `git clean` from gone |
| Q1 | FR-0…FR-4 (§0.5): one freshness primitive, `freshness_sla` in the registry, published coverage, close the bolt-on bypass, provenance on `run_status.json` | Q0 | a 45%-covered, unmeasured registry makes every later number a lie |
| Q2 | `mastermind data health` over what already exists (§8), including the `UNMEASURED` block | Q1 | zero new detection; makes the estate's blindness visible and is immediately useful to every session |
| Q3 | Cross-source reconciliation (§4): generalize `lib/store.py:106 basis_shifted` cross-store; wire the §4.3 verdict table; stamp `adjustment_asof` per `engine/price_ladder.py` row | §D4 V1 labels | the largest measured live defect (30/170) and the one that already forced a stop-ship, `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` |
| Q4 | Continuity + distribution (§3.5, §3.6) | Q1 | the two unimplemented families with existing thresholds — cheap |
| Q5 | Incident registry (§7) + backfill the eight documented incidents | Q2 | memory, not detection, is the gap; backfilling proves the schema |
| Q6 | Referential integrity against the Security Master (§5) | §D2 Phase 1 | blocked on the master; PROPOSED until then |
| Q7 | Temporal-integrity invariants 2 and 3 (§6) | §D3 PIT readers | research validity |

---

## 12. What this framework does NOT build

Per §D11, and named so a future session does not re-propose them:

- No data-quality SaaS, no Great Expectations / Monte Carlo / Soda dependency. Checks are pure functions in
  `lib/dataos/quality.py` and therefore unit tests.
- No second alerting spine. `engine/alert_triage.py:1233 push_ops_alert` is the route.
- No second ownership registry. `config/sector_intelligence_ownership.yml` (477 lines,
  `one_writer_required: true`, `duplicate_writer_behavior: hard_fail`, `unresolved_owner_behavior:
  block_or_degrade`, `:6-13`) is extended, not duplicated — its scope today is
  sector-intelligence/biocatalyst/corporate-intelligence/capital-structure, and **no price, macro, options,
  news or CN store carries a `canonical_owner` row**, which is the actual gap.
- No second control plane or authority map — standing cross-repo prohibition (`duplicate_control_planes`,
  Mastermind `AGENTS.md`).
- No Redis, no queue, no streaming tier. The census found **zero** real Redis client sites; the earlier count
  was substring false positives on "redistribution". Files + parquet + R2 + git is the declared house answer.
- No `fillna(0)` class-wide validator (§3.4) — two named idioms only.
- No unification of the four detector ids held by `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`. Registering a known
  divergence is mandatory; resolving one is a product decision.
- No re-litigation of `engine/price_ladder.py`'s 20.6% raw-cache fallback (`:97-101`). It is a disclosed
  standing coverage hole, correctly stamped per row; the framework counts it, it does not close it.

---

## Appendix A — verification log

Commands run in this session, with the claims they support.

| # | Command (abbrev.) | Supports |
|---|---|---|
| A1 | `python3 -c "json.load(open('data/run_status.json'))"` → 149 sources, checked_at ∈ 2026-07-05..09, `last_run 2026-07-09T06:48:30Z`, keys `[last_run, sources, circuit_breaker, circuit_breaker_probe, stale_series]` | §0.3 |
| A2 | `ls -1 data \| wc -l` → 332; `ls -1d data/*/ \| wc -l` → 329 | §0.3, §8.1 |
| A3 | `grep -c "additive, never fatal" scripts/collect.py` → 28 | §0.4 |
| A4 | `grep -c freshness_sla config/dataset_registry.yml` → 0 | §0.5 FR-1 |
| A5 | pandas read of HON/NVDA across `data/{stocks,yahoo,baskets/ohlcv,massive_stock_day}` at 2025-09-25 and 2026-06-29 | §4.1 |
| A6 | pandas ratio scan, `data/stocks.close` vs `data/yahoo.close` over 170 co-covered names at `tol=1e-3` → 30 exceed; worst SPGI 5.700%, HON 5.172%, MO 1.496%, CMCSA 1.363%, BMY 1.129%, NKE 0.887%, USB 0.856%, MDLZ 0.838% | §4.2 |
| A7 | pandas ratio scan, HON `stocks/baskets` over 3,140 dates → ratio clusters at two levels (≈0.95350, ≈1.00282; 5 distinct values at 6-dp rounding), last disagreement 2026-06-26 | §4.2 |
| A8 | store file counts: stocks 229, yahoo 824, baskets/ohlcv 2,519, massive_stock_day 20,476 | §4.1 |
| A9 | tip scan over all 229 `data/stocks/*.parquet` → 7 distinct tips, 2026-06-18..2026-07-08, 220 at max | §3.1 |
| A10 | `python3 -c "json.load(open('data/massive_stock_day/_manifest.json'))"` → `n_processed_days 471`, `max_missing_run_weekdays 832`, anchor SPY `n_rows 454`, `max_gap_calendar_days 1165` | §3.5 |
| A11 | `git show HEAD:data/prophet/ledger_quarantine.json` (worktree, fresh `origin/main`) → schema `prophet.ledger_quarantine/v1`, count 11, rule and effect quoted verbatim, `KKR-BULL-20260318` close 2026-05-04 / origination 2026-07-14 | §6, §7.4 |
| A12 | `ls research/ \| grep -iE incident` → no match; `ls research/ \| grep -iE postmortem` → 7 files | §7.5 |
| A13 | `ls data/quality` → 11 audit JSONs | §8.2 |
| A14 | `ls -la lib/dataos/` → quality.py 15,792 B present, mtime 2026-08-12 13:50 | §1 |
| A15 | `wc -l tests/test_dataos_*.py` → 6 files, 1,729 lines (identity 417, nulls 253, price 174, quality 302, registry 347, temporal 236) | §1, §11 Q0 |
| A16 | `ls ops/*RUNBOOK.md \| wc -l` → 6 | §7.5 |
| A17 | `grep -n "point_in_time_corporate_actions" contracts/market_memory/spy_daily_price_source_observation.v1.schema.json` → `:232` (required), `:246` (`{"const": false}`) | §4.3 |

A1, A2, A5–A10, A13 were run against `/Users/chriswong/Documents/Cluade/Macro Dashboard` (the materialized
checkout). Per the caveat at the head of this document, their **content** results are usable and their
**dates** are not evidence of production staleness. A6/A7's ratio results are properties of two committed
frames relative to each other and do not depend on the checkout's recency. A11 was read through the
worktree's git objects specifically because the materialized checkout does not contain the file.

## Appendix B — corrections carried from the adversarial verifier

Recorded so a future session does not re-derive the wrong versions:

- Four US per-ticker daily stores, not three (five distinct readings for HON 2025-09-25, §4.1). "Adjusted" is
  a **(basis, as-of-vintage) pair**, never a boolean.
- `data/stocks` has no `open` in 229/229 files — but opens exist in `data/baskets/ohlcv` (2,519 names) and are
  synthesized by `engine/ohlc_reconstruct.py`. The defect is **undisclosed mixture**, not absence (§7.4).
  Reader count is 133, not 132.
- `lib/ticker_aliases.py` is the **narrowest** of at least ten identity surfaces, not the only one (§5, §7.4).
- No corporate-action **event** store exists, and the absence is declared:
  `"point_in_time_corporate_actions": false` (§4.3).
- `engine/canon.py` has **no** `atr` and **no** `realized_vol`, so ~23 apparent duplicates are canon **gaps**,
  not violations. Corrected counts: 103 files import canon (55 in production trees); 56 production files
  define an rsi/atr/realized_vol-named function; 6 do both; 5 of 8 sampled definers compute a genuinely
  different quantity. Not a quality-framework item; recorded so §3 is not written against the wrong premise.
- No spec clause targets `fillna(0)` as a class (§3.4).
- Redis is used nowhere (§12).
