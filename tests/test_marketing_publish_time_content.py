"""tests/test_marketing_publish_time_content.py — publish-time mover/theme lane.

Covers engine/marketing/publish_time_content.py (the publish-time generator that
builds honest live-tape mover/theme_list posts inside the publisher's slot runs)
and the scoped auto-approve exception added to scripts/marketing_publisher.py.

Conventions mirror tests/test_marketing_live_verify.py and
tests/test_marketing_publisher_autoapprove.py: tmp_path roots, injected now= for
determinism, ZERO network, engine/runner modules imported inside each test.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.marketing import outbox, publish_time_content as pt


# Thursday 2026-07-23, 14:05 UTC == 10:05 ET → the AM slot, mid-session.
NOW = datetime(2026, 7, 23, 14, 5, 0, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
TODAY = NOW.strftime("%Y-%m-%d")
NOW_ISO = NOW.strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _write_snapshot(tmp: Path, quotes: dict, *, asof: str = NOW_ISO,
                    ts_ms: int | None = NOW_MS) -> None:
    """Write a live_quotes_snapshot.json (the freshest tape tier)."""
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    q = {t: {"price": v[0], "prevClose": v[1], "changePct": v[2],
             **({"ts": ts_ms} if ts_ms is not None else {})}
         for t, v in quotes.items()}
    (p / "live_quotes_snapshot.json").write_text(
        json.dumps({"asof": asof, "quotes": q}), encoding="utf-8")


def _write_sp500(tmp: Path, tiles: list[dict], *, asof: str = "2026-07-22") -> None:
    p = tmp / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "sp500_heatmap.json").write_text(
        json.dumps({"asof": asof, "tiles": tiles}), encoding="utf-8")


def _write_themes(tmp: Path, tiles: list[dict]) -> None:
    p = tmp / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "themes_heatmap.json").write_text(
        json.dumps({"tiles": tiles}), encoding="utf-8")


def _tile(t: str, pct: float, *, name: str | None = None, sector: str = "Tech") -> dict:
    return {"t": t, "name": name or t, "sector": sector, "perf": {"1D": pct}}


def _theme_tile(theme: str, members: dict[str, float]) -> dict:
    return {"t": theme[:3].upper(), "name": theme, "sector": theme, "perf": {"1D": 0.0},
            "members": [{"t": t, "perf": {"1D": p}} for t, p in members.items()]}


def _cfg(*, accounts: list[dict] | None = None, channels: dict | None = None,
         personas: dict | None = None, enabled: bool = True,
         max_per_run: int = 2, sentinel: dict | None = None) -> dict:
    """A publish config with the publish_time_movers block + desk network."""
    accounts = accounts or [
        {"id": "flagship", "voice": "authoritative desk"},
        {"id": "theme_desk", "voice": "specialist"},
        {"id": "research_b", "voice": "fast, reactive"},
    ]
    channels = channels if channels is not None else {
        "flagship": "c1", "theme_desk": "c2", "research_b": "c3"}
    personas = personas if personas is not None else {
        "flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"},
        "theme_desk": {"name": "The Specialist", "voice_notes": "spicy. Emoji budget: 1"},
        "research_b": {"name": "The Tape Reader", "voice_notes": "clipped. Emoji budget: 1"},
    }
    cfg: dict = {
        "publish": {
            "publish_time_movers": {
                "enabled": enabled, "max_per_run": max_per_run,
                "min_abs_mover_pct": 3.0, "min_abs_theme_pct": 1.0,
                "max_quote_age_min": 45,
                # Unit fixtures are a handful of tiles — pin the flat-tape belt
                # to 1 so it only fires in its own dedicated tests.
                "min_active_tiles": 1,
                # Per-call lane allowlist (XG-W1). The fixture opts every account
                # it declares INTO the lane, so these tests keep exercising the
                # multi-account fan-out they were written for. The production
                # default is restrictive (flagship + founder only) and is covered
                # by its own tests below — do not delete this key to "simplify".
                "accounts": [str(a.get("id", "")) for a in accounts],
            },
            "channels": channels,
        },
        "desk_network": {"accounts": accounts},
        "copywriter": {"personas": personas},
    }
    if sentinel is not None:
        cfg["sentinel"] = sentinel
    return cfg


def _gen(tmp: Path, cfg: dict, *, now: datetime = NOW, live: bool = True,
         approved_due=None, cap: int = 2, account_filter=None) -> dict:
    state = outbox.fold_state(tmp)
    return pt.generate_slot_items(
        tmp, cfg=cfg, now=now, state=state, approved_due=approved_due or [],
        posted_counts={}, cap=cap, live=live, account_filter=account_filter)


#: The GENUINE card resolver, captured before any fixture can patch it. The
#: autouse stub below replaces pt._resolve_card for every test in this file, so a
#: fixture that tried to "un-stub" by reading the attribute at call time would
#: just re-install the stub.
_REAL_RESOLVE_CARD = pt._resolve_card


#: A hosted card, the shape _resolve_card returns on its happy path.
def _fake_card(cand, *, root, cfg, as_of, now, slot):
    tag = (cand.get("ticker") or cand.get("_lead_ticker") or "x").lower()
    return {
        "media": {"kind": "chart_svg", "chart_id": f"stub-{tag}",
                  "path": f"data/marketing/outbox/media/{as_of}/stub-{tag}.svg",
                  "media_url": f"https://cards.example/{tag}.png"},
        "published": {"chart_id": f"stub-{tag}"},
        "reason": "ok",
    }


@pytest.fixture(autouse=True)
def _stub_card(monkeypatch):
    """Every pre-existing test in this file predates the card requirement.

    From 2026-07-31 the lane refuses to enqueue a mover/theme item whose card
    cannot be HOSTED (a rollup with no picture is quarantined by the
    bare-cashtag law, so shipping one is shipping a dead item). Under tmp_path
    there is no R2 and no renderer, so without a stub every one of those tests
    would be asserting the drop path instead of the behaviour it was written for.
    The card path itself is covered for real — renderers live, publish_card
    mocked — in section 12 below.
    """
    monkeypatch.setattr(pt, "_resolve_card", _fake_card)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Overlay
# ─────────────────────────────────────────────────────────────────────────────

def test_overlay_replaces_stale_heatmap_pct_with_snapshot():
    """A stale heatmap 1D is replaced by the snapshot's live change_pct."""
    movers = {"sp500_tiles": [_tile("AMD", 0.1)],
              "theme_tiles": [], "asof": "2026-07-22"}
    tape = {"quotes": {"AMD": {"change_pct": 4.2, "price": 150.0, "ts_ms": NOW_MS,
                               "source": "quotes"}},
            "asof": NOW_ISO, "source": "snapshot"}
    out = pt._overlay_movers(movers, tape)
    assert out["sp500_tiles"][0]["perf"]["1D"] == 4.2
    # Source dict was NOT mutated in place.
    assert movers["sp500_tiles"][0]["perf"]["1D"] == 0.1


def test_overlay_drops_tiles_without_live_quote_when_feed_present():
    """With a snapshot feed, tiles/members lacking a live quote are dropped."""
    movers = {
        "sp500_tiles": [_tile("AMD", 0.1), _tile("STALE", -5.0)],
        "theme_tiles": [_theme_tile("AI", {"NVDA": 0.0, "GHOST": 0.0})],
        "asof": "2026-07-22",
    }
    tape = {"quotes": {"AMD": {"change_pct": 4.2, "ts_ms": NOW_MS, "source": "quotes"},
                       "NVDA": {"change_pct": 2.6, "ts_ms": NOW_MS, "source": "quotes"}},
            "asof": NOW_ISO, "source": "snapshot"}
    out = pt._overlay_movers(movers, tape)
    sp_tickers = [t["t"] for t in out["sp500_tiles"]]
    assert sp_tickers == ["AMD"]                      # STALE dropped (no live quote)
    theme_members = [m["t"] for m in out["theme_tiles"][0]["members"]]
    assert theme_members == ["NVDA"]                  # GHOST dropped


