# Non-Technical Durable-Bottom Program — W0 Inventory (census of existing implementations)

**Status:** census record, 2026-07-05; produced by workflow wf_ec6648eb (12 sonnet lanes); adjudicated by research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md; companion paper research/nontech_bottom/NON_TECH_DURABLE_BOTTOM_SIGNALS_FOR_FABLE.md.

This is a point-in-time census — verify paths before building against it.

---

## Insider sponsorship (F1)

The insider sponsorship lane is the most built-out non-technical bottom signal in the repo. A full PIT per-transaction SEC Form 4 panel exists (2,314,291 rows, 16,834 tickers, 2006q1–2026q1, keyed on filing_date) via collectors/sec_insider.py + 81 per-quarter parquet files. engine/insider_factor.py implements all Codex signal forms except the drawdown-conditioned cluster (opportunistic/routine CMP split, distinct-buyer cluster, role-weighted dollars, market-cap normalisation). Two completed phase studies exist: Phase 0 (scripts/insider_phase0.py → reports/insider-phase0.md) returned net_usd_mcap|SN as the sole BH-FDR(10%) survivor in the PIT S&P 1500 mid-cap era (IC 0.029, t=2.9, q≈0.10); Phase 1 (scripts/insider_phase1.py → reports/insider-phase1.md) confirmed orthogonality to momentum/size/reversal and a long-only active Sharpe 0.70–0.73 but DSR FAILS the conservative whole-program haircut (n_trials=12 → DSR~0.85). The combined SUE×insider study (reports/sue-insider-deep-phase0.md) returned NEUTRAL on survivorship-clean S&P-1500: insider_opp_buyers IC non-zero but BH-FDR fails, long-only DSR matched by a random placebo. Published verdict (research/INSIDER_FACTOR.md §6): "orthogonal conviction/confirmer leg, expressed LONG-ONLY; do NOT size standalone." Current display surfaces are factors.html leaderboard (net_mcap_bps ranked) and per-stock positioning chip (stock.html). A known dead-path bug: engine/equity_factors.py reads insider_panel.parquet (flat file) which only exists after backfill_panel() runs nightly via build_site.py; the flat file is gitignored and absent in a fresh worktree, causing the panel-tier to silently fall through to the single-quarter aggregate (cluster=False). No Neural Web synapse registration exists for any insider family. None of the four Codex F1 signal forms (insider_cluster_after_washout, off_schedule_top_officer_buy, insider_buy_vs_prior_year, insider_cluster_near_confluence) have been built or measured against drawdown-conditioned windows; all cross-sectional studies were unconditional rank-IC sweeps, not durable-bottom conditional studies.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| SEC Form 4 per-transaction panel (collectors/sec_insider.backfill_panel) | collectors/sec_insider.py:299 | none | Strict: filing_date only. 2006q1–2026q1, 20 years, US only, 16,834 tickers |
| engine/insider_factor.py — cross-sectional signal construction | engine/insider_factor.py | none | Causal: trades enter only after filing_date. US SEC Form 4 universe, trailing k-month (default 6) window |
| Phase 0 harness (scripts/insider_phase0.py → reports/insider-phase0.md) | scripts/insider_phase0.py | none | Full PIT: S&P 1500 PIT membership, filing_date alignment. 2006–2026, mid-cap era cutoff 2012 |
| Phase 1 harness (scripts/insider_phase1.py → reports/insider-phase1.md) | scripts/insider_phase1.py | none | Full PIT as Phase 0. S&P 1500, mid-cap era 2012-01-31 to 2026-02-27, 170 monthly rebalances |
| SUE×insider combined study | scripts/sue_insider_deep_phase0.py | none | Strictest available: deep close matrix union delisted recovery. Deep+delisted prices (1962→), PIT S&P-1500, 2011–2026 |
| Display surfaces: factors.html leaderboard + stock.html chip | engine/equity_factors.py:113 | display | Panel path PIT when flat file present; fallback to single-quarter aggregate (cluster=False) |
| altdata_models.py + altdata_confirmers.py — insider confirmer channel | engine/altdata_models.py:449 | display | US stocks with altdata coverage; filing_date alignment is upstream in collector |
| Canada insider (engine/canada_insider.py) | engine/canada_insider.py | display | TSX (.TO) tickers only, ~150-row cap per name from yfinance; no PIT de-bias study run |

**Gaps:**
- insider_cluster_after_washout: no implementation. Codex form requires >=2 or >=3 distinct open-market buyers within 45 trading days AFTER a 15–30% drawdown. Existing engine computes rolling trailing-window cluster counts (unconditional), not drawdown-conditioned event windows.
- off_schedule_top_officer_buy: CMP opportunistic split exists but Codex form requires per-event binary flag isolating CEO/CFO as separate output. No binary is_ceo_cfo_buy per-event exists.
- insider_buy_vs_prior_year: current net buy $ as percentile of ticker's own history — not built. No self-normalised percentile ranking against the ticker's historical distribution exists.
- insider_cluster_near_confluence: cluster within -20 to +15 trading days of a MACD+StochRSI fire — not built. No join between the insider panel and the entry-stack technical fire log exists.
- Per-event insider records for bottom-context cluster detection: the raw panel contains the raw material, but no function exists that takes a (ticker, drawdown_start_date) pair and retrieves + aggregates subsequent filing events into a cluster summary.
- No Neural Web synapse registration for any insider family (bottom_sponsor.insider or any predecessor). No spine emission exists.
- No durable-bottom conditional study: all three completed studies test unconditional cross-sectional IC, not the conditional question (does cluster sensor reduce stop-out/dead-money rate vs matched controls).

**Collisions:**
- insider_cluster_after_washout → engine/insider_factor.py build_signals() n_buyers / opp_buyers rolling window (partial: existing engine is a fixed monthly rebalance grid; Codex form requires event-anchored window per ticker drawdown start date)
- off_schedule_top_officer_buy → engine/insider_factor.classify_routine() + role_weights() (substantial overlap; gap is per-event binary output vs monthly panel column)
- insider_cluster_near_confluence → altdata_models.py insider_cluster channel >=3 buyers (close functional match but uses quiver_insiders feed and single-quarter aggregate rather than PIT panel; must not be double-registered as the same evidence)
- Distinct-buyer cluster count → altdata_models cluster_min=3 vs scripts/research/insider_netbuy_cluster.py CLUSTER_MIN=2 vs Codex F1 >=2 or >=3 (three different thresholds; must be collapsed before a spine event_key is defined)

**Binding laws:**
- research/INSIDER_FACTOR.md §6: ship as ORTHOGONAL conviction/confirmer leg, expressed LONG-ONLY, with net_usd_mcap as construction. Not a standalone dollar-neutral alpha sizer.
- reports/sue-insider-deep-phase0.md VERDICT: NEUTRAL — no new scored rank. Cross-sectional event IC ~0 on survivorship-clean S&P-1500. The Codex conditional (drawdown-anchored) question has NOT been tested and is not covered by this verdict.
- RUL-13 (Amendment 1): primary horizon = 21 trading days (mae21 co-primary). Phase 0/1 studies used 63d as primary — legally compliant for the existing research base but new Codex W2 studies must use 21d.
- CLAUDE.md: LLMs may not originate signals, scores, or escalations. All insider event extraction must use the deterministic SEC panel.
- NON_TECH_DURABLE_BOTTOM §5.4: filing_date is the only legal alignment date (already enforced in existing engine — confirmed PIT).
- NON_TECH_DURABLE_BOTTOM §3 F1 kill rule: if cluster buys do not improve clean-liftoff or dead-money versus same-sector same-fire-date controls, keep display-only.
- NON_TECH_DURABLE_BOTTOM §5.3 Neural Web kernel promotion bar: n_eff >= 12 per marginal cell before quarterly FDR batch; confirmer chip requires >=3pp improvement in clean-liftoff or dead-money, same sign in >=3/4 eras.

**Event counts:** PIT panel: 2,314,291 total Form 4 P/S transactions, 16,834 tickers, 2006q1–2026q1. Approximate open-market buy events (code=P): ~1.1–1.3M. Active names per monthly rebalance in S&P 1500 PIT universe: median ~520 names. For the drawdown-conditioned cluster form: no event count exists yet. Rough estimate 800–2,500 qualifying drawdown episodes per year across S&P 1500, of which perhaps 15–25% would have an insider cluster (>=2 distinct buyers) within the 45-day window — yielding 120–625 positive events per year, or 2,400–12,500 total over the 20-year panel.

---

## Corporate actions — buybacks, activists/13D, strategic holders (Codex §F2) + EDGAR infrastructure

The repo has substantial EDGAR infrastructure for the 13D/activist leg and the 8-K "Capital Returns" category, all wired into the live nightly pipeline. The beneficial-ownership sweep (collectors/beneficial_ownership.py) pulls SC 13D/13G daily from the EDGAR index with a 45-day rolling window, filer-SGML enrichment, and a custodian-aggregation guard; it feeds engine/beneficial_ownership.py (regime classifier with activist/flip/passive/custodial states) → engine/intel_discovery.py (scan_activist_ownership, cap 20, 63d freshness gate) → altdata_models.py ("activist_13d" channel, weight 0.55) → stock_view.py display. A monthly workflow (validate-leading-legs) runs an event-study harness (scripts/validate_activist_ownership.py) against 2024-Feb post-rule-change filings and writes a gate JSON that promotes the leg from measuring to scored if drift is right-signed with HAC-t >= 2.0. The 8-K "Capital Returns" category (buyback authorizations, special dividends) exists in engine/special_situations.py as a keyword-classified text category fed by collectors/edgar_8k.py (nightly), rendered on special_situations.html. Actual repurchase dollar amounts exist only as a stub: scripts/backfill_edgar_quarterly.py extracts PaymentsForRepurchaseOfCommonStock into data/edgar/statements_quarterly.parquet, but that script is explicitly marked "Wire nothing downstream yet" and no engine or builder reads statements_quarterly.parquet. Shares outstanding is in the annual fundamentals.parquet from edgar_facts.py and in signal_factory.py as the net_issuance leg. The F2 Codex signal forms buyback_authorization_after_washout, buyback_actual_intensity, and strategic_holder_add have no dedicated bottom-context implementation; existing assets handle each fragment only in a generic event-desk context, not conditioned on prior washout depth.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| EDGAR 13D/13G beneficial-ownership collector | collectors/beneficial_ownership.py:1 | display | Filing date from EDGAR index. All SEC 13D/13G filers with a ticker; lookback 45 calendar days per run |
| Beneficial-ownership regime engine + activist discovery | engine/beneficial_ownership.py:1 + engine/intel_discovery.py:277 | display | Entry at first close strictly after filing date. US equity names in SEC company_tickers master |
| Activist track-record engine (filer prior) | engine/activist.py:1 | none | Entry at filing date. 13D events in data/special_situations/events.parquet with priced targets |
| Activist ownership event-study validation harness | scripts/validate_activist_ownership.py:1 | none | Post-2024-Feb-05 13D initiations only (amended 10→5-day filing window). yfinance price for target + SPY |
| Special situations desk — 8-K 'Capital Returns' category | engine/special_situations.py:40,205 + collectors/edgar_8k.py | display | Event date = 8-K filing date. All SEC filers with resolved tickers; floor $100M mcap |
| EDGAR quarterly statements backfill (repurchases + shares) | scripts/backfill_edgar_quarterly.py:1 | none | Uses filed date; ~1,334-name fundamentals universe; history from SEC XBRL tagging (~2009+). OFF-PIPELINE |
| Annual repurchases field in edgar_facts / fundamentals.parquet | collectors/edgar_facts.py:34 + engine/stock_fundamentals.py:886 | none | yfinance snapshot is point-in-time on pull date only, no history |
| Net issuance leg in signal_factory (shares-outstanding change) | engine/signal_factory.py:13,140-146 | none | asof filtering on edgar-filed date. Fundamentals panel universe (~1,334 names) |
| Smart-money 13F engine (strategic/marquee holders) | engine/smart_money.py:1 + engine/altdata_models.py:116,477 | display | Filing date used (available_on). Curated marquee fund list only (~17 funds) |

