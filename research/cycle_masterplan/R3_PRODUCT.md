# R3 — Product-honesty & user-value red-team of the cycle masterplan (D1–D5)

**Lens:** a person trading real money reads these pages. Does the MEASURED/STRUCTURAL split clarify or
confuse? Is the curated turn history preserved or vandalized? Are the tripwires honest about what they
catch? Does any pillar add rigor-theater that improves zero trades? Is total scope one-person-realistic,
and what is the 80/20?

Verified against canonical main `/tmp/macro-cycle-fable-main/`: `auto_adjust=True` (yahoo.py:100),
`LADDER_SCORE` static dict + direct read (cycles.py:406, :1038), `_project_next` TODAY-anchored floor
(sector_cycles.py:204-206), `read:None` narrative override (sector_cycles.py:343), 23 cycles in
cycle_data.js, frozen `today:2026.48`, statsmodels absent from requirements, and — a finding the designs
missed — **markets.html AND country_cycles.html are BOTH live nav entries** (`_navlinks.html.j2:266,268`).

---

## HEADLINE VERDICT

The five pillars are individually excellent and mutually coherent — the best-argued solution set I've
reviewed. But as a **product** they carry three honesty risks and one scope risk that will bite a trader:

1. **The tier taxonomy is now FIVE labels** (MEASURED, MEASURED-proxy, MEASURED-M, STRUCTURAL,
   DUAL-with-two-bands) plus per-band PRIOR/MODEL/accruing/FIRED/DATA_MISSING/overdue chips. Fable's T1 was
   a 2-way honesty split; the designs have re-fragmented it into a vocabulary a user cannot hold in their
   head. This risks re-committing the ontology sin (too many co-firing labels) inside the *fix* for it.
2. **The backfilled "day-one track record" is synthetic and will be read as real.** D2's own honesty column
   (`provenance: backfilled`) is correct, but the badge (`MEASURED · turn P/R 0.70 (n=18)`) puts a number
   in front of a user that was produced by re-running today's engine over history — it grades the engine's
   *self-consistency*, not its *forward* skill, and the user cannot tell.
3. **The hazard model + conditional-cells + regime-prior is the largest rigor surface and the one most at
   risk of calibration-theater-rebuilt-fancier** — not because the stats are wrong (they are careful) but
   because a Brier-beats-KM-by-2% cone changes zero trades a median-half-cycle IQR band wouldn't.
4. **Scope is ~35 waves across 5 pillars with hard cross-dependencies.** One person + agents cannot ship
   this coherently in same-day-squash cadence without a spine that goes stale mid-flight.

None of these is fatal to the program. All four are fixable by *subtracting*. The 80/20 is at the end.

---

## ATTACKS (target · issue · severity · fix)

### FATAL

