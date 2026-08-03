"""W5 — a dark desk PARKS, and no account takes an unbounded wire firehose.

THE DEFECT (operator, 2026-08-02/03). Four posts on the brand account
@mastermindx001 inside one hour, all from a single John Williams appearance
(2, 2, 2 and 1 views), plus two Switzerland CPI sub-prints and a Germany
retail-sales print in the same batch. Measured from the committed outbox
(`data/marketing/outbox/items.jsonl`): **11** `kind="breaking"` items addressed
to `flagship` on 2026-08-03, every one of them `event_class=macro_print`.

TWO INDEPENDENT FAULTS PRODUCE THAT, and this file pins both.

D3a — THE DARK-DESK FALLBACK IS WRONG FOR A VOLUME LANE. `wire_routing.route`
and `hot_tape.live_account` redirected a dark desk's items onto the routing
default, which is the BRAND account. That is a defensible rescue for a lane
emitting a handful of items a day and a product failure for a firehose: one
`desk_network` switch silently made @mastermindx001 the destination for the
whole wire. Parking is now the default (`wire_routing.dark_desk.policy`), the
redirect is opt-in, and the high-severity hatch is off.

D3b — NOTHING BOUNDED PER-ACCOUNT VOLUME. `breaking.flagship_top_k_per_day: 10`
is a per-LANE, per-HOST, calendar-day counter in press_lane's daemon state, so
it cannot see the three other lanes that emit `kind="breaking"`, it resets with
a fresh checkout, and a 23:00 burst can spend two days' worth in two hours. 11
items shipped against a cap of 10. `wire_volume.breaking` is a rolling
per-ACCOUNT ceiling measured from the outbox itself.

Every assertion below fails on the pre-W5 code. Where that is not obvious from
the assertion, the test says which line of the old implementation it pins.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import engine.marketing.hot_tape as HT
from engine.marketing import wire_routing as WR

ROOT = Path(__file__).resolve().parent.parent

#: The fixture clock is REAL now, not a pinned date. `route`, `spill_pool` and
#: `live_account` take no `now` — they are called per item from a daemon and a
#: reference date is not something a routing seam should have to be handed — so
#: they read the wall clock. Pinning the fixture to a literal date would make
#: every assertion here a time bomb that starts failing the day the window
#: slides past it (the fixture-date-plus-wall-clock trap). Tests that need a
#: SPECIFIC offset pass `now=` to `breaking_counts` explicitly instead.
NOW = datetime.now(timezone.utc)

#: A root with NO outbox, for the tests that are about routing rather than
#: volume. Passing it is not decoration: `route`/`live_account` default to the
#: repo root, so a rootless call in a test reads `data/marketing/outbox/
#: items.jsonl` — the committed queue — and the assertion silently becomes a
#: statement about whatever the wire posted today. That is how a routing test
#: turns into a flaky data test.
empty = Path(tempfile.mkdtemp(prefix="wire-volume-empty-"))


@pytest.fixture(autouse=True)
def _reset():
    WR.reset_dark_route_warnings()
    WR.reset_volume_cache()
    HT.reset_dark_account_warnings()
    yield
    WR.reset_dark_route_warnings()
    WR.reset_volume_cache()
    HT.reset_dark_account_warnings()


def _cfg(*, news_on: bool = False, policy: str | None = None,
         hatch: dict | None = None, volume: dict | None = None) -> dict:
    """A marketing.yml-shaped cfg: flagship live, the wire desk switchable."""
    routing: dict = {"default": "flagship",
                     "classes": {"macro_print": "flagship",
                                 "geopolitical": "mastermind_news"}}
    if policy is not None or hatch is not None:
        routing["dark_desk"] = {}
        if policy is not None:
            routing["dark_desk"]["policy"] = policy
        if hatch is not None:
            routing["dark_desk"]["severity_exception"] = hatch
    cfg: dict = {
        "desk_network": {"accounts": [{"id": "flagship", "enabled": True},
                                      {"id": "mastermind_news", "enabled": news_on}]},
        "wire_routing": routing,
    }
    if volume is not None:
        cfg["wire_volume"] = {"breaking": volume}
    return cfg


def _outbox(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal outbox queue and return the root to read it from."""
    d = tmp_path / "data" / "marketing" / "outbox"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "items.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return tmp_path


