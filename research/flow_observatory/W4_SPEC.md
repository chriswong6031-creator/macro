# W4 frozen spec — universe, official/curated lenses, coverage, concentration, contribution

`child: macro-flow-observatory-v2-w4-universe-aggregation-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §9 (sector/theme boundary), §4 (contract), packet W4`
`design authority: this spec. Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. Users can tell at a glance whether they are viewing overlapping curated themes or the
   official (non-overlapping) sector lens; the official lens NEVER borrows curated
   membership and NEVER claims history it does not have.
2. Every group statistic declares its denominator and coverage; below the calibrated
   coverage floor a group renders `insufficient coverage` — never a survivor-biased read.
3. Concentration is first-class: top-1/top-3 share and a without-top-1 sensitivity
   direction per group; contributors reconcile to the aggregate within tolerance
   (tested).
4. Theme overlap is disclosed (theme-level overlap count; member-level "in N themes" in
   the drilldown).
5. Evidence matrix for the changed surfaces: dark/light × EN/ZH × 1440 + one 390 crop
   per theme; zero console errors; no horizontal scroll; both themes judged as designs.
6. Targeted suites green; contract-delta 0 introduced (new test file wired both halves
   in the same commit); canonical rebuild committed; PR DRAFT/unlabeled; tree clean.

## 1. Official lens spike (bounded, FIRST, ≤ ~30 min of effort)

Determine whether akshare exposes Shenwan L1 constituent membership keylessly TODAY
(candidate endpoints to try, in order: `ak.sw_index_cons`, `ak.index_component_sw`,
`ak.sw_index_first_info`-adjacent constituent calls, or the current documented SW
constituent API — read the installed akshare's own docs/signatures). akshare is a repo
dependency of collectors/china_sectors.py; if it is not importable in this checkout,
`pip install --user akshare` is authorized (same dependency the collectors already use).
Record the spike outcome (endpoint name, sample shape, row count for 2 L1 codes) in the
PR body.

- **Spike SUCCEEDS** → implement §2A.
- **Spike FAILS** (no keyless endpoint, import impossible, or shape unusable) →
  implement §2B and record the exact gap in the PR body + masterplan §9 note (one-line
  edit permitted).

## 2A. Official lens (spike success path)

- Extend `collectors/china_sectors.py` (the existing official-sector owner — never a
  new collector family) with `collect_sw_membership()` → 
  `data/china_sectors/membership.parquet`, interval pattern:
  `ticker (.SS/.SZ normalized) · l1_code · l1_name · start_date · end_date(null=current)`.
  Seeded from the current snapshot on first run; forward accrual (a later run diffs
  membership: departures get end_date, arrivals get new rows). Wire collection into the
  same lane step where china_sectors already collects. Commit the seed parquet.
- `engine/flow_observatory/groups.py` (new): `aggregate_lens(kmap, membership, kind)`
  computing per-group equal-weight mean of member 主力 demeaned rates (same math as the
  theme rollup — reuse engine.flow_velocity helpers, no second velocity engine),
  emitting the same per-row contract as themes (abs/rel/quadrant/rank/coverage) plus
  `group_kind: "official_sector"`, `overlap_allowed: false`, `membership_as_of`.
- Lens label (pinned): EN "Official sectors (Shenwan L1) — current membership; history
  accrues from {seed_date}" ZH "官方行业（申万一级）——当前成分；历史自{seed_date}起累积".
  No historical replay of official-sector aggregates before real accrued membership
  covers the window (the ledger records official-sector observations from W4 forward
  like any entity — entity_kind "sector").
- Validation: no ticker appears in two L1 codes at one effective date (test; if the
  source itself violates this, the affected ticker is excluded + counted in
  excluded/missing, never silently double-counted).

## 2B. Official lens (spike failure path)

Designed-unavailable official tab: EN "Official sector lens unavailable — no lawful
keyless constituent source; showing curated themes only." ZH
"官方行业视图暂不可用——缺少合规的成分数据源；仅显示精选主题。" plus a LENS receipt naming
the gap. No fabrication, no relabeled baskets. All §3-§5 items still ship for themes.

## 3. Curated-theme overlap + coverage (both paths)

- Theme row gains `overlap_count` (members shared with ≥1 other theme) and the board
  sub-line keeps "curated overlapping themes — not official sectors".
- Member drilldown rows gain "in {n} themes / 属{n}个主题" chips when n ≥ 2.
- Coverage: per group `n_members`, `n_covered` (members present+scored in the kinetics
  map), `coverage_pct`; excluded/missing members listed in the drilldown (name + reason:
  unscored/missing).
- **Coverage floor calibration (REQUIRED receipt)**: measure the coverage_pct
  distribution across all groups on real data; set the floor at the largest value that
  keeps every currently-healthy group eligible while catching the degenerate tail
  (starting hypothesis 60%; move it only with the measurement, state it in the PR
  body). Below floor → row state `insufficient coverage / 覆盖不足` (quadrant
  neutral_or_unknown, no rank), never a partial statistic.

## 4. Concentration + contribution (both paths, themes + official sectors)

- Per group: top-3 positive and top-3 negative contributors (member, signed demeaned
  rate contribution = member_rel / n_covered); `top1_share`/`top3_share` = |top-k
  contributions| / Σ|contributions| (gross); `without_top1_direction`: recompute the
  group rel mean excluding the largest |contribution| member → same | flips | unknown.
- Reconciliation law (tested): Σ contributions == group rel value within 1e-6.
- Drilldown UI line (pinned): EN "top name = {p}% of gross flow · without it: {same
  direction/flips}" ZH "最大贡献个股占总流量{p}% · 剔除后：{方向不变/方向反转}".
  Concentration chip on the group row when top1_share > 40%: "concentrated /
  集中度高" (muted, LENS carries the numbers).

## 5. UI composition

The groups section gains a lens tabset (existing .mx-tabset/segbtn idiom — tasks:
"Curated themes / 精选主题" | "Official sectors / 官方行业"), URL hash state, JS-off →
both lenses render stacked with their labels. The A-Share/HK market toggle is unchanged
(HK has no official lens this wave — its tab shows themes only). Section budget
unchanged (the tabset replaces nothing; it scopes the existing board).

## 6. Tests (tests/test_flow_observatory_groups.py, new — wire both CI halves same
commit)

1. official lens: no duplicate ticker per effective date (or exclusion + count when
   source violates);
2. themes may overlap; overlap_count correct on a constructed fixture;
3. official lens refuses historical claims (aggregating a window before seed_date →
   unavailable/refused, tested);
4. coverage floor → insufficient_coverage state, no rank, neutral quadrant;
5. contributors reconcile to aggregate (1e-6);
6. without_top1 flip detection on a constructed concentrated fixture;
7. excluded/missing members visible with reasons;
8. lens tabset renders both lenses; JS-off stacked rendering;
9. long ZH labels + dense contribution rows: no overflow (rendered-HTML assertion on a
   long-label fixture);
10. spike-failure path (if 2B): unavailable state renders with pinned strings; no
    curated data leaks into the official tab;
11. mutation M1: relabel curated themes as official (set group_kind official on theme
    rows) → duplicate-ticker or overlap tests fail (paste output).

## 7. Real proof (PR body)

Spike outcome + endpoint receipt (or gap record); coverage-floor calibration numbers;
one concentrated group + one diversified group shown side-by-side in the evidence
(concentration chip + drilldown line visible); full §0.5 matrix; performance note
(builder wall-time delta); authority context_only; accepted limitation: cap-weighted
views deferred (equal-weight is the shipped truth), HK official lens out of scope.
