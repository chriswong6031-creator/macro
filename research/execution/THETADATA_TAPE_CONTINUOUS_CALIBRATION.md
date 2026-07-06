# ThetaData Tape — Continuous Calibration Plan

**Authority:** RUL-F3.12 (`research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`)
**Session log:** `data/options_flow/tape_signing_sessions.jsonl` (append-only JSONL)
**Gate:** `data/options_flow/signing_gate.json` → `thetadata_tape` sub-key only
**Harness:** `scripts/calibrate_thetadata_tape_sessions.py`
**Status as of 2026-07-06:** 3 sessions measured, all FAIL (suspend active — see §5)

---

> **In plain English:** We measured whether our options trade signing method works across
> different market conditions. The first session (June 2026, SPY calls only, narrow window)
> passed with 88% agreement. Expanding to multiple roots, both calls and puts, and stress
> days, the agreement drops to 67–72% — below the 75% bar. This is an honest null: the
> tape method is condition-dependent. The suspend mechanism is correctly active. Bar-source
> signing (minute-tick rule) remains permanently disabled regardless. This document is the
> standing ops reference for how to run future sessions and what the evidence bar requires.

---

## §1 What counts as a "session"

A session is one measured window: a date × time-range × set of roots × contract set.

Required session attributes recorded in the JSONL log:
- `date` — YYYY-MM-DD of the historical day
- `window_start` / `window_end` — ET time window (e.g. 14:30–14:50)
- `roots` — list of underlying roots measured (e.g. ["SPY", "QQQ", "NVDA"])
- `n_trades` — total trade count after window filter
- `n_contracts` — number of contracts with at least one trade in window
- `per_trade_agreement` — fraction of trades where Lee-Ready quote rule and tick rule agree
- `net_sign_recovery` — fraction of contracts where minute-net-sign direction matches quote rule
- `vix_close` — VIX closing level on session date (from `data/fred/VIXCLS.parquet`)
- `vix_regime` — "high" (VIX>=20) or "calm" (VIX<20)
- `moneyness_buckets` — set of moneyness labels seen across contracts
- `expiries_covered` — distinct expiration dates in the session
- `agreement_ok` / `recovery_ok` / `pass` — whether each bar was met

A session `pass=True` requires BOTH `per_trade_agreement >= 0.75` AND
`net_sign_recovery >= 0.75`, with `n_trades >= 5,000`.

A session `status` of `no_data` or `insufficient_n` does not count toward the pass total
and does not trigger suspend (the session was not meaningfully measured).

---

## §2 The >=5-session / conditions bar (production_ready)

`production_ready=True` in `signing_gate.json`'s `thetadata_tape` sub-key requires:

1. **≥5 measured sessions** with `pass=True` (agreement AND recovery both ≥0.75)
2. **At least one high-VIX session** (VIX>=20 on session date)
3. **At least one calm session** (VIX<20 on session date)
4. **At least 2 distinct roots** measured across all sessions (e.g. SPY + QQQ)
5. **Zero real failures** — no session with `status=ok` and `pass=False`

`production_ready=True` does NOT automatically flip `direction_reliable=True` in the root
gate. That flip requires explicit Fable/human adjudication (ratified separately, per §7.1
of LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md).

---

## §3 Suspend-on-fail semantics

ANY measured session (`status=ok`) with `per_trade_agreement < 0.75` sets:

```json
"direction_reliable_tape": false,
"suspend_reason": "N session(s) failed agreement bar ..."
```

Suspension is not auto-cleared. To clear:

1. Investigate the failing session — is the failure explained by measurement conditions
   (e.g. illiquid contracts, very wide spreads, truncated data)?
2. If spurious: remove the session record manually from the JSONL and re-run `update_gate`.
3. If real: investigate whether the tape methodology requires revision before re-opening.
4. Fable adjudication required to re-enable.

---

## §4 Agreement methodology note

The metric labelled `per_trade_agreement` is computed between:
- **Quote rule (truth):** Lee-Ready classification using ThetaData NBBO at trade execution
- **Tick rule:** sign of price change from previous trade

This is the same methodology as the ratified #1292 session. **Difference from the
initial calibration:** the initial session used Databento as an independent source for
NBBO; these sessions use ThetaData's own NBBO. There is no cross-provider oracle.

The metric is labelled `quote_rule_self_consistency` in every session record. This does
NOT invalidate the measurement — the NBBO at execution is ThetaData's own timestamp-matched
quote, which is the correct reference for tape signing. It means: we cannot separate
"ThetaData NBBO accuracy" from "signing methodology accuracy" in a single-source test.

---

## §5 Measured sessions (as of 2026-07-06)

**SUSPEND ACTIVE** — all 3 measured sessions fail the 0.75 agreement bar.

| # | Date | Window | Roots | n_trades | Agreement | NSR | VIX | Pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 2025-04-07 | 14:30–14:50 | SPY, QQQ | 8,225 | 0.6715 | 0.619 | 46.98 (high) | FAIL |
| 2 | 2024-12-16 | 14:30–14:50 | SPY, QQQ | 10,157 | 0.6996 | 0.500 | 14.69 (calm) | FAIL |
| 3 | 2025-01-14 | 14:30–14:50 | SPY, QQQ, NVDA | 12,737 | 0.7197 | 0.677 | 18.71 (calm) | FAIL |