def test_overlay_heatmap_only_keeps_all_tiles():
    """Heatmap-only tape (no snapshot/display): the tiles ARE the source → keep all."""
    movers = {"sp500_tiles": [_tile("AMD", 5.0), _tile("MSFT", -6.0)],
              "theme_tiles": [], "asof": NOW_ISO}
    tape = {"quotes": {"AMD": {"change_pct": 5.0, "source": "heatmap"},
                       "MSFT": {"change_pct": -6.0, "source": "heatmap"}},
            "asof": None, "source": "heatmap"}
    out = pt._overlay_movers(movers, tape)
    assert sorted(t["t"] for t in out["sp500_tiles"]) == ["AMD", "MSFT"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Freshness gate
# ─────────────────────────────────────────────────────────────────────────────

def test_freshness_gate_stale_tape_generates_nothing(tmp_path):
    """Stale tape (old asof, no per-ticker ts) → zero candidates, reason 'tape stale'."""
    # Heatmap-only source, asof two days old, NO per-ticker ts in the snapshot.
    _write_sp500(tmp_path, [_tile("AMD", 5.0)], asof="2026-07-21")
    rep = _gen(tmp_path, _cfg(), live=False)
    assert rep["generated"] == []
    assert rep["would_generate"] == []
    assert any(d["reason"] == "tape stale" for d in rep["dropped"])


def test_freshness_gate_fresh_snapshot_passes(tmp_path):
    """A fresh per-ticker snapshot ts clears the freshness gate."""
    _write_sp500(tmp_path, [_tile("AMD", 0.1)])
    _write_snapshot(tmp_path, {"AMD": (150.0, 144.0, 4.2)})
    rep = _gen(tmp_path, _cfg(), live=False)
    assert not any(d["reason"] == "tape stale" for d in rep["dropped"])
    assert len(rep["would_generate"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Copy (reuse-only v3 banks)
# ─────────────────────────────────────────────────────────────────────────────

def test_mover_copy_has_cashtag_and_live_pct(tmp_path):
    """A generated mover item's text contains the cashtag and the LIVE pct,
    with zero copy violations (whitelisted)."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, name="Intuitive", sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    items = outbox.read_items(tmp_path)
    mv = next(i for i in items if i["kind"] == "mover")
    assert "$ISRG" in mv["text"]
    assert "-14.0%" in mv["text"]          # the LIVE overlaid pct, not the stale 0.1


def test_theme_copy_has_members_and_ends_with_question(tmp_path):
    """A generated theme item has ≥4 member cashtags and its body ends with '?'."""
    _write_themes(tmp_path, [_theme_tile("Artificial Intelligence", {
        "NVDA": 0.0, "AMD": 0.0, "SMCI": 0.0, "MU": 0.0, "AVGO": 0.0})])
    _write_snapshot(tmp_path, {
        "NVDA": (120.0, 117.0, 2.6), "AMD": (150.0, 144.0, 4.2),
        "SMCI": (40.0, 37.0, 8.1), "MU": (100.0, 96.0, 4.1),
        "AVGO": (170.0, 165.0, 3.0)})
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    import re
    cashtags = set(re.findall(r"\$[A-Z]{1,5}", tl["text"]))
    assert len(cashtags) >= 4
    assert tl["text"].rstrip().endswith("?")


def test_copy_differs_across_accounts_same_slot(tmp_path):
    """Two accounts with different voices produce different mover texts for the
    same slot (the LIVE-<slot> hash key + voice vary the chosen template)."""
    # Two big movers so two accounts each get one this run.
    _write_sp500(tmp_path, [
        _tile("ISRG", 0.1, sector="Health Care"),
        _tile("BA", 0.1, sector="Industrials"),
    ])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0),
                               "BA": (150.0, 174.0, -13.0)})
    # No themes → both candidates are movers → two accounts get one each.
    rep = _gen(tmp_path, _cfg(max_per_run=2))
    movers = [i for i in outbox.read_items(tmp_path) if i["kind"] == "mover"]
    assert len(movers) == 2
    assert movers[0]["account"] != movers[1]["account"]
    assert movers[0]["text"] != movers[1]["text"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fail-closed copy
# ─────────────────────────────────────────────────────────────────────────────

def test_copy_violation_drops_candidate(tmp_path, monkeypatch):
    """A validate_copy violation drops the candidate; nothing is enqueued."""
    from engine.marketing import copywriter
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    def _bad(contexts):
        return [{"headline": "bad", "body": "copy", "violations": ["banned vocab: 'x'"],
                 "mode": "deterministic"} for _ in contexts]

    monkeypatch.setattr(copywriter, "write_posts_deterministic", _bad)
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    assert outbox.read_items(tmp_path) == []
    assert any(d["reason"] == "copy_violation" for d in rep["dropped"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. Caps / spacing
# ─────────────────────────────────────────────────────────────────────────────

def test_account_at_ledger_daily_cap_gets_nothing(tmp_path):
    """An account whose ledger-based posts-today already hit the cap is skipped."""
    # flagship is the only channel'd account; it already posted `cap` items today
    # (ledger `at` == today, status posted).
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    # Seed two posted items today (as_of yesterday to prove ledger-based counting,
    # not as_of-based). Transition them to posted so the last ledger `at` is today
    # — stamped from the test clock, or the fixture breaks past UTC midnight.
    # Texts are DEEPLY distinct (token Jaccard < 0.7) so the enqueue-time near-dup
    # guard (2026-07-27) does not collapse the two into one — this test needs both
    # to reach the cap.
    _posted_texts = [
        "Gold cleared its downtrend line on the strongest volume in weeks.",
        "Regional banks stabilized after deposit outflows finally slowed.",
    ]
    for n in range(2):
        it = outbox.make_item(account="flagship", kind="signal",
                              text=_posted_texts[n],
                              as_of="2026-07-22", provenance="content_studio", now=NOW)
        outbox.enqueue(it, root=tmp_path, max_per_account_day=99)
        outbox.transition(it["id"], "approved", actor="t", root=tmp_path, now=NOW)
        outbox.transition(it["id"], "posting", actor="t", root=tmp_path, now=NOW)
        outbox.transition(it["id"], "posted", actor="t", root=tmp_path, now=NOW)

    rep = _gen(tmp_path, only_flagship, cap=2)
    assert rep["generated"] == []
    assert any(d["reason"] == "no_account" for d in rep["dropped"])


def test_account_with_approved_due_this_run_gets_nothing(tmp_path):
    """An account already carrying an approved_due item this run is skipped
    (spacing law: one post per account per slot run)."""
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    prelim = [{"account": "flagship", "id": "x", "kind": "signal"}]
    state = outbox.fold_state(tmp_path)
    rep = pt.generate_slot_items(tmp_path, cfg=only_flagship, now=NOW, state=state,
                                 approved_due=prelim, posted_counts={}, cap=5, live=True)
    assert rep["generated"] == []
    assert any(d["reason"] == "no_account" for d in rep["dropped"])


def test_second_candidate_goes_to_next_account(tmp_path):
    """Two candidates → two distinct accounts (at most one per account per run)."""
    _write_sp500(tmp_path, [
        _tile("ISRG", 0.1, sector="Health Care"),
        _tile("BA", 0.1, sector="Industrials"),
    ])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0),
                               "BA": (150.0, 174.0, -13.0)})
    rep = _gen(tmp_path, _cfg(max_per_run=2))
    items = outbox.read_items(tmp_path)
    assert len(items) == 2
    assert len({i["account"] for i in items}) == 2


def test_max_per_run_respected(tmp_path):
    """max_per_run=1 caps the run at a single new item even with more candidates."""
    _write_sp500(tmp_path, [
        _tile("ISRG", 0.1, sector="Health Care"),
        _tile("BA", 0.1, sector="Industrials"),
    ])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0),
                               "BA": (150.0, 174.0, -13.0)})
    rep = _gen(tmp_path, _cfg(max_per_run=1))
    assert len(rep["generated"]) == 1
    assert len(outbox.read_items(tmp_path)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. Dedupe / idempotency
# ─────────────────────────────────────────────────────────────────────────────

def test_existing_today_mover_blocks_regeneration(tmp_path):
    """An existing today mover item with the same source.ticker blocks regen."""
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    # Seed a mover for ISRG created today (any account/status).
    seed = outbox.make_item(account="theme_desk", kind="mover",
                            text="$ISRG down big today. Watching.",
                            as_of=TODAY, provenance="content_studio", now=NOW,
                            source={"ticker": "ISRG"})
    outbox.enqueue(seed, root=tmp_path, max_per_account_day=99)

    rep = _gen(tmp_path, only_flagship)
    assert rep["generated"] == []
    assert any(d["reason"] == "dup_today_mover" for d in rep["dropped"])


def test_same_slot_rerun_is_idempotent(tmp_path):
    """Re-running the same slot with identical tape → outbox 'duplicate', no 2nd item."""
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep1 = _gen(tmp_path, only_flagship)
    assert len(rep1["generated"]) == 1
    n_after_first = len(outbox.read_items(tmp_path))

    # Identical tape, fresh fold → the per-day dedupe fires first (same ticker
    # already has a mover today), so nothing new is written.
    rep2 = _gen(tmp_path, only_flagship)
    assert rep2["generated"] == []
    assert len(outbox.read_items(tmp_path)) == n_after_first


def test_duplicate_result_reported_when_dedupe_bypassed(tmp_path, monkeypatch):
    """When the per-day dedupe is bypassed, an identical text still hashes to the
    same id → outbox returns 'duplicate' (idempotent), reported quietly."""
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep1 = _gen(tmp_path, only_flagship)
    gen_id = rep1["generated"][0]

    # Two publisher-tier guards normally stop a re-gen before enqueue: the
    # per-day dedupe corpus AND the "already queued this lane today" account
    # guard. Neutralize BOTH so the identical candidate reaches enqueue again —
    # enqueue's own id-dedupe (same text → same sha1 id) is the last line and
    # must return 'duplicate' (idempotent), which the module reports quietly.
    monkeypatch.setattr(pt, "_existing_today_items", lambda state, today: [])
    monkeypatch.setattr(pt, "_live_pending_pt_today", lambda state, today: [])
    monkeypatch.setattr(pt, "_live_occupying_pt_today", lambda state, today: [])
    rep2 = _gen(tmp_path, only_flagship)
    assert rep2["generated"] == []
    assert any(d["reason"] == "duplicate" and gen_id in d["detail"]
               for d in rep2["dropped"])


# ─────────────────────────────────────────────────────────────────────────────
# 7. Near-dup
# ─────────────────────────────────────────────────────────────────────────────

def test_near_dup_vs_existing_today_drops_candidate(tmp_path):
    """A candidate whose text is ≥0.5 jaccard vs an existing today item is dropped."""
    only_flagship = _cfg(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                         channels={"flagship": "c1"})
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    # Discover the exact text the generator will produce (dry run), then seed a
    # near-identical existing item under a DIFFERENT ticker (so the mover-ticker
    # per-day dedupe can't fire) — only the near-dup jaccard gate can catch it.
    dry = _gen(tmp_path, only_flagship, live=False)
    assert dry["would_generate"]
    seed_text = dry["would_generate"][0]["text"]  # the mover text (short → full)
    seed = outbox.make_item(account="theme_desk", kind="chart",
                            text=seed_text + " extra tail words here",
                            as_of=TODAY, provenance="content_studio", now=NOW,
                            source={"ticker": "OTHER"})
    outbox.enqueue(seed, root=tmp_path, max_per_account_day=99)

    rep = _gen(tmp_path, only_flagship)
    assert rep["generated"] == []
    assert any(d["reason"] == "near_dup_today" for d in rep["dropped"])


# ─────────────────────────────────────────────────────────────────────────────
# 8. Source stamp + gate round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_source_stamp_baseline_pct_and_gate_post(tmp_path):
    """The generated item's source.baseline_pct equals the live pct and
    live_verify.verify_item(item, live=same tape) → 'post'."""
    from engine.marketing import live_verify
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    cfg = _cfg()
    rep = _gen(tmp_path, cfg)
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")
    assert mv["source"]["baseline_pct"] == -14.0
    assert mv["source"]["ticker"] == "ISRG"
    assert mv["source"]["quote_source"] == rep["quote_source"]

    tape = live_verify.load_live_quotes(tmp_path)
    v = live_verify.verify_item(mv, live=tape, now=NOW, cfg=cfg)
    assert v["action"] == "post"


def test_source_stamp_sign_flip_tape_quarantines(tmp_path):
    """With a sign-flipped tape at post time, the gate quarantines the item."""
    from engine.marketing import live_verify
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    cfg = _cfg()
    _gen(tmp_path, cfg)
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")

    # A later tape where ISRG flipped to +2% → the -14% claim is stale.
    flipped = {"quotes": {"ISRG": {"change_pct": 2.0, "price": 356.0,
                                   "ts_ms": NOW_MS, "source": "quotes"}},
               "asof": NOW_ISO, "source": "snapshot"}
    v = live_verify.verify_item(mv, live=flipped, now=NOW, cfg=cfg)
    assert v["action"] == "quarantine"


def test_theme_stamp_uses_lead_member(tmp_path):
    """A theme item stamps the LEAD member's ticker + pct (the loudest number),
    and the gate verifies against that exact figure."""
    from engine.marketing import live_verify
    _write_themes(tmp_path, [_theme_tile("Artificial Intelligence", {
        "NVDA": 0.0, "AMD": 0.0, "SMCI": 0.0, "MU": 0.0, "AVGO": 0.0})])
    _write_snapshot(tmp_path, {
        "NVDA": (120.0, 117.0, 2.6), "AMD": (150.0, 144.0, 4.2),
        "SMCI": (40.0, 37.0, 8.1), "MU": (100.0, 96.0, 4.1),
        "AVGO": (170.0, 165.0, 3.0)})
    cfg = _cfg()
    _gen(tmp_path, cfg)
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    # The stamped baseline is a MEMBER's pct (the lead member), not the +4.4% agg.
    assert tl["source"]["theme"] == "Artificial Intelligence"
    assert tl["source"]["ticker"] in {"NVDA", "AMD", "SMCI", "MU", "AVGO"}
    assert tl["source"]["agg_pct"] == 4.4          # the aggregate is stamped separately
    lead_pct = tl["source"]["baseline_pct"]
    assert lead_pct in (2.6, 4.2, 8.1, 4.1, 3.0)   # a member pct, never the agg
    assert lead_pct != tl["source"]["agg_pct"]     # baseline is NOT the aggregate
    tape = live_verify.load_live_quotes(tmp_path)
    v = live_verify.verify_item(tl, live=tape, now=NOW, cfg=cfg)
    assert v["action"] == "post"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Dry-run
# ─────────────────────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing_and_lists_would_generate(tmp_path):
    """live=False → items.jsonl untouched; report lists would_generate."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    rep = _gen(tmp_path, _cfg(), live=False)
    assert rep["generated"] == []
    assert len(rep["would_generate"]) >= 1
    # No items file written at all.
    assert outbox.read_items(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────────
# 11. enabled default (block absent → disabled)
# ─────────────────────────────────────────────────────────────────────────────

def test_disabled_when_block_absent(tmp_path):
    """A cfg with no publish_time_movers block → generation disabled, enabled False."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    cfg = {"publish": {"channels": {"flagship": "c1"}},
           "desk_network": {"accounts": [{"id": "flagship", "voice": "x"}]},
           "copywriter": {"personas": {}}}
    rep = _gen(tmp_path, cfg)
    assert rep["enabled"] is False
    assert rep["generated"] == []
    assert outbox.read_items(tmp_path) == []


def test_generate_never_raises_on_garbage_state(tmp_path):
    """Fail-soft: a broken state shape yields a report, never an exception."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    rep = pt.generate_slot_items(tmp_path, cfg=_cfg(), now=NOW, state={},
                                 approved_due=[], posted_counts={}, cap=2, live=False)
    assert "enabled" in rep and "dropped" in rep


# ═════════════════════════════════════════════════════════════════════════════
# 10. Auto-approve scoping (scripts/marketing_publisher.py) — parse + config
# ═════════════════════════════════════════════════════════════════════════════

def test_auto_approve_kinds_parses_strictly():
    """publish.auto_approve_kinds: only lowercase strings that are outbox.KINDS
    members survive; junk is ignored."""
    import scripts.marketing_publisher as pub
    got = pub._auto_approve_kinds_cfg({
        "auto_approve_kinds": ["mover", "THEME_LIST", "signal", "not_a_kind", 42, None]})
    # lowercased, KINDS-filtered: mover/theme_list/signal kept; junk dropped.
    assert got == frozenset({"mover", "theme_list", "signal"})


def test_auto_approve_kinds_absent_is_empty():
    import scripts.marketing_publisher as pub
    assert pub._auto_approve_kinds_cfg({}) == frozenset()
    assert pub._auto_approve_kinds_cfg({"auto_approve_kinds": "mover"}) == frozenset()


# ═════════════════════════════════════════════════════════════════════════════
# 11. Template applicability tags (direction / chart) + flat-tape belt
# ═════════════════════════════════════════════════════════════════════════════

# Every voice in the v3 banks. Personas empty → build_context default budgets.
_ALL_VOICES = [
    "authoritative desk", "dry, receipts-forward", "specialist",
    "educational", "fast, reactive", "pattern/history",
]

# Phrases that only make sense on a DOWN tape (from the tagged bank lines) plus
# chart-claim markers a text-only item must never carry.
_DOWN_MARKERS = ("ugly", "dip buyers", "flush", "bottom setup", "catching the drop",
                 "getting hit", "worst first", "selling", "under pressure")
_CHART_MARKERS = ("chart",)


def _mover_candidate(ticker: str, pct: float) -> dict:
    from engine.marketing import movers_source
    mv = {"ticker": ticker, "name": ticker, "pct": pct, "sector": "Tech"}
    return {"type": "mover", "ticker": ticker, "cashtag": f"${ticker}",
            "_mover_data": mv, "_mover_facts": movers_source.mover_facts(mv)}


def _theme_candidate(direction: str) -> dict:
    from engine.marketing import movers_source
    sign = 1.0 if direction == "up" else -1.0
    members = [{"ticker": t, "pct": sign * p}
               for t, p in (("NVDA", 4.1), ("AMD", 3.2), ("SMCI", 2.8), ("AVGO", 2.2))]
    tl = {"theme": "Artificial Intelligence", "direction": direction,
          "tone": "ripping" if direction == "up" else "selling off",
          "members": members, "agg_pct": round(sign * 3.1, 2),
          "question": ("Which one breaks out first?" if direction == "up"
                       else "Which one comes back first?")}
    return {"type": "theme_list", "ticker": "", "cashtags": [f"${m['ticker']}" for m in members],
            "_theme_data": tl, "_theme_facts": movers_source.theme_facts(tl),
            "_lead_ticker": members[0]["ticker"], "_lead_pct": members[0]["pct"],
            "_theme_name": tl["theme"], "_agg_pct": tl["agg_pct"]}


@pytest.mark.parametrize("voice", _ALL_VOICES)
def test_up_mover_copy_never_down_flavored_or_chart_claiming(voice):
    """An UP mover must never render a down-only line ("Ugly.", "dip buyers")
    and a text-only item must never claim an attached chart — across every
    voice, several tickers and all three slots (sweeping the variant hash)."""
    for slot in ("AM", "PM", "EOD"):
        for tkr in ("NVDA", "AMD", "TSLA", "AVGO", "MSFT", "META"):
            text, _hl, viol = pt._render_copy(
                _mover_candidate(tkr, 8.2), account="acct_x", voice=voice,
                persona={}, slot=slot)
            low = text.lower()
            assert not any(m in low for m in _DOWN_MARKERS), (voice, slot, tkr, text)
            assert not any(m in low for m in _CHART_MARKERS), (voice, slot, tkr, text)
            assert viol == [], (voice, slot, tkr, viol)


@pytest.mark.parametrize("voice", _ALL_VOICES)
def test_down_mover_copy_never_chart_claiming(voice):
    """DOWN movers may use the bearish lines, but text-only items must still
    never reference a chart."""
    for slot in ("AM", "PM", "EOD"):
        for tkr in ("ISRG", "ENPH", "PYPL", "NKE", "LULU", "CRM"):
            text, _hl, viol = pt._render_copy(
                _mover_candidate(tkr, -9.1), account="acct_x", voice=voice,
                persona={}, slot=slot)
            assert "chart" not in text.lower(), (voice, slot, tkr, text)
            assert viol == [], (voice, slot, tkr, viol)


@pytest.mark.parametrize("voice", _ALL_VOICES)
def test_up_theme_copy_never_down_flavored(voice):
    """An UP theme must never render a down-only headline ("getting hit",
    "worst first", "under pressure", "group-wide selling")."""
    for slot in ("AM", "PM", "EOD"):
        text, _hl, viol = pt._render_copy(
            _theme_candidate("up"), account="acct_x", voice=voice,
            persona={}, slot=slot)
        low = text.lower()
        assert not any(m in low for m in _DOWN_MARKERS), (voice, slot, text)
        assert viol == [], (voice, slot, viol)


def test_variant_pool_fallback_never_empty():
    """Over-filtering falls back to the full bank instead of crashing: a ctx
    whose direction/chart flags exclude tagged variants still renders."""
    from engine.marketing.copywriter import _TEMPLATES, _variant_allowed
    # "ticker" is not decoration: _variant_allowed also partitions a bank by
    # ticker-dependency, and a mover ctx ALWAYS carries one (_render_copy sets
    # it from candidate["ticker"]). Omitting it here described a context this
    # lane never builds.
    ctx = {"type": "mover", "ticker": "AAPL", "mover_pct": "+8.2%", "has_chart": False}
    pool = [v for v in _TEMPLATES[("mover", "authoritative desk")]
            if _variant_allowed(v, ctx)]
    # The authoritative up+no-chart pool is exactly the one untagged variant.
    assert len(pool) == 1
    assert "biggest move in the index" in pool[0][0]


def test_nightly_path_selection_unchanged_by_tags():
    """A ctx WITHOUT direction/has_chart info (the nightly D-slot shape) filters
    nothing — the pool is the full bank, so nightly selection is unchanged."""
    from engine.marketing.copywriter import _TEMPLATES, _variant_allowed
    for key in (("mover", "authoritative desk"), ("theme_list", "fast, reactive")):
        bank = _TEMPLATES[key]
        # No mover_pct / theme_direction / has_chart. "ticker" IS set, because
        # every real ctx has it (build_context always writes the key) and it now
        # also drives the ticker-dependency partition; a mover bank is entirely
        # cashtag-bearing, so a ticker-less ctx would legitimately select none.
        ctx = {"type": key[0], "ticker": "AAPL"}
        assert [v for v in bank if _variant_allowed(v, ctx)] == list(bank)


def test_flat_tape_belt_skips_closed_market(tmp_path):
    """One rogue -8% print on an otherwise ~0% board (holiday / static splice)
    is refused by the flat-tape belt; a genuinely moving board passes."""
    flat = [_tile(f"T{i:03d}", 0.1) for i in range(30)] + [_tile("ROGUE", -8.0)]
    _write_sp500(tmp_path, flat)
    _write_snapshot(tmp_path, {t["t"]: (100.0, 100.0, t["perf"]["1D"]) for t in flat})
    cfg = _cfg()
    cfg["publish"]["publish_time_movers"]["min_active_tiles"] = 25
    rep = _gen(tmp_path, cfg, live=False)
    assert rep["would_generate"] == []
    assert any(d["reason"] == "tape_flat" for d in rep["dropped"])

    moving = [_tile(f"M{i:03d}", 1.2 if i % 2 else -1.4) for i in range(30)] \
        + [_tile("BIGMV", -8.0)]
    _write_sp500(tmp_path, moving)
    _write_snapshot(tmp_path, {t["t"]: (100.0, 100.0, t["perf"]["1D"]) for t in moving})
    rep2 = _gen(tmp_path, cfg, live=False)
    assert not any(d["reason"] == "tape_flat" for d in rep2["dropped"])
    assert rep2["would_generate"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Per-call lane eligibility (XG-W1 fixes F1/F2/F3)
#
# Both per-call lanes used to filter on acc.get("disabled") ALONE. desk_network
# carries an explicit `enabled`, and accounts._config_enabled gives it precedence
# over `disabled` — so an `enabled: false` account with no `disabled` key passed
# the filter, and a Buffer channel id was then enough to make a deliberately dark
# property a live posting target under an unrestricted auto-approve and a -1 cap.
# ─────────────────────────────────────────────────────────────────────────────

def _two_movers(tmp_path):
    _write_sp500(tmp_path, [
        _tile("ISRG", 0.1, sector="Health Care"),
        _tile("BA", 0.1, sector="Industrials"),
    ])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0),
                               "BA": (150.0, 174.0, -13.0)})


def _real_cfg() -> dict:
    import yaml
    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / "config" / "marketing.yml").read_text(encoding="utf-8"))


