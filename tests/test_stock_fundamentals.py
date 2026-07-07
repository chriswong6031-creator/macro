"""Tests for engine/stock_fundamentals.py (the single-stock panel assembler).

pytest is not installed in the venv — run as a plain script: python tests/test_stock_fundamentals.py
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_fundamentals as SF  # noqa: E402


def test_num_and_clean():
    assert SF._num(float("nan")) is None
    assert SF._num(float("inf")) is None
    assert SF._num("x") is None
    assert SF._num(3) == 3.0
    cleaned = SF._clean({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2}})
    assert cleaned == {"a": None, "b": [1.0, None], "c": {"d": 2}}
    # the cleaned structure must be valid JSON with no NaN/Infinity tokens
    s = json.dumps(cleaned)
    assert "NaN" not in s and "Infinity" not in s


def test_archetype_unprofitable_veto_fires_first():
    # a strong-quality name that is unprofitable must NOT read "quality"
    fac = {"value": 0.0, "quality": 2.0, "profitability": 2.0,
           "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    a = SF._archetype(fac, ni=-50.0, net_margin=-10.0, nm_top_thr=20.0)
    assert a["key"] == "speculative_unprofitable"


def test_archetype_cascade():
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    # high beta + high vol (negative low_* z) → high_beta_momentum
    hb = dict(base, low_beta=-0.8, low_vol=-0.6)
    assert SF._archetype(hb, 10, 5, 30)["key"] == "high_beta_momentum"
    # high payout + low vol + low beta → dividend_defensive
    dd = dict(base, payout=0.8, low_vol=0.6, low_beta=0.5)
    assert SF._archetype(dd, 10, 5, 30)["key"] == "dividend_defensive"
    # high quality + profitable + not expensive → quality_compounder
    qc = dict(base, quality=0.8, profitability=0.5)
    assert SF._archetype(qc, 10, 5, 30)["key"] == "quality_compounder"
    # quality gate can pass via top-tercile net margin even when profitability z is missing
    qc2 = dict(base, quality=0.8, profitability=None)
    assert SF._archetype(qc2, 10, net_margin=40.0, nm_top_thr=30.0)["key"] == "quality_compounder"
    # cheap on value, quality not high → deep_value
    dv = dict(base, value=1.0, quality=0.0)
    assert SF._archetype(dv, 10, 5, 30)["key"] == "deep_value"
    # nothing dominates → mixed
    assert SF._archetype(base, 10, 5, 30)["key"] == "mixed"
    # missing factor row → None
    assert SF._archetype(None, 10, 5, 30) is None


def test_archetype_shape():
    fac = {"value": 1.0, "quality": 0.0, "profitability": 0.0,
           "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    a = SF._archetype(fac, 10, 5, 30)
    # v2: new required fields in output
    for k in ("key", "label", "label_zh", "confidence", "conf_word", "why", "why_zh",
              "anchored", "v2_inputs"):
        assert k in a, f"missing key '{k}' in archetype output"
    assert a["key"] in SF.ARCHETYPES
    assert 0.0 <= a["confidence"] <= 1.0
    assert a["conf_word"] in ("high", "moderate", "low")
    assert isinstance(a["anchored"], bool)
    assert isinstance(a["v2_inputs"], dict)


def test_earnings_includes_sue_z():
    # a full earnings row + the validated SUE z surfaces both, next to each other
    row = {"next_date": "2026-07-30", "next_time": "time-pre-market", "eps_forecast": 1.86,
           "surprises": [{"qtr": "Mar 2026", "eps": 2.01, "consensus": 1.92, "surprise_pct": 4.7}]}
    e = SF._earnings(row, 1.466)
    assert e["sue_z"] == 1.47                       # rounded to 2dp
    assert e["next_date"] == "2026-07-30"
    assert e["next_time"] == "pre-market"
    assert e["summary"]["beats"] == 1


def test_earnings_sue_only_block():
    # SUE is itself an earnings read: a name with NO Nasdaq next-date/surprises but a
    # SUE z still returns an earnings block (the chip surfaces alone).
    e = SF._earnings(None, 1.0)
    assert e is not None and e["sue_z"] == 1.0
    assert e["next_date"] is None and e["surprises"] == [] and e["summary"] is None
    assert SF._earnings({}, 2.4)["sue_z"] == 2.4


def test_earnings_none_when_nothing_to_show():
    assert SF._earnings(None, None) is None
    assert SF._earnings({}, None) is None
    # a NaN SUE with no other earnings data is nothing to show
    assert SF._earnings(None, float("nan")) is None


def test_earnings_sue_nan_coerced_json_safe():
    # a NaN SUE alongside a real next-date keeps the block but nulls the z (JSON-safe)
    e = SF._earnings({"next_date": "2026-07-30"}, float("nan"))
    assert e is not None and e["sue_z"] is None
    assert "NaN" not in json.dumps(SF._clean(e))


def test_mktcap_tier():
    assert SF._mktcap_tier(None) is None
    assert SF._mktcap_tier(500)["key"] == "mega"
    assert SF._mktcap_tier(50)["key"] == "large"
    assert SF._mktcap_tier(5)["key"] == "mid"
    assert SF._mktcap_tier(1)["key"] == "small"


def test_panels_smoke():
    """If the EDGAR cache exists, panels() must return JSON-safe blocks for a
    decent slice of the universe. Skips cleanly when data isn't present."""
    p = SF.panels()
    if not p:
        print("  (no edgar fundamentals cache — panels() smoke skipped)")
        return
    assert len(p) > 100
    # whole structure must serialize as valid JSON (no NaN/Infinity tokens)
    s = json.dumps(p, default=str)
    assert "NaN" not in s and "Infinity" not in s
    sample = next(iter(p.values()))
    # blocks present are from the known set; archetype key is valid when present
    # W2 PR-J adds thesis_clock; W2 PR-K adds moat_falsifiers + great_company_trap;
    # LT-3a adds capital_allocation; LT-2c adds expectation_state;
    # LT-4 adds thesis_funnel (AND-gate survival funnel shadow; hold_thesis; display-only)
    assert set(sample).issubset({"profile", "valuation", "financials",
                                 "factors", "positioning", "analyst", "earnings",
                                 "accounting_quality", "leverage_ratios",
                                 "thesis_clock", "moat_falsifiers", "great_company_trap",
                                 "capital_allocation", "expectation_state", "thesis_funnel"})
    for rec in list(p.values())[:200]:
        arch = (rec.get("profile") or {}).get("archetype")
        if arch:
            assert arch["key"] in SF.ARCHETYPES
        fac = rec.get("factors")
        if fac and fac.get("fundamental_score") is not None:
            assert -100 <= fac["fundamental_score"] <= 100


