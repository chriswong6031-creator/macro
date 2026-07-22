# POSTMORTEM 2026-07-22 — Bullish crossovers vs. the capex bind (Mag-7 dispersion week)

Adjudicated tape postmortem + integration charter. Fourth entry in the rotation-genre lesson
series (06-25 semis→Mag7 postmortem in #2286 / Rotation Command; `POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md`;
`POSTMORTEM_20260716_DEFENSIVE_ROTATION_MISS_BY_FABLE.md`). Written the evening of the Alphabet
Q2 print, before the next session opens — the forward scenario in §1 is falsifiable within days
and is *meant* to be graded (see §5).

Epistemics: everything chartered here is display-tier context or a pre-registered study.
Nothing in this document escalates, ranks, sizes, or gates. Promotion claims go through the
gauntlet as always.

---

## 1. The tape (facts, as of 2026-07-22 after hours)

- **Index regime turned hostile ~4 weekly bars ago, and our own ledger dated it.**
  `data/index_momentum/events.parquet` (W-FRI grid): **MAG7 carrier and SOXX weekly RSI-MACD
  bearish crosses on 2026-06-26** (SOXX from 95th-pctile depth — crossed down from an extended
  state; MAG7 from 26th-pctile depth — weak structure), **QQQ weekly bearish cross 2026-07-03**.
  Since then: semis/memory sold off hard, then violent two-way chop; every day a see-saw
  rotation among defensives ↔ Mag-7 hyperscalers ↔ AI hardware.
- **The entry layer leaned bullish into it.** 2D/3D MACD-RSI bullish crossovers (the
  `engine/confluence_tiers.py` T1/T2 constructions) fired across the Mag-7 cohort. We believed
  the hyperscalers were about to run, and NVDA with them.
- **Resolution so far:** AAPL was the only clean outperformer. NVDA is constructive but
  violently choppy — the *path*, not necessarily the terminal direction, is what failed.
  GOOGL/AMZN/META/MSFT were weak and chopped hard.
- **2026-07-22 AH:** Alphabet beat on every reported line, **raised FY26 capex guidance from
  $180–190B to $195–205B**, and traded **−4% after hours**. AMZN/META/MSFT down in sympathy.
  Hardware not up big AH — the capex raise that is nominally *their* revenue produced no loud
  relief.

## 2. What the system already knew (the painful part)

This was **not a missing-signal failure**. Two artifacts, both live before the fires, contained
the answer:

1. **`engine/demand_capex.py:5`** — the hyperscaler capex spender pool is
   **MSFT / GOOGL / AMZN / META / ORCL**. AAPL and NVDA are structurally *excluded* (refuge and
   beneficiary respectively). The realized Mag-7 dispersion this week followed that taxonomy
   exactly: the only two names whose crossovers worked are the only two not in the spender
   pool. The sign convention was already written down (line 26: Cooper–Gulen–Schill — spender
   capex predicts **negative** spender returns; the beneficiary chain is the bullish leg).
2. **`research/MAG7_Q2_2026_EARNINGS_CAPEX_DILEMMA_AND_TAPE_SCENARIOS.md`** (2026-07-18,
   PR #2880) — predicted a split season; named **"Apple remains the cash-conversion refuge"**;
   flagged the reaction-function question ("whether investors will still pay peak multiples
   when excellent news no longer produces positive price response" — the TSMC
   record-print-into-falling-semis episode); and anticipated that "even bullish capex
   commentary may produce only a relief rally in hardware." Alphabet's actual print (raise
   *above* the reaffirm range) was one step more capex-forward than the memo's base case — the
   punished branch of the documented dilemma: cut capex and admit overspend, or raise and be
   punished for unproven ROI. They raised.

Neither artifact was consulted by the entry layer. A T1/T2 fire on GOOGL carried no annotation
that the name sits in an actively-documented structural bind, and no annotation that its own
cohort carrier had crossed down on the weekly three weeks prior. The organs were right
individually and mute collectively — the same verdict as 07-14 ("4–5 conflicting opinions")
and 07-16. **Three wiring postmortems in 21 days makes this the system's dominant failure
mode: synthesis, not signal coverage.**

## 3. Lessons → engine homes

Each lesson: what we learned, where it lives, epistemic tier, and the standing rulings that
constrain the build.

### L1 — A crossover fired against a hostile weekly index regime is a different signal. (STUDY)

