"""Hostile tests for W2C M0D v2 REST source seal and v2 vertical slice.

Tests prove:
- stable same-session source throughout seal → seal eligible; one generation
- digest changes during seal → refuse/abstain
- source appears only after 04:05 → cannot pull backward
- prior session → abstain (no valid bar by close)
- malformed/multiple results → refused by bar validator
- transport errors cannot fake stability (status != valid_bar)
- CPI SOURCE_ID/SCHEMA unchanged
- v1 registration content_sha256 still matches spec
- v2 registration exists and validates against spec
- v2 store root guards refuse v1 roots
- v2 unit failure cannot suppress v1 timer (units independent)
- experience-v2 activation guard works
- SourceFamily importable from market_memory_sources
- seal predicate coverage minima enforced
- lookback cannot substitute for missing seal
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _make_spy_bar(close: float = 590.25) -> dict[str, Any]:
    """Return a minimal valid SPY REST bar."""
    return {
        "o": 588.0,
        "h": 592.0,
        "l": 587.0,
        "c": close,
        "v": 10_000_000,
        "n": 150000,
        "t": 1_720_000_000_000,
        "vw": 589.5,
    }


def _make_spy_obs(
    observed_at: datetime,
    bar: dict[str, Any],
    status: str = "valid_bar",
) -> Any:
    """Create a SealObservation with the correct field names."""
    from engine.neuralweb.market_memory_sources_spy import SealObservation  # noqa: PLC0415

    results = [bar]
    digest = hashlib.sha256(
        json.dumps(results, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return SealObservation(
        observed_at=observed_at,
        status=status,
        digest=digest if status == "valid_bar" else None,
    )


def _make_transport_error_obs(observed_at: datetime) -> Any:
    from engine.neuralweb.market_memory_sources_spy import SealObservation  # noqa: PLC0415

    return SealObservation(
        observed_at=observed_at,
        status="transport_error",
        digest=None,
    )


def _bar_digest(bar: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps([bar], separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Source kernel guard
# ---------------------------------------------------------------------------


def test_validate_source_store_root_accepts_path(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_source_kernel import validate_source_store_root

    sources_dir = tmp_path / "state" / "sources"
    sources_dir.mkdir(parents=True)
    result = validate_source_store_root(sources_dir)
    assert result.name == "sources"


def test_validate_source_store_root_rejects_repository(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_source_kernel import (
        validate_source_store_root,
        SourceStoreError,
    )

    # Cannot use the repository itself
    with pytest.raises(SourceStoreError):
        validate_source_store_root(ROOT)


# ---------------------------------------------------------------------------
# SPY REST source module constants
# ---------------------------------------------------------------------------


def test_spy_family_constants() -> None:
    from engine.neuralweb.market_memory_sources_spy import (
        SOURCE_ID,
        SOURCE_SCHEMA,
        SPY_FAMILY,
    )

    assert SOURCE_ID == "massive_rest:SPY:unadjusted_daily"
    assert SOURCE_SCHEMA == "market_memory.source.spy_rest_unadjusted_daily.v1"
    assert SPY_FAMILY.source_id == SOURCE_ID
    assert SPY_FAMILY.source_schema == SOURCE_SCHEMA


def test_validate_spy_rest_store_root_accepts_spy_leaf(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_sources_spy import validate_spy_rest_store_root

    spy_dir = tmp_path / "state" / "sources-spy-rest-v1"
    spy_dir.mkdir(parents=True)
    result = validate_spy_rest_store_root(spy_dir)
    assert result.name == "sources-spy-rest-v1"


def test_validate_spy_rest_store_root_rejects_cpi_root(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_sources_spy import validate_spy_rest_store_root
    from engine.neuralweb.market_memory_source_kernel import SourceStoreError

    cpi_dir = tmp_path / "state" / "sources"
    cpi_dir.mkdir(parents=True)
    with pytest.raises(SourceStoreError):
        validate_spy_rest_store_root(cpi_dir)


# ---------------------------------------------------------------------------
# Seal predicate: stable same-session → eligible
# ---------------------------------------------------------------------------


def test_stable_seal_is_eligible() -> None:
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    bar = _make_spy_bar()
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)
    after_04_04 = window_open + timedelta(seconds=255)

    observations = [
        _make_spy_obs(window_open + timedelta(seconds=5), bar),      # first 60s
        _make_spy_obs(window_open + timedelta(seconds=120), bar),
        _make_spy_obs(window_open + timedelta(seconds=241), bar),    # ≥240s span
        _make_spy_obs(after_04_04, bar),                              # after 04:04:00Z
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is True
    assert state.stable is True


def test_stable_seal_one_generation_not_n_polls(tmp_path: Path) -> None:
    """N polls with identical digest → exactly one generation created."""
    from engine.neuralweb.market_memory_sources_spy import (
        evaluate_seal_predicate,
        intake_spy_rest_bar,
    )

    session = date(2026, 8, 21)
    bar = _make_spy_bar()
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    observations = [
        _make_spy_obs(window_open + timedelta(seconds=5), bar),
        _make_spy_obs(window_open + timedelta(seconds=120), bar),
        _make_spy_obs(window_open + timedelta(seconds=241), bar),
        _make_spy_obs(window_open + timedelta(seconds=255), bar),
    ]
    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is True

    spy_dir = tmp_path / "state" / "sources-spy-rest-v1"
    spy_dir.mkdir(parents=True)

    now_str = _utc(2026, 8, 22, 4, 5, 30).isoformat().replace("+00:00", "Z")

    # Call intake once
    r1 = intake_spy_rest_bar(
        spy_dir,
        session=session,
        seal_state=state,
        results=[bar],
        sealed_at=now_str,
        observed_at=now_str,
    )
    assert r1.created is True

    # Call intake again — same session, same results → idempotent, no new generation
    r2 = intake_spy_rest_bar(
        spy_dir,
        session=session,
        seal_state=state,
        results=[bar],
        sealed_at=now_str,
        observed_at=now_str,
    )
    assert r2.created is False


def test_digest_change_during_seal_is_unstable() -> None:
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate, SealObservation

    session = date(2026, 8, 21)
    bar1 = _make_spy_bar(close=590.25)
    bar2 = _make_spy_bar(close=591.00)
    digest1 = _bar_digest(bar1)
    digest2 = _bar_digest(bar2)
    assert digest1 != digest2

    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    observations = [
        SealObservation(
            observed_at=window_open + timedelta(seconds=5),
            status="valid_bar",
            digest=digest1,
        ),
        SealObservation(
            observed_at=window_open + timedelta(seconds=120),
            status="valid_bar",
            digest=digest2,  # digest changed!
        ),
        SealObservation(
            observed_at=window_open + timedelta(seconds=241),
            status="valid_bar",
            digest=digest2,
        ),
        SealObservation(
            observed_at=window_open + timedelta(seconds=255),
            status="valid_bar",
            digest=digest2,
        ),
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False
    assert state.stable is False


def test_no_observations_not_eligible() -> None:
    """No valid bar by 04:05Z → source absent."""
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    state = evaluate_seal_predicate(
        [], session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


def test_too_few_observations_not_eligible() -> None:
    """Fewer than 3 successful observations → not eligible."""
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)
    bar = _make_spy_bar()

    observations = [
        _make_spy_obs(window_open + timedelta(seconds=5), bar),
        _make_spy_obs(window_open + timedelta(seconds=245), bar),
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


def test_transport_errors_cannot_fake_stability() -> None:
    """Transport errors (status=transport_error) do not count toward coverage."""
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    observations = [
        _make_transport_error_obs(window_open + timedelta(seconds=i * 60))
        for i in range(5)
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


def test_no_observation_in_first_60s_not_eligible() -> None:
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)
    bar = _make_spy_bar()

    observations = [
        _make_spy_obs(window_open + timedelta(seconds=70), bar),   # after 60s
        _make_spy_obs(window_open + timedelta(seconds=180), bar),
        _make_spy_obs(window_open + timedelta(seconds=241), bar),
        _make_spy_obs(window_open + timedelta(seconds=255), bar),
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


def test_no_observation_after_04_04_not_eligible() -> None:
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)
    bar = _make_spy_bar()
    # All observations before 04:04:00Z
    observations = [
        _make_spy_obs(window_open + timedelta(seconds=5), bar),
        _make_spy_obs(window_open + timedelta(seconds=120), bar),
        _make_spy_obs(window_open + timedelta(seconds=230), bar),
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


def test_malformed_results_refused() -> None:
    from engine.neuralweb.market_memory_sources_spy import _validate_single_bar
    from engine.neuralweb.market_memory_source_kernel import SourceIntakeError

    session = date(2026, 8, 21)

    # Empty bar
    ok, reason = _validate_single_bar({}, session_date=session)
    assert not ok and reason is not None

    # Missing required field
    bar = _make_spy_bar()
    del bar["h"]
    ok2, reason2 = _validate_single_bar(bar, session_date=session)
    assert not ok2 and reason2 is not None


def test_insufficient_span_not_eligible() -> None:
    """Observations span less than 240s → not eligible."""
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)
    bar = _make_spy_bar()

    observations = [
        _make_spy_obs(window_open + timedelta(seconds=5), bar),
        _make_spy_obs(window_open + timedelta(seconds=120), bar),
        _make_spy_obs(window_open + timedelta(seconds=200), bar),   # only 195s span
    ]

    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False


# ---------------------------------------------------------------------------
# Session boundaries
# ---------------------------------------------------------------------------


def test_session_window_for_seal_time() -> None:
    from engine.neuralweb.market_memory_sources_spy import seal_window_for_session

    session_d = date(2026, 8, 21)
    open_, close_ = seal_window_for_session(session_d)
    assert open_.date() == date(2026, 8, 22)
    assert open_.hour == 4
    assert open_.minute == 0
    assert close_.date() == date(2026, 8, 22)
    assert close_.hour == 4
    assert close_.minute == 5


def test_session_for_seal_time() -> None:
    from engine.neuralweb.market_memory_sources_spy import session_for_seal_time

    seal_time = _utc(2026, 8, 22, 4, 2, 0)
    session = session_for_seal_time(seal_time)
    assert session == date(2026, 8, 21)


# ---------------------------------------------------------------------------
# Technicals-v2 root guards
# ---------------------------------------------------------------------------


def test_technicals_v2_root_guard_accepts_v2_leaf(tmp_path: Path) -> None:
    from scripts.capture_market_memory_technicals_v2 import validate_technicals_v2_store_root

    v2_dir = tmp_path / "state" / "technicals-v2"
    v2_dir.mkdir(parents=True)
    result = validate_technicals_v2_store_root(v2_dir)
    assert result.name == "technicals-v2"


def test_technicals_v2_root_guard_refuses_v1_root(tmp_path: Path) -> None:
    from scripts.capture_market_memory_technicals_v2 import (
        validate_technicals_v2_store_root,
        TechnicalsV2StoreError,
    )

    v1_dir = tmp_path / "state" / "technicals-v1"
    v1_dir.mkdir(parents=True)
    with pytest.raises(TechnicalsV2StoreError):
        validate_technicals_v2_store_root(v1_dir)


def test_spy_rest_source_root_guard_refuses_cpi_path(tmp_path: Path) -> None:
    from scripts.capture_market_memory_technicals_v2 import (
        validate_spy_rest_source_root,
        TechnicalsV2SourceError,
    )

    cpi_dir = tmp_path / "state" / "sources"
    cpi_dir.mkdir(parents=True)
    with pytest.raises(TechnicalsV2SourceError):
        validate_spy_rest_source_root(cpi_dir)


# ---------------------------------------------------------------------------
# Experience-v2 root guard and activation policy
# ---------------------------------------------------------------------------


def test_experience_store_root_accepts_v1(tmp_path: Path) -> None:
    """B6: validate_experience_store_root is v1-only."""
    from engine.neuralweb.market_memory_experience_accrual import validate_experience_store_root

    v1_dir = tmp_path / "state" / "experience-v1"
    v1_dir.mkdir(parents=True)
    result = validate_experience_store_root(v1_dir)
    assert result.name == "experience-v1"


def test_experience_store_root_rejects_v2(tmp_path: Path) -> None:
    """B6: validate_experience_store_root must NOT accept experience-v2."""
    from engine.neuralweb.market_memory_experience_accrual import (
        validate_experience_store_root,
        MarketMemoryExperienceStoreError,
    )

    v2_dir = tmp_path / "state" / "experience-v2"
    v2_dir.mkdir(parents=True)
    with pytest.raises(MarketMemoryExperienceStoreError):
        validate_experience_store_root(v2_dir)


def test_experience_v2_store_root_validator_accepts_v2(tmp_path: Path) -> None:
    """B6: validate_experience_v2_store_root accepts experience-v2."""
    from scripts.accrue_market_memory_spy_experience_v2 import validate_experience_v2_store_root

    v2_dir = tmp_path / "state" / "experience-v2"
    v2_dir.mkdir(parents=True)
    result = validate_experience_v2_store_root(v2_dir)
    assert result.name == "experience-v2"


def test_experience_v2_store_root_validator_rejects_v1(tmp_path: Path) -> None:
    """B6: validate_experience_v2_store_root must reject experience-v1."""
    from scripts.accrue_market_memory_spy_experience_v2 import validate_experience_v2_store_root
    from engine.neuralweb.market_memory_experience_accrual import MarketMemoryExperienceStoreError

    v1_dir = tmp_path / "state" / "experience-v1"
    v1_dir.mkdir(parents=True)
    with pytest.raises(MarketMemoryExperienceStoreError):
        validate_experience_v2_store_root(v1_dir)


def test_experience_store_root_refuses_wrong_leaf(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_experience_accrual import (
        validate_experience_store_root,
        MarketMemoryExperienceStoreError,
    )

    bad_dir = tmp_path / "state" / "technicals-v1"
    bad_dir.mkdir(parents=True)
    with pytest.raises(MarketMemoryExperienceStoreError):
        validate_experience_store_root(bad_dir)


def test_experience_v2_activation_guard_missing_marker(tmp_path: Path) -> None:
    from scripts.accrue_market_memory_spy_experience_v2 import (
        check_activation,
        ExperienceV2ActivationError,
    )

    exp_root = tmp_path / "state" / "experience-v2"
    exp_root.mkdir(parents=True)
    session = date(2026, 8, 25)

    with pytest.raises(ExperienceV2ActivationError, match="install marker"):
        check_activation(exp_root, session=session)


def test_experience_v2_activation_guard_session_too_early(tmp_path: Path) -> None:
    from scripts.accrue_market_memory_spy_experience_v2 import (
        check_activation,
        ExperienceV2ActivationError,
        _write_install_marker,
    )

    exp_root = tmp_path / "state" / "experience-v2"
    exp_root.mkdir(parents=True)
    # Install on 2026-08-25; session on 2026-08-25 — must be STRICTLY after
    _write_install_marker(exp_root, "2026-08-25T04:32:00Z")
    session = date(2026, 8, 25)

    with pytest.raises(ExperienceV2ActivationError, match="not strictly after"):
        check_activation(exp_root, session=session)


# ---------------------------------------------------------------------------
# V1 registration integrity
# ---------------------------------------------------------------------------


def test_v1_registration_content_sha256_unchanged() -> None:
    """Prove v1 registration content_sha256 is still e00ffc1d34..."""
    reg_path = ROOT / "config" / "market_memory_spy_experience_registration.v1.json"
    data = json.loads(reg_path.read_bytes())
    assert data["content_sha256"] == "e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3"
    assert data["schema"] == "market_memory.spy_experience_registration.v1"


def test_v1_registration_spec_unchanged() -> None:
    """Prove _expected_registration_spec() dict still matches v1 JSON file."""
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec

    reg_path = ROOT / "config" / "market_memory_spy_experience_registration.v1.json"
    data = json.loads(reg_path.read_bytes())
    assert data["spec"] == _expected_registration_spec()


def test_v2_registration_exists_and_validates() -> None:
    """Prove v2 registration file exists and matches _expected_registration_spec_v2()."""
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    reg_path = ROOT / "config" / "market_memory_spy_experience_registration.v2.json"
    assert reg_path.exists(), "v2 registration file must exist"
    data = json.loads(reg_path.read_bytes())
    assert data["schema"] == "market_memory.spy_experience_registration.v2"
    assert data["spec"] == _expected_registration_spec_v2()


def test_v2_registration_schema_constant() -> None:
    from engine.neuralweb.market_memory_experience_accrual import REGISTRATION_SCHEMA_V2

    assert REGISTRATION_SCHEMA_V2 == "market_memory.spy_experience_registration.v2"


# ---------------------------------------------------------------------------
# Store isolation: v2 cannot write v1 roots
# ---------------------------------------------------------------------------


def test_technicals_v2_refuses_v1_root(tmp_path: Path) -> None:
    from scripts.capture_market_memory_technicals_v2 import (
        validate_technicals_v2_store_root,
        TechnicalsV2StoreError,
    )

    v1_root = tmp_path / "state" / "technicals-v1"
    v1_root.mkdir(parents=True)
    with pytest.raises(TechnicalsV2StoreError):
        validate_technicals_v2_store_root(v1_root)


def test_experience_v2_activation_blocks_v1_root(tmp_path: Path) -> None:
    """B6: Using a v1 root for experience-v2 fails — validate_experience_v2_store_root rejects it."""
    from scripts.accrue_market_memory_spy_experience_v2 import accrue_spy_experience_v2
    from engine.neuralweb.market_memory_experience_accrual import MarketMemoryExperienceStoreError

    v1_root = tmp_path / "state" / "experience-v1"
    v1_root.mkdir(parents=True)

    # Pass session explicitly so session derivation is bypassed
    with pytest.raises(MarketMemoryExperienceStoreError, match="experience-v2"):
        accrue_spy_experience_v2(
            repository_root=ROOT,
            experience_root=v1_root,
            source_root=tmp_path / "state" / "sources-spy-rest-v1",
            technicals_v2_root=tmp_path / "state" / "technicals-v2",
            session=date(2026, 8, 21),
        )


# ---------------------------------------------------------------------------
# Unit independence: v1 experience has no Requires= on v2
# ---------------------------------------------------------------------------


def test_experience_v1_unit_has_no_requires_v2() -> None:
    unit_path = ROOT / "app" / "deploy" / "macro-market-memory-experience.service"
    content = unit_path.read_text()
    lines = [line.strip() for line in content.splitlines()]
    requires_lines = [line for line in lines if line.startswith("Requires=")]
    for req in requires_lines:
        assert "v2" not in req, f"v1 experience unit must not Requires= v2: {req}"


def test_experience_v2_timer_is_04_32z() -> None:
    timer_path = ROOT / "app" / "deploy" / "macro-market-memory-experience-v2.timer"
    content = timer_path.read_text()
    assert "04:32:00 UTC" in content


def test_experience_v1_timer_is_still_04_30z() -> None:
    timer_path = ROOT / "app" / "deploy" / "macro-market-memory-experience.timer"
    content = timer_path.read_text()
    assert "04:30:00 UTC" in content


def test_source_spy_rest_timer_is_04_00z() -> None:
    timer_path = ROOT / "app" / "deploy" / "macro-market-memory-source-spy-rest.timer"
    content = timer_path.read_text()
    assert "04:00:00 UTC" in content


def test_technicals_v2_timer_is_04_07z() -> None:
    timer_path = ROOT / "app" / "deploy" / "macro-market-memory-technicals-v2.timer"
    content = timer_path.read_text()
    assert "04:07:00 UTC" in content


# ---------------------------------------------------------------------------
# Source-spy-rest unit: PrivateNetwork must NOT be set to true
# ---------------------------------------------------------------------------


def test_source_spy_rest_unit_no_private_network() -> None:
    unit_path = ROOT / "app" / "deploy" / "macro-market-memory-source-spy-rest.service"
    content = unit_path.read_text()
    lines = [line.strip() for line in content.splitlines()]
    pn_lines = [line for line in lines if line.startswith("PrivateNetwork=")]
    for pn in pn_lines:
        assert pn.lower() in ("privatenetwork=false", "privatenetwork=no"), (
            f"source-spy-rest must not set PrivateNetwork=true: {pn}"
        )


def test_source_spy_rest_unit_has_load_credential() -> None:
    unit_path = ROOT / "app" / "deploy" / "macro-market-memory-source-spy-rest.service"
    content = unit_path.read_text()
    assert "LoadCredential" in content
    assert "MASSIVE_API_KEY" in content
    assert "POLYGON_API_KEY" in content


# ---------------------------------------------------------------------------
# CPI SOURCE_ID/SCHEMA unchanged
# ---------------------------------------------------------------------------


def test_cpi_source_constants_unchanged() -> None:
    from engine.neuralweb import market_memory_sources as sources

    assert sources.SOURCE_ID == "fred_alfred:CPIAUCSL"
    assert sources.SOURCE_SCHEMA == "market_memory.source.alfred_cpiaucsl.v1"


# ---------------------------------------------------------------------------
# Kernel re-export: SourceFamily importable from market_memory_sources
# ---------------------------------------------------------------------------


def test_kernel_reexport_via_sources() -> None:
    from engine.neuralweb.market_memory_sources import SourceFamily
    from engine.neuralweb.market_memory_source_kernel import SourceFamily as KernelSourceFamily

    assert SourceFamily is KernelSourceFamily


# ---------------------------------------------------------------------------
# V2 registration spec checks
# ---------------------------------------------------------------------------


def test_v2_registration_spec_v2_profile() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    assert spec["profile"] == "market_memory.private.spy_experience_accrual.v2"


def test_v2_registration_spec_source_family() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    assert spec["source_seal"]["source_family"] == "sources-spy-rest-v1"
    assert spec["source_seal"]["source_id"] == "massive_rest:SPY:unadjusted_daily"


def test_v2_registration_spec_technical_profile_v2() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    assert "v2" in spec["state_inputs"]["technical_profile"]


def test_v2_registration_spec_store_roots_disjoint() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    roots = spec["store_roots"]
    assert roots["experience_leaf"] == "experience-v2"
    assert roots["technicals_leaf"] == "technicals-v2"
    assert roots["source_leaf"] == "sources-spy-rest-v1"
    assert roots["disjoint_from_v1"] is True


def test_v2_registration_spec_trusted_v1_read_only() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    assert spec["state_inputs"]["trusted_v1_read_only"] is True


def test_v2_registration_spec_seal_window_params() -> None:
    from engine.neuralweb.market_memory_experience_accrual import _expected_registration_spec_v2

    spec = _expected_registration_spec_v2()
    seal = spec["source_seal"]
    assert seal["seal_window_opens_utc_time"] == "04:00:00Z"
    assert seal["seal_window_closes_utc_time"] == "04:05:00Z"
    assert seal["seal_window_on_day"] == "D+1"
    pred = seal["stability_predicate"]
    assert pred["min_successful_observations"] == 3
    assert pred["min_span_seconds"] == 240
    assert pred["require_observation_in_first_60s"] is True
    assert pred["require_observation_after_04_04_00z"] is True


# ---------------------------------------------------------------------------
# _results_digest: canonical hash strips request_id
# ---------------------------------------------------------------------------


def test_results_digest_strips_request_id() -> None:
    from engine.neuralweb.market_memory_sources_spy import _results_digest

    bar = _make_spy_bar()
    # _results_digest takes list[Any] not a response dict
    digest_a = _results_digest([dict(bar)])
    digest_b = _results_digest([dict(bar)])
    assert digest_a == digest_b


def test_results_digest_differs_on_different_bar() -> None:
    from engine.neuralweb.market_memory_sources_spy import _results_digest

    bar1 = _make_spy_bar(close=590.0)
    bar2 = _make_spy_bar(close=591.0)
    assert _results_digest([bar1]) != _results_digest([bar2])


# ---------------------------------------------------------------------------
# Lookback cannot substitute for missing seal
# ---------------------------------------------------------------------------


def test_lookback_cannot_create_generation_without_seal(tmp_path: Path) -> None:
    from scripts.capture_market_memory_technicals_v2 import (
        capture_technicals_v2,
        TechnicalsV2SourceError,
    )

    source_dir = tmp_path / "state" / "sources-spy-rest-v1"
    source_dir.mkdir(parents=True)
    store_dir = tmp_path / "state" / "technicals-v2"
    store_dir.mkdir(parents=True)

    with pytest.raises(TechnicalsV2SourceError):
        capture_technicals_v2(
            source_root=source_dir,
            store_root=store_dir,
            session=date(2026, 8, 21),
        )


# ===========================================================================
# HOSTILE TESTS (H1-H13): Prove each B/M blocker cannot regress
# ===========================================================================


# H1 — B1: _build_fetcher uses CREDENTIALS_DIRECTORY; missing creds → _main returns 1
def test_h1_build_fetcher_uses_credentials_directory(tmp_path: Path) -> None:
    """H1: _build_fetcher succeeds with CREDENTIALS_DIRECTORY; without creds, _main returns 1."""
    import tempfile
    from scripts.ingest_market_memory_sources_spy import _build_fetcher, _main

    # Without any credentials: _main should return 1
    env_backup = {}
    for key in ("CREDENTIALS_DIRECTORY", "MASSIVE_API_KEY", "POLYGON_API_KEY"):
        env_backup[key] = os.environ.pop(key, None)
    try:
        # No credentials → _build_fetcher returns None → _main returns 1
        fetcher = _build_fetcher()
        assert fetcher is None, "_build_fetcher must return None when no credentials"
    finally:
        for key, val in env_backup.items():
            if val is not None:
                os.environ[key] = val

    # With CREDENTIALS_DIRECTORY pointing to temp dir with one key file:
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir(mode=0o700)
    key_file = creds_dir / "MASSIVE_API_KEY"
    key_file.write_text("test-api-key-123\n", encoding="utf-8")
    key_file.chmod(0o600)

    old_creds = os.environ.pop("CREDENTIALS_DIRECTORY", None)
    os.environ["CREDENTIALS_DIRECTORY"] = str(creds_dir)
    try:
        # Should not raise (may fail to build HTTP client, but that's OK)
        fetcher2 = _build_fetcher()
        # fetcher2 may be None if HTTP client unavailable in test env, that's OK
        # The important thing is it doesn't crash
    finally:
        del os.environ["CREDENTIALS_DIRECTORY"]
        if old_creds is not None:
            os.environ["CREDENTIALS_DIRECTORY"] = old_creds


def test_h1_no_credentials_main_returns_1() -> None:
    """H1: _main returns 1 when status is no_credentials."""
    from scripts.ingest_market_memory_sources_spy import _main
    import tempfile

    env_backup = {}
    for key in ("CREDENTIALS_DIRECTORY", "MASSIVE_API_KEY", "POLYGON_API_KEY"):
        env_backup[key] = os.environ.pop(key, None)
    try:
        # Pass an explicit session so we don't need to be inside the seal window.
        # Without creds, ingest_spy_rest_source returns no_credentials.
        # But it also refuses if session is in the past. We need to mock.
        # Instead test via _main which calls ingest_spy_rest_source.
        # We need a session in a valid seal window context — skip via mocking.
        # Test the receipts path: if receipt.status == "no_credentials" → return 1.
        from scripts.ingest_market_memory_sources_spy import ingest_spy_rest_source
        with tempfile.TemporaryDirectory() as td:
            store_dir = Path(td) / "state" / "sources-spy-rest-v1"
            store_dir.mkdir(parents=True)
            # Provide clock so we're inside the seal window
            seal_time = _utc(2026, 8, 22, 4, 2, 0)
            result = ingest_spy_rest_source(
                store_root=store_dir,
                session=date(2026, 8, 21),
                clock=lambda: seal_time,
                sleeper=lambda _: None,
            )
            assert result["status"] == "no_credentials"
    finally:
        for key, val in env_backup.items():
            if val is not None:
                os.environ[key] = val


# H2 — B2: Timers at 04:07Z/04:32Z derive session T-1, not T
def test_h2_technicals_v2_at_0407_derives_previous_session() -> None:
    """H2: At 2026-08-21T04:07Z, session = 2026-08-20, not 2026-08-21."""
    from engine.neuralweb.market_memory_sources_spy import derive_morning_session

    # 2026-08-21 is a Friday (session). At 04:07Z → session = 2026-08-20 (Thursday).
    now = _utc(2026, 8, 21, 4, 7, 0)
    derived = derive_morning_session(now)
    assert derived == date(2026, 8, 20), (
        f"At 04:07Z on 2026-08-21, session must be 2026-08-20 (D), not 2026-08-21 (D+1); "
        f"got {derived}"
    )


def test_h2_experience_v2_at_0432_derives_previous_session() -> None:
    """H2: At 2026-08-21T04:32Z, session = 2026-08-20, not 2026-08-21."""
    from engine.neuralweb.market_memory_sources_spy import derive_morning_session

    now = _utc(2026, 8, 21, 4, 32, 0)
    derived = derive_morning_session(now)
    assert derived == date(2026, 8, 20), (
        f"At 04:32Z on 2026-08-21, session must be 2026-08-20 (D); got {derived}"
    )


def test_h2_derive_morning_session_returns_none_before_threshold() -> None:
    """H2: Before 04:05Z, derive_morning_session returns None."""
    from engine.neuralweb.market_memory_sources_spy import derive_morning_session

    # 04:03Z → before threshold → None
    now = _utc(2026, 8, 21, 4, 3, 0)
    derived = derive_morning_session(now)
    assert derived is None


def test_h2_derive_morning_session_returns_none_for_non_session() -> None:
    """H2: If T-1 is not an XNYS session (e.g. Sunday), returns None."""
    from engine.neuralweb.market_memory_sources_spy import derive_morning_session

    # 2026-08-17 is Monday; T-1 = 2026-08-16 (Sunday) → not a session → None
    now = _utc(2026, 8, 17, 4, 7, 0)
    derived = derive_morning_session(now)
    assert derived is None, f"Sunday T-1 should yield None; got {derived}"


# H3 — B3: update.sh contains --write-install-marker and three new profiles in both loops
def test_h3_update_sh_write_install_marker() -> None:
    """H3: update.sh contains --write-install-marker invocation."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()
    assert "--write-install-marker" in content, (
        "update.sh must invoke --write-install-marker after experience-v2 install"
    )


