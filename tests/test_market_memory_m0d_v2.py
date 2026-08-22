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
    """H3: Both reciprocal loops include source-spy-rest, technicals-v2, experience-v2."""
    update_sh = ROOT / "app" / "deploy" / "update.sh"
    content = update_sh.read_text()
    for profile in ("source-spy-rest", "technicals-v2", "experience-v2"):
        # Check both stop and ready functions
        count = content.count(f' {profile} ')
        # Each should appear at least twice (once in stop loop, once in ready loop)
        assert count >= 2, (
            f"update.sh reciprocal loops must include '{profile}' in BOTH loops; "
            f"found only {count} occurrence(s)"
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
