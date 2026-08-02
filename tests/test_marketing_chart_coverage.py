"""tests/test_marketing_chart_coverage.py — every ticker post carries a chart.

Pins the 2026-07-28 defect the operator reported from the Outbox: four queued
posts, all naming a ticker, none carrying an illustration —

    "$LKFN chart I keep coming back to  …  mine's on the chart."   (no chart)
    "Radar check on $CVI — near entry. Nothing's triggered."       (no chart)

Four independent causes, one per section below:

  1. content_plan charted ONLY `type == "signal"`, so the `chart`, `watchlist`
     and `receipt` types were structurally incapable of carrying an image.
  2. The live-price gate VETOED the chart instead of choosing its variant, so an
     item about to be demoted signal→watchlist lost its card on the way.
  3. chart_render read daily bars from data/stocks/ alone (232 large caps) while
     Prophet picks its signals from data/baskets/ohlcv/ (2,758 names) — 30 of the
     43 tickers in the plan, including all four the operator saw, had no bars
     anywhere marketing could find them.
  4. The chart_id was deduped GLOBALLY, so the first desk to chart a ticker
     locked every other desk out of it.

The operator's law: a post that names a ticker gets a chart. Only a post with no
ticker (education / macro / a company event) may ship text-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
_FRESH = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()


@pytest.fixture(autouse=True)
def _no_logo_cache_writes(monkeypatch):
    """Never touch the repo's real logo cache (MM_DATA_GUARD law).

    These tests call content_plan with the REAL root so the loaders can read the
    committed parquet trees — which means render_chart_v2's logo_root kwarg would
    otherwise fetch and cache company logos into data/marketing/logos/. Caught the
    honest way: an early run of this file left 19 untracked *_color.png files in
    the worktree. Neutralised for every test in the module, so the cards render
    offline (monograms) and write nothing.
    """
    import engine.marketing.chart_render as cr

    monkeypatch.setattr(cr, "resolve_color_logo", lambda *a, **k: None)
    monkeypatch.setattr(cr, "resolve_logo", lambda *a, **k: None)

# Ticker-bearing post types. `mover` is charted by its own reach lane.
_CHARTABLE = ("signal", "chart", "watchlist", "receipt")


def _plan(asset: str, *, entry: float, signal_date: str) -> dict:
    return {
        "id": f"{asset}-BULL", "asset": asset, "direction": "BULL",
        "entry": entry, "invalidation": entry * 0.85,
        "targets": [entry * 1.15, entry * 1.3], "trigger": entry,
        "_conviction_score": 88, "_signal_date": signal_date,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 65.0, "what_to_do_now": [],
    }


def _series(n: int = 140, start: float = 100.0):
    dates, closes = [], []
    d = datetime.now(timezone.utc).date() - timedelta(days=n)
    for i in range(n):
        dates.append((d + timedelta(days=i)).isoformat())
        closes.append(start + i * 0.10)
    return dates, closes


# ---------------------------------------------------------------------------
# 1. Cause one: the type filter
# ---------------------------------------------------------------------------

def test_every_ticker_bearing_type_can_carry_a_chart():
    """`chart` / `watchlist` / `receipt` posts must be chartable, not just `signal`.

    This is the operator's headline defect: a post headed "$LKFN chart I keep
    coming back to" whose body says "mine's on the chart", shipped with no chart.
    """
    # DATA-DEPENDENT: the tape variant has no v1 fallback by design (the v1 card
    # hard-draws a green "BUY" label), so a `chart`/`watchlist` post only gets an
    # image when render_chart_v2 succeeds — which needs real bars off a parquet.
    # Skipped on the thin pytest+pyyaml lane, executed on the fat chart-render-data
    # lane. Both lanes must name this file or the gate below is unrun.
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    plans = [_plan(t, entry=closes[-1], signal_date=_FRESH)
             for t in ("PLTR", "SBUX", "MSFT", "EQT", "ROST", "GM")]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    d1 = [q for a in plan["accounts"] for q in a["queue"]
          if str(q.get("slot", "")).startswith("D1-") and q.get("ticker")]
    assert d1, "fixture produced no D1 ticker posts — the test would pass vacuously"

    uncharted = [q for q in d1 if q["type"] in _CHARTABLE and not q.get("chart_id")]
    assert not uncharted, (
        "ticker-bearing D1 posts shipped with no chart_id: "
        + ", ".join(f"{q['slot']}/{q['type']}/{q['ticker']}" for q in uncharted)
    )

    # And the types that were previously excluded are genuinely represented,
    # so a plan that happened to contain only `signal` cannot fake a pass.
    seen = {q["type"] for q in d1 if q.get("chart_id")}
    assert seen - {"signal"}, (
        f"only `signal` posts got charts ({seen}) — the type filter is still "
        "signal-only and the defect is not actually pinned"
    )


def test_a_post_with_no_ticker_stays_text_only():
    """The operator's carve-out: no ticker (education / macro) → no chart needed."""
    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    plans = [_plan("PLTR", entry=closes[-1], signal_date=_FRESH)]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    for a in plan["accounts"]:
        for q in a["queue"]:
            if not q.get("ticker") and q.get("type") not in ("mover", "theme_list"):
                assert not q.get("chart_id"), (
                    f"{q['slot']}/{q['type']} has no ticker but was given a chart"
                )


