# P0-B2 production acceptance — BioCatalyst deploy decoupling

**Date:** 2026-08-16  
**Probe window:** 17:36:42Z–17:46:37Z  
**Scope:** evidence only. Normal `macro-update` cron (`*/3 * * * *`). No `systemctl restart macro-api`. No `update.sh`, Market Memory, BioCatalyst, timer, ledger, or evidence edits.

## Conclusion

PR **#5804** squash-merged as `021553985cbe6bf950413c7cb10fc302d05a9633` at 17:36:58Z. The next cron tick (17:39Z) pulled it through `/usr/local/bin/macro-update` and performed a verified `macro-api` PID transition **before** W2C attestation failed closed.

`/api/health.commit` now equals `/api/health.checkout`. Both are `021553985cb`. That commit is a child of `80b7e77ee1b0`, which already contained #5793 (`8f6952966866`). The running process therefore loads the #5793 caller-binding (`_CALLER_ACCESS_DOMAIN = "site_full"`; no `user.get("tier")`).

Two subsequent cron ticks (17:42Z, 17:45Z) did **not** restart `macro-api`. PID and InvocationID were unchanged. The API fence continued to name that same process. W2C remained fail-closed on trusted-regime freshness. Experience.service was not started. The options timer stayed disabled.

Signed-out BioCatalyst is HTTP 401 and paints `data-state=locked`, not “Registry page unavailable.” No existing entitled browser/session could be reconstituted. No JWT was minted.

## Identity

