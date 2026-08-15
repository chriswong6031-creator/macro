"""WS-2 / GATE-2 quota-safety tests for engine.neuralweb.brain_gateway.

Acceptance (research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md WS-2):
  1. Check-and-increment is atomic (flock held across read AND write).
  2. Writes are tmp+os.replace; a corrupt ledger is NOT treated as count=0.
  3. Guest quota-state failure fail-CLOSES; authenticated payer fail-OPENS.
  4. >=50 concurrent callers against limit=10 admit AT MOST 10.
     Mutation-proof: the unlocked replica over-admits (positive control).
  5. A global daily spend ceiling exists, independent of per-user ledgers.

All offline. Ledger writes go to tmp_path.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_guest_cfg():
    """Do not leak BRAIN_GUEST_CFG into sibling suites (_get_allowance reads it)."""
    prev = os.environ.pop("BRAIN_GUEST_CFG", None)
    gw._GUEST_CFG_CACHE = None
    try:
        yield
    finally:
        gw._GUEST_CFG_CACHE = None
        if prev is None:
            os.environ.pop("BRAIN_GUEST_CFG", None)
        else:
            os.environ["BRAIN_GUEST_CFG"] = prev


def _make_temp_root() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    nw = d / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    (nw / "world_state.json").write_text(json.dumps({
        "verdict": "RISK_OFF", "regime": "Q1", "score": 34,
    }))
    return d


def _cfg(fast_limit: int = 10, *, request_ceiling: int = 0, token_ceiling: int = 0) -> dict:
    return {
        "lanes": {"fast": {"max_tokens": 2000, "tool_budget": 5, "usage_lane": "brain-fast"}},
        "quotas": {
            "free": {"fast": {"limit": fast_limit, "period": "week"}, "pro": {"limit": 0, "period": "month"}},
            "pro": {"fast": {"limit": 1000, "period": "month"}, "pro": {"limit": 150, "period": "month"}},
        },
        "token_ceilings": {"fast": 5_000_000, "pro": 2_000_000},
        "tier_cache_ttl_seconds": 60,
        "global_daily_request_ceiling": request_ceiling,
        "global_daily_token_ceiling": token_ceiling,
    }


def _write_guest_cfg(tmp_path: pathlib.Path, daily_limit: int) -> None:
    p = tmp_path / "guest_cfg.json"
    p.write_text(json.dumps({"enabled": True, "daily_limit": daily_limit}), encoding="utf-8")
    os.environ["BRAIN_GUEST_CFG"] = str(p)
    gw._GUEST_CFG_CACHE = None


# ---------------------------------------------------------------------------
# Mutation-proof replica of the pre-WS-2 unlocked RMW (MMX-002)
# ---------------------------------------------------------------------------

def _unlocked_check_and_increment(path: pathlib.Path, limit: int, *, delay_s: float = 0.003) -> bool:
    """The old algorithm: read, gap, write — no flock, no atomic replace.

    ``delay_s`` widens the race so the positive control cannot flake-pass on a
    lucky serial schedule. The production defect does not need the sleep; 50
    FastAPI worker threads hitting the real unlocked pair were enough.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"count": 0}
    except Exception:  # noqa: BLE001 — old _read_quota swallowed corruption as zero
        data = {"count": 0}
    count = int(data.get("count") or 0)
    if count >= limit:
        return False
    if delay_s:
        time.sleep(delay_s)
    data["count"] = count + 1
    path.write_text(json.dumps(data))
    return True


def test_unlocked_replica_over_admits_under_concurrency(tmp_path):
    """Positive control: the OLD unlocked RMW admits more than ``limit``.

    If this assertion ever starts failing, the replica no longer models MMX-002
    and the concurrent-cap test has lost its mutation-proof.
    """
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"count": 0}), encoding="utf-8")

    def one(_i: int) -> bool:
        return _unlocked_check_and_increment(path, 10)

    with ThreadPoolExecutor(max_workers=50) as pool:
        allowed = sum(pool.map(one, range(50)))
    assert allowed > 10, (
        f"unlocked replica admitted only {allowed} of 50 against limit=10 — "
        "the mutation-proof can no longer see the MMX-002 race"
    )


