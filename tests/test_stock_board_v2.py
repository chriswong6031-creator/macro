"""Tests for the Buy Board 2.0 SHADOW build (W6-US, US-3).

Covers the two load-bearing contracts:
  * engine.group_context — tolerant readers degrade to neutral (never crash),
    the fuse is a weighted mean of PRESENT sources (absent = not diluted), and
    the leadership score orders leading > washed-out.
  * scripts.build_stock_board_v2 — the WHAT×WHEN dual gate, the honesty guard
    (a blocked buy never enters entry_open), variable width (no fill pressure),
    the provisional flag on setting_up, group-leadership floor MODULATION (never
    a hard gate), and the sparse event bonus entering as OR/max (not an average).
"""
import json
from pathlib import Path

import pytest

import engine.group_context as gcmod
from engine.group_context import GroupContext, READER_CONTRACT
from scripts import build_stock_board_v2 as v2


# --------------------------------------------------------------------------- #
#  group_context — tolerant readers                                            #
# --------------------------------------------------------------------------- #
def test_missing_artifacts_degrade_to_neutral(tmp_path, monkeypatch):
    """Every source missing → leadership 0, coverage 0, degraded list full, NO crash."""
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    (tmp_path / "site").mkdir()
    gc = GroupContext()
    pp = gc.source_passport()
    assert all(not v["found"] for v in pp.values())
    ctx = gc.for_name("ETN", "Industrials")
    assert ctx["leadership"] == 0.0
    assert ctx["state"] == "neutral"
    assert ctx["passport"]["n"] == 0
    assert set(ctx["passport"]["degraded"]) == set(READER_CONTRACT["sources"])


def test_malformed_json_degrades_not_crashes(tmp_path, monkeypatch):
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    sd = tmp_path / "site" / "sectordata"
    sd.mkdir(parents=True)
    (sd / "sector_central.json").write_text("{ not valid json")
    gc = GroupContext()
    assert gc.source_passport()["sector_central"]["degraded"] is True
    assert gc.for_name("ETN", "Industrials")["leadership"] == 0.0


def test_stale_artifact_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    sd = tmp_path / "site" / "sectordata"
    sd.mkdir(parents=True)
    (sd / "sector_central.json").write_text(json.dumps(
        {"as_of": "2000-01-01", "sectors": [
            {"name": "Industrials", "conviction": {"score": 90},
             "forward": {"trend_pass": True}}]}))
    gc = GroupContext()
    assert gc.source_passport()["sector_central"]["stale"] is True
    # a stale source is treated as degraded → contributes nothing
    assert gc.for_name("ETN", "Industrials")["passport"]["n"] == 0


def test_sector_alias_information_technology(tmp_path, monkeypatch):
    """standouts 'Information Technology' must join sector_central 'Technology'."""
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    sd = tmp_path / "site" / "sectordata"
    sd.mkdir(parents=True)
    import datetime
    today = datetime.date.today().isoformat()
    (sd / "sector_central.json").write_text(json.dumps(
        {"as_of": today, "sectors": [
            {"name": "Technology", "conviction": {"score": 80, "label_en": "Accumulate"},
             "forward": {"trend_pass": True}}]}))
    gc = GroupContext()
    ctx = gc.for_name("NVDA", "Information Technology")
    assert ctx["passport"]["n"] == 1          # the alias resolved
    assert ctx["leadership"] > 0              # score 80 → positive


def test_leading_outranks_washed_out(tmp_path, monkeypatch):
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    sd = tmp_path / "site" / "sectordata"
    sd.mkdir(parents=True)
    import datetime
    today = datetime.date.today().isoformat()
    (sd / "sector_central.json").write_text(json.dumps(
        {"as_of": today, "sectors": [
            {"name": "Technology", "conviction": {"score": 95}, "forward": {"trend_pass": True}},
            {"name": "Utilities", "conviction": {"score": 10}, "forward": {"trend_pass": False}}]}))
    gc = GroupContext()
    lead_tech = gc.for_name("NVDA", "Technology")["leadership"]
    lead_util = gc.for_name("XEL", "Utilities")["leadership"]
    assert lead_tech > lead_util
    assert lead_tech > 0 > lead_util


