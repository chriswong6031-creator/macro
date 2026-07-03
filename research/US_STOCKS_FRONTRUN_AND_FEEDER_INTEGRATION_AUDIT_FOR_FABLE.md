# Front-Running the Rotation — US Stocks × Feeder-Engine Integration Audit (for Fable)

> **Role split (owner directive).** Opus produced this assessment, the mechanism map, the
> evidence, and the candidate-solution seeds. **Fable** does the second-pass reassessment, the
> novel-idea generation, and authors the phased fix plan (then delegates Opus/Sonnet to execute).
> This document is a *fixed input*: it pins the problem and the guardrails so the wrong test is hard
> to run. It is a problem map, not a spec. Authored 2026-07-03. Every load-bearing claim is cited to
> `file:line` or to a live artifact read this session.

---

## 0. Read this first — how this document relates to the ones already written

This is **not** a re-audit of the Standout board's internal ranking/scoring honesty. That work is
done and rigorous — do not re-run it:

- **`research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md`** (45KB) — the board-internal audit: `rank_by="bottoming-alignment"`
  ordering, the `potential_score`-overwrites-alpha inversion (`corr(score,alpha)=−0.31`),
  `entry_open_first` handing slot #1 to the weakest name, sector concentration (56% of buys from 2
  sectors), the inert honesty gate. **Treat its findings as accepted priors here.**
- **`research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md`** (2026-07-02) — the
  "entry passed the gate many ticks ago" problem *at the single-name level*: `FRESH_TICKS=2` +
  `not_topped` veto kills the based-and-coiled-late archetype (MCD/KO). Discriminator = extension-since-cross.
- **`research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md`** — the COILED cohort-washout program and,
  critically, the **falsified-ideas ledger** (H2 "aged quiet base" wrong-sign; H4 "volume dry-up"
  dead; near-low+fresh anti-correlates with forward return). Any solution that re-derives these is
  dead on arrival.
- **`research/ANTICIPATION_ENGINE_DESIGN.md`**, `SECTOR_CONFLUENCE.md`, `SECTOR_BOTTOM_RADAR.md` —
  the honesty contracts for the timing/bottoming stack.

**What THIS document adds** — the axis the owner emphasized in this session and the prior docs
under-cover: the **system-level integration** of the thematic-basket / sector-rotation / confluence
feeders into stock selection, the **front-running / early-detection** objective (surface a sector
*before* it runs, not mid-cycle), and the **accuracy/validation** of the feeders themselves. The
prior audit asked "is the board honest about the ~0 selection edge it has?" This one asks a
different question: **"is the board even measuring the right thing, and are the engines that could
front-run the rotation actually wired to it?"** The answer to both is no, and the two failures share
one root cause.

---

## 1. TL;DR

### The single deepest root cause — the system is split along the wrong seam, and the board is run by the wrong brain

The codebase contains **two brains** that never merge into the product the owner actually wants:

- **Brain A — SELECTION / EDGE.** Cross-sectional "which name is better." It orders `us_standouts.json`.
  Its own point-in-time harness shows its edge is **~zero** (rank-IC +0.008..+0.021, nothing survives
  FDR except insider, present on 2/34 rows — `US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md §1`). The board
  is ranked by this brain.
- **Brain B — TIMING / BOTTOMING / ROTATION.** The *entire feeder stack* the owner named:
  thematic baskets, `subsector_rotation`, `sector_bottom`, `bottom_radar`, `subsector_confluence`,
  `coiled`, the T1–T4 confluence cascade. This brain is **validated on the axes that matter for
  entries** (drawdown, stop-out, clean-liftoff — `sector_central.py` docstring cites the trend gate
  as a `validated_risk_control`; COILED cohort-washout is +6–7.5pp clean-liftoff / −5.6pp stop-out).

**The owner's stated product — "surface great stocks in about-to-lead sectors, where the stock is
just about to run up, using our thematic baskets coupled with our confluence gates and other
engines" — is ~90% Brain B's job.** But the architecture does the opposite of what the product needs:

1. **Brain B is contractually forbidden from ranking the board.** Every timing/bottoming engine
   carries an honesty clause: "entry timing has NEGATIVE forward-return correlation … MUST NOT touch
   the cross-sectional selection rank" (`bottom_radar.py:6-12`; identical language in
   `sector_bottom.py`, `basket_score.py`, `narrative_rotation.py`). So the brain that serves the
   product is quarantined to *display*.
2. **The one Brain-B signal that IS allowed into the rank measures the wrong direction.** The sole
   quantitative feeder→rank channel is the "basket tailwind," scored as the theme's **20-day
   relative return** (`build_stock_library.py:595`, `perf.20d.rel`). That is *trailing momentum* — it
   rewards themes that have **already run**, the exact opposite of front-running a bottoming sector.
   And it is ~10% of the composite (`US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md §2`).
