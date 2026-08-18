# Contract — `options.intel_brief/v1` (`intel_brief_heuristic/v1.2`)

Code-facing executable contract for the Daily EOD Options Intelligence Brief.
Sources of authority, in order: the program masterplan
(`research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md`),
`DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION`,
`DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT`, and the amended AD-1 handoff §5.3 (v1.2)
(`research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md`),
plus the AD-1 runtime source-clock ruling (settled vs pending, 2026-08-18) and the Sol
review Block B1-B4 fix (2026-08-18, PR #5872 REQUEST_CHANGES — receipt closure, the
two-gate coverage law, evidence-derived freshness, and the two-domain Prophet mapping)
transcribed here. Implementation is transcription: any divergence between code and this
contract is a defect in exactly one of them and must be returned, never silently adapted.

Producer: `scripts/build_options_intel_brief.py` → `engine/options_intel_brief.py` (pure).
Artifact: `site/options_intel_brief.json` (atomic write; semantic no-op on unchanged receipt).
Consumer (AD-1): `scripts/build_options_command.py` → `templates/options.html.j2` (pass-through
adapter; zero recomputation). No Prophet/Neural-Web/Sector/Terminal consumer in AD-1.
Authority: display-tier research-priority ONLY. Deterministic; no network; no LLM anywhere
in the authoritative path.

---

## 1. Source-clock law (settled vs pending; supersedes any T+0 wiring)

The chain snapshot and OI are on different knowledge clocks: a snapshot dated `D` carries
the OI print attributable to the PRIOR session. Full directional scoring therefore uses the
newest lawful pair of consecutive NYSE sessions:

```text
S = settled research session          (the session the board is ABOUT)
D = next_nyse_session(S)              (the snapshot whose OI count is attributable to S)
require: chain[S] exists AND chain[D] exists AND D == next_nyse_session(S)
```

- IV / volume / skew / spot / same-session features: from `chain[S]` ONLY.
- `Q_oi` for S: contract-matched OI change over the lawful `S → D` pair. `oi_counted_date = D`.
- NO non-OI field from `D` may leak into the S research state (test 24).
- Same-day OI (treating chain[S]'s own OI column as S's settled OI) is UNLAWFUL for Q_oi (test 25).
- If the newest two stored sessions are not consecutive NYSE sessions, walk backward to the
  newest lawful consecutive pair and disclose the gap (test 26). NYSE calendar = the repo's
  existing session arithmetic helper (`engine` trading-calendar utilities); never raw calendar days.
- If a chain session newer than S exists without its next-session OI print: header carries
  `pending_session = <date>`, `pending_reason = "OI_NOT_YET_SETTLED"`. The pending session is
  NEVER scored, never directional, and never mixed into S cards (test 27).
- Historical windows: only observations lawfully available at build time for S.
- GEX mechanics (`gex_confirm_verdict`) may set `M_gex` only when its evidence binds to S
  (artifact as-of == S). Otherwise the mechanics family is ABSENT and `M_gex = 1.0`; never
  borrow next-session mechanics (test 28).
- Prophet display context may be newer than S (`prophet_asof` shown); zero rank authority (test 29).
- Any core mixed-vintage failure → `board_state = "DEGRADED"`, `board_reason = "MIXED_VINTAGE"`;
  an optional family simply goes absent if the core state stays coherent. Never zero-fill.

## 1a. Two gates (B2 — SOURCE_COVERAGE_GATE is SEPARATE from ELIGIBILITY_GATE)

Two different failure modes used to share one constant (`ELIGIBILITY_GATE`), which
collapsed "is chain[S] itself a plausible full snapshot" and "how many present names
individually have enough data" into a single number. They are now two independent gates,
checked in this order:

