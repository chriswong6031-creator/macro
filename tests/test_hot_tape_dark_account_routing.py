"""The hot-tape wire desk routed most of its volume to a DARK account — and the
first fix for that then routed it onto the BRAND account.

ROUND ONE (2026-07-31). `hot_tape.severity_account` sends every sub-85 event to
`emit.account`, whose in-code default is `mastermind_news`. While that desk was
dark the pipeline ran in full for each of those events — a Chrome raster, an R2
upload, an LLM phrasing call, an outbox enqueue — and then the publisher's
dispatch-time park quarantined it with reason `account_disabled`. 19 items died
that way on 2026-07-31 alone. `live_account` was added as the liveness step at
the booking seam, where `marketing_cfg` (and therefore `desk_network`) is
actually in hand, and it RESCUED those items onto the first armed fallback.

ROUND TWO (W5, 2026-08-03) — THE RESCUE WAS THE PROBLEM. The only desk with room
to take a rescued firehose is the flagship, so one `desk_network` switch
silently made @mastermindx001 the destination for the whole tape. The operator's
measured view of that: 11 kind=breaking items on the brand account in one day,
four of them from a single John Williams appearance inside an hour, at 2, 2, 2
and 1 views. A grave is a cost; a firehose on the brand account is a product
failure, and between the two the grave is cheaper.

So the rescue is now OPT-IN (`wire_routing.dark_desk.policy: redirect`) plus a
high-severity single-event hatch that is OFF, and the default is to PARK: the
item keeps its owner's address, `wire_routing` counts it and announces it once,
and the dispatch-time park records it where the admin can see it. This file now
pins BOTH halves — that the redirect still works when asked for, and that it is
not what happens by default.

`severity_account` is untouched throughout: it answers "which desk owns this
event" from config alone, and an emitter that consulted desk_network there would
rewrite the routing table every time an operator flipped a switch.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import engine.marketing.hot_tape as HT

#: A root with no outbox. `live_account` weighs the per-account rolling
#: kind=breaking ceiling since W5 and defaults to the REPO root, so a rootless
#: call here would read the committed queue and make these liveness assertions
#: depend on how much the wire posted today.
EMPTY = Path(tempfile.mkdtemp(prefix="hot-tape-dark-empty-"))


def _cfg(*, flagship_on: bool = True, news_on: bool = False,
         extra: list[dict] | None = None) -> dict:
    """A marketing.yml-shaped cfg with a desk_network roster."""
    accounts = [
        {"id": "flagship", "enabled": flagship_on},
        {"id": "mastermind_news", "enabled": news_on},
    ]
    accounts.extend(extra or [])
    return {"desk_network": {"accounts": accounts},
            "wire_routing": {"default": "flagship"}}


@pytest.fixture(autouse=True)
def _reset_warnings():
    HT.reset_dark_account_warnings()
    yield
    HT.reset_dark_account_warnings()


class TestDarkTargetParksLoudly:
    """W5 INVERTED THE FIRST ASSERTION HERE. It used to read
    `assert got == "flagship"` — the rescue — and that is the line that made the
    brand account inherit the tape firehose."""

    def test_the_dark_wire_desk_keeps_its_own_items(self, capsys):
        got = HT.live_account("mastermind_news", marketing_cfg=_cfg(), root=EMPTY,
                              fallbacks=("flagship", "mastermind_news"))
        assert got == "mastermind_news", (
            "the flagship inherited a dark wire desk's volume — one switch flip "
            "away from being a print ticker")

    def test_the_park_is_announced_at_line_start(self, capsys):
        HT.live_account("mastermind_news", marketing_cfg=_cfg(), root=EMPTY,
                        fallbacks=("flagship",))
        out = capsys.readouterr().out
        line = next((l for l in out.splitlines()
                     if l.startswith("::warning title=wire-routing-parked::")), "")
        assert line, out
        # House law: a logger prefix makes GitHub drop the annotation entirely,
        # so it must START the line. It has to name the desk AND the quarantine
        # reason, or the operator cannot connect it to the parked items.
        assert "mastermind_news" in line and "account_disabled" in line, line

    def test_it_warns_once_per_process_not_once_per_item(self, capsys):
        """The radar ticks every five minutes and books up to three items a
        pass. Warning per item buries the Actions summary it exists to fill."""
        for _ in range(5):
            HT.live_account("mastermind_news", marketing_cfg=_cfg(), root=EMPTY,
                            fallbacks=("flagship",))
        out = capsys.readouterr().out
        hits = [l for l in out.splitlines()
                if l.startswith("::warning title=wire-routing-parked::")]
        assert len(hits) == 1, hits

    def test_the_redirect_is_still_there_when_config_asks_for_it(self, capsys):
        cfg = _cfg()
        cfg["wire_routing"]["dark_desk"] = {"policy": "redirect"}
        got = HT.live_account("mastermind_news", marketing_cfg=cfg, root=EMPTY,
                              fallbacks=("flagship",))
        assert got == "flagship"
        assert "::warning title=wire-routing-dark::" in capsys.readouterr().out


class TestTheConfigOverrideStillWorks:
    def test_an_enabled_target_is_returned_untouched_and_silently(self, capsys):
        got = HT.live_account("mastermind_news", root=EMPTY,
                              marketing_cfg=_cfg(news_on=True),
                              fallbacks=("flagship",))
        assert got == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_operator_pointing_emit_account_at_a_third_live_desk_is_honoured(self):
        cfg = _cfg(extra=[{"id": "crypto_desk", "enabled": True}])
        assert HT.live_account("crypto_desk", marketing_cfg=cfg, root=EMPTY,
                               fallbacks=("flagship",)) == "crypto_desk"

    def test_routing_itself_is_unchanged(self):
        """`severity_account` stays PURE — it answers ownership, never liveness.

        An emitter that consulted desk_network there would rewrite the routing
        table every time an operator flipped a switch, and the config would stop
        describing the system.
        """
        from engine.marketing.hot_tape import FactPacket

        packet = FactPacket(
            trigger="mover_drop", key="k", fired_at="2026-07-31T15:00:00Z",
            session="rth", ticker="MU", name=None, sector=None, direction="down",
            severity=80.0, facts={"pct": -9.0}, provenance={},
        )
        assert HT.severity_account(packet, HT.DEFAULTS) == "mastermind_news"


class TestUnknownLivenessIsNotEvidenceOfDarkness:
    """Three answers, not two — the mistake wire_routing's own `_enabled_accounts`
    documents. Rerouting a correctly-configured desk's volume because an import
    failed, or because a test fixture carries no roster, is a silent redirection:
    a worse fault than the one being fixed, and invisible."""

    def test_no_desk_network_roster_leaves_the_target_alone(self, capsys):
        assert HT.live_account("mastermind_news", marketing_cfg={},
                               root=EMPTY) == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_unconsultable_accounts_model_leaves_the_target_alone(
            self, monkeypatch, capsys):
        from engine.marketing import wire_routing as WR

        monkeypatch.setattr(WR, "_enabled_accounts",
                            lambda cfg, root: None)
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                               root=EMPTY) == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_all_dark_roster_leaves_the_target_alone(self, capsys):
        """Nothing to fall back TO. Inventing a destination would be worse than
        letting the dispatch-time park report it honestly."""
        cfg = _cfg(flagship_on=False, news_on=False)
        assert HT.live_account("mastermind_news", marketing_cfg=cfg,
                               root=EMPTY) == "mastermind_news"

    def test_it_never_raises(self, monkeypatch):
        from engine.marketing import wire_routing as WR

        def _boom(cfg, root):
            raise RuntimeError("accounts model exploded")

        monkeypatch.setattr(WR, "_enabled_accounts", _boom)
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                               root=EMPTY) == "mastermind_news"


class TestTheBookingPathActuallyCallsIt:
    """A resolver nothing invokes is the grave with extra steps."""

    def test_the_alert_loop_resolves_liveness(self):
        import inspect

        import scripts.hot_tape_radar as RADAR

        src = inspect.getsource(RADAR.emit)
        # TWO call sites: the alert loop and the two-step brief loop. The brief
        # inherits its alert's account and falls back to the same hardcoded
        # `emit.account` in pending_briefs, so covering only the first would
        # leave the second half of every two-step publish going to a grave.
        # AST, not src.count(): a string count is satisfied by a comment and
        # broken by a legitimate refactor — same reasoning as the
        # phrase_or_fallback scan in test_marketing_hot_tape_radar.py.
        import ast
        import textwrap
        tree = ast.parse(textwrap.dedent(src))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "live_account"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "HT"
        ]
        assert len(calls) == 2, f"expected 2 HT.live_account call sites, found {len(calls)}"

    def test_a_sub_85_event_does_not_land_on_the_brand_desk(self, tmp_path,
                                                            capsys, monkeypatch):
        """END TO END through emit(). W5 INVERTED WHAT THIS ASSERTS.

        `book_packet` is stubbed because the real one rasters a card and calls
        an LLM — neither is the thing under test. What IS under test is the
        account emit() hands it. Round one asserted `["flagship"]`: the rescue.
        Round two asserts it is NOT flagship, because that rescue is exactly how
        every sub-85 tape event — most of the lane's volume — became brand-account
        volume the moment the wire desk was switched off. The item goes to the
        desk that owns it and parks at dispatch, which is a cost the operator
        chose over a print ticker.
        """
        from datetime import datetime, timezone

        import scripts.hot_tape_radar as RADAR

        seen: list[str] = []

        def _fake_book(packet, *, account, **kw):
            seen.append(account)
            return {"status": "would_book", "item_id": None, "text": "x"}

        packet = HT.FactPacket(
            trigger="mover_drop", key="mover:MU:down:2026-07-31:0",
            fired_at="2026-07-31T15:00:00Z", session="rth", ticker="MU",
            name=None, sector=None, direction="down", severity=80.0,
            facts={"pct": -9.0}, provenance={},
        )
        monkeypatch.setattr(RADAR, "book_packet", _fake_book)
        RADAR.emit(
            [packet], root=tmp_path, cfg=HT.load_config(tmp_path),
            marketing_cfg=_cfg(),          # flagship live, news DARK
            fired_today=[], now=datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc),
            as_of="2026-07-31", demo=False, dry_run=True,
        )

        assert seen == ["mastermind_news"], (
            f"a sub-85 event was booked to {seen} — a dark wire desk's volume "
            "must park on that desk, never be donated to the brand account")
        assert "flagship" not in seen
        out = capsys.readouterr().out
        assert "::warning title=wire-routing-parked::" in out

    def test_the_shipped_config_default_is_a_dark_desk(self):
        """The premise of this whole file, asserted rather than assumed.

        If mastermind_news is ever armed this test flips and the fallback goes
        quiet on its own — which is the correct outcome, not a broken test.
        """
        import yaml
        from pathlib import Path

        from engine.marketing.accounts import effective_accounts

        repo = Path(__file__).resolve().parent.parent
        cfg = yaml.safe_load((repo / "config" / "marketing.yml").read_text(
            encoding="utf-8")) or {}
        live = {a["id"] for a in effective_accounts(cfg, repo) if a.get("enabled")}
        assert live, "desk_network resolved zero accounts — the roster moved"
        assert HT.DEFAULTS["emit"]["account"] == "mastermind_news"
        if "mastermind_news" in live:
            pytest.skip("mastermind_news is armed — the fallback is now inert")
        assert HT.live_account("mastermind_news", marketing_cfg=cfg,
                               root=repo, fallbacks=("flagship",)) in live