def test_concurrent_auth_check_and_increment_caps_at_limit(tmp_path):
    """>=50 concurrent authenticated callers against limit=10 → at most 10 succeed.

    This is the GATE-2 chaos test. Against the pre-WS-2 unlocked pair it
    over-admits (see test_unlocked_replica_over_admits_under_concurrency).
    """
    root = _make_temp_root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10)):
            def one(_i: int) -> bool:
                ok, _q = gw._check_and_increment_quota(
                    "race-user", "fast", "free", "active", None, root,
                )
                return ok

            with ThreadPoolExecutor(max_workers=50) as pool:
                futs = [pool.submit(one, i) for i in range(50)]
                allowed = sum(f.result() for f in as_completed(futs))

    assert allowed <= 10, (
        f"authenticated quota admitted {allowed} of 50 concurrent callers against limit=10"
    )
    ledgers = list(tmp_path.glob("q_race-user_fast_*.json"))
    if ledgers:
        stored = int(json.loads(ledgers[0].read_text(encoding="utf-8")).get("count") or 0)
        assert stored <= 10


def test_concurrent_guest_check_and_increment_caps_at_limit(tmp_path):
    """>=50 concurrent guest callers against daily_limit=10 → at most 10 succeed."""
    root = _make_temp_root()
    _write_guest_cfg(tmp_path, 10)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        def one(_i: int) -> bool:
            ok, _q = gw._check_and_increment_guest_quota("aid-race", "ip-race", "fast", root)
            return ok

        with ThreadPoolExecutor(max_workers=50) as pool:
            futs = [pool.submit(one, i) for i in range(50)]
            allowed = sum(f.result() for f in as_completed(futs))

    assert allowed <= 10, (
        f"guest quota admitted {allowed} of 50 concurrent callers against limit=10"
    )


# ---------------------------------------------------------------------------
# Corrupt ledger must not deserialize as a fresh zero-count allowance
# ---------------------------------------------------------------------------

def test_read_quota_missing_file_is_fresh_zero(tmp_path):
    missing = tmp_path / "no_such_ledger.json"
    assert gw._read_quota(missing) == {"count": 0}


def test_read_quota_corrupt_is_loud_not_zero(tmp_path):
    """A truncated/corrupt ledger must raise — never silently become count=0."""
    path = tmp_path / "q_corrupt.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(gw.QuotaLedgerCorrupt):
        gw._read_quota(path)


def test_read_quota_empty_file_is_corrupt(tmp_path):
    path = tmp_path / "q_empty.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(gw.QuotaLedgerCorrupt):
        gw._read_quota(path)


def test_read_quota_non_object_json_is_corrupt(tmp_path):
    path = tmp_path / "q_list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(gw.QuotaLedgerCorrupt):
        gw._read_quota(path)


def test_auth_corrupt_ledger_fail_opens_without_resetting(tmp_path):
    """Authenticated payer: corrupt ledger fail-opens and is NOT rewritten as {count:0}."""
    root = _make_temp_root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10)):
            pk = gw._period_key("week", "active", None)
            qf = gw._quota_file("payer1", "fast", pk)
            qf.write_text("{truncated", encoding="utf-8")
            # free/active/fast uses the week period — same file we just corrupted.
            allowed, info = gw._check_and_increment_quota(
                "payer1", "fast", "free", "active", None, root,
            )
    assert allowed is True
    assert info["limit"] == -1  # fail-open sentinel, not a fresh 10-count allowance
    assert qf.read_text(encoding="utf-8") == "{truncated"


def test_guest_corrupt_ledger_fail_closes_without_resetting(tmp_path):
    """Guest: corrupt ledger fail-closes and is NOT rewritten as {count:0}."""
    root = _make_temp_root()
    _write_guest_cfg(tmp_path, 10)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        pk = gw._period_key("day", "active", None)
        cf = gw._guest_cookie_quota_file("aid1", "fast", pk)
        cf.write_text("{truncated", encoding="utf-8")
        allowed, info = gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)
    assert allowed is False
    assert info["remaining"] == 0
    assert cf.read_text(encoding="utf-8") == "{truncated"