```text
1. Source coverage (board-level):
   source_coverage_pct = |present_names ∩ universe| / |universe|
   universe = producer-resolved engine/options_universe.py::gex_symbols() (input #7)
   source_coverage_pct < SOURCE_COVERAGE_GATE (0.90)
     -> board_state = "INSUFFICIENT_COVERAGE" (cards withheld)
   NEVER derived from any historical chain session's own name count (the deleted
   "historical-max" heuristic) — a session with no explicit universe override defaults
   to asserting 100% of ITS OWN present names, never borrowing another session's count.
2. Eligibility (per-name data quality, unchanged threshold):
   eligible/present < ELIGIBILITY_GATE (0.60)
     -> board_state = "DEGRADED", board_reason = "ELIGIBILITY_COLLAPSE" (cards withheld)
```

The header's `eligibility` block additionally reports `universe_count` and
`source_coverage_pct` (rounded 4dp) on EVERY payload where a chain[S] was loaded at all
(not only on the `INSUFFICIENT_COVERAGE` branch) — `null` only when undecidable
(`MIXED_VINTAGE`, no chain ever loaded).

## 2. Inputs (read-only; existing loaders only)

| # | Input | Path | Used for | Clock |
|---|---|---|---|---|
| 1 | EOD chains | `data/polygon_gex/chains/{session}.parquet` (underlying, strike_ticker, expiry, K, T, is_call, oi, iv, gamma, delta, volume, spot, asof) | eligibility, V family, salience buckets, Q_skew, Q_oi (S→D pair), C family, market-implied move | S (and D for OI only) |
| 2 | GEX summaries | `data/polygon_gex/summary_{SYM}.parquet` (spot history, gamma_flip, …) | RV for v2, spot-extension c2, flip proximity display | rows ≤ S only |
| 3 | gex_confirm | `site/gex/{SYM}.json` via `engine.gex_confirm.assess(..., direction="up")` | mechanics context + `M_gex` | must bind to S else absent |
| 4 | Earnings calendar | `data/earnings/earnings.parquet` (`next_date` per ticker) | E family event window (S, S+45d] | forward-known |
| 5 | Prophet display context (TWO domains, B4) | `site/prophet/index.json`: `plans[]` (`asset`, `entry_status`, `lifecycle_state`, `closed`) AND `intake.receipts.groups` (bucket `reason` + `names[].ticker`) | display-only `prophet_state` chip, resolved per §5's two-domain precedence | may be newer than S; `prophet_asof` disclosed |
| 6 | Flow signing gate | `data/options_flow/signing_gate.json` | proves `Q_flow` must stay ABSENT while `direction_reliable == false` | current |
| 7 | Options universe (B2) | `engine/options_universe.py::gex_symbols()` (config anchors + baskets, capped) | `SOURCE_COVERAGE_GATE` denominator; producer-resolved, passed to the pure engine as an explicit list+count | current; NEVER derived from the chain store's own historical session sizes |

No collector is invoked; no network; missing optional input → family absent; missing core
input (chains for the pair) → `STALE_SOURCE`/`DEGRADED` per §5.