def test_archetype_v2_new_buckets():
    """Known-fixture tests for each v2 bucket. Each fixture is designed to be
    unambiguous — only one bucket should fire."""
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}

    # --- distressed: Altman z < 1.81, non-approx ---
    my_d = {"rev_cagr": 4.0, "eps_cagr": 2.0,
            "altman": {"z": 1.2, "zone": "distress", "approx": False}}
    a = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, my=my_d)
    assert a["key"] == "distressed", f"expected distressed, got {a['key']}"
    assert a["anchored"] is True

    # --- distressed should NOT fire when approx=True (too incomplete for hard block) ---
    my_d_approx = {"rev_cagr": 4.0, "eps_cagr": 2.0,
                   "altman": {"z": 1.2, "zone": "distress", "approx": True}}
    a_approx = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, my=my_d_approx)
    assert a_approx["key"] != "distressed", "distressed must not fire on approx=True Altman"

    # --- financial: sector-keyed, not ratio-keyed ---
    a_fin = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Financials")
    assert a_fin["key"] == "financial"
    assert a_fin["anchored"] is True

    # --- rate_sensitive: |rates beta| >= 0.40 ---
    betas_pos = {"rates": 0.55, "raw": {"oil": 0.01}}
    a_rs_pos = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, betas=betas_pos)
    assert a_rs_pos["key"] == "rate_sensitive"
    betas_neg = {"rates": -0.50, "raw": {"oil": 0.01}}
    a_rs_neg = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, betas=betas_neg)
    assert a_rs_neg["key"] == "rate_sensitive", "negative rates beta should also fire"

    # --- commodity_sensitive: |oil beta raw| >= 0.35 ---
    betas_oil = {"rates": 0.1, "raw": {"oil": 0.50}}
    a_cs = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, betas=betas_oil)
    assert a_cs["key"] == "commodity_sensitive"

    # --- secular_growth: rev_cagr>=15 AND eps_cagr>=12 ---
    my_sg = {"rev_cagr": 20.0, "eps_cagr": 15.0,
             "altman": {"z": 4.0, "zone": "safe", "approx": False}}
    a_sg = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, my=my_sg)
    assert a_sg["key"] == "secular_growth"
    assert a_sg["anchored"] is True

    # --- broken_growth: rev_cagr>=10 AND eps_cagr<=0 ---
    my_bg = {"rev_cagr": 12.0, "eps_cagr": -3.0,
             "altman": {"z": 4.0, "zone": "safe", "approx": False}}
    a_bg = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, my=my_bg)
    assert a_bg["key"] == "broken_growth"
    assert a_bg["anchored"] is True

    # --- cyclical: Industrials sector, no defensive/quality overlay ---
    a_cy = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials")
    assert a_cy["key"] == "cyclical"

    # --- cyclical: Energy sector ---
    a_cy_e = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Energy")
    assert a_cy_e["key"] == "cyclical"

    # --- cyclical does NOT fire when quality compounder overlay present ---
    qc_fac = dict(base, quality=0.8, profitability=0.5)
    a_no_cy = SF._archetype(qc_fac, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials")
    assert a_no_cy["key"] != "cyclical", "quality overlay should block cyclical"


def test_archetype_v2_precedence_determinism():
    """Precedence is deterministic: multiple-match scenarios resolve to the highest-priority
    bucket, and calling twice returns the same result (no stochastic element)."""
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}

    # speculative_unprofitable beats financial (rule 1 > rule 3)
    a1 = SF._archetype(base, ni=-100.0, net_margin=-10.0, nm_top_thr=20.0, sector="Financials")
    assert a1["key"] == "speculative_unprofitable", \
        f"speculative_unprofitable should beat financial; got {a1['key']}"

    # financial beats rate_sensitive (rule 3 > rule 4)
    betas_rs = {"rates": 0.7, "raw": {"oil": 0.01}}
    a2 = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0,
                       sector="Financials", betas=betas_rs)
    assert a2["key"] == "financial", \
        f"financial should beat rate_sensitive; got {a2['key']}"

    # secular_growth beats cyclical (rule 6 > rule 8)
    my_sg = {"rev_cagr": 20.0, "eps_cagr": 15.0,
             "altman": {"z": 4.0, "zone": "safe", "approx": False}}
    a3 = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0,
                       sector="Industrials", my=my_sg)
    assert a3["key"] == "secular_growth", \
        f"secular_growth should beat cyclical; got {a3['key']}"

    # Determinism: calling twice gives same key
    a4a = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0,
                        sector="Industrials", my=my_sg)
    a4b = SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0,
                        sector="Industrials", my=my_sg)
    assert a4a["key"] == a4b["key"], "archetype is not deterministic"


def test_archetype_v2_anchored_flag():
    """anchored=True for all absolute-threshold v2 buckets; False for factor-z buckets."""
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}

    # v2 anchored buckets
    my_sg = {"rev_cagr": 20.0, "eps_cagr": 15.0, "altman": {"z": 4.0, "zone": "safe", "approx": False}}
    cases_anchored = [
        SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Financials"),       # financial
        SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials"),      # cyclical
        SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0, my=my_sg),                 # secular_growth
        SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0,
                      betas={"rates": 0.7, "raw": {"oil": 0.01}}),                                # rate_sensitive
    ]
    for a in cases_anchored:
        assert a["anchored"] is True, f"expected anchored=True for {a['key']}"

    # v1 factor-z buckets should have anchored=False
    cases_not_anchored = [
        SF._archetype(dict(base, quality=0.8, profitability=0.5), ni=10.0, net_margin=5.0, nm_top_thr=20.0),  # quality_compounder
        SF._archetype(dict(base, value=1.0), ni=10.0, net_margin=5.0, nm_top_thr=20.0),                       # deep_value
        SF._archetype(dict(base, payout=0.8, low_vol=0.6, low_beta=0.5), ni=10.0, net_margin=5.0, nm_top_thr=20.0),  # dividend_defensive
        SF._archetype(base, ni=10.0, net_margin=5.0, nm_top_thr=20.0),                                        # mixed
    ]
    for a in cases_not_anchored:
        assert a["anchored"] is False, f"expected anchored=False for {a['key']}, got {a['anchored']}"


def test_archetype_v2_known_compounder():
    """A known secular compounder profile: high quality, strong multi-year CAGR,
    above-threshold rev/eps growth. Should land in secular_growth (highest priority
    growth bucket, beats quality_compounder)."""
    # Profile: strong quality z-scores + secular CAGR above both thresholds
    fac = {"value": -0.2, "quality": 0.9, "profitability": 0.8,
           "payout": 0.1, "low_vol": 0.2, "low_beta": 0.1}
    my = {"rev_cagr": 22.0, "eps_cagr": 18.0,
          "altman": {"z": 4.5, "zone": "safe", "approx": False}}
    a = SF._archetype(fac, ni=500.0, net_margin=25.0, nm_top_thr=20.0, my=my)
    assert a["key"] == "secular_growth", \
        f"compounder with strong CAGR should be secular_growth, got {a['key']}"


def test_archetype_v2_known_bank():
    """A known bank (Financials sector). Should land in financial regardless of ratios
    (EDGAR inventory/gross_profit absent for banks)."""
    fac = {"value": 0.3, "quality": 0.4, "profitability": 0.5,
           "payout": 0.6, "low_vol": 0.3, "low_beta": 0.2}
    a = SF._archetype(fac, ni=1000.0, net_margin=20.0, nm_top_thr=15.0,
                      sector="Financials")
    assert a["key"] == "financial"
    assert a["anchored"] is True


def test_archetype_v2_known_distressed():
    """A known distressed name: Altman Z well below 1.81, non-approx, profitable."""
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.1,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    my = {"rev_cagr": 3.0, "eps_cagr": 1.0,
          "altman": {"z": 0.8, "zone": "distress", "approx": False}}
    a = SF._archetype(base, ni=50.0, net_margin=3.0, nm_top_thr=15.0, my=my)
    assert a["key"] == "distressed"
    assert a["anchored"] is True
    assert a["confidence"] > 0.0


