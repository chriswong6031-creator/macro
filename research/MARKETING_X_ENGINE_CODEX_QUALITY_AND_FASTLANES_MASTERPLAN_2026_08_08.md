# Marketing X Engine — Codex Quality, Volume, and Fast Lanes (2026-08-08)

Operator order (2026-08-08): resume publishing today after the Buffer outage; full audit
of the X post mechanisms; every written post authored by the Codex LLM (human register,
never bot register); nothing stale; news fires fast; 20–30 posts per account per day
across all 7 live accounts; macro prints / FOMC / Trump-policy news may fan out to
multiple accounts when genuinely reworded in different formats; chart posts stay one
ticker per account; use the full ticker database; learn from TrendSpider + fintwit
corpus (bounded twitterapi.io pull — polling stays dead per DNR ruling 2026-08-03).

Doc of record for this program. Audit evidence and per-wave acceptance gates below.
Related standing docs: `MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md`
(the LLM-first ruling this extends), `MARKETING_AUTONOMOUS_CADENCE_MASTERPLAN.md`,
`MARKETING_VOICE_DOCTRINE_V3_FINTWIT_REGISTER_BY_FABLE.md`, D05 dockets (wire),
`MARKETING_TRENDSPIDER_PLAYBOOK_AND_CHART_ENGINE_BY_FABLE.md` (chart engine, built).

## §0 ACCEPTANCE GATES (program not done unless)

