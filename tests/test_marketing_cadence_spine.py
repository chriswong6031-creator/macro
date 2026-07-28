"""tests/test_marketing_cadence_spine.py — XG-W2 cadence + collision spine.

The four gates this wave has to hold, and the sections that hold them:

  1. The resolver REPLACES the decorative per-account behaviour — a spec's
     posts_per_day / min_spacing_min genuinely bounds emission (§1 unit, §2
     through the live publisher on a fixture clock).
  2. The `session` schema field validates and Cici's committed spec exercises
     it (§3).
  3. Two accounts drawing the same story produce exactly ONE emission (§4).
  4. Cross-account near-dup rejects a candidate near-identical to ANOTHER
     account's recent post (§5).
  5. press_lane + fastlane emit through make_item/validate_item — no
     hand-rolled writer remains (§6, including a source-text grep).

Plus §7 (wire routing is config, not code) and §8 (jitter determinism).

CONVENTIONS. tmp_path for all I/O, an injected `now` everywhere (no wall clock
in any assertion path), zero network. Import closure is stdlib + pyyaml so the
suite runs in full in the marketing-engine lane — nothing here is
importorskip-gated, so it can never decay into a skip-only suite.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# A Wednesday, 12:00 UTC — 20:00 in Hong Kong (inside Cici's evening window).
_WED_UTC = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
# The same Wednesday at 04:00 UTC — 12:00 in Hong Kong (cash session).
_WED_HK_CASH = datetime(2026, 7, 22, 4, 0, 0, tzinfo=timezone.utc)
# The same Wednesday at 18:00 UTC — 02:00 Thursday in Hong Kong (outside both).
_WED_HK_ASLEEP = datetime(2026, 7, 22, 18, 0, 0, tzinfo=timezone.utc)
# A Saturday, for weekend_shape.
_SAT_UTC = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)

_AS_OF = "2026-07-22"


def _profile(**overrides):
    """A CadenceProfile built from a cadence dict, so the tests exercise the
    same parser the persona specs go through."""
    from engine.marketing.cadence_resolver import profile_from_cadence

    cadence = {
        "posts_per_day": 3,
        "min_spacing_min": 120,
        "jitter_min": 0,
        "weekend_shape": "full",
    }
    cadence.update(overrides)
    p = profile_from_cadence("desk", cadence)
    assert p is not None, f"fixture cadence did not parse: {cadence}"
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. The resolver bounds emission — unit level, fixture clock
# ─────────────────────────────────────────────────────────────────────────────

def test_posts_per_day_bounds_emission():
    """The spec's number is the law: at budget, the next post is refused."""
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=2, min_spacing_min=1)
    # Two posts already out today, spaced far enough apart to clear spacing.
    history = [(_WED_UTC - timedelta(hours=6), "signal"),
               (_WED_UTC - timedelta(hours=3), "macro")]

    d = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history)
    assert not d.allow
    assert d.reason == CR.REASON_DAILY_CAP
    assert d.detail["posted_today"] == 2
    assert d.detail["daily_budget"] == 2

    # One fewer post today → allowed.
    d2 = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history[:1])
    assert d2.allow and d2.reason == CR.REASON_OK


def test_min_spacing_bounds_emission():
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=9, min_spacing_min=120)
    history = [(_WED_UTC - timedelta(minutes=30), "signal")]

    d = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history)
    assert not d.allow
    assert d.reason == CR.REASON_MIN_SPACING
    assert d.detail["required_spacing_min"] == 120
    assert d.detail["elapsed_min"] == 30.0

    # 2h01 later the same history clears.
    later = _WED_UTC + timedelta(minutes=91)
    assert CR.resolve("desk", "signal", now=later, profile=prof, history=history).allow


def test_jitter_lengthens_the_floor_never_shortens_it():
    """Jitter is anti-regularity, not a spacing discount."""
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=9, min_spacing_min=100, jitter_min=30)
    history = [(_WED_UTC - timedelta(minutes=100), "signal")]
    d = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history,
                   seed="fixed-seed")
    assert d.detail["required_spacing_min"] >= 100
    assert d.detail["required_spacing_min"] <= 130


def test_a_post_booked_in_the_future_still_blocks_the_spacing_gate():
    """Regression: the publisher advances its in-run history to the BOOKED time
    (now + send jitter), so the next candidate sees a negative elapsed. Reading
    that as "no recent post" would wave the whole backlog through in one sweep —
    the exact burst the spacing floor exists to prevent."""
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=9, min_spacing_min=120)
    booked_ahead = [(_WED_UTC + timedelta(minutes=7), "signal")]
    d = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof,
                   history=booked_ahead)
    assert not d.allow
    assert d.reason == CR.REASON_MIN_SPACING
    assert d.detail["elapsed_min"] < 0


def test_no_profile_abstains_rather_than_inventing_a_bound():
    """An account with no spec is governed exactly as it was before XG-W2."""
    from engine.marketing import cadence_resolver as CR

    d = CR.resolve("no_spec_desk", "signal", now=_WED_UTC, profile=None,
                   history=[(_WED_UTC, "signal")] * 50)
    assert d.allow
    assert d.reason == CR.REASON_NO_PROFILE


