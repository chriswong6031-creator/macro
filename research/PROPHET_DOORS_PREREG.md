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
(DNR:KILL-ONSET-FINGERPRINTS / DNR:KILL-VOLUME-FINGERPRINTS).

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
- The graded population of `us_board_ledger` is untouched either way (masterplan G0.4 / DNR:KILL-PROPHET-POP-MERGE). Doors grade in their OWN ledger; the live board's buy membership stays
  byte-identical unless and until a flip is separately ratified.
- Adjudication inputs are the formal read PLUS the disclosed comparator weakness (§4) PLUS the
  door's fire-rate and concentration profile. A statistically-clean door that fires 90% inside
  one sector is a routing artefact, and the adjudication is entitled to say so.

---

## §7 Fences — what these doors are NOT

Each line cites the standing kill it stays clear of.

- **NOT a leadership/momentum board (DNR:KILL-FORCED-CALLS, Mag-7 forced-call class).** Neither door
  pins an un-gauntleted directional call to any surface: W3 ships no user-facing surface at
  all, and promotion (§6) requires an operator-ratified adjudication, which is exactly the
  process that row demands.
- **NOT per-name outcome audition (DNR:KILL-OUTCOME-AUDITION).** Both doors are single GLOBAL constructions
  with identical constants for every ticker; nothing is selected per-name, and no per-name
  best-of-grid timing choice exists anywhere in this lane.
- **NOT a conviction×timing blend or a graded-population merge (DNR:KILL-PROPHET-POP-MERGE).** No conviction
  score is read, blended, or ranked by; the doors write only their own ledger and change no
  population on `us_standouts.json`.
