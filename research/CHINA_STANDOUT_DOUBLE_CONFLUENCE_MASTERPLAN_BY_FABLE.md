# China Standouts × Double-Confluence — close the tailwind-blind gap (masterplan by Fable)

Date: 2026-07-16 · Status: CHARTERED — audit complete; W0/W1/W3 display-tier build authorized;
W2 rank change GATED on W4 forward evidence
Program id: `cn_standout_dblconf` · Siblings: `research/CHINA_PICK_LAB_MASTERPLAN_BY_FABLE.md`
(measurement apparatus), 07-16 entry-stage audit (memory `entry-stage-3d-anchor-2d-lag`)
Operator directive: 2026-07-16 session — "We should be showing the stocks with Double
Confluence Buys from subsectors_china.html in top standout picks… assess integrating Double
Confluence Buys into standout stocks, or improving standout stocks so that it allows in the
stocks like the ones in Double Confluence Buys."

---

## §1 Problem statement and audit (empirical, as_of 2026-07-16 artifacts)

The subsectors_china Double-Confluence board (`engine/subsector_confluence.py
compute_china_ths_confluence()` → `site/marketdata/subsector_confluence_china.json`) surfaces
member stocks whose OWN T1–T4 cascade is buyable AND whose THS concept is a tailwind. The
operator reads these as comparable-or-better than the Standout board's picks — and asks why
they are "not in there."

Joined the live artifacts (both as_of 2026-07-16; 26 double-buy rows, 25 unique tickers) against
`site/factordata/china_standouts.json` (110-row buy shelf, 181 eligible, universe 1436):

| Fate | n | Detail |
|---|---|---|
| On buy shelf, stage ENTRY, **glance-visible** | 1 | 002157.SZ at buy[1] (visible window = first 3 ENTRY cards + china.html hero top-5) |
| On buy shelf, stage ENTRY, **below the fold** | 16 | ranks 8–106; median rank ≈ 55 |
| On buy shelf but stage **RAN_LATE** ("wait for pullback") | 1 | 603236.SS at buy[27] — fresh T2 mislabeled by the 3D-anchored stage clock (see §2 R4) |
| **Eligible but ranked 111–181** → cut by `[:110]` | 5 | 002045.SZ, 002127.SZ, 300459.SZ, 300638.SZ, 603300.SS — all re-verified gate-eligible T1/T2 (ticks ≤1) on the board's own closes; all carry deeply negative residual alpha (α −1.11..−2.49, resid_ann −47..−112%) |
| **Never scored** — history floor + no alpha entry | 1 | 688775.SS: 268 deep bars < `min_days=300` (build_china_library.py:213) and absent from `china_alpha.per_ticker`; gate-eligible T2 on its own series |
| **ADV floor** marginal miss | 1 | 000913.SZ: adv_yi 0.455 < 0.50 floor (engine/china_liquidity.py:33) — working as designed |

Universe coverage is NOT the problem: 916/919 active THS members are inside the standout
universe (`data/china_search/members.parquet` + closes panel). Both boards run the SAME
`signal_gate.gate()` on essentially the same deep closes — eligibility agrees; **ranking,
staging, glance-tier collapse, and two silent single-point exclusions produce the perceived
absence.** Piquant datum: 002045.SZ is simultaneously a T1 double-confluence buy and a
member of the standout page's *laggards* (worst residual-alpha) strip — the two lenses
actively disagree, and today only one of them is allowed to speak in the rank.

## §2 Root causes (bug vs design)

