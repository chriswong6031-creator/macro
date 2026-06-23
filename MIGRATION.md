# Live web-app migration — runbook

**Goal:** make signals update *during market hours* (not just the 22:40 UTC nightly
run), host **Mastermind** on a real server, and stay reachable from **mainland China**.

**TL;DR:** the hard part is already built and merged. The live-overlay engine, the
browser enhancer (`site/live.js`), the Cloudflare quote Worker, and the design doc
(`research/LIVE_DATA_ARCHITECTURE.md`) are all on `main`. What's missing is **purely
deployment** — turning the dormant layer on and standing up one Hong Kong box. No
engine rewrite, no `live.yml` (deliberately rejected — see the arch doc).

---

## 0. What already exists vs. what's missing

| Piece | Status |
|---|---|
| `engine/live_overlay.py`, `engine/live_quotes.py` (fast-leaf recompute + quote fetch) | ✅ on `main` |
| `scripts/build_live_overlay.py` → writes `site/live/overlay.json` | ✅ on `main` |
| `site/live.js` (browser enhancer; polls Worker + overlay, **display-only**) | ✅ on `main`, wired into dashboard/china/hk |
| `worker/quotes.worker.js` (+ `worker/DEPLOY.md`) — Cloudflare quote proxy | ✅ on `main`, **not deployed** |
| `live:` config block (`config.yml`) | ✅ on `main`, `quotes_worker_url: ""` (dormant) |
| `scripts/check_live_worker.py` (verifier) | ✅ on `main` |
| **A scheduler that runs `build_live_overlay.py` intraday** | ❌ **missing** — the gap; addressed by the HK-VPS cron in §4 |
| `scripts/quotes_server.py` — same-origin, China-reachable quote service (Worker alt) | ✅ **added on this branch** (tested) |
| Cloudflare Worker deployed + `LIVE_QUOTES_WORKER_URL` set | ❌ infra step (or use the quotes server instead) |
| Mastermind auth (`app/auth.py`, password gate over UI + API + SSE) | ✅ **added** (committed in the Mastermind repo) |
| **A host for Mastermind + the fast loop** | ❌ infra — the HK VPS (§4–§5) |

### Why signals are frozen today
The static site is rebuilt once/day by `daily.yml` (22:40 UTC). The nightly batch is
the **slow brain** (regime, conviction, allocation) and is *hysteresis-gated by design*
— it must not flip on intraday noise. The **fast brain** (technicals, RS, extension,
the live-vs-cone divergence flag) is cheap to recompute but nothing runs it intraday.

### The three liveness layers (from `research/LIVE_DATA_ARCHITECTURE.md`)
1. **Live prices in the browser** — `live.js` calls the **Worker** directly every
   `poll_seconds` (60s). Patches price text + freshness dot. *No server, no commits.*
2. **Live recomputed signals** — `build_live_overlay.py` runs on a cron, writes
   `site/live/overlay.json` (recomputed technicals + divergence chips + live-marked
   allocations). `live.js` also reads this. *Needs a scheduler.*
3. **Live GEX/options** — Phase 4, deferred (entitlement-gated).

**What moves intraday:** prices, per-name technicals/RSI/MACD, RS, extension, breadth,
vol cone, divergence chips, the "act-now" verb. **What deliberately does NOT:** regime
quad, conviction ranks, theme scores, directional leans (hysteresis — a feature).

---

## 1. Target architecture — one Hong Kong VPS

```
GitHub Actions (UNCHANGED)
  daily.yml @ 22:40 UTC: collect (~100m) + engine/render (~42m)
  → commits data/ + site/ to main          (free CI compute)
                  │  git pull (cron, ~23:30 UTC)
                  ▼
Hong Kong VPS  (China-reachable, no ICP)
  • macro checkout, refreshed nightly via git pull
  • FAST LOOP: cron */2 during market hours → build_live_overlay.py
       → site/live/overlay.json
  • nginx serves site/ + overlay.json on your domain (HTTPS)   ← PUBLIC
  • /quotes endpoint (Worker logic) for China-reachable live prices
  • Mastermind: uvicorn on localhost, BEHIND AUTH               ← PRIVATE
       └ snapshot job → pushes read-only JSON to the public site (already built)
                  │  browser polls overlay.json / quotes every 60s
                  ▼
  Browser: static pages + live.js → live prices + divergence chips
```

The heavy nightly build **stays in GitHub Actions** (free, already works). The HK box
only does the seconds-long fast loop + the mostly-idle Mastermind, so it stays small.

**Key coupling:** both the fast loop and Mastermind read the macro `data/` store
(`data/regime/latest.json`, `masterminds_latest.json`, cached closes, `site/stockdata/*.json`).
So they **co-locate** with a macro checkout that `git pull`s the nightly outputs.