def _breaking(account: str, n: int, *, at: datetime = NOW,
              kind: str = "breaking") -> list[dict]:
    return [{"id": f"ob-{account}-{i}", "account": account, "kind": kind,
             "text": f"item {i}",
             "created_at": (at - timedelta(minutes=5 * i)).isoformat()}
            for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# 1. A dark desk PARKS. The brand account does not inherit its firehose.
# ─────────────────────────────────────────────────────────────────────────────

class TestDarkDeskParksByDefault:
    """PINS D3a. Pre-W5, every assertion here returned "flagship"."""

    def test_route_keeps_the_dark_owner_and_does_not_hand_it_to_flagship(self):
        """The load-bearing one. `route` used to end in `return fallback`."""
        got = WR.route("geopolitical", cfg=_cfg(), root=empty)
        assert got == "mastermind_news", (
            "a dark wire desk's item was donated to another account — that is "
            "how one switch flip made the brand account a print ticker")
        assert got != "flagship"

    def test_the_park_is_counted_not_merely_logged(self):
        """"Counted, not silent" (house law). A silent `continue` is a leak."""
        for _ in range(3):
            WR.route("geopolitical", cfg=_cfg(), root=empty)
        assert WR.park_census() == {"mastermind_news": 3}

    def test_the_park_is_announced_at_line_start_once_per_desk(self, capsys):
        for _ in range(5):
            WR.route("geopolitical", cfg=_cfg(), root=empty)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "wire-routing-parked" in ln]
        assert len(lines) == 1, f"one line per desk per process, got {lines}"
        # House law: routed through a logger the prefix makes GitHub drop it.
        assert lines[0].startswith("::warning title=wire-routing-parked::")
        assert "mastermind_news" in lines[0]
        assert "account_disabled" in lines[0], (
            "the annotation must name the dispatch-time quarantine reason, or "
            "the operator cannot connect it to the parked items in the ledger")

    def test_hot_tape_live_account_parks_too(self):
        """The tape lane's seam. Pre-W5 this returned the first armed fallback."""
        got = HT.live_account("mastermind_news", marketing_cfg=_cfg(), root=empty,
                              fallbacks=("flagship", "mastermind_news"))
        assert got == "mastermind_news", "flagship inherited the tape firehose"

    def test_an_armed_desk_is_untouched_and_silent(self, capsys):
        assert WR.route("geopolitical", cfg=_cfg(news_on=True),
                        root=empty) == "mastermind_news"
        assert HT.live_account("mastermind_news", root=empty,
                               marketing_cfg=_cfg(news_on=True)) == "mastermind_news"
        assert "parked" not in capsys.readouterr().out

    def test_routing_report_marks_the_park_for_the_admin(self):
        report = WR.routing_report(_cfg())
        assert report["geopolitical"].parked is True
        assert report["geopolitical"].account == "mastermind_news"
        assert report["macro_print"].parked is False

    def test_unknown_liveness_is_not_evidence_of_darkness(self, monkeypatch,
                                                          capsys):
        """Parking a correctly-configured desk's whole output because an import
        failed would be a self-inflicted outage — a worse fault than the one
        being fixed, and invisible."""
        monkeypatch.setattr(WR, "_enabled_accounts", lambda cfg, root: None)
        assert WR.route("geopolitical", cfg=_cfg(), root=empty) == "mastermind_news"
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                               root=empty) == "mastermind_news"
        assert not WR.park_census(), "unknown liveness must not count as a park"
        assert "wire-routing-parked" not in capsys.readouterr().out

    def test_a_config_less_checkout_parks_nothing(self, capsys):
        assert HT.live_account("mastermind_news", marketing_cfg={},
                               root=empty) == "mastermind_news"
        assert not WR.park_census()
        assert "wire-routing-parked" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# 2. The redirect still exists — as an explicit, OFF-by-default choice.
# ─────────────────────────────────────────────────────────────────────────────

