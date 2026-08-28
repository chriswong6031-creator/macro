from scripts.build_btc_strategy import build_context, load_close


def test_retired_midterm_override_uses_ungated_figures_on_pinned_vintage():
    """The retired calendar veto leaves the strategy on its measured rules.

    The historical store later revised the July 1 close from the page's
    published $58,964 to $59,961. Pinning that close makes the regression stable;
    the risk strategy must now equal its ungated track and the live gate stamp
    must remain inactive.
    """
    close = load_close().loc[:"2026-07-01"].copy()
    close.iloc[-1] = 58_964.0
    view = build_context(close)
    by_id = {row["id"]: row for row in view["strategies"]}

    hodl = view["hodl"]
    assert (
        round(hodl["total"]),
        round(hodl["cagr"]),
        round(hodl["sharpe"], 2),
        round(hodl["maxdd"]),
    ) == (129, 51, 0.95, -84)

    cycle = by_id["cycle"]
    assert (
        round(cycle["metrics"]["total"]),
        round(cycle["metrics"]["cagr"]),
        round(cycle["metrics"]["sharpe"], 2),
        round(cycle["metrics"]["maxdd"]),
    ) == (13_681, 124, 1.71, -62)

    risk = by_id["risk"]
    assert (
        round(risk["metrics"]["total"]),
        round(risk["metrics"]["cagr"]),
        round(risk["metrics"]["sharpe"], 2),
        round(risk["metrics"]["maxdd"]),
    ) == (188, 56, 1.12, -71)
    assert (
        round(risk["metrics_raw"]["total"]),
        round(risk["metrics_raw"]["cagr"]),
        round(risk["metrics_raw"]["sharpe"], 2),
        round(risk["metrics_raw"]["maxdd"]),
    ) == (188, 56, 1.12, -71)
    assert risk["metrics"] == risk["metrics_raw"]
    assert view["gate"]["active"] is False

    leverage = cycle["leverage"]
    assert round(leverage[0]["total"]) == 13_681
    assert round(leverage[1]["total"]) == 1_333_284
    assert leverage[2]["blown"] is True
    assert leverage[2]["total"] == 0
