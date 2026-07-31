"""Publish-lane throughput + media recovery (2026-07-28).

Pins the two defects that made the desk network publish NOTHING on a day it had
a full queue, and the fix for each:

  1. THROUGHPUT WAS THE CRON GRID. An item inside the global spacing floor was
     deferred to the next sweep, so 30 sweeps/day capped the network at 30
     posts/day regardless of what the desks generated or the caps allowed. The
     fix books it forward at the moment the floor clears (Buffer schedules it)
     instead — same spacing, decoupled from the grid. Bounded by a horizon
     because every item is tape-verified at BOOK time.

  2. A CHART URL COULD ONLY BE STAMPED ONCE. media_url is written inside the
     nightly's content_studio build and only when R2 creds are live in that
     process; a miss shipped the day text-only with no way back. The publisher
     now falls back to the append-only backfill sidecar.

Stdlib-only (thin CI lane): no pandas, no network, no Chrome.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. Forward-booking horizon config
# ─────────────────────────────────────────────────────────────────────────────

class TestForwardBookHorizonCfg:
    @pytest.mark.parametrize("raw,expected", [
        ({}, 0),                              # absent → off (old behaviour)
        ({"max_forward_book_min": 0}, 0),     # explicit off
        ({"max_forward_book_min": -5}, 0),    # negative is not "unlimited"
        ({"max_forward_book_min": "nonsense"}, 0),
        ({"max_forward_book_min": None}, 0),
        ({"max_forward_book_min": 60}, 60),
        ({"max_forward_book_min": "45"}, 45),  # YAML may hand back a string
    ])
    def test_parsed_strictly(self, raw, expected):
        from scripts.marketing_publisher import _forward_book_horizon_cfg
        assert _forward_book_horizon_cfg(raw) == expected

    def test_shipped_config_enables_it_within_the_tape_gate_window(self):
        """The horizon is a TAPE-FRESHNESS bound: a booked item is verified when
        it is booked, not when it sends. Keep it near the live gate's own quote
        age limit — this test fails loudly if someone raises it to drain the
        queue faster and silently starts shipping stale reads."""
        import yaml
        from pathlib import Path

        cfg_path = Path(__file__).resolve().parent.parent / "config" / "marketing.yml"
        pub = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["publish"]
        horizon = int(pub["max_forward_book_min"])
        quote_age = int(pub["live_gate"]["max_quote_age_min"])
        assert horizon > 0, "forward booking off → throughput is back on the cron grid"
        assert horizon <= quote_age * 2, (
            f"horizon {horizon}m is more than 2x the {quote_age}m quote-age limit; "
            "a booked post would send against a tape far older than it claims"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Forward booking preserves the spacing floor
# ─────────────────────────────────────────────────────────────────────────────

class TestForwardBookingSpacing:
    """The floor's guarantee is 'no two posts closer than N minutes'. Booking
    forward must reproduce it exactly — it changes WHEN the slot is reserved,
    never how far apart the sends land."""

    def test_booked_times_are_never_closer_than_the_floor(self):
        from scripts.marketing_publisher import _post_jitter_minutes, _within_floor

        floor_min, jitter_max, horizon = 10, 7, 60
        now = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
        last_post_at = now - timedelta(minutes=2)   # deep inside the floor

        booked: list[datetime] = []
        for i in range(6):
            iid = f"item-{i}"
            if _within_floor(last_post_at, now, floor_min):
                floor_clear_at = last_post_at + timedelta(minutes=floor_min)
                ahead = int((floor_clear_at - now).total_seconds() // 60)
                if ahead > horizon:
                    break
            else:
                floor_clear_at = now
            at = floor_clear_at + timedelta(minutes=_post_jitter_minutes(iid, jitter_max))
            booked.append(at)
            last_post_at = at

        assert len(booked) > 1, "one sweep still books only a single item"
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(booked, booked[1:])]
        assert all(g >= floor_min for g in gaps), f"floor violated: {gaps}"

    def test_horizon_bounds_how_far_ahead_one_sweep_reaches(self):
        """Past the horizon the item must fall back to the old defer path —
        otherwise a sweep books the whole day against one moment's tape."""
        from scripts.marketing_publisher import _within_floor

        floor_min, horizon = 10, 60
        now = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
        last_post_at = now                        # floor clears at now+10

        booked = 0
        while True:
            if not _within_floor(last_post_at, now, floor_min):
                break
            floor_clear_at = last_post_at + timedelta(minutes=floor_min)
            if int((floor_clear_at - now).total_seconds() // 60) > horizon:
                break
            last_post_at = floor_clear_at
            booked += 1

        assert booked == horizon // floor_min, (
            f"a sweep booked {booked} items; the {horizon}m horizon at a "
            f"{floor_min}m floor allows exactly {horizon // floor_min}"
        )
        assert (last_post_at - now) <= timedelta(minutes=horizon)

    def test_horizon_zero_is_the_old_defer_path(self):
        """0 must be a true off-switch: with it, an item inside the floor is
        never booked — it defers, exactly as before this feature."""
        from scripts.marketing_publisher import _within_floor

        floor_min, horizon = 10, 0
        now = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
        last_post_at = now - timedelta(minutes=1)

        assert _within_floor(last_post_at, now, floor_min)
        # The production branch is `if horizon <= 0 or ahead > horizon: defer`.
        assert horizon <= 0, "guard must short-circuit before any booking math"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Media sidecar fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestMediaSidecarFallback:
    PUB_CFG = {"media_enabled": True}

    def test_item_with_its_own_url_ignores_the_sidecar(self):
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28",
              "media": [{"chart_id": "chart-001",
                         "media_url": "https://cdn.example/real.png"}]}
        sidecar = {"2026-07-28/chart-001": "https://cdn.example/WRONG.png"}
        assert _media_paths_for(it, self.PUB_CFG, sidecar) == \
            ["https://cdn.example/real.png"]

    def test_unstamped_item_recovers_its_url_from_the_sidecar(self):
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28", "media": [{"chart_id": "chart-001"}]}
        sidecar = {"2026-07-28/chart-001": "https://cdn.example/recovered.png"}
        assert _media_paths_for(it, self.PUB_CFG, sidecar) == \
            ["https://cdn.example/recovered.png"]

    def test_no_sidecar_is_text_only_not_a_crash(self):
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28", "media": [{"chart_id": "chart-001"}]}
        assert _media_paths_for(it, self.PUB_CFG, None) == []
        assert _media_paths_for(it, self.PUB_CFG, {}) == []

    def test_sidecar_never_overrides_the_media_enabled_gate(self):
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28", "media": [{"chart_id": "chart-001"}]}
        sidecar = {"2026-07-28/chart-001": "https://cdn.example/recovered.png"}
        assert _media_paths_for(it, {"media_enabled": False}, sidecar) == []

    def test_non_http_sidecar_value_is_refused(self):
        """A local path in the sidecar must never reach Buffer — it would render
        as a broken attachment rather than degrade to text."""
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28", "media": [{"chart_id": "chart-001"}]}
        sidecar = {"2026-07-28/chart-001": "data/marketing/outbox/media/x.png"}
        assert _media_paths_for(it, self.PUB_CFG, sidecar) == []


