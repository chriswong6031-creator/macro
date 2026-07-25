"""tests/test_marketing_publisher_autoapprove.py — W1 wiring-layer tests.

Covers the auto-approve gate added to scripts/marketing_publisher.py plus the
writeless dry-run report entrypoint and the admin marketing.publisher() shape.

Mirrors tests/test_marketing_social_publisher.py conventions: tmp_path for all
I/O, injected now= for determinism, ZERO live network (a fully fake publisher),
and the engine/runner modules imported INSIDE each test function.

Auto-approve contract under test:
  * config OFF and flag OFF        → NO queued→approved mutation
  * flag ON (live)                 → queued items passing ALL gates → approved
  * config ON (live)               → same, via config not flag
  * DRY-RUN + auto-approve         → reports what it WOULD approve, mutates NOTHING
  * an item failing a gate (over-280, no channel, over cap) is NOT auto-approved
  * dry_run_report() makes NO ledger writes (ledger byte-identical before/after)
  * admin marketing.publisher() returns the frozen shape and NEVER echoes a token
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


_FIXED_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-19"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers (mirrors test_marketing_social_publisher.py)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_queued_item(tmp_path: Path, *, text: str = "$PLTR reclaimed the 50-day. Watching now.",
                      account: str = "flagship", as_of: str = _AS_OF,
                      scheduled_at: str = "immediate") -> str:
    """Enqueue one item, leaving it in the 'queued' state. Returns its id."""
    from engine.marketing.outbox import make_item, enqueue
    item = make_item(
        account=account, kind="signal", text=text, as_of=as_of,
        scheduled_at=scheduled_at, provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path, max_per_account_day=99)
    return item["id"]


def _write_publish_cfg(tmp_path: Path, *, channel: str = "buf-chan-123",
                       links_allowed: bool = True, auto_approve: bool = False,
                       cap: int = 2, auto_approve_kinds: str | None = None,
                       floor_min: int = 0) -> None:
    """Write a minimal config/marketing.yml with publish + sentinel blocks.

    auto_approve_kinds: when given (e.g. "[mover, theme_list]"), adds the scoped
    exception key so publish-time-lane items of those kinds auto-approve even
    while require_approval stays true and auto_approve stays false.
    """
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    scoped = f"  auto_approve_kinds: {auto_approve_kinds}\n" if auto_approve_kinds else ""
    (cfg_dir / "marketing.yml").write_text(
        "sentinel:\n"
        f"  max_posts_per_account_per_day: {cap}\n"
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        f"  auto_approve: {'true' if auto_approve else 'false'}\n"
        f"  min_minutes_between_any_posts: {floor_min}\n"
        + scoped +
        "  channels:\n"
        f"    flagship: \"{channel}\"\n"
        "  links_allowed:\n"
        f"    flagship: {'true' if links_allowed else 'false'}\n",
        encoding="utf-8",
    )


def _append_publish_key(tmp_path: Path, key: str, value) -> None:
    """Add one key to the publish: block of an already-written marketing.yml.

    Inserted directly after the `publish:` line so it lands inside that block
    regardless of what _write_publish_cfg emitted below it.
    """
    p = tmp_path / "config" / "marketing.yml"
    lines = p.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        out.append(line)
        if line.strip() == "publish:":
            out.append(f"  {key}: {value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def _seed_queued_kind(tmp_path: Path, *, kind: str, provenance: str,
                      text: str, account: str = "flagship", as_of: str = _AS_OF,
                      source: dict | None = None) -> str:
    """Enqueue one queued item of a given kind + provenance. Returns its id."""
    from engine.marketing.outbox import make_item, enqueue
    item = make_item(
        account=account, kind=kind, text=text, as_of=as_of,
        scheduled_at="immediate", provenance=provenance, now=_FIXED_NOW,
        source=source,
    )
    enqueue(item, root=tmp_path, max_per_account_day=99)
    return item["id"]


class _FakePublisher:
    """Stand-in backend that records calls and never touches the network."""

    backend = "buffer"

    def __init__(self, *, ok: bool = True, external_id: str = "buf-post-1") -> None:
        self._ok = ok
        self._external_id = external_id
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        at_iso = (kwargs.get("now") or _FIXED_NOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        if self._ok:
            return Receipt(True, self._external_id, None, None, self.backend, at_iso)
        return Receipt(False, None, None, "boom", self.backend, at_iso)

    def list_channels(self):
        return [{"id": "buf-chan-123", "service": "twitter", "name": "Flagship"}]


def _write_fresh_quotes(tmp_path: Path, now: str,
                        tickers: tuple[str, ...] = ("PLTR",)) -> None:
    """Write a live-quotes snapshot so the publisher's tape gate can verify
    the fixture tickers (a signal it cannot verify is HELD, by design)."""
    import json as _json
    from datetime import datetime, timezone as _tz
    dt = datetime.fromisoformat(now.replace("Z", "+00:00")).replace(tzinfo=_tz.utc)
    ts_ms = int(dt.timestamp() * 1000)
    p = tmp_path / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "live_quotes_snapshot.json").write_text(_json.dumps({
        "asof": now,
        "quotes": {t: {"price": 100.0, "prevClose": 99.5, "changePct": 0.5,
                       "ts": ts_ms} for t in tickers},
    }), encoding="utf-8")


def _run_publisher(monkeypatch, tmp_path: Path, argv: list[str], *,
                   fake_publisher: _FakePublisher | None = None,
                   kill_switch: bool = False, now: str = "2026-07-19T13:00:00Z") -> int:
    """Invoke the runner main() in-process with a controlled environment."""
    import scripts.marketing_publisher as pub
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1" if kill_switch else "0")
    monkeypatch.setenv("BUFFER_TOKEN", "test-token")
    _write_fresh_quotes(tmp_path, now)
    if fake_publisher is not None:
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake_publisher)
    full_argv = list(argv) + ["--root", str(tmp_path), "--now", now]
    return pub.main(full_argv)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auto-approve OFF (default) — no mutation
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_approve_off_by_default_no_mutation(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False)
    qid = _seed_queued_item(tmp_path)

    fake = _FakePublisher()
    # --live + kill-switch, but NO --auto-approve and config auto_approve=false.
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []                       # nothing was approved → nothing posts
    assert current_statuses(tmp_path)[qid] == "queued"   # untouched


def test_auto_approve_flag_off_config_off_stays_queued(monkeypatch, tmp_path):
    """Neither the flag nor config → queued items are never advanced."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False)
    qid = _seed_queued_item(tmp_path)

    # No --live either — pure dry-run, no flag.
    rc = _run_publisher(monkeypatch, tmp_path, [], kill_switch=False)
    assert rc == 0
    assert current_statuses(tmp_path)[qid] == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Auto-approve ON via flag / config (live) — gates pass → approved
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_approve_flag_on_live_approves_and_posts(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, read_ledger
    _write_publish_cfg(tmp_path, auto_approve=False)   # config off; flag drives it
    qid = _seed_queued_item(tmp_path)

    fake = _FakePublisher(ok=True, external_id="buf-777")
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--auto-approve"],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    # queued → approved (auto) → posting → posted, in one run.
    assert current_statuses(tmp_path)[qid] == "posted"
    tos = [r["to"] for r in read_ledger(tmp_path) if r.get("id") == qid]
    assert tos == ["approved", "posting", "posted"]
    # The auto-approval transition was stamped by the publisher-autoapprove actor.
    appr = next(r for r in read_ledger(tmp_path) if r.get("id") == qid and r["to"] == "approved")
    assert appr["actor"] == "publisher-autoapprove"
    assert len(fake.calls) == 1


def test_auto_approve_config_on_live_approves(monkeypatch, tmp_path):
    """config publish.auto_approve: true enables it without the CLI flag."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True)
    qid = _seed_queued_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert current_statuses(tmp_path)[qid] == "posted"
    assert len(fake.calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. DRY-RUN + auto-approve — reports, mutates NOTHING
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_approve_dry_run_does_not_mutate(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, read_ledger
    _write_publish_cfg(tmp_path, auto_approve=True)
    qid = _seed_queued_item(tmp_path)

    ledger_before = read_ledger(tmp_path)
    fake = _FakePublisher(ok=True)
    # --auto-approve but NO --live (and kill-switch off) → dry-run.
    rc = _run_publisher(monkeypatch, tmp_path, ["--auto-approve"],
                        fake_publisher=fake, kill_switch=False)

    assert rc == 0
    assert fake.calls == []                              # nothing posted
    assert current_statuses(tmp_path)[qid] == "queued"   # NOT approved
    # No status transitions written by the dry-run auto-approve pass.
    assert read_ledger(tmp_path) == ledger_before


def test_auto_approve_live_flag_without_killswitch_stays_dry(monkeypatch, tmp_path):
    """--live --auto-approve but kill-switch OFF must degrade to dry-run: no mutation."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True)
    qid = _seed_queued_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--auto-approve"],
                        fake_publisher=fake, kill_switch=False)
    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[qid] == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Gate-failing items are NOT auto-approved
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_approve_skips_over_280(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True)
    bad = _seed_queued_item(tmp_path, text="x" * 300)   # over the 280 cap

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []
    # Failing validation → NOT auto-approved; it stays queued (the publisher only
    # quarantines items that are already APPROVED, never queued ones).
    assert current_statuses(tmp_path)[bad] == "queued"


