"""XS push lane (engine/marketing/press_stream.py) — rule construction, event
normalization parity with the REST lane, spool round-trip, rule sync
convergence, daemon drain wiring, and the shipped-config pins.

No test here touches the network or the websocket: chunk/normalize/spool are
pure or tmp_path-local, and sync_rules is exercised against a recorded fake
transport. The websockets lib is deliberately NOT imported — CI packs may not
carry it, and the listener degrades to nothing by design.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import press_stream as ps  # noqa: E402


def _cfg(handles: list[dict], **over) -> dict:
    cfg = {
        "enabled": True,
        "rule_tag_prefix": "mmx-press",
        "tier_intervals_s": {"fast": 5, "mid": 30, "slow": 120},
        "handles": handles,
    }
    cfg.update(over)
    return cfg


def _tweet(tid: str, handle: str, text: str) -> dict:
    return {"id": tid, "text": text, "createdAt": "2026-08-03T12:00:00Z",
            "author": {"userName": handle}}


# ─────────────────────────────────────────────────────────────────────────────
# chunk_rules
# ─────────────────────────────────────────────────────────────────────────────

class TestChunkRules:
    def test_groups_by_tier_with_config_intervals(self):
        rules = ps.chunk_rules(_cfg([
            {"handle": "A", "tier": "fast"},
            {"handle": "B", "tier": "fast"},
            {"handle": "C", "tier": "slow"},
        ]))
        by_tag = {r["tag"]: r for r in rules}
        assert by_tag["mmx-press-fast-1"]["value"] == "from:A OR from:B"
        assert by_tag["mmx-press-fast-1"]["interval_seconds"] == 5.0
        assert by_tag["mmx-press-slow-1"]["value"] == "from:C"
        assert by_tag["mmx-press-slow-1"]["interval_seconds"] == 120.0

    def test_255_char_value_cap_forces_chunking(self):
        handles = [{"handle": f"account_{i:02d}_padded_to_be_long", "tier": "mid"}
                   for i in range(30)]
        rules = ps.chunk_rules(_cfg(handles))
        assert len(rules) > 1
        for rule in rules:
            assert len(rule["value"]) <= 255
        # Every handle survives the chunking exactly once.
        clauses = " OR ".join(r["value"] for r in rules).split(" OR ")
        assert len(clauses) == 30 and len(set(clauses)) == 30

    def test_satire_never_reaches_a_rule(self):
        rules = ps.chunk_rules(
            _cfg([{"handle": "RealDesk", "tier": "fast"},
                  {"handle": "HalfwayPost", "tier": "fast"}]),
            satire_blocklist=["HalfwayPost"],
        )
        assert all("HalfwayPost" not in r["value"] for r in rules)

    def test_deterministic_across_calls(self):
        cfg = _cfg([{"handle": "A", "tier": "fast"},
                    {"handle": "B", "tier": "mid"}])
        assert ps.chunk_rules(cfg) == ps.chunk_rules(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# normalize_event — REST-lane parity is the contract
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeEvent:
    REG = {"deitaone": {"handle": "DeItaone", "tier": "fast",
                        "corroboration_class": "hearsay"},
           "rawsalerts": {"handle": "rawsalerts", "tier": "mid",
                          "corroboration_class": "hearsay",
                          "strict_corroboration": True,
                          "route": "wire"}}

    def test_shapes_top_level_nested_single_and_bare(self):
        tw = _tweet("100", "DeItaone", "CPI PRINTS 2.9%")
        for payload in ({"tweets": [tw]},
                        {"data": {"tweets": [tw]}},
                        {"tweet": tw},
                        tw):
            items = ps.normalize_event(payload, self.REG)
            assert len(items) == 1, payload
            assert items[0]["headline"] == "CPI PRINTS 2.9%"

    def test_output_matches_rest_lane_for_the_same_tweet(self):
        """A pushed tweet and a polled tweet must be the SAME item downstream —
        ids, source keys and corroboration flags all byte-equal, or the shared
        seen-ledger would double-ingest whatever both transports saw."""
        from engine.marketing.press_providers import TwitterApiIoProvider
        handle_cfg = {"handle": "DeItaone", "corroboration_class": "hearsay"}
        prov = TwitterApiIoProvider({"handles": [handle_cfg]}, spend_cap_usd=75.0)
        rest_items, _ = prov.parse_tweets(
            {"tweets": [_tweet("42", "DeItaone", "FED HOLDS RATES")]},
            handle_cfg, since_id=None)
        push_items = ps.normalize_event(
            {"tweets": [_tweet("42", "DeItaone", "FED HOLDS RATES")]}, self.REG)
        assert len(rest_items) == 1 and len(push_items) == 1
        for key in ("id", "source", "source_name", "source_tier", "url",
                    "headline", "body_snippet", "corroboration_class"):
            assert push_items[0][key] == rest_items[0][key], key

    def test_register_gate_drops_unknown_handles(self):
        items = ps.normalize_event(
            {"tweets": [_tweet("7", "SomeRandomAcct", "hello")]}, self.REG)
        assert items == []

    def test_strict_and_route_flags_carried(self):
        items = ps.normalize_event(
            {"tweets": [_tweet("8", "rawsalerts", "BREAKING: thing")]}, self.REG)
        assert items[0]["strict_corroboration"] is True
        assert items[0]["route"] == "wire"

    def test_satire_dropped_even_when_registered(self):
        reg = {"halfwaypost": {"handle": "HalfwayPost", "tier": "fast"}}
        items = ps.normalize_event(
            {"tweets": [_tweet("9", "HalfwayPost", "satire")]},
            reg, satire={"halfwaypost"})
        assert items == []

    def test_garbage_payloads_yield_empty(self):
        for payload in (None, [], "x", {"unrelated": 1}, {"tweets": "nope"}):
            assert ps.normalize_event(payload, self.REG) == []


# ─────────────────────────────────────────────────────────────────────────────
# Spool
# ─────────────────────────────────────────────────────────────────────────────

class TestSpool:
    def test_round_trip_dedupes_and_truncates(self, tmp_path):
        items = [{"id": "a", "headline": "one"},
                 {"id": "b", "headline": "two"},
                 {"id": "a", "headline": "one again"}]
        assert ps.append_spool(tmp_path, items) == 3
        drained = ps.drain_spool(tmp_path)
        assert [i["id"] for i in drained] == ["a", "b"]
        # Drain truncates: a second drain sees nothing.
        assert ps.drain_spool(tmp_path) == []

    def test_missing_spool_is_empty(self, tmp_path):
        assert ps.drain_spool(tmp_path) == []

    def test_corrupt_lines_are_skipped_not_fatal(self, tmp_path):
        spool = tmp_path / "data" / "marketing" / "press" / "stream_spool.jsonl"
        spool.parent.mkdir(parents=True)
        spool.write_text('{"id": "ok"}\nnot-json\n[]\n', encoding="utf-8")
        assert [i["id"] for i in ps.drain_spool(tmp_path)] == ["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# sync_rules against a recorded fake transport
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncRules:
    def _record(self, monkeypatch, remote_rules):
        calls: list[tuple[str, dict | None]] = []

        def fake_request(cfg, path, payload=None):
            calls.append((path, payload))
            if path.endswith("get_rules"):
                return {"rules": remote_rules, "status": "success"}
            if path.endswith("add_rule"):
                return {"rule_id": f"rid-{len(calls)}", "status": "success"}
            return {"status": "success"}

        monkeypatch.setattr(ps, "_rules_request", fake_request)
        return calls

    def test_creates_and_activates_missing_rules(self, monkeypatch):
        calls = self._record(monkeypatch, [])
        report = ps.sync_rules(_cfg([{"handle": "A", "tier": "fast"}]))
        assert report["created"] == ["mmx-press-fast-1"]
        adds = [p for p, body in calls if p.endswith("add_rule")]
        activates = [body for p, body in calls
                     if p.endswith("update_rule") and body and body.get("is_effect") == 1]
        assert len(adds) == 1 and len(activates) == 1

    def test_updates_drifted_and_reactivates_dark_rules(self, monkeypatch):
        remote = [{"rule_id": "r1", "tag": "mmx-press-fast-1",
                   "value": "from:OLD", "interval_seconds": 5, "is_effect": 1},
                  {"rule_id": "r2", "tag": "mmx-press-mid-1",
                   "value": "from:B", "interval_seconds": 30, "is_effect": 0}]
        self._record(monkeypatch, remote)
        report = ps.sync_rules(_cfg([{"handle": "A", "tier": "fast"},
                                     {"handle": "B", "tier": "mid"}]))
        assert sorted(report["updated"]) == ["mmx-press-fast-1", "mmx-press-mid-1"]

    def test_unchanged_rules_are_not_rewritten(self, monkeypatch):
        remote = [{"rule_id": "r1", "tag": "mmx-press-fast-1",
                   "value": "from:A", "interval_seconds": 5, "is_effect": 1}]
        calls = self._record(monkeypatch, remote)
        report = ps.sync_rules(_cfg([{"handle": "A", "tier": "fast"}]))
        assert report["unchanged"] == ["mmx-press-fast-1"]
        assert not [p for p, _ in calls if p.endswith("update_rule")]

    def test_stale_prefixed_rules_deleted_foreign_rules_untouched(self, monkeypatch):
        remote = [{"rule_id": "r9", "tag": "mmx-press-mid-9",
                   "value": "from:GONE", "interval_seconds": 30, "is_effect": 1},
                  {"rule_id": "rX", "tag": "someone-else",
                   "value": "from:other", "interval_seconds": 60, "is_effect": 1}]
        calls = self._record(monkeypatch, remote)
        report = ps.sync_rules(_cfg([{"handle": "A", "tier": "fast"}]))
        assert report["deleted"] == ["mmx-press-mid-9"]
        deletes = [body for p, body in calls if p.endswith("delete_rule")]
        assert deletes == [{"rule_id": "r9"}]

    def test_deactivate_only_flips_is_effect_and_deletes_nothing(self, monkeypatch):
        remote = [{"rule_id": "r1", "tag": "mmx-press-fast-1",
                   "value": "from:A", "interval_seconds": 5, "is_effect": 1}]
        calls = self._record(monkeypatch, remote)
        report = ps.sync_rules(_cfg([{"handle": "A", "tier": "fast"}]),
                               deactivate_only=True)
        assert report["deactivated"] == ["mmx-press-fast-1"]
        assert not [p for p, _ in calls if p.endswith("delete_rule")]
        offs = [body for p, body in calls
                if p.endswith("update_rule") and body]
        assert offs and all(b.get("is_effect") == 0 for b in offs)


# ─────────────────────────────────────────────────────────────────────────────
# Daemon drain wiring
# ─────────────────────────────────────────────────────────────────────────────

class TestDaemonDrain:
    def _daemon(self):
        import importlib
        return importlib.import_module("scripts.marketing_fastlane_daemon")

    def _stub(self, monkeypatch, tmp_path, *, drained: list[dict]):
        d = self._daemon()
        import engine.marketing.breaking_feed as bf
        import engine.marketing.intelligence_desk as idesk
        import engine.marketing.press_lane as pl
        import engine.marketing.press_providers as pp
        import engine.marketing.press_stream as pstream
        monkeypatch.setattr(d, "ROOT", tmp_path)
        monkeypatch.setattr(d, "_PRESS_STATE_PATH", tmp_path / "press" / "state.json")
        monkeypatch.setattr(d, "_PRESS_SEEN_PATH", tmp_path / "press" / "seen.json")
        monkeypatch.setattr(d, "_load_yaml", lambda p: {})
        monkeypatch.setattr(bf, "poll_all", lambda root, cfg: [])
        monkeypatch.setattr(pp, "poll_all",
                            lambda root, cfg, state, *, offline=False, now=None: [])
        monkeypatch.setattr(idesk, "update_intelligence_desk",
                            lambda *a, **k: {"health": {}})
        drain_calls: list = []

        def fake_drain(root):
            drain_calls.append(root)
            return list(drained)

        monkeypatch.setattr(pstream, "drain_spool", fake_drain)
        seen_items: dict = {}

        def fake_tick(items, **kwargs):
            seen_items["items"] = list(items)
            return {"emitted": [], "skipped": [], "digest": [], "blocked": [],
                    "rail": [], "_rail_order": {}, "intelligence": [],
                    "_seen": [], "_emit_allowed": False}

        monkeypatch.setattr(pl, "run_press_tick", fake_tick)
        return d, drain_calls, seen_items

    def test_live_tick_feeds_stream_items_through_the_pipeline(
            self, monkeypatch, tmp_path):
        item = {"id": "x1", "source": "x_DeItaone", "headline": "h"}
        d, drain_calls, seen = self._stub(monkeypatch, tmp_path, drained=[item])
        d._run_press_tick(dry_run=False)
        assert drain_calls, "live tick must drain the stream spool"
        assert item in seen["items"]

    def test_dry_run_never_drains(self, monkeypatch, tmp_path):
        d, drain_calls, _ = self._stub(monkeypatch, tmp_path, drained=[])
        d._run_press_tick(dry_run=True)
        assert drain_calls == [], "a dry-run drain would consume items " \
                                  "the next live tick was owed"


# ─────────────────────────────────────────────────────────────────────────────
# Shipped config pins
# ─────────────────────────────────────────────────────────────────────────────

class TestShippedConfig:
    def _cfg(self):
        import yaml
        return yaml.safe_load(
            (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))

    def test_stream_on_poll_off(self):
        cfg = self._cfg()
        # Operator 2026-08-03: push lane ON (billing scales with news),
        # hot-poll lane OFF (billing scaled with the clock). BOTH pins in one
        # test because flipping either back is the same money decision.
        assert cfg["x_stream"]["enabled"] is True
        assert cfg["x_follow"]["enabled"] is False

    def test_register_carries_v1_and_v2_handles(self):
        cfg = self._cfg()
        handles = {h["handle"] for h in cfg["x_stream"]["handles"]}
        # v1 spine survives the transport change…
        assert {"DeItaone", "FirstSquawk", "financialjuice", "zerohedge",
                "WHPressPool", "unusual_whales", "CoinDesk"} <= handles
        # …and the v2 robustness additions the operator asked for are present.
        assert {"NickTimiraos", "Newsquawk", "BNONews", "KobeissiLetter",
                "WuBlockchain"} <= handles
        assert len(handles) >= 25

    def test_osint_additions_are_strict(self):
        cfg = self._cfg()
        rows = {h["handle"]: h for h in cfg["x_stream"]["handles"]}
        for osint in ("Faytuks", "sentdefender", "rawsalerts", "BRICSinfo"):
            assert rows[osint].get("strict_corroboration") is True, osint

    def test_rules_fit_the_vendor_value_cap(self):
        cfg = self._cfg()
        rules = ps.chunk_rules(cfg["x_stream"],
                               satire_blocklist=cfg.get("satire_blocklist") or [])
        assert rules, "shipped register must produce at least one rule"
        for rule in rules:
            assert len(rule["value"]) <= 255
            assert 0.1 <= float(rule["interval_seconds"]) <= 86400
