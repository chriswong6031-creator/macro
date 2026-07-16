# ThetaData EOD Backfill — Ops Runbook

_Maintained under: research/THETADATA_OPS_RUNBOOK.md_
_Authoritative plan of record: research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md_

---

## §1 In plain English

The ThetaData EOD backfill is a long-running Python process that pulls historical
options chains (EOD snapshots + greeks) from the ThetaTerminal v3 REST API and writes
them to `data/thetadata_eod/` in the ops worktree (`/Users/chriswong/theta-ops-wt`).
It is idempotent: a state file (`_backfill_state.json`) records every completed
root+date pair, so restarting after any interruption resumes without re-pulling.

A launchd keepalive (`com.macro.thetadata-backfill.plist`) ensures the job
auto-resumes after Mac reboots and auto-exits if an instance is already running.

---

## §2 Resume-after-reboot procedure

After a Mac reboot, the launchd keepalive (§3) should auto-resume.  If it does not,
or if you need to manually confirm the job:

**Step 1 — Confirm ThetaTerminal is running.**

```bash
pgrep -fl "ThetaTerminalv3\|theta"
```

If it is not running, start it:

```bash
# Preferred: the repo launcher (handles Java 21, key-via-env, health hints)
bash "/Users/chriswong/Documents/Cluade/Macro Dashboard/scripts/run_theta_terminal.sh"

# Manual equivalent — key via environment, NEVER as --api-key argv
# (argv is plaintext-readable by any local process via `ps`):
cd /Users/chriswong/theta && \
    THETADATA_API_KEY="$THETA_API_KEY" java -jar ThetaTerminalv3.jar &
# Allow 30–60 seconds for the terminal to become reachable
# THETA_API_KEY must be set in the operator's shell profile or fetched from
# the local secret store (e.g. `export THETA_API_KEY=$(op read "op://Private/ThetaData/api_key")`).
# Never commit the literal key to git.
```

**Step 2 — Check whether the backfill is already running.**

```bash
pgrep -fl "backfill_thetadata_eod"
```

If output shows a PID, the job is running — do nothing.

**Step 3 — If the job is NOT running, resume manually.**

```bash
cd /Users/chriswong/theta-ops-wt
# ETF pass (22 named roots) → bare universe pass (~360 roots)
python -m scripts.backfill_thetadata_eod \
    --roots SPY,QQQ,IWM,DIA,XLK,XLF,XLE,XLI,XLU,XLV,XLY,XLP,XLB,XLC,XLRE,SMH,SOXX,XBI,KRE,ARKK,SPX,SPXW \
  && python -m scripts.backfill_thetadata_eod \
  >> backfill.log 2>&1 &
```

Both passes are **idempotent** — `_backfill_state.json` tracks every completed
root+date pair.  Re-running on already-completed roots is safe and fast (skips).

**Step 4 — Confirm it is running and check progress.**

```bash
pgrep -fl "backfill_thetadata_eod"   # should show a PID
tail -20 /Users/chriswong/theta-ops-wt/backfill.log
```

---

## §3 Keepalive: install, verify, uninstall

The plist and wrapper script ship under `scripts/launchd/` in the repo.
After the PR merges to main, run the install commands once.

### Install

```bash
# Step 1: copy the plist to LaunchAgents (do NOT commit ~/Library to git)
cp "$(git -C "/Users/chriswong/Documents/Cluade/Macro Dashboard" rev-parse --show-toplevel)/scripts/launchd/com.macro.thetadata-backfill.plist" \
    ~/Library/LaunchAgents/

# Step 2: load it
launchctl load ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist

# Step 3: confirm the job is registered
launchctl list com.macro.thetadata-backfill
```

Expected output from Step 3 should show the label with `"OnDemand" = false`.

### Verify guard exits correctly while a backfill is running

While `backfill_thetadata_eod` is live:

```bash
bash "/Users/chriswong/Documents/Cluade/Macro Dashboard/scripts/launchd/theta_backfill_keepalive.sh"
# Should exit immediately (guard path)
tail -5 /Users/chriswong/theta-ops-wt/backfill.log
# Should show: "... backfill_thetadata_eod already running — exiting (no duplicate)"
```

