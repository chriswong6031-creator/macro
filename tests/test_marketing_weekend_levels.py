"""Tests for engine.marketing.weekend_levels — popular-ticker weekend posts.

Focus: level math is correct, copy is compliant (no advice lexicon, one cashtag,
≤280 chars) across every state, and the batch is fail-soft on missing data.
"""
from __future__ import annotations

import pytest

from engine.marketing import weekend_levels as wl


# ─────────────────────────────────────────────────────────────────────────────
# Level math
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_levels_basic():
    closes = [float(x) for x in range(1, 101)]  # 1..100, last=100
    lv = wl.compute_levels(closes)
    assert lv is not None
    assert lv["last"] == 100.0
    assert lv["sma20"] == pytest.approx(90.5)   # mean(81..100)
    assert lv["sma50"] == pytest.approx(75.5)   # mean(51..100)
    assert lv["hi52"] == 100.0 and lv["lo52"] == 1.0
    assert lv["above20"] and lv["above50"]
    assert lv["wk_pct"] == pytest.approx((100 / 95 - 1) * 100)
    assert lv["pct_from_hi"] == pytest.approx(0.0)


def test_compute_levels_insufficient_history_returns_none():
    assert wl.compute_levels([1.0] * 49) is None
    assert wl.compute_levels([]) is None
    assert wl.compute_levels(None) is None  # type: ignore[arg-type]


def test_compute_levels_rejects_nonpositive_last():
    closes = [1.0] * 60 + [0.0]
    assert wl.compute_levels(closes) is None


def test_classify_state_covers_the_grid():
    # leading: above both, at highs
    up = [float(x) for x in range(1, 121)]
    assert wl.classify_state(wl.compute_levels(up)) == "leading"
    # downtrend: below both, not near low
    down = [float(x) for x in range(120, 0, -1)]  # 120..1 -> last well off low? last=1 => near low
    st = wl.classify_state(wl.compute_levels(down))
    assert st in {"downtrend", "basing"}
    # basing: below both AND near the 52w low
    assert wl.classify_state(wl.compute_levels(down)) == "basing"


# ─────────────────────────────────────────────────────────────────────────────
# Copy compliance — the load-bearing safety property for a live brand account
# ─────────────────────────────────────────────────────────────────────────────

def _all_state_series() -> dict[str, list[float]]:
    """Synthetic close series engineered to land in each state."""
    up = [float(x) for x in range(1, 121)]                      # leading
    down = [float(x) for x in range(120, 0, -1)]                # basing (near low)
    # cooling: above 50 but under the 20 (recent dip after a run)
    cooling = [float(x) for x in range(1, 111)] + [95.0, 96.0, 97.0, 98.0, 99.0,
                                                   98.0, 97.0, 98.0, 99.0, 98.0]
    # reclaiming: under 50, back over the 20 (recent bounce off lows)
    reclaiming = [float(x) for x in range(120, 40, -1)] + [42.0, 44.0, 46.0, 48.0,
                                                           50.0, 52.0, 54.0, 56.0]
    return {"leading": up, "basing": down, "cooling": cooling, "reclaiming": reclaiming}


def test_render_post_is_compliant_across_states_and_tails():
    for state, closes in _all_state_series().items():
        lv = wl.compute_levels(closes)
        assert lv is not None
        for variant in range(len(wl._TAILS)):
            headline, body = wl.render_post("NVDA", lv, variant=variant)
            text = f"{headline}\n\n{body}"
            # must not raise: no lexicon, exactly one cashtag, ≤280 chars
            wl._assert_clean(text, "NVDA")
            assert text.count("$NVDA") == 1
            assert len(text) <= wl._MAX_LEN


def test_assert_clean_rejects_banned_phrase():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA is a no-brainer, load up", "NVDA")


def test_assert_clean_rejects_wrong_or_extra_cashtag():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA and $AMD both look great", "NVDA")  # two cashtags
    with pytest.raises(ValueError):
        wl._assert_clean("no cashtag here", "NVDA")


def test_assert_clean_rejects_overlength():
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA " + "x" * 300, "NVDA")


# ─────────────────────────────────────────────────────────────────────────────
# Batch construction (fail-soft, outbox-shaped)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_parquet(root, ticker, closes):
    pd = pytest.importorskip("pandas")
    d = root / "data" / "stocks"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    pd.DataFrame({"close": closes}, index=idx).to_parquet(d / f"{ticker}.parquet")


