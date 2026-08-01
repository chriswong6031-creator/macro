"""tests/test_marketing_press_copy.py — PRESS-FEEDS B2-COPY + B4a acceptance tests.

D05 Addendum 2 §3 (copy law), §6 (registers + B4a site sink), §7 (B2-COPY charter).

Fixture-driven; ZERO live network, ZERO live LLM. MARKETING_LLM_ENABLED /
MARKETING_PUBLISH_ENABLED never set here (the summarizer's env gate keeps every
run on the deterministic path). Import closure is stdlib + pyyaml — the thin
marketing-engine CI lane (pytest + pyyaml, no pandas) must stay green, so any
heavy top-level import in engine/marketing/wire_* or tape_stamp turns this red at
collection.

Covers:
  1. Opener determinism + no-repeat window + not-a-fixed-template.
  2. Register derivation (deterministic from event_class + route + corroboration).
  3. Format-picker matrix + wire_deep length-budget enforcement.
  4. AI-tell rejection on a seeded "delve into the ever-evolving landscape".
  5. Tape-stamp four cases: moved / quiet / missing / stale.
  6. Model tiering (sonnet flagship / haiku volume) + deterministic keyless path.
  7. wires.json rail: shape / atomicity / rail-floor / eligibility (incl. digest).
  8. site_access classification present (/live/wires.json is free_registered).
  9. Deterministic fallback proof: full press tick emits keyless with voice on.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import wire_format as wf  # noqa: E402
from engine.marketing import wire_voice as wv  # noqa: E402
from engine.marketing import tape_stamp as ts  # noqa: E402
from engine.marketing.press_lane import run_press_tick  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 1. Opener determinism + no-repeat window + not-a-fixed-template
# ─────────────────────────────────────────────────────────────────────────────

class TestOpeners:
    def _item(self, iid: str, ec: str = "policy", corr: str = "direct-quote") -> dict:
        return {"id": iid, "headline": "Trump says trade talks", "body_snippet": "talks",
                "event_class": ec, "corroboration_class": corr, "salience": 60.0,
                "matched": {"tickers": []}}

    def test_deterministic_same_id_same_opener(self):
        # Same id + same recent state => same opener, every call.
        it = self._item("trumpstruth:42")
        o1, _ = wv.select_opener(it, account="flagship", recent_openers=[])
        o2, _ = wv.select_opener(it, account="flagship", recent_openers=[])
        assert o1 == o2

    def test_no_repeat_window(self):
        # Two consecutive items on the same account never share the opener.
        recent: list[str] = []
        openers = []
        for i in range(6):
            it = self._item(f"trumpstruth:{i}")
            o, _ = wv.select_opener(it, account="flagship", recent_openers=recent)
            recent.append(o)
            openers.append(o)
        # No two ADJACENT openers are equal.
        for a, b in zip(openers, openers[1:]):
            assert a != b, f"adjacent repeat: {a!r}"

    def test_not_a_fixed_template(self):
        # Across many distinct items, more than one distinct opener is used (the
        # rotating pool is real, not a single hard-coded phrase).
        seen = set()
        recent: list[str] = []
        for i in range(12):
            it = self._item(f"x:{i}")
            o, _ = wv.select_opener(it, account="flagship", recent_openers=recent)
            recent.append(o)
            seen.add(o)
        assert len(seen) >= 3

    def test_direct_quote_may_lead_with_speaker(self):
        # The empty-string opener ("summary leads, no hook") is a member of the
        # people-register pool, so a direct quote CAN lead without a manufactured
        # hook — the pool contains "".
        assert "" in wv._OPENERS_DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# 2. Register derivation (deterministic)
# ─────────────────────────────────────────────────────────────────────────────

class TestRegister:
    def test_geopolitical_is_topics(self):
        assert wv.derive_register({"event_class": "geopolitical", "matched": {}}) == "topics"

    def test_brief_candidates_route(self):
        assert wv.derive_register(
            {"event_class": "geopolitical", "route": "brief_candidates", "matched": {}}
        ) == "brief_candidates"

    def test_crypto_keyword(self):
        assert wv.derive_register(
            {"event_class": "none", "headline": "Bitcoin surges", "matched": {}}
        ) == "crypto"

    def test_company_news(self):
        assert wv.derive_register(
            {"event_class": "company_news", "matched": {}}
        ) == "companies"

    def test_direct_quote_is_people(self):
        assert wv.derive_register(
            {"event_class": "policy", "corroboration_class": "direct-quote", "matched": {}}
        ) == "people"

    def test_default_markets(self):
        assert wv.derive_register(
            {"event_class": "none", "corroboration_class": "hearsay", "matched": {},
             "headline": "some flash", "body_snippet": ""}
        ) == "markets"

    def test_company_news_beats_crypto_ticker(self):
        # m1 (opus review): a "COIN earnings" item is company_news, NOT crypto —
        # company_news precedence wins even though COIN is a crypto-adjacent ticker.
        assert wv.derive_register({
            "event_class": "company_news",
            "headline": "Coinbase (COIN) beats on Q2 earnings",
            "body_snippet": "Revenue rose", "matched": {"tickers": ["COIN"]},
        }) == "companies"

    def test_crypto_ticker_without_company_news_is_crypto(self):
        # The other direction: the SAME crypto ticker with NO company_news
        # classification stays in the crypto register (register reserved for
        # non-equity crypto items — here a keyword/ticker crypto item).
        assert wv.derive_register({
            "event_class": "none",
            "headline": "MSTR adds to its bitcoin holdings",
            "body_snippet": "", "matched": {"tickers": ["MSTR"]},
        }) == "crypto"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Format-picker matrix + wire_deep length-budget enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatPicker:
    def test_flash_default_low_salience(self):
        it = {"event_class": "geopolitical", "salience": 50.0,
              "headline": "x" * 300, "body_snippet": "", "matched": {}}
        assert wf.pick_format(it)["format"] == "flash"  # below deep salience floor

    def test_flash_ineligible_register(self):
        # people register is never deep-eligible regardless of salience/body.
        it = {"event_class": "policy", "corroboration_class": "direct-quote",
              "salience": 99.0, "headline": "x" * 400, "body_snippet": "y" * 200,
              "matched": {}}
        assert wf.pick_format(it)["format"] == "flash"

    def test_flash_thin_source(self):
        # Deep-eligible register + high salience but a THIN source => flash (a thin
        # source cannot honestly fill two paragraphs).
        it = {"event_class": "geopolitical", "salience": 90.0,
              "headline": "short", "body_snippet": "", "matched": {}}
        assert wf.pick_format(it)["format"] == "flash"

    def test_wire_deep_eligible(self):
        it = {"event_class": "geopolitical", "salience": 90.0,
              "headline": "x" * 200, "body_snippet": "y" * 100, "matched": {}}
        assert wf.pick_format(it)["format"] == "wire_deep"

    def test_flash_length_budget(self):
        assert wf.validate_length("A short flash. Second sentence.", "flash") == []
        over = "x" * 300
        assert any("chars" in v for v in wf.validate_length(over, "flash"))
        three = "One. Two. Three."
        assert any("sentences" in v for v in wf.validate_length(three, "flash"))

    def test_wire_deep_length_budget(self):
        good = "x" * 500
        assert wf.validate_length(good, "wire_deep") == []
        too_long = "x" * 800
        assert any("max" in v for v in wf.validate_length(too_long, "wire_deep"))
        too_short = "x" * 100
        assert any("min" in v for v in wf.validate_length(too_short, "wire_deep"))


# ─────────────────────────────────────────────────────────────────────────────
# 4. AI-tell rejection (imported lexicon, not forked)
# ─────────────────────────────────────────────────────────────────────────────

class TestAITells:
    def test_delve_ever_evolving_rejected(self):
        # Both seeded tells present verbatim per config/press.yml ("delve" and the
        # full phrase "in the ever-evolving landscape").
        hits = wv.ai_tell_hits("Let us delve in the ever-evolving landscape of trade.")
        assert hits, "seeded AI-tell phrases must be caught"
        joined = " ".join(hits)
        assert "delve" in joined
        assert "ever-evolving landscape" in joined

    def test_clean_prose_passes(self):
        assert wv.ai_tell_hits("China tariffs rise sharply, the White House said.") == []

    def test_moreover_opener_rejected(self):
        assert any("Moreover" in h for h in wv.ai_tell_hits("Moreover, the deal collapsed."))

    def test_lexicon_sourced_from_press_yml(self):
        # The list is loaded from config/press.yml validators.ai_tell_phrases, not a
        # duplicated in-module copy (house law: import, never fork).
        phrases = wv._load_ai_tell_phrases()
        press_yml = yaml.safe_load((ROOT / "config" / "press.yml").read_text())
        expected = (press_yml.get("validators") or {}).get("ai_tell_phrases") or []
        assert phrases == [str(p) for p in expected]
        assert phrases, "press.yml must supply the AI-tell phrases"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tape-stamp four cases: moved / quiet / missing / stale
# ─────────────────────────────────────────────────────────────────────────────

class TestTapeStamp:
    def _now(self) -> datetime:
        return datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)

    def _fresh_ms(self) -> int:
        return int(self._now().timestamp() * 1000)  # now, in ms

    def _oil_item(self) -> dict:
        return {"headline": "Oil spikes on Hormuz strike", "body_snippet": "WTI crude jumps",
                "matched": {"tickers": []}}

    def test_moved(self):
        quotes = {"ts": self._fresh_ms(),
                  "quotes": {"CL=F": {"changePct": -1.8, "ts": self._fresh_ms()}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["reason"] == "moved"
        assert out["stamp"] == "WTI -1.8%"

    def test_quiet(self):
        quotes = {"ts": self._fresh_ms(),
                  "quotes": {"CL=F": {"changePct": 0.1, "ts": self._fresh_ms()}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["stamp"] == ""
        assert out["reason"] == "quiet_or_stale"

    def test_missing(self):
        # No CL=F in the store at all -> no stamp, reason symbol_absent.
        quotes = {"ts": self._fresh_ms(),
                  "quotes": {"SPY": {"changePct": 2.0, "ts": self._fresh_ms()}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["stamp"] == ""
        assert out["reason"] == "symbol_absent"

    def test_stale(self):
        # A quote 2 hours old is past the 30-min staleness bound -> no stamp.
        old_ms = int((self._now() - timedelta(hours=2)).timestamp() * 1000)
        quotes = {"ts": old_ms, "quotes": {"CL=F": {"changePct": -1.8, "ts": old_ms}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["stamp"] == ""
        assert out["reason"] == "quiet_or_stale"

    def test_no_store(self):
        assert ts.compute_stamp(self._oil_item(), None, now=self._now())["reason"] == "no_store"

    def test_no_mapping(self):
        item = {"headline": "Some unrelated flash", "body_snippet": "", "matched": {}}
        quotes = {"ts": self._fresh_ms(), "quotes": {"CL=F": {"changePct": -1.8, "ts": self._fresh_ms()}}}
        assert ts.compute_stamp(item, quotes, now=self._now())["reason"] == "no_mapping"

    def test_entity_map_ticker_precedence(self):
        # A matched SPY ticker maps to SPY before an entity keyword.
        item = {"headline": "market flash", "body_snippet": "", "matched": {"tickers": ["SPY"]}}
        assert "SPY" in ts.map_entities(item)

    def test_future_skew_clamp(self):
        # m3 (opus review): a quote timestamped far in the FUTURE (clock skew /
        # corrupt feed) is NOT fresh -> no stamp (fail-closed). Previously any
        # future-dated quote passed as fresh.
        future_ms = int((self._now() + timedelta(minutes=10)).timestamp() * 1000)
        quotes = {"ts": future_ms,
                  "quotes": {"CL=F": {"changePct": -1.8, "ts": future_ms}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["stamp"] == ""
        assert out["reason"] == "quiet_or_stale"

    def test_benign_future_skew_within_tolerance_is_fresh(self):
        # Sub-tolerance future skew (default 120s) is still fresh -> a valid move
        # earns its stamp. 30s ahead is inside the benign window.
        near_ms = int((self._now() + timedelta(seconds=30)).timestamp() * 1000)
        quotes = {"ts": near_ms,
                  "quotes": {"CL=F": {"changePct": -1.8, "ts": near_ms}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now())
        assert out["reason"] == "moved"
        assert out["stamp"] == "WTI -1.8%"

    def test_future_skew_tolerance_configurable(self):
        # The clamp tolerance is config-driven; a tighter tolerance rejects a skew
        # the default would admit.
        skew_ms = int((self._now() + timedelta(seconds=90)).timestamp() * 1000)
        quotes = {"ts": skew_ms,
                  "quotes": {"CL=F": {"changePct": -1.8, "ts": skew_ms}}}
        out = ts.compute_stamp(self._oil_item(), quotes, now=self._now(),
                               cfg={"future_skew_tolerance_s": 30})
        assert out["stamp"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 6. Model tiering + deterministic keyless path
# ─────────────────────────────────────────────────────────────────────────────

class TestModelTier:
    _CFG = {"llm_tier_salience_floor": 80.0,
            "llm_tier_flagship": "marketing_copy", "llm_tier_volume": "press_brief"}

    def test_flagship_above_floor(self):
        assert wv.resolve_llm_tier({"salience": 90.0}, cfg=self._CFG) == "flagship"
        assert wv.resolve_model_key({"salience": 90.0}, cfg=self._CFG) == "marketing_copy"

    def test_volume_below_floor(self):
        assert wv.resolve_llm_tier({"salience": 50.0}, cfg=self._CFG) == "volume"
        assert wv.resolve_model_key({"salience": 50.0}, cfg=self._CFG) == "press_brief"

    def test_summarize_item_keyless_deterministic(self):
        # With no LLM env armed, summarize_item(wire=...) still lands on the
        # deterministic fallback — the wire path never forces an LLM call.
        from engine.marketing.breaking_summary import summarize_item
        item = {"headline": "Retail sales unchanged", "source_name": "MarketWatch",
                "salience": 90.0}
        out = summarize_item(item, {"breaking": {"llm": {"enabled": True}}},
                             wire={"llm_tier_salience_floor": 80.0})
        assert out["mode"] == "deterministic"
        # B1: the source clause joins on a DOUBLE HYPHEN. An em dash here is what
        # the publisher's language gate quarantines, and the deterministic summary
        # is exactly the body a keyless run ships.
        assert out["summary"] == "Retail sales unchanged -- MarketWatch"


# ─────────────────────────────────────────────────────────────────────────────
# 7. wires.json rail: shape / atomicity / rail-floor / eligibility
# ─────────────────────────────────────────────────────────────────────────────

def _emitting_items() -> list[dict]:
    """Fixture batch: a strong direct-quote (emits), a weak item (rail-only)."""
    return [
        # Direct-quote, mirror tier, two ticker matches ($AAPL $NVDA) + two policy
        # keywords -> salience clears the flagship floor (base 45 + kw 10 + ticker
        # 20 = 75 in market hours); corroboration_decision = instant (single
        # primary OK for a mirror-verified own post).
        {"id": "trumpstruth:strong", "source": "trumpstruth",
         "source_name": "Truth Social (via trumpstruth.org)", "source_tier": "mirror",
         "url": "u1", "published_at": "2026-07-27T13:59:00Z",
         "headline": "Trump orders new tariff and export controls on $AAPL and $NVDA",
         "body_snippet": "The president said tariffs and export controls on $AAPL and $NVDA rise.",
         "truth_status_id": "strong", "corroboration_class": "direct-quote"},
        # Weak macro item -> below the post floor but above the rail floor.
        {"id": "x:tradfi:weak", "source": "x_tradfi", "source_name": "@tradfi",
         "source_tier": "x_relay", "url": "u2", "published_at": "2026-07-27T13:58:00Z",
         "headline": "Retail sales unchanged in latest print",
         "body_snippet": "Monthly retail figures flat.", "x_handle": "tradfi",
         "corroboration_class": "hearsay"},
    ]


class TestRail:
    def _run(self, dry_run=True):
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        state: dict = {}
        result = run_press_tick(_emitting_items(), root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state=state,
                                seen_ids=set(), dry_run=dry_run)
        return result, state

    def test_rail_key_present_and_shaped(self):
        result, _ = self._run()
        assert "rail" in result
        for item in result["rail"]:
            # m2: spec field is `en` (was text_en); `class` slug stays for machine
            # use and label_en/label_zh are the plain-word display labels.
            assert {"id", "ts", "class", "label_en", "label_zh", "register", "en",
                    "attribution", "corroboration"} <= set(item.keys())
            # The raw slug is never the ONLY class signal the client sees.
            assert item["label_en"] and item["label_zh"]
            assert "text_en" not in item

    def test_rail_floor_eligibility_includes_weak(self):
        # The weak item is below the X post floor but above the rail floor, so it
        # appears in the rail (the rail shows more than X posts).
        result, _ = self._run()
        rail_ids = {r["id"] for r in result["rail"]}
        assert "x:tradfi:weak" in rail_ids

    def test_rail_corroboration_chip_honest(self):
        # A single-source hearsay item's chip is "reports", never presented as fact.
        result, _ = self._run()
        weak = next(r for r in result["rail"] if r["id"] == "x:tradfi:weak")
        assert weak["corroboration"] == "reports"

    def test_wires_sink_atomic_shape(self):
        import scripts.marketing_fastlane_daemon as d
        result, _ = self._run()
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            press_cfg = {"wire": {"wires_sink_paths": [str(sink)]}}
            d._write_wires_sink(result["rail"], press_cfg, now)
            payload = json.loads(sink.read_text())
            assert payload["schema"] == "wires.v1"
            assert payload["updated_at"] == "2026-07-27T14:00:00Z"
            assert isinstance(payload["items"], list)
            # Atomicity: no leftover .tmp files in the target dir.
            leftovers = [p.name for p in sink.parent.iterdir() if p.name != "wires.json"]
            assert leftovers == []

    def test_rail_capped(self):
        # rail_max_items cap is honoured.
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        press_cfg["wire"]["rail_max_items"] = 1
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        result = run_press_tick(_emitting_items(), root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state={},
                                seen_ids=set(), dry_run=True)
        assert len(result["rail"]) <= 1

    def test_rail_plain_word_labels(self):
        # m2 (opus review): every rail item carries plain-word EN/ZH labels so the
        # B4b client never renders the raw slug. The known classes map explicitly.
        from engine.marketing.press_lane import _class_labels
        assert _class_labels("macro_print") == ("Macro", "宏观")
        assert _class_labels("policy") == ("Washington", "政策")
        assert _class_labels("geopolitical") == ("Geopolitics", "地缘")
        assert _class_labels("company_news") == ("Companies", "公司")
        assert _class_labels("none") == ("Wire", "快讯")
        # An unknown/未来 class falls back to Wire/快讯 (never a bare slug leak).
        assert _class_labels("some_future_class") == ("Wire", "快讯")

    def test_rail_item_carries_labels_and_en_field(self):
        # The composed rail item uses `en` (not text_en) and carries both labels.
        result, _ = self._run()
        assert result["rail"], "expected at least one rail item"
        for item in result["rail"]:
            assert "en" in item and "text_en" not in item
            assert item["label_en"] and item["label_zh"]


class TestWiresRollingWindow:
    """M1 (opus review): the wires.json sink is a ROLLING WINDOW, not per-tick.

    Each tick's `rail` carries only THIS tick's newly-seen items, so a naive
    overwrite blanks the rail the moment a quiet tick lands. The sink must merge by
    id (new wins), sort newest-first, cap at rail_max_items, and fail-soft on a
    corrupt existing file.
    """

    @staticmethod
    def _daemon():
        import scripts.marketing_fastlane_daemon as d
        return d

    @staticmethod
    def _now():
        return datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)

    @staticmethod
    def _item(iid: str, ts: str) -> dict:
        return {"id": iid, "ts": ts, "class": "none", "label_en": "Wire",
                "label_zh": "快讯", "register": "markets", "en": f"body {iid}",
                "attribution": "", "corroboration": "reports"}

    def _read(self, sink: Path) -> list:
        return json.loads(sink.read_text())["items"]

    def test_quiet_tick_keeps_prior_items(self):
        d = self._daemon()
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            cfg = {"wire": {"wires_sink_paths": [str(sink)]}}
            # tick1: two items.
            d._write_wires_sink(
                [self._item("a", "2026-07-27T13:00:00Z"),
                 self._item("b", "2026-07-27T13:05:00Z")], cfg, self._now())
            assert {i["id"] for i in self._read(sink)} == {"a", "b"}
            # tick2: ZERO new items -> the file still has both (rolling window).
            d._write_wires_sink([], cfg, self._now())
            assert {i["id"] for i in self._read(sink)} == {"a", "b"}

    def test_new_item_merges_newest_first(self):
        d = self._daemon()
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            cfg = {"wire": {"wires_sink_paths": [str(sink)]}}
            d._write_wires_sink(
                [self._item("a", "2026-07-27T13:00:00Z"),
                 self._item("b", "2026-07-27T13:05:00Z")], cfg, self._now())
            # tick3: one NEW item, newest ts -> 3 items, newest first.
            d._write_wires_sink(
                [self._item("c", "2026-07-27T13:10:00Z")], cfg, self._now())
            items = self._read(sink)
            assert [i["id"] for i in items] == ["c", "b", "a"]

    def test_same_id_new_wins(self):
        d = self._daemon()
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            cfg = {"wire": {"wires_sink_paths": [str(sink)]}}
            d._write_wires_sink([self._item("a", "2026-07-27T13:00:00Z")],
                                cfg, self._now())
            updated = self._item("a", "2026-07-27T13:00:00Z")
            updated["en"] = "REVISED body a"
            d._write_wires_sink([updated], cfg, self._now())
            items = self._read(sink)
            assert len(items) == 1
            assert items[0]["en"] == "REVISED body a"

    def test_cap_enforced_across_window(self):
        d = self._daemon()
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            # This test isolates the count cap. Disable age pruning so the fixed
            # fixture timestamps do not become stale as wall-clock time advances.
            cfg = {"wire": {"wires_sink_paths": [str(sink)], "rail_max_items": 3,
                            "rail_max_age_h": 0}}
            # Seed 3, then add 2 newer -> window capped to the 3 newest.
            d._write_wires_sink(
                [self._item(f"old{i}", f"2026-07-27T12:0{i}:00Z") for i in range(3)],
                cfg, self._now())
            d._write_wires_sink(
                [self._item("new1", "2026-07-27T13:00:00Z"),
                 self._item("new2", "2026-07-27T13:05:00Z")], cfg, self._now())
            ids = [i["id"] for i in self._read(sink)]
            assert len(ids) == 3
            assert ids[0] == "new2" and ids[1] == "new1"
            # The oldest seed item fell out of the capped window.
            assert "old0" not in ids

    def test_corrupt_existing_file_starts_fresh(self):
        d = self._daemon()
        with tempfile.TemporaryDirectory() as td:
            sink = Path(td) / "live" / "wires.json"
            sink.parent.mkdir(parents=True, exist_ok=True)
            sink.write_text("{ this is not valid json ][")
            cfg = {"wire": {"wires_sink_paths": [str(sink)]}}
            # Must not raise; the new items are written, corrupt history dropped.
            d._write_wires_sink([self._item("a", "2026-07-27T13:00:00Z")],
                                cfg, self._now())
            items = self._read(sink)
            assert [i["id"] for i in items] == ["a"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. site_access classification present
# ─────────────────────────────────────────────────────────────────────────────

def test_site_access_wires_json_free_registered():
    cfg = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    assert "/live/wires.json" in cfg["free_registered"]["exact"]
    # It must NOT be public (registered-user surface, unlike /live/quotes.json).
    assert "/live/wires.json" not in cfg["public"]["exact"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Deterministic fallback proof — full tick emits keyless with voice on
# ─────────────────────────────────────────────────────────────────────────────

_RICH_GEO = (
    "Multiple wires report a missile strike and blockade near the Strait of Hormuz "
    "amid a sharp escalation; oil tankers carrying seaborne crude are rerouting as "
    "officials weigh a military response and insurers reassess war-risk premiums."
)
_DEEP_BODY = (
    "Multiple wires report a missile strike and blockade near the Strait of Hormuz "
    "amid a sharp escalation, with oil tankers carrying seaborne crude now rerouting "
    "away from the channel as officials weigh a military response. Insurers are "
    "reassessing war-risk premiums on the route, shippers are pausing transits, and "
    "traders are bracing for a supply squeeze if the disruption holds into next week."
)


def _geo_pair() -> list[dict]:
    """Two independent wires on the SAME corroborated geopolitical claim."""
    hl = "Missile strike and blockade near Strait of Hormuz halt $XOM $CVX oil shipping"
    return [
        {"id": "x:zerohedge:g", "source": "x_zerohedge", "source_name": "@zerohedge",
         "source_tier": "x_relay", "url": "u", "published_at": "2026-07-27T13:59:00Z",
         "headline": hl, "body_snippet": _RICH_GEO, "x_handle": "zerohedge",
         "corroboration_class": "hearsay"},
        {"id": "x:firstsquawk:g", "source": "x_FirstSquawk", "source_name": "@FirstSquawk",
         "source_tier": "x_relay", "url": "u", "published_at": "2026-07-27T13:59:05Z",
         "headline": hl, "body_snippet": _RICH_GEO, "x_handle": "FirstSquawk",
         "corroboration_class": "hearsay"},
    ]


def test_wire_deep_emits_with_tape_stamp():
    """A corroborated high-salience geopolitical item + rich source + moved oil tape
    => wire_deep format with a tape stamp; a quiet/unmapped item stays flash."""
    import tempfile as _tempfile
    now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    press_cfg["wire"]["flagship_top_k_per_day"] = 10
    press_cfg["wire"]["flagship_salience_floor"] = 40.0
    with _tempfile.TemporaryDirectory() as td:
        qpath = Path(td) / "quotes.json"
        qpath.write_text(json.dumps({"ts": now_ms, "quotes": {
            "CL=F": {"changePct": -2.3, "ts": now_ms}}}))
        press_cfg["wire"]["tape"]["quote_store_paths"] = [str(qpath)]

        def llm(item, cfg):
            return _DEEP_BODY if "Hormuz" in item.get("headline", "") else None

        result = run_press_tick(_geo_pair(), root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state={},
                                seen_ids=set(), dry_run=True, llm_override=llm)
    assert result["emitted"], "corroborated geopolitical pair must emit"
    deep = result["emitted"][0]
    assert deep["source"]["wire_format"] == "wire_deep"
    assert deep["source"]["tape_stamp"] == "WTI -2.3%"
    body = deep["body"]
    assert "WTI -2.3%" in body
    # The composed wire_deep post is within the 400-700 budget.
    assert wf.validate_length(body, "wire_deep") == []


def test_full_tick_emits_keyless_with_voice():
    """A strong direct-quote item emits with a composed voice body even keyless.

    No LLM env armed => the summary is the deterministic '{headline}' path; the
    voice pass still applies opener + attribution + tape, and the composed body
    is a valid flash within budget.
    """
    now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    result = run_press_tick(_emitting_items(), root=str(ROOT), now=now,
                            cfg=marketing_cfg, press_cfg=press_cfg, state={},
                            seen_ids=set(), dry_run=True)
    assert result["emitted"], "the strong direct-quote item must emit"
    emit = result["emitted"][0]
    body = emit["body"]
    prov = emit["source"]
    # Attribution present, register derived, format recorded.
    assert "on Truth Social" in body
    # `speaker`, not `people`, since the 2026-07-31 attribution law: this fixture
    # IS a Truth Social item (source=trumpstruth + truth_status_id), so its
    # provenance licenses the speaker register and its "TRUMP:" hooks. The old
    # `people` value was topic-keyed and reached the SAME pool from any ordinary
    # wire story — which is how a MarketWatch item shipped datelined "White
    # House, minutes ago:".
    assert prov["register"] == "speaker"
    assert prov["wire_format"] in ("flash", "wire_deep")
    # The composed post is within the flash budget.
    assert wf.validate_length(body, prov["wire_format"]) == []


# ─────────────────────────────────────────────────────────────────────────────
# 10. B1 — press copy meets the house language law, and the lane seals it
#
# The publisher runs copywriter.banned_language() on every due item and
# QUARANTINES a hit (scripts/marketing_publisher.py). Every join in this lane
# used an em dash, so the whole press estate was building copy that could not
# survive its own last gate: the lane looked healthy (items queued, tick green)
# and nothing ever posted. These tests pin the two halves of the fix — the copy
# no longer contains the token, and the lane refuses to enqueue it if a future
# vintage ever reintroduces one.
# ─────────────────────────────────────────────────────────────────────────────

def _banned():
    from engine.marketing.copywriter import banned_language
    return banned_language


class TestB1LanguageLaw:
    def test_every_opener_in_every_pool_is_clean(self):
        banned_language = _banned()
        pools = dict(wv._REGISTER_POOLS)
        assert pools, "the register pools must not be empty"
        for register, pool in pools.items():
            for opener in pool:
                assert banned_language(opener) == [], (
                    f"opener {opener!r} in the {register} pool would quarantine "
                    f"every post that draws it")

    def test_compose_post_attribution_join_is_double_hyphen(self):
        banned_language = _banned()
        post = wv.compose_post(
            opener="Now crossing.", summary="Retail sales unchanged",
            attribution="Reuters reporting", tape_stamp="WTI -2.3%")
        assert "-- Reuters reporting" in post
        assert banned_language(post) == []

    def test_compose_post_does_not_double_append_a_legacy_join(self):
        # An older-vintage body that already carries the clause (in any dash form)
        # must not get a second one appended.
        post = wv.compose_post(
            opener="", summary="Retail sales unchanged -- Reuters reporting",
            attribution="Reuters reporting")
        assert post.count("Reuters reporting") == 1

    def test_full_tick_copy_survives_the_publisher_language_gate(self):
        """The end-to-end proof: every string this lane emits — X body, composed
        text, and the rail item — passes the same screen the publisher applies."""
        banned_language = _banned()
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        result = run_press_tick(_emitting_items(), root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state={},
                                seen_ids=set(), dry_run=True)
        assert result["emitted"], "the strong direct-quote item must emit"
        for emit in result["emitted"]:
            assert banned_language(emit["text"]) == [], emit["text"]
            assert banned_language(emit["body"]) == [], emit["body"]
            assert banned_language(emit["headline"]) == [], emit["headline"]
        rail = result.get("rail") or []
        assert rail, "the rail must carry the tick's items"
        for item in rail:
            # The rail-ONLY path builds its own text (headline + attribution +
            # tape); it must join the same way the post path does.
            assert banned_language(item["en"]) == [], item["en"]

    def test_source_headline_with_an_em_dash_is_refused_at_the_choke_point(self):
        """The seal. A source wire arrives with an em dash IN THE HEADLINE, which
        is copied verbatim into the post text. Nothing upstream can catch it, so
        the last gate must: no item enters the queue, and the skip census names
        the gate instead of a generic refusal."""
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        items = _emitting_items()
        items[0]["headline"] = (
            "Trump orders new tariff — and export controls on $AAPL and $NVDA")
        result = run_press_tick(items, root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state={},
                                seen_ids=set(), dry_run=True)
        # ASSERT THE CONTRACT, NOT A SIDE EFFECT OF THE FLOOR.
        #
        # This used to read `assert not result["emitted"]`, which held only while
        # wire.flagship_salience_floor was 70.0 — a value so high that items[0]
        # was the ONLY fixture item that could clear it, so refusing it emptied
        # the whole tick. The floor moved to 30.0 (2026-07-31: 70 was the exact
        # arithmetic ceiling of macro_print+official, which is why this wire only
        # ever posted BEA prints), a clean sibling item now also clears, and the
        # blanket assertion started failing while the gate it guards was working
        # perfectly.
        #
        # What must be true is narrower and stronger, and does not move with a
        # calibration knob: the em-dash item specifically does not enter the
        # queue, NOTHING that enters carries banned language, and the skip census
        # names the gate rather than a generic refusal.
        banned_language = _banned()
        for emit in result["emitted"]:
            assert banned_language(emit["text"]) == [], (
                "an em dash in the source headline reached the post text "
                "verbatim; the lane must refuse it rather than queue an "
                "unpostable item: " + emit["text"])
            assert "—" not in emit["text"], emit["text"]
        reasons = [s.get("reason") for s in result["skipped"]]
        assert "banned_language" in reasons, reasons
        row = next(s for s in result["skipped"] if s.get("reason") == "banned_language")
        assert any("em dash" in v for v in row.get("violations", []))


# ─────────────────────────────────────────────────────────────────────────────
# 11. M1 — the post that ships fits the platform
#
# The outbox text is headline + blank line + body, X's cap is 280, and
# wire_deep's budget is 400-700. Every deep item therefore composed to ~480
# characters, cleared its own validator, entered the queue, and was quarantined
# by validate_postable. The format the lane researched hardest had never once
# reached the timeline. The clamp decides what X gets; the rail keeps the item
# whole, because news.html has no character cap.
# ─────────────────────────────────────────────────────────────────────────────

class TestPlatformClamp:
    def test_a_post_that_fits_is_untouched(self):
        out = wf.clamp_for_x("Headline here", "Body here -- Reuters reporting")
        assert out["text"] == "Headline here\n\nBody here -- Reuters reporting"
        assert out["clamped"] is False

    def test_the_duplicated_headline_is_the_first_thing_dropped(self):
        body = "A. " * 60  # 180 chars of body
        body = body.strip()
        headline = "H" * 150
        out = wf.clamp_for_x(headline, body)
        assert out["text"] == body, "the body alone fits; the prefix must go first"
        assert out["clamped"] is True
        assert "headline prefix dropped" in out["reason"]

    def test_an_over_cap_body_is_trimmed_on_a_SENTENCE_boundary_with_its_tail(self):
        s1 = ("Multiple wires report a missile strike and a blockade near the "
              "strait, and tankers carrying crude are already rerouting away.")
        s2 = ("Insurers are reassessing war risk premiums on the route while "
              "shippers pause transits through the channel entirely this week.")
        s3 = ("Traders brace for a supply squeeze if the disruption holds into "
              "next week and the reroute becomes the standing arrangement.")
        body = f"{s1} {s2} {s3} -- Reuters reporting · WTI -2.3%"
        assert len(body) > wf.X_POST_MAX_CHARS, "fixture is degenerate"
        out = wf.clamp_for_x("A headline", body,
                             attribution="Reuters reporting", tape_stamp="WTI -2.3%")
        text = out["text"]
        assert len(text) <= wf.X_POST_MAX_CHARS
        assert out["clamped"] is True and "trimmed to" in out["reason"]
        # The tail is the source line and the tape number: losing either would
        # turn an attributed wire post into an unattributed claim.
        assert text.endswith(" -- Reuters reporting · WTI -2.3%")
        # Whole sentences only. Every sentence is either present entire or gone
        # entirely: no post ever ends mid-claim.
        head = text[: -len(" -- Reuters reporting · WTI -2.3%")]
        assert head.startswith(s1)
        for sentence in (s1, s2, s3):
            assert sentence in head or sentence[:30] not in head, (
                f"a sentence was cut mid-claim: {head!r}")

    def test_a_post_that_cannot_fit_at_all_returns_nothing(self):
        # One 400-character sentence: no whole-sentence prefix fits, and a
        # mid-sentence cut is not on the ladder.
        out = wf.clamp_for_x("H", "word " * 79 + "end")
        assert out["text"] == ""
        assert "not one sentence fits" in out["reason"]

    def test_the_deep_tick_now_produces_a_POSTABLE_item(self):
        """End to end, against the publisher's own validator."""
        from engine.marketing.social_publisher import validate_postable
        import tempfile as _tempfile

        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        press_cfg["wire"]["flagship_top_k_per_day"] = 10
        press_cfg["wire"]["flagship_salience_floor"] = 40.0
        with _tempfile.TemporaryDirectory() as td:
            qpath = Path(td) / "quotes.json"
            qpath.write_text(json.dumps({"ts": now_ms, "quotes": {
                "CL=F": {"changePct": -2.3, "ts": now_ms}}}))
            press_cfg["wire"]["tape"]["quote_store_paths"] = [str(qpath)]

            def llm(item, cfg):
                return _DEEP_BODY if "Hormuz" in item.get("headline", "") else None

            result = run_press_tick(_geo_pair(), root=str(ROOT), now=now,
                                    cfg=marketing_cfg, press_cfg=press_cfg,
                                    state={}, seen_ids=set(), dry_run=True,
                                    llm_override=llm)
        assert result["emitted"], "the corroborated deep pair must still emit"
        emit = result["emitted"][0]
        assert emit["source"]["wire_format"] == "wire_deep"
        assert validate_postable(emit["text"], None, False) == [], emit["text"]
        # The clamp is recorded, not silent.
        assert emit["source"].get("x_clamp")
        # ...and the RAIL still carries the full-length item.
        rail = {r["id"]: r for r in result["rail"]}
        assert len(rail[emit["source"]["feed_item_id"]]["en"]) > wf.X_POST_MAX_CHARS

    def test_every_emitted_press_item_is_postable(self):
        """The general form: no tick may queue an item the publisher will
        quarantine for length. This is the regression that would have caught the
        defect on the day wire_deep landed."""
        from engine.marketing.social_publisher import validate_postable

        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        result = run_press_tick(_emitting_items(), root=str(ROOT), now=now,
                                cfg=marketing_cfg, press_cfg=press_cfg, state={},
                                seen_ids=set(), dry_run=True)
        assert result["emitted"]
        for emit in result["emitted"]:
            assert validate_postable(emit["text"], None, False) == [], emit["text"]


