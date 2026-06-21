# Special Situations — Roadmap V2 (data-source expansion + feed placement + phasing)

*Written 2026-06-21. **Consolidates and supersedes** `SPECIAL_SITUATIONS_ROADMAP.md` (V1, the Phase-1 handoff, currently on `origin/main`) — keeps V1's Tier 1–5 action list intact but (a) re-frames it into shippable phases, (b) adds a **new-data-source catalog** with a per-source **feed-placement decision** (Special-Situations desk vs Alternative-Data feed), and (c) folds in a competitor/source scan that replaces the missing "ChatGPT similar-sites note."*

*Companions: `SPECIAL_SITUATIONS_RECON_FINDINGS.md` (what the digest does, §A–§F), `SPECIAL_SITUATIONS_BUILD_SPEC.md` (the original locked plan). Live code on `origin/main`: `engine/special_situations.py`, `collectors/special_situations.py`, `scripts/build_special_situations.py`.*

> ⚠️ **Worktree note:** the canonical roadmap + all special-situations code live on `origin/main` (the remote `macro` repo), which is far ahead of this local checkout. When shipping, cherry-pick onto a fresh branch off `origin/main` and have this file **replace** the V1 `SPECIAL_SITUATIONS_ROADMAP.md`.

---

## 0. Where we stand (one paragraph)

We have two backfilled assets — the curated **digest DB** (`digest_db.parquet`, 4,471 situations, our *answer key*) and our own **EDGAR event store** (`events.parquet`, ~29k filings Feb–Jun 2026). The live desk (`engine/special_situations.py`, `SCORED=False`) does deterministic form→category classification, $100M floor, cross-border tagging, confidence tiering, and a now-on DeepSeek 88-word summary lane. Self-sufficiency vs the latest digest issue is **~41–46%**; high-confidence precision **~56%**. The honest gaps are: (1) the keyword text-lane is noisy (~67% FP on unvalidated extras), (2) text-lane only ran on the recent ~2,500 of ~26k deferred filings, (3) no deal-terms / lifecycle / merger-arb math, (4) **international (55% of the digest) is unbuilt** — that's the moat.

---

## ✅ Status — shipped this session (branch `feat/special-sits-v2`)

All of Phases 1, 2, 3, and 5.1 below were **built, offline-tested, and merged** in one autonomous pass (full suite **2737 pass**). Display-only throughout (`SCORED=False`); the LLM/newswire lanes stay gated until a key/flag is set in CI, so production is unaffected until switched on.

| Phase | What shipped | Verified |
|---|---|---|
| **1.1** ⭐ | LLM-verify `{category, role, confidence, deal_terms}` (one JSON call); kills keyword FPs (`None` verdict), promotes verified categories | 6 tests (mocked LLM); build renders |
| **1.2** | `engine/special_arb.py` — spread / annualized / days-to-close / downside-on-break; `arb` desk chip + `risk_arb` Mastermind book | 10 tests; pure math |
| **2.1** | `collectors/special_news.py` newswire lane for the form-absent categories (gated **off** by default) | 6 tests; gated no-op proven |
| **3.1** | `lifecycle()` — per-deal timeline, current stage, amendments, terminal broke/closed | 3 tests; real data: 1037 amended, 273 terminal |
| **3.2** | `engine/activist.py` — reporting-person extraction + per-filer track-record (sample-gated) | 5 tests |
| **3.3** | Feed handshake — `activist_13d`/`special_situation` Alt-Data channels fed by the desk emit | 2 tests |
| **5.1** | Backtest by category×**stage**, **filing-date** entry (point-in-time) | 2 tests; real data: 238 situations, stage differentiates |

**Follow-up rounds (also merged):** per-build caps so the backlog can't stall the daily deploy (#395); P5.1 priors surfaced as desk/brain **context** (#397); **Phase 4 UK/Canada** intl classifier (§D3, pure) + gated UK/CA RSS collectors + cross-border desk merge; market-cap floor **confidence gate** ($25M for high-confidence only); **newswire lane flipped ON**; a Tier-2.2 **backlog-backfill workflow** (manual + weekly) that also refreshes priors.

**Still deferred (honest):** **Phase 4 Japan / HK / Korea** (CJK-language ingest — the classifier core is ready, the collectors are not). **SEDAR+ direct ingest** stays RSS-only (direct scraping is ToS/CAPTCHA-barred). The UK/CA intl lanes ship **gated off** (`intl_uk` / `intl_canada`) until a CI smoke-check confirms real-world feed quality.

---

## 1. The feed-boundary decision framework (answers "this feed vs Alt-Data feed?")

We run **two complementary display-only desks**, and the choice of where a new source goes is structural, not arbitrary:

| | **Special-Situations desk** (`engine/special_situations.py`) | **Alternative-Data feed** (`engine/altdata.py` + `altdata_models.py`) |
|---|---|---|
| **Unit** | A *discrete corporate event*, one record per deal/filing | A *continuous, quantified signal* on a ticker |
| **Shape** | Categorical (16 mature categories), staged, archival | Weighted convergence — 31 channels, `weighted_score = Σ CHANNEL_WEIGHTS` |
| **Cadence** | Low-frequency, high-conviction (most names: 0–1/yr) | Daily streams, hundreds of names lit |
| **Output** | `site/special_situations.html`, `data/regime/special_situations_latest.json` (hub card), `site/allocationdata/special_situations.json` (Mastermind context) | `site/altdata/feed.json`, `data/altdata/by_ticker.json`, `site/altdata/mastermind.json` |
| **Add a source by** | new collector → form/text→category routing in the engine | new collector → `CHANNEL_WEIGHTS[...]` + detection in `channel_records()` |

**The decision rule:**
- **→ Special-Situations** if the datum *defines or advances a specific corporate event* (a deal's terms, stage, spread, break, the activist's identity, the spin-off ratio). It's *archival and categorical*.
- **→ Alt-Data** if the datum is a *recurring, ticker-keyed signal that gains meaning by converging with others* (insider clusters, options surge, contract acceleration). It's *weighted and cross-sectional*.
- **→ Both (a "handshake")** when an event in one desk should *light a channel* in the other. This is the highest-value pattern and we don't do it yet: e.g. a confirmed 13D should also raise an `activist_13d` Alt-Data channel; an Alt-Data insider-cluster on a name already in a Strategic Review is a confirming leg. **Wiring the handshake (a thin cross-emit) is its own Phase-3 item.**

**Crucial overlap note:** InsideArbitrage's canonical "six event-driven strategies" are merger-arb, spin-offs, **management changes, SPACs, buybacks, insider transactions**. The last three already exist (or half-exist) as Alt-Data channels (`material_8k`, insider channels, `13f_add`, `unusual_options`) and as digest categories (Capital Returns, Management Changes). **Do not rebuild those in the special-sits engine — reference them via the handshake.** Special-sits owns the *deal-shaped* half (M&A, going-private, tender, spin-off, SPAC lifecycle, restructuring, deal-break); Alt-Data owns the *flow-shaped* half (who's buying, what's accelerating).

---

## 2. New-data-source catalog (the "what else should we add" answer)

