"""W7 — the unwired seasonality research-browser API surface.

Two tests here are the reason the file exists:

* ``test_pagination_at_an_exact_multiple`` — trailing-page bugs live exactly at
  the boundary where ``total % page_size == 0``.  An off-by-one there produces a
  final page that repeats the previous page's tail (double-counted rows) or an
  empty page reported as more results.  The test walks every page of a 20-row
  set at size 10 and asserts the concatenation equals the full ordered set with
  no repeats.
* ``test_partial_without_a_reason_is_a_server_error`` — a short list that says
  nothing is silent truncation, which reads to a user as "there are no more
  rows".  The handler refuses to serve it.

Everything else pins the envelope: model and data versions, source entitlements,
``no-store`` on private data, and one shared result payload for the API and the
server-rendered view so the two cannot drift.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import seasonality as api  # noqa: E402
from engine.seasonality import screener  # noqa: E402

ASOF = date(2026, 8, 6)


def _multiplicity() -> dict:
    return screener.program_multiplicity(
        symbols_searched=180,
        windows_per_symbol=2645,
        family_id="calendar_windows_v1",
        correction="joint_max_t_westfall_young",
    )


def _row(symbol: str, *, up_years: int = 15, n_years: int = 23) -> screener.ResearchRow:
    return screener.descriptive_row(
        row_id=f"{symbol}:40-70",
        symbol=symbol,
        window_start_doy=40,
        window_end_doy=70,
        up_years=up_years,
        n_years=n_years,
        baseline_up_share=0.52,
        issuer_count=1,
        date_cluster_count=n_years,
        search_family="calendar_windows_v1",
        family_size=2645,
        multiplicity=_multiplicity(),
        family_adjusted_p_value=0.2,
        evidence_label="descriptive_only_no_forward_record",
        costs=screener.costs_disclosure(
            round_trip_cost_bps=18.0,
            borrow_cost_included=False,
            slippage_model="static_bps_assumption",
            applied_to_estimate=False,
        ),
        freshness=screener.freshness_disclosure(artifact_asof=date(2026, 8, 5), asof=ASOF),
    )


def _rows(count: int) -> list[screener.ResearchRow]:
    # Deliberately identical up-shares for half the set so the tiebreaker, not
    # the sort column, is what makes the order total.
    return [
        _row(f"SYM{index:03d}", up_years=15 if index % 2 else 16)
        for index in range(count)
    ]


def _provider(rows, provenance=None):
    def provide(asof):
        return list(rows), dict(provenance or {})

    return provide


def _call(**overrides):
    kwargs = dict(
        asof=ASOF,
        consumer="api_research_browser",
        rows_provider=_provider(_rows(20)),
        universe=screener.resolve_universe(ASOF),
        multiplicity=_multiplicity(),
    )
    kwargs.update(overrides)
    return api.research_browser_handler(**kwargs)


def _view(**overrides):
    kwargs = dict(
        asof=ASOF,
        consumer="api_research_browser",
        rows_provider=_provider(_rows(20)),
        universe=screener.resolve_universe(ASOF),
        multiplicity=_multiplicity(),
    )
    kwargs.update(overrides)
    return api.research_browser_view(**kwargs)


#: One kwargs recipe per reachable status class. Every envelope assertion is
#: parametrized over this so a law claimed for "every response" is tested on
#: every response rather than on the happy path plus one 400.
_STATUS_CASES = {
    "200_ok": (200, {}),
    "400_asof_missing": (400, {"asof": None}),
    "400_page_size": (400, {"page_size": 10_000}),
    "400_sort_by": (400, {"sort_by": "edge_score"}),
    "403_machine_consumer": (403, {"consumer": "prophet_board_score_consumer"}),
    "429_rate_limited": (429, {"rate_limit_hook": lambda binding: {"allowed": False}}),
    "500_partial_without_reason": (500, {"rows_provider": _provider(_rows(4), {"partial": True})}),
}


# --- the envelope -----------------------------------------------------------


class TestEnvelope:
    def test_success_carries_versions_and_entitlements(self):
        response = _call()
        assert response.status == 200
        assert response.body["model_version"] == api.MODEL_VERSION
        assert response.body["data_versions"]["result_set"] == screener.RESEARCH_BROWSER_SCHEMA
        assert response.body["source_entitlements"]
        for entry in response.body["source_entitlements"]:
            assert {"source", "entitlement", "redistribution"} <= set(entry)

    def test_errors_carry_the_same_envelope(self):
        response = _call(asof=None)
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_ASOF_REQUIRED
        assert response.body["model_version"] == api.MODEL_VERSION
        assert response.body["source_entitlements"]
        assert response.body["is_calibrated_screener"] is False

    def test_every_response_declares_the_research_tier(self):
        for response in (_call(), _call(asof=None), _call(page_size=10_000)):
            assert response.body["tier"] == "research"
            assert response.body["is_calibrated_screener"] is False
            assert "not a calibrated screener" in response.body["not_calibrated_reason"]

    # The envelope law used to be pinned on ONE status code: 200 and two 400s.
    # Three separate mutations that dropped `source_entitlements`, or stamped
    # `tier="production"` / `is_calibrated_screener=True`, on every non-400 path
    # shipped green, so the API could claim production tier on every 403/429/500
    # with nothing noticing. Every reachable status is checked here.
    @pytest.mark.parametrize("case", sorted(_STATUS_CASES))
    def test_envelope_rides_on_every_reachable_status(self, case):
        expected_status, kwargs = _STATUS_CASES[case]
        response = _call(**kwargs)
        assert response.status == expected_status, case
        body = response.body
        assert body["schema"] == api.API_SCHEMA
        assert body["tier"] == "research"
        assert body["is_calibrated_screener"] is False
        assert "not a calibrated screener" in body["not_calibrated_reason"]
        assert body["model_version"] == api.MODEL_VERSION
        assert body["data_versions"]["result_set"] == screener.RESEARCH_BROWSER_SCHEMA
        assert body["source_entitlements"]
        for entry in body["source_entitlements"]:
            assert {"source", "entitlement", "redistribution"} <= set(entry)

    @pytest.mark.parametrize("case", sorted(_STATUS_CASES))
    def test_every_refusal_names_a_stable_error_code(self, case):
        expected_status, kwargs = _STATUS_CASES[case]
        response = _call(**kwargs)
        if expected_status == 200:
            assert response.body["error"] is None
            return
        assert response.body["error"]["code"]
        assert response.body["result"] is None

    def test_private_data_is_no_store(self):
        response = _call()
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Vary"] == "Authorization"

    def test_public_mode_is_opt_in(self):
        response = _call(private=False)
        assert "no-store" not in response.headers["Cache-Control"]

    def test_public_mode_still_varies_on_authorization(self):
        # Without `Vary` a shared cache keys a licensed, per-consumer body on the
        # URL alone and hands one caller's response — its `consumer` identity and
        # its `not_redistributable` entitlement block included — to everyone else.
        response = _call(private=False)
        assert response.headers["Vary"] == "Authorization"

    @pytest.mark.parametrize("case", sorted(_STATUS_CASES))
    def test_a_refusal_is_never_shared_cacheable(self, case):
        expected_status, kwargs = _STATUS_CASES[case]
        response = _call(private=False, **kwargs)
        if expected_status == 200:
            return
        assert response.headers["Cache-Control"] == "no-store", case


class TestAsofIsExplicit:
    def test_missing_asof_is_refused(self):
        response = _call(asof=None)
        assert response.status == 400
        assert "reproducible" in response.body["error"]["message"]

    def test_iso_string_asof_is_accepted(self):
        response = _call(asof="2026-08-06")
        assert response.status == 200
        assert response.body["result"]["asof"] == "2026-08-06"

    def test_unparseable_asof_is_refused(self):
        response = _call(asof="last tuesday")
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_ASOF_INVALID

    @pytest.mark.parametrize(
        "value",
        [datetime(2026, 8, 6, 13, 45), datetime(2026, 8, 6, 13, 45, tzinfo=timezone.utc)],
    )
    def test_datetime_asof_is_refused_like_a_timestamped_string(self, value):
        # `datetime` subclasses `date`, so an isinstance check passed it straight
        # through and `asof` serialised WITH a time: two requests for the same
        # trading day produced different reproducibility keys and different
        # rate-limit keys. An ISO string carrying a time already 400s.
        response = _call(asof=value)
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_ASOF_INVALID
        assert _call(asof="2026-08-06T13:45:00").status == 400

    @pytest.mark.parametrize(
        "value", [date(2099, 1, 1), date(1, 1, 1), date(1970, 1, 1), "2099-01-01"]
    )
    def test_asof_is_bounded_at_both_ends(self, value):
        response = _call(asof=value)
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_ASOF_OUT_OF_RANGE
        assert response.body["error"]["min_asof"] == api.MIN_ASOF.isoformat()


class TestHandlerParameterHandling:
    def test_a_missing_asof_kwarg_is_a_400_not_a_traceback(self):
        # The natural wiring splats a query dict. A MISSING `asof` used to raise
        # `TypeError: missing 1 required keyword-only argument`, so the stable
        # ERR_ASOF_REQUIRED code was reachable only by passing `asof=None`.
        response = api.research_browser_handler(
            consumer="api_research_browser",
            rows_provider=_provider(_rows(4)),
            universe=screener.resolve_universe(ASOF),
            multiplicity=_multiplicity(),
        )
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_ASOF_REQUIRED

    @pytest.mark.parametrize("name", ["foo", "limit", "offset", "top_n"])
    def test_an_unrecognised_parameter_is_a_400_not_a_traceback(self, name):
        response = _call(**{name: 1})
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_UNKNOWN_PARAMETER
        assert name in response.body["error"]["unknown_parameters"]

    def test_a_missing_required_dependency_is_a_400_not_a_traceback(self):
        response = api.research_browser_handler(asof=ASOF, consumer="api_research_browser")
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_UNKNOWN_PARAMETER
        assert "rows_provider" in response.body["error"]["missing_parameters"]


class TestRowsProviderContract:
    """The provider is the one dependency this module does not own."""

    def test_a_provider_outage_is_a_stated_500_not_a_traceback(self):
        def explode(asof):
            raise OSError("store gone")

        response = _call(rows_provider=explode)
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_ROWS_PROVIDER_FAILED
        assert "OSError" in response.body["error"]["message"]
        assert response.body["tier"] == "research"

    @pytest.mark.parametrize(
        "returns",
        [
            lambda asof: (list(_rows(2)),),
            lambda asof: (list(_rows(2)), {}, "extra"),
            lambda asof: (list(_rows(2)), "stale"),
            lambda asof: (list(_rows(2)), [1, 2]),
            lambda asof: (7, {}),
            lambda asof: ([{"symbol": "AAAA"}], {}),
            lambda asof: {"rows": []},
            lambda asof: None,
        ],
    )
    def test_a_broken_provider_shape_is_a_stated_500(self, returns):
        response = _call(rows_provider=returns)
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_ROWS_PROVIDER_CONTRACT
        assert response.body["source_entitlements"]


# --- deterministic pagination -----------------------------------------------


class TestPagination:
    def test_pagination_at_an_exact_multiple(self):
        rows = _rows(20)
        full = _call(rows_provider=_provider(rows), page_size=20).body["result"]["rows"]
        assert len(full) == 20

        seen = []
        for page in (1, 2):
            response = _call(rows_provider=_provider(rows), page=page, page_size=10)
            body = response.body["result"]
            assert len(body["rows"]) == 10
            assert body["pagination"]["total_rows"] == 20
            assert body["pagination"]["total_pages"] == 2
            seen.extend(row["row_id"] for row in body["rows"])

        assert seen == [row["row_id"] for row in full]
        assert len(set(seen)) == 20  # no page repeated a row, none was skipped

    def test_last_page_of_an_exact_multiple_closes_the_set(self):
        response = _call(page=2, page_size=10)
        pagination = response.body["result"]["pagination"]
        assert pagination["has_more"] is False
        assert pagination["next_page"] is None
        assert pagination["page_out_of_range"] is False

    def test_a_page_past_the_end_says_so_instead_of_repeating(self):
        response = _call(page=3, page_size=10)
        body = response.body["result"]
        assert body["rows"] == []
        assert body["pagination"]["page_out_of_range"] is True
        assert body["pagination"]["has_more"] is False

    def test_ragged_last_page(self):
        rows = _rows(21)
        response = _call(rows_provider=_provider(rows), page=3, page_size=10)
        pagination = response.body["result"]["pagination"]
        assert len(response.body["result"]["rows"]) == 1
        assert pagination["total_pages"] == 3
        assert pagination["has_more"] is False

    def test_order_is_stable_across_calls_with_a_shuffled_provider(self):
        rows = _rows(20)
        first = _call(rows_provider=_provider(rows), page=2, page_size=10).body["result"]["rows"]
        second = _call(rows_provider=_provider(list(reversed(rows))), page=2, page_size=10).body["result"]["rows"]
        assert [row["row_id"] for row in first] == [row["row_id"] for row in second]

    def test_sorted_pagination_is_still_a_partition(self):
        rows = _rows(20)
        seen = []
        for page in (1, 2):
            body = _call(
                rows_provider=_provider(rows), page=page, page_size=10, sort_by="historical_up_share",
                descending=True,
            ).body["result"]
            seen.extend(row["row_id"] for row in body["rows"])
        assert len(set(seen)) == 20

    def test_page_size_is_bounded_and_refused_not_clamped(self):
        response = _call(page_size=api.MAX_PAGE_SIZE + 1)
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_PAGE_SIZE_EXCEEDS_MAX
        assert response.body["error"]["max_page_size"] == api.MAX_PAGE_SIZE

    @pytest.mark.parametrize("bad", [0, -1, "10", 1.5, True])
    def test_bad_page_and_page_size_are_refused(self, bad):
        assert _call(page=bad).status == 400
        assert _call(page_size=bad).status == 400

    def test_out_of_range_answers_one_condition_one_way(self):
        # Page 5 of an EMPTY set is as far past the end as page 3 of a 20-row set;
        # keying the flag on `total > 0` answered the same client condition two
        # different ways. Page 1 is never out of range — an empty first page is an
        # empty set, not an overshoot.
        empty = _call(rows_provider=_provider([]), page=5, page_size=10).body["result"]
        assert empty["pagination"]["page_out_of_range"] is True
        assert empty["rows"] == []
        first = _call(rows_provider=_provider([]), page=1, page_size=10).body["result"]
        assert first["pagination"]["page_out_of_range"] is False
        assert _call(page=3, page_size=10).body["result"]["pagination"]["page_out_of_range"] is True

    def test_counts_are_set_scoped_and_the_page_count_is_named(self):
        # `counts.rows` is the whole ordered set while `rows` is one page: a UI
        # rendering "N of counts.rows" from the page it holds needs both numbers
        # and the label that says which is which.
        body = _call(rows_provider=_provider(_rows(20)), page=1, page_size=5).body["result"]
        assert body["counts"]["scope"] == "result_set_not_page"
        assert body["counts"]["rows"] == 20
        assert body["counts"]["rows_on_page"] == 5
        assert len(body["rows"]) == body["counts"]["rows_on_page"]
        assert body["pagination"]["total_rows"] == body["counts"]["rows"]

        past_end = _call(rows_provider=_provider(_rows(20)), page=9, page_size=5).body["result"]
        assert past_end["counts"]["rows"] == 20
        assert past_end["counts"]["rows_on_page"] == 0


# --- stale / partial --------------------------------------------------------


class TestStaleAndPartialAreExplicit:
    def test_fresh_complete_answer_still_states_both(self):
        body = _call(
            rows_provider=_provider(_rows(4), {"stale": False, "artifact_asof": "2026-08-05"})
        ).body["result"]
        assert body["freshness"]["stale"] is False
        assert body["freshness"]["known"] is True
        assert body["completeness"]["partial"] is False

    def test_unknown_freshness_is_printed_as_unknown_not_as_fresh(self):
        # `stale: False` next to `artifact_asof: None` was an affirmative
        # freshness claim assembled out of an absence of information: a provider
        # that says nothing is indistinguishable from one that says "fresh".
        body = _call(rows_provider=_provider(_rows(4), {})).body["result"]
        assert body["freshness"]["stale"] is None
        assert body["freshness"]["known"] is False
        assert body["freshness"]["stale_reason"] == api.UNKNOWN_FRESHNESS_REASON

    def test_stale_state_is_a_field(self):
        body = _call(
            rows_provider=_provider(
                _rows(4), {"stale": True, "stale_reason": "artifact older than 7d", "artifact_asof": "2026-07-20"}
            )
        ).body["result"]
        assert body["freshness"]["stale"] is True
        assert body["freshness"]["stale_reason"]

    def test_partial_state_names_what_is_missing(self):
        body = _call(
            rows_provider=_provider(
                _rows(4),
                {
                    "partial": True,
                    "partial_reason": "3 symbols had no complete-year panel",
                    "omitted_row_count": 3,
                    "omitted_symbols": ["AAAA", "BBBB", "CCCC"],
                },
            )
        ).body["result"]
        assert body["completeness"]["partial"] is True
        assert body["completeness"]["omitted_row_count"] == 3
        assert body["completeness"]["omitted_symbols"] == ["AAAA", "BBBB", "CCCC"]

    def test_partial_without_a_reason_is_a_server_error(self):
        response = _call(rows_provider=_provider(_rows(4), {"partial": True}))
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_PARTIAL_WITHOUT_REASON
        assert response.body["result"] is None


# --- refusals travel through the API ----------------------------------------


class TestRefusals:
    def test_machine_authority_consumer_is_refused_with_403(self):
        response = _call(consumer="prophet_board_score_consumer")
        assert response.status == 403
        assert response.body["error"]["code"] == api.ERR_CONSUMER_REFUSED
        assert "prophet_board_score_consumer" in response.body["error"]["message"]
        assert screener.MACHINE_AUTHORITY_REFUSAL in response.body["error"]["message"]

    def test_unknown_consumer_is_refused(self):
        assert _call(consumer="mystery_service").status == 403

    def test_non_allowlisted_sort_by_is_refused_with_the_allowlist(self):
        response = _call(sort_by="edge_score")
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_SORT_BY_NOT_ALLOWED
        assert response.body["error"]["sortable_columns"] == list(screener.SORTABLE_COLUMNS)

    def test_mixed_estimate_axis_is_refused(self):
        calibrated = screener.build_row(
            row_id="WXYZ:calibrated",
            symbol="WXYZ",
            window_start_doy=40,
            window_end_doy=70,
            estimate_type=screener.ESTIMATE_CALIBRATED,
            calibrated_probability=0.61,
            calibrated_probability_baseline=0.5,
            calibrated_probability_edge=0.11,
            calibration_reference="oos_epoch:2027h1_walk_forward",
            uncertainty_semantics="predictive_interval",
            uncertainty_low=0.44,
            uncertainty_high=0.78,
            uncertainty_level=0.9,
            sample_size=140,
            issuer_count=1,
            date_cluster_count=140,
            search_family="calendar_windows_v1",
            family_size=2645,
            multiplicity=_multiplicity(),
            family_adjusted_p_value=0.02,
            evidence_label="graded_out_of_sample",
            costs=screener.costs_disclosure(
                round_trip_cost_bps=18.0,
                borrow_cost_included=False,
                slippage_model="static_bps_assumption",
                applied_to_estimate=False,
            ),
            oos_epoch="2027h1_walk_forward",
            freshness=screener.freshness_disclosure(artifact_asof=date(2026, 8, 5), asof=ASOF),
            extrapolation=False,
        )
        response = _call(
            rows_provider=_provider([_row("AAAA"), calibrated]), sort_by="historical_up_share"
        )
        assert response.status == 400
        assert response.body["error"]["code"] == api.ERR_MIXED_ESTIMATE_AXIS

    @pytest.mark.parametrize(
        "overrides",
        [
            {"universe": None},
            {"universe": {"basis": "point_in_time"}},
            {"universe": screener.resolve_universe(date(2020, 1, 1))},
            {"multiplicity": None},
            {"multiplicity": {"scope": "program_level"}},
            {
                "multiplicity": screener.program_multiplicity(
                    symbols_searched=2,
                    windows_per_symbol=2645,
                    family_id="calendar_windows_v1",
                    correction="joint_max_t_westfall_young",
                )
            },
        ],
    )
    def test_a_bare_screener_refusal_is_a_stated_500_not_a_traceback(self, overrides):
        # `build_result_set` and ~a dozen `ResearchRow` invariants raise the BASE
        # `ScreenerError`, which the handler did not catch: a bad universe object
        # or a forged multiplicity block produced an uncaught traceback with no
        # envelope, defeating the "every response declares the tier" property.
        response = _call(**overrides)
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_RESULT_SET_REFUSED
        assert response.body["tier"] == "research"
        assert response.body["is_calibrated_screener"] is False
        assert response.body["source_entitlements"]
        assert response.body["result"] is None

    def test_a_calibrated_row_reaching_this_artifact_is_a_stated_500(self):
        calibrated = screener.build_row(
            row_id="WXYZ:calibrated",
            symbol="WXYZ",
            window_start_doy=40,
            window_end_doy=70,
            estimate_type=screener.ESTIMATE_CALIBRATED,
            calibrated_probability=0.61,
            calibrated_probability_baseline=0.5,
            calibrated_probability_edge=0.11,
            calibration_reference="oos_epoch:2027h1_walk_forward",
            uncertainty_semantics="predictive_interval",
            uncertainty_low=0.44,
            uncertainty_high=0.78,
            uncertainty_level=0.9,
            sample_size=140,
            issuer_count=1,
            date_cluster_count=140,
            search_family="calendar_windows_v1",
            family_size=2645,
            multiplicity=_multiplicity(),
            family_adjusted_p_value=0.02,
            evidence_label="graded_out_of_sample",
            costs=screener.costs_disclosure(
                round_trip_cost_bps=18.0,
                borrow_cost_included=False,
                slippage_model="static_bps_assumption",
                applied_to_estimate=False,
            ),
            oos_epoch="2027h1_walk_forward",
            freshness=screener.freshness_disclosure(artifact_asof=date(2026, 8, 5), asof=ASOF),
            extrapolation=False,
        )
        response = _call(rows_provider=_provider([calibrated]))
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_RESULT_SET_REFUSED
        assert "may not carry calibrated rows" in response.body["error"]["message"]

    def test_duplicate_rows_fail_rather_than_paginate_unstably(self):
        row = _row("AAAA")
        response = _call(rows_provider=_provider([row, row]))
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_ROWS_NOT_TOTALLY_ORDERED


class TestRateLimitHook:
    def test_hook_is_a_parameter_not_a_live_limiter(self):
        seen = []

        def hook(binding):
            seen.append(dict(binding))
            return {"allowed": True}

        response = _call(rate_limit_hook=hook)
        assert response.status == 200
        assert seen[0]["consumer"] == "api_research_browser"
        assert seen[0]["asof"] == "2026-08-06"

    def test_denied_request_returns_429_with_retry_after(self):
        response = _call(rate_limit_hook=lambda binding: {"allowed": False, "retry_after_s": 30})
        assert response.status == 429
        assert response.headers["Retry-After"] == "30"
        assert response.body["error"]["code"] == api.ERR_RATE_LIMITED

    def test_no_hook_means_no_limiting(self):
        assert _call(rate_limit_hook=None).status == 200

    @pytest.mark.parametrize("verdict", ["denied", ["denied"], True, 1, object(), b"no"])
    def test_a_truthy_non_mapping_verdict_is_refused_not_crashed(self, verdict):
        # The guard detected a non-Mapping and the very next line called `.get`
        # on that same object, so the exact input the check existed for was the
        # one that produced an uncaught AttributeError.
        response = _call(rate_limit_hook=lambda binding: verdict)
        assert response.status == 429
        assert response.body["error"]["code"] == api.ERR_RATE_LIMITED
        assert response.headers["Retry-After"] == str(api.DEFAULT_RETRY_AFTER_S)

    def test_a_hook_that_raises_fails_closed_with_an_envelope(self):
        def broken(binding):
            raise RuntimeError("limiter down")

        response = _call(rate_limit_hook=broken)
        assert response.status == 500
        assert response.body["error"]["code"] == api.ERR_RATE_LIMIT_HOOK_FAILED
        assert response.body["tier"] == "research"
        assert response.body["source_entitlements"]

    @pytest.mark.parametrize(
        "retry_after_s, expected",
        [
            (-5, api.DEFAULT_RETRY_AFTER_S),
            (0, api.DEFAULT_RETRY_AFTER_S),
            ("soon", api.DEFAULT_RETRY_AFTER_S),
            (None, api.DEFAULT_RETRY_AFTER_S),
            (10**30, api.MAX_RETRY_AFTER_S),
            (30, 30),
        ],
    )
    def test_retry_after_is_always_a_legal_delta_seconds(self, retry_after_s, expected):
        # RFC 9110 delta-seconds is a non-negative integer; `-5` and `1e30` are
        # rejected or ignored by clients and proxies.
        response = _call(
            rate_limit_hook=lambda binding: {"allowed": False, "retry_after_s": retry_after_s}
        )
        assert response.status == 429
        assert response.headers["Retry-After"] == str(expected)
        assert 1 <= int(response.headers["Retry-After"]) <= api.MAX_RETRY_AFTER_S


# --- one schema, two surfaces -----------------------------------------------


class TestServerAndUiParity:
    def test_view_and_api_return_the_identical_result(self):
        kwargs = dict(
            asof=ASOF,
            consumer="human_research_browser",
            rows_provider=_provider(_rows(20)),
            universe=screener.resolve_universe(ASOF),
            multiplicity=_multiplicity(),
            page=2,
            page_size=10,
            sort_by="symbol",
        )
        response = api.research_browser_handler(**kwargs)
        view = api.research_browser_view(**kwargs)
        assert view.status == response.status
        assert view.result == response.body["result"]
        assert view.headers["Cache-Control"] == "no-store"

    @pytest.mark.parametrize("case", sorted(_STATUS_CASES))
    def test_the_view_carries_the_whole_envelope_on_every_status(self, case):
        # The view used to return `result` alone, so on any refusal it handed the
        # renderer `None` with no error code — and, because the tier declaration
        # lives in the envelope rather than inside `result`, no tier disclosure
        # either. 400/403/429/500 were indistinguishable to the UI.
        expected_status, kwargs = _STATUS_CASES[case]
        response = _call(**kwargs)
        view = _view(**kwargs)
        assert view.status == expected_status
        assert view.result == response.body["result"]
        assert view.error == response.body["error"]
        assert view.envelope["tier"] == "research"
        assert view.envelope["is_calibrated_screener"] is False
        assert view.envelope["model_version"] == api.MODEL_VERSION
        assert view.envelope["source_entitlements"]
        if expected_status != 200:
            assert view.result is None
            assert view.error["code"]

    def test_the_view_and_the_api_agree_field_for_field_on_a_refusal(self):
        kwargs = {"consumer": "prophet_overlay"}
        response = _call(**kwargs)
        view = _view(**kwargs)
        rebuilt = {**view.envelope, "result": view.result, "error": view.error}
        assert rebuilt == response.body

    def test_declared_schema_matches_what_is_served(self):
        schema = api.result_schema()
        body = _call().body["result"]
        assert schema["result_set_schema"] == body["schema"]
        assert schema["row_schema"] == body["rows"][0]["schema"]
        assert schema["sortable_columns"] == body["ordering"]["sortable_columns"]
        assert schema["max_page_size"] == body["pagination"]["max_page_size"]
        assert schema["is_calibrated_screener"] is False
        assert schema["uncertainty_semantics"] == list(screener.UNCERTAINTY_SEMANTICS)

    def test_universe_disclosure_reaches_the_payload(self):
        body = _call().body["result"]
        assert body["universe"]["point_in_time_available"] is False
        assert body["universe"]["survivorship_biased"] is True
        assert "current-vintage, survivorship-biased" in body["universe"]["note"]

    def test_program_multiplicity_reaches_the_payload(self):
        body = _call().body["result"]
        assert body["multiplicity"]["scope"] == "program_level"
        assert body["multiplicity"]["hypotheses_total"] == 180 * 2645
