# Breathing Platform Masterplan — live signals during the trading session

**Date:** 2026-08-08 (commissioned by the operator: "superintelligent should be
reactive and breathing and live during the trading day and not dead and asleep
using yesterday's stale data")
**Status:** PROPOSED — operator assessment pending. Nothing below is armed until
ratified; wave order and the §6 decisions are the operator's to set.
**Extends:** `research/LIVE_INTRADAY_DASHBOARD_MASTERPLAN_2026-07-29.md`
(ratified — not reopened), `research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md`
Part B (trajectory ruling), `research/PROPHET_LIVE_INTRADAY_SIGNALS_MASTERPLAN_BY_FABLE.md`
(P0/P1 shipped — this doc hardens and widens that lane).
**Does not create:** a SPA rewrite (rejected 07-29), a database migration of
canonical stores (§2-R2), a second forecast engine, or any change to the
epistemics laws (nightly = sole forward-ledger advancer; intraday lanes discard
`data/` writes — `DNR:KILL-INTRADAY-CHRONICLE`; LLM never originates signals).

Evidence base: five parallel audit lanes run 2026-08-08 (live-plane census,
Prophet engine anatomy, data layer, China Prophet census, infra/latency).
Load-bearing claims spot-verified in the main loop at
`engine/prophet_live/armed_pack.py:164-173`, `engine/signal_gate.py:93-100`,
`engine/us_board_rank.py:105-192`, `engine/prophet_live/live_states.py:440-534`.

---

## §0 ACCEPTANCE GATES (per wave, "not done unless")

**W-L0 (truth):**
1. The armed pack's probe is append-semantics (a probe at price X appends a
   session-D bar; it never replaces the as-of bar), G0.1 parity re-verifies
   against an APPENDED series, and a CI test pins the two semantics apart by
   reproducing (or refuting, with the measurement in the PR body) the audit's
   13/15 board-name flip on a frozen fixture store.
2. Cross-path fade has the same two-sided hysteresis + debounce the board path
   has; the current one-tick `faded` flip at +0.48% over `fade_hi_px` (pinned
   today by `tests/test_prophet_live_evaluator.py:172-175`) becomes a failing
   test in its old form.
3. One price basis: armed edges, live quotes, and the reconciler's
   `cross_px`/`close_same_day` are all explicitly same-basis (dividend-adjusted
   vs raw named at every seam), with a startup assertion comparing the pack's
   `as_of_close` to the quote feed's `prev_close` per name.
4. The freshness sentinel carries a Prophet surface (candidates stamp +
   `site/prophet/index.json` asof vs the exchange calendar) — the 08-05→08-08
   freeze class alerts within 26h from outside GitHub. The `engine` job writes
   native W2 timing rows (its finish-step silent-fail is fixed); an engine row
   appears the first green night.
5. `dormant` never asserts over an unprobed region: the down-band is probed or
   the state is labeled unknown below the probe floor.

**W-L1 (evening SLA):** fresh US picks (provisional close-pass board) live on
the site by **18:30 ET** on five consecutive green sessions, measured by the
sentinel's own stamps; the provisional→nightly confirmation delta is published
per name; no `data/` writes from the close-pass lane.

**W-L2 (breathing board):** intraday states cover the full candidate universe
(not 45/109 + 54/1631); a new-signal alert (site chip + at least one push
channel) fires within one evaluator cadence of a confirmed cross, with a
measured precision floor registered BEFORE send-enable (G0.8 discipline); zero
one-tick public state flips (CSP-R2).

**W-L3 (China same-day):** a CN cross during the CN session surfaces as a
provisional state + alert during that session (01:30–07:00 UTC), armed from the
prior asia-close pack; CN repaint rates (T2 8.8% US-measured / 15.1% CN) are
disclosed on the surface; the asia ledger stays nightly-single-writer.

**W-L4 (platform):** per-source collect attribution rows exist in the timings
ledger; at least two day-cadence collector migrations shipped with the nightly
band measurably smaller; the DuckDB read-only lane converts ≥1 measured hot
scan (first target `qledger-ccw`, 59.2m) with before/after in the PR body;
module-level engine caches on any resident-service path are mtime-keyed.

---

