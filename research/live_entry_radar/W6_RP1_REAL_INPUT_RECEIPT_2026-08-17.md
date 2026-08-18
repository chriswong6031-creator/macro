# W6 RP1 — genuine real-input pre-merge receipt

**Status:** ACCRUING / RESEARCH PRIORITY. Not production commissioning.
**Policy:** `research/live_entry_radar/W6_RP1_POLICY.md` (`RP1`, post-Sol-review correction)
**Schema:** `mastermind.research_priority.v1`
**This is not** `W6_RP1_RECEIPT_2026-08-17.md` (that file is the W4 **synthetic**
LivePack live-seam proof). Sol required a receipt from the real Radar evaluator
on real store frames. This is that receipt.
**No episodes were planted.** An empty board is the honest result of this
snapshot, not a low score.

## What was run

1. Materialized `data/stocks/{AAPL,NVDA,TSLA,NFLX,INTC,PFE}.parquet` from
   `origin/main` via `git show` into `/tmp/w6-rp1-real/` (sparse-safe; no write
   into omitted `data/`). Store tip **2026-08-13** on every name. Columns
   `close/high/low/volume`.
2. `live_pack.build_pack` with that injected `store_reader`, `as_of=2026-08-13`,
   `built_at=2026-08-13T22:00:00Z`. Next session **2026-08-14**.
   `pack_hash=6b9c818ba764de71`. `substrate_missing` empty. Pack `fresh: true`.
3. `live_eval.run_pass` on that pack with agreeing reconstructed quotes
   (`prevClose = as_of_close`, print = `0.97 × as_of_close`, age 120s) at
   32 minutes after the 2026-08-14 open. Same quote shape the W4 live harness
   uses. **Not** a captured RTH tape; the **daily substrate is real**.
4. Ran the pass twice with independent ledgers/state dirs.
   `json.dumps(board, sort_keys=True)` equal.

SPY is not in `origin/main:data/stocks/`, so `rs_60_vs_bench` would be
unavailable on any rankable row (policy: never a probe-set median).

G0/C5 nightly lanes stayed `slice_store_unconfigured` — those experts consume
Terminal artifacts, not daily OHLC. They were not fabricated.

## Pack provenance (real frames)

| ticker | K(conf) | close | bars | freshness | c1_arm_price | c2a_cross_price |
|---|---:|---:|---:|---|---|---|
| AAPL | 5.41 | 305.26 | 11,509 | confirmed | **320.0362** (solvable; in-washout) | 304.4716 |
| INTC | 93.61 | 104.56 | 11,697 | confirmed | `never_true` | 98.2008 |
| NFLX | 80.48 | 78.24 | 6,095 | confirmed | `never_true` | 77.1200 |
| NVDA | 87.89 | 225.30 | 6,932 | confirmed | `never_true` | 217.5955 |
| PFE | 56.42 | 26.80 | 13,663 | confirmed | `never_true` | 27.7676 |
| TSLA | 96.18 | 339.96 | 4,056 | confirmed | `never_true` | `never_true` |

Matches the 2026-08-13 W4 real-data smoke on the same blobs. AAPL remains the
only in-washout name in this six-name cut.

## Evaluator result

| field | value |
|---|---|
| payload `schema` | live entry_radar payload |
| session | 2026-08-14 |
| health.state | `degraded` |
| health.reasons | `reading_null:6/6` |
| basis | audited 6 / mismatched 0 |
| quote coverage | 6/6, stale_n=0 |
| pack fresh | true |
| `research_priority.status` | ACCRUING |
| `research_priority.policy_version` | RP1 |
| `research_priority.population_n` | **0** |
| `research_priority.episodes` | **[]** |
| twice-equal | true |
| authority | all `can_*` false |
| Prophet paths | untouched |

Per-name (no dark, no basis mismatch):

| ticker | name state | reasons | observations | developing episode |
|---|---|---|---:|---|
| AAPL | evaluated | `reading_unavailable` | 6 | none |
| INTC | evaluated | `reading_unavailable` | 6 | none |
| NFLX | evaluated | `reading_unavailable` | 6 | none |
| NVDA | evaluated | `reading_unavailable` | 6 | none |
| PFE | evaluated | `reading_unavailable` | 6 | none |
| TSLA | evaluated | `reading_unavailable` | 6 | none |

A quote-only +32m pass does not produce a finite live StochRSI reading, so C1
does not arm even on in-washout AAPL. That is the same W4 live law already
recorded on the synthetic pack (`quote-only run_pass does not arm C1`; the
recovery-tape seam is a different proof, already in
`W6_RP1_RECEIPT_2026-08-17.md`). Ranked/abstained RP1 rows are therefore empty
because **no developing episode existed on this real snapshot**. Missing ≠ 0;
empty ≠ a 17/100.

## Ranked / abstained rows

None. Board:

```json
{
  "schema": "mastermind.research_priority.v1",
  "policy_version": "RP1",
  "status": "ACCRUING",
  "population_n": 0,
  "episodes": [],
  "cycle_state": "degraded"
}
```

## What this discharges

The pre-merge **real-input** gate: RP1 is wired at the live projection seam and
was computed against a pack frozen from real daily store frames through
`build_pack` + `run_pass`. It does **not** discharge VPS/RTH commissioning
(`ENTRY_RADAR_LIVE_ENABLE`, a session that actually develops episodes).

## Firewalls

No W5 table was opened to choose or retune the formula. No Prophet path changed.
Durable ledger `research_priority` remains null (not exercised on this dry
pass beyond the payload object).
