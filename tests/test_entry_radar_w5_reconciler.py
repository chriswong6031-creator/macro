"""W5 §8/§17 — the nightly reconciler's write discipline.

EVERY test here runs against a ``tmp_path`` root.  The reconciler's whole job is
writing durable evidence, so a suite that let it touch the real
``data/entry_radar/`` or ``data/qledger/`` would be writing production claims
from CI — the exact single-writer violation the script exists to prevent.

WHAT IS BEING PINNED, in order of how badly it would hurt to lose it:

  1. **The gate refuses ALWAYS and writes NOTHING.**  Not "writes the safe
     subset" — a partial artifact from a lane error is worse than none, because
     it is indistinguishable from a healthy pass to every instrument we own.
  2. **No spool ⇒ WAITING_FOR_LIVE_SOURCE and zero rows.**  The failure mode
     this forecloses is a reconciler that, finding no live stream, quietly
     replays nightly artifacts into plausible "observations".
  3. **No epoch ⇒ recorded but never registered.**  §8 forbids relabelling a
     row's live-forward status afterwards, so registering early is irreversible.
  4. **Re-runs are idempotent.**  Append-only means the second pass adds nothing
     and moves nothing.
"""
from __future__ import annotations

import json

import pytest

from engine.entry_radar.replay import prereg
from scripts import reconcile_entry_radar as rec


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _event(ticker: str = "ABCD", detector: str = "C2_1D_TURN@1", *,
           session: str = "2026-08-14",
           observed_at: str = "2026-08-14T20:05:00+00:00",
           event_id: str | None = None) -> dict:
    return {
        "schema": rec.SPOOL_EVENT_SCHEMA,
        "record": {
            "event_id": event_id or f"{ticker}-{detector}-{session}",
            "producer": "entry_radar",
            "detector_id": detector,
            "ticker": ticker,
            "family": "radar_turn",
            "subtype": "c2_turn",
            "context": {"market_session": session},
            "signal_ts": f"{session}T19:55:00+00:00",
            "signal_known_ts": f"{session}T20:00:00+00:00",
            "observed_at": observed_at,
            "bar_state": "confirmed",
            "final": True,
            "source_identity": {"detector_spec_hash":
                                prereg.EXPECTED_SPEC_HASHES[detector]},
        },
    }


def _write_spool(directory, events) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2026-08-14.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _state(root):
    path = root / "data" / "entry_radar" / rec.LEDGER_STATE_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def _entry_radar_files(root) -> set[str]:
    out = root / "data" / "entry_radar"
    if not out.is_dir():
        return set()
    return {p.name for p in out.iterdir() if not p.name.startswith(".")}