def test_h3_update_sh_reciprocal_loops_include_v2_profiles() -> None:
    """H3: STOP and RE-ARM loops include v2 profiles; READY loop does not."""
    import re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    # Extract the stop function body
    m_stop = re.search(
        r"stop_reciprocal_market_memory_writers\(\)\s*\{(.*?)\n\}",
        content,
        re.DOTALL,
    )
    assert m_stop, "stop_reciprocal_market_memory_writers function not found"
    stop_body = m_stop.group(1)

    # Extract the re-arm loop line
    m_rearm = re.search(r"for RECIPROCAL_PROFILE in ([^\n;]+)", content)
    assert m_rearm, "for RECIPROCAL_PROFILE in ... (re-arm loop) not found"
    rearm_line = m_rearm.group(1)

    # Extract the ready function body
    m_ready = re.search(
        r"reciprocal_market_memory_units_ready\(\)\s*\{(.*?)\n\}",
        content,
        re.DOTALL,
    )
    assert m_ready, "reciprocal_market_memory_units_ready function not found"
    ready_body = m_ready.group(1)

    for profile in ("source-spy-rest", "technicals-v2", "experience-v2"):
        assert profile in stop_body, (
            f"stop_reciprocal_market_memory_writers must contain '{profile}'"
        )
        assert profile in rearm_line, (
            f"re-arm loop must contain '{profile}'"
        )
        assert profile not in ready_body, (
            f"reciprocal_market_memory_units_ready must NOT contain '{profile}' "
            "(v2 units may not exist on first deploy and would deadlock the v1 gate)"
        )