- **R1 — The standout rank is tailwind-blind (design gap, the headline).** `blend_sorted`
  (build_china_library.py:1485, CN_TIER_FRAC=0.30) scores tier weight × setup-score
  percentile + washout/coiled bonuses − extension penalty. NO term reads concept/subsector
  context. This is precisely the hole `engine/subsector_confluence.py`'s own docstring names
  ("a great stock in a sector institutions are distributing into ranks identically to one
  with a tailwind") — closed for the US via that module's board, never wired back into the
  CN standout rank or cards.
- **R2 — Alpha-heavy blend vs A-share reversal doctrine (design tension).** 70% of the blend
  is the setup-score percentile with CN_ALPHA_WEIGHT=0.35 rewarding positive residual alpha —
  a momentum-flavored quantity — on a tape where the CN pick-lab masterplan §1 records
  momentum FALSIFIED and reversion paying. Deep-washout turn names (exactly what the
  cascade × tailwind lens finds) carry the most negative residual alpha and sink to the tail;
  the binary WASHOUT_BONUS (+0.5) failed to save any of the five cut names.
- **R3 — Glance-tier collapse.** ENTRY shelf renders 3 cards before show-more
  (china.html.j2:2527 `data-showmore-rows=3`), hero shows buy[:5]. A 110-row shelf whose
  ordering is R1/R2-shaped means double-buys are "in standouts" yet invisible.
- **R4 — Stage clock 3D-anchor lag.** Verified 07-16 (memory `entry-stage-3d-anchor-2d-lag`):
  ENTRY freshness reads the 3D master marker; fresh-T2 names read RAN_LATE with anti-buy copy.
- **R5 — Silent single-point exclusions.** (a) 300-bar history floor excludes young names from
  ALL shelves regardless of a live fresh cross (subsector side needs only 220 bars on the
  concept index, members even less); (b) the alpha-coverage prerequisite
  (build_china_library.py:1147 — no `alpha_pt` entry → never reaches `cand`) silently drops
  gate-eligible names. Neither leaves a user-visible trace ("nulls printed" violated in spirit).
- **R6 — ADV tradability floor: NOT a defect.** Keep. Marginal misses (000913.SZ) are the
  honest cost of the one data-backed garbage filter; W3 makes them visible instead of absent.

## §3 Rulings

- **R-1 (one rank system).** The standout board keeps ONE page-wide rank
  (memory `china-sector-rotation-ranker`). Double-confluence context enters as badges, a
  context lane, and disclosure — never a second competing sort of the same shelf.
- **R-2 (display ships, rank is gated).** Chips/lanes/disclosures (W0/W1/W3) ship freely.
  ANY change to blend weights, bonuses, admission, or the [:110] composition is a promotion
  and runs through W4's pre-registered forward comparison first. The operator's quality claim
  is treated as a hypothesis to measure, not a fact to encode.
- **R-3 (kill adjacency, cited).** "Gating A-share reversal by subsector state — FALSIFIED"
  killed a VETO construction on the reversal sleeve; an additive tailwind BONUS on the
  standout blend is a different construction — testable, not pre-killed. "Rotation ×
  cycle-position entry-confluence — DON'T-TEST" and "FRESH BUY as a buy edge (#1513)" are
  fenced: W2 tests neither rotation×cycle position nor freshness-as-edge. Nothing here
  re-opens a killed family; kills remain construction-specific.
- **R-4 (plain words at glance).** Lane copy answers "so what": *"has both its own fresh
  buy signal and a rising industry theme"* — concept names bilingual, internal vocabulary
  (T1/T2, alpha_z, blend) demoted to hover/detail per docs/DESIGN_DOCTRINE.md.

## §4 Workstreams

- **W0 — Double-confluence context on the standout board (display, build now).**
  In `build_china_library.py`, read the committed previous-night
  `site/marketdata/subsector_confluence_china.json` (as_of chip; one-session lag disclosed —
  see §6), join `double_buy` + `headwind_warn` by ticker, and stamp matching rows with
  `dbl_conf = {concept, concept_zh, state, reliability, side}`. Render: (a) a tailwind chip on
  matching ENTRY/RAN_LATE cards; (b) a compact **"Double confluence — concept tailwind"** lane
  inside the standouts panel listing the CURRENT double_buy set with each name's board status
  in plain words — on-board rank, or the honest reason it isn't ranked ("young listing — not
  yet scored", "thin turnover", "ranked below the board cut"); (c) reciprocal link from the
  subsectors_china double-buy table to the standout card anchor. Headwind names on the shelf
  get the warning chip too — context cuts both ways.
- **W1 — Visible-window disclosure (display, build now).** A one-line chip row above the
  ENTRY shelf: "N of today's double-confluence names are on this board — M below the fold"
  anchoring to the lane. Option (operator taste, one token): ENTRY `data-showmore-rows` 3→6.
- **W2 — Tailwind-aware rank (PROMOTION — gated on W4).** Two pre-registered candidates,
  graded on forward ledgers vs the incumbent book BEFORE any live re-rank: (a) additive
  `TAILWIND_BONUS = k × subsector_factor` in `_cn_bonus` (same slot as WASHOUT_BONUS; k
  pre-declared); (b) alpha-leg reshaping for turn cohorts — clip the alpha percentile's
  negative extreme for names with fresh T1/T2 + washout_2w (addresses R2 without abandoning
  alpha for trend names). Also weighs same-night wiring (§6). Opens only after W4 accrues
  n ≥ ~30 graded double-buy picks.
- **W3 — Print the nulls (display, build now).** Gate-eligible names excluded by the
  300-bar floor or missing alpha coverage appear in the W0 lane with a "young/unscored" flag
  (never silently absent); ADV-floor names likewise with "thin turnover". No admission change
  to the ranked 110. Also file the 3/919 THS names outside the china_search panel as a
  collector backlog note.
- **W4 — Measure the operator's claim (build now, verdicts later).** Register the daily
  `double_buy` list as its OWN pick-lab book (CN grader, keep-first-permanent discipline,
  same horizon-ladder rulers as the standout book; coordinate with the pick-lab audit fixes —
  CN book first maturation ~07-17, fixes must land first per memory
  `pick-lab-measurement-audit`). This turns "comparable if not better" into a printed
  side-by-side forward record. No authority language until it matures through the gauntlet.
- **W5 — Stage-clock repair (tie-in, separate lane).** The R4 fix (EARLY/FORMING badge or
  pre-ENTRY stage for fresh-T2/T3 currently reading RAN_LATE) is chartered in the 07-16
  entry-stage audit; build there, cross-reference here (603236.SS is the shared witness).

## §5 Measurement

W4 protocol: nightly append of the double_buy set (ticker, tier, concept, state, entry px,
as_of) to a forward ledger; grade at the pre-declared horizon ruler alongside the standout
book; report side-by-side WR / excess / MFE-MAE with nulls printed. Overlap rows (names on
both books) are tagged — the interesting cohort is the symmetric difference. W2's k and the
alpha-clip variant are pre-registered before the first W2 grade is read. No "validated"
claims (CI-enforced) anywhere on the surface until promotion passes.

## §6 Architecture and wiring

Asia-close ordering: the spine (`build_china` → `build_china_library`) runs BEFORE band A's
`subsector_conf_cn` (asia-close.yml:344), so the same-night artifact lands after the library
build. W0 therefore reads the PREVIOUS night's committed JSON — zero render-budget cost, one
Asia session of lag, disclosed via the lane's as_of chip. Same-night alternative (deferred to
W2 evaluation): lift the concept-tailwind map (237 concept-index gates on collected stores —
no build_china dependency) into the spine ahead of the library; budget ~minutes, must be
measured against the render-budget law before adoption. The join itself is a dict lookup —
negligible. Artifacts: no new collectors; one new ledger file under the pick-lab convention
for W4; template work confined to china.html.j2 standouts panel + subsectors_china.js link.

