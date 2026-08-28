# Sentry — error + trace reporting for the VPS serving tier

**Status:** live on the droplet (`146.190.142.17`, `mastermind-x.com`) for
`macro-api.service`.
**Code:** [`app/observability.py`](../../app/observability.py) (the arm),
[`app/main.py`](../../app/main.py) (the call site),
[`app/requirements.txt`](../../app/requirements.txt) (`sentry-sdk`).
**Tests:** `tests/test_observability_sentry.py`, run by the `serving-observability`
CI job (`gate: code`, i.e. on the merge gate).

---

## What this buys

Before this, a serving-tier fault existed only as a line in
`journalctl -u macro-api` on the droplet. A 500 on a paid route, a
`paywall router not mounted` degrade, an exception inside a BackgroundTask —
all of it died on the box unless somebody SSH'd in and read the journal.

Now `macro-api` reports to the Sentry project **`python`** under org
`o4511944095432704`:

- **Every unhandled exception**, with the full FastAPI request context.
  Errors are *not* sampled — 100% are captured.
- **`logging` records** at WARNING/ERROR from the whole process (the
  `macro.api` logger and every module it wraps), via `enable_logs`.
- **A sample of transactions** for latency/tracing (10% by default — see below).

Auto-instrumented: FastAPI, Starlette, `logging`, `requests`/`urllib3`,
`boto3`, and the stdlib. No per-route code was added anywhere.

---

## Where the DSN lives

`/etc/macro-api.env` on the droplet (root-only, `0600`) — the same file that
holds the Stripe and Supabase secrets. **It is not in git**, deliberately:

```
SENTRY_DSN=https://<key>@o4511944095432704.ingest.us.sentry.io/4511944141307905
```

A Sentry DSN is a write-only ingest key rather than a true secret (browser SDKs
ship theirs in page source), but keeping it in the env file is what lets you
rotate it, point a staging box at a different project, or **kill ingestion
entirely** — comment the line out and `systemctl restart macro-api` — with no
code change and no render cycle.

With `SENTRY_DSN` absent, `app/observability.py` logs one INFO line and no-ops.
That is also the default state for every local checkout and every CI runner, so
nobody's laptop or PR ever ships events into the production project.

---

## Tuning knobs (all optional, all in `/etc/macro-api.env`)

| Variable | Default | What it does |
|---|---|---|
| `SENTRY_DSN` | *(unset)* | Absent ⇒ Sentry is off entirely. |
| `SENTRY_ENVIRONMENT` | `production` | Tags every event. Use `staging` on a second box. |
| `SENTRY_RELEASE` | deployed git SHA (12 chars) | Resolved from `/opt/macro` at boot; set explicitly to override. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Fraction of requests traced. **Does not affect error capture.** |
| `SENTRY_PROFILE_SESSION_SAMPLE_RATE` | `0.0` | Profiler off by default. |
| `SENTRY_SEND_DEFAULT_PII` | `1` | Attach request headers + client IP. |
| `SENTRY_ENABLE_LOGS` | `1` | Forward `logging` records as Sentry logs. |

Any change here needs `systemctl restart macro-api` to take effect — systemd
reads `EnvironmentFile` at unit start, not on write.

### Why not the quickstart's `1.0` / `1.0`

Sentry's Python quickstart hands out `traces_sample_rate=1.0` and
`profile_session_sample_rate=1.0`. That is a *getting-started* setting. On this
box it would trace:

- every `/api/flow/*` poll — the tape page polls several of those on a
  seconds-long cadence, per open tab;
- every Caddy-fronted static-gate check that reaches `/api`;
- every 3-minute `macro-update` health probe.

That burns the transaction quota in hours and adds a profiler thread to a
process sharing a 1–2 vCPU droplet with the live lanes. **Errors are captured
at 100% regardless of these two numbers.**