def test_enabled_false_account_with_a_channel_is_not_eligible(tmp_path):
    """F1 REGRESSION. `enabled: false` + a channel id must never post.

    The account carries NO `disabled` key on purpose — that is exactly the shape
    the old `acc.get("disabled")` filter waved through.
    """
    _two_movers(tmp_path)
    accounts = [{"id": "flagship", "voice": "authoritative desk"},
                {"id": "mastermind_news", "voice": "fast, reactive", "enabled": False}]
    cfg = _cfg(accounts=accounts,
               channels={"flagship": "c1", "mastermind_news": "c9"},
               personas={"flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"},
                         "mastermind_news": {"name": "Wire", "voice_notes": "wire. Emoji budget: 0"}},
               max_per_run=2)
    _gen(tmp_path, cfg)
    accts = {i["account"] for i in outbox.read_items(tmp_path)}
    assert "mastermind_news" not in accts, "an enabled:false account was queued"


def test_the_committed_config_never_makes_mastermind_news_eligible(tmp_path):
    """The real config, not a fixture: the dark news property must be excluded by
    BOTH the liveness gate and the lane allowlist."""
    cfg = _real_cfg()
    for lane in ("publish_time_movers", "publish_time_read"):
        ids = [str(a.get("id", "")) for a in
               pt._per_call_eligible(cfg, lane_key=lane, root=tmp_path)]
        assert "mastermind_news" not in ids, lane
        assert set(ids) <= {"flagship", "founder"}, (lane, ids)


