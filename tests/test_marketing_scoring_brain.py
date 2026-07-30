"""XG-W5 scoring brain — L0 story spine, L1 features, garbage gate, golden set.

Deps: stdlib + pytest + pyyaml ONLY. Nothing here is importorskip-gated, so the
suite can never decay into a skip-only suite (scripts/check_skip_only_suites.py):
every test executes in the thin marketing-engine lane.

The OPTIONAL-DEPENDENCY paths (datasketch MinHash-LSH) are covered by the sibling
suite tests/test_marketing_scoring_optional_deps.py, which imports datasketch at
module level ON PURPOSE — it must go RED, never skip, in the lane that declares
it. The semantic pass is covered HERE with an injected fake encoder, because the
model2vec artifact is an operator/R2 step and must never be a CI dependency.

What is pinned:
  * production wiring (press_lane.run_press_tick) actually calls L0 + L1 + gate;
  * gate ordering — a score can reorder and deprioritize, never publish;
  * no score reaches a user-facing surface;
  * `_components` for 100% of ingested items, with honest null states;
  * the golden-set harness runs end-to-end on a fixture-labeled mini-set and
    prints the honest "no labels yet" state when the store is empty;
  * no LLM anywhere in the new modules.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import garbage_gate as gg  # noqa: E402
from engine.marketing import golden_set as gs  # noqa: E402
from engine.marketing import signal_features as sf  # noqa: E402
from engine.marketing import story_spine as ss  # noqa: E402
from engine.marketing.breaking_relevance import score_item  # noqa: E402

NOW = datetime(2026, 7, 28, 14, 30, tzinfo=timezone.utc)


def _item(iid="i1", headline="CPI rises 3.2% in June", *, url="https://wire.example/a",
          source="cnbc_top", tier="wire", body="Consumer prices rose in June.",
          **extra) -> dict:
    row = {
        "id": iid,
        "source": source,
        "source_name": source,
        "source_tier": tier,
        "url": url,
        "published_at": NOW.isoformat(),
        "headline": headline,
        "body_snippet": body,
    }
    row.update(extra)
    return row


# ═════════════════════════════════════════════════════════════════════════════
# L0 — URL normalization + identity
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalization:
    def test_scheme_and_www_collapse(self):
        assert ss.normalize_url("http://www.a.com/x") == ss.normalize_url("https://a.com/x")

    def test_tracking_params_stripped_meaningful_kept(self):
        assert ss.normalize_url(
            "https://a.com/x?utm_source=tw&fbclid=9&id=42#frag"
        ) == "a.com/x?id=42"

    def test_trailing_slash_and_amp_folded(self):
        assert ss.normalize_url("https://a.com/x/") == "a.com/x"
        assert ss.normalize_url("https://a.com/x/amp") == "a.com/x"

    def test_x_host_scoped_s_and_t_stripped_elsewhere_kept(self):
        assert ss.normalize_url("https://x.com/u/status/1?s=20&t=q") == "x.com/u/status/1"
        # `s` is meaningful off X (e.g. a symbol query) — never blanket-stripped.
        assert ss.normalize_url("https://a.com/q?s=AAPL") == "a.com/q?s=AAPL"

    def test_empty_and_garbage_are_safe(self):
        assert ss.normalize_url("") == ""
        assert ss.normalize_url(None) == ""

    def test_content_key_precedence_mirror_collapse(self):
        a = _item("a", url="https://m1.example/p/1", truth_status_id="99")
        b = _item("b", url="https://m2.example/p/2", truth_status_id="99")
        assert ss.content_key(a) == ss.content_key(b) == "truth:99"

    def test_content_key_falls_back_to_headline_when_no_url(self):
        key = ss.content_key(_item("a", url=""))
        assert key.startswith("head:")

    def test_shingles(self):
        assert ss.shingles("a b c d", k=3) == {"a b c", "b c d"}
        assert ss.shingles("a b", k=3) == {"a b"}
        assert ss.shingles("", k=3) == set()


# ═════════════════════════════════════════════════════════════════════════════
# L0 — the spine
# ═════════════════════════════════════════════════════════════════════════════

class TestStorySpine:
    def test_the_same_url_twice_is_one_story_and_ONE_source(self):
        """Review F-6: the same artifact re-ingested is not a second witness."""
        spine = ss.StorySpine({}, cfg={})
        spine.assign(_item("a", url="https://w.example/1", source="cnbc"), now=NOW)
        view = spine.assign(
            _item("b", url="https://w.example/1?utm_source=x", source="reuters",
                  tier="official"),
            now=NOW,
        )
        assert len(spine.stories) == 1
        assert view["source_count"] == 1, "one URL is one source, whatever the feed key"
        assert view["tier_mix"] == {"wire": 1, "official": 1}

    def test_feed_key_and_url_host_are_one_source_not_two(self):
        """Review F-6/F-14: `cnbc_top` and `cnbc.com/...` are one publisher."""
        a = ss.independence_key(_item("a", url="https://cnbc.com/x", source="cnbc_top"))
        b = ss.independence_key(_item("b", url="https://www.cnbc.com/y", source="rss"))
        assert a == b == "host:cnbc.com"

    def test_distinct_hosts_are_distinct_sources(self):
        a = ss.independence_key(_item("a", url="https://one.example/1"))
        b = ss.independence_key(_item("b", url="https://two.example/9"))
        assert a != b

    def test_x_handle_wins_over_host(self):
        key = ss.independence_key(
            _item("a", url="https://x.com/Loud/status/1", x_handle="Loud"))
        assert key == "x:loud"

    def test_press_lane_and_spine_share_one_independence_rule(self):
        """Review F-14: two copies of one rule is how the two drift apart."""
        from engine.marketing import press_lane as pl

        item = _item("a", url="https://cnbc.com/x", source="cnbc_top")
        assert pl._independent_source(item) == ss.independence_key(item)

    def test_different_stories_stay_apart(self):
        spine = ss.StorySpine({}, cfg={})
        a = spine.assign(_item("a", "CPI rises", url="https://w.example/1"), now=NOW)
        b = spine.assign(_item("b", "Missile strike hits port",
                               url="https://w.example/2"), now=NOW)
        assert a["story_id"] != b["story_id"]

    def test_first_seen_is_the_first_sighting_not_the_latest(self):
        spine = ss.StorySpine({}, cfg={})
        first = spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        later = spine.assign(_item("b", url="https://w.example/1", source="reuters"),
                             now=NOW + timedelta(minutes=30))
        assert later["first_seen"] == first["first_seen"]

    def test_source_windows_expire(self):
        """Two hosts on one story (via the mirror key), 40 minutes apart."""
        spine = ss.StorySpine({}, cfg={})
        spine.assign(_item("a", url="https://one.example/1", truth_status_id="77"),
                     now=NOW)
        view = spine.assign(
            _item("b", url="https://two.example/9", truth_status_id="77"),
            now=NOW + timedelta(minutes=40),
        )
        assert view["source_count"] == 2
        # one.example first-seen 40 min ago: outside 15m, inside 60m.
        assert view["sources_15m"] == 1
        assert view["sources_60m"] == 2

    def test_a_mirror_re_ingest_carries_zero_corroboration_weight(self):
        """Review F-6: `exact` match = the same artifact = no new evidence."""
        spine = ss.StorySpine({}, cfg={})
        spine.assign(_item("a", url="https://one.example/1", truth_status_id="77"),
                     now=NOW)
        view = spine.assign(
            _item("b", url="https://two.example/9", truth_status_id="77"), now=NOW)
        assert view["sources_15m"] == 2, "two hosts, raw"
        assert view["weighted_15m"] == 1.0, "but the mirror adds no evidence"
        assert view["match_mix_15m"] == {"new": 1, "exact": 1}

    def test_observed_engagement_folds_from_the_poller_stream_only(self):
        spine = ss.StorySpine({}, cfg={})
        spine.assign(
            _item("a", url="https://x.com/h/status/1",
                  x_engagement={"likes": 10, "retweets": 4, "replies": 2, "views": 900}),
            now=NOW,
        )
        view = spine.assign(
            _item("b", url="https://x.com/h/status/1", source="other",
                  x_engagement={"likes": 5, "retweets": 1, "replies": 0, "views": 100}),
            now=NOW,
        )
        assert view["observed_engagement"]["likes"] == 15
        assert view["observed_engagement"]["samples"] == 2

    def test_item_without_engagement_never_fabricates_a_sample(self):
        spine = ss.StorySpine({}, cfg={})
        view = spine.assign(_item("a"), now=NOW)
        assert view["observed_engagement"]["samples"] == 0

    def test_state_round_trips_through_json(self):
        state: dict = {}
        spine = ss.StorySpine(state, cfg={})
        first = spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        revived = json.loads(json.dumps(state))
        spine2 = ss.StorySpine(revived, cfg={})
        view = spine2.assign(_item("b", url="https://w.example/1", source="reuters"),
                             now=NOW)
        assert view["story_id"] == first["story_id"]
        assert view["member_count"] == 2

    def test_v1_state_shape_is_read_tolerantly(self):
        """A restart across the v1->v2 source-shape bump must not crash."""
        state: dict = {}
        spine = ss.StorySpine(state, cfg={})
        spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        for rec in state["stories"].values():
            rec["sources"] = {k: v["first_ts"] for k, v in rec["sources"].items()}
        revived = ss.StorySpine(json.loads(json.dumps(state)), cfg={})
        sid = next(iter(revived.stories))
        view = revived.view(sid, now=NOW)
        assert view["sources_15m"] == 1
        assert view["weighted_15m"] == 1.0, "a v1 row reads as match=new"

    def test_an_unparseable_last_seen_expires_via_the_ttl(self):
        """Review F-21: a row we cannot date is a row we cannot keep."""
        state: dict = {}
        spine = ss.StorySpine(state, cfg={"story_ttl_h": 1})
        spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        for rec in state["stories"].values():
            rec["last_seen"] = "not-a-timestamp"
        assert spine.prune(NOW + timedelta(hours=5)) == 1
        assert spine.stories == {}, "a corrupt timestamp must not pin a story forever"

    def test_prune_drops_expired_stories_and_their_keys(self):
        spine = ss.StorySpine({}, cfg={"story_ttl_h": 1})
        spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        assert spine.prune(NOW + timedelta(hours=5)) == 1
        assert spine.stories == {}
        assert spine.keys == {}

    def test_prune_enforces_the_hard_cap(self):
        spine = ss.StorySpine({}, cfg={"max_stories": 2, "story_ttl_h": 999})
        # Distinct headlines on purpose: with the optional near-dup pass
        # installed, five copies of one headline are ONE story, and the cap would
        # never be exercised.
        subjects = ["Copper", "Wheat", "Volcano", "Shipping", "Semiconductor"]
        for i, subject in enumerate(subjects):
            spine.assign(
                _item(f"i{i}", f"{subject} update number {i} from the desk",
                      url=f"https://w.example/{i}"),
                now=NOW + timedelta(minutes=i),
            )
        assert len(spine.stories) == 5
        spine.prune(NOW + timedelta(minutes=5))
        assert len(spine.stories) == 2

    def test_assign_never_raises_on_a_hostile_item(self):
        spine = ss.StorySpine({}, cfg={})
        view = spine.assign({"id": None, "url": {"not": "a url"}}, now=NOW)
        assert "story_id" in view

    def test_downgrade_notices_are_readable(self):
        """Optional deps must degrade with a NOTICE, not a traceback."""
        spine = ss.StorySpine({}, cfg={})
        # The semantic pass is always off without an injected encoder.
        assert spine.semantic_enabled is False
        assert any("semantic" in d for d in spine.downgrades)
        if not spine.near_dup_enabled:
            assert any("datasketch" in d for d in spine.downgrades)
            # And the lane still clusters on exact identity.
            first = spine.assign(_item("a", url="https://w.example/1"), now=NOW)
            view = spine.assign(_item("b", url="https://w.example/1", source="r"),
                                now=NOW)
            assert view["story_id"] == first["story_id"]
            assert view["member_count"] == 2


class TestSemanticPass:
    """The semantic branch, exercised with an injected encoder.

    model2vec + its artifact are an operator/R2 step (docs/scoring_brain.md §3)
    and must never become a CI dependency — but the clustering BRANCH they feed
    is ours and is tested here deterministically.
    """

    @staticmethod
    def _encoder(texts):
        # 2-D unit-ish vectors: "rate" topic vs "oil" topic.
        out = []
        for text in texts:
            low = text.lower()
            out.append([1.0, 0.0] if "rate" in low or "fed" in low else [0.0, 1.0])
        return out

    def test_paraphrases_join_one_story(self):
        spine = ss.StorySpine({}, cfg={"semantic_threshold": 0.9},
                              encoder=self._encoder)
        assert spine.semantic_enabled is True
        a = spine.assign(_item("a", "Fed holds rates steady",
                               url="https://w.example/1"), now=NOW)
        b = spine.assign(_item("b", "Rate decision: no change",
                               url="https://w.example/2", source="reuters"), now=NOW)
        assert a["story_id"] == b["story_id"]
        assert b["match"] == "semantic"

    def test_different_topics_stay_apart(self):
        spine = ss.StorySpine({}, cfg={"semantic_threshold": 0.9},
                              encoder=self._encoder)
        a = spine.assign(_item("a", "Fed holds rates steady",
                               url="https://w.example/1"), now=NOW)
        b = spine.assign(_item("b", "Oil slips on inventory build",
                               url="https://w.example/2"), now=NOW)
        assert a["story_id"] != b["story_id"]

    def test_a_broken_encoder_disables_the_pass_and_does_not_raise(self):
        def boom(_texts):
            raise RuntimeError("model exploded")

        spine = ss.StorySpine({}, cfg={}, encoder=boom)
        view = spine.assign(_item("a", url="https://w.example/1"), now=NOW)
        assert view["story_id"]

    def test_load_encoder_is_off_by_default_and_never_downloads(self, tmp_path):
        assert ss.load_encoder({}) is None
        assert ss.load_encoder({"enabled": True, "model_path": ""}) is None
        assert ss.load_encoder(
            {"enabled": True, "model_path": str(tmp_path / "nope")}
        ) is None

    def test_load_encoder_source_has_no_hub_id_or_network_call(self):
        """The absence of a download path is the contract, so assert on source."""
        source = (ROOT / "engine" / "marketing" / "story_spine.py").read_text(encoding="utf-8")
        body = source.split("def load_encoder", 1)[1].split("\ndef ", 1)[0]
        for banned in ("urlopen", "requests.", "http://", "https://",
                       "hf_hub", "snapshot_download", "minishlab/"):
            assert banned not in body, f"load_encoder must not reference {banned}"


# ═════════════════════════════════════════════════════════════════════════════
# Garbage gate
# ═════════════════════════════════════════════════════════════════════════════

class TestGarbageGate:
    def test_satire_reason_string_is_unchanged(self):
        """The historical P0 reason string is a downstream contract."""
        hit = gg.check(_item("a", x_handle="HalfwayPost"), cfg={},
                       satire_blocklist={"halfwaypost"})
        assert hit["reason"] == "satire_blocklist"

    def test_satire_matches_the_x_source_key_form(self):
        hit = gg.check(_item("a", source="x_HalfwayPost"), cfg={},
                       satire_blocklist={"halfwaypost"})
        assert hit["reason"] == "satire_blocklist"

    def test_source_blocklist_by_key_handle_and_host(self):
        cfg = {"source_blocklist": ["badwire", "spam.example"]}
        assert gg.check(_item("a", source="badwire"), cfg=cfg)["reason"] == "source_blocklist"
        assert gg.check(_item("a", url="https://eu.spam.example/x"),
                        cfg=cfg)["reason"] == "source_blocklist"
        assert gg.check(_item("a", source="goodwire"), cfg=cfg) is None

    def test_source_blocklist_ships_empty(self):
        cfg = json_config()["breaking"]["garbage_gate"]
        assert cfg["source_blocklist"] == []

    def test_promo_strong_marker_drops(self):
        hit = gg.check(_item("a", "Sign up now for the newsletter"), cfg={})
        assert hit["reason"] == "promo_spam"

    def test_two_weak_markers_drop_one_does_not(self):
        assert gg.check(_item("a", "Free trial for readers"), cfg={}) is None
        hit = gg.check(_item("a", "Free trial and a giveaway"), cfg={})
        assert hit["reason"] == "promo_spam"

    @pytest.mark.parametrize("headline,body", [
        ("Fed leaves the discount rate unchanged", "Officials held policy steady."),
        ("Apple free cash flow tops estimates", "Quarterly results beat."),
        ("Recipe for disaster: the carry trade unwinds", "Analysts warn."),
        ("Chipmakers hurry to secure capacity", "Supply is tight."),
        ("Bidding war erupts over retail chain", "Two suitors emerged."),
    ])
    def test_finance_english_negative_controls_pass(self, headline, body):
        """The near-miss set the conservative lexicon exists for."""
        assert gg.check(_item("a", headline, body=body), cfg={}) is None

    @pytest.mark.parametrize("headline,body", [
        # Review F-9 — the four cases the reviewer's probe P0-DROPPED under raw
        # substring matching. A P0 drop is unrecoverable, so each is pinned.
        ("Nasdaq closes 3% off the highs", "Breadth narrowed into the bell."),
        ("Airlines save up to $2bn on fuel hedges", "Carriers locked in crude."),
        ("Black Friday deal volume rose 8% year over year", "Retail sales data."),
        ("Fed holds rates steady", "Advertisement. The committee voted 11-1."),
    ])
    def test_reviewer_probe_cases_must_not_drop(self, headline, body):
        assert gg.check(_item("a", headline, body=body), cfg={}) is None, \
            "raw substring matching P0-dropped this real finance copy"

    def test_the_gate_stays_enabled_after_the_fix(self):
        assert json_config()["breaking"]["garbage_gate"]["enabled"] is True
        assert gg.check(_item("a", "Sign up now for the newsletter"),
                        cfg={})["reason"] == "promo_spam"

    def test_every_matcher_is_word_boundary(self):
        """Review F-9: one matcher, and it is the strict one."""
        source = (ROOT / "engine" / "marketing" / "garbage_gate.py").read_text(encoding="utf-8")
        assert "_phrase_hits" not in source, "the substring matcher must be gone"

    def test_demoted_markers_still_drop_when_a_second_marker_joins(self):
        hit = gg.check(_item("a", "Black Friday deal: shop the lowest price"), cfg={})
        assert hit is not None and hit["reason"] == "promo_spam"

    def test_paywalled_stub_marker_drops(self):
        hit = gg.check(_item("a", body="Subscribe to continue reading."), cfg={})
        assert hit["reason"] == "paywalled_stub"

    def test_short_body_alone_never_drops(self):
        """A twitterapi.io relay body is short BY CONSTRUCTION."""
        assert gg.check(_item("a", body="Fed cuts.", tier="aggregator"), cfg={}) is None

    def test_length_rule_available_but_opt_in(self):
        cfg = {"require_marker": False, "stub_min_chars": 80}
        assert gg.check(_item("a", body="Short teaser...", tier="aggregator"),
                        cfg=cfg)["reason"] == "paywalled_stub"
        assert gg.check(_item("a", body="Short teaser...", tier="wire"), cfg=cfg) is None

    def test_non_story_is_headline_scoped(self):
        assert gg.check(_item("a", "Your daily horoscope"), cfg={})["reason"] == "non_story"
        # Same term in the BODY is not a drop — the headline is what the item is.
        assert gg.check(_item("a", "Markets close mixed",
                              body="Also inside: the horoscope."), cfg={}) is None

    def test_detectors_are_individually_toggleable(self):
        cfg = {"detectors": {"non_story": False}}
        assert gg.check(_item("a", "Your daily horoscope"), cfg=cfg) is None

    def test_gate_can_be_disabled_wholesale(self):
        assert gg.check(_item("a", "Your daily horoscope"), cfg={"enabled": False}) is None

    def test_every_detector_name_is_in_config(self):
        cfg = json_config()["breaking"]["garbage_gate"]
        assert set(cfg["detectors"]) == set(gg.detector_names())


def json_config() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


# ═════════════════════════════════════════════════════════════════════════════
# L1 features
# ═════════════════════════════════════════════════════════════════════════════

class TestCorroborationVelocity:
    def test_single_source_scores_zero(self):
        value, detail = sf.corroboration_velocity(
            {"sources_15m": 1, "sources_60m": 1, "source_count": 1})
        assert value == 0.0
        assert detail["state"] == "observed"

    def test_more_sources_score_higher(self):
        low, _ = sf.corroboration_velocity({"sources_15m": 2, "sources_60m": 2})
        high, _ = sf.corroboration_velocity({"sources_15m": 3, "sources_60m": 5})
        assert 0.0 < low < high <= 1.0

    def test_no_story_is_a_named_state_not_a_crash(self):
        value, detail = sf.corroboration_velocity(None)
        assert value == 0.0 and detail["state"] == "no-story"

    def test_it_scores_the_match_weighted_count_not_the_raw_one(self):
        """Review F-6: five aggregators reprinting one wire is not five witnesses."""
        fanout = {"sources_15m": 5, "sources_60m": 5,
                  "weighted_15m": 1.0, "weighted_60m": 1.0}
        independent = {"sources_15m": 3, "sources_60m": 3,
                       "weighted_15m": 3.0, "weighted_60m": 3.0}
        fan_value, fan_detail = sf.corroboration_velocity(fanout)
        ind_value, _ = sf.corroboration_velocity(independent)
        assert fan_detail["basis"] == "match-weighted"
        assert fan_value < ind_value, "syndication fan-out must not outscore real corroboration"
        assert fan_value == 0.0

    def test_the_raw_basis_stays_available_for_comparison(self):
        story = {"sources_15m": 5, "sources_60m": 5,
                 "weighted_15m": 1.0, "weighted_60m": 1.0}
        value, detail = sf.corroboration_velocity(
            story, cfg={"use_weighted_sources": False})
        assert detail["basis"] == "raw" and value > 0

    def test_the_residual_is_stated_not_hidden(self):
        _, detail = sf.corroboration_velocity({"sources_15m": 2, "sources_60m": 2,
                                               "weighted_15m": 2.0, "weighted_60m": 2.0})
        assert "publisher map" in detail["residual"]


class TestNovelty:
    def test_cold_start_is_neutral_and_says_so(self):
        corpus = sf.SignalCorpus({}, cfg={})
        corpus.observe(_item("a"), now=NOW)
        value, detail = corpus.novelty(_item("a"))
        assert value == 0.5
        assert detail["state"] == "cold-start"
        assert "NOT a measurement" in detail["note"]

    def test_a_repeated_story_is_less_novel_than_a_fresh_one(self):
        corpus = sf.SignalCorpus({}, cfg={"novelty_min_docs": 3})
        for i in range(12):
            corpus.observe(_item(f"r{i}", "Tariff talks continue in Geneva",
                                 body="Trade delegations met again."), now=NOW)
        stale, _ = corpus.novelty(_item("x", "Tariff talks continue in Geneva",
                                        body="Trade delegations met again."))
        fresh, _ = corpus.novelty(_item("y", "Volcano halts Reykjavik flights",
                                        body="Airspace closed overnight."))
        assert fresh > stale

    def test_evicted_tokens_do_not_read_as_maximally_novel(self):
        """Review F-4(a): bucket-cap eviction deletes exactly the RARE tokens.

        A naive DF sum then reported df=0 for a token the corpus has seen
        hundreds of times and handed it maximum IDF — the corpus's own memory
        loss reading as freshness.
        """
        corpus = sf.SignalCorpus({}, cfg={"novelty_min_docs": 3,
                                          "max_tokens_per_bucket": 5})
        for i in range(60):
            corpus.observe(_item(f"r{i}", f"Tariff talks continue in Geneva round {i}"),
                           now=NOW)
        for i in range(60):
            corpus.observe(_item(f"f{i}", "Filler filler filler filler payroll"), now=NOW)
        corpus.prune(NOW)
        assert corpus.capped_days() >= 1, "fixture must actually trigger the cap"
        value, detail = corpus.novelty(
            _item("x", "Tariff talks continue in Geneva round 7"))
        assert detail["df_is_floor"] is True
        assert value < 1.0, "an evicted-but-common token must not read as brand new"

    def test_document_frequency_floors_evicted_tokens_at_one(self):
        corpus = sf.SignalCorpus({}, cfg={"max_tokens_per_bucket": 1})
        corpus.observe(_item("a", "alpha beta gamma delta"), now=NOW)
        corpus.prune(NOW)
        assert corpus.document_frequency("definitely-evicted-token") == 1

    def test_too_few_tokens_reports_a_null_not_a_number(self):
        """Review F-4(b): top-3-of-2 is a different statistic from top-3-of-12."""
        corpus = sf.SignalCorpus({}, cfg={"novelty_min_docs": 1})
        for i in range(20):
            corpus.observe(_item(f"o{i}", f"Filler story number {i} about markets"),
                           now=NOW)
        value, detail = corpus.novelty(_item("x", "Fed cuts", body=""))
        assert detail["state"] == "too-few-tokens"
        assert value == 0.5
        assert "NOT a measurement" in detail["note"]

    def test_novelty_excludes_the_items_own_contribution(self):
        corpus = sf.SignalCorpus({}, cfg={"novelty_min_docs": 2})
        item = _item("a", "Unique zebra quokka headline", body="")
        corpus.observe(item, now=NOW)
        for i in range(9):
            corpus.observe(_item(f"o{i}", f"Filler story number {i}"), now=NOW)
        value, detail = corpus.novelty(item)
        assert detail["state"] == "observed"
        assert value > 0.5


class TestKeywordHeat:
    def test_cold_start_is_zero_and_says_so(self):
        corpus = sf.SignalCorpus({}, cfg={})
        corpus.observe(_item("a"), now=NOW)
        value, detail = corpus.keyword_heat(_item("a"), now=NOW)
        assert value == 0.0 and detail["state"] == "cold-start"

    def test_a_burst_beats_a_steady_term(self):
        corpus = sf.SignalCorpus({}, cfg={"burst_min_hours": 3})
        # 10 quiet hours: "markets" every hour, "tariff" never.
        for hour in range(10):
            when = NOW - timedelta(hours=10 - hour)
            for j in range(10):
                corpus.observe(_item(f"q{hour}{j}", "Markets drift sideways today"),
                               now=when)
        # Current hour: a tariff burst, over the recent-bucket doc floor.
        for j in range(10):
            corpus.observe(_item(f"b{j}", "Tariff shock jolts tariff-exposed names"),
                           now=NOW)
        hot, hot_detail = corpus.keyword_heat(
            _item("x", "Tariff shock jolts tariff-exposed names"), now=NOW)
        cold, _ = corpus.keyword_heat(_item("y", "Markets drift sideways today"),
                                      now=NOW)
        assert hot_detail["state"] == "observed"
        assert hot > cold
        assert hot_detail["burst"] is True

    def test_heat_can_reach_the_top_of_its_range(self):
        """Review F-3(a): burst_min_std 0.5 capped z at 2.0, so heat could never
        exceed 0.5 — half the feature's declared range was unreachable and the
        ordering weight was silently halved."""
        corpus = sf.SignalCorpus({}, cfg={"burst_min_hours": 3})
        for hour in range(10):
            when = NOW - timedelta(hours=10 - hour)
            for j in range(10):
                corpus.observe(_item(f"q{hour}{j}", "Markets drift sideways today"),
                               now=when)
        for j in range(10):
            corpus.observe(_item(f"b{j}", "Tariff shock jolts tariff-exposed names"),
                           now=NOW)
        value, detail = corpus.keyword_heat(
            _item("x", "Tariff shock jolts tariff-exposed names"), now=NOW)
        assert detail["z"] > 2.0, "z must be able to exceed the old hard ceiling"
        assert value > 0.5, "heat must be able to exceed the old hard ceiling"

    def test_min_std_default_is_near_measured_reality(self):
        """The floor exists to avoid dividing by ~0, not to cap the statistic."""
        assert sf._CORPUS_DEFAULTS["burst_min_std"] <= 0.1

    def test_a_thin_partial_hour_cannot_fire_a_burst(self):
        """Review F-3(b): one document in a fresh hour reads rate=1.0.

        The recent bucket is a PARTIAL hour compared against complete ones, so
        without a floor the same story scored ~15x differently depending on
        where in the hour it happened to land.
        """
        corpus = sf.SignalCorpus({}, cfg={"burst_min_hours": 3})
        for hour in range(8):
            when = NOW - timedelta(hours=8 - hour)
            for j in range(10):
                corpus.observe(_item(f"q{hour}{j}", "Markets drift sideways today"),
                               now=when)
        # A brand-new hour holding ONE document that contains the token.
        corpus.observe(_item("fresh", "Tariff shock jolts tariff-exposed names"),
                       now=NOW)
        value, detail = corpus.keyword_heat(
            _item("x", "Tariff shock jolts tariff-exposed names"), now=NOW)
        assert detail["state"] == "recent-bucket-thin"
        assert value == 0.0
        assert "NOT a measured absence" in detail["note"]

    def test_clock_position_within_the_hour_does_not_swing_the_score(self):
        """The same corpus scored at :05 and at :55 must agree."""
        def _corpus_at(minute: int):
            corpus = sf.SignalCorpus({}, cfg={"burst_min_hours": 3})
            when_now = NOW.replace(minute=minute)
            for hour in range(8):
                when = when_now - timedelta(hours=8 - hour)
                for j in range(10):
                    corpus.observe(_item(f"q{hour}{j}", "Markets drift sideways"),
                                   now=when)
            for j in range(10):
                corpus.observe(_item(f"b{j}", "Tariff shock jolts tariff names"),
                               now=when_now)
            return corpus.keyword_heat(_item("x", "Tariff shock jolts tariff names"),
                                       now=when_now)

        early, _ = _corpus_at(5)
        late, _ = _corpus_at(55)
        assert early == late

    def test_rates_not_counts_so_a_busy_hour_is_not_a_burst(self):
        """A doubled news hour must not make every token look bursty."""
        corpus = sf.SignalCorpus({}, cfg={"burst_min_hours": 3})
        for hour in range(8):
            when = NOW - timedelta(hours=8 - hour)
            for j in range(3):
                corpus.observe(_item(f"q{hour}{j}", "Markets drift sideways today"),
                               now=when)
        for j in range(30):  # 10x the volume, same composition
            corpus.observe(_item(f"b{j}", "Markets drift sideways today"), now=NOW)
        value, detail = corpus.keyword_heat(_item("x", "Markets drift sideways today"),
                                            now=NOW)
        assert detail["state"] == "observed"
        assert value == 0.0

    def test_prune_bounds_the_state(self):
        corpus = sf.SignalCorpus({}, cfg={"burst_window_h": 2, "novelty_window_d": 1})
        corpus.observe(_item("old"), now=NOW - timedelta(days=10))
        corpus.observe(_item("new"), now=NOW)
        assert corpus.prune(NOW) >= 1
        assert len(corpus.hours) == 1


class TestSourceAuthority:
    def test_neutral_prior_until_min_samples_and_it_says_so(self):
        store = sf.AuthorityStore({}, cfg={"min_samples": 3})
        value, detail = store.prior(_item("a", source="cnbc"))
        assert value == 0.5
        assert detail["state"] == "neutral-prior"
        assert "NOT a measurement" in detail["note"]

    def test_observed_after_enough_samples(self):
        store = sf.AuthorityStore({}, cfg={"min_samples": 2})
        for i in range(4):
            store.observe(_item(f"i{i}", x_handle="Loud",
                                x_engagement={"likes": 400, "retweets": 200,
                                              "replies": 30, "views": 90000}),
                          now=NOW)
        value, detail = store.prior(_item("z", x_handle="Loud"))
        assert detail["state"] == "observed"
        assert value > 0.5

    def test_a_source_with_no_engagement_stays_neutral_forever(self):
        store = sf.AuthorityStore({}, cfg={"min_samples": 1})
        for i in range(50):
            assert store.observe(_item(f"i{i}", source="rss_wire")) is False
        value, detail = store.prior(_item("z", source="rss_wire"))
        assert value == 0.5 and detail["state"] == "neutral-prior"

    def test_store_is_bounded(self):
        store = sf.AuthorityStore({}, cfg={"max_sources": 3})
        for i in range(10):
            store.observe(_item(f"i{i}", x_handle=f"h{i}",
                                x_engagement={"likes": i}), now=NOW)
        assert len(store.sources) <= 3


class TestToneExtremity:
    def test_absent_join_is_zero_contribution_and_named(self):
        value, detail = sf.tone_extremity(_item("a"), {})
        assert value == 0.0 and detail["state"] == "absent"

    def test_present_join_scores(self):
        lookup = {"wire.example/a": {"tone": -8.0}}
        value, detail = sf.tone_extremity(_item("a", url="https://wire.example/a"),
                                          lookup)
        assert detail["state"] == "observed"
        assert value == pytest.approx(0.8)

    def test_unmatched_row_is_absent_not_zero_tone(self):
        value, detail = sf.tone_extremity(_item("a", url="https://other.example/z"),
                                          {"wire.example/a": {"tone": 9.0}})
        assert value == 0.0 and detail["state"] == "absent"

    def test_load_tone_lookup_returns_empty_when_nothing_exists(self, tmp_path):
        assert sf.load_tone_lookup(tmp_path, cfg={"paths": ["nope.json"]}) == {}

    def test_load_tone_lookup_reads_a_local_file(self, tmp_path):
        path = tmp_path / "tone.json"
        path.write_text(json.dumps({"a.com/x": {"tone": 3.0}}), encoding="utf-8")
        assert sf.load_tone_lookup(tmp_path, cfg={"paths": ["tone.json"]})["a.com/x"]

    def test_absent_tone_shifts_every_item_equally(self):
        """Zero-contribution must be RANK-NEUTRAL, not a silent penalty."""
        values_a = {name: 0.5 for name in sf.FEATURE_NAMES}
        values_b = dict(values_a, corroboration_velocity=0.9)
        with_tone_a, _ = sf.rank_score(60, dict(values_a, tone_extremity=0.0))
        with_tone_b, _ = sf.rank_score(60, dict(values_b, tone_extremity=0.0))
        assert with_tone_b > with_tone_a


class TestHeadlineShape:
    def test_numbers_and_entities_lift_the_score(self):
        bare, bare_detail = sf.headline_shape(_item("a", "Something happened"))
        rich, rich_detail = sf.headline_shape(
            _item("b", "CPI rises 3.2% as payrolls add 250,000 jobs"),
            matched={"tickers": ["AAPL"], "macro_keys": ["cpi"], "sectors": []},
        )
        assert rich > bare
        assert rich_detail["has_numbers"] is True
        assert bare_detail["has_numbers"] is False

    def test_title_case_does_not_collapse_into_one_entity(self):
        """Review F-20: the greedy run-glue read publisher HOUSE STYLE.

        "Bank Of America Corp Reports Record Quarterly Results" counted as ONE
        entity, so title-case outlets scored 1 and sentence-case outlets
        covering the same story scored 5 — the feature ranked stylebooks.
        """
        _, title_case = sf.headline_shape(
            _item("a", "Bank Of America Corp Reports Record Quarterly Results"))
        _, sentence_case = sf.headline_shape(
            _item("b", "Bank of America reports record quarterly results"))
        assert title_case["entities"] > 1
        assert title_case["entities"] >= sentence_case["entities"]

    def test_length_bands(self):
        _, short = sf.headline_shape(_item("a", "Fed cuts"))
        _, medium = sf.headline_shape(
            _item("a", "Fed cuts rates by 25 basis points at the July meeting"))
        _, long_ = sf.headline_shape(_item("a", "Fed cuts rates by 25 basis points as "
                                                "policymakers weigh a softening labour "
                                                "market, cooling inflation and a slower "
                                                "second half"))
        assert short["length_band"] == "short"
        assert medium["length_band"] == "medium"
        assert long_["length_band"] == "long"


class TestComputeFeatures:
    def test_all_six_features_present_with_no_inputs_at_all(self):
        out = sf.compute_features(_item("a"))
        assert set(out["values"]) == set(sf.FEATURE_NAMES)
        assert set(out["detail"]) == set(sf.FEATURE_NAMES)
        for name in sf.FEATURE_NAMES:
            assert "state" in out["detail"][name]

    def test_values_are_bounded(self):
        out = sf.compute_features(
            _item("a", "CPI 9.9% 8.8% 7.7%"),
            matched={"tickers": ["A", "B", "C"], "macro_keys": ["cpi"], "sectors": ["x"]},
            story={"sources_15m": 99, "sources_60m": 99},
        )
        for name, value in out["values"].items():
            assert 0.0 <= value <= 1.0, name


class TestSourceAuthorityIsInert:
    """Review F-5, adjudicated: keep the machinery, zero the ordering weight."""

    def test_authority_carries_zero_rank_weight_by_default(self):
        assert sf.rank_weights({})["source_authority"] == 0.0
        assert json_config()["breaking"]["scoring"]["rank_weights"]["source_authority"] == 0.0

    def test_authority_cannot_move_the_ordering(self):
        base = {name: 0.5 for name in sf.FEATURE_NAMES}
        low, _ = sf.rank_score(60, dict(base, source_authority=0.0))
        high, _ = sf.rank_score(60, dict(base, source_authority=1.0))
        assert low == high, "an inert feature must not reorder anything"

    def test_the_accrual_machinery_still_runs(self):
        """Inert in the ORDERING, not deleted — the label loop still needs it."""
        store = sf.AuthorityStore({}, cfg={"min_samples": 2})
        for i in range(3):
            assert store.observe(_item(f"i{i}", x_handle="Loud",
                                       x_engagement={"likes": 100}), now=NOW) is True
        value, detail = store.prior(_item("z", x_handle="Loud"))
        assert detail["state"] == "observed" and value > 0

    def test_the_two_arming_preconditions_are_documented(self):
        text = (ROOT / "docs" / "scoring_brain.md").read_text(encoding="utf-8")
        assert "fixed post age" in text.lower()
        assert "measured axis" in text.lower()
        source = (ROOT / "engine" / "marketing" / "signal_features.py").read_text(encoding="utf-8")
        assert "fixed-age refresh is deliberately NOT attempted" in source


class TestRankScore:
    def test_weights_sum_and_are_config_overridable(self):
        assert sum(sf.rank_weights({}).values()) == pytest.approx(1.0)
        weights = sf.rank_weights({"rank_weights": {"salience": 0.9}})
        assert weights["salience"] == 0.9

    def test_salience_is_the_dominant_term(self):
        weights = sf.rank_weights({})
        assert weights["salience"] > sum(
            weights[name] for name in sf.FEATURE_NAMES) / 2

    def test_score_is_monotone_in_salience(self):
        values = {name: 0.5 for name in sf.FEATURE_NAMES}
        low, _ = sf.rank_score(10, values)
        high, _ = sf.rank_score(90, values)
        assert high > low

    def test_contributions_are_inspectable(self):
        _, detail = sf.rank_score(50, {name: 0.5 for name in sf.FEATURE_NAMES})
        assert set(detail["contributions"]) == {"salience", *sf.FEATURE_NAMES}


# ═════════════════════════════════════════════════════════════════════════════
# score_item — `_components` for 100% of items
# ═════════════════════════════════════════════════════════════════════════════

class TestScoreItemComponents:
    def test_components_present_without_any_context(self):
        scored = score_item(_item("a"), now=NOW)
        comp = scored["_components"]
        assert comp["context"] == "no-context"
        assert set(comp["features"]) == set(sf.FEATURE_NAMES)
        assert comp["scoring_version"] == "xg-w5.1"

    def test_components_present_with_context(self):
        spine = ss.StorySpine({}, cfg={})
        story = spine.assign(_item("a"), now=NOW)
        scored = score_item(_item("a"), now=NOW, context={
            "story": story, "corpus": sf.SignalCorpus({}), "authority": sf.AuthorityStore({}),
            "tone_lookup": {},
        })
        assert scored["_components"]["context"] == "present"
        assert scored["_components"]["story"]["story_id"] == story["story_id"]

    def test_legacy_salience_components_keep_their_shape(self):
        scored = score_item(_item("a"), now=NOW)
        for key in ("base", "tier_bonus", "kw_bonus", "ticker_bonus",
                    "market_hours_weight", "raw", "capped"):
            assert key in scored["_salience_components"]

    def test_salience_is_unchanged_by_the_l1_layer_by_default(self):
        plain = score_item(_item("a"), now=NOW)
        with_ctx = score_item(_item("a"), now=NOW, context={
            "story": {"sources_15m": 5, "sources_60m": 5},
            "corpus": None, "authority": None, "tone_lookup": {},
        })
        assert plain["salience"] == with_ctx["salience"]

    def test_demotion_can_only_lower_salience_and_is_off_by_default(self):
        base = score_item(_item("a"), now=NOW)
        assert base["_salience_components"]["demotion_factor"] == 1.0
        armed = score_item(
            _item("a"), now=NOW,
            cfg={"scoring": {"demote_enabled": True, "demote_floor": 0.5}},
            context={"story": {"sources_15m": 1, "sources_60m": 1}},
        )
        assert armed["salience"] < base["salience"]

    def test_demotion_multiplier_is_clamped_at_one(self):
        """No configuration may make a feature RAISE salience over a floor."""
        base = score_item(_item("a"), now=NOW)
        armed = score_item(
            _item("a"), now=NOW,
            cfg={"scoring": {"demote_enabled": True, "demote_floor": 5.0}},
            context={"story": {"sources_15m": 9, "sources_60m": 9}},
        )
        assert armed["salience"] <= base["salience"]

    def test_a_feature_failure_degrades_and_does_not_raise(self):
        class Boom:
            def keyword_heat(self, *a, **k):
                raise RuntimeError("boom")

            def novelty(self, *a, **k):
                raise RuntimeError("boom")

            def item_tokens(self, *a, **k):
                raise RuntimeError("boom")

        scored = score_item(_item("a"), now=NOW, context={"corpus": Boom()})
        assert "features_error" in scored["_components"]
        assert scored["salience"] > 0

    def test_rank_score_is_present_and_bounded(self):
        scored = score_item(_item("a"), now=NOW)
        assert 0.0 <= scored["rank_score"] <= 1.0


# ═════════════════════════════════════════════════════════════════════════════
# PRODUCTION WIRING — press_lane.run_press_tick
# ═════════════════════════════════════════════════════════════════════════════

def _press_cfg() -> dict:
    return {"satire_blocklist": ["HalfwayPost"],
            "wire": {"flagship_top_k_per_day": 3, "flagship_salience_floor": 70.0,
                     "voice": {"enabled": False}, "tape": {"enabled": False}}}


def _marketing_cfg(**scoring) -> dict:
    return {"breaking": {"salience_threshold": 60, "llm": {"enabled": False},
                         "scoring": scoring,
                         "garbage_gate": {"enabled": True}}}


def _run(items, tmp_path, *, cfg=None, state=None, now=None):
    from engine.marketing.press_lane import run_press_tick
    return run_press_tick(
        items, root=tmp_path, now=now or NOW, cfg=cfg or _marketing_cfg(),
        press_cfg=_press_cfg(), state=state if state is not None else {},
        seen_ids=set(), dry_run=True,
    )


class TestProductionWiring:
    def test_every_ingested_item_carries_components(self):
        items = [_item(f"i{i}", f"CPI rises {i}.1% in June",
                       url=f"https://w.example/{i}") for i in range(5)]
        result = _run(items, Path("."))
        rows = [r for r in result["corpus"] if not r["outcome"].startswith("blocked")]
        assert len(rows) == 5
        for row in rows:
            assert row["_components"]["features"], row["item_id"]
            assert set(row["_components"]["features"]) == set(sf.FEATURE_NAMES)

    def test_the_gate_drops_garbage_before_scoring(self):
        items = [
            _item("good", "CPI rises 3.2% in June", url="https://w.example/1"),
            _item("promo", "Sign up now for our best deals", url="https://w.example/2"),
            _item("horo", "Your daily horoscope", url="https://w.example/3"),
            _item("satire", "Fed abolishes money", url="https://w.example/4",
                  x_handle="HalfwayPost"),
        ]
        result = _run(items, Path("."))
        reasons = {row["id"]: row["reason"] for row in result["blocked"]}
        assert reasons == {"promo": "promo_spam", "horo": "non_story",
                           "satire": "satire_blocklist"}
        scored_ids = {r["item_id"] for r in result["corpus"]
                      if not r["outcome"].startswith("blocked")}
        assert scored_ids == {"good"}

    def test_gate_drops_are_recorded_as_corpus_rows_too(self):
        result = _run([_item("horo", "Your daily horoscope")], Path("."))
        row = result["corpus"][0]
        assert row["outcome"] == "blocked:non_story"

    def test_the_story_spine_persists_into_the_daemon_state(self):
        state: dict = {}
        _run([_item("a", url="https://w.example/1")], Path("."), state=state)
        assert state["story_spine"]["stories"]
        assert state["signal_corpus"]["hours"]
        # And the whole state stays JSON-persistable (the daemon writes it out).
        json.dumps(state)

    def test_two_sources_in_one_tick_share_a_story_and_a_velocity(self):
        """The refresh pass: list order must not decide a story-level feature.

        Two HOSTS carrying one mirror-identified claim, so this holds with or
        without the optional near-dup pass installed.
        """
        items = [
            _item("a", "CPI rises 3.2% in June", url="https://one.example/1"),
            _item("b", "CPI rises 3.2% in June",
                  url="https://one.example/1?utm_source=x"),
        ]
        result = _run(items, Path("."))
        rows = {r["item_id"]: r for r in result["corpus"]}
        assert len(rows) == 2, "distinct feed ids both ingest"
        assert rows["a"]["story_id"] == rows["b"]["story_id"]
        detail_a = rows["a"]["_components"]["feature_detail"]["corroboration_velocity"]
        detail_b = rows["b"]["_components"]["feature_detail"]["corroboration_velocity"]
        # THE REFRESH PASS: both rows read the SAME story-level numbers. Before
        # it, the first item of a batch saw the story as it stood mid-loop and
        # the second saw it complete — one story, two velocities, decided by
        # list order.
        assert detail_a["sources_15m"] == detail_b["sources_15m"]
        assert detail_a["match_mix_15m"] == detail_b["match_mix_15m"]
        assert (rows["a"]["_components"]["features"]["corroboration_velocity"]
                == rows["b"]["_components"]["features"]["corroboration_velocity"])

    def test_a_non_emitting_item_is_rowed_once_per_window_not_once_per_tick(self):
        """Review F-1, the blocker.

        `seen` only advances on emit/refusal, so a digest / below-floor /
        top-K / story-locked item is re-ingested every 120 seconds forever. The
        reviewer's 6-hour replay of 3 stale items wrote 560 rows over 23 ids.
        The corpus is a SAMPLE, so its unit must be the item.
        """
        state: dict = {}
        items = [_item("weak", "Analyst notes a modest move",
                       url="https://w.example/1", tier="aggregator",
                       body="Nothing much happened.")]
        rows = 0
        for tick in range(30):  # one hour at the daemon's 120s cadence
            result = _run(items, Path("."), state=state,
                          now=NOW + timedelta(seconds=120 * tick))
            rows += len(result["corpus"])
        assert rows == 1, f"one item, one window, one row — got {rows}"

    def test_the_window_reopens_after_it_elapses(self):
        state: dict = {}
        items = [_item("weak", "Analyst notes a modest move",
                       url="https://w.example/1", tier="aggregator")]
        first = _run(items, Path("."), state=state, now=NOW)
        again = _run(items, Path("."), state=state, now=NOW + timedelta(hours=25))
        assert len(first["corpus"]) == 1 and len(again["corpus"]) == 1

    def test_the_window_is_a_config_key(self):
        state: dict = {}
        items = [_item("weak", "Analyst notes a modest move",
                       url="https://w.example/1", tier="aggregator")]
        cfg = _marketing_cfg(corpus_row_window_h=0.25)
        _run(items, Path("."), state=state, cfg=cfg, now=NOW)
        again = _run(items, Path("."), state=state, cfg=cfg,
                     now=NOW + timedelta(minutes=20))
        assert len(again["corpus"]) == 1
        assert "corpus_row_window_h" in json_config()["breaking"]["scoring"]

    def test_the_dedupe_ledger_is_bounded(self):
        state: dict = {}
        _run([_item("a", url="https://w.example/1")], Path("."), state=state, now=NOW)
        _run([_item("b", url="https://w.example/2")], Path("."), state=state,
             now=NOW + timedelta(hours=48))
        assert len(state["corpus_rowed"]) == 1, "expired entries must be pruned"

    def test_garbage_drops_are_also_windowed(self):
        state: dict = {}
        items = [_item("horo", "Your daily horoscope", url="https://w.example/1")]
        total = sum(len(_run(items, Path("."), state=state,
                             now=NOW + timedelta(seconds=120 * t))["corpus"])
                    for t in range(10))
        assert total == 1

    def test_rank_ordering_is_dark_by_default(self):
        from engine.marketing import press_lane

        source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(encoding="utf-8")
        assert 'scoring_cfg.get("rank_ordering", False)' in source
        cfg = json_config()
        assert cfg["breaking"]["scoring"]["rank_ordering"] is False
        assert cfg["breaking"]["scoring"]["demote_enabled"] is False
        assert press_lane is not None

    def test_ordering_follows_salience_when_dark_and_rank_when_armed(self):
        # A high-salience macro print vs a low-salience item that scores well on
        # shape/novelty. Dark: salience wins. Armed: rank_score decides.
        items = [
            _item("low", "Chip maker names new CFO", url="https://w.example/1",
                  tier="aggregator", body="Company statement."),
            _item("high", "CPI rises 3.2% as payrolls add 250,000 jobs",
                  url="https://w.example/2", tier="official",
                  body="Inflation and the labour market both moved."),
        ]
        dark = _run(items, Path("."), cfg=_marketing_cfg(rank_ordering=False))
        armed = _run(items, Path("."), cfg=_marketing_cfg(rank_ordering=True))
        dark_rows = [r for r in dark["corpus"]]
        armed_rows = [r for r in armed["corpus"]]
        assert dark_rows == sorted(dark_rows, key=lambda r: -(r["salience"] or 0))
        assert armed_rows == sorted(armed_rows, key=lambda r: -(r["rank_score"] or 0))

    def test_scoring_can_be_disabled_wholesale(self):
        result = _run([_item("a")], Path("."), cfg=_marketing_cfg(enabled=False))
        row = result["corpus"][0]
        # Review F-16: features are still computed (score_item always emits
        # them), but the layer's stores were never constructed, so the honest
        # state is "empty-context" — calling that "present" was a green light
        # for a layer that did nothing.
        assert row["_components"]["context"] == "empty-context"
        assert row["story_id"] == ""


class TestSuccessfulEmission:
    """Review F-10: the wave had ZERO coverage of an item that actually emits.

    Every wiring test ran with dry_run=True, so the whole back half —
    stamp_value_gate, make_item, validate_item, enqueue — was unexercised, and a
    provenance block that failed schema validation would have shipped green.
    """

    def _emit(self, tmp_path):
        from engine.marketing.press_lane import run_press_tick

        item = _item("hot", "CPI rises 3.2% as payrolls add 250,000 jobs",
                     url="https://one.example/1", tier="official",
                     body="Inflation and the labour market both moved sharply.")
        return run_press_tick(
            [item], root=tmp_path, now=NOW, cfg=_marketing_cfg(),
            press_cfg=_press_cfg(), state={}, seen_ids=set(),
            dry_run=False, spool=True,
        )

    def test_an_item_flows_all_the_way_to_the_queue(self, tmp_path):
        result = self._emit(tmp_path)
        assert len(result["emitted"]) == 1, result["skipped"] + result["digest"]

    def test_the_scoring_provenance_survives_onto_the_enqueued_item(self, tmp_path):
        result = self._emit(tmp_path)
        spool = tmp_path / "data" / "marketing" / "outbox" / "items-host.jsonl"
        assert spool.exists(), "spool=True must write the gitignored host queue"
        rows = [json.loads(line) for line in
                spool.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(rows) == 1
        scoring = (rows[0].get("source") or {}).get("scoring") or {}
        assert scoring.get("version")
        assert set(scoring.get("features") or {}) == set(sf.FEATURE_NAMES)
        assert scoring.get("story_id")
        assert "rank_score" in scoring

    def test_the_enqueued_item_still_validates(self, tmp_path):
        from engine.marketing import outbox as ob

        result = self._emit(tmp_path)
        assert ob.validate_item(result["emitted"][0]) == []

    def test_no_score_leaks_into_the_post_text(self, tmp_path):
        result = self._emit(tmp_path)
        text = str(result["emitted"][0].get("text", ""))
        for banned in ("rank_score", "salience", "_components", "story_id"):
            assert banned not in text


class TestGateOrdering:
    """A score may REORDER and DEPRIORITIZE. It may never publish."""

    def test_a_top_ranked_political_item_still_falls_to_the_digest(self):
        # Single-source uncorroborated policy claim: corroboration_decision sends
        # it to the digest regardless of any score.
        item = _item("pol", "New tariffs on imports announced by executive order",
                     url="https://w.example/1", tier="official",
                     body="The order raises tariffs across several categories.")
        result = _run([item], Path("."), cfg=_marketing_cfg(rank_ordering=True))
        assert [row["id"] for row in result["digest"]] == ["pol"]
        assert result["emitted"] == []

    def test_a_top_ranked_item_below_the_floor_still_does_not_emit(self):
        item = _item("weak", "Analyst notes a modest move", url="https://w.example/1",
                     tier="aggregator", body="Nothing much happened.")
        result = _run([item], Path("."), cfg=_marketing_cfg(rank_ordering=True))
        assert result["emitted"] == []
        assert any(row["reason"] == "below_flagship_floor" for row in result["skipped"])

    def test_no_gate_reads_rank_score(self):
        """Static proof: rank_score appears ONLY in the sort and in provenance."""
        source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "run_press_tick")
        uses = [n for n in ast.walk(func)
                if isinstance(n, ast.Constant) and n.value == "rank_score"]
        # The two lambdas inside the ordering sort are the only reads.
        assert len(uses) == 1, "rank_score must be read only by the ordering sort"

    def test_the_floor_compares_salience_not_rank(self):
        source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(encoding="utf-8")
        assert 'if s.get("salience", 0.0) < floor:' in source


class TestNoScoreIsUserFacing:
    def test_rail_items_carry_no_score(self):
        items = [_item(f"i{i}", f"CPI rises {i}.2% in June",
                       url=f"https://w.example/{i}") for i in range(3)]
        result = _run(items, Path("."))
        assert result["rail"], "fixture should produce rail items"
        for row in result["rail"]:
            for banned in ("rank_score", "_components", "salience",
                           "_salience_components", "story_id"):
                assert banned not in row, f"rail item leaked {banned}"

    def test_the_rail_builder_never_copies_the_components(self):
        source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(encoding="utf-8")
        builder = source.split("def _build_rail_item", 1)[1].split("\ndef ", 1)[0]
        for banned in ("_components", "rank_score", "salience"):
            assert banned not in builder, f"_build_rail_item references {banned}"

    def test_rail_order_is_returned_internally_and_keyed_to_the_rail(self):
        """The ranked view the Mastermind brain wants ships as `_rail_order` — an
        UNDERSCORE key the daemon folds into host-local state and expresses as
        element order in the non-public wire_rank sidecar. It exists so nothing
        has to put a number on a rail item; the two tests above stay green."""
        items = [_item(f"i{i}", f"CPI rises {i}.2% in June",
                       url=f"https://w.example/{i}") for i in range(3)]
        result = _run(items, Path("."))
        order = result["_rail_order"]
        assert isinstance(order, dict) and order, "the internal order map is missing"
        assert set(order) == {row["id"] for row in result["rail"]}, (
            "the map must cover exactly this tick's rail items"
        )
        assert all(isinstance(v, float) for v in order.values())

    def test_no_public_return_key_carries_the_ordering_map(self):
        """`_rail_order` must stay underscore-prefixed: every non-underscore key of
        the tick result is a candidate for a served payload."""
        items = [_item("i0", "CPI rises 3.2% in June", url="https://w.example/0")]
        result = _run(items, Path("."))
        assert "_rail_order" in result
        assert "rail_order" not in result
        for row in result["rail"]:
            assert "_rail_order" not in row and "rail_order" not in row

    def test_a_primed_cold_start_returns_an_empty_order_map(self):
        """Shape stability: the prime early-return is a second return statement,
        and the daemon reads the key unconditionally."""
        items = [_item("i0", "CPI rises 3.2% in June", url="https://w.example/0")]
        from engine.marketing.press_lane import run_press_tick
        result = run_press_tick(
            items, root=Path("."), now=NOW, cfg=_marketing_cfg(),
            press_cfg=_press_cfg(), state={}, seen_ids=set(), dry_run=True,
            prime=True,
        )
        assert result["_rail_order"] == {}


class TestNoLlmAnywhere:
    @pytest.mark.parametrize("module", [
        "engine/marketing/story_spine.py",
        "engine/marketing/signal_features.py",
        "engine/marketing/garbage_gate.py",
        "engine/marketing/golden_set.py",
    ])
    def test_the_scoring_modules_contain_no_model_call(self, module):
        """DO_NOT_REBUILD: LLM-originated signals/scores/escalations are FORBIDDEN."""
        source = (ROOT / module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            low = name.lower()
            for banned in ("anthropic", "openai", "llm", "claude", "deepseek",
                           "engine.llm", "lib.llm"):
                assert banned not in low, f"{module} imports {name}"


class TestAnnotationLineStart:
    """House law: ::warning/::notice must START the line, never via a logger.

    The repo-wide guard (tests/test_gh_annotation_line_start.py, its own CI job)
    rglobs engine/ and scripts/, so it already covers every module this wave
    adds. What is asserted HERE is only that the new modules are inside that
    guard's scan scope and are not exempted — a new module placed outside
    engine/scripts, or added to EXEMPT, would go unguarded silently.
    """

    NEW_MODULES = (
        "engine/marketing/story_spine.py",
        "engine/marketing/signal_features.py",
        "engine/marketing/garbage_gate.py",
        "engine/marketing/golden_set.py",
        "engine/marketing/breaking_relevance.py",
        "engine/marketing/press_lane.py",
        "scripts/marketing_golden_set.py",
        "scripts/marketing_fastlane_daemon.py",
    )

    @staticmethod
    def _guard():
        import importlib.util  # noqa: PLC0415

        path = ROOT / "tests" / "test_gh_annotation_line_start.py"
        spec = importlib.util.spec_from_file_location("_gh_annotation_guard", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_module_is_covered_by_the_repo_annotation_guard(self, module):
        guard = self._guard()
        assert module.split("/", 1)[0] in guard.SCAN_DIRS
        assert module not in guard.EXEMPT
        assert (ROOT / module).exists()

    @pytest.mark.parametrize("module", NEW_MODULES)
    def test_no_annotation_is_emitted_through_a_logger(self, module):
        """The specific defect the guard exists for, re-pinned per new module."""
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "error",
                                      "critical", "exception"}:
                continue
            for arg in node.args:
                head = None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    head = arg.value
                elif isinstance(arg, ast.JoinedStr) and arg.values:
                    first = arg.values[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        head = first.value
                assert not (head or "").startswith("::"), (
                    f"{module}:{node.lineno} emits an annotation through a logger")


# ═════════════════════════════════════════════════════════════════════════════
# Golden set + eval harness
# ═════════════════════════════════════════════════════════════════════════════

def _corpus_row(item_id, *, salience, rank, label_hint="", outcome="scored",
                tier="wire", ingested_at="2026-07-28T14:00:00+00:00",
                salience_base=None):
    return {
        "schema": gs.CORPUS_SCHEMA,
        "item_id": item_id,
        "ingested_at": ingested_at,
        "headline": f"headline {item_id} {label_hint}",
        "source": "cnbc_top",
        "source_tier": tier,
        "salience": salience,
        "salience_base": salience if salience_base is None else salience_base,
        "rank_score": rank,
        "outcome": outcome,
        "_components": {"features": {}},
    }


def _duplicated_corpus(distinct=3, copies=90):
    """The reviewer's F-1 corpus: a handful of items, each rowed on every tick."""
    rows = []
    for i in range(distinct):
        for c in range(copies):
            rows.append(_corpus_row(
                f"stale{i}", salience=50 + i, rank=0.5 + i / 100,
                ingested_at=f"2026-07-28T{c % 24:02d}:00:00+00:00"))
    return rows


