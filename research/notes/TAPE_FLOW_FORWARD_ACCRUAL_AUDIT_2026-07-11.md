# Tape Flow Forward Accrual Audit — 2026-07-11

Authored by Sonnet (W5a builder). Worktree: `claude/flow-leaders-w5a-tape-audit`.

---

## Finding in one sentence

The forward accrual has produced zero data since the July 5 smoke test because the ThetaData Terminal is not started in `daily.yml`, so `reachable()` returns False and the step exits silently on every nightly run.

---

## Evidence trail

### State file (data/tape_flow/_state.json)

```json
{
  "completed": {
    "forward": {
      "SPY": ["2026-07-02"]
    }
  }
}
```

Only SPY 2026-07-02 — the initial smoke test row seeded in PR #1431 (commit `3ba628f45a`). Every subsequent nightly collection commit (`807cfc5b5c` July 10, `4f68f8d950` July 9, `3773a5bf80` July 8, `38dc031b11` July 7) contains zero `data/tape_flow/` changes.

### run_status.json frozen since July 5

`data/run_status.json` entry for `tape_flow_forward`:
```json
{
  "status": "ok", "n_ok": 1, "n_err": 0,
  "elapsed_sec": 32.9, "last_date": "2026-07-02",
  "checked_at": "2026-07-05T12:14:56.350868+00:00",
  "mode": "forward"
}
```

`n_ok: 1` and `checked_at: 2026-07-05` have not changed across any of the July 7–10 daily commits. If the step were running and producing results, `_register_run_status` would update this entry; it does not.

### The reachable() early-exit path

`scripts/build_tape_flow_daily.py` lines 520–523 (pre-fix):

```python
from collectors.thetadata import reachable
if not reachable():
    log.warning("tape_flow: ThetaData terminal not reachable — exiting gracefully")
    sys.exit(0)
```

`sys.exit(0)` is reached BEFORE `_register_run_status` is called. This means a terminal-absent run leaves both `run_status.json` and `data/tape_flow/` unchanged — exactly the observed pattern.

### No terminal-start step in daily.yml

`grep -rn "THETA_API_KEY\|ThetaTerminalv3\|run_theta_terminal\|25503" .github/workflows/` returns only a comment in `daily.yml`:
```
# Requires ThetaData Terminal running on the self-hosted runner (port 25503).
```

There is no step that starts the terminal. `scripts/run_theta_terminal.sh` exists but is not called by any workflow. The terminal was started manually during the July 5 smoke test session and has not been running since.

---

## Secondary bugs (also fixed)

### Bug 2: Budget enforcement broken by ThreadPoolExecutor submit-all

`scripts/build_tape_flow_daily.py` lines 599–648 (pre-fix) submitted ALL work items to the executor upfront via a dict comprehension, then `break`-ed the `as_completed` drain loop when the budget deadline was exceeded. This is ineffective: `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True, cancel_futures=False)`, which waits for ALL submitted futures to complete before the `with` block exits. A budget-stop with 375 tasks submitted and 20 drained would still block for the remaining 355 tasks.

Fix: batch submission (BATCH_SIZE=workers), explicit `f.cancel()` on pending futures, then `executor.shutdown(wait=True, cancel_futures=True)`.

### Bug 3: Forward mode had no budget guard

The `daily.yml` forward step invoked:
```sh
python -m scripts.build_tape_flow_daily --mode forward
```
with no `--budget-minutes`. At 2-concurrent (backfill alive), 375 roots at ~5s/root = ~31 min, leaving insufficient headroom for episodes(30) + etf-history(20) within the 100-min job ceiling. Fix: default budget of 25 min (hard-coded in script, overridable via `--budget-minutes N`).

### Bug 4: No round-robin resume → trailing roots never accrue

With a budget stopping at N roots per night, and no cursor, the same N leading roots (first in `gex_symbols()` list) complete every night while trailing roots never accrue data. Fix: round-robin cursor stored as `state["cursors"]["forward"]`. Each nightly run rotates the work list by the cursor, then advances the cursor by `n_attempted`, so every root reaches the head of the queue eventually.

---

## Runtime math — widened universe at 2-concurrent

Source: T2A_THROUGHPUT_PROBE.md §6a measurements.

| Category | Count | Avg per-root (s) | Serial total (s) |
|---|---|---|---|
| ETF heavy (SPY, QQQ) | 2 | 28 | 56 |
| ETF medium (IWM, DIA, sector ETFs) | 18 | 10 | 180 |
| Heavy single-names (NVDA, TSLA tier) | 50 | 10 | 500 |
| Medium single-names (AMD, META tier) | 100 | 5 | 500 |
| Light single-names (ANET, LITE tier) | 205 | 3 | 615 |
| **Total (375 roots)** | | | **~1,851s serial** |

At **2-concurrent** (backfill alive): ~1,851 / 2 × 1.3 overhead = **~20 min**

At **6-concurrent** (backfill absent): ~1,851 / 6 × 1.3 overhead = **~6.7 min**

With the 25-min default budget:
- At 6-concurrent: all 375 roots complete in ~7 min — full universe per night.
- At 2-concurrent: ~180 roots/night × 2 nights ≈ full universe every 2 nights via round-robin.

The budget is conservative enough that the forward step never starves episodes(30) + etf-history(20) within the 100-min job ceiling:
- Forward: 25 min + Episodes: 30 min + ETF-history: 20 min + Collectors + Finviz: ~35 min = ~110 min
- Actual total stays under 100 min because at 6-concurrent forward completes in ~7 min (not 25), and episodes/etf-history are also faster when backfill is absent.

---

## Fix summary

| File | Change |
|---|---|
| `.github/workflows/daily.yml` | Add "ThetaData Terminal — health-check / start (non-fatal)" step before tape_flow steps; uses `THETA_API_KEY` secret; polls until healthy or 30s timeout; non-fatal if key absent |
| `scripts/build_tape_flow_daily.py` | (1) Default 25-min budget for forward mode; (2) Batch-submit executor with `cancel_futures=True` on budget-stop; (3) Round-robin cursor (`_load_cursor`, `_save_cursor`, `_rotate_work`); (4) `[timing]` ticks at key phases; (5) Outcome summary log line (attempted/succeeded/skipped/failed/elapsed) |
| `tests/test_tape_flow.py` | 9 new tests in `TestRoundRobinCursor`: rotate_work semantics, cursor save/load, distribute-coverage property, forward-default-budget applied, cursor-advances-after-run |

---

## Residual risk (live-nightly only)

1. **THETA_API_KEY secret**: The fix assumes `secrets.THETA_API_KEY` is set in the repo's Actions secrets. If not set, the new step prints a warning and the three tape_flow steps self-skip as before. Operator must confirm the secret is set.

2. **Terminal startup time**: `run_theta_terminal.sh` launches a Java process that takes 5–10s to become healthy. The new step polls 10×3s = 30s max. If startup takes longer (e.g., on a cold JVM), the terminal won't be ready and the tape_flow steps self-skip. Operator may need to extend the poll window or run the terminal as a launchd service.

3. **Backfill concurrency**: If `backfill_thetadata_eod` runs concurrently with the daily collect job (both on mac-builder-2), the 2-concurrent cap will apply, and forward mode will process ~180 roots/night. This is the intended behavior; the round-robin cursor ensures all 375 roots accrue over 2 nights.

4. **Cancel semantics**: `Future.cancel()` only cancels tasks not yet started (queued in the executor's work queue). In-flight tasks at budget-stop will complete. The overshoot is bounded to at most `workers` (2–6) tasks past the deadline.
