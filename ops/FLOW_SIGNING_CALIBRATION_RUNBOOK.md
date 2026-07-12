# Flow-Signing Calibration — Operator Runbook (FC-R10)

## Status

**Tape signing is currently SUSPENDED for production** (RUL-F3.12).
Direction signals require `direction_reliable=true` in `data/options_flow/signing_gate.json`
→ `thetadata_tape` sub-key, which requires `production_ready=true`, which requires ≥5
calibration sessions meeting the diversity requirement below.

The calibration harness is at `scripts/calibrate_flow_signing.py`.

## What calibration does

Uses Databento `tbbo` (trade + consolidated NBBO) samples to compare the tick rule (what
the engine uses, since the massive.com plan has no per-trade NBBO) against the gold-standard
quote rule.  Measures:

- **Per-trade agreement**: tick rule vs quote rule, size-weighted (literature: ~0.77–0.84)
- **Minute net-sign recovery**: whether the tick rule recovers the same NET daily sign per
  contract (the operative metric for our minute-aggregated engine)

Results write to:
- `data/options_flow/signing_gate.json` — machine-readable gate (read by `engine/flow_signing.py`);
  multi-session evidence accumulates into the `thetadata_tape.sessions[]` array.
- `reports/flow-signing-calibration.md` — human-readable Databento report

## Two-step calibration workflow

Each calibration session is a two-step process:

**Step 1 — Run the Databento measurement** (produces the numbers you supply in Step 2):

```bash
# Activate your venv + load secrets
source /etc/macro-api.env

# Run the Databento tbbo measurement for a 20-min window on the target date.
# Day is inferred from --start (first 10 chars).  Reports to stdout + reports/
python -m scripts.calibrate_flow_signing \
  --start "2026-07-10T14:30" \
  --end   "2026-07-10T14:50"
# Read the printed JSON: copy per_trade_agreement, net_sign_recovery, n_trades.
```

**Step 2 — Record the session** (supply the measured numbers from Step 1):

```bash
# Append this session's measurements into signing_gate.json→thetadata_tape.sessions[].
# --roots is comma-separated (default: SPY).
# --agreement, --recovery, --n-trades MUST be supplied (from the Step-1 output above).
# Day is inferred from --start[:10]; --vix-close defaults to Yahoo auto-fetch.
python -m scripts.calibrate_flow_signing \
  --append-session \
  --roots SPY \
  --start "2026-07-10T14:30" \
  --end   "2026-07-10T14:50" \
  --agreement 0.81 \
  --recovery  0.76 \
  --n-trades  12450

# Example for a high-VIX day (NVDA + SPY):
python -m scripts.calibrate_flow_signing \
  --append-session \
  --roots NVDA,SPY \
  --start "2026-04-04T10:00" \
  --end   "2026-04-04T10:20" \
  --agreement 0.78 \
  --recovery  0.73 \
  --n-trades  8900 \
  --vix-close 52.0
```

Note: `--append-session` ONLY records the supplied measurements into
`signing_gate.json → thetadata_tape.sessions[]`; it does NOT re-run
the Databento measurement.  Omitting `--agreement`/`--recovery`/`--n-trades`
records a null session that will never count toward the gate threshold.

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
   - At least 1 high-VIX session (VIX ≥ 20 on that day)
   - At least 1 calm session (VIX < 20 on that day)
   - At least 2 different roots (e.g. SPY + a single name like NVDA)
   - Spread across at least 3 calendar weeks

   Sessions accumulate into `data/options_flow/signing_gate.json → thetadata_tape.sessions[]`.

## Session diversity checklist

Run the following 5 sessions minimum:

| # | Date | Root(s) | VIX regime | Status |
|---|------|---------|------------|--------|
| 1 | TBD | SPY | high-VIX (VIX ≥ 20) | PENDING |
| 2 | TBD | SPY | calm (VIX < 20) | PENDING |
| 3 | TBD | NVDA | any | PENDING |
| 4 | TBD | QQQ | any | PENDING |
| 5 | TBD | (any) | different week from #1–4 | PENDING |

Suggested high-VIX dates (historical): 2025-04-04 (VIX ~52), 2024-08-05 (VIX ~65),
2025-01-27 (VIX ~32), 2026-04-07 (post-tariff).

## Checking session accumulation and gate readiness

```bash
# View full gate (human-readable)
python -c "import json; print(json.dumps(json.load(open('data/options_flow/signing_gate.json')), indent=2))"

# Quick session summary (reads from thetadata_tape.sessions[] array):
python -c "
import json, pathlib
gate = json.load(pathlib.Path('data/options_flow/signing_gate.json').open())
td = gate.get('thetadata_tape', {})
sessions = td.get('sessions', [])
print(f'{len(sessions)} sessions accumulated')
for s in sessions:
    print(f'  {s.get(\"date\")} roots={s.get(\"roots\")} '
          f'agreement={s.get(\"per_trade_agreement\")} '
          f'recovery={s.get(\"net_sign_recovery\")} '
          f'vix={s.get(\"vix_close\")}')
print()
# Gate readiness keys (all nested under thetadata_tape):
print(f'  sessions_n       : {td.get(\"sessions_n\")}')
print(f'  sessions_passed  : {td.get(\"sessions_passed\")}')
print(f'  bar_agreement    : {td.get(\"bar_agreement\")}')
print(f'  bar_recovery     : {td.get(\"bar_recovery\")}')
print(f'  production_ready : {td.get(\"production_ready\")}')
"

# Gate is ready for direction promotion when ALL of:
#   thetadata_tape.production_ready = true
#   thetadata_tape.sessions_n >= 5
#   thetadata_tape.sessions_passed >= required threshold
#   (bars: bar_agreement and bar_recovery shown above)
```

## Promoting direction signing

When `signing_gate.json → thetadata_tape.production_ready = true`:
1. Open a PR changing `flow_signing.direction_reliable()` to check the gate file.
2. The PR must include the calibration report (`reports/flow-signing-calibration.md`).
3. Fable adjudication required before merge (RUL-F3.12 gate).
4. After merge: the `~` / "direction approx" idiom remains on ALL copy until
   the Fable promotion ruling explicitly removes it from specific surfaces.

## DO NOT

- Run calibration against the live Theta Terminal production poller.
- Invoke `calibrate_flow_signing.py` without `--append-session` more than once
  per date (the Databento report overwrites; sessions accumulate safely with `--append-session`).
- Run `--append-session` without `--agreement`/`--recovery`/`--n-trades` — you will record
  a null session that never counts toward the gate threshold.
- Skip the session-diversity requirement — 5 SPY sessions on the same day
  do NOT satisfy RUL-F3.12.

## Timing

Clock set at 2026-07-18 for first armed calibration session.  ≥5 sessions
needed before direction promotion is eligible (no earlier than 2026-08-15 per
the masterplan clock).
