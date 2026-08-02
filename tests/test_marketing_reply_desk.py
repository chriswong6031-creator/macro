"""Reply desk (XG-W4) — acceptance-gate suite.

Every test here maps to a line in the charter's §0 XG-W4 gate. The critic tests
are MUTATION-style on purpose: a clean draft must clear every critic, and
each critic must be shown killing its own target defect on a draft that differs
only in that defect. A critic suite that only ever asserts "clean copy passes"
proves nothing about whether the gate is wired.

Stdlib + pyyaml only (marketing-engine CI lane). Nothing here touches the
network, and nothing calls an LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import copywriter  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_discovery as rd  # noqa: E402
from engine.marketing import reply_drafter as rdr  # noqa: E402
from engine.marketing import reply_export as rx  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402
from engine.marketing import reply_score as rs  # noqa: E402
from engine.marketing import sentinel  # noqa: E402

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
THREAD = "1900000000000000001"
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."
#: WARMED 2026-08-01 (the warmth build). The previous text was the same fact
#: with the closing line "Credit is the test." — twenty content units on an
#: employee desk with no human-register marker anywhere in it, which is exactly
#: the instrument-readout shape the `warmth_register` critic now rejects (W1).
#: The fixture was updated rather than the bar: a long cold reply from Kelly is
#: no longer a clean draft, and a "clean draft" fixture that the shipped gate
#: rejects would be testing the old law.
CLEAN_DRAFT = (
    "IG spreads widened 12.5% this week while capex guidance held.\n\n"
    "The price move is the reaction. Credit is the thing that settles it."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def press_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))


@pytest.fixture()
def m1_cfg(cfg: dict) -> dict:
    """A config with kelly dialled to M1 (approved items export).

    Burst pacing is switched OFF here on purpose. Every test taking this fixture
    is about the mode dial, the daily cap, or mirror lifecycle — one subject
    each. Leaving pacing on would make all of them additionally depend on
    whether the module's fixed ``NOW`` happens to fall inside a burst window,
    which is a second unrelated reason to go red and would hide the first.
    Pacing has its own suite: tests/test_marketing_reply_pacing.py.
    """
    out = json.loads(json.dumps(cfg))
    out["reply_desk"]["mode"]["accounts"]["kelly"] = "M1"
    out["reply_desk"].setdefault("pacing", {})["enabled"] = False
    return out


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """An isolated host-state root. Never the repo checkout."""
    return tmp_path / "reply_desk"


@pytest.fixture()
def critic_ctx(cfg: dict) -> dict:
    return {
        "account": "kelly",
        "parent_text": PARENT,
        "parent_author": "somequant",
        "numbers_whitelist": ["12.5%"],
        "corpus": [],
        "theses": [],
        "satire_blocklist": ["HalfwayPost"],
        "cfg": cfg,
    }


def _pass_stamp() -> dict:
    """A stamp from a real full critic pass, not a hand-written literal."""
    return rc.stamp({
        "verdict": "pass",
        "rejected_by": [],
        "critics": [{"critic": name, "verdict": "pass", "reasons": []}
                    for name in rc.CRITICS],
    })


def _item(account: str = "kelly", thread: str = THREAD, draft: str = CLEAN_DRAFT,
          tier: str = "relationship", ttl_min: int = 45, now: datetime = NOW,
          critics: dict | None = -1) -> dict:  # type: ignore[assignment]
    return rq.make_item(
        account=account,
        target_url=f"https://x.com/somequant/status/{thread}",
        parent_author="somequant", parent_excerpt=PARENT, draft=draft,
        tier=tier, score=0.8, score_components={"author_tier": 0.26},
        critics=_pass_stamp() if critics == -1 else critics,
        ttl_min=ttl_min, now=now,
    )


def _advance_to_claimed(item_id: str, store: Path, *, now: datetime = NOW) -> None:
    assert rq.approve(item_id, root=store)
    assert rq.claim(item_id, holder="desk-1", root=store, now=now) is not None


# ===========================================================================
# GATE: the author register ships a schema + loader + validation
# ===========================================================================
class TestAuthorRegister:
    def test_committed_register_is_valid(self):
        reg = rd.load_register(ROOT)
        assert reg, "config/reply_targets.yml must exist and parse"
        assert rd.validate_register(reg) == []

    def test_register_covers_every_live_desk(self, cfg: dict):
        reg = rd.load_register(ROOT)
        live = {
            a["id"] for a in (cfg.get("desk_network") or {}).get("accounts") or []
            if a.get("enabled") and a.get("handle")
        }
        assert live <= set(reg["accounts"]), "every live desk needs a register block"

    def test_seed_entries_are_parked_for_operator_curation(self):
        """The handle list is the operator's call, not a builder's invention."""
        reg = rd.load_register(ROOT)
        for account in reg["accounts"]:
            assert rd.register_for_account(reg, account) == []

    def test_bad_tier_rejects(self):
        errs = rd.validate_register(
            {"accounts": {"kelly": {"authors": [{"handle": "x", "tier": "megacap"}]}}})
        assert any("tier" in e for e in errs)

    def test_leading_at_rejects(self):
        errs = rd.validate_register(
            {"accounts": {"kelly": {"authors": [{"handle": "@x", "tier": "conversion"}]}}})
        assert any("leading '@'" in e for e in errs)

    def test_duplicate_handle_within_a_desk_rejects(self):
        errs = rd.validate_register({"accounts": {"kelly": {"authors": [
            {"handle": "x", "tier": "conversion"},
            {"handle": "X", "tier": "relationship"},
        ]}}})
        assert any("duplicate handle" in e for e in errs)

    def test_one_author_two_desks_rejects(self):
        """A shared author guarantees a same-thread collision later."""
        errs = rd.validate_register({"accounts": {
            "kelly": {"authors": [{"handle": "shared", "tier": "conversion"}]},
            "cici": {"authors": [{"handle": "shared", "tier": "conversion"}]},
        }})
        assert any("one author, one desk" in e for e in errs)


# ===========================================================================
# GATE: discovery runs inside its own sub-budget with its own cursors
# ===========================================================================
class TestDiscoveryBudget:
    def test_sub_cap_is_carved_from_the_shared_cap(self, press_cfg: dict):
        sub = float(press_cfg["reply_discovery"]["monthly_usd_cap"])
        shared = float(press_cfg["spend"]["twitterapiio_monthly_cap_usd"])
        assert 0 < sub < shared, "the reply sub-budget must fit inside the wire's bucket"

    def test_combined_spend_cannot_exceed_the_shared_bucket(self, monkeypatch, capsys):
        """CARVED, not additive. Asserting 0 < 15 < 75 is true of an additive
        budget too — this pins that the combined ceiling is really $75."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": [{"handle": "a", "tier": "relationship"}]}},
        )
        monkeypatch.setattr(provider, "_request",
                            lambda *a, **k: pytest.fail("must not spend past the bucket"))
        month = NOW.strftime("%Y-%m")
        # Reply is under its own $15 sub-cap, but the wire has taken $70 of $75.
        state = {
            "twitterapiio": {"spend": {month: {"usd": 70.0}}},
            rd.STATE_NS: {"spend": {month: {"usd": 5.0}}},
        }
        assert provider.fetch(session_state=state, now=NOW) == []
        assert any(ln.startswith("::warning title=reply-discovery-bucket::")
                   for ln in capsys.readouterr().out.splitlines())

    def test_the_wire_counter_is_read_never_written(self, monkeypatch):
        """Reading the wire's spend must not perturb it, or this lane could
        starve the wire through its own bookkeeping."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "a", "tier": "relationship"}]}}},
        )
        monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": []})
        month = NOW.strftime("%Y-%m")
        state = {"twitterapiio": {"spend": {month: {"usd": 10.0, "requests": 3}}}}
        provider.fetch(session_state=state, now=NOW)
        assert state["twitterapiio"]["spend"][month] == {"usd": 10.0, "requests": 3}
        assert state[rd.STATE_NS]["spend"][month]["usd"] > 0

    def test_wire_spend_reads_the_shared_namespace(self):
        month = NOW.strftime("%Y-%m")
        state = {"twitterapiio": {"spend": {month: {"usd": 12.5}}}}
        assert rd.ReplyDiscoveryProvider.wire_spend(state, now=NOW) == 12.5
        assert rd.ReplyDiscoveryProvider.wire_spend({}, now=NOW) == 0.0

    def test_wire_spend_is_read_from_the_daemons_real_state_file(self, tmp_path):
        """The two lanes keep their counters in DIFFERENT FILES. Reading only
        the reply lane's session dict left the shared stop inert in every real
        invocation, which is how the ceiling became $90 against a $75 bucket."""
        month = NOW.strftime("%Y-%m")
        press = tmp_path / "data" / "marketing" / "press"
        press.mkdir(parents=True)
        (press / "state.json").write_text(json.dumps(
            {"providers": {"twitterapiio": {"spend": {month: {"usd": 61.25}}}}}),
            encoding="utf-8")
        assert rd.load_wire_spend(tmp_path, now=NOW) == 61.25

    def test_wire_spend_is_fail_soft_when_the_daemon_has_never_run(self, tmp_path):
        assert rd.load_wire_spend(tmp_path, now=NOW) == 0.0

    def _seed_wire(self, tmp_path: Path, usd: float) -> None:
        press = tmp_path / "data" / "marketing" / "press"
        press.mkdir(parents=True, exist_ok=True)
        (press / "state.json").write_text(json.dumps(
            {"providers": {"twitterapiio": {"spend": {NOW.strftime("%Y-%m"): {"usd": usd}}}}}),
            encoding="utf-8")

    def _reply_provider(self, monkeypatch, *, fail_on_request: bool):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "a", "tier": "relationship"}]}}})
        if fail_on_request:
            monkeypatch.setattr(provider, "_request",
                                lambda *a, **k: pytest.fail("must not spend past the bucket"))
        else:
            monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": []})
        return provider

    def test_run_tick_stops_when_the_wire_has_taken_the_whole_bucket(
            self, monkeypatch, tmp_path, capsys):
        """End to end through the REAL state file: reply yields to the wire."""
        self._seed_wire(tmp_path, 75.0)
        provider = self._reply_provider(monkeypatch, fail_on_request=True)
        result = rd.run_tick(provider, root=tmp_path / "host", repo_root=tmp_path, now=NOW)
        assert result["count"] == 0
        assert result["wire_spend"] == 75.0
        assert any(ln.startswith("::warning title=reply-discovery-bucket::")
                   for ln in capsys.readouterr().out.splitlines())

    def test_run_tick_still_polls_while_the_bucket_has_room(self, monkeypatch, tmp_path):
        """The stop is a shared-bucket ceiling, not a wire-activity veto — a
        busy wire that is still inside the cap must not halt reply discovery."""
        self._seed_wire(tmp_path, 40.0)
        provider = self._reply_provider(monkeypatch, fail_on_request=False)
        result = rd.run_tick(provider, root=tmp_path / "host", repo_root=tmp_path, now=NOW)
        assert result["wire_spend"] == 40.0
        assert result["spend"]["requests"] == 1, "room in the bucket means keep polling"


class TestDiscoveryStatePersistence:
    """Without persistence the sub-cap resets to zero every process and the
    cursors re-read (and re-bill) every author's whole timeline."""

    def test_run_tick_persists_spend_and_cursors(self, monkeypatch, store):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "someauthor", "tier": "relationship"}]}}},
        )
        monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": [
            {"id": "1900000000000000009", "text": "hi",
             "author": {"userName": "someauthor"}}]})

        first = rd.run_tick(provider, root=store, now=NOW)
        assert first["count"] == 1 and first["persisted"] is True
        assert rd._state_path(store).exists()

        # A brand-new process must see the prior spend AND the prior cursor.
        reloaded = rd.load_state(store)
        assert reloaded[rd.STATE_NS]["spend"][NOW.strftime("%Y-%m")]["usd"] > 0
        assert reloaded[rd.STATE_NS]["cursors"]["author:someauthor"] == "1900000000000000009"
        second = rd.run_tick(provider, root=store, now=NOW)
        assert second["count"] == 0, "the persisted cursor must gate the re-read"

    def test_offline_tick_persists_nothing(self, store):
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        result = rd.run_tick(provider, root=store, offline=True, now=NOW)
        assert result["count"] == 0 and result["persisted"] is False
        assert not rd._state_path(store).exists()

    def test_a_crash_mid_tick_still_persists_the_spend_already_billed(
            self, monkeypatch, store):
        """Bailing without saving discards spend that WAS charged — an
        under-count in the direction that costs money."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "a", "tier": "relationship"},
                {"handle": "b", "tier": "relationship"},
            ]}}})
        calls = {"n": 0}

        def _boom(*a, **k):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("boom mid-tick")
            return {"tweets": [{"id": "1", "author": {"userName": "a"}}]}

        monkeypatch.setattr(provider, "_request", _boom)
        with pytest.raises(RuntimeError):
            rd.run_tick(provider, root=store, now=NOW)

        persisted = rd.load_state(store)
        billed = persisted[rd.STATE_NS]["spend"][NOW.strftime("%Y-%m")]
        assert billed["requests"] >= 1, "billed requests must survive the crash"


class TestDiscoveryFairness:
    """A fixed order plus a per-tick request cap starves the tail forever."""

    def _provider(self, monkeypatch, accounts, cap):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        register = {"accounts": {
            a: {"authors": [{"handle": f"{a}{i}", "tier": "conversion"} for i in range(3)]}
            for a in accounts}}
        provider = rd.ReplyDiscoveryProvider(
            {"max_requests_per_tick": cap}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register=register)
        seen: list[str] = []

        def _fake(api_key, endpoint, params):
            seen.append(params.get("userName"))
            return {"tweets": []}

        monkeypatch.setattr(provider, "_request", _fake)
        return provider, seen

    def test_every_desk_is_reached_across_ticks(self, monkeypatch):
        desks = ["cici", "flagship", "founder", "kelly", "meagan", "sophia"]
        provider, seen = self._provider(monkeypatch, desks, cap=12)
        state: dict = {}
        for _ in range(6):
            provider.fetch(session_state=state, now=NOW)
        polled = {h[:-1] for h in seen}
        assert set(desks) <= polled, f"starved desks: {set(desks) - polled}"

    def test_truncation_is_announced(self, monkeypatch, capsys):
        provider, _ = self._provider(monkeypatch, ["a", "b", "c"], cap=2)
        provider.fetch(session_state={}, now=NOW)
        assert any(ln.startswith("::warning title=reply-discovery-tick-cap::")
                   for ln in capsys.readouterr().out.splitlines())

    def test_the_cursor_advances_by_desks_covered_not_by_one(self, monkeypatch):
        """m5 — advancing by one re-polls the same head every tick whenever a
        tick covers several desks, so the tail still starves, just slower."""
        provider, seen = self._provider(monkeypatch, ["a", "b", "c", "d"], cap=6)
        state: dict = {}
        provider.fetch(session_state=state, now=NOW)   # covers a, b (3 authors each)
        first = {h[0] for h in seen}
        assert state[rd.STATE_NS]["rotation"] == len(first) % 4

        seen.clear()
        provider.fetch(session_state=state, now=NOW)
        second = {h[0] for h in seen}
        assert not (first & second), f"tick 2 re-polled {first & second}"


class TestUnknownResponseShapeIsAnnounced:
    """m4 — an unparseable envelope bills at the floor and counts ZERO items,
    which is how a renamed response key becomes a silent under-read of the very
    counter this lane's budget depends on."""

    def test_an_unrecognised_shape_warns(self, monkeypatch, capsys):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "a", "tier": "relationship"}]}}})
        monkeypatch.setattr(provider, "_request",
                            lambda *a, **k: {"posts": [{"id": "1"}], "next": None})
        provider.fetch(session_state={}, now=NOW)
        assert any(ln.startswith("::warning title=reply-discovery-shape::")
                   for ln in capsys.readouterr().out.splitlines())

    def test_a_genuinely_empty_page_does_not_warn(self, monkeypatch, capsys):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "a", "tier": "relationship"}]}}})
        monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": []})
        provider.fetch(session_state={}, now=NOW)
        assert not any("reply-discovery-shape" in ln
                       for ln in capsys.readouterr().out.splitlines())

    def test_poll_outcomes_honours_the_shared_bucket_stop(self, monkeypatch, capsys):
        """M5 — telemetry polling must not reopen the $90-against-$75 shape."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        monkeypatch.setattr(provider, "_request",
                            lambda *a, **k: pytest.fail("must not spend past the bucket"))
        month = NOW.strftime("%Y-%m")
        state = {"twitterapiio": {"spend": {month: {"usd": 75.0}}}}
        assert provider.poll_outcomes(session_state=state, status_ids=["1"], now=NOW) == []
        assert any(ln.startswith("::warning title=reply-discovery-bucket::")
                   for ln in capsys.readouterr().out.splitlines())


class TestSilencedVersusSpentCap:
    """m3 — they read the same to a caller checking ok=False, but need opposite
    receipt handling: a spent cap clears at midnight, a silenced account never
    does on its own."""

    def test_a_silenced_account_reports_account_silenced(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": None}
        gate = rq.may_send("kelly", cfg=cfg, root=store, now=NOW)
        assert gate["ok"] is False and gate["reason"] == "account_silenced"

    def test_m0_reports_draft_only(self, store, cfg):
        gate = rq.may_send("kelly", cfg=cfg, root=store, now=NOW)
        assert gate["reason"] == "mode_m0_draft_only"

    def test_a_spent_cap_reports_reply_cap_daily(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=cfg, now=NOW)
        gate = rq.may_send("kelly", cfg=cfg, root=store, now=NOW)
        assert gate["reason"] == "reply_cap_daily"

    def test_a_silenced_accounts_receipt_is_parked_not_retained(self, store, m1_cfg):
        """Retaining it would warn on every sweep forever with nothing an
        operator could do about it."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": None}
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        path = rx.receipts_dir(store) / f"{item['id']}.json"
        path.write_text(json.dumps({"id": item["id"], "url": "u", "screenshot": "s"}),
                        encoding="utf-8")
        result = rx.ingest_receipts(cfg=cfg, root=store, now=NOW)
        assert result["refused"][0]["reason"] == "account_silenced"
        assert path.with_suffix(".unresolved").exists()
        assert rx.ingest_receipts(cfg=cfg, root=store, now=NOW)["refused"] == []

    def test_sub_cap_exhaustion_stops_reply_polling(self, monkeypatch, capsys):
        """GATE fixture, half 1: at its own sub-cap, reply discovery stops."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "someauthor", "tier": "relationship"}]}}},
        )
        calls: list[str] = []
        monkeypatch.setattr(provider, "_request",
                            lambda *a, **k: calls.append("hit") or {"tweets": []})

        state = {rd.STATE_NS: {"spend": {NOW.strftime("%Y-%m"): {"usd": 15.0, "requests": 1}}}}
        out = provider.fetch(session_state=state, now=NOW)

        assert out == []
        assert calls == [], "no billed request may be made at the sub-cap"
        line = capsys.readouterr().out
        assert line.startswith("::warning title=reply-discovery-subcap::"), line

    def test_wire_polling_is_unaffected_by_an_exhausted_reply_lane(self, monkeypatch):
        """GATE fixture, half 2: the Trump wire keeps polling regardless.

        The guarantee is structural, not incidental: reply spend increments a
        counter the wire's cap check never reads, so an exhausted reply lane is
        invisible to the wire.
        """
        from engine.marketing import press_providers as pp

        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        wire = pp.TwitterApiIoProvider(
            {"handles": [{"handle": "DeItaone", "tier": "fast",
                          "corroboration_class": "hearsay"}]},
            spend_cap_usd=75.0,
        )
        wire_calls: list[str] = []
        monkeypatch.setattr(wire, "_request",
                            lambda key, handle: wire_calls.append(handle) or {"tweets": []})

        # One shared session_state carrying an EXHAUSTED reply bucket. Seed
        # both the current and next month so a rollover between these two lines
        # cannot turn a real assertion into a KeyError.
        now = datetime.now(tz=timezone.utc)
        months = {now.strftime("%Y-%m"), (now + timedelta(days=2)).strftime("%Y-%m")}
        shared_state: dict = {rd.STATE_NS: {"spend": {m: {"usd": 15.0} for m in months}}}
        wire.fetch(root=ROOT, session_state=shared_state, offline=False)

        assert wire_calls == ["DeItaone"], "reply exhaustion must not stop the wire"
        wire_spend = shared_state["twitterapiio"]["spend"]
        assert any(v["usd"] > 0 for v in wire_spend.values())
        # And the two counters never merged: reply spend is untouched by a wire poll.
        assert all(v["usd"] == 15.0 for v in shared_state[rd.STATE_NS]["spend"].values())

    def test_reply_lane_yields_inside_the_shared_bucket(self):
        """Reply yields to the wire; the wire never yields to reply."""
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        ok, reason = provider.budget_check({"usd": 5.0}, wire_spend_usd=70.0)
        assert (ok, reason) == (False, "shared_bucket_cap")
        ok, reason = provider.budget_check({"usd": 5.0}, wire_spend_usd=10.0)
        assert ok and reason == ""

    def test_sub_cap_larger_than_shared_cap_is_clamped(self, capsys):
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=900.0, global_cap_usd=75.0)
        assert provider.sub_cap_usd == 75.0
        assert capsys.readouterr().out.startswith("::warning title=reply-discovery-subcap::")

    def test_cursor_namespace_is_not_the_wires(self, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "someauthor", "tier": "relationship"}]}}},
        )
        monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": [
            {"id": "1900000000000000009", "text": "hi",
             "author": {"userName": "someauthor"}}]})
        state: dict = {}
        provider.fetch(session_state=state, now=NOW)
        assert rd.STATE_NS in state
        assert "twitterapiio" not in state, "reply cursors must not land in the wire's namespace"
        assert state[rd.STATE_NS]["cursors"]["author:someauthor"] == "1900000000000000009"

    def test_since_id_cursor_gates_already_seen_posts(self, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {}, sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "someauthor", "tier": "relationship"}]}}},
        )
        monkeypatch.setattr(provider, "_request", lambda *a, **k: {"tweets": [
            {"id": "1900000000000000005", "text": "old", "author": {"userName": "someauthor"}}]})
        state = {rd.STATE_NS: {"cursors": {"author:someauthor": "1900000000000000005"}}}
        assert provider.fetch(session_state=state, now=NOW) == []

    def test_offline_makes_no_request_and_no_spend(self, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        monkeypatch.setattr(provider, "_request",
                            lambda *a, **k: pytest.fail("offline must not touch the network"))
        state: dict = {}
        assert provider.fetch(session_state=state, offline=True) == []
        assert state == {}

    def test_missing_key_skips_cleanly(self, monkeypatch):
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        assert provider.fetch(session_state={}) == []

    def test_include_replies_is_a_caller_decision_not_a_constant(self, monkeypatch):
        """The wire's provider hardcodes includeReplies=false; this one must not."""
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        provider = rd.ReplyDiscoveryProvider(
            {"include_replies_for_tiers": ["relationship"]},
            sub_cap_usd=15.0, global_cap_usd=75.0,
            register={"accounts": {"kelly": {"authors": [
                {"handle": "rel", "tier": "relationship"},
                {"handle": "brk", "tier": "breakout"},
            ]}}},
        )
        seen: list[tuple[str, str]] = []

        def _fake(api_key, endpoint, params):
            seen.append((params.get("userName"), params.get("includeReplies")))
            return {"tweets": []}

        monkeypatch.setattr(provider, "_request", _fake)
        provider.fetch(session_state={}, now=NOW)
        assert ("rel", "true") in seen
        assert ("brk", "false") in seen


