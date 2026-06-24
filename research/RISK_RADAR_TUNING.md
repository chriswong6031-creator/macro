# Risk Radar v2 — Tuning Recommendation

**Author:** lead quant • **Date:** 2026-06-23 • **Worktree:** `/private/tmp/risk-tune` (frozen origin/main)
**Engine:** `engine/risk_radar.py` (decision layer only — scores untouched) • **Eval harness:** `/tmp/risktune/*.py`
**Bar (mandatory):** day-level forward outcomes (precision/recall/F1/lift), 2020+ OOS holdout, frequency-matched permutation null, explicit FP/precision tradeoff. Event = SPY ≥ X% max-drawdown onset within H business days; episodes collapsed at `min_gap=20bd`.

---

## 0. TL;DR

The current composite `alert` is **saturated, not selective**: it fires on **72.1% of all days** (full) and **81.5% of days** (2020+). Day-level lift collapses to **~1.0 at every horizon and dd-threshold**; the FP rate (~0.72 full / ~0.81 2020+) is essentially identical to the fire rate. High recall (0.68–0.91) is an artifact of always-firing, NOT detection skill. **The lever is the saturation, not flicker-suppression.**

Three factor-rule families were tested adversarially. **Two ADOPT, one MAYBE:**

1. **`regime_gating` (ADOPT, strongest)** — gate the elevated state on `SPY < 200dma AND breadth %>200dma in a low causal percentile (≤0.40)`. Precision **0.085 → 0.249** (2.9×) at H21, fire-rate **80% → 17%**, F1 **0.156 → 0.342** (2.2×), holds and is *slightly stronger* OOS (F1 0.180 → 0.353), permutation p=0.0 both eras.
2. **`conjunction_required` / armed+confirm (ADOPT)** — escalate only when a *validated leading leg* (`credit_oas_roc` at its strict thr) is armed inside a hot Tier-A scare AND a 2nd Tier-A scare confirms (≥ watch). H21 2020+: precision **0.127 → 0.188** (+48%), F1 **0.220 → 0.284** (+29%), fp_rate **0.812 → 0.351** (more than halved), permutation p=0.0. The baseline state-machine *fails* the 2020+ permutation null (p=0.168).
3. **`confirmation_persistence` (MAYBE — do not adopt as primary)** — `consec_N3` only nibbles a saturated signal; full-sample F1 is flat (−0.0004) and fails the full-sample delta-permutation; only the OOS delta is significant (p=0.026). Use as a non-gating confirmation *badge* at most.

---

## 1. ACCURACY ACROSS TIMEFRAMES (baseline = live `compute()` alert, `state ≥ elevated`)

Day-level metrics at dd_thr = 0.05. `lift = precision / base_rate`; `fp_rate = FP / non-positive days`; `fire_rate = alerts / all days`.

### Full history (n≈8,033 days; n_alert = 5,790; fire_rate 0.7205)

| Horizon | base_rate | precision | recall | F1 | **lift** | fp_rate |
|--------:|----------:|----------:|-------:|-----:|---------:|--------:|
| 5d  | 0.0285 | 0.0285 | 0.7205 | 0.0548 | **1.000** | 0.7205 |
| 10d | 0.0795 | 0.0826 | 0.7480 | 0.1487 | **1.038** | 0.7181 |
| 21d | 0.1890 | 0.1850 | 0.7051 | 0.2931 | **0.979** | 0.7241 |
| 42d | 0.3720 | 0.3656 | 0.7083 | 0.4823 | **0.983** | 0.7278 |
| 63d | 0.4006 | 0.3798 | 0.6831 | 0.4882 | **0.948** | 0.7455 |

### 2020+ holdout (n≈1,626; n_alert = 1,325; fire_rate 0.8149)

| Horizon | base_rate | precision | recall | F1 | **lift** | fp_rate |
|--------:|----------:|----------:|-------:|-----:|---------:|--------:|
| 5d  | 0.0264 | 0.0294 | 0.9070 | 0.0570 | **1.113** | 0.8124 |
| 10d | 0.0695 | 0.0732 | 0.8584 | 0.1349 | **1.053** | 0.8116 |
| 21d | 0.2005 | 0.2053 | 0.8344 | 0.3295 | **1.024** | 0.8100 |
| 42d | 0.3899 | 0.3947 | 0.8249 | 0.5339 | **1.012** | 0.8085 |
| 63d | 0.3512 | 0.3638 | 0.8441 | 0.5084 | **1.036** | 0.7991 |

