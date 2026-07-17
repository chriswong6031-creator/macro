# U-CHAIN Chain-Snapshot Poller — Runbook

## Architecture overview

The chain-snapshot poller (`scripts/chain_snapshot_poller.py`) runs on the Mac
during RTH (09:35–16:00 ET, weekdays).  Every `cadence_min` minutes (default
15) it sweeps the active options universe (22 ETF anchors + top `top_names`
gex names, ~150 roots) and pulls a full-chain greeks snapshot per root via the
ThetaData v3 snapshot API — first_order (delta/theta/vega/rho/IV) joined with
second_order (gamma/vanna/charm/vomma/veta) on the contract key.  This is the
Interval Map / Volatility Drift data plane
(`research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` §5 U-CHAIN, WP-UCHAIN).

## Files written

| Path (under `data/chain_snapshots/`, gitignored) | Contents |
|---|---|
| `{ROOT}/{YYYY-MM-DD}.parquet` | greeks rows; dedup key = (root, expiration, strike, right, snapshot_bucket) |
| `{ROOT}/{YYYY-MM-DD}_oi.parquet` | one OI snapshot per root per day (first sweep only — OI timing law: the ~06:30 ET stamp holds EOD t-1 positions and never moves intraday) |
| `_meta.json` | per-cycle run status (sweep count, rows, latency, errors, quarantined) |
| `{ROOT}/{date}.corrupt-{ts}.parquet` | quarantine: an existing day frame that failed to read is renamed aside (bytes preserved), never overwritten — check `_meta.json` `quarantined` and recover/inspect manually |

Forward volume ≈ 0.4–1 GB/day (program doc §5) — watch disk alongside the
tape-lane hot window.

## Concurrency budget (HARD)

`chain_snapshots.max_concurrent: 1` in `config.yml`.  The live_flow poller
owns 2 of the terminal's 8 concurrent request slots during RTH and the T1
backfill shares the rest.  NEVER raise without explicit Fable adjudication.
A full ~150-root sweep ≈ 300 snapshot requests ≈ ~5 min wall at concurrency 1
— comfortably inside the 15-min cadence.

## launchd install

The job follows the deploy-worktree doctrine (see `ops/LIVE_FLOW_RUNBOOK.md`):
launchd must run from a dedicated worktree pinned to `origin/main`, never from
the main checkout.

```bash
cd '/Users/chriswong/Documents/Cluade/Macro Dashboard'
git fetch origin main
git worktree add -B ops/chainsnap-deploy /Users/chriswong/chainsnap-ops-wt origin/main
cp '/Users/chriswong/Documents/Cluade/Macro Dashboard/.env' /Users/chriswong/chainsnap-ops-wt/.env

cp /Users/chriswong/chainsnap-ops-wt/ops/launchd/com.mastermind.chainsnapshots.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
```

The plist fires weekdays at 06:30 PT (= 09:30 ET); the poller waits for the
09:35 ET window start and self-exits after 16:00 ET (`--rth-only`).
ThetaTerminalApp must be running on port 25503 before the fire (Login Items
recommended).  No R2 creds are required — this lane writes local parquet only.

## Smoke / manual sweep

```bash
# One sweep, three roots (market closed returns last-known close-ish
# snapshots — structurally verifiable; timestamps carry the truth):
python -m scripts.chain_snapshot_poller --once --roots SPY MSFT WDC
```

## Log tailing

```bash
tail -f /tmp/chainsnapshots.stdout.log /tmp/chainsnapshots.stderr.log
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
rm ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
```
