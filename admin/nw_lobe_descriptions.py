"""Plain-English descriptions for Neural Web lobes (admin Observatory).

AUTO-MANAGED by scripts/nw_lobe_desc_audit.py — do not hand-edit `src_fp`.
Edit a lobe's `short`/`full` prose freely, then run:

    python scripts/nw_lobe_desc_audit.py --update

to re-stamp `src_fp` (the fingerprint of the synapse note the prose describes).

`src_fp` is how the console knows a description is still current: if a lobe's
synapse note changes but this prose isn't refreshed, the fingerprints diverge and
the description is flagged 'stale' in the UI, and tests/test_nw_lobe_descriptions.py
fails CI. A lobe with an empty `short` renders an auto-generated summary until real
prose is written here. Run `--update` (no seed) after adding a lobe or editing prose.
"""
# fmt: off
SCHEMA_VERSION = 1

LOBE_DESCRIPTIONS = {
    "attention-deterministic": {
        "short": "Five rule-based attention items surfaced from structured artifact values — zero AI, display only.",
        "full": "The deterministic attention builder applies five pre-registered template rules: contradiction tension above threshold, a daily-cadence lobe past 1.5 times its SLA, regime confidence below 0.25, the evidence clock overdue, and the cortex run degraded. Items are filled from structured artifact fields, never authored by a language model. The artifact is display-only and never writes to the AI reviewer's earn-in track. Consumed by the committee page and the brief context builder.",
        "src_fp": "1485ea3a668caacc",
    },
    "bottom-sensors-json": {
        "short": "The public-site copy of the bottom sensors data, used for display and debugging.",
        "full": "This is the public-site version of the bottom sensors data, written at the same time as the main data file. It is display and debug only — it does not add any new information beyond what the main data file contains.",
        "src_fp": "76728a9d7cf1a69d",
    },
    "bottom-sensors-parquet": {
        "short": "Daily per-stock sensor readings for the US board — shown for context only, ranks and gates nothing.",
        "full": "Each day this feed gathers sensor readings for each US stock on the board: distance from recent lows and highs, balance-sheet leverage ratios from regulatory filings, and other positioning metrics. It is display-only — it neither ranks stocks nor gates any alert or allocation. Leverage ratios need data still arriving through a weekly refresh, so many are null today. The thresholds defining sensor states are frozen; changing them needs a new record.",
        "src_fp": "43fa427c4b716dd3",
    },
    "capability-audit": {
        "short": "Append-only audit tape of every capability broker call actually used in a pipeline run — no secret values, operator audit only.",
        "full": "The capability broker appends one record each time a capability resolve call is actually used. Each record carries the schema version, event ID, timestamp, run ID, workflow name, actor, commit SHA, capability ID, and lane — never the secret value itself. Used for the weekly operator audit digest and audit-tape link described in the Metabolism masterplan. No consumers are wired beyond operator review.",
        "src_fp": "ef5e40df81ba2ca8",
    },
    "causal-brainstorm-runs": {
        "short": "Run log for each LLM brainstorm invocation — token counts, status, and truncated replies for provenance — display only.",
        "full": "The brainstorm runner appends one record per pack-only or full-mode invocation. Each record holds the pack ID, run status, token counts, truncated raw LLM replies, and trigger metadata for provenance. Infrastructure tier only — never signals, never ranks, never gates any money-path surface. Absent until the first brainstorm run completes.",
        "src_fp": "0702b24ea2f5feb5",
    },
    "causal-confluence-audit": {
        "short": "Directed anti-mirage annotations over the confluence graph: price-derived sibling pairs, shared-parent suspects, and collider-risk warnings — display only, screened not gauntleted.",
        "full": "The anti-mirage auditor (CHF-R10, W6) reads three committed artifacts and applies deterministic rules to produce three annotation categories. Duplicate exposure: pairs of candidate-cause features that share the same price-derived family (breadth, GEX, options entry, momentum, and similar) and may inflate apparent co-firing by sharing a common market-process parent. Shared parent suspect: confirms edges in the confluence graph whose two endpoint engines sit in the same R-ORTH independence cluster and additionally share a common driver family in the causal inventory — flagged as potential shared-parent artifacts rather than independent confirmation. Collider risk: mechanism cards that condition on downstream composites named in the forbidden-causes list (board_rank, final_verdict, and similar), which may open a collider back-door path. No R-ORTH statistics are recomputed (RUL-ORTH-9); no LLM-originated content appears (RUL-ORTH-11); all annotations are deterministic rule applications over committed artifacts. Absent inputs produce empty sections with gap notes, never phantom annotations. The confluence builder stamps matching confirms edges with an additive causal_audit field. The admin Causal Lab panel shows annotation counts and the latest five annotations.",
        "src_fp": "de4ee9f80336560d",
    },
    "causal-edges": {
        "short": "Weekly battery results: one row per screened causal edge with verdict, support, concerns, and cumulative trial-ledger width — screened, not gauntleted.",
        "full": "Each week the causal edge scout runs a bounded battery over the top-priority frontier cells. Each record captures the cause feature, target, environment, lag set, declared environment map, and the full battery of identification tests required by the estimator law: a declared-lag effect estimate, a negative-lag placebo, a time-shift placebo, a circular block bootstrap, an overlap-corrected era split, and environment invariance over the pre-registered split set. Verdict vocabulary covers: screened candidate, era-specific, unstable, insufficient era span, insufficient power, null, and forbidden. The record also carries the cumulative scan family width at the time of scanning, per the launder-proof multiplicity law. Support fields carry weak, medium, or strong per lens alongside a concerns list. The feed never claims causality: the language sanitizer enforces this at write time. Null edges stay in the library and feed the kill mask — they are retained as confluence context, not deleted.",
        "src_fp": "d3841fbbfbca72e2",
    },
    "causal-feature-inventory": {
        "short": "Annotated catalogue of every feature that the causal scout may use as a candidate cause, target, or conditioning variable — display only, screened not gauntleted.",
        "full": "Each night the causal inventory builder reads the causal priors config and probes every registered feature store to produce this catalogue. Each entry records the feature role vocabulary (candidate cause, target, conditioner, environment split, collider, and so on), era coverage, minimum lag constraint derived from publication cadence, PIT basis, and collider risk level. Forbidden-future features are hard-restricted to the target role; features matching the forbidden-causes pattern lose candidate-cause eligibility automatically. The inventory also runs a kill-mask sync check: if the compiled section of the priors config diverges from the current null library, the gap is flagged. All entries are display-only infrastructure. The inventory never ranks anything, never gates any alert, and never escalates any position. It is the input catalogue for the causal edge scout and for the anti-mirage auditor.",
        "src_fp": "fa1f14e841273b38",
    },
    "causal-frontier": {
        "short": "Coverage map of all cause-family by target-family by environment cells, with priority scores and exploration state — the causal scout's agenda.",
        "full": "The frontier ledger maintains one cell for every combination of cause family, target family, and declared environment. Each cell carries an exploration state (unexplored, accruing, screened, null_basin, or killed) and a deterministic value heuristic score that drives which cells the weekly battery tackles next. The heuristic adds bonuses for unexplored cells and data-present features, penalizes null-basin and killed cells, and rewards broader era coverage. The frontier is the machine-owned agenda-setting mechanism: the operator ratifies promotions but does not have to hypothesize. The cumulative causal_scan width is printed on every frontier surface per the launder-proof multiplicity law.",
        "src_fp": "e2610dad74b0ee7d",
    },
    "causal-lab-state": {
        "short": "Nightly CHF heartbeat: funnel counts, cumulative scan width, frontier map summary, surprise queue, and LLM lane status — display only.",
        "full": "Each nightly run of the causal frontier builder assembles this lab state snapshot. It carries the program heartbeat (wave, status), funnel counts (edges by verdict, nulls, mechanism cards by status), the cumulative scan FDR family width (printed on every surface per the launder-proof multiplicity law), a frontier map summary (total cells, cells by state, target families, environments), the surprise queue size and stalest source, and the LLM lane status (awaiting phase A until the operator completes a full triggered cycle with five valid cards and one promoted candidate). Data-absent notes are printed honestly when runner-local stores are unreachable. Nothing in this file gates, ranks, sizes, or escalates any money-path decision.",
        "src_fp": "693255d5fa8e3a39",
    },
    "causal-llm-lane": {
        "short": "Weekly-anchored LLM lane status for the causal brainstorm — armed, degraded, or awaiting Phase A — display only.",
        "full": "The brainstorm runner writes this file on Tuesday nightly runs; every other night a status-only pass refreshes it from config truth without re-running the brainstorm. Statuses are degraded-pack-only, awaiting-phase-a, armed, and ok. The SLA is intentionally lenient at 200 hours because the artifact is weekly-anchored — a Tuesday result is preserved until the ISO week rolls over. Read by the causal frontier engine to wire the lane status block into the lab state. Absent until the first brainstorm run; the frontier falls back to awaiting-phase-a when absent.",
        "src_fp": "c6a1b6fa290565e3",
    },
    "causal-mechanisms": {
        "short": "Mechanism cards proposed by the LLM brainstorm lane — inert drafts with zero authority until a human or the cortex stakes them.",
        "full": "When the LLM brainstorm chain runs (operator-triggered or behind the Phase-A autonomy gate), it files structured mechanism cards here. Each card holds a mechanism story in English and Chinese, a causal graph fragment with cause, target, mediators, confounders, and colliders to avoid, a frozen environment map hashed before any invariance test runs, two or more falsifiers, and a test specification. Cards are inert proposal material until a human operator or the cortex's own server-budgeted staking chokepoint acts on them. No card may transition to a registered or chartered state via an LLM actor — only script or human actors may change status. LLM numeric confidence is forbidden anywhere in this feed. The schema firewall deduplicates and validates every card before filing; an ISO-week idempotent lock prevents double-filing on token-flip retries. All entries are display-only with not_a_signal unconditionally true.",
        "src_fp": "ce2d51b904566ac6",
    },
    "causal-nulls": {
        "short": "Null library: every edge where the scout returned null, forbidden, or insufficient-era, kept permanently as case law and fed into the kill mask.",
        "full": "When the causal scout returns a null, forbidden, or insufficient-era verdict for an edge, the record is appended here permanently. This library serves two roles: it populates the compiled section of the kill mask in the causal priors config (regenerated nightly, CI-synced so newly killed edges cannot silently become proposable again), and it feeds the weekly brainstorm pack so the LLM chain knows what has already been tried. Each record includes the edge, verdict, concerns, and a do-not-repropose field the scout prints when refusing to rerun a killed edge. Null edges are retained as confluence context — a standalone null does not delete the edge from consideration but prevents it from re-entering the scout queue. The cumulative width counter runs over the entire null library, not just recent additions.",
        "src_fp": "0432a241637a062c",
    },
    "causal-surprise-queue": {
        "short": "Unexplained-variance tickets from the MPC pathway miss, MRI release misses, and Oracle episode failures — seeds the causal brainstorm agenda.",
        "full": "When the mechanism-pathways engine emits a no_attributable_driver result, or when the release forecast misses and the Oracle episodes fail to explain the move, a surprise ticket is filed here. Each ticket records the source artifact, the as-of date of that artifact (so the queue knows when a ticket is stale), and a brief description of the unexplained event. The frontier ledger and surprise queue together form the causal scout's full agenda: the frontier decides what has not been explored yet, and the surprise queue elevates specific unexplained episodes that most need a causal hypothesis. Stale tickets are not deleted — they are marked stale when their source artifact is refreshed without explaining the event.",
        "src_fp": "c5256fcf54684fd3",
    },
    "claim-accountability": {
        "short": "A standing audit of signal-claim coverage, gradeability, and maturity across all desks.",
        "full": "After each grading run, this audit summarizes how many claims each desk has made, what share carry falsifiable predictions, how many have matured enough to grade, and how fill conventions have shifted over time. Infrastructure-type claims with no directional prediction are counted separately and not scored for accuracy. Per-source reliability stats can't be built yet because the graded sample is too small. A companion document holds the full methodology.",
        "src_fp": "757860443079a84c",
    },
    "confluence-candidates": {
        "short": "Statistically screened co-firing pairs from the confluence tape — robust-stats z-scan, young pairs marked accruing — display only.",
        "full": "The confluence discovery engine runs a deterministic robust-stats z-scan (median and median-absolute-deviation z, 100-draw circular-shift null) over engine-pair co-occurrence rates in the confluence tape. Young tape rows carry state accruing and a null z-statistic — never a fabricated number. The rotation-state by cycle-position pairing is explicitly excluded from testing. No language model is involved. Display only with no consumers currently wired.",
        "src_fp": "50f34bb4de262402",
    },
    "confluence-graph": {
        "short": "A map of which signals tend to agree or conflict — shown for context only, never changes any decision.",
        "full": "This feed builds a map where nodes are engines, sectors, regimes, and theses, and links show how they relate: structural wiring, historical co-firing, lead-lag timing, and detected contradictions. The contradiction detector currently watches six specific signal pairs. Every link is display-only — this map never gates alerts, raises priorities, or changes rankings. Promoting any link to decision use requires its own separately registered validation study.",
        "src_fp": "2e87b9de964df238",
    },
    "confluence-sequence": {
        "short": "Per-subject persistence streak and strength slope for co-firing patterns — state machine from new to gone — display only.",
        "full": "The confluence sequence engine reads the confluence tape and for each subject computes a persistence streak, a Theil-Sen robust slope over the trailing window, and a state machine progression of new, strengthening, stable, decaying, or gone. Contradiction pair streaks and slopes are also tracked. An embedded self-check asserts no authority is claimed. Read by the brief context builder.",
        "src_fp": "a1b371f83dd11665",
    },
    "confluence-strength": {
        "short": "Per-subject independent confirming engine count with redundancy discount from the covariance spine — display only.",
        "full": "The confluence strength engine counts confirming engines per subject, as_of date, direction, and horizon, then applies a redundancy discount derived from the covariance spine dominant-overlap clusters to yield a fractional independent confirming count. The regime bucket is stamped from the world state quad for context only — no conditioning. The rotation-state by cycle-position pairing is excluded from dedicated field emission. An embedded self-check asserts no authority is claimed. Read by the brief context builder.",
        "src_fp": "5f7ee830f2edd066",
    },
    "confluence-tape": {
        "short": "Nightly point-in-time tape of confluence strength rows and contradiction pair firings — sole advancer is the nightly run.",
        "full": "The confluence sequence engine appends one row per nightly run. Each row records confluence strength and any contradiction pair firings for the as_of date. The append is idempotent per as_of — a same-night rerun replaces the row rather than duplicating it. Read by the confluence sequence and confluence discovery engines. Never gates, never ranks, never raises a priority.",
        "src_fp": "61768c9933701a81",
    },
    "context-candidates": {
        "short": "Statistically screened co-occurrence and composition shift candidates from the nightly context scanner — display only, never ranked.",
        "full": "Built nightly by the context scanner using three frozen template families: composition drift (T1), outcome heterogeneity (T2), and co-occurrence shift (T3). Each candidate carries a short identifier, the template family, the cell tested, the z-statistic, a null-percentile from circular-shift draws, and a status of candidate or decayed. Young candidates with insufficient history carry a null statistic and accruing state — never a fabricated number. Candidates decay after 60 days unrefreshed and stay in the file as dead-stays-dead records to block re-emission as novel. Three legal exits exist: the cortex stakes a candidate, a human charters a pre-registered study, or the candidate decays. Consumed by the cortex reader; never ranks, scores, or gates any money-path surface.",
        "src_fp": "df77fb74704493da",
    },
    "context-risk": {
        "short": "Board composition risk lens: archetype ratios, regime-conditional tail, and crowding flags — display only, never ranks.",
        "full": "The context risk builder reads the current US standouts list, the stock personality store, and the regime timeline to profile the board's archetype composition versus the full universe. It produces a weighted risk profile from personality field-guide fingerprints, a regime-conditional P10 tail using the current regime quadrant crossed with a liquidity cell (cells with fewer than 887 observations print insufficient_n), and three flags: tinderbox, negative-gamma, and event-window. All numbers carry observation counts and a survivorship watermark. The artifact annotates only — it may never rank, size, gate, or raise attention floors. Read by the world state engine.",
        "src_fp": "7d32806c54260d63",
    },
    "cortex-attention-firings": {
        "short": "Log of the AI reviewer's attention claims, tracked to build a performance record before it earns any authority.",
        "full": "Each time the AI reviewer flags something noteworthy during its nightly run, it logs a claim here. These claims are folded into the master signal table as ungraded entries and tracked over time. The reviewer earns expanded authority only after at least 30 graded claims with a hit rate whose conservative lower bound clears the base rate by a set margin. Until then every entry is marked context-only, and only the reviewer may write to this log.",
        "src_fp": "4f8c7f6cb54f650e",
    },
    "cortex-attention-grades": {
        "short": "Performance grades for the AI reviewer's past attention claims, used to track whether its observations were correct.",
        "full": "For each attention claim the AI reviewer logged in the past, this feed records whether the prediction was correct at the specified horizon. Graded rows are joined back to the original claim log and included in the master signal table. Infrastructure-type claims with no directional prediction are not graded for hit rate. Only the grading script may write to this log.",
        "src_fp": "f7429f4df861fdad",
    },
    "cortex-memo": {
        "short": "The AI reviewer's nightly written summary of the day, with contradiction and decay notes — display only.",
        "full": "Each night the AI reviewer reads the day's market state, signal history, reliability estimates, confluence map, governance log, and reflex firings, then writes a structured memo summarizing what fired, any signal contradictions, and families showing reliability decay. The memo is display-only and never feeds any ranked surface. The reviewer is on a trial period and cannot act on its own — the probation status is reported honestly in every memo.",
        "src_fp": "f380cc97fefb651e",
    },
    "cortex-probation": {
        "short": "Current earn-in status for the AI reviewer, tracking whether it has met the statistical bar to gain any authority.",
        "full": "This file is the single source of truth for whether the AI reviewer has earned expanded authority. It is rewritten nightly by the grading process after evaluating the reviewer's accumulated performance record. Currently the reviewer is on probation with zero graded entries — it has not yet met the threshold. The governance log is updated only when the status actually changes, keeping that log sparse and meaningful.",
        "src_fp": "2cef2470e3afe15e",
    },
    "covariance-spine": {
        "short": "Daily structural independence check across four signal blocks — rates, factors, dispersion, and NW engine firings — display only.",
        "full": "The covariance spine builder measures independence across four blocks: rates PCA over yield curve shapes, factor-return correlation PCA, dispersion regime pass-through, and NW engine firing independence via participation-ratio of the engine correlation matrix (requires at least 30 active weeks). Each block is guarded independently so a missing input affects only its own block; the builder always exits cleanly. The same-bet warning fires when the largest cluster has three or more engines with mean intra-cluster correlation above 0.60. The confluence engine reads the lobes block to embed an independence summary in the confluence graph. This artifact annotates only — it may never score, size, gate, rank, or originate a trade.",
        "src_fp": "4c384a9319ffafee",
    },
    "covariance-spine-history": {
        "short": "Daily row of headline covariance-spine scalars — effective independent lobes, dominant factor share, same-bet warning — display only.",
        "full": "The covariance spine builder appends one row per nightly run alongside the main artifact. Each row is keyed by as_of; an existing row for the same date is replaced rather than duplicated. Fields captured: effective independent lobes, measurable lobes count, rates dominant principal-component share, factor effective bets, dispersion state, and the same-bet warning flag. Display and operations only — no authority over any decision surface.",
        "src_fp": "cde97c269bfed318",
    },
    "cycle-pattern-state": {
        "short": "Compact summary of cycle phase, hazard gate verdicts, and truth-registry counts for each entity — display only, never escalates.",
        "full": "The cycle pattern state builder compacts the latest cycle phase per entity, hazard gate verdicts for the six up/down by horizon cells, and active truth-registry counts into one governed display artifact. Hazard gate verdicts are read from the model epoch files at runtime, never hardcoded. Cells where the verdict is PRIOR carry family-stratified survival base rates; every surfaced probability carries its cell verdict badge — no naked probabilities. Read by the world state engine, the mastermind context builder, and the cortex ask tool. The artifact may de-escalate a calibrated key as context but may never originate, score, or escalate any decision.",
        "src_fp": "76104926fef20113",
    },
    "dt-contra-state": {
        "short": "Per-ticker momentum-contra chip states aggregated from stock data into a governed Neural Web artifact — display only.",
        "full": "The contra-state builder exposes the already-computed per-ticker contra-chip field (state, band, score percentile, whale size, and whale change) aggregated from the stock data files. The caveat string is sourced from the chip module so there is a single source of truth. Ordering is deterministic (alphabetical by ticker) for stable diffs. On CI runners where the stock data directory is absent, the artifact degrades gracefully to an empty states list with an explanatory note. No Neural Web consumer is wired to this artifact yet (2026-07-17 audit) — it accrues display-only; any future cortex use would be citation-to-de-escalate only, never originate, score, or escalate. The momentum-dilution law forbids blending this artifact into any momentum ranker.",
        "src_fp": "516ab774c7be674c",
    },
    "entity-thesis-mechanism-registry": {
        "short": "Deterministic crosswalk linking entities, theses, and mechanism cards across local ID systems — display only, no scoring.",
        "full": "The entity-thesis-mechanism registry builder constructs a conceptual lineage graph over existing local ID systems: the species registry, research-factory candidates, governance events, reflexivity thesis groups, and the trial ledger. The crosswalk is deterministic and display-only — each local system remains its own authority. Suggested duplicates are token-overlap context only. No scores, no rankings, no gating authority.",
        "src_fp": "161761b3e23173b0",
    },
    "evidence-clock": {
        "short": "Daily read-only aggregator answering what is due, stale, underpowered, or blocked across all review clocks — display only.",
        "full": "The evidence clock builder reads every review-clock source in the repo and produces one unified answer about what needs attention today. No language model is in the loop; all computation is deterministic. The builder never promotes, retires, or mutates any source system. The operator-maintained attention-snooze ledger (evidence-clock-reviews) is read but never written by the builder. Consumed by the evidence clock check script and the brief context builder. Ratified by adjudication in mid-2026.",
        "src_fp": "096288451a0909aa",
    },
    "evidence-clock-reviews": {
        "short": "Operator-maintained snooze ledger for the evidence clock — append only, attention routing only.",
        "full": "Maintained by hand, this append-only ledger lets the operator acknowledge review-clock items within a seven-day window. Each row records the clock ID, the reviewed-on date, a note, and the outcome. A review within the snooze window sets the matching clock row to acknowledged and excludes it from the top-due and morning-line counts. Real state changes must flow through the source system — this ledger handles attention routing only. The builder handles its absence gracefully, so a freshness SLA of 9999 hours is intentional.",
        "src_fp": "44f0d5bd64b017bf",
    },
    "factor-contradictions-ledger": {
        "short": "Append-only borrowed-strength contradiction log — dormant until the factor panel accumulates 60 dates of history.",
        "full": "The factor contradictions detector runs nightly inside the factor panel job, but emits no records until the panel has at least 60 distinct dates of history. The runner-local panel has far fewer dates, so the ledger cannot exist yet by design. When it does begin accruing, each row is keyed by date and ticker and carries a severity hardcoded to 'note' until the H2 gate passes. All entries are display-only unconditionally. The SLA is parked at 9999 hours — the declared-dormant idiom — so the missing file is printed honestly in health status without driving a degraded flag. The operational SLA of 30 hours should be restored when the ledger first appears, approximately 60 trading days of panel accrual from now unless a backfill runs.",
        "src_fp": "438522b1da479232",
    },
    "factor-intelligence-state": {
        "short": "Daily summary of factor-panel health and active factor hypotheses — context only, never changes any ranking.",
        "full": "Each day after the factor-analysis job runs, this feed publishes a digest of the factor panel's health, its current 'factor weather,' the active factor-pair hypothesis under study, and a performance scorecard. It is context-only — no scoring surface or decision system reads it to act. The permitted-actions block is a mirror of configuration, not a switch that changes behavior. It is read by the factors page on the public site and by the admin panel.",
        "src_fp": "c6f3cc9b63500673",
    },
    "feeds-plane": {
        "short": "The daily published data plane assembling risk, breadth, events, and sector feeds into a single delivery package.",
        "full": "Each day this process assembles the full set of public feeds: risk radar data, sector breadth, an event calendar, international spillover data, subsector rotation, and several supporting data files. Feeds copied from other engines are copied byte-for-byte without reshaping, because the source engine owns the schema. The assembled package is pushed to cloud storage and is not stored in the code repository.",
        "src_fp": "12759a6542c0dedd",
    },
    "fred-wresbal": {
        "short": "Raw FRED reserve-balance store (WRESBAL) — collected weekly from H.4.1, input to the liquidity-plumbing lobe.",
        "full": "The FRED collector populates this store from the H.4.1 release: reserve balances with Federal Reserve Banks, weekly Wednesday, in billions of dollars. The registry entry intentionally precedes the artifact's first appearance — the file appears on the next collect run after registration. The liquidity-plumbing builder reads this store fail-open: if the file does not yet exist, the reserve-balances field is null with a gaps entry. A millions guard is in place in case the store convention differs from billions. Raw data only — no scoring or net-liquidity composite here.",
        "src_fp": "641530b6e6cc5382",
    },
    "governance-ledger": {
        "short": "Append-only log of every significant change to what each part of the system is allowed to do.",
        "full": "This ledger records consequential authority changes: when a component gains or loses permission to act, when a tier changes, when an operator overrides, and when the AI reviewer proposes or applies a change. Each event type has exactly one designated writer to avoid conflicts. The ledger itself has no authority — reading it for display or a quarterly audit never changes any engine behavior. It grows slowly, an estimated five to twenty events per quarter.",
        "src_fp": "3ad9f7601532403f",
    },
    "hypothesis-inbox": {
        "short": "Inbox where the AI reviewer deposits candidate research hypotheses for human review and registration.",
        "full": "When the AI reviewer's nightly run identifies a potential research hypothesis, it writes a draft entry here. Entries start with an 'inbox' status and transition to registered, budget-rejected, or invalid through the formal registration process. Registration is a separate step that enforces budget limits. Only the AI reviewer's nightly job may write to this log.",
        "src_fp": "b9e2c318ebe1065d",
    },
    "kernel-decisions": {
        "short": "The record of which engine families passed the statistical review to be used in decisions — currently empty.",
        "full": "This file records the outcome of the quarterly statistical batch review that decides which engine families are cleared to inform decisions. The survivors list is empty and stays empty until the next scheduled review in October 2026. Being marked 'armed' in the reliability estimates only means the display is ready — it does not mean statistical clearance. Only families on the survivors list here may ever be used in a decision.",
        "src_fp": "e111103525400c97",
    },
    "kernel-estimates": {
        "short": "Track-record reliability estimates per engine and market regime — shown for context only, never used in decisions.",
        "full": "This feed holds reliability estimates for each engine, broken down by market regime and time horizon, using statistical shrinkage to keep thin samples honest. It is displayed for information only. No ranking, alert, or allocation may use these numbers until they pass a quarterly pre-registered review. Regime-specific estimates are honest but thin because grading began only in mid-2026; the overall estimates draw on far deeper history back to 1962.",
        "src_fp": "5e9d580afc6bdc8d",
    },
    "kernel-families": {
        "short": "Per-engine decay diagnostics showing how reliability changes across time horizons — display only.",
        "full": "For each engine family, this feed shows how its reliability score changes as the holding horizon lengthens, how recent performance compares to longer history, and when the engine last fired. It is generated from the reliability estimates and is displayed for information only — no decision-making system reads it. The recency comparison is intentionally left unshrunk because the time windows are sequential, not independent.",
        "src_fp": "f0331b7e087eefba",
    },
    "kernel-half-lives": {
        "short": "Measured signal decay curves showing how quickly each engine's edge fades — display only, all currently null.",
        "full": "This feed tries to measure how quickly each engine's statistical edge decays as a position ages. It uses conservative sample floors and requires decay curves to fall as the horizon grows — rising curves are reported as null rather than published. Because grading data is still accumulating, the honest expected result today is that all families report null. A separate marker tells a clean all-null run from a crash. Display-only, off the render path.",
        "src_fp": "426710d4cb0d5c2c",
    },
    "lagging-signals": {
        "short": "Per-signal flags for firings in hostile regimes, without breadth support, or too soon after prior firings.",
        "full": "For each recent signal firing, this feed adds three diagnostic flags: whether it fired during a hostile market regime (stagflation, growth scare, or recession), whether market breadth was below normal that day, and whether the same engine and stock fired repeatedly in a short window (a rough proxy for a signal running late). All three flags are display-only context. Missing regime or breadth data makes the flags null rather than assumed.",
        "src_fp": "46496c4eda3afdca",
    },
    "liquidity-plumbing": {
        "short": "Daily Fed and treasury liquidity conditions aggregated from quantity, quality, stance, and auction inputs — display only, de-escalation only.",
        "full": "The liquidity plumbing builder aggregates four data layers: quantity from the Fed net liquidity store, quality and overlay from the regime latest file, treasury position from net issuance and TGA stores, and auction context from the treasury auctions store. Funding scarcity spreads and swap or FIMA blocks are null with honest gaps entries pending future phases. Fed and Treasury posture language is constrained to 'condition/steer', not 'control markets'. The cortex may explain, attend to, or de-escalate based on this artifact; it may never raise a score or rank anything. The sole tailwind entry is the already-measured 21-day cycle-ladder nudge from the cycles engine — this lobe exposes that context, not a new signal. Read by the world state engine, the ask-brain tool, the contradictions engine, the causal inventory, and the brief context builder.",
        "src_fp": "277f5806406db13f",
    },
    "machine-registry": {
        "short": "The official ledger of research hypotheses proposed by the AI reviewer and formally registered for tracking.",
        "full": "This append-only ledger records every research hypothesis the AI reviewer has formally registered, including the question, the pre-committed decision criteria, the time horizon, and a come-back date for review. A hard budget of three new registrations per calendar week applies — to add a new one, an old one must be retired. No scoring surface may read this ledger for decision-making; it is context and record-keeping only.",
        "src_fp": "15658cf62ffd9472",
    },
    "mechanism-pathways": {
        "short": "Deterministic attribution of today's market move to a primary mechanism family — display only, never ranks or sizes.",
        "full": "The mechanism pathways builder uses a trigger precedence chain: clear market-drivers reading first, then risk-radar scare, then factor rotation, then a no-pathway null if all triggers are stale or absent. The artifact carries a coverage score and a coherence label of supported, partial, or conflicted. The confidence ceiling is always context-only. Read by the daily brief why-the-tape-moved block, the ask-brain and cortex read tools, the committee page client-side block, and the admin quality-assurance panel. Ranking, sizing, alert escalation, board ordering, and mastermind arming are all forbidden consumers.",
        "src_fp": "f5b7ebc6fff87d6d",
    },
    "mechanism-pathways-history": {
        "short": "Append-only daily digest of mechanism pathway snapshots — one compact row per day — display only.",
        "full": "The mechanism pathways builder appends one compact row alongside the main artifact each nightly run. Each row records the as_of date, schema version, pathway count, primary family, and no-pathway reason. Same-day reruns skip if the as_of date is already present, keeping one row per calendar day. Display and operations only — no authority over any decision surface.",
        "src_fp": "a877a25246d46445",
    },
    "nasdaq-internals": {
        "short": "Rotation state for seven Nasdaq-100 tech archetype groups — RRG-style descriptive labels, display only.",
        "full": "The Nasdaq internals builder reads the basket membership archetype-groups partition and assigns each of seven groups an RRG-style state — leading, improving, weakening, or lagging — with two-day hysteresis to avoid flip-churn. Groups cover: AI compute supply, AI capital-spending recipients, edge devices, enterprise software, cybersecurity, digital services and media, and quality megacaps. Member composites are equal-weighted against the QQQ benchmark. Union-semantics overlap across groups is intentional. No forecast, no onset or routing fields, no authority over any decision.",
        "src_fp": "b0ee91358541276e",
    },
    "neuralweb-daily-brief": {
        "short": "A daily plain-language summary of what the Neural Web did today — deterministic, no trading language.",
        "full": "Each day this feed answers the question 'what did the Neural Web do today?' in plain terms. The engine job writes a first draft; the AI reviewer job finalizes it and adds a compact history row. The brief is strictly display and operations content — it contains no trading language and carries no authority. Its schema is versioned to allow future changes without breaking readers.",
        "src_fp": "a805c3423b5e10a5",
    },
    "neuralweb-daily-brief-history": {
        "short": "Rolling history of daily brief snapshots, one record per day, used to detect what changed since the last run.",
        "full": "Each day a compact summary row is appended here after the AI reviewer finalizes the brief. If the same date already has a row, it is replaced rather than duplicated. The file is kept in chronological order and is used by the next day's run to detect what changed. It is display and operations only.",
        "src_fp": "151ddea3b1bf6897",
    },
    "neuralweb-discovery-confluence": {
        "short": "Two-source discovery join of filing phrase velocity and basket adoption — watchlist only, never auto-promoted.",
        "full": "The discovery confluence builder joins two legs: EDGAR phrase velocity and basket adoption signals. A theme is flagged when both the phrase velocity z-score is positive with at least two filers and any basket star-velocity z-score is positive. Output sections cover confluence candidates, single-leg phrase hits, single-leg adoption hits, and novel phrase clusters. Detection is honest about being noisy with approximately zero early-entry edge. Watchlist and candidate feed only — never auto-promoted. All authority switches are false; context only.",
        "src_fp": "2d87390ef7dbe2be",
    },
    "neuralweb-health": {
        "short": "Machine-readable status of every Neural Web lobe, updated in two phases each day by the engine and the AI reviewer.",
        "full": "This file provides the operating status for all Neural Web lobes in a machine-readable format. The engine job writes a first pass using the previous day's AI reviewer status; then the AI reviewer job rewrites the reviewer section with the current run's result. Data-only lobes stored in cloud storage are reported as not locally verifiable rather than missing. This file has no authority over engine behavior — it is for display and operations monitoring only.",
        "src_fp": "6c057bd7036b09e0",
    },
    "neuralweb-market-plane": {
        "short": "Compact macro header feed for the Terminal top bar and committee hero strip — regime, risk, breadth, and liquidity in one small file.",
        "full": "The mastermind context builder writes this canonical copy alongside a byte-identical site mirror in one atomic call. Sources: world state for verdict, regime, volatility, and breadth; liquidity plumbing for the liquidity block with world state fallback; the confluence graph for the contradiction summary; and the cortex memo for run status. Each missing input yields nulls for its block plus a gaps entry — never an exception. Weekend-aware stale flag is included. Context only; no authority booleans; all fail-open.",
        "src_fp": "99d0cf41349af0a7",
    },
    "neuralweb-mastermind-context": {
        "short": "The daily bridge feed packaging Neural Web context for the Terminal product — context only, no authority.",
        "full": "Each day this feed assembles a curated package of Neural Web context — market state, reliability summaries, detected contradictions, bottom-sensor readings, options-entry context, and the AI reviewer note — formatted for the Terminal product to read. Its candidate list draws from US standouts, alternative data, and radar tickers, capped at 250 rows. All five authority switches are off: this is context only. The Terminal product stays the decision-maker.",
        "src_fp": "af9df5338e5c1483",
    },
    "neuralweb-orchestrator-runlog": {
        "short": "Per-pipeline-run summary of what the NW orchestrator built, what changed, and the Mastermind dialogue state — ops only.",
        "full": "The orchestrator log builder appends one deterministic entry per pipeline run, keeping the first entry per run-date and workflow combination. Each entry summarises lobes built and stale, what-changed counts, contradiction counts, cortex status, and the Mastermind dialogue state including nudges and directives. Every N runs (default 5, configurable) a roll-up review row with a deterministic progress assessment lands in the sibling reviews log. No language model, no trading semantics. Runs in the daily cortex job after the brief is finalised. Read by the admin neural web panel.",
        "src_fp": "e95f48b8bd4483b6",
    },
    "neuralweb-theme-clinical": {
        "short": "Per-theme clinical-trial capital-commitment rollups from ClinicalTrials.gov — display only, three themes covered.",
        "full": "The theme clinical engine reads the ClinicalTrials.gov v2 API (keyless, industry-sponsored trials only). It covers three themes: GLP-1 obesity, diagnostics and life science, and medical devices, with nine modality rows total. Per modality it reports registration velocity year-over-year (like-month comparison), enrollment commitment trend, and a phase-migration read showing Phase 2-plus share delta. History is keyed by study first post date; a vocabulary version stamps the query definition for history integrity. No composite across themes. Off the render path — collected via the standalone CLI or a collect-lane step. Honest null when the monthly parquet store is absent.",
        "src_fp": "10c9c35a1801036b",
    },
    "neuralweb-theme-options-witness": {
        "short": "Per-theme options-tape crowding hazard: call-OI concentration, put-call ratio, and IV premium — hazard framing only.",
        "full": "The theme options witness engine reads from the ThetaData EOD store (runner-local at the theta-ops machine). Three independent legs per theme: call open-interest HHI concentration, put-call OI ratio, and IV premium versus realized volatility. High values flag crowded or fragile positioning — never bullish. Position fusion is forbidden. Baskets with less than 40% member OI coverage emit null legs. The daily pipeline writes a structured honest-null artifact when the ThetaData store is absent, keeping as_of current while legs are null. Real legs require the launchd lane on the theta-ops machine. The keep-last-real law prevents a store-less run from overwriting real legs newer than six days. Context only; all authority switches false.",
        "src_fp": "7224ebb9b769034c",
    },
    "neuralweb-theme-trade-flows": {
        "short": "Per-theme Census import-flow rollups — year-over-year change and acceleration, display only, requires Census API key.",
        "full": "The theme trade flows engine reads the US Census International Trade API using monthly HS-code import values. Covers 29 HS codes across 11 themes including rare-earth minerals, solar, AI semiconductors, grid electrification, copper-steel electrification, defense aerospace, and medical devices. Per theme it reports year-over-year percent change, a three-month versus twelve-month acceleration signal, a confirmation label of confirms, contradicts, or neutral, and a magnitude band. Sign convention: rising imports confirms onshoring demand; falling imports confirms domestic substitution. Census trade data lags approximately six weeks. When the API key is absent or inactive the collector writes a structured honest null. A seven-night self-chunking backfill runs once the key is activated.",
        "src_fp": "88c4f514fa5a41e7",
    },
    "nw-health-run-history": {
        "short": "Per-nightly-run health status log — keyed by run date, used to measure consecutive degraded nights.",
        "full": "The health escalation checker appends one row per nightly engine run. Each row records the run date, degraded flag, produced_at timestamp, and reasons count. Keying by run date rather than data vintage means a frozen as_of across consecutive degraded nights counts correctly as distinct run records. The escalation checker reads this file to measure the streak of consecutive degraded runs with a calendar-adjacency guard before deciding whether to dispatch an alert.",
        "src_fp": "71bdaa94919c4ae4",
    },
    "opex-risk-snapshot": {
        "short": "Options-expiration window risk read embedded in the vol regime page payload — plain-word level, display only.",
        "full": "The vol regime builder embeds a nightly options-expiration risk snapshot in the site regime payload: how many risk states are running hot out of those applicable, a plain-word level (quiet, elevated, or heavy), bilingual glance copy, the per-state stack, and where we are in the expiration window. It is context only — it is never read by the risk computation, never feeds any scare channel, and never sizes or gates anything, per the standing rates-and-inflation program rulings. Sole writer is the nightly vol regime builder.",
        "src_fp": "a7a507365de425c3",
    },
    "ops-push-basket-freeze": {
        "short": "Deduplication log for basket-freeze churn alerts, preventing repeat notifications for the same event.",
        "full": "When the basket-freeze process detects excessive churn and dispatches an alert, a record is appended here to prevent the same alert from firing again. The log is written only by the basket-freeze process and only when the feature is enabled. If disabled, the dedup check is skipped but the alert still fires. This feature was enabled by an operator authorization event in mid-2026.",
        "src_fp": "ab0760c825a99a2a",
    },
    "ops-push-healthcheck": {
        "short": "Deduplication log for system health heartbeat failure alerts.",
        "full": "When the system health check detects a heartbeat failure and dispatches an alert, a record is appended here. However, the heartbeat workflow does not commit this file, so the six-hour dedup window is effectively inactive for this lane — every heartbeat failure alert dispatches regardless of prior alerts. This is an honest limitation documented in the system.",
        "src_fp": "2a0ec953a0da02f1",
    },
    "ops-push-nw-health": {
        "short": "Dedup store for Neural Web health degradation alerts — fires after three consecutive degraded nights.",
        "full": "The health escalation checker writes here when the overall NW status is degraded or any daily-cadence lobe is missing or stale beyond 1.5 times its SLA for three or more consecutive nights. The dedup store prevents the same alert from dispatching repeatedly. When the escalation spine is disabled the dedup and ledger are skipped, but the raw alert dispatch still fires as an invariant. Read by the alert triage engine.",
        "src_fp": "8c0a08a5f316c83d",
    },
    "ops-push-signal-sanity": {
        "short": "Deduplication log for signal-sanity tripwire alerts, with a six-hour suppression window.",
        "full": "When the signal sanity check detects a data integrity problem and dispatches an alert, a record is appended here. A six-hour suppression window prevents the same alert from firing repeatedly across the daily and heartbeat check lanes. If the feature is disabled, the dedup check is skipped but the alert still fires.",
        "src_fp": "5ec2cae86867bdc0",
    },
    "options-entry-gate": {
        "short": "Pre-registered options entry quality gate — currently building history, not yet scoring.",
        "full": "This gate will eventually measure whether options market conditions at entry time improve trade outcomes across three pre-registered signal buckets. The gate is currently in a history-building phase with far fewer observations than the minimum needed to reach a verdict. All scoring is suspended until each bucket reaches at least 30 observations, expected around late 2026. The gate remains in shadow mode until the validation threshold is crossed.",
        "src_fp": "3ffd8e6fa48b19c2",
    },
    "options-entry-state": {
        "short": "A daily fusion of raw options-market fields per stock — shown for context only, no composite scores allowed.",
        "full": "Each day this feed assembles raw options-market readings for each stock: implied volatility, skew, dealer positioning, open interest, gamma regime, and distance to key price levels. By design no composite or combined score may be built from this data — each field must stand alone. Some fields stay unavailable until a future data backfill lands. When source data is missing, fields are left null rather than filled with a neutral placeholder.",
        "src_fp": "e421e596e477494c",
    },
    "prophet-pick-autopsies": {
        "short": "One postmortem file per selected pick, written after the pick matures, naming what drove the outcome and whether a better process could have changed it.",
        "full": "After a standout pick matures, the audit lane selects a subset for individual review — favouring the biggest winners, the worst losers, any picks that were held back by a data problem, and any that barely missed the board. For each selected pick, one artifact records the deterministic performance numbers alongside a plain-language postmortem: what drove the result, whether it was a process misstep or simply unforeseeable, which signals performed well and which were late, and what a future board should keep in mind. The verdict falls into one of five closed categories ranging from a correctable process fault to a result that was simply outside anyone's control. These files accrue as picks mature and are read by the Prophet governor when compiling the cross-market health report.",
        "src_fp": "0ac50e4ed40f3d3c",
    },
    "prophet-status": {
        "short": "Cross-market accountability summary: what each standout board has accrued, which inputs are healthy, and how the whole system is holding up.",
        "full": "This artifact is the Prophet lobe's nightly health report for the entire standout system. It reads the committed records for every market — US, China, Hong Kong, Canada, and the international dashboard — and compiles a single document that captures how many picks have matured and been graded in each market, which artifacts are fresh or overdue, how many data gaps exist per market, and what the overall process-fault picture looks like. Importantly, each market's numbers stay in its own block: the US and Canada boards fill at a different price than the China board, and those fill conventions are never mixed together. The cross-market section shows counts and coverage only. A separate section records the freshness of every monitored artifact against its stated deadline and flags anything that has fallen behind.",
        "src_fp": "5e741d080da14380",
    },
    "prophet-suggestions": {
        "short": "Coded recommendations from the Prophet lobe to the Master Brain, flagging stale data, coverage gaps, and system drift.",
        "full": "Each night the Prophet governor scans the dashboard health report for deterministic findings worth surfacing to the wider system. When it finds an artifact that has gone stale, a cluster of missing data in one market, or signs that a board ledger has not been updated recently, it writes a suggestion row here. The rows follow the same format as the Mastermind feedback nudges: a stable code, a short severity label, the affected market, and a plain-language description of the problem capped at one hundred and sixty characters. High-severity findings are also sent to the shared inter-lobe channel so the Master Brain can see them without polling this file directly. The suggestions accumulate across nights but are deduplicated by their stable codes, so the same recurring problem appears once with its original discovery date.",
        "src_fp": "70b5d3d3d3e798f2",
    },
    "reflex-firings-commodity-shock": {
        "short": "Log of commodity shock events detected by the automated sentinel, graded over short horizons.",
        "full": "Each time the commodity shock sentinel detects a genuine new state transition — a shock or a recovery — a record is appended here. Duplicate detection prevents the same event from being logged twice. Shock states carry a bearish direction; recovery and normal states carry a neutral direction. The log is graded against a commodity benchmark at one-day and five-day horizons, but the sample is still small and no conclusion can yet be drawn.",
        "src_fp": "d9e9f7ac42b5665d",
    },
    "reflex-firings-pattern": {
        "short": "The shared pattern for automatic-rule firing logs, each written by its own rule's dedicated process.",
        "full": "Each automatic rule that has reached the live-mirroring stage owns one append-only firing log following this pattern. A log is written only when the rule genuinely fires, and each has exactly one designated writer. The firing records are then folded into the master signal table as ungraded entries. Two rules mirror today — the stale-regime self-heal and the commodity-shock sentinel — with the AI reviewer's attention rule recently added as a third.",
        "src_fp": "ca5985e023e378c6",
    },
    "reflex-firings-regime-selfheal": {
        "short": "Log of times the system automatically refreshed a stale market regime reading.",
        "full": "When the system detects that the market regime data has gone stale and automatically refreshes it, a record is appended here. Entries are only written when the self-heal actually fires — not on every check. This is an infrastructure-level log with no directional signal; it cannot be graded for performance.",
        "src_fp": "967f67b04801353d",
    },
    "reflex-push-dedup-store": {
        "short": "Deduplication log for priority push alerts, ensuring the same alert is not sent twice.",
        "full": "When a priority alert is dispatched, a record is appended here keyed by the alert's source, type, asset, and send time. The sole purpose is to prevent duplicate pushes — this log is never read by any scoring or ranking surface and never raises or lowers any signal. Push alerts were formally enabled by an operator authorization event.",
        "src_fp": "bc0d8b48a00279ef",
    },
    "release-forecast-latest": {
        "short": "Before each major data release, this feed shows our projection alongside several reference benchmarks and the current Fed policy backdrop — display only, never conditions any trade.",
        "full": "Each night before CPI and jobs report releases, this feed publishes our quantitative projection (point estimate plus a confidence band) for the upcoming print, compares it against reference benchmarks including the Cleveland Fed nowcast, and attaches the current Fed policy context: stance, the market-versus-Fed-dots gap in basis points, implied cuts over the next twelve months, and the next meeting date. The surprise-skew field shows which direction our projection leans relative to the benchmark set, in units of historical forecast error. A running scoreboard accumulates actual versus projected accuracy as prints land. Everything here is display-only and horizon-agnostic context — it never gates alerts, conditions entries, or changes any score. Forward accrual began in July 2026.",
        "src_fp": "18153b17f4e42daf",
    },
    "research-queue": {
        "short": "Advisory ranked research candidate list — dormant and unwired, never produced on a schedule.",
        "full": "The research queue ranker exists but is wired to no automated workflow — the artifact has never been produced by any scheduled run. When run, it ranks candidates from the hypothesis inbox, the machine registry, the species registry, and the trial ledger into buckets: high value to build now, blocked by missing data, too sparse, duplicate of existing work, or invalid shape. It is advisory only — the metabolism register-hypothesis step remains the sole budget chokepoint. The SLA is parked at 9999 hours — the declared-dormant idiom — so the missing file is printed honestly without driving a degraded flag. The operational SLA of 168 hours should be restored when the producer is wired to a nightly opt-in or manual cadence.",
        "src_fp": "6b2fa001937bb675",
    },
    "risk-radar-review-log": {
        "short": "Risk Radar self-correction audit trail — dormant until 30 graded forward-log calls accumulate.",
        "full": "The Risk Radar review engine runs nightly inside the daily pipeline and never aborts, but self-gates before writing the first row: records are appended only after a usable AI proposal, which requires the review feature to be enabled, an API key present, and at least 30 graded entries in the radar forward scorecard. With zero graded entries as of mid-2026, the artifact cannot exist yet by design. When it does begin accruing, each row captures the proposal, the do-no-harm backtest verdict, and any apply or reject decision. Governance events for proposals, applies, and rejects also land in the system-wide governance ledger. The SLA is parked at 9999 hours — the declared-dormant idiom — so the missing file prints honestly without driving a degraded flag. The operational SLA of 200 hours should be restored when the first row lands.",
        "src_fp": "81d9a0b86f3c32be",
    },
    "rule-experiment-registry": {
        "short": "Pre-registration ledger for rule replay experiments, enforcing that no experiment runs without a prior commitment.",
        "full": "Before any rule replay experiment can run, it must be registered here with its full experimental grid, minimum sample size, decision criteria, and a hash of its specification. The runner refuses to execute any unregistered or hash-mismatched experiment, preventing after-the-fact result selection. All experiments are pooled into a single statistical family for false-discovery control, regardless of the specific rule being tested.",
        "src_fp": "9c1310b2ea293fd0",
    },
    "rule-experiment-summaries": {
        "short": "Per-experiment results from rule replay studies — display only, cannot promote any rule to live use.",
        "full": "After a rule replay experiment runs, its summary results are stored here: win rates per condition, exit metrics, regret metrics, era-split breakdowns, and pooled trial counts. These are committed to the repository and shown for review. The underlying per-trade data files are stored locally only and not committed. All results are display-only — promoting any rule to live behavior requires passing a separately registered validation process.",
        "src_fp": "ee9e7d02ed8e2a24",
    },
    "site-altdata-mastermind": {
        "short": "Daily alternative-data summary published to the public site for the Terminal product to read.",
        "full": "The alternative-data engine assembles a daily summary and writes it to the public site under a versioned schema. The Terminal product reads this feed to enrich its views with alternative-data signals. Ten other parts of the system also consume this output.",
        "src_fp": "a40d99ba2c360fd7",
    },
    "site-artifact-manifest": {
        "short": "Daily registry of all published signal artifacts, used to verify the pipeline produced complete outputs.",
        "full": "Each day the signal-export process writes a manifest listing every artifact it produced. Three downstream consumers read this manifest to confirm the pipeline ran completely. It serves as a conformance checkpoint — if an artifact is missing, the manifest exposes the gap.",
        "src_fp": "07a8b02b06bde190",
    },
    "site-attention-deterministic": {
        "short": "Site mirror of the deterministic attention surface, fetched client-side by the committee page.",
        "full": "The deterministic attention builder writes this file in the same step as the data copy. The committee page fetches it client-side to display the five pre-registered attention items. Content is byte-identical to the data copy — display only, no authority.",
        "src_fp": "5561d4d16c467a5d",
    },
    "site-causal-lab-state": {
        "short": "Public-site copy of the CHF lab heartbeat, byte-identical to the data copy.",
        "full": "This is the site-published copy of the causal lab state, written at the same time by the causal frontier builder. It is the preferred read source for the admin Causal Lab panel and for any future committee display surface. Byte-identical to the data copy. Display-only context artifact with not-a-signal status unconditionally.",
        "src_fp": "03680cf0a66fc266",
    },
    "site-china-cycle-phase": {
        "short": "China cycle phase tape and falsifier ledger published to the site — null until the China cycle phase build lands.",
        "full": "The China cycle phase builder writes this artifact carrying the phase tape and the accompanying falsifier ledger. The producer is part of a parallel build wave not yet merged into this tree, so the artifact is null for now — the spine degrades gracefully on its absence. When the build lands, the phase tape and falsifier ledger stores will begin accruing, and the mastermind context reader will pick up the China cycle state. Read by the China market state engine.",
        "src_fp": "d4c954f030a161fd",
    },
    "site-china-market-state": {
        "short": "China sovereign spine: phase, participation, microstructure, policy, rotation, macro, external, and allocation — context only.",
        "full": "The China market state builder assembles the W1 through W4 China lobe artifacts — phase, participation, microstructure, policy, rotation, macro, external, and allocation — into one sovereign spine. No fused composite score is emitted. Authority is context-only. Read by the world state engine, the mastermind context builder, the daily brief engine, and the ask-brain China router.",
        "src_fp": "f6b3de953945780c",
    },
    "site-china-standouts": {
        "short": "China standouts list with three lifecycle zones: ready, basing, and falling — display only, no scored path surface on zone keys.",
        "full": "The China library builder writes this site-published standout list. It carries three zone keys beyond the existing buy shelf: ripening (ready and basing, cap 32), ripening-falling (falling sink, cap 8), and the existing buy shelf. Zone assignment follows a hard precedence cascade: falling veto first (five-day return at or below negative eight percent, or daily MACD histogram negative with falling trend), then ready (directional evidence live), then basing. Ordering within each zone uses MACD bars to cross ascending as the primary key. The zone keys carry no scored path surface and are not wired to alert triage, board ordering, or push floor. Read by the China builder, the signal contracts exporter, the stock open backfiller, and the mastermind context builder.",
        "src_fp": "a31ab7fc6382db26",
    },
    "site-confluence-graph": {
        "short": "Site mirror of the confluence graph, fetched client-side by the committee page — display only.",
        "full": "Copied by the site builder from the data copy in the daily-engine step. Read by the committee page typed-graph panel and the AI brief context sidebar. SLA mirrors the data-side entry at 30 hours on the daily-engine cadence, and freshness is judged on when the mirror was produced rather than the content date: the nightly health build runs before the same night's site copy, so the mirror always trails the data side by one cycle at judgment time by design. Display only — no authority.",
        "src_fp": "c137fab4b565cdf3",
    },
    "site-context-risk": {
        "short": "Site mirror of the board composition risk lens, written atomically alongside the data copy — display only.",
        "full": "The context risk builder writes this file atomically alongside the canonical data copy. Content is byte-identical to the data copy. No in-repo reader has been wired to this site path yet; it is a machine-readable mirror and a candidate for future theme-page or committee-page wiring. Display only, no authority.",
        "src_fp": "a30d99ba05cbcea5",
    },
    "site-cortex-memo": {
        "short": "Site mirror of the AI reviewer's nightly memo — read by the committee brief widget and the cortex deliberation panel.",
        "full": "The cortex engine writes this file atomically alongside the canonical data copy. Note the path name difference: the data copy uses a subdirectory while the site copy uses a flat name. Read by the AI brief widget and the cortex deliberation panel on the committee page. SLA mirrors the data-side entry at 30 hours on the nightly-cortex cadence. Display only — no authority.",
        "src_fp": "c372c8705a82274d",
    },
    "site-covariance-spine": {
        "short": "Site mirror of the covariance spine for frontend display — exact copy, display only.",
        "full": "The covariance spine builder writes this file atomically alongside the data copy. Byte-identical to the data copy. Intended for frontend consumption of structural independence data. No authority over any decision surface.",
        "src_fp": "28e5ef449ec6b76b",
    },
    "site-factor-intelligence-state": {
        "short": "The public-site copy of the factor intelligence state, byte-identical to the canonical version.",
        "full": "This is the public-site mirror of the factor intelligence state feed, written atomically alongside the canonical data copy by the same factor-analysis job. The two files are always in sync. It is context and display only with no consumers currently reading it from the public site.",
        "src_fp": "26d99706bb006b9a",
    },
    "site-golden-signals": {
        "short": "Daily snapshot of the key signals used as a conformance baseline to detect unexpected changes.",
        "full": "The signal-export process writes a snapshot of the key signals along with a hash of its inputs. Three consumers read this to verify that signal values match what was produced and that nothing changed unexpectedly between runs. It functions as an integrity check for the pipeline.",
        "src_fp": "067a74de2b8050a1",
    },
    "site-kernel-families": {
        "short": "Site mirror of the per-engine decay diagnostics, fetched client-side by the committee page — display only.",
        "full": "Copied by the site builder from the data copy in the daily-engine step. Read by the committee page per-engine-family decay diagnostics panel. SLA mirrors the data-side entry at 30 hours on the daily-engine cadence. Display only — no authority.",
        "src_fp": "7bdbb44757f9c4a5",
    },
    "site-kernel-half-lives": {
        "short": "Site mirror of signal decay curves by engine — fetched client-side by the committee page, all currently null — display only.",
        "full": "Copied by the site builder from the data copy in the daily-engine step. Read by the committee page holding-horizon half-life chip display. Because grading data is still accumulating, the honest expected result is that all families are null. SLA mirrors the data-side entry at 30 hours on the daily-engine cadence. Display only — no authority.",
        "src_fp": "80ab5048a3edb5b5",
    },
    "site-liquidity-plumbing": {
        "short": "Site mirror of the liquidity plumbing lobe, fetched client-side by the committee page — display only.",
        "full": "Copied by the site builder from the data copy in the daily-engine step. Read by the committee page liquidity-plumbing lobe panel. Content as_of trails produced_at by one to two days due to the FRED T+1 or T+2 publication lag; freshness checking uses produced_at rather than as_of so the lobe is not penalised for the structural data lag. SLA mirrors the data-side entry at 30 hours on the daily-engine cadence. Display only — no authority.",
        "src_fp": "9cc2969ba6a06990",
    },
    "site-mechanism-pathways": {
        "short": "Site mirror of the mechanism pathways artifact, fetched client-side by the committee page — display only.",
        "full": "The mechanism pathways builder writes this file atomically alongside the data copy. Exact copy of the data artifact. Read by the committee page for client-side display of the market move attribution block. Display and context only — no authority.",
        "src_fp": "c873e26a819487c4",
    },
    "site-neuralweb-daily-brief": {
        "short": "The public-site copy of the Neural Web daily brief, read by the committee page.",
        "full": "This is the public-site mirror of the Neural Web daily brief, written atomically alongside the data copy by the same script. The committee page on the public site reads this copy to display the daily summary to users. It is display and operations only with no authority.",
        "src_fp": "b6bfbdf280d13aa7",
    },
    "site-neuralweb-governance-recent": {
        "short": "Last 20 governance-ledger events distilled for the committee page — display only, event recency is not a freshness signal.",
        "full": "The site builder distils the last 20 governance-ledger events in chronological order each nightly run. Malformed lines are skipped; a failed distil never breaks the site render. Because the source ledger accrues only five to twenty events per quarter, event recency is explicitly not a freshness signal — the 30-hour SLA covers only the nightly re-render. The envelope rides in a sidecar file because a top-level JSON array cannot carry in-line envelope keys. Read by the committee page for display. No authority.",
        "src_fp": "422faf4073bde6a3",
    },
    "site-neuralweb-health": {
        "short": "The public-site copy of the Neural Web health status file, for the admin panel and frontend to read.",
        "full": "This is the public-site mirror of the Neural Web health status, written atomically alongside the data copy by the same script. It is display and operations use only with no authority. The admin panel and frontend consume this copy to show lobe status.",
        "src_fp": "c190ef7d01fb95ca",
    },
    "site-neuralweb-health-history": {
        "short": "Last 14 NW health run records distilled for the committee page — display only.",
        "full": "The site builder distils the last 14 health run records newest-last each nightly run. Malformed lines are skipped; a missing or malformed ledger never breaks the site render. The envelope rides in a sidecar file because a top-level JSON array cannot carry in-line envelope keys. The 30-hour SLA covers the nightly re-render; run-date recency is not a freshness concern because each nightly run appends a new row regardless. Read by the committee page. No authority.",
        "src_fp": "861ce9193cf131f6",
    },
    "site-neuralweb-market-plane": {
        "short": "Site mirror of the macro header feed for the Terminal top bar and committee hero — byte-identical twin, display only.",
        "full": "The mastermind context builder writes this file as a byte-identical copy of the stamped canonical in the same atomic call. Serves the Terminal product's top-bar macro header via an external pull of the site folder and the committee hero strip via client-side fetch. All fields fail open to nulls with gaps entries. Context only — all authority booleans are false.",
        "src_fp": "16cfbac557f91157",
    },
    "site-neuralweb-mastermind-context": {
        "short": "The public-site copy of the Terminal bridge feed, byte-identical to the canonical version.",
        "full": "This is the public-site copy of the Neural Web to Terminal bridge feed, written at the same time as the canonical data copy. The Terminal product's sync process picks this file up automatically as part of its existing site-folder checkout, with no new sync infrastructure required. It is context only and carries no authority.",
        "src_fp": "332a083b7ac6a113",
    },
    "site-neuralweb-orchestrator-runlog": {
        "short": "Published site copy of the orchestrator run log, last 60 runs and last 12 reviews — read by the admin Observatory.",
        "full": "The orchestrator log builder writes this envelope-stamped dict-root copy containing the last 60 run entries and the last 12 review rows. The admin Observatory Master Brain page reads this artifact. Context only — no authority.",
        "src_fp": "4c9894c3b1a183a0",
    },
    "site-neuralweb-ruling-graph": {
        "short": "Advisory air-traffic-control artifact for multi-agent sessions: open PRs, file collisions, and recent merges — display only.",
        "full": "The ruling graph builder reads the source-of-truth registry and produces this artifact. Records open PRs with file lists and protected-path flags, pairwise file collision pairs, and recent merges from a 14-day window. The builder fails open when the GitHub CLI is unavailable: it exits cleanly without touching the file. Advisory only — gates nothing in CI or the pipeline. Public rows only. Display and context only with authority ceiling at explain-only; all authority booleans are false. Regenerated on demand at PR time rather than on a nightly schedule.",
        "src_fp": "a9c9def77b47a937",
    },
    "site-qledger-track-record": {
        "short": "Daily track-record output for the signal ledger, combining raw grades and ladder states.",
        "full": "Two processes write to this file in sequence: the signal-ledger engine first emits the core track record, then a grading script merges in ladder-state information. Both writes are additive — neither overwrites the other's data. The result is published to the public site and read by seven downstream consumers.",
        "src_fp": "ddfbdaff9f2e6a44",
    },
    "site-radar-ticker": {
        "short": "Daily ticker-level Risk Radar data published to the public site.",
        "full": "The radar builder assembles per-ticker Risk Radar data and writes it to the public site each day. Six other parts of the system read this feed. It provides the ticker-resolution view of risk conditions that complements the broader market-state signals.",
        "src_fp": "26e960ae67900d05",
    },
    "site-riskdata-scorecard": {
        "short": "Cross-market Risk Radar track record: hit rates and graded counts for US, China, Hong Kong, Canada, and seven intl markets — display only.",
        "full": "The Risk Radar scorecard engine uses 100% deterministic math over already-graded forward-ledger rows — no language model, no model scores. Hit rates are null when fewer than five graded entries exist. Covers eleven markets: US, China, Hong Kong, Canada, Korea, Japan, Taiwan, India, Australia, UK, and Eurozone. Market keys under schema v1 are additive-only — consumers must tolerate unknown keys. The mastermind lobe reads only the four main markets. Display and context only; nothing here may gate, rank, size, or escalate.",
        "src_fp": "137b3586dd4d6c65",
    },
    "site-theme-asymmetry": {
        "short": "Site mirror of the per-leg theme asymmetry panel — wired to the state-of-themes page drawer and ask-brain read tool.",
        "full": "The thematic state builder writes this file as the site projection of the theme asymmetry data artifact. The state-of-themes page has read this file since TIL W4 (PR #2137) for the 7-dot Legs column and hover tips; the 2026-07-17 audit erroneously flagged it as having no reader because it checked consumers: rather than code. Wired 2026-07-18 to a new drawer expansion section (Setup legs plain-word rows) and the ask-brain read tool read_theme_asymmetry. Display and context only — no fused master number (WA-R1).",
        "src_fp": "adcae6f5b3bf65a5",
    },
    "site-theme-pathways": {
        "short": "Site mirror of the theme beneficiary and loser pathway graph — display only, read by the ask-brain tool.",
        "full": "The thematic state builder writes this file as the site projection of the theme pathways data artifact. The pathways graph maps supply-chain beneficiaries and losers for each canonical theme. Loser legs are avoid-shaped evidence, not short calls. Read by the ask-brain tool for theme context. Display and context only.",
        "src_fp": "75e5bcaae48f9fd6",
    },
    "site-theme-state": {
        "short": "Site mirror of the thematic composition organ — read by the state-of-themes page and ask-brain.",
        "full": "The thematic state builder writes this file atomically alongside the data copy. Tolerant-read composition over foresight cascade, basket theme intelligence, radar divergence flags, narrative emergence overlap, subsector rotation quadrants, and divergence log. Missing inputs produce stale-legs entries rather than exceptions. Read by the state-of-themes page and the ask-brain tool. Display and context only — all authority booleans are false.",
        "src_fp": "8e69e2d21d827c90",
    },
    "site-theme-thesis": {
        "short": "Site mirror of the theme thesis ledger — latest record per theme with falsifier status, read by multiple NW engines.",
        "full": "The thematic state builder writes this file as the site projection of the theme thesis ledger. Carries the latest versioned thesis record per theme compiled from the curated thesis registry, including machine-checkable falsifier status. Read by the ask-brain tool, the world state engine, the mastermind context builder, and the daily brief engine. Display and context only.",
        "src_fp": "2655c4c92f392a60",
    },
    "site-us-standouts": {
        "short": "Daily list of US stock standouts published to the public site and read by the Terminal screener.",
        "full": "Each day the engine scores US stocks and writes the resulting standout list to the public site. This feed is the anchor contract for the Terminal product's stock screener — any downstream tool that reads standout data relies on it. It has 16 consumers, making it one of the most widely read feeds in the system.",
        "src_fp": "257c11198cf0dda2",
    },
    "special-sits-context-latest": {
        "short": "",
        "full": "",
        "src_fp": "f646afda96a036a5",
    },
    "spine-index": {
        "short": "The master searchable table joining every engine's recent signal history, rebuilt fresh each night.",
        "full": "Each night the system rebuilds a unified table that joins signal history from all major engines: US, Hong Kong, Canada, and China boards, the signal ledger, and sector-cycle forward logs. It also pulls in graded rows from the track-record store. Because it is a fully rebuilt derived view rather than a running ledger, overwriting it each night is correct. Several source ledgers are still pending formal registration in a future cleanup sweep.",
        "src_fp": "7a23127513aaf65e",
    },
    "theme-asymmetry": {
        "short": "Per-leg asymmetry panel for each canonical theme — bottleneck, consensus gap, dislocation, crowding, and orthogonality — no fused score.",
        "full": "The thematic state builder computes this internal data artifact for per-theme asymmetry. Seven legs are computed independently: bottleneck tightness, stale-consensus gap, cyclical dislocation, entry cleanliness, crowding hazard, falsifier clarity, and orthogonality. The ownership and attention legs are hazard context only. No fused master number is permitted. The hard caveat embedded in the artifact states explicitly that this is not a buy score and that no behavior-changing consumer is wired. Read surface is the site projection (site-theme-asymmetry) — state_of_themes page and ask_brain read tools; data/ copy remains the primary artifact.",
        "src_fp": "0ae4db926fb7644b",
    },
    "theme-pathways": {
        "short": "Theme beneficiary and loser pathway graph compiled from the curated pathway registry — display only, no runtime escalation.",
        "full": "The thematic state builder reads the curated pathway registry to produce this graph following the mechanism pathways schema conventions at theme supply-chain granularity. Loser legs are avoid-shaped evidence, not short calls. Includes a purity-weighted cross-theme node-collision map. Runtime shock-to-beneficiary escalation is an explicitly forbidden use. No in-repo consumer is wired to the data copy — the site mirror is read by the ask-brain tool.",
        "src_fp": "4cf30e315f3c4683",
    },
    "theme-phase-history": {
        "short": "Point-in-time phase history tape for all 18 canonical themes — append-only, one row per transition or weekly heartbeat.",
        "full": "The thematic state builder appends one row per theme per as_of date when a state transition occurs or on a weekly heartbeat. Fields include foresight stage, scoring lifecycle, radar lifecycle, divergence quadrant, evidence z-score, and a hash-chain field linking to the prior row. The nightly pipeline is the sole advancer. The tape is read by the thematic state builder to derive current state. First promotion-eligible read is expected in October 2026.",
        "src_fp": "f875255fb62d09b1",
    },
    "theme-state": {
        "short": "Thematic composition organ assembling foresight, basket intelligence, radar flags, and rotation quadrants — display only.",
        "full": "The thematic state builder produces this primary composition artifact. Tolerant-read composition reads from the foresight cascade, basket theme intelligence, radar divergence flags, narrative emergence ticker overlap, subsector rotation quadrants, and the divergence log latest-per-theme. Each missing input produces a stale-legs entry and a null block; the builder always exits cleanly. Read by the world state engine, ask-brain tool, mastermind context builder, daily brief engine, and brief context builder. All authority booleans are false.",
        "src_fp": "72f09076e95ca26a",
    },
    "theme-thesis-ledger": {
        "short": "Append-only versioned thesis records for each canonical theme, compiled from the curated thesis registry with machine-checkable falsifiers.",
        "full": "The thematic state builder compiles this ledger from the curated thesis registry. Records are versioned and re-emitted only when the content hash changes. The ledger covers class-level winner and loser taxonomy only — per-stock thesis records are forbidden by design. Falsifier tripwires are evaluated via a domain-specific language embedded in the registry. Read by the thematic state builder to derive the latest thesis per theme for the site projection.",
        "src_fp": "cc07bd7fe36f547a",
    },
    "treasury-watch": {
        "short": "Intraday TGA cash-flow detector with episode state — written each time the TGA moves, display only.",
        "full": "The White House pipeline builder wraps the treasury watch engine to detect the current TGA release or rebuild episode, using a quarter-end-preferred anchor to keep the episode ID stable across hourly sentinel runs. Sources: the TGA data store for level data (converted from millions to billions), the liquidity plumbing artifact and regime latest for context. Each missing input yields nulls and a gaps entry rather than an exception. Written idempotently — a quiet hour is a no-op. Rendered on the Treasury Watch panel of the White House page. Also read fail-soft by the Mastermind bot's treasury context layer, dark-shipped by default. The Treasury DTS API publishes each business day around 20:00 UTC the following day, so the inner as_of is structurally one to two calendar days back at morning build time; the sentinel advances it each evening after publication. SLA is 48 hours to accommodate this structural lag.",
        "src_fp": "d2e68db603783d3e",
    },
    "world-state": {
        "short": "A daily one-page snapshot of the full market state: regime, risk, breadth, alerts, and data health.",
        "full": "Each day this feed assembles the current market regime, risk-radar verdict, breadth conditions, sector-rotation summary, data-health status, and alert census into one unified snapshot. Any unavailable source leaves that section null rather than fabricated — gaps are listed explicitly. Ten other parts of the system read this feed. A planned qualitative-intelligence section is currently null, pending a cross-team ruling.",
        "src_fp": "280c564245a5e3d4",
    },
}
