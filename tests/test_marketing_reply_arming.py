"""XG-W7 — ARMING the reply desk, and the actuation contract it hands over.

Two claims are under test here and neither is "the pipeline works" (that is
``tests/test_marketing_reply_producer.py``):

1. **A silent desk announces itself.** Four independent switches gate this lane
   — the process switch, the systemd lane, ``producer.enabled`` and the API key
   — and every one of them used to fail as an INFO line of zeroes. The tests
   below pin the heartbeat, the ordered silence diagnosis, and the start-of-line
   warning that fires after N empty ticks.
2. **The handoff is a versioned contract.** The consumer of ``queue/``,
   ``claims/`` and ``receipts/`` is the operator's own system, written outside
   this repo. So the file shapes are an interface: the version rides on every
   file, a double claim and a double receipt are both safe, a failure has a
   file-level way to be reported, and the runbook's worked example is compared
   against what the code actually writes rather than trusted.

Stdlib + pyyaml only. No network, no LLM, no wall clock.
"""
from __future__ import annotations

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

from engine.marketing import persona_memory as pm  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_export as rx  # noqa: E402
from engine.marketing import reply_producer as rp  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."
GIFT = "IG spreads widened 12.5% this week while capex guidance held."

RUNBOOK = ROOT / "docs" / "reply_desk_runbook.md"
WIRE_UNIT = ROOT / "app" / "deploy" / "marketing-press-feeds.service"
REPLY_UNIT = ROOT / "app" / "deploy" / "marketing-reply-desk.service"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def base_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture()
def armed_cfg(base_cfg: dict) -> dict:
    cfg = json.loads(json.dumps(base_cfg))
    cfg["reply_desk"]["producer"]["enabled"] = True
    return cfg


@pytest.fixture()
def m1_cfg(armed_cfg: dict) -> dict:
    cfg = json.loads(json.dumps(armed_cfg))
    cfg["reply_desk"]["mode"]["accounts"]["kelly"] = "M1"
    # The pacing rule (a sibling lane) gates the export on a burst window; this
    # suite is about the CONTRACT shapes, not about when a burst opens, so it
    # opts out explicitly rather than pinning somebody else's schedule.
    cfg["reply_desk"].setdefault("pacing", {})["enabled"] = False
    return cfg


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """An isolated checkout carrying a valid ONE-desk author register."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "reply_targets.yml").write_text(
        "accounts:\n"
        "  kelly:\n"
        "    beats: [credit, capex]\n"
        "    authors:\n"
        "      - handle: somequant\n"
        "        tier: relationship\n",
        encoding="utf-8")
    return tmp_path


@pytest.fixture()
def placeholder_repo(tmp_path: Path) -> Path:
    """The SHIPPED posture: a desk registered, every author parked at enabled:false."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "reply_targets.yml").write_text(
        "accounts:\n"
        "  kelly:\n"
        "    beats: [credit]\n"
        "    authors:\n"
        "      - handle: PLACEHOLDER_ONE\n"
        "        tier: relationship\n"
        "        enabled: false\n",
        encoding="utf-8")
    return tmp_path


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    return tmp_path / "reply_desk_store"