class TestLabelStore:
    def test_valid_row_passes(self):
        row = gs.make_label_row("i1", "post_worthy", labeler="fable", now=NOW)
        assert gs.validate_label_row(row) == []

    @pytest.mark.parametrize("mutation,expected", [
        ({"label": "excellent"}, "label must be one of"),
        ({"item_id": ""}, "item_id is required"),
        ({"labeler": ""}, "labeler is required"),
        ({"labeled_at": "not-a-date"}, "labeled_at must be ISO-8601"),
        ({"schema": "golden.v9"}, "schema must be"),
    ])
    def test_invalid_rows_are_named(self, mutation, expected):
        row = gs.make_label_row("i1", "useful", labeler="fable", now=NOW)
        row.update(mutation)
        errors = gs.validate_label_row(row)
        assert errors and any(expected in e for e in errors)

    def test_load_labels_skips_bad_rows_loudly(self, tmp_path, capsys):
        path = tmp_path / "labels.jsonl"
        good = gs.make_label_row("ok", "useful", labeler="fable", now=NOW)
        path.write_text(
            json.dumps(good) + "\n{not json}\n"
            + json.dumps({"item_id": "x", "label": "bogus", "labeler": "f"}) + "\n",
            encoding="utf-8",
        )
        labels = gs.load_labels(path=path)
        assert set(labels) == {"ok"}
        out = capsys.readouterr().out
        assert out.count("::warning title=golden-set-bad-row::") == 2
        for line in out.splitlines():
            if "golden-set-bad-row" in line:
                assert line.startswith("::warning")

    def test_missing_store_is_empty_not_an_error(self, tmp_path):
        assert gs.load_labels(path=tmp_path / "nope.jsonl") == {}


