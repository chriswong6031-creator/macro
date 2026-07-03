# China Stock-Picker PIPELINE — problem audit + solution brainstorm (for Fable)

> **Role split (owner directive):** Opus produced this assessment, context, and candidate-direction
> brainstorm. **Fable** does the second-pass reassessment, novel-idea generation, and the actual fix,
> then orchestrates Opus/Sonnet sub-sessions to execute. This document is a *fixed input* — it pins
> the problem and the guardrails. It does **not** prescribe the solution.
> Authored 2026-07-03. Scope: `china_stocks.html`, `sector_central_china.html`, `baskets_china.html`.

---

## 0. Read this first — what this doc is, and is NOT

There is already a comprehensive China audit: **`research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md`**
(2026-07-01, 91 problems, 8 root causes, a tensions layer). **This companion does not re-derive it.**
Everything in that doc (validated reversal edge demoted, US-momentum stack drives selection, no
shared regime, graders never fed back, wide flat boards, upstream data holes) still stands and was
spot-checked as still-live below. Read that doc's **§8 (Tensions)** as a prerequisite — several
"obvious" fixes there are probably wrong for subtle reasons, and those reasons apply here too.

**What THIS doc adds** is the axis the owner's 2026-07-03 request centers, which the prior doc
treats only obliquely: **the FEEDER→PICKER pipeline.** The owner's thesis is a specific architecture:

> *Detect sectors/themes that are heating up **early** (bottomed, washed-out, basing, or just ticking
> up — NOT already-run leaders) → surface individual names inside them that are bottom-basing/perking
> up → gate/time the entry with confluence, including **pre-emptive buying of names about to pass the
> gate** and **re-admitting names that based after passing it.** The sector-rotation and thematic-
> basket engines are FEEDERS and must be (a) genuinely accurate and (b) fast enough to flag emerging
> sectors before they run, so the picker is never fed mid-cycle.*

This doc audits that pipeline end-to-end, in the current code, and asks the three owner questions:
**what engines power it and how are they ineffective; are we misleading users; where is the UX
failing.** It closes with the cross-market port question (US/`baskets.html` → HK/Canada) and a
Fable-facing tensions layer distinct from the prior doc's.

**Method:** direct code read of the three named build paths + their engine deps + the US/HK/CA
siblings; cross-checked against the 2026-07-01 brainstorm and the shipped-since git log. Every claim
is cited to `file:line`. Where I did not fully trace a path, it is flagged **[verify]** — do not treat
those as established (see §9).

---

## 1. The pipeline as BUILT vs as INTENDED (the core finding)

The owner describes a **funnel**: sector/theme detection → in-sector name selection → entry timing.
The code implements **three near-independent surfaces that barely touch**, and the one place they
connect uses a *trailing* signal. Here is the actual wiring, traced:

```
INTENDED:   [sector rotation]  ─┐
            [thematic baskets] ─┼─► detect EARLY-heating/bottomed sectors ─► pick basing names ─► time entry
            [confluence gate]  ─┘

BUILT:      sector_central_china  ──✗ NOT IMPORTED by the picker ──►  (siloed)
            baskets_china         ──► _basket_tailwind_map(): 20d REL return ──► one "upside" axis
            coiled (cohort washout) ──► ranking bonus (the ONLY real "sector-bottoming" feeder)
            confluence cascade    ──► inclusion gate + tier rank (US-fit)
```

**Traced facts:**

1. **The sector-rotation engine is not a feeder at all.** `scripts/build_china_library.py` (the
   `china_stocks.html` builder) imports `engine.cycles` and `engine.coiled` and nothing from
   `china_sector_central` / `china_sector_cycles` / `china_sector_pathway` (grep of the import block
   + full-file scan, `build_china_library.py:39,43`). The per-sector regime gate, washout↔euphoria
   signature, and forward tilt that `sector_central_china.html` computes
   (`engine/china_sector_central.py:72-214`) **reach the name board through nothing.** A sector can
   read "BOTTOM WATCH / constructive" on the sector page while its members carry no corresponding
   boost on the stock page — and vice versa. This is the prior doc's R3/`cycle-state-is-an-island`,
   but stated as the owner frames it: *the feeder the owner most wants (early sector detection) is
   physically disconnected from the picker.*

