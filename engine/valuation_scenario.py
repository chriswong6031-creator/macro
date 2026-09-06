"""Pure valuation-scenario calculator (V1) -- FROZEN SPEC B-F07-1.

No IO, no network, no clock. Consumes already-loaded per-fiscal-year
statement rows (engine.stock_fundamentals._load_statements() shape) and
emits the valuation_scenario.v1 blob for exactly one pinned issuer.

Frozen formula (spec section 2):
  per_share = ((net_income * (1 + sales_growth_pct/100)
                * (1 + (margin_delta_pp/100) / net_margin_base))
               * earnings_multiple - net_debt) / share_count

net_margin_base = net_income / revenue for the SAME fiscal row.

net_debt = debt_lt + debt_cur - cash, computed ONLY when all three legs are
reported (None otherwise). This is deliberately stricter than the shared
identity in engine/stock_fundamentals._net_debt (which defaults a missing
leg to 0) -- this module is re-implemented rather than imported, and the
contract here is "null means not reported, never imputed" with no exception.

Forbidden by construction: no consensus, no estimates, no price targets, no
probability/confidence wording, no LLM-authored numbers, no ranking/score.
"""
from __future__ import annotations

# (key, sales_growth_pct, margin_delta_pp, earnings_multiple)
SCENARIOS = (
    ("cautious", -2, -1.5, 14),
    ("base", 3, 0, 18),
    ("upbeat", 7, 1.5, 22),
)


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _field(value, unit, period, reported, **extra):
    d = {"value": value, "unit": unit, "period": period, "reported": reported}
    d.update(extra)
    return d


def compute(rows: list[dict], price: float | None = None, asof: str | None = None,
            ticker: str = "") -> dict | None:
    if not rows:
        return None
    dated = [r for r in rows if r.get("fy") is not None and r.get("period_end")]
    if not dated:
        return None
    latest = max(dated, key=lambda r: r["fy"])
    fy = latest["fy"]
    period_end = latest["period_end"]

    revenue = _num(latest.get("revenue"))
    op_income = _num(latest.get("op_income"))
    net_income = _num(latest.get("net_income"))
    cash = _num(latest.get("cash"))
    debt_lt = _num(latest.get("debt_lt"))
    debt_cur = _num(latest.get("debt_cur"))
    shares = _num(latest.get("shares"))
    share_identity = latest.get("share_identity") or "outstanding"

    # Defensive period/unit consistency: every base input must belong to the
    # SAME fiscal row. A fixture may declare an explicit "<field>_fy" override
    # to simulate a mixed-period assembly; a mismatch there fails the whole
    # section rather than silently mixing fiscal years.
    consistent = True
    for k in ("revenue_fy", "op_income_fy", "net_income_fy", "cash_fy",
              "debt_lt_fy", "debt_cur_fy", "shares_fy"):
        v = latest.get(k)
        if v is not None and v != fy:
            consistent = False

    net_debt = None
    if debt_lt is not None and debt_cur is not None and cash is not None:
        net_debt = debt_lt + debt_cur - cash

    base = {
        "revenue": _field(revenue, "USD", f"FY{fy}", revenue is not None),
        "op_income": _field(op_income, "USD", f"FY{fy}", op_income is not None),
        "net_income": _field(net_income, "USD", f"FY{fy}", net_income is not None),
        "share_count": _field(shares, "shares", f"FY{fy}", shares is not None,
                               identity=share_identity),
        "net_debt": _field(
            net_debt, "USD", f"FY{fy}", net_debt is not None,
            sign=("net_cash" if (net_debt is not None and net_debt < 0) else "net_debt"),
        ),
    }

    net_margin_base = None
    if net_income is not None and revenue not in (None, 0):
        net_margin_base = net_income / revenue

    scenarios = []
    any_computable = False
    for key, g, m_pp, mult in SCENARIOS:
        missing: list[str] = []
        if not consistent:
            missing.append("consistent period")
        if net_income is None:
            missing.append("net_income")
        if revenue is None:
            missing.append("revenue")
        elif net_income is not None and net_margin_base is None:
            missing.append("net_margin_base")
        if net_debt is None:
            missing.append("net_debt")
        if shares is None or shares == 0:
            missing.append("share_count")
        if net_income is not None and net_income <= 0:
            missing.append("positive reported earnings")

        seen: set = set()
        missing = [m for m in missing if not (m in seen or seen.add(m))]

        computable = not missing
        per_share = None
        if computable:
            adj_income = net_income * (1 + g / 100.0) * (1 + (m_pp / 100.0) / net_margin_base)
            per_share = round((adj_income * mult - net_debt) / shares, 2)
            any_computable = True

        scenarios.append({
            "key": key,
            "assumptions": {"sales_growth_pct": g, "margin_delta_pp": m_pp, "earnings_multiple": mult},
            "per_share": per_share,
            "computable": computable,
            "missing": missing,
        })

    return {
        "schema": "valuation_scenario.v1",
        "ticker": ticker,
        "tier": "research_display_only",
        "source": "SEC filings",
        "fy": fy,
        "period_end": period_end,
        "base": base,
        "price": ({"value": _num(price), "unit": "USD", "asof": asof} if price is not None else None),
        "scenarios": scenarios,
        "any_computable": any_computable,
    }
