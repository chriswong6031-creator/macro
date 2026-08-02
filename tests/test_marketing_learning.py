"""XG-W6 — telemetry, learning, health monitor, network tripwire, halt registry.

Every test maps to a line in the charter's XG-W6 row or its §8 assumptions
register. Three of them are AST/source walks over committed code rather than
behaviour tests, because the properties they pin cannot be observed by calling
the function:

  * ``labels.consolidate`` is the ONLY writer under the tracked ledger dir
    (nightly-sole-advancer law) — a RENAMED intraday writer has to fail it too.
  * ``health_monitor`` imports no model client (LLM-never-scores).
  * the >=80% blind-identity number gates NOTHING anywhere in the tree.

Stdlib + pyyaml only (marketing-engine CI lane). No network, no LLM.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import blind_identity as bie  # noqa: E402
from engine.marketing import health_monitor as hm  # noqa: E402
from engine.marketing import labels as lb  # noqa: E402
from engine.marketing import learned_rules as lr  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_export as rx  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _row(account="kelly", day="2026-07-28", surface="post", label=0.05,
         subject=None, **over):
    row = lb.new_row(
        surface=surface,
        subject_id=subject or f"{account}-{day}-{surface}",
        as_of=day, account=account, format=over.pop("fmt", "signal"),
        register=over.pop("register", "analysis"),
        hook_family=over.pop("hook_family", "confirmation_check"),
        observed=over.pop("observed", {"impressions": 1000, "likes": 40,
                                       "reposts": 5, "comments": 5}),
        features=over.pop("features", {}),
        label=label,
        observed_at="2026-07-28T15:00:00Z",
    )
    row.update(over)
    return row


# ===========================================================================
# GATE: per-post telemetry -> labels store, from the LIVE metrics poll
# ===========================================================================
class TestLabelsStore:
    def test_four_named_consumers_one_loop(self):
        """Charter §6: D05 §7 loop == IS-W5 == Persona W4 == Media W2."""
        assert lb.CONSUMERS == (
            "d05_wire_loop", "is_w5_ranker",
            "persona_w4_report_card", "media_w2_scorecard",
        )
        assert lb.DIMS == ("account", "format", "register", "hook_family")

    def test_row_shape_is_l2_retrain_ready_but_nothing_more(self):
        """The retrain job is OUT of scope; the row is SHAPED for it, no more."""
        row = _row()
        for field in ("features", "label", "weight", "label_version"):
            assert field in row, f"{field} must exist for a future L2 retrain"
        assert lb.validate_row(row) == []

    def test_validate_refuses_a_row_with_no_account(self):
        bad = _row()
        bad["account"] = ""
        assert any("account" in e for e in lb.validate_row(bad))

    def test_row_id_is_day_based_so_a_retried_nightly_cannot_double_a_cell(self):
        """The n's here gate the n-floor, so a doubled row silently promotes."""
        a = _row(subject="x1")
        b = _row(subject="x1")
        b["observed_at"] = "2026-07-28T23:59:00Z"   # a later re-harvest
        assert lb.row_id(a) == lb.row_id(b)

    def test_record_observation_writes_HOST_only(self, tmp_path):
        lb.record_observation(_row(), root=tmp_path)
        assert (lb.host_dir(tmp_path) / "labels.jsonl").exists()
        assert not lb.labels_path(tmp_path).exists(), \
            "an intraday write must never touch the tracked ledger"

    def test_record_observation_refuses_an_invalid_row(self, tmp_path):
        bad = _row()
        bad["surface"] = "banner"
        assert lb.record_observation(bad, root=tmp_path)["ok"] is False
        assert not (lb.host_dir(tmp_path) / "labels.jsonl").exists()

    def test_readers_see_the_union_of_tracked_and_host(self, tmp_path):
        lb._write_tracked(lb.labels_path(tmp_path), [_row(subject="tracked")])
        lb.record_observation(_row(subject="host"), root=tmp_path)
        subjects = {r["subject_id"] for r in lb.load_labels(tmp_path)}
        assert subjects == {"tracked", "host"}


class TestPostLabelHarvest:
    """The LIVE source is data/marketing/post_metrics.jsonl (written by
    scripts/marketing_metrics_poll.py, committed by marketing-publish.yml)."""

    def _seed(self, tmp_path, *, impressions=1000, account="flagship"):
        from engine.marketing.outbox import enqueue, make_item, transition

        item = make_item(account=account, kind="signal",
                         text="$PLTR reclaimed the 50-day. Watching.",
                         as_of="2026-07-28", provenance="content_studio", now=NOW)
        enqueue(item, root=tmp_path, max_per_account_day=99)
        transition(item["id"], "approved", actor="t", root=tmp_path)
        transition(item["id"], "posting", actor="t", root=tmp_path)
        transition(item["id"], "posted", actor="t", root=tmp_path,
                   receipt={"external_id": "buf-1", "at": "2026-07-28T13:00:00Z"})
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps({
            "remote_id": "buf-1", "account": account,
            "metrics": {"impressions": impressions, "likes": 30, "reposts": 4,
                        "comments": 6},
            "polled_at": "2026-07-28T14:00:00Z", "ok": True,
        }) + "\n", encoding="utf-8")
        return item

    def test_joins_metrics_to_the_outbox_receipt(self, tmp_path):
        item = self._seed(tmp_path)
        rows = lb.harvest_post_labels(root=tmp_path, now=NOW)
        assert len(rows) == 1
        assert rows[0]["subject_id"] == item["id"]
        assert rows[0]["account"] == "flagship"
        assert rows[0]["format"] == "signal"
        assert rows[0]["observed"]["orphan"] is False
        assert rows[0]["label"] == pytest.approx(40 / 1000)

    def test_zero_impressions_is_a_NULL_not_a_zero_rate(self, tmp_path):
        """An unmeasured post is not a failed post. Folding it in as 0.0 drags
        every cell median toward zero in proportion to poller lag."""
        self._seed(tmp_path, impressions=0)
        row = lb.harvest_post_labels(root=tmp_path, now=NOW)[0]
        assert row["label"] is None
        assert row["adjusted_reason"] == "no_impressions_yet"

    def test_orphan_metrics_row_is_kept_not_dropped(self, tmp_path):
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps({
            "remote_id": "buf-unknown", "account": "sophia",
            "metrics": {"impressions": 500, "likes": 5},
            "polled_at": "2026-07-28T14:00:00Z",
        }) + "\n", encoding="utf-8")
        rows = lb.harvest_post_labels(root=tmp_path, now=NOW)
        assert len(rows) == 1
        assert rows[0]["observed"]["orphan"] is True
        assert rows[0]["format"] == "unknown"

    def test_an_orphan_polled_on_two_days_stays_ONE_row(self, tmp_path):
        """An orphan has no item to take a business date from. Falling back to
        polled_at moves the day every night, which mints a fresh row_id every
        night — one orphan becomes 180 rows, and every one counts toward the n
        the n-floor gates on."""
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        with mp.open("w", encoding="utf-8") as fh:
            for polled in ("2026-07-28T14:00:00Z", "2026-07-29T14:00:00Z",
                           "2026-07-30T14:00:00Z"):
                fh.write(json.dumps({
                    "remote_id": "buf-orphan", "account": "sophia",
                    "metrics": {"impressions": 500, "likes": 5},
                    "metrics_updated_at": "2026-07-28T09:00:00Z",
                    "polled_at": polled,
                }) + "\n")

        ids = set()
        for day in (28, 29, 30):
            when = datetime(2026, 7, day, 15, 0, tzinfo=timezone.utc)
            rows = lb.harvest_post_labels(root=tmp_path, now=when)
            assert len(rows) == 1
            ids.add(rows[0]["id"])
        assert len(ids) == 1, f"three nightlies minted {len(ids)} ids for one orphan"

    def test_orphan_day_prefers_a_fixed_timestamp_over_the_poll_clock(self):
        assert lb._orphan_day({"metrics_updated_at": "2026-07-01T00:00:00Z",
                               "polled_at": "2026-07-30T00:00:00Z"}) == "2026-07-01"
        assert lb._orphan_day({"published_at": "2026-07-02T00:00:00Z",
                               "polled_at": "2026-07-30T00:00:00Z"}) == "2026-07-02"
        assert lb._orphan_day({"_first_seen": "2026-07-03T00:00:00Z",
                               "polled_at": "2026-07-30T00:00:00Z"}) == "2026-07-03"
        # polled_at only as the last resort.
        assert lb._orphan_day({"polled_at": "2026-07-30T00:00:00Z"}) == "2026-07-30"

    def test_orphan_consolidates_to_one_row_across_nightlies(self, tmp_path):
        """The same guarantee through the production consolidator."""
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        with mp.open("w", encoding="utf-8") as fh:
            for polled in ("2026-07-28T14:00:00Z", "2026-07-29T14:00:00Z"):
                fh.write(json.dumps({
                    "remote_id": "buf-orphan", "account": "sophia",
                    "metrics": {"impressions": 500, "likes": 5},
                    "polled_at": polled,
                }) + "\n")
        for day in (28, 29):
            lb.consolidate(now=datetime(2026, 7, day, 23, 0, tzinfo=timezone.utc),
                           root=tmp_path, store=tmp_path / "desk")
        assert len(lb._read_jsonl(lb.labels_path(tmp_path))) == 1

    def test_latest_poll_wins(self, tmp_path):
        self._seed(tmp_path)
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        with mp.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "remote_id": "buf-1", "account": "flagship",
                "metrics": {"impressions": 2000, "likes": 100, "reposts": 0,
                            "comments": 0},
                "polled_at": "2026-07-28T20:00:00Z",
            }) + "\n")
        row = lb.harvest_post_labels(root=tmp_path, now=NOW)[0]
        assert row["observed"]["impressions"] == 2000