# ─────────────────────────────────────────────────────────────────────────────
# 11. ATTRIBUTION LAW — a dateline is a factual claim about provenance
#
# THE INCIDENT (2026-07-31, PUBLISHED): `_OPENERS_DEFAULT` held four
# speaker/venue hooks ("🚨 TRUMP:", "TRUMP:", "🇺🇸 TRUMP:", "White House, minutes
# ago:") and `_REGISTER_POOLS` pointed BOTH `people` and `markets` at that pool.
# `derive_register` returns `markets` for every ordinary wire story, so the hook
# was drawn by hash from a pool with nothing to do with the item's source: a
# MarketWatch story about three Fed dissenters posted on the flagship datelined
# "White House, minutes ago:" — a fabricated attribution on a finance account.
#
# These tests fail on the pre-fix module: the wire-item sweep below draws a
# TRUMP/White House hook within a handful of ids from the old shared pool.
# ─────────────────────────────────────────────────────────────────────────────

#: Anything that names a speaker or a venue. Independent of the module's own
#: `_ATTRIBUTIVE_OPENERS` on purpose — a test that reuses the guard's regex
#: passes for free the day the regex stops matching.
_DATELINE_MARKS = ("trump", "white house", "president said", "oval office")


def _has_dateline(text: str) -> bool:
    low = str(text or "").lower()
    return any(m in low for m in _DATELINE_MARKS)


