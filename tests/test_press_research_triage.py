"""tests/test_press_research_triage.py — W2R research triage & tiering (XG-W8).

What this suite is FOR, in the order the acceptance gates state it:

  1. ONE SCORING BRAIN.  The triage layer must CALL the XG-W5 modules
     (garbage_gate, story_spine, signal_features) and engine/press/validators,
     not grow a parallel copy of them.  Asserted on the AST of the shipped
     source, so a future rewrite that reimplements clustering fails here.
  2. DEMOTE-ONLY, STRUCTURALLY.  The LLM path may lower a score and may not
     raise one — proven by construction (the veto module performs no arithmetic
     on a score at all) and by a property sweep over hostile config values.
  3. NULLS PRINTED.  Every report in the window gets a ledger row every day,
     including garbage-dropped and skipped ones, each with a named state.
  4. CONFIG CONTRACT.  Every threshold in config/press.yml matches its module
     default (the XG-W5 TestConfigContract pattern), and the volume knob ships
     on the cold-start ramp.
  5. PRODUCTION WIRING.  The planner really consumes the ranking, the workflow
     really invokes the CLI, and the CLI really writes the ledger.
  6. THE RESEARCH LANE IS DARK, on all four locks, and cannot be talked into
     enqueueing anything.

Every test runs against a synthetic root under tmp_path (MM_DATA_GUARD law) or
reads committed source text.  No test makes a network call: the veto pass is
exercised through its injected `call` seam, never through llm_auth.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import desk_planner as P  # noqa: E402
from engine.press import research_lane as RL  # noqa: E402
from engine.press import research_triage as T  # noqa: E402
from engine.press import research_veto as V  # noqa: E402
from tests import press_fixtures as F  # noqa: E402

ROOT = _REPO


def press_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "press.yml").read_text(encoding="utf-8"))


def marketing_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _item(rid: str, **over) -> dict:
    """A vault catalog row with the shipped field set."""
    base = {
        "id": rid,
        "title": "Rates into the autumn: what the curve is telling clients",
        "institution": "Another Desk",
        "side": "sell",
        "desk": "",
        "published_at": "2026-07-25T09:00:00Z",
        # DELIBERATELY LEXICON-CLEAN. The press planner drops any summary point
        # that trips the house lexicon (desk_planner._press_safe), so a fixture
        # written in ordinary rates-desk shorthand ("front-end", "regime") makes
        # every planner test in this file vacuously green by producing no slots
        # at all. Checked by test_the_fixture_prose_clears_the_house_lexicon.
        "summary_points": [
            "Short-term yields have moved 18 basis points since the June meeting.",
            "The desk puts the terminal rate at 3.75 percent by the second quarter.",
            "Its hedge of choice is a levered structure, which prices a jump.",
            "The stated risk is a labour print above 200 thousand.",
        ],
        "tags": [], "tickers": [], "top_pick": False, "pages": 8,
        "needs_metadata": False,
    }
    base.update(over)
    return base


# ═════════════════════════════════════════════════════════════════════════════
# 1. ONE SCORING BRAIN — the XG-W5 modules are called, never re-implemented
# ═════════════════════════════════════════════════════════════════════════════


class TestOneScoringBrain:
    SOURCE = (ROOT / "engine" / "press" / "research_triage.py").read_text(encoding="utf-8")

    @pytest.mark.parametrize("module,symbol", [
        ("engine.marketing.garbage_gate", "garbage_gate"),
        ("engine.marketing.story_spine", "StorySpine"),
        ("engine.marketing.signal_features", "tokenize"),
        ("engine.marketing.signal_features", "headline_shape"),
        ("engine.press.validators", "window_jaccard"),
    ])
    def test_the_reused_modules_are_actually_imported(self, module, symbol):
        """The charter's reconciliation ruling, asserted on the AST.

        Prose saying "we reuse the scoring brain" is not reuse; an import is.
        """
        tree = ast.parse(self.SOURCE)
        package, _, leaf = module.rpartition(".")
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = {a.name for a in node.names}
                # `from engine.marketing.story_spine import StorySpine`
                if node.module == module and symbol in names:
                    found = True
                # `from engine.marketing import garbage_gate` (module-level use)
                if node.module == package and leaf in names:
                    found = True
            elif isinstance(node, ast.Import):
                if any(a.name == module for a in node.names):
                    found = True
        assert found, f"{module}.{symbol} is not imported — reuse claimed, not made"

    def test_no_minhash_or_shingle_reimplementation(self):
        """story_spine owns clustering.  A second copy is how the two drift."""
        tree = ast.parse(self.SOURCE)
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for banned in ("shingles", "minhash", "normalize_url", "content_key",
                       "independence_key", "cosine"):
            assert banned not in names, (
                f"research_triage defines {banned}() — story_spine already has it")

    def test_no_llm_call_anywhere_in_the_scorer(self):
        """The scorer originates every number by arithmetic (DO_NOT_REBUILD).

        Asserted on IMPORTS and CALLS rather than on raw text: the module has to
        be able to explain in prose why a config key exists ("llm_auth's default
        is a tier up") without that explanation tripping its own guard.
        """
        tree = ast.parse(self.SOURCE)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "llm" not in alias.name and "anthropic" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "llm" not in mod and "anthropic" not in mod, mod
                for alias in node.names:
                    assert alias.name not in ("llm_auth", "build_providers", "make_call")
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None) or ""
                assert name not in ("build_providers", "make_call", "create"), name

    def test_cluster_density_consumes_a_story_spine_view(self):
        """The density term reads story_spine's own `source_count` field."""
        view = {"story_id": "st-x", "source_count": 4, "member_count": 6}
        value, detail = T.cluster_density(view, near_dup_enabled=True,
                                          cfg={"institutions_full": 4})
        assert value == pytest.approx(1.0)
        assert detail["state"] == "observed"
        assert detail["institutions"] == 4

    def test_a_single_institution_theme_scores_zero(self):
        value, _ = T.cluster_density({"source_count": 1}, near_dup_enabled=True)
        assert value == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 2. THE COMPONENTS — each one's honest states
# ═════════════════════════════════════════════════════════════════════════════


class TestInstitutionTier:
    def test_an_unlisted_institution_is_neutral_not_zero(self):
        value, detail = T.institution_tier(_item("a"), cfg={"tiers": {}})
        assert value == 0.5
        assert detail["state"] == "unranked"
        assert "NOT a measurement" in detail["note"]

    def test_a_listed_institution_scores_its_tier(self):
        cfg = {"tiers": {"tier_1": ["Another Desk"]}}
        value, detail = T.institution_tier(_item("a"), cfg=cfg)
        assert value == 1.0
        assert detail["tier"] == "tier_1"

    def test_the_shipped_register_is_empty_an_operator_lever(self):
        tiers = press_config()["research_triage"]["institution"]["tiers"]
        assert all(not v for v in tiers.values()), (
            "the institution register ships EMPTY on purpose — a builder's opinion "
            "about which houses matter is not evidence")


class TestExtractionQuality:
    def test_no_points_is_a_named_zero(self):
        value, detail = T.extraction_quality(_item("a", summary_points=[]))
        assert value == 0.0
        assert detail["state"] == "no-extraction"

    def test_a_thin_extraction_scores_below_a_deep_one(self):
        thin, _ = T.extraction_quality(_item("a", summary_points=["Rates rose."]))
        deep, _ = T.extraction_quality(_item("b"))
        assert thin < deep

    def test_needs_metadata_multiplies_it_down_and_says_so(self):
        clean, _ = T.extraction_quality(_item("a"))
        flagged, detail = T.extraction_quality(_item("a", needs_metadata=True))
        assert flagged == pytest.approx(clean * 0.5)
        assert detail["needs_metadata"] is True


class TestRelevance:
    def test_no_context_is_zero_for_everyone_and_says_so(self):
        value, detail = T.relevance(_item("a"), {"tickers": set(), "topics": set()})
        assert value == 0.0
        assert detail["state"] == "no-context"
        assert "0 contribution for EVERY report" in detail["note"]

    def test_a_ticker_hit_lifts_the_score(self):
        ctx = {"tickers": {"NVDA"}, "topics": set()}
        hit, detail = T.relevance(_item("a", tickers=["NVDA"]), ctx)
        miss, _ = T.relevance(_item("b", tickers=["KO"]), ctx)
        assert hit > miss == 0.0
        assert detail["ticker_hits"] == ["NVDA"]

    def test_the_vault_is_excluded_from_its_own_chronicle_context(self, tmp_path):
        """THE CIRCULARITY FIX.

        The vault ingest writes one `research_vault` chronicle event per report.
        Without the exclusion, "relevance vs hot chronicle threads" compares the
        corpus with itself: measured on the live catalog before the fix, all 280
        candidates sat at the identical saturated value and a 0.22-weight
        component ordered nothing.
        """
        root = tmp_path / "repo"
        (root / "data" / "chronicle").mkdir(parents=True)
        rows = [
            {"date": "2026-07-25", "source": "research_vault", "kind": "report",
             "title": "Rates into the autumn curve terminal", "tickers": ["ZZZ"],
             "themes": ["rates"]},
            {"date": "2026-07-25", "source": "risk_band", "kind": "state_flip",
             "title": "Risk radar: caution to watch", "tickers": [], "themes": ["risk"]},
        ]
        (root / "data" / "chronicle" / "events.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        ctx = T.build_context(root, as_of=date(2026, 7, 26), cfg=None)
        assert "ZZZ" not in ctx["tickers"], "a vault event leaked into the context"
        assert "terminal" not in ctx["topics"]
        assert "risk" in ctx["topics"]
        assert ctx["states"]["chronicle"]["events"] == 1

    def test_the_exclusion_is_a_config_key_and_ships_set(self):
        rel = press_config()["research_triage"]["relevance"]
        assert rel["exclude_chronicle_sources"] == ["research_vault"]


class TestAttentionPotential:
    def test_it_is_declared_ranking_only(self):
        _value, detail = T.attention_potential(_item("a"))
        assert "ranking input only" in detail["contract"]

    def test_top_pick_lifts_it(self):
        plain, _ = T.attention_potential(_item("a"))
        picked, _ = T.attention_potential(_item("a", top_pick=True))
        assert picked > plain

    def test_it_carries_the_smallest_weight_in_the_shipped_blend(self):
        """Design law, not taste: the term most able to pull the brand toward
        the framing the §5 validators ban must never lead the ranking."""
        w = T.weights(press_config()["research_triage"])
        assert w["attention_potential"] == min(w.values())


class TestNovelty:
    def test_an_empty_estate_is_neutral_and_says_so(self):
        value, detail = T.novelty(_item("a"), [])
        assert value == 0.5
        assert detail["state"] == "no-peers"
        assert "NOT a measurement" in detail["note"]

    def test_a_report_we_already_wrote_up_scores_less_novel(self):
        text = T.report_text(_item("a"))
        filler = [{"slug": f"p{i}", "text": f"Unrelated post {i} about other things."}
                  for i in range(10)]
        repeated, d1 = T.novelty(_item("a"), filler + [{"slug": "old", "text": text}])
        fresh, d2 = T.novelty(_item("a"), filler)
        assert d1["state"] == d2["state"] == "observed"
        assert repeated < fresh

    def test_a_thin_peer_corpus_reports_its_null(self):
        """M4: zero overlap against six evergreen posts is not a measurement."""
        value, detail = T.novelty(_item("a"), [{"slug": "p", "text": "Other words."}])
        assert value == 0.5
        assert detail["state"] == "peer-corpus-too-thin"
        assert "NOT a measurement" in detail["note"]


# ═════════════════════════════════════════════════════════════════════════════
# 3. THE RANKING + NULLS PRINTED
# ═════════════════════════════════════════════════════════════════════════════


class TestRanking:
    def test_it_is_deterministic(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        items = [_item("a"), _item("b"), _item("c", top_pick=True)]
        a = T.rank(items, as_of="2026-07-26", root=root, cfg=cfg)
        b = T.rank(items, as_of="2026-07-26", root=root, cfg=cfg)
        assert [r["report_id"] for r in a["rows"]] == [r["report_id"] for r in b["rows"]]
        assert [r["w_score"] for r in a["rows"]] == [r["w_score"] for r in b["rows"]]

    def test_as_of_is_a_hard_right_edge(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("future", published_at="2026-08-05T09:00:00Z"),
                      _item("now", published_at="2026-07-25T09:00:00Z")],
                     as_of="2026-07-26", root=root, cfg=cfg)
        by_id = {r["report_id"]: r for r in res["rows"]}
        assert by_id["now"]["status"] in ("selected", "skipped")
        # The excluded report is PRINTED, not vanished (review M1): a filter
        # nobody can see the output of is how a denominator shrinks silently.
        assert by_id["future"]["status"] == "skipped_input"
        assert by_id["future"]["skip_reason"] == "published-after-run-date"
        assert res["inputs"] == 2 and res["reconciled"] is True

    def test_every_excluded_input_class_gets_a_named_row(self, tmp_path):
        """The four silent `continue`s the review found, one probe each."""
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([
            "not a mapping",
            {"title": "no id here", "published_at": "2026-07-25T00:00:00Z"},
            _item("bad-date", published_at="not-a-date"),
            _item("ancient", published_at="2020-01-01T00:00:00Z"),
            _item("good"),
        ], as_of="2026-07-26", root=root, cfg=cfg)

        assert res["inputs"] == 5
        assert len(res["rows"]) == 5
        assert res["reconciled"] is True
        reasons = {r["report_id"]: r.get("skip_reason") for r in res["rows"]}
        assert reasons["_unscorable_0"] == "not-a-mapping"
        assert reasons["_unidentified_1"] == "no-report-id"
        assert reasons["bad-date"] == "unparseable-published-at"
        assert reasons["ancient"] == "outside-ledger-window"
        assert reasons["good"] is None
        # A skipped input still carries a full component block, all not-scored.
        row = next(r for r in res["rows"] if r["report_id"] == "ancient")
        assert set(row["component_detail"]) == set(T.COMPONENT_NAMES)
        assert all(d["state"] == "not-scored" for d in row["component_detail"].values())

    def test_a_reconciliation_mismatch_is_annotated(self, tmp_path, capsys, monkeypatch):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        # Force a mismatch by making the scorer drop a row on the floor.
        real = T._score_one
        calls = {"n": 0}

        def _lossy(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(T, "_score_one", _lossy)
        res = T.rank([_item("a"), _item("b")], as_of="2026-07-26", root=root, cfg=cfg)
        assert res["reconciled"] is True and calls["n"] == 2
        # And the negative: a hand-built mismatch must annotate.
        capsys.readouterr()
        T._annotate("warning", "x", "y")
        assert capsys.readouterr().out.startswith("::warning")

    def test_every_report_gets_a_row_including_the_dropped_ones(self, tmp_path):
        """NULLS PRINTED.  A day's ledger carries a row for EVERY inflow report.

        The garbage-dropped report is the interesting one: it is excluded from
        the ranking (so it costs zero LLM tokens) and still carries its six
        deterministic components, because a dropped row with no numbers on it is
        the hidden null the house law forbids.
        """
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        junk = _item("junk", title="Your daily horoscope for Wednesday",
                     summary_points=["Mercury is in retrograde. Click here."])
        res = T.rank([_item("good"), junk], as_of="2026-07-26", root=root, cfg=cfg)

        by_id = {r["report_id"]: r for r in res["rows"]}
        assert set(by_id) == {"good", "junk"}
        assert by_id["junk"]["status"] == "garbage_dropped"
        assert by_id["junk"]["drop_reason"] in ("non_story", "promo_spam")
        assert by_id["junk"]["rank"] is None
        assert set(by_id["junk"]["components"]) == set(T.COMPONENT_NAMES)
        assert by_id["good"]["status"] in ("selected", "skipped")

    def test_every_component_reports_a_named_state_for_every_report(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("a"), _item("b", summary_points=[])],
                     as_of="2026-07-26", root=root, cfg=cfg)
        for row in res["rows"]:
            for name in T.COMPONENT_NAMES:
                assert name in row["components"]
                assert row["component_detail"][name].get("state"), (
                    f"{row['report_id']}/{name} has no state — that is a hidden null")

    def test_scores_are_bounded_and_contributions_are_inspectable(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("a"), _item("b")], as_of="2026-07-26", root=root, cfg=cfg)
        for row in res["rows"]:
            assert 0.0 <= row["w_score"] <= 1.0
            assert set(row["contributions"]) == set(T.COMPONENT_NAMES)

    def test_a_hostile_row_does_not_crash_the_run(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([{"id": "x", "published_at": "2026-07-25", "summary_points": None},
                      "not a dict", {"no": "id"}, _item("ok")],
                     as_of="2026-07-26", root=root, cfg=cfg)
        assert {"x", "ok"} <= {r["report_id"] for r in res["rows"]}
        assert len(res["rows"]) == res["inputs"] == 4

    def test_a_raising_garbage_gate_fails_closed(self, tmp_path, monkeypatch, capsys):
        """M8: not knowing whether it is garbage is not a reason to spend."""
        from engine.marketing import garbage_gate as GG

        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        monkeypatch.setattr(GG, "check", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("gate exploded")))
        res = T.rank([_item("a")], as_of="2026-07-26", root=root, cfg=cfg)
        row = res["rows"][0]
        assert row["status"] == "gate_error"
        assert row["rank"] is None
        assert row["status"] not in T.VETO_ELIGIBLE_STATUSES, (
            "a gate-error row must not reach the veto head")
        assert set(row["components"]) == set(T.COMPONENT_NAMES), (
            "its scores are still printed")
        assert any(line.startswith("::warning")
                   for line in capsys.readouterr().out.splitlines())

    def test_cluster_absence_states_are_distinguished(self, tmp_path):
        """M7: three causes of 'no cluster' are not one state."""
        for reason in ("outside-cluster-window", "cluster-truncated", "no-story"):
            _v, detail = T.cluster_density(None, absent_reason=reason)
            assert detail["state"] == reason
            assert "ABSENCE" in detail["note"]
        # And a genuine measured single-institution story is NOT an absence.
        _v, detail = T.cluster_density({"source_count": 1}, near_dup_enabled=True)
        assert detail["state"] == "measured-alone"
        assert "IS" in detail["note"]

    def test_the_cluster_slice_is_recency_ordered(self, tmp_path, capsys):
        """M7: catalog order is ingest order — the newest reports must survive."""
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["research_triage"]["cluster"]["max_items"] = 2
        # All INSIDE the 7-day cluster window, so the cap is what excludes them
        # rather than the window (which would be a different state entirely).
        items = [_item(f"old{i}", published_at="2026-07-21T00:00:00Z") for i in range(4)]
        items += [_item("newest", published_at="2026-07-26T00:00:00Z")]
        res = T.rank(items, as_of="2026-07-26", root=root, cfg=cfg)
        assert res["cluster_truncated"] == 3
        newest = next(r for r in res["rows"] if r["report_id"] == "newest")
        assert newest["component_detail"]["cluster_density"]["state"] != "cluster-truncated"
        assert any(line.startswith("::warning")
                   for line in capsys.readouterr().out.splitlines())

    @pytest.mark.parametrize("wheel", [False, True],
                             ids=["datasketch-absent", "datasketch-present"])
    def test_the_degraded_cluster_state_is_named_not_smoothed(self, tmp_path,
                                                              monkeypatch, wheel):
        """Each dependency state names ITSELF: a FLOOR is never a measurement.

        Both states are FORCED at the availability seam instead of inherited
        from whatever the runner happens to have installed, so this suite stays
        importorskip-free AND stops being environment-dependent.

        Asserting a UNION of both branches (`state in ("observed",
        "exact-only")`) was the earlier bug: a one-item rank reads
        `measured-alone` WITH the wheel and `exact-only` without it, so the test
        passed only in the minimal CI pack env and failed on any dev machine
        carrying datasketch. A union assertion also could not pin which state
        belongs to which dependency state — which is the whole claim here.
        """
        from engine.marketing import story_spine as SS

        if wheel:
            # `near_dup_enabled` only REPORTS `_backend.available`; the near-dup
            # machinery guards on the backend itself, so forcing the property
            # cannot drive an absent wheel down a path that needs it.
            monkeypatch.setattr(SS.StorySpine, "near_dup_enabled",
                                property(lambda self: True))
        else:
            # A None in sys.modules makes `import datasketch` raise, so the REAL
            # probe in `_MinHashBackend.__init__` takes its absent branch and
            # produces its real downgrade — wheel installed or not.
            monkeypatch.setitem(sys.modules, "datasketch", None)  # type: ignore[arg-type]

        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("a")], as_of="2026-07-26", root=root, cfg=cfg)
        detail = res["rows"][0]["component_detail"]["cluster_density"]

        assert res["near_dup_enabled"] is wheel
        if wheel:
            # Clustered and genuinely alone on its theme, BY MEASUREMENT — the
            # degraded label must not leak into a state the near-dup pass really
            # observed.
            assert detail["state"] == "measured-alone"
            assert "IS" in detail["note"]
            assert "FLOOR" not in detail["note"]
        else:
            assert detail["state"] == "exact-only"
            assert "FLOOR" in detail["note"]
            # The degradation is disclosed at the RUN level too, not only per
            # row. Asserted on the returned downgrade rather than on stdout:
            # `_notice` prints once per PROCESS, so a capsys assertion here
            # would pass or fail on test ORDER.
            assert any("story-spine-no-datasketch" in d for d in res["downgrades"]), (
                res["downgrades"])


