# W5 prereg — pre-merge red-team findings and dispositions (audit receipt)

**Reviewed artifact:** the DRAFT `research/live_entry_radar/W5_FORWARD_EVIDENCE_PREREG.md`
before PR-5a. **Reviewer:** independent fresh-context Opus agent (adversarial commission:
contract-contradiction sweep, unfrozen degrees of freedom, mechanical impossibilities,
budget arithmetic, era/holdout defects, statistical design, basis law, completeness).
**Results seen: NONE** — no Radar forward outcome, replay return, MFE/MAE, false-start,
control-excess, or ranking row existed anywhere during the review.
**Adjudicator:** the W5 orchestrator (Fable main loop). All findings folded into the
frozen text **pre-merge** (lawful: the document was a draft until the PR-5a commit; the
prereg's own freeze point is its merge). This file is the §19 receipt.

**Reviewer verifications that found no defect:** all five §11 seeds recomputed and
matched; all six §1 spec hashes matched live `DETECTORS`; the §13 sum was arithmetically
correct pre-revision (129) and is again post-revision (253); Panel-A's 240-name count
confirmed; G-1/G-2 confirmed implementable and non-circular (the two-PR split with
`_UNSET` sentinels); the holdout boundary satisfies "most recent 6 months of replayable
history at first replay" with slack.

## Blockers (5)

| id | finding (compressed) | adjudication → fix in frozen text |
|---|---|---|
| B1 | NC-2 kill arm was definitionally identical to the primary for Q1/Q5 (controls already proximity-matched), so PROXIMITY SHADOW was unreachable on the champion — the one instrument `DNR:KILL-WASHOUT-TURN` mandates; the overlap floor measured control availability, not proximity common support | ACCEPTED. §9 rebuilt as a **matched-vs-unmatched contrast**: the identical machinery re-run with the proximity decile dropped from the CEM cell; shadow = unmatched favorable while matched is not. Overlap diagnostic redefined as the share of candidates whose proximity-UNMATCHED admissible set contains ≥1 same-band member; floor 0.50 → UNINFORMATIVE, never KILLED. `controls.match(match_proximity=False)` implements the companion |
| B2 | Q5's primary could not fail: forward-only matching forced gap ∈ [0,30], median ≥ 0 by construction; a guaranteed rank-1 p also loosened BH for Q1–Q4 | ACCEPTED. §10 Q5 rebuilt: **nearest incumbent fire within ±30 sessions, signed** (negative when the incumbent fired first); PASS requires CI excluding 0 favorably AND point ≥ +2 sessions (pre-registered minimum lead); unmatched candidates counted, +30-lead bounding read declared |
| B3 | Both guardrails structurally unpassable at the §12 floors (order-of-magnitude from price dispersion alone: CI half-widths ≳3–5pp vs margins −1.0pp/+5.0pp) — frozen as pass/fail they were verdicts fixed independent of data | ACCEPTED. Guardrails re-frozen as **three-state** (NON-INFERIOR / INCONCLUSIVE / ADVERSE; EQUAL-OR-BETTER / INCONCLUSIVE / WORSE) with margins unchanged; §0(e)'s measured dispersion (median per-name 10-session SD ≈ 5.7pp) added, and INCONCLUSIVE declared the expected state at floors — stated pre-outcome, not discovered post |
| B4 | The first §16 amendment would change the doc's sha256 and permanently brick gate G-1 — amendments and the hash gate were mutually exclusive | ACCEPTED. G-1 re-frozen as a **frozen-prefix hash**: bytes up to and including the §16 marker line; amendments append strictly after; tamper-vs-amendment now mechanical (`gates.frozen_prefix`), battery §15.C tests both directions |
| B5 | Panel-A's A0 basis was ambiguous (curated total-return ATR vs vendor split-only P0/MAE): one reading mis-scales the false-start threshold ~12–14% on dividend payers (inflating C1/C2/C3 false-start rates — Q3's primary); the other refuses Panel-A wholesale | ACCEPTED. §4/§6: **A0 on the vendor plane on BOTH panels**; per-episode plane-consistency battery row added (`p0_basis`/`atr_basis` one plane or refuse) |

## Majors (13)

