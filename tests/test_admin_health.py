"""admin.health — status bucketing, verdict flip, and tolerant freshness parsing.

Regression cover for the audit finding that the Health panel reported a permanent
"Nightly pipeline: Healthy" (dead==0 was always true) while hiding every
blocked/failed/no_creds/empty feed, and anchored dashboard freshness on file mtime
(meaningless in a git checkout)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admin.health as H  # noqa: E402


def test_parse_any_age_tolerates_the_forex_date_format():
    # ISO (most markets) and the 'Jul 22, 2026' variant forex/commodities emit both parse;
    # the old _parse_iso_age_hours choked on the latter, so freshness fell back to mtime.
    assert H._parse_any_age_hours("2026-07-21") is not None
    assert H._parse_any_age_hours("Jul 22, 2026") is not None
    assert H._parse_any_age_hours("Jul 22 2026") is not None
    assert H._parse_any_age_hours("junk") is None
    assert H._parse_any_age_hours(None) is None


def test_summary_buckets_every_status_and_verdict_flips_on_failure(monkeypatch):
    fake = {
        "last_run": None,   # None → not stale, so the verdict is driven purely by down-count
        "sources": {
            "a": {"status": "ok"}, "b": {"status": "ok"}, "c": {"status": "stale"},
            "d": {"status": "failed"},     # a genuine failure must flip the verdict
            "e": {"status": "blocked"},    # throttled upstream — surfaced, doesn't flip
            "f": {"status": "no_creds"},   # config gap — gated
            "g": {"status": "empty"},      # ran, no rows
        },
        "circuit_breaker": {},
    }
    monkeypatch.setattr(H, "_read_json", lambda p: fake if str(p).endswith("run_status.json") else None)
    monkeypatch.setattr(H, "market_freshness", lambda: [])   # skip disk reads
    s = H.summary()
    b = s["sources"]
    # every feed is accounted for — no hidden statuses
    assert b["ok"] == 2 and b["stale"] == 1 and b["down"] == 1
    assert b["blocked"] == 1 and b["gated"] == 1 and b["empty"] == 1
    assert b["ok"] + b["stale"] + b["down"] + b["blocked"] + b["gated"] + b["empty"] + b["other"] == b["total"] == 7
    # the single 'failed' feed flips the verdict off "Healthy" (the old dead==0 rule never did)
    assert s["down_count"] == 1
    assert s["healthy"] is False


def test_summary_healthy_when_all_feeds_deliver(monkeypatch):
    fake = {"last_run": None, "sources": {"a": {"status": "ok"}, "b": {"status": "ok"}},
            "circuit_breaker": {}}
    monkeypatch.setattr(H, "_read_json", lambda p: fake if str(p).endswith("run_status.json") else None)
    monkeypatch.setattr(H, "market_freshness", lambda: [])
    s = H.summary()
    assert s["healthy"] is True and s["down_count"] == 0