2. **The one theme feeder that IS wired is a trailing-momentum signal.** `_basket_tailwind_map()`
   (`build_china_library.py:463-487`) scores each name by its strongest basket's **20-day relative
   return vs CSI 300** (`:474-477`) and feeds that into the Conviction "upside/theme tailwind" axis
   (`:805`). A 20d relative-return tailwind **rewards themes that have already run** — precisely the
   "mid-cycle / already-ran" feed the owner wants to exclude. There is no early/emerging-detection
   term (acceleration-off-a-base, breadth-thrust, dispersion-compression, first-cross) anywhere in
   the tailwind. `engine/baskets_china.py` itself is a thin shell (`compute_china_baskets` +
   membership/closes helpers, `:40-92`) — the "which theme is heating" intelligence is just perf
   ranking, not a rotation-phase model.

3. **The only genuine "sector-bottoming" detector wired into the picker is COILED.**
   `engine.coiled` (cohort-washout state machine) contributes a cross-sectional ranking bonus
   (`build_china_library.py:895-901,1192-1221`), wave-3-validated on CN (clean-liftoff +7.33pp,
   stop-out −6.21pp better, n=10,784 — `:43`). This is real and is the closest thing to the owner's
   "many stocks in the sector washed out and basing" idea. **But** it ships as a *bonus + display
   chip only* (never a gate — it recalls only a slice of durable bottoms), and its wave-4 extension
   **COILED-FIRE is display-only, no rank change** (`:1202-1210`, chip only). So the mechanism that
   best matches the owner's intent is deliberately kept weak, and the sector-rotation page's richer
   read is not feeding it.

**Consequence for the owner's stated use:** the picker is *not* "fed by early sector rotation." It is
fed by (a) a trailing 20d theme-return nudge that leans mid-cycle, (b) a deliberately-weak cohort-
washout bonus, and (c) a US-fit confluence gate. The sector-rotation engine's actual output is
decorative relative to the board. **This is the mechanical reason the picks feel mid-cycle and
disconnected from the "heating sector" narrative the pages tell.**

---

## 2. The timing problem — front-running vs basing-after-confluence (the owner's two-sided ask)

The owner wants two things that pull in opposite directions: **buy names *about to* pass the gate**
(front-run) AND **re-admit names that passed the gate a while ago and then based** (don't miss the
delayed movers). The repo has machinery for both — but it is unevenly deployed on China.

**Front-running ("about to pass the gate") — PARTIALLY built, under-weighted.**
The confluence cascade already emits *projected* tiers: **T3** ("2D MACD projected within ~1-2 days
& 3D StochRSI already crossed — the early prediction") and **T4** ("earliest; anti-falling-knife;
above-200MA") — `engine/confluence_tiers.py:11-12`. These are exactly "about to cross." They are
close-only so they work on the A-share tape, and the CN board consumes the cascade via
`signal_gate.blend_sorted` (`build_china_library.py:546-549`). **So pre-emptive admission exists** —
but T3/T4 carry the *lowest* cascade weights (0.6/0.4 vs T1=1.0, `confluence_tiers.py:48`), so an
about-to-cross name is structurally ranked *below* a just-crossed one. The owner's "front-run while
staying accurate" is therefore a **weighting/validation** question (are projected tiers actually good
on CN?), not a "build it" question — and no CN forward grade on T3/T4 precision exists to answer it.

