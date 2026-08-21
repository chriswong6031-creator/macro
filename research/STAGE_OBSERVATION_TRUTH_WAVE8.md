# Wave 8 — Stage Analysis observation truth & industry history

Frozen build spec. Authored in the main loop; implementation is mechanical against
this document. Ships as two PRs (A then B).

**The one-line goal:** an old stock history may still be browseable as last-known
context, but it must not rank beside current names, alter today's market weather,
generate a "new" Stage transition, contaminate industry ranks, enter a current
machine candidate pool, or masquerade as fresh data.

---

## §0 ACCEPTANCE GATES (not done unless)

1. Stage **lifecycle age** (`fresh`) and **observation currentness** (`stage_current`)
   are separate fields with separate meanings, and `fresh=true, stage_current=false`
   is a legitimate, tested combination.
2. The hero shows the real Stage-week and source-tape clocks. The string
   `Priced <build date>` is gone.
3. One fresh ticker cannot certify a mixed-vintage population: current counts,
   Stage-2 share, Stage-4 share, market weather, fresh-Stage-2 headline, top
   Stage-2 board, Stage-3 rail, sector rollups, industry ranks/flows, the change
   feed, and the machine snapshot are all computed from **one completed Stage week**.
4. Stale rows remain browseable in the screener with visible provenance and **no
   current rank number**.
5. Machine Stage candidate pools cannot reacquire a stale row because the global
   snapshot date is current.
6. Industry ranks stop reporting `stale` merely because the wall clock advanced.
7. The Rank Heatmap no longer depends on the absent EquityDesk seed parquet and is
   powered by house-native accrual; with one real week it shows one column, not a
   blank "healthy" panel.
8. A missing Stage source artifact cannot leave yesterday's `site/stagedata/*.json`
   serving 200 OK as though it were today's.

## §0.1 FROZEN NON-GOALS

Do **not**: redesign Stage Analysis visually; change Weinstein thresholds,
hysteresis, the MA window, breakout logic, or the Stage taxonomy; redefine
`fresh`; recalibrate SGA score weights; promote Stage to trading authority; build
EU/Asia live OHLCV; re-import the EquityDesk historical corpus; create a generic
data-health platform; touch Prophet Stage scoring/fusion beyond preserving `fresh`
compatibility; or absorb the generic render-workflow failure-propagation problem.

---

## §1 THE CLOCK MODEL

Four distinct planes. They are never collapsed.

| Plane | Field | Meaning |
|---|---|---|
| Build clock | `built` | when the machine ran (UTC timestamp) |
| Display label | `asof` | **UNCHANGED** legacy label; still the build date |
| Daily observation | `stage_source_asof` (per row), `data_session` (contract) | newest daily bar behind the classification |
| **Weekly Stage** | `stage_week_end` (per row), `target_stage_week` (contract) | the completed W-FRI bar the stage was read from |

`stage_current` = `stage_week_end == target_stage_week`.

**`asof` keeps its current value and meaning in this wave.** New authoritative
fields are added alongside it. Deprecating `asof` is a later migration, after
consumers move.

### §1.1 `stage_week_end` — expose the value the classifier already has

`engine/weinstein_stage.py` already computes the completed-week grid via
`_w_fri_completed` (the single canonical completed-week rule). `weekly_frame()`
returns a frame whose index **is** the completed W-FRI Fridays. Expose the last one.

- In `classify()`, add to the returned dict:
  `"stage_week_end": wf.index[-1].date().isoformat()`
  (guard with try/except → `None`; never raise).
- In `_empty_result()`, add `"stage_week_end": None`.
- **Change nothing else in this file.** `fresh` (line ~536,
  `fresh = bool(stage == 2 and wis <= 10)`) keeps its exact meaning: Stage 2 and
  ≤10 completed weeks in that stage. Prophet/research consume it as a lifecycle
  concept. It is not a recency flag and must never be made to depend on wall clock.

`engine/stage_analysis.py::_classify_one()` passes `stage_week_end` straight
through from the classify result (no recomputation). A classify shim that does not
return it yields `None` → the row is **unknown**, never assumed current.

### §1.2 The target-week resolver

New helper in `engine/stage_analysis.py`:

```
_resolve_target_stage_week(dr, classified) -> (week: str|None, source: str)
```

- **SPY is required.** Reuse `classified.get("SPY")`, else classify
  `_load_bench_close(dr)` against itself (exactly the existing SPY path); take its
  `stage_week_end` as `spy_stage_week`. If SPY cannot be classified, return
  `(None, "unresolved")` — **do not guess a date, do not fall back to a wall-clock
  Friday, and do not invent a second Stage calendar.** The product then loses
  current cross-sectional authority (§2.4).
- Compute `population_modal_week` = the most common `stage_week_end` across the
  classified records (argmax; ties broken by taking the LATER week).
- **`target_stage_week = population_modal_week`.** The modal week is the only week
  that actually has a comparable cross-section, so it is the target in every case.
  SPY is required as a corroborating benchmark but **never overrides the mode**.
  - `target_week_source = "spy_benchmark"` — the two agree (the normal case).
  - `target_week_source = "population_mode_benchmark_ahead"` — SPY is later.
  - `target_week_source = "population_mode_benchmark_lagging"` — SPY is earlier.
