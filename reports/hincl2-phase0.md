# H-INCL-2 Phase-0 — Stock-Connect Southbound (港股通) Inclusion Events — DEEPER-PANEL RE-RUN

## **VERDICT: NO-GO on both gated trials (T-ANN, T-EFF), robustly — the deeper panel does NOT rescue the battery, it removes the one silver lining. Coverage lifted 7.2× (38→275 of 444 add tickers on the 545-name union panel; episode-K 25→74), and with the small/mid-cap additions now IN the panel the post-inclusion drift is mildly NEGATIVE, not positive: T-ANN/T-EFF +20d mean CAR ≈ −2.6% to −4.5% after screening corporate-action artifacts (raw −8.8%), HAC t ≈ −1.2 to −1.8 (|t|<2, not significant), DSR≈0, BH-FDR rejects neither (q=0.96). The run-1 +5.3% pre-fill rally is REVISED AWAY — on the broad add universe the t−10→t0 run-up is flat-to-slightly-negative (a mega-cap-only artifact). The run-1 T-ANN +5d accrue seed (t=+1.65) COLLAPSES to −0.2% (t=−0.19). Negative mean CAR fails ACCRUE's positive-sign requirement; |t|<2 fails KILL → NO-GO. The one robust exploratory finding is the REMOVAL side: announcement of Connect REMOVAL precedes −6.5% vs HSI over +20d (HAC t=−3.9, screened, K=27) — non-gated, survivorship-selected, but real and worth a dedicated battery. Nothing is wired.**

