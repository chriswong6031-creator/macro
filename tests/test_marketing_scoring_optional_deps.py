"""XG-W5 optional-dependency paths — the MinHash-LSH near-dup pass (datasketch).

THIS SUITE IMPORTS datasketch AT MODULE LEVEL, ON PURPOSE, WITH NO importorskip.

`pytest.importorskip` here would recreate the exact house trap the repo has hit
twice (#3703, #3760, and the guard scripts/check_skip_only_suites.py that came
out of them): the near-dup pass would be "covered" by a suite that skips in every
lane that names it, and main would go green and weaker in the same commit.

The contract is therefore explicit: this file runs ONLY in the CI job that
installs datasketch (`marketing-scoring-optional` in .github/ci/legacy-jobs.yml),
and in that job a missing wheel is a COLLECTION ERROR — red, loud, immediate —
not a skip. The deterministic core of the scoring brain lives in the sibling
suite tests/test_marketing_scoring_brain.py, which is stdlib+pyyaml and runs in
the thin marketing-engine lane; the two together are the split the acceptance
gate asks for.

model2vec is deliberately NOT covered here: its artifact is an operator/R2 step
(docs/scoring_brain.md §3) and must never become a CI dependency. The semantic
clustering BRANCH is ours and is tested with an injected encoder in the sibling
suite; what is untested by design is model2vec's own inference, which is theirs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# NO importorskip — see the module docstring. A missing wheel must be red.
import datasketch  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import story_spine as ss  # noqa: E402

NOW = datetime(2026, 7, 28, 14, 30, tzinfo=timezone.utc)

_HEADLINE = ("Federal Reserve holds interest rates steady as policymakers "
             "weigh a softening labour market")
_REWRITE = ("Federal Reserve holds interest rates steady while policymakers "
            "weigh a softening labour market")
_UNRELATED = ("Volcanic activity halts flights out of Reykjavik as the airspace "
              "closes overnight across the region")


def _item(iid, headline, *, url, source="cnbc", tier="wire", body=""):
    return {"id": iid, "headline": headline, "body_snippet": body, "url": url,
            "source": source, "source_name": source, "source_tier": tier,
            "published_at": NOW.isoformat()}


class TestNearDupPassIsActuallyEnabled:
    def test_the_backend_reports_available(self):
        spine = ss.StorySpine({}, cfg={})
        assert spine.near_dup_enabled is True
        assert not any("datasketch" in d for d in spine.downgrades)

    def test_signatures_are_produced_and_json_persistable(self):
        backend = ss._MinHashBackend(num_perm=64, threshold=0.5)
        signature = backend.signature("the quick brown fox jumps", 3)
        assert signature and len(signature) == 64
        assert all(isinstance(v, int) for v in signature)
        json.dumps(signature)


class TestNearDupClustering:
    """Wire-copy near-dups: DIFFERENT urls, DIFFERENT sources, one story."""

    def test_a_reworded_syndication_joins_the_same_story(self):
        spine = ss.StorySpine({}, cfg={"near_dup_threshold": 0.5})
        a = spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        b = spine.assign(_item("b", _REWRITE, url="https://two.example/9",
                               source="reuters", tier="official"), now=NOW)
        assert a["story_id"] == b["story_id"]
        assert b["match"] == "near_dup"
        assert b["source_count"] == 2
        assert b["tier_mix"] == {"wire": 1, "official": 1}

    def test_an_unrelated_story_stays_apart(self):
        spine = ss.StorySpine({}, cfg={"near_dup_threshold": 0.5})
        a = spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        b = spine.assign(_item("b", _UNRELATED, url="https://two.example/9",
                               source="reuters"), now=NOW)
        assert a["story_id"] != b["story_id"]

    def test_the_threshold_is_a_real_lever(self):
        strict = ss.StorySpine({}, cfg={"near_dup_threshold": 0.9})
        assert strict.near_dup_enabled is True, "0.9/96 must be a feasible LSH pair"
        a = strict.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        b = strict.assign(_item("b", _REWRITE, url="https://two.example/9",
                                source="reuters"), now=NOW)
        assert a["story_id"] != b["story_id"], "a 0.9 threshold must not merge a rewrite"

    def test_an_infeasible_threshold_downgrades_rather_than_crashing(self):
        """A config value datasketch cannot band must cost the pass, not the wire."""
        spine = ss.StorySpine({}, cfg={"near_dup_threshold": 0.99,
                                       "minhash_num_perm": 96})
        assert spine.near_dup_enabled is False
        assert any("unbuildable" in d or "threshold" in d for d in spine.downgrades)
        # And the lane still clusters on exact identity.
        spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        view = spine.assign(_item("b", _HEADLINE, url="https://one.example/1",
                                  source="reuters"), now=NOW)
        assert view["source_count"] == 2

    def test_a_signature_from_another_scheme_is_treated_as_absent(self):
        """An upgraded datasketch must never produce a silently wrong similarity."""
        state: dict = {}
        spine = ss.StorySpine(state, cfg={"near_dup_threshold": 0.5})
        spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        for rec in state["stories"].values():
            rec["signature_scheme"] = "some-older-scheme"
        spine2 = ss.StorySpine(json.loads(json.dumps(state)),
                               cfg={"near_dup_threshold": 0.5})
        view = spine2.assign(_item("b", _REWRITE, url="https://two.example/9",
                                   source="reuters"), now=NOW)
        assert view["match"] == "new"

    def test_corroboration_velocity_rises_because_of_the_near_dup_pass(self):
        """The pass exists to make the ≥2-source law's evidence countable."""
        from engine.marketing.signal_features import corroboration_velocity

        spine = ss.StorySpine({}, cfg={"near_dup_threshold": 0.5})
        spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        spine.assign(_item("b", _REWRITE, url="https://two.example/9",
                           source="reuters"), now=NOW)
        view = spine.assign(_item("c", _HEADLINE, url="https://three.example/7",
                                  source="ap"), now=NOW)
        value, detail = corroboration_velocity(view)
        assert detail["sources_15m"] == 3
        assert value > 0.0