class TestEndpointShapeAwareCostCounter:
    """The wire's `_count_tweets` reads only the `tweets` key, so a mentions or
    thread-replies payload bills as zero. This counter must see every shape."""

    @pytest.mark.parametrize("payload,expected", [
        ({"tweets": [1, 2, 3]}, 3),
        ({"replies": [1, 2]}, 2),
        ({"mentions": [1]}, 1),
        ({"results": [1, 2, 3, 4, 5]}, 5),
        ({"data": {"tweets": [1, 2, 3, 4]}}, 4),
        ([1, 2, 3, 4, 5, 6], 6),
        ({"unrecognised": 1}, 0),
        (None, 0),
        ("not json", 0),
    ])
    def test_counts_every_response_shape(self, payload, expected):
        assert rd.count_items(payload) == expected

    def test_wire_counter_undercounts_the_shapes_this_lane_needs(self):
        """Pins WHY this lane needs its own counter (regression guard)."""
        from engine.marketing.press_providers import _count_tweets

        assert _count_tweets({"replies": [1, 2, 3]}) == 0
        assert rd.count_items({"replies": [1, 2, 3]}) == 3

    def test_billing_uses_the_shape_aware_count(self):
        provider = rd.ReplyDiscoveryProvider({}, sub_cap_usd=15.0, global_cap_usd=75.0)
        spend = {"requests": 0, "items": 0, "usd": 0.0}
        provider._bill(spend, rd.count_items({"mentions": list(range(1000))}))
        assert spend["items"] == 1000
        assert spend["usd"] == pytest.approx(0.15)