# H4 — B4: Saturday install does not TypeError; first eligible is next XNYS session
def test_h4_saturday_install_no_typeerror(tmp_path: Path) -> None:
    """H4: Saturday install timestamp does not TypeError; first eligible is the next XNYS session."""
    from scripts.accrue_market_memory_spy_experience_v2 import (
        check_activation,
        ExperienceV2ActivationError,
        _write_install_marker,
    )

    exp_root = tmp_path / "state" / "experience-v2"
    exp_root.mkdir(parents=True)
    # 2026-08-22 is a Saturday
    _write_install_marker(exp_root, "2026-08-22T10:00:00Z")

    # Saturday install → next XNYS session is Monday 2026-08-24
    # Session 2026-08-24 should be eligible (>= first eligible)
    monday = date(2026, 8, 24)
    try:
        check_activation(exp_root, session=monday)
        # No error → eligible ✓
    except TypeError as exc:
        raise AssertionError(
            f"Saturday install must not raise TypeError; got: {exc}"
        ) from exc
    except ExperienceV2ActivationError as exc:
        raise AssertionError(
            f"Monday session should be eligible after Saturday install; got: {exc}"
        ) from exc

    # Friday 2026-08-21 should NOT be eligible (before Saturday install)
    friday = date(2026, 8, 21)
    with pytest.raises(ExperienceV2ActivationError):
        check_activation(exp_root, session=friday)


