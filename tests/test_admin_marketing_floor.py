"""Marketing floor / model desk / X lanes admin panels.

These panels exist because the console was rendering what succeeded and hiding
what leaked, so a jammed factory read as a quiet one. The tests pin the
properties that make them trustworthy:

* NEVER-RAISE on a missing, empty, or malformed repo (a panel that throws puts
  the operator back behind a tinted window).
* The break point is the station losing the most POSTS, not the biggest share —
  a 2-in/0-out tail station is a 100% loss and nobody's emergency.
* Every publisher counter renders, including ones this module has no plain word
  for, so a new engine gate cannot ship invisible.
* ``posted`` leads the dispatch ledger even at zero.
* No secret VALUE crosses the panel boundary (capability redline).
"""
from __future__ import annotations

import json

import pytest

from admin import marketing_floor as mf


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    """A miniature marketing repo: 10 planned posts, 4 cleared, 2 enqueued."""
    plan = {
        "as_of": "2026-07-29",
        "produced_at": "2026-07-29T03:00:00Z",
        "summary": {"total_posts": 99},          # deliberately wrong vs the queue
        "accounts": [
            {
                "id": "flagship", "name": "Flagship",
                "queue": [
                    {"id": "post-flagship-001", "type": "macro", "account": "flagship",
                     "headline": "Where it stands", "status": "drafted",
                     "_copy_mode": "llm:sol"},
                    {"id": "post-flagship-002", "type": "signal", "account": "flagship",
                     "headline": "A signal", "status": "drafted",
                     "_copy_mode": "llm:sol"},
                ],
            },
            {
                "id": "kelly", "name": "Kelly",
                "queue": [
                    # three held as near-dups of the SAME flagship post
                    {"id": "post-kelly-001", "type": "macro", "account": "kelly",
                     "status": "quarantined", "headline": "k1",
                     "sentinel_reasons": ["near_dup:post-flagship-001"],
                     "_copy_mode": "deterministic"},
                    {"id": "post-kelly-002", "type": "macro", "account": "kelly",
                     "status": "quarantined", "headline": "k2",
                     "sentinel_reasons": ["near_dup:post-flagship-001"],
                     "_copy_mode": "deterministic"},
                    {"id": "post-kelly-003", "type": "macro", "account": "kelly",
                     "status": "quarantined", "headline": "k3",
                     "sentinel_reasons": ["near_dup:post-flagship-001"],
                     "_copy_mode": "deterministic"},
                    {"id": "post-kelly-004", "type": "event", "account": "kelly",
                     "status": "quarantined", "headline": "k4",
                     "sentinel_reasons": ["cadence_cap_daily"],
                     "_copy_mode": "deterministic"},
                    # no writer ever reached this one
                    {"id": "post-kelly-005", "type": "signal", "account": "kelly",
                     "status": "quarantined", "headline": "k5"},
                    {"id": "post-kelly-006", "type": "chart", "account": "kelly",
                     "status": "drafted", "headline": "k6", "_copy_mode": "llm:sol"},
                    {"id": "post-kelly-007", "type": "chart", "account": "kelly",
                     "status": "drafted", "headline": "k7", "_copy_mode": "llm:sol"},
                ],
            },
        ],
    }
    _write(tmp_path / "data/marketing/content_plan.json", plan)
    _write(tmp_path / "data/marketing/sentinel_report.json", {
        "as_of": "2026-07-29",
        "counts": {"items": 9, "passed": 4,
                   "quarantined_policy": 4, "quarantined_overflow": 1},
        "checks": {"kill_switch": {"accounts_disabled": ["receipts", "theme_desk"]}},
    })
    _write_lines(tmp_path / "data/marketing/outbox/items.jsonl", [
        {"id": "ob-1", "as_of": "2026-07-29", "account": "flagship", "status": "queued"},
        {"id": "ob-2", "as_of": "2026-07-29", "account": "kelly", "status": "queued"},
        {"id": "ob-old", "as_of": "2026-07-01", "account": "kelly", "status": "posted"},
    ])
    _write_lines(tmp_path / "data/marketing/outbox/status_ledger.jsonl", [
        {"id": "ob-1", "to": "posted", "at": "2026-07-29T22:00:00Z"},
        {"id": "ob-2", "to": "quarantined", "at": "2026-07-29T22:00:00Z"},
    ])
    _write_lines(tmp_path / "data/marketing/outbox/activity.jsonl", [{
        "at": "2026-07-29T23:00:00Z", "lane": "publisher_live", "backend": "buffer",
        "posted": 0, "failed": 0, "skipped_cap": 3, "tape_skipped": 1,
        "auto_approved": 2, "halted_accounts": [],
        # a counter this module has no plain word for — must still render
        "brand_new_engine_gate": 5,
    }])
    return tmp_path


