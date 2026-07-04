# S7 RS-Repair Phase-0 (+ triple-lock test)

Pre-registered phase-0 for species **S7 Relative-Strength-Before-Price** (two-sided),
brought forward from W3 after triage of the external Codex bottom backtest
(`research/bottom_signal_backtest/`). Read in order:

1. [SPEC.md](SPEC.md) — frozen pre-registration (panels, fires, features, hypotheses, protocol)
2. [REPORT.md](REPORT.md) — dev results, frozen holdout predictions, holdout outcome, verdicts

**Outcome (2026-07-04):** S7's registered form (RS slope vs within-cohort rank) passed dev
with CIs excluding 0 and met the rs_low promotion bar, attenuated on the 2025-26 holdout
(signs held, underpowered) → **stays phase0**, re-read after W0.4. The Codex vs-SPY RS
leg was **refuted** (holdout-significantly worse) and the triple-lock conjunction is
**NO-GO** (worse than cohort-alone on holdout). Registry updated: `data/species/registry.json` S7.

## Reproduce

```bash
# full run (data auto-resolves to the main checkout's data/; needs massive_stock_day complete)
python3 research/species/s7_rs_repair_phase0/run_all.py --panel both --full --workers 4
# dev tables
python3 research/species/s7_rs_repair_phase0/analyze.py --panel both
# holdout (single pass — do not run before predictions are frozen in REPORT.md)
python3 research/species/s7_rs_repair_phase0/analyze.py --panel p1 --holdout
```

Summary CSVs are committed under `results/dev/` and `results/holdout/`; per-fire
parquets are regenerable and gitignored.