def _wire_item(iid: str) -> dict:
    """The 2026-07-31 item, verbatim in shape: an ordinary wire story."""
    return {
        "id": iid, "source": "marketwatch_top", "source_name": "MarketWatch",
        "source_tier": "wire", "url": "https://www.marketwatch.com/story/fed-dissent",
        "headline": "Three Fed officials dissent from the rate decision",
        "body_snippet": "Three regional presidents voted against the hold.",
        "event_class": "macro_print", "corroboration_class": "hearsay",
        "salience": 62.0, "matched": {"tickers": []},
    }


def _truth_item(iid: str) -> dict:
    """A genuine Truth Social post of Trump's own (the trumpstruth mirror)."""
    return {
        "id": iid, "source": "trumpstruth",
        "source_name": "Truth Social (via trumpstruth.org)", "source_tier": "mirror",
        "url": "https://truthsocial.com/users/realDonaldTrump/statuses/1",
        "mirror_url": "https://trumpstruth.org/statuses/1",
        "truth_status_id": "1", "author": "Donald J. Trump",
        "headline": "Trump says tariffs on China rise Monday",
        "body_snippet": "The tariffs go up.", "event_class": "policy",
        "corroboration_class": "direct-quote", "salience": 80.0,
        "matched": {"tickers": []},
    }