def _target(*, account: str = "kelly", author: str = "somequant",
            status_id: str = "1900000000000000001", age_min: int = 10) -> dict:
    return {
        "kind": "author_post",
        "status_id": status_id,
        "thread_root_id": status_id,
        "url": f"https://x.com/{author}/status/{status_id}",
        "author": author,
        "author_tier": "relationship",
        "beats": ["credit", "capex"],
        "text": PARENT,
        "created_at": (NOW - timedelta(minutes=age_min)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reply_count": 3, "like_count": 40, "retweet_count": 4, "view_count": 900,
        "account": account, "mechanism": "credit", "subject": "capex",
    }


class _StubProvider:
    """A twitterapi.io stand-in that bills nothing and records its calls."""

    source_tier = "x_reply"
    billed = True

    def __init__(self, targets: list[dict] | None = None) -> None:
        self._targets = targets or []
        self.calls: list[dict] = []

    def fetch(self, *, session_state, offline=False, wire_spend_usd=None,
              accounts=None, now=None):
        self.calls.append({"offline": offline, "accounts": list(accounts or [])})
        if offline:
            return []
        return [t for t in self._targets
                if accounts is None or t.get("account") in accounts]


def _facts(_account: str, _target: dict) -> dict:
    return {
        "facts": [{"id": "f1", "text": GIFT, "salience": 1.0, "numbers": ["12.5%"]}],
        "numbers_whitelist": ["12.5%"],
    }


def _tick(cfg, repo, store, targets, **over):
    kwargs = dict(cfg=cfg, press_cfg={}, root=repo, store=store, now=NOW,
                  facts_for=_facts, provider=_StubProvider(targets))
    kwargs.update(over)
    return rp.run_producer(**kwargs)


def _pass_stamp() -> dict:
    return {"schema": rc.STAMP_SCHEMA, "verdict": "pass", "rejected_by": [],
            "critics_run": list(rc.CRITICS), "stamped_at": "2026-08-01T00:00:00Z"}


def _item(*, account: str = "kelly", thread: str = "1900000000000000042",
          draft: str = "IG spreads widened 12.5% while capex guidance held.") -> dict:
    return rq.make_item(
        account=account, target_url=f"https://x.com/somequant/status/{thread}",
        parent_author="somequant", parent_excerpt=PARENT, draft=draft,
        tier="relationship", score=0.8, score_components={"author_tier": 1.0},
        thread_root_id=thread, target_status_id=thread, as_of="2026-08-01",
        critics=_pass_stamp(), now=NOW, provenance="test",
    )


# ===========================================================================
# GATE 1 — the lane is actually invoked somewhere
# ===========================================================================
class TestTheLaneIsWired:
    def test_a_sibling_unit_runs_the_reply_lane(self):
        """THE root cause: `--lane reply` was implemented and never invoked."""
        assert REPLY_UNIT.exists(), "no unit runs the reply producer on any host"
        exec_line = [ln for ln in REPLY_UNIT.read_text(encoding="utf-8").splitlines()
                     if ln.startswith("ExecStart=")]
        assert exec_line, "the reply unit declares no ExecStart"
        assert "--lane reply" in exec_line[0], exec_line[0]
        assert "marketing_fastlane_daemon" in exec_line[0]

    def test_the_wire_unit_is_untouched(self):
        """The wire keeps its own unit and its own 75 s cadence. Widening it to
        `--lane all` would force one interval on two lanes and make a reply-lane
        crash restart the Trump wire."""
        wire = [ln for ln in WIRE_UNIT.read_text(encoding="utf-8").splitlines()
                if ln.startswith("ExecStart=")][0]
        assert "--lane press" in wire and "--interval 75" in wire

    def test_the_reply_unit_names_no_interval_so_config_governs(self):
        exec_line = [ln for ln in REPLY_UNIT.read_text(encoding="utf-8").splitlines()
                     if ln.startswith("ExecStart=")][0]
        assert "--interval" not in exec_line, (
            "cadence in the unit file makes retuning it a host hand-edit CI never sees")

    def test_the_reply_unit_ships_dark_and_says_so(self):
        text = REPLY_UNIT.read_text(encoding="utf-8")
        assert "reply_desk.producer.enabled" in text
        assert "TWITTERAPI_IO_KEY" in text
        assert "MARKETING_FASTLANE_ENABLED" in text
        assert "M0" in text, "the unit must say it sends nothing"


class TestTheDeskSweepAlsoRuns:
    """The producer half was dark; so was the DESK half. `reply_export.sweep`
    shipped with the runbook telling an operator to drive it from a `python3 -c`
    one-liner, which at M1 means a receipt is read only when a human remembers —
    and the daily cap is sized against that count."""

    def test_the_reply_lane_drives_the_desk_sweep(self):
        import ast

        src = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = {getattr(c.func, "id", "") for c in ast.walk(main)
                  if isinstance(c, ast.Call)}
        assert "_run_reply_sweep" in called, (
            "a sweep only a human can trigger is not a scheduled sweep")
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_reply_sweep")
        dumped = ast.dump(fn)
        assert "sweep" in dumped and "repo_root" in dumped, (
            "the sweep needs the CHECKOUT for the halt registry and the relation store")

    def test_the_sweep_is_skipped_on_a_dry_run(self):
        """--dry-run writes nothing to disk; the sweep writes."""
        src = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
            encoding="utf-8")
        assert "if not args.dry_run:\n                    _log_reply_sweep(" in src


