# W2 frozen spec — binding source quality and fail-visible publication

`child: macro-flow-observatory-v2-w2-quality-publication-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §3 (budgets), §5 (state machine + publication law), §7 (failure states are designed states)`
`design authority: this spec. Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. A stale, degraded, unavailable, revised, or historical-only source leg can no longer
   render as a current/neutral read anywhere on flow_velocity.html: machine contract
   (desk.json) and UI agree on every leg's status.
2. The 2026-07/08 incident shape (#4676: A-share legs 12 days behind a live Southbound,
   page confidently current) is reproduced as a fixture and visibly fails-safe: trust
   chip STALE + section watermark + publication_state=STALE.
3. Golden Week fixture: CN market closure produces NO false staleness inside the
   calendar-aware budget (existing test_flow_desk_staleness holiday tests stay green).
4. A missing source never reads as zero flow; the page always renders (last-good with
   watermark, or explicit unavailable) — never an empty "no flow" state.
5. Machine receipts: every sources[] block carries status/reasons/confidence; a
   `health` summary block + `publication_state` land in desk.json; ::warning/::error
   annotations preserved; ≥2-consecutive-session degradation escalates to ::error +
   GitHub job summary line in the asia-close lane.
6. Evidence: dark/light × EN/ZH of the STALE and DEGRADED renders (fixture-forced),
   refreshed live matrix, zero console errors, no layout breakage; both themes'
   degraded/stale treatments are independently designed (not token-swapped).
7. Targeted suites green (2 known pre-existing cn_theme_tape failures excepted);
   canonical rebuild committed; tree clean; PR left DRAFT/unlabeled for principal review.

## 1. Quality engine (`engine/flow_observatory/quality.py`, new)

Pure module (no I/O beyond calendars): deterministic per-leg classification.

```python
def classify_leg(leg_id, effective_date, coverage, panels_meta, today) -> dict:
    # -> {"status": HEALTHY|DEGRADED|STALE|UNAVAILABLE|HISTORICAL_ONLY|REVISED,
    #     "confidence": HIGH|MEDIUM|LOW|INSUFFICIENT,
    #     "reasons": [machine-readable slugs], "gap_sessions": int|None}