class TestReplyLabels:
    def _sent_item(self, store, *, account="kelly", replied=None):
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        item = make_reply_item(account=account)
        assert rq.enqueue(item, store)["ok"]
        rq.transition(item["id"], "approved", actor="t", root=store)
        rq.transition(item["id"], "claimed", actor="t", root=store)
        rq.transition(item["id"], "sent", actor="t", root=store,
                      receipt={"url": "https://x.com/a/status/1"})
        if replied is not None:
            rq.record_outcome(item["id"], root=store, author_replied=replied)
        return item

    def test_author_replyback_is_the_label(self, tmp_path):
        store = tmp_path / "desk"
        self._sent_item(store, replied=True)
        rows = lb.harvest_reply_labels(store=store, root=tmp_path, now=NOW)
        assert len(rows) == 1
        assert rows[0]["label"] == 1.0
        assert rows[0]["surface"] == "reply"

    def test_unpolled_outcome_is_NULL_not_a_miss(self, tmp_path):
        """A reply we never polled and a reply that was ignored are different
        facts; collapsing them makes every early cohort look like a failure."""
        store = tmp_path / "desk"
        self._sent_item(store, replied=None)
        row = lb.harvest_reply_labels(store=store, root=tmp_path, now=NOW)[0]
        assert row["label"] is None
        assert row["adjusted_reason"] == "outcome_not_polled"

    def test_unsent_drafts_produce_no_labels(self, tmp_path):
        """Counting drafts would make the denominator our own productivity."""
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        assert rq.enqueue(make_reply_item(), store)["ok"]
        assert lb.harvest_reply_labels(store=store, root=tmp_path, now=NOW) == []


# ===========================================================================
# GATE: parent-adjusted reply labels — 2-3 covariates AT LAUNCH VOLUME (§8)
# ===========================================================================
class TestParentAdjustment:
    def test_launch_config_declares_exactly_three_covariates(self, cfg):
        cov = cfg["learning"]["parent_adjust"]["covariates"]
        assert cov == ["parent_size", "post_age", "market_intensity"]
        assert len(cov) <= 3, "charter §8: 8 covariates is over-parameterized at launch"

    def test_expansion_is_encoded_as_config_not_a_future_decision(self, cfg):
        pa = cfg["learning"]["parent_adjust"]
        assert pa["expansion_pool"], "the other covariates must be named, not implied"
        assert isinstance(pa["samples_per_covariate"], int)

    def test_covariate_count_is_truncated_to_what_the_sample_supports(self, capsys):
        rows = [_row(subject=f"r{i}", label=0.1) for i in range(40)]
        cfg = {"learning": {"parent_adjust": {
            "covariates": ["parent_size", "post_age", "market_intensity"],
            "samples_per_covariate": 40}}}
        active, meta = lb.active_covariates(rows, cfg=cfg)
        assert active == ["parent_size"], "40 rows supports exactly one covariate"
        assert meta["max_supported"] == 1
        out = capsys.readouterr().out
        assert out.startswith("::warning") or "\n::warning" in out
        assert "over-parameterized" in out

    def test_thin_stratum_yields_a_printed_null_not_a_guess(self):
        rows = [_row(subject=f"r{i}", label=0.1,
                     features={"parent_engagement": 10.0 * i}) for i in range(3)]
        out = lb.parent_adjust(rows, cfg={"learning": {"parent_adjust": {
            "covariates": ["parent_size"], "samples_per_covariate": 1,
            "stratum_n_floor": 5}}})
        assert all(r["adjusted"] is None for r in out)
        assert all("below_floor" in (r["adjusted_reason"] or "") for r in out)

    def test_adjustment_is_a_stratum_lift_anyone_can_check_by_hand(self):
        rows = [_row(subject=f"r{i}", label=v, features={"parent_engagement": 10.0})
                for i, v in enumerate([0.0, 0.1, 0.2, 0.3, 0.4])]
        out = lb.parent_adjust(rows, cfg={"learning": {"parent_adjust": {
            "covariates": ["parent_size"], "samples_per_covariate": 1,
            "stratum_n_floor": 5}}})
        # stratum mean is 0.2; the lift is label - mean.
        assert out[0]["adjusted"] == pytest.approx(-0.2)
        assert out[4]["adjusted"] == pytest.approx(0.2)
        assert out[0]["stratum_n"] == 5

    def test_unknown_covariate_reading_is_its_own_stratum(self):
        """'we did not observe the parent's size' != 'the parent was small'."""
        rows = ([_row(subject=f"k{i}", features={"parent_engagement": 5.0})
                 for i in range(5)]
                + [_row(subject=f"u{i}", features={}) for i in range(5)])
        out = lb.parent_adjust(rows, cfg={"learning": {"parent_adjust": {
            "covariates": ["parent_size"], "samples_per_covariate": 1,
            "stratum_n_floor": 5, "buckets": {"parent_size": [50, 500]}}}})
        buckets = {r["covariates"]["parent_size"] for r in out}
        assert "unknown" in buckets and len(buckets) == 2

    def test_a_null_label_never_becomes_an_adjusted_number(self):
        out = lb.parent_adjust([_row(label=None)], cfg={})
        assert out[0]["adjusted"] is None
        assert out[0]["adjusted_reason"]

    def test_HARVEST_preserves_an_unobserved_parent_as_None(self, tmp_path):
        """Through the PRODUCTION path, not a hand-built row. Coercing an
        unobserved parent to 0.0 buckets it as the SMALLEST parent stratum
        instead of `unknown`, and harvest wins dedup over the producer's
        correct None — so the coerced zero would overwrite the truth."""
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        item = make_reply_item()
        assert rq.enqueue(item, store)["ok"]
        for to in ("approved", "claimed", "sent"):
            rq.transition(item["id"], to, actor="t", root=store, now=NOW,
                          receipt={"url": "https://x.com/a/status/1"})
        rq.record_outcome(item["id"], root=store, author_replied=True)

        row = lb.harvest_reply_labels(store=store, root=tmp_path, now=NOW)[0]
        feats = row["features"]
        assert feats["parent_engagement"] is None, "never observed — not zero"
        assert feats["post_age_min"] is None
        assert feats["score"] is not None, "score IS on the item"

        adjusted = lb.parent_adjust([row], cfg={"learning": {"parent_adjust": {
            "covariates": ["parent_size"], "samples_per_covariate": 1,
            "buckets": {"parent_size": [50, 500]}}}})
        assert adjusted[0]["covariates"]["parent_size"] == "unknown", \
            "an unobserved parent must not join the small-parent stratum"

    def test_HARVEST_keeps_a_real_reading_when_the_producer_banked_one(self, tmp_path):
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        item = make_reply_item()
        item["score_features"] = {"_context": {"engagement": 120.0, "age_min": 9.0,
                                               "reply_count": 4}}
        assert rq.enqueue(item, store)["ok"]
        for to in ("approved", "claimed", "sent"):
            rq.transition(item["id"], to, actor="t", root=store, now=NOW,
                          receipt={"url": "https://x.com/a/status/1"})
        row = lb.harvest_reply_labels(store=store, root=tmp_path, now=NOW)[0]
        assert row["features"]["parent_engagement"] == 120.0
        assert row["features"]["post_age_min"] == 9.0
        assert row["features"]["thread_saturation"] == 4.0


