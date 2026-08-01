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

#: Distinct bodies for the multi-item cap / floor fixtures below. They used to be
#: "First queued post here." / "Second queued post here." / ... — one template
#: with an ordinal swapped, which the ported template-frame gate (2026-07-29)
#: scores at exactly 0.60 and quarantines, correctly: blank the numbers and those
#: three strings differ by one token in five. Varying an ordinal is NOT varying a
#: post, and that is the whole point of the gate. Each entry here is a different
#: sentence about a different thing, so these fixtures exercise the CAP and the
#: FLOOR they were written for instead of dying on a copy gate.
#:
#: DELIBERATELY TICKER-FREE. _seed_queued_item builds `kind="signal"` items, and
#: signal is a price kind: give one a cashtag and the LIVE TAPE GATE holds it for
#: want of a fresh quote, which is a second way to fail these tests for a reason
#: they are not about. Max pairwise frame similarity across these four is 0.12.
_DISTINCT_BODIES: tuple[str, ...] = (
    "Breadth improved into the close and the laggards finally joined.",
    "Credit spreads tightened while equity vol kept bleeding lower.",
    "Volume dried up all afternoon; nobody wanted to press either side.",
    "Rate expectations shifted again, and the long end took the brunt.",
)


def _seed_queued_item(tmp_path: Path, *, text: str = "$PLTR reclaimed the 50-day. Watching now.",
                      account: str = "flagship", as_of: str = _AS_OF,
                      scheduled_at: str = "immediate", priority: int = 5) -> str:
    """Enqueue one item, leaving it in the 'queued' state. Returns its id.

    ``priority`` steers the publisher's consideration order (lower posts first);
    the default matches make_item's default."""
    from engine.marketing.outbox import make_item, enqueue
    item = make_item(
        account=account, kind="signal", text=text, as_of=as_of,
        scheduled_at=scheduled_at, priority=priority,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path, max_per_account_day=99)
    return item["id"]


def _write_publish_cfg(tmp_path: Path, *, channel: str = "buf-chan-123",
                       links_allowed: bool = True, auto_approve: bool = False,
                       cap: int = 2, auto_approve_kinds: str | None = None,
                       floor_min: int = 0,
                       auto_approve_scope: str = "all") -> None:
    """Write a minimal config/marketing.yml with publish + sentinel blocks.

    auto_approve_kinds: when given (e.g. "[mover, theme_list]"), adds the scoped
    exception key so publish-time-lane items of those kinds auto-approve even
    while require_approval stays true and auto_approve stays false.

    auto_approve_scope: "all" HERE ON PURPOSE, and it is not the product default.
    The live default is "kinds" (Content Studio W1, masterplan §7: the global
    flag no longer clears nightly planned kinds — they wait for an operator
    decision). Every test in this file predates that split and exercises the
    auto-approve MACHINERY — gates, caps, floor, jitter, immediates — on a plain
    content_studio signal, so they pin the unrestricted blanket explicitly and
    keep testing what they were written to test. The scope's own semantics
    (planned kind NOT auto-approved, mover still auto-approved) are pinned in
    tests/test_marketing_selection.py.

    APPROVAL DESK OFF, EXPLICITLY. `approval_desk.enabled` ships TRUE and a
    MISSING block reads as enabled, so a minimal config like this one arms the
    autonomous desk — which now runs UPSTREAM of the auto-approve pass and
    audits every queued planned-kind item (payload, number sanity, liveness,
    chart law, banned language, dedup). Every fixture in this file is a
    throwaway string ("Fresh post now.", "Leave this one alone.", 300 x's) that
    the desk's payload floor correctly quarantines for carrying no number, no
    cashtag and no dated precedent.

    Same reasoning as the `auto_approve_scope: all` line below: this file
    exercises the auto-approve MACHINERY — gates, caps, floor, jitter,
    immediates, post-now, dark desks — and pinning its fixtures to the desk's
    editorial bar would make sixteen unrelated tests fail the day somebody
    tightens a check. The desk's own behaviour, and its interaction with these
    lanes (planned item approved and dispatched in one sweep; breaking and
    mover untouched), is pinned in tests/test_marketing_approval_desk.py.
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
        f"  auto_approve_scope: {auto_approve_scope}\n"
        f"  min_minutes_between_any_posts: {floor_min}\n"
        + scoped +
        "  channels:\n"
        f"    flagship: \"{channel}\"\n"
        "  links_allowed:\n"
        f"    flagship: {'true' if links_allowed else 'false'}\n"
        # See the docstring: OFF on purpose, this file is not the desk's file.
        "approval_desk:\n"
        "  enabled: false\n",
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
    """cap=2 → of three gate-clean queued LADDER items, only two are auto-approved.

    Ladder items carry an explicit past slot time: the cap governs LADDER volume;
    immediate/breaking items are cap-EXEMPT (operator 2026-07-27) and would defeat
    this test if left on the _seed_queued_item default scheduled_at="immediate"."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=2)
    ids = [
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[0],
                          scheduled_at="2026-07-19T12:00:00Z"),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[1],
                          scheduled_at="2026-07-19T12:00:00Z"),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[2],
                          scheduled_at="2026-07-19T12:00:00Z"),
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
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[0]),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[1]),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[2]),
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
    # NOT "Strength worth respecting, not chasing" — that is a RETIRED house
    # closer (operator 2026-07-30) and the publisher's voice gate quarantines
    # it on sight. These tests are about auto-approve ROUTING, so the fixture
    # copy has to be copy that would actually ship.
    return f"$PLTR +{pct:.1f}% today, and I keep underestimating this one."


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
    """Global auto_approve: true UNDER SCOPE "all" approves any kind/provenance.

    `auto_approve_scope: all` is the operator's one-line reversal of the W1
    kind scoping (masterplan §7) — this test is what pins that the reversal
    really restores the pre-W1 blanket. The DEFAULT scope ("kinds") refusing this
    same content_studio signal is pinned in tests/test_marketing_selection.py.
    """
    from engine.marketing.outbox import current_statuses
    # Global ON; the scoped list is present but must be ignored (global wins).
    _write_publish_cfg(tmp_path, auto_approve=True,
                       auto_approve_kinds="[mover]", auto_approve_scope="all")
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
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[0],
                          scheduled_at="2026-07-19T12:00:00Z"),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[1],
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
    """floor_min=0 (the default) disables the floor — both LADDER items post in
    one run. Explicit past slots so they take the ladder path, not the immediate
    (breaking) path (which would post regardless of the floor)."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
    ids = [
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[0],
                          scheduled_at="2026-07-19T12:00:00Z"),
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[1],
                          scheduled_at="2026-07-19T12:00:00Z"),
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
    # Explicit past slot → LADDER item (the immediate default would post
    # regardless of the floor and not exercise "allows after window").
    fresh = _seed_queued_item(tmp_path, text="Fresh post now.",
                              scheduled_at="2026-07-19T12:30:00Z")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[fresh] == "posted"
    assert len(fake.calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Phase 3 — breaking dispatch: immediate items are UNLIMITED (operator
#    2026-07-27). They are floor-exempt, cap-exempt, and never deferred — they
#    post at `now`. Safety gates (validate, dedup, tape, channel, kill) still run.
#    A posted immediate STILL advances the in-memory floor for the next ladder.
# ─────────────────────────────────────────────────────────────────────────────

def test_immediate_posts_now_even_inside_the_floor(monkeypatch, tmp_path):
    """A BREAKING item posts at `now` even when a post went out seconds ago —
    floor-EXEMPT. (Old behavior booked it at last_post + floor; that is retired.)"""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    # A post went out one minute ago — well inside the 10-min floor.
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 59, tzinfo=timezone.utc),
                    text="Earlier post.")
    breaking = _seed_queued_item(tmp_path, text="Breaking post now.",
                                 scheduled_at="immediate")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    assert current_statuses(tmp_path)[breaking] == "posted"
    assert len(fake.calls) == 1
    # Posts at the run's "now" (13:00Z), NOT deferred to last_post + floor.
    assert fake.calls[0]["scheduled_at"] == "2026-07-19T13:00:00Z"
    assert fake.calls[0]["immediate"] is True


def test_burst_of_immediates_all_post_now_no_stagger(monkeypatch, tmp_path):
    """A burst of THREE breaking items all post in one run, all at `now` — no
    stagger, none deferred (floor-exempt)."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    ids = [
        _seed_queued_item(tmp_path, text="Breaking one about oil here.", scheduled_at="immediate"),
        _seed_queued_item(tmp_path, text="Breaking two about gold here.", scheduled_at="immediate"),
        _seed_queued_item(tmp_path, text="Breaking three about yields.", scheduled_at="immediate"),
    ]
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert all(statuses[i] == "posted" for i in ids), statuses
    sent = [c["scheduled_at"] for c in fake.calls]
    assert sent == ["2026-07-19T13:00:00Z"] * 3, sent


