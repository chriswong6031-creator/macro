# Special Situations — Roadmap / Next-Session Handoff

*Written 2026-06-21 after Phase-1 shipped to main. Read this cold to continue. Companion to `SPECIAL_SITUATIONS_RECON_FINDINGS.md` (what the digest does) and `SPECIAL_SITUATIONS_BUILD_SPEC.md` (the original plan).*

## Where it stands (shipped, on `main`)
- **Collector** `collectors/special_situations.py` — EDGAR daily-index discovery + EFTS join (8-K items + geography); SC 13D via the authoritative `.idx` (EFTS blind spot); `backfill_range`; text lane (`enrich_text`, keyword) + DeepSeek summary lane (`enrich_summaries`, **now ON**); `reclassify_cached`.
- **Engine** `engine/special_situations.py` (`SCORED=False` leaf) — deterministic form→mature-category classifier, $100M floor, cross-border tag, going-private/SPAC reclass, **confidence tiering** (structured=high, keyword text-lane=low), `desk_payload` (digest+EDGAR merge), `mastermind_emit`.
- **Surfaces** — `site/special_situations.html` (bilingual, nav, daily build step), `site/allocationdata/special_situations.json` + `master_brain.gather_state()`.
- **Data** — `digest_db.parquet` (4,471 curated), `events.parquet` (~29k owned EDGAR filings Feb–Jun 2026), `backtest_priors.json`, `benchmark_scorecard.json`.
- **State of the metrics** — self-sufficiency confirmation **~41–46%** of the latest digest issue's US picks (lower bound); high-confidence precision ~56% vs digest; backtest over 1,789 US situations shows deal-certainty categories carry forward drift (Capital Returns 74% / Tender 71% / Going-Private 65% win @20d), distress bleeds.
- **Honest gaps** — keyword text-lane has boilerplate/buyer-seller false positives (flagged low-confidence); text-lane only ran on the recent ~2,500 of ~26k deferred; SPACs/Rights weak; international (the digest's moat) not built; no deal-terms/lifecycle.

---

## TIER 1 — highest leverage (do first): turn detection into a *trustworthy, tradeable* signal

### 1.1 — Let the LLM CONFIRM/correct the category (not just summarize)  ⭐ single biggest win
**Why:** the keyword text-lane is the precision bottleneck (audit found 67% FP on unvalidated extras — 424B5/boilerplate/buyer-vs-seller). DeepSeek *already reads each filing* for the summary; have it also return the **verified category + registrant role (acquirer/target/seller) + confidence**. This converts the noisy low-confidence lane into HIGH-confidence verified classifications, fixing the FPs AND raising the confirmation rate — for ~no extra cost (same call, bigger structured output).
**How:** extend `enrich_summaries` (or split a `enrich_classify`) to return JSON `{category, role, confidence, summary}` (DeepSeek supports JSON output). Store `llm_category`/`llm_role`. In `build_situations`, prefer `llm_category` over the keyword `text_category` for promotion and set `confidence="high"` when the LLM agrees with itself across role+category. Keep the keyword lane as the cheap pre-filter (decides *whether* to spend an LLM call).
**Effort:** ~1 session. **Cost:** marginal over the summary lane already running.
**Validate:** re-run `benchmark_vs_digest.py` + the adversarial audit workflow on the new extras → expect FP rate to drop from ~67% toward <20%.

### 1.2 — Merger-arb spread monitor (tradeable, uses data we already have)
**Why:** for announced cash/cash+stock Acquisitions, Tender Offers, Going-Privates, the **spread** (deal price vs live price), annualized return, and days-to-close is a directly tradeable, classic event-driven signal — and the digest doesn't compute it.
**How:** parse deal terms (`price_per_share`, consideration cash/stock, expected close date) from the filing text — reuse the LLM call from 1.1 to emit these fields. Join to the live price (`site/live.js` / breadth closes / `bt_prices`). New desk section or columns: spread %, ann. return, days-to-close, downside-on-break. Surface to Mastermind as a risk-arb context block.
**Effort:** ~1–2 sessions. **Depends on:** 1.1 (term parsing rides the same LLM call).

---

## TIER 2 — coverage & depth

### 2.1 — Full text-lane / LLM classification over the entire backfill
Run `enrich_text` + the 1.1 LLM lane over ALL ~26k deferred filings (currently only the recent ~2,500). Lifts confirmation across the whole period and completes the owned dataset. Heavy but mechanical — a long background job (SEC rate limit caps it to single-stream ~8 req/s; budget hours, cache makes it one-time).

### 2.2 — Lifecycle / stage tracking (our edge over the weekly digest)
Link filings for the SAME deal (key on `cik` + counterparty) into a timeline: `announced → amended (13D/A escalations) → vote-scheduled (DEFM14A) → closed (8-K 2.01) / terminated (8-K 1.02)`. Gives a true deal-lifecycle view, powers the arb-spread lifecycle, and enables "deal broke / deal closed" events. The digest has no stage field — this is a genuine improvement. Add a `stage_history` and current-stage to each situation.

### 2.3 — SPACs & Rights proper detection
SPAC: parse S-4/de-SPAC business-combination structure (the 1.1 LLM lane handles this cleanly — name-heuristic is brittle). Rights: distinguish a true rights offering (subscription rights / oversubscription) from an ordinary 424B5 shelf takedown (the 1.1 LLM lane handles this too). Both fold into 1.1.

---

## TIER 3 — integration & surfaces

### 3.1 — Mastermind: context emit → decision-matrix lens + alerting
Today we emit `special_situations.json` (by_ticker context) + a slim `master_brain` block. Next: a proper **context lens** in the bot's decision matrix (event catalyst that informs, never sizes — per the bot's doctrine), and **watchlist/portfolio-aware alerting** when a high-confidence situation lands on a held/watched ticker.

