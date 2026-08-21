"""Contract tests for the paid Catalyst Radar API (BioCatalyst P1-1).

``GET /api/biocatalyst/v1/catalyst-radar`` is the serving plane over the
frozen, pure projection in ``engine.biocatalyst.catalyst_events``.  These
tests exercise the route's own responsibilities only: authentication,
entitlement, query validation, generation-anchored pagination, the
sponsor-map serve-time hazard (must degrade, never 503), and the public
safety boundary (no score/rank vocabulary, no private path/receipt/object-key
leakage).  The projection's own semantics -- timing classification,
precision honesty, evidence shape -- are frozen and unit-tested in
``tests/test_biocatalyst_catalyst_radar.py``; this file does not re-test them.

Harness modeled on ``tests/test_biocatalyst_api.py``'s ``promoted_config`` /
``entitled_client`` fixtures (a genuine B2 generation published through the
worker's normal seam) and its ``_milestone_snapshot`` / ``_milestone_projection``
/ ``_milestone_operational`` fixtures (a monkeypatched ``_read_bundle`` for
scenario control), reused here rather than re-implemented.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

import pytest

pytest.importorskip("fastapi", reason="BioCatalyst API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.biocatalyst as biocatalyst_api  # noqa: E402
from engine.biocatalyst.catalyst_events import (  # noqa: E402
    RADAR_EVENT_KINDS,
    RADAR_HORIZONS,
    project_trial_milestones,
)
from tests.test_biocatalyst_api import (  # noqa: E402
    _assert_private_headers,
    _milestone_operational,
    _milestone_projection,
    _milestone_snapshot,
    _walk_keys,
    entitled_client,  # noqa: F401  (fixture)
    promoted_config,  # noqa: F401  (fixture)
)

# Mirrors test_biocatalyst_api.py's own evidence-safety fragment list -- the
# private-shaped keys this public route must never expose regardless of what
# the underlying worker state carries.
_FORBIDDEN_KEY_FRAGMENTS = (
    "canonical_study",
    "canonical_content",
    "source_snapshot",
    "source_record_ref",
    "raw_object",
    "receipt",
    "object_key",
    "source_json_path",
    "manifest_sha",
    "generation_id",
    "snapshot_id",
    "query_sha",
)
_FORBIDDEN_VALUE_PATTERN = re.compile(r"score|probability|materiality|rank|composite|confidence|weight", re.IGNORECASE)
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/[A-Za-z0-9_.\-]+){2,}$")
_R2_OBJECT_KEY_PATTERN = re.compile(r"^biocatalyst/[a-z_]+/")
_HEX_HASH_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def _walk_values(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    else:
        yield value


# ---------------------------------------------------------------------------
# 1-3: envelope shape, authority, headers -- against a REAL published cut.
# ---------------------------------------------------------------------------


def test_catalyst_radar_returns_expected_envelope_against_a_real_published_generation(
    entitled_client,
) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    for key in (
        "schema_version",
        "as_of",
        "source",
        "health",
        "coverage",
        "authority",
        "query",
        "effective_horizon",
        "pagination",
        "catalyst_radar",
    ):
        assert key in payload, key
    assert payload["authority"]["decision_authority"] is False

    # Nonzero rows against the real single-trial worker fixture generation
    # (NCT00000001, primary_completion 2026-12 ESTIMATED, no sponsor on file,
    # RECRUITING, no revision history collected on this seam).
    rows = payload["catalyst_radar"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["nct_id"] == "NCT00000001"
    assert row["kind"] == "primary_completion"
    assert row["milestone"]["date"] == "2026-12"
    assert row["timing"]["state"] == "upcoming"
    assert row["trial_status"] == {"value": "RECRUITING", "activity": "active", "reason_code": None}
    assert row["issuer"]["state"] == "sponsor_name_absent"
    assert row["revision"] == {"state": "history_not_collected", "count": 0, "latest": None}
    assert payload["pagination"]["total"] == 1
    assert payload["coverage"]["radar"]["trials_in_cohort"] == 1
    # _meta's own generation coverage block must survive being merged with the
    # radar denominators, not be clobbered by them.
    assert payload["coverage"]["class"] == "current_only"
    assert "configured" in payload["coverage"] and "observed" in payload["coverage"]


def test_catalyst_radar_authority_block_never_grants_decision_authority(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    authority = response.json()["authority"]
    assert authority["decision_authority"] is False
    assert authority["classification"] == "source_fact"
    assert "originate_signal" in authority["forbidden_uses"]
    assert "raise_authority" in authority["forbidden_uses"]


def test_catalyst_radar_headers_are_exactly_the_private_set(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    _assert_private_headers(response)
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


# ---------------------------------------------------------------------------
# 4: unauthenticated -> 401 (entitlement dependency NOT overridden).
# ---------------------------------------------------------------------------


def test_catalyst_radar_requires_authentication_before_any_public_read() -> None:
    def must_not_read() -> tuple[object, dict[str, Any]]:
        raise AssertionError("anonymous catalyst-radar request reached the public reader")

    def deny() -> dict[str, Any]:
        raise HTTPException(
            401,
            "missing credentials",
            headers={
                **biocatalyst_api._PRIVATE_HEADERS,
                "WWW-Authenticate": "Bearer realm=mastermind",
            },
        )

    app = FastAPI()
    app.include_router(biocatalyst_api.router)
    app.dependency_overrides[biocatalyst_api.require_site_full_user] = deny
    with TestClient(app) as client:
        with mock.patch.object(biocatalyst_api, "_read_bundle", must_not_read):
            response = client.get("/api/biocatalyst/v1/catalyst-radar")

    assert response.status_code == 401
    _assert_private_headers(response)
    assert response.headers["www-authenticate"] == "Bearer realm=mastermind"
    assert response.json() == {"detail": "missing credentials"}


# ---------------------------------------------------------------------------
# 5: invalid horizon / milestone_kind / cursor -> 400.
# ---------------------------------------------------------------------------


def test_catalyst_radar_invalid_horizon_milestone_kind_and_cursor_fail_before_any_read(
    entitled_client, monkeypatch
) -> None:
    def must_not_read() -> tuple[object, dict[str, Any]]:
        raise AssertionError("invalid query must be rejected before the public read")

    monkeypatch.setattr(biocatalyst_api, "_read_bundle", must_not_read)

    bad_horizon = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=bogus")
    assert bad_horizon.status_code == 400
    assert bad_horizon.json() == {"detail": "invalid horizon"}
    _assert_private_headers(bad_horizon)

    bad_kind = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?milestone_kind=bogus")
    assert bad_kind.status_code == 400
    assert bad_kind.json() == {"detail": "invalid milestone_kind"}
    _assert_private_headers(bad_kind)

    bad_cursor = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?cursor=not-a-real-cursor!!")
    assert bad_cursor.status_code == 400
    assert bad_cursor.json() == {"detail": "invalid cursor"}
    _assert_private_headers(bad_cursor)


# ---------------------------------------------------------------------------
# 6: anchor is the generation clock, never wall clock.
# ---------------------------------------------------------------------------


def test_catalyst_radar_anchor_is_the_generation_clock_not_wall_clock(
    entitled_client, monkeypatch
) -> None:
    projection = _milestone_projection(
        [_milestone_snapshot("NCT00000001", primary_completion=("2026-05-01", "ESTIMATED"))],
        as_of="2026-02-28T23:30:00Z",
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    payload = response.json()
    # The generation's committed as-of civil date, not whatever "today" is
    # when the test happens to run.
    assert payload["effective_horizon"]["anchor_date"] == "2026-02-28"
    assert payload["as_of"] == "2026-02-28T23:30:00Z"


# ---------------------------------------------------------------------------
# 7: sponsor-map failure degrades every row -- 200, never 503.
# ---------------------------------------------------------------------------


def test_catalyst_radar_sponsor_map_failure_degrades_to_200_never_503(
    entitled_client, monkeypatch
) -> None:
    def raising_loader(_repo_root: Any) -> dict[str, Any]:
        raise RuntimeError("sponsor ticker map unavailable in this deployment")

    monkeypatch.setattr(
        biocatalyst_api,
        "_catalyst_radar_runtime",
        lambda: (RADAR_HORIZONS, RADAR_EVENT_KINDS, project_trial_milestones, raising_loader),
    )
    projection = _milestone_projection(
        [
            _milestone_snapshot("NCT00000001", primary_completion=("2026-03-01", "ACTUAL")),
            _milestone_snapshot("NCT00000002", primary_completion=("2026-03-15", "ACTUAL")),
        ]
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    payload = response.json()
    rows = payload["catalyst_radar"]
    assert len(rows) == 2, rows
    assert all(row["issuer"]["state"] == "sponsor_map_unavailable" for row in rows)
    assert all(row["issuer"]["ticker"] is None for row in rows)


def test_catalyst_radar_loads_sponsor_map_at_most_once_per_request(
    entitled_client, monkeypatch
) -> None:
    calls: list[Any] = []

    def counting_loader(repo_root: Any) -> dict[str, Any]:
        calls.append(repo_root)
        return {"rows": []}

    monkeypatch.setattr(
        biocatalyst_api,
        "_catalyst_radar_runtime",
        lambda: (RADAR_HORIZONS, RADAR_EVENT_KINDS, project_trial_milestones, counting_loader),
    )
    projection = _milestone_projection(
        [
            _milestone_snapshot("NCT00000001", primary_completion=("2026-03-01", "ACTUAL")),
            _milestone_snapshot("NCT00000002", primary_completion=("2026-03-15", "ACTUAL")),
            _milestone_snapshot("NCT00000003", primary_completion=("2026-04-01", "ACTUAL")),
        ]
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    assert len(response.json()["catalyst_radar"]) == 3
    assert len(calls) == 1, "sponsor map loader must be called at most once per request"


# ---------------------------------------------------------------------------
# 8: no-score invariant across the full response.
# ---------------------------------------------------------------------------


def test_catalyst_radar_never_emits_a_score_rank_or_confidence_key(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    payload = response.json()
    for key in _walk_keys(payload):
        assert not _FORBIDDEN_VALUE_PATTERN.search(key), key


# ---------------------------------------------------------------------------
# 9: evidence safety -- no absolute path, R2 object key, or private hash.
# ---------------------------------------------------------------------------


def test_catalyst_radar_never_leaks_a_path_object_key_or_private_hash(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    payload = response.json()

    for key in _walk_keys(payload):
        lowered = key.lower()
        for fragment in _FORBIDDEN_KEY_FRAGMENTS:
            assert fragment not in lowered, key

    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        assert not _ABSOLUTE_PATH_PATTERN.match(value), value
        assert not _R2_OBJECT_KEY_PATTERN.match(value), value
        assert not _HEX_HASH_PATTERN.match(value), value


# ---------------------------------------------------------------------------
# 10: static UI-contract checks (string-level, like test_biocatalyst_page.py).
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES = _ROOT / "templates"


def test_ui_contract_wires_the_radar_api_and_365_day_window() -> None:
    js = (_TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    html = (_TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")

    assert "RADAR_API" in js
    assert "/api/biocatalyst/v1/catalyst-radar" in js
    # The 180/365/730/All radar window options are painted at JS runtime onto
    # the shared window-control markup (tests/test_biocatalyst_page.py pins
    # that markup's SSR shape at 30/90/180/all, 90 active); "365" therefore
    # lives in the JS default/option table, not the static template.
    assert "365" in js
    assert "DEFAULT_RADAR_HORIZON = '365'" in js
    # Frozen ids/attributes (tests/test_biocatalyst_page.py:62-101) must survive
    # the upgrade in place.
    assert 'id="bci-mode-milestones"' in html
    assert 'data-mode="milestones"' in html


def test_ui_contract_never_speaks_forbidden_market_wording() -> None:
    js = (_TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    html = (_TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    # "readout" is checked as a standalone word: the pre-existing, unrelated
    # Temporal Braid feature owns the compound id/variable "braid-readout" /
    # "braidReadout" (bci-braid-readout), which is not the forbidden market
    # sense of the word and is out of this packet's scope.
    js_without_braid = re.sub(r"braid-?readout", "", js, flags=re.IGNORECASE)
    html_without_braid = re.sub(r"braid-?readout", "", html, flags=re.IGNORECASE)
    assert "readout" not in js_without_braid.lower()
    assert "readout" not in html_without_braid.lower()
    for forbidden in ("catalyst date", "cancelled"):
        assert forbidden not in js.lower(), forbidden
        assert forbidden not in html.lower(), forbidden