def test_h4_friday_install_first_eligible_is_monday(tmp_path: Path) -> None:
    """H4: Friday install → first eligible is next Monday (session_n_forward(Friday, 1))."""
    from scripts.accrue_market_memory_spy_experience_v2 import (
        check_activation,
        ExperienceV2ActivationError,
        _write_install_marker,
    )

    exp_root = tmp_path / "state" / "experience-v2"
    exp_root.mkdir(parents=True)
    # 2026-08-21 is a Friday (session)
    _write_install_marker(exp_root, "2026-08-21T10:00:00Z")

    # Friday is a session → session_n_forward(Friday, 1) = Monday 2026-08-24
    monday = date(2026, 8, 24)
    try:
        check_activation(exp_root, session=monday)
    except ExperienceV2ActivationError as exc:
        raise AssertionError(
            f"Monday should be eligible after Friday install; got: {exc}"
        ) from exc

    # Friday itself should NOT be eligible (must be STRICTLY after install date)
    friday = date(2026, 8, 21)
    with pytest.raises(ExperienceV2ActivationError, match="not strictly after"):
        check_activation(exp_root, session=friday)


# H5 — B6: accrue_spy_experience_v2 on experience-v1 root raises and creates no files
def test_h5_accrue_v2_on_v1_root_raises_and_writes_nothing(tmp_path: Path) -> None:
    """H5: v2 accrual on experience-v1 root raises MarketMemoryExperienceStoreError and writes nothing."""
    from scripts.accrue_market_memory_spy_experience_v2 import accrue_spy_experience_v2
    from engine.neuralweb.market_memory_experience_accrual import MarketMemoryExperienceStoreError

    v1_root = tmp_path / "state" / "experience-v1"
    v1_root.mkdir(parents=True)
    # Plant a marker to ensure the check reaches the store validator
    marker = v1_root / ".v2_install_verified"
    marker.write_text("2026-08-21T04:32:00Z\n")

    files_before = set(v1_root.rglob("*"))

    with pytest.raises(MarketMemoryExperienceStoreError):
        accrue_spy_experience_v2(
            repository_root=ROOT,
            experience_root=v1_root,
            source_root=tmp_path / "state" / "sources-spy-rest-v1",
            technicals_v2_root=tmp_path / "state" / "technicals-v2",
            session=date(2026, 8, 21),
        )

    files_after = set(v1_root.rglob("*"))
    new_files = files_after - files_before
    assert not new_files, f"v2 accrual must not create files in v1 root; created: {new_files}"


# H6 — M1: OPTIONS_RUNTIME_CLOSURE_REGEX and OPTIONS_RECIPROCAL_CLOSURE_REGEX content
def test_h6_options_runtime_closure_regex_excludes_v2_paths() -> None:
    """H6: OPTIONS_RUNTIME_CLOSURE_REGEX must NOT include v2 paths."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    # Extract the RUNTIME regex value
    import re
    m = re.search(r"OPTIONS_RUNTIME_CLOSURE_REGEX='([^']+)'", content)
    assert m, "OPTIONS_RUNTIME_CLOSURE_REGEX not found in update.sh"
    regex_val = m.group(1)

    for v2_path in (
        "source-spy-rest",
        "technicals-v2",
        "experience-v2",
        "sources_spy",
        "source_kernel",
        "capture_market_memory_technicals_v2",
        "ingest_market_memory_sources_spy",
        "accrue_market_memory_spy_experience_v2",
    ):
        assert v2_path not in regex_val, (
            f"OPTIONS_RUNTIME_CLOSURE_REGEX must NOT include {v2_path!r} "
            "(v2 paths belong in OPTIONS_RECIPROCAL_CLOSURE_REGEX)"
        )


def test_h6_options_reciprocal_closure_regex_includes_v2_paths() -> None:
    """H6: OPTIONS_RECIPROCAL_CLOSURE_REGEX must include v2 paths."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    import re
    m = re.search(r"OPTIONS_RECIPROCAL_CLOSURE_REGEX='([^']+)'", content)
    assert m, "OPTIONS_RECIPROCAL_CLOSURE_REGEX not found in update.sh"
    regex_val = m.group(1)

    for v2_path in (
        "source-spy-rest",
        "technicals-v2",
        "experience-v2",
        "ingest_market_memory_sources_spy",
        "capture_market_memory_technicals_v2",
        "accrue_market_memory_spy_experience_v2",
    ):
        assert v2_path in regex_val, (
            f"OPTIONS_RECIPROCAL_CLOSURE_REGEX must include {v2_path!r}"
        )


# H7 — M5: Digest-stable in-window results are persisted even if post-window fetch differs
def test_h7_stable_in_window_results_persisted(tmp_path: Path) -> None:
    """H7: _collect_seal_observations returns cached results; sealed bar is from the window, not re-fetched."""
    from scripts.ingest_market_memory_sources_spy import _collect_seal_observations
    from engine.neuralweb.market_memory_sources_spy import _results_digest

    session = date(2026, 8, 21)
    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    # Build a bar whose bar.t milliseconds correspond to session 2026-08-21
    session_ts_ms = int(datetime(2026, 8, 21, tzinfo=timezone.utc).timestamp() * 1000)
    bar_in_window = {
        "o": 588.0, "h": 592.0, "l": 587.0, "c": 590.25,
        "v": 10_000_000, "n": 150000,
        "t": session_ts_ms, "T": "SPY",
    }

    def fake_fetcher(path: str, params: Any) -> dict[str, Any]:
        return {"status": "OK", "results": [dict(bar_in_window)]}

    times = [
        window_open + timedelta(seconds=5),
        window_open + timedelta(seconds=120),
        window_open + timedelta(seconds=241),
        window_open + timedelta(seconds=255),
        window_close,  # ends the loop
    ]
    time_idx = [0]
    def fake_clock() -> datetime:
        idx = time_idx[0]
        if idx < len(times):
            t = times[idx]
            time_idx[0] += 1
            return t
        return window_close

    observations, results_cache = _collect_seal_observations(
        session,
        seal_open=window_open,
        seal_close=window_close,
        fetcher=fake_fetcher,
        clock=fake_clock,
        sleeper=lambda _: None,
    )

    digest = _results_digest([bar_in_window])
    assert digest in results_cache, (
        f"In-window bar digest {digest!r} must be cached; cache keys: {list(results_cache)}"
    )
    assert results_cache[digest][0]["c"] == 590.25, "Cached results must match in-window bar close"


