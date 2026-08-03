"""tests/test_marketing_press_wire.py — Actions press wire acceptance tests (E7).

Fixture-driven; ZERO live network. Both pollers are monkeypatched in every test
that reaches them, and the one test that exercises the real
``press_providers.poll_all`` disables the mirror providers and replaces the
twitterapi.io transport with a function that FAILS the test if it is called.

MARKETING_LLM_ENABLED / MARKETING_PUBLISH_ENABLED are never set here; the outbox
queue switch (MARKETING_OUTBOX_ENABLED) is set only inside the tests that assert
an emission, via monkeypatch.

Covers:
  1. The budget is a TEST, not a comment — the shipped config's projected monthly
     twitterapi.io spend must sit under the lane's own cap, which must itself sit
     under the estate cap. A cadence edit that overruns turns this red.
  2. Tier cadence arithmetic + the Actions config transform (poll_tiers override,
     sub-cap clamp, caller's dict left untouched).
  3. Committed-state round-trips: cursors.json, the append-only spend deltas, the
     two-key-space seen ring, and breaking_feed's hydrate/harvest bridge.
  4. Spend-cap enforcement FROM COMMITTED STATE — an over-cap ledger makes the
     provider refuse before any request, with the ::warning at line start.
  5. PRESS_WIRE_DAEMON_ACTIVE makes the whole tick a no-op before any poll.
  6. An emitted item reaches the git-TRACKED items.jsonl and fold_state sees it
     queued — the actual split-brain this program closes.
  7. Cold-start priming, dry-run non-consumption, cross-tick dedupe.
  8. Workflow + gitattributes shape guards.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

import scripts.marketing_press_wire as PW  # noqa: E402
from engine.marketing import breaking_feed, press_providers  # noqa: E402
from engine.marketing.press_providers import TrumpstruthProvider  # noqa: E402

NOW = datetime(2026, 7, 27, 16, 0, 0, tzinfo=timezone.utc)   # Monday, ET afternoon

_TS_CFG = {"key": "trumpstruth", "source_name": "Truth Social (via trumpstruth.org)",
           "author": "Donald J. Trump"}


def _live_press_cfg() -> dict:
    import yaml

    return yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))


def _fixture_items() -> list[dict]:
    """Direct-quote Truth items from the committed fixture (no network)."""
    return TrumpstruthProvider(_TS_CFG).parse(
        (FIXTURES / "trumpstruth_feed.xml").read_text(encoding="utf-8")
    )


def _stage_repo(tmp_path: Path, *, press_cfg: dict | None = None) -> Path:
    """A minimal repo root: the two config files the tick reads, nothing else."""
    import yaml

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    press = press_cfg if press_cfg is not None else {
        "satire_blocklist": ["HalfwayPost"],
        "wire": {"flagship_top_k_per_day": 3, "flagship_salience_floor": 40.0},
        "x_follow": {"handles": [], "poll_tiers": {"fast": 75}},
        "spend": {"twitterapiio_monthly_cap_usd": 75.0},
        "actions_wire": {"monthly_usd_cap": 55.0},
    }
    (cfg_dir / "press_sources.yml").write_text(yaml.safe_dump(press), encoding="utf-8")
    (cfg_dir / "marketing.yml").write_text(
        yaml.safe_dump({"breaking": {"llm": {"enabled": False}}}), encoding="utf-8")
    return tmp_path


def _no_network(monkeypatch, *, wire_items=None, press_items=None):
    """Replace BOTH pollers. Anything reaching the network fails the test."""
    monkeypatch.setattr(breaking_feed, "poll_all",
                        lambda root, cfg: list(wire_items or []))
    monkeypatch.setattr(
        press_providers, "poll_all",
        lambda root, cfg, state, offline=False, now=None: list(press_items or []))


# ---------------------------------------------------------------------------
# 1. The budget is a test
# ---------------------------------------------------------------------------

class TestBudget:
    def test_shipped_config_projects_under_its_own_cap(self):
        """A cadence edit that overruns the budget must redden the suite, not the
        invoice. This is the gate the config comment's arithmetic points at."""
        cfg = _live_press_cfg()
        projection = PW.projected_monthly_usd(cfg)
        cap = PW.actions_monthly_cap(cfg)
        assert projection["usd_per_month"] <= cap, (
            f"projected ${projection['usd_per_month']}/mo exceeds the lane cap "
            f"${cap} — the provider would hard-stop mid-month and the wire would "
            f"go dark: {projection}")

    def test_lane_cap_leaves_the_reply_desk_whole(self):
        """One bucket, two lanes: the wire's sub-cap plus the reply desk's must
        not exceed the single twitterapi.io account cap."""
        cfg = _live_press_cfg()
        estate = float(cfg["spend"]["twitterapiio_monthly_cap_usd"])
        reply = float((cfg.get("reply_discovery") or {}).get("monthly_usd_cap", 0.0))
        assert PW.actions_monthly_cap(cfg) + reply <= estate

    def test_cap_is_clamped_to_the_estate_cap(self):
        """A typo in the sub-block can only ever LOWER the ceiling."""
        cfg = {"spend": {"twitterapiio_monthly_cap_usd": 75.0},
               "actions_wire": {"monthly_usd_cap": 9000.0}}
        assert PW.actions_monthly_cap(cfg) == 75.0

    def test_projection_uses_the_billed_page_not_the_minimum_charge(self):
        """Budgeting off the $0.00015 minimum charge under-states this lane 20x."""
        cfg = _live_press_cfg()
        projection = PW.projected_monthly_usd(cfg)
        assert projection["usd_per_request"] == pytest.approx(0.003, rel=1e-6)

    def test_every_five_minute_polling_would_blow_the_estate_cap(self):
        """The reason the fast tier is 19 minutes and not 5, pinned as a number."""
        cfg = _live_press_cfg()
        naive = dict(cfg)
        naive["actions_wire"] = dict(cfg["actions_wire"],
                                     poll_tiers={"fast": 300, "mid": 300, "slow": 300})
        assert PW.projected_monthly_usd(naive)["usd_per_month"] > 400.0


# ---------------------------------------------------------------------------
# 2. Tier cadence + the Actions config transform
# ---------------------------------------------------------------------------

class TestCadence:
    def test_intervals_come_from_config_with_defaults_for_missing_tiers(self):
        cfg = {"actions_wire": {"poll_tiers": {"fast": 600}}}
        intervals = PW.poll_tier_intervals(cfg)
        assert intervals["fast"] == 600
        assert intervals["mid"] == PW.DEFAULT_TIER_INTERVALS_S["mid"]
        assert intervals["slow"] == PW.DEFAULT_TIER_INTERVALS_S["slow"]

    def test_missing_block_falls_back_to_shipped_defaults(self):
        assert PW.poll_tier_intervals({}) == PW.DEFAULT_TIER_INTERVALS_S

    def test_requests_per_day_is_handles_times_day_over_interval(self):
        cfg = {
            "x_follow": {"handles": [{"handle": "a", "tier": "fast"},
                                     {"handle": "b", "tier": "fast"}]},
            "actions_wire": {"poll_tiers": {"fast": 1200}, "tweets_per_request": 20},
        }
        projection = PW.projected_monthly_usd(cfg)
        assert projection["requests_per_day_by_tier"]["fast"] == pytest.approx(144.0)

    def test_satire_and_pcf_handles_are_not_budgeted(self):
        """The projection must count the handles that will actually be polled —
        the provider drops these two at construction."""
        cfg = {
            "satire_blocklist": ["HalfwayPost"],
            "x_follow": {"exclude_pcf_labeled": True, "handles": [
                {"handle": "real", "tier": "fast"},
                {"handle": "HalfwayPost", "tier": "fast"},
                {"handle": "parody", "tier": "fast", "pcf_labeled": True},
            ]},
        }
        assert PW.handles_by_tier(cfg) == {"fast": 1}

    def test_actions_cfg_overrides_tiers_and_cap_without_touching_the_caller(self):
        """The whole Actions-mode adaptation is this transform — press_providers.py
        and the daemon's own config path stay byte-identical."""
        cfg = _live_press_cfg()
        original_tiers = dict(cfg["x_follow"]["poll_tiers"])
        original_cap = cfg["spend"]["twitterapiio_monthly_cap_usd"]

        out = PW.actions_press_cfg(cfg)

        assert out["x_follow"]["poll_tiers"] == PW.poll_tier_intervals(cfg)
        assert out["spend"]["twitterapiio_monthly_cap_usd"] == PW.actions_monthly_cap(cfg)
        assert out["spend"]["twitterapiio_monthly_cap_usd"] < original_cap
        # The daemon reads the untransformed dict; it must not see the overrides.
        assert cfg["x_follow"]["poll_tiers"] == original_tiers
        assert cfg["spend"]["twitterapiio_monthly_cap_usd"] == original_cap


