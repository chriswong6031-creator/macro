"""Hermetic tests for T5 leadership persistence (tenure / handoff) — pure logic + the
idempotent site-tier ledger accrual. No Bash, no network.
"""
from engine.momentum_king import compute_persistence


# ── The pure tenure function ────────────────────────────────────────────────────

def test_persistence_stable_leader_rising_tenure():
    hist = [{"as_of": "2026-07-01", "entries": {"sectors:IT": "NVDA"}},
            {"as_of": "2026-07-02", "entries": {"sectors:IT": "NVDA"}}]
    p = compute_persistence(hist, {"sectors:IT": "NVDA"})["sectors:IT"]
    assert p["tenure"] == 3 and p["handoff"] is False and p["first_seen"] == "2026-07-01"


def test_persistence_handoff_resets_and_flags():
    hist = [{"as_of": "2026-07-01", "entries": {"sectors:IT": "AAPL"}}]
    p = compute_persistence(hist, {"sectors:IT": "NVDA"})["sectors:IT"]
    assert p["tenure"] == 1 and p["handoff"] is True


def test_persistence_cold_start():
    assert compute_persistence([], {"sectors:IT": "NVDA"})["sectors:IT"] == {
        "tenure": 1, "first_seen": None, "handoff": False, "authority_tier": "display"}


def test_persistence_ignores_null_leader():
    assert compute_persistence([], {"sectors:IT": None}) == {}


def test_persistence_gap_breaks_tenure():
    # a prior session where a DIFFERENT leader held breaks the streak — tenure counts
    # only the consecutive tail, not an older run of the same leader.
    hist = [{"as_of": "d1", "entries": {"g": "NVDA"}},
            {"as_of": "d2", "entries": {"g": "MU"}},
            {"as_of": "d3", "entries": {"g": "NVDA"}}]
    p = compute_persistence(hist, {"g": "NVDA"})["g"]
    assert p["tenure"] == 2 and p["first_seen"] == "d3"


# ── The site-tier ledger accrual (idempotent, absent-safe) ───────────────────────

def test_attach_persistence_idempotent_and_accrues(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk, "_HISTORY_JSONL", tmp_path / "history.jsonl")

    def _board(as_of, leader="NVDA"):
        return {"as_of": as_of,
                "sectors": [{"sector": "IT", "state": "LEADER_CANDIDATE", "leader": leader}]}

    b1 = _board("2026-07-01")
    bmk._attach_persistence(b1)
    assert b1["sectors"][0]["persistence"]["tenure"] == 1

    # re-run the SAME session → idempotent: still tenure 1, ledger has exactly one row
    b1b = _board("2026-07-01")
    bmk._attach_persistence(b1b)
    assert b1b["sectors"][0]["persistence"]["tenure"] == 1
    assert len((tmp_path / "history.jsonl").read_text().strip().splitlines()) == 1

    # next session, same leader → tenure accrues
    b2 = _board("2026-07-02")
    bmk._attach_persistence(b2)
    assert b2["sectors"][0]["persistence"]["tenure"] == 2
    assert b2["sectors"][0]["persistence"]["handoff"] is False

    # handoff → tenure resets to 1, handoff flagged
    b3 = _board("2026-07-03", leader="MU")
    bmk._attach_persistence(b3)
    assert b3["sectors"][0]["persistence"]["tenure"] == 1
    assert b3["sectors"][0]["persistence"]["handoff"] is True


def test_attach_persistence_absent_safe(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk, "_HISTORY_JSONL", tmp_path / "history.jsonl")
    # a board with no crowned leaders → no persistence attached, no crash, empty ledger row
    board = {"as_of": "2026-07-01",
             "sectors": [{"sector": "IT", "state": "CONTESTED", "leader": None}]}
    bmk._attach_persistence(board)
    assert "persistence" not in board["sectors"][0]
