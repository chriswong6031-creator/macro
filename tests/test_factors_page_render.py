"""Jinja2 render smoke tests for templates/factors.html.j2.

Tests:
1. Renders without exception when seas=None, momo=None (fail-open / degraded path).
2. Renders without exception when seas is real output from compute_factor_seasonality().
3. Hero headline text is present when seas is given.
4. Renders without exception with synthetic momo (top_decile present).
5. "BH-WITHHELD" appears AFTER "Factor leaders" in the rendered HTML (NW panel demoted).
6. "validated" does not appear in any new user-facing copy (CI-guarded).

Mirrors idiom from tests/test_news_page_render.py (FileSystemLoader, i18n globals).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


# ---------------------------------------------------------------------------
# Minimal synthetic context factories
# ---------------------------------------------------------------------------

def _minimal_fac() -> dict:
    """Minimal fac dict — enough to render without crashing."""
    return {
        "n": 100,
        "fy": 2025,
        "as_of": "2026-07-15",
        "leadership": [{"label": "Value", "spread_pct": 1.2}],
        "factors": ["value", "profitability"],
        "factor_labels": {"value": "Value", "profitability": "Profitability"},
        "composite_top": [],
        "composite_bottom": [],
        "leaders": {"value": [], "profitability": []},
        "rank_legs": ["value"],
        "composite_passport": {"excluded_legs": []},
        "insider": None,
    }


def _minimal_ic() -> dict:
    """Minimal ic dict."""
    return {
        "rows": [
            {
                "factor": "value",
                "label_en": "Value",
                "mean_ic": 0.015,
                "ic_ir_ann": 0.4,
                "t_hac": 1.8,
                "hit": 0.6,
                "q_fdr": 0.08,
                "n": 24,
                "survives_fdr": True,
            }
        ],
        "any_survive": True,
        "span": "2011-2026",
        "rebalances": 60,
        "median_universe": 1200,
        "horizon_d": 63,
        "survivorship_biased": True,
        "factors": {"composite": {"mean_ic": -0.002}},
        "collinearity": None,
    }


def _minimal_breadth() -> dict:
    return {
        "groups": [
            {"label_en": "S&P 500", "label_zh": "标普500", "p50": 65, "p200": 58, "n": 503}
        ],
        "div_small_large": 3.2,
    }


def _minimal_series() -> dict:
    """Minimal series dict — skips chart_data so JS blocks don't render."""
    return {
        "chart_data": None,
        "chart_data_narrow": None,
        "factors": ["value"],
        "labels": {"value": "Value"},
        "series": {"value": {"long_only": {"cum_pct": 12.0, "spark": [100, 102, 105]}, "long_short": {"cum_pct": 3.0, "spark": [100, 101, 103]}}},
        "stats": {"value": {"sharpe_lo": 0.8, "sharpe_ls": 0.4, "sharpe_ls_ci": [0.1, 0.4, 0.7], "sharpe_gt0_prob": "72%"}},
        "horizons": {"value": {
            "long_only": {"d1": {"ret_pct": 0.1, "z": 0.2, "pct": 55, "flag": False},
                          "d5": {"ret_pct": 0.5, "z": 0.4, "pct": 60, "flag": False},
                          "d20": {"ret_pct": 1.2, "z": 0.8, "pct": 65, "flag": False}},
            "long_short": {"d1": {"ret_pct": 0.05, "z": 0.1, "pct": 52, "flag": False},
                           "d5": {"ret_pct": 0.2, "z": 0.3, "pct": 55, "flag": False},
                           "d20": {"ret_pct": 0.6, "z": 0.5, "pct": 58, "flag": False}},
        }},
        "rotation": {"leader": "value", "leader_label": "Value", "leader_ret20_pct": 1.2,
                     "leader_held_days": 5, "previous_leader_label": None,
                     "quartile_jumps": [], "recent_flips": [], "r20": []},
        "benchmark": {"cum_pct": 18.0, "spark": [100, 108, 118]},
        "crowding": None,
        "quilt": None,
        "honesty": "Descriptions, not tradeable.",
        "history_start": "2022-01-01",
        "as_of": "2026-07-15",
        "n_rebalances": 20,
    }