def test_archetype_v2_taxonomy_completeness():
    """ARCHETYPE_TAXONOMY must equal ARCHETYPES and ARCHETYPE_PRECEDENCE must
    cover every key in ARCHETYPES exactly once."""
    assert SF.ARCHETYPE_TAXONOMY is SF.ARCHETYPES, "ARCHETYPE_TAXONOMY must alias ARCHETYPES"
    prec_keys = SF.ARCHETYPE_PRECEDENCE
    arch_keys = set(SF.ARCHETYPES.keys())
    assert set(prec_keys) == arch_keys, (
        f"ARCHETYPE_PRECEDENCE keys mismatch ARCHETYPES.\n"
        f"  extra in precedence: {set(prec_keys) - arch_keys}\n"
        f"  missing from precedence: {arch_keys - set(prec_keys)}"
    )
    assert len(prec_keys) == len(set(prec_keys)), "ARCHETYPE_PRECEDENCE has duplicate keys"


def test_archetype_precedence_cascade_order():
    """ARCHETYPE_PRECEDENCE is not just documentation — its order must match the
    actual first-match-wins cascade in _archetype(). This test constructs minimal
    fixtures that fire each overlapping bucket pair and asserts the higher-priority
    bucket wins, catching any divergence if the cascade is reordered without
    updating ARCHETYPE_PRECEDENCE (or vice versa).

    Pairs tested (higher priority listed first per ARCHETYPE_PRECEDENCE):
      1 > 2: speculative_unprofitable beats distressed
      1 > 3: speculative_unprofitable beats financial
      2 > 3: distressed beats financial
      3 > 4: financial beats rate_sensitive
      4 > 5: rate_sensitive beats commodity_sensitive
      5 > 6: commodity_sensitive beats secular_growth
      6 > 7: secular_growth beats broken_growth
      6 > 8: secular_growth beats cyclical
      7 > 8: broken_growth beats cyclical
      8 > 9: cyclical beats high_beta_momentum
    """
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}

    # (higher_priority, lower_priority, kwargs_that_fire_both)
    overlap_cases = [
        # 1 > 2: unprofitable veto fires even with Altman distress
        ("speculative_unprofitable", "distressed",
         dict(ni=-100.0, net_margin=-5.0, nm_top_thr=20.0,
              my={"rev_cagr": 2.0, "eps_cagr": 1.0,
                  "altman": {"z": 0.8, "zone": "distress", "approx": False}})),
        # 1 > 3: unprofitable fires even in Financials sector
        ("speculative_unprofitable", "financial",
         dict(ni=-100.0, net_margin=-5.0, nm_top_thr=20.0, sector="Financials")),
        # 2 > 3: distressed beats financial sector for a profitable bank
        ("distressed", "financial",
         dict(ni=50.0, net_margin=5.0, nm_top_thr=20.0, sector="Financials",
              my={"rev_cagr": 2.0, "eps_cagr": 1.0,
                  "altman": {"z": 0.8, "zone": "distress", "approx": False}})),
        # 3 > 4: financial sector wins over high rates beta
        ("financial", "rate_sensitive",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Financials",
              betas={"rates": 0.7, "raw": {"oil": 0.01}})),
        # 4 > 5: rates beta wins over oil beta when both exceed thresholds
        ("rate_sensitive", "commodity_sensitive",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0,
              betas={"rates": 0.55, "raw": {"oil": 0.50}})),
        # 5 > 6: oil beta wins over secular CAGR thresholds
        ("commodity_sensitive", "secular_growth",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0,
              my={"rev_cagr": 20.0, "eps_cagr": 15.0,
                  "altman": {"z": 4.0, "zone": "safe", "approx": False}},
              betas={"rates": 0.05, "raw": {"oil": 0.50}})),
        # 6 > 7: secular_growth wins over broken_growth (secular requires BOTH rev+eps high;
        #        broken requires rev high + eps<=0 — they cannot fire simultaneously, so
        #        we test secular_growth beats broken_growth via the eps floor)
        # NOTE: secular_growth and broken_growth are mutually exclusive by construction
        # (secular requires eps_cagr>=12, broken requires eps_cagr<=0), so instead verify
        # secular_growth beats cyclical (rule 6 > rule 8):
        ("secular_growth", "cyclical",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials",
              my={"rev_cagr": 20.0, "eps_cagr": 15.0,
                  "altman": {"z": 4.0, "zone": "safe", "approx": False}})),
        # 7 > 8: broken_growth beats cyclical
        ("broken_growth", "cyclical",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials",
              my={"rev_cagr": 12.0, "eps_cagr": -3.0,
                  "altman": {"z": 4.0, "zone": "safe", "approx": False}})),
        # 8 > 9: cyclical beats high_beta_momentum (cyclical sector + high beta)
        ("cyclical", "high_beta_momentum",
         dict(ni=10.0, net_margin=5.0, nm_top_thr=20.0, sector="Industrials",
              fac_override={"value": 0.0, "quality": 0.0, "profitability": 0.0,
                            "payout": 0.0, "low_vol": -0.6, "low_beta": -0.8})),
    ]

    for hi, lo, kwargs in overlap_cases:
        fac = kwargs.pop("fac_override", None) or base
        result = SF._archetype(fac, **kwargs)
        assert result is not None, f"_archetype returned None for {hi}>{lo} case"
        assert result["key"] == hi, (
            f"Precedence violation: expected '{hi}' to beat '{lo}', "
            f"got '{result['key']}' (ARCHETYPE_PRECEDENCE says {hi} has higher priority)"
        )

    # Also assert the cascade key order in ARCHETYPE_PRECEDENCE itself matches
    # the declared list exactly (guards against list mutation without test update).
    prec = SF.ARCHETYPE_PRECEDENCE
    expected_order = [
        "speculative_unprofitable", "distressed", "financial",
        "rate_sensitive", "commodity_sensitive",
        "secular_growth", "broken_growth", "cyclical",
        "high_beta_momentum", "dividend_defensive",
        "quality_compounder", "deep_value", "mixed",
    ]
    assert prec == expected_order, (
        f"ARCHETYPE_PRECEDENCE order mismatch.\n"
        f"  Expected: {expected_order}\n"
        f"  Got:      {prec}"
    )


def test_leverage_ratios_normal_case():
    """Normal: all fields present.  interest_coverage, net_debt, both debt ratios computed."""
    rows = [
        {
            "op_income": 100.0,
            "interest_exp": 10.0,
            "debt_lt": 200.0,
            "debt_cur": 50.0,
            "cash": 80.0,
            "depreciation": 20.0,
        }
    ]
    lev = SF._leverage_ratios(rows)
    # interest_coverage = 100 / 10 = 10.0
    assert lev["interest_coverage"] == 10.0, lev
    # net_debt = 200 + 50 - 80 = 170
    assert lev["net_debt"] == 170.0, lev
    # net_debt_to_op_income = 170 / 100 = 1.7
    assert lev["net_debt_to_op_income"] == 1.7, lev
    # net_debt_to_ebitda = 170 / (100 + 20) = 170 / 120 ≈ 1.42
    assert lev["net_debt_to_ebitda"] == round(170 / 120, 2), lev


def test_leverage_ratios_interest_exp_none():
    """interest_exp = None → interest_coverage absent."""
    rows = [
        {
            "op_income": 100.0,
            "interest_exp": None,
            "debt_lt": 200.0,
            "debt_cur": 0.0,
            "cash": 50.0,
            "depreciation": None,
        }
    ]
    lev = SF._leverage_ratios(rows)
    assert "interest_coverage" not in lev, lev
    # net_debt still computable: 200 + 0 - 50 = 150
    assert lev.get("net_debt") == 150.0, lev


