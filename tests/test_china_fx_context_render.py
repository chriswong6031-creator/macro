"""Render tests for the FX context block on the China Risk Radar dialog (MSX-1, Tier-2).

Tests that:
  - fx_context present → offshore-yuan row renders with the correct text
  - fx_context absent → the entire block is not rendered

MOVED 2026-08-11 (W1 of research/RISK_RADAR_COUNTRY_PORT_MASTERPLAN.md): the FX rows
used to be hand-rolled inside `#cnx-dlg-risk` in templates/china.html.j2 and this test
line-sliced them out by a comment marker. That dialog body is now the SHARED partial
templates/_risk_radar_dlg.html.j2 (one source for CN/HK/CA), so the test renders the
macro directly — no slicing, and the assertion now covers all three country pages.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent

# A minimally-complete radar payload: the macro embeds the shared .rrx card, which reads
# the odds fields, so a stub without them would exercise a different (card-suppressed)
# path than production. Shape mirrors engine/market_state.py `_radar_to_rd`.
_RD = {
    "state": "caution", "top_score": 55, "label_en": "Margin froth", "label_zh": "两融拥挤",
    "state_zh": "警戒", "do_en": "Trim chasing.", "do_zh": "减少追高。", "gross": None,
    "dd5": 0.06, "dd10": 0.12, "dd21": 0.24, "dd_lift": 1.3,
    "dd_base": {"h5": 0.036, "h10": 0.086, "h21": 0.178},
    "is_loud": True, "scares": [], "forward_log": None, "cycle": None, "counterread": None,
    "amp": 0, "amp_flags_en": [], "amp_flags_zh": [], "recovery": None, "track": None,
}


def _render(fxc: dict | None) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    tpl = env.from_string(
        '{% import "_risk_radar_dlg.html.j2" as rrd %}'
        "{{ rrd.risk_radar_dlg('cn', rd, none, ctx) }}"
    )
    ctx = {"fx": fxc} if fxc is not None else {}
    return tpl.render(rd=_RD, ctx=ctx)


class TestFxContextRender:
    def test_block_renders_offshore_yuan_row_when_present(self):
        """fx_context present → 'Yuan pressure' row renders."""
        fxc = {
            "cnh_basis_bps": -32.5,
            "cnh_basis_state": "neutral",
            "usd_dir": "weakening",
            "as_of": "2026-07-17",
            "stale": False,
        }
        html = _render(fxc)
        # section eyebrow
        assert "Currency backdrop" in html and "汇率背景" in html
        # Yuan pressure row
        assert "Yuan pressure" in html and "人民币压力" in html
        # Dollar row + the falling read (usd_dir=weakening)
        assert "Dollar" in html and "美元" in html
        assert "Falling" in html and "走弱" in html
        assert "A tailwind for this market" in html and "对本市场构成顺风" in html
        # basis bps chip
        assert "-32bp" in html or "-33bp" in html  # %.0f formatting of -32.5

    def test_block_absent_when_fx_context_missing(self):
        """fx_context absent → the block must not render any yuan/FX rows."""
        html = _render(None)
        assert "Yuan pressure" not in html
        assert "人民币压力" not in html
        assert "Currency backdrop" not in html
        assert "汇率背景" not in html

    def test_block_absent_when_fx_context_carries_no_readable_field(self):
        """A payload with neither a yuan state nor a dollar direction renders nothing —
        the section must not appear as an empty eyebrow with no rows."""
        html = _render({"as_of": "2026-07-17", "stale": False})
        assert "Currency backdrop" not in html
        assert "汇率背景" not in html

    def test_dollar_row_alone_renders_without_a_yuan_state(self):
        """HK/Canada carry no CNH basis — the dollar row must still render on its own."""
        html = _render({"usd_dir": "strengthening"})
        assert "Currency backdrop" in html
        assert "Yuan pressure" not in html and "人民币压力" not in html
        assert "Rising" in html and "走强" in html
        assert "A headwind for this market" in html and "对本市场构成逆风" in html