@pytest.fixture()
def nightly(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv(rec.SPOOL_DIR_ENV, raising=False)


@pytest.fixture()
def lane_down(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.delenv(rec.SPOOL_DIR_ENV, raising=False)


# =========================================================================== #
# 1 — the hard gate
# =========================================================================== #
def test_nightly_outside_the_lane_exits_2_and_writes_nothing(tmp_path, lane_down):
    rc = rec.main(["--root", str(tmp_path), "--nightly"])
    assert rc == 2
    assert not (tmp_path / "data").exists(), (
        "a refused nightly must not create even the output directory")


def test_gate_refusal_precedes_intake(tmp_path, lane_down, monkeypatch, capsys):
    """The refusal cannot depend on what the spool happened to contain tonight.

    MUTATION CONTROL: move the gate below ``read_spool_events`` and this passes
    only by accident — so the assertion is on the ANNOTATION, which names the
    lane, not on the (also-empty) output.
    """
    spool = tmp_path / "spool"
    _write_spool(spool, [_event()])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 2
    out = capsys.readouterr().out
    assert "::warning title=entry-radar-reconcile::" in out
    assert "COLLECT_LANE!=nightly" in out and "NOTHING written" in out
    assert not (tmp_path / "data").exists()


def test_every_annotation_starts_the_line_and_is_a_bare_print(tmp_path, lane_down,
                                                              capsys):
    """House law: a ``::warning`` emitted through a logger is silently dropped."""
    rec.main(["--root", str(tmp_path), "--nightly"])
    for line in capsys.readouterr().out.splitlines():
        if "::warning" in line or "::error" in line or "::notice" in line:
            assert line.startswith("::"), f"annotation not at line start: {line!r}"


# =========================================================================== #
# 2 — no spool ⇒ WAITING_FOR_LIVE_SOURCE
# =========================================================================== #
def test_no_spool_writes_only_the_waiting_state(tmp_path, nightly):
    assert rec.main(["--root", str(tmp_path), "--nightly", "--verbose"]) == 0
    state = _state(tmp_path)
    assert state["schema"] == rec.LEDGER_STATE_SCHEMA
    assert state["state"] == prereg.WAITING_FOR_LIVE_SOURCE
    assert state["live_forward_start"] is None
    assert state["observed_spool_events"] == 0
    assert state["session"] and state["updated_at"]
    # No forward rows, and above all no claims: nothing was observed, so nothing
    # may be asserted about anything.
    assert rec.FORWARD_NAME not in _entry_radar_files(tmp_path)
    assert not (tmp_path / "data" / "qledger").exists()


def test_no_spool_writes_nothing_outside_DURABLE_WRITES(tmp_path, nightly):
    """The declared list is the complete list, not a sample of it."""
    rec.main(["--root", str(tmp_path), "--nightly"])
    declared = {p.rsplit("/", 1)[-1] for p in rec.DURABLE_WRITES}
    assert _entry_radar_files(tmp_path) <= declared


def test_session_stamp_is_a_real_session_not_the_wall_clock(tmp_path, nightly):
    """A date the market never opened is a join key no outcome can attach to."""
    from datetime import date as _date

    from lib.nyse_calendar import is_session

    rec.main(["--root", str(tmp_path), "--nightly"])
    session = _state(tmp_path)["session"]
    assert is_session(_date.fromisoformat(session)), \
        f"{session} is not an NYSE session"


# =========================================================================== #
# 3 — idempotency
# =========================================================================== #
def test_rerun_is_idempotent_with_no_spool(tmp_path, nightly):
    rec.main(["--root", str(tmp_path), "--nightly"])
    first = _state(tmp_path)
    rec.main(["--root", str(tmp_path), "--nightly"])
    second = _state(tmp_path)
    # `updated_at` is excluded ON PURPOSE: it stamps WHEN the pass ran, and is
    # the one field that must move. Every field that makes a CLAIM about the
    # evidence is compared, and none of them may move on a re-run.
    assert {k: v for k, v in first.items() if k != "updated_at"} == \
           {k: v for k, v in second.items() if k != "updated_at"}


def test_rerun_appends_no_duplicate_forward_rows(tmp_path, nightly, monkeypatch):
    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA"), _event("BBB")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    rec.main(["--root", str(tmp_path), "--nightly"])
    forward = tmp_path / "data" / "entry_radar" / rec.FORWARD_NAME
    first_bytes = forward.read_bytes()
    assert _state(tmp_path)["forward_rows_total"] == 2

    rec.main(["--root", str(tmp_path), "--nightly"])
    assert _state(tmp_path)["forward_rows_total"] == 2
    assert _state(tmp_path)["forward_rows_appended"] == 0
    # Nothing new ⇒ the file is not rewritten at all, so the stored rows are
    # byte-identical rather than merely value-identical.
    assert forward.read_bytes() == first_bytes


def test_a_new_event_appends_without_disturbing_the_stored_rows(tmp_path, nightly,
                                                                monkeypatch):
    import pandas as pd

    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    rec.main(["--root", str(tmp_path), "--nightly"])
    forward = tmp_path / "data" / "entry_radar" / rec.FORWARD_NAME
    before = pd.read_parquet(forward)

    _write_spool(spool, [_event("AAA"), _event("BBB")])
    rec.main(["--root", str(tmp_path), "--nightly"])
    after = pd.read_parquet(forward)

    assert len(after) == 2 and _state(tmp_path)["forward_rows_appended"] == 1
    # Keep-first: the original row's VALUES survive the append untouched.
    pd.testing.assert_frame_equal(after.iloc[:1].reset_index(drop=True),
                                  before.reset_index(drop=True))


# =========================================================================== #
# 4 — spool present, epoch unset  (the state PR-5b inherits)
# =========================================================================== #
def test_events_are_recorded_but_never_registered_while_the_epoch_is_unset(
        tmp_path, nightly, monkeypatch):
    # The live module is stamped (epoch = the merged PR-5a instant); the
    # pre-stamp None state is reconstructed here because its BEHAVIOR — record
    # everything, register nothing — must stay pinned forever.
    monkeypatch.setattr(rec, "LIVE_FORWARD_EPOCH", None)
    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA"), _event("BBB", "G0_GREY_DOT@1")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 0
    state = _state(tmp_path)
    assert state["observed_spool_events"] == 2
    assert state["forward_rows_total"] == 2
    # RECORDED (nothing is lost) ...
    assert state["state"] == prereg.WAITING_FOR_LIVE_SOURCE
    assert state["live_forward_start"] is None
    assert state["live_forward_rows"] == 0
    # ... and REGISTERED NOWHERE: an early registration is irreversible.
    assert not (tmp_path / "data" / "qledger").exists()
    assert rec.REGISTRATION_LOG_NAME not in _entry_radar_files(tmp_path)


def test_rows_recorded_under_an_unset_epoch_carry_the_waiting_state(tmp_path,
                                                                    nightly,
                                                                    monkeypatch):
    import pandas as pd

    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    rec.main(["--root", str(tmp_path), "--nightly"])
    frame = pd.read_parquet(tmp_path / "data" / "entry_radar" / rec.FORWARD_NAME)
    assert set(frame["state"]) == {rec.STATE_WAITING}
    assert frame["observed_at_basis"].iloc[0] == "spool_envelope"


def test_live_forward_eligible_is_false_for_every_row_without_an_epoch():
    row = {"observed_at": "2030-01-01T00:00:00+00:00"}
    assert rec.live_forward_eligible(row, epoch=None) is False
    # CONTROL: with an epoch, the same row IS eligible — the None answer above
    # is the epoch's doing, not a function that always says no.
    assert rec.live_forward_eligible(row, epoch="2026-01-01T00:00:00+00:00") is True


def test_an_event_at_or_before_the_epoch_is_never_live_forward():
    epoch = "2026-08-14T12:00:00+00:00"
    assert rec.live_forward_eligible({"observed_at": epoch}, epoch=epoch) is False
    assert rec.live_forward_eligible(
        {"observed_at": "2026-08-14T11:59:59+00:00"}, epoch=epoch) is False
    assert rec.live_forward_eligible(
        {"observed_at": "2026-08-14T12:00:01+00:00"}, epoch=epoch) is True


# =========================================================================== #
# 5 — dry-run and report-only
# =========================================================================== #
def test_dry_run_writes_nothing(tmp_path, nightly, monkeypatch):
    spool = tmp_path / "spool"
    _write_spool(spool, [_event()])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    assert rec.main(["--root", str(tmp_path), "--nightly", "--dry-run"]) == 0
    assert not (tmp_path / "data").exists()


def test_without_nightly_nothing_is_written_even_inside_the_lane(tmp_path, nightly,
                                                                 monkeypatch):
    """The single-advancer law has no 'just the state file' exception."""
    spool = tmp_path / "spool"
    _write_spool(spool, [_event()])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    assert rec.main(["--root", str(tmp_path)]) == 0
    assert not (tmp_path / "data").exists()


# =========================================================================== #
# 6 — registration, once an epoch exists (§17)
# =========================================================================== #
def test_live_forward_rows_register_into_the_injected_root(tmp_path, nightly,
                                                           monkeypatch):
    """CONTROL for the 'never registered' tests above — with a lawful epoch the
    same machinery DOES register, so those assertions are about the epoch."""
    monkeypatch.setattr(rec, "LIVE_FORWARD_EPOCH", "2026-01-01T00:00:00+00:00")
    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 0
    state = _state(tmp_path)
    assert state["state"] == "LIVE_FORWARD_ACCRUING"
    assert state["live_forward_rows"] == 1
    assert state["live_forward_start"] == "2026-08-14"
    assert state["qledger"]["registered"] == 1

    claims = (tmp_path / "data" / "qledger" / "claims.jsonl")
    assert claims.exists(), "registration must land in the INJECTED root only"
    rows = [json.loads(x) for x in claims.read_text().splitlines() if x.strip()]
    assert len(rows) == 1
    claim = rows[0]
    assert claim["horizon_d"] == prereg.QLEDGER_HORIZON_D == 21
    assert claim["horizon_unit"] == "trading_days"
    assert claim["claim_family"] == "entry_radar_C2_1D_TURN@1"
    assert claim["desk"] == prereg.QLEDGER_DESK
    assert claim["authority"] == prereg.AUTHORITY
    assert claim["registration_note"] == prereg.REGISTRATION_NOTE
    assert "DNR:KILL-WASHOUT-TURN" in str(claim["falsifier"])


def test_registration_is_keep_first_across_reruns(tmp_path, nightly, monkeypatch):
    monkeypatch.setattr(rec, "LIVE_FORWARD_EPOCH", "2026-01-01T00:00:00+00:00")
    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))
    rec.main(["--root", str(tmp_path), "--nightly"])
    rec.main(["--root", str(tmp_path), "--nightly"])

    log = (tmp_path / "data" / "entry_radar" / rec.REGISTRATION_LOG_NAME)
    entries = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    assert len(entries) == 1, "a second pass must not re-log a latched episode"
    claims = (tmp_path / "data" / "qledger" / "claims.jsonl")
    assert len([x for x in claims.read_text().splitlines() if x.strip()]) == 1


