# Problems with the US Standout Stock Engine (`us_stocks.html`) — and where Fable should look for solutions

*Grounded brainstorm/audit prepared as input for Fable 5. Fable's job: refute / agree / upgrade / expand these problems and their candidate solutions with deep reasoning and novel twists. Every claim is cited to `file:line` or to live `site/factordata/us_standouts.json` (as_of 2026-06-30, verified 2026-07-01). Numbers were re-pulled from the live artifact; where a finding cited a phantom/mis-nested path, it is corrected inline. This is a problem map, not a spec — the solution directions are seeds, not commitments.*

*Method: 9 parallel subsystem readers → 9 theme deep-dives + an adversarial completeness critic + an average-user simulation → synthesis. 53 raw problems distilled. The contrarian section (§6) exists specifically so Fable does not "fix" things that are already correct.*

---

## 1. TL;DR

### The single deepest root cause

**The product spec (a fixed-width, imperative "34 BUYs — act now" board) is irreconcilable with the measured signal (a cross-sectional selection edge that is statistically ~zero).** The project's own deep+PIT harness (`reports/stock-conviction-phase0.md`, 2008–2025, 210 rebalances, ~419 names, `powered:true`) shows every candidate composite FAILS the deflated-Sharpe haircut; rank-IC is +0.008..+0.021 and **nothing clears FDR except insider — which is present on only 2 of 34 live buy rows.** Given a near-zero edge, you cannot honestly produce 34 differentiated high-conviction picks, because the signal to differentiate them does not exist.

Every downstream pathology is a **compensatory hack to fill the 34 slots the product demands:**
- `rank_by="bottoming-alignment"` is the gate because it is the only construct loose enough to admit 34 names (`build_stock_library.py:1594`).
- `potential_score` overwrites the honest edge-percentile because a washout×timing number produces more visual spread than a flat edge distribution (`build_stock_library.py:1457-1459`).
- `entry_open_first` floats a name to #1 because *something* must be #1 (`build_stock_library.py:1616`).
- The confirmer chips add apparent rigor to compensate for absent edge.

The recurring "headline says BUY, guts say neutral" contradiction exists because a **TIMING/HWM code path** and an **EDGE/VALIDATION code path** run in parallel and never reconcile — so the card says both. **Fix the wiring and you still have 34 coin-flips sorted more honestly.** The real fix is to let board *width* and *label strength* be functions of measured edge/regime: variable N, abstention allowed, "BUY" reserved for the FDR-surviving subset.

### The 5 highest-leverage problems

1. **The user-facing board ranks by a TIMING construct the project itself validated as return-dilutive/negative-IC**, while the one positive-IC leg (residual alpha) is demoted to a tiebreaker. Live: `corr(board_position, alpha) = +0.266` — higher-alpha names sit *lower*. The "reverted to alpha" fix in the research docs landed only on the sibling `setups.json` (rank_by="alpha", L1519), never on the board the user reads.

2. **The headline number is negatively correlated with the one edge leg.** `corr(displayed score, alpha) = -0.31`. WAB (alpha **+1.73**, sector rank **11/252**, a genuine leader) scores **26/neutral**; LKQ (alpha **-1.08**, rank **175/195**, a laggard) scores **75/high**. The displayed score is `name_score.potential_score` (a washout×timing quantity); the honest edge-percentile is computed and discarded into a hidden `rank_pctile` field. The median displayed score across the 34-name BUY board is only **31/100** (mean 36).