def test_weekend_shape_thins_but_never_silences():
    from engine.marketing import cadence_resolver as CR

    light = _profile(posts_per_day=3, weekend_shape="light")
    full = _profile(posts_per_day=3, weekend_shape="full")
    factors = CR.resolver_config(None)["weekend_factors"]

    assert CR.daily_budget(light, _WED_UTC, weekend_factors=factors) == 3
    assert CR.daily_budget(light, _SAT_UTC, weekend_factors=factors) == 1
    assert CR.daily_budget(full, _SAT_UTC, weekend_factors=factors) == 3

    # A 1/day account keeps its single weekend slot — thinning is not silencing.
    tiny = _profile(posts_per_day=1, weekend_shape="light")
    assert CR.daily_budget(tiny, _SAT_UTC, weekend_factors=factors) == 1


def test_shadow_mode_reports_the_refusal_without_binding():
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=1, min_spacing_min=1)
    history = [(_WED_UTC - timedelta(hours=5), "signal")]
    cfg = {"cadence_resolver": {"enabled": False}}
    d = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history,
                   cfg=cfg)
    assert d.allow, "shadow mode must not bind"
    assert d.reason == CR.REASON_SHADOW
    assert d.detail["would_refuse"] == CR.REASON_DAILY_CAP


def test_market_state_seam_is_accepted_and_ignored_in_v1():
    """The XG-W5 seam exists at the signature so wiring the scorer later does
    not touch every call site — and v1 provably does not read it."""
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=1, min_spacing_min=1)
    history = [(_WED_UTC - timedelta(hours=5), "signal")]
    a = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history)
    b = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history,
                   market_state={"opportunity": 99.0, "topic_load": 0.0})
    assert (a.allow, a.reason) == (b.allow, b.reason)


def test_posting_history_reads_the_state_the_publisher_already_keeps():
    """No new intraday store: history comes from the outbox status ledger."""
    from engine.marketing import cadence_resolver as CR
    from engine.marketing.outbox import fold_state

    state = {
        "items": {
            "i1": {"account": "desk", "kind": "signal"},
            "i2": {"account": "desk", "kind": "macro"},
            "i3": {"account": "other", "kind": "signal"},
        },
        "status": {"i1": "posted", "i2": "queued", "i3": "posting"},
        "last": {"i1": {"at": "2026-07-22T09:00:00Z"},
                 "i3": {"at": "2026-07-22T10:00:00Z"}},
    }
    hist = CR.posting_history(state)
    assert [k for k, _ in hist["desk"]] == [datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)]
    assert "other" in hist, "'posting' is in-flight and holds its slot"
    # fold_state's real shape is what posting_history is typed against.
    assert set(fold_state(ROOT / "does" / "not" / "exist")) >= {"items", "status", "last"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. …through the live publisher, on a fixture clock
# ─────────────────────────────────────────────────────────────────────────────

class _FakePublisher:
    backend = "buffer"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        at_iso = (kwargs.get("now") or _WED_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Receipt(True, f"buf-{len(self.calls)}", None, None, self.backend, at_iso)

    def list_channels(self):
        return []


def _write_cfg(tmp_path: Path, *, accounts=("desk",), extra: str = "") -> None:
    chans = "\n".join(f'    {a}: "buf-chan-{i}"' for i, a in enumerate(accounts))
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "marketing.yml").write_text(
        "sentinel:\n"
        "  max_posts_per_account_per_day: -1\n"   # the global backstop, unlimited
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        "  auto_approve: true\n"
        "  min_minutes_between_any_posts: 0\n"    # isolate the resolver
        "  post_jitter_max_min: 0\n"
        "  channels:\n" + chans + "\n"
        + extra,
        encoding="utf-8",
    )


_SPEC_TEMPLATE = """\
id: {id}
persona_kind: branded
archetype: "test desk"
voice: "authoritative desk"
voice_codex:
  register: "plain"
  quirks: []
  emoji_policy: none
  banned: []
  banned_patterns:
    - "first-person trade/position/P&L claims"
    - "fabricated personal experience"
    - "testimonial-style product claims"
  zh: false
beat: "test beat"
tilt:
  signal: 0.40
  chart: 0.12
  mover: 0.10
  theme_list: 0.09
  receipt: 0.08
  event: 0.06
  education: 0.05
  macro: 0.05
  watchlist: 0.05
pipeline: engine
model_tier: default
cadence:
  posts_per_day: {posts_per_day}
  min_spacing_min: {min_spacing_min}
  jitter_min: 0
  weekend_shape: full
{session}isolation:
  profile_id: null
  egress: null
  registered_at: null
  warmed_through: null
  rail: null
context_packs:
  chronicle: [short]
  desks: [macro]
memory: data/marketing/personas/{id}/theses.jsonl
scorecard:
  min_impressions: 20000
  promote_after:
    weeks: 4
    engagement_rate_ci_lower_above: 0.015
  kill_after:
    weeks: 8
    engagement_rate_ci_upper_below: 0.005
  alpha_note: "pre-registered"
"""


def _write_spec(tmp_path: Path, spec_id: str, *, posts_per_day: int,
                min_spacing_min: int, session: str = "") -> None:
    d = tmp_path / "config" / "personas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{spec_id}.yml").write_text(
        _SPEC_TEMPLATE.format(id=spec_id, posts_per_day=posts_per_day,
                              min_spacing_min=min_spacing_min, session=session),
        encoding="utf-8",
    )


