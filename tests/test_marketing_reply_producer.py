"""XG-W6 reply-desk PRODUCER — the connective tissue XG-W4 left out.

    discovery -> score -> draft -> critics -> enqueue

The load-bearing tests here are the negative ones. It is easy to write a
producer that enqueues; the claims worth pinning are that it CANNOT enqueue
around the critic stamp, that it produces nothing for a halted desk while the
rest of the fleet runs, that it sends nothing at any dial setting, and that it
spends nothing offline.

Stdlib + pyyaml only (marketing-engine CI lane). No network, no LLM.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import health_monitor as hm  # noqa: E402
from engine.marketing import labels as lb  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_export as rx  # noqa: E402
from engine.marketing import reply_producer as rp  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."
GIFT = "IG spreads widened 12.5% this week while capex guidance held."


@pytest.fixture(scope="module")
def base_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture()
def armed_cfg(base_cfg: dict) -> dict:
    """The committed config with ONLY the producer flag flipped on."""
    cfg = json.loads(json.dumps(base_cfg))
    cfg["reply_desk"]["producer"]["enabled"] = True
    return cfg


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """An isolated checkout carrying a valid two-desk author register."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "reply_targets.yml").write_text(
        "accounts:\n"
        "  kelly:\n"
        "    beats: [credit, capex]\n"
        "    authors:\n"
        "      - handle: somequant\n"
        "        tier: relationship\n"
        "  cici:\n"
        "    beats: [asia, china]\n"
        "    authors:\n"
        "      - handle: asiadesk\n"
        "        tier: relationship\n",
        encoding="utf-8")
    return tmp_path


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    return tmp_path / "reply_desk_store"


def _target(*, account: str = "kelly", author: str = "somequant",
            status_id: str = "1900000000000000001", age_min: int = 10,
            text: str = PARENT) -> dict:
    return {
        "kind": "author_post",
        "status_id": status_id,
        "thread_root_id": status_id,
        "url": f"https://x.com/{author}/status/{status_id}",
        "author": author,
        "author_tier": "relationship",
        "beats": ["credit", "capex"],
        "text": text,
        "created_at": (NOW - timedelta(minutes=age_min)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reply_count": 3,
        "like_count": 40,
        "retweet_count": 4,
        "view_count": 900,
        "account": account,
        "mechanism": "credit",
        "subject": "capex",
    }


class _StubProvider:
    """A twitterapi.io stand-in. Records the offline flag and bills nothing."""

    source_tier = "x_reply"
    billed = True

    def __init__(self, targets: list[dict] | None = None) -> None:
        self._targets = targets or []
        self.calls: list[dict] = []

    def fetch(self, *, session_state, offline=False, wire_spend_usd=None,
              accounts=None, now=None):
        self.calls.append({"offline": offline, "accounts": list(accounts or []),
                           "wire_spend_usd": wire_spend_usd})
        if offline:
            return []
        # Mirror the real provider: spend accrues in the session state the
        # caller persists, so a test can prove the counter is threaded through.
        ns = session_state.setdefault("reply_discovery", {})
        month = (now or NOW).strftime("%Y-%m")
        spend = ns.setdefault("spend", {}).setdefault(
            month, {"requests": 0, "items": 0, "usd": 0.0})
        spend["requests"] += 1
        spend["items"] += len(self._targets)
        spend["usd"] = round(spend["usd"] + 0.00015, 6)
        return [t for t in self._targets
                if accounts is None or t.get("account") in accounts]


CICI_GIFT = "Margin balances thinned 8.4% into the close while issuance held."


def _facts(_account: str, _target: dict) -> dict:
    return {
        "facts": [{"id": "f1", "text": GIFT, "salience": 1.0, "numbers": ["12.5%"]}],
        "numbers_whitelist": ["12.5%"],
    }


def _facts_by_account(account: str, _target: dict) -> dict:
    """Distinct own-feed facts per desk, so a same-thread test exercises the
    thread lock rather than the near-dup critic."""
    if account == "cici":
        return {
            "facts": [{"id": "f2", "text": CICI_GIFT, "salience": 1.0,
                       "numbers": ["8.4%"]}],
            "numbers_whitelist": ["8.4%"],
        }
    return _facts(account, _target)


def _run(cfg, repo, store, targets, **over):
    kwargs = dict(cfg=cfg, press_cfg={}, root=repo, store=store, now=NOW,
                  facts_for=_facts, provider=_StubProvider(targets))
    kwargs.update(over)
    return rp.run_producer(**kwargs)


# ===========================================================================
# GATE: the producer's scheduler entry point exists and is wired
# ===========================================================================
class TestSchedulerWiring:
    def test_daemon_accepts_the_reply_lane(self):
        import scripts.marketing_fastlane_daemon as daemon

        src = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
            encoding="utf-8")
        assert '"reply"' in src, "--lane reply must be a real choice"
        assert hasattr(daemon, "_run_reply_tick")
        assert hasattr(daemon, "_log_reply_tick")

    def test_the_lane_dispatches_to_the_producer(self):
        """A choice the dispatcher never reads is a flag that lies."""
        src = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = {getattr(c.func, "id", "") for c in ast.walk(main)
                  if isinstance(c, ast.Call)}
        assert "_run_reply_tick" in called

    def test_reply_tick_calls_run_producer(self):
        src = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_reply_tick")
        assert "run_producer" in ast.dump(fn)

    def test_dry_run_maps_to_offline(self, armed_cfg, repo, store):
        """The dry-run law for a BILLED provider: zero network, zero spend."""
        stub = _StubProvider([_target()])
        out = _run(armed_cfg, repo, store, None, provider=stub, offline=True)
        assert stub.calls[0]["offline"] is True
        assert out["targets"] == 0 and out["enqueued"] == 0