**Gaps:**
- buyback_authorization_after_washout: existing CAP category classifies 8-K buyback announcements but does NOT condition on prior drawdown depth (>=25% drawdown from high).
- buyback_actual_intensity: statements_quarterly.parquet has PaymentsForRepurchaseOfCommonStock but has no downstream consumer and is not in the nightly pipeline.
- activist_13d_after_washout: existing activist 13D detection does not condition on whether the target experienced a prior washout.
- strategic_holder_add: no dedicated signal form conditioned on drawdown for broad high-conviction 13F holder adds.
- bottom_sponsor.corporate_action NW lobe: not built. No such lobe exists in engine/neuralweb/.
- Balance-sheet veto for buyback: no veto logic for high leverage / cash falling / debt maturities near.
- EDGAR full-text search for buyback context in 10-Q/10-K: the current CAP keyword classifier works on 8-K text only.

**Collisions:**
- activist_13d_after_washout (F2) → engine/intel_discovery.py scan_activist_ownership + altdata_models activist_13d channel (partial; existing is generic event-desk signal; F2 adds washout-conditioning requirement)
- strategic_holder_add (F2) → engine/smart_money.py + altdata_models 13f_add / smart_money_13f channels (partial overlap; F2 is broader and requires bottom-conditioning)
- buyback_authorization_after_washout (F2) → engine/special_situations.py CAP category (duplicate risk; new signal must be a filtered/conditioned view, not a parallel 8-K parser)
- bottom_sponsor.corporate_action NW lobe → altdata_models.py activist_13d + special_situation channels + Amendment 1 RUL-16 esx_sponsorship (naming collision; corporate_action sub-channel is NOT esx_sponsorship)

**Binding laws:**
- SCORED=False enforced on engine/special_situations.py (line 34) and engine/beneficial_ownership.py — both are display-only; activist_13d scoring gate requires validated drift from validate_activist_ownership.py (currently 'measuring').
- LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations. Any buyback/activist signal must be display-only until gauntleted.
- Nightly is the sole advancer of forward ledgers. buyback_actual_intensity requires statements_quarterly.parquet which is manual-only and off the nightly path.
- PIT discipline (NON_TECH §line 354): 13F uses filing date not quarter-end; EDGAR facts use filed/as-of dates not period-end.
- Amendment 1 RUL-16: sponsorship stratification is pre-registered as family esx_sponsorship (sector velocity sign); corporate-action sponsorship must coordinate to avoid double-counting.
- Amendment 1 RUL-13 horizon doctrine: 21d primary, 63/126d holdability lane only.
- SEC fair-access policy ≤10 req/s; EDGAR quarterly backfill targets 8 req/s (0.12s sleep).

**Event counts:** 13D initiations post-2024-Feb: validate_activist_ownership explicitly notes _MIN_EVENTS=40 is likely not yet met as of Jul-2026, implying <40 priced events in 18 months. Capital Returns 8-K events: based on $100M floor, likely 5–20 events/month. Smart-money 13F adds: ~100–200 adds/quarter across the curated 17-fund universe.

---

## Fundamental repair — SUE, guidance, revisions, quality floors (Codex §F3)

All four buildable components of Codex §F3 exist in the repo but are wired for cross-sectional factor ranking and single-stock context pages, not for the bottom-entry durability use-case the Codex demands. SUE is the most developed: a fully PIT quarterly EPS panel (collectors/edgar_eps.py → data/edgar/eps_quarterly.parquet) feeds engine/sue.py, which was originally scored but then DEMOTED to display/confirmer after a deep 2011–2026 Phase-0 showed IC collapsing from 0.038 to 0.0005 (HAC t 0.06). It survives in setups.py as a confirmer-weight signal and in stock_score.py at 10% weight in the EDGE composite — but is never conditioned on proximity to a washout bottom. Analyst revisions are present via two separate feeds: collectors/finnhub_altdata.py (monthly direction deltas via Finnhub → engine/analyst_revisions.py) and collectors/equity_revisions.py (yfinance eps_revisions drip → data/revisions/latest.parquet; breadth, est_chg_30d/90d, eps_dispersion_norm, rev_growth_fwd). The guidance pipeline (collectors/edgar_guidance.py → data/edgar/guidance_hits.parquet → engine/guidance_gap.py) is live and nightly-ish (runs in build_foresight.py), but it produces a per-THEME raise/cut band for the Thematic Foresight Desk, not a per-TICKER guidance_delta_positive signal. The quality-floor components (Piotroski F-score, Altman Z, Sloan accruals) live in engine/stock_fundamentals.py as display-only accounting-quality reads — explicitly labeled context-not-signal and not wired to any scored output or entry-quality gate. None of the five Codex signal forms have any Neural Web wiring.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| engine/sue.py + collectors/edgar_eps.py | engine/sue.py | none | Real SEC filing dates as asof_date (median ~34d post quarter-end). Fallback = period_end+60d synthetic lag. ~1,317 S&P 1500 tickers, 2008-present |
| collectors/equity_revisions.py + data/revisions/latest.parquet | collectors/equity_revisions.py | none | Current-snapshot problem: yfinance gives only the CURRENT estimate snapshot; history.parquet accrues forward from collection start. S&P 1500 breadth + midcap + smallcap |
| engine/analyst_revisions.py (Finnhub recommendation direction) | engine/analyst_revisions.py | none | Monthly snapshots accruing with file dates. Free Finnhub tier watchlist only |
| collectors/edgar_guidance.py + engine/guidance_gap.py | engine/guidance_gap.py | display | file_date from EDGAR is PIT-accurate. 90-day rolling window. THEMATIC not STOCK-LEVEL scope |
| engine/stock_fundamentals.py — Piotroski/Altman/Sloan/quality reads | engine/stock_fundamentals.py | none | Annual statements lagged to EDGAR report date. ANNUAL SNAPSHOTS, ~12mo staleness. S&P 1500 universe with EDGAR XBRL |
| scripts/validate_sue.py + reports/sue-deep-history-phase0.md | scripts/validate_sue.py | none | Same asof_date gate as production engine. Shallow window passes; deep window fails (IC ~0, HAC t 0.06). 2011–2026, ~1039 names/q |

**Gaps:**
- sue_positive_near_bottom: cross-sectional SUE exists (display-only) but zero code conditions it on bottom proximity or washout state.
- sue_less_bad_repair: serial-miss → improvement transition logic — no trend/trajectory computation in engine/sue.py; only the latest cross-sectional z is stored.
- guidance_delta_positive: edgar_guidance.py produces phrase-matched 8-K hits rolled up to THEMES, not individual stock signals; no numeric guidance range parse exists.
- revision_breadth_turn: polarity-flip detector — only raw direction labels and cross-sectional z are present; no flip-detection or event-anchored turn logic.
- bottom_fundamental_repair: Neural Web node absent from engine/neuralweb/; no NW spine context, no kernel conditioning, no display wiring.
- Revenue revision trend (30d/90d): collectors/equity_revisions.py documents this is structurally unavailable from yfinance (line 43).
- PIT quality-floor gate: Piotroski/Altman/Sloan are annual-filing reads (~12mo staleness) baked into static per-stock pages.

**Collisions:**
- quality_floor as entry gate → cn_reversal_sleeve.py _FORBIDDEN_GATE_FIELDS (line 66) explicitly lists 'quality_floor' as forbidden — Phase-0 measured it flipping the CN reversal edge negative (−0.21%/mo). Not binding for US bottom-entry but a strong prior.
- revision_breadth_turn → engine/analyst_revisions.py direction field and equity_revisions.py breadth field both present in stock_score.py; gap is the FLIP event anchored to a bottom-fire date.
- sue_positive_near_bottom → setups.sue_confirmer (engine/setups.py line 62) and stock_score._EDGE_W['sue']=0.10 are unconditional; code scaffolding exists in setups.py but different question.
- guidance_delta_positive (per-stock) → engine/guidance_gap.py compute_guidance_gap() already named 'guidance_gap' and run nightly — different granularity (THEME vs STOCK).

**Binding laws:**
- Amendment 1 §A (RUL-13): 21d is the primary horizon for bottom-entry signals; 63/126d is holdability lane only. Codex §F3 assigns bottom_fundamental_repair to 63/126d — this is the holdability lane per Amendment 1.
- SUE has a completed Phase-0 (FAIL on deep history). Any of the five Codex F3 signal forms conditioning on bottom proximity requires its own Phase-0 before scoring.
- LLM de-escalation-only law: guidance_delta_positive cannot be LLM-extracted without a Phase-0 validating the text-derived delta.
- DATA_SIGNAL_EXPANSION_2026 §5: analyst revision breadth (yfinance snapshots) must remain display/confluence only until ~1yr of weekly PIT vintages accrue.
- CLAUDE.md render budget law: ~67min, 4-core-bound. Per-ticker guidance numeric parse from 8-K XML on the nightly path must be off-path.
- Ledgers law: nightly is the sole advancer of forward ledgers; any PIT accrual for revision history must run in the nightly build only.

**Event counts:** SUE panel: ~65k (ticker, quarter) rows, ~1,317 tickers, 2008-present. Revision breadth: drip ~200 names/build, universe ~1,500+ names, ~6-day staleness window. Finnhub recommendation snapshots: monthly per ticker, watchlist-sized. Piotroski/Altman: one read per ticker per annual filing cycle (~1,000–1,500 names with EDGAR XBRL).

---

## Event-risk hygiene — earnings blackout, dilution/shelf/ATM/convertible, lockup expiry, debt maturities, FDA/PDUFA/court calendar (Codex §F4)