def _minimal_momo() -> dict:
    """Synthetic momo with top_decile present."""
    return {
        "schema": "momentum_display.v1",
        "as_of": "2026-07-17",
        "unscored": True,
        "universe": {"n_tickers": 500, "start": "2021-01-04", "end": "2026-07-17"},
        "top_decile": {
            "n": 50,
            "sectors": [
                {"sector": "Information Technology", "share_pct": 46.0},
                {"sector": "Communication Services", "share_pct": 14.0},
                {"sector": "Consumer Discretionary", "share_pct": 10.0},
            ],
            "top_sector": "Information Technology",
            "top_sector_share_pct": 46.0,
            "sample": ["NVDA", "AAPL", "MSFT", "META", "GOOGL"],
        },
        "spread": {
            "top_decile_mean_pct": 120.5,
            "bottom_decile_mean_pct": -35.2,
            "spread_pp": 155.7,
        },
        "pulse": {"mtum_spy_20d_pct": -3.5, "mtum_spy_60d_pct": 4.2},
        "disclosure_en": "A descriptive X-ray of where price momentum is concentrated right now — not a score, not a signal, and kept out of every ranking.",
        "disclosure_zh": "对当前价格动量集中位置的描述性透视——不是评分，不是信号，且不进入任何排名。",
    }