class TestRedirectIsOptIn:
    def test_policy_redirect_restores_the_old_behaviour_wholesale(self, capsys):
        got = WR.route("geopolitical", cfg=_cfg(policy="redirect"), root=empty)
        assert got == "flagship"
        assert "::warning title=wire-routing-dark::" in capsys.readouterr().out

    def test_the_default_is_park_not_redirect(self):
        assert WR.dark_desk_policy({}) == "park"
        assert WR.dark_desk_policy(_cfg()) == "park"

    def test_a_typo_reads_as_park_and_says_so(self, capsys):
        """A mistyped value that silently resolved to `redirect` would re-open
        the hole invisibly, which is the entire failure mode."""
        cfg = _cfg(policy="redirekt")
        assert WR.dark_desk_policy(cfg) == "park"
        assert WR.route("geopolitical", cfg=cfg, root=empty) == "mastermind_news"
        out = capsys.readouterr().out
        assert "::warning title=wire-routing-policy-invalid::" in out

    def test_nothing_to_redirect_to_parks_rather_than_inventing_a_desk(self):
        cfg = _cfg(policy="redirect")
        cfg["desk_network"]["accounts"] = [
            {"id": "flagship", "enabled": False},
            {"id": "mastermind_news", "enabled": False},
        ]
        # An all-dark roster is still a roster, so liveness IS known here.
        assert WR.route("geopolitical", cfg=cfg, root=empty) == "mastermind_news"


class TestTheHighSeverityException:
    """The narrow hatch: one genuinely huge single event, never volume."""

    _HATCH = {"enabled": True, "min_severity": 90, "to": "flagship"}

    def test_it_is_off_by_default(self):
        assert WR.severity_exception({})["enabled"] is False
        assert WR.severity_exception(_cfg())["enabled"] is False
        # Off => a 99-severity event on a dark desk still parks.
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg(), root=empty,
                               fallbacks=("flagship",), severity=99.0) == "mastermind_news"

    def test_enabled_and_over_the_floor_redirects(self):
        cfg = _cfg(hatch=self._HATCH)
        assert HT.live_account("mastermind_news", marketing_cfg=cfg, root=empty,
                               fallbacks=("flagship",), severity=95.0) == "flagship"

    def test_enabled_but_under_the_floor_still_parks(self):
        cfg = _cfg(hatch=self._HATCH)
        assert HT.live_account("mastermind_news", marketing_cfg=cfg, root=empty,
                               fallbacks=("flagship",), severity=80.0) == "mastermind_news"

    def test_a_caller_that_passes_no_severity_can_never_reach_it(self):
        """The press wire passes none. It must not fall through the hatch by
        accident just because an operator armed it for the tape."""
        cfg = _cfg(hatch=self._HATCH)
        assert WR.route("geopolitical", cfg=cfg, root=empty) == "mastermind_news"
        assert HT.live_account("mastermind_news", marketing_cfg=cfg, root=empty,
                               fallbacks=("flagship",)) == "mastermind_news"