def test_leverage_ratios_interest_exp_zero():
    """interest_exp = 0 → interest_coverage absent (division by zero guard)."""
    rows = [
        {
            "op_income": 100.0,
            "interest_exp": 0.0,
            "debt_lt": 100.0,
            "debt_cur": None,
            "cash": 20.0,
            "depreciation": None,
        }
    ]
    lev = SF._leverage_ratios(rows)
    assert "interest_coverage" not in lev, lev


def test_leverage_ratios_op_income_negative():
    """Negative op_income: interest_coverage can still compute; debt ratios absent."""
    rows = [
        {
            "op_income": -50.0,
            "interest_exp": 10.0,
            "debt_lt": 200.0,
            "debt_cur": None,
            "cash": 30.0,
            "depreciation": 15.0,
        }
    ]
    lev = SF._leverage_ratios(rows)
    # interest_coverage = -50 / 10 = -5.0 (still computable — interest_exp > 0)
    assert lev["interest_coverage"] == -5.0, lev
    # net_debt_to_op_income: op_income <= 0 → absent
    assert "net_debt_to_op_income" not in lev, lev
    # net_debt_to_ebitda: ebitda = -50 + 15 = -35 → denominator <= 0 → absent
    assert "net_debt_to_ebitda" not in lev, lev


def test_leverage_ratios_all_debt_fields_none():
    """All three debt-related fields are None → net_debt absent; no fabricated zero."""
    rows = [
        {
            "op_income": 80.0,
            "interest_exp": 8.0,
            "debt_lt": None,
            "debt_cur": None,
            "cash": None,
            "depreciation": 10.0,
        }
    ]
    lev = SF._leverage_ratios(rows)
    # net_debt not computable → all net_debt ratios absent
    assert "net_debt" not in lev, lev
    assert "net_debt_to_op_income" not in lev, lev
    assert "net_debt_to_ebitda" not in lev, lev
    # interest_coverage still computable
    assert lev["interest_coverage"] == 10.0, lev


def test_leverage_ratios_depreciation_absent():
    """Without depreciation, net_debt_to_ebitda is absent; proxy still present."""
    rows = [
        {
            "op_income": 60.0,
            "interest_exp": 5.0,
            "debt_lt": 150.0,
            "debt_cur": 0.0,
            "cash": 40.0,
            "depreciation": None,
        }
    ]
    lev = SF._leverage_ratios(rows)
    # net_debt = 150 + 0 - 40 = 110
    assert lev.get("net_debt") == 110.0, lev
    # net_debt_to_op_income = 110 / 60 ≈ 1.83
    assert lev.get("net_debt_to_op_income") == round(110 / 60, 2), lev
    # net_debt_to_ebitda: depreciation absent → not computed
    assert "net_debt_to_ebitda" not in lev, lev


def test_leverage_ratios_depreciation_present():
    """With depreciation present, net_debt_to_ebitda activates."""
    rows = [
        {
            "op_income": 60.0,
            "interest_exp": 5.0,
            "debt_lt": 150.0,
            "debt_cur": 0.0,
            "cash": 40.0,
            "depreciation": 20.0,
        }
    ]
    lev = SF._leverage_ratios(rows)
    net_debt = 110.0  # 150 + 0 - 40
    ebitda = 80.0     # 60 + 20
    assert lev.get("net_debt_to_ebitda") == round(net_debt / ebitda, 2), lev


def test_leverage_ratios_empty_rows():
    """Empty rows list → empty dict."""
    assert SF._leverage_ratios([]) == {}


def test_leverage_ratios_uses_latest_row():
    """Multi-row input: only the LATEST row is used (PIT-filtered by caller)."""
    rows = [
        # old row with very different values
        {"op_income": 10.0, "interest_exp": 1.0, "debt_lt": 50.0,
         "debt_cur": None, "cash": 10.0, "depreciation": None},
        # latest row
        {"op_income": 200.0, "interest_exp": 20.0, "debt_lt": 400.0,
         "debt_cur": 50.0, "cash": 100.0, "depreciation": None},
    ]
    lev = SF._leverage_ratios(rows)
    # Should use latest: interest_coverage = 200 / 20 = 10.0
    assert lev["interest_coverage"] == 10.0, lev
    # net_debt from latest: 400 + 50 - 100 = 350
    assert lev.get("net_debt") == 350.0, lev


def test_leverage_ratios_zero_cash_not_none():
    """Zero cash must NOT be treated as None (it IS a valid value)."""
    rows = [
        {
            "op_income": 50.0,
            "interest_exp": 5.0,
            "debt_lt": 100.0,
            "debt_cur": 0.0,
            "cash": 0.0,    # zero cash — valid, not missing
            "depreciation": None,
        }
    ]
    lev = SF._leverage_ratios(rows)
    # net_debt = 100 + 0 - 0 = 100 (not None)
    assert lev.get("net_debt") == 100.0, lev


def test_leverage_ratios_output_is_json_safe():
    """All outputs must be JSON-serializable (no NaN, no Infinity tokens)."""
    import json
    rows = [
        {
            "op_income": 100.0,
            "interest_exp": 10.0,
            "debt_lt": 200.0,
            "debt_cur": 50.0,
            "cash": 80.0,
            "depreciation": 20.0,
        }
    ]
    lev = SF._leverage_ratios(rows)
    s = json.dumps(lev)
    assert "NaN" not in s and "Infinity" not in s


# ---------------------------------------------------------------------------
# _load_statements() point-in-time gate (period_end + 120d; parity with #1572)
# ---------------------------------------------------------------------------

def _pit_stmt_frame(*, include_period_end=True, future_period_end="2099-06-30"):
    """3-row TST frame: two filed FYs (past period_end) + one not-yet-filed future
    FY. ``include_period_end=False`` drops the column entirely (legacy schema);
    ``future_period_end=None`` leaves the future row's period_end NaN (un-restamped
    legacy row)."""
    import pandas as pd
    rows = [
        {"ticker": "TST", "fy": 2023, "op_income": 20.0, "interest_exp": 2.0,
         "debt_lt": 40.0, "debt_cur": 10.0, "cash": 5.0, "period_end": "2023-06-30"},
        {"ticker": "TST", "fy": 2024, "op_income": 22.0, "interest_exp": 2.0,
         "debt_lt": 42.0, "debt_cur": 11.0, "cash": 6.0, "period_end": "2024-06-30"},
        {"ticker": "TST", "fy": 2099, "op_income": 500.0, "interest_exp": 2.0,
         "debt_lt": 99.0, "debt_cur": 9.0, "cash": 1.0, "period_end": future_period_end},
    ]
    df = pd.DataFrame(rows)
    if not include_period_end:
        df = df.drop(columns=["period_end"])
    return df


def _load_statements_with(df):
    """Run SF._load_statements() against a temp statements.parquet built from df,
    with SF.config.data_dir patched to the temp dir (restored afterwards)."""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "edgar").mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp / "edgar" / "statements.parquet")
        orig = SF.config.data_dir
        SF.config.data_dir = lambda: tmp
        try:
            return SF._load_statements()
        finally:
            SF.config.data_dir = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_statements_drops_not_yet_filed_fy():
    """A future fiscal row whose availability date (period_end + 120d) is after today
    is dropped, so latest-row consumers never see a not-yet-filed FY (the #1572 leak
    for statements.parquet — e.g. the FY2027 STX row)."""
    out = _load_statements_with(_pit_stmt_frame())
    yrs = [r["fy"] for r in out["TST"]]
    assert yrs == [2023, 2024], yrs
    # end-to-end: _leverage_ratios now reads fy2024 (net_debt 42+11-6=47),
    # NOT the gated fy2099 row (99+9-1=107).
    lev = SF._leverage_ratios(out["TST"])
    assert lev["net_debt"] == 47.0, lev