def test_c4_is_recorded_but_never_registered(tmp_path, nightly, monkeypatch):
    """§17: C4 is stratification-only, so a directional claim for it would be
    fabricated symmetry.  It still gets a forward row — recording is not
    endorsement."""
    import pandas as pd

    monkeypatch.setattr(rec, "LIVE_FORWARD_EPOCH", "2026-01-01T00:00:00+00:00")
    spool = tmp_path / "spool"
    _write_spool(spool, [_event("AAA", "C4_MTF_TURN@1")])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 0
    frame = pd.read_parquet(tmp_path / "data" / "entry_radar" / rec.FORWARD_NAME)
    assert len(frame) == 1 and frame["detector_id"].iloc[0] == "C4_MTF_TURN@1"
    assert not (tmp_path / "data" / "qledger").exists()
    assert _state(tmp_path)["live_forward_rows"] == 0


def test_build_claims_refuses_a_non_live_forward_row(tmp_path):
    """The separation is enforced where the claim is BUILT, not only where the
    caller filters — one filter is one place to forget."""
    row = {"state": rec.STATE_WAITING, "detector_id": "C2_1D_TURN@1",
           "ticker": "AAA", "decision_session": "2026-08-14",
           "episode_address": "x"}
    with pytest.raises(AssertionError, match="LIVE-FORWARD"):
        rec.build_claims([row], root=tmp_path)