| Item | Before (17:36:42Z) | After deploy tick (17:39:10Z) | Stabilization (17:42Z and 17:45:50Z) |
|---|---|---|---|
| `origin/main` | `80b7e77ee1b0` | `021553985cbe` (#5804) | `021553985cbe` |
| `/opt/macro` HEAD | `80b7e77ee1b0` | `021553985cbe` | `021553985cbe` |
| `/api/health.commit` | `ba6a6665a97` | `021553985cb` | `021553985cb` |
| `/api/health.checkout` | `80b7e77ee1b` | `021553985cb` | `021553985cb` |
| `macro-api` MainPID | **372997** since 09:51:09Z | **856919** since 17:39:10Z | **856919** since 17:39:10Z |
| InvocationID | `e47d97d752da448189f23acaf04bd4a9` | `de8564e0f6754a04bffa2e1c69137d27` | `de8564e0f6754a04bffa2e1c69137d27` |
| API fence body | `372997 e47d97d752da448189f23acaf04bd4a9` | `856919 de8564e0f6754a04bffa2e1c69137d27` | same as after |
| Fence metadata | `root:root:644` | present, matches live PID/InvocationID | present, matches live PID/InvocationID |

Public Caddy path `https://www.mastermind-x.com/api/health` at 17:46:37Z: HTTP 200 `{"status":"ok","commit":"021553985cb","checkout":"021553985cb"}`.

#5793 ancestry (local object db, not the VPS shallow clone): `git merge-base --is-ancestor 8f695296686687e957aa4e31fabc33259de1c224 origin/main` → yes. Parent of `021553985cbe` is `80b7e77ee1b0`. Production `/opt/macro` is a depth-1 checkout (`rev-list --count HEAD` = 1), so ancestry was confirmed from GitHub `origin/main` plus the on-disk `app/biocatalyst.py` loaded at the 17:39 restart: `_CALLER_ACCESS_DOMAIN` present; `entitlement = user.get("tier")` absent.

## Verified restart through normal macro-update

Cron: `*/3 * * * * /usr/local/bin/macro-update >> /var/log/macro-update.log 2>&1`.

Sanitized 17:39Z tick (log lines 1592–1597):

```
macro-update: self-updated from repo
macro-update: deferring W2C replay and attestation until reciprocal boundary closure
macro-api restarted pid 372997 -> 856919
macro-update: option-OI lane remains disarmed until units, credential, and API fence are verified
macro-update: W2C installation and terminal state were not authenticated
```

That is the allowed result: API deployment succeeded; W2C remained fail-closed; updater reported W2C unhealthy. No manual `systemctl restart macro-api` was issued.

`NRestarts=0` on the unit; the PID change is the updater’s verified restart, not systemd crash-looping.

## No restart loop

| Tick (UTC) | Log | PID | InvocationID | Restart? |
|---|---|---|---|---|
| 17:36 | pre-#5804; W2C context `exit 1` | 372997 | `e47d97d7…` | no (pre-decouple; API never reached) |
| 17:39 | pull #5804; restart; W2C unauthenticated | **856919** | `de8564e0…` | **yes, once** `372997 -> 856919` |
| 17:42 | defer W2C; context freshness fail; refuse deferred W2C | 856919 | `de8564e0…` | **no** |
| 17:45 | W2C owner replay failed: context; refuse activation | 856919 | `de8564e0…` | **no** |

`grep` of `/var/log/macro-update.log`: exactly one `macro-api restarted pid 372997 -> 856919`; zero later `macro-api restarted pid 856919 -> …` lines. Fence after 17:45 still `856919 de8564e0f6754a04bffa2e1c69137d27`.

17:42 excerpt (1603–1606) then 17:45 (1608–1611):

```
Job for macro-market-memory-context.service failed ...
macro-update: W2C owner replay failed: context
macro-update: refusing deferred W2C activation before owner replay completion
...
Job for macro-market-memory-context.service failed ...
macro-update: W2C owner replay failed: context
macro-update: refusing W2C activation before owner replay completion
```

## W2C stayed fail-closed

Inputs were not cured.

**Context owner (first causal failure, unchanged from #5802):**  
`MarketMemoryProjectionError: regime source build is too old for current trusted projection`  
Latest start in this window: 17:42:24Z, exit 17:42:26Z, `ExecMainStatus=1`. Bound remains `_MAX_SOURCE_BUILD_AGE = 36h` against `data/regime/latest.json` `freshness.built_at=2026-08-14T23:58:19Z`.

**Technicals (independent, not reached by a failing owner chain until context is green):** still failed as of last start 16:54:04Z–16:54:09Z with `MarketMemoryTechnicalObservationError: public R2 manifest contains an unsafe or noncanonical filename`. Not restarted at 17:42/17:45 because context died first.

**Experience activation:**

| Check | Observation |
|---|---|
| `macro-market-memory-experience.service` since 17:39 | `journalctl --since 17:39` → no entries. Last success remains Sat 2026-08-15 04:30:00–04:30:04Z, `Result=success`, `ActiveState=inactive` |
| experience.timer | `UnitFileState=enabled` (pre-existing latch from the Saturday run; updater `exit 1` never reaches a disable). `ActiveState=inactive`, `SubState=dead`, `NextElapseUSecRealtime` empty, `LastTriggerUSec=Sat 2026-08-15 04:30:00 UTC`. Not `enable --now`’d by failed owner replay |
| options.timer | `disabled` / `inactive` throughout |
| API fence vs options/W2C arming | Fence valid after 17:39. Log: `option-OI lane remains disarmed until units, credential, and API fence are verified`. 17:42 attempted a fail-soft options capture (`option-OI capture failed closed; weekday timer will retry`) and left the timer **disabled**. Valid fence did not arm W2C |

## BioCatalyst serving proof

### Signed-out (required, observed)

| Probe | Result |
|---|---|
| `GET /api/biocatalyst/v1/health` (VPS `127.0.0.1:8000`, Host `www.mastermind-x.com`) | HTTP **401** `{"detail":"missing bearer token"}` `Cache-Control: private, no-store` |
| `GET /api/biocatalyst/v1/trials?window=current` | HTTP **401** same body |
| Browser `https://www.mastermind-x.com/biocatalyst.html` (Playwright Chromium, no storage state) | `#bci-workspace data-state=locked`; body matches locked/full-access copy; **not** “Registry page unavailable”; `MDXAuth.hasSession()=false`; `tokenPresent=false` |
| Browser API | `GET /api/biocatalyst/v1/trials/milestones?...` HTTP **401** |
| `pageerror` | none |
| console | one expected `Failed to load resource: … 401`. No validator throw |

### Entitled browser / HTTP 200 matrix

No already-authorized session was available. No JWT was minted or printed. The #5800 checkout-interpreter positive control is **not** reused as serving-path proof.

Public projection pointer (not an entitled HTTP 200): `generation_id=ctgov_run_20260816T170023094484Z_e679bb3d2518`, `coverage_class=current_only`, `published_at=2026-08-16T17:00:24Z`.

| Surface | Entitled serving-path result |
|---|---|
| Trial Screen | **OWED** |
| Peer Matrix (two covered NCTs) | **OWED** |
| Milestones | **OWED** |
| Change Tape | **OWED** |
| First-seen Tape | **OWED** |
| dossier | **OWED** |

## Rollback

Revert #5804. `macro-update` would again `exit 1` at W2C before `macro-api` restart; `health.commit` would stick on the previous PID. This session did not change production bytes except by merging #5804 and letting the existing cron pull it.

P0-B2 DEPLOYMENT ACCEPTED — ENTITLED BROWSER ACCEPTANCE OWED