def test_immediate_exempt_from_cap_while_ladder_is_capped(monkeypatch, tmp_path):
    """A positive daily cap blocks a LADDER item but NOT an immediate/breaking
    item — breaking has no volume limits."""
    from engine.marketing.outbox import current_statuses
    # cap=1, floor disabled so the floor never confounds the cap check.
    _write_publish_cfg(tmp_path, auto_approve=True, cap=1, floor_min=0)
    # One post already went out today → the account is AT the cap of 1.
    _seed_posted_at(tmp_path, datetime(2026, 7, 19, 12, 30, tzinfo=timezone.utc),
                    text="Already posted today filling the cap.")
    ladder = _seed_queued_item(tmp_path, text="Ladder item wants the slot too.",
                               scheduled_at="2026-07-19T12:00:00Z")
    breaking = _seed_queued_item(tmp_path, text="Breaking overrides the cap now.",
                                 scheduled_at="immediate")
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert statuses[breaking] == "posted", statuses    # cap-exempt → posts
    assert statuses[ladder] != "posted", statuses      # capped → never posts
    assert len(fake.calls) == 1
    assert fake.calls[0]["immediate"] is True


def test_posted_immediate_advances_floor_and_skips_due_ladder(monkeypatch, tmp_path):
    """A posted immediate item STILL advances the in-memory floor, so a due
    LADDER item in the SAME run is floor-skipped (the 10-min spacing survives for
    ladder posts)."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=10)
    # priority steers order: the immediate (priority 1) is considered first and
    # advances the floor; the ladder item (priority 5) then sits inside the floor.
    breaking = _seed_queued_item(tmp_path, text="Breaking goes first here.",
                                 scheduled_at="immediate", priority=1)
    ladder = _seed_queued_item(tmp_path, text="Ladder item due right now too.",
                               scheduled_at="2026-07-19T12:00:00Z", priority=5)
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert rc == 0
    statuses = current_statuses(tmp_path)
    # The immediate posts (advancing the floor to now); the ladder item, now
    # inside the floor window, defers.
    assert statuses[breaking] == "posted", statuses
    assert statuses[ladder] == "approved", statuses
    assert len(fake.calls) == 1
    assert fake.calls[0]["immediate"] is True


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


class TestPostNowSkipsPacingNotSafety:
    """`post_now` BUYS A SLOT, NOT A WAIVER (#3960 reviewer minor).

    The bypass is legitimate for PACING — the ladder slot, the daily cap, the
    cadence resolver, the min-spacing floor, the send-time jitter — because an
    operator click and a breaking dispatch are explicit intent about WHEN. It is
    not consent to relax a safety gate, and it never arms the publisher.

    The gates below all bind on a `post_now` item. The chart law is the one that
    did NOT: line 1449 used to read `iid not in post_now and
    _missing_required_media(...)`, so a ticker post whose chart URL never
    resolved shipped BARE on an operator click -- silently, since the panel does
    not show that the R2 upload failed. Everything here is a RUNTIME assertion;
    the source-shape half lives in tests/test_marketing_forward_booking.py.
    """

    @staticmethod
    def _seed_charted_signal(tmp_path: Path, *, media_url: str = "") -> str:
        """A $ticker `signal` that carries chart metadata with no public URL.

        This is the real production shape of the defect: the plan build stamped a
        chart onto the item, and the R2 upload that would have given it a public
        https URL never landed.
        """
        from engine.marketing.outbox import make_item, enqueue
        media = [{"kind": "chart_svg", "chart_id": "sig-pltr-1",
                  "path": "data/marketing/outbox/media/x/sig-pltr-1.svg",
                  "ticker": "PLTR"}]
        if media_url:
            media[0]["media_url"] = media_url
        item = make_item(
            account="flagship", kind="signal",
            text="$PLTR reclaimed the 50-day. Watching now.", as_of=_AS_OF,
            media=media, scheduled_at="immediate", priority=5,
            provenance="content_studio", now=_FIXED_NOW,
        )
        enqueue(item, root=tmp_path, max_per_account_day=99)
        return item["id"]

    def test_a_post_now_ticker_post_missing_its_chart_is_refused(
            self, monkeypatch, tmp_path):
        from engine.marketing.outbox import current_statuses
        _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
        _append_publish_key(tmp_path, "media_enabled", "true")
        bare = self._seed_charted_signal(tmp_path)
        fake = _FakePublisher(ok=True)

        rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", bare],
                            fake_publisher=fake, kill_switch=True)

        assert fake.calls == [], "a chartless ticker post reached the timeline"
        # Deferred, not destroyed: it retries when the media backfill lands.
        assert current_statuses(tmp_path)[bare] == "approved"
        # And the dispatch reports RED, so the operator is not told it went out.
        assert rc == 3

    def test_the_same_item_posts_once_its_chart_has_a_public_url(
            self, monkeypatch, tmp_path):
        """The control. The gate refuses a MISSING chart, not the whole kind."""
        from engine.marketing.outbox import current_statuses
        _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
        _append_publish_key(tmp_path, "media_enabled", "true")
        good = self._seed_charted_signal(
            tmp_path, media_url="https://pub-test.r2.dev/c/sig-pltr-1.png")
        fake = _FakePublisher(ok=True)

        rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", good],
                            fake_publisher=fake, kill_switch=True)

        assert rc == 0
        assert current_statuses(tmp_path)[good] == "posted"
        assert len(fake.calls) == 1

    def test_a_post_now_item_with_banned_language_is_quarantined(
            self, monkeypatch, tmp_path):
        """An em dash is what the press lane's whole B1 wave was about: the
        publisher's last-gate language screen quarantines it. A breaking dispatch
        must not be the way around the copy bar."""
        from engine.marketing.outbox import current_statuses
        _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
        bad = _seed_queued_item(
            tmp_path, text="$PLTR reclaimed the 50-day — watching now.")
        fake = _FakePublisher(ok=True)

        rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", bad],
                            fake_publisher=fake, kill_switch=True)

        assert fake.calls == []
        assert current_statuses(tmp_path)[bad] == "quarantined"
        assert rc == 3

    def test_a_post_now_item_on_a_halted_account_never_sends(
            self, monkeypatch, tmp_path):
        """The halt registry is a kill switch with an account's name on it."""
        import json as _json
        from engine.marketing.outbox import current_statuses
        _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
        from engine.marketing import health_monitor as hm
        target = _seed_queued_item(tmp_path, text="$PLTR held the 50-day.")
        path = hm.halts_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps({"accounts": {"flagship": {
            "state": "halted", "reason": "fixture halt",
            "at": "2026-07-19T12:00:00Z"}}}), encoding="utf-8")
        assert hm.is_halted("flagship", root=tmp_path) is True
        fake = _FakePublisher(ok=True)

        rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", target],
                            fake_publisher=fake, kill_switch=True)

        assert fake.calls == []
        assert current_statuses(tmp_path)[target] != "posted"
        assert rc == 3

    def test_post_now_cannot_arm_the_publisher(self, monkeypatch, tmp_path):
        """Restates test_post_now_dry_run_exits_zero as a SAFETY claim: the
        global kill switch is computed before post_now is ever consulted, so
        `--post-now` with the switch off sends nothing."""
        _write_publish_cfg(tmp_path, auto_approve=True, cap=-1, floor_min=0)
        target = _seed_queued_item(tmp_path, text="$PLTR reclaimed the 50-day.")
        fake = _FakePublisher(ok=True)

        rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", target],
                            fake_publisher=fake, kill_switch=False)

        assert rc == 0 and fake.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# Post-time repeat gate — identical copy never posts twice in the window
