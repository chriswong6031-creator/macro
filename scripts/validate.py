"""Phase 2e validation: backtest the classifier 2007 -> present and write
reports/validation.md + site/validation_timeline.html.

Because the engine recomputes full history every run (one code path), this
script just runs the production classifier and inspects its output — there is
no separate backtest engine.

Sanity targets (from the build spec):
  late-2008      -> Q4, recession tag engaged
  2021           -> Q2 -> Q3 path
  2022           -> Q3 with inflation-shock episodes
  Mar-2020       -> shock-override flip to Q4 within days
  whipsaw        -> regime changes lasting < 10 days are < 15% of all changes
Plus: sector-preference hit-rate vs forward 60d returns per quad.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.inputs import build_features, yahoo_closes  # noqa: E402
from engine.regime import classify  # noqa: E402
from engine.transition import compute_flags, state_machine  # noqa: E402
from lib import config  # noqa: E402

QUAD_COLORS = {"Q1": "#2e7d32", "Q2": "#f9a825", "Q3": "#c62828", "Q4": "#1565c0"}


def episode_share(regime: pd.DataFrame, start: str, end: str, col: str = "quad") -> pd.Series:
    seg = regime.loc[start:end, col].dropna()
    return seg.value_counts(normalize=True).round(3)


def regime_segments(quad: pd.Series) -> pd.DataFrame:
    q = quad.dropna()
    seg_id = (q != q.shift()).cumsum()
    g = q.groupby(seg_id)
    return pd.DataFrame({
        "quad": g.first(),
        "start": g.apply(lambda s: s.index.min()),
        "end": g.apply(lambda s: s.index.max()),
        "days": g.size(),
    }).reset_index(drop=True)


def whipsaw_stats(segments: pd.DataFrame, max_days: int) -> dict:
    changes = len(segments) - 1
    if changes <= 0:
        return {"changes": 0, "whipsaws": 0, "pct": 0.0}
    whips = int((segments["days"].iloc[1:] < max_days).sum())
    return {"changes": changes, "whipsaws": whips,
            "pct": round(100 * whips / changes, 1)}


def sector_hit_rate(regime: pd.DataFrame, fwd_days: int) -> pd.DataFrame:
    prefs = config.load()["engine"]["sector_preferences"]
    closes = yahoo_closes()
    spy_fwd = closes["SPY"].pct_change(fwd_days).shift(-fwd_days)
    rows = []
    for quad, names in prefs.items():
        cols = [t for t in names if t in closes.columns]
        if not cols:
            continue
        basket_fwd = pd.concat(
            [closes[t].pct_change(fwd_days).shift(-fwd_days) for t in cols], axis=1
        ).mean(axis=1)
        mask = (regime["quad"] == quad).reindex(basket_fwd.index, fill_value=False)
        mask &= basket_fwd.notna() & spy_fwd.notna()
        n = int(mask.sum())
        if n < 30:
            rows.append({"quad": quad, "days": n, "hit_rate_pct": None,
                         "avg_excess_60d_pct": None})
            continue
        excess = (basket_fwd - spy_fwd)[mask]
        rows.append({"quad": quad, "days": n,
                     "hit_rate_pct": round(100 * (excess > 0).mean(), 1),
                     "avg_excess_60d_pct": round(100 * excess.mean(), 2)})
    return pd.DataFrame(rows)


def timeline_chart(f: pd.DataFrame, regime: pd.DataFrame, segments: pd.DataFrame,
                   out_html: Path) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.55, 0.3, 0.15], vertical_spacing=0.03,
                        subplot_titles=["SPY (log) with regime bands",
                                        "Axis scores", "Transition state"])
    spy = f["SPY"].dropna()
    fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY",
                             line={"color": "#222", "width": 1}), row=1, col=1)
    fig.update_yaxes(type="log", row=1, col=1)
    for _, seg in segments.iterrows():
        fig.add_vrect(x0=seg["start"], x1=seg["end"],
                      fillcolor=QUAD_COLORS.get(seg["quad"], "#999"),
                      opacity=0.18, line_width=0, row=1, col=1)
    for q, c in QUAD_COLORS.items():
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                                 marker={"color": c, "size": 10},
                                 name=f"{q}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=regime.index, y=regime["growth_score"],
                             name="growth", line={"color": "#2e7d32", "width": 1}),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=regime.index, y=regime["inflation_score"],
                             name="inflation", line={"color": "#c62828", "width": 1}),
                  row=2, col=1)
    fig.add_hline(y=0, line={"color": "#888", "width": 0.5}, row=2, col=1)
    state_num = regime["transition_state"].map(
        {"STABLE": 0, "WEAKENING": 1, "TRANSITIONING": 2, "NEW_REGIME": 3})
    fig.add_trace(go.Scatter(x=regime.index, y=state_num, name="transition",
                             line={"color": "#6a1b9a", "width": 1},
                             fill="tozeroy"), row=3, col=1)
    fig.update_yaxes(tickvals=[0, 1, 2, 3],
                     ticktext=["STABLE", "WEAK", "TRANS", "NEW"], row=3, col=1)
    fig.update_layout(height=900, title="Regime classifier validation timeline 2007 -> present",
                      hovermode="x unified", template="plotly_white")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_html, include_plotlyjs="cdn")


def main() -> None:
    vcfg = config.load()["validation"]
    start = vcfg["start_date"]

    f = build_features()
    regime = classify(f)
    flags = compute_flags(f, regime)
    regime["transition_state"] = state_machine(flags, regime)
    regime = regime.loc[start:]
    f = f.loc[start:]

    segments = regime_segments(regime["quad"])
    ws = whipsaw_stats(segments, vcfg["whipsaw_max_days"])
    hits = sector_hit_rate(regime, vcfg["forward_return_window_d"])

    # --- episode checks ---------------------------------------------------------
    ep = {
        "2008 crisis (2008-09-01..2009-03-31)": episode_share(regime, "2008-09-01", "2009-03-31"),
        "2020 covid crash (2020-02-24..2020-05-31)": episode_share(regime, "2020-02-24", "2020-05-31"),
        "2021 H1 (reflation?)": episode_share(regime, "2021-01-01", "2021-06-30"),
        "2021 H2 (toward stagflation?)": episode_share(regime, "2021-07-01", "2021-12-31"),
        "2022 (inflation shock?)": episode_share(regime, "2022-01-01", "2022-12-31"),
    }
    rec_2008 = regime.loc["2008-10-01":"2009-03-31", "recession"].mean()
    shock_2022 = regime.loc["2022-01-01":"2022-12-31", "inflation_shock"].mean()

    # covid shock-override speed: first Q4 day after the 2020-02-19 top
    covid = regime.loc["2020-02-19":"2020-04-30"]
    q4_days = covid.index[covid["quad"] == "Q4"]
    covid_flip = str(q4_days[0].date()) if len(q4_days) else "NEVER"

    # transition detector lead time: share of regime changes preceded by a
    # non-STABLE state within the prior 20 trading days
    q = regime["quad"].dropna()
    change_days = q.index[q != q.shift()][1:]
    led = 0
    for d in change_days:
        win = regime.loc[:d].iloc[-21:-1]["transition_state"]
        led += int((win != "STABLE").any())
    lead_rate = round(100 * led / len(change_days), 1) if len(change_days) else None

    timeline_chart(f, regime, segments,
                   config.ROOT / config.load()["storage"]["site_dir"] / "validation_timeline.html")

    # --- report -------------------------------------------------------------------
    lines = ["# Regime classifier validation (Phase 2e)", "",
             f"Backtest window: {regime.index.min().date()} -> {regime.index.max().date()}",
             f"(engine code path identical to live; GEX flag inactive historically — see DECISIONS D14)", "",
             "## Whipsaw",
             f"- regime changes: {ws['changes']}",
             f"- lasting < {vcfg['whipsaw_max_days']} days: {ws['whipsaws']} ({ws['pct']}%)"
             f" — target < {vcfg['whipsaw_target_pct']}% -> "
             + ("**PASS**" if ws["pct"] < vcfg["whipsaw_target_pct"] else "**FAIL**"), "",
             "## Episode sanity checks"]
    for name, share in ep.items():
        lines.append(f"- **{name}**: " + ", ".join(f"{k} {v:.0%}" for k, v in share.items()))
    lines += [f"- 2008-10..2009-03 recession-tag engaged on {rec_2008:.0%} of days",
              f"- 2022 inflation-shock tag engaged on {shock_2022:.0%} of days",
              f"- Covid: first Q4 day after the 2020-02-19 top: **{covid_flip}**", "",
              "## Transition detector",
              f"- {lead_rate}% of regime changes were preceded by a non-STABLE "
              f"transition state within the prior 20 trading days", "",
              "## Sector-preference hit-rate (fwd 60d, preferred basket vs SPY)",
              hits.to_markdown(index=False), "",
              "## Regime segments (last 25)",
              segments.tail(25).to_markdown(index=False), "",
              "Timeline chart: `site/validation_timeline.html`", ""]

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"wrote {out}")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