1. **Publishing resumed**: a live `marketing-publish` run posts ≥1 item to Buffer with a
   receipt, on the day the Buffer subscription is verifiably active again. (The 429
   `Retry-After ≈ 13.7d` lock is Buffer-side; if still locked, the gate is "everything
   armed + proven in dry-run, loud subscription_locked surfacing in admin".)
2. **No stale burst**: zero pending items created before 2026-08-08 post after resume
   (one-shot purge + post-time age gate both in place). Kill-switch interlock used
   during the transition (`MARKETING_PUBLISH_ENABLED=0` set 2026-08-08 ~10:20Z; MUST be
   re-armed the same session the purge merges).
3. **Codex serves**: the nightly plan-gate report + `data/ai_costs/usage.jsonl` show
   `provider=codex` rows for marketing copywriter lanes on the first post-merge nightly;
   per-stage drop accounting appears in the plan summary (the 81→8 collapse is visible
   and shrinking: ≥70% of selected posts survive copy+validation within 3 nights).
4. **Volume**: within 3 days of Buffer resume, each of the 7 live accounts publishes
   ≥15 posts/day trending to 20–30, with per-account spacing ≥ configured floor and no
   cross-account near-dup quarantine spike (>10% of emissions).
5. **Freshness**: no published post whose underlying event is >24h old at post time
   (wire TTL 3h unchanged; planned kinds re-verified at post time; day-stamped copy
   passes the clock gate).
6. **Fast lanes live**: (a) a macro print (CPI/NFP/etc.) produces explained, per-account
   posts within ≤10 min of the wire flash; (b) an FOMC decision day produces the
   statement-diff analysis post ≤15 min after the statement; (c) White House alert-brain
   items reach the wire pipeline (no duplicate shallow poll); (d) breaking wire posts
   carry LLM copy written at post time on the codex-capable runner.
7. **Anti-bot register**: sentinel/validator suite carries the abstention ban
   (`copywriter.py _ABSTENTION_PATTERNS`), no-meta-header law, rounding law, shape
   diversity (≤15% of any account's day in one skeleton), and the em-dash normalizer;
   regression fixtures from the 2026-07-29 rejected batch stay green.

## §1 AUDIT FINDINGS (2026-08-08, evidence-backed)

- **Outage**: last successful post 2026-08-05T20:46:42Z (kelly). From 08-06T00:42Z every
  Buffer call returns 429 with `Retry-After` counting down to ≈2026-08-21T23:09Z —
  a subscription/plan lock, not throttling. Publisher misclassifies it as transient
  (`rate_limited (transient)`) and requeues forever. As of 08-08T08:02Z still locked.
- **Volume baseline (14d)**: best days 22–26 network-wide; kelly 1 post in 14 days;
  meagan/sophia/cici 1–4 total. Caps are NOT the binder (ramp allows 14–20/day).
- **The collapse is the copy stage**: selection offers ~81 posts/night; ~34 die on
  unreadable provider replies (ladder walks to deepseek; codex/oauth/anthropic never
  serve), ~36 die on validators (em dash, shape, number rules). 129 of the last 7 days'
  245 quarantines are "number soup" voice-law kills on deepseek output.
- **Codex ground truth**: `/Applications/ChatGPT.app/Contents/Resources/codex` exists,
  `~/.codex/auth.json` fresh (2026-08-08T07:22Z), live probe `codex exec` returns
  CODEX_OK on this Mac — which hosts the self-hosted runners (`~/actions-runner*`).
  `CODEX_PROVIDER_ENABLED` defaults ON. So the rung's failure is in the adapter/config
  path on the nightly, not auth/binary — instrument per-rung and fix (W2).
- **Publisher runs on `macstudio-light`** (workflow header comment claiming
  ubuntu-latest is stale) ⇒ codex is available AT POST TIME for wire-quality passes.
- **Dark/broken supply lanes**: `receipt` kind 0 emissions ever (enabled), `congress`
  0 ever (enabled), earnings fastlane 0 ever (dead data source — finviz 404, no paid
  provider), `education` tilt zeroed 07-30 (operator act — leave), publish-time daily
  read lane dark, `desk_feed.py` unused scaffold, earnings_call_lane unwired.
- **Four requested features**: econ prints = headline relay only (release-analytics
  stack `release_cpi_bridge`/`macro_surprise`/`event_calendar` has ZERO marketing
  imports); FOMC = keyword detect only, no statement diff, no analysis post; White
  House = rich `whitehouse_brain` alerts feed dashboard only while marketing runs a
  duplicate shallow RSS poll; breaking = live end-to-end (press_stream → spool → press
  tick → outbox → posts) but copy is wire-template/deepseek grade.
- **Fresh queue**: 49 pending (28 queued + 21 approved), 45 created 08-05..08-08;
  wire TTL (3h) and `_STALE_QUEUED_HOURS=36` catch most but pre-08-08 pending items
  must not post on resume.
- **Style corpus**: `research/marketing_dockets/x_corpus_2026_07_29/` (286 posts, 17
  accounts) + weekly x-intel harvester + exemplar store (inactive pending manual
  quality flip) + fresh TrendSpider/Kobeissi/Bilello/unusual_whales/MacroCharts pull
  (this session, scratchpad → distilled into W2's style pack).

## §2 DESIGN RULINGS

R1. **Words by codex, facts by engine** (extends the LLM-first ruling). Every
    user-facing sentence on every lane is LLM-written with `provider_order`
    `[codex, oauth, anthropic, deepseek]`; planned kinds keep NO-template-fallback;
    wire lanes keep their deterministic skeleton as the SPEED floor but get a
    post-time codex quality pass on the publisher runner (mac): if codex returns a
    validated render in ≤20s, post it; else the skeleton posts (speed never blocked).
R2. **Explanation is computed, never invented**. Econ-print/FOMC "explanation" pulls
    ONLY engine artifacts (actual vs consensus vs our published projection, priors,
    percentiles, statement diff). The LLM phrases; it never originates a number or a
    stance (A7/no-uncomputed-directional-advice unchanged). Wire relay lanes keep the
    no-stance charter; house-view fan-out posts carry computed context instead.
R3. **Multi-account fan-out for tickerless macro events only** (macro_print, policy,
    fomc, geopolitical top-tier): one event → per-account renders with assigned
    distinct ANGLE + FORMAT (news: straight wire; flagship: house data view; founder:
    trader read; meagan/sophia/kelly/cici: register-specific takes). Cross-account
    near-dup 0.50 + 3-gram gates stay as the enforcement that rewording is real.
    Ticker posts stay ≤1 account/day/ticker; signals stay 1.
R4. **Volume comes from supply, not caps**: fix copy survival (W2), then raise
    account_overrides to 30/day @20-min spacing for all 7 (operator order supersedes
    the cold-start 2–4/day doctrine — accept the reach tradeoff, mitigate bot
    signatures via shape diversity + jitter + distinct voices), plan_account per_day
    8→20, wire desk cap 10→20, revive receipt + congress lanes, widen chart-post
    ticker allocation over the 2.7k-name US universe (+ HK/CN for cici later), keep
    education zeroed. Global 4-min floor stands (capacity ≈200/day network).
R5. **Freshness**: one-shot purge of pre-08-08 pending items; post-time max-age gate
    (planned kinds 36h → enforced for approved too; wire 3h unchanged; macro_print
    explainers 6h); `subscription_locked` receipt class (429 with Retry-After >24h)
    with bounded requeue (8 attempts → held, loud admin pill + ::error).
R6. **Speed**: press-wire stays on ubuntu for ingest cadence; immediate items keep
    firing the publish workflow_dispatch; the codex quality pass happens at post time
    on the mac runner (R1), so speed and quality decouple. FOMC/econ-print listeners
    arm from `event_calendar` dates and tighten polling around release instants.
R7. **Style pack**: distilled from the operator bar + V3 + fresh corpus; ships as
    (a) per-account voice cards + few-shot exemplars in prompts, (b) validator-side
    diversity budgets. Exemplar store flip only after quality review evidence in the
    PR body (manual gate honored).

## §3 BUILD WAVES

- **W1 (PR-1, small, first)**: publisher hardening + hygiene. `subscription_locked`
  classification + bounded requeue + admin surfacing; `scripts/marketing_stale_purge.py`
  (idempotent, legal transitions, `--cutoff`) + executed purge ledger rows for
  pre-08-08 pending; approved-item age gate parity. Merge → re-arm publisher → live
  dispatch probe (posts only if Buffer renewed; else clean subscription_locked proof).
- **W2 (PR-2, core)**: codex serving + copy quality. Per-rung waterfall instrumentation
  (provider_health sidecar + plan summary per-stage drops + ai_costs rows for every
  marketing lane); fix the codex adapter failure; write-time em-dash/shape/number
  normalizer + one repair turn with validator feedback; voice pack v4 (V3 register +
  abstention ban + quality bar + style pack + per-account cards + shape-diversity
  budgets); publish-time mover/theme lane gains the terra/low phrase pass.
- **W3 (PR-3)**: volume + cadence config per R4 + receipt/congress lane revival +
  per-account ticker allocation over the full universe + macro fan-out routing (R3).
- **W4 (PR-4a/4b)**: fast lanes. 4a: econ-print explainer bridge (event_calendar +
  release artifacts → enriched immediate items → per-account codex renders at post
  time) + whitehouse_brain bridge (retire duplicate shallow poll) + post-time codex
  pass for all wire kinds. 4b: FOMC desk — statement collector + diff engine
  (data/fomc/), decision-day listener, diff-card render (machine-assisted poster OK),
  codex 2–4 paragraph analysis (splits to ≤280-char posts or card+hook per account
  capability), flagship house-view + news relay fan-out.
- **W5**: docs/memory/handoff + measured volume/quality report after first full day.

## §4 OPERATOR-SIDE ITEMS (cannot be done by the agent)

- Buffer subscription renewal (429 lock ends ≈08-21 otherwise). Everything else is
  armed to flow the moment it unlocks.
- Optional: X Premium on accounts if long-form FOMC text posts are wanted as text
  (else diff-card image + ≤280 hook, which ships regardless).

## §5 STATUS LEDGER

- 2026-08-08: audit complete (6-agent fan-out); kill-switch interlock set; masterplan
  committed; W1–W4 commissioned to Opus builders in parallel worktrees.
