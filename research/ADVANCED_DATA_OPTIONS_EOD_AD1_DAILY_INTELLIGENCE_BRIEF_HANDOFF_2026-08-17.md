# AD-1 Implementation Handoff — Daily EOD Options Intelligence Brief
## Advanced Data: Options EOD + Off-Exchange Intelligence OS · 2026-08-17

**Wave:** AD-1 (first implementation slice; authorized only after Chairman review of AD-0)
**Evidence base:** `research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md` (all path/clock/liveness claims below are proven there; section references `AD0:§n`)
**Masterplan:** `research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md` (in-repo, committed with the Sol-review amendments)
**Stop condition:** production acceptance packet (§7) returned for review. AD-2 does not begin.

---

## §0 Acceptance gates (inline, binding — "not done unless")

1. A fresh end-to-end happy path runs with **zero manual workarounds**: nightly/closing-bell lane → brief JSON → served board, on a real current session, with no hand-run steps.
2. The proof's ranked signal symbol is **selected by the production algorithm** — never hard-coded, never cherry-picked after the fact.
3. A **liquid, complete-data symbol shows `NO_SIGNAL`** on the same board, same session.
4. A **degraded/withheld case** is demonstrated (real or induced in staging by withholding an input artifact — never by faking data in production).
5. Per-viewport **visual crops (light + dark + zh)** of the board are posted in the PR body.
6. UI and machine projection are **byte-derived from the same artifact** (parity test §6.11).
7. Front-facing copy passes house language law: no "falsifier/refuted/validated" vocabulary (`scripts/check_validated_claims.py` is CI-enforced); bilingual EN/ZH; no translated text in `title=` attributes.
8. Design: the board is a flagship user-facing surface — design-spec-first per the Design lane (doctrine `docs/DESIGN_DOCTRINE.md`, constitution `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`, specimen `mockups/design_system/specimen.html`); glance tier = state + plain-word stance under word budgets; technicals demoted to hover/detail.
9. No first-pass self-merge of the flagship UI by a child builder — the commissioning session reviews the PR + visual artifact, then owns the normal merge chain.

---

## §1 Exact outcome (one sentence)

> After every completed US market session, the Options Workspace's first viewport opens with a **Daily EOD Options Intelligence Brief**: a machine-built, receipt-backed board showing the market derivatives regime, up to N ranked anticipation/event-pricing opportunity cards each carrying direction-or-type, horizon, asymmetry, confidence, actionability, why-now evidence families, contradiction, trigger, invalidation-as-watch-condition, expected move, fresh-until, source state, and Prophet state — plus explicit `NO_SIGNAL` / degraded states — so a user can answer "what matters now and what would make it wrong" in under one minute without opening a raw chain.

## §2 Exact files allowed

**New files (owned by AD-1):**
- `engine/options_intel_brief.py` — feature computation + composer (families §4.2; contract §5).
- `scripts/build_options_intel_brief.py` — producer CLI; reads §4 inputs, writes the §5 artifacts; no network calls.
- `contracts/options/OPTIONS_INTEL_BRIEF_V1.md` — the frozen schema/contract document.
- `tests/test_options_intel_brief.py` (+ `tests/test_options_intel_brief_js.py` if board JS warrants it).

**Bounded edits (smallest possible diff, no drive-by changes):**
- `templates/options.html.j2` — insert the Brief board at the top of the Daily Brief tab ONLY; no other section may change.
- `.github/workflows/daily.yml` — one step invoking the producer after the collect/engine phase (daily runs 7 days — this is what closes the weekend settle gap, AD0:§1.1-1).
- `.github/workflows/closing-bell.yml` — one step so the T+0 evening board exists before the nightly.
- `config/synapse.yml` — one registry entry for the new artifact (producer/consumer declaration, `tier: display`).

**Explicitly NOT granted:** broad directory authority. If implementation reveals a needed file outside this list, stop and return the gap — do not widen scope in-flight.

## §3 Exact files forbidden