3. **The purpose-built early-detection engines are orphaned from the board.** `subsector_confluence`
   — whose own docstring says it exists *specifically* because "the Standout board … has NO
   subsector-condition gate" — has **zero references in `build_stock_library.py`.** So do
   `bottom_radar` and `sector_bottom`. They feed *other display pages*, never the stock board.

So the board is ranked by a near-zero-edge selection brain on an objective (cross-sectional forward
return) the product doesn't care about, while the validated timing/rotation brain that the product is
actually made of is either quarantined or measured backwards. **This is why sessions keep failing:
each fix tunes Brain A's honesty, but the product lives in Brain B, which isn't allowed to drive.**

**The reframe Fable should reason on:** re-found the board's *objective* as **capital-efficient entry
into durable, breadth-confirmed sector bottoms** — Brain B's validated home turf — and grade it on
Brain B's validated axes (stop-out / clean-liftoff / dead-money / MAE / recall), **not** rank-IC. Then
the feeders become *primary selectors*, the ~0 cross-sectional alpha becomes a quality tiebreak, and
the "front-run before takeoff" promise is served by the machinery built for it.

### The 5 highest-leverage problems (this document's scope)

1. **Objective mismatch (Cluster A).** The board is graded/ranked on a forward-return objective its
   own harness shows is unwinnable, when the product objective is entry/drawdown efficiency. The
   board's forward track is *literally empty* (`us_board_track.json` → `{"empty": true}`), so nothing
   even measures the product's real objective today.
2. **The feeder→rank channel is trailing, not leading (Cluster B).** Basket tailwind = 20d relative
   return (`build_stock_library.py:595`). It systematically up-weights themes mid/late-cycle and
   under-weights the washed-out/basing themes the owner wants to front-run.
3. **The early-detection engines are orphaned (Cluster C).** `subsector_confluence`, `bottom_radar`,
   `sector_bottom` = 0 wiring into the stock board. The gap they were built to close is still open on
   the artifact the user reads.
4. **Sector-clock vs stock-clock desync (Cluster D).** A sector is confirmed a leader by a *lagging*
   RRG lens weeks after its constituents' `FRESH_TICKS=2` entry windows expired. Nothing re-arms a
   constituent's entry when its sector *finally* confirms. This is the owner's "de facto leader but
   entry passed the gate many ticks ago" complaint, and it is a distinct, integration-level bug from
   the single-name BASING problem.
5. **The front-run signal is unproven and the breadth model is too narrow (Cluster E).** The flagship
   "emerging" rotation signal has 5 days of snapshots and **zero matured observations** (`proven: all
   False`, `verdict: accruing`). The owner's "many stocks in the sector washed out and basing"
   breadth model exists only as `coiled.cohort_fractions` (≥0.40 threshold, half-tier bonus, ~7%
   recall of durable bottoms).

### The cross-cutting threads (every finding is one of these)

- **T1 — Wrong objective.** Return-alpha is measured and optimized; entry/drawdown efficiency (the
  product) is not the board's grading target, so the validated levers can't earn rank power.
- **T2 — Trailing-where-leading-is-needed.** Every wired feeder signal (tailwind 20d, RRG rs_ratio,
  cycle-state dict) is coincident-to-lagging; the leading components (accel, Improving-quadrant,
  bottom_radar PRIMED, coiled cohort) are either unwired or unproven.
- **T3 — Quarantine-by-honesty.** The honesty contracts correctly killed *return-alpha* claims for
  timing, then over-generalized to "display-only," locking the validated *drawdown* levers out of the
  rank. The contracts protect the right thing (no fake alpha) but enforce the wrong remedy (no rank
  power at all).
- **T4 — Clock desync.** Sector/theme confirmation and single-name entry run on different, un-reconciled
  clocks; the board never re-opens a name's window when its context finally confirms.
- **T5 — Validation debt.** The board and its front-run feeder are both unvalidated (empty / 5-day
  accruing), so no fix can be graded and every session argues from first principles instead of a ledger.

---

## 2. The stated product vs. the built system

The owner's product spec, verbatim intent (this session):

> "Surface stocks that are both great picks in about-to-lead sectors where the stock is just about to
> run up, using our data from thematic baskets coupled with our confluence gates and other engines …
> by *heating up* I don't mean already running by a lot; I mean basing, or lots of stocks in the
> sector washed out and bottomed and then basing or ticking up, and we see confluence in the
> technicals show it's a great time to enter."

Decomposed into the four measurable capabilities the product requires, and where each stands:

| # | Required capability | Built? | Wired to the board? | Validated? |
|---|---|---|---|---|
| C1 | Detect a sector/theme **bottoming/basing early** (before it runs) | Yes — `sector_bottom`, `bottom_radar`, `subsector_rotation` accel/Improving | **No** (orphaned) / tailwind only, and it's trailing | **No** (rotation track 5d, 0 matured) |
| C2 | Measure **breadth of bottoming** ("lots of stocks in the sector washed out") | Partially — `coiled.cohort_fractions` | Yes, as a **half-tier** bonus only | Cohort-washout validated; recall ~7% |
| C3 | **Confluence entry** timing on the name | Yes — T1–T4 cascade, `signal_gate` | Yes for `setups.json`; **badge-only** for the wide board | Cascade held-out stop-out validated |
| C4 | **Compose** C1×C2×C3 so a name surfaces *because* its sector is bottoming AND it's a fresh entry | **No** — `subsector_confluence` built this and is orphaned | **No** | n/a |

**The product is C4. C4 is the one capability that was designed (`subsector_confluence.py`) and never
connected.** Everything else is present but siloed or pointed the wrong way. The gap is not missing
math — it is missing *wiring* and a missing *objective* to wire it toward.

---

## 3. Mechanism map — how the feeders connect to selection today (verified 2026-07-03)