# ---------------------------------------------------------------------------
# 3. Committed-state round-trips
# ---------------------------------------------------------------------------

class TestCursorsState:
    def test_round_trip(self, tmp_path):
        state = {"providers": {"twitterapiio": {"cursors": {"DeItaone": "1234"}}},
                 "flagship_counter": {"day": "2026-07-27", "count": 2},
                 "corroboration": {"truth:x": {"sources": ["a"], "first_ts": "t"}}}
        PW.save_cursors(tmp_path, state, now=NOW, press_cfg={})
        back = PW.load_cursors(tmp_path)
        assert back["providers"]["twitterapiio"]["cursors"]["DeItaone"] == "1234"
        assert back["flagship_counter"]["count"] == 2
        assert back["corroboration"]["truth:x"]["sources"] == ["a"]
        assert back["schema"] == PW.CURSORS_SCHEMA

    def test_missing_file_is_a_cold_start_not_an_error(self, tmp_path):
        assert PW.load_cursors(tmp_path) == {}

    def test_corrupt_file_degrades_to_empty_with_a_line_start_warning(self, tmp_path, capsys):
        path = tmp_path / PW.CURSORS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert PW.load_cursors(tmp_path) == {}
        line = capsys.readouterr().out.strip().splitlines()[0]
        assert line.startswith("::warning")

    def test_scoring_stores_are_dropped_by_default(self, tmp_path):
        """They change no gate while rank_ordering is dark, and this file is
        rewritten whole 288 times a day."""
        state = {"story_spine": {"stories": {"s": 1}}, "signal_corpus": {"days": {}},
                 "source_authority": {"sources": {}}, "flagship_counter": {"count": 1}}
        PW.save_cursors(tmp_path, state, now=NOW, press_cfg={})
        back = PW.load_cursors(tmp_path)
        for key in PW.SCORING_KEYS:
            assert key not in back
        assert back["flagship_counter"]["count"] == 1

    def test_scoring_stores_persist_when_armed(self, tmp_path):
        state = {"story_spine": {"stories": {"s": 1}}}
        PW.save_cursors(tmp_path, state, now=NOW,
                        press_cfg={"actions_wire": {"persist_scoring": True}})
        assert PW.load_cursors(tmp_path)["story_spine"] == {"stories": {"s": 1}}

    def test_byte_ceiling_drops_scoring_stores_and_says_so(self, tmp_path, capsys):
        state = {"story_spine": {"stories": {str(i): "x" * 200 for i in range(200)}},
                 "flagship_counter": {"count": 3}}
        PW.save_cursors(tmp_path, state, now=NOW, press_cfg={
            "actions_wire": {"persist_scoring": True, "cursors_max_bytes": 4096}})
        back = PW.load_cursors(tmp_path)
        assert "story_spine" not in back
        assert back["flagship_counter"]["count"] == 3      # correctness key survives
        warnings = [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]
        assert any("ceiling" in ln for ln in warnings)


class TestSpendLedger:
    def test_deltas_sum_to_the_month_total(self, tmp_path):
        PW.append_spend(tmp_path, {"requests": 3, "tweets": 60, "usd": 0.009},
                        month="2026-07", now=NOW)
        PW.append_spend(tmp_path, {"requests": 2, "tweets": 40, "usd": 0.006},
                        month="2026-07", now=NOW)
        PW.append_spend(tmp_path, {"requests": 9, "tweets": 180, "usd": 0.027},
                        month="2026-06", now=NOW)
        total = PW.fold_spend(tmp_path, "2026-07")
        assert total["requests"] == 5
        assert total["tweets"] == 100
        assert total["usd"] == pytest.approx(0.015)

    def test_duplicate_rows_from_a_union_merge_both_count(self, tmp_path):
        """Rows are DELTAS precisely so union merge is the correct resolution:
        two runs that appended in the same push race must both be counted."""
        path = tmp_path / PW.SPEND_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        row = json.dumps({"month": "2026-07", "requests": 1, "tweets": 20, "usd": 0.003})
        path.write_text(row + "\n" + row + "\n", encoding="utf-8")
        assert PW.fold_spend(tmp_path, "2026-07")["usd"] == pytest.approx(0.006)

    def test_zero_spend_writes_no_row(self, tmp_path):
        assert PW.append_spend(tmp_path, {"requests": 0, "tweets": 0, "usd": 0.0},
                               month="2026-07", now=NOW) is False
        assert not (tmp_path / PW.SPEND_REL).exists()

    def test_bad_lines_are_skipped_not_fatal(self, tmp_path):
        path = tmp_path / PW.SPEND_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"month":"2026-07","usd":0.01}\nnot json\n\n', encoding="utf-8")
        assert PW.fold_spend(tmp_path, "2026-07")["usd"] == pytest.approx(0.01)

    def test_roll_keeps_the_current_month(self, tmp_path):
        PW.append_spend(tmp_path, {"requests": 1, "usd": 0.003}, month="2019-01", now=NOW)
        PW.append_spend(tmp_path, {"requests": 1, "usd": 0.003}, month="2026-07", now=NOW)
        assert PW.roll_spend(tmp_path, now=NOW) == 1
        assert PW.fold_spend(tmp_path, "2026-07")["usd"] == pytest.approx(0.003)
        assert PW.fold_spend(tmp_path, "2019-01")["usd"] == 0.0


class TestSeenRing:
    def test_two_key_spaces_stay_separate(self, tmp_path):
        PW.append_seen(tmp_path, {PW.SEEN_SPACE_PRESS: ["p1"],
                                  PW.SEEN_SPACE_WIRE: ["w1"]}, now=NOW)
        assert set(PW.load_seen(tmp_path, PW.SEEN_SPACE_PRESS, now=NOW)) == {"p1"}
        assert set(PW.load_seen(tmp_path, PW.SEEN_SPACE_WIRE, now=NOW)) == {"w1"}

    def test_rows_past_the_age_horizon_are_not_returned(self, tmp_path):
        PW.append_seen(tmp_path, {PW.SEEN_SPACE_PRESS: ["old"]}, now=NOW)
        later = NOW + timedelta(hours=PW.SEEN_MAX_AGE_H + 1)
        assert PW.load_seen(tmp_path, PW.SEEN_SPACE_PRESS, now=later) == {}

    def test_roll_trims_to_capacity_keeping_the_newest(self, tmp_path):
        for i in range(5):
            PW.append_seen(tmp_path, {PW.SEEN_SPACE_PRESS: [f"k{i}"]},
                           now=NOW + timedelta(minutes=i))
        assert PW.roll_seen(tmp_path, now=NOW + timedelta(minutes=10), keep=2) == 3
        kept = PW.load_seen(tmp_path, PW.SEEN_SPACE_PRESS, now=NOW + timedelta(minutes=10))
        assert set(kept) == {"k3", "k4"}


class TestBreakingBridge:
    def test_hydrate_then_harvest_round_trips_etag_state_and_seen(self, tmp_path):
        cursors = {"wire": {"cnbc": {"etag": "abc", "last_poll_ts": 123.0}}}
        PW.hydrate_breaking(tmp_path, cursors, {"item-1": "2026-07-27T00:00:00Z"})

        d = tmp_path / PW.BREAKING_SUBDIR
        assert json.loads((d / "state.json").read_text())["cnbc"]["etag"] == "abc"
        assert json.loads((d / "seen.json").read_text()) == {"item-1": "2026-07-27T00:00:00Z"}

        # breaking_feed would advance both in place; simulate and harvest back.
        (d / "state.json").write_text(json.dumps({"cnbc": {"etag": "def"}}))
        (d / "seen.json").write_text(json.dumps({"item-1": "t", "item-2": "t"}))
        out = {}
        seen = PW.harvest_breaking(tmp_path, out)
        assert out["wire"]["cnbc"]["etag"] == "def"
        assert set(seen) == {"item-1", "item-2"}

    def test_hydrate_uses_the_real_breaking_feed_paths(self, tmp_path):
        """Pins the bridge to breaking_feed's own path helper — a move there must
        break this, not silently strand the seen ledger."""
        PW.hydrate_breaking(tmp_path, {}, {})
        assert breaking_feed._breaking_dir(tmp_path) == tmp_path / PW.BREAKING_SUBDIR
        assert breaking_feed._load_seen(tmp_path) == {}
        assert breaking_feed._load_state(tmp_path) == {}


