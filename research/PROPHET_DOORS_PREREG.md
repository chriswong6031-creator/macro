# Prophet candidate DOORS — pre-registration (PDR)

Registered **2026-08-03**, frozen BEFORE the first accrual row exists. Scope: **Door T
(theme-relay)** and **Door R (re-arm)** only, built as W3 of
`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §5. **Door E (catalyst
confirmation) is NOT registered here** — it consumes W4's un-frozen earnings feed and gets its
own registration when that feed lands.

Implementation: `engine/prophet_doors.py` (emitters), `scripts/emit_prophet_doors.py` (nightly
hook), `scripts/grade_prophet_doors.py` (grader), `tests/test_prophet_doors.py` (fences).
Ledger: `data/prophet_doors/flags.jsonl` + `grades.jsonl` + `status.json`.

---

## §0 Honest framing — read first

**These doors have ZERO authority and this document does not grant them any.** They are
shadow-accrual lanes: they write their own ledger and nothing else. No board membership, no
plan origination, no rank / gate / size influence, no user-facing surface. Under house
epistemics that ships freely — a null never blocks building or accrual, and the gauntlet is a
PROMOTION gate, not a build gate. `tests/test_prophet_doors.py::test_no_authority_*` pins the
import fence: `scripts/build_stock_library.py`, `engine/us_board_rank.py`,
`engine/prophet_bridge.py` and `engine/signal_gate.py` may not reference `prophet_doors`.

**Prospective only — no backfill exists or will be added.** The ledger starts empty and
accrues from the night this merges, mirroring the PSS prospective-accrual charters. Every row
is a forward call made without hindsight. This is deliberately the slow, honest path: a
backfilled ledger of these constructions would be an in-sample fit of the very §2.5 study that
motivated them.

**What a PASS buys is a REVIEW, never authority** (§6). The gates below open an
operator-ratified adjudication on plan-origination rights. They do not arm anything, and no
code path reads the gate result.

**Where the constructions came from** (masterplan §2, not re-litigated here): the incumbent
fresh-cross family sights most eventual winners but median eligibility is 3 sessions of 63,
and hot-theme members sit permanently veto-blocked (44 of the top-50 21d movers are
stoch_ob-family vetoed). §2.5 measured the naive remedy and it FAILED — leader pullback-reset
scored **−2.12% per-name median excess** at H=21, while laggard crosses scored **+1.44%**.
Neither door here loosens a veto; both are new doors beside the incumbent one.

---

## §1 Fire definitions — EXACTLY as coded, constants included

Both doors evaluate once per nightly on the committed US cache universe
(`data/{breadth,midcap_breadth,smallcap_breadth}/_closes_cache.parquet`, deduped columns,
names with ≥ `MIN_HISTORY = 200` non-null closes; n = 1,493 at registration). The signal bar
is the LAST bar in that cache — never the wall clock — so a flag dated `D` was computed on
`D`'s close.

`v = engine.signal_gate.gate(ticker, close)` is the production verdict, called unmodified.

### 1.1 Door T (theme-relay) — routing, not a new detector

Fires iff **all three** hold:

| # | Leg | As coded |
|---|---|---|
| T1 | **Hot-theme membership** | `ticker` appears in the `members[].t` list of ANY subsector whose `theme` is one of the **top `TOP_K_THEMES = 5`** themes of `site/marketdata/subsector_rotation.json` ranked by `emerging_score` desc (ties broken by theme name asc) |
| T2 | **Gate eligible** | `v["eligible"] is True` |
| T3 | **Buyable tier** | `engine.signal_gate.is_buyable(v)` — i.e. `v["tier_cascade"] ∈ ("T1","T2","T3")`, the `BUYABLE_TIERS` constant. T4 is excluded by that constant, not by this door |

T2/T3 are the incumbent VALIDATED construction, byte-unmodified. **The only new thing is
candidacy routing**: theme heat conditions WHICH validated fires are recorded, never WHETHER a
fire is a fire. Theme state is a cross-sectional context, so nothing per-name is claimed
(DNR rows 114-115).

Recorded at fire: `theme`, `theme_rank` (1-5), `theme_score` (`emerging_score`), `subsector`
(+ all `subsectors`/`themes_hit` when a name is in several), `tier` (`tier_cascade`),
`tier_sub`, `ticks`, `rs63_pctile`, `sector`, `hist_d2`, `hist_d3`.

**Fail-soft + disclosed.** A missing, unreadable, or stale theme artifact makes Door T emit
**nothing** that night, with the reason written to `data/prophet_doors/status.json` and a
`::warning` annotation. Stale = the artifact's `asof` is more than `THEME_MAX_AGE_DAYS = 7`
days OLDER than the signal bar (an artifact fresher than the tape is never stale). An
unconditioned Door T would be a different door, so degrading into one is forbidden.

### 1.2 Door R (re-arm) — the MSFT/PLTR-class re-entry

Fires iff **all five** hold:

| # | Leg | As coded |
|---|---|---|
| R1 | **Not currently offered** | `v["eligible"] is not True` |
| R2 | **Master cross stale, not ancient** | `REARM_TICKS_MIN = 3 ≤ v["ticks"] ≤ REARM_TICKS_MAX = 15` (native-TF ticks since the master arrow; the incumbent's own fresh window is `FRESH_TICKS = 2`, so R starts exactly where the incumbent stops) |
| R3 | **Above the 200MA** | `v["above200"] is True` |
| R4 | **Weekly bull** | `v["weekly_bull"] is True` |
| R5 | **Re-arm confluence** | 2D RSI-MACD crossed up on the **latest COMPLETED 2D bucket** AND 3D StochRSI `K ≥ D` on the **latest COMPLETED 3D bucket** |

`is True` in R3/R4 is deliberate and load-bearing: an unanalysed `None` must never read as an
intact trend (the `build_stock_library` leaders-lane convention).

R5 reuses the frozen helpers `confluence_tiers._tf_bars` / `_rsi_macd` / `_stoch_rsi_kd` /
`_xup` — the math is never reimplemented. `prophet_doors.completed_tf(c, n)` wraps `_tf_bars`
and drops the IN-PROGRESS tail bucket: `_tf_bars` labels `{n}B` bins by bin START, so
`confluence_tiers._completed_resample`'s right-label truncation (W-FRI / 2W-FRI) does not
transfer; a bin is provably closed whenever a later bin holds data, so only the final bin is
tested (closed once the tape printed through `label + (n−1)` business days). A holiday inside
that bin holds it open one extra session rather than firing early — conservative, which is the
correct direction for a point-in-time gate. **Door R therefore cannot repaint**, unlike the
incumbent T3 tier which is read off the incomplete tail at a measured 23.8% US repaint rate.

Recorded at fire: `ticks_since_master`, `hist_d2`, `hist_d3`, `k3`, `d3`, `rs63_pctile`,
`sector`, theme membership if any (`theme`, `theme_rank`, `theme_score`), `above200`,
`weekly_bull`.

Door R keys on **trend-intactness + reset**, never on washout DEPTH (#1747 Amendment-3).

### 1.3 Shared frozen mechanics

- **`RS_LOOKBACK = 63`** — `rs63_pctile` is the cross-sectional percentile of
  `close / close.shift(63) − 1` over the cache universe at the signal bar (the §2.5 study's
  construction). Null when the name lacks 63 sessions; recorded as `null`, never imputed.
- **Cap: `MAX_FLAGS_PER_DOOR = 25` per door per night.** Overflow is COUNTED and announced via
  a `::warning` — no silent caps. Priority BEFORE the cap is frozen here:
  Door T = (`theme_rank` asc, `signal_gate.tier_rank(v)` asc, ticker asc);
  Door R = (`ticks` asc, ticker asc).
- **Dedupe: `DEDUPE_SESSIONS = 21`.** Within a door, a ticker is suppressed while a prior flag
  from the SAME door is fewer than 21 trading sessions old (sessions counted on the cache
  calendar). Dedupe is per-door: a Door R flag never suppresses a Door T flag. A same-night
  re-run therefore appends nothing, which also makes the lane idempotent.
- **Nightly is the sole advancer.** `append_flags` / `append_grades` / `write_status` refuse
  unless `engine.ledger_lane.nightly_advance_enabled()` (COLLECT_LANE=nightly), and the DAG
  hooks additionally require `--nightly`. Re-renders and intraday lanes compute the same flags
  and discard them.
- **Runtime**: 146 s measured over the 1,493-name committed universe at registration (both
  doors, single shared gate pass) — inside the ≤ 3 min/night budget.

---

## §2 Outcomes — the ruler, FROZEN

Graded by `scripts/grade_prophet_doors.py` into `data/prophet_doors/grades.jsonl`.

- **Horizons: H = 10 and H = 21 SESSIONS.** Positional offsets on the price index; those
  parquets hold trading days only, so H is sessions, never calendar days.
- **Fill: NEXT BAR.** Entry is the close of the bar STRICTLY AFTER the flag bar. A flag
  computed on tonight's close is filled at tomorrow's close. No same-bar entry on any path.
- **Primary statistic: `excess_spy` = `fwd_ret_H(name) − fwd_ret_H(SPY)`**, SPY reindexed onto
  the name's own calendar and forward-filled before being graded through the identical ruler.
- **Reused, not forked**: every return comes from `engine.grading.forward_metrics`, the same
  function `scripts/grade_us_board.py` grades the live board with (one-grader law §1.2). The
  excess construction is byte-identical to that file's `excess_spy`.
- **Policy-free**: fixed-horizon marks ONLY. No stops, no exits, no hold rules, no sizing.
  `engine.track_scoring.score_episode` carries that machinery and is deliberately NOT used —
  layering an exit policy would grade the policy instead of the door. A test pins this.
- **One-grader law**: a graded `(flag_date, door, ticker, horizon)` row is FROZEN and never
  regraded. Unmatured horizons are ABSENT from the ledger, never marked short.
- Also recorded per mark (supporting, no promotion power): `fwd_mfe`, `fwd_mdd`, `bench_ret`,
  `entry_price`, `fill_date`, `mark_date`.

---

## §3 Interim-read discipline (committed)

Between registration and a door's first formal read:

- **Accrual COUNTS may be displayed** — "Door T: N flags since 2026-08-04" is lawful anywhere.
- **OUTCOMES MAY NOT BE READ OR DISPLAYED.** No win rates, no excess figures, no "how is it
  doing" summaries, in any surface, PR body, report, or adjudication. The grader writes the
  rows; nobody reads their distribution until §4's trigger fires.

This is the whole point of pre-registering: a door watched continuously is a door that gets
promoted on its best week.

---

## §4 Promotion gate — ONE formal read per door, per trigger

The formal read is TRIGGERED (not scheduled) the first moment **all four** of the following
hold for that door. It is taken ONCE, and its verdict is filed whichever way it falls.

| Gate | Condition |
|---|---|
| **G1 — volume** | ≥ **100** matured flags at the primary horizon |
| **G2 — span** | ≥ **60** trading sessions between the earliest and latest matured flag date (a gate satisfied inside one hot fortnight is not satisfied) |
| **G3 — beats the incumbent** | door `win%` (share of matured flags with `excess_spy > 0`) ≥ the incumbent buy lane's matched-horizon `win%` |
| **G4 — economically non-negative** | door **median `excess_spy` ≥ 0** |

**Primary horizon: H = 21.** Exactly one promotion-bearing horizon, because exactly one
promotion-bearing test is permitted. H=21 is chosen a priori: it is the horizon the §2.5 study
that motivated both doors was measured on, and the house swing-horizon band is 2-4 weeks.
**H = 10 is printed as SUPPORTING** — it carries no promotion power and cannot rescue a G3/G4
failure at H=21.

**The incumbent comparator is defined, not chosen at read time:** rows of
`data/us_board_ledger/retro_grades.parquet` with `lane == "buy"` and `horizon == 21`, whose
`as_of` falls inside the door's own accrual window (same calendar, therefore same regime), on
the same `excess_spy` column and the same next-bar ruler. **Degenerate guard:** fewer than 30
such incumbent rows in the window → **NO VERDICT** (report only, the read does not count as
one of §5's two).

**Disclosed weakness of the comparator, stated now rather than at read time:** `retro_grades`
rows are pooled overlapping fires and `us_track_history.json` itself prints `effective_n = 1`
overlap caveats. G3 is therefore a point-estimate BAR, not a significance test, and the read
must say so. It is used because it is the only matched-ruler, matched-benchmark incumbent
number that exists; a door that cannot clear even an optimistic incumbent bar has nothing to
argue.

**Both doors are read independently.** Door T passing says nothing about Door R.

---

## §5 Falsifiers and kill rule (committed)

- **FAIL** = any of G3, G4 unmet at the primary horizon on a formal read (G1/G2 unmet is not a
  FAIL — it is "not yet read"). A FAIL files a null, changes nothing, and the door KEEPS
  ACCRUING. A null never deletes the lane.
- **Re-read trigger after a FAIL:** the next formal read is taken when BOTH ≥ 100 ADDITIONAL
  matured flags have accrued AND ≥ 60 trading sessions have passed since the previous read.
  No read may be taken earlier for any reason.
- **KILL — two consecutive formal reads FAIL.** The door closes: the emitter stops firing it,
  and a row is appended to `research/DO_NOT_REBUILD.md` (inside sections 1-4, with the
  regenerated `config/compiled_kill_registry.yml` + `config/signal_foundry_blocklist.yml` in
  the same PR). The kill is **construction-scoped** — it closes THAT door's exact
  construction as specified in §1, not theme-conditioned routing or re-arm entries as ideas.
- A KILL of one door does not touch the other.
- A door that is killed keeps its accrued ledger; the rows are evidence, not garbage.

---

## §6 What a PASS buys — a REVIEW, and only a review

A door that satisfies §4 and passes G3+G4 earns **the right to be adjudicated**, nothing more:

- It opens an **operator-ratified adjudication** on granting that door **plan-origination
  rights** (a candidacy path into `prophet_bridge` intake).
- **No authority is armed automatically.** No code reads the gate result; there is no auto-arm
  branch anywhere in this lane, by construction.
- A PASS grants **no rank authority, no sizing authority, no veto authority, and no board
  membership** under any circumstances — those are separate questions requiring their own
  registrations.
- The graded population of `us_board_ledger` is untouched either way (masterplan G0.4 / DNR
  §1 row 49). Doors grade in their OWN ledger; the live board's buy membership stays
  byte-identical unless and until a flip is separately ratified.
- Adjudication inputs are the formal read PLUS the disclosed comparator weakness (§4) PLUS the
  door's fire-rate and concentration profile. A statistically-clean door that fires 90% inside
  one sector is a routing artefact, and the adjudication is entitled to say so.

---

## §7 Fences — what these doors are NOT

Each line cites the standing kill it stays clear of.

- **NOT a leadership/momentum board (DNR row 117, Mag-7 forced-call class).** Neither door
  pins an un-gauntleted directional call to any surface: W3 ships no user-facing surface at
  all, and promotion (§6) requires an operator-ratified adjudication, which is exactly the
  process that row demands.
- **NOT per-name outcome audition (DNR row 69).** Both doors are single GLOBAL constructions
  with identical constants for every ticker; nothing is selected per-name, and no per-name
  best-of-grid timing choice exists anywhere in this lane.
- **NOT a conviction×timing blend or a graded-population merge (DNR row 49).** No conviction
  score is read, blended, or ranked by; the doors write only their own ledger and change no
  population on `us_standouts.json`.
- Also clear of: **#1513** (no 2D-freshness re-ranking — Door R records ticks, it does not
  rank by them), **#1747 Amendment-3** (Door R keys on trend-intactness, not washout depth),
  **DNR rows 114-115** (Door T conditions on THEME state, a cross-sectional context, and
  claims nothing per-name until its ledger matures), **A7 / CXI-R23** (no LLM originates any
  flag, score, or escalation here), and **P5** (no CN code, artifact, or ledger era touched).

---

## §8 Look-ahead controls and amendment law

- Every input is truncated at the signal bar. The gate verdict is the production
  `signal_gate.gate` on closes through that bar; Door R's technical legs read COMPLETED
  buckets only (§1.2); the RS percentile is cross-sectional at that bar.
- The theme artifact is consumed at its own `asof` and is REFUSED when it post-dates nothing
  useful (§1.1 staleness). It is never re-read historically — no backfill exists.
- Grading is strictly forward from a next-bar fill; an unmatured horizon is absent, not
  estimated.
- The word "validated" stays out of any user-facing text about these doors
  (`scripts/check_validated_claims.py` is CI-enforced). The incumbent trigger Door T reuses is
  validated; the DOOR is not.
- **This document is frozen at registration.** Any change to a constant, leg, ruler, gate,
  comparator, or horizon in §1-§6 is a dated amendment row below, added BEFORE the affected
  accrual or read — never after seeing an outcome. Changing a §1 constant changes the door and
  restarts its accrual clock.

| Amendment | Date | Change | Reason |
|---|---|---|---|
| — | — | none yet | registration |

---

*Related: `PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (§5 W3, the program),
`PROPHET_STAGE_QUALITY_PREREG.md` (the prereg form this follows),
`US_BOARD_MEASUREMENT.md` (the measurement canon the comparator comes from),
`DO_NOT_REBUILD.md` (rows 49 / 69 / 117 fenced in §7).*
