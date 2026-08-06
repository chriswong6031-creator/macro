#!/usr/bin/env python3
"""Mockup generator for the redesigned /stocks/ market hub.

Reads the REAL committed heatmap payload (site/marketdata/sp500_heatmap.json —
503 S&P names with true sectors, cap-proxy sizes and multi-timeframe returns)
and the REAL production summary function (engine.market_heatmap.page_summary),
so every number and every line of derived copy is the same arithmetic the
shipped page runs.

Volume / engine-stance / 52w-position are production-SHAPED stand-ins: they
live in site/stockdata/<T>.json, which is gitignored + R2-published and so is
absent from a fresh checkout. The shipped builder reads them for real.
"""
from __future__ import annotations

import html
import json
import math
import random
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "mockups/stocks/market_hub_v1.html"
sys.path.insert(0, str(REPO))

from engine import market_heatmap as hm  # noqa: E402

PAYLOAD = json.loads((REPO / "site/marketdata/sp500_heatmap.json").read_text())
SUMMARY = hm.page_summary(PAYLOAD)
TF = SUMMARY["tf"]
TILES = [t for t in PAYLOAD["tiles"] if t.get("perf", {}).get(TF) is not None]
SECTOR_LABELS = {s["key"]: s for s in PAYLOAD.get("sectors") or []}
E = html.escape

rng = random.Random(20260804)
STANCES = [
    ("uptrend", "Uptrend", "上涨", "up"),
    ("extended", "Extended", "偏高", "warn"),
    ("basing", "Basing", "筑底", "flat"),
    ("recovering", "Recovering", "复苏", "up"),
    ("topping", "Topping", "见顶", "warn"),
    ("downtrend", "Downtrend", "下跌", "down"),
    ("aside", "Stand aside", "观望", "flat"),
]
STANCE_LABELS = {s[0]: (s[1], s[2], s[3]) for s in STANCES}


def enrich(t: dict) -> dict:
    ret = t["perf"][TF]
    cap_bn = max(2.0, t["size"] * 1400.0)
    price = round(max(4.0, rng.lognormvariate(4.4, 0.75)), 2)
    dvol = cap_bn * 1e9 * rng.lognormvariate(-5.2, 0.7) * (1 + abs(ret) / 6.0)
    rvol = max(0.25, rng.lognormvariate(0.0, 0.42) * (1 + abs(ret) / 14.0))
    trail = t["perf"].get("3M") or t["perf"].get("1M") or ret
    pos = min(0.995, max(0.005, 0.55 + trail / 90.0 + rng.gauss(0, 0.17)))
    st = rng.choices(STANCES, weights=[26, 12, 14, 11, 9, 16, 12])[0]
    return {"t": t["t"], "name": t.get("name") or t["t"], "sector": t["sector"],
            "industry": t.get("industry") or "", "ret": ret, "size": t["size"],
            "cap_bn": cap_bn, "price": price, "dvol": dvol, "rvol": rvol,
            "pos52": pos, "stance_key": st[0], "stance_en": st[1],
            "stance_zh": st[2], "stance_tone": st[3], "perf": t["perf"]}


ROWS = sorted((enrich(t) for t in TILES), key=lambda r: r["t"])
N = len(ROWS)

# ── signature: "the day's shape" ────────────────────────────────────────────
SPINE_W, SPINE_H = 1200.0, 128.0
MID = SPINE_H / 2.0