### Where it is weakest

- **Lift ≈ 1.0 everywhere.** Precision tracks the base rate to within ±0.02 at every horizon → an alert carries **almost no information beyond the unconditional base rate**. This is the central failure.
- **Short horizons (H5–H10) pay the saturation tax hardest.** Recall looks best here (0.72–0.91) but precision/lift are worst — the high recall is "always on," not "early & right." Episode-level confirms: at dd=0.05/H5 full, **18 of 31 episodes are false**.
- **Long horizons (H42–H63) are a base-rate mirage.** Because the positive-window prevalence is ~0.37–0.40, an always-on rule *looks* "precise" (0.37–0.40) while adding nothing (lift 0.95–1.01). Any always-on rule clears this bar; it is not evidence of skill.
- **Post-2020 the saturation is worse** (fire-rate 0.81 vs 0.72), driven by sub-scores running hot — exactly the regime we care about most.
- **Leg edge is real but fragmented:** `credit_oas_roc` strong full (1.97 @H5) but **dead 2020+** (0.69–1.06); `bubble_ext` the opposite (0.53–0.97 full, **1.26–1.53 2020+** — the genuine modern precursor); `growth_cyc_def`/`rates_move` most era-robust (≥1.3 both slices, short H); `vol_term` spikes 2.3× @H5 2020+ but is pure noise (0.5–0.75) beyond 10d. **No single leg generalizes uniformly** — which is why the fix is gating/conjunction, not a new always-on band.

---

## 2. WHAT REDUCES FALSE POSITIVES WITHOUT LOSING SENSITIVITY

Ranked by **verified** precision–recall improvement (2020+ OOS, permutation-checked). The goal is FP reduction at *equal-or-better* recall, or a strongly favorable FP-removed/TP-lost trade that holds OOS — NOT trading recall for precision blindly.

### Rank 1 — `regime_gating` (ADOPT) — best F1, best precision, holds strongest OOS