def test_absent_source_not_diluted(tmp_path, monkeypatch):
    """A name covered ONLY by sector_central must not be pulled toward 0 by the
    four absent sources — the fuse is over PRESENT sources only."""
    monkeypatch.setattr(gcmod, "_ROOT", tmp_path)
    sd = tmp_path / "site" / "sectordata"
    sd.mkdir(parents=True)
    import datetime
    today = datetime.date.today().isoformat()
    (sd / "sector_central.json").write_text(json.dumps(
        {"as_of": today, "sectors": [
            {"name": "Technology", "conviction": {"score": 100}, "forward": {"trend_pass": True}}]}))
    gc = GroupContext()
    ctx = gc.for_name("NVDA", "Technology")
    # score 100 → contrib +1.0; with only one present source the fuse == +1.0,
    # NOT +1.0 * one_weight / all_weights.
    assert ctx["leadership"] == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
#  build_stock_board_v2 — dual gate + honesty                                  #
# --------------------------------------------------------------------------- #
def _rich_row(ticker="AAA", *, verdict="Constructive — building", z=0.5,
              tier_cascade="T2", eligible=True, above200=True, weekly_bull=True,
              last_quality="pending", off_high=-3.0, alpha=0.5, sector="Technology"):
    return {
        "ticker": ticker, "name": ticker, "sector": sector, "alpha": alpha,
        "off_high": off_high,
        "conviction": {"verdict": verdict, "composite_z": z,
                       "trust_tier": {"tier": "context"}, "drivers": []},
        "signal": {"eligible": eligible, "tier_cascade": tier_cascade,
                   "above200": above200, "weekly_bull": weekly_bull, "ticks": 1,
                   "last": {"quality": last_quality}},
    }


def test_when_gate_hard_admission_is_buyable():
    """A non-buyable tier (T4) never passes the WHEN gate → never entry_open."""
    r = _rich_row(tier_cascade="T4")
    assert v2._when_gate(r)["pass"] is False


def test_honesty_guard_blocked_buy_rejected():
    """A buyable tier whose §7 last marker is quality=='block' must be rejected
    (the ETN bearish-divergence bug). This is the central honesty guard."""
    r = _rich_row(tier_cascade="T2", last_quality="block")
    w = v2._when_gate(r)
    assert w["blocked"] is True
    assert w["pass"] is False


def test_what_gate_rejects_lagging():
    r = _rich_row(verdict="Lagging — relative weakness", z=0.5)
    assert v2._what_gate(r, leadership=0.0)["pass"] is False


def test_what_gate_floor_modulation_is_soft_not_a_hard_gate():
    """Group leadership MODULATES the z-floor (leading lowers it, washed-out
    raises it) but NEVER hard-gates: a strong-z name in a washed-out group can
    still pass if its z clears the raised floor."""
    # z just above the base floor but below the raised floor → washed-out blocks on Z,
    # but a leading group would pass it. Verify the floor MOVES, not a hard veto.
    r = _rich_row(z=0.10)
    lead = v2._what_gate(r, leadership=0.9)     # leading → floor 0.0-0.25 = -0.25
    washed = v2._what_gate(r, leadership=-0.9)  # washed-out → floor 0.0+0.25 = +0.25
    assert lead["floor"] < washed["floor"]
    assert lead["pass"] is True                 # 0.10 > -0.25
    assert washed["z_pass"] is False            # 0.10 < 0.25 (floor raised, not vetoed)
    # and a high-z name STILL passes even in a washed-out group (soft, not hard)
    r_hi = _rich_row(z=0.9)
    assert v2._what_gate(r_hi, leadership=-0.9)["pass"] is True


def test_setting_up_flags_provisional_and_detects_t4():
    r = _rich_row(tier_cascade="T4")
    r["signal"]["bars_to_cross"] = 1.5
    setup = v2._about_to_cross(r)
    assert setup["imminent"] is True
    # end-to-end: a T4 trajectory-passing name lands in setting_up, provisional
    row = v2._build_row(r, {"leadership": 0.3, "chips": [], "surfaced_by": [],
                            "passport": {"freshness": 0, "n": 1}},
                        "setting_up", v2._when_gate(r), v2._what_gate(r, 0.3), setup, 0.5)
    assert row["provisional"] is True
    assert row["lane"] == "setting_up"


def test_event_bonus_or_max_not_averaged():
    """An event-edge name gets a bonus chip; a non-event name gets None (absent,
    NOT a diluting zero in an average)."""
    ev = _rich_row()
    ev["conviction"]["trust_tier"] = {"tier": "event-edge", "en": "insider buying"}
    assert v2._event_bonus(ev) is not None
    plain = _rich_row()
    assert v2._event_bonus(plain) is None