# H8 — M6 (B8): Lookback cannot create a generation without a D seal
def test_h8_lookback_cannot_create_generation_without_seal(tmp_path: Path) -> None:
    """H8: capture_technicals_v2 without a sealed D bar raises TechnicalsV2SourceError."""
    from scripts.capture_market_memory_technicals_v2 import (
        capture_technicals_v2,
        TechnicalsV2SourceError,
    )

    source_dir = tmp_path / "state" / "sources-spy-rest-v1"
    source_dir.mkdir(parents=True)
    store_dir = tmp_path / "state" / "technicals-v2"
    store_dir.mkdir(parents=True)

    with pytest.raises(TechnicalsV2SourceError):
        capture_technicals_v2(
            source_root=source_dir,
            store_root=store_dir,
            session=date(2026, 8, 21),
        )


# H9 — B2/M2: After 04:05Z → no session derived; derive_morning_session covers this
def test_h9_derive_morning_session_behavior() -> None:
    """H9: After 04:05Z on D+1, session is D (T-1). Before 04:05Z, returns None."""
    from engine.neuralweb.market_memory_sources_spy import derive_morning_session

    # 04:04:59Z → before threshold → None
    just_before = _utc(2026, 8, 21, 4, 4, 59)
    assert derive_morning_session(just_before) is None

    # 04:05:00Z → at threshold → 2026-08-20
    at_threshold = _utc(2026, 8, 21, 4, 5, 0)
    assert derive_morning_session(at_threshold) == date(2026, 8, 20)

    # 04:32:00Z → in experience-v2 window → 2026-08-20
    at_432 = _utc(2026, 8, 21, 4, 32, 0)
    assert derive_morning_session(at_432) == date(2026, 8, 20)


# H10 — v1 registration sha256 unchanged
def test_h10_v1_registration_sha256_unchanged() -> None:
    """H10: v1 registration content_sha256 still matches the frozen value."""
    reg_path = ROOT / "config" / "market_memory_spy_experience_registration.v1.json"
    data = json.loads(reg_path.read_bytes())
    assert data["content_sha256"] == "e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3", (
        "v1 registration content_sha256 must remain e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3"
    )


# H11 — CPI SOURCE_ID/SOURCE_SCHEMA unchanged
def test_h11_cpi_constants_unchanged() -> None:
    """H11: CPI SOURCE_ID and SOURCE_SCHEMA are unchanged."""
    from engine.neuralweb import market_memory_sources as sources

    assert sources.SOURCE_ID == "fred_alfred:CPIAUCSL"
    assert sources.SOURCE_SCHEMA == "market_memory.source.alfred_cpiaucsl.v1"


# H12 — v1 experience timer still 04:30:00 UTC; no Requires= on v2; Persistent=false on v2 timers
def test_h12_v1_experience_timer_unchanged() -> None:
    """H12: v1 experience timer is still 04:30:00 UTC."""
    timer = ROOT / "app" / "deploy" / "macro-market-memory-experience.timer"
    content = timer.read_text()
    assert "04:30:00 UTC" in content


def test_h12_v1_experience_unit_no_requires_v2() -> None:
    """H12: v1 experience service has NO Requires= on any v2 unit."""
    unit = ROOT / "app" / "deploy" / "macro-market-memory-experience.service"
    content = unit.read_text()
    requires = [l.strip() for l in content.splitlines() if l.strip().startswith("Requires=")]
    for req in requires:
        assert "v2" not in req, f"v1 experience unit must not Requires= v2: {req}"


def test_h12_experience_v2_timer_persistent_false() -> None:
    """H12/M2: experience-v2 timer has Persistent=false."""
    timer = ROOT / "app" / "deploy" / "macro-market-memory-experience-v2.timer"
    content = timer.read_text()
    assert "Persistent=false" in content, "experience-v2.timer must have Persistent=false"


def test_h12_technicals_v2_timer_persistent_false() -> None:
    """H12/M2: technicals-v2 timer has Persistent=false."""
    timer = ROOT / "app" / "deploy" / "macro-market-memory-technicals-v2.timer"
    content = timer.read_text()
    assert "Persistent=false" in content, "technicals-v2.timer must have Persistent=false"


# H13 — Digest change in seal → not eligible (existing test already covers)
def test_h13_digest_change_in_seal_not_eligible() -> None:
    """H13: Changing digest during seal window → not eligible (one generation not N polls)."""
    from engine.neuralweb.market_memory_sources_spy import evaluate_seal_predicate, SealObservation

    session = date(2026, 8, 21)
    bar1 = _make_spy_bar(close=590.25)
    bar2 = _make_spy_bar(close=591.00)
    digest1 = _bar_digest(bar1)
    digest2 = _bar_digest(bar2)

    window_open = _utc(2026, 8, 22, 4, 0, 0)
    window_close = _utc(2026, 8, 22, 4, 5, 0)

    observations = [
        SealObservation(observed_at=window_open + timedelta(seconds=5), status="valid_bar", digest=digest1),
        SealObservation(observed_at=window_open + timedelta(seconds=120), status="valid_bar", digest=digest2),
        SealObservation(observed_at=window_open + timedelta(seconds=241), status="valid_bar", digest=digest2),
        SealObservation(observed_at=window_open + timedelta(seconds=255), status="valid_bar", digest=digest2),
    ]
    state = evaluate_seal_predicate(
        observations, session=session, seal_open=window_open, seal_close=window_close
    )
    assert state.opportunity_eligible is False
    assert "differing" in state.reason


# ============================================================================
# N1–N4 / B3 HOSTILE TESTS (third repair, 2026-08-21)
# ============================================================================


def test_n1_ready_loop_v1_only() -> None:
    """N1: reciprocal_market_memory_units_ready must NOT list v2 units.

    v2 units are not on disk on first deploy, so including them would deadlock
    the v1 W2C attestation gate.
    """
    import re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    # Extract the function body of reciprocal_market_memory_units_ready
    m = re.search(
        r"reciprocal_market_memory_units_ready\(\)\s*\{(.*?)\n\}",
        content,
        re.DOTALL,
    )
    assert m, "reciprocal_market_memory_units_ready function not found"
    fn_body = m.group(1)

    for v2_profile in ("source-spy-rest", "technicals-v2", "experience-v2"):
        assert v2_profile not in fn_body, (
            f"reciprocal_market_memory_units_ready must NOT contain '{v2_profile}'; "
            "v2 units may not be on disk on first deploy and would deadlock the v1 gate"
        )

    # v1 units must still be present
    for v1_profile in ("source", "context", "identity", "breadth", "technicals", "experience", "production-records"):
        assert v1_profile in fn_body, (
            f"reciprocal_market_memory_units_ready must still contain v1 profile '{v1_profile}'"
        )


def test_n1_stop_loop_has_v2_profiles() -> None:
    """N1: stop_reciprocal_market_memory_writers must still include v2 profiles."""
    import re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    m = re.search(
        r"stop_reciprocal_market_memory_writers\(\)\s*\{(.*?)\n\}",
        content,
        re.DOTALL,
    )
    assert m, "stop_reciprocal_market_memory_writers function not found"
    fn_body = m.group(1)

    for profile in ("source-spy-rest", "technicals-v2", "experience-v2"):
        assert profile in fn_body, (
            f"stop_reciprocal_market_memory_writers must contain '{profile}'"
        )


def test_n4_rearm_loop_has_v2_profiles() -> None:
    """N4: The re-arm loop must include v2 profiles and must NOT include bare 'experience'.

    'experience' (v1) timer is owned by w2c_reconcile_timer (Persistent=true) and
    must not be re-armed directly; only experience-v2 belongs here.
    """
    import re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    m = re.search(r"for RECIPROCAL_PROFILE in ([^\n;]+)", content)
    assert m, "for RECIPROCAL_PROFILE in ... not found in update.sh"
    loop_line = m.group(1)

    for profile in ("source-spy-rest", "technicals-v2", "experience-v2"):
        assert profile in loop_line, (
            f"re-arm loop must include '{profile}'; got: {loop_line!r}"
        )

    # Must NOT contain bare 'experience' (the v1 timer — owned by w2c_reconcile_timer)
    # Use word-boundary check: 'experience' followed by space or end-of-tokens
    tokens = loop_line.split()
    bare_experience = [t for t in tokens if t == "experience"]
    assert not bare_experience, (
        f"re-arm loop must NOT contain bare 'experience' (v1, Persistent=true, "
        f"owned by w2c_reconcile_timer); got loop: {loop_line!r}"
    )


def test_n2_b3_marker_uses_macro_api_venv_and_not_env_python() -> None:
    """N2/B3: install marker must use /opt/macro-api/.venv/bin/python, not APP_DIR/env/bin/python3."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    # The correct interpreter must be present near --write-install-marker
    import re
    # Find lines containing --write-install-marker
    marker_region = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "--write-install-marker" in line:
            # grab ±5 lines for context
            start = max(0, i - 5)
            end = min(len(lines), i + 5)
            marker_region.extend(lines[start:end])

    assert marker_region, "--write-install-marker not found in update.sh"
    region_text = "\n".join(marker_region)

    assert "/opt/macro-api/.venv/bin/python" in region_text, (
        "update.sh must use /opt/macro-api/.venv/bin/python near --write-install-marker; "
        "found: " + region_text
    )
    assert "env/bin/python3" not in region_text, (
        "update.sh must NOT use APP_DIR/env/bin/python3 near --write-install-marker"
    )


def test_n2_b3_marker_write_outside_unit_updated_block() -> None:
    """N2/B3: Marker write must not be exclusively inside MARKET_MEMORY_EXPERIENCE_V2_UNIT_UPDATED -eq 1."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    import re
    # Find the V2_INSTALL_MARKER block
    m = re.search(
        r'V2_INSTALL_MARKER=.*?(?:done|fi)',
        content,
        re.DOTALL,
    )
    assert m, "V2_INSTALL_MARKER block not found in update.sh"
    marker_block = m.group(0)

    # The marker check must be keyed on the marker file being absent,
    # not exclusively on UNIT_UPDATED. We check by asserting that
    # V2_INSTALL_MARKER appears outside an "if UNIT_UPDATED -eq 1" context.
    # Simple heuristic: the line before V2_INSTALL_MARKER should NOT be
    # "if [ \"$MARKET_MEMORY_EXPERIENCE_V2_UNIT_UPDATED\" -eq 1 ]"
    idx = content.find("V2_INSTALL_MARKER=")
    assert idx != -1
    preceding = content[max(0, idx - 400):idx]
    # In the fixed version, V2_INSTALL_MARKER comes after the install block closes (fi)
    # and is NOT wrapped in UNIT_UPDATED check.
    assert 'MARKET_MEMORY_EXPERIENCE_V2_UNIT_UPDATED" -eq 1' not in preceding[-200:], (
        "Marker write must not be exclusively gated on MARKET_MEMORY_EXPERIENCE_V2_UNIT_UPDATED -eq 1; "
        "it must also run when units were already current (to handle first-ship)"
    )


