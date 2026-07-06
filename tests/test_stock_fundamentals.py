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
    # W2 PR-J adds thesis_clock; W2 PR-K adds moat_falsifiers + great_company_trap
    assert set(sample).issubset({"profile", "valuation", "financials",
                                 "factors", "positioning", "analyst", "earnings",
                                 "accounting_quality", "leverage_ratios",
                                 "thesis_clock", "moat_falsifiers", "great_company_trap"})
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