def test_auto_approve_skips_when_no_channel(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, channel="", auto_approve=True)   # no channel id
    qid = _seed_queued_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[qid] == "queued"


def test_auto_approve_respects_daily_cap(monkeypatch, tmp_path):
    """cap=2 → of three gate-clean queued items, only two are auto-approved."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=2)
    ids = [
        _seed_queued_item(tmp_path, text="First queued post here."),
        _seed_queued_item(tmp_path, text="Second queued post here."),
        _seed_queued_item(tmp_path, text="Third queued post here."),
    ]

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    statuses = current_statuses(tmp_path)
    posted = [i for i in ids if statuses[i] == "posted"]
    queued = [i for i in ids if statuses[i] == "queued"]
    # cap=2 bounds the whole pipeline: exactly two post, one stays queued.
    assert len(posted) == 2
    assert len(queued) == 1
    assert len(fake.calls) == 2


def test_auto_approve_unlimited_cap_posts_all(monkeypatch, tmp_path):
    """Regression: cap == -1 (the unlimited sentinel) means NO limit, not a
    literal cap of -1. Before the _at_cap() guard, ``posted_today(0) >= -1`` was
    True, so EVERY item was skipped as 'account at daily cap (-1/day)' and NOTHING
    posted once config lifted the caps to unlimited (max_posts_per_account_per_day
    -1, PR #3376). This exercises both cap gates — auto-approve and post-time —
    end to end: all three gate-clean items must approve AND post in one run."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1)
    ids = [
        _seed_queued_item(tmp_path, text="First queued post here."),
        _seed_queued_item(tmp_path, text="Second queued post here."),
        _seed_queued_item(tmp_path, text="Third queued post here."),
    ]

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    statuses = current_statuses(tmp_path)
    # Unlimited cap → all three auto-approve AND post in the same run.
    assert all(statuses[i] == "posted" for i in ids), statuses
    assert len(fake.calls) == 3


def test_auto_approve_skips_held_item(monkeypatch, tmp_path):
    """A queued item the operator put on hold is NOT auto-approved."""
    from engine.marketing.outbox import current_statuses, record_decision
    _write_publish_cfg(tmp_path, auto_approve=True)
    qid = _seed_queued_item(tmp_path)
    assert record_decision(qid, "hold", actor="admin", root=tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[qid] == "queued"   # held → left alone


# ─────────────────────────────────────────────────────────────────────────────
# 5. dry_run_report() — writeless structured report
# ─────────────────────────────────────────────────────────────────────────────

def test_dry_run_report_shape_and_no_writes(monkeypatch, tmp_path):
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger
    import scripts.marketing_publisher as pub
    _write_publish_cfg(tmp_path, auto_approve=False)

    # One APPROVED + DUE item → should land in would_post.
    it = make_item(account="flagship", kind="signal", text="Approved and due post.",
                   as_of=_AS_OF, provenance="content_studio", now=_FIXED_NOW)
    enqueue(it, root=tmp_path, max_per_account_day=99)
    transition(it["id"], "approved", actor="t", root=tmp_path)

    ledger_before = read_ledger(tmp_path)
    rep = pub.dry_run_report(root=tmp_path, now=_FIXED_NOW)

    assert rep["ok"] is True
    assert rep["mode"] == "dry_run"
    assert rep["backend"] == "buffer"
    for key in ("counts", "would_post", "quarantine", "would_auto_approve", "stuck_posting"):
        assert key in rep
    assert rep["counts"]["would_post"] == 1
    assert rep["would_post"][0]["id"] == it["id"]
    assert rep["would_post"][0]["account"] == "flagship"
    # No ledger writes whatsoever.
    assert read_ledger(tmp_path) == ledger_before


def test_dry_run_report_previews_auto_approve(monkeypatch, tmp_path):
    import scripts.marketing_publisher as pub
    _write_publish_cfg(tmp_path, auto_approve=True)
    qid = _seed_queued_item(tmp_path)

    rep = pub.dry_run_report(root=tmp_path, now=_FIXED_NOW)
    assert rep["auto_approve"] is True
    assert rep["counts"]["would_auto_approve"] == 1
    assert rep["would_auto_approve"][0]["id"] == qid


# ─────────────────────────────────────────────────────────────────────────────
# 6. Admin marketing.publisher() — shape + token safety
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_publisher_empty_state(monkeypatch, tmp_path):
    from admin import marketing
    _write_publish_cfg(tmp_path)
    monkeypatch.delenv("BUFFER_TOKEN", raising=False)

    d = marketing.publisher(root=tmp_path)
    assert d["ok"] is True
    assert "note" in d                       # cold outbox → honest note
    assert d["config"]["backend"] == "buffer"
    assert d["config"]["token_present"] is False
    assert d["recent_posted"] == []
    assert d["stuck_posting"] == []
    # Status keys present and zeroed.
    for k in ("queued", "approved", "posting", "posted", "failed", "quarantined"):
        assert d["status_counts"][k] == 0


def test_admin_publisher_surfaces_posted_receipt_and_stuck(monkeypatch, tmp_path):
    from admin import marketing
    from engine.marketing.outbox import make_item, enqueue, transition
    _write_publish_cfg(tmp_path)

    # A posted item with a receipt.
    posted = make_item(account="flagship", kind="signal", text="Posted item.",
                       as_of=_AS_OF, provenance="content_studio", now=_FIXED_NOW)
    enqueue(posted, root=tmp_path, max_per_account_day=99)
    transition(posted["id"], "approved", actor="t", root=tmp_path)
    transition(posted["id"], "posting", actor="t", root=tmp_path)
    transition(posted["id"], "posted", actor="t", root=tmp_path,
               receipt={"backend": "buffer", "external_id": "buf-42", "external_url": None})

    # A stuck-in-posting item (crashed mid-post).
    stuck = make_item(account="flagship", kind="signal", text="Stuck item.",
                      as_of=_AS_OF, provenance="content_studio", now=_FIXED_NOW)
    enqueue(stuck, root=tmp_path, max_per_account_day=99)
    transition(stuck["id"], "approved", actor="t", root=tmp_path)
    transition(stuck["id"], "posting", actor="t", root=tmp_path)

    d = marketing.publisher(root=tmp_path)
    assert d["ok"] is True
    assert d["status_counts"]["posted"] == 1
    assert d["status_counts"]["posting"] == 1
    # Receipt surfaced on the recent-posted row.
    rp = next(r for r in d["recent_posted"] if r["id"] == posted["id"])
    assert rp["external_id"] == "buf-42"
    assert rp["backend"] == "buffer"
    # Stuck item surfaced prominently.
    assert any(r["id"] == stuck["id"] for r in d["stuck_posting"])


def test_admin_publisher_never_echoes_token(monkeypatch, tmp_path):
    """token_present is a bool; the raw token value must appear NOWHERE in the payload."""
    import json
    from admin import marketing
    _write_publish_cfg(tmp_path)
    monkeypatch.setenv("BUFFER_TOKEN", "super-secret-token-value")

    d = marketing.publisher(root=tmp_path)
    assert d["config"]["token_present"] is True
    assert "super-secret-token-value" not in json.dumps(d)


def test_admin_publisher_dryrun_wrapper_no_writes(monkeypatch, tmp_path):
    from admin import marketing
    from engine.marketing.outbox import read_ledger
    _write_publish_cfg(tmp_path, auto_approve=True)
    _seed_queued_item(tmp_path)

    ledger_before = read_ledger(tmp_path)
    d = marketing.publisher_dryrun(root=tmp_path)
    assert d["ok"] is True
    assert d["mode"] == "dry_run"
    assert read_ledger(tmp_path) == ledger_before


# ─────────────────────────────────────────────────────────────────────────────
# 7. Scoped auto-approve (publish.auto_approve_kinds) — the require_approval
#    exception for publish-time-lane mover/theme_list items.
# ─────────────────────────────────────────────────────────────────────────────

def _mover_text(pct: float = 0.5) -> str:
    return f"$PLTR +{pct:.1f}% today. Strength worth respecting, not chasing."


def test_scoped_auto_approves_publisher_lane_mover(monkeypatch, tmp_path):
    """A queued mover with provenance publisher_live_movers auto-approves when
    auto_approve_kinds=[mover, theme_list] AND global auto_approve is false."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False,
                       auto_approve_kinds="[mover, theme_list]")
    qid = _seed_queued_kind(tmp_path, kind="mover",
                            provenance="publisher_live_movers",
                            text=_mover_text(),
                            source={"ticker": "PLTR", "baseline_pct": 0.5})

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    # queued → approved (scoped) → posting → posted (tape gate posts the +0.5%).
    assert current_statuses(tmp_path)[qid] == "posted"
    assert len(fake.calls) == 1


def test_scoped_does_not_approve_content_studio_mover(monkeypatch, tmp_path):
    """The SAME kind (mover) from provenance content_studio is NOT auto-approved
    by the scoped exception — the lane guard is provenance publisher_live_movers."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False,
                       auto_approve_kinds="[mover, theme_list]")
    qid = _seed_queued_kind(tmp_path, kind="mover", provenance="content_studio",
                            text=_mover_text(),
                            source={"ticker": "PLTR", "baseline_pct": 0.5})

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[qid] == "queued"     # untouched


def test_scoped_does_not_approve_signal_of_wrong_kind(monkeypatch, tmp_path):
    """A publisher-lane item of a kind NOT in auto_approve_kinds (signal) stays
    queued under the scoped exception."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False,
                       auto_approve_kinds="[mover, theme_list]")
    qid = _seed_queued_kind(tmp_path, kind="signal",
                            provenance="publisher_live_movers",
                            text="$PLTR reclaimed the 50-day. Watching now.")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[qid] == "queued"


def test_global_auto_approve_true_still_approves_everything(monkeypatch, tmp_path):
    """Global auto_approve: true is unchanged by the scoping — any kind /
    provenance auto-approves (the scoped list is a superset here, not a filter)."""
    from engine.marketing.outbox import current_statuses
    # Global ON; the scoped list is present but must be ignored (global wins).
    _write_publish_cfg(tmp_path, auto_approve=True,
                       auto_approve_kinds="[mover]")
    qid = _seed_queued_item(tmp_path)   # a plain content_studio signal

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    # A content_studio SIGNAL (not in the scoped list) still posts because the
    # global flag is on → unrestricted, exactly as before this feature.
    assert current_statuses(tmp_path)[qid] == "posted"
    assert len(fake.calls) == 1


def test_scoped_junk_config_values_ignored(monkeypatch, tmp_path):
    """Junk auto_approve_kinds entries are ignored; a real mover still approves."""
    from engine.marketing.outbox import current_statuses
    # "signal" is a valid kind but not what we seed; "garbage" and 5 are junk.
    _write_publish_cfg(tmp_path, auto_approve=False,
                       auto_approve_kinds="[mover, garbage, 5]")
    qid = _seed_queued_kind(tmp_path, kind="mover",
                            provenance="publisher_live_movers",
                            text=_mover_text(),
                            source={"ticker": "PLTR", "baseline_pct": 0.5})

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    # Junk was dropped, "mover" survived → the item auto-approves and posts.
    assert current_statuses(tmp_path)[qid] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Global min-spacing floor (publish.min_minutes_between_any_posts) — the
#    Phase-2 post-time anti-spam guard: at most one post per window, any account.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_posted_at(tmp_path: Path, when: datetime, *, text: str) -> str:
    """Seed one item already advanced to 'posted' with a controlled ledger `at`
    (the floor reads the last posted row, so it holds across cron runs)."""
    from engine.marketing.outbox import make_item, enqueue, transition
    it = make_item(account="flagship", kind="signal", text=text, as_of=_AS_OF,
                   provenance="content_studio", now=_FIXED_NOW)
    enqueue(it, root=tmp_path, max_per_account_day=99)
    for to in ("approved", "posting"):
        transition(it["id"], to, actor="t", root=tmp_path, now=when)
    transition(it["id"], "posted", actor="t", root=tmp_path, now=when,
               receipt={"backend": "buffer", "external_id": "prev", "external_url": None})
    return it["id"]


def test_floor_posts_one_per_run(monkeypatch, tmp_path):
    """Two approved+due LADDER items + a 10m floor → exactly ONE posts this run;
    the other stays approved and retries next slot (an accumulated backlog can't
    burst out at once).

    The items carry an explicit past ladder slot: a slotless ("immediate") item
    takes the Phase-3 breaking path instead and is Buffer-scheduled at
    last_post + floor rather than deferred (test_immediate_* below)."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    ids = [
        _seed_queued_item(tmp_path, text="First floor post here.",
                          scheduled_at="2026-07-19T12:00:00Z"),
        _seed_queued_item(tmp_path, text="Second floor post here.",
                          scheduled_at="2026-07-19T12:00:00Z"),
    ]
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert len([i for i in ids if statuses[i] == "posted"]) == 1, statuses
    assert len([i for i in ids if statuses[i] == "approved"]) == 1, statuses
    assert len(fake.calls) == 1


