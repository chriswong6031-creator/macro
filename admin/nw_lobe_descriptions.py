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
        "short": "",
        "full": "",
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
        "src_fp": "d3b2cbe35a292ef0",
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
    "confluence-graph": {
        "short": "A map of which signals tend to agree or conflict — shown for context only, never changes any decision.",
        "full": "This feed builds a map where nodes are engines, sectors, regimes, and theses, and links show how they relate: structural wiring, historical co-firing, lead-lag timing, and detected contradictions. The contradiction detector currently watches six specific signal pairs. Every link is display-only — this map never gates alerts, raises priorities, or changes rankings. Promoting any link to decision use requires its own separately registered validation study.",
        "src_fp": "2e87b9de964df238",
    },
    "context-candidates": {
        "short": "",
        "full": "",
        "src_fp": "df77fb74704493da",
    },
    "context-risk": {
        "short": "",
        "full": "",
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
        "short": "",
        "full": "",
        "src_fp": "4c384a9319ffafee",
    },
    "covariance-spine-history": {
        "short": "",
        "full": "",
        "src_fp": "cde97c269bfed318",
    },
    "cycle-pattern-state": {
        "short": "",
        "full": "",
        "src_fp": "76104926fef20113",
    },
    "dt-contra-state": {
        "short": "",
        "full": "",
        "src_fp": "eef3af10ebddce16",
    },
    "entity-thesis-mechanism-registry": {
        "short": "",
        "full": "",
        "src_fp": "161761b3e23173b0",
    },
    "evidence-clock": {
        "short": "",
        "full": "",
        "src_fp": "096288451a0909aa",
    },
    "evidence-clock-reviews": {
        "short": "",
        "full": "",
        "src_fp": "44f0d5bd64b017bf",
    },
    "factor-contradictions-ledger": {
        "short": "Append-only log of days when the factor pair signals borrowed strength from each other — display only.",
        "full": "When the factor analysis detects a contradiction between the factor pair's signals — where one factor's apparent strength may be borrowed from the other — a record is appended here keyed by date and stock. All entries are display-only and all are currently marked as informational notes rather than warnings. The ledger remains dormant until the factor panel has at least 60 distinct dates of history.",
        "src_fp": "fab37061327f82e9",
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
        "short": "",
        "full": "",
        "src_fp": "277f5806406db13f",
    },
    "machine-registry": {
        "short": "The official ledger of research hypotheses proposed by the AI reviewer and formally registered for tracking.",
        "full": "This append-only ledger records every research hypothesis the AI reviewer has formally registered, including the question, the pre-committed decision criteria, the time horizon, and a come-back date for review. A hard budget of three new registrations per calendar week applies — to add a new one, an old one must be retired. No scoring surface may read this ledger for decision-making; it is context and record-keeping only.",
        "src_fp": "15658cf62ffd9472",
    },
    "mechanism-pathways": {
        "short": "",
        "full": "",
        "src_fp": "f5b7ebc6fff87d6d",
    },
    "mechanism-pathways-history": {
        "short": "",
        "full": "",
        "src_fp": "a877a25246d46445",
    },
    "nasdaq-internals": {
        "short": "",
        "full": "",
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
    "neuralweb-health": {
        "short": "Machine-readable status of every Neural Web lobe, updated in two phases each day by the engine and the AI reviewer.",
        "full": "This file provides the operating status for all Neural Web lobes in a machine-readable format. The engine job writes a first pass using the previous day's AI reviewer status; then the AI reviewer job rewrites the reviewer section with the current run's result. Data-only lobes stored in cloud storage are reported as not locally verifiable rather than missing. This file has no authority over engine behavior — it is for display and operations monitoring only.",
        "src_fp": "6c057bd7036b09e0",
    },
    "neuralweb-mastermind-context": {
        "short": "The daily bridge feed packaging Neural Web context for the Terminal product — context only, no authority.",
        "full": "Each day this feed assembles a curated package of Neural Web context — market state, reliability summaries, detected contradictions, bottom-sensor readings, options-entry context, and the AI reviewer note — formatted for the Terminal product to read. Its candidate list draws from US standouts, alternative data, and radar tickers, capped at 250 rows. All five authority switches are off: this is context only. The Terminal product stays the decision-maker.",
        "src_fp": "af9df5338e5c1483",
    },
    "nw-health-run-history": {
        "short": "",
        "full": "",
        "src_fp": "71bdaa94919c4ae4",
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
        "short": "",
        "full": "",
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
        "short": "An advisory ranked list of research candidates from the AI reviewer's pipeline — purely informational.",
        "full": "This feed ranks potential research items from the hypothesis inbox, the registered-hypothesis ledger, the signal-species registry, and the trial ledger into buckets: high value to build now, blocked by missing data, too sparse, duplicate of existing work, or invalid shape. It is advisory only — the formal registration process stays the sole gatekeeper for what gets pursued. It is off the nightly render path and holds no authority over rankings, alerts, or sizing.",
        "src_fp": "55b648e23eae4346",
    },
    "risk-radar-review-log": {
        "short": "Audit trail of every proposed change to the Risk Radar, including whether a safety backtest passed or failed.",
        "full": "Each time a change to the Risk Radar is proposed or reviewed, a record is added to this log. The log captures the proposal, the outcome of a do-no-harm backtest, and any apply or reject decisions. It is append-only, meaning nothing is ever removed. Changes to what the Risk Radar is allowed to do are also recorded in a separate system-wide governance log.",
        "src_fp": "62ef64b5ba854386",
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
        "short": "",
        "full": "",
        "src_fp": "5561d4d16c467a5d",
    },
    "site-causal-lab-state": {
        "short": "Public-site copy of the CHF lab heartbeat, byte-identical to the data copy.",
        "full": "This is the site-published copy of the causal lab state, written at the same time by the causal frontier builder. It is the preferred read source for the admin Causal Lab panel and for any future committee display surface. Byte-identical to the data copy. Display-only context artifact with not-a-signal status unconditionally.",
        "src_fp": "03680cf0a66fc266",
    },
    "site-china-cycle-phase": {
        "short": "",
        "full": "",
        "src_fp": "d4c954f030a161fd",
    },
    "site-china-market-state": {
        "short": "",
        "full": "",
        "src_fp": "f6b3de953945780c",
    },
    "site-context-risk": {
        "short": "",
        "full": "",
        "src_fp": "a30d99ba05cbcea5",
    },
    "site-covariance-spine": {
        "short": "",
        "full": "",
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
    "site-mechanism-pathways": {
        "short": "",
        "full": "",
        "src_fp": "c873e26a819487c4",
    },
    "site-neuralweb-daily-brief": {
        "short": "The public-site copy of the Neural Web daily brief, read by the committee page.",
        "full": "This is the public-site mirror of the Neural Web daily brief, written atomically alongside the data copy by the same script. The committee page on the public site reads this copy to display the daily summary to users. It is display and operations only with no authority.",
        "src_fp": "b6bfbdf280d13aa7",
    },
    "site-neuralweb-health": {
        "short": "The public-site copy of the Neural Web health status file, for the admin panel and frontend to read.",
        "full": "This is the public-site mirror of the Neural Web health status, written atomically alongside the data copy by the same script. It is display and operations use only with no authority. The admin panel and frontend consume this copy to show lobe status.",
        "src_fp": "32f95c6fd368941c",
    },
    "site-neuralweb-mastermind-context": {
        "short": "The public-site copy of the Terminal bridge feed, byte-identical to the canonical version.",
        "full": "This is the public-site copy of the Neural Web to Terminal bridge feed, written at the same time as the canonical data copy. The Terminal product's sync process picks this file up automatically as part of its existing site-folder checkout, with no new sync infrastructure required. It is context only and carries no authority.",
        "src_fp": "332a083b7ac6a113",
    },
    "site-neuralweb-ruling-graph": {
        "short": "",
        "full": "",
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
    "site-theme-asymmetry": {
        "short": "",
        "full": "",
        "src_fp": "f97bf8dc53c56128",
    },
    "site-theme-pathways": {
        "short": "",
        "full": "",
        "src_fp": "75e5bcaae48f9fd6",
    },
    "site-theme-state": {
        "short": "",
        "full": "",
        "src_fp": "8e69e2d21d827c90",
    },
    "site-theme-thesis": {
        "short": "",
        "full": "",
        "src_fp": "2655c4c92f392a60",
    },
    "site-us-standouts": {
        "short": "Daily list of US stock standouts published to the public site and read by the Terminal screener.",
        "full": "Each day the engine scores US stocks and writes the resulting standout list to the public site. This feed is the anchor contract for the Terminal product's stock screener — any downstream tool that reads standout data relies on it. It has 16 consumers, making it one of the most widely read feeds in the system.",
        "src_fp": "257c11198cf0dda2",
    },
    "spine-index": {
        "short": "The master searchable table joining every engine's recent signal history, rebuilt fresh each night.",
        "full": "Each night the system rebuilds a unified table that joins signal history from all major engines: US, Hong Kong, Canada, and China boards, the signal ledger, and sector-cycle forward logs. It also pulls in graded rows from the track-record store. Because it is a fully rebuilt derived view rather than a running ledger, overwriting it each night is correct. Several source ledgers are still pending formal registration in a future cleanup sweep.",
        "src_fp": "7a23127513aaf65e",
    },
    "theme-asymmetry": {
        "short": "",
        "full": "",
        "src_fp": "2283b351521c4ebd",
    },
    "theme-pathways": {
        "short": "",
        "full": "",
        "src_fp": "4cf30e315f3c4683",
    },
    "theme-phase-history": {
        "short": "",
        "full": "",
        "src_fp": "f875255fb62d09b1",
    },
    "theme-state": {
        "short": "",
        "full": "",
        "src_fp": "72f09076e95ca26a",
    },
    "theme-thesis-ledger": {
        "short": "",
        "full": "",
        "src_fp": "cc07bd7fe36f547a",
    },
    "world-state": {
        "short": "A daily one-page snapshot of the full market state: regime, risk, breadth, alerts, and data health.",
        "full": "Each day this feed assembles the current market regime, risk-radar verdict, breadth conditions, sector-rotation summary, data-health status, and alert census into one unified snapshot. Any unavailable source leaves that section null rather than fabricated — gaps are listed explicitly. Ten other parts of the system read this feed. A planned qualitative-intelligence section is currently null, pending a cross-team ruling.",
        "src_fp": "280c564245a5e3d4",
    },
}
