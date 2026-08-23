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

A launchd keepalive (`com.macro.thetadata-backfill.plist`) used to auto-resume
the job after Mac reboots. **That lane is RETIRED (AD-1T1, 2026-08-22)** —
see §3a. The store's day-to-day freshness is now owned by a *separate*
tool, `scripts/topup_thetadata_day.py --daily` (the AD-1T1 full-universe
incremental daily maintainer), scheduled by `com.macro.thetadata-daily.plist`.
`backfill_thetadata_eod.py` itself remains as an explicit, manually-invoked
resumable tool for HISTORY (initial fills, ticker-reuse floors, deep
re-backfills) — it is no longer scheduled nightly, and no longer re-pulls the
whole current year.

---

## §2 Resume-after-reboot procedure

After a Mac reboot, the launchd keepalive (§3) should auto-resume.  If it does not,
or if you need to manually confirm the job:

**Step 1 — Confirm ThetaTerminal is running.**

```bash
pgrep -fl "ThetaTerminalv3\|theta"
```

If it is not running, the `com.macro.theta-terminal` keepalive lane (§3) should
relaunch it within ~60 s.  If that lane is not installed, start it manually:

```bash
# Preferred: the repo launcher (handles Java 21, key-via-env, stdin-safe launch)
bash "/Users/chriswong/Documents/Cluade/Macro Dashboard/scripts/run_theta_terminal.sh"

# Manual equivalent — TWO laws:
#   1. Key via environment, NEVER as --api-key argv (argv is plaintext-readable
#      by any local process via `ps`).
#   2. stdin held open by an infinite pipe — stdin EOF is the v3 shutdown
#      trigger; a bare `java ... &` dies when the launching tty closes
#      (the 2026-07-17..07-20 outage).
cd /Users/chriswong/theta && \
    nohup tail -f /dev/null | THETADATA_API_KEY="$THETA_API_KEY" nohup java -jar ThetaTerminalv3.jar &
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

## §3 launchd lanes: install, verify, uninstall

Three launchd lanes keep the EOD store alive end-to-end.  Plists + wrapper
scripts ship under `scripts/launchd/` in the repo; the plists execute the ops
worktree copies (`/Users/chriswong/theta-ops-wt/scripts/launchd/`) because
macOS TCC denies launchd exec under `~/Documents/` — after a lane-affecting
merge, fast-forward the ops worktree before expecting behavior changes.

| Lane | Label | Schedule | What it does |
|------|-------|----------|--------------|
| Terminal keepalive | `com.macro.theta-terminal` | `KeepAlive`, 60 s `ThrottleInterval` | Health-polls :25503 — healthy = HTTP 200 **and** a non-trivial body (> 1000 B) on `/v3/option/list/symbols`; a bare 200 can be a ZOMBIE (stale/revoked `THETA_API_KEY` → empty 200s while data endpoints time out; bit live 2026-07-20). Exits 0 when healthy, or when a ThetaTerminalv3 process exists and the port doesn't answer (never duplicates a manual launch). A confirmed zombie (two consecutive empty-200 reads) is recycled: the bootstrapper jar plus the `:25503` LISTENer (the inner lib jar, which can orphan-survive the bootstrapper) are killed and the next fire relaunches with a fresh `.env` read. Otherwise launches the terminal with stdin held open on an anonymous FIFO (stdin EOF is the v3 shutdown trigger; root cause of the 2026-07-17..07-20 outage — and never a `tail -f \|` pipe, which deadlocks the wrapper when java dies), java backgrounded under an in-run watchdog that applies the same zombie law every 60 s (launchd cannot re-invoke a running job, so the wrapper polices its own child). Backs off 240 s on insta-death (< 30 s) or a zombie recycle so the auth endpoint is never hammered; auto-heals ~5 min after the key is fixed in `theta-ops-wt/.env`. Log: `/tmp/theta_terminal_keepalive.log`. |
| **Daily incremental maintainer** (AD-1T1) | `com.macro.thetadata-daily` | `StartCalendarInterval` 13:20/14:30/16:00/18:00 PT, **no `KeepAlive`** | Runs `topup_thetadata_day.py --daily` — the full-universe incremental T1 maintainer (§3a). Gate-checked + idempotent in python; the four fire points are the bounded retry ladder (a healthy earlier run makes later fires cheap no-ops). Log: `theta-ops-wt/daily_refresh.log`. Health receipt: `daily_refresh` section of `data/thetadata_eod/_manifest.json`. |
| ~~Backfill keepalive~~ **RETIRED** | ~~`com.macro.thetadata-backfill`~~ | — | Whole-year re-pull of 48 refresh roots nightly + unconditional `KeepAlive` restart loop. Retired 2026-08-22 (AD-1T1) in favor of the daily incremental maintainer above — see §3a for the bootout procedure. `backfill_thetadata_eod.py` remains for manual historical work only. |
| Staleness sentinel | `com.macro.theta-staleness` | 06:15 + 18:30 local (`StartCalendarInterval`) | Tripwire against silent stalls: ALERTs when :25503 is unreachable, answers 200 with a trivial symbols body (zombie — stale/revoked key), `greeks/SPY` is ≥ 2 weekday-sessions behind (WARN at 1; today counts as due when local hour ≥ 17, or force with `--due-today`), **or (AD-1T1 F8, threshold fixed RF1 2026-08-22) `_manifest.json`'s `daily_refresh.D` is not today's NYSE session date after 20:00 ET on a session day** — the daily lane's own liveness anchor, needed because launchd calendar fires do not wake a sleeping Mac and coalesce on wake, so a sleeping/missed host is otherwise indistinguishable from a healthy one. (N2, R3 verify-pass) An anchor ALERT firing in the 20:00–21:30 ET window means the daily lane's three EARLIER fire points (13:20/14:30/16:00 PT) all failed too, since a successful earlier run would already have stamped `daily_refresh.D` — read it as an early warning that the whole day's ladder is behind, not a false alarm from catching the lane mid-attempt. (N3) The anchor also ALERTs unconditionally if the calendar evaluation itself cannot run (broken import, bad `REPO_ROOT`) — it fails CLOSED, never silently. Writes `/tmp/theta_staleness.json` (latest machine-readable verdict, atomic), appends `/tmp/theta_staleness.log`, and raises a macOS notification on WARN/ALERT. 06:15 = pre-open sanity before the ledger seal; 18:30 = post-close check that today's pull landed. |

The lanes are independent — install any subset.  The terminal keepalive is the
one that prevents a repeat of the 07-17 silent death; the sentinel is the alarm
if anything else starves the store.

### Install (once per lane)

```bash
# Pick the lane:
LANE=com.macro.theta-terminal   # or com.macro.thetadata-daily / com.macro.theta-staleness