def _write_quotes(tmp_path: Path, now: datetime) -> None:
    p = tmp_path / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "live_quotes_snapshot.json").write_text(json.dumps({
        "asof": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": {},
    }), encoding="utf-8")


def _seed_approved(tmp_path: Path, *, account: str, text: str,
                   scheduled_at: str = "2026-07-22T09:00:00Z",
                   kind: str = "event") -> str:
    """Queue + approve one LADDER item (an explicit past slot, so it does not
    take the immediate/breaking path, which is resolver-exempt by config)."""
    from engine.marketing.outbox import make_item, enqueue, transition
    item = make_item(account=account, kind=kind, text=text, as_of=_AS_OF,
                     scheduled_at=scheduled_at, provenance="content_studio",
                     now=_WED_UTC)
    assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"
    assert transition(item["id"], "approved", actor="test", root=tmp_path,
                      now=_WED_UTC)
    return item["id"]


def _run(monkeypatch, tmp_path: Path, fake, *, now: datetime = _WED_UTC) -> int:
    import scripts.marketing_publisher as pub
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("BUFFER_TOKEN", "test-token")
    _write_quotes(tmp_path, now)
    monkeypatch.setattr(pub, "_make_publisher",
                        lambda backend, *, token, cfg: fake)
    return pub.main(["--live", "--root", str(tmp_path),
                     "--now", now.strftime("%Y-%m-%dT%H:%M:%SZ")])


def _seed_posted_earlier(tmp_path: Path, *, account: str, text: str,
                         hours_ago: int) -> str:
    """One item already POSTED earlier today, its ledger rows stamped with the
    fixture clock (the resolver counts by ledger `at`, not by as_of)."""
    from engine.marketing.outbox import make_item, enqueue, transition
    when = _WED_UTC - timedelta(hours=hours_ago)
    item = make_item(account=account, kind="event", text=text, as_of=_AS_OF,
                     scheduled_at="immediate", provenance="content_studio",
                     now=when)
    assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"
    assert transition(item["id"], "approved", actor="test", root=tmp_path, now=when)
    assert transition(item["id"], "posted", actor="test", root=tmp_path, now=when)
    return item["id"]


@pytest.mark.parametrize("posts_per_day,expect_posts", [(1, 0), (2, 1)])
def test_publisher_honours_posts_per_day_from_the_spec(
        monkeypatch, tmp_path, posts_per_day, expect_posts):
    """THE GATE: the spec's posts_per_day genuinely bounds emission.

    The sentinel cap is -1 (unlimited) and the global floor is 0, so the ONLY
    thing that can stop the post is the per-account resolver. One post is
    already out (5h ago, so the spacing floor is long clear — isolating the
    daily budget), and the SAME fixture flips from refused to allowed purely on
    the spec's number, which is what makes this a test of the number rather than
    of "something refused".
    """
    from engine.marketing.outbox import current_statuses

    _write_cfg(tmp_path)
    _write_spec(tmp_path, "desk", posts_per_day=posts_per_day, min_spacing_min=1)
    _seed_posted_earlier(tmp_path, account="desk", hours_ago=5,
                         text="Earlier today the tape was quiet into the open.")
    pending = _seed_approved(tmp_path, account="desk",
                             text="Credit spreads tightened this afternoon.")

    fake = _FakePublisher()
    assert _run(monkeypatch, tmp_path, fake) == 0

    assert len(fake.calls) == expect_posts
    statuses = current_statuses(tmp_path)
    # A refused item is HELD (still approved), never quarantined — it is not a
    # defective post, it is a post the account has no room for today.
    assert statuses[pending] == ("posted" if expect_posts else "approved")


def test_publisher_honours_min_spacing_from_the_spec(monkeypatch, tmp_path):
    """Same run, budget to spare, but the spacing floor holds the second item."""
    from engine.marketing.outbox import current_statuses

    _write_cfg(tmp_path)
    _write_spec(tmp_path, "desk", posts_per_day=9, min_spacing_min=180)
    a = _seed_approved(tmp_path, account="desk", text="Breadth improved into the close today.")
    b = _seed_approved(tmp_path, account="desk", text="Credit spreads tightened this afternoon.")

    fake = _FakePublisher()
    assert _run(monkeypatch, tmp_path, fake) == 0

    statuses = current_statuses(tmp_path)
    assert len(fake.calls) == 1, "min_spacing_min must hold the second post"
    assert sorted(statuses[i] for i in (a, b)) == ["approved", "posted"]


