# China Intelligence × Cycles Masterplan — by Fable

Date: 2026-07-06
Status: ACTIVE program (W0 dispatching same day)
Digests: `research/CHINA_INTELLIGENCE_HUB_FREE_DATA_RESEARCH.md` (Codex, 2026-07-06)
Related: `research/CHINA_INTEL_POWERHOUSE.md`, `research/INTELLIGENCE_HUB_V2_RESEARCH.md`,
`research/CYCLE_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`, `data/china_official/phrase_book.yml`

---

## 0. Program charter

The Codex paper proposes a China Intelligence Hub built from free sources: policy
phrase diffs, filing ledgers, priced-in checks, and a validation ledger. Its product
philosophy is right and matches house discipline (provenance-heavy, context-only,
validation-aware, "rank by edge remaining"). Its **repo model is badly stale**: it
proposes building several organs that already exist, and it completely ignores the
repo's single deepest asset — **29 years of daily China regime history and 26 years
of Shenwan sector history** — which is exactly what turns "China headlines" into
*pattern studying in past history contexts*.

This masterplan reframes the program around that asset:

> **The product is not "what changed in official language." The product is "what
> changed, in which cycle/regime context, and what happened the last N times this
> configuration appeared."**

Everything display/context-only until gauntleted. LLMs never originate signals,
scores, or escalations. Phrase polarity stays PROVISIONAL/unsigned until graded
empirically by the event studies in W2.

---

## 1. Verdict on the Codex paper (keep / already-built / kill)