# Step 1: copy the plist to LaunchAgents (do NOT commit ~/Library to git)
cp "/Users/chriswong/theta-ops-wt/scripts/launchd/${LANE}.plist" ~/Library/LaunchAgents/

# Step 2: load it
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/${LANE}.plist"

# Step 3: confirm the job is registered
launchctl list "${LANE}"
```

### Verify — terminal keepalive

```bash
curl -s -m 6 -o /dev/null -w 'http=%{http_code} bytes=%{size_download}\n' \
    'http://127.0.0.1:25503/v3/option/list/symbols'
# Healthy = http=200 AND bytes ≈ 100k+ (the full symbols list). http=200 with
# bytes=0 is a ZOMBIE (stale/revoked key) — the keepalive recycles it within
# ~2 min + a 240 s backoff; if it persists, refresh the key.
tail -5 /tmp/theta_terminal_keepalive.log
# Healthy steady state is SILENT (the wrapper exits 0 without logging).
# After a terminal death you should see "launching terminal (health was 000)"
# within ~60 s; repeated "died in <30s ... backing off 240s" = stale THETA_API_KEY
# → refresh it at https://thetadata.us/account into theta-ops-wt/.env (and
# hub-ops-wt/.env). Never echo or commit the key.
```

### Verify — daily incremental maintainer

```bash
# Manual diagnostic run (bypasses the session/time gate; stamps forced=true):
cd /Users/chriswong/theta-ops-wt
python -m scripts.topup_thetadata_day --daily --force-run
python -c "import json; d=json.load(open('data/thetadata_eod/_manifest.json')); print(json.dumps(d['daily_refresh'], indent=2))"
# Two concurrent invocations: the second must refuse (writer_locked, exit 0,
# zero mutations) — confirms the flock:
python -m scripts.topup_thetadata_day --daily --force-run &
python -m scripts.topup_thetadata_day --daily --force-run
```

### Verify — staleness sentinel

```bash
bash /Users/chriswong/theta-ops-wt/scripts/launchd/theta_staleness_sentinel.sh --due-today
cat /tmp/theta_staleness.json   # level OK/WARN/ALERT + latest_greeks_date + daily_refresh_d + reasons
```

### Uninstall (per lane)

```bash
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/${LANE}.plist"
rm "$HOME/Library/LaunchAgents/${LANE}.plist"
```

---

## §3a AD-1T1 transition: retiring the backfill keepalive for the daily maintainer

**Ruling (Sol handoff, `research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md`
§E):** exactly ONE scheduled daily T1 maintainer may be active on m1. This
wave ships the new lane's plist + wrapper + this runbook section; **m1
installation is a post-Sol-acceptance act, done by hand following the steps
below** — the PR does not run `launchctl` itself (§I out of scope for the
builder).

**Current status:** `com.macro.thetadata-daily` — `installed_live_status: NOT_INSTALLED`
pending Sol acceptance. Do not install, bootout, or bootstrap anything in
this section until Sol has accepted the PR; the steps below are the
documented procedure for whoever performs that install, not an instruction
to this build.

**Step 0 — refresh the ops-tree bytes to current main FIRST.** The live lane
runs from a DETACHED worktree, not a synced main (measured 2026-08-22:
`theta-ops-wt` HEAD was weeks behind, with newer bytes hand-copied on top for
some files and `collectors/thetadata.py` left at an old revision missing the
#5942 NA-parse fixes). Installing the new label on stale bytes ships the OLD
writer under the NEW schedule. At minimum, refresh these files in
`/Users/chriswong/theta-ops-wt/` to the merged AD-1T1 commit before
bootstrapping:

```bash
cd /Users/chriswong/theta-ops-wt
git fetch origin && git checkout origin/main -- \
    collectors/thetadata.py \
    scripts/topup_thetadata_day.py \
    scripts/backfill_thetadata_eod.py \
    lib/nyse_calendar.py \
    scripts/launchd/theta_daily_refresh.sh \
    scripts/launchd/com.macro.thetadata-daily.plist \
    scripts/launchd/theta_staleness_sentinel.sh
