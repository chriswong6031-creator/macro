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


def build_vm(
    pick_lab_dict: dict | None,
    longhold_dict: dict | None,
    t0_dict: dict | None = None,
    audit_scoreboard: dict | None = None,
) -> dict:
    """Build the Jinja2 view-model for us_stocks_lab.html.

    Both dicts can be None (empty state) or fully populated per the spec §4
    schema. Returns a vm dict safe to pass directly to the template.

    t0_dict: optional t0_indicator.v1 artifact (site/factordata/t0_indicator.json).
    audit_scoreboard: optional us_audit_scoreboard.v1 artifact (SA-W5 Accountability section).
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

    velocity_books: list[dict] = []
    for eid in velocity_book_ids:
        b_data = books_raw.get(eid) or {}
        picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
        recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
        # find scoreboard meta for this book
        sb_meta = next((r for r in scoreboard if r.get("engine_id") == eid), {})
        velocity_books.append({
            "engine_id": eid,
            "name_en": sb_meta.get("name_en", eid),
            "name_zh": sb_meta.get("name_zh", eid),
            "family": sb_meta.get("family", "A"),
            "picks_today": picks_today,
            "recent_fires": recent_fires,
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
            all_books.append({
                "engine_id": eid,
                "name_en": row.get("name_en", eid),
                "name_zh": row.get("name_zh", eid),
                "family": row.get("family", ""),
                "picks_today": picks_today,
                "recent_fires": recent_fires,
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

    lh_book_ids = [
        ("plab_lh_compounder", "LH Compounder Grid", "长持复利网格"),
        ("plab_lh_edge_durability", "LH EDGE Durability Grid", "长持EDGE耐久网格"),
        ("plab_lh_washout_survivor", "LH Washout Survivor Grid", "长持洗盘幸存网格"),
    ]
    lh_books: list[dict] = []
    for eid, en, zh in lh_book_ids:
        b_data = lh_books_raw.get(eid) or {}
        picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
        recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
        lh_books.append({
            "engine_id": eid,
            "name_en": en,
            "name_zh": zh,
            "picks_today": picks_today,
            "recent_fires": recent_fires,
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

    SA-W5: if vm does not already contain 'accountability', loads
    site/factordata/us_audit_scoreboard.json and injects it.
    """
    site = site or (config.ROOT / "site")
    # Inject accountability if the caller did not pre-load it
    if "accountability" not in vm:
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

    # Load T0 beta-screen artifact (separate path: site/factordata/)
    t0_dict: dict | None = None
    t0_path = site / "factordata" / "t0_indicator.json"
    if t0_path.exists():
        try:
            import json as _json
            t0_dict = _json.loads(t0_path.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("pick_lab render: could not load t0_indicator.json (%s)", exc)

    vm = build_vm(pick_lab_dict, longhold_dict, t0_dict=t0_dict)
    try:
        render_page(vm, site)
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab render: page render failed (%s)", exc)
