# P2_1B_F1_REPROBE — RESULTS

**Study:** `P2_1B_f1_concordance_reprobe` (trials P2_1B_F1_REPROBE_T01–T10)
**Program:** Entry Intelligence (EI)
**PREREG:** `research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md` §3.3 / §8 / §11 (APPROVED Fable 2026-07-05)
**Memo:** `P0_MEASUREMENT_MEMO.md` v1.0 (2026-07-04) + §6 v1.1
**Date:** 2026-07-05 · **Author:** Opus subagent under Fable orchestration

---

## VERDICT: `PROMOTION_DIES_PROXY_ONLY`

**F1 rank-weight promotion DIES.** On production COILED washout values, the P1.3
F1 RW safety-net effect that authorized the promotion (T09, 63d stop-out) does not
merely fail to survive — **it reverses sign**: the proxy showed −4.55pp stop-out
(favorable), production shows **+3.34pp stop-out (unfavorable)**. Per PREREG §3.3
the P1.3 F1 verdict is re-scoped **'proxy-definition only'**. F2 is untouched by
this verdict (its evidence base is not proxy-sourced; it may proceed independently
per §11).

The one F1 effect that reproduces on production values is the HG-mode 21d dead-money
reduction (T02: −13.19pp proxy → −15.11pp production, stronger). But T02 is **HG
context only** — the HG gate path is permanently closed (P1.3 §6.2), and the RW
promotion is the only live path. The reproduced dead-money effect cannot authorize
the RW promotion because the RW ship-qualifying trial (T09) reversed.

---

## Integrity / provenance (reuse, not reinvention)

| Check | Result |
|---|---|
| Replay MD5 | `906175f9eb8caa351ed6d7d5c56265d3` — matches concordance artifact |
| `engine/coiled.py` | byte-identical to commit `4bebc06716` (branch `ei/p2-board-stack`) |
| Production compute path | copied verbatim from `scripts/p2_1b_concordance_check.py` @ `4bebc06716` |
| Statistic | copied verbatim from `run_P1_3_v2.py` (episode label-permutation MWU, N_PERM=5000, two-sided, Phipson-Smyth +1) |
| **Concordance reproduced exactly** | **YES** — n_valid=47,182, rate=0.664046, prod_true=36,734, prod_false=10,448, prod_none=2,757 (all match `concordance_check.json`) |

Because the replay artifact and `engine/coiled.py` are both identical to the commit
that produced the 66.40% concordance, the production washout values here reproduce
that computation bit-for-bit (verified in-run). The reprobe is a faithful re-encoding
of F1, not a re-derivation.

---

## Population & fire-rate impact (production washout)

| Quantity | Proxy (P1.3) | Production (reprobe) |
|---|---|---|
| Verdict-grade fires | 49,939 | 49,939 |
| Washout state **defined** | 49,939 (boolean, no nulls) | 47,182 (2,757 excluded: <308-bar PIT history → `None`) |
| Washout = **True** (F1_pass) | 22,965 | **36,734** |
| Washout = False | 26,974 | 10,448 |
| **HG fire-rate impact** (would-block = not-in-washout) | **54.0%** (26,974/49,939) | **22.1%** (10,448/47,182) |

As predicted, production fire-rate impact differs from 54%: production **finds more
washout** (36,734 vs 22,965 True), so a hard gate would block *fewer* fires (22.1%).
This is the concordance direction (`production_finds_more_washout`; 15,743 proxy-False
→ production-True, 33.4% of valid pairs) expressed as a fire-count.

---

## Mandatory negative calibration control (on the production encoding)

Run **before** the grid (a grid result without it is unacceptable). 200 permuted-label
draws on the production-washout encoding:

| Metric | Value | Expectation | Status |
|---|---|---|---|
| Rejection rate @α=0.05 | **0.085** | ~0.05 (tolerant band ≤0.12) | PASS |
| p-value mean / median | 0.472 / 0.467 | ~0.5 | PASS |
| KS-uniformity D / p | 0.060 / **0.458** | large p (uniform) | PASS |
| Positive control (inject +0.05 shift) | perm_p=2.0e-4, r=−0.31 | p≪0.05 | PASS |

The instrument calibrates on the new encoding: permuted labels reject near nominal
and p is uniform; the injected effect is detected. Sanity gate (param/perm divergence,
the P1.3 round-1 defect signature) did not trip.

---

## Side-by-side: proxy (P1.3) vs production (reprobe) — F1 T01–T10

BH family = the 10 reprobe trials only (m=10, q≤0.10). `fav`=favorable direction,
`surv`=survives BH, `sgn`=sign-stable both halves.