def test_load_statements_failopen_when_no_period_end_column():
    """Legacy schema without a period_end column cannot be gated — every row is KEPT
    (fail-open) so the panel is not blanked before the re-fetch re-stamps period_end."""
    out = _load_statements_with(_pit_stmt_frame(include_period_end=False))
    yrs = [r["fy"] for r in out["TST"]]
    assert yrs == [2023, 2024, 2099], yrs


def test_load_statements_failopen_on_nan_period_end():
    """A row with period_end NaN (legacy row not yet re-fetched) cannot be gated and
    is KEPT — the gate self-activates only once period_end is stamped."""
    out = _load_statements_with(_pit_stmt_frame(future_period_end=None))
    yrs = [r["fy"] for r in out["TST"]]
    assert yrs == [2023, 2024, 2099], yrs


# ---------------------------------------------------------------------------
# W2 PR-I — _compounders() tests
# ---------------------------------------------------------------------------

# Fixture: 6 years of clean data covering all computable features.
# Values chosen to be simple round numbers so expected outputs can be
# verified by hand.
_COMP_ROWS = [
    # fy, revenue, ni, gross_profit, cfo, capex, op_income,
    #     equity, debt_lt, debt_cur, cash, assets, depreciation
    {"fy": 2019, "revenue": 1000.0, "ni": 100.0, "gross_profit": 400.0,
     "cfo": 150.0, "capex": 50.0, "op_income": 130.0,
     "equity": 500.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 100.0,
     "assets": 900.0, "depreciation": None},
    {"fy": 2020, "revenue": 1100.0, "ni": 110.0, "gross_profit": 450.0,
     "cfo": 160.0, "capex": 55.0, "op_income": 140.0,
     "equity": 520.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 110.0,
     "assets": 950.0, "depreciation": None},
    {"fy": 2021, "revenue": 1250.0, "ni": 130.0, "gross_profit": 520.0,
     "cfo": 180.0, "capex": 60.0, "op_income": 160.0,
     "equity": 560.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 120.0,
     "assets": 1000.0, "depreciation": None},
    {"fy": 2022, "revenue": 1400.0, "ni": 150.0, "gross_profit": 590.0,
     "cfo": 200.0, "capex": 65.0, "op_income": 180.0,
     "equity": 600.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 130.0,
     "assets": 1050.0, "depreciation": None},
    {"fy": 2023, "revenue": 1600.0, "ni": 170.0, "gross_profit": 680.0,
     "cfo": 220.0, "capex": 70.0, "op_income": 200.0,
     "equity": 650.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 140.0,
     "assets": 1100.0, "depreciation": None},
    {"fy": 2024, "revenue": 1800.0, "ni": 190.0, "gross_profit": 780.0,
     "cfo": 240.0, "capex": 75.0, "op_income": 225.0,
     "equity": 700.0, "debt_lt": 200.0, "debt_cur": 50.0, "cash": 150.0,
     "assets": 1150.0, "depreciation": None},
]


def test_compounders_keys_present():
    """All expected computable feature keys appear for a full fixture."""
    c = SF._compounders(_COMP_ROWS)
    # Core keys
    assert "roic_series"       in c, c.keys()
    assert "roic_5y_median"    in c, c.keys()
    assert "roic_5y_stability" in c, c.keys()
    assert "gross_margin_5y_stability" in c, c.keys()
    assert "fcf_conversion"    in c, c.keys()
    assert "reinvestment_rate" in c, c.keys()
    assert "incremental_rev_per_reinvestment" in c, c.keys()
    assert "asset_light_scaling" in c, c.keys()
    # Firewall annotations
    assert c["_horizon_role"] == "hold_thesis"
    assert c["_display_only"] is True
    assert "21%" in c["_tax_assumption"]


def test_compounders_roic_value():
    """ROIC proxy is computed correctly for a single row.

    Row 0: op_income=130, tax=21%, equity=500, debt_lt=200, debt_cur=50, cash=100
    invested_capital = 500 + 200 + 50 - 100 = 650
    ROIC = 130 * (1 - 0.21) / 650 * 100 = 102.7 / 650 * 100 ≈ 15.8%
    """
    rows = [_COMP_ROWS[0]]
    c = SF._compounders(rows)
    assert c.get("roic_series") is not None
    assert abs(c["roic_series"][0] - 130 * 0.79 / 650 * 100) < 0.1, c["roic_series"]


def test_compounders_fcf_conversion():
    """FCF conversion = (CFO - capex) / NI for the latest row.

    Latest row: cfo=240, capex=75, ni=190
    FCF = 165, FCF/NI = 165/190 ≈ 0.868
    """
    c = SF._compounders(_COMP_ROWS)
    assert c["fcf_conversion"] is not None
    assert abs(c["fcf_conversion"] - (240 - 75) / 190) < 0.01, c["fcf_conversion"]


def test_compounders_reinvestment_rate():
    """Reinvestment rate = capex / CFO for latest row.

    Latest row: capex=75, cfo=240 → 75/240 = 0.3125
    """
    c = SF._compounders(_COMP_ROWS)
    assert c["reinvestment_rate"] is not None
    assert abs(c["reinvestment_rate"] - 75 / 240) < 0.01, c["reinvestment_rate"]


def test_compounders_incremental_rev():
    """Incremental revenue per reinvestment dollar (sum Δrev / sum capex).

    Δrev: 100+150+150+200+200 = 800
    capex years 1..5: 55+60+65+70+75 = 325
    800 / 325 ≈ 2.462
    """
    c = SF._compounders(_COMP_ROWS)
    assert c.get("incremental_rev_per_reinvestment") is not None
    delta_rev   = 1100 - 1000 + (1250 - 1100) + (1400 - 1250) + (1600 - 1400) + (1800 - 1600)
    total_capex = 55 + 60 + 65 + 70 + 75
    expected = delta_rev / total_capex
    assert abs(c["incremental_rev_per_reinvestment"] - expected) < 0.01, c


def test_compounders_asset_light_scaling():
    """asset_light_scaling spread = rev_cagr - asset_cagr."""
    c = SF._compounders(_COMP_ROWS)
    s = c.get("asset_light_scaling")
    assert s is not None, "asset_light_scaling missing"
    assert "rev_cagr_pct"   in s
    assert "asset_cagr_pct" in s
    assert "spread_pct"     in s
    assert abs(s["spread_pct"] - (s["rev_cagr_pct"] - s["asset_cagr_pct"])) < 0.01, s


def test_compounders_cov_stamps():
    """Every feature has a paired _cov stamp that is in [0, 1]."""
    c = SF._compounders(_COMP_ROWS)
    cov_keys = [k for k in c if k.endswith("_cov")]
    assert len(cov_keys) > 0, "no _cov stamps found"
    for k in cov_keys:
        v = c[k]
        assert isinstance(v, (int, float)), f"{k}={v} not numeric"
        assert 0.0 <= v <= 1.0, f"{k}={v} out of range [0,1]"


def test_compounders_empty_rows():
    """Empty rows → empty dict (not None, not crash)."""
    c = SF._compounders([])
    assert isinstance(c, dict)
    assert len(c) == 0


