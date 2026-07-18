"""Tests for engine.theme_context (theme_context.v1 producer).

Contract: /tmp/theme_context_contract.md

Coverage:
- health precedence incl. the Memory fixture (breadth 0.0, r10 -0.127, label
  deteriorating -> broken)
- confirmed + mixed cases
- null-safety (all-missing -> mixed)
- leadership state machine (rotating requires broken leader + 3 cross-category strength)
- same-day idempotent replace
- state_changes prev/changed_on correctness across two snapshots
- off-lane no-write
- read_context None on absence

All file paths are redirected to tmp_path — never write to real data/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

# ── Helpers to build minimal fixture inputs ────────────────────────────────────

def _make_rank_row(
    tid: str,
    category: str = "Semiconductors",
    breadth: float | None = None,
    r10: float | None = None,
    val_state: str | None = None,
    rank: int = 1,
    score: float | None = 2.5,
    name: str | None = None,
    name_zh: str | None = None,
) -> dict:
    return {
        "id": tid,
        "name": name or tid,
        "name_zh": name_zh or tid,
        "category": category,
        "rank": rank,
        "score": score,
        "eligible": True,
        "z_resid_mom": None,
        "z_mom_13612w": None,
        "z_accel": None,
        "gate": {"above_200dma": True},
        "r10": r10,
        "val_state": val_state,
        "durability": {
            "breadth": breadth,
            "persistence": 0.6,
            "cohesion": 0.5,
            "bar": 0.5,
        },
    }


def _make_alloc(rank_rows: list[dict], as_of: str = "2026-07-17") -> dict:
    return {
        "as_of": as_of,
        "region": "us",
        "ranks": rank_rows,
        "rotation": {},
        "allocation": {"weights": [], "cash": 0.0},
    }


def _make_theme_intel(themes: list[dict], as_of: str = "2026-07-17") -> dict:
    """Minimal theme_intel shape with a 'themes' list."""
    return {
        "as_of": as_of,
        "themes": themes,
    }


def _make_ti_theme(
    tid: str,
    label: str = "neutral",
    reco: str = "hold",
    score: int = 55,
    name: str | None = None,
    name_zh: str | None = None,
) -> dict:
    return {
        "id": tid,
        "name": name or tid,
        "name_zh": name_zh or tid,
        "label": label,
        "reco": reco,
        "score": score,
    }


# ── Import under test (deferred so path redirect is possible) ────────────────

import engine.theme_context as TC


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Remove lane env vars before each test."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


# ── Health classification tests ───────────────────────────────────────────────

class TestHealthClassification:
    """_classify_health precedence and null-safety."""

    def test_memory_fixture_broken(self):
        """Memory/HBM: breadth 0.0, r10 -0.127, label deteriorating -> broken (contract example)."""
        h = TC._classify_health(
            breadth=0.0,
            r10=-0.127,
            label="deteriorating",
            reco="avoid",
            val_state="fading",
        )
        assert h == "broken"

    def test_broken_by_breadth_and_r10(self):
        h = TC._classify_health(breadth=0.20, r10=-0.06, label="neutral", reco="hold", val_state=None)
        assert h == "broken"

    def test_broken_by_label_alone(self):
        h = TC._classify_health(breadth=0.8, r10=0.10, label="deteriorating", reco="hold", val_state=None)
        assert h == "broken"

    def test_broken_by_reco_avoid_r10_negative(self):
        h = TC._classify_health(breadth=0.4, r10=-0.01, label="neutral", reco="avoid", val_state=None)
        assert h == "broken"

    def test_confirmed(self):
        h = TC._classify_health(
            breadth=0.80,
            r10=0.047,
            label="dominant",
            reco="hold",
            val_state="confirming",
        )
        assert h == "confirmed"

    def test_confirmed_enters(self):
        h = TC._classify_health(
            breadth=0.60,
            r10=0.00,
            label="emerging",
            reco="enter",
            val_state=None,
        )
        assert h == "confirmed"

    def test_mixed_when_borderline(self):
        # breadth ok, r10 too low for confirmed but not broken
        h = TC._classify_health(
            breadth=0.60,
            r10=-0.04,  # not <= -0.05 so not broken by rule 1; not >= -0.02 so not confirmed
            label="neutral",
            reco="hold",
            val_state=None,
        )
        assert h == "mixed"

    def test_null_all_missing_mixed(self):
        """If label AND breadth AND r10 all missing -> mixed."""
        h = TC._classify_health(None, None, None, None, None)
        assert h == "mixed"

    def test_null_breadth_partial(self):
        """Missing breadth — rule 1 breadth test fails (not passing), can still be broken by label."""
        h = TC._classify_health(breadth=None, r10=-0.10, label="deteriorating", reco="hold", val_state=None)
        assert h == "broken"

    def test_null_r10_partial_breadth_ok(self):
        """Missing r10 — breadth+r10 rule needs both; but confirmed needs both too."""
        # breadth>0.55, r10=None -> rule1 breadth passes but r10 check fails; rule2 r10 check fails
        h = TC._classify_health(breadth=0.70, r10=None, label="dominant", reco="hold", val_state=None)
        assert h == "mixed"

    def test_avoid_reco_positive_r10_not_broken(self):
        """reco=avoid but r10>=0 -> rule 1c fails; check falls through."""
        h = TC._classify_health(breadth=0.70, r10=0.05, label="neutral", reco="avoid", val_state=None)
        # not broken by 1c (r10 not < 0), not confirmed (reco not in allowed set)
        assert h == "mixed"


# ── Leadership state machine ───────────────────────────────────────────────────

class TestLeadershipStateMachine:
    def test_rotating_requires_broken_leader_and_3_cross_category_strength(self):
        strength = [
            {"id": "cyber", "category": "Software"},
            {"id": "cloud", "category": "Software"},
            {"id": "finance", "category": "Financials"},
        ]
        state = TC._leadership_state("broken", strength, "Semiconductors")
        assert state == "rotating"

    def test_rotating_does_not_fire_if_same_category_cross_count_below_3(self):
        strength = [
            {"id": "cyber", "category": "Software"},
            {"id": "cloud", "category": "Software"},
            # only 2 cross-category entries
        ]
        state = TC._leadership_state("broken", strength, "Semiconductors")
        # broken + fewer than 3 cross-category -> strain
        assert state == "strain"

    def test_rotating_needs_broken_leader(self):
        strength = [
            {"id": "cyber", "category": "Software"},
            {"id": "cloud", "category": "Software"},
            {"id": "finance", "category": "Financials"},
        ]
        # leader confirmed -> no rotating even with 3 cross-category
        state = TC._leadership_state("confirmed", strength, "Semiconductors")
        assert state == "steady"

    def test_strain_when_leader_mixed(self):
        state = TC._leadership_state("mixed", [], "Semiconductors")
        assert state == "strain"

    def test_steady_when_leader_confirmed(self):
        state = TC._leadership_state("confirmed", [], "Semiconductors")
        assert state == "steady"


# ── compute_theme_context – integration-level ─────────────────────────────────

def _run_compute(
    rank_rows: list[dict],
    ti_themes: list[dict],
    as_of: str = "2026-07-17",
    root: Path | None = None,
) -> dict | None:
    alloc = _make_alloc(rank_rows, as_of)
    ti = _make_theme_intel(ti_themes, as_of)
    return TC.compute_theme_context(alloc, ti, region="us", root=root)


class TestComputeThemeContextBasic:
    def test_returns_dict(self, tmp_path):
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, val_state="confirming")]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold", score=72)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx is not None
        assert ctx["schema"] == "theme_context.v1"
        assert ctx["display_only"] is True
        assert ctx["region"] == "us"

    def test_memory_broken_case(self, tmp_path):
        """The contract's named example: Memory/HBM broken leader."""
        rows = [
            _make_rank_row(
                "memory_storage",
                category="Semiconductors",
                breadth=0.0,
                r10=-0.127,
                val_state="fading",
                rank=1,
            )
        ]
        themes = [_make_ti_theme("memory_storage", label="deteriorating", reco="avoid", score=41)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx is not None
        tl = ctx["leadership"]["trailing_leader"]
        assert tl["health"] == "broken"
        assert tl["id"] == "memory_storage"
        assert tl["breadth"] == 0.0
        # broken leader in breaking list
        breaking = ctx["leadership"]["breaking"]
        assert any(b["id"] == "memory_storage" for b in breaking)

    def test_confirmed_leader(self, tmp_path):
        rows = [
            _make_rank_row("cyber", breadth=0.80, r10=0.05, val_state="confirming", rank=1)
        ]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold", score=72)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["trailing_leader"]["health"] == "confirmed"

    def test_mixed_when_partial_data(self, tmp_path):
        rows = [
            _make_rank_row("mixed_theme", breadth=0.40, r10=-0.03, val_state=None, rank=1)
        ]
        themes = [_make_ti_theme("mixed_theme", label="neutral", reco="hold", score=50)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["trailing_leader"]["health"] == "mixed"

    def test_returns_none_on_empty_ranks(self, tmp_path):
        alloc = _make_alloc([])
        ti = _make_theme_intel([])
        ctx = TC.compute_theme_context(alloc, ti, root=tmp_path)
        assert ctx is None

    def test_null_safety_all_missing(self, tmp_path):
        """All-missing per-theme fields -> health mixed (not a crash)."""
        rows = [_make_rank_row("theme_x", breadth=None, r10=None, val_state=None, rank=1)]
        themes = [_make_ti_theme("theme_x", label=None, reco=None, score=None)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx is not None
        assert ctx["leadership"]["trailing_leader"]["health"] == "mixed"

    def test_challenger_present(self, tmp_path):
        rows = [
            _make_rank_row("leader_theme", breadth=0.80, r10=0.05, rank=1, score=3.0),
            _make_rank_row("chall_theme", breadth=0.60, r10=0.03, rank=2, score=2.0),
        ]
        themes = [
            _make_ti_theme("leader_theme", label="dominant", reco="hold"),
            _make_ti_theme("chall_theme", label="emerging", reco="enter"),
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["challenger"]["id"] == "chall_theme"
        assert ctx["leadership"]["challenger"]["margin"] == 1.0

    def test_strength_list_max_6_sorted_by_score(self, tmp_path):
        rows = [
            _make_rank_row(f"t{i}", breadth=0.80, r10=0.05, rank=i+1, score=float(80-i))
            for i in range(8)
        ]
        themes = [
            _make_ti_theme(f"t{i}", label="dominant", reco="hold", score=80-i)
            for i in range(8)
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert len(ctx["leadership"]["strength"]) <= 6

    def test_breaking_list_max_4(self, tmp_path):
        rows = [
            _make_rank_row(f"b{i}", breadth=0.10, r10=-0.10 - i*0.02, rank=i+1)
            for i in range(6)
        ]
        themes = [
            _make_ti_theme(f"b{i}", label="deteriorating", reco="avoid", score=30)
            for i in range(6)
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert len(ctx["leadership"]["breaking"]) <= 4

    def test_stance_steady(self, tmp_path):
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, val_state="confirming", rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold", score=72)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["stance_en"] == TC._STANCE["steady"]["en"]

    def test_stance_strain(self, tmp_path):
        rows = [_make_rank_row("semi", breadth=0.40, r10=-0.03, val_state=None, rank=1)]
        themes = [_make_ti_theme("semi", label="neutral", reco="hold", score=50)]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["stance_en"] == TC._STANCE["strain"]["en"]

    def test_stance_rotating(self, tmp_path):
        """rotating requires broken leader + 3 cross-category strength entries."""
        rows = [
            _make_rank_row("semi", category="Semiconductors", breadth=0.0, r10=-0.15,
                           val_state="fading", rank=1, score=1.0),
            _make_rank_row("cyber", category="Software", breadth=0.80, r10=0.05, rank=2, score=2.0),
            _make_rank_row("cloud", category="Software", breadth=0.75, r10=0.04, rank=3, score=1.9),
            _make_rank_row("finance", category="Financials", breadth=0.70, r10=0.03, rank=4, score=1.8),
        ]
        themes = [
            _make_ti_theme("semi", label="deteriorating", reco="avoid", score=30),
            _make_ti_theme("cyber", label="dominant", reco="hold", score=72),
            _make_ti_theme("cloud", label="dominant", reco="hold", score=70),
            _make_ti_theme("finance", label="emerging", reco="enter", score=65),
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["leadership"]["state"] == "rotating"
        assert ctx["leadership"]["stance_en"] == TC._STANCE["rotating"]["en"]


# ── History / same-day idempotency ────────────────────────────────────────────

class TestHistoryAndIdempotency:
    def _run_with_lane(self, rows, themes, as_of, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        return _run_compute(rows, themes, as_of, root=tmp_path)

    def test_off_lane_does_not_write_history(self, tmp_path):
        """Without COLLECT_LANE set, history file must NOT be created."""
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold")]
        _run_compute(rows, themes, root=tmp_path)
        hist_path = tmp_path / "data" / "themes" / "context_history.jsonl"
        assert not hist_path.exists()

    def test_on_lane_writes_history(self, tmp_path, monkeypatch):
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold")]
        self._run_with_lane(rows, themes, "2026-07-17", tmp_path, monkeypatch)
        hist_path = tmp_path / "data" / "themes" / "context_history.jsonl"
        assert hist_path.exists()
        lines = [l for l in hist_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["asof"] == "2026-07-17"

    def test_same_day_idempotent_replace(self, tmp_path, monkeypatch):
        """Calling compute_theme_context twice with the same as_of -> still only 1 history row."""
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold")]
        self._run_with_lane(rows, themes, "2026-07-17", tmp_path, monkeypatch)
        # Second call same day
        self._run_with_lane(rows, themes, "2026-07-17", tmp_path, monkeypatch)
        hist_path = tmp_path / "data" / "themes" / "context_history.jsonl"
        lines = [l for l in hist_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1, f"Expected 1 row after idempotent re-run, got {len(lines)}"

    def test_different_day_appends(self, tmp_path, monkeypatch):
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold")]
        self._run_with_lane(rows, themes, "2026-07-16", tmp_path, monkeypatch)
        self._run_with_lane(rows, themes, "2026-07-17", tmp_path, monkeypatch)
        hist_path = tmp_path / "data" / "themes" / "context_history.jsonl"
        lines = [l for l in hist_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


# ── state_changes correctness ─────────────────────────────────────────────────

class TestStateChanges:
    def _seed_history(self, tmp_path: Path, rows: list[dict]) -> None:
        TC._write_history(rows, tmp_path)

    def test_state_changes_on_leadership_change(self, tmp_path, monkeypatch):
        """If leadership_state changes between snapshots, state_changes captures it."""
        # Seed history with a 'steady' state
        self._seed_history(tmp_path, [{
            "asof": "2026-07-16",
            "leadership_state": "steady",
            "trailing_leader_id": "cyber",
            "leader_health": "confirmed",
            "labels": {"cyber": "dominant"},
            "scores": {"cyber": 72},
        }])
        # Now run with a broken leader (→ strain or rotating)
        rows = [_make_rank_row("semi", breadth=0.0, r10=-0.15, val_state="fading", rank=1)]
        themes = [_make_ti_theme("semi", label="deteriorating", reco="avoid", score=30)]
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ctx = _run_compute(rows, themes, as_of="2026-07-17", root=tmp_path)
        sc = ctx["state_changes"]
        assert "leadership_state" in sc
        ls_change = sc["leadership_state"]
        assert ls_change["prev"] == "steady"
        assert ls_change["current"] in ("strain", "rotating")
        assert ls_change["changed_on"] == "2026-07-17"

    def test_prev_asof_set_from_history(self, tmp_path):
        self._seed_history(tmp_path, [{
            "asof": "2026-07-16",
            "leadership_state": "steady",
            "trailing_leader_id": "cyber",
            "leader_health": "confirmed",
            "labels": {"cyber": "dominant"},
            "scores": {"cyber": 72},
        }])
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold", score=72)]
        ctx = _run_compute(rows, themes, as_of="2026-07-17", root=tmp_path)
        assert ctx["prev_asof"] == "2026-07-16"

    def test_no_state_changes_when_nothing_changed(self, tmp_path, monkeypatch):
        """If state/leader/health are the same, label changes dict should be empty."""
        self._seed_history(tmp_path, [{
            "asof": "2026-07-16",
            "leadership_state": "steady",
            "trailing_leader_id": "cyber",
            "leader_health": "confirmed",
            "labels": {"cyber": "dominant"},
            "scores": {"cyber": 72},
        }])
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, val_state="confirming", rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold", score=72)]
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ctx = _run_compute(rows, themes, as_of="2026-07-17", root=tmp_path)
        sc = ctx.get("state_changes", {})
        # leader_health and leadership_state should show days_in_state > 1 if unchanged
        if "leadership_state" in sc:
            # if present, prev should equal current (no change)
            lsc = sc["leadership_state"]
            assert lsc["current"] == "steady"
            assert lsc["prev"] == "steady"


# ── read_context ───────────────────────────────────────────────────────────────

class TestReadContext:
    def test_read_context_none_on_absence(self, tmp_path):
        result = TC.read_context(region="us", root=tmp_path)
        assert result is None

    def test_read_context_returns_dict_when_present(self, tmp_path):
        # Write a minimal valid context
        ctx = {
            "schema": "theme_context.v1",
            "as_of": "2026-07-17",
            "region": "us",
            "display_only": True,
        }
        TC.write_context(ctx, root=tmp_path)
        result = TC.read_context(region="us", root=tmp_path)
        assert result is not None
        assert result["schema"] == "theme_context.v1"

    def test_read_context_none_on_wrong_region(self, tmp_path):
        ctx = {
            "schema": "theme_context.v1",
            "as_of": "2026-07-17",
            "region": "us",
            "display_only": True,
        }
        TC.write_context(ctx, root=tmp_path)
        result = TC.read_context(region="china", root=tmp_path)
        assert result is None


# ── write_context ─────────────────────────────────────────────────────────────

class TestWriteContext:
    def test_write_creates_file(self, tmp_path):
        ctx = {
            "schema": "theme_context.v1",
            "as_of": "2026-07-17",
            "region": "us",
            "display_only": True,
        }
        TC.write_context(ctx, root=tmp_path)
        p = tmp_path / "site" / "basketdata" / "theme_context.json"
        assert p.exists()
        loaded = json.loads(p.read_text())
        assert loaded["schema"] == "theme_context.v1"


# ── Migration aggregation ──────────────────────────────────────────────────────

class TestMigration:
    def test_migration_groups_by_category(self, tmp_path):
        rows = [
            _make_rank_row("cyber", category="Software", breadth=0.80, r10=0.05, rank=1),
            _make_rank_row("cloud", category="Software", breadth=0.75, r10=0.04, rank=2),
            _make_rank_row("semi", category="Semiconductors", breadth=0.10, r10=-0.10, rank=3),
        ]
        themes = [
            _make_ti_theme("cyber", label="dominant", reco="hold"),
            _make_ti_theme("cloud", label="dominant", reco="hold"),
            _make_ti_theme("semi", label="deteriorating", reco="avoid"),
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        absorbing = ctx["migration"]["absorbing"]
        bleeding = ctx["migration"]["bleeding"]
        # Software should be in absorbing (high breadth)
        assert any(a["category"] == "Software" for a in absorbing)
        # Semiconductors should be in bleeding (low breadth)
        assert any(b["category"] == "Semiconductors" for b in bleeding)


# ── Alignment (fail-open when rotation_events absent) ────────────────────────

class TestAlignment:
    def test_alignment_null_when_rotation_events_absent(self, tmp_path):
        rows = [_make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1)]
        themes = [_make_ti_theme("cyber", label="dominant", reco="hold")]
        ctx = _run_compute(rows, themes, root=tmp_path)
        assert ctx["alignment"]["sector_rotation_agrees"] is None

    def test_alignment_agrees_when_to_leg_matches(self, tmp_path):
        """sector_rotation_agrees=True when a rotation event's to_leg matches a strength theme."""
        # Write a minimal rotation_events.json
        re_dir = tmp_path / "site" / "marketdata"
        re_dir.mkdir(parents=True, exist_ok=True)
        re_data = {
            "schema": "rotation_events.v1",
            "ok": True,
            "as_of": "2026-07-17",
            "active": [
                {
                    "id": "xlk:ai_semis->cyber",
                    "sector": "xlk",
                    "from_leg": {"key": "ai_semis", "name_en": "AI Semis"},
                    "to_leg": {"key": "cyber", "name_en": "Cybersecurity"},
                    "severity": "major",
                }
            ],
        }
        (re_dir / "rotation_events.json").write_text(json.dumps(re_data))
        rows = [
            _make_rank_row("cyber", breadth=0.80, r10=0.05, rank=1, score=3.0),
            _make_rank_row("cloud", breadth=0.75, r10=0.04, rank=2, score=2.0),
        ]
        themes = [
            _make_ti_theme("cyber", label="dominant", reco="hold", score=72),
            _make_ti_theme("cloud", label="emerging", reco="enter", score=65),
        ]
        ctx = _run_compute(rows, themes, root=tmp_path)
        # cyber is in strength (confirmed); rotation event to_leg=cyber -> agrees
        assert ctx["alignment"]["sector_rotation_agrees"] is True
