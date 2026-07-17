"""Pick Lab HTML renderer.

Builds the view-model (VM) from site/labdata/pick_lab.json and
site/labdata/pick_lab_longhold.json, then renders site/us_stocks_lab.html
via Jinja2 (FileSystemLoader on templates/).

Public API:
    build_vm(pick_lab_dict, longhold_dict) -> dict
    render_page(vm, site=None) -> None   # writes site/us_stocks_lab.html

Either dict may be None or empty (empty-state render; the page ships the
honest "first accrual tonight" hero and works with zero data).

Authoritity: all rows are display_only per PL-R10.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

log = logging.getLogger("pick_lab.render")

# --------------------------------------------------------------------------- #
#  View-model builders                                                         #
# --------------------------------------------------------------------------- #

def _fmt_pct(v, decimals=1, signed=True):
    """Format a fractional float as a %-string, or '—' when None."""
    if v is None:
        return "—"
    s = f"{v * 100:.{decimals}f}%"
    if signed and v > 0:
        s = "+" + s
    return s


def _fmt_float(v, decimals=2, signed=True):
    if v is None:
        return "—"
    s = f"{v:.{decimals}f}"
    if signed and v > 0:
        s = "+" + s
    return s


def _fmt_int(v):
    if v is None:
        return "—"
    return str(int(v))


def _status_badge(status: str | None) -> dict:
    """Return {css, label_en, label_zh} for a status string."""
    s = (status or "accruing").lower()
    if "accruing" in s:
        return {"css": "badge-accruing", "label_en": "ACCRUING", "label_zh": "累积中"}
    if "active" in s or "pass" in s:
        return {"css": "badge-active", "label_en": "ACTIVE", "label_zh": "活跃"}
    return {"css": "badge-accruing", "label_en": "ACCRUING", "label_zh": "累积中"}


def _enrich_horizon_ladder(row: dict) -> dict:
    """Extract and format the per-horizon ladder fields (h5/h10/h21/h63).

    Returns a dict with keys:
        ladder: list of {horizon, wr_abs_fmt, wr_exc_fmt, med_exc_fmt, capture_fmt}
        path_en: plain-word EN path summary line
        path_zh: plain-word ZH path summary line
    All values are em-dash when the underlying data is null (grades not yet matured).
    """
    horizons = [
        ("h5",  "5d"),
        ("h10", "10d"),
        ("h21", "21d"),
        ("h63", "63d"),
    ]
    ladder = []
    for key, label in horizons:
        wr_abs = row.get(f"{key}_wr_abs")
        wr_exc = row.get(f"{key}_wr_exc")
        med_exc = row.get(f"{key}_med_exc")
        capture = row.get(f"{key}_capture")
        ladder.append({
            "horizon": label,
            "wr_abs_fmt": _fmt_pct(wr_abs, signed=False),
            "wr_exc_fmt": _fmt_pct(wr_exc, signed=True),
            "med_exc_fmt": _fmt_pct(med_exc, signed=True),
            "capture_fmt": _fmt_pct(capture, signed=False),
        })

    # Path summary (plain words)
    t_mfe = row.get("path25_med_t_mfe")       # median session of peak (1-based)
    t_mae = row.get("path25_med_t_mae")        # median session of trough
    mfe = row.get("path25_med_mfe")            # median best gain
    med_uw = row.get("path25_med_underwater")  # median fraction of sessions underwater
    mae = row.get("path25_med_abs_mae")        # median worst dip (absolute)
    pct_mae_first = row.get("path25_pct_mae_first")  # fraction where trough before peak

    # Build plain-word path line only when at least t_mfe is available
    if t_mfe is not None:
        t_mfe_int = int(round(t_mfe))
        mfe_pct = f"{mfe * 100:.1f}%" if mfe is not None else "—"
        mae_pct = f"{mae * 100:.1f}%" if mae is not None else "—"
        if pct_mae_first is not None:
            pct_first_int = int(round(pct_mae_first * 100))
            dip_timing = (
                f"dip usually before peak ({pct_first_int}% of cases)"
                if pct_mae_first >= 0.5
                else f"peak usually before dip ({100 - pct_first_int}% of cases)"
            )
            dip_timing_zh = (
                f"下跌通常早于峰值（{pct_first_int}%的情况）"
                if pct_mae_first >= 0.5
                else f"峰值通常早于下跌（{100 - pct_first_int}%的情况）"
            )
        else:
            dip_timing = "dip timing: —"
            dip_timing_zh = "下跌时机：—"

        path_en = (
            f"Peak typically day {t_mfe_int}; {dip_timing}; "
            f"median best gain {mfe_pct}; median worst dip −{mae_pct}"
        )
        t_mfe_zh = t_mfe_int
        path_zh = (
            f"峰值通常第{t_mfe_zh}日；{dip_timing_zh}；"
            f"中位最佳收益{mfe_pct}；中位最大回撤−{mae_pct}"
        )
    else:
        path_en = "Path data arriving as grades mature"
        path_zh = "路径数据随评级成熟而填入"

    return {"ladder": ladder, "path_en": path_en, "path_zh": path_zh}


def _enrich_scoreboard_row(row: dict) -> dict:
    """Add display-formatted fields to a scoreboard row from the JSON artifact."""
    r = dict(row)
    r["wr21_abs_fmt"] = _fmt_pct(r.get("wr21_abs"), signed=False)
    r["wr21_excess_fmt"] = _fmt_pct(r.get("wr21_excess"), signed=True)
    r["med_excess21_fmt"] = _fmt_pct(r.get("med_excess21"), signed=True)
    r["mfe_med_fmt"] = _fmt_pct(r.get("mfe_med"), signed=False)
    r["mae_med_fmt"] = _fmt_pct(r.get("mae_med"), signed=False)
    r["asym_fmt"] = _fmt_float(r.get("asym"), decimals=2, signed=False)
    r["nav_excess_cum_fmt"] = _fmt_pct(r.get("nav_excess_cum"), signed=True)
    r["max_dd_fmt"] = _fmt_pct(r.get("max_dd"), signed=False)
    r["vs_random_lift_fmt"] = _fmt_pct(r.get("vs_random_lift"), signed=True)
    r["vs_universe_lift_fmt"] = _fmt_pct(r.get("vs_universe_lift"), signed=True)
    r["n_fires_fmt"] = _fmt_int(r.get("n_fires"))
    r["n_open_fmt"] = _fmt_int(r.get("n_open"))
    r["n_dates_fmt"] = _fmt_int(r.get("n_dates"))
    r["months_span_fmt"] = (
        f"{r['months_span']:.1f}" if r.get("months_span") is not None else "—"
    )
    r["status_badge"] = _status_badge(r.get("status"))
    # is_random: pin plab_random_ctrl as the yardstick row
    r["is_random"] = r.get("engine_id") == "plab_random_ctrl"
    # is_inverse: plab_topping_avoid is scored as avoid-accuracy
    r["is_inverse"] = r.get("engine_id") == "plab_topping_avoid"

    # Task 1 — horizon ladder + capture + path detail
    r["horizon_detail"] = _enrich_horizon_ladder(r)

    # Task 2 — data_gap badge (plab_sector_trough, plab_revision_accel carry data_gap field)
    dg = r.get("data_gap")
    if dg and isinstance(dg, dict):
        r["data_gap_badge"] = {
            "present": True,
            "reason_en": dg.get("en", "Awaiting feed"),
            "reason_zh": dg.get("zh", "等待数据源"),
        }
    else:
        r["data_gap_badge"] = {"present": False}

    return r


def _enrich_pick(pick: dict) -> dict:
    """Add display fields to a pick card dict."""
    p = dict(pick)
    c = p.get("close")
    p["close_fmt"] = f"${c:,.2f}" if c is not None else "—"
    return p


def _enrich_fire(fire: dict) -> dict:
    """Add display fields to a recent-fire dict."""
    f = dict(fire)
    f["ret21_excess_fmt"] = _fmt_pct(f.get("ret21_excess"), signed=True)
    f["matured_label"] = "matured" if f.get("matured") else "open"
    return f


def _build_t0_vm(t0_dict: dict | None) -> dict:
    """Normalize a t0_indicator.v1 artifact into a vm sub-dict.

    Always returns a dict with at least {"present": bool}.
    Template can rely on vm["t0"] always existing.
    """
    if not t0_dict:
        return {"present": False, "as_of": None, "matches": [], "total": 0,
                "disclosure_en": "", "disclosure_zh": ""}
    matches_all = t0_dict.get("matches") or []
    return {
        "present": True,
        "as_of": t0_dict.get("as_of"),
        "matches": matches_all[:30],
        "total": len(matches_all),
        "disclosure_en": t0_dict.get("disclosure_en", ""),
        "disclosure_zh": t0_dict.get("disclosure_zh", ""),
    }


def _build_accountability_vm(scoreboard: dict | None) -> dict:
    """Normalise a us_audit_scoreboard.v1 artifact into a template-safe dict.

    Always returns a dict with at least {"present": bool}.
    Never raises; absent or corrupt JSON → {"present": False}.
    """
    if not scoreboard:
        return {"present": False}
    try:
        cov = scoreboard.get("coverage_monitor") or {}
        return {
            "present": True,
            "as_of": scoreboard.get("as_of"),
            "note": scoreboard.get("note") or "",
            "buy_lane_rows": scoreboard.get("buy_lane_rows") or 0,
            "all_lanes_rows": scoreboard.get("all_lanes_rows") or 0,
            "strata": scoreboard.get("strata") or {},
            "coverage_monitor": {
                "frozen_baseline": cov.get("frozen_baseline"),
                "trailing_4wk_buy_count": cov.get("trailing_4wk_buy_count"),
                "weekly_history": cov.get("weekly_history") or [],
                "data_gap": cov.get("data_gap"),
            },
            "gate_suppressed": scoreboard.get("gate_suppressed") or {},
        }
    except Exception:  # noqa: BLE001
        return {"present": False}


def _enrich_all_fires(fires_list: list[dict]) -> list[dict]:
    """Add display fields to a list of full-history fire dicts."""
    result = []
    for f in fires_list:
        row = dict(f)
        row["ret21_excess_fmt"] = _fmt_pct(row.get("ret21_excess"), signed=True)
        row["matured_label"] = "matured" if row.get("matured") else "open"
        result.append(row)
    return result


def build_vm(
    pick_lab_dict: dict | None,
    longhold_dict: dict | None,
    t0_dict: dict | None = None,
    audit_scoreboard: dict | None = None,
    fires_dict: dict | None = None,
) -> dict:
    """Build the Jinja2 view-model for us_stocks_lab.html.

    Both dicts can be None (empty state) or fully populated per the spec §4
    schema. Returns a vm dict safe to pass directly to the template.

    t0_dict: optional t0_indicator.v1 artifact (site/factordata/t0_indicator.json).
    audit_scoreboard: optional us_audit_scoreboard.v1 artifact (SA-W5 Accountability section).
    fires_dict: optional pick_lab_fires.v1 artifact (site/labdata/pick_lab_fires.json).
                Absent → all_fires: [] on every book (template hides the section).
    Authority: display_only throughout.
    """
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    empty = not pick_lab_dict

    # ---- regime scalars ----
    regime: dict = {}
    if pick_lab_dict:
        regime = pick_lab_dict.get("regime") or {}

    # ---- scoreboard ----
    raw_board = []
    if pick_lab_dict:
        raw_board = pick_lab_dict.get("scoreboard") or []
    scoreboard = [_enrich_scoreboard_row(r) for r in raw_board]

    # ---- 1D velocity picks (books 1-4) ----
    velocity_book_ids = [
        "plab_1d_pure",
        "plab_1d_regime",
        "plab_1d_sectorheat",
        "plab_1d_blastoff",
    ]
    books_raw: dict = {}
    if pick_lab_dict:
        books_raw = pick_lab_dict.get("books") or {}

    # ---- full-history fires (pick_lab_fires.json, graceful absent) ----
    fires_by_book: dict[str, list[dict]] = {}
    if fires_dict:
        fires_by_book = fires_dict.get("fires_by_book") or {}

    velocity_books: list[dict] = []
    for eid in velocity_book_ids:
        b_data = books_raw.get(eid) or {}
        picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
        recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
        all_fires_raw = fires_by_book.get(eid) or []
        # find scoreboard meta for this book
        sb_meta = next((r for r in scoreboard if r.get("engine_id") == eid), {})
        velocity_books.append({
            "engine_id": eid,
            "name_en": sb_meta.get("name_en", eid),
            "name_zh": sb_meta.get("name_zh", eid),
            "family": sb_meta.get("family", "A"),
            "picks_today": picks_today,
            "recent_fires": recent_fires,
            "all_fires": _enrich_all_fires(all_fires_raw),
            "sb": sb_meta,
        })

    # ---- on-the-run lane ----
    lanes: dict = {}
    if pick_lab_dict:
        lanes = pick_lab_dict.get("lanes") or {}
    otr_stocks = [_enrich_pick(p) for p in (lanes.get("on_the_run_stocks") or [])]
    tp_stocks = [_enrich_pick(p) for p in (lanes.get("take_profits_stocks") or [])]

    # ---- all-books (for the "All Books" tab) ----
    all_books: list[dict] = []
    if pick_lab_dict:
        for row in scoreboard:
            eid = row.get("engine_id", "")
            if row.get("horizon_role", "entry") != "entry":
                continue
            b_data = books_raw.get(eid) or {}
            picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
            recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
            all_fires_raw = fires_by_book.get(eid) or []
            all_books.append({
                "engine_id": eid,
                "name_en": row.get("name_en", eid),
                "name_zh": row.get("name_zh", eid),
                "family": row.get("family", ""),
                "picks_today": picks_today,
                "recent_fires": recent_fires,
                "all_fires": _enrich_all_fires(all_fires_raw),
                "sb": row,
            })

    # ---- long-hold ----
    lh_books_raw: dict = {}
    lh_as_of: str | None = None
    first_maturation_eta: str | None = None
    if longhold_dict:
        lh_books_raw = longhold_dict.get("books") or {}
        lh_as_of = longhold_dict.get("as_of")
        first_maturation_eta = longhold_dict.get("first_maturation_eta")

    # Task 3 — LH book list extended to 4 entries; LH-2 v1 flagged as no-gate control
    lh_book_ids = [
        ("plab_lh_compounder",           "LH Compounder Grid",              "长持复利网格",            False),
        ("plab_lh_edge_durability",      "LH EDGE Durability (no-gate control)", "长持EDGE耐久（无门控对照）", True),
        ("plab_lh_washout_survivor",     "LH Washout Survivor Grid",        "长持洗盘幸存网格",        False),
        ("plab_lh_edge_durability_b",    "LH EDGE Durability B (gated)",    "长持EDGE耐久B（有门控）",   False),
    ]
    lh_books: list[dict] = []
    for eid, en, zh, is_control in lh_book_ids:
        b_data = lh_books_raw.get(eid) or {}
        picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
        recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
        all_fires_raw = fires_by_book.get(eid) or []
        # Passthrough why-chips that pick rows may carry (e.g. 'dilution n/a', 'ic n/a')
        # _enrich_pick already passes the why list through; template renders them.
        lh_books.append({
            "engine_id": eid,
            "name_en": en,
            "name_zh": zh,
            "is_control": is_control,
            "picks_today": picks_today,
            "recent_fires": recent_fires,
            "all_fires": _enrich_all_fires(all_fires_raw),
        })

    # ---- as_of / method_note ----
    as_of: str | None = None
    if pick_lab_dict:
        as_of = pick_lab_dict.get("as_of")
    method_note: str = (pick_lab_dict or {}).get("method_note") or ""

    return {
        "built": built,
        "empty": empty,
        "as_of": as_of,
        "regime": regime,
        "scoreboard": scoreboard,
        "velocity_books": velocity_books,
        "otr_stocks": otr_stocks,
        "tp_stocks": tp_stocks,
        "all_books": all_books,
        "lh_books": lh_books,
        "lh_as_of": lh_as_of,
        "first_maturation_eta": first_maturation_eta or "~2027-01",
        "method_note": method_note,
        "t0": _build_t0_vm(t0_dict),
        # SA-W5: Accountability section data (display-only; absent → empty state)
        "accountability": _build_accountability_vm(audit_scoreboard),
        # Display-only invariant — never drives selection / scoring
        "authority": "display_only",
    }


# --------------------------------------------------------------------------- #
#  Page renderer                                                               #
# --------------------------------------------------------------------------- #

def _load_audit_scoreboard(site: Path) -> dict | None:
    """Load site/factordata/us_audit_scoreboard.json; never raises."""
    try:
        import json as _json
        p = site / "factordata" / "us_audit_scoreboard.json"
        if p.exists():
            return _json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


def render_page(vm: dict, site: Path | None = None) -> None:
    """Render site/us_stocks_lab.html from vm (the output of build_vm).

    SA-W5: if vm does not already contain 'accountability', or if it contains
    {"present": False} (the default emitted by build_vm when no audit_scoreboard
    arg was passed), load site/factordata/us_audit_scoreboard.json from disk and
    inject the real scoreboard.  Belt-and-suspenders: the builders should also
    pass audit_scoreboard explicitly (see build_pick_lab.py), but this fallback
    guarantees the committed JSON is never suppressed.
    """
    site = site or (config.ROOT / "site")
    # Inject accountability when absent OR when build_vm emitted the null sentinel
    _acct = vm.get("accountability")
    if "accountability" not in vm or (_acct is not None and not _acct.get("present")):
        vm = dict(vm)
        vm["accountability"] = _build_accountability_vm(_load_audit_scoreboard(site))
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    html = env.get_template("us_stocks_lab.html.j2").render(**vm)
    out = site / "us_stocks_lab.html"
    write_page(out, html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)


# --------------------------------------------------------------------------- #
#  Convenience entry point                                                     #
# --------------------------------------------------------------------------- #

def build_and_render(site: Path | None = None) -> None:
    """Load committed site artifacts and render the lab page.

    Called from scripts/build_pick_lab.py after it writes the JSON artifacts.
    Never raises — a render failure must not break the nightly flow.
    """
    site = site or (config.ROOT / "site")
    labdata = site / "labdata"

    pick_lab_dict: dict | None = None
    longhold_dict: dict | None = None

    def _load(name: str) -> dict | None:
        p = labdata / name
        if not p.exists():
            return None
        try:
            import json
            return json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("pick_lab render: could not load %s (%s)", name, exc)
            return None

    pick_lab_dict = _load("pick_lab.json")
    longhold_dict = _load("pick_lab_longhold.json")
    fires_dict = _load("pick_lab_fires.json")

    # Load T0 beta-screen artifact (separate path: site/factordata/)
    t0_dict: dict | None = None
    t0_path = site / "factordata" / "t0_indicator.json"
    if t0_path.exists():
        try:
            import json as _json
            t0_dict = _json.loads(t0_path.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("pick_lab render: could not load t0_indicator.json (%s)", exc)

    vm = build_vm(pick_lab_dict, longhold_dict, t0_dict=t0_dict, fires_dict=fires_dict)
    try:
        render_page(vm, site)
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab render: page render failed (%s)", exc)