chmod +x scripts/launchd/theta_daily_refresh.sh
```

(A full `git pull`/fast-forward of the ops worktree to main is preferable
where the ops-tree divergence allows it — the file list above is the MINIMUM,
not a ceiling.)

**Step 1 — bootout the old label, then verify no orphan survives it.**
`launchctl bootout` kills the wrapper shell but NOT necessarily a
`backfill_thetadata_eod` python child it may have spawned and left running —
the F7 orphan hazard this build's daily-mode pgrep-advisory design exists
because of:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
pkill -f backfill_thetadata_eod
sleep 2
pgrep -fl backfill_thetadata_eod   # MUST print nothing — verify before Step 2
rm -f ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
```

**Step 2 — TZ + no-sleep assertions.** The plist's `StartCalendarInterval`
hours are host-local (PT) — correctness rests on the `America/New_York` gate
inside python, but the fire *points* only land where intended if the host
clock is where the plist assumes:

```bash
systemsetup -gettimezone   # MUST print: Time Zone: America/Los_Angeles
pmset -g | grep -E '^\s*sleep\s'   # sleep must be 0 (Never) — a sleeping Mac
                                    # coalesces missed calendar fires on wake
                                    # (F8 is the tripwire if this regresses)
```

**Step 3 — bootstrap the new label.**