# ===========================================================================
# GATE: weekly admin scorecard — hook family x format x register x account
# ===========================================================================
class TestScorecard:
    def test_cells_key_on_all_four_dims(self):
        card = lb.scorecard([_row()], now=NOW)
        assert set(card["cells"][0]["dims"]) == set(lb.DIMS)
        assert card["consumers"] == list(lb.CONSUMERS)

    def test_thin_cell_is_printed_with_a_seeding_verdict_not_hidden(self):
        card = lb.scorecard([_row(subject=f"r{i}") for i in range(3)], now=NOW)
        cell = card["cells"][0]
        assert cell["verdict"] == "seeding"
        assert "n-floor" in cell["verdict_note"]

    def test_a_full_cell_carries_no_seeding_verdict(self):
        rows = [_row(subject=f"r{i}") for i in range(25)]
        card = lb.scorecard(rows, cfg={"learning": {"n_floor": 20}}, now=NOW)
        assert "verdict" not in card["cells"][0]

    def test_nulls_are_counted_separately_from_labelled_rows(self):
        rows = [_row(subject="a", label=0.1), _row(subject="b", label=None)]
        cell = lb.scorecard(rows, now=NOW)["cells"][0]
        assert cell["n"] == 2 and cell["n_labelled"] == 1 and cell["n_null"] == 1

    def test_north_star_is_NOT_COMPUTED_and_says_what_it_needs(self):
        """Charter §8: undefined at zero. Not computed-and-hidden — not
        computed, with both missing inputs named."""
        ns = lb.north_star([_row()], now=NOW)
        assert ns["active"] is False
        assert "not computed" in ns["reason"]
        assert len(ns["needs"]) == 2

    def test_north_star_has_no_unreachable_active_branch(self):
        """Nothing writes a follower series, so an `active: True` branch could
        never be reached — and dead code that implies a capability reads to the
        next maintainer as 'this works once you cross the floor'."""
        rows = [_row(subject=f"r{i}", observed={"impressions": 10, "likes": 1,
                                                "followers_at_post": 99999})
                for i in range(30)]
        ns = lb.north_star(rows, now=NOW)
        assert ns["active"] is False, "even a fabricated follower count cannot arm it"
        # ...but the reading IS surfaced, so the day a series lands it shows up.
        assert ns["observed_followers"]["kelly"] == 99999

    def test_no_production_path_writes_a_follower_count(self):
        """The premise of the branch removal, pinned. If someone wires a
        follower series, this fails and north_star gets revisited."""
        writers = []
        for rel in ("scripts/marketing_metrics_poll.py",
                    "engine/marketing/social_publisher.py",
                    "engine/marketing/labels.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                if f'"{lb.FOLLOWERS_OBSERVED_KEY}":' in line:
                    writers.append(f"{rel}:{i}")
        assert not writers, (
            "a follower series now exists — north_star can be computed: " + str(writers))

    def test_bottleneck_table_is_raw_counts_during_cold_start(self):
        table = lb.bottleneck_table([_row(), _row(account="cici")], now=NOW)
        assert table["basis"] == "raw_counts"
        assert {b["account"] for b in table["accounts"]} == {"kelly", "cici"}

    def test_drafts_and_kills_are_NOT_counted_as_replies_sent(self):
        """At M0 the true sent count is ZERO. A counter reporting drafts as
        'replies sent' is a false statement about public activity."""
        enqueued = _row(subject="q1", surface="reply", label=None,
                        observed={"stage": "enqueued"})
        killed = _row(subject="k1", surface="reply", label=None,
                      observed={"stage": "abstained"})
        killed["weight"] = 0.0
        block = lb.bottleneck_table([enqueued, killed], now=NOW)["accounts"][0]
        assert block["replies_sent"] == 0
        assert block["replies_enqueued"] == 1
        assert block["replies_abstained"] == 1
        assert block["contributions"] == 0, "nothing was published"
        assert block["unmeasured"] == 0, "a draft is not an unmeasured post"

    def test_a_weight_zero_row_counts_as_a_kill_even_without_a_stage(self):
        """Belt and braces for a future writer that forgets the stage field."""
        row = _row(subject="w0", surface="reply", label=None, observed={})
        row["weight"] = 0.0
        block = lb.bottleneck_table([row], now=NOW)["accounts"][0]
        assert block["replies_abstained"] == 1 and block["replies_sent"] == 0

    def test_a_genuinely_sent_reply_counts_as_sent(self):
        sent = _row(subject="s1", surface="reply", label=1.0,
                    observed={"author_replied": True, "sent_at": "2026-07-28T15:00:00Z"})
        block = lb.bottleneck_table([sent], now=NOW)["accounts"][0]
        assert block["replies_sent"] == 1
        assert block["author_replies"] == 1
        assert block["contributions"] == 1


# ===========================================================================
# GATE: nightly is the SOLE advancer
# ===========================================================================
class TestConsolidator:
    def test_consolidate_advances_tracked_and_clears_the_host_spool(self, tmp_path):
        lb.record_observation(_row(subject="h1"), root=tmp_path)
        out = lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk")
        assert out["tracked_after"] == 1
        assert lb.labels_path(tmp_path).exists()
        assert lb.scorecard_path(tmp_path).exists()
        assert not (lb.host_dir(tmp_path) / "labels.jsonl").exists()

    def test_consolidate_is_idempotent(self, tmp_path):
        """A retried nightly must not double a cell's n — the n-floor gates on it."""
        lb.record_observation(_row(subject="h1"), root=tmp_path)
        lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk")
        first = len(lb._read_jsonl(lb.labels_path(tmp_path)))
        lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk")
        assert len(lb._read_jsonl(lb.labels_path(tmp_path))) == first == 1

    def test_env_kill_switch_is_real(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("MARKETING_LEARNING_ENABLED", "0")
        lb.record_observation(_row(), root=tmp_path)
        out = lb.consolidate(now=NOW, root=tmp_path)
        assert out["skipped"] == "disabled"
        assert not lb.labels_path(tmp_path).exists()
        assert "::notice" in capsys.readouterr().out

    def test_empty_repo_writes_a_valid_empty_artifact(self, tmp_path):
        out = lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk")
        assert out["tracked_after"] == 0
        card = json.loads(lb.scorecard_path(tmp_path).read_text(encoding="utf-8"))
        assert card["schema"] == lb.SCORECARD_SCHEMA and card["cells"] == []

    def test_retention_drops_rows_past_the_window(self, tmp_path):
        old = _row(subject="old", day="2025-01-01")
        lb.record_observation(old, root=tmp_path)
        lb.record_observation(_row(subject="new"), root=tmp_path)
        lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk",
                       cfg={"learning": {"retention_days": 30}})
        kept = {r["subject_id"] for r in lb._read_jsonl(lb.labels_path(tmp_path))}
        assert kept == {"new"}

    def test_AST_GUARD_consolidate_is_the_only_tracked_writer(self):
        """Nightly-sole-advancer law, pinned in source so a RENAMED intraday
        writer fails too. Only ``_write_tracked``/``_write_tracked_json`` may
        open a handle under the tracked dir, and only the consolidator calls
        them."""
        src = (ROOT / "engine" / "marketing" / "labels.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        allowed_writers = {"_write_tracked", "_write_tracked_json"}
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                fn = inner.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                # `open(...)` in append/write mode, anywhere but the host writer.
                if name == "open" and node.name not in {"record_observation",
                                                        "_read_jsonl", "_spool_lock"}:
                    mode = "".join(
                        a.value for a in inner.args[1:2]
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    )
                    if "w" in mode or "a" in mode:
                        offenders.append(f"{node.name} opens a write handle")
                if name in allowed_writers and node.name not in {
                        "consolidate", "_consolidate_locked"}:
                    offenders.append(f"{node.name} calls {name}")
        assert not offenders, (
            "only consolidate() may advance the tracked ledger: " + "; ".join(offenders))


# ===========================================================================
# GATE: per-account health monitor — deterministic telemetry only
# ===========================================================================
class TestHealthMetrics:
    def test_approval_rate_null_below_min_observations(self):
        res = hm.approval_rate({"approved": 1, "rejected": 1})
        assert res["value"] is None and res["verdict"] == "null"

    def test_approval_rate_warns_under_the_threshold(self):
        res = hm.approval_rate({"approved": 2, "rejected": 8})
        assert res["value"] == 0.2 and res["verdict"] == "warn"

    def test_holds_are_excluded_from_the_denominator(self):
        """A hold is 'not yet', not 'no'. Counting it makes a careful operator
        look like a failing desk."""
        res = hm.approval_rate({"approved": 6, "rejected": 2, "held": 40})
        assert res["value"] == 0.75 and res["verdict"] == "ok" and res["n"] == 8

    def test_reason_mix_distinguishes_concentrated_from_diffuse(self):
        conc = hm.rejection_reason_mix(["off_voice"] * 8 + ["stale"] * 2)
        diff = hm.rejection_reason_mix(["a", "b", "c", "d", "e", "f"])
        assert conc["shape"] == "concentrated" and conc["top_reason"] == "off_voice"
        assert diff["shape"] == "diffuse"

    def test_engagement_trend_is_median_based_so_one_viral_post_cannot_mask_a_collapse(self):
        base_day = (NOW - timedelta(days=20)).strftime("%Y-%m-%d")
        rows = [_row(subject=f"b{i}", day=base_day,
                     observed={"likes": 100, "reposts": 0, "comments": 0})
                for i in range(6)]
        rows += [_row(subject=f"r{i}", day="2026-07-27",
                      observed={"likes": 1, "reposts": 0, "comments": 0})
                 for i in range(5)]
        rows += [_row(subject="viral", day="2026-07-27",
                      observed={"likes": 100000, "reposts": 0, "comments": 0})]
        res = hm.engagement_trend(rows, now=NOW)
        assert res["collapsed"] is True, "a mean would have hidden this"

    def test_engagement_trend_null_when_the_baseline_is_zero(self):
        rows = [_row(subject=f"b{i}", day=(NOW - timedelta(days=20)).strftime("%Y-%m-%d"),
                     observed={"likes": 0, "reposts": 0, "comments": 0})
                for i in range(6)]
        rows += [_row(subject=f"r{i}", day="2026-07-27",
                      observed={"likes": 3, "reposts": 0, "comments": 0})
                 for i in range(6)]
        res = hm.engagement_trend(rows, now=NOW)
        assert res["value"] is None and "undefined" in res["reason"]

    def test_last_nine_reads_the_window_a_profile_visitor_sees(self):
        rows = [_row(subject=f"p{i}", features={"has_media": i < 4})
                for i in range(12)]
        res = hm.last_nine(rows)
        assert res["n"] == 9
        assert res["with_receipt"] <= 4

    def test_last_nine_flags_a_receipt_free_grid(self):
        rows = [_row(subject=f"p{i}", features={"has_media": False})
                for i in range(9)]
        res = hm.last_nine(rows)
        assert res["verdict"] == "warn"
        assert any("receipt" in p for p in res["problems"])

    def test_an_all_null_account_reads_unmeasured_not_ok(self):
        """A null is not a pass. 'unmeasured' and 'ok' are different
        instructions to an operator."""
        card = hm.evaluate_account("kelly", labels=[], decisions={},
                                   reason_list=[], now=NOW)
        assert card["verdict"] == "unmeasured"

    def test_AST_GUARD_no_model_client_in_the_monitor(self):
        """LLM-never-scores (charter §2 amendment 9), pinned in source."""
        src = (ROOT / "engine" / "marketing" / "health_monitor.py").read_text(
            encoding="utf-8")
        banned = ("anthropic", "openai", "llm_client", "brain_gateway",
                  "call_llm", "copywriter_llm")
        tree = ast.parse(src)
        seen: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                seen += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                seen.append(node.module or "")
        assert not [m for m in seen if any(b in m.lower() for b in banned)], \
            "every health-monitor input must be deterministic telemetry"


# ===========================================================================
# GATE: network tripwire — fleet signal, PER-ACCOUNT effect
# ===========================================================================
class TestNetworkTripwire:
    def _collapsed(self, *accounts):
        return {a: {"metrics": {"engagement_trend": {"collapsed": True}}}
                for a in accounts}

    def test_one_collapsed_account_is_weather_not_a_trip(self):
        out = hm.evaluate_fleet(self._collapsed("kelly"), labels=[], now=NOW)
        assert out["tripped"] is False and out["implicated"] == []

    def test_simultaneous_collapse_trips_and_names_the_implicated(self):
        out = hm.evaluate_fleet(self._collapsed("kelly", "cici", "sophia"),
                                labels=[], now=NOW)
        assert out["tripped"] is True
        assert out["implicated"] == ["cici", "kelly", "sophia"]
        assert out["signals"]["simultaneous_collapse"]["fired"] is True

    def _series(self, per_account_by_day: dict[str, list[float]],
                posts_by_day: list[int] | None = None) -> list[dict]:
        """Build label rows with an explicit POST COUNT per day per account.

        The post count is the confound: one nightly content plan drives all
        seven desks, so their daily post counts move together whatever the
        audience does.
        """
        rows: list[dict] = []
        days = len(next(iter(per_account_by_day.values())))
        posts = posts_by_day or [1] * days
        for i in range(days):
            day = (datetime(2026, 7, 1, tzinfo=timezone.utc)
                   + timedelta(days=i)).strftime("%Y-%m-%d")
            for acc, per_post in per_account_by_day.items():
                for k in range(posts[i]):
                    rows.append(_row(subject=f"{acc}-{i}-{k}", account=acc, day=day,
                                     observed={"likes": per_post[i], "reposts": 0,
                                               "comments": 0}))
        return rows

    def test_shared_posting_volume_alone_does_NOT_trip_the_wire(self):
        """THE CONFOUND, excluded. Every desk posts more on busy days (one
        nightly plan drives all seven) while per-post engagement is flat and
        independent. Summed daily engagement would correlate perfectly here and
        halt the whole fleet; per-post engagement must not."""
        flat = {
            "kelly":  [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "cici":   [7.0, 9.0, 6.0, 8.0, 7.0, 9.0, 6.0, 8.0, 7.0, 9.0, 6.0, 8.0],
            "sophia": [5.0, 4.0, 6.0, 4.0, 5.0, 6.0, 4.0, 5.0, 6.0, 4.0, 5.0, 6.0],
        }
        busy = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5, 1, 5]   # the shared driver
        out = hm.evaluate_fleet({}, labels=self._series(flat, busy), now=NOW)
        assert out["signals"]["cross_account_corr"]["fired"] is False, (
            "posting volume is our own scheduler, not a platform signal")

    def test_lockstep_PER_POST_engagement_trips_the_correlation_wire(self):
        """The real signal: post counts differ, but every desk's per-post
        engagement moves the same way on the same days."""
        rising = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
        moves_together = {
            "kelly":  rising,
            "cici":   [v * 2 for v in rising],
            "sophia": [v + 3 for v in rising],
        }
        # Deliberately UNEQUAL post counts, so the correlation cannot be coming
        # from a shared volume driver.
        out = hm.evaluate_fleet({}, labels=self._series(
            moves_together, [1, 3, 2, 1, 4, 1, 2, 3, 1, 2, 1, 3]), now=NOW)
        assert out["signals"]["cross_account_corr"]["fired"] is True
        assert out["tripped"] is True

    def test_spearman_is_none_not_zero_on_a_constant_series(self):
        assert hm.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None

    def test_the_nightly_only_cadence_is_recorded_as_an_M2_precondition(self):
        """The reviewer's observation, pinned in both docs: at M2/M3 an account
        can keep sending for a full day after the signal that should have
        stopped it."""
        charter = (ROOT / "research" / "agentic_media"
                   / "X_GROWTH_UNIFIED_OPERATION_BY_FABLE.md").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "reply_desk_runbook.md").read_text(encoding="utf-8")
        for text in (charter, runbook):
            assert "NIGHTLY ONLY" in text or "nightly-only" in text.lower()
            assert "precondition for any dial flip above M1" in text \
                or "precondition for any flip above M1" in text

    def test_the_charter_records_what_XG_W6_shipped(self):
        charter = (ROOT / "research" / "agentic_media"
                   / "X_GROWTH_UNIFIED_OPERATION_BY_FABLE.md").read_text(encoding="utf-8")
        assert "docs/blind_identity_eval_prereg.md" in charter
        assert "GATES_NOTHING" in charter
        assert "engine/marketing/health_monitor.py" in charter

    def test_the_launch_default_WARNS_rather_than_halting_seven_desks(self, cfg):
        """`implicated` is every account in any correlated pair, and 3 of 21
        pairs fires it. Halting on that with no correlation baseline costs
        seven manual clears on one confounded reading."""
        assert cfg["learning"]["health"]["network_tripwire"]["action"] == "warn"
        assert hm.DEFAULTS["network_tripwire"]["action"] == "warn"

    def test_a_trip_at_the_launch_default_writes_NO_halt_rows(self, tmp_path, cfg):
        lb._write_tracked(lb.labels_path(tmp_path), self._series_collapse())
        report = hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=cfg)
        # The wire FIRES — it is measuring, which is the point of warn mode...
        assert report["network_tripwire"]["tripped"] is True
        assert report["network_tripwire"]["implicated"] == ["cici", "kelly", "sophia"]
        # ...and halts nothing.
        assert report["tripped_this_run"] == []
        assert hm.halted_accounts(tmp_path) == []

    def test_arming_halt_implicated_writes_one_row_per_implicated_account(
            self, tmp_path, cfg):
        armed = json.loads(json.dumps(cfg))
        armed["learning"]["health"]["network_tripwire"]["action"] = "halt_implicated"
        lb._write_tracked(lb.labels_path(tmp_path), self._series_collapse())
        report = hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=armed)
        assert sorted(report["tripped_this_run"]) == ["cici", "kelly", "sophia"]
        # One row per account — never a fleet switch.
        assert sorted(hm.halted_accounts(tmp_path)) == ["cici", "kelly", "sophia"]

    def _series_collapse(self) -> list[dict]:
        """Three desks whose engagement collapses on the same day."""
        rows: list[dict] = []
        base_day = (NOW - timedelta(days=20)).strftime("%Y-%m-%d")
        for acc in ("kelly", "cici", "sophia"):
            rows += [_row(subject=f"{acc}-b{i}", account=acc, day=base_day,
                          observed={"likes": 100, "reposts": 0, "comments": 0})
                     for i in range(6)]
            rows += [_row(subject=f"{acc}-r{i}", account=acc, day="2026-07-27",
                          observed={"likes": 1, "reposts": 0, "comments": 0})
                     for i in range(6)]
        return rows

    def test_there_is_no_global_halt_code_path(self):
        """Charter §5: a failure must halt one account without halting seven.
        The fleet wire returns a LIST of implicated accounts, and the runner
        writes one row each — there is nowhere to set a fleet switch."""
        src = (ROOT / "engine" / "marketing" / "health_monitor.py").read_text(
            encoding="utf-8")
        assert "halt_all" not in src and "halt_fleet" not in src
        out = hm.evaluate_fleet(self._collapsed("a", "b", "c"), labels=[], now=NOW)
        assert isinstance(out["implicated"], list)