def test_employees_are_not_eligible_for_the_per_call_lanes(tmp_path):
    """F2 REGRESSION. An ENABLED employee holding a channel id is still excluded
    from both per-call lanes.

    These lanes never consult tilt, so the employee specs' zeroed mover/event
    weights cannot reach them — the allowlist is what enforces the charter's
    "employees launch on non-news/tape kinds" sequencing.
    """
    cfg = _real_cfg()
    live_employees = [a["id"] for a in cfg["desk_network"]["accounts"]
                      if a.get("kind") == "employee" and a.get("enabled")]
    assert len(live_employees) == 4, live_employees
    for lane in ("publish_time_movers", "publish_time_read"):
        ids = {str(a.get("id", "")) for a in
               pt._per_call_eligible(cfg, lane_key=lane, root=tmp_path)}
        assert ids.isdisjoint(live_employees), (lane, ids)
    # ...and each one IS live with a channel, so the exclusion is the lane's
    # doing and not an accident of missing wiring (which would pass vacuously).
    for emp in live_employees:
        assert cfg["publish"]["channels"].get(emp), emp


def test_an_enabled_employee_is_not_selected_by_the_movers_lane(tmp_path):
    """End-to-end through the real generator, not just the helper."""
    _two_movers(tmp_path)
    accounts = [{"id": "flagship", "voice": "authoritative desk", "enabled": True},
                {"id": "meagan", "voice": "fast, reactive", "enabled": True}]
    cfg = _cfg(accounts=accounts,
               channels={"flagship": "c1", "meagan": "c5"},
               personas={"flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"},
                         "meagan": {"name": "Meagan", "voice_notes": "quick. Emoji budget: 1"}},
               max_per_run=2)
    # Drop the fixture's opt-in so the PRODUCTION default allowlist governs.
    del cfg["publish"]["publish_time_movers"]["accounts"]
    _gen(tmp_path, cfg)
    accts = {i["account"] for i in outbox.read_items(tmp_path)}
    assert accts == {"flagship"}, accts