class TestCadenceIsConfigDriven:
    def test_the_reply_lane_reads_its_interval_from_config(self, base_cfg):
        import scripts.marketing_fastlane_daemon as daemon

        want = int(base_cfg["reply_desk"]["producer"]["tick_interval_s"])
        assert daemon._resolve_interval(None, lane="reply") == want

    def test_the_config_declares_the_cadence_and_the_silence_threshold(self, base_cfg):
        block = base_cfg["reply_desk"]["producer"]
        assert isinstance(block.get("tick_interval_s"), int)
        assert isinstance(block.get("silent_tick_warn_after"), int)

    def test_other_lanes_keep_the_module_default(self):
        import scripts.marketing_fastlane_daemon as daemon

        assert daemon._resolve_interval(None, lane="press") == daemon._DEFAULT_INTERVAL_S

    def test_an_explicit_flag_always_wins(self):
        import scripts.marketing_fastlane_daemon as daemon

        assert daemon._resolve_interval(11, lane="reply") == 11


# ===========================================================================
# GATE 2 — a tick against a fixture register writes a draft to the queue
# ===========================================================================
class TestATickFillsTheQueue:
    def test_a_tick_writes_a_draft_to_the_M0_queue(self, armed_cfg, repo, store):
        out = _tick(armed_cfg, repo, store, [_target()])
        assert out["enqueued"] == 1, out
        [item] = rq.read_items(store)
        assert item["account"] == "kelly"
        assert item["status"] == "queued"
        assert item["mode"] == "M0", "arming means drafts appear, never sends"
        assert item["draft"].strip()

    def test_the_tick_reports_how_many_authors_are_curated(self, armed_cfg, repo, store):
        """Zero here is the difference between 'quiet day' and 'structurally dark'."""
        out = _tick(armed_cfg, repo, store, [_target()])
        assert out["curated_authors"] == {"kelly": 1}


# ===========================================================================
# GATE 3 — the heartbeat
# ===========================================================================
class TestHeartbeat:
    def test_a_live_tick_writes_the_heartbeat(self, armed_cfg, repo, store):
        out = _tick(armed_cfg, repo, store, [_target()])
        beat = json.loads(rp.heartbeat_path(store).read_text(encoding="utf-8"))
        assert beat["schema"] == rp.HEARTBEAT_SCHEMA
        assert beat["tick"] == 1
        assert beat["consecutive_empty"] == 0
        assert beat["last_enqueued_at"] == "2026-08-01T15:00:00Z"
        assert beat["diagnosis"] is None
        assert out["heartbeat"]["tick"] == 1

    def test_the_heartbeat_lives_in_host_state_not_the_checkout(self, store):
        assert rp.heartbeat_path(store) == store / "producer_heartbeat.json"

    def test_a_DARK_tick_still_advances_the_heartbeat(self, base_cfg, repo, store):
        """An early return that skipped the heartbeat would make 'the producer is
        switched off' look exactly like 'the daemon is dead'."""
        out = _tick(base_cfg, repo, store, [_target()])
        assert out["enabled"] is False
        beat = rp.read_heartbeat(store)
        assert beat["tick"] == 1 and beat["consecutive_empty"] == 1
        assert "producer.enabled is false" in beat["diagnosis"]

    def test_an_offline_tick_writes_nothing(self, armed_cfg, repo, store):
        """The dry-run law for a billed provider: zero network, zero writes — and
        an offline tick returns zero targets BY CONSTRUCTION, so counting it as a
        silent tick would manufacture an alarm out of an inspection command."""
        _tick(armed_cfg, repo, store, [_target()], offline=True)
        assert not rp.heartbeat_path(store).exists()
        assert rp.read_heartbeat(store) == {}

    def test_the_empty_run_climbs_then_resets_on_an_enqueue(self, armed_cfg, repo, store):
        _tick(armed_cfg, repo, store, [])
        _tick(armed_cfg, repo, store, [])
        assert rp.read_heartbeat(store)["consecutive_empty"] == 2
        _tick(armed_cfg, repo, store, [_target()])
        beat = rp.read_heartbeat(store)
        assert beat["consecutive_empty"] == 0 and beat["tick"] == 3

    def test_an_unwritable_heartbeat_never_takes_down_a_tick(self, armed_cfg, repo,
                                                            store, monkeypatch):
        """The artifact exists to prove the lane is alive; a crash here would
        make it look dead in exactly the way it is meant to disprove."""
        monkeypatch.setattr(rp, "heartbeat_path", lambda _s=None: Path("/proc/nope/x.json"))
        out = _tick(armed_cfg, repo, store, [_target()])
        assert out["enqueued"] == 1