# ===========================================================================
# GATE: deterministic scorer, LLM never scores, _components persisted
# ===========================================================================
class TestOpportunityScorer:
    def _target(self, **over) -> dict:
        base = {
            "kind": "author_post", "author": "somequant", "author_tier": "relationship",
            "status_id": THREAD, "text": PARENT,
            "created_at": (NOW - timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reply_count": 4, "like_count": 60, "retweet_count": 8,
        }
        base.update(over)
        return base

    def test_components_are_persisted_and_inspectable(self, cfg):
        res = rs.score_target(self._target(), persona_beats=["credit", "spreads"],
                              cfg=cfg, now=NOW)
        assert set(res["components"]) == set(rs.DEFAULT_WEIGHTS)
        assert res["score"] == pytest.approx(sum(res["components"].values())
                                             / sum(rs.DEFAULT_WEIGHTS.values()))

    def test_scoring_is_deterministic(self, cfg):
        a = rs.score_target(self._target(), persona_beats=["credit"], cfg=cfg, now=NOW)
        b = rs.score_target(self._target(), persona_beats=["credit"], cfg=cfg, now=NOW)
        assert a == b

    def test_inside_the_window_beats_a_cold_thread(self, cfg):
        hot = rs.score_target(self._target(), cfg=cfg, now=NOW)
        cold = rs.score_target(
            self._target(created_at=(NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")),
            cfg=cfg, now=NOW)
        assert hot["score"] > cold["score"]
        assert cold["components"]["age_fit"] == 0.0

    def test_saturated_thread_scores_below_an_open_one(self, cfg):
        open_thread = rs.score_target(self._target(reply_count=2), cfg=cfg, now=NOW)
        saturated = rs.score_target(self._target(reply_count=200), cfg=cfg, now=NOW)
        assert saturated["score"] < open_thread["score"]

    def test_relationship_outranks_breakout(self, cfg):
        rel = rs.score_target(self._target(author_tier="relationship"), cfg=cfg, now=NOW)
        brk = rs.score_target(self._target(author_tier="breakout"), cfg=cfg, now=NOW)
        assert rel["score"] > brk["score"], "conversion/relationship outweigh vanity reach"

    def test_absent_relationship_store_is_printed_not_hidden(self, cfg):
        res = rs.score_target(self._target(), cfg=cfg, now=NOW)
        assert res["features"]["_context"]["relationship_source"] == "absent"
        assert res["components"]["relationship_stage"] == 0.0

    def test_weights_are_reweightable_from_config(self, cfg):
        """Charter §8: no tier weight is load-bearing until telemetry ranks it."""
        tweaked = json.loads(json.dumps(cfg))
        tweaked["reply_desk"]["score_weights"] = {
            **{k: 0.0 for k in rs.DEFAULT_WEIGHTS}, "author_tier": 1.0}
        res = rs.score_target(self._target(), cfg=tweaked, now=NOW)
        assert res["score"] == pytest.approx(rs.DEFAULT_TIER_PRIOR["relationship"])

    def test_a_partial_weight_override_keeps_the_other_defaults(self, cfg):
        tweaked = json.loads(json.dumps(cfg))
        tweaked["reply_desk"]["score_weights"] = {"author_tier": 1.0}
        res = rs.score_target(self._target(), cfg=tweaked, now=NOW)
        assert set(res["components"]) == set(rs.DEFAULT_WEIGHTS)

    def test_rank_orders_best_first(self, cfg):
        targets = [self._target(status_id="2", author_tier="breakout"),
                   self._target(status_id="1", author_tier="relationship")]
        ranked = rs.rank(targets, cfg=cfg, now=NOW)
        assert ranked[0]["status_id"] == "1"

    def test_module_imports_no_model_client(self):
        """LLM-never-scores, checked against the AST rather than the prose.

        The docstring legitimately discusses the law, so a substring grep would
        match its own explanation. Imports and call targets are what matter.
        """
        import ast

        tree = ast.parse((ROOT / "engine" / "marketing" / "reply_score.py")
                         .read_text(encoding="utf-8"))
        tells = ("llm", "anthropic", "openai", "claude", "completion")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(t in alias.name.lower() for t in tells), alias.name
            elif isinstance(node, ast.ImportFrom):
                assert not any(t in (node.module or "").lower() for t in tells), node.module
            elif isinstance(node, ast.Call):
                target = getattr(node.func, "attr", None) or getattr(node.func, "id", "")
                assert not any(t in str(target).lower() for t in tells), target


# ===========================================================================
# GATE: drafter — families not paraphrases, shared voice guard
# ===========================================================================
FACTS = {
    "facts": [{"id": "f1", "salience": 0.9, "numbers": ["12.5%"],
               "text": "IG spreads widened 12.5% this week while capex guidance held."}],
    "numbers_whitelist": ["12.5%"],
}


class TestReplyDrafter:
    def test_register_matches_the_constitution_family_count(self):
        assert len(rdr.FAMILIES) == 14, "constitution §9.4 lists 14 reply families"
        for spec in rdr.FAMILIES.values():
            assert spec["move"] and spec["trigger"]

    def test_alternates_are_different_families_not_paraphrases(self, cfg):
        out = rdr.draft_reply(account="kelly", target={"subject": "capex", "mechanism": "credit"},
                              facts=FACTS, recent_families=[], cfg=cfg, n_alts=2)
        families = [out["family"], *out["alt_families"]]
        assert len(set(families)) == 3
        texts = [out["draft"], *out["alt_drafts"]]
        assert len(set(texts)) == 3
        from engine.marketing.outbox import token_jaccard
        for other in out["alt_drafts"]:
            assert token_jaccard(out["draft"], other) < 0.9

    def test_rotation_is_least_recently_used(self):
        fams = rdr.family_ids()
        assert rdr.rotate_family([]) == fams[0]
        assert rdr.rotate_family([fams[0]]) == fams[1]
        # A family used long ago outranks one used recently.
        assert rdr.rotate_family(fams[:-1], allowed=[fams[0], fams[1]]) == fams[0]

    def test_gift_grip_doorway_present(self, cfg):
        """One gift, one grip, one doorway (constitution §9.3).

        REWRITTEN 2026-08-01 (the tail build). This used to assert the literal
        words "reaction" and "test", which were the two halves of the ONE welded
        doorway sentence `missing_variable` closed on for every desk and every
        thread. Asserting a specific sentence is asserting the defect: the law is
        that a doorway is present and comes from THIS desk's pool for THIS
        family, not that it is any particular line.
        """
        out = rdr.draft_reply(account="kelly", target={"subject": "capex", "mechanism": "credit"},
                              facts=FACTS, family="missing_variable", cfg=cfg)
        assert "12.5%" in out["draft"]            # gift, from own-feed facts
        assert out["tail"] in rdr.tails_for("kelly", "missing_variable")
        doorway = rdr.render_tail(out["tail"], {"subject": "capex",
                                                "mechanism": "credit"})
        assert doorway and doorway in out["draft"]

    def test_abstains_with_no_own_feed_fact(self, cfg):
        out = rdr.draft_reply(account="kelly", target={}, facts={"facts": []}, cfg=cfg)
        assert out["draft"] == ""
        assert out["components"]["abstained"]

    def test_never_emits_a_dash_tell(self, cfg):
        out = rdr.draft_reply(account="kelly", target={"subject": "capex"},
                              facts={"facts": [{"text": "Spreads widened 12.5% — sharply.",
                                                "salience": 1.0}],
                                     "numbers_whitelist": ["12.5%"]}, cfg=cfg)
        assert "—" not in out["draft"] and "–" not in out["draft"]
        assert copywriter.banned_language(out["draft"]) == []

    def test_chart_families_are_unavailable_without_a_chart(self, cfg):
        out = rdr.draft_reply(account="kelly", target={}, facts=FACTS, cfg=cfg, n_alts=13)
        assert "original_chart" not in [out["family"], *out["alt_families"]]

    def test_chart_reference_carries_an_as_of_stamp(self, tmp_path, cfg):
        """Charts are EOD-only; a nightly bar may never read as live."""
        media = tmp_path / "data" / "marketing" / "outbox" / "media" / "2026-07-28"
        media.mkdir(parents=True)
        (media / "reply-nvda.png").write_bytes(b"png")
        chart = rdr.attach_chart("2026-07-28", "reply-nvda", root=tmp_path)
        assert chart["local_path"].endswith("reply-nvda.png")
        assert chart["as_of_stamp"] == "chart as of 2026-07-28 close"
        assert "local_path" in chart and "public_url" in chart  # charter §5 schema
        out = rdr.draft_reply(account="kelly", target={}, facts=FACTS,
                              family="original_chart", chart=chart, cfg=cfg)
        assert "chart as of 2026-07-28 close" in out["draft"]

    def test_attach_chart_returns_none_when_absent(self, tmp_path):
        assert rdr.attach_chart("2026-07-28", "nope", root=tmp_path) is None


class TestSharedVocabGuardIsCalledNotForked:
    """GATE: the shared copywriter banned-vocab guard runs on every draft path.

    Charter §2 amendment 12 exists because `check_validated_claims.py` is a
    source grep and cannot see runtime-generated copy. The proof that the guard
    is CALLED and not re-implemented is object identity.
    """

    def test_critics_use_the_copywriter_guard_object_itself(self):
        assert rc.banned_language is copywriter.banned_language

    def test_critics_use_the_copywriter_number_tokenizer(self):
        assert rc._extract_number_tokens is copywriter._extract_number_tokens
        assert rc._SHARED_NUMBER_RE is copywriter._NUMBER_RE

    @pytest.mark.parametrize("sample", [
        "spreads widened 12.5% to 226.50, a 3x move on 1000 units",
        "a 3x move",
        "1000 units and 12.5%",
    ])
    def test_no_shared_token_is_lost_except_to_a_wider_reading(self, sample):
        """The merge may only DROP a shared token when a wider span contains it.

        The earlier form asserted a plain subset on a fixture where the extra
        regex contributed nothing, so it degenerated to `X <= X` and could not
        fail for any content of _EXTRA_NUMBER_RE.
        """
        shared = set(copywriter._extract_number_tokens(sample))
        merged = rc.number_tokens(sample)
        for tok in shared - set(merged):
            assert any(tok in wider and tok != wider for wider in merged), (
                f"{tok!r} vanished with no wider token containing it: {merged}")

    def test_a_dropped_shared_token_is_always_covered_by_a_wider_one(self):
        sample = "Issuance of 3,500 units cleared."
        merged = rc.number_tokens(sample)
        assert "500" not in merged and "3,500" in merged

    def test_critics_own_no_banned_list_of_their_own(self):
        for forked in ("_BANNED_VOCAB", "_BANNED_SUBSTRINGS", "_BANNED_CHEESE_WORDS"):
            assert not hasattr(rc, forked), f"{forked} must live in copywriter, not be forked"

    def test_validated_word_law_binds_the_reply_path(self, critic_ctx):
        verdict = rc.run_critics("Our validated signal says spreads widen 12.5%.", critic_ctx)
        assert verdict["verdict"] == "reject"
        assert "vocab" in verdict["rejected_by"]
        assert any("validated" in r for r in verdict["reasons"])

    def test_a_new_upstream_ban_binds_immediately(self, monkeypatch, critic_ctx):
        """A ban added to copywriter must reach this lane with no edit here."""
        monkeypatch.setattr(rc, "banned_language",
                            lambda text: ["banned vocab: 'brandnewban'"] if "spreads" in text else [])
        assert rc.vocab(CLEAN_DRAFT, critic_ctx)["verdict"] == "reject"

    def test_dial_is_consulted_with_kind_reply(self, monkeypatch, critic_ctx):
        captured: dict = {}

        def _fake_violations(headline, body, **kw):
            captured.update(kw)
            return []

        from engine.marketing import expression_dial as dial
        monkeypatch.setattr(dial, "violations", _fake_violations)
        rc.vocab(CLEAN_DRAFT, critic_ctx)
        assert captured["kind"] == "reply"
        assert captured["account"] == "kelly"

    def test_dial_profiles_carry_the_reply_level(self):
        from engine.marketing import expression_dial as dial
        assert dial.PROFILES["employee"]["reply"] == 2
        assert dial.PROFILES["flagship"]["reply"] == 1

    def test_which_accounts_the_register_half_of_the_vocab_critic_binds_for(self):
        """Documents a PRE-EXISTING gap rather than implying it is closed.

        `expression_dial.violations` returns [] for any account with no codex,
        and `flagship`'s spec carries a prose-only voice_codex that the loader
        rejects — so the register half of the vocab critic is inert there. The
        word law still binds flagship via copywriter.banned_language (asserted
        below). Closing the flagship codex is XG-W1/W3 spec territory, not this
        wave's; this test fails loudly if that changes so the note gets updated.
        """
        from engine.marketing import expression_dial as dial

        codexed = set(dial.codex_index(ROOT))
        assert {"kelly", "cici", "meagan", "sophia"} <= codexed
        assert "flagship" not in codexed, (
            "flagship gained a codex — the vocab critic's register half now "
            "binds there; update this note")
        # The shared word law is account-independent, so flagship is not unguarded.
        assert rc.vocab("Our validated read.", {"account": "flagship"})["verdict"] == "reject"

    def test_a_dial_failure_holds_the_draft_rather_than_passing_it(self, monkeypatch, critic_ctx):
        from engine.marketing import expression_dial as dial
        monkeypatch.setattr(dial, "violations",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert rc.vocab(CLEAN_DRAFT, critic_ctx)["verdict"] == "reject"


# ===========================================================================
# GATE: every draft passes ALL critics; each critic rejects its own defect
# ===========================================================================
class TestCriticsCleanDraft:
    def test_a_clean_draft_clears_every_critic(self, critic_ctx):
        verdict = rc.run_critics(CLEAN_DRAFT, critic_ctx)
        assert verdict["verdict"] == "pass", verdict["reasons"]
        assert {c["critic"] for c in verdict["critics"]} == set(rc.CRITICS)

    def test_every_drafted_family_clears_every_critic(self, cfg, critic_ctx):
        """The generator and the gate must agree, or the desk drafts nothing.

        THE TARGET CARRIES ITS PARENT TEXT, which it did not before the warmth
        build and which every production target always does. The warmth register
        is SHAPE-CONDITIONED: with no parent text there is no parent shape, so
        no warmth move is admissible, so every family composes the plain
        template — and a plain template over twelve content units on an employee
        desk is precisely what `warmth_register` now rejects. Drafting against a
        textless target was testing a state the discovery lane cannot produce.
        """
        out = rdr.draft_reply(
            account="kelly",
            target={"subject": "capex", "mechanism": "credit",
                    "text": PARENT, "author": "somequant"},
            facts=FACTS, cfg=cfg, n_alts=13)
        assert out["warmth"], "an employee desk on a classifiable parent must be warmed"
        for text in [out["draft"], *out["alt_drafts"]]:
            verdict = rc.run_critics(text, critic_ctx)
            assert verdict["verdict"] == "pass", (text, verdict["reasons"])


class TestCriticMutations:
    """One mutation per critic. Each draft differs from CLEAN_DRAFT only in the
    defect its critic exists to catch."""

    def test_informational_surplus_rejects_a_restatement(self, critic_ctx):
        verdict = rc.run_critics(PARENT, critic_ctx)
        assert "informational_surplus" in verdict["rejected_by"]

    def test_informational_surplus_rejects_referents_already_in_the_parent(self, critic_ctx):
        ctx = {**critic_ctx, "parent_text": "Credit spreads are widening fast.",
               "numbers_whitelist": []}
        verdict = rc.informational_surplus("Worth noting the credit spreads here.", ctx)
        assert verdict["verdict"] == "reject"

    def test_corpus_near_dup_rejects_a_repeat_of_our_own_reply(self, critic_ctx):
        ctx = {**critic_ctx, "corpus": [{"account": "kelly", "draft": CLEAN_DRAFT}]}
        assert "corpus_near_dup" in rc.run_critics(CLEAN_DRAFT, ctx)["rejected_by"]

    def test_corpus_near_dup_catches_a_sibling_desk(self, critic_ctx):
        """Cross-portfolio: text-similarity clustering is a fleet-linkage tell."""
        ctx = {**critic_ctx, "corpus": [{"account": "cici", "draft": CLEAN_DRAFT}]}
        verdict = rc.corpus_near_dup(CLEAN_DRAFT, ctx)
        assert verdict["verdict"] == "reject"
        assert "cici" in verdict["reasons"][0]

    def test_blocklist_rejects_a_satire_author(self, critic_ctx):
        ctx = {**critic_ctx, "parent_author": "HalfwayPost"}
        assert "blocklist" in rc.run_critics(CLEAN_DRAFT, ctx)["rejected_by"]

    def test_blocklist_reuses_the_press_satire_list(self, press_cfg, critic_ctx):
        listed = (press_cfg.get("satire_blocklist") or [])[0]
        ctx = {**critic_ctx, "parent_author": listed, "satire_blocklist": press_cfg["satire_blocklist"]}
        assert rc.blocklist(CLEAN_DRAFT, ctx)["verdict"] == "reject"

    def test_blocklist_rejects_a_sensitive_event_thread(self, critic_ctx):
        ctx = {**critic_ctx, "parent_text": "Awful news, the death toll is climbing."}
        assert "blocklist" in rc.run_critics(CLEAN_DRAFT, ctx)["rejected_by"]

    def test_position_consistency_rejects_a_silent_contradiction(self, critic_ctx):
        ctx = {**critic_ctx, "theses": [
            {"subject": "credit spreads", "direction": "widen", "status": "open"}]}
        draft = "Credit spreads narrow from here. Levels held at 12.5%."
        assert "position_consistency" in rc.run_critics(draft, ctx)["rejected_by"]

    def test_position_consistency_allows_an_explained_change(self, critic_ctx):
        ctx = {**critic_ctx, "theses": [
            {"subject": "credit spreads", "direction": "widen", "status": "open"}]}
        draft = ("I was wrong on this one. Credit spreads narrow from here, "
                 "and the 12.5% move is the reason.")
        assert rc.position_consistency(draft, ctx)["verdict"] == "pass"

    def test_position_consistency_ignores_a_closed_thesis(self, critic_ctx):
        ctx = {**critic_ctx, "theses": [
            {"subject": "credit spreads", "direction": "widen", "status": "closed"}]}
        assert rc.position_consistency("Credit spreads narrow from here.", ctx)["verdict"] == "pass"

    def test_persona_label_rejects_judgment_adjectives_alone(self, critic_ctx):
        draft = "Honestly this is fascinating and deeply important. Bold, and very telling."
        assert "persona_label" in rc.run_critics(draft, critic_ctx)["rejected_by"]

    def test_persona_label_accepts_a_concrete_referent(self, critic_ctx):
        assert rc.persona_label("Fascinating, but $NVDA is the tell.", critic_ctx)["verdict"] == "pass"
        assert rc.persona_label("Fascinating, but the funding side is the tell.",
                                critic_ctx)["verdict"] == "pass"

    def test_fact_discipline_rejects_an_unwhitelisted_number(self, critic_ctx):
        draft = "IG spreads widened 47.9% this week. Credit is the test."
        verdict = rc.run_critics(draft, critic_ctx)
        assert "fact_discipline" in verdict["rejected_by"]
        assert any("47.9%" in r for r in verdict["reasons"])

    def test_fact_discipline_allows_small_bare_integers(self, critic_ctx):
        assert rc.fact_discipline("Two of 3 legs agree on the funding side.",
                                  critic_ctx)["verdict"] == "pass"

    @pytest.mark.parametrize("draft,token", [
        ("Credit spreads widened to $4.5B of issuance.", "$4.5B"),
        ("Funding stress at 1.2T notional.", "1.2T"),
        ("Basis at 100bp on the curve.", "100bp"),
        ("Carry ratio 0.35 on the spread.", "0.35"),
        ("Margins fell -3.4 on the quarter.", "-3.4"),
        ("Issuance of 3,500 units cleared.", "3,500"),
    ])
    def test_fact_discipline_catches_the_shapes_finance_copy_hallucinates(
            self, draft, token, critic_ctx):
        """The shared tokenizer passes all of these; a reply is the worst place
        for a fabricated figure, so the critic adds coverage on top of it."""
        ctx = {**critic_ctx, "numbers_whitelist": []}
        verdict = rc.fact_discipline(draft, ctx)
        assert verdict["verdict"] == "reject", f"{token} slipped through"
        assert any(token in r for r in verdict["reasons"]), verdict["reasons"]

    def test_a_whitelisted_scaled_number_is_allowed(self, critic_ctx):
        ctx = {**critic_ctx, "numbers_whitelist": ["$4.5B"]}
        assert rc.fact_discipline("Issuance hit $4.5B this week.", ctx)["verdict"] == "pass"
        # Same figure, currency mark dropped in the prose.
        assert rc.fact_discipline("Issuance hit 4.5B this week.", ctx)["verdict"] == "pass"

    def test_a_thousands_separator_is_not_read_as_its_tail(self, critic_ctx):
        """The shared regex reads "3,500" as the bare integer "500", so a
        whitelist of 3,500 would reject the truth and admit a fabrication."""
        ctx = {**critic_ctx, "numbers_whitelist": ["3,500"]}
        assert rc.fact_discipline("Issuance of 3,500 units.", ctx)["verdict"] == "pass"
        assert rc.fact_discipline("Issuance of 500 units.", ctx)["verdict"] == "reject"

    def test_vocab_rejects_a_banned_study_name(self, critic_ctx):
        assert "vocab" in rc.run_critics("The vwap held at 12.5% on credit.",
                                         critic_ctx)["rejected_by"]

    def test_dignity_rejects_contempt(self, critic_ctx):
        draft = "This take is clown behaviour. Spreads widened 12.5%."
        assert "dignity" in rc.run_critics(draft, critic_ctx)["rejected_by"]

    def test_dignity_rejects_shouting(self, critic_ctx):
        assert rc.dignity("CREDIT SPREADS ARE THE ONLY THING THAT MATTERS HERE",
                          critic_ctx)["verdict"] == "reject"

    def test_dignity_rejects_personal_correction(self, critic_ctx):
        assert rc.dignity("you are wrong about the funding side", critic_ctx)["verdict"] == "reject"

    @pytest.mark.parametrize("critic", [
        # Enumerated by hand ON PURPOSE. Parametrising over rc.CRITICS compares
        # the output against the constant that drove it, so deleting a critic
        # from the register would keep the test green.
        "informational_surplus", "corpus_near_dup", "blocklist",
        "position_consistency", "persona_label", "reply_value",
        "fact_discipline", "vocab", "warmth_register", "fabrication", "dignity",
    ])
    def test_every_critic_is_wired_into_the_pass(self, critic, critic_ctx):
        verdict = rc.run_critics(CLEAN_DRAFT, critic_ctx)
        assert critic in {c["critic"] for c in verdict["critics"]}
        assert critic in rc.CRITICS and critic in rc._CRITIC_FUNCS

    def test_the_critic_register_has_not_silently_shrunk(self):
        # 8 at XG-W4; `reply_value` (E4 reply doctrine) is the ninth; the
        # warmth build (2026-08-01) added `warmth_register` and `fabrication`.
        assert len(rc.CRITICS) == 11
        assert set(rc.CRITICS) == set(rc._CRITIC_FUNCS)

    def test_a_crashing_critic_rejects_rather_than_passes(self, monkeypatch, critic_ctx):
        """A pass-by-exception is how a gate silently stops gating."""
        monkeypatch.setitem(rc._CRITIC_FUNCS, "dignity",
                            lambda d, c: (_ for _ in ()).throw(RuntimeError("boom")))
        verdict = rc.run_critics(CLEAN_DRAFT, critic_ctx)
        assert verdict["verdict"] == "reject"
        assert "dignity" in verdict["rejected_by"]


class TestLlmMayOnlyDeEscalate:
    """Charter §2 amendment 9, enforced structurally rather than by policy."""

    def test_llm_can_turn_a_pass_into_a_reject(self, critic_ctx):
        verdict = rc.run_critics(CLEAN_DRAFT, critic_ctx, llm_de_escalate=lambda d, c: True)
        assert verdict["verdict"] == "reject"
        assert "dignity_llm" in verdict["rejected_by"]

    def test_llm_is_never_consulted_on_an_already_rejected_draft(self, critic_ctx):
        """No code path exists by which a model rescues a rejected draft."""
        called: list[int] = []

        def _hook(draft, ctx):
            called.append(1)
            return False

        verdict = rc.run_critics(PARENT, critic_ctx, llm_de_escalate=_hook)
        assert verdict["verdict"] == "reject"
        assert called == []

    def test_a_false_answer_cannot_clear_a_deterministic_reject(self, critic_ctx):
        verdict = rc.run_critics("The vwap held.", critic_ctx, llm_de_escalate=lambda d, c: False)
        assert verdict["verdict"] == "reject"

    def test_a_raising_hook_is_ignored_not_fatal(self, critic_ctx):
        verdict = rc.run_critics(CLEAN_DRAFT, critic_ctx,
                                 llm_de_escalate=lambda d, c: (_ for _ in ()).throw(ValueError()))
        assert verdict["verdict"] == "pass"


# ===========================================================================
# GATE: queue enforces expiry + one-owner + attempts cap; lease expiry requeues
# ===========================================================================
class TestReplyQueueStore:
    def test_state_dir_is_never_inside_the_repo(self, monkeypatch):
        monkeypatch.delenv("MASTERMIND_REPLY_DESK_DIR", raising=False)
        assert ROOT not in rq.state_dir().parents
        assert rq.state_dir() == Path.home() / ".mastermind" / "reply_desk"

    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MASTERMIND_REPLY_DESK_DIR", str(tmp_path / "x"))
        assert rq.state_dir() == tmp_path / "x"

    def test_item_schema_carries_the_charter_fields(self):
        item = _item()
        for field in ("account", "target_url", "target_status_id", "parent_author",
                      "parent_excerpt", "draft", "alt_drafts", "tier", "score",
                      "score_components", "not_before", "expires_at", "mode", "status"):
            assert field in item
        assert rq.validate_item(item) == []

    def test_media_carries_both_local_path_and_public_url(self):
        item = _item()
        item2 = rq.make_item(
            account="kelly", target_url=f"https://x.com/a/status/{THREAD}",
            parent_author="a", parent_excerpt="p", draft="d with 12.5%",
            tier="relationship", score=0.5,
            chart={"local_path": "x.png", "public_url": "https://cdn/x.png", "chart_id": "c"},
        )
        assert set(item2["chart"]) == {"local_path", "public_url", "chart_id"}
        assert item["chart"] is None

    def test_id_is_a_content_hash(self):
        assert _item()["id"] == _item()["id"]
        assert _item(draft="different draft 12.5%")["id"] != _item()["id"]

    def test_bad_tier_raises(self):
        with pytest.raises(ValueError):
            _item(tier="megacap")

    def test_unparseable_target_url_raises(self):
        with pytest.raises(ValueError):
            rq.make_item(account="kelly", target_url="https://x.com/a", parent_author="a",
                         parent_excerpt="p", draft="d", tier="relationship", score=0.1)

    def test_duplicate_enqueue_refused(self, store):
        item = _item()
        assert rq.enqueue(item, store)["ok"]
        assert rq.enqueue(item, store)["reason"] == "duplicate"


class TestCriticStampIsStructural:
    """M1 — the runbook tells the operator every draft cleared the full roster.

    That was a claim about a PRODUCER, and the producer (discovery -> score ->
    draft -> critics -> enqueue) is not built in this wave. Enforcing the stamp
    at the STORE makes the claim true for anything that ever reaches the desktop
    lane, whoever built it and whenever that lands.
    """

    def test_an_unstamped_item_cannot_be_enqueued(self, store):
        item = _item(critics=None)
        result = rq.enqueue(item, store)
        assert result["ok"] is False and result["reason"] == "invalid"
        assert any("critics" in e for e in result["errors"])
        assert rq.read_items(store) == []

    def test_a_rejected_verdict_cannot_be_enqueued(self, store):
        stamp = rc.stamp({
            "verdict": "reject", "rejected_by": ["dignity"],
            "critics": [{"critic": n, "verdict": "pass", "reasons": []} for n in rc.CRITICS],
        })
        result = rq.enqueue(_item(critics=stamp), store)
        assert result["ok"] is False
        assert any("verdict must be 'pass'" in e for e in result["errors"])

    def test_a_hand_written_pass_does_not_satisfy_the_gate(self, store):
        """Forging the verdict is not enough — the roster must have run."""
        result = rq.enqueue(_item(critics={"verdict": "pass"}), store)
        assert result["ok"] is False
        assert any("schema" in e for e in result["errors"])

    def test_a_partial_pass_is_refused(self, store):
        partial = rc.stamp({
            "verdict": "pass", "rejected_by": [],
            "critics": [{"critic": n, "verdict": "pass", "reasons": []}
                        for n in list(rc.CRITICS)[:4]],
        })
        result = rq.enqueue(_item(critics=partial), store)
        assert result["ok"] is False
        assert any("did not all run" in e for e in result["errors"])

    def test_screen_produces_a_stamp_the_queue_accepts(self, store, critic_ctx):
        """End to end on the REAL critic pass, not a fabricated stamp."""
        verdict, stamp = rc.screen(CLEAN_DRAFT, critic_ctx)
        assert verdict["verdict"] == "pass"
        assert rq.enqueue(_item(critics=stamp), store)["ok"] is True

    def test_screen_on_a_bad_draft_produces_a_stamp_the_queue_refuses(self, store, critic_ctx):
        _, stamp = rc.screen("Our validated read.", critic_ctx)
        assert rq.enqueue(_item(critics=stamp), store)["ok"] is False

    def test_every_stored_item_carries_a_passing_stamp(self, store):
        """The invariant stated positively: nothing in the store lacks one."""
        rq.enqueue(_item(), store)
        rq.enqueue(_item(thread="1900000000000000950", draft="Another 12.5%."), store)
        for item in rq.read_items(store):
            assert rq.validate_critic_stamp(item) == []

    def test_exactly_one_production_module_enqueues(self):
        """XG-W4 shipped with NO caller and asserted `callers == []`, so that the
        wave wiring a producer would be forced to touch the docs in the same
        change. XG-W6 wired it, updated `docs/reply_desk_runbook.md` §9-§11 and
        `reply_queue`'s docstring, and this assertion moved to its post-producer
        form: exactly ONE module may enqueue, and it is the producer.

        The bar is unchanged in substance — a second, un-reviewed path into the
        queue is still a defect, and the store-side critic stamp is still what
        makes the safety claim true regardless of who fills the store.

        TWO ways in, as of the reply deck (2026-08-01). `admin/marketing.py`
        joined the list when the operator got an EDIT button: `_item_id` hashes
        the draft text, so rewriting a draft is a supersession — retire the
        original, enqueue a re-screened replacement — and there is no way to
        express that without a second enqueue call. It is admitted here and
        NOT waved through: the loop below additionally requires every enqueuing
        module to import `reply_critics`, so a second entrance cannot be one
        that skips the pass. The store-side stamp check remains the real gate;
        this is the census that keeps the list of entrances short and reviewed.
        """
        import ast

        callers: list[str] = []
        for directory in ("engine", "scripts", "admin", "app", "lib"):
            base = ROOT / directory
            if not base.is_dir():
                continue
            for path in base.rglob("*.py"):
                if path.name == "reply_queue.py":
                    continue  # the definition site
                try:
                    src = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                # Scope to modules that actually bind the reply queue —
                # `outbox.enqueue` is a different function on a different rail.
                if "reply_queue" not in src:
                    continue
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                aliases = {"reply_queue"}
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module and \
                            node.module.endswith("marketing"):
                        aliases |= {a.asname or a.name for a in node.names
                                    if a.name == "reply_queue"}
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call)
                            and getattr(node.func, "attr", None) == "enqueue"
                            and getattr(node.func.value, "id", None) in aliases):
                        callers.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        modules = sorted({c.split(":")[0] for c in callers})
        assert modules == ["admin/marketing.py", "engine/marketing/reply_producer.py"], (
            f"only reviewed modules may fill the reply queue; found {modules}. "
            "A second path in is a second place the critic contract has to hold.")

        # ...and each of them faces the critics. A module that enqueues without
        # importing the pass is the exact defect the census exists to catch,
        # and "it is on the allowlist" must never be the reason it is safe.
        for module in modules:
            src = (ROOT / module).read_text(encoding="utf-8")
            assert "reply_critics" in src, (
                f"{module} fills the reply queue without importing reply_critics")

    def test_the_docs_describe_the_producer_that_exists(self):
        runbook = (ROOT / "docs" / "reply_desk_runbook.md").read_text(encoding="utf-8")
        low = runbook.lower()
        assert "the producer (xg-w6)" in low, "the runbook must document the built producer"
        assert "--lane reply" in runbook, "operators need the command that runs it"
        assert "reply_desk.producer.enabled" in runbook, "and the arming lever"
        src = (ROOT / "engine" / "marketing" / "reply_queue.py").read_text(encoding="utf-8")
        assert "XG-W6" in src

    def test_the_runbook_no_longer_claims_the_producer_is_unbuilt(self):
        """The stale-doc trap this pair exists to catch, in its live form."""
        runbook = (ROOT / "docs" / "reply_desk_runbook.md").read_text(encoding="utf-8")
        assert "the queue\n  does not fill on its own yet" not in runbook
        assert "does not fill on its own yet" not in runbook


class TestZeroCrossAccountEngagement:
    """M4 — the fleet-linkage hard law, in code rather than in the runbook.

    It is the STRONGER of the two coordination rules; the weaker
    one-conversation-one-owner rule already has a hard lock, so leaving this one
    to operator discipline was backwards.
    """

    def test_replying_to_our_own_account_is_rejected(self, critic_ctx, cfg):
        ctx = {**critic_ctx, "parent_author": "mastermindkelly",
               "our_handles": rc.our_handles(cfg)}
        verdict = rc.run_critics(CLEAN_DRAFT, ctx)
        assert "blocklist" in verdict["rejected_by"]
        assert any("cross-account" in r for r in verdict["reasons"])

    def test_an_ancestor_author_in_the_thread_is_rejected(self, critic_ctx, cfg):
        ctx = {**critic_ctx, "parent_author": "someoutsider",
               "thread_authors": ["someoneelse", "mastermindcici"],
               "our_handles": rc.our_handles(cfg)}
        assert "blocklist" in rc.run_critics(CLEAN_DRAFT, ctx)["rejected_by"]

    def test_an_outsider_thread_still_passes(self, critic_ctx, cfg):
        ctx = {**critic_ctx, "parent_author": "someoutsider",
               "thread_authors": ["anotheroutsider"],
               "our_handles": rc.our_handles(cfg)}
        assert rc.run_critics(CLEAN_DRAFT, ctx)["verdict"] == "pass"

    def test_our_handles_covers_every_desk_including_dark_ones(self, cfg):
        handles = {h.lower() for h in rc.our_handles(cfg)}
        for handle in ("mastermindx001", "w_chris6031", "meagmastermind",
                       "sophmastermind", "mastermindkelly", "mastermindcici"):
            assert handle in handles
        # mastermind_news is wired-but-dark; replying to it is the same signal.
        assert "mastermindnews1" in handles

    def test_the_law_is_case_and_at_insensitive(self, critic_ctx, cfg):
        ctx = {**critic_ctx, "parent_author": "@MastermindKelly",
               "our_handles": rc.our_handles(cfg)}
        assert rc.blocklist(CLEAN_DRAFT, ctx)["verdict"] == "reject"


class TestExpiredItemsAreUnclaimable:
    """M3 — an item expiring between the sweep and the claim would otherwise be
    sent stale AND become permanently unexpirable, since `claimed` is (rightly)
    not expirable."""

    def test_claim_refuses_an_expired_item(self, store):
        item = _item(ttl_min=10)
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        assert rq.claim(item["id"], holder="d", root=store,
                        now=NOW + timedelta(minutes=30)) is None
        assert rq.fold_state(store)["status"][item["id"]] == "approved"

    def test_the_item_remains_expirable_after_the_refused_claim(self, store):
        item = _item(ttl_min=10)
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rq.claim(item["id"], holder="d", root=store, now=NOW + timedelta(minutes=30))
        assert rq.expire_due(now=NOW + timedelta(minutes=31), root=store) == [item["id"]]

    def test_a_live_item_is_still_claimable(self, store):
        item = _item(ttl_min=45)
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        assert rq.claim(item["id"], holder="d", root=store,
                        now=NOW + timedelta(minutes=5)) is not None

    def test_claim_for_desktop_is_behind_the_dial(self, store, cfg, m1_cfg):
        """M0 must export NOTHING — including a claim file."""
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        assert rx.claim_for_desktop(item["id"], holder="d", cfg=cfg,
                                    root=store, now=NOW) is None
        assert not (rx.claims_dir(store) / f"{item['id']}.json").exists()
        assert rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg,
                                    root=store, now=NOW) is not None


class TestOneConversationOneOwner:
    def test_a_second_desk_cannot_take_an_owned_thread(self, store):
        assert rq.enqueue(_item(account="kelly"), store)["ok"]
        result = rq.enqueue(_item(account="cici", draft="other draft 12.5%"), store)
        assert result["ok"] is False
        assert result["reason"] == "thread_owned"
        assert result["owner"] == "kelly"

    def test_the_lock_survives_a_send(self, store):
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rq.transition(item["id"], "sent", actor="desk-1", root=store, receipt={"url": "u"})
        assert rq.thread_owner(THREAD, store) == "kelly"
        assert rq.enqueue(_item(account="cici", draft="x 12.5%"), store)["reason"] == "thread_owned"

    def test_a_rejected_item_releases_the_thread(self, store):
        item = _item()
        rq.enqueue(item, store)
        rq.reject(item["id"], root=store, reason="off-beat")
        assert rq.thread_owner(THREAD, store) is None
        assert rq.enqueue(_item(account="cici", draft="cici draft 12.5%"), store)["ok"]

    def test_an_expired_item_releases_the_thread(self, store):
        item = _item(ttl_min=1)
        rq.enqueue(item, store)
        rq.expire_due(now=NOW + timedelta(minutes=5), root=store)
        assert rq.thread_owner(THREAD, store) is None

    def test_different_threads_do_not_collide(self, store):
        assert rq.enqueue(_item(account="kelly"), store)["ok"]
        assert rq.enqueue(_item(account="cici", thread="1900000000000000002",
                                draft="another draft 12.5%"), store)["ok"]


class TestExpiry:
    def test_a_stale_draft_is_auto_killed(self, store):
        item = _item(ttl_min=15)
        rq.enqueue(item, store)
        killed = rq.expire_due(now=NOW + timedelta(minutes=16), root=store)
        assert killed == [item["id"]]
        assert rq.fold_state(store)["status"][item["id"]] == "expired"

    def test_a_live_draft_survives(self, store):
        item = _item(ttl_min=45)
        rq.enqueue(item, store)
        assert rq.expire_due(now=NOW + timedelta(minutes=10), root=store) == []

    def test_expiry_does_not_resurrect_a_terminal_item(self, store):
        item = _item(ttl_min=1)
        rq.enqueue(item, store)
        rq.reject(item["id"], root=store)
        assert rq.expire_due(now=NOW + timedelta(hours=2), root=store) == []
        assert rq.fold_state(store)["status"][item["id"]] == "rejected"

    def test_an_expired_item_is_never_exported(self, store, m1_cfg):
        item = _item(ttl_min=5)
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        result = rx.export_approved(cfg=m1_cfg, root=store, now=NOW + timedelta(minutes=30))
        assert result["count"] == 0
        assert item["id"] in result["expired_ids"]
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()


class TestLeaseAndClaims:
    def test_claim_marks_the_item_in_flight(self, store):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        claim = rq.claim(item["id"], holder="desk-1", root=store, now=NOW)
        assert claim["holder"] == "desk-1"
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"

    def test_a_queued_item_cannot_be_claimed(self, store):
        item = _item()
        rq.enqueue(item, store)
        assert rq.claim(item["id"], holder="desk-1", root=store, now=NOW) is None

    def test_expired_lease_returns_the_item_to_queued(self, store):
        """GATE: lease expiry returns items to queued.

        Deliberately `queued`, not `approved`: an expired lease means we cannot
        know whether the session posted, so a human re-approves.
        """
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        released = rq.release_expired_claims(now=NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 1),
                                             root=store)
        assert released == [item["id"]]
        assert rq.fold_state(store)["status"][item["id"]] == "queued"

    def test_a_live_lease_is_not_released(self, store):
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        assert rq.release_expired_claims(now=NOW + timedelta(seconds=60), root=store) == []


