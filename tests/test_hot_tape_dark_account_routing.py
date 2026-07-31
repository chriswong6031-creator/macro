"""The hot-tape wire desk routed most of its volume to a DARK account.

`hot_tape.severity_account` sends every sub-85 event to `emit.account`, whose
in-code default is `mastermind_news` — an account that is wired-but-DISABLED in
`desk_network` on purpose. So the pipeline ran in full for each of those events:
a Chrome raster, an R2 upload, an LLM phrasing call, an outbox enqueue — and
then the publisher's dispatch-time dark-desk park quarantined it with reason
`account_disabled`. 19 items died that way on 2026-07-31 alone.

`engine/marketing/wire_routing.py` exists precisely to stop this ("LIVENESS IS
NOT ROUTING … a class routed to a disabled account falls back to the default
with a start-of-line ::warning"). The hot-tape lane simply never called it.

The fix keeps ROUTING pure — `severity_account` still answers "which desk owns
this event" from config alone — and adds `live_account` as the separate liveness
step at the booking seam, where `marketing_cfg` (and therefore `desk_network`)
is actually in hand.
"""
from __future__ import annotations

import pytest

import engine.marketing.hot_tape as HT


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


class TestDarkTargetFallsBackLoudly:
    def test_the_dark_wire_desk_falls_back_to_an_enabled_one(self, capsys):
        got = HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                              fallbacks=("flagship", "mastermind_news"))
        assert got == "flagship"

    def test_the_fallback_is_announced_at_line_start(self, capsys):
        HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                        fallbacks=("flagship",))
        out = capsys.readouterr().out
        line = next((l for l in out.splitlines()
                     if l.startswith("::warning title=hot-tape-dark-account::")), "")
        assert line, out
        # House law: a logger prefix makes GitHub drop the annotation entirely,
        # so it must START the line. Both account names have to be in it — the
        # operator needs the intent AND the fact that it is not in force.
        assert "mastermind_news" in line and "flagship" in line, line

    def test_it_warns_once_per_process_not_once_per_item(self, capsys):
        """The radar ticks every five minutes and books up to three items a
        pass. Warning per item buries the Actions summary it exists to fill."""
        for _ in range(5):
            HT.live_account("mastermind_news", marketing_cfg=_cfg(),
                            fallbacks=("flagship",))
        out = capsys.readouterr().out
        hits = [l for l in out.splitlines()
                if l.startswith("::warning title=hot-tape-dark-account::")]
        assert len(hits) == 1, hits


class TestTheConfigOverrideStillWorks:
    def test_an_enabled_target_is_returned_untouched_and_silently(self, capsys):
        got = HT.live_account("mastermind_news",
                              marketing_cfg=_cfg(news_on=True),
                              fallbacks=("flagship",))
        assert got == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_operator_pointing_emit_account_at_a_third_live_desk_is_honoured(self):
        cfg = _cfg(extra=[{"id": "crypto_desk", "enabled": True}])
        assert HT.live_account("crypto_desk", marketing_cfg=cfg,
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
        assert HT.live_account("mastermind_news", marketing_cfg={}) == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_unconsultable_accounts_model_leaves_the_target_alone(
            self, monkeypatch, capsys):
        from engine.marketing import wire_routing as WR

        monkeypatch.setattr(WR, "_enabled_accounts",
                            lambda cfg, root: None)
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg()) == "mastermind_news"
        assert "hot-tape-dark-account" not in capsys.readouterr().out

    def test_an_all_dark_roster_leaves_the_target_alone(self, capsys):
        """Nothing to fall back TO. Inventing a destination would be worse than
        letting the dispatch-time park report it honestly."""
        cfg = _cfg(flagship_on=False, news_on=False)
        assert HT.live_account("mastermind_news", marketing_cfg=cfg) == "mastermind_news"

    def test_it_never_raises(self, monkeypatch):
        from engine.marketing import wire_routing as WR

        def _boom(cfg, root):
            raise RuntimeError("accounts model exploded")

        monkeypatch.setattr(WR, "_enabled_accounts", _boom)
        assert HT.live_account("mastermind_news", marketing_cfg=_cfg()) == "mastermind_news"


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
        assert src.count("HT.live_account(") == 2, src.count("HT.live_account(")

    def test_a_sub_85_event_books_on_an_ENABLED_desk(self, tmp_path, capsys,
                                                     monkeypatch):
        """END TO END through emit(), which is where the grave was dug.

        `book_packet` is stubbed because the real one rasters a card and calls
        an LLM — neither is the thing under test. What IS under test is the
        account emit() hands it, which on the old code was `mastermind_news`
        for every sub-85 event: rendered, phrased, uploaded, enqueued, then
        quarantined at dispatch with account_disabled.
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

        assert seen == ["flagship"], (
            f"a sub-85 event was booked to {seen} — the wire desk is dark and "
            "every one of those items dies at dispatch with account_disabled")
        assert "::warning title=hot-tape-dark-account::" in capsys.readouterr().out

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