# ---------------------------------------------------------------------------
# 4. Spend-cap enforcement from COMMITTED state
# ---------------------------------------------------------------------------

class TestSpendCapFromCommittedState:
    def _cfg(self) -> dict:
        return {
            "truth_mirrors": [],       # free mirror providers OFF: no network at all
            "satire_blocklist": [],
            "x_follow": {"handles": [{"handle": "DeItaone", "tier": "fast"}],
                         "poll_tiers": {"fast": 1}},
            "spend": {"twitterapiio_monthly_cap_usd": 75.0},
            "actions_wire": {"monthly_usd_cap": 1.0},
        }

    def test_over_cap_ledger_refuses_before_any_request(self, tmp_path, monkeypatch, capsys):
        """THE REASON THE STATE IS COMMITTED. In Actions every run is a fresh
        checkout: without this ledger the provider starts every month at $0.00 and
        the cap is never enforced at all."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key-not-used")
        month = PW.month_key(NOW)
        PW.append_spend(tmp_path, {"requests": 400, "tweets": 8000, "usd": 1.20},
                        month=month, now=NOW)

        def _explode(self, api_key, handle):     # noqa: ANN001
            pytest.fail("over-cap lane reached the network")

        monkeypatch.setattr(press_providers.TwitterApiIoProvider, "_request", _explode)

        spent = PW.fold_spend(tmp_path, month)
        session: dict = {"twitterapiio": {"spend": {month: {
            "requests": int(spent["requests"]), "tweets": int(spent["tweets"]),
            "usd": float(spent["usd"])}}}}
        items = press_providers.poll_all(
            tmp_path, PW.actions_press_cfg(self._cfg()), session, offline=False, now=NOW)

        assert items == []
        warnings = [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]
        assert any("spend-cap" in ln for ln in warnings), (
            "the cap stop must annotate at LINE START (never through a logger)")

    def test_under_cap_ledger_still_permits_the_lane(self, tmp_path, monkeypatch):
        """The mirror of the test above: an under-cap ledger must NOT stop the
        lane, or the cap enforcement would be a permanent outage."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        month = PW.month_key(NOW)
        PW.append_spend(tmp_path, {"requests": 1, "tweets": 20, "usd": 0.003},
                        month=month, now=NOW)
        calls: list[str] = []

        def _fake(self, api_key, handle):        # noqa: ANN001
            calls.append(handle)
            return {"tweets": []}

        monkeypatch.setattr(press_providers.TwitterApiIoProvider, "_request", _fake)
        spent = PW.fold_spend(tmp_path, month)
        session: dict = {"twitterapiio": {"spend": {month: {
            "requests": int(spent["requests"]), "tweets": int(spent["tweets"]),
            "usd": float(spent["usd"])}}}}
        press_providers.poll_all(
            tmp_path, PW.actions_press_cfg(self._cfg()), session, offline=False, now=NOW)
        assert calls == ["DeItaone"]

    def test_tick_appends_only_the_delta_it_spent(self, tmp_path, monkeypatch):
        """The ledger must record THIS tick's spend, not the running total it was
        seeded with — otherwise the month double-counts every run."""
        root = _stage_repo(tmp_path)
        month = PW.month_key(NOW)
        PW.append_spend(root, {"requests": 10, "tweets": 200, "usd": 0.60},
                        month=month, now=NOW)

        def _spender(root_, cfg, state, offline=False, now=None):   # noqa: ANN001
            bucket = state.setdefault("twitterapiio", {}).setdefault("spend", {})[month]
            bucket["requests"] += 2
            bucket["tweets"] += 40
            bucket["usd"] = round(bucket["usd"] + 0.006, 6)
            return []

        monkeypatch.setattr(breaking_feed, "poll_all", lambda r, c: [])
        monkeypatch.setattr(press_providers, "poll_all", _spender)
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)

        assert PW.run(root, now=NOW) == 0
        rows = [json.loads(ln) for ln in
                (root / PW.SPEND_REL).read_text().splitlines() if ln.strip()]
        assert len(rows) == 2
        assert rows[-1]["usd"] == pytest.approx(0.006)
        assert rows[-1]["requests"] == 2
        assert PW.fold_spend(root, month)["usd"] == pytest.approx(0.606)


# ---------------------------------------------------------------------------
# 5. Daemon-active stand-down
# ---------------------------------------------------------------------------

class TestDaemonStanddown:
    def test_daemon_active_makes_the_tick_a_noop_before_any_poll(
            self, tmp_path, monkeypatch, capsys):
        root = _stage_repo(tmp_path)

        def _explode(*args, **kwargs):
            pytest.fail("stood-down lane polled anyway")

        monkeypatch.setattr(breaking_feed, "poll_all", _explode)
        monkeypatch.setattr(press_providers, "poll_all", _explode)
        monkeypatch.setenv(PW.ENV_DAEMON_ACTIVE, "true")
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")

        assert PW.run(root, now=NOW) == 0
        assert not (root / PW.CURSORS_REL).exists()
        assert not (root / PW.SPEND_REL).exists()
        line = capsys.readouterr().out.strip().splitlines()[0]
        assert line.startswith("::notice")

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
    def test_truthy_spellings(self, monkeypatch, value):
        monkeypatch.setenv(PW.ENV_DAEMON_ACTIVE, value)
        assert PW.daemon_active() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no"])
    def test_falsy_spellings_leave_the_lane_live(self, monkeypatch, value):
        monkeypatch.setenv(PW.ENV_DAEMON_ACTIVE, value)
        assert PW.daemon_active() is False


# ---------------------------------------------------------------------------
# 6. The emission actually reaches the publisher's queue
# ---------------------------------------------------------------------------

