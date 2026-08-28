"""Construction, causality, lifecycle, and authority fences for CR1/CD1/AF1."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import personality_challenge_resilience as cr1
from engine import personality_crowding_hazard as cd1
from engine import personality_flow_absorption as af1
from engine import personality_followon_common as common
from scripts.research import freeze_pss_followon_gates as freezer


MODULES = (cr1, cd1, af1)

# The label vocabulary is part of each frozen construction — a lane may never
# emit a group outside its own tuple, and the state ledger counts each by name.
LEDGER_GROUPS = {
    cr1.PROGRAM_ID: (
        "resilient_leader",
        "challenged_control",
        "failed_hold_diagnostic",
    ),
    cd1.PROGRAM_ID: (
        "crowding_hazard",
        "uncrowded_control",
        "mixed_diagnostic",
    ),
    af1.PROGRAM_ID: (
        "flow_witness",
        "leader_flow_control",
        "low_activity_diagnostic",
        "missing_flow_diagnostic",
    ),
}

# Per-module launch-row fields beyond the shared CR1/CD1/AF1 registration shape. AF1's
# writer deliberately stamps an extra frozen-membership hash the other two lanes never
# modelled (engine/personality_flow_absorption.py:363) — it authenticates which FINRA
# prefix rows AF1's construction is frozen against, the same role construction_sha256
# plays for the graph shape. CR1/CD1 carry none, so their launch row is the bare shared
# shape unchanged.
EXTRA_LAUNCH_FIELDS = {
    cr1.PROGRAM_ID: {},
    cd1.PROGRAM_ID: {},
    af1.PROGRAM_ID: {"finra_prefix_sha256": af1.FINRA_PREFIX_SHA256},
}


def _copy_registration(root: Path, module) -> None:
    target = root / "personality_timing"
    target.mkdir(parents=True, exist_ok=True)
    source = Path("data/personality_timing")
    for name in (
        "relief_hazard_manifest_v1.json",
        "relief_hazard_membership_v1.json",
        module.manifest_path().name,
    ):
        shutil.copyfile(source / name, target / name)


def _event(module, *, action_date: str, group: str) -> dict:
    return {
        "kind": "event",
        "schema": module.LEDGER_SCHEMA,
        "program_id": module.PROGRAM_ID,
        "family": module.FAMILY,
        "construction_id": module.CONSTRUCTION_ID,
        "construction_sha256": module.EXPECTED_CONSTRUCTION_SHA256,
        "membership_sha256": module.EXPECTED_MEMBERSHIP_SHA256,
        "authority": dict(module.AUTHORITY),
        "source_action_date": action_date,
        "sym": "TEST",
        "sector": "Information Technology",
        "anchor_date": action_date,
        "formation_confirm": action_date,
        "action_date": action_date,
        "action_close": 100.0,
        "atr_anchor": 2.0,
        "reference_low": 90.0,
        "severity_band": "p2",
        "delay_band": "d1",
        "group": group,
        "grade": None,
        "grade_as_of": None,
    }


def _events(root: Path, module) -> list[dict]:
    return common.read_events(
        module.ledger_path(root),
        schema=module.LEDGER_SCHEMA,
        program_id=module.PROGRAM_ID,
    )


def _committed_rows(module) -> list[dict]:
    return [
        json.loads(line)
        for line in module.ledger_path().read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def test_frozen_registrations_and_committed_ledgers_preserve_launch():
    """Registrations stay frozen; an accrued ledger keeps its launch fences.

    CR1/CD1/AF1 are prospective-only accrual lanes: each charter §2 says "the
    ledger launches empty", and nightly is the sole advancer. A ledger file
    therefore APPEARS the first night a lawful post-cutoff source resolves —
    CD1 accrued 7 rows on 2026-08-06 off 7 eligible RH1 actions, while CR1
    (awaiting_challenge_window) and AF1 (downstream of CR1 leaders) have not
    reached their windows yet. Absence of the file was only ever a proxy for
    the real contract, and it expires on first lawful accrual.

    What must hold forever is the launch record and the fences: zero rows at
    launch, no backfill on either date, frozen construction and membership
    hashes, the frozen label vocabulary, and no authority. RH1 — the launched
    sibling on the same charter shape — made this exact transition in #4031
    (`test_committed_launch_is_zero_event_and_has_absolute_authority_fences`
    -> `test_committed_ledger_preserves_launch_and_absolute_authority_fences`);
    this mirrors it for the three follow-ons and holds in both states, so the
    guard no longer re-reds as CR1 and AF1 accrue in turn.
    """
    for module in MODULES:
        registration = module.load_registration()
        assert registration is not None
        manifest = registration["manifest"]
        assert manifest["construction_sha256"] == module.EXPECTED_CONSTRUCTION_SHA256
        assert common.canonical_sha256(manifest["construction"]) == (
            module.EXPECTED_CONSTRUCTION_SHA256
        )
        assert manifest["authority"] == common.AUTHORITY
        assert manifest["not_before_session"] == common.NOT_BEFORE_SESSION

        groups = LEDGER_GROUPS[module.PROGRAM_ID]
        state = json.loads(module.state_path().read_text(encoding="utf-8"))
        assert state["schema"] == module.STATE_SCHEMA
        assert state["program_id"] == module.PROGRAM_ID
        assert state["family"] == module.FAMILY
        assert state["status"] == "prospective_accrual_only"
        assert state["not_before_session"] == common.NOT_BEFORE_SESSION
        assert state["construction_sha256"] == module.EXPECTED_CONSTRUCTION_SHA256
        assert state["authority"] == common.AUTHORITY
        assert state["consumers"] == []
        assert state["decision_read"]["sole_read_executed"] is False

        if not module.ledger_path().exists():
            # Registered but nothing eligible has resolved yet — still lawful.
            assert state["ledger"]["events"] == 0
            continue

        rows = _committed_rows(module)
        assert rows
        launch, *events = rows
        expected_launch = {
            "kind": "registration",
            "schema": module.LEDGER_SCHEMA,
            "program_id": module.PROGRAM_ID,
            "family": module.FAMILY,
            "manifest_sha256": module.EXPECTED_MANIFEST_SHA256,
            "membership_sha256": module.EXPECTED_MEMBERSHIP_SHA256,
            "construction_sha256": module.EXPECTED_CONSTRUCTION_SHA256,
            "not_before_session": common.NOT_BEFORE_SESSION,
            "event_rows_at_launch": 0,
            "authority": dict(common.AUTHORITY),
            **EXTRA_LAUNCH_FIELDS[module.PROGRAM_ID],
        }
        assert launch == expected_launch
        for event in events:
            assert event["kind"] == "event"
            assert event["schema"] == module.LEDGER_SCHEMA
            assert event["program_id"] == module.PROGRAM_ID
            assert event["family"] == module.FAMILY
            assert event["construction_id"] == module.CONSTRUCTION_ID
            assert event["construction_sha256"] == module.EXPECTED_CONSTRUCTION_SHA256
            assert event["membership_sha256"] == module.EXPECTED_MEMBERSHIP_SHA256
            # Prospective firewall on both dates: the RH1 source action that
            # seeded the row and the lane's own action must clear the cutoff.
            assert event["source_action_date"] > common.NOT_BEFORE_SESSION
            assert event["action_date"] > common.NOT_BEFORE_SESSION
            assert event["group"] in groups
            assert event["authority"] == common.AUTHORITY

        counts = {group: sum(row["group"] == group for row in events) for group in groups}
        matured = sum(row.get("grade") is not None for row in events)
        action_dates = sorted(row["action_date"] for row in events)
        assert state["registration_ok"] is True
        assert state["ledger"]["events"] == len(events)
        assert state["ledger"]["primary_events"] == sum(
            counts[group] for group in module.PRIMARY_GROUPS
        )
        for group, count in counts.items():
            assert state["ledger"][group] == count
        assert state["ledger"]["matured"] == matured
        assert state["ledger"]["ungraded"] == len(events) - matured
        assert state["ledger"]["earliest_action"] == action_dates[0]
        assert state["ledger"]["latest_action"] == action_dates[-1]


def test_finra_runtime_prefix_matches_freezer_and_frozen_attestation():
    panel = pd.read_parquet(af1.finra_path(), columns=list(af1.FINRA_COLUMNS))
    runtime = af1.canonical_finra_prefix_bytes(panel)
    frozen = freezer._finra_prefix_bytes(panel)
    assert runtime == frozen
    assert hashlib.sha256(runtime).hexdigest() == af1.FINRA_PREFIX_SHA256
    dates = pd.to_datetime(panel["date"]).dt.normalize()
    assert int((dates <= pd.Timestamp(af1.FINRA_PREFIX_END)).sum()) == (
        af1.FINRA_PREFIX_ROWS
    )


def _challenge_panels() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    index = pd.bdate_range("2025-01-02", periods=190)
    t = np.arange(len(index), dtype=float)
    peers = {}
    for number in range(20):
        daily = 0.0003 + 0.0025 * np.sin(t / (4.0 + number / 10.0) + number)
        peers[f"P{number:02d}"] = 100.0 * np.cumprod(1.0 + daily)
    peer_close = pd.DataFrame(peers, index=index)
    source = 150
    # Search begins at B+5. Make its completed three-session peer return a
    # decisive pullback; the prior-only q20 remains frozen at B.
    for position in range(source + 3, source + 6):
        peer_close.iloc[position] = peer_close.iloc[position - 1] * 0.98
    subject_close = np.full(len(index), 100.0)
    subject_close[: source + 3] = 100.0 + 0.02 * np.arange(source + 3)
    subject_close[source + 3 : source + 6] = [103.5, 104.0, 104.5]
    subject_close[source + 6 :] = 104.5
    subject = pd.DataFrame(
        {
            "open": subject_close,
            "high": subject_close + 1.0,
            "low": subject_close - 1.0,
            "close": subject_close,
        },
        index=index,
    )
    return subject, peer_close, source


def test_cr1_first_challenge_is_prefix_invariant_and_selective():
    subject, peers, source = _challenge_panels()
    full, reason = cr1.find_challenge(
        subject,
        peers,
        source,
        atr_anchor=2.0,
        reference_low=90.0,
        source_action_close=float(subject["close"].iloc[source]),
    )
    assert reason == "ok"
    assert full is not None
    completion = int(full["completion_position"])
    prefix, prefix_reason = cr1.find_challenge(
        subject.iloc[: completion + 1],
        peers.iloc[: completion + 1],
        source,
        atr_anchor=2.0,
        reference_low=90.0,
        source_action_close=float(subject["close"].iloc[source]),
    )
    assert prefix_reason == "ok"
    assert prefix is not None
    assert prefix["completion_position"] == full["completion_position"] == source + 5
    assert prefix["peer_q20_at_source"] == full["peer_q20_at_source"]
    assert full["group"] == "resilient_leader"

    weak = subject.copy()
    weak.iloc[completion, weak.columns.get_loc("close")] = 95.0
    control, reason = cr1.find_challenge(
        weak.iloc[: completion + 1],
        peers.iloc[: completion + 1],
        source,
        atr_anchor=2.0,
        reference_low=90.0,
        source_action_close=float(subject["close"].iloc[source]),
    )
    assert reason == "ok"
    assert control is not None and control["group"] == "challenged_control"


def _crowding_panel() -> tuple[pd.DataFrame, int]:
    rng = np.random.default_rng(20260812)
    rows = 210
    names = 24
    returns = rng.normal(0.0002, 0.012, size=(rows, names))
    source = 195
    common_leg = np.linspace(-0.006, 0.007, cd1.RETURN_SESSIONS)
    for offset, position in enumerate(
        range(source - cd1.RETURN_SESSIONS + 1, source + 1)
    ):
        returns[position] = common_leg[offset] + np.linspace(-1e-5, 1e-5, names)
    close = 100.0 * np.cumprod(1.0 + returns, axis=0)
    return pd.DataFrame(
        close,
        index=pd.bdate_range("2025-01-02", periods=rows),
        columns=[f"P{i:02d}" for i in range(names)],
    ), source


def test_cd1_uses_prior_thresholds_and_ignores_future_suffix():
    panel, source = _crowding_panel()
    current, reason = cd1.classify_crowding(panel.iloc[: source + 1], source)
    assert reason == "ok"
    assert current is not None
    assert current["group"] == "crowding_hazard"
    assert current["high_pc1"] and current["low_dispersion"]

    changed_future = panel.copy()
    changed_future.iloc[source + 1 :] = np.arange(
        len(changed_future) - source - 1
    )[:, None]
    suffix, suffix_reason = cd1.classify_crowding(changed_future, source)
    assert suffix_reason == "ok"
    assert suffix is not None
    for key in ("pc1_share", "pc1_q80_prior", "dispersion_5", "dispersion_q20_prior"):
        assert np.isclose(float(current[key]), float(suffix[key]))
    assert suffix["group"] == current["group"]


def _flow_panel(challenge_ratio: float, challenge_total: float = 150.0) -> tuple:
    dates = pd.bdate_range("2026-05-01", periods=23)
    rows = []
    for number, date in enumerate(dates[:20]):
        ratio = 0.35 + 0.005 * (number % 5)
        rows.append(
            {
                "date": date,
                "ticker": "TEST",
                "short_vol": ratio * 100.0,
                "short_exempt": 0.0,
                "total_vol": 100.0,
                "short_ratio": ratio,
            }
        )
    for date in dates[20:]:
        rows.append(
            {
                "date": date,
                "ticker": "TEST",
                "short_vol": challenge_ratio * challenge_total,
                "short_exempt": 0.0,
                "total_vol": challenge_total,
                "short_ratio": challenge_ratio,
            }
        )
    return pd.DataFrame(rows), dates[:20], dates[20:]


def test_af1_exact_date_flow_groups_are_disjoint():
    high, baseline, challenge = _flow_panel(0.70)
    witness = af1.classify_flow(high, "TEST", baseline, challenge)
    assert witness["group"] == "flow_witness"
    assert witness["baseline_rows"] == 20
    assert witness["challenge_rows"] == 3

    light, baseline, challenge = _flow_panel(0.20)
    control = af1.classify_flow(light, "TEST", baseline, challenge)
    assert control["group"] == "leader_flow_control"

    quiet, baseline, challenge = _flow_panel(0.70, challenge_total=50.0)
    low_activity = af1.classify_flow(quiet, "TEST", baseline, challenge)
    assert low_activity["group"] == "low_activity_diagnostic"

    missing = high.iloc[:-1].copy()
    absent = af1.classify_flow(missing, "TEST", baseline, challenge)
    assert absent["group"] == "missing_flow_diagnostic"
    assert absent["missing_required_rows"] == 1


@pytest.mark.parametrize(
    ("module", "group"),
    [
        (cr1, "resilient_leader"),
        (cd1, "crowding_hazard"),
        (af1, "flow_witness"),
    ],
)
def test_nightly_enrollment_rejects_backfill_and_is_idempotent(
    tmp_path,
    monkeypatch,
    module,
    group,
):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(module, "load_registration", lambda root=None: {})
    old = _event(module, action_date=common.NOT_BEFORE_SESSION, group=group)
    future = _event(module, action_date="2026-07-27", group=group)
    monkeypatch.setattr(
        module,
        "_scan_sources",
        lambda registration, root, through, **kwargs: (
            [old.copy(), future.copy()],
            {"derived_events": 2},
        ),
    )
    monkeypatch.setattr(module.common, "load_ohlcv", lambda *args, **kwargs: None)

    first = module.update(root=tmp_path, as_of="2026-07-27")
    assert first is not None
    assert first["ledger"]["events"] == 1
    assert first["ledger"]["appended_today"] == 1
    assert first["ledger"]["rejected_pre_cutoff_today"] == 1
    rows = _events(tmp_path, module)
    assert len(rows) == 1 and rows[0]["action_date"] == "2026-07-27"
    assert rows[0]["authority"] == common.AUTHORITY

    before = module.ledger_path(tmp_path).read_bytes()
    second = module.update(root=tmp_path, as_of="2026-07-27")
    after = module.ledger_path(tmp_path).read_bytes()
    assert second is not None and second["ledger"]["appended_today"] == 0
    assert before == after


@pytest.mark.parametrize("module", MODULES)
def test_non_nightly_lane_cannot_scan_append_or_grade(tmp_path, monkeypatch, module):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.setattr(module, "load_registration", lambda root=None: {})

    def forbidden(*args, **kwargs):
        raise AssertionError("non-nightly lane attempted a source scan")

    monkeypatch.setattr(module, "_scan_sources", forbidden)
    state = module.update(root=tmp_path, as_of="2026-07-27")
    assert state is not None
    assert state["gate_open"] is False
    assert state["ledger"]["events"] == 0
    assert not module.ledger_path(tmp_path).exists()
    assert module.state_path(tmp_path).exists()


def test_registration_tamper_fails_inert(tmp_path):
    _copy_registration(tmp_path, cr1)
    manifest = cr1.manifest_path(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["construction"]["leadership"]["minimum_percentile_inclusive"] = 0.74
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert cr1.load_registration(tmp_path) is None


def test_common_grade_is_exact_rh1_ruler_and_action_day_is_excluded():
    index = pd.bdate_range("2026-01-02", periods=100)
    close = np.full(len(index), 100.0)
    low = np.full(len(index), 99.0)
    action = 32
    close[action] = 80.0
    row = _event(
        cr1,
        action_date=str(index[action].date()),
        group="resilient_leader",
    )
    row["action_close"] = 80.0
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": low,
            "close": close,
        },
        index=index,
    )
    assert common.grade_row(frame.iloc[: action + 63], row) is None
    grade = common.grade_row(frame, row)
    assert grade is not None
    assert grade["mae63"] == 25.0


def test_engine_wiring_is_ordered_and_has_no_product_payload():
    source = Path("engine/run.py").read_text(encoding="utf-8")
    rh1_at = source.index("personality_relief_hazard as _prh")
    cr1_at = source.index("personality_challenge_resilience as _pcr")
    cd1_at = source.index("personality_crowding_hazard as _pch")
    af1_at = source.index("personality_flow_absorption as _pfa")
    assert rh1_at < cr1_at < cd1_at < af1_at
    assert 'latest["personality_challenge_resilience"]' not in source
    assert 'latest["personality_crowding_hazard"]' not in source
    assert 'latest["personality_flow_absorption"]' not in source
    for module in MODULES:
        assert module.AUTHORITY == common.AUTHORITY
        assert module.AUTHORITY["may_gate"] is False
        assert module.AUTHORITY["may_display_to_users"] is False