def test_build_items_skips_tickers_without_data(tmp_path):
    _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
    items = wl.build_items(tmp_path, tickers=["NVDA", "ZZZZ"], as_of="2026-07-25")
    assert [i["source"]["ticker"] for i in items] == ["NVDA"]  # ZZZZ skipped, no data


def test_build_items_are_watchlist_and_compliant(tmp_path):
    for t in ("NVDA", "AAPL", "TSLA"):
        _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
    items = wl.build_items(tmp_path, tickers=["NVDA", "AAPL", "TSLA"], as_of="2026-07-25")
    assert len(items) == 3
    for it in items:
        assert it["kind"] == "watchlist"
        assert it["provenance"] == "weekend_levels"
        assert it["source"]["lane"] == "weekend_levels"
        assert len(it["text"]) <= wl._MAX_LEN
        wl._assert_clean(it["text"], it["source"]["ticker"])


def test_build_items_respects_max_and_schedule(tmp_path):
    for t in ("NVDA", "AAPL", "TSLA", "AMD"):
        _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
    sched = [("D1-S1", "2026-07-25T11:00:00Z"), ("D1-S2", "2026-07-25T13:00:00Z")]
    items = wl.build_items(tmp_path, tickers=["NVDA", "AAPL", "TSLA", "AMD"],
                           as_of="2026-07-25", schedule=sched, max_items=2)
    assert len(items) == 2
    assert items[0]["slot"] == "D1-S1" and items[0]["scheduled_at"] == "2026-07-25T11:00:00Z"
    assert items[1]["slot"] == "D1-S2"


# ─────────────────────────────────────────────────────────────────────────────
# Weekend gating + scheduling
# ─────────────────────────────────────────────────────────────────────────────

def test_should_run_only_on_weekends():
    assert wl.should_run("2026-07-25") is True    # Saturday
    assert wl.should_run("2026-07-26") is True    # Sunday
    assert wl.should_run("2026-07-24") is False   # Friday
    assert wl.should_run("2026-07-27") is False   # Monday
    assert wl.should_run("garbage") is False


def test_weekend_schedule_resolves_ladder_to_utc():
    sched = wl.weekend_schedule("2026-07-25", 3)
    assert [s for s, _ in sched] == ["D1-S1", "D1-S2", "D1-S3"]
    # S1 = 4 AM PT on 2026-07-25 (PDT, UTC-7) → 11:00Z
    assert sched[0][1] == "2026-07-25T11:00:00Z"
    # every entry resolved to a real datetime (not the "immediate" fallback)
    assert all(at.endswith("Z") and at != "immediate" for _, at in sched)


# ─────────────────────────────────────────────────────────────────────────────
# Cited-level contract — the chart draws the line the text names
# ─────────────────────────────────────────────────────────────────────────────
# The 2026-07-27 $AVGO incident: copy cited "the POC at 379.32" over a card
# that drew no such line, because text and chart were assembled from different
# sources. cited_level() is now the single source; these tests pin (a) the
# state→level mapping, (b) that every body frame for a state formats the SAME
# level its card will draw, and (c) that the renderer actually draws it.

_LV_FIXTURE = {
    "last": 100.0, "wk_pct": 1.0, "sma20": 98.0, "sma50": 95.0,
    "hi52": 110.0, "lo52": 80.0, "above20": True, "above50": True,
    "pct_from_hi": -9.1, "pct_from_lo": 25.0,
}

_STATE_PLACEHOLDER = {
    "leading": "{s20}", "uptrend": "{s20}", "cooling": "{s20}",
    "downtrend": "{s20}", "reclaiming": "{s50}", "basing": "{lo}",
}


def test_cited_level_maps_every_state():
    for state, ph in _STATE_PLACEHOLDER.items():
        label, price = wl.cited_level(_LV_FIXTURE, state)
        expected = {"{s20}": 98.0, "{s50}": 95.0, "{lo}": 80.0}[ph]
        assert price == expected, (state, label, price)
        assert label and "poc" not in label.lower()


def test_every_frame_cites_the_level_its_card_draws():
    """Each body shape for a state must format the placeholder matching
    cited_level(state) — otherwise the copy names a number the chart does
    not draw, which is the exact AVGO defect."""
    for state, frames in wl._FRAMES.items():
        ph = _STATE_PLACEHOLDER[state]
        for frame in frames:
            assert ph in frame, (
                f"{state} frame formats no {ph} (would cite a level the "
                f"card does not draw): {frame!r}")


