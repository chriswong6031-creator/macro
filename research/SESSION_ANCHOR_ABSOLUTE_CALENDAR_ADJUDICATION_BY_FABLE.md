# Absolute session-calendar anchor for the confluence cascade — adjudication

**Date:** 2026-08-06 · **Adjudicator:** Fable (main loop) · **Charter:** adversarial audit
2026-08-06 finding F1 (+F6), fleet-wide repair. **Era stamp:** `abs-session-2026-08-06`
(DT-R16 family — a dated graded-population change, labelled forever, never silent).

## The defect (verified, reproduced in-PR)

`engine/confluence_tiers._tf_bars` used `daily.resample("2B"/"3B")`, whose bin edges
anchor to the SERIES' FIRST timestamp. Every 2D/3D leg — tier crosses, freshness ticks,
the not_topped veto — therefore depended on how much LEADING history the caller passed.
Audit measurement: one dropped leading bar flips tier on 13/232 names (5.6%) and the
not_topped veto on 27/232 (11.6%); the two production loaders (data/stocks 1960s-start
vs data/baskets/ohlcv 2014-start) disagree on live buyability same-night (NUE, PEP
buyable from stocks/ and rejected from ohlcv/; ECL, SW inverted; WMT T1 vs T2). Four
history depths reach `cascade()` in production (deep stores; 345-bar breadth caches;
777-bar smallcap caches; massive_stock_day 2021-start; ohlcv 2014-start). The
`_completed_resample(c, "2W-FRI")` used by the S1/S2 HTF badges carries the same defect
class: the FORTNIGHT phase anchors to the series start (W-FRI itself is calendar-absolute
and clean).