class TestCanonicalEmission:
    def _armed(self, monkeypatch):
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)

    def _prime_then_run(self, root, monkeypatch, items):
        """Cold start primes (emits nothing); the second tick is the real one."""
        _no_network(monkeypatch, wire_items=items)
        PW.run(root, now=NOW)                                  # prime
        _no_network(monkeypatch, wire_items=_fixture_items())  # fresh objects
        return PW.run(root, now=NOW + timedelta(minutes=5))

    def test_emitted_item_lands_in_the_tracked_items_jsonl(self, tmp_path, monkeypatch):
        """THE WHOLE PROGRAM. The daemon emits with spool=True into the GITIGNORED
        items-host.jsonl, which the Actions publisher folds from a different
        checkout and has therefore never seen. This lane emits with spool=False."""
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        # Second tick over the same batch: seed the ring with nothing so the
        # fixture items are new, but skip the cold-start prime by pre-creating state.
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        PW.append_seen(root, {PW.SEEN_SPACE_PRESS: ["unrelated"]}, now=NOW)
        _no_network(monkeypatch, wire_items=_fixture_items())

        assert PW.run(root, now=NOW) == 0

        items_path = root / "data" / "marketing" / "outbox" / "items.jsonl"
        assert items_path.exists(), "emission did not reach the canonical queue"
        rows = [json.loads(ln) for ln in items_path.read_text().splitlines() if ln.strip()]
        assert rows, "items.jsonl is empty"
        for row in rows:
            assert row["kind"] == "breaking"
            assert row["scheduled_at"] == "immediate"
            assert row["schema"] == "marketing.outbox/v1"
            assert row["source"]["lane"] == "press"

        # The GITIGNORED daemon spool must stay empty — that file is the bug.
        assert not (root / "data" / "marketing" / "outbox" / "items-host.jsonl").exists()

    def test_fold_state_sees_the_item_queued(self, tmp_path, monkeypatch):
        """What the publisher actually does with items.jsonl."""
        from engine.marketing import outbox as OB

        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        PW.append_seen(root, {PW.SEEN_SPACE_PRESS: ["unrelated"]}, now=NOW)
        _no_network(monkeypatch, wire_items=_fixture_items())
        PW.run(root, now=NOW)

        state = OB.fold_state(root)
        press_ids = [i for i, item in (state.get("items") or {}).items()
                     if (item.get("source") or {}).get("lane") == "press"]
        assert press_ids
        assert all(state["status"][i] == "queued" for i in press_ids)

    def test_booked_ids_are_written_to_github_output(self, tmp_path, monkeypatch):
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        PW.append_seen(root, {PW.SEEN_SPACE_PRESS: ["unrelated"]}, now=NOW)
        _no_network(monkeypatch, wire_items=_fixture_items())
        PW.run(root, now=NOW)

        written = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        assert written.startswith("post_now_ids="), written
        assert written.strip().split("=", 1)[1]

    def test_cold_start_primes_and_emits_nothing(self, tmp_path, monkeypatch):
        """The first Actions run sees a full history snapshot (mirror archives,
        last_tweets with no cursor). Priming is what stops it flooding the queue."""
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        _no_network(monkeypatch, wire_items=_fixture_items())

        assert PW.run(root, now=NOW) == 0
        assert not (root / "data" / "marketing" / "outbox" / "items.jsonl").exists()
        # …but the seen ring is seeded, so the next tick dedupes the history away.
        assert PW.load_seen(root, PW.SEEN_SPACE_PRESS, now=NOW)

    def test_second_tick_over_the_same_batch_emits_nothing(self, tmp_path, monkeypatch):
        """Cross-tick dedupe through the COMMITTED ring — the state that would
        otherwise evaporate with the checkout and re-post every story every run."""
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        PW.append_seen(root, {PW.SEEN_SPACE_PRESS: ["unrelated"]}, now=NOW)

        _no_network(monkeypatch, wire_items=_fixture_items())
        PW.run(root, now=NOW)
        items_path = root / "data" / "marketing" / "outbox" / "items.jsonl"
        first = len(items_path.read_text().splitlines())

        _no_network(monkeypatch, wire_items=_fixture_items())
        PW.run(root, now=NOW + timedelta(minutes=5))
        assert len(items_path.read_text().splitlines()) == first

    def test_queue_switch_unset_writes_no_item(self, tmp_path, monkeypatch):
        """MARKETING_OUTBOX_ENABLED is the arming switch; unset, the pipeline runs
        and books nothing."""
        root = _stage_repo(tmp_path)
        monkeypatch.delenv(PW.ENV_OUTBOX_ENABLED, raising=False)
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        PW.append_seen(root, {PW.SEEN_SPACE_PRESS: ["unrelated"]}, now=NOW)
        _no_network(monkeypatch, wire_items=_fixture_items())

        assert PW.run(root, now=NOW) == 0
        assert not (root / "data" / "marketing" / "outbox" / "items.jsonl").exists()

    def test_dry_run_is_non_consuming(self, tmp_path, monkeypatch):
        """An inspection run may not advance the seen ring or the spend ledger, or
        it would silently dedupe those items away from the next LIVE run."""
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        PW.save_cursors(root, {}, now=NOW, press_cfg={})
        before = (root / PW.CURSORS_REL).read_text(encoding="utf-8")
        _no_network(monkeypatch, wire_items=_fixture_items())

        assert PW.run(root, now=NOW, dry_run=True) == 0
        assert not (root / "data" / "marketing" / "outbox" / "items.jsonl").exists()
        assert not (root / PW.SEEN_REL).exists()
        assert not (root / PW.SPEND_REL).exists()
        assert (root / PW.CURSORS_REL).read_text(encoding="utf-8") == before

    def test_a_broken_poller_never_raises(self, tmp_path, monkeypatch):
        """Fail toward 'no post': a lane that crashes 288 times a day is noise."""
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)

        def _boom(*args, **kwargs):
            raise RuntimeError("upstream is down")

        monkeypatch.setattr(breaking_feed, "poll_all", _boom)
        monkeypatch.setattr(press_providers, "poll_all", _boom)
        assert PW.run(root, now=NOW) == 0


# ---------------------------------------------------------------------------
# 6b. The salience-floor diagnostic (open calibration question, NOT fixed here)
# ---------------------------------------------------------------------------

class TestFloorDiagnostic:
    """Closing the split-brain was necessary and is not sufficient.

    The floor check runs BEFORE account routing, so an item under
    wire.flagship_salience_floor emits to no account at all. Retuning a relevance
    gate is a content-calibration call rather than plumbing, so this lane REPORTS
    the condition instead of silently posting nothing.

    The diagnostic's own text is under test here as well. Its first cut recited
    the calibration as it stood that morning ("the mirror/x_relay tiers earn no
    tier bonus"), the E7 calibration landed on the same branch hours later, and
    the line went on printing a state of the world that no longer existed. Every
    number it prints is now read from the taxonomy at call time.
    """

    def test_fires_when_the_floor_blocked_the_whole_tick(self):
        # SETS ITS OWN UNREACHABLE FLOOR. This used to read the live config and
        # rely on it being 70.0 — i.e. the test only passed while production was
        # misconfigured, and it broke the moment the floor was fixed (2026-07-31,
        # 70 was the exact ceiling of macro_print+official, which is why the wire
        # only ever posted BEA prints). A diagnostic test must construct the
        # condition it reports on.
        cfg = _live_press_cfg()
        cfg["wire"]["flagship_salience_floor"] = 999.0
        line = PW.floor_diagnostic(
            cfg, [{"reason": "below_flagship_floor", "salience": 45.0}], [])
        assert line is not None and line.startswith("::notice")
        assert "flagship_salience_floor" in line

    def test_silent_when_something_emitted(self):
        cfg = _live_press_cfg()
        assert PW.floor_diagnostic(
            cfg, [{"reason": "below_flagship_floor", "salience": 45.0}],
            [{"id": "ob-1"}]) is None

    def test_silent_when_the_skips_were_for_other_reasons(self):
        cfg = _live_press_cfg()
        assert PW.floor_diagnostic(cfg, [{"reason": "dedupe"}], []) is None

    def test_disarms_itself_once_the_floor_is_reachable(self):
        """When the calibration is fixed this stops firing on its own — it is a
        report on a live condition, not a permanent alarm."""
        cfg = _live_press_cfg()
        cfg["wire"]["flagship_salience_floor"] = 40.0
        assert PW.floor_diagnostic(
            cfg, [{"reason": "below_flagship_floor", "salience": 30.0}], []) is None

    def test_the_message_recites_no_remembered_constant(self):
        """MINOR (stale text). Every figure in the line must agree with the live
        tables, and the line must not claim the press tiers earn nothing — they
        have earned a bonus since the E7 calibration."""
        from engine.marketing.breaking_relevance import _CLASS_TAXONOMY, _TIER_BONUS

        cfg = _live_press_cfg()
        cfg["wire"]["flagship_salience_floor"] = 999.0   # construct the condition
        line = PW.floor_diagnostic(
            cfg, [{"reason": "below_flagship_floor", "salience": 62.0}], [])
        assert line is not None, "fixture no longer trips the diagnostic"
        max_base = max(float(row[1]) for row in _CLASS_TAXONOMY)
        press_bonus = max(float(_TIER_BONUS.get(t, 0.0))
                          for t in ("mirror", "x_relay"))
        assert f"base is {max_base:g}" in line, line
        assert f"+{press_bonus:g}" in line, line
        assert "earn no tier bonus" not in line
        assert press_bonus > 0, (
            "the press tiers lost their bonus — update the diagnostic's premise")

    def test_it_disarms_when_the_press_tiers_can_reach_the_floor(self):
        """The reachability test counts the TIER BONUS this lane's items carry,
        not the base alone: a floor a mirror item clears on base+tier is not a
        floor worth annotating."""
        cfg = _live_press_cfg()
        cfg["wire"]["flagship_salience_floor"] = 60.0     # 55 base + 12 mirror
        assert PW.floor_diagnostic(
            cfg, [{"reason": "below_flagship_floor", "salience": 55.0}], []) is None

    def test_the_calibration_gap_is_closed_and_the_arithmetic_is_pinned(self):
        """The E7 calibration ruling (2026-07-29), pinned so it cannot silently
        regress: both press-provider tiers now earn a tier bonus, and a bare
        policy post from the president's own mirror clears the 60 emit
        threshold (50 base + 12 mirror = 62) while a bare AGGREGATOR policy
        post stays under it (50 + 0) and flagship's 70 floor still demands
        keyword/ticker strength on top. When this test fails, the taxonomy
        moved — re-derive the floor arithmetic before touching the assert."""
        from engine.marketing.breaking_relevance import _CLASS_TAXONOMY, _TIER_BONUS

        policy_base = next(float(row[1]) for row in _CLASS_TAXONOMY
                           if row[0] == "policy")
        assert _TIER_BONUS.get("mirror") == 12.0
        assert _TIER_BONUS.get("x_relay") == 8.0
        assert policy_base + _TIER_BONUS["mirror"] >= 60.0
        assert policy_base + _TIER_BONUS["aggregator"] < 60.0
        # The flagship floor moved 70 -> 30 on 2026-07-31 because 70 was exactly
        # macro_print(55) + official(15), so it admitted ONE class and nothing
        # else. What this line pins is the arithmetic that made 70 wrong, not the
        # value itself: a mirror policy post is 62, which is why it could never
        # clear a 70 floor and can clear a 30 one.
        assert policy_base + _TIER_BONUS["mirror"] == 62.0