def test_compounders_all_none_inputs():
    """All None inputs → no feature keys computed; no crash."""
    rows = [{"fy": 2024, "revenue": None, "ni": None, "gross_profit": None,
             "cfo": None, "capex": None, "op_income": None, "equity": None,
             "debt_lt": None, "debt_cur": None, "cash": None, "assets": None,
             "depreciation": None}]
    c = SF._compounders(rows)
    assert isinstance(c, dict)
    # firewall annotations should still be present
    assert c.get("_horizon_role") == "hold_thesis"
    # no numeric feature keys should be computable
    numeric_keys = {"roic_series", "roic_5y_median", "roic_5y_stability",
                    "gross_margin_5y_stability", "fcf_conversion", "reinvestment_rate",
                    "incremental_rev_per_reinvestment", "asset_light_scaling"}
    for k in numeric_keys:
        assert k not in c, f"unexpected key {k} in all-None rows"


def test_compounders_depreciation_blocked():
    """When all depreciation values are None, blocked_pending_backfill is stamped."""
    c = SF._compounders(_COMP_ROWS)   # fixture has depreciation=None in all rows
    assert c.get("depreciation_gated_blocked") is True
    assert "blocked_pending_backfill" in c.get("depreciation_gated_note", "")


def test_compounders_depreciation_present():
    """When depreciation is present (>=5% cov), blocked_pending_backfill absent."""
    rows_with_dep = [dict(r, depreciation=20.0) for r in _COMP_ROWS]
    c = SF._compounders(rows_with_dep)
    assert "depreciation_gated_blocked" not in c, \
        "should NOT be blocked when depreciation data present"


def test_compounders_ni_zero_no_fcf_conv():
    """NI=0 rows are skipped for FCF conversion; latest non-zero NI row is used."""
    rows = [
        {"fy": 2022, "revenue": 1000.0, "ni": 0.0, "gross_profit": 400.0,
         "cfo": 150.0, "capex": 50.0, "op_income": 0.0,
         "equity": 500.0, "debt_lt": 200.0, "debt_cur": 0.0, "cash": 100.0,
         "assets": 900.0, "depreciation": None},
        {"fy": 2023, "revenue": 1100.0, "ni": 0.0, "gross_profit": 440.0,
         "cfo": 160.0, "capex": 60.0, "op_income": 0.0,
         "equity": 520.0, "debt_lt": 200.0, "debt_cur": 0.0, "cash": 110.0,
         "assets": 950.0, "depreciation": None},
    ]
    c = SF._compounders(rows)
    # Both NI=0 so fcf_conversion should be absent
    assert "fcf_conversion" not in c, c


def test_compounders_json_safe():
    """Output must be JSON-serializable with no NaN/Infinity tokens."""
    c = SF._compounders(_COMP_ROWS)
    cleaned = SF._clean(c)
    s = json.dumps(cleaned)
    assert "NaN" not in s and "Infinity" not in s


def test_multiyear_includes_compounder():
    """_multiyear() must embed a non-empty compounder sub-dict."""
    my = SF._multiyear(_COMP_ROWS, mktcap=5000.0)
    assert my is not None
    comp = my.get("compounder")
    assert isinstance(comp, dict), "compounder key missing or wrong type"
    assert comp.get("_horizon_role") == "hold_thesis"
    # Ensure the enclosing structure stays JSON-safe
    s = json.dumps(SF._clean(my))
    assert "NaN" not in s and "Infinity" not in s


def test_net_debt_helper():
    """Shared _net_debt: total debt − cash&equiv, computed only when at least one
    component is present (0 is a valid value; all-missing → None, never zero)."""
    assert SF._net_debt({"debt_lt": 200.0, "debt_cur": 50.0, "cash": 80.0}) == 170.0
    # zero cash is a valid value, not "missing": 100 + 0 - 0 = 100
    assert SF._net_debt({"debt_lt": 100.0, "debt_cur": 0.0, "cash": 0.0}) == 100.0
    # partial (only cash present) → net cash −40
    assert SF._net_debt({"cash": 40.0}) == -40.0
    # all three missing → None (never fabricate a zero net-debt)
    assert SF._net_debt({}) is None
    assert SF._net_debt({"debt_lt": None, "debt_cur": None, "cash": None}) is None


def test_net_debt_parity_with_leverage_panel():
    """The whole point of the shared helper: EV multiples and the leverage panel must
    report the SAME net_debt (they cannot be allowed to diverge)."""
    stmt = {"op_income": 100.0, "interest_exp": 10.0, "debt_lt": 400.0,
            "debt_cur": 50.0, "cash": 100.0, "depreciation": 20.0}
    lev = SF._leverage_ratios([stmt])
    assert lev["net_debt"] == round(SF._net_debt(stmt), 0) == 350.0


def _mk_fund(rows: dict):
    import pandas as pd
    return pd.DataFrame.from_dict(rows, orient="index")


def _ev_frame():
    """Tiny synthetic universe exercising every EV-multiple branch."""
    base_row = {"ni": 5e9, "equity": 5e10, "revenue": 2e10, "cfo": 8e9,
                "dividends": 0.0, "repurchases": 1e9}
    fund = _mk_fund({"GOOD": dict(base_row), "BANK": dict(base_row),
                     "NOSTMT": dict(base_row),
                     "LOSS": {"ni": -1e9, "equity": 5e10, "revenue": 2e10,
                              "cfo": -3e9, "dividends": 0.0, "repurchases": 0.0}})
    table = {
        "GOOD":   {"mktcap_bn": 100.0, "sector": "Information Technology", "composite": 0.5},
        "BANK":   {"mktcap_bn": 100.0, "sector": "Financials", "composite": 0.4},
        "NOSTMT": {"mktcap_bn": 100.0, "sector": "Health Care", "composite": 0.3},
        "LOSS":   {"mktcap_bn": 50.0,  "sector": "Industrials", "composite": 0.2},
    }
    good_stmt = {"op_income": 6e9, "capex": 2e9, "cfo": 8e9, "revenue": 2e10,
                 "debt_lt": 1e10, "debt_cur": 2e9, "cash": 5e9}
    statements = {
        "GOOD": [dict(good_stmt)],
        "BANK": [dict(good_stmt)],
        # NOSTMT intentionally has no statement row
        "LOSS": [{"op_income": -2e9, "capex": 1e9, "cfo": -3e9, "revenue": 2e10,
                  "debt_lt": 1e10, "debt_cur": 0.0, "cash": 1e9}],
    }
    return fund, table, statements


def test_context_frame_ev_multiples():
    """EV = mktcap + net_debt; ev_sales/ev_ebit off the statement layer; P/FCF is TRUE
    post-capex FCF (cfo − capex), not the pre-capex proxy."""
    fund, table, statements = _ev_frame()
    M = SF._context_frame(fund, table, statements)
    g = M.loc["GOOD"]
    # net_debt = 1e10 + 2e9 − 5e9 = 7e9 ; ev = 1e11 + 7e9 = 1.07e11
    assert abs(g["ev_sales"] - (1.07e11 / 2e10)) < 1e-6, g["ev_sales"]   # 5.35
    assert abs(g["ev_ebit"] - (1.07e11 / 6e9)) < 1e-6, g["ev_ebit"]      # 17.83
    assert abs(g["p_fcf"] - (1e11 / (8e9 - 2e9))) < 1e-6, g["p_fcf"]     # 16.67


def test_context_frame_ev_financial_suppressed():
    """Financials: enterprise ratios are meaningless (bank balance sheets) → all NaN,
    but the equity-based P/B is still computed."""
    fund, table, statements = _ev_frame()
    M = SF._context_frame(fund, table, statements)
    b = M.loc["BANK"]
    assert math.isnan(b["ev_sales"]) and math.isnan(b["ev_ebit"]) and math.isnan(b["p_fcf"])
    assert not math.isnan(b["pb"])