- Any divergence adds the issue `benchmark_week_divergence` to the receipt and
  emits `::warning title=stage-target-week::` naming BOTH weeks.
- Record BOTH `spy_stage_week` and `population_modal_week` in the receipt (§2.5) so
  the resolution is fully auditable.

**Why the mode, and why NOT `min(spy, modal)`.** An earlier draft of this section
specified `min(spy_stage_week, population_modal_week)`. **That was wrong and is
superseded** — adversarial review (2026-08-20) proved the cap is two-sided and
inverts the population whenever the benchmark store is the one that freezes:

> `data/yahoo/SPY.parquet` freezes for a week while `data/baskets/ohlcv/` keeps
> advancing. SPY classifies to `2026-06-26`, 2,600 names classify to `2026-08-14`,
> and `min()` picks **`2026-06-26`**. `stage_current` is then `True` for the ~100
> genuinely stale June rows and `False` for the 2,600 current ones. Counts,
> weather, `top_stage2`, the change feed and `data_session` all recompute from the
> June rows, and `append_stage_snapshot` stamps those June rows `stage_current=True`
> into the machine snapshot — so the §4.2 consumer gate *passes* them. The wave's
> stated goal is achieved exactly in reverse, behind nothing louder than a
> coverage warning.

This is not hypothetical: §9 records that single-store freezes are the norm here
(183 frozen OHLCV files, a 110-file cluster, and a tripwire blind to all of it).
`data/yahoo/` can freeze the same way.

Working both directions through, the correct target is the **modal week in both**:
SPY ahead (benign Friday skew) → the population's week is the valid cross-section;
SPY behind (benchmark store broken) → the population's week is still the valid
cross-section. `min()` happened to be right in the first case only because
`modal < spy` there. So the mode is the rule, and SPY's real job is corroboration:
it is our independent read of what week the market is in, and a divergence in
either direction is a data-integrity alarm — which is why divergence is disclosed
loudly rather than silently resolved.

A stale benchmark degrades Mansfield RS (each name's RS is computed on its own
weekly grid with the benchmark reindexed and forward-filled,
`bw.reindex(wclose.index, method="ffill")`), but RS is one scoring input among
several and the stage classification itself — price versus the 30-week MA — does
not depend on SPY at all. Degrading one input with a loud warning is strictly
better than inverting the entire population. SPY remains REQUIRED: an unclassifiable
SPY still yields `(None, "unresolved")` and no current authority (§2.4), because
that failure also tells us the classifier or benchmark store is broken.

No threshold or day-count is involved, and both candidate weeks still come from
`_w_fri_completed`, so there remains exactly one Stage calendar.

Verified against the real completed-week machinery: tapes ending Thu Aug 20, Wed
Aug 19, Mon Aug 17 and Fri Aug 14 ALL resolve to completed week `2026-08-14`;
Jun 30 → `2026-06-26`; Jul 10 → `2026-07-10`; Aug 13 → `2026-08-07`; Fri Aug 21 →
`2026-08-21` (the skew case the cap exists for).

This resolver must run **before** the population is partitioned. Restructure
`build_context_feed` so the SPY classification happens once, above the record
loop, and the existing `spy_stage` / `spy_weeks` market fields reuse that same
result rather than classifying SPY a second time.

**Why a completed-week test and not a day threshold:** tickers whose raw daily tape
ends on different weekdays legitimately describe the same completed Friday. A tape
through Wed Aug 19 and a tape through Mon Aug 17 both yield completed week
Aug 14 — both current. A tape ending Jun 30 yields Jun 26 — stale, regardless of
how many weeks it has been in Stage 2. Currentness is week equality, never a
day-count.

---

## §2 THE CURRENT POPULATION

### §2.1 Partition

After the per-name records are assembled (classified, not too-young), stamp each
record with `stage_week_end` and a tri-valued `stage_current`:

- `True` — target known, row week known, equal → **current**
- `False` — target known, row week known, unequal → **stale**
- `None` — either unknown → **unknown**

Then split into `current_recs` / `stale_recs` / `unknown_recs`.

### §2.2 Only `current_recs` may carry current authority

Compute **from `current_recs` only**: Stage 1/2/3/4 headline counts; `stage2_fresh`;
`pct_stage2`; `pct_stage4`; `market.weather`; `top_stage2`; `warnings_stage3`;
`sectors`; the industry rank/flow frame; the change feed; the machine snapshot;
`roster`; and `data_session`.

`recs` (the full list, all three buckets) still feeds the screener and both stage
boards, so stale names stay browseable.

### §2.3 Scoring and ranking admission

- `slope_pop` (the cross-sectional slope percentile population) is built from
  **current Stage-2 records only**. A stale row must not distort the current
  cross-section it is not a member of.