def test_publisher_without_a_spec_is_unchanged(monkeypatch, tmp_path):
    """No spec → the resolver abstains and both items post, exactly as before."""
    _write_cfg(tmp_path)
    _seed_approved(tmp_path, account="desk", text="Breadth improved into the close today.")
    _seed_approved(tmp_path, account="desk", text="Credit spreads tightened this afternoon.")

    fake = _FakePublisher()
    assert _run(monkeypatch, tmp_path, fake) == 0
    assert len(fake.calls) == 2


def _seed_two_breaking(root: Path) -> list[str]:
    """Two APPROVED immediate/breaking items on a 1-post-per-day desk."""
    from engine.marketing.outbox import make_item, enqueue, transition

    ids = []
    for text in ("Breaking one text here today.", "Breaking two text here today."):
        item = make_item(account="desk", kind="breaking", text=text, as_of=_AS_OF,
                         scheduled_at="immediate", provenance="press_lane",
                         now=_WED_UTC)
        assert enqueue(item, root=root, max_per_account_day=99) == "queued"
        assert transition(item["id"], "approved", actor="test", root=root,
                          now=_WED_UTC)
        ids.append(item["id"])
    return ids


def test_immediate_items_are_exempt_by_config(monkeypatch, tmp_path):
    """The 2026-07-27 operator ruling ("breaking has no limits") survives XG-W2 —
    and it survives as a CONFIG KEY, not a buried constant.

    Two independent roots with identical fixtures; the ONLY difference is
    cadence_resolver.exempt_immediate.
    """
    from engine.marketing.outbox import current_statuses

    exempt, bounded = tmp_path / "exempt", tmp_path / "bounded"
    for root, extra in ((exempt, ""),
                        (bounded, "cadence_resolver:\n  exempt_immediate: false\n")):
        root.mkdir()
        _write_cfg(root, extra=extra)
        _write_spec(root, "desk", posts_per_day=1, min_spacing_min=1)
        ids = _seed_two_breaking(root)
        assert all(current_statuses(root)[i] == "approved" for i in ids), \
            "fixture must start with BOTH items approved, or the test is vacuous"

    fake = _FakePublisher()
    assert _run(monkeypatch, exempt, fake) == 0
    assert len(fake.calls) == 2, "immediate items are resolver-exempt by default"

    fake2 = _FakePublisher()
    assert _run(monkeypatch, bounded, fake2) == 0
    assert len(fake2.calls) == 1, "exempt_immediate: false must bound breaking too"


# ─────────────────────────────────────────────────────────────────────────────
# 3. The `session` schema field — validation + Cici's committed spec
# ─────────────────────────────────────────────────────────────────────────────

_GOOD_SESSION = (
    "  session:\n"
    "    tz: Asia/Hong_Kong\n"
    "    windows:\n"
    '      - "08:00-17:00"\n'
    "    outside_window_posts_per_day: 1\n"
)


def test_session_field_validates(tmp_path):
    from engine.marketing import personas as P

    _write_spec(tmp_path, "sessiondesk", posts_per_day=3, min_spacing_min=60,
                session=_GOOD_SESSION)
    spec, errors = P.load_spec(tmp_path / "config" / "personas" / "sessiondesk.yml")
    assert errors == [], errors
    assert spec is not None
    assert spec.cadence["session"]["tz"] == "Asia/Hong_Kong"


@pytest.mark.parametrize("bad_session,expect", [
    ("  session:\n    tz: Not/AZone\n    windows:\n      - \"08:00-17:00\"\n"
     "    outside_window_posts_per_day: 0\n", "not a resolvable IANA zone"),
    ("  session:\n    tz: Asia/Hong_Kong\n    windows: []\n"
     "    outside_window_posts_per_day: 0\n", "non-empty list"),
    ("  session:\n    tz: Asia/Hong_Kong\n    windows:\n      - \"morning\"\n"
     "    outside_window_posts_per_day: 0\n", "unparseable range"),
    ("  session:\n    tz: Asia/Hong_Kong\n    windows:\n      - \"08:00-17:00\"\n"
     "    outside_window_posts_per_day: 9\n", "exceeds posts_per_day"),
    ("  session:\n    tz: Asia/Hong_Kong\n    windows:\n      - \"08:00-17:00\"\n",
     "missing key"),
])
def test_session_field_rejects_bad_specs(tmp_path, bad_session, expect):
    from engine.marketing import personas as P

    _write_spec(tmp_path, "baddesk", posts_per_day=3, min_spacing_min=60,
                session=bad_session)
    _spec, errors = P.load_spec(tmp_path / "config" / "personas" / "baddesk.yml")
    assert any(expect in e for e in errors), errors


