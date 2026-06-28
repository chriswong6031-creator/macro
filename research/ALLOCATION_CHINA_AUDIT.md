# allocation_china — Engine Quality Audit

**Question (owner).** Is the `allocation_china` engine (`engine/narrative_rotation.py`, China
instance) actually high-quality and institutional-grade, or "voodoo noise"? Is it predictive,
or — as suspected — a *reactive, lagging confirmer* that can't front-run?

**Method.** Independent backtest (`scripts/allocation_china_audit.py`) of the engine's **actual
composite score** (not a momentum proxy) on a **deeper, survivorship-clean universe** than the
existing Phase-0, with an explicit **lead/lag** test, **de-overlapped** significance checks, and
the book at the engine's **realistic low-turnover hold horizons** (not just monthly churn). The
headline numbers were adversarially re-verified (two 1-month-rebalance artifacts were caught and
corrected below). Run: `python -m scripts.allocation_china_audit`.

---

## Verdict

**Not voodoo — but not a predictor either. It is an honest, well-built 6–12-month momentum/trend
CONFIRMER with no tradeable forward alpha in China; its rotation book adds no return over simply
equal-weighting the same assets; and its only risk benefit is *de-risking-by-cash* (chronic
under-exposure), not crash protection or a risk-adjusted edge.** Use it in Phase 2 as a
**display-only confirmer / focus lens / risk-discipline annotation — never as a return-predictive
score leg, and never as a China drawdown gate.** This independently confirms the house line
([[narrative-rotation-validation]]) and the engine's own self-label (`discipline_not_prediction`)
— and quantifies *why*.

The engine is honest *by construction*: its docstrings, `ai_handoff.do_not_conclude`, and
equal-weight (not conviction-weight) book all already say "momentum rank ≈ a focus lens,
rank-IC ~0; the only edge is drawdown control." The audit refines even that: the drawdown
reduction is real in *absolute* terms but is just the mechanical effect of holding ~57% cash —
it does not beat buy-hold on Sharpe or Calmar — so the China page is correctly EXPERIMENTAL.

---

## What the engine actually does (`engine/narrative_rotation.py`)

- **Score** (`rank_themes`): `score = mean(z(resid_mom_1y), z(13612W)) + 0.25·z(accel)`.
  - `resid_mom_1y` — 1y cumulative (skip last 21d) of market-residual return `e = r − β·r_bench`
    (causal rolling-252 β shrunk 0.66 → 1).
  - `13612W` — 12·1m + 4·3m + 2·6m + 1·12m weighted momentum.
  - `accel` — relative-strength acceleration.
- **Eligibility** (`_abs_gate`): price > 200-DMA **AND** trailing-12m return > 0 (dual momentum).
- **Book** (`allocate`): equal-weight the top-4 *eligible* themes (≤1/parent), idle slots → cash,
  crowding down-size, 30% cap, crash-overlay halves to cash.
- The "validated edge" it cites (gate halves drawdown, MaxDD −49%→−24%) is the **27-year US
  SPDR-sector** result — *borrowed*, not locally validated.

---

## Evidence

**Testbed.** *Primary:* **shenwan** — 31 Shenwan L1 industry indices, **1999–2026 (26.5y)**,
continuous and survivorship-clean. *Context (flagged):* **baskets** — the 22 live curated
A-share theme baskets, ~5y, hindsight-curated (all 22 have **zero removed members** → pure
survivorship curation). Benchmark = Shanghai Composite (000001.SS, deep; the on-shore CSI 300
ETF is too shallow for a 26y run).

### 1 · Forward predictive power — there is none that survives scrutiny

Cross-sectional Spearman rank-IC of the real composite score → forward returns (Shenwan):

| horizon | mean IC | HAC t | hit | perm-p | note |
|---|---|---|---|---|---|
| **1m** | +0.024 | **0.93** | 55% | 0.09 | indistinguishable from zero |
| 3m | +0.039 | 1.49 | 60% | — | not significant |
| 6m (overlapping) | +0.083 | 2.19 | 60% | — | **overlap-inflated** |
| **6m (non-overlapping)** | **+0.056** | **0.88** | — | — | **n=33 — NOT significant** |

→ The overlapping 6m t of 2.2 is an artifact of monthly-sampling a 6-month forward window.
**De-overlapped, t collapses to 0.88 (n=33) — no horizon is statistically significant.** (It is
also regime-concentrated: +0.24 in the thin 1999–2004 ~14-sector universe, +0.05 in 2020–2026.)
There is at most a *faint, non-zero slow-trend tilt* (lead/lag k≥1 averages +0.038) — consistent
with the engine's own "focus lens, rank-IC ~0" — but nothing tradeable.

### 2 · Lead / lag — the confirmer test (decisive)

`IC( score_t , 1-month return of month t+k )`, 31 Shenwan sectors, 26.5y:

| k (months) | −2 | −1 | **0** | **+1** | +2 | +3 | +6 |
|---|---|---|---|---|---|---|---|
| IC | +0.35 | +0.38 | **+0.51** | **+0.02** | +0.04 | +0.03 | +0.05 |

