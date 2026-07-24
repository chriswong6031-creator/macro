# Live Tape runbook (Phase 1 — `/ws/tape`)

Operator deploy + verify + rollback for the macro.html six-instrument futures
tape (`research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md` Phase 1).

**What ships in this PR (code only):** the tiles (`templates/dashboard.html.j2`),
the relay (`app/tape.py` + `app/tape_decode.py`, mounted in `app/main.py`), the
client (`templates/live.js` ↔ `site/live.js`), and the config flag
(`config.yml live.ws_tape_enabled`). **What the operator must do to arm it:** one
Caddy route + a macro-api restart (below). Until then the page is fully correct —
the tiles just ride the existing `live.js` polling fallback (worker/snapshot →
baked numbers), never blank.

---

## Architecture (one glance)

```
browser (macro.html)                     macro-api (FastAPI, 127.0.0.1:8000)
  live.js  ──wss://<host>/ws/tape──►  Caddy ──► GET /ws/tape (app/tape.py)
                                                     │  one process-wide TapeHub
                                                     ▼
                                          wss://streamer.finance.yahoo.com
                                          (keyless, unofficial; base64 protobuf)
                                                     │  dead upstream >60s ▼
                                          engine.live_quotes REST poll (≤15s)
                                          broadcast basis:"poll" (downgraded)
```

- ONE upstream connection per macro-api process fans out to every browser.
- No browser ever talks to Yahoo directly (same-origin = China-reachable, like
  the `/sb` Supabase proxy; no CORS; no key material anywhere in this lane).
- Fallback ladder (page never breaks): **ws → live.js polling → baked numbers**,
  each tier honestly freshness-stamped. `basis` is `quote` (live upstream tick)
  or `poll` (REST fallback) — never a fabricated "live".

---

## 1. Caddy route (`app/deploy/Caddyfile`)

Add a WebSocket route to the macro-api upstream in the **www host block**, next
to the existing `reverse_proxy /api/* 127.0.0.1:8000`. Caddy upgrades WebSocket
connections transparently (it forwards `Upgrade`/`Connection` headers), so the
route is a one-liner mirroring the `/api/*` precedent:

```caddyfile
	# Live Tape websocket — same-origin relay to macro-api (app/tape.py).
	# China-reachable (same-origin, like the /sb Supabase proxy). Placed BEFORE
	# the Site Access Gate handle so a ws upgrade is never routed through the
	# HTML gate matcher.
	reverse_proxy /ws/tape 127.0.0.1:8000
```

Put this line immediately after the `reverse_proxy /api/* 127.0.0.1:8000` line
(≈L63) so it is matched before the `@gate_html` / `@reg_html` HTML matchers. The
gate matchers only match `*.html` + `/`, so `/ws/tape` would fall through to
`file_server` (404) without this route.

Reload Caddy after editing:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy      # graceful; existing connections survive
```

## 2. macro-api restart

The relay is a background task started on FastAPI startup, so the new code needs
a process restart (a reload is not enough — the upstream task must (re)spawn):

```bash
sudo systemctl restart macro-api      # app/deploy/macro-api.service
journalctl -u macro-api -n 40 --no-pager | grep -i tape
# expect: "tape hub started (6 symbols)" and, during trading hours,
#         "tape: upstream connected, subscribed ('ES=F', 'NQ=F', ...)"
```

No new env vars, no secrets. The relay uses the `websockets` client already
bundled with `uvicorn[standard]` (in `app/requirements.txt`) — if that import is
ever absent the relay logs a warning and serves the REST-poll fallback only; it
never crashes the API.

## 3. Verify

**Server side** — hit the socket directly with `websocat` (or `wscat`):

```bash
# from the VPS (bypasses Caddy):
websocat ws://127.0.0.1:8000/ws/tape
# through Caddy / from anywhere:
websocat wss://www.mastermind-x.com/ws/tape
```

Expected first frames = a **snapshot-on-connect** (one JSON per cached symbol),
then live deltas, then a heartbeat every ~20s if idle:

```json
{"sym":"ES=F","price":5432.25,"chgPct":0.85,"ts":1753380000000,"basis":"quote"}
{"sym":"NQ=F","price":19875.5,"chgPct":-0.42,"ts":1753380000123,"basis":"quote"}
...
{"type":"heartbeat","ts":1753380020000}
```

- `basis:"quote"` = live upstream tick. `basis:"poll"` = REST fallback (upstream
  was silent >60s) — honestly downgraded, the tile will NOT show the green pulse.
- Outside futures hours the cache may be empty on first connect (no snapshot
  frames) until the first upstream tick / poll lands — the browser keeps the
  baked numbers meanwhile. `^TNX` streams cash hours only; off-hours it stays
  stale-stamped (never a faked overnight liveness).

**Browser side** — open `https://www.mastermind-x.com/macro.html`, DevTools →
Network → WS: one `/ws/tape` connection, frames flowing; the six MARKETS tiles
tick; the `^TNX` tile reads e.g. `4.25%` with a `+3 bps` delta.

## 4. Rollback

Two independent levers, both no-code:

1. **Ops kill switch (fastest, no Caddy change):** set
   `config.yml live.ws_tape_enabled: false` and rebuild `live_config.js`
   (`python -m scripts.build_live_overlay` writes it, or the nightly build). The
   browser stops opening `/ws/tape`; tiles fall back to polling. `LIVE_WS_TAPE`
   can also be overridden per-build; the default is ON.
2. **Remove the Caddy route** (`reverse_proxy /ws/tape …`) and reload Caddy. The
   browser's ws connect then fails; `live.js` closes the socket silently and the
   polling path (already running) carries the tiles. No page redeploy needed —
   the fallback ladder degrades automatically.

Either way the page keeps working; the tape just loses its sub-5s cadence and
reverts to the ~5-min snapshot cadence.

---

## Appendix: the DORMANT Cloudflare Worker fallback tier (operator step, separate PR)

The polling fallback under the tape is only as fast as its quote source. Today
`config.yml live.quotes_worker_url = ""`, so the poller rides the static
`site/live/quotes.json` snapshot (GitHub Action `live-quotes.yml`, cron `*/5`,
best-effort ⇒ ~5-min updates). Deploying `worker/quotes.worker.js` (see
`worker/DEPLOY.md`) and setting `live.quotes_worker_url` to its URL upgrades the
**polling** tier from ~5-min to ~60s — a strictly better floor beneath the ws.

That deploy is an **operator step** and the config flip ships in its own PR
**after** the Worker is live — do NOT set `quotes_worker_url` in the Live Tape
PR (a non-empty URL with no deployed Worker would make every poll tick fail over
to the snapshot for one extra round-trip). The Worker tier is independent of the
`/ws/tape` relay; arming it strengthens the fallback, it does not gate the tape.