def test_cici_spec_exercises_the_session_field():
    """The gap XG-W1 flagged is closed: Cici's Asia weighting has ENGINE behind
    it, not a prose note."""
    from engine.marketing import cadence_resolver as CR
    from engine.marketing import personas as P

    specs = P.load_all(ROOT)
    cici = specs["cici"]
    assert "session" in cici.cadence, "Cici's spec must declare a session"

    prof = CR.load_profile("cici", specs=specs)
    assert prof is not None and prof.has_session
    assert prof.tz == "Asia/Hong_Kong"
    assert prof.outside_window_posts_per_day == 1

    # 12:00 and 20:00 Hong Kong are in session; 02:00 is not.
    assert CR.in_session(prof, _WED_HK_CASH)
    assert CR.in_session(prof, _WED_UTC)
    assert not CR.in_session(prof, _WED_HK_ASLEEP)


def test_cici_out_of_session_allowance_is_spent_then_refused():
    """The weighting is real: one slot may fall outside the Asia windows, the
    next one is refused for being out of session.

    Every timestamp below is chosen to land on the SAME Hong Kong calendar day
    (Thu 2026-07-23) and outside both of her windows, and to clear her 150-minute
    spacing floor — otherwise an earlier gate would fire and the session branch
    would never be reached.
    """
    from engine.marketing import cadence_resolver as CR
    from engine.marketing import personas as P

    prof = CR.load_profile("cici", specs=P.load_all(ROOT))
    assert prof is not None

    now = datetime(2026, 7, 22, 21, 0, tzinfo=timezone.utc)      # 05:00 Thu HK
    earlier = datetime(2026, 7, 22, 17, 0, tzinfo=timezone.utc)  # 01:00 Thu HK
    assert not CR.in_session(prof, now) and not CR.in_session(prof, earlier)

    # Nothing posted yet → the single out-of-window allowance is available.
    d0 = CR.resolve("cici", "macro", now=now, profile=prof, history=[])
    assert d0.allow and d0.reason == CR.REASON_OK

    # One post already made out of window on the same HK day → allowance spent.
    spent = [(earlier, "macro")]
    d1 = CR.resolve("cici", "macro", now=now, profile=prof, history=spent)
    assert not d1.allow
    assert d1.reason == CR.REASON_OUTSIDE_SESSION
    assert d1.detail["outside_window_posted_today"] == 1

    # The SAME history is fine once she is IN session — the windows are the point.
    in_session_now = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)  # 10:00 Thu HK
    d2 = CR.resolve("cici", "macro", now=in_session_now, profile=prof, history=spent)
    assert d2.allow, d2.detail


