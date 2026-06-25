# Vector BTC Impulse-Warning Engine — Design & Research

**Status:** design doc + research findings. Display-only radar first, alerts/falsifier later. **REVISED post-critique** (2026-06-24): D1's headline edge has been re-derived under the exact standard leak-free label and **downgraded** — the prior 1.73-lift figure did not reproduce and is retracted (see §3, §7).
**Author:** lead engineer (Vector).  **Data as-of:** 2026-06-23 (signals.parquet n=4298 daily, 2014-09-17 → 2026-06-23; coinbase/btc_hourly n≈91,775 → 2026-06-23 05:00 UTC).
**Mandate (user):** Vector today only describes the long-term *status quo* ("bearish") — useless for calling tops/bottoms/flushes. It must instead **fire impulse warnings (up AND down)**, be **leading not coincident/lagging**, **escalate** (not be permanently-on), and be **falsifiable**.

This doc is built ON TOP OF the 4 prior suggestions already given to the user, which it folds into one coherent engine:
1. an **OI-crowding de-risk alert** that breaks the funding-AND-OI gate so crowded-but-not-euphoric OI can warn on its own;
2. make the **leverage-cascade chip a real colored warning** AND route elevated/high into the alert engine (today `btc_leverage_cascade.compute` is display-only and emits no alert);
3. a **"fuel gauge"** escalation when OI percentile + vol-of-vol both rise, surfaced at the hero not buried;
4. **fix staleness** (the intraday flash sentinel last ran 2026-06-13 while data ends 2026-06-23).

---

## 1. Executive answer: was June-24 detectable from pre-event (≤2026-06-23) data?

**Verdict: PARTIAL — yes, weakly, by ONE robust signal; no high-conviction call was available.**

The June-24 cascade was a **shallow (~-5 to -6%), intraday-resolution down-flush** from the 2026-06-23 close (~$64,054). On the strict daily close-to-close definition it is **borderline/MISSED** (the 1.5σ-scaled trigger on 6/23 was −5.74%, so a clean −5.5% daily close marginally does not cross the floor); it registers cleanly only on the **intraday hourly fwd-48h** label (≈5th–7th percentile) and on the relaxed daily abs=0.05 label. So this was *not* a major break — it sits among the **shallowest ~2%** of historical down-impulse onsets (historical median down-event reaches −10.8%, mean −11.9%, p25 −14.2%).

**What actually fired before the event, on a non-hindsight basis:**

| Signal (survivor) | Family | Fired pre-event? | Lead | Verdict |
|---|---|---|---|---|
| **Coinbase premium z `cbp_z90 < -1.0`** (2-of-3 confirm) | onchain_flow | **YES — fired** | nominal 2–4d, but ~coincident | Fired ahead of June-24, but full-sample lift **0.90** (anti-pred), 2024+ **1.12**, mean past-5d −3.1%, 35% of fires already down >3% → **largely coincident**, weak context flag not a clean lead |
| DVOL intraday-range jolt `dvol_range_z60 ≥ 2.0` | options_vol | **NO** | — | Validated precursor, but **silent** into June-24 (its documented "options-calm slow-flush" blind spot) |
| DXY thrust `roc5` z≥1.5 | crossasset_macro | YES (weak) | ~4 bd (6/18–6/19) | Real but **REFUTED as alpha** (overfit, weekend-leak, more coincident than leading) — do **not** ship as a primary trigger |

**The honest answer.** June-24 was detectable only as a **WEAK, largely-coincident de-risk context flag — not a leading call.** The cbp_z90 trigger did fire on **6/20, 6/21, 6/22** (reproduced in-repo below), so something *was* lit ahead of the flush. But under the exact standard leak-free label (forward-min over (t,t+3] ≤ −5%, z with `.shift(1)`/90d trailing) this trigger has **lift 0.90 over the full sample (anti-predictive) and only ~1.12 in the 2024+ holdout** — i.e. near base rate, not the 1.73 the first draft claimed (that number is retracted; see §3). Worse, it is **materially coincident, not leading:** mean BTC return in the 5 days *before* the trigger fires is **−3.1%** (vs +0.6% baseline), and **35% of fires occur with BTC already down >3% over the prior 3 days.** This is the *same coincidence defect* the doc correctly used to refuse DXY-thrust. So cbp_z90 is best read as *"US spot is already selling"* — a confirmation that a sell-off is underway, with at most a marginal 1–2 day forward tilt, not a clean pre-flush warning.

The two vol-surface tools that *should* anticipate a flush did **not** fire: `vov_pctile` rose monotonically 44→67 but **never crossed its validated 70 trigger** (peak 67.0 on 6/19, reproduced below), and the DVOL intraday-range jolt stayed silent (6/23 closed calm, z≈−0.79). June-24 was a **slow, options-calm flush** — exactly the regime where the vol-surface family is documented blind. The Deribit options structure (skew_25d 0.12→0.20, rr_25d −4.6→−7.7, gamma_regime "short", dist_to_flip<0) was *leaning the right way*, but with **only 11 rows of history (first non-null 2026-06-13)** it is **un-backtestable / INSUFFICIENT-HISTORY** and cannot be promoted to a trigger today — it is descriptive coincidence, not a tested edge.

**In-repo reproduction (this worktree, signals.parquet):**
```
cbp_z90 fires <-1.0: 06-11, 06-18, 06-20, 06-21, 06-22   (2-of-3 rule satisfied 6/20–6/22)
vov_pctile last 10:  61.2 63.1 65.0 66.1 67.0 67.2 66.6 65.8 65.3 63.4   (never ≥70)

# D1 under the EXACT standard leak-free label (this worktree, re-run 2026-06-24):
cbp_z90<-1.0 (2of3), label=fwd_min(t,t+3] <= -5%:
  full    base=0.094 cond=0.085 lift=0.90  n_fire=424  recall=0.13
  2024+   base=0.049 cond=0.054 lift=1.12  n_fire=184
  coincidence: mean past-5d ret at fire=-3.10% (base +0.64%); 35% of fires already down >3% over 3d
```

So: **partial, weak, largely-coincident single-signal detection.** The one thing that lit before June-24 (cbp_z90) is closer to a *confirmation that US spot was already selling* than a forward warning, and on a strict leak-free label it does not beat the base rate over the full history. Anyone claiming June-24 was a high-confidence pre-callable top is overfitting hindsight. **Honest bottom line: yes, the system seriously needs work — today it would have shown, at best, an "elevated / de-risk" context flag with no validated forward edge, not a leading trigger.**

---

## 2. Why today's engine is descriptive, not predictive

Grounded in the actual module lead/lag inventory:

- **The headline regime read is a standing-state classifier.** `engine/btc_regime.py` + `btc_signals.py` emit `risk_regime`, `structure_state`, `momentum_state`, `market_mode`, `bfi_zone` — these are **coincident/lagging** regime labels (trend efficiency, momentum oscillator ±0.5 bands, 25-threshold risk index). They tell you *what regime you are in now* ("bearish"), which by construction persists; they do not fire a *forward* warning on a threshold-cross-plus-change. The alert layer (`btc_alerts.daily_state_events`) only emits on **state transitions of these lagging labels** → you hear about the regime *after* it has already turned.