# ===========================================================================
# GATE 4 — the silent-desk warning
# ===========================================================================
class TestSilentDeskWarning:
    @staticmethod
    def _warnings(capsys) -> list[str]:
        return [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning title=reply-desk-silent::")]

    def _cfg(self, armed_cfg: dict, after: int = 3) -> dict:
        cfg = json.loads(json.dumps(armed_cfg))
        cfg["reply_desk"]["producer"]["silent_tick_warn_after"] = after
        return cfg

    def test_it_fires_at_line_start_after_n_empty_ticks(self, armed_cfg, repo,
                                                       store, capsys):
        cfg = self._cfg(armed_cfg, after=3)
        for _ in range(2):
            _tick(cfg, repo, store, [])
        assert self._warnings(capsys) == [], "two empty ticks is a quiet day"
        _tick(cfg, repo, store, [])
        [line] = self._warnings(capsys)
        assert line.startswith("::warning title=reply-desk-silent::")
        assert "3 consecutive ticks" in line
        assert "last enqueue: never" in line

    def test_it_does_not_repeat_on_every_tick(self, armed_cfg, repo, store, capsys):
        cfg = self._cfg(armed_cfg, after=3)
        for _ in range(5):
            _tick(cfg, repo, store, [])
        assert len(self._warnings(capsys)) == 1
        _tick(cfg, repo, store, [])
        assert len(self._warnings(capsys)) == 1, "the 6th empty tick re-announces once"

    def test_an_enqueue_clears_the_run(self, armed_cfg, repo, store, capsys):
        cfg = self._cfg(armed_cfg, after=3)
        for _ in range(2):
            _tick(cfg, repo, store, [])
        _tick(cfg, repo, store, [_target()])
        for _ in range(2):
            _tick(cfg, repo, store, [])
        assert self._warnings(capsys) == []

    def test_the_warning_names_the_placeholder_register(self, armed_cfg,
                                                        placeholder_repo, store, capsys):
        """The loudest reason this lane produces nothing must not read as
        'discovery returned zero targets'."""
        cfg = self._cfg(armed_cfg, after=1)
        _tick(cfg, placeholder_repo, store, [])
        [line] = self._warnings(capsys)
        assert "reply_targets.yml" in line and "PLACEHOLDER" in line

    def test_the_warning_names_the_producer_switch_first(self, base_cfg, repo,
                                                         store, capsys):
        cfg = json.loads(json.dumps(base_cfg))
        cfg["reply_desk"]["producer"]["silent_tick_warn_after"] = 1
        _tick(cfg, repo, store, [_target()])
        [line] = self._warnings(capsys)
        assert "reply_desk.producer.enabled is false" in line

    def test_the_diagnosis_is_ordered_by_pipeline_position(self):
        """Reporting 'enqueued=0' is what the tick log already did. The ladder
        must return the EARLIEST stage that explains the silence."""
        assert "producer.enabled" in rp._silence_diagnosis({"enabled": False})
        assert "reply_targets.yml" in rp._silence_diagnosis(
            {"enabled": True, "curated_authors": {"kelly": 0}, "targets": 4})
        assert "zero targets" in rp._silence_diagnosis(
            {"enabled": True, "curated_authors": {"kelly": 3}, "targets": 0})
        assert "min_score" in rp._silence_diagnosis(
            {"enabled": True, "curated_authors": {"kelly": 3}, "targets": 4, "eligible": 0})
        assert "abstention" in rp._silence_diagnosis(
            {"enabled": True, "curated_authors": {"kelly": 3}, "targets": 4,
             "eligible": 2, "drafted": 0, "abstained": 2})
        assert "critics" in rp._silence_diagnosis(
            {"enabled": True, "curated_authors": {"kelly": 3}, "targets": 4,
             "eligible": 2, "drafted": 2, "critic_rejected": 2})


# ===========================================================================
# GATE 5 — preflight
# ===========================================================================
class TestPreflight:
    def test_it_is_offline_and_writes_nothing(self, armed_cfg, repo, store):
        before = sorted(p.name for p in repo.rglob("*"))
        rp.preflight(cfg=armed_cfg, press_cfg={}, root=repo, store=store, now=NOW)
        assert not store.exists(), "preflight must create no host state"
        assert sorted(p.name for p in repo.rglob("*")) == before

    def test_it_names_every_dark_switch(self, base_cfg, repo, store, monkeypatch):
        monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        report = rp.preflight(cfg=base_cfg, press_cfg={}, root=repo, store=store, now=NOW)
        blob = " ".join(report["blockers"])
        assert report["ready"] is False
        assert "MARKETING_FASTLANE_ENABLED" in blob
        assert "reply_desk.producer.enabled" in blob
        assert "reply_discovery.enabled" in blob
        assert "TWITTERAPI_IO_KEY" in blob

    def test_it_goes_ready_once_all_four_are_armed(self, armed_cfg, repo, store,
                                                   monkeypatch):
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "k")
        report = rp.preflight(cfg=armed_cfg, press_cfg={"reply_discovery": {"enabled": True}},
                              root=repo, store=store, now=NOW)
        assert report["ready"] is True, report["blockers"]

    def test_M0_everywhere_is_a_warning_not_a_blocker(self, armed_cfg, repo, store,
                                                      monkeypatch):
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "k")
        report = rp.preflight(cfg=armed_cfg, press_cfg={"reply_discovery": {"enabled": True}},
                              root=repo, store=store, now=NOW)
        assert any("M0" in w for w in report["warnings"])
        assert not any("M0" in b for b in report["blockers"]), (
            "M0 is the LAUNCH STATE — blocking on it would refuse the shipped posture")

    def test_a_placeholder_register_is_a_warning_not_a_blocker(
            self, armed_cfg, placeholder_repo, store, monkeypatch):
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "k")
        report = rp.preflight(cfg=armed_cfg,
                              press_cfg={"reply_discovery": {"enabled": True}},
                              root=placeholder_repo, store=store, now=NOW)
        assert report["checks"]["curated_authors_total"] == 0
        assert any("PLACEHOLDER" in w for w in report["warnings"])
        assert report["ready"] is True, (
            "inbound mentions still produce targets, so this degrades rather than blocks")

    def test_it_reports_the_heartbeat_so_a_dead_lane_is_visible(self, armed_cfg, repo,
                                                               store, monkeypatch):
        monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "k")
        _tick(armed_cfg, repo, store, [])
        report = rp.preflight(cfg=armed_cfg, press_cfg={}, root=repo, store=store, now=NOW)
        assert report["checks"]["heartbeat"]["consecutive_empty"] == 1
        assert "consecutive_empty=1" in rp.format_preflight(report)

    def test_the_daemon_runs_it_ahead_of_the_kill_switch(self, monkeypatch, capsys):
        """Gating the readout behind the switch would hide the answer behind the
        question: 'the switch is off' is the answer it most often has to give."""
        import scripts.marketing_fastlane_daemon as daemon

        monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)
        code = daemon.main(["--lane", "reply", "--preflight"])
        out = capsys.readouterr().out
        assert code == 1, "a blocked desk exits non-zero"
        assert "reply desk preflight" in out
        assert "BLOCKER" in out

    def test_preflight_is_refused_on_the_wrong_lane(self, monkeypatch):
        import scripts.marketing_fastlane_daemon as daemon

        assert daemon.main(["--lane", "press", "--preflight"]) == 2