Earnings-blackout hygiene (the `esx_ev_blackout` family) is the most advanced sub-lane: the historical anchor store data/edgar/earnings_8k_dates.parquet (98,975 rows, 1,314 tickers, 2004–2026, gate PASS at 1,143 names × >=8y) was built by collectors/edgar_earnings_8k.py for the in-flight W1-SEV study; the live Nasdaq drip data/earnings/earnings.parquet (1,364 tickers, as_of 2026-06-19) already feeds earnings_days into the US stock score and size-down logic in engine/stock_score.py:668–672. IPO/SPAC lockup data exists as a display-only calendar (engine/ipo_lockup.py, data/ipo/lockups.parquet 46 prospectus-confirmed deals, data/ipo/calendar.parquet 1,027 IPOs) with a phase-0 event study already run (scripts/ipo_lockup_phase0.py), verdict display-only. Everything else in the §F4 signal family — dilution/shelf/ATM/convertible filing detection, debt-maturity nearness, FDA/PDUFA/court-date calendar — has no implementation beyond scattered qualitative flags. W1-SEV is actively in flight with trials registered and the 8-K anchor data built; no W1-SEV report exists yet under research/entry_stack/.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| esx_ev_blackout family (S-EV in-flight study) | scripts/research/entry_strata_phase0.py:113 · research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md:74–82 | none | Historical anchor = EDGAR 8-K Item 2.02 filing_date (PIT-clean). Deep panel 38,250 fires / baskets 113,542 fires; 8-K anchor 1,314 tickers 2004–2026 |
| EDGAR 8-K Item 2.02 earnings-date store | collectors/edgar_earnings_8k.py · data/edgar/earnings_8k_dates.parquet | none | filing_date = SEC acceptance date. ~1,314 US tickers, full history 2004–2026 |
| Live earnings calendar (Nasdaq drip) | data/earnings/earnings.parquet · collectors/equity_earnings.py · engine/stock_fundamentals.py:787–809 | display | Forward-looking only (next scheduled date). 1,364 US tickers. Rows with passed next_dates are stale and must be dropped under the F1 per-row freshness law |
| earnings_days size-down logic (stock_score.py) | engine/stock_score.py:662–672 | display | Same as live Nasdaq calendar; ~1,364 names |
| IPO lockup expiry calendar and phase-0 study | engine/ipo_lockup.py · data/ipo/lockups.parquet · data/ipo/calendar.parquet · scripts/ipo_lockup_phase0.py | display | US IPOs only; 46 prospectus-confirmed, rest use 180d standard. SPAC mechanics explicitly excluded (ipo_lockup.py:56–58) |
| Dilution detection in stock_fundamentals.py | engine/stock_fundamentals.py:420,546,700–716 | display | Historical share count from EDGAR XBRL — PIT at annual filing cadence. ~1,335 EDGAR-covered US names |
| openFDA drug approval history | engine/altdata.py:566–577 · collectors/openfda.py · data/openfda/approvals.parquet | display | Approval date from FDA = PIT-clean for the outcome. NOT forward-looking. Healthcare/biotech names with FDA submissions |
| Clinical trials pipeline | engine/altdata.py:411–423 · collectors/clinicaltrials.py · data/clinicaltrials/trials.parquet | display | first_post date = PIT-clean. Biotech/pharma names with ClinicalTrials.gov registrations |
| Special situations 8-K parser | engine/special_situations.py:94–108 | spine-context | Filing date = PIT-clean. US 8-K filers; operating companies only |
| event_calendar.py (macro event calendar) | engine/event_calendar.py | display | Release dates from FRED/OMB/BLS schedules. US macro only; 14-day forward horizon |
| bottom_sensors.parquet envelope (RUL-15, Amendment 1 §C2) | research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md:71–91 | none | Schema specified; earnings_next_date binds from live earnings.parquet. Not yet built |

**Gaps:**
- dilution_overhang: no forward S-3/424B5 issuance calendar per ticker; special_situations.py does not extract a per-ticker forward offering date.
- lockup_expiry_overhang for SPAC De-SPAC and secondary lockup windows — ipo_lockup.py explicitly excludes SPACs (line 56–58) and covers only the standard 180d window.
- debt_maturity_refi: no debt-maturity date extraction from EDGAR or any other source.
- regulatory_binary: openFDA carries historical approvals only; no forward PDUFA date feed exists.
- court_date / litigation_binary: no court-calendar feed or docket-date extraction.
- W1-SEV study script and report — collectors/edgar_earnings_8k.py and anchor store are built, trials registered, but run_w1_sev.py does not exist and no S_EV_REPORT.md is present under research/entry_stack/.
- event_blackout rejection tag emitter — grading.REJECTION_TAXONOMY contains the slot (grading.py:110) but nothing currently emits it.
- bottom_event_hygiene Neural Web family (direction=-1, is_veto=true) — no engine/neuralweb family or synapse entry for this lane exists.

**Collisions:**
- earnings_blackout (§F4) → esx_ev_blackout family (Entry-Stack Expansion W1-SEV, in flight) — DIRECT COLLISION: do not build a parallel implementation; consume the W1-SEV verdict when it lands. Amendment 1 §B table explicitly marks this: "ALREADY IN FLIGHT."
- lockup_expiry_overhang (§F4) → engine/ipo_lockup.py + data/ipo/lockups.parquet + scripts/ipo_lockup_phase0.py (PARTIAL COLLISION: standard IPO lockup implemented as display-only calendar with phase-0 verdict; Codex form needs per-fire window logic and SPAC lockup extension)
- dilution_overhang (§F4) → engine/stock_fundamentals.py:708 dilution_pct backward-looking share-count check (CONCEPTUAL CONFUSION RISK: existing flag is a backward-looking quality screen, not a forward event sensor; using it would mis-label them as equivalent)

**Binding laws:**
- RUL-4 (Masterplan §10): S-EV is the ONLY candidate permitted to target a hard gate, and only under hygiene semantics with the F1 per-row fail-open rule.
- F1 per-row freshness law (Masterplan §3 F1, §9 RT row, Amendment 1 §A): veto iff (next_date >= today) AND (next_date − today <= k) AND (as_of within 10 trading days of today); rows with next_date < today are DROPPED; collector outage => fail-open, never a blocked board build.
- Amendment 1 RUL-13: primary horizon = 21d; W1-SEV grandfathered with stop5 primary and mae63 as secondary, mae21 computed at adjudication.
- HYGIENE promotion bar (Masterplan §5): CI-excluding-0 degradation of the vetoed set on stop5 OR mae63 (pooled FE, k=3 primary); vetoed volume <= 10% of fires.
- Amendment 1 §B: EVENT_BLACKOUT overlay in bottom_sensors envelope is display-only — no ranking authority until the label earns its own pre-registered family verdict.
- event_calendar.py module docstring: no event-risk score / conviction dampener; the impact field is DISPLAY tier only.

**Event counts:** esx_ev_blackout study universe: 38,250 deep fires / 113,542 baskets fires. Estimated inside-window fraction at k=3: roughly 1–3% of fires per k-day window, implying ~1,100–2,000 in-window fires on deep. EDGAR 8-K anchor: 98,975 Item 2.02 filings across 1,314 tickers 2004–2026, averaging ~4 per ticker-year. IPO lockups: 46 prospectus-confirmed deals; calendar has 1,027 total IPOs.

---

## Macro/credit stress release (Codex §F5)

All raw series for F5 are already collected, computed, and live in the regime architecture, but none is wired as a Neural Web sensor family nor instantiated as a bottom-context conditioner. OFR FSI (daily, 2000+, 9 legs), NFCI/ANFCI/subindices (weekly, 1971+), STLFSI (weekly, 1994+), HY OAS BAMLH0A0HYM2 (daily, 1997+), IG OAS, MOVE (daily, 2003+), CP spreads A2P2 and CP-bill (daily, 1997+), and OFR SOFR/EFFR repo rates (2016+) are all collected and in the feature frame. The existing regime stack consumes them at two depths: (1) engine/conditions.py produces a full systemic_stress block that feeds market_state.py's liquidity component and is embedded in the Neural Web world_state as risk_radar_raw; (2) risk_radar.py uses hy_oas 21d ROC as a Tier-A validated leg (credit_oas_roc, lift_2020=1.23). A dedicated phase-0 study (scripts/validate_stress_gate.py) ran the OFR FSI vs NFCI forward-drawdown-discrimination test and returned display-only verdict. The kill rule is exactly stated in the Codex paper: F5 must prove increment over VIX plus SPY drawdown plus existing market_state/risk_regime conditioning; none of those columns are currently on gate_fires_deep.parquet, so no head-to-head kill-rule test exists yet.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| OFR FSI collection and storage | data/ofr_fsi/ (fsi.parquet + 8 sub-legs) | display | No revisions; no ALFRED vintage needed. 2000-01-03 to current; ffill_limit=7 |
| NFCI / ANFCI / subindices collection | data/fred/NFCI.parquet + ANFCI.parquet + NFCIRISK.parquet + NFCICREDIT.parquet + NFCILEVERAGE.parquet | spine-context | NFCI NOT in VINTAGED_SID_TO_COL (re-revises all history, API timeout). 1971+; 55+ years |
| STLFSI4 collection and PIT vintage | data/fred/STLFSI4.parquet | display | VINTAGED: stlfsi in VINTAGED_SID_TO_COL (pit.py:84). lag_bd=6. Only credit/stress series with proper ALFRED vintage. 1994+; ~32 years |
| HY OAS (BAMLH0A0HYM2) | data/fred/BAMLH0A0HYM2.parquet + data/archive/BAMLH0A0HYM2.parquet | kernel | No revisions. credit_oas_roc validated Tier-A radar leg (21d ROC, lift_2020=1.23). 1997+ deep history via archive merge |
| MOVE index collection | data/yahoo/_MOVE.parquet | kernel | No revisions. rates_move lift_2020=1.52 but era_robust=False. vol_regime_move_pctile in us_regime.parquet. 2003+; ~23 years |
| CP spreads (A2/P2 and CP-bill) | data/fred/RIFSPPNA2P2D90NB.parquet + RIFSPPNAAD90NB.parquet | display | No revisions. Embedded in systemic_stress block in us_regime.parquet archive. 1997/1998+; ~28 years |
| OFR SOFR/EFFR repo rates | engine/funding_stress.py + data/ofr/FNYR-SOFR-A.parquet etc. | display | No revisions. Short history (8y) limits use as conditioning variable for long-run studies. 2016-2018+ only |
| systemic_stress block in conditions.py | engine/conditions.py:143-481 | spine-context | systemic_stress.lead_lag='coincident' — documented at conditions.py:474-476. Not a leading indicator. Archive only ~12 rows |
| market_state.py liquidity component | engine/market_state.py:290-318 | spine-context | Current-state read, not a historical series |
| risk_radar.py credit scare (Tier A) | engine/risk_radar.py:82-114 | kernel | No revisions. credit_oas_roc is the only era_robust validated stress leg in the entire radar |
| world_state.py liquidity lobe | engine/neuralweb/world_state.py:285-289 | display | Current snapshot only |
| quad_nfci_phase0.py — NFCI conditioning study | scripts/quad_nfci_phase0.py | none | Uses latest-revised NFCI (not PIT). NFCI from 1971; regime quad from 1971 |
| validate_stress_gate.py — OFR FSI phase-0 | scripts/validate_stress_gate.py | none | Both halves of available history from 2000+ |

**Gaps:**
- stress_peak_turn signal form: no engine emits 'OFR FSI or NFCI extreme percentile starts falling' as a derived boolean/score on a per-date basis. Only the direction (rising vs easing) is computed, not a peak-detection with look-back confirmation.
- credit_spread_turn signal form: HY OAS 21d ROC exists as a radar leg but only in the de-risk (widening) direction. A 'spread peak and reversal' is not computed anywhere.
- liquidity_impulse signal form for US (FRED/ALFRED PIT): China and ECB have liquidity_impulse blocks but no analogous US liquidity-impulse turn series exists.
- rates_vol_relief signal form: MOVE percentile exists as a radar leg but only as a stress detector, not a peak-and-turn.
- bottom_macro_release Neural Web family: no synapse registered, no spine emission, no family budget pre-registered in entry_strata_phase0.py.
- Per-fire macro conditioning columns on gate_fires_deep.parquet: VIX level, SPY drawdown, market_state/risk_regime state, NFCI direction, and OFR FSI pctile are NOT joined onto the fire panel. The kill rule cannot be tested without building this join.
- Historical systemic_stress time series for backtest conditioning: conditions.py computes the block nightly but us_regime.parquet archive is only 12 rows (2 weeks). A full re-derivation from raw FRED/OFR parquet files is needed for any historical phase-0 study.
- NFCI PIT vintage: NFCI is excluded from VINTAGED_SID_TO_COL by design. For a PIT-clean study using NFCI, the analyst must use STLFSI4 (which IS vintaged) or accept the revision-present flag.