- `sga_score` is computed for current records. **Stale and unknown records get
  `sga_score = None`** — a stale observation has no current-ranking authority, so
  it carries no current rank number. This is the admission boundary; it is not a
  retune. Weights are untouched.
- Inside the admitted current population the existing Stage-age component is
  unchanged.
- `_compute_sga_score`: rename the component **description only** — the docstring
  line `freshness 25` becomes `early-stage position 25`, and `W_FRESHNESS` gains a
  comment stating it scores Stage-2 earliness, not data freshness. Do not rename
  the constant, do not change any weight.

Ordering: because scoring now depends on the partition, `build_context_feed` must
build records first, resolve the target week, partition, build `slope_pop`, then
score. Keep `build_context_feed`'s public contract (returns the contract dict).

### §2.4 When the target week cannot be established

`target_stage_week is None` → every row is unknown, `current_recs` is empty, and:

- `population.status = "no_target_week"`.
- Every value in `counts` is **`null`, not `0`**. Zero is a measurement; null is
  the absence of one. The template already renders `'—'` for null counts.
- `market.weather` is `null` (the template's `{% else %}` branch fires).
- **The template's `{% else %}` copy must NOT say "Warming up" / "The first stage
  read runs tonight" when `population.status` is `no_target_week` or
  `unavailable`.** A mature-lane failure is never described as a first run. Add an
  explicit unavailable state: EN `Stage read unavailable` /
  `We could not establish tonight's completed stage week, so the market read is
  withheld rather than shown stale.` ZH `阶段判定暂不可用` /
  `今晚无法确定已完成的阶段周，因此暂不显示市场判读，而不是给出过时数据。`
  The genuine first-run warm-up copy stays for the case where there is no artifact
  at all.

### §2.5 The population receipt

Add to the contract (`stage_context.v1`), additively:

```json
"target_stage_week": "2026-08-14",
"target_week_source": "spy_benchmark",
"stage_week_end": "2026-08-14",
"data_session": "<max stage_source_asof over CURRENT recs, else null>",
"population": {
  "status": "ready" | "warn" | "no_target_week",
  "target_stage_week": "2026-08-14",
  "target_week_source": "spy_benchmark",
  "current": 2610, "stale": 112, "unknown": 19, "total": 2741,
  "current_coverage_pct": 95.2,
  "data_session": "2026-08-19",
  "data_session_all": "2026-08-19",
  "week_histogram": [{"week": "2026-08-14", "n": 2610}, {"week": "2026-06-26", "n": 41}],
  "issues": []
}
```

- `week_histogram`: the top 8 distinct `stage_week_end` values by count. This is the
  alarm that makes a target-week/population disagreement visible immediately
  instead of silently blacking out the page.
- `status = "warn"` with issue `current_coverage_below_floor` when
  `current_coverage_pct < 60`. Warn loudly (`::warning title=stage-population::`),
  do **not** suppress the render — an honest small population plus a loud receipt
  beats a fabricated one.
- `data_session` moves to max-over-current (the tape behind the comparable
  cross-section). `data_session_all` preserves the old max-over-everything for
  audit. In practice these are equal, because the freshest row is by definition
  current.

The hero renders, in place of `Priced <asof>`:
EN `Stage week ended <target_stage_week> · source tape through <data_session>`
ZH `阶段周截至 <target_stage_week> · 数据行情至 <data_session>`
Both the Jinja block (`templates/stage_analysis.html.j2` line ~654) and the JS
provenance string (line ~1375) must change. `built` may still appear as technical
provenance, but **never** labelled "Priced".

Also render the coverage receipt in plain words near the hero, e.g.
EN `2,610 current · 112 stale · 19 unknown` / ZH `2,610 当前 · 112 过时 · 19 未知`.

---

## §3 SCREENER / BOARD PROVENANCE

`_screener_row()` currently strips the provenance needed to detect a stale
observation: the client receives `source: "live"` and `fresh: true` and nothing
else. `source="live"` means "our live classifier rather than the EquityDesk seed";
it does **not** mean current observation. **Do not rename `source` to `current` —
they are different facts.**

Add three fields to `_screener_row()`:

```
"stage_week_end":    r.get("stage_week_end"),
"stage_source_asof": r.get("stage_source_asof"),
"stage_current":     r.get("stage_current"),
```

`rating` already derives from `sga_score`, so it is `null` for stale rows — that is
the intended "no current rank number".

- Seed rows from `_seed_screener_rows()` (EU/ASIA) get
  `stage_week_end: null, stage_current: null`. They are display inventory and never
  enter current authority.
- `_stage_board_contract()` sort key gains `x.get("stage_current") is not True`
  immediately after the `source != "live"` term, so current rows sort first.
- `_stage_board_contract()` gains the same top-level clock fields and the
  `population` block.
- `_top_row()` gains `stage_week_end` and `stage_current` (top rows are always
  current, but the field must travel for the forward ledger and for tests).

Client: a row with `stage_current === false` renders
EN `Last Stage read <stage_week_end> · stale` / ZH `最近阶段判定 <stage_week_end> · 已过时`
and shows no rating number. Stale rows stay filterable/browseable.

**No current row may depend on `source === "live"` for freshness.**

---

## §4 MACHINE SNAPSHOT HARDENING

The defect: `append_stage_snapshot` stamps a **global** `as_of_date = asof` (the
build date) on every row, and `attention_source.stage2_leaders()` freshness-checks
only that global date. A June observation rewritten into an Aug-20 snapshot
therefore looks fresh to a downstream candidate pool. Stage is display-tier, but a
machine candidate pool reading it is a machine-integrity defect.

### §4.1 Producer — `append_stage_snapshot(recs, asof, root, *, target_stage_week=None)`

The "latest live snapshot" is current-state inventory, so it carries only current
rows.

- Admit **only** rows with `stage_current is True`.
- Add per-row columns `stage_week_end` and `stage_current`. Keep `stage_date`
  (= `stage_source_asof`) and `as_of_date` (snapshot/build provenance) as they are.
- Disclose exclusions:
  `::warning title=stage-snapshot::<n> stale + <m> unknown row(s) excluded from the
  <week> snapshot`.
- If `target_stage_week is None`, do **not** advance; warn and return 0. The prior
  snapshot stands.
- The `SNAPSHOT_MIN_ROWS` floor now applies to admitted rows.
- Retention (`SNAPSHOT_KEEP = 2`) and same-`as_of` idempotent replace are unchanged.

### §4.2 Consumers — `engine/marketing/attention_source.py`

These must fail closed **regardless of what the producer does**.

`_read_stage()` must request only columns the parquet actually has (read the
schema first and intersect; `pd.read_parquet(columns=…)` raises on a missing
column). Request `_STAGE_COLS` plus `stage_date`, `stage_week_end`, `stage_current`.

`stage2_leaders()` — after selecting the latest `as_of_date` snapshot, apply a
per-row currentness gate, in this precedence:
1. `stage_current` column present → require `== True`.
2. else `stage_week_end` present → require `== max(stage_week_end)` within the
   selected snapshot.
3. else `stage_date` present → require that row's own date is not more than
   `budget` sessions behind `ref` (the same session budget the global gate uses).
4. else → no per-row provenance at all → `_warn(...)` and return `[]` (**fail
   closed**).

If the gate admits zero rows, warn naming the reason rather than returning a silent
empty list.

`stage_transitions()` — build the snapshot list from distinct `stage_week_end`
values when that column exists (else `as_of_date`), and require the two compared
groups to be **different Stage weeks**. Two snapshots from the same Stage week are
the same weekly read and can only manufacture phantom transitions. Apply the same
per-row currentness gate to the current side.

**Do not change pool rankings, ordering, or quotas beyond removing invalid
observations.**

---

## §5 CHANGE FEED — key on the Stage week, not the wall clock

`_build_changes_block` currently keys same-day idempotence on `asof`, a clock read.
Rolling the machine date therefore rolls the diff base even though the Stage week —
and hence the stage read — has not moved.

Re-key it on `target_stage_week`:

- Base selection: if the stored `target_stage_week` differs from today's, the base
  is the stored `_current_by_key` (the week advanced → genuine transitions may
  fire). If it is the same week, the base is the stored `prev_state.by_key`, frozen
  (a same-week rerun preserves the change set rather than wiping or duplicating it).
- `target_stage_week is None` → empty changes, preserve `prev_state`, no authority.
- `prev_state` gains `stage_week`; keep `asof` in it for back-compat.
- `new_by_key` is built from `current_recs` only.
- `_current_by_key` is a **carry-forward union**: prior `_current_by_key` overlaid
  with today's current rows. Without this, a name that goes stale drops out of the
  key map and then fires a spurious `entered_stage2` "first sighting" when it
  returns. Bounded by universe size.

`counts.new_today` continues to count `entered_stage2` + `breakout`, now stable
across a wall-clock roll inside one Stage week.

---

## §6 INDUSTRY — false staleness and honest provenance (PR B)

### §6.1 The false-stale warning

`industry_ranks.json` is non-vacuous (2,741 input rows, 1,836 eligible, 74
industries, 67% taxonomy coverage, 100% RS-change coverage) yet reports
`status: warn` solely because `coverage_snapshot` compares `source_asof`
(2026-08-19, the settled daily tape) against `expected_asof` (2026-08-20, the
builder's wall clock). The classifier is weekly-native; a current Stage week must
not be downgraded because the UTC calendar rolled forward.

`coverage_snapshot(stage_frame, expected_asof, output_rows, *, expected_stage_week=None)`:

- Compute `source_stage_week` = max of the frame's `stage_week_end`.
- When both `expected_stage_week` and `source_stage_week` exist, judge freshness on
  the **Stage-week plane** by equality, and report `freshness.plane = "stage_week"`.
- Only when the week plane is unavailable does the existing daily comparison apply,
  with `freshness.plane = "daily"`.
- The daily values stay in the payload for audit (`expected_asof`, `source_asof`)
  but **must not generate an issue when the week plane answered**.
- `freshness` gains `expected_stage_week`, `source_stage_week`, `plane`.

`stage_industry.build()` and `stage_flows.build()` take `target_stage_week` and
pass it through.

### §6.2 Mixed vintages excluded before aggregation

`_build_live_industry_surfaces()` must:
- call `prepare_live_frame()` on **all** records, so every row (including stale
  ones) still gets its reference-taxonomy identity for the screener's industry
  column;
- then pass a frame filtered to **current tickers only** into
  `stage_industry.build()`, `stage_flows.build()`, and
  `name_industry_percentiles()`.

Stale rows therefore get `industry_percentile = null` — correct, they have no
current rank.

### §6.3 Provenance text (Defect 7)

The metadata still claims the method is "our aggregation of THEIR Mansfield RS +
rate-of-change". The shipping path now builds the industry frame from our own
OHLCV classifier records. Separate the two facts; **do not delete the calibration
receipt** — correct what it claims to calibrate.

```json
"method": {
  "live": "House-native: Mansfield RS and 4-week RS change computed from our own OHLCV via the Weinstein stage classifier, grouped by reference GICS taxonomy. Ranks are per-region z-scores of the blended score.",
  "plane": "completed W-FRI stage week"
},
"calibration": {
  "target": "stageanalysis_industry_ranks_weekly (EquityDesk)",
  "yardstick": "Historical comparison only — the EquityDesk dataset is NOT an input to the shipping calculation.",
  "note": "rank rho ~0.4 (USA .36 / EUR .49 / ASIA .43); quartile-bucket agreement ~35% — measured, ordinal only"
}
```

Keep the `calibration.target` key for back-compat. Keep `all_region_is_concat` and
`all_region_note` untouched.

---

## §7 INDUSTRY RANK HISTORY — house-native accrual (PR B)

### §7.1 Why a new store

The heatmap is structurally dead: `regions: []`, `n_regions: 0`. Its engine reads
`data/stage_analysis/backfill/industry_ranks.parquet`, a one-shot proprietary
EquityDesk export that is **absent** from the committed backfill (only
`earnings_seed.parquet` and `equitydesk_overview.parquet` are there).

Ruled out as sources:
- Re-importing the competitor seed as an ongoing production dependency — forbidden.
- The Stage engine snapshot — retains only the newest `SNAPSHOT_KEEP = 2` engine
  snapshots.
- The forward ledger — contains only fresh Stage-2 names.

Neither is a complete historical industry-rank tape. So: **one narrow house-native
derived history inside the existing Stage subsystem.** This is not a second
lifecycle or control plane; it is the time-series backing for an existing
first-class Stage surface.

### §7.2 Serialization — follow `append_forward_ledger`

House precedent is `engine/stage_analysis.py::append_forward_ledger` writing
`data/stage_analysis/forward_ledger.jsonl`: JSONL, keyed on a **data-plane** date
and never a clock read, deduped, fail-open, disclosing skips via `::warning`.

New file: `data/stage_analysis/industry_rank_history.jsonl`. One record per
`(stage_week_end, region, industry_id)`:

```json
{"stage_week_end":"2026-08-14","region":"USA","industry_id":"4510","industry":"Software",
 "rank":1,"score":1.83,"bucket":"top","n":42,
 "built":"2026-08-20T08:08:01Z","source":"stage_industry.live"}
```

### §7.3 Writer — `append_industry_rank_history(all_ranks, stage_week_end, coverage, root)`

Sole writer is nightly Stage, called from `stage_industry.build()` after ranks are
computed. It advances **only** when all of:

- `stage_week_end` is not `None`;
- `coverage["non_vacuous"] is True`;
- `coverage["status"] == "ready"` and no currentness issue is present.

Otherwise: skip and `::warning title=industry-rank-history::` naming exactly why.
**Never advance from a wall-clock date. No synthetic backfill. No seed re-import.**

Idempotence: read all records, drop every record whose `stage_week_end` **equals the
target week**, append the freshly computed set, rewrite atomically (temp +
`os.replace`). A same-week rebuild therefore **replaces** that week's point rather
than creating a duplicate weekly point — which is also the deterministic correction
path when a corrected OHLCV file changes a same-week result.

**Past weeks are immutable.** Only the record set for `target_stage_week` may ever
be dropped or rewritten. A completed week other than the target is never touched,
which preserves the house keep-FIRST discipline
(`engine/sector_central_grader.py::append_central_log`,
`engine/track_record.py`: "a past day's stamped call is never rewritten") while
still allowing the same-week idempotence a nightly rerun needs. The write is a
whole-file rewrite only because the file is small; it is **not** a licence to
re-stamp history.

Record fields map 1:1 onto what `_rank_region()` already returns — `industry_id`,
`industry_name`, `region`, `n`, `score`, `rank`, `bucket`, `industry_percentile` —
so nothing is recomputed for the history; it persists exactly what shipped.

Retention: keep the newest **30** distinct `stage_week_end` values (26-week view
plus headroom). Max size ≈ 30 × 74 × 3 ≈ 6.7k lines.

**Historical correction out of scope:** silently rewriting a *previously completed*
week when a late correction would materially change stored history is NOT
implemented here. Record it for Sol rather than inventing a general correction
subsystem in this PR.

### §7.4 Reader

`industry_heatmap()` reads `industry_rank_history.jsonl` instead of the seed
parquet; delete the `_ranks_seed_path` dependency. Grid columns = distinct
`stage_week_end` descending, capped at `_HEATMAP_WEEKS = 26`. Row shape, ordering
(most-recent week's rank, strongest first) and `max_rows` are unchanged.

`build_industry_heatmap()` contract gains:

```json
"source": "house-native stage industry rank history (data/stage_analysis/industry_rank_history.jsonl)",
"history": {"status":"unavailable"|"accruing"|"ready",
            "weeks_available": 1, "weeks_target": 26,
            "first_week": "2026-08-14", "latest_week": "2026-08-14"}
```

`unavailable` = 0 weeks; `accruing` = 1–25; `ready` = 26+.

Client: `accruing` renders
EN `Rank history accruing from <first_week> — <n> of 26 weeks` /
ZH `排名历史自 <first_week> 起累积 —— 26 周中的第 <n> 周`,
`unavailable` renders an honest unavailable state.
**Never a blank panel that reads as healthy, and never a fabricated 26 weeks.**
On first deployment the truthful render is one real column.

---

## §8 PUBLICATION INTEGRITY (PR B)

`scripts/build_stage_analysis_page.py::_copy_stagedata()` (lines 95–112) does
`if not src.exists(): log.info(...); continue` — it never revokes the previous
public destination. A producer that stops emitting `data/stage_analysis/foo.json`
leaves yesterday's `site/stagedata/foo.json` in place; the client fetch returns
200, so the surface never enters its unavailable state. That directly contradicts
the module docstring's promise (lines 14–16) of "an explicit ingestion-health
state, never a misleading scheduled 'warm-up'".

Required behavior:

- **Source present and valid** → copy (atomically: temp + `os.replace`).
- **Source absent** → remove the public destination and `::warning
  title=stagedata-revoked::<name> source absent — public copy revoked`. A missing
  current source must never preserve the old destination as though it were current.
- **Source present but carrying explicit stale provenance** (`status` of `stale`,
  or `stage_current is false`, or `population.status == "no_target_week"`) → copy
  it, and let the client render it as stale. Valid last-known data may be retained
  **only** when the artifact itself discloses that it is stale.
- Validation stays narrow and per-artifact: the file parses as JSON and carries a
  `schema` key. **Do not invent a global health database.**

Return a small report `(copied, revoked, stale)` and log it.

Client: an artifact that 404s already lands in the existing `.catch()` branches;
those must render a mature-lane unavailable state, **not** "warming up" copy.

**Concrete instance found while testing PR A (2026-08-20).** The screener table's
client-side empty state in `templates/stage_analysis.html.j2` still reads:

> `Warming up` / `The screener table is generated tonight. Check back after the
> first stage run.` (ZH `正在预热` / `选股器表格今晚生成。首次阶段运行后再来查看。`)

That fires whenever `stagedata/screener.json` fails to load — including on a mature
lane whose artifact was revoked by §8 — so a production failure reads as a first
run. PR A fixed the equivalent copy in the HERO (§2.4) and its render test is
deliberately scoped to the hero so it does not mask this one. Sweep the remaining
per-surface `.catch()` empty states (screener, boards, industry, earnings, altdata,
research) and give each a mature-lane unavailable state distinct from genuine
first-run copy.

---

## §9 PRICE-SOURCE PRECEDENCE — **VOIDED BY THE PRODUCTION PROBE. DO NOT CHANGE `_load_prices`.**

The handoff gated a loader change on a probe showing "preferred store stale AND
fallback store current". **The probe falsified that hypothesis.** Do not touch
`_load_prices`, do not change store precedence, and do not add `stage_price_source`
— there is only ever one store, so the field would carry no information.

Measured (all 8 suspects + TMHC + 3 controls; `_load_prices` invoked for real, its
returned series byte-compared against both parquets):

- `data/stocks/<TK>.parquet` **does not exist** for any of the 12. The `stocks`
  rung is never reached; `baskets/ohlcv` satisfies `p.exists()` and returns.
- Repo-wide: `stocks` holds 242 files vs 2,782 in `baskets/ohlcv`, and across the
  241 tickers present in both, **0** cases have `stocks` fresher than `ohlcv`.
- The two stores are the *same adjusted basis* anyway (median close ratio exactly
  1.000000 for 232/241; Pearson ≥0.9999982 for every name), so the "don't splice
  adjusted with unadjusted" risk is real but moot.

**The actual root cause is fetch-universe drift, and it is UPSTREAM of Stage:**

- `build_universe()` does `for p in ohlcv_dir.glob("*.parquet"): _add(p.stem, "ohlcv")`
  — every file ever written, forever. It never forgets a ticker.
- `scripts/fetch_basket_ohlcv.py::_resolve_universe()` maintains only
  `membership ∪ finviz(idx_ndx, idx_rut)` = 2,603 names, and the finviz screener
  JSONs are re-pulled nightly, so index reconstitution silently shrinks the
  maintained set.
- Separation is near-perfect: **2,599/2,599 fresh files are inside the fetch
  universe; 179 of 183 stale files are outside it.** The 2026-07-10 cluster of 110
  files is a reconstitution drop-out, far too large to be simultaneous delistings.
- Corroborated genuine tape ends: LPRO and TMHC carry `Delistings` stage
  `"completed"`; SILA carries a high-confidence Going-Private classification.
- The existing tripwire is blind to all of it: `check_membership_staleness()`
  censuses only the 702 active membership names, so it reports `n_stale: 1` (EA)
  while 179 files sit frozen. **That blindness is why this reached production.**

Wave 8 is the **containment**, not the cure: the observation-truth boundary stops
those frozen names from carrying current authority. Repairing the collector
universe (and the census's blind spot) is a separate wave — out of scope here,
flagged in the continuation report.

### §9.1 THE CURE SHIPPED (2026-08-20) — and three §9 claims did not survive re-checking

The upstream repair is `DEC:BASKET-OHLCV-STORE-SELF-MAINTAINS`: the deep store now
self-maintains (`fetch_basket_ohlcv --store`, wired into the nightly), so leaving an
index can no longer freeze a file, and the only lawful exit is a resolved row in
`config/delisted_symbols.yml`. The census was widened to judge the whole store under
three dispositions (`stale` / `unsponsored` / `retired`). Wave 8's containment is
UNCHANGED and still load-bearing.

Every §9 measurement above reproduced exactly on 2026-08-20 (2,782 files, 183 stale,
179 orphans, the 110-file 2026-07-10 cluster, 2,599/2,599 and 179/183 separation) —
plus two that §9 did not state: **zero** orphans are fresh, and **zero** fetch-universe
names lack a file. A live vendor probe then settled the reconstitution hypothesis:
10 of 10 sampled names from the 07-10 cluster (ARWR/AXSM/BBIO/BE/AAOI/ALDX/BARK/BOOM/
ACNT/AHR) returned a current tape while frozen 29 sessions back, and a real fetch
advanced ARWR/AXSM/BBIO to 2026-08-20.

Three claims in the bullets above are **wrong** and are corrected here rather than
edited away, because each one would mislead the next reader in the same direction —
toward believing an orphan is dead when it is merely unrequested:

1. **TMHC does not carry `Delistings` "completed"** — the string `TMHC` does not appear
   anywhere in `data/special_situations/context/latest.json`. (Its tape *is* genuinely
   over: the vendor returns nothing. The conclusion was right, the cited receipt is not.)
2. **SILA has no "high-confidence" classification** — the key `SILA|Going-Private`
   exists with `stage: ""`. An empty stage is not a confidence level.
3. **AVB is not "one session behind, ordinary jitter"** (stated in the handoff's
   four-name breakdown). AVB was acquired 2026-08-17 and already had a *well-formed exit
   row in the ledger*. Its 1-session lag is the vendor flat-forwarding a dead symbol as
   0-volume repeats past its real 2026-08-14 close. Nothing read that ledger, so AVB was
   days from becoming BLD's permanent unexplained red line a second time.

The generalisable lesson from (1) and (2): `data/special_situations/context/latest.json`
is `is_context_only: true` and carries the disclaimer "never a signal" — it is a HINT
source, and only ~13 of the 179 orphans have even a hint of an exit. From (3): freshness
alone cannot classify a name, in either direction. Both are why the shipped census
surfaces a triage QUEUE and never infers a retirement.

---

## §10 REQUIRED TESTS

Fixed clocks and fixture dates throughout. No wall-clock dependence.

**Week resolution**
- Tape ends Aug 19, last completed week Aug 14 → current vs target Aug 14.
- Tape ends Aug 17 (Monday), also classified through Aug 14 → **still current**.
- Tape ends Jun 30, completed week Jun 26 → stale vs target Aug 14.
- Assert currentness is decided by completed-week equality, **not** by a count of
  calendar days.

**Population** — with rows AAPL current Stage 2, MSFT current Stage 4, SILA stale
Stage 2: current total = 2; stale total = 1; current Stage-2 count = 1 (not 2);
the Stage-2 percentage denominator = 2; SILA is absent from `top_stage2`; SILA is
still present and browseable with stale provenance.

**Lifecycle vs currentness** — assert `fresh=true, stage_current=false` is
producible and preserved. Assert Stage-age points still work for admitted current
rows, and that a stale row cannot obtain a current rank via those points
(`rating is None`).

**Screener contract** — `stage_week_end`, `stage_source_asof`, `stage_current`
present on live rows; no current row derives freshness from `source == "live"`.

**Change feed** — run Monday and Tuesday with an identical target Stage week and a
changed wall-clock `asof`: no duplicate `entered_stage2`/"new today" event appears
solely because the machine date rolled. Then advance the target week and assert
genuine transitions do fire.

**Snapshot / machine** — a stale per-row entry cannot enter current Stage marketing
candidates under a fresh global snapshot date; `stage2_leaders` fails closed on an
old per-row Stage week (including the legacy no-`stage_week_end` parquet, via
`stage_date`); `stage_transitions` compares only different Stage weeks.

**Industry** — an Aug-20 build with an Aug-19 daily source and target completed
week Aug 14 is **not** reported stale; mixed stale rows are excluded before
aggregation; the calibration block distinguishes live method from historical
yardstick.

**Heatmap** — no house history → explicit accruing/unavailable state, not a healthy
empty panel; first valid completed week → one column; same-week rerun → still one
column (no duplicate); next completed week → two columns; a failed/empty/
currentness-invalid industry run → history does **not** advance; the history key is
the Stage week, never the build date.

**Publication** — an existing `site/stagedata/foo.json` plus a missing source on a
new build → the stale destination cannot survive as a normal current artifact; an
explicitly-stale source remains usable only with stale treatment; a current valid
source copies normally.

---

## §11 DATA / NULL / CORRECTION RULES

Everything here is deterministic. **No LLM** determines currentness, source choice,
Stage week, ranking admission, history advancement, or failure state.

- No provable `stage_week_end` → `stage_current` unknown, never assumed current.
- No benchmark target week → no current cross-sectional authority (§2.4).
- A missing current source is **not zero**.
- A stale row is **not dropped from history** merely because it is stale.
- A stale row **is excluded from current statistics**.
- Zero Stage-2 names is legitimate **only** when a successfully observed current
  population genuinely has zero.
- A corrected OHLCV file may change a same-week Stage result; the same-week rebuild
  replaces that weekly point deterministically (§7.3) and never duplicates it.

---

## §12 CONSUMER SAFETY — audited before any field is added

The `asof` field is **not** being changed in this wave, but the audit was run first
because the handoff gates the change on it.

**Readers of `asof` on a Stage contract** — all plain `.get("asof")` lookups with no
schema validation and no key-set iteration, so all four are unaffected by new
sibling keys:
`engine/neuralweb/world_state.py:3754`, `engine/neuralweb/ask_brain.py:2040`,
`engine/neuralweb/mastermind_context.py:1365`,
`scripts/build_stage_analysis_page.py:78-92` (passes the whole dict to the template).

**Readers of `data_session`** — exactly one:
`engine/stage_analysis.py:1045`, rung (b) of `append_forward_ledger`'s session
ladder. Rung (a) (`row.stage_source_asof`) is preferred and, because `top_stage2`
is now current-only, always resolves — so narrowing `data_session` to the current
population cannot change a ledger row's date. **Side effect, and it is the correct
one:** the forward ledger stops recording stale fresh-Stage-2 names, which matters
because it is the engine's only point-in-time record of which names were fresh
Stage 2 on a session and is read date-keyed by the Prophet US "stage-ran shelf"
study.

**The `fresh` contract must not move.** `engine/prophet_stage_shadow.py:501,538,569,921`
consumes it (`res.get("fresh", False)`, `fresh_stage2 = [r for r in stage2 if
r.get("fresh")]`) straight off the classifier's row output, and
`world_state.py:3734` / `ask_brain.py` / `mastermind_context.py:1380-1390` read it
off `top_stage2`. Note `engine/marketing/radar_internal.py::_feed_stage` runs its
**own** `as_of_date` staleness gate and never reads the `fresh` boolean — two
distinct mechanisms that must not be conflated.

**Tests pin the contract key set additively.** `tests/test_stage_analysis.py:24-25`
declares `_ADDITIVE_SINCE_FIXTURE = {"data_session"}` and
`_ADDITIVE_TOP_ROW_SINCE_FIXTURE = {"stage_source_asof"}`, and lines 177-196 assert
`set(contract.keys()) - _ADDITIVE_SINCE_FIXTURE == set(fixture.keys())`. **Every new
top-level key in §2.5 must be added to `_ADDITIVE_SINCE_FIXTURE`, and every new
`top_stage2` row key to `_ADDITIVE_TOP_ROW_SINCE_FIXTURE`**, or these tests fail.
That is the house mechanism for additive fields — use it; do not regenerate the
fixtures.

**A second writer exists for the overview parquet.**
`scripts/import_equitydesk_backfill.py:563-566` writes it as the one-shot committed
yardstick, outside `engine/stage_analysis.py`. New snapshot columns must therefore
be tolerant of seed rows that lack them (they concat to NaN — fine); do not make
any reader require the new columns (§4.2's precedence ladder already handles this).

**Deliberately excluded consumer.** `scripts/build_portfolio_ctx.py:208-212` reads
`site/stagedata/screener.json` filtered to `region=="USA"` and `source=="live"`,
which now also matches stale rows. Its behavior is **unchanged from today** (it
already ingests those rows, merely unlabelled), so this is status quo rather than a
regression — and the handoff forbids modifying Portfolio/Watchlist in this wave.
After this PR the row-level `stage_current` flag exists for a later wave to gate on.
Recorded in the continuation report as a known remaining defect.