- **The leverage-cascade gate is display-only and AND-gated to near-silence.** `engine/btc_leverage_cascade.py` requires `funding_state=="high"` **AND** `oi_state=="stretched"` for `cascade_risk="high"`. It returns `{"display_only": True}` and **emits no alert** — it is consumed in `build_vector.py` only as a `context_legs["leverage"]` card. The AND gate means crowded-but-not-euphoric OI, or building OI under flat funding, **cannot warn on its own**. (This is prior-suggestion #1 and #2's target.)

- **The intraday sentinel is stale.** `scripts/vector_sentinel.py` runs the flash-crash state machine, but it **last ran 2026-06-13** while data ends 2026-06-23 — so the one component that *would* have resolved June-24 at intraday resolution was **not executing**. The headline is daily-only and lags. (Prior-suggestion #4.)

- **Nothing is forward-conditional or decaying.** There is no module that takes a *verified leading precursor*, fires on a **threshold-cross + still-rising** condition, scores it into a **0–100 forward-pressure gauge**, and **decays** it back to quiet. The closest thing (`risk_extreme_events`) is a contrarian-at-extremes capitulation watch — itself "suggestive, not proven." The result is an engine that is permanently "bearish/neutral" and never *escalates* into a loud, time-bounded warning.

**Conclusion:** the engine describes the regime; it does not *anticipate the impulse*. We need a new, separate, forward-conditional layer built only from adversarially-verified leading precursors.

---

## 3. Verified leading precursors (survived adversarial verify)

Only candidates with **`real_lead == true && survives == true`** are eligible for the engine. The full verdict ledger (incl. rejects) is preserved in §7. Triggers are **leak-free**: all z-scores use trailing `rolling(W).mean()/.std()` with `.shift(1)`; forward labels are strict `(t, t+H]`.

### DOWN-impulse precursors

**D1 — Coinbase premium z (US net selling).  [DOWNGRADED to CONTEXT-ONLY — does not survive the standard label; largely coincident]**
- **Field:** `signals.parquet['coinbase_premium']`.
- **Feature:** `cbp_z90 = (cbp - cbp.rolling(90).mean().shift(1)) / cbp.rolling(90).std().shift(1)`.
- **Trigger:** `cbp_z90 < -1.0`. **Confirmation:** ≥2 of the last 3 sessions `< -1.0`.
- **EXACT label (now stated, per critique):** the down event is
  ```python
  fwd_min = close.shift(-1).rolling(3).min()      # min of close[t+1..t+3]
  label   = (fwd_min / close - 1.0) <= -0.05      # forward-min over (t,t+3] <= -5%
  conf    = (cbp_z90 < -1.0).rolling(3).sum() >= 2
  valid   = cbp_z90.notna() & label.notna()
  ```
- **Edge (RE-DERIVED under that exact label — the prior numbers are RETRACTED):**
  - **Full sample:** base **0.094** / cond **0.085** / **lift 0.90** (i.e. *below* base rate — anti-predictive) / recall **0.13** / n_fire 424.
  - **2024+ holdout:** base 0.049 / cond 0.054 / **lift 1.12** / n_fire 184 — a marginal tilt, not an edge.
  - No standard −5%/3d (or −7%/−10%, h=3/5) variant reaches anything near the previously-claimed **1.73**; that figure and the **6.6% base / 27% recall** came from an undocumented narrower/look-ahead label and are **withdrawn.**
- **Coincidence split (applying the DXY standard to D1):** mean BTC return in the **5 days before** a fire = **−3.1%** (baseline +0.6%); in the **3 days before** = **−1.9%** (baseline +0.4%); **35% of fires occur with BTC already down >3% over the prior 3 days.** → **materially coincident, not cleanly leading.**
- **June-24:** trigger fired 6/20–6/22, but on the evidence above this is a *"US spot already selling"* confirmation with at most a 1–2 day forward tilt, **not** a validated lead.
- **Disposition:** ship D1 **descriptive/context-only** (it tells the user *US spot is selling now*), **not** as an act-tier point-bearing leg, unless/until it passes the §6 holdout-lift gate (it currently does not). Precision ~9–11% (~89–91% false alarms), fires ~16% of days.

**D2 — DVOL intraday-range jolt (vol-of-vol spike).  [PRIMARY act-tier — only leg clearing the holdout bar; high confidence, low overfit — but missed June]**
- **Field:** Deribit dvol (`dvol_high`, `dvol_low`, `dvol_close`).
- **Feature:** `dvol_range_z60 = causal_60d_z( (dvol_high - dvol_low) / dvol_close )`.
- **Trigger:** `dvol_range_z60 ≥ 2.0`; **confirm** with a 2nd consecutive close `≥ 1.5` to cut single-bar noise.
- **Edge (reproduced near-exactly):** base 0.0614 / cond 0.1538 / **lift 2.507**; **2024+ holdout STRENGTHENS** → cond 0.2245, lift 3.277, n_fire=49; block-bootstrap p=0.0015. Cross-threshold monotonicity argues against threshold-mining. Leak-free verified.
- **Lead:** modest, recall ~0.14.
- **June-24: MISSED** (no ≥2.0 or even ≥1.5 in the valid pre-window 6/19–6/23; the 6/08 fire is 16 calendar days early = not a valid lead; 6/23 closed calm at z≈−0.79). **Document this blind spot loudly:** it is silent on slow, options-calm flushes — exactly June-24's character.

**D3 — Aggregate SOPR profit-taking spike (on-chain top exhaustion).  [ACT-TIER — clears the holdout bar; genuinely LEADING / coincidence-clean — but missed June]**
- **Field:** `store.read('bgeo','sopr')['sopr']` (aggregate realized SOPR; **5470-row history, 2011-07..2026-06-22**, joins to 4207 close-overlap rows ~11.8yr).
- **Feature:** `sopr_z90 = (sopr - sopr.rolling(90).mean().shift(1)) / sopr.rolling(90).std().shift(1)`.
- **Trigger:** `sopr_z90 > 2.0`. **Confirmation:** require `sopr > 1.02` *absolute* on the fire bar (filters one-bar reversion blips like 06-21) **AND** BTC up over prior 5d (so it reads as profit-taking-into-strength, not a falling-knife). A looser `z > 1.5` variant (lift 1.87 full / 1.74 holdout) ships as a **context-tier** earlier-but-noisier warning.
- **Edge (reproduced exactly):** base **0.1072** / cond **0.2292** / **lift 2.138** / n_fire 192 / recall 0.098. **2024+ holdout HOLDS:** cond 0.087 / base 0.049 / **lift 1.787**, n_fire 46. Circular-shift p **0.0002**; survives Bonferroni (≈0.007) and maxT (≈0.0025). UP direction is **dead** (lift 1.00) — it is a one-sided DOWN signal.
- **Coincidence (CLEAN — genuinely leading):** mean BTC return in the 5 days *before* a fire = **+9.95%** (fires into strength); only **6.8%** of fires occur already down >3% over the prior 3 days. This is the coincidence-clean profile that D1/DXY-thrust lacked — it warns *before* the down-leg, leading by a modest window.
- **June-24: MISSED.** SOPR hovered ~0.97–1.02 (neutral) the entire 06-08..06-23 window — **zero profit-taking exhaustion.** `z>2.0` never fired (peak **1.831 on 06-21**, a one-bar blip reverting to z=0.32 the next day); the looser `z>1.5` grazed a single un-sustained fire on 06-21, but on a bar where price was *down* 3.6%/5d (the confirmation filter rejects it). The shallow options-calm flush left **no on-chain SOPR signature** — the same blind spot as D2.

### UP-impulse precursors

**None survived adversarial verify as a standalone leading trigger.** This is an honest gap. The taxonomy's UP base rate (0.089 daily / forward-max ≥ +thr) is real, but no candidate cleared `real_lead && survives` for the up direction. Candidates examined leaned on funding/OI crowding, which **failed**:
- `funding_z` as a long-squeeze fuel: standalone forward-3d −5% lift **0.55 all / 0.92 2024+** (crowded-long readings did **not** reliably precede drawdowns — contrarian-at-extremes); descriptive of risk-build, not a calibrated trigger.
- OI percentile/divergence: `oi_mcap_pctile>80` → lift **0.36 (anti-predictive)**; `oi_pctile>75 & building` → lift **0.61**.

**U1 — Aggregate SOPR capitulation bottom-caller (on-chain wash-out).  [ACT-TIER — first surviving UP trigger; bottom/bounce lead, NOT a pre-crash signal]**
- **Field:** `store.read('bgeo','sopr')['sopr']` (same aggregate SOPR as D3).
- **Feature:** `sopr_z90 = (sopr - sopr.rolling(90).mean().shift(1)) / sopr.rolling(90).std().shift(1)`.
- **Trigger:** `sopr_z90 < -1.5` (mass realized-loss / capitulation). A `< -2.0` variant is higher-precision/lower-recall (lift 3.51, n=97).
- **Edge (reproduced exactly):** base **0.1146** / cond **0.3498** / **lift 3.053** / n_fire 203 / recall **0.147**. **2024+ holdout STRENGTHENS:** cond 0.214 / base 0.056 / **lift 3.798**, n_fire 28. Circular-shift p **0.0004**; survives maxT (≈0.022) and Bonferroni — the **single strongest signal in the whole screen.**
- **Honest nature (coincident-with-the-drop, leads only the BOUNCE):** it fires AFTER a deep down-leg — mean BTC return in the 5 days *before* a fire = **−10.7%** (median −11.2%), and **70%** of fires occur already down >3% over the prior 3 days. So it is a reactive **"buy-the-capitulation"** caller that LEADS the *subsequent bounce* by ~2d; it is **NOT** a pre-crash warning and must be paired with a *"price already washed out >5% over prior 5d"* context tag so it never reads as a generic buy.
- **June-24: correctly silent for the DOWN event.** As an UP/bottom signal it cannot and did not flag the 06-24 down flush; it had reset to neutral by 06-22. (It *did* fire 06-09/06-10 on the earlier dip, before the rally to 66k — out of competence for the June flush.)

**Design consequence:** the **UP gauge now ships its FIRST act-tier trigger (U1)** — a capitulation/bottom-bounce caller, explicitly framed as *reactive-to-the-drop, leads the bounce ~2d*, never as a pre-rally precursor. It still surfaces the *fuel* (crowding, vov rising) descriptively. We do not fabricate a *pre-emptive* up-trigger to satisfy symmetry; U1 is honest about being a wash-out responder. (See §4.4 and §7.)

### Not-yet-screened families — **SCREEN NOW DONE (2026-06-24)**

The order-flow / SOPR / OI-structure families have been run through the full leak-free gate (results in **§3.7**). Outcome:
- **SOPR / profit-taking exhaustion:** TWO act-tier survivors found — **D3** (`sopr_z90 > 2.0`, DOWN top) and **U1** (`sopr_z90 < -1.5`, UP bottom). `sth_sopr` absolute bands, `sopr` rolling-over, and the spread/premium z's all **REJECT** (maxT fails, coincident, or lift < 1).
- **Order-flow / aggressor imbalance:** **NO act-tier survivor.** Every true aggressor-imbalance column (`taker_*`, `okx_*`, `ls_ratio`) derives from the shallow OKX-rubik feed (~168–189 rows from 2025-12-17) — **INSUFFICIENT-HISTORY, never gateable.** The only long column, `flow_pctile`, is a volume/liquidity proxy (not aggressor flow); `flow_pctile ≥ 0.90 → UP` is real and holdout-surviving but **fails the coincidence test** (median lead **0 days**, 48% already up >3%/3d) → **CONTEXT-only, never scored.** The real unlock is a **sub-daily intraday CVD collector** (daily aggregation destroys order-flow's edge) — flagged for P2, not shippable now.
- **OI/price structure:** `oi_price_divergence ≥ 0.20 → DOWN` REJECTS for act-tier (single cherry-picked tail bin, ~3–7 effective episodes, maxT brittle, June MISS). Ships **CONTEXT-only** as a descriptive trapped-long flag.

**Updated act-tier survivor count: THREE — D2 (DVOL, DOWN), D3 (SOPR-spike, DOWN), U1 (SOPR-capitulation, UP).** D1 stays context-only. The UP gauge now has its first act-tier trigger (U1). **None of the three would have led the 06-24 flush** (see §3.7 June column).

### 3.7 Order-flow / SOPR / OI-structure screen results (2026-06-24)

Locked label: down = `fwd_min(t,t+3] ≤ −5%` (base ~0.094–0.107 on each column's span); up = `fwd_max(t,t+3] ≥ +5%`. Causal z90, strict forward labels. All verdicts independently reproduced in-repo.

| Candidate | Dir | Span (non-null) | Lift full / holdout | Lead vs coincident | June | Tier |
|---|---|---|---|---|---|---|
| **`sopr_z90 < -1.5`** (capitulation) | UP | 2014-12..2026-06 (4207, ~11.8yr) | **3.05 / 3.80** | coincident-with-drop; **leads the bounce ~2d** | MISSED (out of competence for a DOWN event; silent, correct) | **ACT (U1)** |
| **`sopr_z90 > 2.0`** (profit-take spike) | DOWN | 2014-12..2026-06 (4207, ~11.8yr) | **2.14 / 1.79** | **LEADING** (fires +10%/5d up, 6.8% already down) | MISSED (SOPR neutral ~1.0; peak z=1.83 06-21, one-bar blip) | **ACT (D3)** |
| `sopr_z90 > 1.5` (looser profit-take) | DOWN | same | 1.87 / 1.74 | leading but noisier | grazed 1 un-sustained fire 06-21 (filtered out) | context |
| `flow_pctile ≥ 0.90` | UP | 2014-12..2026-06 (4202, ~11.5yr) | 2.75 / 2.59 | **COINCIDENT** (median lead **0d**, 48% already up>3%/3d) | MISSED | context (badge, never scored) |
| `sth_sopr < 0.97 / < 0.95` | UP | 2022-06..2026-06 (1471, ~4yr) | 6.09 / 6.75 (n=10–36) | coincident (fires −7.8%/−9.6% 5d) | MISSED (ranged 0.98–1.00) | **REJECT** (maxT p~0.12, thin) |
| `sth_sopr > 1.03 / > 1.05` | DOWN | same | 2.59 / 3.01 (n=25–80) | coincident blow-off tops only; recall 5–14% | MISSED | **REJECT** (maxT p~0.31, thin) |
| `oi_price_divergence ≥ 0.20` | DOWN | span ok, n_fire 17 (holdout 13) | 4.64 / 4.75 | more coincident than claimed; ~3 effective episodes | MISSED (feature NEGATIVE through the run-in) | context-only |
| `sopr` rolling-over from elevated | DOWN | 2011-07..2026-06 (5469) | **0.83 / 0.39** | anti-predictive (fires after rallies) | MISSED (june fire was FABRICATED in candidate) | **REJECT** |
| `taker_*` / `okx_*` / `ls_ratio` (aggressor) | both | ~168–189 rows from 2025-12 | n/a (1–2 holdout events) | n/a | wrong-footed long into the top | **INSUFFICIENT-HISTORY** |

### Watched-but-not-shipped (real lead, did NOT survive)

- **DXY thrust `roc5` z≥1.5 (crossasset_macro):** `real_lead=true, survives=false`. Genuine weak shallow-flush tell (leak-free weekday fires 6/18, 6/19 → 4 bd ahead of June-24) **but**: overfit-high (2024+ edge rests on ~8 episodes/16 winning days; lift climbs as n shrinks; Bonferroni p≈0.9), weekend-carry leak inflates fire counts, **62% of fires occur with BTC already down 5d (more coincident than leading)**, the "corr rising" amplifier leg was **FALSE in June** (corr_spx falling 0.408→0.380), 79% false-positive in 2024+. → **Hold as a context badge only, never an act-tier trigger.**

---

### 3.8 Intraday (hourly) flush-precursor screen (P2) — 2026-06-24

**Premise.** The daily legs (D2 DVOL, D3 SOPR-spike, U1 SOPR-cap) all went silent into the 06-24 slow, options-calm intraday flush (~−5/−6% over a day, no shock candle). This screen asks at **hourly** resolution whether an intraday order-flow / vol-compression precursor LEADS flushes — *especially the slow/grinding archetype.* The **only** deep intraday history is `store.read('coinbase','btc_hourly')` (OHLCV, 91,775 bars, 2016→2026-06-23 05:00). **There is no aggressor-side field — true taker CVD is unavailable.** Every flow feature below is a **candle proxy** (`signed_vol = volume·sign(close−open)`), not real order flow. Hourly data ends **before** 06-24, so June is judged on the slow-flush *archetype*, not directly.

**Event labels (locked).** DOWN flush at hour `t` = `fwd_min(t,t+24] ≤ −5%` (per-bar base rate **8.88%**). Onsets de-overlapped to **one per 24 quiet bars → 620 DOWN onsets** (split **321 slow / 299 sharp** by intra-window path shape). All stats are **event-level** (de-overlapped triggers AND events) to kill the per-bar pseudo-replication that inflated the headline lifts in the candidate write-ups; causal z `W=720h`, causal trailing percentile, strict forward labels. Reproduced in-repo (`/tmp/verify_final.py`, `verify_maxt.py`, `verify_holdout.py`, `verify_strict.py`, `verify_archetype.py`, `verify_recall_window.py`).

| Family / candidate | Dir | n_eff onsets | Event lift (full) | Holdout (≥2023 / ≥2024) | Lead vs coincident | maxT / perm | Slow-flush | Tier |
|---|---|---|---|---|---|---|---|---|
| **CVD/price divergence** (`price_z − slope_z`, top ~3%) | DOWN | 409 trig-onsets | **1.37** (1.15–1.42, parametrization-sensitive) | 1.67 / 1.58 (holds) | **LEADING** (trailing-24h **+2.17%**, 28% falling, 10h median lead) | block-perm **p≈0.001**; maxT fragile (0.00 my null / 0.11–0.18 prior) | **NOT real** (slow 21% ≈ sharp 20%; 48h: 30.5% ≈ 30.8%) | **DISPLAY / context** |
| `cvd_net24_z` / `cvd_tick_net24_z` rolling-over | DOWN | ~590 | 1.6–2.0 | holds | **COINCIDENT** (trailing-24h −5.1%, 97% already falling) | clears maxT | n/a (reactive) | **REJECT** (coincident) |
| `comp48_then_z3` (compress 48h → realized-vol z≥3) | DOWN | 26 | 1.61 | 2.48 (n=9, single OOS hit) | non-coincident | block-p 0.0195 (**fails Bonferroni** 0.0017) | **FAILS** (5% slow-recall; z-jolt needs a vol-expansion the grind never makes) | **REJECT / display sharp-shock only** |
| `vol_z168 ≥ 2` single-hour volume spike | both | ~620 | **1.06** de-overlapped (1.55 was per-bar) | never reaches 1.3 | **COINCIDENT** (deepens with z) | maxT-p 0.10–0.31 | **SHARP-biased** (slow 0.41 < sharp 0.70) | **REJECT** |
| Pure compression (low-rv / BB-squeeze / low-vol-pctile) | DOWN | — | 0.74–0.94 | — | quiet regime is mildly **protective** | — | — | **REJECT** |

**The one genuinely-leading candidate (CVD/price divergence) and why it still does not ship act-tier.** It is the only intraday form that fires *from plateaus/local highs* (price firm, signed-volume slope deeply negative = "hidden distribution"): trailing-24h **+2.17%**, only **28% already falling**, **10h median lead** to first −5% breach. At the **pre-registered q=0.97** threshold it holds across both time-splits (1.67 / 1.58) and clears two strict block-permutation nulls (circular-shifted label and count-matched random onsets, **p≈0.001–0.002**). That is the strongest intraday result in the whole screen. **But three things sink it for act-tier:**
1. **It does not solve the 06-24 miss.** The slow-flush advantage that the early candidate analysis claimed is **NOT real** once measured at the event level: slow-recall **21.2%** ≈ sharp **20.1%** (at 48h lookback, 30.5% ≈ 30.8%). And the trigger fired in the prior 24h before **none of the three canonical slow-flush exemplars** in the taxonomy (2023-11-15, 2024-06-10, 2022-11-13 — the 06-24-shaped events). It catches at best ~1 in 3 slow flushes and misses the named archetypes.
2. **Operating characteristics are poor.** ~39 trigger-onsets/yr with a **71% false-alarm rate** (≈2.4 dud fires per flush it precedes). A 29% precision vs 21% base is a real but thin edge — the wrong shape to hang an act-tier de-risk on.
3. **Magnitude is parametrization-fragile and it is a candle proxy.** Event-lift ranges 1.15→1.42 across reasonable constructions; maxT-p flips between ~0.00 and ~0.18 depending on the null. The lift rises monotonically with threshold (1.10 at q=0.90 → 1.42 at q=0.99) — the classic threshold-mining signature. With no taker side in the data, this is *candle-color × volume persistence*, not order flow.

**Net (§3.8).** **No intraday act-tier survivor.** Every flow form is either coincident (cvd net-volume rolling-over: −5.1% trailing, 97% falling), or vol-event proxies misfiled as compression (`comp48_then_z3`, `vol_z168` — both sharp-shock biased, both miss the slow grind), or — for the one genuinely-leading divergence form — **too weak, too parametrization-fragile, and crucially WITHOUT a real slow-flush advantage** to act on. The divergence form is worth keeping as a **DISPLAY-only "hidden distribution" context badge** (honest direction, 10h lead, leak-free, explicitly a candle proxy that does not survive multiple comparison and does not solve the slow-flush gap) — **never scored, never act-tier.**

---

## 4. The engine: `engine/btc_impulse_radar.py`

A **forward impulse-PRESSURE gauge**, separate **UP** and **DOWN**, each **0–100**, whose contributing legs **SUM to the headline** (house style of `vol_shock_scorecard` / `risk_radar`). **Display-only first.** It is **distinct from the standing regime read** (`btc_regime`): the regime says *where we are*; the radar says *forward pressure is building / cresting / firing now*.

### 4.1 Module contract

```python
# engine/btc_impulse_radar.py
def compute(sig_df: pd.DataFrame | None = None) -> dict:
    """Forward impulse-pressure gauge. Never raises. Returns:
    {
      "ok": True, "display_only": True, "asof": "2026-06-23",
      "down": { "score": 0-100, "ladder": "quiet|coiled|warning|trigger",
                "legs": [ {leg}... ], "fired_today": bool, "lead_window_days": [1,3] },
      "up":   { "score": 0-100, "ladder": ..., "legs": [...],
                "validated": True,   # U1 SOPR-capitulation cleared act-tier
                "note": "U1 = act-tier wash-out-bounce caller (leads the bounce "
                        "~2d, NOT a pre-rally lead); other up legs descriptive" },
      "fuel_gauge": { "oi_pctile": .., "vov_pctile": .., "lit": bool, "state": ... },
      "staleness": { "daily_asof": .., "intraday_asof": .., "stale": bool },
      "note": "Forward pressure, NOT the standing regime. Each leg = a verified "
              "leading precursor; legs sum to the headline; legs decay."
    }
    """
```
Mirrors `btc_leverage_cascade.compute(sig_df)`: reads `store.read("vector","signals")` when `sig_df is None`, NaN-safe `_f`/`_pctile_rank` helpers, config-gated under `btc_impulse_radar:` in config, returns `{"ok": False, "reason": ...}` on any failure. Wired into `build_vector.py` as a new `context_legs["impulse_radar"]` entry next to `leverage`.

### 4.2 DOWN gauge — legs (points sum to ≤100)

Each leg contributes points **only when its verified trigger condition is met AND still rising/sustained**, then **decays** geometrically. Points are sized by each leg's *validated lift and confidence*, not equal-weighted.

**Leg sizing rule (per critique): legs are sized by holdout lift × independence, NOT by June performance.** D2 (holdout lift ~3.3) carries the largest cap; **D3 (SOPR-spike, holdout lift 1.79, coincidence-CLEAN and independent of vol) is the second act-tier DOWN leg at 30** — sized below D2 on lift but a genuinely orthogonal on-chain source. D1 is demoted to a small context cap (does not clear the gate, largely coincident). The OI-divergence trapped-long leg is context-only (too thin to gate). Fuel/cascade stay small context amplifiers. Note: nominal caps sum to >100 (D2 40 + D3 30 + context legs), but the headline is **capped at 100 with per-leg decay**, and D2/D3 rarely co-fire (vol-jolt vs on-chain profit-taking are different onset signatures).

| Leg | Source | Fire condition | Max pts | Decay |
|---|---|---|---|---|
| **D2 dvol_range_z60** (PRIMARY act-tier) | Deribit dvol | `z60 ≥ 2.0`, 2nd close `≥1.5` confirms | **40** | ×0.5/day after the 2nd-confirm bar; **0 pts if dvol history < 60 valid rows** |
| **D3 sopr_z90 spike** (act-tier, on-chain top) | `bgeo` aggregate `sopr` | `sopr_z90 > 2.0` AND `sopr > 1.02` abs AND BTC up prior-5d | **30** | ×0.5/day once condition clears; **0 pts if sopr history < 90 valid rows**. A `z>1.5`-only print (no abs/price filter) adds **+8 context**, not act-tier. |
| **D1 cbp_z90** (CONTEXT-only, demoted) | `coinbase_premium` | `cbp_z90 < -1.0` AND ≥2-of-3 last sessions | **15** | ×0.6/day once condition clears. **Deepening bonus (+8) is BOUNDED:** applies only in the **first 2 bars of a fresh cross** AND only if trailing-3d return was **≥ −2%** at cross onset (i.e. the move had not yet happened); it is suppressed once BTC is already falling, so in a sustained selloff this leg cannot stay pinned. |
| **OI-divergence trapped-longs** (CONTEXT-only) | `oi_price_divergence` | `oi_price_divergence ≥ 0.18` sustained 2+ days | **10** | step to 0 when divergence drops below 0.18. **Display flag only — too thin (n≤22) and brittle to gate; silent in options-calm flushes.** |
| **Fuel: OI+vov coincidence** (suggestion #3) | `oi_mcap_pctile`, `vov_pctile` | `oi_mcap_pctile ≥ 0.70` **AND** `vov_pctile ≥ 60 & rising-5d` | **15** | linear −5/day; *coiled-spring* leg, NOT an act-trigger on its own. **Provenance caveat: see §4.5 — `vov_pctile`/`oi_mcap_pctile` are borrowed precomputed columns and must be confirmed causal before this leg ships.** |
| **Cascade context** (suggestion #1+#2) | `btc_leverage_cascade.compute()` | `cascade_risk ∈ {elevated, high}` **OR** new OI-only break (see §5) | **15** | step to 0 when `cascade_risk` returns to `low` |

- **Headline = sum of live leg points**, capped at 100. `ladder` is derived from the sum (§4.3).
- **Why these sizes (holdout-lift-driven, NOT June-driven):** D2 holds lift ≥1.5 in the 2024+ holdout with block-bootstrap p=0.0015 → it earns the act-tier cap even though it **missed June** (we explicitly do *not* penalize it for that, and do *not* reward D1 for catching June). D1 (full-sample lift 0.90 / 2024+ 1.12, coincident) gets a small context cap. Fuel + cascade are descriptive amplifiers with small caps so they cannot drive the headline alone.
- **Generalization fixture (per critique):** P0 tests include a **June-blind historical flush fixture** (a pre-2024 down-impulse onset) to prove the radar escalates on an event it was *not* built around — not only on June-24.

### 4.3 Escalation ladder (the anti-"permanently-on" mechanism)

```
quiet    : score   0–14   no live precursor; standing regime read governs
coiled   : score  15–34   fuel/context legs lit (OI+vov rising, cascade elevated) — spring loading, NOT firing
warning  : score  35–59   ≥1 PRIMARY/SECONDARY precursor crossed its verified threshold
trigger  : score  60–100  primary precursor crossed AND still deepening/confirmed (act-tier)
```

**The four mechanisms that prevent permanently-on (CRUCIAL):**

1. **Conditional on a forward-validated CROSS, not a standing level.** Every act-tier leg fires on a *threshold-cross* of a leak-free leading feature (`cbp_z90 < -1.0`, `dvol_range_z60 ≥ 2.0`), **never** on the standing "bearish/neutral" regime label. The regime read is explicitly *not* a leg.
2. **Cross + change, with a BOUNDED deepening bonus.** The biggest points require the feature to be **still moving** (dvol 2nd consecutive confirm bar). The cbp deepening bonus is the one place a "new-low" reward could pin the gauge in a sustained downtrend (it makes new lows every day while you are *already* falling). Per critique it is therefore **doubly bounded:** (a) it only applies in the **first 2 bars of a fresh cross**, and (b) it is **gated on a benign trailing return** (require trailing-3d ≥ −2% at cross onset). Once the move is underway the bonus is off, so the deepening leg cannot reintroduce the permanently-on failure.
3. **Decay.** Every leg decays (×0.5–0.6/day or linear) the moment its condition stops being met. Absent fresh crosses the gauge **bleeds back to quiet** within ~2–4 days. There is no permanent floor.
4. **Distinct from the standing regime.** The radar lives in its own card/field (`context_legs["impulse_radar"]`), labeled *"forward pressure"*; the headline regime stays where it is. They never sum together, so a chronically bearish regime cannot inflate the radar.

June-24 illustrates the decay mechanism but **not** a clean lead: the cbp leg lit 6/20–6/22 (a *context* nudge, since its deepening bonus would have been suppressed — BTC was already down >3% over those 3 days, so the benign-trailing gate fails), then z reset to +1.43 on 6/23 and the leg decayed. The radar's *correct* June behavior is therefore a low-level **coiled/de-risk context read that bleeds back to quiet**, not an act-tier trigger — honest, because the underlying signal was largely coincident.

### 4.4 UP gauge

The SOPR screen (§3.7) yielded the UP gauge's **first act-tier trigger, U1** — so it no longer ships fully context-only. U1 is honest about being a **wash-out responder**: it fires *after* the drop and leads the **bounce ~2d**, never a pre-rally precursor. Everything else on the UP side stays descriptive (funding crowding, OI percentile, vov rising) with `validated: true` for U1 only.

| Leg | Source | Fire condition | Max pts | Decay |
|---|---|---|---|---|
| **U1 sopr_z90 capitulation** (act-tier, on-chain bottom) | `bgeo` aggregate `sopr` | `sopr_z90 < -1.5` AND BTC already down ≥5% over prior-5d (so it reads as capitulation-bounce, not generic buy) | **30** | ×0.5/day once `z` recovers above −1.0; **0 pts if sopr history < 90 valid rows**. A `z < -2.0` print (higher precision, lift 3.5, n=97) raises the cap to the full 35. |
| **Fuel: funding/OI crowding** (context) | `funding_pctile`, `oi_mcap_pctile`, `vov_pctile` | crowding ≥ 0.70 & vov rising-5d | **12** | linear −4/day. Descriptive *fuel*, never an act-trigger. |
| **flow_pctile momentum badge** (context) | `flow_pctile` | `flow_pctile ≥ 0.90` | **0 (badge)** | display chip only — **COINCIDENT, median lead 0d**, never scored. |

- **`validated: true` for U1 only**; the up `note` becomes *"U1 SOPR-capitulation is an act-tier wash-out-bounce caller (leads the bounce ~2d, NOT a pre-rally lead); all other up legs descriptive."* U1's cap (30) is sized on its holdout lift (3.80) × on-chain independence, but is **explicitly not a pre-emptive top/bottom oracle** — it is reactive-to-the-drop by construction. No *pre-emptive* up-trigger exists; we do not fabricate one for symmetry. (See §3.7, §7.)

### 4.5 Provenance of borrowed precomputed columns (causal-leak audit — per critique)

The radar's *own* z-scores are freshly built leak-free (`.shift(1)` + trailing windows). But several legs **borrow precomputed `_pctile`/derived columns from the inventory**, and the radar inherits any leak baked into them. **Before any borrowed column ships in an act-tier or point-bearing role, P0 must assert its construction is causal** (trailing/expanding window with no centering and no full-sample fit):
- `vov_pctile` — confirm it is a trailing-window percentile, not full-sample/centered.
- `oi_mcap_pctile` — same.
- `coinbase_premium_pctile`, `reserve_risk_pctile`, `*_z` columns used only as cross-checks — same.

If a borrowed column cannot be shown causal, the radar **recomputes it locally** from the raw series with an explicit trailing window, rather than trusting the inventory value. This provenance assertion is added to the P0 test suite and to the CI gate (§6.2).

---

## 5. Alerts + UI wiring

### 5.1 New alert types in `engine/btc_alerts.py`

Add to the `CONVICTION`/`ANCHOR` maps and a new emitter `impulse_radar_events(sig, cfg)` (parallel to `risk_extreme_events`), each producing `_ev(...)` records consumed by `compute_all_events`:

- **`impulse_warn_down` (act-tier).** Fires on the DOWN ladder entering **warning** (the D2 dvol cross — the only act-tier leg). `tier="act"`, severity `high`. Headline: *"Down-impulse pressure rising — vol-of-vol jolt."* Edge string: cite D2 dvol_range_z60 lift **2.5 (3.28 in 2024+ holdout, p=0.0015)**, *"de-risk window, ~modest recall — D2 is silent on slow/options-calm flushes."* **Do NOT cite the retracted cbp 1.73/27% figures.** When the cbp context leg is also lit, append *"US spot selling underway (coincident confirmation, not a lead)."*
- **`impulse_trigger_down` (act-tier).** Fires on **trigger** (primary crossed AND deepening/confirmed). severity `high`. The loud one.
- **`leverage_cascade` (NEW — suggestion #2).** Route `btc_leverage_cascade.compute()` into the alert engine: emit on `cascade_risk` transition into `elevated` or `high`. Today this is display-only and silent — this makes the chip a **real colored warning** (amber=elevated, red=high) AND an alert.
- **`oi_crowding_derisk` (NEW — suggestion #1).** **Breaks the funding-AND-OI gate.** Add to `btc_leverage_cascade.py` a standalone OI path: when `oi_mcap_pctile ≥ 0.80` (or `≥0.70 & oi_change>0 & vov rising`) *regardless of funding*, return `oi_only_risk: "elevated"`. Emit a one-sided de-risk alert. **Honesty note baked into the edge string:** OI percentile is *anti-predictive standalone* (lift 0.36) — so this fires as a **soft de-risk nudge / "crowding building" context badge, NOT an act-tier crash call.** It exists because the user asked for crowded-but-not-euphoric OI to be able to warn; we ship it labeled as low-conviction context, never as a validated trigger.
- **`impulse_up_context` (info-tier, NOT act).** UP gauge context only; `tier="watch"`, severity `info`; explicitly *"no validated up-lead — descriptive."*

All inherit the existing i18n (`headline_zh`/`detail_zh`), `tier`/`edge`/`forward` conviction plumbing, and dedupe by `id`.

### 5.2 Hero escalation + fuel gauge (where it surfaces — NOT buried)

- **Hero band (top of Vector page).** When DOWN ladder ≥ **warning**, the hero shows a colored escalation strip (amber=warning, red=trigger) with the live score, the firing leg(s), and the lead window — *above* the standing regime read, not buried in a context card. Quiet/coiled states show a small neutral "impulse pressure: quiet" chip so the absence of a warning is also legible (falsifiable both ways).
- **Fuel gauge (suggestion #3).** A small 0–100 dual-arc (OI-pctile × vov-pctile) pinned at the hero, **lit** when both rise together (`oi_mcap_pctile ≥ 0.70 & vov_pctile ≥ 60 & rising`). This is the *coiled-spring* visual — it tells the user the spring is loading *before* any act-tier cross. In June it would have been lit (oi elevated, vov 44→67 rising) while the act-tier ladder stayed at warning — exactly the intended "early, not yet firing" read.
- **Leverage-cascade chip (suggestion #2).** Recolor the existing display-only chip: grey=low, amber=elevated, red=high, **and** make it a clickable anchor to the new alert. No longer silent.
- **Staleness banner (suggestion #4).** If `intraday_asof` lags `daily_asof` by > 1 day (the 6/13-vs-6/23 bug), show a "intraday sentinel stale — last ran {date}" banner so a stale flash sentinel can never silently hide an intraday flush again.

### 5.3 Template/build wiring

- `scripts/build_vector.py`: add `("btc_impulse_radar", "impulse_radar")` to the `context_legs` loop; pass `regime["context_legs"]["impulse_radar"]` to the Vector template; call `btc_alerts.impulse_radar_events(...)` inside `compute_all_events`.
- Vector Jinja template: hero escalation strip + fuel-gauge dual-arc + recolored cascade chip + staleness banner. (Template name resolved at implementation; the data contract above is the stable interface.)

---

## 6. Falsification: forward-outcome log + CI gate

Mirror `engine/btc_regime_ledger.py` (stamp/falsifier pattern, already in the build) and the `risk_radar_backtest.py` CI-gate concept.

### 6.1 Forward-outcome log

- **File:** `data/vector/impulse_ledger.jsonl` (append-only). New module `engine/btc_impulse_ledger.py` with `stamp(radar_dict)` called from `build_vector.py` right after the radar computes.
- **Each fire writes:** `{asof, direction, ladder, score, legs_fired, cbp_z90, dvol_range_z60, oi_pctile, vov_pctile, btc_close}`. No forward outcome yet — that is filled in on later runs.
- **Grading (forward, leak-free):** `H=3` daily (dual-threshold 0.05 / 1.5σ, the locked taxonomy) for daily fires; `H=48h` hourly for intraday. For each past fire, on the run ≥ H bars later, compute `fwd_min`/`fwd_max` and mark `hit / miss`, plus realized lead (bars from fire to extreme).

### 6.2 CI gate: `engine/btc_impulse_radar_backtest.py`

Run in CI (like `risk_radar_backtest`). **FAILS the build if a shipped leg stops leading.** Per leg, recompute on the full leak-free history + the **2024+ holdout**:

- **D2 dvol_range_z60 (only current act-tier leg):** assert holdout `lift ≥ 1.5` (today 3.28) **and** block-bootstrap `p ≤ 0.05` (today 0.0015).
- **D1 cbp_z90 (context-only):** graded and printed, but **NOT gated as an act-trigger** — under the standard label its full-sample lift is 0.90 / 2024+ 1.12, *below* the `lift ≥ 1.3` act-tier bar, so it ships context-only by construction. The gate will only **promote** D1 to act-tier if it ever clears `lift ≥ 1.3 & recall ≥ 0.15 & holdout-holds`; today it does not.
- **Order-flow / SOPR screen:** the gate runs the not-yet-screened families (`taker_*`, `oi_price_divergence`, `reserve_risk`, `sth_lth_sopr_spread`, `coinbase_premium_divergence`) through the same bar; none may be cited as a survivor until it passes.
- **Fuel / cascade / oi_only:** graded but **NOT gated as act-triggers** — they are context legs. The gate asserts only that they remain *non-negatively* associated (do not flip anti-predictive beyond noise), and it **prints** their lift so silent decay is visible.
- **UP gauge:** the gate scans up-candidates and **stays in context-only mode unless** an up-lead passes `lift ≥ 1.3 & p ≤ 0.05 & holdout-holds & survives multiple-comparison`. It can *promote* an up-trigger only by passing this bar.

**Multiple-comparison discipline (baked into the gate):** any *new* candidate leg must clear a Bonferroni/maxT-adjusted threshold over the variant-scan it came from (the explicit failure mode that sank DXY-thrust: Bonferroni p≈0.9). The gate refuses to promote threshold-mined single-sample illusions.

### 6.3 What "graded" means per leg

Each leg carries, in its radar output and ledger, its **live rolling hit-rate** vs base rate over the trailing fires. If a leg's trailing-50-fire hit-rate drops below its base rate for N consecutive evaluations, the gate **demotes** it (act → context) and opens a CI failure for review. This is how "stops leading" is detected automatically rather than by a human noticing.

---

## 7. Honest limits

- **Direction vs timing.** We can flag *pressure building in a direction* with a 1–4 day window; we **cannot** time the exact bar or guarantee magnitude. And a ~5–6% **intraday flush is an hourly event** — a daily 1–3d "de-risk window" is a genuinely different (lower-resolution) product than catching the flush itself. Treat the daily radar as *regime de-risk*, the hourly sentinel (P2) as the flush-catcher.
- **Base rates / false-alarms (corrected).** Under the exact standard leak-free −5%/3d label the daily DOWN base is **~0.094** (the prior **0.066** was an artifact of an undocumented narrower label and is **retracted**); UP base 0.089. D1's trigger fires ~16% of days at ~9–11% precision (~89–91% false alarms) **and does not beat base rate** full-sample (lift 0.90) — hence its demotion to context-only.
- **D1 is largely coincident, not leading.** 35% of D1 fires occur with BTC already down >3% over 3d; mean past-5d return at fire = −3.1%. It tells you US spot *is* selling, not that it *will*.
- **What is NOT predictable today:** *pre-emptive* UP-impulses (U1 is reactive — it leads the **bounce** after a wash-out, not a fresh rally from neutral), magnitude, and slow/options-calm flushes (D2's and D3's documented blind spot — and June-24 was exactly that). The Deribit options surface (skew/rr/gamma) is **INSUFFICIENT-HISTORY (n=11, since 2026-06-13)** — un-backtestable, ships descriptive-only, *no* lead verdict. The aggressor order-flow family (`taker_*`/`okx_*`/`ls_ratio`) is **INSUFFICIENT-HISTORY (~168–189 rows from 2025-12)** — never gateable; the real unlock is a sub-daily intraday CVD collector (P2), since daily aggregation destroys order-flow's edge.
- **Multiple-comparison discipline.** Most scanned candidates were noise. The order-flow/SOPR/OI-structure screen is now **DONE** (§3.7). After it, the honest act-tier survivor count is **THREE: D2 (DVOL, DOWN), D3 (SOPR-spike, DOWN), U1 (SOPR-capitulation, UP)** — every other candidate (`sth_sopr` bands, `sopr` rolling-over, `oi_price_divergence`, `flow_pctile`, all aggressor columns) **rejected or context-only.** D3 and U1 each survive maxT/Bonferroni on their threshold families (`z>2.0`/`z<-1.5`); D2's own act-tier is two coupled thresholds (`≥2.0` with 2nd-confirm `≥1.5`). DXY-thrust *looked* great in 2024+ but was an 8-episode small-sample illusion (Bonferroni p≈0.9) with a weekend-carry leak — **excluded from act-tier.**
- **ETF-era regime change.** Post-ETF (2024+) holdouts are where we validate, because the pre-ETF microstructure differs. D1 and D2 both *strengthen* post-ETF (good), but this means edges are estimated on a short modern window — the CI gate's holdout assertion is what keeps us honest as the regime drifts further.
- **June-24 specifically.** The only thing lit beforehand (cbp_z90) was **largely coincident** (BTC already falling), so the engine's correct, honest behavior on that event is a **low-level coiled/de-risk context read that decays** — not an act-tier trigger, and certainly not "flush imminent." Anyone who says June-24 was a clean pre-callable top is fitting hindsight.
- **Bluntly: the system still needs work.** The SOPR screen added breadth (D3 + the first UP act-tier leg U1) but **not coverage of the June-24 flush** — all three DOWN-relevant act-tier legs (D2 DVOL, D3 SOPR-spike) were silent into that shallow options-calm onset, and U1 is a reactive bottom-caller. So the validated forward edge for a *pre-flush* BTC down-warning still rests on signatures (vol-jolt, mass profit-taking) that this specific event did not produce. This doc's value is an honest map of what is and isn't predictable and a falsifier that prevents over-claiming — not a working pre-flush alarm for slow/calm flushes yet. The genuine next unlock is structural: a **sub-daily intraday CVD/aggressor + options-microstructure collector** (P2), because the daily on-chain/vol surface had no June signature at all.
- **Intraday (hourly) screen is now DONE (§3.8) and confirms the gap is structural, not a tuning miss.** Run on the deep hourly Coinbase OHLCV (the only sub-daily history, 2016→06-23), **no intraday act-tier survivor exists** either. The flow features are **candle proxies** (`signed_vol`) — there is **no aggressor side in the data**, so true taker CVD cannot be built. The CVD net-volume "rolling-over" forms (lift 1.6–2.0) are **coincident** (−5.1% trailing, 97% already falling). The vol-compression/volume-spike forms (`comp48_then_z3`, `vol_z168`) are **sharp-shock biased and structurally miss the slow grind** (5% / mixed slow-recall). The one **genuinely-leading** form — CVD/price **divergence** ("hidden distribution": price firm, signed-volume slope deeply negative; +2.17% trailing, 28% falling, **10h median lead**) — clears block-permutation (p≈0.001) at its pre-registered threshold and holds on both time-splits, **but its slow-flush advantage is NOT real** (slow recall 21% ≈ sharp 20%; 48h 30.5% ≈ 30.8%), it fired before **none** of the three canonical slow-flush exemplars, runs a **71% false-alarm rate**, and its lift (1.15–1.42) is parametrization-fragile and threshold-mined. → **DISPLAY-only "hidden distribution" context badge at most; never scored.** Bottom line: the candle proxy is **insufficient** to catch the slow/options-calm flush. Only a **true sub-daily aggressor-CVD + options-microstructure collector** would plausibly close the gap — the proxy confirms it cannot be done from OHLCV candles alone.

---

## 8. Phased roadmap

### P0 — Display-only forward radar — ✅ DONE (2026-06-24)
- **New:** `engine/btc_impulse_radar.py` — `compute(sig_df=None)` mirroring `btc_leverage_cascade`. DOWN legs D2(dvol,40,act)+D3(sopr-spike,30,act)+D1(cbp,15,ctx,bounded-deepening)+FUEL(OI×vov,15,ctx)+CASCADE(15,ctx incl. OI-only break); UP leg U1(sopr-capitulation,30,act). Builds its OWN causal z / trailing percentiles from raw series (provenance handled — `oi`/`vov` percentiles recomputed locally, not borrowed). Ladder `quiet/coiled/warning/trigger` is **act-gated**: context legs alone can stack past 35 pts but cap at `coiled` — only an act-tier cross reaches `warning`/`trigger`. Outputs `down`/`up` gauges, `fuel_gauge`, `cascade`, `staleness`.
- **Touch:** `scripts/build_vector.py` — added `("btc_impulse_radar","impulse_radar")` to the `context_legs` loop → persists into `regime_latest.json`. `config.yml` — added `btc_impulse_radar:` block.
- **Tests:** `tests/test_btc_impulse_radar.py` — **9 passing.** leg-sum-to-headline; the act-gating cap (context-only stays `coiled`); decay bleeds to quiet (anti-permanently-on); leak-free causal z (a future spike never changes a past z); cbp deepening **suppressed when already falling**; a **synthetic-flush fixture** proves the gauge ESCALATES to warning/trigger on an event it was not built around (generalises beyond June-24); the integration fixture asserts the honest **June-23 read = `coiled`, `act_live=False`** (no false act-tier warning); NaN-safe degrade. 24 existing BTC/vector engine tests still green.
- **Honest behavior on the live data:** DOWN **score 37 → `coiled`** (cbp context + OI-only cascade + decayed fuel), `act_live=False` — i.e. an elevated *de-risk context* that correctly does **not** masquerade as an acute impulse warning, exactly because no act leg led the options-calm flush. UP `quiet`.
- **Not yet surfaced:** the radar computes + persists but is not rendered on the page and emits no alert — that is P1 by design.

### P1 — Alerts + UI escalation (folds in suggestions #1, #2, #3) — ✅ DONE (2026-06-24)
- **Engine (suggestion #1):** `engine/btc_leverage_cascade.py` — added `oi_only_risk` to `compute()` (funding-INDEPENDENT OI-crowding flag that **breaks the funding-AND gate**) + vectorised `oi_state_series(df)` for historical transitions. Low-conviction by construction (OI standalone lift ~0.36).
- **Alerts:** `engine/btc_alerts.py` — new emitters `impulse_radar_events` (act-tier `impulse_warn_down` on a D2/D3 cross, `impulse_trigger_down` when D2+D3 co-fire, `impulse_warn_up` for the U1 wash-out bounce) + `leverage_derisk_events` (watch-tier `oi_crowding_derisk`). New CONVICTION tiers + ANCHOR (`#impulse`, `#leverage`) + bespoke honest edge strings (cite holdout lifts; flag D2's options-calm blind spot, U1's reactive nature, OI's low-conviction) + EN/zh. `engine/btc_impulse_radar.py` exposes `fire_series()` so the bells can't drift from the gauge. Wired into `compute_all_events`.
- **UI:** `templates/vector.html.j2` — a new **Impulse Radar card** above the Market-State hero: DOWN/UP gauges with a colour-coded ladder chip (quiet=grey, coiled=blue, warning=amber, trigger=red), a score bar, the lit legs (● act / ○ context with points + freshness), a **fuel gauge** (OI %ile × vov %ile), a **staleness banner** (red, when the intraday sentinel lags >1d), and an honesty caveat. The **leverage chip recoloured** (amber=elevated, red=high) and now surfaces `· OI elevated` when cascade is "low" but OI-only fired — the exact silent-in-June gap.
- **Tests:** `tests/test_btc_impulse_alerts.py` (4) — act warnings + co-fire trigger + up-bounce + id-dedup; OI-crowding fires **independent of funding** (no funding columns) at watch-tier; declining OI emits nothing. **291 BTC/vector/alert/leverage/PIT tests green** (incl. the point-in-time leak-free suite — the new causal features introduce no look-ahead).
- **Verified live (rendered page):** DOWN gauge = **coiled 37/100, "no act-tier cross"**; leverage chip shows **"low · OI elevated"** (amber); fuel gauge **OI 80%ile × vov 63%ile**. The honest June behaviour is now *visible*, not silent. *(The P1 staleness banner initially read "STALE last ran 06-13" — that was a FALSE ALARM, corrected in P2a; see below.)*

### P2 — Intraday sentinel + staleness fix (suggestion #4)
- **Intraday flush-precursor screen — ✅ DONE (2026-06-24, see §3.8). Outcome: NO intraday act-tier leg; the candle proxy is insufficient for the slow flush.** Screened the deep hourly Coinbase OHLCV (the only sub-daily history) for an order-flow / vol-compression precursor that LEADS flushes, under the same leak-free, event-level, multiple-comparison bar that killed the daily candidates. Result: coincident CVD-net forms, sharp-shock-biased vol/compression forms, and one genuinely-leading-but-too-weak **CVD/price divergence** form (DISPLAY-only) — **none solves the 06-24 slow-flush miss** (divergence slow-recall 21% ≈ sharp, fired before none of the three canonical slow exemplars, 71% false-alarm). Confirmed: there is **no aggressor side in OHLCV**, so this is a candle proxy, not real CVD — the gap is structural.
- **Decision taken:** (a) **No intraday act-tier leg wired** — nothing clears the gate. (b) The optional candle-proxy "hidden distribution" badge is **NOT shipped** — at 71% false-alarm with no slow-flush edge it would be UI noise. (c) **The real unlock — a true sub-daily aggressor-CVD collector — is now BUILT (P2.5, 2026-06-24).**

### P2.5 — Real intraday aggressor-CVD collector — ✅ BUILT (accruing)
The candle proxy failed because OHLCV has no aggressor side. **OKX's `rubik/stat/taker-volume` endpoint returns true taker buy-vs-sell volume and is US-accessible** (the existing okx collector already used it, but only at `period=1D`). `collectors/okx.py::_taker_volume_hourly` now pulls it at **`period=1H`** (a rolling ~720-hour / 30-day window, newest-first `[ts, sell, buy]`), keeping the **raw buy/sell volumes** (not just the ratio); `store.upsert(..., normalize_index=False)` **accumulates it forward** into `okx/taker_volume_hourly` so a deep hourly aggressor-flow history builds over time (each daily collect overlaps the prior 29 days → no gaps). `engine/btc_intraday_cvd.py` reads it and computes **CVD = Σ(buy−sell)**, 24h/72h net aggressor flow + a sign state, and (once ≥ ~2·720h have accrued) the **CVD/price "hidden distribution" divergence** — the one genuinely-leading *shape* the screen identified. Seeded with 30 days now (live read: `flow_state=distribution`, −281M/24h). **DISPLAY-ONLY / `accruing`** — explicitly not scored, never an act-tier leg, until it has the months of history to be re-derived under the §6 falsifier; *then* the divergence form is the candidate to validate and (if it passes the leak-free gate) promote via the auto-demote/auto-promote machinery. Surfaced as a context line on the radar card; collector runs in the existing daily `okx` adapter (no new cron). This is the honest closure of the slow-flush gap: we can't validate it yet (the data has to accrue), but the instrument now exists and is collecting.

**Operational hardening (post a 5-agent ops audit — "will it actually be ON in 6 months?").** The audit confirmed the pipeline will run/accrue/persist correctly (0 critical), but caught one bug + three monitoring gaps, all fixed:
- **CRITICAL (caught & fixed before it ran):** `run_adapter` calls `adapter.validate()` *before* `store.upsert`, and the base `Adapter.validate` `.normalize()`s every index to dates — it would have **silently collapsed the 720 hourly rows to ~31 daily** on every production run, killing the accrual. `OkxAdapter` now overrides `validate()` to exempt `taker_volume_hourly` (mirrors Coinbase's `btc_hourly`). The `normalize_index=False` upsert flag alone was **not** sufficient. Verified end-to-end via `run_adapter`.
- **HIGH (visibility):** a frozen hourly feed was invisible (okx reports `ok` off its daily series). The engine now flags `stale`/`hours_behind_ref` by comparing to the `coinbase/btc_hourly` live reference; `build_vector` emits a `::warning::` and the page shows a "⚠ FEED STALE" badge.
- **MEDIUM:** a >720h (unbackfillable) gap → cumsum restarts after it (`gap_detected`); one corrupt ledger `asof` no longer aborts all grading (per-row try/except); the hourly sub-fetch is guarded so a rubik outage can't trip the okx circuit breaker. Tests: `tests/test_btc_intraday_cvd.py` (8) + `tests/test_btc_impulse_falsifier.py` ledger-resilience.
- **Staleness fix — ✅ DONE (P2a, 2026-06-24).** *Root cause was NOT a dead cron.* `sentinel.yml` runs every 30 min and commits `flash_state.json` **only on a flash-state change** ("no heartbeat spam"), so its `last_eval` lags by design — the P1 banner that read "STALE last ran 06-13" was a **false alarm** off that unreliable heartbeat. Fix: `btc_impulse_radar.compute` now keys `stale` off the **freshness of the committed hourly data** (`coinbase/btc_hourly` last candle vs the daily close) — truthful and no-spam. On current data `stale=False` (hourly ends 06-23 05:00), banner correctly hidden; `last_flash_change` surfaced separately for transparency. Test: `test_staleness_tracks_intraday_data_not_sentinel_heartbeat` (fresh→not-stale, >1d-old→stale). No cron change needed (the cron is healthy); the optional belt-and-braces would be a committed heartbeat on the `live-data` branch, deferred as low value.
- **Tests:** `tests/test_vector_sentinel.py` (or extend) — stale state surfaces; banner field set; intraday flash state machine resolves the June-24 hourly fixture.

### P3 — Falsifier gate (suggestion: falsifiability mandate) — ✅ DONE (2026-06-24)
- **New `engine/btc_impulse_radar_backtest.py`** — `validate()` re-derives each act leg's leak-free edge (full + 2024+ holdout + a **circular-shift block-permutation** p, deterministic RNG) vs a PRE-REGISTERED floor (D2 ≥1.5, D3 ≥1.3, U1 ≥1.3) using `btc_impulse_radar`'s *shared* condition builders (gate can't drift from the live legs), and writes the verdict gate `data/vector/impulse_legs_gate.json`. `main()` exits non-zero on a failure (loud CI signal). **Live result: all_pass — d2 holdout-lift 4.49, d3 2.65, u1 6.34, all p≤0.002.**
- **Auto-demote (the live falsifier):** `btc_impulse_radar.compute` reads the gate and **zeroes the act-points of any leg marked `demoted`** + flags it (`demoted:true`, honesty note) — a leg that stops leading is removed *without a code change*, exactly the repo's `validate-leading-legs` pattern. The UI radar card shows a **🛡 Falsifier: N/3 act legs still leading** line.
- **New `engine/btc_impulse_ledger.py`** — `stamp(radar, sig)` appends the day's radar state + which act legs fired + BTC close to `data/vector/impulse_ledger.jsonl` (idempotent per asof); `grade(sig)` fills the forward outcome for matured rows (≥3d) and `render_summary()` reports the live forward hit-rate per direction (cold-start/thin by design, like `btc_regime_ledger` — it complements, not replaces, the historical backtest).
- **Wiring:** `build_vector.py` runs `validate()`+`write_gate()` BEFORE the radar leg (fresh verdict) and `stamp()`+`grade()` after; `.github/workflows/validate-leading-legs.yml` runs the falsifier monthly + commits the gate.
- **Tests:** `tests/test_btc_impulse_falsifier.py` (6) — validate PASSES when a synthetic leg leads, **FAILS (leg demoted, `all_pass=false`) when fires are random/non-leading**, `main()` returns 1 on a failing leg, the radar **auto-demotes** (zeroes points) on a demoted gate, ledger stamp is idempotent + grades a matured down-hit. **299 BTC/vector/alert/leverage/impulse/falsifier/PIT tests green.**
- **Design note:** the daily build uses GRACEFUL auto-demote (never crashes the build); the non-zero exit / CI warning is the loud human signal. Floor for U1 is 1.3 (not 1.5) — it is the reactive-bounce leg, sized on its strong holdout lift but explicitly not a pre-emptive oracle.