**Collisions:**
- stress_peak_turn → engine/conditions.py systemic_stress block computes ofr_fsi_pctile and ofr_fsi_trend (rising/easing); risk_radar.py credit scare uses hy_oas 21d ROC (direction is computed; peak detection with confirmation look-back is not)
- credit_spread_turn → risk_radar.py credit_oas_roc (validated Tier-A leg, lift_2020=1.23) — F5 turn form must invert sign of this leg; kill rule says F5 must beat this incumbent
- rates_vol_relief → risk_radar.py rates_move leg (lift_2020=1.52, era_robust=False); vol_regime.py move leg — relief turn (MOVE falling from elevated) not computed
- liquidity_impulse → regime.py liquidity_overlay (expanding/neutral/contracting) — existing is a level/direction classifier; impulse (second-derivative) is not computed; TGA/RRP/reserve series are not ALFRED-vintaged
- esx_sponsorship (Amendment 1 lane B2) — name collision only: esx_sponsorship tests oracle sector velocity, not F5 macro/credit stress; two separate families

**Binding laws:**
- Kill rule (Codex §F5): F5 must prove incremental value over VIX, SPY drawdown, AND existing market_state/risk_regime. None of those columns are currently on gate_fires_deep.parquet — the kill-rule test requires building a macro-conditioning join first.
- OFR FSI verdict (validate_stress_gate.py + conditions.py:474-476): OFR FSI is labeled 'coincident' and DISPLAY-ONLY. This verdict covers the level/direction form; the peak-turn form is explicitly unvalidated.
- NFCI PIT exclusion (config.yml:87 + pit.py): NFCI excluded from ALFRED vintage backfill. Any historical study using NFCI as a conditioning column carries revision lookahead.
- Amendment 1 RUL-15 bind-first law: bottom_sensors.py envelope BINDS existing emitted fields; an F5 family that recomputes stress series from scratch would violate this law.
- Amendment 1 B0 binding law (RUL-15): the bottom_sensors.py envelope binds existing emitted fields and adds only 2 new rolling columns.
- Amendment 1 RUL-13 horizon doctrine: primary = ~21d; F5 is expected to condition entry PERMISSION at the 21d level.
- Amendment 1 B2 scoping (RUL-16): esx_sponsorship pre-registered with budget 8; any F5 study using oracle velocity as a macro-permission proxy should coordinate with B2.

**Event counts:** gate_fires_deep.parquet: 38,250 fires (1962–2026); stress series coverage starts 1997+ (HY OAS), 2000+ (OFR FSI), 1971+ (NFCI), 2003+ (MOVE). Usable conditioning window for all F5 series simultaneously: approximately 2003+ (~23 years, ~5,800 business days). Expected fires in the 2003+ window: ~13,800 fires. Stress elevated (OFR FSI pctile >80%) base rate historically ~5–8% of days, yielding ~700–1,100 fires in elevated-stress regimes. Stress peak-turn (FSI pctile >80th AND falling) ~3–5% of days, ~400–700 fires — likely near the MIN_FAMILY_N=12 threshold per marginal cell.

---

## Positioning/flow capitulation — AAII, NAAIM, COT, ICI, FINRA margin, short interest (Codex §F6)

All five major feed categories have partial implementations, but none is wired into Neural Web or has any bottom-specific transform. NAAIM is the most mature: 1,043 weekly rows from 2006-07, a completed phase-0 study (CONFIRMER verdict — drawdown reduction real but fails to beat 200dma, honest null), and a display leg in the Fear/Greed composite. AAII has only 22 rows (2026-02 to present) due to PerimeterX bot-wall blocking the free scrape; it is hard-excluded from the Fear/Greed composite and is a raw context tile only. COT is well-collected (17 active markets, ES+NASDAQ equity-index specs since 1997/1999, weekly at 3-day lag) and is the third leg of the capitulation gauge (conditions.py:354–358); the capitulation overlay phase-0 shows the 3-leg stack does NOT beat a dumb VIX>30 rule (head-to-head p=0.52), verdict CONFIRMER. FINRA short interest (bi-monthly snapshot) has exactly one settlement date on disk (2026-05-29, 1,499 names); Signal Commons W0 added a short_interest_history.parquet accrual path but the file does not yet exist. FINRA daily short volume is rolling 30-day, context-only. ICI equity fund flows and FINRA margin debt/statistics are not collected at all — zero code or data files in the repo for either.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| NAAIM exposure collector + data | collectors/sentiment.py (NaaimAdapter), data/sentiment/naaim.parquet | display | Weekly survey self-dated; 7-day forward lag in phase-0 harness. 2006-07-05 to present (~20y) |
| NAAIM phase-0 validation study | scripts/naaim_overlay_phase0.py, reports/naaim-overlay-phase0.md | display | PIT-honest: 7-day lag applied. 2006-07 to 2026-06, 5015 trading days |
| AAII bull/bear collector + data | collectors/sentiment.py (AaiiAdapter), data/sentiment/aaii.parquet | display | No PIT panel. 22 rows (2026-02 to present). HARD-EXCLUDED from Fear/Greed composite |
| COT collector + data (equity-index speculative positioning) | collectors/cot.py (CotAdapter), data/cot/cot_es_spx.parquet, data/cot/cot_nasdaq.parquet | display | 3-day lag documented. ES from 1997 (~29y), NASDAQ from 1999 (~27y). Weekly cadence |
| Capitulation gauge + phase-0 study | engine/conditions.py:347-359 (capitulation_score), scripts/capitulation_overlay_phase0.py, reports/capitulation-overlay-phase0.md | display | Reconstructed faithfully from config thresholds; no look-ahead. SPY 1993-01-29 to 2026-06-17 |
| FINRA bi-monthly short interest (snapshot) | collectors/finra.py, data/finra/short_interest.parquet | none | NOT PIT-safe for backtesting (code comment at line 144-157). One snapshot: 2026-05-29 |
| FINRA daily short volume (rolling panel) | collectors/finra_short_volume.py, engine/short_volume.py, data/finra_short_volume/panel.parquet | none | PIT-safe by construction (never revised). Rolling ~30 calendar days only. 33,806 rows |
| Fear/Greed composite (NAAIM leg) | engine/fear_greed.py, scripts/build_site.py:362-385 | display | NAAIM leg: 2006-07 to present. Excluded legs: AAII (young), putcall (young) |
| Positioning display in macro page / FE-factor chip | scripts/build_site.py:312-390 (positioning_rows), scripts/build_site.py:1494-1681 | display | COT since 1997/1999; insider from sec_insider collector |

**Gaps:**
- aaii_bear_extreme_turn: AAII history is only 22 rows. No extreme-percentile computation is possible; the Codex form requires years of history.
- naaim_exposure_washout_turn (bottom-specific form): existing NAAIM phase-0 tests a trend-following drawdown overlay on SPY, not conditioned on a technical bottom fire. The conditional form has never been built or tested.
- cot_equity_spec_washout (bottom-specific form): COT spec washout is the third leg of the index-level capitulation gauge. The conditional, bottom-anchored form does not exist.
- ici_equity_outflow_exhaustion: ICI weekly fund/ETF flow estimates are NOT collected — complete gap.
- finra_margin_deleveraging: FINRA margin statistics are NOT collected — complete gap.
- short_interest_crowded_repair (ticker-level, PIT-panel form): requires multi-vintage PIT panel; current FINRA SI store has exactly one settlement date. short_interest_history.parquet does not yet exist.
- bottom_positioning_reset engine / family: no engine, spine family, synapse entry, or Neural Web artifact for any positioning/flow signal conditioned on bottom entry context.

**Collisions:**
- cot_equity_spec_washout → COT ES net-spec washout already leg 3 of capitulation_score in engine/conditions.py:354-358, tested in capitulation_overlay_phase0 (CONFIRMER). New work is: given a MACD+StochRSI fire, was COT also at washout percentile on that date?
- naaim_exposure_washout_turn → NAAIM live in fear_greed.py, froth_fragility.py, naaim_overlay_phase0 (CONFIRMER verdict on SPY drawdown reduction). The bottom-specific form (washout turn at fire date) is additive and must use a different harness; cannot cite the confirmed SPY result.
- short_interest_crowded_repair → engine/equity_factors.py:445-456 FINRA SI already in cross-sectional factor composite as 'short_interest' (strongest FDR-surviving positive factor). New PIT panel must be a separate file (short_interest_history.parquet) and must NOT change how equity_factors.py reads the current snapshot.
- finra_margin_deleveraging — no collision; complete gap. FINRA publishes monthly debit-balance statistics on finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics — keyless, monthly, ~2-month lag; not in config.yml, not collected.

**Binding laws:**
- R3 (Signal Commons MASTERPLAN_BY_FABLE.md:21): Positioning fusion is illegal as proposed. Legal path: (a) W0 starts PIT accrual for every latest-only ingredient; (b) each ingredient gets its own measured-lead phase-0 once history accrues; (c) survivors become de-escalation/conditioning gates, never a fused escalating score.
- R4 (engine/fear_greed.py header): A leg enters Fear/Greed composite ONLY with >=252 daily / >=104 weekly / >=40 quarterly observations. AAII (22 rows) is structurally excluded.
- R7 (Signal Commons): Everything here lands display-only (is_context_only=true). Promotion only through pre-registered gates.
- FINRA SI PIT warning (engine/equity_factors.py:447-450): any backtest of short_interest_crowded_repair using the current single-snapshot store is illegal.
- Signal Commons W0 mandate: FINRA short interest mandatory for PIT accrual. The short_interest_history.parquet append path is armed but the file does not yet exist.
- NAAIM confirmer ruling (signal_lab.py:593-605): NAAIM registered as 'de-risking confirmer, NOT alpha.' Any contrarian-timing interpretation requires a separate pre-registered phase-0.
- AAII bot-wall expectation (collectors/sentiment.py AaiiAdapter): expected_failure = 'AAII blocks non-browser clients (403).' The 22-row store is the best achievable on the current plan.
- Capitulation overlay confirmer ruling: keep capitulation as a confirmer / display-only attention signal — do NOT promote to an independently scored allocation leg.

**Event counts:** COT equity-index (ES+NASDAQ): ~1,400–1,500 weekly rows per series since 1997/1999. Capitulation gauge: 91 firings / 54 independent clusters over 1993–2026 (60d P(up) 84%). NAAIM: 1,043 weekly rows 2006–2026; ~6–7 independent crisis episodes for honest-N. AAII: 22 rows (too few for any study). FINRA SI: 1 settlement date, 1,499 names. FINRA short volume: 33,806 (date, ticker) rows across ~1,500 names over ~6 weeks. ICI and FINRA margin: 0 rows (not collected).

---

## Ownership/fund-flow reweighting — 13F, VIP holders, crowding (Codex §F7)

