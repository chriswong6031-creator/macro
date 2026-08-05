# Options information-dislocation engine — feasibility assessment and build

_Assessed and built 2026-08-05. Proposal: a 13-feature, 6-score options information engine.
Verdict: **the framing is right, the feature list is half-buildable, and the score
architecture as specified is a forbidden shape here.** The buildable half ships._

---

## §0 Verdict in one page

| Proposal element | Verdict | Why |
|---|---|---|
| "Do not use raw call/put volume" | **CONFIRMED on our own data** | Raw call-vs-put volume tilt IC5 flips sign between sub-periods: +0.049 → −0.030. The proposal's opening warning is correct and we measured it. |
| Buyer-initiated call / put volume | **CANNOT BUILD** | OPRA trades+NBBO are 403 on our plan. The bar-only substitute recovers a contract's net daily sign at **0.41 — worse than a coin flip**. |
| Opening vs closing trades | **CANNOT BUILD** | Needs Cboe Open-Close (~$2,000/mo). Procurement already adjudicated **DENIED** (RO-10, W6 SKIP-ALL). |
| Delta-weighted **directional** volume | **MEASURED DEAD** | Direction needs signing we lack; delta-adjustment was tested and **rejected** (0.39 < 0.41 tick rule). The direction-free form flips sign sub-period. |
| Changes in 25-delta skew | **BUILT** | Survives neutralisation, sign-stable, sign-correct vs Xing-Zhang-Zhao. |
| Front-vs-back IV slope | **BUILT** | Survives neutralisation (level and change). |
| Implied vs realized vol | **BUILT, DEMOTED** | 86% of its raw IC was implied-vol level. Survives only as a neutralised residual. |
| Option-implied expected move | **BUILT, NOT A PREDICTOR** | Raw `em30` **is** the IV level. Its −0.23 IC is the low-vol factor, not information. |
| Actual vs implied pre-event move | **BUILT (accruing)** | Scale-free by construction, so it escapes the vol-level trap. Null until events pass. |
| Synthetic-stock price deviation | **STRUCTURALLY ABSENT → substituted** | Chain store carries no option *price* column. Its IV-space equivalent (Cremers-Weinbaum `ivspread`) is computed and shipped. |
| Concentration by strike/expiry | **BUILT, RE-PURPOSED** | Dies as a return predictor under neutralisation (+0.040 → +0.007, flips). Retained as a *fragility/hazard* read, which is a different claim. |
| Change in OI after unusual volume | **BUILT** | Standing delta-weighted OI tilt is the strongest survivor. |
| Stock flow confirms option flow | **BUILT** | Categorical confirm/contradict read. |
| The six named **scores** | **4 of 6 REJECTED AS SPECIFIED** | Fused escalating composites are a forbidden pre-gate shape (RO-2 / Signal Commons R3). Shipped as categorical **reads** over named primitives instead. |

**Net: 9 of 13 features built, 3 unbuildable at any price we will pay, 1 substituted.
2 of 6 scores ship as numbers; 4 ship as categorical reads.**

---

## §1 The finding that shaped the whole build

Run naively, almost every "options information" feature is a **repackaged bet on implied-vol
level** — a long-known priced characteristic, not information.

Measured on our own panel (41 chain dates × 392 names, 2026-06-15→07-31), per-date
cross-sectional rank IC vs SPY-relative 5-day forward returns, before and after per-date
rank-space residualisation on (`iv30`, `log spot`):

| feature | raw IC5 | neutralised IC5 | sub-period sign flip? | verdict |
|---|---|---|---|---|
| `em30` (implied expected move) | **−0.2297** | *is* `iv30` | no | **not information — it IS the vol level** |
| `iv_rv` (implied − realized) | −0.1090 | **−0.0148** | no | 86% was vol level |
| `turnover` | −0.0599 | **−0.0071** | **YES** after | dead |
| `kv_conc` (volume concentration) | +0.0403 | **+0.0065** | **YES** after | dead as predictor |
| `term_slope` | −0.0922 | −0.0402 | no | survives, halved |
| `skew` | −0.0622 | −0.0305 | no | survives, halved |
| `skew_accel` | −0.0683 | −0.0554 | no | survives |
| `d5_ivspread` | +0.0941 | +0.0505 | no | survives |
| `d5_term_slope` | +0.0651 | **+0.0659** | no | barely contaminated |
| `oi_tilt` (Δ-weighted call/put OI) | −0.0673 | **−0.0873** | no | **strengthens** |
| `v_tilt` (raw call/put volume) | +0.0068 | +0.0134 | **YES** | dead |
| `dw_tilt` (Δ-weighted volume) | −0.0204 | −0.0107 | **YES** | dead |

An engine that skipped neutralisation would have shipped `event_expected_move_gap` at an
apparent IC of −0.23 (t≈−9.4) and been, in fact, **short high-volatility stocks in one
six-week window**. That is the single most important thing this assessment produced.

`oi_tilt`'s sign is worth naming: call-heavy standing OI predicts **lower** forward returns.
That is a **crowding** signal, not a bullish confirmation — precisely the proposal's own
"not 'someone bought calls, therefore moon'".

### What the panel cannot do

41 dates in **one regime**. At h=5 that is ~8 independent windows; at h=21, ~1. **Every
t-statistic on this panel is vacuous by construction** — overlapping windows inside a single
regime. Nothing here is validated and nothing may be described as such.

A moving-block bootstrap (block=6) over dates says only that the surviving signs are robust
*within* the window — `oi_tilt` 100% sign-keep [−0.128, −0.035], `d5_term_slope` 100%
[+0.042, +0.080], `skew_accel` 100% [−0.078, −0.032] — and that they are broad, not a few
names (top-10 of 392 carry ~10% of the contribution). That is the bar for **shipping
display-tier**, not for authority.