**A1 — D3 §3 + D1 §6 + D2 §3.4: the two-tier split has metastasized into a five-tier taxonomy the user
cannot parse.** T1 asked for MEASURED vs STRUCTURAL — one bright line so a trader knows "this is graded" vs
"this is a frame." The designs deliver: MEASURED, MEASURED-proxy (with a fitness chip), MEASURED-M (monthly),
STRUCTURAL, DUAL (a single card carrying BOTH a measured band and a structural band stacked), each further
annotated with accruing/graded, PRIOR/MODEL (D5), armed/FIRED/DATA_MISSING/manual (D3 §4.5), and overdue
(D1 §4.5). A user looking at the gold card sees a measured oscillator, a 17y age-dial, a MEASURED-proxy-style
basis label, an accruing badge, a hazard PRIOR chip, and a tripwire strip — six independent trust signals on
one card. **This is the ontology disease (five co-firing vocabularies, audit finding #2) re-created one level
up, inside the pillar whose job was to kill it.** *Fix:* collapse the user-facing taxonomy to exactly TWO
words — **MEASURED** and **FRAME** — and demote everything else (proxy, monthly, dual, prior) to a single
hover-only "how this is computed" line. DUAL cards render as a MEASURED card with a thin secular-context
strip that is explicitly *not* a second tier — it is context on a measured card. PRIOR-vs-MODEL is an
engineering distinction that must not reach the card face; both are "projection (typical rhythm)" until the
model earns a *materially different, graded* cone. The bright line the user needs is: *is there a number I
can hold you to, or is this a frame?* Two states. Everything else is methodology-drawer.

### SERIOUS

**A2 — D2 §3.4 + §1: the backfill badge launders self-consistency as forward skill.** D2 correctly stamps
`provenance:backfilled` and shows a provenance split on measurement.html. But the *card badge* — the thing
99% of users see — reads `MEASURED · turn P/R 0.70 (n=18) · cone 78%`. That number is the engine re-run over
its own history with today's parameters; it measures whether the deterministic stamp function is
self-consistent, NOT whether the oscillator predicted anything a trader could have acted on. A backfilled
turn-P/R of 0.70 is nearly guaranteed by construction (the "ground truth" is the *same ZigZag* that produced
the projection, D2 §3.1 — the detector is graded against itself). The user reads "70% of this engine's turn
calls were right" and sizes into it. *Fix:* (a) the card badge must say `BACKTEST n=18` (dual-span) and only
flip to `LIVE n=…` when the *prospective* cohort matures — never a bare number that conflates the two; (b)
turn-P/R ground truth must be an *independent* definition of a turn (e.g. a realized N% move confirmed by
price, or a different-parameter detector), not the same ZigZag whose projection is being graded, or the
precision number is circular; (c) measurement.html must lead with the *live* cohort and gray the backfill
cohort as "self-consistency check, not forward evidence."

**A3 — D5 §1 + §2 + §3: the hazard/conditional/regime-prior stack is the single largest build in the
program and its marginal effect on a real trade is unestablished.** The audit's calibration-theater sin was
"machinery that looks rigorous without binding a decision." D5 is scrupulously honest about *statistics*
(KM skill bar, isotonic, FDR, no-FWER footers) — but honesty about a number is not the same as the number
*changing a trade*. Concretely: the conditional-cell prose (§2 "when {phase} met {quad}, {h}-month return was
{x}% vs base {y}%") ships with a standing footer "no cell clears a family-wise significance bar" — i.e. it is
pre-declared to be non-actionable, yet it is built, graded, shrunk, and rendered on every page. That is the
definition of decorative rigor. The hazard cone (§1) only ships if it beats the age-only KM prior by ≥2% Brier
with CI excluding zero — a bar it may never clear on n≈1,200 pooled events, in which case the whole D5-W1/W2
build ships the median-half-cycle prior D1 already produces. *Fix:* pre-register, BEFORE building D5, the
*decision* each output must move: "the hazard cone replaces the IQR band on a card ONLY if a trader sizing on
the cone would have realized materially better drawdown-adjusted entry than sizing on the IQR band, measured
on walk-forward." If it can't, D5-W1/W2 ship as a research artifact on measurement.html, NOT as a card
element. And **cut the conditional-cell prose from cards entirely** — a pre-declared-insignificant lift map on
a trading card is exactly the froth the audit named. Keep it in the methodology drawer only.

**A4 — D3 §3.3 STRUCTURAL age-dial "year 14.4 of a 15–20y upswing" is precisely the false-precision the
STRUCTURAL tier was invented to avoid.** The design correctly strips the oscillator, pos, signal, and cone
from structural cards — then re-introduces a single-number position claim through the back door: an age-dial
marker at `years_since_last_hand_turn` on a `period.low→period.high` band, rendered as "year 14.4 of 18." For
housing (n≈2 turns) the "central 18y" is one-or-two-observation folklore; placing a precise marker at 14.4
tells the user the cycle is 80% elapsed with a confidence the data cannot support. A user sizing "late-cycle
housing" off "year 14.4 of 18" is trading a hand-typed period constant dressed as a gauge. *Fix:* the
structural card shows the curated turn timeline and the tripwire strip and NOTHING that resolves to a scalar
position. Replace the age-dial with "last major turn: {date} ({N}y ago); prior up-legs ran {list of the 2-3
historical durations}." Show the raw historical leg lengths, never a central-period marker with a needle.
n≈2 supports a list, not a dial.

**A5 — D3 §6 + verified nav: the markets.html→country_cycles fold ignores that BOTH pages are live,
separately-branded nav entries, and the fold degrades a distinct product.** `_navlinks.html.j2:266` is
"Global Market Cycles — Nine national equity markets on one clock"; `:268` is "Country Cycles — Every country
& region ETF on one cycle clock." These are marketed as different products (9 curated flagship markets with
valuation blocks + archetypes vs 31 ETF/bloc breadth). D3 folds markets into a *filter tab* on
country_cycles, but a filter tab inside a 31-item page is a strictly worse home for the 9 hand-curated
flagship narratives than a dedicated page — the curation gets buried. Worse, the redirect stub burns the
"Global Market Cycles" nav slot's identity. *Fix:* either (a) keep markets.html as a distinct curated
*flagship* view but re-point its DATA at the country_cycles engine (fold the engine, keep the page + nav
identity + curated overlay as a first-class page, not a tab) — this preserves the crown-jewel curation's
prominence; or (b) if truly folding, the flagship tab must be the *default landing* tab of country_cycles
with the 9 markets rendered full-curation, and the nav entry renamed, not stubbed to a redirect. Do not bury
9 hand-verified market histories inside a breadth screener.