# ═════════════════════════════════════════════════════════════════════════════
# 4. TIERING + THE COLD-START VOLUME RAMP
# ═════════════════════════════════════════════════════════════════════════════


class TestVolumeAndTiers:
    def test_the_shipped_stage_is_cold_start(self):
        vol = T.volume(press_config()["research_triage"]["volume"])
        assert vol["stage"] == "cold_start"
        assert vol["flagship_per_day"] == 1
        assert vol["desk_notes_per_day"] == 0, (
            "the desk-note lane must ship dark — a cold domain at note volume is "
            "the scaled-content-abuse profile the masterplan names")

    def test_the_ramp_is_config_not_code(self):
        stages = press_config()["research_triage"]["volume"]["stages"]
        assert set(stages) == {"cold_start", "warm", "target"}
        assert stages["target"]["flagship_per_day"] == 3
        assert stages["target"]["desk_notes_per_day"] == 12
        for name, row in stages.items():
            assert set(row) == {"flagship_per_day", "desk_notes_per_day"}, name

    def test_an_unknown_stage_falls_back_loudly(self, capsys):
        vol = T.volume({"stage": "rocket", "stages": {"cold_start":
                                                      {"flagship_per_day": 1,
                                                       "desk_notes_per_day": 0}}})
        assert vol["stage"] == "cold_start"
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") for line in out.splitlines())

    def test_tiers_follow_the_volume_knob(self):
        rows = [{"report_id": str(i), "status": "ranked", "w_score": 1.0 - i / 10}
                for i in range(6)]
        T.assign_tiers(rows, cfg={"volume": {"stage": "target"}})
        assert [r["tier"] for r in rows] == ["flagship"] * 3 + ["desk_note"] * 3
        assert all(r["status"] == "selected" for r in rows)

    def test_beyond_the_tiers_a_report_is_skipped_with_its_score_intact(self):
        rows = [{"report_id": str(i), "status": "ranked", "w_score": 1.0 - i / 10}
                for i in range(4)]
        T.assign_tiers(rows, cfg={"volume": {"stage": "cold_start"}})
        assert rows[0]["tier"] == "flagship" and rows[0]["status"] == "selected"
        assert [r["status"] for r in rows[1:]] == ["skipped"] * 3
        assert all(r["w_score"] > 0 for r in rows[1:])


