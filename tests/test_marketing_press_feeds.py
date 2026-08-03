"""tests/test_marketing_press_feeds.py — PRESS-FEEDS B1 acceptance tests (D05 Add.2).

Fixture-driven; ZERO live network. MARKETING_LLM_ENABLED / MARKETING_PUBLISH_ENABLED
never set in tests. Covers:
  1. TrumpstruthProvider: RSS -> FeedItems (RT + truth: namespace fields, dedupe id).
  2. CnnTruthBackfillProvider: JSON -> FeedItems; shares status ids (cross-mirror dedupe).
  3. TwitterApiIoProvider: fixture -> FeedItems + since-id cursor advance; spend-cap STOP
     emits the ::warning at LINE START (capsys + line.startswith("::")); key-unset skip.
  4. Corroboration gates: direct-quote single-source instant; hearsay single-source blocked
     -> digest/attributed; 2-source-in-window passes.
  5. Satire blocklist drops at ingestion.
  6. Relevance ranks a tariff headline above celebrity noise (reuses existing scorer).
  7. Daemon tick with kill-switches unset = no-op exit 0; dry-run bypasses.
  8. Emission idempotency (seen-ledger); flagship top-K cap.
  9. Config register sanity + gitignore guard.
 10. AlpacaNewsProvider (Intelligence Desk V2 §C): recorded-shape mapping, the
     per-provider cold-start cursor prime, strictly-newer-than-cursor ingest,
     the keyless no-op + once-per-process preflight notice, offline/dry-run,
     the min_interval politeness floor, and the 429 backoff ladder.
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
FIXTURES = ROOT / "tests" / "fixtures" / "press"
sys.path.insert(0, str(ROOT))

from engine.marketing.press_providers import (  # noqa: E402
    AlpacaNewsProvider,
    TrumpstruthProvider,
    CnnTruthBackfillProvider,
    TwitterApiIoProvider,
    build_providers,
)
from engine.marketing.press_corroboration import corroboration_decision  # noqa: E402
from engine.marketing.press_lane import run_press_tick  # noqa: E402


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


_REQUIRED_KEYS = {"id", "source", "source_name", "source_tier",
                  "url", "published_at", "headline", "body_snippet"}

_TS_CFG = {"key": "trumpstruth", "source_name": "Truth Social (via trumpstruth.org)",
           "author": "Donald J. Trump"}
_CNN_CFG = {"key": "cnn_truth_backfill", "source_name": "Truth Social (via CNN archive)"}


# ---------------------------------------------------------------------------
# 1. TrumpstruthProvider
# ---------------------------------------------------------------------------

class TestTrumpstruth:
    def _items(self):
        return TrumpstruthProvider(_TS_CFG).parse(_load("trumpstruth_feed.xml"))

    def test_parses_all_items(self):
        assert len(self._items()) == 3

    def test_schema_keys_and_mirror_tier(self):
        for it in self._items():
            assert not (_REQUIRED_KEYS - set(it.keys()))
            assert it["source_tier"] == "mirror"
            assert it["author"] == "Donald J. Trump"

    def test_truth_namespace_status_id_captured(self):
        tariff = next(i for i in self._items() if "tariff" in i["headline"].lower())
        assert tariff["truth_status_id"] == "116993810062084166"
        # url points at the original Truth Social status, not the mirror
        assert "truthsocial.com" in tariff["url"]

    def test_retweet_flagged(self):
        rts = [i for i in self._items() if i["is_retweet"]]
        assert len(rts) == 1
        assert "RT:" in rts[0]["body_snippet"]

    def test_dedupe_id_stable_on_status_id(self):
        # Same feed parsed twice -> identical ids (dedupe by status id).
        a = {i["truth_status_id"]: i["id"] for i in self._items()}
        b = {i["truth_status_id"]: i["id"] for i in self._items()}
        assert a == b

    def test_iso_timestamps(self):
        for it in self._items():
            dt = datetime.fromisoformat(it["published_at"].replace("Z", "+00:00"))
            assert dt.tzinfo is not None

    def test_direct_quote_class(self):
        for it in self._items():
            assert it["corroboration_class"] == "direct-quote"


# ---------------------------------------------------------------------------
# 2. CnnTruthBackfillProvider
# ---------------------------------------------------------------------------

class TestCnnBackfill:
    def _items(self):
        return CnnTruthBackfillProvider(_CNN_CFG).parse(_load("cnn_truth_archive.json"))

    def test_parses_all_rows(self):
        assert len(self._items()) == 3

    def test_schema_and_tier(self):
        for it in self._items():
            assert not (_REQUIRED_KEYS - set(it.keys()))
            assert it["source_tier"] == "mirror"

    def test_shares_status_ids_with_trumpstruth(self):
        cnn_ids = {i["truth_status_id"] for i in self._items()}
        ts_ids = {i["truth_status_id"] for i in TrumpstruthProvider(_TS_CFG).parse(
            _load("trumpstruth_feed.xml"))}
        # At least the tariff + RT posts are shared -> cross-mirror dedupe surface.
        assert cnn_ids & ts_ids >= {"116993810062084166", "116993809640438974"}

    def test_bad_json_returns_empty(self):
        assert CnnTruthBackfillProvider(_CNN_CFG).parse("{not json") == []


# ---------------------------------------------------------------------------
# 3. TwitterApiIoProvider
# ---------------------------------------------------------------------------

class TestTwitterApiIo:
    def _provider(self, cap=75.0):
        cfg = {
            "handles": [{"handle": "DeItaone", "tier": "fast",
                         "corroboration_class": "hearsay"}],
            "poll_tiers": {"fast": 75, "mid": 105, "slow": 300},
        }
        return TwitterApiIoProvider(cfg, spend_cap_usd=cap, satire_blocklist=["HalfwayPost"])

    def test_parse_tweets_to_feeditems(self):
        prov = self._provider()
        items, since = prov.parse_tweets(
            _load("twitterapiio_last_tweets.json"),
            {"handle": "DeItaone", "corroboration_class": "hearsay"},
            since_id=None,
        )
        assert len(items) == 3
        for it in items:
            assert not (_REQUIRED_KEYS - set(it.keys()))
            assert it["source_tier"] == "x_relay"
            assert it["x_handle"] == "DeItaone"
        # new since-id is the max tweet id seen
        assert since == "1949000000000000003"

    def test_since_id_cursor_gates_old_tweets(self):
        prov = self._provider()
        items, since = prov.parse_tweets(
            _load("twitterapiio_last_tweets.json"),
            {"handle": "DeItaone", "corroboration_class": "hearsay"},
            since_id="1949000000000000002",
        )
        # only the one tweet newer than the cursor survives
        assert len(items) == 1
        assert items[0]["body_snippet"].startswith("*TREASURY SECRETARY")
        assert since == "1949000000000000003"

    def test_key_unset_fetch_skips_cleanly(self, monkeypatch):
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        assert self._provider().fetch(root=ROOT, session_state={}) == []

    def test_spend_cap_stop_emits_warning_at_line_start(self, monkeypatch, capsys):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        state = {"twitterapiio": {"spend": {month: {"requests": 1, "tweets": 1, "usd": 90.0}}}}
        out = self._provider(cap=75.0).fetch(root=ROOT, session_state=state)
        assert out == []
        captured = capsys.readouterr().out
        cap_lines = [ln for ln in captured.splitlines()
                     if "twitterapiio-spend-cap" in ln]
        assert cap_lines, "expected a spend-cap ::warning line"
        # Repo law: GH annotation must START the line (never via a logger).
        assert cap_lines[0].startswith("::"), f"warning not at line start: {cap_lines[0]!r}"
        assert cap_lines[0].startswith("::warning title=twitterapiio-spend-cap::")

    def test_satire_handle_excluded_at_construction(self):
        cfg = {"handles": [
            {"handle": "HalfwayPost", "tier": "fast"},
            {"handle": "DeItaone", "tier": "fast"},
        ]}
        prov = TwitterApiIoProvider(cfg, spend_cap_usd=75.0, satire_blocklist=["HalfwayPost"])
        assert [h["handle"] for h in prov.handles] == ["DeItaone"]


class TestAFailedCallIsStillABilledCall:
    """Fail-CLOSED billing (#3960 reviewer minor).

    ``_request`` collapses a network error, a timeout and an HTTP 4xx/5xx into a
    single ``None``, and the vendor's floor is per REQUEST: "Minimum charge:
    $0.00015 per request". The lane used to ``continue`` past its own accounting
    on that branch, so in OUR ledger every failure was free. A handle that 401s
    or times out on every one of the 288 ticks a day therefore spent real money
    against the shared $75 twitterapi.io bucket while the committed spend state
    read zero -- and that state is the only thing the cap can see.
    """

    def _provider(self, cap=75.0):
        cfg = {"handles": [{"handle": "DeItaone", "tier": "fast",
                            "corroboration_class": "hearsay"}],
               "poll_tiers": {"fast": 75, "mid": 105, "slow": 300}}
        return TwitterApiIoProvider(cfg, spend_cap_usd=cap, satire_blocklist=[])

    @staticmethod
    def _month() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m")

    def test_transport_none_records_the_minimum_charge(self, monkeypatch):
        from engine.marketing import press_providers as pp
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        prov = self._provider()
        monkeypatch.setattr(prov, "_request", lambda *_a, **_k: None)
        state: dict = {}

        assert prov.fetch(root=ROOT, session_state=state) == []

        spend = state["twitterapiio"]["spend"][self._month()]
        assert spend["usd"] > 0, "a failed call was recorded as free"
        assert spend["usd"] == pytest.approx(pp._TW_MIN_CHARGE)
        assert spend["requests"] == 1
        # No tweets arrived, so the per-tweet counter must not move.
        assert int(spend.get("tweets", 0)) == 0

    def test_a_raising_transport_is_billed_the_same(self, monkeypatch):
        """``_request`` swallows its own exceptions into None, so the caller sees
        one branch. Pin that a raising urlopen still lands there and still bills:
        this is the shape a real DNS failure or timeout takes."""
        from engine.marketing import press_providers as pp

        def _boom(*_a, **_k):
            raise OSError("connection reset")

        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        monkeypatch.setattr(pp, "urlopen", _boom, raising=False)
        prov = self._provider()
        state: dict = {}

        assert prov.fetch(root=ROOT, session_state=state) == []

        spend = state["twitterapiio"]["spend"][self._month()]
        assert spend["usd"] == pytest.approx(pp._TW_MIN_CHARGE)
        assert spend["requests"] == 1

    def test_repeated_failures_accumulate_toward_the_cap(self, monkeypatch):
        """The point of billing a failure: a permanently broken handle must walk
        the lane into its own cap instead of polling free forever."""
        from engine.marketing import press_providers as pp
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        state: dict = {}
        for _ in range(5):
            prov = self._provider()
            monkeypatch.setattr(prov, "_request", lambda *_a, **_k: None)
            # A fresh provider each tick, exactly like the workflow: the poll
            # throttle lives in the committed state, so clear it to model five
            # separate ticks rather than one burst.
            state.setdefault("twitterapiio", {}).setdefault("last_poll", {}).clear()
            prov.fetch(root=ROOT, session_state=state)

        spend = state["twitterapiio"]["spend"][self._month()]
        assert spend["requests"] == 5
        assert spend["usd"] == pytest.approx(5 * pp._TW_MIN_CHARGE)

    def test_an_offline_tick_is_still_free(self, monkeypatch):
        """The control. Billing attaches to a REQUEST, not to a tick: an offline
        pass makes no call and must not invent a charge."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        state: dict = {}
        assert self._provider().fetch(root=ROOT, session_state=state,
                                      offline=True) == []
        month = (state.get("twitterapiio") or {}).get("spend") or {}
        assert float((month.get(self._month()) or {}).get("usd", 0.0)) == 0.0

    def test_the_x_intel_lane_already_bills_a_failed_call(self):
        """The sibling lane's accounting is the shape this fix copied, and it is
        pinned here so the two cannot drift apart silently."""
        from engine.marketing import x_intel as xi

        state: dict = {}
        now = datetime.now(tz=timezone.utc)
        # record_call is what Harvester.run calls unconditionally after a
        # _request that may have returned None (0 items extracted).
        cost = xi.record_call(state, 0, cfg={"intel": {}}, now=now)
        assert cost > 0
        assert xi.month_bucket(state, now)["usd"] > 0


# ---------------------------------------------------------------------------
# 4. Corroboration gate (pure)
# ---------------------------------------------------------------------------

class TestCorroboration:
    def test_direct_quote_single_source_instant(self):
        item = {"corroboration_class": "direct-quote", "source_tier": "mirror",
                "event_class": "policy"}
        d = corroboration_decision(item, corroborated_sources=1, window_ok=False)
        assert d["gate"] == "instant"
        assert d["attribution"] == "on Truth Social"

    def test_hearsay_single_political_goes_to_digest(self):
        item = {"corroboration_class": "hearsay", "source_tier": "x_relay",
                "event_class": "policy", "source_name": "@DeItaone"}
        d = corroboration_decision(item, corroborated_sources=1, window_ok=False)
        assert d["gate"] == "digest"

    def test_hearsay_two_sources_in_window_instant(self):
        item = {"corroboration_class": "hearsay", "source_tier": "x_relay",
                "event_class": "policy"}
        d = corroboration_decision(item, corroborated_sources=2, window_ok=True)
        assert d["gate"] == "instant"

    def test_hearsay_two_sources_out_of_window_not_instant(self):
        item = {"corroboration_class": "hearsay", "source_tier": "x_relay",
                "event_class": "policy"}
        d = corroboration_decision(item, corroborated_sources=2, window_ok=False)
        assert d["gate"] == "digest"

    def test_nonpolitical_single_hearsay_attributed(self):
        item = {"corroboration_class": "hearsay", "source_tier": "x_relay",
                "event_class": "company_news", "source_name": "@StockMKTNewz"}
        d = corroboration_decision(item, corroborated_sources=1, window_ok=False)
        assert d["gate"] == "attributed"
        # The admission survives; the ACCOUNT does not (operator de-handling law
        # 2026-08-02 — this used to be "{source_name} reporting", which shipped
        # "-- @FirstSquawk reporting" to the flagship). Full coverage of the
        # credit lives in tests/test_marketing_wire_dehandle.py.
        assert d["attribution"] == "wire reports"
        assert "@StockMKTNewz" not in d["attribution"]

    def test_strict_corroboration_no_confirmation_digest(self):
        item = {"corroboration_class": "hearsay", "source_tier": "x_relay",
                "event_class": "company_news", "strict_corroboration": True,
                "source_name": "@rawsalerts"}
        d = corroboration_decision(item, corroborated_sources=1, window_ok=False)
        assert d["gate"] == "digest"


# ---------------------------------------------------------------------------
# 5-6-8. Press lane tick (satire block, relevance rank, flagship cap, idempotency)
# ---------------------------------------------------------------------------

_MARKET_HOURS = datetime(2026, 7, 27, 16, 0, 0, tzinfo=timezone.utc)  # Monday, ET afternoon


def _fixture_items():
    """Trumpstruth direct-quote items + one satire + one policy-hearsay + one celebrity."""
    ts = TrumpstruthProvider(_TS_CFG).parse(_load("trumpstruth_feed.xml"))
    ts.append({
        "id": "satire1", "source": "x_halfwaypost", "x_handle": "HalfwayPost",
        "source_name": "@HalfwayPost", "source_tier": "x_relay", "url": "",
        "published_at": "2026-07-27T20:00:00Z",
        "headline": "Trump announces 500% tariff on the Moon", "body_snippet": "satire",
    })
    ts.append({
        "id": "hearsay1", "source": "x_DeItaone", "x_handle": "DeItaone",
        "source_name": "@DeItaone", "source_tier": "x_relay", "url": "",
        "published_at": "2026-07-27T20:00:00Z",
        "headline": "Trump told reporters new China tariffs coming",
        "body_snippet": "Trump told reporters new China tariffs coming",
        "corroboration_class": "hearsay",
    })
    ts.append({
        "id": "celeb1", "source": "cnbc_top", "source_name": "CNBC", "source_tier": "wire",
        "url": "https://x", "published_at": "2026-07-27T20:00:00Z",
        "headline": "Pop star announces surprise world tour", "body_snippet": "concert",
    })
    return ts


_CFG = {"breaking": {"llm": {"enabled": False}}}
_PRESS_CFG = {"satire_blocklist": ["HalfwayPost"],
              "wire": {"flagship_top_k_per_day": 3, "flagship_salience_floor": 40.0}}


class TestPressLane:
    def test_satire_blocked_at_ingestion(self, tmp_path):
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=True)
        blocked = [b["id"] for b in res["blocked"]]
        assert "satire1" in blocked
        assert all(b["reason"] == "satire_blocklist" for b in res["blocked"])

    def test_tariff_outranks_celebrity(self, tmp_path):
        # The tariff direct-quote emits; the celebrity headline never does.
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=True)
        emitted_heads = [e["headline"].lower() for e in res["emitted"]]
        assert any("tariff" in h for h in emitted_heads)
        assert not any("pop star" in h for h in emitted_heads)

    def test_single_source_political_hearsay_to_digest(self, tmp_path):
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=True)
        assert "hearsay1" in [d["id"] for d in res["digest"]]

    def test_emitted_items_are_breaking_immediate(self, tmp_path):
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=True)
        assert res["emitted"], "expected at least one emitted item"
        for e in res["emitted"]:
            assert e["kind"] == "breaking"
            assert e["scheduled_at"] == "immediate"
            assert e["account"] == "flagship"

    def test_flagship_top_k_cap(self, tmp_path):
        # top_k=1 -> at most one emit even though multiple direct-quotes qualify.
        press_cfg = {"satire_blocklist": ["HalfwayPost"],
                     "wire": {"flagship_top_k_per_day": 1, "flagship_salience_floor": 40.0}}
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=press_cfg, state={}, seen_ids=set(),
                             dry_run=True)
        assert len(res["emitted"]) == 1
        assert any(s["reason"] == "flagship_top_k_reached" for s in res["skipped"])

    def test_emission_idempotency_via_seen(self, tmp_path):
        # Run once (live write), carry the returned _seen set (mirror-collapsed
        # emission keys, M1) into a second tick -> nothing re-emits. Feeding _seen
        # (what the daemon persists) is the real dedupe contract; raw out_item ids
        # would NOT dedupe a mirror pair.
        state1: dict = {}
        res1 = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                              cfg=_CFG, press_cfg=_PRESS_CFG, state=state1, seen_ids=set(),
                              dry_run=False)
        emitted_ids = {e["id"] for e in res1["emitted"]}
        assert emitted_ids
        seen_after = set(res1["_seen"])
        res2 = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                              cfg=_CFG, press_cfg=_PRESS_CFG, state={},
                              seen_ids=seen_after, dry_run=True)
        # Nothing that emitted the first time emits again.
        assert res2["emitted"] == []
        # The previously-emitted items come back as dedupe skips.
        assert any(s["reason"] == "dedupe" for s in res2["skipped"])

    def test_dry_run_writes_nothing(self, tmp_path):
        run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                       cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                       dry_run=True)
        outbox = tmp_path / "data" / "marketing" / "outbox"
        assert not outbox.exists() or not list(outbox.glob("*.json"))
        # XG-W2: the canonical queue must be untouched by a dry run too.
        assert not (outbox / "items.jsonl").exists()

    def test_live_write_lands_in_outbox_only(self, tmp_path):
        """XG-W2: emissions land in the CANONICAL queue (items.jsonl), which is
        what the publisher folds — not in per-item <id>.json files nothing read."""
        res = run_press_tick(_fixture_items(), root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=False)
        outbox = tmp_path / "data" / "marketing" / "outbox"
        items_file = outbox / "items.jsonl"
        assert items_file.exists()
        queued = {json.loads(line)["id"]: json.loads(line)
                  for line in items_file.read_text().splitlines() if line.strip()}
        for e in res["emitted"]:
            written = queued.get(e["id"])
            assert written is not None, f"{e['id']} not in items.jsonl"
            assert written["kind"] == "breaking"
            assert written["scheduled_at"] == "immediate"
            assert written["schema"] == "marketing.outbox/v1"
        # No hand-rolled per-item JSON remains.
        assert list(outbox.glob("*.json")) == []

    def test_corroboration_stale_entries_pruned(self, tmp_path):
        # A claim entry older than the window must be pruned, not grow forever.
        press_cfg = {"satire_blocklist": [],
                     "wire": {"flagship_salience_floor": 40.0, "corroboration_window_s": 60}}
        state = {"corroboration": {
            "truth:stale": {"sources": ["old"], "first_ts": "2020-01-01T00:00:00+00:00"},
        }}
        run_press_tick([], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                       press_cfg=press_cfg, state=state, seen_ids=set(), dry_run=True)
        assert "truth:stale" not in state["corroboration"]