def test_the_lane_allowlist_defaults_restrictive_and_an_empty_list_means_nobody():
    cfg = {"publish": {"channels": {"flagship": "c1", "meagan": "c5"}},
           "desk_network": {"accounts": [
               {"id": "flagship", "enabled": True}, {"id": "meagan", "enabled": True}]}}
    assert pt._lane_accounts(cfg, "publish_time_movers") == frozenset(
        pt._PER_CALL_DEFAULT_ACCOUNTS)

    cfg["publish"]["publish_time_movers"] = {"accounts": []}
    assert pt._lane_accounts(cfg, "publish_time_movers") == frozenset()
    assert pt._per_call_eligible(cfg, lane_key="publish_time_movers", root=".") == []

    cfg["publish"]["publish_time_movers"] = {"accounts": ["meagan"]}
    ids = [a["id"] for a in pt._per_call_eligible(
        cfg, lane_key="publish_time_movers", root=".")]
    assert ids == ["meagan"]


def test_a_junk_lane_allowlist_falls_back_to_the_restrictive_default():
    """Fail-safe, not fail-open: a malformed allowlist must not widen the lane."""
    cfg = {"publish": {"publish_time_movers": {"accounts": "flagship"}}}
    assert pt._lane_accounts(cfg, "publish_time_movers") == frozenset(
        pt._PER_CALL_DEFAULT_ACCOUNTS)


def test_the_operator_override_file_can_still_dark_an_account(tmp_path):
    """Liveness resolves through effective_accounts, so the override file — the
    operator's no-deploy kill switch — reaches these lanes too."""
    d = tmp_path / "data" / "marketing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "account_overrides.json").write_text(
        json.dumps({"flagship": {"enabled": False}}), encoding="utf-8")
    cfg = {"publish": {"channels": {"flagship": "c1"}},
           "desk_network": {"accounts": [{"id": "flagship", "enabled": True}]}}
    assert pt._per_call_eligible(
        cfg, lane_key="publish_time_movers", root=tmp_path) == []


def test_two_accounts_on_one_per_call_lane_never_emit_identical_text(tmp_path):
    """F3 REGRESSION. The codex pass is SUBTRACTIVE — it strips off-signature
    emoji and downgrades ungranted exclamations; it does NOT inject a quirk, so
    it cannot be relied on to differentiate two accounts.

    On the per-call lane the real fence is the allowlist. This test pins what is
    left after it: two allowed accounts must still emit different text, and if a
    future edit makes them identical that is the signal to keep the allowlist
    narrow rather than to widen it.
    """
    _two_movers(tmp_path)
    accounts = [{"id": "flagship", "voice": "authoritative desk", "enabled": True},
                {"id": "founder", "voice": "fast, reactive", "enabled": True}]
    cfg = _cfg(accounts=accounts,
               channels={"flagship": "c1", "founder": "c2"},
               personas={"flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"},
                         "founder": {"name": "The Founder", "voice_notes": "plain. Emoji budget: 0"}},
               max_per_run=2)
    _gen(tmp_path, cfg)
    movers = [i for i in outbox.read_items(tmp_path) if i["kind"] == "mover"]
    assert len(movers) == 2
    assert movers[0]["account"] != movers[1]["account"]
    assert movers[0]["text"] != movers[1]["text"], "two desks emitted identical copy"


# ─────────────────────────────────────────────────────────────────────────────
# 12. The picture. A mover/theme post ships one or it does not ship.
#
# THE DEFECT: this lane was text-only BY CONSTRUCTION ("Items are text-only (no
# media ...)", and chart_render was imported nowhere). #4030's bare-cashtag law
# then made a ticker-naming rollup with no picture unpublishable, so from that
# merge on every item this lane produced was generated, queued and quarantined.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def real_card(monkeypatch):
    """Un-stub _resolve_card and mock only the two things tmp_path cannot give:
    the R2 upload and the network logo fetch. The renderers run for real."""
    from engine.marketing import chart_render, media_publish
    monkeypatch.setattr(pt, "_resolve_card", _REAL_RESOLVE_CARD)  # un-stub
    monkeypatch.setattr(chart_render, "resolve_color_logo", lambda t, r: None)
    return media_publish


def _hosted(**over):
    def _publish_card(svg, *, chart_id, as_of, root=None, legacy_png=None):
        out = {"svg_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.svg",
               "media_png_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.png",
               "media_url": f"https://cards.example/{as_of}/{chart_id}.png"}
        out.update(over)
        return out
    return _publish_card


def _theme_fixture(tmp: Path) -> None:
    _write_themes(tmp, [_theme_tile("Artificial Intelligence", {
        "NVDA": 0.0, "AMD": 0.0, "SMCI": 0.0, "MU": 0.0, "AVGO": 0.0})])
    _write_snapshot(tmp, {
        "NVDA": (120.0, 117.0, 2.6), "AMD": (150.0, 144.0, 4.2),
        "SMCI": (40.0, 37.0, 8.1), "MU": (100.0, 96.0, 4.1),
        "AVGO": (170.0, 165.0, 3.0)})