To match the quickstart exactly anyway:

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'printf "SENTRY_TRACES_SAMPLE_RATE=1.0\nSENTRY_PROFILE_SESSION_SAMPLE_RATE=1.0\n" >> /etc/macro-api.env && systemctl restart macro-api'
```

### PII

`send_default_pii=1` attaches request headers and the client IP. Sentry's
default event scrubber (on unless explicitly disabled) still strips
`Authorization`, `Cookie`, `X-Api-Key` and friends, so the Supabase bearer
token does not leave the box. Set `SENTRY_SEND_DEFAULT_PII=0` to drop headers
and IPs entirely.

---

## Deploy path

No manual step for the code. `app/main.py`, `app/observability.py`, and
`app/requirements.txt` all match the existing `MACRO_API_RESTART_TRIGGER` regex
in `app/deploy/update.sh` (`^app/.*\.py$` / `^app/requirements\.txt$`), so the
3-minute `macro-update` cron:

1. pulls the merge,
2. sees `app/requirements.txt` changed → `pip install -r` into
   `/opt/macro-api/.venv` (installing `sentry-sdk`),
3. restarts `macro-api` and logs the PID transition.

The only manual step ever needed is writing `SENTRY_DSN` into
`/etc/macro-api.env` — done once, at install.

---

## Verify it is armed

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'journalctl -u macro-api --since "-10 min" | grep -i observability'
```

Armed looks like:

```
observability: Sentry armed for macro-api (env=production release=<sha> traces=0.1 profiles=0.0)
```

**Why that banner goes to stdout rather than through the logger** (it was a
`log.info` on first ship, and was invisible — fixed same day): uvicorn's
`LOGGING_CONFIG` configures only the `uvicorn`, `uvicorn.error` and
`uvicorn.access` loggers and leaves the root logger at its default `WARNING`.
Verified on the box:

```
uvicorn configured loggers: ['uvicorn', 'uvicorn.error', 'uvicorn.access']
root logger level: 30 WARNING
macro.observability effective level: WARNING
```

So any `log.info` from `app/observability.py` is dropped, while its
`log.warning` failure paths come through fine. The startup banner therefore
prints to stdout (flushed — stdout is block-buffered under systemd), which the
journal captures regardless of logging config. `tests/test_observability_sentry.py`
asserts this via `capsys`, **not** `caplog`: a `caplog` assertion passes on the
broken version, which is exactly how the gap shipped.

Not armed prints exactly one of:

- `observability: SENTRY_DSN unset; Sentry disabled for macro-api` → the env
  line is missing or the unit was not restarted after adding it.
- `observability: sentry_sdk unavailable (...)` → the pip step has not landed
  yet; the next `macro-update` tick fixes it (`/usr/local/bin/macro-update` to
  force one).
- `observability: sentry init failed (...)` → malformed DSN.

**In all three cases `/api` keeps serving.** That is the whole design
constraint: observability may go dark, but it may never take the API with it.

---

## Send a test event

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'set -a; . /etc/macro-api.env; set +a; /opt/macro-api/.venv/bin/python - <<PY
import sentry_sdk, os
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], environment="production")
sentry_sdk.capture_message("macro-api sentry smoke test")
sentry_sdk.flush(5)
print("sent")
PY'
```

It lands in the Sentry issue stream within a few seconds.

---

## Not yet wired

The **live lanes** (`macro-live-*.service`, `macro-market-memory-*.service`)
are systemd oneshots running out of a *different* venv (`/opt/macro/.venv`,
provisioned by `app/deploy/live-setup.sh`) and reading a different env file
(`/etc/macro-live.env`). They currently report only to the journal. They can
adopt the same arm — `init_sentry("macro-live-breadth")` and a `SENTRY_DSN` in
`/etc/macro-live.env` — but that means adding `sentry-sdk` to the lane venv and
accepting per-lane ingest volume, which is a separate decision. Deliberately
out of scope here.

The **nightly pipeline** runs on the self-hosted Mac Studio via GitHub Actions,
not on the VPS. Its failures already surface as red Actions runs, so it is not
a Sentry candidate.