# ---------------------------------------------------------------------------
# 2. Cause two: the live gate picks the VARIANT, it does not veto the chart
# ---------------------------------------------------------------------------

def test_stale_signal_still_gets_a_card_but_without_the_setup_marker():
    """A signal that fails the live gate is demoted to `watchlist` further down
    content_plan. It must keep a chart — a "watching, not triggered" post needs
    the tape MORE than a live signal does — but must NOT wear the SETUP pill,
    which would contradict its own copy."""
    # DATA-DEPENDENT: the tape variant has no v1 fallback by design (the v1 card
    # hard-draws a green "BUY" label), so a `chart`/`watchlist` post only gets an
    # image when render_chart_v2 succeeds — which needs real bars off a parquet.
    # Skipped on the thin pytest+pyyaml lane, executed on the fat chart-render-data
    # lane. Both lanes must name this file or the gate below is unrun.
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    # Eligibility (is_postable_signal) and actionability (verify_signal_live) are
    # DIFFERENT gates. A stale date fails both, so no post would exist at all —
    # use a fresh signal whose price has run away past the +12% entry band: it is
    # postable, but no longer an actionable entry, which is exactly the item that
    # gets demoted signal→watchlist.
    plans = [_plan(t, entry=closes[-1] / 1.5, signal_date=_FRESH)
             for t in ("PLTR", "SBUX", "MSFT", "EQT")]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    charts = {c["id"]: c for c in plan["featured_charts"]}
    d1 = [q for a in plan["accounts"] for q in a["queue"]
          if str(q.get("slot", "")).startswith("D1-") and q.get("ticker")
          and q["type"] in _CHARTABLE]
    assert d1, "fixture produced no D1 ticker posts"

    charted = [q for q in d1 if q.get("chart_id")]
    assert charted, (
        "a stale signal lost its chart entirely — the live gate is still "
        "vetoing the card instead of downgrading it to the tape variant"
    )
    for q in charted:
        fc = charts[q["chart_id"]]
        assert fc.get("variant") == "tape", (
            f"{q['slot']} is a stale/demoted signal but got the "
            f"{fc.get('variant')!r} card"
        )
        assert "SETUP" not in (fc.get("svg") or ""), (
            f"{q['slot']} carries a SETUP pill on a post that is not an entry claim"
        )


def test_live_signal_keeps_the_setup_marker():
    """The converse: a genuinely live signal still gets the marked card, so the
    tape variant cannot silently swallow every chart."""
    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    plans = [_plan(t, entry=closes[-1], signal_date=_FRESH)
             for t in ("PLTR", "SBUX", "MSFT", "EQT")]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    charts = {c["id"]: c for c in plan["featured_charts"]}
    sig = [q for a in plan["accounts"] for q in a["queue"]
           if str(q.get("slot", "")).startswith("D1-")
           and q.get("type") == "signal" and q.get("chart_id")]
    assert sig, "no live signal post got a chart — fixture is not exercising the path"
    assert any(charts[q["chart_id"]].get("variant") == "signal" for q in sig), (
        "no live signal received the marked `signal` card variant"
    )