def test_theme_list_item_ships_a_hosted_card(tmp_path, monkeypatch, real_card):
    """PINS: a theme_list item carries a media[] entry with a public https URL.

    Pre-fix this asserts on `[]` — make_item was never handed media at all — so
    the `len(...) == 1` line is the mutation check for the whole card lane.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _theme_fixture(tmp_path)

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")

    assert len(tl["media"]) == 1, tl["media"]
    entry = tl["media"][0]
    assert entry["kind"] == "chart_svg"
    assert entry["chart_id"].startswith("ptlive-theme-")
    assert entry["media_url"].startswith("https://")
    # The picture names the SAME tickers the copy does — a card listing a name
    # the post never mentions is its own small lie.
    import re as _re
    assert set(entry["tickers"]) <= set(
        t.lstrip("$") for t in _re.findall(r"\$[A-Z]{1,5}", tl["text"]))


def test_mover_item_ships_a_tape_chart_card(tmp_path, monkeypatch, real_card):
    """PINS: a mover item carries a single-name chart card keyed to its ticker."""
    from engine.marketing import chart_render
    monkeypatch.setattr(real_card, "publish_card", _hosted())

    n = 320
    dates = [f"2025-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}" for i in range(n)]
    closes = [100.0 + (i % 17) * 0.7 for i in range(n)]
    bars = (dates, closes, [c + 1 for c in closes], [c - 1 for c in closes],
            closes, [1_000_000.0] * n)
    monkeypatch.setattr(chart_render, "load_ohlcv_windowed",
                        lambda t, r, **kw: (bars, 60))

    _write_sp500(tmp_path, [_tile("ISRG", 0.1, name="Intuitive", sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")
    assert len(mv["media"]) == 1, mv["media"]
    assert mv["media"][0]["ticker"] == "ISRG"
    assert mv["media"][0]["chart_id"].startswith("ptlive-mover-isrg-")
    assert mv["media"][0]["media_url"].startswith("https://")


def test_a_card_that_will_not_host_blocks_the_enqueue(tmp_path, monkeypatch,
                                                      real_card, capsys):
    """PINS the chartless-DEFER law: a rendered-but-unhosted card means NO item.

    publish_card returns without a media_url (exactly what an ubuntu runner with
    no R2 credentials produces). Nothing may be enqueued, the drop must name the
    reason, the tally must count it, and the annotation must START the line.
    Pre-fix the lane enqueued a text-only item here and the assertion on
    `read_items == []` fails.
    """
    monkeypatch.setattr(real_card, "publish_card",
                        lambda svg, **kw: {"svg_path": "x.svg"})   # no media_url
    _theme_fixture(tmp_path)

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    assert outbox.read_items(tmp_path) == []
    assert rep["cards_unhosted"] >= 1, rep
    no_card = [d for d in rep["dropped"] if d["reason"] == "no_card"]
    assert no_card and "no-media-url" in no_card[0]["detail"], rep["dropped"]

    ann = [ln for ln in capsys.readouterr().out.splitlines()
           if "publish-time-card-unhosted" in ln]
    assert ann, "no annotation emitted"
    # A logger-prefixed annotation is silently dropped by GitHub — it must be a
    # bare print that STARTS the line.
    assert ann[0].startswith("::warning title=publish-time-card-unhosted::"), ann[0]


def test_missing_bars_drop_the_mover_rather_than_ship_it_bare(tmp_path, monkeypatch,
                                                              real_card):
    """PINS: no local daily bars → no card → no post (not a bare ticker post)."""
    from engine.marketing import chart_render
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    monkeypatch.setattr(chart_render, "load_ohlcv_windowed", lambda t, r, **kw: None)

    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    assert outbox.read_items(tmp_path) == []
    assert any(d["reason"] == "no_card" and "no-bars" in d["detail"]
               for d in rep["dropped"]), rep["dropped"]


# ─────────────────────────────────────────────────────────────────────────────
# 13. The day-cap bug: a DEAD item may not hold its account hostage
#
# _live_queued_pt_today selected on created_at alone with NO status filter, and
# every account it returned was a hard skip. `state["items"]` freezes `status` at
# "queued" forever (the folded status lives in `state["status"]`), so a posted or
# quarantined item blocked its account for the REST OF THE DAY — the comment said
# "one per account per slot RUN". With two eligible accounts that capped the
# whole network at 2 posts/day, which is what the ledger shows.
# ─────────────────────────────────────────────────────────────────────────────

_ONLY_FLAGSHIP = dict(accounts=[{"id": "flagship", "voice": "authoritative desk"}],
                      channels={"flagship": "c1"})


def _seed_lane_item(tmp: Path, *, status: str) -> str:
    """One publisher_live_movers item created TODAY on flagship, folded to
    `status`. Text is deliberately far from any tape copy so the near-dup gate
    never becomes the reason a later assertion passes."""
    it = outbox.make_item(
        account="flagship", kind="mover",
        text="Gold cleared its downtrend line on the strongest volume in weeks.",
        as_of=TODAY, provenance="publisher_live_movers",
        source={"ticker": "GLD"}, now=NOW)
    outbox.enqueue(it, root=tmp, max_per_account_day=99)
    ladder = {"approved": ["approved"],
              "posted": ["approved", "posting", "posted"],
              "quarantined": ["quarantined"],
              "queued": []}[status]
    for to in ladder:
        outbox.transition(it["id"], to, actor="t", root=tmp, now=NOW)
    return it["id"]


@pytest.mark.parametrize("status,expect_generation", [
    ("posted", True),        # consumed its slot hours ago — must not block
    ("quarantined", True),   # dead — must not block
    ("queued", False),       # still occupying the account's next slot — blocks
    ("approved", False),     # ditto
])
def test_only_a_slot_occupying_lane_item_blocks_its_account(
        tmp_path, status, expect_generation):
    """PINS both halves. The `posted`/`quarantined` rows fail on the pre-fix tree
    (every created-today item blocked); the `queued`/`approved` rows are the
    spacing law the fix must NOT loosen."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    _seed_lane_item(tmp_path, status=status)

    rep = _gen(tmp_path, _cfg(**_ONLY_FLAGSHIP), cap=5)
    if expect_generation:
        assert rep["generated"], rep["dropped"]
    else:
        assert rep["generated"] == []
        assert any(d["reason"] == "no_account" for d in rep["dropped"]), rep


def test_a_posted_lane_item_is_not_double_charged_to_the_day_cap(tmp_path):
    """A posted item is already counted by outbox.posted_today_by_account, so the
    lane must not add it a second time. cap=2 with ONE posted item leaves exactly
    one slot; charging it twice would leave none."""
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    _seed_lane_item(tmp_path, status="posted")

    rep = _gen(tmp_path, _cfg(**_ONLY_FLAGSHIP), cap=2)
    assert rep["generated"], rep["dropped"]


# ─────────────────────────────────────────────────────────────────────────────
# 14. Freshness anchor + the session a claim may make
#
# load_movers took `asof` from sp500_heatmap.json only, and that stamp runs one
# session behind themes_heatmap.json on every commit measured. _tape_stale then
# aged the whole heatmap-only branch by it — and by a DATE, which at 14:05Z is
# 845 minutes old and can never pass a 45-minute gate. Result on 2026-07-31:
# every in-window sweep logged pt_generated=0 / pt_dropped=1 "tape stale".
# ─────────────────────────────────────────────────────────────────────────────