class TestCorpusRowDedupe:
    """Review F-1/F-2 — the two blockers, at both ends."""

    def test_export_returns_distinct_items_only(self):
        batch = gs.export_batch(_duplicated_corpus(), n=200, seed="s", now=NOW)
        ids = [i["item_id"] for i in batch["items"]]
        assert len(ids) == len(set(ids)), "a batch must never repeat an item"
        assert batch["returned"] == 3
        assert batch["distinct_corpus_items"] == 3

    def test_precision_ranks_items_not_rows(self):
        rows = _duplicated_corpus(distinct=3, copies=90)
        labels = {f"stale{i}": gs.make_label_row(f"stale{i}", "garbage",
                                                 labeler="f", now=NOW)
                  for i in range(3)}
        result = gs.precision_at_k(rows, labels, k=20)
        assert result["k_effective"] == 3, (
            "k_effective must count DISTINCT items — 20 copies of one story is "
            "not 20 items of evidence")

    def test_evaluate_collapses_duplicates_before_ranking(self):
        report = gs.evaluate(_duplicated_corpus(), {}, k=20)
        assert report["corpus_rows"] == 270
        assert report["distinct_items"] == 3

    def test_dedupe_keeps_the_newest_row_per_item(self):
        rows = [
            _corpus_row("a", salience=10, rank=0.1,
                        ingested_at="2026-07-28T10:00:00+00:00"),
            _corpus_row("a", salience=90, rank=0.9,
                        ingested_at="2026-07-28T18:00:00+00:00"),
        ]
        [kept] = gs.dedupe_rows(rows)
        assert kept["salience"] == 90, "features change as corroboration accrues"