---

## 2. Costs

| Item | Recommendation | Cost |
|---|---|---|
| Server | **Oracle Cloud Always-Free, Hong Kong** (2 OCPU/12 GB Arm). Fallback: **Tencent Lighthouse HK** | $0 / ~$4–10/mo |
| Domain + HTTPS | any registrar + Let's Encrypt (certbot) | ~$12/yr / $0 |
| US live prices | **Yahoo spark** (free, 15-min) works out-of-box; upgrade: Polygon/Massive Starter or Alpaca free SIP | $0 → $29/mo |
| HK + A-share prices | **Tencent `qt.gtimg.cn` + Sina `hq.sinajs.cn`** (free, keyless, need `Referer`); Yahoo HK=15min, SH/SZ=30min | $0 |
| LLM (Mastermind brain) | keep Claude subscription (`BOT_LLM_BACKEND=cli` + `claude` CLI on box) or metered `api` | existing / metered |
| CDN for China | **not needed** at this traffic; if ever: Tencent EdgeOne (ICP-free overseas path). **Do NOT** rely on Cloudflare for China. | $0 |

**Bottom line:** **$0–10/mo + ~$12/yr** on free feeds; ~$40/mo with paid market-data SLAs.
**No ICP license** (stay offshore in HK — a foreign individual can't realistically get
one and doesn't need one outside the mainland).

---

## 3. Phase 1 — turn on browser live prices (zero server, ~30 min)

Gives every user (outside China) live ticking prices on the *current* GitHub Pages site.

1. Deploy the Worker (needs your Cloudflare account + a Polygon/Massive key — Yahoo
   fallback works even without it):
   ```bash
   cd worker
   npm install            # wrangler
   wrangler login
   wrangler secret put POLYGON_API_KEY     # optional; omit → Yahoo-only
   wrangler deploy                          # prints https://<name>.<acct>.workers.dev
   ```
   See `worker/DEPLOY.md` for the full procedure.
2. Turn it on **without a code edit**: set the GitHub repo **Variable**
   `LIVE_QUOTES_WORKER_URL` to the deployed URL
   (Settings → Secrets and variables → Actions → Variables). `daily.yml` already reads
   `vars.LIVE_QUOTES_WORKER_URL` and bakes it into `site/live_config.js`. The next
   build → cards go live. (Or set `config.yml → live.quotes_worker_url` and commit.)
3. Verify: `python scripts/check_live_worker.py` (resolves the URL, hits `/health`
   and `/quotes`).

**Caveat:** the Worker is **unreliable from mainland China** (GFW blocks ECH to
Cloudflare + `workers.dev`). China users get live prices via the HK origin in Phase 2.

---

## 4. Phase 2 — Hong Kong VPS: live signals + China-reachable origin

1. **Provision** the HK VM (Oracle Free HK or Tencent Lighthouse HK). Install:
   ```bash
   sudo apt update && sudo apt install -y python3.12 python3.12-venv git nginx certbot python3-certbot-nginx
   ```
2. **Checkout + venv:**
   ```bash
   git clone https://github.com/chriswong6031-creator/macro.git ~/macro && cd ~/macro
   python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
   ```
3. **Nightly pull** (after the 22:40 UTC build lands) — `crontab -e`:
   ```cron
   30 23 * * 1-5  cd ~/macro && git pull --ff-only origin main >> ~/macro/pull.log 2>&1
   ```
4. **Fast loop** — recompute the overlay every 2 min during US market hours
   (13:30–20:00 UTC). `build_live_overlay.py` is fail-safe (any feed down → emits
   `stale`, no crash). Add `POLYGON_API_KEY`/`MASSIVE_API_KEY` to the env for US
   real-time, else it uses free Yahoo:
   ```cron
   */2 13-20 * * 1-5  cd ~/macro && .venv/bin/python -m scripts.build_live_overlay >> ~/macro/live.log 2>&1
   ```
   (Add Asia-hours rows later for live HK/A-share overlay.)
5. **Serve the site** via nginx (`/etc/nginx/sites-available/macro`):
   ```nginx
   server {
     server_name dash.example.com;
     root /home/ubuntu/macro/site;
     location / { try_files $uri $uri/ =404; }
     # overlay.json must never cache-pin — it's the live file
     location = /live/overlay.json { add_header Cache-Control "no-store"; }
   }
   ```
   Then `sudo certbot --nginx -d dash.example.com` for HTTPS. The HK origin is
   reachable from mainland China without ICP.
6. **China-reachable live prices** — run the same-origin quote micro-service
   (`scripts/quotes_server.py`, shipped on this branch) instead of relying on the
   Cloudflare Worker (which the GFW blocks). It mirrors the Worker's wire contract
   exactly and reuses `engine.live_quotes`, so `live.js` is unchanged:
   ```cron
   # behind nginx; restart via systemd in practice
   @reboot  cd ~/macro && .venv/bin/python -m scripts.quotes_server --host 127.0.0.1 --port 8787
   ```
   ```nginx
   location /quotes { proxy_pass http://127.0.0.1:8787; }
   ```
   Then set `config.yml → live.quotes_worker_url` (or the repo var
   `LIVE_QUOTES_WORKER_URL`) to **your HK origin** (e.g. `https://dash.example.com`)
   — `live.js` polls `<origin>/quotes` with no Cloudflare dependency. Verify with
   `python scripts/check_live_worker.py`. (Add a `POLYGON_API_KEY` to this service's
   env for US real-time; otherwise it serves free Yahoo quotes.)

**Result:** signals visibly update during market hours, served from a China-reachable
origin, no commit churn.

---

## 5. Phase 3 — host Mastermind (PRIVATE, auth required)

> ✅ **Auth has been added** — `app/auth.py` (shipped) gates the whole app (UI +
> every `/api` + the SSE stream) behind a single password with an HMAC-signed
> session cookie. It is **opt-in**: set `MASTERMIND_PASSWORD` to turn it on (unset =
> disabled, fine for localhost-only). Set it before exposing the box. A bearer token
> (`MASTERMIND_AUTH_TOKEN`) is available for the snapshot-push / uptime clients.
> Even so, prefer keeping Mastermind **off the public internet** (localhost + the
> options below); the password is defence-in-depth, not an invitation to expose it.

1. **Co-locate** with the macro checkout. Mastermind reads the engine + `data/` via
   `vendor/macro`. Locally that's a symlink; on the box point it at `~/macro`:
   ```bash
   git clone <mastermind-remote-or-rsync> ~/mastermind && cd ~/mastermind
   ln -s ~/macro vendor/macro        # so it reads the freshly-pulled data store
   python3.12 -m venv .venv && . .venv/bin/activate && pip install -e .
   ```
   (Mastermind has no git remote today — `rsync` it up or add a private remote.)
2. **Env:** `CLAUDE_CODE_OAUTH_TOKEN` (or `ANTHROPIC_API_KEY` + `BOT_LLM_BACKEND=api`),
   `QUIVER_USER`/`QUIVER_PASS`, and **`MASTERMIND_PASSWORD`** (turns on the auth gate —
   see `.env.example`). For the `cli` backend, install the `claude` CLI on the box.
   State is ~10 MB of JSON + `data/scheduler.sqlite` — persist `~/mastermind/data/`.
3. **Run** under systemd, bound to **localhost** (not 0.0.0.0):
   ```ini
   # /etc/systemd/system/mastermind.service
   [Service]
   WorkingDirectory=/home/ubuntu/mastermind
   ExecStart=/home/ubuntu/mastermind/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
   Restart=always
   EnvironmentFile=/home/ubuntu/mastermind/.env
   [Install]
   WantedBy=multi-user.target
   ```
   `uvicorn` runs with **no `--reload`** — restart the service to pick up code changes.
   Its in-process APScheduler already fires the daily books + market-hours fills + the
   snapshot push (which keeps publishing the read-only Mastermind panel to the public
   site).
4. **Auth** — the **app-level password gate is built in** (`app/auth.py`): set
   `MASTERMIND_PASSWORD` and it's on. For defence-in-depth add a network gate too:
   - **Tailscale** (simplest for solo use): join the box to your tailnet, reach
     Mastermind at its tailnet IP. Nothing public.
   - **nginx + HTTPS** vhost proxying `127.0.0.1:8000` (set `MASTERMIND_COOKIE_SECURE=1`
     so the session cookie is marked Secure behind TLS termination).
   - **Cloudflare Access** in front (non-China admin use is fine).
   The public never gets the controls — only the read-only snapshot it already pushes.

---

## 6. Decisions you still need to make

- **Host:** Oracle Free HK (cheapest, signup friction) vs Tencent Lighthouse HK
  (~$5/mo, turnkey) vs managed PaaS (Render Singapore, not HK).
- **Market-data tier:** free (Yahoo/Tencent/Sina, 15–30 min) vs Polygon Starter
  ($29) for US real-time.
- **Mastermind reachability:** Tailscale (just you) vs Basic-Auth (a few users).
- **Public site origin:** move to the HK VPS (China-reachable) vs keep GitHub Pages
  (global, flaky from China) + HK box only for overlay/quotes/Mastermind.
- **Domain name** for the HK origin.

## 7. Sequencing

Phase 1 (Worker) is independent and reversible — do it first for an instant win
everywhere except China. Phase 2 (HK VPS) delivers the China-complete live signals.
Phase 3 (Mastermind) is gated on the **auth** decision. The nightly GitHub Actions
build never changes.