| Codex proposal | Verdict | Reality check (recon 2026-07-06) |
|---|---|---|
| §10 Phase 0: China lens in `intelligence_hub.html` from existing briefing | **KEEP — W0** | Real gap. Hub has zero China/region module; `site/china_intel/briefing.json` (v3) is richer than the paper assumes (conviction, chains, flagged tickers, what_changed, salience). |
| §10 Phase 1: official policy phrase ledger (1 week) | **ALREADY ~80% BUILT** | `collectors/china_official_corpora.py` (State Council/PBoC/NDRC/CSRC/People's Daily front page + layout_rank), `data/china_official/phrase_book.yml` (~44 canonical formulas + variants), `engine/communique_diff.py` (APPEARED/DROPPED/LEAD_SHIFT events, salience-only qledger claims, direction=0). **But the collector is red** (`DateParseError` — organ string parsed as date) and the corpus store holds only 3 days (2026-07-02→04). Fix + backfill, don't rebuild. |
| §10 Phase 2: filing metadata ledger (CNInfo/SSE/SZSE/HKEX) | **KEEP — the one genuinely new organ (W3)** | No announcement/inquiry-letter collector exists. Only `hk_placements` (dilution events) + per-ticker dividend lookups. But the paper's "high-value categories" are half-collected already as structured Eastmoney datasets: buybacks (`china_buyback`), pledges (`china_pledge`), block trades, LHB, analyst revisions, unlock queue. The new value is the **announcement stream itself** — especially 问询函 (inquiry letters) and 业绩预告 (preannouncements) — joined to what we already have, not duplicating it. |
| §10 Phase 3: market tape + priced-in axis (1–2 weeks) | **MOSTLY BUILT** | A-share OHLCV ×1,589 names, Shenwan 31 sectors to 1999, breadth to 1991, margin to 2010, Connect to 2014 (northbound *net* dead post-2024-08 — paper doesn't know), A/H premium 3 layers (25-pair panel to 2001), QVIX, ZT pool, THS 373 concepts. Real gaps: KWEB/MCHI/ASHR/CQQQ offshore ETFs not collected (trivial, W0), and priced-in labels not surfaced per-theme (W4). |
| §10 Phase 4: validation ledger / event-study pipeline (2–4 weeks) | **ALREADY BUILT — do not rebuild** | `scripts/hincl_event_study.py` + `scripts/backtest_event_priors.py` (index-relative CAR, episode aggregation, NW HAC-t, BH-FDR, DSR via `TrialLedger`), experiments registry (`data/experiments/registry_seed.json`), PREREG conventions, `engine/china_sector_cycles_grader.py` PIT rules. What's missing is not the pipeline — it's that **nobody has ever run a study on the policy events**. That's W2, the heart of this program. |
| §10 Phase 5: attention proxies (Baidu/Trends) + satellite/physical (NO2/FIRMS/VIIRS) | **KILL / park indefinitely** | Baidu Index is cookie-gated (known since POWERHOUSE audit); Google Trends unstable; satellite proxies are high-maintenance macro confirmers with no event timing. Low value density. Revisit only if a validated signal family demands confirmation. |
| §3 region selector (Global/US/China/HK/Cross-Border) in the hub | **KILL** | Overreach. One compact China lens module + a `regions/china.json` contract. HK/CA lenses only if the China lens earns its screen space. |
| §5.2 DBnomics/World Bank/IMF/BIS macro additions | **KILL** | Existing `china_macro`/`china_pboc`/`china_credit` stores cover the useful frequency. NBS direct is GeoIP-blocked (paper doesn't know); we already use Eastmoney mirrors. Annual IMF/WB context adds nothing tradeable. |
| §4 event schema (`china_intel.event.v1`) | **ADAPT** | Right instinct, wrong home. Map onto existing conventions: keep-FIRST parquet ledgers + qbus/qledger claims, not a parallel JSONL universe. `body_hash`/`first_seen`/`layout_rank` already exist in the corpus collector. |
| §11 compliance boundaries | **KEEP verbatim** | Sound, matches house law. Metadata/hashes/links only; no paywall/captcha/robots bypass; no personal data; aggregate only. |

**What the paper misses entirely (our additions):**

1. **Cycle/regime conditioning** — `data/china_regime/regime_history.parquet`
   (1997-07→, 7,568 days: quad, liquidity overlay, cycle tag, confidence),
   `data/china_sector_cycles/backfill.parquet` (2010→, 31 Shenwan + 22 baskets,
   5-phase wheel), `data/hk_regime/regime_history.parquet` (1986→). Every event
   study and every hub card gets a cycle-context axis for free.
2. **Rate-action events are studiable TODAY** — RRR changes 2007→ (55 events with
   magnitudes), LPR 2017→, PMI 2008→ already on disk. No collection needed to run
   the first pre-registered study.
3. **Historical analog finder** — with 29y of regime vectors, "the last N times
   this configuration appeared" is a k-NN lookup, not a research project.
4. **Backfill feasibility (probed live 2026-07-06)** — akshare `news_cctv(date)`
   returns full 新闻联播 transcripts back to ~2015 (16 items/day recent, ~45s/day
   serial). And the canonical communiqué families (PBoC MPC quarterly readouts,
   Politburo econ meetings, CEWC) are ~30 dated docs/year — a *curated* backfill
   is ~450 documents, not a crawl.

---

## 2. Rulings

- **RUL-1 (no new pipeline):** China policy/filing events plug into the existing
  event-study harness (index-relative log CAR, episode aggregation, `newey_west_tstat`,
  `benjamini_hochberg`, `deflated_sharpe` with `TrialLedger` budget). Benchmark:
  CSI 300 (510300.SS) for A-share studies; SHCOMP for pre-2012 depth checks.
- **RUL-2 (conditioning is descriptive):** cycle/regime conditioning cuts (quad,
  liquidity overlay, sector cycle phase) are printed as context tables, **not FDR
  slots**. Verdicts only at the pre-declared primary horizon on the unconditional
  event family. A conditioning cell may graduate to its own pre-registered family
  only in a later amendment, with its own trial budget.
- **RUL-3 (backfill priority):** curated communiqués first (MPC quarterly readouts,
  Politburo econ-meeting readouts, CEWC — ~450 docs, paced, off render path), CCTV
  daily backfill second (2016→, resumable background lane on the Mac, store
  gitignored/R2 — never on the render path). gov.cn full-archive crawling: only if
  the curated set proves insufficient.
- **RUL-4 (filings = metadata only):** title/category/ticker/URL/publish-time only
  in v1; no PDF bodies, no republication. Category normalizer targets 问询函
  (inquiry letters), 业绩预告 (preannouncements), 回购, 质押, 减持/增持, 重大合同/中标,
  立案调查, 重组, 退市风险. Joins to existing structured stores (buyback/pledge/LHB)
  instead of duplicating them.
- **RUL-5 (phrase polarity stays unsigned):** `phrase_book.yml` polarities remain
  PROVISIONAL and communique_diff events remain direction=0 salience until the W2
  event study grades them. Even then, signing requires the standard gauntlet.
- **RUL-6 (kills):** attention proxies, satellite/physical proxies, hub region
  selector, DBnomics/WB/IMF/BIS macro additions — killed per §1 table.
- **RUL-7 (analog finder is context):** k-NN over regime vectors emits descriptive
  forward-path fans ("what followed the k nearest historical configurations"),
  clearly labeled n, no scores, no LLM text in the loop. Display-only.
- **RUL-8 (hub contract):** the China lens reads `site/china_intel/briefing.json`
  and emits `site/intel_hub/regions/china.json` (schema
  `intelligence_hub.region.v1`, adapted from the Codex paper §4). The lens shows
  the command packet only (what changed / cycle context / confirmations /
  freshness / validation state) and routes to `china_intel.html` for detail.
- **RUL-9 (render budget):** all backfills and event studies run off the render
  path (manual/Mac-local). Nightly additions: the filings collector rides the
  `asia` lane (auto-routed by `china_` prefix) with pacing + per-source isolation;
  new page modules are O(seconds) JSON merges.
- **RUL-10 (routing):** Sonnet builds (agentType `builder`), Opus reviews/red-teams
  stats (agentType `reviewer`), Fable (main loop) plans/adjudicates/merges. Effort
  low on mechanical stages.

---

## 3. Waves

### W0 — Repair + wire (same day, 3 PRs)

- **W0.1 Fix `china_official_corpora`** — collector red since 2026-07-05 with
  `DateParseError: unable to parse: state_council` (organ string hitting a
  datetime parse — likely a column-order/schema drift in the status/last_date
  path). Repro, fix, regression test with a fixture frame. The phrase pipeline's
  feedstock is dark until this lands.
- **W0.2 China lens in `intelligence_hub.html`** — compact module reading
  `briefing.json`: headline (what changed), regime/cycle chips (quad, liquidity,
  RORO band), top-2 conviction rows with stage + edge bar, flagged-ticker count,
  per-surface freshness dots, "Context only" badge, link to `china_intel.html`.
  Emit `site/intel_hub/regions/china.json`. Bilingual (t() macro, data-tip-en/zh,
  never title=), mobile-capped rows, degrade-safe (module hides if briefing
  absent). Acceptance: hub renders with and without briefing.json; no new scores.
- **W0.3 Offshore China ETF tape** — add KWEB, MCHI, ASHR, CQQQ (+ GXC if free)
  to the yahoo collection universe so the onshore/offshore divergence axis has
  instruments. Data-only PR; no engine consumer yet.

### W1 — History depth (the enabling wave)

- **W1.1 Curated communiqué backfill** — scout then build: PBoC MPC quarterly
  readouts (货币政策委员会例会, archives on pbc.gov.cn, target 2009→), Politburo
  econ-meeting readouts (April/July/Oct/Dec, via gov.cn/Xinhua mirrors, target
  2010→), CEWC (annual). ~450 dated documents → `data/china_official/communiques.parquet`
  (doc_id, family, meeting_date, publish_date, title, body, body_sha256, url,
  source). Paced (≥1s + jitter), browser UA, per-source isolation, resumable.
- **W1.2 CCTV daily backfill** — **AMENDED 2026-07-06**: the repo already had
  `scripts/backfill_cctv_archive.py` (PR #923, Qualitative-Intelligence W4
  prereq) implementing exactly this spec (resumable newest-first 2016-02-03→,
  stub detection, `--repair`, `--gap-audit`), with `data/china_news/cctv_archive/`
  already holding 2021-05→2026-07. A duplicate lane (PR #1630) was built and
  CLOSED unmerged; instead the existing script was relaunched on the Mac to fill
  the 2016→2021 gap (~1,900 days, ~30h). Store stays gitignored Mac-local.
  Lesson recorded: check `data/china_news/` sublanes before commissioning
  CCTV-adjacent collectors.
- **W1.3 Rate-action event table** — derived in-runner from on-disk parquets (no
  new nightly artifact until a study says ACCRUE): RRR change dates + magnitudes
  2007→ (n=55), LPR cut/hold dates 2017→, plus MPC meeting dates once W1.1 lands.

### W2 — Pattern studies in past history contexts (the heart)

- **W2.1 PREREG** (`research/CHINA_POLICY_EVENTS_PREREG.md`, committed before any
  runner executes): families = (a) RRR eases, (b) LPR cuts, (c) MPC communiqué
  phrase-diff events (once W1.1 lands), (d) CCTV phrase APPEARED events (once W1.2
  lands). Outcome = index-relative log CAR on CSI 300 and 2–3 pre-named
  rate-sensitive Shenwan sectors (banks 801780, real estate 801180, brokers
  801790). Horizons 5/10/20/40/60d, **verdict only at H=20**, HAC-t + BH-FDR +
  DSR ≥ 0.90, episode-K ≥ 8, split-half sign stability. Conditioning cuts (quad,
  liquidity, cycle phase at event date via `regime_history.parquet`) are
  DESCRIPTIVE per RUL-2. Trial budget declared via `TrialLedger` before running.
- **W2.2 Runner** — adapts `car_for_event()` from the hincl harness; A-share
  panel = `data/china_stocks_raw/` + Shenwan sector indices; PIT rule: forward
  window anchors at first close strictly after event date (grader convention).
  Output: `data/experiments/china_policy_events_results.json` + plain-language
  report (`reports/china-policy-events-phase0.md`) with "In plain English" boxes.
- **W2.3 Analog finder phase-0** — k-NN over standardized regime vectors
  (growth_score, inflation_score, liquidity, quad one-hot, cycle tag, RORO) with
  a time-exclusion window; emit descriptive forward-path fans for SHCOMP/CSI300 at
  20/60/120d for today's configuration + top-k analog dates. Display-only JSON
  (`site/china_intel/analogs.json`) + methodology note. Reviewer red-teams for
  lookahead and for degenerate neighbor clustering (adjacent-day analogs).
- **W2.4 Register** every family in `data/experiments/registry_seed.json` with
  `status: accruing`, precise maturation criteria, and come-back dates.

### W3 — Filing metadata ledger (the new organ)

- **W3.1 Scout** — probe CNInfo public POST endpoint (reliable tier per
  POWERHOUSE), akshare disclosure wrappers (`stock_zh_a_disclosure_report_cninfo`
  et al.), SZSE inquiry-letter pages, HKEXnews headline categories. Report:
  reachability, rate limits, category taxonomy, historical depth per source.
- **W3.2 Collector** — `collectors/china_filings.py` (auto-routes to `asia` lane):
  metadata-only rows, keep-FIRST parquet `data/china_filings/filings.parquet`
  (+ R2 if it grows heavy), category normalizer, `expected_failure` marks for
  fragile sources, audit-gate registration.
- **W3.3 Theme/entity link + bus card** — resolve tickers via
  `data/china_search/members.parquet` + THS concepts; map categories → policy
  themes (phrase_book domains); emit filing-confirmation counts into the china
  bus (`briefing.json` new `filings` surface, context-only) and a "Filing
  confirmations" card on `china_intel.html`.
- **W3.4 Forward registration** — filing-category event families (inquiry
  letters, preannouncement direction) registered as accruing experiments with
  come-back dates; studied through the W2 harness once n matures.

### Amendment 1 (2026-07-06) — cross-session division of labor

A concurrent session ("China Intelligence Hub redesign", masterplan
`research/CHINA_INTEL_HUB_MASTERPLAN.md`) built from the same Codex paper the
same day: #1609 (hub v2, briefing v4), #1627 (special-situations desk +
`collectors/china_inquiry.py`, briefing v5), #1663 (W5 polish incl.
cycle-context chips — the chips contract from this program, already wired).
Agreed division, both sides confirmed:

- **They owned** `templates/china_intel.html.j2`, `engine/china_intel_bus.py`,
  the briefing schema (additive-only guarantee, their R-4), all China subpage
  UX, and the `cn_special_sits` qledger salience family.
- **This program owns** history backfills (W1), pre-registered event studies
  (W2), the filings **spine** (W3 — their narrow `china_inquiry.py` migrates to
  it; contract: `kind` ∈ letter/reply/attachment on the inquiry family;
  reply/attachment take precedence over letter keyword match), the analog-finder
  JSON, and the global-hub China lens (#1616; their thin routing card dropped).
- Contracts delivered to them: `analogs.json` schema + card spec,
  `filings.parquet` schema, cycle-chips regime_history join, `communiques.parquet`
  schema (read-only deepening of their policy_phrase card history).
- That session is now COMPLETE. Consequences inherited here: the
  `china_inquiry.py` → `china_filings` migration of
  `engine/china_special_situations.py` and the analogs/filings card wiring on
  `china_intel.html` fall to this program's W4 (additive edits on their v5
  template, respecting the schema additive-only rule).

### W4 — Surfaces + validation wiring

- **W4.1 `china_intel.html` upgrades** — "Policy phrase shifts" card upgraded to
  show cycle context per event (quad/liquidity/phase chips at event date),
  "Cycle context & analogs" card (W2.3 output), "Filing confirmations" card
  (W3.3), validation-status chips per signal family read from the experiments
  registry (ACCRUING/n/come-back date — the honest state, never "validated"
  without the BC-2 allowlist).
- **W4.2 Hub lens polish** — priced-in labels per theme (sector RS 5/20d, A/H gap,
  southbound turnover percentile) on the China lens rows; freshness strip reads
  per-surface `surface_asof`.

### W5 — Program close

Memory updates, registry reconciliation, come-back clock entries, ObsidianBrain
sources refreshed, deprecation note added to the Codex paper pointing here.

---

## 4. Compliance & source boundaries

Codex paper §11 adopted verbatim as program law. Additions: CCTV/communiqué
backfills store text for internal diffing only — published UI shows metadata,
phrase hits, hashes, and links; PBoC/gov.cn crawls are paced ≥1s+jitter with
browser UA and per-source isolation; anything CN-IP-gated is marked
`expected_failure`, never load-bearing.

## 5. Budget

Nightly delta: filings collector (paced, ~1–2 min in asia lane) + two O(seconds)
JSON builders. Zero render-path compute added; all studies and backfills are
Mac-local manual lanes. Heavy text stores gitignored/R2 per `r2-data-plane`.
