# MARKETING HOT TAPE — attention-driven, intraday-first content

Operator directive 2026-07-28 (verbatim intent): *"We should be reporting on
tickers that are very hot… people want live data as it happens… when
semiconductors and memory are all down big during market hours, early into the
day, we should already be posting lists… This stale data issue is so serious."*
Same day the operator supplied a 20-post reference corpus from their timeline
(§2) and ruled: sensational reporting on names people know beats signals on
obscure names; posting during market hours on live data is the product.

Program name: **Hot Tape**. One sentence: a 5-minute intraday loop that turns
live tape events on high-attention names into wire-voice posts with charts,
booked to X within minutes of the event, while the nightly pipeline keeps the
persona desks' proof-of-work content.

## §0 ACCEPTANCE GATES — not done unless

1. **Latency**: on a day a sector crosses ±2% (median, breadth ≥70%) during
   RTH, a sector post is BOOKED at Buffer within **20 minutes** of the cross.
   Same bar for a |≥4%| move on a top-attention name. Demonstrated in the PR
   with a real fired event: detector log line → outbox item id → Buffer
   receipt, timestamps visible.
2. **Differentiating stat**: every Hot Tape post carries ≥1 device from §2.D —
   a "since <date>", a streak count, a dollar translation, or a record/rank.
   A bare "%-move + chart" post is the corpus's 95-view flop; the template
   layer must structurally refuse it (test-pinned).
3. **Facts are engine-computed**: every number in the copy exists in the
   item's FactPacket (provenance-committed). The copy layer (template or LLM)
   may phrase, never originate. Numeric-consistency check is a hard gate,
   test-pinned. [Epistemics law: LLMs never originate signals.]
4. **Observations, not calls**: Hot Tape items carry NO entry/buy/sell/added
   language. "Reporting the tape" is display-tier and needs no gauntlet;
   a directive call on an un-gauntleted read is the Mag-7 killed class
   (DO_NOT_REBUILD: operator force-add kill, 2026-07-23). Test-pinned ban
   list on the wire templates.
5. **Existing safety stack untouched**: sentinel near-dup/caps, post-time tape
   gate, kill switch + recall, per-ticker cooldowns (one post per ticker per
   direction per 2h unless the move doubles), sector once-per-direction-per-day.
6. **Charts on every ticker post** (operator law): single-name events reuse the
   v2 tape card; sector events ship the sector grid card (Phase 1.5) or a
   clean list format until it exists.
7. **CI**: every new suite named in a run line in BOTH lanes it belongs to,
   plus ci.yml trigger paths for every new file — a suite that ships dark is
   the unrun-suite rot class.
8. **Measured, then tuned**: every Hot Tape item's provenance carries its
   trigger type; the metrics poller already returns per-post impressions.
   After 7 days, a per-trigger engagement table exists (even a crude one) so
   weights move on evidence, not taste. "Today"-keyword hypothesis (operator)
   gets an A/B cell here rather than an assumption.

## §1 Why volume alone failed (diagnosis, 2026-07-28)

Selection was supply-driven: nightly Prophet plans on quality-filtered
small/mids (LKFN, CVI, CBOE) — names with no search volume, posted 12–40h
stale through a ladder. Engagement follows attention; attention lives on
household names, big movers, earnings, and NOW. Meanwhile the intraday
machinery that existed was dark or strangled:

- `publish_time_content` generated sector/theme lists from live quotes every
  30 min — Semiconductors, Software, FinTech, on the semis-crash day itself —
  and **100% died at the theme ramp** (no desk past week-5).
  Fixed 2026-07-28: #3932 (bool account_overrides + flagship grant).
- `marketing_fastlane_daemon` (earnings + press lanes): **never ticked** — no
  heartbeat file, no workflow, no MARKETING_FASTLANE_ENABLED anywhere.
- Prophet levels are computed nightly and never re-armed intraday: a level
  crossed at 10:04 AM is our own proprietary event, currently unused.