The same T2 fire meant different things on AAPL (out of the spender pool, tape-refuge) and
GOOGL (spender, three weeks after its cohort's weekly bear cross). Today we weight tier fires
identically regardless of index-regime context (`confluence_tiers.py` WEIGHTS, line 50).

- **Hypothesis to measure, not assume:** tier-fire quality (path *and* return) degrades inside
  an event-anchored window after the relevant index carrier's W-FRI bearish cross.
- **Design constraints (binding priors):**
  - **Event-anchored, not standing-state.** The IHM masterplan printed the null: naive joint
    *state* conditioning does not predict (`INDEX_HYBRID_MOMENTUM_MASTERPLAN_BY_FABLE.md` —
    "valid only at turn events from depth"). Condition on "within N weeks after cross_dn," not
    on "MACD below signal."
  - **Gating can hurt.** The A-share subsector gate is FALSIFIED — gating hurt vs. flat
    (`DO_NOT_REBUILD.md` §2). The study's null branch (regime conditioning adds nothing) must
    be a printable, acceptable outcome.
  - **Path metrics are first-class.** This week's failure is chop, not direction — NVDA may
    yet resolve up. Score MFE/MAE, whipsaw count, stop-out rate (the tier table already keys
    on held-out stop-out), not just fwd return.
  - **Promotion, if earned, is de-escalation-only** via the `signal_governor.py` idiom
    (trust ≤ 1.0, HAC gate, pre-registered constants) — a hostile-regime fire gets *discounted*,
    never does a friendly-regime fire get boosted.
  - **This is domain-program work, not Neural Web kernel conditioning** (kernel conditioning
    before NW clocks arm is FORBIDDEN, `DO_NOT_REBUILD.md` §1; rotation×cycle entry-confluence
    is DON'T-TEST — this study conditions on *index* regime events, not cycle position; keep it
    that way).
- **Data already exists:** `data/index_momentum/events.parquet` (W-FRI crosses per carrier,
  2015→) × the tier scorecard history. No new collection needed.
- **Display-tier now (no study needed):** showing the *fact* next to a fire — "cohort weekly
  trend crossed down 2026-06-26" — is context re-expression of an existing ledger and ships
  freely. No edge claim; just stop hiding the regime from the reader of the fire.

### L2 — A cohort with a structural bind must never be read as a monolith. (BUILD — display-tier)

Every Mag-7 member had the same bullish crossover; capex role, not the technical setup, was the
differentiator. We already own the taxonomy — it's just not surfaced where members are read.

- **Build:** a `capex_role` tag on the `mag7_regime.v1` member table
  (`engine/mag7_regime.py`) — `spender` (MSFT/GOOGL/AMZN/META per `demand_capex.py` pool) |
  `beneficiary` (NVDA) | `refuge` (AAPL) | `narrative` (TSLA) — rendered as a plain-word chip
  wherever the member row or its tier fire is displayed (Mag-7 panel, Big Seven board,
  us_stocks tier grids). Plain-word framing per DESIGN_DOCTRINE: "spends the AI capex" /
  "sells into the AI capex" / "cash refuge — outside the bind".
- **Epistemics:** pure re-expression of an existing calibrated taxonomy + a published memo.
  Display-tier, ships freely. No new signal originated.

### L3 — Capex guidance changes are transmission events. (BUILD — display-tier chip)

Tonight's raise is simultaneously spender-bearish (CGS) and supplier-bullish
(`AI_CAPEX_THEMES` in `demand_capex.py:45` already tags memory_storage / ai_semiconductors as
**direct**, semicap_equipment **lagged**, power themes **indirect**). That two-sided read is
the single most useful sentence we could have shown a user tonight, and no surface said it.

- **Build:** a cross-asset context chip per the **oil→XEG C1-R2 pattern**
  (`templates/commodities.html.j2:471`; chip-tier rule in
  `research/COMMODITY_C1R2_OIL_XEG_PREREG.md`): on a hyperscaler FY-capex guidance change,
  surfaces on the Mag-7 panel / semis-memory theme pages render: "GOOGL raised FY capex
  $180–190B → $195–205B · historically a demand tailwind for memory/semicap (direct chain) ·
  a spending headwind for the spender itself · context, not a scored signal."
- **Trigger honesty:** the chip's trigger is the *stated guidance number* (parsed data — data
  collection, not signal origination). `earnings_qual.py` tags (`guidance_raised`/`lowered`)
  are LLM tone tags — usable as a fallback *flag*, never as the number, per the
  LLM-may-only-de-escalate law.
- **Transmission page:** `engine/rate_inflation_transmission.py` is rates/inflation-only by
  design; the AI-capex chain stays in the demand-chain/theme surfaces (don't graft a second
  ontology onto the transmission page without its own adjudication).

### L4 — The reaction function is regime information: when beats get sold, the tape is telling you the multiple is full. (BUILD NOW — forward ledger, time-sensitive)

GOOG: beat everything → −4%. TSMC last week: record everything → semis kept falling. The 07-18
memo *predicted this tell mattered*, and we have no machinery that records it.

- **Gap confirmed:** `surprise_pct` exists per quarter (`collectors/equity_earnings.py:113`),
  price parquets exist, and **nothing joins them** — no gap%, no day-after return vs. surprise
  sign anywhere (`engine/altdata.py:376` earnings clock is deliberately non-directional and
  stays that way).