- Also clear of: **#1513** (no 2D-freshness re-ranking — Door R records ticks, it does not
  rank by them), **#1747 Amendment-3** (Door R keys on trend-intactness, not washout depth),
  **DNR:KILL-ONSET-FINGERPRINTS / DNR:KILL-VOLUME-FINGERPRINTS** (Door T conditions on THEME state, a cross-sectional context, and
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
| §9 addendum | 2026-08-04 | Recorded features added to the flag payload. **No §1-§6 change**: no constant, leg, ruler, gate, comparator or horizon moved | US Superintelligence Roadmap §4.1 — instrument the relay hypothesis before the ledger matures |

---

## §9 Recorded features (2026-08-04 addendum)

Added **before the first formal read and before any outcome was inspected**. At the time of
writing `data/prophet_doors/flags.jsonl` does not yet exist — the doors merged 2026-08-03 and
begin accruing tonight — so no distribution, win rate, or excess figure has been looked at by
anybody, and every row this ledger will ever hold carries these fields.

**Why now.** `PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §4.1 calls for the doors to
carry relay instrumentation from day one, so the promotion read can test the CN-measured relay
finding — that relay POSITION, not theme-heat LEVEL, separates chase outcomes — on US forward
data. A feature added later would only be measurable on rows accrued later; added now it is
measurable on all of them.

### 9.1 The fields

Every flag row carries all seven keys. A key is **present-and-null** when uncomputable, never
absent, so `null` always means "computed and unavailable" rather than "predates the addendum".

| Field | Definition as coded |
|---|---|
| `relay_count_3d` | Count of **other** cache-covered members of the flag's theme that printed a **fresh 63-session closing high** within the trailing `RELAY_RECENT_SESSIONS = 3` sessions, the flag bar included. Fresh high = `close > max(prior RELAY_HIGH_LOOKBACK = 63 closes)` — the session a NEW high PRINTED, not a session sitting at a standing one. |
| `relay_position` | Count of **other** covered members whose fresh high printed **strictly before** the flag bar inside the trailing `RELAY_POSITION_WINDOW = 21` sessions, divided by the theme's covered-member count. `0` = first mover, → 1 = late relay. |
| `relay_members_covered` | `n` — the covered-member count that denominator is taken over. Always recorded, including when `relay_position` is null. |
| `turnover_pctile` | Share of the flag ticker's own trailing volume window at or below its **admission-day** share volume (`1.0` = the window's highest). Source: `data/{breadth,midcap_breadth,smallcap_breadth}/_volume_cache.parquet`. |
| `turnover_window` | The number of sessions that percentile was actually computed over = `min(TURNOVER_WINDOW_MAX = 60, sessions available)`. |
| `foresight_stage` | The per-theme `stage` string from the Thematic Foresight Desk artifact `site/basketdata/foresight_cascade.json`, when the flag's theme joins a desk-covered theme. Read-only join; this lane never triggers, modifies, or reorders the desk. |
| `foresight_covered` | Whether that join hit. `false` + `foresight_stage: null` is the disclosed non-coverage. |

**Theme resolution.** Door T uses the flag's own theme. Door R uses the name's best-ranked hot
theme when it has one, and `null` when it does not — a Door R name outside every hot theme
records null relay fields, which is a reading, not a gap.

### 9.2 Null rules — what is deliberately NOT computed

Nulls here are printed, never imputed (house epistemics; prereg §0).

- **`relay_position` is null below `RELAY_MIN_MEMBERS = 4` covered members.** A "position"
  among two names is an artefact of the denominator. `relay_count_3d` is *not* gated this way —
  a raw count stays honest at any `n` — and `relay_members_covered` discloses `n` either way.
- **Relay coverage is strict.** A member counts only when it is in the doors' own close-cache
  universe AND its closes are complete across the whole 63+21 session tail. A hole would make
  `close > NaN` evaluate False, i.e. would silently record "did not break out" for a name
  nobody could measure. Measured at registration of this addendum: **81 of 128** top-5 theme
  members were covered — 45 members of the rotation artifact are absent from the three breadth
  caches entirely, 2 more carried holes. The rotation artifact's universe is wider than the
  doors' universe; `relay_members_covered` is the per-flag disclosure of that gap.
- **`turnover_pctile` is null when the volume cache carries no observation ON the flag bar.**
  Reading the prior session's volume as "admission-day" would fabricate the feature. A
  single-observation window is likewise null — its percentile is definitionally `1.0`.
- **The 60-session window is aspirational, not claimed.** These caches were backfilled
  2026-05-19 and the median column currently holds ~51 non-null sessions, so most flags will
  record `turnover_window` in the 50s. The roadmap names this cache depth as known debt; the
  honest response is to record the window that existed, which is why `turnover_window` is a
  field rather than a constant.
- **`foresight_stage` joins on normalised-exact theme names only** (casefold, strip
  non-alphanumerics; the desk's slug and display name are both indexed). No fuzzy or nearest
  match — that would invent desk coverage the desk never claimed. The two taxonomies were built
  independently, so coverage is partial by construction: **2 of 41** rotation themes joined at
  the time of writing, and **none of the current top-5 hot themes**. Expect this field to be
  mostly null until the §4.2 Foresight → Theme Tape wiring reconciles the vocabularies.

### 9.3 Authority — none, and the fences that make that structural

**These features have ZERO effect on fire, cap, dedupe, priority, or grading.** They are not a
filter, not a leg, not a tiebreak, and not a score.

- **Fire definitions are unchanged.** §1's legs and constants are byte-identical to
  registration. Nothing in §1-§6 moved.
- **Computed after the fact.** `emit()` settles every fire decision, the frozen priority sort,
  the `MAX_FLAGS_PER_DOOR` cap and the `DEDUPE_SESSIONS` dedupe, and only then featurises the
  rows it already kept. Dropped and deduped candidates are never featurised. The ordering is
  structural, not a convention.
- **Degrade-to-null.** Any failure inside the feature computer records the all-null block and
  leaves the night's flags untouched.
- **The grader stays blind.** `scripts/grade_prophet_doors.py` reads price and nothing else; a
  test asserts no feature key appears in it. The ruler grades the door, not a feature.
- **Constants are segregated.** `engine/prophet_doors.py` carries the frozen door constants and
  the analysis-feature constants in two separately labelled blocks, so a future edit cannot
  mistake one for the other. Changing a feature constant changes what an analyst can measure;
  changing a §1 constant changes the door and restarts its accrual clock.

Pinned by `tests/test_prophet_doors.py`: `TestFireInvariance` runs the same synthetic tape
through `emit(features=True)` and `emit(features=False)` and requires an identical fire set —
same tickers, same candidate/overflow/dedupe counts — with the feature block purely ADDITIVE
(no recorded fire receipt overwritten by a colliding key). `TestFeatureScopeFences` pins the
after-the-cap ordering, the blind grader, and the constant segregation.

### 9.4 What this addendum does not do

It does not add a gate, move a horizon, change the comparator, or grant the features any
promotion power. §4's four gates are unchanged and remain the only promotion trigger. These
fields are inputs to the ADJUDICATION that a §4 pass opens (prereg §6 already admits the
door's fire-rate and concentration profile as adjudication inputs); they are not evidence a
door can pass a gate with, and a relay result cannot rescue a G3/G4 failure.

---

## §10 W8 ignition features (2026-08-05 addendum)

Appended, not a rewrite: **§1–§8 are untouched**, and §9's seven fields are unchanged. This
addendum adds six recorded keys and nothing else. No gate moved, no horizon moved, no
comparator moved, no fire condition moved.

Registered while the ledger is still young and, as with §9, **before any outcome has been
read** — §3's interim-read discipline has not been broken by anybody, and no distribution,
win rate or excess figure from `data/prophet_doors/` has been inspected.

**Why now.** `PROPHET_US_IGNITION_LAYER_W8_BY_FABLE.md` ran four ignition stand-ins on the
2014–2026 OHLCV panel (PR #4564, `research/prophet_us_audit/ignition_standins.py`). Two
survived. Recording their STATE on every door flag from tonight makes them measurable on the
whole forward ledger; added later they would be measurable only on rows accrued later.

### 10.1 Provenance — what #4564 actually measured

Matched-set deltas against gate-matched controls, month-block CI in brackets.

| Stand-in | H=10 | H=21 | H=63 | n |
|---|---|---|---|---|
| **S-COIL** (release out of a compressed uptrend) | +0.12 [−0.02, +0.27] | +0.24 [−0.00, +0.53] | **+0.98 [+0.42, +1.55]** | 24,989 |
| **S-THRUST-LAG** vs coiled names in NON-thrusting themes | **+1.31 [+0.64, +1.95]** | **+2.04 [+0.79, +4.21]** | **+4.67 [+2.29, +6.41]** | 228 |
| S-THRUST-LAG vs already-moved members of the SAME theme | +0.24 [−0.40, +0.97] | −0.22 [−1.04, +0.90] | +0.39 [−1.37, +2.42] | 228 |

Bold = the CI excludes zero. The third row is the arm that came back **null at every horizon**:
theme context pays, the laggard-vs-leader choice inside the theme does not. Only the
theme-context reading is recorded here.

**Not recorded, deliberately.** S-RANKVEL was **refuted** (negative at every horizon) and is
wired nowhere. S-INSIDER was **never run** (its kills-check hit a named gap). Neither appears
in `FEATURE_KEYS`, and a refuted sensor is not "available for later" — re-proposing it needs a
new instrument, not this addendum.

### 10.2 The fields

Six keys, present on every flag row, null-with-a-reason when uncomputable.
Constructions live in `engine/ignition_features.py` — a port of the frozen W8 instrument whose
**elementwise fidelity is pinned** by `tests/test_ignition_features.py::TestPortFidelity`
(the research file is frozen and is not edited to import the engine module, so the fork risk
is answered by a test rather than by a convention).

| Field | Definition as coded |
|---|---|
| `coil_compressed` | The S-COIL compression state of the flag's own name **at the flag bar**: ATR(21) percentile against its own trailing 252 sessions `< 0.25`, **and** close above a 50dMA that is rising over 10 sessions. This is the instantaneous leg S-THRUST-LAG used to pick candidates. `bool`; `null` + a reason when uncomputable. |
| `coil_bars_compressed` | Compressed sessions inside the trailing `COMP_LOOKBACK = 21`. `>= COMP_MIN = 10` is S-COIL's own **armed** run, so the count reconstructs that state while keeping the distance from the threshold that a bare boolean would discard. |
| `coil_reason` | Why the coil block is null: one of `ohlcv_absent`, `no_bar_on_flag_date`, `short_history`, `read_failed`. `null` when the block computed. |
| `theme_thrust_state` | `"thrusting"` when the flag's theme fires the stand-in's thrust **event** on the flag bar — above-20d-high member fraction `> 0.50` now, `< 0.30` within the prior 5 sessions, de-bounced to the run's first bar — else `"quiet"`. `null` + a reason when uncomputable. |
| `theme_thrust_frac` | That fraction at the flag bar: covered theme members trading above their own 20d high, over the covered-member count. |
| `theme_thrust_reason` | Why the thrust block is null: one of `no_theme`, `no_covered_member`, `thin_membership`, `short_history`. `null` when the block computed. |

**Frame.** `data/baskets/ohlcv/<ticker>.parquet` — the SAME panel #4564 measured on, so a
forward reading is comparable with the numbers in §10.1 rather than merely analogous. The
breadth `_high_cache`/`_low_cache` parquets were measured on 2026-08-05 at a **median of 51
non-null sessions** against the **293** an ATR-percentile-over-252d read needs (33 of ~1,550
columns clear 252), so sourcing high/low there would have nulled the coil on ~98% of flags.
The OHLCV store covers **1,190 of the 1,495** universe names; the rest record `ohlcv_absent`.

**Theme resolution** is §9's, unchanged: Door T uses the flag's own theme, Door R the name's
best-ranked hot theme, `null` when it has none.

### 10.3 Null rules and stated construction deltas

- **Null, never `False`.** An uncomputable coil is not an uncompressed name and an unreadable
  theme is not a quiet theme, so both carry `null` plus a reason key. `False` and `"quiet"`
  are reserved for readings that were actually taken. This is load-bearing rather than
  stylistic: `coil_compression` and `above_20d_high` return **booleans**, so a bar inside a
  warm-up window reads `False`, not NaN — cold data does not announce itself, it impersonates
  a measured negative. The history floors (`COIL_MIN_SESSIONS = 293`,
  `THRUST_MIN_SESSIONS = 27`) exist to keep that fabricated `False` out of the ledger.
- **The crash path is all-null, including the reason keys.** The four/four slugs above cover
  data gaps, which is what a per-row reason can honestly name. An exception inside the feature
  computer is an engine fault, not a coverage fact, so it records §9's all-null block (every W8
  key `null`, reasons included) and announces itself at run level — `feature_source.ignition`
  plus a logged warning — rather than inventing a fifth coverage slug for it.
- **Never imputed.** A store that stops before the flag bar records `no_bar_on_flag_date`;
  carrying the last available session forward would date-shift the feature onto a bar the name
  did not trade. Same rule §9.2 applies to admission-day volume.
- **Strict coverage.** A theme member enters the thrust fraction only when its close and high
  are complete across the whole trailing window; a holed member leaves the numerator **and the
  denominator**. `thin_membership` below `THRUST_MIN_MEMBERS = 6`, the stand-in's own
  readability floor.
- **DELTA — the thrust de-bounce is kept.** `"thrusting"` is an event-day reading, so most
  flags will read `"quiet"`. That is deliberate: #4564's +1.31/+2.04/+4.67pp was measured on
  coiled members **on the thrust bar** (n=228). Recording a standing "fraction is high"
  condition would accrue a population the study never graded, and the forward comparison would
  not be a comparison.
- **DELTA — holes are dropped, not held.** The stand-in read a panel where a missing bar stayed
  NaN. Held as NaN, every rolling window covering the hole returns NaN and — because the
  detector is a boolean AND — lands as `False`, i.e. a fabricated "not compressed". The per-name
  read here drops holed rows instead and computes over the bars the name actually traded, at the
  cost of a window spanning more calendar time than sessions. Neither choice is free; this one
  cannot manufacture a negative. The W8 frame is survivor-lean (119 of 120 sampled names carry
  bars to the final session), so it bites rarely.
- **DELTA — no PIT membership.** The stand-in honoured each basket's `added`/`removed` dates.
  `site/marketdata/subsector_rotation.json` is a nightly snapshot carrying no membership
  history, so the fraction is read over the theme's CURRENT member set across the trailing
  window. §9's relay feature already has this property. Stated, not fixed: inventing membership
  dates the artifact never recorded would be the worse error.
- **DELTA — the flag bar is not S-COIL's graded event.** S-COIL grades the **release** bar
  (first close above the prior 21d high out of an armed run). A door flag is its own trigger and
  coincides with a release only by accident. What is recorded is therefore the **arming state**,
  which ESX §9 / DT-R5 ban as a standalone **surfaced or graded** read. It is recorded here in a
  no-authority shadow ledger with no surface, no rank and no grade of its own, and this addendum
  grants it none. A future surface would need its own adjudication, not this section.

### 10.4 The horizon mismatch — stated, not papered over

**S-COIL's only measured payoff was at H=63. §2 grades H=10 and H=21, and nothing else.**

Those are exactly the two horizons where S-COIL came back null (+0.12 and +0.24, both CIs
straddling zero). So the coil keys accrue a state whose measured effect this ledger's ruler
**cannot currently see**. That is a real limitation of recording it here, and it is worth
recording anyway — the state is cheap, it is needed as the candidate leg of the thrust reading
regardless, and a state not accrued tonight is unmeasurable for every row accrued before
somebody notices.

What this addendum explicitly does **not** do is add an H=63 mark to fix the mismatch. Changing
the horizon set is a §2 change and therefore a §8 amendment with its own restart of the accrual
clock — not something an addendum may do silently to make its own feature look promotable. Any
future coil promotion read must either state that it is reading a longer horizon than §2 grades
(and register it properly first), or accept that it is testing the sensor at the two horizons
where it already failed.

The thrust keys carry no such mismatch: the surviving arm cleared zero at **H=10 and H=21**,
both of which §2 grades.

### 10.5 Authority — none, by the same structural fences as §9

§9.3 applies unchanged and its fences are the same code path: computed after every fire
decision, the priority sort, the cap and the dedupe; degrade-to-null on any failure; the grader
stays blind (`tests/test_prophet_doors.py::TestFeatureScopeFences` iterates `FEATURE_KEYS`, so
the new keys are covered without a new rule); constants segregated into the analysis block.

`TestFireInvariance` now seeds the ignition store too, and carries an explicit guard
(`test_the_ignition_features_actually_computed_in_this_fixture`) asserting the W8 keys really
computed in that fixture — an invariance test whose features all degraded to null would agree
with itself no matter what the feature computer did.

**Cost.** Measured 2026-08-05 against the live store: a full 25-flag door computes in **0.66 s**,
including the one-time load of its 128 hot-theme members (~3.3 ms/ticker, ~27 ms/flag amortised).
Bounded by construction — at most `2 × MAX_FLAGS_PER_DOOR` coil reads plus the members of at
most `TOP_K_THEMES` themes, each theme's thrust computed once and shared by every flag in it,
every read cached per run. Against the doors' own ~159 s universe pass this is under 1%.

### 10.6 What this addendum does not do

It adds no gate, no horizon, no comparator, no score, no composite and no ordering. §4's four
gates remain the only promotion trigger, and a coil or thrust result cannot rescue a failure
there. These fields are inputs to the **adjudication** a §4 pass opens — never evidence a door
can pass a gate with.

---

*Related: `PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (§5 W3, the program),
`PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` (§4.1, the addendum's origin),
`PROPHET_STAGE_QUALITY_PREREG.md` (the prereg form this follows),
`US_BOARD_MEASUREMENT.md` (the measurement canon the comparator comes from),
`DO_NOT_REBUILD.md` (DNR:KILL-PROPHET-POP-MERGE / DNR:KILL-OUTCOME-AUDITION / DNR:KILL-FORCED-CALLS fenced in §7).*

---

## §10 Door W — washout-turn entries, fully aligned (registered 2026-08-06, FROZEN before first accrual)

Chartered by `SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md` §4 (W5) from the 2026-08-05 census:
of 117 names live in the washout-turn watch cohort, 109 were invisible to Prophet; the 65
fully-aligned members held 61 invisible — among them ABT, BKNG, BSX, CME, CRM, GILD, HCA, ICE,
INTU. Door W makes that class a RECORDED, forward-graded candidate population. It is a shadow
lane in this document's exact sense: §0's honest framing, §7's fences, and §8's amendment law
all bind unchanged.

### §10.1 Fire definition — EXACTLY as coded, constants included

A name FIRES Door W on a session when ALL THREE legs hold (`engine/prophet_doors.py
door_w_candidates` / `door_w_aligned`):

- **W1 — the organ says WASHOUT_TURN.** `engine.washout_turn.compute_symbol_washout(close,
  _deepen_close(sym, close))` returns state `WASHOUT_TURN` on the organ's own closes ladder
  (`mtf_upturn._load_close` preferred store; #4663 prepend-splice for the depth legs). The
  state machine — depth ≤ 15th own-history percentile at a completed-weekly canon RSI-MACD
  bull cross, graduation/failure exits, 1-bar hysteresis — is the ORGAN's; this door
  reimplements none of it.
- **W2 — the entry is FRESH:** `weeks_since_cross <= 2` (`WASHOUT_FRESH_WEEKS = 2`). Door W
  records ENTRIES into the class, not standing membership; a long-basing name fires once per
  qualifying cross, not nightly.
- **W3 — full faster-grid alignment:** on the 2B AND 3B session-grouped canon grids
  (`WASHOUT_ALIGN_GRIDS = ("2B","3B")`), RSI-MACD line > signal on the LAST COMPLETED bar,
  recomputed from price at fire time (definite-True only; an unreadable grid never counts as
  aligned). No `site/` or `data/stock_events/` artifact is read — the fire set cannot move
  with nightly step ordering.

Cap and hygiene inherit §1's machinery verbatim: dedupe on (ticker, session) against the
shared `flags.jsonl`, `MAX_FLAGS_PER_DOOR = 25` per night with counted, announced overflow —
under the cap the DEEPEST `depth_pctile_at_cross` wins (the depth receipt is the door's own
sort key; conviction-style scores are not consulted).

### §10.2 Ruler — declared at registration

Grading unit = flag-day cohort, mirror of §2. **H=63 sessions excess-vs-SPY is PRIMARY** for
this door — the basing class pays at the swing horizon if it pays at all (W8 S-COIL:
compression NULL at entry horizons, +0.98 [+0.42,+1.55] at H=63) — with H=21 recorded as the
supporting read. Declaring a different primary horizon than Doors T/R at REGISTRATION (not
after results) is the lawful form of the choice; §8's no-peeking discipline applies from the
first row.

### §10.3 Promotion gate — one formal read

Mirrors §4's shape: earliest formal read when ≥40 matured H=63 flags exist spanning ≥8
distinct admission weeks. Pre-stated bar: median H=63 excess > 0 AND loser-rate (H=63 excess
< −10%) below the matched-universe base rate, both surviving a date-blocked bootstrap 90% CI.
A PASS buys a REVIEW (§6) — an operator-ratified adjudication of whether washout-turn context
may enter any scored surface — never automatic authority. A FAIL closes THIS construction
(fresh + aligned + depth≤P15 at weekly grain) and appends the DNR row itself.

### §10.4 Fences — what Door W is NOT (verified against primary sources 2026-08-06)

- NOT an entry-stack leg, gate covariate, or veto change: the killed `esx_washout_x_turn`
  interaction (#1747 Amendment-3) stays killed; Door W is a candidate RECORD.
- NOT a revival of sector-grain scored washout→turn (Oracle P8 P-W1/S-W3, NULL): the SEA
  atlas first-read REPRODUCES the pooled thinness (+0.23pp median 13w excess on 7,328
  aligned washout crosses) — the door exists because the CONDITIONED class, not the pooled
  trigger, is the open question, and only forward accrual can answer it lawfully.
- NOT per-name outcome audition (DNR row 69): the fire definition is uniform across names;
  per-name atlas receipts ride as recorded features, never as fire conditions.
- NOT a Prophet consumer: nothing in the pick chain imports Door W output
  (`test_no_authority_*` pins extended).

### §10.5 Recorded features (never fire conditions)

Attached only to rows that already survived fire/sort/cap/dedupe (structural invariance, same
placement as §9): depth_pctile, depth_pctile_at_cross, weeks_since_cross, weekly_cb,
drawdown_pct, stoch_k/d, era, regime_bucket, and the SEA atlas receipt components
(name/arch/global n + 13w/26w posteriors) where cheaply available. Feature failure degrades
to nulls and cannot change a flag (`feature_source_w` disclosure in status.json).

### §10.6 Prospective only

No historical backfill. The ledger's first Door W row is the first nightly after this
section merges. The 2026-08-05 census cohort is CONTEXT for why the door exists; those
sightings are not rows.