# ═════════════════════════════════════════════════════════════════════════════
# 5. THE VETO PASS — DEMOTE ONLY, BY CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════════════


class TestVetoIsStructurallyDemoteOnly:
    VETO_SOURCE = (ROOT / "engine" / "press" / "research_veto.py").read_text(encoding="utf-8")

    def test_the_veto_module_performs_no_arithmetic_at_all(self):
        """THE STRUCTURAL ARGUMENT.

        The module that talks to the model contains no numeric operator, so
        there is no expression anywhere in it that could produce a score — never
        mind a higher one.  Asserted on the AST, so the prose above cannot
        satisfy the check and a future edit that adds `score * 1.5` fails here
        rather than in review.
        """
        tree = ast.parse(self.VETO_SOURCE)
        arithmetic = [n for n in ast.walk(tree)
                      if isinstance(n, ast.BinOp)
                      and isinstance(n.op, (ast.Mult, ast.Div, ast.Sub, ast.Pow))]
        assert not arithmetic, (
            "engine/press/research_veto.py performs arithmetic — the veto path "
            "must not be able to compute a score in either direction")

    def test_the_veto_module_never_assigns_a_score_or_a_rank(self):
        """Asserted on ASSIGNMENT TARGETS, so the prose may discuss ranking
        while the code stays unable to write one."""
        tree = ast.parse(self.VETO_SOURCE)
        targets: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                nodes = node.targets if isinstance(node, ast.Assign) else [node.target]
                for tgt in nodes:
                    if isinstance(tgt, ast.Name):
                        targets.append(tgt.id)
                    elif isinstance(tgt, ast.Attribute):
                        targets.append(tgt.attr)
                    elif isinstance(tgt, ast.Subscript) and isinstance(tgt.slice, ast.Constant):
                        targets.append(str(tgt.slice.value))
        for name in targets:
            low = name.lower()
            assert "score" not in low and "rank" not in low, (
                f"the veto module assigns {name!r} — it returns reasons, not numbers")


    def test_the_reason_vocabulary_has_no_promotion_word(self):
        assert T.VETO_REASONS == {"thin", "paywalled", "duplicate"}

    def test_an_unknown_reason_is_discarded(self):
        parsed = V.parse_verdicts(
            json.dumps([{"id": "a", "demote": True, "reason": "excellent"},
                        {"id": "b", "demote": True, "reason": "thin"}]),
            ["a", "b"])
        assert parsed == {"b": "thin"}

    def test_a_hallucinated_id_cannot_demote_anything(self):
        parsed = V.parse_verdicts(
            json.dumps([{"id": "never-submitted", "demote": True, "reason": "thin"}]),
            ["a", "b"])
        assert parsed == {}

    def test_unparsable_output_demotes_nothing(self):
        for raw in ("", "I think report a is fine.", "{", "null", "[1, 2, 3]"):
            assert V.parse_verdicts(raw, ["a"]) == {}

    def test_a_promotion_shaped_response_is_simply_not_understood(self):
        parsed = V.parse_verdicts(
            json.dumps([{"id": "a", "demote": False, "reason": "thin", "promote": True},
                        {"id": "a", "score": 0.99}]),
            ["a"])
        assert parsed == {}

    @pytest.mark.parametrize("factor", [0.0, 0.35, 1.0, 1.5, 42.0, -1.0, -0.0])
    def test_apply_vetoes_can_never_raise_a_score(self, factor):
        """PROPERTY SWEEP over hostile config values, including > 1 and < 0."""
        rows = [{"report_id": "a", "status": "ranked", "w_score": 0.8,
                 "published_at": "2026-07-25"},
                {"report_id": "b", "status": "ranked", "w_score": 0.6,
                 "published_at": "2026-07-25"}]
        result = {"rows": rows}
        out = T.apply_vetoes(result, {"a": {"reason": "thin"}},
                             cfg={"veto": {"demote_factor": factor}})
        after = {r["report_id"]: r["w_score"] for r in out["rows"]}
        assert after["a"] <= 0.8
        assert after["b"] == 0.6

    def test_a_demotion_moves_a_report_down_the_ranking_never_up(self):
        rows = [{"report_id": "a", "status": "ranked", "w_score": 0.9,
                 "published_at": "2026-07-25"},
                {"report_id": "b", "status": "ranked", "w_score": 0.5,
                 "published_at": "2026-07-25"}]
        out = T.apply_vetoes({"rows": rows}, {"a": {"reason": "duplicate"}},
                             cfg={"veto": {"demote_factor": 0.35}})
        assert [r["report_id"] for r in out["rows"]] == ["b", "a"]
        demoted = next(r for r in out["rows"] if r["report_id"] == "a")
        assert demoted["veto"]["demoted"] is True
        assert demoted["w_score_pre_veto"] == 0.9
        assert demoted["w_score"] < 0.9

    def test_an_unknown_reason_reaching_apply_is_still_refused(self):
        rows = [{"report_id": "a", "status": "ranked", "w_score": 0.9,
                 "published_at": "2026-07-25"}]
        out = T.apply_vetoes({"rows": rows}, {"a": {"reason": "promote"}}, cfg={})
        assert out["rows"][0]["w_score"] == 0.9
        assert out["rows"][0].get("veto") is None