def test_session_windows_may_wrap_past_midnight():
    from engine.marketing import cadence_resolver as CR

    prof = _profile(session={"tz": "UTC", "windows": ["22:00-02:00"],
                             "outside_window_posts_per_day": 0})
    assert CR.in_session(prof, datetime(2026, 7, 22, 23, 0, tzinfo=timezone.utc))
    assert CR.in_session(prof, datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc))
    assert not CR.in_session(prof, datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# 4. One conversation, one owner
# ─────────────────────────────────────────────────────────────────────────────

def _press_item(iid: str, *, handle: str, headline: str,
                truth_status_id: str = "", source_tier: str = "") -> dict:
    """One press FeedItem.

    ``truth_status_id`` is the lane's own claim identity: two mirror reports of
    ONE Truth post share it, so two DIFFERENTLY-WORDED items can be the same
    story. That is what makes a story-lock test a story-lock test — with
    identical wording the cross-account near-dup radar would refuse the second
    item first and the lock would never be exercised.
    """
    item = {
        "id": iid,
        "source": f"x_{handle}",
        "source_name": handle,
        "x_handle": handle,
        "url": f"https://example.test/{iid}",
        "published_at": "2026-07-22T11:58:00Z",
        "headline": headline,
        "body_snippet": headline,
        "corroboration_class": "direct-quote",
    }
    if truth_status_id:
        item["truth_status_id"] = truth_status_id
    if source_tier:
        item["source_tier"] = source_tier
    return item


_PRESS_CFG = {
    "satire_blocklist": [],
    "wire": {"flagship_top_k_per_day": 9, "flagship_salience_floor": 0.0,
             "corroboration_window_s": 1800, "rail_salience_floor": 0.0,
             "voice": {"enabled": False}, "tape": {"enabled": False}},
}


#: Two reports of ONE Truth post: same claim id, genuinely different wording.
#: The wording difference is deliberate — it clears the cross-account near-dup
#: bar so the ONLY thing that can refuse the second item is the one-owner lock.
#: ``source_tier: mirror`` + direct-quote is what clears the corroboration gate
#: to "instant" for a single primary source (press_corroboration §1).
_STORY_A = _press_item(
    "tw:mirror-a:1", handle="trumpstruth", truth_status_id="tsid-9001",
    source_tier="mirror",
    headline="Trump orders new tariffs on Chinese semiconductors")
_STORY_B = _press_item(
    "tw:mirror-b:1", handle="cnn_truth_backfill", truth_status_id="tsid-9001",
    source_tier="mirror",
    headline="Beijing chip levies announced by the White House this afternoon")


def test_two_accounts_same_story_produce_exactly_one_emission(tmp_path):
    """THE GATE. Two accounts draw the same story; exactly one emits."""
    from engine.marketing.outbox import read_items, token_jaccard
    from engine.marketing.press_lane import run_press_tick

    # Precondition: the two reports are NOT near-duplicates, so this test can
    # only pass because of the lock.
    assert token_jaccard(_STORY_A["headline"], _STORY_B["headline"]) < 0.5

    # Tick 1: routing sends the class to deskA — it emits and takes the lock.
    cfg_a = {"wire_routing": {"default": "deskA"},
             "story_lock": {"enabled": True, "window_minutes": 720}}
    res_a = run_press_tick([_STORY_A], root=tmp_path, now=_WED_UTC, cfg=cfg_a,
                           press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert len(res_a["emitted"]) == 1
    assert res_a["emitted"][0]["account"] == "deskA"

    # Tick 2: the SAME story in different words, routed to deskB, with a fresh
    # seen-set so nothing but the lock can stop it.
    cfg_b = {"wire_routing": {"default": "deskB"},
             "story_lock": {"enabled": True, "window_minutes": 720}}
    res_b = run_press_tick([_STORY_B], root=tmp_path,
                           now=_WED_UTC + timedelta(minutes=5),
                           cfg=cfg_b, press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert res_b["emitted"] == [], "a second account must not draw a locked story"
    locked = [s for s in res_b["skipped"] if s["reason"] == "story_locked"]
    assert locked, f"expected a story_locked skip, got {res_b['skipped']}"
    assert locked[0]["owner"] == "deskA"

    # Exactly ONE emission is in the canonical queue.
    queued = read_items(tmp_path)
    assert len(queued) == 1
    assert queued[0]["account"] == "deskA"


def test_the_lock_releases_after_its_window(tmp_path):
    """A developing story may be picked up by another desk once the window is
    past — the lock is ownership, not permanent exclusivity."""
    from engine.marketing.outbox import read_items
    from engine.marketing.press_lane import run_press_tick

    cfg = {"wire_routing": {"default": "deskA"},
           "story_lock": {"enabled": True, "window_minutes": 60}}
    run_press_tick([_STORY_A], root=tmp_path, now=_WED_UTC, cfg=cfg,
                   press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert len(read_items(tmp_path)) == 1

    cfg_b = dict(cfg, wire_routing={"default": "deskB"})
    res = run_press_tick([_STORY_B], root=tmp_path, now=_WED_UTC + timedelta(hours=3),
                         cfg=cfg_b, press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert len(res["emitted"]) == 1, res["skipped"]
    assert res["emitted"][0]["account"] == "deskB"


def test_the_lock_is_cross_account_only():
    """An account re-drawing its OWN story is a repeat (the near-dup guard's
    job), not a lock violation — refusing it here would double-punish."""
    from engine.marketing import story_lock as SL

    key = SL.story_key(cluster_key="claim:policy:tic:AAPL")
    items = [{"account": "deskA", "created_at": "2026-07-22T11:00:00Z",
              "source": {"story_key": key}}]
    assert SL.check("deskA", key, items, now=_WED_UTC).allowed
    assert not SL.check("deskB", key, items, now=_WED_UTC).allowed


def test_an_unidentifiable_story_never_locks():
    """An empty key must not be able to silence an unrelated story."""
    from engine.marketing import story_lock as SL

    assert SL.story_key() == ""
    items = [{"account": "deskA", "created_at": "2026-07-22T11:00:00Z",
              "source": {"story_key": ""}}]
    v = SL.check("deskB", "", items, now=_WED_UTC)
    assert v.allowed and v.reason == "no_key"


def test_story_key_prefers_the_cluster_key_then_id_then_headline():
    from engine.marketing import story_lock as SL

    assert SL.story_key(cluster_key="c1", event_id="e1", headline="h").startswith("c:")
    assert SL.story_key(event_id="e1", headline="h").startswith("e:")
    assert SL.story_key(headline="Some Headline!").startswith("h:")
    # The headline fallback is normalization-stable.
    assert SL.story_key(headline="Some  Headline!") == SL.story_key(headline="some headline")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Cross-account near-dup radar
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_account_near_dup_rejects_another_accounts_recent_post(tmp_path):
    """THE GATE, at enqueue time."""
    from engine.marketing.outbox import (
        cross_account_threshold, enqueue, make_item, read_items, token_jaccard,
    )

    a_text = "The dollar gave back yesterday's bid as two-year yields slipped."
    b_text = "The dollar gave back yesterday's bid while two-year yields slipped."
    assert token_jaccard(a_text, b_text) >= cross_account_threshold(None)

    a = make_item(account="deskA", kind="macro", text=a_text, as_of=_AS_OF,
                  provenance="content_studio", now=_WED_UTC)
    b = make_item(account="deskB", kind="macro", text=b_text, as_of=_AS_OF,
                  provenance="content_studio", now=_WED_UTC)
    assert enqueue(a, root=tmp_path) == "queued"
    assert enqueue(b, root=tmp_path) == "cross_account_duplicate"
    assert len(read_items(tmp_path)) == 1


def test_cross_account_threshold_comes_from_sentinel_config():
    """Config tunes the bar; it never disarms it (no config → Sentinel default)."""
    from engine.marketing.outbox import cross_account_threshold

    assert cross_account_threshold({"sentinel": {"near_dup_jaccard": 0.9}}) == 0.9
    default = cross_account_threshold(None)
    assert 0.0 < default < 1.0
    # Stricter than the same-account bar, on purpose.
    from engine.marketing.outbox import _NEAR_DUP_JACCARD
    assert default < _NEAR_DUP_JACCARD


def test_cross_account_radar_covers_the_press_lane(tmp_path):
    """The point of routing the fast lanes through the canonical path: they
    inherit the guard. deskB's near-identical wire copy is refused."""
    from engine.marketing.outbox import make_item, enqueue, read_items
    from engine.marketing.press_lane import run_press_tick

    headline = "Oil spikes after a strike near the Strait of Hormuz"
    # deskA already queued near-identical copy through the ordinary path.
    prior = make_item(account="deskA", kind="macro",
                      text=f"{headline}\n\n{headline}", as_of=_AS_OF,
                      provenance="content_studio", now=_WED_UTC)
    assert enqueue(prior, root=tmp_path) == "queued"

    cfg = {"wire_routing": {"default": "deskB"}, "story_lock": {"enabled": False}}
    res = run_press_tick([_press_item("tw:c:1", handle="FirstSquawk", headline=headline)],
                         root=tmp_path, now=_WED_UTC, cfg=cfg,
                         press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert res["emitted"] == []
    assert any(s["reason"] == "outbox_refused" for s in res["skipped"])
    assert len(read_items(tmp_path)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. Outbox KINDS hardening — no hand-rolled writer remains
# ─────────────────────────────────────────────────────────────────────────────

def test_wire_and_breaking_and_earnings_are_admitted_kinds():
    from engine.marketing.outbox import KINDS

    assert {"wire", "breaking", "earnings"} <= set(KINDS)


def _module_symbols(rel: str) -> tuple[set[str], set[str], set[str]]:
    """(function names, called names, module-level assigned names) for a source
    file, read from its AST.

    AST, not a text grep, on purpose: a grep over the raw source matches the
    guard's OWN explanatory prose — the comments that say what was removed
    contain the very strings the guard hunts, so a text-scanning version of this
    test passes only while nobody documents the change.
    """
    import ast

    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    funcs, calls, assigns = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                calls.add(f.id)
            elif isinstance(f, ast.Attribute):
                calls.add(f.attr)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns.add(t.id)
    return funcs, calls, assigns


def test_no_hand_rolled_outbox_writer_remains():
    """THE GATE. Neither fast lane may build or persist its own outbox record.

    `json.dump` is the signature of the bypass: both lanes used to serialize
    their own `data/marketing/outbox/<id>.json` — a shape no reader consumed,
    which is how they skipped every dedup guard in enqueue().
    """
    for rel in ("engine/marketing/press_lane.py", "engine/marketing/fastlane.py"):
        funcs, calls, _ = _module_symbols(rel)
        assert not {f for f in funcs if f.startswith("_write_outbox")}, \
            f"{rel}: a hand-rolled outbox writer survives"
        assert "dump" not in calls, f"{rel}: still serializing raw outbox JSON"
        assert "make_item" in calls, f"{rel}: does not use the canonical builder"
        assert "validate_item" in calls, f"{rel}: does not validate"
        assert "enqueue" in calls, f"{rel}: does not go through the queue"


def test_press_emission_is_a_valid_canonical_item(tmp_path):
    from engine.marketing.outbox import SCHEMA_ID, read_items, validate_item
    from engine.marketing.press_lane import run_press_tick

    cfg = {"wire_routing": {"default": "flagship"}}
    res = run_press_tick(
        [_press_item("tw:d:1", handle="FirstSquawk",
                     headline="Retail sales unchanged in the latest print")],
        root=tmp_path, now=_WED_UTC, cfg=cfg, press_cfg=_PRESS_CFG,
        state={}, seen_ids=set())
    assert len(res["emitted"]) == 1
    item = res["emitted"][0]
    assert item["schema"] == SCHEMA_ID
    assert item["kind"] == "breaking"
    assert isinstance(item["text"], str) and item["text"].strip()
    assert isinstance(item["priority"], int)
    assert validate_item(item) == []
    # …and it is in the canonical queue, which is what the publisher folds.
    assert [q["id"] for q in read_items(tmp_path)] == [item["id"]]
    # No stray per-item JSON.
    assert list((tmp_path / "data" / "marketing" / "outbox").glob("*.json")) == []


def test_text_flattens_headline_and_body():
    """The flattening lives in outbox (the schema owns it), not in a lane."""
    from engine.marketing.outbox import compose_text

    assert compose_text("Head", "Body") == "Head\n\nBody"
    assert compose_text("Head", "") == "Head"
    assert compose_text("", "Body") == "Body"
    assert compose_text("", "") == ""


def test_press_items_inherit_the_same_account_near_dup_guard(tmp_path):
    """The whole point of the canonical path: the fast lanes now dedupe."""
    from engine.marketing.outbox import read_items
    from engine.marketing.press_lane import run_press_tick

    headline = "Copper hits a record on a supply disruption in Chile"
    cfg = {"wire_routing": {"default": "flagship"}, "story_lock": {"enabled": False}}
    for iid in ("tw:e:1", "tw:e:2"):   # two distinct feed ids, same copy
        run_press_tick([_press_item(iid, handle="FirstSquawk", headline=headline)],
                       root=tmp_path, now=_WED_UTC, cfg=cfg,
                       press_cfg=_PRESS_CFG, state={}, seen_ids=set())
    assert len(read_items(tmp_path)) == 1, "identical copy must dedupe at enqueue"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Wire routing is config, not code
# ─────────────────────────────────────────────────────────────────────────────

def test_routing_is_read_from_config():
    from engine.marketing.wire_routing import route

    cfg = {"wire_routing": {"default": "flagship",
                            "classes": {"macro_print": "mastermind_news"}},
           "desk_network": {"accounts": [{"id": "mastermind_news", "enabled": True},
                                         {"id": "flagship", "enabled": True}]}}
    assert route("macro_print", cfg=cfg) == "mastermind_news"
    assert route("company_news", cfg=cfg) == "flagship"      # unmapped → default
    assert route("macro_print", cfg={}) == "flagship"        # no config → fallback


def test_routing_to_a_dark_account_falls_back_and_says_so(capsys):
    """Liveness is not routing: a route onto a disabled desk falls back to the
    default and prints a START-OF-LINE annotation (house law) so the operator
    sees both the intent and the fact that it is not in force."""
    from engine.marketing.wire_routing import route

    cfg = {"wire_routing": {"default": "flagship",
                            "classes": {"macro_print": "mastermind_news"}},
           "desk_network": {"accounts": [{"id": "mastermind_news", "enabled": False},
                                         {"id": "flagship", "enabled": True}]}}
    assert route("macro_print", cfg=cfg) == "flagship"
    out = capsys.readouterr().out
    warn = [ln for ln in out.splitlines() if "wire-routing-dark" in ln]
    assert warn, f"no annotation emitted: {out!r}"
    assert warn[0].startswith("::warning"), "annotation must start the line"


def test_committed_config_routes_every_class_to_a_live_account():
    """The shipped map must not silently route a class into the dark."""
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    from engine.marketing.wire_routing import routing_table

    table = routing_table(cfg, root=ROOT)
    assert table, "wire_routing.classes is empty — the lane has no map"
    enabled = {a["id"] for a in cfg["desk_network"]["accounts"]
               if a.get("enabled") and not a.get("disabled")}
    for klass, account in table.items():
        assert account in enabled, f"{klass} routes to the dark account {account}"


def test_the_fast_lanes_have_no_hardcoded_account():
    """The uncharted gap XG-W2 closed. A module-level `_ACCOUNT` constant is what
    made six of the seven live Buffer channels unreachable from the wire lane.

    Checked against the AST's module-level assignments, so the comment that
    EXPLAINS the removal cannot satisfy the test that enforces it.
    """
    for rel in ("engine/marketing/press_lane.py", "engine/marketing/fastlane.py"):
        _funcs, calls, assigns = _module_symbols(rel)
        assert "_ACCOUNT" not in assigns, f"{rel}: module-level account constant"
        assert "route" in calls or "_route_account" in calls, \
            f"{rel}: does not resolve its account through wire routing"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Jitter determinism (no clock, no RNG, in any path)
# ─────────────────────────────────────────────────────────────────────────────

def test_jitter_is_seeded_and_deterministic():
    from engine.marketing.cadence_resolver import jitter_minutes

    assert jitter_minutes("seed-a", 30) == jitter_minutes("seed-a", 30)
    assert 0 <= jitter_minutes("seed-a", 30) <= 30
    assert jitter_minutes("anything", 0) == 0
    # Different seeds spread across the range (not a constant function).
    spread = {jitter_minutes(f"item-{i}", 30) for i in range(40)}
    assert len(spread) > 5


def test_resolver_verdict_is_reproducible():
    """Two identical calls give identical verdicts — nothing samples a clock."""
    from engine.marketing import cadence_resolver as CR

    prof = _profile(posts_per_day=5, min_spacing_min=90, jitter_min=25)
    history = [(_WED_UTC - timedelta(minutes=95), "signal")]
    a = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history,
                   seed="ob-1")
    b = CR.resolve("desk", "signal", now=_WED_UTC, profile=prof, history=history,
                   seed="ob-1")
    assert a.as_dict() == b.as_dict()