| id | finding (compressed) | adjudication → fix |
|---|---|---|
| M1 | Holdout seam understated: {21,15}-session diagnostic horizons touch up to 21 sessions past the boundary, not 10 | ACCEPTED. §1 restates the seam as 10 sessions for every confirmatory primary and up to 21 for the diagnostic cells, disclosed; no holdout-anchored episode enters any read |
| M2 | BH denominator floated with the graded subset (m=3 or 4 when Q4 waits), loosening every threshold; sequential re-reads at growing m are not a valid FDR procedure | ACCEPTED. **m = 5 fixed** in §10 and in `ruler.bh_fdr(m_total=5)`; ungraded questions never shrink the denominator |
| M3 | Floors (30 episodes / 12 months) did not bound the unit of the primary statistic — 2 names could carry an arm | ACCEPTED. Third floor added: **effective-N of distinct names (1/HHI) ≥ 8 per arm** (the contract A2.5.6 instrument); `n_names`/HHI printed with every estimate |
| M4 | LIVE primary window silently narrowed the contract's `(decision, decision+H]` (day-D remainder excluded); return and excursions measured over different windows; false starts understated on the arm side of Q3's own head-to-head | ACCEPTED. §7 window law rebuilt: the **day-0 sampled segment** (the episode's own 5-minute path after T) participates in MFE/MAE and false-start first-touch ordering as position 0; confirmed-bar rows unaffected; battery §15.G proves both |
| M5 | Q3/Q5 named no panel — an exploitable universe degree of freedom | ACCEPTED. Q3 = Panel-A, Q5 = Panel-B, written into the primary-metric sentences |
| M6 | k-NN mechanics under-frozen: no distance cap, unweighted axes with unequal ranges (dollar-vol 9× hotness), undeclared hotness encoding, circular tie-break | ACCEPTED. Axes normalized to [0,1] (decile/9, (quintile−1)/4, hot 0/1), **max admissible L1 distance 1.0**, ties by lexicographic ticker only; k distribution reported |
| M7 | Frozen `make_claim` call omitted required `asof` (TypeError as written); entry-fill session and the qledger price plane were unfrozen/undisclosed | ACCEPTED. §17: `asof` = decision session; qledger fills at the first close strictly after asof (D+1) **on its own curated plane** — a second meter by design, divergence expected and disclosed |
| M8 | The horizon-21 rationale ("off-rung 10 grades only at 5") is false against live post-P0b code — measured `in_scope_horizons(10) == [5, 10]` | ACCEPTED (verified live this session). Registration at 21 stands per the commission; the rationale corrected in §17 (on-rung bracketing + ruler separation); battery §15.L asserts the reconciler registers 21 |
| M9 | Q2's B arm selects on the absence of a future in-window event (episode life ≈ outcome window) — anti-conservative for Q2; direction unstated; "the contract's own frozen contrast" overstated | ACCEPTED. §10 Q2 names the bias direction (upward), adds the budgeted **PIT-clean sensitivity arm** (C2a vs ALL C1, §13 row 17) and an interpretation ceiling |
| M10 | The budget was declared but unenforceable (no cell-name list; `log_trial` never refuses; "undeclared look ⇒ caught" had no mechanism) | ACCEPTED. The **253 cell names ship in `prereg.LOOK_CELLS`** (length-asserted); `gates.check_look_cell` refuses unlisted names; §13/§14 state exactly what is and is not mechanically bounded |
| M11 | The 27-cell grid was under-counted 5× (false starts report per detector; every sibling row carries its detector multiplier) | ACCEPTED. Row 4 = **27 × 5 = 135**; budget re-totaled to 253 |
| M12 | "No outcome-variance estimate exists pre-read" was false — unconditional H=10 dispersion is a §0-class data property, and it would have exposed B3 before freezing | ACCEPTED. Measured (§0(e)): median per-name SD ≈ 5.7pp (IQR 4.7–7.1), seeded 60-name sample; floors/guardrails sized against it; the false sentence removed |
| M13 | Regime tag and C4 strata were precisely defined but budgeted at zero — the most tempting post-hoc slices would have required post-results amendments | ACCEPTED. Budgeted now: regime × 5 detectors (row 18, 10 cells) + C4 recovery-count strata on C2a (row 19, 3 cells) |

*(M14–M18 in the reviewer's numbering)*

| id | finding | adjudication → fix |
|---|---|---|
| M14 | G-5 validates the curated-feed code path while Q1 grades a vendor-plane population; row 16 was pre-disarmed ("cannot alter §10") so no divergence could ever bind; contract gate P-2 undischarged for the graded population | ACCEPTED. Row 16 now carries a **binding ≥90% G0-date-agreement floor**: below it, every Panel-B G0 read (Q1/Q5) reports UNINFORMATIVE. §14 states G-5's green licenses the staged code path, never the Panel-B population |
| M15 | Q5's aggregation was undefined (median of what?) and a pooled median would be the E1 pooled-fire shape | ACCEPTED. §10: per name, median signed gap over its pairs → cross-name mean of per-name medians; bootstrap resamples months recomputing the full two-step |
| M16 | No missing-sector law; `sector_of_ticker` returns None on unmapped names (material on Panel-B) — undefined whether such episodes refuse, drop, or fall back | ACCEPTED. Unmapped-sector candidates are `uninformative_no_control` (counted in the census); unmapped controls never enter a cell; per-panel sector coverage published with every table |
| M17 | The TrialLedger write-site was unfrozen — a sparse-worktree write would truncate the fleet-wide `data/trial_ledger.jsonl` (house-measured hazard) and G-3 would bless the corrupt store | ACCEPTED. §13 names the execution site (this session's full checkout, data/ materialized); G-3 now additionally refuses when the ledger carries **no pre-existing families** (the truncation signature) |
| M18 | The adjudication coverage gate (standards §11.1–.2) had no budgeted place: no motivating-exemplar read, no current-regime out-of-sample statement | ACCEPTED. §18 lead obligation added: every graded question's report leads with the row-20 exemplar read (KRUS/MCK/NVDA/REGN/YELP) and the statement that TEST closes 2026-02-13, so the current regime is out of sample by construction; row 20 budgeted |

## Minors (11)

| id | finding | fix |
|---|---|---|
| N1 | Month-draw count per replicate unfrozen in the doc | "drawn at the observed month count" written into §11 |
| N2 | The p formula could exceed 1 | `min(1, …)` written into §11 (code already clamped) |
| N3 | C32 WITHOUT arm denominator inconsistent between §7 and row 9 | Pinned: WITHOUT = all episodes **within the same cohort** |
| N4 | `_GICS_ETF` cited as a qledger symbol; it is a private re-export from `engine.ai_desk` | Public `control_for_sector`/`sector_of_ticker` cited; home module named as a basis-change tripwire |
| N5 | Zero-control exclusion is survivorship-shaped inside the primary | Bounding read added: primary re-reported with excluded candidates imputed at zero excess, direction stated |
| N6 | k varies 1..5 with no minimum and no precision weighting | k ≥ 1 kept, frozen explicitly; the k distribution reported with every table |
| N7 | G-2 wedges silently on shallow checkouts | Full-history requirement stated; refusal message distinguishes "history unavailable" from "not an ancestor" |
| N8 | Placebo under-pinned (which detector's non-fire; which era; single noisy draw) | Pinned: same detector, candidate's own era, **R = 5** draws averaged per candidate |
| N9 | target-before-invalidation / gap-through-invalidation / ex-div flag had no budget line | Named inside row 6's parenthetical |
| N10 | Decile/quintile reference population and dollar-volume window unstated (two dollar-volume constructs under one name) | Cross-sectional within (panel, session); dollar-vol decile on the same 60-session median basis as the cost tiers |
| N11 | Anchor asymmetry differs in SIGN by detector family (LIVE subject captures P0→close(D); confirmed-bar controls capture the overnight gap) — one "conservative" sentence covered both | Disclosure split by family with each direction named; row 21 budgets the subject-at-session-close bounding read |

## Outcome

All 29 findings adjudicated ACCEPTED with fixes folded in place before PR-5a; no finding
was rejected; no fix required weakening any contract-frozen law — every repair moved in
the strict/conservative direction or made an unreachable verdict reachable. The frozen
budget moved 129 → **253** (grid multiplier, regime/C4/exemplar/sensitivity/bounding
cells). The revised document is what PR-5a merges; this table is the receipt that the
revision happened pre-evidence.