---

## §2 Why there are reads, not scores

RO-2 / Signal Commons R3: fused escalating composites are a **forbidden shape pre-gate** —
"no ... scores, or ranks anywhere a reader can lift them pre-gate ... Any summary of options
state may only ever be a post-hoc roll-up of already-gated survivors."

Four of the six requested scores (`directional_option_information`, `volatility_disagreement`,
`option_stock_confirmation`, `dealer_positioning_fragility`) are multi-primitive fusions by
construction. They ship as **categorical reads over separately-visible named primitives** —
never a 0-100 or −3..+3 number. Two (`skew_acceleration`, `event_expected_move_gap`) are
genuinely single measured quantities, so they lawfully carry a value.

The proposal's own four stated *uses* — confirmation/contradiction, pre-event expectations,
crowding, vol regime — are fully honoured. Only the liftable-number packaging is refused.

Per RO-3 the reads are caution/context only: they may **lower** confidence in a candidate the
rest of the stack already likes, never originate or escalate one.

---

## §3 Registry adjacency — declared, not evaded

Two `DO_NOT_REBUILD.md` rows land near this work. Both are declared in the engine docstring.

* **"DOI (options delta-OI family) | DEAD"** — that kill closed DOI *persistence tested at
  sector-ETF level* (W-E1: 0/12 across ~24 roots). `oi_tilt` is a different construction on a
  different population: single-name **cross-sectional**, IV-level-neutralised, ~390 names. The
  same masterplan lists single-name cross-sectional claims as **blocked on data** ("Store has
  only NVDA") — never tested, not killed. It ships display-only and claims no revival.
* **"Skew-deceleration | UNSUPPORTED"** — that kill closed the *bullish-deceleration*
  hypothesis. W-E1's lone survivor pointed **opposite** the bullish premise. `skew_accel` here
  carries that opposite sign (rising skew → lower forward returns), so this is **concordant
  with** the existing evidence, not a re-litigation of the killed direction.

---

## §4 Literature — priors to gate with, never evidence to deploy

The proposal's supporting claim ("option volume has been shown to contain information about
future underlying stock movements") is true of the published record and **materially decayed**:

* **Pan & Poteshman (2006)** — >40bps next-day, >1%/week, from **buyer-initiated
  open-position** put-call ratios built on a proprietary CBOE dataset. That dataset is today's
  Cboe Open-Close (~$2,000/mo, EOD back to 2011). This is the paper the proposal's top three
  features are describing, and it is *definitionally* not replicable without that purchase.
* **Cremers & Weinbaum (2010)** — ~50bps/week; the paper itself reports predictability
  **decreasing over its own sample**, consistent with mispricing that eroded.
* **Xing, Zhang & Zhao (2010)** — steepest smirks underperform ~10.9%/yr; subsequent work
  reports decay, with no smirk effect observed post-GFC in some samples.

Per the standing rule these enter as **priors that set a sign to pre-register**, never as
effect sizes to quote on a user-facing surface. Our own IC magnitudes (0.02–0.09) are an
order of magnitude below the headline figures, which is what decay looks like.

---

## §5 What shipped

| Artifact | Role |
|---|---|
| `engine/options_dislocation.py` | Primitives + cross-sectional neutralisation + categorical reads + accruing ledger. Pure; IO isolated. |
| `scripts/build_options_dislocation.py` | Nightly builder → `data/options_dislocation/snapshots.parquet` + `site/options_dislocation.json`. Per-read coverage printed so an all-null layer cannot pass as healthy. |
| `scripts/validate_options_dislocation.py` | Dormant gate. Pre-registered signs, 120-date × 15-name power floor, BH-FDR across the whole primitive × horizon family. |
| `tests/test_options_dislocation.py` | 21 tests, incl. the three-way gate discipline below. |

Wired into `daily.yml`, `closing-bell.yml`, `engine-render.yml` (after skew/ivspread, whose
ledgers it joins) — **and into each lane's `ORDER` list**, without which a first failure
passes silently. Gate runs in `validate-leading-legs.yml` and its verdict is committed.

### The tests that carry the weight

* **Neutralisation works**: a feature that is a pure monotone function of `iv30` must
  neutralise to ~zero; an IV-independent feature must survive; a cross-section thinner than
  20 names must refuse to produce a residual at all.
* **The gate cannot open early**: a 40-date panel carrying a planted, correctly-signed,
  overwhelming predictor **still does not score**. The floor is a precondition, not a tiebreak.
* **The gate rejects a wrong-signed predictor**: 150 dates, strong signal, opposite the
  pre-registration → not scored. A failed hypothesis is not re-labelled a discovery.
* **The gate is not decorative**: 150 dates with the pre-registered sign **does** open it —
  without this, every shut-gate test above would pass on a gate hard-wired to refuse.

### Current honest state

`scored=false`, `status="insufficient_history (have 41/120 dates, 392/15 names)"`. All seven
pre-registered primitives are sign-correct and six survive FDR at 5d — **and the gate still
refuses to score them**, which is the intended behaviour on a one-regime panel.

---

## §6 Open decisions for the operator

1. **Surface.** This ships as an engine + payload + ledger. It has **no page**. Whether the
   reads belong on the options workspace (as a per-name context strip) or on the stock dossier
   is a design call, not an engine call.
2. **Procurement stays denied.** Cboe Open-Close (~$2k/mo) is the only honest route to the
   proposal's top three features. RO-10 denied it; nothing here re-opens that. If it were ever
   bought, `MEASURED_NULLS` names exactly which fields would light up.
3. **The clock.** 120 dates at ~1 chain/day means a first real verdict around **2026-12**,
   assuming chain coverage holds. Until then this is context that may only lower confidence.