# ─────────────────────────────────────────────────────────────────────────────
# 3. The per-account rolling ceiling. PINS D3b.
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakingCapBinds:
    _VOL = {"window_hours": 24, "default_per_window": 8, "accounts": {"flagship": 6}}

    def test_thirteen_breaking_items_aimed_at_flagship_in_a_day(self, tmp_path,
                                                                capsys):
        """THE REPRODUCTION. 13 kind=breaking items already on flagship inside
        the window; the 14th is refused by name.

        Pre-W5 there was no function to call: the only bound was press_lane's
        daemon-state counter, which this scenario does not touch at all.
        """
        root = _outbox(tmp_path, _breaking("flagship", 13))
        cfg = _cfg(news_on=True, volume=self._VOL)

        counts = WR.breaking_counts(root, window_hours=24, now=NOW)
        assert counts["flagship"] == 13, counts

        verdict = WR.breaking_cap_verdict("flagship", cfg=cfg, root=root, now=NOW)
        assert verdict.allowed is False
        assert verdict.reason == "breaking_cap_reached"
        # A cap that binds must NAME itself (house law): account, used, cap,
        # window — all four, in the annotation, at line start.
        line = next((ln for ln in capsys.readouterr().out.splitlines()
                     if ln.startswith("::warning title=wire-volume-cap-reached::")), "")
        assert line, "the ceiling bound silently"
        for token in ("flagship", "13", "6", "24"):
            assert token in line, (token, line)

    def test_the_surplus_goes_to_the_wire_desk_not_back_onto_flagship(
            self, tmp_path):
        """The operator's actual complaint: the BRAND account stops taking it."""
        root = _outbox(tmp_path, _breaking("flagship", 13))
        cfg = _cfg(news_on=True, volume=self._VOL)
        assert WR.route("macro_print", cfg=cfg, root=root) == "mastermind_news"

    def test_a_capped_desk_is_not_a_spill_target(self, tmp_path):
        """press_lane's overflow picks from `spill_pool`, so leaving a capped
        flagship in that list would let surplus land on exactly the desk the
        ceiling protects — the cap would be routable around in one hop."""
        root = _outbox(tmp_path, _breaking("flagship", 13))
        cfg = _cfg(news_on=True, volume=self._VOL)
        assert WR.spill_pool(cfg, root=root) == ["mastermind_news"]

    def test_under_the_cap_nothing_changes(self, tmp_path, capsys):
        root = _outbox(tmp_path, _breaking("flagship", 5))
        cfg = _cfg(news_on=True, volume=self._VOL)
        assert WR.route("macro_print", cfg=cfg, root=root) == "flagship"
        assert WR.spill_pool(cfg, root=root) == ["flagship", "mastermind_news"]
        assert "wire-volume" not in capsys.readouterr().out

    def test_every_wire_desk_capped_is_a_park_not_a_pile_on(self, tmp_path,
                                                            capsys):
        """The hole a naive overflow leaves: with both desks spent, "move it
        somewhere" degenerates back to "put it on flagship"."""
        root = _outbox(tmp_path,
                       _breaking("flagship", 13) + _breaking("mastermind_news", 9))
        cfg = _cfg(news_on=True, volume=self._VOL)
        verdict = WR.route_verdict("macro_print", cfg=cfg, root=root)
        assert verdict.parked is True
        assert verdict.reason == "breaking_cap_exhausted"
        assert "::warning title=wire-volume-exhausted::" in capsys.readouterr().out

    def test_hot_tape_honours_the_same_ceiling(self, tmp_path):
        root = _outbox(tmp_path, _breaking("flagship", 13))
        cfg = _cfg(news_on=True, volume=self._VOL)
        assert HT.live_account("flagship", marketing_cfg=cfg, root=root,
                               fallbacks=("flagship",)) == "mastermind_news"

    def test_the_window_is_rolling_not_calendar_daily(self, tmp_path):
        """A calendar day resets at midnight, so a 23:00 burst spends a full day
        and then spends another one an hour later — the exact burst shape."""
        old = _breaking("flagship", 13, at=NOW - timedelta(hours=30))
        root = _outbox(tmp_path, old)
        cfg = _cfg(news_on=True, volume=self._VOL)
        assert WR.breaking_counts(root, window_hours=24, now=NOW) == {}
        assert WR.breaking_cap_verdict("flagship", cfg=cfg, root=root,
                                       now=NOW).allowed is True

    def test_only_kind_breaking_is_counted(self, tmp_path):
        root = _outbox(tmp_path, _breaking("flagship", 13, kind="signal"))
        assert WR.breaking_counts(root, window_hours=24, now=NOW) == {}

    def test_a_persona_desk_ceiling_is_zero_in_the_committed_config(self):
        """Charter §4: a wire account relays and never takes a stance, so a
        persona desk may not carry a relay AT ALL. spill_pool already refuses to
        select one; this is the belt for a lane that addresses one directly."""
        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(
            encoding="utf-8"))
        for desk in ("founder", "meagan", "sophia", "kelly", "cici"):
            assert WR.breaking_cap_for(desk, cfg) == 0, desk

    def test_an_unlimited_cap_is_negative_not_zero(self, tmp_path):
        """0 must be a real zero, so an operator can stop a desk deliberately."""
        root = _outbox(tmp_path, _breaking("flagship", 50))
        off = _cfg(volume={"accounts": {"flagship": -1}})
        stop = _cfg(volume={"accounts": {"flagship": 0}})
        assert WR.breaking_cap_verdict("flagship", cfg=off, root=root,
                                       now=NOW).allowed is True
        assert WR.breaking_cap_verdict("flagship", cfg=stop, root=root,
                                       now=NOW).allowed is False


