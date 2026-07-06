# Oracle Reversion Promotion — LIVE floor (PRE-REGISTRATION)

**Date frozen:** 2026-07-05 · **Status:** pre-registered BEFORE any live forward
evidence accrues. Thresholds FROZEN; changing them after seeing live results is
p-hacking. Governs the reversion promotion track (`research/ORACLE_REVERSION_PROMOTION_TRACK_DESIGN.md`).

## Why a separate LIVE floor

A 6-leg reversion-gauntlet PASS (`ORACLE_REVERSION_GATE_PREREG.md`, incl. Amendment 1)
earns a compound a place in the **library** and the **display** surface — nothing more.
The money path (ranking / attention) requires an **earned live track record**, gated by
the SAME mechanism the Neural Web already uses for `can_force` and the cortex:
`engine/neuralweb/constitution.py::grant_authority`. This doc freezes that live floor and
the ledger schema it reads, so neither can be tuned to a live result.

## Frozen forward-ledger schema (what P0 records)

One row per (compound, node, fire_date), append-only, nightly-single-writer at
`data/oracle/reversion_forward/<compound_id>.jsonl`:
```
compound_id, node, tier(s|m), fire_date, exec_date(=next session), exit_date(=fire+21 sessions),
regime(risk_on|risk_off at fire), ret_exit, mfe, mae, matured(bool)
```
- Grading uses `_per_entry_rows` from `scripts/oracle_reversion_screen.py` VERBATIM (live == backtest grading).
- **PIT law:** a row is graded (matured=true, ret_exit/mfe/mae filled) ONLY once `exit_date <= today`.
  No look-ahead: exec at fire+1, exit at fire+21, regime stamped at fire. Ungraded rows carry nulls.
- Nightly is the sole writer; intraday lanes discard (house law).

## Frozen LIVE promotion floor

Feed `grant_authority(hits, n, base_rate)`:
- **n** = matured live fires for the compound. For **single-regime** signals, count only
  operating-regime fires (bear-tape accrues in risk-off only — its clock is regime-gated).
- **hits** = matured fires with `ret_exit > 0` (the WR definition).
- **base_rate** = the UNCONDITIONAL trailing 21-session win-rate on the same universe
  (buy-anytime rate, computed PIT as of each grading). The gate therefore measures live
  entry-timing LIFT over random — the live analog of the backtest placebo.

**L2 → L3 (Display → Confirmer):** grant iff
`wilson_lower(hits, n, z=1.645) / base_rate > 1.25`  AND  `n >= 25`.
(1.25 and z=1.645 are the constitution's own `_LIFT_THRESHOLD` and Article-3 bound — reused, not forked. n≥25 matches the cortex A2 / can_force earn-in floors.)

**L3 → L4 (Confirmer → Scored):** additionally `n >= 60` AND `asym_live >= 1.3`
(a live haircut from the 1.5 backtest bar, for live noise + transaction costs).

**Lapse (Article 3):** de-escalate to Display if no fire in 90 sessions OR live `lift_lb`
falls back to `<= 1.25` at the current n. De-escalation MAY be triggered by an LLM/cortex;
escalation NEVER may (Article 1).

**Hard precondition:** only compounds with a `reversion` block (backtest gauntlet PASS)
enter the ladder at all.

## Adjudication + governance

The promotion scan (`scripts/oracle_reversion_promotion_scan.py`, P2) applies this floor to
the live ledger and QUEUES candidates for operator/Fable adjudication — it NEVER auto-promotes
(mirrors `oracle_promotion_scan.py`). Every proposed tier transition emits a
`data/neuralweb/governance.jsonl` event (Article-2 event). The floor above is display-only until
a human ratifies each promotion.

## Open ruling (flagged for the operator at P3, NOT frozen here)

Grant authority at the **cluster** level (dollar-relief, V-bottom, oil, rs-laggard — see the
independence map, ~7 bets not 10) rather than per-signal, so correlated siblings do not
double-count on the money path. Deferred to the P3 adjudication.