# ---------------------------------------------------------------------------
# 7. Publisher dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    def _queue(self, root: Path, rows: list[dict]) -> None:
        path = root / "data" / "marketing" / "outbox" / "items.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def _item(self, item_id: str, *, lane: str, created: datetime) -> dict:
        return {"schema": "marketing.outbox/v1", "id": item_id, "account": "flagship",
                "kind": "breaking", "text": item_id, "as_of": "2026-07-27",
                "media": [], "scheduled_at": "immediate", "slot": None, "priority": 1,
                "provenance": "press_lane", "source": {"lane": lane},
                "status": "queued",
                "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def test_recent_still_queued_press_items_ride_along_oldest_first(self, tmp_path):
        self._queue(tmp_path, [
            self._item("ob-old", lane="press", created=NOW - timedelta(minutes=20)),
            self._item("ob-new", lane="press", created=NOW),
        ])
        assert PW.dispatch_ids(tmp_path, ["ob-new"], now=NOW) == ["ob-old", "ob-new"]

    def test_other_lanes_are_never_dispatched(self, tmp_path):
        self._queue(tmp_path, [
            self._item("ob-hot", lane="hot_tape", created=NOW - timedelta(minutes=5)),
        ])
        assert PW.dispatch_ids(tmp_path, ["ob-mine"], now=NOW) == ["ob-mine"]

    def test_stale_backlog_is_named_in_one_line_start_warning(self, tmp_path, capsys):
        self._queue(tmp_path, [
            self._item("ob-stale", lane="press",
                       created=NOW - timedelta(minutes=PW.CARRYOVER_MAX_AGE_MIN + 30)),
        ])
        assert PW.dispatch_ids(tmp_path, [], now=NOW) == []
        warnings = [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]
        assert any("ob-stale" in ln for ln in warnings)

    def test_no_queue_file_degrades_to_booked_only(self, tmp_path):
        assert PW.dispatch_ids(tmp_path, ["ob-a"], now=NOW) == ["ob-a"]


# ---------------------------------------------------------------------------
# 8. Workflow + gitattributes shape guards
# ---------------------------------------------------------------------------

WORKFLOW_PATH = ROOT / ".github" / "workflows" / "marketing-press-wire.yml"


@pytest.fixture(scope="module")
def wf_text() -> str:
    assert WORKFLOW_PATH.exists(), "the Actions lane is the whole fix — it must exist"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wf(wf_text: str) -> dict:
    import yaml

    return yaml.safe_load(wf_text)


@pytest.fixture(scope="module")
def attrs() -> str:
    return (ROOT / ".gitattributes").read_text(encoding="utf-8")


class TestWorkflowShape:
    def test_runs_every_five_minutes_around_the_clock(self, wf):
        # PyYAML parses a bare `on:` key as the boolean True.
        crons = [c["cron"] for c in wf[True]["schedule"]]
        assert crons == ["*/5 * * * *"], (
            "news is 24/7 — unlike the hot-tape radar this lane carries no session window")

    def test_never_runs_on_the_render_pool(self, wf):
        assert wf["jobs"]["wire"]["runs-on"] == "ubuntu-latest"

    def test_concurrency_queues_rather_than_cancels(self, wf):
        conc = wf["concurrency"]
        assert conc["group"] == "marketing-press-wire"
        assert conc["cancel-in-progress"] is False

    def test_dispatch_requires_the_push_to_have_landed(self, wf):
        """ORDER IS LOAD-BEARING: the publisher folds items.jsonl from main's HEAD,
        so a dispatch that outruns the push names ids that do not exist there."""
        steps = wf["jobs"]["wire"]["steps"]
        dispatch = [s for s in steps if "gh workflow run" in str(s.get("run", ""))]
        assert len(dispatch) == 1
        assert "steps.commit.outputs.pushed == 'true'" in dispatch[0]["if"]

    def test_lane_cannot_publish_only_queue(self, wf_text):
        """MARKETING_PUBLISH_ENABLED belongs to marketing-publish.yml. This lane
        must never be one env var away from posting."""
        assert "MARKETING_OUTBOX_ENABLED" in wf_text
        assert "MARKETING_PUBLISH_ENABLED:" not in wf_text

    def test_daemon_standdown_variable_is_wired(self, wf_text):
        assert "PRESS_WIRE_DAEMON_ACTIVE: ${{ vars.PRESS_WIRE_DAEMON_ACTIVE }}" in wf_text

    def test_llm_flag_ships_with_its_credentials(self, wf_text):
        """The flag alone is a lie without them (2026-07-26 incident)."""
        assert "MARKETING_LLM_ENABLED" in wf_text
        for secret in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "DEEPSEEK_API_KEY"):
            assert secret in wf_text

    def test_commit_stages_only_this_lanes_paths(self, wf_text):
        assert "git add data/marketing/outbox" in wf_text
        assert "git add data/marketing/press_wire" in wf_text
        assert "git add data/" not in wf_text.replace("git add data/marketing", "")

    def test_installs_no_pandas(self, wf_text):
        """A ~40 s install paid 288 times a day, for a fallback path that does not
        need it (breaking_relevance degrades to its static universe)."""
        install = [ln for ln in wf_text.splitlines() if "pip install" in ln]
        assert install and all("pandas" not in ln for ln in install)


class TestGitattributes:
    def test_append_only_state_is_union_merged(self, attrs):
        assert "data/marketing/press_wire/spend.jsonl merge=union" in attrs
        assert "data/marketing/press_wire/seen_ring.jsonl merge=union" in attrs

    def test_cursors_json_is_not_union_merged(self, attrs):
        """A union-merged JSON document is a syntax error, not a merge."""
        assert "data/marketing/press_wire/cursors.json merge=union" not in attrs

    def test_state_dir_is_tracked_not_gitignored(self):
        """If .gitignore ever swallows this dir the cap stops being enforced and
        every run re-posts every story — silently, because git shows nothing."""
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for line in ignore.splitlines():
            entry = line.strip()
            if entry.startswith("#") or not entry:
                continue
            assert not entry.rstrip("/").endswith("data/marketing/press_wire"), entry


# ---------------------------------------------------------------------------
# 9. BLOCKER 2 — the billed tier fails CLOSED on remote write
# ---------------------------------------------------------------------------