# ===========================================================================
# GATE: the halt registry
# ===========================================================================
class TestHaltRegistry:
    def test_trip_then_is_halted_only_for_that_account(self, tmp_path):
        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=tmp_path)
        assert hm.is_halted("kelly", root=tmp_path) is True
        assert hm.is_halted("cici", root=tmp_path) is False
        assert hm.halted_accounts(tmp_path) == ["kelly"]

    def test_trip_announces_at_line_start(self, tmp_path, capsys):
        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") for line in out.splitlines())

    def test_retrip_preserves_since_so_darkness_duration_stays_true(self, tmp_path):
        hm.trip("kelly", reason="a", evidence={}, now=NOW, root=tmp_path)
        later = NOW + timedelta(days=3)
        rec = hm.trip("kelly", reason="b", evidence={}, now=later, root=tmp_path)
        assert rec["since"] == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert rec["updated_at"] == later.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_only_an_operator_clears_and_the_actor_is_required(self, tmp_path):
        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        assert hm.clear("kelly", actor="", now=NOW, root=tmp_path)["ok"] is False
        assert hm.clear("kelly", actor="chris", now=NOW, root=tmp_path)["ok"] is True
        assert hm.is_halted("kelly", root=tmp_path) is False

    def test_the_monitor_cannot_clear_its_own_trip(self, tmp_path, cfg):
        """An intermittent condition would otherwise flap the desk in silence."""
        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=tmp_path)
        hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=cfg)
        assert hm.is_halted("kelly", root=tmp_path) is True

    def test_corrupt_registry_fails_OPEN_and_says_so(self, tmp_path, capsys):
        """Fail-closed here would silence all seven desks with no way to tell
        why — the fleet-wide outage the per-account design exists to prevent."""
        p = hm.halts_path(tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        assert hm.load_halts(tmp_path) == {}
        assert "::warning" in capsys.readouterr().out

    def test_dry_run_evaluates_without_writing_the_registry(self, tmp_path, cfg):
        report = hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=cfg,
                        apply_halts=False)
        assert report["apply_halts"] is False
        assert report["tripped_this_run"] == []

    def test_dry_run_STILL_writes_health_json(self, tmp_path, cfg):
        """apply_halts=False means no HALT-REGISTRY writes, not no report.
        Operator visibility is the point of the flag."""
        hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=cfg,
               apply_halts=False)
        assert hm.health_path(tmp_path).exists()
        assert hm.load_health(tmp_path)["schema"] == hm.HEALTH_SCHEMA
        assert not hm.halts_path(tmp_path).exists(), "no registry write"

    def test_a_telemetry_SILENT_desk_still_appears_as_unmeasured(self, tmp_path, cfg):
        """A desk that posted nothing is the desk most likely to be broken.
        Deriving the roster from label rows would drop it out entirely, and
        'missing' and 'healthy' read identically."""
        lb._write_tracked(lb.labels_path(tmp_path),
                          [_row(account="kelly", subject="k1")])
        report = hm.run(now=NOW, root=tmp_path, store=tmp_path / "desk", cfg=cfg)
        graded = {c["account"] for c in report["accounts"]}
        assert "kelly" in graded
        assert len(graded) > 1, "the whole enabled roster must be graded"
        silent = next(c for c in report["accounts"] if c["account"] != "kelly")
        assert silent["verdict"] == "unmeasured"
        assert silent["n_rows"] == 0

    def test_the_roster_comes_from_enabled_desks_in_config(self, cfg):
        names = hm.roster(cfg, root=ROOT)
        assert names, "config must yield a desk roster"
        enabled = {a["id"] for a in (cfg.get("desk_network") or {}).get("accounts") or []
                   if a.get("enabled")}
        assert set(names) <= enabled

    def test_the_NIGHTLY_passes_the_config_roster(self):
        src = (ROOT / "scripts" / "marketing_learning_nightly.py").read_text(
            encoding="utf-8")
        assert "_health.roster(cfg" in src
        assert "accounts=_health.roster" in src