# ---------------------------------------------------------------------------
# 7. Daemon kill-switch behaviour
# ---------------------------------------------------------------------------

class TestDaemon:
    def test_kill_switch_unset_press_noop_exit0(self, monkeypatch, capsys):
        monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)
        monkeypatch.delenv("MARKETING_PUBLISH_ENABLED", raising=False)
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        rc = d.main(["--lane", "press", "--once"])
        assert rc == 0
        assert "fast lane disabled" in capsys.readouterr().out

    def test_dry_run_bypasses_kill_switch(self, monkeypatch):
        # --dry-run must run the tick even with the kill-switch off; _run_press_tick
        # is stubbed so this stays network-free.
        monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        calls = {"n": 0}

        def _stub(*, dry_run):
            calls["n"] += 1
            return {"emitted": [], "skipped": [], "digest": [], "blocked": [],
                    "_emit_allowed": False}

        monkeypatch.setattr(d, "_run_press_tick", _stub)
        rc = d.main(["--lane", "press", "--once", "--dry-run"])
        assert rc == 0
        assert calls["n"] == 1

    def test_dry_run_does_not_persist_press_state(self, tmp_path, monkeypatch):
        # A dry-run must leave NO press state file (non-consuming) so it never
        # dedupes items away from a later live run.
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        monkeypatch.setattr(d, "ROOT", tmp_path)
        monkeypatch.setattr(d, "_PRESS_STATE_PATH", tmp_path / "data/marketing/press/state.json")
        monkeypatch.setattr(d, "_PRESS_SEEN_PATH", tmp_path / "data/marketing/press/seen.json")
        # Stub both pollers so no network happens.
        import engine.marketing.breaking_feed as bf
        import engine.marketing.press_providers as pp
        monkeypatch.setattr(bf, "poll_all", lambda root, cfg: [])
        monkeypatch.setattr(pp, "poll_all", lambda root, cfg, state: (
            state.setdefault("providers", {}).update({"touched": True}) or []))
        monkeypatch.setattr(d, "_load_yaml", lambda p: {})
        d._run_press_tick(dry_run=True)
        assert not (tmp_path / "data/marketing/press/state.json").exists()

    def test_earnings_lane_default_unchanged(self, monkeypatch):
        # Default lane is earnings; the press tick must NOT run for the default.
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        press_calls = {"n": 0}
        earn_calls = {"n": 0}
        monkeypatch.setattr(d, "_run_press_tick",
                            lambda *, dry_run: press_calls.__setitem__("n", press_calls["n"] + 1) or {})
        # `spool` joined the signature 2026-07-31 so the Actions lane can write the
        # git-TRACKED outbox instead of the host spool. A stub that omits it makes
        # every tick raise TypeError into the daemon's catch-and-continue, which
        # presents as ZERO POSTS rather than an error — the exact failure this test
        # then reports as "the earnings lane did not run".
        monkeypatch.setattr(d, "_run_one_tick",
                            lambda *, dry_run, armed=True, spool=True: earn_calls.__setitem__("n", earn_calls["n"] + 1) or
                            {"emitted": [], "skipped": [], "quarantined": []})
        d.main(["--once", "--dry-run"])
        assert earn_calls["n"] == 1
        assert press_calls["n"] == 0


