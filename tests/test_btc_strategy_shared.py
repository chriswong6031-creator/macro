from scripts.build_btc_strategy import build_context, load_close


def test_published_july_1_strategy_figures_reproduce_on_pinned_vintage():
    """Frozen replay for the figures published by the legacy strategy page.

    The historical store later revised the July 1 close from the page's
    published $58,964 to $59,961. Pinning that one displayed close reproduces
    the old page exactly and proves the shared Wave-1 module did not change the
    strategy calculations during the move.
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
    ) == (441, 68, 1.29, -64)
    assert (
        round(risk["metrics_raw"]["total"]),
        round(risk["metrics_raw"]["cagr"]),
        round(risk["metrics_raw"]["sharpe"], 2),
        round(risk["metrics_raw"]["maxdd"]),
    ) == (188, 56, 1.12, -71)

    leverage = cycle["leverage"]
    assert round(leverage[0]["total"]) == 13_681
    assert round(leverage[1]["total"]) == 1_333_284
    assert leverage[2]["blown"] is True
    assert leverage[2]["total"] == 0