class TestNightlyEntryPoint:
    """The documented CLI semantics have to be the implemented ones."""

    def test_dry_run_does_NOT_advance_the_tracked_ledger(self, tmp_path):
        import scripts.marketing_learning_nightly as nightly

        lb.record_observation(_row(), root=tmp_path)
        rc = nightly.main(["--root", str(tmp_path), "--store", str(tmp_path / "desk"),
                           "--dry-run", "--now", "2026-07-28T23:00:00Z"])
        assert rc == 0
        assert not lb.labels_path(tmp_path).exists(), \
            "--dry-run consolidating is the opposite of a dry run"
        assert not lb.scorecard_path(tmp_path).exists()
        # ...but health IS evaluated and reported.
        assert hm.health_path(tmp_path).exists()
        assert not hm.halts_path(tmp_path).exists()

    def test_a_real_run_DOES_advance_it(self, tmp_path):
        import scripts.marketing_learning_nightly as nightly

        lb.record_observation(_row(), root=tmp_path)
        rc = nightly.main(["--root", str(tmp_path), "--store", str(tmp_path / "desk"),
                           "--now", "2026-07-28T23:00:00Z"])
        assert rc == 0
        assert lb.labels_path(tmp_path).exists()
        assert lb.scorecard_path(tmp_path).exists()

    def test_an_empty_tree_is_a_clean_exit_zero(self, tmp_path):
        import scripts.marketing_learning_nightly as nightly

        assert nightly.main(["--root", str(tmp_path),
                             "--store", str(tmp_path / "desk")]) == 0

    def test_a_failing_outcome_poll_still_lets_labels_and_health_advance(
            self, tmp_path, monkeypatch, capsys):
        """The poll is the only network step and it runs FIRST. An unhandled
        hiccup would take consolidation down with it — and daily.yml's `exit 0`
        would turn that into a silent night where nothing advanced."""
        import scripts.marketing_learning_nightly as nightly
        from engine.marketing import reply_producer as rp

        def _boom(**kw):
            raise RuntimeError("twitterapi.io timeout")

        monkeypatch.setattr(rp, "poll_reply_outcomes", _boom)
        lb.record_observation(_row(), root=tmp_path)
        rc = nightly.main(["--root", str(tmp_path), "--store", str(tmp_path / "desk"),
                           "--now", "2026-07-28T23:00:00Z"])
        assert rc == 0
        assert lb.labels_path(tmp_path).exists(), "consolidation must still run"
        assert hm.health_path(tmp_path).exists(), "health must still run"
        out = capsys.readouterr().out
        assert any(line.startswith("::warning title=learning")
                   for line in out.splitlines()), "the failure must be announced"

    def test_outcome_polling_runs_before_consolidation(self, tmp_path, capsys):
        import scripts.marketing_learning_nightly as nightly

        nightly.main(["--root", str(tmp_path), "--store", str(tmp_path / "desk"),
                      "--now", "2026-07-28T23:00:00Z"])
        out = capsys.readouterr().out
        assert "reply outcomes" in out
        assert out.index("reply outcomes") < out.index("labels tracked_before"), \
            "outcomes must be polled before the labels that read them"


# ===========================================================================
# GATE (THE ONE THAT MATTERS): one account halts, the other six do not
# ===========================================================================
class TestPerAccountHaltIsolation:
    """Charter §5 / XG-W4 §0: 'failures must be able to halt one account
    without halting seven'. Proven on BOTH rails."""

    FLEET = ("flagship", "founder", "meagan", "sophia", "kelly", "cici",
             "mastermind_news")

    def test_reply_rail_halts_A_and_exports_B_through_G(self, tmp_path, cfg):
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        m1 = json.loads(json.dumps(cfg))
        # PACING OFF: this test pins HALT ISOLATION, one axis. Burst pacing is a
        # second, orthogonal gate that holds every desk outside its session
        # window — with it on at a fixed NOW the whole fleet is held for a
        # reason that has nothing to do with kelly's halt, and the test would
        # pass or fail on what time the fixture happens to name. The
        # halt-vs-pacing INTERACTION is pinned separately below.
        m1.setdefault("reply_desk", {}).setdefault("pacing", {})["enabled"] = False
        for acc in self.FLEET:
            m1["reply_desk"]["mode"].setdefault("accounts", {})[acc] = "M1"
            m1.setdefault("reply_desk", {}).setdefault("daily_caps", {}) \
              .setdefault("accounts", {})[acc] = 5

        ids = {}
        for i, acc in enumerate(self.FLEET):
            item = make_reply_item(account=acc, thread=f"19000000000000000{i:02d}")
            assert rq.enqueue(item, store)["ok"], acc
            assert rq.approve(item["id"], root=store)
            ids[acc] = item["id"]

        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=tmp_path)

        out = rx.export_approved(cfg=m1, root=store, repo_root=tmp_path, now=NOW)

        assert ids["kelly"] in out["skipped_halt"], "the halted desk must export nothing"
        assert ids["kelly"] not in out["exported"]
        for acc in self.FLEET:
            if acc == "kelly":
                continue
            assert ids[acc] in out["exported"], f"{acc} must be unaffected by kelly's halt"
        assert out["halted_accounts"] == ["kelly"]

    def test_a_pacing_hold_is_reported_apart_from_a_spent_daily_cap(self, tmp_path, cfg):
        """The two holds have OPPOSITE remedies, so they may not share a bucket.

        Outside its burst window an item used to report as `skipped_cap` with
        `cap: 0`, which reads as "the daily cap is spent — raise it". Raising it
        releases nothing: the gate is the burst schedule, and it clears itself
        when the next window opens. The bucket IS the remedy, so it is pinned.
        """
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        m1 = json.loads(json.dumps(cfg))
        m1["reply_desk"]["mode"].setdefault("accounts", {})["sophia"] = "M1"
        m1.setdefault("reply_desk", {}).setdefault("daily_caps", {}) \
          .setdefault("accounts", {})["sophia"] = 5
        # Pacing ON with no burst that can contain NOW: zero planned bursts is
        # the unambiguous "outside every window" state, and it needs no guess
        # about which hour the fixture clock lands on.
        pacing = m1.setdefault("reply_desk", {}).setdefault("pacing", {})
        pacing["enabled"] = True
        pacing.setdefault("bursts", {})["per_day"] = 0

        item = make_reply_item(account="sophia", thread="19000000000000900")
        assert rq.enqueue(item, store)["ok"]
        assert rq.approve(item["id"], root=store)

        out = rx.export_approved(cfg=m1, root=store, repo_root=tmp_path, now=NOW)

        assert item["id"] in out["skipped_pacing"], (
            "a burst-window hold must report as pacing, never as a spent daily cap")
        assert item["id"] not in out["skipped_cap"]
        assert item["id"] not in out["exported"]

    def test_reply_rail_refuses_a_claim_on_a_halted_desk(self, tmp_path, cfg):
        from tests._xgw6_helpers import make_reply_item  # type: ignore

        store = tmp_path / "desk"
        m1 = json.loads(json.dumps(cfg))
        m1["reply_desk"]["mode"]["accounts"]["kelly"] = "M1"
        item = make_reply_item(account="kelly")
        assert rq.enqueue(item, store)["ok"]
        assert rq.approve(item["id"], root=store)
        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        assert rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1,
                                    root=store, repo_root=tmp_path, now=NOW) is None

    def test_post_rail_halts_A_and_posts_B(self, monkeypatch, tmp_path):
        """End-to-end through scripts/marketing_publisher.main()."""
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import (current_statuses, enqueue,  # noqa: PLC0415
                                             make_item, transition)

        now_iso = "2026-07-28T13:00:00Z"
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "marketing.yml").write_text(
            "sentinel:\n  max_posts_per_account_per_day: 9\n"
            "publish:\n  backend: buffer\n  require_approval: true\n"
            "  auto_approve: false\n  min_minutes_between_any_posts: 0\n"
            "  channels:\n    kelly: \"buf-kelly\"\n    cici: \"buf-cici\"\n"
            "  links_allowed:\n    kelly: false\n    cici: false\n",
            encoding="utf-8")
        qp = tmp_path / "data" / "marketing"
        qp.mkdir(parents=True, exist_ok=True)
        (qp / "live_quotes_snapshot.json").write_text(
            json.dumps({"asof": now_iso, "quotes": {}}), encoding="utf-8")

        # Deliberately unrelated copy: the outbox's own cross-account near-dup
        # radar rejects two desks posting the same sentence, so a fixture that
        # reused one string would fail on THAT gate and prove nothing about
        # halts.
        texts = {
            "kelly": "Credit spreads widened while capex guidance held steady.",
            "cici": "Shanghai turnover thinned into the close ahead of the print.",
        }
        ids = {}
        for acc in ("kelly", "cici"):
            item = make_item(account=acc, kind="macro", text=texts[acc],
                             as_of="2026-07-28", scheduled_at="immediate",
                             provenance="content_studio", now=NOW)
            enqueue(item, root=tmp_path, max_per_account_day=99)
            transition(item["id"], "approved", actor="t", root=tmp_path)
            ids[acc] = item["id"]

        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=tmp_path)

        posted: list[str] = []

        class _Fake:
            backend = "buffer"

            def publish(self, **kw):
                from engine.marketing.social_publisher import Receipt
                posted.append(kw.get("text", ""))
                return Receipt(True, "buf-x", None, None, "buffer", now_iso)

            def list_channels(self):
                return []

        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: _Fake())
        rc = pub.main(["--live", "--root", str(tmp_path), "--now", now_iso])

        assert rc == 0
        statuses = current_statuses(tmp_path)
        assert statuses[ids["kelly"]] == "approved", "halted desk must not post"
        assert statuses[ids["cici"]] == "posted", "the other desk must be unaffected"
        assert len(posted) == 1 and "Shanghai" in posted[0]

    def test_the_admin_dry_run_preview_hides_a_halted_desk(self, tmp_path):
        """A halted desk under 'would post' tells the operator the exact
        opposite of what a live run does."""
        import scripts.marketing_publisher as pub
        from engine.marketing import outbox as ob  # noqa: PLC0415

        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "marketing.yml").write_text(
            "sentinel:\n  max_posts_per_account_per_day: 9\n"
            "publish:\n  backend: buffer\n  min_minutes_between_any_posts: 0\n"
            "  channels:\n    kelly: \"buf-kelly\"\n    cici: \"buf-cici\"\n",
            encoding="utf-8")
        texts = {
            "kelly": "Credit spreads widened while capex guidance held steady.",
            "cici": "Shanghai turnover thinned into the close ahead of the print.",
        }
        for acc in ("kelly", "cici"):
            item = ob.make_item(account=acc, kind="macro", text=texts[acc],
                                as_of="2026-07-28", scheduled_at="immediate",
                                provenance="content_studio", now=NOW)
            ob.enqueue(item, root=tmp_path, max_per_account_day=99)
            ob.transition(item["id"], "approved", actor="t", root=tmp_path)

        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=tmp_path)
        rep = pub.dry_run_report(root=tmp_path, now=NOW)

        assert rep["ok"] is True
        assert rep["counts"]["skipped_halt"] == 1
        assert rep["halted_accounts"] == ["kelly"]
        assert {r["account"] for r in rep["would_post"]} == {"cici"}

    def test_post_rail_auto_approve_skips_a_halted_desk(self, tmp_path):
        from engine.marketing import outbox as ob  # noqa: PLC0415

        # Unrelated copy — see the note in the sibling test: the outbox's own
        # cross-account near-dup radar would otherwise reject the second item.
        texts = {
            "kelly": "Credit spreads widened while capex guidance held steady.",
            "cici": "Shanghai turnover thinned into the close ahead of the print.",
        }
        items = {}
        for acc in ("kelly", "cici"):
            item = ob.make_item(account=acc, kind="macro", text=texts[acc],
                                as_of="2026-07-28", scheduled_at="immediate",
                                provenance="content_studio", now=NOW)
            ob.enqueue(item, root=tmp_path, max_per_account_day=99)
            items[acc] = item["id"]

        import scripts.marketing_publisher as pub
        approved = pub._auto_approve_pass(
            ob, ob.fold_state(tmp_path),
            {"channels": {"kelly": "c1", "cici": "c2"}},
            cap=9, now=NOW, live=False, account=None, posted_today={},
            validate_postable=lambda *a, **k: [], root=tmp_path,
            halted={"kelly"},
        )
        assert items["cici"] in approved
        assert items["kelly"] not in approved