class TestBilledLaneFailsClosedOnPush:
    """A run that cannot push must not spend.

    THE STATE WRITE IS THE BUDGET, and it is two things at once: cursors.json
    holds the per-handle ``last_poll`` the provider throttles against, and
    spend.jsonl holds the deltas ``fold_spend`` sums into the cap guard's seed.
    A push that never lands loses BOTH, so the next */5 run re-polls all 18
    handles believing $0.00 has been spent. The workflow's commit step used to
    exit 0 after five failed attempts, which made that a GREEN loop: ~$466/mo of
    real money against a $75 account, forever, with nothing red anywhere.
    """

    @staticmethod
    def _cfg() -> dict:
        return {
            "x_follow": {
                "handles": [{"handle": "DeItaone", "tier": "fast"}],
                "poll_tiers": {"fast": 60},
            },
            "spend": {"twitterapiio_monthly_cap_usd": 75.0},
            "actions_wire": {"monthly_usd_cap": 50.0, "poll_tiers": {"fast": 60}},
        }

    def _run_with_probe(self, tmp_path, monkeypatch, *, probe_ok: bool):
        root = _stage_repo(tmp_path, press_cfg=self._cfg())
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        monkeypatch.setattr(breaking_feed, "poll_all", lambda r, c: [])
        monkeypatch.setattr(
            PW, "push_access_ok",
            lambda *a, **k: (probe_ok, "ok" if probe_ok else "remote rejected the probe"))
        # The REAL provider runs; its transport fails the test if it is reached.
        reached: list[str] = []
        monkeypatch.setattr(
            press_providers.TwitterApiIoProvider, "_request",
            lambda self, key, handle: reached.append(handle) or {"tweets": []})
        assert PW.run(root, now=NOW) == 0
        return reached

    def test_a_failed_push_probe_stands_the_billed_lane_down(self, tmp_path,
                                                             monkeypatch, capsys):
        reached = self._run_with_probe(tmp_path, monkeypatch, probe_ok=False)
        assert reached == [], (
            "the billed twitterapi.io lane made a request on a run whose state "
            "could not be committed")
        lines = capsys.readouterr().out.splitlines()
        hits = [ln for ln in lines
                if ln.startswith("::warning") and "push-preflight" in ln]
        assert hits, (
            "the stand-down must annotate at LINE START — a logger prefixes the "
            "line and GitHub drops it silently "
            "(tests/test_gh_annotation_line_start.py)")

    def test_a_healthy_push_probe_leaves_the_billed_lane_running(self, tmp_path,
                                                                 monkeypatch):
        """The mirror: fail-closed must not become a permanent outage."""
        reached = self._run_with_probe(tmp_path, monkeypatch, probe_ok=True)
        assert reached == ["DeItaone"]

    def test_the_probe_never_raises_on_a_non_repo(self, tmp_path):
        """git missing, no remote, not a checkout — all read as "cannot push"."""
        ok, why = PW.push_access_ok(tmp_path)
        assert ok is False and why

    def test_the_probe_does_not_push_at_main(self, tmp_path, monkeypatch):
        """A busy main advancing under a fresh checkout is a non-fast-forward the
        commit step's rebase loop resolves in seconds. Probing ``HEAD:main``
        would read that as a push outage and stand the lane down for nothing."""
        seen: dict = {}

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(argv, **kw):
            seen["argv"] = list(argv)
            return _Proc()

        import subprocess as _sp
        monkeypatch.setattr(_sp, "run", _fake_run)
        assert PW.push_access_ok(tmp_path)[0] is True
        assert seen["argv"][-1].startswith("HEAD:refs/heads/")
        assert seen["argv"][-1] != "HEAD:main"


class TestWorkflowPushFailureIsRed:
    def test_the_commit_step_no_longer_swallows_a_terminal_push_failure(self, wf_text):
        """`exit 0` after the retry loop is what made the overspend green.

        The retries stay (a lost race is normal and self-heals); running OUT of
        them must surface as a failed run.
        """
        tail = wf_text.split("could not push state after 5 attempts")[-1]
        assert "exit 1" in tail.split("\n\n")[0], (
            "terminal push failure still exits 0 — a persistent push outage would "
            "loop green every 5 minutes while the spend counter reads $0.00")
        assert "::error title=press-wire-push" in wf_text


# ---------------------------------------------------------------------------
# 10. MAJOR 7 — the three sub-caps must leave a reserve
# ---------------------------------------------------------------------------

class TestSpendCapReserve:
    """Nothing in code sums the lanes; each clamps only against the account cap.

    So three lanes each "within budget" can still bill the whole $75 together —
    and they were EXACTLY $75 (wire 55 + reply 15 + intel 5), zero reserve. This
    is the arithmetic no module owns, pinned here so a cap edit that erases the
    reserve is red.
    """

    RESERVE_USD = 5.0

    @staticmethod
    def _yaml(rel: str) -> dict:
        import yaml
        return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8")) or {}

    def _caps(self) -> dict:
        press = self._yaml("config/press_sources.yml")
        marketing = self._yaml("config/marketing.yml")
        return {
            "account": float(press["spend"]["twitterapiio_monthly_cap_usd"]),
            "wire": float(press["actions_wire"]["monthly_usd_cap"]),
            "reply": float(press["reply_discovery"]["monthly_usd_cap"]),
            "intel": float((marketing.get("intel") or {})["monthly_usd_cap"]),
        }

    def test_every_carve_is_a_config_key_not_a_comment(self):
        """A budget that exists only in prose cannot be enforced or summed."""
        caps = self._caps()
        for lane in ("wire", "reply", "intel"):
            assert caps[lane] > 0, f"{lane} carve is missing from config"

    def test_the_lanes_sum_under_the_account_cap_with_a_reserve(self):
        caps = self._caps()
        total = caps["wire"] + caps["reply"] + caps["intel"]
        assert total <= caps["account"] - self.RESERVE_USD, (
            f"press {caps['wire']} + reply {caps['reply']} + intel {caps['intel']} "
            f"= {total} against a {caps['account']} account cap: the ${self.RESERVE_USD} "
            "reserve is gone. Minimum-charge rounding, a retry or a manual backfill "
            "in ANY lane now overdraws the real account.")

    def test_the_wire_cap_still_clears_its_own_projection(self):
        """A cap under the plan is not conservative — it is a silent outage
        around day 26 of every month. Lowering the cap must not create one."""
        import yaml
        press = yaml.safe_load(
            (ROOT / "config/press_sources.yml").read_text(encoding="utf-8"))
        projected = PW.projected_monthly_usd(press)["usd_per_month"]
        assert projected <= PW.actions_monthly_cap(press), (
            f"projected ${projected}/mo exceeds the lane cap "
            f"${PW.actions_monthly_cap(press)}")

    def test_the_code_default_tracks_the_config(self):
        """DEFAULT_ACTIONS_CAP_USD is used when the config block is absent; a
        stale default would silently RAISE the cap in that case."""
        import yaml
        press = yaml.safe_load(
            (ROOT / "config/press_sources.yml").read_text(encoding="utf-8"))
        assert PW.DEFAULT_ACTIONS_CAP_USD == float(
            press["actions_wire"]["monthly_usd_cap"])


# ---------------------------------------------------------------------------
# 11. m4 — one clock decides the spend month
# ---------------------------------------------------------------------------

class TestSpendMonthIsSingleSourced:
    def test_a_month_end_tick_books_into_the_run_ts_month(self, monkeypatch):
        """The wire derives the month from its run `ts` (seeding the counter and
        folding the delta); the provider used to re-read `datetime.now` for the
        same decision. A tick that straddles midnight on the last of the month
        therefore booked spend into a bucket the fold never reads — money spent,
        counter untouched.

        THE MODULE CLOCK IS FORCED INTO A DIFFERENT MONTH than the run `ts`, so
        the assertion discriminates on any calendar day. Pinning only a
        month-end fixture would pass under the defect for eleven months of the
        year (memory: fixture-date-plus-wall-clock-gate-bomb).
        """
        ts = datetime(2026, 7, 31, 23, 59, 30, tzinfo=timezone.utc)
        wall = datetime(2026, 8, 1, 0, 0, 30, tzinfo=timezone.utc)

        class _FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return wall if tz is None else wall.astimezone(tz)

        monkeypatch.setattr(press_providers, "datetime", _FrozenDT)
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        prov = press_providers.TwitterApiIoProvider(
            {"handles": [{"handle": "DeItaone", "tier": "fast"}],
             "poll_tiers": {"fast": 1}},
            spend_cap_usd=50.0)
        monkeypatch.setattr(press_providers.TwitterApiIoProvider, "_request",
                            lambda self, key, handle: {"tweets": []})

        state: dict = {}
        prov.fetch(root=ROOT, session_state=state, offline=False, now=ts)

        spend = state["twitterapiio"]["spend"]
        assert PW.month_key(ts) != PW.month_key(wall), "fixture is degenerate"
        assert PW.month_key(ts) in spend, (
            f"the tick booked into {sorted(spend)} instead of {PW.month_key(ts)} "
            "— the provider re-read its own clock instead of the run's")
        assert PW.month_key(wall) not in spend
        assert float(spend[PW.month_key(ts)]["requests"]) == 1

    def test_the_wire_hands_the_provider_its_own_clock(self, tmp_path, monkeypatch):
        seen: dict = {}
        root = _stage_repo(tmp_path)
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        monkeypatch.setattr(breaking_feed, "poll_all", lambda r, c: [])

        def _spy(root_, cfg, state, *, offline=False, now=None):
            seen["now"] = now
            return []

        monkeypatch.setattr(press_providers, "poll_all", _spy)
        PW.run(root, now=NOW)
        assert seen["now"] == NOW