# ===========================================================================
# GATE 6 — the actuation contract: the payload
# ===========================================================================
def _export_one(store: Path, cfg: dict) -> tuple[dict, dict]:
    item = _item()
    rq.enqueue(item, store)
    rq.approve(item["id"], root=store)
    result = rx.export_approved(cfg=cfg, root=store, now=NOW)
    assert result["count"] == 1, result
    payload = json.loads((rx.queue_dir(store) / f"{item['id']}.json").read_text(
        encoding="utf-8"))
    return item, payload


class TestHandoffPayload:
    def test_the_queue_file_declares_the_contract_version(self, store, m1_cfg):
        _, payload = _export_one(store, m1_cfg)
        assert payload["contract"] == rx.HANDOFF_CONTRACT

    def test_the_payload_carries_what_is_needed_to_act_and_nothing_more(self, store,
                                                                       m1_cfg):
        _, payload = _export_one(store, m1_cfg)
        assert set(payload) == set(rx._EXPORT_FIELDS) | {"contract", "exported_at"}
        for internal in ("score", "score_components", "alt_drafts", "critics",
                         "provenance", "family"):
            assert internal not in payload

    def test_the_claim_file_declares_the_contract_version(self, store, m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        claim = rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg,
                                     root=store, now=NOW)
        assert claim["contract"] == rx.HANDOFF_CONTRACT
        assert claim["reclaimed"] is False
        on_disk = json.loads((rx.claims_dir(store) / f"{item['id']}.json").read_text(
            encoding="utf-8"))
        assert on_disk == claim