def test_context_frame_ev_missing_statement():
    """No statement row → no net_debt → no EV → all three NaN; cross-section P/S intact."""
    fund, table, statements = _ev_frame()
    M = SF._context_frame(fund, table, statements)
    n = M.loc["NOSTMT"]
    assert math.isnan(n["ev_sales"]) and math.isnan(n["ev_ebit"]) and math.isnan(n["p_fcf"])
    assert not math.isnan(n["ps"])


def test_context_frame_ev_negative_denominators():
    """Negative EBIT → ev_ebit NaN; negative FCF → p_fcf NaN; ev_sales still valid
    (revenue > 0), following the same explicit >0 guard the other multiples use."""
    fund, table, statements = _ev_frame()
    M = SF._context_frame(fund, table, statements)
    lo = M.loc["LOSS"]
    assert math.isnan(lo["ev_ebit"]), lo["ev_ebit"]
    assert math.isnan(lo["p_fcf"]), lo["p_fcf"]
    assert not math.isnan(lo["ev_sales"]), lo["ev_sales"]


def test_valuation_ev_cells_json_safe():
    """_valuation exposes the three EV cells; suppressed/missing names get a clean None
    (not a NaN token), and the block serializes JSON-safe."""
    fund, table, statements = _ev_frame()
    M = SF._context_frame(fund, table, statements)
    good = SF._valuation("GOOD", fund.loc["GOOD"], table["GOOD"], M, None)
    assert good["ev_to_sales"]["v"] is not None
    assert good["ev_to_ebit"]["v"] is not None
    assert good["price_to_fcf"]["v"] is not None
    bank = SF._valuation("BANK", fund.loc["BANK"], table["BANK"], M, None)
    assert bank["ev_to_sales"] is None and bank["ev_to_ebit"] is None and bank["price_to_fcf"] is None
    s = json.dumps(SF._clean({"good": good, "bank": bank}))
    assert "NaN" not in s and "Infinity" not in s


# ---------------------------------------------------------------------------
# Tier-1 metrics tests (Panel A: ev_ebitda, fcf_yield_true; Panel B: op_margin,
# gp_assets, roce, rd_sales; Panel C: current_ratio, quick_ratio)
# ---------------------------------------------------------------------------

def _tier1_ev_frame():
    """Extend the _ev_frame() fixture to cover ev_ebitda and fcf_yield_true.

    GOOD: has op_income + depreciation → ebitda computable; FCF = cfo − capex.
    BANK: Financials sector → ev_ebitda and fcf_yield_true suppressed.
    NODEP: missing depreciation → ev_ebitda NaN, fcf_yield_true still works.
    """
    import pandas as pd
    base_row = {"ni": 5e9, "equity": 5e10, "revenue": 2e10, "cfo": 8e9,
                "dividends": 0.0, "repurchases": 1e9}
    fund = pd.DataFrame.from_dict(
        {"GOOD": dict(base_row), "BANK": dict(base_row), "NODEP": dict(base_row)},
        orient="index",
    )
    table = {
        "GOOD": {"mktcap_bn": 100.0, "sector": "Information Technology", "composite": 0.5},
        "BANK": {"mktcap_bn": 100.0, "sector": "Financials", "composite": 0.4},
        "NODEP": {"mktcap_bn": 100.0, "sector": "Health Care", "composite": 0.3},
    }
    good_stmt = {
        "op_income": 6e9, "capex": 2e9, "cfo": 8e9, "revenue": 2e10,
        "debt_lt": 1e10, "debt_cur": 2e9, "cash": 5e9,
        "depreciation": 1e9,   # ebitda = 6e9 + 1e9 = 7e9; ev_ebitda = 1.07e11 / 7e9
    }
    nodep_stmt = {
        "op_income": 6e9, "capex": 2e9, "cfo": 8e9, "revenue": 2e10,
        "debt_lt": 1e10, "debt_cur": 2e9, "cash": 5e9,
        "depreciation": None,   # no D&A → ev_ebitda NaN
    }
    statements = {
        "GOOD":  [dict(good_stmt)],
        "BANK":  [dict(good_stmt)],
        "NODEP": [dict(nodep_stmt)],
    }
    return fund, table, statements


def test_context_frame_ev_ebitda_correct():
    """ev_ebitda = EV / (op_income + depreciation); numerically correct."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    g = M.loc["GOOD"]
    # net_debt = 1e10 + 2e9 − 5e9 = 7e9; ev = 1e11 + 7e9 = 1.07e11
    # ebitda = 6e9 + 1e9 = 7e9; ev_ebitda = 1.07e11 / 7e9 ≈ 15.286
    expected = 1.07e11 / 7e9
    assert abs(g["ev_ebitda"] - expected) < 1e-6, g["ev_ebitda"]


def test_context_frame_ev_ebitda_no_depreciation():
    """Missing depreciation → ev_ebitda NaN; ev_ebit still computes."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    nd = M.loc["NODEP"]
    assert math.isnan(nd["ev_ebitda"]), nd["ev_ebitda"]
    assert not math.isnan(nd["ev_ebit"]), nd["ev_ebit"]


def test_context_frame_ev_ebitda_financial_suppressed():
    """Financials sector → ev_ebitda NaN (bank balance sheets make it noise)."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    b = M.loc["BANK"]
    assert math.isnan(b["ev_ebitda"]), b["ev_ebitda"]


def test_context_frame_fcf_yield_true_correct():
    """fcf_yield_true = (cfo − capex) / mktcap × 100; higher-is-better."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    g = M.loc["GOOD"]
    # fcf = 8e9 − 2e9 = 6e9; mktcap = 1e11; yield = 6e9/1e11 * 100 = 6.0
    assert abs(g["fcf_yield_true"] - 6.0) < 1e-6, g["fcf_yield_true"]


