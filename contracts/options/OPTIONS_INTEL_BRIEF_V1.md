# Contract — `options.intel_brief/v1` (`intel_brief_heuristic/v1.2`)

Code-facing executable contract for the Daily EOD Options Intelligence Brief.
Sources of authority, in order: the program masterplan
(`research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md`),
`DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION`,
`DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT`, and the amended AD-1 handoff §5.3 (v1.2)
(`research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md`),
plus the AD-1 runtime source-clock ruling (settled vs pending, 2026-08-18) transcribed
here. Implementation is transcription: any divergence between code and this contract is
a defect in exactly one of them and must be returned, never silently adapted.

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

## 2. Inputs (read-only; existing loaders only)

| # | Input | Path | Used for | Clock |
|---|---|---|---|---|
| 1 | EOD chains | `data/polygon_gex/chains/{session}.parquet` (underlying, strike_ticker, expiry, K, T, is_call, oi, iv, gamma, delta, volume, spot, asof) | eligibility, V family, salience buckets, Q_skew, Q_oi (S→D pair), C family, market-implied move | S (and D for OI only) |
| 2 | GEX summaries | `data/polygon_gex/summary_{SYM}.parquet` (spot history, gamma_flip, …) | RV for v2, spot-extension c2, flip proximity display | rows ≤ S only |
| 3 | gex_confirm | `site/gex/{SYM}.json` via `engine.gex_confirm.assess(..., direction="up")` | mechanics context + `M_gex` | must bind to S else absent |
| 4 | Earnings calendar | `data/earnings/earnings.parquet` (`next_date` per ticker) | E family event window (S, S+45d] | forward-known |
| 5 | Prophet display echo | `site/prophet/index.json` (`plans[].asset`, `entry_status`, index `asof`) | display-only `prophet_state` chip | may be newer than S; `prophet_asof` disclosed |
| 6 | Flow signing gate | `data/options_flow/signing_gate.json` | proves `Q_flow` must stay ABSENT while `direction_reliable == false` | current |

No collector is invoked; no network; missing optional input → family absent; missing core
input (chains for the pair) → `STALE_SOURCE`/`DEGRADED` per §5.

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
ELIGIBILITY_GATE         = 0.60        # eligible/present below => DEGRADED/ELIGIBILITY_COLLAPSE
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
input_receipts[]          {logical_source, path, asof, sha256, state}
eligibility               {present, eligible, insufficient_history, insufficient_coverage}
board_state               "OK" | "NO_SIGNAL" | "INSUFFICIENT_COVERAGE" | "STALE_SOURCE" | "DEGRADED"
board_reason              null | "ELIGIBILITY_COLLAPSE" | "MIXED_VINTAGE" | "NO_SETTLED_OI_PAIR" | ...
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
fresh_until               YYYY-MM-DD (NYSE-session arithmetic)
source_state              ok | degraded-note
prophet_state             EXTENDED | ALREADY_OPEN | NOT_READY | READY | OTHER | UNAVAILABLE
prophet_asof              date | null
asymmetry_score           null            asymmetry_state "UNCALIBRATED"
probability_up            null            probability_down null
expected_edge_bps         null
supersedes_signal_id      null            corrected_at null      (AD-2 placeholders)
```

Prophet `entry_status` mapping (display only): hold/partial → ALREADY_OPEN; bounce_wait →
NOT_READY; buy_now → READY; extension states (`ran_too_far`/extension flags where present) →
EXTENDED; other lawful → OTHER; missing → UNAVAILABLE. Never blank; never affects any score.

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