def test_floor_copy_passes_the_language_bar():
    """Every headline and body the deterministic floor can emit clears the
    same banned-language screen the publisher enforces at post time —
    no study names (POC/VWAP), no dash tells, no cheese."""
    from engine.marketing.copywriter import banned_language

    for state, frames in wl._FRAMES.items():
        for sv, _ in enumerate(frames):
            lv = dict(_LV_FIXTURE)
            headline, body = wl.render_post("AVGO", lv, variant=sv,
                                            state_variant=sv)
            # render_post classifies state from lv; we only need SOME valid
            # copy per shape here, plus the full pools screened directly:
            assert not banned_language(f"{headline}\n\n{body}"), (headline, body)
    for pools in (wl._HEADLINES, wl._FRAMES):
        for state, entries in pools.items():
            for e in entries:
                text = e.replace("$T", "$AVGO").replace("{wk_cap}", "Up 2%")
                text = text.replace("{wk}", "up 2% on the week")
                text = text.replace("{s20}", "98").replace("{s50}", "95")
                text = text.replace("{lo}", "80").replace("{px}", "100")
                assert not banned_language(text), (state, e)


def test_render_chart_v2_draws_the_cited_level():
    from engine.marketing.chart_render import render_chart_v2

    n = 60
    c = [100.0 + (i % 7) - 3 for i in range(n)]
    o = [x - 0.5 for x in c]
    h = [x + 1.5 for x in c]
    l = [x - 1.5 for x in c]
    v = [1_000_000.0] * n
    dates = [f"2026-05-{(i % 28) + 1:02d}" for i in range(n)]

    svg = render_chart_v2(
        ticker="AVGO", dates=dates, o=o, h=h, l=l, c=c, volume=v,
        show_indicators=False,
        level_overlay={"price": 99.0, "label": "20-day avg"},
    )
    assert "20-day avg" in svg
    assert 'stroke-dasharray="6 4"' in svg

    # Out-of-range level: skipped silently, no phantom label.
    svg2 = render_chart_v2(
        ticker="AVGO", dates=dates, o=o, h=h, l=l, c=c, volume=v,
        show_indicators=False,
        level_overlay={"price": 5.0, "label": "52-wk low"},
    )
    assert "52-wk low" not in svg2


# ─────────────────────────────────────────────────────────────────────────────
# X Growth W1g — the double slate, and the retired v1 writer.
#
# (a) IDEMPOTENCE. This lane ran twice for as_of=2026-07-26 (a 03:13 batch and a
#     09:52 batch) and wrote EIGHT items each time: a second, contradictory post
#     for every slot, deleted by the operator by hand. A re-run must add zero
#     new slots — and must not spend eight Chrome rasters discovering that.
#     The guard is STATUS-BLIND (2026-07-31): the first fix read live items only,
#     which went blind the moment the 03:13 batch POSTED — i.e. exactly when the
#     09:52 rerun happened. See TestWeekendLaneIsIdempotent.
#
# (b) NO SILENT TEMPLATE FALLBACK. write_copy called `copywriter.write_posts_llm`,
#     the retired v1 BATCH path whose documented failure mode is a silent 100%
#     template fallback (one call for the whole batch; a truncated reply returns
#     None and every post reverts to template prose). On `write_posts_llm_v2`,
#     an armed lane that produces no model copy DROPS the post — `watchlist` is
#     a planned kind and the no-fallback law covers it.
# ─────────────────────────────────────────────────────────────────────────────

_ARMED_CFG = {"copywriter": {"llm": {"enabled": True}}}


def _queue_a_weekend_item(root, as_of="2026-07-26", account="flagship"):
    from engine.marketing.outbox import enqueue, make_item
    item = make_item(
        account=account, kind="watchlist",
        text="$NVDA into the week\n\nClosed 120.00, holding its 20-day average.",
        as_of=as_of, provenance="weekend_levels",
        source={"ticker": "NVDA", "lane": "weekend_levels"},
    )
    assert enqueue(item, root=root) == "queued"
    return item