# ---------------------------------------------------------------------------
# 9. Config register + gitignore guard
# ---------------------------------------------------------------------------

class TestConfigAndGitignore:
    def test_press_sources_yaml_shape(self):
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        assert "truth_mirrors" in cfg
        assert "x_follow" in cfg
        assert "satire_blocklist" in cfg and "HalfwayPost" in cfg["satire_blocklist"]
        assert cfg["spend"]["twitterapiio_monthly_cap_usd"] == 75.0
        # IS-W1: the Alpaca lane ships ARMED IN CONFIG for every host. That is only
        # safe because arming is really an ENV decision — a host without both keys
        # no-ops (TestAlpacaNews::test_no_keys_is_a_total_no_op pins it), so the
        # same committed file rides the VPS daemon and the Actions wire.
        assert cfg["alpaca"]["enabled"] is True
        assert cfg["alpaca"]["rest_url"] == "https://data.alpaca.markets/v1beta1/news"
        assert cfg["alpaca"]["key_env"] == "ALPACA_API_KEY_ID"
        assert cfg["alpaca"]["secret_env"] == "ALPACA_API_SECRET_KEY"
        # Politeness floor and page cap are the two numbers that keep one page per
        # poll honest; the endpoint's own maximum limit is 50.
        assert cfg["alpaca"]["min_interval_s"] >= 60
        assert 1 <= cfg["alpaca"]["limit"] <= 50
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        bls = next(
            s for s in marketing_cfg["breaking"]["sources"]
            if s["key"] == "bls_news"
        )
        assert bls["url"] == "https://www.bls.gov/feed/bls_latest.rss"
        # x_follow register: the exact v1 handle set + tiers.
        handles = {h["handle"]: h["tier"] for h in cfg["x_follow"]["handles"]}
        for h in ("DeItaone", "FirstSquawk", "financialjuice", "zerohedge", "WHPressPool"):
            assert handles[h] == "fast"
        for h in ("NewsWire_US", "unusual_whales", "WatcherGuru"):
            assert handles[h] == "mid"
        for h in ("HormuzLetter", "CoinDesk", "Cointelegraph"):
            assert handles[h] == "slow"
        assert cfg["x_follow"]["key_env"] == "TWITTERAPI_IO_KEY"

    def test_build_providers_from_config(self):
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        provs = build_providers(cfg)
        names = {type(p).__name__ for p in provs}
        assert "TrumpstruthProvider" in names
        assert "CnnTruthBackfillProvider" in names
        assert "TwitterApiIoProvider" in names
        assert "AlpacaNewsProvider" in names

    def test_build_providers_omits_alpaca_when_disabled(self):
        """`enabled: false` must not even construct the lane."""
        provs = build_providers({"alpaca": {"enabled": False,
                                            "key_env": "ALPACA_API_KEY_ID"}})
        assert [type(p).__name__ for p in provs] == []

    def test_press_dir_in_gitignore(self):
        content = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "data/marketing/press/" in content

    def test_systemd_unit_ships_dark(self):
        unit = (ROOT / "app" / "deploy" / "marketing-press-feeds.service").read_text()
        assert "--lane press" in unit
        # ships disabled — no [Install] auto-enable trickery; arming is manual.
        assert "MARKETING_FASTLANE_ENABLED" in unit  # documented in the unit comments


