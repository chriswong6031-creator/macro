# Massive Advanced Integration — umbrella masterplan for the tick plane, the flow desks, and the Terminal bridge

_Authored by Fable, 2026-08-08, on operator commission ("research what new data we can
implement… advanced strategies… across macro dashboard and terminal and options intraday
flow in Terminal — create extensive build plan"). Status: **PLAN OF RECORD, waves gated
individually** — TP-0 ships with this PR; every later wave is a normal ship-loop PR (or a
charting-app PR for §6) commissioned per §5's inline prompts. Grounded in: a live
entitlement probe run today (§1), the four-lane census run for this doc (repo estate,
Terminal estate, collision registry, vendor matrix), and the anchor docs cited throughout.
Companion docs: `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` §7½ (M-waves — a
SIBLING program, not subsumed), `research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md`
(P-phases; this plan executes its deferred rungs), `research/DARKPOOL_DESK_AUDIT_AND_UPGRADE_2026-08-05.md`
(the desk this plan gives eyes to), `research/OPTIONS_FLOW_DATA.md`, `research/LIVE_DATA_POLYGON.md` §3._

---

## §0 ACCEPTANCE GATES (per wave, "not done unless")

Inline per the spawn-handoff law — a pointer to this section goes in every commissioning
prompt, and the wave's PR body must show the evidence.

**TP-0 (this PR) — verified ruler:**
1. `scripts/massive_entitlement_probe.py` + tests merged; probe run against the live key;
   `data/massive/capability_manifest.json` committed with `derived{}` verdicts populated
   (not `null`) for realtime trades, realtime quotes, second aggs, tick-history depth,
   options tier, indices tier.
2. The manifest never contains key material (self-check in the probe, pinned by a test
   that plants a fake key in a raised exception and asserts it cannot reach the output).
3. This masterplan merged with every DNR row it must honor cited by stable key (§2.4).

**TP-0.5 (concurrency + depth re-probe; small, BEFORE TP-1 design freezes):**
1. WS concurrency probe run during RTH: hold the real-time stocks socket open, then
   attempt the delayed socket (and the reverse), recording whether both survive — this
   decides whether delayed/real-time share one connection bucket (§3.1b's premise; the
   TP-0 Saturday run cannot decide it, see §1 footnote). Also read the Terminal hub's
   effective cluster (`/health`) before/after.
2. RTH re-probe of `ws_stocks_realtime` with data frames observed (TP-0's Saturday
   verdict rests on auth+subscribe only).
3. Quote-history depth rungs (`v3/quotes` at 2015/2005) + S3 flat-file LIST probes
   (`trades_v1`, `quotes_v1` prefixes) added to the probe + manifest — TP-B's quotes
   branch is unsatisfiable until the manifest actually carries these verdicts.
4. Probe's business-day fallback switched to `/v1/marketstatus/upcoming` (entitled)
   with the hardcoded holiday table demoted to offline fallback.

**TP-1 (ingest spine) — not done unless:**
1. A supervised WS client holds `T.*` + `Q.*` subscriptions for the pilot universe
   through a full RTH session with ≥ 99% session-seconds connected — early-close
   sessions (13:00 ET) and DST transitions handled via the market-status calendar,
   never wall-clock arithmetic. Reconnect gaps healed via REST replay; healed trades
   are signed only against replayed `v3/quotes` for the same gap, else hard-labeled
   `unclassified` (a cold NBBO ring must never sign silently); replay/live dedup key
   pinned as `(ticker, id, sip_timestamp)`; heal receipts logged as structured JSONL.
2. In-flight NBBO join measured and printed in the PR body **stratified by venue
   class**: lit prints ≥ 95% classified against a quote ≤ 5s old; off-exchange
   (TRF-reported) prints measured and disclosed separately with NO floor at TP-1 —
   their floor is set at TP-2 from this measurement (late reporting makes their
   quote-age distribution structurally different; hiding them inside a blended gate
   would fake precision). Remainder labeled `unclassified`, never guessed.
3. Off-exchange (`exchange == 4`) prints carry `trf_id` through to the minute rollup;
   lit vs off-exchange totals reconcile against the day's grouped-daily volume within
   2% on ≥ 90% of pilot names, with session scope stated (RTH vs incl-extended) and
   halted names carved out to their own disclosed bucket (no NBBO during a halt;
   reopen prints excluded from the ≤5s gate, counted in volume per condition rules).
4. Every artifact lands in a **dedicated PRIVATE R2 bucket with its own credential
   family** — the existing `publish_r2.py`/`audit_r2.py` pipeline serves the PUBLIC
   bucket (`audit_r2.py` literally alarms when an object is not publicly readable), so
   TP-1's first deliverable is the private plane: bucket + creds + a credentialed
   (S3 HEAD) beacon mode + freshness assertion on CONTENT advancing. **Zero tick/quote
   payloads in the public bucket or the public repo, ever.** Producer registers in the
   data-health breaker (`run_status.json` + audit tripwire) so a silent death surfaces
   within one session (the 21-night `massive_stock_day` no-creds incident is the
   binding precedent).
5. Kill switch: one config flag stops the daemon and the site falls back to the current
   (M1) REST presentation with no dead panels.

**TP-2 (off-exchange intraday desk) — not done unless:**
1. `darkpool.html` gains its intraday tier fed from R2 rollups: real per-print block tape
   (≥ $100k/$500k/$1m tiers), off-exchange share vs 20-day baseline (median/MAD z, current
   observation excluded — reuse `engine/darkpool_signals.trailing_z`), and price-level
   shelves — all labeled "off-exchange" per R5 semantics; the words "dark pool" appear
   only where ATS attribution genuinely exists (FINRA weekly tier).
2. Signed inference (NBBO quote-rule) ships **display-tier** with its measured
   classification rate on the card; no rank/size/gate authority; `is_context_only=true`.
3. Forward ledger rows accrue nightly from the intraday observations via the nightly lane
   only (the intraday lane never advances a forward ledger — epistemics law).
4. Bilingual EN/ZH; glance tier passes the banned-vocab sweep; hover carries the receipt
   (venue nuance: TRF ≠ named ATS; attribution stays weekly-FINRA).
5. The nightly rollup step fits the measured budget: ≤ 5 min added to `collect_tail` or
   an offrender sibling (never the render path), timings-ledger entry present.

**TP-3 (block/institutional signal factory) — not done unless:** every new signal
artifact registers in `config/synapse.yml` with grade + lobe, ships display-tier with
nulls printed, and any promotion beyond display carries its own pre-registered gate doc
(§4.4) — "not found yet" outcomes print as nulls, never blocked from shipping.

**TP-4 (Prophet/engine confluence) — not done unless:** confluence inputs land behind
Prophet's existing input contracts as **nullable columns** with coverage floors declared
(the `nullable-input-to-a-cross-sectional-gate-needs-a-coverage-floor` law); zero
published-threshold recomputes without a pre-registered era note (M3's era law binds here
too); ledger columns single-writer (A9).

**TP-5 (Terminal bridge) — not done unless:** Terminal surfaces render from the same R2
artifacts the dashboard reads (one producer, two faces); tier-gating enforced
server-side; i18n complete across the Terminal lexicons; no vendor names user-facing
(debrand law); the D4 deferral lift is recorded (operator ask 2026-08-08) in the PR body.

**TP-6 (event microstructure) — not done unless:** every event-study artifact carries its
timestamp provenance (`participant_timestamp` vs `sip_timestamp` choice stated); headline
join uses the wire's ingest stamp with measured wire latency disclosed; any "informed
flow" style tripwire ships as a watch condition, never a verdict (2026-07-27 falsifier
language law).

**Global, all waves:** normal ship loop (commit → push → PR → CI → same-day squash-merge
→ live verification); new guards registered in `config/house_law_checks.yml`; new
producers in the freshness breaker; GH annotations only as line-start `print(..., flush=True)`.