def test_floor_disabled_posts_all(monkeypatch, tmp_path):
    """floor_min=0 (the default) disables the floor — both items post in one run."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
    ids = [
        _seed_queued_item(tmp_path, text="Post one text here."),
        _seed_queued_item(tmp_path, text="Post two text here."),
    ]
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert all(statuses[i] == "posted" for i in ids), statuses
    assert len(fake.calls) == 2


def test_floor_blocks_when_last_post_recent(monkeypatch, tmp_path):
    """A prior post 5m ago (read from the ledger — i.e. an earlier cron run)
    blocks a fresh due LADDER item under a 10m floor: it auto-approves but does
    NOT post."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    # Run's now is 2026-07-19T13:00Z; seed a post 5 minutes earlier.
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 55, tzinfo=timezone.utc),
                    text="Earlier post.")
    fresh = _seed_queued_item(tmp_path, text="Fresh post now.",
                              scheduled_at="2026-07-19T12:30:00Z")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[fresh] == "approved"   # floored → deferred
    assert fake.calls == []


def test_floor_allows_after_window(monkeypatch, tmp_path):
    """A prior post 15m ago (> the 10m floor) does not block — the fresh item posts."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 45, tzinfo=timezone.utc),
                    text="Older post.")
    fresh = _seed_queued_item(tmp_path, text="Fresh post now.")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[fresh] == "posted"
    assert len(fake.calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Phase 3 — breaking dispatch: immediate items budge in under the floor
#    (cadence masterplan gate 6) instead of waiting out a 2-hourly sweep.
# ─────────────────────────────────────────────────────────────────────────────

def test_immediate_due_at_unit():
    """_immediate_due_at: clear floor → now; inside the floor → last + floor;
    past the horizon → None (caller defers as before)."""
    from scripts.marketing_publisher import _immediate_due_at
    now = datetime(2026, 7, 19, 13, 0, tzinfo=timezone.utc)

    # nothing posted yet, or the floor is disabled → post now
    assert _immediate_due_at(now, None, 10, 60) == now
    assert _immediate_due_at(now, now, 0, 60) == now
    # last post 15m ago, 10m floor → clear → now
    assert _immediate_due_at(now, now - timedelta(minutes=15), 10, 60) == now
    # last post 4m ago → book the 10m mark (6m out), not now, not never
    assert (_immediate_due_at(now, now - timedelta(minutes=4), 10, 60)
            == now + timedelta(minutes=6))
    # a 120m floor with a 60m horizon → too far out → defer to the next run
    assert _immediate_due_at(now, now - timedelta(minutes=1), 120, 60) is None
    # horizon 0 = no horizon → always schedule, however far
    assert (_immediate_due_at(now, now - timedelta(minutes=1), 120, 0)
            == now + timedelta(minutes=119))


def test_immediate_item_schedules_at_floor_instead_of_deferring(monkeypatch, tmp_path):
    """A BREAKING item inside the floor window posts — booked at last_post + 10m
    via Buffer — where a ladder item would have deferred to the next sweep."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 55, tzinfo=timezone.utc),
                    text="Earlier post.")
    breaking = _seed_queued_item(tmp_path, text="Breaking post now.",
                                 scheduled_at="immediate")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[breaking] == "posted"
    assert len(fake.calls) == 1
    # 12:55 + 10m floor = 13:05, five minutes after the run's 13:00 "now".
    assert fake.calls[0]["scheduled_at"] == "2026-07-19T13:05:00Z"
    assert fake.calls[0]["immediate"] is True