## §1 What the audits established (evidence, compressed)

**Delivery latency is structural, not flakiness.** Cron waits until 22:30Z for
the ~6pm-ET FINRA short-volume file (`daily.yml:5-16`); `collect → engine` is a
4h40m serial floor (collect 144.9–151.4m measured; engine 135–205m). Best green
night = picks ~11:13pm ET; even a hypothetical 20:05Z fire = 8:45pm ET.
Consecutive nightlies now self-serialize (`concurrency: pipeline-daily`,
`cancel-in-progress: false` — run 31226002132's collect started 15s after run
31210097197's last job ended). Only decoupling the pick path from the full
chain fixes the complaint.

**The US board score is 100% price-derived.** `SCORE_WEIGHTS`
(`engine/us_board_rank.py:105-111`): signal 30 / entry 25 / edge 25 / runway 10
/ quality 10 — all computed from close series and cross-sectional price panels.
Options OI/GEX, short volume, fundamentals/SUE/insider, smart money, macro
prints: **zero score authority** (`ZERO_SCORE_AUTHORITY`,
`us_board_rank.py:174-192`; `data/gex/gate.json` `scored:false`). Intraday
rescoring is a price-basis and bar-semantics problem, NOT a data-availability
problem. No macro print touches a Prophet score today (§2-R3).

**The shipped Prophet-Live lane is the right skeleton with a wrong core
identity.** Nightly arms per-name buyable price intervals; a VPS systemd timer
re-evaluates every ~5 min during RTH at ~0.5 CPU-s/pass; states are debounced,
published display-tier to R2 + same-origin, never to `data/`; the nightly
reconciler is the only grader. But the probe REPLACES the as-of bar
(`armed_pack.py:164-173` — docstring: "the provisional close IS today's close,
not an extra bar") while tonight's gate runs on an APPENDED session bar. The
audit measured 8.0% of grid points disagreeing between the two semantics, and
**13 of 15 as-of-buyable board names flip to NOT-buyable under append** —
freshness ticks advance and reclaim-and-hold resolves on the next bar, so
replace-probes systematically over-claim. The G0.1 parity gate feeds the close
back through the same replace-probe, so it cannot see this axis. The P1 promise
("the same test tonight will apply already passes at this price") is currently
false for most board rows. Fixing this is W-L0 #1. (Magnitude is one store
snapshot, n=15; the mechanism is deterministic and source-verified.)

**Other live-lane defects (audit F2–F8, spot-verified where cited):** one-tick
`faded` on upper-edge overrun (`live_states.py:517-526` protects only the
lower band); mixed price basis between adjusted armed edges and raw quotes —
including inside the ledger statistic `fill_vs_cross_pct`
(`scripts/reconcile_prophet_live.py:151-160,292-296`); the evaluator returns
exit 0 on every exception with no heartbeat watcher (`prophet_live_evaluator.py:458-463`
— a green run with nothing behind it, the class W1 exists to kill); `dormant`
asserts over a never-probed down-region; optimistic `forming` default on a
board name's first pass; 5× universe re-IO inside the 420s arm budget that
already caps coverage at 45/109 board + 54/1631 cross candidates
(`config.yml:729-740`).

**Sentinel blind spots (found live during this audit).** The current freeze is
Prophet-specific: `data/us_prophet_rank/candidates/2026-08.parquet` stamps
2026-08-05, `site/prophet/index.json` asof 08-06, while `site/us_stocks.html`
re-bakes fresh daily on top (the exact re-stamp trap the sentinel doc names).
0/7 concluded nightlies green since 08-05 (engine killed at cap 08-05/08-06;
every Prophet writer sits behind `needs: engine`). The sentinel has **no
Prophet surface** (`scripts/freshness_sentinel.py:143-172`), us_stocks emits no
`prices as of` marker (delay branch never evaluates), and the `engine` job is
the only one of 16 with zero native timing rows (finish-step failures are
`::warning` + `exit 0`). The tripwire built after the Jul-31→Aug-6 outage
cannot fire for the job that caused it.

**Collect is decomposable and mostly already idempotent.** 178 registered
adapters run inside ONE opaque step (`scripts/collect.py` specs list;
`daily.yml:226-299`), invisible to dag conformance and the timings ledger;
per-adapter `elapsed_sec` already exists in `data/run_status.json`. Adapters
run serially by design (akshare segfaults under threads; vendors throttle) — a
faster machine buys nothing; per-source cadences do. Idempotency (dedupe /
windowed overwrite / first-writer-wins) verified across the majority of
sources; genuinely post-close sources are few (FINRA short volume ~6pm ET,
hk_cbbc ~18:30 HKT, massive_stock_day T+1, OI by settle-buffer convention) —
and none of them carry score authority. Precedent: `capital_structure` split
out 2026-08-06 (#4746 class).

**Data layer ruling inputs.** `data/` = 37,571 git-tracked files, 13,881
parquets, 2.3 GB; "the repo is the database" (`lib/store.py:1`). 3,635
`read_parquet` sites across 1,321 files; only 150 files use `lib.store`. Git
provides PIT auditability, cross-lane concurrency safety (rebase-retry),
single-writer enforcement, and DR. The hot live layer is **116 KB across 15
JSON files**, atomically published. SQLite already in production for derived
indices; no DuckDB/Postgres/Redis anywhere. ~19 module-level engine caches have
no invalidation (`ai_desk._CLOSE_MEMO`/`_BREADTH_MEMO` never cleared — safe in
batch, fatal in a resident service); the in-house fix idiom exists
(`earnings_qual` mtime-keyed cache). `lib/store.py:102` writes parquet
non-atomically — survivable single-writer, first thing to break under
concurrent writers.

**China.** CN Prophet's score needs zero tushare (confluence gate is close-only
by construction; tushare darkness stales 4 display badges only). Yahoo spark
already serves `.SS/.SZ/.HK` keyless (~0–15min delay) and already runs during
CN hours for the china risk-state lane (`vps_live_orchestrator.py:313-320`,
01:00–09:00 UTC weekdays). asia-close arms nothing today and rides FOUR
staggered GH crons against measured 86–233min fire lag; board live ~10:15Z
steady-state vs next CN open 01:30Z. Nothing prophet_live references CN.
The china.html delayed-board disclosure already shipped (#4812).

**Fleet.** 5 self-hosted mac hosts (mac-builder-1/2/3 = M1 incl. theta-m1;
4/5 = M2) are **idle through the entire US session** (PR CI runs on
GitHub-hosted `ubuntu-latest`; nightly occupies ~22:30–09:30Z). A separate
`macstudio-light` box already carries RTH intraday lanes. VPS = 2 vCPU /
3.8 GiB / 77 GiB (38 free), 4-vCPU tier already planned in
`docs/VPS_LIVE_ORCHESTRATION.md`. ThetaData Terminal is single-session with a
~60 GB M1-local store; per operator (2026-08-08): a VPS re-home is permissible
if needed but requires a VPS storage/RAM upgrade — carried as §6-D3, not
assumed. GHA scheduling jitter measured 35–58min (daily cron→run-created) and
86–233min (asia early-bird): disqualified as the scheduler for any intraday
cadence. render-linux is ONE box (pc-render-1, WSL2), not four — CLAUDE.md's
fleet line is stale.

---

## §2 Rulings (the operator's questions, answered)

**R1 — "Can we compute live signals during the session?" Yes.** The score is
100% price-derived, the rescore is ~3 orders of magnitude cheaper than the
render (0.5 CPU-s vs 24–62min), the compute (idle macs + VPS) and the delivery
plane (R2 + same-origin JSON + hydrators) already exist, and the epistemics law
already has a compliant shape for it (provisional display-tier states graded
nightly). What stands between today and "breathing" is the W-L0 truth fixes,
coverage, alerts, and CN wiring — engineering, not architecture.

**R2 — "Do we need to move from parquet to a database?" No.** Canonical
vintages/ledgers stay parquet+git+R2 (git IS the PIT ledger and the
concurrency control; a second canonical store is the named degenerate form,
`DNR:KILL-PARALLEL-KNOWLEDGE-BASE`). The hot intraday layer stays lastgood
JSON (116 KB; atomic; proven). The one addition worth making: **DuckDB as a
read-only query engine** over existing parquet globs for measured hot scans
(first: `qledger-ccw` 59.2m; then the `stock_library` creep) — derived,
rebuildable, deletable, no write path, no law surface. Prerequisite for any
resident engine process: mtime-keyed cache invalidation (W-L4).

**R3 — "Macro prints (CPI/NFP) changing a stock's score intraday."** Today no
macro print reaches any Prophet score (zero score authority — verified). The
release watcher already detects prints in ~1 min and the regime/risk chips
already move display-tier. Wiring prints INTO score authority would be a new
scored input → that is promotion-gauntlet territory (pre-registered, graded),
not a live-transition feature. The lawful immediate form: prints update the
live risk/regime context chips and can re-prioritize the WATCH ordering of the
provisional lane (display-tier), never mutate scores. If a print-conditioned
score leg is wanted later, it gets its own prereg.

**R4 — "Risk events de-risking the board intraday."** Auto-removal is ruled
out: board membership is authority-tier (nightly), and the forced-liquidation
classifier idea was tested and KILLED phase-0
(`DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`; tape-grade features blocked on
entitlement). The lawful form ships in W-L2: the live risk state (already
computed every ~2min) badges the board — "risk elevated — de-risk watch" — with
the mandatory 2-tick debounce + pending-escalation badge
(`DNR:KILL-ONE-TICK-ESCALATION`), plus an alert kind. Users get the warning in
minutes; the ledger records what the nightly confirms.

**R5 — China gap-up capture.** Port the armed-pack + evaluator pattern to the
CN session (W-L3): arm at asia-close (~10:15Z, 15h before next CN open),
evaluate every 5 min during 01:30–07:00 UTC against Yahoo spark quotes the
product already polls. No new vendor. A CN confluence cross then surfaces
DURING the session it fires in — enter intraday, hold through the next-day gap
instead of buying it. Tushare token reissue (operator) restores 4 display
badges; it gates nothing here.

**R6 — Orchestration & hardware.** All cadenced lanes run on OUR metal
(systemd: VPS for quote-driven lanes; macs for theta/options and heavy
close-passes, publishing to R2), GHA keeps only CI + the authority nightly.
This is the pattern that survived the 08-06 GitHub outage. No new hardware is
required through W-L3: the 5-host mac pool is idle exactly when the breathing
lane needs compute. The M2 Studio stays the operator's; the PC stays a render
spare.

---

## §3 Target architecture — three cadences, one engine

1. **Authority (nightly, shrinking):** collect stragglers, advance ledgers,
   grade yesterday's provisional states, re-arm packs, rebuild pages. Every
   island the live plane absorbs is DELETED from the render path (the 08-06
   Part B contraction rule; falsifier B5-2 stands).
2. **Provisional close-pass (new, ~16:15–17:30 ET):** on session close, a
   mac-side pass recomputes ADMISSION + the price-derived score legs over the
   full universe from the day's closes (which need no FINRA/OI/fundamental
   inputs — zero score authority), publishing a **provisional board** to the
   live plane: "tonight's picks, pending nightly confirmation." This is the
   evening-SLA fix: picks by ~18:30 ET instead of ~11pm–1am ET. The overnight
   nightly remains the single writer of record; its confirmation/divergence
   per name is published (integrity metric, free).
3. **Breathing lane (existing, hardened + widened, ~5min RTH):** append-
   semantics crossing states over the full candidate universe; partial live
   rescore of the legs that move intraday (signal 30 + runway 10 pts — the
   stage bucket that dominates sort order); risk-overlay badges; alert
   dispatch (site chip → email/push per §6-D5) on confirmed transitions only
   (2-pass debounce, precision floor pre-registered).

Provisional never touches `data/`; every provisional surface names itself
provisional (the P1 "settles at tonight's close" language stays); nightly
grading of intraday states remains the only track-record input (§5).

---

## §4 Waves

**W-L0 — TRUTH (first, small, high-severity).** Fix the shipped lane before
widening it: append-semantics probes + de-tautologized G0.1 + CI pin (gate
§0-1); symmetric fade hysteresis (§0-2); one price basis incl. the reconciler
(§0-3); prophet surface in the sentinel + engine W2 native rows (§0-4);
dormant honesty (§0-5); conservative first-pass default. NOT in scope: the
confluence PIT latch — open PR #4964 owns it (cite, don't duplicate). Also
file the November DST cron race (`daily.yml:10-11`) with the nightly owners.

**W-L1 — EVENING SLA.** The close-pass provisional board (§3-2) on the idle
mac pool; publish via R2 → VPS. Alongside: emit per-source `elapsed_sec` from
`run_status.json` into the collect timings bands (attribution BEFORE
decomposition), then move the first day-pollable collectors (news, filings,
wiki_pageviews-class) onto day cadences under their existing idempotency.
Gate: §0 W-L1.

**W-L2 — BREATHING BOARD.** Full-universe armed coverage (kill the 5× re-IO,
raise/parallelize the 420s budget on mac-side arming); live partial rescore
(signal+runway) each cadence; `prophet_forming`/`prophet_confirming` +
`risk_derisk_watch` alert kinds through `notify_turn_events` → email first,
web-push after; measured precision floor registered before send-enable.
Gate: §0 W-L2.

**W-L3 — CHINA SAME-DAY.** CN armed pack in asia-close; CN evaluator window
01:30–07:00 UTC on the VPS (Yahoo spark, freshness ceiling honest about the
0–15min delay); CN repaint disclosure; gap-up capture measured (cross-time vs
next-open price, published). Gate: §0 W-L3.

**W-L4 — PLATFORM.** Collect decomposition to per-source systemd/workflow
cadences (the monolith shrinks toward the genuinely post-close residue);
DuckDB read-only hot-scan lane; mtime-keyed caches for resident services;
`lib/store` atomic-write fix; §6-D2/D3 upgrades if ratified. Gate: §0 W-L4.

Dependency spine: W-L0 → W-L1 → W-L2 → W-L3 (CN reuses the hardened core);
W-L4 runs alongside from W-L1. Every wave lands as normal PRs under the ship
loop; each migration PR body carries measured minutes reclaimed (B5-2).

---

## §5 Track-record law (era discipline — binding)

Intraday alerts and provisional boards are display-tier timestamps. The
forward ledger's entry definitions DO NOT CHANGE with this program: advertised
performance never uses intraday alert prices unless/until a separately
pre-registered intraday ledger accrues and matures through the gauntlet. The
existing `reconcile_prophet_live.py` nightly grading stays the sole spine; the
W-L0 price-basis fix is prerequisite to trusting its `fill_vs_cross_pct`. Any
era boundary this creates for published numbers routes through the OPEN
track-record era-break decision (operator, due since 2026-08-07) — this
masterplan does not move any anchor by itself.

## §6 Operator decision menu

- **D1:** Ratify waves W-L0…W-L4 (or re-order; W-L0 is not skippable).
- **D2 — real-time quotes:** Polygon plan upgrade + deploy the existing
  worker websocket seam (removes the 15-min delay floor for US). Without it,
  "live" honestly means "~15–25min-lagged states" — already useful; the
  upgrade is a product-quality call, price to be checked at decision time.
- **D3 — VPS tier:** 4-vCPU upgrade (already planned) for the widened live
  lanes; separately, optional ThetaData re-home to VPS (needs ~60GB+ disk and
  RAM headroom — operator 2026-08-08: permitted if needed) vs keeping the
  proven mac→R2→VPS path. Default: keep mac-side; revisit at W5 hardening.
- **D4 — tushare token:** reissue at tushare.pro + update `TUSHARE_TOKEN`
  secret (restores 4 CN display badges; independent of this program).
- **D5 — alert channels:** email first (infrastructure exists), web-push as a
  follow-on; both behind the measured precision floor.
- **D6 — era coordination:** confirm §5 (no anchor moves; intraday ledger only
  via prereg).

## §7½ Massive Stocks Advanced addendum (2026-08-08, post-ratification)

Operator upgraded the market-data plan (Massive, née polygon.io — "Stocks
Advanced": real-time, unlimited calls, trades/quotes, second+minute aggs, 20y+
flat files, websockets, snapshot, reference, corporate actions, financials;
business licensing included) and enabled real-time. Entitlement **verified
live 2026-08-08 ~06:50Z**: `v3/trades` and `v3/quotes` flipped 403→200 (both
were documented entitlement-blocked in `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`'s
still-open clause), second aggs / snapshot / financials / splits all 200, and
the trades tape is current through the prior session's 20:00 ET after-hours
close. S3 flat-file probes: `us_stocks_sip/day_aggs_v1` EXISTS back to
**2006-03-15** and `minute_aggs_v1` to at least **2010-06-15** —
`collectors/massive_stock_day.py:143` `EARLIEST_ENTITLED = 2021-07-06` is now
provably stale. Full touchpoint census (19 stale "15-min delayed" label sites,
8 old-plan rate guards, key-injection map): run 2026-08-08, summarized here;
sites enumerated in the census tables carried in the PR #4975 discussion.

**M-waves (slot alongside W-L1+; each is a normal ship-loop PR):**

- **M1 — real-time honesty flip (first; user-facing).** Add
  `scripts/verify_massive_realtime.py` (snapshot lastTrade/min-bar age vs wall
  clock, must run during premarket/RTH); on measured proof, flip
  `config.yml:618-627` `delayed_min: 15→0` + `feed_label`, the derived
  evaluator ceiling (`quote_max_age_min` 25→slack-only), and every label site
  the census lists (most read config; the hardcoded template token generators
  in `dashboard.html.j2` / `sector_central.html.j2` / worker header / docs flip
  in the same PR — honesty is atomic). Gate: probe output in the PR body,
  captured during market hours.
- **M2 — old-plan guard re-tunes (measured, not blind).** `polygon.workers`
  5→measured, `build_polygon_universe` 0.22s pacing, `polygon.intraday.sleep`,
  `max_underlyings: 375`, `massive_stock_day` `max_days: 40`. Unlimited calls
  ≠ unlimited politeness: raise stepwise with observed error rates in the PR
  body.
- **M3 — history extension.** `EARLIEST_ENTITLED` → 2006-03-15 (evidence
  above); staged day-aggs backfill (~5k sessions × ~140–200KB gz ≈ ~1GB —
  trivial); minute-aggs optional (~13MB/day ≈ ~50GB to R2, fetch-on-demand
  acceptable). NOTE the era law: any breadth/threshold recompute over the
  widened window is a measurement-era change — pre-register before touching
  published thresholds ([[measurement-lens-reassessment-protocol]] class).
- **M4 — tape adoption (research-grade).** `engine/flow_signing.py` tick-rule
  → NBBO quote-rule via `quotes_v1`; retire the `collectors/databento_tbbo.py`
  calibration workaround; reopen the LSR tape-grade lead (signed order
  imbalance, price-impact-per-signed-dollar, true spread) ONLY via a fresh
  prereg per the DNR row's own reopener clause.
- **M5 — new collectors (display-tier first).** Corporate actions
  (splits/divs → capital-structure event spine + adjustment-basis truth — also
  the durable fix direction for the W-L0 price-basis class), fuller reference
  data (sector/share-class enrichment), financials & ratios as an
  EDGAR-supplement. Vendor technical indicators: skip (house computes its own).
- **Websocket ruling:** with real-time REST verified, the Durable-Object
  websocket build is OPTIONAL, not the critical path — M1's flip needs no new
  infrastructure. The undeployed REST worker proxy remains a cache/edge
  decision, deferred until W-L2 measures browser-side needs.

## §7 Falsifiers / kill criteria

- Provisional close-pass disagreeing with the nightly on >5% of board
  membership over any rolling 10 sessions → halt W-L2, audit the basis/
  semantics before widening (the divergence metric is published either way).
- An island migration that does not shrink the engine band → cargo cult; stop
  (restates 08-06 B5-2).
- Any wave requiring the live plane to advance a forward ledger → drifted into
  violating the epistemics law; halt and re-adjudicate (restates B5-3).
- Alert precision floor unmet at measurement → alerts stay dark; shipping them
  anyway is forbidden, not delayed.
- If W-L1 cannot beat 18:30 ET on green sessions, the close-pass thesis is
  wrong somewhere measurable (universe IO, gate cost, publish path) — profile
  and re-rule before W-L2 rather than re-budgeting caps forever.
