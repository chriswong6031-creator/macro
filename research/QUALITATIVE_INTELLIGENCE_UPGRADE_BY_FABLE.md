# Qualitative-Intelligence Upgrade — by Fable

*Fable solution pass, 2026-07-02. Inputs: the four problem audits (`QUALITATIVE_INTELLIGENCE_MASTERPLAN.md`, `QUALITATIVE_SIGNAL_US_AUDIT_FOR_FABLE.md`, `QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md`, `NEWS_FEED_PROBLEM_AUDIT_FOR_FABLE.md`) plus six feasibility probes run against the live repo and web (instant-grading backfill; event-time/PIT audit; entity-resolver inventory; China official-corpora fetchability; LLM extraction economics; W0 fix verification). One fix already shipped during this pass: the China News dead render (macro#895 — artifacts unfrozen 06-22→07-01, JSON writes moved above render, silent except now logs). This document answers the audits' payload questions, specifies the solution mechanisms, and lays out the phased execution plan with delegation briefs. Probe facts are cited as [P1]–[P6].*

---

## 0. The design thesis

**The suite's problem is not weak signals — it is that nothing can ever become a strong signal, because "importance" is frozen fiat, outputs leak into scores without grades, and no loop ever closes.** The upgrade therefore does not begin by building better signals. It begins by building the machine that can tell a good signal from a bad one — a claim registry every scored number must pass through, a nightly scoreboard that grades every open claim against matched controls and a placebo tape, and a shadow lane where new legs run gradeable-but-unrendered. Only then do the new capabilities (events-over-vibes extraction, the China Communiqué Diff, the censorship guard) plug in — each born inside the accountability machine rather than promising to join it later. The near-term ceiling is honest unification; learned importance is deferred until the scoreboard has earned the labels. Every current "calibrated by the ledger" claim is a promise the system cannot keep; the roadmap's job is to make that promise honest for the first time — and the probes show it can start being honest **this week**, not in September: ~1,300 radar observations and all 133 alt-data theses are gradeable at 5d today, and the radar's 21d clock starts maturing 2026-07-11 [P1].

---

## 1. Decisions — answers to the payload questions

The four audits posed ~28 payload questions; they collapse into ten decisions.

**D1 — Events over vibes; extraction only where bodies exist. (masterplan Q1, news Q1/Q6)**
Headline-only feeds CAN support signal — but only for *detection and timing*: novelty, cross-source corroboration, velocity, echo-collapse. They can never support magnitude, negation, or verified meaning, and LLM extraction over 10–15-word titles fails its own citation guard by construction ([P5] R2: `_verify_citations` degrades every field to `unknown` without a body). So the ambition splits: the **wire layer is demoted to an event-detection trigger** (when did attention start, how broad, how novel), and **extraction runs only where bodies are already free** — EDGAR 8-K full text (~111/day, 75% already LLM-annotated in `events.parquet` [P5]), White House RSS `content:encoded`, China official policy corpora and CNInfo full-text, transcripts later. No body, no extracted field. Per-asset alpha from qualitative text is reachable only down the body-bearing lanes; the headline lanes are confirmers/timers and are labeled as such.

**D2 — Grade NOW; the scoreboard is the first build, not the last. (masterplan Q2/Q6, US Q2)**
The empty-ledger equilibrium breaks only if grading is decoupled from desks. One nightly grader — independent of every build script — grades every open claim at **5/21/63d simultaneously**, against (a) SPY / CSI300-ETF and (b) a sector-matched control, writing to ONE ledger keyed `(entity, date, desk, signal_id, horizon)`. Probe 1 verified the instant supply: alt-data's 133 theses carry PIT `entry_levels` and are re-scorable at 5/21d **today** (effort S); radar has ~1,328 obs ≥5d old (honest caveat: only 8 snapshot-dates → overlapping, autocorrelated — report `n_dates` beside `n_obs` and treat 5d as smoke-test, 21d as the honest horizon); the China event-move claim ("High-importance items' tickers move") is gradeable on ~172 tagged events against `510300.SS` with local price data. Deadline is real: radar's 21d clock matures from **2026-07-11**; the scoreboard must exist to catch it.

**D3 — The counterfactual comes from a placebo tape, not from grading the firehose. (masterplan Q2)**
Daily, sample K random low-importance events and grade them through the identical pipeline. High-importance items must beat the placebo tape, not zero. This yields negative labels at fixed cost, avoids survivorship (sample from full accrual, not the displayed feed), and turns "importance" into a falsifiable ranking claim from day one. Relevance grading (did the high band move more than placebo?) runs beside pick grading.

**D4 — Diffuse events get typed claims, not forced ticker proxies. (masterplan Q3, US Q3, news Q4)**
Claim types: `entity | basket | sector | macro`. Entity claims grade vs sector-matched control; basket/sector claims vs the matched sector ETF; **macro claims grade against a named machine-checkable observable declared at emit time** (a rate, an FX level, a breadth count) — if the emitter cannot name one, the claim is display-only and says so. This constrains the thesis generator to proxy-mappable calls; the fraction that goes dark under this constraint is itself logged and reported (the honest measure of how much "institutional value" the proxy-vs-SPY frame was discarding). Policy Watch's 13 open soft-falsifier predictions [P1 — audit's 39 was stale] get a subject→proxy map where possible; the rest become explicitly display-only.

