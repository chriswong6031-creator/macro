"""International bridge — the pre-registered CLAIM grid + the already-run evidence.

This module is PURE DATA (no computation): the declarative substrate the
``scripts/intl_phase0.py`` harness composes over, kept separate from the harness
logic so the C1–C8 channel book (masterplan §5) and the backfill evidence can be
imported, tested and audited on their own.

Two payloads:

* ``CLAIMS`` — the pre-registered claim grid. Each CLAIM is one channel × direction ×
  target × horizon(s), declared here as data (never invented at scan time). The harness
  logs the FULL grid into the ``intl_bridge`` trial-ledger family AT GENERATION
  (``--declare``), so the Deflated-Sharpe multiple-testing haircut deflates by the honest
  count — the forex declared-N=60 discipline, ported. A claim carries:
      id                snake_case unique key (also the ledger config identity)
      channel           "C1".."C8" (masterplan §5)
      hypothesis        one-line mechanism the claim asserts
      direction         'de-risk' | 'add-tilt' — de-risk legs strictly dominate (§4.1)
      target            the benchmark whose forward drawdown/return the claim predicts
      horizons          pre-registered forward windows (business days); NO post-hoc pick
      source_series     [(group, series)] on-disk parquets the causal signal reads
      freshness_sla_days per the fail-closed freshness gate (§4.2 gate 6)
      builder           the name of the causal signal builder in intl_phase0 (or None if
                        the builder is not yet implemented — the claim still DECLARES, so
                        the trial budget is spent honestly, and grades PENDING).
      notes             pre-registration provenance / prior evidence pointer.

* ``BACKFILL`` — the ledger rows encoding evidence already run (3 phase-0 reports, the
  forex calibration, the lead-lag screen, the risk_radar_intl validation), so the registry
  starts TRUTHFUL rather than empty. Each row's ``validation_ref`` quotes the exact report
  path; ``verdict`` follows the calibrate_forex grammar; ``weight_cap`` follows the
  three-state policy (§4.1). These are the SAME schema the harness emits, so the backfill
  and a fresh scan merge into one ``data/intl_bridge/ledger.json``.

House rules: pure stdlib, keyless, no scipy/sklearn. Nothing here touches the scoring core.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# The pre-registered claim grid (masterplan §5 channel book). Declared as data
# so `intl_phase0 --declare` logs the WHOLE grid before any scan runs.
# --------------------------------------------------------------------------- #
FAMILY = "intl_bridge"

# Pre-registered forward horizons per direction class. De-risk claims predict a
# forward DRAWDOWN at the drawdown-relevant windows; add-tilt claims predict a
# forward RETURN. Fixed here, never re-chosen at scan time.
_DD_HORIZONS = (21, 42)
_TILT_HORIZONS = (21, 63)

CLAIMS: list[dict] = [
    # -- C1 · Global-beta size-dampener (the v1 flagship) ------------------
    {
        "id": "c1_china_global_beta",
        "channel": "C1",
        "hypothesis": "High global-beta China names get size/stop dampening when the "
                      "global risk state deteriorates (port of hk_global_beta, Vasicek-shrunk).",
        "direction": "de-risk",
        "target": ("yahoo", "FXI"),
        "horizons": _DD_HORIZONS,
        # SPY is the HK-convention global-risk factor (hk_global_beta uses SPY, overnight-
        # lagged); _GSPC on disk lags ~20d and would trip the fail-closed freshness gate.
        "source_series": [("yahoo", "FXI"), ("yahoo", "SPY")],
        "freshness_sla_days": 5,
        "builder": "scripts.c1_cn_global_beta.builder",   # measured in W2 (C1)
        "notes": "HK validated ~2x transmission; China A couples less (~2x ratio, "
                 "china_global_factors) — measure, don't assume. Gate: incremental over CN RORO. "
                 "Seam (post-promotion): china_name_score._tailwind + conviction_profile ctx.",
    },
    # -- C2 · MRS intl macro-sleeve leg (the cheapest honest wire) ---------
    {
        "id": "c2_intl_macro_sleeve",
        "channel": "C2",
        "hypothesis": "Pooled intl macro de-risk sleeve (curve-inv + Sahm + short-tightening "
                      "across JP/EZ/GB, ≥2 legs firing) leads US/CN equity drawdowns.",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        "source_series": [("intl_macro", "JP_yield_10y"), ("intl_macro", "JP_short_3m"),
                          ("intl_macro", "de_10y"), ("intl_macro", "GB_yield_10y")],
        # monthly macro + ~1m publication lag: a freshly-collected monthly print is
        # ~35d old, and OECD/FRED monthly short/curve series routinely lag a full
        # quarter before the next observation lands. 120d = ~2 monthly cadences with
        # lag — tight enough to catch a DEAD series (years stale, e.g. the retired CPI
        # ids) but not so tight it fails-closed on a live-but-quarterly-lagged print.
        "freshness_sla_days": 120,
        "builder": "scripts.intl_phase0.build_c2_sleeve",   # W2: causal pooled-sleeve builder
        "notes": "Prior (pooled INTL sleeve vs INTL drawdowns): DSR 0.9978, split-half PASS. "
                 "C2 tests the DECLARED target — US SPY forward drawdown — with orthogonality "
                 "vs the 5 US MRS legs + crisis-independent ES. KR dropped from the pooled gate "
                 "(INTL-50). Seam if it clears: conditions._macro_risk_legs → macro_risk_series "
                 "× sector_macro_beta.",
    },
    # -- C3 · Global ETF breadth barometer --------------------------------
    {
        "id": "c3_global_etf_breadth",
        "channel": "C3",
        "hypothesis": "% of country ETFs > 200dma (+63d slope) below threshold leads "
                      "SPX/CSI300 ≥5% drawdowns at 21-42d (global analog of risk_radar_intl breadth).",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        "source_series": [("intl_etf", "EWJ"), ("intl_etf", "EWG"), ("intl_etf", "EWU"),
                          ("intl_etf", "EWY"), ("intl_etf", "EWA"), ("intl_etf", "EWQ")],
        "freshness_sla_days": 8,
        "builder": None,   # W2 (C3) on the W0 ETF store
        "notes": "Breadth-collapse is the STRONGEST leg inside risk_radar_intl.CN (lift 1.97-3.13×). "
                 "Gate: orthogonality vs US radar's domestic legs. Seams: US risk_radar Tier-B leg "
                 "(INTL-38) + a risk_radar_intl profile leg.",
    },
    # -- C4 · Dollar channel, three prongs --------------------------------
    {
        "id": "c4_reer_value",
        "channel": "C4",
        "hypothesis": "Broad-dollar REER value factor (cheap = bullish USD) predicts forward "
                      "broad-USD returns — pre-registered N=1 resurrection.",
        "direction": "de-risk",   # a rich dollar is the risk-off tell for cyclicals/EM
        "target": ("forex", "broad_dollar"),
        "horizons": _TILT_HORIZONS + (126,),
        # W3 correction (same shape as the C1 _GSPC→SPY re-point): the forex group stores
        # JSON snapshots, not per-series parquets, so "forex/broad_dollar" would trip the
        # fail-closed freshness gate (missing → PENDING). The engine's OWN driver map
        # (config.yml forex.drivers) resolves broad_dollar → fred/DTWEXBGS and reer_us →
        # fred/RBUSBIS — the actual on-disk causal series the calibration report graded.
        # target/horizons/direction are UNCHANGED (no post-hoc grid edit).
        "source_series": [("fred", "DTWEXBGS"), ("fred", "RBUSBIS")],
        # RBUSBIS is the BIS monthly real broad effective exchange rate — a monthly print
        # with a multi-week publishing lag (on disk ~2 months old between releases). 90d =
        # ~2 monthly cadences: tolerant of the normal lag, still catches a DEAD series
        # (years stale). DTWEXBGS is daily/live (~6d), well inside 90d.
        "freshness_sla_days": 90,
        "builder": "scripts.c4_reer_value.builder",   # W3 (C4a) — pre-registered N=1
        # The N=1 budget separation (INTL-43 discipline): grade this ONE config on its OWN
        # single-trial ledger family, NOT the intl_bridge budget (N=17) and NOT the forex
        # 60-trial family that budget-killed it. This is the honest resurrection door.
        "trial_family": "c4_reer_value_n1",
        "notes": "CONFIRMED both halves (IC +0.065/+0.077/+0.060) but killed by the forex 60-trial "
                 "budget. Pre-register as N=1, not a quiet promotion (INTL-43 discipline).",
    },
    {
        "id": "c4_cnh_basis",
        "channel": "C4",
        "hypothesis": "cnh_basis_bps widening (offshore CNH funding stress) leads CSI300 63d "
                      "forward drawdowns — second China RORO leg beside the raw usdcnh leg.",
        "direction": "de-risk",
        "target": ("yahoo", "FXI"),
        "horizons": _DD_HORIZONS,
        # cnh_basis_bps = (offshore USDCNH − onshore USDCNY)/onshore × 1e4 (engine.forex_signals
        # .cnh_basis). Offshore = yahoo/CNH_F (CME futures, live daily from 2013-02); onshore =
        # fred/DEXCHUS (PBoC reference, ~2-week publishing lag). No standalone "forex/cnh_basis"
        # parquet exists → point at the two raw inputs the basis is derived from (W3 correction).
        "source_series": [("yahoo", "CNH_F"), ("fred", "DEXCHUS")],
        # DEXCHUS lags ~2 weeks; CNH_F is same-day. 21d SLA tolerates the onshore publishing
        # lag while still catching a dead feed.
        "freshness_sla_days": 21,
        "builder": "scripts.c4_cnh_basis.builder",   # W3 (C4c)
        "notes": "cny_shock is an established China driver fingerprint (china_market_drivers). "
                 "USDCNH history short (2013+) → unmeasured in the standard split (INTL-44). "
                 "Orthogonality vs the EXISTING raw usdcnh RORO leg is the deciding gate.",
    },
    # -- C5 · Global-rates leaf -------------------------------------------
    {
        "id": "c5_global_rates",
        "channel": "C5",
        "hypothesis": "Rising avg_10y / widening us_premium_bp (global duration/growth headwind) "
                      "leads US equity drawdowns beyond the existing US curve/credit legs.",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        # W3 correction (documented): avg_10y + us_premium_bp dead-end in bond_health.json
        # with NO history on disk (INTL-15) — store.last_date('bonds','avg_10y') is None, so
        # the declared placeholders would trip the fail-closed freshness gate as MISSING and
        # force PENDING regardless of the measurement. engine.global_rates reconstructs both
        # aggregates causally from the underlying sovereign 10y legs the scorecard uses;
        # source_series is re-pointed to those live on-disk inputs (US DGS10 + the deepest
        # roster legs). Target/horizons/direction/channel are UNCHANGED — no new trial.
        "source_series": [("fred", "DGS10"), ("sovereign", "ez_aaa_10y"),
                          ("sovereign", "jgb_10y")],
        "freshness_sla_days": 8,
        "builder": "scripts.c5_global_rates.builder",   # W3 (C5) — causal global cost-of-capital leg
        "notes": "avg_10y + us_premium_bp computed in bond_health.json but with NO history "
                 "(INTL-15) → reconstructed causally by engine.global_rates from the same "
                 "sovereign 10y legs. Gate: orthogonality vs existing US curve/credit MRS legs "
                 "(the global 10y is plausibly ~US 10y + noise — a truthful CONTEXT is expected). "
                 "Seam if it clears: MRS candidate leg.",
    },
    # -- C6 · Asia-semi aggregate read-through ----------------------------
    {
        "id": "c6_asia_semi_readthrough",
        "channel": "C6",
        "hypothesis": "One EW Asia-semi sensor basket (TSM+ASML+…) leads SMH at ONE pre-registered "
                      "horizon, earnings-print windows excised (overnight risk carry-in).",
        "direction": "de-risk",   # rolling over → de-risk confirmer; add-tilt only post-kernel
        "target": ("yahoo", "SMH"),
        "horizons": (5,),   # ONE pre-registered horizon — the lead-lag prior is lag-1
        "source_series": [("yahoo", "TSM"), ("yahoo", "ASML")],
        "freshness_sla_days": 5,
        "builder": None,   # W4 (C6) through the lead-lag kernel
        "notes": "Context tier until it clears the lead-lag kernel; if only lag-1 survives → "
                 "transmission read (honest de-risk confirmer). Seam if promoted: "
                 "stock_score._axis_tailwind, DOWNGRADE-capable only.",
    },
    # -- C7 · Luxury → China-consumer aggregate ---------------------------
    {
        "id": "c7_luxury_china_consumer",
        "channel": "C7",
        "hypothesis": "One EW luxury basket (LVMUY+…) rolling over leads a CN-consumer target "
                      "basket down — a policy-undistorted read on the Chinese consumer.",
        "direction": "de-risk",
        "target": ("yahoo", "FXI"),
        "horizons": (21,),   # ONE pre-registered horizon
        "source_series": [("yahoo", "LVMUY")],
        "freshness_sla_days": 5,
        "builder": None,   # W4 (C7) through the lead-lag kernel
        "notes": "Same discipline as C6: one aggregate, kernel-gated, context-tier default, "
                 "de-risk grain first (luxury rolling over → trim CN-consumer conviction).",
    },
    # -- C8 · Cross-asset leading votes → fractional MRS booster ----------
    {
        "id": "c8_crossasset_leading_votes",
        "channel": "C8",
        "hypothesis": "cross_asset_confirm leading_caution_votes ≥ 2 while verdict=diverge → "
                      "small MRS bump (credit + curve, the literature-lead legs).",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        # W3 correction (documented): the votes are computed live in cross_asset_confirm from
        # bond_health.json + forex/latest.json (no vote HISTORY on disk), so the declared
        # placeholders bonds/hy_oas + bonds/curve_2s10s do not exist as parquets (store.last_date
        # is None → MISSING → fail-closed PENDING). scripts.c8_leading_votes reconstructs the
        # three votes (credit / rates-vol / dollar) causally from their ACTUAL on-disk inputs,
        # same-day-available. source_series re-pointed to those. Target/horizons/direction fixed.
        "source_series": [("fred", "BAMLH0A0HYM2"), ("yahoo", "_MOVE"),
                          ("fred", "DTWEXBGS")],
        "freshness_sla_days": 8,
        "builder": "scripts.c8_leading_votes.builder",   # W3 (C8) — reconstructed vote series
        "notes": "cross_asset_confirm is LIVE in run.py (INTL-46) but its leading legs are never "
                 "consumed upstream of stock scoring, and no vote HISTORY exists on disk → the "
                 "votes (credit HY-band/widening, rates-vol MOVE-band/leads-VIX, dollar risk-off) "
                 "are reconstructed causally from their input series. Gate: the credit/curve votes "
                 "may be near-duplicates of the nfci/recession MRS legs — that is the orthogonality "
                 "test. Needs only orthogonality + measured weight.",
    },
    # -- RRI-S4 · fast global legs (2026-07-17, operator-ratified prereg) --------
    # research/RRI_S4_FAST_GLOBAL_LEG_PREREG.md (frozen in PR #2725). Two LOCAL-close
    # substrates for the C3 global-breadth channel, motivated by the 2026-07-17 Asia-crash
    # anti-fire postmortem: the ETF-based c3_global_etf_breadth prices at the US close (a
    # session behind Asia cash) and reads %>200dma level (blind at parabolic tops). Both
    # claims carry an EXTRA gate beyond the standard battery: incremental content vs the
    # same-day c3_global_etf_breadth feature + a t vs t+1 timing decomposition (prereg §3).
    # APPEND-ONLY at the list tail: tests index CLAIMS positionally (e.g. CLAIMS[1] = c2).
    {
        "id": "c3b_local_index_breadth",
        "channel": "C3",
        "hypothesis": "% of local bench indices (>=8 of the 10 radar benches, LOCAL closes) above "
                      "their 200dma, with its 63d slope, leads US >=5% drawdowns — the C3 mechanism "
                      "on a substrate that is a session faster and immune to US-session smoothing.",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        "source_series": [("intl", "^KS11"), ("intl", "^N225"), ("intl", "^TWII"),
                          ("intl", "^NSEI"), ("intl", "^AXJO"), ("intl", "^FTSE"),
                          ("intl", "^STOXX"), ("china", "000001.SS"), ("hk", "_HSI"),
                          ("canada", "_GSPTSE")],
        "freshness_sla_days": 5,
        "builder": None,   # builder PR only after this declare lands (prereg lifecycle)
        "notes": "RRI-S4a (2026-07-17). Anti-fire postmortem of the 2026-07-17 Asia crash. "
                 "Extra gate: incremental content vs c3_global_etf_breadth (residual must retain "
                 ">=0.50 of the unconditional surviving fraction) + t vs t+1 timing decomposition "
                 "(research/RRI_S4_FAST_GLOBAL_LEG_PREREG.md §3).",
    },
    {
        "id": "c3c_intl_radar_alert_breadth",
        "channel": "C3",
        "hypothesis": "Fraction of intl radar profiles (10 markets) in gated elevated/risk-off, "
                      "causal 504d percentile, leads US >=5% drawdowns — the radars aggregate "
                      "rate/FX/extension drivers that individual breadth lenses miss.",
        "direction": "de-risk",
        "target": ("yahoo", "_GSPC"),
        "horizons": _DD_HORIZONS,
        "source_series": [("intl", "^KS11"), ("intl", "^N225"), ("intl", "^TWII"),
                          ("intl", "^NSEI"), ("intl", "^AXJO"), ("intl", "^FTSE"),
                          ("intl", "^STOXX"), ("china", "000001.SS"), ("hk", "_HSI"),
                          ("canada", "_GSPTSE"), ("fred", "DGS2"), ("fred", "DFII10"),
                          ("fred", "DGS10"), ("intl", "USDKRW=X"), ("intl", "USDJPY=X"),
                          ("intl", "USDTWD=X"), ("intl", "USDINR=X"), ("intl", "AUDUSD=X"),
                          ("intl", "GBPUSD=X"), ("intl", "EURUSD=X"), ("yahoo", "DX-Y.NYB"),
                          ("yahoo", "CNH_F"), ("china_property", "cgb"),
                          ("china_breadth", "breadth"), ("canada_breadth", "breadth")],
        "freshness_sla_days": 5,
        "builder": None,   # builder PR only after this declare lands (prereg lifecycle)
        "notes": "RRI-S4b (2026-07-17). Deterministic transform of committed store data via "
                 "engine.risk_radar_intl.composite_series — a DATA leg, not a verdict router "
                 "(FR-1/R3 fence): no can_force, no veto, no state is consumed; only the count of "
                 "band-crossings of a published deterministic construction. Graded by THIS battery "
                 "vs _GSPC at (21, 42) — NOT by risk_radar_intl_audit "
                 "(research/RRI_S4_FAST_GLOBAL_LEG_PREREG.md §2-3).",
    },
]


def declared_grid() -> list[dict]:
    """The FULL claim × horizon × target grid, one config per (claim, horizon) — the
    multiple-testing budget the harness logs into the ``intl_bridge`` ledger family at
    generation. Content is deterministic so re-declaring is idempotent (the ledger dedups
    by content hash). Each config is a small JSON-able dict (the ledger hashes it)."""
    grid: list[dict] = []
    for c in CLAIMS:
        tgt = "/".join(c["target"])
        for h in c["horizons"]:
            grid.append({
                "claim": c["id"], "channel": c["channel"], "direction": c["direction"],
                "target": tgt, "horizon": int(h),
            })
    return grid


# --------------------------------------------------------------------------- #
# Backfill — the already-run evidence, in the ledger schema. validation_ref quotes
# the exact report path; verdict/weight_cap follow the §4.1 policy. `builder` is None
# because these are graded from prior reports, not re-scanned by this harness.
# --------------------------------------------------------------------------- #
# Three-state weight policy (§4.1): CONFIRMED → measured cap; DIRECTIONAL → half,
# de-risk-only; CONTEXT/INVERTED/PENDING → 0. Backfill entries are display/pending
# until a fresh scan clears the intl-specific gates, so every cap here is 0.0.
BACKFILL: list[dict] = [
    {
        "id": "c2_intl_macro_sleeve",
        "channel": "C2",
        "hypothesis": "Pooled intl macro de-risk sleeve (curve+Sahm+tightening, JP/EZ/GB) "
                      "leads US SPY drawdowns beyond the 5 existing US MRS legs.",
        "direction": "de-risk",
        # W2 (macro C2) VERDICT: CONTEXT — do NOT wire. The prior DSR 0.9978 was the pooled
        # INTL sleeve predicting INTL drawdowns; graded against the DECLARED target (US SPY
        # forward drawdown) on the honest fully-specified window (2002-05, first date all
        # three markets carry all their declared legs — no look-ahead), the sleeve-gated SPY
        # strategy's deflated Sharpe is 0.83 — BELOW the 0.90 promotion door — and its residual
        # forward-DD content after partialing out the 5 US MRS legs is marginal and
        # window-fragile (Spearman −0.03 @2000-start, −0.17 @2002-start). crisis_count PASS (5),
        # crisis-independent ES PASS (+0.0026), split-half PASS. The binding failure is the DSR
        # door: against the US book the sleeve's growth-scare information largely overlaps what
        # NFCI/liquidity/recession already capture. Truthful negative — weight_cap 0, kill=True.
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": 0.8282, "split_half_same_sign": True,
                    "effective_n_crises": 5, "es_ex_top3": 0.0026, "orthogonal_partial": -0.1669},
        "gates": {"deflated_sharpe": "fail", "split_half": "pass", "leave_one_crisis_out": "pass",
                  "orthogonality": "pass", "crisis_independent_es": "pass", "lead_lag_kernel": "na",
                  "freshness": "pass"},
        "source_series": ["intl_macro/JP_yield_10y", "intl_macro/JP_short_3m",
                          "intl_macro/de_10y", "intl_macro/GB_yield_10y"],
        "freshness_sla_days": 120,
        "validation_ref": "reports/intl-macro-sleeve-phase0.md; scripts/intl_phase0.py "
                          "build_c2_sleeve (W2 grade — US SPY target, honest 2002-05 window)",
        "kill": True,
        "notes": "W2 VERDICT: CONTEXT (do NOT wire). Prior DSR 0.9978 was the pooled INTL sleeve "
                 "vs INTL drawdowns; against the DECLARED US SPY forward-drawdown target the "
                 "sleeve-gated strategy DSR is 0.83 (< 0.90 door) and its residual DD-content vs "
                 "the 5 US MRS legs is marginal/window-fragile (Spearman −0.03..−0.17). It DOES "
                 "cut SPY MaxDD modestly (−50.1% vs −56.8% B&H) but that overlaps NFCI/liquidity/"
                 "recession — no orthogonal edge that clears the door. EZ runs curve+short only "
                 "(EZ unemployment dead, frozen 2023-01). KR dropped (INTL-50). weight_cap 0.",
    },
    {
        "id": "intl_trend_overlay",
        "channel": "C3",
        "hypothesis": "200d-SMA trend overlay on foreign PRICE indices cuts the within-crisis "
                      "drawdown (DD-side tail insurance).",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": 0.9253, "split_half_same_sign": False,
                    "effective_n_crises": 5, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "pass", "split_half": "fail", "leave_one_crisis_out": "pass",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "na",
                  "freshness": "na"},
        "source_series": ["intl/_N225", "intl/_GDAXI", "intl/_FTSE", "intl/_KS11"],
        "freshness_sla_days": 5,
        "validation_ref": "reports/intl-trend-overlay-phase0.md",
        "kill": False,
        "notes": "DD-cut is REAL (pooled MaxDD −18.5% vs −57.0%, bootstrap CI [5.9,25.1,48.1] "
                 "excludes 0) but the Sharpe/return edge FAILS split-half (2H trend < B&H) and "
                 "the megabear robustness. CONTEXT = tail-insurance, no scored alpha.",
    },
    {
        "id": "intl_tr_trend",
        "channel": "C3",
        "hypothesis": "Trend/macro overlays on tradeable USD total-return country ETFs "
                      "(EWJ/EWG/EWU/EWY/EWA/EWQ) rescue the intl trend edge above confirmer.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": 0.848, "split_half_same_sign": False,
                    "effective_n_crises": 5, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "fail", "split_half": "fail", "leave_one_crisis_out": "pass",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "na",
                  "freshness": "na"},
        "source_series": ["intl_etf/EWJ", "intl_etf/EWG", "intl_etf/EWU", "intl_etf/EWY"],
        "freshness_sla_days": 8,
        "validation_ref": "reports/intl-tr-trend-phase0.md",
        "kill": False,
        "notes": "ALL overlays land 'no' on the tradeable TR ETFs: pooled DSR 0.848 (<0.90), "
                 "split-half Sharpe sign-flips (+0.24/−0.02), and macro-gating HARMS EWY "
                 "(MaxDD −79.3% vs −74.1%, INTL-50). USD TR lacks the local indices' secular bear. "
                 "Confirms: trend on tradeable intl is dead, same as the US kill.",
    },
    {
        "id": "forex_per_pair_conviction",
        "channel": "C4",
        "hypothesis": "Per-pair FX conviction (naive-bullish factor blend) times the base-vs-USD "
                      "forward return — a tradeable pair-level signal.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": 0.8607, "split_half_same_sign": None,
                    "effective_n_crises": None, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "fail", "split_half": "na", "leave_one_crisis_out": "na",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "na",
                  "freshness": "na"},
        "source_series": ["forex/eurusd", "forex/usdjpy", "forex/audusd", "forex/usdcad"],
        "freshness_sla_days": 5,
        "validation_ref": "reports/forex-calibration.md",
        "kill": False,
        "notes": "EVERY pair fails DSR (best USDCAD 0.8607 < 0.90; most ≈0). No pair-level gating "
                 "on equities, ever (INTL-43). The REER value factor is split out as c4_reer_value.",
    },
    {
        "id": "c4_reer_value",
        "channel": "C4",
        "hypothesis": "Broad-dollar REER value factor (cheap = bullish USD) predicts forward "
                      "broad-USD returns — pre-registered N=1 resurrection.",
        "direction": "de-risk",
        # W3-C4a VERDICT: CONFIRMED. The honest INTL-43 resurrection. The factor (cheap dollar
        # = bullish USD, faithful to config forex.dollar_desk.valuation) CONFIRMED forward
        # broad-USD returns in BOTH halves at all three declared horizons (h=21 +0.031/+0.030,
        # h=63 +0.062/+0.056, h=126 +0.120/+0.099). Graded through the FULL harness battery on
        # its OWN single-trial budget (trial_family c4_reer_value_n1) — the pre-registered N=1
        # door, budget-separated from the forex 60-trial family AND the intl_bridge N=17 family:
        # de-risk long-flat book DSR = 0.9436 (>= 0.90 door), split-half PASS, orthogonality vs
        # the 5 US MRS legs PASS (residual Spearman −0.130), crisis-count 4 PASS, crisis-indep
        # ES +0.0025 PASS. Contrast: the SAME strategy under the intl_bridge N=17 budget DSRs
        # to 0.40, and the forex 60-trial family DSR was 0.0056 — the budget separation is the
        # whole resurrection. weight_cap 0.1333 (0.20 × (4−2)/3, scaled by 4 independent crises).
        "verdict": "CONFIRMED",
        "weight_cap": 0.1333,
        "metrics": {"ic": 0.0507, "dsr": 0.9436, "split_half_same_sign": True,
                    "effective_n_crises": 4, "es_ex_top3": 0.0025, "orthogonal_partial": -0.1301},
        "gates": {"deflated_sharpe": "pass", "split_half": "pass", "leave_one_crisis_out": "pass",
                  "orthogonality": "pass", "crisis_independent_es": "pass", "lead_lag_kernel": "na",
                  "freshness": "pass"},
        "source_series": ["fred/DTWEXBGS", "fred/RBUSBIS"],
        "freshness_sla_days": 90,
        "validation_ref": "reports/forex-calibration.md (DOLLAR INDEX value); "
                          "reports/forex-reer-n1-phase0.md (W3-C4a N=1); "
                          "scripts/c4_reer_value.py + scripts/intl_phase0.py (grade, N=1 budget)",
        "kill": False,
        "notes": "W3-C4a VERDICT: CONFIRMED (the pre-registered N=1 resurrection, INTL-43). "
                 "CONFIRMED both halves at all 3 declared horizons; graded on a SEPARATE "
                 "single-trial budget (c4_reer_value_n1) → de-risk long-flat DSR 0.9436 >= 0.90 "
                 "(vs 0.40 under the intl_bridge N=17 budget, 0.0056 under the forex 60-trial "
                 "family — the budget separation is the resurrection). Orthogonality vs the 5 US "
                 "MRS legs PASS. weight_cap 0.1333 (4 independent crises). NO CONSUMER WIRING this "
                 "wave: the CONFIRMED verdict is RECORDED and the leg is surfaced by the Layer-2 "
                 "registry reader (intl_feed.features() → weight 0.1333, de-risk direction), but "
                 "NO scorer calls intl_feed — nothing sizes on it. Consumer wiring DEFERRED to a "
                 "follow-up: the target seam is an MRS candidate leg (conditions._macro_risk_legs) "
                 "but W2-C2 showed the MRS orthogonality bar is high and this is a returns-"
                 "predicting dollar factor, not a US-drawdown leg, so a dedicated MRS-composite "
                 "orthogonality gate must clear before it sizes US positions.",
    },
    {
        "id": "c4_cnh_basis",
        "channel": "C4",
        "hypothesis": "cnh_basis_bps widening (offshore CNH funding stress) leads CSI300/FXI "
                      "forward drawdowns — candidate SECOND China RORO leg beside the raw usdcnh leg.",
        "direction": "de-risk",
        # W3-C4c VERDICT: INVERTED — do NOT wire. The offshore-minus-onshore CNH basis (a
        # funding-stress spread) carries NO orthogonal de-risk content vs the EXISTING raw
        # usdcnh RORO leg (offshore 20d move, china_conditions.roro_frame). Graded at the
        # declared 42d DD horizon against FXI (CSI300 proxy on disk): rank-IC ~0.0003 (null),
        # split-half sign-FLIPS, DSR 0.0013, and — the decider — the residual after partialing
        # out the raw usdcnh leg is WRONG-SIGNED (Spearman +0.121: wider basis → SHALLOWER
        # forward drawdown), plus crisis-independent ES is NEGATIVE (−0.0095: the gated book
        # does not reduce expected-shortfall outside crises). Respecting W2-C1 (CN RORO legs
        # already carry beta-type content), the basis double-counts the offshore-move leg with
        # the wrong sign. Truthful negative — weight_cap 0, kill=True; the existing raw usdcnh
        # RORO leg (china_conditions.py:161-163) is UNCHANGED, no second leg added.
        "verdict": "INVERTED",
        "weight_cap": 0.0,
        "metrics": {"ic": 0.0003, "dsr": 0.0013, "split_half_same_sign": False,
                    "effective_n_crises": 4, "es_ex_top3": -0.0095, "orthogonal_partial": 0.1214},
        "gates": {"deflated_sharpe": "fail", "split_half": "fail", "leave_one_crisis_out": "pass",
                  "orthogonality": "pass", "crisis_independent_es": "fail", "lead_lag_kernel": "na",
                  "freshness": "pass"},
        "source_series": ["yahoo/CNH_F", "fred/DEXCHUS"],
        "freshness_sla_days": 21,
        "validation_ref": "reports/forex-reer-n1-phase0.md (W3-C4c CNH-basis section); "
                          "scripts/c4_cnh_basis.py + scripts/intl_phase0.py (grade)",
        "kill": True,
        "notes": "W3-C4c VERDICT: INVERTED (do NOT wire). The CNH offshore-onshore basis adds no "
                 "orthogonal de-risk edge vs the existing raw usdcnh RORO leg — rank-IC ~0 vs FXI "
                 "forward DD, split-half sign-flips, DSR 0.0013, and its residual after partialing "
                 "the raw usdcnh leg is WRONG-SIGNED (+0.121) with negative crisis-independent ES. "
                 "USDCNH history is short (2013+, ~2 China bears). Respecting W2-C1 (CN RORO legs "
                 "already carry beta content), a second basis leg double-counts. NOT wired: "
                 "china_conditions._macro/roro legs unchanged.",
    },
    {
        "id": "crossmarket_leadlag",
        "channel": "C8",
        "hypothesis": "Cross-market lead/lag links (150 pairs × 5 lags) forecast next-session "
                      "moves in US/CN/HK.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": None, "split_half_same_sign": True,
                    "effective_n_crises": None, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "na", "split_half": "pass", "leave_one_crisis_out": "na",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "pass",
                  "freshness": "na"},
        "source_series": ["yahoo/_GSPC", "yahoo/FXI"],
        "freshness_sla_days": 5,
        "validation_ref": "reports/cross-asset-leadlag-phase0.md",
        "kill": False,
        "notes": "HAC-t + BH-FDR across 150 pairs: 7/150 survive, 5 split-half stable — but ALL "
                 "survivors are timezone lag-1 (US/global close → next Asia open). Transmission "
                 "read, NOT a forecastable lead. CONTEXT.",
    },
    {
        "id": "cn_external_radar",
        "channel": "C3",
        "hypothesis": "China external-driver radar (breadth collapse, US rate shocks, US-CN "
                      "differential, USD/CNH) lifts forward CSI300 drawdown probability.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": None, "dsr": None, "split_half_same_sign": None,
                    "effective_n_crises": None, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "na", "split_half": "na", "leave_one_crisis_out": "na",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "na",
                  "freshness": "na"},
        "source_series": ["risk_radar_intl/cn_forward_log"],
        "freshness_sla_days": 5,
        "validation_ref": "engine/risk_radar_intl.py (validated #711/#718); "
                          "engine/risk_radar_intl_audit.py (forward-log + can_force governance)",
        "kill": False,
        "notes": "NOTE-ONLY entry. This engine EXISTS on main with committed forward logs and its "
                 "OWN can_force maturation gate (>=30 graded, >=8 alerts, realized lift >=1.25x). "
                 "Composite >=10%/42d drawdown lift 2.07x (p=0.01), CSI300-confirmed. The intl_bridge "
                 "does NOT duplicate its machinery — it defers to risk_radar_intl_audit.scorecard "
                 "for the CN/HK/CA governance. Listed CONTEXT here for registry completeness.",
    },
    # W3-C5 — global cost-of-capital de-risk leg (graded 2026-07-02, scripts/intl_phase0.py --c5c8)
    # VERDICT: CONTEXT — do NOT wire. The global 10y IS ~US 10y + noise (the US 10y is one of
    # the seven roster legs, weight 0.42) — the C5 global-10y momentum signal correlates 0.948
    # with the US-only 10y momentum, exactly the masterplan's honest prior. The binding failure
    # is the drawdown-reduction gate measured over the SIGNAL-ACTIVE era (from 1963, the first
    # flat day; the full _GSPC history includes the 1929-32 crash both books were long through,
    # which is not a de-risk test): the long/flat strategy shaves only 1.1pp off SPY MaxDD
    # (-55.66% vs -56.78% B&H) while HALVING the total return — its Calmar (0.115) is WORSE than
    # buy-and-hold (0.137), so the overlay destroys value, it does not de-risk. A de-risk leg
    # whose drawdown reduction is not cost-justified is CONTEXT no matter its DSR (the DSR 0.98
    # is SPY drift: a mostly-long book inherits SPY's Sharpe; buy-and-hold SPY clears the door).
    {
        "id": "c5_global_rates",
        "channel": "C5",
        "hypothesis": "Rising GDP-weighted global 10y / widening US premium (global duration + "
                      "growth-beta headwind) leads US equity drawdowns beyond the US curve/credit legs.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": -0.064, "dsr": 0.9797, "split_half_same_sign": True,
                    "effective_n_crises": 6, "es_ex_top3": 0.0012, "orthogonal_partial": -0.1288},
        "gates": {"deflated_sharpe": "spy-drift", "split_half": "pass",
                  "leave_one_crisis_out": "pass", "orthogonality": "pass",
                  "crisis_independent_es": "pass", "drawdown_reduction": "fail",
                  "lead_lag_kernel": "na", "freshness": "pass"},
        "source_series": ["fred/DGS10", "sovereign/ez_aaa_10y", "sovereign/jgb_10y"],
        "freshness_sla_days": 8,
        "validation_ref": "scripts/c5_global_rates.py + scripts/intl_phase0.py (grade, W3 C5); "
                          "engine/global_rates.py; data/intl_bridge/ledger.json (C5)",
        "kill": True,
        "notes": "W3-C5 VERDICT: CONTEXT (do NOT wire). avg_10y + us_premium_bp reconstructed "
                 "causally by engine.global_rates from the sovereign 10y roster (bond_health.json "
                 "keeps only a snapshot, no history — INTL-15). The global 10y is ~US 10y + noise "
                 "(the C5 rate-rise signal correlates 0.948 with the US-only 10y momentum; US is a "
                 "0.42-weight roster leg), so it carries no orthogonal US-drawdown edge over the "
                 "existing curve/credit MRS legs. The DECIDING gate is drawdown-reduction over the "
                 "signal-active era (from 1963): the long/flat strategy cuts SPY MaxDD only 1.1pp "
                 "(-55.7% vs -56.8% B&H) while HALVING total return — Calmar 0.115 < 0.137 B&H, so "
                 "the overlay destroys value, it does not de-risk. DSR 0.98 is SPY drift, not an "
                 "edge. conditions._macro_risk_legs UNCHANGED — no MRS leg added. weight_cap 0.",
    },
    # W3-C8 — cross-asset leading-votes fractional MRS booster (graded 2026-07-02, --c5c8)
    # VERDICT: CONTEXT — do NOT wire. The credit/rates-vol votes are near-duplicates of the
    # nfci/recession MRS legs (residual partial only -0.09), and over the signal-active era
    # (from 2007) the votes>=2 while-equities-calm 'diverge' booster shaves only 0.6pp off SPY
    # MaxDD (-56.15% vs -56.78% B&H) — BELOW the 1pp door — while cratering the return (Calmar
    # 0.105 vs 0.153 B&H). It flattens out of good days without avoiding the bad ones.
    {
        "id": "c8_crossasset_leading_votes",
        "channel": "C8",
        "hypothesis": "cross_asset_confirm leading_caution_votes >= 2 while verdict='diverge' → "
                      "a fractional MRS de-risk booster (credit + rates-vol + dollar votes).",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": -0.0468, "dsr": 0.981, "split_half_same_sign": True,
                    "effective_n_crises": 6, "es_ex_top3": 0.0001, "orthogonal_partial": -0.0899},
        "gates": {"deflated_sharpe": "spy-drift", "split_half": "pass",
                  "leave_one_crisis_out": "pass", "orthogonality": "pass",
                  "crisis_independent_es": "pass", "drawdown_reduction": "fail",
                  "lead_lag_kernel": "na", "freshness": "pass"},
        "source_series": ["fred/BAMLH0A0HYM2", "yahoo/_MOVE", "fred/DTWEXBGS"],
        "freshness_sla_days": 8,
        "validation_ref": "scripts/c8_leading_votes.py + scripts/intl_phase0.py (grade, W3 C8); "
                          "engine/cross_asset_confirm.py (vote defs); data/intl_bridge/ledger.json (C8)",
        "kill": True,
        "notes": "W3-C8 VERDICT: CONTEXT (do NOT wire). The three votes (credit HY-band/widening, "
                 "rates-vol MOVE-band/leads-VIX, dollar risk-off) reconstructed causally from their "
                 "input series (no vote history on disk — INTL-46). The credit/rates-vol votes are "
                 "near-duplicates of the nfci/recession MRS legs (residual partial only -0.09). The "
                 "DECIDING gate is drawdown-reduction over the signal-active era (from 2007): the "
                 "votes>=2 while-equities-calm booster cuts SPY MaxDD only 0.6pp (-56.2% vs -56.8% "
                 "B&H) — below the 1pp door — while cratering return (Calmar 0.105 < 0.153 B&H). It "
                 "flattens out of good days without avoiding the bad ones. DSR 0.98 is SPY drift. "
                 "conditions._macro_risk_legs UNCHANGED — no MRS leg added. weight_cap 0.",
    },
    # W4-C6 — Asia-semi aggregate read-through (graded 2026-07-02, scripts/intl_phase0.py --c6)
    # VERDICT: CONTEXT — do NOT wire. The ONE pre-registered EW Asia-semi basket (TSM + ASML,
    # the declared source_series — US-listed ADRs chosen ON PURPOSE per §4.4 to kill the
    # lag-1 timezone ambiguity) shows, through the lead-lag kernel with ±2td earnings-print
    # excision (12.8% of rows excised, INTL-49), a MASSIVE contemporaneous lag-0 correlation
    # with SMH (HAC-t +15.9, mean +0.82, FDR-reject, split-half stable) — but that is
    # MECHANICAL CO-MEMBERSHIP (TSM+ASML are two of SMH's largest holdings), NOT a lead. NO
    # lag>=1 link survives: lag1 HAC-t −1.67 (q_FDR 0.16, does not reject; split-half FALSE;
    # its sign is negative, mirroring SMH's OWN lag-1 mean-reversion −0.05), lag2/3/5 all
    # |t|<2.1 and non-surviving. So there is no tradeable lead AND — because the ADRs trade
    # in the US session — not even the timezone-transmission lag-1 the raw local-index screen
    # (cross-asset-leadlag-phase0) had: the ADR design removed the overnight carry-in, leaving
    # only same-day co-membership. The lead-lag kernel is the BINDING gate (ADJ-4): its pass
    # excludes lag0 by construction, so a claim with no surviving lag>=1 is CONTEXT no matter
    # its other gates. (For completeness the de-risk overlay also fails gate f — the basket-
    # rolling-over long/flat book does cut SMH MaxDD 10.1pp but the DSR is 0.45 and split-half
    # Sharpe sign-flips; and orthogonality vs SMH's OWN 5d/21d momentum leaves a wrong-signed
    # residual +0.07 — the basket adds nothing beyond 'semis lead semis'.) Truthful negative,
    # weight_cap 0, kill=True. stock_score._axis_tailwind (the would-be DOWNGRADE-only seam)
    # is UNCHANGED — the harness wires nothing this wave regardless of verdict, and CONTEXT
    # means nothing to wire ever.
    {
        "id": "c6_asia_semi_readthrough",
        "channel": "C6",
        "hypothesis": "One EW Asia-semi sensor basket (TSM + ASML, US-listed ADRs) leads SMH at "
                      "the pre-registered 5d horizon, earnings-print windows excised.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {"ic": 0.1568, "dsr": 0.4463, "split_half_same_sign": False,
                    "effective_n_crises": 5, "es_ex_top3": 0.0061, "orthogonal_partial": 0.0724},
        "gates": {"deflated_sharpe": "fail", "split_half": "fail", "leave_one_crisis_out": "pass",
                  "orthogonality": "fail", "crisis_independent_es": "pass",
                  "drawdown_reduction": "fail", "lead_lag_kernel": "fail", "freshness": "pass"},
        "source_series": ["yahoo/TSM", "yahoo/ASML"],
        "freshness_sla_days": 5,
        "validation_ref": "reports/intl-semi-readthrough-phase0.md (W4-C6, 2026-07-02); "
                          "scripts/c6_asia_semi_readthrough.py + scripts/intl_phase0.py --c6 (grade); "
                          "data/intl_bridge/c6_earnings_dates.json (print-excision source)",
        "kill": True,
        "notes": "W4-C6 VERDICT: CONTEXT (do NOT wire). EW TSM+ASML ADR basket vs SMH through the "
                 "lead-lag kernel (±2td print excision, 12.8% of rows). lag-0 co-membership is huge "
                 "(HAC-t +15.9, mean +0.82, FDR-reject) but MECHANICAL — TSM+ASML are two of SMH's "
                 "largest holdings, not a lead. NO lag>=1 link survives FDR + split-half: lag1 HAC-t "
                 "−1.67 (q 0.16, negative — mirrors SMH's own lag-1 mean-reversion), lag2/3/5 all "
                 "|t|<2.1. The ADR design deliberately removed the overnight timezone lag, so there "
                 "is not even the transmission-read lag-1 the raw local-index screen had — only "
                 "same-day co-membership. The lead-lag kernel is the binding gate (ADJ-4). Orthogonality "
                 "vs SMH's OWN 5d/21d momentum leaves a wrong-signed residual (+0.07): nothing beyond "
                 "'semis lead semis'. stock_score._axis_tailwind UNCHANGED — nothing wired. weight_cap 0.",
    },
    # W2-C3 — global ETF breadth barometer (graded 2026-07-02, scripts/intl_phase0.py --c3)
    # Live run result: CONFIRMED. N=23 ETFs, panel>=10 threshold, 200dma, causal pctile-504d,
    # top-30% de-risk. DSR 0.9326 (intl_bridge N=17). All hard gates pass.
    # Orthogonality basis: SPY trend, HY OAS (BAMLH0A0HYM2), T10Y2Y.
    {
        "id": "c3_global_etf_breadth",
        "channel": "C3",
        "hypothesis": "% of country ETFs > 200dma below threshold leads SPX/CSI300 >=5% "
                      "drawdowns at 21-42d (global analog of risk_radar_intl breadth).",
        "direction": "de-risk",
        "verdict": "CONFIRMED",
        "weight_cap": 0.20,         # scaled by 6 independent crises; MAX_WEIGHT_CAP=0.20
        "metrics": {
            "ic": -0.198,           # Spearman(-breadth, fwd_dd42/SPX) from harness run
            "dsr": 0.9326,          # deflated-Sharpe on SPY/SPX long-flat strategy (N=17 trials)
            "split_half_same_sign": True,       # H1/H2 Sharpe both positive
            "effective_n_crises": 6,            # all 6 declared crises covered
            "es_ex_top3": 0.0078,              # ES reduction ex top-3 DD windows
            "orthogonal_partial": -0.1209,     # residual Spearman after SPY/HY/curve partial
        },
        "gates": {
            "deflated_sharpe": True,    # DSR 0.9326 >= 0.90 with N=17 intl_bridge budget
            "split_half": True,         # same-sign Sharpe both halves
            "orthogonality": True,      # surviving frac 0.62 >= 0.50; |orth| 0.12 >= 0.03
            "crisis_count": True,       # 6 independent crises
            "crisis_independent_es": True,  # ES positive ex top-3 (not crisis_only)
            "freshness": True,          # intl_etf store current through 2026-07-01
        },
        "source_series": [
            "intl_etf/EWJ", "intl_etf/EWG", "intl_etf/EWU", "intl_etf/EWY",
            "intl_etf/EWA", "intl_etf/EWQ", "intl_etf/EIDO", "intl_etf/EWT",
            "intl_etf/EWZ", "intl_etf/EZA", "intl_etf/INDA",   # + 12 more in panel
        ],
        "freshness_sla_days": 8,
        "validation_ref": "reports/intl-global-breadth-phase0.md (W2-C3, 2026-07-02); "
                          "scripts/intl_phase0.py build_c3_global_breadth()",
        "kill": False,
        "notes": "W2-C3 CONFIRMED. All hard gates pass. Panel: 23 ETFs from 1996-03-18 "
                 "(17 alive at start; min-panel=10 satisfied from day 1). "
                 "Orthogonality: global breadth corr 0.68 with SPY trend (collinearity concern); "
                 "residual after SPY/HY/curve partial = 0.62 surviving frac — PASSES (>=0.50). "
                 "This adds information BEYOND the domestic US trend leg. "
                 "W4 US radar Tier-B leg is JUSTIFIED by this verdict.",
    },
    # W4-C7 — luxury→CN-consumer aggregate read-through (graded 2026-07-02,
    # scripts/intl_phase0.py --c7 via scripts/c7_luxury_readthrough.py)
    # VERDICT: CONTEXT — do NOT wire. The EW luxury basket (LVMUY + RMS.PA + CFR.SW)
    # rolling-return trend-turn signal carries NO statistically significant lead over FXI
    # forward drawdowns at the declared 21d horizon. The lead-lag kernel confirms the
    # standing ADJ-4 prior: lag=0 is strongly contemporaneous (t=11.75, same-session
    # overlap — luxury and FXI trade in overlapping US hours), but NO lagged cross-market
    # link survives BH-FDR (lag=1: t=−1.49 p=0.14; lag=2: t=1.04 p=0.30). This is a
    # TRANSMISSION READ (luxury and Chinese consumer co-move in real-time), not a tradeable
    # lead. The de-risk strategy DSR=0.16 (far below the 0.90 door) and the
    # drawdown-reduction gate FAILS (the strategy has NEGATIVE Calmar −0.008 vs B&H
    # FXI Calmar +0.045 — the flat-out-of-FXI-recovery overlay destroys value). Four
    # hard-gate passes are noted: freshness, orthogonality (residual partial −0.061, just
    # above the 0.03 floor), crisis-count 4/6 (LVMUY's 20y history covers GFC/eurozone/
    # covid/rate_22), and crisis-independent ES +0.0076. But the signal mechanism itself
    # is not predictive: the luxury trend-turn does NOT reliably lead China consumer
    # drawdowns at any lag that survives multiple-testing correction. Earnings-print
    # excision confirmed: 271 bars excised (±2td around LVMH/Hermès/Richemont prints)
    # so the result is not contaminated by event spikes. The validated channel is
    # contemporaneous co-movement — useful as a DISPLAY confirmer ("luxury and FXI are
    # co-moving today") but structurally unable to carry the de-risk lead the thesis required.
    # weight_cap 0, kill=True; FXI target and all scorer seams UNCHANGED.
    {
        "id": "c7_luxury_china_consumer",
        "channel": "C7",
        "hypothesis": "One EW luxury basket (LVMUY+RMS.PA+CFR.SW) trend-turn leads FXI "
                      "forward drawdowns at 21d — a policy-undistorted CN-consumer read-through.",
        "direction": "de-risk",
        "verdict": "CONTEXT",
        "weight_cap": 0.0,
        "metrics": {
            "ic": -0.0695,              # Spearman(luxury_trend_turn, FXI_fwd_DD21d)
            "dsr": 0.1609,              # deflated-Sharpe on FXI long/flat strategy (N=17 trials)
            "split_half_same_sign": True,   # Sharpe both halves positive (+0.19/+0.16) — a mirage:
                                            # strategy near-always long → inherits FXI positive drift
            "effective_n_crises": 4,        # GFC/eurozone/covid/rate_22 (LVMUY 20y)
            "es_ex_top3": 0.0076,           # ES reduction ex top-3 DD windows PASSES
            "orthogonal_partial": -0.0612,  # residual Spearman vs FXI-mom + CNH-RORO basis
            "maxdd_cut": 0.0643,            # MaxDD cut passes (−66.3% vs −72.7% B&H)
        },
        "gates": {
            "deflated_sharpe": "fail",      # DSR 0.16 << 0.90 — the signal is not predictive
            "split_half": "pass",           # trivially: both halves near-long → FXI drift
            "leave_one_crisis_out": "pass", # 4 crisis windows
            "orthogonality": "pass",        # just above the 0.03 noise floor
            "crisis_independent_es": "pass",
            "drawdown_reduction": "fail",   # CALMAR KILLER: Calmar −0.008 vs +0.045 B&H
            "lead_lag_kernel": "fail",      # NO lagged link survives BH-FDR; lag=0 only
            "freshness": "pass",            # LVMUY 2026-07-02 (cold-seeded W4-C7)
        },
        "source_series": ["yahoo/LVMUY"],
        "freshness_sla_days": 5,
        "validation_ref": "reports/intl-luxury-readthrough-phase0.md (W4-C7, 2026-07-02); "
                          "scripts/c7_luxury_readthrough.py + scripts/intl_phase0.py --c7",
        "kill": True,
        "notes": "W4-C7 VERDICT: CONTEXT (do NOT wire). EW luxury basket (LVMUY ~20y + "
                 "RMS.PA/CFR.SW ~5y from intl_search/closes) rolling-return trend-turn "
                 "signal: lead-lag kernel finds NO lagged cross-market link surviving "
                 "BH-FDR (lag=1 t=−1.49 p=0.14); only lag=0 is significant (t=11.75, "
                 "contemporaneous same-session co-movement). DSR=0.16, drawdown-reduction "
                 "FAILS (negative Calmar). The validated information is SIMULTANEOUS "
                 "co-movement — a transmission read, not a tradeable de-risk lead. "
                 "271 earnings-print bars excised (±2td; causal method). Effective-N "
                 "honesty: LVMUY has 20y (4 crises), but RMS.PA/CFR.SW only 5y (1 crisis) "
                 "— the full 3-leg basket covers only 1 declared crisis window. "
                 "The LVMUY-only signal's 4-crisis count passes the floor but the "
                 "aggregate DSR fails decisively (0.16). weight_cap 0.",
    },
]


__all__ = ["FAMILY", "CLAIMS", "BACKFILL", "declared_grid"]
