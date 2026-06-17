# Macro Admin

A **local, single-user, localhost-only** control panel for the static Macro
Regime & Sector-Flow dashboard. The public site stays a server-less GitHub Pages
build — this tool runs on your machine, edits the repo's `config.yml`, reads the
committed pipeline state, and drives the GitHub Actions API. It is **never deployed**.

## Run

```bash
.venv/bin/python -m admin            # → http://127.0.0.1:8787
.venv/bin/python -m admin --open     # also open a browser
.venv/bin/python -m admin --port 9000
```

The core needs **no extra dependencies** (stdlib `http.server` + `requests` + `pyyaml`,
all already in the project). Live Google Analytics reading is optional:

```bash
.venv/bin/pip install -r admin/requirements.txt
```

## What it does

| Tab | Capability |
|-----|------------|
| **Overview** | Health, AI-brief schedule, cost & feature snapshot; one-click rebuild/redeploy. |
| **Features** | Toggle curated `config.yml` flags (AI brief, AI desk, notifications, news, data sources, dashboards). Edits are **surgical line edits** — every comment is preserved. ON-but-missing-secret flags are flagged as inert. |
| **AI Brief** | Enable/disable Master Brain & AI Desk and set the **regenerate-every-N-days** interval (1–7). Shows each lens's last-generated time, model, and degrade status. |
| **Traffic** | GA4 (`G-BZTZ9W1BBB`) — live real-time active users, 7-day sessions/users/pageviews, top pages & countries. Degrades to setup instructions until a service account is configured. |
| **Build & Deploy** | Recent GitHub Actions runs (status/conclusion) + trigger `daily.yml` / `pages.yml` / `weekly.yml`. |
| **Health** | `data/run_status.json` pipeline health, per-source status & circuit breakers, per-market dashboard freshness. |
| **AI Cost** | Estimated DeepSeek spend per build / month and a cost-vs-interval table. Estimate only — the pipeline logs no token usage. |
| **Content** | Page inventory + sizes, offline broken-internal-link check, live-site uptime probe. |

## How changes go live

The site is rebuilt from **`origin/main`**. Toggling a flag edits the working-tree
`config.yml` immediately, but it only takes effect once it's committed to `main` and a
build runs:

1. Toggle / set an interval → a banner shows "config.yml changed (not yet live)".
2. **Commit & push to main** (enabled only when you're on a `main` tracking branch), or
   commit locally and push from your main checkout.
3. **Rebuild & deploy now** (Build tab) dispatches `daily.yml` to regenerate the site
   with the new config. (`pages.yml` only redeploys the already-committed `site/`.)

## Secrets / credentials (local `.env`)

Read from `<repo>/.env` (gitignored), same convention as `lib/config.py`:

```
GH_TOKEN=ghp_...                 # fine-grained PAT, Actions: Read+Write — for rebuild/deploy
GA4_PROPERTY_ID=123456789        # numeric GA4 property id (NOT the G-XXXX measurement id)
GA4_SA_JSON=/abs/path/sa.json    # GA4 Data API service-account key (Viewer on the property)
```

Run status loads without a token (public repo); only **dispatching** a workflow needs `GH_TOKEN`.

## Safety

- Binds to `127.0.0.1` only.
- Config edits never round-trip YAML (comments preserved); writes are atomic.
- Pushing to the live branch and dispatching workflows require an explicit confirm.
- China: GA4 is blocked by the Great Firewall, so mainland traffic is undercounted —
  the Traffic panel is provider-pluggable so Baidu Tongji can be added later.