def test_immediate_item_past_horizon_still_defers(monkeypatch, tmp_path):
    """The floor-booking is bounded: when the wait exceeds
    publish.immediate_defer_max_minutes the item defers to the next run, so one
    sweep can never book hours of future posts."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    # 5m horizon vs a floor that clears in 9m → past the horizon.
    _append_publish_key(tmp_path, "immediate_defer_max_minutes", 5)
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 59, tzinfo=timezone.utc),
                    text="Earlier post.")
    breaking = _seed_queued_item(tmp_path, text="Breaking post now.",
                                 scheduled_at="immediate")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[breaking] == "approved"
    assert fake.calls == []


def test_two_immediate_items_ladder_by_the_floor(monkeypatch, tmp_path):
    """A burst of breaking items goes out spaced by the floor (+0, +10), not all
    at once and not one-per-two-hours."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    ids = [
        _seed_queued_item(tmp_path, text="Breaking one here.", scheduled_at="immediate"),
        _seed_queued_item(tmp_path, text="Breaking two here.", scheduled_at="immediate"),
    ]
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert all(statuses[i] == "posted" for i in ids), statuses
    sent = [c["scheduled_at"] for c in fake.calls]
    assert sent == ["2026-07-19T13:00:00Z", "2026-07-19T13:10:00Z"], sent