def test_write_quota_is_replace_not_in_place(tmp_path, monkeypatch):
    """Writes must go through os.replace (tmp + rename), never path.write_text."""
    path = tmp_path / "q.json"
    seen: list[tuple[str, str]] = []
    real_replace = gw.os.replace

    def spy_replace(src, dst):
        seen.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(gw.os, "replace", spy_replace)
    gw._write_quota(path, {"count": 3})
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 3
    assert seen, "os.replace was not used — write is not crash-safe"
    assert any(str(path) == dst for _src, dst in seen)


# ---------------------------------------------------------------------------
# Failure asymmetry: guest fail-closed / authenticated payer fail-open
# ---------------------------------------------------------------------------

def test_auth_quota_dir_unavailable_fail_opens(tmp_path):
    """ASYMMETRY — authenticated payer: unwritable state dir → allow (fail-open)."""
    root = _make_temp_root()
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    with patch.object(gw, "_brain_quota_dir", return_value=blocker / "brain_quota"):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10)):
            allowed, info = gw._check_and_increment_quota(
                "payer1", "fast", "pro", "active", None, root,
            )
    assert allowed is True
    assert info["limit"] == -1


def test_guest_quota_dir_unavailable_fail_closes(tmp_path):
    """ASYMMETRY — guest: unwritable state dir → deny (fail-closed)."""
    root = _make_temp_root()
    _write_guest_cfg(tmp_path, 30)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    with patch.object(gw, "_brain_quota_dir", return_value=blocker / "brain_quota"):
        allowed, info = gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)
    assert allowed is False
    assert info["remaining"] == 0
    assert info["limit"] == 30


# ---------------------------------------------------------------------------
# Global daily spend ceiling — independent of per-user counters
# ---------------------------------------------------------------------------

def test_global_daily_request_ceiling_independent_of_per_user(tmp_path):
    """Four users each have per-user limit 10; global request ceiling 3 → 3 admits total."""
    root = _make_temp_root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10, request_ceiling=3)):
            results = [
                gw._check_and_increment_quota(uid, "fast", "free", "active", None, root)[0]
                for uid in ("u1", "u2", "u3", "u4")
            ]
    assert results == [True, True, True, False]
    spend_files = list(tmp_path.glob("global_spend_*.json"))
    assert spend_files, "global spend ledger was not written"
    stored = int(json.loads(spend_files[0].read_text(encoding="utf-8")).get("count") or 0)
    assert stored == 3


def test_global_daily_token_ceiling_blocks_subsequent_requests(tmp_path):
    """Tokens recorded against the global ledger trip the next check-and-increment."""
    root = _make_temp_root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10, token_ceiling=150)):
            ok1, _ = gw._check_and_increment_quota("u1", "fast", "free", "active", None, root)
            assert ok1 is True
            gw._record_token_usage("u1", "fast", 80, 80)  # 160 >= 150
            ok2, info = gw._check_and_increment_quota("u2", "fast", "free", "active", None, root)
    assert ok2 is False
    assert info["remaining"] == 0


def test_global_ceiling_applies_to_guests_too(tmp_path):
    root = _make_temp_root()
    _write_guest_cfg(tmp_path, 30)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_load_brain_config", return_value=_cfg(10, request_ceiling=2)):
            a1, _ = gw._check_and_increment_guest_quota("aidA", "ipA", "fast", root)
            a2, _ = gw._check_and_increment_guest_quota("aidB", "ipB", "fast", root)
            a3, _ = gw._check_and_increment_guest_quota("aidC", "ipC", "fast", root)
    assert a1 is True and a2 is True and a3 is False


def test_config_global_daily_ceilings_present_in_brain_yml():
    """Production brain.yml (and the hardcoded fallback) carry a non-zero global ceiling."""
    repo = pathlib.Path(__file__).resolve().parent.parent
    gw._BRAIN_CONFIG_CACHE = None
    cfg = gw._load_brain_config(repo)
    gw._BRAIN_CONFIG_CACHE = None
    assert int(cfg.get("global_daily_request_ceiling") or 0) > 0
    assert int(cfg.get("global_daily_token_ceiling") or 0) > 0