class TestAttemptsCap:
    def test_re_arm_is_refused_past_the_cap(self, store):
        """Two attempts, then the item is dead. Never retry-spam a thread."""
        assert rq.MAX_SEND_ATTEMPTS == 2
        item = _item()
        rq.enqueue(item, store)
        iid = item["id"]

        # Attempt 1: approve -> claim -> fail -> re-arm is allowed.
        _advance_to_claimed(iid, store)
        assert rq.transition(iid, "failed", actor="desk-1", root=store)
        assert rq.fold_state(store)["attempts"][iid] == 1
        assert rq.transition(iid, "approved", actor="admin", root=store)

        # Attempt 2: fail again -> the cap is reached and re-arm is refused.
        assert rq.claim(iid, holder="desk-1", root=store, now=NOW) is not None
        assert rq.transition(iid, "failed", actor="desk-1", root=store)
        assert rq.fold_state(store)["attempts"][iid] == rq.MAX_SEND_ATTEMPTS
        assert rq.transition(iid, "approved", actor="admin", root=store) is False
        assert rq.fold_state(store)["status"][iid] == "failed"

    def test_the_cap_cannot_be_walked_around_via_queued(self, store):
        """`failed -> queued -> approved` was a free re-arm: the guard sat on
        one edge instead of on the state."""
        item = _item()
        rq.enqueue(item, store)
        iid = item["id"]
        for _ in range(rq.MAX_SEND_ATTEMPTS):
            assert rq.approve(iid, root=store)
            assert rq.claim(iid, holder="d", root=store, now=NOW) is not None
            assert rq.transition(iid, "failed", actor="d", root=store)
            rq.transition(iid, "queued", actor="admin", root=store)
        assert rq.fold_state(store)["attempts"][iid] == rq.MAX_SEND_ATTEMPTS
        assert rq.approve(iid, root=store) is False
        assert rq.claim(iid, holder="d", root=store, now=NOW) is None

    def test_illegal_transitions_are_refused(self, store):
        item = _item()
        rq.enqueue(item, store)
        assert rq.transition(item["id"], "sent", actor="x", root=store) is False
        assert rq.transition("unknown-id", "approved", actor="x", root=store) is False

    def test_terminal_statuses_never_move(self, store):
        item = _item()
        rq.enqueue(item, store)
        rq.reject(item["id"], root=store)
        assert rq.transition(item["id"], "approved", actor="x", root=store) is False


