"""tests/test_marketing_social_publisher.py — W1 live social publisher tests.

Mirrors tests/test_marketing_outbox.py: pure/fail-soft assertions, tmp_path for
all file I/O, injected now= for determinism, engine module imported INSIDE each
test function, and ZERO live network — every HTTP path is mocked via the
publisher's single _transport() seam or a fully fake publisher.

Covers:
  * tweet_length counts any URL as 23 chars
  * validate_postable flags over-280 / disallowed-link / empty
  * BufferPublisher.publish success → Receipt(ok=True); GraphQL-error and
    network-error → Receipt(ok=False) with NO raise
  * BufferPublisher.list_channels parses channels (mocked transport)
  * runner with kill-switch OFF or without --live → zero transport / nothing posted
  * runner quarantines an over-280 item
  * runner happy path → approved→posting→posted, receipt recorded, cap respected
  * runner idempotency → second run does not double-post
  * runner leaves a startup 'posting' item alone (reported, never reposted)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


_FIXED_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-19"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed_approved_item(tmp_path: Path, *, text: str = "$PLTR reclaimed the 50-day. Watching the soldiers now.",
                        account: str = "flagship", as_of: str = _AS_OF,
                        scheduled_at: str = "immediate") -> str:
    """Enqueue one item and drive it to 'approved'. Returns its id."""
    from engine.marketing.outbox import make_item, enqueue, transition
    item = make_item(
        account=account, kind="signal", text=text, as_of=as_of,
        scheduled_at=scheduled_at, provenance="content_studio", now=_FIXED_NOW,
    )
    # Raise the ENQUEUE-time cap (the outbox's weeks_1_2 floor is 2/account/day)
    # so tests can seed several approved items; the PUBLISHER-tier daily cap is a
    # separate gate exercised via config in the runner tests.
    enqueue(item, root=tmp_path, max_per_account_day=99)
    transition(item["id"], "approved", actor="test", root=tmp_path)
    return item["id"]


def _write_publish_cfg(tmp_path: Path, *, channel: str = "buf-chan-123",
                       links_allowed: bool = True) -> None:
    """Write a minimal config/marketing.yml with the publish + sentinel blocks."""
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
        f"    flagship: \"{channel}\"\n"
        "  links_allowed:\n"
        f"    flagship: {'true' if links_allowed else 'false'}\n",
        encoding="utf-8",
    )


class _FakePublisher:
    """Stand-in backend that records calls and never touches the network."""

    backend = "buffer"

    def __init__(self, *, ok: bool = True, external_id: str = "buf-post-1",
                 error: str | None = None) -> None:
        self._ok = ok
        self._external_id = external_id
        self._error = error
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        at = kwargs.get("now") or _FIXED_NOW
        at_iso = at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self._ok:
            return Receipt(True, self._external_id, None, None, self.backend, at_iso)
        return Receipt(False, None, None, self._error or "boom", self.backend, at_iso)

    def list_channels(self):
        return [{"id": "buf-chan-123", "service": "twitter", "name": "Flagship"}]


class _RateLimitedPublisher(_FakePublisher):
    """The 2026-07-30 live failure, verbatim: a 429 with retryable=True.

    Not `ok=False` alone — that is a VERDICT on the post and the publisher is
    right to fail it. The whole distinction this fixture exists to exercise is
    the transient one: the publisher and the engagement poller share ONE Buffer
    token and ONE 24h allowance, so a metrics sweep can spend the posting
    budget out from under a perfectly good post.
    """

    def __init__(self) -> None:
        super().__init__(ok=False, error=(
            'http_error 429: {"errors":[{"message":"Too many requests from '
            'this client. Please try again later."}]}'))

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        at = (kwargs.get("now") or _FIXED_NOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Receipt(False, None, None, self._error, self.backend, at,
                       retryable=True)


def _write_fresh_quotes(tmp_path: Path, now: str,
                        tickers: tuple[str, ...] = ("PLTR",),
                        *, only_if_absent: bool = False) -> None:
    """Write a live-quotes snapshot so the publisher's tape gate can verify
    the fixture tickers (a signal it cannot verify is HELD, by design)."""
    import json as _json
    from datetime import datetime, timezone as _tz
    p = tmp_path / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    snap = p / "live_quotes_snapshot.json"
    if only_if_absent and snap.exists():
        return  # a test staged its own tape (e.g. an adverse quote) — keep it
    dt = datetime.fromisoformat(now.replace("Z", "+00:00")).replace(tzinfo=_tz.utc)
    ts_ms = int(dt.timestamp() * 1000)
    snap.write_text(_json.dumps({
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
    _write_fresh_quotes(tmp_path, now, only_if_absent=True)
    if fake_publisher is not None:
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake_publisher)
    full_argv = list(argv) + ["--root", str(tmp_path), "--now", now]
    return pub.main(full_argv)


# ─────────────────────────────────────────────────────────────────────────────
# 1. tweet_length
# ─────────────────────────────────────────────────────────────────────────────

def test_tweet_length_plain_text():
    from engine.marketing.social_publisher import tweet_length
    assert tweet_length("hello world") == len("hello world")


def test_tweet_length_url_counts_as_23():
    from engine.marketing.social_publisher import tweet_length
    # A long URL still counts as exactly 23 regardless of its real length.
    long_url = "https://mastermind-x.com/some/really/long/path?with=query&and=more#frag"
    body = f"see this {long_url}"
    # "see this " (9 chars) + 23 for the URL.
    assert tweet_length(body) == 9 + 23


def test_tweet_length_appended_link_adds_24():
    from engine.marketing.social_publisher import tweet_length
    # Non-empty body + appended link = body + 1 space + 23.
    n_body_only = tweet_length("body text")
    n_with_link = tweet_length("body text", link="https://mastermind-x.com/x")
    assert n_with_link == n_body_only + 1 + 23


def test_tweet_length_link_on_empty_body_no_leading_space():
    from engine.marketing.social_publisher import tweet_length
    assert tweet_length("", link="https://mastermind-x.com/x") == 23


# ─────────────────────────────────────────────────────────────────────────────
# 2. validate_postable
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_postable_ok():
    from engine.marketing.social_publisher import validate_postable
    assert validate_postable("A clean short post.", None, links_allowed=False) == []


def test_validate_postable_flags_empty():
    from engine.marketing.social_publisher import validate_postable
    assert "empty_text" in validate_postable("   ", None, links_allowed=True)


def test_validate_postable_flags_over_280():
    from engine.marketing.social_publisher import validate_postable
    problems = validate_postable("x" * 281, None, links_allowed=True)
    assert any(p.startswith("over_280:") for p in problems)


def test_validate_postable_flags_disallowed_link():
    from engine.marketing.social_publisher import validate_postable
    problems = validate_postable("body", "https://mastermind-x.com/x", links_allowed=False)
    assert "link_not_allowed" in problems


def test_validate_postable_allows_link_when_allowed():
    from engine.marketing.social_publisher import validate_postable
    problems = validate_postable("body", "https://mastermind-x.com/x", links_allowed=True)
    assert "link_not_allowed" not in problems


# ─────────────────────────────────────────────────────────────────────────────
# 3. BufferPublisher.publish — success + error paths (mocked transport)
# ─────────────────────────────────────────────────────────────────────────────

def test_buffer_publish_success(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {
            "__typename": "PostActionSuccess",
            "post": {"id": "buf-post-42", "text": "hi", "dueAt": None},
        }}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    receipt = pub.publish(text="hello", channel_id="chan-9", now=_FIXED_NOW)

    assert receipt.ok is True
    assert receipt.external_id == "buf-post-42"
    assert receipt.backend == "buffer"
    assert receipt.error is None
    # Mutation carried the right input.
    inp = captured["payload"]["variables"]["input"]
    assert inp["channelId"] == "chan-9"
    assert inp["text"] == "hello"
    assert inp["mode"] == "addToQueue"  # no scheduled_at → queue


def test_buffer_publish_scheduled_sets_dueat(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {
            "__typename": "PostActionSuccess",
            "post": {"id": "buf-post-7"},
        }}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    receipt = pub.publish(text="hi", channel_id="c1",
                          scheduled_at="2026-07-20T15:00:00Z", now=_FIXED_NOW)
    assert receipt.ok is True
    inp = captured["payload"]["variables"]["input"]
    assert inp["mode"] == "customScheduled"
    assert inp["dueAt"] == "2026-07-20T15:00:00Z"


def test_buffer_publish_past_slot_bumps_dueat_into_future(monkeypatch):
    """Regression: a DUE item's slot time is in the PAST by post time. Buffer
    rejects a past dueAt ("must be in the future"), which failed EVERY post — the
    real reason the account never published. The past slot must be bumped ahead
    of now, not sent verbatim."""
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {
            "__typename": "PostActionSuccess", "post": {"id": "buf-post-8"}}}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    # slot two hours BEFORE _FIXED_NOW (2026-07-19 12:00) — the failing case.
    receipt = pub.publish(text="hi", channel_id="c1",
                          scheduled_at="2026-07-19T10:00:00Z", now=_FIXED_NOW)
    assert receipt.ok is True
    inp = captured["payload"]["variables"]["input"]
    assert inp["mode"] == "customScheduled"
    assert inp["dueAt"] > "2026-07-19T12:00:00Z"   # strictly after now → Buffer accepts
    assert inp["dueAt"] != "2026-07-19T10:00:00Z"  # not the past slot


def test_buffer_publish_immediate_uses_share_now_not_queue(monkeypatch):
    """SHARE-NOW (cadence masterplan F3): a breaking item with no readable
    schedule must go out as customScheduled at now+lead. addToQueue would park it
    in *Buffer's own* queue — arbitrary latency on the one post whose entire
    value is speed."""
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {
            "__typename": "PostActionSuccess", "post": {"id": "buf-post-9"}}}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    receipt = pub.publish(text="breaking", channel_id="c1", scheduled_at=None,
                          now=_FIXED_NOW, immediate=True)
    assert receipt.ok is True
    inp = captured["payload"]["variables"]["input"]
    assert inp["mode"] == "customScheduled"
    assert inp["dueAt"] > "2026-07-19T12:00:00Z"     # strictly in the future
    assert "addToQueue" not in str(captured["payload"])


def test_buffer_publish_immediate_honours_a_real_future_schedule(monkeypatch):
    """immediate=True is a floor, not an override: an explicitly future send time
    (the floor-respecting last_post+10m the publisher computes) is still used."""
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {
            "__typename": "PostActionSuccess", "post": {"id": "buf-post-10"}}}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    receipt = pub.publish(text="breaking", channel_id="c1",
                          scheduled_at="2026-07-19T12:08:00Z",
                          now=_FIXED_NOW, immediate=True)
    assert receipt.ok is True
    assert captured["payload"]["variables"]["input"]["dueAt"] == "2026-07-19T12:08:00Z"


def test_effective_due_at_immediate_flag():
    """Unit: only the immediate flag turns a blank/garbage schedule into a
    share-now time — the default stays None (addToQueue), unchanged."""
    from engine.marketing.social_publisher import _effective_due_at

    assert _effective_due_at(None, _FIXED_NOW) is None
    assert _effective_due_at("not-a-date", _FIXED_NOW) is None
    assert _effective_due_at("", _FIXED_NOW, immediate=True) == "2026-07-19T12:03:00Z"
    assert _effective_due_at("immediate", _FIXED_NOW, immediate=True) == "2026-07-19T12:03:00Z"
    # a genuinely future time is honoured either way
    assert (_effective_due_at("2026-07-19T18:00:00Z", _FIXED_NOW, immediate=True)
            == "2026-07-19T18:00:00Z")


def test_buffer_publish_appends_link_to_text(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: captured.setdefault("payload", payload) or {
                            "data": {"createPost": {"__typename": "PostActionSuccess",
                                                    "post": {"id": "p1"}}}})
    pub.publish(text="body", channel_id="c1", link="https://mastermind-x.com/x", now=_FIXED_NOW)
    assert captured["payload"]["variables"]["input"]["text"] == "body https://mastermind-x.com/x"


def test_buffer_publish_media_url_becomes_asset(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: captured.setdefault("payload", payload) or {
                            "data": {"createPost": {"__typename": "PostActionSuccess",
                                                    "post": {"id": "p1"}}}})
    pub.publish(text="body", channel_id="c1",
                media_paths=["https://cdn.example.com/chart.png",
                             "data/marketing/outbox/media/local.svg"],
                now=_FIXED_NOW)
    inp = captured["payload"]["variables"]["input"]
    # Only the public URL becomes an asset; the local path is skipped.
    assert inp["assets"] == [{"image": {"url": "https://cdn.example.com/chart.png"}}]


def test_buffer_publish_graphql_error(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"errors": [{"message": "bad token"}]})
    receipt = pub.publish(text="hi", channel_id="c1", now=_FIXED_NOW)
    assert receipt.ok is False
    assert receipt.external_id is None
    assert "bad token" in (receipt.error or "")


def test_buffer_publish_mutation_error_union(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"data": {"createPost": {
                            "__typename": "MutationError", "message": "channel disconnected"}}})
    receipt = pub.publish(text="hi", channel_id="c1", now=_FIXED_NOW)
    assert receipt.ok is False
    assert "channel disconnected" in (receipt.error or "")


def test_buffer_publish_network_error_no_raise(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    from urllib.error import URLError

    pub = BufferPublisher(token="tkn", organization_id="org-1")

    def boom(payload):
        raise URLError("connection refused")

    monkeypatch.setattr(pub, "_transport", boom)
    receipt = pub.publish(text="hi", channel_id="c1", now=_FIXED_NOW)  # must NOT raise
    assert receipt.ok is False
    assert "network_error" in (receipt.error or "")


def test_buffer_publish_empty_token_fails_soft(monkeypatch):
    # No token → _transport raises RuntimeError; publish must convert to a
    # failed Receipt, never propagate.
    from engine.marketing.social_publisher import BufferPublisher
    monkeypatch.delenv("BUFFER_TOKEN", raising=False)
    pub = BufferPublisher(token="", organization_id="org-1")
    receipt = pub.publish(text="hi", channel_id="c1", now=_FIXED_NOW)
    assert receipt.ok is False
    assert receipt.error


def test_buffer_list_channels_parses(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    monkeypatch.setattr(pub, "_transport", lambda payload: {"data": {"channels": [
        {"id": "c1", "service": "twitter", "name": "Flagship"},
        {"id": "c2", "service": "linkedin", "name": "Research"},
    ]}})
    chans = pub.list_channels()
    assert chans == [
        {"id": "c1", "service": "twitter", "name": "Flagship"},
        {"id": "c2", "service": "linkedin", "name": "Research"},
    ]


def test_buffer_list_channels_error_returns_empty(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    pub = BufferPublisher(token="tkn", organization_id="org-1")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"errors": [{"message": "nope"}]})
    assert pub.list_channels() == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Runner — kill-switch / --live gating (ZERO transport)
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_default_dry_run_posts_nothing(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher()
    # No --live flag at all.
    rc = _run_publisher(monkeypatch, tmp_path, [], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []  # zero transport / publish calls
    assert current_statuses(tmp_path)[item_id] == "approved"  # unchanged


def test_runner_live_flag_without_kill_switch_posts_nothing(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher()
    # --live passed BUT kill-switch off → must degrade to dry-run.
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=False)

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[item_id] == "approved"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Runner — quarantine an over-280 item
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_quarantines_over_280(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path, text="x" * 300)

    fake = _FakePublisher()
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []  # never attempted to post the bad item
    assert current_statuses(tmp_path)[item_id] == "quarantined"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Runner — happy path: approved → posting → posted, receipt recorded, cap
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_happy_path_posts_and_records_receipt(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, read_ledger
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher(ok=True, external_id="buf-post-777")
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1
    assert current_statuses(tmp_path)[item_id] == "posted"

    # The ledger recorded the approved→posting→posted chain.
    rows = [r for r in read_ledger(tmp_path) if r.get("id") == item_id]
    tos = [r["to"] for r in rows]
    assert tos == ["approved", "posting", "posted"]

    # The posted row carries the receipt with the external id.
    posted_row = next(r for r in rows if r["to"] == "posted")
    assert posted_row["receipt"]["external_id"] == "buf-post-777"
    assert posted_row["receipt"]["backend"] == "buffer"


def test_runner_respects_daily_cap(monkeypatch, tmp_path):
    """cap=2 → with one already posted today, only 1 more of 2 approved posts."""
    from engine.marketing.outbox import current_statuses, make_item, enqueue, transition
    _write_publish_cfg(tmp_path)

    # One item already posted today consumes a slot. The cap counter is
    # ledger-based (last transition date), so the fixture stamps its ledger
    # rows with the test's fixed clock, not the wall clock.
    already = make_item(account="flagship", kind="signal", text="Already posted today.",
                        as_of=_AS_OF, provenance="content_studio", now=_FIXED_NOW)
    enqueue(already, root=tmp_path, max_per_account_day=99)
    transition(already["id"], "approved", actor="t", root=tmp_path, now=_FIXED_NOW)
    transition(already["id"], "posted", actor="t", root=tmp_path, now=_FIXED_NOW)

    # Two more approved and due LADDER items (explicit past slot — the immediate
    # default is cap-EXEMPT as of 2026-07-27 and would defeat this cap test).
    a = _seed_approved_item(tmp_path, text="Second post of the day here.",
                            scheduled_at="2026-07-19T12:00:00Z")
    b = _seed_approved_item(tmp_path, text="Third post would exceed the cap.",
                            scheduled_at="2026-07-19T12:00:00Z")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    # cap=2, one already posted → exactly ONE more posts, one skipped.
    assert len(fake.calls) == 1
    statuses = current_statuses(tmp_path)
    posted = [i for i in (a, b) if statuses[i] == "posted"]
    still_approved = [i for i in (a, b) if statuses[i] == "approved"]
    assert len(posted) == 1
    assert len(still_approved) == 1


def test_runner_cap_counts_nightly_item_posted_today(monkeypatch, tmp_path):
    """A NIGHTLY item (as_of = the GENERATION day, i.e. yesterday) that posted
    TODAY still consumes a cap slot. as_of-based counting made these posts
    invisible, letting same-day slot runs breach the Sentinel daily cap."""
    from engine.marketing.outbox import current_statuses, make_item, enqueue, transition
    _write_publish_cfg(tmp_path)

    # Generated by the nightly on 07-18, posted this morning (07-19).
    nightly = make_item(account="flagship", kind="signal", text="Nightly plan item.",
                        as_of="2026-07-18", provenance="content_studio", now=_FIXED_NOW)
    enqueue(nightly, root=tmp_path, max_per_account_day=99)
    transition(nightly["id"], "approved", actor="t", root=tmp_path, now=_FIXED_NOW)
    transition(nightly["id"], "posted", actor="t", root=tmp_path, now=_FIXED_NOW)

    # Two more approved and due LADDER items (explicit past slot — the immediate
    # default is cap-EXEMPT as of 2026-07-27 and would defeat this cap test).
    a = _seed_approved_item(tmp_path, text="Second post of the day here.",
                            scheduled_at="2026-07-19T12:00:00Z")
    b = _seed_approved_item(tmp_path, text="Third post would exceed the cap.",
                            scheduled_at="2026-07-19T12:00:00Z")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    # cap=2, the nightly post already used a slot today → exactly ONE more posts.
    assert len(fake.calls) == 1
    statuses = current_statuses(tmp_path)
    assert len([i for i in (a, b) if statuses[i] == "posted"]) == 1
    assert len([i for i in (a, b) if statuses[i] == "approved"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. Runner — idempotency: two runs never double-post
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_idempotent_no_double_post(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher(ok=True)
    _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)
    assert current_statuses(tmp_path)[item_id] == "posted"
    assert len(fake.calls) == 1

    # Second run: item is now 'posted' (terminal), not approved → not re-posted.
    fake2 = _FakePublisher(ok=True)
    _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake2, kill_switch=True)
    assert fake2.calls == []
    assert current_statuses(tmp_path)[item_id] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Runner — item stuck in 'posting' at startup: reported, never reposted
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_leaves_stuck_posting_item_alone(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses, make_item, enqueue, transition
    _write_publish_cfg(tmp_path)

    # Simulate a crash mid-post: item is left in 'posting'.
    item = make_item(account="flagship", kind="signal", text="Crashed mid-post item.",
                     as_of=_AS_OF, provenance="content_studio", now=_FIXED_NOW)
    enqueue(item, root=tmp_path, max_per_account_day=99)
    transition(item["id"], "approved", actor="t", root=tmp_path)
    transition(item["id"], "posting", actor="t", root=tmp_path)
    assert current_statuses(tmp_path)[item["id"]] == "posting"

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []  # the stuck item is NOT re-posted
    assert current_statuses(tmp_path)[item["id"]] == "posting"  # left as-is


# ─────────────────────────────────────────────────────────────────────────────
# 9. Runner — account filter + no channel id configured
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_skips_item_with_no_channel(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path, channel="")  # empty channel id
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert fake.calls == []  # no channel id → cannot post
    assert current_statuses(tmp_path)[item_id] == "approved"  # untouched


def test_runner_account_filter(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    flagship_id = _seed_approved_item(tmp_path, account="flagship")
    # A different account with no channel config — filtered out entirely.
    other_id = _seed_approved_item(tmp_path, account="receipts", text="Other desk post.")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live", "--account", "flagship"],
                        fake_publisher=fake, kill_switch=True)

    assert rc == 0
    assert len(fake.calls) == 1
    statuses = current_statuses(tmp_path)
    assert statuses[flagship_id] == "posted"
    assert statuses[other_id] == "approved"  # not in the filtered account


# ─────────────────────────────────────────────────────────────────────────────
# 10. Runner — not-due scheduled item is left approved
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_skips_future_scheduled_item(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    # Scheduled well past --now (2026-07-19T13:00Z).
    item_id = _seed_approved_item(tmp_path, scheduled_at="2026-07-25T15:00:00Z")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True, now="2026-07-19T13:00:00Z")

    assert rc == 0
    assert fake.calls == []  # not due yet
    assert current_statuses(tmp_path)[item_id] == "approved"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Runner — live tape gate (post-time freshness verification)
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_tape_gate_quarantines_adverse_move(monkeypatch, tmp_path):
    """A BULL signal whose ticker is down hard TODAY must never post — the
    plan was written off yesterday's close (the 'engine said buy, it's -7%
    on earnings' case). Live run → approved → quarantined, zero network calls."""
    import json as _json
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    now = "2026-07-19T13:00:00Z"
    from datetime import datetime, timezone as _tz
    ts_ms = int(datetime.fromisoformat(now.replace("Z", "+00:00"))
                .replace(tzinfo=_tz.utc).timestamp() * 1000)
    (tmp_path / "data" / "marketing").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "marketing" / "live_quotes_snapshot.json").write_text(
        _json.dumps({"asof": now, "quotes": {
            "PLTR": {"price": 93.0, "prevClose": 100.0, "changePct": -7.0,
                     "ts": ts_ms}}}), encoding="utf-8")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True, now=now)

    assert rc == 0
    assert fake.calls == []  # never reached the network
    assert current_statuses(tmp_path)[item_id] == "quarantined"


