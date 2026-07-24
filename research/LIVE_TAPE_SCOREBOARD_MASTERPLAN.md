# Live tape + compact breadth scoreboard — masterplan

Status: CHARTERED 2026-07-24 (operator session: 同花顺 screenshot reference).
Extends `research/LIVE_DATA_ARCHITECTURE.md` (3-tier model) and executes the
`research/LIVE_DATA_POLYGON.md` §3 websocket upgrade seam. Three phases, three PRs.

## §0 ACCEPTANCE GATES

**Phase 1 (futures tape + websocket relay) — not done unless:**
1. macro.html index strip shows EXACTLY six tiles: ES=F, NQ=F, YM=F, RTY=F,
   ^TNX (displayed as 10Y yield %, delta in bps), DX-Y.NYB (DXY). SPY/QQQ/DJI/RUT
   spot tiles GONE from the strip (the deep-dive dialogs may keep spot indices).
2. With macro-api running, the six tiles tick via `/ws/tape` (server-fanout
   websocket) — sub-5s from upstream tick to DOM patch during futures hours; the
   page NEVER breaks when the ws is down (fallback ladder: ws → worker/snapshot
   polling → baked numbers, each tier honestly stamped, `basis` law §6).
3. Same-origin wss through Caddy (China path parity with the `/sb` proxy);
   deploy runbook covers Caddy route + macro-api restart + rollback.
4. Upstream decoder is a pure function with unit tests (recorded frames), and a
   dead-upstream server fallback (REST poll via engine.live_quotes at ≤15s,
   basis honestly downgraded) keeps the socket serving.
5. Zero regression on every other live surface: `live.js` polling contract,
   `quotes.json` schema, worker contract, basket tape, landing overrides untouched.
6. Render tests pin the six tiles + the ^TNX display transform; visual crops
   (light+dark+zh) in the PR body. First-pass flagship strip → no self-merge.

**Phase 2 (live breadth + scoreboard revamp) — not done unless:**
1. Advancers/decliners for the S&P 1500 update ≤2 min behind the (15-min-delayed)
   feed during RTH, from ONE full-market Polygon snapshot joined to nightly-baked
   per-name thresholds (MA50/MA200/52w bands) — no per-symbol fan-out, no new
   entitlement assumed, delay labeled on-surface ("≈15-min delayed").
2. us_stocks scoreboard is REBUILT as compact glance cards in the macro.html mx5
   idiom (small containers, one number + one plain-word stance each, 同花顺-style
   single adv/dec bar with counts at the ends); click opens the detailed panel
   (current deep tables demoted there). Size & Style REMOVED from the dashboard
   (operator ruling 2026-07-24 — data stays in stores; no user-facing surface).
3. Design-spec-first: exact markup/CSS pinned by main-loop/designer BEFORE any
   builder assembles (house Design lane law); reference = 同花顺 A股 大盘 screen
   (single thin bar, green left count 跌/red right count 涨 in CN convention —
   OURS uses house up/down tokens, which flip correctly under zh).
4. Live breadth JSON is display-tier ONLY: no engine store writes, no ledger
   advancement, nightly remains the sole forward-ledger advancer.

**Phase 3 (macro signal reactivity) — not done unless:**
1. The overlay fast-leaves cadence moves from GH-cron (*/30, best-effort) to the
   persistent poller host at ≤5 min during RTH, with the same PIT stamps.
2. The macro hero regime chip states its own freshness (baked date + overlay
   as-of + delay) in one honest stamp; slow-brain (regime/quad) stays nightly BY
   DESIGN (hysteresis law, LIVE_DATA_ARCHITECTURE tier S) — no live regime flips.

## §1 Current-state audit (2026-07-24, this session)

- Browser `live.js` polls every 60s BUT `config.yml live.quotes_worker_url = ""`
  — the Cloudflare Worker tier was never armed, so pages ride the static
  `site/live/quotes.json` snapshot from `.github/workflows/live-quotes.yml`
  (cron `*/5`, best-effort ⇒ operator-perceived "5–10 min updates").
- macro.html strip (`dashboard.html.j2` ~L9903): SPY/QQQ/DJI/RUT spot tiles +
  ES=F/NQ=F futures tiles — mixed spot/futures, the operator kill target.
- `build_live_overlay` (fast leaves → `site/live/overlay.json`) runs in
  `intraday-fastpath.yml` at */30 on the 15-min-delayed Polygon STANDARD feed.
  Slow brain (regime/quad/conviction) is nightly-only BY DESIGN.
- macro-api = FastAPI (`app/main.py`) behind Caddy on the VPS ⇒ native
  websocket capability; persistent-loop precedent = `scripts/live_flow_poller.py`
  (RTH loop, `/etc/macro-api.env`). Same-origin proxy precedent = `/sb` (GFW).
- Polygon plan = STANDARD (15-min delayed REST; websocket NOT included; stocks
  ws starts at Starter+; futures/indices ws are separate products) ⇒ the
  six-instrument tape (futures + index + yield) cannot come from our Polygon
  tier; breadth CAN (one full-market REST snapshot call).