**D5 — One schema, two heads; China direction priors are frozen out of learning until the backfill lands. (masterplan Q4, CN Q2/Q5)**
Importance is ONE schema with region-specific feature heads and separate calibration. The China contrarian sign (`sign_expected=-1`, n_obs=0) is structurally unfalsifiable on the 19-day tone series — but **not permanently**: `ak.news_cctv` reaches back to 2016-02 (~3,800 days, order-preserving) [P1, P4]. So: demote the sign to **weight-0 direction / salience-only immediately**, run the CCTV backfill in W4, and let the sign earn its way back through the gate on a decade of tone history. No China direction prior enters any learned model before that.

**D6 — Learning is deferred; novelty-first v0 ships in shadow; ONE feature gets the controlled experiment. (masterplan Q7, US Q5, news Q2/Q7)**
At solo-shop label velocity a learned importance model is not justified yet. The near-term ceiling: a **novelty-first deterministic v0** — `importance_v0 = f(novelty-z vs trailing entity/theme window, cross-source corroboration within event_key, source_tier, scheduled-surprise validity)` with attention-crowding as a *penalty* — running in the shadow lane, champion-challenger against the hand formulas, graded daily. Learning (logistic/GBM, ≤8 features) begins only when the scoreboard holds ≥500 graded relevance labels. The controlled experiment the payloads demand: **cross-source corroboration count** (the single most theoretically-defensible qualitative feature) is nominated to bind a capped ≤0.10 confirmer weight in `radar_plus` — after, and only after, it clears the promotion gate (§3). Everything else stays shadow. "Narrative" is reserved for the text pipeline; `narrative_rotation` is relabeled thematic momentum (copy change, W6).

**D7 — The lexical-regime legs are re-aimed once, then retired if they fail. (news Q3)**
phase0 falsified EPU/GPR on forward-vol-incremental-over-VIX — the one clean kill in the suite. The salvage test they never got: the VIX-orthogonal residual aimed at a target VIX cannot price (cross-sectional dispersion / complacency-fade timing), run once through the same phase0 harness in shadow. Pass → bounded display-to-confirmer promotion; fail → retire the family entirely rather than leaving it pinned-off forever. SF-Fed sentiment-z gets the same single harness run. One shot each; no perpetual deferral.

