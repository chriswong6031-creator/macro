# CA-GATE — Confluence-Gate Calibration on Canada · Phase-0 Report

**VERDICT: T1 = ACCRUE · T2 = ACCRUE · T3 = DEMOTE-FLAG (CONDITIONAL — held, not wired).**
**The owner's hypothesis ("the US system detects Canadian stocks about to go up"), answered: NO** — on the 5-year 219-name CA panel the confluence BUYABLE gate adds no measurable go-up edge over each stock's own base rate. It is not harmful in aggregate either: it is doing its real job — **entry hygiene** (fresh, not-topped, oversold-reclaim) — not stock-picking.

Pre-registration: `research/CA_GATE_CONFLUENCE_CALIBRATION_PREREG.md` (committed before any run; salvaged from the run's audit-trail commit `fcaa6813c1`).

> **Provenance note (honest record):** the run's analysis script and this report were lost in a
> worktree-cleanup incident before the agent's push completed (its branch retained only an
> unrelated commit). The pre-reg commit survived in the git object store and is restored
> verbatim; the numbers below are transcribed from the run's structured output (verdict,
> per-cell statistics, gates table), which was captured in full by the orchestrating workflow.
> The analysis script is regenerated at the pre-registered re-adjudication (2026-08-24), which
> re-runs the battery against the live board's first matured 21d cohort anyway.

## Events & construction
- 4,209 fresh buyable-cross events (tier ∈ {T1,T2,T3}, production `tier_stream` completed-bucket basis — leak-free/repaint-free PIT) on the 219-name CA panel, 2021→.
- 1,059 events on the 12 TSX sector ETFs, 2001→ (deep multi-cycle control).
- Outcome: forward 1w/2w/4w excess vs `_GSPTSE`, next-close fill, **differenced against each name's matched base rate** (same name, non-event windows) — the gate's *lift*, not raw drift.
- Basis divergence check vs the live provisional-tail cascade render: 1.4% (10/738), concentrated in T3 (which carries production's provisional flag). The pre-reg's claim that tier_stream reproduces the cascade "EXACTLY" was corrected in-run to this measured rate (retraction stamped).
- T1 measured is a SUPERSET of the live board's T1 (raw-3D-cross fallback vs §7 buy-filter-endorsed master); T2/T3 map 1:1. A §7-master confirmatory pass is a flagged follow-up.

## Results (name panel, base-rate-differenced lift)
| Tier | 1w | 2w | 4w |
|---|---|---|---|
| T1 | −0.15% (t −1.48) | −0.24% (t −1.81, split-stable) | −0.08% (t −0.39) |
| T2 | +0.70% (t 1.34) | +0.90% (t 1.40) | +0.68% (t 0.80) |
| T3 | −0.25% (t −0.53, stable) | **−1.47% (t −2.33, stable, effN 47)** | −0.49% (t −0.38, stable) |
| POOLED | −0.09% (t −1.01) | −0.23% (t −1.87, stable) | −0.06% (t −0.29) |

**Deep-ETF control (2001→, opposite sign):** pooled 4w +0.22% (t 1.32); T2/2w +0.76% (t 2.59, BH-reject); **T3 positive at all horizons** — the two Canadian samples sign-disagree on T1/T3.

## Gates (family `ca_confluence_gate`, program budget via `TrialLedger.with_declared_budget(40, …)`)
- BH-FDR (9-cell family, α=0.10): **zero name-panel cells reject** (best q 0.176 at T3/2w); one ETF cell rejects (T2/2w q 0.087 — context only).
- DSR: **no cell ≥ 0.90** (best name-panel cell ≈ 0.30) → no standalone Canadian alpha from the gate.
- KEEP-BADGE (positive + FDR + HAC≥2 + stable + effN≥30): **none qualify** → T1/T2 = ACCRUE.
- DEMOTE-FLAG (stable-negative + HAC≥2): **T3 only, on the name panel** — but the deep ETF control sign-disagrees, so per the pre-registered conditionality the proposed `CA_BUYABLE_TIERS = BUYABLE_TIERS − {T3}` re-param is **held as a FLAG, not wired**; re-adjudication at the first live board 21d cohort (**2026-08-24**).
- Effective-N (overlap-clustered episodes): name T1 43–139, T2 39–89, T3 33–66; ETF T1 187–402.

## What this does NOT show
No cost/slippage/borrow model (gross, next-close fills). Not causal (joint oversold-reclaim + not-topped selection). Name panel is current-membership survivorship-biased (lift biased *up* — strengthening the null) and spans a single 5y regime; the ETF control is survivorship-clean but a different instrument class. It does not test the gate's *drawdown-avoidance* value (its hygiene role), only the go-up claim.

## Disposition
Gate stays wired on CA as **entry hygiene with "US-calibrated" fine-print** (per masterplan §5.3). T3 demote-flag re-adjudicated 2026-08-24 against the live board ledger. Registry: `ca-confluence-gate-calibration` (accruing, come_back_on 2026-08-24).