def spine() -> dict:
    vals = sorted(r["ret"] for r in ROWS)
    n = len(vals)
    mags = sorted(abs(v) for v in vals)
    scale = max(mags[min(n - 1, int(0.97 * n))] or 1.0, 0.8)

    def xy(i: int, v: float) -> tuple[float, float]:
        u = v / scale
        a = abs(u)
        if a > 1.0:                                   # soft clamp, tails compress
            a = 1.0 + math.log1p(a - 1.0) * 0.5
        u = math.copysign(min(a, 1.55), u) / 1.55
        return (i / max(1, n - 1)) * SPINE_W, MID - u * (MID - 3)

    pts = [xy(i, v) for i, v in enumerate(vals)]
    # Cross at the SAME dead-band page_summary() uses for advancing/declining
    # (engine.market_heatmap._ADV_BAND). Using `v >= 0` here instead put a
    # second, slightly different breadth number on screen beside the first —
    # one fact, two answers, which reads as a bug to anyone who checks.
    cross = next((i for i, v in enumerate(vals) if v > hm._ADV_BAND), n)

    def seg(lo: int, hi: int) -> str:
        sub = pts[lo:hi]
        if len(sub) < 2:
            return ""
        return (f"M {sub[0][0]:.2f} {MID:.2f} "
                + " ".join(f"L {x:.2f} {y:.2f}" for x, y in sub)
                + f" L {sub[-1][0]:.2f} {MID:.2f} Z")

    return {"neg": seg(0, cross + 1), "pos": seg(max(0, cross - 1), n),
            "line": "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts),
            "cross_x": (cross / max(1, n - 1)) * SPINE_W,
            "green_pct": SUMMARY["pct_up"], "n": n}


SPINE = spine()
BEST, WORST = max(ROWS, key=lambda r: r["ret"]), min(ROWS, key=lambda r: r["ret"])


# ── squarified treemap (server-rendered: the JSON is auth-gated) ─────────────
def squarify(items: list[dict], x: float, y: float, w: float, h: float) -> list[dict]:
    items = [i for i in items if i.get("v", 0) > 0]
    if not items or w <= 0 or h <= 0:
        return []
    tot = sum(i["v"] for i in items)
    items = sorted(({**i, "v": i["v"] / tot * (w * h)} for i in items),
                   key=lambda i: i["v"], reverse=True)
    out: list[dict] = []
    cx, cy, cw, ch = x, y, w, h

    def ratio(row: list[dict], length: float) -> float:
        s = sum(i["v"] for i in row)
        if s <= 0 or length <= 0:
            return math.inf
        band = s / length
        worst = 0.0
        for i in row:
            side = i["v"] / band
            if side <= 0:
                return math.inf
            worst = max(worst, band / side, side / band)
        return worst

    def place(row: list[dict], x0, y0, w0, h0):
        s = sum(i["v"] for i in row)
        if s <= 0:
            return x0, y0, w0, h0
        if w0 >= h0:                                  # vertical band on the left
            band = s / h0 if h0 else 0
            cyy = y0
            for i in row:
                ih = i["v"] / band if band else 0
                out.append({**i, "x": x0, "y": cyy, "w": band, "h": ih})
                cyy += ih
            return x0 + band, y0, w0 - band, h0
        band = s / w0 if w0 else 0                    # horizontal band on top
        cxx = x0
        for i in row:
            iw = i["v"] / band if band else 0
            out.append({**i, "x": cxx, "y": y0, "w": iw, "h": band})
            cxx += iw
        return x0, y0 + band, w0, h0 - band

    row: list[dict] = []
    queue = list(items)
    while queue:
        length = ch if cw >= ch else cw
        cand = row + [queue[0]]
        if not row or ratio(cand, length) <= ratio(row, length):
            row, queue = cand, queue[1:]
        else:
            cx, cy, cw, ch = place(row, cx, cy, cw, ch)
            row = []
    if row:
        place(row, cx, cy, cw, ch)
    return out


HM_W, HM_H = 1200.0, 520.0


def tone(ret: float) -> str:
    a = abs(ret)
    if a < 0.15:
        return "var(--hm0)"
    step = 1 if a < 1 else (2 if a < 2 else (3 if a < 3 else 4))
    return f"var(--hm{'u' if ret > 0 else 'd'}{step})"