**Global licensing gate (B3, blocking for every user-facing wave):** no TP artifact
reaches a public page or a Terminal surface until the Massive plan terms — and whatever
exchange/SIP display attestations the vendor's real-time redistribution requires — are
filed under `research/licenses/` (the roadmap P0.6 discipline, applied to THIS vendor;
§7½'s "business licensing included" is the purchase claim, not the filed evidence).
Until filed: TP-2…TP-6 surfaces ship internal-first; TP-1/TP-B (data plane, no
display) proceed. The Terminal hub README's own note ("live cluster requires an
RT-entitled plan + signed exchange agreements") is treated as binding until the filing
proves otherwise.

---

## §1 What the upgrade actually grants (verified, not marketing)

Two independent verifications, same day:

1. **Breathing Platform §7½ live check (2026-08-08 ~06:50Z):** `v3/trades` + `v3/quotes`
   403→200; second aggs, snapshot, financials, splits all 200; S3 flat files
   `us_stocks_sip/day_aggs_v1` back to 2006-03-15, `minute_aggs_v1` to ≥ 2010-06-15;
   trades tape current through prior session's 20:00 ET close. Plan sold as: real-time,
   unlimited calls, trades+quotes, second+minute aggs, 20y+ flat files, websockets,
   snapshot, reference, corporate actions, financials, business licensing included.
   **The licensing clause is a purchase-record claim, not verified evidence — no probe
   can establish display/redistribution rights, and no terms are filed in-repo. The §0
   global licensing gate holds every user-facing wave until they are.**
2. **TP-0 probe manifest (`data/massive/capability_manifest.json`, committed with this
   PR):** re-runnable (`scripts/massive_entitlement_probe.py`), 36 test functions (59
   parametrized cases), key-scrubbed (leak self-check runs before every write). Run
   2026-08-08T11:44Z, 33s, market closed — WS verdicts rest on auth+subscribe only
   (zero data frames expected on a Saturday; TP-0.5 re-proves during RTH):

   | Capability | Verdict | Evidence |
   |---|---|---|
   | Real-time trades (REST `v2/last/trade`) | **entitled** | 200, ts 23:59:59Z prior session |
   | Real-time NBBO (REST `v2/last/nbbo`) | **entitled** | 200, bid+ask present |
   | WS stocks real-time `T.*`+`Q.*` | **entitled** | auth_success + subscribe success |
   | Second aggregates | **entitled** | 50 bars returned |
   | Tick history depth | **20y+** | `v3/trades` non-empty at 2015 AND 2005 probes |
   | Quote **recency** (`v3/quotes`, no depth rung probed) | entitled | 200 — historical NBBO depth + flat-file `quotes_v1` entitlement are UNPROBED until TP-0.5; nothing downstream may assume them |
   | Snapshots (single/gainers/unified) + grouped daily | entitled | 200 × 4 |
   | Reference/conditions/splits/dividends/financials | entitled | 200 (94 conditions; 27 stocks venues) |
   | **Short interest + short volume REST** (`/stocks/v1/*`) | entitled | 200 — new since the old integration |
   | Treasury yields | entitled | 200 |
   | Options chain snapshot (greeks/IV/OI) | entitled | 200, greeks present |
   | **Options trades / options WS / options realtime** | **not_entitled** | 403 + subscribe error + no `last_quote`/`last_trade` in snapshot (3 signals triangulate) |
   | Indices (`v3/snapshot/indices`, WS) | **not_entitled** | 403 + auth_failed |
   | Benzinga endpoints | not_entitled | 403 (paid add-ons) |
   | WS stocks **delayed** cluster | ambiguous | auth_success then close **1008 (max_connections)** — cause UNDECIDABLE from this run: the probe's own just-closed real-time socket (close_timeout 2s vs 1.5s settle) explains it as well as the Terminal hub holding the slot; a Saturday hub may hold nothing. TP-0.5's concurrency probe decides it |
   | `plan_guess` | `stocks: advanced_or_higher; options: snapshot-tier; indices: none` | derived block, committed |

   Naming nuance recorded by the probe: the exchanges reference labels **id 4 "FINRA
   Alternative Display Facility"** — the vendor's own scanner tutorial nonetheless
   defines off-exchange prints as `exchange==4 && trf_id present` (ADF + TRFs report
   through the same id namespace slot). TP-1 validates empirically on live prints
   (distribution of `exchange` ids where `trf_id` is present) before any copy names a
   facility; `trf_id` 201/202/203 remains the TRF-pipe map.

What this **does not** change (probed, §7½-consistent, and load-bearing for scope):
- **Options entitlements are a separate product.** As of the 2026-06-21 probe
  (`research/OPTIONS_FLOW_DATA.md`): options snapshot (OI/IV/greeks) + flat-file
  minute/day aggs entitled; OPRA per-trade tape and options NBBO **not** entitled. The
  TP-0 manifest re-probes this — if the bundle changed, §7 re-scopes by amendment.
  Until then: the options *tape* vendor remains ThetaData (signing calibration ratified
  #1292); Massive Advanced contributes the **equity leg** (real-time spot for greeks,
  NBBO for the underlying, second bars) to the options stack.
- **Indices/futures/fx/crypto real-time**: not part of Stocks Advanced (indices cluster
  probe recorded in the manifest; expected not-entitled).

### §1.1 Vendor facts that bind the architecture (docs-sourced, 2026-08-08)

- **ONE simultaneous WebSocket connection per cluster per product** on individual
  plans (extras $75/mo via support). This is the single most architecture-shaping
  constraint — see §3.1b connection-ownership law. Delayed and real-time hosts are
  separate endpoints (`delayed.polygon.io` vs `socket.polygon.io`).
- Stocks Advanced tier ladder: `T.*` real-time from Advanced (Developer = delayed);
  **`Q.*` NBBO exists at Advanced only** (no delayed tier below it); `A.*` second aggs
  + `AM.*` minute aggs; **`LULD.*` is Advanced-only** (halt/band monitor is genuinely
  new); **`FMV.*` is Business-tier only — we do NOT have it; never design against it.**
- REST: `v3/trades` + `v2/last/trade` (Developer+), `v3/quotes` + `v2/last/nbbo`
  (Advanced-only), full-market + unified snapshots, grouped daily, second-level custom
  bars. Unlimited calls with a documented soft ceiling (~<100 req/s recommended);
  M2's politeness law binds regardless.
- **Flat Files (S3)** on all paid tiers: daily gzip CSVs for trades / quotes (top-of-book
  NBBO) / minute / day aggs, nanosecond stamps, TRF prints included; prior-day file
  ready ~11:00 ET — flat files are a T+1 substrate, never a live one. Trades/quotes
  history to 2003-09-10.
- **Condition codes carry machine-readable `update_rules`** (`updates_volume`,
  `updates_high_low`, `updates_open_close`) via `/v3/reference/conditions` — all
  bar/VWAP math branches on those booleans, never on hardcoded condition IDs.
- **Off-exchange identification (official tutorial method):** `exchange == 4` AND
  `trf_id` present ⇒ TRF-reported print; `trf_id` 201 = FINRA/NYSE TRF,
  202 = FINRA/Nasdaq TRF Carteret, 203 = FINRA/Nasdaq TRF Chicago. Tutorial default
  block floor $100k notional. The tutorial omits the attribution caveat — house law
  keeps it: **TRF ≠ named ATS**; venue naming stays with FINRA weekly (§2.1).
- **Short Interest (`/stocks/v1/short-interest`, biweekly) and Short Volume
  (`/stocks/v1/short-volume`, daily, venue + exempt split, history from 2024-02)** are
  included on all stocks tiers — a free cross-check for the FINRA CNMSshvol collector,
  not a replacement (FINRA history is deeper and already sealed/attested).
- Benzinga endpoints are $99/mo-per-dataset add-ons — **not** included; do not plan
  around them. Financials vX is sunset (June 2026) in favor of the Fundamentals
  family — M5's concern, noted so the probe's `financials` verdict is read correctly.
- Rebrand mechanics: PyPI package is now `massive` (v2.8.x; `polygon-api-client`
  frozen at 1.16.3, critical-fixes only); hosts `api.massive.com` /
  `socket.massive.com` canonical with `*.polygon.io` still honored "for an extended
  period". New code takes the host from config (`config.yml polygon.base_url`), adds
  the massive.com hosts as the documented default at TP-1, and never hardcodes either.

---

## §2 Program boundaries — who owns what (collision map)

This is an umbrella plan in a crowded estate. The census found the estate **prepared**
for this purchase — three documents pre-registered seams that were waiting for the
entitlement. This plan activates those seams and builds only what nobody owns.

### §2.1 Owned elsewhere — cited, not rebuilt

| Lane | Owner | This plan's relationship |
|---|---|---|
| **M1 real-time honesty flip** (`delayed_min 15→0`, ~19 label sites, `verify_massive_realtime.py`) | Breathing Platform §7½ | Prerequisite for user-facing "live" copy anywhere; TP waves consume its verdict, never flip labels themselves |
| **M2 rate-guard re-tunes** (workers 5→measured, pacing, `max_underlyings`) | BP §7½ | TP-1's daemon obeys the same politeness law; measured raises only |
| **M3 daily/minute-agg history extension** (`EARLIEST_ENTITLED` → 2006) | BP §7½ | TP-2's baselines read the extended store when it lands; era law respected |
| **M4 equity-tape adoption for flow signing** (`engine/flow_signing.py` tick-rule → quote-rule via REST/flat-file `quotes_v1`; retire databento; LSR reopener via fresh prereg) | BP §7½ | TP-1's **live** NBBO join is the streaming sibling of M4's historical join — same classification code, one home (§3.4); the LSR reopener prereg stays M4's |
| **M5 reference/corp-actions/financials collectors** | BP §7½ | TP stores join splits/divs from M5's spine (the F6 split trap lives here) |
| Provisional close-pass, breathing board, CN same-day (W-L1…W-L4) | BP core waves | TP artifacts may feed its badges later; no shared files |
| Fear/greed, screener, EOD flow desk phases P1–P5 | `LIVE_FLOW_PRODUCTION_ROADMAP` | Untouched; TP-2/TP-3 fulfill its **T3e/T4e** dark-pool rungs ("massive trades_v1 upgrade… paid SIP/live tape") that were procurement-deferred |
| FINRA weekly ATS/non-ATS attribution, venue roles, PSS-AF1 compliance | Dark-pool desk v2 (shipped 08-05) | TP-2 adds the desk's own §3-declared missing tier (intraday/per-print); weekly attribution remains the venue-truth layer |
| Options EOD tape, signing calibration, T2a signed features | Roadmap P2 (ThetaData; `HOLD-THETA-TAPE` suspends the Final3-lobes tape lobe specifically) | Unchanged vendor; TP-7 only upgrades *cadence* and the equity leg |
| **`/ws/tape` browser fanout + futures tape + live breadth scoreboard** | `LIVE_TAPE_SCOREBOARD_MASTERPLAN` (CHARTERED 07-24; built `app/tape.py`, Yahoo-sourced). Its **D2** assigned any future Polygon WS to slot behind its relay; its **D6** chartered breadth as snapshot-join, NOT per-name WS | Honest tension, named: TP-1 stands up a vendor socket for **artifact production** (a scope D2 did not adjudicate — D2 governs the browser quote path, whose consumers stay unchanged). §4.2/8 (WS-derived breadth) is an amendment PROPOSAL to their D6, not an offer; their charter decides. Any conflict at build time resolves by amendment to one doc or the other, never silently |
| Heartbeat/staleness spine (CSP-W5/W6 `run_status.json`, breakers) | Contagion-sensing program | TP producers REGISTER in it (mandatory), never fork it |
| Intel Hub lobe audit (W0–W6) | `INTEL_HUB_LOBE_AUDIT…` (08-08) | Parallel program, no shared files; new synapse artifacts follow its ruler conventions |
| Terminal options-hub UX, flow desk, GEX desk, voltick port | `OPTIONS_HUB_MASTERPLAN`, `VOLTICK_COMPETITIVE_SWEEP_AND_BUILD_PLAN`, `INTRADAY_FLOW_TRACKER_DESIGN`(+V2 ruling) | TP-5 lands *data planes + overlays* into their surfaces; UX programs keep their charters |

### §2.2 This plan owns (net-new)

1. **The tick plane** — supervised Massive WS ingest (trades + NBBO), in-flight
   classification, minute/second rollups, R2 tick-artifact layout, gap heal, health.
2. **Off-exchange intraday** — real TRF prints: blocks, DP share intraday, shelves,
   signed inference (display-tier), after-hours block monitor.
3. **Tick history plane** — flat-file trades/quotes backfill (scoped universe), baseline
   calibration for every intraday z-score, and the backtest substrate for promotions.
4. **Event microstructure** — press-wire/earnings-wire × nanosecond tape joins.
5. **Second-aggregate structures** — opening-range/acceleration features offered to BP's
   breathing lane and Prophet anticipation (consumers decide; display first).
6. **Terminal bridge** — the D4 lift: flow/desk surfaces in charting-app fed by this
   repo's R2 artifacts (one producer, two faces).
7. **Options cadence upgrade** — intraday snapshot cadence for GEX/flow context using
   already-entitled endpoints + live equity spot (no new OPRA claims).

### §2.3 Explicit non-goals

- No second quotes pipeline: `live_quotes.py`/worker/`live.js` presentation is M1's.
- No options-tape vendor change; no OPRA claims beyond probed entitlements.
- No indices/futures/fx feeds (not entitled; probe-recorded).
- No yfinance replacement program (separate risk decision; `massive_stock_day` already
  covers whole-market daily cross-sections).
- No LLM-originated signals anywhere in the plane (A7; LLMs may only de-escalate
  calibrated keys).

### §2.4 Standing kills/laws/holds honored (stable keys, quoted scope)

| Key | What it forbids/holds here | TP consequence |
|---|---|---|
| `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` | LSR-P0 killed; STILL-OPEN clause names tape-grade features (signed order imbalance, price-impact-per-signed-dollar, true spread) as "blocked on entitlement, not effort" | The reopener is **M4's** to exercise via fresh prereg; TP waves build the substrate but never resurrect LSR constructions on the side |
| `DNR:HOLD-PSS-AF1-FINRA` (+ charter §14) | Raw short ratio / off-exchange share forbidden as standalone direction | TP-2's signed inference is a *different construction* — per-print NBBO aggressor classification (quote rule), a measured procedure with **disclosed coverage rates per venue stratum and a literature-cited method whose equity signing ACCURACY is UNMEASURED here** (we hold no aggressor ground truth; live-vs-historical agreement in §9 is reproducibility, not accuracy). It ships display-tier, framed as classified flow, and **cannot enter any promotion gauntlet until a pre-registered accuracy design exists** (§4.4). The killed construction (raw share ⇒ verdict) stays dead. Frozen-family seals untouched: TP stores are **new files**; nothing appends to `data/finra_short_volume/panel.parquet` |
| `DNR:KILL-INTRADAY-CHRONICLE` | Intraday lanes advancing nightly-owned stores | Restated as TP law: the tick plane writes ONLY its own R2 stores + live-dir artifacts; every forward ledger advances via nightly |
| `DNR:KILL-REGIME-SCORECARD` + `DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR` | Fusing gamma/vol/flow/breadth/positioning into composite regime verdicts (positioning-fusion illegal) | §4 ships per-signal observations only; **no "institutional flow score", no fused dial** — confluence chips reference individual keys through the existing risk_radar→market_state chain |
| `DNR:KILL-NIGHTLY-HARD-GATE` | Hard-gating downstream jobs on collector success | Tick-plane producers fail soft: staleness via disclosure + heartbeat; consumers render honest nulls |
| `DNR:KILL-DIRECTIONAL-SHORTING` | Short-side reads as SHORT calls | Any short-flavored TP context (SSR flags, short-volume cross-checks) is AVOID-only evidence |
| `DNR:KILL-FRESH-TICKS-WINDOW` | Prophet admission "ticks" window widening | Naming discipline: TP never uses "ticks" for Prophet-adjacent features (the word is claimed); trade-print features are named `tape_*`/`prints_*` |
| `DNR:KILL-CHARM-NARRATIVES`, `DNR:KILL-DOI-FAMILY`, `DNR:KILL-SKEW-DECELERATION` | Killed options constructions | TP-7 cadence work surfaces observed greeks drift only; none of these constructions return via "intraday" re-skins |
| `DNR:HOLD-THETA-TAPE` | Theta tape lobe SUSPENDED (Final3-lobes program) | TP treats the options tape as an operating *production* feed for the flow desk but builds no new lobes on it; the hold's lift belongs to its program |
| `DNR:HOLD-WF-OPTIONS` | W-F options track PARKED | TP-7 does not advance it |
| `DNR:HOLD-IGNITION-SURFACES` | Live-ish predictive "radar" surfaces suspended pending ≥30 graded calls + operator ruling | TP surfaces are **observational desks** (what printed, what is elevated vs own baseline), never "igniting/warming" predictions; any alerting rides existing alert_triage precision floors |
| `DNR:KILL-PUBLIC-INTERNALS` | Internals on public surfaces | TP receipts cite product artifacts only (CXI-R23 unchanged) |

---

## §3 Target architecture — the tick plane

Design law: the render budget is untouched (all ingest off-path), GHA hosts no daemons
(BP R6: "cadenced lanes run on OUR metal"), the public repo carries no paid payloads
(public-repo law), and every store answers "who heals it, who watches it, who retires it"
before it exists (§3.6).

```
                        ┌─ Massive WS  wss://socket.polygon.io/stocks  (T.* , Q.*)
                        │      one connection, supervised, pilot→scaled universe
   VPS (systemd) ───────┤
   engine/tick_plane/   │  ingestd: auth → subscribe → frame decode
                        │    ├─ last-NBBO cache per symbol (ring, ~seconds)
                        │    ├─ trade classifier: quote-rule vs cached NBBO
                        │    │    (midpoint → buy/sell/mid; stale-quote ⇒ unclassified)
                        │    ├─ TRF splitter: exchange==4 → off-exchange leg (trf_id kept)
                        │    ├─ block detector: notional tiers, AH session tag
                        │    └─ rollup: per-symbol 1-min bars of {lit vol, oe vol,
                        │         signed vol (b/s/u), block counts/notional, vwap, spread}
                        ├─ spool: local JSONL/parquet ring (crash-safe, replayable)
                        ├─ publish: R2 (private tick bucket) every N min + EOD compact
                        └─ health: heartbeat file + run_status registration + gap log
                                     │
        Mac fleet (launchd, RTH-idle) ─ heavy passes: EOD compaction, shelf detection,
        baseline recompute, flat-file backfills (S3), event-study batches → R2
                                     │
        Nightly (GHA, existing jobs) ─ reads R2 rollups only (bounded minutes):
        desk pages, ledgers (sole advancer), synapse artifacts, site JSON
```

### §3.1 Placement

- **Ingest daemon**: VPS systemd unit (`app/deploy/` pattern, like `macro-sentinel`),
  running from the VPS deploy tree; secrets via the existing env file mechanism, key name
  `POLYGON_API_KEY` (alias `MASSIVE_API_KEY`). The VPS is 24/7, already fronts
  `/ws/tape`, and BP R6 assigns quote-driven lanes there. The Mac fleet is the fallback
  home (launchd + `run_with_env.sh` + dedicated deploy-tree doctrine) if VPS CPU/egress
  measures tight in TP-1's pilot.
- **Heavy compute**: Mac fleet launchd (idle through RTH; §7½ census) or nightly
  offrender siblings (`needs: engine, if: always()`) — never the render path.
- **Browser fanout**: NOT in scope for TP-1 (no per-user tick streaming). Site panels
  read R2-derived JSON at existing cadences; a `/ws/tape`-style fanout for Terminal is a
  §6 decision **after** measured demand (mirrors §7½'s worker-deferral logic).

### §3.1b Connection-ownership law (single-WS constraint)

The plan allows **one simultaneous WS connection per cluster** — and whether the
delayed and real-time endpoints are one bucket or two is **untested** (the TP-0
Saturday 1008 cannot decide it; TP-0.5 gate 1 exists to decide it). Two candidate
clients exist in the estate: this repo's TP-1 daemon (to build) and Terminal's Quote
Hub (`hub/lib/polygon.js`, today subscribing `AM.*` only, with auto-demote-to-delayed
on a real-time-denial frame). Law:

1. **The TP-1 ingest daemon is the sole owner of `socket.*/stocks` (real-time).**
   Recorded in a connection registry block in this doc + the daemon's runbook; any
   second real-time client is a defect, not a config choice.
2. **Terminal's hub pins `HUB_POLYGON_CLUSTER=delayed`** until TP-5, when it migrates
   to consuming TP-1's derived per-minute stream (via co-located macro-api or R2) and
   drops its own vendor socket for US equities. Its auto-demote behavior is the interim
   safety net, not the design. **If TP-0.5 shows delayed and real-time share ONE
   bucket, the hub migration moves INTO TP-1's wave** (the daemon cannot take the slot
   until the hub is off it — shipping a Terminal quote outage as an architecture is
   the named failure this law exists to prevent), with the hub's REST-snapshot
   fallback bridging the cutover.
3. **The paging predicate is post-`auth_success` `1008`/`max_connections` on
   reconnect** — NOT auth failure. The vendor delivers entitlement/slot denials AFTER
   a successful auth (the hub's own code documents this: "RT entitlement denied
   arrives AFTER auth_success"). TP-1's supervisor reads the hub's `/health` effective
   cluster before first connect and on every eviction.

### §3.2 Universe policy (storage is the binding constraint, not API calls)

Full-SIP capture is a firehose (quotes ~O(10⁹)/day market-wide) and is **rejected**.
Tiered capture instead:

- **Tier A — full trade capture + NBBO classification**: pilot = the options/GEX
  universe (`gex_symbols()`, ~375) ∪ Prophet US actives ∪ index/sector ETFs, **hard
  cap 600 symbols** (a bounded set, not two unbounded unions — overflow drops
  lowest-ADV names, logged). Trades stored per-print (~50-80M/day market-wide; this
  tier is a fraction); quotes **never stored raw** — consumed in-flight for
  classification, only per-minute spread/imbalance summaries persist. TP-1's PR mints
  the measured GB/day envelope for the cap; §9's storage tripwire is inert until that
  number exists and arms the day it does.
- **Tier B — whole-market rollups**: no per-print retention; per-minute aggregates from
  the same feed for breadth/DP-share context (whole-tape `T.*` is affordable to *listen*
  to; storage is what's rationed). Enabled only after Tier A runs clean for a week.
- **Tier C — everything else**: grouped-daily + snapshot (already canonical via
  `massive_stock_day`).

### §3.3 Stores (all R2-private; naming provisional until TP-1's PR)

| Store | Grain | Retention (creep remedy applies to ⚡ rows) |
|---|---|---|
| `tick/trades/<yyyy-mm-dd>/<SYM>/part-<HHMM>.parquet` ⚡ | per-print, Tier A, **appended as intraday part files** (a symbol-day file rewritten every N minutes uploads O(N²) bytes — parts + EOD compaction upload each byte ~once) | 90d hot, then EOD-compacted archive; archive prunable by age |
| `tick/rollup_1m/<yyyy-mm-dd>.parquet` | symbol×minute | permanent — bounded by construction (KBs/name/day) |
| `tick/blocks/<yyyy-mm-dd>.parquet` | per block print | permanent — bounded by construction |
| `tick/oe_daily/<yyyy-mm-dd>.parquet` | symbol×day off-exchange summary | permanent — bounded by construction |
| `tick/health/<yyyy-mm-dd>.jsonl` | gaps, heals, classification rates | permanent — bounded |
| local spool ⚡ | crash-safe ring on the ingest host | ring-bounded; oldest-partition drop is LOUD (§3.6) |

Local spool survives R2 outages (replay on recovery). EOD compaction reconciles vs
grouped-daily (the 2% SIP self-consistency gate, §0/TP-1.3). §9's storage remedy names
the ⚡ rows — the "permanent" rows cannot creep by construction, and if one does, that
is a defect in its producer, not a pruning decision.

### §3.4 One classification home (corrected per review)

`engine/flow_signing.py` **already implements** the quote rule:
`quote_rule_sign` = quote rule with tick-test tiebreak at the midpoint, and it is
already the shared signer for the options-tape callers (`engine/tape_flow.py`,
`engine/live_flow.py`). TP does NOT re-add it. TP-1 adds a **new, additive entry
point** (working name `classify_print`) in the same module that (a) returns the
4-bucket vocabulary `buy | sell | mid | unclassified` + the quote-age that justified
it — `mid` is a bucket the existing tiebreak deliberately collapses, so the existing
callers' contract is untouched (no signature or behavior change to
`quote_rule_sign`); (b) is imported by both the live daemon and any historical
backfill, so live and historical paths cannot drift. **Sequencing with M4:** M4 is
chartered to touch this same module for the options-side migration — TP-1 lands the
additive entry point first (or rebases onto M4 if M4 lands first); neither wave
modifies the other's functions, and the PR that arrives second carries the
reconciliation note.

### §3.5 Timestamps

`participant_timestamp` (venue) is the event time for microstructure work;
`sip_timestamp` for tape-sequence work; wall-clock only for freshness. **TRF-reported
prints are the exception and get their own policy:** they are late-reported by
construction, and their participant stamp is frequently absent or not meaningful — a
TRF print is signed against the NBBO at `participant_timestamp` when present and
sane (≤ session bounds, ≤ sip), else at `trf_timestamp`, else labeled `unclassified`;
the stratum's stamp-availability rates are disclosed in TP-1's PR body. Every derived
artifact states which stamp it used. Nanoseconds survive parquet as int64 — no
datetime truncation in stores; humanize only at render.

### §3.6 Ops covenant per store

Producer registered in the freshness breaker; private-plane beacon (§0 TP-1.4); a
documented heal command; a retirement condition ("if unread for 90 days, retire the
producer"). No heartbeat-only adapters: the breaker asserts **content advanced**, not
process-exited-0 (binding precedent: 21 nights of silent `{"blocked":"no_creds"}`).
Host discipline (load-bearing because a 5s quote-age window rides nanosecond stamps):
NTP sync asserted at daemon start + hourly (refuse to classify when measured skew
> 1s — quote-age becomes fiction); spool-full behavior defined (oldest-partition
drop with a loud breaker event, never a silent wedge); key/credential rotation
runbook lines for both the API key and the private-bucket creds.

---

## §4 What Advanced uniquely enables (the signal catalog)

Ordered by (evidence-of-demand × buildability). Everything enters **display-tier free**
(nulls never block building); authority requires the §4.4 gauntlet. Confluence framing
throughout — a factor that is null standalone is retained as a confluence input.

### §4.1 Off-exchange / institutional prints (the dark-pool desk's missing tier)

The desk today: FINRA daily short-volume (T+0 ~18:00 ET) + weekly ATS attribution
(2-4wk lag). Advanced adds the **same-day, per-print** layer it declared pending:

1. **Real-time off-exchange share** — TRF volume ÷ consolidated, intraday cumulative vs
   each name's own baseline. Two measurement laws baked in from the audit: baselines
   are **minute-of-session-conditioned** (off-exchange share has a strong intraday
   shape — a 10:00 cumulative scored against a full-day distribution manufactures
   morning z-spikes; F7's median/MAD discipline fixes the estimator, this fixes the
   conditioning), and **split-guarded in-wave** (TP-B computes `share_break_index`
   baseline restarts itself from the entitled splits endpoint — F6's BKNG z=+53.7
   ghost is the precedent; no waiting on M5).
2. **Block tape** — large prints with lit/off-exchange venue leg, session tag
   (pre/RTH/AH), and NBBO-relative placement (at bid/mid/ask). Tiers are
   **dual-reported**: absolute notional ($100k/$500k/$1m, the vendor-tutorial
   convention users recognize) AND ADV/percentile-relative (a $100k print is a
   different event in F vs in a $3 microcap; the relative tier is what feeds any
   z-scored context). Copy says "large prints" — size is measured; who traded is not
   (no "institutional" attribution in glance copy; the ATS-character blend in 2b is
   the honest actor-context layer).
2b. **ATS-character blend (the named-dark-pool layer)** — each live off-exchange
   observation carries the name's trailing FINRA venue split as context: ATS fraction
   (true dark pools) vs wholesaler vs bank-desk vs unattributed, from the ALREADY-SHIPPED
   weekly collectors (`finra_ats_transparency`, `finra_otc_nonats`) and
   `knowledge/darkpool/otc_firm_roles.yaml`. Copy law: the blend is a **labeled
   historical heuristic** ("~31% of AAPL's hidden volume typically routes through true
   dark pools — weekly FINRA, 2-4wk lag"), never a live measurement; a live print is
   attributed to a TRF pipe (201/202/203), never to a named ATS. Named-venue truth
   arrives on FINRA's clock and back-fills the desk's weekly tier — the fast signal and
   the slow attribution are two layers by design, not a gap to paper over.
3. **Signed off-exchange flow** — quote-rule classified TRF prints, aggregated to
   buy/sell/mid/unclassified notional. Display-tier with the measured **coverage** rate
   per stratum printed on the card; the method is literature-standard but its equity
   signing **accuracy is unmeasured here** (§2.4) and the copy never overstates that.
   Different construction than what PSS-AF1 killed (classified prints, not inferred
   direction from share) — and it still cannot touch authority without the §4.4
   accuracy design + gauntlet.
4. **Repeat-print levels** — price levels where off-exchange notional repeatedly
   concentrates; rendered as level chips with recurrence counts. Recurrence is the
   measurement; "accumulation" is an actor-intent claim the data cannot make, so the
   word does not appear (§11.16).
5. **After-hours block monitor** — AH TRF prints joined to that evening's
   earnings-wire/press-wire events; feeds the earnings desks' "what moved after the
   close" context.
6. **Off-exchange acceleration** — day-over-day and intra-day slope of DP share on
   names already flagged by Prophet/standouts (confluence chip, never standalone).
7. **Sector/board rollups** — off-exchange notional flow by sector/basket via the
   existing membership spine, feeding sector rotation desks as context columns.

### §4.2 Microstructure & breadth (whole-tape listening)

8. **True real-time breadth** — advancers/decliners/new-highs from the live tape.
   **This contradicts two standing decisions of the tape-scoreboard charter and is an
   AMENDMENT PROPOSAL to that program, not an offer**: its D6 chartered breadth as a
   full-market snapshot join, explicitly NOT per-name websocket, and its D2 assigned
   any future Polygon WS to slot behind its relay. TP-1's ingest socket exists for
   artifact production regardless (that decision is this plan's); whether breadth
   presentation ever consumes a TP artifact is that charter's call via its own
   amendment — until then their snapshot-join breadth stands, upgraded to real-time
   labels by M1 alone.
9. **Spread/liquidity regime** — per-minute effective spread + top-of-book imbalance
   summaries (from the in-flight NBBO cache; never raw quote storage) → a liquidity
   stress chip for risk overlays; also the execution-quality context Mastermind needs.
10. **Halt/LULD monitor** — halts and reopenings as events on the wire desks.
11. **Odd-lot share** — odd-lot % of prints as a context column. NOT claimed as an
    institutional/retail separator: odd-lot share is dominated by share price (a $900
    name prints odd lots mechanically) and by post-2014 algorithmic slicing — the
    column ships price-normalized (vs same-price-band peers) or not at all.
12. **Opening/closing structure** — opening-range formation from second-aggs; MOC
    imbalance *proxies* from the closing print cluster (labeled proxy — we do not have
    exchange imbalance feeds; no fabricated "imbalance" claims).

### §4.3 History-enabled (flat files: trades to 20y, quotes where entitled)

13. **Baseline truth for every intraday z** — 2-5y of per-name DP-share/block-rate
    distributions so day-one intraday z-scores aren't cold-started (the audit's F5
    lesson: never ship a 47-day baseline again).
14. **Event studies at print resolution** — earnings/headline reaction latency and
    depth (joins press-wire/earnings-wire stamps to the tape); produces the "how fast
    does this name absorb news" per-name profile the wires can cite.
15. **Signed-flow history for gauntlets** — the backtest substrate for every §4.1
    promotion attempt (quote-rule over historical NBBO where flat-file quotes are
    entitled; tick-rule fallback labeled where not).
16. **Execution-cost curves** — spread/impact by time-of-day per name (Mastermind's
    slippage model input; receipts live in that repo).

### §4.4 Promotion gauntlet (unchanged house law, restated as the contract)

Display → authority requires: pre-registered gate doc (hypothesis, eras, FDR family,
kill criteria) BEFORE the joined look; walk-forward on the §4.3 substrate; nulls printed
either way; "validated" never emitted (CI-enforced); falsifier language never
user-facing (watch-conditions only). A null keeps the factor as display + confluence
input — the search continues, the specific construction closes.

**Additional clause for signed-flow factors (B4):** no signed-flow construction enters
any gauntlet until a **pre-registered accuracy design** exists for the classifier
itself — an estimator of signing accuracy against something that is not the same
classifier on another data path (candidates: a purchased labeled sample, an
exchange-direct aggressor-flagged feed, or a designed natural experiment; live-vs-M4
agreement measures reproducibility and is expressly insufficient). Until that design
exists and runs, signed flow is display + confluence context, permanently capped.

---

## §5 Waves

Model routing per house law: Opus builds (`builder`), Opus reviews (`reviewer`),
Sonnet censuses, Fable (main loop) adjudicates/ratifies. Every wave = fresh worktree off
`origin/main`, one PR, `merge-on-green`, live verification. Gates: §0.

| Wave | Scope (repo) | Depends on |
|---|---|---|
| **TP-0** | Probe + manifest + this plan (macro) | — (this PR) |
| **TP-0.5** | Concurrency probe (delayed↔realtime buckets), RTH WS re-probe, quote-depth rungs, flat-file LIST probes, marketstatus-based calendar in the probe | TP-0; **blocks TP-1 design freeze and TP-B's quotes branch** |
| **TP-1** | `engine/tick_plane/` ingest daemon + spool + **private R2 plane (new bucket + creds + credentialed beacon)** + health + VPS systemd unit + pilot-universe RTH soak; hub migration folds in if TP-0.5 proves one shared connection bucket | TP-0.5 |
| **TP-2** | Off-exchange intraday desk tier (builders + `darkpool.html` sections + ledger accrual via nightly) | TP-1 stores |
| **TP-3** | Signal factory: blocks/shelves/AH monitor/sector rollups as synapse-registered artifacts + desk cards | TP-1; TP-2 patterns |
| **TP-B** | History backfill: flat-file trades (+quotes where entitled) for Tier-A universe → R2; baseline calibration pack | TP-0 (parallel to TP-1/2) |
| **TP-4** | Prophet/engine confluence columns + breathing-lane artifact offers (BP consumes at their choice) | TP-2/TP-3 + TP-B baselines |
| **TP-5** | Terminal bridge (charting-app PRs): desk mirrors + chart overlays via R2/intel bridge | TP-2/TP-3 artifacts; §6 census |
| **TP-6** | Event microstructure: wire×tape joins, reaction profiles, AH-block × earnings joins | TP-1 + TP-B |
| **TP-7** | Options cadence upgrade: intraday snapshot passes + live-spot greeks context (existing entitlements only) | TP-1 (spot feed); probe verdicts |

Wave sizing: TP-1 is deliberately the **only** infrastructure wave; every later wave is
artifact/product work on top of its stores. If TP-1's pilot week fails its gates, nothing
downstream has been built against fiction — the plan degrades to M-waves + EOD tiers
(which ship regardless).

### §5.1 Commissioning prompts (spawn-handoff law: gates travel with the prompt)

Later waves get their prompts minted by the commissioning session at dispatch time
(context changes between waves); TP-1/TP-2/TP-B/TP-5 are pinned now because their specs
are fully determined by this doc.

**TP-1 (opus `builder`, fresh worktree off origin/main):**
> Build `engine/tick_plane/` per `research/MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md`
> §3 (read §0 TP-1 gates, §1.1, §2.4, §3 in full first; honor every §11 rejection).
> Deliverables: (0) FIRST: the private R2 plane — new non-public bucket + its own
> credential family + a credentialed S3-HEAD beacon mode (`audit_r2.py --private` or a
> sibling tool; the existing pipeline serves the PUBLIC bucket and its beacon alarms
> on non-public objects — do NOT route tick data through it); (1) `ingestd.py` —
> supervised WS client (package `massive`, add to requirements with pin; host from
> config with `socket.massive.com` default, `*.polygon.io` fallback documented)
> subscribing `T.<pilot>`+`Q.<pilot>` where pilot = `gex_symbols()` ∪ Prophet US
> actives ∪ sector/factor ETFs, HARD CAP 600 (drop lowest-ADV, log drops);
> single-connection law §3.1b — paging predicate is post-`auth_success`
> `1008`/`max_connections` on reconnect, read the Terminal hub `/health` cluster
> before first connect, and if TP-0.5 proved ONE shared bucket, fold the hub cutover
> into this wave; (2) in-flight NBBO ring + a NEW ADDITIVE `classify_print` entry
> point in `engine/flow_signing.py` returning `buy|sell|mid|unclassified` + quote-age
> (`quote_rule_sign` already exists with a tick-tiebreak contract two options callers
> depend on — do not change its signature or behavior; see §3.4 for the M4 sequencing
> note); TRF prints follow the §3.5 timestamp policy (participant → trf → unclassified);
> (3) TRF splitter (`exchange==4 && trf_id`), block detector (absolute + ADV-relative
> dual tiers, conditions filtered via `/v3/reference/conditions` `update_rules`, never
> hardcoded IDs); (4) intraday part-files + EOD compaction to the §3.3 private-plane
> layout (ZERO payloads in the public bucket or repo); (5) REST gap-heal: replay
> `v3/trades` AND `v3/quotes` for the gap — healed trades with no replayed quote are
> hard-labeled `unclassified`; dedup key `(ticker, id, sip_timestamp)`; heal receipts;
> (6) systemd unit + deploy notes under `app/deploy/` (macro-sentinel precedent), env
> via the existing VPS env-file mechanism, key `POLYGON_API_KEY`/`MASSIVE_API_KEY`;
> (7) freshness-breaker registration (`run_status.json` + audit tripwire asserting
> CONTENT advanced) — the 21-night silent no-creds incident is the failure you are
> fencing; (8) pytest per module incl. recorded-frame decode tests (pure function),
> classification-vs-fixture tests, and a key-scrub test; (9) kill-switch config flag.
> RTH soak evidence (≥99% session-seconds, ≥95% classification, 2% reconciliation) in
> the PR body per §0 TP-1 — run the soak from the VPS or a Mac host, not GHA. GH
> annotations only as line-start `print(..., flush=True)`. PR + `merge-on-green`.

**TP-2 (opus `builder` for engine/site + `designer` for the desk sections; two PRs ok):**
> Read §0 TP-2 gates + §4.1 + `research/DARKPOOL_DESK_AUDIT_AND_UPGRADE_2026-08-05.md`
> in full. Extend `engine/darkpool_signals.py`/`darkpool_context.py` + `scripts/
> build_darkpool_desk.py` with the intraday tier reading TP-1's R2 rollups (never the
> raw feed): intraday off-exchange share vs 20d baseline (`trailing_z` reuse), block
> tape, ATS-character blend per §4.1/2b (labeled historical heuristic), AH block list.
> Copy law: "off-exchange" vocabulary, R5 semantics, glance-tier word budgets, EN/ZH,
> hover receipts carry TRF≠ATS nuance + classification rate. Forward-ledger rows accrue
> via the nightly builder only. Nightly cost ≤5 min measured in the timings ledger.
> Design lane: desk sections get spec-first treatment (frontend-design skill +
> DESIGN_DOCTRINE) before assembly.

**TP-B (opus `builder`; parallel to TP-1, AFTER TP-0.5):**
> Flat-file backfill per §3.3/§4.3: S3 `us_stocks_sip/trades_v1` (+`quotes_v1` ONLY if
> the TP-0.5 manifest carries an entitled verdict for it — the TP-0 manifest has no
> flat-file or quote-depth verdicts at all) for the Tier-A universe, 2 years minimum
> (extend to 5y only after sizing the first pull), LIST-then-budget before any GET
> (hard cap in the PR body), to the PRIVATE R2 plane partitioned per §3.3; derive
> per-name baselines (DP-share/block-rate distributions, median/MAD,
> **minute-of-session-conditioned** per §4.1.1) into a calibration pack consumed by
> TP-2; **split guard in-wave**: pull `/v3/reference/splits` and compute
> `share_break_index` baseline restarts (the audit's F6 trap — flat-file trades are
> raw, day-agg comparisons are retro-adjusted); reconciliation vs grouped-daily per
> day pulled. Uses `MASSIVE_S3_*` creds (separate family — verify presence, fail soft
> with the §3.6 covenant). Runs on Mac fleet or offrender lane, never render path.

**TP-5 (per-surface: `designer` spec → opus `builder` implement; charting-app PRs):**
> Read §6 in full + §0 TP-5 gates. Audit `claude/massive-financials` +
> `claude/live-rt-second-bars` branches first; branch from charting-app `master`.
> Deliverables per §6.5 (a)–(d), fed exclusively by macro-api endpoints + R2 keys this
> repo publishes (extend `flowSource.ts` ladder); chart work through
> `terminal/lib/chart-engine/` only; new lexicon file per surface; features gated by
> new `features[]` keys minted on the macro-api billing side; measured-freshness
> badges; debrand law. Visual crops (light+dark+zh) in each PR body; no first-pass
> self-merge on flagship surfaces.

---

## §6 Terminal track (charting-app) — census-grounded

The Terminal was *designed* for this purchase: its founding architecture doc names the
"Polygon/Massive full-SIP tier" as the target primary vendor, and its Databento design
doc + options audit both record TRF prints as a named gap whose "only route" is exactly
this feed. Census facts that bind the build:

- **Estate today:** options flow = SSE from the co-located macro-api
  (`127.0.0.1:8000` on the SAME VPS — this repo's FastAPI serves Terminal directly) with
  R2 fallback (`flowSource.ts` `backendPath()`/`r2Key()`); root options vendor is
  ThetaData on the Mac fleet → R2. The equity WS leg is the Node Quote Hub
  (`hub/lib/polygon.js`, `AM.*` only, systemd `quote-hub.service`). Dark pool exists
  only as the EOD context belt (FINRA, labeled "NOT prints, NOT live"). No equity
  time-and-sales, no Level-2, no equity block feature anywhere — all net-new surface.
- **Transport for TP-5 already exists**: extend `flowSource.ts` upstream paths +
  macro-api endpoints + the public R2 bucket keys — the same three-rung ladder the flow
  desk uses today. No new infra class needed for desk mirrors.
- **Chart overlays** target the in-progress `terminal/lib/chart-engine/` contract
  (never raw Lightweight-Charts call sites): DP shelves/levels via the
  `createPriceLine` pattern (the "Options Levels R3.1" overlay at
  `ChartPanel.tsx:1519` is the template), block prints via `createSeriesMarkers`,
  anything richer (shaded DP bands, in-canvas tape strip) via the `ISeriesPrimitive`
  template (`sessionShading.ts`).
- **Gating:** new features key off macro-api `/api/me` `features[]` (the
  `terminal_live_options` precedent) — feature flags minted on the billing side of THIS
  repo; `entitlement.ts` 45s positive-cache consumes them. Tiers free/essential/pro.
- **i18n:** self-contained surfaces get a sibling `xxxStrings.ts` lexicon (the
  `flowdeskStrings.ts`/`gexStrings.ts` precedent); chrome strings go to `i18n.tsx`.
- **Pre-build audit:** two unmerged branches likely contain reusable prototypes —
  `claude/massive-financials` (Massive fundamentals client) and
  `claude/live-rt-second-bars` (`HUB_REALTIME_QUOTES`, second bars, measured-freshness
  labels). TP-5's builder audits both before writing new client code. The Terminal
  working tree may sit far behind `master` — TP-5 branches from `master`, always.

Binding decisions:
1. **One producer, two faces.** Terminal renders artifacts this repo produces (macro-api
   + R2), exactly like the flow desk today. No second vendor ingest in Terminal; the
   Quote Hub *sheds* its vendor socket per §3.1b rather than gaining channels.
2. **D4 lift: commissioned, pending ratification.** The operator's 2026-08-08 ask
   names Terminal explicitly — that is the commission, and this plan treats it as
   intent. But D4 lives in the roadmap's plan-of-record, and plan-of-record changes
   move by ruling, not by inference from a commission. **TP-5 dispatch is gated on the
   ruling**: one line appended to `LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md` §6 (or
   operator confirmation on the TP-5 PR) recording the lift. Scope once lifted: desk
   mirrors + chart overlays + tape panels reading TP artifacts; a Terminal-native
   per-user streaming tick feed stays a later, measured decision
   (HOLD-IGNITION-SURFACES-adjacent caution: observational surfaces only).
3. Tier-gating server-side; debrand law (no vendor names user-facing); LIVE badges obey
   the measured-freshness law (a badge reflects data freshness, not transport
   liveness — the flow desk's ~48-min-loop lesson is the cautionary precedent).
4. Options intraday flow upgrades ride TP-7 cadence artifacts (existing OPRA
   entitlements), not claimed new options data.
5. Concrete TP-5 deliverables (each its own charting-app PR, spec-first per the
   design lane): (a) **Hidden Flow desk mirror** (off-exchange share, block tape,
   ATS-character context) beside the EOD belt it upgrades; (b) **on-chart DP levels +
   block markers** overlay toggle; (c) **equity time-and-sales pane** for Tier-A names
   (from rollup + block artifacts, honest cadence label); (d) hub migration off its
   vendor socket (§3.1b.2).

---

## §7 Options track — what Advanced changes and what it doesn't

Facts (2026-06-21 probe + TP-0 re-probe): options tape/quotes remain un-entitled unless
the manifest says otherwise; snapshot (OI/IV/greeks) + minute/day flat-file aggs remain
entitled. Therefore:

1. **Cadence, not tape:** an RTH snapshot pass every N minutes (politeness-tuned) on the
   GEX universe → intraday GEX/IV drift context (`intraday_greeks.py` exists; it gains a
   real intraday spot from TP-1 instead of delayed snapshot spot). Display-tier chips on
   gex.html / flow desks: "dealer gamma drifting long/short since open" as observed
   deltas, no forecasts.
2. **Equity-leg upgrades to existing options analytics:** live underlying spot for
   strike-distance/moneyness; NBBO spread context for the screener's liquidity columns;
   second-agg underlying bars under 0DTE charts.
3. **Signed options flow stays on the ThetaData production feed** (calibration ratified
   #1292; `DNR:HOLD-THETA-TAPE` suspends the Final3-lobes tape *lobe*, and TP builds no
   new lobes on the tape). M4 retires the databento crutch on the equity side only. The
   roadmap's P6 15-min tier earn-in now has its transport (TP-1 infrastructure + TP-7
   cadence artifacts) — the earn-in condition (demonstrated desk usage) is unchanged.
4. If the TP-0 manifest shows the options bundle DID change (any 403→200 on OPRA
   trades/quotes), §7 re-scopes by amendment with its own prereg — not silently.
5. **Procurement decision, explicitly deferred (operator's when demand proves):**
   Options Advanced ($199/mo, separate product) would add real-time OPRA trades+quotes —
   true live sweeps/blocks with NBBO signing, replacing the poller-loop cadence
   honestly. The trigger mirrors T3e's discipline: measured flow-desk usage + a written
   case that the ThetaData plane can't serve the demanded latency. Until then, no OPRA
   real-time claims anywhere.

---

## §8 Cross-engine integration map

| Consumer | Input from this plan | Contract |
|---|---|---|
| Prophet US (eyes-open/anticipation) | DP-share z, block/AH-block flags, signed-flow confluence chips | nullable columns + coverage floors; display until gauntleted |
| Breathing lane (BP W-L2) | real-time breadth artifact, second-agg opening structures | offered artifacts; BP owns presentation + evaluator use |
| Dark-pool desk | the entire intraday tier (§4.1) | desk page + forward ledger via nightly |
| Neural Web / brain | new synapse artifacts per §4; market_packet gains a compact "tape block" (aggregation-only, A7 intact) | synapse registry + lobe grades |
| Earnings/press wires | AH block joins, reaction-latency profiles | wire desks cite; no effect/beneficiary invention (TI-R5) |
| Mastermind (sister repo) | spread/impact curves, DP shelves as execution context | R2 read contract; execution receipts stay in that repo |
| Calibration Lab | every gauntlet verdict, promotion or null | below-the-fold receipts per falsifier-language law |

---

## §9 Risks, falsifiers, kill criteria

- **Feed discipline:** if the daemon cannot hold ≥ 99% session coverage over the pilot
  week (net of vendor outages), TP-2+ do not build; fix or re-home first (the gate is
  the feed, not the calendar).
- **Classification honesty:** if live quote-rule classification (vs the M4 historical
  join on the same days) disagrees on signed-notional sign for > 10% of name-days,
  signed surfaces stay dark until reconciled — magnitude-only ships regardless (the
  OPTIONS_FLOW precedent: direction soft, magnitude reliable).
- **Storage creep:** tick bucket > 2× the envelope TP-1's PR mints (tripwire inert
  until that number exists, armed the day it does) for 2 consecutive weeks → halt
  Tier-B, re-model, prune the §3.3 ⚡ stores (per-print archive + spool — the
  bounded-by-construction stores are not prunable remedies; one of them creeping is a
  producer defect). No silent growth: growth must trace to universe × days, nothing
  else.
- **Program-level falsifier (usage review):** at TP-3 merge and again at TP-6 merge, a
  measured usage review over every TP surface shipped so far — surfaces without
  demonstrated reads get retired or demoted to data-only, and the program halts
  surface expansion (data plane may continue) until something earns its screen space.
  HOLD-IGNITION-SURFACES exists because surfaces outran their gates; this program
  schedules its own reckoning instead of waiting for one.
- **Budget law:** any nightly step this plan adds that exceeds its declared minutes in
  the timings ledger for 3 consecutive nights → the step moves offrender or dies; the
  render budget is not negotiable.
- **Epistemic drift:** any TP surface caught asserting direction from unsigned share,
  emitting "validated", or advancing a forward ledger intraday → halt the wave,
  re-adjudicate against §2.4/§4.4 (these are the exact failure modes the estate already
  paid for once).
- **Vendor drift:** entitlement probe re-run (weekly cron + before each TP wave);
  a 200→403 regression freezes dependent waves and pages the operator (manifest diff in
  the alert).

---

## §10 Budget & storage math (bounded, revisited at TP-1 merge)

- **Render path:** +0 minutes (nothing in this plan touches render).
- **Nightly:** TP-2 rollup read ≤ 5 min (offrender/collect_tail); ledger accrual ≤ 1 min.
- **VPS daemon:** one WS connection, one core-ish decode budget at Tier A (pilot
  measures; Tier B only if headroom proves out), R2 egress trivial (rollups are MBs).
- **R2 (private plane):** Tier-A per-print trades expected low-GB/day pre-compaction at
  the 600-symbol cap — TP-1's PR replaces "expected" with the measured envelope that
  arms §9's tripwire; rollups MBs/day; blocks KBs/day. TP-B backfill sized before pull
  (flat-file LIST first, budget in the wave PR, hard cap declared) — never an
  unbounded crawl.
- **API:** unlimited-calls plan, but M2's politeness law governs concurrency; the probe +
  daemon share the existing key with no new key surface.

---

## §11 What NOT to build (standing rejections restated for this program)

1. No full-market raw quote retention (firehose; classification is in-flight only).
2. No standalone direction verdicts from share/ratio constructions (PSS-AF1 stays dead).
3. No user-facing "dark pool prints" labels on TRF data — off-exchange semantics with
   ATS attribution only where FINRA weekly provides it (R5).
4. No falsifier/refutation vocabulary user-facing; watch conditions only (07-27 law).
5. No vendor names on customer surfaces (debrand law); no paid payloads in the public
   repo (R2-private only).
6. No browser tick-streaming to end users until a measured-demand decision (mirrors the
   §7½ worker deferral); no per-user WS fanout in TP-1.
7. No indices/futures/fx/crypto claims (not entitled).
8. No LLM-originated signals/scores/escalations anywhere in the plane (A7).
9. No new schedulers on GHA for live cadences (jitter-disqualified; BP R6 metal law).
10. No re-cutting the PSS-AF1 tamper seal; new stores are new files, unions at read time.
11. No composite "institutional flow score" or fused regime dial from TP inputs
    (KILL-REGIME-SCORECARD / KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR — positioning
    fusion is illegal); per-signal chips only, composed only by the existing
    risk_radar→market_state chain.
12. No FMV usage (Business-tier only — not entitled); no Benzinga-endpoint assumptions
    ($99/dataset add-ons, not bundled).
13. No second real-time stocks WS client, ever (§3.1b single-connection law).
14. No predictive "igniting/warming" framing on any TP surface (HOLD-IGNITION-SURFACES
    boundary): desks state what printed and what is elevated vs its own baseline.
15. No "ticks" vocabulary in Prophet-adjacent features (KILL-FRESH-TICKS-WINDOW claims
    the word for admission sessions); tape/prints vocabulary only.
16. No "accumulation clusters" / "institutional prints" vocabulary anywhere — both
    assert actor intent/identity the tape cannot measure (the PSS-AF1 inference in
    fresh words). House terms: "repeat-print levels", "large prints".
17. No user-facing or Terminal-facing TP surface before the vendor terms are filed
    under `research/licenses/` (§0 global licensing gate).

---

## §12 Status log

| Date | Event |
|---|---|
| 2026-08-08 | Plan authored on operator commission; TP-0 probe + manifest shipped in the same PR; census lanes (repo, Terminal, registry, vendor) + live probe grounded §1–§6. |
| 2026-08-08 | Adversarial review (opus) returned HOLD: 4 blockers, 10 material, 8 minor — ALL accepted and folded pre-merge. Structural consequences: §0 gains the global licensing gate (B3) and wave TP-0.5 (B2/m1/m2); TP-1 now mints the PRIVATE R2 plane first (B1 — the existing publisher/beacon serve the public bucket only); the PSS-AF1 distinction restated on measured COVERAGE with signing accuracy explicitly unmeasured + a §4.4 accuracy-design prerequisite for any promotion (B4); stratified classification gates + TRF timestamp policy (M8); gap-heal quote replay + dedup key (M1); minute-of-session baselines (M2); in-wave split guard for TP-B (M3); part-file store layout (M4); 600-symbol cap + envelope-minting (M5/M6); §3.4 corrected to the additive `classify_print` contract with M4 sequencing (M7); tape-scoreboard D2/D6 tension named as amendment-proposal (M9); program-level usage falsifier at TP-3/TP-6 (M10); vocabulary bans extended (m3/m4); D4 lift marked ratification-pending (m8). Wave order is now TP-0.5 → TP-1. |