**Live artifact chain:** `us_stocks.html` (567KB) is rendered from `templates/dashboard.html.j2`
(not `us_stocks_v2.html.j2`, which is **unlinked/experimental** — 0 refs in `_navlinks`/`config.yml`/
`build_site.py`; its aspirational line "Rotation context … sets PRIORITY, never a gate" describes a
page that isn't shipped). The board data is `site/factordata/us_standouts.json`, built by
`scripts/build_stock_library.py`.

**What the builder actually imports from the feeder stack** (`grep '^from\|^import' build_stock_library.py`):

```
signal_gate          (:30)   — T1→T4 confluence cascade   [WIRED: gate + badge]
baskets              (:592)  — thematic baskets            [WIRED: tailwind = 20d rel return]
theme_scoring        (:665)  — per-basket score/label      [WIRED: spotlight tilt, display]
narrative_rotation   (:700)  — allocation/trend-gate state [WIRED: _basket_risk de-risk]
coiled               (:53)   — cohort-washout bonus        [WIRED: ~half-tier ranking bonus]
anticipation         (:389)  — forward cone                [WIRED: DISPLAY-ONLY risk read]
```

**What it does NOT import** (each = 0 hits in the builder, verified):

```
subsector_confluence   — the double-gate (stock buyable AND subsector buyable)   ORPHANED
bottom_radar           — anticipation-tier early-bottom PRIMED score              ORPHANED
sector_bottom          — per-sector bottom_confidence + washout temper            ORPHANED
```

Where the orphans actually go: `subsector_confluence` → `subsectors.js`, `index_leadership`,
`group_context`; `bottom_radar` → `index_leadership`, `validation`; `sector_bottom` →
`vol_shock_scorecard`. **They power sibling display pages, never the stock-selection rank.**

**The one quantitative feeder→rank channel, in full** (`build_stock_library.py:585-608`):

```python
def _basket_tailwind_map():
    # "the strongest theme a name belongs to, scored by that basket's 20d return vs the benchmark"
    rel = ((b.get("perf") or {}).get("20d") or {}).get("rel")   # <-- TRAILING 20d relative return
    ...
    if prev is None or abs(rel20) > abs(prev["rel20"]):          # <-- strongest-|20d| theme wins
        out[sym] = {"name": b.get("name"), "rel20": rel20}
```

Consequence: a name in a theme that already ran +15% over 20d gets the maximum tailwind; a name in a
theme that just washed out and is basing (rel ≈ 0 or negative) gets *zero or negative* tailwind. **The
feeder channel is calibrated to reward exactly the mid-cycle names the owner is trying to avoid.**

**The board's grading state, verified live:**
- `site/factordata/us_board_track.json` → `{"empty": true, "note": "no matured graded rows"}`.
- `data/subsector_rotation/track_record.json` → `n_days: 5`, `n_matured: 0` at every horizon,
  `proven: {5:false,10:false,21:false,63:false}`, `verdict: "accruing"`.

---

## 4. Problem clusters (ordered by leverage)

### Cluster A — The board optimizes/grades the wrong objective

**A1. The product is entry/drawdown efficiency; the board is ranked and (not-)graded on cross-sectional forward return.**
- *Evidence:* the board rank key is `bottoming-alignment`→`composite_z` (Brain A);
  `US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md §1` establishes that objective's edge is FDR-dead. Meanwhile
  every Brain-B engine is validated on *drawdown/stop-out/clean-liftoff* (`sector_central.py`
  header: absolute-trend gate = `validated_risk_control`, MaxDD −0.49→−0.24; COILED +6–7.5pp
  clean-liftoff). The board's forward track is `empty:true` — so the objective the product cares
  about (did we enter durable bottoms efficiently?) is **not measured at all.**
- *Mechanism:* return-IC was chosen as the grading yardstick because it is the standard quant
  yardstick, not because it fits the product. On this yardstick the timing brain *correctly* fails
  (timing has negative return-IC), so the honesty layer quarantines it — and the product loses its
  engine to a category error.
- *Owner-harm:* every past "fix" was scored on the wrong axis, so real improvements to entry
  efficiency looked like noise and real degradations to it were invisible.
- *Solution seeds (for Fable to refine/replace):*
  - Adopt the **DURABLE_BOTTOM measurement constitution** (stop-out / clean-liftoff (+15% before −5%)
    / dead-money / recall, per-fire count-fair) as the board's *primary* grader, replacing/augmenting
    the rank-IC gate. Rank-IC becomes a *secondary* honesty check on the alpha tiebreak, not the pass/fail.
  - Make the board's forward track non-empty *first* (it grades nothing today) so any subsequent
    change is measurable.
- *Open questions for Fable:* If the true objective is drawdown-efficient entry, is a *ranked 34-name
  BUY board* even the right artifact, or should it be a *set of armed sector-cohorts with per-name
  entry states*? Does "rank" survive at all, or does it become "which cohorts are armed × which names
  in them are fresh"?

**A2. The honesty contracts protect the right thing but prescribe the wrong remedy.**
- *Evidence:* `bottom_radar.py:6-12`, `sector_bottom.py`, `basket_score.py`, `narrative_rotation.py`
  all read: timing/momentum has ~0-or-negative *return* IC → therefore *display-only, must not touch
  selection rank.* The inference "no return alpha ⇒ no rank power" is the load-bearing error.
- *Mechanism:* a signal can be worthless for *return-ranking* yet decisive for *entry-timing/drawdown
  ranking* — different objective, different validity. The contract collapses the two.
- *Solution seed:* Split the contract: "MUST NOT rank *for forward return*" (keep) vs "MAY rank *for
  entry/drawdown efficiency, graded on the DURABLE_BOTTOM axes*" (unlock). This preserves the honesty
  discipline exactly where it's earned while freeing the validated levers to do the product's job.

---

### Cluster B — The feeder→selection channel measures trailing momentum (anti-front-running)

**B1. Basket tailwind = 20d relative return.**
- *Evidence:* `build_stock_library.py:595` (`perf.20d.rel`), `:604` picks the strongest-|20d| theme.
- *Mechanism:* trailing 20d return peaks *mid/late* in a theme's move; it is near-zero at the bottom.
  The channel therefore up-weights names whose theme already ran and near-zeros names whose theme is
  basing — inverting the owner's intent.
- *Owner-harm:* directly manufactures the "we keep getting fed mid-cycle sectors and picks" symptom.
- *Solution seeds:*
  - Replace 20d-return tailwind with an **early sector-state score** = f(bottoming-breadth `coiled`
    cohort-fraction, rotation *acceleration* not level, confluence-cross freshness on the sector's
    equal-weight index via `subsector_confluence`/`sector_signals`). Reward *turning up from washout*,
    not *already up*.
  - If a trailing-return term survives at all, make it a **veto on lateness** (extension penalty,
    mirroring China's validated `EXT_PENALTY=0.5`), not a positive contributor.
- *Open question for Fable:* Should the sector channel ever be *additive to a name's score*, or should
  it be *the gate that decides which cohorts are eligible at all* (Cluster C/D)? The additive framing
  is what let it be set to 20d-return in the first place.

**B2. The `narrative_rotation`/trend-gate feeder is a trend-follower — structurally late by design.**
- *Evidence:* `narrative_rotation.py` header — trend-following, absolute-SMA-200 gate; "the one
  repeatable edge is CRASH avoidance / staying power," momentum rank-IC ~0.
- *Mechanism:* an SMA-200 absolute-trend gate *cannot* be early — it admits a theme only after it has
  reclaimed a 200-day average, i.e. well after the bottom. It's the right tool for *drawdown control*
  and the wrong tool for *front-running*. The board uses it (via `_basket_risk`) as a de-risk, which
  is fine — the problem is that it's the *only* rotation input with rank influence, so "don't get
  crashed" is represented but "get in early" is not.
- *Solution seed:* Keep the trend gate as the **de-risk/size** leg (its validated job) and add a
  *distinct* **early-arming** leg (bottoming-breadth × accel × confluence-freshness) as the
  surfacing/priority leg. Two legs, two jobs — never one number.

---

### Cluster C — The early-detection engines are orphaned from the board

**C1. `subsector_confluence` (the C4 capability) is built and disconnected.**
- *Evidence:* its docstring names the exact gap — "The Standout board (`build_stock_library` →
  us_standouts.json) gates SINGLE names with the validated T1-T4 cascade but has NO subsector-condition
  gate, so a great stock in a sector institutions are distributing ranks identically to one with a
  tailwind. This module closes that gap." Yet `grep subsector_confluence build_stock_library.py` = 0.
  It feeds `subsectors.js` / `index_leadership` / `group_context` instead.
- *Mechanism:* the double-gate ("stock buyable AND its subsector buyable") — literally the product's
  C4 — runs, renders on subsectors.html, and is thrown away before it can filter or order the board.
- *Owner-harm:* the single most on-thesis engine in the repo produces nothing the stock board sees.
- *Solution seed:* Wire `subsector_confluence`'s subsector-state (buyable / setup / distributing) into
  the board as **eligibility + priority**: a name in a distributing subsector is demoted/gated; a name
  in a *buyable-and-freshly-crossing* subsector is surfaced. Start as a priority tilt + chip with a
  forward ledger (repo discipline), earn gate power after grades accrue.

**C2. `sector_bottom` / `bottom_radar` (the early bottom detectors) feed everything except the board.**
- *Evidence:* `sector_bottom.py` → only `vol_shock_scorecard`; `bottom_radar.py` → `index_leadership`,
  `validation`. Both 0 in the builder. `sector_bottom.py` even *names* the problem it should fix:
  "The Sector Heat Board's RRG stages … confirm a turn weeks late and — by construction — never
  separate a durable sector low from a falling knife."
- *Mechanism:* the repo already has "the SAME validated bottoming machinery the stock library runs per
  name" applied *at the sector level* — the exact C1 capability — and it's routed to a scorecard the
  board doesn't read.
- *Solution seed:* Feed `sector_bottom.bottom_confidence` (per-GICS-sector, walk-forward calibrated
  monotone on 69k evals) as the **sector-eligibility conditioner** for the board: only surface
  washed-out-basing names whose *sector* also scores a durable bottom (not a knife). This is the
  breadth/durability confirmation the owner asks for, already built and validated.

---

### Cluster D — Sector-clock vs stock-clock desync ("de facto leader but the entry already passed")

**D1. Sector leadership confirms on a lagging clock; constituent entry windows expire on a fast clock; nothing reconciles them.**
- *Evidence:* leadership/rotation reads (`subsector_rotation` RRG rs_ratio, `playbook.stage_table`)
  are, by `sector_bottom.py`'s own admission, "200-day-smoothed … confirm a turn weeks late." The
  single-name entry gate is `FRESH_TICKS=2` (~6 days on the 3D master, `confluence_tiers.py:44`) +
  `not_topped`. So by the time a sector is *confirmed* leading, its washed-out constituents crossed
  confluence 3–10+ ticks ago and are `eligible=False`. There is no code path that says "sector X just
  confirmed leadership → re-arm entry for X's basing constituents."
- *Mechanism:* this is a **different bug from the single-name BASING problem** (which is "one name's
  cross aged out"). This is *integration-level*: the two engines that must agree for a C4 surfacing —
  sector-confirmation and name-entry — operate on incompatible latencies and never hand off. The BASING
  doc's D3 ("gate the re-admit on sector leadership") is the *name-level* version; D1 here is the
  *portfolio-construction* version: **sector confirmation as a re-arm event broadcast to constituents.**
- *Owner-harm:* the exact stated failure — "a sector may become a de facto leader but the entry for
  stocks in that sector passed the gate many ticks ago, so we can't buy at the right time."
- *Solution seeds (for Fable):*
  - **Sector-confirmation → constituent re-arm.** When a sector/subsector transitions to
    confirmed-leading (or `sector_bottom` flips to durable-bottom), re-open a bounded re-entry window
    for its constituents that are *based-low-extension* (reuse BASING's extension-since-cross
    discriminator so JNJ/AMAT stay out). The sector event supplies the confirmation the aged name's
    freshness can't.
  - **Lead the confirmation, don't wait for it.** Replace the *level*-based leadership read
    (rs_ratio) with an *acceleration/breadth*-based arming read so the sector "confirms" earlier and
    the two clocks overlap. (Ties to Cluster B's early sector-state score.)
  - **Pre-position on breadth, not on the leader.** Surface the *cohort* when bottoming-breadth
    crosses a threshold (many constituents washed-out-and-basing), *before* any single name is a
    confirmed leader — the owner's literal "lots of stocks in the sector washed out and basing" trigger.
- *Open question for Fable:* is the right primitive a *re-arm event* (keep the fast gate, re-fire it
  on sector confirmation) or a *slow parallel window* (a BASED tier that lives as long as the sector
  stays constructive)? The event framing keeps the validated freshness axis; the window framing risks
  re-deriving the falsified H2 "aged quiet base." Lean event.

---

### Cluster E — Feeder accuracy & validation (don't let a bad feeder plague the board)

**E1. The flagship front-run signal is unproven.**
- *Evidence:* `subsector_rotation` ranks 268 subsectors by `emerging_score` and labels
  emerging/fading — forward claims. Its own grader (`subsector_track_record.py`,
  `data/subsector_rotation/track_record.json`) reports `n_days:5`, `n_matured:0`, `proven:` all
  `false`, `verdict: accruing`. **There is zero evidence the "emerging" signal front-runs anything.**
- *Mechanism:* the harness is honest and correct (`CONTEXT-ONLY · DEGRADE-NEVER-RAISE`) — but the
  signal is 5 days old. If Fable wires `emerging_score` into selection now, it wires an unvalidated
  claim into the product. Sequencing matters: **prove, then wire.**
- *Solution seed:* Backfill the track record from history (the snapshot inputs are Finviz perf
  horizons that can be reconstructed PIT) to get matured obs *now* instead of waiting a quarter, then
  wire only the horizons/quadrants that clear the HAC-t bar.

**E2. The breadth-of-bottoming model is too narrow and low-recall.**
- *Evidence:* the owner's "lots of stocks in the sector washed out and basing" maps to exactly one
  construct: `coiled.cohort_fractions` (`coiled.py:248`), gated at `cohort_frac ≥ 0.40`
  (`coiled.py:298-309`), delivered as a **half-tier** bonus (`build_stock_library.py:1686`). Per the
  BASING/DURABLE docs, COILED "recalls only ~7% of durable bottoms."
- *Mechanism:* a single hard 0.40 threshold + half-tier weight can't express "the sector is 25%
  washed-out and accelerating" or "60% washed-out and basing." It's a binary-ish nudge, not a graded
  breadth-of-bottoming surface.
- *Solution seeds:* promote **sector bottoming-breadth to a first-class, graded feeder** (fraction of
  cohort washed-out × fraction basing × fraction with a fresh confluence cross), sweep the threshold
  instead of hardcoding 0.40, and let it *drive* surfacing (Cluster C/D) rather than nudge a rank.
  Grade on the DURABLE_BOTTOM axes.

**E3. Feeder data-provenance risks to audit (so a bad feed doesn't silently poison the board).**
- The rotation feeder rides Finviz's broad `perf_snapshot.json` (268 subsectors incl. names we hold
  no prices for) — a *different universe* from the 34 curated baskets; cross-universe joins are a
  known silent-drop surface. The basket tailwind reads `baskets.compute_baskets()` live in-process,
  so a stale/failed basket collect degrades to `{}` and the axis *silently vanishes* rather than
  flagging (`build_stock_library.py:606-607`, "never fatal"). **Missingness-as-neutrality** (the prior
  doc's cross-cutting thread #3) applies to the feeder channel too: a dead feeder reads as "no
  tailwind," not "unknown — reduce confidence."
- *Solution seed:* a feeder **health gate** that marks a name's sector-context as `unknown` (and
  demotes/abstains) when the feeder that should cover it is stale/empty, instead of defaulting to
  neutral. Reuse the `run_status.json` / circuit-breaker pattern already in the repo.

---

### Cluster F — Per-feeder-dashboard specific findings

*(Grounded in each engine's docstring/scoring core, read this session. These are the pages the owner
named as "support"; each is individually fine as a display but mis-serves its role as a board feeder.)*

- **`subsector_rotation.html` (`engine/subsector_rotation.py`).** *Role as feeder:* the early-rotation
  watchlist (Improving-quadrant + positive `accel`). *Problem:* (i) unproven (E1); (ii) the headline
  quadrant read is `rs_ratio × rs_mom` = *level × its slope*, both trailing; the genuinely-leading
  `accel` term is a sub-signal, not the headline; (iii) not wired to the board. *Direction:* elevate
  `accel`/Improving to the arming signal, prove it, wire it as Cluster-B/C early sector-state.
- **`sector_central.html` (`engine/sector_central.py`).** *Role as feeder:* per-sector fused
  intelligence (cycle → gate → confirm). *Problem:* it is a *confirmation/context* fuser (cycle state
  as LEAD, trend gate as GATE) — excellent for "is this sector permissible/de-risked," but its LEAD
  leg is cycle-rhythm ("not a forecast," per its own header), so it too confirms rather than
  front-runs. It has a grader (`sector_central_grader.py`) — check its matured-obs count before
  trusting it as a feeder. *Direction:* use it as the *eligibility/de-risk* conditioner (its
  validated job), not the *surfacing* trigger.
- **`baskets.html` (`engine/baskets.py`, `basket_score.py`).** *Role as feeder:* the thematic tailwind
  source. *Problem:* `basket_score` textures are all `directional: False` (honest), and the tailwind
  the board actually consumes is 20d-return (B1). The `EMERGING` clean-entry texture *exists* in
  `basket_score` ("whether it is an EMERGING clean entry") but the board reads `perf.20d.rel`, not the
  EMERGING flag. *Direction:* consume `basket_score`'s EMERGING/roll-over textures instead of raw
  20d-return; they already encode "early vs extended."
- **`subsectors.html` (`engine/subsector_confluence.py`).** *Role as feeder:* the double-gate (C4).
  *Problem:* orphaned from the board (C1). It is arguably the highest-value rewiring in this document.
  *Direction:* the primary Cluster-C fix lands here.

---

## 5. What is already RIGHT — do not "fix" these (contrarian guardrails)

Fable should refute the above, but must not regress these — they are correct and hard-won:

1. **The honesty contracts' *diagnosis* is right:** timing/momentum genuinely has ~0/negative *return*
   IC. Do not re-introduce timing as a *return-alpha* claim. The unlock is a *different objective*
   (drawdown/entry efficiency), not a re-litigation of return alpha.
2. **The absolute-trend gate is validated drawdown control** (`sector_central.py`, `narrative_rotation.py`).
   Keep it as the de-risk/size leg. It is *supposed* to be late.
3. **`FRESH_TICKS=2` correctly kills the blasted-off-late case** (JNJ/AMAT). Any re-arm/window must keep
   that cohort out — extension-since-cross is the proven discriminator (BASING §3).
4. **The falsified ledger is real:** H2 "aged quiet base" (wrong sign), H4 "volume dry-up," "near-low+fresh
   anti-correlates with forward return." A breadth/early solution must not collapse into these — grade
   count-fair on stop-out/clean-liftoff/dead-money, never round-trip return.
5. **COILED cohort-washout is validated** (+6–7.5pp clean-liftoff / −5.6pp stop-out). It is the seed of
   the breadth model, not a thing to replace — promote it, don't discard it.
6. **The forward-ledger discipline** (ship as bonus/chip → grade → earn gate power) is the correct
   rollout shape. Every seed here should follow it.

---

## 6. Novel solution seeds (Opus's own suggestions — for Fable to assess/replace)

These are *seeds*, generated deliberately to differ in mechanism (per the same-sentence test). Fable
should discard, merge, or invent past them.

**N1 — The "Armed Cohort" board (re-found the artifact around C4).** Stop shipping a ranked 34-name BUY
list. Ship a small set of **armed sector-cohorts** — a sector/subsector is *armed* when
(bottoming-breadth ≥ θ) AND (`sector_bottom` durable-bottom, not knife) AND (rotation *accelerating*,
not just leading). Within each armed cohort, list constituents by **entry state** (fresh confluence
cross / based-low-extension / extended-avoid), not by cross-sectional alpha. The board becomes "here
are the 2–4 sectors bottoming as a group, and the names inside them with live entries" — literally the
owner's sentence. Alpha becomes a within-cohort tiebreak. *Kills:* fixed-width fill pressure, sector
concentration (it's now *intentional* and labeled), the objective mismatch. *Risk:* fewer/zero cards
in some regimes — which is the honest state, and abstention is the point.

**N2 — Two-clock reconciliation via a sector re-arm bus.** A single event channel: when
`subsector_confluence`/`sector_bottom`/rotation emit a *confirmation transition* for a sector, broadcast
a `sector_confirmed` event; the name-entry gate subscribes and re-opens a bounded window for based-low-
extension constituents. Keeps the fast validated freshness gate intact; adds exactly one new object (the
event), not a new stale-admit tier. *This is the direct fix for the owner's headline complaint (D1).*

**N3 — Lead-lag inversion of the tailwind.** Replace the 20d-return tailwind with a **bottoming-phase
score** whose *maximum* is at "washed-out and just ticking up" and whose value *decays* as the theme
extends (an inverted-U in extension). Concretely: `phase = f(−extension_from_low, +breadth_washed_out,
+accel, +confluence_freshness)`, clipped so a +15%-already theme scores *low*. Same wiring slot as
today's tailwind, opposite calibration. Cheapest possible first move — it's a one-function swap in
`_basket_tailwind_map`.

**N4 — Grade the board on MAE/clean-liftoff, and publish it.** Stand up the board's forward ledger on
the DURABLE_BOTTOM axes *first* (it's empty today), including a "would we have front-run it?" lead-time
metric: for each name that later ran, how many ticks *before* the run did the board surface it? Negative
lead-time = we were late = the exact failure the owner reports, now *measured*. No selection change ships
until this ledger can grade it.

**N5 — Breadth-first surfacing with a leader-confirmation upgrade.** Two-stage: (stage 1) surface a
cohort on *breadth of bottoming* alone (early, lower-precision, labeled "forming"); (stage 2) *upgrade*
its label to "confirmed" when a leader/RRG/`sector_central` confirmation arrives. The user sees the
sector *forming* early (front-run) and *confirmed* later (conviction) — the two clocks become two labels
on one object instead of two disconnected engines. Mitigates E1's unproven-signal risk: the early stage
is explicitly lower-confidence.

**N6 — Cross-feeder agreement as the precision lever.** The feeders are *independent lenses* (Finviz-RRG,
our-basket-tailwind, price-confluence, cohort-washout, sector bottom_confidence). Require **≥k-of-n
feeder agreement** to arm a cohort, rather than trusting any single (unproven) feeder. This buys
precision from redundancy without needing any one feeder to be individually validated — a bridge that
lets the system front-run *now* while the individual track records accrue.

---

## 7. Suggested first moves for Fable

1. **Reconcile the objective (decisive, cheap).** Decide explicitly: is the US Standout board a
   *cross-sectional return-alpha* product or an *entry/drawdown-efficiency* product? The whole document
   forks on this. The evidence says the latter is the only one with a validated engine. Commit, then
   re-derive the grader (N4) before touching selection.
2. **Stand up the board's forward ledger on DURABLE_BOTTOM axes + lead-time** (N4). It is empty today;
   nothing can be graded until it isn't. Backfill rotation track history (E1) so the front-run feeder
   has matured obs.
3. **Fix the cheapest, highest-signal wire first:** the lead-lag inversion of the tailwind (N3) — one
   function, opposite calibration — and measure lead-time before/after.
4. **Wire the orphan `subsector_confluence` as priority+chip** (C1/N1), forward-ledger it, earn gate
   power after grades.
5. **Build the sector re-arm bus (N2)** for the owner's headline complaint (D1); keep JNJ/AMAT as the
   regression fixtures (must stay excluded).
6. Keep §5's guardrails and §0's falsified ledger open the whole time — several adjacent ideas are
   already dead.

**Reproduce this document's key evidence:**
```bash
cd <repo>
# feeder wiring (should print 0 for all three orphans, >0 for coiled):
for m in subsector_confluence bottom_radar sector_bottom coiled; do \
  echo "$m: $(grep -ciE $m scripts/build_stock_library.py)"; done
# the trailing tailwind:
sed -n '585,608p' scripts/build_stock_library.py
# validation state:
cat site/factordata/us_board_track.json
python3 -c "import json;d=json.load(open('data/subsector_rotation/track_record.json'));print(d['verdict'],d['proven'],'n_matured=',{h:v['n_matured'] for h,v in d['horizons'].items()})"
```

---

## 8. Cross-reference index (so Fable sees the whole map, not just this slice)

| Prior doc | Covers | This doc's relationship |
|---|---|---|
| `US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` | Board-internal ranking/scoring honesty (Brain A) | Accepted priors; this adds the Brain-B/feeder axis |
| `BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md` | Single-name stale-cross re-admission | Cluster D is the *portfolio/sector-clock* generalization |
| `signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` | COILED, the measurement constitution, falsified ledger | The grading objective (§6 N4) + guardrails (§5) come from here |
| `ANTICIPATION_ENGINE_DESIGN.md` | Timing = drawdown lever not return alpha | The honesty contract this doc argues is *over-generalized* (A2) |
| `SECTOR_CONFLUENCE.md` / `SECTOR_BOTTOM_RADAR.md` | Validated sector confluence + bottom radar | The orphaned engines (Cluster C) |
| `ENGINE_PROBLEM_AUDIT.md` / `CYCLE_INTELLIGENCE_*` | Broader engine + cycle audits | Adjacent; feeder health (E3) overlaps their data-quality findings |

*End of input for Fable. The problem is not that the math is missing — it is built and largely
validated. The problem is that it is wired to the wrong pages, calibrated in the wrong direction, and
graded against the wrong objective. Fable's task: decide the objective, then reconnect the brain the
product is actually made of.*
