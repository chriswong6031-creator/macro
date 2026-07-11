# The Oracle Constitution

**Load this document before touching anything under `engine/oracle/`, `scripts/oracle_*`, `data/oracle/`, or any surface that displays Oracle output.** It consolidates every binding ruling from the program's registrations, adjudications, and reviews (P1→P8 + backbone, all 2026-07-04) into one place. Each law cites its source. Changing a law requires a new registration or an operator directive — never a drive-by edit.

## I. The phase system (the exploration/validation resolution)
1. **Tier 0 — generation** (Fable): hypotheses come from mechanism-first reasoning, recorded in [ORACLE_COMPOUND_LIBRARY.md](ORACLE_COMPOUND_LIBRARY.md). Wide search is encouraged.
2. **Tier 1 — screening** (cheap models): compounds are JSON specs in `data/oracle/compounds/registry.jsonl`, executed ONLY by `scripts/oracle_screen.py` through the constrained grammar (`engine/oracle/compounds.py`) — **the causality firewall**. External contributors write SPECS, never evaluation code. Every screen appends a trial-ledger row. Mining is legal *because it is counted*.
3. **Tier 2 — promotion** (Fable adjudicates): the nightly promotion scan flags compounds crossing the floor (|63d effect| ≥ 1% or hit ≥ 55%, n ≥ 100, ≥3/4 eras consistent) into a queue with the **search width attached** (Harvey-Liu-Zhu accounting). One registered gauntlet shot per promotion; the registration is merged BEFORE any result is computed. **Nothing auto-promotes. Ever.**
4. Verdict vocabulary is pre-bound: **VALIDATED / DISPLAY-WITH-EDGE / NULL** (P3 prereg §3). Secondaries cap at DISPLAY-WITH-EDGE. No post-hoc categories.

## II. Truth-in-labeling (the law the factory's own seed broke)
- A compound's narrative (`mechanism_en/zh`, `name`) must describe **what the rule executes**, not the mechanism the author wishes it executed (#1285 review: A1 claimed the routing-matrix construction while running plain opposite-complex rollover — a laundered claim).
- Thresholds are labeled by what they ARE: a fixed scalar proxy is never called "the validated threshold."
- The grammar is intentionally SMALL (6 comparators + `episode_event`). **Grammar additions are reviewed changes**, not conveniences. Breadth semantics count **distinct nodes**.
- Evaluator semantics are part of a trial's identity: the params-hash must include the grammar/evaluator version, else a semantics change silently re-labels old results (W-B4 item).

## III. The evidence hierarchy and its stamps
- Confidence classes (`engine/oracle/contract.py`): `validated | display_with_edge | exploratory | descriptive`, each with lineage to a registration/adjudication. Current display_with_edge set: `entry_onset_21d`, `exit_onset_5d`, the 6 P3b placebo-surviving routing cells — nothing else, and **nothing is `validated`**.
- **Tier-M watermark law** (P3 prereg §1): no headline claim rests on the 2021→ survivorship-flagged panel; watermarks travel inline with the data.
- **R4 bindings** ([P3 adjudication](ORACLE_GAUNTLET_P3_ADJUDICATION.md)): the scored tilt stays config-dark (`oracle.tilt_enabled=false`) until a registered pass; onset surfaces print BOTH S3 error rates from data (never hardcoded); banner language is descriptive only; the Mastermind directive tempers, never directs buys; `engine/masterminds.py` (the cross-asset quant book) is off-limits.
- **Forecast-language ban**: enforced in code (banned-implication keys) — no field implies a forecast without validated lineage.

## IV. The empirical spine (what is actually known, 2026-07-04)
- Confirmed-tier rotation continuation: **NULL both directions** (P3 primaries; the registered expectation was falsified and logged). The edge, where any, lives at **onset** — detection speed with printed error rates IS the product.
- Standalone 2W washout-turn on sector ETFs: **NULL pooled** (P8; loses to the validated `sector_signals` BUY state). The strongest honest cell in the program: washout × opposite-complex-rollover, +1.14% increment vs a size-matched null (P8 cond_b — unvalidated, accruing).
- Routing: 6/90 cells survive the placebo (software→ai_compute the standout); 28 bootstrap rejections were small-n artifacts. Sector personalities are real terrain (XLE washouts +1.79% vs +0.45% pooled) — per-sector claims need their own registration.

## V. Operational law
- **Nightly**: `scripts/oracle_nightly.py`, 12 steps, heavy steps delegate to the canonical CLIs with `--tier all` (Tier M is the alert layer — never Tier-S-only). Loud-error pattern (`::error::` + nonzero exit; later steps still attempt). Payload validated BEFORE write; on failure the prior payload is kept.
- **Staleness** (contract v1.1.0): ≤ 2 *trading* days + 168h hard cap (fixed calendar hours fail every weekend — learned on July-4th weekend).
- **Alerts**: state-diff engines, idempotent ids, **first run seeds silently** (a deploy-day storm is a major). All events bilingual.
- **Additive-only extension**: new nightly steps append at END; new payload fields are additive (tolerant-reader contract); field names avoid the banned substrings; config keys append at END of config.yml.
- **Model routing** (operator directive): Fable = generation/architecture/pre-registration/adjudication; Opus = hard reviews; Sonnet/Haiku = builds and data-grind; **no Codex for Oracle**.
- **Merge discipline**: fresh branch off origin/main; serialized merges when waves share files; inspect the diff-vs-main before merging (a stash-pop once nearly shipped 15 stale site pages); the "Workers Builds: macro" red CI check is a known-spurious auto-detect.
- **Editing law** (self-inflicted, twice): wide anchor-slice edits on big files must anchor on a KNOWN next definition and be grep-verified after — two incidents ate neighboring functions (`compute_cell_stats`; four test fixtures), both caught by NameError.

## VI. Interfaces
- Red Queen consumes `site/basketdata/oracle_state.json` under [docs/ORACLE_RED_QUEEN_INTERFACE.md](../docs/ORACLE_RED_QUEEN_INTERFACE.md) — versioned, confidence-stamped, staleness-contracted. Oracle's role per the P8 verdict: **initiator-class**; the cond_b channel is the named candidate for promotion to confirmer.
- The Time Machine (subsector_rotation.html) is display-only replay; D6 (free vs premium) is the operator's open business call; it ships ungated.

## VII. Amendment log
- 2026-07-04 — v1 authored (Fable), consolidating P1–P8 + backbone rulings at program close.
- 2026-07-11 — Ratio Lens grammar registered ([RATIO_LENS_MASTERPLAN_BY_FABLE.md](RATIO_LENS_MASTERPLAN_BY_FABLE.md), RL-R1..R16): pairwise log-ratio series over a frozen curated pair registry as a new display-tier organ family; ratio-fed oscillator outputs watermarked "not characterized on ratio inputs"; decomposition-in-absolute-returns law; no dispersion gates, no tensor extension, no episode/routing fields; forward ledger `ratio_lens.v1` expected-null.
