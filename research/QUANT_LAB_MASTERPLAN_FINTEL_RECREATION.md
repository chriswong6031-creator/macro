# Quant Lab — Fintel quant-model recreation

Program home for recreating externally-published quant models on our own panel and
measuring whether they rank anything here. Wave 1 covers Fintel's Quality+Value family
(QV / QVM / QVO / QVF) plus one fully-specified control screen.

Status: **Wave 1 shipped 2026-08-05.** Engine + page + study live. Every result is
display-tier; nothing here ranks, sizes, or gates anything.

---

## §0 ACCEPTANCE GATES

Not done unless all of these hold. (CLAUDE.md §Spawn-handoff law — gates go at the top,
phrased "not done unless".)

1. **Every vendor claim carries provenance.** Publisher, date, URL. A claim we cannot
   source is not printed. Vendor performance statistics are reproduced as CLAIMS,
   attributed, never as findings of ours. ✅
2. **Every leg carries a fidelity grade and, when it is not `faithful`, a NAMED
   distortion.** A stand-in with an unnamed distortion is a lie of omission. ✅
3. **No backtest reads a non-point-in-time store.** `statements.parquet` is excluded by
   name with the reason recorded; only `fundamentals_panel.asof_date` and
   `statements_quarterly.filed` may gate a study. ✅
4. **Coverage is printed next to every measurement.** A leg computed on 43% of the panel
   ranks a different population than one computed on 94%. ✅
5. **A null or an inverted read is printed, not hidden.** Sign-aware verdicts: a
   significantly anti-predictive signal may never be reported as a survivor. ✅
6. **A composite that collapses to one leg is reported as `degenerate`, not under the
   parent model's name.** ✅
7. **Display-tier only.** No Quant Lab score is wired into any ranker, sizer, or gate.
   Promotion requires its own pre-registration. ✅
8. **Bilingual EN/ZH, light+dark, no hardcoded colours, Tier-1 header copy.** ✅

---

## §1 What Fintel actually discloses

Fintel's pages sit behind a Cloudflare bot-verification interstitial we do not bypass.
The usable primary sources are Fintel's own SYNDICATED articles (published under Fintel's
byline on Nasdaq), which carry the same boilerplate methodology blocks as the site **plus
per-name numeric readouts the site does not print in prose**. Those readouts turned out to
be the only quantitative window into the models.

### The model family

| Model | Composition | Disclosure |
|---|---|---|
| **QV** ("QuantSoft Score") | six-factor; "cash-generating ability and growth" + "a significant value factor" | 3 of 6 legs grounded |
| **QVM** | QV + QMM (Quantitative Momentum Model), momentum = 6-month price performance | lookback named; weights not |
| **QVO / QVF** | QV + two fund-sentiment factors | one of two named |
| Short Squeeze Score | short interest, float, borrow fee rates, 0–100 | inputs listed, no formula |

Attribution: the QV model was developed by Wilton Risenhoover from research at UCLA
Anderson. Coverage is stated as 75,000+ listed companies; the QVF screen is stated to rank
against **36,606 screened global securities**. Scores are percentiles, 0–100, 50 = average.

### The only place inputs are named

From the AMR article (2023-01-04) — the single source that says what each sub-score is
*computed from* rather than what it "measures":

- **Quality 97.40** — "3 year average return on investor capital of 0.42 which has grown
  by 11.54%" → **3y average ROIC + ROIC growth**