```bash
cp /Users/chriswong/theta-ops-wt/scripts/launchd/com.macro.thetadata-daily.plist \
    ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-daily.plist
launchctl list com.macro.thetadata-daily
```

**Step 4 — auto-login note.** Both the retired and the new lane carry
`LimitLoadToSessionType Aqua` — the agent loads only at GUI login, so the
account must be configured for auto-login (System Settings → Users & Groups)
or a reboot silently drops the whole daily lane until someone logs in.

### Catch-up procedure (gaps of >= 2 sessions)

The daily mode NEVER sweeps history — a missed prior session self-heals only
one day at a time (the next session's run ensures the missed S cells by
construction). For a real gap (host down over a long weekend, terminal outage
spanning multiple days), use the explicit catch-up tool instead of the
historical backfill:

```bash
cd /Users/chriswong/theta-ops-wt
python -m scripts.topup_thetadata_day --roots @universe --date 2026-08-18
```

This resolves the full T1 universe via the same resolver the daily mode uses
and runs the same 3-tier one-day ensure as the legacy bounded mode, for the
one named date. Run once per missed session date, oldest first.

### `ONE_OFF_CLOSURES` maintenance (F12)

`lib/nyse_calendar.py`'s `ONE_OFF_CLOSURES` is **hand-maintained** (a market
closure that is not a fixed federal holiday — e.g. a national day of
mourning). If the daily receipt's `s_suspect_non_session` flag is ever `true`
(> 50% of attempted roots returned EOD[S] vendor-empty), that is the
operator breadcrumb to check whether an unlisted closure needs to be added to
`ONE_OFF_CLOSURES` — never patch around it by walking `S` backwards manually;
the calendar module is the single source of truth for what counts as a
session.

---

## §4 State-file semantics

| File | Location (ops worktree) | Semantics |
|------|------------------------|-----------|
| `_backfill_state.json` | `data/thetadata_eod/` | One entry per (root, date) pair, written after a successful pull. Drives idempotency: completed pairs are skipped. Never delete; edit only with `backfill_thetadata_eod.py --reset-root <root>` if a root needs re-pulling. |
| `_manifest.json` | `data/thetadata_eod/` | Read-modify-write (AD-1T1) — the backfill script's own four keys (`store`/`n_roots`/`per_root`/`updated_at`) and the daily maintainer's `daily_refresh` health receipt (§3a) each preserve the OTHER writer's section rather than clobbering it. Gate R8 (roadmap): no gate harness reads the store until this marks the universe pass complete. |
| `daily_refresh` (inside `_manifest.json`) | `data/thetadata_eod/_manifest.json` | Overwritten once per `--daily` run (no unbounded history — `daily_refresh.log` carries history). `status` is `healthy`/`partial`/`failed`; `D` is the staleness anchor the sentinel checks (F8). A gate no-op or a lock refusal writes NO receipt at all — absence is itself the honest record. |
| `_writer.lock` | `data/thetadata_eod/` | Crash-safe advisory `flock` guarding every T1 store writer (§B). Never committed to git, never uploaded to R2 (`.gitignore` + `publish_r2._uploadable`). The lock FILE persisting on disk is harmless — the LOCK dies with the process. |
| `backfill.log` | `theta-ops-wt/` | Append-only; records `backfill_thetadata_eod.py` manual-run output. Never truncate while a backfill is running. |
| `daily_refresh.log` | `theta-ops-wt/` | Append-only launchd stdout/stderr for the `com.macro.thetadata-daily` lane. |

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

**When to publish:** SCHEDULED since 2026-07-16 — the `com.macro.thetadata-r2sync`
launchd agent runs the sync nightly at 22:00 PT (after the refresh pass settles).
**How:** `python -m scripts.publish_r2 --dirs thetadata_eod` (md5/ETag delta-skip;
`_DATA_DIR_MIN_FILES` guard refuses partial checkouts). Install + verify + restore:
`ops/THETADATA_R2_SYNC_RUNBOOK.md`.
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