`resample(origin=...)` does not fix it (no effect on non-tick freqs — verified,
RuntimeWarning). A calendar busday anchor (`np.busday_count // n`) re-introduces the
holiday mis-split that `engine/canon.py::resample_sessions` was built to eliminate (~80%
of NVDA signal dates relocated on calendar bins — audit #7). The repair must bucket by
the position of each session in a FIXED REFERENCE SESSION INDEX.

## Rulings

**R1 — Reference source is per-market; the US reference is RULES, not data.**
- **US (default):** `lib/nyse_calendar` sessions, materialized 1950-01-03 → today+400d,
  cached per process. Rationale: pure stdlib arithmetic — zero data dependencies (engine
  tests and CI packs need no store), identical in every lane (nightly, intraday, tests),
  immune to vendor-revision re-phasing (a silently revised historical row in a
  data-derived reference would re-phase every bucket after it — the audited disease
  reintroduced through the reference), and forward-dated (the reference always covers
  today, so the beyond-end extension path never triggers for US in practice).
  `ONE_OFF_CLOSURES` appends announced ahead of the date cause zero historical flips;
  a LATE append causes one bounded re-phase of the days since the closure (3 closures in
  14 years; the module's documented contract).
- **CN (`.SS`/`.SZ`):** sessions of `data/china/000001.SS.parquet` (Shanghai Composite,
  1997→, refreshed nightly, an index never halts). Covers the CN cascade inputs
  (china_search panel starts 2021-06).
- **HK (`.HK`):** sessions of `data/hk/_HSI.parquet` (1986→, nightly). Deepest HK input
  is 2008 (2800.HK).
- **CA (`.TO`/`.V`):** sessions of `data/canada/_GSPTSE.parquet`.
- **Unmapped markets (intl library):** US reference, disclosed. Start-invariance holds
  under ANY fixed reference (position is a function of (reference, date) only — never of
  the series); only bucket-edge placement around off-calendar holidays is approximate,
  which is the same class of approximation the old `"3B"` bins applied to EVERY market.
  Per-market references for intl are a follow-up, not this PR.

**R2 — Bucketing semantics.** For reference index R (ascending session dates):
`position(d) = R.searchsorted(d, side="left")`; `bucket(d) = position(d) // n`.
Per name: group its own daily bars by bucket id; bucket close = last by date; bucket
known-date = max date; bucket label = known-date. A date ABSENT from R (halt-free names
never hit this; synthetic bdate fixtures and off-calendar intl sessions do) shares the
position of the next reference session — deterministic, series-independent, graceful.
Dates BEYOND R's end (stale CN/HK/CA store; impossible for rules-US): per-series rank
extension `position = len(R) + rank among own post-R dates` — exact whenever the gap is
≤1 session or the name traded every gap session (the live case: reference stores refresh
nightly beside the name stores); divergence is confined to the stale window and heals on
refresh. Dates BEFORE R's start: currently unreachable (deepest input 1962 > 1950 epoch;
CN 2021 > 1997; HK 2008 > 1986) — guarded by the same rank rule mirrored, documented as
approximate.

**R3 — Market routing.** `cascade`/`tier_stream` gain `market: str = "US"`.
`signal_gate.gate()` infers from its ticker suffix via one shared helper
(`engine/session_anchor.market_for_ticker`) and passes through — US, CN, HK, CA boards
all route through `gate()`, so board callers need no edits. Direct CN callers
(`china_sector_turn` composites, CN replay paths) pass `market="CN"` explicitly.
Unrecognized suffixes → US (disclosed above).

**R4 — F6 ships as DISCLOSED fail-open, not tri-state.** The veto's `macd_bear` leg
(3D RSI-MACD, 232-bar warmup) is structurally unknowable for 159–231-bar names and
`float(NaN) < float(NaN)` evaluated it False — fail-open — while publishing
`not_topped=True` as if all three legs had been checked. Tri-state (`not_topped=None`)
would flow through every `if not not_topped` consumer as falsy and BLANK the whole
159–231-bar cohort — silently reversing the operator's 2026-08-05 floor-lift admission
decision, which is not this charter's call to make. Instead: the boolean keeps its
current decision arithmetic (fail-open on unknowable legs — now an EXPLICIT, tested
decision), and every return carries `veto_legs_null` naming each veto leg short of its
warmup with the same plain-word form as `null_legs` (the above200 PLTR-precedent shape:
never assert the unknowable; disclose it). `signal_gate` propagates the field beside
`null_legs`.

**R5 — Era stamp.** `confluence_tiers.ANCHOR_ERA = "abs-session-2026-08-06"`, emitted as
`anchor_era` on every `cascade` return (blank and graded) and as a column on
`tier_stream` frames; `signal_gate` copies it onto every verdict (`_VERDICT_KEYS` and the
slim `_BUY_KEYS` board dict) exactly as `young_history` propagates. Graded records
separate cohorts by the field's presence/value; the date inside the value is the charter
date and stays stable even if the merge lands a day later — the field's first appearance
in each stream is the operative boundary. Any future anchor change mints a new era
string. `calibration/provisional_replay.json` repaint rates and the warmup-floor numbers
cited in docstrings are PRE-era measurements — cited as such, queued for re-measurement;
never silently re-baked.

**R6 — 2W fortnight phase fixed in the same PR.** Absolute fortnight id
`((week_friday − 1970-01-02) days) // 14` (1970-01-02 is a Friday) replaces the
start-phased `"2W-FRI"` bins in `_completed_resample` call sites (`_htf_confluence_active`,
`_htf_2w_pending`), preserving the completed-only tail-drop contract. Weekly W-FRI legs
are already calendar-absolute — untouched. Without this the mandated start-invariance
test fails on the htf fields.

**R7 — Warmup floors re-measured phase-worst-case.** LEG_WARMUP_BARS values were
measured under start-anchored bins where every window landed at phase 0. Under the
absolute anchor a window's phase depends on its start date, so each floor becomes the
MAX over reference phases of the minimal sufficient N (same truncate-and-test method,
swept over n phase offsets). Any moved floor moves `MIN_HISTORY`/F6's boundary with it
through the existing single-source constants, covered by the same era stamp.

**R8 — What does NOT change.** `engine/canon.py::resample_sessions` (start-anchored
session grouping) is the golden oracle pinned 1:1 to the Terminal's `compute_signals` by
`golden_gate` — changing it unilaterally breaks a cross-repo contract; flagged for its
own adjudication if the Terminal ever moves. W-FRI weekly legs. All warmup-floor
SEMANTICS (the 345-bar breadth-cache one-armed confirm gate — wbull needs 391 bars — is
a DEPTH effect, disclosed via `null_legs`, measured in the blast-radius report; not an
anchor effect and not silently "fixed" here). Ledger history: no backfill, no retro-edit.

## Post-implementation amendments (2026-08-06, measured during the build)

**A1 — CN reference store gaps, scoped.** `data/china/000001.SS.parquet` lacks ~131
majority-trading dates that appear in the DEEP CN replay stores (`data/china_stocks`,
pre-2021 — e.g. 2014-12-25, a real CN session with 274/300 names trading). Against the
LIVE CN lane (`data/china_search/closes.parquet`, 2021→) the reference has **zero** gaps.
So live CN verdicts are cleanly anchored; only deep-replay bucket EDGES are approximate on
~1.66% of pre-2021 CN bars (invariance is unaffected — an absent date shares the next
session's slot deterministically). Union with `399001.SZ` was considered and REJECTED: it
doubles the reference's revision surface for zero live-lane benefit. **Binding rule:** a
future backfill that ADDS historical sessions to the CN reference store re-phases every CN
bucket after the inserted date — that is a graded-population change and REQUIRES a new era
stamp; never backfill the reference silently. If CN gap quality ever matters, the
designated upgrade is a committed append-only CN session artifact with an immutability
guard, not a wider store union.

**A2 — R2's "before R's start is unreachable" was wrong for CN replay.** 95
`data/china_stocks` names predate the 1997 CN reference start (`000001.SZ`: 1,695
pre-reference bars from 1991). The mirrored negative-rank branch is therefore LIVE, not a
guard. Containment: negative positions never cross 0, so every post-1997 bucket is
absolute regardless of how much pre-1997 history a caller loads; start-dependence is
confined to pre-1997 bucket rows plus an ewm warm-up carry that decays within about a
year. Replay grading windows (2021→) are unaffected.

**A3 — Sibling defect, out of charter, follow-up required.** `engine/signal_quality.py`
(the §7 marker engine that feeds `take_active`/`take_date` INTO the cascade) still runs
its own `resample("3B"/"2B")` — so while the CASCADE layer is now start-invariant (this
PR's measured 0/0), `gate()` END-TO-END is not: a leading-bar drop still moves §7 marker
dates on all five quintet names and flips `ticks` (PEP 7→3, SW 15→3), which can flip the
freshness gate. Same class in `engine/coiled.py`, `engine/mtf_upturn.py`,
`engine/leader_lifecycle.py`, `engine/cycles.py`, `engine/pick_lab/signals_1d.py`. Each
repair is its own charter with its own era stamp — `abs-session-2026-08-06` covers ONLY
confluence_tiers' buckets. Repairing signal_quality touches the validated §7 master's
calibration lineage and MUST NOT be folded into an unrelated PR.

**A4 — One downstream consumer DID read the old bin labels.** The adjudication's claim
that nothing reads `_tf_bars`' index semantically was false: `prophet_doors.completed_tf`
derived its closed-bucket test from the pandas bin-START label. Under the new
known-date-labelled buckets that expression silently delayed every Door R fire by one
session; caught by its own suite and repaired in-PR with exact position arithmetic
(`session_positions(last_obs) % n == n-1`), pinned by
`tests/test_prophet_doors.py::test_closed_tail_bucket_is_kept`.

**A5 — massive_stock_day measured in a restored lane only.** The store is R2-canonical
(0 parquets in dev checkouts; restored by the collect job), so the scan-tier blast slice
is deferred: `scripts/measure_anchor_blast_radius.py` is committed and emits a
`::warning` naming the absent universe; run it in a restored lane. Its names are
2021-start — the same depth class as baskets/ohlcv, whose slice IS measured.

**A6 — S-B frozen cross-age table.** The anchor redistributes S-B's cross-age events
across tick buckets (n 53/30/26 → 43/39/25). The frozen W5.2 packet JSON is untouched
(asserted untouched); the gate now pins the post-era reproduction so further drift still
reds. Re-reading the packet's verdicts at a fresh `REPRO_ASOF` is an open research
decision, chartered separately.

## Ship requirements (charter §SHIP, all in this PR)

1. Blast-radius measurement: `scripts/measure_anchor_blast_radius.py` →
   `reports/session_anchor_blast_radius.md` + `.json`, committed. Old-vs-new tier/veto
   flips per production loader (stocks/, ohlcv/, massive_stock_day scan universe, breadth
   cache depths, CN panel, HK stores); stocks/∩ohlcv/ agreement BEFORE and AFTER (target:
   0 disagreements, the NUE/PEP/ECL/SW/WMT quintet called out); start-invariance re-run
   on real data under the new anchor (must be 0 flips); 345-bar residual disclosed.
2. Era stamp as R5.
3. `tests/test_session_anchor_invariance.py`: cascade(c) == cascade(c.iloc[k:]) k=1..6 on
   all signal fields (length-encoding fields `bars`/`young_history`/`null_legs`/
   `veto_legs_null` excluded by definition) across a synthetic battery incl. real-NYSE
   holiday spans; tier_stream truncation-stability on the shared tail; F6 disclosure pins;
   fail-open decision pinned explicitly.
4. F6 per R4.
5. `tests/test_provisional_replay` + tier_stream consumers updated for the new anchor;
   full downstream confluence suite green.
6. Ship loop per repo law; this document + the measurement report are the PR's evidence.