# ─────────────────────────────────────────────────────────────────────────────
# The enqueue-time text guard (#3824) stops identical copy ENTERING the queue,
# but the byte-identical 2026-07-26/27 "My read on today's move" pair was
# enqueued BEFORE that guard shipped: the second copy sat approved under a
# fresh id, due a night later. The publisher's repeat gate is the post-time
# half — text that already went out this window is quarantined at the last
# gate before the network, whatever path put it in the queue.

_REPEAT_TEXT = ("My read on today's move\n\nRates are doing the driving today. "
                "Traders are pricing out Fed cuts.")


def _seed_item_bypassing_enqueue_guard(tmp_path: Path, *, text: str, as_of: str,
                                       kind: str = "event",
                                       account: str = "flagship") -> str:
    """Append an item straight to items.jsonl, exactly like the pre-guard
    legacy rows the gate exists for (enqueue() would rightly refuse it)."""
    from engine.marketing import outbox
    item = outbox.make_item(account=account, kind=kind, text=text, as_of=as_of,
                            scheduled_at="immediate", provenance="content_studio",
                            now=_FIXED_NOW)
    assert outbox.append_jsonl(outbox._items_path(tmp_path), item)
    return item["id"]


def _post_first_copy(tmp_path: Path, *, text: str, as_of: str) -> str:
    """Seed + walk one item to folded status 'posted' (night one)."""
    from engine.marketing.outbox import transition
    first = _seed_item_bypassing_enqueue_guard(tmp_path, text=text, as_of=as_of)
    for to in ("approved", "posting", "posted"):
        assert transition(first, to, actor="test", root=tmp_path, now=_FIXED_NOW)
    return first


def test_recent_posted_text_keys_scopes_by_status_and_window():
    """Unit contract: only posted/posting items inside the dedup window feed
    the gate; queued/approved/old items never do."""
    from engine.marketing.outbox import recent_posted_text_keys, text_key

    def _item(iid, account, text, as_of):
        return iid, {"id": iid, "account": account, "text": text, "as_of": as_of}

    items = dict([
        _item("a", "flagship", "same words", "2026-07-26"),   # posted, in window
        _item("b", "flagship", "same words", "2026-07-27"),   # approved → ignored
        _item("c", "flagship", "old words", "2026-07-01"),    # posted, OUT of window
        _item("d", "second", "other words", "2026-07-27"),    # posting counts too
    ])
    state = {"items": items,
             "status": {"a": "posted", "b": "approved", "c": "posted",
                        "d": "posting"}}
    keys = recent_posted_text_keys(state, "2026-07-27")
    assert text_key("flagship", "same words") in keys
    assert text_key("second", "other words") in keys
    assert text_key("flagship", "old words") not in keys