# ===========================================================================
# GATE: dark by default
# ===========================================================================
class TestDarkByDefault:
    def test_committed_config_ships_the_producer_off(self, base_cfg):
        assert base_cfg["reply_desk"]["producer"]["enabled"] is False

    def test_disabled_producer_is_a_clean_no_op(self, base_cfg, repo, store):
        stub = _StubProvider([_target()])
        out = _run(base_cfg, repo, store, None, provider=stub)
        assert out["enabled"] is False
        assert out["enqueued"] == 0
        assert stub.calls == [], "a dark lane must not even reach the provider"


# ===========================================================================
# GATE: the pipeline actually runs end to end
# ===========================================================================
class TestPipeline:
    def test_enqueues_a_screened_draft(self, armed_cfg, repo, store):
        out = _run(armed_cfg, repo, store, [_target()])
        assert out["targets"] == 1
        assert out["eligible"] == 1
        assert out["drafted"] == 1
        assert out["critic_rejected"] == 0
        assert out["enqueued"] == 1
        items = rq.read_items(store)
        assert len(items) == 1
        assert items[0]["account"] == "kelly"
        assert items[0]["provenance"] == "reply_producer"
        assert items[0]["status"] == "queued"

    def test_per_tick_cap_binds(self, armed_cfg, repo, store):
        cfg = json.loads(json.dumps(armed_cfg))
        cfg["reply_desk"]["producer"]["max_drafts_per_account_per_tick"] = 1
        targets = [_target(status_id=f"19000000000000000{i:02d}") for i in range(4)]
        out = _run(cfg, repo, store, targets)
        assert out["enqueued"] == 1

    def test_no_own_feed_fact_is_an_ABSTENTION_not_an_error(self, armed_cfg, repo, store):
        """Law 1: value before activity. An empty gift is a legal answer."""
        out = _run(armed_cfg, repo, store, [_target()],
                   facts_for=lambda a, t: {"facts": [], "numbers_whitelist": []})
        assert out["abstained"] == 1 and out["drafted"] == 0 and out["enqueued"] == 0
        assert rq.read_items(store) == []

    def test_one_conversation_one_owner_still_binds(self, armed_cfg, repo, store):
        """Two desks must never land under the same post.

        The two desks are given DIFFERENT gifts on purpose: with the same gift
        the near-dup critic kills the second draft first, and the test would
        pass while proving nothing about the thread lock.
        """
        same = "1900000000000000042"
        targets = [_target(account="kelly", status_id=same),
                   _target(account="cici", author="asiadesk", status_id=same,
                           text="Mainland equities drifted lower as offshore "
                                "funds stepped back.")]
        targets[1]["mechanism"] = "liquidity"
        targets[1]["subject"] = "the mainland tape"
        out = _run(armed_cfg, repo, store, targets, facts_for=_facts_by_account)
        assert out["enqueued"] == 1
        assert out["critic_rejected"] == 0, "both drafts must reach the queue gate"
        assert any(r.get("reason") == "thread_owned" for r in out["refused"])

    def test_score_features_ride_the_item_so_covariates_survive(self, armed_cfg,
                                                               repo, store):
        """Parent size and post age are observable only AT DRAFT TIME."""
        _run(armed_cfg, repo, store, [_target()])
        item = rq.read_items(store)[0]
        ctx = (item.get("score_features") or {}).get("_context") or {}
        assert ctx.get("engagement") == 47.0
        assert ctx.get("age_min") == pytest.approx(10.0)

    def test_enqueue_banks_a_label_observation_in_the_HOST_spool(self, armed_cfg,
                                                                repo, store):
        _run(armed_cfg, repo, store, [_target()])
        host = lb.host_dir(repo) / "labels.jsonl"
        assert host.exists()
        rows = lb._read_jsonl(host)
        assert rows[0]["surface"] == "reply"
        assert rows[0]["features"]["parent_engagement"] == 47.0
        assert not lb.labels_path(repo).exists(), \
            "an intraday writer must never touch the tracked ledger"


