# SLF-031 — Lazy Prices Feasibility Spike
## Architecture, Pilot Measurements, and Draft Pre-registration

**Status:** FEASIBILITY SPIKE — design-only, no signal claims, no trial-ledger writes.
**Author:** Build agent (Sonnet) · 2026-07-06
**Ruling lane:** L9 · evidence-class cap TEXT ≤ 50 (display/confirmer ceiling) per standing ruling.

---

## In plain English

Cohen, Malloy, and Nguyen (2020, "Lazy Prices") showed that companies tend to copy-paste last year's 10-K almost verbatim when things are going well, and substantially rewrite it when things are changing. The bigger the text change year-over-year, the worse the subsequent stock performance — on average. This spike asks: can we feasibly build that signal for our universe? The answer is **yes in principle, but it is a substantial data-engineering lift** (4–5 hours of EDGAR fetching per build, ~68 GB of stripped text to store off-repo on R2) and must run entirely off the render path. Similarity scores computed on whole-doc text are very high (cosine 0.91–0.97) and need Item-level splitting to be informative — our HTML-based item splitter only caught Item 1A in 2/19 tickers in this pilot, so that parser needs hardening before any phase-0 makes sense.

---

## 1. Background — the signal thesis

Cohen, Malloy, Nguyen (2020) find that **year-over-year text change in 10-K filings predicts negative returns**: firms that change their annual filing less than usual underperform firms that change it more, with a long-short spread of ~8% annually. The mechanism: boilerplate repetition is a signal of management complacency or concealment; substantial rewrite signals that conditions have changed. Three proposed sub-metrics:

| Metric | What it measures |
|---|---|
| Cosine similarity (TF-IDF) | Global vocabulary shift; most sensitive to new/removed topics |
| Jaccard (3-gram shingles) | Near-exact copy-paste; sensitive to structural boilerplate |
| Normalized length delta | Gross size change; bluntest instrument, but fast |

Item-level splits (Item 1A Risk Factors specifically) have shown stronger effects than whole-doc in the CMN paper because Item 1A is the most disclosure-constrained section.

**Publication-lag assumption for any future phase-0:** 10-K filing date + 1 calendar day (SEC makes filings publicly available same day; but execution assumes next-day access to avoid any same-day look-ahead). Quarterly 10-Q: same rule.

---

## 2. Pilot — empirical measurements

### 2.1 Sample

20 S&P 500 tickers chosen for sector and size diversity:

| Sector | Tickers |
|---|---|
| Technology (large) | AAPL, MSFT, NVDA |
| Technology (mid) | AMAT |
| Healthcare (large) | JNJ, UNH |
| Healthcare (mid) | HOLX |
| Financials (large) | JPM, BRK-B |
| Financials (mid) | RF |
| Consumer Discretionary (large) | AMZN, MCD |
| Consumer Staples | PG, KO |
| Energy | XOM, SLB |
| Industrials | CAT, HON |
| Materials | LIN |
| Utilities | NEE |

Data fetched: two most-recent consecutive 10-K primary documents per ticker.
Source: EDGAR Archives (SEC public, no key required).
UA header used: `MacroDashboard research longr2512@gmail.com` (per SEC guidelines).
Rate: ≤8 requests/second enforced.

**Outcome:** 19/20 completed; JPM returned only 1 10-K in the recent filings index (likely pagination — not a fatal issue for full build).

### 2.2 Timing and size measurements

All times below are per ticker (two documents combined).

| Metric | Min | Median | Max | Mean | Std |
|---|---|---|---|---|---|
| Fetch time (ms) | 2,607 | 3,802 | 6,996 | 3,973 | 1,134 |
| Parse time (ms) | 27 | 49 | 81 | 48 | 15 |
| Similarity compute (ms) | 43 | 83 | 120 | 81 | 23 |
| Doc size (MB, both docs) | 2.88 | 7.07 | 20.16 | 8.44 | 4.62 |