class TestClaimIdempotency:
    def test_the_same_holder_may_reclaim_its_live_lease(self, store, m1_cfg):
        """A session that crashed after taking the lease but before recording it
        locally must be able to resume."""
        item, _ = _export_one(store, m1_cfg)
        first = rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg,
                                     root=store, now=NOW)
        again = rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store,
                                     now=NOW + timedelta(seconds=30))
        assert again is not None, "a double claim by its own holder must not refuse"
        assert again["reclaimed"] is True
        assert again["lease_until"] == first["lease_until"], "no lease extension by retry"
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"

    def test_a_different_holder_is_refused(self, store, m1_cfg):
        """Two sessions racing one item is the collision the lease exists to stop."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store, now=NOW)
        assert rx.claim_for_desktop(item["id"], holder="desk-2", cfg=m1_cfg,
                                    root=store, now=NOW) is None

    def test_a_lapsed_lease_is_not_silently_extended_by_its_own_holder(self, store,
                                                                      m1_cfg):
        """An expired lease means we cannot know whether the session posted. A
        human re-approves — handing the lease straight back would erase that."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store, now=NOW)
        late = NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 60)
        assert rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg,
                                    root=store, now=late) is None


class TestAbandonedItems:
    def test_an_abandoned_lease_returns_to_queued_and_clears_the_handoff(self, store,
                                                                        m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store, now=NOW)
        late = NOW + timedelta(seconds=rq.DEFAULT_LEASE_S + 60)
        out = rx.sweep(cfg=m1_cfg, root=store, now=late)
        assert out["released_claims"] == [item["id"]]
        assert rq.fold_state(store)["status"][item["id"]] == "queued"
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()
        assert not (rx.claims_dir(store) / f"{item['id']}.json").exists()

    def test_an_unclaimed_item_expires_and_its_mirror_goes_with_it(self, store, m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        out = rx.sweep(cfg=m1_cfg, root=store, now=NOW + timedelta(minutes=120))
        assert item["id"] in out["export"]["expired_ids"]
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()


# ===========================================================================
# GATE 7 — the actuation contract: receipts
# ===========================================================================
def _write_receipt(store: Path, iid: str, payload: dict) -> Path:
    rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
    path = rx.receipts_dir(store) / f"{iid}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestReceiptOutcomes:
    def test_a_success_receipt_records_the_send_and_clears_the_handoff(self, store,
                                                                      m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {
            "id": item["id"], "status": "sent",
            "url": "https://x.com/mastermindkelly/status/1900000000000000999",
            "screenshot": "/tmp/shot.png", "holder": "desk-1",
            "sent_at": "2026-08-01T15:04:00Z"})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["recorded"] == [item["id"]]
        assert rq.fold_state(store)["status"][item["id"]] == "sent"
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()
        assert not (rx.claims_dir(store) / f"{item['id']}.json").exists()

    def test_a_receipt_with_no_status_is_still_read_as_a_send(self, store, m1_cfg):
        """The pre-XG-W7 shape. A consumer written against v0 must keep working,
        or upgrading this repo silently stops recording its sends."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "url": "https://x.com/a/status/1"})
        assert rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)["recorded"] == [item["id"]]

    def test_a_failure_receipt_marks_the_item_failed_without_a_url(self, store, m1_cfg):
        """There is no URL when nothing was posted. Before this, the file contract
        could only express success and the runbook had to send the operator's
        system into `reply_queue.transition` for one of three outcomes."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg, root=store, now=NOW)
        path = _write_receipt(store, item["id"], {
            "id": item["id"], "status": "failed", "reason": "compose box never loaded",
            "holder": "desk-1", "sent_at": "2026-08-01T15:04:00Z"})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["failed"] == [item["id"]] and out["refused"] == []
        assert rq.fold_state(store)["status"][item["id"]] == "failed"
        assert path.with_suffix(".done").exists()

    def test_a_failure_receipt_clears_the_mirror_and_the_claim(self, store, m1_cfg):
        """A leftover queue file is a live instruction to post what the session
        just said it could not post."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "status": "failed",
                                           "reason": "rate limited"})
        rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert not (rx.queue_dir(store) / f"{item['id']}.json").exists()
        assert not (rx.claims_dir(store) / f"{item['id']}.json").exists()

    def test_a_failure_receipt_records_the_reason_in_the_ledger(self, store, m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "status": "failed",
                                           "reason": "captcha wall"})
        rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        notes = [r.get("note") or "" for r in rq.read_ledger(store)
                 if r.get("id") == item["id"] and r.get("to") == "failed"]
        assert any("captcha wall" in n for n in notes), notes

    def test_a_double_receipt_is_a_duplicate_not_an_orphan(self, store, m1_cfg, capsys):
        """`.unresolved` means 'a reply may be PUBLIC but unrecorded' and costs a
        manual reconciliation. Spending it on a send that IS on the books is how
        the one warning that matters gets ignored."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "url": "https://x.com/a/status/1"})
        rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        capsys.readouterr()

        path = _write_receipt(store, item["id"], {"id": item["id"],
                                                  "url": "https://x.com/a/status/1"})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["duplicates"] == [item["id"]]
        assert out["refused"] == [], "a duplicate report is not a refusal"
        assert path.with_suffix(".duplicate").exists()
        assert not any("reply-receipt-orphan" in ln
                       for ln in capsys.readouterr().out.splitlines())

    def test_a_double_receipt_never_double_counts_against_the_cap(self, store, m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        for _ in range(2):
            _write_receipt(store, item["id"], {"id": item["id"],
                                               "url": "https://x.com/a/status/1"})
            rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert rq.sends_today("kelly", "2026-08-01", store) == 1

    def test_two_receipt_FILES_for_one_item_settle_in_a_single_pass(self, store,
                                                                    m1_cfg, capsys):
        """The item id is read from the JSON BODY and only defaults to the
        filename, so two differently-named files can name one item. Without an
        in-pass ledger the second lands in the orphan branch and sends an
        operator to reconcile a send that is correctly on the books."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        rx.receipts_dir(store).mkdir(parents=True, exist_ok=True)
        for name in ("a-first", "b-second"):
            (rx.receipts_dir(store) / f"{name}.json").write_text(
                json.dumps({"id": item["id"], "url": "https://x.com/a/status/1"}),
                encoding="utf-8")
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["recorded"] == [item["id"]]
        assert out["duplicates"] == [item["id"]]
        assert out["refused"] == []
        assert not any("reply-receipt-orphan" in ln
                       for ln in capsys.readouterr().out.splitlines())
        assert rq.sends_today("kelly", "2026-08-01", store) == 1

    def test_an_unknown_status_is_refused_rather_than_guessed(self, store, m1_cfg,
                                                              capsys):
        """Reading a field the consumer got wrong as the charitable case is how a
        failed send becomes a recorded one."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        path = _write_receipt(store, item["id"], {"id": item["id"], "status": "posted?",
                                                  "url": "https://x.com/a/status/1"})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["refused"][0]["reason"] == "receipt_unknown_status"
        assert rq.fold_state(store)["status"][item["id"]] == "claimed"
        assert path.with_suffix(".invalid").exists()
        assert any(ln.startswith("::warning title=reply-receipt-invalid::")
                   for ln in capsys.readouterr().out.splitlines())