# ===========================================================================
# GATE: learning without collapse — a rule that cannot be reverted is refused
# ===========================================================================
class TestLearnedRules:
    def _rule(self, **over):
        kwargs = dict(kind="reply_family", path="reply_desk.families.kelly",
                      value=["missing_variable"], revert_present=False,
                      evidence={"n": 40, "verdict": "ok"}, account="kelly",
                      now=NOW)
        kwargs.update(over)
        return lr.make_rule(**kwargs)

    def test_a_valid_rule_validates(self):
        assert lr.validate_rule(self._rule()) == []

    def test_a_rule_with_NO_revert_block_is_refused(self):
        """Charter §8: a rule that cannot be reverted may not be learned."""
        bad = self._rule()
        del bad["revert"]
        errs = lr.validate_rule(bad)
        assert any("cannot be reverted" in e for e in errs)

    def test_revert_present_must_be_a_bool_not_inferred(self):
        bad = self._rule()
        bad["revert"] = {"value": 1}
        assert any("revert.present" in e for e in lr.validate_rule(bad))

    def test_restoring_rule_must_carry_the_value_to_restore(self):
        bad = self._rule(revert_present=True)
        del bad["revert"]["value"]
        assert any("nothing to restore" in e for e in lr.validate_rule(bad))

    def test_thin_evidence_is_refused(self):
        """'No learning promotes from one viral accident', with teeth."""
        errs = lr.validate_rule(self._rule(evidence={"n": 2}))
        assert any("viral accident" in e for e in errs)

    def test_a_seeding_cell_cannot_support_a_ranking_claim(self):
        errs = lr.validate_rule(self._rule(evidence={"n": 40, "verdict": "seeding"}))
        assert any("seeding" in e for e in errs)

    def test_apply_then_rollback_deletes_a_first_time_key(self, tmp_path):
        rule = self._rule()
        assert lr.apply_rule(rule, now=NOW, root=tmp_path)["ok"]
        assert rule["path"] in lr.active(tmp_path)
        out = lr.rollback(rule["version_id"], now=NOW, root=tmp_path, actor="chris")
        assert out["ok"] and out["restored"]["action"] == "deleted"
        assert rule["path"] not in lr.active(tmp_path)

    def test_rollback_restores_a_previous_value_and_stays_revertible(self, tmp_path):
        """The realistic sequence: a first rule sets the key, a second
        supersedes it declaring the first's value as its revert."""
        first = self._rule(value=["compression"])          # revert_present=False
        assert lr.apply_rule(first, now=NOW, root=tmp_path)["ok"]

        second = self._rule(value=["missing_variable"], revert_present=True,
                            revert_value=["compression"])
        assert lr.apply_rule(second, now=NOW, root=tmp_path)["ok"]
        assert lr.active(tmp_path)[second["path"]]["value"] == ["missing_variable"]

        out = lr.rollback(second["version_id"], now=NOW, root=tmp_path, actor="chris")
        assert out["restored"]["value"] == ["compression"]
        restored = lr.active(tmp_path)[second["path"]]
        assert restored["value"] == ["compression"]
        assert lr.validate_rule(restored) == [], "the restored state is itself revertible"

    def test_a_revert_that_lies_about_the_current_state_is_REFUSED(self, tmp_path):
        """Shape is not truth. A proposer built against a stale read would
        declare 'nothing was here' on a live path, and rolling that back would
        DELETE someone else's rule instead of restoring one."""
        first = self._rule(value=["compression"])
        assert lr.apply_rule(first, now=NOW, root=tmp_path)["ok"]

        # (a) claims the path is empty when it is not
        stale = self._rule(value=["reframe"])              # revert_present=False
        out = lr.apply_rule(stale, now=NOW, root=tmp_path)
        assert out["ok"] is False
        assert any("already active" in e for e in out["errors"])

        # (b) claims a previous value that was never there
        wrong = self._rule(value=["reframe"], revert_present=True,
                           revert_value=["second_order"])
        out = lr.apply_rule(wrong, now=NOW, root=tmp_path)
        assert out["ok"] is False
        assert any("does not match the active value" in e for e in out["errors"])

        # the live state is untouched by either refusal
        assert lr.active(tmp_path)[first["path"]]["value"] == ["compression"]

    def test_claiming_a_prior_value_on_an_empty_path_is_REFUSED(self, tmp_path):
        out = lr.apply_rule(self._rule(revert_present=True, revert_value=["x"]),
                            now=NOW, root=tmp_path)
        assert out["ok"] is False
        assert any("nothing is active" in e for e in out["errors"])
        assert lr.active(tmp_path) == {}

    def test_an_invalid_rule_never_reaches_the_store(self, tmp_path, capsys):
        bad = self._rule()
        del bad["revert"]
        assert lr.apply_rule(bad, now=NOW, root=tmp_path)["ok"] is False
        assert lr.active(tmp_path) == {}
        assert "::warning" in capsys.readouterr().out

    def test_version_log_ships_alongside_the_scorecard(self, tmp_path):
        rule = self._rule()
        lr.apply_rule(rule, now=NOW, root=tmp_path)
        lr.rollback(rule["version_id"], now=NOW, root=tmp_path, actor="chris")
        actions = [r["action"] for r in lr.history(tmp_path)]
        assert actions == ["apply", "rollback"]

    def test_consumption_is_DARK_by_default(self, cfg, tmp_path):
        assert lr.enabled(cfg) is False
        lr.apply_rule(self._rule(), now=NOW, root=tmp_path)
        assert lr.active_for("reply_family", account="kelly",
                             root=tmp_path, cfg=cfg) == []

    def test_consumption_works_once_armed(self, cfg, tmp_path):
        armed = json.loads(json.dumps(cfg))
        armed["learning"]["learned_rules"]["enabled"] = True
        lr.apply_rule(self._rule(), now=NOW, root=tmp_path)
        got = lr.active_for("reply_family", account="kelly", root=tmp_path, cfg=armed)
        assert len(got) == 1 and got[0]["value"] == ["missing_variable"]


