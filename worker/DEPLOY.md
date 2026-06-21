# Turn on live (intraday) prices — deploy the quotes Worker

The dashboard is a static GitHub Pages site, so it can't hold a secret or proxy a quote
feed. This tiny Cloudflare Worker (`quotes.worker.js`) is the one piece that makes browser
**live prices** work: it keeps the Polygon key server-side, routes US symbols → Polygon and
everything else → Yahoo (keyless), and edge-caches each response. Until it's deployed and its
URL is wired in, the live layer stays **dormant** (the site shows nightly closes — no errors).

Everything below is a **one-time, ~5-minute** setup. You only need a (free) Cloudflare account.
A Polygon key is **optional** — without it, US names fall back to Yahoo and live prices still work.

## 1. Deploy the Worker
```sh
cd worker
npx wrangler login                       # opens a browser, authorizes your Cloudflare account
npx wrangler deploy                      # publishes -> https://macro-quotes.<your-subdomain>.workers.dev
npx wrangler secret put POLYGON_API_KEY  # OPTIONAL: paste your Polygon key (skip for Yahoo-only)
```
`wrangler deploy` prints the deployed URL — copy it.

## 2. Verify it works (before relying on it)
```sh
python -m scripts.check_live_worker https://macro-quotes.<your-subdomain>.workers.dev
```
This checks `/health`, the `/quotes` contract, CORS, and price routing, and tells you if the
Polygon key is wired. (Run during US/HK trading hours to see live prices; off-hours it confirms
the contract with 0 quotes.) You can also smoke-test the Worker logic offline: `node quotes.worker.test.mjs`.

## 3. Wire the URL in (turns the layer ON)
Pick **either** path — the next nightly build bakes the URL into `site/live_config.js`, which the
browser `live.js` reads:

- **No-code (recommended):** GitHub → repo **Settings → Secrets and variables → Actions →
  Variables** → New repository variable → name `LIVE_QUOTES_WORKER_URL`, value the deployed URL.
- **In config:** set `live.quotes_worker_url` in `config.yml` to the URL and commit.

To turn it back **off**, clear the variable (or the config value) — the layer goes dormant again,
no code change.

## Notes
- The Worker's edge cache (60s) + the canonical symbol key mean a fan of browsers polling the same
  set costs ~one upstream call/minute — comfortably inside Cloudflare's free tier.
- The Python intraday overlay (`scripts/build_live_overlay.py`, for the Mastermind feed) fetches
  quotes **server-side** with its own key and does **not** need this Worker; the Worker is only for
  **browser** live prices on the static pages.
- The URL is **not** a secret (it's public in `live_config.js`), so a repo *variable* (not a secret)
  is correct. The Polygon key never leaves the Worker.
