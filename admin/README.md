# Mastermind Admin

A control + observability console for the whole Mastermind/Macro stack. It runs in
**two modes**:

- **Local (default):** binds `127.0.0.1`, no auth required — the original
  single-user dev tool for editing `config.yml` and driving GitHub Actions.
- **Deployed:** runs on the VPS behind Caddy at **https://admin.mastermind-x.com**,
  **password-authenticated**, and tracks the entire live site — web analytics,
  registered users, server/service health, uptime, pipeline, cost, and content.

## Run locally

```bash
.venv/bin/python -m admin            # → http://127.0.0.1:8787  (open, localhost-only)
.venv/bin/python -m admin --open     # also open a browser
ADMIN_PASSWORD=secret .venv/bin/python -m admin   # local + login wall
```

Core needs no extra deps beyond the project's `requests` + `pyyaml`. Live Google
Analytics reading is optional (`pip install -r admin/requirements.txt`).

## What it tracks

| Tab | Capability |
|-----|------------|
| **Overview** | One-glance health: pipeline, services up, server load/mem/disk, AI cost, features, analytics. One-click rebuild/redeploy. |
| **Analytics** | **Umami** (privacy-first, cookieless) — the tracking script is live on every page for free. In-panel visitors / pageviews / top pages / countries / referrers + realtime light up when `UMAMI_API_KEY` is set (paid Umami Cloud or self-hosted); otherwise it links out to the dashboard. |
| **Users** | **Supabase** auth roster (Google + email): total / new / active, signups-over-30d sparkline, provider split, recent users. Read via the Management API SQL endpoint with a `sbp_…` PAT — no service-role key needed. |
| **System** | VPS host metrics (CPU load, memory, swap, disk, uptime from `/proc`), **systemd service health** (caddy, macro-api, admin, terminal, mastermind), and an **endpoint uptime board** (all subdomains + `/api/health`). |
| **Health** | `data/run_status.json` pipeline health, per-source status & circuit breakers, per-market dashboard freshness. |
| **Features** | Toggle curated `config.yml` flags. Local mode edits the working tree; **deployed mode commits straight to `main` via the GitHub Contents API** (the VPS clone is read-only/ephemeral). |
| **AI Brief** | Enable/disable Master Brain & AI Desk and set the regenerate-every-N-days interval. |
| **Build & Deploy** | Recent GitHub Actions runs + trigger `daily.yml` / `pages.yml` / `weekly.yml`. |
| **AI Cost** | DeepSeek spend estimate per build / month and cost-vs-interval table. |
| **Content** | Page inventory + sizes, offline broken-internal-link check, live-site uptime probe. |

## Security model (deployed)

- Binds `127.0.0.1` only (the code **refuses** a non-loopback bind); Caddy
  reverse-proxies the public host to it and terminates TLS (real Let's Encrypt —
  `admin.` is grey-cloud / direct-to-origin, not behind Cloudflare).
- Password → **HMAC-signed, stateless session cookie** (HttpOnly, Secure,
  SameSite=Strict). Every `/api/*` route except login/session/health requires it.
- Writes additionally require a **double-submit CSRF token** + same-origin Origin +
  JSON Content-Type.
- **Per-client** login lockout (keyed on the real IP via `X-Forwarded-For`), so an
  attacker can't lock the operator out; atomic reserve closes the concurrency window.
- **Fail-closed:** deployed mode refuses to start without `ADMIN_PASSWORD`.

## Environment (`.env` locally, `/etc/macro-admin.env` on the VPS)

```
# --- deployed-mode auth (REQUIRED when ADMIN_DEPLOYED=1) ---
ADMIN_DEPLOYED=1                 # forced by `--deployed`; enables auth + proxy trust
ADMIN_PASSWORD=...               # the login password (no password → refuses to start)
ADMIN_SESSION_SECRET=...         # persist so signed sessions survive a restart
ADMIN_ALLOWED_HOSTS=admin.mastermind-x.com   # DNS-rebinding allowlist (default)
ADMIN_SESSION_TTL_HOURS=168      # optional (default 7 days)

# --- integrations (all optional; panels degrade with setup steps) ---
SUPABASE_ACCESS_TOKEN=sbp_...    # Supabase PAT → Users panel (Management API SQL)
SUPABASE_PROJECT_REF=...         # optional (defaults to the MarketIntelligence project)
UMAMI_API_KEY=...                # optional → in-panel analytics (paid/self-hosted)
GH_TOKEN=ghp_...                 # Contents:write + Actions:write → flag toggles + rebuild
GA4_PROPERTY_ID / GA4_SA_JSON    # optional legacy GA4 reader
```

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/metabolism` | Metabolism panel: armed state, recent runs, organism state, key pool health. |
| `GET /api/metabolism/history?limit=N` | **Change History:** unified reverse-chronological event feed over all metabolism and Neural Web ledgers (PRs, audit verdicts, reverts, immune heals, governance events, charter proposals, revamp adjudications, lifecycle docket, cycle journals, dispatch freezes, verify outcomes, lessons, parked constructions, heartbeat probes, shadow rehearsals). Returns `{events, sources, phase0, generated_at}`. |

## Deploy to admin.mastermind-x.com

DNS A record `admin → 146.190.142.17` (grey-cloud/DNS-only) is required. Then:

```bash
# 1. land the code on main (the VPS pulls it via the macro-update cron), then on the VPS:
ssh root@146.190.142.17

# 2. create the secrets file (root-only) — NEVER in the repo:
cat > /etc/macro-admin.env <<'EOF'
ADMIN_DEPLOYED=1
ADMIN_PASSWORD=<your password>
ADMIN_SESSION_SECRET=<long random>
SUPABASE_ACCESS_TOKEN=sbp_<...>
EOF
chmod 600 /etc/macro-admin.env

# 3. provision (idempotent): venv deps, systemd unit, Caddy block, start:
bash /opt/macro/admin/deploy/setup-admin.sh
```

`update.sh` (the existing 3-min pull cron) auto-restarts `admin.service` whenever
`admin/` code changes on `main`, so the deployed panel tracks the repo without a
manual redeploy. Secrets live in the untouched `/etc/macro-admin.env`.
