"""engine.macro_thesis + admin.macro_thesis — the Macro Thesis Ledger.

Covers the contract that actually matters for a conviction register: schema
validation, keep-first/append-only immutability, the ON-OR-AFTER anchor, excess
math against a benchmark on synthetic series, basket-id resolution, the
forward/retro pooling hard-error, and the admin route wiring.

Every test drives ``data_root=tmp_path`` and a fake price store — nothing here
touches the repo's real ``data/`` tree (tests/conftest.py fails the session on
that, and rightly so).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_thesis as mt  # noqa: E402
from lib import store as lib_store  # noqa: E402  (patched directly: mt defers this import)

# ---------------------------------------------------------------------------
# synthetic price store
# ---------------------------------------------------------------------------

# 2024-01-01 is a Monday; 400 business days is enough for both horizons.
_DATES = pd.bdate_range("2024-01-01", periods=400, name="Date")


def _frame(closes) -> pd.DataFrame:
    return pd.DataFrame({"close": closes}, index=_DATES[: len(closes)])


def _flat_then_step(n: int, base: float, step_at: int, factor: float) -> list[float]:
    """base until ``step_at``, base*factor from there on — exact, easy to reason about."""
    return [base if i < step_at else base * factor for i in range(n)]


@pytest.fixture
def fake_store(monkeypatch):
    """Replace lib.store.read with an in-memory (group, name) -> DataFrame map."""
    shelf: dict[str, pd.DataFrame] = {}

    def fake_read(group: str, name: str):
        # The real store is keyed by (group, name); the group only decides WHERE
        # to look, so a name-keyed fake is faithful for resolution-order tests as
        # long as unknown names return None.
        return shelf.get(name)

    # Patch lib.store itself, not `mt.store`. engine/macro_thesis.py imports
    # lib.config/lib.store INSIDE its three consumer functions so the admin panel
    # does not import-cache them (see the note at that module's import block), so
    # `mt.store` no longer exists as an attribute. This is the same module object
    # the deferred import resolves to, so the fake is just as faithful.
    monkeypatch.setattr(lib_store, "read", fake_read)
    return shelf


def _valid_thesis(**over):
    payload = {
        "registered_at": "2024-03-01",
        "author": "operator",
        "title": "Test macro thesis",
        "direction": "long",
        "horizon_sessions": [21, 63],
        "conviction": 4,
        "entry_class": "forward",
        "legs": [{"plane": "rates", "claim": "real yields rolling over", "leg_kind": "judgment"}],
        "instruments": [{"series": "AAA.SS", "benchmark": "absolute"}],
        "confirm_watch": "confirm",
        "risk_watch": "risk",
    }
    payload.update(over)
    return payload


# ---------------------------------------------------------------------------
# schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_valid_thesis_normalizes(self):
        t = mt.normalize_thesis(_valid_thesis())
        assert t["thesis_id"] == "test-macro-thesis-2024-03-01"
        assert t["schema"] == mt.SCHEMA
        assert t["horizon_sessions"] == [21, 63]
        assert t["legs"][0]["state_ref"] is None

    @pytest.mark.parametrize("over,fragment", [
        ({"title": ""}, "title is required"),
        ({"registered_at": "03/01/2024"}, "ISO date"),
        ({"registered_at": ""}, "registered_at is required"),
        ({"direction": "sideways"}, "direction must be one of"),
        ({"author": "nobody"}, "author must be one of"),
        ({"entry_class": "maybe"}, "entry_class must be one of"),
        ({"conviction": 0}, "between 1 and 5"),
        ({"conviction": 6}, "between 1 and 5"),
        ({"conviction": "high"}, "conviction must be an integer"),
        ({"legs": []}, "legs must be a non-empty list"),
        ({"instruments": []}, "instruments must be a non-empty list"),
        ({"horizon_sessions": []}, "horizon_sessions must be a non-empty list"),
        ({"horizon_sessions": [0]}, "between 1 and 504"),
        ({"instruments": [{"series": "bad ticker!", "benchmark": "absolute"}]}, "must be a ticker"),
        ({"legs": [{"plane": "moon", "claim": "x"}]}, "plane must be one of"),
        ({"legs": [{"plane": "rates", "claim": ""}]}, "claim is required"),
    ])
    def test_rejects_bad_field(self, over, fragment):
        with pytest.raises(ValueError) as exc:
            mt.normalize_thesis(_valid_thesis(**over))
        assert fragment in str(exc.value)

    def test_calibrated_leg_without_state_ref_is_refused(self):
        """The exact shape that lets an unwired plane pose as a measured one."""
        payload = _valid_thesis(legs=[
            {"plane": "flow", "claim": "flow velocity positive", "leg_kind": "calibrated"},
        ])
        with pytest.raises(ValueError) as exc:
            mt.normalize_thesis(payload)
        assert "requires a state_ref" in str(exc.value)

    def test_state_ref_roundtrips_observed_value(self):
        t = mt.normalize_thesis(_valid_thesis(legs=[{
            "plane": "cn_sector_cycle",
            "claim": "cycle read",
            "leg_kind": "calibrated",
            "state_ref": {
                "artifact": "data/china_sector_cycles/leg_context.json",
                "key": "b-cn_gold.phase",
                "observed": {"phase": "Bottoming"},
            },
        }]))
        ref = t["legs"][0]["state_ref"]
        assert ref["key"] == "b-cn_gold.phase"
        assert ref["observed"] == {"phase": "Bottoming"}

    def test_leg_kind_defaults_from_state_ref_presence(self):
        with_ref = mt.normalize_thesis(_valid_thesis(legs=[{
            "plane": "flow", "claim": "c",
            "state_ref": {"artifact": "a.json", "key": "k"},
        }]))
        without = mt.normalize_thesis(_valid_thesis(legs=[{"plane": "flow", "claim": "c"}]))
        assert with_ref["legs"][0]["leg_kind"] == "calibrated"
        assert without["legs"][0]["leg_kind"] == "judgment"


class TestRetroSchema:
    def _retro(self, **over):
        payload = _valid_thesis(
            entry_class="retro",
            event_period={"from": "2024-02-28", "to": "2024-05-31"},
            hindsight_risk="selected because it worked",
            sources=["a source"],
        )
        payload.update(over)
        return payload

    def test_valid_retro_normalizes(self):
        t = mt.normalize_thesis(self._retro())
        assert t["entry_class"] == "retro"
        assert t["event_period"] == {"from": "2024-02-28", "to": "2024-05-31"}
        assert t["sources"] == ["a source"]

    @pytest.mark.parametrize("over,fragment", [
        ({"hindsight_risk": ""}, "hindsight_risk is required"),
        ({"sources": []}, "non-empty sources list"),
        ({"event_period": None}, "require event_period"),
        ({"event_period": {"from": "2024-05-31", "to": "2024-02-28"}}, "cannot be before"),
    ])
    def test_retro_requires_its_disclosures(self, over, fragment):
        with pytest.raises(ValueError) as exc:
            mt.normalize_thesis(self._retro(**over))
        assert fragment in str(exc.value)

    def test_forward_entry_cannot_carry_retro_fields(self):
        """A forward row with hindsight fields is a retro row wearing a disguise."""
        with pytest.raises(ValueError) as exc:
            mt.normalize_thesis(_valid_thesis(hindsight_risk="sneaky"))
        assert "only valid on a retro entry" in str(exc.value)


# ---------------------------------------------------------------------------
# append-only / keep-first
# ---------------------------------------------------------------------------

class TestKeepFirstAppendOnly:
    def test_register_appends_one_line_per_thesis(self, tmp_path):
        mt.register(_valid_thesis(title="First"), data_root=tmp_path)
        mt.register(_valid_thesis(title="Second"), data_root=tmp_path)
        rows = mt.load_ledger(data_root=tmp_path)
        assert [r["title"] for r in rows] == ["First", "Second"]
        raw = (tmp_path / mt.LEDGER_DIR / mt.LEDGER_FILE).read_text(encoding="utf-8")
        assert len(raw.strip().splitlines()) == 2

    def test_reregistering_an_id_keeps_the_first_and_refuses(self, tmp_path):
        first = mt.register(_valid_thesis(conviction=1), data_root=tmp_path)
        assert first["ok"] is True
        again = mt.register(_valid_thesis(conviction=5), data_root=tmp_path)
        assert again["ok"] is False
        assert again["kept"] == "first"
        assert "already registered" in again["error"]
        rows = mt.load_ledger(data_root=tmp_path)
        # The incumbent is untouched — the second conviction never landed.
        assert len(rows) == 1 and rows[0]["conviction"] == 1

    def test_amendment_is_a_new_row_that_links_back(self, tmp_path):
        mt.register(_valid_thesis(title="Original"), data_root=tmp_path)
        res = mt.register(
            _valid_thesis(title="Original revised", amended_from="original-2024-03-01"),
            data_root=tmp_path,
        )
        assert res["ok"] is True
        rows = mt.load_ledger(data_root=tmp_path)
        assert len(rows) == 2
        assert rows[1]["amended_from"] == "original-2024-03-01"
        assert rows[0]["title"] == "Original"  # never rewritten

    def test_amended_from_must_name_a_real_row(self, tmp_path):
        with pytest.raises(ValueError) as exc:
            mt.register(_valid_thesis(amended_from="does-not-exist-2024-01-01"),
                        data_root=tmp_path)
        assert "unknown thesis_id" in str(exc.value)

    def test_load_ledger_skips_corrupt_lines(self, tmp_path):
        mt.register(_valid_thesis(), data_root=tmp_path)
        path = tmp_path / mt.LEDGER_DIR / mt.LEDGER_FILE
        with path.open("a", encoding="utf-8") as fh:
            fh.write("{not json\n\n")
        assert len(mt.load_ledger(data_root=tmp_path)) == 1


# ---------------------------------------------------------------------------
# anchor selection — ON OR AFTER
# ---------------------------------------------------------------------------

class TestAnchorSelection:
    def test_anchor_is_the_bar_itself_on_a_trading_day(self):
        idx = _DATES[:10]
        pos = mt.anchor_position(idx, str(idx[3].date()))
        assert pos == 3

    def test_anchor_moves_FORWARD_over_a_non_trading_day(self):
        """A weekend registration must anchor on the NEXT session, never the
        previous one — a backward snap would hand the thesis a price printed
        BEFORE it was written."""
        idx = _DATES[:10]
        friday = idx[4]
        assert friday.dayofweek == 4
        saturday = friday + pd.Timedelta(days=1)
        pos = mt.anchor_position(idx, str(saturday.date()))
        assert pos == 5
        assert idx[pos] > friday  # strictly forward

    def test_anchor_before_history_starts_is_the_first_bar(self):
        idx = _DATES[:10]
        assert mt.anchor_position(idx, "2020-01-01") == 0

    def test_anchor_after_history_ends_is_none(self):
        idx = _DATES[:10]
        assert mt.anchor_position(idx, "2030-01-01") is None

    def test_unresolvable_anchor_is_a_disclosed_null_not_a_crash(self, fake_store):
        fake_store["AAA.SS"] = _frame([100.0] * 10)
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  "2030-01-01", [21, 63])
        assert out["resolution"] == "unresolved"
        assert "no close on or after" in out["reason"]
        assert out["returns"] == {} or all(v is None for v in out["returns"].values())


# ---------------------------------------------------------------------------
# return + excess math
# ---------------------------------------------------------------------------

class TestReturnAndExcessMath:
    def test_simple_return_at_each_horizon(self, fake_store):
        closes = [100.0] * 400
        closes[21:] = [110.0] * (400 - 21)  # +10% at H21
        closes[63:] = [120.0] * (400 - 63)  # +20% at H63
        fake_store["AAA.SS"] = _frame(closes)
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21, 63])
        assert out["returns"]["21"] == pytest.approx(0.10)
        assert out["returns"]["63"] == pytest.approx(0.20)
        assert out["excess"]["21"] is None  # 'absolute' has no benchmark by design
        assert out["status"] == mt.STATUS_GRADED_63

    def test_excess_is_return_minus_benchmark_over_the_same_window(self, fake_store):
        inst = [100.0] * 400
        inst[21:] = [110.0] * (400 - 21)          # +10%
        bench = [50.0] * 400
        bench[21:] = [52.0] * (400 - 21)          # +4%
        fake_store["AAA.SS"] = _frame(inst)
        fake_store["BENCH.SS"] = _frame(bench)
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "BENCH.SS"},
                                  str(_DATES[0].date()), [21])
        assert out["returns"]["21"] == pytest.approx(0.10)
        assert out["excess"]["21"] == pytest.approx(0.06)

    def test_excess_is_negative_when_the_benchmark_wins(self, fake_store):
        fake_store["AAA.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.02))
        fake_store["BENCH.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.05))
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "BENCH.SS"},
                                  str(_DATES[0].date()), [21])
        assert out["excess"]["21"] == pytest.approx(-0.03)

    def test_unresolvable_benchmark_discloses_and_leaves_return_intact(self, fake_store):
        fake_store["AAA.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.10))
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "NOPE.SS"},
                                  str(_DATES[0].date()), [21])
        assert out["returns"]["21"] == pytest.approx(0.10)
        assert out["excess"]["21"] is None
        assert "benchmark_reason" in out

    def test_immature_horizon_is_none_not_zero(self, fake_store):
        """Frozen-until-matured: 30 bars cannot answer H63."""
        fake_store["AAA.SS"] = _frame(_flat_then_step(30, 100.0, 21, 1.10))
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21, 63])
        assert out["returns"]["21"] == pytest.approx(0.10)
        assert out["returns"]["63"] is None
        assert out["status"] == mt.STATUS_GRADED_21

    def test_mark_to_latest_interim_is_available_before_the_first_horizon(self, fake_store):
        fake_store["AAA.SS"] = _frame(_flat_then_step(10, 100.0, 5, 1.07))
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21, 63])
        assert out["status"] == mt.STATUS_INTERIM
        assert out["interim"] == pytest.approx(0.07)
        assert out["returns"]["21"] is None

    def test_interim_is_capped_at_the_event_period_close(self, fake_store):
        """A bounded retro episode must not mark to today.

        The series doubles long AFTER the event window; the interim has to report
        the window (+10%), not the years since (+100%) — otherwise the biggest
        number on a retro card describes a hold nobody claimed.
        """
        closes = [100.0] * 400
        closes[21:] = [110.0] * (400 - 21)
        closes[200:] = [200.0] * (400 - 200)
        fake_store["AAA.SS"] = _frame(closes)
        cutoff = str(_DATES[100].date())
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21], interim_cutoff=cutoff)
        assert out["interim"] == pytest.approx(0.10)
        assert out["interim_date"] == cutoff
        assert "capped at" in out["interim_basis"]

        uncapped = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                       str(_DATES[0].date()), [21])
        assert uncapped["interim"] == pytest.approx(1.00)

    def test_cutoff_before_the_series_reports_no_interim_not_a_todays_mark(self, fake_store):
        """The degenerate cap must fail closed.

        If the event window closed before this instrument has any data, falling
        back to the last bar would print a mark-to-today number on a bounded
        card — the very defect the cap exists to prevent.
        """
        fake_store["AAA.SS"] = _frame(_flat_then_step(400, 100.0, 21, 2.00))
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21],
                                  interim_cutoff="1999-01-01")
        assert out["interim"] is None
        assert out["interim_date"] is None

    def test_retro_thesis_caps_interim_but_forward_marks_to_latest(self, tmp_path, fake_store):
        closes = [100.0] * 400
        closes[21:] = [110.0] * (400 - 21)
        closes[200:] = [200.0] * (400 - 200)
        fake_store["AAA.SS"] = _frame(closes)
        mt.register(_valid_thesis(
            title="Bounded", registered_at="2026-08-04", entry_class="retro",
            event_period={"from": str(_DATES[0].date()), "to": str(_DATES[100].date())},
            hindsight_risk="hindsight", sources=["src"],
        ), data_root=tmp_path)
        mt.register(_valid_thesis(title="Live", registered_at=str(_DATES[0].date())),
                    data_root=tmp_path)
        out = mt.grade(data_root=tmp_path)
        assert out["retro"]["theses"][0]["rollup"]["interim"] == pytest.approx(0.10)
        assert out["forward"]["theses"][0]["rollup"]["interim"] == pytest.approx(1.00)

    def test_zero_elapsed_sessions_is_accruing(self, fake_store):
        fake_store["AAA.SS"] = _frame([100.0] * 5)
        out = mt.grade_instrument({"series": "AAA.SS", "benchmark": "absolute"},
                                  str(_DATES[4].date()), [21, 63])
        assert out["status"] == mt.STATUS_ACCRUING
        assert out["sessions_elapsed"] == 0
        assert out["interim"] is None

    def test_missing_series_is_a_disclosed_null(self, fake_store):
        out = mt.grade_instrument({"series": "GHOST.SS", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21])
        assert out["resolution"] == "unresolved"
        assert "not found in any price store" in out["reason"]

    def test_thesis_rollup_is_the_median_across_instruments(self, fake_store):
        for name, factor in (("A.SS", 1.10), ("B.SS", 1.20), ("C.SS", 1.60)):
            fake_store[name] = _frame(_flat_then_step(400, 100.0, 21, factor))
        thesis = mt.normalize_thesis(_valid_thesis(
            registered_at=str(_DATES[0].date()),
            horizon_sessions=[21],
            instruments=[{"series": n, "benchmark": "absolute"} for n in ("A.SS", "B.SS", "C.SS")],
        ))
        graded = mt.grade_thesis(thesis)
        # median(0.10, 0.20, 0.60) == 0.20 — deliberately not the mean (0.30).
        assert graded["rollup"]["returns"]["21"] == pytest.approx(0.20)

    def test_unresolved_instruments_are_excluded_from_the_rollup_and_counted(self, fake_store):
        fake_store["A.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.10))
        thesis = mt.normalize_thesis(_valid_thesis(
            registered_at=str(_DATES[0].date()),
            horizon_sessions=[21],
            instruments=[{"series": "A.SS", "benchmark": "absolute"},
                         {"series": "GHOST.SS", "benchmark": "absolute"}],
        ))
        graded = mt.grade_thesis(thesis)
        assert graded["unresolved_n"] == 1
        assert graded["rollup"]["returns"]["21"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# basket resolution
# ---------------------------------------------------------------------------

class TestBasketResolution:
    def _membership(self, tmp_path, members):
        d = tmp_path / "baskets_china"
        d.mkdir(parents=True, exist_ok=True)
        (d / "membership.json").write_text(
            json.dumps({"baskets": {"t_gold": {"name": "T", "members": members}}}),
            encoding="utf-8",
        )

    def test_basket_id_resolves_to_equal_weight_member_mean(self, tmp_path, fake_store):
        self._membership(tmp_path, [{"ticker": "M1.SS"}, {"ticker": "M2.SS"}])
        fake_store["M1.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.20))  # +20%
        fake_store["M2.SS"] = _frame(_flat_then_step(400, 50.0, 21, 1.00))   # 0%
        out = mt.grade_instrument({"series": "b-t_gold", "benchmark": "absolute"},
                                  str(_DATES[0].date()), [21], data_root=tmp_path)
        assert out["resolution"] == "basket_equal_weight"
        assert sorted(out["members"]) == ["M1.SS", "M2.SS"]
        # Equal weights AT THE ANCHOR: mean(+20%, 0%) == +10%, and the members'
        # very different price levels (100 vs 50) must not tilt it.
        assert out["returns"]["21"] == pytest.approx(0.10)

    def test_bare_and_prefixed_basket_ids_both_resolve(self, tmp_path, fake_store):
        self._membership(tmp_path, [{"ticker": "M1.SS"}])
        fake_store["M1.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.10))
        bare, _ = mt.resolve_frame("t_gold", data_root=tmp_path)
        prefixed, _ = mt.resolve_frame("b-t_gold", data_root=tmp_path)
        assert bare is not None and prefixed is not None
        assert list(bare.columns) == list(prefixed.columns) == ["M1.SS"]

    def test_removed_members_are_excluded(self, tmp_path, fake_store):
        self._membership(tmp_path, [
            {"ticker": "M1.SS"}, {"ticker": "M2.SS", "removed": "2023-01-01"},
        ])
        fake_store["M1.SS"] = _frame([100.0] * 400)
        fake_store["M2.SS"] = _frame([100.0] * 400)
        frame, meta = mt.resolve_frame("b-t_gold", data_root=tmp_path)
        assert list(frame.columns) == ["M1.SS"]
        assert meta["members"] == ["M1.SS"]

    def test_missing_members_are_disclosed_not_silently_dropped(self, tmp_path, fake_store):
        self._membership(tmp_path, [{"ticker": "M1.SS"}, {"ticker": "GONE.SS"}])
        fake_store["M1.SS"] = _frame([100.0] * 400)
        frame, meta = mt.resolve_frame("b-t_gold", data_root=tmp_path)
        assert list(frame.columns) == ["M1.SS"]
        assert meta["missing"] == ["GONE.SS"]

    def test_basket_with_no_resolvable_members_is_a_disclosed_null(self, tmp_path, fake_store):
        self._membership(tmp_path, [{"ticker": "GONE.SS"}])
        frame, meta = mt.resolve_frame("b-t_gold", data_root=tmp_path)
        assert frame is None
        assert meta["resolution"] == "unresolved"
        assert "no member" in meta["reason"]

    def test_unknown_basket_id_falls_through_to_ticker_lookup(self, tmp_path, fake_store):
        self._membership(tmp_path, [{"ticker": "M1.SS"}])
        frame, meta = mt.resolve_frame("b-not_a_basket", data_root=tmp_path)
        assert frame is None
        assert meta["kind"] == "series"


# ---------------------------------------------------------------------------
# FORWARD / RETRO FIREWALL — the hard error
# ---------------------------------------------------------------------------

class TestForwardRetroFirewall:
    def _rec(self, entry_class):
        return {
            "entry_class": entry_class, "status": mt.STATUS_GRADED_63,
            "horizon_sessions": [21], "legs_calibrated": 0, "legs_judgment": 1,
            "unresolved_n": 0,
            "rollup": {"returns": {"21": 0.1}, "excess": {"21": 0.05}, "interim": 0.1},
        }

    def test_pooling_forward_and_retro_raises(self):
        with pytest.raises(mt.MacroThesisFirewallError) as exc:
            mt.summarize([self._rec("forward"), self._rec("retro")])
        msg = str(exc.value)
        # Pin the DEFECT, not the wording: the message must name both classes and
        # say it is refusing, so a future reword cannot make this pass vacuously.
        assert "forward" in msg and "retro" in msg
        assert "refusing to pool" in msg

    def test_firewall_error_is_a_valueerror_but_its_own_type(self):
        """Its own type so a test asserting 'some ValueError' cannot swallow it."""
        assert issubclass(mt.MacroThesisFirewallError, ValueError)
        assert mt.MacroThesisFirewallError is not ValueError

    def test_single_class_batches_summarize_fine(self):
        for cls in ("forward", "retro"):
            out = mt.summarize([self._rec(cls), self._rec(cls)])
            assert out["entry_class"] == cls
            assert out["n"] == 2

    def test_empty_batch_is_not_an_error(self):
        assert mt.summarize([])["n"] == 0

    def test_grade_returns_separate_sections_and_no_pooled_total(self, tmp_path, fake_store):
        fake_store["AAA.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.10))
        mt.register(_valid_thesis(title="Fwd", registered_at=str(_DATES[0].date())),
                    data_root=tmp_path)
        mt.register(_valid_thesis(
            title="Retro", registered_at=str(_DATES[0].date()), entry_class="retro",
            event_period={"from": str(_DATES[0].date()), "to": str(_DATES[80].date())},
            hindsight_risk="picked because it worked", sources=["src"],
        ), data_root=tmp_path)

        out = mt.grade(data_root=tmp_path)
        assert out["forward"]["summary"]["n"] == 1
        assert out["retro"]["summary"]["n"] == 1
        assert out["forward"]["summary"]["entry_class"] == "forward"
        assert out["retro"]["summary"]["entry_class"] == "retro"
        # There must be no top-level statistic that spans both sections.
        for key in ("summary", "n", "median_return", "theses"):
            assert key not in out, f"grade() must not expose a pooled {key!r}"
        assert "hindsight-disclosed, never pooled" in out["retro"]["label"]

    def test_retro_anchors_on_event_period_not_registration(self, tmp_path, fake_store):
        """A retro row registered today must grade from its historical window."""
        fake_store["AAA.SS"] = _frame(_flat_then_step(400, 100.0, 21, 1.10))
        mt.register(_valid_thesis(
            title="Retro anchor", registered_at="2026-08-04", entry_class="retro",
            event_period={"from": str(_DATES[0].date()), "to": str(_DATES[80].date())},
            hindsight_risk="hindsight", sources=["src"],
        ), data_root=tmp_path)
        graded = mt.grade(data_root=tmp_path)["retro"]["theses"][0]
        assert graded["anchor_date"] == str(_DATES[0].date())
        assert graded["registered_at"] == "2026-08-04"
        assert graded["rollup"]["returns"]["21"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# zero-authority tier
# ---------------------------------------------------------------------------

def test_module_declares_zero_authority_in_its_docstring():
    """The tier is a load-bearing claim; a silent edit of it should fail here."""
    doc = mt.__doc__ or ""
    assert "ZERO AUTHORITY" in doc
    assert "never scores, ranks, gates" in doc.replace("\n", " ").replace("  ", " ") \
        or "never scores, ranks, gates" in " ".join(doc.split())


def test_no_engine_or_script_consumes_this_ledger_as_a_signal():
    """Zero-authority is only real if nothing downstream imports it.

    The admin adapter and this suite are the ONLY permitted importers.  A new
    importer under engine/ or scripts/ means the journal has grown authority and
    must go through pre-registration + gauntlet instead.
    """
    allowed = {"engine/macro_thesis.py", "admin/macro_thesis.py", "tests/test_macro_thesis.py"}
    offenders = []
    for folder in ("engine", "scripts", "lib", "app"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "macro_thesis" in text:
                offenders.append(rel)
    assert not offenders, (
        "macro_thesis is ops/journal tier with zero authority; these modules "
        f"reference it: {offenders}"
    )


# ---------------------------------------------------------------------------
# admin adapter + route wiring
# ---------------------------------------------------------------------------

class TestAdminAdapter:
    def test_panel_shapes_both_sections(self, monkeypatch):
        from admin import macro_thesis as admin_mt

        canned = {
            "forward": {"label": "FORWARD REGISTER (track record)", "theses": [],
                        "summary": {"n": 0}},
            "retro": {"label": "RETRO LIBRARY", "theses": [], "summary": {"n": 0}},
        }
        monkeypatch.setattr(mt, "grade", lambda *a, **k: canned)
        out = admin_mt.panel()
        assert out["ok"] is True
        assert out["forward"]["label"].startswith("FORWARD")
        assert out["retro"]["label"].startswith("RETRO")
        assert "none" in out["authority"]
        assert out["tier"] == "ops/journal"

    def test_panel_degrades_with_a_reason_instead_of_raising(self, monkeypatch):
        from admin import macro_thesis as admin_mt

        def boom(*a, **k):
            raise RuntimeError("store exploded")

        monkeypatch.setattr(mt, "grade", boom)
        out = admin_mt.panel()
        assert out["ok"] is False
        assert "store exploded" in out["error"]

    def test_register_returns_the_validation_error_as_text(self, monkeypatch, tmp_path):
        from admin import macro_thesis as admin_mt

        # Capture the real function BEFORE patching — referring to mt.register
        # inside the replacement would recurse into the patch, not the engine.
        real_register = mt.register
        monkeypatch.setattr(mt, "register", lambda p: real_register(p, data_root=tmp_path))
        bad = admin_mt.register(_valid_thesis(direction="sideways"))
        assert bad["ok"] is False
        assert "direction must be one of" in bad["error"]

        good = admin_mt.register(_valid_thesis())
        assert good["ok"] is True
        assert good["thesis_id"] == "test-macro-thesis-2024-03-01"

        # keep-first surfaces through the adapter too
        dup = admin_mt.register(_valid_thesis())
        assert dup["ok"] is False and dup["kept"] == "first"

    def test_register_rejects_a_non_object_payload(self):
        from admin import macro_thesis as admin_mt
        assert admin_mt.register("not a dict")["ok"] is False


def test_admin_server_dispatches_the_macro_thesis_route(monkeypatch):
    """LIVE round-trip, not a source grep: proves the route really dispatches.

    tests/test_admin_server.py is run by ZERO CI jobs, so a route assertion left
    there would be dark; this suite is wired into a pack.
    """
    import json as _json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from admin import macro_thesis as admin_mt
    from admin.server import Handler, _clear_response_cache

    monkeypatch.setattr(admin_mt, "panel", lambda: {"ok": True, "forward": {"probe": 1},
                                                    "retro": {"probe": 2}})
    _clear_response_cache()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/macro-thesis", timeout=10
        ) as resp:
            assert resp.status == 200
            body = _json.loads(resp.read())
        assert body["ok"] is True
        assert body["forward"] == {"probe": 1}
        assert body["retro"] == {"probe": 2}
    finally:
        _clear_response_cache()
        httpd.shutdown()
        httpd.server_close()


def test_admin_server_wires_the_registration_post():
    src = (ROOT / "admin" / "server.py").read_text(encoding="utf-8")
    assert "macro_thesis.register(b)" in src
    assert "macro_thesis.panel()" in src


def test_app_js_renders_the_page_with_escaped_values():
    js = (ROOT / "admin" / "static" / "app.js").read_text(encoding="utf-8")
    assert "RENDER.macro_thesis" in js
    assert '["macro_thesis", "Macro Thesis"]' in js
    assert 'macro_thesis: ["/api/macro-thesis"]' in js
    # Forward and retro render as separate sections on the page too.
    assert "Forward register" in js and "Retro library" in js
    # Operator free text lands in innerHTML — every interpolation goes via esc().
    for expr in ("esc(t.title)", "esc(leg.claim)", "esc(t.hindsight_risk)",
                 "esc(sr.artifact)", "esc(i.series)"):
        assert expr in js, expr


def test_committed_seed_ledger_is_parseable_and_firewalled():
    """The two shipped seeds must parse under the live schema, not just have shipped."""
    path = ROOT / "data" / "macro_thesis" / "ledger.jsonl"
    assert path.is_file(), "seed ledger must be committed"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 2
    by_class = {r["entry_class"] for r in rows}
    assert by_class == {"forward", "retro"}
    assert len({r["thesis_id"] for r in rows}) == len(rows), "thesis_id must be unique"
    for row in rows:
        # Re-validating the committed bytes catches a hand-edit that drifts from
        # the schema — the ledger is a text file an operator can open.
        assert mt.normalize_thesis(row)["thesis_id"] == row["thesis_id"]
        if row["entry_class"] == "retro":
            assert row["hindsight_risk"].strip()
            assert row["sources"]
        for leg in row["legs"]:
            if leg["leg_kind"] == "calibrated":
                assert leg["state_ref"] and leg["state_ref"]["artifact"] and leg["state_ref"]["key"]
            else:
                assert leg["state_ref"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