**Comparison with ratified single-session (#1292):**

| Session | Date | Window | Roots | Rights | n_trades | Agreement | NSR | Pass |
|---|---|---|---|---|---|---|---|---|
| Ratified | 2026-06-18 | 14:30–14:50 | SPY only | Calls only, near-ATM, 3 exp | 16,366 | **0.8848** | **0.800** | PASS |
| Multi-session (this harness) | 2024–2025 dates | 14:30–14:50 | SPY+QQQ±NVDA | Calls+Puts, ATM band, 3 exp | 8–13k | 0.67–0.72 | 0.50–0.68 | FAIL |

**Interpretation (print null, do not hide):**

The multi-session harness includes PUT contracts and multiple roots in each session.
The ratified session was SPY calls only. The drop in agreement (0.88→0.67–0.72) is
observed but the confounding factor (calls vs. calls+puts, narrow vs. broader universe)
is not isolated. Known relevant factor: put options trade differently from calls
(dealer hedge direction differs; tick-rule sign may systematically disagree for put
sellers). This requires investigation before producing a corrected assessment.

Three plausible explanations, not yet discriminated:
1. **Puts degrade agreement** — tick rule on put trades has systematically reversed sign
   vs. quote rule (a known issue in the literature for OTM puts)
2. **Multi-root pooling dilutes** — lower-volume roots have higher bid-ask bounce, which
   increases zero-tick noise and tick-rule errors
3. **Date/regime sensitivity** — the ratified session was a specific day (post-expiry
   morning, near market open) with unusually orderly flow; other windows may differ

**Next steps (operator):**
- Run a calls-only session on a non-ratified date to isolate puts vs. calls
- Run SPY-only session on a new date to isolate multi-root from single-root
- If calls-only single-root passes: the puts and/or multi-root are the issue; gate
  conditions coverage definition may need revision
- Report findings to Fable before clearing suspend

---

## §6 How to run the harness

**Prerequisites:**
- ThetaTerminal v3 running at `http://127.0.0.1:25503` with a valid API key
- `python3` with `pandas`, `requests` installed (no venv required)
- `data/fred/VIXCLS.parquet` on disk for VIX regime classification

**Check terminal reachability (window-stall law: check before running, don't hang):**
```bash
curl -s --connect-timeout 5 http://127.0.0.1:25503/v3/option/list/symbols | head -2
```

**Dry-run (no network, synthetic fixture data):**
```bash
python -m scripts.calibrate_thetadata_tape_sessions --dry-run
```

**Single session (requires terminal):**
```bash
python -m scripts.calibrate_thetadata_tape_sessions \
    --date 2025-04-07 --start 14:30 --end 14:50 \
    --roots SPY,QQQ,NVDA
```

**Run the pre-defined session plan (5 sessions covering required conditions):**
```bash
python -m scripts.calibrate_thetadata_tape_sessions --run-plan
```

**Show current session log summary (no new session):**
```bash
python -m scripts.calibrate_thetadata_tape_sessions --summary
```

**What each run does:**
1. Resolves ATM±10% contracts for each root from the day's EOD chain
2. Pulls `trade_quote` for each contract (sequential; respects v3 8-concurrent ceiling)
3. Filters to the ET time window
4. Computes `compare_trade_signs` and `minute_sign_recovery` from `engine.flow_signing`
5. Appends one JSONL record to `data/options_flow/tape_signing_sessions.jsonl`
6. Updates ONLY `thetadata_tape` sub-key of `signing_gate.json`
7. Prints a summary of all sessions

**NEVER:**
- Touch root-level keys in `signing_gate.json` (`direction_reliable`, `scored`, etc.)
- Rewrite past records in the JSONL
- Flip `direction_reliable_tape=True` without Fable/human adjudication
- Run during market hours on a production machine (historical sessions only; no live data path)

---

## §7 Root gate authority — PERMANENT

Root `direction_reliable` in `signing_gate.json` stays `false` for bar sources
**permanently**. This is a verdict about minute-bar tick-rule signing (agreement≈0.777,
recovery≈0.41 on Databento truth), which does not change based on tape sessions.

The `thetadata_tape` sub-key is a **separate, source-specific authority** for tape-sourced
features only. `direction_reliable_tape=True` (once the suspend is cleared and sessions
meet the production bar) means: options features built from `trade+NBBO` tape records
are reliable for direction. It does NOT grant direction authority to bar-sourced features.

Mixed-source aggregates (bar + tape) remain forbidden per LIVE_ORDER_FLOW §8.2.

---

## §8 Session plan (target conditions)

| Plan entry | Date | Roots | VIX context | Status |
|---|---|---|---|---|
| High-VIX + dual-root | 2025-04-07 | SPY, QQQ | 46.98 (tariff shock) | MEASURED (FAIL) |
| High-VIX + single-name | 2025-04-08 | SPY, QQQ, NVDA | 52.33 | Not run |
| Calm + dual-root | 2024-12-16 | SPY, QQQ | 14.69 | MEASURED (FAIL) |
| Calm + single-name | 2025-01-14 | SPY, QQQ, NVDA | 18.71 | MEASURED (FAIL) |
| Calm mid | 2025-02-21 | SPY, QQQ | ~18 | Not run |

Additional diagnostic sessions needed (see §5):
- SPY calls-only on a new date (isolate rights contamination)
- SPY-only on a new date (isolate multi-root contamination)
