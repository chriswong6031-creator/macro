# P0-B1 — BioCatalyst deployment blocker diagnosis

**Date:** 2026-08-16  
**Probe window:** 16:11Z–16:15Z  
**Base:** `origin/main` `80b7e77ee1b01d4570f9eb80276120ee427ff6f8` (`cn-live(pr2)` #5787). Evidence PR #5800 was still open at probe time; its serving-stack finding is used as prior, not as a merge prerequisite for this diagnosis.  
**Scope:** name the first causal failure of `macro-market-memory-context.service` and whether that failure is *required* to block `macro-api` restart. No `update.sh` edit. No Market Memory evidence rewrite. No bound widening. No timer enable. No BioCatalyst change. No production API restart.

## Conclusion

The context oneshot fails at **trusted-regime temporal freshness**, not at systemd sandboxing, source/config ownership, public/private store validation, `publish_live_audit`, or an options-context ledger bound.

Exact raise: `engine.neuralweb.market_memory_projection._validate_source_freshness` → `MarketMemoryProjectionError: regime source build is too old for current trusted projection`.

Input: git-tracked `/opt/macro/data/regime/latest.json` (`asof=2026-08-14`, `freshness.built_at=2026-08-14T23:58:19Z`). Bound: `_MAX_SOURCE_BUILD_AGE = 36 hours`. Wall-clock age at 16:15Z was **40.28 h**. Threshold crossed **2026-08-16T11:58:19Z**. Last successful `Finished` was the 11:57:20Z start / 11:58:33Z finish (observation clock still inside 36 h). Repeating failure began **2026-08-16T12:00:25Z** and has fired every ~3 minutes since.

`macro-market-memory-source.service` succeeds independently (`already_present`). `macro-market-memory-technicals.service` fails independently with a **different** error (`public R2 manifest contains an unsafe or noncanonical filename`). The W2C owner chain is source → context → technicals, so context failure stops the chain before technicals; technicals is still failing on its own timer.

W2C owner-replay failure is **required to keep experience/options/reciprocal activation disarmed**. It is **not** required to prevent `macro-api` restart for `app/*.py`. The same context.service failure is already fail-soft in the W1B.1 projection block (`hourly timer will retry`, no `exit 1`). The BioCatalyst serving stall is caused by W2C attestation using `exit 1` for the whole updater before `MACRO_API_RESTART_TRIGGER`.

## Identity (serving stack, unchanged from #5800)

| Item | Value at 16:15Z |
|---|---|
| `/opt/macro` HEAD | `80b7e77ee1b0` |
| `/api/health` | `{"status":"ok","commit":"ba6a6665a97","checkout":"80b7e77ee1b"}` |
| `macro-api` MainPID | **372997** since 2026-08-16 09:51:09 UTC |
| #5793 | ancestor of checkout; not in the running import |

## 1. Context service — first causal failure

Live systemd boundary (not a hand-invoked Python import). Cron/`w2c_start_owner_chain` already starts the unit every ~3 minutes. Latest observed start: 16:09:20Z (and 16:12:22Z).

| Field | Value |
|---|---|
| Unit | `macro-market-memory-context.service` |
| Type | oneshot, `PrivateNetwork=true`, `ProtectSystem=strict`, `ReadOnlyPaths=/opt/macro` |
| ExecStart | `/opt/macro-api/.venv/bin/python -m scripts.project_market_memory_context --repository-root /opt/macro --public-store-root /var/lib/macro-market-memory/public/trusted-v1 --private-evidence-root /var/lib/macro-market-memory/state/context-projection` |
| `ActiveState` / `Result` | `failed` / `exit-code` |
| `ExecMainCode` / `ExecMainStatus` | 1 / **1** |
| First causal exception | `engine.neuralweb.market_memory_projection.MarketMemoryProjectionError` |
| Message | `regime source build is too old for current trusted projection` |
| Function | `_validate_source_freshness` (`engine/neuralweb/market_memory_projection.py` ~454–486) |
| Call chain | `main` → `run_projection_cycle` → `project_current_context` → `build_macro_regime_snapshot` → `_validate_source_freshness` |
| Input/artifact | `/opt/macro/data/regime/latest.json` (tracked checkout file, not private evidence) |
| Bound | `_MAX_SOURCE_BUILD_AGE = timedelta(hours=36)`; `_MAX_SOURCE_AGE_SESSIONS = 1` |
| Evaluated clocks | `freshness.built_at=2026-08-14T23:58:19Z`; `asof=2026-08-14`; `freshness.age_days=0`; `age_sessions=0`; `max_age_sessions=1`; `stale=false` |
| Which clause fired | `build_age > _MAX_SOURCE_BUILD_AGE` (the session-stale / `stale is not False` clause would not fire: `stale=false` and `age_sessions=0 ≤ 1`) |
| Last success | `Finished` 2026-08-16T11:58:33Z (start 11:57:20Z; observation clock still ≤ 36 h) |
| Repeating failure began | 2026-08-16T12:00:25Z (first `too old` after `built_at + 36h = 11:58:19Z`) |

Sanitized journal excerpt (16:09:20Z tick):

```
Starting macro-market-memory-context.service ...
File ".../scripts/project_market_memory_context.py", line 91, in project_current_context
    snapshot = market_memory_projection.build_macro_regime_snapshot(regime_path)
File ".../engine/neuralweb/market_memory_projection.py", line 519, in build_macro_regime_snapshot
    _validate_source_freshness(...)
File ".../engine/neuralweb/market_memory_projection.py", line 484, in _validate_source_freshness
    raise MarketMemoryProjectionError(
MarketMemoryProjectionError: regime source build is too old for current trusted projection
Main process exited, code=exited, status=1/FAILURE
Failed with result 'exit-code'.
```

Not reached on this failure (later in `project_current_context` / `run_projection_cycle`): checkout ownership of regime bytes (`_tracked_bytes`), canary config SHA, `capture_trusted_regime_context`, options receipt `publish_live_audit`. Systemd sandbox did not prevent the process from starting or importing the projector.

`tests/test_market_memory_projection.py` already documents the same 36 h wall-clock trap on this git-tracked fixture and pins the unit-test clock to `freshness.built_at` so CI does not expire. Production systemd uses wall clock. Friday 23:58Z build + no Saturday/Sunday `built_at` refresh ⇒ Sunday 11:58Z fail-closed. The 14:16Z commit `80b7e77ee1b` touched `data/regime/latest.json` without advancing `freshness.built_at`.

### Source and technicals independently

| Unit | Independent result | Evidence |
|---|---|---|
| `macro-market-memory-source.service` | **succeeds** | `Result=success`, `ExecMainStatus=0`; stdout `status=already_present` `source_id=fred_alfred:CPIAUCSL` generation `mmsgen_396db27d…` |
| `macro-market-memory-context.service` | **fails** | freshness, above |
| `macro-market-memory-technicals.service` | **fails, different cause** | last start 15:54:01Z (not in the current owner chain after context dies). `MarketMemoryTechnicalObservationError: public R2 manifest contains an unsafe or noncanonical filename` at `_validate_manifest` ← `fetch_current_spy_daily_inputs`. Not the W2C-blocking exception today. |

`w2c_start_owner_chain` order is `source`, `context`, `technicals`. Context failure returns 1 after source success; technicals is not started on that tick.

## 2. Must W2C failure block macro-api restart?

### What the tests actually require

| Artifact | Invariant pinned | Couples API restart? |
|---|---|---|
| `tests/test_market_memory_experience_deploy.py::test_updater_deferred_replay_is_ordered_and_owner_failure_suppresses_w2c` | Owner chain is source → context → technicals → **experience**. Context failure: returncode 1; **experience.service must not start**. | No. Extracted `W2C_DEFERRED_REPLAY` shell only. |
| `::test_updater_no_diff_attests_and_rearm_requires_synchronous_owner_replay` | Rearming experience.timer requires owner starts first; invalid/forged terminal fails closed; sealed terminal disarms the timer. | No. |
| `tests/test_market_memory_experience_deploy.py` (unit-block presence) | `w2c_start_owner_chain`, `w2c_verify_installation`, `w2c_reconcile_timer` exist in the experience/update block. | No API-restart assertion. |
| `tests/test_market_memory_context_deploy.py::test_update_verifies_installs_arms_and_immediately_reprojects` | Context unit reconcile + `systemctl start …-context.service` live in the block *before* `# macro-api: restart ONLY`. | File order of the **context install** block vs the API comment. Does not require start-failure to abort the updater. |
| `::test_api_setup…` (setup.sh) | First-install: `systemctl start macro-market-memory-context.service` before `systemctl restart macro-api`. | **Setup only**, not `update.sh` ongoing ticks. |
| `tests/test_deploy_update_self_heal.py` | `MACRO_API_RESTART_TRIGGER` fires on `API_UNIT_UPDATED`, fence unreadiness, or `CHANGED` matching `app/*.py` (and the listed import-cached modules). | Independent of W2C. |
| `tests/test_market_memory_options_deploy.py` | Reciprocal fence marker, Conflicts/After vs other MM units, option root hidden. | Options stay disarmed without a healthy reciprocal/API fence. Not “no API restart until context projects.” |
| `app/deploy/update.sh` comment at deferred replay (~1372) | “A deploy in W2C's 04:30-04:45Z window must never seal stale pre-deploy owner heads.” | About **not activating W2C on stale heads**, not about skipping `macro-api` restart. |

No test, decision record, or fence contract was found that requires: “W2C owner replay succeeds BEFORE macro-api may restart for `app/*.py`.”

The narrower invariant **is** tested: W2C/experience activation (and deferred reciprocal re-arm) must remain disarmed until owner replay + installation attestation succeed.

### Same failure, two treatments in `update.sh`

W1B.1 context projection (~665–672), **before** W2C attestation:

```
elif ! systemctl start macro-market-memory-context.service; then
    echo "macro-update: Market Memory context projection failed closed; hourly timer will retry" >&2
fi
```

No `exit 1`. The updater continues.

W2C runtime attestation (~936–938):

```
if ! w2c_start_owner_chain; then
    echo "macro-update: refusing W2C activation before owner replay completion" >&2
    exit 1
fi
```

`exit 1` aborts the **entire** `macro-update` process. `MACRO_API_RESTART_TRIGGER` (~1214) is never reached. That is script-order coupling, not a named security invariant. The W1B.1 block already shows the house pattern for “context projection failed closed; retry later.”

`api-setup.sh` starting context before the first API restart is greenfield readiness (trusted store empty). Ongoing deploys already have an API process; #5800’s defect is that process remaining on `ba6a6665a97`.

## Evidence matrix

Observed production at 16:15Z, plus what the contracts pin.

| State | Observed now | Needs coupling to W2C owner-replay health? | Needs coupling to API restart? |
|---|---|---|---|
| macro-api unit/dependencies safe to restart | Yes: unit active, PID 372997 healthy, checkout has `app/biocatalyst.py` #5793 | No | This *is* the restart decision |
| macro-api restart requested by changed files | Yes since 12:38Z (#5793 `app/biocatalyst.py` matches `app/.*\.py`) | No. Trigger regex is independent (`test_deploy_update_self_heal.py`) | Yes — that is the trigger |
| W2C owner replay healthy | **No** (context freshness; technicals would fail next) | Self | No |
| W2C experience activation permitted | **No** (tests: suppress experience on owner failure) | **Yes** — this is the tested invariant | No |
| options canary activation permitted | Remain disarmed while reciprocal/API fence unset; W2C `exit 1` currently also prevents later fence finalization | **Yes** to stay disarmed until attested | Restart *disarms* the options timer (`disarm_options_timer` inside the API restart block) but does not require W2C green first |
| reciprocal writer activation permitted | Reciprocal pause/re-arm is a separate W1B5 boundary; owner failure must not re-arm | **Yes** to stay paused until deferred replay succeeds | No |

## Why not “fix Market Memory only” or “decouple only”

Fixing only the 36 h regime artifact (or waiting for the next weekday nightly that stamps a new `built_at`) would unblock owner replay **and** API restart without touching `update.sh`. That still leaves technicals red on the R2 filename, so experience activation would remain blocked after context is green. It also leaves every future stale-regime weekend able to freeze **all** `app/*.py` deploys.

Decoupling only would let #5793 load into uvicorn while W2C stays fail-closed — matching the W1B.1 fail-soft line and the tested “don’t activate experience” invariant. It would not make trusted context or technicals healthy.

Those are two different defects. They should not share one PR.

## Rollback

Documentation only. No production bytes, ledgers, receipts, timers, or API process were changed by this session.

FIRST DEPLOYMENT ROOT CAUSE: trusted-regime temporal freshness — `_validate_source_freshness` rejects `/opt/macro/data/regime/latest.json` because `freshness.built_at=2026-08-14T23:58:19Z` is older than `_MAX_SOURCE_BUILD_AGE` (36h); wall-clock age 40.28h at 16:15Z; repeating since 12:00:25Z

RECOMMENDED NEXT PR: TWO SEPARATE REPAIRS ARE REQUIRED