def test_repeat_gate_quarantines_identical_text_live(monkeypatch, tmp_path):
    """LIVE: the second byte-identical copy is quarantined, never sent."""
    from engine.marketing.outbox import current_statuses, read_ledger, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")

    dup = _seed_item_bypassing_enqueue_guard(tmp_path, text=_REPEAT_TEXT,
                                             as_of="2026-07-19")
    assert transition(dup, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert fake.calls == []                       # the repeat never reached Buffer
    assert current_statuses(tmp_path)[dup] == "quarantined"
    note = next(r for r in read_ledger(tmp_path)
                if r.get("id") == dup and r["to"] == "quarantined")["note"]
    assert "repeat" in note


def test_repeat_gate_dry_run_counts_but_does_not_mutate(monkeypatch, tmp_path):
    """DRY-RUN: the repeat is reported, the ledger is untouched."""
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")

    dup = _seed_item_bypassing_enqueue_guard(tmp_path, text=_REPEAT_TEXT,
                                             as_of="2026-07-19")
    assert transition(dup, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    rc = _run_publisher(monkeypatch, tmp_path, [], kill_switch=False)
    assert rc == 0
    assert current_statuses(tmp_path)[dup] == "approved"   # untouched in dry-run


def test_repeat_gate_lets_fresh_text_post(monkeypatch, tmp_path):
    """Different words sail through — the gate matches identical copy only."""
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")

    fresh = _seed_item_bypassing_enqueue_guard(
        tmp_path, text="Credit is the story today. Spreads are widening.",
        as_of="2026-07-19")
    assert transition(fresh, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[fresh] == "posted"



# A lightly-reworded variant of _REPEAT_TEXT (token Jaccard ~0.89 >= 0.7).
_REPEAT_TEXT_REWORDED = ("My read on today's move\n\nRates are doing the driving "
                         "today. Traders are now pricing out Fed cuts here.")


def test_post_time_near_dup_quarantines_with_receipt(monkeypatch, tmp_path):
    """LIVE: a lightly-reworded repeat (Jaccard >= 0.7 vs a same-account posted
    text) is quarantined; the receipt names the offending item and the score."""
    from engine.marketing.outbox import (
        current_statuses, read_ledger, transition, token_jaccard, fold_state,
    )
    assert token_jaccard(_REPEAT_TEXT, _REPEAT_TEXT_REWORDED) >= 0.7

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    first = _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")

    reworded = _seed_item_bypassing_enqueue_guard(tmp_path,
                                                  text=_REPEAT_TEXT_REWORDED,
                                                  as_of="2026-07-19")
    assert transition(reworded, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert fake.calls == []                               # never reached Buffer
    assert current_statuses(tmp_path)[reworded] == "quarantined"
    note = next(r for r in read_ledger(tmp_path)
                if r.get("id") == reworded and r["to"] == "quarantined")["note"]
    assert "near-identical" in note
    assert "jaccard=" in note
    assert first in note                                  # names the prior post


def test_post_time_deeply_reworded_passes(monkeypatch, tmp_path):
    """A DEEPLY reworded post (Jaccard < 0.7) is NOT caught by the near-dup gate."""
    from engine.marketing.outbox import current_statuses, transition, token_jaccard
    deep = "Credit is the story today. Spreads are widening across high yield."
    assert token_jaccard(_REPEAT_TEXT, deep) < 0.7

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")
    fresh = _seed_item_bypassing_enqueue_guard(tmp_path, text=deep, as_of="2026-07-19")
    assert transition(fresh, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[fresh] == "posted"


def test_post_time_near_dup_defers_cross_account(monkeypatch, tmp_path):
    """XG-W2 INVERTED this contract, deliberately — and DEFERS rather than kills.

    The old law was "cross-account near-dup is the sentinel's plan-time job".
    Sentinel's cross-account pass only sees items inside ONE nightly content
    plan, so it never covered the queue across nights or the fast lanes (which
    never enter a plan). Two of OUR accounts posting near-identical text is the
    fleet-linkage signal, and the last gate before the network is where it must
    be caught. Threshold: sentinel.near_dup_jaccard, stricter than the
    same-account 0.7 on purpose.

    But the item stays APPROVED, not quarantined: quarantine is terminal, and
    which of the two desks loses this race is decided by hash-ordered iteration.
    A collision is a property of the PAIR — killing an arbitrary one of them
    forever is the wrong remedy. It retries on a later sweep, by which time the
    counterpart has aged out of the window or been reworded.
    """
    from engine.marketing.outbox import (
        current_statuses, transition, token_jaccard, make_item, append_jsonl,
        _items_path, cross_account_threshold,
    )
    assert token_jaccard(_REPEAT_TEXT, _REPEAT_TEXT_REWORDED) >= cross_account_threshold(None)

    # flagship posted the original; a DIFFERENT account "second" carries the
    # near-identical copy and must now be REFUSED (its channel is configured, so
    # nothing else could be stopping it).
    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    cfg_p = tmp_path / "config" / "marketing.yml"
    txt = cfg_p.read_text(encoding="utf-8").replace(
        '    flagship: "buf-chan-123"',
        '    flagship: "buf-chan-123"\n    second: "buf-chan-456"')
    cfg_p.write_text(txt, encoding="utf-8")

    _post_first_copy(tmp_path, text=_REPEAT_TEXT, as_of="2026-07-18")  # flagship
    other = make_item(account="second", kind="event", text=_REPEAT_TEXT_REWORDED,
                      as_of="2026-07-19", scheduled_at="immediate",
                      provenance="content_studio", now=_FIXED_NOW)
    append_jsonl(_items_path(tmp_path), other)
    assert transition(other["id"], "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    # It never reached the network …
    assert all(_REPEAT_TEXT_REWORDED not in c.get("text", "") for c in fake.calls)
    # … and it is DEFERRED, not destroyed: still approved, eligible next sweep.
    assert current_statuses(tmp_path)[other["id"]] == "approved"


# ─────────────────────────────────────────────────────────────────────────────
# Post-time language gate — the queue is not a bypass around the copy bar
# ─────────────────────────────────────────────────────────────────────────────
# The 2026-07-27 $AVGO "POC held" post was enqueued by an older weekend_levels
# lane BEFORE the study-name bans existed, then fired days later: no
# generation-time validator can reach copy already in the queue. The publisher
# screens every due item with copywriter.banned_language — same bar, last gate.

_JARGON_TEXT = ("POC held, waiting\n\n$AVGO retested the POC at 379.32 and "
                "held, now 0.7% above it. Not yet.")


def test_language_gate_quarantines_jargon_live(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, read_ledger, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    bad = _seed_item_bypassing_enqueue_guard(tmp_path, text=_JARGON_TEXT,
                                             as_of="2026-07-19", kind="watchlist")
    assert transition(bad, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert fake.calls == []                       # jargon never reached Buffer
    assert current_statuses(tmp_path)[bad] == "quarantined"
    note = next(r for r in read_ledger(tmp_path)
                if r.get("id") == bad and r["to"] == "quarantined")["note"]
    assert "poc" in note.lower()


def test_language_gate_dry_run_reports_only(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    bad = _seed_item_bypassing_enqueue_guard(tmp_path, text=_JARGON_TEXT,
                                             as_of="2026-07-19", kind="watchlist")
    assert transition(bad, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    rc = _run_publisher(monkeypatch, tmp_path, [], kill_switch=False)
    assert rc == 0
    assert current_statuses(tmp_path)[bad] == "approved"   # untouched


def test_language_gate_passes_plain_copy(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    ok_item = _seed_item_bypassing_enqueue_guard(
        tmp_path,
        text=("$AVGO is holding the line\n\n$AVGO held 379.32, the price where "
              "the most shares changed hands lately. Watching, no position."),
        as_of="2026-07-19", kind="watchlist")
    assert transition(ok_item, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[ok_item] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# Post-time headline-shape gate — fragment headlines are vintage-proof too
# ─────────────────────────────────────────────────────────────────────────────
# validate_copy 4f (#3907) screens headline shape at generation time, but items
# enqueued before that law existed (or via a lane that bypasses validate_copy)
# fire later unscreened — the $AVGO lesson applied to headline SHAPE. The
# publisher recovers the headline only from an unambiguous two-block text of a
# headline-bearing kind; quarantine is terminal, so ambiguity means skip.

_FRAGMENT_TEXT = ("Radar check on\n\nThree names set up for the week. "
                  "Watching, no position.")


def test_headline_gate_quarantines_fragment_live(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, read_ledger, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    bad = _seed_item_bypassing_enqueue_guard(tmp_path, text=_FRAGMENT_TEXT,
                                             as_of="2026-07-19", kind="watchlist")
    assert transition(bad, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert fake.calls == []                       # the fragment never reached Buffer
    assert current_statuses(tmp_path)[bad] == "quarantined"
    note = next(r for r in read_ledger(tmp_path)
                if r.get("id") == bad and r["to"] == "quarantined")["note"]
    # Only the headline-shape gate writes this note — proof the gate fired, not
    # the language/repeat/tape gates sitting on either side of it.
    assert "fragment headline" in note


def test_headline_gate_dry_run_reports_only(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    bad = _seed_item_bypassing_enqueue_guard(tmp_path, text=_FRAGMENT_TEXT,
                                             as_of="2026-07-19", kind="watchlist")
    assert transition(bad, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    rc = _run_publisher(monkeypatch, tmp_path, [], kill_switch=False)
    assert rc == 0
    assert current_statuses(tmp_path)[bad] == "approved"   # untouched


def test_headline_gate_skips_one_block_kinds(monkeypatch, tmp_path):
    """A wire/breaking summary is ONE block. Its text may still contain a blank
    line, and the first block may look fragment-shaped ("Markets are on") — that
    is prose, not a headline. Screening it would kill a legitimate post
    permanently, so one-block kinds are never screened."""
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    wire = _seed_item_bypassing_enqueue_guard(
        tmp_path,
        text=("Markets are on\n\nedge after the Fed statement. "
              "Watching the close."),
        as_of="2026-07-19", kind="breaking")
    assert transition(wire, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[wire] == "posted"


def test_queued_headline_shape_matrix():
    """The recovery helper is the whole false-positive defense: it returns a
    headline ONLY for an unambiguous two-block text of a headline-bearing kind."""
    from scripts.marketing_publisher import _queued_headline

    assert _queued_headline("watchlist", "Radar check on\n\nbody here") == "Radar check on"
    assert _queued_headline("earnings", "🧾 $AVGO Q2 earnings: beat.\n\nGuide raised.") == "🧾 $AVGO Q2 earnings: beat."
    assert _queued_headline("breaking", "Radar check on\n\nbody here") is None
    assert _queued_headline("wire", "Radar check on\n\nbody here") is None
    assert _queued_headline(None, "Radar check on\n\nbody here") is None
    assert _queued_headline("watchlist", "one block only, no separator") is None
    assert _queued_headline("watchlist", "Line1\nLine2\n\nbody") is None
    assert _queued_headline("watchlist", "\n\nbody") is None
    assert _queued_headline("watchlist", "Head\n\n   ") is None


def test_headline_gate_passes_clean_two_block(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, transition

    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    ok_item = _seed_item_bypassing_enqueue_guard(
        tmp_path,
        text=("$AVGO is holding the line\n\n$AVGO held 379.32, the price where "
              "the most shares changed hands lately. Watching, no position."),
        as_of="2026-07-19", kind="watchlist")
    assert transition(ok_item, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[ok_item] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# Hot-tape orphan-brief gate — a brief never outlives the alert it explains
# ─────────────────────────────────────────────────────────────────────────────
# #3983 closed the RADAR half of the two-step recall cascade: dispatch_ids
# re-checks a queued brief's parent alert and quarantines the orphan. That
# sweep only runs when the radar runs. An operator recall after the last radar
# pass of the day (end of the ET window, a weekend, the workflow disabled)
# leaves an already-booked brief sitting on its scheduled_at, and the publisher
# sweep would send it — a brief explaining a post the operator pulled. The gate
# below is the publisher half; both call the SAME predicate
# (engine.marketing.hot_tape.orphaned_brief_status) so they cannot drift apart.

_HT_ALERT_KEY = "mover:PLTR:up:2026-07-19:0"


def _seed_hot_tape_brief(tmp_path: Path, *, parent: str | None = "recalled"):
    """Seed a hot-tape alert walked to `parent` status plus its queued context
    brief. parent=None seeds NO alert at all (the ledger-has-no-record case).
    Returns (alert_id or None, brief_id)."""
    from engine.marketing import outbox as ob
    from engine.marketing.hot_tape import BRIEF_TRIGGER, brief_key
    alert_id = None
    if parent is not None:
        alert_id = _seed_queued_kind(
            tmp_path, kind="breaking", provenance="hot_tape",
            text="$PLTR up 4.9 percent on heavy volume. Session high 31.20.",
            source={"lane": "hot_tape", "trigger": "mover",
                    "story_key": _HT_ALERT_KEY})
        for step in ("approved", "posted"):
            assert ob.transition(alert_id, step, actor="test", root=tmp_path,
                                 now=_FIXED_NOW)
        if parent != "posted":
            assert ob.transition(alert_id, parent, actor="test", root=tmp_path,
                                 now=_FIXED_NOW)
    brief_id = _seed_queued_kind(
        tmp_path, kind="breaking", provenance="hot_tape",
        text=("Context on that move: three peers are bid in sympathy and "
              "breadth is one-sided. Watching whether the group holds into "
              "the close."),
        source={"lane": "hot_tape", "trigger": BRIEF_TRIGGER,
                "story_key": brief_key(_HT_ALERT_KEY)})
    return alert_id, brief_id


def test_orphan_brief_quarantined_when_alert_recalled(monkeypatch, tmp_path, capsys):
    """THE regression: the operator recalls the alert AFTER the radar's last
    pass, so only the publisher is left to catch it. The brief must never
    reach the network."""
    from engine.marketing.outbox import fold_state

    _write_publish_cfg(tmp_path, auto_approve=True, cap=5)
    _alert_id, brief_id = _seed_hot_tape_brief(tmp_path, parent="recalled")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    st = fold_state(tmp_path)
    assert st["status"][brief_id] == "quarantined"
    last = st["last"][brief_id]
    assert last["actor"] == "publisher"
    # Only this gate writes that note — proof the orphan gate fired, and not
    # the language/repeat/tape gates sitting downstream of it.
    assert "alert is recalled" in (last.get("note") or "")
    assert fake.calls == []                       # nothing reached the network

    # The annotation must START the line or GitHub silently drops it.
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("::warning title=hot-tape-orphan-brief::")
               for line in lines)


def test_posted_alert_still_lets_its_brief_ship(monkeypatch, tmp_path):
    """Over-fire control. The parent is still posted, so the brief is the
    legitimate second half of a two-step publish and posts exactly as before —
    the gate must never mass-quarantine the lane it guards."""
    from engine.marketing.outbox import fold_state

    _write_publish_cfg(tmp_path, auto_approve=True, cap=5)
    _alert_id, brief_id = _seed_hot_tape_brief(tmp_path, parent="posted")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert fold_state(tmp_path)["status"][brief_id] == "posted"
    assert len(fake.calls) == 1


def test_orphan_brief_quarantined_when_alert_absent(monkeypatch, tmp_path):
    """No parent anywhere in the ledger. The publisher's map is built FROM the
    outbox ledger — the authority on statuses — so a parent it cannot name is
    positive evidence, not a fold hiccup: it quarantines where the radar (whose
    same-day fired map is lossy) merely withholds."""
    from engine.marketing.outbox import fold_state

    _write_publish_cfg(tmp_path, auto_approve=True, cap=5)
    alert_id, brief_id = _seed_hot_tape_brief(tmp_path, parent=None)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert alert_id is None
    st = fold_state(tmp_path)
    assert st["status"][brief_id] == "quarantined"
    assert "alert is unresolved" in (st["last"][brief_id].get("note") or "")
    assert fake.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch-time DARK-DESK park (desk_network liveness)
# ─────────────────────────────────────────────────────────────────────────────
# hot_tape.severity_account routes every sub-85 event to mastermind_news and
# never consults liveness — routing is pure by design (wire_routing: "LIVENESS
# IS NOT ROUTING"). That desk is deliberately dark in config/marketing.yml, but
# its Buffer channel id IS wired, and the breaking/immediate rail never passes
# through sentinel's plan gate. Liveness therefore binds HERE, at dispatch, in
# both the auto-approve pass and the post loop: quarantine with reason
# account_disabled, one ::warning per account, and arming stays one flip.

_WIRE_DESK = "mastermind_news"
_WIRE_TEXT = ("$NVDA just broke to a new high on heavy volume. "
              "Watching how it holds into the close.")


@pytest.fixture(autouse=True)
def _reset_dark_park_warnings():
    """The park annotation is once-per-account-per-PROCESS and pytest runs the
    whole file in one process — a stale warn set would make the "printed exactly
    once" assertion depend on execution order."""
    import scripts.marketing_publisher as pub
    pub.reset_dark_park_warnings()
    yield
    pub.reset_dark_park_warnings()


def _write_desk_network_cfg(tmp_path: Path, *, wire_enabled: bool,
                            auto_approve: bool = False, cap: int = -1,
                            floor_min: int = 0,
                            with_desk_network: bool = True) -> None:
    """marketing.yml with a desk_network block AND the wire desk's channel id.

    ``wire_enabled=False`` reproduces the live config/marketing.yml shape for
    mastermind_news exactly — BOTH keys (``enabled: false`` plus the legacy
    ``disabled: true``) with the Buffer channel already bound — which is the
    combination the dispatch-time park exists for. ``True`` is the armed state
    after the one desk_network flip.

    ``with_desk_network=False`` drops the roster entirely while KEEPING the bound
    channels — the shape a missing or mis-indented block produces, and the one
    the gate must never read as "asked, nothing is dark".
    """
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    on = "true" if wire_enabled else "false"
    off = "false" if wire_enabled else "true"
    roster = (
        "desk_network:\n"
        "  accounts:\n"
        "    - id: flagship\n"
        "      enabled: true\n"
        f"    - id: {_WIRE_DESK}\n"
        f"      enabled: {on}\n"
        f"      disabled: {off}\n"
    ) if with_desk_network else ""
    (cfg_dir / "marketing.yml").write_text(
        "sentinel:\n"
        f"  max_posts_per_account_per_day: {cap}\n"
        + roster +
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        f"  auto_approve: {'true' if auto_approve else 'false'}\n"
        "  auto_approve_scope: all\n"
        f"  min_minutes_between_any_posts: {floor_min}\n"
        "  channels:\n"
        "    flagship: \"buf-chan-123\"\n"
        f"    {_WIRE_DESK}: \"buf-chan-news\"\n"
        "  links_allowed:\n"
        "    flagship: true\n"
        f"    {_WIRE_DESK}: true\n"
        # OFF for the same reason _write_publish_cfg turns it off — see there.
        "approval_desk:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )


def _seed_wire_item(tmp_path: Path, *, text: str = _WIRE_TEXT,
                    account: str = _WIRE_DESK) -> str:
    """One queued kind=breaking, scheduled_at=immediate item — the exact shape
    scripts/hot_tape_radar.py enqueues before dispatching post_now."""
    return _seed_queued_kind(tmp_path, kind="breaking", provenance="hot_tape",
                             text=text, account=account)


def _quarantine_note(tmp_path: Path, iid: str) -> str:
    from engine.marketing.outbox import read_ledger
    return next(r for r in read_ledger(tmp_path)
                if r.get("id") == iid and r["to"] == "quarantined")["note"]


def _dark_park_lines(capsys) -> list[str]:
    """Annotation lines at LINE START — a logger-prefixed one does not count,
    because GitHub would never parse it (house law)."""
    return [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning title=publisher-dark-desk")]


def _auto_approve_direct(tmp_path: Path, *, live: bool, only_ids=None) -> list[str]:
    """Call the pass directly with the dark set THIS fixture resolves, so the
    kwarg contract is pinned independently of main()'s wiring."""
    import scripts.marketing_publisher as pub
    from engine.marketing import outbox
    from engine.marketing.social_publisher import validate_postable
    cfg = pub._load_marketing_cfg(tmp_path)
    return pub._auto_approve_pass(
        outbox, outbox.fold_state(tmp_path), pub._publish_cfg(cfg),
        cap=-1, now=_FIXED_NOW, live=live, account=None, posted_today={},
        validate_postable=validate_postable, root=tmp_path,
        only_ids=only_ids, dark_accounts=pub._dark_account_ids(cfg, tmp_path),
    )


def test_dark_desk_parks_the_post_now_dispatch(monkeypatch, tmp_path, capsys):
    """The gap this closes: a fresh sub-85 radar event, dispatched post_now onto
    a dark desk whose Buffer channel is wired. It must NEVER reach the network —
    the operator's click does not override account_disabled."""
    from engine.marketing.outbox import current_statuses, read_activity

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    iid = _seed_wire_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    # RULING 2026-07-29: a dispatch whose every requested item was dark-parked
    # exits 0, not 3. Until XG-W2 arms the desk this fires several times a day,
    # and a recurring expected red only teaches the operator to ignore reds. The
    # annotation and the account_disabled ledger row are the receipts.
    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "quarantined"
    assert _quarantine_note(tmp_path, iid).startswith("account_disabled")
    assert len(_dark_park_lines(capsys)) == 1
    # The park is COUNTED. It happens in the auto-approve pass (a queued item is
    # the breaking rail's normal shape), so a post-loop-only counter read 0 here.
    row = read_activity(tmp_path, n=1)[0]
    assert row["parked_dark"] == 1
    assert row["dark_accounts"] == [_WIRE_DESK]


def test_post_now_nonpark_failure_still_exits_red(monkeypatch, tmp_path):
    """The rc=0 ruling is scoped to a PURE park. An item that quarantines for any
    other reason is the kind of nothing-posted a human must look at, so the
    dispatch stays red — here a live desk whose copy fails the language gate."""
    from engine.marketing.outbox import current_statuses, transition

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    bad = _seed_item_bypassing_enqueue_guard(tmp_path, text=_JARGON_TEXT,
                                             as_of="2026-07-19", kind="watchlist",
                                             account="flagship")
    assert transition(bad, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", bad],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 3
    assert fake.calls == []
    assert current_statuses(tmp_path)[bad] == "quarantined"
    assert "banned language" in _quarantine_note(tmp_path, bad)


def test_dark_desk_park_pass_contract_live(tmp_path):
    """Pass level: dark_accounts binds even with only_ids set (post_now)."""
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    iid = _seed_wire_item(tmp_path)

    assert _auto_approve_direct(tmp_path, live=True, only_ids=frozenset({iid})) == []
    assert current_statuses(tmp_path)[iid] == "quarantined"
    assert _quarantine_note(tmp_path, iid).startswith("account_disabled")


def test_dark_desk_park_dry_run_writes_nothing(monkeypatch, tmp_path):
    """DRY-RUN parity: the pass reports and returns, it does not touch the
    ledger — the same invariant every other auto-approve gate keeps."""
    from engine.marketing.outbox import current_statuses, read_ledger

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    iid = _seed_wire_item(tmp_path)
    ledger_before = read_ledger(tmp_path)

    assert _auto_approve_direct(tmp_path, live=False, only_ids=frozenset({iid})) == []
    assert current_statuses(tmp_path)[iid] == "queued"
    assert read_ledger(tmp_path) == ledger_before

    # And through main(), kill-switch off: still queued, still no ledger row.
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=False)
    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "queued"
    assert read_ledger(tmp_path) == ledger_before


def test_one_desk_network_flip_arms_the_dispatch(monkeypatch, tmp_path):
    """Arming is ONE flip: the same fixture with the desk enabled posts. Nothing
    else about the item, the channel, or the dispatch changes."""
    from engine.marketing.outbox import current_statuses
    import scripts.marketing_publisher as pub

    _write_desk_network_cfg(tmp_path, wire_enabled=True)
    iid = _seed_wire_item(tmp_path)

    cfg = pub._load_marketing_cfg(tmp_path)
    assert pub._dark_account_ids(cfg, tmp_path) == frozenset()

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[iid] == "posted"


def test_dark_desk_park_leaves_live_desks_alone(monkeypatch, tmp_path):
    """Per-account, like the halt: the dark wire desk parks while flagship
    auto-approves and posts in the same run."""
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=False, auto_approve=True)
    dark = _seed_wire_item(tmp_path)
    live_item = _seed_queued_item(tmp_path, text="Flagship read, unaffected.")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert statuses[dark] == "quarantined"
    assert statuses[live_item] == "posted"
    assert len(fake.calls) == 1


def test_account_override_parks_a_config_enabled_desk(monkeypatch, tmp_path):
    """The admin lever binds at dispatch too: config says enabled, the operator
    override file says off, and effective_accounts (the one reader of that
    question) gives the override the last word."""
    import json
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=True)
    ov_dir = tmp_path / "data" / "marketing"
    ov_dir.mkdir(parents=True, exist_ok=True)
    (ov_dir / "account_overrides.json").write_text(
        json.dumps({_WIRE_DESK: {"enabled": False, "note": "paused"}}),
        encoding="utf-8")
    iid = _seed_wire_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0                                        # pure park — see the ruling
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "quarantined"
    assert _quarantine_note(tmp_path, iid).startswith("account_disabled")


def test_account_override_can_also_ARM_a_config_dark_desk(monkeypatch, tmp_path):
    """The lever swings both ways: config says dark, the override says enabled,
    and the item posts. This is the no-deploy arming path the park's annotation
    points the operator at, and it beats the legacy `disabled: true` too."""
    import json
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=False)   # enabled:false + disabled:true
    ov_dir = tmp_path / "data" / "marketing"
    ov_dir.mkdir(parents=True, exist_ok=True)
    (ov_dir / "account_overrides.json").write_text(
        json.dumps({_WIRE_DESK: {"enabled": True, "note": "armed for the drill"}}),
        encoding="utf-8")
    iid = _seed_wire_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[iid] == "posted"


def test_post_loop_parks_an_already_approved_dark_item(monkeypatch, tmp_path, capsys):
    """The other half: an item approved BEFORE the desk went dark (or approved
    by the operator) reaches the post loop, not the auto-approve pass. Same
    park, same reason, and the backend is never called."""
    from engine.marketing.outbox import current_statuses, transition

    _write_desk_network_cfg(tmp_path, wire_enabled=False)   # auto_approve off
    iid = _seed_wire_item(tmp_path)
    assert transition(iid, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "quarantined"
    assert _quarantine_note(tmp_path, iid).startswith("account_disabled")
    assert len(_dark_park_lines(capsys)) == 1


def test_dark_park_annotation_prints_once_per_account(monkeypatch, tmp_path, capsys):
    """Two parked items, ONE annotation: the publisher runs on a */5 cron and a
    per-item line would bury the summary it exists to surface. The line must
    start at column 0 — a logger prefix and GitHub drops it silently."""
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=False, auto_approve=True)
    first = _seed_wire_item(tmp_path)
    second = _seed_wire_item(tmp_path, text="$AMD is up sharply on the session. "
                                            "Watching the close.")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    statuses = current_statuses(tmp_path)
    assert statuses[first] == statuses[second] == "quarantined"
    lines = _dark_park_lines(capsys)
    assert len(lines) == 1, lines
    assert _WIRE_DESK in lines[0]


def test_unknown_liveness_stands_the_gate_down_inert(monkeypatch, tmp_path, capsys):
    """Fail-open, deliberately the opposite of wire_routing: with no safe
    fallback for "may this desk post", failing closed would park all seven live
    desks on a transient helper error. Unknown → items flow as before, and the
    run SAYS the gate is not enforcing."""
    from engine.marketing.outbox import current_statuses
    import engine.marketing.accounts as accounts
    import scripts.marketing_publisher as pub

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    iid = _seed_wire_item(tmp_path)

    def _boom(cfg, root=None):
        raise RuntimeError("accounts model exploded")

    monkeypatch.setattr(accounts, "effective_accounts", _boom)
    assert pub._dark_account_ids(pub._load_marketing_cfg(tmp_path), tmp_path) is None

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1                       # gate inert — item flowed
    assert current_statuses(tmp_path)[iid] == "posted"
    inert = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("::warning title=publisher-dark-desk")
             and "INERT" in ln]
    assert len(inert) == 1, inert


def test_dry_run_report_parks_dark_desk_items(monkeypatch, tmp_path, capsys):
    """The admin preview must MIRROR the park, not hide it and not promise a post.

    A dark-desk item under would_post tells the operator the opposite of what a
    live run does — on an UNARMED property, which is the exact confusion this
    gate exists to end. The preview also must not print the annotation: it is
    once-per-account-per-PROCESS, so a preview that spent it would leave the real
    dispatch behind it parking in silence.
    """
    import scripts.marketing_publisher as pub
    from engine.marketing.outbox import current_statuses, read_ledger, transition

    _write_desk_network_cfg(tmp_path, wire_enabled=False, auto_approve=True)
    queued = _seed_wire_item(tmp_path)
    approved = _seed_wire_item(tmp_path, text="$AMD is up sharply on the session. "
                                              "Watching the close.")
    assert transition(approved, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)
    ledger_before = read_ledger(tmp_path)
    capsys.readouterr()                                   # drop the seeding noise

    rep = pub.dry_run_report(root=tmp_path, now=_FIXED_NOW)

    assert rep["ok"] is True
    # Neither item is offered as postable or approvable …
    assert [w["id"] for w in rep["would_auto_approve"]] == []
    assert [w["id"] for w in rep["would_post"]] == []
    # … and both are NAMED as parked rather than silently dropped.
    parked = {w["id"]: w["account"] for w in rep["would_park_dark"]}
    assert parked == {queued: _WIRE_DESK, approved: _WIRE_DESK}
    assert rep["counts"]["would_park_dark"] == 2
    assert rep["dark_accounts"] == [_WIRE_DESK]

    # Writeless, as every other preview path is.
    assert read_ledger(tmp_path) == ledger_before
    assert current_statuses(tmp_path)[queued] == "queued"
    assert current_statuses(tmp_path)[approved] == "approved"

    # The preview is not a dispatch: no annotation, and the once-per-process
    # budget is untouched — the live run behind it still gets its warning.
    assert _dark_park_lines(capsys) == []
    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)
    assert rc == 0
    assert fake.calls == []
    assert len(_dark_park_lines(capsys)) == 1


def test_no_desk_network_roster_is_unknown_not_all_clear(monkeypatch, tmp_path, capsys):
    """An EMPTY roster is not an answer. effective_accounts returns [] for every
    way desk_network can go missing — fail-soft cfg load, mis-indent, rename — so
    reading [] as "nothing is dark" silently disarms the gate on exactly the
    configs least likely to be correct. Items still flow (fail-open is the
    adjudicated direction), but the run must SAY the gate is not enforcing."""
    from engine.marketing.outbox import current_statuses
    import scripts.marketing_publisher as pub

    _write_desk_network_cfg(tmp_path, wire_enabled=False, with_desk_network=False)
    iid = _seed_wire_item(tmp_path)

    cfg = pub._load_marketing_cfg(tmp_path)
    assert cfg.get("desk_network") is None                 # channels bound, no roster
    assert pub._dark_account_ids(cfg, tmp_path) is None    # UNKNOWN, not frozenset()

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1                            # fail-open, unchanged
    assert current_statuses(tmp_path)[iid] == "posted"
    inert = [ln for ln in _dark_park_lines(capsys) if "INERT" in ln]
    assert len(inert) == 1, inert


def test_dark_set_ignores_id_less_desk_entries(tmp_path):
    """An id-less desk_network entry resolves to "" — kept in the set it would
    park every item whose account field is blank or missing."""
    import scripts.marketing_publisher as pub

    cfg = {"desk_network": {"accounts": [
        {"id": "flagship", "enabled": True},
        {"enabled": False},                 # no id at all
        {"id": "   ", "enabled": False},    # whitespace id
        {"id": _WIRE_DESK, "enabled": False},
    ]}}
    assert pub._dark_account_ids(cfg, tmp_path) == frozenset({_WIRE_DESK})


def test_post_loop_dark_park_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    """The post loop's dry-run parity, the sibling of the pass-level case: an
    approved dark-desk item is REPORTED, not parked — no ledger row, and no
    annotation claiming a park that did not happen (which would also spend the
    once-per-process budget the next live run needs)."""
    from engine.marketing.outbox import current_statuses, read_ledger, transition

    _write_desk_network_cfg(tmp_path, wire_enabled=False)   # auto_approve off
    iid = _seed_wire_item(tmp_path)
    assert transition(iid, "approved", actor="test", root=tmp_path, now=_FIXED_NOW)
    ledger_before = read_ledger(tmp_path)
    capsys.readouterr()

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=False)                  # kill-switch off → dry

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "approved"    # untouched
    assert read_ledger(tmp_path) == ledger_before
    assert _dark_park_lines(capsys) == []


def test_post_now_park_plus_unknown_id_still_exits_red(monkeypatch, tmp_path):
    """Tie-break on the rc ruling: a dispatch that parks one real item AND names
    an id that is not in this checkout keeps its red. The park is expected; a
    phantom id is a fault of its own (the radar dispatched something never
    committed), and the enumeration keeps "missing item" red."""
    from engine.marketing.outbox import current_statuses

    _write_desk_network_cfg(tmp_path, wire_enabled=False)
    iid = _seed_wire_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path,
                        ["--live", "--post-now", f"{iid},ob-does-not-exist"],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 3
    assert fake.calls == []
    assert current_statuses(tmp_path)[iid] == "quarantined"   # the real one parked


# ─────────────────────────────────────────────────────────────────────────────
# The silent night.
#
# Every other annotation in the publisher names a PER-ITEM reason. The aggregate
# outcome -- "the whole night produced nothing" -- was silent, so on 2026-07-29
# zero posts went out and the operator found out by looking at the account
# instead of at the run. A machine that cannot tell you it failed is not
# autonomous, it is unattended.
#
# These drive the publisher LOOP, not the predicates. That distinction is not
# academic: the bare-cashtag gate shipped green while writing into a `counters`
# dict that was never defined, because its tests only exercised the pure
# function and never walked main().
# ─────────────────────────────────────────────────────────────────────────────
class TestSilentNightAlarm:
    def test_zero_posted_with_candidates_raises_a_loud_error(
            self, monkeypatch, tmp_path, capsys):
        """A post exists, none go out, and the run says so at ::error level."""
        _write_publish_cfg(tmp_path, auto_approve=False)
        # Queued and never approved: considered, blocked, zero posted.
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[0])

        fake = _FakePublisher(ok=True)
        rc = _run_publisher(monkeypatch, tmp_path, ["--live"],
                            fake_publisher=fake, kill_switch=True)
        assert rc == 0
        assert fake.calls == [], "fixture assumption: nothing should have posted"

        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines()
                if ln.startswith("::error title=marketing-zero-posted::")]
        # Line-START, bare print: a logger prefix makes GitHub drop it silently.
        assert hits, f"no silent-night alarm in output:\n{out[-1500:]}"
        assert "NOTHING POSTED" in hits[0]

    def test_a_night_that_posts_stays_quiet(self, monkeypatch, tmp_path, capsys):
        """The alarm must not cry wolf, or it gets ignored like every other one."""
        from engine.marketing.outbox import current_statuses

        _write_publish_cfg(tmp_path, auto_approve=True)
        qid = _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[1])

        fake = _FakePublisher(ok=True)
        assert _run_publisher(monkeypatch, tmp_path, ["--live"],
                              fake_publisher=fake, kill_switch=True) == 0
        assert current_statuses(tmp_path)[qid] == "posted", "fixture must post"

        out = capsys.readouterr().out
        assert "marketing-zero-posted" not in out, "alarm fired on a good night"

    def test_an_empty_queue_is_not_an_alarm(self, monkeypatch, tmp_path, capsys):
        """Nothing was DUE. That is a supply problem the plan lane owns, and
        firing here would train the operator to ignore the annotation."""
        _write_publish_cfg(tmp_path, auto_approve=True)

        fake = _FakePublisher(ok=True)
        assert _run_publisher(monkeypatch, tmp_path, ["--live"],
                              fake_publisher=fake, kill_switch=True) == 0
        out = capsys.readouterr().out
        assert "marketing-zero-posted" not in out, "alarm fired on an empty queue"

    def test_a_dry_run_never_alarms(self, monkeypatch, tmp_path, capsys):
        """--live only. A dry run posting nothing is the point of a dry run."""
        _write_publish_cfg(tmp_path, auto_approve=True)
        _seed_queued_item(tmp_path, text=_DISTINCT_BODIES[2])

        assert _run_publisher(monkeypatch, tmp_path, [], kill_switch=False) == 0
        out = capsys.readouterr().out
        assert "marketing-zero-posted" not in out


# ─────────────────────────────────────────────────────────────────────────────
# The post-time voice screen judges a post by ITS OWN SHAPE
# (adversarial review, 2026-07-31)
#
# THE DEFECT, end to end: the LLM prompt ORDERS a `stack` to carry three numbers
# (copywriter.SHAPE_CONTRACT), validate_copy_v2 admits it under the per-shape
# budget, outbox.emit_from_content_plan persists the shape at `source.shape` —
# and then the publisher's post-time screen called queued_voice_violations with
# no shape at all, re-judging the post at the shapeless default of two and
# TERMINALLY quarantining it at dispatch. A post written to spec, paid for,
# queued, and killed for obedience. Two halves, one in each file; this is the
# call-site half.
# ─────────────────────────────────────────────────────────────────────────────

#: 3 distinct numbers, no cashtag (a cashtag on a price kind pulls in the live
#: tape gate, which is a different test's subject). Over the shapeless budget of
#: 2, inside the `stack` budget of 3.
_THREE_NUMBER_STACK = (
    "Three numbers off this morning's claims print, and then I will shut up "
    "about it.\n\n"
    "Initial claims 218.0 thousand, the four-week average 223.5 thousand, "
    "continuing claims 1.94 million. I had been braced for a worse number "
    "and I hedged into it, which cost me a decent week."
)


def _voice_quarantine_notes(tmp_path: Path, iid: str) -> list[str]:
    """The voice screen's quarantine notes for one item, and only those.

    Asserting on the NOTE rather than on the final status is deliberate: a
    dispatch can end `posted` or `failed` for reasons that have nothing to do
    with this gate, and either a bare "not quarantined" or a bare "posted"
    assertion would go green the day an unrelated gate changed.
    """
    from engine.marketing.ledgers import read_jsonl
    rows = read_jsonl(tmp_path / "data" / "marketing" / "outbox" / "status_ledger.jsonl")
    return [str(r.get("note") or "") for r in rows
            if r.get("id") == iid
            and str(r.get("note") or "").startswith("voice laws (queue vintage):")]


def test_a_three_number_stack_survives_the_dispatch_voice_screen(monkeypatch, tmp_path):
    """The item's recorded shape reaches the gate, so the gate uses the stack
    budget the writer was held to."""
    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    iid = _seed_queued_kind(tmp_path, kind="macro", provenance="content_studio",
                            text=_THREE_NUMBER_STACK,
                            source={"shape": "stack", "angle": "data"})

    fake = _FakePublisher(ok=True)
    _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                   fake_publisher=fake, kill_switch=True)

    assert _voice_quarantine_notes(tmp_path, iid) == [], (
        "a post written to its own shape contract was killed at dispatch")


def test_a_shapeless_item_still_gets_the_narrow_budget(monkeypatch, tmp_path):
    """THE ANTI-VACUITY CONTROL, and the compatibility pin in one.

    Identical copy, no recorded shape — a pre-W1 outbox row. It must still trip
    the gate at the shapeless budget of two, which proves (a) the gate is armed
    at all, so the test above is not passing on a disabled screen, and (b)
    threading the shape did not quietly widen the budget for every queued item.
    """
    _write_publish_cfg(tmp_path, auto_approve=False, cap=-1, floor_min=0)
    iid = _seed_queued_kind(tmp_path, kind="macro", provenance="content_studio",
                            text=_THREE_NUMBER_STACK, source={"angle": "data"})

    fake = _FakePublisher(ok=True)
    _run_publisher(monkeypatch, tmp_path, ["--live", "--post-now", iid],
                   fake_publisher=fake, kill_switch=True)

    notes = _voice_quarantine_notes(tmp_path, iid)
    assert len(notes) == 1, notes
    assert "number soup (3 numbers" in notes[0], notes
