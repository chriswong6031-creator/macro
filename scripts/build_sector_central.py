"""Build the US Sector Central Intelligence dashboard -> site/sector_central.html.

The consolidation hub: engine.sector_central fuses the cycle map + the VALIDATED absolute-trend
drawdown gate + the macro regime posture + the (audited) momentum / heat / crowding CONTEXT into
one per-sector conviction read with a reasoning trace. This script emits the data JS
(window.SECTOR_CENTRAL), the raw JSON, runs the self-grader (append today's calls + grade matured
ones), and renders the page. It links + embeds the four sub-dashboards it sits above (Sector
Cycles overlay + Sector Heatmap scorecard embedded; Thematic Baskets + Narrative Rotation linked).

Additive — any failure logs and returns 0 so it never breaks the rest of the build.
Run: python -m scripts.build_sector_central
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_sector_central")


#: Board lanes that carry the reduce-side read. The graduation-gap chip only ever
#: belongs on these — a name the cycle organ reads as recovering while the longer
#: trend still says reduce. Stamping it on a buy-side lane would invert its meaning.
_REDUCE_SIDE_LANES = ("take_profits", "avoid", "hold")


# ── ACT-NOW BOARD TIER GATE (docs/TIER_PREVIEW_PATTERN.md) ───────────────────
# templates/_us_act_now_board.html.j2 is SHARED with us_stocks.html, where PR
# #5846 gave it the three-shape split (full / gated shell / rows-only). That gate
# is driven by build_site and reached only that page: this host passed no `pgate`,
# so sector_central.html kept server-rendering all five lanes in full to anonymous
# readers — 45 `.actitem` rows, measured live 2026-08-17 — and the us_stocks gate
# merely moved the same rows one click away. This page never loads
# tier_preview.js either, so there was no client-side overlay here to soften it.
#
# Same mechanism, its OWN payload. The board arrives here through the reader
# pattern (site/basketdata/action_board.json, written by an earlier build_site
# run), so this page is rendered by a different script at a different time from a
# possibly older generation of the artifact. Sharing site/premiumdata/us_stocks.json
# would make whichever builder ran last silently overwrite the other's rows, so
# the withheld remainder ships as site/premiumdata/sector_central.json. Both are
# under the /premiumdata/ prefix that config/site_access.yml already enforces at
# premium.enforced_early, so no policy change is needed for a NEW file there.
_SC_PAYLOAD_DIR = "premiumdata"
_SC_PAYLOAD_NAME = "sector_central.json"
#: Page-relative, because sector_central.html sits at the site root.
_SC_PAYLOAD_URL = "premiumdata/sector_central.json"

#: lane key -> (the .actbody id its rows were sliced out of, does the lane wrap
#: theme rows in the TS-R5 data-theme-id div?). Deliberately a COPY of
#: scripts/build_site.py::_US_ACTNOW_LANES rather than an import: build_site pulls
#: plotly at module scope, and importing it here would drag the whole page stack
#: into this fail-soft builder and out of the import-light CI lane. The two tables
#: and the template's own fold ids are pinned together by
#: tests/test_sector_central_gate.py::test_lane_table_matches_build_site (and
#: ::test_lane_ids_exist_in_template), so a drift is a red, not a silent leak.
_ACTNOW_LANES = [
    ("buy_now", "ab-buy-fold", False),
    ("buy_soon", "ab-soon-fold", False),
    ("on_the_run", "ab-run-fold", False),
    ("take_profits", "ab-trim-fold", False),
    ("hold", "dash-hold-fold", True),
    ("avoid", "dash-hold-fold", True),
]


def _gate_cfg() -> dict:
    """The `sector_central_gate` switch. Never raises: a missing or malformed
    block leaves the board UNGATED, which is the pre-gate behaviour — this
    builder is additive-and-never-fatal by contract, and a crash here would cost
    the whole page."""
    try:
        cfg = config.load().get("sector_central_gate") or {}
        return {"gated": bool(cfg.get("gated", False)),
                "preview_rows": int(cfg.get("preview_rows") or 3)}
    except Exception as e:  # noqa: BLE001
        log.warning("sector_central: gate config unreadable (%s) — board ungated", e)
        return {"gated": False, "preview_rows": 3}


def split_actnow(action_board: dict | None, preview: int, *, gated: bool = True):
    """Tier-preview split for the Act-Now board. Returns (pgate, locked).

    Pure in `action_board` — the caller hands the SAME dict to the page render,
    which re-derives its own preview slices in-template from `pgate` so the lane
    headings and empty-state branches keep reading the FULL lists (the counts and
    the state are what stays free; only the names are paid).

    `locked` is the [{lane, rows, wrap}] list the include consumes in its
    rows-only shape, keyed by the `.actbody` id each row was sliced out of.

    Returns (None, []) when nothing is withheld anywhere — a board at or under
    the preview cap ships whole, because a wall over nothing is worse than no
    wall, and an ungated page must stay byte-identical to the pre-gate one.
    """
    if not gated or not isinstance(action_board, dict):
        return None, []
    preview = max(0, int(preview))
    locked: list[dict] = []
    total = 0
    hold_shown = 0
    for key, dest, wrap in _ACTNOW_LANES:
        rows = list(action_board.get(key) or [])
        total += len(rows)
        # Stand aside is ONE .actbody fed by hold+avoid, so the lane's budget is
        # spent on `hold` first and `avoid` takes the remainder — exactly how the
        # template slices it, or the two halves would disagree about what shipped.
        budget = max(0, preview - hold_shown) if key == "avoid" else preview
        shown = rows[:budget]
        if key == "hold":
            hold_shown = len(shown)
        if len(rows) > len(shown):
            locked.append({"lane": dest, "rows": rows[len(shown):], "wrap": wrap})
    if not locked:
        return None, []
    n_locked = sum(len(L["rows"]) for L in locked)
    pgate = {
        "tier": "essential",
        "payload": _SC_PAYLOAD_URL,
        "preview": preview,
        "actnow": {"preview": preview, "locked": n_locked, "total": total},
    }
    return pgate, locked


def write_payload(env, site: Path, pgate: dict | None, locked: list[dict],
                  action_board: dict | None, *, built: str = "") -> None:
    """Write the withheld Act-Now rows to site/premiumdata/sector_central.json.

    ALWAYS written, including the ungated / nothing-withheld case: a night whose
    board shrank below the cap would otherwise leave YESTERDAY's payload in place
    for a paying reader to hydrate rows that are no longer on tonight's board.

    The rows are rendered from the SAME include the shell renders, in its
    rows-only (`ab_locked`) shape, so the hydrated page and a full server render
    cannot drift apart. Never fatal: a render that raises ships an empty block and
    the rows simply stay withheld, which is what a locked reader sees anyway.
    """
    path = site / _SC_PAYLOAD_DIR / _SC_PAYLOAD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema": "tier_payload.v1", "page": "sector_central",
                     "gated": bool(pgate), "required_tier": "essential",
                     "built": built}
    if pgate:
        payload["panels"] = {"actnow": pgate["actnow"]}
        try:
            payload["actnow_html"] = env.get_template(
                "_us_act_now_board.html.j2").render(
                    action_board=action_board, ab_locked=locked)
        except Exception as e:  # noqa: BLE001 — a payload must not abort the build
            log.error("sector_central: locked act-now render failed (%s)", e)
            payload["actnow_html"] = ""
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                    encoding="utf-8")
    log.info("sector_central: premium payload %s (%d withheld row(s))",
             _SC_PAYLOAD_URL,
             sum(len(L["rows"]) for L in locked))


def build_bottoming_context(act_now: dict | None, action_board: dict | None) -> dict | None:
    """Slice the bottoming-watch payload for the page and stamp the recovering chip.

    Two halves of the W-A lane (#4599 + Amendment 1 #4614), both display-tier:

    * the **lane** — `bottoming_watch` rows render as the watch strip under the five
      action lanes (templates/_us_bottoming_watch.html.j2);
    * the **graduation-gap chip** — `recovering_ids` name reduce-side rows the cycle
      organ reads as recovering off a low but which have already LEFT the bottoming
      lane. Those rows are on no lane, which is the whole reason the chip exists, so
      the chip is stamped onto the board's own rows here rather than in the strip.

    This is the join point on purpose: build_sector_central is the only place that
    holds BOTH artifacts (basketdata/baskets.json and basketdata/action_board.json).
    The board's own docstring establishes the pattern — "every per-row field is
    pre-merged onto each item" — so the template stays a renderer.

    The chip's words ship from the engine (`bottoming_authority`) so the page cannot
    drift from the measured basis; an older artifact without them stamps nothing
    rather than a blank chip. `action_board` is mutated in place (adding
    `recovering_chip_*`); returns None when there is no lane payload at all.
    """
    if not isinstance(act_now, dict):
        return None
    rows = act_now.get("bottoming_watch")
    if rows is None:
        return None

    auth = act_now.get("bottoming_authority") or {}
    out: dict = {
        "bottoming_watch": rows,
        "dual_read_ids": act_now.get("dual_read_ids") or [],
        "recovering_ids": act_now.get("recovering_ids") or [],
        "bottoming_authority": auth,
        "recovering_rendered": False,
    }

    chip_en = (auth.get("recovering_chip_en") or "").strip()
    if not chip_en or not isinstance(action_board, dict) or not out["recovering_ids"]:
        return out
    chip_zh = (auth.get("recovering_chip_zh") or "").strip() or chip_en
    tip_en = (auth.get("recovering_tip_en") or "").strip()
    tip_zh = (auth.get("recovering_tip_zh") or "").strip() or tip_en

    try:
        from engine.us_act_now import canonical_id
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_central: recovering chip skipped (%s)", e)
        return out

    #: Both id spellings ride recovering_ids ('b-gold_miners' AND 'gold_miners');
    #: canonicalising collapses them so a row matches on either. Sector rows key on
    #: the SPDR ticker, theme rows on the theme id — hence the case-fold.
    want = {canonical_id(str(i)).lower() for i in out["recovering_ids"] if str(i).strip()}
    stamped = 0
    for lane in _REDUCE_SIDE_LANES:
        for item in action_board.get(lane) or []:
            if not isinstance(item, dict) or item.get("recovering_chip_en"):
                continue
            keys = {
                canonical_id(str(item.get(k))).lower()
                for k in ("slug", "ticker") if item.get(k)
            }
            if not (keys & want):
                continue
            item["recovering_chip_en"] = chip_en
            item["recovering_chip_zh"] = chip_zh
            item["recovering_tip_en"] = tip_en
            item["recovering_tip_zh"] = tip_zh
            stamped += 1
    out["recovering_rendered"] = stamped > 0
    if out["recovering_ids"] and not stamped:
        #: The ids exist but nothing on the board matched them — the footnote would
        #: otherwise explain a chip that is not on the page.
        log.info(
            "sector_central: %d recovering id(s) matched no reduce-side board row",
            len(want),
        )
    return out


def _fmt_money_mn(v: float | None) -> str:
    """$ millions -> human string: 1234 -> +$1.2B, -87 -> -$87M, None -> —."""
    import math
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    sign = "+" if v >= 0 else "−"
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    return f"{sign}${a:.0f}M"


def _flows_section_html() -> str | None:
    """Server-rendered 'Where sector-ETF money is flowing' board: a multi-window
    (1D/3D/1W/2W/1M) flow heatmap across the 11 sector SPDRs, sorted by the widest
    window, with a net-of-complex row. Replaces the day-by-day grid that used to
    live on us_stocks.html. Returns None until flow history exists."""
    from collectors.sponsors import sector_flow_periods
    from engine.i18n import t
    from engine.playbook import SECTOR_NAMES
    data = sector_flow_periods()
    if not data or not data.get("rows"):
        return None
    labels = data["labels"]
    rows = data["rows"]
    net = data["net"]
    # per-window max-abs for the heat tint (the net row is excluded so one big
    # complex-wide window doesn't wash every cell out)
    maxabs = {lbl: max((abs(r["vals"].get(lbl) or 0.0) for r in rows), default=0.0)
              for lbl in labels}
    widest = labels[-1]
    rows = sorted(rows, key=lambda r: -(r["vals"].get(widest) or 0.0))

    def cell(v: float | None, lbl: str) -> str:
        if v is None:
            return "<td class='scf-c muted'>—</td>"
        cls = "pos" if v >= 0 else "neg"
        m = maxabs.get(lbl) or 0.0
        inten = min(1.0, abs(v) / m) if m else 0.0
        var = "--up" if v >= 0 else "--down"
        bg = (f"background:color-mix(in srgb, var({var}) "
              f"{6 + inten * 46:.0f}%, transparent)") if inten > 0.02 else ""
        return f"<td class='scf-c {cls}' style='{bg}'>{_fmt_money_mn(v)}</td>"

    head = "<th class='scf-s'>" + str(t("sector", "板块")) + "</th>" + "".join(
        f"<th class='scf-c'>{lbl}</th>" for lbl in labels)
    body = []
    for r in rows:
        name = SECTOR_NAMES.get(r["ticker"], r["ticker"])
        label = (f"<b>{r['ticker']}</b> <span class='muted'>"
                 f"{t(name, name)}</span>")
        body.append("<tr><td class='scf-s'>" + label + "</td>"
                    + "".join(cell(r["vals"].get(lbl), lbl) for lbl in labels)
                    + "</tr>")
    net_cells = "".join(cell(net.get(lbl), lbl) for lbl in labels)
    body.append("<tr class='scf-net'><td class='scf-s'><b>"
                + str(t("Net · 11 sector ETFs", "净额 · 11 个板块 ETF"))
                + "</b></td>" + net_cells + "</tr>")
    note = t(
        f"As of {data['asof']} · net creation/redemption flow (ΔShares × NAV) "
        f"summed over each window · positive = money in. Windows cap at the "
        f"{data['depth']} trading days collected so far (history builds from "
        f"June 2026), so the wider windows can coincide until more accrues. "
        f"Display-only.",
        f"截至 {data['asof']} · 各时间窗内份额申购／赎回净额（份额变动 × 资产净值）"
        f"求和 · 正值 = 资金流入。各窗口取目前已采集的 {data['depth']} 个交易日"
        f"（历史自 2026 年 6 月起累积），故在数据充足前较宽的窗口可能重合。仅作展示。")
    return (
        "<div class='scc-section-h' id='sc-flows'>"
        "<h2><span class='l-en'>Where sector-ETF money is flowing</span>"
        "<span class='l-zh'>板块 ETF 资金流向何处</span></h2>"
        "<span class='scc-section-sub'><span class='l-en'>Multi-day "
        "creation/redemption flow across the 11 sector SPDRs — read the rotation, "
        "not the daily noise</span><span class='l-zh'>覆盖 11 个板块 SPDR 的多日"
        "申购／赎回资金流 — 看轮动趋势，而非单日噪声</span></span></div>"
        "<div class='scf-wrap'><table class='scf'><thead><tr>" + head
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        "<p class='muted sm' style='margin:8px 2px 0'>" + str(note) + "</p></div>")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import sector_central as cc
        data = cc.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("sector_central engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("sector_central: no data — skipping")
        return 0

    # self-grader: append today's calls (PIT) + grade matured ones; attach the scorecard
    try:
        from engine import sector_central_grader as cg
        n_logged = cg.append_central_log(data)
        data["grader"] = cg.grade()
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("sector_central: grader failed: %s", e)
        data["grader"] = {"available": False, "note": "grader error"}

    payload = "window.SECTOR_CENTRAL=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (site / "sector_central_data.js").write_text(payload, encoding="utf-8")
    fdir = site / "sectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_central.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # autoescape=True: the merged Sector Intelligence template descends from the baskets
    # rvx template (written for an autoescaping env); flows_html is |safe-marked in-template.
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    try:
        flows_html = _flows_section_html()
    except Exception as e:  # noqa: BLE001 — additive embed, never fatal
        log.warning("sector_central: flow board failed (%s)", e)
        flows_html = None
    # Sector-intelligence handoff from build_baskets (hero verdict / factor-season chip /
    # money-flow verdict / member-symbol registry). Fail-soft: absent file → fallback hero.
    ctx: dict = {}
    try:
        ctx_p = site / "basketdata" / "si_handoff.json"
        if ctx_p.exists():
            ctx = json.loads(ctx_p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_central: theme_context handoff read failed (%s)", e)
    # Act-Now board (reader pattern) — build_site persists the SAME 5-lane board it renders
    # on us_stocks.html to site/basketdata/action_board.json (build_site runs earlier in the
    # engine job); read it fail-soft so an absent/corrupt file just renders the refreshing
    # fallback. The US board pre-merges every per-row field, so no separate lookup is needed.
    _action_board = None
    try:
        _ab_p = site / "basketdata" / "action_board.json"
        if _ab_p.exists():
            _action_board = (json.loads(_ab_p.read_text(encoding="utf-8")) or {}).get("action_board")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_central: action_board read failed (%s)", e)
    # W-A bottoming watch (reader pattern, same shape as the board above). The lane's
    # payload rides theme_intel.act_now in basketdata/baskets.json — written by
    # build_baskets, which runs earlier in the engine job. Read fail-soft: an absent or
    # older artifact renders the strip empty (or hides it), never a crash. This restores
    # the display half that #4642 dropped when it transplanted the us_stocks board over
    # sector_central's own five lanes; the engine and builder halves never stopped.
    _bottoming = None
    try:
        _bk_p = site / "basketdata" / "baskets.json"
        if _bk_p.exists():
            _bk = json.loads(_bk_p.read_text(encoding="utf-8")) or {}
            _bottoming = build_bottoming_context(
                ((_bk.get("theme_intel") or {}).get("act_now")), _action_board
            )
            if _bottoming is not None:
                log.info(
                    "sector_central: bottoming lane — %d row(s), %d dual-read id(s), "
                    "recovering chip %s",
                    len(_bottoming["bottoming_watch"]),
                    len(_bottoming["dual_read_ids"]),
                    "rendered" if _bottoming["recovering_rendered"] else "not on page",
                )
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_central: bottoming lane read failed (%s)", e)
    # ── TIER GATE (docs/TIER_PREVIEW_PATTERN.md). Split the board BEFORE the
    # render and write the withheld remainder to this page's own payload. The
    # split is the gate: the shell below bakes only the preview slice per lane,
    # so the paid rows are not in the shipped bytes at all.
    #
    # Ordered before the render, and the payload written unconditionally, so the
    # published pair can never disagree in the leaky direction — a payload that
    # failed to write leaves last night's rows behind a 401, while a shell that
    # failed to render keeps the last-good HTML (below) whose rows the payload
    # already matches.
    _sc_gate_cfg = _gate_cfg()
    _sc_pgate, _sc_locked = split_actnow(
        _action_board, _sc_gate_cfg["preview_rows"], gated=_sc_gate_cfg["gated"])
    _sc_built = ctx.get("generated_utc") or data.get("as_of") or ""
    try:
        write_payload(env, site, _sc_pgate, _sc_locked, _action_board,
                      built=_sc_built)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        # A payload we could not write must NOT be paired with a gated shell that
        # promises it: fall back to the ungated board rather than publish a page
        # whose withheld rows are unreachable for everyone, paying or not.
        log.error("sector_central: payload write failed (%s) — board ungated", e)
        _sc_pgate = None
    try:
        html = env.get_template("sector_central.html.j2").render(
            flows_html=flows_html,
            pgate=_sc_pgate,
            bottoming=_bottoming,
            theme_context=ctx.get("theme_context"),
            factor_season=ctx.get("factor_season"),
            flow=ctx.get("flow"),
            basket_member_syms=ctx.get("basket_member_syms") or [],
            action_board=_action_board,
            generated_utc=ctx.get("generated_utc") or data.get("as_of") or "")
        write_page(site / "sector_central.html", html, encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — a template error must NOT abort the daily engine job
        # The CI step that runs this is a bare `run:` (its claim "the builder returns 0 on any
        # failure" is only true if main() never raises), so an unguarded render here aborts the
        # whole engine job → no commit → stale site (this exact `t`-undefined crash, #624→#643).
        # Degrade: keep the last-good committed sector_central.html (the fresh data JS/JSON written
        # above still drive the page's runtime content) and return 0 so the rest of the build ships.
        log.exception("sector_central: page render failed (%s) — keeping last-good HTML", e)
        return 0

    # the page embeds the cycle-map overlay (window.SECTOR_CYCLES) + the heatmap scorecard →
    # ensure their shared assets are present. The cycles DATA (sector_cycles_data.js) is written
    # by build_sector_cycles, which must run before this; we copy the page assets and warn if
    # required runtime files are absent.
    import shutil
    for asset in ("product-nav-icons.css", "dashboard-icons.css", "dashboard-icons.js",
                  "sector_cycles.css", "sector_cycles.js",
                  # MOVEMENT donors extracted from the retired subsector_rotation page.
                  # subsector_rotation.js exports window.SRR, which time_machine.js needs.
                  "subsector_rotation.js", "rotation_events.js", "desk_watch.js",
                  "time_machine.js",
                  # _forming_narratives.html.j2 (end of MOVEMENT) loads this; the panel
                  # self-hides when basketdata/narrative_emergence.json is absent.
                  "forming_narratives.js",
                  # SI Workspace V2 shell: hash router, per-view lazy mount, view reads.
                  "si_workspace.js"):
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)
    for need in ("sector_cycles_data.js", "sector_cycles_series_data.js",
                 "sector_cycles_narr_data.js", "sector_cycles_dna_data.js",
                 "mm_charts.js", "cycle.css"):
        if not (site / need).exists():
            log.warning("sector_central: %s missing — embedded cycle chart needs "
                        "build_sector_cycles (+ build_cycle) to run first", need)
    if not (site / "heatmap.js").exists():
        log.warning("sector_central: heatmap.js missing — embedded heatmap scorecard needs "
                    "build_site to run first")

    log.info("built site/sector_central.html (%d sectors, %d baskets, %d calls logged, grader=%s)",
             len(data["sectors"]), len(data.get("baskets", [])), n_logged,
             (data.get("grader") or {}).get("available"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