# ---------------------------------------------------------------------------
# the line
# ---------------------------------------------------------------------------
def test_line_counts_and_losses(repo):
    d = mf.floor(repo)
    assert d["ok"] is True
    stations = {s["id"]: s for s in d["line"]}

    assert stations["planned"]["out"] == 9            # the queue, not the header
    assert d["plan_claimed_total"] == 99             # the drift is reported…
    assert stations["planned"]["detail"]             # …and shown on the station

    assert stations["written"]["out"] == 8           # one post has no _copy_mode
    assert stations["written"]["lost"] == 1
    assert stations["cleared"]["out"] == 4
    assert stations["enqueued"]["out"] == 2         # today's items only
    assert stations["enqueued"]["lost"] == 2        # cleared 4 → enqueued 2


def test_break_point_is_the_biggest_post_loss_not_the_biggest_share(repo):
    """A tail station losing 2 of 2 must not outrank a station losing more."""
    d = mf.floor(repo)
    stations = {s["id"]: s for s in d["line"]}
    losses = {k: v["lost"] for k, v in stations.items() if v["lost"]}
    assert d["break_at"] == max(losses, key=lambda k: losses[k])
    # the gate loses 4 of 8 here — more posts than any later station
    assert d["break_at"] == "cleared"


def test_never_raises_on_an_empty_repo(tmp_path):
    for fn in (mf.floor, mf.models, mf.lanes):
        out = fn(tmp_path)
        assert out["ok"] is True, f"{fn.__name__} degraded to not-ok on an empty repo"


def test_never_raises_on_malformed_files(tmp_path):
    p = tmp_path / "data/marketing"
    p.mkdir(parents=True)
    (p / "content_plan.json").write_text("{ this is not json", encoding="utf-8")
    (p / "sentinel_report.json").write_text("[]", encoding="utf-8")
    (p / "hot_tape_pack.json").write_text("null", encoding="utf-8")
    for fn in (mf.floor, mf.models, mf.lanes):
        assert fn(tmp_path)["ok"] is True


# ---------------------------------------------------------------------------
# loss detail
# ---------------------------------------------------------------------------
def test_attractor_ranking_names_the_post_that_killed_the_others(repo):
    top = mf.floor(repo)["loss"]["attractors"][0]
    assert top["post_id"] == "post-flagship-001"
    assert top["killed"] == 3
    assert top["account"] == "flagship"
    assert "kelly" in top["victim_desks"]


def test_desk_yield_sorts_worst_first(repo):
    rows = mf.floor(repo)["loss"]["by_desk"]
    assert [r["account"] for r in rows] == ["kelly", "flagship"]
    # yields are display values, rounded to 4dp by the panel
    assert rows[0]["yield"] == pytest.approx(2 / 7, abs=1e-4)
    assert rows[0]["held_near_dup"] == 3
    assert rows[0]["held_cap"] == 1
    assert rows[-1]["yield"] == 1.0


def test_gate_reasons_collapse_near_dup_into_one_family(repo):
    fams = {r["reason"]: r["n"] for r in mf.floor(repo)["loss"]["gate_reasons"]}
    assert fams["near_dup"] == 3          # not three separate near_dup:<id> rows
    assert fams["cadence_cap_daily"] == 1


# ---------------------------------------------------------------------------
# authorship
# ---------------------------------------------------------------------------
def test_authorship_separates_template_from_no_writer(repo):
    a = mf.floor(repo)["authorship"]
    assert a["llm_posts"] == 4
    assert a["template_on_planned_kind"] == 4      # the deterministic ones
    assert a["no_writer_on_planned_kind"] == 1     # the one with no _copy_mode
    assert a["by_mode"]["no writer reached"] == 1