# ─────────────────────────────────────────────────────────────────────────────
# 9. Phase 3 — --post-now (the admin "Post now" button's runner side)
# ─────────────────────────────────────────────────────────────────────────────

def test_post_now_sends_a_future_slotted_item_without_auto_approve(monkeypatch, tmp_path):
    """--post-now posts a queued item whose ladder slot is HOURS away, with
    publish.auto_approve OFF: the operator's click is the approval."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=10)
    later = _seed_queued_item(tmp_path, text="Scheduled for tonight.",
                              scheduled_at="2026-07-19T23:00:00Z")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", later],
                        fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[later] == "posted"
    assert len(fake.calls) == 1
    assert fake.calls[0]["immediate"] is True
    assert fake.calls[0]["scheduled_at"] == "2026-07-19T13:00:00Z"   # now, not 23:00


def test_post_now_does_not_touch_other_items(monkeypatch, tmp_path):
    """--post-now scopes the whole run: another approved+due item does NOT go out
    on the back of a breaking dispatch."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
    target = _seed_queued_item(tmp_path, text="Send this one now.")
    other = _seed_queued_item(tmp_path, text="Leave this one alone.")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", target],
                        fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert statuses[target] == "posted"
    assert statuses[other] == "queued"      # untouched — not even auto-approved
    assert len(fake.calls) == 1