class TestAttributionLaw:
    def test_a_markets_wire_item_can_never_draw_a_speaker_opener(self):
        # 40 distinct ids, walking the no-repeat window: every reachable slot of
        # the markets pool is exercised. Not one may name a speaker or a venue.
        recent: list[str] = []
        drawn = set()
        for i in range(40):
            it = _wire_item(f"mw:{i}")
            assert wv.derive_register(it) == "markets"
            opener, register = wv.select_opener(it, account="flagship",
                                                recent_openers=recent)
            recent.append(opener)
            drawn.add(opener)
            assert not _has_dateline(opener), (
                f"wire item {it['id']} drew the fabricated dateline {opener!r}")
        # …and the pool is still a rotating pool, not one surviving phrase.
        assert len(drawn) >= 3, drawn

    def test_a_truth_social_item_still_draws_the_speaker_hook(self):
        # The other direction, and the reason this is a provenance rule rather
        # than a deletion: an item that IS Trump's own post keeps the hook.
        assert wv.derive_register(_truth_item("t:0")) == "speaker"
        drawn = {wv.select_opener(_truth_item(f"t:{i}"), account="flagship",
                                  recent_openers=[])[0] for i in range(40)}
        assert any("TRUMP" in o for o in drawn), drawn

    def test_the_white_house_dateline_needs_the_white_house_feed(self):
        wh = {"id": "wh:1", "source": "whitehouse_actions",
              "source_name": "White House presidential actions",
              "url": "https://www.whitehouse.gov/presidential-actions/x",
              "headline": "Executive order signed", "body_snippet": "",
              "event_class": "policy", "matched": {}}
        assert wv.derive_register(wh) == "white_house"
        drawn = {wv.select_opener(dict(wh, id=f"wh:{i}"), recent_openers=[])[0]
                 for i in range(40)}
        assert any("White House" in o for o in drawn), drawn

    def test_a_story_about_the_white_house_is_not_a_white_house_source(self):
        # The exact confusion the incident rested on: provenance is read from
        # where the item CAME from, never from what it is about.
        it = _wire_item("mw:about-wh")
        it["headline"] = "White House weighs new tariffs, sources say"
        it["body_snippet"] = "Trump is said to favor the move."
        assert wv.source_provenance(it) == ""
        assert wv.derive_register(it) == "markets"
        for i in range(40):
            opener, _ = wv.select_opener(dict(it, id=f"mw:wh:{i}"), recent_openers=[])
            assert not _has_dateline(opener), opener

    def test_a_config_override_cannot_reintroduce_a_fabricated_dateline(self):
        # `wire.opener_pools` is a live edit surface. The filter in select_opener
        # is what makes the law hold there too.
        cfg = {"opener_pools": {"markets": ["TRUMP:", "White House, minutes ago:"]}}
        opener, register = wv.select_opener(_wire_item("mw:cfg"), cfg=cfg,
                                            recent_openers=[])
        assert register == "markets"
        assert opener == "", opener

    def test_a_truth_mirror_repointed_at_another_author_loses_the_hook(self):
        # Fail-closed: `author:` is a config field. A mirror aimed at somebody
        # else must not keep stamping "TRUMP:" on their words.
        it = _truth_item("t:other")
        it["author"] = "Jerome Powell"
        assert wv.source_provenance(it) == ""
        for i in range(40):
            opener, _ = wv.select_opener(dict(it, id=f"t:other:{i}"), recent_openers=[])
            assert not _has_dateline(opener), opener

    def test_no_opener_pool_ships_an_unguarded_attribution(self):
        # The sweep, mechanically: every pool the module ships is either
        # non-attributive or reachable only through its provenance register.
        for register, pool in wv._REGISTER_POOLS.items():
            for opener in pool:
                needed = wv.opener_requires_provenance(opener)
                if needed:
                    assert register in ("speaker", "white_house"), (
                        f"{register} pool ships the attributive opener {opener!r}")
                else:
                    assert not _has_dateline(opener), (
                        f"{register} pool ships {opener!r}, which reads as a "
                        "dateline but no provenance rule guards it")

    def test_the_composed_press_body_of_a_wire_item_carries_no_dateline(self):
        # End to end through the tick: the bodies that would have POSTED. Eight
        # distinct wire stories, because one item is one opener draw and the
        # pre-fix pool put a dateline in 4 of its 9 slots — a single-item version
        # of this test passes by luck on the hash and pins nothing.
        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        press_cfg["wire"]["flagship_top_k_per_day"] = 20
        press_cfg["wire"]["flagship_salience_floor"] = 10.0
        _stories = (
            "Three Fed officials dissent from the rate decision",
            "Retail sales fall for a second month",
            "Jobless claims drop to a four-week low",
            "Factory orders rise more than forecast",
            "Housing starts slide as rates bite",
            "Consumer confidence slips in July",
            "Industrial production edges higher",
            "Trade deficit narrows on softer imports",
        )
        items = []
        for i, hl in enumerate(_stories):
            it = dict(_wire_item(f"mw:tick:{i}"),
                      published_at="2026-07-27T13:59:00Z", headline=hl)
            it["body_snippet"] = f"{hl}, the report showed."
            items.append(it)
        result = run_press_tick(items, root=str(ROOT), now=now, cfg=marketing_cfg,
                                press_cfg=press_cfg, state={}, seen_ids=set(),
                                dry_run=True)
        bodies = [e.get("body", "") for e in result["emitted"]]
        bodies += [r.get("en", "") for r in result["rail"]]
        assert bodies, "the fixture must produce at least one composed body"
        for body in bodies:
            assert "White House, minutes ago" not in body, body
            assert not body.startswith("TRUMP:"), body
            assert "🚨 TRUMP:" not in body, body