**A6 — D1 §2.3 crosswalk + D3/D5: the "clocks disagree" amber chip is honest but the resolved STANCE it
emits is a NEW single action label the user will trade, and it is un-graded on day one.** D1's resolve_state
is the right fix for the Peak/SELL-beside-BOTTOM-WATCH pathology. But it *manufactures a 9th vocabulary* — the
stance (BUY/HOLD/TRIM/SELL/COUNTERTREND ONLY/…) — that becomes the single most prominent action word on every
card (D1 §2.2 "the resolved stance is the only action-toned text"). This stance is a hand-authored crosswalk
matrix (D1 §2.3), NOT a graded output — the 5×8→9 mapping is exactly the kind of expert-tuned constant table
the audit called calibration-theater when it appeared as LADDER_SCORE. A user now trades "TRIM" because a
hand-filled matrix cell said so, with the same false authority the old labels had. *Fix:* the stance matrix
must be registered as a bindable calibration artifact from day one (D2 §4 machinery) — each (phase,ladder)→
stance cell carries the backfilled drawdown-adjusted forward stat that justifies it, and the cell's stance is
FIT (or at minimum audited) against that stat, not asserted. Until then, render the stance with an explicit
"rule-based, not yet graded" hover, and never let it carry more visual weight than the graded position.

### MINOR

**A7 — D3 §1.5 MEASURED-proxy (MU for DRAM, CCJ for uranium): a stock is not the cycle, and the fitness gate
grades the wrong thing.** The gate (match_rate≥0.7, median offset≤6mo of hand ASP turns vs MU equity turns)
validates that MU *turned near* the DRAM turns historically — but the user trading the "memory cycle" card is
shown MU's *position* (pos, phase, oscillator), and MU's position is a semiconductor equity's position
(driven by rates, NVDA, market beta), not DRAM contract ASP's position. A card can pass the turn-timing gate
and still show a wildly wrong *current position* (MU stretched on AI-beta while DRAM ASP is mid-cycle). *Fix:*
proxy cards may show turn TIMING (the thing the gate validates) but must NOT show a proxy-derived position
gauge as if it were the cycle's position — either suppress the oscillator on proxy cards (structural-style) or
label the oscillator "MU price position (proxy), not DRAM ASP position." The gate validates timing; don't let
the card imply it validated level.