def test_variable_width_empty_lane_is_honest(tmp_path):
    """No candidates pass → both lanes empty, no backfill, status ok."""
    site = tmp_path / "site"
    (site / "factordata").mkdir(parents=True)
    # a single Lagging, non-buyable name → drops from both lanes
    std = {"as_of": "2026-06-30",
           "buy": [_rich_row(verdict="Lagging — weak", tier_cascade=None, eligible=False)],
           "watch": [], "laggards": []}
    (site / "factordata" / "us_standouts.json").write_text(json.dumps(std))
    (site / "factordata" / "setups.json").write_text(json.dumps({"buy": []}))
    payload = v2.compute(site=site)
    assert payload["status"] == "ok"
    assert payload["counts"]["entry_open"] == 0
    assert payload["counts"]["setting_up"] == 0
    # no minimum-count backfill: universe==1 but lanes empty
    assert payload["counts"]["candidates"] == 1


def test_no_fused_0_100_score_only_two_glyphs():
    r = _rich_row()
    row = v2._build_row(r, {"leadership": 0.3, "chips": [], "surfaced_by": [],
                            "passport": {"freshness": 0, "n": 1}},
                        "entry_open", v2._when_gate(r), v2._what_gate(r, 0.3),
                        None, 0.7)
    assert "edge_glyph" in row and "entry_glyph" in row
    # the dead 0-100 must not be present
    assert "score" not in row and "potential_score" not in row and "band" not in row


def test_row_identity_fields_for_ledger():
    """v2 rows must carry the row-identity fields US-2's ledger grades on."""
    r = _rich_row()
    row = v2._build_row(r, {"leadership": 0.3, "chips": [], "surfaced_by": [],
                            "passport": {"freshness": 0, "n": 1}},
                        "entry_open", v2._when_gate(r), v2._what_gate(r, 0.3), None, 0.7)
    for f in ("ticker", "lane", "rank", "gates_passed"):
        assert f in row


# ---------------------------------------------------------------------------
# W4 reflexivity overlay integration: render() accepts overlay kwarg
# Template: card chips (data-tip-en/data-tip-zh) + board banner
# ---------------------------------------------------------------------------