# ─────────────────────────────────────────────────────────────────────────────
# 12. THE PRESS CARD IS RASTERED AND HOSTED
#
# THE DEFECT (2026-07-31): `_emit_outbox_item` wrote the raw SVG to disk and
# stopped. Nothing in press_lane.py or breaking_summary.py called rasterize_svg
# or media_publish.publish_card, so every press item carried a media[] entry
# with no `media_url` — and Buffer/X can only attach a HOSTED image. Every press
# post shipped text-only, and a press item naming a cashtag was permanently
# unpostable (the publisher quarantines a bare cashtag post).
#
# All three tests fail on the pre-fix module: no media_url is ever stamped, and
# a cashtag item with an unhostable card enqueues happily.
# ─────────────────────────────────────────────────────────────────────────────

_CARD_SVG = "<svg width='10' height='10'></svg>"


def _emit(root, monkeypatch, published, *, body, item_id="feed-1", refusal=None):
    """Run the emit path with `media_publish.publish_card` stubbed."""
    from engine.marketing import media_publish, press_lane

    seen: list[dict] = []

    def _fake_publish_card(svg, *, chart_id, as_of, root=None, legacy_png=None):
        seen.append({"svg": svg, "chart_id": chart_id, "as_of": as_of})
        return dict(published)

    monkeypatch.setattr(media_publish, "publish_card", _fake_publish_card)
    press_lane.reset_media_host_stats()
    now = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)
    item = press_lane._emit_outbox_item(
        Path(root), item_id, "flagship", "Three Fed officials dissent", body,
        _CARD_SVG,
        {"url": "https://www.marketwatch.com/story/fed-dissent",
         "source_headline": "Three Fed officials dissent"},
        now, story_key="k", cta_suppress=False, dry_run=False, cfg={},
        spool=False, refusal=refusal if refusal is not None else {},
    )
    return item, seen