class TestReceiptFeedsRelationshipMemory:
    def test_a_recorded_send_writes_the_relation_row(self, store, m1_cfg, tmp_path):
        """reply_score reads relations.jsonl for its relationship_stage feature;
        persona_memory writes it; NO production caller sat between them, so the
        feature scored 0.0 with source 'absent' forever."""
        repo_root = tmp_path / "checkout"
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "url": "https://x.com/a/status/1"})
        rx.ingest_receipts(cfg=m1_cfg, root=store, repo_root=repo_root, now=NOW)
        rows = pm.relations("kelly", root=repo_root)
        assert rows["somequant"]["stage"] == "engaged"
        assert rows["somequant"]["touches"] == 1

    def test_without_a_repo_root_the_send_still_records(self, store, m1_cfg):
        """A memory write rides on the send-recording path and must never make a
        recorded send look unrecorded."""
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {"id": item["id"], "url": "https://x.com/a/status/1"})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["recorded"] == [item["id"]]

    def test_note_relation_refuses_to_infer_a_checkout(self, tmp_path):
        assert rx.note_relation(account="kelly", handle="somequant", stage="engaged",
                                repo_root=None, now=NOW) is False

    def test_a_bad_stage_never_escapes_the_helper(self, tmp_path):
        """persona_memory raises on an out-of-vocabulary stage; a raise here would
        turn a recorded send into an unrecorded one."""
        assert rx.note_relation(account="kelly", handle="somequant",
                                stage="besties", repo_root=tmp_path, now=NOW) is False

    def test_an_author_reply_back_escalates_the_relation(self, store, m1_cfg, tmp_path):
        repo_root = tmp_path / "checkout"
        item, _ = _export_one(store, m1_cfg)
        rx.claim_for_desktop(item["id"], holder="d", cfg=m1_cfg, root=store, now=NOW)
        _write_receipt(store, item["id"], {
            "id": item["id"],
            "url": "https://x.com/mastermindkelly/status/1900000000000000999"})
        rx.ingest_receipts(cfg=m1_cfg, root=store, repo_root=repo_root, now=NOW)

        class _Outcomes:
            def poll_outcomes(self, *, session_state, status_ids, offline=False,
                              wire_spend_usd=None, now=None):
                return [{"status_id": status_ids[0],
                         "raw": [{"author": {"userName": "somequant"}}]}]

        out = rp.poll_reply_outcomes(cfg=m1_cfg, press_cfg={}, root=repo_root,
                                     store=store, now=NOW, provider=_Outcomes())
        assert out["author_replied"] == 1
        assert pm.relations("kelly", root=repo_root)["somequant"]["stage"] == "reciprocal"


