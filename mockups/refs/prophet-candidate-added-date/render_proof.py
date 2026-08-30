#!/usr/bin/env python3
"""One-off visual proof: stamp real committed artifacts and render labelled Added chips."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from engine import i18n
from engine.prophet_board_since import is_iso_date, stamp_setups

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _rows(artifact: dict, lanes: tuple[str, ...]) -> list[dict]:
    out = []
    for lane in lanes:
        for row in artifact.get(lane) or []:
            if isinstance(row, dict) and row.get("ticker"):
                out.append({**row, "_lane": lane})
    return out


def _row(artifact: dict, ticker: str, lanes: tuple[str, ...]) -> dict | None:
    want = str(ticker)
    for row in _rows(artifact, lanes):
        if str(row.get("ticker")) == want:
            return row
    return None


def _oldest(artifact: dict, lanes: tuple[str, ...]) -> dict | None:
    dated = [r for r in _rows(artifact, lanes) if is_iso_date(r.get("board_since"))]
    return min(dated, key=lambda r: r["board_since"]) if dated else None


def _newest(artifact: dict, lanes: tuple[str, ...]) -> dict | None:
    dated = [r for r in _rows(artifact, lanes) if is_iso_date(r.get("board_since"))]
    return max(dated, key=lambda r: (r["board_since"], str(r.get("ticker")))) if dated else None


def _undated(artifact: dict, lanes: tuple[str, ...]) -> dict | None:
    for row in _rows(artifact, lanes):
        if not is_iso_date(row.get("board_since")):
            return row
    return None


def _zone(row: dict) -> tuple[str, str | None, str | None]:
    es = row.get("entry_signal") or {}
    bz = es.get("buy_zone") if isinstance(es, dict) else None
    if isinstance(bz, dict) and bz.get("low") is not None:
        lo = f"${float(bz['low']):.2f}"
        hi = f"${float(bz['high']):.2f}" if bz.get("high") is not None else None
        return "active", lo, hi
    for key in ("zone_low", "zone_lo", "buy_low"):
        if row.get(key) is not None:
            lo = f"${float(row[key]):.2f}"
            hi_v = row.get("zone_high") or row.get("zone_hi") or row.get("buy_high")
            hi = f"${float(hi_v):.2f}" if hi_v is not None else None
            return "active", lo, hi
    return "none", None, None


def _cx(market: str, row: dict, *, long_zone: bool = False) -> dict:
    tk = str(row.get("ticker"))
    zk, lo, hi = _zone(row)
    if long_zone:
        zk, lo, hi = "active", "$12.345–pending-reentry", "$1,234.56"
        lo, hi = "$12.34", "$1,234.56"
    return {
        "href": f"stock.html#{tk}",
        "tk": tk.split(".")[0] if market in {"hk", "cn", "ca"} else tk,
        "mkt": market,
        "name": row.get("name") or tk,
        "sec": row.get("sector") or row.get("industry") or "—",
        "price_txt": f"${float(row['price']):.2f}" if row.get("price") is not None else None,
        "show_change": False,
        "verb": "buy",
        "edge": 72,
        "stage": 3,
        "spark": None,
        "zone_kind": zk,
        "zone_lo": lo,
        "zone_hi": hi,
        "date": None,
        "added_date": row.get("board_since"),
        "flags": [],
    }


def _stamp(market: str, rel: str) -> dict:
    blob = _load(rel)
    return stamp_setups(market, blob, repo_root=ROOT) or blob


def main() -> None:
    us = _stamp("us", "site/factordata/us_standouts.json")
    cn = _stamp("cn", "site/factordata/china_setups.json")
    hk = _stamp("hk", "site/factordata/hk_standouts.json")
    ca = _stamp("ca", "site/factordata/canada_setups.json")
    intl = _stamp("intl", "site/factordata/intl_setups.json")

    us_lanes = ("buy", "watch", "leaders", "ran", "laggards", "laggard")
    cn_lanes = ("buy", "more_actionable", "late_or_unfillable")
    hk_ca = ("buy", "watch")
    picks = [
        ("US continuing", "us", _oldest(us, us_lanes)),
        ("US newest on board", "us", _newest(us, us_lanes)),
        ("CN continuing", "cn", _oldest(cn, cn_lanes)),
        ("CN newest on board", "cn", _newest(cn, cn_lanes)),
        ("HK continuing", "hk", _oldest(hk, hk_ca)),
        ("HK newest on board", "hk", _newest(hk, hk_ca)),
        ("CA continuing", "ca", _oldest(ca, hk_ca)),
        ("CA newest on board", "ca", _newest(ca, hk_ca)),
        ("Intl fail-closed (as_of null)", "intl", _undated(intl, ("buy",))),
    ]
    missing = [label for label, _, row in picks if row is None]
    if missing:
        raise SystemExit(f"missing real rows: {missing}")

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(("html", "j2")),
    )
    env.globals.update(t=i18n.t, tr=i18n.tr, td=i18n.td)
    macros = env.get_template("_prophet_card.html.j2").make_module({"t": i18n.t, "tr": i18n.tr})

    cards = []
    for label, market, row in picks:
        html = macros.pv_card(_cx(market, row))
        cards.append((label, row.get("ticker"), row.get("board_since"), html))

    long_row = dict(picks[0][2])
    long_row["ticker"] = "VERYLONGTICKER"
    long_row["name"] = "Very Long Industrial Conglomerate Holdings Ltd"
    cards.append(
        (
            "Geometry: long ticker + wide zone (US VIR membership date kept)",
            long_row["ticker"],
            long_row.get("board_since"),
            macros.pv_card(_cx("us", long_row, long_zone=True) | {"tk": "VERYLONGTICKER"}),
        )
    )

    css = str(macros.pv_css())
    css = css.replace("<style>", "").replace("</style>", "")
    theme = (ROOT / "templates" / "theme.css").read_text(encoding="utf-8")
    sections = []
    for label, ticker, since, html in cards:
        since_txt = since if is_iso_date(since) else "none (chip omitted)"
        sections.append(
            f'<section class="proof"><h2>{label}</h2>'
            f'<p class="meta">{ticker} · board_since={since_txt}</p>'
            f'<div class="grid">{html}</div></section>'
        )
    body = "\n".join(sections)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Prophet Added date proof</title>
<style>{theme}\n{css}
body{{margin:0;background:var(--bg);color:var(--text);font:14px var(--font-ui);padding:18px}}
h1{{font-size:18px;margin:0 0 8px}}
.lede{{color:var(--muted);margin:0 0 18px;max-width:70ch}}
.proof{{margin:0 0 22px}}
.proof h2{{font-size:13px;margin:0 0 4px}}
.meta{{color:var(--muted);font-size:11px;margin:0 0 8px}}
.grid{{display:grid;grid-template-columns:minmax(0,360px);gap:12px}}
.pvcard{{max-width:360px}}
@media (min-width:900px){{.grid{{grid-template-columns:repeat(2,minmax(0,360px))}}}}
</style>
</head>
<body>
<h1>Prophet candidate Added date — real artifact proof</h1>
<p class="lede">Stamped from committed US/CN/HK/CA/Intl artifacts. Labelled Added / 入榜 only. Intl has as_of null so the chip is omitted. Not a revert of #6532/#6544.</p>
{body}
</body>
</html>
"""
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "en-dark": ("en", "dark"),
        "zh-dark": ("zh", "dark"),
        "en-light": ("en", "light"),
        "zh-light": ("zh", "light"),
    }
    chrome = Path(CHROME)
    if not chrome.exists():
        raise SystemExit("chrome missing")
    for name, (lang, theme_name) in variants.items():
        html_path = OUT / f"specimen-{name}.html"
        html_path.write_text(
            page.replace('<html lang="en">', f'<html lang="{lang}" data-lang="{lang}" data-theme="{theme_name}">', 1),
            encoding="utf-8",
        )
        for width, tag in ((1440, "desktop"), (390, "mobile")):
            png = OUT / f"{name}-{tag}.png"
            cmd = [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={width},4200",
                f"--screenshot={png}",
                html_path.resolve().as_uri(),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            print("wrote", png, "bytes", png.stat().st_size)
    print("cards", [(a, b, c) for a, b, c, _ in cards])


if __name__ == "__main__":
    main()