# ---------------------------------------------------------------------------
# 12. M11 — the two mechanisms the money depends on, pinned END TO END
#
# Both of these were UNPINNED: the suite exercised save_cursors directly and
# exercised the provider's parse, so deleting the lane's ONE call to
# save_cursors, or the per-handle interval check inside fetch(), left the whole
# file green. They are the same defect class as the B2 finding they follow from
# (cursors.json IS the budget): losing either turns a $46.60/mo lane into one
# that re-polls every handle on every five-minute run.
#
# Each test below is written so that removing the mechanism it names makes THIS
# test fail, not merely some assertion somewhere.
# ---------------------------------------------------------------------------

class TestM11StatePersistsEndToEnd:
    def _armed(self, monkeypatch):
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)

    def test_provider_state_survives_the_run_boundary(self, tmp_path, monkeypatch):
        """DELETE `save_cursors(...)` FROM `run()` AND THIS FAILS.

        Every run is a separate process on a fresh Actions checkout, so the only
        thing that carries the per-handle throttle and the spend counter from one
        run to the next is cursors.json. A run that polls and does not write it
        has spent money and remembered nothing.
        """
        root = _stage_repo(tmp_path)
        self._armed(monkeypatch)
        monkeypatch.setattr(breaking_feed, "poll_all", lambda r, c: [])
        handed: list[dict] = []

        def _poll(root_, cfg, state, *, offline=False, now=None):
            # What the real provider does to the state it is handed.
            handed.append(json.loads(json.dumps(state)))
            tw = state.setdefault("twitterapiio", {})
            tw.setdefault("last_poll", {})["realDonaldTrump"] = 1_800_000_000.0
            tw.setdefault("cursors", {})["realDonaldTrump"] = "1949"
            return []

        monkeypatch.setattr(press_providers, "poll_all", _poll)

        assert PW.run(root, now=NOW) == 0
        cursors_path = root / PW.CURSORS_REL
        assert cursors_path.exists(), "the run wrote no cursors.json at all"
        on_disk = json.loads(cursors_path.read_text(encoding="utf-8"))
        assert on_disk["providers"]["twitterapiio"]["cursors"] == {
            "realDonaldTrump": "1949"}
        assert on_disk["providers"]["twitterapiio"]["last_poll"] == {
            "realDonaldTrump": 1_800_000_000.0}

        # The round trip is the point: the NEXT run must be handed what the last
        # one learned, or the throttle it consults is empty every time.
        assert PW.run(root, now=NOW + timedelta(minutes=5)) == 0
        assert len(handed) == 2
        # `poll_all` is handed cursors["providers"], so the provider block is at
        # the top level of what the spy captured.
        second = handed[1].get("twitterapiio", {})
        assert second.get("last_poll") == {"realDonaldTrump": 1_800_000_000.0}, (
            "the second run started from an empty throttle — cursors.json did "
            "not survive the run boundary")
        assert second.get("cursors") == {"realDonaldTrump": "1949"}