# ─────────────────────────────────────────────────────────────────────────────
# 3b. A ticker post must carry its chart
# ─────────────────────────────────────────────────────────────────────────────

def _signal_item(**over):
    """A real emitted signal row (shape copied from data/marketing/outbox/
    items.jsonl): the ticker lives in `source`, NOT at the top level."""
    it = {
        "id": "itm-0001",
        "kind": "signal",
        "as_of": "2026-07-28",
        "account": "w_chris6031",
        "source": {"ticker": "ROST", "chart_id": "chart-001",
                   "direction": "long", "signal_id": "sig-1"},
        "media": [{"kind": "chart_svg", "chart_id": "chart-001", "ticker": "ROST",
                   "path": "data/marketing/outbox/media/2026-07-28/chart-001.svg"}],
        "text": "$ROST back on the board\n\nHeld the anchored VWAP for 13 days.",
    }
    it.update(over)
    return it


class TestTickerPostMustCarryItsChart:
    """The last gap in the illustration chain (operator's standing rule: "we
    should always have illustrations for charting tickers ... we're doing entry
    timing so charting should be used").

    media_url is stamped ONCE, inside the nightly, and only if R2 creds were
    live in that process. Before this gate, any sweep firing between a failed
    upload and marketing_media_backfill.py resolved nothing and posted the read
    BARE to all seven desks — silently, because [] is also the legitimate
    text-only answer for a macro post. The publisher now DEFERS such an item
    (leaves it approved) instead of posting it naked.
    """
    PUB_CFG = {"media_enabled": True}

    # -- the defect: a ticker post whose chart will not resolve ---------------

    def test_ticker_post_with_an_unresolvable_chart_defers(self):
        from scripts.marketing_publisher import (
            _media_paths_for, _missing_required_media)

        it = _signal_item()
        media_paths = _media_paths_for(it, self.PUB_CFG, {})   # no stamp, no sidecar
        assert media_paths == []
        assert _missing_required_media(it, self.PUB_CFG, media_paths) is True

    def test_the_same_post_goes_out_once_the_sidecar_supplies_the_url(self):
        """The deferral must be TRANSIENT — this is the whole reason it is a
        defer and not a quarantine."""
        from scripts.marketing_publisher import (
            _media_paths_for, _missing_required_media)

        it = _signal_item()
        sidecar = {"2026-07-28/chart-001": "https://cdn.example/recovered.png"}
        media_paths = _media_paths_for(it, self.PUB_CFG, sidecar)
        assert media_paths == ["https://cdn.example/recovered.png"]
        assert _missing_required_media(it, self.PUB_CFG, media_paths) is False

    def test_a_plan_build_stamp_also_clears_the_hold(self):
        from scripts.marketing_publisher import (
            _media_paths_for, _missing_required_media)

        it = _signal_item(media=[{"chart_id": "chart-001", "ticker": "ROST",
                                  "media_url": "https://cdn.example/stamped.png"}])
        media_paths = _media_paths_for(it, self.PUB_CFG, {})
        assert _missing_required_media(it, self.PUB_CFG, media_paths) is False

    # -- what must KEEP flowing ----------------------------------------------

    def test_a_method_post_with_no_ticker_and_no_media_still_posts(self):
        """"Why I post the losers", "Macro without the jargon" — these carry no
        chart by design. Deferring them would strangle the desks' whole
        non-ticker voice."""
        from scripts.marketing_publisher import _missing_required_media

        for kind in ("education", "macro", "event", "theme_list", "wire"):
            it = {"id": "itm-x", "kind": kind, "as_of": "2026-07-28", "media": [],
                  "source": {}, "text": "The stop matters more than the target"}
            assert _missing_required_media(it, self.PUB_CFG, []) is False, kind

    def test_a_rollup_whose_chart_was_built_is_held_not_shipped_bare(self):
        """The incident itself: $ALL $ERIE $TRV went out with no picture.

        A `theme_list` is not a chart-bearing KIND, so the kind gate waved it
        through; `_bare_cashtag_post` treats a built-but-unresolved chart as the
        recoverable deferral case, so it waved it through too. Each gate deferred
        to the other and the post shipped text-only — "ID RATHER YOU DESTROY THE
        ENTIRE ENGINE THAN SHIP TEXT ONLY".

        The chart EXISTS here (media[] is non-empty), so its URL is recoverable
        by the backfill and deferring is honest rather than a quarantine.
        """
        from scripts.marketing_publisher import _missing_required_media

        for kind in ("theme_list", "mover"):
            it = {"id": "itm-r", "kind": kind, "as_of": "2026-07-28",
                  "source": {}, "media": [{"chart_id": "chart-011"}],
                  "text": "Insurance caught a bid today: $ALL $ERIE $TRV."}
            assert _missing_required_media(it, self.PUB_CFG, []) is True, kind

    def test_a_rollup_with_no_chart_built_is_still_out_of_scope(self):
        """Nothing was rendered, so there is nothing for the backfill to fix.

        Holding it would wedge the post until the escape hatch for a picture that
        does not exist — the same reasoning that keeps a chartless ticker post
        out of this gate.
        """
        from scripts.marketing_publisher import _missing_required_media

        it = {"id": "itm-r2", "kind": "theme_list", "as_of": "2026-07-28",
              "source": {}, "media": [],
              "text": "Insurance caught a bid today: $ALL $ERIE $TRV."}
        assert _missing_required_media(it, self.PUB_CFG, []) is False

    def test_a_breadth_post_that_mentions_a_cashtag_still_posts(self):
        """"231 of 231 names..." may name a ticker in passing and even carry an
        illustration. The KIND gate, not the text, decides — so a macro post can
        never be held for a chart it was never required to have."""
        from scripts.marketing_publisher import _missing_required_media

        it = {"id": "itm-y", "kind": "macro", "as_of": "2026-07-28",
              "source": {}, "media": [{"chart_id": "chart-009"}],
              "text": "231 of 231 names above the 200-day. Even $SPY is stretched."}
        assert _missing_required_media(it, self.PUB_CFG, []) is False

    def test_a_ticker_post_that_never_had_a_chart_is_out_of_scope(self):
        """A missing media[] is a DIFFERENT gap (nothing was rendered) and is
        not recoverable by the backfill — holding it here would wedge it until
        the escape hatch, for a picture that does not exist."""
        from scripts.marketing_publisher import _missing_required_media

        it = _signal_item(media=[])
        assert _missing_required_media(it, self.PUB_CFG, []) is False

    def test_media_enabled_off_never_defers_anything(self):
        """With the global gate off NOTHING resolves a URL. Deferring on that
        would wedge every ticker post on every desk, not one item."""
        from scripts.marketing_publisher import _missing_required_media

        assert _missing_required_media(_signal_item(), {"media_enabled": False}, []) is False

    # -- ticker resolution ----------------------------------------------------

    @pytest.mark.parametrize("it,expected", [
        (_signal_item(), "ROST"),                                    # source.ticker
        (_signal_item(source={}), "ROST"),                           # media[].ticker
        (_signal_item(source={}, media=[{"chart_id": "c1"}]), "ROST"),  # $ROST in copy
        (_signal_item(ticker="NVDA"), "NVDA"),                       # top-level wins
        (_signal_item(source={}, media=[{"chart_id": "c1"}], text="no name here"), ""),
    ])
    def test_ticker_is_found_wherever_the_emitter_put_it(self, it, expected):
        """Emitted items carry NO top-level `ticker` — it is in `source` and
        mirrored onto `media[]`. A resolver that only read the top level would
        find nothing and this whole gate would be dead code."""
        from scripts.marketing_publisher import _item_ticker
        assert _item_ticker(it) == expected

    def test_the_chart_bearing_kinds_are_real_outbox_kinds(self):
        """A typo here silently removes a desk's posts from the gate."""
        from engine.marketing.outbox import KINDS
        from scripts.marketing_publisher import _CHART_BEARING_KINDS

        assert _CHART_BEARING_KINDS <= KINDS
        assert _CHART_BEARING_KINDS == {"signal", "chart", "watchlist", "receipt"}

    # -- the bounded escape ---------------------------------------------------

    def test_escape_hatch_is_quarantine_not_a_bare_post(self):
        """THE PINNED CHOICE. Past _MEDIA_DEFER_MAX_AGE_DAYS the publisher gives
        up — and it QUARANTINES rather than posting text-only. Posting bare is
        the exact violation this gate exists to prevent, and an entry-timing
        read that is days stale is not worth sending even with the picture.
        If someone flips this to a text-only escape, this test must fail."""
        import inspect
        from scripts.marketing_publisher import main

        src = inspect.getsource(main)
        gate = src.split("a ticker post must carry its chart", 1)[1]
        gate = gate.split("global min-spacing floor", 1)[0]
        assert 'note="expired_no_media"' in gate, (
            "the escape hatch no longer quarantines — a stale ticker post is "
            "about to go out with no chart"
        )
        assert "_MEDIA_DEFER_MAX_AGE_DAYS" in gate
        # The operator has to be able to SEE it in the Actions summary, and the
        # annotation must start the line (a logger prefix makes GitHub drop it).
        assert 'print(f"::warning title=marketing-chart-missing::' in gate

    @pytest.mark.parametrize("age_days,expect_quarantine", [
        (0, False), (3, False), (4, True), (40, True),
    ])
    def test_escape_hatch_fires_only_past_the_bound(self, age_days, expect_quarantine):
        from datetime import datetime, timezone

        from scripts.marketing_publisher import (
            _MEDIA_DEFER_MAX_AGE_DAYS, _item_age_days)

        now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
        as_of = (now - timedelta(days=age_days)).date().isoformat()
        it = _signal_item(as_of=as_of)
        assert _item_age_days(it, now) == age_days
        assert (_item_age_days(it, now) > _MEDIA_DEFER_MAX_AGE_DAYS) is expect_quarantine

    def test_an_unparseable_stamp_never_expires_an_item(self):
        """Fail-soft: a malformed date must not be the reason a post is dropped."""
        from datetime import datetime, timezone

        from scripts.marketing_publisher import _item_age_days

        now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
        assert _item_age_days({"as_of": "not-a-date"}, now) == 0
        assert _item_age_days({}, now) == 0

    # -- wiring ---------------------------------------------------------------

    def test_the_gate_is_wired_ahead_of_the_spacing_floor(self):
        """Order is load-bearing: a held item must not consume the spacing
        window or a forward-book slot, the same reason the tape/cap/channel
        gates run first. Also pins that the predicate is actually acted on —
        computing it and falling through would be dead code."""
        import inspect
        from scripts.marketing_publisher import main

        src = inspect.getsource(main)
        assert src.index("_missing_required_media") < src.index(
            "global min-spacing floor: at most one post"), (
            "the media gate moved below the floor — deferred items now burn "
            "the spacing window"
        )
        gate = src.split("a ticker post must carry its chart", 1)[1]
        gate = gate.split("global min-spacing floor", 1)[0]
        assert "deferred_no_media += 1" in gate and "continue" in gate

    def test_an_operator_post_now_click_does_not_waive_the_chart_law(self):
        """REVERSED 2026-07-29 (#3960 reviewer minor). This gate used to carry an
        `iid not in post_now` exemption, on the reasoning that explicit operator
        intent outranks the hold. That conflates two different questions: the
        click is intent about WHEN to send, not consent to ship a ticker post
        with no chart, which the standing law (#3921) forbids outright. The
        operator cannot see from the admin panel that the chart's R2 URL never
        resolved, so the waiver silently turned a charted entry-timing read into
        a naked call. `post_now` skips pacing; it waives no safety gate.

        The behavioural half of this lives in
        tests/test_marketing_publisher_autoapprove.py::
        TestPostNowSkipsPacingNotSafety."""
        import inspect
        from scripts.marketing_publisher import main

        gate = inspect.getsource(main).split(
            "a ticker post must carry its chart", 1)[1].split(
            "global min-spacing floor", 1)[0]
        # CODE only: the comment above the gate names post_now to explain the
        # reversal, and a comment must not be able to satisfy or break this.
        code = [l for l in gate.splitlines() if not l.lstrip().startswith("#")]
        assert "post_now" not in "\n".join(code), code
        assert "        if _missing_required_media(it, pub_cfg, media_paths):" in code

    def test_the_counter_reaches_the_operator(self):
        """A silent hold is the defect this replaces. The count must show up in
        the run summary AND the activity row next to its sibling counters."""
        import inspect
        from scripts.marketing_publisher import main

        src = inspect.getsource(main)
        assert "deferred_no_media=%d" in src, "missing from the summary log line"
        assert '"deferred_no_media": deferred_no_media' in src, \
            "missing from the activity row"

    def test_a_held_sweep_names_the_recovery_lane_on_the_first_run(self):
        """marketing-media-backfill is workflow_dispatch-only — NOTHING schedules
        it. A hold therefore waits on a human, so the very first sweep that holds
        anything must say so in the Actions summary, with the command. Warning
        only at quarantine time would tell the operator three days too late."""
        import inspect
        from scripts.marketing_publisher import main

        src = inspect.getsource(main)
        assert 'print(f"::warning title=marketing-charts-missing::' in src
        assert "if deferred_no_media:" in src
        assert "marketing-media-backfill" in src


