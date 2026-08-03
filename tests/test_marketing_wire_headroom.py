"""tests/test_marketing_wire_headroom.py — W4d press-wire headroom (masterplan §8.2).

WHAT W4d CHANGED, AND WHAT IT DID NOT. The press wire's daily budget was a code
constant (3) enforced by ONE counter that was named for one account while
bounding every account. It is now config-driven, PER WIRE DESK, and surplus
spills across the declared wire desks instead of vanishing through a bare
`continue`. Nothing about WHICH item may go out moved: the salience floor, the
market-nexus test, the corroboration gate, the garbage gate and the value gate
are untouched and are exercised elsewhere (tests/test_marketing_press_feeds.py).

Every test here fails on the pre-W4d code. The load-bearing ones are marked
MUTATION: with the inversion that must turn them red.

Covers:
  1. _resolve_top_k precedence (breaking > wire > measured default) + junk.
  2. Per-desk budgets — two desks do NOT share one counter (MUTATION target).
  3. Cross-desk spill: a full desk hands surplus to another LIVE wire desk.
  4. A DARK desk is never a spill target; a PERSONA desk is never eligible.
  5. Counted drops: an exhausted pool increments a PERSISTED census and prints
     its ::warning at LINE START.
  6. The ramp cap is the stricter half of a desk's budget.
  7. hot_tape.live_account: a dark routing target is rescued to a live desk and
     the rescue announces itself at LINE START (the `account_disabled` class —
     29 quarantines on 2026-07-30/31, all mastermind_news, all hot_tape lane).
  8. The committed config resolves every wire target to a live desk.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
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

from engine.marketing import hot_tape as HT  # noqa: E402
from engine.marketing import wire_routing as WR  # noqa: E402
from engine.marketing import press_lane as PL  # noqa: E402
from engine.marketing.press_lane import run_press_tick  # noqa: E402

_MARKET_HOURS = datetime(2026, 7, 27, 16, 0, 0, tzinfo=timezone.utc)  # Mon, ET pm


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — real-shaped mirror items, one per event_class the router splits on
# ─────────────────────────────────────────────────────────────────────────────

#: (headline, resolved event_class). Every one is a direct-quote on a mirror
#: tier, so the corroboration gate returns "instant" and the ONLY thing left
#: between the item and an emission is the budget under test.
_POLICY = "Trump announces {n}0% tariff on Chinese semiconductors and chip tools"
_COMPANY = "Apple reports record quarterly revenue number {n} and raises guidance"


def _item(iid: str, headline: str) -> dict:
    return {
        "id": iid,
        "source": "trumpstruth",
        "source_name": "Truth Social (via trumpstruth.org)",
        "source_tier": "mirror",
        "url": f"https://truthsocial.com/@realDonaldTrump/{iid}",
        "published_at": "2026-07-27T15:30:00Z",
        "headline": headline,
        "body_snippet": headline,
        "corroboration_class": "direct-quote",
        "truth_status_id": iid,
        "author": "Donald J. Trump",
    }


def _items(*, policy: int = 0, company: int = 0) -> list[dict]:
    out = [_item(f"pol{n}", _POLICY.format(n=n + 1)) for n in range(policy)]
    out += [_item(f"com{n}", _COMPANY.format(n=n + 1)) for n in range(company)]
    return out


def _desk(acct_id: str, *, enabled: bool = True, created: str = "2026-01-01") -> dict:
    return {"id": acct_id, "kind": "branded", "enabled": enabled, "created": created}


def _cfg(*, classes: dict, accounts: list[dict], default: str = "flagship",
         spill: list[str] | None = None, ramp: dict | None = None) -> dict:
    block: dict = {"default": default, "classes": classes}
    if spill is not None:
        block["spill_accounts"] = spill
    cfg: dict = {
        "breaking": {"llm": {"enabled": False}},
        "wire_routing": block,
        "desk_network": {"accounts": accounts},
    }
    if ramp is not None:
        cfg["sentinel"] = {"ramp": ramp}
    return cfg


def _press_cfg(top_k: int | None = None, floor: float = 40.0) -> dict:
    wire: dict = {"flagship_salience_floor": floor}
    if top_k is not None:
        wire["flagship_top_k_per_day"] = top_k
    return {"satire_blocklist": [], "wire": wire}


def _tick(items, cfg, press_cfg, tmp_path, state=None):
    st = {} if state is None else state
    res = run_press_tick(items, root=tmp_path, now=_MARKET_HOURS, cfg=cfg,
                         press_cfg=press_cfg, state=st, seen_ids=set(),
                         dry_run=True, llm_override=lambda i, c: None)
    return res, st


def _accounts(res) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in res["emitted"]:
        out[item["account"]] = out.get(item["account"], 0) + 1
    return out


@pytest.fixture(autouse=True)
def _reset_process_warning_sets():
    """Both once-per-process announcement sets, cleared around every test.

    They exist so a 90-second daemon does not print the same line 1,000 times a
    day; left dirty across tests they make a capsys assertion pass or fail on
    TEST ORDER, which is how a guard starts lying.
    """
    PL.reset_spill_warnings()
    WR.reset_dark_route_warnings()
    HT.reset_dark_account_warnings()
    yield
    PL.reset_spill_warnings()
    WR.reset_dark_route_warnings()
    HT.reset_dark_account_warnings()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Config resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestTopKResolution:
    def test_breaking_block_outranks_press_sources_wire(self):
        assert PL._resolve_top_k({"flagship_top_k_per_day": 7},
                                 {"flagship_top_k_per_day": 3}) == 7

    def test_wire_block_used_when_breaking_is_silent(self):
        assert PL._resolve_top_k({}, {"flagship_top_k_per_day": 4}) == 4

    def test_code_default_when_neither_config_speaks(self):
        assert PL._resolve_top_k({}, {}) == PL._DEFAULT_FLAGSHIP_TOP_K
        assert PL._resolve_top_k(None, None) == PL._DEFAULT_FLAGSHIP_TOP_K

    def test_zero_is_honoured_as_a_deliberate_stop(self):
        # 0 is a real answer ("book nothing"), NOT missing-config. Falling
        # through to the default here would re-arm a lane an operator stopped.
        assert PL._resolve_top_k({"flagship_top_k_per_day": 0}, {}) == 0

    def test_junk_is_ignored_and_announced_at_line_start(self, capsys):
        got = PL._resolve_top_k({"flagship_top_k_per_day": "lots"},
                                {"flagship_top_k_per_day": 5})
        assert got == 5, "junk must fall THROUGH to the next source, not to 0"
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-top-k-invalid" in ln]
        assert lines, "a mistyped cap must not be silent"
        # HOUSE LAW: a GitHub annotation must start the line. Emitted through a
        # logger it reads as an alarm in review and produces nothing in the
        # Actions summary — that shipped dead five times before #3587.
        assert all(ln.startswith("::warning title=press-lane-top-k-invalid::")
                   for ln in lines)

    def test_negative_is_ignored_not_treated_as_unlimited(self, capsys):
        assert PL._resolve_top_k({"flagship_top_k_per_day": -1}, {}) == \
            PL._DEFAULT_FLAGSHIP_TOP_K
        assert "press-lane-top-k-invalid" in capsys.readouterr().out

    def test_default_cannot_exceed_the_committed_flagship_ramp_cap(self):
        """The wire may never be licensed to spend a desk's whole day.

        The ramp cap is the operator's declared daily volume for a desk, and the
        nightly ladder plus the publish-time lanes draw from the same number. A
        code default at or above it would mean a busy news day could leave every
        other lane with no desk to post to.
        """
        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        cap = (((cfg.get("sentinel") or {}).get("ramp") or {})
               .get("account_overrides", {}).get("flagship", {})
               .get("max_posts_per_account_per_day"))
        assert isinstance(cap, int) and cap > 0, "flagship ramp cap moved shape"
        assert PL._DEFAULT_FLAGSHIP_TOP_K < cap, (
            f"wire default {PL._DEFAULT_FLAGSHIP_TOP_K} would claim the whole "
            f"{cap}/day flagship ramp cap")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Per-desk budgets  (MUTATION TARGET)
# ─────────────────────────────────────────────────────────────────────────────

class TestPerDeskBudget:
    def test_two_desks_do_not_share_one_counter(self, tmp_path):
        """MUTATION: charge one shared counter instead of `day_counts[account]`
        (i.e. restore the pre-W4d global `counter["count"] >= top_k`) and this
        goes RED — the total collapses from 4 to 2.

        This is the defect the XG-W2 TODO recorded: arming the wire desk under
        the old shape would have made it SUBTRACT from the flagship's budget
        rather than add to the network's.
        """
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        res, state = _tick(_items(policy=3, company=3), cfg, _press_cfg(2), tmp_path)
        assert _accounts(res) == {"flagship": 2, "news": 2}
        assert len(res["emitted"]) == 4
        assert state["wire_day_counts"]["counts"] == {"flagship": 2, "news": 2}

    def test_flagship_counter_still_tracks_the_primary_desk_only(self, tmp_path):
        """The committed cursors.json contract survives the per-desk split.

        tests/test_marketing_press_wire.py asserts `flagship_counter` survives
        the state-ceiling trim; it must keep meaning "the primary desk's count",
        not "everything the network emitted".
        """
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        res, state = _tick(_items(policy=3, company=3), cfg, _press_cfg(2), tmp_path)
        assert state["flagship_counter"]["count"] == 2
        assert len(res["emitted"]) == 4

    _COLD_RAMP = {
        "graduate_after_days": 56,
        "weeks_1_2": {"max_posts_per_account_per_day": 1},
        "account_overrides": {"flagship": {"max_posts_per_account_per_day": 20}},
    }

    def test_ramp_cap_bounds_a_cold_desk_below_the_wire_budget(self, tmp_path):
        """A cold desk keeps its ramp cap even when the wire budget is wider.

        Press items are scheduled_at="immediate" and an immediate item is exempt
        from the per-account daily cap downstream, so this is the ONLY place the
        ramp reaches them. MUTATION: drop the `min(top_k, cap)` in `_budget` and
        the cold desk emits 3 instead of 1.
        """
        cfg = _cfg(
            classes={"company_news": "cold"},
            accounts=[_desk("cold", created="2026-07-26")],
            default="cold", ramp=self._COLD_RAMP,
        )
        res, state = _tick(_items(company=3), cfg, _press_cfg(5), tmp_path)
        assert _accounts(res) == {"cold": 1}, "the ramp cap must bound the wire"
        assert state["wire_headroom"]["exhausted"] == 2

    def test_a_ramp_capped_desk_spills_rather_than_drops(self, tmp_path):
        """The cap moves the surplus; it does not destroy it. The cold desk takes
        its 1, and the other 2 go to the warmed desk that still has budget."""
        cfg = _cfg(
            classes={"policy": "flagship", "company_news": "cold"},
            accounts=[_desk("flagship"), _desk("cold", created="2026-07-26")],
            ramp=self._COLD_RAMP,
        )
        res, state = _tick(_items(policy=3, company=3), cfg, _press_cfg(5), tmp_path)
        assert _accounts(res) == {"flagship": 5, "cold": 1}
        assert state["wire_headroom"]["spilled"] == {"cold->flagship": 2}
        assert state["wire_headroom"]["exhausted"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cross-desk spill
# ─────────────────────────────────────────────────────────────────────────────

class TestSpill:
    def test_surplus_crosses_to_another_live_wire_desk(self, tmp_path, capsys):
        """MUTATION: return "" from _pick_spill_account and this goes RED —
        `news` gets 1 instead of 2 and the third policy item is dropped."""
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        res, state = _tick(_items(policy=3, company=1), cfg, _press_cfg(2), tmp_path)
        got = _accounts(res)
        assert got["flagship"] == 2, "the routed desk fills first"
        assert got["news"] == 2, "surplus policy item spilled onto the wire desk"
        assert state["wire_headroom"]["spilled"] == {"flagship->news": 1}
        assert state["wire_headroom"]["exhausted"] == 0

    def test_spill_announces_itself_at_line_start(self, tmp_path, capsys):
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        _tick(_items(policy=3, company=1), cfg, _press_cfg(2), tmp_path)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-wire-spill" in ln]
        assert lines, "a desk publishing another desk's class must not be silent"
        assert all(ln.startswith("::notice title=press-lane-wire-spill::")
                   for ln in lines)

    def test_spill_is_announced_once_per_pair_per_process(self, tmp_path, capsys):
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        _tick(_items(policy=6), cfg, _press_cfg(2), tmp_path)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-wire-spill" in ln]
        assert len(lines) == 1, (
            "the daemon ticks every ~90s; one line per (from,to) pair is the "
            "signal, hundreds bury it")

    def test_spill_charges_the_receiving_desk_not_the_nominal_owner(self, tmp_path):
        """Charging the pre-spill account would leave the receiver uncharged and
        let one exhausted route empty the whole pool."""
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        _, state = _tick(_items(policy=6), cfg, _press_cfg(2), tmp_path)
        assert state["wire_day_counts"]["counts"] == {"flagship": 2, "news": 2}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Who may receive a wire relay
# ─────────────────────────────────────────────────────────────────────────────

class TestSpillPoolMembership:
    def test_a_dark_desk_is_never_a_spill_target(self, tmp_path):
        """The desk exists in desk_network and owns a class — and is DARK. An
        item spilled to it would be enqueued, rendered, paid for, and then
        quarantined at dispatch with reason account_disabled. That is the exact
        grave hot_tape dug 29 times on 2026-07-30/31."""
        cfg = _cfg(classes={"policy": "flagship", "company_news": "dark_desk"},
                   accounts=[_desk("flagship"), _desk("dark_desk", enabled=False)])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship"]
        res, state = _tick(_items(policy=4), cfg, _press_cfg(2), tmp_path)
        assert _accounts(res) == {"flagship": 2}
        assert "dark_desk" not in state["wire_day_counts"]["counts"]

    def test_persona_desks_are_not_eligible_even_when_live(self, tmp_path):
        """§4 safety rails: wire accounts RELAY and never take a stance. An
        enabled persona desk that owns no wire class is not a wire desk, and a
        raw press relay in an authored voice is a charter violation dressed up
        as a volume fix."""
        cfg = _cfg(classes={"policy": "flagship"},
                   accounts=[_desk("flagship"), _desk("meagan"), _desk("sophia")])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship"]
        res, _ = _tick(_items(policy=4), cfg, _press_cfg(2), tmp_path)
        assert set(_accounts(res)) == {"flagship"}

    def test_explicit_spill_accounts_admits_a_desk_that_owns_no_class(self, tmp_path):
        cfg = _cfg(classes={"policy": "flagship"},
                   accounts=[_desk("flagship"), _desk("news")],
                   spill=["flagship", "news"])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship", "news"]
        res, _ = _tick(_items(policy=4), cfg, _press_cfg(2), tmp_path)
        assert _accounts(res) == {"flagship": 2, "news": 2}

    def test_explicit_spill_accounts_cannot_admit_a_dark_desk(self, tmp_path):
        cfg = _cfg(classes={"policy": "flagship"},
                   accounts=[_desk("flagship"), _desk("news", enabled=False)],
                   spill=["flagship", "news"])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship"]

    def test_default_desk_sorts_first_then_alphabetical(self, tmp_path):
        cfg = _cfg(classes={"a": "zulu", "b": "alpha", "c": "flagship"},
                   accounts=[_desk("flagship"), _desk("alpha"), _desk("zulu")])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship", "alpha", "zulu"]

    def test_unknown_liveness_falls_closed_to_the_default_alone(self, monkeypatch,
                                                               tmp_path):
        """`_enabled_accounts` returns None when the accounts model could not be
        consulted. None is NOT "no constraint" — route() already learned that the
        hard way, and spill must give the same answer."""
        monkeypatch.setattr(WR, "_enabled_accounts", lambda cfg, root: None)
        cfg = _cfg(classes={"policy": "flagship", "company_news": "news"},
                   accounts=[_desk("flagship"), _desk("news")])
        assert WR.spill_pool(cfg, root=tmp_path) == ["flagship"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Counted drops
# ─────────────────────────────────────────────────────────────────────────────

class TestCountedDrops:
    def test_exhausted_pool_increments_a_persisted_census(self, tmp_path):
        """MUTATION: delete the `census["exhausted"] += 1` line and this goes RED.

        A `continue` that counts nothing is the defect class that hid twelve
        nights of lost mover posts. This census rides in `state`, and
        scripts/marketing_press_wire.save_cursors writes every non-underscore
        state key into the COMMITTED cursors.json — so the number outlives the
        run that produced it.
        """
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        res, state = _tick(_items(policy=5), cfg, _press_cfg(2), tmp_path)
        assert len(res["emitted"]) == 2
        assert state["wire_headroom"]["exhausted"] == 3
        dropped = [s for s in res["skipped"]
                   if s["reason"] == "flagship_top_k_reached"]
        assert len(dropped) == 3
        # The skip row names the desks and their budgets, so the log line is a
        # diagnosis rather than a count.
        assert "flagship=2/2" in dropped[0]["detail"]

    def test_headroom_alarm_is_printed_at_line_start(self, tmp_path, capsys):
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        _tick(_items(policy=5), cfg, _press_cfg(2), tmp_path)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-wire-headroom" in ln]
        assert len(lines) == 1
        assert lines[0].startswith("::warning title=press-lane-wire-headroom::")
        assert "3 wire item(s)" in lines[0]

    def test_census_accumulates_across_ticks_within_a_day(self, tmp_path):
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        state: dict = {}
        _tick(_items(policy=4), cfg, _press_cfg(2), tmp_path, state=state)
        assert state["wire_headroom"]["exhausted"] == 2
        # A second tick on the same day keeps the budget spent AND keeps counting.
        _tick(_items(policy=2), cfg, _press_cfg(2), tmp_path, state=state)
        assert state["wire_headroom"]["exhausted"] == 4
        assert state["wire_day_counts"]["counts"]["flagship"] == 2

    def test_no_alarm_and_no_census_growth_when_nothing_was_dropped(self, tmp_path,
                                                                   capsys):
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        _, state = _tick(_items(policy=2), cfg, _press_cfg(10), tmp_path)
        assert state["wire_headroom"]["exhausted"] == 0
        assert "press-lane-wire-headroom" not in capsys.readouterr().out

    def test_a_deliberate_stop_counts_but_does_not_shout(self, tmp_path, capsys):
        """top_k=0 is an operator switching the lane off, not a shortage.

        The daemon runs 288 times a day; an alarm on every one of them is how a
        real alarm gets tuned out. The census still records the drops, so the
        evidence survives in cursors.json without the noise.
        """
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        res, state = _tick(_items(policy=3), cfg, _press_cfg(0), tmp_path)
        assert res["emitted"] == []
        assert state["wire_headroom"]["exhausted"] == 3
        assert "press-lane-wire-headroom" not in capsys.readouterr().out

    def test_day_rollover_resets_budgets_and_census(self, tmp_path):
        cfg = _cfg(classes={"policy": "flagship"}, accounts=[_desk("flagship")])
        state: dict = {}
        _tick(_items(policy=4), cfg, _press_cfg(2), tmp_path, state=state)
        assert state["wire_headroom"]["exhausted"] == 2
        run_press_tick(_items(policy=2), root=tmp_path,
                       now=_MARKET_HOURS.replace(day=28), cfg=cfg,
                       press_cfg=_press_cfg(2), state=state, seen_ids=set(),
                       dry_run=True, llm_override=lambda i, c: None)
        assert state["wire_headroom"]["exhausted"] == 0
        assert state["wire_day_counts"]["counts"] == {"flagship": 2}


# ─────────────────────────────────────────────────────────────────────────────
# 6. hot_tape.live_account — the account_disabled class
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveAccountRescue:
    """29 items on 2026-07-30/31 were rendered, phrased, uploaded, enqueued and
    then quarantined at dispatch with reason `account_disabled` — every one of
    them hot_tape lane, every one addressed to mastermind_news. `live_account`
    is the fix; these pin it against a config where the target is dark, so the
    guard keeps meaning something after the desk is armed.
    """

    def _dark_cfg(self):
        return {"desk_network": {"accounts": [
            _desk("flagship"), _desk("wire_desk", enabled=False)]},
            "wire_routing": {"default": "flagship"}}

    def test_dark_target_is_rescued_to_a_live_desk(self):
        got = HT.live_account("wire_desk", marketing_cfg=self._dark_cfg(),
                              fallbacks=("flagship", "wire_desk"))
        assert got == "flagship"

    def test_rescue_announces_itself_at_line_start(self, capsys):
        HT.live_account("wire_desk", marketing_cfg=self._dark_cfg(),
                        fallbacks=("flagship", "wire_desk"))
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "hot-tape-dark-account" in ln]
        assert lines, "a lane posting as a different desk than its config names"
        assert all(ln.startswith("::warning title=hot-tape-dark-account::")
                   for ln in lines)
        assert "account_disabled" in lines[0], (
            "the annotation must name the quarantine reason it prevents, or the "
            "operator cannot connect it to the graves in the ledger")

    def test_a_live_target_is_returned_untouched_and_silently(self, capsys):
        assert HT.live_account("flagship", marketing_cfg=self._dark_cfg()) == "flagship"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_rescue_never_lands_on_another_dark_desk(self):
        cfg = {"desk_network": {"accounts": [
            _desk("flagship"), _desk("dark_a", enabled=False),
            _desk("dark_b", enabled=False)]},
            "wire_routing": {"default": "dark_b"}}
        got = HT.live_account("dark_a", marketing_cfg=cfg,
                              fallbacks=("dark_b", "dark_a"))
        assert got == "flagship", "every fallback rung must be liveness-checked"

    def test_committed_config_routes_hot_tape_to_live_desks(self):
        """The two desks config/hot_tape.yml addresses must both resolve live.

        Deliberately NOT pinned to a named account: W4f arms mastermind_news, so
        an assertion that it is dark would invert the day it ships. The invariant
        that survives either way is "whatever hot_tape addresses, resolves to a
        desk the accounts model says is armed".
        """
        mcfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        ht_cfg = HT.load_config(ROOT)
        live = WR._enabled_accounts(mcfg, ROOT)
        assert live, "the committed config must resolve at least one live desk"
        for key in ("emit.account", "emit.flagship_account"):
            target = str(HT._c(ht_cfg, key, ""))
            assert target, f"hot_tape {key} is unset"
            resolved = HT.live_account(target, marketing_cfg=mcfg, root=ROOT,
                                       fallbacks=("flagship",))
            assert resolved in live, (
                f"hot_tape {key}={target!r} resolves to {resolved!r}, which the "
                f"accounts model does not report as enabled — items addressed "
                f"there quarantine at dispatch with reason account_disabled")


# ─────────────────────────────────────────────────────────────────────────────
# 7. The committed config, end to end
# ─────────────────────────────────────────────────────────────────────────────

class TestCommittedConfig:
    def test_every_wire_class_owner_is_live_and_spill_eligible(self):
        mcfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        pool = WR.spill_pool(mcfg, root=ROOT)
        assert pool, "the committed config resolves no live wire desk at all"
        table = WR.routing_table(mcfg, root=ROOT)
        for klass, acct in table.items():
            assert acct in pool, (
                f"class {klass!r} routes to {acct!r}, which is not in the spill "
                f"pool {pool} — its surplus would have nowhere to go")

    def test_committed_top_k_is_a_usable_budget(self):
        mcfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        pcfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
        top_k = PL._resolve_top_k(mcfg.get("breaking"), (pcfg or {}).get("wire"))
        assert top_k > 0, "the committed config books nothing"
        # The two homes must not disagree in a way that makes the file a lie:
        # press_sources' value is documented as the one the breaking block
        # overrides, so a reader comparing them should see the same number.
        wire_value = (pcfg.get("wire") or {}).get("flagship_top_k_per_day")
        breaking_value = (mcfg.get("breaking") or {}).get("flagship_top_k_per_day")
        if wire_value is not None and breaking_value is not None:
            assert wire_value == breaking_value, (
                "config/press_sources.yml and config/marketing.yml both declare "
                "flagship_top_k_per_day and they disagree; the breaking block "
                "wins, so the press_sources value is documentation that lies")