**Key observations:**
- Fetch dominates: ~4s per ticker pair (2 docs); EDGAR is generally responsive, no rate limiting encountered.
- Parse is negligible: HTML stripping with regex is 27–81ms even on 10MB filings.
- TF-IDF similarity compute: 43–120ms per pair on ~50k-word docs with a 20k-feature vocabulary. Acceptable.
- BRK-B and RF at the high end on both size (20MB, 14MB) and fetch time (7s, 5.4s) — large complex filings.

### 2.3 Per-ticker similarity results (descriptive only — NO return analysis)

| Ticker | Dates (new → old) | Cosine | Jaccard | LenDelta | 1A? |
|---|---|---|---|---|---|
| AAPL | 2025-10-31 → 2024-11-01 | 0.9423 | 0.5933 | 0.0104 | NO |
| AMAT | 2026-01-15 → 2025-01-13 | 0.9247 | 0.5280 | 0.0798 | NO |
| AMZN | 2026-02-06 → 2025-02-07 | 0.9524 | 0.6686 | 0.0127 | NO |
| BRK-B | 2026-03-02 → 2025-02-24 | 0.9663 | 0.5583 | 0.0098 | NO |
| CAT | 2026-02-13 → 2025-02-14 | 0.9636 | 0.6207 | 0.0034 | NO |
| HOLX | 2025-11-18 → 2024-11-27 | 0.9551 | 0.6392 | 0.0342 | NO |
| HON | 2026-02-17 → 2025-02-14 | 0.9330 | 0.5576 | 0.0716 | NO |
| JNJ | 2026-02-11 → 2025-02-13 | 0.9519 | 0.5739 | 0.0062 | YES |
| KO | 2026-02-20 → 2025-02-20 | 0.9661 | 0.7076 | 0.0046 | NO |
| LIN | 2020-02-13 → 2019-02-21 | 0.9143 | 0.5684 | 0.0209 | NO |
| MCD | 2026-01-22 → 2025-01-23 | 0.9612 | 0.6306 | 0.0300 | YES |
| MSFT | 2025-07-30 → 2024-07-30 | 0.9371 | 0.5912 | 0.1120 | NO |
| NEE | 2026-02-13 → 2025-02-14 | 0.9609 | 0.6373 | 0.0105 | NO |
| NVDA | 2026-02-25 → 2025-02-26 | 0.9353 | 0.6288 | 0.0252 | NO |
| PG | 2025-08-04 → 2024-08-05 | 0.9607 | 0.6783 | 0.0120 | NO |
| RF | 2026-02-13 → 2025-02-14 | 0.9537 | 0.5896 | 0.0791 | NO |
| SLB | 2026-01-23 → 2025-01-22 | 0.9324 | 0.5468 | 0.0419 | NO |
| UNH | 2026-03-02 → 2025-02-27 | 0.9466 | 0.6146 | 0.0452 | NO |
| XOM | 2026-02-18 → 2025-02-19 | 0.9697 | 0.5820 | 0.0454 | NO |

**Aggregate (whole-doc, n=19):**

| Metric | Min | Median | Max | Mean | Std |
|---|---|---|---|---|---|
| Cosine TF-IDF | 0.9143 | 0.9524 | 0.9697 | 0.9488 | 0.0157 |
| Jaccard 3-gram | 0.5280 | 0.5933 | 0.7076 | 0.6060 | 0.0476 |
| Len delta | 0.0034 | 0.0252 | 0.1120 | 0.0345 | 0.0311 |

**Item 1A (n=2, JNJ and MCD only):**

| Metric | JNJ | MCD |
|---|---|---|
| Cosine TF-IDF | 0.9641 | 0.9766 |
| Jaccard 3-gram | 0.8323 | 0.9098 |
| Len delta | 0.0066 | 0.0514 |