def test_invalidated_plan_is_still_never_charted():
    """The standing law survives the widened type filter: an invalidated plan
    must not reach a chart through the new `watchlist`/`chart` doors either."""
    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    bad = _plan("QCOM", entry=closes[-1], signal_date=_FRESH)
    bad.update({"phase": "invalidated", "recommended_action": "invalidated",
                "management_confidence": 13.5})
    plans = [_plan(t, entry=closes[-1], signal_date=_FRESH)
             for t in ("PLTR", "SBUX", "MSFT")] + [bad]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)
    assert "QCOM" not in {c["ticker"] for c in plan["featured_charts"]}


# ---------------------------------------------------------------------------
# 3. Cause three: the loaders must look where Prophet looks
# ---------------------------------------------------------------------------

def test_price_search_order_matches_prophet():
    """chart_render must read the same tree build_prophet reads, in the same
    order. Marketing looking only at data/stocks/ is what left 30 of the plan's
    43 tickers with no bars at all."""
    from engine.marketing.chart_render import _PRICE_SUBDIRS

    assert _PRICE_SUBDIRS[0] == "data/baskets/ohlcv", (
        "the wide basket tree must be searched FIRST — it is where Prophet "
        "picks the signals marketing publishes"
    )
    assert "data/stocks" in _PRICE_SUBDIRS

    prophet = (ROOT / "scripts" / "build_prophet.py").read_text(encoding="utf-8")
    assert '["data/baskets/ohlcv", "data/stocks"]' in prophet, (
        "build_prophet's search order moved — chart_render._PRICE_SUBDIRS must "
        "move with it or marketing goes blind on the tickers Prophet chooses"
    )


def test_loaders_find_a_baskets_only_ticker():
    """A ticker present ONLY in data/baskets/ohlcv must load. $CBOE and $LKFN are
    the operator's own uncharted posts and both are baskets-only names."""
    # DATA-DEPENDENT: the tape variant has no v1 fallback by design (the v1 card
    # hard-draws a green "BUY" label), so a `chart`/`watchlist` post only gets an
    # image when render_chart_v2 succeeds — which needs real bars off a parquet.
    # Skipped on the thin pytest+pyyaml lane, executed on the fat chart-render-data
    # lane. Both lanes must name this file or the gate below is unrun.
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    from engine.marketing.chart_render import load_closes, load_ohlcv

    baskets = ROOT / "data" / "baskets" / "ohlcv"
    stocks = ROOT / "data" / "stocks"
    if not baskets.is_dir():
        pytest.skip("data/baskets/ohlcv is not present in this checkout")

    candidates = [p.stem for p in sorted(baskets.glob("*.parquet"))[:400]
                  if not (stocks / f"{p.stem}.parquet").exists()]
    if not candidates:
        pytest.skip("no baskets-only ticker available to exercise the fallback")
    ticker = candidates[0]

    got_closes = load_closes(ticker, ROOT, n=90)
    assert got_closes is not None, (
        f"{ticker} exists in data/baskets/ohlcv but load_closes returned None — "
        "marketing is still reading data/stocks/ alone"
    )
    dates, closes = got_closes
    assert len(closes) > 10 and all(isinstance(c, float) for c in closes)

    bars = load_ohlcv(ticker, ROOT, n=90)
    assert bars is not None, f"load_ohlcv found no bars for {ticker}"
    d, o, h, l, c, v = bars
    assert len({len(d), len(o), len(h), len(l), len(c), len(v)}) == 1
    # The baskets tree carries REAL opens — they must not all be the prev close.
    assert any(abs(oo - cc) > 1e-9 for oo, cc in zip(o[1:], c[:-1])), (
        "every open equals the previous close — the real `open` column is being "
        "ignored in favour of the prev-close proxy"
    )


# ---------------------------------------------------------------------------
# 4. Cause four: chart ids are per-account (the shared-media guard)
# ---------------------------------------------------------------------------