**Config:** alert fires only when engine Tier-A `state ≥ elevated` **AND** `SPY close < 200d SMA` **AND** `breadth %>200dma` in a **low trailing-504d causal percentile (≤ 0.40)`. Both gate legs leak-free/causal. Headline H21, depth ≥ 8%.

| Metric (H21) | Baseline (always-on) | Gated | Δ |
|---|---:|---:|---:|
| precision | 0.085 | **0.249** | **+193% (2.9×)** |
| recall | 0.903 | 0.549 | −0.354 |
| F1 | 0.156 | **0.342** | **+119% (2.2×)** |
| fp_rate | 0.915 | 0.751 | −0.164 |
| fire-rate | ~80% | **~17%** | −63 pts |
| episode precision | 0.087 | **0.222** | +0.135 |

- **OOS (2020+) is STRONGER, not weaker:** precision 0.099 → **0.259**, F1 0.180 → **0.353**, fp_rate 0.901 → 0.741. Permutation p=0.0 full AND 2020+ (400 draws).
- **Per-horizon F1 (gated vs base):** H5 0.100 vs 0.027 · H10 0.197 vs 0.065 · **H21 0.342 vs 0.156** · H42 0.394 vs 0.258. Helps at **every** horizon; the gain is largest at H10–H42.
- **Behaviorally sane:** fires in 2008/2011/2015–16/2018/2020/2022/2025; **silent in calm bull years** (2013/2017/2021/2024 = 0 alerts). Median lead ~13bd preserved — **the gate trades recall for precision but does NOT make the signal lagging.**
- **Honest cost:** recall falls 0.90 → 0.55 by design. This IS partly a recall-for-precision trade — but unlike the rejected rules below, the trade *raises lift ~3×*, holds OOS, and survives permutation, and it still keeps majority recall (0.55) at the watch budget. The `< 200dma` leg means the gate only fires once price has begun deteriorating, so it sacrifices the earliest froth/blow-off precursors (`bubble_ext`'s purpose). For pre-break topping, the **breadth-pctl-only** gate (precision 0.162, recall 0.76) is the milder alternative.

### Rank 2 — `conjunction_required` / armed+confirm (ADOPT) — best for preserving more recall

**Config:** escalate to elevated/alert only when **(a)** a *validated* leading leg (2020+ lift ≥ 1.20 → currently `credit_oas_roc`) is at/above its `thr_pct` inside a Tier-A scare that is ≥ watch, **AND (b)** ≥ 1 *other* Tier-A scare is ≥ watch. "Armed leg + second-scare confirms" — NOT a naive count.

| Metric (H21, 2020+) | Baseline | armed+confirm | Δ |
|---|---:|---:|---:|
| precision | 0.127 | **0.188** | **+48%** |
| lift | 1.03 | **1.52** | +0.49 |
| F1 | 0.220 | **0.284** | **+29%** |
| recall | 0.836 | 0.577 | −0.259 |
| fp_rate | 0.812 | **0.351** | **−57% (halved)** |
| fire-rate | 0.815 | 0.379 | −0.436 |

- **The baseline state-machine FAILS the 2020+ permutation null (perm-p=0.168)** — its precision is indistinguishable from a random signal at the same fire rate in the modern era. **armed+confirm passes p=0.0 full AND 2020+.**
- **Per-horizon (2020+):** H5 prec 0.042/lift 1.46 · H10 0.083/1.43 · **H21 0.188/1.52** · H42 0.341/1.42. Era-robust lift ~1.4–1.5× across all four horizons.
- **Why it works:** gating on the validated *leading* leg filters the always-on coincident-leg noise that inflates the baseline fire-rate, while the second-scare confirmation preserves recall better than `regime_gating`. The edge is the **leading-leg ARM, not the count.**
- **Rejected sub-variants (count-only):** `≥2-of-N at caution` cuts FP but **FAILS 2020+ permutation hard (perm-p=0.79)** and F1 DROPS below baseline 2020+ (0.188 vs 0.220) — a pure count requirement *destroys* the modern edge. `AND-of-all-scares` is degenerate (9 alerts pre-2020, 0 TP). **Naive conjunction does not work.**
- **Honest cost:** recall 0.84 → 0.58 (still majority). Episode-level FP rises (more, shorter episodes) because the rule toggles around the watch band → needs a hysteresis/min-duration overlay (§4).

### Rank 3 — `confirmation_persistence` / `consec_N3` (MAYBE → do not adopt as primary)

**Config:** alert only after 3 consecutive raw-elevated days.

- Full-sample F1 **flat** (0.1573 → 0.1569, −0.0004); FP cut 8.6% but recall also dropped 8.0% — a **near-proportional, near-chance trade**.
- **Fails the full-sample delta-permutation** (does persistence beat random thinning of the same alert pool? p=0.231/0.334/0.482 for N=2/3/5). Only the **OOS delta is significant** (p=0.061/0.026/0.011) — persistence helps *only* in the modern regime, and only marginally (OOS precision 0.099 → 0.104).
- Persistence **fragments** long episodes (more, shorter) rather than killing whole false episodes — it does not deliver the hoped-for "remove a false alarm" win.
- **Per the spec** ("a rule that only helps full-sample but not 2020+ is rejected"), the converse partial-pass = **MAYBE**. **Verdict: do NOT use as a gate.** If wanted, surface `consec_N3` as a *confirmation badge* on an already-fired alert (cuts ~9% FP, −3% OOS recall, lead unchanged), never as a suppressor of early single-day flags.

### Rules that only traded recall for precision (flagged, not adopted)

- **`≥2-of-N caution count conjunction`** — REJECT (fails 2020+ permutation, F1 below baseline OOS).
- **`not_quad_Q1` regime gate** — REJECT (precision 0.093, *worse* than other gates; drawdowns happen in Q1 too).
- **VIX-level / quad gates** — underperform price/breadth gates (p 0.13 vs 0.23–0.25); not adopted.

---

## 3. RECOMMENDED OPERATING POINTS (per scare-type × horizon × FP budget)

Two alert tiers, mapped to an explicit FP budget. **Loud banner** = de-risk action, tight FP budget (~≤1–2 false episodes/yr). **Quiet watch tier** = context/sizing, higher recall accepted.

### 3a. LOUD banner (de-risk): `regime_gating` overlay, fire only when context-confirmed

| Scare focus | Horizon | Rule | exp. precision | exp. recall | exp. lead |
|---|---|---|---:|---:|---:|
| Any Tier-A (default loud) | **H21** | elevated **AND** `SPY<200dma` **AND** breadth-pctl ≤ 0.40 | **0.25** | 0.55 | ~13bd |
| Any Tier-A (medium-term) | H42 | same gate | **0.37** | 0.43 | ~13bd |
| Credit/Rates (fast) | H10 | gate + armed `credit_oas_roc`/`rates_move` | **0.11–0.12** | 0.66 | 10–15bd |

- **FP budget check:** gated fire-rate ~17% with episode precision ~0.22–0.25 → in calm years (2013/17/21/24) **0 episodes** fired; in active years ~3–6 episodes of which ~1-in-4 are pre-drawdown. This meets a "few loud calls/yr, mostly in real regimes" budget. Do NOT run the loud banner ungated (current behavior = ~80% of days → unusable as an action signal).

### 3b. QUIET watch tier (context/sizing): `conjunction_required` armed+confirm

| Scare-type | Horizon | Rule | exp. precision | exp. recall | exp. lead |
|---|---|---|---:|---:|---:|
| Bubble (modern precursor) | H21 | armed `bubble_ext`@pct≥0.90 + 2nd Tier-A ≥ watch | ~0.19 (2020+) | 0.58 | ~10bd |
| Credit (full-history) | H5–H10 | armed `credit_oas_roc`@pct≥0.90 + 2nd scare | 0.04–0.08 | 0.54 | ~10bd |
| Rates | H10–H21 | armed `rates_move`@pct≥0.90 + 2nd scare | 0.08–0.19 | 0.57 | ~15bd |
| Growth | H21–H42 | armed `growth_cyc_def`@pct≥0.90 + 2nd scare | 0.19–0.34 | 0.54 | ~12bd |

### 3c. Per-scare-type tuning notes

- **`vol` (Tier B) stays escalator-only.** `vol_term` is noise beyond H10 (0.5–0.75); its only real value is H5 2020+ (2.3×). Keep it as a *short-horizon* escalator on an already-lit Tier-A state; never let it originate. **Do not add the genuinely-leading vol/positioning precursors (put/call, dealer GEX, implied-corr) until deep history accrues** (see §5).
- **`bubble` is the modern (2020+) workhorse; `credit` the full-history workhorse** — they are complementary across eras. The armed-leg gate should treat *both* as validating arms even though only `credit_oas_roc` clears the strict era-robust bar today; `bubble_ext` clears the 2020+ bar (2.34) but `era_robust=False`. **Recommend: add a second validated-arm path for `bubble_ext` scoped to the 2020+ slice** (see §4, optional).
- **Horizon routing:** run the loud banner at H21 (the knee — best gated F1 0.342). Surface H42 for medium-term de-risk (highest gated precision 0.37–0.39). Treat H5–H10 as quiet-tier only — short-horizon precision is structurally low even gated.

---

## 4. CONCRETE ENGINE CHANGES — `engine/risk_radar.py`

Each delta is bounded so the Opus self-correction loop (`engine/risk_radar_review.py`, `data/risk_radar/calibration.json`) can tune *within* these limits. **No score math changes — decision/gate layer only.**

### Change 1 — Raise `alert_from` off the saturated band (highest-impact, smallest diff)
The single biggest win is to stop firing the loud banner on 72–81% of days. Either raise `_ALERT_FROM` or, preferably, add the context gate (Change 3) and keep `elevated` as the *pre-gate* trigger.
```python
# Current
_ALERT_FROM = "elevated"            # loud banner fires at/above this  -> 72-81% of days
# Recommended: gate the loud banner (Change 3); keep elevated as pre-gate.
# If gating is NOT wired, raise to "risk_off" as a stopgap (cuts fire-rate sharply,
# but loses recall — gating is strictly better, lift 2.9x vs threshold-only).
```
**Justification:** the saturated `elevated` alert has lift ≈ 1.0; gating it lifts precision 0.085 → 0.249 (verified, perm p=0.0).

### Change 2 — Tighten `_DEFAULT_BANDS` (modest; secondary to the gate)
Post-2020 sub-scores run hot, so `elevated=70` trips near-permanently. Bump the loud bands; leave `watch` low for the quiet tier.
```python
# Current
_DEFAULT_BANDS = {"watch": 45.0, "caution": 58.0, "elevated": 70.0, "risk_off": 85.0}
# Recommended (bounds for the Opus loop in [], elevated/risk_off raised):
_DEFAULT_BANDS = {"watch": 45.0, "caution": 60.0, "elevated": 76.0, "risk_off": 88.0}
#   elevated  in [72, 80]   (was 70 -> fires ~81% of 2020+ days)
#   risk_off  in [85, 90]
#   caution   in [55, 62]   watch left at 45 to preserve quiet-tier recall
```
**Justification:** band-raise alone is *necessary but not sufficient* — persistence work showed nibbling a saturated band yields flat F1. The gate (Change 3) does the heavy lifting; this just stops the band from re-saturating.

### Change 3 — NEW context gate on loud-banner alert (the `regime_gating` ADOPT)
Add a causal context gate so `alert` requires the elevated state AND deteriorating trend/internals. Implement as a new helper + one line in `compute()`.
```python
# New module-level constants (Opus-tunable bounds in comments):
_CTX_GATE = {
    "spy_200dma": True,          # require SPY close < 200d SMA
    "breadth_pctl_max": 0.40,    # require %>200dma breadth in trailing-504d causal pctile <= this
                                 #   bound: [0.30, 0.50]
}
# In compute(), after `alert = _STATE_ORDER.index(state) >= ...`:
if alert and calib.get("ctx_gate", _CTX_GATE):
    g = calib.get("ctx_gate", _CTX_GATE)
    ctx_ok = (_spy_below_sma(sigrow, 200) and
              _breadth_causal_pctl(sigrow) <= g["breadth_pctl_max"])
    alert = bool(alert and ctx_ok)          # gate the LOUD banner only; keep `state` for the quiet tier