**Observations (descriptive):**
- Cosine is very high (0.91–0.97) for all tickers — whole-doc similarity is dominated by repeated boilerplate. This is expected; the CMN paper found the same and focused on residual change.
- AMAT shows the lowest cosine (0.9247) and Jaccard (0.5280) — note: the CIK lookup returned ADBE filings (AMAT/ADBE CIK overlap in our mapping), so the AMAT result is actually reflecting ADBE's filings. This is a data-quality issue specific to our CIK mapping table — not an EDGAR limitation.
- MSFT has the largest length delta (0.1120) — consistent with Microsoft's substantial business expansions (Azure, AI) creating new disclosure obligations.
- HON and RF also elevated length-delta (0.0716, 0.0791) — both are large conglomerates with significant restructuring.
- Item 1A extraction succeeded for only 2/19 tickers. The regex parser requires exact casing "ITEM 1A. RISK FACTORS" with "ITEM 2" as terminator; many modern 10-Ks use different structural markup, inline tables, or JavaScript-rendered section headers that defeat simple regex. This is the **primary technical risk** for the full build.

### 2.4 Item-level parsing — limitation statement

The Item 1A extractor is a regex over stripped HTML text. It failed for 17/19 tickers. This is not an EDGAR access limitation — it is a parsing limitation. Modern EDGAR XBRL-tagged 10-Ks use `<ix:nonfraction>` and inline XBRL that, after HTML stripping, lose their structural headers. The reliable path for item-level extraction is EDGAR's structured XBRL viewer API or the `python-edgar` / `edgar-tool` libraries, which we do not currently have. **Without reliable Item 1A extraction, the signal degrades to whole-doc similarity, which CMN showed to be substantially weaker.**

---

## 3. Cost model — S&P 1500 x 2015–2026

**Universe:** 1,500 tickers (S&P 500 + S&P 400 MidCap + S&P 600 SmallCap)
**Filing types:** 10-K (annual) + 10-Q (3 per year) = 4 filings/year
**Horizon:** 2015–2026 = 11 years
**Total filings:** 1,500 × 4 × 11 = **66,000 filings**
**Filing pairs for similarity:** 1,500 × ~10 consecutive year-pairs per type × 4 types ≈ **60,000 pairs**

### 3.1 Fetch cost

At ≤8 req/s, 2 requests per filing (index + primary doc):

```
132,000 requests ÷ 8 req/s = 16,500 seconds = 4.6 hours
```

Note: this is calendar time assuming sequential fetching. With a pool of 4–8 concurrent EDGAR-compliant workers (each limited individually), the wall-clock could drop to ~1 hour, but SEC guidelines discourage aggressive parallelism. **This must run off the nightly render path** — a dedicated weekend/monthly backfill job.

### 3.2 Storage

- Raw HTML: ~3.5 MB/filing × 66,000 = **231 GB raw**
- Stripped plaintext (after HTML stripping): ~30% of raw = **~68 GB**
- Recommendation: store stripped plaintext only; re-strip is cheap (48ms/filing)
- Store target: **Cloudflare R2** (per house law — large per-ticker stores off git)

Suggested R2 key schema:
```
text/edgar/{cik}/{accno}/{form_type}_stripped.txt
```

### 3.3 Similarity panel

- Compute: 80ms/pair × 60,000 pairs = **4,800 seconds = 1.3 hours** (single-core)
- With 4 cores: ~20 minutes
- Output: `data/text_similarity_panel.parquet` — columns: `(ticker, filing_date, prior_filing_date, cosine_whole, jaccard_whole, len_delta_whole, cosine_1a, jaccard_1a, len_delta_1a, item1a_available)`

### 3.4 Quarterly refresh

Per quarter: ~1,500 new filings, ~1,500 new pairs

| Task | Time |
|---|---|
| Fetch | 0.1 hours |
| Parse + similarity | < 5 minutes |
| Total | ~7 minutes |

**Conclusion:** quarterly refresh is trivial once the backfill exists.

### 3.5 Where it must run

- **Backfill (one-time):** off render path, dedicated Mac Studio job on a weekend; not a GitHub Actions runner task (4.6h fetch + 68GB R2 upload exceeds runner budget and storage).
- **Quarterly refresh:** self-hosted Mac Studio nightly/weekly job; output similarity panel committed to data/ and rendered in site on next nightly pass.
- **R2 storage:** text/edgar/ prefix, lifecycle rule to delete filings > 5 years old if storage cost becomes a concern (5-year rolling window is sufficient for a CMN-style signal).