def test_two_desks_never_share_a_chart_id():
    """sentinel.gate_plan quarantines a second account carrying a chart_id another
    desk already used (reason shared_media:<id>) — two desks posting the identical
    image is the coordinated-posting fingerprint. Sharing ids to save a raster
    silently cost real posts."""
    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    plans = [_plan(t, entry=closes[-1], signal_date=_FRESH)
             for t in ("PLTR", "SBUX", "MSFT", "EQT")]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
        {"id": "founder", "kind": "branded", "beat": "c", "voice": "specialist"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    owner: dict[str, str] = {}
    for a in plan["accounts"]:
        for q in a["queue"]:
            cid = q.get("chart_id")
            if not cid:
                continue
            prev = owner.setdefault(cid, a["id"])
            assert prev == a["id"], (
                f"chart_id {cid} is used by both {prev!r} and {a['id']!r} — the "
                "Sentinel will quarantine the second desk as shared_media"
            )


def test_a_second_desk_is_not_starved_of_a_ticker():
    """The old global dedupe meant the first desk to chart a ticker locked all
    others out — the founder desk's own $EQT and $ROST posts got nothing."""
    from engine.marketing.content_studio import content_plan

    dates, closes = _series()
    plans = [_plan("PLTR", entry=closes[-1], signal_date=_FRESH)]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
        {"id": "founder", "kind": "branded", "beat": "c", "voice": "specialist"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes), root=ROOT)

    charted_desks = {
        a["id"] for a in plan["accounts"]
        for q in a["queue"]
        if str(q.get("slot", "")).startswith("D1-") and q.get("chart_id")
    }
    assert charted_desks >= {"flagship", "founder"}, (
        f"only {charted_desks} got charts on the single shared ticker — a "
        "global ticker dedupe is starving the other desk"
    )


# ---------------------------------------------------------------------------
# 5. The deferred raster: pay only for cards that actually post
# ---------------------------------------------------------------------------

def test_raster_plan_media_only_pays_for_survivors_and_prunes_the_rest():
    """content_plan renders an SVG per candidate (cheap); the PNG raster is one
    headless-Chrome launch (~13s) and must be spent only on cards attached to a
    post that survived the gate."""
    from engine.marketing import content_studio as cs

    calls: list[str] = []

    def _fake_attach(fc, **kw):
        calls.append(fc["id"])
        fc["media_png_path"] = f"data/marketing/outbox/media/x/{fc['id']}.png"

    plan = {
        "as_of": "2026-07-28",
        "featured_charts": [
            {"id": "chart-001", "svg": "<svg/>", "_defer": {"closes": [1.0, 2.0],
                                                            "dates": ["a", "b"],
                                                            "marker_index": 1,
                                                            "subtitle": "s"}},
            {"id": "chart-002", "svg": "<svg/>", "_defer": {"closes": [1.0, 2.0],
                                                            "dates": ["a", "b"],
                                                            "marker_index": 1,
                                                            "subtitle": "s"}},
            {"id": "chart-003", "svg": "<svg/>", "_defer": {"closes": [1.0, 2.0],
                                                            "dates": ["a", "b"],
                                                            "marker_index": 1,
                                                            "subtitle": "s"}},
            {"id": "chart-900", "svg": "<svg/>"},  # reach-lane card, no blob
        ],
        "accounts": [{"id": "flagship", "queue": [
            {"slot": "D1-S1", "chart_id": "chart-001", "sentinel_ok": True},
            {"slot": "D1-S2", "chart_id": "chart-002", "sentinel_ok": False,
             "status": "quarantined"},
            {"slot": "D2-S1", "chart_id": "chart-003", "sentinel_ok": True},
        ]}],
    }

    orig = cs._attach_chart_media
    cs._attach_chart_media = _fake_attach
    try:
        counts = cs.raster_plan_media(plan, cfg={"publish": {"media_enabled": True}},
                                      root=None)
    finally:
        cs._attach_chart_media = orig

    assert calls == ["chart-001"], (
        f"rastered {calls} — expected only the surviving D1 card. A quarantined "
        "post and a D2 post can never carry an image, so neither may cost a "
        "Chrome launch."
    )
    assert counts["rastered"] == 1
    assert counts["pruned"] == 2

    kept = {c["id"] for c in plan["featured_charts"]}
    assert kept == {"chart-001", "chart-900"}, (
        f"kept {kept} — non-shipping cards must be pruned out of the artifact "
        "(each SVG is ~45KB), and reach-lane cards must be kept"
    )
    assert all("_defer" not in c for c in plan["featured_charts"]), (
        "the internal deferral blob leaked into the written artifact"
    )