Sourced from the recon (§D source mix, §D3 international, §D4 form-absent categories) + a competitor scan (InsideArbitrage's 6-strategy model, 13D Monitor, Boardroom Alpha/SPAC Research, LevelFields, the distressed/Petition world). Ordered by leverage. **All free-first / keyless-or-existing-key**, per the standing "no paid vendors" rule.

| # | Source / signal | What it adds | Closes which gap | **Feed** | Cost / key | Effort |
|---|---|---|---|---|---|---|
| **S1** | **LLM-verified category + role + deal-terms** (extend the DeepSeek call we already run) | Turns the noisy keyword lane into high-confidence verified categories; emits `price_per_share`, consideration, expected-close, break-fee | FP rate ~67%→<20%; unblocks arb + SPAC/Rights | **Special-Sits** | marginal (call already runs) | ~1 sess |
| **S2** | **Merger-arb spread math** (deal price from S1 × live price we already hold) | Spread %, annualized return, days-to-close, downside-on-break — the single most *tradeable* output, and the digest doesn't compute it | We have zero quantitative deal output today | **Special-Sits** (with an Alt-Data `risk_arb` context chip) | $0 (reuses `live.js`/breadth closes) | ~1–2 sess |
| **S3** | **Newswire RSS lane** (GlobeNewswire / BusinessWire / PRNewswire / ACCESSWIRE category + Google-News RSS, reuse `engine/news_rss.py`) | Catches the **form-absent categories** — Strategic Reviews (the #2 stable category, 399), out-of-court Restructuring, Capital Returns, Deal Terminations — *faster than EDGAR* | EDGAR-only misses ~35–40% of US categories (§D4) | **Special-Sits** (primary) | keyless | ~1–2 sess |
| **S4** | **Activist filer track-record** (mine our own `events.parquet` 13D/13D-A history → per-filer forward-return alpha) | Distinguishes a Pershing/Elliott 13D from a no-name filer; weights the situation. 13D-Monitor's whole business. | All 13Ds look identical today | **Both** — scores the situation (Special-Sits) *and* defines a new `activist_13d` Alt-Data channel | $0 (own data) | ~1–2 sess |
| **S5** | **Deal lifecycle / stage tracking** (link filings for one deal on `cik`+counterparty: announced→amended→vote→closed/terminated) | A true deal timeline + "deal broke / deal closed" events; powers arb-spread lifecycle. The digest has *no* stage field — genuine edge. | We emit isolated filings, not deals | **Special-Sits** | $0 | ~2 sess |
| **S6** | **SPAC lifecycle data** (S-4/424B/8-K trust + Form 25; redemption %, trust/share, extension votes, deadline) | Proper SPAC detection + the redemption/deadline math (Boardroom Alpha / SPAC Research model) | SPACs/Rights are weak today | **Special-Sits** (S1 LLM lane handles the S-4 parse) | $0 | ~1–2 sess |
| **S7** | **International regulator lanes** — Canada SEDAR+ & UK RNS first (English, structured), then Japan EDINET/TDnet | The non-US **55%** of the catalog = the digest's moat. CA/UK are English + structured (Early-Warning Reports, Rule 2.7, scheme circulars). | We are structurally a US-only product | **Special-Sits** | keyless scraping (ToS-aware) | CA/UK ~2–3 sess; JP high |
| **S8** | **Bankruptcy / distressed docket** (free PACER-adjacent: CourtListener/RECAP API, courtlistener.com) | First-day motions, Ch.11 petitions, plan-confirmation dates — the distressed lane (Petition/Reorg world). EDGAR 8-K 1.03 only catches the *announcement*, not the docket. | Restructuring/Insolvency are thin on docket detail | **Special-Sits** | CourtListener API (free key) | ~2 sess |
| **S9** | **Buybacks / special dividends** (8-K 8.01 + newswire) | Capital Returns coverage | partial today | **Alt-Data** (this is a flow signal; add/raise a `capital_return` channel — *don't* duplicate in special-sits) | keyless | ~1 sess |
| **S10** | **Insider-cluster + options-flow confirmation** (already in Alt-Data) | Confirms a special-sit is *being traded* before the catalyst | no cross-confirmation today | **Alt-Data → handshake into Special-Sits** | already collected | rides S4 handshake |

**Placement summary:** the *deal-shaped* sources (S1, S2, S3, S5, S6, S7, S8) live in the **Special-Situations desk**; the *flow-shaped* ones (S9, S10) live in **Alt-Data**; and **S4** plus the confirmation legs are explicit **handshakes** between the two. This keeps each engine's contract clean (categorical-archival vs weighted-convergence) while letting them confirm each other.

---

## 3. The phased plan (consolidates V1 Tiers 1–5 + the new sources)

Each phase is independently shippable and **display-only stays display-only** until a validation gate says otherwise (the house rule: events are *context/catalyst*, never sizing alone).

### Phase 1 — Make detection *trustworthy and tradeable* (do this first; unchanged from V1's steer)
> *V1 Tier 1. "If the next session does one thing, do 1.1." Highest leverage, ~free, the difference between a noisy list and a signal the Mastermind can size against.*

- **1.1 — LLM CONFIRM/correct the category (= source S1).** ⭐ Extend `enrich_summaries` (or split `enrich_classify`) to return JSON `{category, role, confidence, summary, deal_terms}`. Prefer `llm_category` over the keyword `text_category` in `build_situations`; set `confidence="high"` when role+category self-agree. Keep the keyword lane as the cheap *pre-filter* deciding whether to spend the call. **Validate:** re-run `benchmark_vs_digest.py` + the adversarial audit → expect FP ~67%→<20%, confirmation rate up.
- **1.2 — Merger-arb spread monitor (= source S2).** Ride S1's deal-terms output. Join to live price → spread %, annualized return, days-to-close, downside-on-break. New desk section/columns + a `risk_arb` context block to Mastermind. *Immediate tradeable value.*
- **Why this order:** 1.1 fixes precision *and* unblocks 1.2 (terms), 2.x (lifecycle), and SPAC/Rights — one LLM change pays for four downstream features.

### Phase 2 — Coverage: the form-absent categories + the full backfill
> *V1 Tier 2.1/2.3 + new source S3.*

- **2.1 — Newswire RSS lane (= source S3).** Wire `engine/news_rss.py`-style ingest (GlobeNewswire/BusinessWire/PRNewswire/ACCESSWIRE + Google-News RSS) as a parallel lane, keyword-routed to the form-absent categories, then merged/deduped with EDGAR on a company-date key. Without this we miss Strategic Reviews (the #2 category) entirely.
- **2.2 — Full LLM/text classification over the whole backfill (V1 2.1).** Run the S1 lane over all ~26k deferred filings (currently ~2,500). Long background job, SEC-rate-capped (~8 req/s single stream); cache makes it one-time. Lifts confirmation across the whole period.
- **2.3 — SPAC & Rights proper detection (= source S6, V1 2.3).** Folds into S1 — S-4/de-SPAC structure parse + true-rights-vs-shelf 424B5 disambiguation, plus SPAC redemption/trust/deadline math.

### Phase 3 — The structural edge (what the *weekly* digest can't do)
> *V1 Tier 2.2 + new sources S4, S5, S8 + the feed handshake.*

- **3.1 — Deal lifecycle / stage tracking (= source S5, V1 2.2).** Link filings into per-deal timelines keyed on `cik`+counterparty; add `stage_history` + current stage; emit "deal broke / deal closed" events. Powers the arb-spread lifecycle and is a true improvement over the digest's stageless cards.
- **3.2 — Activist filer track-record (= source S4).** Mine our `events.parquet` 13D/13D-A history → per-filer forward-return priors; weight the situation by filer quality. **Handshake:** define an `activist_13d` channel in `altdata_models.CHANNEL_WEIGHTS` so a verified 13D also lights the Alt-Data convergence.
- **3.3 — Feed handshake / Mastermind lens.** Two thin cross-emits: (a) high-confidence special-sit → Alt-Data channel on the same ticker; (b) Alt-Data convergence (insider cluster / options surge) → a confirming chip on a live special-sit. Then a proper **context lens** in the bot's decision matrix (catalyst that *informs*, never sizes) + watchlist/portfolio-aware alerting when a high-confidence situation lands on a held/watched name. *(V1 Tier 3.1.)*
- **3.4 — Distressed docket lane (= source S8, optional).** CourtListener/RECAP for Ch.11 dockets to deepen Restructuring/Insolvency beyond the 8-K announcement.

### Phase 4 — The moat: international coverage
> *V1 Tier 4 + source S7.*

- **4.1 — Canada SEDAR+ + UK RNS** (English, structured; Early-Warning Reports / Rule 2.7 / scheme circulars). The classifier + S1 LLM lane already exist — this is mostly new collectors. Moderate effort, high coverage gain (~556 situations between them, per §A2/§D3).
- **4.2 — Japan EDINET/TDnet** (562 situations — the single biggest non-US bloc). Needs Japanese-language ingest + the 大量保有 13G→13D purpose-flip detector. High value, highest build cost — do last.

### Phase 5 — Backtest → deployable strategy (the gate to ever being SCORED)
> *V1 Tier 5.*

- **5.1 — Forward returns by category × stage × market-cap × holding period** (e.g. "buy a Going-Private at announcement vs after the vote"), with **filing-date entry** from our `events.parquet` (clean point-in-time; removes the digest's weekly-lag bias).
- **5.2 — Activist track-record weighting** baked into deployable rules (which 13D filers actually create alpha — feeds 3.2).
- **5.3 — The promotion gate.** Only if a category×stage cohort clears the standard DSR/PBO/FDR gauntlet does any leg move from `SCORED=False` to a sized input. Until then, everything stays context-only.

### Ongoing / hygiene (V1)
- Let `benchmark_scorecard.json` accrue per build → watch self-sufficiency climb.
- Dedup edge cases (warrant/unit/preferred ticker variants), foreign-ticker resolution, the $4.5T market-cap parse-outlier sanity bound.
- Keep the digest as the **answer key** (re-grade ourselves), never the live source.

---

## 4. Open decisions (need your call — they reorder the phases)

1. **Market-cap floor.** We use $100M; the digest has *none* (820 sub-$50M situations, §A3). Lowering it captures the micro/nano special-sits niche (where retail edge is largest) but adds noise. **Recommend:** drop to ~$25M *behind a confidence gate* (only high-confidence S1 classifications shown sub-$100M).
2. **International order.** Recommend **Canada+UK before Japan** (English + structured + cheaper) — but if the goal is "match the digest's coverage stat fastest," Japan is the biggest single bloc. Your call on whether breadth or ease wins.
3. **How far past the digest to go.** S2/S4/S5 (arb math, activist track-record, lifecycle) are things the digest *doesn't* do — our integration edge. Confirm you want to prioritize *exceeding* the digest over merely *matching* its international breadth.
4. **The missing ChatGPT "similar sites" note** never made it into the repo — §2 above is my own competitor scan as a substitute. If you paste the note, I'll reconcile any sources it lists that I didn't cover.

---

## 5. Immediate next action

**Do 1.1 (source S1).** Extend the existing DeepSeek summary call in `collectors/special_situations.py::enrich_summaries` to also return verified `{category, role, confidence, deal_terms}`; consume `llm_category` in `engine/special_situations.py::build_situations`; re-validate with `benchmark_vs_digest.py` + the adversarial audit. It is ~free (the call already runs), fixes the precision bottleneck, and unblocks 1.2, 2.3, 3.1, and 3.2. Then 1.2 (merger-arb) for immediate tradeable value.
