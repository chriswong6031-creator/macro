"""The board track-record block on china_stocks.html (CN-1 masterplan §W6-CN).

Pins that the honest forward ledger actually RENDERS (it was attached to china_standouts.json but zero
templates consumed it), that it degrades to an honest 'accruing' state until picks mature, uses the
semantic .pos/.neg classes (so the zh up-red/down-green flip is automatic), and never puts t() inside
an attribute.
"""
import re
from pathlib import Path

from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent


def _block_template() -> Environment:
    """Extract the nb-track block from china.html.j2 into a standalone renderable template."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index("{# ── BOARD TRACK RECORD")
    end = src.index("{% endif %}\n  </div>\n  {% endif %}", start)
    snippet = src[start:end] + "{% endif %}"
    from engine import i18n
    env = Environment(loader=DictLoader({"blk": snippet}), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t, help=lambda *a, **k: "")
    return env


def test_accruing_state_is_honest():
    bt = {"available": True, "n_rows": 120, "dates": ["2026-06-30"],
          "grading": {"entry_basis": "t1_hl2"},
          "by_horizon": {"21d": {"n": 0, "note": "accruing"}}}
    html = _block_template().get_template("blk").render(
        setups={"board_track": bt, "coverage": {"data_through": "2026-06-30", "partial_session": False}})
    assert "Accruing" in html and "2026-07-29" in html          # honest "not matured yet" + ETA
    assert "Board track record" in html


def test_matured_state_shows_hit_ci_and_semantic_classes():
    bt = {"available": True, "n_rows": 240, "dates": ["2026-06-30", "2026-07-01"],
          "grading": {"benchmark": "510300.SS", "relative": True, "entry_basis": "t1_hl2",
                      "marker_dates": "forbidden"},
          "by_horizon": {"21d": {"n": 40, "hit_vs_csi300": 0.575, "hit_ci": [0.42, 0.72],
                                 "median_excess": 0.018, "board_rank_ic": -0.12,
                                 "extended_fwd": -0.021, "not_extended_fwd": 0.033, "n_extended": 10}}}
    html = _block_template().get_template("blk").render(
        setups={"board_track": bt, "coverage": {"data_through": "2026-07-01", "partial_session": False}})
    assert "57%" in html                                        # hit rate
    assert "42–72%" in html                                     # Wilson CI
    assert 'class="pos"' in html                                # positive hit/excess → up color
    assert 'class="neg"' in html                                # extended-lags → down color
    assert "510300" in html or "CSI300" in html                 # benchmark stated
    assert "T+1" in html                                        # fill-realism disclosed


def test_partial_session_is_labelled():
    bt = {"available": True, "n_rows": 120, "dates": ["2026-07-02"],
          "grading": {"entry_basis": "t1_hl2"}, "by_horizon": {"21d": {"n": 0, "note": "accruing"}}}
    html = _block_template().get_template("blk").render(
        setups={"board_track": bt, "coverage": {"data_through": "2026-07-02", "partial_session": True}})
    assert "partial session" in html.lower()


def test_no_t_call_inside_attributes():
    """The i18n gotcha: t() must never sit inside an HTML attribute (dual-span breaks there)."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index("{# ── BOARD TRACK RECORD")
    end = src.index("{% endif %}\n  </div>\n  {% endif %}", start)
    snippet = src[start:end]
    assert not re.search(r'(?:title|style|data-[a-z]+|aria-[a-z]+)="[^"]*\{\{\s*t\(', snippet)