def _write_sp500_meta(tmp: Path, tiles, *, asof, generated_utc=None):
    p = tmp / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    payload = {"asof": asof, "tiles": tiles, "source": "daily-close"}
    if generated_utc:
        payload["generated_utc"] = generated_utc
    (p / "sp500_heatmap.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_themes_meta(tmp: Path, tiles, *, asof, generated_utc=None):
    p = tmp / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    payload = {"asof": asof, "tiles": tiles, "source": "finviz-themes"}
    if generated_utc:
        payload["generated_utc"] = generated_utc
    (p / "themes_heatmap.json").write_text(json.dumps(payload), encoding="utf-8")


# The heatmap builders write generated_utc as "YYYY-MM-DD HH:MM" (space, no zone).
_GEN_UTC = NOW.strftime("%Y-%m-%d %H:%M")
_YESTERDAY = "2026-07-22"


def test_a_fresh_generated_utc_clears_the_gate_a_date_asof_never_could(tmp_path):
    """PINS the freshness anchor. Heatmap-only sweep, no live snapshot: the gate
    must age the payload by its REFRESH stamp. Pre-fix it aged by the sp500
    `asof` date, which is 845 minutes old at 14:05Z, so 'tape stale' fired on
    every sweep and this assertion fails."""
    _write_sp500_meta(tmp_path, [_tile("ISRG", -14.0, sector="Health Care")],
                      asof=_YESTERDAY, generated_utc=_GEN_UTC)
    rep = _gen(tmp_path, _cfg(), live=False)
    assert not any(d["reason"] == "tape stale" for d in rep["dropped"]), rep["dropped"]


def test_stale_session_rows_may_not_ship_a_today_claim(tmp_path):
    """PINS the mixed-asof law. The payload is FRESH (generated minutes ago) but
    its rows are dated to the PRIOR session, and every mover/theme template says
    "today" in its own words. The honest outcome is to skip, not to publish."""
    _write_sp500_meta(tmp_path, [_tile("ISRG", -14.0, sector="Health Care")],
                      asof=_YESTERDAY, generated_utc=_GEN_UTC)
    rep = _gen(tmp_path, _cfg(), live=False)

    assert rep["generated"] == [] and rep["would_generate"] == []
    stale = [d for d in rep["dropped"] if d["reason"] == "stale_session"]
    assert stale, rep["dropped"]
    assert _YESTERDAY in stale[0]["detail"]
    assert outbox.read_items(tmp_path) == []


def test_the_fresher_themes_read_re_dates_a_mover_and_revives_it(tmp_path):
    """PINS the (c) arm: where themes_heatmap carries the SAME row a session
    fresher, prefer it — that is what keeps the mover family alive on a
    heatmap-only sweep instead of refusing all of it as stale-session."""
    _write_sp500_meta(tmp_path, [_tile("ISRG", -9.0, sector="Health Care")],
                      asof=_YESTERDAY, generated_utc=_GEN_UTC)
    _write_themes_meta(tmp_path, [_theme_tile("Health", {
        "ISRG": -14.0, "A": -0.1, "B": -0.1, "C": -0.1})],
        asof=TODAY, generated_utc=_GEN_UTC)

    rep = _gen(tmp_path, _cfg(max_per_run=4), live=False)
    movers = [g for g in rep["would_generate"] if g["kind"] == "mover"]
    assert movers, (rep["would_generate"], rep["dropped"])
    assert movers[0]["ticker"] == "ISRG"
    # ...and it quotes the FRESHER number, not the index board's stale one.
    assert "-14.0%" in movers[0]["text"], movers[0]["text"]
    assert not any(d["reason"] == "stale_session" and "ISRG" in d["detail"]
                   for d in rep["dropped"]), rep["dropped"]


def test_a_theme_whose_members_span_two_sessions_is_refused(tmp_path):
    """A theme aggregate that averages two sessions is undatable, so theme_lists
    reports asof=None and this lane refuses it rather than guessing."""
    from engine.marketing import movers_source
    tiles = [{"t": "AI", "name": "AI", "sector": "AI", "perf": {"1D": -2.0},
              "members": [
                  {"t": "NVDA", "perf": {"1D": -3.0}, "asof": TODAY},
                  {"t": "AMD", "perf": {"1D": -4.0}, "asof": TODAY},
                  {"t": "MU", "perf": {"1D": -2.0}, "asof": _YESTERDAY},
                  {"t": "AVGO", "perf": {"1D": -1.5}, "asof": _YESTERDAY},
              ]}]
    out = movers_source.theme_lists({"theme_tiles": tiles}, min_members=4)
    assert out and out[0]["asof"] is None, out


# ─────────────────────────────────────────────────────────────────────────────
# 15. The tail. A post ends on a stance that COSTS the author, never on bait.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_four_historical_bait_tails_are_all_caught(tmp_path):
    """The exact strings from the four live publisher_live_movers posts, plus a
    stance tail that must NOT be caught. A blocklist of these four would be a
    regression pin; _tail_is_bait is a positive test (is the final question about
    the AUTHOR?), so the fifth bait line nobody has written yet is caught too."""
    for bait in ("Dead-cat bounce or the real dip?",
                 "Which one breaks out first?",
                 "$LII -19.6%\n\nLII crashed today. Watching, not chasing. What's your read?",
                 "Who leads this group higher?",
                 "So which is it, a top or a pause?"):
        assert pt._tail_is_bait(bait), bait
    for ok in ("Tape check. Not touching it yet.",
               "I want one quiet close before I touch this group. Am I too slow here?",
               "Passing on the whole group here. Does that cost me the snapback?"):
        assert not pt._tail_is_bait(ok), ok


def test_a_bait_tail_is_re_rolled_onto_another_variant(tmp_path, monkeypatch):
    """PINS the re-roll. One variant in copywriter's mover bank ends "...What's
    your read?" and this lane cannot edit that bank, so it rotates the variant
    hash instead of spending the post. The stub is bait ONLY on the first roll."""
    from engine.marketing import copywriter

    def _rolled(contexts):
        out = []
        for ctx in contexts:
            baity = "-r" not in str(ctx.get("slot") or "")
            out.append({
                "headline": "$ISRG -14.0%",
                "body": ("ISRG fell today. What's your read?" if baity
                         else "ISRG fell today. I'm not touching it. Am I too slow?"),
                "violations": [], "mode": "deterministic"})
        return out

    monkeypatch.setattr(copywriter, "write_posts_deterministic", _rolled)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")
    assert "What's your read?" not in mv["text"]
    assert mv["text"].rstrip().endswith("Am I too slow?")
    # The ITEM's slot label is untouched by the re-roll — only the copy hash moved.
    assert mv["slot"] == "LIVE-AM"


def test_copy_that_is_bait_on_every_variant_is_dropped(tmp_path, monkeypatch):
    """A bank that is bait all the way down is a copywriter defect to report, not
    a post to make."""
    from engine.marketing import copywriter
    monkeypatch.setattr(copywriter, "write_posts_deterministic", lambda ctxs: [
        {"headline": "$ISRG -14.0%", "body": "ISRG fell today. What's your read?",
         "violations": [], "mode": "deterministic"} for _ in ctxs])
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    assert outbox.read_items(tmp_path) == []
    assert any(d["reason"] == "bait_tail" for d in rep["dropped"]), rep["dropped"]


def test_generated_theme_copy_never_ends_on_reader_bait(tmp_path, monkeypatch,
                                                        real_card):
    """End to end, through the real v3 banks: the shipped theme post ends on a
    tail whose final question is about the author. Pre-fix the bank's tail was
    "Which one breaks out first?" and this fails."""
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _theme_fixture(tmp_path)
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    assert tl["text"].rstrip().endswith("?")        # copywriter's theme_list law
    assert not pt._tail_is_bait(tl["text"]), tl["text"]


# ─────────────────────────────────────────────────────────────────────────────
# 16. The workflow has to be able to MAKE a picture
# ─────────────────────────────────────────────────────────────────────────────

def test_marketing_publish_workflow_can_render_and_host_a_card():
    """PINS defect 2. The publish job runs on ubuntu-latest with a pip line that
    had neither a rasteriser fallback nor an S3 client, and no R2 credentials in
    the publisher step's env — so every card this lane renders would fail to host
    and every candidate would be dropped."""
    import yaml
    root = Path(__file__).resolve().parents[1]
    wf = yaml.safe_load(
        (root / ".github" / "workflows" / "marketing-publish.yml").read_text(
            encoding="utf-8"))
    job = wf["jobs"]["publish"]
    assert job["runs-on"] == "ubuntu-latest"

    install = next(st for st in job["steps"] if st.get("name") == "install deps")
    for pkg in ("pillow", "boto3", "pyarrow", "pyyaml"):
        assert pkg in install["run"], install["run"]

    publisher = next(st for st in job["steps"]
                     if str(st.get("name", "")).startswith("run publisher"))
    for key in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET"):
        assert key in publisher["env"], sorted(publisher["env"])
        assert "secrets." + key in publisher["env"][key]


# ─────────────────────────────────────────────────────────────────────────────
# 17. DRY-RUN WRITES NOTHING — including no card
#
# The module contract has always said live=False "writes NOTHING". _resolve_card
# ran unguarded anyway, and it is not a read: it rasterises through Chrome and
# hands the SVG to media_publish.publish_card, which writes an SVG and a PNG
# under data/ and PUTs the PNG to R2. Every scheduled dry sweep therefore paid a
# raster + an upload per candidate and left data/ dirty — against the house law
# that intraday lanes discard data/ writes.
# ─────────────────────────────────────────────────────────────────────────────

def _tree(root: Path) -> set[str]:
    """Every file under *root*, as posix-relative strings."""
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_dry_run_never_resolves_a_card(tmp_path, monkeypatch):
    """PINS the fix. The spy FAILS the test if the resolver is entered at all —
    a call count assertion, not a side-effect assertion, so it cannot be
    satisfied by a resolver that happens to no-op under tmp_path."""
    calls: list[str] = []

    def _spy(cand, **kw):
        calls.append(str(cand.get("type")))
        return _fake_card(cand, **kw)

    monkeypatch.setattr(pt, "_resolve_card", _spy)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg(), live=False)
    assert rep["would_generate"], rep["dropped"]
    assert calls == [], f"_resolve_card ran {len(calls)} time(s) in a DRY run"
    assert rep["cards_deferred_dry_run"] == len(rep["would_generate"])


def test_dry_run_leaves_the_root_byte_identical(tmp_path, monkeypatch):
    """The whole-tree assertion — a card SVG, a card PNG, an outbox row, a ledger
    line all show up here as a new path.

    The stub WRITES, on purpose. media_publish.publish_card writes the SVG and
    the PNG under data/marketing/outbox/media/<as_of>/ before it uploads, so a
    resolver that is merely *entered* dirties the tree. Under tmp_path the real
    resolver bails on "no-bars" and writes nothing, which would make a
    tree-equality assertion pass on the broken code — the exact vacuous-green
    shape this repo keeps finding. Standing in for the write is what makes the
    assertion below able to SEE the failure.
    """
    def _writing_card(cand, *, root, cfg, as_of, now, slot):
        d = Path(root) / "data" / "marketing" / "outbox" / "media" / as_of
        d.mkdir(parents=True, exist_ok=True)
        (d / "dry-leak.svg").write_text("<svg/>", encoding="utf-8")
        (d / "dry-leak.png").write_bytes(b"\x89PNG")
        return _fake_card(cand, root=root, cfg=cfg, as_of=as_of, now=now, slot=slot)

    monkeypatch.setattr(pt, "_resolve_card", _writing_card)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})
    before = _tree(tmp_path)

    rep = _gen(tmp_path, _cfg(), live=False)
    assert rep["would_generate"], rep["dropped"]
    assert _tree(tmp_path) == before, sorted(_tree(tmp_path) - before)
    assert outbox.read_items(tmp_path) == []