The repo has a substantial but display-only 13F stack: engine/smart_money.py (quarterly diff + multi-quarter accumulation trend), engine/manager_quality.py (filing-date-anchored fund skill scores), engine/manager_trades.py (per-trade SPY-excess scorecard), engine/holdings_signals.py (ETF/SPDR weight-decomposition + active ETF signals), engine/crowding.py (fragility flag — price RS × short interest × extension), engine/theme_crowding.py (basket-level comomentum/RS-stretch crowding composite), and engine/beneficial_ownership.py (13D/13G activist-vs-custodial regime). The 13F store is rigorously filing-date-stamped with an explicit available_on contract that prevents quarter-end look-ahead. However, none of these modules is wired into the Neural Web; they are display-only. The ownership percentile history form (Codex §F7: 13f_underowned_reaccumulation) is not implemented — the store tracks holder count and value per quarter but emits no cross-ticker ownership percentile or "low-then-rising" gate. The vip_holder_count_delta and crowding_relief forms also have no implementation. History depth is 6 quarters live (8 on backfill), covering ~18 months.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| engine/smart_money.py — 13F quarterly diff + accumulation trend | engine/smart_money.py | none | FILING-DATE STAMPED. available_on accessor prevents quarter-end look-ahead. 17 curated super-investor funds; ~6 quarters live |
| engine/manager_quality.py — backtested fund skill scores | engine/manager_quality.py | none | Filing-date anchored; completed-window-only. Same 17 funds; minimum 8 events gate; horizon 63d fixed |
| engine/manager_trades.py — per-trade SPY-excess scorecard | engine/manager_trades.py | none | Filing-date entry, completed-window-only, snap-forward guard (SNAP_MAX_DAYS=8d) |
| engine/crowding.py — per-ticker fragility flag | engine/crowding.py | none | Current cross-section only. Short interest has no PIT history. S&P-1500 universe; 252d RS window |
| engine/theme_crowding.py — basket-level comomentum/RS-stretch crowding composite | engine/theme_crowding.py | none | All legs causal/trailing. Short-interest leg excluded from composite (no PIT history). ~15 US thematic baskets |
| engine/holdings_signals.py — ETF weight-decomposition + active ETF signals | engine/holdings_signals.py | none | Latest vs N-day-prior snapshots. 11 sector SPDRs (passive) + curated thematic ETF universe + ARK watchlist (active). US-only |
| engine/beneficial_ownership.py — 13D/13G activist regime per ticker | engine/beneficial_ownership.py | none | Filing-date based (date_filed column). S&P-1500 universe via CIK→ticker join |
| engine/etf_pulse.py — sector RS rotation context | engine/etf_pulse.py | display | Trailing price ratios. 11 SPDR sector ETFs; SPY + major style ETFs |

**Gaps:**
- 13f_underowned_reaccumulation: no cross-ticker ownership percentile history exists. The store has raw holder counts and values per quarter per ticker, but no percentile rank of current ownership vs the name's own history. The 'low-then-rising' conditional gate is entirely absent.
- vip_holder_count_delta: accumulation_trend() outputs holders_delta but does not condition on a prior price drawdown. No post-washout conditioning exists.
- sector_fund_flow_turn: no US-equity sector-level fund-flow series (dollar inflows/outflows to sector SPDRs over time) exists. ICI equity flow data is not collected.
- crowding_relief: no per-ticker or per-basket time-series of crowding state exists. The crowding.py fragility flag is current-snapshot only; no 'crowding receding' state is defined or emitted anywhere.
- NW synapse registration for any ownership/fund-flow form: zero entries in engine/neuralweb/ for smart_money, manager_trades, holdings_signals, beneficial_ownership, or crowding.

**Collisions:**
- strategic_holder_add → engine/smart_money.py accumulation_trend() + diff_snapshots() (partial; MISSING piece is the drawdown conditioning: adds not filtered or flagged by a per-ticker price drawdown of 15–30%)
- activist_13d_after_washout → engine/beneficial_ownership.py computes regime_for() from 13D/13G filings (partial; drawdown conditioning absent)
- crowding_relief → theme_crowding.py basket_crowding() + crowding.py compute_fragility() (no collision risk — existing modules are snapshot-only; the Codex form requires a time-series of crowding state per name/basket)
- sector_fund_flow_turn → holdings_signals.py accumulation_signals() (naming risk only — existing is ETF weight-change signals, not aggregate dollar inflow/outflow; different constructs)

**Binding laws:**
- Filing-date entry is mandatory (engine/smart_money.py:277-284 as_of_for_scoring() doctrine); any F7 forms reaching the spine must carry size_binding=false, is_context=true.
- 13F is CONTEXT only (smart_money.py module docstring: 'CONTEXT only — never imported by any scoring path').
- Neural Web wiring of ownership signals is pending Lane B2 (RUL-16 Amendment 1): 'sponsorship_state (unavailable until B2).'
- Crowding is asymmetric size-down only: theme_crowding.py and crowding.py both state this invariant explicitly. The Codex crowding_relief form is a NEW signal class.
- Short-interest has no PIT history (crowding.py:21-23): any form combining short interest with a historical back-test is currently illegal without a new PIT short-interest history build.
- RUL-13 (Amendment 1): F7 forms are inherently 63/126d horizon — compliant with holdability lane; they do not decide entry verdicts under current doctrine.
- Universe for 13F ticker resolution is S&P-1500 membership.parquet (active tickers only).

**Event counts:** 13F store: 17 funds × ~6 quarters = ~102 quarterly snapshots; ~3,000–8,000 ticker×quarter data points for accumulation_trend. Beneficial ownership: sparse (13D events are rare). ETF holdings signals: flagged accumulation rows typically 20–80 per nightly run. Short-interest: one snapshot; no history count meaningful.

---

## Real-activity/alt-data repair — app reviews, gov contracts, patents, hiring, developer activity (Codex §F8)

Five of the six Codex F8 signal forms (app_demand, gov_contract, patent_cluster, developer_activity via github+HuggingFace) already have live Quiver-backed channels in the Signal Intelligence Desk (engine/altdata_models.py CHANNEL_WEIGHTS, engine/altdata.py collectors, engine/altdata_signals.py kernel). All five channels fire as generic cross-sectional convergence signals — no drawdown-conditional, washout-anchored, or bottom-specific transforms; app_demand fires when rating >= 4.3 AND reviews >= 1000, patent_cluster when patents >= 3 in 120 days, gov_contract_accel when 2x acceleration off a $5M floor — no price-drawdown conditioning is applied anywhere. History depth is the critical constraint: govcontracts Quiver store starts 2026-02-08 (5 months), appratings 2026-06-13 (3 weeks), patents 2026-06-09 (3 weeks), github/HuggingFace 2026-06-20 (2 weeks) — none have the 2+ years of historical fires needed for a phase-0 study. Neural Web wiring is none: no bottom_real_activity_repair family, no synapse entry, no spine registration for any F8 form exists.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| app_demand channel (appratings) | engine/altdata_models.py:103,132-171; collectors/quiver.py:264-268 | none | Time is snapshot timestamp, not event-date. 810 tickers; history 2026-06-13 to 2026-07-04 (3 weeks only) |
| gov_contract / gov_contract_accel channel | engine/altdata_models.py:82-99,417-425; collectors/quiver.py:155-158 | none | action_date from USAGov IS a valid PIT anchor if it precedes the fire. 310 unique tickers; 2026-02-08 to 2026-07-04 (~5 months) |
| patent_cluster channel | engine/altdata_models.py:102,174-200,527-528; collectors/quiver.py:180-183 | none | Patent Date is grant date from USPTO — valid known-date anchor in principle. 385 unique tickers; history 2026-06-09 to 2026-06-30 (3 weeks only) |
| github_momentum channel (developer activity) | engine/altdata.py:527-563; collectors/github_repos.py | none | snapshot_date is collection timestamp. No event-date anchor. 17 unique tickers; 2026-06-20 to 2026-07-05 (2 weeks) |
| hf_model_momentum channel (developer/AI activity) | engine/altdata.py:487-523; collectors/huggingface.py | none | snapshot_date is collection timestamp. 9 unique tickers; 2026-06-20 to 2026-07-05 (2 weeks) |
| hiring / headcount (EDGAR annual 10-K) | collectors/edgar_headcount.py; engine/demand_chain.py:317-366; engine/demand_ledger.py:149 | none | EDGAR filing date used as known-date anchor. HC_BASKETS members only; history depth ~3 10-Ks per name = ~3 years annual datapoints |
| Signal Intelligence Desk L1/L2 architecture | engine/altdata_models.py (L1 deterministic), engine/altdata_brain.py (L2 Opus), engine/altdata_signals.py (kernel aggregation) | display | No unified known-date policy enforced across all channels; full market watchlist + broader scan |

**Gaps:**
- app_demand_reaccel_after_washout: no drawdown-conditional variant of app_ratings_momentum() exists.
- gov_contract_accel_after_washout: no join between govcontracts store and the price/drawdown series.
- patent_cluster_after_washout: patent_cluster fires on grant count alone, no drawdown conditioning.
- hiring_reaccel: per-company live job-posting data is explicitly absent from the repo (edgar_headcount.py:4-7). Quiver has no live job-postings adapter.
- developer_activity_repair (combined form): no GitHub/HuggingFace bottom-conditional transform; repo has star-velocity and download-velocity as generic momentum channels only.
- bottom_real_activity_repair Neural Web family: engine/neuralweb/ has no bottom_sensors.py, no synapse registration, no qual_ladder entry, and no spine_index rows for any F8 signal form.
- Historical fire panel for phase-0: all Quiver-based F8 stores are 2–5 weeks old. None have sufficient history to run a fire-anchored bottom phase-0 study.