- Collectors and stores: `collectors/*` (all), `scripts/collect.py`, `scripts/build_polygon_gex.py`, `data/*` write paths other than those the producer owns under §5.
- Existing options builders/engines: `engine/options_flow.py`, `scripts/build_options_flow.py`, `scripts/build_gex_board.py`, `engine/gex_confirm.py`, `scripts/build_darkpool_desk.py`, `engine/darkpool_*`, `scripts/build_options_command.py` (the Brief is additive; the Workspace's existing modules are not rewritten), `scripts/build_options_skew.py`, `build_options_ivspread.py`, `build_options_dislocation.py`, `scripts/build_options_prophet.py`.
- Prophet planes: `engine/us_prophet_fusion.py`, `engine/us_board_rank.py`, `engine/prophet_bridge.py`, `scripts/build_prophet.py`, `scripts/grade_us_board.py` — **no new family, no delta, no score logic** (AD-5/AD-7 territory).
- Neural Web: `engine/neuralweb/*`; Sector: `engine/sector*`; Terminal bridge: `scripts/export_signal_contracts.py`.
- Sparse-selector / W1A estate: `engine/options_sparse_selector.py`, `engine/options_market_memory_local_*`, `ops/launchd/*` (all units; nothing is armed or installed in AD-1).
- Episode/outcome ledgers: `engine/options_signal_episode.py`, `scripts/build_options_signal_*` (adapter work is AD-2/AD-6).
- Shared chrome/nav/auth: `templates/_site_nav.html.j2`, `templates/_navlinks.html.j2`, `app/*`.

## §4 Exact source inputs

All inputs are read through their **existing loaders**; AD-1 adds zero ingestion.

| # | Input | Path / schema | Source clock | PIT rule | Coverage threshold | Degraded behavior |
|---|---|---|---|---|---|---|
| 1 | EOD option chains | `data/polygon_gex/chains/{session}.parquet` (per-contract: OI, IV, gamma/delta, volume; session-stamped) | collected ~18:30 ET T+0 (`daily.yml`); OI is next-morning PIT | **no same-day OI**: OI for session S is usable only from S+1 ("positions counted" convention, AD0:§6.2); ΔOI vs immediately prior distinct snapshot day | brief publishes ranked cards only if session chain files cover ≥90% of the Workspace universe (408 names, AD0:§1); below → board_state `INSUFFICIENT_COVERAGE`, cards withheld | latest session chains absent >36h after session close → board_state `STALE_SOURCE`, cards withheld, stamp shows last good session |
| 2 | GEX summaries | `data/polygon_gex/summary_{SYM}.parquet` | as #1 | as #1 | n/a (per-name optional) | missing name → that name's positioning family contributes nothing (family absent, not zero-filled) |
| 3 | Flow accrual | `data/options_flow/summary_{SYM}.parquet` | massive.com EOD aggs | direction is tick-rule **inferred** (~77–83%) — may only feed hedged evidence-family text, never a card's direction on its own (AD0:§6.3) | n/a | missing → demand family absent for that name |
| 4 | Vol-surface display stores | `data/options_ivspread/`, `data/options_skew/` (as read by their live builders) | closing-bell EOD | same-session lawful | n/a | absent → volatility families reduced; card confidence caps lower |
| 5 | Underlying prices / realized vol | the exact price loaders already used by `scripts/build_options_flow.py` / `scripts/build_gex_board.py` (pin the function names in `contracts/options/OPTIONS_INTEL_BRIEF_V1.md` during implementation — reuse, never re-ingest) | EOD T+0 | same-session lawful | n/a | absent → implied-vs-realized family off |
| 6 | Event calendar | `data/earnings/earnings.parquet`, `data/event_windows/forward_log.jsonl` | calendar (known in advance) | forward-known; event-conditioning lawful same-session | n/a | absent → event families off; affected cards carry `null_reason: EVENT_STATE_UNKNOWN`; no event-pricing board section |
| 7 | Prophet state (display echo only) | `site/prophet/index.json` (`prophet.index/v1`, `asof`, plans) | nightly EOD | display-only echo; **no delta computed, no score read into ranking** | n/a | absent/stale → card Prophet field shows "unavailable (as of <date>)" — never blank |

## §5 Exact output contract

**Machine projection:** `site/options_intel_brief.json`, schema `options.intel_brief/v1` (auth-gated in production like sibling data JSONs — AD0:§1; the served page carries the board server-rendered).

Header (all required): `schema`, `as_of_session`, `built_at_utc`, `source_watermarks{chains_session, oi_counted_date, flow_session, surface_session, events_loaded, prophet_asof}`, `coverage{names_present, names_universe, pct}`, `board_state ∈ {OK, NO_SIGNAL, INSUFFICIENT_COVERAGE, STALE_SOURCE, DEGRADED}`, `model_version`, `receipt_id` (hash of input watermarks + model_version — deterministic, §6.10).

`opportunities[]` — each card (field names follow masterplan §6.2 where present; **AD-1P0 additions/nulls**: every card carries `evidence_strength` and `research_priority_score`; `asymmetry_score = null` with `asymmetry_state = "UNCALIBRATED"`, `expected_edge_bps = null`, `probability_up = null`, `probability_down = null` until AD-6; `confidence` renders as "Evidence confidence"):
`signal_id`, `canonical_instrument_id` (via `engine/stock_identity/`), `as_of_session`, `direction ∈ {LONG, SHORT, VOLATILITY, RISK_ONLY, NEUTRAL}`, `horizon`, `asymmetry_score`, `confidence`, `actionability`, `why_now` (plain-word), `evidence_family_contributions[]` (family name + capped contribution + observed-vs-inferred tag), `contradictions[]`, `trigger`, `invalidation` (front-facing copy = "what would change this read" watch-condition phrasing — operator 2026-07-27 language law), `expected_move_range`, `fresh_until`, `source_state`, `prophet_state`, `null_reason` (null on ranked cards), `what_would_make_this_wrong`.

**Direction law (binding — `DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT`, CEO review on #5830):** the architectural vocabulary includes `SHORT`; the old AVOID-not-SHORT vocabulary ban is NOT carried into this contract. The protection is evidence-gated instead: machine direction requires the two independent hypothesis legs plus material salience (`Q_oi` + `Q_skew` + `D_salience`, §5.3 v1.2 direction qualification law); no raw call/put volume, premium, volume/OI, tick-rule-signed flow, GEX, `gex_confirm_verdict`, gamma mechanics, 0DTE share, or event premium may originate `LONG` **or** `SHORT`; direction that fails qualification abstains or expresses as `RISK_ONLY`/`NEUTRAL`. With today's entitled EOD sources the implementation may lawfully emit **zero** SHORT signals — an empty SHORT lane is a correct output, not a defect. **Machine vocabulary vs display copy:** `LONG`/`SHORT` are the machine enum for *directional research hypotheses*; served copy renders them as "upside evidence"/"downside evidence" framing with the hypothesis nature explicit, never as trade imperatives ("buy"/"short"/"sell"), and never describes any field as observed buying or selling (no aggressor/open-close evidence exists in the entitled sources).

`event_board[]` — event candidates where implied move and event-conditioned historical distribution diverge: `symbol, event_type, event_date, implied_move, conditioned_move_reference, divergence, direction=VOLATILITY, fresh_until`.

`risk_warnings[]` — crowding/extension/fragility contexts (RISK_ONLY cards).

`no_signal_exemplar` — required whenever `board_state=OK`: one liquid, coverage-complete symbol with `NO_SIGNAL` and its `null_reason` (§4.3 law below).

**UI:** one new board at the top of the Daily Brief tab of `options.html`, rendering exclusively from this artifact (regime strip may continue to come from the existing tiles — the Brief adds the opportunity/event/risk/no-signal layer, it does not duplicate the tiles). Raw chain detail stays in existing tabs (drill-down, not first viewport).

### §5.1 Feature families (only proven fields — AD0:§4)
ATM IV; IV percentile conditioned by symbol/liquidity tier/regime; skew; term structure; implied-vs-realized; implied-vs-event-conditioned move; OI concentration + ΔOI (lawful clock only); DTE/moneyness/liquidity/event-conditioned volume anomalies; strike/expiry concentration; multi-session persistence. Family caps per masterplan §8.3 (correlated fields never become independent votes). All scoring mappings without outcome evidence are labeled `heuristic` in the artifact and cap `confidence` accordingly (masterplan §8.2). Off-exchange families are **excluded** (AD-3 owns them; nothing in the current architecture forces them into AD-1).

### §5.2 No-signal law
`NO_SIGNAL` on liquid complete-data names is a first-class output; the board is allowed to be empty (including a session where **every** complete-data name yields `NO_SIGNAL`); there is no activity quota; raw-volume leaders are never backfilled into the opportunities list to make it look active.

### §5.3 Frozen deterministic display-tier scoring and ranking (`intel_brief_heuristic/v1.2`)

This section is the complete initial method. **v1.1 → v1.2 (AD-1P0 semantic-authority freeze, Sol ruling 2026-08-18, `DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION`):** the data-feasibility laws of v1.1 are accepted and preserved (eligibility floors, min(W,H) windows, `history_n` disclosure, blended conditioning, non-vacuity gate, state distinctions, no activity quota, determinism); what changes is **semantic authority**. v1.1 mixed salience, directional hypotheses, dealer mechanics, event premium, and Prophet context into one score with stronger semantics than the source contracts support. v1.2 separates them under the authority ladder:

```text
OBSERVED FACT → QUALIFIED INFERENCE → DISPLAY-TIER RESEARCH-PRIORITY HYPOTHESIS
→ PROSPECTIVE OUTCOME MEASUREMENT → CALIBRATED FORECAST/ASYMMETRY → BOUNDED PROPHET AUTHORITY
```

AD-1 is the third rung only. Its outputs order research attention; they are not probabilities, alpha, forecasts, Prophet inputs, gates, sizes, or trade authority; no output may be described with the word "validated". Predictive/calibrated promotion remains AD-6/AD-7. `LONG`/`SHORT` cards are **directional research hypotheses**: no field lacking actual aggressor/open-close evidence may be described as observed buying or selling, and front-facing copy uses "upside evidence"/"downside evidence" phrasing, never trade imperatives. All constants below are frozen in one `CONFIG` dict in `engine/options_intel_brief.py`; `tests/test_options_intel_brief.py` pins them; any change is a new `model_version`. The implementation worker has **no scoring, weighting, threshold, or ranking decisions to make** — divergence is a spec deviation to be returned, not resolved in code. Thresholds were NOT tuned to preserve v1.1's signal counts (the directional collapse in §5.4's v1.2 preflight is the intended correction).

**Eligibility (per name, per session S).** A name is *eligible* iff: session chain file present; ≥ 20 quotable contracts after quality exclusions (§6.5); and **H ≥ 10**, where H = number of prior sessions with chain rows for the name in `data/polygon_gex/chains/`. A name failing only the history floor carries `null_reason: INSUFFICIENT_HISTORY`; a name failing contract/coverage rules carries `null_reason: INSUFFICIENT_COVERAGE`. Both are excluded from ranking and are **distinct from `NO_SIGNAL`**, which is reserved for eligible names whose evidence is unremarkable. A name is never made ineligible because a noncritical longitudinal feature lacks depth — the affected feature/family is simply absent for that name.

**Liquidity tiers (from quantities the estate possesses).** Underlying ADV$ is not in the canonical estate; tiers are cross-sectional quintiles of mean total contract volume over the trailing min(20, H) sessions: T1 = top 20%, T2 = next 40%, T3 = rest. Conditioning peer group = tier.

**Conditioning (replaces v1's 252-session own-history percentiles).** Two percentile sources: `p_xs` = rank among same-session tier peers (matched cross-sectional); `p_long` = rank against the name's own available history over the trailing min(W, H) sessions with a floor of 10 observations, where W is the feature's target window (20 unless stated; ΔOI targets 60). Blend: `p = 0.5·p_xs + 0.5·p_long` where both exist; a feature whose only meaningful frame is longitudinal (marked ⟂ below) uses `p_long` alone and is absent below the floor; a level meaningless across names never uses `p_xs`. Every card reports `history_n` per contributing feature so short denominators are visible. **Growth clause:** windows grow automatically toward W as the estate accrues (min(W,H) is self-extending); raising any W target is a `model_version` bump, never a silent edit.

**Feature transforms** (signed surprise `s = 2p − 1` where sign is meaningful):

- Family **V** (volatility): `v1`⟂ ATM IV (mean IV of the ≤6 contracts nearest ATM within ±5% moneyness, 7–60 DTE) — `p_long` only (IV level is not comparable across names); `v2` IV−RV spread = (ATM IV − RV)/RV where RV = annualized std of log returns of the GEX-summary spot series over the trailing min(20, H−1) returns, floor 10 (absent below) — blended; `v3` term slope = (ATM IV 7–45 DTE − ATM IV 60–120 DTE)/ATM IV 60–120 DTE — blended; `v4` skew = (mean IV of −0.35…−0.15Δ puts − mean IV of 0.15…0.35Δ calls)/ATM IV, 7–60 DTE — blended.
- Family **D** (demand): `d1`⟂ volume anomaly inside (DTE bucket {0–7, 8–30, 31–90, >90} × moneyness bucket {≤0.95, 0.95–1.05, ≥1.05 of spot}): today's bucket volume ranked against the same bucket's own min(20, H) history (floor 10); name-level = max bucket percentile, maximizing bucket named on the card; `d2`⟂ ΔOI lean = robust z of today's r = (call ΔOI − put ΔOI)/(call ΔOI + put ΔOI + ε) against its own min(60, H) history (floor 10), where ΔOI is **contract-matched** (contracts present in both sessions, expiry > S, per-contract ΔOI floored at 0) — z = (r − median)/(1.4826·MAD + ε), clamped to [−3,3]/3, lawful clock only (§4.1); `d3`⟂ persistence = share of the last min(10, H) sessions with `d1` ≥ 0.8 (floor 10, else absent).
- Family **P** (mechanics/context ONLY — v1.2): describes AMPLIFICATION / DAMPENING-PINNING / CEILING-SUPPORT / FRAGILITY / MECHANICAL-TRIGGER context; it never selects stock direction. Exposed where available: `p1` strike-concentration HHI of OI (expiries ≤ 90 DTE, blended), gamma regime, `p3` flip proximity = 1 − min(1, |spot − flip| / (spot × ATM IV·√(1/252))), call/put walls, vol-hole state, and `gex_confirm_verdict` (read from the live artifact, never recomputed). **`gex_confirm` authority (engine contract is a long-thesis verifier, `engine/gex_confirm.py`):** `confirm` never creates LONG and never increases directional evidence strength; `caution` never creates SHORT; `caution` may only reduce the actionability of an already-qualified LONG (`M_gex` below); for SHORT hypotheses the long-centric confirmer is display context only until a separately designed symmetric downside mechanic exists. There is no positive GEX multiplier and no synthetic SHORT inverse.
- Family **E** (event premium — REDEFINED for feasibility): the v1 historically-conditioned mispricing ratio needs ≥3 prior same-name events; the estate's depth (~28 sessions) cannot supply it. Until the estate holds ≥3 same-name events (self-activating upgrade, `model_version` bump), E is a **cross-sectional event-premium read**: defined when the earnings calendar (§4.6) shows an event within (S, S+45d] AND ≥5 such names exist that session; `F_E = clamp(0.6·(2·p_xs_event − 1) + 0.4·(2·p_long_iv − 1))` where `p_xs_event` ranks ATM IV among that session's event names and `p_long_iv` is the name's own ATM-IV percentile. Semantics: "event premium unusually high/low vs event peers and own baseline" — explicitly NOT a claim of event mispricing against realized history.
- Family **C** (crowding/extension, risk-only): `c1` same-day (≤1.5 DTE) volume share, `p_xs` among tier peers; `c2` = 1 if (`v1` ≥ 0.95 AND spot ≥ 0.98 × max spot over min(20, H) sessions, floor 10) else 0; `c3` = 1 if (`d1` ≥ 0.95 AND `d3` ≥ 0.5 AND `v2` ≥ 0.9) else 0. C-fire iff `c1 ≥ 0.9` or `c2 = 1` or `c3 = 1`.

**Salience (unsigned; replaces v1.1's signed `F_D`).** `d1` and `d3` measure *unusual activity*, never bullish/bearish: high `d1` = unusual, low = ordinary — never a direction. `D_salience = clamp01(0.65·d1 + 0.35·d3)`, renormalized over present member weights when one is absent (never zero-filled). `D_salience` may raise research priority; it may not determine LONG or SHORT.

**Directional research hypothesis legs (the ONLY two current-source origination legs).**
- `Q_oi = d2` ∈ [−1, +1] (the contract-matched robust-z ΔOI above). Semantics: positive = call-side OI growth dominates; negative = put-side dominates. This is an **unsigned positioning hypothesis** — every open contract has both a buyer and a seller (OIC/OCC mechanics); it is never "observed buying/selling" and never predictive authority (Fodor–Krieger–Doran find predictive information in ΔOI, which motivates the hypothesis leg, not observed aggressor direction).
- `Q_skew` — **skew CHANGE, not level** (absolute equity skew is structurally negative; the house `gex_confirm` contract already uses risk-reversal *change* for the same reason; Xing–Zhang–Zhao motivate smirk-shape information as hypothesis, not observed put demand): `delta_skew_t = skew_t − skew_{t−1}` on the v1.1 skew construction; robust z of `delta_skew_t` against the name's trailing min(20, available) `delta_skew` history, floor **8**; `Q_skew = −clamp(z, −3, +3)/3`. Positive = downside skew flattened unusually (upside-evidence hypothesis); negative = steepened unusually (downside-evidence hypothesis).
- `Q_flow = ABSENT` — structurally reserved while `data/options_flow/signing_gate.json.direction_reliable == false` (currently false, `net_sign_recovery 0.4108`). No fallback; activating it requires a production-ready aggressor/tape gate, a new `model_version`, and explicit review.

**Direction qualification law (supersedes the v1.1 D-law).** Machine direction requires BOTH independent hypotheses AND material activity:

```text
LONG  = Q_oi ≥ +0.50  AND  Q_skew ≥ +0.50  AND  D_salience ≥ 0.60
SHORT = Q_oi ≤ −0.50  AND  Q_skew ≤ −0.50  AND  D_salience ≥ 0.60
```

Zero direction-origination authority (frozen list): `d1`, `d3`, raw call/put volume, premium, volume/OI, tick-rule flow while its gate is false, GEX, `gex_confirm_verdict`, gamma flip/walls, 0DTE share, event premium. If the law fails: strong V/E evidence (|F_V| ≥ 0.6 or |F_E| ≥ 0.5) → `VOLATILITY`; crowding/mechanics fire → `RISK_ONLY`; else `NEUTRAL`/`NO_SIGNAL`. The ±0.50/0.60 thresholds are frozen — they may not be tuned to recover v1.1's signal counts.

**Family scores retained for non-directional lanes.** `F_V = mean(s_v1, s_v2, s_v3)` over present members; `F_E` as defined in the E family (sign = high/low event premium, not equity direction). Both clamped [−1, +1]; absent members excluded, never zero-filled. There is no `F_D` and no `F_P` score in v1.2 — D is salience, P is mechanics context.

**Evidence strength (replaces "asymmetry" — AD-1 has no calibrated payoff distribution).** For qualified LONG/SHORT: `Dir_strength = mean(|Q_oi|, |Q_skew|)`; `evidence_strength = clamp01(0.70·Dir_strength + 0.30·D_salience)`. Cross-sectional event premium adds NO directional strength and receives no "cheap convexity" bonus before historical calibration. For `VOLATILITY`: `evidence_strength = |F_E|` if E present else `|F_V|` — labeled *evidence extremity*, never expected-return edge. For `RISK_ONLY`: the maximum fired crowding/mechanics severity (`max(c1 where ≥0.9, c2, c3)`). Card contract: `asymmetry_score = null`, `asymmetry_state = "UNCALIBRATED"`, `expected_edge_bps = null`, `probability_up = null`, `probability_down = null` at AD-1 (fields kept for forward compatibility; AD-6 earns them). User copy: "Evidence strength" / "Research priority" — never "% probability", "alpha", "expected edge", or "true asymmetry".

**Evidence confidence (non-probabilistic, ceiling-bound).** `evidence_confidence = 0.30 + 0.10·[d3 ≥ 0.5] + 0.05·[coverage complete]`; hard ceiling **0.60**; directional cards built from the current unsigned EOD hypothesis legs cap at **0.45**. Displayed as 3-band words (`tentative` < 0.40 ≤ `moderate` < 0.55 ≤ `firm`), never a percentage; user label is "Evidence confidence". If `firm` is unreachable under current sources, that is lawful — the ceiling is not raised to populate a band.

**Actionability (AD-native only).** `M_ad = tier × fresh × event × crowd × M_gex` with v1.1 values retained: tier T1=1.0/T2=0.8/T3=0.5; fresh = 1.0 if every contributing evidence input is within its life (§ freshness below) else 0.5; event = 0.6 for directional cards with an event ≤ 2 sessions out, else 1.0; crowd = 0.5 on C-fire for LONG cards, else 1.0; `M_gex = 0.75 iff machine_direction == LONG AND gex_confirm_verdict == "caution"`, else 1.00. No multiplier exceeds 1.0; GEX may only reduce LONG actionability; **Prophet contributes zero (`M_prophet = 1.0` always)**; off-exchange contributes zero in AD-1; no machine trade action is produced.

**Horizon contract (research/evaluation window, never a holding-period instruction).** Directional hypothesis and non-event VOLATILITY: `horizon = "next_5_sessions"`. Event VOLATILITY: `horizon = "through_event_close"` using the existing canonical event timing helper (no second event clock). RISK_ONLY/0DTE: `horizon = "next_session"` unless tied to a later named expiry/event, in which case the canonical named clock wins.

**Freshness / `fresh_until`.** `fresh_until = minimum lawful expiry among contributing evidence`, in **NYSE session arithmetic** (never calendar days): `Q_oi`/D-salience 3 sessions; `Q_skew` 3 sessions; V family 5 sessions; P/GEX mechanics 1 session; 0DTE crowding current session only; E family event close. When a required contributing input expires, the card expires/degrades — it is never silently reused as current.

**Trigger and invalidation (deterministic state transitions; no LLM authors them).** LONG/SHORT — trigger-watch: `Q_oi` and `Q_skew` remain same-sign AND |each| ≥ 0.50 on the next lawful settled session; invalidation-watch: sign agreement lost OR |Q_oi| < 0.25 OR |Q_skew| < 0.25 OR a required source becomes stale/degraded. VOLATILITY — trigger: qualifying V/E extremity persists or expands; invalidation: it falls below its card threshold. RISK_ONLY — trigger: the named condition remains active; invalidation: it clears. Display copy describes *what would change the read*; no buy/sell/short-now language.

**Market-implied movement (implied dispersion, never a forecast).** With lawful ATM IV: 5-session horizon → `market_implied_move_pct = ATM_IV·√(5/252)`; next-session → `ATM_IV·√(1/252)`; event horizon → the E-family front-expiry calculation, else null. User label: "Market-implied movement range" — never "price target", "expected return", or "forecast gain/loss".

**Prophet boundary (load-bearing — AD-1 stands alone).** Prophet state is visible user context with **zero rank authority**: it never enters `evidence_strength`, `evidence_confidence`, `M_ad`, or `R`, and no Prophet state creates or destroys an AD hypothesis (the v1.1 `prophet = 0.7` multiplier is REMOVED — it was hidden AD-5-style confluence). Map existing Prophet receipt states for display: extension/ran_too_far → `EXTENDED` ("Prophet: already extended — not a fresh entry", prominently); already_open/hold/partial → `ALREADY_OPEN` ("plan already running"); not_ready/wait_pullback/bounce_wait → `NOT_READY`; other lawful state → mapped as-is; missing → `UNAVAILABLE` (never blank). Same AD inputs + different Prophet echo ⇒ identical machine score/rank, different display context only. The first score-level confluence belongs to AD-5.

**Event board contract (matches the cross-sectional truth).** Before historical activation every event card carries: `symbol, event_type, event_date, atm_iv, event_peer_percentile, own_iv_percentile, event_premium_state ∈ {LOW, NORMAL, HIGH}, history_mode = "cross_sectional", fresh_until`. Display: "Event premium low/elevated versus current event peers". FORBIDDEN before historical activation: "underpriced/overpriced event move", "historical move says X". Once ≥3 lawful prior same-name events exist the producer may additionally expose `history_mode = "historical_conditioned", historical_event_count, historical_abs_move_median, implied_move, implied_vs_history_ratio` — historical *context*, not calibrated mispricing authority; any ranking change from activation is a `model_version` change; AD-6 owns predictive promotion.

**Rank and board composition.** `R = round(1000 · evidence_strength · evidence_confidence · M_ad)` — this is the `research_priority_score`; `R_MIN = 250`. Opportunities board: eligible cards with direction ∈ {LONG, SHORT, VOLATILITY} and `R ≥ 250`, sorted `R` desc, tie-break higher `evidence_confidence`, then higher tier-metric (mean contract volume), then symbol ascending; display at most **6** (overflow count shown, never silently dropped). Event board: up to **4** event cards by `|F_E|` desc. Risk board: up to **4** C-fire names by severity desc. `NEUTRAL` cards are never ranked; an eligible name that is NEUTRAL or below `R < 100` reports `NO_SIGNAL`. `no_signal_exemplar` = the highest-tier-metric eligible, coverage-complete name with `R < 100` (deterministic). No activity quota, no forced minimum board size; a session with zero qualifying opportunity cards is lawful when eligibility is healthy. Prophet display context never changes `R`.

**Eligibility non-vacuity gate (frozen).** The artifact header carries `eligibility{present, eligible, insufficient_history, insufficient_coverage}`. Board state is `OK` only if `eligible / present ≥ 0.60` on the session; below that the board is `DEGRADED` with reason `ELIGIBILITY_COLLAPSE` and cards are withheld — a data-health tripwire, never a signal statement. This gate is measured **before** signal thresholds, so a quiet board (`NO_SIGNAL` everywhere) with healthy eligibility is clearly distinguished from a board that went dark because the data could not support the method. At the amendment head the current production estate measures 95.7% eligible (§5.4), so zero signals, if it occurs, is a threshold outcome, not a data-prerequisite failure.

**Determinism.** No randomness, no wall-clock inputs beyond `as_of_session`; identical inputs reproduce identical JSON (test §6.10); every threshold above appears verbatim in `CONFIG` and in the contract doc.

### §5.4 Data-feasibility census, preflight, and the feasibility law (2026-08-17)

**Feature-readiness census** (read-only, canonical estate at the amendment head, latest session 2026-08-13):

```text
data/polygon_gex/chains/         28 committed session snapshots (2026-06-15 → 2026-08-13), 4,418,705 contract rows
per-name session depth           min 1 · p25 26 · median 26 · p75 26 · max 28; 370/408 names ≥ 10 and ≥ 20 sessions; only 10 names have all 28
latest session                   372 names present; 372/372 with ≥ 20 quotable contracts (iv non-null, oi+vol > 0)
ATM IV (7–60 DTE, ±5%)          368/372 names
term structure (front + back)    308/372 names
25Δ skew pair                    369/372 names
contract-matched ΔOI             372/372 names (both of last two sessions)
GEX summaries                    408 per-name files, 26–28 session rows each (spot, iv30, gamma_flip, tier)
site/gex/<T>.json                710 files (gex_confirm inputs)
data/options_skew  validation_gate.json   41 dates
data/options_ivspread validation_gate.json 41 dates
data/earnings/earnings.parquet   1,983 tickers with next_date (56 in-window event names on 2026-08-13)
```

The v1 requirements (≥60-session eligibility, 252-session percentiles, 60-session ΔOI z) were therefore **impossible for 100% of the universe** — the method as first frozen was vacuous. v1.1's floors (H ≥ 10, windows min(W, H)) are satisfiable by 370/408 names today.

**Preflight (read-only dry run of §5.3 v1.1 against real current data, session 2026-08-13):**

```text
universe present:                372
technically eligible:            356 (95.7%) — non-vacuity gate (≥60%) PASS
excluded:                        16 INSUFFICIENT_HISTORY (H < 10; recently added names) · 0 INSUFFICIENT_COVERAGE
family availability (of 356):    V 353 · D 356 · P 345 · E 56 (event names) · C computed for all
state counts:                    LONG 69 · SHORT 46 · VOLATILITY 99 · RISK_ONLY 22 · NO_SIGNAL 120
ranked cards (R ≥ 250):          88 (board takes top 6; overflow disclosed)
top of board (illustrative):     SPY VOLATILITY R=424 · QQQ VOLATILITY R=418 · CVX SHORT R=414 · AMZN VOLATILITY R=410
confidence ceilings binding:     all sampled directional cards capped at 0.45 (inference-degraded ceiling) — the ceilings work
zero-signal confirmation:        signals exist at current thresholds; with 95.7% eligibility measured BEFORE thresholds, an
                                 empty board can only arise from thresholds (R_MIN, D-law), never from impossible prerequisites
```

Preflight caveats (honest limits of the dry run, not of the spec): it ran as a session-scratch script (methodology fully specified by §5.3; not committed — the implementation reproduces it as `tests/` fixtures + the §7 production proof); `v2` used cross-sectional ranking only; `d3` used an approximate recomputation; the E family used ATM IV as the event-premium proxy exactly as §5.3 defines. Counts above are a **feasibility demonstration**, not product output, and carry no research-priority authority.

**v1.2 semantic-authority preflight (AD-1P0, read-only, 2026-08-18, audit head `6482f876ba7f`, session 2026-08-13):**

```text
present 372 · eligible 356 (95.7%) · INSUFFICIENT_HISTORY 16 · INSUFFICIENT_COVERAGE 0   (feasibility preserved)
family availability: V 353 · D_salience 356 · Q_oi 356 · Q_skew 351 · P(gex verdict) 345 · E 56 · C 356
direction funnel: both Q legs present 351 → both |Q| ≥ 0.50: 19 → same-sign strong pairs: 10 → qualified (D_salience ≥ 0.60): 10
state counts: LONG 3 · SHORT 7 · VOLATILITY 152 · RISK_ONLY 29 · NO_SIGNAL 165
ranked cards ≥ R_MIN: 64 (board takes 6)
top-ranked directional exemplar: MSFT SHORT R=405 (Q_oi −1.00, Q_skew −0.75, D_salience 0.97, gex=caution shown as context, prophet=display-only)
event board: cross_sectional 56 · historical_conditioned 0
Prophet context among ranked: UNAVAILABLE 52 · OTHER 8 · NOT_READY 2 · ALREADY_OPEN 1 · READY 1  (display-only; zero rank effect)
v1.1 → v1.2 deltas: LONG 69 → 3 · SHORT 46 → 7 — ~105 v1.1 directional labels disappeared because they
depended on salience/GEX/absolute-skew semantics; this reduction is the intended correction and thresholds
were NOT tuned to recover the old counts. Non-vacuity: PASS (95.7% eligibility measured before thresholds;
64 ranked cards; both directional lanes demonstrably reachable on real data).
```

**Data-feasibility law (binding on AD-1 and every later spec change):**

> No frozen scoring specification may require more historical depth, per-name coverage, or field availability than the canonical producer store actually supplies at spec-freeze time. Every history-dependent constant in `CONFIG` must be satisfiable by ≥ 60% of the present universe on the freeze date, measured against the real store — never against intended future accrual. A spec change that raises a depth requirement must include a fresh census proving the store now supplies it.

## §6 Exact tests (minimum; all in `tests/test_options_intel_brief.py`)

1. **Contract identity:** adjusted/nonstandard vendor contract tickers are excluded by rule and counted in a named exclusion stat (never silently aggregated) — AD0:§6.1.
2. **Adjusted contract:** a synthetic adjusted-contract row cannot enter any feature family.
3. **DTE:** DTE computed against `as_of_session` (not wall clock); 0DTE evidence expires with its session.
4. **OI PIT:** using session-S OI for session-S scoring raises; ΔOI uses prior distinct snapshot day.
5. **Quote quality:** null/absent IV and degenerate values are excluded per family and counted; a name below per-name field coverage produces family-absent, not zero.
6. **Event conditioning:** an earnings-window name routes to event families; absent calendar → `EVENT_STATE_UNKNOWN` path.
7. **Incomplete chain:** coverage below threshold → `INSUFFICIENT_COVERAGE`, zero ranked cards.
8. **No-signal:** a liquid complete-data fixture with unremarkable conditioned features yields `NO_SIGNAL` with a `null_reason`.
9. **Stale source:** chains older than the freshness rule → `STALE_SOURCE`, cards withheld, last-good stamped.
10. **Deterministic replay:** same inputs → byte-identical artifact (stable ordering, no wall-clock leakage except `built_at_utc`, `receipt_id` reproducible).
11. **UI/API parity:** the rendered board's cards are exactly the artifact's cards (count + key fields), via the template-render test pattern already used by `tests/test_render_options_workspace_scope.py`.
12. **Correction placeholder:** artifact carries `supersedes_signal_id: null` + `corrected_at: null` on every card and the contract doc states correction semantics are implemented in AD-2 — the fields exist now so AD-2 is additive.
13. Build inputs for fixtures **through the production builder path** with production dtypes (house law: synthetic harnesses must not pick easier dtypes).
14. **Frozen-spec pin:** every §5.3 constant (salience weights 0.65/0.35, direction thresholds ±0.50/0.60, skew-change floor 8, evidence-strength weights 0.70/0.30, confidence ceilings 0.60/0.45, `M_gex` 0.75, actionability multipliers, R≥250/board sizes 6/4/4, tie-break order, eligibility floors H≥10/≥20 contracts, non-vacuity gate 0.60, blend weights 0.5/0.5, freshness session lives) asserted verbatim against `CONFIG`.
15. **Data-feasibility law (fails on impossible specs):** a test that reads the real canonical store (`data/polygon_gex/chains/` session count and per-name depth distribution; `needs_full_checkout`-marked so sparse trees skip rather than false-fail) and asserts every history-dependent `CONFIG` constant (eligibility floor, every feature window floor) is satisfiable by ≥ 60% of the names present in the latest committed session. This test FAILS if a future spec change again requires more depth than the canonical producer supplies — the exact defect this amendment repairs can never re-freeze silently.
16. **State-distinction test:** a name below the history floor reports `INSUFFICIENT_HISTORY`, never `NO_SIGNAL`; an eligible unremarkable name reports `NO_SIGNAL`, never a history/coverage state; `ELIGIBILITY_COLLAPSE` fires iff eligible/present < 0.60.
17. **Direction anti-vacuity (adversarial, all required):** (a) `d1=1.0, d3=1.0`, neutral Q legs → NOT LONG; (b) `gex_confirm_verdict=confirm`, neutral Q legs → NOT LONG; (c) `caution`, neutral Q legs → NOT SHORT; (d) positive `Q_oi` alone → NOT LONG; (e) negative `Q_oi` alone → NOT SHORT; (f) skew change alone → no machine direction; (g) Q legs agree but `D_salience < 0.60` → no directional card; (h) Q legs disagree → no directional card; (i) signing gate false → `Q_flow` structurally absent; (j) no rendered text ever describes current unsigned EOD observations as "customers bought/sold".
18. **GEX authority:** caution reduces qualified-LONG actionability (×0.75); confirm cannot create LONG; confirm cannot increase `evidence_strength` or `R`; caution cannot create SHORT; SHORT has no synthetic inverse of the long-centric confirmer.
19. **Forecast honesty:** `asymmetry_score` null/`UNCALIBRATED` at AD-1; no probability/expected-edge field populated; UI copy is "Evidence strength"/"Evidence confidence", never calibrated-alpha language.
20. **Event semantics:** <3 prior same-name events → `history_mode=cross_sectional` and no historical-mispricing copy; historical fields activate only with lawful history and remain context-only before AD-6.
21. **Prophet standalone boundary:** Prophet states never change `R`; `EXTENDED` is visibly disclosed; same AD inputs + different Prophet echo → identical machine score/rank, different display context only.
22. **Horizon/freshness:** 0DTE risk expires the current session; NYSE session arithmetic governs freshness; expired required evidence degrades/expires the card; trigger/invalidation derive deterministically from Q/V/E/C state, never generated prose.

## §7 Exact production proof (AD-1 may not pass without all of these)

```text
deployed SHA                      (/api/health checkout, reconciled to the merge SHA)
real latest completed source session   (chains session + oi_counted_date, from the served artifact watermarks)
real source watermark             (source_watermarks block, verbatim)
real ranked signal                (algorithm-selected; symbol + signal_id + card contents from production)
real liquid NO_SIGNAL             (no_signal_exemplar from the same production artifact)
real degraded or withheld case    (a production STALE_SOURCE/INSUFFICIENT_COVERAGE occurrence, or a staging run with an input withheld — never faked data)
signal receipt                    (receipt_id + input watermarks reproducing it)
API output                        (the served/committed artifact; auth-gated fetch or committed copy + served-page parity)
production UI output              (screenshot of the served board, light+dark+zh crops)
freshness display                 (visible as-of/fresh-until on the served board)
```

The proof symbol must be selected by the production algorithm. Auth note (AD0:§1): data JSONs are 401 in production — the lawful proof path is the server-rendered page + the committed artifact + R2 mirror, exactly as AD-0 audited the existing surfaces.

**AD-1P0 amendment — the runtime proof additionally requires, on real current/recent production data:** (1) one top-ranked directional card supported by both `Q_oi` and `Q_skew`; (2) one high-salience name that does NOT become directional because the Q legs disagree; (3) one GEX `confirm`/`caution` case showing GEX did not originate direction; (4) one liquid eligible `NO_SIGNAL`; (5) one event card showing its correct `history_mode`; (6) one Prophet `EXTENDED`/`ALREADY_OPEN`/`NOT_READY` card with visible context and an unchanged AD score; (7) one stale/degraded case; (8) zero user-facing text describing unsigned observations as observed buying/selling; (9) `asymmetry_score`/probability/expected-edge fields unpopulated; (10) UI and artifact agree on every displayed evidence and authority state.

## §8 Stop

After the production acceptance packet is posted, the AD-1 operator stops and returns for Chairman review. AD-2 (receipts/corrections/lifecycle) does not begin. The AD-1 session writes `agentos/handoffs/ADVANCED-DATA-OPTIONS-<date>.md` and updates `WS:ADVANCED-DATA-OPTIONS` wave state in the same PR as its final docs.

---

### Appendix — standing constraints the AD-1 session must load before writing code
- `AD0:§2.4` REJECTED_BY_DESIGN list and the DNR rows quoted there (`KILL-POSITIONING-FUSION` + Amendment 1 scope, `KILL-DOI-FAMILY`, `KILL-SKEW-DECELERATION`, `PSS-AF1`, `HOLD-WF-OPTIONS`).
- Options Confluence binding laws 1–18 (`research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` §3): inferred direction, no same-day OI, GEX-as-proxy, correlated-transformations-are-not-confluence, abstention allowed. Law 17 (AVOID-not-SHORT) is superseded **for this contract only** by `DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT` — the D-law (§5.3) is the operative direction protection; legacy confluence surfaces keep law 17 until their own docs are amended.
- Fleet law: ship loop (commit→push→PR→CI→same-day squash-merge→live verification, one session owns all of it), sparse-worktree opt-in before touching `site/` (`python3 scripts/worktree_sparse.py full`), paired plain-copy rule does not apply to `.j2` templates, GitHub-annotation line-start law, quota discipline.
- **Semantic-authority references (AD-1P0, primary sources):** OIC/OCC General Information FAQ — open interest reflects open contracts, not bullish/bearish outlook (OI = position quantity, not observed informed-side direction); Fodor, Krieger & Doran, *Do Option Open-Interest Changes Foreshadow Future Equity Returns?* (ΔOI predictive information motivates the hypothesis leg, not observed aggressor direction); Kehrle & Puhan, *The Information Content of Option Demand* (unsigned OI must not be narrated as informed buying/selling); Xing, Zhang & Zhao, *What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?* (smirk-shape information → skew is a hypothesis/innovation, not observed put demand); Soebhag, *Option Gamma and Stock Returns*, and Dim, Eraker & Vilkov, *0DTEs: Trading, Gamma Risk and Volatility Propagation* (gamma governs mechanics/volatility propagation — not a standalone informed stock-direction selector).