def test_the_dry_run_preview_says_the_card_is_pending(tmp_path, monkeypatch):
    """A preview that showed no card and said nothing about it would read as
    'this lane ships bare rollup posts'. It does not — it defers."""
    monkeypatch.setattr(pt, "_resolve_card", _fake_card)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg(), live=False)
    assert rep["would_generate"], rep["dropped"]
    assert all(w["card"] == "deferred_dry_run" for w in rep["would_generate"]), \
        rep["would_generate"]


def test_a_live_run_still_resolves_every_card(tmp_path, monkeypatch):
    """The mutation check on the guard above: skip the card in LIVE mode and
    this fails. Without it, `if not live` could be inverted and nothing would
    notice until a bare rollup post was quarantined in production."""
    calls: list[str] = []

    def _spy(cand, **kw):
        calls.append(str(cand.get("type")))
        return _fake_card(cand, **kw)

    monkeypatch.setattr(pt, "_resolve_card", _spy)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg(), live=True)
    assert rep["generated"], rep["dropped"]
    assert calls, "the live run skipped card resolution"
    assert rep["cards_deferred_dry_run"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 18. A TOO-LONG RENDER IS A VARIANT PROBLEM, SO IT IS RE-ROLLED
#
# validate_copy caps headline+body at 275 chars and the variant banks are not
# all the same length. On the same candidate the 'dry, receipts-forward' theme
# template rendered 282 chars and _render_copy_unbaited short-circuited on it at
# attempt 0 — spending a real post to punish a template, which is the exact
# failure the re-roll was written to stop for bait.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_too_long_render_is_re_rolled_onto_a_shorter_variant(tmp_path, monkeypatch):
    """282 chars on roll 0, a compliant render on roll 1. Fails pre-fix: the old
    loop returned the violation from attempt 0 and the candidate was dropped."""
    from engine.marketing import copywriter

    long_body = ("ISRG fell today. " + "The tape kept selling into the close. " * 6
                 + "I'm not touching it. Am I too slow?")
    assert len(long_body) > 275, len(long_body)

    def _rolled(contexts):
        out = []
        for ctx in contexts:
            first = "-r" not in str(ctx.get("slot") or "")
            body = long_body if first else "ISRG fell today. I'm out. Am I too slow?"
            out.append({
                "headline": "$ISRG -14.0%", "body": body, "mode": "deterministic",
                "violations": ([f"too long: {len(body) + 13} chars (max 275)"]
                               if first else []),
            })
        return out

    monkeypatch.setattr(copywriter, "write_posts_deterministic", _rolled)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")
    assert mv["text"].rstrip().endswith("I'm out. Am I too slow?"), mv["text"]


def test_a_non_length_violation_is_still_terminal_on_the_first_attempt(tmp_path,
                                                                       monkeypatch):
    """The other half of the rule. A banned phrase is a property of the
    candidate's facts, not of the variant — grinding the bank would only burn
    renders and hide the real reason from `copy_violation`."""
    from engine.marketing import copywriter
    seen: list[str] = []

    def _always_banned(contexts):
        for ctx in contexts:
            seen.append(str(ctx.get("slot")))
        return [{"headline": "$ISRG -14.0%", "body": "ISRG fell. I'm out.",
                 "violations": ["banned vocab: 'validated'"],
                 "mode": "deterministic"} for _ in contexts]

    monkeypatch.setattr(copywriter, "write_posts_deterministic", _always_banned)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    assert any(d["reason"] == "copy_violation" for d in rep["dropped"]), rep["dropped"]
    assert len(seen) == 1, f"a non-length violation was re-rolled {len(seen)}x"


def test_too_long_in_every_variant_reports_copy_violation_not_bait(tmp_path,
                                                                   monkeypatch):
    """Exhausting the rolls on LENGTH must not be reported as reader-bait — the
    two have different fixes (shorten the bank vs rewrite the tails), and a
    mislabelled counter sends the next reader to the wrong file."""
    from engine.marketing import copywriter
    long_body = ("ISRG fell today. " + "The tape kept selling into the close. " * 6
                 + "I'm not touching it. Am I too slow?")
    monkeypatch.setattr(copywriter, "write_posts_deterministic", lambda ctxs: [
        {"headline": "$ISRG -14.0%", "body": long_body, "mode": "deterministic",
         "violations": [f"too long: {len(long_body) + 13} chars (max 275)"]}
        for _ in ctxs])
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"] == []
    reasons = {d["reason"] for d in rep["dropped"]}
    assert "copy_violation" in reasons, rep["dropped"]
    assert "bait_tail" not in reasons, rep["dropped"]


def test_only_length_violations_predicate():
    """Directly on the gate, so the pin survives a loop refactor."""
    assert pt._only_length_violations(["too long: 282 chars (max 275)"])
    assert pt._only_length_violations(["shape list: 300 chars (max 275)",
                                       "shape two_part: body 290 chars (max 275)"])
    assert not pt._only_length_violations([])
    assert not pt._only_length_violations(["banned vocab: 'validated'"])
    # MIXED is not length-only: the banned phrase survives every re-roll.
    assert not pt._only_length_violations(["too long: 282 chars (max 275)",
                                           "banned vocab: 'validated'"])


# ─────────────────────────────────────────────────────────────────────────────
# 19. A SENTENCE-INITIAL PRONOUN IS STILL FIRST PERSON
#
# _FIRST_PERSON_RE was one case-sensitive alternation, so its lower-case arm
# only ever matched lower-case pronouns — and a pronoun is capitalised exactly
# when it opens the sentence, which is the commonest place for it.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_capitalised_pronoun_opening_the_tail_is_not_bait():
    """The two repro strings from the review, plus the bare-I control."""
    for ok in ("My read is nothing here?",
               "ISRG fell today. Our patience is the cost?",
               "Mine to miss if it runs?",
               "Am I too slow here?"):
        assert not pt._tail_is_bait(ok), ok


def test_lower_case_i_is_still_not_a_pronoun():
    """The bare-I arm stays case-sensitive on purpose: `\\bi\\b` under IGNORECASE
    matches the stray single letter in any enumeration, which would silently
    disarm the bait gate."""
    assert pt._tail_is_bait("Option i or option ii?")
    assert not pt._has_first_person("Option i or option ii")
    assert pt._has_first_person("Option I take")


# ─────────────────────────────────────────────────────────────────────────────
# 20. THE WORKFLOW COMMENT MUST DESCRIBE A WIRE THAT EXISTS
#
# marketing-publish.yml justified `pip install pillow` with "media_publish.
# publish_card falls back to the legacy PIL raster when no Chrome is available".
# This lane never passes `legacy_png`, so that fallback is unreachable from here
# and a Chrome-less runner drops every candidate for `no-media-url` whatever PIL
# is installed. Pinning the FACT, not the prose: a comment cannot be tested, but
# the call shape it describes can.
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_card_never_arms_the_legacy_png_fallback(tmp_path, monkeypatch):
    """If this ever starts passing `legacy_png`, the workflow comment about why
    pillow is installed has to be rewritten again — so fail here first."""
    from engine.marketing import media_publish
    seen: dict = {}

    def _spy_publish_card(svg, *, chart_id, as_of, root=None, legacy_png=None):
        seen["legacy_png"] = legacy_png
        return {"media_url": f"https://cards.example/{chart_id}.png",
                "media_png_path": f"data/x/{chart_id}.png"}

    monkeypatch.setattr(media_publish, "publish_card", _spy_publish_card)
    monkeypatch.setattr(pt, "_resolve_card", _REAL_RESOLVE_CARD)
    from engine.marketing import chart_render
    monkeypatch.setattr(chart_render, "resolve_color_logo", lambda t, r: None)
    _theme_fixture(tmp_path)

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    assert "legacy_png" in seen, "publish_card was never reached — fixture is wrong"
    assert seen["legacy_png"] is None, (
        "the publish-time lane now arms the legacy PIL raster; the pillow "
        "justification comment in .github/workflows/marketing-publish.yml is "
        "stale again"
    )
