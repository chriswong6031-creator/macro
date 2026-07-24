# Postmortem 2026-07-23 — the forced Mag-7 call, and the Ignition Radar that ranked a dead tape

Status: ADJUDICATED (Fable, 2026-07-23). Operator-declared failure, operator's own words:
"It was a false breakout in Mag 7 that we forced onto the board … this was a greedy call to
want to get in mag 7 from the operator (me)."

Companion rulings: `DO_NOT_REBUILD.md` §2 (forced-call construction KILLED) and §4 (Ignition
Radar surfaces SUSPENDED → background-only). Lessons distilled into `research/lessons/`
(L-20260723-1, L-20260723-2). Program history: `MAG7_COMMAND_MASTERPLAN_BY_FABLE.md`.

---

## §0. Verdict in one paragraph

On 2026-07-11 the operator ordered the site to reflect Mag-7 leadership ("MAG 7 is on the
run … yet our us_stocks.html and baskets.html dashboard does not reflect any of this") at a
moment when the engines' own reads were bearish-to-skeptical: the action board had mag7
**deteriorating → avoid**, the Ignition Radar read **⚪ OFF · K=0/8**, and the masterplan
itself noted MAGS was "~8% below its 52-week high: the run is a **recovery inside a larger
consolidation** — which is exactly why every trend-anchored engine read it as a bounce."
The operator's evidence was a multi-name 3-day bullish-crossover confluence — a
lower-timeframe long signal taken against weekly / bi-weekly / monthly topping structure on
the Nasdaq. Twelve days later the breakout resolved as false: 2026-07-23 printed the worst
one-day Mag-7 basket decline in roughly five years (per Goldman Sachs), TSLA −15% and GOOGL
−7% intraday. The engines were right. The override was the error. **The failure was not a
model failure — every layer of skepticism the system already had was manually bypassed.**

## §1. Timeline of record

- **06-26 → 07-10** — MAGS +~9% in a narrowing tape; memory/HBM crashes while the generals
  run (MU −16%, SNDK −17%). Trend-anchored engines classify the move as a bounce inside
  consolidation.
- **07-11** — Operator initiates the Mag 7 Command program over the engines' reads
  (masterplan §0 records both sides verbatim). The board lands on us_stocks.
- **07-14 / 07-16** — Two rotation-miss postmortems land in the same fortnight
  (`POSTMORTEM_20260714_ROTATION_MISS`, `POSTMORTEM_20260716_DEFENSIVE_ROTATION_MISS`) —
  the desk is already documenting leadership-read fragility.
- **07-19** — Board rebuilt as "The Big Seven" price ledger (MLC-W1, #3026): raw moves +
  count-derived stance only. An honest de-escalation of the display — but the surface
  itself, born of the forced call, stays pinned to the page.
- **07-22** — `POSTMORTEM_20260722_CROSSOVERS_VS_CAPEX_BIND` lands: Mag-7 crossover signals
  shown to be wiring-not-signal (only the non-spenders worked; GOOG beat-but-sold). The
  warning about exactly this signal family arrives **one day before** the crash.
- **07-23** — False breakout resolves. Worst 1-day Mag-7 basket drop in ~5y (GS); TSLA
  −15%, GOOGL −7%. The page is still showing "3 of 7 up this week" (stale prices to the
  prior close) and the Ignition Radar strip says "Warming up".

## §2. The companion failure — Ignition Radar ranked a dead tape

On the same 07-23 page the Ignition Radar strip read **"Warming up"** with **1 of 8** broad
signals lit, on the strength of a narrow-theme streak: **#1 XLE ↗ (day 8)** — an
event-driven war bid (Iran), not risk appetite; **#2 Crypto & Digital Assets**; **#3 AI
Semiconductors ↗** — a falling knife mid-crash, structurally indistinguishable (to the
checklist) from a dead-cat bounce. Three separate defects compounded:

1. **Surfaced ahead of its own gate.** The card's self-audit line literally said "accruing —
   display-only until ≥30 grades + operator ruling." That gate was never met; the surface
   shipped anyway. A pre-registered display gate that does not bind is decoration.
2. **No event-sector exclusion.** A single-sector geopolitical bid (XLE on a war headline)
   satisfied the "narrow persistence" honesty rule (M7C-R7) and propagated a "Warming" badge
   to the whole strip while 7 of 8 broad signals were dark.
3. **Always-rank boards manufacture actionability.** "Hottest themes #1/#2/#3" renders even
   when nothing is hot. Ranking by checklist-fraction is honest at Tier-2, but a glance-tier
   reader sees a podium — a podium implies a race is on. In a dead tape the honest glance
   answer is a null: *nothing is igniting*.

Note the symmetry with §1: on 07-11 the same narrow channel scored "Magnificent Seven 0.70,
igniting" and was cited as supporting evidence for the forced call. The channel has now
been on the wrong side of both bookends of this incident.

## §3. Failure-mode taxonomy (the truths to keep)

- **FM-1 · Operator override of the gauntlet.** The gauntlet exists precisely for the
  moment when conviction is highest. "Display-tier ships freely; promotion to authority
  needs the gauntlet" applies to the operator's ideas exactly as it applies to an engine's.
  An "alert" pinned to a page IS authority-tier — it tells the reader to act.
- **FM-2 · Higher-timeframe veto ignored.** A 3-day crossover confluence is a
  lower-timeframe entry read. Weekly/bi-weekly/monthly topping structure on the index it
  lives in is a standing veto — the daily signal wasn't wrong to *exist*, it was wrong to
  be *promoted* while the veto stood.
- **FM-3 · Topic-importance bias ("greed").** Mag-7 felt mandatory to be in *because it is
  Mag-7*. Importance of the topic is not evidence for the trade — the same law the house
  already applies to model routing (topic importance does not justify fable) applies to
  capital: importance ≠ signal.
- **FM-4 · Warnings existed and were fresh.** Three postmortems in the preceding nine days
  (07-14, 07-16, 07-22) flagged leadership-read fragility, the last one about this exact
  signal family on this exact cohort. New evidence against an open call must be re-binding:
  a call that survives only by not re-reading the file is already dead.
- **FM-5 · A surface's own gate must bind (ignition).** See §2.1.
- **FM-6 · Ranked boards need an honest-null state (ignition).** See §2.3.

## §4. Rules derived (with promotion status — house epistemics: n=1 anecdotes seed
candidate rules; process rules that are structurally obvious promote immediately;
market-behavior rules stay candidates until gauntleted)

- **R1 (PROMOTED — process; registry §2 row).** No operator force-adds of directional
  calls to signal surfaces. Operator conviction enters the system as a display-tier watch
  item or a pre-registration — never as a pinned board/alert. Removal of the un-gauntleted
  surface is not optional cleanup; it is the enforcement.
- **R2 (CANDIDATE — market; needs prereg + gauntlet before becoming a gate).**
  Higher-timeframe veto: a leadership/breakout call on cohort X may not surface as
  actionable while the parent index's weekly+monthly structure is in a topping/distribution
  read. To be tested as a formal gate on future leadership constructions, not assumed.
- **R3 (PROMOTED — design; registry §4 re-surface conditions).** Any always-on ranking
  surface must (a) have an honest-null glance state, (b) exclude event-driven single-sector
  moves from "ignition"-class narratives, and (c) never let a narrow streak escalate the
  board's headline state while broad confirmation is dark.
- **R4 (PROMOTED — process).** A surface's own pre-registered display gate binds. If the
  card says "display-only until ≥30 grades + operator ruling," it does not render on a
  public page until both are true. Self-audit lines are contracts, not captions.
- **R5 (CANDIDATE — process).** Standing calls get re-read against new postmortems: when a
  postmortem lands touching an open call's signal family, the call is re-adjudicated within
  one session or it auto-demotes to watch.

## §5. Actions taken (this PR)

- **Removed** the "Big Seven" leadership board from us_stocks (template render + partial +
  `_leadership_board_view()` + tests + CI wiring; baked page hot-patched same-day).
- **Removed** all Ignition Radar user surfaces: us_stocks strip; macro Upturn hero button,
  `dlg-ignition` dialog, "Turning up?" where-next card, risk-dialog cross-ref row, legacy
  anchor mapping (template + baked pages).
- **Removed** the "Mag 7" chip from the landing rotation-lanes seed decor.
- **Kept running (background):** `engine/mag7_regime.py` (context artifact + stockdata
  publish), `engine/ignition_radar.py` + `engine/ignition_audit.py` (nightly snapshot +
  forward self-grading into `data/ignition_radar/`). Accrual continues; only display died.
- **Registry:** §2 forced-call kill row; §4 ignition suspension row with explicit
  re-surface conditions. Compiled blocklists regenerated in the same PR.
- **Lessons ledger chartered:** `research/lessons/` (see its README for the contract).

## §6. What stays open (a kill closes the construction, not the search space)

A *gauntleted* Mag-7 / mega-cap leadership read remains a legitimate research object — the
MLC preregs (S-MLC-1/2) and the mag7_regime organ keep accruing evidence, and nothing here
forbids a future prereg that clears the promotion gate. What is dead is the *delivery
mechanism*: conviction → board, skipping the gauntlet. Likewise the ignition machinery may
earn its way back through its own forward log — the suspension row lists exactly what
"earned" means.