# ===========================================================================
# GATE: validate_critic_stamp is UNTOUCHED and the producer passes through it
# ===========================================================================
class TestCriticStampIsTheGate:
    def test_enqueued_items_carry_a_full_passing_stamp(self, armed_cfg, repo, store):
        _run(armed_cfg, repo, store, [_target()])
        item = rq.read_items(store)[0]
        assert rq.validate_critic_stamp(item) == []
        assert set(item["critics"]["critics_run"]) == set(rc.CRITICS)
        assert item["critics"]["schema"] == rc.STAMP_SCHEMA

    def test_a_producer_that_skipped_the_critics_enqueues_NOTHING(self, armed_cfg,
                                                                 repo, store,
                                                                 monkeypatch):
        """THE STRUCTURAL GUARANTEE. Forge the stamp the producer hands over and
        the STORE refuses it — the safety claim does not depend on this module
        staying correct."""
        monkeypatch.setattr(
            rc, "screen",
            lambda draft, ctx=None, **kw: ({"verdict": "pass", "rejected_by": [],
                                            "reasons": [], "critics": []},
                                           {"schema": rc.STAMP_SCHEMA,
                                            "verdict": "pass", "critics_run": []}))
        out = _run(armed_cfg, repo, store, [_target()])
        assert out["drafted"] == 1
        assert out["enqueued"] == 0
        assert any("critics did not all run" in str(r.get("errors"))
                   for r in out["refused"])
        assert rq.read_items(store) == []

    def test_a_critic_rejection_stops_the_item(self, armed_cfg, repo, store,
                                               monkeypatch):
        monkeypatch.setattr(
            rc, "screen",
            lambda draft, ctx=None, **kw: (
                {"verdict": "reject", "rejected_by": ["dignity"], "reasons": [],
                 "critics": []},
                {"schema": rc.STAMP_SCHEMA, "verdict": "reject",
                 "critics_run": list(rc.CRITICS)}))
        out = _run(armed_cfg, repo, store, [_target()])
        assert out["critic_rejected"] == 1 and out["enqueued"] == 0

    def test_machine_rejections_never_pollute_the_operator_taste_corpus(
            self, armed_cfg, repo, store, monkeypatch):
        """The rejection corpus is what a HUMAN wants this desk to sound like."""
        monkeypatch.setattr(
            rc, "screen",
            lambda draft, ctx=None, **kw: (
                {"verdict": "reject", "rejected_by": ["vocab"], "reasons": [],
                 "critics": []},
                {"schema": rc.STAMP_SCHEMA, "verdict": "reject",
                 "critics_run": list(rc.CRITICS)}))
        _run(armed_cfg, repo, store, [_target()])
        assert rq.read_rejections(store) == []
        rows = lb._read_jsonl(lb.host_dir(repo) / "labels.jsonl")
        assert rows and rows[0]["hook_family"] == "abstained"
        assert rows[0]["weight"] == 0.0

    def test_the_fleet_linkage_critic_actually_has_its_inputs(self, armed_cfg,
                                                              repo, store):
        """`our_handles` is what enforces zero cross-account engagement. A
        producer that omitted it would run a gate with nothing to check."""
        ours = rc.our_handles(armed_cfg)
        assert ours, "desk_network must yield handles for the blocklist critic"
        out = _run(armed_cfg, repo, store,
                   [_target(author=ours[0], status_id="1900000000000000077")])
        assert out["enqueued"] == 0
        assert out["critic_rejected"] == 1