class TestBatchExport:
    def test_batch_is_deterministic(self):
        rows = [_corpus_row(f"i{i}", salience=i, rank=i / 100) for i in range(50)]
        a = gs.export_batch(rows, n=10, seed="s", now=NOW)
        b = gs.export_batch(rows, n=10, seed="s", now=NOW)
        assert [x["item_id"] for x in a["items"]] == [x["item_id"] for x in b["items"]]

    def test_a_different_seed_gives_a_different_batch(self):
        rows = [_corpus_row(f"i{i}", salience=i, rank=i / 100) for i in range(50)]
        a = gs.export_batch(rows, n=10, seed="s1", now=NOW)
        b = gs.export_batch(rows, n=10, seed="s2", now=NOW)
        assert [x["item_id"] for x in a["items"]] != [x["item_id"] for x in b["items"]]

    def test_already_labeled_ids_are_excluded(self):
        rows = [_corpus_row(f"i{i}", salience=i, rank=i / 100) for i in range(20)]
        batch = gs.export_batch(rows, n=20, labeled={"i0", "i1"}, seed="s", now=NOW)
        assert {"i0", "i1"}.isdisjoint({x["item_id"] for x in batch["items"]})
        assert batch["already_labeled"] == 2

    def test_batch_is_stratified_across_salience_bands_and_outcomes(self):
        rows = (
            [_corpus_row(f"h{i}", salience=90, rank=0.9) for i in range(40)]
            + [_corpus_row(f"l{i}", salience=5, rank=0.1) for i in range(40)]
            + [_corpus_row(f"b{i}", salience=0, rank=0.0,
                           outcome="blocked:promo_spam") for i in range(40)]
        )
        batch = gs.export_batch(rows, n=12, seed="s", now=NOW)
        strata = {x["stratum"] for x in batch["items"]}
        assert len(strata) >= 3

    def test_rows_ship_unlabeled_with_the_engine_numbers_printed(self):
        rows = [_corpus_row("i1", salience=71, rank=0.6)]
        item = gs.export_batch(rows, n=1, seed="s", now=NOW)["items"][0]
        assert item["label"] == ""
        assert item["salience"] == 71 and item["rank_score"] == 0.6

    def test_smaller_corpus_than_requested_is_not_an_error(self):
        batch = gs.export_batch([_corpus_row("i1", salience=1, rank=0.1)],
                                n=200, seed="s", now=NOW)
        assert batch["returned"] == 1 and batch["requested"] == 200


