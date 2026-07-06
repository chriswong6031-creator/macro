# Long-Hold Masterplan — PROPOSED AMENDMENT LH-R11: multiple at-entry families vs `missed_hold`

**Status:** PROPOSED — for operator/Fable ratification. Rev 2 (Opus red-team applied). Not in force until merged into `LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md §3`.
**Trigger:** the washout-timeframe proposal + its red-team exposed a governance gap (how many feature families may probe one label + program-wide FDR + restriction-of-range).
**Author:** orchestrator. **Ratifier:** operator / Fable.
**Rev-2 corrections (Opus red-team, evidence-grounded):** (i) W1's fundamental family has ALREADY run OOS and G1 was ruled **DEFERRED** (`W1_KILLTEST_RESULTS.md` §12, 2026-07-06) — the roster-freeze logic must reckon with that; (ii) the entry selector is `engine/coiled.py:116` `washout_ctx` = a **daily ≥15%-from-126d-high** condition + **3D** StochRSI (`confluence.py:218`) — it does NOT condition on monthly/weekly StochRSI, and `entry_intel/P2_5_INTERACTION_PREREG.md` proves depth varies richly within entry fires. So blanket inadmissibility was wrong; R11.3 is now per-feature.

## The gap

The masterplan governs FDR *isolation* (LH-R5) and effective-n (LH-R4) but not: (1) how many feature families may test the same `missed_hold` outcome; (2) a program-wide correction across families; (3) restriction-of-range / the firewall gap when a family reuses the entry vocabulary.

## LH-R11.1 — Fixed roster + calendar freeze anchor + DEFERRED window

The set of at-entry feature families permitted to test `missed_hold` is a FIXED, pre-registered roster (**current: { fundamental (W1 OBJECTIVE §5) }**). A **family** = a pre-registered fixed feature list with a shared data vocabulary and a single sub-`fdr_family` id; dropping a low-coverage feature (per OBJECTIVE §5's 20% rule) does NOT create a new family, adding any feature does.

**Freeze anchor (not a first-to-OOS race):** the roster freezes at the **commit of the OOS-analysis script** for the operative OOS window (mirrors OBJECTIVE §7 lock semantics), NOT at whoever touches OOS first. **DEFERRED does not consume the one-shot:** because W1's G1 was DEFERRED (honest-OOS n-floor unmet → no KILL/SURVIVE verdict issued → the label was not meaningfully adjudicated), the roster window remains **OPEN** until the **G1-RETEST (Amendment A2, OOS-2 2025+ cohort)** analysis script is committed. A family may still be added (by amendment) before that commit. At that commit the roster freezes and every registered family enters the program-wide search-width (R11.2). *Anti-abuse: the freeze is a calendar/artifact event (the A2 script commit), removing the incentive to rush or stall OOS.*

## LH-R11.2 — Program-wide FDR (sole ratifying correction)

Program-wide **Harvey-Liu-Zhu / BH-FDR (q=0.10)** over **Σ registered hypotheses across all frozen-roster families** is the **SOLE ratifying** correction. Search-width Σ counts hypotheses **at registration** (dropped-for-coverage features included in the denominator, as W1's fundamental m was handled). Within-family q becomes **descriptive**, not a second gate (per the Oracle HLZ house precedent, `ORACLE_CONSTITUTION.md:8` — "search width attached"; inherit its "one gauntlet shot, registration merged before any result" discipline). OBJECTIVE §6.4's per-feature reshuffle null remains an **orthogonal** hurdle (unchanged). A feature must clear (1) its reshuffle null AND (2) the program-wide HLZ correction. A feature that clears its within-family q but fails the program-wide correction is `program_fdr_marginal=True` → **routes to NOT-SURVIVE = KILL or DEFERRED per the n-floor logic** (positive routing, mirroring OBJECTIVE Amendment A1's KILL/SURVIVE/DEFERRED table — never an ambiguous middle state).

## LH-R11.3 — Per-feature admissibility (keyed to the actual selection variable)

The entry population is selected by `coiled.washout_ctx` (daily ≥15%-from-126d-high) + 3D StochRSI. Admissibility is judged **per feature** against that selection, not blanket:

- **Inadmissible:** any feature that re-expresses the *daily washout-proximity selection flag itself* (a near-constant on this population → genuine range collapse).
- **Admissible with `restricted_range` (left-truncation) stamp:** depth-magnitude features (`pct_below_200dma`, `drawdown_from_52wk_high`, `mtf_washout_count`) — left-truncated at 15% but demonstrably variable above it (P2.5 evidence). Interpretation is **direction-only**, and the survivorship **sign-flip** on depth (deep-washout traps are the missing dead names) routes any positive survivor-only result to DEFERRED (never SURVIVE).
- **Admissible (least confounded):** monthly/weekly-timeframe features (`stochrsi_m_k`, `washout_m_active`, `washout_w_active`, `ma200_slope_up`, `vel_3m_turn`, `base_length_days`) — NOT the selection variable, so range is essentially free on this population. These are the washout-timeframe hypothesis's headline features and are cleanly testable here.

**Firewall caveat (retained from red-team B2):** because the LH-R1 CI wall guards artifact *output paths*, not feature computation, an admissible entry-vocabulary family carries a manual `feature_provenance` declaration and a human review gate — the CI cannot mechanically prevent the same code being reused on the entry side.

**Optional clean-population alternative:** the operator MAY instead pose the durable-bottom question on a universe-wide washout population. If so, that study needs its OWN pre-registered selection + forking-paths controls (it does not inherit "clean" for free) AND must cross-reference the existing **program-wide kill** on the washout-as-rank-input line (`entry_intel/P2_5_INTERACTION_PREREG.md:230`) — a *different ruler* (252d hold vs stop-out), so permitted, but it must state it is not reopening the killed entry-ranking line.

## Application to the washout-timeframe proposal (corrected)

Under Rev-2, `WASHOUT_TIMEFRAME_HYPOTHESIS.md` is **ADMISSIBLE** on the entry-stack population — its headline monthly/weekly features are the *least* confounded (not the selection variable); its depth features are admissible-with-`restricted_range`-stamp; only a bare daily-washout-proximity flag would be inadmissible (and it proposes none). It may be added to the roster **now** (the DEFERRED window is open, R11.1) as a second family, subject to R11.2's program-wide FDR. **This supersedes the proposal's §0-B3 "not admitted / redirect" framing** (that framing rested on my over-broad R11.3, now corrected). The honest-OOS-n data block (§0-B1) still stands, so like W1 it will most likely **DEFER** until the A2 2025+ cohort matures — but it is admissible, not rejected.

## Recommendation

Ratify **R11.1 + R11.2** (governance — strictly improves rigor). For **R11.3**, adopt the per-feature version (admit the washout family with the stamps) — it is the honest reading of the evidence and preserves a testable question. The washout family then enters the roster as family #2 under program-wide FDR, and runs (or defers) on the A2 2025+ cohort alongside the fundamental family.

---

*PROPOSED amendment, Rev 2. Requires Fable/operator ratification. On ratification, LH-R11 appends to masterplan §3.*