# ─────────────────────────────────────────────────────────────────────────────
# 4. Backfill ledger semantics
# ─────────────────────────────────────────────────────────────────────────────

class TestBackfillSidecarLedger:
    def _write(self, tmp_path, rows):
        d = tmp_path / "data" / "marketing" / "outbox"
        d.mkdir(parents=True, exist_ok=True)
        (d / "media_urls.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def test_last_row_wins_so_a_reupload_supersedes(self, tmp_path):
        from scripts.marketing_media_backfill import load_sidecar

        self._write(tmp_path, [
            {"key": "2026-07-28/chart-001", "media_url": "https://a.example/old.png"},
            {"key": "2026-07-28/chart-001", "media_url": "https://a.example/new.png"},
        ])
        assert load_sidecar(tmp_path)["2026-07-28/chart-001"] == \
            "https://a.example/new.png"

    def test_malformed_rows_are_skipped_not_fatal(self, tmp_path):
        from scripts.marketing_media_backfill import load_sidecar

        self._write(tmp_path, [
            {"key": "", "media_url": "https://a.example/x.png"},   # no key
            {"key": "2026-07-28/chart-002"},                        # no url
            {"key": "2026-07-28/chart-003", "media_url": "ftp://nope"},
            {"key": "2026-07-28/chart-004", "media_url": "https://a.example/ok.png"},
        ])
        got = load_sidecar(tmp_path)
        assert got == {"2026-07-28/chart-004": "https://a.example/ok.png"}

    def test_missing_file_is_an_empty_map(self, tmp_path):
        from scripts.marketing_media_backfill import load_sidecar
        assert load_sidecar(tmp_path) == {}

    def test_backfill_key_matches_the_publisher_lookup(self):
        """The sidecar is useless if the two sides disagree on the key. Build it
        from the backfill's own helper and read it through the publisher."""
        from scripts.marketing_media_backfill import media_key
        from scripts.marketing_publisher import _media_paths_for

        it = {"as_of": "2026-07-28", "media": [{"chart_id": "wl-2026-07-28-aapl"}]}
        key = media_key("2026-07-28", "wl-2026-07-28-aapl")
        got = _media_paths_for(it, {"media_enabled": True},
                               {key: "https://a.example/aapl.png"})
        assert got == ["https://a.example/aapl.png"]

    def test_r2_key_is_content_addressed_not_the_build_counter(self):
        """chart_id is a per-BUILD counter, not an identity: rebuild a day and
        `chart-001` names a different ticker than it did that morning. Keying the
        upload on chart_id alone (media_publish.chart_key) would PUT the new
        render over the object an already-stamped item points at, and that older
        post would silently start attaching someone else's chart. Real collision
        on 2026-07-28: chart-001 was EQT to the nightly and CBOE to the rebuild.
        """
        from engine.marketing import media_publish
        from scripts.marketing_media_backfill import r2_key_for

        eqt = r2_key_for("2026-07-28", "chart-001", b"<eqt render bytes>")
        cbo = r2_key_for("2026-07-28", "chart-001", b"<cboe render bytes>")
        assert eqt != cbo, "same key for different artwork — the clobber is back"
        assert eqt != media_publish.chart_key("2026-07-28", "chart-001"), (
            "backfill must not reuse content_studio's key; that IS the clobber"
        )
        # Deterministic: re-running the backfill re-derives the same object.
        assert r2_key_for("2026-07-28", "chart-001", b"<eqt render bytes>") == eqt
        # Byte-identical cards still share one object (no pointless re-upload).
        assert r2_key_for("2026-07-28", "chart-009", b"same") == \
            r2_key_for("2026-07-28", "chart-009", b"same")
        assert eqt.startswith(f"{media_publish.R2_MARKETING_PREFIX}/2026-07-28/chart-001-")
        assert eqt.endswith(".png")

    def test_only_entries_without_a_public_url_are_selected(self):
        from scripts.marketing_media_backfill import _iter_missing

        items = [
            {"id": "a", "as_of": "2026-07-28",
             "media": [{"chart_id": "c1", "media_url": "https://x.example/c1.png"}]},
            {"id": "b", "as_of": "2026-07-28", "media": [{"chart_id": "c2"}]},
            {"id": "c", "as_of": "2026-07-27", "media": [{"chart_id": "c3"}]},
        ]
        assert [i["id"] for i, _ in _iter_missing(items, None)] == ["b", "c"]
        assert [i["id"] for i, _ in _iter_missing(items, "2026-07-28")] == ["b"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. A stale quote source must not displace a fresh one
# ─────────────────────────────────────────────────────────────────────────────

class TestStaleQuoteSourceNeverWins:
    """2026-07-28: VPS_LIVE_PRIMARY flipped true, the GitHub live-quotes lane
    correctly stood down, and nothing repointed the `live-data` branch. The tape
    gate kept loading that 2105-symbol snapshot — seventeen hours old — and
    dict.update() let it overwrite the genuinely current heatmap and display
    quotes. Every signal then failed the 45-minute age check and the desk network
    held its entire queue."""

    NOW_MS = 1785000000000       # arbitrary fixed epoch-ms; no clock reads
    HOUR_MS = 3600 * 1000

    def _write(self, tmp_path, rel, obj):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def _iso(self, ms):
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()

    def test_seventeen_hour_snapshot_does_not_overwrite_fresh_display(self, tmp_path):
        from engine.marketing.live_verify import load_live_quotes

        fresh_ms = self.NOW_MS
        stale_ms = self.NOW_MS - 17 * self.HOUR_MS
        self._write(tmp_path, "site/live/quotes.json", {
            "asof": self._iso(fresh_ms),
            "quotes": {"ROST": {"price": 240.0, "ts": fresh_ms}},
        })
        self._write(tmp_path, "data/marketing/live_quotes_snapshot.json", {
            "asof": self._iso(stale_ms),
            "quotes": {"ROST": {"price": 999.0, "ts": stale_ms}},
        })

        got = load_live_quotes(tmp_path)
        assert got["quotes"]["ROST"]["price"] == 240.0, (
            "the 17h-old snapshot displaced the current quote — the exact "
            "failure that held every signal on 2026-07-28"
        )
        assert got["quotes"]["ROST"]["ts_ms"] == fresh_ms

    def test_a_fresh_snapshot_still_wins_over_older_display(self, tmp_path):
        """The fix must not invert the normal case: when the snapshot IS the
        freshest source (its usual state) it keeps precedence."""
        from engine.marketing.live_verify import load_live_quotes

        older_ms = self.NOW_MS - 30 * 60 * 1000
        self._write(tmp_path, "site/live/quotes.json", {
            "asof": self._iso(older_ms),
            "quotes": {"ROST": {"price": 240.0, "ts": older_ms}},
        })
        self._write(tmp_path, "data/marketing/live_quotes_snapshot.json", {
            "asof": self._iso(self.NOW_MS),
            "quotes": {"ROST": {"price": 245.0, "ts": self.NOW_MS}},
        })
        assert load_live_quotes(tmp_path)["quotes"]["ROST"]["price"] == 245.0

    def test_untimed_heatmap_pct_is_not_clobbered_by_a_stale_snapshot(self, tmp_path):
        """Heatmap tiles carry no per-quote ts, so their freshness is the
        artifact's asof. A stale snapshot must still lose to them."""
        from engine.marketing.live_verify import load_live_quotes

        stale_ms = self.NOW_MS - 17 * self.HOUR_MS
        self._write(tmp_path, "site/marketdata/sp500_heatmap.json", {
            "asof": self._iso(self.NOW_MS),
            "tiles": [{"ticker": "ROST", "pct": 1.5}],
        })
        self._write(tmp_path, "data/marketing/live_quotes_snapshot.json", {
            "asof": self._iso(stale_ms),
            "quotes": {"ROST": {"price": 999.0, "changePct": -9.9, "ts": stale_ms}},
        })
        assert load_live_quotes(tmp_path)["quotes"]["ROST"]["change_pct"] == 1.5

    def test_reported_asof_is_the_newest_artifact_not_the_last_read(self, tmp_path):
        """`asof` is the fallback age for any quote with no ts of its own, so
        taking the last-read (stale) artifact's asof would age out fresh
        heatmap entries wholesale."""
        from engine.marketing.live_verify import load_live_quotes

        stale_ms = self.NOW_MS - 17 * self.HOUR_MS
        self._write(tmp_path, "site/live/quotes.json", {
            "asof": self._iso(self.NOW_MS),
            "quotes": {"AAPL": {"price": 1.0, "ts": self.NOW_MS}},
        })
        self._write(tmp_path, "data/marketing/live_quotes_snapshot.json", {
            "asof": self._iso(stale_ms),
            "quotes": {"MSFT": {"price": 2.0, "ts": stale_ms}},
        })
        assert load_live_quotes(tmp_path)["asof"] == self._iso(self.NOW_MS)

    def test_no_sources_is_empty_not_a_crash(self, tmp_path):
        from engine.marketing.live_verify import load_live_quotes

        got = load_live_quotes(tmp_path)
        # feed_delay_min is 0.0 with nothing readable: no artifact, so no artifact
        # DECLARED a feed delay, so no consumer may allow itself one.
        assert got == {"quotes": {}, "asof": None, "source": "none",
                       "feed_delay_min": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# 6. The lane that must not die again
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishLaneCheckout:
    """2026-07-28: marketing-publish's fetch-depth:0 checkout ran the full 25m
    job timeout and was cancelled mid-clone, so `run publisher` never executed
    and nothing went out all day. The clone only grows — pin it shallow."""

    def _wf(self, name):
        from pathlib import Path
        import yaml
        p = Path(__file__).resolve().parent.parent / ".github" / "workflows" / name
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("name", ["marketing-publish.yml",
                                      "marketing-media-backfill.yml"])
    def test_checkout_is_shallow(self, name):
        steps = self._wf(name)["jobs"][next(iter(self._wf(name)["jobs"]))]["steps"]
        checkout = [s for s in steps if "actions/checkout" in str(s.get("uses", ""))]
        assert checkout, f"{name}: no checkout step found"
        for s in checkout:
            depth = (s.get("with") or {}).get("fetch-depth")
            assert depth == 1, (
                f"{name}: fetch-depth is {depth!r}; a full-history clone of this "
                "repo exceeds the job timeout and cancels the run mid-checkout"
            )

    def test_push_loop_deepens_enough_to_rebase(self):
        """A shallow clone cannot rebase onto an advanced main without deepening
        — without this the ledger silently stops reaching main."""
        from pathlib import Path

        for name in ("marketing-publish.yml", "marketing-media-backfill.yml"):
            body = (Path(__file__).resolve().parent.parent / ".github" /
                    "workflows" / name).read_text(encoding="utf-8")
            assert "git fetch --depth" in body, f"{name}: bare fetch on a shallow clone"

    def test_live_quotes_outpaces_its_tightest_consumer(self):
        """`live-data` is written by ONE lane and read by three, so its cadence has
        to satisfy the strictest reader — not merely exist.

        History, twice over. 2026-07-27T22:50Z: VPS_LIVE_PRIMARY went true, the
        whole workflow was gated on it, the branch froze at 22:31Z and
        marketing-publish's tape gate held the entire queue against a 17h-old
        snapshot. The patch was a */15 tick exempted from the gate — enough for the
        publisher's 45-minute ceiling, and the test that pinned it asked only that
        SOME tick survive. 2026-07-29: the Hot Tape radar shipped with a 12-minute
        budget, a */15 writer cannot satisfy that even at perfect delivery, and the
        radar fired zero events all day. "One tick survives" was true throughout.

        So this asserts the actual invariant: every scheduled tick must run the job
        (no cutover gate can skip one — half of GitHub's scarce delivered runs were
        being burned on `skipped` no-ops), and the cadence must beat the TIGHTEST
        consumer budget in the repo, not just the loosest.
        """
        import re
        from pathlib import Path
        import yaml

        root = Path(__file__).resolve().parent.parent
        wf = yaml.safe_load((root / ".github" / "workflows" /
                             "live-quotes.yml").read_text(encoding="utf-8"))
        # PyYAML parses the `on:` key as the boolean True.
        crons = [c["cron"] for c in (wf.get("on") or wf.get(True))["schedule"]]
        assert "if" not in wf["jobs"]["snapshot"], (
            "the snapshot job carries a condition again: a job-level `if` still "
            "consumes a delivered cron slot and still enters the workflow-level "
            "concurrency group, so a skipped tick can cancel a real snapshot")

        every = min(int(m.group(1)) for c in crons if (m := re.match(r"\*/(\d+) ", c)))
        pub = yaml.safe_load((root / "config" / "marketing.yml")
                             .read_text(encoding="utf-8"))["publish"]
        ceilings = {
            "publish.live_gate.max_quote_age_min":
                int(pub["live_gate"]["max_quote_age_min"]),
            "hot_tape.max_quote_age_min":
                int(yaml.safe_load((root / "config" / "hot_tape.yml")
                                   .read_text(encoding="utf-8"))["max_quote_age_min"]),
        }
        name, tightest = min(ceilings.items(), key=lambda kv: kv[1])
        assert every < tightest, (
            f"live-quotes writes every {every}m but {name} demands quotes younger "
            f"than {tightest}m — the reader cannot be satisfied by this writer")

    def test_outbox_ledgers_carry_union_merge(self):
        """The publish sweep and the nightly commit the same append-only JSONL.
        Without union merge the retry-rebase loop conflicts on every attempt and
        gives up, stranding posted/approved transitions off main."""
        from pathlib import Path

        attrs = (Path(__file__).resolve().parent.parent /
                 ".gitattributes").read_text(encoding="utf-8")
        for path in ("data/marketing/outbox/activity.jsonl",
                     "data/marketing/outbox/status_ledger.jsonl",
                     "data/marketing/outbox/items.jsonl",
                     "data/marketing/outbox/media_urls.jsonl"):
            assert f"{path} merge=union" in attrs, f"{path} lacks merge=union"
