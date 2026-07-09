"""CN Pick Lab HTML renderer.

Builds the view-model (VM) from site/labdata/china_pick_lab.json and renders
site/china_stocks_lab.html via Jinja2 (FileSystemLoader on templates/).

Public API:
    build_vm(cn_pick_lab_dict) -> dict
    render_page(vm, site=None) -> None   # writes site/china_stocks_lab.html

The dict may be None or empty (empty-state render; the page ships the honest
"first accrual tonight" hero and works with zero data).

Authority: all rows are display_only per CNPL-R1.
No Long-Hold tab per CNPL-R10.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

log = logging.getLogger("pick_lab.render_cn")

# --------------------------------------------------------------------------- #
#  View-model formatters (mirror render.py idiom)                              #
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
    """Add display-formatted fields to a CN scoreboard row."""
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
    r["skipped_unfillable_fmt"] = _fmt_int(r.get("skipped_unfillable"))
    r["months_span_fmt"] = (
        f"{r['months_span']:.1f}" if r.get("months_span") is not None else "—"
    )
    r["status_badge"] = _status_badge(r.get("status"))
    # is_random: pin cnlab_random_ctrl as yardstick row
    r["is_random"] = r.get("engine_id") == "cnlab_random_ctrl"
    # is_inverse: cnlab_chase_avoid is scored as avoid-accuracy (NOT a buy)
    r["is_inverse"] = r.get("engine_id") == "cnlab_chase_avoid"
    # data_gap: store-dependent books (cnlab_block_discount, cnlab_lhb_inst)
    r["has_data_gap"] = bool(r.get("data_gap"))
    return r


def _enrich_pick(pick: dict) -> dict:
    """Add display fields to a pick card dict."""
    p = dict(pick)
    c = p.get("close")
    # CN prices in ¥
    p["close_fmt"] = f"¥{c:.2f}" if c is not None else "—"
    # board chip label for limit state
    ls = p.get("limit_state")
    if ls == "sealed_up":
        p["limit_chip_en"] = "sealed ↑"
        p["limit_chip_zh"] = "封涨停"
        p["limit_chip_css"] = "chip-warn"
    elif ls == "sealed_down":
        p["limit_chip_en"] = "sealed ↓"
        p["limit_chip_zh"] = "封跌停"
        p["limit_chip_css"] = "chip-down"
    elif ls == "hit_up":
        p["limit_chip_en"] = "hit ↑"
        p["limit_chip_zh"] = "涨停"
        p["limit_chip_css"] = "chip-up"
    elif ls == "hit_down":
        p["limit_chip_en"] = "hit ↓"
        p["limit_chip_zh"] = "跌停"
        p["limit_chip_css"] = "chip-down"
    else:
        p["limit_chip_en"] = None
        p["limit_chip_zh"] = None
        p["limit_chip_css"] = None
    return p


def _enrich_fire(fire: dict) -> dict:
    """Add display fields to a recent-fire dict."""
    f = dict(fire)
    f["ret21_excess_fmt"] = _fmt_pct(f.get("ret21_excess"), signed=True)
    f["matured_label"] = "matured" if f.get("matured") else "open"
    f["fill_basis_label"] = f.get("fill_basis") or "—"
    return f


# --------------------------------------------------------------------------- #
#  CN velocity book ids (Family B, books 5–8)                                  #
# --------------------------------------------------------------------------- #

_CN_VELOCITY_BOOK_IDS = [
    "cnlab_1d_pure",
    "cnlab_1d_phase",
    "cnlab_1d_participation",
    "cnlab_1d_blastoff",
]

# Books that need runner-local stores (CNPL-R9: data_gap flag on scoreboard)
_DATA_GAP_BOOKS = {"cnlab_block_discount", "cnlab_lhb_inst"}


def build_vm(cn_pick_lab_dict: dict | None) -> dict:
    """Build the Jinja2 view-model for china_stocks_lab.html.

    Dict can be None (empty state) or fully populated per spec §5 schema.
    Returns a vm dict safe to pass directly to the template.

    Authority: display_only throughout (CNPL-R1).
    No Long-Hold tab (CNPL-R10).
    """
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    empty = not cn_pick_lab_dict

    # ---- scoreboard ----
    raw_board = []
    if cn_pick_lab_dict:
        raw_board = cn_pick_lab_dict.get("scoreboard") or []
    scoreboard = [_enrich_scoreboard_row(r) for r in raw_board]

    # ---- aggregate skipped_unfillable for header display ----
    total_skipped = None
    if cn_pick_lab_dict:
        ts = cn_pick_lab_dict.get("total_skipped_unfillable")
        if ts is not None:
            total_skipped = int(ts)

    # ---- 1D velocity books (Family B) ----
    books_raw: dict = {}
    if cn_pick_lab_dict:
        books_raw = cn_pick_lab_dict.get("books") or {}

    velocity_books: list[dict] = []
    for eid in _CN_VELOCITY_BOOK_IDS:
        b_data = books_raw.get(eid) or {}
        picks_today = [_enrich_pick(p) for p in (b_data.get("picks_today") or [])]
        recent_fires = [_enrich_fire(f) for f in (b_data.get("recent_fires") or [])]
        sb_meta = next((r for r in scoreboard if r.get("engine_id") == eid), {})
        velocity_books.append({
            "engine_id": eid,
            "name_en": sb_meta.get("name_en", eid),
            "name_zh": sb_meta.get("name_zh", eid),
            "family": sb_meta.get("family", "B"),
            "picks_today": picks_today,
            "recent_fires": recent_fires,
            "sb": sb_meta,
            "data_gap": bool(b_data.get("data_gap")),
        })

    # ---- all-books (for the "All Books" tab) ----
    all_books: list[dict] = []
    if cn_pick_lab_dict:
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
                "data_gap": bool(b_data.get("data_gap")),
                "is_inverse": row.get("is_inverse", False),
                "is_data_gap_book": eid in _DATA_GAP_BOOKS,
            })

    # ---- as_of ----
    as_of: str | None = None
    if cn_pick_lab_dict:
        as_of = cn_pick_lab_dict.get("as_of")
    method_note: str = (cn_pick_lab_dict or {}).get("method_note") or ""

    return {
        "built": built,
        "empty": empty,
        "as_of": as_of,
        "scoreboard": scoreboard,
        "velocity_books": velocity_books,
        "all_books": all_books,
        "total_skipped_unfillable": total_skipped,
        "method_note": method_note,
        # Display-only invariant — never drives selection / scoring
        "authority": "display_only",
    }


# --------------------------------------------------------------------------- #
#  Page renderer                                                               #
# --------------------------------------------------------------------------- #

def render_page(vm: dict, site: Path | None = None) -> None:
    """Render site/china_stocks_lab.html from vm (output of build_vm)."""
    site = site or (config.ROOT / "site")
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    html = env.get_template("china_stocks_lab.html.j2").render(**vm)
    out = site / "china_stocks_lab.html"
    write_page(out, html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)


# --------------------------------------------------------------------------- #
#  Convenience entry point                                                     #
# --------------------------------------------------------------------------- #

def build_and_render(site: Path | None = None) -> None:
    """Load committed site artifacts and render the CN lab page.

    Called from scripts/build_china_pick_lab.py after it writes the JSON artifact.
    Never raises — a render failure must not break the asia-lane flow.
    """
    site = site or (config.ROOT / "site")
    labdata = site / "labdata"

    cn_dict: dict | None = None

    def _load(name: str) -> dict | None:
        p = labdata / name
        if not p.exists():
            return None
        try:
            import json
            return json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("cn pick_lab render: could not load %s (%s)", name, exc)
            return None

    cn_dict = _load("china_pick_lab.json")

    vm = build_vm(cn_dict)
    try:
        render_page(vm, site)
    except Exception as exc:  # noqa: BLE001
        log.warning("cn pick_lab render: page render failed (%s)", exc)