def test_build_claims_refuses_a_never_register_detector(tmp_path):
    row = {"state": rec.STATE_LIVE_FORWARD, "detector_id": "F1_FUSION",
           "ticker": "AAA", "decision_session": "2026-08-14",
           "episode_address": "x"}
    with pytest.raises(AssertionError, match="never be registered"):
        rec.build_claims([row], root=tmp_path)


def test_registration_outcome_is_fail_closed():
    """A slot that persisted nothing must never be logged as registered."""
    assert rec._registration_outcome(None) == rec._OUTCOME_FAILED
    assert rec._registration_outcome({"status": "error", "error": "x"}) == \
        rec._OUTCOME_FAILED
    assert rec._registration_outcome({"status": "open"}) == rec._OUTCOME_FAILED
    assert rec._registration_outcome({"status": "rejected", "claim_id": "z"}) == \
        rec._OUTCOME_REJECTED
    assert rec._registration_outcome({"status": "open", "claim_id": "z"}) == \
        rec._OUTCOME_REGISTERED


# =========================================================================== #
# 7 — intake hygiene
# =========================================================================== #
def test_off_schema_and_torn_records_are_skipped_never_repaired(tmp_path, nightly,
                                                                monkeypatch, capsys):
    spool = tmp_path / "spool"
    spool.mkdir(parents=True)
    (spool / "mixed.jsonl").write_text(
        json.dumps(_event("AAA")) + "\n"
        + json.dumps({"schema": "something.else/v1", "record": {"ticker": "ZZZ"}}) + "\n"
        + '{"schema": "mastermind.entry_ev\n', encoding="utf-8")
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    rec.main(["--root", str(tmp_path), "--nightly"])
    assert _state(tmp_path)["observed_spool_events"] == 1
    assert "were SKIPPED" in capsys.readouterr().out


def test_episode_address_is_stable_across_passes():
    """The join key may never contain a wall-clock field, or every re-run
    appends a 'new' episode and the ledger grows without bound."""
    ev = _event("AAA")["record"]
    assert rec.episode_address(ev) == rec.episode_address(dict(ev))
    no_id = {k: v for k, v in ev.items() if k != "event_id"}
    assert rec.episode_address(no_id) == "AAA|C2_1D_TURN@1|2026-08-14"