def test_context_frame_fcf_yield_true_financial_suppressed():
    """Financials sector → fcf_yield_true NaN."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    b = M.loc["BANK"]
    assert math.isnan(b["fcf_yield_true"]), b["fcf_yield_true"]


def test_valuation_ev_ebitda_and_fcf_yield_true_cells():
    """_valuation() exposes ev_to_ebitda and fcf_yield_true cells; Financials → None."""
    fund, table, statements = _tier1_ev_frame()
    M = SF._context_frame(fund, table, statements)
    good = SF._valuation("GOOD", fund.loc["GOOD"], table["GOOD"], M, None)
    assert good["ev_to_ebitda"] is not None, "ev_to_ebitda missing for GOOD"
    assert good["fcf_yield_true"] is not None, "fcf_yield_true missing for GOOD"
    bank = SF._valuation("BANK", fund.loc["BANK"], table["BANK"], M, None)
    assert bank["ev_to_ebitda"] is None, "ev_to_ebitda must be None for Financials"
    assert bank["fcf_yield_true"] is None, "fcf_yield_true must be None for Financials"
    s = json.dumps(SF._clean({"good": good, "bank": bank}))
    assert "NaN" not in s and "Infinity" not in s


def _mk_fin_row():
    """Synthetic cross-section fund row for _financials() tests."""
    import pandas as pd
    return pd.Series({
        "revenue": 2e10, "ni": 2e9, "ni_prior": 1.8e9,
        "equity": 1e10, "cfo": 3e9, "gross_profit": 8e9,
        "assets": 5e10, "assets_prior": 4.5e10,
        "debt_lt": 1e10, "shares": 1e9,
        "dividends": 5e8, "repurchases": 2e8,
    })


def _mk_stmt(**kw):
    """Synthetic latest statement row for the financials stmt param."""
    base = {
        "op_income": 2.5e9, "revenue": 2e10, "assets": 5e10,
        "cur_liab": 5e9, "gross_profit": 8e9, "research_dev": 1e9,
    }
    base.update(kw)
    return base


def test_financials_op_margin_correct():
    """op_margin = op_income / revenue × 100, rounded to 1 d.p."""
    f = _mk_fin_row()
    s = _mk_stmt(op_income=2.5e9, revenue=2e10)
    fin = SF._financials("TEST", f, None, stmt=s)
    # 2.5e9 / 2e10 * 100 = 12.5
    assert fin["op_margin"] == 12.5, fin["op_margin"]


def test_financials_op_margin_missing_stmt():
    """No stmt → op_margin is None (not 0, not crash)."""
    f = _mk_fin_row()
    fin = SF._financials("TEST", f, None, stmt=None)
    assert fin.get("op_margin") is None


def test_financials_op_margin_zero_revenue():
    """Zero revenue denominator → op_margin is None (not divide-by-zero)."""
    f = _mk_fin_row()
    s = _mk_stmt(op_income=1e9, revenue=0.0)
    fin = SF._financials("TEST", f, None, stmt=s)
    assert fin.get("op_margin") is None


def test_financials_gp_assets_correct():
    """gp_assets = gross_profit / assets; non-Financials."""
    f = _mk_fin_row()
    s = _mk_stmt(gross_profit=8e9, assets=5e10)
    fin = SF._financials("TEST", f, None, stmt=s, sector="Information Technology")
    # 8e9 / 5e10 = 0.16
    assert fin["gp_assets"] == round(8e9 / 5e10, 3), fin["gp_assets"]


def test_financials_gp_assets_financial_suppressed():
    """gp_assets is None for Financials sector (bank assets misleading)."""
    f = _mk_fin_row()
    s = _mk_stmt(gross_profit=8e9, assets=5e10)
    fin = SF._financials("TEST", f, None, stmt=s, sector="Financials")
    assert fin.get("gp_assets") is None


def test_financials_gp_assets_missing_assets():
    """Missing assets → gp_assets is None."""
    f = _mk_fin_row()
    s = _mk_stmt(gross_profit=8e9, assets=None)
    fin = SF._financials("TEST", f, None, stmt=s)
    assert fin.get("gp_assets") is None


def test_financials_roce_correct():
    """roce = op_income / (assets − cur_liab) × 100; capital employed > 0."""
    f = _mk_fin_row()
    s = _mk_stmt(op_income=2.5e9, assets=5e10, cur_liab=5e9)
    fin = SF._financials("TEST", f, None, stmt=s, sector="Information Technology")
    # cap_employed = 5e10 − 5e9 = 4.5e10; roce = 2.5e9/4.5e10 * 100 ≈ 5.556
    expected = round(2.5e9 / (5e10 - 5e9) * 100, 1)
    assert fin["roce"] == expected, fin["roce"]


def test_financials_roce_financial_suppressed():
    """roce is None for Financials sector."""
    f = _mk_fin_row()
    s = _mk_stmt(op_income=2.5e9, assets=5e10, cur_liab=5e9)
    fin = SF._financials("TEST", f, None, stmt=s, sector="Financials")
    assert fin.get("roce") is None


def test_financials_roce_negative_capital_employed():
    """cur_liab > assets → cap_employed ≤ 0 → roce is None."""
    f = _mk_fin_row()
    s = _mk_stmt(op_income=2.5e9, assets=5e9, cur_liab=1e10)  # assets < cur_liab
    fin = SF._financials("TEST", f, None, stmt=s)
    assert fin.get("roce") is None


def test_financials_rd_sales_present():
    """rd_sales = research_dev / revenue × 100 when both present."""
    f = _mk_fin_row()
    s = _mk_stmt(research_dev=1e9, revenue=2e10)
    fin = SF._financials("TEST", f, None, stmt=s)
    # 1e9 / 2e10 * 100 = 5.0
    assert fin["rd_sales"] == 5.0, fin["rd_sales"]


def test_financials_rd_sales_absent_when_no_rd():
    """rd_sales is None (not 0) when research_dev is absent."""
    f = _mk_fin_row()
    s = _mk_stmt(research_dev=None, revenue=2e10)
    fin = SF._financials("TEST", f, None, stmt=s)
    assert fin.get("rd_sales") is None


def test_financials_tier1_json_safe():
    """The four new financials keys must serialize without NaN/Infinity tokens."""
    f = _mk_fin_row()
    s = _mk_stmt()
    fin = SF._financials("TEST", f, None, stmt=s, sector="Information Technology")
    cleaned = SF._clean(fin)
    text = json.dumps(cleaned)
    assert "NaN" not in text and "Infinity" not in text


def test_leverage_current_and_quick_correct():
    """current_ratio = cur_assets / cur_liab; quick_ratio = (cur_assets − inv) / cur_liab."""
    rows = [{
        "op_income": 100.0, "interest_exp": 10.0,
        "cur_assets": 300.0, "cur_liab": 150.0, "inventory": 60.0,
    }]
    lev = SF._leverage_ratios(rows)
    assert lev["current_ratio"] == round(300.0 / 150.0, 2)          # 2.0
    assert lev["quick_ratio"]   == round((300.0 - 60.0) / 150.0, 2) # 1.6


def test_leverage_current_ratio_no_inventory():
    """inventory absent → treat as 0 for quick_ratio (cur_assets is present)."""
    rows = [{"cur_assets": 200.0, "cur_liab": 100.0, "inventory": None}]
    lev = SF._leverage_ratios(rows)
    assert lev["current_ratio"] == 2.0
    assert lev["quick_ratio"]   == 2.0   # inventory treated as 0


def test_leverage_current_quick_financial_suppressed():
    """current_ratio and quick_ratio absent for Financials sector."""
    rows = [{
        "cur_assets": 300.0, "cur_liab": 150.0, "inventory": 60.0,
    }]
    lev = SF._leverage_ratios(rows, sector="Financials")
    assert "current_ratio" not in lev, lev
    assert "quick_ratio" not in lev, lev


def test_leverage_current_ratio_zero_denominator():
    """cur_liab == 0 → neither ratio computed (division by zero guard)."""
    rows = [{"cur_assets": 300.0, "cur_liab": 0.0, "inventory": 50.0}]
    lev = SF._leverage_ratios(rows)
    assert "current_ratio" not in lev, lev
    assert "quick_ratio" not in lev, lev


def test_leverage_current_ratio_missing_inputs():
    """cur_assets or cur_liab None → neither ratio computed."""
    lev_no_ca = SF._leverage_ratios([{"cur_assets": None, "cur_liab": 100.0}])
    assert "current_ratio" not in lev_no_ca

    lev_no_cl = SF._leverage_ratios([{"cur_assets": 200.0, "cur_liab": None}])
    assert "current_ratio" not in lev_no_cl


def test_leverage_tier1_json_safe():
    """current_ratio and quick_ratio must serialize without NaN/Infinity tokens."""
    rows = [{
        "op_income": 100.0, "interest_exp": 10.0,
        "debt_lt": 200.0, "debt_cur": 50.0, "cash": 80.0,
        "cur_assets": 300.0, "cur_liab": 150.0, "inventory": 60.0,
        "depreciation": 20.0,
    }]
    lev = SF._leverage_ratios(rows, sector="Information Technology")
    s = json.dumps(lev)
    assert "NaN" not in s and "Infinity" not in s


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run())