# ===========================================================================
# GATE: mode dial ships M0/M1; M2/M3 config-gated OFF
# ===========================================================================
class TestModeDial:
    def test_shipped_config_is_m0_everywhere(self, cfg):
        for account in cfg["reply_desk"]["mode"]["accounts"]:
            assert rq.resolve_mode(cfg, account) == "M0"

    def test_shipped_config_enables_only_m0_and_m1(self, cfg):
        assert set(cfg["reply_desk"]["modes_enabled"]) == {"M0", "M1"}

    def test_m2_and_m3_exist_as_keys(self):
        assert rq.MODES == ("M0", "M1", "M2", "M3")

    def test_m2_cannot_be_enabled_by_config(self, capsys):
        bad = {"reply_desk": {"modes_enabled": ["M0", "M1", "M2"],
                              "mode": {"accounts": {"kelly": "M2"}}}}
        assert rq.resolve_mode(bad, "kelly") == "M0"
        out = capsys.readouterr().out
        assert out.startswith("::warning title=reply-desk-mode-gated::")
        assert "XG-W6" in out

    def test_m3_cannot_be_enabled_by_config(self):
        bad = {"reply_desk": {"modes_enabled": ["M3"], "mode": {"default": "M3"}}}
        assert rq.resolve_mode(bad, "kelly") == "M0"

    def test_m1_is_selectable(self, m1_cfg):
        assert rq.resolve_mode(m1_cfg, "kelly") == "M1"
        assert rq.resolve_mode(m1_cfg, "cici") == "M0"

    def test_unknown_mode_falls_back_to_m0(self):
        assert rq.resolve_mode({"reply_desk": {"mode": {"default": "M9"}}}, "kelly") == "M0"