# ===========================================================================
# GATE: blind-identity eval PRE-REGISTERED, not run, gating nothing
# ===========================================================================
class TestBlindIdentityPrereg:
    DOC = ROOT / "docs" / "blind_identity_eval_prereg.md"

    def test_the_eval_has_not_been_run(self):
        assert bie.PREREG["status"] == "not_run"
        assert bie.GATES_NOTHING is True
        assert bie.PREREG["gates"] == []

    def test_chance_is_twenty_percent_not_fifty(self):
        assert bie.CHANCE_BASELINE == pytest.approx(0.20)
        assert bie.N_PERSONAS == 5

    def test_doc_and_code_agree_on_every_number(self):
        """A prereg that can drift from its own doc is not a prereg."""
        text = self.DOC.read_text(encoding="utf-8")
        assert bie.PREREG["id"] in text
        assert str(bie.PREREG["n_per_persona"]) in text
        assert str(bie.PREREG["n_samples"]) in text
        assert "0.20" in text and "0.80" in text
        assert str(bie.PREREG["holdout"]["seed"]) in text
        for persona in bie.PREREG["personas"]:
            assert persona in text

    def test_the_80_percent_number_gates_nothing_in_the_tree(self):
        """Grep proof, not a promise. If a gate ever branches on this number
        the assertion below is what catches it."""
        hits: list[str] = []
        for path in (ROOT / "engine").rglob("*.py"):
            src = path.read_text(encoding="utf-8", errors="replace")
            if "blind_identity" not in src or path.name == "blind_identity.py":
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if re.search(r"(if|assert|while|and|or)\b.*blind_identity", line):
                    hits.append(f"{path.relative_to(ROOT)}:{i}")
        assert not hits, "nothing may branch on the blind-identity result: " + str(hits)

    def test_holdout_is_deterministic_and_reports_shortfall(self):
        samples = [{"id": f"s{i}", "persona": "kelly", "text": f"post {i} @kelly",
                    "date": "2026-07-01"} for i in range(5)]
        a = bie.build_holdout(samples, n_per_persona=30)
        b = bie.build_holdout(samples, n_per_persona=30)
        assert [i["sample_id"] for i in a["items"]] == [i["sample_id"] for i in b["items"]]
        assert a["shortfall"]["kelly"] == 25
        assert a["complete"] is False

    def test_holdout_never_backfills_from_another_identity(self):
        samples = ([{"id": f"k{i}", "persona": "kelly", "text": f"k{i}",
                     "date": "2026-07-01"} for i in range(10)]
                   + [{"id": f"c{i}", "persona": "cici", "text": f"c{i}",
                       "date": "2026-07-01"} for i in range(10)])
        out = bie.build_holdout(samples, n_per_persona=5)
        per = {}
        for item in out["items"]:
            per[item["truth"]] = per.get(item["truth"], 0) + 1
        assert per == {"kelly": 5, "cici": 5}

    def test_blinding_strips_handles_but_keeps_GENERIC_cashtags(self):
        blinded = bie.blind("@kelly here: $NVDA capex is the tell #macro",
                            persona="kelly")
        assert "@kelly" not in blinded and "#macro" not in blinded
        assert "$NVDA" in blinded, "a generic market cashtag is substance, not a tell"

    def test_blinding_strips_ACCOUNT_SPECIFIC_cashtags(self):
        """'the desk that always posts $FXI' is a byline in cashtag form."""
        blinded = bie.blind("$FXI slipped while $SPX held.", persona="cici")
        assert "$FXI" not in blinded
        assert "$SPX" in blinded

    def test_blinding_strips_franchise_titles_and_signature_emoji(self):
        blinded = bie.blind("Before New York Wakes 🍵 — breadth narrowed.",
                            persona="cici")
        assert "Before New York Wakes" not in blinded
        assert "🍵" not in blinded
        assert "breadth narrowed" in blinded

    def test_the_registered_strip_list_and_the_harness_agree(self):
        """The defect this pair exists to catch: a rule stated in the prereg
        that the harness never implemented."""
        rule = bie.PREREG["holdout"]["blinding"]
        assert "STRIP" in rule and "KEEP" in rule
        assert "$FXI" in bie.PREREG["holdout"]["account_specific_cashtags"]["cici"]
        assert bie.account_cashtags("cici") >= {"FXI", "KWEB"}
        assert bie.account_cashtags("kelly") == set()

    def test_the_amendment_is_recorded_with_its_justification(self):
        """Amending a prereg is only honest before the data exists."""
        amendment = bie.PREREG["amendments"][-1]
        assert amendment["at"] == "2026-07-28"
        assert "NEVER RUN" in amendment["legitimate_because"]
        assert bie.PREREG["status"] == "not_run"

    def test_wilson_lower_bound_never_goes_below_zero(self):
        lo, hi = bie.wilson_interval(0, 5)
        assert lo == 0.0 and 0.0 < hi <= 1.0

    def test_unanswered_samples_leave_the_denominator(self):
        """Scoring a skipped item as wrong punishes a rater for abstaining."""
        holdout = bie.build_holdout(
            [{"id": f"k{i}", "persona": "kelly", "text": f"k{i}"} for i in range(4)],
            n_per_persona=4)
        ids = [i["sample_id"] for i in holdout["items"]]
        result = bie.grade({ids[0]: "kelly", ids[1]: "cici"}, holdout)
        assert result["n_answered"] == 2 and result["n_unanswered"] == 2
        assert result["accuracy"] == 0.5

    def test_verdict_is_not_run_without_responses(self):
        assert bie.verdict({})["status"] == "not_run"

    def test_an_uneven_fleet_does_not_read_as_a_pass(self):
        result = {
            "accuracy": 0.9, "ci95": [0.8, 0.95],
            "per_persona": {
                "kelly": {"n": 30, "above_chance": True},
                "cici": {"n": 30, "above_chance": False},
            },
        }
        out = bie.verdict(result)
        assert out["status"] == "above_chance_but_uneven"
        assert out["identities_at_or_below_chance"] == ["cici"]
        assert out["gates"] == []

    def test_an_UNANSWERED_identity_cannot_license_the_fleet_claim(self):
        """Absence of evidence is not evidence of absence. An identity the
        rater skipped must not drop out of the weakness check."""
        result = {
            "accuracy": 0.9, "ci95": [0.8, 0.95],
            "per_persona": {
                "kelly": {"n": 30, "above_chance": True},
                "cici": {"n": 0, "above_chance": False},
            },
        }
        out = bie.verdict(result)
        assert out["status"] == "unmeasured"
        assert out["identities_below_answer_floor"] == ["cici"]
        assert out["gates"] == []

    def test_a_thinly_answered_identity_also_blocks(self):
        result = {
            "accuracy": 0.9, "ci95": [0.8, 0.95],
            "per_persona": {
                "kelly": {"n": 30, "above_chance": True},
                "cici": {"n": 5, "above_chance": True},
            },
        }
        assert bie.verdict(result)["status"] == "unmeasured"

    def test_per_persona_intervals_run_the_REGISTERED_bonferroni_z(self):
        """The harness must not quietly apply a more lenient test than its own
        pre-registration."""
        assert bie.PREREG["bonferroni_z"] == pytest.approx(2.638, abs=0.001)
        holdout = bie.build_holdout(
            [{"id": f"k{i}", "persona": "kelly", "text": f"post {i}"}
             for i in range(30)], n_per_persona=30)
        ids = [i["sample_id"] for i in holdout["items"]]
        # 24 of 30 correct — comfortably above chance at z=1.96, and the point
        # is that the CORRECTED interval is the one reported.
        responses = {sid: ("kelly" if i < 24 else "cici")
                     for i, sid in enumerate(ids)}
        block = bie.grade(responses, holdout)["per_persona"]["kelly"]
        assert block["z"] == pytest.approx(2.638, abs=0.001)
        assert "ci95_bonferroni" in block
        wide = bie.wilson_interval(24, 30, 2.638)
        narrow = bie.wilson_interval(24, 30, 1.96)
        assert wide[0] < narrow[0], "the corrected interval must be the wider one"
        assert block["ci95_bonferroni"] == list(wide)

    def test_min_answered_floor_is_registered_in_both_doc_and_code(self):
        text = self.DOC.read_text(encoding="utf-8")
        assert str(bie.PREREG["min_answered_per_persona"]) in text
        assert str(bie.PREREG["bonferroni_z"]) in text