class TestPressCardMedia:
    _HOSTED = {
        "svg_path": "data/marketing/outbox/media/2026-07-31/feed-1.svg",
        "media_png_path": "data/marketing/outbox/media/2026-07-31/feed-1.png",
        "media_url": "https://cdn.mastermind-x.com/charts/2026-07-31/feed-1.png",
        "media_render": "svg_raster",
    }

    def test_the_emitted_item_carries_a_hosted_media_url(self, tmp_path, monkeypatch):
        from engine.marketing import press_lane

        item, seen = self._emit_hosted(tmp_path, monkeypatch)
        assert item is not None
        entry = item["media"][0]
        # The hot-tape card contract, copied exactly.
        assert entry["media_url"] == self._HOSTED["media_url"]
        assert entry["media_png_path"] == self._HOSTED["media_png_path"]
        assert entry["media_render"] == "svg_raster"
        # One seam, and it is handed the SAME svg the lane rendered, keyed so the
        # backfill sidecar (<as_of>/<chart_id>) can heal a failed upload later.
        assert len(seen) == 1
        assert seen[0]["svg"] == _CARD_SVG
        assert seen[0]["chart_id"] == "feed-1"
        assert seen[0]["as_of"] == item["as_of"]
        assert press_lane.media_host_stats()["hosted"] == 1

    def _emit_hosted(self, tmp_path, monkeypatch):
        return _emit(tmp_path, monkeypatch, self._HOSTED,
                     body="Rare triple dissent at the Fed. $SPY watches the vote.")

    def test_a_cashtag_item_whose_host_failed_is_not_enqueued(self, tmp_path,
                                                              monkeypatch, capsys):
        from engine.marketing import outbox as OB
        from engine.marketing import press_lane

        refusal: dict = {}
        item, _seen = _emit(
            tmp_path, monkeypatch, {"svg_path": "x.svg"},   # no media_url
            body="Rare triple dissent at the Fed. $SPY watches the vote.",
            refusal=refusal,
        )
        assert item is None, "a cashtag post with no picture must not enqueue"
        assert refusal["reason"] == "media_unhosted"
        assert OB.read_items(Path(tmp_path)) == []
        assert press_lane.media_host_stats()["unhosted_refused"] == 1
        lines = capsys.readouterr().out.splitlines()
        hits = [ln for ln in lines if "press-lane-card-unhosted" in ln]
        assert hits, lines
        assert hits[0].startswith("::warning title=press-lane-card-unhosted::"), hits[0]

    def test_a_cashtag_free_item_whose_host_failed_still_posts_text_only(
            self, tmp_path, monkeypatch, capsys):
        from engine.marketing import press_lane

        item, _seen = _emit(
            tmp_path, monkeypatch, {},
            body="Three regional presidents voted against the hold -- MarketWatch",
        )
        assert item is not None, "prose with no cashtag must keep flowing"
        # No pointer to a picture nothing can fetch.
        assert item["media"] == []
        assert press_lane.media_host_stats()["unhosted"] == 1
        assert press_lane.media_host_stats()["unhosted_refused"] == 0
        hits = [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning title=press-lane-card-unhosted::")]
        assert hits, "an unhosted card is announced even when the post still ships"

    def test_a_raising_publisher_never_takes_down_the_lane(self, tmp_path,
                                                           monkeypatch, capsys):
        from engine.marketing import media_publish, press_lane

        def _boom(*a, **kw):
            raise RuntimeError("boto3 missing")

        monkeypatch.setattr(media_publish, "publish_card", _boom)
        press_lane.reset_media_host_stats()
        now = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)
        item = press_lane._emit_outbox_item(
            Path(tmp_path), "feed-2", "flagship", "Fed holds rates",
            "Three regional presidents voted against the hold -- MarketWatch",
            _CARD_SVG, {"url": "u", "source_headline": "Fed holds rates"}, now,
            story_key="k2", cta_suppress=False, dry_run=False, cfg={}, spool=False,
        )
        # Fail-soft to the pre-fix behaviour for a cashtag-free item.
        assert item is not None
        assert item["media"] == []
        out = capsys.readouterr().out
        assert "::warning title=press-lane-card-publish-failed::" in out