def test_template_and_no_writer_are_separate_blockers(repo):
    titles = [b["title"] for b in mf.floor(repo)["blockers"]]
    assert any("template" in t.lower() for t in titles)
    assert any("never reached a writer" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# dispatch ledger
# ---------------------------------------------------------------------------
def test_posted_leads_the_ledger_even_at_zero(repo):
    lines = mf.floor(repo)["dispatch_ledger"]["lines"]
    assert lines[0]["key"] == "posted"
    assert lines[0]["n"] == 0


def test_an_unmapped_counter_still_renders(repo):
    """A new engine counter must not vanish because this table wasn't updated."""
    lines = {ln["key"]: ln for ln in mf.floor(repo)["dispatch_ledger"]["lines"]}
    assert "brand_new_engine_gate" in lines
    row = lines["brand_new_engine_gate"]
    assert row["n"] == 5
    assert row["mapped"] is False
    assert row["word"] == "brand new engine gate"


def test_ledger_loss_total_excludes_informational_counters(repo):
    led = mf.floor(repo)["dispatch_ledger"]
    # skipped_cap 3 + tape_skipped 1 are losses; auto_approved 2 is not
    assert led["lost_total"] == 4


def test_disabled_desks_surface_as_a_blocker(repo):
    hit = [b for b in mf.floor(repo)["blockers"] if "switched off" in b["title"]]
    assert hit and "receipts" in hit[0]["why"]


# ---------------------------------------------------------------------------
# model desk
# ---------------------------------------------------------------------------
def test_every_llm_lane_is_reported_even_without_config(tmp_path):
    d = mf.models(tmp_path)
    ids = [lane["id"] for lane in d["lanes"]]
    assert ids == [spec["id"] for spec in mf._LLM_LANES]
    # with no config on disk, every lane falls back to its code default and says so
    assert all(lane["source"] == "code default" for lane in d["lanes"])
    assert all(lane["first_choice"] == "codex" for lane in d["lanes"]), (
        "codex-first must be the CODE default, not only the config value — a "
        "dropped config key must not silently restore Claude-first")


def test_pool_and_single_key_providers_are_not_mixed(tmp_path):
    pool = mf.models(tmp_path)["pool"]
    if not pool.get("available"):
        pytest.skip("key_pool not importable in this environment")
    pool_ids = {k["key_id"] for k in pool["keys"]}
    prov_ids = {p["key_id"] for p in pool.get("providers") or []}
    assert not (pool_ids & prov_ids)
    # "N of M ready" must count only balanced pool keys
    assert pool["total"] == len(pool["keys"])
    assert "codex_account" not in pool_ids


def test_absent_keys_report_no_load(tmp_path):
    """A key that is not set here must not read as idle capacity."""
    pool = mf.models(tmp_path)["pool"]
    if not pool.get("available"):
        pytest.skip("key_pool not importable in this environment")
    for row in list(pool["keys"]) + list(pool.get("providers") or []):
        if not row["present"]:
            assert row["window_5h_est_tokens"] is None
            assert row["weekly_est_tokens"] is None


def test_no_secret_value_crosses_the_panel_boundary(tmp_path, monkeypatch):
    """Capability redline: names and load only, never a token."""
    secret = "sk-ant-oat01-THIS-MUST-NEVER-APPEAR-IN-A-PANEL"
    for env in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY", "BUFFER_TOKEN", "CODEX_API_KEY"):
        monkeypatch.setenv(env, secret)
    blob = json.dumps(mf.models(tmp_path)) + json.dumps(mf.floor(tmp_path))
    assert secret not in blob
    assert "THIS-MUST-NEVER-APPEAR" not in blob


# ---------------------------------------------------------------------------
# lanes
# ---------------------------------------------------------------------------
def test_lanes_sort_problems_before_healthy_ones(repo):
    rows = mf.lanes(repo)["lanes"]
    states = [r["state"] for r in rows]
    healthy = {"live", "shadow", "accruing"}
    first_healthy = next((i for i, s in enumerate(states) if s in healthy), len(states))
    assert all(s not in healthy for s in states[:first_healthy])


def test_a_stale_tape_pack_is_reported_stale_not_live(repo):
    _write(repo / "data/marketing/hot_tape_pack.json",
           {"trade_date": "2020-01-02", "n_tickers": 5, "built_at": "2020-01-02T01:00:00Z"})
    lane = next(r for r in mf.lanes(repo)["lanes"] if r["id"] == "hot_tape")
    assert lane["state"] == "stale"
    assert "days old" in lane["state_word"]


class TestAuditorBlockPath:
    """The plan's copy census lives at `content.copy`, NOT `report.copy`.

    Reading the wrong path made the panel report "not run yet" on a plan whose
    auditor had cut 10 posts — a silent null dressed as an honest empty state,
    which is the exact defect this module exists to eliminate. Caught only by
    reading a real plan, so pin the path.
    """

    def test_it_reads_content_copy_not_report_copy(self, tmp_path):
        from admin.marketing_floor import _auditor_block
        plan = {"content": {"copy": {"auditor": {
            "ran": True, "kept": 19, "cut": 10, "unaudited": 0,
            "cuts": [{"id": "p1", "account": "flagship", "kind": "chart",
                      "codes": ["repetitive"], "note": "dupe", "text": "x"}],
            "notes": {"flagship": "formulaic"},
        }}}}
        blk = _auditor_block(plan)
        assert blk["present"] is True
        assert blk["kept"] == 19 and blk["cut"] == 10
        assert blk["cut_share"] == pytest.approx(10 / 29, abs=1e-4)

    def test_a_plan_with_only_a_report_key_is_not_mistaken_for_data(self):
        """The old wrong path must not silently start working again."""
        from admin.marketing_floor import _auditor_block
        assert _auditor_block({"report": {"copy": {"auditor": {"kept": 5}}}})["present"] is False

    def test_high_cut_share_points_upstream(self):
        """A cut rate above a third is the supply failing, not the gate."""
        from admin.marketing_floor import _auditor_block
        blk = _auditor_block({"content": {"copy": {"auditor": {
            "ran": True, "kept": 10, "cut": 10, "cuts": [], "notes": {}}}}})
        assert "supply" in blk["verdict"]


# ─────────────────────────────────────────────────────────────────────────────
# "its like a factory with its window panes all tinted and me as the CEO unable
# to see the inside of the factory. Work to let me see the factory."
#
# The Floor renders an unmapped counter under its raw name rather than dropping
# it, so a new gate is never INVISIBLE — but a raw slug is still a tinted pane.
# This walks the publisher's own activity row so a gate cannot ship wordless.
# ─────────────────────────────────────────────────────────────────────────────
def test_every_publisher_counter_has_plain_words_on_the_floor():
    import re
    from pathlib import Path

    from admin.marketing_floor import _ACTIVITY_WORDS

    src = Path("scripts/marketing_publisher.py").read_text(encoding="utf-8")
    start = src.index('"lane": "publisher_live"')
    block = src[start:src.index("})", start)]
    keys = set(re.findall(r'^\s+"([a-z_0-9]+)":', block, re.M))

    # Structural fields, not loss counters: these name the run or carry lists,
    # and the Floor renders them through its own header rather than the ledger.
    STRUCTURAL = {"at", "lane", "backend", "cap", "account",
                  "dark_accounts", "halted_accounts", "parked_dark"}

    assert len(keys) > 20, f"only {len(keys)} activity keys parsed — the scrape broke"
    missing = sorted(k for k in keys if k not in _ACTIVITY_WORDS and k not in STRUCTURAL)
    assert not missing, (
        "publisher counters with no plain-word label on the Floor "
        f"(they would render as raw slugs): {missing}"
    )


def test_the_2026_07_30_gates_are_named_in_operator_language():
    """Each of the four new gates says WHY in words, and names no internals."""
    from admin.marketing_floor import _ACTIVITY_WORDS

    for key in ("quarantined_bare_cashtag", "quarantined_unknown_cashtag",
                "quarantined_voice_laws", "quarantined_run_duplicate"):
        words = _ACTIVITY_WORDS[key]
        assert words and words == words.lower() or words[0].islower(), words
        # No slugs, no internal names, no study jargon in the operator's view.
        for banned in ("cashtag_", "_violations", "validate_", "queued_voice",
                       "jaccard", "regex"):
            assert banned not in words.lower(), (key, words)
