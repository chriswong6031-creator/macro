#!/usr/bin/env python3
"""Generate lab-data.js — the Prophet Operator Lab fixture (D-LAB-R5).

HONESTY CONTRACT — read this before touching the output.

The R4 board fixture (`../institutionalize/us_stocks/board-data.js`) is a real
extract of a committed payload. **The Lab half of this fixture cannot be**, and
pretending otherwise would be the exact defect the RIG cycle exists to catch:

  * Radar's live transport (R-LAB-1 / W4.1) has not landed, so no canonical
    `mastermind.entry_event.v1` stream exists to extract. There is no store to
    read; there is no honest way to obtain a real first-observation time.
  * Therefore EVERY Lab-plane fact below is SYNTHETIC and deterministic:
    which detector fired, when it fired, when it was first observed, and the
    observation class. They are marked `data-mock-lab` in the DOM and disclosed
    on the harness bar and in DESIGN_NOTES §Evidence.

What is NOT synthetic, and is taken verbatim from the committed R4 payload:

  * ticker, company name, sector          — real
  * the spark SVG                         — real, and ONLY ever attached to the
                                            ticker the payload drew it for
  * the Prophet comparison                — real: lifecycle state and plan-open
                                            date read from the same plan rows
                                            the R4 board renders

No chart is fabricated. A Lab row whose ticker carries no spark in the payload
renders the printed null hero, exactly as the Prophet card does — the enrichment
gap (G-D) is visible in the Lab too rather than papered over with a drawn line.

Regenerate:  python3 mockups/refs/prophet_lab/tools/gen_lab_fixture.py
"""

from __future__ import annotations

import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
R4 = LAB.parent / "institutionalize" / "us_stocks"
OUT = LAB / "lab-data.js"

# ── the frozen product contract (LAB-0 §3). Board ids and detector/expert
#    identities are LAW: they are not renamed, re-split, merged, or reordered
#    here. The plain words are a DISPLAY projection over them; the exact
#    identity travels alongside and surfaces on the Tier-2 receipt. ──────────
BOARDS = [
    dict(
        id="lab-g0-v1",
        en="Earliest mark", zh="最早标记",
        sub_en="The first mark a detector puts on a name.",
        sub_zh="检测器给一只股票打上的第一个标记。",
        rc_en="Exact G0_GREY_DOT@1 events.",
        rc_zh="精确匹配 G0_GREY_DOT@1 事件。",
        want=lambda ex: any(e["det"] == "G0_GREY_DOT@1" for e in ex),
    ),
    dict(
        id="lab-c1-v1",
        en="Flush in progress", zh="急跌进行中",
        sub_en="A sharp sell-off that has not finished yet.",
        sub_zh="一轮尚未结束的急跌。",
        rc_en="C1_1D_LIVE_WASHOUT@1, current non-terminal episode only.",
        rc_zh="C1_1D_LIVE_WASHOUT@1，仅取当前未结束的回合。",
        want=lambda ex: any(e["det"] == "C1_1D_LIVE_WASHOUT@1" for e in ex),
    ),
    dict(
        id="lab-c2a-v1",
        en="Turning up", zh="开始转强",
        sub_en="The one turn reading we have watched longest.",
        sub_zh="我们观察时间最长的那一项转折读数。",
        rc_en="C2_1D_TURN@1 / c2a_kd_cross.",
        rc_zh="C2_1D_TURN@1 / c2a_kd_cross。",
        want=lambda ex: any(e["exp"] == "c2a_kd_cross" for e in ex),
    ),
    dict(
        id="lab-c2-variants-v1",
        en="Turning up — all readings", zh="开始转强 · 全部读数",
        sub_en="Six ways of reading the same turn. Each keeps its own name.",
        sub_zh="同一个转折的六种读法，每一种保留各自的名称。",
        rc_en="c2a_kd_cross, c2b_k_slope, c2c_higher_k_low, c2d_hist_trough, "
              "c2e_hist_curvature, c2f_rebound_atr — identities never merged.",
        rc_zh="c2a_kd_cross、c2b_k_slope、c2c_higher_k_low、c2d_hist_trough、"
              "c2e_hist_curvature、c2f_rebound_atr —— 身份不合并。",
        want=lambda ex: any(e["det"] == "C2_1D_TURN@1" for e in ex),
    ),
    dict(
        id="lab-g0-c2a-v1",
        en="Marked and turning", zh="已标记且转强",
        sub_en="Names that carry both the earliest mark and the turn.",
        sub_zh="同时带有最早标记和转折读数的股票。",
        rc_en="Display set intersection only. detector_id = null; this board "
              "mints zero events, episodes or scores.",
        rc_zh="仅为显示层集合求交。detector_id = null；本板不产生任何事件、"
              "回合或分数。",
        want=lambda ex: any(e["det"] == "G0_GREY_DOT@1" for e in ex)
        and any(e["exp"] == "c2a_kd_cross" for e in ex),
    ),
    dict(
        id="lab-all-early-v1",
        en="All early signs", zh="全部早期迹象",
        sub_en="Everything early, in one stream. One card can carry several readings.",
        sub_zh="所有早期迹象汇总为一条时间流。一张卡片可以带多项读数。",
        rc_en="Union of G0 + C1 + C2a–f. C3 and C5 are excluded in V1.",
        rc_zh="G0 + C1 + C2a–f 的并集。V1 不含 C3 与 C5。",
        want=lambda ex: True,
    ),
]