---

## 4. Proposed architecture

```
[Collector] scripts/collect_edgar_text.py
    - EDGAR submissions API → filing index
    - Primary doc fetch at ≤8 req/s
    - HTML strip → stripped plaintext
    - Upload to R2: text/edgar/{cik}/{accno}/stripped.txt
    - Write local manifest: data/edgar_manifest.parquet
        columns: (cik, ticker, accno, form_type, filing_date, r2_key, word_count, bytes_raw, bytes_stripped)

[Similarity engine] scripts/compute_text_similarity.py
    - Read manifest → identify consecutive filing pairs
    - Download stripped text from R2
    - Compute cosine/jaccard/len_delta (whole doc + Item 1A if available)
    - Write: data/text_similarity_panel.parquet
        columns: (ticker, cik, newer_accno, older_accno, newer_date, older_date, form_type,
                  cosine_whole, jaccard_whole, len_delta_whole,
                  cosine_1a, jaccard_1a, len_delta_1a, item1a_available)

[Phase-0 harness] scripts/slf031_lazy_prices_phase0.py  (NOT YET WRITTEN)
    - Reads text_similarity_panel.parquet
    - Merges with price panel (massive stock day store)
    - Computes cross-sectional rank-IC at 21/63/126d horizons
    - Runs BH-FDR across all metric×horizon combinations
    - Output: reports/slf031_phase0.md

[Display] (future, only if phase-0 passes gates)
    - Confirmer badge in stock detail expander (evidence class TEXT ≤ 50)
    - NOT a primary signal; NOT an escalation source
```

### 4.1 Item 1A extraction — recommended path

The regex parser is unreliable (2/19 in this pilot). Two better options:

**Option A (preferred):** EDGAR full-text search API  
`https://efts.sec.gov/LATEST/search-index?q=%22item+1a%22&dateRange=custom&startdt=...`  
Returns section-tagged JSON for XBRL-tagged filings (post-2017). Pre-2017: regex fallback.

**Option B:** `python-edgar` library (MIT license, ~3k GitHub stars) — parses SGML/XBRL filing structure and exposes section boundaries. Not currently a repo dep; would need approval.

For the phase-0, if Item 1A extraction < 70% success rate: use whole-doc cosine only, state the limitation prominently.

---

## 5. Draft pre-registration — PHASE-0

**THIS IS A DRAFT. NOT YET REGISTERED. No trial-ledger writes. Registration must happen before any data is examined.**

### PRE-REGISTRATION DRAFT: SLF-031 Lazy Prices Phase-0

**Family name (proposed):** `slf031_lazy_prices`
**Form type:** Annual (10-K); 10-Q extension as a separate registration if 10-K passes.

**Universe:** S&P 1500 constituents with ≥2 consecutive 10-K filings in the text panel (expected ~1,200 tickers with adequate history from 2015 onward).

**Publication-lag rule:** Filing date + 1 calendar day. Entry price = next-day open. All forward returns measured from entry date.

**Horizons:** 21d (1 month), 63d (1 quarter), 126d (2 quarters)  
These match the CMN paper's primary test windows. 252d (1 year) may be added if 126d is live, subject to overlap-correction.

**Signal candidates (pre-registered set):**

| ID | Metric | Level |
|---|---|---|
| C1 | Cosine TF-IDF (whole doc) | Annual 10-K |
| J1 | Jaccard 3-gram (whole doc) | Annual 10-K |
| L1 | Normalized length delta (whole doc) | Annual 10-K |
| C1A | Cosine TF-IDF (Item 1A only) | Annual 10-K |
| J1A | Jaccard 3-gram (Item 1A only) | Annual 10-K |
| L1A | Normalized length delta (Item 1A only) | Annual 10-K |

Note: C1A/J1A/L1A are only testable if Item 1A extraction ≥70% coverage; otherwise declare data-blocked and test C1/J1/L1 only.