class TestWeekendLaneIsIdempotent:
    def test_a_second_same_day_run_adds_zero_new_slots(self, tmp_path):
        for t in ("NVDA", "AAPL", "TSLA"):
            _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
        tickers = ["NVDA", "AAPL", "TSLA"]

        first = wl.build_items(tmp_path, tickers=tickers, as_of="2026-07-26")
        assert first, "first run built nothing — fixture is wrong"
        from engine.marketing.outbox import enqueue
        for it in first:
            assert enqueue(it, root=tmp_path, max_per_account_day=8) == "queued"

        second = wl.build_items(tmp_path, tickers=tickers, as_of="2026-07-26")
        assert second == [], (
            f"the 09:52 re-run built {len(second)} more item(s) for a day that "
            f"already has {len(first)}"
        )

    def test_the_guard_is_scoped_to_that_account_and_that_day(self, tmp_path):
        for t in ("NVDA", "AAPL"):
            _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
        _queue_a_weekend_item(tmp_path, as_of="2026-07-26", account="flagship")
        # A different content day is untouched...
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-27")
        # ...and so is a different desk.
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                              account="cici")

    def test_a_POSTED_batch_still_blocks_the_rerun(self, tmp_path):
        """THE 2026-07-26 INCIDENT, exactly. Fails pre-fix.

        `already_built` used to read `rewrite.live_items_for`, which filters out
        every TERMINAL status — and `posted` is terminal. So the guard could only
        see a batch that had NOT shipped yet: the 03:13 slate queued, posted
        through the morning, and by 09:52 every one of its rows was invisible.
        The lane read "nothing built for 2026-07-26" and rebuilt the whole day.

        An idempotence guard that goes blind the moment its work SUCCEEDS is the
        inverse of the guarantee it advertises.
        """
        from engine.marketing.outbox import transition
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        item = _queue_a_weekend_item(tmp_path)
        # Walk the row all the way to the terminal `posted` status the morning
        # batch reaches — queued → approved → posting → posted.
        for to in ("approved", "posting", "posted"):
            transition(item["id"], to, actor="publisher", root=tmp_path)
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26") == [], (
            "a POSTED 03:13 batch let the 09:52 rerun rebuild the whole day"
        )

    def test_a_quarantined_batch_also_blocks_the_rerun(self, tmp_path):
        """The trade this fix makes, pinned so it cannot be reverted by accident.

        Quarantining a bad slate used to re-arm the lane for the same day. It no
        longer does: "built" is now ANY row for (account, as_of, provenance) in
        items.jsonl, whatever the ledger later did to it, because status-aware
        was exactly what let a POSTED batch look like an empty day. A duplicate
        slate on a live timeline is a public contradiction; a day with a
        quarantined batch and no replacement is a quiet day. Deliberate
        regeneration goes through the rewrite path (next test).
        """
        from engine.marketing.outbox import transition
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        item = _queue_a_weekend_item(tmp_path)
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26") == []
        transition(item["id"], "quarantined", actor="operator", root=tmp_path)
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26") == []

    def test_already_built_counts_every_status(self, tmp_path):
        """Directly on the predicate, so the pin survives a build_items refactor."""
        from engine.marketing.outbox import transition
        item = _queue_a_weekend_item(tmp_path)
        assert wl.already_built(tmp_path, as_of="2026-07-26") == 1
        for to in ("approved", "posting", "posted"):
            transition(item["id"], to, actor="publisher", root=tmp_path)
        assert wl.already_built(tmp_path, as_of="2026-07-26") == 1, (
            "the row vanished from the idempotence read once it posted"
        )
        # Still scoped: another day / another desk is not this day's work.
        assert wl.already_built(tmp_path, as_of="2026-07-27") == 0
        assert wl.already_built(tmp_path, as_of="2026-07-26", account="cici") == 0

    def test_the_rewrite_path_can_still_regenerate_a_queued_day(self, tmp_path):
        """skip_if_queued=False is what the supersede lane passes; without it a
        rewrite could never regenerate the copy it exists to replace."""
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        _queue_a_weekend_item(tmp_path)
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                              skip_if_queued=False)


