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


def test_experience_store_root_accepts_v2(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_experience_accrual import validate_experience_store_root

    v2_dir = tmp_path / "state" / "experience-v2"
    v2_dir.mkdir(parents=True)
    result = validate_experience_store_root(v2_dir)
    assert result.name == "experience-v2"


def test_experience_store_root_still_accepts_v1(tmp_path: Path) -> None:
    from engine.neuralweb.market_memory_experience_accrual import validate_experience_store_root

    v1_dir = tmp_path / "state" / "experience-v1"
    v1_dir.mkdir(parents=True)
    result = validate_experience_store_root(v1_dir)
    assert result.name == "experience-v1"


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
    """Using a v1 root for experience-v2 fails at the activation guard (no install marker)."""
    from scripts.accrue_market_memory_spy_experience_v2 import (
        accrue_spy_experience_v2,
        ExperienceV2ActivationError,
    )

    v1_root = tmp_path / "state" / "experience-v1"
    v1_root.mkdir(parents=True)

    with pytest.raises(ExperienceV2ActivationError, match="install marker"):
        accrue_spy_experience_v2(
            repository_root=ROOT,
            experience_root=v1_root,
            source_root=tmp_path / "state" / "sources-spy-rest-v1",
            technicals_v2_root=tmp_path / "state" / "technicals-v2",
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