**Basing-after-confluence ("entry passed the gate many ticks ago") — the fix EXISTS but is US-ONLY.**
This is the owner's most concrete complaint ("a sector becomes a de-facto leader but the entry passed
the gate many ticks ago"). It has a dedicated design doc
(`research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md`) and a **shipped engine**:
`engine/hold.py` (`hold_state`, `days_basing`, `invalidation`-after-anchor, `:83-204`), landed
2026-07-02 as W6-C (#1032). **It is wired into the US board only** —
`build_stock_library.py:1202-1478` computes and attaches `hold`, and `grade_us_board.py:201,532`
even *grades* by `hold_state`. **`build_china_library.py` imports nothing from `engine.hold`**
(grep: zero references). So the just-shipped basing tracker — the direct answer to the owner's
timing complaint — **has not reached the China board.** The freshness gate on CN (`FRESH_TICKS=2`)
therefore still drops a name ~6 days after it crosses, with no post-cross "based & coiled" re-admit,
exactly the failure the US fix was built to cure.

**Net:** the owner's timing problem is not unsolved — it is **unported and unweighted on China.**
Front-running exists but is deprioritized and ungraded; basing-re-admission exists but is US-only.
The gap is deployment + CN validation, not invention. (Caveat, from the basing doc §4: the US
re-admit is itself still bonus/chip-shape pending forward grades, and H2 "aged quiet base" was
FALSIFIED — so porting must carry the same guardrails, not just copy the code.)

---

## 3. Are the feeders ACCURATE enough to feed the picker? (feeder-integrity)

The owner explicitly worries the feeders may "provide genuinely inaccurate data that plagues our
results." The prior doc's R7/§8 already catalogs this; the pipeline-specific point is that **these
holes are upstream of the picker, so they poison the *feed*, not just the feeder page:**

- **Trailing tailwind on a total-return plane.** The basket 20d-rel tailwind (§1.2) is computed from
  the basket engine's perf, which runs on yfinance `auto_adjust=True` closes (dividend-adjusted /
  total-return — see prior doc R7 `yfinance-total-return-close`). For a *relative-return* theme
  ranking this is a second-order bias, but it compounds the "already-ran" problem: adjusted closes
  drift up vs raw.
- **THS truncation fabricates membership churn** (`ths-truncation-fabricates-removals`, prior doc;
  memory `ths-truncated-scrape-fabricates-removals`) — a truncated concept scrape makes the basket
  feeder think names *left* a hot theme, silently changing what the picker sees as "in a heating
  theme."
- **Survivorship in the name universe** (`china_search` top-N snapshot) is *maximally* destructive to
  a reversal/bottoming feed specifically (prior doc §8): the deepest decliners the feed wants are the
  names most likely to be later ST'd/delisted and pruned — so both the backtest and the live feed are
  biased toward the survivors, inflating apparent hit-rate.
- **No staleness gate on the sector-rotation inputs.** `china_sector_central` regime anchor reads
  `china_masterminds.regime_state` + `china_regime/latest.json` (`china_sector_central.py:72-95`);
  the akshare Shenwan cycle plane is serial with `stale_after_days=6` (prior doc coherence map). A
  frozen upstream renders as a fresh sector call — and if that call *were* wired into the picker
  (which the owner wants), a stale sector read would silently mis-route every name in it.

**Pipeline implication:** *before* wiring the sector engine into the picker (which §1 argues for), the
feed must carry a **freshness + coverage stamp** that the picker can down-weight on. Wiring a stale or
truncated feeder into the board is worse than leaving it siloed. This is a prerequisite, not a nicety.

---

## 4. The selection & display core — still misaligned with the stated use

Spot-checked as **still live** (2026-07-03), these are the prior doc's findings, re-confirmed because
they directly defeat the owner's "surface great names at great entries" goal:

- **Displayed number ≠ the edge.** The big 0–100 the user reads is `china_name_score.potential_score`
  (a trigger-gated washout/readiness number), and it **overwrites** `conviction.score`; the real
  within-board rank is demoted to a hidden `rank_pctile` (`build_china_library.py:997-1041`). The
  code comment now claims the potential "agrees" with the verdict because it's cycle-anchored
  (`:1032-1035`) — an improvement over the old "most-fallen ranks highest" — but it is still a
  **timing/readiness** number, not the validated within-sector reversal edge. The owner's "great
  pick" (edge) and "great entry" (timing) are fused into one glyph that shows only timing.
