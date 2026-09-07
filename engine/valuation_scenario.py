"""Pure valuation-scenario calculator (V1) -- FROZEN SPEC B-F07-1.

No IO, no network, no clock. Consumes already-loaded per-fiscal-year
statement rows (engine.stock_fundamentals._load_statements() shape) and
emits the valuation_scenario.v1 blob for exactly one pinned issuer.

Frozen formula (spec section 2, corrected 2026-09-06 -- review B-F07-1 MAJOR-1):
  per_share = (net_income * (1 + sales_growth_pct/100)
               * (1 + (margin_delta_pp/100) / net_margin_base)
               * earnings_multiple) / share_count

An earnings (P/E) multiple already yields equity value per share -- net
debt/cash lives inside net income via interest expense, so subtracting or
adding it on top of an earnings multiple double-counts the balance sheet.
The bridge term was removed; net_debt/net_cash is reported ONLY as a base
fact (informational), never applied inside the scenario math, matching the
plain-language assumption text shown on every card ("valued at N x
earnings" never mentions a debt bridge).

net_margin_base = net_income / revenue for the SAME fiscal row, floored at 1%:
a smaller reported margin is treated as an unusable base (missing), never as
a denominator, because margin_delta_pp/net_margin_base blows up for a
thin-margin issuer (review round 2 MINOR-2).

net_debt = debt_lt + debt_cur - cash, computed ONLY when all three legs are
reported (None otherwise). This is deliberately stricter than the shared
identity in engine/stock_fundamentals._net_debt (which defaults a missing
leg to 0) -- this module is re-implemented rather than imported, and the
contract here is "null means not reported, never imputed" with no exception.

Input column names (fixed 2026-09-06 -- review B-F07-1 BLOCKER B1): the rows
passed in are engine.stock_fundamentals._load_statements() records, sourced
from collectors/edgar_facts.py's FLOW/BALANCE/BALANCE_SHARES concept tables.
Net income is read as "ni" (FLOW["ni"] = NetIncomeLoss/ProfitLoss) -- the same
column engine.stock_fundamentals._piotroski/_altman/_valuation_ratios all
read (see e.g. "pe = mktcap / ni" there). A prior revision read "net_income",
a key that does not exist anywhere in the real schema, so every AAPL row
silently produced net_income=None and every scenario read "can't be computed
without reported net income" against live data despite the field being fully
reported -- caught only because no test built its fixture from the real
column names. Every other input this module reads (revenue, op_income, cash,
debt_lt, debt_cur, shares, fy, period_end) already matches the loader's real
column name 1:1; "shares" is CommonStockSharesOutstanding (share count
identity "outstanding", not "diluted" -- the loader has no diluted share
count column, only a diluted EPS column ("eps_diluted"), which is a
per-share ratio, not a share count, and is deliberately not used here).
tests/test_valuation_scenario.py asserts the fixture's field set is a subset
of the loader's declared columns so this class of bug cannot pass silently
again.

Forbidden by construction: no consensus, no estimates, no price targets, no
probability/confidence wording, no LLM-authored numbers, no ranking/score.
"""
from __future__ import annotations

# (key, sales_growth_pct, margin_delta_pp, earnings_multiple)
MISSING_LABELS = {
    "consistent period": ("a consistent reporting period", "同一个报告期的数据"),
    "net_income": ("reported net income", "披露的净利润"),
    "revenue": ("reported revenue", "披露的营业收入"),
    "net_margin_base": ("a usable margin base", "可计算的利润率基数"),
    "net_debt": ("reported net cash or debt", "披露的净现金或净负债"),
    "share_count": ("a reported share count", "披露的股数"),
    "positive reported earnings": ("positive reported earnings", "为正数的披露净利润"),
}

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
    net_income = _num(latest.get("ni"))  # loader column is "ni", not "net_income" -- BLOCKER B1
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
    for k in ("revenue_fy", "op_income_fy", "ni_fy", "cash_fy",
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

    # MINOR-2 (review round 2): a margin base near zero is a reported number
    # but not a usable denominator -- margin_delta_pp/net_margin_base blows up
    # for a thin-margin issuer (e.g. 0.1% margin makes the Cautious factor
    # 1 + (-1.5/0.1) = -14, printing a negative per-share as a computed
    # value). Below this floor the margin base is treated the same as an
    # unreported one: it gates computability rather than producing a number.
    _MARGIN_BASE_FLOOR = 0.01  # 1% -- well under AAPL-scale margins (~24%)
    net_margin_base = None
    if net_income is not None and revenue not in (None, 0):
        candidate = net_income / revenue
        if abs(candidate) >= _MARGIN_BASE_FLOOR:
            net_margin_base = candidate

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
            per_share = round((adj_income * mult) / shares, 2)
            any_computable = True

        missing_plain = [
            {"en": MISSING_LABELS.get(m, (m, m))[0], "zh": MISSING_LABELS.get(m, (m, m))[1]}
            for m in missing
        ]

        scenarios.append({
            "key": key,
            "assumptions": {"sales_growth_pct": g, "margin_delta_pp": m_pp, "earnings_multiple": mult},
            "per_share": per_share,
            "computable": computable,
            "missing": missing,
            "missing_plain": missing_plain,
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
