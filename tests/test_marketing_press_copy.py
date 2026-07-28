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
        assert out["summary"] == "Retail sales unchanged — MarketWatch"


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
            cfg = {"wire": {"wires_sink_paths": [str(sink)], "rail_max_items": 3}}
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
    assert deep["provenance"]["wire_format"] == "wire_deep"
    assert deep["provenance"]["tape_stamp"] == "WTI -2.3%"
    body = deep["text"]["body"]
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
    body = emit["text"]["body"]
    prov = emit["provenance"]
    # Attribution present, register derived, format recorded.
    assert "on Truth Social" in body
    assert prov["register"] == "people"
    assert prov["wire_format"] in ("flash", "wire_deep")
    # The composed post is within the flash budget.
    assert wf.validate_length(body, prov["wire_format"]) == []