class TestEvalHarness:
    def test_no_labels_is_an_honest_null_never_a_pass(self):
        rows = [_corpus_row(f"i{i}", salience=i, rank=i / 100) for i in range(30)]
        report = gs.evaluate(rows, {}, k=20)
        assert report["state"] == "no-labels"
        assert report["precision_at_k"]["rank_score"]["precision"] is None
        assert report["precision_at_k"]["salience"]["precision"] is None
        assert report["beats_salience"] is None
        assert "NO LABELS YET" in report["note"]

    def test_insufficient_labels_prints_but_gates_nothing(self):
        rows = [_corpus_row(f"i{i}", salience=i, rank=i / 100) for i in range(10)]
        labels = {f"i{i}": gs.make_label_row(f"i{i}", "useful", labeler="f", now=NOW)
                  for i in range(5)}
        report = gs.evaluate(rows, labels, k=20)
        assert report["state"] == "insufficient"
        assert report["beats_salience"] is None
        assert report["precision_at_k"]["rank_score"]["precision"] is not None

    def test_beats_salience_needs_a_margin_AND_a_paired_p_value(self):
        """Review F-7: a bare sign test reads 'better' on noise about half the time."""
        rows = []
        labels = {}
        # Two orderings that barely differ: rank wins by one item out of 40.
        for i in range(40):
            positive = i < 20
            rows.append(_corpus_row(f"i{i}", salience=100 - i, rank=(100 - i) / 100))
            labels[f"i{i}"] = gs.make_label_row(
                f"i{i}", "post_worthy" if positive else "garbage",
                labeler="fable", now=NOW, sample_mode="head")
        rows[25]["rank_score"] = 9.0  # rank pulls one extra NEGATIVE into the top-k
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["state"] == "ok"
        assert report["beats_salience"] is False
        assert report["paired_test"]["discordant_pairs"] >= 0
        assert report["delta"] is not None, "the raw delta is still displayed"

    def test_the_gate_is_pre_registered_and_config_keyed(self):
        cfg = json_config()["breaking"]["scoring"]["golden_set"]
        assert cfg["alpha"] == gs.DEFAULT_ALPHA
        assert cfg["min_margin"] == gs.DEFAULT_MIN_MARGIN

    def test_mcnemar_only_counts_discordant_pairs(self):
        labels = {
            "a": gs.make_label_row("a", "post_worthy", labeler="f", now=NOW),
            "b": gs.make_label_row("b", "garbage", labeler="f", now=NOW),
            "c": gs.make_label_row("c", "post_worthy", labeler="f", now=NOW),
        }
        # a is in both top-ks (concordant, carries no information).
        out = gs.mcnemar(["a", "c"], ["a", "b"], labels)
        assert out["b_rank_only_positives"] == 1
        assert out["c_salience_only_positives"] == 0
        assert out["discordant_pairs"] == 1

    def test_the_ci_and_p_value_are_reported(self):
        rows, labels = [], {}
        for i in range(40):
            positive = i < 20
            rows.append(_corpus_row(f"i{i}", salience=(10 + i) if positive else (90 - i),
                                    rank=(0.99 - i * 0.001) if positive else 0.1))
            labels[f"i{i}"] = gs.make_label_row(
                f"i{i}", "post_worthy" if positive else "garbage",
                labeler="fable", now=NOW, sample_mode="head")
        report = gs.evaluate(rows, labels, k=20,
                             cfg={"min_labeled": 10, "bootstrap_draws": 200})
        assert report["delta_ci"]["n_boot"] > 0
        assert report["delta_ci"]["low"] is not None
        assert report["paired_test"]["p_value"] <= 1.0
        text = gs.format_report(report)
        assert "paired test" in text and "CI[" in text