def treemap() -> str:
    by_sec: dict[str, list[dict]] = {}
    for r in ROWS:
        by_sec.setdefault(r["sector"], []).append(r)
    cells = squarify([{"v": sum(x["size"] for x in g), "key": k, "rows": g}
                      for k, g in by_sec.items()], 0, 0, HM_W, HM_H)
    svg, HEAD = [], 16.0
    for c in cells:
        lab = SECTOR_LABELS.get(c["key"], {})
        en, zh = lab.get("en", c["key"]), lab.get("zh", lab.get("en", c["key"]))
        svg.append(f'<g class="hmsec"><rect x="{c["x"]:.1f}" y="{c["y"]:.1f}" '
                   f'width="{max(0,c["w"]-2):.1f}" height="{max(0,c["h"]-2):.1f}" '
                   f'rx="5" class="hmsec-bg"/>')
        if c["w"] > 56 and c["h"] > 32:
            svg.append(f'<text class="hmsec-t" x="{c["x"]+7:.1f}" y="{c["y"]+11.5:.1f}">'
                       f'<tspan class="l-en">{E(en.upper())}</tspan>'
                       f'<tspan class="l-zh">{E(zh)}</tspan></text>')
        for t in squarify([{"v": r["size"], "r": r} for r in c["rows"]],
                          c["x"] + 2, c["y"] + HEAD,
                          max(1.0, c["w"] - 6), max(1.0, c["h"] - HEAD - 4)):
            r = t["r"]
            if t["w"] < 1.4 or t["h"] < 1.4:
                continue
            svg.append(f'<a class="hmt" href="{E(r["t"])}.html">'
                       f'<rect x="{t["x"]:.1f}" y="{t["y"]:.1f}" '
                       f'width="{max(0,t["w"]-1.5):.1f}" height="{max(0,t["h"]-1.5):.1f}" '
                       f'rx="2.5" fill="{tone(r["ret"])}"/>')
            big = t["w"] > 38 and t["h"] > 28
            if t["w"] > 27 and t["h"] > 15:
                dy = -1.0 if big else 3.6
                svg.append(f'<text class="hmt-t" x="{t["x"]+t["w"]/2:.1f}" '
                           f'y="{t["y"]+t["h"]/2+dy:.1f}">{E(r["t"])}</text>')
            if big:
                svg.append(f'<text class="hmt-p" x="{t["x"]+t["w"]/2:.1f}" '
                           f'y="{t["y"]+t["h"]/2+10.5:.1f}">{r["ret"]:+.1f}%</text>')
            svg.append(f'<title>{E(r["t"])} · {E(r["name"])} · {r["ret"]:+.2f}%</title></a>')
        svg.append("</g>")
    return "\n".join(svg)


# ── boards ──────────────────────────────────────────────────────────────────
def fmt_dvol(v: float) -> str:
    return (f"${v/1e9:.1f}B" if v >= 1e9 else
            f"${v/1e6:.0f}M" if v >= 1e6 else f"${v/1e3:.0f}K")


GAINERS = sorted(ROWS, key=lambda r: r["ret"], reverse=True)[:7]
LOSERS = sorted(ROWS, key=lambda r: r["ret"])[:7]
ACTIVE = sorted(ROWS, key=lambda r: r["dvol"], reverse=True)[:7]
UNUSUAL = sorted([r for r in ROWS if r["dvol"] > 3e8],
                 key=lambda r: r["rvol"], reverse=True)[:7]
NEAR_HI = sorted([r for r in ROWS if r["pos52"] >= 0.93], key=lambda r: -r["pos52"])[:7]
NEAR_LO = sorted([r for r in ROWS if r["pos52"] <= 0.07], key=lambda r: r["pos52"])[:7]


def bd_row(r: dict, mx: float, metric: str) -> str:
    # The secondary-value cell is ALWAYS emitted (empty when the board has no
    # second metric). Omitting it shifts every later cell one grid column left,
    # which silently crushed the company-name column to an ellipsis.
    tn = "up" if r["ret"] >= 0 else "dn"
    if metric == "ret":
        val, w, extra = f'{r["ret"]:+.2f}%', abs(r["ret"]) / mx * 100, '<span class="bd-x"></span>'
    elif metric == "dvol":
        val, w = fmt_dvol(r["dvol"]), r["dvol"] / mx * 100
        extra = f'<span class="bd-x {tn}">{r["ret"]:+.1f}%</span>'
    else:
        val, w = f'{r["rvol"]:.1f}×', r["rvol"] / mx * 100
        extra = f'<span class="bd-x {tn}">{r["ret"]:+.1f}%</span>'
    return (f'<a class="bd-row" href="{E(r["t"])}.html">'
            f'<span class="bd-tk">{E(r["t"])}</span>'
            f'<span class="bd-nm">{E(r["name"])}</span>{extra}'
            f'<span class="bd-v {tn}">{val}</span>'
            f'<span class="bd-bar"><i class="{tn}" style="width:{min(100,w):.0f}%"></i></span></a>')