```
**Justification:** verified precision 0.085 → 0.249 (2.9×), F1 0.156 → 0.342 (2.2×), fire-rate 80% → 17%, holds OOS (0.099 → 0.259), perm p=0.0 both eras. Gate the *banner*, not the *state* — the quiet watch tier still surfaces the ungated state for context/sizing.

### Change 4 — armed+confirm conjunction (the `conjunction_required` ADOPT)
Replace the naive `conjunction = len(hotA) >= 2` count with armed-leg + second-scare logic for the alert escalator. Keep the displayed `conjunction` flag for transparency but gate escalation on the armed version.
```python
# Current
hotA = [s for s in tierA if s["score"] >= bands["caution"]]
conjunction = len(hotA) >= 2
# Recommended: armed = validated leading leg at thr inside a hot Tier-A scare
def _armed(scares, calib):
    for s in scares:
        if s["tier"] != "A":
            continue
        for lg in s["firing_legs"]:
            if lg["confirmed"] and _is_validated(lg["leg"], calib):
                return True
    return False
armed = _armed(scares, calib)
watch_hot = [s for s in tierA if s["score"] >= bands["watch"]]
conjunction = len(hotA) >= 2                      # keep for display
armed_confirm = armed and len(watch_hot) >= 2     # NEW: drives the quiet-tier escalation
```
**Justification:** verified 2020+ precision 0.127 → 0.188 (+48%), F1 +29%, fp_rate halved, perm p=0.0; the naive count FAILS the 2020+ permutation (p=0.79). Pure count conjunction destroys the modern edge.

### Change 5 — hysteresis / min-duration to stop episode chatter
Both ADOPT rules toggle around the watch band → more, shorter false episodes at the episode level. Add a min-duration latch so a fired banner stays latched N days unless the state drops below `caution`.
```python
_ALERT_HYSTERESIS_BD = 5     # bound [3, 10]: latch the banner this many bd; clear on state < caution
```
**Justification:** persistence work showed both ADOPT rules fragment episodes (episode precision lags day-level by ~0.10). A latch (not a *suppressor*) cleans episode-level FP without adding lag — distinct from `consec_N3`, which suppresses early flags and is rejected.

### Change 6 — `_LEG_CALIB` lift refresh (feed the Opus bounds with measured numbers)
The validation confirms the committed numbers but sharpens the era split. Recommend NO structural change to `_SCARES` weights/tiers (they already correctly put `credit_oas_roc` at 0.85 and keep `vol` Tier-B) — but record the verified era-specific lifts as the Opus loop's prior so it does not "rediscover" dead legs:
```python
# Verified era split (keep values; the actionable change is the era_robust flags / arm-eligibility):
#   credit_oas_roc : era_robust True  (1.97 full @H5, 1.23 2020+)  -> validated arm (full-history workhorse)
#   bubble_ext     : 2.34 2020+, 1.00 full -> 2020+-scoped validated arm (modern workhorse) [OPTIONAL]
#   rates_move, growth_cyc_def : most era-robust at short H -> keep as confirming legs
#   vol_term       : Tier-B escalator-only, H5-only -> DO NOT promote
```
Optional: allow `bubble_ext` as a *2020+-scoped* validated arm in `_is_validated` (its 2.34 lift is the genuine modern precursor) — but keep the strict global `_VALIDATED_MIN = 1.20` gate so pre-2020 history is not polluted.

### Change 7 — `_PROB_CAL` drawdown_prob recalibration
The escalating prob surface is reasonable but the *gated* elevated state is now ~3× more informative, so the elevated/risk-off rows should reflect the gated conditional, not the saturated one.
```python
# Current h21 elevated=0.20, risk-off=0.27 (measured on the SATURATED state).
# Recommended (measured on the GATED elevated state; base_h21=0.178 unchanged):
#   h21: elevated 0.20 -> 0.25 (gated precision @H21), risk-off 0.27 -> 0.33
#   h10: elevated 0.10 -> 0.12 (gated precision @H10)
#   h5 : leave (short-horizon gated precision still ~0.05-0.06)
# Bounds for the Opus loop: each band within +/-0.05 of the measured gated conditional.
```
**Justification:** the displayed odds must match the *gated* alert the user now sees — gated H21 precision is 0.25, not 0.20.

---

## 5. HONESTY

### What generalizes
- **`regime_gating` (SPY<200dma + low breadth pctl)** generalizes across eras and is *stronger* OOS (F1 0.180 → 0.353). It is the most robust finding. Mechanism is sound: it filters benign percentile-of-percentile crossings in calm uptrends, which are the dominant FP source.
- **The leading-leg ARM** (validated leg at thr) generalizes — gating on a *measured leading* leg rather than coincident noise is the durable insight, era-independent in logic even though *which* leg is validated is era-specific.
- **Saturation is the root problem** across all horizons and dd-thresholds — not regime-specific.

### What is era/regime-specific (handle with care)
- **Leg validity flips by era:** `credit_oas_roc` leads full-history but is dead 2020+; `bubble_ext` is dead full-history but the strongest 2020+ precursor. Any rule that hard-codes a single arm leg will silently degrade when the regime rotates. **The armed-leg set must be era-aware** (Change 6) and the Opus loop must keep re-measuring.
- **`vol_term`'s 2.3× @H5 2020+** is a short-horizon, modern-only spike that is noise beyond 10d — do not generalize it.
- **`confirmation_persistence`** only helps 2020+ and only marginally — explicitly **not** a generalizing finding.
- **Long-horizon "precision"** (H42–H63, base rate ~0.4) is a base-rate artifact, not skill — never quote raw long-horizon precision as evidence.

### Residual FP no rule fixed
- Even the best gate leaves **precision ~0.25 @H21** (vs ~0.08 base): **~3 of 4 alert episodes are still not pre-drawdown.** This is a ~1.5–3× conditional lift, NOT a forecast — consistent with the engine's stated modesty. The de-risk response must remain **sizing, not selection.**
- **Episode-level precision (0.22–0.25) lags day-level** — clustered alerts mean roughly 1-in-4 alert *episodes* is a true pre-drawdown even after gating. Change 5 (hysteresis) mitigates but does not eliminate this.
- The `<200dma` leg means the loud banner **misses the earliest froth/blow-off precursors** (it only fires once price has rolled over). The breadth-pctl-only milder gate (precision 0.162, recall 0.76) recovers some pre-break sensitivity at lower precision — a deliberate tier choice, not a free lunch.

### What needs not-yet-collected data
- The genuinely-leading **vol/positioning precursors — put/call, dealer GEX, implied correlation — are NOT in deep history yet.** `vol` stays Tier-B (escalator-only) until their collectors accrue ≥ a full cycle of leak-free history, then they must clear the *same* strict bar (day-level lift + perm + 2020+ holdout) before promotion. This is the single biggest expected upgrade to short-horizon precision (H5–H10), which no current rule fixes.
- A longer 2020+ OOS window would firm up the small-n episode counts (OOS gated = 4–8 episodes); current OOS episode metrics are *indicative only*.

---

*All findings are recommendations on a frozen snapshot; no tracked files were edited. Eval scripts: `/tmp/risktune/acc.py`, `rule_regime_gating.py`, `rule_conjunction_required.py`, `rule_confirmation_persistence.py`; dumps in `/tmp/risktune/*.json`.*
