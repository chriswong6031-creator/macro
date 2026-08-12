"""Calibration Lab tile for the ETF board's forward windows (ETF masterplan §3 W3).

Two contracts, both of which have been broken elsewhere on this site before:

  * ABSENT-SAFE — `scripts/build_measurement.py` runs on the RENDER path. It may only
    read the nightly's artifact, never advance it, and a missing artifact (every
    render between shipping this and the first nightly) must degrade to an honest
    "collecting" state rather than crash the Calibration Lab.
  * WINDOWS LANGUAGE — the panel reports projections re-drawn nightly. Accuracy /
    validated / falsified vocabulary is not permitted anywhere in the copy, front or
    below the fold, in either language.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.build_measurement as bm  # noqa: E402

TEMPLATE = REPO / "templates" / "measurement.html.j2"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _track(n_graded: int = 4) -> dict:
    return {
        "schema": "etf_board_track.v1",
        "generated_at": "2026-08-12T03:00:00Z",
        "as_of": "2026-08-12",
        "first_board": "2026-08-01",
        "benchmark": "SPY",
        "horizons": [5, 21, 63],
        "n_boards_logged": 3,
        "n_snapshot_rows": 60,
        "n_graded_total": n_graded,
        "collecting": n_graded == 0,
        "per_horizon": {
            "h5": {"horizon": 5, "n_rows": 60, "n_graded": n_graded, "n_pending": 56,
                   "n_boards": 1, "n_names": n_graded, "n_vs_bench": n_graded,
                   "n_ahead": 3, "median_excess_bench": 0.0123,
                   "mean_excess_bench": 0.011, "median_ret": 0.021,
                   "state": "open" if n_graded else "collecting"},
            "h21": {"horizon": 21, "n_rows": 60, "n_graded": 0, "n_pending": 60,
                    "n_boards": 0, "n_names": 0, "n_vs_bench": 0, "n_ahead": None,
                    "median_excess_bench": None, "mean_excess_bench": None,
                    "median_ret": None, "state": "collecting"},
            "h63": {"horizon": 63, "n_rows": 60, "n_graded": 0, "n_pending": 60,
                    "n_boards": 0, "n_names": 0, "n_vs_bench": 0, "n_ahead": None,
                    "median_excess_bench": None, "mean_excess_bench": None,
                    "median_ret": None, "state": "collecting"},
        },
        "rows": [{"as_of": "2026-08-01", "ticker": "NVDA", "rank": 1, "horizon": 5,
                  "n_accum": 5, "net_conviction_pp": 1.84, "ret": 0.031,
                  "excess_bench": 0.0123}],
        "source_ledger": "data/etf_board_ledger/",
    }


def _render(**over) -> str:
    """Render the template the way the builder does, with absent-state defaults."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(REPO / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    ctx = {
        "page_title": "Test", "engines": [], "gate_ledger": [],
        "accruing_experiments": [], "cone_recalibration": {}, "collinearity": {},
        "sync_gauge": {"available": False},
        "provenance": {"epochs": {}, "fingerprint_consistent": True},
        "build_date": date.today().isoformat(), "generated_at": "2026-08-12T00:00:00Z",
        "n_stamps_grand_total": 0, "truth_ledger": {"available": False},
        "accrual_clocks": [], "prediction_layer": {"available": False},
        "coverage_matrix": {"available": False, "rows": []},
        "grading_closure": {"available": False}, "trial_budgets": {"available": False},
        "rule_experiments": {"available": False},
        "qledger_reliability": {"available": False},
        "seasonality_record": {"available": False, "registered": 0, "graded": 0,
                               "next_close": None},
    }
    ctx.update(over)
    return env.get_template("measurement.html.j2").render(**ctx)


