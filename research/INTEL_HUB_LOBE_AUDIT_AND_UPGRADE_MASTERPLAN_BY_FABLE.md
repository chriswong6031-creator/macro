# Intelligence Hub — Full Lobe Audit + Upgrade Masterplan

Author: Fable (main loop) · Date: 2026-08-08 · Status: decision-grade audit + build program.
Census: 9 read-only agent sweeps over this checkout (engine, page, track record, SPCX
forensics, six feeder lobes, Prophet linkage, technicals inventory, DNR/lane pre-flight),
load-bearing claims re-verified by hand in `engine/intel_hub.py` / `engine/desk_grader.py`.
Extends (does not supersede) `research/INTEL_HUB_V3_LOOP_CLOSING.md` — V3 Phases 1/1b/2
shipped; its open Phase 3 (recalibrate the accountable-lean layer) is folded into Wave 1 here.
Companion current docs it defers to on their own turf: `ALTDATA_REBOOT.md`,
`SPECIAL_SITUATIONS_ROADMAP_V2.md`, `SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md`,
`PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md`, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md`.

---

## §0 ACCEPTANCE GATES (for every build wave commissioned from this plan)

Not done unless:

1. **Ruler first.** No scoring/weight/cohort change ships before Wave 0+1 (measurement
   integrity) is merged and one nightly has advanced the new per-cohort ledgers. Tuning a
   ranker against a corrupted or cohort-blind ruler is forbidden.
2. **Display-tier vs authority.** Every new plane lands display-tier first (chips, printed
   legs, windows). Anything that changes rank, size, gate, or cohort membership carries a
   pre-registered gauntlet note (metric, horizon, n-floor, pass/fail) appended to this doc
   BEFORE merge. The word "validated" in user-facing copy remains CI-guarded.
3. **No fused composites in scored paths** (DNR:KILL-FUSED-COMPOSITE). The Asymmetry read
   ships as printed legs + two-sided windows only. No single blended asymmetry number
   enters any ranked path. Additionally, per SM2-R3 (`engine/short_pressure.py:9-16`,
   CI-enforced): no function may combine a 13F-derived metric with a short-derived
   metric into one number — squeeze axes are PRINTED context and may never condition the
   analog windows or any derived figure (the hub's convergence channels include 13f_add).
4. **LLM boundary** (DNR:KILL-LLM-ORIGINATION, DNR:KILL-LLM-CONFIDENCE): LLMs de-escalate
   calibrated keys or disambiguate taxonomy; they never originate a signal, score, lean,
   or confidence that enters a scored path. Wave 3's policy refactor is the enforcement of
   this, not an exception to it.
5. **Prophet population untouched** (DNR:KILL-PROPHET-POP-MERGE). Hub→Prophet linkage is
   presentation-tier only: chips + a visually separate context sub-board. No hub-sourced
   name enters `us_standouts.json`'s graded population or reorders it.
6. **Front-facing voice**: windows not certainties; no falsifier/refuted vocabulary on user
   surfaces (operator 2026-07-27); plain-word stance lines on every panel ("so what do I
   do", even when the answer is "watch — don't chase"); nulls printed as plain-word
   disclosures with Tier-2 receipts.
7. **Per-step visual crops** (light+dark+zh) in the PR body for every page-touching wave,
   against the reference mocks named in the wave. Fresh end-to-end nightly (or scoped
   equivalent) with zero manual workarounds before merge.
8. **Render budget is law** (~67 min): new collectors/backtests run off the render path
   (R2 artifacts or separate lanes). A wave that adds >2 min to render must show the
   before/after step timing in the PR.
9. **Collision check at ship time**: re-read `docs/ACTIVE_BUILD_MAP.md`; #4964
   (confluence PIT latch — `signal_gate.py`/`confluence_tiers.py`), #4942/#4734
   (track-ledger era files), #4765/#4512 (sector_central i18n) were open at audit time.
   Rebase-or-defer, never parallel-edit those files.

---

## §1 Executive summary

**What the Hub is today.** `engine/intel_hub.py` (schema `intel_hub.command.v2`, built by
`scripts/build_intel_hub.py` → `site/intel_hub/hub.json` + `site/intelligence_hub.html`) is a
*reader*: it fuses five scored desks — news sentiment, alt-data convergence, radar
divergence states, Buy-Board standouts, policy theses — plus special-situations catalysts
(context-only), its own yahoo-parquet price trajectory, and a discovery feed
(USASpending velocity, insider clusters, beneficial-ownership, dormant index-recon) into a
per-name `edge_remaining` (hand-tuned weighted mean, `intel_hub.py:236-327`) ×
`signal_core` × leading-gap multiplier = `opportunity_score`. Command = top-30
(`:879`). The Emerging panel additionally demands the Prophet T1-T4 gate to read
affirmatively eligible (`_hero_ok`, `:795-810`). A signal governor
(`engine/signal_governor.py`) can only de-escalate, and only radar, behind a
pre-registered gate.

**The five headline findings.**

1. **The Hub is measurement-honest but cohort-blind — and its ruler is bent.** The track
   record grades the whole ~14k-name ranking for cross-sectional IC
   (`intel_hub.py:880-886`) — good science — but no artifact grades *the 30 Command picks
   as a cohort*, so the operator's only question ("do the picks win?") is unanswerable
   today; the snapshot rows don't even store rank or cohort (`hub_track_record.py:88-96`).
   The scorecard shows the emerging cohort NEGATIVE vs SPY at every matured horizon
   (−0.53/−1.61/−3.86pp at 5/10/21d) and warns "departed names OUTPERFORM on-desk names" —
   but read those numbers with the ruler's own defects in view: price coverage is 6.2%
   of eligible grades (desk_grader coverage: 7,516 ok / 121,320 eligible at 20d), the
   fallback price source is split-corrupted, EVERY stage bucket is negative (a
   universe-wide shift that smells like basis artifact, not stock selection), and the
   ledger silently skipped accrual on 2026-08-04/07/08. Fix the ruler (W0/W1), then
   interpret. The feedback loop (lessons) is meanwhile a 4-row hardcoded seed from
   2026-07-04 that nothing refills (`desk_grader.py:700-734`).
2. **The strongest machinery in the repo is not wired into the Hub.** Validated extension
   grades (`engine/extension.py` ext_z), entry zones/don't-chase lines/stops
   (`engine/entry_signal.py`), six PIT short-squeeze axes (`engine/short_pressure.py`),
   Weinstein stages over ~2.8k names (`engine/stage_analysis.py`), a 195-signal Technical
   Lab, earnings beat/raise tags (`site/stagedata/earnings_table.json`), the hourly
   Opus-de-escalated White-House stream, and ALL THREE sector-heat surfaces feed the Hub
   **nothing** (absences grep-proven). The Hub's price awareness is one thin trajectory
   read. The cheapest large upgrade is wiring what already exists, display-tier.
3. **SPCX proves both the pipeline and its blind spot.** The Hub surfaced SpaceX at rank 5
   the night after its 08-04 beat-and-raise, #1 the next night — from alt-data
   convergence + radar + catalyst confluence, before the +16% day. But it could never
   appear in Emerging Edge: `young_history: True` → gate `eligible: False` every night.
   The flagship panel structurally excludes young/recently-listed names — precisely the
   highest-asymmetry profile. (Deliberate design, per the `_hero_ok` comment — the fix is
   a disclosed young-name confirmation path, not deleting the gate.)
4. **Robustness debt is concentrated and cheap to fix.** No staleness gates on ~8
   `exists()`-only inputs; special-situations went silently ~2 days dark; the governor
   reads 2-day-stale `data/` copies because `engine-render.yml` commits `site/` only;
   hub_track_record's price reads can fall back to the split-corrupted breadth cache its
   sibling desk_grader explicitly abandoned; alt-data hangs 22 datasets off one paid
   vendor key (incl. a dead twitter dataset); policy is one weekly DeepSeek synthesis
   whose 22 open theses have never been graded (scored_total: 0) — and it ORIGINATES
   leans that are a LIVE A7 breach in the scored path today (verified chain:
   `policy_intent_desk.py:310→178` lean/conviction → `intel_hub.py:117-121,226` policy
   direction → `:409-418` net_confirm/conf_bonus, a boost up to +25% on the ranking
   tie-break, AND `:345→464-465` lag_up → gap_mult → opportunity_score). Standing law
   (DNR:KILL-LLM-ORIGINATION) already forbids this — removal is a W0 compliance heal,
   not a new decision.
5. **Prophet↔Hub runs one way and the operator's mental model is the missing half.** Flow
   today is Prophet→Hub only (gate verdicts as a desk + hero veto; reverse reads:
   grep-proven zero). The lawful completion (DNR:KILL-PROPHET-POP-MERGE) is
   presentation-tier: hub-context chips on Prophet rows + a separate "context watch"
   sub-board for hub-hot-but-gate-ineligible names — the exact SPCX shape.

**Ruling (recommendation to operator, §8):** keep **Prophet as the decision/money-path
authority** (its gate is the only backtest-validated scorer in the chain) and make the
**Hub the perception layer** — the one place all context planes converge, graded per
cohort, exporting presentation-tier context INTO Prophet. Neither absorbs the other.

---

## §2 System map (verified mechanics)

### 2.1 Build chain and inputs

`daily.yml` (cron 22:30 UTC) → collectors → desk builders → `build_intelligence` +
`build_briefing` → `scripts/build_intel_hub.py` → `engine/intel_hub.build()`.

Scored desks (per-name facets, `engine/intelligence.py:280-292`):

| Desk | Artifact | Fields used | Weight in edge_remaining |
|---|---|---|---|
| news | `site/news/by_ticker.json` | sentiment_lean/score, n_recent, sectors, baskets | crowding leg (w 0.9, inverse) |
| alt | `site/altdata/mastermind.json` (fallback `by_ticker.json`) | signal_score, action, extended, rs_vs_spy_60d | anti-chase 0.05 leg (w 0.7) + RS leg (w 0.7) |
| radar | `site/basketdata/radar_ticker.json` | state, lifecycle, within_basket_pct | lifecycle (w 1.4) + basket-room (w 0.8) |
| standout (Buy Board) | `site/factordata/us_standouts.json["buy"]` | label, off_high, state | label edge (w 0.9) + off-high (w 0.6) |
| policy | `site/policy_intent.json` | theses{subject,lean,conviction,horizon_d}, regime | direction vote only |

Context (non-scored): `site/allocationdata/special_situations.json` → catalyst
freshness leg (w 0.7, live-category allowlist, ≤120d); `site/factordata/signal_gate.json`
→ hero veto + T1-T4 badge; `data/yahoo/<T>.parquet` → trajectory (off_high_252,
ret_20/60d, above_50d, rs_vs_spy_60d, rolling_over, basing) — the price VETO;
`data/intel_hub/news_counts.jsonl` → self-owned mention-velocity ledger; macro frame via
`briefing.macro_context`; discovery feed (`engine/intel_discovery.py`) with a 12-name
command-injection cap and its own anti-chase haircuts.

Ranking: `opportunity = 100 × signal_core × fals_pen(0.85) × edge_remaining ×
gap_mult(±15%) × governor`, sorted with `composite_conviction` as tie-break
(`intel_hub.py:459-478, 793`). Stage classifier (`:355-383`): price veto first
(rolling_over → faltering/distribution/exhausted regardless of desks), then
crowding/lean/edge/gap thresholds → {emerging, early, building, consensus,
distribution, exhausted, faltering}. NB: this "stage" is the Hub's own idea-lifecycle
label — it is NOT Weinstein stage analysis (`stage_analysis` is grep-absent from
`intel_hub.py`) and NOT the radar's lifecycle field (one input among eight).

### 2.2 Page sections (in current page order — `templates/intelligence_hub.html.j2`)

Hero+macro frame → desk rail (6 tiles incl. the "Buy-Board" tile that reads as a lobe) →
**Emerging edge** (stage∈{emerging,early} AND `_hero_ok`, cap 14; "room left" bar =
`edge_remaining`) → **Discovery** (diversified 14-of-149, ≤5/source; "View all 14" =
modal over the same 14 — the other 135 candidates are invisible everywhere) →
**Exhausted / Dated-catalyst pair** (caps 12) → **Command** (top-30) → **Track record**
(per-horizon IC vs SPY) → **Desk scorecard** (closed `<details>`; per-desk IC + mean
alpha vs SPY + lessons) → **Sector heat** (SELF-computed from the Hub's own dossiers —
name collision with the real sector surfaces, see §3.6) → footer. No date-added exists
anywhere in `hub.json` (grep-proven) though the track ledger snapshots could derive it.

### 2.3 Measurement machinery

- `engine/hub_track_record.py`: snapshots ALL dossiers daily (~170k rows), grades
  5/10/21/63 **calendar**-day forward returns vs SPY, cross-sectional rank IC
  (opportunity_ic) with HAC t-stats. Rows carry `date` (entry). Prices via
  `engine.ai_desk._close_series` — which still carries the split-corrupted breadth-cache
  fallback that `desk_grader.py:31-34` documents and privately fixed (yahoo-only reader).
- `engine/desk_grader.py`: grades three desks (intel_hub, alt_data, congress) on level +
  velocity rank-IC and mean forward alpha vs SPY over 5-90 **trading** days; emits
  auto_findings nightly; lessons ledger `data/desk_grader/notes.jsonl` seeded once
  (4 rows, all 2026-07-04) — `seed_notes()` is a permanent no-op after first write and
  `add_note()` has no production caller. Auto-findings → lessons promotion does not exist.
- `engine/signal_governor.py`: de-escalation-only trust map (demote only at n≥150,
  |t_HAC|≥2, IC≤−0.03), radar + hub keys; only `radar` is consumed
  (`intel_hub.py:754-758,472-477`). Reads `data/` copies that lag `site/` copies by ~2
  days because the engine-render lane stages `site/` only.

Current honest readings (2026-08-08 build): overall desk mean_fwd_rel −0.26/−1.25/−2.34/
−2.05pp at 5/10/20/30 trading days (hit 50.3/48.6/47.4/46.8%); emerging-stage cohort
−0.53/−1.61/−3.86pp at 5/10/21 calendar days; "departed names outperform" flagged at 10d
and 20d; governor trust 1.0 (nothing demoted); hub opportunity IC +0.026 (t 0.42,
"measuring").

---

## §3 Per-lobe audit + upgrade paths

Format per lobe: what it is → sources (free/paid) → processing → what the Hub gets →
verified weaknesses → upgrades (D = display-tier, ships freely; G = needs gauntlet to
touch authority).

### 3.1 Alt Data (`site/alt_data.html`, `engine/altdata*.py`)

- **Sources**: Quiver Quantitative (PAID, one key): congress/senate/house trades, gov
  contracts, lobbying, off-exchange, insiders, 13F(+changes), CNBC, WSB, spacs, patents,
  flights, corp donors, news, bills, app ratings, top shareholders, exec comp — and a
  DEAD twitter dataset still listed (`engine/altdata.py:38-59`; X API killed 2023).
  Free: USASpending, SEC EDGAR 8-K materials, OpenFDA, ClinicalTrials.gov, GitHub stars,
  HuggingFace downloads, FINRA short interest. Paid: Polygon news-sentiment + options
  chains, Finnhub, Stocktwits.
- **Processing**: per-source deterministic scorers → `convergence()` = unweighted count
  of independent channels ≥2 (`altdata.py:1124`); Opus brain proposes lean/conviction but
  is clamped de-escalation-only (`altdata_brain.py:17-36,389`) — A7-clean.
- **Hub gets**: mastermind signal_score/action/extended/rs.
- **Weaknesses**: single-vendor concentration (~20 of ~30 signal functions die with one
  key); convergence treats correlated channels (13F add + CNBC pick + congress cluster
  often co-occur on the same news cycle) as independent votes; no novelty/decay — a
  channel that confirmed weeks ago counts like this morning's.
- **Upgrades**:
  - D: novelty-weighted, decay-windowed convergence display (per-channel last-fire date,
    "fresh vs standing" split); per-channel hit-rate receipts on the Tier-2 card.
  - D: vendor-independence ledger — per-channel provenance with free primary fallbacks
    where they exist (PatentsView for patents; SAM.gov + USASpending for contracts; EDGAR
    Form 4 for insiders — panel already collected; FINRA for short interest). Quiver stays
    the convenience aggregator; the ledger makes an outage degrade, not blind.
  - W0: delete/flag the dead twitter dataset entry.
  - G: correlation-aware convergence (channel clusters counted as one plane) may replace
    raw channel-count in scoring only after a pre-registered side-by-side on the track
    ledger.

### 3.2 News / Briefing

- **Sources**: 13 hardcoded top-tier RSS feeds (free) + Google-News RSS fallback
  (`engine/news_rss.py:56-102`); Polygon + Finnhub company news (paid); GDELT (free,
  429-fragile, circuit-breakered); Quiver news (paid). LLM summarizer exists but ships
  OFF; no LLM touches selection (A7-clean).
- **Processing**: source-tier × relevance × recency − clickbait → dedup/top-N; briefing
  ranks confidence×strength; per-name sentiment_lean/n_recent feed the Hub's crowding
  leg and the mention-velocity ledger.
- **Weaknesses**: static source list, no coverage/dead-feed monitoring (a silently dead
  RSS feed = invisible sentiment starvation); `site/news/financial.json` uses different
  freshness keys (fetched_at/asof) than every other lobe (as_of).
- **Upgrades**:
  - D: source-health sentinel (per-feed last-item age, emitted into the ops heartbeat;
    dead feed = printed LIMITED disclosure on the news desk tile).
  - D: vertical trade-press feeds mapped to baskets (SpaceNews, DefenseNews, FierceBiotech,
    Utility Dive, Rigzone…) — free RSS, directly densifies the thin-coverage small-caps
    where the Hub's edge should live; plus GlobeNewswire/BusinessWire category RSS for
    primary PRs (8-K precursors).
  - D: schema-harmonize freshness keys (as_of everywhere) so staleness gates (W3) can be
    uniform.

### 3.3 Radar (theme activity)

- **Sources**: USASpending obligations (free), Quiver gov-contracts/congress/lobbying
  (paid, same single key), modeled news velocity; price leg = 60d RS vs SPY.
- **Processing**: robust-z fusion → fused_obs_z/accel vs price con_z → four states
  (POSITIVE/NEGATIVE_DIVERGENCE, CONFIRMED_UP/DOWN) + lifecycle
  {emerging,forming,mature,fading,quiet}; POSITIVE_DIVERGENCE seeds hypotheses graded by
  `radar_ic.py` — the one lobe with its own IC harness feeding the governor.
- **Weaknesses**: 3 of 4 activity legs share the Quiver key; governor reads the 2-day
  stale `data/radar/radar_ic.json` copy; the governor's own docstring flags that its
  original demotion fired on an IC later judged an unsigned-pooling artifact.
- **Upgrades**:
  - W0: point governor at the same artifact the page shows (or commit `data/` in the
    engine-render lane); one truth.
  - D: demand-side activity legs — Google Trends basket queries (free, pytrends),
    FDA/ClinicalTrials event velocity per basket (collectors exist), EDGAR 8-K item-type
    velocity per basket (collector exists) — display-first as extra divergence witnesses.
    (These are theme-activity legs; the six DNR radar kills — Hindenburg, IBD
    distribution days, MCO thrust, absolute-VIX, lumber/gold, transports — are RISK-radar
    market-internals legs and remain dead; none are re-proposed here.)
  - G: any new leg entering fused_obs_z needs the radar_ic pre-registration path.

### 3.4 Special Situations

- **Sources**: SEC EDGAR daily-index + EFTS full-text (free) as the backbone; the
  newswire lane and the Canada intl lane are already ON (`config.yml:6798,6807`) —
  only `intl_uk` ships off, for a documented reason (no direct RNS feed wired;
  Google-News alone yields ~0 recall). yfinance backfill for arb targets.
  [Red-team correction: the census initially read these lanes as coded-but-off from
  the collector defaults; config.yml is the truth.]
- **Processing**: deterministic form→category+stage taxonomy (13D/G, TO, 13E3, mergers,
  Form 25/15/10, S-4…); ambiguous 8-K/6-K go to an LLM *disambiguation* lane
  (promote-into-taxonomy only, Management Changes excluded — A7-clean); $100M cap floor
  ($25M high-confidence); priors published with n≥5 floor.
- **Hub gets**: catalyst {category, stage, days_since, live} — context + one freshness
  leg; Dated Catalysts panel.
- **Weaknesses**: artifact went silently ~2 days stale (a no-op cycle with no alarm);
  `activist_filers` empty while risk_arb holds 22 rows; UK lane blocked on feed recall.
- **Upgrades**:
  - W0: freshness sentinel (as_of age > 1 nightly = ops ping + LIMITED chip on the desk
    tile).
  - D: wire a direct RNS feed if UK coverage is wanted (the gate that keeps `intl_uk`
    off is feed recall, not code); investigate why `activist_filers` is empty.
  - D: 13D/G *amendment velocity* (accumulation pace), Form 25/15 delisting watch,
    S-1/424B4 IPO + lockup-expiry calendar — the young-name feeder the SPCX class needs;
    all parse the EDGAR pipe that already runs.
  - D: print each catalyst class's OWN base rate on its card (n, win_20d, median move —
    already computed; SPCX's 8-K class reads 50%/−0.1% — honest "this alone is noise").
  - G: catalyst-class differentiation in scoring (live-allowlist → per-class weights)
    only via gauntlet. (DNR:KILL-PHASE3-START-WEIGHT stays honored — Phase-3 starts
    remain display chips.)

### 3.5 Policy

- **Today**: `site/policy_intent.json` = ONE weekly DeepSeek call over a hand-curated
  substrate (`data/policy/intel.json`) + regime read; it ORIGINATES 0-5 theses
  (lean/conviction/horizon) that enter the Hub's five-desk direction vote; its embedded
  track_record shows scored_total: 0 across 22 open theses; 6.5d old at audit (7d regen
  by design). The far fresher hourly White-House lane (RSS → Opus DE-escalation gate) is
  not consumed by the Hub at all.
- **Verdict**: closest active thing to an A7 boundary breach in a scored path
  (LLM-originated lean with a conviction knob voting into confirmation), un-graded to
  boot. DNR:KILL-POLICY-TIMING-PREDICTOR ("intent unfalsifiable — conditions-framing
  only") points the way.
- **Upgrades**:
  - W1: grade the existing 22 theses (they carry falsifiers + check_by dates; the ledger
    machinery exists) — before anything else, learn whether this desk has ever been right.
  - W3 refactor: policy desk becomes conditions-framed + mechanical: (a) White-House
    item stream (already de-escalated) mapped to sectors/baskets as dated events; (b)
    Federal Register + congress.gov activity series (free APIs) as policy *activity*
    velocity per theme — radar-style, no intent prediction; (c) LLM role limited to
    de-escalation/taxonomy. Theses (if kept) become display-tier "conditions to watch"
    with their falsifiers living below the fold (Calibration-Lab style), not votes.
  - W0 (moved up on red-team ruling): remove the policy direction from `nz`/`lag_up` —
    the minimal heal that takes the LLM-originated lean out of every scored path while
    keeping policy as a printed flag/chip. This is enforcement of a standing law
    (DNR:KILL-LLM-ORIGINATION), so it ships without new ratification; the operator may
    veto in §10.1. Premise correction from review: policy never reaches `base` in the
    common path (`intelligence.py:174-177,215` — `brain.priority` short-circuits), so
    the breach surface is exactly n_confirm/conf_bonus + lag_up/gap_mult, nothing else.

### 3.6 Sector Heat

- **Today, three unlinked surfaces**: (a) macro.html "Sector Heat Strip" from
  `engine/sector_pulse.py` — whose heating/hot tiers were kill-tested against 27y of
  SPDR data and found to carry NO forward edge (display-only by evidence, per
  `scripts/calibrate_sector_pulse_heat.py`); (b) `site/sector_central.html` — RRG
  rotation states, bottom_confidence, dislocation over sector-ETF OHLC (the real
  intelligence); (c) `site/sector_heatmap.html` — SP500/themes visual heatmaps. NONE feed
  `intel_hub` (grep-proven both directions). The Hub's own "sector_heat" panel is
  self-computed from its dossiers — a pure name collision.
- **Upgrades**:
  - D: per-dossier **sector-regime chip** from sector_central: RRG quadrant +
    bottom_confidence for the name's sector — context on every Emerging/Command card
    ("sector improving / topping / washed-out"). Rotation STATES, not the null-tested
    heat tiers.
  - D: rename the Hub's self-computed panel ("Desk sector tilt") and link the real
    sector surfaces; one glossary entry in `docs/site_semantics/`.
  - G: sector-regime as a scored confluence direction (a 6th vote) only via gauntlet,
    and NOT as an entry-timing gate on cycle position (DNR:KILL-ROTATION-CYCLE-CONFLUENCE
    forbids that construction; DNR:KILL-RS-DISPERSION-GATES forbids dispersion gates).
    What the kill rows leave open and this plan pursues: sector regime as *context
    display* and as a *candidate confirmation direction* measured on the hub's own track
    ledger — not a rotation-timing entry gate.

### 3.7 Discovery (inside the Hub)

- **Today**: USASpending federal velocity, insider clusters (quarter-lagged by SEC
  panel cadence per its own docstring), beneficial-ownership regime, index-recon
  (dormant pending its validation gate). 149 candidates → 14 shown (≤5/source) → ≤12
  injected into command ranking with anti-chase haircuts; displayed discovery names are
  mostly NOT in the graded track rows (only injected ones are).
- **Upgrades**:
  - W1: grade the DISPLAYED discovery cohort (they're recommendations the user sees;
    ungraded display is untracked exposure).
  - D: "View all" opens the full 149 with per-source grouping (see §7) — the data
    already exists in the artifact chain.
  - D: replace the quarter-lag insider panel read with the Form-4 stream for the
    *display* layer (keep the panel for the scored cluster leg until gauntleted).

---

## §4 Measurement + feedback repairs (Wave 0/1 — the ruler)

1. **Snapshot schema first (X1)**: add `rank`, `cohort` (command_top5/command_30/
   emerging_panel/discovery_shown/catalyst_shown), and the `_hero_ok` rejection reason
   to every `hub_track_record` snapshot row (`:88-96`). Three fields, ~zero cost; their
   absence is exactly why "did Command win" and "how often does young_history exclude a
   #1 name" are unanswerable. Without this, any cohort work rebuilds the same blind spot.
2. **Price integrity — versioned, not swapped (M1)**: port desk_grader's yahoo-only
   close reader into `hub_track_record`, but as an ERA-STAMPED versioned grader with
   BOTH series printed side-by-side — yahoo-only coverage is ~603 of 7,670 ledger
   tickers (7/30 of today's command names have no yahoo parquet, including the sole
   Emerging name), so a silent swap trades split-corruption for a 10× sample shrink.
   Companion fixes: (a) bound the asof-or-before close lookups (`desk_scorer.py:96`,
   `ai_desk.py:236`) with a max-staleness window — today a stalled series silently grades
   against an arbitrarily old close on BOTH legs; (b) an off-render backfill collector
   that closes the yahoo-parquet gap for every ledger ticker.
3. **One governor truth — fail-loud (M8)**: the genuinely stale governor input is
   `data/radar/radar_ic.json` (the hub track-record half is re-persisted in-run before
   compute). Point the radar read at the artifact the page ships — and note there is NO
   `site/hub/` dir (the site copy is `site/intel_hub/`): a naive repoint = missing file =
   silent trust 1.0 forever, because the governor degrades-never-raises. The fix must
   fail LOUD on a missing/stale input (line-start `::warning`), not default to identity.
4. **Per-cohort grading, statistically honest (B3)**: (a) retro-reconstruct cohorts for
   the existing 38 ledger dates by ranking each date's stored `opp` (the full universe
   is snapshotted daily — 2.8-4.8k rows/day), giving command/top-30 an instant graded
   history; (b) grade small cohorts (top-5/top-30) as MEAN EXCESS RETURN vs SPY with
   date-block bootstrap CIs — never IC (the ≥10-names/date floor at `:186` makes
   cohort-IC undefined, and overlapping daily windows mean effective n = dates, not
   rows); (c) emerging_panel/young-lane cohorts start honestly at n=0 (the `_hero_ok`
   verdict was never stored — begins accruing the night item 1 ships); (d) partition
   already-matured rows so the 5-cohort fan-out doesn't 5× the ~20s render-path compute
   (the ledger grows ~2.9k rows/day — unbounded-scan creep shape).
5. **Calendar/trading-day harmonization**: keep both graders but label horizons on-page
   in trading days; reuse #4942's era-stamp convention rather than inventing one.
6. **Lessons pipeline — significance-gated (M2)**: nightly mechanical promotion of
   desk_grader `auto_findings` into `notes.jsonl`, gated on a date-block bootstrap CI
   excluding zero PLUS cross-horizon agreement (the raw generator fires on n≥10 &
   Δ≥0.5pp with no test, across 6 horizons × 4 finding types — it currently asserts
   both "departed names OUTPERFORM" (10/20d) and "DROPS ARE CORRECT" (30d)
   simultaneously). Dedup on (desk, finding-key), persistence ≥N nights, max M/night,
   no LLM. Lessons panel shows date + receipt link. The 07-04 freeze ends as a side
   effect.
7. **Entry-date surfacing**: derive first_seen per (ticker, cohort) from the existing
   snapshots; render "added N d ago · +X% since add" on Command + Emerging cards. (The
   operator asked for exactly this; the data has existed all along.)
8. **Policy ledger grading** (per §3.5): score the 22 open theses against their own
   check_by dates.
9. **Accrual + coverage monitor (X3)**: expected-dates vs present-dates and a
   coverage_pct floor per horizon, emitted as line-start `::warning` (house annotation
   law) AND as a printed chip on the scorecard. The ledger already skipped 2026-08-04/
   07/08 with zero alarms while the page read fresh; the scorecard grades 6.2% of its
   eligible universe and shows it nowhere. Staleness/degrade gates (W3) apply to DISPLAY
   and desk-vote exclusion only — NEVER to ledger accrual: an empty-bundle gate would
   write 0 rows and punch a permanent point-in-time hole (M7).
10. **Ranker units audit (X2 — highest-leverage correctness fix found by review)**:
   `signal_core` = `strength` = `max()` over three NON-COMPARABLE scales
   (`radar edge/100`, `|alt−50|/50`, `|standout conviction|`,
   `intelligence.py:189-199`) and multiplies `opportunity_score` directly
   (`intel_hub.py:459,465`) — one loud desk sets the primary ranking key on unnormalized
   units. Fix: per-desk historical-percentile normalization computed as a SHADOW score
   printed alongside the live one, with a pre-registered switch criterion (rank
   correlation + per-cohort excess-return side-by-side on the W1 ledgers). Ranker
   switches are authority changes: prereg, era-stamp, both series printed through the
   transition.

---

## §5 SPCX case study (what worked, what to harden)

Timeline (nightly snapshots; price data is prior-close vintage):

- 06-22→06-29: alt-data convergence alerts (2-channel, then 3-channel) around the 8-K
  $25B senior-notes filing (CIK 1181412, filed 06-23). Special-sits catalyst class base
  rate for that filing type: n=140, win_20d 50%, median −0.1% — correctly weak alone.
- 08-04: Q2 FY26 earnings — revenue +92% YoY, EBITDA +191%, tags guidance_raised,
  beat_and_raise, demand_acceleration (`site/stagedata/earnings_table.json`) — the real
  ignition. NOT a Hub input; it reached the Hub only via news mentions + alt channels.
- 08-06 snapshot: SPCX debuts in Command at rank 5, stage "emerging", edge_remaining
  0.869, opportunity 40.0.
- 08-07 snapshot (the +6% session): #1/30, opportunity 77.4 (peak). Stage flipped to
  "early" only because the news facet flickered out that night (lag_present=0 fails the
  emerging gate) — label churn on a facet dropout, not on evidence.
- 08-07T00:00Z: fresh 3-channel convergence alert (13f_add + cnbc_pick +
  congress_cluster) — this is the event the operator experienced as "golden oracle
  confluence". (The literal `golden oracle` in `engine/canon.py:447` is a CI reference
  frame for Terminal parity — display/QA, never in any scoring path.)
- 08-08 snapshot (after the +16% session): still #1, stage "emerging" again, +"isolated"
  flag (no Space-Economy peer confirms), opportunity 55.7 — the score FELL 28% on the
  biggest up-day, pure churn from facet flicker + crowding legs.
- Every night: `signal_gate` verdict eligible:False, young_history:True, flat_sell:True
  → `_hero_ok` False → structurally barred from Emerging Edge while topping Command.

**Lessons → program mapping:**

| Lesson | Fix |
|---|---|
| Young names (freshest listings = highest asymmetry class) cannot reach the flagship panel | Young-name lane (W2): disclosed alternative positive-confirmation path (see §6.4) |
| The actual ignition (earnings acceleration) is not a Hub plane | Earnings beat/raise tags as catalyst input (W2, display; G for scoring) |
| Convergence counted three correlated channels as three votes — right call here, but uncalibrated in general | Novelty/correlation-aware convergence display (W3, D; scoring via G) |
| Stage label churns on facet dropout; opportunity fell 28% while the thesis strengthened | Facet-dropout memory (last-known-good with age disclosure) + score hysteresis — pre-registered, aligns with EYES-OPEN Wave-2's hysteresis item |
| Catalyst-class base rate (50%/−0.1%) was invisible next to the pick | Base-rate line on catalyst cards (W3, D) |
| "Command #1" carried no date, no since-add return | §4.7 |

**What worked and must not be broken**: multi-desk confluence beat any single desk; the
12-name discovery injection cap and anti-chase haircuts did NOT block a legitimate
runner; the governor stayed out of the way; Command (ungated) caught what the gated
panel could not — the two-tier design is right, it just needs the young-name disclosure
path and cohort grading.

---

## §6 Asymmetric risk/reward: the "Asymmetry read" (display-tier v0)

Goal: for every Command/Emerging/Discovery name, answer — from planes we already
compute — "how much is plausibly left, what does the downside case look like, and is
NOW an entry?" without a fused score (DNR:KILL-FUSED-COMPOSITE) and without chasing
bans (a runner is filtered by tactic, never by exclusion).

### 6.1 Printed legs (each with its receipt, no blending)

- **Catalyst base-rate leg**: for the name's live catalyst class: n, win_20d, median,
  p75, p25 moves (already computed by special-sits priors). Two-sided by construction.
- **Stretch leg**: `extension.py` grade (intrend / steady / stretched / parabolic) with
  the cohort forward stats the module already carries (parabolic cohort: ~9% fwd with
  50% vol, −94% worst drawdown, −1.37 skew vs intrend 18.9%/25%/−49%/+0.41) — the
  honest "extended ≠ short, but size/entry changes" evidence.
- **Squeeze-context leg (printed ONLY — SM2-R3 blocker from review)**: short_pressure
  axes shown separately (days-to-cover, borrow fee, SI change, short-volume). They may
  NEVER condition the analog windows or enter any derived number: SM2-R3 forbids any
  function combining a 13F metric with a short-derived metric into a single number, the
  convergence channels include `13f_add`, and `short_pressure.AUTHORITY` is
  may_rank/size/gate: False, CI-enforced (`tests/test_short_pressure.py:247-268`).
- **Sector-regime leg**: RRG state + bottom_confidence (§3.6).
- **Crowd leg**: news crowding + "isolated vs theme_wide" flag (already computed).
- **Freshness leg**: catalyst days_since + convergence novelty (§3.1).

### 6.2 Two-sided window (the user-facing line)

Analog windows, not forecasts: condition on (catalyst class × stretch grade) ONLY and
print the historical distribution of 20d forward moves for that cell from the existing
ledgers — "names like this: median +X%, upside quartile +Y%, downside quartile −Z%
(n=…)". Sector regime and squeeze axes are printed BESIDE the window, never inside its
conditioning (KILL-ROTATION-CYCLE-CONFLUENCE bars rotation×position entry-confluence;
SM2-R3 bars squeeze in any derived number). Cells below the n-floor print "too few
analogs — window not drawn" (nulls printed). Voice: windows, re-drawn nightly; never
certainty, never falsifier vocabulary front-facing.

### 6.3 Entry tactic label (replaces "is it too late?" with "how, if at all")

Derived from PRICE/ATR ONLY — `entry_signal.py` zones + `extension.py` stretch grade +
trajectory. Sector regime and Weinstein stage are printed beside the label and never
condition it (review ruling M3: conditioning tactic on regime is the
KILL-ROTATION-CYCLE-CONFLUENCE construction; KILL-STAGE-WIN-GATE keeps stage
display-only on entry timing):

| State | Label (glance tier) |
|---|---|
| in buy-zone, trend intact | "in entry zone" (+zone bounds) |
| above zone, grade steady/stretched | "extended — pullback zone $A–$B" |
| grade parabolic | "chase risk high — analog cohort stats shown" |
| rolling_over | "broken — de-risk" (already the veto) |
| young_history | "young name — event-driven read only" (§6.4) |

This preserves runners: nothing bullish is hidden for being up a lot; the tactic and
the analog stats change instead. (Entry-timing *authority* constructions from the PSS
family stay dead per their DNR rows; this is display.)

### 6.4 Young-name lane (the SPCX class)

A name with `young_history` (gate can't grade) qualifies for the Emerging panel only
via an ALTERNATIVE positive-confirmation checklist — fresh multi-PLANE confirmation
(not raw channel count: `13f_add`/`cnbc_pick`/`congress_cluster` all key off the same
disclosed-flow tape and count as ONE plane; require ≥2 independent planes, e.g.
disclosed-flow + live catalyst/earnings-acceleration + volume confirmation) + a minimum
bar-count floor so the rolling_over veto is EVALUABLE — review found young names get a
free pass on that veto today (`_hero_ok:803` only vetoes on `rolling_over == True`, and
a name with no closes returns trajectory None, so the veto never evaluates). Where
trajectory is unknown, print "trajectory unknown" rather than implying it was checked.
Rendered with a "young name — technical gate not yet gradable" chip; cohort-tracked
separately from day one (§4.4c), so within a quarter we KNOW whether young-lane picks
earn their place. This honors the `_hero_ok` design intent (positive confirmation,
never absence-of-evidence) while unblinding the flagship panel to the
highest-asymmetry class. Sequencing: lands AFTER #4964 (confluence PIT latch) — that
lane owns the `eligible` verdict this checklist extends.

### 6.5 Promotion path (if we ever want asymmetry to RANK)

Only via gauntlet: pre-registered spec (metric, horizon, n-floor, base-rate-vs-uplift)
measured on the per-cohort ledgers from W1, one factor at a time, never a fused
composite. Until then the Asymmetry read changes zero ranks.

### 6.6 Known gaps worth building (small, off-render)

Measured-move/base-depth targets, base-pattern detection (VCP/flat-base), and
blow-off-top volume climax (only bottom-capitulation exists today) are genuinely absent
(grep-proven). Build as Tech-Lab families first (display), candidate legs later.

---

## §7 Page/UX plan (designer lane, W5)

Operator complaints, mapped:

1. **Order**: Command first (it is the product; it carried SPCX). Then Emerging +
   Discovery as a side-by-side pair of equal containers, each cap-4 cards + "View all N"
   (the modal already exists — reuse `lst-cap4` symmetry; Discovery's modal should page
   the full 149 grouped by source, not just the shown 14). Exhausted + Dated Catalysts
   move to the bottom as context panels.
2. **"View all 14" wording**: the operator read it as a see-more idiom mismatch — with
   the side-by-side layout the pill reads "View all N" per container and behaves like the
   expected see-more. Keep the modal (it's good), fix the container geometry.
3. **Exhausted panel is two ideas mixed**: split copy into "Broken — de-risk"
   (rolling_over/lean-down) vs "Crowded — late" (crowded_top with intact trend); plain
   one-line stance each. Retitle "Dated catalysts" → "Known dates" with its base-rate
   line ("timing context — not a reason to buy" stays).
4. **Dates everywhere**: "added Nd ago · +X% since" chips (§4.7) on Command/Emerging.
5. **Scorecard**: keep the honest negative readings (voice law) but add the one-line
   plain read ("The desk's bullish cohort has lagged SPY over the last month — read being
   updated; changes logged below") and link lessons (now refilling, §4.6). "Losing to
   SPY" without context is demoralizing; with the lesson trail it's a system that learns
   in the open.
6. **Glance-tier jargon**: gloss or demote "off-desk", "leads by +N", T1-T4 badges
   (hover receipts), engine_version blocks (§ Tier-2 only).
7. Nav/name unification for the Prophet surface (one product, three names today:
   "Stock Dashboard" / "Prophet Stock Signals" / "Buy Board") — pick one per §8 ruling.

All copy bilingual EN/ZH per house law; no translated text in title= attributes; banned
vocab per glance-tier law; visual crops in PR per §0.7.

---

## §8 Prophet ↔ Hub architecture (ruling recommendation)

**Facts**: Prophet's chain (`build_stock_library.py` → `signal_gate.gate()` per name →
`us_board_rank.score_rows()`: signal 30 / entry 25 / edge 25 / runway 10 / quality 10)
is the only backtest-validated scorer in either system, and flow today is strictly
Prophet→Hub (gate verdicts as desk + hero veto + label leg). The Hub feeds Prophet
nothing (grep-proven). "Buy Board is a lobe of the Hub" is a UI impression from the desk
rail tile.

**Ruling recommendation**: two organs, one direction each, neither absorbed:

- **Prophet = decision layer** (money path). Its population/ranking stays sovereign —
  DNR:KILL-PROPHET-POP-MERGE already enshrines this. Its validated gate remains the
  Hub's hero-quality bar for gradable names.
- **Hub = perception layer** (this audit's subject). All context planes converge here,
  cohort-graded, honestly windowed.
- **Build the missing half presentation-tier**: (a) a **hub-context chip** on Prophet
  board rows (confluence count, sector regime, catalyst class + freshness, crowding) —
  context only, never reordering; (b) a **"Context watch" sub-board** on the Prophet
  page: hub-hot names NOT in Prophet's graded population (young names, gate-ineligible,
  off-universe) — visually separate, disclosure-labeled, cohort-tracked. That is the
  ratified ⚡-chip + residual-sub-board form, and it is exactly where an SPCX surfaces
  next time — visible on the money page without contaminating the graded board.
  Review guard (M4 — the HOLD-IGNITION-SURFACES failure mode was precisely a ranked
  sub-board shipped ahead of its display gate with a forced top-N in a dead tape): the
  sub-board pre-registers its EMPTY state ("nothing qualifies today" is a valid,
  rendered answer), carries NO forced N, and its cohort grading ships in the SAME PR.
- **Scored influence later, single-factor, gauntleted**: if the W1 per-cohort ledgers
  show hub context adds selection edge, promote ONE pre-registered input into Prophet's
  quality leg — after, and only after, it wins on the ledger. (Consolidating the two
  systems into one is explicitly NOT proposed: consolidation is not architecture —
  operator law.)

This gives the operator's intuition ("Hub feeds Prophet") its lawful realization while
keeping the only validated ranker uncontaminated — and keeps the Hub as the wide-net
perception organ whose Command list can catch what a technical gate cannot yet grade.

---

## §9 Wave plan (routing per CLAUDE.md §Model routing; each wave = one PR-sized session)

| Wave | Content | Route |
|---|---|---|
| W0 | policy vote removal from nz/lag_up (A7 heal); snapshot-row schema fields (rank/cohort/hero-reason); governor radar_ic fresh-read + fail-loud; era-stamped dual-series price grader + bounded-staleness lookups; accrual/coverage monitor; special-sits freshness sentinel; dead-twitter delist | builder (opus) |
| W1 | per-cohort track record (retro-reconstructed 38 dates; mean-excess + date-block bootstrap for small cohorts) + on-page "Command vs SPY"; entry-date chips; significance-gated lessons promotion; policy-ledger grading; horizon labeling (#4942 era convention); ranker-units SHADOW score (X2) + prereg switch spec; yahoo-parquet backfill collector (off-render) | builder (opus) |
| W2 | dossier chips: ext_z grade, entry zones, squeeze axes, Weinstein stage, sector-regime, earnings tags; young-name lane (with separate cohort tracking); sector_heat rename | builder (opus); young-name lane spec pinned by main loop first |
| W3 | staleness gates (LIMITED-null pattern) on all core inputs; special-sits lanes ON + amendment-velocity/delisting/IPO-lockup feeds; convergence novelty display; news source-health + vertical feeds; policy conditions-refactor; price dual-source tripwire | builder (opus), collectors off render path |
| W4 | Asymmetry read v0 (printed legs + analog windows + tactic labels) | main-loop design spec → builder (opus) |
| W5 | page reorder + section split + copy (bilingual) + crops | designer (opus) |
| W6 | Prophet context chip + Context-watch sub-board (presentation-tier) | designer + builder (opus) |

Sequencing law: W0+W1 before any W2+ item that could be tuned against the ledgers
(§0.1). W2 young-name lane and W6 sub-board are cohort-forming: their tracking starts
the night they ship. W3 collectors land in daily.yml off the render-critical path.

---

## §10 Open operator decisions

1. **Policy vote removal** (§3.5): W0 ships the removal as a standing-law heal
   (DNR:KILL-LLM-ORIGINATION — the vote is a live breach). This row is the operator's
   VETO point, not an approval request; a veto would need a registry amendment
   ratifying the exception.
2. **Paid-data appetite**: this plan is free-first by design. If budget exists, the
   highest-value paid adds are (a) a second cross-check price/reference feed, (b) an
   options-flow feed for the squeeze/positioning plane, (c) an earnings-estimates feed
   (revision velocity). None are required for W0-W6. (No paid X/Twitter reads — standing
   operator veto.)
3. **Naming**: one public name for the Prophet surface ("Buy Board" is the strongest
   user-facing brand; "Prophet" reads internal; "Stock Dashboard" is generic).
4. **Young-name lane checklist** (§6.4): ratify the confirmation checklist before W2
   ships it (it defines who can appear in the flagship panel).
5. **Command cap**: top-30 with 12 discovery injections is ~40% off-desk at the tail;
   after W1 cohort grading, revisit whether 30 is the right N.

---

## Appendix A — verified defect register (short form)

| # | Defect | Where | Wave |
|---|---|---|---|
| D1 | hub_track_record price fallback to split-corrupted cache | `hub_track_record.py:36-38` → `ai_desk.py:210-233` | W0 |
| D2 | governor reads 2-day-stale data/ copies | `signal_governor.py:46-48` + engine-render staging | W0 |
| D3 | special-sits silent no-op (~2d stale) | `site/allocationdata/special_situations.json` | W0 |
| D4 | dead Quiver twitter dataset listed | `engine/altdata.py:38-59` | W0 |
| D5 | no per-cohort (Command) grading | `hub_track_record.py:198-260` | W1 |
| D6 | lessons ledger frozen at 4 seed rows (07-04) | `desk_grader.py:700-734` | W1 |
| D7 | policy theses never graded (0/22) | `site/policy_intent.json` | W1 |
| D8 | no date-added surfaced anywhere | `hub.json` schema | W1 |
| D9 | young-history names barred from Emerging | `intel_hub.py:795-810` + signal_gate | W2 |
| D10 | validated extension/entry/squeeze/stage/sector planes unwired | §3/§6 | W2 |
| D11 | no staleness gates on core inputs | `intelligence.py:273-279` etc. | W3 |
| D12 | single-vendor alt-data concentration | `engine/altdata.py` | W3 |
| D13 | policy LLM origination votes in scored path (LIVE A7 breach) | `policy_intent_desk.py:310,178` → `intel_hub.py:226,409-418,464-465` | **W0** |
| D14 | sector surfaces unlinked + name collision | §3.6 | W2/W3 |
| D15 | convergence ignores channel correlation/novelty | `altdata.py:1124` | W3(D)/G |
| D16 | score churn on facet dropout (SPCX 77→56) | `intel_hub.py` facets | W2/prereg |
| D17 | earnings acceleration not a Hub plane | `stagedata/earnings_table.json` | W2 |
| D18 | Discovery 135/149 candidates invisible; displayed cohort ungraded | `intel_hub.py:887-888` | W1/W5 |
| D19 | `strength` = max over non-comparable desk scales, multiplies opportunity directly | `intelligence.py:189-199` + `intel_hub.py:459,465` | W1 shadow → prereg |
| D20 | ledger accrual silently skipped (2026-08-04/07/08 absent) with page reading fresh | `data/hub/track_record.json` | W0 (monitor) |
| D21 | asof-or-before close lookups unbounded (stalled series grades on stale close, both legs) | `desk_scorer.py:96`, `ai_desk.py:236` | W0 |
| D22 | snapshot rows lack rank/cohort/hero-rejection fields | `hub_track_record.py:88-96` | W0 |

## Appendix B — DNR keys honored by this plan

DNR:KILL-FUSED-COMPOSITE · DNR:KILL-LLM-ORIGINATION · DNR:KILL-LLM-CONFIDENCE ·
DNR:KILL-CHATTER-PROMOTION · DNR:KILL-POLICY-TIMING-PREDICTOR ·
DNR:KILL-PROPHET-POP-MERGE · DNR:KILL-STAGE-WIN-GATE · DNR:KILL-PHASE3-START-WEIGHT ·
DNR:KILL-FRESH-BUY-EDGE · DNR:HOLD-IGNITION-SURFACES · DNR:KILL-ROTATION-CYCLE-CONFLUENCE ·
DNR:KILL-RS-DISPERSION-GATES · DNR:KILL-ROTATION-SCHEDULE · radar-leg kills
(RRX-R10 §6) · PSS entry-timing family kills/holds · DNR:LAW-REVERSION-RULER ·
DNR:KILL-OFFHORIZON-VERDICTS · SM2-R3 positioning-fusion ruling
(`engine/short_pressure.py:9-16`, module-level law, CI-enforced).

## Appendix C — red-team disposition (Opus review, 2026-08-08)

B1 squeeze-in-window → accepted, §6.1/6.2 amended (printed-only). B2 policy A7 breach →
accepted, moved to W0 (§3.5, §10.1). B3 cohort grading stats → accepted, §4.4 rewritten
(retro-reconstruction, mean-excess + date-block bootstrap, n=0 honesty). M1 yahoo
coverage shrink → accepted, §4.2 (era-stamped dual series + bounded lookups + backfill).
M2 findings noise → accepted, §4.6 significance gates. M3 tactic×regime → accepted,
§6.2/6.3 (price/ATR only). M4 sub-board empty-state → accepted, §8. M5 lanes-off premise
→ corrected, §3.4. M6 young-lane soft spots → accepted, §6.4 (planes not channels,
bar-count floor, traj-unknown). M7 accrual gating → accepted, §4.9 (display-only gates).
M8 governor repoint trap → accepted, §4.3 (fail-loud, radar_ic only). N1 render math →
folded into §4.4d. N2 collisions → §6.4/§4.5. X1/X2/X3 misses → adopted as §4.1, §4.10,
§4.9 (defects D19-D22).
