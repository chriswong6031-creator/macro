# Flow-Signing Calibration — Operator Runbook (FC-R10)

## Status

**Tape signing is currently SUSPENDED for production** (RUL-F3.12).
Direction signals require `direction_reliable=true` in `data/options_flow/signing_gate.json`,
which requires `production_ready=true`, which requires ≥5 calibration sessions meeting the
diversity requirement below.

The calibration harness is at `scripts/calibrate_flow_signing.py`.

## What calibration does

Uses Databento `tbbo` (trade + consolidated NBBO) samples to compare the tick rule (what
the engine uses, since the massive.com plan has no per-trade NBBO) against the gold-standard
quote rule.  Measures:

- **Per-trade agreement**: tick rule vs quote rule, size-weighted (literature: ~0.77–0.84)
- **Minute net-sign recovery**: whether the tick rule recovers the same NET daily sign per
  contract (the operative metric for our minute-aggregated engine)

Results write to:
- `data/options_flow/signing_gate.json` — machine-readable gate (read by `engine/flow_signing.py`)
- `reports/flow-signing-calibration.md` — human-readable report

## Prerequisites

1. **Databento account** with `DATABENTO_API_KEY` set in environment.  The calibration
   script uses a short (20-min) `tbbo` window for ONE name by default — cost is minimal.
   A cached raw pull at `data/options_flow/_dbento_sample.parquet` avoids re-charging.

2. **Install the Databento client** (not in requirements.txt — only needed for calibration):
   ```bash
   pip install databento
   ```

3. **Session diversity requirement** (RUL-F3.12, binding):
   ≥5 sessions must be calibrated, spanning:
   - At least 1 high-VIX session (VIX > 25 on that day)
   - At least 1 calm session (VIX < 15 on that day)
   - At least 2 different roots (e.g. SPY + a single name like NVDA)
   - Spread across at least 3 calendar weeks

   The `--append-session` mode (see below) accumulates sessions into
   `data/options_flow/tape_signing_sessions.jsonl`.

## Running a calibration session

```bash
# Activate your venv + load secrets
source /etc/macro-api.env

# Single session for SPY on a specific date + window
python -m scripts.calibrate_flow_signing \
  --append-session \
  --symbols SPY \
  --date 2026-07-10 \
  --window "2026-07-10T14:30" "2026-07-10T14:50"

# Single session for NVDA on a high-VIX day
python -m scripts.calibrate_flow_signing \
  --append-session \
  --symbols NVDA \
  --date 2026-04-04 \
  --window "2026-04-04T10:00" "2026-04-04T10:20"

# Check current session count and diversity
python -c "
import json, pathlib
sessions = [json.loads(l) for l in
    pathlib.Path('data/options_flow/tape_signing_sessions.jsonl').open()
    if l.strip()]
print(f'{len(sessions)} sessions accumulated')
for s in sessions:
    print(f'  {s.get(\"date\")} {s.get(\"symbol\")} vix={s.get(\"vix_approx\")}')
"
```

## Session diversity checklist

Run the following 5 sessions minimum:

| # | Date | Symbol | VIX regime | Status |
|---|------|--------|------------|--------|
| 1 | TBD | SPY | high-VIX (VIX > 25) | PENDING |
| 2 | TBD | SPY | calm (VIX < 15) | PENDING |
| 3 | TBD | NVDA | any | PENDING |
| 4 | TBD | QQQ | any | PENDING |
| 5 | TBD | (any) | different week from #1–4 | PENDING |

Suggested high-VIX dates (historical): 2025-04-04 (VIX ~52), 2024-08-05 (VIX ~65),
2025-01-27 (VIX ~32), 2026-04-07 (post-tariff).

## Reviewing the gate

```bash
# View current gate
python -c "import json; print(json.dumps(json.load(open('data/options_flow/signing_gate.json')), indent=2))"

# Gate is ready for direction promotion when:
#   production_ready = true
#   n_sessions >= 5
#   minute_agreement >= 0.70 (70% minute net-sign recovery)
```

## Promoting direction signing

When `production_ready=true` appears in `signing_gate.json`:
1. Open a PR changing `flow_signing.direction_reliable()` to check the gate file.
2. The PR must include the calibration report (`reports/flow-signing-calibration.md`).
3. Fable adjudication required before merge (RUL-F3.12 gate).
4. After merge: the `~` / "direction approx" idiom remains on ALL copy until
   the Fable promotion ruling explicitly removes it from specific surfaces.

## DO NOT

- Run calibration against the live Theta Terminal production poller.
- Invoke `calibrate_flow_signing.py` without `--append-session` more than once
  per date (the report overwrites; sessions accumulate safely with `--append-session`).
- Skip the session-diversity requirement — 5 SPY sessions on the same day
  do NOT satisfy RUL-F3.12.

## Timing

Clock set at 2026-07-18 for first armed calibration session.  ≥5 sessions
needed before direction promotion is eligible (no earlier than 2026-08-15 per
the masterplan clock).