# --------------------------------------------------------------------------- #
# 1. builder — absent-safe
# --------------------------------------------------------------------------- #
class TestBuilderAbsentSafe:
    def test_missing_artifact_degrades_to_collecting(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", tmp_path / "nope.json")
        out = bm.build_etf_board_windows()
        assert out["available"] is False
        assert out["state"] == "collecting"
        assert len(out["horizons"]) == 3, (
            "the three horizon cards render even with no artifact — the panel is never "
            "hidden, it states that it is collecting"
        )
        assert all(h["median_excess_str"] == "—" for h in out["horizons"])

    def test_unreadable_artifact_does_not_raise(self, tmp_path, monkeypatch):
        p = tmp_path / "etf_board_track.json"
        p.write_text("{not json")
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        out = bm.build_etf_board_windows()
        assert out["available"] is False, "a corrupt artifact must not kill the render"

    def test_the_builder_never_writes_into_the_ledger(self, tmp_path, monkeypatch):
        """build_measurement runs on the render path — it is a READER, full stop."""
        ledger = tmp_path / "etf_board_ledger"
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", tmp_path / "nope.json")
        bm.build_etf_board_windows()
        assert not ledger.exists()


# --------------------------------------------------------------------------- #
# 2. builder — populated
# --------------------------------------------------------------------------- #
class TestBuilderPopulated:
    def test_counts_and_strings(self, tmp_path, monkeypatch):
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(_track()))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        out = bm.build_etf_board_windows()

        assert out["available"] is True and out["state"] == "open"
        assert out["n_boards_logged"] == 3
        h5 = next(h for h in out["horizons"] if h["horizon"] == 5)
        assert h5["median_excess_str"] == "+1.2%"
        assert h5["ahead_str"] == "3 of 4", "hit rate is stated as x of y, never a rate"
        h21 = next(h for h in out["horizons"] if h["horizon"] == 21)
        assert h21["state"] == "collecting" and h21["median_excess_str"] == "—", (
            "a horizon with no closed window prints a dash, never a 0.0%"
        )

    def test_zero_graded_artifact_is_available_but_collecting(self, tmp_path, monkeypatch):
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(_track(n_graded=0)))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        out = bm.build_etf_board_windows()
        assert out["available"] is True
        assert out["state"] == "collecting"
        assert out["n_boards_logged"] == 3, (
            "the boards ARE logged even though nothing has matured — the honest first-"
            "nights state is 'collecting', not 'unavailable'"
        )


# --------------------------------------------------------------------------- #
# 3. template
# --------------------------------------------------------------------------- #
class TestTemplate:
    def test_section_renders_with_no_payload_at_all(self):
        html = _render()
        assert 'id="efw-section"' in html, (
            "the panel must render even when the caller passes no payload — the "
            "self-defaulting {% set %} is what keeps it from vanishing"
        )
        assert "Collecting — no window has closed yet." in html

    def test_section_renders_the_numbers_when_windows_are_open(self, tmp_path, monkeypatch):
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(_track()))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        html = _render(etf_board_windows=bm.build_etf_board_windows())
        assert "+1.2%" in html
        assert "3 of 4 ahead of SPY" in html
        assert "NVDA" in html
        assert "Collecting — no window has closed yet." not in html

    def test_zh_half_is_present_for_every_en_span(self):
        """i18n parity: the section is bilingual, and zh never rides in a title attr."""
        src = TEMPLATE.read_text(encoding="utf-8")
        block = src.split('id="efw-section"', 1)[1].split("end #efw-section", 1)[0]
        n_en = block.count('class="l-en"')
        n_zh = block.count('class="l-zh"')
        assert n_en == n_zh and n_en >= 12, (
            f"EN/ZH dual-span parity broken in the ETF windows section "
            f"({n_en} en vs {n_zh} zh)"
        )
        assert not re.search(r'title="[^"]*[一-鿿]', block), (
            "translated text in a title= attribute is CI-guarded house-wide"
        )

    def test_windows_language_only(self):
        """No accuracy/validated/falsifier vocabulary — this is a projection surface."""
        src = TEMPLATE.read_text(encoding="utf-8")
        block = src.split('id="efw-section"', 1)[1].split("end #efw-section", 1)[0]
        banned = ["validated", "已验证", "经验证", "accuracy", "准确率",
                  "falsified", "证伪", "refuted", "proven", "edge over"]
        hits = [w for w in banned if w.lower() in block.lower()]
        assert not hits, f"banned measurement vocabulary in the ETF windows copy: {hits}"

    def test_the_panel_disclaims_authority(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        block = src.split('id="efw-section"', 1)[1].split("end #efw-section", 1)[0]
        flat = re.sub(r"\s+", " ", block)          # the copy is line-wrapped in source
        assert "Forward windows, re-drawn nightly" in flat
        assert "ranking does not read this record" in flat, (
            "display-tier disclosure: the board must not be able to read its own "
            "forward record, and the panel has to say so"
        )