# ===========================================================================
# GATE: halted account produces nothing; the fleet continues
# ===========================================================================
class TestHaltGate:
    def test_halted_desk_produces_nothing_and_the_other_desk_does(self, armed_cfg,
                                                                 repo, store):
        targets = [_target(account="kelly", status_id="1900000000000000010"),
                   _target(account="cici", author="asiadesk",
                           status_id="1900000000000000011")]
        hm.trip("kelly", reason="network_tripwire", evidence={}, now=NOW, root=repo)
        out = _run(armed_cfg, repo, store, targets)
        assert out["halted"] == ["kelly"]
        assert "cici" in out["accounts"] and "kelly" not in out["accounts"]
        accounts = {i["account"] for i in rq.read_items(store)}
        assert accounts == {"cici"}

    def test_a_halted_desk_costs_no_billed_request(self, armed_cfg, repo, store):
        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=repo)
        stub = _StubProvider([_target()])
        _run(armed_cfg, repo, store, None, provider=stub)
        assert stub.calls, "the tick still runs for the live desks"
        assert "kelly" not in stub.calls[0]["accounts"]

    def test_every_desk_halted_is_a_clean_no_op(self, armed_cfg, repo, store):
        for acc in ("kelly", "cici"):
            hm.trip(acc, reason="x", evidence={}, now=NOW, root=repo)
        stub = _StubProvider([_target()])
        out = _run(armed_cfg, repo, store, None, provider=stub)
        assert out["enqueued"] == 0 and stub.calls == []
        assert sorted(out["halted"]) == ["cici", "kelly"]

    def test_halt_announcement_starts_the_line(self, armed_cfg, repo, store, capsys):
        hm.trip("kelly", reason="x", evidence={}, now=NOW, root=repo)
        _run(armed_cfg, repo, store, [_target(account="cici", author="asiadesk")])
        out = capsys.readouterr().out
        assert any(line.startswith("::warning title=reply-producer-halted")
                   for line in out.splitlines())


# ===========================================================================
# GATE: nothing sends — the dial is untouched by this wave
# ===========================================================================
class TestNothingSends:
    def test_output_lands_in_the_M0_queue(self, armed_cfg, repo, store):
        _run(armed_cfg, repo, store, [_target()])
        item = rq.read_items(store)[0]
        assert item["mode"] == "M0"
        assert item["status"] == "queued"

    def test_M0_exports_nothing_even_after_approval(self, armed_cfg, repo, store):
        _run(armed_cfg, repo, store, [_target()])
        iid = rq.read_items(store)[0]["id"]
        assert rq.approve(iid, root=store)
        out = rx.export_approved(cfg=armed_cfg, root=store, repo_root=repo, now=NOW)
        assert out["exported"] == []
        assert iid in out["skipped_mode"]

    def test_the_producer_never_calls_a_send_path(self):
        """Source-pinned: mark_sent / ingest_receipts / claim have no business
        in a producer, and a future edit that reaches for one fails here."""
        src = (ROOT / "engine" / "marketing" / "reply_producer.py").read_text(
            encoding="utf-8")
        for forbidden in ("mark_sent", "ingest_receipts", "claim_for_desktop",
                          "export_approved"):
            assert forbidden not in src, f"a producer must not call {forbidden}"

    def test_the_shippable_mode_set_is_unchanged_by_this_wave(self):
        assert rq.SHIPPABLE_MODES == frozenset({"M0", "M1"})