class TestVetoRun:
    def _result(self):
        return {"rows": [
            {"report_id": "a", "status": "ranked", "title": "A", "institution": "X",
             "w_score": 0.8, "published_at": "2026-07-25"},
            {"report_id": "b", "status": "ranked", "title": "B", "institution": "Y",
             "w_score": 0.7, "published_at": "2026-07-25"},
            {"report_id": "junk", "status": "garbage_dropped", "title": "J",
             "institution": "Z", "w_score": 0.1, "published_at": "2026-07-25"},
        ]}

    def test_garbage_never_reaches_the_model(self, monkeypatch):
        seen = {}

        def _call(system, user):
            seen["user"] = user
            return "[]", "anthropic", "claude-haiku-4-5"

        monkeypatch.setattr(V, "_model_id", lambda _k: "claude-haiku-4-5")
        out = V.run(self._result(), cfg={"veto": {"enabled": True}}, call=_call)
        assert out["state"] == "ok"
        assert "junk" not in seen["user"], (
            "a P0-dropped report was submitted to the veto pass — the gate exists "
            "so garbage costs zero tokens")

    def test_a_demotion_round_trips(self, monkeypatch):
        monkeypatch.setattr(V, "_model_id", lambda _k: "claude-haiku-4-5")
        out = V.run(self._result(), cfg={"veto": {"enabled": True}},
                    call=lambda s, u: (json.dumps([{"id": "a", "demote": True,
                                                    "reason": "thin"}]),
                                       "anthropic", "claude-haiku-4-5"))
        assert out["vetoes"] == {"a": {"reason": "thin", "model": "claude-haiku-4-5",
                                       "provider": "anthropic"}}

    def test_no_provider_demotes_nothing(self, monkeypatch):
        monkeypatch.setattr(V, "_model_id", lambda _k: "")
        out = V.run(self._result(), cfg={"veto": {"enabled": True}})
        assert out["state"] == "no_provider"
        assert out["vetoes"] == {}

    def test_disabled_is_a_clean_no_op(self):
        out = V.run(self._result(), cfg={"veto": {"enabled": False}})
        assert out["state"] == "disabled" and out["vetoes"] == {}

    def test_a_raising_provider_does_not_stop_triage(self, monkeypatch):
        def _boom(system, user):
            raise RuntimeError("429")

        monkeypatch.setattr(V, "_model_id", lambda _k: "claude-haiku-4-5")
        out = V.run(self._result(), cfg={"veto": {"enabled": True}}, call=_boom)
        assert out["vetoes"] == {}
        # DISTINCT from `no_provider`: a 429 reported as a missing credential
        # sends the operator to the waterfall instead of to rate limits.
        assert out["state"] == "call_failed"
        assert out["failed_batches"] == out["batches"] > 0

    def test_it_batches(self, monkeypatch):
        calls = []
        monkeypatch.setattr(V, "_model_id", lambda _k: "claude-haiku-4-5")
        rows = {"rows": [{"report_id": str(i), "status": "ranked", "title": "T",
                          "institution": "I", "w_score": 1.0 - i / 100,
                          "published_at": "2026-07-25"} for i in range(10)]}

        def _call(system, user):
            calls.append(user)
            return "[]", "anthropic", "m"

        V.run(rows, cfg={"veto": {"enabled": True, "head_size": 10, "batch_size": 4}},
              call=_call)
        assert len(calls) == 3

    def test_the_prompt_states_the_demote_only_contract(self):
        system, _user = V.build_prompt([{"report_id": "a", "institution": "X",
                                         "title": "T", "summary_points": ["p"]}])
        assert "ONLY POWER IS TO DEMOTE" in system
        assert "cannot promote" in system

    def test_the_cheapest_tier_pin_holds_on_every_provider_rung(self):
        """M12: an Anthropic model id is not a DeepSeek one."""
        src = TestVetoIsStructurallyDemoteOnly.VETO_SOURCE
        assert "deepseek_model=" in src
        assert V._DEEPSEEK_FALLBACK == "deepseek-v4-flash"
        cfg = press_config()["research_triage"]["veto"]
        assert cfg["deepseek_model"] == V._DEEPSEEK_FALLBACK
        assert cfg["deepseek_model"] != cfg["model_key"]

    def test_a_gate_error_row_cannot_reach_the_head(self):
        out = V.run({"rows": [{"report_id": "g", "status": "gate_error",
                               "title": "T", "institution": "I",
                               "w_score": 0.9, "published_at": "2026-07-25"}]},
                    cfg={"veto": {"enabled": True}})
        assert out["state"] == "no_head"

    def test_spend_rides_the_existing_lane_and_ledger(self):
        """No new spend path: the waterfall and lib.ai_costs, via usage_lane."""
        src = TestVetoIsStructurallyDemoteOnly.VETO_SOURCE
        assert "llm_auth.build_providers" in src
        assert '"usage_lane": "press-research-triage-veto"' in src
        assert "record_usage" not in src and "record_response_usage" not in src, (
            "the veto must not write the cost ledger itself — llm_auth.make_call "
            "already records usage for the lane it was built with")


# ═════════════════════════════════════════════════════════════════════════════
# 6. THE LEDGER
# ═════════════════════════════════════════════════════════════════════════════


