# PROPHET LIVE — intraday provisional signals, alerts, and the path to sub-minute

**Program:** `prophet_live` · **Author:** Fable main loop · **Date:** 2026-07-29
**Operator ask:** let Prophet picks surface the same day their conditions form — intraday
detection, user alerts (site now, mobile push later), a lawful pathway for the Mastermind
bot, and richer intraday data for breaking-news content. Assess tick-by-tick honestly.

**One-line architecture:** *two speeds, one engine* — the nightly build arms a per-name
trigger pack; a light intraday lane re-runs the SAME close-only admission gate with the
live price as a provisional close; the nightly run stays the sole confirmer, grader, and
ledger advancer. No second signal engine is ever built.

---

## §0 ACCEPTANCE GATES — binding on every build spawn (inline them in prompts)

- **G0.1 Parity or nothing (P0):** the evaluator, fed yesterday's actual close as the
  "live" price, must reproduce the nightly gate verdict for every ARMED name.
  **What is gated is `signal_gate.is_buyable`** — that boolean is the whole admission
  question and the only thing the intraday states turn on. `tier` / `tier_cascade`
  ride along as as-of-close CONTEXT for display and are not part of the parity
  assertion (the earlier "is_buyable + tier, bit-for-bit" wording promised more than
  the evaluator consumes or the pack can check). Parity is proven by re-running the
  REAL gate at the published prices, not by re-reading the pack's own numbers. A
  parity test is in the PR and in CI; any divergence is a build blocker, not a
  tolerance, and an unverified level is withheld rather than published.
- **G0.2 Ledger law (P0):** the intraday lane writes NO `data/` paths. Events go to the
  runtime spool (R2) + live artifacts only; the nightly reconciler is the only writer of
  `data/prophet_live/`. Test-pinned (grep-level: evaluator module imports no `data/`
  writers; workflow has no `git add data/`).
- **G0.3 Honest degradation (P0/P1):** stale or missing quotes ⇒ the affected names show
  `state:"dark"` with a reason; the artifact never carries a guessed state. Global
  freshness stamp + per-name `delay_min` in every payload (house `delayMin` convention).
- **G0.4 No graded-board contamination (all phases):** provisional states NEVER alter
  `us_standouts.json` membership, `us_board_ledger`, or the track record. Presentation
  tier only (DNR §1 Top-setups row is the governing kill). CI keeps the existing
  grade-population tests green untouched.
- **G0.5 Debounce (P1):** a FORMING state requires 2 consecutive passes above trigger
  (or equivalent price-buffer hysteresis); a single print never flips a public state
  (1-tick escalation kill, CSP-R2).
- **G0.6 Language law (P1):** user copy = "forming / crossing / settles at tonight's
  close / faded" — never "fired/confirmed" pre-close, never falsifier vocabulary, never
  "validated" (CI-guarded), EN/ZH with 红涨绿跌 respected, delayed-data label visible
  wherever a live number renders.
- **G0.7 Fresh-path proof (P1+ UI):** each UI phase lands with light+dark(+zh where the
  surface is bilingual) crops in the PR body from a production-shaped render; flagship
  surfaces follow the design lane (designer/Opus or main loop), not raw builders.
- **G0.8 Alert integrity (P2):** an alert kind ships only with a pre-registered
  provisional→close-confirm precision floor measured from the P0 ledger (below floor ⇒
  the kind stays site-only); every alert carries a working recall/"read updated" path.
- **G0.9 Paper wall (P3):** Mastermind consumption is a shadow/paper book behind the
  existing one-way R2 callosum (NW-U9); zero execution code, zero doctrine edits. Any
  future auto-execution question is its own operator-owned adjudication document, not a
  flag flip in this program.
- **G0.10 Storage declaration (every PR, RUL-P10):** each new write path states
  gitignored-local / git-single-writer / R2 in the PR body.

---

## §1 Why this works — the three load-bearing facts (verified 2026-07-29)