def board(t_en, t_zh, rows, metric, n_en, n_zh, cls="") -> str:
    if not rows:
        return ""
    k = {"ret": lambda r: abs(r["ret"]), "dvol": lambda r: r["dvol"],
         "rvol": lambda r: r["rvol"]}[metric]
    mx = max(k(r) for r in rows) or 1.0
    return f"""<section class="card bd {cls}">
  <header class="card-h"><h2><span class="l-en">{E(t_en)}</span><span class="l-zh">{E(t_zh)}</span></h2>
  <span class="card-note"><span class="l-en">{E(n_en)}</span><span class="l-zh">{E(n_zh)}</span></span></header>
  <div class="bd-body">{''.join(bd_row(r, mx, metric) for r in rows)}</div>
</section>"""


# ── search index + directory ────────────────────────────────────────────────
SEARCH = [[r["t"], r["name"], r["sector"], round(r["price"], 2), round(r["ret"], 2),
           r["stance_key"], round(r["cap_bn"]), round(r["rvol"], 2), round(r["pos52"], 3)]
          for r in ROWS]

DIR: dict[str, list[dict]] = {}
for r in ROWS:
    DIR.setdefault(r["t"][0].upper(), []).append(r)

SEC_KEYS = sorted({r["sector"] for r in ROWS})


def sec_chips() -> str:
    out = ['<button class="fchip on" data-f="sec" data-v="">'
           '<span class="l-en">All sectors</span><span class="l-zh">全部板块</span></button>']
    for k in SEC_KEYS:
        lab = SECTOR_LABELS.get(k, {})
        out.append(f'<button class="fchip" data-f="sec" data-v="{E(k)}">'
                   f'<span class="l-en">{E(lab.get("en", k))}</span>'
                   f'<span class="l-zh">{E(lab.get("zh", lab.get("en", k)))}</span></button>')
    return "".join(out)


def stance_chips() -> str:
    out = ['<button class="fchip on" data-f="st" data-v="">'
           '<span class="l-en">Any read</span><span class="l-zh">全部研判</span></button>']
    for k, (en, zh, tn) in STANCE_LABELS.items():
        out.append(f'<button class="fchip s-{tn}" data-f="st" data-v="{E(k)}">'
                   f'<span class="l-en">{E(en)}</span><span class="l-zh">{E(zh)}</span></button>')
    return "".join(out)


def directory() -> str:
    out = []
    for letter in sorted(DIR):
        chips = "".join(f'<a class="dir-t" href="{E(r["t"])}.html">{E(r["t"])}</a>'
                        for r in sorted(DIR[letter], key=lambda x: x["t"]))
        out.append(f'<div class="dir-grp"><span class="dir-l">{letter}</span>'
                   f'<div class="dir-row">{chips}</div></div>')
    return "".join(out)


SECTOR_STRENGTH = "".join(
    f'<div class="ss-row"><span class="ss-n"><span class="l-en">{E(s["en"])}</span>'
    f'<span class="l-zh">{E(s["zh"])}</span></span>'
    f'<span class="ss-track"><i class="{"up" if s["up"] else "dn"}" '
    f'style="width:{s["w"]}%"></i></span>'
    f'<span class="ss-v {"up" if s["up"] else "dn"}">{E(s["pc"])}</span></div>'
    for s in SUMMARY["sectors"])

# theme.css inlined so the mockup opens standalone from anywhere (the fonts
# resolve from the CDN-less @font-face paths only when served from site/, so the
# stack falls back to the system UI face — the token system is what matters here).
THEME = (REPO / "templates/theme.css").read_text()
CSS = (Path(__file__).parent / "hub.css").read_text()
JS = (Path(__file__).parent / "hub.js").read_text()
TPL = (Path(__file__).parent / "hub.html").read_text()

