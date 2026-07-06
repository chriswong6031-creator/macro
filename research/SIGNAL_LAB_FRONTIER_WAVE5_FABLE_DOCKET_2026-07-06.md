# Signal Lab frontier Wave 5 — Fable-authored docket + gauntlet adjudication — 2026-07-06

Wave 5 inverts the process: ten candidates authored by Fable from first principles
(mechanism, forced/slow counterparty, and an explicit "why does this edge survive
arbitrage" story written before verification), then run through the same adversarial
gauntlet applied to Codex's waves 1–4: on-disk data receipts, external receipts,
program-ownership census, and an Opus red-team whose primary target was the survival
story — required to name who else already trades or sells each construct.

## Honest scoreboard of the Fable docket

**Of 10: 3 survive (each only in a narrowed variant) · 5 weakened to gates/accruals ·
1 refuted on data · 2 blocked by existing pre-registrations.** Zero candidates failed
on fabricated data claims (every claimed store existed as described), but one (F5-08)
failed on a *missing field* — the on-disk earnings-date store carries actual
announcement dates only, no scheduled dates, so the So-et-al. delay construct cannot be
measured as specified and its vendored form is owned by Wall Street Horizon (PO-2
violation). Two candidates (F5-03, F5-06) collided with live pre-registrations
(HK/Canada H1; Oracle Turn Asymmetry member-transmission) — the gauntlet catches the
orchestrator's blind spots exactly as it caught the generator's.

## Rulings

### BUILD-NOW (enters the queue): `w5_trade_size_capitulation` (F5-05)

The cleanest verdict in the set. Data fully ready (massive_stock_day `transactions`
column: zero nulls sampled, 20,476 tickers, 2021-07→now). Red-team verdict: survives —
the mechanism (Wyckoff effort-vs-result; Barclay-Warner stealth trading; VPIN lineage)
is old, but **nobody runs it at 20k-ticker whole-market scale in the small-cap bottoms
niche where institutions can't deploy** (PO-4 is the moat, not novelty).

**Frozen pre-registration** (variants final; grid logged at build time):
- Universe: US names, price>$2, 20d dollar-volume $0.5M–$50M (the capacity moat band),
  at/within 5% of 52-week low.
- Signal: avg_trade_size = volume/transactions; z of 20d avg-trade-size vs own trailing
  252d (Z-COLLAPSE, not level — cancels algo-slicing drift), interacted with depressed
  participation (dollar-volume z < 0).
- V1 (primary): trade-size z-collapse + low participation at lows → forward 21/63d
  return vs matched 52w-low baseline cohort. Pre-registered direction: collapse
  (retail-dominated tape) with subsequent stabilization → positive relative bounce.
- V2: inverse cell — trade-size EXPANSION at lows (institutional distribution) →
  negative continuation (AVOID read).
- V3 (control): raw volume z alone must NOT subsume V1 (incrementality gate).
- Gates: BH-FDR q≤0.10 across the 3×2 (variant×horizon) family; split-half same-sign;
  survives excluding 2022-H2 (the one bear cohort in the 5y window — crisis-concentration
  honesty); V1 must beat V3. Expected home: entry-quality confirmer for the
  durable-bottom program (program owner; family charged to its budget).
- Queue position: after the wave-2 queue items (WARN → ITC-337 → CMDI → housing → TSA),
  before the gaming tape and FFIEC.

### AUTHORIZED BEHIND DATA BUILDS (2)

- **F5-04 → dealer-conditioned signed option tape** (options-alpha program, resolving the
  ownership conflict by routing THROUGH that program). The red-team's ruling stands: raw
  signed premium is the most commoditized construct in the industry (SpotGamma,
  SqueezeMetrics, LiveVol, OptionMetrics) — dead on arrival. What survives is the
  residual only a tape-holder can build: signed flow conditioned on NBBO-inferred dealer
  positioning. Authorized now: the bounded tape pull (top ~500 liquid underlyings,
  2012-06→, off-render, R2 store, Lee-Ready classification at ingest). The residual
  construct pre-registers inside the options program after the tape lands.
- **F5-01 → unlock-driven block sector read-through** (china-alpha). Narrowed per
  red-team: only blocks cross-referenced to the unlock calendar (forced supply, not
  pledge liquidation). Blocked today by a real gap: the block store is a rolling
  snapshot with no historical tape. Authorized now: the daily block-tape archiver +
  Shenwan L1 sector mapping; backtest when the tape exists or a historical backfill
  path is verified.

### ROUTED (4)

- **F5-06 → Oracle Turn Asymmetry program**: laggard-diffusion is a within-episode
  *weighting* refinement of the booked member-transmission result (#1533), not a new
  family — same fish, second net. Handed over as a design note charged to OTA's budget:
  diffusion signal = residual cohesion after the confirmed transmission effect,
  pre-registered against episode-equal-weight.
- **F5-03 → HK/Canada H1**: my candidate was a duplicate of the live H1 prereg. One
  material addendum from receipts: the per-stock holdings store starts 2024-07 (~2y,
  single regime) — H1 itself is accrue-shaped and should carry that clock explicitly.
- **F5-02 → china-alpha, de-escalation gate only**: onshore ETF creation impulse is
  watched by every China desk as the national-team tell; the only R3-legal, non-crowded
  use is downweighting risk-off escalations while the state is visibly defending.
- **F5-07 → china-alpha, divergence variant + ACCRUE**: raw LHB seat-following is a
  retail cottage industry (THS/东财 seat products, 游资 trackers). Only the
  institutional-seat vs hot-money-seat *divergence* on the same name survives, and the
  store is 2024-07+ — two years, accrue clock.

### ACCRUE (1)

- **F5-09 10b5-1 adoption/termination**: correctly short-history by its own admission
  (~2.5y since S-K 408(a)), and Quiver/InsiderScore/Washington Service already parse it —
  the moat is smaller than drafted. Build the extractor + freeze the gates now
  (termination=bullish / oversized-adoption=bearish); verdict ≥2027-H1.

### AVOID-OVERLAY, display only (1)

- **F5-10 → qualitative-intelligence/special-situations**: Audit Analytics sells exactly
  this feed to shorts — no alpha claim survives. The narrowed form ships as a display
  AVOID overlay: NT-filing + item-4.01 auditor-change co-occurrence within 90 days,
  small-cap exclusion lens per the L1 short-side charter (AVOID-not-SHORT).

### KILLED (1)

- **F5-08 earnings-date delay**: refuted as specified — no scheduled-date field exists
  on disk (actual announcement dates only, 1,314 tickers), and the vendored version is
  Wall Street Horizon's flagship (PO-2). The surviving cousin (own-cadence drift z as a
  SUE-conditioning flag) is noted for the factor family, not a frontier family.

## Rule amendment adopted: PO-1b (latent-factor orthogonality)

The red-team's cross-docket ruling: F5-01/02/07 have genuinely distinct ticker sets
(peers-of-blocked-names / broad-index ETFs / LHB names) yet all load the same latent
factor — CN-A onshore liquidity/sentiment. Ticker-set disjointness is necessary but not
sufficient. **PO-1b: candidates whose payoffs load a common latent factor (same market ×
same flow regime) count as one vertical for advance purposes; at most one may hold a
build slot at a time, and its result gates the others.** Applied here: F5-01 holds the
CN-A slot (behind its data build); F5-02/F5-07 wait on its outcome.

*In plain English: this time the ideas came from us, built around a specific reason each
edge should still exist. The same hostile review that shredded the machine-generated
lists was applied — and it trimmed ours too: one idea died because a needed data field
doesn't exist, two turned out to already be registered experiments elsewhere in the
shop, and several got cut down to their one defensible corner. What's left: one test
that starts when a slot opens (reading the tape of tiny stocks at their lows to tell
panicked selling from quiet accumulation — a place too small for big funds to fish),
two bigger builds that first need their data assembled (our own options tape, a Chinese
block-trade archive), and a set of narrower experiments filed where they belong. That's
what an honest week-one of a research program looks like.*