class TestWeekendWriterNeverFallsBackToTemplates:
    def test_it_calls_the_v2_per_item_writer(self, monkeypatch):
        """The v1 batch path is the one with the documented silent-fallback
        failure mode; this lane must not be on it."""
        import engine.marketing.copywriter as cw
        seen = {}

        def _fake_v2(contexts, cfg, *, root=None):
            seen["n"] = len(contexts)
            return [{"mode": "llm", "headline": "$NVDA into the week",
                     "body": "Closed 120.00 and held its 20-day average."}
                    for _ in contexts]

        monkeypatch.setattr(cw, "write_posts_llm_v2", _fake_v2, raising=True)
        monkeypatch.setattr(cw, "write_posts_llm",
                            lambda *a, **k: pytest.fail("v1 batch writer called"),
                            raising=True)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        specs = [{"ticker": "NVDA", "lv": {"last": 120.0, "sma20": 118.0,
                                           "sma50": 110.0, "lo52": 90.0,
                                           "hi52": 130.0, "wk_pct": 1.0,
                                           "above20": True, "above50": True,
                                           "pct_from_hi": -7.0, "pct_from_lo": 33.0},
                  "headline": "$NVDA floor", "body": "Floor body copy."}]
        out = wl.write_copy(specs, _ARMED_CFG)
        assert seen.get("n") == 1
        assert out == [("$NVDA into the week",
                        "Closed 120.00 and held its 20-day average.")]

    def test_an_armed_lane_with_no_copy_drops_the_post(self, tmp_path, monkeypatch):
        """EMPTY LLM → DROPPED, NOT TEMPLATED. Pre-fix this shipped the floor."""
        import engine.marketing.copywriter as cw
        monkeypatch.setattr(
            cw, "write_posts_llm_v2",
            lambda contexts, cfg, root=None: [
                {"mode": "dropped", "reasons": ["no_provider_credential"],
                 "stage": "provider"} for _ in contexts],
            raising=True)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        items = wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                               cfg=_ARMED_CFG, with_media=False)
        assert items == [], (
            f"a dropped post was replaced with template copy: "
            f"{[i['text'] for i in items]}"
        )

    def test_a_writer_that_raises_drops_rather_than_templates(self, tmp_path,
                                                              monkeypatch):
        import engine.marketing.copywriter as cw

        def _boom(*_a, **_k):
            raise RuntimeError("provider construction blew up")

        monkeypatch.setattr(cw, "write_posts_llm_v2", _boom, raising=True)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                              cfg=_ARMED_CFG, with_media=False) == []

    def test_one_drop_costs_one_post_not_the_batch(self, tmp_path, monkeypatch):
        """The whole reason for per-item calls: isolation."""
        import engine.marketing.copywriter as cw

        def _one_bad(contexts, cfg, root=None):
            out = []
            for i, ctx in enumerate(contexts):
                if i == 0:
                    out.append({"mode": "dropped", "reasons": ["critic"],
                                "stage": "critic"})
                else:
                    tk = str(ctx.get("ticker") or "")
                    out.append({"mode": "llm",
                                "headline": f"${tk} into the week",
                                "body": f"{tk} closed at 120.00 and held the "
                                        f"20-day average into the weekend."})
            return out

        monkeypatch.setattr(cw, "write_posts_llm_v2", _one_bad, raising=True)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        for t in ("NVDA", "AAPL"):
            _seed_parquet(tmp_path, t, [float(x) for x in range(1, 121)])
        items = wl.build_items(tmp_path, tickers=["NVDA", "AAPL"],
                               as_of="2026-07-26", cfg=_ARMED_CFG, with_media=False)
        assert [i["source"]["ticker"] for i in items] == ["AAPL"], items

    def test_a_mute_lane_is_not_a_drop(self, tmp_path, monkeypatch):
        """Nobody armed the writer (no flag, no env) — the floor still ships, or
        every local run and every unarmed nightly posts an empty weekend."""
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        items = wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                               cfg=_ARMED_CFG, with_media=False)
        assert len(items) == 1, items
        assert not wl.lane_armed(_ARMED_CFG)

    def test_model_copy_that_breaks_the_compliance_bar_is_dropped(
            self, tmp_path, monkeypatch):
        """_assert_clean still runs, and a failure is a DROP now, not a
        substitution."""
        import engine.marketing.copywriter as cw
        monkeypatch.setattr(
            cw, "write_posts_llm_v2",
            lambda contexts, cfg, root=None: [
                {"mode": "llm", "headline": "$NVDA is a no-brainer",
                 "body": "Back up the truck, this is easy money."}
                for _ in contexts],
            raising=True)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        _seed_parquet(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
        assert wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-26",
                              cfg=_ARMED_CFG, with_media=False) == []