class TestEstimatorHonesty:
    """Review F-8(a): a stratified sample is not a uniform head sample."""

    def _rows_and_labels(self, mode, weight):
        rows, labels = [], {}
        for i in range(40):
            positive = i < 20
            rows.append(_corpus_row(f"i{i}", salience=100 - i, rank=(100 - i) / 100))
            labels[f"i{i}"] = gs.make_label_row(
                f"i{i}", "post_worthy" if positive else "garbage", labeler="f",
                now=NOW, sample_mode=mode, inclusion_weight=weight)
        return rows, labels

    def test_head_mode_uses_the_unweighted_estimator(self):
        rows, labels = self._rows_and_labels("head", 1.0)
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["estimator"] == "uniform-head"
        assert "unbiased estimate of head precision" in report["note"]

    def test_stratified_mode_uses_the_iip_estimator(self):
        rows, labels = self._rows_and_labels("stratified", 4.0)
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["estimator"] == "stratified-iip"
        assert "INVERSE-INCLUSION-PROBABILITY" in report["note"]
        assert report["precision_at_k"]["rank_score"]["weight_sum"] > 0

    def test_a_mixed_design_says_so_instead_of_guessing(self):
        rows, labels = self._rows_and_labels("head", 1.0)
        labels["i0"]["sample_mode"] = "stratified"
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["estimator"] == "unweighted-mixed-design"
        assert "indicative only" in report["note"]

    def test_unknown_design_is_named_not_assumed(self):
        rows, labels = self._rows_and_labels("", 1.0)
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["estimator"] == "unweighted-unknown-design"
        assert "UNKNOWN" in report["note"]

    def test_head_batch_carries_unit_weights_stratified_carries_real_ones(self):
        rows = ([_corpus_row(f"h{i}", salience=90, rank=0.9) for i in range(40)]
                + [_corpus_row(f"l{i}", salience=5, rank=0.1) for i in range(40)])
        head = gs.export_batch(rows, n=10, seed="s", now=NOW, mode="head")
        strat = gs.export_batch(rows, n=10, seed="s", now=NOW, mode="stratified")
        assert {i["inclusion_weight"] for i in head["items"]} == {1.0}
        assert max(i["inclusion_weight"] for i in strat["items"]) > 1.0

    def test_head_mode_samples_the_head(self):
        rows = ([_corpus_row(f"h{i}", salience=90, rank=0.9) for i in range(20)]
                + [_corpus_row(f"l{i}", salience=5, rank=0.1) for i in range(200)])
        batch = gs.export_batch(rows, n=10, seed="s", now=NOW, mode="head",
                                cfg={"head_size": 20})
        assert all(i["item_id"].startswith("h") for i in batch["items"])