def test_post_now_still_runs_the_safety_gates(monkeypatch, tmp_path):
    """--post-now jumps the QUEUE, not the CHECKS: an over-length item is not
    approved, nothing posts, and the run exits non-zero so the operator sees red."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    bad = _seed_queued_item(tmp_path, text="$PLTR " + ("x" * 400))
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", bad],
                        fake_publisher=fake, kill_switch=True)
    assert rc == 3
    assert current_statuses(tmp_path)[bad] == "queued"
    assert fake.calls == []


def test_post_now_unknown_id_exits_nonzero(monkeypatch, tmp_path):
    """An id that is not in this checkout's outbox fails loudly rather than
    reporting a green no-op run."""
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
    _seed_queued_item(tmp_path, text="Unrelated queued post.")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", "ob-does-not-exist"],
                        fake_publisher=fake, kill_switch=True)
    assert rc == 3
    assert fake.calls == []


def test_post_now_dry_run_exits_zero(monkeypatch, tmp_path):
    """With the kill-switch OFF the dispatch is a dry-run — no post was ever
    going to happen, so it must not masquerade as a failed breaking send."""
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
    target = _seed_queued_item(tmp_path, text="Would be sent now.")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", target],
                        fake_publisher=fake, kill_switch=False)
    assert rc == 0
    assert fake.calls == []