**A8 — D3 §4 + D5: tripwire honesty is good but the FIRED-latch UX can trap a user on the wrong side.** Latched
FIRED (D3 §4.2: stays fired until a human authors v(N+1)) is correct for anti-gaming, but the UX
(§4.5: "projection band grays out, thesis refuted, sticky") means a card whose falsifier fired on a brief
spike then fully mean-reverted keeps screaming "REFUTED" for weeks until a human re-authors — actively
misleading a trader whose thesis is now fine again. `sustain_bars` mitigates spikes but not the general case.
*Fix:* FIRED must show the *current* state of its legs alongside the latched flag ("fired 2026-08-12; legs
currently: WTI $71 — condition no longer met"). The latch prevents silent un-firing; it must not hide that the
world moved on. A refuted-then-recovered card is a re-authoring PRIORITY signal, not a state to freeze
silently.

**A9 — D2 §1.4 monthly cadence + D5 monthly panel: choosing month-end stamps "so n_eff≈n by construction" is
honest for the statistic but throws away the fast-timing information the ladder exists to provide.** D2 makes
the daily ladder/DC states config-off-by-default in backfill (§1.4) to kill overlap inflation. But the ladder
(TURN SIGNALED, FRESH BUY) is the *only* part of the platform with tradeable daily granularity; grading it
only monthly means the one fast, actionable signal never gets a daily track record. *Fix:* keep the phase
wheel monthly (correct — it's a slow clock) but grade the ladder/timing states at their native daily cadence
with the effective_n deflator D2 already built (§2.2) — the deflator exists precisely so you don't have to
choose. Two cadences, one per clock-speed, is more honest than one cadence that silences the fast clock.

**A10 — D4 §5 FX decomposition per-turn `fx_share` is a genuinely valuable honesty upgrade but adds a THIRD
line to every country card (local-equity cycle + FX leg + peg annotation) — re-fragmenting the "one clock"
promise.** Decomposing "Japan trough" into equity vs yen is exactly right (the audit's cycle_dna complaint).
But rendering local-cycle + FX-leg + fx_share-per-turn on every one of 24 country cards is a lot of surface,
and for the user the actionable question is usually just "is this a real equity turn or a currency artifact?"
*Fix:* default the country card to the local-currency equity cycle (the honest primary) with a single
`fx_share` flag on any turn where currency drove >60% of the USD move (D4 already computes this) — surface the
full FX leg only in the card's drill-down. One clock by default; the FX leg on demand.

---

## CONTRADICTIONS BETWEEN DESIGNS

**C1 — Backfill basis ordering: D2 vs D4 vs D5 disagree on what runs first.** D4 §THESIS: "the substrate fix
must land before D5 backfills any grades and before D3 fits any hazard model — a grade on the wrong basis is
worthless." D2 §1.6/W3: "can run on `tr_v0` first with basis_version stamped, then re-run." D5 §1.10: "v0
panels built on existing TR closes... rebuilt under turn_def_version when close_price lands." So D4 says
basis-first-or-worthless; D2 and D5 both say ship-on-TR-now-rebuild-later. Both cannot be the house position.
This matters for product because a TR-basis backfill badge that later re-dates every turn (when close_price
lands) will *change the graded numbers on cards a user already saw* — the badge silently revises. *Resolve:*
either accept D4's gate (no graded badge ships until close_price basis lands — cleaner for the user, slower)
or accept D2/D5's staging but then the badge MUST carry the basis_version and a "provisional basis" marker so
a user isn't shown a 0.70 that becomes 0.61 next month with no explanation.

**C2 — Turn ground-truth ownership: D1 vs D2.** D1 §3 makes ZigZag THE turn primitive with `confirmed_at`,
and D2 §3.1 grades projected turns against "confirmed ZigZag turns on the full post-hoc series." But if the
projection and the ground-truth are the same detector (A2), precision is circular. D1 doesn't provide an
*independent* turn definition and D2 assumes one exists. *Resolve:* D1 must add a second, independent
turn-truth definition (realized-move confirmation) for grading, distinct from the projection detector.

**C3 — Overdue semantics: D1 §4.5 vs D5 §1.** D1 replaces the receding-horizon projection with an
`overdue:true`+`overdue_frac` state anchored at the last confirmed turn. D5 removes the `max(0.05,…)` floor
and "prior cones expose OVERDUE state." These are the same fix authored twice in two pillars touching the same
function (`_project_next`). If both land independently they will conflict-edit sector_cycles.py:204-215.
*Resolve:* assign the `_project_next` rewrite to exactly one pillar (D1, since it owns the projection
*semantic*); D5 consumes it.

**C4 — "validated" gate scope: D2 §4.3 vs D5.** D2's template-grep test bans the token "validated"/"已验证"
unless backed by an artifact with `validated:true`. D5 ships isotonic-calibrated hazard scorecards and lead-lag
"GO/NO-GO" verdicts. If a D5 lead-lag artifact or hazard model card uses "validated" in prose without D2's
exact artifact schema, D2's grep test fails the build. The pillars must share ONE validated-artifact schema or
D5's honest language trips D2's honesty gate. *Resolve:* D5 registers its scorecards through
`grading_stats.emit_calibration_artifact()` (D2 §4.3) so the schema is shared.

**C5 — DUAL-card tier home: D1 §6 registry (`tier: measured|structural`, one per cycle) vs D3 §1.1 (tier is a
property of a BAND, a cycle can have both).** D1's proxy_registry schema has a single `tier` field per cycle;
D3 needs two tiers per DUAL cycle (gold = measured band + structural band). The schema D1 ships in D1-W6 can't
represent what D3 needs. *Resolve:* D1's registry schema must carry a `bands: [{tier, freq, series,...}]`
list, not a scalar `tier`, or D3-W1 will have to fork the registry schema D1 just declared canonical.

---

## SECOND-ORDER PROBLEMS THE DESIGNS CREATE

**SO1 — The measurement.html hub + per-card badges + methodology drawers add a large NEW surface to keep
current, in a program whose founding complaint was un-maintained surfaces.** measurement.html (D2-W5),
tripwire strips (D3-W4), hazard scorecard drawers (D5), regime-prior banners (D5-W5), FX legs (D4) — each is a
new thing that rots if a build breaks. The cure imports the disease's mechanism (more surface) even as it
fixes the disease's content (now data-driven). *Mitigation to add:* every new surface must degrade to
*absent*, not *stale* — a missing artifact hides the badge/strip entirely rather than showing a frozen one
(the graceful-degrade house pattern). This must be an explicit acceptance gate on D2-W5/D3-W4/D5-W5.

**SO2 — Backfill re-runs on every basis/threshold bump silently revise historical badges → user trust
whiplash.** D2 §1.6 re-runs backfill on D3 basis bumps, D5 threshold bumps, and quarterly calibration
refreshes. Each re-run can change a card's displayed `turn P/R 0.70` to `0.63` with no user-facing changelog.
A trader who screenshotted "70%" last month and sees "63%" today with no explanation loses trust faster than
if the number were never shown. *Mitigation:* badge numbers carry a `computed_on` date and a version; a
material revision surfaces a one-line "recomputed on corrected price basis {date}" note, not a silent swap.

**SO3 — The hazard model's `family="flagship"` shrinkage pools 23 heterogeneous flagship cycles (vol ~2y,
housing ~18y, credit, PGMs) into one family for shrinkage (D3 §2.5, D5 §1.1).** A "flagship" family is not a
statistical family — it's a UI grouping. Shrinking a vol-cycle hazard toward a housing-cycle mean is nonsense.
*Mitigation:* flagships must NOT be a shrinkage family; each flagship either has enough turns to stand alone
(vol, gold, oil do) or is STRUCTURAL (no hazard at all). Drop `family="flagship"` from the shrinkage pool.

**SO4 — D5 §5 novel features (provisional-turn survival classifier, leg-velocity) are scope creep inside the
highest-risk pillar.** They're gated (pass/fail pre-registered), which is disciplined, but they're net-new
research bets bolted onto a pillar that already has the largest build and the weakest decision-linkage (A3).
*Mitigation:* cut D5-W8 from the masterplan entirely; it's a research backlog item, not a masterplan wave.

**SO5 — i18n load explodes.** Every new stance (9), zone word (5), tier chip, tripwire state, divergence note,
fx_share flag, and hazard-prior label needs an en/zh dual-span pair, and zh flips up/down colors. The stance
`tone` field (D1 §2.3) tries to route color through existing tokens, but COUNTERTREND ONLY / HIGH-RISK BOUNCE
have no natural up/down tone — the zh color-flip rule (memory: zh-updown-token-flip) is undefined for them.
*Mitigation:* enumerate the zh color mapping for every non-directional stance explicitly in D1-W1; don't leave
it to render-time inference.

---

## WHAT IS MISSING

**M1 — No user-facing "what changed" / provenance-of-revision story.** Given SO2, the program needs a
first-class "why did this number move" surface (basis change, threshold change, calibration refresh). Absent
it, the honesty upgrade paradoxically *reduces* trust (numbers that silently revise are worse than no
numbers).

**M2 — No design confronts that the curated turn history's VALUE is the causal WHY, and none of the pillars
grade or preserve the WHY — only the turn DATES.** The crown jewels (DRAM ASP turns, uranium spot turns, the
land-cycle chronology) are valuable because of the *causal archetype* attached (D3 §0 says so). All five
pillars preserve the turn *dates* (re-keying) and the prose (as annotation), but nothing measures whether the
causal archetype still holds — the archetype prose gets a TTL badge (D3 §5.2) and staleness, but a stale
archetype is the one thing a user most needs flagged (the "why" is wrong now), and TTL is a timer, not a test.
*Add:* the archetype's *mechanism* should get a machine-checkable proxy where possible (e.g. "datacenter
capex accelerating" → a NVDA/AI-capex tape check), not just an as_of timer.

**M3 — No pillar owns the cross-page consistency a user will immediately notice.** cycle.html's "japan" card,
markets.html/country_cycles' "japan" row, and any China-page Japan reference will now show potentially
different positions (different basis, different kernel freq, different tier). D3 §6 cross-links them but
nothing asserts they *agree* or explains the divergence. A user who clicks japan on two pages and sees pos 79
vs pos 71 loses trust. *Add:* a cross-page reconciliation assertion (same instrument, same basis → same pos
within tolerance) as a build gate, mirroring D1's within-card divergence work but across pages.

**M4 — No minimal "does the oscillator predict anything at all" gate BEFORE building the whole apparatus.**
The audit's single biggest unverified question: "there is no evidence today that any oscillator/phase/
projection has forward power." D2's backfill can answer this in ONE wave (does pos<16 → positive fwd drawdown-
adjusted return, walk-forward, pooled?). If the answer is NO, most of D3/D5's card apparatus is decorating a
signal with no edge. *Add:* a Phase-0 "signal has forward power" gate as the literal first wave of the
program, gating everything downstream. This is the cheapest possible de-risk and it's not called out as a
gate.

---

## IS THE MEASURED/STRUCTURAL SPLIT GOOD FOR A TRADER? (direct answer)

**The concept clarifies; the execution confuses.** A trader absolutely needs to know "is this graded or is
this a frame." That bright line is the single best product idea in the program. But the designs deliver it as
a 5-tier taxonomy with 6 chips per card (A1), a synthetic backtest number dressed as a track record (A2), a
false-precision age-dial on the "honest" structural cards (A4), and a hand-tuned stance the user trades
without grading (A6). Net: a *disciplined* trader gains real honesty; a *typical* trader sees more labels and
trusts a backfill number they shouldn't. Fix by subtracting to two words (MEASURED / FRAME), one action
signal (graded position + graded-or-not projection), and a strict "BACKTEST vs LIVE" badge distinction.

## IS THE CURATED LAYER PRESERVED OR VANDALIZED? (direct answer)

**Preserved in letter, at risk in prominence.** All five pillars go out of their way to keep the turn history
(re-keying, orphan quarantine, never-delete — genuinely good, T6-faithful). The vandalism risk is
*demotion-by-burial*: folding markets.html's 9 curated markets into a filter tab (A5), and reducing the land-
cycle chronology to an age-dial needle (A4). The data survives; the curation's *product prominence* — which
is its actual value — is what gets damaged. Keep the curated flagship views as first-class pages/tabs, not
buried filters, and show curated turns as timelines (lists), not resolved needles.

## TRIPWIRE HONESTY? (direct answer)

**Honest about coverage, with two UX gaps.** D3 §4.4's 10-FULL / 8-PARTIAL / 5-NONE enumeration is
admirably honest — it explicitly refuses to pretend coverage it lacks, and the manual-falsifier-with-TTL state
for the 5 NONEs is the right call. Gaps: the FIRED latch can strand a user on a recovered thesis (A8), and
DATA_MISSING vs ARMED must never silently read as ARMED on dead data (D3 handles this — good). Net: the most
honest part of the whole program.

## RIGOR-THEATER CHECK? (direct answer)

**Two offenders.** (1) D5 §2 conditional-cell prose ships with a pre-declared "clears no significance bar"
footer — building, shrinking, and rendering a lift map you've already declared non-actionable IS the froth the
audit named (A3). Cut from cards. (2) D1's resolved STANCE is a hand-tuned matrix with the same false
authority as the LADDER_SCORE the audit flagged, un-graded on day one (A6). Bind it or hover-caveat it. The
hazard model itself is NOT theater IF the skill gate genuinely blocks shipping a cone that doesn't beat the
prior — but that gate must be enforced ruthlessly and the "PRIOR fallback" must be the honest common case,
not the embarrassing exception.

---

## SCOPE REALISM + THE 80/20

**Total scope: ~35 waves (D1×6, D2×8, D3×8, D4×7+, D5×8) with a hard dependency spine.** For one person +
agent sessions on same-day-squash cadence, this is a multi-month program where the spine (ontology → basis →
backfill → grading → hazard) must not go stale mid-flight (memory: stale-worktree hazards are real here). It
is NOT one-person-realistic as a single coherent push. It IS realistic as a sequenced program IF ruthlessly
subsetted.

**The 80% of value is ~8 waves:**

1. **D3-W0 — wall-clock TODAY + kill the push-forward + staleness banners.** Stops the active rot TODAY,
   zero dependencies, ships day one. Highest value/effort in the entire program.
2. **D2-W1+W2 — grading_stats extraction + the missing live writers (US sector, country) + cone columns.**
   Turns "unmeasured" into "accruing for real," creates the substrate, no basis dependency.
3. **[NEW] Phase-0 signal-power gate (M4)** — one wave on the backfill: does the oscillator have ANY forward
   drawdown-adjusted edge? Gates whether the rest is worth building. Cheapest de-risk.
4. **D1-W1+W2 — ontology module + generated JS + kernel state machine.** Kills the contradictory-label
   pathology (the acute action-generating bug: buy-into-a-top). This is the audit's #2/#5 fix.
5. **D4-W1 — dual-basis store (collector flip + read API), byte-safe per D4's own verification.** Additive,
   unblocks honest grading; the re-key can wait.
6. **D2-W3+W4 — backfill + the three primitives**, rendered with the A2 fix (BACKTEST vs LIVE badge
   discipline) — the first real track record.
7. **D3-W1+W3 — proxy registry + engine-backed cycle.html with the TWO-tier (MEASURED/FRAME) rendering
   from A1**, structural cards as timelines-not-dials (A4). Collapses the schism, the root disease.
8. **D3-W4 — falsifier tripwires** (the most honest, highest-trust surface, cheap given alerts infra exists).

**Explicitly DEFER (the 20% that is 60% of the risk/effort):** the full hazard model + conditional cells +
regime prior (D5-W1..W5) — ship the median-half-cycle IQR band (already honest) and the Phase-0 signal gate;
build hazard only if the signal gate says the oscillator has edge AND you pre-registered the trade-decision it
must move (A3). Defer FX decomposition beyond the local-currency default (A10). Defer D5-W8 novel features
entirely (SO4). Defer binding-calibration of stance/ladder until backfill exists (fold the stance into the
calibration artifact when D2-W6 runs).

**One-line program directive:** *Ship the honesty split as two words, stop the rot, prove the signal has edge
BEFORE building the prediction apparatus, and never let a backfilled number wear a live track-record's badge.*