| Trial | mode | hz | target | proxy Δpp | fav | surv | sgn | proxy r | ‖ | **prod Δpp** | fav | surv | sgn | **prod r** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | HG | 21 | STOPPED | +2.41 | N | Y | Y | −0.125 | ‖ | **+4.84** | N | Y | Y | −0.105 |
| **T02** | HG | 21 | DEAD_MONEY | **−13.19** | **Y** | **Y** | **Y** | −0.125 | ‖ | **−15.11** | **Y** | **Y** | **Y** | −0.105 |
| T03 | HG | 21 | CUSHIONED | −4.10 | N | Y | Y | −0.125 | ‖ | −4.49 | N | Y | Y | −0.105 |
| **T04** | HG | 63 | STOPPED | **−5.21** | **Y** | **Y** | **Y** | −0.098 | ‖ | **−0.87** | Y | Y | **N** | −0.061 |
| T05 | HG | 63 | DEAD_MONEY | −0.13 | Y | Y | Y | −0.098 | ‖ | −0.27 | Y | Y | Y | −0.061 |
| T06 | HG | 63 | CUSHIONED | −2.15 | N | Y | Y | −0.098 | ‖ | −4.19 | N | Y | Y | −0.061 |
| T07 | RW | 21 | STOPPED | +2.58 | N | Y | Y | −0.109 | ‖ | +5.14 | N | **N** | Y | −0.006 |
| T08 | RW | 21 | CUSHIONED | −3.62 | N | Y | Y | −0.109 | ‖ | −1.68 | N | **N** | Y | −0.006 |
| **T09** | RW | 63 | STOPPED | **−4.55** | **Y** | **Y** | **Y** | −0.084 | ‖ | **+3.34** | **N** | Y | Y | **+0.020** |
| T10 | RW | 63 | CUSHIONED | −1.79 | N | Y | Y | −0.084 | ‖ | −2.19 | N | Y | Y | +0.020 |

Cohort sizes: HG A/B proxy 22,965/26,974 → production 36,734/10,448. RW moved-up A/B
proxy 20,698/29,241 → production 27,403/19,779.

### The three task-mandated deltas

- **T02 dead-money Δ:** −13.19pp (proxy) → **−15.11pp (production)** — reproduces,
  *stronger*, BH-survive, sign-stable (H1 −18.15pp, H2 −12.98pp). This is the sole
  cleanly-reproduced safety-net effect. HG context only.
- **T04 / T09 stop Δ (the promotion axis):**
  - T04 (HG 63d stop): −5.21pp → **−0.87pp** — magnitude collapses ~6×, and
    **sign-stability fails** (H1 +0.11pp, H2 −0.19pp; the halves straddle zero).
  - T09 (RW 63d stop, ship-qualifying): −4.55pp → **+3.34pp** — **full sign reversal**
    (r flips −0.084 → +0.020). The favorable stop-out reduction that promoted F1-RW
    is gone; the production cohort has *higher* stop-out. Both halves now positive
    (H1 +1.92pp, H2 +4.99pp — sign-stable in the *unfavorable* direction).
  - T07 (RW 21d stop): +2.58pp proxy (BH-survive) → +5.14pp production, and
    **perm_p 0.54 — no longer survives BH**.
- **Fire-rate impact of production washout:** 22.1% (vs 54% proxy), as noted above.

---

## Why the RW effect reversed (mechanism, verified)

The proxy and production define *different* washout cohorts. Production flags washout
on 36,734 fires vs the proxy's 22,965 — a 60% larger, differently-composed set. In RW
mode the "moved-up" group A is the subset of washout=True names whose within-day rank
bonus actually changed their rank (27,403 rows); group B (not-moved, 19,779) mixes the
9,331 washout=True names that were already top-ranked with all 10,448 washout=False
names. On production values the moved-up cohort's 63d stop-out is **63.72%** vs
not-moved **60.37%** (Δ=+3.34pp). Under the proxy the same construction ran favorable.
The effect is composition-driven: the extra 15,743 washout states production finds
(that the proxy missed) do not carry the proxy cohort's stop-out benefit — they carry
the opposite. The direction is not a coding artifact; it is what the production signal
actually says.

---

## In plain English

> The washout finding from Phase 1 earned a tryout on the strength of one number: names
> in a washout had about a 4.5-point-lower chance of getting stopped out over three
> months. But that number came from a **stand-in** for "washout" (a simple 200-day-average
> rule), not the real production washout detector. When we swap in the real detector — the
> same code the live system uses — the picture inverts. The real detector calls washout on
> a lot more names (36,700 vs 22,900), and once you include all of them, the washout group
> is stopped out **more** often, not less (+3.3 points, not −4.5). The one thing that
> survives is that washout names still spend far less time as dead money in the first month
> (−15 points, even stronger than before) — but that was a bonus, not the reason for the
> promotion, and it only ever applied to the hard-gate design that was already closed.
>
> So the rank-tilt promotion for washout does not go forward on the real signal. The
> Phase-1 result stands only as a fact about the stand-in definition, not the production
> one. (The separate RS-inflection tilt, F2, is unaffected — it never used a stand-in.)

---

## Files

- Run script: `research/entry_intel/p1_runs/P2_1B_F1_REPROBE/run_P2_1B_F1_reprobe.py`
- Results JSON: `research/entry_intel/p1_runs/P2_1B_F1_REPROBE/results.json`
- Run log: `research/entry_intel/p1_runs/P2_1B_F1_REPROBE/_run.log`
- Reused concordance path: `scripts/p2_1b_concordance_check.py` @ `4bebc06716`
- Reused statistic: `research/entry_intel/p1_runs/P1_3/run_P1_3_v2.py`