- **Reversal coverage still 16-capped on the surface.** `reversal_watch` is called with the default
  `top_n=16` (no override, `build_china_library.py:341-342`; `china_reversal.py:48,103`
  `head(top_n)`). The "confluence" chip = reversal-watch ∩ low-vol-sleeve is therefore still a 16×16
  intersection (prior doc `confluence-flag-16x16`, "half-fixed"). **[verify]** whether the `rev_z`
  *axis* covers the full board or only the 16 — this determines whether the validated edge even
  reaches most names' scores. This is the single most important thing for Fable to confirm first.
- **Selection gate is the US-fit cascade, not the validated CN reversal.** Inclusion is the confluence
  cascade (validated on US names); the one validated A-share edge (within-sector 3m reversal,
  Sharpe 0.58) enters as a tiebreaker. Prior doc R2 — unchanged. (But heed prior doc §8.1: making
  reversal the *inclusion* gate may surface falling knives and feel *more* broken; this is genuinely
  unresolved.)

---

## 5. Are we misleading users? (concrete, grounded)

Yes, in specific, fixable ways. Ordered by how directly they mislead an acting user:

1. **The page copy misdescribes its own screen.** `site/china_stocks.html` copy simultaneously
   references "BOTTOMING-ALIGNMENT" (`:215,1191`), "confluence"/"cascade" (`:935,1193`),
   "mean-reversion" (`:1176`), "reversal" (`:12-22,1202`) and "momentum" (`:1008,1107`). The engine
   runs the confluence cascade + reversal tiebreak; the header/footer still narrate a bottoming-
   alignment/mean-reversion screen. A user cannot tell what the board actually selects on. (Prior doc
   `template-describes-dead-screen` — still live. Caveat prior doc §8.5: *fixing the copy toward the
   cascade may cement a regression* — the described screen may be closer to what a contrarian board
   needs. So the fix is "make copy match a *decided* screen," not "match the current code.")
2. **A timing number wearing an "edge" costume.** The 0–100 headline reads as conviction/quality; it
   is buy-readiness with `edge_mult=1` (zero cross-sectional edge). Users size on a number with no
   validated forward meaning (§4).
3. **Cross-page contradictions presented as agreement.** `china_conviction.py` unifies the 0–100
   *display band* across pages (prior doc coherence map) so two pages show matching "High" badges
   computed from **contradictory** underlying reads — actively teaching the user the pages corroborate
   when they don't. And within one page, `sector_central_china` renders the desk 8-state ladder
   ("DECLINE"/"RALLY ON") *beside* the 5-phase wheel ("Recovery") — a user sees "prime entry" and
   "DECLINE" for the same sector at once.
4. **No published hit-rate.** Every surface has a self-grader; none renders a track record
   (prior doc R1). The honest answer to "does this board work?" is currently unavailable to the user,
   while the board still says "buy." (Prior doc §8.7: an honestly-computed, fill-adjusted, benchmark-
   relative hit-rate on a daily single-name contrarian board may be genuinely *low* — surfacing it and
   keeping a loud "BUY now" board are in tension.)

---

## 6. UX / UI failures (beyond the honesty issues)

- **Wide flat boards, no confidence floor, no top-few cut.** `china_stocks` up to ~110 identically-
  styled buys (6/sector cap); `sector_central` all 31 Shenwan + ~22 baskets with only ~4 carrying a
  validated forward leg; `baskets_china_ths` a 237-basket wall with no reco desk (prior doc R8). The
  two real ideas are invisible among the 108 → **realized** user hit-rate collapses even if the
  *true* hit-rate is fine. (Prior doc §8.2: shrinking to ~5 names may destroy the breadth that IS the
  edge — so this is a framing problem ["this is a basket, size small"], not simply "show fewer.")
- **Incomparable confidence vocabularies** rendered in similar UI language (mean-confidence % vs
  agree/3 vs strength×reliability) — users read them as comparable across pages when they are not.
