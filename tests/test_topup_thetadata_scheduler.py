"""tests/test_topup_thetadata_scheduler.py — AD-1T1 §E/§H scheduler suite.

Pins the new finite-periodic launchd lane (plist + thin wrapper) and the
retirement of the whole-year daily-refresh keepalive lane.
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHD_DIR = REPO_ROOT / "scripts" / "launchd"
PLIST_PATH = LAUNCHD_DIR / "com.macro.thetadata-daily.plist"
WRAPPER_PATH = LAUNCHD_DIR / "theta_daily_refresh.sh"

RETIRED_WRAPPER = LAUNCHD_DIR / "theta_backfill_keepalive.sh"
RETIRED_PLIST = LAUNCHD_DIR / "com.macro.thetadata-backfill.plist"

EXPECTED_FIRE_POINTS = [(13, 20), (14, 30), (16, 0), (18, 0)]


def _load_plist() -> dict:
    with open(PLIST_PATH, "rb") as f:
        return plistlib.load(f)


# ── plist parses ─────────────────────────────────────────────────────────────
def test_plist_exists_and_parses():
    assert PLIST_PATH.exists()
    doc = _load_plist()
    assert doc["Label"] == "com.macro.thetadata-daily"


def test_plist_lints_with_plutil_when_available():
    if shutil.which("plutil") is None:
        import pytest
        pytest.skip("plutil not available on this platform")
    rc = subprocess.run(["plutil", "-lint", str(PLIST_PATH)],
                        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stdout + rc.stderr


def test_plist_is_well_formed_xml_fallback():
    import xml.etree.ElementTree as ET
    ET.parse(PLIST_PATH)   # raises on malformed XML


# ── no KeepAlive ─────────────────────────────────────────────────────────────
def test_plist_has_no_keepalive_key():
    doc = _load_plist()
    assert "KeepAlive" not in doc


# ── StartCalendarInterval fire points exactly as §E ─────────────────────────
def test_plist_fire_points_match_spec_exactly():
    doc = _load_plist()
    intervals = doc["StartCalendarInterval"]
    assert isinstance(intervals, list)
    got = sorted((d["Hour"], d["Minute"]) for d in intervals)
    assert got == sorted(EXPECTED_FIRE_POINTS)


def test_plist_run_at_load_true():
    doc = _load_plist()
    assert doc["RunAtLoad"] is True


def test_plist_limit_load_to_session_type_aqua():
    doc = _load_plist()
    assert doc["LimitLoadToSessionType"] == "Aqua"


def test_plist_label_is_the_daily_label_not_the_retired_one():
    doc = _load_plist()
    assert doc["Label"] == "com.macro.thetadata-daily"
    assert doc["Label"] != "com.macro.thetadata-backfill"


# ── wrapper contains no gating logic (grep-test) ────────────────────────────
def test_wrapper_exists_and_is_thin():
    assert WRAPPER_PATH.exists()
    text = WRAPPER_PATH.read_text()
    # No gating constructs: no `if`, no time/date comparisons, no pgrep guard.
    banned = ["if [", "if [[", "pgrep", "date +%H", "ThrottleInterval"]
    for token in banned:
        assert token not in text, f"wrapper contains gating logic: {token!r}"
    assert "--daily" in text
    assert "topup_thetadata_day" in text


def test_wrapper_execs_the_python_module_directly():
    text = WRAPPER_PATH.read_text()
    assert "exec" in text
    assert "-m scripts.topup_thetadata_day --daily" in text


# ── retired files are GONE ───────────────────────────────────────────────────
def test_retired_backfill_wrapper_is_gone():
    assert not RETIRED_WRAPPER.exists()


def test_retired_backfill_plist_is_gone():
    assert not RETIRED_PLIST.exists()


# ── exactly one scheduled daily maintainer in the repo estate ──────────────
def test_exactly_one_scheduled_daily_maintainer_plist():
    """No OTHER launchd plist under scripts/launchd/ declares a
    StartCalendarInterval-scheduled ThetaData T1 writer besides this one."""
    daily_labels = []
    for p in LAUNCHD_DIR.glob("*.plist"):
        try:
            with open(p, "rb") as f:
                doc = plistlib.load(f)
        except Exception:
            continue
        label = doc.get("Label", "")
        args = " ".join(doc.get("ProgramArguments", []))
        if "thetadata" in label and ("StartCalendarInterval" in doc
                                     or doc.get("KeepAlive")):
            if "topup_thetadata_day" in args or "theta_daily_refresh" in args \
                    or "backfill" in args:
                daily_labels.append(label)
    assert daily_labels == ["com.macro.thetadata-daily"]


# ── successful run followed by immediate re-invocation = cheap no-op ───────
def test_successful_run_then_immediate_reinvocation_is_cheap_noop(tmp_path, monkeypatch):
    import scripts.topup_thetadata_day as topup
    from datetime import date as _date, datetime as _dt

    store = tmp_path / "thetadata_eod"
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_daily_universe", lambda: ["SPY"])
    monkeypatch.setattr(topup, "_ad_universe", lambda: ["SPY"])

    class _Fake:
        def __init__(self):
            self.calls = []

        def reachable(self):
            return True

        def bulk_eod(self, root, exp, s, e):
            import pandas as pd
            self.calls.append(("eod", root, s))
            return pd.DataFrame({"date": [pd.Timestamp(s)], "strike": [1]})

        def bulk_open_interest(self, root, exp, s, e):
            import pandas as pd
            self.calls.append(("oi", root, s))
            return pd.DataFrame({"date": [pd.Timestamp(s)], "strike": [1]})

        def bulk_greeks(self, root, exp, s, e, order=3):
            import pandas as pd
            self.calls.append(("greeks", root, s))
            return pd.DataFrame({"date": [pd.Timestamp(s)], "strike": [1]})

    fake = _Fake()
    import collectors.thetadata as real_td
    monkeypatch.setattr(real_td, "reachable", fake.reachable)
    monkeypatch.setattr(real_td, "bulk_eod", fake.bulk_eod)
    monkeypatch.setattr(real_td, "bulk_open_interest", fake.bulk_open_interest)
    monkeypatch.setattr(real_td, "bulk_greeks", fake.bulk_greeks)

    now_fn = lambda: _dt(2026, 8, 19, 16, 30, tzinfo=topup.nyse_calendar.ET)
    rc1 = topup._daily_main(workers=1, deadline_min=topup._DEFAULT_DEADLINE_MIN, forced=False, now_fn=now_fn)
    assert rc1 == 0
    n_calls_first = len(fake.calls)
    assert n_calls_first > 0

    rc2 = topup._daily_main(workers=1, deadline_min=topup._DEFAULT_DEADLINE_MIN, forced=False, now_fn=now_fn)
    assert rc2 == 0
    assert len(fake.calls) == n_calls_first   # zero NEW vendor calls