class TestTheCeilingFailsOpenNotShut:
    """A brake that jams shut on a read error is a worse outage than the volume
    it was fitted to bound."""

    def test_an_unreadable_outbox_allows(self, monkeypatch, tmp_path):
        def _boom(root):
            raise OSError("queue is gone")

        import engine.marketing.outbox as OB
        monkeypatch.setattr(OB, "read_items_all", _boom)
        WR.reset_volume_cache()
        assert WR.breaking_counts(tmp_path, window_hours=24, now=NOW) == {}
        assert WR.breaking_cap_verdict(
            "flagship", cfg=_cfg(volume={"accounts": {"flagship": 1}}),
            root=tmp_path, now=NOW).allowed is True

    def test_an_invalid_cap_is_ignored_with_an_annotation(self, capsys):
        cfg = _cfg(volume={"default_per_window": "lots"})
        assert WR.breaking_cap_for("flagship", cfg) == WR.DEFAULT_BREAKING_PER_WINDOW
        assert "::warning title=wire-volume-cap-invalid::" in capsys.readouterr().out

    def test_route_never_raises_when_the_ceiling_explodes(self, monkeypatch):
        monkeypatch.setattr(WR, "breaking_cap_verdict",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        assert WR.route("macro_print", cfg=_cfg(news_on=True), root=empty) == "flagship"

    def test_the_count_cache_notices_a_growing_queue_inside_one_tick(
            self, tmp_path):
        """A TTL cache would let a lane overshoot its own ceiling inside one
        pass — the one failure a cap may not have. The memo is keyed on file
        identity, and enqueue appends synchronously."""
        root = _outbox(tmp_path, _breaking("flagship", 3))
        assert WR.breaking_counts(root, window_hours=24, now=NOW)["flagship"] == 3
        path = root / "data" / "marketing" / "outbox" / "items.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "x", "account": "flagship",
                                 "kind": "breaking", "text": "n",
                                 "created_at": NOW.isoformat()}) + "\n")
        assert WR.breaking_counts(root, window_hours=24, now=NOW)["flagship"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# 4. The committed config, end to end.
# ─────────────────────────────────────────────────────────────────────────────

class TestCommittedConfig:
    def _cfg(self) -> dict:
        return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(
            encoding="utf-8"))

    def test_the_shipped_default_is_park_with_the_hatch_shut(self):
        cfg = self._cfg()
        assert WR.dark_desk_policy(cfg) == "park"
        assert WR.severity_exception(cfg)["enabled"] is False

    def test_the_brand_desk_ceiling_binds_on_the_day_that_caused_this(self):
        """11 breaking items shipped to flagship on 2026-08-03. The committed
        ceiling must be strictly under that, or this config change is decorative.
        It must also be at or under `breaking.flagship_top_k_per_day`, or the
        looser per-lane counter is still the one deciding."""
        cfg = self._cfg()
        cap = WR.breaking_cap_for("flagship", cfg)
        assert 0 < cap < 11, cap
        assert cap <= int(cfg["breaking"]["flagship_top_k_per_day"]), cap

    def test_every_declared_wire_desk_has_a_ceiling_above_zero(self):
        """A wire desk whose ceiling is 0 is a lane that cannot emit. Persona
        desks are 0 BY DESIGN and are not wire desks — so this reads the roster
        wire_routing actually draws from."""
        cfg = self._cfg()
        declared = set(cfg["wire_routing"]["classes"].values())
        declared.add(WR.default_account(cfg))
        for desk in sorted(declared):
            assert WR.breaking_cap_for(desk, cfg) != 0, desk

    def test_no_persona_desk_owns_a_wire_class(self):
        cfg = self._cfg()
        personas = {"founder", "meagan", "sophia", "kelly", "cici"}
        assert not (set(cfg["wire_routing"]["classes"].values()) & personas)
        assert not (set(WR.spill_pool(cfg, root=ROOT)) & personas)