- **The feeder narrative and the board don't visibly connect.** Because §1's wiring is absent, a user
  reading "Semiconductors is bottoming" on the sector page cannot click through to the basing semis
  names on the stock page — the sector taxonomies differ (≥4 taxonomies, prior doc R4) so
  "Semiconductors" is literally a different basket per page. The product *tells* a rotation story its
  navigation cannot fulfill.
- **Sector concentration hidden.** The board is often one macro bet in many hats (the US sibling is
  56% two sectors); the CN 6/sector cap operates on labels, not realized covariance. The user believes
  they hold N independent ideas.

---

## 7. Cross-market port map — US / `baskets.html` → CN / HK / Canada

The owner asks what to move from `us_stocks.html` / `baskets.html` to HK/Canada, and what must be
built fresh. Traced current state:

| Capability | US | China | HK | Canada | Port verdict |
|---|---|---|---|---|---|
| Confluence T1–T4 cascade | ✅ native | ✅ wired | ✅ wired (`build_hk_library.py:34`) | ✅ wired (`build_canada_library.py:39`) | **Already ported** (close-only → universal). Validate per market. |
| Basket tailwind feeder | ✅ | ✅ (`:463`) | ✅ (`build_hk_library.py:462`) | ✅ (`build_canada_library.py:117`) | Ported — but all trailing-momentum (§1.2). Fix the *feeder*, not the port. |
| COILED cohort-washout | ✅ | ✅ wave-3 | ❌ **failed its gate** (`:43`) | ❌ not wired | CN-only. HK failed OOS; do **not** force-port. |
| HOLD basing tracker (#1032) | ✅ + graded | ❌ | ❌ | ❌ | **Highest-value port** to CN (§2); HK/CA after. |
| Validated local edge | insider (thin) | within-sector reversal (Sharpe 0.58) | **screen only** | **unvalidated** | HK/CA lack a validated name edge — this is the real gap. |

**The load-bearing caveat (do not skip):** the US system the owner wants to port from **has a
near-zero measured cross-sectional edge by its own deep+PIT harness** — every composite fails the
deflated-Sharpe haircut; only insider survives FDR and it's present on 2/34 live rows
(`research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` §1). So "port the US stack" ports its *pathologies*
(fixed-width fill pressure, timing-sorted board, score-overwrite) along with its *machinery*. The
**machinery is reusable** (confluence tiers, COILED, HOLD, forward ledger, the Edge-vs-Timing split
the US doc proposes); the **rank/gate/display architecture is not** — it's what both audits flag as
broken. **Port the primitives, not the product.**

**Market-specific weighting (why one config won't transfer):**
- **A-shares (CN):** short-term REVERSAL dominant, momentum FAILS, QVIX must be *inverted* (positive
  return-vol correlation), margin-surge = crowding RISK, limit-up days need special handling
  (`research/CHINA_STOCKS_OVERHAUL.md §2`). Reversal-led weights.
- **HK:** global-factor-driven (~2× A-share beta to global; memory `china-global-factors`); screen
  exists but no validated selection edge — needs its own edge search, not CN's reversal weights.
- **Canada:** explicitly **alpha/momentum-led** ("developed, momentum-…", `build_canada_library.py:9`)
  — the *opposite* of CN. Porting CN reversal weights to Canada would invert the edge. Canada's
  selection is currently unvalidated vs its promise (memory `hk-canada-stocks-audit-for-fable`, #1033).

(The HK/CA Phase-1 audit is already merged — **#1033**; see `research/HK_CA_INTL_OVERHAUL.md` and the
memory pointer. Do not re-audit HK/CA from scratch; this doc's contribution there is the *port map*
above and the caveat that the source system's edge is ~0.)

---

## 8. Candidate solution DIRECTIONS (seeds for Fable — refute / merge / replace)

Each carries a mechanism story and a validation hook so none can be graded the wrong way. These are
raw material, not a spec. The prior doc's §4–7 directions still apply; these are the **pipeline-
specific** additions the owner's framing surfaces.

**D1 — Make the sector-rotation engine an actual feeder (close the §1 disconnect).**
Emit ONE per-sector state artifact from `china_sector_central` (early/bottoming/heating/topping +
freshness stamp + validated-forward-leg flag) and read it in `build_china_library` as a **rank
modifier + gate context**, so a name in a bottoming/early-heating sector is boosted and a name in a
topping sector is demoted. Mechanism: supplies the "sector is turning" confirmation the base itself
can't. **Guardrail (prior doc §8.3):** apply at the *sleeve/ranking* layer, NOT as a per-name inclusion
veto — a shared de-risk gate keys on high-vol/credit-contraction, exactly when the reversal edge is
strongest. Validate: does the sector-state-boosted stratum beat the unboosted on CN forward
clean-liftoff/stop-out, count-fair, survivorship-corrected?

**D2 — Replace the trailing tailwind with an EARLY-rotation feeder (attack the mid-cycle-feed problem
directly).** The owner's exact complaint. Swap/augment the 20d-rel tailwind with a *phase* read:
theme is (i) low on the washout↔euphoria signature AND (ii) breadth turning up (% members reclaiming
a fast MA) AND (iii) dispersion compressing — i.e. "many members washed out and starting to tick up
together," which is the owner's verbal definition. This is a **breadth-thrust / first-turn** feeder,
not a return feeder. Validate: does an early-phase theme tag lead forward theme return, and does
conditioning names on it beat the trailing-return tailwind? (Mind prior doc H4: naive "volume dry-up"
and "quiet base" filters were FALSIFIED — the early-turn feature must be the one that *isn't* already
dead.)

**D3 — Port HOLD to CN and validate T3/T4 precision (the two-sided timing ask, §2).** Wire
`engine.hold.hold_state` into `build_china_library` (mirror `build_stock_library:1202-1478`) so
post-cross basing names are re-admitted with the same extension/invalidation guardrails; and add a CN
forward grade on T3/T4 (about-to-cross) precision so front-running can be weighted on evidence, not
the current fixed 0.6/0.4. Ship as bonus/chip + forward ledger first (repo discipline). **Guardrail:**
carry the basing doc's falsified H2 (aged quiet base) as a held-out regression — post-cross basing ≠
pre-cross calm base, and Fable must prove the distinction on CN, not assume it.

**D4 — A real cross-surface fusion → one "High-conviction China" card (prior doc §5, re-scoped to the
pipeline).** A name qualifies only when the *feeder chain* agrees: validated-edge slice (top-quartile
rev_z + washout-reclaim) AND its sector reads early/bottoming on the (now-wired, D1) sector state AND
a leading orthogonal confirmer fires (discovery LHB/southbound/breadth) AND regime is permissive-or-
flagged. Attach the honest board_track hit-rate. **Guardrail (prior doc §8):** decide between
AND-intersection (collapses recall), empirical-Bayes shrinkage (degrades to prior — likely better for
tiny effective-N), and small-basket framing — do NOT default to naive AND-gating.

**D5 — Feeder freshness/coverage stamp as a precondition (§3).** Before D1/D2 wire any feeder into the
board, route drip/sector inputs through a staleness gate and emit a coverage fraction; the picker
down-weights (never silently trusts) a stale/truncated feed. De-biasing, not alpha — but prerequisite
to trusting anything the wired feeders say.

---

## 9. Verification appendix — what I ran, and what I did NOT

**Verified by direct read (this session, 2026-07-03, worktree `lucid-knuth-523979`):**
- `build_china_library.py`: imports (`:39,43`); basket tailwind = 20d-rel (`:463-487`); COILED
  wiring + COILED-FIRE display-only (`:886,895-903,1192-1266`); potential_score overwrites displayed
  score, rank_pctile hidden (`:997-1041`); reversal_watch called default `top_n=16` (`:341-342`);
  no `engine.hold` / `china_sector_central` import (full-file grep).
- `engine/china_sector_central.py:72-214` — global regime `gate_factor`, forward tilt on ~4 GS
  sectors only, momentum = confirmer with no forward alpha.
- `engine/confluence_tiers.py:11-12,48` — T3/T4 projected ("about to cross"), weights 1.0/0.8/0.6/0.4.
- `engine/hold.py:83-204` — hold_state/days_basing/invalidation; `build_stock_library.py:1202-1478`
  + `grade_us_board.py:201,532` — HOLD wired & graded **US only**.
- `build_hk_library.py:34,462` / `build_canada_library.py:9,39,117` — HK/CA wire cascade + tailwind,
  NOT coiled/hold; Canada alpha/momentum-led.
- `site/china_stocks.html` copy tokens (`:12-22,215,935,1008,1107,1176,1191-1202`) — muddled screen
  description.
- `engine/baskets_china.py:40-92` — thin engine (perf ranking, no rotation-phase model).

**NOT verified — Fable should confirm before acting:**
- **[verify] Does `rev_z` (the validated edge axis) cover the full board or only the 16 watch names?**
  I confirmed the *watch/confluence surface* is 16-capped; I did not trace whether the conviction
  *selection axis* reads a full-universe rev_z. This gates §4 and is the highest-priority check.
- **[verify]** Whether the W1 leakage-tax harness (`db8fae90ef`) covers the live china_stocks feature
  path at the as-of edge (prior doc §8, Q10). A leaky board explains good in-sample / bad live
  independent of every design issue here.
- **[verify]** Exact location where basket `perf.20d.rel` is computed (build vs engine) and whether it
  runs on raw or adjusted closes.
- I did **not** re-run the prior doc's 91-item inventory; I spot-checked the load-bearing ones as
  still-live and otherwise defer to `CHINA_ENGINE_PROBLEM_BRAINSTORM.md`.

---

## 10. Handoff to Fable — the hardest open questions (distinct from the prior doc's)

1. **Should the sector-rotation engine feed the picker at all, or does wiring it import one more
   correlated, laggy leg?** The owner's intuition says yes (early sectors → in-sector names). But the
   sector engine is monthly-Shenwan-lagged (prior doc R5) and only 4/31 sectors have a validated
   forward leg. Is a *fast, breadth-based* early-rotation feeder (D2) a better feeder than the
   existing slow sector-cycle engine — i.e. build a new fast feeder rather than wire the slow one?
2. **What is the honest "front-run" ceiling on A-shares given close-only data?** T3/T4 project a cross
   1-2 days out from close data alone. With no intraday and dead northbound, is there any orthogonal
   fast demand proxy (ETF create/redeem, margin-balance velocity, turnover-shape) that legitimately
   advances the entry without inverting the reversal edge? Or is close-only front-running intrinsically
   capped at ~1-2 days?
3. **Is "heating sector, basing name" one setup or two theses that fight?** "Sector heating up"
   (momentum/leadership) and "name bottom-basing" (mean-reversion) are opposite return processes. The
   owner wants their intersection. Does that intersection have measurable forward edge on CN, or does
   requiring both just shrink recall to noise? (This is the pipeline version of prior doc §8.1.)
4. **Port order:** HOLD-to-CN (deployment, low risk, high owner-value) vs early-rotation feeder (D2,
   research-heavy, attacks the root "mid-cycle feed") vs sector-state wiring (D1, coherence). Which
   first — the cheap deployment that answers the loudest complaint, or the research bet that fixes the
   architecture? My lean: **D3 (HOLD port + T3/T4 grade) first** — it's the owner's most concrete
   complaint, the fix already exists and is graded on US, and it de-risks the harder D1/D2 by proving
   the CN forward-ledger plumbing end-to-end. But that is a sequencing call for Fable.
5. **HK/Canada:** given neither has a validated selection edge and the source (US) edge is ~0, is the
   honest HK/CA product a **regime/sector-timing overlay on a passive basket** rather than a name
   picker at all? Porting a name-picker whose edge is unproven in its home market to two markets where
   it's also unproven may manufacture three false-confidence boards instead of one.