class TestM11PerHandleCadenceGate:
    def _provider(self, monkeypatch, calls):
        prov = press_providers.TwitterApiIoProvider(
            {"handles": [{"handle": "realDonaldTrump", "tier": "fast"},
                         {"handle": "DeItaone", "tier": "fast"}],
             "poll_tiers": {"fast": 75}},
            spend_cap_usd=50.0)
        monkeypatch.setattr(
            press_providers.TwitterApiIoProvider, "_request",
            lambda self, key, handle: calls.append(handle) or {"tweets": []})
        return prov

    def test_a_second_poll_inside_the_interval_makes_no_request(
            self, monkeypatch):
        """DELETE THE `last_poll` INTERVAL CHECK IN `fetch()` AND THIS FAILS.

        The lane runs every five minutes and the tier interval is 75 seconds per
        handle, so without this gate a handle is re-requested on every run and
        the projected bill multiplies by the number of runs per interval. The
        gate is the reason the budget test in section 1 is arithmetic and not a
        wish.
        """
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        calls: list[str] = []
        prov = self._provider(monkeypatch, calls)
        state: dict = {}

        prov.fetch(root=ROOT, session_state=state, offline=False, now=NOW)
        assert sorted(calls) == ["DeItaone", "realDonaldTrump"], calls

        # Same tick's state, 30 seconds later: inside the 75s tier interval.
        calls.clear()
        prov.fetch(root=ROOT, session_state=state, offline=False,
                   now=NOW + timedelta(seconds=30))
        assert calls == [], (
            f"the per-handle interval gate did not hold: {calls} were re-polled "
            "inside their tier interval")

        # ...and the gate is a THROTTLE, not a mute: past the interval it polls.
        import time as _time
        monkeypatch.setattr(_time, "time",
                            lambda: state["twitterapiio"]["last_poll"][
                                "realDonaldTrump"] + 100.0)
        prov.fetch(root=ROOT, session_state=state, offline=False,
                   now=NOW + timedelta(seconds=100))
        assert sorted(calls) == ["DeItaone", "realDonaldTrump"], calls

    def test_the_throttle_it_consults_is_the_one_that_was_persisted(
            self, tmp_path, monkeypatch):
        """The two halves together, which is what the invoice actually depends
        on: run twice through `PW.run` with only the HTTP call stubbed, and the
        billed provider must make its requests once, not once per run."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "fake-key")
        root = _stage_repo(tmp_path, press_cfg={
            "satire_blocklist": [],
            "wire": {"flagship_top_k_per_day": 3, "flagship_salience_floor": 40.0},
            "x_follow": {"handles": [{"handle": "DeItaone", "tier": "fast"}],
                         "poll_tiers": {"fast": 75}},
            "spend": {"twitterapiio_monthly_cap_usd": 75.0},
            "actions_wire": {"monthly_usd_cap": 50.0},
        })
        monkeypatch.setenv(PW.ENV_OUTBOX_ENABLED, "1")
        monkeypatch.delenv(PW.ENV_DAEMON_ACTIVE, raising=False)
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        monkeypatch.setattr(breaking_feed, "poll_all", lambda r, c: [])
        # tmp_path is not a git checkout, so the B2 push preflight would stand
        # the billed tier down before it ever consults the throttle under test.
        monkeypatch.setattr(PW, "push_access_ok", lambda root_, **kw: (True, "test"))
        calls: list[str] = []
        monkeypatch.setattr(
            press_providers.TwitterApiIoProvider, "_request",
            lambda self, key, handle: calls.append(handle) or {"tweets": []})

        assert PW.run(root, now=NOW) == 0
        assert calls == ["DeItaone"], calls
        assert PW.run(root, now=NOW + timedelta(seconds=30)) == 0
        assert calls == ["DeItaone"], (
            f"the second run re-polled the handle inside its interval: {calls}")


class TestTheFloorAdmitsMoreThanOneEventClass:
    """The wire posted BEA prints and nothing else, for arithmetic reasons.

    wire.flagship_salience_floor was 70.0. Against breaking_relevance's taxonomy:

        macro_print  55 + official 15 = 70   <- clears, EXACTLY
        policy       50 + mirror   12 = 62   <- never
        geopolitical 40 + official 15 = 55   <- never
        company_news 30 + mirror   12 = 42   <- never

    A floor set at the exact ceiling of ONE class silently reduced a six-source
    news wire to an official-macro-print relay. The record matches: two items
    booked in the lane's whole life, both BEA prints (GDP advance estimate,
    personal income/outlays). Trump, the White House and every company story were
    excluded by construction — the pollers ran, scored, and could not clear the
    bar. A live tick now books a Truth Social policy post and a CNBC company
    story that were previously impossible.
    """

    def _floor(self):
        cfg = _live_press_cfg()
        return float(cfg["wire"]["flagship_salience_floor"])

    def test_more_than_one_event_class_can_reach_the_floor(self):
        from engine.marketing.breaking_relevance import _CLASS_TAXONOMY, _TIER_BONUS

        floor = self._floor()
        best_bonus = max(float(_TIER_BONUS.get(t, 0.0))
                         for t in ("mirror", "x_relay", "official", "wire"))
        reachable = [str(row[0]) for row in _CLASS_TAXONOMY
                     if float(row[1]) + best_bonus >= floor]
        assert len(reachable) >= 3, (
            f"only {reachable} can reach flagship_salience_floor={floor:g} — the "
            "floor is back at the ceiling of one class and the wire is a "
            "single-source relay again"
        )

    def test_a_trump_policy_post_from_the_mirror_can_clear_it(self):
        """The president's own post is direct-quote/mirror — the one item type
        this lane exists to carry — and it scores 62 at best."""
        from engine.marketing.breaking_relevance import _CLASS_TAXONOMY, _TIER_BONUS

        policy_base = next(float(row[1]) for row in _CLASS_TAXONOMY
                           if row[0] == "policy")
        assert policy_base + _TIER_BONUS["mirror"] >= self._floor()

    def test_a_company_story_can_clear_it(self):
        """"Apple drops 7%, Amazon surges 12% as investors pick AI winners" is a
        company_news item — worth 30 base, and previously unpostable."""
        from engine.marketing.breaking_relevance import _CLASS_TAXONOMY, _TIER_BONUS

        base = next(float(row[1]) for row in _CLASS_TAXONOMY
                    if row[0] == "company_news")
        assert base + _TIER_BONUS["wire"] >= self._floor()

    def test_volume_is_still_bounded_by_top_k_not_by_the_floor(self):
        """Lowering the floor cannot flood a desk: the per-desk daily budget is
        what caps volume, and the floor only decides WHICH items compete for
        those slots.

        THE ASSERTION USED TO BE `<= 3` AND THAT WAS A TIME BOMB. It pinned the
        value the floor PR happened to leave in place as proof that the floor PR
        raised no volume — but the budget is a volume cap, and W4d (masterplan
        §8.2) was chartered to raise exactly it on measured evidence. A test that
        pins the number a later ruling is expected to change does not guard the
        separation it was written for; it just fails the day the ruling lands and
        pressures the next reader to weaken something.

        What this test actually protects is the SEPARATION: the budget must stay
        a finite, positive, config-declared bound, and it must never be wide
        enough to hand the wire a desk's entire day (the ramp cap is the
        operator's declared daily volume, shared with the nightly ladder and the
        publish-time lanes). Both of those survive any value W4d chooses.
        """
        import yaml

        cfg = _live_press_cfg()
        mcfg = yaml.safe_load(
            (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
        from engine.marketing.press_lane import _resolve_top_k

        top_k = _resolve_top_k(mcfg.get("breaking"), cfg.get("wire"))
        assert isinstance(top_k, int) and top_k > 0, (
            "the wire budget must be a finite positive bound, not absent or 0")
        ramp_cap = (((mcfg.get("sentinel") or {}).get("ramp") or {})
                    .get("account_overrides", {}).get("flagship", {})
                    .get("max_posts_per_account_per_day"))
        assert isinstance(ramp_cap, int) and top_k < ramp_cap, (
            f"per-desk wire budget {top_k} is not below flagship's {ramp_cap}/day "
            f"ramp cap — the wire would be licensed to spend a desk's whole day "
            f"and leave the nightly ladder nowhere to post")

    def test_unclassified_noise_still_does_not_clear_it(self):
        """A live tick scores its `none`-class rows at 4.8-7.2. The floor must
        stay well above that band or the wire starts relaying anything."""
        assert self._floor() >= 20.0


class TestPolicyNeedsAMarketNexus:
    """Lowering the floor 70 -> 30 opened the `policy` class on salience alone.

    The floor change was right: at 70 only `macro_print + official` could ever
    clear (55 + 15, exactly), so the wire was a BEA-print relay. But a floor is
    a proxy for "worth posting", not for "about markets", and `policy` is base
    50 — it clears 30 on class alone, whatever the item actually says.

    Measured on the 2026-07-31 dry run off the fix branch: three items booked to
    the FLAGSHIP account, two of them real market news (Apple/Amazon earnings,
    Reddit on Google's AI Overviews) and one a Truth Social post about the
    Supreme Court's "Money and Prestige". There is exactly one emit path in
    press_lane and it is gated on `salience >= floor`, so that item scored above
    30 and could never have cleared 70 — the floor change admitted it.

    HONEST LIMIT ON THIS GUARD: the live item's headline was 452 characters (the
    run logged "headline prefix dropped (452 > 280)") and the dry run wrote no
    state, so its exact text is not recoverable. Scoring the truncated headline
    puts it at 9.0 in class `none` — below the floor — which does NOT reproduce
    the booking. So this rule is aimed at the CLASS of defect the floor change
    created, and is pinned on constructed items below rather than on a replay of
    the live one.

    The separating signal was already computed and thrown away: `matched`.
    """

    def test_a_policy_item_matching_nothing_is_refused(self):
        from engine.marketing.press_lane import _no_market_nexus

        assert _no_market_nexus({
            "event_class": "policy", "salience": 46.5,
            "matched": {"tickers": [], "sectors": [], "macro_keys": []},
        })

    def test_any_single_match_is_enough(self):
        """One connection to a market is the whole bar — this is not a quality
        gate, it is a topicality gate."""
        from engine.marketing.press_lane import _no_market_nexus

        for key, val in (("tickers", ["NVDA"]), ("sectors", ["technology"]),
                         ("macro_keys", ["tariffs"])):
            m = {"tickers": [], "sectors": [], "macro_keys": []}
            m[key] = val
            assert not _no_market_nexus({"event_class": "policy", "matched": m}), key

    def test_geopolitical_is_deliberately_exempt(self):
        """"Israel and Iran agree to ceasefire after two weeks of strikes"
        scores 36.0 and matches NO ticker, sector or macro key — and is one of
        the most market-moving headlines a wire can carry. An earlier draft of
        this rule included geopolitical and blocked exactly that story."""
        from engine.marketing.press_lane import _no_market_nexus

        assert not _no_market_nexus({
            "event_class": "geopolitical", "salience": 36.0,
            "matched": {"tickers": [], "sectors": [], "macro_keys": []},
        })

    def test_company_news_and_macro_prints_are_never_touched(self):
        """Both are about markets by construction. A company story whose name
        the ticker universe happens not to carry must still ship."""
        from engine.marketing.press_lane import _no_market_nexus

        for cls in ("company_news", "macro_print", "none", ""):
            assert not _no_market_nexus({
                "event_class": cls,
                "matched": {"tickers": [], "sectors": [], "macro_keys": []},
            }), cls

    def test_the_real_headlines_this_lane_exists_for_still_post(self):
        """End-to-end against the live scorer, not hand-made verdicts.

        Every one of these is a headline the wire SHOULD carry, and each is a
        policy-class item that would be blocked by a naive "politics is banned"
        rule. They pass because each one genuinely touches a market.
        """
        import yaml
        from pathlib import Path
        from engine.marketing.breaking_relevance import score_item
        from engine.marketing.press_lane import _no_market_nexus

        root = Path(__file__).resolve().parent.parent
        cfg = (yaml.safe_load((root / "config/marketing.yml").read_text()) or {})
        bc = cfg.get("breaking", {})
        for headline in (
            "Trump announces 50% tariff on Chinese semiconductors",
            "White House announces new export controls on advanced chips to China",
            "Treasury sanctions Russian oil shipping network",
        ):
            s = score_item({"headline": headline, "body_snippet": "",
                            "source_tier": "mirror", "url": "http://x",
                            "published_at": "2026-07-31T15:00:00Z"},
                           cfg=bc, root=root)
            assert s["event_class"] == "policy", (headline, s["event_class"])
            assert s["salience"] >= 30.0, (headline, s["salience"])
            assert not _no_market_nexus(s), (
                f"{headline!r} is the reason this lane exists and the nexus rule "
                f"would drop it; matched={s['matched']}")
