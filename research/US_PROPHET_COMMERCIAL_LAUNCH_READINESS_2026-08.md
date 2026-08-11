# US Prophet — commercial launch readiness review (2026-08-11)

**Reviewer role:** independent launch reviewer (Handoff D). I did not design the release
candidate and do not assume its design is correct.
**Governing spec:** `04_PROPHET_LAUNCH_READINESS_AND_PUBLIC_PROOF.md` (product promise, stage
model, signal-card contract, entry-quality contract, launch evidence, Public Proof Board,
tier behavior, UX hierarchy, launch gate). Access matrix:
`01_ACCESS_PAYWALL_AND_PRICING_RULING.md`. Role law: `06_EXECUTION_DOCKET…` §3.
**Program of record:** `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.7/§6.8/§6.9.

**Standing of this document.** This is an INPUT to the executive release decision. It is not
release approval — Sol approves releases. Measurement/display tier: nothing here promotes,
ranks, gates, or sizes anything. Every quantitative claim below cites an artifact path plus a
table/section id; no number is asserted from memory, including numbers supplied to me in the
commissioning brief (three of those are corrected in §2.1).

---

## §0 RULING

### §0.1 Coverage-gate answer FIRST — the motivating exemplars and the current regime

House law (operator 2026-08-10, `discovered-rule-must-cover-the-motivating-exemplars`)
requires the discovered rule to be run against the names that motivated it and against the
CURRENT regime, and that answer to lead. It does.

**(a) The four exemplars the bake-off itself gates on.** Receipts:
`research/prophet_us_audit/early_admission_bakeoff_results.json` tables `R1.STLD`, `R1.NEM`,
`R1.HL`, `R1.UEC`, `R9k` (PR #5339, head `8aee5aea870`).

| exemplar | union-lane fire (C1/C2r/C3) | entry vs its own reference low | td→trough | false bounce | incumbent C0 | verdict for the union lane |
|---|---|---|---|---|---|---|
| **STLD** | 2026-07-14 @ 233.35 | **+7.85%** | +7 (post-trough) | False | 2026-08-07 @ 262.45 = **+21.30%** | **WIN** — 18 sessions earlier, 13.5pp closer |
| **NEM** | 2026-07-09 @ 94.81 | +3.98% backward / **+6.83% trough-referenced** | **−6 (pre-trough)** | **True** | 2026-07-27 @ 93.47 = +5.32%, marker `quality=block`, reason "counter-trend, held but no 200-reclaim" | **LOSS** — fired into the knife; the incumbent fire the product REFUSED was closer to the eventual trough |
| **HL** | 2026-06-16 @ 16.72 | **+21.07%** | +5 | False | not in store universe | **LOSS on proximity** — worse than the incumbent's pooled +10.1% |
| **UEC** | 2026-06-22 @ 11.47 | **+22.54%** | +7 | False | not in store universe | **LOSS on proximity** — and MFE_42 = −0.8% |

**Score: 1 win, 3 losses on the names that motivated the work.** The pooled claim ("early
lanes surface ~35–45% closer to the eventual trough", bake-off §A1) is TRUE pooled (R9h:
C1 +6.5% / dot +6.9% vs C0-take +10.6% trough-referenced) and FALSE on three of the four
named exemplars. The deep-miner class (HL, UEC) — the class the operator escalated about — is
where the union lane surfaces at **+21% to +22.5%** off the low, i.e. exactly the "reaches my
desk up 10–15% and I chase" complaint the program exists to fix (masterplan §6.9 R8).
The bake-off's own §R1 prose reports HL/UEC as "the early lanes fire INTO their deep miner
washouts (HL C2r median td_to_trough −9.5; false-bounce 37–60%)" and does **not** print the
+21.07% / +22.54% entry-vs-low figures that its own frozen `R1.HL`/`R1.UEC` tables carry.
That omission is a finding (§4.4, F-7).

**(b) The panel that is MISSING.** The exemplar gate covers STLD/NEM/HL/UEC. It does **not**
cover ASTS, GPCR, SKY, VSEC, XPEL or NGVT — the six names in the operator's original
2026-08-07 lateness escalation (`research/prophet_us_audit/ENTRY_LATENESS_FORENSIC_2026-08-07.md`
§2, §4). The union lane has never been run against the names whose lateness started the
program. Neither study replays them. This is an unfilled hole in the launch-evidence list
(04 §6 "examples where confirmed was correct but too late").

**(c) The CURRENT regime.** `early_admission_bakeoff_results.json` table `R2h`
("CURRENT-REGIME CELL — episodes with T >= 2026-01-01"), n = 436 C1 episodes / 228 names:

| lane | near-low% | entry vs low | td→trough | false-bounce% | stopA surv% | excess vs SPY @21d | @42d |
|---|---|---|---|---|---|---|---|
| C0 (incumbent, pooled) | 6.54 | +12.0% | +14 | 7.59 | 73.85 | **−0.4pp** | **+0.4pp** |
| C1 (union spine) | 39.91 | +5.8% | +3 | 21.74 | 53.20 | **−2.2pp** | **−4.4pp** |
| C2s dot | 40.96 | +5.8% | +4 | 21.26 | 55.77 | −1.9pp | −3.0pp |
| C3 | 46.21 | +5.2% | +2 | 22.13 | 55.96 | −2.4pp | −3.0pp |
| C4 | 44.97 | +5.5% | +3 | 26.75 | 51.70 | −0.9pp | −1.5pp |

**In the tape we are launching into, every early lane's naked excess return over SPY is
negative at both horizons, and the confirmed lane's is not.** The geometry improvement is
real and holds in 2026; the return does not. The bake-off says this plainly (§R2 "honest
wrinkle") and it is the single most launch-relevant number in either study.

**(d) Honest-N, as distinct episodes.** Bake-off `R2f`: C1 7,973 episodes / 240 names /
2,658.7 name-years (`universe.panel_name_years`); dot C2r 3,630 / 240; C0-take 2,828 / 240.
Union set (footprint study `footprint_picker_results.json` `union`): **9,805 episodes / 240
names / 2,880.5 name-years**. Episodes are 10-session-deduped per construction (bake-off §2),
so they are not independent across names or across time — the studies report month-cluster
bootstrap CIs on §R8 spreads but **no clustering adjustment on the headline lane means**.
Current-regime cell honest-N is **436 episodes on 228 names in one partial year**.
The live public track record is a different and much thinner object: `site/us_track_record.html`
publishes 256 finished trades **from only 11 separate board days**, win rate 59% with CI
[50.4%, 64.4%], average trade **+0.5%**, and 262 picks still running and uncounted.

**(e) Who is missing from the panel — and the disclosure covers the smaller half.** Bake-off
§6 discloses one form of survivorship: the panel is the 241-name `site/signals` store universe
∩ priced = **240 names**, and "names that delisted before the store existed are absent".
`R0` records that **18,137 C0 and 7,202 C2s store events predating the ~2014+ OHLCV window
were dropped and never relocated**. Basket membership back-projects to a single
`seed_date=2023-05-09` (986/1,038 memberships), so every breadth result is a post-2023 slice
(§R3).

**The larger and undisclosed half is forward selection.** Enumerating the price root the
study reads (`early_admission_bakeoff.py:1697-1708`, panel = `sorted(load_store(site/signals))`
∩ priced): **2,779 priced tickers exist on the host; 240 are used (8.6%)**, and **2,539
fully-priced names with adequate history are excluded**. The 240 are today's deep-history
marker roster — it contains PLTR, APP, HOOD, CVNA, VRT, GEV, TKO, SNDK, DASH, CRWD, i.e.
names in the panel *because they succeeded*, back-tested from 2014. For a study whose outcome
column is "did this washout resolve upward within 42 sessions", winner-inclusion biases
`MFE_42`, `fwd21/42`, `r_mult_42`, `reached_2r` and every survival column **upward in every
lane**, hardest in the lanes that fire deepest into washouts. Compounding: the study's own
motivating hard-mode names, **HL and UEC, are `ADDON_EXEMPLARS` (`:99`) and are excluded from
every pooled number** (`:1098`, `:1255`, `:1868-1869`) — the panel systematically excludes the
asset class the conclusion is meant to serve. There is no delisted-name control panel and no
small/mid-cap or miner cohort anywhere in either study. `:1798` (`len(df) < 300: continue`)
silently drops short-history names on top of that.

**(f) Forward evidence.** 04 §6 is explicit: "Backtests support design. Forward evidence
outranks backtests." The W7 forward grader's first possible grade is **~2026-08-18**
(masterplan §6.9 R6: `candidates=7465 dates=4 pending=29860 new=0`). **Forward evidence for
the union tier is empty at review time.** Under the spec's own ordering rule, the release
candidate is being judged on the evidence class the spec ranks second.

### §0.2 The ruling

> ## PRIVATE BETA ONLY

The research is honest, well-measured, and adversarially red-teamed to a standard most
published work does not reach (see §11 strengths). The **wiring is not** — and it is not a
commercial launch surface today, for six reasons that are independent of each other and each
sufficient:

0. **The release candidate's wiring ships a fresh instance of the exact defect it was written
   to close.** PR #5370 admits on the still-open 3D bucket, so a name renders
   "Early turn — watch, don't chase" and is erased the next session with no receipt — 4 ghosts
   of 8 live fires on STLD, 13 of 20 on NEM, measured on the PR's own fixtures, with the
   study's headline example (STLD 2026-07-10) double-stamped (B-15, §5.4). A repaint is
   disqualifying for a product whose entire pitch is *timing*, and fatal to any proof board.
   Alongside it: a scheduled contract red that is green only because a manifest is stale
   (B-16), a shipped deck that is **not** the object the recall numbers were measured on
   (B-17), an inverted deck⊇plan invariant with un-era-stamped admissions (B-18), and a chase
   verdict fired off a two-month-dead signal onto every plan (B-19).

1. **The product's own numbers say the early book loses money mechanically and is flat-to-
   negative versus the index in the current regime.** Union basis-X stop-out 56.5%, median R
   **−1.0**, mean +0.359 carried entirely by the right tail (`footprint_picker_results.json`
   `R2`); mechanical hold-42 median R is **negative for every early lane** and positive for
   the incumbent (`bakeoff` `R9e`: C1 median −0.360, C2r −0.267, C4 −1.000 vs C0-take
   **+0.373**); 2026 excess vs SPY −2.2pp/−4.4pp (`R2h`). Both studies state that the early
   book "monetizes ONLY under the operator's cut-fast/let-run execution and some second-stage
   selection" (bake-off §R2, §A1) — and the footprint study then **measured two candidate
   second-stage selectors and both were null** (`footprint_picker_results.json` `R3`: P1
   0.95 R/name-year, P2 0.97 vs P0's 1.21). Shipping to paying customers a signal whose
   expectancy is known to depend on one individual's discretionary execution, with the
   mechanical substitutes measured and null, is a product-truth problem, not a copy problem.
2. **A live "validated" claim is on the anonymous public landing today and CI cannot see
   it** (§7 B-1, proven). This is a house-law violation currently shipping.
3. **The Public Proof Board contract is inverted by what ships today**: the live public proof
   payload is `kind: "delayed_winners"` — **winners only, "Selected because they worked"**
   (`site/prophet/showcase.json`; builder comment `scripts/build_prophet.py:198-207`
   "winners only (ret > 0), ranked by return"). 04 §7 requires wins **and** losses. §7 B-2.
4. **The spec's stage model is largely unimplemented on the live board** — no CONFIRMING
   tier, no AGING, no EXTENDED, and 116 of 140 live plans carry no `admission_class` at all
   (§5). A stage-model product cannot launch without its stages.

**What PRIVATE BETA ONLY means concretely here:** ship the union deck to a named, consenting,
logged-in cohort (operator + invited Pro accounts) behind a hard entitlement gate, with the
public landing teaser and public proof board **withdrawn or fixed first** (B-1 and B-2 are
not beta-deferrable — they are live-today defects on anonymous surfaces). Re-review after the
first forward-grade window closes (≥ 2026-09-30, i.e. ≥ 6 weeks of W7 grades on the union
era stamp, not the 08-18 first-grade date).

I explicitly did **not** rule NO-GO: the mechanism, the measurement discipline, and the entry-
zone machinery are genuine assets, and the geometry improvement reproduces in the current
regime. I explicitly did **not** rule GO WITH BLOCKERS: GO-WITH-BLOCKERS presumes the
blockers are execution debt. Here the top blocker is an **evidence** blocker (the expectancy
result), which no amount of implementation clears.

### §0.3 Blockers ranked by launch risk

| # | severity | blocker | evidence |
|---|---|---|---|
| **B-1** | **blocker** | Public landing ships "validated drawdown gate" (EN) + "已验证的回撤门槛" (ZH); the CI guard is structurally blind to it | `site/index.html:507`; `site/prophet/showcase.json`; `scripts/check_validated_claims.py:100` — §7 |
| **B-2** | **blocker** | Public proof surface is winners-only and self-declares it | `site/prophet/showcase.json` `kind/note`; `scripts/build_prophet.py:198-213` — §7, §9 |
| **B-2b** | **blocker** | **The paid Prophet board is gated client-side only** — every board row is rendered into the anonymous HTML and then blurred/hidden by CSS. The repo's own doctrine names this as the wrong pattern for paid data | `templates/dashboard.html.j2:15690-16029` (unconditional render loop), `templates/tier_preview.js:75-98, :198-215`; `docs/TIER_PREVIEW_PATTERN.md:18-21` — §7 |
| **B-3** | **blocker** | Early-lane expectancy is mechanically negative at the median and index-negative in 2026; no measured second-stage selector exists | `R9e`, `R2h`, footprint `R2`/`R3` — §4.1 |
| **B-4** | **blocker** | Forward ledger empty for the union era; first grade ~08-18 | masterplan §6.9 R6 — §0.1(f) |
| **B-5** | **blocker** | Spec stages CONFIRMING / AGING / EXTENDED absent; `admission_class` null on 116/140 live plans | `site/prophet/index.json` — §5 |
| **B-6** | **major** | Two published track records disagree (board 59% n=256/11 days vs plans ledger 41.2% n=17 with 11/28 quarantined) | `site/us_track_record.html`; `site/prophet/index.json.record` — §7 |
| **B-7** | **major** | Single opaque conviction number in user-facing copy ("conviction 12/100"), plus a second blended 0-100 `management_confidence` in the payload | `engine/prophet_bridge.py:2649`, `:2754`; `site/prophet/index.json` — §6 |
| **B-8** | **major** | One ranking axis for both lanes: early-turn starters are ordered by the CONFIRMED lane's `us_prophet_v1` priority score | `engine/prophet_bridge.py:589-613`; live EU plan `_priority_score=69.0` / `_conviction_score=12` — §5.3 |
| **B-9** | **major** | Publication lag and repaint are unfixed on the plan path; any public timestamp is therefore not a knowable date | lateness forensic §1(c), §1(d) — §3.3, §9 |
| **B-10** | **major** | `entry` field is the chase-above line, not the entry; zone present on only ~24/140 plans | live EU plan (`entry`=`trigger`=`chase_above`=1.31, zone 1.16–1.17); 113/140 `entry_zone_state.reason` = "pre-R3 plan" — §6 |
| **B-11** | **major** | `stage_tilt` ships `provisional: true` + basis "forward-shadow checked (~2026-12)" on every plan, a check `DNR:HOLD-PSQ-TILT-CLOCK` records as structurally unable to occur | `site/prophet/index.json` plans[].stage_tilt; `DNR:HOLD-PSQ-TILT-CLOCK` — §7 |
| **B-15** | **blocker** | **PR #5370 ships a NEW repaint**: the union admits on the still-open 3D bucket, so a name renders "Early turn — watch, don't chase" and is silently erased next session. Measured on the PR's own fixtures: STLD 8 live fires → 4 survive (**4 ghosts**), NEM 20 → 7 (**13 ghosts**). STLD's 2026-07-10 is double-stamped — the field's own headline example | `engine/us_early_turn.py:651-653` (docstring claim), `:835`, `:1102-1103` — §5.4 |
| **B-16** | **blocker** | **Scheduled hard red**: `early_signal_dates` is emitted conditionally but registered in `schema_fields` (ALWAYS-PRESENT), `schema_version` not bumped, and `artifact_manifest.json` not regenerated — green today only because the manifest is stale | `engine/signal_quality.py:937-949` vs `scripts/export_signal_contracts.py:170-180, :223`; `.github/ci/legacy-jobs.yml:2172` — §5.4 |
| **B-17** | **major** | **The shipped deck is not the measured object.** `early_turn_watch` is appended downstream of `select_candidates`, so it is union ∩ the confirmed lane's own admission gate — while the 60.6% recall / 12-session-lead numbers that justify the split are naked-union over the whole universe | `engine/prophet_bridge.py:4018, :4318-4319`, `:1127-1132`; claim at `engine/us_early_turn.py:1096-1099` — §5.4, §8.2 |
| **B-18** | **major** | Deck roster is NOT a superset of the plan roster (114 STLD sessions with `fired=True, deck_admitted=False`), and those rows carry `ADMISSION_CLASS_EARLY_TURN` with `admission_era: None` — an admission class with no era stamp | `engine/us_early_turn.py:1047-1058, :1102-1103`; invariant claimed at `engine/prophet_bridge.py:4181-4182` — §5.4 |
| **B-19** | **major** | A user-facing chase verdict fires off a **dead** union fire, on every plan including confirmed-lane `buy_now` rows | `engine/us_early_turn.py:948` (keys on `fire_date`, ignores `fired`); `engine/prophet_bridge.py:300-302, :4536-4569` — §5.4 |
| **B-12** | **minor** | Three headline numbers in the commissioning brief are not reproducible from the frozen artifacts | §2.1 |

---

## §1 Method and scope

**Read (in full or targeted):** the charter and 04/01/02/06 convergence docs; the frozen
bake-off (PR #5339, `EARLY_ADMISSION_BAKEOFF_2026-08-11.md` + its 46-table results JSON); the
frozen footprint-picker prereg (PR #5359, 13 tables); the wiring PR #5370 (engine diff, PR
body, tests); `ENTRY_LATENESS_FORENSIC_2026-08-07.md`; masterplan §6.7/§6.8/§6.9 + execution
records; `docs/DESIGN_DOCTRINE.md`; `research/DO_NOT_REBUILD.md`; the live payloads
`site/prophet/{index.json, showcase.json, plans/, states/}`; `site/index.html`;
`templates/{index.html, us_track_record.html.j2, _prophet_card.html.j2}`;
`scripts/{build_prophet.py, build_track_record_page.py, check_validated_claims.py}`;
`engine/prophet_bridge.py`.

**PR state at review time (2026-08-11):** all three release-candidate PRs were **still OPEN**.
#5339 head `8aee5aea8700cfdb6057f8e647ed7766b3975312`; #5359 head `cfa49b3a92b2e995bd5475f68997be105959cc49`;
#5370 head `edaf501ae7e4e1547e6124d50dd1b59e3cb17954` — note this is **not** the `ed658de2c55`
head named in my commissioning brief; #5370's head moved (a main merge, `Merge branch 'main'
into claude/prophet-us-union-admission-wiring`). Studies read from the PR head refs.

**New computation:** none. Every number below is read from a frozen artifact or from a live
committed payload. Where I disagree with a study, I disagree from its own frozen tables.

**Ruler discipline I applied to my own reading** (the three artifact classes the bake-off §RT
records): (a) labels anchored on a reference low make entry-distance-correlated features fake
discriminators; (b) features conditioned on another episode's label leak the future; (c)
policy comparisons that re-anchor the stop at a later entry manufacture stop-out differences.
I checked each against the frozen record in §4.4.

---

## §2 Evidence table

### §2.1 Corrections to the commissioning brief (verify-every-number rule)

| brief claim | frozen artifact says | status |
|---|---|---|
| "66.8% coverage of confirmed fires at a ~12-session median lead" | `bakeoff R2i`: C1-relaxed **60.62%** @ median lead 12; dot C2r 29.21%; C4 68.69%. **No union-coverage row exists in either results JSON.** PR #5370's own body table also says 60.6% | **UNSOURCED** — 66.8% appears in no frozen artifact I could find (grepped both results JSONs, the masterplan, and the PR body) |
| "win 46.1% at +42 sessions, mean +0.336R, ~46% stopped (1R≈6%)" | `footprint R2` basis A: stop-out **46.18%**, mean R **0.3327**, median risk **5.96%** of entry. These are the same three numbers | **MISREAD** — 46.1% is the STOP-OUT share, not a win rate. There is no 46.1% win rate. Median R on basis A is **−0.3131** |
| "CONFIRMED lane … win 66.1%" | `bakeoff R9e` C0-take: mean R **0.447**, median **0.373**, stop-out **15.73%**. No win-rate column exists in R9e | **UNSOURCED** as stated; the defensible C0-take claim is the R-distribution, not a 66.1% win rate |
| "~46% stopped (1R≈6%)" for the early lane | correct on basis A only; on the study's **PRIMARY** basis X (entry − 2×ATR14) it is **56.5%** stopped at 1R≈4.6% (`footprint R2`) | **basis-dependent** — the primary basis is harsher and must be the quoted one |

These four are why a launch packet must never quote a number without its table id. Two of the
four flatter the release candidate.

### §2.2 The evidence that actually exists

| # | claim | value | source (artifact §table) | tier |
|---|---|---|---|---|
| E1 | Union set size | 9,805 episodes / 240 names / 2,880.5 name-years | `footprint_picker_results.json` `union` | measured |
| E2 | Recall of the incumbent (relaxed spine) | 60.62% of C0 episodes preceded ≤30 sessions, median lead 12 sessions | `bakeoff R2i` | measured |
| E3 | Recall of the charter-LITERAL form | **25.0%** — below the dot's 29.2% | `bakeoff R2i`, `R9b` | measured |
| E4 | Proximity, backward-anchored | C1 49.8% near-low / +5.0%; C0-take 7.47% / +10.3% | `bakeoff R9h` | measured |
| E5 | Proximity, trough-referenced | C1 33.5% / +6.5%; C0-take 6.83% / +10.6% | `bakeoff R9h` | measured |
| E6 | Ambient near-low base on this panel | 24.7% backward / 16.4% trough-referenced | `bakeoff R9g` | measured |
| E7 | False-bounce rate | C1 24.3%, dot 20.0–21.4%, C3 25.0%, C4 26.6% vs **C0-take 3.1%** | `bakeoff R2a` | measured |
| E8 | Stop-A survival | early lanes 49.5–55.6% vs **C0-take 84.3%** | `bakeoff R2a` | measured |
| E9 | Pre-trough firing share | early lanes **35.1–42.2%** vs C0-take **5.16%** (C0-all 14.45%) | `bakeoff R9i` | measured |
| E10 | Survival conditional on pre-trough | **6.99–11.26% in every lane** including the incumbent | `bakeoff R9i` | measured |
| E11 | Survival conditional on post-trough | C0-take **88.46%** vs early lanes 76.15–79.36% | `bakeoff R9i` | measured |
| E12 | Mechanical hold-42 R | C1 mean +0.359 / median **−0.360** / 47.34% stopped; C2r +0.290 / **−0.267** / 44.69%; C4 +0.405 / **−1.000** / 50.84%; **C0-take +0.447 / +0.373 / 15.73%** | `bakeoff R9e` | measured |
| E13 | Union book, primary entry-anchored basis | stop-out **56.5%**, mean R +0.359, **median R −1.0**, median risk 4.61% | `footprint R2` | measured |
| E14 | Patience policies | P1 0.95 and P2 0.97 R/name-year vs P0 **1.21** — both FAIL their pre-stated win condition | `footprint R3` | measured |
| E15 | Why the policies fail | skipping worked (declined fires stopped out 82.7%/77.8%); the deficit is the later entry (−1,092R / −989R). Holding the fire's own risk contract fixed, waiting changes stop-out by **exactly 0** (50.35% = 50.35%) | `footprint R8b` | measured |
| E16 | Every static durability feature | collapses or flips under risk-equalized labels; decline-depth is the only MAYBE and is volatility-confounded | `bakeoff R9d`, §R8 | measured |
| E17 | Repeat-fire "filter" | **RETRACTED** — look-ahead; PIT-only spread −2.2pp (C2r) / +0.3pp (C1) | `bakeoff R9c` | retracted |
| E18 | Theme breadth as a false-start filter | NULL at the pre-stated 10pp bar, direction runs AGAINST the hypothesis, post-2023 slice only | `bakeoff R3` | null |
| E19 | Footprint/accumulation battery (5 deep + 2 thin) | every feature null; the two near-misses mechanism-explained as stop-width | `footprint R4`, `R8c` | null |
| E20 | Chart-vs-tradable gap | store `early_markers` stamped at bucket **OPEN** (3,756/3,760 move under remapping); honoring knowability costs **8.6pp** of near-low rate (53.4% plotted vs 44.8% knowable) | `bakeoff R0`, `R0c` | measured defect |
| E21 | Structure stops mark lows | 34.9% of 12,940 confirms within ±2 sessions of the local low vs a **15.7% random null** = 2.2× chance | `bakeoff R4a`, `R9f` | measured |
| E22 | §6.8(a) histogram-disarm hypothesis | NOT supported (0.9% cohort, marks lows LESS: 23.6% vs 35.0%) | `bakeoff R4b` | null |
| E23 | Entry-placement machinery (zones) | median entry-vs-low **7.26% → 2.29%** (−4.97pp, half-stable ±0.75pp) | masterplan §6.9 R4 (PR #5007) | measured |
| E24 | Prior lateness baseline | median pre-signal run-up +6.34%; 66.7% ≥5%; entry +2.72% above signal close; publication lag median 5d / p75 11d / max 57d | lateness forensic §1(a)(b)(c) | measured, **not reproducible** (see §3.3) |
| E25 | Repaint | 4/5 dissected names flip `eligible` True→False when the next bar lands; XPEL live 50.29 (+18.50%) vs surviving-history 47.68 (+11.58%) | lateness forensic §1(d) | measured defect |
| E26 | Live public track record | 59% win / +0.5% average trade / 256 finished trades from **11 board days** / CI [50.4, 64.4] / 262 uncounted in-flight | `site/us_track_record.html` | live |
| E27 | Plans-ledger record block | 28 rows, **11 quarantined**, 17 scored, 7 wins, win_rate 41.2%, avg +3.77% | `site/prophet/index.json` `record` | live |
| E28 | Live board composition | 140 plans; `admission_class`: 116 null / 14 patience / 9 confirmation / **1 early_turn_starter** | `site/prophet/index.json` | live |
| E29 | Live zone coverage | 113/140 plans carry `entry_zone_state.reason = "plan carries no entry zone (pre-R3 plan)"` | `site/prophet/index.json` | live |
| E30 | Forward grades | first possible grade ~2026-08-18; grader alive, 0 grades to date | masterplan §6.9 R6 | empty |

---

## §3 Entry timing — old vs new

### §3.1 What improved, measured

Against the **actioned** incumbent (C0 `quality=take`, the 36% of markers the product's own
buy filter passes — the honest comparator, per bake-off §RT item 4):

- **Lead time:** median 12 sessions earlier, on 60.62% of incumbent episodes (E2). On the
  STLD exemplar the gap is 18 sessions and 13.5 percentage points of price (E: `R9k`).
- **Proximity:** trough-referenced median entry +6.5% (C1) vs +10.6% (C0-take) — a ~39%
  reduction in distance-from-trough (E5). Backward-anchored near-low rate rises from 7.47% to
  49.8% against a measured ambient base of 24.7% (E4, E6).
- **The improvement survives into 2026** (E: `R2h` — C1 near-low 39.91% / +5.8% / +3td vs C0
  6.54% / +12.0% / +14td).
- **Independently, the entry-PLACEMENT half was already fixed by mechanics, not by the
  signal:** structure-anchored zones cut median entry-vs-low from 7.26% to 2.29% (E23). This
  is the largest single measured entry-timing win in the whole program and it came from the
  zone builder, not from earlier admission.

### §3.2 What the improvement costs, measured — and a correction that favours the candidate

The same tables (E7–E12): 6.5–8.7× the false-bounce rate, 7–8× the pre-trough firing share,
and a mechanical R-distribution whose **median is negative in every early lane and positive in
the incumbent**.

**Correction C-1 (see §4.6): the study's headline "~30pp less stop-A survival" is itself
stop-width arithmetic and overstates the cost by roughly 2–3×.** The bake-off's stop A is
`P_low × 0.99` re-struck at every fire (`early_admission_bakeoff.py:612-613, :656`), so stop
*width* is identically `entry_vs_low` — the very confound the study's own §RT retracted one
level down, at the feature level. Recomputing from the study's own frozen episode plane using
columns it already computes but never tabulates cross-lane (`survive_fix8`, `survive_atr2`,
`survive_atr3`, referenced only at `:1367`, `:1386`, `:1410` inside within-lane analyses):

| lane | median entry_vs_low | survival, stop A (P_low×0.99) | stop −8% | stop 2×ATR | stop 3×ATR |
|---|---|---|---|---|---|
| C0 all | 10.03% | 73.0% | 62.8% | 43.3% | 57.6% |
| C0 take | 10.28% | **84.3%** | 75.6% | 57.4% | 69.0% |
| C1 | 5.00% | 52.6% | **63.2%** | **44.1%** | **59.5%** |
| C2r | 5.50% | 55.2% | 63.1% | 43.0% | 57.9% |
| C4 | 4.54% | 49.1% | 63.4% | 44.8% | 59.8% |

Under every distance-independent stop, the durability penalty collapses from ~30pp to
**8.8–14.4pp against the actioned incumbent, and to zero or slightly negative against the
pooled incumbent** (C1 beats C0-all on all three alternative bases). This correction is a
review-side recomputation of the study's own frozen columns, not new data; it needs the study
to print three columns in `r9_metric_row` (`:1186-1196`), not a re-run.

**What survives the correction, and it is the load-bearing half:** the union book's central
outcome on the *entry-anchored* primary basis is still a stop-out (56.5%, median R −1.0,
`footprint R2` — that basis has no P_low anchor at all, by design), and the 2026 excess-return
cell (`R2h`) is a pure price measure with no stop in it. **B-3 stands on those two.** What
does not stand is the "~30pp survival gap" as a marketing or adjudication fact.

The bake-off's decomposition (`R9i`) needs the same treatment — see §4.6 C-2.

### §3.3 Chase cases and what is still broken

- **Chase case, live and structural:** the plan `entry` field is the DON'T-CHASE line. Live
  early-turn starter `EU-BULL-20260805` carries `entry = trigger = chase_above = 1.31` while
  the actual instruction is a 1.16–1.17 zone (`pct_from_entry: -11.07`). Any consumer that
  reads `entry` as the entry — including the Terminal, any API client, and the plans JSON
  itself — reads the chase level. The lateness forensic §5 already named this
  ("entry = asof close by construction"); it is unfixed.
- **Publication lag is unfixed and unmeasured since 08-07.** Median 5d, p75 11d, max 57d
  (E24) — over which price moved a median +3.03%. No committed instrument reproduces this
  table; the forensic's own 2026-08-09 revalidation boundary states the corpus grew 96 → 124
  plans and "no committed replay instrument reconstructs this table from a pinned plan/price
  manifest". **The program therefore has no current measurement of its own publication lag.**
- **Repaint is unfixed on this side.** E25. The CN-side PIT-latch fix sat unmerged on
  `claude/missing-300363-china-prophet-8702fa` as of that receipt. Until a fired event cannot
  be un-fired, no public timestamp is trustworthy and no backtest of "earliness" is honest —
  the forensic states the direction of the bias: "backtests over surviving history are
  optimistic about live earliness."
- **The chart is 2 sessions ahead of the tradable signal.** E20/`R0c`. The grey dot the
  operator points at is plotted at the bucket-OPEN label; honoring knowability costs 8.6pp of
  near-low rate. Every screenshot-based intuition about the dot is measurably better than what
  any admission lane can act on. PR #5370 adds `early_signal_dates` (bucket-LAST) additively —
  which fixes the store, not the chart.

### §3.4 Regime and sector cells

Regime: only the 2026-YTD cell exists (`R2h`) plus a time half-split for sign stability
(`R2g`). There is **no regime-state conditioning** (no bull/bear, vol, or breadth regime
split) anywhere in either study. Sector/theme: the only conditioning lane is basket breadth
(`R3`), which is null, direction-adverse, and confined to the post-2023 membership slice.
**04 §6 requires "regime breakdown" and "sector/theme breakdown" before broad launch. Neither
exists in a usable form.** This is a launch-evidence gap, not a defect.

---

## §4 Precision and failure

### §4.1 The core precision result

Under the study's own primary, fully entry-anchored label (basis X, entry − 2×ATR14):
**stop-out 56.5%, mean R +0.359, median R −1.0** (E13). Read plainly: *the central outcome of
a union-admission fire is a stop-out*, and the positive mean is a right-tail artifact. On the
continuity basis A it is 46.18% stopped, mean +0.333, median −0.313. On the loosest basis
(entry −8%) it is 37.06% stopped, mean +0.278, median +0.038.

The incumbent's actioned cohort is better on every axis a mechanical user experiences
(E12: 15.73% stopped, median +0.373). **There is no reading of these tables in which the
early lane is a better trade than the confirmed lane under a rule-following user.** It is a
better *surfacing* mechanism for a discretionary user who is a genuine second-stage filter.

### §4.2 The second-stage filter does not exist mechanically

This is the decisive finding for commercialization. Both studies searched for it and both
returned pre-registered nulls:

- Static feature battery (10 families, bake-off §8): every LIVE feature collapsed or flipped
  under risk-equalization; one was retracted as look-ahead (E16, E17).
- Theme breadth: null, direction adverse (E18).
- Accumulation footprint (5 volume-profile + 2 dark-pool, full 12-year depth): every feature
  null, both near-misses mechanism-explained as stop-width (E19).
- Patience policies (wait-k, pivot-confirm): both fail the pre-stated win condition; and
  holding the fire's own risk contract fixed, waiting changes the stop-out rate by **exactly
  zero** — "waiting does not get you stopped out more; it gets you less of the move"
  (footprint §R3/`R8b`, E14/E15).

The footprint study's own honest summary: "the SELECTION signal exists ex-post (the declined
fires really were the losers — the largest separation in this file) but is not knowable at T".
**The one thing that would make the early book commercially safe is measured, present in
hindsight, and unavailable at decision time.**

### §4.3 The dominant structure is ex-post and therefore not a product feature

The pre/post-trough decomposition (E9–E11) is the study's central explanatory result, and it
is **not computable at fire time**: `td_to_trough` is defined as `T − argmin(low over [T−45,
T+15])` (bake-off §2), i.e. it needs 15 sessions of future data. The bake-off says so
(`R9i` notes: "the post-trough false-bounce column is 0 BY IDENTITY… `false_bounce` is
therefore very nearly a restatement of `td_to_trough < 0`") and correctly declines to build a
filter on it, redirecting to PIT proxies in a future prereg (§A6) — which the footprint study
then ran and nulled (E14). **The honest statement for any launch packet is: "the thing that
separates good early fires from bad ones is whether the low has already printed, and we
cannot know that at the time we show you the name."** That sentence is compatible with a
watch-tier product and incompatible with a paid signal product.

### §4.4 My independent read on the three measurement-artifact classes

| class | study's claim | my verdict |
|---|---|---|
| (a) stop-width arithmetic | handled — §R8 verdict rewritten around `R9d` risk-equalization; `entry_vs_low` itself out-discriminates every feature (−29.6pp) | **HANDLED AT FEATURE LEVEL, NOT AT LANE LEVEL.** The feature work is better than most published work (`:1072-1078` prints median `entry_vs_low` beside every spread; `:903` marks `f_dist_swing` label-coupled; `:1222-1243` within-quintile spreads; `:1378-1414` three re-label bases). But `survive_fix8/atr2/atr3` are called **only** inside within-lane analyses (`:1367`, `:1386`, `:1410`); `r9_metric_row` (`:1186-1196`) emits `survA%`/`survB%` only, so **no cross-lane table anywhere uses a distance-independent stop**. The lane-level trade-off headline (`.md:252`, `.md:394`, `.md:428-429`) is therefore the exact defect the study retracted one level down. **blocker** for presentation; see §3.2 C-1 |
| (b) label leakage | handled — repeat-fire retracted (`R9c`) | **HANDLED, and thoroughly.** I re-walked the whole battery (`:735-801`): `f_dist_swing`/`f_higher_low` (`:768`) correctly enforce pivot-at-p-knowable-at-p+3 even though `_pivot_mask` (`:358`) uses `low.shift(-j)`; the 3D→daily ffill (`:368-373`) is bucket-LAST; `engine/signal_quality.py:189,213` already lag the weekly and 2D legs. Residuals: tercile cutpoints are **full-sample, not as-of** (`:955-963`, `:2360-2366`) — immaterial in fact (expanding-window recompute moves C2r `f_k_cross` −21.85 → −22.77pp) but undisclosed, **minor**; breadth basket assignment is not PIT (`:2310-2313` takes the episode's own basket from the CURRENT membership file while date-filtering only the other members), **minor** on a null lane. `R9d`'s relabels keep the false-bounce leg P_low-anchored — disclosed by the study itself (§A6) |
| (c) policy re-anchoring | handled — `R8b` re-runs P1 on the fire's own stop and horizon | **HANDLED IN THE FOOTPRINT STUDY, NOT IN THE BAKE-OFF.** `footprint R8b` is the single best piece of methodology in either file: it isolates a −7.06pp stop-out difference (57.41% vs 50.35%) as pure re-anchoring artifact. The bake-off does the opposite across its policy arms: each lane re-strikes `P_low` at its own `T`, and C0-take fires at `td_to_trough = +18` so its trailing window *contains* the realized trough — its stop lands at the true bottom 10.3% below entry, while C1/C4 fire at +2..+3 with a 4.5–5.0% stop. The "same rule" is a 2× different risk contract, and `survA%`, `false_bounce%` (`:637-638`) and `reached_2r` (`:676`) all inherit it. The study concedes the ≥2R column is "partly arithmetic" (`.md:255-257`) and does not extend that concession to the two columns that carry §A1/§A6. **blocker** for presentation |
| (d) **fourth class: dedup is a free parameter** | — | **NOT HANDLED.** `R9j` reports C4's near-low rate moving 55.5% → 50.3% under keep-last vs keep-first. Other lanes move <1.1pp, so the union spine is robust — but the sensitivity is reported for one lane and one column, and no lane reports dedup sensitivity of the outcome columns |
| (e) **fifth: overlapping episodes and no headline CIs** | — | **NOT HANDLED.** `dedup` (`:593-601`) collapses fires within 10 sessions, but forward windows are 42 sessions, so consecutive "episodes" overlap. Merging fires <42 sessions apart within a name gives independent-cluster counts **11–41% below the printed episode counts** (C0 7,918→6,325 = 1.25×; C1 7,973→5,832 = 1.37×; C2r 3,630→3,071 = 1.18×; **C4 11,111→6,556 = 1.69×**), and 16–18% of dot-family episodes sit on 20 calendar dates (systemic washouts; busiest 2020-03-26). `boot_spread_ci` (`:982-1003`) does month-cluster resampling correctly but has **exactly one call site** (`:1071`, inside `ore_ledger`) — `R2a`, `R2h`, `R2g`, `R3`, `R4a–e`, `R9a`, `R9b`, `R9e`, `R9h`, `R9i` carry **no uncertainty quantification at all**. Month blocks are also shorter than the 42-session outcome window, so even the §R8 CIs under-cover. And the LIVE/SUGGESTIVE verdict (`:1063-1070`) is decided on the point spread plus a two-way sign test and **never consults the CI it just computed** |
| (f) **sixth: the headline table mixes aggregation bases** | — | **NOT HANDLED — major.** `.md:225` captions the §R2 table "per-name-first medians", and rows C0-all/C1/C2s/C2r/C3/C4 are `R2a` (per-name-first). But the row the study calls the honest baseline — `.md:231` C0 `quality=take`: 7.4 / +10.3% / +18 / 3.1 / 84.3 — is `R9a`, which is **pooled** (`r9_metric_row :1186-1196` has no per-name-first path). On the table's own stated basis, C0-take reads near-low **0.0%**, false-bounce **0.0%**, survA 85.7%. **No per-name-first C0-take row exists anywhere in the artifact**, so the headline comparison is apples-to-oranges in both directions |
| (g) **seventh: the near-low headline has no conditional null** | — | **NOT HANDLED — major.** `R9g` (`:1493-1529`) draws ambient sessions **unconditionally** (24.7% backward / 16.4% trough-referenced). Every candidate fires by construction inside a 3D washout, where price sits near its own trailing low mechanically. The correct null is a random session *conditional on 3D %D < 20*, which is never computed. The tell is already in the artifact: **C4 — "any confirmed r3 pivot while %D<20", the crudest construction in the file — posts the best near-low rate of all eight lanes** (57.2% per-name-first, `R2a`), beating the operator's proposal, the grey dot and C3. C4 is presented as a lane rather than as the near-null it functionally is |

### §4.5 Pre-registration — §1–§7 is real; §8 has no freeze receipt

**Clean and verifiable:** the bake-off's charter commit `e602737841c` (2026-08-11 11:00:36Z,
155 lines) carries `§1 §2 §3 §4 §5 §6 §7` with `§R` empty, and the results `run_utc` is
12:36:43Z. That is a genuine, checkable pre-registration of the constructions, the ruler, the
breadth lane, the structure-stop replay and the exemplar gate. Deviations from charter are
named rather than absorbed (C1's spec-added branch, C4's %D-at-p+3 pin, both emitted as
`deviate()` calls at `:1774-1789`).

**Not clean — major:** that charter commit contains **no §8**. §8 — the durable-vs-false-start
discriminator lane, 16 features × 2 lanes = 32 univariate tests (`FEATURE_SPEC :878-896`), the
LIVE ≥10pp / SUGGESTIVE ≥5pp thresholds (`:78-79`), and the single-2×2 rule — first appears in
commit `77241997ccf` (11:41:31Z, "results, §8 ore ledger, §A adjudication"), i.e. **the same
commit as the harness and the results**. The doc's claim at `.md:156` that §8 was "frozen
before §R was viewed" has no artifact backing it. That is the section that produced the
study's headline discriminator deliverable. Relatedly, `results.json` records
`"charter": "<path>"` as a bare string and captures **no charter SHA** (`grep charter_sha` →
0 hits), so `.md:194`'s "charter SHA `e602737841c`" is prose, not a receipt; and the §1/§2
definition text for C1 and C4 was **rewritten in the results commit** to describe what the
code did — honestly labeled as deviations, but the original prereg survives only in git.

**Multiple comparisons:** no correction anywhere, on 46 tables. Mitigating: the read criteria
are pre-stated per lane and the headline outcomes are **nulls**, which is the direction
multiplicity bias does not produce.

**Knowability and publication lag — clean and better than the shipping store.** Every
synthetic fire is stamped at bucket-LAST (`snap :394-408`, `gen_c2s :445-459` remaps every
store OPEN label; `gen_c0 :419-425` prefers `signal_date` with a bucket-last fallback), and
pre-coverage store dates are *refused* rather than relocated to `idx[0]`. Intrabar look-ahead
is excluded conservatively: `survive_a` (`:673`) scans from `T+1`, `reached_2r` (`:678-684`)
tests the stop **before** the target on the same session, `mfe_42` (`:675`) uses closes not
highs. Next-open sensitivity is measured, not assumed (`:625-631`, surfaced as
`near_low_open%`; the gap is ~1pp). This is the strongest part of the engineering.

### §4.6 Corrections this review makes to the frozen studies' own conclusions

| id | the study says | the correction | direction |
|---|---|---|---|
| **C-1** | early lanes give up "~30pp of stop-A survival" (`.md:252, :394, :428-429`) | Under the three distance-independent stops the study already computes, the gap is **8.8–14.4pp vs C0-take and ~0 or negative vs C0-all** (§3.2 table) | **favours the candidate** |
| **C-2** | "Stop-A survival is ~7–11% for fires before the eventual trough **in every lane**" is a finding (`.md:359-360`) | It is an **identity**. `td_to_trough < 0` ⟺ a strictly lower low prints in (T, T+15]; stop A sits at `P_low × 0.99`; so survival requires that new low to land inside a 1% band. That is why the number is the same in all eight lanes (7.97 / 6.99 / 10.37 / 10.62 / 10.59 / 10.63 / 11.26 / 10.61). It measures the stop pad, not the construction | neutral — deletes a "finding" |
| **C-3** | a "~10pp per-fire residual" in post-trough survival separates the lanes (`.md:358, :361-363, :429-430`) | `R9i` has no `entry_vs_low` conditioning. Standardising every lane to C0-take's entry-distance distribution on the frozen plane: C0-take 88.46% vs C1 81.67 / C2r 81.90 / C4 81.33 — the residual shrinks to **6.6–7.1pp**, ~35% of it was mix. Within the matched (0.02, 0.04] bin the lanes are indistinguishable (76.3% vs 75.2%) | **favours the candidate** |
| **C-4** | the pre/post-trough decomposition is the surviving finding (§A6) | Correct, but it must carry a **"not observable at T"** marker in §A, not only the forward-looking hint at `.md:376-382`. `td_to_trough` (`:635-636`) reads 15 sessions past the fire | neutral |
| **C-5** | §RT: "every finding was reproduced into frozen `R9.*` tables by the study script" (`.md:442-444`) | `.md:458` cites "R4b thinness (month-cluster CI −11.4pp [−19.2,−2.8])". `R4b`'s columns are `['cohort','n','names','near_low_stop%','median fwd10','median fwd21']` — no CI column; `boot_spread_ci` never touches the stop lane; the bounds appear nowhere in `results.json`. −11.4 is the bare point spread (23.64 − 35.02) | against the study's own claim |
| **C-6** | `f_decline_depth` survives as the one "MAYBE" (`.md:326`) | `R9d.C2r`: shipped −13.09, fixed −8% **−16.26**, 2ATR **+8.51**, 3ATR +3.75. A feature that strengthens under a fixed-% stop and *reverses* under an ATR-normalised stop is measuring realised volatility. The two-way flip is closer to a null than a MAYBE | neutral |

Two further minor defects: truncated survival windows (30–41 forward sessions) are pooled with
full ones and bias `survive_a` **up** (`:670-671`, `window_sessions` recorded at `:686` but
never used to filter or weight; ~1.2% of rows); and a hardcoded measurement sits inside a
`deviate()` string (`:1780`, "5926 of C1's 7973 panel episodes (74%)") — currently correct,
stale on any re-run.

**None of C-1..C-6 changes my ruling**, because the ruling rests on (i) the entry-anchored
`footprint R2` median R of −1.0, which has no P_low anchor by construction, (ii) the 2026
excess-return cell, which contains no stop, (iii) the two measured-null second-stage
selectors, and (iv) the live-surface and stage-model defects. C-1 and C-3 do materially soften
the *durability* half of the case, and any launch packet must cite the corrected numbers.

---

## §5 Stage semantics — field-level mapping

### §5.1 Spec stage → payload key → verdict

Source of truth for "what the payload encodes": `site/prophet/index.json` (schema
`prophet.index/v1`, `asof` 2026-08-10, live main) and `engine/prophet_bridge.py`. Where PR
#5370 changes the answer it is marked *(#5370, unmerged)*.

| 04 §3 stage | payload key(s) that could carry it | literal values observed live (n=140 plans) | verdict |
|---|---|---|---|
| **EARLY** | `admission_class` | `early_turn_starter` (**1**), `patience` (14), `confirmation` (9), `null` (**116**) | **PRESENT BUT VESTIGIAL** — 0.7% of the live board |
| **EARLY** (signature) | `early_turn.fired` + `early_turn.reason` | `fired: false` on 23/24 populated rows; reasons `"signature fired but no licensing context — a naked dot is not a starter admission"`, `"signature incomplete: cross_up"`, `"signature incomplete: from_washed"` | **PRESENT, mechanically honest** — refusal reasons are per-name and plain-worded |
| **CONFIRMING** | — | — | **ABSENT.** No key encodes "multiple dimensions are aligning but not complete". The closest is `signal_tier` T1/T2 (29/28 plans, 83 null), which is a confluence-tier, not a lifecycle stage, and 59% null |
| **CONFIRMED** | `admission_class='confirmation'`, `signal_tier`, `confirmed_date` | 9 plans `confirmation`; `confirmed_date` populated on a minority | **PARTIAL** — the class exists; it does not partition the board (116 nulls) |
| **AGING** | `age_days` (median 17, p75 35, **max 164**) | numeric only | **ABSENT as a stage.** Age is a number, never a state. Nothing distinguishes "old but intact" from "stale" |
| **EXTENDED** | `entry_zone_state.state` = `live`/`filled`/`none`; `entry_zone.chase_above`; `entry_status` | `entry_status`: 116 null / 14 `bounce_wait` / 7 `partial` / 2 `buy_now` / 1 `hold` | **PARTIAL AND MISNAMED.** Chase/extension is expressed only as a price level (`chase_above`) and only on the 24 zone-bearing plans. There is no EXTENDED state |
| **INVALIDATED** | `phase='invalidated'`, `recommended_action='invalidated'`, `closed` | `phase`: `triggered_pre_t1` 67 / `pre_trigger` 58 / **`invalidated` 8** / `between_t1_t2` 6 / `at_t1` 1; `closed`: 16 true | **PRESENT** — the one lifecycle stage that is fully implemented |
| — | `signal_provisional` | `null` 113 / `false` 19 / **`true` 8** | present; 8 live plans are provisional and this is not surfaced as a stage |
| — | `integrity_status` | `null` 110 / `audited_current` 27 / `audited_mixed_vintage` 3 | present, mostly null |
| — | `signal_date_basis` | `null` 83 / **`legacy_formation_alias` 30** / `tier_event_date` 27 | **material to §9** — for 30 plans the "signal date" is an alias for the formation date, and for 83 the basis is unknown |
| — | `stage_tilt.provisional` | `true` on every populated row; `eligible: false`; `ec_source_state: 'unavailable'` | see B-11 |
| *(#5370)* | `deck_admitted` vs `fired`; `union_fired`; `licensing_chip`; `stage`; `early_signal_dates` | not on main. `stage` literals `EARLY`/`CONFIRMING`/`CONFIRMED` exist in `STAGE_SIZING_COPY` (`engine/us_early_turn.py:886-887`) but **only `EARLY` is ever assigned** (`:1093`) | adds the deck-vs-fired distinction (which inverts — B-18) and a bucket-last date list. **CONFIRMING and CONFIRMED are declared and unreachable; AGING and EXTENDED are still absent.** No template reads `licensing_chip` |

### §5.2 Verdict on the stage model

**Of the six stages 04 §3 requires, two are implemented (EARLY as a class, INVALIDATED as a
phase), two are partial (CONFIRMED, EXTENDED), and two are absent (CONFIRMING, AGING).** The
spec's central product idea — "the product should represent the lifecycle" (04 §2) — is not
what the payload encodes. The payload encodes an admission decision plus a plan-management
phase machine (`pre_trigger → triggered_pre_t1 → at_t1 → between_t1_t2`), which is a
different and legitimate object, but it is a *trade-management* lifecycle, not the
*evidence* lifecycle 04 asks for.

### §5.3 Display language vs mechanical state

Checked every state-bearing string I could reach. Findings:

1. **`stage_tilt.basis` = "PSQ 2026-07-20 quality re-grade; provisional — forward-shadow
   checked (~2026-12)"** ships on every populated plan. `DNR:HOLD-PSQ-TILT-CLOCK` records
   that this forward shadow **structurally cannot occur** (its sole EC input is gitignored and
   absent on every deploy; the auto-demote clause is "unreachable, not merely unmet"). The
   payload asserts a pending check that the registry says will never happen. **Display
   language outruns mechanical state.** (B-11)
2. **`thesis` opens with `"{ticker} — conviction {score}/100 ({band})"`**
   (`engine/prophet_bridge.py:2649`; ZH `:2754` `确信度 {score}/100`). The live early-turn
   starter reads "EU — conviction 12/100 (neutral) Entry grade: minimal." A single opaque
   0–100 number in user copy is exactly what 04 §5 forbids, and it sits beside a *second*
   blended 0–100 (`management_confidence` 67.9, components `validity/progress/pace/retention/
   overlay`). A 12/100 conviction and a 67.9 confidence on the same card is not
   interpretable. (B-7)
3. **One ranking axis for two lanes.** `_selection_sort_key` (`engine/prophet_bridge.py:589-613`)
   orders every admitted candidate by `us_prophet_v1` priority score descending, falling back
   to legacy conviction. The live `early_turn_starter` plan carries `_priority_score = 69.0`
   with `_conviction_score = 12` — i.e. the early-turn starter is placed on the board by the
   **confirmed lane's** scorer. The design law that the two scores are never blended is
   satisfied in the narrow sense (they are not summed) and violated in the operative sense
   (one axis orders both populations). This is adjacent to `DNR:KILL-PROPHET-POP-MERGE`,
   which forbids "a single blended conviction×timing ranking" on the graded board. (B-8)
   *(#5370 adds `setup_geometry` as the early lane's own ordering key; whether it reaches
   board ordering is the open question the wiring must answer — see §10 J-4.)*
4. **Refusal copy is good.** `early_turn.reason` strings ("a naked dot is not a starter
   admission", "signature incomplete: cross_up") are mechanically exact, plain-worded, and
   carry no falsifier vocabulary. This is compliant with operator law #3821 and is the model
   the rest of the payload should follow.
5. **`gate_go: false` and `authority_tier: "display"` and the `note` field**
   ("DISPLAY-ONLY. All plans are display-tier artifacts. No signal has passed a forward
   ledger gate. The word 'validated' is forbidden in user-facing text.") are present and
   correct at the payload root. The display-only-until-gauntleted law is honored **in the
   payload**. It is not honored on the landing (§7 B-1/B-2).

### §5.4 The wiring PR (#5370) — audited against the stage contract

**What it gets right, and it is not trivial.** Score separation is clean:
`setup_geometry(price_history, asof, *, union)` (`engine/us_early_turn.py:902-903`) takes no
stage and no confirmed-lane score; `stage` is assigned once
(`STAGE_EARLY if union.get("fired") else None`, `:1093`) and consumed only for copy selection
(`engine/prophet_bridge.py:311`). No consumer anywhere ranks or gates on `geometry_score`.
The open-label bug is genuinely **not** inherited: the cross leg maps rows through
`_tf_bars`, whose index is the bucket's last session (`engine/confluence_tiers.py:301-304`),
re-verifies it (`engine/us_early_turn.py:670-676`), and `early_signal_dates` resolves through
`_bucket_last_session` (`engine/signal_quality.py:929`). Fail-closed behavior on the admission
axis is thorough — every absence refuses with a named reason and no path admits on missing
data. `scripts/validate_signals.py` **strengthens** its guard rather than weakening it.

**B-15 (blocker) — a new repaint at the admission layer.** `_tf_bars`/`_tf_grid` emit the
still-open trailing bucket, whose "last session" is only the last session *available*.
Nothing in the new code excludes it, so the docstring's G0.4 claim
(`engine/us_early_turn.py:651-653`, "a 3D event is stamped at the close on which it became
knowable … with no open-label round trip") is false for the live bar. Walk-forward replay on
the PR's **own committed fixtures**: STLD shows 8 fires live and retains 4 (ghosts
2025-08-12, 2025-08-13, 2026-07-10, 2026-07-13); NEM shows 20 and retains 7 (13 ghosts). Each
ghost is stamped `age_bars == 0` → `fired=True` → `deck_admitted=True` → renders
`UNION_CHIP_EN = "Early turn — watch, don't chase"`, and vanishes the next session with no
receipt. **STLD 2026-07-10 is double-stamped** — published as a fire on 07-10 and again at
07-14 when the bucket closes, i.e. the study's own headline example fires twice. No test
covers this: both acceptance exemplars sit on complete buckets, so the provisional path is
never touched. This is the same defect family (`ENTRY_LATENESS_FORENSIC_2026-08-07.md` §1d,
masterplan §6.7) that the PR exists to close, reappearing one layer further out.

**B-16 (blocker) — a scheduled contract red.** `engine/signal_quality.py:937-949` emits
`early_signal_dates` only when every bucket resolves; `research/signal_engine/SCHEMA.json` and
`tests/test_early_signal_dates_contract.py:73` both correctly treat it as optional. But the
PR adds it to `schema_fields`, which `scripts/export_signal_contracts.py:170-180` defines as
**ALWAYS-PRESENT** and explicitly warns "a conditional field belongs in `optional_fields`, NOT
in `schema_fields`, or it flaps the drift lane red↔green with the data". `schema_version`
stays `1.2.0` (`:223`) against the same block's bump rule, and
`site/factordata/contracts/artifact_manifest.json` was not regenerated. All 241 committed
`site/signals/*.json` lack the field. CI is green **only because the manifest is stale**; the
first nightly regeneration yields `removed = ['early_signal_dates']` and a hard exit 1 in
`.github/ci/legacy-jobs.yml:2172` and `.github/workflows/ci-main-heartbeat.yml:97`, neither of
which passes `--warn-only`. This is the append-only-store-pinned-by-equality failure shape.

**B-17 (major) — the shipped deck is not the measured object.** `early_turn_watch.append(...)`
(`engine/prophet_bridge.py:4318-4319`) sits inside the loop over `candidates`, i.e. downstream
of `select_candidates` (`:4018`), which requires `entry_signal` present, `dir` admitted,
`conviction.band != "low"`, `tier_cascade ∈ {T1,T2,T3}` and an admitted `entry_signal.status`
(`:1127-1132`), plus five further `continue`s. The code states the opposite as fact
(`engine/us_early_turn.py:1096-1099`: "it carries EVERY union fire with no context licensing —
the measured coverage/lead numbers are naked-union numbers and a gated deck would silently
under-deliver them"). **The 60.6% recall and 12-session lead were measured on the naked union
over the whole panel; what ships is union ∩ the confirmed lane's admission gate.** Until the
shipped roster is re-measured, those two numbers may not be claimed for the product (§8.2).

**B-18 (major) — the documented deck⊇plan invariant inverts.** `deck_admitted` keys on
`union.fired` alone (`engine/us_early_turn.py:1102`), while `fired` also accepts a
`turn_signature` fire on the daily or 2D grid (`:1047-1058`). On the STLD fixture with a
washed-out basket there are **114 sessions with `fired=True` and `deck_admitted=False`**,
contradicting `engine/prophet_bridge.py:4181-4182`. Those rows are classed
`ADMISSION_CLASS_EARLY_TURN` (`:4321`) with `admission_era: None` and `stage: None` — an
admission class carrying no era stamp, against the law stated at
`engine/us_early_turn.py:617-619` — and `setup_geometry_texture(..., None)` emits no sizing
line on exactly the rows that are starter plans.

**B-19 (major) — a chase verdict off a dead fire, on the wrong rows.** `setup_geometry` keys
on `union.get("fire_date")` and ignores `fired` (`engine/us_early_turn.py:948`), and
`assess_early_turn` passes the live union unconditionally (`:1031-1032`). Measured: STLD at
`asof=2026-06-12` has `union.fired=False` and `fire_date=2026-03-25` (≈2.5 months dead), yet
emits `chase_pct=0.6351` and the chip **"Already run from where it turned — chasing"**
(`engine/prophet_bridge.py:300-302`) — naming a turn no surface shows. Because the
`early_turn` block is unconditional in the plan payload (`:4536-4569`), this rides on **every**
plan, including confirmation-class `buy_now` rows, which additionally receive
"Watch only — not licensed for a starter plan" (`:4568`).

**Major — the tests do not pin what they claim.** 54 collected, all passing, no
monkeypatch-into-vacuity. But: patching both union legs to return `[]` leaves **20 of 42 union
tests green** — `test_cross_leg_requires_both_lines_under_the_band`
(`tests/test_us_early_turn_union_admission.py:62-70`) self-skips via
`if UNION_LEG_CROSS not in out["legs"]: continue`; `test_union_carries_no_quality_or_buy_semantics`
(`:120-124`) asserts `∅ ⊆ anything`; `test_the_deck_roster_is_a_superset_of_the_plan_roster`
(`:438-442`) evaluates only on rows where `plan_licensed` is always `False`, so the implication
is trivially true — and the invariant it claims to guard is the one B-18 shows violated.
The knowability claim rests on **one assertion, one dot, one ticker**
(`tests/test_early_signal_dates_contract.py:117`), NEM is never used by that suite, and
`:109`'s `assert known >= label` is satisfied by equality — i.e. **the open-label bug passes
that assertion**. Regressing the stamp to the open label leaves 10 of 12 contract tests green.

**Major — the guard cannot see the failure it was added for.** `validate_signals.py` checks
format, ordering and count, not the knowability *relation*: a doc whose
`early_signal_dates` equals `early_markers`, and one whose dates are physically impossible
(knowable before the bucket opened), both validate clean. One line
(`early_signal_dates[i] >= early_markers[i]`) closes both.

**Major — the dot leg is silently starved for 120–270 daily bars.** `signal_frame` needs ~90
buckets ≈ 270 daily sessions (`engine/signal_quality.py:178-179`); the cross leg needs 40
buckets ≈ 120 (`engine/us_early_turn.py:649`). Measured on STLD: at 130 and 200 bars the row
reports only `relaxed_cross` and never discloses that the dot leg could not run; at 95 bars
the reason string asserts a *measured absence* — "no washout cross with a 1D confirm, and **no
dot, in this history**" — for a leg that was never computed. This violates the module's own law
(`engine/us_early_turn.py:221-223`: "a starved read and an honest 'not extended' must never be
indistinguishable"). The same silent skip applies to the grid-length mismatch branch (`:716-719`).

**Minor** — `STAGE_CONFIRMING` and `STAGE_CONFIRMED` (`engine/us_early_turn.py:886-887`) are
**unreachable**: no producer assigns them, `STAGE_SIZING_COPY["CONFIRMED"]` is dead copy, and
`tests/test_us_early_turn_union_admission.py:374` exercises it by passing the literal by hand.
**So the missing CONFIRMING tier in §5.1 is not closed by #5370 either** — the constant exists,
the state does not. Also minor: `UNION_1D_RECENT_SESSIONS = 5` and `UNION_1D_WAIT_SESSIONS = 10`
(`:625-630`) are **admission-gating** constants with no provenance and no uncalibrated label,
unlike the display constants beside them; the geometry score is degenerate as an ordering key
(**302 of 400 scored STLD sessions pin at exactly 0.0**, 99 distinct values total, because
`decay_leg` maxes at 45 while `risk_leg` zeroes for any `risk_pct ≥ 0.15`); and the union
suite is appended *after* the anticipation-intake step in the same CI job
(`.github/ci/legacy-jobs.yml:5794-5796`), so an intake red makes the PR's headline proof
invisible.

---

## §6 Product card — 04 §4's ten questions

**Structural finding that must precede the table: there are two different objects called
"Prophet", and the richer one has no first-party UI.**

1. **The board card** — `site/factordata/us_standouts.json`, rendered by
   `templates/_prophet_card.html.j2` inside `dashboard.html.j2` (and mirrored to
   China/HK/Canada/Intl). This is what a visitor to this site actually sees.
2. **The trade-plan artifact** — `site/prophet/{index,showcase}.json`, `plans/*.json` (178
   files), `states/*.json` (159 files), built by `scripts/build_prophet.py` from
   `engine/prophet_bridge.py`. **No template in this repo renders any of its plan-level
   fields** — `thesis`, `entry_zone`, `admission_class`, `what_to_do_now`, `profit_plan`,
   `management_confidence` return zero hits across every `.j2`. Its documented consumer is
   the Terminal (`engine/prophet_bridge.py:1302, :1851`; `scripts/build_prophet.py:1826,
   1917, 1922`), which is the sister repo.

So the card whose contract 04 §4 specifies is assembled **in another repository** from a JSON
contract this repo publishes and never renders. Every stage, freshness and provenance field
below is UI-invisible on this site by construction. That is not automatically wrong — but it
means (a) 04 §9's Prophet-page hierarchy has no page here to apply to, (b) any card-quality
gate must be run against the Terminal, and (c) the two artifacts can drift without any
first-party surface showing it. **This should be the first question the executive asks: which
repo owns the flagship commercial surface?**

Judged against the live payload for the one early-turn starter on the board
(`EU-BULL-20260805`, `site/prophet/index.json`) and the landing card schema
(`site/prophet/showcase.json`).

| 04 §4 question | answered? | evidence / gap |
|---|---|---|
| What is it? | **YES** | `asset`, `direction`, sector |
| What stage is it? | **PARTIAL** | `admission_class` present but null on 83% of the board; no CONFIRMING/AGING/EXTENDED (§5) |
| Why is it here now? | **PARTIAL** | `thesis` carries drivers, but opens with an uninterpretable "conviction 12/100" and mixes event-edge prose with basket cautions |
| What changed? | **NO** | No delta field anywhere. `state.change_reason` exists and is `''` on every plan I sampled except `price_history_unavailable`. 04 §9's "Today's state: new / advancing / confirming / aging / invalidated" cannot be built from this payload |
| Is the entry still attractive? | **PARTIAL, and misleading** | `entry_zone_state` answers it well (`live`/`filled`/`expired`, `stance`, `sessions_remaining`) — on 27 of 140 plans. On the other 113 the reason is literally "plan carries no entry zone (pre-R3 plan)". Meanwhile `entry` = the chase-above price (B-10) |
| What is the risk reference? | **YES** | `invalidation`, `_r_unit`, `state.geometry.dist_to_stop_r`. This is the strongest part of the card |
| What could invalidate it? | **PARTIAL** | A price level, yes. A *condition* ("what we're watching"), no |
| What should the user do at this stage? | **YES** | `what_to_do_now` (EN+ZH) is genuinely good: "Wait for a pullback into the $1.16–$1.17 zone before starting. No entry above $1.31… Starter size only — this is a window, not a certainty." Correct voice, correct hedge, no falsifier language |
| How fresh is the evidence? | **PARTIAL AND UNRELIABLE** | `age_days`, `pulse` ("3d · pre-trigger · awaiting trigger"), `plan_asof`, `price_basis_date` all exist. But `signal_date_basis` is `legacy_formation_alias` on 30 plans and null on 83, and publication lag is unmeasured since 08-07 (§3.3). The forensic §3 already caught this surface reporting `age_days=0, delayed=false` for ~29h against a 7-day-old factor vintage |
| Complete / partial / delayed / reconstructed / provisional? | **PARTIAL** | `signal_provisional` (8 true), `integrity_status` (`audited_mixed_vintage` 3), `source_delayed`, `source_mixed_vintage` exist at root. **There is no `reconstructed` flag anywhere** — required by 04 §7 and by the repaint finding (E25) |

**Card verdict:** the *action* and *risk* halves of the card are launch-quality. The *stage*,
*change*, *freshness-provenance* and *reconstructed* halves are not. A user can tell what to
do; a user cannot tell what state the idea is in or how much to trust its timestamp.

---

## §7 UI / payload blockers (detail)

**B-1 (blocker) — a live "validated" claim on the anonymous landing, invisible to CI.**
`site/prophet/showcase.json` cards carry flag strings including
`"Narrative basket (…) is below its long-term trend — validated drawdown gate: size down…"`
and the ZH `"…已验证的回撤门槛：减小仓位。"`. These render on the public landing:
`templates/index.html:487-507` bakes the `#ph-data` island and live-overrides it from
`prophet/showcase.json`; `templates/index.html:2156-2158` renders `c.flags` into a tooltip.
The rendered `site/index.html:507` contains both tokens today.
**Why CI is green:** `scripts/check_validated_claims.py` `_STRUCTURAL` pattern at line 100 —
`re.compile(r'"(?:absolute_trend_gate|weighting|timing|note)"\s*:.*validated')` — matches, and
`_STRUCTURAL` matches suppress the **whole line**. The `#ph-data` island is a single
22,965-character line that carries a `"note":` key before the claim, so one structural
exemption meant for engine-stamped scoring fields swallows the entire public payload. I
verified the guard exits 0 on this checkout while both tokens are present.
Compounding: `SCAN_GLOBS` (`:66-71`) covers `site/prophet/plans/*.json` but **not**
`site/prophet/*.json`, so `showcase.json` itself is never scanned; and
`engine/prophet_bridge.py:2276-2292` (`_sanitize_thesis_text`) strips exactly these tokens on
the *plan* path — the sanitizer exists and the showcase path does not call it
(`scripts/build_prophet.py:238` `derive_showcase_card`). Classic loud-failure-fixed,
silent-sibling-dark.

**B-2 (blocker) — winners-only public proof.** `site/prophet/showcase.json`:
`kind: "delayed_winners"`, `count: 12`, note "…Selected because they worked; the live board
ships nightly behind registration and includes wins and losses." Builder:
`scripts/build_prophet.py:198-213` — "winners only (ret > 0), ranked by return",
`SHOWCASE_MIN_WINNERS = 6` (fewer than six winners → keep the previous payload, i.e. the
surface cannot go red). 04 §7 requires "wins and losses" and an "aggregate summary with
sample-size disclosure". A disclosure sentence inside a winners-only artifact does not satisfy
a wins-and-losses requirement; and the `SHOWCASE_MIN_WINNERS` fallback means a bad fortnight
is silently replaced by a good one. Additionally the baked island in `templates/index.html`
(as_of 2026-07-06, count 11) is 15 days staler than the live override (as_of 2026-07-21,
count 12) — an anonymous visitor with a blocked fetch sees a month-old teaser.

**B-2b (blocker) — the paid board is a marketing wall, not a gate.**
`templates/dashboard.html.j2`'s board loop (`:15690-16029`) renders **every** row into the
HTML response with no tier condition anywhere in the file. Gating is done afterwards, in the
browser, by `templates/tier_preview.js`: `groups()` (`:75-98`) registers
`add("#us-standouts .nbgrid")` at `:84` and `applyGroup()` (`:198-215`) sets `aria-hidden` and
adds `mx-tier-blurred` / `mx-tier-hidden` classes to nodes **already in the document** with
real tickers, prices and edge scores. `templates/dashboard.html.j2:2130-2132` self-describes
it as "a deliberate skeleton of content that is there, just not yours yet."
The repo's own doctrine forbids exactly this for paid data — `docs/TIER_PREVIEW_PATTERN.md:18-21`:
hiding rows with CSS or a JS tier check is a marketing wall, the rows are one view-source
away, and if the content is what you charge for then the shipped bytes have to differ. That
doc's own reference-implementation list (`:175-192`) names Special Situations and China
Special Situations as the server-split surfaces; **us_stocks/Prophet is not among them.**
This fails 01 §7 ("No client-only hiding of paid rows") and 01 §12's acceptance test
("page source contains no locked rows"). Related: `/prophet/index.json`, `/prophet/plans/*`
and `/prophet/states/*` are declared in no public or free tier in `config/site_access.yml`
and fall through to `premium.default_tier: essential` — but only **once `PAYWALL_ENABLED=1`**
(`config/site_access.yml:256-263, 418-420`). Until that flag is on, the complete plan corpus
is static JSON at a predictable path. A tier audit of the actual served bytes in all four
access states is a launch precondition, not a nice-to-have.

**B-6 (major) — two disagreeing published track records.** `site/us_track_record.html`
publishes 59% / +0.5% avg / 256 finished trades from 11 board days (board ledger,
`data/us_board_ledger/retro_grades.parquet` via `scripts/build_track_record_page.py:44`).
`site/prophet/index.json.record` publishes 28 rows / 11 quarantined / 17 scored / 7 wins /
41.2% / +3.77% (plans ledger). These are different populations of the same product in the
user's mind. Whichever is chosen for the proof board, the other must be relabeled or removed.
*Credit where due:* the track-record page is the best truth surface in the repo — it prints
the CI, the board-day count (the honest-N denominator), the in-flight exclusion, and an
era-break comparison that "invites comparison, refuses a verdict"
(`templates/us_track_record.html.j2:55-68, 186-196, 229-245`). It is the model for §9.

**B-7 (major) — opaque blended numbers.** §5.3(2). `engine/prophet_bridge.py:2649/:2754`.

**B-8 (major) — one ranking axis.** §5.3(3). `engine/prophet_bridge.py:589-613`.

**B-10 (major) — `entry` is the chase line; zones on 27/140.** §3.3, §6.

**B-11 (major) — unreachable-check language in the payload.** §5.3(1).

**B-14 (major) — a performance verdict scored on a different methodology.** The track-record
dialog renders the verdict string **"Worth following — wins are outrunning stops."**
(`templates/_track_record_dlg.html.j2:469`). It is computed from `factordata/us_track_ledger.json`
(`engine/track_scoring.py`) under a next-bar-fill / 10-session-horizon /
StochRSI-overbought-exit / 90d-trough-stop rule (`templates/dashboard.html.j2:16226-16233`) —
**not** Prophet's own trigger/T1/T2/invalidation management
(`engine/prophet_management.py`) and **not** `data/prophet/ledger.jsonl`. A user reads it as a
verdict on the product they are being sold. Either the rule becomes the product's rule, or the
verdict string goes.

**Minor / nit**
- `plans_sort_key` prose is exposed in the public payload and names the internal era
  `us_prophet_v1` — a raw internal identifier on a user-reachable surface (design doctrine
  banned-vocabulary law).
- `showcase.json` cards publish `edge` (19–100) and `stage` (0–3) as bare integers with no
  legend — two more untranslated stats on the most public surface in the product.
- 3 of 140 plans carry `management_status: "unavailable"` / `change_reason:
  "price_history_unavailable"` and still render as plans.
- Tier-name drift: `templates/plans.html.j2:436,464` and `templates/tier_preview.js:19,26` say
  **Essential**; `docs/TIER_PREVIEW_PATTERN.md:132,139` and `config/site_access.yml:362` still
  say **Insider**. `tier_preview.js:14-19` documents the wire-value hazard explicitly — a
  far-future-cached copy must not lock a paying visitor into the 3-row cap. 01 §8 requires
  this reconciled before launch.
- `site/prophet/index.json.record` (the 41.2% block) and `data/prophet/ledger.jsonl` have
  **zero downstream consumers** in `scripts/`, `templates/` or `engine/` — the product's own
  forward ledger is dark data with no surface.

**Credit — two things the UI already gets right and the proof board should inherit:** the
Edge/Priority tooltip states plainly *"It is not a win probability"* / *"it is not a win rate"*
(`templates/dashboard.html.j2:16012-16017`), and the refusal shelf's lede is
*"Watch — don't chase. Each rejoins the board when its setup completes."*
(`templates/_prophet_receipts.html.j2:135`) — correct voice, no falsifier vocabulary,
window-not-certainty framing already in the house idiom.

---

## §8 Claims

### §8.1 Claims ALLOWED at launch (each traceable to a frozen table)

1. "The early-turn deck surfaces names a median **12 sessions** before the confirmed board
   does, on **60.6%** of confirmed setups." — `bakeoff R2i`. Must be stated as *relaxed-form*
   coverage; the charter-literal form covers 25.0% (`R9b`). **SUSPENDED until B-17 is fixed
   or re-measured**: those numbers describe the naked union over the whole panel, and the
   shipped `early_turn_watch` roster is union ∩ the confirmed lane's admission gate
   (`engine/prophet_bridge.py:4018, :4318-4319`). Until the shipped roster is re-measured,
   this claim describes something the product does not do.
2. "Early-turn candidates are surfaced a median **+5.0%** above their decline low, versus
   **+10.3%** for the confirmed board." — `bakeoff R2a`/`R9h`. Must carry the measured ambient
   base (24.7% near-low, `R9g`) if a near-low RATE is quoted.
3. "Most early-turn fires do not work out: about **1 in 2** hits its stop within 42 sessions,
   and the typical single fire loses." — `footprint R2` (56.5% on the primary basis; median R
   −1.0). This is a *required* claim, not merely an allowed one.
4. "About **1 in 3** early-turn fires happens before the low is in; those survive roughly
   **1 time in 10**." — `bakeoff R9i` (35–42% pre-trough; 7–11% survival).
5. "Entry zones cut the distance between the published entry and the recent low from a median
   **7.26%** to **2.29%**." — masterplan §6.9 R4 / PR #5007. Allowed only for zone-bearing
   plans, which is 27 of 140 today.
6. "Roughly **1 in 3** structure stops lands within two sessions of a local low — about
   **2.2×** what random timing would give." — `bakeoff R4a`/`R9f`. The null must ship with the
   number.
7. "Measured on 240 US names over ~2,880 name-years; names that delisted before our marker
   store existed are not in the panel." — `bakeoff §6`, `footprint union`.
8. Track record, if published: "59% of finished trades made money, average trade +0.5%, from
   256 trades on 11 separate board days; 262 picks are still running and are not counted."
   — the existing page's own wording, which already meets the bar.

### §8.2 Claims PROHIBITED

1. **Any use of "validated"** (EN) or 已验证 / 经验证 / 经过验证 (ZH) about any Prophet
   output. CI-enforced in principle; currently live in violation (B-1).
2. **Any win-rate, accuracy, or hit-rate claim for the early/union lane.** No win rate exists
   in the frozen tables; the brief's "46.1%" is a stop-out share (§2.1). Prohibited until W7
   forward grades exist on the union era stamp.
3. **Any expectancy, "average return", or R-multiple claim for the early lane** that omits
   the negative median. Mean-only quotation of +0.36R is prohibited.
4. **Any claim that the early lane beats the market.** 2026 excess is −2.2pp @21d and −4.4pp
   @42d (`R2h`).
5. **Any durability, reliability, quality-tier, or "high-conviction early setup" language.**
   Every static durability feature is retracted or null (E16–E19). No feature licenses a tier.
6. **Any claim that the system "catches the bottom" or "gets you in at the low."** The
   pre/post-trough split is ex-post (§4.3) and 35–42% of fires precede the low.
7. **Any reuse of the repeat-fire / "no failed dot recently" chip** — retracted look-ahead
   (`R9c`). It must not reappear as copy, a badge, or a sort key.
8. **Any theme/basket-breadth confirmation language** ("the whole basket is turning, so this
   is safer") — the measured direction is the opposite (`R3`, §R8).
9. **Any 66.8% / 66.1% coverage-or-win figure** until it exists in a frozen table (§2.1).
10. **Falsifier / refutation / 证伪 vocabulary on any user surface** (operator law #3821) —
    including on the proof board. Verdicts live on the Calibration Lab below the fold.
11. **Any claim built on the plotted dot's proximity.** The chart is a median 2 sessions ahead
    of tradability and 8.6pp better on near-low rate than anything actionable (`R0c`).
12. **Any implication that a published timestamp is when the idea became available** until
    publication lag is re-measured and repaint is latched (§3.3, B-9).
13. **Comparative claims against any named competitor or index-beating language** in the same
    surface as an ungauntleted signal.
14. **Any "~30pp more durable" / "the confirmed lane survives far better" framing** as stated
    in the bake-off — corrected to 8.8–14.4pp vs the actioned incumbent and ~0 vs the pooled
    incumbent under distance-independent stops (§3.2 C-1). The uncorrected figure is
    stop-width arithmetic and must not be quoted in either direction.
15. **Any claim that "pre-trough fires survive only 1 in 10 *because* they are early"** —
    that constancy is the 1% stop pad (§4.6 C-2). The honest form is descriptive: "fires that
    happen before the low is in usually stop out."

---

## §9 Public Proof Board — exact schema

Purpose per 04 §7: a marketing and trust surface, not the live paid board. The schema below
is written to be *safe under the defects that currently exist* — i.e. it forces reconstructed
and lag-affected rows to be labeled rather than assuming the defects are fixed first.

### §9.1 Record schema (one resolved call)

```
prophet.proof/v1
  # identity
  ticker                 str
  name                   str
  sector                 str        # EN + zh pair
  market                 "US"
  # origination — every date is a KNOWABLE date (§6.7 law); no bucket-open labels
  originated_on          date       # the session on which the call became knowable
  originated_basis       enum {tier_event_date, bucket_last_knowable, legacy_formation_alias}
  published_on           date       # when the artifact carrying it was actually served
  publication_lag_days   int        # published_on - originated_on; NEVER omitted
  provenance             enum {live, reconstructed}     # REQUIRED (04 §7)
  reconstructed_reason   str|null   # non-null iff provenance == reconstructed
  # state at origination — frozen, never re-derived
  stage_at_origination   enum {early, confirming, confirmed}   # once §5's gaps are closed
  admission_class        enum {early_turn_starter, patience, confirmation}
  thesis_at_origination  {en, zh}   # the exact visible thesis, verbatim, no re-render
  risk_reference         {entry_basis, entry_zone_low, entry_zone_high, chase_above,
                          invalidation, r_unit}
  # outcome
  horizon_sessions       int        # fixed per methodology version
  exit_rule              str        # plain words, e.g. "sold 10 sessions later, or sooner if it runs hot or breaks its base"
  entry_fill             {price, date, basis}   # next session's close, stated
  exit_fill              {price, date, reason enum {horizon, stop, target}}
  result_pct             float
  result_r               float
  outcome                enum {win, loss, flat, stopped}
  path_summary           {mfe_pct, mae_pct}
  current_status         enum {resolved, resolved_and_still_held, superseded}
  # governance
  methodology_version    str        # e.g. "union-admission-v1-2026-08-11"
  era_at_origination     str        # selection_era on the day
  publication_delay_days int        # the fixed delay this row was released under
```

### §9.2 Aggregate schema (the only place a rate may appear)

```
prophet.proof.aggregate/v1
  window                 {from, to}
  methodology_version    str
  n_resolved             int
  n_distinct_board_days  int        # THE honest-N denominator — never omitted
  n_in_flight_excluded   int
  n_quarantined          int        # + quarantine_reasons[]
  win_rate               float
  win_rate_ci            [lo, hi]   # REQUIRED whenever win_rate is shown
  avg_result_pct         float
  median_result_pct      float      # REQUIRED beside any mean
  stop_out_rate          float
  by_stage               [{stage, n, win_rate, ci, median_result_pct}]
  by_provenance          [{provenance, n, win_rate, ci}]     # live vs reconstructed, split
  survivorship_note      {en, zh}   # names absent from the panel, in plain words
  disclosure             {en, zh}   # display-tier, no forward-ledger authority
```

### §9.3 Publication rules

1. **Fixed delay.** ≥ 10 trading sessions after resolution, applied uniformly. The delay is a
   published field, not a policy note.
2. **Wins AND losses, from the same selection rule.** The set is "every call resolved in the
   window", not "the ones that worked". If the count is small, publish the small count — the
   `SHOWCASE_MIN_WINNERS` carry-forward behavior (B-2) must be deleted, not re-tuned.
3. **Reconstructed rows are labeled and segregated in the aggregate** (`by_provenance`). Until
   the repaint latch lands (E25), rows originated before the latch are `reconstructed` by
   default — the forensic proved that surviving history is optimistic about live earliness.
4. **`publication_lag_days` is mandatory on every row.** A median-5-day lag (E24) is the
   difference between an honest and a dishonest proof board, and it is currently unmeasured.
5. **Every rate carries its CI and its distinct-board-day denominator.** The existing
   track-record page already does this; the proof board inherits the pattern, not a new one.
6. **No falsifier vocabulary** (law #3821). A loss is "stopped out" / "did not work", never
   "refuted" / "证伪". Full verdicts stay on the Calibration Lab below the fold.
7. **One aggregate per methodology version**; an era change starts a new series beside the
   old one (the `us_track_record` era-break pattern), never a silent re-basing.

### §9.4 Prohibited on the public proof board (04 §7 + house law)

The complete current live board; all live entry zones; all current exact stops and targets;
internal feature weights or any component score (`edge`, `management_confidence`, `conviction`,
`_priority_score`, `stage_tilt`); private research notes; unpublished model experiments;
refusal receipts for current names; the `intake` block (`refused_*`, `admitted_by_class`);
any un-resolved current call; any name whose row would be the only row in its cell.

---

## §10 Implementation jobs (filed, not built)

Owner lane per `06_EXECUTION_DOCKET…` §3 and CLAUDE.md §Model routing. Sizes are rough.

| id | job | owner lane | size | gate it clears |
|---|---|---|---|---|
| **J-1** | Close the `check_validated_claims` `_STRUCTURAL` hole: make `"note":`-style patterns mask **in place** rather than kill the line, add `("site/prophet", ("*.json",))` to `SCAN_GLOBS`, and route `derive_showcase_card` flags through `_sanitize_thesis_text`/`_zh`. Add a mutation test that plants the token in a single-line JSON island and asserts red | Codex (tests + guard) | S | B-1 |
| **J-2** | Replace the winners-only showcase with a wins-and-losses delayed slice per §9; delete `SHOWCASE_MIN_WINNERS` carry-forward; re-bake the `#ph-data` island in the same PR (paired plain-copy law) | Codex | M | B-2 |
| **J-3** | Implement the missing stages: `CONFIRMING` as a first-class `admission_class`, `AGING`/`EXTENDED` as derived states with published thresholds, and backfill `admission_class` for the 116 null plans (or mark them `legacy` explicitly) | Opus `builder` on a Fable/`designer`-pinned state spec | L | B-5 |
| **J-4** | Enforce two-axis ordering: early-turn starters ordered by `setup_geometry` only, confirmed plans by `us_prophet_v1`, **never interleaved on one list**; stage must not enter either score. Add an order-invariance test per lane | Opus `builder` | M | B-8, `DNR:KILL-PROPHET-POP-MERGE` |
| **J-5** | Rename/repair the entry contract: `entry` must be the zone, not `chase_above`; add `entry_semantics` enum; backfill zones for the 113 pre-R3 plans or mark them `zone_absent` in the card | Opus `builder` | M | B-10 |
| **J-6** | Delete `management_confidence` from the published payload and the `conviction NN/100` prefix from `thesis` EN+ZH; replace with the 04 §5 separate axes (signal quality / entry geometry / stage / chase / stop distance) as named states, not numbers | `designer` (copy) + Opus `builder` | M | B-7 |
| **J-7** | Re-measure publication lag with a committed, replayable instrument (pinned plan + price manifest) — the forensic's own 08-09 boundary says none exists — and land the PIT latch so a fired event cannot be un-fired | Opus `builder` + `reviewer` | L | B-9, §9.3(3)(4) |
| **J-8** | Build the proof-board producer to §9's schema, sourcing one ledger only, with `provenance`, `publication_lag_days`, CI and distinct-board-day denominators mandatory; retire or relabel the second track record | Codex (data contract) + `designer` (surface) | L | B-2, B-6 |
| **J-9** | Strip `stage_tilt`'s "forward-shadow checked (~2026-12)" basis string and replace with the `DNR:HOLD-PSQ-TILT-CLOCK` state ("frozen; the check that would advance it cannot run on this deploy") | Opus `builder` | S | B-11 |
| **J-10** | Add the missing launch-evidence cells: a regime breakdown (not just a 2026 cell), a sector/theme breakdown, and a delisted-name control panel or an explicit statement that one is unavailable | Opus `reviewer` (measurement) | L | 04 §6 |
| **J-11** | Replay the union lane against ASTS, GPCR, SKY, VSEC, XPEL, NGVT — the six names in the original 2026-08-07 escalation — and publish the surfacing date and % off low for each | Opus `reviewer` | M | §0.1(b) |
| **J-12** | Add dedup-rule and clustering sensitivity to the headline lane tables (currently `R9j` covers one lane's near-low column only; no headline CI anywhere) | Opus `reviewer` | M | §4.4(d)(e) |
| **J-13** | Tier enforcement: **split the board payload server-side** so anonymous/Free bytes do not contain locked rows (the Special Situations pattern in `docs/TIER_PREVIEW_PATTERN.md:175-192`), and prove anonymous/Free cannot reach `prophet/index.json` / `plans/` / `states/` independent of `PAYWALL_ENABLED`. Live browser verification in all four access states | Codex | L | B-2b, 01 §7, §12 |
| **J-14** | **Exclude the incomplete trailing 3D bucket from union admission**, or emit it as an explicitly `provisional: true` deck row that can never mint a plan and is receipted when it withdraws. Add a walk-forward ghost test on both fixtures asserting the live fire set is a subset of the final one | Opus `builder` | M | **B-15** |
| **J-15** | Move `early_signal_dates` to `optional_fields`, bump `schema_version`, regenerate `artifact_manifest.json` in the same PR; add the knowability-relation assertion (`early_signal_dates[i] >= early_markers[i]`) to `scripts/validate_signals.py:153-161` | Opus `builder` | S | **B-16** |
| **J-16** | Re-measure recall and lead **on the shipped roster** (union ∩ `select_candidates`), or move the `early_turn_watch` append upstream of the gate so the deck is the measured object; correct `engine/us_early_turn.py:1096-1099`'s comment either way | Opus `reviewer` + `builder` | M | **B-17**, §8.1(1) |
| **J-17** | Fix `deck_admitted` to key on the same predicate as `fired` (or rename both), era-stamp every `ADMISSION_CLASS_EARLY_TURN` row, and gate `setup_geometry` on `union["fired"]` rather than `fire_date` so a dead fire cannot emit a chase chip; scope the `early_turn` payload block to early-lane rows | Opus `builder` | M | B-18, B-19 |
| **J-18** | De-vacuum the union test suite: delete the self-skipping `continue` guards, replace `∅ ⊆ anything` assertions, make the superset test run on rows where `plan_licensed` can be true, add a NEM knowability pin and a ≥2-dot case, and change `assert known >= label` to a strict inequality where the bucket has >1 session. Target: patching both union legs to `[]` fails every behavioral test | Opus `builder` | M | test integrity |
| **J-19** | Disclose leg starvation: when `signal_frame` cannot run at the given history depth, the row's reason must say the dot leg was **not computed**, never "no dot in this history" | Opus `builder` | S | starved-vs-null law |
| **J-20** | Add the three distance-independent survival columns to `r9_metric_row` (`:1186-1196`), the entry-distance-standardised post-trough comparison, headline-table CIs with a block length ≥ the outcome window, a per-name-first C0-take row, and a %D<20-conditional near-low null. Correct or withdraw the unreceipted `R4b` CI in §RT | Opus `reviewer` | M | §4.4(a)(c)(e)(f)(g), §4.6 |
| **J-21** | Re-freeze §8 as its own pre-registration with a commit that predates its results, and record `charter_sha` in `results.json` | Opus `reviewer` | S | §4.5 |

---

## §11 Largest strengths and largest failure modes

### §11.1 Largest strengths

1. **The measurement discipline is genuinely excellent** and better than most published
   quant work I have reviewed. Charters frozen pre-results with recorded SHAs; deviations
   named rather than absorbed; a red-team pass that **retracted the study's own headline
   finding** as a look-ahead artifact (`R9c`) and rewrote the verdict section around the
   correction; three independent stop bases; a mandatory within-entry-distance-quintile
   column on every feature row; and `R8b`, which isolates a −7.06pp effect as pure
   re-anchoring artifact. The house's three artifact classes are handled (§4.4).
2. **The nulls are printed, not hidden.** Theme breadth, the whole footprint battery, both
   patience policies, every static durability feature — all null, all published, all with the
   pre-stated read criteria attached. `DNR` rows and the ORE law are cited correctly.
3. **The geometry improvement is real and it reproduces in the current regime.** 12 sessions
   and ~5pp of entry distance are not marginal, and `R2h` shows the pattern holding in 2026.
4. **The entry-zone machinery is the program's best shipped asset** (7.26% → 2.29%) and it
   fixes lateness by *mechanics*, independent of the signal debate.
5. **Refusal receipts and the payload's own display-tier disclosure** are exemplary: per-name
   plain-word reasons, `authority_tier: display`, `gate_go: false`, and an explicit note that
   no signal has passed a forward-ledger gate.
6. **The existing `us_track_record` page already meets the honest-proof bar** — CI, board-day
   denominator, in-flight exclusion, era-break comparison that refuses a verdict.

### §11.2 Largest failure modes

0. **The research quality and the wiring quality are far apart, and only the research was
   red-teamed.** The studies retracted their own headline finding under adversarial review;
   the wiring shipped a fresh repaint, a scheduled contract red, an inverted invariant, a
   chase chip off a dead signal, and a test suite in which 20 of 42 union tests pass with the
   union returning nothing. **Whatever review process was applied to the measurement was not
   applied to the code.** That asymmetry, not any single defect, is the thing to fix first.
1. **The product's core value proposition is not mechanically monetizable, and the studies
   prove it.** Median R is negative on the entry-anchored basis, both measured second-stage
   selectors are null, and the separating variable is ex-post. The honest product is a *watch
   deck*, and a watch deck is a different commercial object from a signal service.
2. **Live public surfaces violate house law today** (B-1, B-2) — and one of them is invisible
   to the guard that exists to catch it.
3. **The stage model — the spec's central idea — is mostly absent** (B-5), and the payload's
   lifecycle is a trade-management machine wearing a stage-model label.
4. **Timestamp integrity is unresolved.** Repaint unfixed, publication lag unmeasured since
   08-07, `signal_date_basis` an alias on 30 plans and unknown on 83, the chart 2 sessions
   ahead of tradability. Every one of these is fatal to a proof board specifically.
5. **Forward evidence is empty** while the spec says forward evidence outranks backtests.
6. **Two published track records disagree** and neither is the proof board (B-6).
7. **Concentration risk in the evidence base:** 240 names, one market, ~12 years, 11 board
   days behind the live record, survivorship-tinted, no delisted control, no clustering
   adjustment on headline means.

---

## §12 Final recommendation

**PRIVATE BETA ONLY.**

Sequence I would hold the executive decision to:

0. **Before #5370 merges at all:** J-14, J-15, J-17, J-18. B-15 (ghost fires) and B-16
   (scheduled contract red) are merge blockers, not launch blockers — the first puts a repaint
   into the nightly, the second reds main on the next manifest regeneration. #5370 should be
   held, not armed, until J-14 and J-15 land in it.
1. **Immediately (not beta-deferrable, live defects on anonymous surfaces):** J-1, J-2, J-9,
   J-13. Until these land, the public landing teaser and the public proof surface should be
   withdrawn.
2. **Beta entry:** J-4, J-5, J-6, J-16 plus a hard server-side entitlement gate. Beta cohort is
   named, consenting, and logged in; every card carries the §8.1(3) required claim ("about 1 in
   2 hits its stop; the typical single fire loses") at glance tier, in the `what_to_do_now`
   voice that already exists.
3. **Beta exit gate (all must hold):** J-3, J-7, J-19, J-20 landed; ≥ 6 weeks of W7 forward
   grades on the `union-admission-v1-2026-08-11` era stamp (i.e. not before ~2026-09-30);
   J-8's proof board passing a truth review; J-11's exemplar replay showing the union lane
   covers the original escalation names; and a re-read of `R2h`'s excess-return cell on fresh
   data.
4. **Broad launch decision returns to Sol** with those artifacts. Nothing in this document
   authorizes broad launch, and nothing here promotes any signal to authority.

**One question for the executive that this review cannot answer:** §6's structural finding is
that the flagship commercial surface — the card whose contract 04 §4 specifies — is assembled
in the Terminal repo from a JSON contract this repo publishes and never renders. Every stage,
freshness and provenance field audited above is UI-invisible here. Deciding which repo owns
the launch surface is a prerequisite for scoping most of §10.

**Standing note for whoever ships the copy:** the honest sentence for this product already
exists in the payload and should be the headline, not the disclaimer —
*"Starter size only — this is a window, not a certainty."*