**D8 — The Missing-Tape Index pivots to official-corpus diffs + onshore/offshore divergence. (CN Q3)**
Probe 4 falsified the naive design: vendor permalinks show ~0% rot at 5–10d (content-addressed URLs), so deletion-tracking of the *aggregator* tape detects nothing. The censorship guard becomes three legs, all verified feasible: (a) **body-hash snapshots of official corpora** at first fetch (People's Daily layout pages, gov.cn, Xinhua readouts — store sha256(body), recrawl T+3/T+7, diff = quiet re-edit/pull detection; requires a new capture field, no vendor dependence); (b) **onshore-zh vs offshore-en GDELT tone divergence** — `sourcelang` cleanly separates the populations, `timelinetone` gives the series, 1req/5s pacing [P4]; (c) lianbo topic-share collapse anomaly (a theme abruptly vanishing from broadcast order). Emitted as a *risk flag with confidence tiers*, never as a positive signal; an abnormal attention-collapse marks a series "possibly suppressed," not "demand fell."

**D9 — China is a context/overlay layer with ONE path to standalone alpha: discrete phrase-diff events. (CN Q1/Q4/Q7)**
Bag-of-words tone can never carry the load; the signal is in ordering, elevation, and formula shifts — and probes confirm the raw material is free and structured: lianbo row order = broadcast order; People's Daily layout page = editorial prominence; PBOC/State Council/NDRC/CSRC all fetch as dated static HTML [P4]. The **Communiqué Diff engine** emits discrete dated events ("适度宽松 reappeared after N days absent"; "房住不炒 dropped from the readout"; "lead item shifted tech→property") from a ~44-formula human-reviewed phrase book ([P4] seed delivered) plus an unsupervised novelty score against the running language distribution — supervised phrase→return mapping is deferred (no leak-free history; CSMAR is the stretch buy if ever needed). Because events accrue across six organs (multiple per week, not four readouts a year), a forward log becomes meaningful within months. Sizing bar for ANY China leg: the §3 gate + regime-stratification + `n_dates ≥ 25`; until then China desks are salience/context, honestly labeled.

**D10 — The MNPI/mosaic boundary gets written, and the UI stops laundering promises. (masterplan Q8, US Q1/Q6, CN Q6)**
A compliance note (`docs/QUAL_DATA_COMPLIANCE.md`) records: public-source-only inventory; expert networks and card panels excluded (US: MNPI supervision burden; China: hard legal line post-Capvision); the corroboration engine aggregates only public regulatory/published text — centralization changes convenience, not the legal character of the inputs, and the boundary is a deliberate documented scope. On the UI: every displayed conviction/score carries a machine-derived state chip — **UNGRADED n=0 / ACCRUING n<25 / GRADED hit% [CI]** — from the scoreboard, and "graded vs SPY"-class copy is generated from the ledger state, never hand-written. Promise-to-grade can no longer render as accountability. — codified in `docs/QUAL_DATA_COMPLIANCE.md`.

---

## 2. The five mechanisms

### 2.1 The Claim Passport (kills the firewall-leak class)
Any numeric field consumed by arithmetic on a rendered page must reference a registered claim: `{claim_id, desk, entity/scope, direction, horizon_d, falsifier, entry_levels, check_by, ledger_ref}`. Enforcement is a **build-time linter** (the repo already has the pattern: `validate_signals.py` §7 gate, `check_nav_mega`): a static map of scored-consumer files; any read of an unregistered field fails the build. Alt-Data `signal_score`→3 engines and Policy lean→`intel_hub` become impossible categories of bug, not fixed instances. Interim (W0): consumption gates on the artifact's own confidence/n — the values already computed and discarded at the boundary.

### 2.2 The Universal Scoreboard (qledger)
One nightly job, independent of all renders: matures every open claim at 5/21/63d vs benchmark AND sector-matched control; writes one ledger; computes per-desk and **per-feature-slice** hit rates (does tier-1 beat tier-3? does high-novelty beat echo? does a distinct-member congress cluster beat an alt-data convergence count?); runs the placebo tape (D3); publishes `site/qledger/track_record.json` that every desk's UI chip reads. Embargo rules follow the [P2] `timestamp_quality` enum (`CRAWL_BOUNDED` no embargo; `PUBLISHER_STATED` +15min and reject pubDate < crawl−48h; `DISCLOSURE_DATE` +1 business day; `EVENT_DATE` never an entry anchor; `SNAPSHOT_DATE` display-only; `CORRUPTED` blocked+alert). Three PIT leaks get fixed at the source (W0): EDGAR backtest same-day-close entry → +1bd; China official cache `_clean_time` at write; WH RSS naive-TZ→ET.

### 2.3 Salience/direction decomposition
Every fused conviction splits into **salience** (|z| × relevance — what deserves attention) and **direction** (sign — which way), and unproven legs contribute to salience only. China's contrarian sign, alt-data's monotone-bullish fallback, policy's low-confidence leans all stop steering direction while keeping their attention value. Direction is earned through the gate; salience is honest immediately.

### 2.4 Events over vibes: the extraction lane
The [P5] `qual_extraction.v1` contract: version-pinned `model_id`, `source_id = sha256(body)`, enum fields (`direction/magnitude/horizon/reversibility/confidence`), **`quote_span` evidence verified verbatim against the body** (the `catalyst_tone._verify_citations` pattern, generalized), `dropped_fields`, `degraded_reason`, `is_context_only`. Degraded-mode rule (the alt-data lesson): `brain_usable = brain_present and not degraded_reason`; degraded output is ABSENT, not neutral — deterministic fallbacks must carry their own downside guards. Drift protocol: config-level pinned model ids (no literals — `altdata_brain.py:57` today), a frozen 50-text anchor set re-scored on any model change with `field_agree_rate ≥ 0.85` gate, jsonschema validation on every record, weekly 10-sample re-score monitor with Telegram alert. Cost is a rounding error: ~$10/mo Haiku for classify-all + top-slice extraction + 100 transcripts/quarter [P5] — spend discipline is about *drift and quality*, not dollars. Immediate hygiene (W0): `news_llm` computes fields nothing consumes while its `max_batches` cap silently drops 87% of the tape — either wire the consumer or default it off.

### 2.5 Hub-and-spoke as three services (qkernel / qledger / qbus)
No monolith. **qkernel**: one `event_id/norm_title/source_tier` + the layered EntityResolver — [P3] v0 design: CN 6-digit code-adjacency (~100% precision) → curated basket aliases → `GENERIC_NOUNS` blocklist (one entry, 机器人, causes 22/22 measured FPs; blocklist drops CN FP 14%→~1-2%) → boundary-guarded longest-match; US token+stopword scan + `name_resolver` (4,101 names; restore the absent SEC `company_tickers.json` to reach ~10k); CUSIP map promoted from smart_money. Learned NER, informal aliases (宁德→300750), and cross-lingual (英伟达→NVDA) are explicitly deferred. **qbus**: the unified item/event store with `_crawled_at`, `timestamp_quality`, body-hash, `event_key` clustering, novelty score, cross-desk echo detection (the same wire counted once, not three times). **qledger**: §2.2. Desks migrate by adapter, strangler-style; data writes always precede renders (the macro#895 class fixed architecturally); spokes keep independent failure domains with "broken ≠ quiet" health tri-state.

---

## 3. The promotion protocol (code-enforced)

A leg moves display → scored only through this ladder, and can move back:

1. **DISPLAY** — rendered, salience-eligible, no arithmetic on traded pages.
2. **SHADOW** — computed + claim-registered + graded nightly; never rendered as conviction.
3. **CONFIRMER** — after: `n_graded ≥ 25` **dates** (not overlapping obs), Wilson-CI lower bound of excess hit-rate vs matched control > 0 at the claim's own horizon, incremental information over price+VIX baseline (regime not level), block-bootstrap stability across date clusters. Binds ≤0.10 capped weight, tie-break/confirm only.
4. **SCORED** — composite-level re-validation (the Top-Pick lesson: the leg's *destination* must also pass — a valid leg inside a DSR-failing composite is still unshippable), plus 63d out-of-sample accrual.
- **AUTO-DEMOTION**: rolling-window CI falls below zero → back one rung, pinned with the `narrative_regime` precedent (`pinned_off`, reason string, date). Demotion is a normal state, not a failure to hide.

The gate is a shared function (`promotion_gate` generalized), and the Claim Passport linter refuses scored-context reads from any leg whose ladder state isn't CONFIRMER+.

---

## 4. The wave plan

| Wave | Scope | Exit criteria | Tier |
|---|---|---|---|
| **W0** Stop the bleeding (days) | 13 surgical fixes, briefs below | all merged; leaks gated; PIT fixed | Sonnet ×8 parallel worktrees, Opus review |
| **W1** Scoreboard (before 2026-07-11) | qledger schema+registrar over existing 7+ ledger dirs; nightly multi-horizon grader + matched controls + placebo tape; altdata 5/21d shadow grades (133 theses); radar multi-horizon incl. 21d catch; China event-move grader (~172 events); policy subject→proxy map; UNGRADED/ACCRUING/GRADED chips on alt_data + intelligence_hub | first non-zero `n_graded` published on-page; radar 21d maturation captured from day one | Opus design, Sonnet build |
| **W2** Kernel + bus | EntityResolver v0 [P3]; shared event_id/dedup; `_crawled_at` + `timestamp_quality` [P2]; event_key + novelty + echo detection; shadow lane infra; migrate `financial_news` + `china_news_intel` onto qkernel; fix US `news_vector` stale accrual (newest 2026-06-20); restore SEC company_tickers.json | one wire story = one event across all desks; CN tag FP <2% measured | Sonnet, Opus on resolver design |
| **W3** Honest importance v0 | novelty-first shadow score US+CN; salience/direction split in `china_intel` + `intel_hub` + altdata emit; promotion ladder + Claim Passport linter live; D7 one-shot re-aim harness for EPU/GPR + SF-Fed | v0 vs hand-formula champion-challenger accruing; linter enforced in CI | Opus |
| **W4** China legs | CCTV backfill 2016→now (~3,800 days, paced, gap-audited); Communiqué Diff v0 (5 corpora collectors from VPS + human-reviewed phrase book + diff events into qbus); Missing-Tape v0 (body-hash snapshots + GDELT divergence series, 1req/5s); contrarian sign demoted to salience-only until backfill grades | phrase-diff events flowing + graded; tone z on 10y baseline; sign verdict published | Opus design, Sonnet build, Haiku for backfill babysitting |
| **W5** Bodies + extraction | `qual_extraction.v1` on the existing 8-K lane (extend, don't rebuild [P5]); WH desk: diagnose-why-dark first (processed.json never existed → provider likely absent), force `--reeval` vs a known EO, commit ledger, CI smoke-gate; anchor set + drift monitor; news_llm consumer-or-off | extraction fields citation-verified; WH fires or is honestly retired | Sonnet, Haiku bulk |
| **W6** Earned weights | the D6 controlled experiment (corroboration count → capped radar_plus confirmer via the gate); congress net-directional cluster + fresh-sell veto rebuild; insider leg re-validation at composite level; costume renames (`narrative_rotation` → thematic momentum); UI honesty pass suite-wide | ≥1 leg passes or fails the gate PUBLICLY; zero unregistered scored reads | Opus |
| **W7** Institutional surface | macro/regime aggregate emit ("many entities in one sector lit today"); unified qualitative-intelligence page reading qbus+qledger; transcripts buy decision (paid FMP) reviewed against W1–W6 evidence; `QUAL_DATA_COMPLIANCE.md` | the one-page desk exists; buy decisions evidence-based | mixed |

### W0 briefs (verified by [P6]; dispatch-ready)

| # | Fix | Files | Size | Note |
|---|---|---|---|---|
| 1 | intel_hub policy-lean gate: consume the stored `conviction`, `low`→no `dirs["policy"]`, no `early_edge`, no `gap_mult` | `engine/intel_hub.py` | M | highest blast radius; consider soft/hard tier per [P6] risk 1 |
| 2 | altdata deterministic double-count: drop conviction add-back on deterministic path (`conviction` is derived FROM `weighted`) | `engine/altdata_emit.py` | S | [P6]: `cofiring_adjusted_score` never existed; re-check board thresholds after |
| 3 | altdata deterministic extended clamp: `extended = brain_flag OR rs > _EXTENDED_PP` + `brain_usable` (present AND not degraded) drives copy/actionable | `engine/altdata_emit.py`, `templates/alt_data.html.j2` | S | kills monotone-bullish fallback |
| 4 | congress: uncovered rows → `unconfirmed` bucket, composite = cluster-only, cannot outrank vetoed covered names | `scripts/build_congress.py` | S | |
| 5 | arb book: **cash-only** gate (overriding [P6]'s cash+stock allowance — the audit's worst offenders UROY/MCHX are cash+stock treated as fixed-price) + drop contradictory positive `downside_on_break_pct` | `engine/special_arb.py`, `engine/special_situations.py` | S | |
| 6 | china intel: drop past `scheduled_ahead` items (`days<0: continue`), per-surface staleness veto (news asof lag >3d) | `engine/china_intel_analysis.py` | S | |
| 7 | china policy watch: surface `intel.json` age via `policy_dates.annotate()` (orphan module wired in), stale callout in hero | `engine/china_policy_watch.py`, template | S | |
| 8 | china altdata: **verify lhb/block sign convention first** ([P6] risk 4 — the audit's −0.10 claim may be wrong if scores are pre-signed), then `n_signals` term in `conviction100` | `engine/china_altdata.py`, `china_signal_lab.py` | S | |
| 9 | radar clocks: `SEED_HORIZON_D=63` / `GRADE_HORIZONS=[21,63]` / `CHECK_BY_PAD` named + snapshot carries `horizon_d` | `engine/radar_ic.py`, `engine/radar.py` | M | W1 grader depends on it |
| 10 | PIT: EDGAR backtest entry → `date_filed + 1bd` | `scripts/backtest_special_situations.py` | S | [P2] leak #2 |
| 11 | PIT: China official cache `_clean_time()` at WRITE path (corrupted `time` fields observed live) | `engine/china_news.py` | S | [P2] |
| 12 | PIT: WH RSS naive-TZ fallback → America/New_York | `engine/whitehouse_feed.py` | S | [P2] |
| 13 | CN resolver quick win: `GENERIC_NOUNS` blocklist (机器人 first entry) in `tag_tickers` | `engine/china_news_intel.py` | S | measured 14%→~2% FP [P3] |

*(news_llm consumer-or-off folded into W5; the china_news dead render is DONE — macro#895.)*

---

## 5. Risks and kill criteria

- **Overlapping-observation illusion** [P1]: radar 5d "n≈1,328" is ~8 independent dates. All gate math runs on `n_dates`/block-bootstrap; any leg promoted on raw-n is a protocol violation.
- **The scoreboard becomes the new costume**: a ledger full of ACCRUING chips can itself launder credibility. Mitigation: chips display *time-to-first-grade*; any family ACCRUING >90d without a path to n≥25 gets auto-flagged for retire-or-redesign.
- **CCTV backfill fragility**: 3,800 sequential scrapes; item-level 404s observed on old dates [P4]. Budget retries + gap audit; accept degraded 2013–16.
- **gov.cn IP sensitivity**: collectors run from the VPS with browser UA (FREDGRAPH_UA precedent), leaf-dir targeting for NDRC [P4].
- **Fix-1 over-gating** [P6]: gating policy leans on `low` conviction may kill `early_edge` everywhere (all current leans are low). That is the honest state — the flag *should* be dark until a grade exists; do not soften to preserve a lit UI.
- **Phrase-book subjectivity**: polarity labels (跨周期, 共同富裕) are context-dependent; human review required before any signed use; unsigned novelty/appearance events are safe immediately.
- **Kill criteria**: novelty-v0 fails to beat the hand formula after 6 months of grading → keep the hand formula, publish the result. Communiqué Diff events show no forward differentiation after n_dates≥25 → China stays context/overlay permanently, stated on-page. The D7 one-shot re-aim fails → retire the lexical family. The experiment's value is the verdict, not the pass.

---

## Appendix: probe fact index

- **[P1] Backfill**: radar 2,489 obs/12 dates/426 tickers, 21d matures 2026-07-11, 5d smoke-test now; altdata 133 theses with PIT `entry_levels` (S); policy 13 open, soft falsifiers (M); China 866 events, 239 tagged, 172 with prices vs `510300.SS` (S); `ak.news_cctv` history to 2016-02.
- **[P2] PIT**: per-feed timestamp table; `timestamp_quality` enum + embargo rules; 3 live leaks (EDGAR same-day close, corrupted CN official cache `time`, WH TZ); `_crawled_at` addition; RSS back-dating sanity check.
- **[P3] Resolver**: `build_entity_map` 684 tickers/1 consumer; `name_resolver` 4,101 names (SEC file absent); CN map 2,367 pairs, FP 14% (94% from 机器人); layered v0 design, 3–5 days; F5 name==ticker already fixed upstream.
- **[P4] China corpora**: lianbo order preserved, 2016+ depth; People's Daily layout = prominence ordering (archive 1946–2026 claimed); PBOC 6,089-record archive; GDELT `sourcelang` separates onshore/offshore, 1req/5s; vendor URL rot ~0% → body-hash pivot; 44-formula phrase-book seed (needs human review).
- **[P5] LLM econ**: ~$10/mo Haiku all-tiers; `catalyst_tone` citation-guard reusable; `news_llm` output consumed by nothing + 87% tail dropped; 8-K lane 75% annotated already; `qual_extraction.v1` contract + drift protocol; `brain_usable` rule.
- **[P6] W0**: 10 briefs verified (1 already shipped); corrections — `cofiring_adjusted_score` aspirational, lhb sign needs verification, cash+stock is the garbage class.

*Companions: the four problem audits listed in the header. Execution status will be tracked in the memory topic `qualitative-intelligence-masterplan-for-fable`.*
