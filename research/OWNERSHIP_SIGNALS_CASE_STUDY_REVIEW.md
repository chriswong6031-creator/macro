# Review: The JPM/SBSW Ownership-Signals Case Study

*Produced by a 6-agent review workflow (methodology · empirical fact-check · finance literature · codebase-fit → adversarial red-team → synthesis), 2026-06-21. Source doc: `JPM_SBSW_Ownership_Signals_Backtest.md`.*

## Verdict — trust the conclusion, distrust every number

The case study lands in the right place — *"JPM ownership data is a supporting institutional-flow factor, not a standalone buy signal; analyst ratings are informational, low predictive weight"* — and its central instinct (a custodian bank's 5% stake is **aggregation, not conviction**) is squarely backed by SEC 13G regulation and the academic literature. But the quantitative artifact that supposedly proves this — a +37.6% / +112.5% "backtest" — is an **n=2 / n=3, single-name, single-cycle anecdote** whose entire edge is one SBSW leg that coincides exactly with the 2024–26 precious-metals rally, with open marks counted as returns and frictions excluded. The ownership *facts* are real (exact EDGAR 13G share counts verify to the share); the *trade math* is unverified, partly inflated, and statistically powerless.

## Factual provenance — PARTLY REAL, with one structural mislabel

- **The ownership backbone is genuine and exact.** JPM's two real US Schedule 13G filings on Sibanye are in EDGAR and match the doc to the share: **2025-10-17 = 195,466,310 ordinary shares @ 6.5%** (acc. 0000019617-25-001005); **2026-01-16 = 140,082,817 @ 4.7%** (acc. 0000019617-26-000028); both CUSIP S7627K103, subsidiaries J.P. Morgan SE / J.P. Morgan Securities LLC. Implied float reconciles to ~2.85–2.95B shares; the 1 ADR = 4 ordinary ratio and several price points verify exactly. A pure hallucination essentially never produces these.
- **The strongest tell — 13G ⟷ JSE/SENS conflation.** The doc presents one unified "JPM Beneficial-Ownership History" of nine rows as if all were US Schedule 13G events. **EDGAR shows only TWO JPM-on-Sibanye filings ever.** The 2024–early-2025 rows (5.64%, 3.78%, 6.32%…) are **South African JSE/SENS notifications under Companies Act s122** — a different statute, cadence, and aggregation rule — and one quarter-end snapshot date is mislabeled a "Schedule 13G event."
- **Trade math is the least-verified part.** Two entry prices are inflated ~2.7% above actual closes ($8.56 vs $8.33; $16.03 vs $15.60) — consistently upward. The quarterly 13F ADR counts and the Dec-2023 $7→$6 downgrade are uncorroborated. **Provenance laundering risk:** exact filing facts buy credibility that does *not* transfer to the returns the whole exercise turns on.

## Where it breaks down (methodology + stats)

- **Sample size is fatal.** 13F strategy = n=2 (one win, one open loser); 5% strategy = 3 regimes. Win-rate CI at 1/2 ≈ [0.10, 0.91] — you cannot reject a coin flip. The headline figures carry false precision.
- **Single-cycle metals-beta confound, never controlled.** The +192% winning leg coincides exactly with the 2024–26 PGM/gold rally. No spread to GDX/GDXJ/platinum/palladium. The doc's own "best interpretation" *requires* "an improving precious-metals regime" — an admission the edge **is** the beta. **No lens computed the counterfactual** (GDX/platinum return over the exact window) — the single most decision-relevant number.
- **Marks counted as returns.** The −26.5% and −15.7% legs are unrealized June-18 marks on open positions, compounded into the headline totals.
- **Asymmetric "conservative" framing + look-ahead.** Monthly-high entries (knowable only after month-close) paired with exits near favorable disclosure prices. Pessimistic entries + optimistic exits ≠ a "lower bound."
- **Strawman analyst test.** Requiring "Overweight before buy" tests the *level*, guaranteeing you miss any name that rallies while rated Neutral — then discards the actually-informative event (the Dec-2023 Overweight→Neutral downgrade + target changes).

## What the literature actually says

- **13F cloning** — real but lag-decayed edge; copycats match net-of-fee returns *because* the ~45-day lag erodes the rent (Frank-Poterba-Shackelford-Shoven 2004). Confirms filing-date discipline.
- **Edge lives in conviction, not the book** — a manager's single top-conviction position beats the market and the rest of their own book by ~+2.8–4.5%/yr (Cohen-Polk-Silli / Anton "Best Ideas"). A diversified custodian/dealer 13F is the canonical *zero*-selection holdings report.
- **13D ≫ 13G** — activist 13D ≈ +6–8% announcement, no 1-yr reversal (Brav-Jiang-Partnoy-Thomas 2008); passive 13G far weaker; the 13G→13D *switch* isolates the signal.
- **Custodian 5% ≠ conviction** — a Qualified-Institution 13G certifies "ordinary course, no control intent" = client/index/custody/securities-lending/market-making aggregation. Scoring a buy-regime on it *inverts* the evidence.
- **Analysts: revision, not level** — ~+3% / −4.7% reactions to up/downgrades, downgrade drift ~6mo (Womack 1996); consensus-level long-short ≈ 0 net of turnover, ratings optimism-skewed ~7× buys/sells (Barber et al. 2001).

## What this means for OUR build (ranked)

**RANK 1 — Audit and fix the quarter-end look-ahead before any scoring.** Two paths key on quarter-end:
- *Scored (higher priority):* the `smart_money_13f` convergence channel is weighted **0.85** into `altdata_models.channel_records`, fed from `altdata.inst_13f_changes` reading Quiver `sec13f_changes` keyed on `ReportPeriod` (quarter-end). Consumable by a scorer today — audit first.
- *Display:* `smart_money.py:282` returns `p.stem` (= `period_end`) and `_accumulation`/`accumulation_trend` key the series on quarter-end. `filing_date` is already captured (`edgar_13f.py:261`) but never read. Cheap fix: thread `filing_date` through `_read_all`, emit `available_on`. Currently inert (display-only) so the fix changes nothing visible — it just makes the as-of date trade-correct *before* any scorer touches it.

**RANK 2 — One pre-registered as-of date for all scoring.** Add `as_of_for_scoring()` + a test asserting no scoring path reads `period`/`period_end`/`ReportPeriod` as the entry date.

**RANK 3 — Phase-2 analyst signal: revisions, never levels (buildable free today).** `finnhub_altdata.py:84` already pre-stores `prev_buy`. Build `engine/analyst_revisions.py`: signal = `(strongBuy+buy) − prev_buy`, scored vs forward returns through the existing `outcomes.py`/Brier loop, as a low-weight CONTEXT channel near `analyst_upgrade_cluster` (=0.35). Per-analyst accuracy is the only piece needing Finnhub-Premium/Benzinga.

**RANK 4 — A 13D/G beneficial-ownership CONTEXT dimension, aggregation-guarded.** A 13D *activist* signal already exists in the special-sits desk (`special_situations.py:46-47`: SC 13D→Activist, 13G→skip-but-watch-for-flip); the gap is a per-ticker above-5%/filer-tagged *regime* on `stock_view`. Build `engine/beneficial_ownership.py` emitting `{above_5pct, filer, filer_type, latest_event_date, is_13g_to_13d_flip}`, with **two mandatory guards:** (a) tag custodian/index complexes (JPM/BLK/STT/Vanguard) + passive 13G as low-conviction, foreground activist 13D + flips (custodian/index DENY-list); (b) for foreign issuers key on **filing source/jurisdiction** — SBSW crossings are JSE/SENS s122, not US 13G. Plug in as a sibling of `_ev_ownership` (`stock_view.py:512`), `tone='neutral'`, **not scored**.

**RANK 5 — Validate "context-not-alpha" is enforced, not just commented.** Lock with a guard test asserting `smart_money`/`accumulation` and any new ownership dimension are absent from every scoring/allocation import graph.

**RANK 6 — Codify the honest-gate for any future promotion.** Min N *decorrelated* events + sector-spread regression (vs GDX/platinum) + net-of-cost haircut + multiple-comparisons/DSR bar, enforced in `validation.py`. Separate realized from unrealized P&L. Process guard: **any single-name LLM-generated backtest is pre-selected on a happy outcome** — it can never clear the gate on its own.

## Red-team corrections carried into this synthesis
- Don't double-count the kill: n=2/single-cycle already drains the number of information; the aggregation confound is fatal to *interpreting any future bank-5% signal*, not independently fatal to *this* backtest.
- The codebase lens had a **severity inversion** — it graded the inert display path "high" and the live 0.85-weighted convergence channel "low." The live scored channel is the higher priority.
- "No 13D/G signal exists" was imprecise — a 13D activist signal exists in special-sits; what's missing is the per-ticker ownership *regime* dimension.
- Friction is not one-directional here: SBSW pays large variable dividends, which for a long *understates* total return — net sign of frictions is ambiguous (though round-trip costs on an illiquid ADR still plausibly swamp a 2–3-trade edge).

## Bottom line

Trust the verdict; the per-number precision is decorative — discount it. The single most actionable finding is in *our* code, not the doc: a verified quarter-end look-ahead, with the 0.85-weighted `smart_money_13f` convergence channel as the first thing to audit because it's the one that can actually be scored. Make **filer-type, jurisdiction, and filing source first-class keys** before any ownership leg is weighted, score analyst **revisions not levels** (buildable today off `prev_buy`), and never let a single-name, single-cycle result clear the honest-gate.
