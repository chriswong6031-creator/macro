"""Weekly deep-dive: markdown to /reports + HTML to /site (GitHub Pages).

Sections per spec: rotation-type identification, positioning extremes,
revision-proxy trends, liquidity trajectory, the week's transition-flag
history, and "what would change my mind" (explicit flip conditions).

Usage: python -m scripts.weekly_report
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.inputs import build_features, yahoo_closes  # noqa: E402
from engine.regime import flip_condition  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("weekly")

CONTRARIAN_HI, CONTRARIAN_LO = 90, 10


def _pctile(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 50:
        return None
    return round(float(s.rank(pct=True).iloc[-1] * 100), 1)


def rotation_section(latest: dict) -> list[str]:
    prefs = config.load()["engine"]["sector_preferences"]
    closes = yahoo_closes()
    bench = closes[config.load()["engine"]["rs_ranking"]["benchmark"]]
    lines = ["## Rotation type", ""]
    basket_mom = {}
    for quad, names in prefs.items():
        moms = []
        for t in names:
            if t in closes.columns:
                rs = (closes[t] / bench).dropna()
                if len(rs) > 25:
                    moms.append(rs.pct_change(20).iloc[-1] * 100)
        if moms:
            basket_mom[quad] = sum(moms) / len(moms)
    if not basket_mom:
        return lines + ["insufficient data", ""]
    leader = max(basket_mom, key=basket_mom.get)
    lines.append("20d RS momentum of each quad's preference basket vs SPY:")
    lines.append("")
    for q, m in sorted(basket_mom.items(), key=lambda kv: -kv[1]):
        marker = " **<- leading**" if q == leader else ""
        lines.append(f"- {q}: {m:+.2f}%{marker}")
    cur = latest["quad"]
    agree = leader == cur
    lines += ["", f"Classifier quad is **{cur}**; tape leadership is **{leader}-consistent** "
              + ("— rotation confirms the regime." if agree else
                 "— **rotation disagrees with the regime; treat as a transition signal.**")]
    # participation: % of the 11 sectors beating SPY over 20d
    sectors = config.load()["yahoo"]["tickers"]["sectors"]
    beats = []
    for t in sectors:
        if t in closes.columns:
            rs = (closes[t] / bench).dropna()
            if len(rs) > 25:
                beats.append(rs.pct_change(20).iloc[-1] > 0)
    if beats:
        share = 100 * sum(beats) / len(beats)
        lines += ["", f"Participation: {share:.0f}% of sectors beat SPY over 20d "
                  + ("(broad)" if share >= 55 else "(narrow)" if share <= 35 else "(mixed)")]
    return lines + [""]


def positioning_section() -> list[str]:
    lines = ["## Positioning extremes", "",
             "| input | latest | pctile (full hist) | flag |", "|---|---|---|---|"]
    flags = 0
    for key, label in [("cot_es_spx", "COT ES net spec %OI"),
                       ("cot_nasdaq", "COT NQ net spec %OI"),
                       ("cot_ust10y", "COT 10Y net spec %OI"),
                       ("cot_dollar", "COT DXY net spec %OI"),
                       ("cot_gold", "COT gold net spec %OI"),
                       ("cot_copper", "COT copper net spec %OI")]:
        df = store.read("cot", key)
        if df is None or "net_spec_pct_oi" not in df.columns:
            continue
        p = _pctile(df["net_spec_pct_oi"])
        flag = ""
        if p is not None and (p >= CONTRARIAN_HI or p <= CONTRARIAN_LO):
            flag = "**CONTRARIAN**"
            flags += 1
        lines.append(f"| {label} | {df['net_spec_pct_oi'].iloc[-1]:+.1f}% | {p} | {flag} |")
    naaim = store.read("sentiment", "naaim")
    if naaim is not None:
        p = _pctile(naaim.iloc[:, 0])
        flag = "**CONTRARIAN**" if p is not None and (p >= CONTRARIAN_HI or p <= CONTRARIAN_LO) else ""
        lines.append(f"| NAAIM exposure | {naaim.iloc[-1, 0]:.0f} | {p} | {flag} |")
    aaii = store.read("sentiment", "aaii")
    if aaii is not None and "aaii_bullish" in aaii.columns:
        spread = aaii["aaii_bullish"] - aaii.get("aaii_bearish", 0)
        p = _pctile(spread)
        lines.append(f"| AAII bull-bear spread | {spread.iloc[-1]:+.0f} | {p} | |")
    else:
        lines.append("| AAII | unavailable (403-blocked source — see LIMITATIONS) | | |")
    lines += ["", f"{flags} contrarian flag(s) at the {CONTRARIAN_HI}th/{CONTRARIAN_LO}th percentile bounds.",
              "COT positioning lags 3 days (Friday release of Tuesday data).", ""]
    return lines


def revisions_section() -> list[str]:
    lines = ["## Earnings-revision proxy (LOW CONFIDENCE module)", ""]
    prox = store.read("fundamentals", "revision_proxy")
    if prox is None or prox.empty:
        return lines + ["no proxy data yet", ""]
    last = prox.dropna(how="all").iloc[-1].dropna().sort_values(ascending=False)
    top = ", ".join(f"{k.replace('_rev_proxy', '')} {v * 100:+.1f}%" for k, v in last.head(3).items())
    bot = ", ".join(f"{k.replace('_rev_proxy', '')} {v * 100:+.1f}%" for k, v in last.tail(3).items())
    return lines + [
        "Price-derived proxy: sector RS vs equal-weight market over 60d, haircut when "
        "credit disagrees. Direction matters, levels don't.", "",
        f"- improving: {top}", f"- deteriorating: {bot}", ""]


def liquidity_section(f: pd.DataFrame) -> list[str]:
    cfg = config.load()["engine"]["liquidity"]
    w = cfg["roc_window_d"]
    lines = ["## Liquidity trajectory", ""]
    nl = f["net_liquidity_bn"].dropna()
    if nl.empty:
        return lines + ["no liquidity data", ""]
    roc = nl.iloc[-1] - nl.iloc[-w - 1] if len(nl) > w else float("nan")
    lines.append(f"- net liquidity: **${nl.iloc[-1]:,.0f}bn** "
                 f"(4w change {roc:+,.0f}bn; thresholds ±{cfg['expanding_threshold_bn']}bn)")
    for col, label, scale in [("walcl_bn", "Fed balance sheet", 1),
                              ("rrp_bn", "ON RRP", 1), ("tga_bn", "TGA", 1)]:
        s = f[col].dropna()
        if len(s) > w:
            lines.append(f"- {label}: ${s.iloc[-1]:,.0f}bn ({s.iloc[-1] - s.iloc[-w - 1]:+,.0f}bn 4w)")
    iss = store.read("treasury", "net_issuance")
    if iss is not None and len(iss) > 40:
        monthly = iss.iloc[:, 0].resample("ME").sum() / 1000
        lines.append(f"- net marketable issuance, last 3 full months ($bn): "
                     + ", ".join(f"{v:+,.0f}" for v in monthly.iloc[-4:-1]))
    return lines + [""]


def flags_section() -> list[str]:
    hist = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
    hist.index = pd.to_datetime(hist.index)
    flag_cols = [c for c in hist.columns if c.startswith("flag_")]
    week = hist.dropna(subset=["quad"]).tail(5)
    lines = ["## Transition flags — this week", "",
             "| date | " + " | ".join(c.replace("flag_", "") for c in flag_cols)
             + " | state |", "|---|" + "---|" * (len(flag_cols) + 1)]
    for d, row in week.iterrows():
        cells = " | ".join("X" if row[c] else "·" for c in flag_cols)
        lines.append(f"| {d.date()} | {cells} | {row['transition_state']} |")
    return lines + [""]


def change_my_mind(f: pd.DataFrame, latest: dict) -> list[str]:
    from engine.regime import classify
    regime = classify(f)
    asof = regime["quad"].last_valid_index()
    lines = ["## What would change my mind", ""]
    row = regime.loc[asof]
    for axis in ("growth", "inflation"):
        sign = "positive" if row[f"{axis}_score"] >= 0 else "negative"
        lines.append(f"- {axis} axis is {sign} at {row[f'{axis}_score']:+.2f} "
                     f"(confidence {row[f'{axis}_confidence']:.0%}, "
                     f"agreement {row[f'{axis}_agreement']:.0%})")
    fc = flip_condition(f, regime, asof)
    lines.append(f"- most fragile input: **{fc.get('component') or 'none near threshold'}** — {fc['note']}")
    if row["pending_quad"] is not None and str(row["pending_quad"]) not in ("None", "nan"):
        need = config.load()["engine"]["quad"]["hysteresis_days"] - int(row["pending_days"])
        lines.append(f"- **hysteresis countdown live**: {row['pending_quad']} pending "
                     f"{int(row['pending_days'])}d — flips in {need} more consecutive day(s)")
    else:
        lines.append("- no pending quad: a flip needs the losing axis to cross zero and "
                     f"hold {config.load()['engine']['quad']['hysteresis_days']} days "
                     f"(or a ±{config.load()['engine']['quad']['shock_override_z']} shock print)")
    return lines + [""]


def render_html(md_text: str, title: str) -> str:
    import markdown
    body = markdown.markdown(md_text, extensions=["tables"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{background:#0f1115;color:#d7dce3;font:14px/1.6 -apple-system,'Segoe UI',sans-serif;
max-width:860px;margin:0 auto;padding:24px}}table{{border-collapse:collapse}}
th,td{{padding:4px 10px;border-bottom:1px solid #2a2f3a;text-align:left}}
h1,h2{{color:#fff}}a{{color:#7aa7e0}}code{{background:#1e222a;padding:1px 5px;border-radius:4px}}</style>
</head><body><p><a href="index.html">&larr; dashboard</a></p>{body}</body></html>"""


def main() -> int:
    with open(config.data_dir() / "regime" / "latest.json") as fh:
        latest = json.load(fh)
    f = build_features()
    asof = latest["date"]

    md = [f"# Weekly deep-dive — {asof}", "",
          f"Regime: **{latest['label']} ({latest['quad_name']})**, confidence "
          f"{latest['confidence']:.0%}, liquidity {latest['liquidity_overlay']}, "
          f"cycle {latest['cycle_tag']}, transition **{latest['transition_state']}**.", ""]
    md += rotation_section(latest)
    md += positioning_section()
    md += revisions_section()
    md += liquidity_section(f)
    md += flags_section()
    md += change_my_mind(f, latest)
    text = "\n".join(md)

    rdir = config.ROOT / config.load()["storage"]["reports_dir"]
    rdir.mkdir(exist_ok=True)
    (rdir / f"weekly-{asof}.md").write_text(text)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(exist_ok=True)
    (site / "weekly.html").write_text(render_html(text, f"Weekly deep-dive {asof}"))
    log.info("wrote reports/weekly-%s.md and site/weekly.html", asof)
    print(text[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