def test_defer_media_leaves_no_scaffolding_when_no_raster_pass_runs():
    """defer_media is internal: a caller that never runs the raster pass must
    still be able to serialize the plan."""
    import json

    from engine.marketing.content_studio import content_plan, raster_plan_media

    dates, closes = _series()
    plans = [_plan("PLTR", entry=closes[-1], signal_date=_FRESH)]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b", "voice": "authoritative desk"},
    ]}}
    plan = content_plan(cfg, plans, closes_loader=lambda t: (dates, closes),
                        root=ROOT, defer_media=True)
    raster_plan_media(plan, cfg={"publish": {"media_enabled": False}}, root=None)
    json.dumps(plan)  # must not raise on a stray non-serializable blob
    assert all("_defer" not in c for c in plan.get("featured_charts") or [])


# ---------------------------------------------------------------------------
# 6. The Sentinel media cap must not cost a desk its posts
# ---------------------------------------------------------------------------

def test_ramp_media_cap_never_sits_below_the_post_cap():
    """A media cap BELOW the post cap does not strip the image — it QUARANTINES
    the post (reason media_cap_daily). With every ticker post now carrying a
    chart, a lower media cap would silently halve a cold desk's daily volume.
    The base block already states the two "must move together"; the ramp tiers
    have to honour it as well."""
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    ramp = (cfg.get("sentinel") or {}).get("ramp") or {}
    tiers = {k: v for k, v in ramp.items() if isinstance(v, dict)}
    assert tiers, "no ramp tiers found — the guard would pass vacuously"

    for name, row in tiers.items():
        posts = row.get("max_posts_per_account_per_day")
        media = row.get("max_media_posts_per_account_per_day")
        if posts is None or media is None:
            continue
        if media == -1:
            continue  # unlimited
        assert media >= posts, (
            f"ramp tier {name}: max_media_posts_per_account_per_day={media} is "
            f"below max_posts_per_account_per_day={posts}. Every ticker post "
            f"carries a chart, so {posts - media} post(s)/day would be "
            f"quarantined as media_cap_daily rather than shipped."
        )


# ---------------------------------------------------------------------------
# 7. Volume: a demoted signal is publishable, but only as a WATCH
# ---------------------------------------------------------------------------