- **Build:** `earnings_reaction` forward ledger — per event: surprise sign/magnitude, AH/open
  gap %, day-1 and day-5 returns, **pre-event 20d run-up** (the control: sell-the-news at
  highs is the documented benign explanation — a "beat-but-sold" read is only interesting
  net of run-up). Derived display-tier context: per-name `beat_but_sold` flag on stock pages /
  Mag-7 member rows; a rolling "share of beats sold, trailing 20 events" breadth line as tape
  context (risk_state-adjacent, context leg only).
- **Epistemics:** display-tier + accrual. No directional claim until a matured-ledger study
  earns one (PEAD / reaction-function gauntlet later, on accrued PIT data). Historical
  backfill from `surprises_json` + price parquets is possible for the study; the *forward*
  ledger is still the clean PIT spine — start it during a live earnings season, which is now.

### L5 — Name the see-saw. (BUILD — fold into existing surfaces only)

Violent daily leadership rotation among defensives / hyperscalers / hardware is itself a regime
state, and its honest stance — "watch, don't chase" — is exactly what house doctrine wants
surfaces to say *while it's true*. Today nothing at cohort altitude measures it
(`compression_signals.py` chop index is per-name; `dispersion.py` is cross-sectional-name;
`rotation_velocity/corr` are family-level, not this triad).

- **Build:** cohort leadership flip-rate — daily winner among 3–4 cohort carriers we already
  compute (defensives proxy, MAG7 carrier, SOXX, equal-weight tape), trailing-10-session count
  of leadership changes → plain-word context line ("leadership has flipped 7 of the last 10
  sessions — chasing either side has been punished").
- **Hard constraint:** `DO_NOT_REBUILD.md` §1 kills any parallel rotation-schedule surface
  (sector_rotation_schedule.v1 row) — this folds into **existing** homes (risk_state context
  legs / Turn Desk Family-D columns / Mag-7 organ context strip), never a new page.

### L6 — The Neural Web is the organ whose job this was. (NW lane, within A7)

The NW masterplan defines NW as the meta-layer over all signals; NW-A7 bans NW from
originating; NW-U15 fences it to rails/memory/governance/synthesis. This episode is the
canonical synthesis case: an entry-layer fire on a name carrying (a) an active structural
thesis flag and (b) a recent hostile cohort-regime event should surface as **one joined read**
("technical fire × structural headwind — historically these argue; here's each side"), not two
mute organs. Annotation and de-escalation are inside the A7 fence; L2/L3's tags are the
substrate NW joins on. Concretely: the latent-state / synthesis layer should treat
`capex_role`, active-thesis-memo flags, and W-FRI cohort cross events as joinable context keys.

## 4. What this postmortem does NOT conclude

- **Not** "MACD-RSI crossovers are broken." The tier cascade's held-out record stands; one
  cohort-week is an anecdote. L1 is a study charter, not a verdict.
- **Not** "hyperscalers are shorts." CGS is a context sign on spenders, display-tier here;
  no authority claim exists or is proposed without the gauntlet.
- **Not** "regime gates should suppress fires." The falsified A-share gate is the standing
  warning that gates can hurt; the null branch of L1 is acceptable and printable.

## 5. Falsifiers (grade this within days)

- If GOOGL/AMZN/META/MSFT rally through this week and NVDA resolves cleanly up, the tape half
  of L1 weakens materially ("early, not wrong") — the study, not the anecdote, decides.
  The operator's forward read tonight: hyperscalers likely sell off tomorrow; hardware
  uncertain. Grade it.
- If the L4 ledger shows "beat-but-sold" is fully explained by pre-event run-up, the tell is
  demoted to a sell-the-news footnote and the breadth line is dropped.
- If AAPL's outperformance fades while spenders recover, L2's refuge framing was
  narrative-fit, and the capex_role chip keeps its tag but loses the implied ordering.

## 6. Chartered lanes (ranked) and routing

| Lane | What | Tier | Route | When |
|---|---|---|---|---|
| A | `earnings_reaction` forward ledger + beat-but-sold context | display + accrual | Opus `builder` | **Now — season is live** |
| B | `capex_role` tags on mag7_regime member table + tier-fire annotation | display | Opus `builder` | Now |
| C | Regime-conditioned tier-fire scorecard (event-anchored, path metrics, pre-registered) | study → governor-idiom de-escalation only | research/signal_engine | After A/B |
| D | Capex-guidance transmission chip (C1-R2 pattern) | display | `designer` + `builder` | After B (shares tags) |
| E | Cohort see-saw flip-rate, folded into existing surfaces | display | Opus `builder` | With/after C |
| F | NW synthesis join on L2/L3 keys | NW program (A7 fence) | NW lanes | After B/D land the keys |

Kill-respect appendix: rotation×cycle entry-confluence DON'T-TEST; kernel conditioning before
NW clocks arm FORBIDDEN; sector_rotation_schedule.v1 parallel surface DO-NOT-BUILD;
rs-based member-dispersion gates DON'T-TEST; A-share subsector gate FALSIFIED (precedent, not
scope — cited as the null prior for Lane C).

*— Fable, 2026-07-22 (evening of the Alphabet Q2 print)*