class TestBaselineIsUncontaminated:
    """Review F-8(b): the control must not be a blend of control and treatment."""

    def test_baseline_reads_the_pre_demotion_salience(self):
        row = _corpus_row("a", salience=40, rank=0.5, salience_base=80)
        assert gs.baseline_salience(row) == 80.0

    def test_baseline_falls_back_for_older_rows(self):
        row = _corpus_row("a", salience=40, rank=0.5)
        del row["salience_base"]
        assert gs.baseline_salience(row) == 40.0

    def test_the_ranking_uses_the_uncontaminated_column(self):
        rows = [
            _corpus_row("hi", salience=1, rank=0.1, salience_base=99),
            _corpus_row("lo", salience=99, rank=0.9, salience_base=1),
        ]
        labels = {"hi": gs.make_label_row("hi", "post_worthy", labeler="f", now=NOW),
                  "lo": gs.make_label_row("lo", "garbage", labeler="f", now=NOW)}
        report = gs.evaluate(rows, labels, k=1, cfg={"min_labeled": 1})
        assert report["precision_at_k"]["salience"]["precision"] == 1.0, (
            "the baseline must rank on pre-demotion salience, not the demoted one")

    def test_press_lane_persists_the_pre_demotion_number(self):
        scored = score_item(
            _item("a"), now=NOW,
            cfg={"scoring": {"demote_enabled": True, "demote_floor": 0.5}},
            context={"story": {"sources_15m": 1, "sources_60m": 1}},
        )
        block = scored["_salience_components"]
        assert block["pre_demotion"] > block["capped"]


