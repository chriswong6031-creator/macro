"""tests/test_china_alpha_w2b.py — W2-B: builder wiring + template render tests.

Four test groups:
  1. Builder synthetic-row: narrative tag attach, ab_tier rules, RAN_LATE exclusion,
     order-invariance assert.
  2. Ledger schema: append_board + append_ripening carry the W2-B columns.
  3. Template render: narrative theme renders on RIPENING (W8-R1 rip-chip);
     ENTRY chips + A/B badges stay decluttered (#1400); dual-span (l-en + l-zh),
     ASCII-only attribute delimiters.
  4. ab_tier edge cases from engine.china_narrative_tags.

Nearest sibling: tests/test_china_stocks_w1c_render.py (template idiom).
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.china_narrative_tags import ab_tier  # noqa: E402

SRC = (ROOT / "templates" / "china.html.j2").read_text()

# ──────────────────────────────────────────────────────────────────────────────
# Group 1: builder synthetic-row logic
# ──────────────────────────────────────────────────────────────────────────────

class TestBuilderNarrativeTags:
    """Verify the builder attaches narrative + ab_tier without touching order."""

    # ---- ab_tier function (imported from engine) ----

    def test_ab_tier_a_hot_entry(self):
        tag = {"level": "HOT", "radar": None}
        assert ab_tier("ENTRY", tag) == "A"

    def test_ab_tier_a_hot_ripening(self):
        tag = {"level": "HOT", "radar": None}
        assert ab_tier("RIPENING", tag) == "A"

    def test_ab_tier_a_radar_validated_entry(self):
        tag = {
            "level": "WARMING",
            "radar": {"global_ai": {"validated_tag": "validated"}},
        }
        assert ab_tier("ENTRY", tag) == "A"

    def test_ab_tier_a_radar_partial_entry(self):
        tag = {
            "level": None,
            "radar": {"global_ai": {"validated_tag": "partial"}},
        }
        assert ab_tier("ENTRY", tag) == "A"

    def test_ab_tier_b_warming_no_radar(self):
        tag = {"level": "WARMING", "radar": None}
        assert ab_tier("ENTRY", tag) == "B"

    def test_ab_tier_b_no_tag_entry(self):
        assert ab_tier("ENTRY", None) == "B"

    def test_ab_tier_b_no_tag_ripening(self):
        assert ab_tier("RIPENING", None) == "B"

    def test_ab_tier_none_ran_late(self):
        """RAN_LATE rows must always get None tier — the spec law."""
        tag = {"level": "HOT", "radar": None}
        assert ab_tier("RAN_LATE", tag) is None

    def test_ab_tier_none_ran_late_no_tag(self):
        assert ab_tier("RAN_LATE", None) is None

    def test_ab_tier_none_no_stage(self):
        assert ab_tier(None, None) is None

    def test_ab_tier_radar_2024_only_not_a(self):
        """2024+-only honesty tag does NOT qualify for A-tier (only validated/partial)."""
        tag = {
            "level": None,
            "radar": {"global_ai": {"validated_tag": "2024+-only"}},
        }
        assert ab_tier("ENTRY", tag) == "B"

    def test_ab_tier_radar_weak_not_a(self):
        tag = {
            "level": None,
            "radar": {"global_ai": {"validated_tag": "weak"}},
        }
        assert ab_tier("ENTRY", tag) == "B"

    # ---- builder row attachment contract ----

    def _make_buy_row(self, ticker: str, stage: str = "ENTRY") -> dict:
        """Minimal synthetic buy row as the builder produces."""
        return {
            "ticker": ticker,
            "name": f"{ticker} Name",
            "sector": "Technology",
            "stage": stage,
            "signal": None,
            "extension": None,
        }

    def _make_ripening_row(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "name": f"{ticker} Name",
            "sector": "Healthcare",
            "reasons": ["2W washout"],
            "imminence": 4.9,
        }

    def _make_narr_tag(self, level: str = "HOT") -> dict:
        return {
            "theme": "Synthetic Biology",
            "theme_zh": "合成生物",
            "basket_id": "ths_synbio",
            "level": level,
            "rel20": 17.8,
            "breadth": 0.875,
            "source": "THS",
            "radar": None,
        }

    def test_narrative_attached_to_entry_row(self):
        """When a tag exists, narrative dict is attached to buy rows."""
        r = self._make_buy_row("300725.SZ", stage="ENTRY")
        narr_tags = {"300725.SZ": self._make_narr_tag("HOT")}

        tag = narr_tags.get(r["ticker"])
        if tag:
            r["narrative"] = {
                "theme": tag.get("theme"),
                "theme_zh": tag.get("theme_zh"),
                "basket_id": tag.get("basket_id"),
                "level": tag.get("level"),
                "rel20": tag.get("rel20"),
                "breadth": tag.get("breadth"),
                "source": tag.get("source"),
                "radar": tag.get("radar"),
            }
        r["ab_tier"] = ab_tier(r["stage"], tag)

        assert r["narrative"]["theme"] == "Synthetic Biology"
        assert r["narrative"]["level"] == "HOT"
        assert r["ab_tier"] == "A"

    def test_ab_tier_none_on_ran_late_row(self):
        """RAN_LATE rows must have ab_tier=None regardless of tag."""
        r = self._make_buy_row("603129.SS", stage="RAN_LATE")
        narr_tags = {"603129.SS": self._make_narr_tag("HOT")}
        tag = narr_tags.get(r["ticker"])
        r["ab_tier"] = ab_tier(r["stage"], tag)
        assert r["ab_tier"] is None

    def test_no_narrative_key_when_no_tag(self):
        """Rows with no matching tag should not have a 'narrative' key added
        (the builder only adds it when tag is truthy)."""
        r = self._make_buy_row("000001.SZ", stage="ENTRY")
        narr_tags: dict = {}
        tag = narr_tags.get(r["ticker"])
        if tag:
            r["narrative"] = {}
        r["ab_tier"] = ab_tier(r["stage"], tag)

        assert "narrative" not in r
        # B-tier: no tag but stage is ENTRY
        assert r["ab_tier"] == "B"

    def test_narrative_attached_to_ripening_row(self):
        """Ripening rows get narrative + ab_tier just like buy rows."""
        r = self._make_ripening_row("688306.SS")
        narr_tags = {"688306.SS": self._make_narr_tag("HOT")}
        tag = narr_tags.get(r["ticker"])
        if tag:
            r["narrative"] = {k: tag.get(k)
                              for k in ("theme", "theme_zh", "basket_id",
                                        "level", "rel20", "breadth", "source", "radar")}
        r["ab_tier"] = ab_tier("RIPENING", tag)

        assert r["narrative"]["level"] == "HOT"
        assert r["ab_tier"] == "A"

    def test_order_invariance(self):
        """Attaching narrative must NOT change row order.

        This mirrors the builder's own invariant assert at:
          scripts/build_china_library.py — W2-B order-invariance assertion
        """
        tickers = [f"00{i:04d}.SZ" for i in range(10)]
        rows = [self._make_buy_row(t) for t in tickers]

        # Record pre-attach order
        pre_order = [r["ticker"] for r in rows]

        # Attach narrative (only odd tickers have tags)
        narr_tags = {t: self._make_narr_tag("HOT") for t in tickers[1::2]}
        for r in rows:
            t = r["ticker"]
            tag = narr_tags.get(t)
            if tag:
                r["narrative"] = {k: tag.get(k)
                                  for k in ("theme", "theme_zh", "basket_id",
                                            "level", "rel20", "breadth", "source", "radar")}
            r["ab_tier"] = ab_tier(r.get("stage"), tag)

        post_order = [r["ticker"] for r in rows]
        assert pre_order == post_order, "Narrative tagging must never change row order"

    def test_warming_tag_gives_b_tier_entry(self):
        """WARMING + no radar => B-tier (not A)."""
        tag = self._make_narr_tag("WARMING")
        assert ab_tier("ENTRY", tag) == "B"

    def test_hot_tag_gives_a_tier_ripening(self):
        """HOT tag on RIPENING row => A-tier."""
        tag = self._make_narr_tag("HOT")
        assert ab_tier("RIPENING", tag) == "A"


# ──────────────────────────────────────────────────────────────────────────────
# Group 2: ledger schema — append_board + append_ripening carry W2-B columns
# ──────────────────────────────────────────────────────────────────────────────

class TestLedgerSchema:
    """Verify append_board and append_ripening write the five W2-B columns."""

    def _make_board_row(self, ticker: str, stage: str = "ENTRY",
                        narr_theme: str | None = "Synthetic Biology",
                        narr_level: str | None = "HOT",
                        narr_rel20: float | None = 17.8,
                        narr_breadth: float | None = 0.875,
                        ab_tier_val: str | None = "A") -> dict:
        return {
            "ticker": ticker,
            "stage": stage,
            "signal": None,
            "extension": None,
            "coiled": None,
            "entry_signal": None,
            "washout_2w": False,
            "hold": None,
            "sector_turn": None,
            "price": 46.5,
            "setup": "T1",
            "narrative": {
                "theme": narr_theme,
                "level": narr_level,
                "rel20": narr_rel20,
                "breadth": narr_breadth,
            } if narr_theme else None,
            "ab_tier": ab_tier_val,
        }

    def _make_ripening_row(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "reasons": ["2W washout"],
            "imminence": 4.9,
            "w2_stoch": 22,
            "narrative": {
                "theme": "Solid-State Battery",
                "level": "HOT",
                "rel20": 31.8,
                "breadth": 0.818,
            },
            "ab_tier": "A",
        }

    def test_append_board_writes_narr_columns(self, tmp_path):
        """append_board must write narr_theme/narr_level/narr_rel20/narr_breadth/ab_tier."""
        import os
        from unittest.mock import patch

        from engine import china_standout_track

        rows = [self._make_board_row("300725.SZ", stage="ENTRY")]

        # Redirect the store path to tmp_path
        store_path = tmp_path / "china_standout_track" / "board.parquet"
        store_path.parent.mkdir(parents=True, exist_ok=True)

        with patch.object(china_standout_track, "_store_path", return_value=store_path), \
             patch.object(china_standout_track, "session_status",
                          return_value={"partial_session": False, "collected_utc": None,
                                        "collected_hour_utc": None, "reason": "ok"}):
            n = china_standout_track.append_board(rows, asof="2026-07-03", lane="asia")

        assert n > 0
        df = pd.read_parquet(store_path)
        assert "narr_theme" in df.columns
        assert "narr_level" in df.columns
        assert "narr_rel20" in df.columns
        assert "narr_breadth" in df.columns
        assert "ab_tier" in df.columns

        row = df[df["ticker"] == "300725.SZ"].iloc[0]
        assert row["narr_theme"] == "Synthetic Biology"
        assert row["narr_level"] == "HOT"
        assert abs(row["narr_rel20"] - 17.8) < 0.01
        assert row["ab_tier"] == "A"

    def test_append_board_ran_late_ab_tier_none(self, tmp_path):
        """RAN_LATE rows must have ab_tier=None in the ledger."""
        from unittest.mock import patch
        from engine import china_standout_track

        rows = [self._make_board_row("603129.SS", stage="RAN_LATE",
                                     narr_theme="Synthetic Biology", narr_level="HOT",
                                     ab_tier_val=None)]

        store_path = tmp_path / "cst2" / "board.parquet"
        store_path.parent.mkdir(parents=True, exist_ok=True)

        with patch.object(china_standout_track, "_store_path", return_value=store_path), \
             patch.object(china_standout_track, "session_status",
                          return_value={"partial_session": False, "collected_utc": None,
                                        "collected_hour_utc": None, "reason": "ok"}):
            china_standout_track.append_board(rows, asof="2026-07-03", lane="asia")

        df = pd.read_parquet(store_path)
        row = df[df["ticker"] == "603129.SS"].iloc[0]
        assert row["ab_tier"] is None or (isinstance(row["ab_tier"], float)
                                           and pd.isna(row["ab_tier"]))

    def test_append_ripening_writes_narr_columns(self, tmp_path):
        """append_ripening must write narr_theme/narr_level/narr_rel20/narr_breadth/ab_tier."""
        from unittest.mock import patch
        from engine import china_standout_track

        rows = [self._make_ripening_row("688306.SS")]

        rip_path = tmp_path / "cst3" / "ripening.parquet"
        rip_path.parent.mkdir(parents=True, exist_ok=True)

        with patch.object(china_standout_track, "_ripening_path", return_value=rip_path), \
             patch.object(china_standout_track, "session_status",
                          return_value={"partial_session": False}):
            n = china_standout_track.append_ripening(rows, asof="2026-07-03", lane="asia")

        assert n > 0
        df = pd.read_parquet(rip_path)
        assert "narr_theme" in df.columns
        assert "narr_level" in df.columns
        assert "narr_rel20" in df.columns
        assert "narr_breadth" in df.columns
        assert "ab_tier" in df.columns

        row = df[df["ticker"] == "688306.SS"].iloc[0]
        assert row["narr_theme"] == "Solid-State Battery"
        assert row["ab_tier"] == "A"

    def test_append_board_schema_union_old_rows(self, tmp_path):
        """Old parquet rows without W2-B columns must concat successfully (schema-union)."""
        from unittest.mock import patch
        from engine import china_standout_track

        # Write a 'legacy' parquet without the W2-B cols
        legacy_row = {"date": "2026-07-01", "ticker": "999999.SZ",
                      "board_rank": 1, "stage": "ENTRY"}
        store_path = tmp_path / "cst4" / "board.parquet"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([legacy_row]).to_parquet(store_path, index=False)

        rows = [self._make_board_row("300725.SZ")]

        with patch.object(china_standout_track, "_store_path", return_value=store_path), \
             patch.object(china_standout_track, "session_status",
                          return_value={"partial_session": False, "collected_utc": None,
                                        "collected_hour_utc": None, "reason": "ok"}):
            n = china_standout_track.append_board(rows, asof="2026-07-03", lane="asia")

        assert n == 2  # legacy + new
        df = pd.read_parquet(store_path)
        # Both rows present; old row's W2-B cols are NaN
        assert len(df) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Group 3: template render tests
# ──────────────────────────────────────────────────────────────────────────────

def _render_w1c_w2b(setups: dict) -> str:
    """Extract and render the W1-C+W2-B block with synthetic context.

    Mirrors _render_w1c() in test_china_stocks_w1c_render.py.
    """
    from jinja2 import DictLoader, Environment

    start = SRC.index("{# ── W1-C: ENTRY SHELF")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    snippet = SRC[start:end]

    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro td(x) -%}{{ x }}{%- endmacro -%}\n'
        '{%- macro nm(name) -%}'
        '{% set p = (name or "").split(" / ") %}'
        '<span class="l-en">{{ p[0] }}</span>'
        '<span class="l-zh">{{ p[1] if p|length > 1 else p[0] }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro help(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh }}</span>'
        "{%- endmacro -%}\n"
    )
    snippet = snippet.replace(
        '{% with sig = n.signal %}{% include "_sig_badge.html.j2" %}{% endwith %}', ""
    )
    full = macros + snippet

    SECZH = {"Technology": "科技", "Healthcare": "医疗保健"}
    env = Environment(loader=DictLoader({"blk": full}), autoescape=False)
    env.globals["SECZH"] = SECZH
    return env.get_template("blk").render(setups=setups)


def _conviction(score=72, band="high", verdict="Fresh turn from washout", verdict_zh="洗盘后新转向"):
    return {
        "score": score, "band": band,
        "verdict": verdict, "verdict_zh": verdict_zh,
        "alignment": None,
        "axes": {
            ax: {"pct": 75}
            for ax in ("selection", "entry", "tailwind", "quality")
        },
        "vol_squeeze": None, "risk": None, "cautions": None,
        "notes": None, "trust_tier": None,
    }


def _entry_signal(status="buy_now"):
    return {
        "status": status, "act_level": 3,
        "headline": "Ready", "headline_zh": "就绪",
        "action": "Buy now", "buy_zone": None,
        "cycle_pos": None, "timing": None,
    }


def _make_entry_row(ticker="300725.SZ",
                    narr_theme="Synthetic Biology",
                    narr_level="HOT",
                    ab_tier_val="A"):
    row = {
        "ticker": ticker,
        "name": "Entry Name / 入场名称",
        "sector": "Healthcare",
        "stage": "ENTRY",
        "stage_sublabel": None,
        "stage_detail": {},
        "why_ranked": "T1+washout_2w",
        "dir": "up",
        "price": 46.5,
        "washout_2w": True,
        "coiled": None,
        "hold": None,
        "sector_turn": None,
        "extension": None,
        "quality": None,
        "off_high": -12.3,
        "spark_svg": None,
        "conviction": _conviction(),
        "entry_signal": _entry_signal("buy_now"),
        "signal": None,
        "align_tier": None,
        "alpha": 0.5,
        "alpha_entry": "pullback",
        "sector_rank": 3,
        "sector_n": 12,
        "risk_sizing": None,
        "confluence": False,
        "label": "buy_now",
        "state": "buy_now",
        "ab_tier": ab_tier_val,
    }
    if narr_theme:
        row["narrative"] = {
            "theme": narr_theme,
            "theme_zh": "合成生物",
            "basket_id": "ths_synbio",
            "level": narr_level,
            "rel20": 17.8,
            "breadth": 0.875,
            "source": "THS",
            "radar": None,
        }
    else:
        row["narrative"] = None
    return row


def _make_ran_row(ticker="603129.SS"):
    return {
        "ticker": ticker,
        "name": "Ran Name / 已过名称",
        "sector": "Technology",
        "stage": "RAN_LATE",
        "stage_sublabel": "signal fired 2026-06-24 (7 sessions ago), +8.9%",
        "stage_detail": {},
        "why_ranked": None,
        "dir": "caution",
        "price": 55.0,
        "washout_2w": False,
        "coiled": None,
        "hold": None,
        "sector_turn": None,
        "extension": None,
        "quality": None,
        "off_high": -3.2,
        "spark_svg": None,
        "conviction": _conviction(score=62, band="constructive"),
        "entry_signal": _entry_signal("hold"),
        "signal": None,
        "align_tier": None,
        "alpha": 1.2,
        "alpha_entry": "extended",
        "sector_rank": 1,
        "sector_n": 20,
        "risk_sizing": None,
        "confluence": False,
        "label": "hold",
        "state": "hold",
        # RAN_LATE rows: no ab_tier, narrative may exist but tier must not render
        "ab_tier": None,
        "narrative": {
            "theme": "Synthetic Biology",
            "theme_zh": "合成生物",
            "level": "HOT",
            "rel20": 17.8,
            "breadth": 0.875,
            "source": "THS",
            "radar": None,
        },
    }


def _make_ripening_row(ticker="688306.SS",
                       narr_theme="Solid-State Battery",
                       narr_level="HOT",
                       ab_tier_val="A"):
    # W8-R1 (#2102): ripening rows carry a zone (READY / BASING); the rip-shelf
    # partitions on it via selectattr, so the fixture must set one for cards to render.
    row = {
        "ticker": ticker,
        "name": "Ripening Name / 待熟名称",
        "sector": "Technology",
        "zone": "READY",
        "reasons": "2W washout,approaching MACD cross",
        "imminence": 4.9,
        "w2_stoch": 22,
        "w2_stoch_arrow": 1,
        "w2_macd_approaching": True,
        "w2_macd_cross_up": False,
        "w1_cross_date": None,
        "w1_cross_bars_since": None,
        "w1_d_at_cross": None,
        "macd_hist_d": -0.02,
        "macd_hist_slope": 0.01,
        "days_in_washout": 12,
        "ret_5d": 0.021,
        "price": 18.4,
        "spot_pct_in_range": 35.0,
        "ab_tier": ab_tier_val,
    }
    if narr_theme:
        row["narrative"] = {
            "theme": narr_theme,
            "theme_zh": "固态电池",
            "basket_id": "ths_solid_state",
            "level": narr_level,
            "rel20": 31.8,
            "breadth": 0.818,
            "source": "THS",
            "radar": None,
        }
    else:
        row["narrative"] = None
    return row


def _full_setups(entry=None, ran=None, ripening=None, ran3=None):
    entry = entry if entry is not None else [_make_entry_row()]
    ran = ran if ran is not None else [_make_ran_row()]
    ripening = ripening if ripening is not None else [_make_ripening_row()]
    ran3 = ran3 if ran3 is not None else []
    return {
        "as_of": "2026-07-03",
        "buy": entry + ran,
        "laggards": [],
        "qvix_regime": None,
        "data_outage": None,
        "board_track": None,
        "coverage": None,
        "ripening": ripening,
        "ran": ran3,
    }


class TestTemplateRender:

    def test_template_parses_without_errors(self):
        """Full template must parse — the most important gate."""
        from jinja2 import Environment
        env = Environment(autoescape=False)
        env.parse(SRC)

    def test_no_non_ascii_attribute_delimiters(self):
        """Zero non-ASCII quote characters in attributes — mirrors the sibling test.

        Detects: U+201C/201D curly-double, U+2018/2019 curly-single, U+00AB/00BB guillemets.
        These are the same codepoints checked by test_china_stocks_w1c_render.py.
        """
        # Build the bad-char set from explicit codepoints (avoids any encoding confusion).
        bad_chars = "".join(chr(c) for c in (0x201C, 0x201D, 0x2018, 0x2019, 0x00AB, 0x00BB))
        pattern = (
            r'(?:class|style|title|href|id|data-[a-z\-]+|aria-[a-z\-]+)=[' +
            bad_chars + ']'
        )
        bad = re.findall(pattern, SRC)
        assert not bad, f"Non-ASCII attribute delimiters: {bad}"

    def test_narrative_chip_decluttered_from_entry(self):
        """ENTRY cards must NOT render the narrative-heat chip (🔥/nb-narr).

        The chip was added by W2-B (#1118) and deliberately removed by the
        standout-board declutter (#1400): narrative heat left the cards; the
        lens survives in the W2-B ledger and the W8-E JSON data layer. This
        test pins the declutter so the chip does not silently come back.
        """
        html = _render_w1c_w2b(_full_setups())
        # Card renders (not vacuous) …
        assert "300725.SZ" in html
        # … but the narrative chip does not, even though narrative data is present.
        assert "🔥" not in html
        assert "nb-narr" not in html
        assert "Synthetic Biology" not in html

    def test_warming_chip_decluttered_from_entry(self):
        """WARMING-level narrative (≈ glyph) must also stay off ENTRY cards.

        Same declutter adjudication as HOT (#1400) — level does not matter.
        """
        row = _make_entry_row(narr_level="WARMING", ab_tier_val="B")
        html = _render_w1c_w2b(_full_setups(entry=[row]))
        assert "300725.SZ" in html
        assert "≈" not in html
        assert "Synthetic Biology" not in html

    def test_a_badge_decluttered_from_entry_card(self):
        """A-tier badge must NOT render on ENTRY cards.

        nb-atier was added by W2-B (#1118) and removed by the declutter (#1400)
        ("Removed A/B-tier, narrative heat, …"). ab_tier stays in the row data
        (ledger + data layer) but must not surface on the card.
        """
        html = _render_w1c_w2b(_full_setups())
        assert "300725.SZ" in html
        assert "nb-atier" not in html

    def test_b_badge_decluttered_from_entry_card(self):
        """B-tier badge (tier-b modifier) must NOT render on ENTRY cards (#1400)."""
        row = _make_entry_row(narr_level="WARMING", ab_tier_val="B")
        html = _render_w1c_w2b(_full_setups(entry=[row]))
        assert "300725.SZ" in html
        assert "tier-b" not in html

    def test_a_badge_absent_on_ran_late(self):
        """No A-tier badge on RAN_LATE cards — the spec law.

        RAN_LATE rows have ab_tier=None so neither 'A' nor 'B' branch fires.
        We pass empty ripening to isolate the RAN/LATE buy-shelf.
        """
        ran_row = _make_ran_row()
        # Empty ripening so the only shelf is RAN_LATE
        html = _render_w1c_w2b(_full_setups(entry=[], ran=[ran_row], ripening=[]))
        assert "nb-atier" not in html

    def test_narrative_chip_on_ripening_card(self):
        """Narrative theme must still appear on RIPENING cards, bilingual.

        W8-R1 (#2102) replaced the compact ripening shelf with the three-zone
        rip-shelf; the theme now renders as a plain context chip (rip-chip)
        with l-en/l-zh spans — the 🔥 heat glyph was decluttered with the old
        chip markup (#1400). Pins the current surface.
        """
        html = _render_w1c_w2b(_full_setups(entry=[], ran=[]))
        assert "rip-chip" in html
        assert "Solid-State Battery" in html
        assert "固态电池" in html

    def test_a_badge_decluttered_from_ripening_card(self):
        """A-tier badge must NOT render on RIPENING cards.

        Removed with the standout declutter (#1400); the W8-R1 rip-shelf
        (#2102) never reintroduced tier badges. ab_tier stays in the row data.
        """
        html = _render_w1c_w2b(_full_setups(entry=[], ran=[]))
        # Ripening card renders (not vacuous) …
        assert "688306.SS" in html
        assert "nb-atier" not in html

    def test_no_narrative_chip_when_no_tag(self):
        """Cards with no narrative tag must not render the chip."""
        row = _make_entry_row(narr_theme=None, ab_tier_val="B")
        rip = _make_ripening_row(narr_theme=None, ab_tier_val="B")
        html = _render_w1c_w2b(_full_setups(entry=[row], ripening=[rip]))
        # nb-narr class should not be present when no tag
        assert "nb-narr" not in html

    def test_narrative_chip_has_dual_span(self):
        """Narrative chip text must use l-en + l-zh dual spans."""
        html = _render_w1c_w2b(_full_setups())
        # Both spans should be present inside the narr chip
        assert 'class="l-en"' in html
        assert 'class="l-zh"' in html

    def test_radar_tag_decluttered_from_chip(self):
        """The radar validated-tag no longer renders on the board.

        It rode the narrative chip's tooltip/label (W2-B #1118) and left with
        the chip in the declutter (#1400). The tag stays in the radar data
        (ledger + data layer); "validated" is CI-enforced in user-facing text
        (scripts/check_validated_claims.py), so its absence here is the honest
        state — pin it so a chip revival cannot re-emit the word unreviewed.
        """
        row = _make_entry_row(ab_tier_val="A")
        row["narrative"]["radar"] = {
            "basket_id": "humanoid_robots",
            "narr_rank": 1,
            "global_ai": {
                "validated_tag": "validated",
                "mom_4w_pct": 3.27,
                "direction": "up",
                "as_of": "2026-07-03",
            },
        }
        html = _render_w1c_w2b(_full_setups(entry=[row]))
        assert "300725.SZ" in html
        assert "validated" not in html

    def test_w2b_block_is_balanced(self):
        """The W1-C+W2-B block must have balanced if/for tags."""
        start = SRC.index("{# ── W1-C: ENTRY SHELF")
        end = SRC.index("{# ── BOARD TRACK RECORD")
        snippet = SRC[start:end]
        ifs_open = len(re.findall(r"\{%-?\s*if\s", snippet))
        fors_open = len(re.findall(r"\{%-?\s*for\s", snippet))
        ifs_close = len(re.findall(r"\{%-?\s*endif\b", snippet))
        fors_close = len(re.findall(r"\{%-?\s*endfor\b", snippet))
        assert ifs_open == ifs_close, (
            f"Unbalanced if/endif in W2-B block: {ifs_open} open vs {ifs_close} close")
        assert fors_open == fors_close, (
            f"Unbalanced for/endfor in W2-B block: {fors_open} open vs {fors_close} close")

    def test_board_footer_keeps_honesty_caveat(self):
        """The board must keep its honesty caveat: buy-readiness, grades accruing.

        The original narrative-confluence caveat left with the chips (#1400)
        and the reader-first help rewrite (#2203). The surviving honesty line
        is the shelf footer note — Score = buy-readiness; forward grades still
        accruing — bilingual. (The (?)-popup caveats are separately enforced
        by test_china_stocks_copy_w09.py.)
        """
        html = _render_w1c_w2b(_full_setups())
        assert "buy-readiness" in html
        assert "still accruing" in html
        assert "仍在累积" in html

    def test_entry_chip_title_not_buy_family(self):
        """Narrative chip tooltip must not contain BUY-family words."""
        html = _render_w1c_w2b(_full_setups())
        # Find the narr chip: check its title attribute for BUY-family words
        narr_chips = re.findall(r'class="nb-narr[^"]*"[^>]*title="([^"]*)"', html)
        buy_words = re.compile(r'\b(BUY|buy|Buy|购买|买入)\b')
        for title in narr_chips:
            assert not buy_words.search(title), (
                f"BUY-family word in narrative chip title: {title!r}")