# ===========================================================================
# Adversarial-review fixes (PR #3838). One regression test per finding, each
# pinned to reproduce the exact defect the reviewer found.
# ===========================================================================

_TARIFF_TSID = "116993810062084166"  # the 50%-steel-tariff post, in BOTH mirrors


def _tariff_from_both_mirrors():
    """The SAME Truth post as seen via trumpstruth AND the CNN archive.

    Two distinct FeedItem ids (each embeds its mirror source key), one shared
    truth_status_id — the exact cross-mirror double-emit shape (M1).
    """
    ts = TrumpstruthProvider(_TS_CFG).parse(_load("trumpstruth_feed.xml"))
    cnn = CnnTruthBackfillProvider(_CNN_CFG).parse(_load("cnn_truth_archive.json"))
    a = next(i for i in ts if i["truth_status_id"] == _TARIFF_TSID)
    b = next(i for i in cnn if i["truth_status_id"] == _TARIFF_TSID)
    assert a["id"] != b["id"], "mirror ids must differ (source key embedded)"
    assert a["truth_status_id"] == b["truth_status_id"] == _TARIFF_TSID
    return a, b


class TestM1CrossMirrorDedupe:
    """M1: the same Truth post via two mirrors must emit exactly once."""

    def test_two_mirror_items_emit_once(self, tmp_path):
        a, b = _tariff_from_both_mirrors()
        res = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS,
                             cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             dry_run=True)
        tariff_emits = [e for e in res["emitted"]
                        if "tariff" in e["headline"].lower()]
        assert len(tariff_emits) == 1, "cross-mirror double-emit (M1) not fixed"
        # the second mirror is a dedupe skip, not a second emission
        assert any(s["reason"] == "dedupe" for s in res["skipped"])

    def test_second_tick_emits_zero(self, tmp_path):
        a, b = _tariff_from_both_mirrors()
        res1 = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS,
                              cfg=_CFG, press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                              dry_run=False)
        assert len([e for e in res1["emitted"]
                    if "tariff" in e["headline"].lower()]) == 1
        # carry the returned collapsed seen-set into a re-poll of BOTH mirrors
        res2 = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS,
                              cfg=_CFG, press_cfg=_PRESS_CFG, state={},
                              seen_ids=set(res1["_seen"]), dry_run=True)
        assert res2["emitted"] == [], "collapsed key did not persist across ticks (M1)"

    def test_seen_records_collapsed_key(self, tmp_path):
        a, _ = _tariff_from_both_mirrors()
        res = run_press_tick([a], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_PRESS_CFG, state={}, seen_ids=set(), dry_run=True)
        assert f"truth:{_TARIFF_TSID}" in set(res["_seen"])
        # the raw mirror id is NOT what dedupe keys on
        assert a["id"] not in set(res["_seen"])


def _hearsay(handle, headline, iid=None):
    return {
        "id": iid or f"tw:{handle}:{abs(hash(headline)) % 10**12}",
        "source": f"x_{handle}", "x_handle": handle, "source_name": f"@{handle}",
        "source_tier": "x_relay", "url": "", "published_at": "2026-07-27T20:00:00Z",
        "headline": headline, "body_snippet": headline,
        "corroboration_class": "hearsay",
    }


# floor 40 so the tariff hearsay (salience 45) clears it once corroborated
_M3_CFG = {"satire_blocklist": [],
           "wire": {"flagship_top_k_per_day": 5, "flagship_salience_floor": 40.0,
                    "corroboration_window_s": 1800}}


class TestM3EntityCorroboration:
    """M3: hearsay corroborates on entity+event_class, not verbatim headline."""

    def test_differently_worded_two_handles_corroborate_instant(self, tmp_path):
        # DeItaone vs FirstSquawk — same tariff claim, different wording.
        a = _hearsay("DeItaone", "Trump told reporters new China tariffs coming")
        b = _hearsay("FirstSquawk", "BREAKING: China tariffs to rise, Trump says")
        res = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_M3_CFG, state={}, seen_ids=set(), dry_run=True)
        gates = {e["source"]["corroboration_gate"] for e in res["emitted"]}
        assert res["emitted"], "≥2-source instant path is still dead (M3)"
        assert "instant" in gates
        # neither differently-worded claim fell to digest
        assert not any("tariff" in d.get("headline", "").lower() for d in res["digest"])

    def test_same_handle_twice_not_corroborated(self, tmp_path):
        # Same source repeating itself is ONE independent source -> digest.
        a = _hearsay("DeItaone", "Trump told reporters new China tariffs coming", iid="dup1")
        b = _hearsay("DeItaone", "China tariffs are coming, Trump says", iid="dup2")
        res = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_M3_CFG, state={}, seen_ids=set(), dry_run=True)
        # single political hearsay source -> digest, never an instant emit
        assert not any(e["source"]["corroboration_gate"] == "instant"
                       for e in res["emitted"])
        assert res["digest"], "same-handle-twice must NOT corroborate to instant (M3)"

    def test_different_event_class_not_corroborated(self, tmp_path):
        # A tariff (policy) and an earnings (company_news) claim never share a key.
        a = _hearsay("DeItaone", "Trump told reporters new China tariffs coming")
        b = _hearsay("FirstSquawk", "Apple earnings beat, guidance raised")
        res = run_press_tick([a, b], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_M3_CFG, state={}, seen_ids=set(), dry_run=True)
        # the tariff claim has only ONE source of its class -> not instant -> digest
        assert not any(e["source"]["corroboration_gate"] == "instant"
                       and e["source"]["event_class"] == "policy"
                       for e in res["emitted"])
        assert any(d.get("salience") is not None for d in res["digest"])