Pre-registered in `research/HINCL2_PREREG.md`, committed as a SEPARATE commit BEFORE any statistic ran
on the expanded panel (commit timestamp = audit trail). Amends `research/H_INCL_PREREG.md` — the
registered ACCRUE path of run-1 (PR #1077, merged NO-GO). Event study `scripts/hincl2_event_study.py`.
Reports-only per masterplan W3 acceptance; NO engine/board wiring.

---

## 1. Headline feasibility number (the run-1 caveat, resolved) → **275 / 444 (61.9%)**

Run-1's binding caveat was that only **38 of 466 add events** were studiable on the 157-name mega-cap
panel. This run widens the price panel to the **union of every local HK per-ticker store**:

| Store | Names | Add-tickers covered |
|---|---|---|
| `data/hk_search/closes_deep.parquet` (run-1 panel) | 157 | 38 |
| `data/hk_stocks/*.HK.parquet` (in-tree) | 157 | 38 |
| `hk_stocks_ext/*.HK.parquet` (R2 / gitignored, read from absolute path) | 388 | 237 |
| **UNION (de-duped)** | **545** | **275 / 444 = 61.9%** |

**A 7.2× coverage lift.** Studiable add-events rose 38→282, and — critically — **episode-K rose 25→74**
(distinct anchor-dates with ≥1 studiable name), well above the pre-stated K≈20–24 expectation, because
the widened panel makes far more review-batch dates studiable. The 169 still-missing add tickers are
delisted / never-in-HSCI micro-caps, entered at CAR=0 in the survivorship lower bound (§4). This is a
genuinely decision-grade sample — the power objection of run-1 is retired.

---

## 2. Pre-registered gates vs results (episode-level, +20d primary)

Family = 2 gated trials, one BH-FDR family; program DSR `n_trials=32` (bumped from 30, stricter).
Episode = distinct anchor-date (review batch = ONE episode). Fill = next-valid-close (H1/run-1
precedent; in-tree `open` unpopulated — verified). Values below are RAW (frozen spec); §3 shows the
corporate-action-screened robustness, which does not change any verdict.

| # | Trial (anchor · fill) | Episode-K | mean CAR +20d | HAC t (gate ≥+2.0) | BH-FDR reject | DSR (gate ≥0.90) | Split-half same-sign | Surv. LB mean | **Verdict** |
|---|---|---|---|---|---|---|---|---|---|
| T-ANN | announce · next close | 74 | **−8.81%** | **−1.66** | no (q=.96) | **0.00** | yes (both neg) | −2.58% | **NO-GO** |
| T-EFF | effective · next close | 74 | **−8.90%** | **−1.77** | no (q=.96) | **0.00** | yes (both neg) | −2.60% | **NO-GO** |

Mean CAR is NEGATIVE at the primary horizon → fails ACCRUE (which requires POSITIVE mean CAR). |HAC t|
< 2 → not a KILL (nothing significant enough to actively fade). DSR≈0. BH-FDR one-sided-long p-values
are 0.95 / 0.96 (the long hypothesis is decisively not supported). Both trials **NO-GO**.

### Horizon curve (raw episode-level)
| horizon | T-ANN mean CAR / HAC t / DSR | T-EFF mean CAR / HAC t / DSR |
|---|---|---|
| +5d  | −0.95% / −0.62 / 0.002 | −1.11% / −0.99 / 0.002 |
| +10d | −1.95% / −1.15 / 0.000 | −2.53% / −1.64 / 0.000 |
| +20d | −8.81% / −1.66 / 0.000 | −8.90% / −1.77 / 0.000 |
| +40d | −10.74% / −1.68 / 0.000 | −10.47% / −1.68 / 0.000 |
| +60d | −5.22% / −1.20 / 0.000 | −5.88% / −1.41 / 0.000 |

Monotone-negative into +40d then partial mean-reversion — the opposite of the hoped-for post-inclusion
continuation. No horizon is positive; the run-1 +5d seed is gone.

---

## 3. Data-quality robustness — corporate-action artifact screen (mandatory, pre-flagged)

Pre-reg §7 flagged that ext-store adjusted-close could mix raw/adjusted on some names. Inspection of the
left tail confirmed it: the worst events carry **single-day log-returns > 1.0** (e.g. 2498.HK −116%,
2477.HK −178% in one session) — split/adjustment discontinuities, not tradeable returns. These inflate
the magnitude but do NOT create the sign. Dropping any event with an intra-window single-day
|log-return| above a corporate-action tripwire:

| screen | T-ANN +20d mean / HAC t | T-EFF +20d mean / HAC t |
|---|---|---|
| raw (frozen spec) | −8.81% / −1.66 | −8.90% / −1.77 |
| drop \|1d\|>0.69 (~±50%) | −4.33% / −1.29 | −4.49% / −1.47 |
| drop \|1d\|>0.40 (~±33%) | −2.57% / −1.18 | −4.57% / −1.50 |

**Sign and verdict are robust:** mean CAR stays negative, |t|<2, DSR=0 under every screen. The
artifacts change −8.8% into −2.6%…−4.6% but never rescue the long thesis. The 38 run-1 (closes_deep)
names reproduce ~flat (−0.3%), a positive control that the pipeline is consistent with run-1 — the
negative drift is carried entirely by the newly-added small/mid caps (n=244, mean −4.1%).

---

## 4. The mechanism, revised (why the deeper panel makes it WORSE, not better)

Event-time index-relative CAR curve (announce anchor, n≈276, fill bar = t0):

| t | −10 | −5 | −1 | 0 | +1 | +3 | +5 | +10 | +20 | +40 | +60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CAR vs HSI | −2.5% | −2.2% | −1.7% | 0.0% | +0.1% | +1.2%\* | +0.9%\* | −0.3% | −2.2% | −6.0% | −8.4% |

\* the tiny t+3/t+5 positive blip is artifact-driven and vanishes under the |1d|>0.40 screen (+5d → −0.2%, t=−0.19).

- **Run-1's headline +5.3% pre-fill rally (t−10→t0) is REVISED AWAY.** On the broad add universe the
  pre-announcement run-up is flat-to-slightly-NEGATIVE. The +5.3% was specific to the 38 mega-cap
  additions (large, liquid, already-crowded names). The typical Connect addition — a small/mid cap — is
  NOT front-run into the fill.
- **No post-inclusion continuation.** The marginal southbound-buyer demand does not produce a
  capturable drift in the small/mid caps either; the post-fill path drifts mildly negative.
- **Interpretation:** the inclusion "demand shock" is either fully impounded elsewhere (A-share
  cross-listing, index events that co-move) or simply small relative to the idiosyncratic vol of these
  names. A "recently added to Connect" long ranker would have LOST vs HSI over 2018–2026. NO-GO stands
  on both capturability AND direction.

### Exploratory REMOVAL side (调出) — the one robust signal (non-gated)
Bigger sample now (76 events, K=27–28). Removal announcement precedes real underperformance:

| removal anchor | mean CAR +20d (raw) | HAC t (raw) | mean CAR (screened) | HAC t (screened) |
|---|---|---|---|---|
| announce | −4.67% | **−2.83** | −6.48% | **−3.93** |
| effective | −9.07% | −1.42 | −4.28% | **−3.09** |

Removal from Connect eligibility → a robust negative de-rate (|t|>2 on both anchors after screening).
This is **exploratory, NOT gated** (not in the H-INCL long family, not FDR-corrected within a removal
family, and removal names are survivorship-selected toward already-troubled names — removal often
FOLLOWS deterioration). It is not a GO here, but it is the first |t|>2 result this battery has produced
and merits a dedicated pre-registered removal/de-rate battery with a clean removal-cause control.

---

## 5. Verdict, honestly

- **T-ANN: NO-GO.** Mean CAR negative at +20d (−8.8% raw, −2.6% screened), HAC t=−1.66, DSR≈0,
  split-half stably negative. Fails ACCRUE (needs positive sign), fails GO, not a KILL (|t|<2).
- **T-EFF: NO-GO.** Same shape (−8.9% raw, −4.6% screened, t=−1.77).
- **This RETIRES the run-1 ACCRUE path.** Run-1 accrued specifically pending "a deeper panel that
  includes the small/mid caps that ARE the additions." That panel now exists; the result is negative,
  not the hoped-for positive small-cap drift. There is no further deeper-panel accrual to register —
  the mechanism has been tested at decision-grade K and does not go.
- **Not KILL** — the long side is negative but not significantly so (|t|<2); there is no gated basis to
  actively FADE inclusions.
- **Registered follow-up (exploratory → new battery):** the REMOVAL de-rate (|t|~3–4) is the live
  question, not inclusion. Recommend a dedicated pre-reg for a Connect-REMOVAL de-rate signal with a
  removal-cause / already-falling control (to separate "removal causes underperformance" from "removal
  follows underperformance").

---

## 6. What this does NOT show (pre-committed)

- Not a full-universe result — 545 names ≈ current HSCI + legacy panel; 169 delisted/micro-cap add
  tickers remain unobserved (imputed-0 lower bound, which is also negative).
- Not causal ID beyond timing; index-membership changes co-move with size/liquidity/A-share events.
- Not tradeable net of costs/borrow; gross index-relative CAR.
- Ext-store adjusted-close mixes at least a few corporate-action discontinuities; §3 shows the verdict
  is robust to screening them, but per-name CAR on unscreened artifact names is unreliable.
- Removal-side results are EXPLORATORY, non-FDR-corrected, and survivorship-selected — flagged, not
  gated.
- SZSE (深港通) adds cross-checked, not exhaustively unioned (SSE record; ~90% overlap).

---

## 7. Artifacts
- `research/HINCL2_PREREG.md` — pre-registration amendment (committed BEFORE the run).
- `scripts/hincl2_event_study.py` — deeper-panel event study (union panel builder + curve + removal).
- `data/experiments/hincl2_event_study_results.json` — full stats (all horizons, curve, removal, FDR).
- Registry: `data/experiments/registry_seed.json` id `hkca_h_incl_connect_events` (UPDATED in place).
- Roster + run-1 artifacts unchanged (`data/hk_connect_roster/roster.parquet`, `reports/hincl-phase0.md`).