## §2 Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Tape = ES=F, NQ=F, YM=F, RTY=F + ^TNX + DX-Y.NYB | Operator fixed the four futures; ratified their DXY+10Y instinct for the two others: dollar + long rates are the two macro transmission channels; VIX already owns a macro.html panel; gold/crude live on commodity surfaces. |
| D2 | Upstream = Yahoo streamer wss (keyless), relayed server-side | Only keyless source covering futures+index+yield in one socket; UNOFFICIAL ⇒ mitigations: pure decoder + recorded-frame tests, auto-fallback to REST polling (§0.4), page-level fallback ladder (§0.2). Polygon ws (if ever bought) slots behind the same relay for stocks — the LIVE_DATA_POLYGON §3 seam is honored: consumers never change. |
| D3 | Relay home = macro-api `/ws/tape`, same-origin wss via Caddy | One upstream connection fans out to all clients; China-reachable (same-origin like `/sb`); no browser ever talks to the unofficial upstream directly. |
| D4 | ^TNX shown as percent (quote/10), delta in bps; off-hours stale chip | ^TNX streams cash hours only; honesty law — never fake overnight liveness; futures tiles carry the overnight read. |
| D5 | Size & Style leaves the dashboard entirely | Operator ruling ("not a useful metric"); breadth %>50d keeps feeding the regime model upstream — engine untouched. |
| D6 | Live breadth = full-market snapshot join, NOT per-name websocket | 1500-symbol ws is entitlement-gated and pointless at 15-min delay; one REST call + nightly threshold join gives 同花顺-grade adv/dec at honest delay for ~zero cost. |
| D7 | Breadth poller lives beside live_flow_poller on the VPS/Mac loop host | GH cron floor (5 min, best-effort) can't hold a 1–2 min cadence; loop-process precedent exists. |

## §3 Phase 1 build spec (one PR)

1. **Tiles** (`templates/dashboard.html.j2` macro strip): six `mx5-mkt-tile`s in
   D1 order, existing chrome, no sparklines (futures precedent), labels
   EN/ZH: S&P fut/标普期货, Nasdaq fut/纳指期货, Dow fut/道指期货,
   Russell fut/罗素期货, 10Y yield/十年期收益率, Dollar DXY/美元指数.
   `data-sym` = feed keys above; ^TNX tile gets `data-fmt="tnx"` (JS divides by
   10, suffix %, delta ×10 bps label).
2. **Relay** (`app/main.py` + new `app/tape.py`): `GET /ws/tape` websocket.
   Background task: connect upstream, subscribe six syms, decode (vendored
   minimal protobuf field map, pure fn), cache last quote per sym, broadcast
   `{sym, price, chgPct, ts, basis}`; snapshot-on-connect; 20s heartbeat;
   exponential reconnect; dead-upstream ⇒ engine.live_quotes REST poll ≤15s
   with `basis:"poll"`. No key material involved.
3. **Client** (`templates/live.js` + paired `site/live.js` via the sync tool):
   if any `[data-sym]` on page matches tape syms, open same-origin
   `wss://…/ws/tape`; patch via the EXISTING nb-px/nb-chg DOM contract; ws
   error/close ⇒ do nothing (polling path already runs); `data-fmt="tnx"`
   transform; never double-patch (ws quote wins only when fresher ts).
4. **Caddy + runbook**: `docs/live_tape_runbook.md` — Caddy `/ws/tape` route
   (websocket upgrade), macro-api restart, verify (wscat), rollback (remove
   route ⇒ page auto-degrades to polling). Also document ARMING the dormant
   Cloudflare Worker (`live.quotes_worker_url`) as the 60s fallback tier —
   deploy is an operator step, config flip ships separately after deploy.
5. **Tests**: decoder unit (recorded frames incl. junk/partial), tape.py cache/
   fallback logic, FastAPI ws smoke (TestClient), dashboard render pins (six
   tiles, data-fmt, no SPY/QQQ/DJI/RUT in strip), live.js tnx-transform unit if
   a JS test lane exists (else render-pinned attribute only).
6. **Paired-file law**: live.js is a templates/↔site/ PAIR — sync BOTH, never
   whole-tree `--fix` (memory: mobile-chat-fab-stack trap).

## §4 Phase 2 spec (breadth live + scoreboard revamp — SEPARATE PR, design-first)

Engine lane: `scripts/live_breadth_poller.py` (loop, RTH), one Polygon
full-market snapshot → join `data/` nightly per-name thresholds (close vs MA50/
MA200, 52w hi/lo bands, prev close) → `site/live/breadth.json`
`{asof, delay_min, tiers: {large|mid|small: {adv, dec, unch, pa50, pa200,
net_nh}}, comp: {...}}` (schema mirrors the baked breadth_panel keys). Surface
lane AFTER design-spec pinned: compact cards idiom from macro.html; adv/dec
single bar w/ end counts (同花顺 ref); % gauges; internals plain-word chip;
click ⇒ detail dialog housing today's full tables; Size&Style removed (D5).
live.js merges breadth.json on its existing 60s tick — no new poll loop.

## §5 Phase 3 spec (macro signal reactivity)

Move `build_live_overlay` invocation onto the poller host at 5-min RTH cadence
(GH lane stays as backstop); add freshness stamp unification on the macro hero
(baked + overlay as-of in ONE chip, Law 4 one-footnote). Slow-brain stays
nightly (tier-S hysteresis law) — reactivity means honest fast-leaf freshness,
NOT live regime flips. Any proposal to flip regime/quad intraday must reopen
LIVE_DATA_ARCHITECTURE tier law first (do not bury it in a build PR).

## §6 Epistemics / honesty rails (all phases)

- Every live number carries source basis + delay; "live" label ONLY for
  basis=trade ticks; poll/delayed bases say so (dtp token precedent).
- Live artifacts are display-tier: no store writes, no ledger advancement,
  no signal-engine inputs (LIVE ledger law: intraday lanes discard data/ writes).
- Nulls/dead feeds render as stale-stamped baked numbers, never hidden.