1. **The admission gate is close-only by construction.**
   `engine/signal_gate.py:85-92` (`is_buyable` = eligible ∧ tier ∈ T1–T3), backed by
   `engine/signal_quality.py` ("CLOSE-ONLY by construction", `signal_gate.py:31`) and
   `engine/confluence_tiers.py:1-23` (tier cascade "computed from the daily close").
   No high/low/volume enters `signal_gate.gate(ticker, close)`
   (`scripts/build_stock_library.py:2242`). The only full-day features anywhere nearby —
   `rel_volume`, `breakout_vol_confirmed` (`engine/stock_technicals.py:300-322`),
   vol-squeeze volume tilt (`engine/stock_score.py:755-770`) — are display/soft-rank
   tilts, not gates, and are null outside the ~232 deep-history names.
   ⇒ **Append the live price as a provisional close and run the same function.** The
   intraday product inherits the nightly engine's exact semantics forever (G0.1).

2. **The official fill is the NEXT session's close.** `scripts/grade_us_board.py:23-27` +
   `engine/grading.py:197-221` ("ENTRY = close at the bar STRICTLY AFTER the signal
   bar"). A user acting intraday at the cross is ~one full session earlier than the
   graded assumption — that session is exactly the gap-up/slippage the operator wants to
   capture, and it is directly measurable per event (cross price vs next-close fill).

3. **Provisional-tier precedent already exists.** `closing-bell.yml` ("Build A",
   16:05/17:05 ET) re-runs the board same-day stamped `provisional: true`, advances no
   ledgers; `daily.yml` 22:30 UTC ("Build B") is the sole authority
   (`closing-bell.yml:2-43`, `daily.yml:4-16`). Prophet Live extends the provisional
   tier from 16:05 back into the session — an established epistemic category, not a new
   one.

**Latency reality (be honest in every surface):** all US single-name quotes in the
estate are 15-min delayed (Polygon STANDARD full-market snapshot; `config.yml:608
live.delayed_min: 15`; the live.js green pulse is structurally unreachable today —
`templates/live.js:216-226`). The only true real-time feed is the 6-symbol macro
futures websocket (`app/tape.py:47-49`). So:

| Stage | User learns a signal is forming | Improvement |
|---|---|---|
| Today | ~16:05 ET provisional page / next morning in practice | — |
| P1 (*/5 on delayed quotes) | ~15–20 min after the cross, same session | **hours-to-a-day earlier** |
| P4 (real-time entitlement + 60s lane) | ~1–2 min after the cross | minutes |
| Tick-by-tick | seconds | **no marginal value for daily-bar signals — see §7** |

The P1 step captures almost all of the product value (same-session action, overnight gap
eliminated). P4 is a priced upgrade, not a prerequisite. Never label P1 surfaces "live"
— "intraday · 15-min delayed" is the compliant form the estate already uses.

## §2 Ground truth inventory (what we reuse — file:line)

**Engine/board:** `scripts/build_stock_library.py` (called from `build_site`,
`scripts/build_site.py:5602`) writes `us_standouts.json` (buy 81 / watch 48 / leaders 15
after #3929 widened sector cap 5→10, leaders strip, `prophet_bridge.N_CANDIDATES` 6→12)
and `setups.json` (buy 12, `engine/setups.py:46`); universe with scores ≈ 1,578 names;
cascade-eligible ≈ 132. `scripts/build_prophet.py --publish` (seconds, `daily.yml:1054`)
originates plans; `scripts/grade_us_board.py --nightly` advances the ledger.

**Quote plane:** Polygon full-market snapshot = ONE request for the whole US tape,
already entitled, polled 60–120s by `scripts/live_breadth_poller.py:262-267`; artifacts:
`data/marketing/live_quotes_snapshot.json` (~2k syms, */5 via `live-quotes.yml`
force-pushed to the zero-deploy `live-data` orphan branch), `site/live/quotes.json`,
heatmap. One consumer seam merges them freshest-wins:
`engine/marketing/live_verify.py::load_live_quotes` (:197-272) — the evaluator consumes
this, no new vendor calls. Ext-hours: `scripts/build_ext_quotes.py` (~100 names,
residential-Mac launchd). `data/massive_stock_day` is ~18 sessions stale (manifest
2026-07-02) — never a dependency here; the hot-tape pack's freshest-of-store union
(`engine/marketing/hot_tape_pack.py:14-19`) is the pattern to copy.

**Intraday lanes precedent:** hot tape radar */5 ET-window on ubuntu
(`marketing-hot-tape.yml`, DST-safe triple cron + ET guard) detect→emit→post_now ≈ ≤9
min; `com.mastermind.prophetmarks` launchd */5 RTH → `scripts/build_prophet_marks.py` →
R2 `live_flow/prophet_marks.json` → Terminal `/api/hub/prophet_marks` (ProphetView chip
currently says "nightly EOD — updates after close", `ProphetView.tsx:14`); VPS systemd
fast lane 60s (`app/deploy/macro-live-fast.timer`, orchestrator
`scripts/vps_live_orchestrator.py`) publishing atomically to
`/var/lib/macro-live/public/live/` (no git). GH cron is best-effort (~15–45 min late) —
fine for */5 windows, wrong for 60s (that cadence lives on the VPS/Mac;
`docs/live_breadth_runbook.md:165-168`). VPS is 2 vCPU with thin burst headroom — a
resize precedes any new 60s lane (`docs/VPS_LIVE_ORCHESTRATION.md:58-74`).

**Delivery:** Terminal already has per-user alert conditions + a 5-min evaluator with
`signal_buy`/`signal_sell` kinds (`CA supabase 0001_init.sql:76-84`,
`terminal/components/AlertsView.tsx`, `CA/ingest/alerts_engine.py`) — but firing only
flips a DB row; **no send channel exists**. Email transport is fully built
(`app/mailer.py`: bilingual renderer, suppression, idempotent ledger; relay activation =
operator step per `docs/ops/email-support-setup.md`; zero alert templates yet).
Web push / service worker / PWA: absent in both repos (greenfield). Account page ships
disabled "Email alerts" toggles (`site/account.js:306-316`) — vapor to make real.
Tier gating mature on both sides (MD entitlements + Caddy forward_auth,
`docs/TIER_PREVIEW_PATTERN.md`; CA `profiles.is_pro`).

**Mastermind:** third repo `/Users/chriswong/Documents/Cluade/Mastermind` — paper-only
portfolio organism, "never auto-executes" doctrine in README/CLAUDE/DOCTRINE +
`config/brain.yml is_paper: true`; consumes Prophet nightly as ADDITIVE-ONLY candidates
(`portfolio/prophet_feed.py`, staleness-gated) over the one-way R2 callosum (ruling
NW-U9); rich shadow-book infra (`portfolio/shadow_books.py`) is the safe trial vehicle.
No broker code exists anywhere (and charting-app docs rule Alpaca redistribution out for
the public app).

**Content:** marketing consumers share the live_verify quote seam; `kind="breaking"` is
deliberately outside the post-time price gate (`live_verify.py:82`,
`hot_tape.py:1417-1422`); post charts are daily-bars-only (every call site
`timeframe="DAILY"`; no intraday loader in `engine/marketing/chart_render.py`);
`mastermind_news` desk is config-dark pending the XG-W2 cadence resolver — sub-85
hot-tape events routed there are parked today.

## §3 Standing-law constraints this plan is built around

1. **Nightly is the sole advancer of forward ledgers; intraday lanes discard `data/`
   writes** (chronicle gate-5 row; DNR line 41). → spool-on-R2 + nightly reconciler.
2. **No trigger-lane merge into the graded board** (DNR §1, `PROPHET_TOPSETUPS…` §2) —
   provisional tier is presentation-only; grading population untouched (G0.4).
3. **1-tick state flips are a killed class** (CSP-R2) → debounce/hysteresis (G0.5).
4. **No un-gauntleted authority on signal surfaces** (Mag-7 forced-call row) — intraday
   states are display-tier context until §6 promotion gates pass; a null never blocks
   building the infrastructure (epistemics law).
5. **Falsifier language never front-facing; "validated" is CI-guarded** → §0.6 vocab.
6. **LLMs may only de-escalate calibrated keys** — the evaluator is deterministic engine
   code; the LLM desks may phrase/de-escalate, never originate or upgrade a state.
7. **Render budget is law** — the arming pass rides inside the existing library build
   (+bounded minutes, measured in the PR); the evaluator runs off-path on ubuntu/VPS.
8. **Runner placement law** — */5 product lane on ubuntu-latest (hot-tape precedent:
   "never the macstudio pool"); 60s+ cadence graduates to the VPS timer estate.

## §4 Build architecture

### 4.1 Nightly arming pass — `engine/prophet_live/armed_pack.py` (P0)

Runs inside `build_stock_library` right after the board is computed (same in-memory
close series — zero re-IO), or as an immediately-following step. For every name in the
scored universe emit:

```
{schema:"prophet_live.armed/v1", as_of, built_at,
 names:{TICKER:{state: buyable|eligible_t4|near|dormant|topped,
        tier, trigger_px,            # smallest provisional close that flips is_buyable true
        fade_px,                     # largest provisional close that flips it false (for buyable names)
        prev_close, adv_dollars, sector, cap_seats_used, board_member: bool,
        plan_levels: {entry, stop} | null}},   # existing published plans (prophet index)
 meta:{universe_n, probed_n, skipped:{reason:n}}}
```

`trigger_px`/`fade_px` come from **bisection over the same gate function** (append
candidate close → `signal_gate.gate`) — ~8–10 gate calls per probed name. Probe only
names within a monotonic pre-screen band (e.g. |price distance to any tier-flip
indicator| inside a generous envelope) plus all currently-eligible/buyable names; cap
probe set (~300–500) and disclose `skipped` counts (no silent truncation). Non-monotone
edge cases (an indicator where higher close ⇒ ineligible, e.g. overbought veto) get both
bounds or `state:"topped"` with no trigger — the evaluator then simply re-runs the gate
directly for those names instead of comparing to a threshold. **The pack is an
optimization; the gate is the truth** — when in doubt the evaluator calls the gate.

Storage (RUL-P10): R2 `live_flow/prophet_live_armed.json` + committed copy under
`site/live/` is NOT needed — the evaluator fetches from R2; a small public mirror ships
only with P1 surfaces. Budget: measure in-PR; expected low single-digit minutes.

### 4.2 Intraday evaluator — `scripts/prophet_live_evaluator.py` (P0)

New workflow `prophet-live.yml`, **ubuntu-latest**, */5 inside 09:25–16:15 ET
(DST-safe triple-cron + ET guard copied from `marketing-hot-tape.yml`; the 16:15 tail
pass records the close-side state). Steps: fetch `live-data` branch quotes artifact
(same two-command fetch the marketing lanes use — no vendor API call), load armed pack
from R2, evaluate:

- price ≥ trigger_px (or gate re-run where no closed-form trigger) ⇒ candidate FORMING;
  2-pass debounce promotes to FORMING (G0.5); drop back below with hysteresis ⇒ FADED.
- buyable names: price ≤ fade_px ⇒ AT-RISK (board pick would lose freshness tonight) —
  surfaced quietly, doctrine§ "watch — don't chase" honesty.
- ≥15:30 ET and still passing ⇒ `confirming_into_close: true` (the strongest product
  moment; close-dependence shrinks as the session ends).
- volume context (display only, never a gate): cumulative-vs-ADV note where volume
  exists in the quote payload.

Outputs (all runtime-tier):
- `live_flow/prophet_live.json` to R2 (Terminal hub pattern, joins `prophet_marks`).
- append event rows to R2 spool `live_flow/prophet_live_events/<date>.jsonl`
  (first_cross_ts, price, state transitions) — merge=union semantics, hot-tape-ring
  class.
- P1+: a copy into the `live-data` orphan branch for site pages (zero Pages churn).

Per-pass cost: ≤1,600 arithmetic comparisons + a handful of gate re-runs — seconds.

### 4.3 Nightly reconciler — inside `daily.yml` engine job (P0)

`scripts/reconcile_prophet_live.py --nightly`: ingest the day's spool, join tonight's
actual board verdicts + next sessions' closes as they mature, write
`data/prophet_live/forward.parquet` (sole writer = nightly; PIT-capped reads on rebakes,
leader-radar pattern). Accrues per event: close-confirmed? · cross_px vs same-day close
vs next-session-close (the official fill) · time-of-day bucket · debounced pass count.
This ledger is the entire evidence base for §6 promotion and for the operator's
"earlier entry = more profit" hypothesis — accruing from week one, display-free.

### 4.4 Surfaces (P1) — presentation tier only

- **us_stocks board**: "Forming today" live strip above the board (quote-override
  pattern; states + plain-word stance; two empty states: quiet-tape vs data-dark), ⚡
  live chip variant on Prophet cards for board members AT-RISK/confirming. Copy: EN/ZH,
  "settles at tonight's close", delayed-15m label. Design lane: designer/Opus with
  committed refs (`mockups/refs/prophet_live/`).
- **Terminal ProphetView**: live rail from `/api/hub/prophet_live` (hub proxy exists for
  marks; add key); cadence chip upgrades from "nightly EOD" to "intraday · 15-min
  delayed" only where the rail is actually live (honest by construction).
- **prophet page + showcase untouched** (delayed-winners contract stays; DNR-compliant).

### 4.4a Delivery path — RULED 2026-07-30, binding on the P1 wiring task

The P1 build (#4088) ships the surface but NOT the transport: with the artifact absent
the strip stays hidden, which is what makes merging it safe. The transport is its own
task and this is its spec. Three options were considered; two are rejected on the record
so they are not re-proposed.

- **REJECTED — mirror into `site/live/` on the `*/30` `intraday-fastpath` lane.** The
  product is a 5-minute read; a 30-minute mirror means the page can sit half an hour
  behind the artifact while displaying an "intraday · 15-min delayed" pill. The pill
  would be false by up to 30 min, which is the freshness lie G0.3 exists to prevent.
  Raising that lane to `*/5` is worse: ~80 Pages deploys a day, which
  `intraday-fastpath.yml` itself names as the thing to avoid at high cadence.
- **REJECTED — the browser fetches the R2 public base directly.** It is anonymously
  readable (verified: `live_flow/prophet_marks.json` → 200 on
  `pub-…r2.dev`), so this would add a NEW public read path for per-name trigger levels
  and pre-publication board membership — against the standing "don't show the real board
  free" ruling (#3391) that regwalled `/factordata/*` (#3393). The payload being
  self-timestamping makes staleness honest, but it does not make the exposure acceptable.
- **CHOSEN — VPS live plane, served same-origin behind the existing gate.** A resource-
  capped systemd oneshot+timer in `app/deploy/` pulls the R2 states key and writes
  `/var/lib/macro-live/public/live/prophet_live.json` atomically (the
  `macro-live-fast/snapshot/bars` pattern; `macro-update` auto-installs the unit on merge,
  so go-live is a REPO COMMIT, not an SSH edit). Caddy already routes `/live/*` through
  `@reg_asset` — `quotes.json`/`breadth.json` are the explicitly-public exceptions, and
  `prophet_live.json` must NOT join that list. The page then fetches a same-origin, gated,
  60–120s-fresh copy: cadence matches the product, no Pages churn, no new anonymous path,
  China-safe by same-origin precedent.

**Acceptance for the wiring task:** anonymous `curl` of `/live/prophet_live.json` returns
the regwall response (NOT 200 with a payload); an entitled session gets 200; the served
copy's `meta.pass_ts` tracks the R2 artifact within one timer period; the strip lights up
only once all three hold. VPS headroom is thin (2 vCPU, measured burst ~90–95% on the
existing 5-min lane) — size the unit's `CPUQuota`/`MemoryMax` like its siblings and state
the measured cost in the PR.

**Inherited exposure, not introduced by this program (own adjudication in flight):** the
repo is public, so `site/factordata/us_standouts.json` — the graded board itself — already
returns 200 from `raw.githubusercontent.com`, i.e. the Caddy regwall gates the served path
while the git mirror serves the same payload anonymously. The armed pack at R2
`live_flow/prophet_live_armed.json` inherits that condition and adds an increment (trigger
levels for names not yet on the board). This is a product/pricing exposure decision for the
operator, tracked separately in `research/PAYWALL_GIT_MIRROR_EXPOSURE_ADJUDICATION.md`;
do NOT resolve it inside this program, and do not widen it — hence the CHOSEN option above.

### 4.5 Alerts (P2)

- Reuse `CA/ingest/alerts_engine.py` (already 5-min cron): new condition kinds
  `prophet_forming` / `prophet_confirming` / watchlist-scoped variants evaluated from
  the R2 live artifact; keep one-shot disarm semantics.
- **Delivery = the missing send step**, two channels in order:
  1. **Email** (transport exists): new `signal_alert` template in `app/mailer.py`'s
     estate; per-user opt-in replaces the `account.js` "soon" toggles; relay activation
     is a named operator step (secrets), not assumed.
  2. **Web push** (greenfield, and the mobile bridge): VAPID keys, service worker on
     the terminal (and/or site), Supabase `push_subscriptions` table (owner-scoped RLS
     like `alerts`), a small dispatcher on the VPS. iOS ≥16.4 installed-PWA web push
     makes this the pre-native mobile path — real lock-screen notifications before any
     App Store work.
- Precision floor per alert kind from the P0 ledger before enabling (G0.8); recall path
  ("read updated") wired day one; tier gating recommendation: confirmed-nightly digest
  free, intraday forming alerts Insider/Pro via the entitlement pattern — final call is
  the operator's pricing decision, mechanism is ready either way.

### 4.6 Mobile app + Mastermind (P3)

- **Contract, not app:** freeze `prophet_live.json` + events schema as `/v1`, document
  on the hub; SSE endpoint on macro-api optional later. A future native app consumes the
  same bus via APNs/FCM behind the same dispatcher — zero engine work when that day
  comes.
- **Mastermind intraday shadow book**: new paper policy book (`shadow_books.py` pattern)
  on the bot side consuming the spool through the existing one-way callosum — measures
  the bot's own selection logic with same-day-cross entries vs its current
  next-day behavior. Paper forever until a separate adjudication (G0.9). The real-money
  path in this phase is the operator acting on their own alerts in their own broker.

## §5 Phases

- **P0 — Measure dark (1 PR, Opus builder).** armed_pack + evaluator + `prophet-live.yml`
  + spool + reconciler + parity/ledger-law/degradation tests. No user surface. Evidence
  accrual starts immediately. Exit: G0.1–G0.3, G0.10 green; one live market day observed
  end-to-end (workflow logs + spool rows + reconciled parquet).
- **P1 — Site + Terminal surfaces (design-first, 1–2 PRs).** §4.4. Exit: G0.4–G0.7;
  live verification on the deployed site (fresh-eyes pass, both themes, zh).
- **P1.5 — Content wire (small PR, rides P0 artifacts).** Hot tape gains a
  `prophet_live` detector consuming the same armed pack + fires (observation-voice wire
  copy, chart law honored with daily card + live marker; extended-hours/intraday-bar
  cards remain the hot-tape P2 seam, one chart house for both programs).
  `mastermind_news` dark-desk status is a known constraint, not ours to fix.
- **P2 — Alerts (2 PRs: email; web push).** §4.5. Exit: G0.8; a real device receives a
  forming alert during RTH; recall verified; entitlement gate verified from a
  free-tier account.
- **P3 — Contracts + shadow (1 PR here, 1 in Mastermind).** §4.6. Exit: G0.9; shadow
  book accruing.
- **P4 — Latency upgrade (operator-priced decision, then 1 PR).** Options, decided on
  P0/P2 evidence: (a) deploy the already-written Cloudflare quotes worker + Polygon
  real-time entitlement (the documented flip: `LIVE_DATA_POLYGON.md:143-151` — wrangler
  secret, `delayed_min: 0`, worker URL var); (b) VPS resize (2→4 vCPU) + 60s
  `macro-live-prophet` timer lane joining the orchestrator; (c) extend `app/tape.py`
  websocket relay to armed-set equities if entitlement supports it. Buys cross→alert
  ≈1–2 min. Do not start before P2 evidence shows cadence (not adoption) is the binding
  constraint.
- **P5 — Promotion gauntlet (prereg doc, no build).** Pre-registered on the P0 ledger
  (≥60 sessions, per-state confirm-rate CIs, entry-advantage CI vs next-close fill
  excluding 0, per-kind alert precision): only then may surfaces claim authority
  ("earlier entries measured +X%"), push default-on, or the Mastermind execution
  adjudication be OPENED (still its own document + operator ruling). Nulls print; a
  null kills the CLAIM, never the display tier.

## §6 Tick-by-tick verdict (the operator's direct question)

Not now, and probably never for Prophet itself. The signals are daily-bar-defined; the
admission gate consumes one number per name per day. Value of added cadence is the
expected price drift between cross and detection — minutes of drift on a swing-horizon
(2–4 week) signal. */5 on delayed quotes already collapses ~23h of latency to ~20 min;
a 60s real-time lane (P4) collapses that to ~1–2 min for a few hundred dollars/month
and a droplet resize. True tick ingestion (full-tape ws, bar-builder, tick store) adds
engineering + vendor cost + the compute the operator worried about, to shave seconds
that a 2–4 week horizon cannot monetize. **The compute fear is moot under this
architecture** — we never re-run the heavy engine intraday; we re-run one close-only
gate over ≤1.6k names, which is seconds on one core. Ticks become worth revisiting only
if a future *intraday-native* signal program (different horizon, own prereg + gauntlet)
is chartered — that program would rent tick data (Polygon Advanced / Databento) for its
backtests first, which is the cheap way to find out if it deserves to exist.

## §7 Risks & traps (encoded from house memory — check each in review)

- Mixed-asof fabrication: never join live price to yesterday's shares/mcap or stale
  prevClose (derived-ratio law); every derived number carries same-session inputs.
- DST: ET-pinned windows via the hot-tape triple-cron + in-script ET guard; never bare
  UTC crons. Fixture dates + wall-clock gates are a known CI bomb — no date fixtures in
  the new tests without the replay pin.
- Degraded-ships-confident: quote-fetch failure ⇒ dark states + `::warning` bare-print
  annotation (line-start law), never a confident empty.
- Pages churn: site copies ride the `live-data` orphan branch, not `site/live/`
  force-tracks, until/unless a surface truly needs same-origin.
- Immutable-cache assets: touching `live.js`/`theme.js` for P1 requires the surgical
  `?v=` re-stamp discipline (unsubscribe-parity trap).
- Quota: the lane polls artifacts, not `gh`; any CI-watching in sessions obeys
  `gh_quota_guard` pacing.
- Armed-pack staleness: evaluator hard-gates on `as_of == last completed session` (the
  leader-radar `_load_radar_json` pattern); a stale pack ⇒ whole artifact dark, never
  yesterday's triggers presented as today's.
- Universe honesty: names outside the scored universe (no alpha score) are out of scope
  and say so; the massive-store outage class means coverage is disclosed per-pass.
- Seat honesty: a FORMING name qualifies *on its own signal*; board seating (sector cap
  spill, leaders strip) settles only at the nightly build — copy must never promise a
  seat. Cap occupancy in the pack is yesterday's, labeled as context.

## §8 Collisions & registry

- Honors (no DNR additions needed; nothing killed here): Top-setups data-merge kill
  (§1 row), chronicle gate-5, CSP-R2 debounce, Mag-7 forced-call, PSS-F2/F3 standalone
  timer kills (untouched — this program adds no new timing signal, it accelerates
  delivery of the existing gate).
- Coordinates with: Hot Tape P1.5/P2 (shared quote seam + chart house; its
  `signal_fired` detector today reads published plan levels — P1.5 upgrades it to the
  armed pack rather than duplicating), XG-W2 cadence resolver (mastermind_news dark),
  closing-bell Build A (its 16:05 provisional stamp is the vocabulary precedent),
  live-tape/VPS orchestration (P4 lane joins that estate), crypto cockpit (no overlap).
- Flagged upstream, not owned here: `mastermind_news` enabled-check gap in the
  outbox/publisher dispatch path (found in this investigation; belongs to the marketing
  program); `data/massive_stock_day` 18-session staleness (collector credential
  hypothesis; deserves its own session).

## §9 Commissioning notes (spawn-handoff law)

Every build spawn gets: the relevant §0 gates INLINE, the §1 file:line facts it builds
against, model routing per house law (Opus `builder` for code, `designer` for P1
surfaces, main loop adjudicates), and the §7 trap list relevant to its slice. P0 is the
foundation PR and merges before any surface work begins. The commissioning session
reviews and merges its child PRs same-day per the ship loop.