class TestW4ReflexivityTemplateIntegration:
    """Verify that the template renders reflexivity chips and the board banner
    when rx is provided, and degrades gracefully when rx is None."""

    def _minimal_payload(self):
        """Minimal payload dict that render() can pass to the template."""
        return {
            "status": "ok", "as_of": "2026-07-05",
            "generated_utc": "2026-07-05T00:00:00Z",
            "shadow": True, "note": "test", "universe": 2,
            "lanes": {
                "entry_open": [{
                    "ticker": "NVDA", "name": "NVIDIA Corp",
                    "rank": 1, "sector": "Information Technology",
                    "lane": "entry_open", "provisional": False,
                    "leadership": 0.3, "group_state": "leading",
                    "composite_z": 0.8, "alpha": 0.5,
                    "edge_glyph": {"grade": "A", "tone": "pos", "verdict": "Leader", "pctile": 0.9},
                    "entry_glyph": {"tier": "T1", "tone": "pos", "freshness": "fresh"},
                    "chips": [],
                    "when": {"off_high": -3.5, "fresh_bars": 1},
                    "gates_passed": {"in_setups": True},
                }],
                "setting_up": [],
            },
            "counts": {"entry_open": 1, "setting_up": 0, "candidates": 2},
            "concentration": {
                "entry_open": {"n": 1, "n_sectors": 1, "top2_sector_share": 1.0,
                               "effective_bets": 1.0, "effective_bets_basis": "X",
                               "concentrated": False, "by_sector": {}},
                "setting_up": {"n": 0, "n_sectors": 0, "top2_sector_share": 0.0,
                               "effective_bets": 0.0, "effective_bets_basis": "X",
                               "concentrated": False, "by_sector": {}},
            },
            "knobs": {}, "knobs_basis": "prior",
            "reader_contract": {"version": "1.0", "sources": []},
            "rotation_coverage": {},
            "board_passport": {"basis": "dual-gate", "frame": "cross-sectional",
                               "as_of": None, "n": 2},
            "ledger": {},
        }

    def _render(self, payload, overlay=None):
        """Render the template in-memory and return the HTML string."""
        from jinja2 import Environment, FileSystemLoader
        from lib import config
        env = Environment(
            loader=FileSystemLoader(str(config.ROOT / "templates")),
            autoescape=True,
        )
        return env.get_template("us_stocks_v2.html.j2").render(
            d=payload, built="2026-07-05 00:00 UTC", rx=overlay)

    def test_render_without_overlay_no_crash(self):
        """render() with overlay=None must not crash — first-pass render."""
        payload = self._minimal_payload()
        html = self._render(payload, overlay=None)
        assert "Buy Board 2.0" in html
        # No reflexivity banner when overlay absent
        assert "W4 Reflexivity" not in html

    def test_render_with_overlay_shows_board_banner(self):
        """When rx is provided, the W4 board banner must appear in the HTML."""
        payload = self._minimal_payload()
        overlay = {
            "schema": "reflexivity_overlay.v1",
            "is_context_only": True,
            "board_concentration": {"n": 2, "n_eff": 1.5, "basis": "membership-jaccard"},
            "n_eff_by_lane": {"entry_open": 1.0, "setting_up": None},
            "by_ticker": {
                "NVDA": {
                    "verdict": "duplicate",
                    "max_similarity": 0.9,
                    "basis": "membership+high-tier-factor",
                    "nearest": [],
                    "why_en": "Same bet as AMD — semis (90%).",
                    "why_zh": "与 AMD 押注相同 — 半导体（90%）。",
                },
            },
            "factor_caveat": "OOS-unstable secondaries excluded.",
            "verdicts": {},
        }
        html = self._render(payload, overlay=overlay)
        # Board banner must be present
        assert "W4 Reflexivity" in html or "reflexivity" in html.lower()
        # Per-ticker chip for NVDA (duplicate verdict)
        assert "same bet" in html or "duplicate" in html.lower() or "⚠" in html

    def test_render_with_overlay_uses_data_tip_not_title(self):
        """Reflexivity chips must use data-tip-en/data-tip-zh, not title= (CI rule)."""
        payload = self._minimal_payload()
        overlay = {
            "schema": "reflexivity_overlay.v1",
            "board_concentration": {"n": 2, "n_eff": 1.5},
            "n_eff_by_lane": {"entry_open": 1.0, "setting_up": None},
            "by_ticker": {
                "NVDA": {
                    "verdict": "partial",
                    "why_en": "Partial overlap with AMD.",
                    "why_zh": "与 AMD 部分重叠。",
                    "nearest": [],
                },
            },
            "factor_caveat": "OOS-unstable.",
            "verdicts": {},
        }
        html = self._render(payload, overlay=overlay)
        # data-tip-en/zh must appear, title= must NOT appear for CJK tooltip content
        assert "data-tip-en=" in html
        assert "data-tip-zh=" in html
        # The why text itself should appear in a data-tip attribute, not in title=
        import re
        # Find title= attributes that contain Chinese characters
        cjk_in_title = re.search(r'title="[^"]*[一-鿿]', html)
        assert cjk_in_title is None, (
            f"CJK text found in title= attribute: {cjk_in_title.group() if cjk_in_title else ''}"
        )

    def test_render_overlay_new_verdict_no_chip(self):
        """'new' verdict tickers must NOT get a reflexivity chip (only duplicate/partial)."""
        payload = self._minimal_payload()
        overlay = {
            "schema": "reflexivity_overlay.v1",
            "board_concentration": {"n": 2, "n_eff": 2.0},
            "n_eff_by_lane": {"entry_open": 1.0, "setting_up": None},
            "by_ticker": {
                "NVDA": {
                    "verdict": "new",  # new → no chip
                    "why_en": "Distinct bet — nearest AMD at 15%.",
                    "why_zh": "独立押注 — 最近的候选名称 AMD，相似度 15%。",
                    "nearest": [],
                },
            },
            "factor_caveat": "",
            "verdicts": {},
        }
        html = self._render(payload, overlay=overlay)
        # 'new' verdict should not produce a chip
        assert "same bet" not in html
        assert "partial overlap" not in html
        assert "重复押注" not in html

    def test_render_accepts_overlay_kwarg(self):
        """render() must accept overlay kwarg without raising TypeError."""
        payload = self._minimal_payload()
        # render() is called from build_reflexivity_overlay._rerender_v2_preview
        # with overlay=<dict>; the old signature had no overlay param → TypeError
        import inspect
        from scripts.build_stock_board_v2 import render as bv2_render
        sig = inspect.signature(bv2_render)
        assert "overlay" in sig.parameters, (
            "render() must accept overlay kwarg (wired by build_reflexivity_overlay._rerender_v2_preview)"
        )