3. **The BUY headline is a static cycle-dict lookup that no confirmer, verdict, or validation flag can downgrade.** ETN (slot #1) ships state "FRESH BUY" / "BUY ZONE" / urgency "now" / entry "buy_now" while `verdict="Neutral — no clear edge"`, `validation_status="neutral_ic"`, `gex="caution"`, `vol_squeeze="EXPANSION"` (move already underway). 34/34 rows are `neutral_ic`; `gate_go=False` at file level — none of it reaches the headline. Verdict distribution on the buy board: **16 "no clear edge," 7 "Lagging," 8 "building a base," only 3 "leader (context)" — i.e. 23 of 34 buy candidates carry a neutral-or-worse verdict.**

4. **The board is one correlated macro bet wearing 34 hats.** Utilities (9) + Industrials (10) = **19/34 = 56%** of buys. `bottoming-alignment` mechanically selects whatever sector is simultaneously washed-out across weekly/3D/daily, so effective N ≈ 2–3 sector bets. The per-sector cap that would prevent this exists but is wired to the *wrong* strip.

5. **There is no forward track record and the honesty gate can never fire.** All three graders are empty (`n_graded=0`, 3-day log). The `gate_go` gate requires DSR≥0.90 on large-cap L/S — mathematically unreachable on this asset class — so `validation_status` is a constant `neutral_ic` on 100% of cards, discriminating nothing.

### The 5 cross-cutting threads (every problem is one of these five)

1. **Fixed-width fill pressure.** The board *must* emit ~34 BUYs. `bottoming-alignment` (loose enough to admit 34), the `potential_score` overwrite (spreads 34 flat-edge names into a visible range), `entry_open_first` (picks a #1 among ties), renormalized edge weights (fills the score when insider is absent on 32/34), and the missing per-sector cap (lets 19 names come from 2 sectors) are *all* mechanisms to populate slots the edge can't justify.
2. **Two decoupled code paths = two product promises.** A TIMING/HWM path and an EDGE/VALIDATION path run in parallel and never reconcile: `cycles.py` static-dict headline vs `stock_score` verdict; `potential_score` vs `rank_pctile`; `entry_signal.status` is confluence-gated but `row.state/label/urgency` are not. Any real fix must impose a single arbiter that makes the loud field a *function* of the quiet field.
3. **Missingness-as-neutrality.** Absent data collapses to a benign default instead of reduced confidence: insider absent → weight silently renormalized; risk inputs absent → tax 0.0 (reads as "de-risked"); valuation uncovered → band None; thin 323-day cache → same BUY label. The completeness metadata (`provenance.uncalibrated`, `n_axes`, `present`) exists but is never wired to demote.
4. **Validation machinery orthogonal to the shipped artifact.** The Phase-0 harness, `validation.py` (DSR/PBO/Clark-West), and the three forward graders validate composites the board doesn't use, grade markers the board doesn't emit, and run offline (not in `daily.yml`). The board's actual rank key (`bottoming-alignment`) was **never fed to the harness at all.**
5. **Regime-blindness at the board level.** The dispersion regime, `gate_go`, and `validation_status` all correctly compute "selection isn't paying / no validated edge right now" — and none of them modulate board width, label loudness, or ordering. The meta-signals are wired only to a per-name size multiplier that is itself an identity (`gross_mult=1.0`) in the modal state.

---

## 2. How the engine works today (mechanism map)

**Two independent board pipelines feed `us_stocks.html`:**

- **`setups.json`** — the "What to act on now" table — is `rank_by="alpha"` and HARD-gated on the validated MACD-2D × StochRSI-3D confluence (`is_buyable`, `build_stock_library.py:1519-1520`). This matches the research docs. It can be empty.
- **`us_standouts.json`** — the WIDE card board the user actually reads — is a separate, hand-rolled pipeline (`build_stock_library.py:1539-1622`) with `rank_by="bottoming-alignment"`. The validated confluence gate is **not** an admission control here; it is only a display badge + a `0.5·weight` tiebreak.

**The wide-board pipeline:**
1. Rank universe by conviction `composite_z` (L1542).
2. Admit names passing `_entry_ok` (cycle not blocked + `entry.z>0`) AND `_atier` MTF bottoming-alignment (L1553-1568); backfill near-aligned to `ALIGN_MIN_KEEP` (L1571).
3. Re-sort by `_combine_key` = alignment-tier → `composite_z` percentile + `0.5·confluence-weight` (L1580).
4. **Finally re-sort by `entry_open_first`** (L1616 → `setups.py:138`): `(0 if status=='buy_now' else 1, -score)`. Only 1/34 names is `buy_now`, so this unilaterally selects slot #1.
5. Write `buy[:120]` (yields 34), `watch` = leftover `composite_z>0` cap 24, `laggards` = bottom-12.

**The conviction composite** (`stock_score.py`): four signed-z axes — selection (EDGE: insider 0.50 / revision 0.30 / sue 0.10 / mom 0.10, `:93`), entry (cycle timing), tailwind (sector, 0.10), quality (0.30) — rolled with US weights `{selection .45, entry .15, tailwind .10, quality .30}` (`:193`). Selection is only 45% of the rank.

**The displayed number is swapped:** `attach_panel_scores` computes an honest within-market percentile of `composite_z` (monotone in edge); then `build_stock_library.py:1457-1459` moves it to hidden `rank_pctile` and overwrites the displayed `score`+`band` with `name_score.potential_score` = `100·trigger·(0.4+0.6·fuel)·survive·tailwind·confidence·edge_mult` (`name_score.py:225`), where `edge_mult` is clipped to `[0.70, 1.35]` (`:78`). The explanatory note is stripped for the US board (`build_stock_library.py:1462`).

**The headline** (state/label/action) is a static dict keyed on cycle state alone (`cycles.py:429-435`); `entry_signal.status` is a direct map from cycle urgency (`entry_signal.py:25`). Only `entry_signal.status` is confluence-gated (`:167`); the row-level `state`/`label`/`urgency` the card renders are not.

**The honesty layer is inert:** `validation_status` is a boolean pass-through of `gate_go` (`stock_score.py:1307`); `gate_go` is read from a committed JSON that requires DSR≥0.90 (unreachable). The `validation.py` toolkit runs only in offline harnesses, none in `daily.yml`. All three forward graders are empty.

**In the template:** `dashboard.html.j2:2397` computes a conviction-sorted `_board`, then `:2404` overwrites it with raw `_su.buy` (JSON `bottoming-alignment` order) — a dead-code sort. Tooltips at 2362/2364 variously claim the board is "sorted by conviction" and "ranked by α"; it is neither. This is why REZI (score 95) renders at position 2, *below* ETN (score 47).

---

## 3. Problem clusters (ordered by leverage)

### Cluster A — The ranking optimizes the wrong quantity (and buries the right one)

**A1. The board ranks by a timing construct with negative forward-return IC.**
- **Evidence:** `build_stock_library.py:1594` hardcodes `rank_by="bottoming-alignment"` vs `:1519` `rank_by="alpha"` for `setups.json`. `mtf_alignment` (`cycles.py:1857-1905`) builds its score from hand-set MACD-phase constants with **no forward-return term**. `setups.py:224-228` docstring: "the cycle-timing/reversal blend … does NOT improve forward-return ranking — it slightly DILUTES alpha." Live: `corr(board_position, alpha) = +0.266`; 15/34 buys have negative alpha (min PRGO -1.88).
- **Mechanism:** The one leg with positive PIT IC is demoted to a tiebreaker; the board is ordered by a pattern-recognition score its own Phase-0 shows is neutral-to-negative for forward returns. Rank position is uncorrelated (or slightly anti-correlated) with which names actually work.
- **Avg-user harm:** A novice reads top-to-bottom trusting rank = quality. Slot #1 (ETN) has alpha -0.12, `composite_z -0.047`, verdict "Neutral — no clear edge." The ordering they trust is anti-correlated with the only edge in the system.
- **Solution directions:**
  - *Rank the wide board by alpha (or the regime·PEAD composite), demote alignment to an eligibility filter + entry badge.* Effort **S**. Risk: alpha's IC (~+0.02) itself fails FDR — this is "least-bad," not "good"; the board will look thinner. Validate: rebuild, confirm `corr(position, alpha)` flips strongly negative and top-5 precision rises on the accruing call log.
  - *See the critic's contrarian caveat (§6) — this "obvious" fix may trade a validated drawdown benefit for an unproven return benefit. Do not ship it without measuring MAE.*
- **OPEN QUESTIONS FOR FABLE:**
  - If the shipped rank key (`bottoming-alignment`) was **never fed to the validation harness at all** — the harness only tested 7 composites, none of which is the live key — is the honest first step simply to *grade the actual live key* before proposing any replacement?
  - Given alpha's IC also fails FDR, is ranking by it genuinely better for an average user, or does it just replace a negative-IC order with a near-zero one while making the board less legible?

**A2. `entry_open_first` hands slot #1 to the weakest name — and it is stale.**
- **Evidence:** `setups.py:149-153` sorts `(status=='buy_now')` first. Only 1/34 is `buy_now` (ETN). ETN: alpha -0.12, verdict "no clear edge," and `signal.last = {type:buy, quality:block, reason:'veto: bearish divergence'}`. REZI (slot #2) has score 95, alpha 0.34. The docstring (`setups.py:145-147`) claims "the board order always matches the visible entry badge and score" — but slot #1 (score 47) sits above slot #2 (score 95), so the claim is false. **Compounding staleness:** the board is one build stale (`as_of 2026-06-30` vs site 2026-07-01); the single field that picks slot #1 is computed on T-1 closes.
- **Mechanism:** With only one `buy_now` name, `entry_open_first` is not "settling ties" (as its docstring claims) — it is unilaterally selecting the single most-prominent slot, by a sparse binary flag that is both stale and edge-blind.
- **Avg-user harm:** The one card a novice acts on (top, green, "buy now") is systematically the least-edged, and its entry window may have already closed a day before they see it.
- **Solution directions:** *Drop `entry_open_first` as terminal sort; make it a within-tier tiebreak among names already above an edge floor.* Effort **S**. Risk: removes the "freshly bounced" feel users may have anchored on. Validate: confirm no negative-alpha name occupies slot #1 post-change.
- **OPEN QUESTIONS FOR FABLE:** Should the "#1 slot" concept exist at all when the edge cannot rank-order 34 names — i.e. is a single hero pick inherently dishonest here?

---

### Cluster B — The displayed score inverts against edge

**B1. `potential_score` overwrites the honest edge-percentile; the big green number is negatively correlated with alpha.**
- **Evidence:** `build_stock_library.py:1457-1459` discards the monotone edge-percentile into `rank_pctile` and displays `potential_score`. Live correlations (re-verified): `corr(score, composite_z) = 0.185`; **`corr(score, alpha) = -0.31`**. The inversion, verified live:

  | Ticker | Board | Displayed score | Band | Alpha | Sector rank | Verdict |
  |---|---|---|---|---|---|---|
  | **WAB** | buy | **26** | neutral | **+1.73** | **11/252** | High-confluence leader (context) |
  | **LKQ** | buy | **75** | high | **-1.08** | **175/195** | Lagging — relative weakness |
  | PRGO | buy | 69 | constructive | -1.88 | 161/168 | Lagging — relative weakness |
  | ETN (#1) | buy | 47 | constructive | -0.12 | 141/252 | Neutral — no clear edge |
  | WING | laggard | 77 | high | -1.13 | 178/195 | Lagging — relative weakness |

- **Mechanism:** `name_score.py:225` `raw = trig·(0.4+0.6·fuel)·…·edge_mult` with `edge_mult` clipped to `[0.70,1.35]` and a `0.4` fuel-floor. "fuel" is drawdown depth, so a washed-out laggard scores HIGH precisely because it fell hard, while a leader scores low. Edge can shave at most 30% — it can never veto.
- **Bimodal thesis inversion (verified):** the deep-washout cohort scores systematically *higher* than the near-high cohort. Deep (`off_high < -20%`): REZI 95, FCN 77, LKQ 75, PRGO 69. Near-high (`off_high > -3%`): ETN 47, XEL 28, BKH 20. The board fuses two *opposite* trades — mean-reversion vs momentum-continuation — under one label and one score that ranks them backwards.
- **Avg-user harm:** The number the eye anchors on rewards falling knives and buries leaders. A novice buys LKQ (75) over WAB (26).
- **Solution directions:**
  - *Stop overwriting `score` (delete L1457-1459); display `rank_pctile` as the headline and `potential` as a separate, explicitly-labeled "timing/readiness" meter.* Effort **M**. Risk: honest edge-percentile is near-flat across a weak field; board reads as "nothing to buy." Validate: top-N by displayed number must have higher forward IC than today.
  - *Recolor the score by the ABSOLUTE verdict band (never green on a "Lagging" name); add a build-time invariant that fails when `band∈{high,constructive}` coexists with `verdict∈{no clear edge, Lagging}`.* Effort **S**. ~23/34 rows currently violate this.
- **OPEN QUESTIONS FOR FABLE:**
  - Is the fused single "conviction" integer salvageable, or must edge and timing be physically separate glyphs? A power user genuinely wants "edged AND entry-timed" — is a 2D quadrant (edge grade × entry state) legible to a novice who reads exactly one glyph?
  - Should deep-washout and near-high names ever share a board and a scoring formula, given they encode opposite theses?

**B2. The 0-100 is uncalibrated ordinal, not P(win) or EV.**
- **Evidence:** `stock_score.py:229` `_logistic_0_100(z, k=0.62)` docstring: "Monotone DISPLAY skin only … Never fed to calibration." `k=0.62` is arbitrary. All 34 rows `uncalibrated=True`, `neutral_ic`. No `hit_rate`/`track_record`/`fwd_ret` token anywhere in the shipped JSON.
- **Mechanism:** A 75 and a 47 have no established difference in realized outcome; multiplicative nuisance multipliers (tailwind 0.85–1.15, confidence 0.9–1.1) mean two names 20 points apart can differ only by regime noise.
- **Avg-user harm:** Users anchor position size on a number carrying no calibrated meaning.
- **Solution directions:** *Close the loop: snapshot daily, grade 21/63d vs SPY, isotonic-map score→empirical P(positive excess return), show per-band hit-rate + Wilson CI.* Effort **M** (plumbing exists) but **months** to mature. Risk: on a ~0-edge universe the calibrated curve may be nearly flat (every band ≈ base rate) — honest but unflattering. Validate: reliability diagram; does any band separate forward returns?
- **OPEN QUESTIONS FOR FABLE:** If honest calibration collapses every band to ~50%, does surfacing the true near-random hit-rate simply tell the user not to use the board — and is that the correct outcome to ship?

---

### Cluster C — The headline is decoupled from all evidence

**C1. BUY is a static cycle-dict lookup no confirmer/verdict/gate can lower.**
- **Evidence:** `cycles.py:429-435` — `"FRESH BUY": {"label":"BUY ZONE","action":"BUY","dir":"up"}`, keyed on cycle state alone. The confluence gate is wired only into `entry_signal.status` (`entry_signal.py:167`), not into `row.state`/`label`/`urgency` (`setups.py:100-106`). Live: 4/34 rows show `urgency="now"` while `entry_signal.status="await_confluence"`; 18/34 are `hold`; 14/34 have `signal.last.quality=="block"`; 15/34 last-printed a sell/cut.
- **Mechanism:** A TIMING/HWM path and an EDGE/VALIDATION path run in parallel and never reconcile. The loud fields (state/label/urgency) say GO; the quiet fields (verdict/validation_status/trust_tier) say STOP. No component arbitrates.
- **Avg-user harm:** Salience wins — the novice acts on "FRESH BUY / act now" and never parses "neutral_ic." The card that is internally a coin-flip reads as a conviction buy.
- **Solution directions:** *Make the headline a FUNCTION of the fused verdict.* Gate BUY/FRESH/urgency wording on `composite_z>0 AND verdict∉{no-edge, Lagging} AND confluence not blocked`; feed the same buyable result into `row.state/label/urgency`. Effort **M**. Risk: strict gating may collapse the board to a handful of names most days. Validate: build-time invariant on fraction of BUY rows with `last.quality=="block"`; A/B whether users pick higher-edge names.
- **OPEN QUESTIONS FOR FABLE:** Is a mostly-empty honest board acceptable product, or does the average user need *some* actionable list even when the engine has no validated edge — and if so, how do you present "least-bad timing plays" without re-manufacturing false confidence?

**C2. Confirmer soup manufactures false confidence; two of three options confirmers are gated to zero weight.**
- **Evidence:** `data/gex/gate.json` and `data/options_ivspread/validation_gate.json` both ship `scored:false, weight:0.0`. `stock_score.py:788` applies the GEX tilt only `if _gex_gate_scored()` → GEX contributes 0 on live data while its "caution" chip still renders. The one live confirmer (vol_squeeze) enters as `-0.15` (`:731`) clipped into a ±0.5 nudge inside the 0.15-weight entry axis → ~-0.04 on composite. `smart_money` and `catalyst_stock` are absent from the US board entirely. **Citation correction:** `vol_squeeze` and `gex_confirm` live under `conviction.*`, not at row top-level; live `conviction.vol_squeeze.state` = EXPANSION on 10/34.
- **Mechanism:** Confirmers are additive, independently-mapped tilts with no cross-confirmer logic; the doctrine "confirmers can only lower, never create a buy" is stated in every caveat and enforced nowhere, because the thing that says BUY is not a function of them.
- **Avg-user harm:** Five chips imply corroboration when the machinery treats them as decoration. On ETN every confirmer is red yet nothing degrades.
- **Solution directions:**
  - *Route a fused conflict-tally into the headline as a downgrade-only gate* (count of `{gex=caution, vol=EXPANSION, iv=bearish, composite_z<0, alpha<0}`; force a rung down above threshold). Effort **M**. Downgrade-only needs no forward-IC proof to be honest.
  - *Escalate vol_squeeze EXPANSION to a hard FRESH-label veto* — "FRESH" (cycle-cross) and "EXPANSION/hv_pctile 100" (vol already high) are logically contradictory. Effort **S**. Risk: real breakouts also show expanding vol — needs a volume-confirmed carve-out.
  - *Hide gated (`scored:false`) confirmer chips, or restrict them to caution-only.* Effort **S**.
- **OPEN QUESTIONS FOR FABLE:**
  - If almost every confirmer is gated-off or absent, is there anything to *fuse* — or is the honest move to delete the soup and show one edge number plus a single "unvalidated regime" stamp?
  - The conflict-tally assumes disagreement predicts worse outcomes. What if EXPANSION-FRESH names actually *outperform* (momentum ignition) on large-caps? Then downgrading on it would hurt. How should the design hedge against confirmers whose sign is untested?

---

### Cluster D — The board is one correlated bet, and regime-blind

**D1. 56% of buys are Utilities + Industrials — effective N ≈ 2–3.**
- **Evidence:** Live sector distribution of the 34 buys: Industrials 10, Utilities 9, Financials 4, then singles/pairs. The `PER_SECTOR=5` cap + dual-class dedup exist only in `action_board.notable` (`build_site.py:1252`), NOT on the wide board (`build_stock_library.py:1595`).
- **Mechanism:** `bottoming-alignment` selects whatever sector is simultaneously washed-out across all timeframes, so the board collapses onto 1–2 co-moving sectors. On a day the Utilities-bottoming bet works, ~9 "work"; when it fails, ~9 fail together. Per-name "edge" is largely sector beta.
- **Avg-user harm:** The user believes they hold 34 independent ideas; they hold one rate/defensive-cyclical trade. Diversification is illusory. **This is a large part of "10 shown, 2 work": the board is not 10 shots, it is ~2 bets duplicated.**
- **Solution directions:** *Apply a soft per-sector cap + dual-class dedup to the wide board.* Effort **S**. Risk: may starve the board in a genuinely one-sector regime. Validate: measure realized cross-name correlation of the capped vs uncapped board.
- **OPEN QUESTIONS FOR FABLE:** Is sector concentration a bug to cap, or an honest signal to *surface* ("today's board = one Utilities-bottoming bet; size accordingly")? Which serves the average user better?

**D2. The dispersion regime knows selection isn't paying, but only trims per-name size — and that trim is currently an identity no-op.**
- **Evidence:** `dispersion.py:21` `_GROSS={lean_in:1.20, neutral:1.0, lean_out:0.75}` — the only lever is a gross multiplier consumed solely at `build_stock_library.py:1339` (`risk_sizing.assess`). Live `dispersion_regime.state="neutral"`, `gross_mult=1.0` (identity), `avg_corr=0.17`. The banner tooltip (`dashboard.html.j2:2384-2389`) promises "de-gross to cash" in macro tapes — no code path does this. The lean_in/lean_out payoff prior is imported from external literature (`dispersion.py:4-8`) with **no internal backtest** conditioning this system's own selection-leg IC on the dispersion state.
- **Mechanism:** The regime is architected as a per-name SIZE multiplier, not a board-level COUNT/ABSTENTION/FRAMING gate. It answers "how much to bet on each name," not "how many should I trust and is this even a stock-picker's week."
- **Avg-user harm:** On a week the engine's own meta-signal says is bad for selection, the user still gets 34 equally-loud BUY cards.
- **Solution directions:** *Wire the regime into pick count and label loudness* (e.g. cap 5 in lean_out, ~20 in lean_in); add an abstention banner when `lean_out AND gate_go==False`. Effort **S–M**. Risk: terciles flip on noise (pctile 0.63 vs 0.66 threshold) — needs hysteresis; the prior is unvalidated for this universe. Validate: condition residual-alpha/insider rank-IC on the three dispersion buckets over the deep panel FIRST.
- **OPEN QUESTIONS FOR FABLE:**
  - `avg_corr` (0.17, low → selection *should* pay) and `dispersion_pctile` (0.63 → "neutral") disagree on the same board. Is a single-scalar dispersion state even the right abstraction, or does the board need a 2D read (correlation level × dispersion trend)?
  - If the dispersion→selection-IC relationship is real in the literature but our legs are too weak to have measurable IC in *any* regime, does regime-gating the count still help purely as overtrading/variance reduction — or is that dressing up a null with false structure?

---

### Cluster E — Nothing earns trust; the validation layer is inert

**E1. The `gate_go` gate is mathematically unreachable; `validation_status` discriminates nothing.**
- **Evidence:** `stock_score.py:1307` — `validation_status = "positive_ic" if gate_go else "neutral_ic"`, a boolean pass-through. `stock_conviction_phase0.py:384-385` requires DSR≥0.90. `reports/stock-conviction-phase0.md`: the FULL deep+PIT run fails DSR on every signal at every horizon; best 63d L/S Sharpe +0.07, selection baseline NEGATIVE -0.16. `data/regime/stock_conviction_gate.json`: US=NEUTRAL, `winner:null`, `powered:true`. Live: 34/34 rows `neutral_ic`. No `conviction_phase0` step in `.github/workflows/daily.yml` — the gate JSON is a manually-refreshed artifact.
- **Mechanism:** Trust is bound to a single binary absolute-significance gate the ~0-edge data can never satisfy. The badge is identical on 100% of cards, forever — users learn to ignore it. It is NEUTRAL not because data is thin but because the true edge is ~0 and DSR≥0.90 is unattainable.
- **Avg-user harm:** The one field meant to say "trust / don't trust" reads the same value on every card, forever. It cannot separate the 2 that work from the 8 that don't.
- **Solution directions:**
  - *Replace the binary gate with a reachable 3-rung ladder* (context / beats-baseline+same-sign-IC+DSR≥0.5 / validated). Effort **M**. Risk: the middle rung could over-promote on relative-to-a-negative-baseline noise. Validate: does the middle rung separate forward returns out-of-sample?
  - *Compute `validation_status` LIVE* from trailing realized rank-IC of the shipped key against the accruing call log, with a CI. Effort **L**; inert for weeks until the log matures.
- **OPEN QUESTIONS FOR FABLE:** If the gate correctly refuses to bless noise (DSR≥0.90 *should* be unreachable on survivor-biased large-cap L/S), is the bug not the gate but that a product still ships 34 BUYs downstream of a gate that correctly said NEUTRAL?

**E2. No live forward track record — accountability is aspirational.**
- **Evidence:** `data/signal_archive/track_record.parquet` is absent; `data/stock_desk/track_record.json` `scored_total=0`; `name_score_grader` logs 4,990 US calls but `n_graded=0` (3-day log, 2026-06-29..07-01, no fwd-return column). No hit-rate anywhere in `us_standouts.json`.
- **Mechanism:** The system logs calls but has never let a horizon mature, and the loggers key off chart markers/AI leans, not the standout buy rows. 34 daily "buy now" claims with zero realized feedback.
- **Avg-user harm:** No "past BUY-ZONE picks: X% hit rate, median +Y%, median MDD -Z%" — the one number that would separate the winners. Users must filter by hand *because* the system withholds its own scorecard.
- **Solution directions:** *Wire a board-level forward ledger now* (snapshot infra exists), grade by verdict/band/urgency at 21/63d vs SPY, surface on the header. Effort **M**; **highest-leverage single fix** for the complaint, but months to mature. Risk: grading vs SPY conflates beta; survivorship inflates the base rate. Validate: confirm the loop keys off standout rows (not markers) and is leak-free.
- **OPEN QUESTIONS FOR FABLE:** A live ledger will likely report ~50% by verdict. Is publishing an honest coin-flip hit-rate net-positive (kills false confidence) or net-negative (destroys perceived value)? Is there a framing where an honest 50% is a feature?

---

### Cluster F — Missingness rendered as confidence; data holes

**F1. Absent inputs collapse to benign defaults, not reduced confidence.**
- **Evidence:** insider (the FDR survivor, weight 0.50) present on **2/34** rows — when absent, its weight silently renormalizes onto revision/mom (`stock_score.py:92-93`); 4/34 rows have `n_axes==3` (a whole axis missing) yet render identical BUY labels. `valuation_band==None` on **34/34**. `risk.total==0.0` with sub-taxes None on **31/34** (missing-input reads as "no risk"). SUE freshness is a synthetic `period_end+60d` proxy, not a real filing date (`build_stock_library.py:293`). Much of the timing/200-day context runs on a 323-row (~15-month) closes cache. The completeness metadata (`provenance.uncalibrated`, `n_axes`, `axes.selection.present`) EXISTS but the template references it essentially nowhere.
- **Mechanism:** Every hole collapses to a benign default (renormalized weight, 0.0 tax, None band). A pick built on a rebuilt-from-noise edge axis renders identically to a fully-supported one.
- **Avg-user harm:** Several of the 34 are not weak picks — they are *unmeasured* picks wearing a confident badge, and the user can't tell which.
- **Solution directions:** *Compute a per-pick data-completeness/freshness pip from existing metadata; below threshold, degrade the label to "THIN DATA — screen only."* Effort **M**. Risk: absent insider is *normal* (not thin) — must not double-penalize. *Treat renormalization as a confidence haircut, not a free re-weight.* Validate: do low-completeness rows underperform in the accruing log?
- **OPEN QUESTIONS FOR FABLE:** Should a missing high-weight leg SHRINK conviction toward a prior, or should the board ABSTAIN on those names? And: is the deeper failure *cultural* — honesty fields (`validation_status`, `gate_go`, `cand_depth_pct`) keep being computed and then born dead? What structural guard (a build-time invariant that fails when a rendered label contradicts its own provenance) would stop the next one?

**F2. Dead defensive code: `cand_depth_pct` never read.**
- **Evidence:** `cycles.py:242` computes `cand_depth_pct`, documented (`:233-237`) as the guard so "a stretched up-trend can't masquerade as a fresh buy (the TTWO/ECG case)." A full grep finds only the assignment and emission (`:220,242,304`) — **zero consumers**. The FRESH-BUY branches (`:791,845`) never reference depth. ETN (`off_high -2.2%`) is exactly this shape and prints FRESH BUY.
- **Mechanism:** The hard-coded band `DC_BAND=(36,42)` (`cycles.py:50`) with an "approaching_band = days 28-35" bucket (`:287`) unlocks the FRESH-BUY path 8 trading days early; the depth filter meant to require a real pullback was designed, documented, and never wired in.
- **Solution directions:** *Wire a min-depth condition into the FRESH-BUY branches.* Effort **S**, high precision gain. Validate: forward MAE of FRESH-BUY calls with depth<floor vs ≥floor.
- **OPEN QUESTIONS FOR FABLE:** For strong trend-continuation names, the best entries ARE shallow pullbacks. Does a min-depth gate correctly kill dead-cat bounces while wrongly killing the best trend entries — is depth even the right discriminator vs distance-from-200dma or a trend/mean-reversion regime split?

---

## 4. Signals-to-improve matrix

| Signal | Current state | Weakness | Improvement direction | Validated? |
|---|---|---|---|---|
| Residual alpha (selection edge) | PIT rank-IC +0.012(21d)/+0.023(63d); demoted to within-tier tiebreaker on wide board | Only positive-IC leg; ~4.5% of composite; buried under timing | Make it the primary rank (as `setups.json` already does); explicit rank column | Weak +IC, **fails FDR** |
| Insider (net-buying) | Weight 0.50, lone FDR survivor; present on **2/34** rows | Board de-facto ranks on decayed legs (SUE/rev/mom) when absent; renormalization hides it | First-class board filter/badge; separate "validated-edge" sub-board | **Borderline FDR pass** |
| SUE (earnings surprise) | Full-weight leg, tier "validated"; asof is synthetic period_end+60d | Edge "collapsed on deep history"; drags names hard (PRGO sue -3.0); real filing date not used | Demote to display confirmer; use real EDGAR filing dates | **Fails** (collapsed) |
| bottoming-alignment / timing | Board gate AND primary sort AND `entry_open_first` #1 selector | Timing-only forward IC negative; anecdote-tuned constants; no forward calibration | Within-tier tiebreak / risk-placement badge only; never sets #1 | **Negative IC** |
| `potential_score` (0-100) | Overwrites edge-percentile as headline (`corr(score,alpha)=-0.31`) | Rewards drawdown depth; non-monotone with edge; inverts leader vs laggard | Split "edge percentile" headline from "timing/readiness" meter; recolor by absolute verdict | No (`uncalibrated=True`) |
| `vol_squeeze` | Only live-weight confirmer; -0.15 diluted to ~-0.04; EXPANSION on 10/34 | Most-diluted signal is the one that most directly contradicts "FRESH" | Escalate EXPANSION to a FRESH-label veto | Partial (this leg scored) |
| GEX / iv_spread confirmers | `scored:false, weight:0.0`; chips still render | Trust-theater: visible, caveated, weightless | Hide while gated, or caution-only downgrade role | No (`building_history`) |
| spotlight (sector tailwind) | Self-declared non-alpha, but weight 0.10, directional-positive | Lifts weak-selection names in hot sectors (sector beta as conviction) | Clamp non-positive (removes caution, never creates conviction) or display-only | No (declared non-alpha) |
| `gate_go` / `validation_status` | Boolean pass-through; `neutral_ic` on 100% of cards | Zero discriminating power; unreachable DSR≥0.90 gate | Reachable trust ladder + live trailing-IC with CI | Gate correct, badge inert |
| dispersion regime | Wired only to per-name size; `gross_mult=1.0` no-op | Knows selection isn't paying; never gates count/label | Gate board width + label loudness; validate prior on OUR legs first | **No internal backtest** |

---

## 5. Models-to-improve matrix

| Model / engine | Role | Core weakness | Why it matters | Direction |
|---|---|---|---|---|
| `build_stock_library.py` wide-board pipeline (L1539-1622) | Assembles the board the user sees | Separate from validated `setups.json`; timing-gated + timing-sorted; overwrites score; no sector cap | This IS the shipped artifact; the docs describe a different board | Unify with `setups.json`; edge-gate inclusion; per-sector cap; stop score overwrite |
| `engine/cycles.py` (ladder/alignment) | Generates state/label/urgency + rank key | Hard-coded `(36,42)` band; anecdote-tuned constants; no forward-return term; `cand_depth_pct` dead | Emits the loud headline that no evidence can downgrade; fires FRESH 8 days early | Per-name adaptive bands; wire depth gate; demote to risk placement |
| `engine/name_score.py` (`potential_score`) | Displayed 0-100 | Multiplicative washout×timing; edge clipped to ±35%; 0.4 fuel-floor | The number the eye anchors on inverts against edge | Edge as a gate not a bounded multiplier; separate timing meter |
| `engine/stock_score.py` (conviction) | Composite + verdict + validation flag | Selection only 45% of rank; verdict from different scorer than band; validation inert | Two disjoint scorers on one card contradict on ~68% of rows | Single source of truth; band derived from verdict logic; live IC |
| `signal_gate` / `confluence_tiers` | Validated buy filter | Only gates `setups.json`; T2-T4 lack bearish-div/reclaim veto; launders blocked buys | 31/34 shown buys are not `is_buyable`; ETN is T2-eligible AND `quality=block` | Hard-gate the wide board; propagate master veto into lower tiers |
| `stock_conviction_phase0.py` + `validation.py` | Honesty/validation harness | Runs offline, not in `daily.yml`; never tests the live rank key; DSR≥0.90 unreachable | Sophisticated machinery touches zero live picks | Grade the actual shipped key; schedule daily; reachable ladder |
| `name_score_grader` / `track_record` / `stock_desk` | Forward accountability | All empty/accruing; key off markers not board rows | No realized hit-rate exists — the exact number the user needs | Wire board-level ledger; grade by verdict/band vs SPY |
| `engine/dispersion.py` | Regime meta-signal | Prior is external-literature; wired only to size; identity in modal state | Board is regime-blind on a bad stock-picking week | Validate on our legs; gate count/frame, not just size |

---

## 6. Contrarian / where the current design may be right

*So Fable does not "fix" non-problems:*

1. **The unanimous "rank_by=alpha" fix is probably unproven — possibly wrong.** Alpha's rank-IC (+0.012/+0.023) also FAILS FDR. The Phase-0 doc explicitly frames cycle timing as **RISK PLACEMENT (drawdown reduction)**, a benefit alpha-ranking discards. **Nobody measured MAE/drawdown of aligned vs alpha entries.** The "obvious" fix could hand average users *deeper-drawdown* entries for a rank-IC gain that isn't real. A defensible design may be: **gate on alpha>0 (floor), order/size by drawdown-minimizing timing.** This is the single biggest blind spot in the analysis.

2. **Several "critical" findings collapse to a 30-line CSS/Jinja fix.** The engine's honesty fields (`neutral_ic`, verdict, `validation_status`) are all PRESENT and CORRECT — the model is honest; the template renders the wrong field big. Recoloring the score by verdict band, demoting timing to a neutral color, and surfacing a `gate_go` banner is not a deep re-architecture. Don't over-scope the UI-hierarchy problem into a modeling rebuild.

3. **"Only 2 of 10 work" is currently UNMEASURABLE and may be wrong as stated.** All graders are empty. "2 of 10" is a gut impression that could reflect genuine ~0 edge, recency/salience bias, OR **correct base-rate behavior misread as failure** — a board with rank-IC ~0 *should* have a ~50% hit-rate, which feels like "half don't work" but is exactly what an honest no-edge screen looks like. **Priority #1 should be accruing the track record, THEN diagnosing — not re-plumbing ranking against a vibe.**

4. **The confirmer "trust-theater" verdict is too harsh on intent.** A confirmer that can only DEMOTE (never create a buy) and is gated-off pending history (n=10/30 buckets) is the *correct conservative posture* for an unvalidated signal. Turning them into hard vetoes now, before validation, would be less rigorous. The failure is that the caveat isn't rendered — not that the confirmer exists.

5. **`gate_go=False` being unreachable is arguably the system working AS DESIGNED.** On survivor-biased large-cap monthly L/S, DSR≥0.90 *should* be unreachable — that is the point of a deflated-Sharpe haircut. The harness is correctly refusing to bless noise. The bug is not the gate; it is that a product still ships 34 BUYs downstream of it.

**Caveat on evidence integrity:** some pooled findings cited `vol_squeeze` and `act_level` as row top-level fields; live inspection confirms they are nested (`conviction.vol_squeeze.state`, `entry_signal.act_level`). The mechanisms hold and the values re-verified (EXPANSION 10/34; act_level {3:1, 2:3, 1:30}), but re-pull from the nested paths before quoting.

---

## 7. Handoff to Fable — the hardest open questions worth novel solutions

1. **Is the honest steady state K≈0?** If the deep+PIT edge is ~0 and DSR is unreachable, the right product may be a variable-width board that shows 0–3 names most days. Is an empty "confident lane" a feature or a churn driver — and if churn, what is the honest alternative that isn't a lie?

2. **Return-IC vs drawdown: is timing a legitimate risk-placement / position-sizing layer** even though it must never SORT the board? How do you present a "when" signal that is honest about having no "what" edge without the user re-conflating them? (This requires measuring MAE of aligned vs alpha entries — which no one has done.)

3. **Is cross-sectional rank-IC even the right yardstick?** The product is a discrete BUY/WATCH classifier, not a dollar-neutral L/S book. A signal with rank-IC ~0 can still have elevated **precision@k in its top bucket** if the relationship is tail-concentrated (where insider/PEAD live). Nobody computed `P(fwd_ret>0 | top-5)` vs base rate. Should Fable measure precision@k before concluding "no edge"?

4. **Where is the true ceiling of free-data name selection?** Insider is the lone FDR survivor; regime·PEAD only nudges IC to +0.02. Is there ANY free/keyless combination (event stacking via OR/max instead of a weighted average that dilutes a mostly-absent insider leg; regime-conditioning; cross-sectional-in-events) that plausibly clears DSR — or should the product pivot to sector/regime/timing where the repo already has validated edges?

5. **Is the gate measuring the wrong universe?** The harness panel is survivor-biased current large-caps (delisted names invisible, `LIMITATIONS L168-174`). Survivorship inflates a momentum baseline; for reversal/insider legs the sign could flip once delisted names are included. Quantify the survivorship haircut before betting any redesign on a measured leg.

6. **One decision variable or a 2D representation?** Collapsing to one Own/Watch/Skip token is novice-safe but hides the continuous edge and centralizes the fusion rule where all the current inconsistency lives. A 2D (edge grade × entry state) quadrant is honest but demands the novice hold contradiction. Which does an average user parse better?

7. **Should missing high-weight legs SHRINK conviction toward a prior, or should the board ABSTAIN on those names?** Shrinkage keeps coverage but ships a hedged number read as a buy; abstention is honest but empties the strip on quiet days. Which failure mode is less punishing?

8. **What is the right calibration unit under near-zero edge** — P(positive excess return), E[excess return] with a band, or precision@k? A P near 0.5 looks useless; an E[return] band straddling zero looks useless; precision@k can be honestly empty. Which is least misleading to an average user when the edge is genuinely marginal?

9. **Should abstention be driven by measurable regime hostility (dispersion, breadth, risk-off) or by the model's own confidence (gate_go/live IC)?** These can disagree — a high-dispersion day where the model still has no validated edge. Is there a novel composite (dispersion-conditional confidence) that resolves the conflict rather than picking one?

10. **Is the deeper failure cultural?** Honesty fields keep being computed and born dead: `validation_status`, `gate_go`, `cand_depth_pct`, the `provenance` metadata, the dead template sort at `dashboard.html.j2:2397`. What single structural guard — a build-time invariant that FAILS the build when a rendered label contradicts its own provenance/verdict/freshness — would stop the next honesty field from being ignored?

---

**Key files for Fable:** `site/factordata/us_standouts.json` (live board); `scripts/build_stock_library.py:1457-1624` (wide-board pipeline, score overwrite, rank_by split, entry_open_first); `engine/stock_score.py` (composite/verdict/validation); `engine/name_score.py:78,225` (potential_score, edge_mult); `engine/cycles.py:50,242,287,429-435` (bands, dead cand_depth_pct, headline dict); `engine/setups.py:138-154` (entry_open_first); `engine/dispersion.py`; `templates/dashboard.html.j2:2355-2600` (card render, dead `_board` sort at 2397, contradictory tooltips 2362/2364); `reports/stock-conviction-phase0.md` + `data/regime/stock_conviction_gate.json` (unreachable gate); `research/US_STANDOUT_SETUP_SCORE.md`, `research/US_STOCKS_ENGINE_OVERHAUL.md`, `research/RESIDUAL_ALPHA_MOMENTUM.md` (edge ground truth).