- **Value 92.55** — "3 year average EBIT/EV ratio of 0.20" → **3y average earnings yield**
  (Greenblatt's EBIT/EV)
- **Fund sentiment 74.97** — "13.71% growth of institutional ownership on the register"
  → **QoQ growth in 13F share count**

Those three quantities ground three of our six legs. Everything else in a six-factor model
is undisclosed. Our three inferred legs (gross profitability, accruals, FCF/debt) come from
the published lineage the vendor gestures at — Novy-Marx, Sloan, Greenblatt, O'Shaughnessy —
and are **marked as inferred** in the registry so nobody later mistakes them for Fintel's.

### The vendor's performance claim

> The Quality+Value Score was analysed by an independent firm … In one test over the
> period of 1992 to 2013, the theoretical CAGR of the Quality+Value score was 20.73% vs.
> the Russell 2000 CAGR of 10.33% … Sharpe 0.91 vs 0.46, Sortino 1.18 vs 0.48.

**Appraisal.** Reproduced as the vendor's claim. It is not evidence about our universe: the
window predates the model's publication, the testing firm is unnamed, the benchmark is a
small-cap index, and no turnover, capacity, or cost assumption is stated. Marketing
provenance, not a prior.

---

## §2 The combination rule — recovered from their own numbers

Fintel never publishes how it blends Quality, Value and Momentum. But the 2023-08-21
"Momentum Monday" article prints ten (Q, V, M, QVM) tuples. That is enough.

**Finding 1 — the total exceeds its own parts.** MCEM (86.15 / 89.66 / 75.60 → **91.04**)
and WSM (85.06 / 89.83 / 74.55 → **90.64**) both score higher on QVM than on any of their
three sub-scores. No convex weighted average can exceed its inputs. So the blend is
**re-percentiled against the universe after blending** — being good on three legs at once
is rarer than being good on any one, so the joint distribution has a thin upper tail that
re-ranking stretches.

**Finding 2 — the weights.** OLS of QVM on (Q, V, M) over the ten rows:

```
QVM ≈ 0.410·Q + 0.588·V + 0.110·M − 5.70      R² = 0.9978   max|resid| = 0.60
```

Weights summing to 1.108 with a negative intercept is exactly the signature of a
locally-linearised rank map (slope > 1 in the thin tail) — the same conclusion Finding 1
reaches independently.

**Read plainly: QVM is the QV score with a light (~11%) momentum tilt.** That matches the
vendor's own framing that momentum "slightly increases the ranks".

**Caveat, stated wherever the fit is shown:** n = 10, one date, all high scorers. This is
the **top-decile local rule**, not the global formula.

---

## §3 Can we rebuild it? — the substrate ledger

| Store | Point-in-time? | Key | Span | Verdict |
|---|---|---|---|---|
| `edgar/fundamentals_panel.parquet` | **Yes** | `asof_date` (436 distinct) | FY2009–2025, 1,552 tickers | the PIT spine |
| `edgar/statements_quarterly.parquet` | **Yes** | `filed` (3,452 distinct) | 2009Q1–2026Q2, 1,507 | source of `cash` (91%), `net_debt` (51%) |
| `edgar/statements.parquet` | **NO** | `as_of` = 5 FETCH timestamps, all 2026-06-15 | FY2020–2025 | **excluded from all studies** |
| `smart_money/<fund>/` | Yes | `filing_date` | 13F quarters | 53 curated funds, not the register |
| `yahoo/<ticker>.parquet` | Yes | trading date | ~3y in-tree | binding limit on study depth |

The `statements.parquet` exclusion is the one worth restating: it is our **richest** schema
(cash, current debt, inventory, receivables) and it would materially improve the EV and
invested-capital legs — which is precisely why the exclusion has to be explicit in code
rather than left to whoever writes the next backtest. Its dates record when *we downloaded*
the data, not when companies filed it.

### Per-leg fidelity (QV)

| Leg | Vendor said | We built | Coverage | Fidelity |
|---|---|---|---|---|
| 3y avg ROIC | ✅ named | NOPAT (21% flat tax) / (equity + debt − cash), 3 knowable FYs | 75% | proxy |
| ROIC growth | ✅ named | latest FY / FY−2 − 1, positive base only | 58% | proxy |
| 3y avg EBIT/EV | ✅ named | op_income / (mktcap + debt − cash) | 66% | proxy |
| Gross profitability | ✗ inferred | GP / assets (Novy-Marx) | 43% | proxy |
| Low accruals | ✗ inferred | −(NI − CFO) / assets (Sloan) | 94% | proxy |
| FCF / total debt | ✗ inferred | (CFO − capex) / total debt | 46% | proxy |

**Zero legs are `faithful`.** The named distortions that matter most:

- **Debt is half-missing.** `debt_lt` is present on ~49% of the PIT panel and short-term
  debt is absent from it entirely. Invested capital is understated and ROIC overstated for
  exactly the levered small caps this model targets.
- **EV is priced once.** Our market cap is a single cross-section held across all three
  averaged years, so our leg is "current EV vs 3-year average EBIT", not a 3-year average
  of the ratio.
- **The tax rate is ours, not theirs.** A flat 21% misstates NOPAT per name but applies the
  same distortion to everyone, which a cross-sectional rank tolerates better than a
  per-name effective rate estimated from a panel with no tax line.

### QVO is not recreatable here

The fund-sentiment leg measures **1.3% coverage** after CUSIP/name resolution. Fintel reads
the full 13F register (444 institutional owners for AMR); we track 53 curated managers, and
only ~20 names have two consecutive quarters inside our universe. A leg on 1.3% of the
panel cannot rank it. **Graded `absent`, excluded from the study, and the page says so.**
Closing this needs a full 13F aggregate feed — not a better mapper.

---

## §4 What it measured here

12 quarterly rebalances, 2023-06-30 → 2026-03-31, 63-day forward window, rank IC with a
Newey-West correction and Benjamini-Hochberg FDR across the leg panel.

| Model | Composite IC | t (HAC) | q | Verdict |
|---|---|---|---|---|
| Fintel QV | **−0.0296** | −2.06 | 0.070 | **ranked backwards** |
| Fintel QVM | −0.0166 | −1.32 | 0.298 | null |
| Quant Investing QVM | −0.0083 | −0.60 | 0.659 | null |

Per-leg, the pattern is consistent and interpretable:

| Leg | IC | q | Verdict |
|---|---|---|---|
| momentum_6m | **+0.0321** | 0.078 | ranked forward |
| momentum_3_6 | +0.0137 | 0.659 | null |
| ebit_ev | +0.0032 | 0.889 | null |
| ebit_ev_3y | −0.0090 | 0.678 | null |
| roic_growth | −0.0110 | 0.678 | null |
| accruals | −0.0241 | 0.070 | backwards |
| gross_profitability | −0.0278 | 0.533 | null |
| fcf_to_debt | −0.0321 | 0.007 | backwards |
| roic_3y | −0.0351 | 0.002 | backwards |
| gross_margin | −0.0585 | 0.040 | backwards |

**The story: the quality legs ranked backwards over this window and momentum is the only
leg that ranked forward.** Adding momentum to QV moves the composite from *inverted* to
*null* — momentum is offsetting the quality legs, not adding to them.

This corroborates our own `data/edgar/ic_scorecard.json` (deep 2011–2026 re-test), which
independently found `quality` mean IC +0.0042 and the equal-weight `composite` **−0.0072**.
Two different harnesses, two different windows, the same direction.

### What this does NOT establish

- **One regime.** 2023–2026 was an AI-led melt-up in which quality and value lagged badly.
  A different stretch could easily read the other way. This is not a refutation of the
  model; it is a measurement of one window.
- **Twelve readings is thin.** Borderline results are undecided, not settled.
- **Survivorship.** Delisted names are absent from our price panel, so every number is a
  mildly optimistic bound.
- **We tested our rebuild, not their model.** With zero faithful legs, a poor result may be
  our stand-ins failing rather than their idea.

---

## §5 The finding that actually decides integration

**Fintel's QV is a small-cap discovery model, and our fundamentals do not reach small caps.**

- Our price universe: 2,895 names (r2000 1,994 · sp600 633 · sp500 509 · sp400 412).
- Our **fundamentals** universe — the binding one for any QV recreation: **1,552**.
- Of the ten QVM leaders Fintel published on 2023-08-21, **six are outside our fundamentals
  panel** (CLS, CMT, KRT, GAMB, SCPL, MCEM, VASO). CMT and KRT are in our price universe
  with no fundamentals at all.

The model exists to surface small, overlooked companies and is benchmarked to the Russell
2000. That is precisely the size band where our filings coverage thins out. **Closing this
gap needs wider EDGAR coverage, not a better formula** — and until it is closed, a faithful
QV recreation here is structurally testing the model on the wrong population.

---

## §6 Where it lives

```
engine/quant_lab/
  specs.py    vendor registry — disclosure provenance, per-leg fidelity, distortions
  legs.py     PIT leg computation (the two PIT stores only)
  score.py    percentile scoring; the three combination rules; the vendor-rule fit
  study.py    IC / decile / FDR harness reusing engine.validation
  page.py     cheap payload assembler (reads the precomputed study)
scripts/build_quant_lab.py     the EXPENSIVE study — off the render path
templates/quant_lab.html.j2    the surface
tests/test_quant_lab.py        the honesty contract
```

Render-budget placement: the study (12 rebalances × a full leg cross-section) runs in
`scripts/build_quant_lab.py` and lands in `data/quant_lab/study.json`. `build_site.py`
reads that artifact and computes one live cross-section only.

---

## §7 Wave 2 — open work, in priority order

1. **W2-A · Widen the fundamentals universe toward the Russell 2000.** The §5 finding makes
   this the highest-value item by a distance; every other improvement is second-order until
   the model can be tested on the names it was built for.
   **SHIPPED 2026-08-05** — `collectors/edgar.py:_universe_tickers()` now unions each
   group's committed `constituents.parquet` with its closes cache across all four groups
   (`russell_breadth` included; its closes cache is a gitignored CI artifact, so the
   committed constituents table is what carries the R2000 on a fresh checkout). Universe
   1,577 → 2,895; the frames-API request count scales with years×concepts, never tickers,
   so the fetch cost is unchanged. Measured against the July candidates store: 1,268 of the
   1,461 fundamentals-absent candidates become coverable; the 193 that remain are foreign
   20-F/IFRS filers the us-gaap frames endpoint cannot serve (BABA/ASML/AZN class), funds/
   crypto tickers with no filings, and a small tail of non-index US filers outside the four
   tracked groups — each a separate lane, none reachable by widening this filter. The panel
   itself advances on the nightly's weekly `fetch_panel` cache expiry; archetype labels
   follow mechanically via `archetypes_history_refresh_if_stale()` (#4677). `edgar_eps`
   shares the universe and widens for free (also frames-based). The §5/§6 "1,552" figures
   and the committed study stamps describe the narrow-universe study and stay until the
   study re-runs on the widened panel (that re-run is the remaining W2-A follow-through,
   after which W2-F should re-stratify on the true small-cap band).

   **Measured end-to-end (local rebuild, 2026-08-05).** Panel 1,552 → **2,826 tickers**
   (22,458 → 35,953 rows, FY2009–2025); fetch wall-clock ~18 min, unchanged from the
   narrow build as predicted. Archetype store rebuilt from it in 3.8 s → 2,826 tickers;
   `heal_candidates_archetype` dry-run on 2026-07: **1,457 → 835 still-absent (622
   filled)**.

   **The next binding constraint is the PRICE universe, not the panel.** Of the 1,457,
   1,221 gained panel rows but only 622 labeled, because the archetype store labels
   100% of rows carrying a factor-table row (22,070/22,070) and only 46% of `fac_present
   =False` rows (6,349/13,883) — the fac-less path withholds a label rather than
   fabricating "mixed". 1,278 of the 1,316 never-factor-covered tickers are russell-only
   names: `equity_factors._closes()` reads `_UNIVERSE_GROUPS["broad"]` = the three S&P
   groups only, so R2000 names get no price → no mktcap → no factor row. Widening THAT
   is not a mechanical follow-through — it re-percentiles every rank on a user-facing
   surface across a 2× wider population, and `russell_breadth/_closes_cache.parquet` is
   a gitignored CI artifact absent from fresh checkouts — so it needs its own charter.
   The remaining 236 with no panel rows at all are foreign 20-F/IFRS filers, funds, and
   crypto tickers, unreachable from the us-gaap frames endpoint.
2. **W2-B · Point-in-time debt and cash on the annual spine.** Backfill `debt_cur` / `cash`
   into `fundamentals_panel` from the quarterly filed-date store so EV and invested capital
   stop depending on a ~49% debt column.
3. **W2-C · Deep price history.** The in-tree close caches cap the study at 12 rebalances.
   The IC scorecard already reaches 2011 on an offline deep panel; point the Quant Lab at
   the same cache to get a real regime sample.
4. **W2-D · Full 13F aggregate** — the only route to a real QVO. Until then the model stays
   graded `absent`.
5. **W2-E · Delisting-recovered prices.** `dead_name_panel` / `dead_name_prices` exist
   (97 names); wiring them removes the optimistic bound.
6. **W2-F · Size-stratified re-test.** Even inside our 1,552, re-run by market-cap tercile.
   If QV is inverted in large caps and flat in small, that is a materially different finding
   from a flat inversion — and it is the closest we can get to the vendor's population
   today.

**Not proposed:** promoting any Quant Lab score to rank/size/gate authority. That needs its
own pre-registration and would be premature on 12 rebalances of an inverted read.

---

## §8 Sources

| Key | Source |
|---|---|
| `fintel_amr_qvf` | "Coal Miner Alpha Metallurgical Resources Begins 2023 Leading the QVF Quant Model", Fintel via Nasdaq, 2023-01-04 — the only public source naming the sub-score inputs |
| `fintel_momentum_monday` | "Mid-August Momentum Monday Ranks Are Sparse…", Fintel via Nasdaq, 2023-08-21 — the ten (Q,V,M,QVM) tuples |
| `fintel_qv` / `fintel_qvm` / `fintel_quant_models` | fintel.io landing pages (Cloudflare-gated; content via syndication + the operator-supplied quote) |
| `quant_investing_qvm` | "Quality, value, momentum — the best strategy you have never heard of?", Quant Investing — the fully-specified control screen |

The control screen matters methodologically: it is the only model in the lab whose
specification is complete, so it separates "the Fintel model does not work here" from "our
reconstruction of it is wrong". Both came back null-to-inverted, which points at the
substrate and the universe rather than at the reconstruction.