class TestPersistenceAcrossRestarts:
    def test_the_lsh_index_rebuilds_from_persisted_signatures(self):
        """The daemon restarts; the story set must survive as a near-dup index."""
        state: dict = {}
        spine = ss.StorySpine(state, cfg={"near_dup_threshold": 0.5})
        first = spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)

        revived = json.loads(json.dumps(state))       # exactly what state.json does
        spine2 = ss.StorySpine(revived, cfg={"near_dup_threshold": 0.5})
        assert spine2.near_dup_enabled is True
        second = spine2.assign(_item("b", _REWRITE, url="https://two.example/9",
                                     source="reuters"), now=NOW)
        assert second["story_id"] == first["story_id"]
        assert second["match"] == "near_dup"

    def test_pruning_removes_the_story_from_the_index_too(self):
        from datetime import timedelta

        spine = ss.StorySpine({}, cfg={"near_dup_threshold": 0.5, "story_ttl_h": 1})
        spine.assign(_item("a", _HEADLINE, url="https://one.example/1"), now=NOW)
        spine.prune(NOW + timedelta(hours=5))
        assert spine.stories == {}
        # A near-dup arriving after the prune opens a NEW story rather than
        # resurrecting a dropped id (a dangling LSH key would do exactly that).
        view = spine.assign(_item("b", _REWRITE, url="https://two.example/9"),
                            now=NOW + timedelta(hours=5))
        assert view["match"] == "new"
        assert len(spine.stories) == 1


class TestProductionLaneWithTheOptionalDep:
    def test_the_press_tick_clusters_syndicated_copies(self, tmp_path):
        from engine.marketing.press_lane import run_press_tick

        items = [
            _item("a", _HEADLINE, url="https://one.example/1"),
            _item("b", _REWRITE, url="https://two.example/9", source="reuters"),
        ]
        result = run_press_tick(
            items, root=tmp_path, now=NOW,
            cfg={"breaking": {"llm": {"enabled": False},
                              "scoring": {"story_spine": {"near_dup_threshold": 0.5}},
                              "garbage_gate": {"enabled": True}}},
            press_cfg={"satire_blocklist": [],
                       "wire": {"voice": {"enabled": False}, "tape": {"enabled": False}}},
            state={}, seen_ids=set(), dry_run=True,
        )
        story_ids = {row["story_id"] for row in result["corpus"]}
        assert len(story_ids) == 1, "two syndicated copies must be one story"
        for row in result["corpus"]:
            assert row["_components"]["features"]["corroboration_velocity"] > 0.0