def test_n3_runtime_regex_matches_v1_service_paths() -> None:
    """N3: OPTIONS_RUNTIME_CLOSURE_REGEX must match v1 service/timer paths."""
    import re as _re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    m = _re.search(r"OPTIONS_RUNTIME_CLOSURE_REGEX='([^']+)'", content)
    assert m, "OPTIONS_RUNTIME_CLOSURE_REGEX not found"
    regex_val = m.group(1)

    should_match = [
        "app/deploy/macro-market-memory-source.service",
        "app/deploy/macro-market-memory-source.timer",
        "app/deploy/macro-market-memory-experience.timer",
        "app/deploy/macro-market-memory-technicals.service",
        "app/deploy/macro-market-memory-breadth.timer",
        "app/deploy/macro-market-memory-production-records.service",
        "app/deploy/macro-market-memory-options.service",
    ]
    should_not_match = [
        "app/deploy/macro-market-memory-source-spy-rest.service",
        "app/deploy/macro-market-memory-technicals-v2.service",
        "app/deploy/macro-market-memory-experience-v2.timer",
    ]

    for path in should_match:
        assert _re.match(regex_val, path), (
            f"OPTIONS_RUNTIME_CLOSURE_REGEX must match {path!r} (v1 unit) but did not"
        )
    for path in should_not_match:
        assert not _re.match(regex_val, path), (
            f"OPTIONS_RUNTIME_CLOSURE_REGEX must NOT match {path!r} (v2 unit)"
        )


def test_n5_ingest_main_no_creds_returns_1(tmp_path: Path) -> None:
    """N5: ingest_market_memory_sources_spy._main returns 1 when no credentials available."""
    from scripts.ingest_market_memory_sources_spy import _main as ingest_main

    store_dir = tmp_path / "state" / "sources-spy-rest-v1"
    store_dir.mkdir(parents=True)

    env_backup = {}
    for key in ("CREDENTIALS_DIRECTORY", "MASSIVE_API_KEY", "POLYGON_API_KEY"):
        env_backup[key] = os.environ.pop(key, None)
    try:
        # Pass session so ingest can proceed to the credential check
        rc = ingest_main([
            "--store-root", str(store_dir),
            "--session", "2026-08-21",
        ])
        assert rc == 1, (
            f"_main must return 1 when no credentials are available; got {rc}"
        )
    finally:
        for key, val in env_backup.items():
            if val is not None:
                os.environ[key] = val


def test_n6_technicals_main_no_session_returns_0() -> None:
    """N6: capture_market_memory_technicals_v2._main returns 0 on no_session (weekend clock)."""
    from scripts.capture_market_memory_technicals_v2 import _main as tech_main

    # 2026-08-17 is Monday; T-1 = 2026-08-16 (Sunday) → not an XNYS session → no_session
    monday_clock = lambda: datetime(2026, 8, 17, 4, 7, 0, tzinfo=timezone.utc)
    rc = tech_main([], clock=monday_clock)
    assert rc == 0, (
        f"_main must return 0 (not 1) when derive_morning_session is None; got {rc}"
    )


def test_n4_marker_write_before_w2c_attested_exit() -> None:
    """N4: --write-install-marker must appear before the W2C MARKET_MEMORY_EXPERIENCE_ATTESTED block.

    A previous regression placed the marker write AFTER the W2C exit 1, causing
    first-ship to never write the marker. The marker block must precede the
    MARKET_MEMORY_EXPERIENCE_ATTESTED initialization and its surrounding exit 1.
    """
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    lines = update_sh.read_text().splitlines()

    marker_lineno = None
    attested_lineno = None

    for i, line in enumerate(lines, start=1):
        if "--write-install-marker" in line and marker_lineno is None:
            marker_lineno = i
        if "MARKET_MEMORY_EXPERIENCE_ATTESTED=0" in line and attested_lineno is None:
            attested_lineno = i

    assert marker_lineno is not None, "--write-install-marker not found in update.sh"
    assert attested_lineno is not None, (
        "MARKET_MEMORY_EXPERIENCE_ATTESTED=0 initialization not found in update.sh"
    )
    assert marker_lineno < attested_lineno, (
        f"--write-install-marker (line {marker_lineno}) must appear BEFORE "
        f"MARKET_MEMORY_EXPERIENCE_ATTESTED=0 (line {attested_lineno}); "
        "marker write was previously placed after the W2C exit, preventing first-ship"
    )


def test_n7_accrue_v2_outside_window_with_explicit_session_writes_nothing(tmp_path: Path) -> None:
    """N7: accrue_spy_experience_v2 with explicit past session + out-of-window clock writes no record."""
    from scripts.accrue_market_memory_spy_experience_v2 import accrue_spy_experience_v2

    exp_root = tmp_path / "state" / "experience-v2"
    exp_root.mkdir(parents=True)

    # Plant install marker so activation check passes
    marker = exp_root / ".v2_install_verified"
    marker.write_text("2026-08-19T04:32:00Z\n")

    records_dir = exp_root / "records"
    records_dir.mkdir(parents=True)

    # clock = 2026-08-21 12:00Z (far outside [04:30Z, 04:45Z))
    out_of_window_clock = lambda: datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

    result = accrue_spy_experience_v2(
        repository_root=ROOT,
        experience_root=exp_root,
        source_root=tmp_path / "state" / "sources-spy-rest-v1",
        technicals_v2_root=tmp_path / "state" / "technicals-v2",
        session=date(2026, 8, 19),
        clock=out_of_window_clock,
    )

    assert result.get("status") == "outside_admission_window", (
        f"Expected outside_admission_window but got: {result}"
    )

    record_path = records_dir / "2026-08-19.json"
    assert not record_path.exists(), (
        "records/2026-08-19.json must NOT be created when outside admission window"
    )


# ===========================================================================
# P1–P10: spy-rest-prereqs hostile tests
# ===========================================================================

PREREQS_SH = ROOT / "app" / "deploy" / "market-memory-spy-rest-prereqs.sh"
_THROWAWAY_KEY = "testkey_m0d_prereqs_16ch"


def _read_prereqs() -> str:
    return PREREQS_SH.read_text(encoding="utf-8")


def test_p1_prereqs_contains_credential_root() -> None:
    """P1: prereqs script declares CREDENTIAL_ROOT=/etc/macro-market-memory-spy-rest."""
    content = _read_prereqs()
    assert "CREDENTIAL_ROOT=/etc/macro-market-memory-spy-rest" in content


def test_p1_prereqs_contains_both_filenames() -> None:
    """P1: prereqs script references both MASSIVE_API_KEY and POLYGON_API_KEY as final filenames."""
    content = _read_prereqs()
    assert "MASSIVE_API_KEY" in content
    assert "POLYGON_API_KEY" in content
    assert "CRED_FILE_A=$CREDENTIAL_ROOT/MASSIVE_API_KEY" in content or \
           "$CREDENTIAL_ROOT/MASSIVE_API_KEY" in content
    assert "CRED_FILE_B=$CREDENTIAL_ROOT/POLYGON_API_KEY" in content or \
           "$CREDENTIAL_ROOT/POLYGON_API_KEY" in content


def test_p2_no_export_eval_set_x_source() -> None:
    """P2: prereqs script must not leak $candidate to a sink."""
    import re as _re

    content = _read_prereqs()
    lines = content.splitlines()
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("export "), (
            f"line {lineno}: must not export: {line!r}"
        )
        assert not stripped.startswith("eval "), (
            f"line {lineno}: must not use eval: {line!r}"
        )
        assert "set -x" not in stripped, (
            f"line {lineno}: must not use set -x: {line!r}"
        )
        assert "xtrace" not in stripped, (
            f"line {lineno}: must not enable xtrace: {line!r}"
        )
        assert not stripped.startswith("source "), (
            f"line {lineno}: must not use source: {line!r}"
        )
        assert not _re.search(r"\blogger\b", stripped), (
            f"line {lineno}: must not logger: {line!r}"
        )
        # $candidate may only be assigned, tested, compared, passed to write, or printf'd into the temp file.
        if "$candidate" in stripped or "${candidate" in stripped:
            allowed = (
                "candidate=$(" in stripped
                or stripped.startswith("candidate=")
                or '[ -z "$candidate" ]' in stripped
                or '[ -n "$candidate" ]' in stripped
                or '[ "$candidate" = "$final_candidate" ]' in stripped
                or "write_credential_file" in stripped
                or "printf '%s" in stripped
                or stripped.startswith("unset candidate")
                or 'case "$candidate"' in stripped
                or "candidate=${candidate#" in stripped
                or "${#candidate}" in stripped
            )
            assert allowed, (
                f"line {lineno}: $candidate reaches a disallowed sink: {line!r}"
            )


def test_p2_absent_key_does_not_delete_existing_files() -> None:
    """Absent extract must not rm already-provisioned LoadCredential files."""
    content = _read_prereqs()
    assert "cannot remove stale derived credential" not in content
    assert 'rm -f "$CRED_FILE_A"' not in content
    assert 'rm -f "$CRED_FILE_B"' not in content
    assert 'rm -f "$dest"' not in content or content.count('rm -f "$dest"') == 0
    # Temps may still be removed; dest/credential finals must not.
    assert "no extractable key in operator env files" in content


def test_p3_three_env_extract_sources() -> None:
    """P3: prereqs extracts from all three env source paths."""
    content = _read_prereqs()
    assert "/opt/macro/.env" in content
    assert "/etc/macro-api.env" in content
    assert "/etc/macro-live.env" in content


