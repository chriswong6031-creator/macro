"""The board track-record chip + popup on china_stocks.html (CN-1 §W6-CN).

RETRACKED 2026-07-20 for the Track-record popup revamp: the honest forward ledger
no longer renders as an always-open inline .nb-track panel — it is now the shared
receipt chip + dialog (templates/_track_record_dlg.html.j2), included from china.html.j2
with a `trd` dict. These pins verify the CN block maps board_track → the right `trd`
state (scored / interim / accruing), passes the semantic .pos/.neg classes so the zh
up-red/down-green flip stays automatic, folds the partial-session disclosure into the
merged footnote, and never puts t() inside an HTML attribute.
"""
import re
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent


def _render_block(setups: dict) -> str:
    """Extract the BOARD TRACK RECORD block and render it with the real partial
    available (FileSystemLoader on templates/, so the {% include %} resolves)."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index("{# ── BOARD TRACK RECORD")
    end = src.index("{% endif %}\n  </div>\n  {% endif %}", start)
    snippet = src[start:end] + "{% endif %}"

    from engine import i18n
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t, help=lambda *a, **k: "")
    # host t() macro is normally file-level; prepend it so the include inherits it
    macros = ('{%- macro t(en, zh="") -%}<span class="l-en">{{ en }}</span>'
              '<span class="l-zh">{{ zh if zh else en }}</span>{%- endmacro -%}\n')
    return env.from_string(macros + snippet).render(setups=setups)


def test_accruing_state_maps_to_chip():
    ledger = {
        "schema": "track_ledger/v1",
        "market": "CN",
        "as_of": "2026-06-30",
        "state": "accruing",
        "summary": {"horizon": 10, "n_logged": 120, "n_matured": 0},
        "rows": [],
        "meta": {"grain": "episode", "board_definition": "cn_prophet_v2"},
    }
    html = _render_block(setups={
        "board_definition": "cn_prophet_v2",
        "track_ledger": ledger,
        "coverage": {"data_through": "2026-06-30", "partial_session": False},
    })
    assert 'id="trd-btn"' in html and 'id="trd-dlg"' in html      # chip + dialog mount
    assert 'data-state="accruing"' in html                        # honest not-matured state
    assert 'data-market="cn"' in html


_CN_LEDGER = {
    "schema": "track_ledger/v1", "market": "CN", "as_of": "2026-07-24", "state": "scored",
    "summary": {"metric": "excess", "horizon": 10, "win_pct": 59.0, "expectancy_pct": 0.94,
                "avg_win_pct": 9.8, "avg_loss_pct": -12.1, "profit_factor": 1.21,
                "ci_lo_pct": 52.5, "ci_hi_pct": 67.7, "exp_lo_pct": -0.73, "exp_hi_pct": 3.01,
                "n_matured": 261, "n_inflight": 216, "n_board_days": 7, "median_hold": 10,
                "n_logged": 477, "n_locked_excluded": 1},
    "rows": [], "meta": {
        "grain": "episode",
        "board_definition": "cn_prophet_v2",
    },
}


def test_scored_state_reads_the_ledger_not_the_research_grade():
    """The chip must report the artifact the popup's table fetches.

    It used to read bt.by_horizon['21d'] — the board's own 21-session research grade —
    while the table below fetched cn_track_ledger.json at a 10-session horizon on
    episode grain. Two studies, one component. The `bt` here carries a DIFFERENT hit
    rate (0.575) from the ledger (59.0) so the binding is provable.
    """
    bt = {"available": True, "n_rows": 240, "dates": ["2026-06-30", "2026-07-01"],
          "grading": {"benchmark": "510300.SS", "relative": True, "entry_basis": "t1_hl2",
                      "marker_dates": "forbidden"},
          "by_horizon": {"21d": {"n": 40, "hit_vs_csi300": 0.575, "hit_ci": [0.42, 0.72],
                                 "median_excess": 0.018, "board_rank_ic": -0.12}}}
    html = _render_block(setups={"board_definition": "cn_prophet_v2",
                                 "board_track": bt, "track_ledger": _CN_LEDGER,
                                 "coverage": {"data_through": "2026-07-01", "partial_session": False}})
    assert 'data-state="scored"' in html
    assert "59% win" in html                                      # from the ledger
    assert "58%" not in html                                      # NOT the 21d research grade
    # semantic up/down classes routed to the partial (zh flip stays automatic)
    assert 'data-up-class="pos"' in html and 'data-dn-class="neg"' in html
    assert "CSI 300" in html or "CSI300" in html                  # benchmark stated
    # the short-record ribbon must fire: 7 board days is a thin independent sample
    assert "7 separate board days" in html


def test_scored_research_grade_does_not_render_without_matching_ledger():
    """A rich research grade must not impersonate the popup's absent ledger."""
    bt = {"available": True, "n_rows": 240, "dates": ["2026-06-30"],
          "grading": {"entry_basis": "t1_hl2"},
          "by_horizon": {"21d": {"n": 40, "hit_vs_csi300": 0.575, "hit_ci": [0.42, 0.72]}}}
    html = _render_block(setups={"board_definition": "cn_prophet_v2",
                                 "board_track": bt,
                                 "coverage": {"data_through": "2026-07-01", "partial_session": False}})
    assert 'id="trd-btn"' not in html
    assert "58%" not in html


def test_partial_session_folds_into_footnote():
    ledger = {
        **_CN_LEDGER,
        "state": "accruing",
        "summary": {"horizon": 10, "n_logged": 120, "n_matured": 0},
    }
    html = _render_block(setups={"board_definition": "cn_prophet_v2",
                                 "track_ledger": ledger,
                                 "coverage": {"data_through": "2026-07-02", "partial_session": True}})
    # the disclosure moves into the ONE merged footnote (Law 4), not a stacked strip
    assert "not yet logged" in html.lower() or "未记录" in html


def test_no_t_call_inside_attributes():
    """The i18n gotcha: t() must never sit inside an HTML attribute (dual-span breaks there)."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index("{# ── BOARD TRACK RECORD")
    end = src.index("{% endif %}\n  </div>\n  {% endif %}", start)
    snippet = src[start:end]
    assert not re.search(r'(?:title|style|data-[a-z]+|aria-[a-z]+)="[^"]*\{\{\s*t\(', snippet)