def test_runner_tape_gate_holds_unverifiable_signal(monkeypatch, tmp_path):
    """No live quote for the ticker → the signal is HELD (stays approved for
    the next slot), not posted and not quarantined."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher(ok=True)
    import scripts.marketing_publisher as pub
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("BUFFER_TOKEN", "test-token")
    monkeypatch.setattr(pub, "_make_publisher",
                        lambda backend, *, token, cfg: fake)
    # NOTE: bypass _run_publisher on purpose — no snapshot file is written.
    rc = pub.main(["--live", "--root", str(tmp_path),
                   "--now", "2026-07-19T13:00:00Z"])

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[item_id] == "approved"  # held, not killed


def test_runner_tape_gate_dry_run_never_mutates(monkeypatch, tmp_path):
    """Dry-run with an adverse quote: the gate reports but writes nothing."""
    import json as _json
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    now = "2026-07-19T13:00:00Z"
    from datetime import datetime, timezone as _tz
    ts_ms = int(datetime.fromisoformat(now.replace("Z", "+00:00"))
                .replace(tzinfo=_tz.utc).timestamp() * 1000)
    (tmp_path / "data" / "marketing").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "marketing" / "live_quotes_snapshot.json").write_text(
        _json.dumps({"asof": now, "quotes": {
            "PLTR": {"price": 93.0, "prevClose": 100.0, "changePct": -7.0,
                     "ts": ts_ms}}}), encoding="utf-8")

    rc = _run_publisher(monkeypatch, tmp_path, [], kill_switch=False, now=now)

    assert rc == 0
    assert current_statuses(tmp_path)[item_id] == "approved"  # dry-run: no writes


# ─────────────────────────────────────────────────────────────────────────────
# F4: approved items on a channel-less account expire after 3 days
# ─────────────────────────────────────────────────────────────────────────────

def _write_publish_cfg_no_channel(tmp_path: Path) -> None:
    """Config whose flagship channel id is empty → the no-channel skip path."""
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
        "    flagship: \"\"\n"          # NO channel id → cannot post
        "  links_allowed:\n"
        "    flagship: false\n",
        encoding="utf-8",
    )


def test_no_channel_old_item_expires_to_quarantined(monkeypatch, tmp_path):
    """An approved item on a channel-less account, older than 3 days, is
    quarantined 'expired_no_channel' instead of rotting approved forever."""
    from engine.marketing.outbox import current_statuses, read_ledger
    _write_publish_cfg_no_channel(tmp_path)
    now = "2026-07-19T13:00:00Z"
    # as_of 5 days before now → past the 3-day expiry.
    item_id = _seed_approved_item(tmp_path, as_of="2026-07-14")

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True, now=now)

    assert rc == 0
    assert fake.calls == []                                   # never posted
    assert current_statuses(tmp_path)[item_id] == "quarantined"
    row = next(r for r in read_ledger(tmp_path)
               if r.get("id") == item_id and r["to"] == "quarantined")
    assert row["note"] == "expired_no_channel"


def test_no_channel_fresh_item_stays_approved(monkeypatch, tmp_path):
    """A recent item on a channel-less account is NOT expired (still approved)."""
    from engine.marketing.outbox import current_statuses
    _write_publish_cfg_no_channel(tmp_path)
    now = "2026-07-19T13:00:00Z"
    item_id = _seed_approved_item(tmp_path, as_of=_AS_OF)     # today → within 3 days

    fake = _FakePublisher(ok=True)
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True, now=now)

    assert rc == 0
    assert fake.calls == []
    assert current_statuses(tmp_path)[item_id] == "approved"  # skipped, not expired


# ─────────────────────────────────────────────────────────────────────────────
# F5: a posted item also appends a schema-valid row to publications.jsonl
# ─────────────────────────────────────────────────────────────────────────────

def test_posted_item_appends_publication_receipt(monkeypatch, tmp_path):
    from engine.marketing.outbox import current_statuses
    from engine.marketing.ledgers import read_jsonl
    _write_publish_cfg(tmp_path)
    item_id = _seed_approved_item(tmp_path)

    fake = _FakePublisher(ok=True, external_id="buf-post-999")
    rc = _run_publisher(monkeypatch, tmp_path, ["--live"], fake_publisher=fake,
                        kill_switch=True)

    assert rc == 0
    assert current_statuses(tmp_path)[item_id] == "posted"

    pubs = read_jsonl(tmp_path / "data" / "marketing" / "publications.jsonl")
    row = next(p for p in pubs if p.get("asset_id") == item_id)

    # Schema-valid per contracts/marketing_publication_receipt.schema.json:
    # every REQUIRED field present and non-empty (no jsonschema dep in CI).
    schema = json.loads(
        (Path(__file__).resolve().parent.parent
         / "contracts" / "marketing_publication_receipt.schema.json").read_text()
    )
    for field in schema["required"]:
        assert field in row, f"missing required field {field}"
        assert row[field] not in (None, ""), f"empty required field {field}"

    assert row["channel"] == "x"
    assert row["account"] == "flagship"
    assert row["remote_id"] == "buf-post-999"    # the Buffer post id
    assert row["mode"] == "live"
    assert row["correction_state"] == "clean"
    assert row["effective_copy_hash"].startswith("sha256:")


class TestARateLimitIsNotAVerdictOnThePost:
    """A 429 DELETED three flagship posts on 2026-07-30.

    `ok=False` was the only signal a send could give, and the publisher's one
    response to it is `transition(iid, "failed")`. `failed` is in
    outbox._DEAD_STATUSES, so nothing ever picks the item up again — a transient
    quota refusal was permanent. The ledger rows read:

        ob-2026-07-30-85765fdcaa  posting -> failed
        http_error 429: {"errors":[{"message":"Too many requests from this
        client. Please try again later."}]}

    Each was a good post that arrived while the shared Buffer token was out of
    quota. The publisher and the engagement poller authenticate as ONE token
    against ONE 24h allowance, so a metrics sweep can spend the posting budget:
    self-inflicted and transient, and both halves say retry, not discard.

    The risk grows with volume, and this change set increases volume — the press
    wire's salience floor moved 70 -> 30 on the same day.
    """

    def _receipt(self, **kw):
        from engine.marketing.social_publisher import Receipt
        base = dict(ok=False, external_id=None, external_url=None,
                    error="boom", backend="buffer", at="2026-07-31T12:00:00Z")
        base.update(kw)
        return Receipt(**base)

    def test_retryable_defaults_false_so_nothing_else_changes(self):
        """Every existing construction site omits it; none may become retryable."""
        assert self._receipt().retryable is False
        assert self._receipt(ok=True, error=None).retryable is False

    def test_a_429_http_error_is_marked_retryable(self):
        from urllib.error import HTTPError
        from engine.marketing.social_publisher import Receipt

        # The shape the live failures took, before BufferRateLimited existed.
        exc = HTTPError("http://buffer", 429, "Too Many Requests", {}, None)
        r = Receipt(False, None, None, f"http_error {exc.code}: x", "buffer",
                    "2026-07-31T12:00:00Z", retryable=exc.code == 429)
        assert r.retryable is True

    def test_a_400_is_not_retryable(self):
        """"Invalid post: Whoops" is a verdict ON THE POST — retrying it forever
        would spin. Only quota gets a second chance."""
        from urllib.error import HTTPError
        from engine.marketing.social_publisher import Receipt

        exc = HTTPError("http://buffer", 400, "Bad Request", {}, None)
        r = Receipt(False, None, None, f"http_error {exc.code}: x", "buffer",
                    "2026-07-31T12:00:00Z", retryable=exc.code == 429)
        assert r.retryable is False

    def test_a_rate_limited_item_ends_the_run_approved_via_legal_edges(
            self, monkeypatch, tmp_path, capsys):
        """END TO END, not a source grep. The requeue's own defect, closed.

        The first cut of the fix called transition(iid, "approved") directly on
        an item the dispatch loop had just moved to `posting` — and
        TRANSITIONS["posting"] is {posted, failed, quarantined}. The call was
        ILLEGAL: transition() logged and returned False, the return was never
        checked, `rate_limited += 1` ran anyway, and the item was left stuck in
        `posting` FOREVER (reported by the next run's stuck_posting scan, never
        reposted). That is the exact loss the branch exists to prevent, one
        state to the left, and it had simply not fired yet because no 429 had
        landed since the fix shipped.

        The previous version of this test asserted on the SOURCE of main() and
        passed against that broken code — a 1400-character window that the new
        comment block alone overflows. A grep over a branch cannot see whether
        the transition it greps for is legal. Drive the runner instead.
        """
        from engine.marketing.ledgers import read_jsonl
        from engine.marketing.outbox import current_statuses

        _write_publish_cfg(tmp_path)
        item_id = _seed_approved_item(tmp_path)
        fake = _RateLimitedPublisher()

        rc = _run_publisher(monkeypatch, tmp_path, ["--live"],
                            fake_publisher=fake, kill_switch=True)

        assert rc == 0
        assert fake.calls, "the fixture never reached the network seam"
        # THE ASSERTION THE DEFECT FAILS: stuck in `posting` on the old code.
        assert current_statuses(tmp_path)[item_id] == "approved"

        ledger = [r for r in read_jsonl(
            tmp_path / "data" / "marketing" / "outbox" / "status_ledger.jsonl")
            if r.get("id") == item_id]
        walk = [(r["from"], r["to"]) for r in ledger]
        assert walk[-3:] == [("approved", "posting"),
                             ("posting", "failed"),
                             ("failed", "approved")], walk
        assert "rate_limited" in (ledger[-2].get("note") or "")
        assert "requeued" in (ledger[-1].get("note") or "")
        # And it is genuinely re-armable: the next sweep sees an approved item.
        assert "posting" not in current_statuses(tmp_path)[item_id]

    def test_a_rate_limited_item_does_not_consume_a_posting_slot(
            self, monkeypatch, tmp_path):
        """The requeue must not charge the account's daily cap for a post that
        never went out — nor for the intermediate `failed` row it walks through.

        posted_today_by_account counts ids whose FOLDED status is posted/posting
        with a ledger row dated today. The walk ends on `approved`, so the item
        is invisible to it; the earlier `posting` row is folded over. Pinned
        because the obvious wrong fix (leaving the item in `posting` so it
        "holds its slot") is exactly the defect."""
        from engine.marketing.outbox import fold_state, posted_today_by_account

        _write_publish_cfg(tmp_path)
        item_id = _seed_approved_item(tmp_path)

        _run_publisher(monkeypatch, tmp_path, ["--live"],
                       fake_publisher=_RateLimitedPublisher(), kill_switch=True)

        state = fold_state(tmp_path)
        # The date the counter would charge, taken from the item's OWN last
        # ledger row rather than from the injected --now: the publisher's
        # transitions stamp wall-clock UTC, so a hardcoded fixture date makes
        # this assertion vacuously true on every code path.
        charged_day = str(state["last"][item_id]["at"])[:10]
        assert posted_today_by_account(state, charged_day) == {}, (
            "a rate-limited post that never went out is consuming a posting "
            "slot — the account's day shrinks by exactly the posts Buffer "
            "refused")

    def test_a_stranded_requeue_is_announced_at_line_start(
            self, monkeypatch, tmp_path, capsys):
        """Both legs are CHECKED, and a refusal is loud.

        The old code ignored transition()'s return entirely. If either leg is
        ever refused the item is stranded mid-post and nothing in this system
        will move it, so the operator has to hear about it — as a bare
        line-start annotation, because a logger prefix makes GitHub drop it.
        """
        from engine.marketing import outbox as OB

        _write_publish_cfg(tmp_path)
        item_id = _seed_approved_item(tmp_path)

        real = OB.transition

        def _refuse_the_requeue(iid, to, **kw):
            # Only the SECOND leg — so the item really does end up stranded in
            # `failed` with no way back, which is the shape the annotation is for.
            if to == "approved" and kw.get("actor") == "publisher":
                return False          # simulate a lost/rejected ledger append
            return real(iid, to, **kw)

        # main() does `from engine.marketing import outbox as _outbox`, so the
        # local name is the module object itself — patching the attribute here
        # reaches the call site.
        monkeypatch.setattr(OB, "transition", _refuse_the_requeue)
        _run_publisher(monkeypatch, tmp_path, ["--live"],
                       fake_publisher=_RateLimitedPublisher(), kill_switch=True)

        out = capsys.readouterr().out
        line = next((l for l in out.splitlines()
                     if l.startswith("::warning title=publisher-requeue-stuck::")), "")
        assert line, out
        assert item_id in line, line

    def test_posting_to_approved_is_NOT_a_legal_transition(self):
        """The pin that would have caught this on day one.

        `posting` is the in-flight state, and it may only resolve to a verdict:
        posted, failed or quarantined. Anything that wants to re-arm an
        in-flight item must walk out through `failed` first.
        """
        from engine.marketing import outbox as OB

        legal = getattr(OB, "TRANSITIONS", None)
        assert legal is not None, "transition table moved — this pin is blind"
        assert "approved" not in legal["posting"], (
            "posting -> approved became legal; if that was deliberate, the "
            "publisher's two-step requeue should collapse back to one step")
        assert "failed" in legal["posting"], "the only legal walk out is broken"

    def test_failed_to_approved_is_a_legal_transition(self):
        """The requeue relies on it; it was reachable but never used."""
        from engine.marketing import outbox as OB

        legal = getattr(OB, "TRANSITIONS", None)
        assert legal is not None, "transition table moved — this pin is blind"
        assert "approved" in legal["failed"], (
            "failed -> approved is no longer legal, so the requeue silently "
            "becomes a no-op and a rate-limited post is lost again")


class TestTheFoldIsTheOnlyStatusThePublisherReads:
    """items.jsonl's top-level `status` is FROZEN at write time.

    `make_item` stamps `"status": "queued"` and `validate_item` REQUIRES that
    value at creation; nothing ever rewrites the row. So all 236 live rows read
    `queued` regardless of what actually happened to them, and the status ledger
    replayed on top is the only truth. A writer that read `item["status"]`
    instead of folding would see a fresh queue every run — which is how a
    double-publish attempt and a reverted quarantine got into the ledger (69
    rows whose `from` did not match the item's real prior state).

    The publisher and the social backend hold NO such read today — every status
    in `scripts/marketing_publisher.py` comes from `_outbox.fold_state(root)`
    (`state["status"]`, threaded through as `statuses`), and
    `engine/marketing/social_publisher.py` reads no item status at all. These
    are the BEHAVIOURAL pins that keep it that way: a source grep would pass on
    a read reintroduced through a helper, so drive the runner instead and put
    the two states in open conflict.
    """

    def _seed_with_a_frozen_status(self, tmp_path: Path, *, ledger_to: str) -> str:
        """An item whose items.jsonl row says `queued` and whose ledger does not."""
        from engine.marketing.outbox import current_statuses
        item_id = _seed_approved_item(
            tmp_path,
            text="$PLTR reclaimed the 50-day. Watching the soldiers now.")
        from engine.marketing.outbox import transition
        assert transition(item_id, ledger_to, actor="test", root=tmp_path)

        raw = json.loads((tmp_path / "data" / "marketing" / "outbox"
                          / "items.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert raw["status"] == "queued", (
            "items.jsonl no longer freezes status at write time — the premise "
            "of this whole class moved")
        assert current_statuses(tmp_path)[item_id] == ledger_to
        return item_id

    def test_a_quarantined_item_is_not_resurrected_by_its_frozen_row(
            self, monkeypatch, tmp_path):
        from engine.marketing.outbox import current_statuses

        _write_publish_cfg(tmp_path)
        item_id = self._seed_with_a_frozen_status(tmp_path, ledger_to="quarantined")
        fake = _FakePublisher(ok=True)

        assert _run_publisher(monkeypatch, tmp_path, ["--live"],
                              fake_publisher=fake, kill_switch=True) == 0

        assert fake.calls == [], (
            "a QUARANTINED item reached the network — the dispatch loop is "
            "reading the frozen items.jsonl status, not the ledger fold")
        assert current_statuses(tmp_path)[item_id] == "quarantined"

    def test_a_posted_item_is_never_posted_twice(self, monkeypatch, tmp_path):
        """The double-publish shape, directly."""
        _write_publish_cfg(tmp_path)
        self._seed_with_a_frozen_status(tmp_path, ledger_to="posted")
        fake = _FakePublisher(ok=True)

        _run_publisher(monkeypatch, tmp_path, ["--live"],
                       fake_publisher=fake, kill_switch=True)

        assert fake.calls == [], "a POSTED item was sent a second time"

    def test_the_auto_approve_pass_reads_the_fold_too(self, monkeypatch, tmp_path,
                                                      caplog):
        """Not just the dispatch loop: the auto-approve pass is the OTHER writer,
        and it is the one that would have to re-approve a dead item first.

        THIS is the assertion with teeth. A stale read cannot corrupt the ledger
        — `transition()` re-folds and refuses an illegal edge, so the write
        fails closed either way — but it CAN make the pass select a dead item as
        a candidate and attempt the write. That attempt is observable, and its
        absence is the proof the candidate set came from the fold. (The two
        tests above are the weaker direction on purpose: a stale read reports
        every item as `queued`, which is never dispatch-eligible, so they pin
        the outcome without being able to distinguish the mechanism.)
        """
        import logging

        from engine.marketing.ledgers import read_jsonl

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "marketing.yml").write_text(
            "sentinel:\n"
            "  max_posts_per_account_per_day: 2\n"
            "publish:\n"
            "  backend: buffer\n"
            "  require_approval: true\n"
            "  auto_approve: true\n"
            "  auto_approve_scope: all\n"
            "  channels:\n"
            "    flagship: \"buf-chan-123\"\n",
            encoding="utf-8",
        )
        item_id = self._seed_with_a_frozen_status(tmp_path, ledger_to="quarantined")

        with caplog.at_level(logging.INFO, logger="marketing_publisher"):
            _run_publisher(monkeypatch, tmp_path, ["--live"],
                           fake_publisher=_FakePublisher(ok=True), kill_switch=True)

        considered = [r.getMessage() for r in caplog.records
                      if "auto-approve" in r.getMessage() and item_id in r.getMessage()]
        assert not considered, (
            "the auto-approve pass considered a QUARANTINED item — its candidate "
            f"set is reading items.jsonl's frozen status, not the fold: {considered}")

        rows = [r for r in read_jsonl(tmp_path / "data" / "marketing" / "outbox"
                                      / "status_ledger.jsonl")
                if r.get("id") == item_id]
        assert rows[-1]["to"] == "quarantined", rows
        assert not any(r.get("from") == "quarantined" for r in rows), (
            "something transitioned OUT of a terminal state — the writer is "
            "reading a stale status")