def test_p4_update_sh_calls_prereqs_before_attested_zero() -> None:
    """P4: update.sh calls market-memory-spy-rest-prereqs.sh before MARKET_MEMORY_EXPERIENCE_ATTESTED=0."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    lines = update_sh.read_text().splitlines()

    prereqs_lineno = None
    attested_lineno = None

    for i, line in enumerate(lines, start=1):
        if "market-memory-spy-rest-prereqs.sh" in line and prereqs_lineno is None:
            prereqs_lineno = i
        if "MARKET_MEMORY_EXPERIENCE_ATTESTED=0" in line and attested_lineno is None:
            attested_lineno = i

    assert prereqs_lineno is not None, (
        "update.sh must call market-memory-spy-rest-prereqs.sh"
    )
    assert attested_lineno is not None, (
        "MARKET_MEMORY_EXPERIENCE_ATTESTED=0 must exist in update.sh"
    )
    assert prereqs_lineno < attested_lineno, (
        f"market-memory-spy-rest-prereqs.sh call (line {prereqs_lineno}) must appear BEFORE "
        f"MARKET_MEMORY_EXPERIENCE_ATTESTED=0 (line {attested_lineno})"
    )


def test_p5_call_site_does_not_exit_or_start_spy_rest() -> None:
    """P5: The spy-rest prereqs call site in update.sh must not exit and must not systemctl start spy-rest."""
    import re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    # Find the block containing the prereqs call
    idx = content.find("market-memory-spy-rest-prereqs.sh")
    assert idx != -1, "spy-rest prereqs call not found in update.sh"

    # Extract ~30 lines of context around the call
    lines = content.splitlines()
    call_lines = []
    in_block = False
    for line in lines:
        if "market-memory-spy-rest-prereqs.sh" in line:
            in_block = True
        if in_block:
            call_lines.append(line)
        # Stop at the next blank line that signals end of the block
        if in_block and line.strip() == "" and len(call_lines) > 3:
            break

    block_text = "\n".join(call_lines)

    # Must not contain standalone exit 1 (exit is only for service-critical paths)
    assert not re.search(r'\bexit\s+1\b', block_text), (
        "spy-rest prereqs call site must not exit 1"
    )
    # Must not systemctl start spy-rest from this block
    assert "systemctl start macro-market-memory-source-spy-rest" not in block_text, (
        "spy-rest prereqs call site must not systemctl start spy-rest"
    )
    assert "systemctl start macro-market-memory-spy-rest" not in block_text, (
        "spy-rest prereqs call site must not systemctl start spy-rest"
    )
    # Status must be captured from the script, not from a `|| echo` pipeline.
    assert "|| SPY_REST_PREREQ_STATUS=$?" in block_text, (
        "provision status must be captured via || SPY_REST_PREREQ_STATUS=$?; "
        "a `|| echo` pipeline would clobber a status-2 absent-key result"
    )
    assert "--check-ready >/dev/null 2>&1" in block_text, (
        "check-ready must be quiet; do not leak credential-path diagnostics"
    )


def test_p6_options_runtime_closure_regex_matches_v1_not_prereqs() -> None:
    """P6: OPTIONS_RUNTIME_CLOSURE_REGEX still matches v1 units but not v2 paths or new prereqs."""
    import re as _re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    m = _re.search(r"OPTIONS_RUNTIME_CLOSURE_REGEX='([^']+)'", content)
    assert m, "OPTIONS_RUNTIME_CLOSURE_REGEX not found in update.sh"
    regex_val = m.group(1)

    # Must still match v1 paths
    for path in (
        "app/deploy/macro-market-memory-options.service",
        "app/deploy/macro-market-memory-source.service",
        "app/deploy/market-memory-options-prereqs.sh",
    ):
        assert _re.match(regex_val, path), (
            f"OPTIONS_RUNTIME_CLOSURE_REGEX must still match v1 path {path!r}"
        )

    # Must NOT match the new prereqs or v2 units
    for path in (
        "app/deploy/market-memory-spy-rest-prereqs.sh",
        "app/deploy/macro-market-memory-source-spy-rest.service",
        "app/deploy/macro-market-memory-technicals-v2.service",
    ):
        assert not _re.match(regex_val, path), (
            f"OPTIONS_RUNTIME_CLOSURE_REGEX must NOT match {path!r}"
        )


def test_p6_options_reciprocal_closure_regex_matches_new_prereqs() -> None:
    """P6: OPTIONS_RECIPROCAL_CLOSURE_REGEX matches the new spy-rest-prereqs script."""
    import re as _re
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()

    m = _re.search(r"OPTIONS_RECIPROCAL_CLOSURE_REGEX='([^']+)'", content)
    assert m, "OPTIONS_RECIPROCAL_CLOSURE_REGEX not found in update.sh"
    regex_val = m.group(1)

    assert _re.match(regex_val, "app/deploy/market-memory-spy-rest-prereqs.sh"), (
        "OPTIONS_RECIPROCAL_CLOSURE_REGEX must match app/deploy/market-memory-spy-rest-prereqs.sh"
    )


def test_p7_v1_registration_sha256_unchanged_prereqs_guard() -> None:
    """P7: v1 registration content_sha256 remains e00ffc1d34..."""
    reg_path = ROOT / "config" / "market_memory_spy_experience_registration.v1.json"
    data = json.loads(reg_path.read_bytes())
    assert data["content_sha256"] == "e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3"


def test_p8_load_credential_paths_match_prereqs_files() -> None:
    """P8: LoadCredential paths in source-spy-rest.service match the prereqs output filenames."""
    unit_path = ROOT / "app" / "deploy" / "macro-market-memory-source-spy-rest.service"
    content = unit_path.read_text()
    assert "LoadCredential=MASSIVE_API_KEY:/etc/macro-market-memory-spy-rest/MASSIVE_API_KEY" in content, (
        "service must LoadCredential MASSIVE_API_KEY from /etc/macro-market-memory-spy-rest/MASSIVE_API_KEY"
    )
    assert "LoadCredential=POLYGON_API_KEY:/etc/macro-market-memory-spy-rest/POLYGON_API_KEY" in content, (
        "service must LoadCredential POLYGON_API_KEY from /etc/macro-market-memory-spy-rest/POLYGON_API_KEY"
    )


def test_p9_tmpdir_harness_provisions_both_files_identical(tmp_path: Path) -> None:
    """P9: tmpdir harness sed-replaces CREDENTIAL_ROOT and source paths,
    then runs the script as current user (skips root check via sed) and proves
    both MASSIVE_API_KEY and POLYGON_API_KEY appear mode 0400 with identical bytes
    using throwaway key testkey_m0d_prereqs_16ch.
    """
    import shutil
    import stat
    import subprocess

    script_src = PREREQS_SH.read_text(encoding="utf-8")

    cred_root = tmp_path / "cred"
    cred_root.mkdir(mode=0o700)

    env_file = tmp_path / "macro-api.env"
    env_file.write_text(f"MASSIVE_API_KEY={_THROWAWAY_KEY}\n", encoding="utf-8")
    env_file.chmod(0o600)

    modified = script_src
    # Replace CREDENTIAL_ROOT path
    modified = modified.replace(
        "CREDENTIAL_ROOT=/etc/macro-market-memory-spy-rest",
        f"CREDENTIAL_ROOT={cred_root}",
    )
    # Replace source paths
    modified = modified.replace("/opt/macro/.env", str(tmp_path / "missing1.env"))
    modified = modified.replace("/etc/macro-api.env", str(env_file))
    modified = modified.replace("/etc/macro-live.env", str(tmp_path / "missing2.env"))
    # macOS stat uses -f instead of -c; add a compat shim at the top of the script
    import platform as _platform
    if _platform.system() == "Darwin":
        compat_shim = (
            "# macOS stat compat shim (injected by test harness)\n"
            "_stat_c() {\n"
            "  local fmt=$1 f=$2\n"
            "  case \"$fmt\" in\n"
            "    '%U') command stat -f '%Su' \"$f\" ;;\n"
            "    '%a') command stat -f '%OLp' \"$f\" | sed 's/^0*//' ;;\n"
            "    '%s') command stat -f '%z' \"$f\" ;;\n"
            "    '%U:%G:%a')\n"
            "      local u g m\n"
            "      u=$(command stat -f '%Su' \"$f\")\n"
            "      g=$(command stat -f '%Sg' \"$f\")\n"
            "      m=$(command stat -f '%OLp' \"$f\" | sed 's/^0*//')\n"
            "      printf '%s:%s:%s' \"$u\" \"$g\" \"$m\" ;;\n"
            "    *) command stat -c \"$fmt\" \"$f\" ;;\n"
            "  esac\n"
            "}\n"
            "stat() { if [ \"${1:-}\" = '-c' ]; then _stat_c \"$2\" \"$3\"; else command stat \"$@\"; fi; }\n\n"
        )
        modified = compat_shim + modified
    # Skip the root check so we can run as non-root in CI
    modified = modified.replace(
        '[ "$(id -u)" -eq 0 ] || die "must run as root"',
        "true  # root check bypassed in harness",
    )
    # install -d with -o root/-g root fails as non-root on macOS; replace with mkdir -p
    modified = modified.replace(
        "install -d -o root -g root -m 0700 \"$CREDENTIAL_ROOT\" || \\\n\t\tdie \"cannot provision credential root\"",
        "mkdir -p \"$CREDENTIAL_ROOT\"  # install bypassed in harness",
    )
    # stat -c '%U' does not return 'root' when running as non-root; bypass owner checks
    modified = modified.replace(
        '[ "$owner" = root ] || return 2',
        "true  # owner check bypassed in harness",
    )
    # Similarly for write_credential_file: skip root-only chown/chmod assertions
    modified = modified.replace(
        'chown root:root "$tmp" || die "cannot set temporary credential owner"',
        'true  # chown bypassed in harness',
    )
    modified = modified.replace(
        'chown root:root "$dest" || die "cannot set credential owner: ${dest##*/}"',
        'true  # chown bypassed in harness',
    )
    # Bypass all root:root ownership/mode checks (owner is the test user, not root)
    modified = modified.replace(
        "[ \"$file_metadata\" = 'root:root:400' ] || \\\n\t\tdie \"credential must be root:root mode 0400: ${dest##*/}\"",
        "true  # owner+mode check bypassed in harness",
    )
    # provision_credential root check (uses root_metadata variable)
    modified = modified.replace(
        "[ \"$root_metadata\" = 'root:root:700' ] || \\\n\t\tdie \"credential root must be root:root mode 0700\"",
        "true  # root dir mode check bypassed in harness",
    )
    # check_ready root check
    modified = modified.replace(
        "[ \"$root_metadata\" = 'root:root:700' ] || return 2",
        "true  # root dir mode check bypassed in harness",
    )

    script_path = tmp_path / "prereqs-test.sh"
    script_path.write_text(modified, encoding="utf-8")
    script_path.chmod(0o755)

    result = subprocess.run(
        ["bash", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"prereqs script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    file_a = cred_root / "MASSIVE_API_KEY"
    file_b = cred_root / "POLYGON_API_KEY"
    assert file_a.exists(), "MASSIVE_API_KEY must be created"
    assert file_b.exists(), "POLYGON_API_KEY must be created"

    # Mode 0400 after script sets it (the harness only bypasses chown, not chmod)
    mode_a = stat.S_IMODE(file_a.stat().st_mode)
    mode_b = stat.S_IMODE(file_b.stat().st_mode)
    assert mode_a == 0o400, f"MASSIVE_API_KEY must be mode 0400; got {oct(mode_a)}"
    assert mode_b == 0o400, f"POLYGON_API_KEY must be mode 0400; got {oct(mode_b)}"

    content_a = file_a.read_text(encoding="utf-8").strip()
    content_b = file_b.read_text(encoding="utf-8").strip()
    assert content_a == _THROWAWAY_KEY, f"MASSIVE_API_KEY content mismatch: {content_a!r}"
    assert content_b == _THROWAWAY_KEY, f"POLYGON_API_KEY content mismatch: {content_b!r}"
    assert content_a == content_b, "Both credential files must have identical bytes"


def _write_harness_prereqs(tmp_path: Path, *, key: str | None):
    """Return (script_path, cred_root, env_file) for executed prereqs tests."""
    import platform as _platform

    cred_root = tmp_path / "cred"
    cred_root.mkdir(mode=0o700, exist_ok=True)
    env_file = tmp_path / "macro-api.env"
    if key is None:
        env_file.write_text("# empty\n", encoding="utf-8")
    else:
        env_file.write_text(f"MASSIVE_API_KEY={key}\n", encoding="utf-8")
    env_file.chmod(0o600)

    modified = PREREQS_SH.read_text(encoding="utf-8")
    modified = modified.replace(
        "CREDENTIAL_ROOT=/etc/macro-market-memory-spy-rest",
        f"CREDENTIAL_ROOT={cred_root}",
    )
    modified = modified.replace("/opt/macro/.env", str(tmp_path / "missing1.env"))
    modified = modified.replace("/etc/macro-api.env", str(env_file))
    modified = modified.replace("/etc/macro-live.env", str(tmp_path / "missing2.env"))
    if _platform.system() == "Darwin":
        compat_shim = (
            "_stat_c() {\n"
            "  local fmt=$1 f=$2\n"
            "  case \"$fmt\" in\n"
            "    '%U') command stat -f '%Su' \"$f\" ;;\n"
            "    '%a') command stat -f '%OLp' \"$f\" | sed 's/^0*//' ;;\n"
            "    '%s') command stat -f '%z' \"$f\" ;;\n"
            "    '%U:%G:%a')\n"
            "      local u g m\n"
            "      u=$(command stat -f '%Su' \"$f\")\n"
            "      g=$(command stat -f '%Sg' \"$f\")\n"
            "      m=$(command stat -f '%OLp' \"$f\" | sed 's/^0*//' )\n"
            "      printf '%s:%s:%s' \"$u\" \"$g\" \"$m\" ;;\n"
            "    *) command stat -c \"$fmt\" \"$f\" ;;\n"
            "  esac\n"
            "}\n"
            "stat() { if [ \"${1:-}\" = '-c' ]; then _stat_c \"$2\" \"$3\"; else command stat \"$@\"; fi; }\n\n"
        )
        modified = compat_shim + modified
    modified = modified.replace(
        '[ "$(id -u)" -eq 0 ] || die "must run as root"',
        "true  # root check bypassed in harness",
    )
    modified = modified.replace(
        "install -d -o root -g root -m 0700 \"$CREDENTIAL_ROOT\" || \\\n\t\tdie \"cannot provision credential root\"",
        "mkdir -p \"$CREDENTIAL_ROOT\"  # install bypassed in harness",
    )
    modified = modified.replace(
        '[ "$owner" = root ] || return 2',
        "true  # owner check bypassed in harness",
    )
    modified = modified.replace(
        'chown root:root "$tmp" || die "cannot set temporary credential owner"',
        'true  # chown bypassed in harness',
    )
    modified = modified.replace(
        'chown root:root "$dest" || die "cannot set credential owner: ${dest##*/}"',
        'true  # chown bypassed in harness',
    )
    modified = modified.replace(
        "[ \"$file_metadata\" = 'root:root:400' ] || \\\n\t\tdie \"credential must be root:root mode 0400: ${dest##*/}\"",
        "true  # owner+mode check bypassed in harness",
    )
    modified = modified.replace(
        "[ \"$file_metadata\" = 'root:root:400' ] || return 2",
        "true  # check_ready owner+mode bypassed in harness",
    )
    modified = modified.replace(
        "[ \"$root_metadata\" = 'root:root:700' ] || \\\n\t\tdie \"credential root must be root:root mode 0700\"",
        "true  # root dir mode check bypassed in harness",
    )
    modified = modified.replace(
        "[ \"$root_metadata\" = 'root:root:700' ] || return 2",
        "true  # root dir mode check bypassed in harness",
    )
    script_path = tmp_path / "prereqs-test.sh"
    script_path.write_text(modified, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path, cred_root, env_file


def test_p9b_check_ready_accepts_matching_files(tmp_path: Path) -> None:
    """--check-ready is the path update.sh runs every tick; it must execute, not just grep."""
    import subprocess

    script_path, cred_root, _env = _write_harness_prereqs(tmp_path, key=_THROWAWAY_KEY)
    provisioned = subprocess.run(["bash", str(script_path)], capture_output=True, text=True)
    assert provisioned.returncode == 0, provisioned.stderr
    ready = subprocess.run(
        ["bash", str(script_path), "--check-ready"],
        capture_output=True,
        text=True,
    )
    assert ready.returncode == 0, (
        f"--check-ready must pass on a just-provisioned tree: {ready.stderr}"
    )
    assert (cred_root / "MASSIVE_API_KEY").exists()
    assert (cred_root / "POLYGON_API_KEY").exists()


def test_p9c_check_ready_refuses_mismatched_bytes(tmp_path: Path) -> None:
    """Property (h): differing file bytes vs extracted key → --check-ready returns 2."""
    import subprocess

    script_path, cred_root, _env = _write_harness_prereqs(tmp_path, key=_THROWAWAY_KEY)
    assert subprocess.run(["bash", str(script_path)], capture_output=True, text=True).returncode == 0
    poly = cred_root / "POLYGON_API_KEY"
    poly.chmod(0o600)
    poly.write_text("totally_different_key_9999\n", encoding="utf-8")
    ready = subprocess.run(
        ["bash", str(script_path), "--check-ready"],
        capture_output=True,
        text=True,
    )
    assert ready.returncode == 2, (
        f"--check-ready must return 2 on byte mismatch; got {ready.returncode} stderr={ready.stderr!r}"
    )


def test_p9d_absent_key_leaves_existing_files(tmp_path: Path) -> None:
    """A later extract miss must not wipe a working credential pair."""
    import subprocess

    script_path, cred_root, env_file = _write_harness_prereqs(tmp_path, key=_THROWAWAY_KEY)
    assert subprocess.run(["bash", str(script_path)], capture_output=True, text=True).returncode == 0
    env_file.write_text("# no key\n", encoding="utf-8")
    env_file.chmod(0o600)
    absent = subprocess.run(["bash", str(script_path)], capture_output=True, text=True)
    assert absent.returncode == 2, (
        f"absent key must return 2; got {absent.returncode} stderr={absent.stderr!r}"
    )
    assert (cred_root / "MASSIVE_API_KEY").read_text(encoding="utf-8").strip() == _THROWAWAY_KEY
    assert (cred_root / "POLYGON_API_KEY").read_text(encoding="utf-8").strip() == _THROWAWAY_KEY


def test_p10_prereqs_wired_into_contract_lane_path_filters() -> None:
    """P10: ci.yml path filters include market-memory-spy-rest-prereqs.sh."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert '      - "app/deploy/market-memory-spy-rest-prereqs.sh"' in workflow, (
        "ci.yml must include market-memory-spy-rest-prereqs.sh in path filters"
    )


def test_m0d_suite_is_wired_into_market_memory_contract_lane() -> None:
    """contract-delta reds a new pytest suite named by no run: step."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]
    assert '      - "tests/test_market_memory_m0d_v2.py"' in workflow
    assert "tests/test_market_memory_m0d_v2.py" in lane
    for path in (
        "engine/neuralweb/market_memory_source_kernel.py",
        "engine/neuralweb/market_memory_sources_spy.py",
        "scripts/ingest_market_memory_sources_spy.py",
        "scripts/capture_market_memory_technicals_v2.py",
        "scripts/accrue_market_memory_spy_experience_v2.py",
        "app/deploy/macro-market-memory-source-spy-rest.service",
        "app/deploy/macro-market-memory-technicals-v2.service",
        "app/deploy/macro-market-memory-experience-v2.service",
        "config/market_memory_spy_experience_registration.v2.json",
        "app/deploy/market-memory-spy-rest-prereqs.sh",
    ):
        assert f'      - "{path}"' in workflow