# ===========================================================================
# GATE: spend rides XG-W4's accounting — no second budget, no second counter
# ===========================================================================
class TestSpend:
    def test_spend_is_persisted_to_host_state_by_run_tick(self, armed_cfg, repo, store):
        from engine.marketing import reply_discovery as rd  # noqa: PLC0415

        out = _run(armed_cfg, repo, store, [_target()])
        assert out["spend"].get("requests") == 1
        persisted = rd.load_state(store)
        month = NOW.strftime("%Y-%m")
        assert persisted["reply_discovery"]["spend"][month]["requests"] == 1

    def test_wire_spend_is_read_and_handed_to_the_lane(self, armed_cfg, repo, store):
        """The shared-bucket stop is inert unless the wire's counter is read."""
        wire = repo / "data" / "marketing" / "press" / "state.json"
        wire.parent.mkdir(parents=True, exist_ok=True)
        month = NOW.strftime("%Y-%m")
        wire.write_text(json.dumps({"providers": {"twitterapiio": {
            "spend": {month: {"usd": 42.0}}}}}), encoding="utf-8")
        stub = _StubProvider([_target()])
        out = _run(armed_cfg, repo, store, None, provider=stub)
        assert out["wire_spend"] == 42.0
        assert stub.calls[0]["wire_spend_usd"] == 42.0

    def test_offline_spends_nothing(self, armed_cfg, repo, store):
        from engine.marketing import reply_discovery as rd  # noqa: PLC0415

        _run(armed_cfg, repo, store, [_target()], offline=True)
        assert rd.load_state(store) == {}

    def test_an_explicit_account_list_still_ROTATES(self):
        """The producer passes the non-halted desks explicitly, and that path
        used to skip the desk rotation entirely — reintroducing XG-W4's
        starvation bug for every tick after a halt existed. With a per-tick
        request cap below the desk count, the tail must eventually be polled."""
        from engine.marketing import reply_discovery as rd  # noqa: PLC0415

        provider = rd.ReplyDiscoveryProvider(
            {"max_requests_per_tick": 1},
            register={"accounts": {
                a: {"authors": [{"handle": f"h_{a}", "tier": "relationship"}]}
                for a in ("alpha", "bravo", "charlie")}},
        )
        polled: list[str] = []
        provider._request = lambda key, ep, params: (  # noqa: SLF001
            polled.append(params.get("userName")) or {"tweets": []})

        state: dict = {}
        import os
        os.environ["TWITTERAPI_IO_KEY"] = "test-key"
        try:
            for _ in range(3):
                provider.fetch(session_state=state,
                               accounts=["alpha", "bravo", "charlie"], now=NOW)
        finally:
            os.environ.pop("TWITTERAPI_IO_KEY", None)

        assert set(polled) == {"h_alpha", "h_bravo", "h_charlie"}, (
            f"a capped tick must rotate across desks; only polled {polled}")

    def test_the_producer_owns_no_second_budget(self):
        """A lane with two budgets has none."""
        src = (ROOT / "engine" / "marketing" / "reply_producer.py").read_text(
            encoding="utf-8")
        for forbidden in ("monthly_usd_cap", "_bill(", "budget_check", "_PRICE_PER_1K"):
            assert forbidden not in src, f"spend accounting stays in reply_discovery ({forbidden})"


# ===========================================================================
# GATE: learned-rule consumption is real but dark
# ===========================================================================
class TestLearnedRuleConsumption:
    def _rule(self):
        from engine.marketing import learned_rules as lr  # noqa: PLC0415

        return lr.make_rule(kind="reply_family", path="reply_desk.families.kelly",
                            value=["compression"], revert_present=False,
                            evidence={"n": 40}, account="kelly", now=NOW)

    def test_disarmed_rules_do_not_steer_the_family(self, armed_cfg, repo, store):
        from engine.marketing import learned_rules as lr  # noqa: PLC0415

        lr.apply_rule(self._rule(), now=NOW, root=repo)
        _run(armed_cfg, repo, store, [_target()])
        assert rq.read_items(store)[0]["family"] == "missing_variable"

    def test_armed_rules_narrow_the_pool(self, armed_cfg, repo, store):
        from engine.marketing import learned_rules as lr  # noqa: PLC0415

        cfg = json.loads(json.dumps(armed_cfg))
        cfg["learning"]["learned_rules"]["enabled"] = True
        lr.apply_rule(self._rule(), now=NOW, root=repo)
        _run(cfg, repo, store, [_target()])
        assert rq.read_items(store)[0]["family"] == "compression"