class TestKillSwitches:
    """A kill switch documented to the operator that does nothing is worse than
    no kill switch."""

    def test_disabling_the_desk_forces_m0(self, m1_cfg):
        off = json.loads(json.dumps(m1_cfg))
        off["reply_desk"]["enabled"] = False
        assert rq.resolve_mode(off, "kelly") == "M0"

    def test_disabling_the_desk_zeroes_the_cap(self, m1_cfg):
        off = json.loads(json.dumps(m1_cfg))
        off["reply_desk"]["enabled"] = False
        assert sentinel.reply_send_cap(off, "kelly", mode="M1") == 0

    def test_disabling_the_desk_stops_every_export(self, store, m1_cfg):
        off = json.loads(json.dumps(m1_cfg))
        off["reply_desk"]["enabled"] = False
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        assert rx.export_approved(cfg=off, root=store, now=NOW)["count"] == 0

    def test_a_null_per_account_cap_silences_that_account(self, m1_cfg):
        """An explicit null is an operator silencing one desk, not asking for
        the default."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": None}
        assert sentinel.reply_send_cap(cfg, "kelly", mode="M1") == 0

    def test_an_unparseable_cap_fails_closed(self, m1_cfg, capsys):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": "eighteen"}
        assert sentinel.reply_send_cap(cfg, "kelly", mode="M1") == 0
        assert capsys.readouterr().out.startswith("::warning title=reply-cap-unparseable::")

    def test_config_ttl_governs_the_real_item(self, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["ttl_min"] = 7
        item = rq.make_item(
            account="kelly", target_url=f"https://x.com/a/status/{THREAD}",
            parent_author="a", parent_excerpt="p", draft="d 12.5%",
            tier="relationship", score=0.5, cfg=cfg, now=NOW)
        assert item["expires_at"] == "2026-07-28T15:07:00Z"

    def test_config_lease_governs_the_real_claim(self, store, m1_cfg):
        """Asserting lease_s_for() alone proved nothing — it had no production
        caller. This drives the path the runbook actually documents."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["lease_s"] = 42
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        claim = rx.claim_for_desktop(item["id"], holder="d", cfg=cfg, root=store, now=NOW)
        assert claim["lease_until"] == "2026-07-28T15:00:42Z"

    def test_a_bad_lease_value_does_not_break_the_claim_path(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["lease_s"] = "ten minutes"
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        claim = rx.claim_for_desktop(item["id"], holder="d", cfg=cfg, root=store, now=NOW)
        assert claim is not None, "a typo must not take down the desktop claim path"


class TestCrossMidnightCap:
    def test_a_stale_dated_draft_cannot_spend_a_second_days_allowance(self, store, m1_cfg):
        """Gating on the draft's creation day let a queue straddling midnight
        send twice its cap in one afternoon."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        send_day = NOW + timedelta(days=1)

        fresh = _item(thread="1900000000000000600", draft="Fresh 12.5%.", now=send_day)
        rq.enqueue(fresh, store)
        _advance_to_claimed(fresh["id"], store, now=send_day)
        assert rq.mark_sent(fresh["id"], receipt={"url": "u"}, root=store,
                            cfg=cfg, now=send_day)["ok"] is True

        # Long TTL so the item is still LIVE on the send day — this test is
        # about the cap's day arithmetic, not about expiry.
        stale = _item(thread="1900000000000000601", draft="Yesterday 12.5%.",
                      now=NOW, ttl_min=48 * 60)
        rq.enqueue(stale, store)
        _advance_to_claimed(stale["id"], store, now=send_day)
        result = rq.mark_sent(stale["id"], receipt={"url": "u"}, root=store,
                              cfg=cfg, now=send_day)
        assert result["ok"] is False and result["reason"] == "reply_cap_daily"


class TestExporterModeGate:
    def test_m0_exports_nothing(self, store, cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        result = rx.export_approved(cfg=cfg, root=store, now=NOW)
        assert result["count"] == 0
        assert result["skipped_mode"] == [item["id"]]
        assert not rx.queue_dir(store).exists() or list(rx.queue_dir(store).glob("*.json")) == []

    def test_m1_exports_approved_items_to_the_host_dir(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        result = rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        assert result["count"] == 1
        path = rx.queue_dir(store) / f"{item['id']}.json"
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["draft"] == CLEAN_DRAFT
        assert payload["target_url"].endswith(THREAD)

    def test_m1_does_not_export_unapproved_items(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        assert rx.export_approved(cfg=m1_cfg, root=store, now=NOW)["count"] == 0

    def test_export_carries_no_scoring_internals_or_credentials(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        payload = json.loads((rx.queue_dir(store) / f"{item['id']}.json").read_text(encoding="utf-8"))
        assert "score_components" not in payload
        assert "alt_drafts" not in payload

    def test_export_is_idempotent(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        assert rx.export_approved(cfg=m1_cfg, root=store, now=NOW)["count"] == 1
        assert rx.export_approved(cfg=m1_cfg, root=store, now=NOW)["count"] == 0


# ===========================================================================
# GATE: the sentinel reply counter counts REAL queue sends
# ===========================================================================
class TestSentinelReplyCounter:
    def test_counter_reads_the_field_items_actually_carry(self):
        """The pre-XG-W4 counter read `type` only; queue/outbox items carry `kind`."""
        assert sentinel.is_reply_item({"kind": "reply"}) is True
        assert sentinel.is_reply_item({"type": "reply"}) is True
        assert sentinel.is_reply_item({"kind": "signal"}) is False
        assert sentinel.is_reply_item({}) is False

    def test_gate_plan_now_counts_a_kind_keyed_reply(self, cfg):
        """Regression: the same plan was uncounted before the fix."""
        plan = {"as_of": "2026-07-28", "accounts": [{"id": "kelly", "queue": [
            {"kind": "reply", "text": "one", "slot": "2026-07-28T14:00:00Z"},
            {"kind": "reply", "text": "two", "slot": "2026-07-28T15:00:00Z"},
        ]}]}
        _, report = sentinel.gate_plan(plan, cfg)
        assert report["checks"]["cadence"]["reply_cap_hits"] >= 1, (
            "with max_replies_per_account_per_day=0 every reply must be trimmed")

    def test_gate_plan_missed_a_kind_keyed_reply_before_the_fix(self, cfg, monkeypatch):
        """Pins the DEFECT, not the wording: restoring the old `type`-only read
        makes the counter vacuous again, which this test must notice."""
        monkeypatch.setattr(sentinel, "is_reply_item",
                            lambda item: item.get("type") == "reply")
        plan = {"as_of": "2026-07-28", "accounts": [{"id": "kelly", "queue": [
            {"kind": "reply", "text": "one", "slot": "2026-07-28T14:00:00Z"},
        ]}]}
        _, report = sentinel.gate_plan(plan, cfg)
        assert report["checks"]["cadence"]["reply_cap_hits"] == 0

    def test_m0_cap_is_zero_whatever_config_says(self, cfg):
        loud = json.loads(json.dumps(cfg))
        loud["reply_desk"]["daily_caps"]["per_account_target"] = 25
        assert sentinel.reply_send_cap(loud, "kelly", mode="M0") == 0

    def test_m1_uses_the_configured_target(self, cfg):
        assert sentinel.reply_send_cap(cfg, "kelly", mode="M1") == 18

    def test_hard_ceiling_cannot_be_raised_by_config(self, cfg, capsys):
        loud = json.loads(json.dumps(cfg))
        loud["reply_desk"]["daily_caps"]["per_account_target"] = 999
        assert sentinel.reply_send_cap(loud, "kelly", mode="M1") == 30
        assert capsys.readouterr().out.startswith("::warning title=reply-cap-clamped::")

    def test_per_account_override(self, cfg):
        tuned = json.loads(json.dumps(cfg))
        tuned["reply_desk"]["daily_caps"]["accounts"] = {"cici": 5}
        assert sentinel.reply_send_cap(tuned, "cici", mode="M1") == 5
        assert sentinel.reply_send_cap(tuned, "kelly", mode="M1") == 18


class TestRealSendsAreCapped:
    def _send_n(self, store: Path, cfg: dict, n: int) -> list[dict]:
        results = []
        for i in range(n):
            thread = str(1900000000000000100 + i)
            item = _item(thread=thread, draft=f"Draft {i} with spreads at 12.5%.")
            assert rq.enqueue(item, store)["ok"], thread
            _advance_to_claimed(item["id"], store)
            results.append(rq.mark_sent(item["id"], receipt={"url": f"u{i}"},
                                        root=store, cfg=cfg, now=NOW))
        return results

    def test_m0_refuses_every_send(self, store, cfg):
        [result] = self._send_n(store, cfg, 1)
        assert result["ok"] is False
        assert result["reason"] == "mode_m0_draft_only"

    def test_the_thirtieth_send_is_refused_when_the_cap_is_twenty_nine(self, store, m1_cfg):
        """GATE fixture, literal reading: the 30th send is refused."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 29}
        results = self._send_n(store, cfg, 30)
        assert all(r["ok"] for r in results[:29])
        assert results[29]["ok"] is False
        assert results[29]["reason"] == "reply_cap_daily"
        assert rq.sends_today("kelly", "2026-07-28", store) == 29

    def test_the_hard_ceiling_refuses_the_thirty_first_send(self, store, m1_cfg):
        """GATE fixture, ceiling reading: config asks for more, 30 is the wall."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 999}
        results = self._send_n(store, cfg, 31)
        assert all(r["ok"] for r in results[:30])
        assert results[30]["ok"] is False
        assert results[30]["reason"] == "reply_cap_daily"
        assert rq.sends_today("kelly", "2026-07-28", store) == 30

    def test_sends_today_counts_only_this_account(self, store, m1_cfg):
        self._send_n(store, m1_cfg, 2)
        assert rq.sends_today("kelly", "2026-07-28", store) == 2
        assert rq.sends_today("cici", "2026-07-28", store) == 0

    def test_a_send_records_its_outcome_seam(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=m1_cfg, now=NOW)
        assert rq.outcomes(store)[item["id"]]["sent_at"] == "2026-07-28T15:00:00Z"

    def test_telemetry_fields_exist_on_the_item(self):
        for field in ("sent_at", "author_replied", "likes", "follower_delta"):
            assert field in _item()

    def test_unknown_outcome_fields_are_ignored(self, store):
        item = _item()
        rq.enqueue(item, store)
        assert rq.record_outcome(item["id"], root=store, nonsense=1) is False


class TestReceiptIngest:
    def test_a_receipt_records_a_real_send(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        (rx.receipts_dir(store) / f"{item['id']}.json").write_text(json.dumps({
            "id": item["id"], "url": "https://x.com/kelly/status/999",
            "screenshot": "shot.png", "holder": "desk-1",
        }), encoding="utf-8")
        result = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert result["recorded"] == [item["id"]]
        assert rq.fold_state(store)["status"][item["id"]] == "sent"

    def test_a_consumed_receipt_is_not_double_counted(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        (rx.receipts_dir(store) / f"{item['id']}.json").write_text(
            json.dumps({"id": item["id"], "url": "u"}), encoding="utf-8")
        rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)["count"] == 0
        assert rq.sends_today("kelly", "2026-07-28", store) == 1

    def test_a_receipt_beyond_the_cap_is_refused_loudly(self, store, m1_cfg, capsys):
        """A SPENT cap (not a silenced account) — the retryable case."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        spent = _item(thread="1900000000000000800", draft="Spent the cap 12.5%.")
        rq.enqueue(spent, store)
        _advance_to_claimed(spent["id"], store)
        rq.mark_sent(spent["id"], receipt={"url": "u"}, root=store, cfg=cfg, now=NOW)

        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        (rx.receipts_dir(store) / f"{item['id']}.json").write_text(
            json.dumps({"id": item["id"], "url": "u"}), encoding="utf-8")
        result = rx.ingest_receipts(cfg=cfg, root=store, now=NOW)
        assert result["refused"][0]["reason"] == "reply_cap_daily"
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        # Every annotation must START its line (GH drops the rest), and the cap
        # warning must be among them regardless of what else was announced.
        assert all(ln.startswith("::") for ln in lines), lines
        assert any(ln.startswith("::warning title=reply-cap-daily::") for ln in lines), lines

    def test_sweep_runs_the_full_tick(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        result = rx.sweep(cfg=m1_cfg, root=store, now=NOW)
        assert result["export"]["count"] == 1
        assert result["released_claims"] == []

    def test_sweep_ingests_before_it_sizes_the_cap(self, store, m1_cfg):
        """A send from the last tick must be on the books before headroom is
        computed, or export hands out allowance that is already spent."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}

        sent_item = _item(thread="1900000000000000900", draft="First reply 12.5%.")
        rq.enqueue(sent_item, store)
        _advance_to_claimed(sent_item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        (rx.receipts_dir(store) / f"{sent_item['id']}.json").write_text(
            json.dumps({"id": sent_item["id"], "url": "https://x.com/a/status/1",
                        "screenshot": "s.png"}), encoding="utf-8")

        pending = _item(thread="1900000000000000901", draft="Second reply 12.5%.")
        rq.enqueue(pending, store)
        rq.approve(pending["id"], root=store)

        result = rx.sweep(cfg=cfg, root=store, now=NOW)
        assert result["ingest"]["recorded"] == [sent_item["id"]]
        assert result["export"]["count"] == 0, "the cap was already spent this tick"
        assert pending["id"] in result["export"]["skipped_cap"]

    def test_a_receipt_with_no_url_is_refused_and_retired(self, store, m1_cfg, capsys):
        """A receipt is the only evidence a reply went out; an empty one is not
        evidence, and it must not loop forever."""
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        path = rx.receipts_dir(store) / f"{item['id']}.json"
        path.write_text(json.dumps({"id": item["id"]}), encoding="utf-8")

        result = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert result["refused"][0]["reason"] == "receipt_missing_url"
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"
        assert not path.exists() and path.with_suffix(".invalid").exists()
        assert any(ln.startswith("::warning title=reply-receipt-invalid::")
                   for ln in capsys.readouterr().out.splitlines())

    def test_a_receipt_refused_for_any_reason_is_parked_not_looped(self, store, cfg, capsys):
        """`mode_m0_draft_only` fell through a list of two known reasons and
        looped forever in SILENCE — the worst version of this bug. The handler
        is a catch-all now, so a new refusal reason cannot reopen it."""
        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        path = rx.receipts_dir(store) / f"{item['id']}.json"
        path.write_text(json.dumps({"id": item["id"], "url": "u", "screenshot": "s"}),
                        encoding="utf-8")

        # cfg is the shipped M0 config: the desk was disabled after the send.
        first = rx.ingest_receipts(cfg=cfg, root=store, now=NOW)
        assert first["refused"][0]["reason"] == "mode_m0_draft_only"
        assert path.with_suffix(".unresolved").exists()
        assert any(ln.startswith("::warning title=reply-receipt-orphan::")
                   for ln in capsys.readouterr().out.splitlines())
        assert rx.ingest_receipts(cfg=cfg, root=store, now=NOW)["refused"] == []

    def test_retiring_two_receipts_to_one_suffix_never_clobbers(self, store, m1_cfg):
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        for name in ("a", "b"):
            (rx.receipts_dir(store) / f"{name}.json").write_text(
                json.dumps({"id": name, "url": "u"}), encoding="utf-8")
        rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        retired = sorted(p.name for p in rx.receipts_dir(store).iterdir()
                         if ".unresolved" in p.name)
        assert len(retired) == 2, retired

    def test_a_deferred_receipt_keeps_its_lease(self, store, m1_cfg):
        """A cap-refused receipt still describes a PUBLIC reply. Releasing its
        lease strands it — `queued` has no edge to `sent` — and the lost send
        buys back a slot in the very count the cap is sized against."""
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}

        first = _item(thread="1900000000000000700", draft="First 12.5%.")
        second = _item(thread="1900000000000000701", draft="Second 12.5%.")
        for it in (first, second):
            rq.enqueue(it, store)
            _advance_to_claimed(it["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        for it in (first, second):
            (rx.receipts_dir(store) / f"{it['id']}.json").write_text(
                json.dumps({"id": it["id"], "url": "u", "screenshot": "s"}), encoding="utf-8")

        # Far past the lease, so a naive release would fire.
        late = NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 60)
        result = rx.sweep(cfg=cfg, root=store, now=late)
        assert len(result["ingest"]["recorded"]) == 1
        assert result["released_claims"] == [], "a pending receipt must keep its lease"

        # Whichever one the cap deferred must still be claimed, so its retained
        # receipt can still be recorded once the cap clears.
        [deferred] = [r["id"] for r in result["ingest"]["refused"]]
        assert result["ingest"]["refused"][0]["reason"] == "reply_cap_daily"
        assert rq.fold_state(store)["status"][deferred] == "claimed"

    def test_an_unresolvable_receipt_is_parked_not_retried_forever(self, store, m1_cfg):
        """An orphan receipt re-refused on every sweep is a permanent warning
        nobody can clear."""
        item = _item()
        rq.enqueue(item, store)
        rq.reject(item["id"], root=store)          # terminal: no send is possible
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        path = rx.receipts_dir(store) / f"{item['id']}.json"
        path.write_text(json.dumps({"id": item["id"], "url": "u", "screenshot": "s"}),
                        encoding="utf-8")

        first = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert first["refused"][0]["reason"] == "illegal_transition"
        assert path.with_suffix(".unresolved").exists()
        assert rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)["refused"] == []


class TestExportCapEnforcement:
    """GATE: the daily cap must bind BEFORE the desktop lane can send, not when
    a receipt comes back — by then the reply is already public."""

    def test_export_never_exceeds_the_daily_cap(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        ids = []
        for i in range(3):
            item = _item(thread=str(1900000000000000200 + i), draft=f"Draft {i} at 12.5%.")
            rq.enqueue(item, store)
            rq.approve(item["id"], root=store)
            ids.append(item["id"])

        result = rx.export_approved(cfg=cfg, root=store, now=NOW)
        assert result["count"] == 1, "three approved items against a cap of one"
        assert len(result["skipped_cap"]) == 2
        assert len(list(rx.queue_dir(store).glob("*.json"))) == 1

    def test_export_counts_sends_already_made_today(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 2}
        sent = _item(thread="1900000000000000300", draft="Already sent 12.5%.")
        rq.enqueue(sent, store)
        _advance_to_claimed(sent["id"], store)
        rq.mark_sent(sent["id"], receipt={"url": "u"}, root=store, cfg=cfg, now=NOW)

        for i in range(2):
            nxt = _item(thread=str(1900000000000000310 + i), draft=f"Next {i} 12.5%.")
            rq.enqueue(nxt, store)
            rq.approve(nxt["id"], root=store)

        result = rx.export_approved(cfg=cfg, root=store, now=NOW)
        assert result["count"] == 1, "one send already spent, cap 2 leaves headroom 1"

    def test_export_counts_mirrors_still_in_flight(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        first = _item(thread="1900000000000000400", draft="First 12.5%.")
        rq.enqueue(first, store)
        rq.approve(first["id"], root=store)
        assert rx.export_approved(cfg=cfg, root=store, now=NOW)["count"] == 1

        second = _item(thread="1900000000000000401", draft="Second 12.5%.")
        rq.enqueue(second, store)
        rq.approve(second["id"], root=store)
        result = rx.export_approved(cfg=cfg, root=store, now=NOW)
        assert result["count"] == 0, "the first mirror is unsent and still holds the slot"

    def test_export_prefers_the_highest_scoring_opportunity(self, store, m1_cfg):
        cfg = json.loads(json.dumps(m1_cfg))
        cfg["reply_desk"]["daily_caps"]["accounts"] = {"kelly": 1}
        low = rq.make_item(account="kelly", target_url="https://x.com/a/status/1900000000000000500",
                           parent_author="a", parent_excerpt="p", draft="Low 12.5%.",
                           tier="conversion", score=0.10, score_components={},
                           critics=_pass_stamp(), now=NOW)
        high = rq.make_item(account="kelly", target_url="https://x.com/a/status/1900000000000000501",
                            parent_author="a", parent_excerpt="p", draft="High 12.5%.",
                            tier="relationship", score=0.95, score_components={},
                            critics=_pass_stamp(), now=NOW)
        for it in (low, high):
            rq.enqueue(it, store)
            rq.approve(it["id"], root=store)
        result = rx.export_approved(cfg=cfg, root=store, now=NOW)
        assert result["exported"] == [high["id"]]


class TestMirrorGarbageCollection:
    """A kill that never reaches the handoff directory is not a kill."""

    def test_an_expired_items_mirror_is_removed(self, store, m1_cfg):
        item = _item(ttl_min=10)
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        assert (rx.queue_dir(store) / f"{item['id']}.json").exists()

        result = rx.export_approved(cfg=m1_cfg, root=store, now=NOW + timedelta(minutes=30))
        assert item["id"] in result["expired_ids"]
        assert item["id"] in result["swept_mirrors"]
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()

    def test_a_released_lease_removes_the_mirror(self, store, m1_cfg):
        """Otherwise the desktop lane can post it a second time, invisibly."""
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        rq.claim(item["id"], holder="desk-1", root=store, now=NOW)
        rq.release_expired_claims(now=NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 1), root=store)

        rx.export_approved(cfg=m1_cfg, root=store, now=NOW + timedelta(seconds=700))
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()

    def test_a_rejected_items_mirror_is_removed(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        rq.reject(item["id"], root=store, reason="off-beat")
        assert rx.sweep_mirrors(store) == [item["id"]]
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()

    def test_a_stale_claim_file_is_swept_too(self, store, m1_cfg):
        """claims/ is a published contract directory; a lease file outliving its
        lease is exactly the divergence wiring it up was meant to avoid."""
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        assert (rx.claims_dir(store) / f"{item['id']}.json").exists()

        rq.release_expired_claims(now=NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 1),
                                  root=store)
        rx.sweep_mirrors(store)
        assert not (rx.claims_dir(store) / f"{item['id']}.json").exists()

    def test_a_live_claim_file_survives(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        rx.sweep_mirrors(store)
        assert (rx.claims_dir(store) / f"{item['id']}.json").exists()

    def test_a_claimed_items_mirror_survives(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        rq.claim(item["id"], holder="desk-1", root=store, now=NOW)
        assert rx.sweep_mirrors(store) == []
        assert (rx.queue_dir(store) / f"{item['id']}.json").exists()

    def test_claim_for_desktop_writes_the_published_contract_dir(self, store, m1_cfg):
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        claim = rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg,
                                     root=store, now=NOW)
        assert claim["holder"] == "desk-1"
        assert (rx.claims_dir(store) / f"{item['id']}.json").exists()


class TestInFlightItemsAreNotExpired:
    def test_a_claimed_item_is_not_expired_out_from_under_the_sender(self, store):
        """It may already be posted; expiring it orphans a PUBLIC reply."""
        item = _item(ttl_min=45)
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store, now=NOW + timedelta(minutes=40))
        assert rq.expire_due(now=NOW + timedelta(minutes=46), root=store) == []
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"

    def test_the_receipt_still_records_after_the_ttl(self, store, m1_cfg):
        item = _item(ttl_min=45)
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store, now=NOW + timedelta(minutes=40))
        rq.expire_due(now=NOW + timedelta(minutes=46), root=store)
        result = rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=m1_cfg,
                              now=NOW + timedelta(minutes=47))
        assert result["ok"] is True

    def test_expiry_resumes_once_the_lease_is_released(self, store):
        item = _item(ttl_min=45)
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store, now=NOW)
        later = NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 1)
        rq.release_expired_claims(now=later, root=store)
        assert rq.expire_due(now=NOW + timedelta(hours=2), root=store) == [item["id"]]


# ===========================================================================
# House-law guards
# ===========================================================================
class TestHouseLaws:
    def test_a_full_lifecycle_writes_nothing_inside_the_repo(self, tmp_path, m1_cfg):
        """The M1 is the nightly render host: an intraday writer inside the
        render checkout collides with render-lane resets.

        Functional, not a substring scan — a grep for 'Path("data")' would miss
        `base / "data"`, single quotes, and f-strings alike.
        """
        tracked = ROOT / "data" / "marketing"
        before = {p: p.stat().st_mtime_ns for p in tracked.rglob("*") if p.is_file()} \
            if tracked.exists() else {}

        store = tmp_path / "desk"
        item = _item()
        rq.enqueue(item, store)
        rq.approve(item["id"], root=store)
        rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=m1_cfg, now=NOW)
        rq.expire_due(now=NOW, root=store)
        rd.run_tick(rd.ReplyDiscoveryProvider({}, sub_cap_usd=1.0, global_cap_usd=75.0),
                    root=store, offline=True, now=NOW)

        after = {p: p.stat().st_mtime_ns for p in tracked.rglob("*") if p.is_file()} \
            if tracked.exists() else {}
        assert after == before, "the reply desk wrote inside the repo checkout"
        assert (store / "store" / "items.jsonl").exists(), "…and wrote nothing at all"

    def test_state_dir_default_is_outside_the_repo(self, monkeypatch):
        monkeypatch.delenv("MASTERMIND_REPLY_DESK_DIR", raising=False)
        resolved = rq.state_dir()
        assert ROOT not in resolved.parents and resolved != ROOT

    def test_annotations_start_the_line(self):
        """GH annotations emitted via a logger are silently dropped."""
        for name in ("reply_queue", "reply_discovery", "reply_export"):
            src = (ROOT / "engine" / "marketing" / f"{name}.py").read_text(encoding="utf-8")
            for line in src.splitlines():
                stripped = line.strip()
                if "::warning" in stripped and stripped.startswith("log."):
                    pytest.fail(f"{name}: ::warning emitted through a logger: {stripped}")

    def test_no_module_opens_a_socket_except_discovery(self):
        """The desktop session is the only sender; the repo never posts."""
        for name in ("reply_queue", "reply_export", "reply_drafter", "reply_score",
                     "reply_critics"):
            src = (ROOT / "engine" / "marketing" / f"{name}.py").read_text(encoding="utf-8")
            for tell in ("urlopen", "urllib.request", "http.client", "requests.post"):
                assert tell not in src, f"{name} must make no network call ({tell})"

    def test_discovery_is_read_only(self):
        """twitterapi.io is a READ path. A write verb here would be a new
        posting rail smuggled past the dial."""
        import ast

        src = (ROOT / "engine" / "marketing" / "reply_discovery.py").read_text(encoding="utf-8")
        assert "api.twitterapi.io" in src
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Request":
                kwargs = {kw.arg for kw in node.keywords}
                assert "data" not in kwargs, "a Request body would make this a write path"
                assert "method" not in kwargs, "the read lane must not name a verb"
        for verb in ('"POST"', "'POST'", '"PUT"', '"DELETE"'):
            assert verb not in src, f"write verb {verb} in a read-only lane"

    def test_reply_queue_is_not_the_outbox(self):
        from engine.marketing import outbox
        assert "reply" not in outbox.KINDS, (
            "replies ride their own store; Buffer cannot reply, so a reply must "
            "never be mistaken for a postable outbox item")
        assert rq.SCHEMA_ID != outbox.SCHEMA_ID

    def test_runbook_is_committed(self):
        doc = ROOT / "docs" / "reply_desk_runbook.md"
        assert doc.exists()
        text = doc.read_text(encoding="utf-8")
        for required in ("~/.mastermind/reply_desk", "lease", "receipt",
                         "browser profile", "stagger", "M0", "M1"):
            assert required in text, f"runbook must cover {required!r}"

    def test_runbook_never_asks_for_a_credential_in_a_file(self):
        """Credentials live only in the browser profiles."""
        text = (ROOT / "docs" / "reply_desk_runbook.md").read_text(encoding="utf-8")
        assert "Credentials live only in the browser profile" in text


# ===========================================================================
# Admin surface
# ===========================================================================
class TestAdminReplyQueuePanel:
    def test_panel_renders_a_two_zone_rail(self, store, cfg):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        # now=NOW is NOT optional. The fixture item is built at NOW with a
        # 45-minute TTL, so a panel read on the WALL CLOCK expires it the moment
        # real time passes 2026-07-28T15:45Z — a clock fixture bomb that turns
        # this suite red on a date rather than on a defect.
        payload = adm.reply_queue(root=ROOT, store=store, now=NOW)
        assert payload["ok"] is True
        [block] = payload["accounts"]
        assert block["id"] == "kelly"
        assert [r["id"] for r in block["awaiting"]] == [item["id"]]
        assert block["approved"] == []

    def test_panel_shows_the_dial_and_the_cap(self, store, cfg):
        from admin import marketing as adm

        rq.enqueue(_item(), store)
        payload = adm.reply_queue(root=ROOT, store=store, now=NOW)
        block = payload["accounts"][0]
        assert block["mode"] == "M0"
        assert block["cap"] == 0, "M0 must render a zero cap"
        assert payload["modes_enabled"] == ["M0", "M1"]
        assert payload["hard_ceiling"] == 30

    def test_panel_expires_stale_drafts_before_showing_them(self, store):
        from admin import marketing as adm

        item = _item(ttl_min=1)
        rq.enqueue(item, store)
        payload = adm.reply_queue(root=ROOT, store=store, now=NOW + timedelta(hours=2))
        assert item["id"] in payload["expired_now"]
        assert payload["accounts"][0]["awaiting"] == []

    def test_panel_surfaces_score_components(self, store):
        from admin import marketing as adm

        rq.enqueue(_item(), store)
        row = adm.reply_queue(root=ROOT, store=store, now=NOW)["accounts"][0]["awaiting"][0]
        assert row["score_components"] == {"author_tier": 0.26}

    def test_approve_moves_the_item(self, store):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        result = adm.decide_reply(item["id"], "approve", store=store)
        assert result["ok"] and result["status"] == "approved"
        assert rq.fold_state(store)["status"][item["id"]] == "approved"

    def test_hold_keeps_the_item_in_the_rail(self, store):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        assert adm.decide_reply(item["id"], "hold", store=store)["ok"]
        assert rq.fold_state(store)["status"][item["id"]] == "queued"

    def test_bad_decision_refused(self, store):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        assert adm.decide_reply(item["id"], "post", store=store)["ok"] is False

    def test_unknown_id_refused(self, store):
        from admin import marketing as adm

        assert adm.decide_reply("nope", "approve", store=store)["ok"] is False
        assert adm.reject_reply("nope", store=store)["ok"] is False

    def test_reject_releases_the_thread(self, store, tmp_path):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        result = adm.reject_reply(item["id"], reason="restates the parent",
                                  root=tmp_path, store=store)
        assert result["ok"] and result["thread_released"]
        assert rq.thread_owner(THREAD, store) is None

    def test_reject_writes_the_taste_corpus_row(self, store, tmp_path):
        """The corpus survives — but in HOST state, not the render checkout."""
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        result = adm.reject_reply(item["id"], reason="no surplus over the parent",
                                  root=tmp_path, store=store)
        assert result["ok"] and result["logged"]

        rows = rq.read_rejections(store)
        assert len(rows) == 1
        assert rows[0]["reason"] == "no surplus over the parent"
        assert rows[0]["kind"] == "reply"
        assert rows[0]["text"] == CLEAN_DRAFT, "snapshot the draft, not a pointer"

    def test_reject_never_writes_into_the_repo_checkout(self, store, tmp_path):
        """The deciding operator runs the admin on the M1 render host."""
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        adm.reject_reply(item["id"], reason="off-beat", root=tmp_path, store=store)
        assert not (tmp_path / "data" / "marketing" / "rejections.jsonl").exists()
        assert rq.rejections_path(store).exists()
        assert ROOT not in rq.rejections_path(store).parents

    def test_hold_leaves_a_ledger_trace(self, store):
        """"The operator held this" and "nobody looked" are different facts."""
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        result = adm.decide_reply(item["id"], "hold", note="wrong read", store=store)
        assert result["ok"] and result["logged"]
        rows = rq.decisions(store)[item["id"]]
        assert rows[0]["decision"] == "hold" and rows[0]["note"] == "wrong read"
        assert rq.fold_state(store)["status"][item["id"]] == "queued"

    def test_rejecting_twice_is_refused(self, store, tmp_path):
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        adm.reject_reply(item["id"], root=tmp_path, store=store)
        assert adm.reject_reply(item["id"], root=tmp_path, store=store)["ok"] is False

    def test_opening_the_panel_never_strands_a_pending_receipt(self, store, m1_cfg):
        """M2 — the panel releases leases too. Without skip_ids, merely OPENING
        the admin page drops an item whose receipt is pending to `queued`, which
        has no edge to `sent`: a PUBLIC reply then goes permanently uncounted
        while the cap hands its slot back."""
        from admin import marketing as adm

        item = _item()
        rq.enqueue(item, store)
        _advance_to_claimed(item["id"], store)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        (rx.receipts_dir(store) / f"{item['id']}.json").write_text(
            json.dumps({"id": item["id"], "url": "u", "screenshot": "s"}), encoding="utf-8")

        late = NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 60)
        payload = adm.reply_queue(root=ROOT, store=store, now=late)
        assert payload["released_now"] == []
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"

        # And the send still records afterwards.
        assert rx.ingest_receipts(cfg=m1_cfg, root=store,
                                  now=late)["recorded"] == [item["id"]]

    def test_panel_is_fail_soft(self, monkeypatch):
        from admin import marketing as adm

        monkeypatch.setattr(rq, "expire_due",
                            lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        payload = adm.reply_queue(root=ROOT, store="/nonexistent", now=NOW)
        assert payload["ok"] is False
        assert payload["accounts"] == []


class TestAdminRoutesAreWired:
    """The panel is only real if the server can reach it."""

    def test_routes_exist(self):
        src = (ROOT / "admin" / "server.py").read_text(encoding="utf-8")
        for route in ("/api/marketing/reply-queue",
                      "/api/marketing/reply-queue/decide",
                      "/api/marketing/reply-queue/reject",
                      # The deck (2026-08-01): the payload the page renders, and
                      # the two halves of edit-then-approve.
                      "/api/marketing/reply-deck",
                      "/api/marketing/reply-deck/validate",
                      "/api/marketing/reply-deck/edit"):
            assert f'path == "{route}"' in src, f"missing route {route}"

    def test_handlers_exist(self):
        from admin import marketing as adm

        for fn in ("reply_queue", "decide_reply", "reject_reply",
                   "reply_deck", "validate_reply_text", "edit_reply"):
            assert callable(getattr(adm, fn))

    def test_spa_view_is_registered(self):
        """The view id is the contract; the LABEL is copy and moved with the
        rebuild ("Reply Queue" -> "Reply Deck", 2026-08-01). Pinned on the id so
        this guard fails when the page is unwired, not when it is renamed."""
        src = (ROOT / "admin" / "static" / "app.js").read_text(encoding="utf-8")
        assert '["marketing_reply_queue", "Reply Deck"]' in src, "nav entry missing"
        assert "RENDER.marketing_reply_queue" in src, "renderer missing"
        assert "marketing_reply_queue:" in src, "nav icon missing"
        # rqSkip is the former rqReject: same store call, a name that says what
        # the operator is doing rather than what the ledger records.
        for fn in ("rqDecide", "rqSkip", "rqeOpen", "rqeCheck", "rqeSave"):
            assert f"function {fn}(" in src

    def test_no_panel_read_in_this_suite_relies_on_the_wall_clock(self):
        """NOW is a fixed 2026-07-28T15:00Z and _item() defaults to ttl_min=45,
        so an item built here expires at 15:45Z. adm.reply_queue() runs
        expire_due() before every read and falls back to datetime.now() when no
        clock is injected — which meant these panel tests passed on the morning
        they were written and went PERMANENTLY red at 15:45Z that same day, on a
        suite that gates the marketing-engine lane. Not a flake: a time bomb with
        a known detonation time. Every panel read must pin the clock.
        """
        import ast

        src = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        unpinned = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "reply_queue"):
                continue
            if not any(kw.arg == "now" for kw in node.keywords):
                unpinned.append(node.lineno)
        assert not unpinned, (
            f"adm.reply_queue() called without now= at line(s) {unpinned}; "
            "expire_due() will kill the fixture item once the wall clock passes "
            "its TTL and this suite goes red for good"
        )