**B1 — receipt closure.** Every score-affecting per-symbol input the producer actually
reads must bind the receipt: `data/polygon_gex/summary_{SYM}.parquet` (input #2) for
every name present in chain[S], and every `site/gex/{SYM}.json` (input #3) whose own
`meta.asof` binds to S (a file opened but rejected for a stale `asof` was never
"consumed" — its bytes never influenced the payload, so it is deliberately excluded).
The producer hashes exactly this consumed set (never the whole directory) into a
deterministic `source_manifest` (§5) and folds a merkle-style aggregate root per domain
into `input_receipts` — see §5's `receipt_id` formula, which already hashes the full
`input_receipts` list, so the two roots are what actually binds them.

## 3. Frozen CONFIG (every constant; tests pin verbatim)

```text
MODEL_VERSION            = "intel_brief_heuristic/v1.2"
SCHEMA                   = "options.intel_brief/v1"
MIN_CONTRACTS            = 20          # quotable contracts (iv notna AND oi+volume > 0)
MIN_HISTORY              = 10          # H floor (prior sessions with chain rows)
LOOKBACK                 = 20          # generic W target window (min(W,H) rule)
DOI_TARGET_WINDOW        = 60          # ΔOI z target window (min(60, available), floor 10)
SKEW_CHANGE_FLOOR        = 8           # min delta-skew observations for Q_skew
SALIENCE_W_D1            = 0.65
SALIENCE_W_D3            = 0.35
Q_TH                     = 0.50        # |Q_oi| and |Q_skew| direction threshold
SALIENCE_TH              = 0.60        # D_salience direction threshold
VOL_STATE_TH             = 0.60        # |F_V| VOLATILITY route threshold
EVENT_STATE_TH           = 0.50        # |F_E| VOLATILITY route / event-board threshold
ES_W_DIR                 = 0.70        # evidence_strength = 0.70*Dir_strength + 0.30*D_salience
ES_W_SAL                 = 0.30
CONF_BASE                = 0.30
CONF_PERSIST_BONUS       = 0.10        # d3 >= 0.5
CONF_COVERAGE_BONUS      = 0.05        # name coverage complete
CONF_CEIL                = 0.60
CONF_CEIL_DIRECTIONAL    = 0.45
CONF_BANDS               = tentative < 0.40 <= moderate < 0.55 <= firm
TIER_MULT                = {T1: 1.0, T2: 0.8, T3: 0.5}   # tier = XS quintiles of mean total contract volume over min(20,H): top 20% / next 40% / rest
FRESH_PENALTY            = 0.5         # any contributing evidence outside its life
EVENT_CONTAM_MULT        = 0.6         # directional card with event <= 2 sessions out
CROWD_MULT_LONG          = 0.5         # C-fire on a LONG card
M_GEX_CAUTION_LONG       = 0.75        # ONLY gex effect: qualified LONG + verdict == "caution"
R_MIN                    = 250
BOARD_N                  = 6
EVENT_BOARD_N            = 4
RISK_BOARD_N             = 4
NO_SIGNAL_R              = 100         # eligible & R < 100 (or NEUTRAL) => NO_SIGNAL
ELIGIBILITY_GATE         = 0.60        # eligible/present below => DEGRADED/ELIGIBILITY_COLLAPSE (per-name quality)
SOURCE_COVERAGE_GATE     = 0.90        # (present ∩ universe)/universe below => INSUFFICIENT_COVERAGE (board-level; B2, SEPARATE from ELIGIBILITY_GATE — see §1a)
EVENT_MIN_NAMES          = 5           # XS event family needs >= 5 event names
EVENT_WINDOW_DAYS        = 45          # event in (S, S+45d]
HIST_EVENT_ACTIVATION    = 3           # same-name events before history_mode may change (model_version bump)
BLEND_XS                 = 0.5
BLEND_LONG               = 0.5
FRESH_LIVES_SESSIONS     = {Q_oi: 3, D_salience: 3, Q_skew: 3, V: 5, P: 1, C_0DTE: 0(current), E: event_close}
ATM_BAND                 = 0.05        # |K/spot - 1| <= 5%
ATM_DTE                  = [7, 60]
ATM_N_CONTRACTS          = 6           # nearest-ATM contracts averaged
TERM_FRONT_DTE           = [7, 45]
TERM_BACK_DTE            = [60, 120]
SKEW_PUT_DELTA           = [-0.35, -0.15]
SKEW_CALL_DELTA          = [0.15, 0.35]
SD_DTE                   = 1.5         # same-day/0DTE bucket
C1_TH = 0.90 ; C2_IV_TH = 0.95 ; C2_EXT = 0.98 ; C3_D1 = 0.95 ; C3_D3 = 0.5 ; C3_V2 = 0.90
DTE_BUCKETS              = {0-7, 8-30, 31-90, >90}
MONEYNESS_BUCKETS        = {<=0.95, 0.95-1.05, >=1.05}
D1_PERSIST_TH            = 0.8 ; D1_PERSIST_WINDOW = 10
DOI_CLAMP                = 3.0         # z clamped to [-3,3]/3
```

## 4. Feature semantics (v1.2 — see AD-1 handoff §5.3 for prose law)

- `d1`, `d3`, `D_salience`: UNSIGNED salience. Zero direction meaning.
- `Q_oi = d2`: contract-matched (strike_ticker join, expiry > D-measurement basis, per-contract
  positive ΔOI on each side) robust z of r = (callΔOI − putΔOI)/(callΔOI + putΔOI + ε) over
  min(60, available) history, floor 10; clamp ±3 → /3. Unsigned positioning HYPOTHESIS; never
  "observed buying/selling".
- `Q_skew`: robust z of `delta_skew_t = skew_t − skew_{t−1}` (skew = (25Δput IV − 25Δcall IV)/ATM IV,
  7–60 DTE) over min(20, available) prior delta-skew observations, floor 8; `Q_skew = −clamp(z,±3)/3`.
  CHANGE, never level.
- `Q_flow`: ABSENT while `signing_gate.direction_reliable == false`. Structural — no code path
  may compute it (activation = new model_version + review).
- Direction: `LONG = Q_oi ≥ +0.50 ∧ Q_skew ≥ +0.50 ∧ D_salience ≥ 0.60`; SHORT mirrored.
  Zero-authority list (may never originate/strengthen direction): d1, d3, raw volume, premium,
  volume/OI, tick-rule flow, GEX, gex_confirm_verdict, walls/flip, 0DTE share, event premium.
- Fallback routing: |F_V| ≥ 0.60 or |F_E| ≥ 0.50 → VOLATILITY; C-fire → RISK_ONLY; else
  NEUTRAL → reported as NO_SIGNAL when R < 100.
- `F_V = mean(s_v1, s_v2, s_v3)` (present members); v1 ATM-IV percentile is longitudinal-only;
  v2 = (ATM IV − RV)/RV, RV from summary-spot log returns over min(20, H−1), floor 10, XS-ranked;
  v3 term slope blended (0.5 XS tier-peers + 0.5 longitudinal).
- `F_E` (cross-sectional mode ONLY at AD-1): needs ≥5 event names; `0.6·(2·p_xs_event − 1) +
  0.4·(2·p_long_iv − 1)` clamped. `history_mode = "cross_sectional"`;
  `event_premium_state ∈ {LOW, NORMAL, HIGH}` (LOW: p_xs ≤ 0.25; HIGH: p_xs ≥ 0.75; else NORMAL).
  Forbidden vocabulary before historical activation: "underpriced/overpriced event move",
  "historical move says …".
- C family: c1 = XS rank of 0DTE volume share (≥0.90 fires); c2 = v1 ≥ 0.95 AND spot ≥ 0.98×
  max spot over min(20,H) (floor 10); c3 = d1 ≥ 0.95 ∧ d3 ≥ 0.5 ∧ v2 ≥ 0.90. Severity =
  max(fired inputs).
  - Cross-sectional percentile convention (`percentile_xs`, crowding-defect ruling,
    2026-08-18, `MODEL_VERSION` unchanged at v1.2 — this is a primitive-correctness fix,
    not a semantic model revision): MIDRANK ties — `p = (count_strictly_less + 0.5·count_equal) / n`. A
    member of a tied block ranks at the block's MIDPOINT, never the top of the block.
    Applies to every `percentile_xs` caller (c1, v2, v3-XS-half, event F_E); does NOT
    apply to `percentile_long` (its histories are proven non-degenerate — changing it
    would perturb frozen v1/d1 longitudinal semantics, out of scope this wave).
  - `sd_share` (c1's input) requires a nonzero same-day (≤`SD_DTE`) volume sum: an empty
    ≤1.5-DTE slice OR a zero-volume slice both resolve `sd_share = None`, not `0.0` — a
    literal same-day share of exactly zero is definitionally "no same-day tape", not
    same-day crowding. `c1` is then the midrank percentile over the remaining FINITE
    `sd_share` members only (peers with `sd_share = None` are excluded from the
    cross-section entirely, same as any other missing peer value); with fewer than
    `MIN_HISTORY` (10) finite members, `c1 = None` universe-wide — honest family
    absence, not a fired leg. Ruling note: a member of a tied block ranks at the
    block's midpoint, so a degenerate-mass block (e.g. a session where most names
    carry `sd_share = 0.0`, formerly ranked at the block's top under plain `<=`
    comparison) can no longer self-certify as extreme.
- `evidence_strength`: directional = clamp01(0.70·mean(|Q_oi|,|Q_skew|) + 0.30·D_salience);
  VOLATILITY = |F_E| if E present else |F_V| (evidence EXTREMITY); RISK_ONLY = C severity.
- `evidence_confidence = min(ceil, 0.30 + 0.10·[d3 ≥ 0.5] + 0.05·[coverage complete])`;
  ceil = 0.45 directional / 0.60 otherwise. Bands per CONF_BANDS; display words only.
- `M_ad = tier × fresh × event × crowd × M_gex`. Prophet multiplier DOES NOT EXIST (=1.0).
- `research_priority_score R = round(1000 · evidence_strength · evidence_confidence · M_ad)`.
- Boards: opportunities = direction ∈ {LONG, SHORT, VOLATILITY} ∧ R ≥ 250, sort (−R,
  −evidence_confidence, −tier_metric, symbol), cap 6 with overflow count; event board ≤ 4 by
  |F_E|; risk board ≤ 4 by severity; `no_signal_exemplar` = highest-tier-metric eligible
  coverage-complete name with R < 100.
- Market-implied move: 5-session horizon `ATM_IV·√(5/252)`; next-session `ATM_IV·√(1/252)`;
  event horizon per E-family front-expiry math; else null. Label: "Market-implied movement
  range" — never target/forecast.
- Horizons: LONG/SHORT and non-event VOLATILITY `"next_5_sessions"`; event VOLATILITY
  `"through_event_close"`; RISK_ONLY/0DTE `"next_session"` (later named clock wins).
- Trigger/invalidation: deterministic templates from Q/V/E/C state exactly per AD-1 handoff
  §5.3 (LONG/SHORT trigger = same-sign ∧ |Q| ≥ 0.50 next settled session; invalidation =
  agreement lost ∨ |Q| < 0.25 ∨ source stale/degraded). Closed vocabulary; no LLM.
- `fresh_until` (B3 — evidence-derived freshness, binding): the MINIMUM lawful expiry
  over the card's ACTUAL contribution set — every evidence input that entered `state`
  (direction/route classification), `evidence_strength`, `evidence_confidence`, or
  `M_ad`. Never derived from direction alone. Session-count lives (`FRESH_LIVES_SESSIONS`,
  §3) convert to real NYSE-session dates; the E-family life (`event_close`) is an actual
  calendar date, combined with everything else via `min()`.
  - LONG/SHORT: Q_oi(3) + Q_skew(3) + D_salience(3) always (the direction law requires
    all three present) `+` P/GEX-mechanics(1) when `M_gex ≠ 1.0` (a qualified LONG under
    caution) `+` the fired crowd leg's own life when a crowd multiplier cut this LONG's
    actionability. A qualified LONG with `M_gex=0.75` -> `fresh_until` = next session
    (life 1 wins the min). A LONG cut by the crowd multiplier where the firing leg is
    same-day `c1` -> current-session expiry (life 0).
  - Crowd leg lives (used for RISK_ONLY too, always crowd-fired by construction — the
    only route to RISK_ONLY): `c1` (same-day/0DTE) = 0; `c2` (V(5) + spot-history(5)) =
    5; `c3` (min(D_salience(3), V(5))) = 3. Multiple fired legs -> the MIN across them.
  - VOLATILITY: event-driven (F_E contributed) -> the event-close date, refined by
    `min()` against D_salience(3) when the confidence d3 persist-bonus also applied;
    V-driven non-event VOLATILITY (F_V used instead) -> V(5), same d3 refinement.
  - The confidence d3 persist-bonus (`evidence_confidence`'s `[d3 ≥ 0.5]` term) is
    ITSELF salience evidence (life 3) and folds into every direction's contribution set
    — a no-op for LONG/SHORT (D_salience(3) is already unconditionally present there).
  - NEUTRAL (no lawful positive claim): life 0 -> `fresh_until` = S.
  - Display-only background (absent families, the Prophet chip) never shortens —
    neither ever enters the contribution set; there is no parameter for either in the
    freshness computation (structural, not merely untested).

## 5. Output schema (`site/options_intel_brief.json`)

Header (all required):

```text
schema                    "options.intel_brief/v1"
model_version             "intel_brief_heuristic/v1.2"
as_of_session             settled session S (YYYY-MM-DD)
oi_counted_date           D (YYYY-MM-DD)
pending_session           newer unsettled chain session | null
pending_reason            "OI_NOT_YET_SETTLED" | null
built_at_utc              ISO-8601 (provenance only; excluded from receipt)
source_watermarks         {chains_session_S, chains_session_D, summaries_max_session,
                           events_loaded(bool), prophet_asof|null, signing_gate_asof}
input_receipts[]          {logical_source, path, asof, sha256, state} (B1: includes the
                          gex_summary_manifest/gex_confirm_manifest aggregate-root entries)
eligibility               {present, eligible, insufficient_history, insufficient_coverage,
                          universe_count, source_coverage_pct}   (B2, last two)
board_state               "OK" | "NO_SIGNAL" | "INSUFFICIENT_COVERAGE" | "STALE_SOURCE" | "DEGRADED"
board_reason              null | "ELIGIBILITY_COLLAPSE" | "MIXED_VINTAGE" | "NO_SETTLED_OI_PAIR" | ...
source_manifest           (B1) {gex_summary, gex_confirm} — each domain:
                          {root: sha256|null, member_count: int, files: {path: sha256}}
                          sorted by path; root = sha256(canonical_json(sorted(files.items())));
                          the two roots are ALSO folded into input_receipts above (that is
                          what actually binds them into receipt_id, not this field itself)
receipt_id                sha256(canonical_json({schema, model_version, as_of_session,
                          oi_counted_date, source_watermarks, sorted(input_receipts)}))
config_hash               sha256(canonical_json(CONFIG))
```

Card (opportunities[], risk_warnings[]; event_board[] uses the §4 event schema):

```text
signal_id                 deterministic: "adib:v1.2:{as_of_session}:{symbol}"
symbol, canonical_instrument_id
direction                 LONG | SHORT | VOLATILITY | RISK_ONLY   (NEUTRAL never ranked)
display_state_en/zh       "Upside evidence" / "Downside evidence" / "Volatility" / "Risk / crowding" (+zh)
horizon                   next_5_sessions | through_event_close | next_session
evidence_strength         [0,1]
evidence_confidence       [0,1] + band word
research_priority_score   R (int)
why_now[]                 deterministic strings (strongest evidence facts, closed vocabulary)
evidence[]                {name, value, history_n, observed_or_inferred}
contradictions[]          deterministic
mechanics_context         {gex_confirm_verdict|null, gamma_regime|null, flip_proximity|null}
crowding                  {fired[], severity} | null
event                     {event_date, history_mode, event_premium_state, ...} | null
market_implied_move_pct   float | null  (+ horizon basis)
trigger_watch             deterministic string (what would confirm)
invalidation_watch        deterministic string (what would change the read)
fresh_until               YYYY-MM-DD — evidence-derived per the card's ACTUAL contribution
                          set (B3, §4), never derived from direction alone
source_state              ok | degraded-note
prophet_state             EXTENDED | ALREADY_OPEN | NOT_READY | READY | OTHER | UNAVAILABLE
prophet_asof              date | null
asymmetry_score           null            asymmetry_state "UNCALIBRATED"
probability_up            null            probability_down null
expected_edge_bps         null
supersedes_signal_id      null            corrected_at null      (AD-2 placeholders)
board_rank                 (B5) int >=1 — 1-based position in the full R>=R_MIN sorted
                          eligible list (BEFORE the board's own cap slice). Present on
                          opportunities[] (1..BOARD_N, contiguous) AND directional_watch[]
                          (>BOARD_N, real ordinals, gaps expected — never renumbered).
                          On event_board[]/risk_warnings[] rows this is instead a
                          CROSS-REFERENCE: the row's rank on the emitted (top-BOARD_N)
                          opportunities board if the same symbol is also on it, else null
                          — never the row's own (possibly >BOARD_N) eligible-list rank.
```

## 5a. B5 — directional watch, event/risk overflow counts, no-signal reason (additive)

Nine fields, every one a projection of state the engine already computes — no new
score, threshold, cap, sort, or Prophet effect. The UI performs no sorting, filtering,
or re-ranking of any array below; each is emitted in its authoritative order and
consumed as-is.

```text
opportunities[].board_rank            see §5 card schema above (1..BOARD_N, contiguous)
directional_watch[]                   list[card] — members of the SAME sorted eligible
                                       list used by opportunities, at positions >
                                       BOARD_N, whose direction in {LONG, SHORT}, in
                                       that list's order. Same card shape + strip() as
                                       the other boards. Emission capped at the
                                       EXISTING CONFIG["BOARD_N"] (6) — no new
                                       constant. board_rank on these rows is >6 and
                                       non-contiguous by construction (the point).
directional_watch_overflow            int >=0 — qualifying below-cap LONG/SHORT
                                       members beyond the <=BOARD_N emitted above.
directional_qualified_count           int >=0 — total LONG/SHORT members of the WHOLE
                                       R>=R_MIN eligible set, cap-independent (i.e. not
                                       limited to the below-cut remainder). Sole input
                                       to a "no directional hypothesis qualified today"
                                       reading — the UI performs no counting.
event_board[].board_rank              see §5 card schema above (cross-reference; null
                                       unless the symbol is also on the emitted
                                       opportunities board)
risk_warnings[].board_rank            as event_board[].board_rank
event_board_overflow                  int >=0 — event-eligible members beyond the
                                       existing EVENT_BOARD_N (4) cap.
risk_board_overflow                   int >=0 — risk-eligible members beyond the
                                       existing RISK_BOARD_N (4) cap.
no_signal_exemplar.no_signal_reason   {en, zh} — deterministic 3-entry closed
                                       vocabulary keyed purely on the exemplar's own
                                       Q_oi/Q_skew leg state (same two readings + the
                                       same Q_TH gate the direction law itself uses,
                                       never a new threshold):
                                         both active, opposite sign -> "the two
                                           readings disagree and activity is normal"
                                         exactly one active                -> "only one
                                           reading moved and activity is normal"
                                         neither active (or both active, same sign)
                                           -> "both readings are inside their normal
                                           range" (default)
                                       Producer-side so the UI stays dumb; null only
                                       when no_signal_exemplar itself is null.
```

All four empty-header builders (`_degraded_payload`/`_stale_payload`/
`_insufficient_coverage_payload`/MIXED_VINTAGE) emit these nine fields at their empty
defaults (`[]`/`0`/`0`) — the fields are always present, never absent-by-branch.

Prophet mapping (B4, display only — reads BOTH domains of `site/prophet/index.json`;
never affects any score):

- **plans[] domain** (`entry_status`/`lifecycle_state`/`closed`): `hold`/`partial` →
  ALREADY_OPEN, but ONLY while the plan is still open (`closed` False) — a closed
  hold/partial plan is a lawful-but-unmapped record → OTHER. `entry_status` `None` →
  ALREADY_OPEN only for an open (`closed` False) `entered` plan; any other `None`-status
  record → OTHER. `bounce_wait` → NOT_READY. `buy_now` → READY. `extended`/`topping` →
  EXTENDED (these last three resolve unconditionally — the open-condition above is
  stated only for the hold/partial and `None`-status cases).
- **intake.receipts.groups domain** (bucket `reason`, `names[].ticker`): `ran_too_far`
  (and any `extended`/`topping` bucket) → EXTENDED; `already_open` → ALREADY_OPEN;
  `not_ready`/`wait_pullback`/`bounce_wait` → NOT_READY; `buy_now` → READY;
  `stood_down`/`conviction_low`/`pointing_down`/`plan_not_built` and any other lawful
  bucket → OTHER.
- **Per-symbol precedence** when the two domains disagree for the same ticker (real
  collisions exist — e.g. BIIB: plans[].entry_status=`bounce_wait` → NOT_READY, but
  receipts.groups reason=`ran_too_far` → EXTENDED):
  `EXTENDED > ALREADY_OPEN > NOT_READY > READY > OTHER > UNAVAILABLE`.
- Absent from BOTH domains → UNAVAILABLE. Never blank.
- OTHER's display words are `"Reviewed · no entry call"` / `"已评估 · 无入场判定"`
  (EXTENDED/ALREADY_OPEN/NOT_READY/READY/UNAVAILABLE words unchanged) — the word table
  itself lives in `scripts/build_options_command.py` (`_AIB_PROPHET_EN`/`_AIB_PROPHET_ZH`,
  outside this packet's OWNED FILES; the enum-level resolution above is complete and
  correct as of this contract, but the downstream word swap for OTHER is a NAMED FOLLOW-UP,
  not yet applied — see the B1-B4 fix's GAPS).

## 6. Authority table

| Quantity | May do | May never do |
|---|---|---|
| D_salience, d1, d3 | raise research priority | carry/imply direction |
| Q_oi, Q_skew | originate LONG/SHORT jointly under the law | act alone; be described as observed buying/selling |
| Q_flow | (absent) | exist while signing gate direction_reliable=false |
| gex_confirm | display context; M_gex 0.75 on qualified LONG under caution | originate/strengthen direction; any positive multiplier; synthetic SHORT inverse |
| F_V, F_E | route VOLATILITY; evidence extremity | equity direction |
| C family | RISK_ONLY route; cut LONG actionability | direction |
| Prophet echo | display chip + prophet_asof | touch strength/confidence/M_ad/R; create/destroy/reorder hypotheses |
| Whole board | order research attention (display tier) | probability/alpha/forecast/trade authority; the word "validated" |

## 7. Writer contract

Atomic write via the house pattern (temp + rename). Semantic no-op: if a rerun produces an
identical `receipt_id` AND identical semantic payload, leave bytes/mtime unchanged and do not
churn git. If the same `as_of_session` later sees different source bytes (pre-AD-2): write the
corrected artifact with its new receipt; git history preserves the prior version; no formal
correction chain is claimed (`supersedes_signal_id`/`corrected_at` stay null placeholders).

## 8. Data-feasibility law (test-enforced)

Every history-dependent CONFIG constant must be satisfiable by ≥60% of names present in the
latest committed session of the real store at test time (`needs_full_checkout`-marked test).
A spec change demanding more depth than the canonical producer supplies must fail CI.

## 9. Known limits (recorded; out of scope this wave)

- `d1`'s max-over-~12-discrete-bucket-ranks construction (§4) inflates: under exchangeability
  `P(max over ~12 roughly-independent percentile ranks ≥ 0.95) ≈ 0.60` (debugger-verified,
  2026-08-18), i.e. `d1 ≥ 0.95` fires far more often than a single-percentile 5% base rate
  would suggest. Recorded as a v1.3 candidate (tighten the bucket-rank aggregation or the
  `D1_PERSIST_TH`/`C3_D1` thresholds against the inflated distribution); NOT touched by the
  crowding-defect fix above — `d1`/`d3` aggregation is explicitly out of scope for that ruling.