class TestEvalHarnessEndToEnd:
    def test_end_to_end_on_a_fixture_labeled_mini_set(self):
        """The harness must actually rank, actually score, and actually compare.

        Construction: rank_score agrees with the labels, salience does not — so a
        working harness reports rank_score ABOVE salience. This is a fixture, not
        a claim about the real scorer; the real comparison waits for real labels.
        """
        rows = []
        labels = {}
        for i in range(40):
            good = i < 20
            rows.append(_corpus_row(
                f"i{i}",
                salience=(10 + i) if good else (90 - i),   # inverted vs the labels
                rank=(0.99 - i * 0.001) if good else (0.10 - i * 0.0001),
            ))
            labels[f"i{i}"] = gs.make_label_row(
                f"i{i}", "post_worthy" if good else "garbage", labeler="fable", now=NOW)
        report = gs.evaluate(rows, labels, k=20, cfg={"min_labeled": 10})
        assert report["state"] == "ok"
        assert report["precision_at_k"]["rank_score"]["precision"] == 1.0
        assert report["precision_at_k"]["salience"]["precision"] < 1.0
        assert report["beats_salience"] is True
        assert report["delta"] > 0

    def test_unlabeled_rows_are_not_counted_as_negatives(self):
        rows = [_corpus_row(f"i{i}", salience=100 - i, rank=1 - i / 100)
                for i in range(30)]
        labels = {"i0": gs.make_label_row("i0", "post_worthy", labeler="f", now=NOW),
                  "i1": gs.make_label_row("i1", "garbage", labeler="f", now=NOW)}
        result = gs.precision_at_k(rows, labels, k=20)
        assert result["k_effective"] == 2
        assert result["precision"] == 0.5

    def test_positive_class_is_post_worthy_and_viral_grade(self):
        assert gs.POSITIVE_LABELS == {"post_worthy", "viral_grade"}
        rows = [_corpus_row("a", salience=1, rank=0.9),
                _corpus_row("b", salience=1, rank=0.8)]
        labels = {"a": gs.make_label_row("a", "viral_grade", labeler="f", now=NOW),
                  "b": gs.make_label_row("b", "useful", labeler="f", now=NOW)}
        assert gs.precision_at_k(rows, labels, k=2)["precision"] == 0.5

    def test_report_formats_without_crashing_in_every_state(self):
        for report in (gs.evaluate([], {}, k=20),
                       gs.evaluate([_corpus_row("a", salience=1, rank=0.1)], {}, k=20)):
            text = gs.format_report(report)
            assert "golden-set eval" in text
            assert "undefined" in text

    def test_read_corpus_round_trip(self, tmp_path):
        path = tmp_path / "corpus.jsonl"
        rows = [_corpus_row("a", salience=1, rank=0.1),
                _corpus_row("b", salience=2, rank=0.2)]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        assert len(gs.read_corpus([path])) == 2

    def test_read_corpus_tolerates_a_torn_line(self, tmp_path):
        path = tmp_path / "corpus.jsonl"
        path.write_text(json.dumps(_corpus_row("a", salience=1, rank=0.1))
                        + "\n{half written", encoding="utf-8")
        assert len(gs.read_corpus([path])) == 1


class TestGoldenSetCli:
    def test_cli_reports_the_empty_state_and_exits_zero(self, tmp_path, capsys):
        sys.path.insert(0, str(ROOT / "scripts"))
        import marketing_golden_set as cli

        labels = tmp_path / "labels.jsonl"
        corpus = tmp_path / "corpus.jsonl"
        corpus.write_text(json.dumps(_corpus_row("a", salience=1, rank=0.1)) + "\n",
                          encoding="utf-8")
        code = cli.main(["--labels", str(labels), "--corpus", str(corpus), "eval"])
        out = capsys.readouterr().out
        assert code == 0
        assert "no-labels" in out
        assert "undefined" in out

    def test_require_labels_is_the_opt_in_strict_mode(self, tmp_path, capsys):
        sys.path.insert(0, str(ROOT / "scripts"))
        import marketing_golden_set as cli

        corpus = tmp_path / "corpus.jsonl"
        corpus.write_text(json.dumps(_corpus_row("a", salience=1, rank=0.1)) + "\n",
                          encoding="utf-8")
        code = cli.main(["--labels", str(tmp_path / "l.jsonl"), "--corpus", str(corpus),
                         "eval", "--require-labels"])
        assert code == 1
        assert capsys.readouterr().out.count("::error title=golden-set-eval::") == 1

    def test_export_writes_a_batch(self, tmp_path, capsys):
        sys.path.insert(0, str(ROOT / "scripts"))
        import marketing_golden_set as cli

        corpus = tmp_path / "corpus.jsonl"
        corpus.write_text("\n".join(
            json.dumps(_corpus_row(f"i{i}", salience=i, rank=i / 100))
            for i in range(30)) + "\n", encoding="utf-8")
        out = tmp_path / "batch.jsonl"
        assert cli.main(["--labels", str(tmp_path / "l.jsonl"), "--corpus", str(corpus),
                         "export", "--n", "5", "--out", str(out)]) == 0
        assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 5
        capsys.readouterr()


# ═════════════════════════════════════════════════════════════════════════════
# Config contract
# ═════════════════════════════════════════════════════════════════════════════

class TestConfigContract:
    def test_every_rank_weight_is_a_config_key(self):
        weights = json_config()["breaking"]["scoring"]["rank_weights"]
        assert set(weights) == {"salience", *sf.FEATURE_NAMES}
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_config_defaults_match_the_module_defaults(self):
        """A config drift that silently re-tunes the scorer must be visible.

        Review F-19: this used to check three blocks out of seven, so
        corpus/tone/headline_shape/golden_set could drift from their module
        defaults unnoticed — and corpus is where every burst and novelty
        threshold lives.
        """
        cfg = json_config()["breaking"]["scoring"]
        assert cfg["rank_weights"] == sf.rank_weights(None)
        for block, defaults in (
            ("corroboration", sf._CORROBORATION_DEFAULTS),
            ("authority", sf._AUTHORITY_DEFAULTS),
            ("corpus", sf._CORPUS_DEFAULTS),
            ("headline_shape", sf._SHAPE_DEFAULTS),
        ):
            for key, value in cfg[block].items():
                assert defaults[key] == value, f"{block}.{key} drifted from the module"
        for key, value in cfg["story_spine"].items():
            assert ss._DEFAULTS[key] == value, f"story_spine.{key} drifted"

    def test_tone_block_matches_the_module_defaults(self):
        cfg = json_config()["breaking"]["scoring"]["tone"]
        assert cfg["tone_cap"] == sf._TONE_DEFAULTS["tone_cap"]
        assert tuple(cfg["paths"]) == tuple(sf._TONE_DEFAULTS["paths"])
        assert cfg["enabled"] is True

    def test_golden_set_block_matches_the_module_defaults(self):
        cfg = json_config()["breaking"]["scoring"]["golden_set"]
        assert cfg["min_labeled"] == gs.DEFAULT_MIN_LABELED
        assert cfg["alpha"] == gs.DEFAULT_ALPHA
        assert cfg["min_margin"] == gs.DEFAULT_MIN_MARGIN
        assert cfg["bootstrap_draws"] == gs.DEFAULT_BOOTSTRAP
        assert cfg["bootstrap_seed"] == gs.DEFAULT_BOOTSTRAP_SEED
        assert tuple(cfg["bands"]) == gs.DEFAULT_BANDS

    def test_every_scoring_block_is_covered_by_a_contract_test(self):
        """The guard's own guard: a NEW block must not slip in unchecked."""
        blocks = set(json_config()["breaking"]["scoring"])
        known = {
            "enabled", "rank_ordering", "demote_enabled", "demote_feature",
            "demote_floor", "rank_weights", "story_spine", "semantic", "corpus",
            "corroboration", "authority", "tone", "headline_shape", "golden_set",
            "corpus_row_window_h", "corpus_sink",
        }
        assert blocks == known, (
            "a scoring block was added or removed without extending the "
            "config-contract tests")

    def test_the_corpus_sink_caps_are_config_keys(self):
        """Review F-17: the sink bounds were module constants."""
        sink = json_config()["breaking"]["scoring"]["corpus_sink"]
        assert sink["max_rows"] > 0 and sink["max_bytes"] > 0
        daemon = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(encoding="utf-8")
        assert 'sink.get("max_rows"' in daemon
        assert 'sink.get("max_bytes"' in daemon

    def test_the_corpus_roll_is_streaming(self):
        """A 64 MB read inside the live tick is not a roll, it is a stall.

        Asserted on the AST so the prose explaining the old defect cannot
        satisfy or break the check.
        """
        source = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "_roll_press_corpus")
        calls = {n.func.attr for n in ast.walk(func)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert "read_text" not in calls and "readlines" not in calls
        assert "splitlines" not in calls
        assert "enumerate" in {n.func.id for n in ast.walk(func)
                               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    def test_semantic_pass_ships_disabled_with_no_model_path(self):
        semantic = json_config()["breaking"]["scoring"]["semantic"]
        assert semantic["enabled"] is False
        assert semantic["model_path"] == ""

    def test_the_docs_runbook_exists_and_names_the_arming_levers(self):
        text = (ROOT / "docs" / "scoring_brain.md").read_text(encoding="utf-8")
        for lever in ("rank_ordering", "demote_enabled", "model_path",
                      "marketing_golden_set.py"):
            assert lever in text


class TestNoRepoWrites:
    def test_the_daemon_corpus_path_is_gitignored(self):
        import subprocess

        target = "data/marketing/press/ingest_corpus.jsonl"
        result = subprocess.run(["git", "check-ignore", target],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, f"{target} must be gitignored (host state)"

    def test_run_press_tick_writes_no_corpus_file_itself(self):
        """The lane RETURNS rows; only the daemon persists them (dry-run safe)."""
        source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(encoding="utf-8")
        assert "ingest_corpus" not in source

    def test_the_daemon_skips_the_corpus_write_in_dry_run(self):
        source = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(encoding="utf-8")
        block = source.split("_append_press_corpus(result", 1)[0]
        assert block.rstrip().endswith("if not dry_run:")