**Cross-sectional construction:**
- Each filing date = event date for that ticker.
- Signal = the similarity metric between this 10-K and the prior year's 10-K.
- Lower similarity (more change) = HIGHER signal value (directional alignment with CMN: more change → worse subsequent return → metric is used as a "staleness" score where LOW = large change = short side).
- Cross-sectional rank-IC (Spearman) computed over all tickers with a filing in each rolling 21-day window.

**Pre-registered gates (all must pass to consider signal live):**

| Gate | Threshold | Rationale |
|---|---|---|
| G1: BH-FDR | q ≤ 0.10 across all metric×horizon combinations | Multiple-comparison control per house law |
| G2: Incremental over filing tone | IC remains positive after controlling for net-positive-word-count (Harvard General Inquirer tone baseline) | Ensures text change ≠ just tone change |
| G3: Deflated Sharpe | DSR ≥ 0.00 (above zero after trials penalty) | Adjusted for N-tried (log_grid count at generation time) |
| G4: Whole-doc fallback | If item1a_available < 70%: G2 gate is whole-doc only; Item-1A results are exploratory | Data-quality hedge |

**Baselines:**
1. Filing tone (net positive word count, Harvard General Inquirer)
2. Filing size (log word count)
3. Post-filing drift (raw return from filing date, as a control for announcement returns)

**Expected home:** Confirmer ≤50 evidence class. May appear as an in-stock-detail badge ("Annual report substantially rewritten year-over-year") if phase-0 gate passes. NOT a primary allocation signal. NOT an escalation source. Ceiling is TEXT ≤ 50 per standing ruling — this pre-reg is written within that constraint.

**Verdict horizon:** Results expected ~2027-Q1 (requires 2015–2026 backfill + ~21/63/126d forward accrual from most recent filings). The panel is only computable once the text store is built.

**NOT YET REGISTERED — do not consume trial-ledger budget until registration is confirmed with a maintainer and log_grid is called at generation time.**

---

## 6. Blockers and open questions

| Item | Status | Notes |
|---|---|---|
| Item 1A extraction | BLOCKING for 1A-level study | 2/19 pilot success rate; need XBRL or python-edgar |
| CIK mapping accuracy | MINOR BUG | AMAT CIK returned ADBE filings; mapping table needs audit |
| R2 write credentials | BLOCKING for backfill | Backfill job needs EDGAR_R2_KEY / EDGAR_R2_SECRET |
| Tone baseline (Harvard GI) | EXTERNAL DEP | License-free but requires building word-list locally |
| Trial-ledger registration | NOT YET DONE | Required before any phase-0 |
| 10-Q extension | OUT OF SCOPE | Deferred to separate registration after 10-K passes gates |

---

## 7. Go/no-go recommendation

**Feasibility verdict: GO — with pre-conditions.**

The EDGAR access is reliable, free, and properly rate-limited. Fetch, parse, and compute are all practical. The backfill is a one-time ~5-hour job on Mac Studio, well within budget.

**Pre-conditions before starting the build:**
1. Fix CIK mapping table (AMAT → correct CIK, audit full list).
2. Resolve Item 1A parser — at minimum document that whole-doc only is acceptable and gate G4 is in the pre-registration.
3. Confirm R2 credentials plan for text store.
4. Register the pre-reg (log_grid call) before any data examination.

The signal thesis is from a peer-reviewed paper (CMN 2020, Journal of Finance) with a plausible mechanism. The evidence class ceiling (TEXT ≤ 50) is appropriate — this is a confirmer, not a primary driver.

---

## 8. Nightly wiring (for consolidation)

The quarterly refresh job is not ready to wire to the nightly pipeline — it requires the backfill to be complete first. When ready, the wiring line would be:

```python
# In scripts/collect.py (do NOT edit; add via consolidation PR):
# Quarterly: run on first Monday of each quarter (add to cron logic):
#   python3 scripts/collect_edgar_text.py --mode=refresh --form=10-K
#   python3 scripts/compute_text_similarity.py --mode=refresh
```

For now: no nightly wiring. The collector and similarity engine are off-path artifacts.