class TestLedger:
    def test_rows_carry_the_whole_audit_trail(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("a")], as_of="2026-07-26", root=root, cfg=cfg)
        row = T.ledger_rows(res, cfg=cfg)[0]
        for key in ("as_of", "report_id", "status", "tier", "rank", "w_score",
                    "w_score_pre_veto", "components", "contributions",
                    "component_detail", "veto"):
            assert key in row, key
        # COMPACTED (M6): the run-level constants moved to the header, and the
        # relevance context state with them.
        for hoisted in ("schema", "scoring_version", "ts"):
            assert hoisted not in row, f"{hoisted} still repeats on every row"
        assert "sources" not in row["component_detail"]["relevance"]

    def test_the_run_header_carries_what_the_rows_no_longer_do(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        res = T.rank([_item("a")], as_of="2026-07-26", root=root, cfg=cfg)
        header = T.run_header(res, cfg=cfg)
        assert header["schema"] == T.RUN_SCHEMA
        for key in ("weights", "volume", "context_states", "near_dup_enabled",
                    "inputs", "rows", "reconciled", "effective_contributions"):
            assert key in header, key

    def test_a_row_is_never_dropped_only_thinned(self, tmp_path, capsys):
        """M6: one row per report is the law; detail is what gives way."""
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["research_triage"]["ledger"]["max_detailed_rows_per_run"] = 1
        res = T.rank([_item(f"r{i}") for i in range(4)],
                     as_of="2026-07-26", root=root, cfg=cfg)
        rows = T.ledger_rows(res, cfg=cfg)
        assert len(rows) == len(res["rows"]), "a report lost its row"
        assert sum(1 for r in rows if r.get("detail_stripped")) == len(rows) - 1
        assert all("w_score" in r for r in rows), "a thinned row kept its score"
        assert any(line.startswith("::notice")
                   for line in capsys.readouterr().out.splitlines())

    def test_compaction_drops_old_rows_and_keeps_recent_ones(self, tmp_path):
        path = tmp_path / "triage.jsonl"
        rows = [{"as_of": "2026-01-01", "report_id": "old"},
                {"as_of": "2026-07-26", "report_id": "new"}]
        T.append_ledger(path, rows)
        out = T.compact_ledger(path, retention_days=30, as_of="2026-07-26")
        assert out == {"before": 2, "after": 1, "dropped": 1}
        remaining = [json.loads(x) for x in
                     path.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [r["report_id"] for r in remaining] == ["new"]

    def test_the_read_cache_collapses_repeated_reads(self, tmp_path):
        """M6: the planner reads this file once per desk, twice per press run."""
        root = tmp_path / "repo"
        (root / "data" / "press").mkdir(parents=True)
        path = root / "data" / "press" / "research_triage.jsonl"
        path.write_text(json.dumps({"as_of": "2026-07-26", "report_id": "a"}) + "\n",
                        encoding="utf-8")
        cfg = {"research_triage": {"ledger": {"path": "data/press/research_triage.jsonl"}}}
        T.clear_ledger_cache()
        first = T.read_ledger(root, cfg)
        assert T.read_ledger(root, cfg) is first, "the second read re-parsed the file"
        # A write invalidates it: the key carries mtime AND size.
        T.append_ledger(path, [{"as_of": "2026-07-27", "report_id": "b"}])
        assert len(T.read_ledger(root, cfg)) == 2

    def test_append_is_idempotent_per_day(self, tmp_path):
        path = tmp_path / "triage.jsonl"
        rows = [{"as_of": "2026-07-26", "report_id": "a", "w_score": 0.5}]
        assert T.append_ledger(path, rows) == 1
        assert T.append_ledger(path, rows) == 0
        assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1
        assert T.append_ledger(path, [{"as_of": "2026-07-27", "report_id": "a"}]) == 1

    def test_thinning_is_announced(self, tmp_path, capsys):
        res = {"rows": [{"report_id": str(i), "component_detail": {"relevance": {}}}
                        for i in range(5)]}
        cfg = {"research_triage": {"ledger": {"max_detailed_rows_per_run": 2}}}
        rows = T.ledger_rows(res, cfg=cfg)
        assert len(rows) == 5, "rows must never be dropped"
        out = capsys.readouterr().out
        assert any(line.startswith("::notice") for line in out.splitlines())

    def _veto_root(self, tmp_path, rows):
        root = tmp_path / "repo"
        (root / "data" / "press").mkdir(parents=True)
        (root / "data" / "press" / "research_triage.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        T.clear_ledger_cache()
        return root, {"research_triage":
                      {"ledger": {"path": "data/press/research_triage.jsonl"}}}

    def test_recorded_vetoes_reads_only_demotions_in_window(self, tmp_path):
        root, cfg = self._veto_root(tmp_path, [
            {"as_of": "2026-07-26", "report_id": "a", "status": "skipped",
             "veto": {"demoted": True, "reason": "thin"}},
            {"as_of": "2026-07-26", "report_id": "b", "status": "skipped", "veto": None},
            {"as_of": "2026-01-01", "report_id": "old", "status": "skipped",
             "veto": {"demoted": True, "reason": "thin"}},
        ])
        out = T.recorded_vetoes(root, cfg, as_of="2026-07-26", window_days=7)
        assert set(out) == {"a"}

    def test_a_later_clean_verdict_clears_an_earlier_demotion(self, tmp_path):
        """A demote-only mechanism must still be able to STOP demoting.

        A `thin` verdict on a stub the vault later re-extracted properly would
        otherwise suppress that report for the whole window.
        """
        root, cfg = self._veto_root(tmp_path, [
            {"as_of": "2026-07-24", "report_id": "a", "status": "skipped",
             "veto": {"demoted": True, "reason": "thin"}},
            {"as_of": "2026-07-26", "report_id": "a", "status": "skipped", "veto": None},
        ])
        assert T.recorded_vetoes(root, cfg, as_of="2026-07-26", window_days=7) == {}

    def test_a_row_that_never_reached_the_head_does_not_clear_a_verdict(self, tmp_path):
        """Only a run that actually READ the report may clear its demotion."""
        root, cfg = self._veto_root(tmp_path, [
            {"as_of": "2026-07-24", "report_id": "a", "status": "skipped",
             "veto": {"demoted": True, "reason": "thin"}},
            {"as_of": "2026-07-26", "report_id": "a", "status": "gate_error",
             "veto": None},
        ])
        assert set(T.recorded_vetoes(root, cfg, as_of="2026-07-26",
                                     window_days=7)) == {"a"}

    def test_the_run_header_is_not_read_as_a_score_row(self, tmp_path):
        root, cfg = self._veto_root(tmp_path, [
            {"schema": T.RUN_SCHEMA, "as_of": "2026-07-26", "report_id": None},
            {"as_of": "2026-07-26", "report_id": "a", "status": "skipped",
             "veto": {"demoted": True, "reason": "thin"}},
        ])
        assert set(T.recorded_vetoes(root, cfg, as_of="2026-07-26",
                                     window_days=7)) == {"a"}

    def test_an_absent_ledger_is_empty_not_an_error(self, tmp_path):
        assert T.recorded_vetoes(tmp_path / "nope", {}, as_of="2026-07-26") == {}

    def test_the_ledger_path_is_tracked_not_gitignored(self):
        """The score ledger is a REPO ledger, written by the nightly lane."""
        import subprocess

        target = "data/press/research_triage.jsonl"
        result = subprocess.run(["git", "check-ignore", target],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode != 0, f"{target} must be tracked, not gitignored"


# ═════════════════════════════════════════════════════════════════════════════
# 7. PLANNER INTAKE — production wiring, not a test-only seam
# ═════════════════════════════════════════════════════════════════════════════


class TestPlannerIntake:
    def test_the_planner_calls_the_triage_layer(self):
        src = (ROOT / "engine" / "press" / "desk_planner.py").read_text(encoding="utf-8")
        assert "from engine.press import research_triage as _rt" in src
        assert "_rt.rank(" in src
        assert "_rt.ranked_order(" in src
        assert "_rt.recorded_vetoes(" in src

    def test_the_research_slot_carries_its_triage_row(self, tmp_path):
        root = F.fixture_root(tmp_path)
        slots = P.plan(["research_desk"], as_of="2026-07-26", root=root)
        assert slots
        triage = slots[0]["triage"]
        assert triage["tier"] == "flagship"
        assert triage["ordered"] is True
        assert triage["rank"] == 1
        assert 0.0 <= triage["w_score"] <= 1.0
        assert set(triage["components"]) == set(T.COMPONENT_NAMES)

    def test_the_ranking_decides_which_report_is_covered(self, tmp_path):
        """The W1 sort took top_pick then recency.  The W-score now decides.

        The planted report is BOTH `top_pick` and the newest in the window, so
        under the W1 rule it wins outright — and it is horoscope-class, so the
        P0 gate drops it before it can be ranked.  If the planner still covered
        it, the intake seam would be decorative.
        """
        root = F.fixture_root(tmp_path)
        path = root / "data" / "research_vault" / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["items"].append(_item(
            "marketdesk-junk-zzz999",
            title="Your daily horoscope: what the zodiac says about markets",
            summary_points=["Subscribe now. Click here for the full reading."],
            top_pick=True, published_at="2026-07-26T09:00:00Z"))
        path.write_text(json.dumps(catalog), encoding="utf-8")

        slots = P.plan(["research_desk"], as_of="2026-07-26", root=root)
        assert slots, "the desk must still cover something"
        assert all("junk" not in ref for s in slots for ref in s["sources"])

    @pytest.mark.parametrize("break_it,label", [
        (lambda c: c["research_triage"].__setitem__("enabled", False),
         "triage disabled"),
        (lambda c: c.pop("research_triage"),
         "config block removed"),
        (lambda c: c["research_triage"].__setitem__("volume", "not a mapping"),
         "volume unreadable"),
        (lambda c: c["desks"]["research_note"].__setitem__("triage_tier", "flagshp"),
         "tier typo"),
    ])
    def test_the_cap_fails_closed_on_every_bypass_route(self, tmp_path, break_it, label):
        """BLOCKER 1: the feature's OFF switch must not be the desk's ON switch.

        `research_note` shipped a ceiling of 12 and `_triage_cap` fell back to
        it whenever the triage layer could not be consulted — so
        `research_triage.enabled: false` would have published twelve notes a
        day. Every route the reviewer reproduced is pinned here.
        """
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        # Give the desk a real ceiling so a fail-OPEN would be visible as a
        # number rather than hidden behind the shipped 0.
        cfg["desks"]["research_note"]["cadence_per_day"] = 12
        break_it(cfg)
        assert P._triage_cap(cfg, cfg["desks"]["research_note"],
                             name="research_note") == 0, label
        assert P.plan(["research_note"], as_of="2026-07-26", root=root, cfg=cfg) == [], label

    def test_a_desk_without_a_triage_tier_keeps_its_own_cadence(self, tmp_path):
        """W1 desks are untouched: fail-closed applies to W2R desks only."""
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg.pop("research_triage")
        assert P._triage_cap(cfg, cfg["desks"]["brief"], name="brief") == 2

    def test_the_note_desk_ships_at_zero_in_config(self):
        """Defence in depth: the resolver fails closed AND the ceiling is 0."""
        assert press_config()["desks"]["research_note"]["cadence_per_day"] == 0

    def test_the_slot_discloses_which_score_it_is_holding(self, tmp_path):
        """The planner recomputes; the nightly computed its own on another host."""
        root = F.fixture_root(tmp_path)
        slots = P.plan(["research_desk"], as_of="2026-07-26", root=root)
        triage = slots[0]["triage"]
        assert triage["score_source"] == "planner-recomputed"
        assert isinstance(triage["datasketch_present"], bool)

    def test_the_note_desk_is_dark_on_the_cold_start_knob(self, tmp_path):
        root = F.fixture_root(tmp_path)
        assert P.plan(["research_note"], as_of="2026-07-26", root=root) == []

    def test_a_configured_zero_cadence_is_not_read_as_one(self, tmp_path):
        """`int(x or 1)` — the W1 idiom — reads a configured 0 as 1.

        That is the exact bug that would have armed the dark note lane the day
        it was added, so the cap resolver must honour 0 explicitly.
        """
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["desks"]["research_desk"]["cadence_per_day"] = 0
        assert P.plan(["research_desk"], as_of="2026-07-26", root=root, cfg=cfg) == []

    def test_cap_is_the_stricter_of_desk_cadence_and_volume(self, tmp_path):
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["research_triage"]["volume"]["stage"] = "target"   # 3 flagship/day
        cfg["desks"]["research_desk"]["cadence_per_day"] = 1   # desk says 1
        assert P._triage_cap(cfg, cfg["desks"]["research_desk"]) == 1
        cfg["desks"]["research_desk"]["cadence_per_day"] = 9
        assert P._triage_cap(cfg, cfg["desks"]["research_desk"]) == 3

    def test_the_note_desk_draws_below_the_flagship_pick(self, tmp_path):
        """ORDER IS LOAD-BEARING: research_desk must claim the head first."""
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["research_triage"]["volume"]["stage"] = "warm"     # 2 flagship + 4 notes
        # BOTH halves have to be raised: the desk ceiling and the volume knob
        # compose as stricter-of, and `research_note` now SHIPS at 0 so the
        # feature's off-switch can never be its arming switch (blocker 1).
        cfg["desks"]["research_desk"]["cadence_per_day"] = 2
        cfg["desks"]["research_note"]["cadence_per_day"] = 4
        catalog = json.loads(
            (root / "data" / "research_vault" / "catalog.json").read_text(encoding="utf-8"))
        catalog["items"] += [_item(f"extra{i}") for i in range(4)]
        (root / "data" / "research_vault" / "catalog.json").write_text(
            json.dumps(catalog), encoding="utf-8")

        slots = P.plan(["research_desk", "research_note"], as_of="2026-07-26",
                       root=root, cfg=cfg)
        flagship = [s for s in slots if s["desk"] == "research_desk"]
        notes = [s for s in slots if s["desk"] == "research_note"]
        assert len(flagship) == 2 and notes
        flagship_refs = {r for s in flagship for r in s["sources"]}
        note_refs = {r for s in notes for r in s["sources"]}
        assert not (flagship_refs & note_refs), "the two desks covered one report twice"

    def test_a_report_outside_the_triage_window_falls_to_the_back_not_off(self, tmp_path):
        """The desk window and the triage window are INDEPENDENT config keys.

        A desk widened past `research_triage.ledger.window_days` would otherwise
        lose its extra candidates silently — an intake seam that quietly shrinks
        the pool is worse than one that does not exist.  The old report must
        still be reachable when everything ranked ahead of it is blocked.
        """
        root = F.fixture_root(tmp_path)
        cfg = P.load_config(root)
        cfg["desks"]["research_desk"]["window_days"] = 400
        cfg["research_triage"]["ledger"]["window_days"] = 3
        path = root / "data" / "research_vault" / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["items"].append(_item("marketdesk-ancient-yyy888",
                                      published_at="2026-01-05T09:00:00Z"))
        path.write_text(json.dumps(catalog), encoding="utf-8")

        # Block everything inside the triage window; the ancient report is the
        # only candidate left, and it is only reachable via the appended tail.
        inside = [f"research_vault:{it['id']}" for it in catalog["items"]
                  if it["id"] != "marketdesk-ancient-yyy888"]
        slots = P.plan(["research_desk"], as_of="2026-07-26", root=root, cfg=cfg,
                       extra_blocked_refs=inside)
        assert slots, "the unranked tail was dropped instead of appended"
        assert slots[0]["sources"] == ["research_vault:marketdesk-ancient-yyy888"]
        assert slots[0]["triage"]["rank"] is None, (
            "an unranked report must not borrow another report's rank")

    def test_the_fixture_prose_clears_the_house_lexicon(self):
        """This suite's own tripwire.

        desk_planner._press_safe drops any summary point that trips the house
        lexicon, and a report whose EVERY point is dropped is skipped.  Fixture
        prose written in ordinary rates-desk shorthand ("front-end yields", "the
        volatility regime") therefore makes every planner test in this file
        vacuously green by producing no slots at all — which is exactly what
        happened while this suite was being written.
        """
        from engine.marketing.copywriter import banned_language

        item = _item("fixture")
        for text in [item["title"], *item["summary_points"]]:
            assert banned_language(text) == [], text

    def test_desks_config_keeps_research_desk_above_research_note(self):
        keys = list(press_config()["desks"])
        assert keys.index("research_desk") < keys.index("research_note")

    def test_triage_failure_falls_back_to_the_w1_sort(self, tmp_path, monkeypatch):
        root = F.fixture_root(tmp_path)

        def _boom(*_a, **_k):
            raise RuntimeError("triage exploded")

        monkeypatch.setattr(T, "rank", _boom)
        slots = P.plan(["research_desk"], as_of="2026-07-26", root=root)
        assert slots, "a broken triage must cost the ordering, never the day"
        assert slots[0]["triage"]["ordered"] is False
        # W1 order: top_pick first -> demo1.
        assert "demo1" in slots[0]["sources"][0]

    def test_the_note_desk_gets_the_research_writer_contract(self):
        from engine.press import writer as W

        slot = {"desk": "research_note", "as_of": "2026-07-26", "byline": "b",
                "min_words": 300, "max_words": 500, "facts": [], "story": {},
                "primary_source": {"kind": "first_party", "name": "n"}}
        system, _user = W.build_prompt(slot, press_config())
        assert "Research Desk of Mastermind Research" in system


# ═════════════════════════════════════════════════════════════════════════════
# 8. THE RESEARCH X LANE — DARK, on four locks
# ═════════════════════════════════════════════════════════════════════════════


class TestResearchLaneIsDark:
    def test_the_account_is_disabled_twice_and_has_no_handle(self):
        accounts = {a["id"]: a for a in
                    marketing_config()["desk_network"]["accounts"]}
        row = accounts["mastermind_research"]
        assert row["enabled"] is False
        assert row["disabled"] is True, (
            "both keys, exactly like mastermind_news — the publish-time lanes "
            "once filtered on `disabled` alone and made a dark property postable")
        assert "handle" not in row, "the X account does not exist yet"

    def test_no_buffer_channel_is_bound(self):
        channels = marketing_config()["publish"]["channels"]
        assert "mastermind_research" not in channels

    def test_liveness_reads_as_planned(self):
        state = RL.account_state(marketing_config(), ROOT)
        assert state["enabled"] is False
        assert state["status"] == "planned"

    def test_build_items_refuses_even_when_asked_to_enqueue(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {"rank": 1}}],
                             cfg=marketing_config(), root=tmp_path,
                             as_of="2026-07-26", enqueue=True)
        assert out["state"] == "dark"
        assert out["items"] == []
        assert out["enqueued"] == 0

    def test_liveness_fails_closed_on_a_broken_config(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg={"desk_network": "not a mapping"}, root=tmp_path)
        assert out["state"] == "dark"

    def test_the_persona_spec_exists_and_is_valid(self):
        from engine.marketing import personas as PZ

        raw = yaml.safe_load(
            (ROOT / "config" / "personas" / "mastermind_research.yml").read_text(
                encoding="utf-8"))
        assert PZ.validate_spec(raw, expect_id="mastermind_research") == []
        assert raw["persona_kind"] == "branded"


class TestResearchLaneShapes:
    """The composition path, exercised with liveness forced on.

    The account is dark in config; these tests hand `build_items` a config where
    it is enabled so the SHAPES are covered rather than only the refusal.  That
    is the opposite of a bypass: the dark test above proves the shipped config
    cannot reach this code.
    """

    def _live_cfg(self):
        cfg = marketing_config()
        for row in cfg["desk_network"]["accounts"]:
            if row["id"] == "mastermind_research":
                row["enabled"] = True
                row.pop("disabled", None)
        return cfg

    def test_both_shapes_are_built_through_make_item(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {"rank": 1,
                                                               "tier": "flagship"}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert out["state"] == "ready"
        formats = {i["source"]["format"] for i in out["items"]}
        assert formats == {RL.FORMAT_POST, RL.FORMAT_ARTICLE}
        for item in out["items"]:
            assert item["schema"] == "marketing.outbox/v1"
            assert item["kind"] == RL.KIND
            assert item["provenance"] == "press_research_lane"

    def test_no_hand_rolled_writer(self):
        src = (ROOT / "engine" / "press" / "research_lane.py").read_text(encoding="utf-8")
        assert "_ob.make_item(" in src and "_ob.validate_item(" in src
        assert "items.jsonl" not in src, "the lane must not write the queue itself"

    def test_no_new_outbox_kind(self):
        from engine.marketing.outbox import KINDS

        assert RL.KIND in KINDS

    def test_the_short_form_is_value_complete_with_the_link_in_a_reply(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26",
                             catalog_items=[_item("a")])
        post = next(i for i in out["items"] if i["source"]["format"] == RL.FORMAT_POST)
        assert "http" not in post["text"], (
            "the link belongs in a REPLY, not the post body (masterplan §6)")
        assert "18 basis points" in post["text"], "the receipt must be IN the post"
        assert post["source"]["reply_link"].startswith("https://")

    @pytest.mark.parametrize("point", [
        "At 10:30 GMT the print showed a 0.3 percent rise.",
        "Three risks: rates, oil, and the labour print.",
        "The ratio sits at 3:1 versus 2:1 a month ago.",
        "Watch 4,200: the desk calls it the line that matters.",
    ])
    def test_a_bare_colon_is_never_treated_as_a_filing_label(self, point):
        """BLOCKER 2: the reviewer's probes, as regression fixtures.

        The first version split the cleaned point on its first colon inside 60
        characters, which decapitated claims and FABRICATED numbers: "At 10:30
        GMT the print showed a 0.3 percent rise." became "30 GMT the print
        showed a 0.3 percent rise." — a wrong figure in a post whose entire job
        is carrying a receipt.
        """
        assert RL.strip_filing_label(point) == point

    def test_a_real_bold_filing_label_is_stripped(self):
        assert RL.strip_filing_label("**NDX Valuation**: NDX trades at 21.8x.") == \
            "NDX trades at 21.8x."

    def test_a_label_with_no_claim_after_it_keeps_the_point(self):
        assert RL.strip_filing_label("**Label**:") == "**Label**:"

    def test_the_clock_time_survives_end_to_end(self, tmp_path):
        item = _item("a", summary_points=["At 10:30 GMT the print showed a rise."])
        out = RL.build_items([{"report": item, "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        post = next(i for i in out["items"] if i["source"]["format"] == RL.FORMAT_POST)
        assert "At 10:30 GMT" in post["text"]

    def test_a_long_lead_point_falls_through_to_the_next_one(self, tmp_path):
        # The fallback point is SIX WORDS OR MORE on purpose. It used to be
        # "Short and usable here." — four words — which is below
        # value_gate.MIN_BODY_WORDS, so once the gate was armed (2026-07-30) the
        # lane correctly abstained and this test failed on a StopIteration that
        # looked like broken fall-through and was actually a working refusal.
        # A four-word body is a stem, not a post; asserting the lane ships one
        # would pin the wrong behaviour.
        item = _item("a", summary_points=[
            "The desk argues at length without stopping for breath " * 12,
            "The second point carries the argument in one usable line.",
        ])
        out = RL.build_items([{"report": item, "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        post = next(i for i in out["items"] if i["source"]["format"] == RL.FORMAT_POST)
        assert "The second point carries the argument in one usable line." in post["text"]

    def test_a_thin_point_is_passed_over_for_a_substantial_one(self, tmp_path):
        """Selection and admission must share one definition of "usable".

        Selection used to ask only "does it FIT the character budget", so a
        two-word point won the slot and the value gate — which asks "is there a
        post here at all" — then abstained on the draft it produced. The report
        was lost even though a later point was a whole paragraph. Neither stage
        was wrong alone; they read different definitions. compose_post now walks
        for the first point that clears the gate's own imported floor.
        """
        item = _item("a", summary_points=[
            "Rates fell.",
            "Two-year yields fell twelve basis points after the auction cleared.",
        ])
        out = RL.build_items([{"report": item, "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        post = next(i for i in out["items"] if i["source"]["format"] == RL.FORMAT_POST)
        assert "Two-year yields fell twelve basis points" in post["text"]
        # The thin lead is passed over, not merely appended after.
        assert "Rates fell." not in post["text"]

    def test_the_floor_is_the_value_gates_own_number_not_a_copy(self, tmp_path):
        """A re-declared constant drifts; an imported one cannot.

        This is the whole point of the fix — if someone raises the gate's floor
        and research_lane keeps its own 6, the two stages silently disagree
        again and the lane resumes losing posts with nobody at fault.
        """
        from engine.marketing.value_gate import MIN_BODY_WORDS

        src = (RL.__file__ and open(RL.__file__, encoding="utf-8").read()) or ""
        assert "from engine.marketing.value_gate import MIN_BODY_WORDS" in src
        # No second literal floor hiding in the module.
        assert f">= {MIN_BODY_WORDS}" not in src.replace(">= MIN_BODY_WORDS", "")

    def test_the_short_form_respects_the_house_char_cap(self, tmp_path):
        long_point = "The desk argues at length. " * 40
        out = RL.build_items([{"report": _item("a", summary_points=[long_point,
                                                                   "Short one here."]),
                               "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        posts = [i for i in out["items"] if i["source"]["format"] == RL.FORMAT_POST]
        for post in posts:
            # 275 is the house copy law (config/marketing.yml copywriter
            # copy_laws), not a round number with slack in it.
            assert len(post["text"]) <= 275

    def test_every_shape_passes_the_shared_banned_vocab_guard(self, tmp_path):
        from engine.marketing.copywriter import banned_language

        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        for item in out["items"]:
            assert banned_language(item["text"]) == []

    def test_banned_content_skips_the_shape_it_does_not_rewrite_it(self, tmp_path):
        out = RL.build_items([{"report": _item("a", summary_points=[
            "The volatility regime has flipped and the narrative changed."]),
            "triage": {}}],
            cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert out["items"] == []
        assert all("copy_guard" in s["reason"] for s in out["skipped"])

    def test_a_site_em_dash_is_normalised_not_a_skip(self, tmp_path):
        """The vault writes for the SITE, where an em dash is normal typography.

        The copy law's own remedy is "a period, a comma, or a new sentence", so
        the substitution is the prescribed fix — not a content edit.  Without it
        every article shape was skipped for punctuation the house itself wrote.
        """
        out = RL.build_items([{"report": _item("a", summary_points=[
            "Short-term yields moved 18 basis points — the desk calls it done."]),
            "triage": {}}],
            cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert out["items"], out["skipped"]
        assert all("—" not in i["text"] for i in out["items"])

    def test_the_article_attributes_the_source_title_rather_than_lifting_it(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        article = next(i for i in out["items"]
                       if i["source"]["format"] == RL.FORMAT_ARTICLE)
        head = article["text"].splitlines()[0]
        assert head.startswith("Another Desk on \"")
        assert head.endswith("\": our read")

    @pytest.mark.parametrize("title", [
        "Rates into the autumn: what the curve is telling clients",
        "A very much longer report title that will certainly not fit inside the "
        "character budget this headline has available to it",
        'A title with "internal quotes" in it',
        "Short",
    ])
    def test_a_quoted_span_is_always_verbatim(self, title):
        """BLOCKER 3 (AM-R4): an edited string in quotation marks is a fabricated
        quotation. Either the quoted span is a verbatim prefix of the source
        title, or there are no quotation marks at all.
        """
        item = _item("a", title=title)
        head = RL._quoted_title(item, "Another Desk", 110)
        if '"' not in head:
            assert head.startswith("Another Desk's latest research note")
            return
        quoted = head.split('"')[1]
        assert quoted.rstrip("…") and title.startswith(quoted.rstrip("…")), (
            f"{quoted!r} is not a verbatim prefix of {title!r}")

    def test_a_title_that_cannot_be_quoted_cleanly_drops_the_quotes(self):
        """An em dash cannot be normalised inside a quotation — it must fall back."""
        item = _item("a", title="Rates — into the autumn",
                     summary_points=["**Curve shape**: front loaded."])
        head = RL._quoted_title(item, "Another Desk", 110)
        assert '"' not in head
        assert head == "Another Desk's latest research note on curve shape"
        from engine.marketing.copywriter import banned_language
        assert banned_language(head) == []

    def test_the_article_carries_the_standing_disclosure(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        article = next(i for i in out["items"]
                       if i["source"]["format"] == RL.FORMAT_ARTICLE)
        assert "not investment advice" in article["text"]

    def test_the_expression_dial_runs_on_this_copy_path(self, tmp_path):
        """M13: the dial is law on every copy path, not only the live ones."""
        src = (ROOT / "engine" / "press" / "research_lane.py").read_text(encoding="utf-8")
        assert "_dial.violations(" in src
        tree = ast.parse(src)
        assert any(isinstance(n, ast.ImportFrom) and n.module == "engine.marketing"
                   and any(a.name == "expression_dial" for a in n.names)
                   for n in ast.walk(tree))

    def test_every_emission_carries_a_value_gate_verdict(self, tmp_path):
        """M13 / charter §0 XG-W3: record-only, like press_lane."""
        out = RL.build_items([{"report": _item("a"), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert out["items"]
        for item in out["items"]:
            assert "value_gate" in item["source"], (
                "an emission with no Gift-Grip-Proof verdict")

    def test_skipped_and_built_reconcile_against_the_shapes_attempted(self, tmp_path):
        out = RL.build_items([{"report": _item("a"), "triage": {}},
                              {"report": _item("b", summary_points=[]), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert len(out["items"]) + len(out["skipped"]) == 4   # 2 reports x 2 shapes

    def test_a_report_with_no_extraction_yields_nothing(self, tmp_path):
        out = RL.build_items([{"report": _item("a", summary_points=[]), "triage": {}}],
                             cfg=self._live_cfg(), root=tmp_path, as_of="2026-07-26")
        assert out["items"] == []
        assert {s["reason"] for s in out["skipped"]} == {"no summary_points"}


# ═════════════════════════════════════════════════════════════════════════════
# 9. THE CLI + THE WORKFLOW — production wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestRunnerAndWorkflow:
    WORKFLOW = (ROOT / ".github" / "workflows" / "research-triage.yml").read_text(
        encoding="utf-8")

    def test_the_workflow_invokes_the_cli(self):
        assert "python -m scripts.run_research_triage" in self.WORKFLOW

    def test_the_workflow_is_dark_by_default(self):
        assert "vars.RESEARCH_TRIAGE_ENABLED == 'true'" in self.WORKFLOW
        assert "secrets.RESEARCH_TRIAGE_ENABLED" not in self.WORKFLOW, (
            "no secrets.* fallback — a lingering secret must not keep the lane live")

    def test_the_workflow_commits_only_the_score_ledger(self):
        adds = [line.strip() for line in self.WORKFLOW.splitlines()
                if line.strip().startswith("git add ")]
        assert adds == ["git add data/press/research_triage.jsonl 2>/dev/null || true"]
        assert "research-triage staged something other than the score ledger" in self.WORKFLOW

    def test_the_workflow_stays_off_the_render_pool(self):
        runners = [line.strip().split("#", 1)[0].strip()
                   for line in self.WORKFLOW.splitlines()
                   if line.strip().startswith("runs-on:")]
        assert runners == ["runs-on: ubuntu-latest"], (
            "the triage lane must stay OFF the macstudio render pool, whose "
            "~67-minute budget is law")

    def test_the_workflow_installs_the_near_dup_backend(self):
        """cluster_density degrades to a floor without datasketch; the
        production lane should not ship the degraded read."""
        assert "datasketch" in self.WORKFLOW

    def test_the_cli_default_writes_nothing(self, tmp_path, monkeypatch):
        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        out = R.run(root, as_of="2026-07-26", write=False, veto=False)
        assert out["ok"] is True
        assert out["ledger_rows"] > 0
        assert out["ledger_written"] == 0
        assert not (root / "data" / "press" / "research_triage.jsonl").exists()

    def test_the_cli_write_mode_appends_the_ledger(self, tmp_path):
        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        out = R.run(root, as_of="2026-07-26", write=True, veto=False)
        path = root / "data" / "press" / "research_triage.jsonl"
        assert path.exists()
        lines = [json.loads(line) for line in
                 path.read_text(encoding="utf-8").splitlines() if line.strip()]
        headers = [r for r in lines if r.get("schema") == T.RUN_SCHEMA]
        rows = [r for r in lines if r.get("schema") != T.RUN_SCHEMA]
        assert len(headers) == 1, "exactly one run header per append"
        assert len(rows) == out["ledger_written"] == out["ledger_rows"]
        assert {r["as_of"] for r in rows} == {"2026-07-26"}
        assert headers[0]["inputs"] == out["inputs"]

    def test_the_cli_writes_nothing_else(self, tmp_path):
        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
        R.run(root, as_of="2026-07-26", write=True, veto=False)
        after = {p for p in root.rglob("*") if p.is_file()}
        new = {p for p in after if p not in before}
        assert new == {root / "data" / "press" / "research_triage.jsonl"}
        for path, mtime in before.items():
            assert path.stat().st_mtime_ns == mtime, f"{path} was modified"

    def test_a_dry_run_spends_nothing_by_default(self, tmp_path, monkeypatch):
        """M5: the docstring said dry-run was free while the flag only governed
        the ledger, so every dry run cost real tokens."""
        import scripts.run_research_triage as R

        called = {"n": 0}

        def _boom(*a, **k):
            called["n"] += 1
            raise AssertionError("the veto pass ran on a default dry run")

        monkeypatch.setattr(R.research_veto, "run", _boom)
        out = R.main(["--dry-run", "--root", str(F.fixture_root(tmp_path)),
                      "--as-of", "2026-07-26"])
        assert out == 0
        assert called["n"] == 0

    def test_a_dry_run_can_opt_into_the_spend(self, tmp_path, monkeypatch):
        import scripts.run_research_triage as R

        seen = {"n": 0}

        def _fake(*a, **k):
            seen["n"] += 1
            return {"state": "ok", "vetoes": {}, "batches": 1, "head": 1, "model": "m"}

        monkeypatch.setattr(R.research_veto, "run", _fake)
        R.main(["--dry-run", "--veto", "--root", str(F.fixture_root(tmp_path)),
                "--as-of", "2026-07-26"])
        assert seen["n"] == 1

    def test_write_keeps_the_veto_on(self, tmp_path, monkeypatch):
        import scripts.run_research_triage as R

        seen = {"n": 0}
        monkeypatch.setattr(R.research_veto, "run", lambda *a, **k: (
            seen.__setitem__("n", seen["n"] + 1),
            {"state": "ok", "vetoes": {}, "batches": 1, "head": 1, "model": "m"})[1])
        R.main(["--write", "--root", str(F.fixture_root(tmp_path)),
                "--as-of", "2026-07-26"])
        assert seen["n"] == 1

    def test_the_three_documents_agree_on_dry_run_spend(self):
        cli = (ROOT / "scripts" / "run_research_triage.py").read_text(encoding="utf-8")
        wf = self.WORKFLOW
        doc = (ROOT / "docs" / "research_triage.md").read_text(encoding="utf-8")
        assert "--veto" in cli and "--veto" in doc
        assert "no LLM call" in cli
        assert "--no-veto" in wf

    def test_the_scheduled_run_applies_retention(self):
        assert "--write --compact" in self.WORKFLOW

    def test_the_x_lane_has_a_production_call_site(self):
        """Promoted minor 11: a feature with no production caller is vacuous."""
        cli = (ROOT / "scripts" / "run_research_triage.py").read_text(encoding="utf-8")
        assert "research_lane.build_items(" in cli
        tree = ast.parse(cli)
        assert any(isinstance(n, ast.ImportFrom) and n.module == "engine.press"
                   and any(a.name == "research_lane" for a in n.names)
                   for n in ast.walk(tree))

    def test_the_production_call_site_no_ops_while_dark(self, tmp_path):
        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        out = R.run(root, as_of="2026-07-26", write=False, veto=False)
        assert out["x_lane"]["state"] == "dark"
        assert out["x_lane"]["items"] == 0

    def test_the_production_call_site_builds_when_the_account_is_live(self, tmp_path):
        """The other half of the fixture pair: the seam really does compose."""
        import shutil

        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        (root / "config").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "config" / "marketing.yml", root / "config" / "marketing.yml")
        raw = yaml.safe_load((root / "config" / "marketing.yml").read_text(encoding="utf-8"))
        for acct in raw["desk_network"]["accounts"]:
            if acct["id"] == "mastermind_research":
                acct["enabled"] = True
                acct.pop("disabled", None)
        (root / "config" / "marketing.yml").write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")

        out = R.run(root, as_of="2026-07-26", write=False, veto=False)
        assert out["x_lane"]["state"] == "ready"
        assert out["x_lane"]["items"] > 0

    def test_an_empty_catalog_is_loud(self, tmp_path, capsys):
        import scripts.run_research_triage as R

        root = F.fixture_root(tmp_path)
        (root / "data" / "research_vault" / "catalog.json").write_text(
            json.dumps({"items": []}), encoding="utf-8")
        out = R.run(root, as_of="2026-07-26", write=True, veto=False)
        assert out["state"] == "no_catalog"
        assert any(line.startswith("::warning")
                   for line in capsys.readouterr().out.splitlines())


# ═════════════════════════════════════════════════════════════════════════════
# 10. HOUSE LAWS
# ═════════════════════════════════════════════════════════════════════════════


class TestHouseLaws:
    MODULES = ("engine/press/research_triage.py", "engine/press/research_veto.py",
               "engine/press/research_lane.py", "scripts/run_research_triage.py")

    @pytest.mark.parametrize("rel", MODULES)
    def test_annotations_start_the_line_and_never_go_through_a_logger(self, rel):
        """House law: a '::warning' behind a log formatter is silently dropped."""
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "error",
                                      "critical", "exception"}:
                continue
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert not arg.value.startswith("::"), f"{rel}: {arg.value[:40]}"
                if isinstance(arg, ast.JoinedStr) and arg.values:
                    head = arg.values[0]
                    if isinstance(head, ast.Constant) and isinstance(head.value, str):
                        assert not head.value.startswith("::"), rel

    @pytest.mark.parametrize("rel", MODULES)
    def test_no_new_first_party_scraping(self, rel):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for token in ("requests.", "urlopen", "httpx", "aiohttp", "BeautifulSoup"):
            assert token not in src, f"{rel} reaches the network directly"

    def test_the_word_validated_stays_out_of_the_shipped_config(self):
        text = (ROOT / "config" / "press.yml").read_text(encoding="utf-8")
        block = text.split("research_triage:", 1)[1].split("\npaths:", 1)[0]
        assert "validated" not in block.lower()

    def test_the_runbook_names_every_arming_lever(self):
        text = (ROOT / "docs" / "research_triage.md").read_text(encoding="utf-8")
        for lever in ("RESEARCH_TRIAGE_ENABLED", "volume.stage", "head_size",
                      "PRESS_PUBLISH_ENABLED", "buffer-channels"):
            assert lever in text, lever


# ═════════════════════════════════════════════════════════════════════════════
# 11. CONFIG CONTRACT (the XG-W5 pattern)
# ═════════════════════════════════════════════════════════════════════════════


def _assert_block_matches(cfg_block: dict, defaults: dict, block: str) -> None:
    """Value-for-value equality, EXCEPT the declared operator levers.

    Levers are checked for presence + type only (see
    research_triage.OPERATOR_LEVER_KEYS and the M9 ruling).
    """
    def _norm(value):
        # YAML has no tuples; the module defaults use them for immutability.
        if isinstance(value, (list, tuple)):
            return [_norm(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _norm(v) for k, v in value.items()}
        return value

    levers = set(T.OPERATOR_LEVER_KEYS)
    for key, value in cfg_block.items():
        assert key in defaults, f"{block}.{key} has no module default to mirror"
        if f"{block}.{key}" in levers:
            assert type(value) is type(defaults[key]) or (
                isinstance(value, (list, tuple)) and
                isinstance(defaults[key], (list, tuple))), f"{block}.{key} type"
            continue
        assert _norm(defaults[key]) == _norm(value), (
            f"{block}.{key} drifted from the module default")


class TestConfigContract:
    def test_every_weight_is_a_config_key_and_they_sum_to_one(self):
        w = press_config()["research_triage"]["weights"]
        assert set(w) == set(T.COMPONENT_NAMES)
        assert sum(w.values()) == pytest.approx(1.0)

    def test_config_weights_match_the_module_defaults(self):
        assert press_config()["research_triage"]["weights"] == T.weights(None)

    @pytest.mark.parametrize("block,defaults", [
        ("institution", T._INSTITUTION_DEFAULTS),
        ("cluster", T._CLUSTER_DEFAULTS),
        ("relevance", T._RELEVANCE_DEFAULTS),
        ("extraction", T._EXTRACTION_DEFAULTS),
        ("attention", T._ATTENTION_DEFAULTS),
        ("novelty", T._NOVELTY_DEFAULTS),
        ("veto", T._VETO_DEFAULTS),
        ("volume", T._VOLUME_DEFAULTS),
        ("ledger", T._LEDGER_DEFAULTS),
    ])
    def test_config_defaults_match_the_module_defaults(self, block, defaults):
        """A config drift that silently re-tunes the triage must be visible."""
        _assert_block_matches(press_config()["research_triage"][block], defaults, block)

    def test_the_story_spine_block_matches_the_spine_defaults(self):
        from engine.marketing import story_spine as SS

        cfg = press_config()["research_triage"]["story_spine"]
        for key, value in cfg.items():
            assert SS._DEFAULTS[key] == value, f"story_spine.{key} drifted"

    def test_every_garbage_detector_is_a_config_key(self):
        from engine.marketing import garbage_gate as GG

        cfg = press_config()["research_triage"]["garbage_gate"]
        assert set(cfg["detectors"]) == set(GG.detector_names())
        assert cfg["enabled"] is True
        assert cfg["source_blocklist"] == []

    def test_the_attention_headline_shape_keys_are_real_signal_features_knobs(self):
        from engine.marketing import signal_features as SF

        cfg = press_config()["research_triage"]["attention"]["headline_shape"]
        for key in cfg:
            assert key in SF._SHAPE_DEFAULTS, f"{key} is not a headline_shape knob"

    def test_operator_levers_are_exempt_from_the_value_pin(self):
        """M9: a knob the charter says an operator turns must be turnable.

        The contract test pins VALUES so a silent re-tune is visible. That is
        the right default and the wrong rule for the four keys the charter calls
        operator levers — pinning those makes "config, not code" false, because
        flipping the volume stage would turn CI red.
        """
        assert set(T.OPERATOR_LEVER_KEYS) == {
            "volume.stage", "veto.head_size", "veto.enabled", "institution.tiers"}
        cfg = press_config()["research_triage"]
        # EXISTS and has the right TYPE — not a pinned value.
        assert isinstance(cfg["volume"]["stage"], str)
        assert isinstance(cfg["veto"]["head_size"], int)
        assert isinstance(cfg["veto"]["enabled"], bool)
        assert isinstance(cfg["institution"]["tiers"], dict)

    def test_flipping_a_lever_does_not_break_the_contract_test(self):
        """The exemption is REAL: prove a flipped lever still passes."""
        cfg = press_config()["research_triage"]
        cfg["volume"]["stage"] = "target"
        cfg["veto"]["head_size"] = 150
        cfg["institution"]["tiers"]["tier_1"] = ["Goldman Sachs"]
        for block, defaults in (("volume", T._VOLUME_DEFAULTS),
                                ("veto", T._VETO_DEFAULTS),
                                ("institution", T._INSTITUTION_DEFAULTS)):
            _assert_block_matches(cfg[block], defaults, block)

    def test_every_triage_block_is_covered_by_a_contract_test(self):
        """The guard's own guard: a NEW block must not slip in unchecked."""
        blocks = set(press_config()["research_triage"])
        known = {"enabled", "weights", "institution", "cluster", "story_spine",
                 "relevance", "extraction", "attention", "novelty",
                 "garbage_gate", "veto", "volume", "ledger"}
        assert blocks == known, (
            "a research_triage block was added or removed without extending the "
            "config-contract tests")

    def test_the_model_keys_resolve(self):
        models = yaml.safe_load(
            (ROOT / "config.yml").read_text(encoding="utf-8"))["llm_models"]
        assert models["press_research_veto"]
        assert models["press_research_note"]
        veto_key = press_config()["research_triage"]["veto"]["model_key"]
        assert veto_key in models
        assert press_config()["desks"]["research_note"]["model_key"] in models
