# LIVE ENTRY RADAR — PR-0 FROZEN RESEARCH CONTRACT

**Program:** Live Entry Radar — real-time tactical entry intelligence for U.S. equities
**Route (future):** `entry_radar.html` · **Workstream:** `WS:LIVE-ENTRY-RADAR` · **Parent program:** `market-timing-intelligence` (`config/mastermind_programs.yml`)
**Authority:** operator/CEO commissioned research + build (execution handoff received 2026-08-13; operator design directive same day)
**Status of this document:** FROZEN at PR-0 merge. Post-freeze changes happen only as numbered, dated, append-only amendments in §18 — never in-place edits — and any amendment made after first replay results exist must state what results its author had seen.
**Freeze date:** 2026-08-13 (all pre-registered thresholds in §10–§11 were fixed before any replay, backtest, or live result of any Radar detector existed).

---

## §0. ACCEPTANCE GATES (program-level, binding on every later PR)

**Product gates** (from the commissioning handoff, condensed; each later PR names which it discharges):

- [ ] Radar exists separately from Prophet; Prophet's selection/gating behavior is byte-identical (P-1)
- [ ] Grey Dot exact identity confirmed AND parity-tested against Terminal before any G0 result is claimed (P-2)
- [ ] 1D live/provisional values visibly and structurally distinguishable from closed-bar values (P-3)
- [ ] Pre-candidates and candidates can appear, promote, invalidate, and expire intraday (P-4)
- [ ] Same ticker can occupy multiple detector lanes simultaneously (P-5)
- [ ] Every lobe nomination can force a ticker into the Probe Set; IPO/small caps not rejected for index non-membership (P-6)
- [ ] Every candidate states why it entered the universe and why it became a candidate; ranking provenance inspectable (P-7)
- [ ] Every reading carries freshness; stale data never masquerades as current (P-8; see stale-frame precedent PR #5555)
- [ ] Detector score and Priority/Opportunity score are separate objects (P-9)
- [ ] False starts remain recorded forever; no silent deletion of failed signals (P-10)
- [ ] Dark + light intentional; EN + ZH; mobile works; no auto-trading anywhere (P-11)

**Research gates:**

- [ ] Point-in-time universe and features wherever replay is claimed; survivorship limitations disclosed in every result doc (R-1)
- [ ] No completed 1D/4H/2D/3D bar leaks backward into an earlier observation; mutation tests prove it (R-2)
- [ ] Signal price = price observable at decision time; costs/slippage modeled for ranked outcomes (R-3)
- [ ] IPO cohort calibrated separately; cap/liquidity cohorts reported (R-4)
- [ ] G0 vs C1 vs C2 compared independently; depth vs turn separated (R-5)
- [ ] False-start definition frozen (§10) before the main comparison was read (R-6)
- [ ] Matched-control performance present in every comparison read (R-7)
- [ ] MFE and MAE present; ranking monotonicity reported (R-8)
- [ ] Look count / multiple-testing disclosure in every result doc; look ledger append-only (R-9)
- [ ] Live-forward ledger running before any claim of measured edge; "validated"/probability language only after Evaluation OS promotion (R-10)

**Sequencing gates:**

- [x] G0-VIS: glyph identity confirmation (§3.3) — **CLOSED 2026-08-13, operator confirmation (§18 A1)**
- [ ] Parity fixtures green before any cross-repo G0 claim
- [ ] Look ledger exists before the first replay read (PR-5 entry criterion)

---

## §1. EXECUTIVE DECISION AND SEPARATION DOCTRINE

Build a **new, separate real-time U.S. tactical entry system**. Do **not** modify existing U.S. Prophet selection/gating logic anywhere in this program.

The system's job: **continuously search the U.S. equity market for stocks where a temporary washout or dislocation is creating unusually favorable entry asymmetry, then rank the opportunities by the quality of their forward upside/downside distribution.**

Three questions stay separate, permanently:

| Layer | Question |
|---|---|
| Prophet / Own-It | Is this an opportunity worthy of conviction? |
| Existing entry gauge (`engine/entry_signal.py`) | Has enough confluence arrived to make entry timing relatively safe? |
| **Live Entry Radar** | Is an unusually attractive early entry **forming right now**, before full confirmation? |

Radar deliberately trades confirmation for earlier timing, greater potential asymmetry, more false starts, and more reliance on operator judgment. If Radar proves incremental value, it may later become a nullable Prophet input or a new validated entry lane — a future promotion decision, not part of this program.

**Non-interference proof obligation:** every Radar PR that touches `engine/` must show `git diff --stat` clean on `engine/entry_signal.py`, `engine/prophet_*.py`, and the Prophet gate configuration; Radar imports from those modules are read-only library uses, never edits. (Sibling workstream `WS:PROPHET-US-ENTRY-TIMING` owns Prophet-side timing diagnosis; `owns_paths: engine/prophet_*.py` — Radar must never claim those paths.)

**Core trade archetype:** structural strength → temporary weakness → selling exhaustion → observable turn → renewed demand. *Buy weakness beginning to fail inside something worth owning.* The central object is **washout → turn**, never "oversold" as a state. The system does not call bottoms; it detects the earliest observable change from "selling is still winning" to "selling is no longer winning" inside names whose structure implies renewed demand could matter.

---

## §2. PRIOR ART AND KILL-REGISTRY COMPLIANCE

This program starts display-tier/accruing (free to build under house epistemics); the gauntlet applies at promotion. But it must be built citing what the house already killed, and every promotion attempt must confront these by name:

- **`DNR:KILL-WASHOUT-TURN`** — "Washout × turn (2W operator seed)" KILLED in entry-stack Amendment-3 (#1747). **Exact killed construction** (Track B receipts: `ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:259,271-276`): the operator's literal **2W/1M StochRSI washout** — deep higher-timeframe oversold *position* — used in interaction with a turn, **layered on Prophet gate fires**. Killed by the **NC-2 proximity de-confound** (RUL-28: a 63-bar close-min proximity band-FE arm is mandatory in every primary read; an effect that dies under proxy-FE is a proximity shadow): the seed added *negative* marginal value once proximity was removed. Its position form and interaction form are dead; the **motion form survives caveated** (weekly turn +19pp held21 at *state* level, ~⅔ proximity, thin residual — display-candidate only, never fire-conditional evidence).
  **Radar's distinction, four-part (house template TS-R3, `TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:46`):** (1) different grain — 1D-live/daily **motion** constructions, not 2W/1M HTF position; (2) not layered on Prophet gate fires — a standalone discovery/ranking product with its own episodes; (3) per-stock granularity with matched controls, not stack-conditional deltas; (4) display-tier accrual with promotion gated fresh. **Inherited obligation:** every Radar primary comparison carries an **NC-2-style proximity kill-arm** (§11) — if a detector's excess dies when proximity-to-recent-low is controlled, it is a proximity shadow and is reported as such. No future promotion may skip re-confronting this kill by name.
- **`DNR:KILL-PSS-F1-DOWNVOL`, `KILL-PSS-F2-OVERNIGHT`, `KILL-PSS-F3-RESIDUAL`, `KILL-PSS-F4-SEMIVAR`** — four standalone entry-*timing* families killed 2026-07 under the PSS §7 timing ruler. None are Radar detectors. Inherited obligations: (a) reuse that ruler's discipline (per-name-first aggregation, matched-construction placebos, incumbent benchmark) rather than invent a new one (§11); (b) semivariance asymmetry stays available as a *confluence descriptor* only, per its own kill row; (c) the incumbent benchmark those kills reference (Stoch-RSI cross at −2td) is Radar's natural "existing gauge" comparator.
- **`DNR:KILL-MCO-THRUST`** — breadth washout *bounce* legs rejected as radar legs (market-level). Radar is single-name; no breadth-thrust detector may enter the arena via this program.
- **Entry Stack expansion finding** (`research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md:20,39,62-65`) — multi-TF washout **depth** behind fires: H1 FAIL, +2.9pp clean15 bought at **+3.5pp stop-out**, `w2_deep ≈ 0 alone`. Motion: weekly TURN +19pp held21, deep×reversing +26pp, 4-TF turn-count monotone 43.7→61.4% — all **state-level, not fire-conditional, never adjudicated on the gate-fire tape**. Frozen consequence: **2D/3D depth is context, never authority** in any Radar detector or score; turns are the object (§4); and Radar must not quote those motion numbers as validation — they motivate, nothing more.
- **Adjacent per-name organs — the real boundary (Track B §7):** `engine/washout_turn.py` is an existing per-name **weekly** washout→turn watch organ (US, display-tier, zero authority, canon math), whose own charter records the Amendment-3 kill boundary; `engine/mtf_upturn.py` is the TS-R3 per-stock multi-TF upturn organ (K-of-N legs, registered expected-NULL). Radar's C1–C4 live in a different grain (1D-live/intraday motion vs weekly/multi-week grain) and a different product (episode ledger + ranking vs watch vocabulary); PR-2/PR-3 must state this boundary in their module docstrings, house precedent `engine/washout_turn.py:1-5`. `engine/ignition_radar.py` is market/basket-grain breadth — name collision only. `engine/setups.py` and `engine/stock_personality.py` are downstream consumers: they may read Radar output later; Radar never writes into their scoring.
- **DRL (dislocation-recovery / price-pressure) boundary (Track E §5):** DRL is a *reactive, cross-sectional residual-shock magnitude* detector (`resid_z ≥ 3 ∧ volume ≥ 2×`, constants imported from a kill-fence and untunable), `authority` all-false, with a standing refusal to become an entry system and an explicit exclusion of oscillator/turn vocabulary. Radar is a *prospective state-transition* entry/ranking system. Zero namespace overlap (`engine/price_pressure/` vs `engine/entry_radar/`), zero construction overlap (level/magnitude trigger vs turn trigger); the two may co-fire on a name without reading each other. Radar **inherits from DRL**: the `engine/ledger_lane.py::nightly_advance_enabled()` single-advancer gate, the `authority: {can_rank/can_size/can_gate/can_originate_signal/can_escalate: false}` display-tier artifact convention, and the R4 prereg shape (`research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md`: provenance → frozen claims → imported evidence cells → inference → floors → consequence matrix → clock → append-only grading log + dated amendments) as the template for Radar's PR-5 registration.
- **Prophet's own evaluation status (context, Track E §4):** "AT ITS RULER verdicts at declared horizon: 0"; the plan ledger's one favorable headline is raw return with **no benchmark field** plus a first-trigger-closure bookkeeping defect (`T1_HIT` forever). This is why Radar begins life as an experiment with a ledger: its episode outcomes carry benchmark/sector excess and MFE/MAE **from day one** (§10), the exact fields whose absence made Prophet's number undefendable.

---

## §3. CHAMPION G0 — TERMINAL GREY DOT (exact, not approximate)

**Identity hypothesis (to be confirmed, not assumed):** the operator's "grey dot" = Terminal's early anticipation dot in `charting-app/signal_layer/confluence_v2.py` — 3D StochRSI bullish cross from oversold AND 2D RSI-MACD histogram rising before the main cross, with point-in-time handling of 2D bar availability and a docstring claiming ~4.6 days of lead; the current emitter renders it as the amber EARLY marker and removes the old gray side-channel dot underneath.

### 3.1 Exact specification (locked; full receipts in `research/live_entry_radar/TRACK_A_GREY_DOT_FORENSICS.md` §1)

Spec source = `charting-app` **`origin/master`** (the local checkout is a month stale and still carries the pre-#392 *leaking* 2D→3D map — it must never be read as spec). Close-only inputs from the **shared** store `$MACRO_REPO/data/stocks/<SYM>.parquet` — the two repos already share this data plane.

- **3D bars:** per-symbol **session grid** anchored at the symbol's first listed session (`gi = arange(n) + bar_anchor`; a new bar opens the session after any `gi % 3 == 0`; bar value = close of its last session; frame indexed by the bar's **OPEN** date; ≥90 bars required). Deliberately not calendar resampling.
- **2D bars:** calendar `resample("2B").last().dropna()` on the daily close (left-edge label), with availability computed separately as each bucket's **last actual session**.
- **Oscillators (constants 14/14/60/5; stoch 14/14/3/3; OB/OS 80/20; CONF_W 8):** Wilder RSI(14) on the 3D close series via **SMA-seeded RMA** (same family as Macro `canon.rsi`); StochRSI = stoch(14) of that RSI, flat window → NaN, %K = SMA(3), %D = SMA(3), pandas-default min_periods, NaN rows dropped; RSI-MACD = `ema(RSI,14) − ema(RSI,60)` with `adjust=False`, signal `ema(·,5)` — never price MACD.
- **The three legs:** `stoch_bull = crossover(K, D)` (strict `>` now, non-strict prior bar); `from_os = D.rolling(8).min() < 20` (**D line only**, window inclusive of current bar); `rising2 = 2D hist > 2D hist.shift(1)` (strictly greater, exactly one bar, no magnitude/sign requirement). `dot = stoch_bull & from_os & PIT-mapped(rising2)`.
- **PIT law:** every bar carries `known_ts` = its CLOSE session; the 2D→3D join takes, per 3D row, the newest 2D state whose availability date ≤ that row's `known_ts` (searchsorted). **The emitted event `ts` is the 3D OPEN date — up to 2 sessions before `known_ts`. Radar consumes `known_ts` as the decision date, never `ts`** (measured backdating examples: NVDA 2026-01-21→known 01-23; NFLX 2026-06-26→known 06-30).
- **Identity:** `SIGNAL_ERA = gc_v2_wo2`; params hashed via the Terminal's own `source_hash`/`strategy_spec_hash` conventions.

**Lead-time honesty (frozen):** the "~4.6d lead" docstring is an unsourced paraphrase. The published figure is **+4.89d matched-pair mean at 49.9% coverage** vs the confirmed buy (`research/signal_engine/CONFLUENCE_TUNING.md:105`); charging every dot to the next confirmed buy gives **mean 12.7 sessions** (Track A §2.6, n=190). No Radar surface or result doc may quote a G0 lead without deriving it under a declared matching rule. Terminal's own charter further records that acting on the early dot was **empirically worse entry quality** (deeper drawdown) than the confirmed buy — the champion enters this program with an adverse prior on raw earliness, and §10's false-start/asymmetry ruler exists precisely to test whether structure + turn conditioning overcomes it.

### 3.2 Parity strategy (DECIDED)

**Primary: consume the versioned Terminal artifact.** `mastermind.indicator/v1` (`<SYM>.slice.json`) already carries `early_dots`, `BOTTOM_WATCH` events, `known_ts`, `source_hash`, `SIGNAL_ERA` — Radar pins on `(source_hash, SIGNAL_ERA)` and reads the **raw emission**, not the capped model slice (`early_dots` is capped at 40/12 in doc/model slices). A **freshness gate is mandatory**: the deep store read at census showed last bar 2026-07-08 (~5 weeks stale — possibly the reading checkout, not production; PR-2 verifies against the production store and hard-gates on `feed_end`).

**Fallback: locked-spec reproduction in Macro** = §3.1 + fixtures F1–F6 + `spec_hash`, seeded from `origin/master` only. Never seed from Macro's `research/signal_engine/confluence.py` — a **verified silent fork** (byte-identical oscillator math but zero `known_ts`, no v2 layer; the Terminal header's "corrected vs that copy" claim is stale) — and never from the stale checkout. **Shared-lib extraction is rejected**: no installable package boundary exists on either side (`sys.path.insert` bootstrapping), `confluence_v2` hard-imports the 1107-line washout_override machinery, and the silent fork above is the standing evidence of what un-fixtured extraction produces.

**Anchor caveat:** G0's 3D grid is **per-symbol listing-anchored** — not Macro's absolute session anchor. The G0 adapter follows the Terminal grid exactly; Radar's own C4 constructions use the absolute anchor with a Radar era string (§4). The two grids never mix inside one detector.

**Fixtures (committed at PR-2):** F1 NVDA full-history (8 dots ≥2025, zero watch events; pins grid phase from a 1999 IPO); F2 NFLX (11 dots, 4 watch events, emitter de-dup in both directions, **plus per §18 A1.1: the adapter's reconstructed G0 population `early_dots ∪ bottom_watches[kind=="early_dot"].ts` contains all 11, and the Radar-synthesized `promoted_by` edges resolve for exactly 2026-02-06/02-25/06-26**); F3 blocked_trigger precedence over early_dot (**and its de-dup edge recorded as known-lossy from the artifact, per A1.1**); F4 TSLA (2010 IPO — warm-up/anchor drift); F5 `known_ts` exact values; **F6 feed-truncation leak test** (truncate the feed to each dot's `ts` before its `known_ts` → the dot must vanish — the exact pre-#392 bug, and the highest-value case).

### 3.3 Glyph confirmation (gate G0-VIS) — CLOSED (code identity confirmed; operator ratified 2026-08-13, §18 A1)

Code verdict **HIGH confidence** (Track A §2): the emitter comment names "the old **gray** side-channel dot" verbatim; the unpromoted dot renders as a 2.2px circle, 55% opacity, fill `#717a8e` (`--muted`), 9px below the bar low, behind the "Signals detail" chip; only washout-context dots are promoted to the amber `EARLY` marker (`#e8b339`), and grey remains the overwhelming form (29 dots ≥2025 across NVDA/TSLA/NFLX; only 3 promoted, all NFLX). No competing grey marker exists in the chart layer.

**Closure protocol:** the operator names one remembered dot (symbol + approximate date); it is matched against the computed fired-date table in Track A §2.6 (NVDA: 2025-01-17, 03-12, 09-11, 09-29, 12-02, 12-18, 2026-01-21, 07-07 · TSLA: 2025-01-16, 02-12, 03-11, 04-09, 07-11, 08-11, 11-20, 2026-02-05, 02-24, 03-30 · NFLX: 11 dots incl. the 3 amber-promoted).

**→ CLOSED 2026-08-13 (§18 A1): the operator confirmed the raw grey anticipation-dot family. G0 = the exact raw grey-dot emitter; the amber-promoted `EARLY` is a distinct recorded family with a preserved promotion link.** PR-2's parity freeze is unblocked.

### 3.4 C5 — Terminal Bottom Watch (locked; receipts Track A §3)

Washout context = **W1 ∧ (W2a ∨ W2b) ∧ W3**: W1 `bear_block` (monthly RSI-MACD bear ∧ below 200DMA ∧ 2W RSI-MACD not bull); W2a 252-session drawdown ≤ −35% (84 3D bars); W2b prior-closed **monthly** StochRSI-D < 20 for ≥3 consecutive months; W3 3D StochRSI-D oversold visit within 8 bars (`min_periods=1`, unlike G0's `from_os`). Candidates = `(early_dot | blocked CB/revBuy trigger) & washed`; `kind ∈ {early_dot, blocked_trigger}` with blocked_trigger taking precedence and de-duplicating the dot; every event `scored: False` with `known_ts`, PIT `sweep_low`, `atr14`, `stop_level`, and `risk_basis` flagging close-proxy substitution. Monthly buckets are PIT-relabelled to the last actual session and searchsorted-joined — same discipline as §3.1.

---

## §4. CHALLENGER FAMILY — WASHOUT AS MEASUREMENT, TURN AS EVENT

A low oscillator is a **state**; the tradable object is the **transition out of it**. Every detector consumes the shared washout-episode feature vector (computed per episode, availability-stamped):

depth (min K, min D), floor-touch flag (min K ≤ 2), time from K=20 to minimum, velocity into washout, sessions below 20, failed-turn count while oversold, K−D relationship, first derivative of K during recovery, rebound velocity, RSI-MACD histogram level/slope/curvature, histogram local-trough location and age, price rebound from episode low in ATR units, volume/relative-volume response, and the structural context vector (§8).

**No detector may require a zero print.** A leader refusing to reach the floor ("partial washout": min K in (2, 20], short dwell, early turn) is a first-class cohort, potentially showing *more* relative strength — never penalized for insufficient depth.

Frozen arena (detector IDs are versioned; `spec_hash` per version; a spec change = new version = new detector for evaluation purposes):

| ID | Definition (frozen intent; exact constants locked in PR-2/PR-3 specs) |
|---|---|
| `G0_GREY_DOT@1` | Terminal implementation, exact (§3) |
| `C1_1D_LIVE_WASHOUT@1` | Pre-candidate arms when **1D LIVE** StochRSI K < 20 (provisional value; full intraday path recorded, including round trips like 35→8→0→24). **Promotion rule (frozen): `candidate_at ≡ first_armed_at`** — for the highest-recall lane, the arm *is* the candidate; §10's clocks key off it |
| `C2_1D_TURN@1` | C1 state + registered turn evidence. Variant family = **exactly six single-feature variants** (C2a K×D cross · C2b K slope > 0 · C2c higher oscillator low · C2d histogram local trough with positive slope · C2e positive histogram curvature · C2f rebound ≥ 0.5×ATR from session low), each promoting CANDIDATE on its condition while ARMED. **Primary variant = C2a (K×D cross)** — the 1D-grain counterpart of G0's leg and the incumbent's cross; C2b–C2f are exploratory and look-counted. No post-hoc variant additions |
| `C3_1D_4H_RECOVERY@1` | 1D washout state + **completed** 4H RSI-MACD histogram turn. A live/partial-4H form, if ever wanted, is a separate detector version, default off. Completed and incomplete 4H bars never mix inside one detector. **Contingent on the intraday-data decision (§7.2)** — no U.S. equity intraday bars exist in-repo today |
| `C4_MTF_TURN@1` | **Stratification family, not an arming interaction (Track F B3):** multi-timeframe turn *features* — 2D turn flag, 3D turn flag, all-timeframe recovery count, and higher-TF washout state — computed on an **unconditioned C2 base** and used to stratify/condition C2 episodes in analysis. No Radar detector arms on "1D turn AND 2D/3D washed": that is `DNR:KILL-WASHOUT-TURN`'s interaction form re-cut at a new grain, and building it would require an explicit pre-declared registration re-opening that kill by name with the NC-2 arm. Depth remains context, never a requirement or monotone bonus |
| `C5_BOTTOM_WATCH@1` | Terminal bottom-watch port (§3.4) |
| `F1_FUSION` | **Not in V1.** Registered only after individual detector results exist; never champion by definition |

**Indicator-soup prohibition:** no new indicator families (Bollinger, VWAP votes, oscillators beyond the above) may join the arena until G0/C1/C2/C3/C5 have independent-information results, and then only via a registered amendment (§18).

**Indicator-core law (Track B §1, binding on PR-2/PR-3):** the Macro repo carries **two incompatible RSI families** — canon's SMA-seeded RMA (`engine/canon.py:353-362`, == Pine `ta.rsi`, the cross-repo golden oracle; used by canon and `washout_turn`) and the bare-`ewm` variant (`engine/technicals.py:26-31`; what the shipped Prophet gate actually runs, under five wrong "== Pine" comments) — differing exactly where crosses flip. Nine StochRSI sites and five RSI-MACD sites exist with divergent NaN policies and `adjust` flags (RSI-MACD here means `EMA(RSI,14) − EMA(RSI,60)`, signal `EMA(·,5)` — never price MACD). Radar therefore: (a) computes its indicators in **its own modules only**, pinning **one named family** — default `engine/canon.py` (R-A) as the cross-repo parity substrate, confirmed against Track A's Terminal spec before PR-2; (b) never imports `engine/technicals.rsi` for any Radar detector (`engine/washout_turn.py:31-33` precedent); (c) uses a true Wilder ATR (`engine/stock_technicals.py:58-73` form, PIT-shifted per `engine/personality_relief_hazard.py:210-220`), **never** `entry_signal._atr_pct` (which is a close-only mean-abs-return misnomer, `engine/entry_signal.py:60-73`); (d) adopts the **absolute session anchor** for any 2D/3D bucketing (`engine/confluence_tiers.py:274-304`, `session_positions // n`, per-bucket last close indexed at bucket-last session date) with its own new era string — never first-bar-ordinal resampling (measured 12.83% verdict movement under leading-bar drops) and never calendar-anchored `resample("2W-FRI")` (the `htf_durability.py:102-115` vs `momentum_events.py:149` contradiction is not inherited).

A ticker can occupy several lanes simultaneously; lanes are never blended behind one number without per-lane provenance (§9). **Beyond the arena, Radar records Terminal's other entry-event families as distinct candidate experts with full identity preserved (§18 A1) — recorded ≠ graded; no flattening.**

---

## §5. PROVISIONAL-BAR AND POINT-IN-TIME LAW (non-negotiable)

Every input carries an availability state: `confirmed | provisional | stale | unavailable`. Every signal stores: `observed_at, market_session, source_bar_time, source_bar_known_at, bar_state, data_vintage`.

The engine distinguishes, as different inputs: **1D LIVE** (current partial daily bar), **1D CONFIRMED** (last completed daily), **4H LIVE** (only if a detector version explicitly enables it), **4H CONFIRMED**, **2D/3D** (mapped by real information-availability date, following Terminal's point-in-time discipline).

**Replay rule:** historical replay of any LIVE-state input requires intraday (minute) reconstruction of what the indicator showed at the decision timestamp. If minute data cannot support that for some period/name, that detector×period is **live-forward only** — never backfilled from EOD values.

**Leakage matrix** (every row must have a contamination test before PR-5's first read):

| Input | known_at rule | Replay source | Live source | Contamination test |
|---|---|---|---|---|
| 1D LIVE StochRSI/hist | continuously; value provisional until session close | minute aggs → provisional daily bar | live plane (§7) | EOD-mutation test: perturb the final close after decision timestamp → all features observed before it must be bit-identical |
| 1D CONFIRMED | next session open (conservative: close + T+0 evening bake time) | daily bars | nightly artifacts | same-day-use test: confirmed value never cited with `source_bar_time == observed_at` session |
| 4H CONFIRMED | at 4H bar close per session calendar | minute aggs aggregated | live plane | bar-boundary test around session irregularities |
| 2D/3D | last session date of the absolute-anchor bucket (`session_positions // n`); a partial bucket is publishable but always `provisional` (existing precedent `engine/confluence_tiers.py:664`) | daily bars + absolute anchor, Radar-era string | same | no future completed bar mapped backward; leading-bar-drop invariance test (the 12.83%-vs-0.00% anchor property). Terminal-side (G0 adapter only): the `known_ts` searchsorted join per §3.1, leak-tested by fixture F6 — note G0's grids differ by design (per-symbol 3D, calendar 2B) and never mix with Radar's absolute-anchor constructions |
| Price basis (adjusted nightly vs raw live quote) | nightly closes are split+dividend-adjusted total-return (`collectors/_stock_ohlc.py:92`); live quotes are raw vendor prints, deliberately never converted | store series at vintage | per-pass basis audit: pack `as_of_close` vs feed `prev_close`, past tolerance → name goes `dark` with `basis_mismatch` (`engine/prophet_live/live_states.py:136-147`, `interval.basis_audit`) | basis-step test: a corporate-action re-adjustment must never fabricate a cross (`lib/store.py:64-77` hazard; `basis_shifted` + full-history re-pull guard `collectors/yahoo.py:226-235`) |
| Universe stats (ranks, RVOL, caps) | as-published artifact asof | archived artifacts / recomputation with PIT inputs | current artifacts | rank-vintage test: replay rank uses only data ≤ decision date |
| Lobe nominations — archived producers (nightly, committed artifacts) | `source_asof` + `observed_at` at bus ingestion | the producer's committed artifact at vintage | live bus | nomination postdate test: no nomination consumed before its producer artifact existed |
| Lobe nominations — ephemeral producers (Track F B2: `hot_tape` has no `data/` artifact; `flow_pulse` fastpath writes zero `data/`) | same | **NONE — historically unreconstructible; anything touching them is live-forward only (§11 Q4)** | live bus; **PR-1 spools every nomination event to R2 from day one** so the live-forward record is durable | spool-before-consume test: no nomination enters an episode without a spooled event carrying `observed_at` |
| Nightly inversion pack (§7.1 thresholds) | `pack.as_of` must equal `last_completed_session()` | n/a (live mechanism) | nightly arming pass | **stale-pack gate (Track F B7): on mismatch every detector state publishes `unavailable`, no transitions are emitted, no events spool** — a stale pack fabricates crossings (wrong session's series; the measured 45/180 armed-pack analog), it does not merely stale them |
| Risk geometry (ATR, swing lows, spreads) | derived from bars ≤ observed_at | same | same | recompute-at-vintage test |

Replay sources resolved (Track D §3): LIVE-state rows replay from episode-windowed Massive `minute_aggs_v1` (≥2010-06-15) fetched per episode; confirmed-bar rows replay from the daily store at vintage. The §7.2 strategy law (episode-windowed, never bulk) governs.

---

## §6. UNIVERSE — DYNAMIC PROBE SET, NOT A CONSTANT

Funnel (all admissions carry machine-readable **admission reasons**; hotness admits, it never scores — §9):

- **Layer A — broad eligibility:** every supported tradable U.S. operating equity/ADR with sufficient data. Leveraged/inverse ETFs, ETNs, warrants/rights/units, and decaying derivative wrappers are excluded-or-separately-classified, never silently dropped. Small caps are not excluded for size.
- **Layer B — core:** S&P 500, major Nasdaq leaders, liquid large/mids, operator watchlists/holdings, names already under first-class single-stock coverage.
- **Layer C — dynamic hot:** admission on measured attention — dollar-volume rank, relative volume, share turnover, unusual realized range, large gap, short-term momentum, theme leadership, news/catalyst intensity, options activity. Thresholds are PR-1 budget knobs (measured against compute/data budget), not constitutional numbers.
- **Layer D — lobe nominations:** any ticker surfaced by an eligible single-name intelligence producer is auto-admitted with provenance, regardless of rank.

**Probe Set operating target:** ~500–1500 names, floating with measured budget. If 1,700 deserve probing, 1,700 are probed and the budget question is escalated, not silently truncated.

**IPO/young-history lane:** `history_age_sessions` on every name; young cohort (< 252 sessions) uses compatible short-history features, lower model certainty, liquidity/spread checks, halt/gap risk flags, and **separate calibration**. Young history is not low-quality data.

### 6.1 Nomination bus contract (frozen)

`mastermind.entry_probe_nomination.v1`: `ticker, source_id, source_family, reason_code, reason_text, observed_at, source_asof, source_rank, source_value, source_horizon, ttl_until, evidence_ref, data_quality`.

One ticker may carry many nominations; all provenance preserved. Producers group into source families (market/price, theme/sector, fund/ETF flow, smart money, options, off-exchange/dark-pool, news/catalyst, fundamental, special situation) so correlated producers cannot be double-counted: **nomination guarantees probing; predictive weight must be earned independently per family (§11). No "+5 points per page."** Nominations come from producer artifacts only — **never from scraping HTML pages.**

**Census results (full table: `research/live_entry_radar/TRACK_C_LOBE_PRODUCER_CENSUS.md`):** ~32 producers across 9 families. Binding consequences for PR-1:

- **Universe machinery that already exists and is reused, never rebuilt:** the canonical ~2,966-name U.S. universe (`scripts/build_stock_library.py:830`, S&P 1500 + Russell 2000); index membership (`data/breadth/constituents.parquet` + siblings); the GICS/SIC sector map (`data/breadth/ticker_sectors.parquet`); market cap; `dollar_vol_20d` / `rel_volume` / intraday `rvol_tod`; realized vol/ATR; sector-neutral momentum (`engine/residual_alpha.py`); the IPO calendar with listing dates (`data/ipo/calendar.parquet`).
- **Missing pieces PR-1 must build or explicitly defer:** an ETF/ETN/leveraged-wrapper classifier for arbitrary tickers (only narrow curated lists exist today — Layer A classification is a build item); float-based share turnover (no float data — declared out until sourced); gap detection (`engine/entry_primitives.py:651` is appendix-locked DORMANT — do not silently resurrect it; a Radar gap feature is a new, boundary-clean construction).
- **Highest-value nomination sources:** the 5-min `hot_tape` detector (`engine/marketing/hot_tape.py` — currently writes only to the marketing outbox; a nomination tap is new PR-1 work, not a file read); `site/live/flow_pulse.json` (30-min, per-ticker vwap/rvol/higher-lows, ~360 names); the nightly stock-library master (~2,966 names, carries entry_signal/setups/name_score reads); `us_standouts`/`setups` boards; basket `pulse` + `linked_outsiders` (filing-linked counterparties — a genuinely distinct catalyst-adjacent path).
- **Structural facts the bus design must respect:** theme/basket surfaces (`state_of_themes`, `radar`, `foresight`) are **not** single-name producers — a basket-membership expansion is a *different admission reason* (`reason_code` must say so; a basket-level fact must never launder into a single-name fact); `capital_structure` is API-gated, not artifact-based; the **operator watchlist/portfolio lives in Supabase** (`watchlists`/`watchlist_symbols`/`portfolio_positions`, RLS owner-scoped) — its adapter is a server-side DB read on the VPS lane, architecturally unlike every file-based producer, and its provenance field records that.

---

## §7. LIVE ARCHITECTURE AND CADENCE (decision)

**Decision (criteria frozen now; mechanics ratified against Track D findings):**

- **Cadence:** ~5-minute decision refresh during RTH for the Probe Set. One-minute cadence is not pursued until research proves 5 minutes materially misses the turn — the signal is daily/4H/2D/3D; refreshing a daily oscillator 60× more often is not intelligence.
- **Plane:** VPS-primary timer (the `prophet-live.yml` pattern: VPS primary, GitHub backstop, live state artifact, event spool, **no intraday durable-ledger writes**, nightly reconciliation). GitHub cron is never the product cadence.
- **Market data:** reuse the estate's existing entitlement and integration plan (Massive: real-time trades/NBBO, second aggregates, snapshots, deep minute history). **No second market-data plane; no second stock WebSocket owner.** If the shared real-time plane is not production-ready, a bounded real-time REST/snapshot poller for the active Probe Set is acceptable only after the data lane demonstrates cadence/vendor constraints/load — and it must be built to be replaced by the shared plane.
- **Sessions:** actual NYSE calendar (holidays, early closes, DST, halts) — never wall-clock arithmetic. Extended-hours data never contaminates RTH-parity daily oscillators; an extended-hours detector would be a separate, explicitly-labeled construction.
- **Single-writer law:** the intraday lane publishes ephemeral state (probe universe, detector states, candidate states, ranking, live page payload, event spool). The nightly reconciler is the **only** writer of durable evidence (episodes, outcomes, evaluation). No git commits of state every 5 minutes; no second forward ledger; live and nightly evaluators never race on one durable store.
- **Stale behavior:** stale inputs demote to `STALE` presentation with age (§13); a kill switch exists from PR-4 onward; liveness is watchdogged (precedents: #5487 dead-man switch, #5571 rescue lane, #5555 stale-frame action safety).

### 7.1 The designated live mechanism: nightly threshold inversion + snapshot path stats (Track B §6)

The house already runs a 5-minute Prophet live lane whose core law is: **the intraday lane never re-derives a signal.** `engine/prophet_live/armed_pack.py:3-8` re-runs the close-only gate nightly with candidate provisional closes appended as *the next session's bar* (append-not-replace semantics — measured to change 45/180 names), records the price interval over which the verdict holds, and the */5 lane only compares a delayed live quote against those precomputed numbers, with a per-pass adjusted-vs-raw **basis audit** and `live/delayed(~Nmin)/last_rth/eod/dark` state grading.

Radar adopts the same mechanism for its oscillator-state conditions: StochRSI-K (and K×D relations) as a function of *today's provisional close* is monotone/piecewise-monotone (reviewed and confirmed, Track F: RSI monotone ↑ in the live close; `rawk` saturates rather than reverses when today's RSI becomes the rolling extreme; K, D, K−D, and the one-bar histogram delta all monotone), so **C1's arm condition (K<20) and C2's cross conditions invert nightly into per-name price thresholds** evaluated every 5 minutes against delayed snapshots — no intraday indicator recomputation, no new bar feed, full parity with the confirmed-bar math by construction. Two hardenings are part of the mechanism, not options: (1) **degenerate cases are explicit** — where no price reaches the condition (K = SMA(3) with high prior `rawk` values, or a flat-RSI NaN window), the pack emits `no_threshold_exists` for that name/condition rather than an absent or unbounded level; (2) **the stale-pack gate** (§5 matrix row): thresholds are only ever compared under `pack.as_of == last_completed_session()`. Path-dependent turn features that thresholds cannot encode (session low, rebound-in-ATR from it, intraday K path extremes) are derived from the same 5-minute snapshot stream and recorded as **path observations, not bar math** — and **replay of path features uses a 5-minute-sampled last-trade reconstruction, never raw minute lows** (Track F: minute-granularity lows are ≤ sampled lows, so a minute-low replay would fire rebound variants earlier and more often than live ever could). This is the PR-4 baseline architecture; anything requiring true intraday bars is deferred per §7.2.

### 7.2 The 4H tier and LIVE-state replay: entitled but unbuilt (Tracks B §4 + D §3)

**No minute-grain U.S. equity bar store is built in the Macro repo today.** The one intraday store that exists (`scripts/build_polygon_intraday.py` → `data/intraday/`, hourly, Polygon STANDARD **15-min delayed**, ~240 curated names, 4H aggregated client-side for charts) is the wrong grain, latency, and universe for replay or signal math — chart plumbing, not a signal substrate. **The entitlement, however, is confirmed**: Massive flat-file `minute_aggs_v1` from ≥2010-06-15, tick history to 2005, real-time REST/snapshots — with the masterplan's own strategy law: *episode-windowed files + per-name REST, never a bulk crawl* (a blanket multi-year backfill is TB-scale). Therefore:

- **LIVE-state replay (C1/C2 1D-LIVE forms):** PR-5 reconstructs provisional daily indicators from **episode-windowed minute aggregates**, fetched per episode/name — never a bulk minute store, never EOD fakery. Names/periods where reconstruction is refused run live-forward only (§5 replay rule). Confirmed-bar forms replay from daily bars regardless.
- **C3 (4H):** stays in the arena, built in PR-3 from vendor aggregates with **completed-4H semantics** under the session calendar; the existing delayed hourly store is not reused for it. Live/partial-4H stays a separate, default-off detector version.
- Any new intraday feed carries its own adjustment-basis reconciliation against the adjusted daily plane (§5 price-basis row).

### 7.3 Ratified reuse points (Track D receipts; decision recorded as `DEC:LER-LIVE-LANE-VPS-5MIN-REST`)

- **Timer:** a systemd sibling of `app/deploy/macro-live-prophet.{service,timer}` — 5-min cadence, offset behind the `:00/5` snapshot lane per the `:03/5` precedent, resource-capped, lowest scheduling tier. The GitHub workflow is a backstop only (measured cron gaps of 90 min–3h12m; it self-disables under `VPS_LIVE_PRIMARY`), with `permissions: contents: read` and zero git steps.
- **Market data: REST/snapshot only — Radar takes no WebSocket.** The Massive stocks WS slot is unclaimed estate-wide today, and the vendor **evicts the oldest connection on overflow** (a silent kill, not a refusal) — casual WS use is an outage generator. At 5-min cadence with threshold inversion (§7.1), delayed snapshots + REST (the pattern every existing collector uses, unlimited-call ~<100 req/s) are sufficient. If the tick-plane daemon (TP-1) ever ships, Radar migrates to its derived stream; Radar itself never opens the socket.
- **Payload:** `live/entry_radar.json` written atomic-rename into the `MACRO_LIVE_DIR` ladder (`$MACRO_LIVE_DIR` → `/var/lib/macro-live/public/live` → `site/live`), **deliberately omitted from the Caddy allowlist** so it inherits the regwall/paywall gate with zero new gate code (the `prophet_live.json` 401 precedent). Client: the `dashboard.html.j2` prophet-live block is the literal template — 60–120s visibility-gated poll against the 5-min producer.
- **Event spool + durable evidence:** one R2 object per pass-with-a-transition under `live_flow/entry_radar_events/**` (PRIVATE_OPERATIONAL, `r2io` conventions); `scripts/reconcile_entry_radar.py --nightly` is the **sole** durable writer (→ `data/entry_radar/forward.parquet`), gated by `ledger_lane.nightly_advance_enabled()`; the intraday lane writes R2 + live dir only, enforced the same three-layer way as prophet-live (workflow read-only perms, no git in the service, module docstring law).
- **Session window:** reuse the `engine/prophet_live/live_states.py::in_window()` two-layer design (UTC systemd window spanning both DST regimes; ET + `lib/nyse_calendar.is_session` + config window + grace inside, fail-soft) and the `last_completed_session()` → `stale_pack` discipline.
- **Liveness is mandatory, not optional:** silence is this estate's default failure mode (the US bake went dark for two sessions, #5487; the Breathing Platform evening lane failed invisibly for a day). PR-4 registers a **positive, content-advanced liveness signal** with the sentinel/freshness machinery, and inherits #5555's law: no live "enter/candidate NOW" instruction off a stale or dead tape.
- **Breathing Platform:** its 5-min breathing lane is a *sibling pattern to copy*, not infrastructure to plug into — its evening W-L1 gate is unproven end-to-end as of the last narrative doc. Radar does not couple to it.
- **Sizing reality (anchors, not limits):** nightly arming precedent probes ~1,730 names in 420s on 4 cores; the planned tick-plane pilot caps at 600 symbols; existing live loop runs 150 names at 60s. A 500–1,500-name Probe Set at 5-min nightly-inversion + snapshot-compare sits inside proven envelope.

---

## §8. STRUCTURE / LEADERSHIP MODEL (context vector, not a gate)

Structural feature vector (no binary gates):

- **Prior leadership:** 20/60/120-session returns; RS vs QQQ/SPY and vs sector; proximity to prior high; prior breakout behavior; trend persistence.
- **Current damage:** pullback from high (raw and ATR-normalized); 20/50/200DMA relationships; whether defined structure failed; gap/catalyst classification.
- **Relative resilience:** stock pullback vs sector pullback; stock washout vs market washout; oscillator reset with price structurally intact (the partial-washout-with-resilient-price case is explicitly valuable).

These features feed cohort assignment (§12), ranking research (§9), and the NVDA/NFLX/TSLA archetype separation: leader reset must be distinguishable from damaged-trend rebound even when the damaged name's oscillator looks prettier; gap/catalyst episodes are their own context, never pooled blindly.

**Rebound quality** (measured after arm; marginal contribution researched, never all required): first rebound from local low in ATR; rebound vs QQQ/sector; volume participation/RVOL; VWAP-reclaim or other already-sanctioned structure; repeated-failure vs clean-first-turn; histogram acceleration.

---

## §9. SCORING DOCTRINE — TWO SCORE TYPES, NO HAND-AUTHORED EDGE

- **Detector Score** (per detector, immediate): descriptive recipe-match strength. Versioned formula, published subcomponents. **Not a probability.**
- **Research Priority** (cross-detector ordering, PR-6): deterministic, transparent composite for operator use, labeled **ACCRUING / RESEARCH PRIORITY**. Subcomponents and provenance always inspectable ("TSLA 91" must decompose on click). No 30/20/20-style hand weights presented as edge.
- **Opportunity Score** (PR-7 only, after honest sample): outcome-calibrated estimates — P(positive at H), P(target before invalidation), E[return_H], E[MFE_H], E[MAE_H], tail MAE, E[cost] — ranked through an explicit utility: expected favorable outcome − downside burden − execution cost − uncertainty penalty. Coefficients set at PR-7 pre-registration, not retrofitted. **Uncertainty shrinkage mandatory** (empirical-Bayes toward cohort mean): 4 spectacular small-cap observations must not outrank 400 moderately strong ones on fake certainty.
- **Language law:** no user-facing "validated", no probabilities, no "92% winner" until Evaluation OS promotion gates clear. Hotness admits; it never adds bullish points (attention-chasing evidence cuts both ways). The precise line (Track F): **admission-time attention levels** (the Layer-C variables as of admission) never enter any score; **post-arm rebound participation** (§8's volume/RVOL response measured after the washout arms) may enter ranking research, but only under the same conditional-incremental-value bar as lobe families — it is a candidate feature, not a granted weight. Lobe badges (OPTIONS / DARK POOL / ETF FLOW / THEME / SMART MONEY) display with provenance; five badges ≠ +25 — incremental value per family must be demonstrated conditional on the technical setup before any weight is granted.
- **Asymmetry definition:** attractive probability × magnitude of favorable excursion, constrained adverse excursion, nearby falsifiable invalidation, acceptable execution cost — measured on the §10 outcome set. **Never drawdown magnitude.** A −50% broken name is not asymmetric; a −12% leader accelerating off valid support may be.

---

## §10. FORWARD OUTCOMES, FALSE START, COSTS (pre-registered, frozen 2026-08-13)

**Outcome attachment per episode:** forward return; MFE; MAE; time-to-positive; time-to-MFE; target-before-invalidation probability; gap-through-invalidation frequency; **and benchmark/sector excess** (`excess_vs_bench` vs SPY, `excess_vs_sector` vs the sector-matched ETF — the fields whose absence undid Prophet's headline, per §2). Granularity: session closes always; intraday minute path where minute data exists (flagged per-episode). **Sign conventions follow the house precedents exactly** (Track E §6: `engine/forward_dist.py`, `engine/grading.py`, `engine/track_scoring.py`): MFE ≥ 0, MAE ≤ 0, both over the strictly-forward window (decision, decision+H]; any capture ratio guards the strictly-positive-MFE trap (`MFE_FLOOR`). The nightly reconciler is gated by `engine/ledger_lane.py::nightly_advance_enabled()` — the mechanical form of the single-advancer law — and never writes from the intraday lane.

**Risk geometry per candidate:** support/invalidation distance; ATR-normalized risk; prior swing low; nearby resistance; prior high; realistic spread/slippage.

**Horizons:** primary **H = 10 trading sessions**; secondary diagnostics {3, 5, 21}. All detectors graded at the same primary H for comparability; per-detector "intended horizon" may be registered additionally at PR-3 (before replay).

**Reference units (P0 frozen per bar-state — Track F B5):** LIVE-state detectors (C1/C2) → P0 = last trade observable at the decision timestamp. Confirmed-bar detectors (G0, C3, C5, C4-features) → P0 = the first trade after `known_at`, reconstructed from episode-windowed minute aggregates; where minute reconstruction is refused, the **next session's close** (never the signal bar's own close — the shared store carries no `open` column, so "next open" is not computable from it, and filling at the close that *created* the signal is self-dealing). A0 = ATR(14, Wilder, true-range on daily OHLC) as of the prior confirmed close; every episode records `atr_basis`, and episodes on a close-only ATR proxy are **excluded from the primary false-start read** (close-proxy ATR is systematically smaller, making the 1.25×A0 breach easier).

**Outcome granularity (uniform primary):** the primary MFE/MAE/false-start read uses **daily high/low bars for every episode** (the store has them for all names and eras); the minute-path read is secondary and flagged, because minute availability (≥2010-06-15, refusable per episode) would otherwise vary measured excursion magnitude with data coverage rather than signal behavior. **Delisting/truncation:** a name that stops trading inside H is censored at its last trade with `terminated_reason` recorded — never dropped, never extrapolated; replay-era membership is disclosed as survivorship-shaped where only current constituent artifacts exist (§0 R-1).

**False start (frozen):** an episode that reached CANDIDATE is a false start iff, within H=10 sessions of `candidate_at`:
`MAE ≥ 1.25×A0 before MFE ≥ 1.00×A0`, **or** the 1D confirmed StochRSI re-enters K < 20 with a price low below the episode's washout low.
Reported: false-start rate; median MAE on false starts; time-to-failure. A 27-cell sensitivity grid {favorable 0.75/1.00/1.50×A0} × {adverse 1.00/1.25/1.50×A0} × {H 5/10/15} is declared now as diagnostic-only and pre-counted in the look ledger.

**Episode hygiene (frozen):** one live episode per (ticker, detector_id); episodes end only via INVALIDATED / EXPIRED / RESOLVED and are never deleted. Re-arm eligibility after an episode ends: 1D confirmed K > 50 for 2 consecutive sessions, or 15 sessions elapsed, whichever first. ARMED/TURNING without candidate-promotion expires after 15 sessions. CANDIDATE resolves at H.

**Costs (frozen for the primary read):** per-side cost = max(measured median half-spread at signal timestamp when NBBO is available, liquidity-tier floor); tier floors 5 bps (median daily dollar volume ≥ $50M), 15 bps ($5–50M), 40 bps (< $5M); round-trip applied to net outcome metrics. Implementation mechanics (spread measurement window etc.) are pre-registered in PR-5 **before** any outcome is read; deviations logged PSS-style (pre-outcome, in the prereg commit).

---

## §11. COMPARISON DESIGN — CONTROLS, RANKING VALIDATION, OVERFITTING

**Registration (decided; Track E §1):** Radar registers into the shipped Evaluation OS (`engine/qledger.py`) — `make_claim(desk="entry_radar", claim_family="entry_radar_<detector_id>", scope_type="entity", direction=1, horizon_d=10, timestamp_quality=…, bench="SPY", control=<sector-matched ETF>, falsifier=…, check_by=…)`, appended via `register_batch()` **only from the PR-5 nightly reconciler**. One family per detector (all long-only, so the mixed-direction pooling rule never engages). **Registration horizon (corrected by Track F review, verified against `engine/qledger.py:1213-1220`):** `in_scope_horizons(10) == [5]` — an off-rung `horizon_d=10` would grade at 5 sessions only, reproducing the exact "zero verdicts at the declared horizon" defect §2 cites. Radar therefore registers claims at **`horizon_d=21`** (on-rung: grades at [5, 21], bracketing the program's H=10), while **H=10 remains the program's own pre-registered primary read, computed by the PR-5 ruler** — reported alongside the qledger 5/21-session grades and never presented as an Evaluation OS graded verdict. qledger's internal `ACCRUING` (< 25 distinct dates) and the external 50-observation reporting floor (`MASTERMIND_EVALUATION_STANDARDS.md` §4.7) are different thresholds — Radar copy never conflates them. Any assertion over Radar's append-only stores is monotonic, never exact-count (append-only law P2). Direct prior art: `engine/basket_turn_cohort.py` — a washout-turn-adjacent family registered post-kill as an "Expected-NULL forward meter, no backfill". Radar's families register with the same humility, made explicit in the registration text: **"accruing forward meter; registration implies no directional performance claim; no backfill; promotion requires clearing the §11 gauntlet and the `DNR:KILL-WASHOUT-TURN` falsifier territory by name."** (Radar does not pre-declare expected-null — G0 carries genuine motivating evidence — but it claims nothing until graded.)

**Ruler reuse (PSS §7, with declared deltas; Track E §2):** per-name-first aggregation (never pooled-fire — the E1 errata is the standing reason); month-cluster bootstrap, NB=1000, seed pinned per family (ticker-only clustering forbidden, DT-R14); era discipline per DT-R16 (declared FIT/TEST split; full-sample-only effects disqualified; grading on TEST only); matched-construction placebos where a mechanism-stripped analog exists, plus the §11 stratified cohort controls (richer than any single mirror placebo); the **C32 decline-deceleration conditioner graded WITH and WITHOUT** (no early family survived 2022 without it — Radar's gap/catalyst and deep-washout cohorts inherit this check); incumbent benchmark = the fixed-2W-rung Stoch-RSI<20 cross (`engine/canon.py::stoch_rsi_kd` via `engine/washout_turn.py`), whose −2td trough-timing figure is the bar every prior W-SIG family failed to beat. Declared deltas: primary lens is §10's H=10 forward window (live, intraday-capable) instead of `mae63`/`prox±31td`, with MFE/MAE/proximity carried over in spirit; controls are the live stratified cohort rather than one frozen analog.

**Look ledger (decided):** Radar's look ledger **is** the existing `TrialLedger` (`engine/trial_ledger.py` — `log_trial()`, `log_declared_budget()`), the same API Amendment-3's RUL-32 mandates, under one flat pooled family per the `engine/rule_experiments.py` R1 registry precedent (append-only JSONL, single writer, `verify_spec_hashes()` before any run is accepted — also the concrete precedent for `detector_spec_hash` and PR-2's spec-hash gate). No new look-count store.

**"The stock went up" is not edge.** Every candidate event gets matched controls drawn from probe-set members that did **not** fire that detector within ±5 sessions **and do not fire it anywhere in (decision, decision+H]** (a day-+6 firer carries its post-fire path into the control mean — excluded/censored). Names structurally unable to fire because of §10's re-arm blackout are flagged `suppressed_by_rearm` and excluded from the control pool. Matching variables (frozen): session date; sector; market-cap bucket (>$200B / $10–200B / $2–10B / <$2B); dollar-volume decile; trailing-60d return quintile; realized-20d-vol quintile; hotness tier (admitted-not-fired); **63-bar close-min proximity decile** (the NC-2 provision above). Primary read = excess vs control mean, per-name-first. Mechanical details (k, distance metric) pre-register in PR-5 before outcomes are read.

**Common-eligibility rule (Track F B8):** detectors have non-comparable warm-ups (G0 needs ≥90 3D bars ≈ 270 sessions; C5's monthly dwell ≈ 28 months; C1/C2 ≈ 17 sessions). Every cross-detector comparison is restricted to `(ticker, date)` pairs on which **both** detectors are computable; the eligibility gap itself is reported separately. The §12 IPO/young cohort (< 252 sessions) is therefore **C1/C2-only** — G0 and C5 cannot fire there by construction, and no comparison may pretend otherwise.

**NC-2 proximity kill-arm (inherited from RUL-28, mandatory — implementability corrected by Track F):** every primary comparison below is additionally read under a proximity de-confound arm (63-bar close-min proximity band fixed-effects, or the closest feasible equivalent registered at PR-5). Because washout-arming detectors fire *at or beside* recent lows by construction, three provisions make the arm meaningful rather than vacuous: (a) a **63-bar close-min proximity decile joins the frozen matching variable set**, so controls share the candidates' band; (b) every NC-2 read ships an **overlap diagnostic** (share of candidates with ≥1 same-band control) with a pre-registered overlap floor below which the arm reports **UNINFORMATIVE — never KILLED** (no common support is not a proximity shadow); (c) for washout-arming detectors the operative counterfactual is **turn-vs-no-turn at equal proximity**, not fired-vs-unfired. An excess that dies at equal proximity is a proximity shadow and is reported as such, never as detector edge — the exact instrument that killed the 2W washout×turn seed, run on Radar by construction.

**Primary registered questions (the confirmatory family, FDR-controlled at BH q=0.10; one pre-declared primary metric each; everything else exploratory and labeled so):**
1. Do G0 candidates outperform matched controls at H=10, net of §10 costs? *Primary metric: per-name-first mean excess vs control at H=10.*
2. Does C2 beat C1? *Contrast: C2 vs **C1-minus-C2** (C2 is a strict subset of C1). Primary metric: excess-vs-controls difference at H=10.*
3. Does C3 beat C2 on false starts without giving up excess? *Primary metric: false-start-rate difference; excess difference is the guardrail (secondary, non-inferiority read).*
4. Do lobe-enlisted G0 candidates beat G0-alone? ***Live-forward only** (Track F B2: ephemeral producers make historical enlistment unreconstructible — replaying it from today's state is look-ahead), additionally matched on cap/ADV/hotness tier (Layer-D auto-admission draws from different strata). Primary metric: excess difference at H=10.*
5. Does G0 beat the existing entry gauge on earliness at equal-or-better false-start burden? *Earliness estimand (frozen matching rule per §3.1's lead-honesty law): matched pairs = each G0 candidate joined to the same name's next incumbent-gauge fire within 30 sessions; earliness = session gap on matched pairs; **coverage (share matched) always reported alongside**; unmatched candidates are reported, never dropped silently. False-start burden compared on the matched set.*

**Ranking validation (the product is a ranking engine):** top-5/top-10/top-decile outcomes; score-decile monotonicity; rank IC where appropriate; top-k MFE/MAE and expected utility; ranking stability; false-start rate by score bucket. If score 90 performs like score 40, the score is decoration and PR-7 does not ship.

**Overfitting controls:** the TrialLedger look ledger above (every parameterized family enumerated with cell counts before running; every executed look recorded); pre-registered comparison families above; **the "pre-register in PR-5 before outcomes are read" clauses in §10/§11 are mechanical, not self-attested** (Track F): the PR-5 prereg is an earlier-merged commit whose hash is logged via `TrialLedger.log_declared_budget()`, and the reconciler refuses to attach outcomes unless that hash verifies — mirroring `engine/rule_experiments.py::verify_spec_hashes()`; walk-forward for anything fitted; **untouched holdout** = the most recent 6 months of replayable history at first replay, plus everything after the live-forward start; kill-registry discipline for dead constructions; prospective champion/challenger comparison is the decisive evidence. No 700-combination sweeps publishing the prettiest curve. Leak tests mirror the ratified Amendment-3 instruments (RUL-31: last-completed-bar known-date mapping, shift audit + truncation-invariance fixture per primitive — existing implementations `tests/test_entry_primitives_a3.py`, `tests/test_bottom_sensors_a3.py`) rather than inventing fresh shapes.

**Evidence ladder:** register → historical replay (PIT) → walk-forward → shadow live (every candidate recorded before outcome) → live-forward (decisive; required for promotion per house law).

---

## §12. COHORTS (same UI, separate calibration)

Minimum cohort set: leader reset; partial/shallow washout; full daily washout; deep multi-timeframe washout; gap/catalyst repair; damaged-trend rebound; IPO/young; small-cap/high-vol momentum. Cohort assignment from §4/§8 features. Cohorts share the interface, never blindly share calibration. Regime tagging (market-level washout vs quiet tape) recorded on every episode for later conditioning.

---

## §13. LIFECYCLE ≠ PRIORITY, AND THE EPISODE CONTRACT

Machine lifecycle per (ticker, detector): `PROBING → ARMED → TURNING → CANDIDATE → INVALIDATED | EXPIRED | RESOLVED` (append/history-preserving; user-facing simplification: Probing / Pre-candidate / Candidate). `detector_state`, `priority_score`, and `manual_state` are independent dimensions — a priority move from 91 to 63 changes no lifecycle fact.

**Episode contract (frozen):** `mastermind.live_entry_episode.v1`: `episode_id, ticker, detector_id, detector_version, detector_spec_hash, state, first_armed_at, candidate_at, last_observed_at, market_session, bar_availability, feature_snapshot, universe_admission, lobe_nominations, price_at_signal, risk_geometry, detector_score, research_priority, opportunity_score, data_quality, freshness, evidence_refs` — plus the §5 availability block on every stored reading. **Per §18 A1, episodes reference `event_id`s in the append-only `mastermind.entry_event.v1` store** (fields and typed promotion/de-dup edges defined in A1.2.1), which holds every recorded expert-event family with per-field `field_origin` honesty — preserved verbatim from the emitter where the emitter carries it, marked `radar_derived` where it does not, so no downstream program must reconstruct a lost distinction. A candidate leaving today's board still exists in the ledger forever.

**Manual disposition (V1 or immediately after):** `Watch / Pass / Took / Rejected` + short reason tags (broken structure, earnings risk, too extended, great leader, bad liquidity, theme weak), timestamped. Not trained on in V1; first used to answer "what does the operator see that the model misses?"

---

## §14. UI DIRECTIVE (operator, 2026-08-13) AND PAGE CONTRACT

**Operator directive (supersedes the handoff's softer §33 language):** *take yesterday's new Prophet Board as the direct design reference — Live Entry Radar should look like a sister product built from that exact card/layout language, with only the information architecture changed.*

Frozen consequences for PR-8/PR-9:

- **Reference artifacts:** `templates/_prophet_card.html.j2` + `templates/_prophet_receipts.html.j2` and the Prophet Board reference-integrity evidence chain (`research/reference_integrity/prophet-board-5514-*`; R3 verdict REVISE, R4 closure PR #5560). PR-8 pins against the **then-current R4-resolved** reference — sister product in that exact card/layout language; IA changes only; known R3/R4 defects are not inherited; the RIG process runs on the Radar reference before migration.
- **Not inherited:** Prophet's seven-cell plan lifecycle and Prophet product semantics. Same design language; different information model.
- **Page hierarchy:** header (LIVE ENTRY RADAR; "Early asymmetric entry opportunities across the U.S. market."; Probe Set count / Pre-candidates / Candidates / source freshness / session state; no prose wall). Lanes: Best · Grey Dot · 1D Washout · 1D Turn · Deep Washout · Intelligence · All — detectors visually comparable, never blended behind one score. **The Grey Dot lane is confirmed-bar, refreshed once nightly from the Terminal slice, and stamped so** (`nightly · confirmed`) — §7.1's intraday inversion covers the 1D lanes only; no provisional-3D form exists in V1.
- **Card anatomy (glance tier):** ticker/name; live price/change; Priority N; lifecycle badge; detector lane chips; cohort line; component states (1D Stoch / MACD-RSI / Structure / Lobe evidence); zone + invalidation footer; freshness stamp with bar state (`5m ago · 1D LIVE`).
- **Expanded drawer answers, in order:** why is it here (admission); why now (detector evidence); what is recovering (oscillator/momentum); still structurally strong? (context); what makes it asymmetric (risk geometry + conditional history); what else sees it (lobes); how trustworthy is this number (sample support, calibration status, freshness); where did it fire (mini chart: arm, trough, turn, promotion).
- **Provisional visual language:** `1D LIVE · provisional` never masquerades as `Daily confirmed`; stale readings demote visibly (`STALE · last usable reading 14m ago`) and never retain a green candidate look (stale-frame law, #5555 precedent).
- **Why-now copy is mechanical** ("Daily washout is reversing; 4H momentum turned higher"), never promotional ("huge upside", "92% likely", "AI says buy"). Falsifier/refutation vocabulary never front-facing (house law); glance tier uses plain-word stance within the design-system word budgets; EN + ZH first-class; dark + light intentional; mobile works.
- **Required PR-8 crops:** desktop dark/light EN, desktop dark/light ZH, mobile dark EN/ZH, no-candidates, stale, partial-data, many-candidates, multi-detector ticker, lobe-only probe, IPO candidate, anonymous/premium state if applicable — committed under `mockups/refs/entry_radar/`.

---

## §15. PR SEQUENCE (build order is law; each PR names its §0 gates)

| PR | Scope | Not done unless |
|---|---|---|
| **PR-0** | This contract + Track A–E censuses + workstream records. No production behavior | All eleven PR-0 deliverables present; kill-registry compliance section complete; all PENDING slots resolved; G0-VIS closed (§18 A1) |
| **PR-1** | Probe universe + enlistment bus (broad eligibility, hot universe, core, lobe nominations, IPO handling, dedupe/provenance, active Probe Set) | A lobe-nominated small cap outside the hot universe appears in the Probe Set at the next eligible refresh with source evidence intact; **every nomination event spools durably from day one** (ephemeral producers are otherwise historically unreconstructible — §5, §11 Q4) |
| **PR-2** | Detector framework + G0 exact (interface, independent detector state, Grey Dot implementation/adapter, parity tests, detector event schema). No score fusion | Parity fixtures green; G0-VIS closed; `spec_hash` stable; zero diffs on Prophet paths |
| **PR-3** | 1D/4H challenger family (live provisional reconstruction, confirmed versions, turn features, 4H variant, MTF context, strict availability timestamps) | EOD-mutation test proves a final close cannot leak into an earlier intraday observation; every §5 matrix row for used inputs has its test |
| **PR-4** | Live evaluator on the existing VPS plane (RTH evaluator, state transitions, ephemeral payload, event spool, stale behavior, kill switch, backstop if appropriate). No automatic trading | 5-min cadence measured across a full RTH session; single-writer law intact; stale demotion observed; **positive content-advanced liveness registered with the sentinel machinery** (silence is the estate's default failure mode); no live instruction off a stale/dead tape (#5555 law) |
| **PR-5** | Forward evidence + replay (nightly reconciliation, immutable event history, outcomes, MFE/MAE, false starts, matched controls, detector comparisons, cohort cuts) — Evaluation OS conventions, no bespoke ledger | Look ledger operating; §11 registration filed before first read; holdout untouched |
| **PR-6** | Deterministic Research Priority for operator use, marked ACCRUING | Provenance decomposition on click; no probability language |
| **PR-7** | Outcome-calibrated Opportunity model (only after honest sample) | Calibration + uncertainty + top-k evidence + monotonicity report + champion/challenger results; promotion language only per house law |
| **PR-8** | UI reference + RIG for `entry_radar.html` per §14 | All §14 crops; independent product + visual critique run |
| **PR-9** | Production UI + live verification during an RTH session | Source→evaluator→payload→page latency measured; promotion/invalidation/stale observed live |

Backend does not wait for design; PR-1..PR-5 proceed while the Prophet Board R4 cycle resolves.

---

## §16. PATH / COLLISION PLAN

**Radar owns (new paths only):** `engine/entry_radar/**`, `scripts/entry_radar_*.py`, `templates/entry_radar.html.j2`, `site/entry_radar.html`, `data/entry_radar/**` (durable, nightly-written), live ephemeral state under the existing live-artifact ladder (exact home per Track D), `research/LIVE_ENTRY_RADAR_*.md`, `research/live_entry_radar/**`, `mockups/refs/entry_radar/**`.

**Radar never touches:** `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`, `engine/prophet_*.py` (WS:PROPHET-US-ENTRY-TIMING territory), `engine/washout_turn.py` and `engine/mtf_upturn.py` (adjacent display organs — boundary stated in Radar docstrings), Prophet templates/payloads (read-only design reference), Terminal repo internals (parity via artifact/fixtures only), Mastermind control plane.

**Non-interference is mechanical (Track B §2.4):** Radar is provably clear of Prophet iff it (a) adds no import into the five gate/presentation modules above; (b) does not alter `ANCHOR_ERA`, `BUYABLE_TIERS`, `FRESH_TICKS`, `EARLY_CROSS_BARS`, or the frozen params at `engine/confluence_tiers.py:56-59`; (c) writes no key those modules read. Every Radar engine PR runs `git diff --stat` on those paths and prints it in the PR body.

Verified this session: no open PR, no worktree, no tracked file, and no Agent OS workstream claims any of the owned paths (collision check 2026-08-13: `git worktree list`, open-PR sweep, `git ls-files`, `agentos/workstreams/` grep).

**Do-not-build list (binding):** no StochRSI-only buy engine; no Prophet gate changes; no deepest-drawdown ranking; no zero-print requirement; no depth-as-positive assumption; no hotness-as-bullish; no per-page mention points; no HTML scraping for nominations; no mixed StochRSI implementations without parity; no EOD-faked intraday history; no GitHub-cron product cadence; no second WebSocket owner; no second durable evaluation ledger; no arbitrary 100-point "AI score" sold as edge; no silent signal deletion; no auto-trading; no full-3D-confirmation-everywhere rebuild of the problem this program exists to solve.

---

## §17. SUCCESS SHAPE (operating definition)

At 11:35 ET the operator opens Live Entry Radar: ~900 probed, ~30 in washout, ~11 pre-candidates, ~5 turning; the board ranks them with detector chips, cohort lines, lobe badges, zone/invalidation, freshness (`1D LIVE · 5m`); clicking a name yields the mechanical why-now trail (fired 10:55; K bottomed 6.3 → 18.7; histogram trough + three rising observations; +1.1 ATR off the session low; 60d RS high; two independent lobes; reading provisional; sample accruing). The operator decides: buy, watch, or ignore. That is the product.

---

## §18. AMENDMENTS (append-only)

### A1 — 2026-08-13 — CEO amendment: G0-VIS closure + Expert Preservation ruling (pre-freeze; operator-directed)

**A1.1 — G0-VIS is CLOSED.** The operator confirmed the raw grey anticipation-dot family against the computed fired-date evidence. Closure is **family-level by explicit CEO message** — the §3.3 named-dot protocol is waived by that message and this is recorded here so the closure stays auditable. G0 is frozen as **the exact raw grey-dot emitter already archaeologized** — the §3.1 *mask*, with no spec change. **G0's event population (frozen):** because the artifact's `early_dots` field carries only *unpromoted* dots, an artifact-consuming adapter reconstructs the full mask population as `early_dots ∪ bottom_watches[kind=="early_dot"].ts` — otherwise G0 silently loses exactly its deep-washout cohort (3 of NFLX's 11 dots ≥2025). This union is pinned as a new F2 assertion (§3.2). The washout-promoted amber `EARLY` marker remains a **distinct recorded family** (A1.2). **Provenance honesty about the promotion link:** fixtures F2/F3 pin the emitter's *de-duplication* (what it suppresses), not any link field — the artifact carries no link, so `promoted_by` edges are **Radar-synthesized** (ts-join of the two streams) and pinned by a new fixture assertion of their own; and on `blocked_trigger` bars no `early_dot` event exists at all, so that de-dup edge is **known-lossy from the artifact**, recoverable only via the §3.2 locked-spec fallback recomputation, and is recorded as such rather than silently absent.

**A1.2 — Expert Preservation ruling (architectural dependency, binding on PR-1..PR-9).** G0/grey is **not** the universal incumbent entry signal, and this program must not collapse Terminal's entry grammar into "grey versus challengers." Terminal currently exposes multiple **mechanistically distinct entry-event families** — at minimum: raw grey / early-dot anticipation; washout-promoted amber `EARLY`; `STARTER — awaiting confirmation`; `STARTER — confirmation failed`; `RE-ENTRY — trend reclaim`; `RE-ENTRY — block repair`; classic confirmed BUY/REBUY where applicable — alongside Radar's own C1–C5 detector families. **These are candidate experts, not synonyms.**

Binding consequences:

1. **Event-level provenance preservation, in an addressable store.** Recorded entry events live in an append-only **`mastermind.entry_event.v1`** store keyed by `event_id`, each carrying: `producer`, `detector_id` (null for non-arena recorded families), `family`, `subtype`, `stage`, `quality`, `context`, `signal_ts`, `signal_known_ts` (the event's own emission clock — distinct from, and joinable to, §5's per-reading `source_bar_time`/`source_bar_known_at`), `source_identity` as a struct `{source_hash, signal_era, detector_spec_hash}` (never one opaque string), `scored_authority` (recorded from the emitter, e.g. Terminal's `scored: false` — a recorded fact, never a grant), `family_first_available` / `family_era` (the amber-EARLY family has zero history before Terminal `935389d4`, 2026-08-11 — without this field the downstream program reads structural absence as negative evidence), and a **per-field `field_origin ∈ {emitter_verbatim, radar_derived}`** marker (for G0 specifically, `early_dots` is a bare date-string side channel — no type, no price, no quality, capped at 40 — so most A1 fields there are Radar-derived and must say so; the 40-cap also bounds recorded grey history unless the raw emission is read per §3.2). Promotion/de-dup links are typed edges `{relation: promoted_by | dedup_suppressed_by, target_event_id}`, never a scalar. Episodes (§13) reference `event_id`s.
2. **No flattening.** Nothing downstream of Radar may be forced to reconstruct lost distinctions: `raw grey` vs `washout-promoted EARLY`, `STARTER pending` vs `STARTER failed`, and `RE-ENTRY trend-reclaim` vs `RE-ENTRY block-repair` must remain distinguishable in the ledger. No `entry_signal=true` boolean, no generic "Golden Oracle" category, anywhere in Radar's stores or payloads.
3. **Adapter obligation (PR-2).** The Terminal adapter ingests the unified `mastermind.indicator/v1` signals stream **preserving the emitter's own type/subtype/quality/stage strings verbatim** plus artifact identity; exact family enumeration with emitter receipts for the STARTER/RE-ENTRY families is PR-2 archaeology (the artifact schema already carries these fields per Track A §4 — the obligation is to not drop them). Family keys are minted at PR-2 from receipts, never invented ahead of them.
4. **Recorded ≠ arena.** These preserved families are ledger/display-tier recorded experts. The §11 confirmatory arena and its registered questions are unchanged; any promotion of a recorded family into the graded arena requires a further §18 amendment with look-budget registration.
5. **Scope boundary (hard) — and the standing kill the future program must clear.** Radar does **not** expand into stock classification, personality modeling, per-stock strategy optimization, or adaptive routing. A separate **Stock Identity / Expert Routing** program (future; deliberately not created here — no such *program* exists in the registry as of this amendment) will test which event families best localize opportunities per security and identity epoch. That future program is hereby put on notice of **`DNR:KILL-OUTCOME-AUDITION`** (`research/DO_NOT_REBUILD.md` §2): per-name timing-tool selection by in-sample outcome audition is KILLED two-ruler at n=1,300 names / 109,974 TEST signals (zero OOS persistence; per-name "home rungs" are ruler-dependent — 5/7 defensives flip), and *"any audition-derived per-name gate/rank/size anywhere is this row's construction."* The row's live carve-out is the lawful path: **structure-MEASUREMENT tailoring stays open** (upgraded under the timing ruler); in-sample best-of-grid per name does not. Radar's preservation obligation is untouched by the kill — recording expert identity is legal and required; *selecting* experts per name by outcome audition is the killed construction. Radar's whole obligation is provenance sufficiency: **Radar discovers and records experts; a separate system later learns which experts to trust for whom — by a method that clears that kill.** (`engine/stock_personality.py::setup_compatibility` is the already-identified natural describe-side consumer, §2 — the boundary there stands: Radar may be read, never written into.)
6. **Motivating observation (display-tier, not a validated claim — and explicitly weaker than the standing null):** operator visual review across KRUS, MCK, NVDA, REGN and YELP suggests different securities respond to different entry mechanisms. Recorded as the commissioning observation for the downstream program only. It is a 5-name visual read standing against `KILL-OUTCOME-AUDITION`'s n=1,300 measured null on per-name selection persistence — motivation to *preserve distinctions*, never evidence that per-name selection works. Radar makes no per-security claim. The family names quoted in this amendment's enumeration (`STARTER — awaiting confirmation`, `RE-ENTRY — trend reclaim`, etc.) are **operator-observed UI labels**, not verified emitter enums — only `early_dot` and `blocked_trigger` have emitter receipts today; the rest are minted at PR-2 per A1.3.

The PR-1→PR-9 sequence continues as commissioned; this amendment adds recording obligations only.
