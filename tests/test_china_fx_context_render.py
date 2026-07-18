"""Render tests for the FX context block in china.html.j2 (MSX-1, Tier-2).

Tests that:
  - fx_context present → offshore-yuan row renders with the correct text
  - fx_context absent → the entire block is not rendered

Reuses the DictLoader pattern from test_china_board_track_render.py.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent


def _env_with_snippet() -> tuple[Environment, str]:
    """Extract the FX context block from china.html.j2 as a standalone snippet."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index("{# FX context row-pair")
    end = src.index('<div class="cnx-receipt">', start)
    snippet = src[start:end]

    # Minimal t() macro: emit both EN and ZH spans so we can assert on either
    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
    )
    full = macros + snippet

    env = Environment(loader=DictLoader({"blk": full}), autoescape=False)
    return env, full


def _render(fxc: dict | None) -> str:
    env, _ = _env_with_snippet()
    _rr = {"fx_context": fxc} if fxc is not None else {}
    return env.get_template("blk").render(_rr=_rr)


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
        # Yuan pressure row
        assert "Yuan pressure" in html or "人民币压力" in html
        # Dollar direction row
        assert "Dollar direction" in html or "美元方向" in html
        # Dollar falling copy (usd_dir=weakening)
        assert "Dollar falling" in html or "美元走弱" in html
        # basis bps chip
        assert "-32bp" in html or "-33bp" in html  # %.0f formatting of -32.5

    def test_block_absent_when_fx_context_missing(self):
        """fx_context absent → the block must not render any yuan/FX rows."""
        html = _render(None)
        assert "Yuan pressure" not in html
        assert "人民币压力" not in html
        assert "Dollar direction" not in html
        assert "FX context" not in html