## §8 Kill-registry adjacency (cited at registration)

| Registry row | Why it does not fence this program |
|---|---|
| Gating A-share reversal by subsector state — FALSIFIED (#791 era) | That was a subsector-state VETO on the reversal sleeve. W0 is display context; W2a is an additive bonus on a different book, pre-registered fresh. |
| Rotation × cycle-position entry-confluence — DON'T-TEST | No cycle-position term anywhere in this program. |
| FRESH BUY as a buy edge on Act-Now board — REFUTED (#1513) | No freshness-as-edge claim; freshness stays an admission window, as today. |
| Washout × turn (2W operator seed) — KILLED (#1747) | W2b clips an alpha percentile for an existing-bonus cohort; it does not resurrect the killed 2W washout×turn seed as a signal. |

## §9 Clocks

- W0/W1/W3 first nightly after merge: lane renders, chips on matched cards, as_of chip
  correct, board order byte-identical to pre-change (W2-B invariant assert must still pass).
- W4: first graded rows ≈ first maturation window after registration (~20-25d ruler);
  check the pick-lab audit fixes landed first.
- W2: opens at n ≥ ~30 W4 grades; pre-registration filed before reading any grade.
- Registry hygiene: if W2 candidates FAIL, append construction-specific rows to
  research/DO_NOT_REBUILD.md §2 and regen compiled blocklists in the same PR.
