"""tests/test_marketing_metrics_poll.py — per-post metrics poller + admin join.

Mirrors tests/test_marketing_social_publisher.py: tmp_path for all I/O, injected
now= for determinism, engine modules imported inside each test, ZERO live network
(the Buffer transport is mocked via _transport, or a fully-stubbed publisher is
injected into poll()).

Covers:
  * BufferPublisher.fetch_post_metrics: success (metrics + externalLink),
    empty-metrics honesty, no_post, GraphQL error, empty id — all fail-soft
  * _normalize_metrics maps Buffer tokens → console keys, drops junk, keeps raw
  * poller gather_targets: dedupe across status_ledger + publications, 7-day filter
  * poller --dry-run lists targets, writes nothing
  * poller no-token → dark no-op (exit 0, no write)
  * poller happy path (stub publisher) → post_metrics.jsonl row shape, empty-row note
  * external_url backfill lands on the metrics row (publications.jsonl not rewritten)
  * admin publisher() join: fail-soft when ledger absent; joins latest metrics + url
  * publisher media attach: config gate off → no attach; on → public URL only
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

_NOW = datetime(2026, 7, 23, 15, 0, 0, tzinfo=timezone.utc)
_ISO = "%Y-%m-%dT%H:%M:%SZ"


# ─────────────────────────────────────────────────────────────────────────────
# Seed helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed_posted(tmp_path: Path, *, external_id: str, account: str = "flagship",
                 as_of: str = "2026-07-23", at: datetime = _NOW, text: str = "signal post") -> str:
    """Drive one item queued→approved→posting→posted with a Buffer receipt."""
    from engine.marketing.outbox import make_item, enqueue, transition
    it = make_item(account=account, kind="signal", text=text, as_of=as_of,
                   provenance="content_studio", now=at)
    enqueue(it, root=tmp_path, max_per_account_day=99)
    transition(it["id"], "approved", actor="t", root=tmp_path)
    transition(it["id"], "posting", actor="t", root=tmp_path)
    transition(it["id"], "posted", actor="publisher", root=tmp_path, note="published",
               receipt={"backend": "buffer", "external_id": external_id,
                        "external_url": None, "at": at.strftime(_ISO)})
    return it["id"]


def _write_publications(tmp_path: Path, rows: list[dict]) -> None:
    import json
    p = tmp_path / "data" / "marketing" / "publications.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _read_metrics_rows(tmp_path: Path) -> list[dict]:
    from engine.marketing.ledgers import read_jsonl
    return read_jsonl(tmp_path / "data" / "marketing" / "post_metrics.jsonl")


class _StubPub:
    """A publisher whose fetch_post_metrics returns canned MetricsResults by id."""

    backend = "buffer"

    def __init__(self, by_id: dict):
        self._by_id = by_id
        self.calls: list[str] = []

    def fetch_post_metrics(self, pid, *, now=None):
        from engine.marketing.social_publisher import MetricsResult
        self.calls.append(pid)
        r = self._by_id.get(pid)
        if r is not None:
            return r
        return MetricsResult(False, None, {}, [], None, "no_post_returned", "buffer",
                             (now or _NOW).strftime(_ISO))


def _metrics_ok(url, metrics, raw=None, updated="2026-07-23T12:00:00Z"):
    from engine.marketing.social_publisher import MetricsResult
    return MetricsResult(True, url, metrics, raw or [], updated, None, "buffer",
                         _NOW.strftime(_ISO))


# ─────────────────────────────────────────────────────────────────────────────
# BufferPublisher.fetch_post_metrics (transport mocked)
# ─────────────────────────────────────────────────────────────────────────────

def test_fetch_metrics_success(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    pub = BufferPublisher(token="tkn")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"post": {
            "id": "buf-1",
            "externalLink": "https://x.com/mastermindx001/status/1",
            "metricsUpdatedAt": "2026-07-23T12:00:00Z",
            "metrics": [
                {"type": "impressions", "name": "Impressions", "value": 1200, "unit": "count"},
                {"type": "reactions", "name": "Likes", "value": 88, "unit": "count"},
                {"type": "retweets", "name": "Reposts", "value": 7, "unit": "count"},
                {"type": "replies", "name": "Comments", "value": 3, "unit": "count"},
                {"type": "urlClicks", "name": "Clicks", "value": 14, "unit": "count"},
                {"type": "engagementRate", "name": "Engagement Rate", "value": 0.081, "unit": "percent"},
            ],
        }}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    res = pub.fetch_post_metrics("buf-1", now=_NOW)
    assert res.ok is True
    assert res.external_url == "https://x.com/mastermindx001/status/1"
    assert res.metrics == {"impressions": 1200, "likes": 88, "reposts": 7,
                           "comments": 3, "clicks": 14, "engagement_rate": 0.081}
    assert res.metrics_updated_at == "2026-07-23T12:00:00Z"
    assert len(res.raw) == 6  # nothing dropped
    # Query carried the post id.
    assert captured["payload"]["variables"]["input"]["id"] == "buf-1"


def test_fetch_metrics_empty_is_honest(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    pub = BufferPublisher(token="tkn")
    monkeypatch.setattr(pub, "_transport", lambda payload: {"data": {"post": {
        "id": "buf-2", "externalLink": "https://x.com/mastermindx001/status/2",
        "metricsUpdatedAt": None, "metrics": []}}})
    res = pub.fetch_post_metrics("buf-2", now=_NOW)
    assert res.ok is True            # empty metrics is NOT a failure
    assert res.metrics == {}
    assert res.raw == []
    assert res.external_url.endswith("/2")


def test_fetch_metrics_no_post(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    pub = BufferPublisher(token="tkn")
    monkeypatch.setattr(pub, "_transport", lambda payload: {"data": {"post": None}})
    res = pub.fetch_post_metrics("buf-x", now=_NOW)
    assert res.ok is False
    assert "no_post" in (res.error or "")


def test_fetch_metrics_graphql_error(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    pub = BufferPublisher(token="tkn")
    monkeypatch.setattr(pub, "_transport",
                        lambda payload: {"errors": [{"message": "bad id"}]})
    res = pub.fetch_post_metrics("buf-x", now=_NOW)
    assert res.ok is False and "bad id" in (res.error or "")


def test_fetch_metrics_empty_id():
    from engine.marketing.social_publisher import BufferPublisher
    res = BufferPublisher(token="tkn").fetch_post_metrics("", now=_NOW)
    assert res.ok is False and res.error == "empty_post_id"


def test_fetch_metrics_network_error_no_raise(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    from urllib.error import URLError
    pub = BufferPublisher(token="tkn")

    def boom(payload):
        raise URLError("refused")

    monkeypatch.setattr(pub, "_transport", boom)
    res = pub.fetch_post_metrics("buf-1", now=_NOW)  # must not raise
    assert res.ok is False and "network_error" in (res.error or "")


def test_normalize_metrics_maps_and_drops():
    from engine.marketing.social_publisher import _normalize_metrics
    out = _normalize_metrics([
        {"type": "impressions", "value": 10},
        {"type": "somethingWeird", "value": 99},         # unmapped → dropped from keys
        {"type": "likes", "value": True},                # bool is not numeric → dropped
        {"type": "clicks", "value": "x"},                # non-numeric → dropped
        {"type": "reposts", "value": 4},
    ])
    assert out == {"impressions": 10, "reposts": 4}


# ─────────────────────────────────────────────────────────────────────────────
# Poller: gather_targets / dry-run / dark / happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_gather_targets_dedupes_and_age_filters(tmp_path):
    import scripts.marketing_metrics_poll as poller
    _seed_posted(tmp_path, external_id="buf-777", at=_NOW)
    _write_publications(tmp_path, [
        {"publication_id": "p1", "account": "flagship", "remote_id": "buf-999",
         "published_at": "2026-07-22T06:00:00Z", "channel": "x"},
        {"publication_id": "p0", "account": "flagship", "remote_id": "buf-OLD",
         "published_at": "2026-07-01T06:00:00Z", "channel": "x"},  # stale > 7d
    ])
    ids = [t["remote_id"] for t in poller.gather_targets(tmp_path, now=_NOW, max_age_days=7)]
    assert set(ids) == {"buf-777", "buf-999"}
    assert "buf-OLD" not in ids


def test_dry_run_lists_and_writes_nothing(tmp_path):
    import scripts.marketing_metrics_poll as poller
    _seed_posted(tmp_path, external_id="buf-777")
    s = poller.poll(tmp_path, now=_NOW, dry_run=True)
    assert s["dry_run"] is True and s["targets"] == 1 and s["polled"] == 0
    assert not (tmp_path / "data" / "marketing" / "post_metrics.jsonl").exists()


def test_no_token_is_dark_noop(tmp_path, monkeypatch):
    import scripts.marketing_metrics_poll as poller
    monkeypatch.delenv("BUFFER_TOKEN", raising=False)
    _seed_posted(tmp_path, external_id="buf-777")
    s = poller.poll(tmp_path, now=_NOW, dry_run=False)  # publisher=None + no token
    assert s["dark"] is True and s["polled"] == 0
    assert not (tmp_path / "data" / "marketing" / "post_metrics.jsonl").exists()


def test_happy_path_row_shape_and_empty_note(tmp_path):
    import scripts.marketing_metrics_poll as poller
    _seed_posted(tmp_path, external_id="buf-777", at=_NOW)
    _write_publications(tmp_path, [
        {"publication_id": "p1", "account": "flagship", "remote_id": "buf-999",
         "published_at": "2026-07-22T06:00:00Z", "channel": "x"}])
    stub = _StubPub({
        "buf-777": _metrics_ok("https://x.com/mastermindx001/status/777",
                               {"impressions": 1200, "likes": 88, "reposts": 7,
                                "comments": 3, "clicks": 14, "engagement_rate": 0.081},
                               raw=[{"type": "impressions", "value": 1200}]),
        "buf-999": _metrics_ok("https://x.com/mastermindx001/status/999", {}, raw=[], updated=None),
    })
    s = poller.poll(tmp_path, now=_NOW, dry_run=False, publisher=stub)
    assert s == {"targets": 2, "polled": 2, "ok": 2, "empty": 1, "failed": 0,
                 "dry_run": False, "dark": False}
    rows = {r["remote_id"]: r for r in _read_metrics_rows(tmp_path)}

    full = rows["buf-777"]
    # Console contract keys.
    assert set(full["metrics"]) >= {"impressions", "likes", "reposts", "comments",
                                    "clicks", "engagement_rate"}
    assert full["account"] == "flagship"
    assert full["external_url"].endswith("/777")
    assert full["metrics_raw"] == [{"type": "impressions", "value": 1200}]
    assert full["metrics_updated_at"] == "2026-07-23T12:00:00Z"
    assert full["polled_at"] == _NOW.strftime(_ISO)
    assert full["ok"] is True and "note" not in full

    empty = rows["buf-999"]
    assert empty["metrics"] == {} and "metrics_empty" in empty["note"]
    assert empty["ok"] is True  # empty-but-fetched is ok


def test_failed_poll_writes_honest_row(tmp_path):
    import scripts.marketing_metrics_poll as poller
    from engine.marketing.social_publisher import MetricsResult
    _seed_posted(tmp_path, external_id="buf-777")
    stub = _StubPub({"buf-777": MetricsResult(False, None, {}, [], None,
                                              "no_post_returned", "buffer", _NOW.strftime(_ISO))})
    s = poller.poll(tmp_path, now=_NOW, dry_run=False, publisher=stub)
    assert s["failed"] == 1 and s["ok"] == 0
    row = _read_metrics_rows(tmp_path)[0]
    assert row["ok"] is False and "poll_failed" in row["note"]


def test_external_url_backfill_from_publications(tmp_path):
    # A publications row lacking external_url; Buffer returns one → it lands on
    # the metrics row (publications.jsonl is NOT rewritten).
    import scripts.marketing_metrics_poll as poller
    import json
    _write_publications(tmp_path, [
        {"publication_id": "p1", "account": "flagship", "remote_id": "buf-999",
         "published_at": "2026-07-22T06:00:00Z", "channel": "x"}])
    pubs_before = (tmp_path / "data" / "marketing" / "publications.jsonl").read_text()
    stub = _StubPub({"buf-999": _metrics_ok("https://x.com/mastermindx001/status/999",
                                            {"impressions": 5})})
    poller.poll(tmp_path, now=_NOW, dry_run=False, publisher=stub)
    row = _read_metrics_rows(tmp_path)[0]
    assert row["external_url"].endswith("/999")
    # publications.jsonl untouched (append-only law)
    assert (tmp_path / "data" / "marketing" / "publications.jsonl").read_text() == pubs_before


# ─────────────────────────────────────────────────────────────────────────────
# Admin publisher() metrics join (fail-soft + latest-wins)
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_join_failsoft_when_ledger_absent(tmp_path):
    import admin.marketing as am
    _seed_posted(tmp_path, external_id="buf-777")
    payload = am.publisher(root=tmp_path)
    assert payload["ok"] is True
    row = payload["recent_posted"][0]
    assert "metrics" not in row          # no ledger → no metrics key
    assert row["external_url"] is None


def test_admin_join_uses_latest_metrics_and_backfills_url(tmp_path):
    import admin.marketing as am
    import json
    _seed_posted(tmp_path, external_id="buf-777")
    mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text("\n".join(json.dumps(r) for r in [
        {"remote_id": "buf-777", "account": "flagship", "external_url": None,
         "metrics": {"impressions": 10}, "polled_at": "2026-07-23T06:00:00Z", "ok": True},
        {"remote_id": "buf-777", "account": "flagship",
         "external_url": "https://x.com/mastermindx001/status/777",
         "metrics": {"impressions": 1200, "likes": 88, "reposts": 7, "comments": 3,
                     "clicks": 14, "engagement_rate": 0.081},
         "polled_at": "2026-07-23T14:00:00Z", "ok": True},
    ]) + "\n", encoding="utf-8")
    row = am.publisher(root=tmp_path)["recent_posted"][0]
    assert row["metrics"]["impressions"] == 1200          # newest poll wins
    assert row["external_url"].endswith("/777")            # backfilled from ledger


# ─────────────────────────────────────────────────────────────────────────────
# Publisher media attach — config gate
# ─────────────────────────────────────────────────────────────────────────────

def test_publisher_media_gate_off_is_text_only():
    import scripts.marketing_publisher as P
    it = {"media": [{"kind": "chart_svg", "path": "data/x.svg", "chart_id": "c1",
                     "media_url": "https://pub-x.r2.dev/marketing/charts/2026-07-23/c1.png"}]}
    assert P._media_paths_for(it, {"media_enabled": False}) == []


def test_publisher_media_gate_on_passes_public_url():
    import scripts.marketing_publisher as P
    it = {"media": [{"kind": "chart_svg", "path": "data/x.svg", "chart_id": "c1",
                     "media_url": "https://pub-x.r2.dev/marketing/charts/2026-07-23/c1.png"}]}
    assert P._media_paths_for(it, {"media_enabled": True}) == \
        ["https://pub-x.r2.dev/marketing/charts/2026-07-23/c1.png"]
    # local-only media (no public url) → text-only even with the gate on
    it2 = {"media": [{"kind": "chart_svg", "path": "data/x.svg", "chart_id": "c1",
                      "media_png_path": "data/marketing/outbox/media/x/c1.png"}]}
    assert P._media_paths_for(it2, {"media_enabled": True}) == []


def test_publisher_attach_flows_through_build_assets(monkeypatch):
    from engine.marketing.social_publisher import BufferPublisher
    import scripts.marketing_publisher as P
    it = {"media": [{"kind": "chart_svg", "path": "data/x.svg", "chart_id": "c1",
                     "media_url": "https://pub-x.r2.dev/marketing/charts/2026-07-23/c1.png"}]}
    media_paths = P._media_paths_for(it, {"media_enabled": True})

    pub = BufferPublisher(token="tkn", organization_id="org-1")
    captured: dict = {}

    def fake_transport(payload):
        captured["payload"] = payload
        return {"data": {"createPost": {"__typename": "PostActionSuccess",
                                        "post": {"id": "buf-1"}}}}

    monkeypatch.setattr(pub, "_transport", fake_transport)
    r = pub.publish(text="hi", channel_id="c9", media_paths=media_paths)
    assert r.ok is True
    assert captured["payload"]["variables"]["input"]["assets"] == \
        [{"image": {"url": "https://pub-x.r2.dev/marketing/charts/2026-07-23/c1.png"}}]


class TestBufferRateLimitIsNameable:
    """The publisher and the engagement poller share ONE token and ONE quota.

    `publish` and `fetch_post_metrics` both go through BufferPublisher._transport
    with the same BUFFER_TOKEN, so a metrics sweep over a few hundred posted
    items can spend the 24h allowance the publisher needs to post at all.

    Before this, a 429 arrived as a bare HTTPError, the public callers turned it
    into a fail-soft "did not send", and it was indistinguishable from Buffer
    being down. Fail-soft is right; indistinguishable is not — a rate limit is
    self-inflicted and fixed by spacing our own calls out, an outage is not.
    """

    @staticmethod
    def _raise(code, headers=None):
        import io
        from urllib.error import HTTPError

        def _fake(req, timeout=None):
            raise HTTPError(req.full_url, code, "boom", headers or {}, io.BytesIO(b""))

        return _fake

    def test_a_429_becomes_a_named_rate_limit_carrying_retry_after(self, monkeypatch):
        from engine.marketing import social_publisher as SP

        monkeypatch.setattr(SP, "urlopen", self._raise(429, {"Retry-After": "900"}))
        client = SP.BufferPublisher(token="t")
        try:
            client._transport({"query": "{}"})
        except SP.BufferRateLimited as exc:
            assert exc.retry_after == "900"
        else:
            raise AssertionError("a 429 did not raise BufferRateLimited")

    def test_it_stays_a_RuntimeError_so_fail_soft_callers_are_unchanged(self, monkeypatch):
        """Every caller catches broadly and must keep doing so.

        This change makes the reason legible; it must not turn a rate limit into
        a crash that takes down a publish sweep.
        """
        from engine.marketing import social_publisher as SP

        assert issubclass(SP.BufferRateLimited, RuntimeError)
        monkeypatch.setattr(SP, "urlopen", self._raise(429))
        try:
            SP.BufferPublisher(token="t")._transport({"query": "{}"})
        except Exception as exc:  # noqa: BLE001 — the shape every caller uses
            assert isinstance(exc, RuntimeError)

    def test_other_http_errors_are_not_reclassified(self, monkeypatch):
        """A 500 is Buffer's problem and must not be blamed on our quota."""
        from urllib.error import HTTPError

        from engine.marketing import social_publisher as SP

        monkeypatch.setattr(SP, "urlopen", self._raise(500))
        try:
            SP.BufferPublisher(token="t")._transport({"query": "{}"})
        except SP.BufferRateLimited:
            raise AssertionError("a 500 was misreported as a rate limit")
        except HTTPError as exc:
            assert exc.code == 500

    def test_the_shared_quota_is_named_on_the_console(self, monkeypatch, capsys):
        """Bare line-start annotation per CLAUDE.md, or GitHub drops it."""
        from engine.marketing import social_publisher as SP

        monkeypatch.setattr(SP, "urlopen", self._raise(429))
        try:
            SP.BufferPublisher(token="t")._transport({"query": "{}"})
        except SP.BufferRateLimited:
            pass
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "buffer-rate-limited" in ln)
        assert line.startswith("::warning title=marketing-buffer-rate-limited::")
        assert "ONE token" in line and "poller" in line