The live backfill process must remain running (check with `pgrep -fl backfill_thetadata_eod`).

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
rm ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
```

---

## §4 State-file semantics

| File | Location (ops worktree) | Semantics |
|------|------------------------|-----------|
| `_backfill_state.json` | `data/thetadata_eod/` | One entry per (root, date) pair, written after a successful pull. Drives idempotency: completed pairs are skipped. Never delete; edit only with `backfill_thetadata_eod.py --reset-root <root>` if a root needs re-pulling. |
| `_manifest.json` | `data/thetadata_eod/` | Written by the backfill script at completion of each root. Gate R8 (roadmap): no gate harness reads the store until this marks the universe pass complete. |
| `backfill.log` | `theta-ops-wt/` | Append-only; records progress, errors, and keepalive guard events. Never truncate while a backfill is running. |

---

## §5 Window law

These limits come from the ThetaData v3 API and the ops constitution:

| Rule | Limit | Rationale |
|------|-------|-----------|
| **Max window per request** | <= 7 calendar days | Larger windows time out or stall the terminal; 1-day windows are safest for greeks-bearing queries |
| **Greeks window** | 1 day (single date) | The per-contract greeks endpoint stalls on multi-day windows; use daily loops |
| **Concurrent requests** | <= 8 | Hard cap; the terminal queues but stalls beyond 8 concurrent connections; the backfill uses sequential pulls to stay safe |
| **Rate note** | ~210 s/root-year (ETF); single-name rate unmeasured | ETF rate observed empirically (346 s for greeks-bearing SPY years); estimate single-name rate before committing to full history |

---

## §6 Concurrency cap: 8-concurrent ceiling

The ThetaTerminal v3 window-stall law: exceeding 8 concurrent connections causes
the terminal to stall and requires a restart.  The backfill script uses up to
6 concurrent windows (ThreadPoolExecutor max_workers=6), staying safely under the
8-concurrent terminal ceiling.  If you run manual `trade_quote` or `bulk_eod` calls
concurrently, add them to the count:

- Backfill (up to 6 concurrent pulls) + manual calls <= 8 total.
- Never run multiple backfill instances simultaneously (the keepalive guard prevents this).

---

## §7 R2 publish plan

Heavy stores (`data/thetadata_eod/`) ship on Cloudflare R2, not git, per A4/A8.

**When to publish:** after the universe pass marks `_manifest.json` complete.
**How:** `scripts/r2_publish.py --prefix thetadata_eod/` (or the bulk publish script
used for other stores — follow the pattern in `data/massive_r2_publish.log`).
**Audit tripwire:** P0.7 registers `thetadata_eod` in `run_status.json`; a missing
or stale manifest entry blocks the gate harness (R8).

See `research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md §3` P0.2 for the full plan.

---

## §8 Multi-session signing extension (P0.4)

The initial signing calibration was ratified on 2026-07-04 (single 20-min window,
single root SPY, 15 contracts, n=16,366; agreement=0.8848, recovery=0.80).

Before the UI direction tone is un-softened, the multi-session extension requires:
- >= 5 sessions, each with per_trade_agreement >= 0.75 AND net_sign_recovery >= 0.75
- Sessions must span at least one high-VIX day (VIX >= 20) AND one calm day (VIX < 20)
- Sessions must span >= 2 distinct roots

After each calibration run, append the session record:

```bash
python -m scripts.calibrate_flow_signing \
    --append-session \
    --start 2026-MM-DDTHH:MM \
    --end   2026-MM-DDTHH:MM \
    --roots SPY,QQQ \
    --agreement 0.88 \
    --recovery  0.80 \
    --n-trades  16366
```

The script prints a summary block showing the running count and whether the pass
threshold is met.  **Direction_reliable is NOT auto-flipped** — adjudication stays
with Fable/human after the threshold is confirmed.

---

## §9 Troubleshooting

| Symptom | First check | Fix |
|---------|-------------|-----|
| `backfill.log` shows `rows=0` for every date | Terminal not reachable | Restart ThetaTerminal (§2 Step 1); wait 30–60 s |
| Backfill stalls at same root for > 30 min | Terminal window-stall | `kill <PID>`; restart terminal; resume (§2 Step 3) |
| Keepalive fires but backfill immediately dies | `backfill.log` tail | Python path not in launchd PATH — verify the plist LaunchAgents entry; use full Python path in wrapper if needed |
| `LastExitStatus` in `launchctl list` = 32512 | Script not executable | `chmod +x .../theta_backfill_keepalive.sh` |
| `_manifest.json` missing after ETF pass | Backfill didn't finish cleanly | Check log; resume — the script writes the manifest at completion |
