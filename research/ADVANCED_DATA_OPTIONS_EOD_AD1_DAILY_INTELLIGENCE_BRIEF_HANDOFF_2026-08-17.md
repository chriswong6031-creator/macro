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

`opportunities[]` — each card (field names follow masterplan §6.2 where present):
`signal_id`, `canonical_instrument_id` (via `engine/stock_identity/`), `as_of_session`, `direction ∈ {LONG, SHORT, VOLATILITY, RISK_ONLY, NEUTRAL}`, `horizon`, `asymmetry_score`, `confidence`, `actionability`, `why_now` (plain-word), `evidence_family_contributions[]` (family name + capped contribution + observed-vs-inferred tag), `contradictions[]`, `trigger`, `invalidation` (front-facing copy = "what would change this read" watch-condition phrasing — operator 2026-07-27 language law), `expected_move_range`, `fresh_until`, `source_state`, `prophet_state`, `null_reason` (null on ranked cards), `what_would_make_this_wrong`.

**Direction law (binding — `DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT`, CEO review on #5830):** the architectural vocabulary includes `SHORT`; the old AVOID-not-SHORT vocabulary ban is NOT carried into this contract. The protection is evidence-gated instead: no raw call/put volume, premium, volume/OI, tick-rule-signed flow, GEX, or other insufficiently directional observation may originate `LONG` **or** `SHORT` on its own (§5.3 D-law); direction that fails qualification abstains or expresses as `RISK_ONLY`/`NEUTRAL`. With today's entitled EOD sources the implementation may lawfully emit **zero** SHORT signals — an empty SHORT lane is a correct output, not a defect. **Machine vocabulary vs display copy:** `LONG`/`SHORT` are the machine enum for *directional research hypotheses*; served copy renders them as "upside evidence"/"downside evidence" framing with the hypothesis nature explicit, never as trade imperatives ("buy"/"short"/"sell"), and never describes any field as observed buying or selling (no aggressor/open-close evidence exists in the entitled sources).

`event_board[]` — event candidates where implied move and event-conditioned historical distribution diverge: `symbol, event_type, event_date, implied_move, conditioned_move_reference, divergence, direction=VOLATILITY, fresh_until`.

`risk_warnings[]` — crowding/extension/fragility contexts (RISK_ONLY cards).

`no_signal_exemplar` — required whenever `board_state=OK`: one liquid, coverage-complete symbol with `NO_SIGNAL` and its `null_reason` (§4.3 law below).

**UI:** one new board at the top of the Daily Brief tab of `options.html`, rendering exclusively from this artifact (regime strip may continue to come from the existing tiles — the Brief adds the opportunity/event/risk/no-signal layer, it does not duplicate the tiles). Raw chain detail stays in existing tabs (drill-down, not first viewport).

### §5.1 Feature families (only proven fields — AD0:§4)
ATM IV; IV percentile conditioned by symbol/liquidity tier/regime; skew; term structure; implied-vs-realized; implied-vs-event-conditioned move; OI concentration + ΔOI (lawful clock only); DTE/moneyness/liquidity/event-conditioned volume anomalies; strike/expiry concentration; multi-session persistence. Family caps per masterplan §8.3 (correlated fields never become independent votes). All scoring mappings without outcome evidence are labeled `heuristic` in the artifact and cap `confidence` accordingly (masterplan §8.2). Off-exchange families are **excluded** (AD-3 owns them; nothing in the current architecture forces them into AD-1).

### §5.2 No-signal law
`NO_SIGNAL` on liquid complete-data names is a first-class output; the board is allowed to be empty (including a session where **every** complete-data name yields `NO_SIGNAL`); there is no activity quota; raw-volume leaders are never backfilled into the opportunities list to make it look active.

### §5.3 Frozen deterministic display-tier scoring and ranking (`intel_brief_heuristic/v1.1`)

This section is the complete initial method, **amended for data feasibility (Sol delta review, 2026-08-17)**: v1's 60/252-session prerequisites were impossible on the canonical estate (28 committed chain sessions at the amendment head; §5.4 census) and would have made the entire method vacuous. v1.1 uses only history the canonical producer actually possesses — current-session matched cross-sectional conditioning plus bounded longitudinal context — with no backfill, no new store, and no opportunistic lowering of evidence standards: where a v1 feature is not lawfully computable yet, it is absent or redefined, never faked.

**Authority (masterplan §8.2 amendment):** this method is a **deterministic ordinal heuristic carrying display-tier research-priority authority only**. Its outputs order research attention. They are not probabilities, alpha, forecasts, Prophet inputs, gates, sizes, or trade authority; no output may be described with the word "validated". Predictive/calibrated promotion remains AD-6/AD-7. `LONG`/`SHORT` cards are **directional research hypotheses**, not trade calls: no field lacking actual aggressor/open-close evidence may be described as observed buying or selling, and front-facing copy uses "upside evidence"/"downside evidence" phrasing, never trade imperatives. All constants below are frozen in one `CONFIG` dict in `engine/options_intel_brief.py`; `tests/test_options_intel_brief.py` pins them; any change is a new `model_version`. The implementation worker has **no scoring, weighting, threshold, or ranking decisions to make** — divergence from this section is a spec deviation to be returned, not resolved in code.

**Eligibility (per name, per session S).** A name is *eligible* iff: session chain file present; ≥ 20 quotable contracts after quality exclusions (§6.5); and **H ≥ 10**, where H = number of prior sessions with chain rows for the name in `data/polygon_gex/chains/`. A name failing only the history floor carries `null_reason: INSUFFICIENT_HISTORY`; a name failing contract/coverage rules carries `null_reason: INSUFFICIENT_COVERAGE`. Both are excluded from ranking and are **distinct from `NO_SIGNAL`**, which is reserved for eligible names whose evidence is unremarkable. A name is never made ineligible because a noncritical longitudinal feature lacks depth — the affected feature/family is simply absent for that name.

**Liquidity tiers (from quantities the estate possesses).** Underlying ADV$ is not in the canonical estate; tiers are cross-sectional quintiles of mean total contract volume over the trailing min(20, H) sessions: T1 = top 20%, T2 = next 40%, T3 = rest. Conditioning peer group = tier.

**Conditioning (replaces v1's 252-session own-history percentiles).** Two percentile sources: `p_xs` = rank among same-session tier peers (matched cross-sectional); `p_long` = rank against the name's own available history over the trailing min(W, H) sessions with a floor of 10 observations, where W is the feature's target window (20 unless stated; ΔOI targets 60). Blend: `p = 0.5·p_xs + 0.5·p_long` where both exist; a feature whose only meaningful frame is longitudinal (marked ⟂ below) uses `p_long` alone and is absent below the floor; a level meaningless across names never uses `p_xs`. Every card reports `history_n` per contributing feature so short denominators are visible. **Growth clause:** windows grow automatically toward W as the estate accrues (min(W,H) is self-extending); raising any W target is a `model_version` bump, never a silent edit.

**Feature transforms** (signed surprise `s = 2p − 1` where sign is meaningful):

- Family **V** (volatility): `v1`⟂ ATM IV (mean IV of the ≤6 contracts nearest ATM within ±5% moneyness, 7–60 DTE) — `p_long` only (IV level is not comparable across names); `v2` IV−RV spread = (ATM IV − RV)/RV where RV = annualized std of log returns of the GEX-summary spot series over the trailing min(20, H−1) returns, floor 10 (absent below) — blended; `v3` term slope = (ATM IV 7–45 DTE − ATM IV 60–120 DTE)/ATM IV 60–120 DTE — blended; `v4` skew = (mean IV of −0.35…−0.15Δ puts − mean IV of 0.15…0.35Δ calls)/ATM IV, 7–60 DTE — blended.
- Family **D** (demand): `d1`⟂ volume anomaly inside (DTE bucket {0–7, 8–30, 31–90, >90} × moneyness bucket {≤0.95, 0.95–1.05, ≥1.05 of spot}): today's bucket volume ranked against the same bucket's own min(20, H) history (floor 10); name-level = max bucket percentile, maximizing bucket named on the card; `d2`⟂ ΔOI lean = robust z of today's r = (call ΔOI − put ΔOI)/(call ΔOI + put ΔOI + ε) against its own min(60, H) history (floor 10), where ΔOI is **contract-matched** (contracts present in both sessions, expiry > S, per-contract ΔOI floored at 0) — z = (r − median)/(1.4826·MAD + ε), clamped to [−3,3]/3, lawful clock only (§4.1); `d3`⟂ persistence = share of the last min(10, H) sessions with `d1` ≥ 0.8 (floor 10, else absent).
- Family **P** (positioning): `p1` strike-concentration HHI of OI (expiries ≤ 90 DTE) — blended; `p2` = `gex_confirm_verdict` mapped {confirm:+1, neutral:0, caution:−1} (read from the live artifact, never recomputed); `p3` flip proximity = 1 − min(1, |spot − flip| / (spot × ATM IV·√(1/252))) using the existing GEX summary flip level (current-session only).
- Family **E** (event premium — REDEFINED for feasibility): the v1 historically-conditioned mispricing ratio needs ≥3 prior same-name events; the estate's depth (~28 sessions) cannot supply it. Until the estate holds ≥3 same-name events (self-activating upgrade, `model_version` bump), E is a **cross-sectional event-premium read**: defined when the earnings calendar (§4.6) shows an event within (S, S+45d] AND ≥5 such names exist that session; `F_E = clamp(0.6·(2·p_xs_event − 1) + 0.4·(2·p_long_iv − 1))` where `p_xs_event` ranks ATM IV among that session's event names and `p_long_iv` is the name's own ATM-IV percentile. Semantics: "event premium unusually high/low vs event peers and own baseline" — explicitly NOT a claim of event mispricing against realized history.
- Family **C** (crowding/extension, risk-only): `c1` same-day (≤1.5 DTE) volume share, `p_xs` among tier peers; `c2` = 1 if (`v1` ≥ 0.95 AND spot ≥ 0.98 × max spot over min(20, H) sessions, floor 10) else 0; `c3` = 1 if (`d1` ≥ 0.95 AND `d3` ≥ 0.5 AND `v2` ≥ 0.9) else 0. C-fire iff `c1 ≥ 0.9` or `c2 = 1` or `c3 = 1`.

**Family scores.** `F_V = mean(s_v1, s_v2, s_v3)` over the present members (v4 informs direction, below); `F_D = (0.5·s_d1 + 0.35·d2 + 0.15·(2·d3 − 1)) / (sum of weights of present members)`; `F_P = 0.5·p2 + 0.3·(2·p1 − 1)·sign(p2) + 0.2·p3·sign(p2)` (defined only when `p2` present); `F_E` as defined in the E family above (sign = high(+)/low(−) event premium, not equity direction). Every family score is clamped to [−1, +1]; a family or member with missing input is **absent** (excluded from all means, weights, and counts), never zero-filled.

**D-law (direction qualification).** A card may carry `LONG` or `SHORT` only if BOTH:
1. ≥ 2 present families agree in equity-direction sign with |signal| ≥ 0.5, where equity-direction sign is: `F_D` sign; `p2` sign; skew tilt `−s_v4` (steepening put skew = bearish tilt) when |s_v4| ≥ 0.5; and
2. at least one agreeing input is NOT tick-rule-derived — i.e. `d2` (ΔOI), `p2` (gex_confirm), or skew tilt qualifies; `d1`/signed premium alone never does.
`SHORT` additionally requires the agreeing set to include `d2 < −0.5` or skew tilt bearish — bearish `p2` (caution) alone is risk, not direction. If C fires, qualified direction is preserved but actionability is cut (below) and a companion `risk_warnings[]` entry is emitted. Direction failing the D-law: strong V family → `VOLATILITY`; C-fire → `RISK_ONLY`; else `NEUTRAL`/`NO_SIGNAL`.

**Asymmetry.** `A = clamp01( mean(|agreeing family scores|) + 0.2·[F_E < 0] − 0.2·[F_E > 0] )` for directional cards (LOW event premium is the favorable convexity case under the v1.1 E semantics; HIGH event premium is a cost); for `VOLATILITY` cards `A = |F_E|` if E present else `|F_V|`; for `RISK_ONLY` cards `A = max(c-inputs that fired)`.

**Confidence (ordinal, ceiling-bound).** `C_conf = 0.30 + 0.10·(#present agreeing families − 2, floored at 0) + 0.10·[d3 ≥ 0.5] + 0.05·[coverage complete]`, then apply ceilings: hard ceiling **0.60** everywhere in AD-1 (uncalibrated heuristic); additional cap **0.45** when every agreeing directional input is inference-degraded (no `p2`, no `d2`). Displayed on cards as a 3-band word (`tentative` < 0.40 ≤ `moderate` < 0.55 ≤ `firm`), never as a percentage.

**Actionability (multiplicative).** `M = tier × fresh × event × crowd × prophet` with: tier T1=1.0, T2=0.8, T3=0.5; fresh = 1.0 if every contributing feature is within its half-life (D families 3 sessions, V families 5, E until event close, P 1 session) else 0.5; event = 0.6 for directional cards with an event ≤ 2 sessions out (contamination), 1.0 otherwise; crowd = 0.5 on C-fire for positive-direction cards, 1.0 otherwise; prophet = 0.7 for `LONG` cards whose `prophet_state` echo shows an already-active plan older than 7 sessions (late-entry guard, display-echo only), 1.0 otherwise.

**Rank and board composition.** `R = round(1000 · A · C_conf · M)`. Opportunities board: eligible cards with direction ∈ {LONG, SHORT, VOLATILITY} and `R ≥ 250`, sorted `R` desc, tie-break higher `C_conf`, then higher tier-metric (mean contract volume), then symbol ascending; display at most **6** (overflow count shown, never silently dropped). Event board: up to **4** names with `|F_E| ≥ 0.5`, sorted by `|F_E|` desc, direction `VOLATILITY`. Risk board: up to **4** C-fire names sorted by `A` desc. `NEUTRAL` cards are never ranked; an eligible name that is NEUTRAL or below `R < 100` reports `NO_SIGNAL`. `no_signal_exemplar` = the highest-tier-metric eligible, coverage-complete name with `R < 100` (deterministic). Empty boards are lawful (§5.2).

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
14. **Frozen-spec pin:** every §5.3 constant (family weights, D-law thresholds, confidence ceilings 0.60/0.45, actionability multipliers, R≥250/board sizes, tie-break order, eligibility floors H≥10/≥20 contracts, non-vacuity gate 0.60, blend weights 0.5/0.5) asserted verbatim against `CONFIG`; a D-law fixture proving (a) tick-rule-only agreement cannot originate direction, (b) SHORT requires `d2 < −0.5` or bearish skew tilt, (c) a bearish caution-only card lands `RISK_ONLY` not `SHORT`.
15. **Data-feasibility law (fails on impossible specs):** a test that reads the real canonical store (`data/polygon_gex/chains/` session count and per-name depth distribution; `needs_full_checkout`-marked so sparse trees skip rather than false-fail) and asserts every history-dependent `CONFIG` constant (eligibility floor, every feature window floor) is satisfiable by ≥ 60% of the names present in the latest committed session. This test FAILS if a future spec change again requires more depth than the canonical producer supplies — the exact defect this amendment repairs can never re-freeze silently.
16. **State-distinction test:** a name below the history floor reports `INSUFFICIENT_HISTORY`, never `NO_SIGNAL`; an eligible unremarkable name reports `NO_SIGNAL`, never a history/coverage state; `ELIGIBILITY_COLLAPSE` fires iff eligible/present < 0.60.

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

## §8 Stop

After the production acceptance packet is posted, the AD-1 operator stops and returns for Chairman review. AD-2 (receipts/corrections/lifecycle) does not begin. The AD-1 session writes `agentos/handoffs/ADVANCED-DATA-OPTIONS-<date>.md` and updates `WS:ADVANCED-DATA-OPTIONS` wave state in the same PR as its final docs.

---

### Appendix — standing constraints the AD-1 session must load before writing code
- `AD0:§2.4` REJECTED_BY_DESIGN list and the DNR rows quoted there (`KILL-POSITIONING-FUSION` + Amendment 1 scope, `KILL-DOI-FAMILY`, `KILL-SKEW-DECELERATION`, `PSS-AF1`, `HOLD-WF-OPTIONS`).
- Options Confluence binding laws 1–18 (`research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` §3): inferred direction, no same-day OI, GEX-as-proxy, correlated-transformations-are-not-confluence, abstention allowed. Law 17 (AVOID-not-SHORT) is superseded **for this contract only** by `DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT` — the D-law (§5.3) is the operative direction protection; legacy confluence surfaces keep law 17 until their own docs are amended.
- Fleet law: ship loop (commit→push→PR→CI→same-day squash-merge→live verification, one session owns all of it), sparse-worktree opt-in before touching `site/` (`python3 scripts/worktree_sparse.py full`), paired plain-copy rule does not apply to `.j2` templates, GitHub-annotation line-start law, quota discipline.
