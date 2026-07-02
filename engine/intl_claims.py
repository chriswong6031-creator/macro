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
        "source_series": [("forex", "broad_dollar"), ("forex", "reer_us")],
        "freshness_sla_days": 10,
        "builder": None,   # W3 (C4a) — pre-registered N=1, budget-separated from the 60-trial family
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
        "source_series": [("forex", "usdcnh"), ("forex", "cnh_basis")],
        "freshness_sla_days": 5,
        "builder": None,   # W3 (C4c)
        "notes": "cny_shock is an established China driver fingerprint (china_market_drivers). "
                 "USDCNH history short → unmeasured in the standard split (INTL-44).",
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
        "source_series": [("bonds", "avg_10y"), ("bonds", "us_premium_bp")],
        "freshness_sla_days": 5,
        "builder": None,   # W3 (C5)
        "notes": "avg_10y + us_premium_bp already computed in bond_health.json (INTL-15). "
                 "Gate: orthogonality vs existing US curve/credit legs. Seam: MRS candidate leg.",
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
        "source_series": [("bonds", "hy_oas"), ("bonds", "curve_2s10s")],
        "freshness_sla_days": 5,
        "builder": None,   # W3 (C8) — already computed live; needs orthogonality gate + weight
        "notes": "cross_asset_confirm is LIVE in run.py (INTL-46) but its leading legs are never "
                 "consumed upstream of stock scoring. Needs only the orthogonality gate + measured weight.",
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
        "verdict": "PENDING",
        "weight_cap": 0.0,
        "metrics": {"ic": 0.065, "dsr": 0.0056, "split_half_same_sign": True,
                    "effective_n_crises": None, "es_ex_top3": None, "orthogonal_partial": None},
        "gates": {"deflated_sharpe": "fail", "split_half": "pass", "leave_one_crisis_out": "na",
                  "orthogonality": "na", "crisis_independent_es": "na", "lead_lag_kernel": "na",
                  "freshness": "na"},
        "source_series": ["forex/broad_dollar", "forex/reer_us"],
        "freshness_sla_days": 10,
        "validation_ref": "reports/forex-calibration.md",
        "kill": False,
        "notes": "Pre-registered N=1 resurrection (INTL-43): CONFIRMED in BOTH halves "
                 "(IC +0.077/+0.060) but budget-killed inside the 60-trial forex family (DSR 0.0056 "
                 "there). PENDING an N=1 re-run whose trial budget is separated from that family; "
                 "the DSR quoted is the family-deflated value, not the N=1 value.",
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
]


__all__ = ["FAMILY", "CLAIMS", "BACKFILL", "declared_grid"]