```

Rules (frozen; trading-day math via lib/cn_calendar + lib/hk_calendar — wall-clock
calendar days are NEVER the gap unit except the final backstop):

- `nb_aggregate` → HISTORICAL_ONLY always (frozen 2024-08-16); never stale.
- `lhb_inst_seats` → event-window source: UNAVAILABLE if store unreadable/absent;
  otherwise HEALTHY with cadence "event-window" and last-event date displayed. It has
  NO stale state (a quiet Dragon-Tiger stretch is market behavior, not degradation).
- `cn_large_order_proxy` → gap = CN trading sessions between effective_date and the
  newest CN session ≤ today. gap 0 → HEALTHY; gap 1 → DEGRADED (reason
  `one_session_behind`); gap ≥ 2 → STALE. Unreadable/absent or unparsable as_of →
  UNAVAILABLE (reason `unreadable_as_of` — never silently skipped).
- `sb_aggregate` → same rule on the HK calendar.
- `hk_sb_holdings` → expected T−1: gap ≤ 1 HK session → HEALTHY (reason
  `expected_t_minus_1` when gap==1); gap 2 → DEGRADED; gap ≥ 3 → STALE.
- Coverage collapse (cn_large_order_proxy, hk_sb_holdings): scored/observed count
  < 70% of its trailing 20-session median (from state_log; INSUFFICIENT history <5
  sessions → skip the check, confidence MEDIUM) → status max(DEGRADED, current),
  reason `coverage_collapse`, confidence LOW.
- REVISED (W2 minimal): a leg whose effective_date moved BACKWARD vs the previous
  state_log entry, or whose newest date equals a prior session while values changed
  upstream, → status REVISED, reason `date_regression`. Full value-level revision
  receipts are W3 — do not build them here.
- Wall-clock backstop (desk-level, retained from desk_guard): newest live-leg
  effective_date > 10 calendar days old → every live leg min-status STALE, reason
  `desk_backstop`. This is the ONLY calendar-day rule.

`publication_state` = worst of LIVE legs (order HEALTHY < DEGRADED < STALE <
UNAVAILABLE); HISTORICAL_ONLY and event-window legs excluded from worst-of; REVISED
maps to DEGRADED severity for the rollup but keeps its own label on the leg.

Budget-calibration receipt (REQUIRED in PR body): before accepting the frozen gaps
above, measure each leg's actual publication lag over the available state_log/store
history (a short scripts/ or scratch probe is fine) and either confirm the budgets or
propose adjusted ones WITH the measurement — a budget is never kept merely because this
spec wrote it. desk_guard's existing 4-day/10-day constants stay untouched for its own
advisory path.

## 2. Contract + builder wiring

- sources[] blocks: `status` (now always set — replaces W1's null), `reasons`,
  `confidence`, `gap_sessions`; `ui_state` derives FROM status (mapping: HEALTHY→
  current, HEALTHY+expected_t_minus_1→expected_lag, DEGRADED→behind, STALE→stale,
  UNAVAILABLE→unavailable, HISTORICAL_ONLY→historical, REVISED→revised).
- New top-level `publication_state` + `health` block:
  `{"publication_state": ..., "consecutive_degraded_sessions": n, "reasons": [...]}`
  (consecutive count derived from state_log entries' health records; state_log entry
  gains a compact `health` field).
- `validate()` extends: sources[] statuses present and drawn from the enum;
  publication_state consistent with worst-of rule; a STALE/UNAVAILABLE leg's values
  never feed market_read as if current — STALE legs keep their last-good values in
  their own panels (watermarked) but market_read/quadrants computed from a STALE
  cn_large_order_proxy MUST carry `market_read.themes.quality = "stale"` and the hero
  verdict switches to the stale form (§3).
- Builder (`scripts/build_flow_velocity.py`): classify → compose → validate → write;
  escalation: if health.consecutive_degraded_sessions ≥ 2 emit
  `::error title=flow-observatory-degraded::<leg> <status> for <n> sessions` and append
  one line to `$GITHUB_STEP_SUMMARY` when set (plain print + flush, house annotation
  law — bare print at line start, never through a logger). Never fail the job (additive
  lane law) — the annotation IS the escalation surface.
- `scripts/check_tushare_freshness.py` untouched (its advisory path stands).

## 3. Template treatment (both themes designed independently)

- Trust chips: add `stale`/`unavailable`/`revised` ui_states. Dark: stale = desaturated
  amber ring + dimmed chip body; unavailable = dashed border + muted; light: stale =
  amber-tinted paper + 3px amber rail + deepened ink; unavailable = hatched/dashed
  hairline + muted ink. State words: stale → EN "stale — showing {date}" ZH "已过期 ·
  显示{date}数据"; unavailable → EN "unavailable" ZH "不可用"; revised → EN "revised"
  ZH "已修正".
- Section watermark: any L1 section whose data comes from a STALE leg gets a one-line
  watermark band directly under its h2: EN "Showing last good data from {date} — source
  behind." ZH "显示{date}最近有效数据 — 数据源滞后。" Dark: subdued amber band; light:
  amber-tinted paper strip + rail. NOT an overlay; numbers stay readable but the band
  is unmissable at a glance.
- Hero verdict stale form: when publication_state is STALE/UNAVAILABLE the verdict
  sentence is REPLACED with EN "Source data is behind — showing the last good read from
  {date}. Treat levels as history, not today's tape." ZH "数据源滞后——显示{date}的最近
  有效读数。请将其视为历史，而非今日盘面。" (stance chip switches to "Stand aside —
  data behind" / "暂缓 — 数据滞后").
- DEGRADED renders a quiet chip-level treatment only (no section watermark, no hero
  replacement) — plus the coverage reason in the chip LENS.
- publication_state HEALTHY renders nothing new (no "all healthy" badge clutter).
- What-changed section: a leg entering DEGRADED/STALE/UNAVAILABLE/REVISED since the
  previous session appears as a change row ("A-share large-order proxy: current →
  stale") — quality transitions are material changes.
- No horizontal overflow, EN/ZH parity, JS-off unaffected (all server-rendered).

## 4. Fixtures (tests/fixtures or in-test builders — commit NO real-data mutations)

F1 partial freeze (#4676 shape): cn legs 12 CN-sessions behind a current sb_aggregate.
F2 total freeze: every live leg > 10 calendar days old (backstop fires).
F3 Golden Week: today inside CN closure, legs dated last session before closure → all
   HEALTHY (and HK legs judged on the HK calendar independently).
F4 coverage collapse: current date, scored names at 50% of trailing median → DEGRADED.
F5 unreadable as_of → UNAVAILABLE with reason, page renders, leg chip unavailable.
F6 northbound → HISTORICAL_ONLY (existing behavior preserved).
F7 date regression → REVISED.
F8 missing source with last-good state_log history → UNAVAILABLE chip + prior-session
   change row; page renders.
F9 missing source, no history at all → UNAVAILABLE, market_read.quality reflects it,
   no zero-flow claim anywhere.

## 5. Tests (failing first; extend tests/test_flow_observatory_contract.py or new
tests/test_flow_observatory_quality.py — wire the new file into the SAME ci lane +
path gates in the SAME commit, per the W1 contract-delta lesson)

1. each fixture F1..F9 → exact expected per-leg status + publication_state;
2. machine/UI agreement: rendered page for F1 contains the stale chip word, the section
   watermark, and the stale hero form (and NOT the healthy verdict sentence);
3. holiday fixture produces zero DEGRADED/STALE (both calendars);
4. trading-day gap math: a weekend gap ≠ staleness; a 1-session gap on CN ≠ a
   1-session gap on HK dates;
5. worst-of rollup excludes HISTORICAL_ONLY and event-window legs;
6. STALE leg → market_read.themes.quality == "stale" and validate() rejects a payload
   claiming HEALTHY publication_state over a STALE proxy leg;
7. escalation: consecutive_degraded_sessions ≥ 2 emits the ::error line (capsys, assert
   line.startswith("::error"), house law);
8. UNAVAILABLE never yields zero-filled breadth (denominators shrink or quality flags,
   never silent zeros);
9. mutation check M1: force classify_leg to return HEALTHY for the F1 fixture → the
   machine/UI agreement test and the validate test both fail (paste output in PR);
10. existing suites stay green (desk_guard tests untouched).

## 6. Real proof (PR body obligations)

Fixture-forced STALE + DEGRADED browser evidence (dark/light × EN/ZH 1440 of the
watermarked page; 390 spot-check), refreshed live matrix (healthy state), calibration
receipt (§1), test counts + mutation output, canonical rebuild committed, performance
note, limitations (value-level revisions = W3; event-window semantics documented),
authority boundary context_only.