html_out = TPL.format(
    CSS=CSS, JS=JS, THEME=THEME,
    N=f"{N:,}", N_REAL="1,544",
    STANCE_EN=SUMMARY["stance"]["en"], STANCE_ZH=SUMMARY["stance"]["zh"],
    STANCE_TONE=SUMMARY["stance"]["tone"],
    PCT_UP=SUMMARY["pct_up"], MEDIAN=SUMMARY["median"],
    MEDIAN_TONE=SUMMARY["median_tone"],
    MEDIAN_W_EN=(SUMMARY["median_word"] or {}).get("en", ""),
    MEDIAN_W_ZH=(SUMMARY["median_word"] or {}).get("zh", ""),
    ADV=SUMMARY["breadth"]["adv"], DEC=SUMMARY["breadth"]["dec"],
    ADV_W=SUMMARY["breadth"]["adv_w"], FLAT_W=SUMMARY["breadth"]["flat_w"],
    DEC_W=SUMMARY["breadth"]["dec_w"],
    TOP_EN=(SUMMARY["top"] or {}).get("en", ""), TOP_ZH=(SUMMARY["top"] or {}).get("zh", ""),
    TOP_PC=(SUMMARY["top"] or {}).get("pc", ""), TOP_TONE=(SUMMARY["top"] or {}).get("tone", ""),
    BOT_EN=(SUMMARY["bot"] or {}).get("en", ""), BOT_ZH=(SUMMARY["bot"] or {}).get("zh", ""),
    BOT_PC=(SUMMARY["bot"] or {}).get("pc", ""), BOT_TONE=(SUMMARY["bot"] or {}).get("tone", ""),
    ASOF=SUMMARY["asof"],
    SPINE_NEG=SPINE["neg"], SPINE_POS=SPINE["pos"], SPINE_LINE=SPINE["line"],
    SPINE_CROSS=f'{SPINE["cross_x"]:.1f}', GREEN_PCT=SPINE["green_pct"],
    SPINE_W=f"{SPINE_W:.0f}", SPINE_H=f"{SPINE_H:.0f}",
    BEST_T=BEST["t"], BEST_V=f'{BEST["ret"]:+.1f}%',
    WORST_T=WORST["t"], WORST_V=f'{WORST["ret"]:+.1f}%',
    GAINERS=board("Top gainers", "涨幅榜", GAINERS, "ret",
                  "Biggest moves up today", "今日涨幅最大"),
    LOSERS=board("Top losers", "跌幅榜", LOSERS, "ret",
                 "Biggest moves down today", "今日跌幅最大"),
    ACTIVE=board("Most traded", "成交额榜", ACTIVE, "dvol",
                 "Where the money went — dollars traded", "资金去向 — 成交金额"),
    UNUSUAL=board("Unusual volume", "异动放量", UNUSUAL, "rvol",
                  "Trading far above their own normal", "成交量远超自身常态"),
    NEAR_HI=board("Near 52-week highs", "接近52周高点", NEAR_HI, "ret",
                  "Within 7% of the year's high", "距年内高点7%以内"),
    NEAR_LO=board("Near 52-week lows", "接近52周低点", NEAR_LO, "ret",
                  "Within 7% of the year's low", "距年内低点7%以内"),
    SECTOR_STRENGTH=SECTOR_STRENGTH,
    TREEMAP=treemap(), HM_W=f"{HM_W:.0f}", HM_H=f"{HM_H:.0f}",
    SEC_CHIPS=sec_chips(), STANCE_CHIPS=stance_chips(),
    DIRECTORY=directory(),
    SEARCH_JSON=json.dumps(SEARCH, separators=(",", ":"), ensure_ascii=False),
    SEC_LABELS_JSON=json.dumps(
        {k: [SECTOR_LABELS.get(k, {}).get("en", k), SECTOR_LABELS.get(k, {}).get("zh", k)]
         for k in SEC_KEYS}, ensure_ascii=False, separators=(",", ":")),
    STANCE_JSON=json.dumps({k: list(v) for k, v in STANCE_LABELS.items()},
                           ensure_ascii=False, separators=(",", ":")),
)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html_out, encoding="utf-8")
print(f"wrote {OUT}  ({len(html_out)/1024:.0f} KB, {N} names, "
      f"{SPINE['green_pct']}% green, stance={SUMMARY['stance']['en']})")