→ The score is **+0.51 correlated with the just-completed month** and **+0.02 with the next
month** — it describes what *already* happened ~25× more strongly than it forecasts what happens
next. (The `k≤0` peak is partly *mechanical*: the 13612W leg literally contains recent returns;
the honest forward test is `k≥+1`, and it is ≈0.) **A lagging/coincident confirmer, not a
front-runner — exactly the owner's read, quantified.** The baskets show the identical shape
(peak +0.47 at k=0, +0.09 at k=+1).

### 3 · The book vs naive baselines, by hold horizon (Shenwan, 26.5y)

| book | CAGR | Sharpe | MaxDD | avg cash |
|---|---|---|---|---|
| engine top-4 dual — **1m rebalance** | +0.71% | 0.13 | −63.5% | 60% |
| engine top-4 dual — **3m hold** | +3.22% | 0.27 | −52.4% | 57% |
| engine top-4 dual — **6m hold** | +2.90% | 0.25 | **−46.2%** | 56% |
| top-4 rel (no gate) — 6m hold | +3.00% | — | −54.5% | — |
| **equal-weight buy-hold** | **+6.59%** | **0.37** | −68.7% | 0% |
| Shanghai Composite buy-hold | +4.16% | 0.29 | −71.0% | 0% |

→ At the engine's realistic **3–6-month** turnover (monthly is the worst case), the book makes
~3%/yr — **still ~half of equal-weighting the same sectors (6.6%), with a lower Sharpe (0.25 vs
0.37) and lower Calmar.** The trend gate **does shallow absolute drawdown** at 6m (−46% gated vs
−55% ungated, ~23pp better than buy-hold's −69%) — **but only because it sits ~57% in cash**;
it is *staying-power via chronic under-exposure*, **not crash avoidance** (the worst single month
is unimproved: ≈ −28% gated vs −27% equal-weight) and **not a risk-adjusted edge** (worse Sharpe
and Calmar than just holding everything). Net information ratio is **negative**.

### 4 · The contaminated basket book looks good — but it's curation, not the engine

On the 22 hindsight baskets the book posts Sharpe 0.67–0.91 — but **equal-weight buy-hold of the
same baskets matches or beats it** (Sharpe 0.74, **IR +1.42 vs the engine's +0.49**), and the
baskets have zero removed members. The apparent "alpha" is the **survivorship/selection of the
curated set**, not the rotation logic. Correctly flagged `contaminated=True`.

---

## Why it behaves this way

A-share sectors **mean-revert at short horizons** ([[china-hk-selection-alpha-reality]]: A-share
momentum is dead, short-term reversal is the edge). A momentum/trend engine in a reverting tape
(a) loads on what just ran (k=0 IC +0.51), (b) earns ~0 forward (the run reverts), and (c) can
only reduce drawdown by stepping aside into cash — it cannot front-run a turn. The slow 6–12m
trend slice that *does* persist is too small to survive China's 25–45% drawdowns and turnover.

---

## Implications for Phase 2 (Sector Central Intelligence)

1. **Narrative-rotation signals enter as CONFIRMER/context only**, never as predictive score
   legs: momentum rank = a "what's already leading" focus lens; durability/rotation-radar =
   coincident regime gauges; eligibility = a "currently trending" flag.
2. **Do not use `_abs_gate` as a risk-control gate in China.** Its only effect is de-risking-by-
   cash; it is not crash protection and not a risk-adjusted edge. At most a descriptive
   above/below-trend annotation; if a cash/de-risk lever is wanted, source it from the
   *validated* regime anchor (`china_regime` liquidity overlay / masterminds risk-off), not this gate.
3. **The only defensible forward axis stays `china_sector_pathway`** (evidence-gated Wilson-CI
   conditional odds) + the cycle state — *that* is where any honest "what happens next" lives.
4. **The central engine's value is confluence + state-mapping**, not a momentum "prediction."
   Weight it so the validated regime/conditional axis leads and gates, while momentum/trend/flow/
   narrative are *capped* context that sizes and confirms and can never masquerade as alpha.
5. **Build the grader on Phase 2 itself** — nothing in the rotation stack has a realized track
   record, so Phase 2 must log its own dated calls and grade them, making predictive power
   *measured*, not asserted.

---

## Caveats (honest scope)

- The deep test uses Shenwan **indices** (index-level residual momentum); the live engine uses
  member-level residuals on curated baskets — a faithful but not byte-identical replication of
  the score. The index testbed is the honest one (the engine's own Phase-0 says baskets cannot
  validate).
- The book test omits the live crowding/crash/vol-target overlays. These were checked and do not
  flip the verdict: vol-target is `display_only` (`_vol_overlay.applied=False`), the 30% pos-cap
  is a no-op at top-4 equal-weight, and the crash overlay fires ~6% of months and does not
  shallow drawdown.
- Idle cash is credited 0% (mildly conservative — biases *in the engine's favor*, yet it still
  underperforms).
- *Corrected from the first draft:* the −63.5% MaxDD and "the gate deepens drawdown / the
  drawdown edge does not replicate" were **1-month-rebalance artifacts**; at 3–6m hold the gate
  shallows absolute DD (via cash), and the realistic-horizon CAGR is ~3% not 0.7%. The
  *return / risk-adjusted / forward-alpha* verdict is unchanged and, with the de-overlapped 6m IC,
  strengthened.
