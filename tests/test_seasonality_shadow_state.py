"""Lane 6 — the Neural Web shadow lobe and its forward outcome ledger.

The tests that matter most here are not the happy paths:

* ``test_window_convention_hand_check`` re-derives one year's window return by
  hand-indexing the committed fixture.  A prior session on exactly this window
  shipped |t| 5.60 against a true 7.25 because ``start_doy`` was read one slot
  off, and NOTHING in the output looks wrong when that happens — the number is
  simply, quietly, a different number.  The hand-check is the only place the
  off-by-one has to show itself.
* ``test_gap_for_absent_entity_*`` pins fail-open: the entity tree is
  R2-published, so a partially-synced checkout is the normal case and it has to
  degrade into a countable hole rather than an exception.
* ``test_ledger_*`` pins the append-only law — a second run on the same night
  appends nothing, and prior bytes are never rewritten.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.seasonality import contracts, state as season_state  # noqa: E402
from engine.seasonality.panel import date_for_slot, slot_for_date, slots_for  # noqa: E402
from scripts import build_seasonality_shadow_state as emitter  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "seasonality"
_NOW = datetime(2026, 8, 2, 4, 0, 0, tzinfo=timezone.utc)

# SPY's committed default window: doy 284 (Oct 11) -> doy 344 (Dec 10).
_SPY_START_DOY = 284
_SPY_END_DOY = 344


# ---------------------------------------------------------------------------
# Fixture universe helpers
# ---------------------------------------------------------------------------


def _entity(stem: str) -> dict:
    return json.loads((_FIXTURES / f"{stem}.entity.json").read_text(encoding="utf-8"))


def _write_universe(
    root: Path,
    covered: dict[str, dict | None],
    *,
    as_of: str = "2026-07-31",
) -> Path:
    """Build a tmp ``site/seasonalitydata`` tree whose covered set we control.

    ``covered`` maps SYMBOL -> entity payload, or None to register the symbol in
    the index while deliberately withholding its entity file.  Every listed
    symbol is labelled Health Care, because the covered set is MEASURED from the
    index's own sector labels.
    """
    base = root / "site" / "seasonalitydata"
    (base / "entities").mkdir(parents=True, exist_ok=True)
    entries = []
    for symbol, payload in covered.items():
        entries.append(
            {
                "symbol": symbol,
                "name": symbol,
                "group": "equity",
                "sector": season_state.BIOPHARMA_SECTOR,
                "n_years": 25,
                "first_year": 2001,
                "n_years_panel": 25,
            }
        )
        if payload is not None:
            (base / "entities" / f"{symbol}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
    index = {
        "schema": "biopharma_seasonality.index.v1",
        "as_of": as_of,
        "default_symbol": "SPY",
        "n_entities": len(entries),
        "entities": entries,
    }
    (base / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return base


def _states(root: Path, now: datetime = _NOW, live_n: dict | None = None):
    index = json.loads(
        (root / "site" / "seasonalitydata" / "index.json").read_text(encoding="utf-8")
    )
    return season_state.build_states(
        index, root / "site" / "seasonalitydata" / "entities", live_n or {}, now
    )


# ---------------------------------------------------------------------------
# 1. The contract holds for every emitted state
# ---------------------------------------------------------------------------


class TestContract:
    def test_every_state_passes_the_fail_closed_contract(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, gaps = _states(tmp_path)
        assert set(states) == {"MU", "SPY"}
        assert gaps == []
        for symbol, state in states.items():
            # Raises ContractError if anything drifted.
            contracts.validate_neuralweb_state(state)
            assert state["schema"] == contracts.NEURALWEB_STATE_SCHEMA, symbol
            assert state["tier"] == "shadow", symbol
            assert state["is_context_only"] is True, symbol

    def test_authority_ceiling_is_all_false(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        states, _ = _states(tmp_path)
        authority = states["SPY"]["authority"]
        assert authority["may_explain"] is True
        assert authority["may_flag_attention"] is True
        for key in (
            "may_deescalate",
            "may_rank",
            "may_gate",
            "may_size",
            "may_originate",
            "may_rewrite_geometry",
            "may_boost_confidence",
        ):
            assert authority[key] is False, f"{key} must be false — seasonality cannot act"

    def test_contradiction_hook_visible_on_every_state(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        for symbol, state in states.items():
            hooks = state["hooks"]
            assert hooks["calendar_tailwind_vs_event_hazard"]["status"], symbol
            assert hooks["momentum_overlap"]["status"] == "not_yet_measured", symbol

    def test_state_stays_bounded(self, tmp_path):
        """Bounded and explainable is a Lane 6 acceptance line — no year arrays."""
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        for symbol, state in states.items():
            size = len(json.dumps(state, separators=(",", ":")).encode("utf-8"))
            assert size < 4096, f"{symbol} state is {size} bytes"


# ---------------------------------------------------------------------------
# 2. The window convention, checked by hand
# ---------------------------------------------------------------------------


class TestWindowConvention:
    def test_window_convention_hand_check(self):
        """``cum[end_doy - 1] - cum[start_doy - 1]``, indexed by hand off the JSON.

        Deliberately not expressed through any helper: this test exists to catch
        a one-slot shift, and a shifted helper would shift the expectation too.
        """
        entity = _entity("SPY")
        years = entity["years"]
        scale = entity["calendar"]["cum_scale"]

        # 284 -> index 283; 344 -> index 343. Written as literals on purpose.
        expected_first_year = (years[0]["cum"][343] - years[0]["cum"][283]) * scale
        computed = season_state._window_deltas(
            [row["cum"] for row in years], _SPY_START_DOY, _SPY_END_DOY
        )
        assert computed[0] * scale == pytest.approx(expected_first_year, abs=1e-12)
        assert len(computed) == len(years)

    def test_p_matches_the_producers_own_up_share(self, tmp_path):
        """The state's ``p`` and the page's ``up_share`` must be ONE number.

        Both are "share of complete years the window finished up", and the
        producer already published its answer for this exact window inside
        ``family.registered_panel``. If the two ever disagree, one of them is
        using a different endpoint convention or a different >0 test.
        """
        entity = _entity("SPY")
        row = next(
            r
            for r in entity["family"]["registered_panel"]
            if (r["start_doy"], r["end_doy"]) == (_SPY_START_DOY, _SPY_END_DOY)
        )
        _write_universe(tmp_path, {"SPY": entity})
        states, _ = _states(tmp_path)
        assert states["SPY"]["forecast"]["p"] == pytest.approx(row["up_share"])

    def test_scalar_and_vector_doy_mappings_agree_across_a_leap_year(self):
        """``slot_for_date`` may not fork the Feb-29 fold ``slots_for`` implements."""
        days = pd.date_range("2024-01-01", "2024-12-31", freq="D")
        vector = list(slots_for(pd.DatetimeIndex(days)))
        scalar = [slot_for_date(stamp.date()) for stamp in days]
        assert scalar == [int(value) for value in vector]
        assert scalar[slot_for_date(date(2024, 2, 29))] == scalar[
            slot_for_date(date(2024, 2, 28))
        ]

    def test_slot_date_round_trip_holds_in_a_leap_year(self):
        for doy in (1, 59, 60, 284, 344, 365):
            resolved = date_for_slot(doy - 1, 2024)
            assert slot_for_date(resolved) == doy - 1


# ---------------------------------------------------------------------------
# 3. The forecast block's internal arithmetic
# ---------------------------------------------------------------------------


class TestForecast:
    def test_edge_is_exactly_p_minus_baseline(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        for symbol, state in states.items():
            forecast = state["forecast"]
            assert forecast["edge"] == pytest.approx(
                forecast["p"] - forecast["p_baseline"], abs=1e-9
            ), symbol

    def test_ci90_contains_p_and_stays_a_probability(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        for symbol, state in states.items():
            low, high = state["forecast"]["ci90"]
            assert 0.0 <= low <= high <= 1.0, symbol
            assert low <= state["forecast"]["p"] <= high, symbol

    @pytest.mark.parametrize("p", [0.0, 0.04, 0.5, 0.96, 1.0])
    @pytest.mark.parametrize("n", [1, 6, 19, 25, 400])
    def test_wilson_contains_p_at_the_endpoints(self, p, n):
        """Wald collapses to a point at p=0 and p=1; Wilson may not."""
        low, high = season_state._wilson_ci90(p, n)
        assert low - 1e-12 <= p <= high + 1e-12
        assert -1e-12 <= low and high <= 1.0 + 1e-12

    def test_baseline_is_the_same_length_all_starts_mean(self):
        """Pinned against an independent recomputation off the raw fixture."""
        entity = _entity("SPY")
        years_cum = [row["cum"] for row in entity["years"]]
        horizon = _SPY_END_DOY - _SPY_START_DOY
        shares = []
        for start in range(1, 365 - horizon + 1):
            deltas = [row[start + horizon - 1] - row[start - 1] for row in years_cum]
            shares.append(sum(1 for value in deltas if value > 0) / len(deltas))
        assert len(shares) == 365 - horizon
        assert season_state._baseline_up_share(years_cum, horizon) == pytest.approx(
            sum(shares) / len(shares)
        )

    def test_baseline_basis_is_declared(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        states, _ = _states(tmp_path)
        assert (
            states["SPY"]["forecast"]["baseline_basis"]
            == "same_length_all_starts_mean"
        )


# ---------------------------------------------------------------------------
# 4. The calendar clock
# ---------------------------------------------------------------------------


class TestClock:
    @pytest.mark.parametrize(
        "today,expected_phase,expected_end",
        [
            (date(2026, 11, 1), "in_window", "2026-12-10"),      # inside 284..344
            (date(2026, 9, 27), "pre_window", "2026-12-10"),     # 14 days before start
            (date(2026, 3, 1), "out_of_window", "2026-12-10"),   # far outside
            (date(2026, 12, 20), "out_of_window", "2027-12-10"),  # past end -> rolls over
        ],
    )
    def test_phase_and_occurrence(self, tmp_path, today, expected_phase, expected_end):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        now = datetime(today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc)
        states, _ = _states(tmp_path, now=now)
        clock = states["SPY"]["clock"]
        assert clock["type"] == "calendar"
        assert clock["phase"] == expected_phase
        assert clock["occurrence_end_date"] == expected_end
        assert clock["pattern_id"] == f"cal:SPY:{_SPY_START_DOY}-{_SPY_END_DOY}"

    def test_horizon_td_is_measured_from_the_data_asof(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        now = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
        states, _ = _states(tmp_path, now=now)
        forecast = states["SPY"]["forecast"]
        assert forecast["horizon_td"] == (date(2027, 12, 10) - date(2026, 7, 31)).days
        assert forecast["horizon_td"] > 0

    def test_pre_window_boundary_is_21_days(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        # doy 284 - 21 = 263 (Sep 20) is still pre_window; 262 (Sep 19) is not.
        inside = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        outside = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        assert _states(tmp_path, now=inside)[0]["SPY"]["clock"]["phase"] == "pre_window"
        assert (
            _states(tmp_path, now=outside)[0]["SPY"]["clock"]["phase"] == "out_of_window"
        )


# ---------------------------------------------------------------------------
# 5. Fail-open with structured gaps
# ---------------------------------------------------------------------------


class TestGaps:
    def test_absent_entity_is_a_gap_and_the_rest_still_emit(self, tmp_path):
        _write_universe(
            tmp_path, {"SPY": _entity("SPY"), "GHOST": None, "MU": _entity("MU")}
        )
        states, gaps = _states(tmp_path)
        assert set(states) == {"MU", "SPY"}, "one absent artifact took the lobe down"
        assert [gap["symbol"] for gap in gaps] == ["GHOST"]
        assert gaps[0]["reason_code"] == "entity_artifact_absent"
        assert gaps[0]["detail"]

    def test_unreadable_entity_is_a_gap_not_an_exception(self, tmp_path):
        base = _write_universe(tmp_path, {"SPY": _entity("SPY"), "BROKEN": None})
        (base / "entities" / "BROKEN.json").write_text("{not json", encoding="utf-8")
        states, gaps = _states(tmp_path)
        assert set(states) == {"SPY"}
        assert gaps[0] == {
            "symbol": "BROKEN",
            "reason_code": "entity_artifact_unreadable",
            "detail": gaps[0]["detail"],
        }
        assert "invalid JSON" in gaps[0]["detail"]

    def test_shifted_window_convention_is_refused_not_guessed(self, tmp_path):
        entity = _entity("SPY")
        entity["calendar"]["window_convention"] = "cum[end_doy] - cum[start_doy]"
        _write_universe(tmp_path, {"SPY": entity})
        states, gaps = _states(tmp_path)
        assert states == {}
        assert gaps[0]["reason_code"] == "schema_mismatch"

    def test_wrong_schema_is_a_gap(self, tmp_path):
        entity = _entity("SPY")
        entity["schema"] = "biopharma_seasonality.entity.v99"
        _write_universe(tmp_path, {"SPY": entity})
        states, gaps = _states(tmp_path)
        assert states == {}
        assert gaps[0]["reason_code"] == "schema_mismatch"

    def test_non_biopharma_symbols_are_not_covered(self, tmp_path):
        base = _write_universe(tmp_path, {"SPY": _entity("SPY")})
        index = json.loads((base / "index.json").read_text(encoding="utf-8"))
        index["entities"][0]["sector"] = "Information Technology"
        (base / "index.json").write_text(json.dumps(index), encoding="utf-8")
        states, gaps = _states(tmp_path)
        assert states == {} and gaps == []


# ---------------------------------------------------------------------------
# 6. The context expires
# ---------------------------------------------------------------------------


class TestExpiry:
    def test_ttl_is_48_hours(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        for symbol, state in states.items():
            available = datetime.fromisoformat(state["available_at"].replace("Z", "+00:00"))
            expires = datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
            assert expires - available == timedelta(hours=season_state.TTL_HOURS), symbol
            assert season_state.TTL_HOURS == 48


# ---------------------------------------------------------------------------
# 7. Abstention
# ---------------------------------------------------------------------------


class TestAbstain:
    def test_thin_panel_abstains_but_still_validates(self, tmp_path):
        entity = _entity("SPY")
        entity["years"] = entity["years"][:4]
        _write_universe(tmp_path, {"SPY": entity})
        states, gaps = _states(tmp_path)
        assert gaps == []
        state = states["SPY"]
        contracts.validate_neuralweb_state(state)
        assert state["uncertainty"]["abstain"] is True
        assert "thin_years" in state["uncertainty"]["flags"]
        assert state["evidence"]["n_independent"] == 4

    def test_stale_artifact_abstains(self, tmp_path):
        entity = _entity("SPY")
        entity["asof"] = "2026-06-01"  # two months behind the index
        _write_universe(tmp_path, {"SPY": entity}, as_of="2026-07-31")
        states, _ = _states(tmp_path)
        assert "artifact_stale" in states["SPY"]["uncertainty"]["flags"]
        assert states["SPY"]["uncertainty"]["abstain"] is True

    def test_thin_forward_sample_flag_clears_once_graded(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        thin, _ = _states(tmp_path, live_n={"SPY": 3})
        assert "forward_sample_thin" in thin["SPY"]["uncertainty"]["flags"]
        assert thin["SPY"]["evidence"]["live_n"] == 3
        deep, _ = _states(tmp_path, live_n={"SPY": 40})
        assert "forward_sample_thin" not in deep["SPY"]["uncertainty"]["flags"]


# ---------------------------------------------------------------------------
# 8. The forward outcome ledger
# ---------------------------------------------------------------------------


_ASOF = date(2026, 7, 31)


def _register(**overrides) -> dict:
    row = {
        "row_type": "register",
        "schema": season_state.LEDGER_SCHEMA,
        "key": "TST:2025:100-130",
        "symbol": "TST",
        "registered_asof": "2025-01-02",
        "start_doy": 100,      # Apr 10
        "end_doy": 130,        # May 10
        "occurrence_end_date": "2025-05-10",
        "p": 0.7,
        "p_baseline": 0.5,
        "n_years": 25,
        "pattern_spec_hash": "sha256:" + "0" * 64,
        "model_version": season_state.MODEL_VERSION,
        "tier": "shadow",
    }
    row.update(overrides)
    return row


class TestLedger:
    def test_every_shown_forecast_registers_once(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        states, _ = _states(tmp_path)
        rows = season_state.register_rows(states, set(), _ASOF)
        assert [row["symbol"] for row in rows] == ["MU", "SPY"]
        # MU's window (doy 142-147, late May) already closed before the Aug 2
        # clock, so its NEXT occurrence — and therefore its key — is 2027.
        assert {row["key"] for row in rows} == {
            "MU:2027:142-147",
            f"SPY:2026:{_SPY_START_DOY}-{_SPY_END_DOY}",
        }
        for row in rows:
            assert row["row_type"] == "register"
            assert row["tier"] == "shadow"
            assert row["registered_asof"] == "2026-07-31"
            assert row["p"] is not None and row["p_baseline"] is not None

        # Same night, same inputs: nothing new.
        again = season_state.register_rows(states, {row["key"] for row in rows}, _ASOF)
        assert again == []

    def test_abstaining_state_is_not_registered(self, tmp_path):
        entity = _entity("SPY")
        entity["years"] = entity["years"][:4]
        _write_universe(tmp_path, {"SPY": entity})
        states, _ = _states(tmp_path)
        assert season_state.register_rows(states, set(), _ASOF) == []

    def test_registration_is_not_phase_gated(self, tmp_path):
        """A window nine months out still gets its forward row."""
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        states, _ = _states(tmp_path, now=now)
        assert states["SPY"]["clock"]["phase"] == "out_of_window"
        assert len(season_state.register_rows(states, set(), _ASOF)) == 1

    def test_grade_computes_the_realized_log_return(self):
        closes = [
            (date(2025, 4, 8), 99.0),
            (date(2025, 4, 10), 100.0),   # entry: the start_doy close
            (date(2025, 4, 30), 105.0),
            (date(2025, 5, 9), 108.0),
            (date(2025, 5, 10), 110.0),   # exit: the end_doy close
            (date(2025, 5, 13), 120.0),   # after the window — must not be used
        ]
        rows = season_state.grade_rows([_register()], {"TST": closes}, _ASOF)
        assert len(rows) == 1
        row = rows[0]
        assert row["row_type"] == "grade"
        assert row["grade_status"] == "graded"
        assert row["realized_log_return"] == pytest.approx(
            round(math.log(110.0 / 100.0), 6)
        )
        assert row["outcome_up"] is True
        assert row["brier"] == pytest.approx(round((0.7 - 1.0) ** 2, 6))
        assert row["key"] == "TST:2025:100-130"

    def test_grade_uses_the_last_close_on_or_before_each_endpoint(self):
        """Non-trading endpoints carry a zero log return — the prior close is right."""
        closes = [
            (date(2025, 4, 9), 100.0),   # Apr 10 is not a session
            (date(2025, 5, 8), 90.0),    # May 10 is not a session
            (date(2025, 5, 20), 200.0),
        ]
        row = season_state.grade_rows([_register()], {"TST": closes}, _ASOF)[0]
        assert row["realized_log_return"] == pytest.approx(
            round(math.log(90.0 / 100.0), 6)
        )
        assert row["outcome_up"] is False
        assert row["brier"] == pytest.approx(round(0.7 ** 2, 6))

    def test_unmatured_occurrence_is_not_graded(self):
        future = _register(occurrence_end_date="2026-12-10", key="TST:2026:100-130")
        closes = [(date(2026, 7, 30), 100.0)]
        assert season_state.grade_rows([future], {"TST": closes}, _ASOF) == []

    def test_matured_but_priceless_stays_pending_then_closes_out(self):
        recent = _register(occurrence_end_date="2026-07-20", key="TST:2026:100-130")
        assert season_state.grade_rows([recent], {}, _ASOF) == [], (
            "11 days past the end with no prices is PENDING, not a verdict"
        )
        stale = _register(occurrence_end_date="2026-05-01", key="TST:2026b:100-130")
        rows = season_state.grade_rows([stale], {}, _ASOF)
        assert len(rows) == 1
        assert rows[0]["grade_status"] == "ungradable_missing_prices"
        assert rows[0]["realized_log_return"] is None
        assert rows[0]["outcome_up"] is None
        assert rows[0]["brier"] is None

    def test_store_behind_the_window_end_is_never_graded_off_a_short_series(self):
        """A store that stops before the exit date cannot price the exit.

        The last close is NOT silently promoted to the exit price — that would
        grade a 30-day window on 22 days of it and call the result an outcome.
        Recently ended: pending. Long past: closed out as ungradable.
        """
        closes = [(date(2025, 4, 10), 100.0), (date(2025, 5, 2), 104.0)]
        recent = _register(occurrence_end_date="2026-07-20", key="TST:2026:100-130")
        assert season_state.grade_rows([recent], {"TST": closes}, _ASOF) == []

        rows = season_state.grade_rows([_register()], {"TST": closes}, _ASOF)
        assert len(rows) == 1
        assert rows[0]["grade_status"] == "ungradable_missing_prices"
        assert rows[0]["realized_log_return"] is None

    def test_live_n_counts_graded_rows_only(self):
        rows = [
            {"row_type": "grade", "grade_status": "graded", "symbol": "AAA"},
            {"row_type": "grade", "grade_status": "graded", "symbol": "AAA"},
            {"row_type": "grade", "grade_status": "ungradable_missing_prices", "symbol": "AAA"},
            {"row_type": "grade", "grade_status": "graded", "symbol": "BBB"},
            {"row_type": "register", "symbol": "AAA"},
        ]
        assert season_state.live_n_by_symbol(rows) == {"AAA": 2, "BBB": 1}

    def test_occurrence_key_shape(self):
        assert season_state.occurrence_key("XBI", 2026, 284, 344) == "XBI:2026:284-344"


# ---------------------------------------------------------------------------
# 9. The emitter end to end
# ---------------------------------------------------------------------------


class TestEmitter:
    def test_writes_a_stamped_state_file(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        summary = emitter.build(root=tmp_path, now=_NOW)
        assert summary["n_covered"] == 2 and summary["n_emitted"] == 2
        payload = json.loads(
            (tmp_path / emitter.STATE_PATH).read_text(encoding="utf-8")
        )
        assert payload["schema"] == season_state.STATE_FILE_SCHEMA
        assert payload["as_of"] == "2026-07-31"
        assert payload["universe"] == {
            "source": "site/seasonalitydata/index.json",
            "sector_filter": "Health Care",
            "n_covered": 2,
            "n_emitted": 2,
            "n_gaps": 0,
        }
        assert set(payload["states"]) == {"MU", "SPY"}
        # Envelope keys are SIBLINGS, never a wrapper.
        for key in ("schema_version", "produced_by", "produced_at", "inputs_hash", "tier"):
            assert key in payload
        assert payload["tier"] == "shadow"

    def test_absent_index_still_writes_an_empty_map(self, tmp_path):
        summary = emitter.build(root=tmp_path, now=_NOW)
        assert summary["n_covered"] == 0 and summary["n_emitted"] == 0
        payload = json.loads(
            (tmp_path / emitter.STATE_PATH).read_text(encoding="utf-8")
        )
        assert payload["states"] == {}
        assert payload["gaps"][0]["reason_code"] == "index_absent"
        assert payload["gaps"][0]["symbol"] is None

    def test_rerun_appends_nothing_and_never_rewrites(self, tmp_path):
        _write_universe(tmp_path, {"SPY": _entity("SPY"), "MU": _entity("MU")})
        ledger = tmp_path / emitter.LEDGER_PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        seeded = json.dumps(_register(), sort_keys=True) + "\n"
        ledger.write_text(seeded, encoding="utf-8")
        prior = ledger.read_bytes()

        first = emitter.build(root=tmp_path, now=_NOW)
        assert first["n_registered"] == 2
        after_first = ledger.read_bytes()
        assert after_first.startswith(prior), "an append-only ledger rewrote its history"

        second = emitter.build(root=tmp_path, now=_NOW)
        assert second["n_registered"] == 0 and second["n_graded"] == 0
        assert ledger.read_bytes() == after_first, "a same-night re-run duplicated rows"

        rows = [json.loads(line) for line in ledger.read_text().splitlines() if line]
        keys = [row["key"] for row in rows]
        assert len(keys) == len(set(keys)) == 3

    def test_grading_is_skipped_without_a_price_store(self, tmp_path):
        """NEVER fabricate: no store means no grade, and the gap says so."""
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        ledger = tmp_path / emitter.LEDGER_PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps(_register(occurrence_end_date="2026-05-10"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary = emitter.build(root=tmp_path, now=_NOW)
        assert summary["n_graded"] == 0
        payload = json.loads((tmp_path / emitter.STATE_PATH).read_text(encoding="utf-8"))
        assert any(gap["reason_code"] == "price_store_absent" for gap in payload["gaps"])

    def test_grades_a_matured_row_from_the_parquet_store(self, tmp_path):
        """The realized number comes off the same adjusted ``close`` the panel folds."""
        _write_universe(tmp_path, {"SPY": _entity("SPY")})
        store = tmp_path / "data" / "yahoo"
        store.mkdir(parents=True, exist_ok=True)
        index = pd.to_datetime(
            [date(2025, 4, 9), date(2025, 4, 10), date(2025, 5, 9), date(2025, 5, 10), date(2026, 7, 30)]
        )
        pd.DataFrame({"close": [95.0, 100.0, 108.0, 110.0, 150.0]}, index=index).to_parquet(
            store / "TST.parquet"
        )
        ledger = tmp_path / emitter.LEDGER_PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(_register(), sort_keys=True) + "\n", encoding="utf-8")

        summary = emitter.build(root=tmp_path, now=_NOW)
        assert summary["n_graded"] == 1
        rows = [json.loads(line) for line in ledger.read_text().splitlines() if line]
        grade = next(row for row in rows if row["row_type"] == "grade")
        assert grade["grade_status"] == "graded"
        assert grade["realized_log_return"] == pytest.approx(
            round(math.log(110.0 / 100.0), 6)
        )

        # Second night: already graded, so nothing is re-graded.
        assert emitter.build(root=tmp_path, now=_NOW)["n_graded"] == 0

    def test_main_returns_zero_on_an_empty_tree(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "--root", str(tmp_path)])
        assert emitter.main() == 0

    def test_annotations_start_the_line(self, capsys):
        emitter._annotate("seasonality_shadow", "probe")
        captured = capsys.readouterr().out.strip()
        assert captured.startswith("::warning title=seasonality_shadow::"), captured