class TestM2DryRunNoBilledReads:
    """M2: dry-run must make ZERO twitterapi.io requests and not touch spend."""

    def _provider(self):
        from engine.marketing.press_providers import TwitterApiIoProvider
        cfg = {"handles": [{"handle": "DeItaone", "tier": "fast",
                            "corroboration_class": "hearsay"}],
               "poll_tiers": {"fast": 1, "mid": 1, "slow": 1}}
        return TwitterApiIoProvider(cfg, spend_cap_usd=75.0)

    def test_offline_fetch_makes_zero_requests(self, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        prov = self._provider()
        calls = {"n": 0}
        monkeypatch.setattr(prov, "_request",
                            lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or {})
        state: dict = {}
        out = prov.fetch(root=ROOT, session_state=state, offline=True)
        assert out == []
        assert calls["n"] == 0, "billed twitterapi.io request made in offline mode (M2)"
        # spend state never even created
        assert state == {} or not state.get("twitterapiio", {}).get("spend")

    def test_poll_all_offline_skips_billed_but_runs_free(self, monkeypatch):
        import engine.marketing.press_providers as pp
        # A billed provider that records requests + a free provider that fetches.
        billed_calls = {"n": 0}
        free_calls = {"n": 0}

        class _Billed:
            billed = True
            def fetch(self, *, root, session_state, offline=False, now=None):
                if offline:
                    return []
                billed_calls["n"] += 1
                return [{"id": "billed"}]

        class _Free:
            def fetch(self, *, root, session_state, offline=False, now=None):
                free_calls["n"] += 1
                return [{"id": "free"}]

        monkeypatch.setattr(pp, "build_providers", lambda cfg: [_Billed(), _Free()])
        items = pp.poll_all(ROOT, {}, {}, offline=True)
        assert billed_calls["n"] == 0
        assert free_calls["n"] == 1
        assert [i["id"] for i in items] == ["free"]

    def test_daemon_dry_run_leaves_spend_unchanged(self, tmp_path, monkeypatch):
        # A full dry-run press tick with a key set must not bill or persist spend.
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        monkeypatch.setattr(d, "ROOT", tmp_path)
        monkeypatch.setattr(d, "_PRESS_STATE_PATH", tmp_path / "data/marketing/press/state.json")
        monkeypatch.setattr(d, "_PRESS_SEEN_PATH", tmp_path / "data/marketing/press/seen.json")
        import engine.marketing.breaking_feed as bf
        import engine.marketing.press_providers as pp
        monkeypatch.setattr(bf, "poll_all", lambda root, cfg: [])
        # Record whether poll_all is asked to go offline, and whether the billed
        # provider would be reached. offline=True must be threaded through.
        seen_offline = {"val": None}
        real_poll = pp.poll_all
        def _spy(root, cfg, state, *, offline=False, now=None):
            seen_offline["val"] = offline
            return []
        monkeypatch.setattr(pp, "poll_all", _spy)
        monkeypatch.setattr(d, "_load_yaml", lambda p: {})
        d._run_press_tick(dry_run=True)
        assert seen_offline["val"] is True, "dry-run did not thread offline=True (M2)"
        assert not (tmp_path / "data/marketing/press/state.json").exists()


class Testm1EarningsDisarmedOffline:
    """m1: disarmed + --dry-run must NOT reach earnings_feed.fetch_events."""

    def test_disarmed_dry_run_skips_earnings_fetch(self, monkeypatch):
        monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        import engine.marketing.earnings_feed as ef
        fetch_calls = {"n": 0}
        monkeypatch.setattr(ef, "fetch_events",
                            lambda since: fetch_calls.__setitem__("n", fetch_calls["n"] + 1) or [])
        # run_tick is stubbed so the (empty) tick stays offline + writes nothing
        import engine.marketing.fastlane as fl
        monkeypatch.setattr(fl, "run_tick",
                            lambda events, **k: {"emitted": [], "skipped": [], "quarantined": []})
        rc = d.main(["--lane", "earnings", "--once", "--dry-run"])
        assert rc == 0
        assert fetch_calls["n"] == 0, "disarmed dry-run reached earnings network fetch (m1)"

    def test_armed_dry_run_still_fetches(self, monkeypatch):
        # Sanity: with the switch ON, the earnings fetch DOES run (no regression).
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        import importlib
        import scripts.marketing_fastlane_daemon as d
        importlib.reload(d)
        import engine.marketing.earnings_feed as ef
        fetch_calls = {"n": 0}
        monkeypatch.setattr(ef, "fetch_events",
                            lambda since: fetch_calls.__setitem__("n", fetch_calls["n"] + 1) or [])
        import engine.marketing.fastlane as fl
        monkeypatch.setattr(fl, "run_tick",
                            lambda events, **k: {"emitted": [], "skipped": [], "quarantined": []})
        d.main(["--lane", "earnings", "--once", "--dry-run"])
        assert fetch_calls["n"] == 1


class Testm2ColdStartPrime:
    """m2: first run primes (0 emitted); a later new item emits normally."""

    def test_prime_emits_zero_and_seeds_seen(self, tmp_path, capsys):
        a, _ = _tariff_from_both_mirrors()
        res = run_press_tick([a], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                             prime=True, dry_run=True)
        assert res["emitted"] == [], "prime must emit nothing (m2)"
        # the item is recorded as seen so the next tick dedupes the history
        assert f"truth:{_TARIFF_TSID}" in set(res["_seen"])
        assert "[press] primed" in capsys.readouterr().out

    def test_second_tick_emits_new_item(self, tmp_path):
        # Prime tick 1, then a NEW item on tick 2 emits (primed history stays quiet).
        a, _ = _tariff_from_both_mirrors()
        res1 = run_press_tick([a], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                              press_cfg=_PRESS_CFG, state={}, seen_ids=set(),
                              prime=True, dry_run=True)
        seen = set(res1["_seen"])
        ts = TrumpstruthProvider(_TS_CFG).parse(_load("trumpstruth_feed.xml"))
        fed = next(i for i in ts if "fed" in i["headline"].lower()
                   or "interest rate" in i["headline"].lower())
        res2 = run_press_tick([a, fed], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                              press_cfg=_PRESS_CFG, state={}, seen_ids=seen, dry_run=True)
        emitted_tsids = {e["source"].get("via_source") is not None for e in res2["emitted"]}
        assert res2["emitted"], "a genuinely new item after prime must emit (m2)"
        # the primed tariff post does NOT re-emit
        assert not any("tariff" in e["headline"].lower() for e in res2["emitted"])


class TestAlpacaNews:
    """IS-W1 / Intelligence Desk V2 §C — the Alpaca (Benzinga) news REST poller.

    ZERO network: ``press_providers.urlopen`` is replaced wholesale, so the REAL
    ``_request`` runs (URL, query params and auth headers are asserted on the
    Request object it built) while nothing leaves the process. A test that reaches
    the network fails loudly instead of quietly costing a rate-limit budget.
    """

    # ---- fixtures ---------------------------------------------------------

    #: A recorded-SHAPE /v1beta1/news response (docs.alpaca.markets, 2026-07-29).
    #: Deliberately includes the three rows the mapper must handle specially:
    #: markup in `summary`, a headline-less row, and a re-served duplicate id.
    PAGE: dict = {
        "news": [
            {
                "id": 48213377,
                "headline": "Fed Holds Rates Steady, Signals One Cut By Year-End",
                "author": "Benzinga Newsdesk",
                "created_at": "2026-07-29T18:02:11Z",
                "updated_at": "2026-07-29T18:04:03Z",
                "summary": "<p>The Federal Reserve left the target range unchanged "
                           "at <b>4.25%&ndash;4.50%</b> and penciled in one cut.</p>",
                "content": "<p>Longer body that should NOT win over summary.</p>",
                "url": "https://www.benzinga.com/news/26/07/48213377/fed-holds-rates",
                "images": [{"size": "large",
                            "url": "https://cdn.benzinga.com/files/fed.jpeg"}],
                "symbols": ["SPY", "TLT"],
                "source": "benzinga",
            },
            {
                "id": 48213301,
                "headline": "Apple Beats On Q3 Revenue, Raises Full-Year Guidance",
                "author": "Benzinga Staff",
                "created_at": "2026-07-29T17:31:00Z",
                "updated_at": "2026-07-29T17:31:00Z",
                "summary": "",
                "content": "<div>Apple reported revenue above consensus.</div>",
                "url": "https://www.benzinga.com/news/26/07/48213301/apple-q3",
                "images": [],
                "symbols": ["AAPL"],
                "source": "benzinga",
            },
            {
                # Headline-less row: an id and a body but nothing to publish.
                "id": 48213208,
                "headline": "   ",
                "author": "",
                "created_at": "2026-07-29T17:05:00Z",
                "updated_at": "2026-07-29T17:05:00Z",
                "summary": "Contentless placeholder.",
                "url": "https://www.benzinga.com/news/26/07/48213208/",
                "symbols": [],
                "source": "benzinga",
            },
            {
                # The SAME article re-served inside one page (corrections do this).
                "id": 48213301,
                "headline": "Apple Beats On Q3 Revenue, Raises Full-Year Guidance",
                "author": "Benzinga Staff",
                "created_at": "2026-07-29T17:31:00Z",
                "updated_at": "2026-07-29T17:44:02Z",
                "summary": "Corrected copy.",
                "url": "https://www.benzinga.com/news/26/07/48213301/apple-q3",
                "symbols": ["AAPL"],
                "source": "benzinga",
            },
        ],
        "next_page_token": "MjAyNi0wNy0yOVQxNzowNTowMFo6NDgyMTMyMDg=",
    }

    NEWEST_ISO = "2026-07-29T18:02:11+00:00"   # the Fed row's created_at, UTC
    APPLE_ISO = "2026-07-29T17:31:00+00:00"
    NOW = datetime(2026, 7, 29, 18, 5, 0, tzinfo=timezone.utc)

    CFG: dict = {
        "enabled": True,
        "rest_url": "https://data.alpaca.markets/v1beta1/news",
        "key_env": "ALPACA_API_KEY_ID",
        "secret_env": "ALPACA_API_SECRET_KEY",
        "min_interval_s": 60,
        "limit": 50,
        "snippet_max_chars": 400,
    }

    @pytest.fixture(autouse=True)
    def _clean_process_state(self, monkeypatch):
        """The preflight notice is once-per-PROCESS; tests share the process."""
        import engine.marketing.press_providers as pp
        pp._PREFLIGHT_NOTICED.clear()
        yield
        pp._PREFLIGHT_NOTICED.clear()

    def _keys(self, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key-id")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")

    def _http(self, monkeypatch, *, payload=None, error=None):
        """Replace press_providers.urlopen; return the call recorder."""
        import engine.marketing.press_providers as pp

        class _Resp:
            def __init__(self, body: bytes):
                self._body = body

            def read(self, n: int = -1) -> bytes:
                return self._body if n is None or n < 0 else self._body[:n]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _Recorder:
            def __init__(self):
                self.requests: list = []

            def __call__(self, req, timeout=None):
                self.requests.append(req)
                if error is not None:
                    raise error
                return _Resp(json.dumps(payload if payload is not None else {}
                                        ).encode("utf-8"))

        rec = _Recorder()
        monkeypatch.setattr(pp, "urlopen", rec)
        return rec

    def _provider(self, **overrides):
        return AlpacaNewsProvider({**self.CFG, **overrides})

    # ---- (a) mapping ------------------------------------------------------

    def test_mapping_shape_and_identity(self):
        items, newest = self._provider().parse(self.PAGE)
        # headline-less row dropped, duplicate id collapsed -> 2 of 4
        assert [i["id"] for i in items] == ["alpaca:48213377", "alpaca:48213301"]
        assert newest == self.NEWEST_ISO
        for it in items:
            assert not (_REQUIRED_KEYS - set(it.keys()))
            assert it["source"] == "alpaca_benzinga"
            assert it["source_tier"] == "wire"
            assert it["corroboration_class"] == "wire"
            # source_name comes from the ARTICLE's own source field, prettified
            assert it["source_name"] == "Benzinga"
            assert datetime.fromisoformat(it["published_at"]).tzinfo is not None

    def test_snippet_is_html_stripped_and_capped(self):
        prov = self._provider(snippet_max_chars=40)
        items, _ = prov.parse(self.PAGE)
        fed = items[0]
        snippet = fed["body_snippet"]
        assert "<" not in snippet and ">" not in snippet, snippet
        assert "&ndash;" not in snippet, "HTML entities must be unescaped, not shipped"
        assert snippet.startswith("The Federal Reserve left the target")
        assert len(snippet) <= 40
        # summary wins over content when both are present
        assert "Longer body" not in snippet
        # …and content is the fallback when summary is empty
        assert items[1]["body_snippet"] == "Apple reported revenue above consensus."

    def test_symbols_pass_through_only_when_present(self):
        items, _ = self._provider().parse(self.PAGE)
        assert items[0]["symbols"] == ["SPY", "TLT"]
        assert items[1]["symbols"] == ["AAPL"]
        # A symbol-less article carries no key at all rather than a lying []
        empty, _ = self._provider().parse(
            {"news": [{"id": 1, "headline": "No tickers here",
                       "created_at": "2026-07-29T18:00:00Z", "source": "benzinga"}]})
        assert "symbols" not in empty[0]

    def test_url_and_author_pass_through(self):
        items, _ = self._provider().parse(self.PAGE)
        assert items[0]["url"] == (
            "https://www.benzinga.com/news/26/07/48213377/fed-holds-rates")
        assert items[0]["author"] == "Benzinga Newsdesk"

    def test_a_timestampless_row_is_dropped_and_noticed(self, capsys):
        """Review N3: a row with no parseable timestamp is DROPPED, not ingested.

        It cannot be ordered against the cursor: ingesting it with an ingest-time
        stamp either stalls the cursor forever (an all-stampless page re-serves
        every poll) or — if that stamp ever drove the cursor — fast-forwards
        `since` to "now" past items still in flight. The drop is counted and
        noticed so a field rename costs visible noise, never silent loss.
        """
        page = {"news": [
            {"id": 1, "headline": "Dateless row", "source": "benzinga"},
            {"id": 2, "headline": "Dated row", "created_at": "2026-07-29T16:00:00Z",
             "source": "benzinga"},
        ]}
        items, newest = self._provider().parse(page)
        assert [i["id"] for i in items] == ["alpaca:2"]
        assert newest == "2026-07-29T16:00:00+00:00"
        out = capsys.readouterr().out
        line = next(l for l in out.splitlines() if "alpaca-timestampless" in l)
        assert line.startswith("::notice") and "1 " in line

    def test_an_all_timestampless_page_ingests_nothing_and_advances_nothing(
            self, capsys):
        """The stall case the drop rule exists for: nothing to order, nothing
        ingested, cursor untouched — instead of the same rows re-serving on
        every poll forever."""
        page = {"news": [
            {"id": 1, "headline": "Dateless one", "source": "benzinga"},
            {"id": 2, "headline": "Dateless two", "source": "benzinga"},
        ]}
        items, newest = self._provider().parse(page, since="2026-07-29T15:00:00Z")
        assert items == [] and newest is None
        assert "alpaca-timestampless" in capsys.readouterr().out

    def test_malformed_payload_never_raises(self):
        prov = self._provider()
        assert prov.parse("{not json") == ([], None)
        assert prov.parse({"news": "not-a-list"}) == ([], None)
        assert prov.parse({}) == ([], None)

    # ---- (b) first-run cursor prime --------------------------------------

    def test_first_run_primes_cursor_and_ingests_nothing(self, monkeypatch, capsys):
        """A history page is not live news: prime the cursor, emit zero.

        The GLOBAL press cold-start only covers a brand-new deployment. A provider
        added mid-life meets a warm seen-ledger, so without this its first page of
        50 back-dated articles would look like 50 simultaneous breaks.
        """
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state: dict = {}
        out = self._provider().fetch(root=ROOT, session_state=state, now=self.NOW)

        assert out == [], "first poll must ingest NOTHING (§C cold start)"
        assert len(http.requests) == 1
        st = state["alpaca"]
        assert st["since"] == self.NEWEST_ISO, "cursor did not advance on the prime"
        assert st["last_poll"] == self.NOW.isoformat()
        assert st["primed_at"] == self.NOW.isoformat()
        notice = [ln for ln in capsys.readouterr().out.splitlines()
                  if "alpaca-cold-start" in ln]
        assert notice and notice[0].startswith("::notice title=alpaca-cold-start::")

    def test_first_run_with_no_cursor_sends_no_start_param(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        self._provider().fetch(root=ROOT, session_state={}, now=self.NOW)
        url = http.requests[0].full_url
        assert "start=" not in url
        assert "limit=50" in url and "sort=desc" in url, url
        assert url.startswith("https://data.alpaca.markets/v1beta1/news?")

    def test_auth_headers_are_the_documented_pair(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        self._provider().fetch(root=ROOT, session_state={}, now=self.NOW)
        req = http.requests[0]
        # urllib capitalises header names on add_header().
        assert req.get_header("Apca-api-key-id") == "test-key-id"
        assert req.get_header("Apca-api-secret-key") == "test-secret"

    def test_empty_first_page_still_primes(self, monkeypatch):
        """An empty prime must not re-arm itself against the first real batch."""
        self._keys(monkeypatch)
        self._http(monkeypatch, payload={"news": []})
        state: dict = {}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        assert state["alpaca"]["since"] == self.NOW.isoformat()

    # ---- (c) second poll ingests only newer -------------------------------

    def test_second_poll_ingests_only_newer_and_advances(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        # Cursor already at the Apple story; last_poll well past the floor.
        state = {"alpaca": {"since": self.APPLE_ISO,
                            "last_poll": (self.NOW - timedelta(minutes=10)).isoformat()}}
        out = self._provider().fetch(root=ROOT, session_state=state, now=self.NOW)

        assert [i["id"] for i in out] == ["alpaca:48213377"], (
            "an item at-or-before the cursor was re-ingested")
        assert state["alpaca"]["since"] == self.NEWEST_ISO
        # The cursor rides the wire as `start` so the page is small — and the
        # cursored poll asks OLDEST-first (review N2) so a wide backlog drains
        # contiguously instead of the cursor leaping over it.
        assert f"start={quote(self.APPLE_ISO, safe='')}" in http.requests[0].full_url
        assert "sort=asc" in http.requests[0].full_url

    def test_third_poll_with_nothing_new_holds_the_cursor(self, monkeypatch):
        self._keys(monkeypatch)
        self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {"since": self.NEWEST_ISO,
                            "last_poll": (self.NOW - timedelta(minutes=10)).isoformat()}}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        assert state["alpaca"]["since"] == self.NEWEST_ISO

    def test_re_served_page_never_double_emits_across_polls(self, monkeypatch):
        """The end-to-end dedupe contract: poll the SAME page three times."""
        self._keys(monkeypatch)
        self._http(monkeypatch, payload=self.PAGE)
        state: dict = {}
        prov = self._provider()
        clock = self.NOW
        seen: list[str] = []
        for _ in range(3):
            for item in prov.fetch(root=ROOT, session_state=state, now=clock):
                seen.append(item["id"])
            clock += timedelta(minutes=5)
        assert seen == [], "a re-served history page must never ingest twice"
        assert state["alpaca"]["since"] == self.NEWEST_ISO

    def test_a_wide_backlog_drains_contiguously_over_asc_polls(self, monkeypatch,
                                                               capsys):
        """Review N2: 120 backlogged items catch up over 3 cursored polls with
        no gap. Before the asc cursor, `sort=desc` + limit meant the cursor
        leapt to the newest of page one and the other 70 items were never
        requested again."""
        import engine.marketing.press_providers as pp

        base = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        rows = [{"id": n, "headline": f"Backlog item {n}", "source": "benzinga",
                 "created_at": (base + timedelta(minutes=n)).isoformat()}
                for n in range(1, 121)]

        class _Resp:
            def __init__(self, body: bytes):
                self._body = body

            def read(self, n: int = -1) -> bytes:
                return self._body if n is None or n < 0 else self._body[:n]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _AscServer:
            """Serve the oldest 50 rows strictly after the `start` param —
            exactly what the real endpoint does for sort=asc."""
            def __init__(self):
                self.requests: list = []

            def __call__(self, req, timeout=None):
                self.requests.append(req)
                from urllib.parse import parse_qs, urlsplit
                q = parse_qs(urlsplit(req.full_url).query)
                start = _iso(q.get("start", [""])[0])
                page = [r for r in rows if _iso(r["created_at"]) > start][:50]
                return _Resp(json.dumps({"news": page}).encode("utf-8"))

        def _iso(v):
            from engine.marketing.press_providers import _iso_to_dt
            return _iso_to_dt(v) or base - timedelta(days=1)

        self._keys(monkeypatch)
        server = _AscServer()
        monkeypatch.setattr(pp, "urlopen", server)
        prov = self._provider()
        state = {"alpaca": {"since": base.isoformat(),
                            "last_poll": (self.NOW - timedelta(minutes=10)).isoformat()}}
        got: list[str] = []
        clock = self.NOW
        for _ in range(3):
            for item in prov.fetch(root=ROOT, session_state=state, now=clock):
                got.append(item["id"])
            clock += timedelta(minutes=5)

        assert got == [f"alpaca:{n}" for n in range(1, 121)], (
            "the backlog did not drain contiguously")
        assert all("sort=asc" in r.full_url for r in server.requests)
        # Full pages 1 and 2 announce catch-up at notice level, never a warning.
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "alpaca-page-catchup" in l]
        assert len(lines) == 2 and all(l.startswith("::notice") for l in lines)

    # ---- (d) no keys = total no-op ----------------------------------------

    def test_no_keys_is_a_total_no_op(self, monkeypatch, capsys):
        """`enabled: true` with keys absent must cost NOTHING — env arms the lane."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        http = self._http(monkeypatch, payload=self.PAGE)
        state: dict = {}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        assert http.requests == [], "keyless lane reached the network"
        assert state == {}, "keyless lane wrote provider state"
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "alpaca-preflight" in ln]
        assert lines, "expected one preflight notice"
        # Repo law: a GH annotation must START its line (never through a logger).
        assert lines[0].startswith("::notice title=alpaca-preflight::"), lines[0]
        assert "ALPACA_API_KEY_ID" in lines[0] and "ALPACA_API_SECRET_KEY" in lines[0]

    def test_half_a_credential_is_still_a_no_op(self, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key-id")
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        http = self._http(monkeypatch, payload=self.PAGE)
        assert self._provider().fetch(
            root=ROOT, session_state={}, now=self.NOW) == []
        assert http.requests == []

    def test_preflight_notice_fires_once_per_process(self, monkeypatch, capsys):
        """A 75 s tick loop must not emit this notice 1,152 times a day."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        self._http(monkeypatch, payload=self.PAGE)
        prov = self._provider()
        for i in range(4):
            prov.fetch(root=ROOT, session_state={},
                       now=self.NOW + timedelta(minutes=i))
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "alpaca-preflight" in ln]
        assert len(lines) == 1, f"notice repeated {len(lines)}x per process"

    # ---- (e) offline / dry-run -------------------------------------------

    def test_offline_makes_no_request_and_no_state_write(self, monkeypatch):
        """Dry-run is NON-CONSUMING: advancing a cursor whose state is discarded
        would hide those items from the next live run."""
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state: dict = {}
        assert self._provider().fetch(
            root=ROOT, session_state=state, offline=True, now=self.NOW) == []
        assert http.requests == []
        assert state == {}

    def test_poll_all_threads_offline_to_the_alpaca_lane(self, monkeypatch):
        """The daemon/wire both reach this lane through poll_all, not fetch()."""
        import engine.marketing.press_providers as pp
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state: dict = {}
        items = pp.poll_all(ROOT, {"alpaca": self.CFG}, state,
                            offline=True, now=self.NOW)
        assert items == [] and http.requests == [] and state == {}

    def test_poll_all_builds_and_runs_the_lane_when_armed(self, monkeypatch):
        import engine.marketing.press_providers as pp
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {"since": self.APPLE_ISO}}
        items = pp.poll_all(ROOT, {"alpaca": self.CFG}, state,
                            offline=False, now=self.NOW)
        assert len(http.requests) == 1
        assert [i["id"] for i in items] == ["alpaca:48213377"]

    # ---- (f) politeness floor --------------------------------------------

    def test_min_interval_skips_without_touching_the_network(self, monkeypatch):
        """The floor is measured against a PERSISTED last_poll, so it holds even
        if the daemon's ~75 s tick shrinks."""
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {"since": self.APPLE_ISO,
                            "last_poll": (self.NOW - timedelta(seconds=30)).isoformat()}}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        assert http.requests == [], "polled 30 s into a 60 s floor"
        assert state["alpaca"]["last_poll"] == (
            self.NOW - timedelta(seconds=30)).isoformat(), "skipped poll re-stamped"

    def test_min_interval_elapsed_polls_again(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {"since": self.APPLE_ISO,
                            "last_poll": (self.NOW - timedelta(seconds=61)).isoformat()}}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) != []
        assert len(http.requests) == 1

    def test_two_ticks_inside_the_floor_make_one_request(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        prov = self._provider()
        state: dict = {}
        prov.fetch(root=ROOT, session_state=state, now=self.NOW)               # prime
        prov.fetch(root=ROOT, session_state=state,
                   now=self.NOW + timedelta(seconds=75 // 2))                  # too soon
        assert len(http.requests) == 1

    # ---- (g) failure honesty ---------------------------------------------

    def _http_error(self, code: str | int):
        from urllib.error import HTTPError
        return HTTPError("https://data.alpaca.markets/v1beta1/news",
                         int(code), "boom", {}, None)   # type: ignore[arg-type]

    def test_rate_limit_backs_off_by_doubling_and_caps(self, monkeypatch, capsys):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, error=self._http_error(429))
        prov = self._provider()
        state: dict = {"alpaca": {"since": self.APPLE_ISO}}
        clock = self.NOW

        steps: list[float] = []
        for _ in range(6):
            # Step the clock past both the floor and the standing backoff so each
            # iteration genuinely re-polls and doubles.
            out = prov.fetch(root=ROOT, session_state=state, now=clock)
            assert out == []
            steps.append(float(state["alpaca"]["backoff_s"]))
            clock = (datetime.fromisoformat(state["alpaca"]["backoff_until"])
                     + timedelta(seconds=1))

        assert steps == [60.0, 120.0, 240.0, 480.0, 900.0, 900.0], steps
        assert len(http.requests) == 6
        warns = [ln for ln in capsys.readouterr().out.splitlines()
                 if "alpaca-rate-limit" in ln]
        assert len(warns) == 6
        assert warns[0].startswith("::warning title=alpaca-rate-limit::"), warns[0]

    def test_backoff_window_is_honoured_before_any_request(self, monkeypatch):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {
            "since": self.APPLE_ISO,
            "backoff_s": 240.0,
            "backoff_until": (self.NOW + timedelta(minutes=3)).isoformat(),
        }}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        assert http.requests == [], "polled inside the 429 backoff window"

    def test_a_good_poll_clears_the_backoff_ladder(self, monkeypatch):
        self._keys(monkeypatch)
        self._http(monkeypatch, payload=self.PAGE)
        state = {"alpaca": {
            "since": self.APPLE_ISO,
            "backoff_s": 480.0,
            "backoff_until": (self.NOW - timedelta(seconds=1)).isoformat(),
        }}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) != []
        assert "backoff_s" not in state["alpaca"]
        assert "backoff_until" not in state["alpaca"]

    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_failure_warns_by_name_and_skips(self, monkeypatch, capsys, code):
        self._keys(monkeypatch)
        self._http(monkeypatch, error=self._http_error(code))
        state = {"alpaca": {"since": self.APPLE_ISO}}
        assert self._provider().fetch(
            root=ROOT, session_state=state, now=self.NOW) == []
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "alpaca-auth" in ln)
        assert line.startswith("::warning title=alpaca-auth::"), line
        assert str(code) in line
        assert "ALPACA_API_KEY_ID" in line and "ALPACA_API_SECRET_KEY" in line
        # An auth failure is not a rate limit — no backoff ladder is armed.
        assert "backoff_until" not in state["alpaca"]

    def test_server_error_warns_and_returns_empty(self, monkeypatch, capsys):
        self._keys(monkeypatch)
        self._http(monkeypatch, error=self._http_error(503))
        assert self._provider().fetch(
            root=ROOT, session_state={"alpaca": {"since": self.APPLE_ISO}},
            now=self.NOW) == []
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "alpaca-http" in ln)
        assert line.startswith("::warning title=alpaca-http::"), line

    def test_network_error_warns_and_returns_empty(self, monkeypatch, capsys):
        from urllib.error import URLError
        self._keys(monkeypatch)
        self._http(monkeypatch, error=URLError("dns is down"))
        assert self._provider().fetch(
            root=ROOT, session_state={"alpaca": {"since": self.APPLE_ISO}},
            now=self.NOW) == []
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "alpaca-fetch" in ln)
        assert line.startswith("::warning title=alpaca-fetch::"), line

    def test_one_dead_provider_never_kills_the_tick(self, monkeypatch):
        """poll_all must still return the other lanes' items when Alpaca 500s."""
        import engine.marketing.press_providers as pp
        self._keys(monkeypatch)
        self._http(monkeypatch, error=self._http_error(500))

        class _Free:
            def fetch(self, *, root, session_state, offline=False, now=None):
                return [{"id": "free"}]

        real_build = pp.build_providers
        monkeypatch.setattr(
            pp, "build_providers",
            lambda cfg: [*real_build(cfg), _Free()])
        items = pp.poll_all(ROOT, {"alpaca": self.CFG},
                            {"alpaca": {"since": self.APPLE_ISO}}, now=self.NOW)
        assert [i["id"] for i in items] == ["free"]

    def test_non_https_url_is_refused_before_any_request(self, monkeypatch, capsys):
        self._keys(monkeypatch)
        http = self._http(monkeypatch, payload=self.PAGE)
        prov = self._provider(rest_url="http://data.alpaca.markets/v1beta1/news")
        assert prov.fetch(root=ROOT,
                          session_state={"alpaca": {"since": self.APPLE_ISO}},
                          now=self.NOW) == []
        assert http.requests == []
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "alpaca-url" in ln)
        assert line.startswith("::warning title=alpaca-url::"), line


class Testm3DeterministicAttribution:
    """m3: deterministic body uses decision attribution; mirror only in provenance."""

    def test_direct_quote_body_says_on_truth_social_not_mirror(self, tmp_path):
        a, _ = _tariff_from_both_mirrors()  # trumpstruth mirror, direct-quote
        res = run_press_tick([a], root=tmp_path, now=_MARKET_HOURS, cfg=_CFG,
                             press_cfg=_PRESS_CFG, state={}, seen_ids=set(), dry_run=True)
        emit = next(e for e in res["emitted"]
                    if "tariff" in e["headline"].lower())
        body = emit["body"]
        # deterministic mode (no LLM) -> body carries the DECISION attribution
        assert "on Truth Social" in body, "deterministic body missing decision attribution (m3)"
        # the mirror surface is NOT named in the post body
        assert "trumpstruth" not in body.lower()
        assert "via" not in body.lower()
        # but the mirror IS recorded in provenance/ledger
        assert "trumpstruth" in emit["source"]["via_source"].lower()