# ===========================================================================
# GATE 8 — the runbook documents the contract that exists
# ===========================================================================
def _json_block_after(text: str, marker: str) -> dict:
    """Parse the first ```json fence following a marker line."""
    idx = text.find(marker)
    assert idx != -1, f"runbook is missing the {marker!r} section"
    match = re.search(r"```json\n(.*?)\n```", text[idx:], re.S)
    assert match, f"no json block after {marker!r}"
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def doc() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


class TestRunbookMatchesTheCode:
    def test_the_worked_queue_example_matches_what_export_writes(self, doc, store,
                                                                 m1_cfg):
        _, payload = _export_one(store, m1_cfg)
        example = _json_block_after(doc, "#### `queue/<id>.json`")
        assert set(example) == set(payload), (
            "the runbook's worked example has drifted from the exported payload")
        assert example["contract"] == rx.HANDOFF_CONTRACT

    def test_the_worked_claim_example_matches_what_claim_writes(self, doc, store,
                                                               m1_cfg):
        item, _ = _export_one(store, m1_cfg)
        claim = rx.claim_for_desktop(item["id"], holder="desk-1", cfg=m1_cfg,
                                     root=store, now=NOW)
        example = _json_block_after(doc, "#### `claims/<id>.json`")
        assert set(example) == set(claim)

    def test_the_worked_receipt_examples_are_both_accepted(self, doc, store, m1_cfg):
        """Not a key comparison — the receipt is an INPUT, so the honest check is
        that the documented shapes actually drive the two outcomes."""
        sent_example = _json_block_after(doc, "#### `receipts/<id>.json` — success")
        failed_example = _json_block_after(doc, "#### `receipts/<id>.json` — failure")

        first = _item(thread="1900000000000000801")
        second = _item(thread="1900000000000000802")
        for it in (first, second):
            rq.enqueue(it, store)
            rq.approve(it["id"], root=store)
            rx.export_approved(cfg=m1_cfg, root=store, now=NOW)
            rx.claim_for_desktop(it["id"], holder="desk-1", cfg=m1_cfg, root=store,
                                 now=NOW)
        _write_receipt(store, first["id"], {**sent_example, "id": first["id"]})
        _write_receipt(store, second["id"], {**failed_example, "id": second["id"]})
        out = rx.ingest_receipts(cfg=m1_cfg, root=store, now=NOW)
        assert out["recorded"] == [first["id"]], out
        assert out["failed"] == [second["id"]], out

    def test_the_runbook_names_the_contract_version(self, doc):
        assert rx.HANDOFF_CONTRACT in doc

    def test_the_runbook_documents_the_arming_path_that_exists(self, doc):
        for required in ("marketing-reply-desk.service", "--preflight",
                         "producer_heartbeat.json", "reply-desk-silent",
                         "tick_interval_s"):
            assert required in doc, f"runbook must cover {required!r}"

    def test_the_runbook_still_forbids_credentials_in_a_file(self, doc):
        assert "Credentials live only in the browser profile" in doc


class TestHouseLaws:
    def test_new_annotations_start_the_line(self):
        """A ::warning emitted through a logger is silently dropped by GitHub."""
        for name in ("reply_producer", "reply_export"):
            src = (ROOT / "engine" / "marketing" / f"{name}.py").read_text(encoding="utf-8")
            for line in src.splitlines():
                stripped = line.strip()
                if "::warning" in stripped and stripped.startswith("log."):
                    pytest.fail(f"{name}: ::warning through a logger: {stripped}")

    def test_the_producer_opens_no_socket(self):
        src = (ROOT / "engine" / "marketing" / "reply_producer.py").read_text(
            encoding="utf-8")
        for tell in ("urlopen", "urllib.request", "http.client", "requests."):
            assert tell not in src, f"the producer must make no network call ({tell})"

    def test_arming_never_widens_the_shippable_modes(self):
        """Arming means DRAFTS APPEAR. Nothing in this wave may open a send."""
        assert rq.SHIPPABLE_MODES == frozenset({"M0", "M1"})