### 3.2 — Per-ticker chip in `stock.html` + landing-hub mini-card
Deferred surface work (touches the parallel-edited `build_stock_library.py` and `build_vector.py` — coordinate). Add a `special_situation` key to `site/stockdata/<T>.json` so the single-stock page shows an inline chip; add `_special_situations_state()` to the landing hub (the hub JSON is already emitted).

### 3.3 — Alert Center integration
Route new high-confidence situations into the existing Alert Center (ranked/triaged), filtered to the user's universe.

---

## TIER 4 — the moat: international coverage (Phases 2 & 3)
Recon showed **US is only 45%** of the digest; this is where the digest's value concentrates.
- **Phase 2 — UK RNS + Canada SEDAR+** (English, structured; ~556 situations). The classifier + LLM lane already exist; mainly new collectors (Rule 2.7 / scheme circulars; Early-Warning Reports / Plan-of-Arrangement). Moderate effort, high coverage gain.
- **Phase 3 — Japan EDINET/TDnet** (562 situations — the single biggest non-US bloc). Needs Japanese-language ingest + the 大量保有 13G→13D purpose-flip detector. High value, highest build cost.

---

## TIER 5 — backtest → deployable strategy
- **Backtest depth:** forward returns by category × **stage** × market-cap × holding period (e.g. "buy a Going-Private at announcement vs after the vote"). Activist-filer **track-record** weighting (which 13D filers actually create alpha). Build deployable rules from the priors.
- **Broader/longer price history** for statistical robustness (current backtest's forward windows are capped by the present; entry uses the digest date — switch to **filing-date entry** from our owned `events.parquet` for clean point-in-time, which also removes the digest's weekly lag bias).

---

## Ongoing / hygiene
- Let `benchmark_scorecard.json` accrue per build → track self-sufficiency climbing over time.
- Data quality: dedup edge cases (warrant/unit/preferred ticker variants), foreign-ticker resolution, the $4.5T cap parse outlier sanity-bound.
- Keep their digest as the **answer key** (re-grade ourselves), never the live source — the goal remains self-sufficiency.

---

## Suggested next-session order (if picking one thing)
**Do 1.1 first.** It's the highest leverage (fixes precision, raises confirmation, ~free since the LLM already runs), unblocks 1.2 (deal terms) and 2.3 (SPAC/Rights), and is the difference between "a noisy detection list" and "a signal the Mastermind can trust." Then 1.2 (merger-arb) for immediate tradeable value, then 2.2 (lifecycle) for the structural edge.
