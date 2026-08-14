"""The US Context Vector store must keep ACCRUING, and say so when it does not.

Between 2026-08-08 and 2026-08-13 this store stamped nothing while the board ran
every night, inside a GREEN engine job. The chain:

1. `context_api._regime_dim` has a merge path that fires when BOTH
   `regime_history.parquet` resolves as-of the date AND `data/regime/latest.json`
   is current. It returned `value={"history": {...}, "live": {...}}`;
2. `context_frame` flattens a dimension's value dict generically, so that became
   two DICT-VALUED columns, `regime__history` and `regime__live`;
3. the store's schema-union append reindexes prior rows of a new column to float
   NaN, pyarrow refuses to unify a struct with a non-null float, and `to_parquet`
   raised `cannot mix struct and non-struct, non-null values`;
4. `append_candidates` catches everything and returns 0, logging through a
   prefixing formatter — so the only trace was a log line GitHub drops.

Four fixes, four tests: the producer emits scalars (1); an unclassified container
column costs THAT COLUMN, not the night (2/3); the NaN→None coercion covers the
~120 flattened dimension columns the named lists never could (3); and a failure is
announced with a line-start `::warning` instead of dying quietly (4).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import us_context_vector as ucv


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _verdict(**extra):
    verdict = {
        "eligible": True, "tier_cascade": "T2", "tier_sub": "deep", "ticks": 1,
        "weight": 1.0, "state": "crossed", "reason": "confluence",
        "asof": "2026-08-14", "veto_legs_null": {},
    }
    verdict.update(extra)
    return verdict


@pytest.fixture
def verdicts():
    return {"AAA": _verdict(), "BBB": _verdict(eligible=False, tier_cascade=None)}


@pytest.fixture
def append_kwargs(tmp_path):
    return {
        "board_definition": "us_prophet_v1",
        "is_buyable": lambda v: bool(v.get("eligible")),
        "root": tmp_path,
        "event_rows": {},
        "with_context_dims": False,
    }


def _dim_frame(monkeypatch, columns: dict):
    """Make ``context_dimension_frame`` return an exact extra-column set."""
    def _fake(tickers, asof, root=None):
        rows = {"ticker": list(tickers)}
        for name, value in columns.items():
            rows[name] = [value] * len(tickers)
        return pd.DataFrame(rows)
    monkeypatch.setattr(ucv, "context_dimension_frame", _fake)


# --------------------------------------------------------------------------- #
# 1. the producer: the merge path emits scalars only
# --------------------------------------------------------------------------- #

class TestRegimeMergePathIsScalarOnly:
    """Runs the REAL `_regime_dim` over a real parquet + a real latest.json.

    A stubbed regime dimension would pass with the defect still in place — the
    whole failure was in what the merge path CONSTRUCTS, so the construction is
    what has to run.
    """

    @staticmethod
    def _root(tmp_path):
        regime = tmp_path / "data" / "regime"
        regime.mkdir(parents=True)
        today = pd.Timestamp.today().normalize()
        history = pd.DataFrame(
            {
                "growth_score": [-0.21, -0.13],
                "inflation_score": [0.04, 0.08],
                "quad": ["Q2", "Q2"],
                "raw_quad": ["Q3", "Q3"],
                "recession": [False, False],
                "flag_gex": [False, True],
                "n_flags": [0, 1],
                "transition_state": ["STABLE", "TRANSITIONING"],
            },
            index=pd.DatetimeIndex([today - pd.Timedelta(days=1), today], name="date"),
        )
        history.to_parquet(regime / "regime_history.parquet")
        # Shaped like the real artifact: a handful of scalars carried among ~50
        # nested blocks. Those blocks are exactly why the live value dict can
        # never BE the merged value.
        (regime / "latest.json").write_text(json.dumps({
            "schema_version": 1,
            "asof": str(today.date()),
            "quad": "Q2",
            "quad_name": "Reflation",
            "growth_score": -0.133,
            "transition_flags": {"flag_gex": True, "flag_credit_equity": False},
            "confirming": ["growth_copper_gold", "growth_wei_trend"],
            "sector_rs": [{"ticker": "XLV", "rs": 0.216}],
            "vol_regime": {"regime": "normalizing", "risk_score": 0.298},
            "playbook": {"headline": "Reflation is still the confirmed label"},
        }))
        return tmp_path

    def test_the_merge_path_value_carries_no_container(self, tmp_path):
        from engine.neuralweb import context_api

        context_api._regime_hist_cache.clear()
        dim = context_api._regime_dim(pd.Timestamp.today().normalize(),
                                      self._root(tmp_path))

        assert dim.get("basis") == "pit_live", "both sources current = a live read"
        value = dim["value"]
        offenders = {k: type(v).__name__ for k, v in value.items()
                     if isinstance(v, (dict, list, set, tuple)) or getattr(v, "ndim", 0)}
        assert not offenders, (
            "a container in a dimension value becomes a container COLUMN and kills "
            f"the committed store's append: {offenders}")
        assert "history" not in value and "live" not in value

    def test_the_merged_value_keeps_the_committed_column_shape(self, tmp_path):
        from engine.neuralweb import context_api

        context_api._regime_hist_cache.clear()
        value = context_api._regime_dim(
            pd.Timestamp.today().normalize(), self._root(tmp_path))["value"]

        # Every history field survives — the store's regime__* columns must not
        # die and be replaced by a differently-named set.
        for field in ("growth_score", "inflation_score", "quad", "raw_quad",
                      "recession", "flag_gex", "n_flags", "transition_state"):
            assert field in value, f"{field} would go null forward"
        # ...plus exactly the two scalar provenance extras.
        assert value["history_as_of"] == str(pd.Timestamp.today().normalize().date())
        assert value["live_quad"] == "Q2"

    def test_both_sources_disagreeing_stays_visible_in_the_row(self, tmp_path):
        """A merge that hid a disagreement would be worse than the nested blob."""
        from engine.neuralweb import context_api

        root = self._root(tmp_path)
        live = json.loads((root / "data" / "regime" / "latest.json").read_text())
        live["quad"] = "Q3"
        (root / "data" / "regime" / "latest.json").write_text(json.dumps(live))
        context_api._regime_hist_cache.clear()

        value = context_api._regime_dim(pd.Timestamp.today().normalize(), root)["value"]
        assert value["quad"] == "Q2" and value["live_quad"] == "Q3"

    def test_the_flattened_frame_has_no_container_column(self, tmp_path):
        """End to end through the flatten that actually produced the bad columns."""
        from engine.neuralweb import context_api

        context_api._regime_hist_cache.clear()
        frame = context_api.context_frame(
            ["AAPL"], date=pd.Timestamp.today().normalize(), root=self._root(tmp_path))
        regime_cols = [c for c in frame.columns if c.startswith("regime__")]
        assert regime_cols
        assert "regime__live" not in frame.columns
        assert "regime__history" not in frame.columns
        for column in regime_cols:
            value = frame[column].iloc[0]
            assert not isinstance(value, (dict, list, set, tuple)), column


# --------------------------------------------------------------------------- #
# 2/3. the store boundary
# --------------------------------------------------------------------------- #

class TestStoreBoundaryContainment:

    def test_an_unclassified_container_column_costs_the_column_not_the_night(
        self, verdicts, append_kwargs, tmp_path, capsys, monkeypatch
    ):
        """The exact 2026-08-08 shape: a new dict-valued column arrives on night 2
        against a part that does not have it."""
        assert ucv.append_candidates(verdicts, "2026-08-13", **append_kwargs)

        _dim_frame(monkeypatch, {"somenewdim__blob": {"secret": "payload"}})
        kwargs = dict(append_kwargs, with_context_dims=True)
        rows = ucv.append_candidates(verdicts, "2026-08-14", **kwargs)

        assert rows, "one bad column must not cost the whole night"
        frame = ucv.load_candidates(tmp_path)
        assert "somenewdim__blob" not in frame.columns
        assert set(frame["stamp_date"]) == {"2026-08-13", "2026-08-14"}

        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "us-context-vector-unclassified-nonscalar" in ln]
        assert lines, "an unclassified column must be announced, not silently dropped"
        # A GitHub annotation is dropped unless it STARTS the line — which is why
        # a `log.warning("::warning ...")` reviews as an alarm and runs blind.
        assert lines[0].startswith("::warning title=us-context-vector-unclassified-nonscalar::")
        assert "somenewdim__blob" in lines[0]

    def test_the_generalized_sweep_leaves_no_float_nan_in_any_object_column(self):
        """The postcondition the runner's pyarrow actually depends on.

        Asserted DIRECTLY rather than through `to_parquet`, because whether a
        NaN-beside-a-struct RAISES is a pyarrow-version property: it raised on the
        2026-08-13 nightly runner (`cannot mix struct and non-struct, non-null
        values`) and writes happily under pandas 3.0.3 / pyarrow 24. An end-to-end
        write test would therefore be GREEN on a developer machine with the defect
        fully intact — a guard that cannot see the failure it names. The invariant
        is version-free: an object column's null is None, never float NaN.

        The named `_OBJECT_COLUMNS`/`_BOOL_COLUMNS` lists cannot supply it — the
        ~120 `<dim>__<field>` columns `context_api.context_frame` flattens in are
        by construction not on any hand-written list, and those are exactly the
        columns a schema-union append fills with NaN.
        """
        frame = pd.DataFrame({
            # named on no dtype list, exactly like every flattened dim column
            "options__gex": [float("nan"), {"spot": 1.0}],
            "spine__records": [float("nan"), [{"signal_id": "x"}]],
            "somenewdim__mixed": pd.Series([float("nan"), {"k": 1}], dtype=object),
            "ticks": [float("nan"), 1.0],                        # numeric: untouched
        })
        out = ucv._coerce_nullable_objects(frame)

        leftovers = [
            f"{column}[{i}]"
            for column in out.columns if out[column].dtype == object
            for i, value in enumerate(out[column])
            if isinstance(value, float) and pd.isna(value)
        ]
        assert not leftovers, (
            "an object column's null must be None — pyarrow cannot unify a float "
            f"NaN with the container in the row below it: {leftovers}")
        for column in ("options__gex", "spine__records", "somenewdim__mixed"):
            assert out[column].iloc[0] is None
        # Numeric columns keep NaN: that IS their null, and coercing them would
        # flip a typed column to object and lose the dtype the contract pins.
        assert pd.isna(out["ticks"].iloc[0]) and out["ticks"].dtype.kind == "f"

    def test_a_reviewed_struct_column_appends_against_a_prior_part_lacking_it(
        self, verdicts, append_kwargs, tmp_path, monkeypatch
    ):
        """`options__gex` is CLASSIFIED, so containment keeps it — a struct column
        must survive the schema union and round-trip, with prior nights null."""
        assert ucv.append_candidates(verdicts, "2026-08-13", **append_kwargs)

        gex = {"spot": 231.4, "net_gex_bn": 3.2, "gamma_regime": "long",
               "gamma_flip": 228.0, "as_of": "2026-08-14"}
        _dim_frame(monkeypatch, {"options__gex": gex})
        kwargs = dict(append_kwargs, with_context_dims=True)
        assert ucv.append_candidates(verdicts, "2026-08-14", **kwargs)

        frame = ucv.load_candidates(tmp_path)
        assert "options__gex" in frame.columns
        night2 = frame[frame["stamp_date"] == "2026-08-14"]
        assert dict(night2["options__gex"].iloc[0])["gamma_regime"] == "long"
        night1 = frame[frame["stamp_date"] == "2026-08-13"]
        assert night1["options__gex"].isna().all(), "prior nights self-heal to null"

    def test_a_forbidden_payload_column_is_dropped_without_an_alarm(
        self, verdicts, append_kwargs, tmp_path, capsys, monkeypatch
    ):
        """Forbidden is CLASSIFIED — it is dropped at the committing seam already,
        so a second drop here is a fence, not news."""
        _dim_frame(monkeypatch, {"forensics__findings": [{"title": "PAID"}]})
        kwargs = dict(append_kwargs, with_context_dims=True)
        assert ucv.append_candidates(verdicts, "2026-08-14", **kwargs)

        frame = ucv.load_candidates(tmp_path)
        assert "forensics__findings" not in frame.columns
        assert "PAID" not in frame.to_json()
        assert "unclassified-nonscalar" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 4. loud failure — MUTATION RECEIPT
# --------------------------------------------------------------------------- #

class TestFailureIsAnnounced:

    def test_a_failed_write_prints_a_line_start_warning_and_returns_zero(
        self, verdicts, append_kwargs, capsys, monkeypatch
    ):
        """MUTATION-VERIFIED 2026-08-14: deleting the `print(...)` in
        `append_candidates`'s except block turns this red (`assert []`), and
        weakening it to `log.warning` turns it red too — a logger prefixes the
        line, so the annotation never starts it and GitHub drops it. That is the
        exact mechanism by which six dead nights read as a green engine job."""
        def _boom(*args, **kwargs):
            raise ValueError("cannot mix struct and non-struct, non-null values")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", _boom)
        rows = ucv.append_candidates(verdicts, "2026-08-14", **append_kwargs)

        assert rows == 0, "a failed append must report 0, never a phantom count"
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "us-context-vector-append-failed" in ln]
        assert lines, "a dead stamp must be announced in the Actions summary"
        assert lines[0].startswith("::warning title=us-context-vector-append-failed::")
        assert "cannot mix struct and non-struct" in lines[0]
        assert "did not advance tonight" in lines[0]

    def test_a_night_that_adds_no_rows_is_announced(
        self, verdicts, append_kwargs, capsys
    ):
        """Keep-first makes a rerun legitimately quiet — and a broken assembly
        looks exactly the same from outside. Say it either way."""
        assert ucv.append_candidates(verdicts, "2026-08-14", **append_kwargs)
        capsys.readouterr()
        assert ucv.append_candidates(verdicts, "2026-08-14", **append_kwargs)

        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "us-context-vector-quiet" in ln]
        assert lines and lines[0].startswith("::warning title=us-context-vector-quiet::")

    def test_a_first_stamp_of_the_night_is_not_announced_as_quiet(
        self, verdicts, append_kwargs, capsys
    ):
        assert ucv.append_candidates(verdicts, "2026-08-14", **append_kwargs)
        assert "us-context-vector-quiet" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 5. the buy-lane reconciliation receipt (masterplan §13.7)
# --------------------------------------------------------------------------- #

class TestBuyLaneReconciliation:

    def test_a_kept_first_row_that_contradicts_the_board_is_reported(
        self, verdicts, append_kwargs, capsys
    ):
        """Non-vacuous by construction: the receipt re-reads the PART, so it can
        see keep-first refusing tonight's lane. A receipt computed from the frame
        it is checking could only ever restate the assignment that built it."""
        assert ucv.append_candidates(
            verdicts, "2026-08-14", lane_by_ticker={}, **append_kwargs)
        capsys.readouterr()
        # Same night, same key — keep-first keeps the `not_on_board` rows, so the
        # store now disagrees with a board that calls AAA a buy.
        ucv.append_candidates(
            verdicts, "2026-08-14", lane_by_ticker={"AAA": "buy"}, **append_kwargs)

        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "us-context-vector-board-mismatch" in ln]
        assert lines, "a store/board buy-lane disagreement must be printed"
        assert lines[0].startswith("::warning title=us-context-vector-board-mismatch::")
        assert "AAA" in lines[0]

    def test_an_agreeing_night_is_silent(self, verdicts, append_kwargs, capsys):
        ucv.append_candidates(
            verdicts, "2026-08-14", lane_by_ticker={"AAA": "buy"}, **append_kwargs)
        assert "board-mismatch" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 6. the upstream liveness tripwire (masterplan §13.0)
# --------------------------------------------------------------------------- #

class TestStalenessTripwire:
    """The grader lane already reads this store nightly, which makes it the
    cheapest place in the pipeline to notice that it has stopped moving."""

    @staticmethod
    def _script(monkeypatch, stamps):
        import scripts.grade_us_prophet_candidates as cli

        monkeypatch.setattr(
            "engine.us_context_vector.load_candidates",
            lambda *a, **k: pd.DataFrame({"stamp_date": stamps}))
        return cli

    def test_a_six_night_gap_is_announced(self, monkeypatch, capsys):
        """The measured outage: newest stamp 2026-08-07, grader as-of 08-13."""
        cli = self._script(monkeypatch, ["2026-08-06", "2026-08-07"])
        cli._warn_if_candidates_store_is_stale("2026-08-13")

        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "us-context-vector-stale" in ln]
        assert lines and lines[0].startswith("::warning title=us-context-vector-stale::")
        assert "2026-08-07" in lines[0] and "2026-08-13" in lines[0]

    def test_a_healthy_lag_is_silent(self, monkeypatch, capsys):
        """The board stamps the settled prior close, so one or two sessions of
        lag is a normal night, not an incident."""
        cli = self._script(monkeypatch, ["2026-08-12", "2026-08-13"])
        cli._warn_if_candidates_store_is_stale("2026-08-14")
        assert "us-context-vector-stale" not in capsys.readouterr().out

    def test_an_empty_store_is_announced_rather_than_read_as_fresh(
        self, monkeypatch, capsys
    ):
        import scripts.grade_us_prophet_candidates as cli

        monkeypatch.setattr("engine.us_context_vector.load_candidates",
                            lambda *a, **k: pd.DataFrame())
        cli._warn_if_candidates_store_is_stale("2026-08-14")
        assert "::warning title=us-context-vector-stale::" in capsys.readouterr().out

    def test_the_tripwire_never_raises(self, monkeypatch, capsys):
        """Zero authority means zero ability to break the grader."""
        import scripts.grade_us_prophet_candidates as cli

        def _boom(*a, **k):
            raise RuntimeError("store on fire")

        monkeypatch.setattr("engine.us_context_vector.load_candidates", _boom)
        cli._warn_if_candidates_store_is_stale("2026-08-14")   # must not raise
        cli._warn_if_candidates_store_is_stale(None)
