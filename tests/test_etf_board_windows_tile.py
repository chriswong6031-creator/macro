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

    def test_a_corrupt_artifact_renders_exactly_what_a_missing_one_renders(
            self, tmp_path, monkeypatch):
        """m18. The corrupt path used to return `horizons: []`, so the metric grid
        rendered NOTHING while the missing path rendered three honest collecting
        cards. A reader cannot tell a broken file from a broken panel — and the
        emptier of the two states is the one that reads as "never finished"."""
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", tmp_path / "nope.json")
        missing = bm.build_etf_board_windows()
        p = tmp_path / "etf_board_track.json"
        p.write_text("{not json")
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        corrupt = bm.build_etf_board_windows()
        assert corrupt == missing, "corrupt and missing must be the same state"
        assert len(corrupt["horizons"]) == 3, "…and that state renders three cards"

    def test_a_truncated_artifact_is_the_same_collecting_state(self, tmp_path, monkeypatch):
        """The other corruption shape: valid JSON, wrong thing inside."""
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", tmp_path / "nope.json")
        missing = bm.build_etf_board_windows()
        for junk in ("[]", '"a string"', "null"):
            p = tmp_path / "etf_board_track.json"
            p.write_text(junk)
            monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
            out = bm.build_etf_board_windows()
            assert len(out["horizons"]) == 3, f"{junk} rendered an empty grid"
            assert out["state"] == "collecting"
            assert out["horizons"] == missing["horizons"]

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

    def test_the_pooled_windows_are_disclosed_in_both_languages(self, tmp_path,
                                                                monkeypatch):
        """m9. The rows in one horizon are pooled over board dates days apart and
        the board re-publishes the same names, so N graded rows are not N
        independent readings. The panel has to say so — in both languages, in
        windows vocabulary, and with the distinct-name count carried beside the
        row count rather than only the row count."""
        track = _track()
        track["per_horizon"]["h5"]["n_names"] = 2        # 4 rows, 2 distinct names
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(track))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        out = bm.build_etf_board_windows()

        note = out["pooling_note"]
        assert note["en"] and note["zh"], "the disclosure is bilingual or it is not shipped"
        assert re.search(r"[一-鿿]", note["zh"]), "the zh half must actually be zh"
        assert "overlap" in note["en"].lower()
        banned = ["validated", "已验证", "经验证", "accuracy", "准确率",
                  "falsified", "证伪", "refuted", "proven", "edge over"]
        flat = (note["en"] + note["zh"]).lower()
        assert not [w for w in banned if w.lower() in flat], (
            "the disclosure is a windows surface, not a results claim")

        h5 = next(h for h in out["horizons"] if h["horizon"] == 5)
        assert h5["n_names"] == 2 and h5["n_graded"] == 4
        assert h5["windows_overlap"] is True, "2 names behind 4 rows IS the overlap"
        assert h5["names_str"] == "2", "the distinct-name count stays printable"
        assert out["windows_overlap"] is True

    def test_no_overlap_is_not_claimed_when_every_row_is_its_own_name(
            self, tmp_path, monkeypatch):
        """Mutation control: the flag must be able to read False, or it discloses
        nothing."""
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(_track()))          # n_names == n_graded == 4
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        out = bm.build_etf_board_windows()
        h5 = next(h for h in out["horizons"] if h["horizon"] == 5)
        assert h5["windows_overlap"] is False
        assert out["pooling_note"]["en"], "…and the standing note still ships"

    def test_the_pending_split_reaches_the_panel(self, tmp_path, monkeypatch):
        """m10. "56 windows still open" hides how many will never open at all."""
        track = _track()
        track["per_horizon"]["h5"].update(n_pending=56, n_immature=50,
                                          n_unpriceable=6)
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(track))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        h5 = next(h for h in bm.build_etf_board_windows()["horizons"]
                  if h["horizon"] == 5)
        assert h5["n_pending"] == 56
        assert h5["n_immature"] == 50 and h5["n_unpriceable"] == 6

    def test_an_older_artifact_without_the_split_degrades_to_immature(
            self, tmp_path, monkeypatch):
        """The artifact on disk tonight predates m10. Absent keys must read as
        "all pending, none known-dead" — never as an invented delisting count."""
        track = _track()
        track["per_horizon"]["h5"].pop("n_immature", None)
        track["per_horizon"]["h5"].pop("n_unpriceable", None)
        track["per_horizon"]["h5"]["n_pending"] = 56
        p = tmp_path / "etf_board_track.json"
        p.write_text(json.dumps(track))
        monkeypatch.setattr(bm, "ETF_BOARD_TRACK_PATH", p)
        h5 = next(h for h in bm.build_etf_board_windows()["horizons"]
                  if h["horizon"] == 5)
        assert h5["n_immature"] == 56 and h5["n_unpriceable"] == 0

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