# ===========================================================================
# GATE: every threshold is a config key with a documented default (§8)
# ===========================================================================
class TestConfigContract:
    def test_every_labels_default_has_a_config_key(self, cfg):
        live = cfg["learning"]
        for key in lb.DEFAULTS:
            assert key in live, f"learning.{key} must be documented in config"

    def test_every_health_default_has_a_config_key(self, cfg):
        live = cfg["learning"]["health"]
        for key in hm.DEFAULTS:
            assert key in live, f"learning.health.{key} must be documented in config"
        for key in hm.DEFAULTS["network_tripwire"]:
            assert key in live["network_tripwire"]

    def test_every_producer_default_has_a_config_key(self, cfg):
        from engine.marketing import reply_producer as rp  # noqa: PLC0415

        live = cfg["reply_desk"]["producer"]
        for key in rp.DEFAULTS:
            assert key in live, f"reply_desk.producer.{key} must be documented"

    def test_learned_rule_consumption_and_the_producer_both_ship_dark(self, cfg):
        assert cfg["learning"]["learned_rules"]["enabled"] is False
        assert cfg["reply_desk"]["producer"]["enabled"] is False

    def test_config_can_actually_move_a_threshold(self):
        """A documented knob nothing reads is a knob that lies."""
        rows = [_row(subject=f"r{i}") for i in range(5)]
        loose = lb.scorecard(rows, cfg={"learning": {"n_floor": 1}}, now=NOW)
        tight = lb.scorecard(rows, cfg={"learning": {"n_floor": 99}}, now=NOW)
        assert "verdict" not in loose["cells"][0]
        assert tight["cells"][0]["verdict"] == "seeding"


# ===========================================================================
# GATE: the halt is OPERATOR-VISIBLE in admin and manually clearable
# ===========================================================================
class TestAdminPanels:
    """Untested admin panels are how the Outbox shipped blank (#3871). Every
    surface a halt is supposed to be visible on is exercised here."""

    def test_health_panel_renders_on_a_cold_repo(self, tmp_path):
        from admin import marketing as adm

        out = adm.account_health(root=tmp_path)
        assert out["ok"] is True
        assert out["halted"] == []
        assert out["metrics"] == list(hm.METRICS)
        assert "No account is halted" in out["note"]

    def test_health_panel_surfaces_a_halt(self, tmp_path):
        from admin import marketing as adm

        hm.trip("kelly", reason="network_tripwire",
                evidence={"secret": "internal"}, now=NOW, root=tmp_path)
        out = adm.account_health(root=tmp_path)
        assert out["halt_count"] == 1
        row = out["halted"][0]
        assert row["account"] == "kelly" and row["reason"] == "network_tripwire"
        assert "evidence" not in row, "the panel shows the halt, not its raw payload"
        assert "blocked on BOTH rails" in out["note"]

    def test_health_panel_never_trips_or_clears(self, tmp_path):
        from admin import marketing as adm

        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        adm.account_health(root=tmp_path)
        adm.account_health(root=tmp_path)
        assert hm.is_halted("kelly", root=tmp_path) is True
        assert hm.halted_accounts(tmp_path) == ["kelly"]

    def test_health_panel_says_the_80_percent_number_gates_nothing(self, tmp_path):
        from admin import marketing as adm

        bie_block = adm.account_health(root=tmp_path)["blind_identity"]
        assert bie_block["status"] == "not_run"
        assert bie_block["gates_nothing"] is True

    def test_clear_halt_requires_an_actor_and_works(self, tmp_path):
        from admin import marketing as adm

        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        assert adm.clear_halt("kelly", actor="", root=tmp_path,
                              push=False)["ok"] is False
        out = adm.clear_halt("kelly", actor="chris", root=tmp_path, push=False)
        assert out["ok"] is True
        assert hm.is_halted("kelly", root=tmp_path) is False

    def test_clear_halt_is_honest_when_it_did_not_push(self, tmp_path):
        """An unpushed clear is undone by the VPS's next pull, so the return
        must not read as success."""
        from admin import marketing as adm

        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=tmp_path)
        out = adm.clear_halt("kelly", actor="chris", root=tmp_path, push=False)
        assert out["pushed"] is False
        assert "locally" in out["note"].lower()

    def test_clearing_an_unhalted_account_is_refused(self, tmp_path):
        from admin import marketing as adm

        assert adm.clear_halt("kelly", actor="chris", root=tmp_path,
                              push=False)["error"] == "not_halted"

    def test_learning_panel_renders_on_a_cold_repo(self, tmp_path):
        from admin import marketing as adm

        out = adm.learning_scorecard(root=tmp_path)
        assert out["ok"] is True
        assert out["consumers"] == list(lb.CONSUMERS)
        assert out["scorecard"] == {}
        assert "not a failure" in out["note"]

    def test_learning_panel_ships_the_version_log_beside_the_scorecard(self, tmp_path):
        from admin import marketing as adm

        rule = lr.make_rule(kind="timing", path="reply_desk.window",
                            value=12, revert_present=False,
                            evidence={"n": 40}, now=NOW)
        assert lr.apply_rule(rule, now=NOW, root=tmp_path)["ok"]
        lb.record_observation(_row(), root=tmp_path)
        lb.consolidate(now=NOW, root=tmp_path, store=tmp_path / "desk")

        out = adm.learning_scorecard(root=tmp_path)
        assert out["scorecard"]["cells"], "the scorecard renders"
        assert out["rules"]["log"][0]["version_id"] == rule["version_id"]
        assert out["rules"]["enabled"] is False

    def test_rollback_is_reachable_from_the_panel(self, tmp_path):
        from admin import marketing as adm

        first = lr.make_rule(kind="timing", path="reply_desk.window", value=15,
                             revert_present=False, evidence={"n": 40}, now=NOW)
        assert lr.apply_rule(first, now=NOW, root=tmp_path)["ok"]
        second = lr.make_rule(kind="timing", path="reply_desk.window", value=12,
                              revert_present=True, revert_value=15,
                              evidence={"n": 40}, now=NOW)
        assert lr.apply_rule(second, now=NOW, root=tmp_path)["ok"]

        out = adm.rollback_learned_rule(second["version_id"], actor="chris",
                                        root=tmp_path, push=False)
        assert out["ok"] is True
        assert lr.active(tmp_path)[second["path"]]["value"] == 15
        assert out["pushed"] is False
        assert "locally" in out["note"].lower()

    def test_every_panel_and_action_has_a_route(self):
        """A panel with no route is a panel nobody can open (#3871)."""
        src = (ROOT / "admin" / "server.py").read_text(encoding="utf-8")
        for route in ("/api/marketing/health", "/api/marketing/learning",
                      "/api/marketing/health/clear-halt",
                      "/api/marketing/learning/rollback"):
            assert f'path == "{route}"' in src, f"{route} is unrouted"
        for fn in ("account_health", "learning_scorecard", "clear_halt",
                   "rollback_learned_rule"):
            assert f"marketing.{fn}(" in src, f"{fn} is never called by a route"

    def test_the_ui_reaches_both_routes_and_offers_the_clear_button(self):
        app_js = (ROOT / "admin" / "static" / "app.js").read_text(encoding="utf-8")
        assert "RENDER.marketing_health" in app_js
        assert "RENDER.marketing_learning" in app_js
        assert '"/api/marketing/health/clear-halt"' in app_js
        assert '"/api/marketing/learning/rollback"' in app_js
        # ...and both views are in the nav, or nothing can open them.
        assert '["marketing_health", "Desk Health"]' in app_js
        assert '["marketing_learning", "Learning"]' in app_js

    def test_the_new_buttons_use_data_attributes_not_inline_onclick(self):
        """esc() is an HTML escaper; an onclick body is a JS-STRING context.
        An id carrying a quote would break out of the argument."""
        app_js = (ROOT / "admin" / "static" / "app.js").read_text(encoding="utf-8")
        assert 'onclick="mhClearHalt' not in app_js
        assert 'onclick="mlRollback' not in app_js
        assert 'data-clear-halt="' in app_js and 'data-rollback="' in app_js
        assert '[data-clear-halt]' in app_js and '[data-rollback]' in app_js

    def test_there_is_no_route_that_HALTS_an_account(self):
        """A halt is a consequence of measured telemetry, not a button."""
        src = (ROOT / "admin" / "server.py").read_text(encoding="utf-8")
        assert "marketing.trip(" not in src
        assert "/health/halt\"" not in src


# ===========================================================================
# GATE: annotations start the line (house law), and no user-facing scores
# ===========================================================================
class TestHouseLaws:
    MODULES = ("labels.py", "health_monitor.py", "learned_rules.py",
               "reply_producer.py", "blind_identity.py")

    def test_annotations_are_bare_prints_not_logger_calls(self):
        """A prefixing logger makes GitHub silently drop the annotation."""
        offenders: list[str] = []
        for name in self.MODULES:
            src = (ROOT / "engine" / "marketing" / name).read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                if re.search(r"log\.\w+\(\s*f?[\"']::", line):
                    offenders.append(f"{name}:{i}")
        assert not offenders, "annotations must be bare print(..., flush=True): " + str(offenders)

    def test_annotation_prints_carry_flush(self):
        """stdout is block-buffered when piped in CI, so an unflushed
        annotation can be lost even when it starts the line."""
        pattern = re.compile(
            r"print\((?:[^()]|\([^()]*\))*::(?:warning|notice|error)"
            r"(?:[^()]|\([^()]*\))*\)", re.S)
        for name in self.MODULES:
            src = (ROOT / "engine" / "marketing" / name).read_text(encoding="utf-8")
            for block in pattern.findall(src):
                assert "flush=True" in block, f"{name}: {block[:80]!r} is unflushed"

    def test_no_learning_artifact_is_read_by_the_site(self):
        """No score or label is ever user-facing."""
        offenders: list[str] = []
        for path in list((ROOT / "scripts").glob("build_*.py")):
            src = path.read_text(encoding="utf-8", errors="replace")
            if "marketing/learning" in src or "learning_scorecard" in src:
                offenders.append(path.name)
        assert not offenders, "learning artifacts must stay operator-console only: " + str(offenders)