# expert identity → plain words. The slug NEVER reaches the glance tier
# (DESIGN_DOCTRINE §2 Law 2); it travels on the LENS receipt.
EXPERTS = {
    "g0_grey_dot":      ("G0_GREY_DOT@1",          "first mark",        "首个标记"),
    "c1_live_washout":  ("C1_1D_LIVE_WASHOUT@1",   "flush open",        "急跌未结束"),
    "c2a_kd_cross":     ("C2_1D_TURN@1",           "crossed up",        "指标上穿"),
    "c2b_k_slope":      ("C2_1D_TURN@1",           "slope turned up",   "斜率转正"),
    "c2c_higher_k_low": ("C2_1D_TURN@1",           "low held higher",   "低点抬高"),
    "c2d_hist_trough":  ("C2_1D_TURN@1",           "momentum bottomed", "动能触底"),
    "c2e_hist_curvature": ("C2_1D_TURN@1",         "momentum curling up", "动能上弯"),
    "c2f_rebound_atr":  ("C2_1D_TURN@1",           "bounce big enough", "反弹幅度够"),
}

MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_board() -> dict:
    src = (R4 / "board-data.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("{"): src.rindex("}") + 1])


def datewords(iso: str) -> dict:
    y, m, d = (int(x) for x in iso.split("-"))
    return {"iso": iso, "en": f"{MON_EN[m - 1]} {d}", "zh": f"{m}月{d}日"}


def daydelta(a: str, b: str) -> int:
    """calendar days a → b (both YYYY-MM-DD), positive when b is later"""
    import datetime
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def build() -> dict:
    B = load_board()
    rng = random.Random(20260818)                       # deterministic

    plans = {r["tk"]: r for r in B["rows"] if r["life"] != "resolved"}
    resolved = {r["tk"]: r for r in B["rows"] if r["life"] == "resolved"}
    sparked = [r for r in B["rows"] if r.get("spark")]
    sparked.sort(key=lambda r: (-(r.get("pri") or 0), r["tk"]))
    plan_tk = {r["tk"] for r in B["rows"]}
    cand_only = sorted(
        {(c["tk"], c.get("nm"), c.get("sec")) for c in B["cand_rows"]
         if c["tk"] not in plan_tk}
    )

    board_day = B["asof"]                               # 2026-08-13, the frozen book
    # the Lab session is the day the fixture describes; the board it compares
    # against is the frozen book, so the Lab is legitimately one session ahead.
    lab_day = "2026-08-14"
    # THE LIVE BASELINE. LAB-0 §4: a historical event is a retrospective seed
    # unless it is proven newly observed AFTER a continuous live baseline. That
    # baseline is a date, so it is drawn on the spine as a dated marker — every
    # row above it was watched live, every row below it is history, and the
    # reader is told why rather than left to infer it from a chip.
    baseline = "2026-08-08"

    rows: list[dict] = []

    def add(tk, nm, sec, spark, px, cls, experts, sig_iso, seen_hm, prophet_row,
            seen_day=None):
        eid = f"LAB-{tk}-{sig_iso.replace('-', '')}"
        ex = []
        for slug in experts:
            det, en, zh = EXPERTS[slug]
            ex.append({"det": det, "exp": slug, "en": en, "zh": zh})
        first = None
        if cls == "live_forward":
            day = seen_day or lab_day
            first = {"iso": f"{day}T{seen_hm}:00-04:00", "hm": seen_hm,
                     "day": datewords(day)}
        pro = None
        if prophet_row is not None:
            opened = prophet_row.get("opened") or None
            pro = {
                "life": prophet_row["life"],
                "opened": opened,
                "pri": prophet_row.get("pri"),
            }
        lead = None
        if cls == "live_forward" and pro and pro["opened"]:
            # R5.1 / VTL-403: the lead is SIGNED and is emitted whenever it is
            # measurable, favourable or not. The R5 fixture wrote null for every
            # adverse case, which made the asymmetry invisible in the artifact
            # and left the adverse branch unphotographed — the generator's
            # convention was standing in for a guard. Positive = the Lab saw it
            # first; negative = Prophet's plan opened first; zero = same day.
            lead = daydelta(first["iso"][:10], pro["opened"]["iso"])
        rows.append({
            "id": eid, "tk": tk, "nm": nm, "sec": sec,
            "spark": spark, "px": px,
            "cls": cls,
            "first": first,
            "sig": datewords(sig_iso),
            # LAB-0 §4: known_ts is preserved only when the emitter supplied it.
            # It is never reconstructed — a seed prints an absent time, and that
            # absence is the honest rendering.
            "known": cls == "live_forward",
            "ex": ex,
            "pro": pro,
            "lead": lead,
            # the sort key and its stated basis (LAB-0 §3)
            "sort": (first["iso"] if first else f"{sig_iso}T00:00:00-04:00"),
            "basis": "first_seen" if first else "signal_ts",
        })

    # ── live-forward observations (6), spread across the live baseline's own
    #    week. Only these may ever show a measured lead, and between them they
    #    exhibit EVERY lead state the design has to be able to say:
    #      · a favourable measured lead  (+3 / +2 / +1 — the Lab saw it first)
    #      · a SAME-DAY result            ( 0 — neither was earlier)
    #      · an ADVERSE measured lead     (-3 — Prophet's plan opened first)
    #      · nothing to compare           (Prophet has no plan on the name)
    #    R5.1 / VTL-403: the R5 fixture produced only favourable magnitudes, so
    #    the adverse and same-day branches were unphotographed and the one-sided
    #    treatment was invisible in the artifact. A fixture that only ever
    #    flatters the system it measures is not a fixture, it is a brochure. ──
    by_tk = {r["tk"]: r for r in sparked}
    live_specs = [
        # (ticker, experts, sighting day, clock) — plan-open dates come from the
        # real payload, so every lead below is arithmetic on real Prophet dates
        ("DAR",  ["g0_grey_dot", "c2a_kd_cross"],                   "2026-08-09", "11:22"),
        ("MRK",  ["c1_live_washout", "c2d_hist_trough"],            "2026-08-10", "09:41"),
        ("KEYS", ["c2a_kd_cross", "c2c_higher_k_low"],              "2026-08-11", "13:58"),
        ("CVCO", ["c2a_kd_cross", "c2f_rebound_atr"],               "2026-08-12", "10:35"),
        ("FTI",  ["g0_grey_dot"],                                   "2026-08-13", "10:07"),
    ]
    for tk, ex, day, hm in live_specs:
        r = by_tk.get(tk)
        if r is None:                     # fixture drifted — fail loudly
            raise SystemExit(f"gen_lab_fixture: {tk} carries no spark in board-data.js")
        add(r["tk"], r.get("nm"), r.get("sec"), r.get("spark"), r.get("px"),
            "live_forward", ex, day, hm, r, seen_day=day)
    # two live-forward names Prophet has no plan for at all — the case the Lab
    # exists to show. Candidate-only tickers carry no spark in the payload, so
    # they render the printed null hero rather than a drawn one.
    for (tk, nm, sec), ex, day, hm in zip(
            cand_only[:2],
            [["g0_grey_dot", "c2a_kd_cross"], ["c2b_k_slope"]],
            ["2026-08-14", "2026-08-13"], ["09:52", "14:31"]):
        add(tk, nm, sec, None, None, "live_forward", ex, day, hm, None, seen_day=day)

    # ── retrospective seeds: every event that predates the live baseline
    #    (LAB-0 §4). They are the majority at commissioning, and that is the
    #    honest shape — a design that only worked when seeds were rare would
    #    fail on day one. ────────────────────────────────────────────────────
    seed_pool = [r for r in sparked if r["tk"] not in {x["tk"] for x in rows}]
    variants = ["c2a_kd_cross", "c2b_k_slope", "c2c_higher_k_low",
                "c2d_hist_trough", "c2e_hist_curvature", "c2f_rebound_atr"]
    seed_days = ["2026-08-07", "2026-08-07", "2026-08-06", "2026-08-06",
                 "2026-08-05", "2026-08-05", "2026-08-04", "2026-08-04",
                 "2026-08-03", "2026-07-31", "2026-07-31", "2026-07-30",
                 "2026-07-30", "2026-07-29", "2026-07-28", "2026-07-28"]
    for i, r in enumerate(seed_pool[:len(seed_days)]):
        ex = []
        if i % 3 == 0:
            ex.append("g0_grey_dot")
        if i % 4 == 1:
            ex.append("c1_live_washout")
        ex.append(variants[i % 6])
        if i % 5 == 2:
            ex.append(variants[(i + 2) % 6])
        add(r["tk"], r.get("nm"), r.get("sec"), r.get("spark"), r.get("px"),
            "seed", ex, seed_days[i], None, r)
    # seeds on names Prophet has already graded out — a real comparison state
    for i, (tk, r) in enumerate(list(resolved.items())[:3]):
        add(tk, r.get("nm"), r.get("sec"), r.get("spark"), r.get("px"),
            "seed", ["g0_grey_dot", variants[i % 6]],
            ["2026-08-06", "2026-08-01", "2026-07-27"][i], None, r)
    # seeds on names outside the plan book entirely
    for i, (tk, nm, sec) in enumerate(cand_only[2:6]):
        add(tk, nm, sec, None, None, "seed",
            [["g0_grey_dot"], ["c1_live_washout", "c2a_kd_cross"],
             ["c2e_hist_curvature"], ["g0_grey_dot", "c2a_kd_cross"]][i],
            ["2026-08-07", "2026-08-02", "2026-07-29", "2026-07-26"][i], None, None)

    rows.sort(key=lambda r: (r["sort"], r["tk"]), reverse=True)

    boards = []
    for b in BOARDS:
        ids = [r["id"] for r in rows if b["want"](r["ex"])]
        boards.append({k: b[k] for k in
                       ("id", "en", "zh", "sub_en", "sub_zh", "rc_en", "rc_zh")}
                      | {"rows": ids})

    return {
        # the Lab feed's own generation, NOT the plan book's as-of. Printing the
        # book's stamp over Lab rows would be a lie about a different producer.
        "gen": {"iso": f"{lab_day}T15:04:00-04:00", "hm": "15:04",
                "day": datewords(lab_day)},
        "stale_gen": {"iso": f"{lab_day}T11:36:00-04:00", "hm": "11:36",
                      "day": datewords(lab_day), "behind_min": 208},
        "baseline": datewords(baseline),
        "book_asof": board_day,
        # LAB-0 §5: the API's authority block, all false, end to end.
        "authority": {"rank": False, "gate": False, "size": False,
                      "originate": False, "mutate_prophet": False},
        "source": {"pack": "entry_radar.live_pack/v2",
                   "event": "mastermind.entry_event.v1",
                   "kill": "PROPHET_LAB_DISABLED"},
        "boards": boards,
        "rows": rows,
        "synthetic": True,
    }


def main() -> int:
    data = build()
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(
        "/* GENERATED — Prophet Operator Lab fixture (D-LAB-R5).\n"
        "   SYNTHETIC LAB PLANE: detector, timing, first-observation and\n"
        "   observation-class facts are fabricated — Radar's live transport\n"
        "   (R-LAB-1 / W4.1) has not landed, so no canonical event stream\n"
        "   exists to extract. Marked data-mock-lab in the DOM.\n"
        "   REAL, from the committed R4 payload: ticker, name, sector, the\n"
        "   spark SVG (only ever on the ticker it was drawn for), and the\n"
        "   Prophet lifecycle/plan-open comparison.\n"
        "   Regenerate: python3 tools/gen_lab_fixture.py */\n"
        "window.PROPHET_LAB = " + body + ";\n",
        encoding="utf-8",
    )
    n = len(data["rows"])
    lf = sum(1 for r in data["rows"] if r["cls"] == "live_forward")
    print(f"lab-data.js: {n} observations · {lf} live-forward · {n - lf} seeds")
    for b in data["boards"]:
        print(f"  {b['id']:24s} {len(b['rows']):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
