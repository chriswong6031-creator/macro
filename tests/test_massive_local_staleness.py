"""Local-mirror staleness tripwire for `data/massive_stock_day` reads.

THE INCIDENT
------------
The store has been R2-CANONICAL since 2026-07-29: the nightly collect lane restores
it from R2, upserts the new sessions, and publishes the delta back.  A local
`data/massive_stock_day` tree is therefore a MIRROR, and nothing refreshes it in
place.  The primary checkout's copy froze at `latest_date` 2026-07-02 and TOPA
phase-0 (`scripts/research_top_anatomy_phase0.py --data-root <primary>/data`) read
that frozen tape for 5.5 weeks, silently, producing a study of early July while
reading as a study of now (audit 2026-08-10).

The CI-side tripwires — `scripts/audit_massive_store.py`, `audit_r2`'s strict
manifest anchor — never see a local read.  `check_local_mirror_freshness` is the
local-read equivalent, and this file pins the five properties that make it safe:

  1. THRESHOLDS are the contract: warn at 5 completed sessions behind, refuse at 20.
  2. LAG IS IN TRADING SESSIONS (`lib.nyse_calendar`), never weekdays — a mirror
     that stops the session before a holiday is CURRENT, not one day behind.
  3. INERT IN CI.  Any Actions lane returns None immediately: the collect job
     legitimately opens the store mid-refresh, and DNR:KILL-NIGHTLY-HARD-GATE
     forbids a nightly fail-dark.  (Hence the delenv in the fixture below — CI sets
     GITHUB_ACTIONS, so a test that forgets it passes vacuously ON THE RUNNER and
     proves nothing.)
  4. NEVER A HARD FAILURE ON ABSENCE.  No store, or no readable manifest, is not a
     staleness verdict — the read owns its own failure; at most one line is said.
  5. The banner is DEDUPED per store per process, but the refusal is re-evaluated
     on every call: deduping the raise would let a second reader through on the
     first one's silence.

Every lag here is computed against an INJECTED `now` — CI runs UTC and the wall
clock would make these assertions rot within a week.

Run: python3 -m pytest tests/test_massive_local_staleness.py -q
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import collectors.massive_stock_day as msd

# Mon 2026-08-10, 08:00 ET (before the 17:00 ET settle buffer), so the last
# COMPLETED session is Fri 2026-08-07.  Hand-checked against lib/nyse_calendar.
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
EXPECTED_LAST = "2026-08-07"      # expected_last_session(NOW)
FRESH = "2026-08-07"              # lag 0
WARN_VINTAGE = "2026-07-29"       # lag 7  — inside [5, 20)
FROZEN_VINTAGE = "2026-07-02"     # lag 25 — the real incident vintage, refuse tier


@pytest.fixture(autouse=True)
def local_lane(monkeypatch):
    """A LOCAL research lane, and a clean banner-dedupe set.

    Both delenvs are load-bearing: GITHUB_ACTIONS is set on every runner, so
    without this every assertion below would pass against an early `return None`.
    """
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(msd, "_STALE_BANNER_SEEN", set())


def _store(tmp_path: Path, latest: str | None, *, manifest: bool = True) -> Path:
    """A store dir carrying a real manifest of the shape _write_manifest() emits."""
    d = tmp_path / "data" / "massive_stock_day"
    d.mkdir(parents=True)
    if manifest:
        (d / "_manifest.json").write_text(json.dumps(
            {"store": "massive_stock_day", "n_tickers": 19_842,
             "latest_date": latest, "updated_at": "2026-08-10T02:00:00+00:00"}, indent=2))
    return d


def _check(path: Path, **kw) -> int | None:
    kw.setdefault("entrypoint", "tests/test_massive_local_staleness.py")
    kw.setdefault("now", NOW)
    return msd.check_local_mirror_freshness(path, **kw)


# --- 1: the thresholds ARE the contract -------------------------------------


def test_thresholds_are_pinned():
    # Not decoration: the numbers are the tripwire.  Moving one is a decision, and
    # a decision that has to edit this line is a decision someone reviews.
    assert msd.LOCAL_STALE_WARN_SESSIONS == 5
    assert msd.LOCAL_STALE_REFUSE_SESSIONS == 20


def test_fresh_mirror_returns_zero_and_says_nothing(tmp_path, capsys):
    assert _check(_store(tmp_path, FRESH)) == 0
    cap = capsys.readouterr()
    assert cap.err == "" and cap.out == ""


def test_warn_tier_names_the_vintage_the_lag_and_the_fix(tmp_path, capsys):
    assert _check(_store(tmp_path, WARN_VINTAGE)) == 7
    cap = capsys.readouterr()
    # STDERR, not stdout: these entrypoints print their study to stdout, and a
    # warning that lands in the artifact stream is a warning that gets piped away.
    assert cap.out == ""
    assert msd.LOCAL_MIRROR_FIX_CMD in cap.err
    assert ("python -m scripts.fetch_r2 --dirs massive_stock_day --workers 24"
            in cap.err)                                   # the literal, not just the const
    assert WARN_VINTAGE in cap.err                        # what the manifest claims
    assert "7 completed trading session(s)" in cap.err    # how far behind
    assert EXPECTED_LAST in cap.err                       # what it should have held
    assert "tests/test_massive_local_staleness.py" in cap.err   # who is reading it
    assert "R2-CANONICAL" in cap.err and "does NOT" in cap.err  # why it is not self-healing
    assert "::" not in cap.err                            # never a GitHub annotation


def test_one_session_under_the_warn_floor_stays_silent(tmp_path, capsys):
    # Mon 2026-08-03 is lag 4 at NOW (08-04, 08-05, 08-06, 08-07 missing).  A mirror
    # that missed a nightly is ordinary; the floor exists so the banner keeps meaning
    # something when it does fire.
    assert _check(_store(tmp_path, "2026-08-03")) == 4
    assert capsys.readouterr().err == ""


def test_refuse_tier_raises_and_names_the_override(tmp_path, capsys):
    with pytest.raises(msd.StaleLocalMirrorError, match="25 trading sessions behind"):
        _check(_store(tmp_path, FROZEN_VINTAGE))
    err = capsys.readouterr().err
    assert "REFUSING TO RUN" in err
    assert "--allow-stale" in err              # the operator needs the way through
    assert FROZEN_VINTAGE in err


def test_allow_stale_proceeds_at_refuse_tier_but_still_shouts(tmp_path, capsys):
    # The override buys a run, never silence: the reader must know the numbers are
    # as of a frozen date before they quote them.
    assert _check(_store(tmp_path, FROZEN_VINTAGE), allow_stale=True) == 25
    err = capsys.readouterr().err
    assert "Proceeding under --allow-stale" in err
    assert f"AS OF {FROZEN_VINTAGE}" in err
    assert "REFUSING TO RUN" not in err


# --- 2: trading sessions, never weekdays ------------------------------------


def test_lag_is_trading_sessions_not_weekdays_across_a_holiday(tmp_path, capsys):
    # Hand-count from lib/nyse_calendar's own rules: 2026-07-04 is a SATURDAY, so
    # Independence Day is observed Friday 2026-07-03 (`_observed`), which is
    # therefore NOT a session.  A mirror holding Thu 2026-07-02, read on Mon
    # 2026-07-06 at 09:00 ET (before the settle buffer, so the expected last
    # completed session is 07-02 itself), is CURRENT: lag 0.
    #
    # Naive weekday math would count 07-03 and call the same mirror 1 behind — the
    # error that makes an operator distrust the tripwire and then ignore it.
    monday_morning_et = datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc)
    assert _check(_store(tmp_path, "2026-07-02"), now=monday_morning_et) == 0
    assert capsys.readouterr().err == ""


# --- 3: inert in every Actions lane -----------------------------------------


@pytest.mark.parametrize("var,val", [("COLLECT_LANE", "nightly"),
                                     ("GITHUB_ACTIONS", "true")])
def test_ci_lanes_are_inert_even_on_an_ancient_mirror(tmp_path, capsys, monkeypatch,
                                                      var, val):
    # The collect job opens the store MID-REFRESH by design, and
    # DNR:KILL-NIGHTLY-HARD-GATE forbids a nightly fail-dark.  Ancient vintage,
    # no return value, no output, no raise.
    monkeypatch.setenv(var, val)
    assert _check(_store(tmp_path, "2021-07-06")) is None
    cap = capsys.readouterr()
    assert cap.err == "" and cap.out == ""


# --- 4: absence is not a staleness verdict ----------------------------------


def test_absent_store_is_silent(tmp_path, capsys):
    assert _check(tmp_path / "data") is None
    cap = capsys.readouterr()
    assert cap.err == "" and cap.out == ""


def test_manifest_missing_says_exactly_one_line_and_does_not_raise(tmp_path, capsys):
    # A store with no manifest cannot be dated — that is UNVERIFIABLE, not stale, and
    # a refusal here would brick a legitimately hand-assembled tree.
    store = _store(tmp_path, None, manifest=False)
    assert _check(store) is None
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "UNVERIFIABLE" in lines[0] and msd.LOCAL_MIRROR_FIX_CMD in lines[0]


def test_null_latest_date_is_unverifiable_not_stale(tmp_path, capsys):
    # A manifest written before the store's first successful batch carries a null.
    assert _check(_store(tmp_path, None)) is None
    assert "UNVERIFIABLE" in capsys.readouterr().err


# --- 5: dedupe the banner, never the refusal --------------------------------


def test_banner_prints_once_per_store_per_process(tmp_path, capsys):
    store = _store(tmp_path, WARN_VINTAGE)
    assert _check(store) == 7
    assert msd.LOCAL_MIRROR_FIX_CMD in capsys.readouterr().err
    assert _check(store) == 7
    assert capsys.readouterr().err == ""          # build_panel_w is not the only reader


def test_refusal_survives_the_dedupe(tmp_path):
    # Second call: banner suppressed, refusal NOT.  A tripwire that fires once per
    # process is a tripwire the second reader walks straight past.
    store = _store(tmp_path, FROZEN_VINTAGE)
    for _ in range(2):
        with pytest.raises(msd.StaleLocalMirrorError):
            _check(store)


# --- path normalization: data root OR the store dir itself ------------------


def test_accepts_the_data_root_and_the_store_dir_alike(tmp_path, capsys):
    # research_top_anatomy_phase0 passes --data-root; run_rule_replay passes
    # --massive-dir, which IS the store dir.  Both must reach the same manifest.
    store = _store(tmp_path, WARN_VINTAGE)
    assert _check(store.parent) == 7
    capsys.readouterr()
    msd._STALE_BANNER_SEEN.clear()
    assert _check(store) == 7


def test_a_data_root_named_massive_stock_day_is_not_doubled(tmp_path, capsys):
    # Defensive: the normalization keys on the LEAF name, so a store dir must not be
    # re-suffixed into <store>/massive_stock_day (which would silently read nothing).
    store = _store(tmp_path, FROZEN_VINTAGE)
    assert not (store / "massive_stock_day").exists()
    with pytest.raises(msd.StaleLocalMirrorError):
        _check(store)


# --- the wired entrypoints all carry the override ---------------------------


def test_every_wired_entrypoint_offers_allow_stale():
    # A refusal with no way through is a refusal an operator works around by
    # deleting the check.  Each wired script must expose the escape hatch.
    root = Path(__file__).resolve().parent.parent
    for rel in ("scripts/research_top_anatomy_phase0.py",
                "scripts/synthetic_control_phase0.py",
                "scripts/pick_forward_dist_phase1_har.py",
                "scripts/run_rule_replay.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "check_local_mirror_freshness" in src, rel
        assert "--allow-stale" in src, rel
        assert "StaleLocalMirrorError" in src, rel


def test_no_github_annotations_anywhere_in_the_feature():
    # The check is inert in CI by construction, so an annotation could only ever be
    # dead decoration — and the house trap is a "::warning" that goes out through a
    # prefixing logger and is silently dropped (tests/test_gh_annotation_line_start).
    root = Path(__file__).resolve().parent.parent
    src = (root / "collectors" / "massive_stock_day.py").read_text(encoding="utf-8")
    start = src.index("def _stale_banner")
    end = src.index("def _scan_store_days")
    feature = src[start:end]
    for token in ("::warning", "::error", "::notice"):
        assert token not in feature


def test_helper_survives_a_str_path(tmp_path):
    # argparse hands some callers a str, others a Path; both are stores.
    assert _check(str(_store(tmp_path, FRESH))) == 0


def test_future_dated_manifest_is_not_negative(tmp_path, capsys):
    # A store ahead of the calendar (a fabricated forward row) is 0 behind, never -3:
    # nyse_calendar.sessions_behind counts only MISSING completed sessions.
    assert _check(_store(tmp_path, "2026-09-01")) == 0
    assert capsys.readouterr().err == ""


def test_expected_last_session_matches_the_calendar(tmp_path):
    # Pins the injected-now convention itself: if NOW's expected last session ever
    # stops being 2026-08-07, every literal above is wrong and this fails first.
    from lib import nyse_calendar

    assert nyse_calendar.expected_last_session(NOW) == date.fromisoformat(EXPECTED_LAST)