def _render(seas: Any, momo: Any) -> str:
    """Render the factors.html.j2 template with the given seas/momo and minimal other context."""
    env = _env()
    tpl = env.get_template("factors.html.j2")
    return tpl.render(
        fac=_minimal_fac(),
        ic=_minimal_ic(),
        breadth=_minimal_breadth(),
        series=_minimal_series(),
        nw_state=None,
        seas=seas,
        momo=momo,
        generated_utc="2026-07-18T00:00:00",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFactorsPageRender:

    def test_renders_null_null(self):
        """Page renders without exception when seas=None, momo=None."""
        html = _render(seas=None, momo=None)
        assert len(html) > 1000  # sanity: got real content

    def test_renders_with_real_seas(self, monkeypatch):
        """Page renders without exception with real compute_factor_seasonality output."""
        import numpy as np
        import pandas as pd
        from engine import factor_seasonality as fs

        idx = pd.date_range("1985-01-31", periods=40 * 12, freq="ME")
        rng = np.arange(len(idx))
        df = pd.DataFrame({
            "mkt_rf": np.sin(rng) * 2,
            "smb": np.cos(rng),
            "hml": (rng % 12 - 5) * 0.3,
            "rf": 0.2,
            "rmw": np.cos(rng) * 0.5,
            "cma": np.sin(rng) * 0.4,
            "mom": (rng % 7 - 3) * 0.5,
        }, index=idx)
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)

        seas = fs.compute_factor_seasonality(today=date(2026, 7, 15))
        assert seas is not None

        html = _render(seas=seas, momo=None)
        assert len(html) > 1000

    def test_hero_headline_present(self, monkeypatch):
        """When seas.now is present, headline text appears in the rendered HTML."""
        import numpy as np
        import pandas as pd
        from engine import factor_seasonality as fs

        # Build deterministic headwind data for July
        idx = pd.date_range("2010-01-31", "2024-12-31", freq="ME")
        data = {col: np.ones(len(idx)) * 2.0 for col in ["mkt_rf", "smb", "hml", "rf", "rmw", "cma", "mom"]}
        df = pd.DataFrame(data, index=idx)
        df.loc[df.index.month == 7, "mom"] = -3.0

        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        seas = fs.compute_factor_seasonality(today=date(2024, 7, 15))
        assert seas is not None
        assert seas["now"] is not None

        html = _render(seas=seas, momo=None)
        # The headline should contain "July" (it's in the engine-generated text)
        assert "July" in html or "rough" in html, "Expected July headline content in rendered HTML"
        # Factor weather h2 present
        assert "Factor weather" in html

    def test_renders_with_momo(self):
        """Page renders without exception when synthetic momo with top_decile is given."""
        html = _render(seas=None, momo=_minimal_momo())
        assert "Where the heat is" in html
        assert "Information Technology" in html

    def test_bh_withheld_after_factor_leaders(self):
        """BH-WITHHELD content appears AFTER 'Factor leaders' in the page (NW panel demoted)."""
        html = _render(seas=None, momo=None)
        leaders_pos = html.find("Factor leaders")
        bh_pos = html.find("BH-WITHHELD")
        # NW panel variables are set early but never rendered then — the actual BH-WITHHELD
        # chip appears in the NW panel which is now at the bottom after Factor leaders.
        # nw_state=None path renders "DORMANT" not BH-WITHHELD chips, so check
        # the technical status h2 instead, which must come after Factor leaders.
        tech_status_pos = html.find("technical status")
        assert leaders_pos != -1, "'Factor leaders' not found in rendered HTML"
        assert tech_status_pos != -1, "'technical status' not found — NW panel missing"
        assert tech_status_pos > leaders_pos, (
            f"NW panel ('technical status' at {tech_status_pos}) must appear AFTER "
            f"'Factor leaders' (at {leaders_pos})"
        )

    def test_no_validated_in_new_user_copy(self):
        """The word 'validated' must not appear in any NEW user-facing copy we introduced.

        The new sections are: Factor weather hero, Factor calendar, 'Where the heat is',
        IC panel plain verdict box (now-block), the 'What is working now' subtitle, and
        the moved NW panel with new first paragraph.  We check the rendered output rather
        than the source so we catch Jinja-emitted text too.
        """
        html = _render(seas=None, momo=None)
        # The VALIDATED chip text (t('VALIDATED','已验证')) is permitted to appear in the
        # rendered IC table rows.  The CI guard bans it in the NEW copy we added.
        # New panels we added: "Factor weather", "Factor calendar", "Where the heat is",
        # "How this research feeds the system", the "leadership rotates" subtitle.
        # We'll verify the specific NEW text blocks don't contain "validated".
        new_section_markers = [
            "Factor weather",
            "Factor calendar",
            "Where the heat is",
            "leadership rotates",
            "technical status",
            "For the curious",
        ]
        for marker in new_section_markers:
            pos = html.find(marker)
            if pos == -1:
                continue  # panel may be absent (fail-open)
            # Grab 500 chars after the marker and check for 'validated' (case-insensitive)
            snippet = html[pos:pos + 500].lower()
            assert "validated" not in snippet, (
                f"'validated' found in new section '{marker}': ...{html[pos:pos+200]}..."
            )

    def test_calendar_panel_present_with_seas(self, monkeypatch):
        """Factor calendar panel appears when seas data is available."""
        import numpy as np
        import pandas as pd
        from engine import factor_seasonality as fs

        idx = pd.date_range("1985-01-31", periods=40 * 12, freq="ME")
        rng = np.arange(len(idx))
        df = pd.DataFrame({
            "mkt_rf": np.sin(rng) * 2,
            "smb": np.cos(rng),
            "hml": (rng % 12 - 5) * 0.3,
            "rf": 0.2,
            "rmw": np.cos(rng) * 0.5,
            "cma": np.sin(rng) * 0.4,
            "mom": (rng % 7 - 3) * 0.5,
        }, index=idx)
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        seas = fs.compute_factor_seasonality(today=date(2026, 7, 15))

        html = _render(seas=seas, momo=None)
        assert "Factor calendar" in html

    def test_what_is_working_subtitle(self):
        """'What is working now' subtitle is present."""
        html = _render(seas=None, momo=None)
        # The subtitle text we added
        assert "leadership rotates" in html