Repositioning (operator-endorsed): Prophet obscure-name posts move to the
RECEIPTS/track-record job at lower cadence (wins on names nobody covers =
proof of alpha); Hot Tape does reach. Reach pulls followers; receipts convert.

## §2 The corpus (operator timeline, 2026-07-28 — a semis-crash day)

20 posts transcribed; engagement recorded. The teachable structure:

**T. Triggers** (what makes them post):
- T1 big intraday move, household name (AMD −10% "so far today", 56K views;
  KO +6%, PLTR −10%)
- T2 threshold/milestone cross (QQQ "ENTERS CORRECTION WITH 10% DROP FROM
  RECORD", 49K; AAPL "second company in history to hit $5T", 29K; META below
  $600 "for the 10th time this year"; NVDA "$1 TRILLION wiped out… −18.5%
  from ALL TIME HIGH", 23K)
- T3 historical rarity/streak ("META has not seen a double digit streak of
  red daily candles in over 5 years. Today is Day #9", 46K; "TSLA falls to
  its most oversold level since March 2025", 26K; "Oracle's credit risk HAS
  NEVER BEEN HIGHER" + CDS record, 24K)
- T4 earnings reaction in minutes ("$BE is up over 12% AH after a monster
  quarter. Top and bottom beat." + numbers in the reply)
- T5 event anticipation ("Tomorrow is going to be a historic day… ~30% chance
  of a hike… nearly every Fed meeting since March 2020 entered decision day
  with ~99% consensus… We think the Fed PAUSE continues" — **312.7K views,
  corpus winner**)
- T6 sector/market aggregation in dollars ("$820,000,000,000 added to the US
  stock market in the last 3 hours as mediators say…", 85K, heatmap image)
- T7 unusual options flow ("Very unusual $SOXX Call Flow Detected. They are
  buying the semiconductor dip", 57K)
- T8 narrative irony / since-event anchor ("Marvell down almost 50% since
  Nvidia CEO Jensen Huang said it will be the next trillion dollar company")
- T9 contrarian breadth flip ("'The markets crashing' the market:" + a list
  card of GREEN defensives — COST HD MMM KO MCD…)

**D. Devices** (how the copy is built):
- D1 number stacking, zooming out: "−17% on the day, now −30% in 5 days and
  −55% from its record high. That's officially over −$200 billion in lost
  market cap since June 22nd." (Kobeissi SNDK, 614K)
- D2 dollar translation: "investors now pay ~$215,000 annually to insure
  $10 million of Oracle debt"; zeros written out for scale ($820,000,000,000)
- D3 "since <date/event>" on nearly every winner — recency-rarity quantifier
- D4 streak/count: "Today is Day #9"; "10th time this year"; 🔴×10 (one per
  percent down — emoji as data)
- D5 live markers: "so far today", "right now", "just became", BREAKING/caps
  for wire items
- D6 superlative + receipt: record claim immediately backed by the number
- D7 stance or question ender: "We think the Fed PAUSE continues tomorrow";
  "Why $AMZN wouldn't work from here?"
- D8 pseudo-official milestone language: "officially", "enters correction"
- D9 one chart, one story; annotation sparing

**The control case**: Mimo's $MU post — same trigger as Kobeissi's SNDK on the
same day's memory-sector crash (−9%!), zero devices, hedged ("seems like it
will keep dumping") — **95 views vs 614K**. Execution, not access, is the moat.
The differentiating stat IS the product; gate 0.2 encodes it.

**Voice note**: wire tone is declarative, unhedged, numbers carry the drama.
Persona desks keep their diary voice for nightly content; Hot Tape speaks wire.
`mastermind_news` (Buffer channel configured, zero use to date) is the wire
desk's home; flagship mirrors the biggest events only.

## §3 Architecture

Two speeds, one skeleton — heavy compute nightly, light joins intraday
(render budget stays law; intraday lanes stay OFF the render path):

1. **Nightly context pack** (new; runs inside the existing marketing step):
   for every liquid name in `data/massive_stock_day` (~20k parquets, floor by
   ADV/mcap to ~2–3k), precompute the stat kit the devices need: 52w/ATH
   distance, consecutive up/down days + how rare (last time a streak this
   long), biggest 1d/5d moves of the past year with dates, MA relationships,
   RSI + last-time-this-oversold date, round-number and correction/bear
   thresholds adjacent, mcap + shares (for $-translation), earnings date/time
   from `data/earnings/earnings.parquet`. One compact JSON, no pandas needed
   to READ it.
2. **Attention radar** (new workflow `marketing-hot-tape.yml`, */5 during
   13:25–20:05Z weekdays, ubuntu, shallow checkout, pyyaml+requests only):
   load live quotes (the same three-source merge the tape gate uses) + the
   context pack → run detectors → fire events.
   v1 detectors: `sector_rout/rip` (median + breadth from heatmap sectors),
   `mover_pop/drop` (|Δ|≥4% on attention-universe names), `threshold_cross`
   (correction/bear/ATH-distance/round-number/mcap milestone),
   `streak_rarity` (today extends a streak the pack says is ≥N-year rare),
   `signal_fired` (live price crosses a Prophet plan level — our proprietary
   event, links to the site), `contrarian_breadth` (index red + defensive
   sector green, the T9 flip). Persist a rolling intraday snapshot ring
   (last ~36 × 5-min) in the workflow's commit to enable "$X added in 3
   hours" claims (T6) and re-fire suppression.
3. **Wire copy layer**: FactPacket (typed, all numbers) → template families
   per trigger with the §2.D device library; every template REQUIRES its
   device slots filled or it refuses (gate 0.2). Phase 2: LLM phrasing via
   the shared AI provider waterfall behind the numeric-consistency gate
   (gate 0.3) with template fallback on any failure. [Coordinate with the
   in-flight word-salad copy session — template mechanics are theirs; the
   trigger/device taxonomy and wire voice are this program's.]
4. **Delivery** (exists): enqueue `kind="breaking"` `scheduled_at="immediate"`
   → immediate items are floor/cap-exempt and unjittered (2026-07-27 re-spec)
   → self-dispatch `marketing-publish.yml post_now_item=<ids>` → ~2–3 min to
   Buffer post-shallow-checkout. End-to-end latency = detector cadence
   + radar runtime (~1m) + dispatch (~3m). **The ≤5m detector cadence this
   assumed does not exist** — GitHub delivers ~1.4 of this lane's 92 daily ticks
   per hour, so the honest figure is ~17 min mean / ~50 min tail with the shipped
   multi-pass loop, against gate 0.1's 20 min. Measurements, options and the
   recommended fix are in §3.6; do not quote a latency from this bullet.
5. **Charts**: single-name → v2 tape card (extend `_PRICE_SUBDIRS` to
   `data/massive_stock_day` so ANY liquid name renders); sector → new grid
   card (tiles + % + logos, Phase 1.5); market-wide → heatmap image reuse.
   R2 upload at raster time (media backfill lane is the recovery path).

**Consolidation**: the never-run `marketing_fastlane_daemon` earnings/press
lanes fold INTO the radar loop as detectors (one intraday loop, N detectors)
rather than reviving a separate daemon. Its emit/dedupe plumbing is reusable.

### §3.6 Trigger strategy — GitHub cron cannot deliver the 5-minute cadence

§3.4 assumed "detector cadence (≤5m)". That assumption is false, and it is the
remaining structural gap against gate 0.1.

**Measured, 2026-07-29, the 13:00–21:00Z window.** GitHub delivered **104
scheduled runs across ALL 46 scheduled workflows in this repo** — about 13 an
hour for the whole estate. Per lane, against ticks asked for:

| lane | scheduled | delivered | rate |
|---|---|---|---|
| live-quotes (`*/5` + `*/15`) | 128 | 11 | 8.6% |
| marketing-hot-tape (`*/5`) | ~92 | 6 | 6.5% |
| vps-live-heartbeat (`*/10`) | 48 | 6 | 12.5% |
| merge-on-green (`*/10`) | 48 | 6 | 12.5% |

Every high-frequency lane lands at **~1–1.5 runs/hour regardless of how many
ticks it asks for**. `startedAt == createdAt` on every run, so nothing is
queuing — GitHub simply never creates the runs. This is a known standing
condition here, already recorded for the merge sweeper (memory:
`merge-on-green-sweeper-cron-starvation`), and it is why "the cron says `*/5`"
has never been evidence about cadence.

**What that does to gate 0.1.** At 1.4 passes/hour the mean detection gap is
~43 min, so a random cross waits ~21 min before the radar even looks, plus ~1
min radar and ~3 min dispatch→Buffer: **~25 min mean, ~47 min tail.** Gate 0.1
asks for ≤20 min. The gate was unreachable before a single line of detector code
ran.

**Options assessed.**

1. **Fewer, denser crons** — no. The delivery rate is per-lane and roughly flat;
   re-shaping 92 ticks into 30 does not raise the ~1.4/hour floor, it only
   coarsens the schedule we fail to get.
2. **More crons** — untested and probably no. Delivered counts (5–11 per lane per
   8h) track lane count far more tightly than requested-tick count, which points
   at a per-lane floor rather than a proportional share of a repo budget. Not
   worth spending the estate's schedule budget to find out.
3. **In-run multi-pass** — shipped 2026-07-30 as a stepping stone, then
   superseded by 5 the same day. Bounded to 3 passes it took the mean to ~17 min
   but left the tail untouched, because the passes cluster and the ~33-minute
   holes between delivered ticks remain.
4. **External `repository_dispatch` ticker** (Mac Studio launchd timer) — an exact
   cadence and near-zero Actions cost, but it needs a **fine-grained PAT with
   `actions:write`** (GITHUB_TOKEN does not exist outside Actions) and puts a
   product dependency on the render-pool host. The PAT is operator-only work.
5. **Session-long poller — CHOSEN AND SHIPPED (operator delegated the call
   2026-07-30).** One bootstrap tick runs the lane as a session: a 2-entry matrix
   with `max-parallel: 1` gives two serialized halves (a GitHub *job* caps at 6h;
   the window is 6h50m), each looping every `PASS_INTERVAL_S` until the ET window
   closes or its own `JOB_BUDGET_S` is spent. **True 5-minute cadence, so the whole
   latency distribution is compliant rather than just the median.**

**Why 5 over 4 — and a correction.** An earlier draft of this section priced 5 at
~$77/month and 4 at ~$23/month and recommended 4 on cost. **Both figures were
wrong: this repo is PUBLIC, and GitHub-hosted runner minutes are free and
unlimited for public repositories.** Cost was the entire case for 4, and it does
not exist. What remains is that 4 needs a credential and a host and 5 needs
neither — so 5 wins outright.

A self-dispatch chain of short runs was also considered and rejected: it would
rest on the GITHUB_TOKEN `workflow_dispatch` carve-out, and nothing in this repo
demonstrates that carve-out working. `metabolism-cycle.yml` writes exactly such a
chain, yet every one of its `workflow_dispatch` runs was human-triggered. `sleep`
in a job needs no such premise.

**What the poller does NOT fix.** It does not make the crons deliver. They are
demoted to two jobs only: bootstrapping the session, and acting as the crash
dead-man. If a half dies mid-session, the next delivered tick (~45 min at the
measured rate) starts a fresh session for the remainder — so a crash costs up to
~45 minutes of coverage, not the day. `fail-fast: false` keeps half 2 alive when
half 1 dies, and the concurrency group makes a tick arriving mid-session queue and
then stand down out-of-window harmlessly. Worth revisiting 4 if that ~45-minute
crash window ever proves material.

**Standing rule.** A cadence claim in this repo is about *delivered* runs, never
about the cron expression. When tuning any intraday lane, measure delivery first
(`gh api "/repos/:owner/:repo/actions/runs?created=<from>..<to>&event=schedule"`)
and treat the crontab as an upper bound that reality will not honour.

#### §3.6a Delivery VERIFIED, and the interval is a trailing sleep (2026-07-30)

The poller works, and the honest number is **~11 min, not 5**. Measured on run
`30556666110` (the session bootstrapped 15:26Z), counted from its own pass banners:

| | passes | span | mean gap |
|---|---|---|---|
| half 1 | 20 | 15:26:59Z → 18:56:20Z | **11.0 min** |
| half 2 | 7 | 19:03:46Z → 20:09:28Z | 11.0 min |
| **session** | **27** | 4h42m | — |

Against **6 delivered scheduled runs in the whole 8h window on 2026-07-29**, that
is the fix working: 27 passes from one bootstrap tick, and the cron's delivery
rate no longer bounds the lane.

**Why 11 and not 5.** `PASS_INTERVAL_S: "300"` is a `sleep` *between* passes, not a
period — the delivered gap is 300s **plus the pass's own runtime**. Measured that
runtime grows through the session: the first three gaps are ~6.4 min (a ~1.4 min
pass), the rest ~11.7 min (a ~6.7 min pass) as more events fire and more cards
render. So the cadence degrades exactly when the tape is busiest, which is the
wrong way round.

**Gate 0.1 is nevertheless met.** At an 11.0 min gap the mean wait to be looked at
is ~5.5 min, plus ~1 min radar and ~3 min dispatch → **~9.5 min mean, ~15 min
tail**, inside the ≤20 min gate. Recorded rather than tuned: closing 11 → 5 means
deadline-scheduling the loop (sleep to the next 5-minute boundary instead of a
fixed 300s) and is only worth doing if the tail approaches the gate. **Do not
quote "5-minute cadence" for this lane** — the shipped, measured figure is ~11 min,
degrading to ~12 under load.

## §4 Data inventory — have vs need

| Capability | Source | Status |
|---|---|---|
| 5-min live quotes, ~2.1k names | radar self-fetch (primary, 2026-07-30) + VPS live plane (macro floor, 2026-07-30) + live-data branch + site/live + heatmap | HAVE (freshness-safe merge since #3913; the radar no longer depends on another lane's commit cadence, and the ceiling allows for the feed's declared ~15-min delay) |

**§4.1 The quote-source ladder, and what each rung is actually for.** Re-derived
2026-07-30 after a Prophet Live live-verification flagged the shared seam as
starved. Every rung is merged freshest-wins by
`live_verify._merge_quotes`, so a stale rung can never displace a fresh one:

| rung | coverage | freshness | written by |
|---|---|---|---|
| radar self-fetch | ≤900 names (the actionable universe) | seconds | **this lane** |
| VPS live plane (`live.public_quotes_url`) | **34 macro symbols only** | ~30s | VPS systemd timer |
| `live-data` branch snapshot | ~2,100 names | throttled GH lane | live-quotes.yml |
| `site/live` + heatmap | ~30 / ~500 | throttled GH lane | fastpath / nightly |

Rungs 3 and 4 are all written by GitHub lanes, so **they inherit the delivery rate
§3.6 measures** — on 2026-07-30T13:41Z the branch snapshot was 83 minutes old
against a 27-minute radar ceiling. That is why rung 1 exists and why it is
primary.

**Rung 2 is a macro floor, not a coverage source — do not mistake it for one.**
`https://www.mastermind-x.com/live/quotes.json` is the 34-symbol DISPLAY set:
indices, ETFs, futures, FX, crypto, and *no single-name equity at all*. The
~2,100-name `quotes_full.json` behind it is deliberately not web-addressable
(`app/deploy/Caddyfile` exempts only `/live/quotes.json`, `/live/breadth.json`,
`/live/release_publications.json` from the `@reg_asset` default-deny route). What
it buys is that the contrarian detector's index proxy (`SPY`) and every macro
reference stay current even when both the self-fetch and the GitHub lanes are
down — measured 31 seconds old while the branch was 83 minutes old. What it
cannot do is verify a single-name claim. A consumer that needs coverage still
fetches its own tape.
| Sector membership + sizes | sp500_heatmap tiles (503, sector+size) | HAVE |
| Daily bars, 20k names | data/massive_stock_day | HAVE |
| Earnings calendar + AH/BMO flag | data/earnings/earnings.parquet (1,364) | HAVE |
| Prophet levels for signal_fired | content_plan `_plan` | HAVE |
| Shares/mcap beyond S&P | Polygon reference (key exists) or nightly join | SMALL GAP |
| Extended-hours quotes (T4 speed play) | Polygon snapshot / webull-sina refs | PHASE 2 |
| Intraday minute bars for cards | Polygon aggs (plan-dependent) | PHASE 2; daily card + live marker until then |
| Social heat (X/Stocktwits/Google) | twitterapi.io relay (press lane), Stocktwits trending endpoint, pytrends | PHASE 2 |
| Fed/event odds (T5 stance posts) | none in-repo | PHASE 3, LLM desk |
| Options flow (T7) | options estate (flow_hist, screener) | PHASE 3 |
| Congress/13F/rating changes | EDGAR adapters exist nightly; disclosures TBD | PHASE 3 |

## §5 Phases

- **P0 (SHIPPED 2026-07-28)**: theme ramp unblock (#3932) — sector lists live
  from tomorrow's open on flagship. Floor 10→4 (#3924), forward booking +
  shallow checkout + union ledgers + quote-freshness merge (#3913).
- **P1 (chip: hot-tape radar)**: context pack + radar workflow + v1 detectors
  + wire templates with device library + mastermind_news activation + tape
  card for any liquid name + tests/CI. Gates 0.1–0.7.
- **P1.5**: sector grid card; per-trigger engagement table (gate 0.8).
- **P2 (chip: LLM wire desk)**: waterfall phrasing behind numeric-consistency;
  extended-hours quotes → earnings speed play (T4); social-heat scorers into
  the attention universe; "$X in 3h" claims from the snapshot ring.
- **P3**: T5 stance posts (odds data + LLM, operator-reviewed), options-flow
  detector (T7), congress/13F/ratings wires, weights tuned by measured
  engagement.

## §6 Collisions & standing law

- DO_NOT_REBUILD: Mag-7 forced-call kill → gate 0.4 (observations only).
  Chronicle gate 5 (nightly sole advancer of forward ledgers) → the radar
  writes ONLY outbox items + its own snapshot ring, never forward ledgers.
- XG charter §6: employee desks join per-call lanes only after XG-W2 enables —
  Hot Tape routes to mastermind_news + flagship until then (cadence-spec chip
  task_0cd280af is in flight; its resolver enablement widens routing later).
- **Dark-desk park (2026-07-29):** the severity_account ↔ desk_network gap is
  closed in `scripts/marketing_publisher.py`, not in routing. `severity_account`
  keeps no liveness fallback — rerouting sub-85 events to flagship would break
  the flagship law (≥85 severity, ≤1 per pass). Instead any dispatch addressed
  to a desk that is not effective-enabled quarantines as `account_disabled`
  (post_now included, both the auto-approve pass and the post loop), with a
  once-per-account `::warning`. Arming remains the one desk_network flip
  (XG-W2): fresh radar items flow from that moment, parked history stays dead.
  A dispatch whose every requested item was dark-parked exits 0 by ruling
  (2026-07-29) — the annotation and the `account_disabled` ledger rows are the
  receipts, and a red several times a day until XG-W2 would only train
  red-fatigue; red stays for genuine failures (validation, unknown id, mixed).
- In-flight sessions to coordinate with: word-salad copy rewrite
  (task_445d4ea5 — owns template mechanics), Buffer recall (task_318af965 —
  shipped `recall_pending`), cadence specs (task_0cd280af).
- Ledger law: intraday lanes discard data/ writes EXCEPT outbox + the radar
  snapshot ring (append-only, merge=union, same class as the publish ledgers).