# ─────────────────────────────────────────────────────────────────────────────
# 13. A TRANSIENT REFUSAL IS NOT A PERMANENT KILL
#
# THE DEFECT (adversarial review, 2026-07-31). run_press_tick added EVERY
# outbox refusal to the permanent `seen` ledger under a comment asserting that
# "every refusal reason is a stable property of the copy, so a retry cannot
# change the answer". `media_unhosted` is not: it fires when the Chrome raster
# loses a race, when the R2 upload blips, when boto3/R2_* are missing on the
# host. One flaky raster therefore suppressed a breaking cashtag story for the
# entire life of the ledger, and the LLM spend that produced its copy bought
# nothing.
#
# Both halves are pinned here: the retry (an unhosted item comes back next
# tick) and the alarm (a host that is genuinely down still surfaces, rather
# than re-rendering and re-paying in silence forever).
# ─────────────────────────────────────────────────────────────────────────────

_TICK_NOW = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)


def _refusing_tick(monkeypatch, reason, *, state, seen, calls=None):
    """One press tick whose outbox emission always refuses with `reason`.

    `_emit_outbox_item` is the seam because the refusal it returns is precisely
    what the caller under test branches on; driving the real card host from here
    would test media_publish, not the seen-ledger law.
    """
    from engine.marketing import press_lane

    def _refuse(root, item_id, account, headline, body, svg, provenance, now,
                **kw):
        if calls is not None:
            calls.append(item_id)
        _refusal = kw.get("refusal")
        if _refusal is not None:
            _refusal["reason"] = reason
        return None

    monkeypatch.setattr(press_lane, "_emit_outbox_item", _refuse)
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    return run_press_tick(_emitting_items(), root=str(ROOT), now=_TICK_NOW,
                          cfg=marketing_cfg, press_cfg=press_cfg, state=state,
                          seen_ids=seen, dry_run=True)