**Collisions:**
- F8 gov_contract_accel_after_washout → engine/altdata_models.py gov_contract_accel channel (weight=0.90) + altdata_confirmers.py LEADING set (partial; accel channel exists and is the strongest non-insider channel; Codex form is a conditional transform layered on top. If wired as a new channel, it must be event-cluster-collapsed with existing gov_contract_accel channel per altdata_signals.py:_EVENT_CLUSTER)
- F8 app_demand_reaccel_after_washout → engine/altdata_models.py app_demand channel (weight=0.40) (partial; app_demand channel exists; washout-conditional variant needs to be distinct channel to avoid double-counting in convergence kernel)
- F8 developer_activity_repair → engine/altdata.py github_momentum() + hf_model_momentum() channels (weights 0.30/0.35) (partial; coverage too narrow — 17/9 tickers — for meaningful bottom phase-0)
- F8 hiring_reaccel → collectors/edgar_headcount.py + engine/demand_chain.hiring_read() (near-miss; repo's hiring data is annual EDGAR headcount as coincident display-only; reliable per-company live job-posting feed gap is documented)

**Binding laws:**
- House epistemics: display-only until gauntleted; no LLM-originated signals; nulls printed not hidden. All F8 channels currently DISPLAY in qual_ladder.
- Co-firing / event-cluster law (altdata_signals.py:_EVENT_CLUSTER): channels that fire on the same underlying corporate event collapse to 1 independent observation. Any new bottom-conditional F8 form must declare its event-cluster membership.
- altdata.signal_score is DISPLAY, grandfathered=true in qual_ladder.yml with explicit n_scored>0 gate. No F8 form may influence a scored axis until the gate clears.
- RUL-13 (Amendment 1): primary horizon = 21d. F8 forms have long half-life (Codex §F8: 'better for durable base than weekly-cycle timing') — 63/126d HOLDABILITY lane only, not entry verdict.
- Amendment 1 RUL-15: engine/neuralweb/bottom_sensors.py artifact is NOT yet built. F8 forms cannot be wired into the bottom_sensors.parquet until the Amendment 1 build lands.
- History floor for phase-0: all current Quiver-based F8 stores are 2–5 weeks old — insufficient for fire-anchored historical study.

**Event counts:** app_demand fires: ~810 tickers in current store; estimated 50–150 tickers per nightly run meet lean=='strong'. gov_contract_accel fires: ~310 tickers, accel>=2x subset likely 20–50/day. patent_cluster fires: ~385 tickers, likely 30–80 tickers active. github_momentum fires: 17 tickers total. hf_model_momentum fires: 9 tickers total. Phase-0 event budget: ZERO historical fires available for F8 channels (all stores 2–5 weeks; no historical backfill in repo).

---

## Neural Web integration contract (Codex §6)

The Neural Web integration substrate is fully built (W2–W7b shipped). SpinePrediction is a concrete dataclass at engine/spine.py:140 with role flags derived mechanically from size_binding and direction. The synapse registry (config/synapse.yml, validated by engine/neuralweb/synapse.py) is the mandatory registration gate for every new artifact. The nightly spine-index build (scripts/build_spine_index.py → engine/neuralweb/query.build_index) unions 9 fixed adapters; a new bottom-sensor engine must either emit SpinePrediction rows via engine/spine.emit() or get its own named adapter wired into build_index's adapters list. The kernel batch (scripts/build_kernel_estimates.py → engine/neuralweb/kernel.write_estimates) runs nightly after build_spine_index in dag.yml; cells are display-only until a quarterly FDR sweep passes. engine/neuralweb/bottom_sensors.py is ABSENT — the file specified in Amendment 1 RUL-15 (lane B0) has not been built yet. None of the 8 Codex §6 engine families (bottom_sponsor, bottom_fundamental_repair, bottom_event_hygiene, bottom_macro_release, bottom_positioning_reset, bottom_ownership_reweight, bottom_narrative_repair, bottom_real_activity_repair) appear anywhere in the codebase or synapse registry.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| SpinePrediction dataclass | engine/spine.py:140 | kernel | as_of = decision date; graded via engine.grading next-bar fill. US board, altdata, desk scorer, HK/CA/CN boards, cycles, reflexes, cortex_attention |
| Synapse registry (config/synapse.yml + engine/neuralweb/synapse.py) | engine/neuralweb/synapse.py:49 | spine-context | All shipped NW artifacts registered; no bottom_sensor* or nontech_bottom families present |
| Spine query index build (engine/neuralweb/query.build_index) | engine/neuralweb/query.py:959 | kernel | ~1086 rows at last census (134 altdata_conv, 952 outcome_graded=True); 9 ledger sources |
| Kernel batch (engine/neuralweb/kernel.build_estimates / write_estimates) | engine/neuralweb/kernel.py:295 | kernel | Deep 1962-present signal-engine archive fills __all__ marginal cells. Regime-conditioned cells thin (stamps began 2026-07; FDR clock 2026-10) |
| event_key co-firing collapse mechanics | engine/spine.py:153-157 + engine/neuralweb/kernel.py:41-50 + engine/pooling.py:227 | kernel | All current ledger adapters set size_binding=False; event_key default is symbol:as_of |
| display-only marking mechanics | engine/neuralweb/query.py:169-175 + engine/neuralweb/world_state.py:139 + config/synapse.yml | display | Pattern used by all shipped NW display artifacts |

**Gaps:**
- engine/neuralweb/bottom_sensors.py — ABSENT. Specified in Amendment 1 RUL-15 (lane B0) as the producer of data/neuralweb/bottom_sensors.parquet + site/neuralwebdata/bottom_sensors.json. Schema v1 is fully specified in the Amendment (21 fields including symbol, as_of, region, trigger_tier, coiled, star, coiled_fire, donor_state, dist_21d_low_pct, dist_126d_high_pct, entry_quality_band, earnings_next_date, sponsorship_state, bottom_state, overlay_flags).
- config/synapse.yml entry for bottom_sensors artifact — ABSENT. Required before merge per sentinel law and CI (check_synapse_registry).
- config/dag.yml step for build_bottom_sensors — ABSENT. Must be added to the nightly band AFTER library builds with a <=+30s budget constraint. Companion site/qa_bottom_sensors.html builder step also absent.
- Spine emitters for all 8 Codex §6 families — ABSENT. No SpinePrediction rows with engine in {bottom_sponsor, bottom_fundamental_repair, bottom_event_hygiene, bottom_macro_release, bottom_positioning_reset, bottom_ownership_reweight, bottom_narrative_repair, bottom_real_activity_repair} exist anywhere in the codebase.
- synapse.yml entries for esx_sponsorship family (Amendment 1 RUL-16, lane B2) — ABSENT. Pre-registered budget=8 cells declared in the Amendment but no registry entry exists.
- adapt_confluence_fires spine adapter — ABSENT from query.build_index adapters list. Masterplan §7 specifies this adapter (historical tier fires as engine='confluence_gate', family='confluence:T{n}').
- site/qa_bottom_sensors.html — ABSENT. Amendment 1 specifies this as the first display surface (reachable by URL, no nav changes, bilingual EN/ZH, data-tip-en/zh popovers, zero 'validated' wording).

**Collisions:**
- §6 bottom_event_hygiene (earnings_blackout veto) → Entry Stack Expansion W1-SEV already running family 'esx_ev_blackout' (Amendment 1 §B table: 'ALREADY IN FLIGHT'). The nontech_bottom program MUST NOT register a competing earnings_blackout family.
- §6 bottom_macro_release / stress_peak_turn → engine/market_state.py and risk radar already compute credit/liquidity stress composites. Nontech program must control for existing market_state/risk_radar_state in every bottom_macro_release stratum test.
- §6 bottom_positioning_reset / AAII / NAAIM → sentiment_engine (~75% built) covers AAII/NAAIM. Nontech program must use bottom-specific transforms and avoid duplicating the sentiment engine's existing ledger.
- §6 bottom_fundamental_repair / quality_floor (Piotroski/Altman/Sloan) → engine/stock_fundamentals.py already computes these quality scores. Program should BIND these outputs read-only.
- §6 bottom_ownership_reweight / 13F underowned reaccumulation → engine/altdata_models.py and altdata_signals.py already handle institutional flow signals. Nontech program needs filing-date PIT discipline that may not exist in the current altdata path.
- §6 bottom_real_activity_repair / gov_contract_accel_after_washout → Quiver-derived feeds for contracts/grants already activated into Signal Intelligence Desk; existing feed, but no bottom-specific 'reaccel after washout' transform.

**Binding laws:**
- RUL-15 (Amendment 1): bottom_sensors.py produces ONLY two new rolling columns (dist_21d_low_pct, dist_126d_high_pct); all other fields BIND from existing engine outputs read-only.
- RUL-11 (Masterplan): no fire testifies twice — FDR sweeps and confluence edges must exclude backfill-v1 rows whose fire-set already produced a phase-0 verdict.
- §7.6 event-budget doctrine (Masterplan §7 item 6): sensors compete for a fixed graded-event budget; a candidate whose expected fire rate cannot reach MIN_FAMILY_N per (regime×horizon) cell within 2 quarters must justify at coarser cell granularity or not ship a kernel lane at all.
- MIN_FAMILY_N=12 / WILSON_MIN_N=12 (engine/pooling.py:67 + kernel.py:136): hard floors before Wilson CI is computed and before arming() can return True.
- Quarterly FDR batch (kernel.py docstring): nothing consumes shrunken_ic to change allocation, alert severity, or board ordering until the quarterly PR2 FDR sweep passes. FDR clock: 2026-10.
- Display-first law (Amendment 1 RUL-15): bottom_sensors.parquet is synapse-registered with is_display_only:true; zero ranking authority until any label earns its own pre-registered family verdict.
- Sentinel staging law (Masterplan §8.4): every new store must be git-added AND appended to the sentinel's staging list in the same PR.
- No master score / hand weights: banned by house law and Codex paper §0 and §9.
- Event_key co-firing collapse: co-firing bottom-sensor channels on the same fire date must share event_key='TICKER:YYYY-MM-DD:bottom_context' so they count as one observation per horizon cell, not 8 independent observations.

**Event counts:** Codex §5.3 promotion bar: n_eff >= 12 per marginal cell. Given rare bottom-sensor fire rates (insider clusters, activist events), per-regime cells will require many quarters to arm. Masterplan §7 note: U&R fires ~10x rarer than gate fires; the plan accepts slow accrual and does NOT manufacture pseudo-events. §7.6 forces coarser engine×horizon cells if regime cells cannot reach MIN_FAMILY_N=12 within 2 quarters.

---

## Technical fire tape + phase-0 study harness (Entry-Stack Expansion W0 anchor)

The W0 fire tape and study harness are fully implemented and frozen. Two fire-tape parquets live in git at data/research/ (deep: 38,250 fires, 220 tickers, 1962–2026; baskets: 113,542 fires, 2,495 tickers, 2014–2026). Both have an 8-column schema: ticker, date, tier (T1/T2/T3), sub (deep/shallow), ticks (0-2), not_topped (all True), eligible (all True), panel. COILED and entry_quality_band are deferred columns documented in W0_BASELINES.md. The study harness at scripts/research/entry_strata_phase0.py implements grade_fires() (T+1 fill, stop5 via fwd_mdd_5, mae63, mfe63, rotational/positional terminal states, days_to_10), r1_estimate() (date-FE demeaned OLS, block-bootstrap 95% CI, BH FDR q<=0.10, fe_granularity frozen per RUL-12), effect_table() over 7 outcomes, era_table(), and compute_recall(). Primary endpoints post-RUL-13 are stop5 + mae21 (mae21 is RUL-13 ratified but not yet a column in EFFECT_OUTCOMES — still mae63 in the shipped harness). The W1-STS template (scripts/research/run_w1_sts.py + research/entry_stack/W1_STS_REPORT.md) is the canonical model for adding a context column.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| Fire tape — deep panel | data/research/gate_fires_deep.parquet | none | Snapshot as of 2026-07-02. US large-cap survivor universe (~224 names). History depth varies: oldest names go to ~1962, median ~11,668 bars |
| Fire tape — baskets panel | data/research/gate_fires_baskets.parquet | none | Same snapshot discipline. Full basket universe ~2,519 names. History only from ~2014 |
| Study harness core — entry_strata_phase0.py | scripts/research/entry_strata_phase0.py | none | No PIT enforcement needed (tape is already PIT-clean at build time). T+1 fill avoids look-ahead. Handles both deep and baskets panels |
| W0 baseline report | research/entry_stack/W0_BASELINES.md | none | Numbers confirmed exact by W0 opus reviewer; ±3-fire boundary noise documented. 2012–2026 program eras only |
| W1-STS runner + report (template for context columns) | scripts/research/run_w1_sts.py; research/entry_stack/W1_STS_REPORT.md | none | Strictly prior bars for all lookbacks. Both panels. VIX loaded from data/fred/VIXCLS.parquet |
| Trial ledger + family registration | data/trial_ledger.jsonl (runtime artifact), engine/trial_ledger.py | none | 8 families registered at W0. esx_sponsorship (Amendment 1 RUL-16) not yet added |

**Gaps:**
- mae21 as co-primary endpoint in effect_table EFFECT_OUTCOMES list — RUL-13 ratified mae21 supersedes mae63 as hygiene co-primary but EFFECT_OUTCOMES tuple (entry_strata_phase0.py:749-758) still lists mae63 only; fwd_mdd_21 is computed in grade_fires() but not surfaced in effect_table(). W1 studies are grandfathered but W2+ must use mae21.
- zone_held_21 and stop_vol_21 (RUL-14 vol-scaled entry zone co-primary metrics) — not implemented anywhere. Queue behind the W1 harness fix (PR #1408) merging.
- esx_sponsorship family (budget=8, RUL-16) not added to FAMILY_BUDGETS dict in entry_strata_phase0.py — ratified in Amendment 1 but not back-ported to harness code.
- COILED flag column in fire tape — deferred to S-UR study PR. No per-fire COILED computation exists.
- entry_quality_band (NC-2) column in fire tape — deferred. Hook exists in r1_estimate(entry_quality_bands=True) but no batch-computed lookup table per ticker×year-quarter has been built.
- region field absent from fire tape — US only; Amendment 1 §E explicitly states 'No HK/CA' for this program.
- S7/cohort fields absent from fire tape — owned by program #1097/#1207 and Entry Intelligence #1302; stamped unavailable pending those programs' W0.4 series.

**Collisions:**
- Codex proposal 'Production-trigger trio ablation' (state-label arms) → Entry Intelligence #1302 P1_3_TRIO_ABLATION_PREREG owns this pre-registration. The entry-stack harness does NOT build this. Coordination boundary: Amendment 1 §B forwards a recommendation to #1302 but does not execute their prereg.
- Codex proposal 'Within-cohort RS repair' as a species → S7 (#1097/#1207) and Entry Intelligence #1302 W0.4 own the within-cohort RS-rank series.
- Vol-regime overlay as a context column → VIX regime band already implemented in run_w1_sts.py as a FREE CONTEXT COLUMN (no inference). Vol-regime overlay previously FAILED additive-value vs vol-target test (masterplan §3/§2); any attempt to register it as a candidate family conflicts with the existing falsification ruling.
- Codex proposal 'ADX-positive-filter' → W1-STS study ran ADX-rising as an expect-null (esx_ts_adx): NULL on deep panel, adverse-sign POSSIBLE NON-NULL on baskets (CHIP path foreclosed per §5 — adverse sign + <2pp magnitude). The question is CLOSED.

**Binding laws:**
- RUL-7: Promotion thresholds frozen at W0. CHIP floor: stop5 FE-coef >= 2pp, block-bootstrap 95% CI excluding 0, BH q<=0.10, sign-stable 3/4 eras, beats both NCs, MFE/|MAE| conjunctive.
- RUL-9: One grader (engine/grading.py barriers: rot liftoff 1.08/21d, pos liftoff 1.15/126d, stop 0.95, cushion 1.05). All studies use this grader; no recomputation with different barriers.
- RUL-12: FE granularity frozen once per family at W0 sign-off. Post-hoc switching banned. Both panels frozen at 'date' FE with sector fallback for baskets.
- RUL-13 (Amendment 1): Primary horizon = 21 trading days. mae21 supersedes mae63 as hygiene co-primary from W2 onward. 63d/126d metrics are holdability lane only.
- RUL-14 (Amendment 1): zone_held_21 and stop_vol_21 are co-primary metrics alongside stop5 from W2 onward. Implementation queues behind W1 harness fix (PR #1408).
- RUL-5: Expect-null protocol — non-null requires pooled FE coefficient with BH-adjusted CI excluding 0. Single-era excursions are noise by pre-registration.
- RUL-3: NC-2 (entry_quality band FE) marginality test required for every promoted stratum.
- RUL-1: Generic oscillators (OBV, CMF, RVOL, ADX as positive filter, KST, Fib/Elliott) REJECTED.
- Total declared trial budget frozen at 115 (per RUL-7 freeze). Adding new families requires amendment + new RUL-7 ruling. esx_sponsorship (budget=8) is ratified but not yet in code, leaving ~0 headroom before an amendment.

**Event counts:** deep panel: 38,250 total fires / 37,722 gradable. Baskets panel: 113,542 total fires / 107,127 gradable. Deep panel era breakdown (T1 only): 2012-2015: 3,384 / 2016-2019: 3,363 / 2020-2022: 2,644 / 2023-2026: 2,727.

---

## Doctrine, prior nulls, and graveyard — what LAW binds the non-technical durable-bottom program

The NON_TECH_DURABLE_BOTTOM_SIGNALS_FOR_FABLE.md proposal is fully downstream of the ratified durable-bottom framework (DURABLE_BOTTOM_FRAMEWORK.md), the Entry-Stack Expansion Masterplan (ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md), Amendment 1 (RUL-13..17), and Signal Commons rulings (R1-R8). The metric constitution (clean-liftoff, stop-out, dead-money, recall, trap-fire) is locked. The graveyard includes: volume confirmation as a positive filter (H4 falsified), trend/location guards (exposure artifact), calm-base arming (H2 wrong sign), SUE collapsed on deep PIT history (IC 0.039→0.0006), narrative momentum rank-IC≈0 (family retired), sentiment/text-uncertainty redundant-or-worse-than-VIX (EPU/GPR incremental IC -0.064 to -0.129 FDR-reject), insider long-only tilt borderline DSR (0.82–0.85, fails L/S), RS-repair vs market null/mildly worse (S7: wrong sign), triple-lock hard conjunction amputates recall. Non-technical context families that are not new independent triggers ride as CHIP/STRATUM lanes inside the Entry-Stack Expansion program — they do NOT require Setup Species registration (#1097). Positioning fusion is ILLEGAL under Signal Commons R3. Horizon doctrine RUL-13 makes 21d the primary endpoint.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| Metric constitution (clean-liftoff, stop-out, dead-money, trap-fire, recall) | research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md:156-176 | none | US deep 223-name panel + basket 2519-name panel; CN wave-3 replication |
| Entry-Stack Expansion RUL-1..12 rulings | research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md:270-281 | none | US primary; HK/CA excluded by default |
| Amendment 1 RUL-13..17 | research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md:1-119 | none | amends ESX masterplan in-place; in-flight W1 grandfathered |
| Signal Commons positioning-fusion prohibition (R3) + PIT-tape law | research/SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md:21 (R3), :14 | none | all positioning-related signal families repo-wide |
| Durable-bottom graveyard ledger (falsified hypotheses H1-H6, W2-W8) | research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md:318-611 (§8 ledger) | none | US 223-name deep panel + 2519-name basket panel; CN (W3 PASS), HK (W3 FAIL), CA (W8 KILL) |
| Species registry and deployment-lane doctrine | research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md:70 (deployment lanes) | none | all programs consuming engine/species_registry.py APIs |
| Event-budget doctrine for NW kernel lanes (§7.6 / NW MIN_FAMILY_N) | research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md:234 (§7.6) | none | all NW kernel lanes across all programs |
| SUE collapse on deep PIT history | research/INTELLIGENCE_HUB_V2_RESEARCH.md:141 | display | US deep panel and EDGAR fundamentals_panel.parquet |
| Narrative/text uncertainty index kill | research/NEWS_FEED_PROBLEM_AUDIT_FOR_FABLE.md:19, :126; engine/narrative_regime.py:130-131 | display | 1990-2026; macro-level, not per-ticker |
| Insider long-only tilt borderline DSR verdict | research/INTELLIGENCE_HUB_V2_RESEARCH.md:124 | display | SEC Form 4 open-market purchases; collectors/sec_insider.py |
| RS repair vs market null (S7 phase-0) | research/species/s7_rs_repair_phase0/REPORT.md:1-15 | none | massive store 20,177 tickers 2021-07→2026-07; deep panel 224 names |
| Triple-lock recall amputation (S7) | research/species/s7_rs_repair_phase0/REPORT.md:16-17, :87-138 | none | structural falsification |

**Gaps:**
- Species registration question for non-trigger context families: SETUP_SPECIES_MASTERPLAN_BY_FABLE.md has no explicit ruling on whether NON-TECHNICAL context families need Setup Species registration or ride as CHIP/STRATUM lanes. This is an open doctrinal gap requiring Fable adjudication.
- Horizon doctrine for non-technical families: no ruling clarifies whether non-technical CONTEXT families that only claim holdability benefit must clear the 21d primary first, or whether they can go directly to the holdability lane.
- PIT ruling for F6 (positioning/flow/AAII/NAAIM/COT/ICI): no explicit policy exists for these specific feeds in the non-technical program context for use as context stratifiers once they have a tape.
- Definitional scope of 'non-technical': no ruling defines what counts as 'non-technical' vs 'technical.' VIX/MOVE/OFR FSI proposed in NON_TECH F5 are borderline — partly covered by existing risk_radar/market_state ecosystem.

**Collisions:**
- F4 Earnings-blackout veto (NON_TECH §3 F4) → S-EV (ESX W1-SEV, family esx_ev_blackout, in-flight study) — EXACT DUPLICATE. NON_TECH must consume S-EV's verdict when it lands.
- F3 SUE/guidance/revision and quality_floor → ESX S-QL (W2 study) + engine/sue.py (display-only post-collapse) + engine/stock_fundamentals.py — SUBSTANTIAL OVERLAP. NON_TECH F3 covers the same ground as ESX S-QL. NON_TECH must reference ESX S-QL outcome when it runs (W2) and not run a parallel study.
- F5 Macro/credit stress release (OFR FSI, MOVE, VIX-rates, NFCI) → ESX Amendment 1 RUL-16 esx_sponsorship (B2 lane); existing macro risk regime (conditions.py, risk_radar, regime_vector) — PARTIAL COLLISION. NON_TECH must control for existing VIX/market_state in any F5 study.
- F7 Ownership/fund-flow reweighting (13F underowned, vip_holder_count_delta) → engine/smart_money.py; Signal Commons R3 positioning fusion illegal — PARTIAL COLLISION. Positioning-fusion prohibition applies to the family as a composite; individual legs may proceed as separate CHIP/STRATUM lanes.
- F9 Narrative neglect/panic (bad_news_peak_decay, narrative_resolution, theme_neglect_reversal) → EPU/GPR kill (gate_status:pinned_off, engine/narrative_regime.py:130-131); narrative_rotation.py rank-IC≈0 (family retired) — HARD COLLISION. This family cannot be built without first proving ticker-level incremental value; entire family is hostile-adjacent and requires a pre-registered expect-null study.

**Binding laws:**
- RUL-1 (ESX): Volume-confirmation confirmers are DEAD (H4). No family may include OBV-div, up/down ratio, dry-up, or cap-spike as positive filters.
- RUL-4 (ESX): Only S-EV (earnings blackout) is permitted to target a hard gate; all other non-technical families are CHIP/STRATUM/KERNEL only.
- RUL-5 (ESX): Trigger SPECIES register before first compute. Non-trigger context families ride as CHIP/STRATUM and do not require #1097 species registration.
- RUL-13 (Amendment 1): Primary horizon = 21d. 63/126d = holdability lane only, never entry verdict.
- RUL-14 (Amendment 1): Vol-scaled entry zone is co-primary beside stop5 from W2 onward.
- RUL-15 (Amendment 1): bottom_sensors.parquet is BIND-first — never recompute a field that an existing engine already emits.
- RUL-17/5 (Amendment 1): NON_TECH work rides INSIDE Entry-Stack Expansion; a parallel program would double-account fires and species.
- Signal Commons R3: Positioning fusion is ILLEGAL as an escalating composite. Legal path: PIT accrual → per-ingredient measured-lead phase-0 → survivors become de-escalation/conditioning gates.
- Signal Commons R7: Everything lands display-only. Promotion only through pre-registered gates. Nightly is sole ledger advancer.
- Framework law: Recall must be printed beside precision. Hard gates reserved for hygiene only (S-EV).
- PIT tape law: any positioning/sentiment ingredient with no historical PIT tape cannot be backtested or scored.
- PIT law (EDGAR fundamentals): asof_date in eps_quarterly.parquet and fundamentals_panel.parquet is SYNTHETIC (period_end+60d constant, std=0). Not a real filing date.
- Graveyard law: Already falsified stays falsified. Re-derivation of a graveyard idea = automatic wave failure.
- HK/CA excluded by default: every US bottom mechanism tested so far inverts or fails in HK/CA (W3 HK gate failed, W8 CA KILL).

**Event counts:** Non-technical events are rare relative to gate fires. Insider cluster events (>=2 buyers in 45d after 15–30% drawdown): estimated single-digits to low-double-digits per year per name for liquid small/mid cap; possibly 1–3 per year for large cap. Activist 13D campaigns: <1 per name per year on average. These rates are orders of magnitude below the gate-fire rate (~165 fires/name/45y on deep panel = ~3.7/year/name). MIN_FAMILY_N=12 per (regime×horizon) cell will take years to arm for rare non-technical sensors.

---

## LLM/text extraction infrastructure + narrative repair (Codex §F9 + §6.4)

The repo has a well-articulated LLM extraction stack with six distinct brain/extraction modules, a shared provider waterfall (llm_auth.py), and a qual_ladder promotion registry. Every LLM consumer enforces de-escalation-only via a code-level _reconcile clamp; the constraint lives in narrative_brain.py:217-226 and altdata_brain.py:269-279. The narrative-regime finding (text uncertainty redundant/worse over VIX for forward vol) is formally retired in engine/narrative_regime.py with _FAMILY_RETIRED=True and documented in two phase-0 reports (Gate A + D7 salvage). Per-ticker news infrastructure exists but is shallow and snapshot-only: Polygon news_sentiment.parquet covers 126 tickers, 2026-06-21 to 2026-07-05 (14 days), and intel_hub/news_counts.jsonl holds 50 rows over 14 dates starting 2026-06-21. There is no multi-year per-ticker news volume/tone time series. The GDELT macro-narrative event store (news_vector/events.parquet) is 60 rows, 2026-06-15 to 2026-06-20, no ticker column, macro themes only. For bad_news_peak_decay: the per-ticker article-count history needed to compute a decay slope does not exist — what exists is an append-only daily count ledger 14 days deep, a single-snapshot bull_ratio from Polygon, and a macro-theme bucket velocity with no ticker scope.

| Component | Path | NW wiring | PIT / coverage |
|---|---|---|---|
| engine/llm_auth.py — shared LLM provider waterfall | engine/llm_auth.py | none | Infrastructure only; all active LLM modules share this |
| engine/news_llm.py — headline batch summarizer + importance re-rank | engine/news_llm.py | none | Market-level financial/macro headlines. No per-ticker history. No tone time series |
| engine/narrative_brain.py — theme durability + rotation LLM desk | engine/narrative_brain.py | display | Theme/basket-level, not per-ticker. US baskets from radar.json. No history depth for ticker-level tone |
| engine/altdata_brain.py — Signal Intelligence Desk LLM analyst | engine/altdata_brain.py | spine-context | Per-ticker, US-focused. ~top-N names with altdata coverage. No multi-year news tone history |
| engine/qual_extraction.py — citation-verified structured 8-K extraction | engine/qual_extraction.py | none | Source_id = sha256(body). filed/as-of date basis documented. US 8-K filings only |
| engine/catalyst_tone.py — FOMC/dislocation document digest (Tier A) | engine/catalyst_tone.py | none | Public FOMC statements/minutes, regulatory releases. NOT per-ticker. Macro/regime scope only |
| engine/foresight_analyst.py — LLM reasoning over convergence board | engine/foresight_analyst.py | display | Theme/basket-level convergence. No per-ticker news tone scope |
| engine/glut_watch.py — LLM language leg (leg6 in glut composite) | engine/glut_watch.py:121-188 | display | Sector-level, US only. NAICS-mapped EDGAR capacity-adds language. PIT-clean on filing dates |
| engine/narrative_regime.py — Narrative-Dominance Index (RETIRED) | engine/narrative_regime.py:46-53 | display | EPU/GPR/SFED market-level macro-narrative uncertainty. 1990–2026. No per-ticker scope. _FAMILY_RETIRED=True |
| engine/news_vector.py — GDELT PIT narrative event bus | engine/news_vector.py | none | first_seen_utc is keep-FIRST. Macro-narrative scope only (NOT per-ticker). ~5-day effective history in artifact |
| engine/intel_hub.py news_counts.jsonl — per-ticker daily news velocity ledger | engine/intel_hub.py:160-201 + data/intel_hub/news_counts.jsonl | none | Counts are deterministic. ~all US tickers with news coverage. 14-day history only |
| engine/altdata.py news_sentiment_signals() + data/polygon/news_sentiment.parquet | engine/altdata.py:454-482 + data/polygon/news_sentiment.parquet | none | snapshot_date is collection date. 126 tickers only (Polygon STANDARD tiered). 14-day history. Bull_ratio only |
| engine/provenance_sidecar.py — Committee View sourcing infrastructure | engine/provenance_sidecar.py | display | Binds spine rows by as_of date. US-only v1; sources: altdata, radar, us_board, sector_central, oracle, fundamentals |
| reports/narrative-regime-phase0.md + reports/narrative-realign-phase0.md | reports/narrative-regime-phase0.md + reports/narrative-realign-phase0.md | none | 1990–2026 (Gate A); 1999–2026 (D7). Macro-level, not per-ticker |
| config/qual_ladder.yml — LLM field promotion registry | config/qual_ladder.yml:1-530+ | none | All LLM/text fields. No bottom-narrative repair family exists yet |

**Gaps:**
- Per-ticker news volume time series (history >= 1 year) needed for bad_news_peak_decay slope computation. The intel_hub/news_counts.jsonl ledger is 14 days deep; Polygon news_sentiment.parquet is 14 days deep on 126 tickers.
- Per-ticker tone z-score baseline (rolling percentile of article tone vs own history). The existing bull_ratio from Polygon is a snapshot, not a time-series with enough history to compute extreme-percentile events.
- Ticker-resolved news event store. The news_vector/events.parquet has no ticker column. A bad_news_peak_decay sensor requires a ticker-tagged event store with headline tone per ticker per day, appended and kept-first PIT.
- bad_news_peak_decay sensor engine (engine/bottom_narrative_repair.py or equivalent) — no engine file, no synapse entry, no spine emission for ticker-level narrative repair signals.
- Decay slope detector: computing the 'news volume decays while price stabilizes' pattern requires a rolling decay function on ticker-level counts and tone — not present anywhere in the repo.
- Narrative resolution classifier: the 'litigation/regulation/supply-chain topic shifts from uncertainty to resolved' form has no deterministic extractor or LLM-based topic-transition classifier at the ticker level.
- social_panic_capitulation sensor: no social/retail mention volume feed at the ticker level (no Reddit/Twitter/StockTwits collector in the pipeline).
- theme_neglect_reversal sensor: per-ticker 'coverage falls to low percentile then real sponsor appears' join is not built.
- qual_ladder entry for bottom_narrative_repair family: a new SHADOW entry would be required before any claim can accrue qledger evidence.

**Collisions:**
- F9 bad_news_peak_decay → intel_hub news_counts.jsonl (14 days, counts only, no tone) + Polygon news_sentiment.parquet (14 days, 126 tickers) (existing infrastructure is ~5% of what bad_news_peak_decay needs; a new collector is required)
- F9 narrative_resolution → qual_extraction.py reversibility field (partial overlap: captures single-filing reversibility but not multi-event topic trajectory; not a duplicate but a reusable building block)
- §6.3 citation/provenance sidecar → engine/provenance_sidecar.py + qual_extraction.py evidence[{field, quote_span}] + catalyst_tone evidence (strong reuse opportunity: verbatim quote_span anti-hallucination pattern is directly applicable; no conflict — additive)
- F9 LLM may classify text and extract cited events (§6.4) → narrative_brain.py _reconcile() + altdata_brain.py _reconcile() + glut_watch.py anti-laundering demotion (de-escalation-only law already enforced in three modules; new bottom_narrative_repair LLM classifier must add a fourth _reconcile clamp)
- F9 theme_neglect_reversal → engine/narrative_rotation.py resid_mom + engine/news_flow.py macro-theme velocity (news_flow.py computes 7d GDELT velocity per basket — correct ancestor but basket-level not ticker-level; beware: narrative_rotation resid_mom was falsified, IC~0)

**Binding laws:**
- De-escalation-only for LLMs (HOUSE LAW, code-enforced): LLMs may classify and de-escalate calibrated keys; they may never originate signals, scores, or escalations. Enforced via _reconcile() in narrative_brain.py:217-226 and altdata_brain.py:269-279, and via anti-laundering demotion in glut_watch.py:121-188. Any new F9 engine must add a matching clamp.
- Narrative-regime family RETIRED (D7, 2026-07-02): EPU+GPR text-uncertainty and SFED sentiment residual are both falsified. engine/narrative_regime.py _FAMILY_RETIRED=True, gate_multiplier=1.0 permanently. The ticker-level bad_news_peak_decay hypothesis is orthogonal (different conditioning) but researcher must not cite the existing NDI display banner as prior support.
- Display-first doctrine: no LLM signal may influence ranking, gating, or allocation until it clears the qual_ladder §3 confirmer gate (n_dates>=25, wilson_ci_low>0 vs matched control, incremental over price+VIX, block-bootstrap stable). All new F9 fields start at SHADOW.
- qual_ladder.yml must be updated before any LLM field is rendered or accrues qledger evidence. Linter at scripts/check_extraction_drift.py and CI enforce the registry.
- LLM may not treat uncited claims as source events (§6.4 rule): every field extracted from text must be backed by a verbatim quote_span verified by _verify_citations() or equivalent. Existing qual_extraction.py and catalyst_tone.py machinery implement this and must be reused, not reimplemented.
- Neural Web kernel-FDR clock (2026-10): no kernel conditioning before October 2026 FDR batch. Any F9 spine rows emitted before then are display-only.
- narrative_rotation resid_mom is falsified (IC~0); it must not be used as a prior for theme_neglect_reversal or any narrative direction signal.

**Event counts:** intel_hub/news_counts.jsonl: 50 rows across 14 dates, 2026-06-21 to 2026-07-05 (counts only, no tone). Polygon news_sentiment.parquet: 1,554 rows, 126 tickers, 14 dates. news_vector/events.parquet: 60 macro-narrative events, 2026-06-15 to 2026-06-20 (macro themes, no ticker). All counts are 2026-only; no multi-year per-ticker news tone history exists.

---

## Cross-lane readout

1. The signals exist; the fire-anchored conditioning layer and the NW conversion layer do not — no lane is wired into Neural Web (zero synapse entries for any bottom_* or nontech family; engine/neuralweb/bottom_sensors.py not yet built).

2. Most-built lanes: insider (2.31M-row PIT Form-4 panel + completed factor program), event-risk (esx_ev_blackout anchor store built, study in flight), macro stress (all series collected, consumed by conditions.py/risk_radar).

3. Zero-history lanes: all Quiver F8 stores 2wk–5mo deep; per-ticker news tone 14 days; AAII 22 rows; FINRA short interest 1 vintage; ICI + FINRA margin not collected.

4. Known bugs to fix during builds: engine/equity_factors.py insider flat-file dead-path (silent cluster=False fallback on fresh worktrees); esx_sponsorship ratified in RUL-16 but absent from FAMILY_BUDGETS; mae21 absent from EFFECT_OUTCOMES.

5. Stale-paper corrections: SUE deep-PIT null is binding (paper calls SUE "one of the strongest candidates"); positioning fusion is illegal (Signal Commons R3); earnings blackout already in flight; synthetic eps asof_date void as a PIT anchor.

---

## Post-census delta (same-day, 2026-07-05 afternoon — main moved during the census)

Three census facts went stale within hours; the census text above is preserved as the point-in-time record:

1. **W1-SEV landed** (#1432, `research/entry_stack/W1_SEV_REPORT.md`): hygiene evidence PRESENT — vetoed fires degrade stop5 by +8.7pp (CI [+7.9, +9.9] excluding 0), veto volume 6.0% ≤10% cap. Reviewer sign-off + W1.5 wiring pending in the ESX lane.
2. **RUL-14 columns are wired**: zone_held_21/stop_vol_21 are in `EFFECT_OUTCOMES` and the BH panel on main (post-#1408 chain). `mae21` remains the one missing RUL-13 co-primary (`fwd_mdd_21` computed in grade_fires, never surfaced).
3. **Lane B0 is in flight**: `engine/neuralweb/bottom_sensors.py` is being built in open PR #1437; the QA page in #1436.