def test_a_stale_signal_emits_as_a_watch_and_never_as_a_signal():
    """39 of 47 Prophet signals are past the 10-day window on any given day. The
    outbox used to drop every one of them, so 6 desks published ~5 posts total.
    They now emit — as watchlist posts with no entry claim — but an item that is
    STILL typed `signal` and failed the live gate must never reach the queue."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = {
        "as_of": "2026-07-28",
        "featured_charts": [],
        "accounts": [{"id": "flagship", "queue": [
            # Demoted: no entry claim, must ship.
            {"slot": "D1-S1", "type": "watchlist", "ticker": "AAA",
             "headline": "Watching $AAA", "body": "On the radar.",
             "_live_gate_fail": "signal is 20d old (max 10d)", "sentinel_ok": True},
            # Still claiming an entry on a dead signal: must NOT ship.
            {"slot": "D1-S2", "type": "signal", "ticker": "BBB",
             "headline": "In on $BBB at 10", "body": "Entry 10, target 12.",
             "_live_gate_fail": "signal is 20d old (max 10d)", "sentinel_ok": True},
        ]}],
    }
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        summary = emit_from_content_plan(plan, root=Path(td), cfg={})
        import json as _json
        items_p = Path(td) / "data" / "marketing" / "outbox" / "items.jsonl"
        items = [_json.loads(x) for x in items_p.read_text().splitlines() if x.strip()]

    kinds = {i["kind"] for i in items}
    assert "watchlist" in kinds, (
        "the demoted watch post was dropped — this is the drop that was costing "
        "the network almost its entire daily volume"
    )
    assert "signal" not in kinds, (
        "a stale signal reached the queue STILL CLAIMING AN ENTRY — the live gate "
        "must keep barring that, it is the whole reason the gate exists"
    )
    assert summary["skipped_gate"] == 1


def test_runaway_watch_copy_never_claims_the_name_is_near_entry():
    """A name that blew through the entry gets its own template family. The
    ordinary watchlist bank is proximity copy ("Near entry", "close, not
    triggered") and every line of it is a false statement about our own book once
    price is well past the level."""
    from engine.marketing.copywriter import (
        WATCH_RUNAWAY, watch_reason_from_gate, build_context,
        write_posts_deterministic,
    )

    assert watch_reason_from_gate("ran away +18.2% — no longer actionable") == WATCH_RUNAWAY
    assert watch_reason_from_gate("underwater -3.3% (last=1, entry=2)") == "underwater"
    assert watch_reason_from_gate("signal is 20d old (max 10d)") == "stale"
    # Unrecognised prose must fall to the bucket that claims the least.
    assert watch_reason_from_gate("something new the gate learned to say") == "stale"

    banned = ("near entry", "close, not triggered", "closest name to triggering",
              "near the level", "it's close")
    for voice in ("authoritative desk", "dry, receipts-forward", "specialist",
                  "educational", "fast, reactive", "pattern/history"):
        ctx = build_context({
            "type": "watchlist", "ticker": "AAA", "account": "flagship",
            "slot": "D1-S1", "watch_reason": WATCH_RUNAWAY,
        }, persona=None, facts=None, extra=None)
        ctx["voice"] = voice
        ctx["type"] = "watchlist"
        post = write_posts_deterministic([ctx])[0]
        blob = f"{post['headline']} {post['body']}".lower()
        hit = [p for p in banned if p in blob]
        assert not hit, (
            f"{voice}: runaway watch copy claims proximity {hit} — "
            f"got {post['headline']!r} / {post['body']!r}"
        )


def test_every_enabled_desk_has_its_own_template_bank():
    """Two desks sharing a `voice` draw the SAME deterministic template bank, so
    their posts come out near-identical and the cross-account near-dup guard
    quarantines whichever the gate reaches second. On 2026-07-28 meagan (voice
    twin of founder) shipped 0 posts and sophia (twin of flagship) shipped 1."""
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    from engine.marketing.content_studio import (  # noqa: PLC0415
        _COPY_TEMPLATES, _drafts_nightly_copy,
    )

    # SCOPED TO THE DESKS THAT ACTUALLY DRAFT (2026-08-02). A desk with no
    # `copywriter.personas` block is a WIRE relay: content_plan gives it an empty
    # nightly queue by construction, so it draws no template bank and cannot
    # collide in one. Scoping here is what lets mastermind_news arm at all — it
    # is persona-less on purpose (house wire voice, charter §4) and would
    # otherwise have to borrow a drafting desk's voice key to pass.
    enabled = [a for a in cfg["desk_network"]["accounts"] if a.get("enabled")]
    assert enabled, "no enabled desks — the guard would pass vacuously"
    drafting = [a for a in enabled if _drafts_nightly_copy(cfg, a["id"])]
    assert drafting, "no drafting desks — the guard would pass vacuously"

    by_voice: dict[str, list[str]] = {}
    for a in drafting:
        by_voice.setdefault(str(a.get("voice", "")), []).append(a["id"])
    shared = {v: ids for v, ids in by_voice.items() if len(ids) > 1}
    assert not shared, (
        f"desks sharing a voice (and therefore a template bank): {shared}. "
        f"The later desk will be near-dup quarantined into near-silence."
    )

    # AND THE COLLISION THE STRING COMPARISON ABOVE CANNOT SEE. `_get_copy` falls
    # back to the "authoritative desk" bank on an unrecognised voice, so giving a
    # colliding desk a brand-new voice string turns this guard green while the
    # desk silently draws FLAGSHIP's templates instead — the same near-dup
    # quarantine, now invisible. Every drafting desk's voice must be a real key
    # in _COPY_TEMPLATES, so "distinct" means distinct banks, not distinct words.
    known = {v for (_t, v) in _COPY_TEMPLATES}
    unbacked = {a["id"]: a.get("voice") for a in drafting
                if str(a.get("voice", "")) not in known}
    assert not unbacked, (
        f"drafting desks whose voice has no template bank: {unbacked}. "
        f"_get_copy falls back to 'authoritative desk', so these silently draft "
        f"the flagship's templates and near-dup against it. Known banks: "
        f"{sorted(known)}"
    )


def test_tape_chart_posts_survive_without_ohlcv_via_the_markerless_card():
    """W1 CI fix (2026-07-29): in a pyarrow-less env (the marketing-engine CI
    lane) or for a ticker outside the OHLCV parquet tree, the v2 candlestick
    cannot load. Tape-variant chart posts used to lose their chart entirely at
    that point and then defer forever at publish under the
    ticker-post-carries-a-chart law. The markerless v1 line card is the honest
    fallback: same chart, NO BUY geometry (a BUY label on a "watching, not
    buying yet" post is the lie the variant split exists to prevent)."""
    from engine.marketing.chart_render import render_signal_chart

    dates = [f"2026-07-{d:02d}" for d in range(1, 29)]
    closes = [100.0 + i * 0.5 for i in range(28)]
    marked = render_signal_chart("PLTR", dates, closes, marker_index=5,
                                 subtitle="$PLTR · signal")
    markerless = render_signal_chart("PLTR", dates, closes, marker_index=None,
                                     subtitle="$PLTR · tape")
    assert "BUY" in marked
    assert "BUY" not in markerless
    assert markerless.startswith("<svg") and "polyline" in markerless


# ─────────────────────────────────────────────────────────────────────────────
# The chart has to draw the thing the copy is about.
#
# render_chart_v2 has supported avwap_overlay / poc_overlay all along. The
# nightly call site built them ONLY when marketing.m2_overlays_always was set,
# and that key is set NOWHERE -- so both went to the renderer as None on every
# chart ever produced. A post read "held 219.90, the average price paid since
# the Jun 26 volume spike" (an AVWAP) or "dipped back to 283.85, the most-traded
# price of the past four months" (a POC) and the picture drew neither.
#
# On a program whose first law is that a ticker post ships a picture, a picture
# that does not support its own claim is the defect wearing a disguise.
# ─────────────────────────────────────────────────────────────────────────────
class TestChartDrawsWhatTheCopyClaims:
    def test_the_nightly_builds_overlays_by_default(self):
        """Opt-OUT now. The config key was opt-in and nobody ever opted in."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        assert 'get("m2_overlays_always", True)' in src, (
            "overlays are opt-in again; they were dark on every chart the last "
            "time this defaulted to False"
        )

    def test_overlays_reach_the_renderer(self):
        """Wiring, not intent: the kwargs must actually be passed."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        assert "avwap_overlay=_m2_ovl.get" in src
        assert "poc_overlay=_m2_ovl.get" in src

    def test_build_m2_overlays_returns_both_for_a_real_ticker(self):
        """Exercised against real OHLCV, not a mock: the levels must compute."""
        import pytest
        pytest.importorskip("pandas", reason="CI packs install minimal deps")
        from engine.marketing.chart_render import build_m2_overlays, load_ohlcv_windowed
        loaded = load_ohlcv_windowed("CVI", ".")
        if not loaded:
            pytest.skip("no OHLCV for the fixture ticker in this checkout")
        (dates, o, h, l, c, v), _warm = loaded
        ovl = build_m2_overlays("CVI", dates, o, h, l, c, v, ".")
        assert ovl.get("avwap_overlay"), "AVWAP overlay did not build"
        assert ovl.get("poc_overlay"), "POC overlay did not build"
        assert "poc" in ovl["poc_overlay"], ovl["poc_overlay"].keys()

    def test_the_drawn_chart_actually_labels_the_levels(self):
        """End to end: render and assert the labels are IN the SVG.

        A kwarg that is passed but silently ignored looks identical to a fix.
        """
        import pytest
        pytest.importorskip("pandas", reason="CI packs install minimal deps")
        from engine.marketing.chart_render import (
            build_m2_overlays, load_ohlcv_windowed, render_chart_v2)
        loaded = load_ohlcv_windowed("CVI", ".")
        if not loaded:
            pytest.skip("no OHLCV for the fixture ticker in this checkout")
        (dates, o, h, l, c, v), warm = loaded
        ovl = build_m2_overlays("CVI", dates, o, h, l, c, v, ".")
        svg = render_chart_v2(
            ticker="CVI", dates=dates, o=o, h=h, l=l, c=c, volume=v,
            timeframe="DAILY", warmup=warm, volume_overlay=True,
            subpanel_h=190, height=880, company_name="CVI", logo_root=".",
            avwap_overlay=ovl.get("avwap_overlay"),
            poc_overlay=ovl.get("poc_overlay"), cta=True,
        )
        assert "POC" in svg, "the POC level is not labelled on the chart"
        assert "AVWAP" in svg, "the anchored VWAP is not labelled on the chart"


class TestChartQualityIsVisible:
    """Which renderer drew the image we posted was a fact nobody could check.

    `legacy_png` is a hand-drawn PIL line chart: no candles, no indicators, no
    footer CTA. It exists so a Chrome-less host (CI, the ubuntu publish runner)
    posts a picture rather than bare text.

    ONE committed content_plan.json showing 15 of 23 cards as `legacy_png` was
    read three ways in two days: as an audit finding ("65% of images are the
    retired legacy chart"); as a REFUTED finding (a census of SVGs on disk found
    every one v2 — but the legacy path emits a PNG, so that check could not
    observe what it was used to rule out); and then as a live production outage.
    It was a LOCAL plan build with Chrome contended by parallel work. Production
    ships the real card: all 21 PNGs the nightly wrote on 2026-07-29 are
    2000x1760, the raster size, against the legacy renderer's 1200x675.

    Three readings, no instrument. The only trace of a fallback was a
    `log.warning` — dropped by GitHub, because this repo's builders log with a
    prefixing format and an annotation must START the line — and nothing counted
    the share. `media_render` is the field that records the answer; this reads it.
    """

    def test_the_census_counts_the_degraded_renderer(self):
        from engine.marketing.content_studio import _chart_quality_census

        out = _chart_quality_census([
            {"id": "chart-001", "media_render": "svg_raster"},
            {"id": "chart-002", "media_render": "legacy_png"},
            {"id": "chart-003", "media_render": "legacy_png"},
        ])
        assert out["rastered"] == 3
        assert out["legacy_fallback"] == 2
        assert out["legacy_share"] == pytest.approx(0.667, abs=0.001)
        assert out["degraded_chart_ids"] == ["chart-002", "chart-003"]

    def test_a_card_that_was_never_rastered_is_not_a_quality_fact(self):
        """Deferred and pruned cards have no media_render. Counting them as
        healthy would inflate the share; counting them as degraded would cry
        wolf on cards no post carries."""
        from engine.marketing.content_studio import _chart_quality_census

        out = _chart_quality_census([
            {"id": "chart-001", "media_render": "svg_raster"},
            {"id": "chart-002"},                       # deferred, never rastered
            {"id": "chart-003", "media_render": ""},   # ditto
        ])
        assert out["rastered"] == 1
        assert out["legacy_share"] == 0.0

    def test_a_degraded_batch_reaches_the_console_as_a_line_start_warning(self, capsys):
        """CLAUDE.md: an annotation that does not start the line is dropped by
        GitHub, which is how this shipped dead five times before #3587."""
        from engine.marketing.content_studio import _chart_quality_census

        _chart_quality_census([
            {"id": "chart-001", "media_render": "legacy_png"},
            {"id": "chart-002", "media_render": "svg_raster"},
        ])
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "marketing-chart-quality" in ln)
        assert line.startswith("::warning title=marketing-chart-quality::"), line
        assert "50%" in line

    def test_a_clean_batch_does_not_cry_wolf(self, capsys):
        from engine.marketing.content_studio import _chart_quality_census

        _chart_quality_census([{"id": "c", "media_render": "svg_raster"}])
        out = capsys.readouterr().out
        assert "::notice title=marketing-chart-quality::" in out
        assert "::warning" not in out

    def test_the_raster_retries_once_before_accepting_a_worse_picture(self):
        """A single failed Chrome launch used to decide the image a live account
        posts. The raster is deterministic and writes only inside its own temp
        dir, so one retry is safe — and it is bounded at one so a genuinely
        Chrome-less host does not pay two doomed launches per card."""
        import inspect
        from engine.marketing import media_publish

        src = inspect.getsource(media_publish.publish_card)
        assert "for _attempt in (1, 2)" in src, "the retry is gone"
        assert "find_chrome()" in src, (
            "without the no-binary short-circuit, a Chrome-less host pays two "
            "doomed launches for every card"
        )

    # The forensic "which renderer drew this card" pin lives in
    # tests/test_marketing_chart_png.py, not here. It rasters a real legacy card,
    # which needs PIL — and PIL is installed by exactly one job
    # (marketing-media-pipeline: pytest+pyyaml+pillow). Written here it guarded
    # nothing twice over: this file's lanes install pandas/numpy but NOT pillow,
    # so render_signal_chart_png hit its own fail-soft ("PIL/share_cards
    # unavailable — no PNG"), returned b"", and the test asserted PNG magic bytes
    # against an empty string. Its importorskip named numpy, which the renderer
    # does not use, so the guard could not even skip itself out of the way.
