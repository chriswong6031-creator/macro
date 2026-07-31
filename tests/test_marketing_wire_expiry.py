"""A wire item that nobody dispatched must not sit queued forever.

THE LIVE CASE, 2026-07-31. Two publish-time mover items (AMZN and COIN) were
created at 15:32:53Z and were still `queued` with ZERO status-ledger rows eight
hours later. Their copy says "right now" about a tape that closed. The operator's
audit had to quarantine them by hand alongside 14 older siblings.

Nothing swept them, and there were two independent reasons why:

  * :func:`outbox.expire_stale_planned` filters on ``provenance ==
    "content_studio"``, and its comment asserts that "the wire lanes
    (press/fastlane) and weekend_levels manage their own retirement". They do
    not — no such reaper existed anywhere in the repo;
  * even without that filter it would have skipped them, because it ages from
    ``scheduled_at`` and its first act on ``scheduled_at == "immediate"`` is
    ``continue`` ("no slot to be late for") — and *every* row the fast lanes
    write is immediate.

Both are pinned below, because closing one and leaving the other would produce a
reaper that runs, reports 0, and looks healthy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

_NOW = datetime(2026, 7, 31, 23, 30, 0, tzinfo=timezone.utc)

# Deeply distinct copy: the enqueue-time near-dup guard compares same-account
# texts inside a 7-day window at jaccard 0.7, so an indexed "item {i}" fixture
# would be refused as a duplicate and the test would pass vacuously on an empty
# queue (memory: vacuous-green presence vs coverage).
_TEXTS = {
    "amzn": "$AMZN is down 4.1% right now, its worst intraday slide since April.",
    "coin": "$COIN just gave back 6.8%, erasing every gain it made this week.",
    "sector": "Insurance carriers: 7 of 7 lower, median -3.9% so far this session.",
    "press": "The BEA revised second quarter real GDP growth down to 1.5 percent.",
    "read": "My read on today's move: breadth cracked long before the index did.",
    "plan": "Semiconductor equipment names caught a bid on upbeat foundry capex.",
    "old": "Regional bank shares stabilized after last week's deposit scare eased.",
}


def _seed(tmp_path: Path, *, key: str, kind: str, provenance: str,
          hours_old: float, status: str = "queued",
          scheduled_at: str = "immediate", account: str = "flagship") -> str:
    """Enqueue one item BORN ``hours_old`` hours before _NOW. Returns its id."""
    from engine.marketing.outbox import enqueue, make_item, transition

    born = _NOW - timedelta(hours=hours_old)
    item = make_item(
        account=account, kind=kind, text=_TEXTS[key],
        as_of=born.strftime("%Y-%m-%d"), scheduled_at=scheduled_at,
        provenance=provenance, now=born,
    )
    rc = enqueue(item, root=tmp_path, max_per_account_day=99)
    assert rc == "queued", f"fixture refused by the enqueue guards: {rc}"
    if status != "queued":
        assert transition(item["id"], status, actor="test", root=tmp_path, now=born)
    return item["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. The reaper itself
# ─────────────────────────────────────────────────────────────────────────────

class TestTheWireReaper:
    def test_the_eight_hour_mover_is_retired_and_the_thirty_minute_one_is_not(
            self, tmp_path):
        """The live shape, both halves.

        The 8h item is the AMZN/COIN stall. The 30-minute item is the control
        that keeps this from being a queue-shredder: a reaper that cannot tell
        those two apart would destroy the lane it is protecting.
        """
        from engine.marketing.outbox import expire_stale_wire, fold_state

        stale = _seed(tmp_path, key="amzn", kind="mover",
                      provenance="publisher_live_movers", hours_old=8.0)
        fresh = _seed(tmp_path, key="coin", kind="mover",
                      provenance="publisher_live_movers", hours_old=0.5)

        out = expire_stale_wire(tmp_path, now=_NOW)

        assert out["expired"] == 1 and out["ids"] == [stale]
        assert out["by_kind"] == {"mover": 1}
        status = fold_state(tmp_path)["status"]
        assert status[stale] == "quarantined"
        assert status[fresh] == "queued"

    def test_the_note_names_the_reason_verbatim(self, tmp_path):
        """The admin quarantine view renders the note; a greppable slug is how
        "why did the movers vanish" is answerable without reading this file."""
        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="sector", kind="theme_list",
                    provenance="publisher_live_movers", hours_old=9.0)
        expire_stale_wire(tmp_path, now=_NOW)

        row = fold_state(tmp_path)["last"][iid]
        assert row["actor"] == "wire_expiry"
        assert row["note"].startswith("expired_stale_wire:"), row["note"]
        assert "9.0h" in row["note"] and "ttl 3h" in row["note"], row["note"]

    def test_an_immediate_schedule_does_not_exempt_a_wire_item(self, tmp_path):
        """HALF THE DEFECT, pinned on its own.

        Every fixture here carries scheduled_at="immediate" because every real
        wire row does. expire_stale_planned skips those outright, so a reaper
        that reused its age function would report 0 forever and read healthy.
        """
        from engine.marketing.outbox import (
            expire_stale_planned, expire_stale_wire)

        _seed(tmp_path, key="press", kind="breaking", provenance="press_lane",
              hours_old=8.0)

        assert expire_stale_planned(tmp_path, now=_NOW)["expired"] == 0
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 1

    def test_a_press_breaking_item_is_in_scope(self, tmp_path):
        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="press", kind="breaking",
                    provenance="press_lane", hours_old=4.0)
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 1
        assert fold_state(tmp_path)["status"][iid] == "quarantined"

    def test_the_planned_lane_is_left_to_its_own_reaper(self, tmp_path):
        """Scope discipline in the other direction: a content_studio item at 8h
        is not late (its ladder slot may be tomorrow morning), and quarantining
        it here would be this reaper reaching into the nightly's lane."""
        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="plan", kind="signal",
                    provenance="content_studio", hours_old=8.0,
                    scheduled_at="2026-08-01T14:00:00Z")
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 0
        assert fold_state(tmp_path)["status"][iid] == "queued"

    def test_the_publish_time_daily_read_keeps_the_longer_default_ttl(self, tmp_path):
        """kind=event on a wire provenance is not a five-minute tape claim, so
        it gets 12h, not 3h. Pinned because a single flat TTL would silently
        shred the after-close read every evening."""
        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="read", kind="event",
                    provenance="publisher_live_movers", hours_old=8.0)
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 0
        assert fold_state(tmp_path)["status"][iid] == "queued"
        # …and it is not immortal either.
        assert expire_stale_wire(
            tmp_path, now=_NOW + timedelta(hours=5))["expired"] == 1

    def test_an_approved_item_is_reaped_too(self, tmp_path):
        """Approved-but-never-dispatched is the SAME stall — arguably worse, the
        item cleared every gate and still went nowhere."""
        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="amzn", kind="mover",
                    provenance="publisher_live_movers", hours_old=8.0,
                    status="approved")
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 1
        assert fold_state(tmp_path)["status"][iid] == "quarantined"

    def test_a_posted_item_is_never_touched(self, tmp_path):
        """`posted` is terminal-except-recall and the reaper must never reach a
        post that already went out — that would be a false quarantine on the
        record of a live tweet."""
        from engine.marketing.outbox import expire_stale_wire, fold_state, transition

        iid = _seed(tmp_path, key="press", kind="breaking",
                    provenance="press_lane", hours_old=8.0, status="approved")
        assert transition(iid, "posted", actor="test", root=tmp_path)
        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 0
        assert fold_state(tmp_path)["status"][iid] == "posted"

    def test_an_unparseable_birth_stamp_never_costs_a_post(self, tmp_path):
        """Fail OPEN, the same rule _item_age_days states in the publisher: a
        malformed stamp must never be the reason a post is destroyed."""
        import json

        from engine.marketing.outbox import expire_stale_wire, fold_state

        iid = _seed(tmp_path, key="coin", kind="mover",
                    provenance="publisher_live_movers", hours_old=8.0)
        path = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
        rows = [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            if row.get("id") == iid:
                row["created_at"] = "not-a-timestamp"
                row["as_of"] = "also-not-a-timestamp"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        assert expire_stale_wire(tmp_path, now=_NOW)["expired"] == 0
        assert fold_state(tmp_path)["status"][iid] == "queued"

    def test_a_zero_ttl_opts_a_kind_out(self, tmp_path):
        from engine.marketing.outbox import expire_stale_wire

        _seed(tmp_path, key="amzn", kind="mover",
              provenance="publisher_live_movers", hours_old=99.0)
        assert expire_stale_wire(
            tmp_path, now=_NOW, ttl_hours_by_kind={"mover": 0})["expired"] == 0

    def test_it_never_raises_on_an_unreadable_root(self, tmp_path):
        """Housekeeping must not be able to stop a dispatch."""
        from engine.marketing.outbox import expire_stale_wire

        assert expire_stale_wire(tmp_path / "nope", now=_NOW)["expired"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. The publisher actually runs it, and the Floor can say so in words
# ─────────────────────────────────────────────────────────────────────────────

class TestTheSweepRunsTheReaperAndReportsIt:
    """A reaper nothing calls is the stall with extra steps."""

    def _publish_cfg(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "marketing.yml").write_text(
            "sentinel:\n"
            "  max_posts_per_account_per_day: 2\n"
            "publish:\n"
            "  backend: buffer\n"
            "  require_approval: true\n"
            "  auto_approve: false\n"
            "  channels:\n"
            "    flagship: \"buf-chan-123\"\n",
            encoding="utf-8",
        )

    def _run(self, monkeypatch, tmp_path: Path, *, live: bool):
        import scripts.marketing_publisher as pub

        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1" if live else "0")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        argv = (["--live"] if live else []) + [
            "--root", str(tmp_path), "--now", _NOW.strftime("%Y-%m-%dT%H:%M:%SZ")]
        return pub.main(argv)

    def test_a_live_sweep_retires_the_stalled_mover(self, monkeypatch, tmp_path):
        from engine.marketing.outbox import fold_state

        self._publish_cfg(tmp_path)
        iid = _seed(tmp_path, key="amzn", kind="mover",
                    provenance="publisher_live_movers", hours_old=8.0)

        assert self._run(monkeypatch, tmp_path, live=True) == 0
        assert fold_state(tmp_path)["status"][iid] == "quarantined"

    def test_a_dry_run_never_destroys_the_queue_it_is_projecting(
            self, monkeypatch, tmp_path):
        """Quarantine is TERMINAL. A projection that reaped would delete the
        posts the operator ran it to preview."""
        from engine.marketing.outbox import fold_state

        self._publish_cfg(tmp_path)
        iid = _seed(tmp_path, key="amzn", kind="mover",
                    provenance="publisher_live_movers", hours_old=8.0)

        self._run(monkeypatch, tmp_path, live=False)
        assert fold_state(tmp_path)["status"][iid] == "queued"

    def test_the_count_reaches_the_activity_row_and_the_annotation(
            self, monkeypatch, tmp_path, capsys):
        from engine.marketing.ledgers import read_jsonl

        self._publish_cfg(tmp_path)
        _seed(tmp_path, key="amzn", kind="mover",
              provenance="publisher_live_movers", hours_old=8.0)
        _seed(tmp_path, key="press", kind="breaking",
              provenance="press_lane", hours_old=8.0)

        self._run(monkeypatch, tmp_path, live=True)

        rows = read_jsonl(tmp_path / "data" / "marketing" / "outbox" / "activity.jsonl")
        row = next(r for r in reversed(rows) if r.get("lane") == "publisher_live")
        assert row["expired_wire"] == 2, row

        out = capsys.readouterr().out
        line = next((l for l in out.splitlines()
                     if l.startswith("::warning title=marketing-wire-expired::")), "")
        assert line, out
        # House law: the annotation STARTS the line (a logger prefix makes
        # GitHub drop it silently) and names the count.
        assert "2 wire item(s)" in line, line

    def test_the_floor_has_plain_words_for_the_counter(self):
        """The Floor renders an unmapped counter under its raw slug, which is
        visible-but-tinted. This gate ships with words."""
        from admin.marketing_floor import _ACTIVITY_WORDS, _LOSS_COUNTERS

        words = _ACTIVITY_WORDS["expired_wire"]
        assert words and words[0].islower(), words
        for banned in ("expire", "provenance", "ttl", "reaper", "quarantin"):
            assert banned not in words.lower(), words
        # It is a LOSS: the desk wrote the post and nobody sent it.
        assert "expired_wire" in _LOSS_COUNTERS


# ─────────────────────────────────────────────────────────────────────────────
# 3. The birth-time ladder
# ─────────────────────────────────────────────────────────────────────────────

class TestBirthTimeLadder:
    def test_an_operator_touch_resets_the_clock(self, tmp_path):
        """Age comes from the LAST ledger row when created_at is missing, so an
        item somebody re-armed five minutes ago is treated as five minutes old —
        not as eight hours old and instantly re-killed."""
        from engine.marketing.outbox import _wire_item_born_at

        it = {"as_of": "2026-07-31"}
        last = {"at": "2026-07-31T23:25:00Z"}
        assert _wire_item_born_at(it, last) == datetime(
            2026, 7, 31, 23, 25, tzinfo=timezone.utc)

    def test_created_at_outranks_the_ledger(self, tmp_path):
        from engine.marketing.outbox import _wire_item_born_at

        it = {"created_at": "2026-07-31T15:32:53Z", "as_of": "2026-07-31"}
        got = _wire_item_born_at(it, {"at": "2026-07-31T23:25:00Z"})
        assert got == datetime(2026, 7, 31, 15, 32, 53, tzinfo=timezone.utc)

    def test_a_date_only_as_of_floors_to_midnight_utc(self, tmp_path):
        from engine.marketing.outbox import _wire_item_born_at

        assert _wire_item_born_at({"as_of": "2026-07-31"}, None) == datetime(
            2026, 7, 31, tzinfo=timezone.utc)

    def test_the_literal_immediate_is_never_read_as_a_time(self, tmp_path):
        from engine.marketing.outbox import _wire_item_born_at

        assert _wire_item_born_at({"created_at": "immediate"}, None) is None