class TestTransientRefusalsRetry:
    def test_an_unhosted_item_is_not_burned_into_the_seen_ledger(self, monkeypatch):
        state: dict = {}
        calls: list[str] = []
        result = _refusing_tick(monkeypatch, "media_unhosted",
                                state=state, seen=set(), calls=calls)
        assert "trumpstruth:strong" in calls, calls
        assert result["emitted"] == []
        reasons = [r["reason"] for r in result["skipped"]]
        assert "media_unhosted" in reasons, result["skipped"]
        # THE PIN. Pre-fix the emission key was in `_seen`, so every later tick
        # deduped the story away and it could never be retried.
        assert "truth:strong" not in set(result["_seen"]), result["_seen"]

    def test_the_next_tick_actually_re_attempts_it(self, monkeypatch):
        state: dict = {}
        calls: list[str] = []
        seen: set = set()
        for _ in range(2):
            result = _refusing_tick(monkeypatch, "media_unhosted",
                                    state=state, seen=seen, calls=calls)
            seen = set(result["_seen"])
        # Two ticks, two genuine attempts — not one attempt and one dedupe skip.
        assert calls.count("trumpstruth:strong") == 2, calls

    def test_a_copy_property_refusal_still_never_comes_back(self, monkeypatch):
        """The invariant the old blanket comment was RIGHT about, kept intact:
        banned language is decided by the text and gives the same answer
        forever, so re-generating it burns billed spend on a known outcome."""
        state: dict = {}
        calls: list[str] = []
        seen: set = set()
        for _ in range(2):
            result = _refusing_tick(monkeypatch, "banned_language",
                                    state=state, seen=seen, calls=calls)
            seen = set(result["_seen"])
        assert "truth:strong" in seen, seen
        assert calls.count("trumpstruth:strong") == 1, calls

    def test_a_genuinely_dead_host_still_alarms(self, monkeypatch, capsys):
        """The retry must not be silent — a host that is down re-renders and
        re-pays every tick, and that has to reach the Actions summary."""
        state: dict = {}
        seen: set = set()
        for _ in range(_TRANSIENT_ALARM_AT := 3):
            result = _refusing_tick(monkeypatch, "media_unhosted",
                                    state=state, seen=seen)
            seen = set(result["_seen"])
        assert state["transient_refusals"]["truth:strong"] == _TRANSIENT_ALARM_AT
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-transient-refusal-stuck" in ln]
        assert lines, "three consecutive environment refusals must alarm"
        # House law: the annotation STARTS the line or GitHub drops it silently.
        assert lines[0].startswith(
            "::warning title=press-lane-transient-refusal-stuck::"), lines[0]

    def test_the_alarm_holds_its_fire_through_a_blip(self, monkeypatch, capsys):
        """One or two failed ticks is a raster race, not an outage."""
        from engine.marketing import press_lane

        state: dict = {}
        seen: set = set()
        for _ in range(press_lane._TRANSIENT_RETRY_ALARM_AT - 1):
            result = _refusing_tick(monkeypatch, "media_unhosted",
                                    state=state, seen=seen)
            seen = set(result["_seen"])
        assert "press-lane-transient-refusal-stuck" not in capsys.readouterr().out

    def test_a_settled_refusal_clears_the_streak(self, monkeypatch):
        """The tally counts CONSECUTIVE environment refusals. A story that then
        refuses on its copy is settled, and its counter must not linger to
        alarm on some unrelated later story."""
        from engine.marketing import press_lane

        state: dict = {}
        seen: set = set()
        result = _refusing_tick(monkeypatch, "media_unhosted",
                                state=state, seen=seen)
        assert state["transient_refusals"]["truth:strong"] == 1
        result = _refusing_tick(monkeypatch, "banned_language",
                                state=state, seen=set(result["_seen"]))
        assert "truth:strong" not in state["transient_refusals"]
        assert press_lane._TRANSIENT_RETRY_ALARM_AT >= 2
