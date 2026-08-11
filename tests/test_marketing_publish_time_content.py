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

from engine.marketing import movers_source, outbox, publish_time_content as pt


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
                # Defect 1 (cashtag spam fingerprint): every lane key in this
                # block is REQUIRED — the module hard-indexes them so a config
                # that forgot one fails loudly instead of silently posting on a
                # default. Mirrors the shipped config/marketing.yml value.
                "max_theme_cashtags_in_text": 3,
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


def test_theme_copy_names_at_most_the_cap_and_ends_on_the_breadth_fact(tmp_path):
    """A generated theme item names AT MOST the cap, and its body ends on a
    STATEMENT, never a question.

    REWRITTEN FOR DEFECT 1 (operator, live 2026-08-03). This test used to assert
    ``len(cashtags) >= 4`` — it encoded copywriter's floor as this lane's law, so
    the eight-cashtag spam fingerprint the operator caught was a PASSING state
    here. The floor belongs to a bank that predates the card; the account-safety
    ceiling is what this lane owes X. The assertion is inverted accordingly.

    INVERTED AGAIN FOR VOICE DOCTRINE v5 (2026-08-11): the second half asserted
    ``endswith("?")``, mirroring copywriter.validate_copy's theme_list "?"
    REQUIREMENT. That requirement is now a "?" BAN, and the group post ends on
    the breadth fact from movers_source's tail banks.
    """
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
    assert 0 < len(cashtags) <= pt._DEFAULTS["max_theme_cashtags_in_text"], tl["text"]
    assert not tl["text"].rstrip().endswith("?"), tl["text"]
    assert tl["text"].rstrip().endswith(
        tuple(movers_source._TAIL_UP) + tuple(movers_source._TAIL_DOWN)), tl["text"]


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
    # The tail comes from the LIVE pools rather than a hard-coded literal: the
    # v4 fixture pinned "Which one breaks out first?" and went stale the day the
    # bank was rewritten for Voice Doctrine v5 (2026-08-11), which is exactly the
    # failure a fixture copied out of a bank always has.
    tail = movers_source._TAIL_UP[0] if direction == "up" else movers_source._TAIL_DOWN[0]
    tl = {"theme": "Artificial Intelligence", "direction": direction,
          "tone": "ripping" if direction == "up" else "selling off",
          "members": members, "agg_pct": round(sign * 3.1, 2),
          "question": tail}
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
    # UPDATED 2026-08-03 (defect 4, the uncomputed-stance ruling). This used to
    # assert the pool was "exactly the one untagged variant", identified by the
    # string "biggest move in the index" — which was the headline of the post
    # whose body said "either way I'd let it settle first". The mover bank is now
    # partitioned by whether a COMPUTED technical state exists for the name, and
    # this ctx carries none, so the pool is the bank's no-stance half. The
    # invariant the test exists for is unchanged and restated below: filtering
    # never empties the pool, and it never leaves a line whose {mover_state}
    # token has nothing to render.
    assert pool, "chart/direction/state filters emptied the pool"
    assert all("{mover_state}" not in v[0] and "{mover_state}" not in v[1]
               for v in pool), (
        "a stateless context may not select a state-citing variant")
    assert all("chart" not in v[1].lower() for v in pool), (
        "has_chart=False must still exclude the chart-claiming lines")


def test_nightly_path_selection_unchanged_by_tags():
    """A ctx WITHOUT direction/has_chart/state/trend info (the nightly D-slot
    shape) filters on the two FAIL-CLOSED axes only, and on nothing else.

    Both axes landed for the 2026-08-03 FSLR postmortem, from two lanes, and
    both are deliberate. A `needs_state` line renders a {mover_state} token a
    stateless ctx has nothing to fill; a trend-bucket line claims a tape shape
    no trend read has established. Direction/chart tags still filter nothing,
    which is what the theme half pins, and which is what keeps the hash-based
    variant assignments for every existing post from moving.
    """
    from engine.marketing.copywriter import (
        _MOVER_CONTEXT_TAG_SET, _TEMPLATES, _variant_allowed,
    )
    # No mover_pct / theme_direction / has_chart. "ticker" IS set, because every
    # real ctx has it (build_context always writes the key) and it now also
    # drives the ticker-dependency partition; a mover bank is entirely
    # cashtag-bearing, so a ticker-less ctx would legitimately select none.
    theme_bank = _TEMPLATES[("theme_list", "fast, reactive")]
    theme_ctx = {"type": "theme_list", "ticker": "AAPL"}
    assert [v for v in theme_bank
            if _variant_allowed(v, theme_ctx)] == list(theme_bank)

    def _tags(v):
        return set(v[2] or ()) if len(v) > 2 else set()

    mover_bank = _TEMPLATES[("mover", "authoritative desk")]
    mover_ctx = {"type": "mover", "ticker": "AAPL"}
    stateless = [v for v in mover_bank if _variant_allowed(v, mover_ctx)]
    assert stateless and len(stateless) < len(mover_bank)
    assert not any(_MOVER_CONTEXT_TAG_SET & _tags(v) for v in stateless), (
        "a trend-less ctx may not select a bucket line")
    assert not any("needs_state" in _tags(v) for v in stateless), (
        "a stateless ctx may not select a state-citing variant")

    # ...and the state half is exactly the complement WITHIN the no-bucket bank,
    # so the two shapes partition it rather than overlapping or leaking.
    no_bucket = [v for v in mover_bank
                 if not (_MOVER_CONTEXT_TAG_SET & _tags(v))]
    stateful = [v for v in no_bucket
                if _variant_allowed(
                    v, dict(mover_ctx,
                            mover_state="X is above its 50-day average"))]
    assert stateful and not set(map(id, stateful)) & set(map(id, stateless))
    assert len(stateful) + len(stateless) == len(no_bucket)


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
    # THE CONTAINMENT DIRECTION FLIPPED (defect 1, 2026-08-03). This used to
    # assert card ⊆ text — "a card listing a name the post never mentions is its
    # own small lie" — and that reasoning is what pinned the copy at eight
    # cashtags and gave the account the spam fingerprint. The card is the
    # ENUMERATION and the text is the HEADLINE, so the honest containment is
    # TEXT ⊆ CARD: naming 3 of 8 is a summary; naming a name the picture omits
    # is the actual lie, and that is what this now forbids.
    import re as _re
    named = set(t.lstrip("$") for t in _re.findall(r"\$[A-Z]{1,5}", tl["text"]))
    assert named <= set(entry["tickers"]), (named, entry["tickers"])
    assert len(named) <= pt._DEFAULTS["max_theme_cashtags_in_text"], tl["text"]


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
    statement tail that must NOT be caught.

    WIDENED FOR VOICE DOCTRINE v5 (2026-08-11). The v4 rule was a positive test
    about WHO the final question was about: a first-person question was spared,
    because the house register was a persona reacting to a trade. The bottom
    three strings below used to live in the "not bait" list for exactly that
    reason. v5 bans first person AND question marks in generated post copy, so
    the exemption those three relied on is now itself a violation and they move
    up into the caught set. The rule is one line now: any interrogative tail is
    bait, whoever it is about — which also means the fifth bait line nobody has
    written yet is still caught.
    """
    for bait in ("Dead-cat bounce or the real dip?",
                 "Which one breaks out first?",
                 "$LII -19.6%\n\nLII crashed today. Watching, not chasing. What's your read?",
                 "Who leads this group higher?",
                 "So which is it, a top or a pause?",
                 # ── retired v4 carve-out: first person no longer buys a pass ──
                 "I want one quiet close before I touch this group. Am I too slow here?",
                 "Passing on the whole group here. Does that cost me the snapback?",
                 "Am I getting a second session out of this?"):
        assert pt._tail_is_bait(bait), bait
    for ok in ("Tape check. Not touching it yet.",
               "Breadth inside the group, not one leader.",
               "$NVDA closed above 209 for the first time in three weeks."):
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
                # The escape body is a v5 STATEMENT (2026-08-11). It used to be
                # "I'm not touching it. Am I too slow?", which the widened rule
                # now classifies as bait too, so the loop would exhaust and this
                # test would prove the opposite of what it says.
                "body": ("ISRG fell today. What's your read?" if baity
                         else "ISRG fell today. The 50-day is now overhead."),
                "violations": [], "mode": "deterministic"})
        return out

    monkeypatch.setattr(copywriter, "write_posts_deterministic", _rolled)
    _write_sp500(tmp_path, [_tile("ISRG", 0.1, sector="Health Care")])
    _write_snapshot(tmp_path, {"ISRG": (300.0, 349.0, -14.0)})

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    mv = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "mover")
    assert "What's your read?" not in mv["text"]
    assert mv["text"].rstrip().endswith("The 50-day is now overhead.")
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
    STATEMENT. Pre-fix the bank's tail was "Which one breaks out first?".

    Voice Doctrine v5 (2026-08-11) replaced the middle assertion. It read
    ``endswith("?")`` with the comment "copywriter's theme_list law", because
    validate_copy required a theme_list body to end on a question — the single
    upstream line that made every group post reply-bait no matter what the tail
    bank said. The requirement is now a ban, so the post must end on the tail
    bank's breadth fact instead.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _theme_fixture(tmp_path)
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    assert not tl["text"].rstrip().endswith("?"), tl["text"]
    assert tl["text"].rstrip().endswith(
        tuple(movers_source._TAIL_UP) + tuple(movers_source._TAIL_DOWN)), tl["text"]
    assert not pt._tail_is_bait(tl["text"]), tl["text"]


# ─────────────────────────────────────────────────────────────────────────────
# 16. The workflow has to be able to MAKE a picture
# ─────────────────────────────────────────────────────────────────────────────

def test_marketing_publish_workflow_can_render_and_host_a_card():
    """PINS defect 2 across the current deadline-bound publishing runner.

    The lane still needs the rasteriser, S3 client, and R2 credentials after its
    intentional move from hosted Ubuntu to the self-hosted light Mac pool; if
    those disappear, every rendered card would still fail to host and drop.
    """
    import yaml
    root = Path(__file__).resolve().parents[1]
    wf = yaml.safe_load(
        (root / ".github" / "workflows" / "marketing-publish.yml").read_text(
            encoding="utf-8"))
    job = wf["jobs"]["publish"]
    assert job["runs-on"] == ["self-hosted", "macstudio-light"]

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
                 + "The 50-day average is now overhead.")
    assert len(long_body) > 275, len(long_body)

    def _rolled(contexts):
        out = []
        for ctx in contexts:
            first = "-r" not in str(ctx.get("slot") or "")
            # v5 statement tails on both rolls (2026-08-11): the shorter body was
            # "I'm out. Am I too slow?", which the widened bait rule now rejects,
            # so the re-roll would exhaust and this test would stop proving that
            # a LENGTH violation is what got escaped.
            body = long_body if first else "ISRG fell today. The 50-day is now overhead."
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
    assert mv["text"].rstrip().endswith("The 50-day is now overhead."), mv["text"]


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
#
# WHERE THAT DEFECT NOW BITES (Voice Doctrine v5, 2026-08-11). Under v4 the
# case-blindness cost a re-roll: `_tail_is_bait` used a first-person marker to
# EXEMPT a trailing question, so a missed pronoun dropped compliant copy. v5
# retires the exemption — every interrogative tail is bait — and the same
# patterns now carry the OPPOSITE duty on `llm_phrase_violations`, where a
# missed pronoun waves the banned first-person register straight through. Same
# regex, same defect, inverted cost. Both directions are pinned below.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_capitalised_pronoun_opening_the_tail_is_still_bait():
    """INVERTED FOR v5. These four used to be the "not bait" list — a
    first-person question was the shape the rule deliberately spared. It is now
    doubly banned (first person AND "?"), so sparing it would make this gate the
    one hole the doctrine leaks through."""
    for bait in ("My read is nothing here?",
                 "ISRG fell today. Our patience is the cost?",
                 "Mine to miss if it runs?",
                 "Am I too slow here?"):
        assert pt._tail_is_bait(bait), bait


def test_a_capitalised_pronoun_is_still_seen_by_the_first_person_screen():
    """THE ORIGINAL DEFECT, on the caller that still consults these patterns.

    `_has_first_person` feeds `llm_phrase_violations`' "first_person_banned"
    law. A capitalised pronoun opening the phrase is the commonest place for
    one, and the pre-fix single case-sensitive alternation could not see it.
    """
    for phrase in ("My read is nothing here",
                   "Our patience is the cost",
                   "Mine to miss if it runs",
                   "Am I too slow here"):
        assert pt._has_first_person(phrase), phrase


def test_lower_case_i_is_still_not_a_pronoun():
    """The bare-I arm stays case-sensitive on purpose: `\\bi\\b` under IGNORECASE
    matches the stray single letter in any enumeration, which would make
    `llm_phrase_violations` reject an enumerated wire phrase as first person."""
    assert pt._tail_is_bait("Option i or option ii?")   # the "?" is what caught it
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


# ═════════════════════════════════════════════════════════════════════════════
# 21. DEFECT 1 — THE CASHTAG SPAM FINGERPRINT
#
# Two posts went LIVE on the flagship on 2026-08-03 ~17:30Z from this lane, which
# auto-approves and posts with no human in the loop. The theme_list one read:
#
#     Virtual & Augmented Reality is up across the board today
#     $COHR $LITE $AXON $META $RBLX $MSFT $GOOGL $U
#     Virtual & Augmented Reality is +3.7% on average on Friday (8 names higher).
#     Does not chasing keep costing me money?
#
# Eight cashtags in one post is the spam signature X flags — an ACCOUNT-SAFETY
# risk, not a style note. Operator: "you know tagging this many cashtags will get
# flagged as spam right? like u can do 2-3 but not like all of them."
#
# TWO code decisions produced it, and both are pinned below:
#   * the cashtag-breadth gate said "(movers only; theme_list exempt, per
#     sentinel)" — the rule pointed away from the one format that enumerates a
#     group by construction;
#   * `_CARD_MAX_ROWS = 8` was justified by "the copy names at most 8 cashtags,
#     so 8 keeps the picture and the text describing the SAME names". That
#     reasoning is backwards: the CARD is the enumeration, the TEXT is the
#     headline. A picture of 8 names captioned with 3 is a summary.
# ═════════════════════════════════════════════════════════════════════════════

#: Eight names, all up, with DISTINCT magnitudes so "the biggest movers" is a
#: decidable question rather than a tie broken by insertion order.
_EIGHT = {"COHR": 9.1, "LITE": 7.4, "AXON": 6.2, "META": 5.0,
          "RBLX": 4.1, "MSFT": 3.3, "GOOGL": 2.2, "U": 1.4}


def _eight_name_theme(tmp: Path) -> None:
    """The live post's shape: one theme, eight members higher, a live snapshot."""
    _write_themes(tmp, [_theme_tile("Virtual & Augmented Reality",
                                    {t: 0.0 for t in _EIGHT})])
    _write_snapshot(tmp, {t: (100.0, 100.0 - p, p) for t, p in _EIGHT.items()})


def _named_cashtags(text: str) -> set[str]:
    import re as _re
    return {t.lstrip("$") for t in _re.findall(r"\$[A-Z]{1,5}", text)}


def test_the_text_names_at_most_the_cap_while_the_card_still_lists_all_eight(
        tmp_path, monkeypatch, real_card):
    """PINS BOTH HALVES OF DEFECT 1 IN ONE ASSERTION PAIR.

    The `<= 3` line is the mutation check for the cap: restore the theme_list
    exemption (or `members[:10]` in _build_candidates) and it fails with the
    live post's eight. The `== 8` line is the mutation check for the OTHER
    direction — "just truncate the members" would silence the first assertion
    while quietly deleting five names from the picture, and this catches that.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _eight_name_theme(tmp_path)

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")

    named = _named_cashtags(tl["text"])
    assert len(named) <= pt._DEFAULTS["max_theme_cashtags_in_text"], tl["text"]
    assert len(tl["media"][0]["tickers"]) == 8, tl["media"][0]["tickers"]
    # ...and every name the text says is a name the picture shows.
    assert named <= set(tl["media"][0]["tickers"]), (named, tl["media"][0])


def _write_tiers(tmp: Path, advs: dict[str, float]) -> None:
    """A cashtag_tiers.json carrying ADV20 — the lane's watchedness column."""
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "cashtag_tiers.json").write_text(json.dumps({
        "tickers": {t: {"tier": "T2", "proxies": {"adv20_musd": v}}
                    for t, v in advs.items()}}), encoding="utf-8")


#: ADV that is the REVERSE of _EIGHT's magnitude order: the biggest mover (COHR,
#: +9.1%) is the least-traded, the smallest mover (U, +1.4%) is the most-traded.
#: This is not a contrived fixture — it is the shape the operator identified
#: ("the biggest movers are almost always the smallest floats"), and it is the
#: only shape in which the two rules give visibly different answers.
_EIGHT_ADV = {t: float(50 * (i + 1))
              for i, t in enumerate(sorted(_EIGHT, key=lambda k: -_EIGHT[k]))}


def test_the_names_we_do_say_are_the_most_watched_not_the_biggest_movers(tmp_path):
    """OPERATOR RULING 2026-08-05. Ranking by |move| ranks by SMALLNESS.

        "the biggest movers are almost always the smallest floats, just due to
        small caps moving more, this is a big problem eh? we need to use the more
        watched ticker at all times, not the biggest mover."

    The lane spent its whole 3-cashtag budget on the three least-watched names in
    its own card — $GFI at $117M ADV led a post whose card also listed $HL at
    $599M, and whose sector ETF trades $1,321M.

    Mutation check: restore the |move| sort in _theme_text_cashtags and this fails
    with exactly the three biggest movers, which the second assertion names so the
    failure output shows the old rule's answer next to the new one.
    """
    _write_themes(tmp_path, [_theme_tile(
        "Virtual & Augmented Reality",
        # ascending by move — insertion order is the WRONG answer either way
        {t: 0.0 for t in sorted(_EIGHT, key=lambda k: _EIGHT[k])})])
    _write_snapshot(tmp_path, {t: (100.0, 100.0 - p, p) for t, p in _EIGHT.items()})
    _write_tiers(tmp_path, _EIGHT_ADV)

    rep = _gen(tmp_path, _cfg(), live=False)
    tls = [g for g in rep["would_generate"] if g["kind"] == "theme_list"]
    assert tls, (rep["would_generate"], rep["dropped"])

    named = _named_cashtags(tls[0]["text"])
    watched = set(sorted(_EIGHT_ADV, key=lambda k: -_EIGHT_ADV[k])[:len(named)])
    movers = set(sorted(_EIGHT, key=lambda k: -abs(_EIGHT[k]))[:len(named)])
    assert named == watched, (named, watched, tls[0]["text"])
    assert named != movers, "fixture is not discriminating between the two rules"


def test_the_named_set_cannot_widen_past_the_cards_rows(tmp_path):
    """Watchedness re-ORDERS inside the card; it must never widen past it.

    The named set stopped being a PREFIX of the rows when the ordering changed —
    that was deliberate — but "the text names nothing the picture omits" is the
    honesty property and it still holds.

    THIS IS A DIRECT UNIT TEST ON PURPOSE, and the end-to-end version of it was
    vacuous. `movers_source.theme_lists` defaults to n=8 and `_CARD_MAX_ROWS` is 8,
    so a 12-member theme is already truncated to 8 before the picker ever sees it:
    deleting the `[:_CARD_MAX_ROWS]` slice left the whole lane suite green. The
    slice guards against an upstream `n` that no longer agrees with the card, which
    is a condition the pipeline cannot currently produce — so it has to be fed
    here, by hand, or it is untested code pretending to be a guard.
    """
    over = [{"ticker": f"N{chr(65 + i)}X", "pct": float(20 - i)} for i in range(12)]
    tiers = {m["ticker"]: float(100 * (i + 1)) for i, m in enumerate(over)}
    # ADV rises with the index, so the MOST-watched names are exactly the ones
    # sitting past row 8 — the pick would reach for them if it could.
    named = pt._theme_text_cashtags(
        over, 3, {t: {"proxies": {"adv20_musd": v}} for t, v in tiers.items()})
    rows = {f"${m['ticker']}" for m in over[:pt._CARD_MAX_ROWS]}
    assert set(named) <= rows, (named, sorted(rows))


def test_without_adv_the_pick_falls_back_to_biggest_movers(tmp_path):
    """No tiers file → the OLD rule, not insertion order.

    An unranked pick is worse than the rule it replaced, not better, so the
    fallback is the previous behaviour exactly. This is also the test that keeps
    the fixture-with-no-ADV suites (most of this file) honest about what they are
    measuring: they exercise this path, not the watchedness path.
    """
    _write_themes(tmp_path, [_theme_tile(
        "Virtual & Augmented Reality",
        {t: 0.0 for t in sorted(_EIGHT, key=lambda k: _EIGHT[k])})])
    _write_snapshot(tmp_path, {t: (100.0, 100.0 - p, p) for t, p in _EIGHT.items()})
    # deliberately NO _write_tiers

    rep = _gen(tmp_path, _cfg(), live=False)
    tls = [g for g in rep["would_generate"] if g["kind"] == "theme_list"]
    assert tls, (rep["would_generate"], rep["dropped"])
    named = _named_cashtags(tls[0]["text"])
    assert named == set(sorted(_EIGHT, key=lambda k: -abs(_EIGHT[k]))[:len(named)])


def test_an_all_zero_adv_cohort_falls_back_too(tmp_path):
    """A tiers file that PRICES the cohort at zero is the same as no tiers.

    Sorting by a column that is zero everywhere degrades to insertion order, which
    is the one answer neither rule wants. Mutation check: delete the
    `any(a > 0 ...)` branch and this returns the payload's ascending order.
    """
    _write_themes(tmp_path, [_theme_tile(
        "Virtual & Augmented Reality",
        {t: 0.0 for t in sorted(_EIGHT, key=lambda k: _EIGHT[k])})])
    _write_snapshot(tmp_path, {t: (100.0, 100.0 - p, p) for t, p in _EIGHT.items()})
    _write_tiers(tmp_path, {t: 0.0 for t in _EIGHT})

    rep = _gen(tmp_path, _cfg(), live=False)
    tls = [g for g in rep["would_generate"] if g["kind"] == "theme_list"]
    assert tls, (rep["would_generate"], rep["dropped"])
    named = _named_cashtags(tls[0]["text"])
    assert named == set(sorted(_EIGHT, key=lambda k: -abs(_EIGHT[k]))[:len(named)])


def test_the_cap_is_config_driven(tmp_path):
    """An operator retune of publish.publish_time_movers.max_theme_cashtags_in_text
    changes the post, without a code change. Pinned at 2 (inside the operator's
    stated 2-3 band) so a hardcoded 3 fails here."""
    _eight_name_theme(tmp_path)
    cfg = _cfg()
    cfg["publish"]["publish_time_movers"]["max_theme_cashtags_in_text"] = 2

    rep = _gen(tmp_path, cfg, live=False)
    tls = [g for g in rep["would_generate"] if g["kind"] == "theme_list"]
    assert tls, (rep["would_generate"], rep["dropped"])
    assert len(_named_cashtags(tls[0]["text"])) <= 2, tls[0]["text"]


def test_the_breadth_gate_is_no_longer_exempt_for_theme_list(tmp_path):
    """PINS THE REMOVED EXEMPTION ITSELF.

    The cap is bypassed at the source (the candidate builder is forced to hand
    over all eight cashtags again), so the only thing that can still stop the
    live post is the breadth gate. Pre-fix that gate read `if cand["type"] ==
    "mover"` and this candidate sailed through it; post-fix it is refused by
    name. Without this test the exemption could be restored and every other
    test in this section would still pass, because they measure the builder.
    """
    monkeypatch_all = pt._theme_text_cashtags
    try:
        pt._theme_text_cashtags = lambda members, cap, tiers=None: [
            f"${m['ticker']}" for m in members]
        _eight_name_theme(tmp_path)
        rep = _gen(tmp_path, _cfg(), live=False)
    finally:
        pt._theme_text_cashtags = monkeypatch_all

    assert not [g for g in rep["would_generate"] if g["kind"] == "theme_list"], \
        rep["would_generate"]
    breadth = [d for d in rep["dropped"] if d["reason"] == "cashtag_breadth"]
    assert breadth, rep["dropped"]
    assert "8 >" in breadth[0]["detail"], breadth[0]


def test_the_card_and_the_text_still_agree_on_theme_count_and_average(
        tmp_path, monkeypatch, real_card):
    """Naming 3 of 8 is a summary; the two halves must still agree on the facts
    that are NOT the enumeration — the theme, the breadth count and the average.

    The subtitle is generated from the same theme item the copy's breadth fact
    is, so this pins that the cap did not quietly truncate `_theme_data`.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _eight_name_theme(tmp_path)

    seen: dict = {}
    _real = pt._theme_card_subtitle
    monkeypatch.setattr(pt, "_theme_card_subtitle",
                        lambda c: seen.setdefault("sub", _real(c)))

    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")

    assert seen["sub"].startswith("8 names higher"), seen["sub"]
    assert "8 names higher" in tl["text"], tl["text"]
    # the average appears in both, to the same precision
    avg = seen["sub"].split("average ")[1].rstrip("%")
    assert f"{avg}%" in tl["text"], (avg, tl["text"])


def test_a_theme_post_still_ships_rather_than_going_dark_under_the_cap(tmp_path):
    """copywriter.validate_copy requires ≥4 cashtags on a theme_list, and this
    lane's cap is 3 — so without _drop_lane_capped_cashtag_violation the whole
    family would generate, fail validation on every variant, and emit NOTHING.
    A silently dark format is not a fix for a spam fingerprint."""
    _eight_name_theme(tmp_path)
    rep = _gen(tmp_path, _cfg(), live=False)
    assert [g for g in rep["would_generate"] if g["kind"] == "theme_list"], \
        (rep["would_generate"], rep["dropped"])
    assert not [d for d in rep["dropped"] if d["reason"] == "copy_violation"], \
        rep["dropped"]


def test_the_cashtag_floor_exception_is_not_a_general_hole():
    """The excuse fires ONLY for the shortfall this lane created.

    Four separate mutation checks on _drop_lane_capped_cashtag_violation: a
    mover, a different violation, a count that does NOT match what the lane
    supplied, and a supplied count already above the cap. Each must keep its
    violation, or the "named collision" is really a bypass.
    """
    cand = {"type": "theme_list", "cashtags": ["$A", "$B", "$C"]}
    v = ["theme_list post must contain ≥4 cashtags; found 3"]
    assert pt._drop_lane_capped_cashtag_violation(v, cand, 3) == []

    # (a) not a theme_list
    assert pt._drop_lane_capped_cashtag_violation(
        v, {"type": "mover", "cashtags": ["$A", "$B", "$C"]}, 3) == v
    # (b) a different violation rides along and survives
    v2 = v + ["banned phrase: guaranteed"]
    assert pt._drop_lane_capped_cashtag_violation(v2, cand, 3) == \
        ["banned phrase: guaranteed"]
    # (c) copywriter found FEWER than the lane supplied — something else ate a
    #     cashtag, so this is a real defect and stays terminal
    assert pt._drop_lane_capped_cashtag_violation(
        ["theme_list post must contain ≥4 cashtags; found 2"], cand, 3) == \
        ["theme_list post must contain ≥4 cashtags; found 2"]
    # (d) the cap has been raised past copywriter's floor → the exception retires
    assert pt._drop_lane_capped_cashtag_violation(
        ["theme_list post must contain ≥4 cashtags; found 5"],
        {"type": "theme_list", "cashtags": ["$A"] * 5}, 4) == \
        ["theme_list post must contain ≥4 cashtags; found 5"]


# ═════════════════════════════════════════════════════════════════════════════
# 22. DEFECT 2 — ONE SESSION PER POST
#
# The same live post carried THREE claims about which session it was about:
#
#   first line : "Virtual & Augmented Reality is up across the board today"
#   body       : "... is +3.7% on average on Friday (8 names higher)."
#   card header: dated 2026-08-03
#
# posted Monday 2026-08-03. The rows really were Monday's — the row-session gate
# ("rows dated X, not today") passed, because it asks whether the DATA is
# current and never looks at what the WORDS say. The body's day word came from
# movers_source.session_phrase, which inferred the session from the CLOCK
# (`last_completed_session`, = Friday at 13:30 ET Monday) instead of from the
# row that supplied the number.
# ═════════════════════════════════════════════════════════════════════════════

#: Monday 2026-08-03, 17:30 UTC == 13:30 ET — the PM slot, mid-session. The
#: exact wall clock of the live posts.
MON = datetime(2026, 8, 3, 17, 30, 0, tzinfo=timezone.utc)
MON_DAY = "2026-08-03"
FRI_DAY = "2026-07-31"

#: The live post, reproduced. Load-bearing: the check must fire on THIS string.
LIVE_MIXED_POST = (
    "Virtual & Augmented Reality is up across the board today\n\n"
    "$COHR $LITE $AXON\n"
    "Virtual & Augmented Reality is +3.7% on average on Friday "
    "(8 names higher). Does not chasing keep costing me money?"
)


def test_the_reproduced_live_post_is_rejected_as_a_mixed_session_claim():
    """PINS THE LIVE DEFECT. "today" in the first line and "on Friday" in the
    body resolve to two different sessions, so the post is refused BY NAME.

    Mutation check: delete the `len(claims) > 1` branch of _session_conflict and
    this returns None — the exact state that let the post ship.
    """
    reason = pt._session_conflict(LIVE_MIXED_POST, now=MON,
                                  row_session=MON_DAY, card_session=MON_DAY)
    assert reason and reason.startswith("mixed_session_claim"), reason
    assert FRI_DAY in reason and MON_DAY in reason, reason


def test_the_same_post_with_one_session_passes():
    """The control. The ONLY edit is the body's day word; nothing else about the
    post changes. Without this the test above would also pass on a check that
    rejects every theme post."""
    assert pt._session_conflict(LIVE_MIXED_POST.replace("on Friday", "today"),
                                now=MON, row_session=MON_DAY,
                                card_session=MON_DAY) is None


def test_the_body_day_word_now_comes_from_the_row_not_the_clock():
    """THE ROOT CAUSE, at the source. At 13:30 ET Monday the clock's "last
    completed session" is Friday, so the clock-inferred word is "on Friday" —
    that is the string that shipped. Given the ROW's session it is "today".

    Both halves are asserted: the first documents the pre-fix behaviour still
    reachable via `asof=None` (the nightly desk's legitimate reading), the
    second is the fix.
    """
    from engine.marketing import movers_source as ms
    assert ms.session_phrase(MON) == "on Friday"          # clock-inferred
    assert ms.session_phrase(MON, asof=MON_DAY) == "today"  # row-derived
    assert ms.session_phrase(MON, asof=FRI_DAY) == "on Friday"

    item = {"theme": "Virtual & Augmented Reality", "direction": "up",
            "members": [{"ticker": t, "pct": p} for t, p in _EIGHT.items()],
            "agg_pct": 3.7, "question": "", "asof": MON_DAY}
    agg = next(f["text"] for f in ms.theme_facts(item, now=MON, asof=MON_DAY)["facts"]
               if f["id"] == "theme_agg")
    assert "today" in agg and "Friday" not in agg, agg

    mover = {"ticker": "FSLR", "name": "First Solar", "pct": 10.3,
             "sector": "Technology", "asof": MON_DAY}
    lead = ms.mover_facts(mover, now=MON, asof=MON_DAY)["facts"][0]["text"]
    assert "today" in lead and "Friday" not in lead, lead


def test_a_lane_post_carries_ONE_session_across_first_line_body_and_card(
        tmp_path, monkeypatch, real_card):
    """END TO END on the live post's own clock: Monday rows, Monday wall clock.

    All three surfaces must name 2026-08-03. Pre-fix the body said "on Friday"
    here — this is the regression pin for the shipped post.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _write_themes_meta(tmp_path, [_theme_tile("Virtual & Augmented Reality",
                                              {t: 0.0 for t in _EIGHT})],
                       asof=MON_DAY, generated_utc=MON.strftime("%Y-%m-%d %H:%M"))
    _write_snapshot(tmp_path, {t: (100.0, 100.0 - p, p) for t, p in _EIGHT.items()},
                    asof=MON.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    ts_ms=int(MON.timestamp() * 1000))

    rep = _gen(tmp_path, _cfg(), now=MON)
    assert rep["generated"], rep["dropped"]
    tl = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")

    # (1)+(2) first line and body: exactly one session, and it is the rows'.
    claims, unresolved = pt._session_claims(tl["text"], now=MON)
    assert not unresolved, (unresolved, tl["text"])
    assert {d.isoformat() for d in claims} == {MON_DAY}, (claims, tl["text"])
    assert "Friday" not in tl["text"], tl["text"]
    # (3) the card. Its stamp is the row session, which is also the item's as_of.
    assert tl["as_of"] == MON_DAY
    assert MON_DAY in tl["media"][0]["path"], tl["media"][0]["path"]
    assert tl["source"]["session_asof"] == MON_DAY, tl["source"]


def test_friday_rows_posted_on_monday_never_reach_the_copy(tmp_path):
    """The OTHER direction of "one session per post": rows from a prior session
    cannot wear this lane's banks (every template says "today" in its own words
    and this lane does not own copywriter), so they are refused BY NAME rather
    than published with a re-worded day.

    The complementary path — a Friday day-word on Friday rows — is pinned at the
    facts level in test_the_body_day_word_now_comes_from_the_row_not_the_clock.

    HEATMAP-ONLY on purpose (no live snapshot): a snapshot feed is by definition
    the current session, so _overlay_movers would re-date every covered row to
    Monday and the fixture would stop being Friday's data at all.
    """
    _write_themes_meta(tmp_path, [_theme_tile("Virtual & Augmented Reality", _EIGHT)],
                       asof=FRI_DAY, generated_utc=MON.strftime("%Y-%m-%d %H:%M"))
    rep = _gen(tmp_path, _cfg(), now=MON, live=False)

    assert rep["would_generate"] == [], rep["would_generate"]
    stale = [d for d in rep["dropped"] if d["reason"] == "stale_session"]
    assert stale and FRI_DAY in stale[0]["detail"], rep["dropped"]


def test_a_card_dated_to_another_session_is_rejected():
    """The THIRD surface has its own refusal. Nothing in the text is wrong here —
    only the picture's date is — and it is still not publishable.

    Mutation check for `as_of=cand_session` in the card call: restore
    `as_of=today` and the two agree only for as long as the row-session gate
    holds them equal; this is the check that says they MUST.
    """
    ok = LIVE_MIXED_POST.replace("on Friday", "today")
    reason = pt._session_conflict(ok, now=MON, row_session=MON_DAY,
                                  card_session=FRI_DAY)
    assert reason and reason.startswith("card_session_mismatch"), reason


def test_a_today_word_with_no_session_in_progress_is_rejected():
    """Saturday 2026-08-01: nothing is in progress, so "today" names no session
    at all. Refused as unresolvable rather than silently resolved to Friday —
    the same defect class as ob-2026-08-01-a83c188711 ("$AMZN +15.3% today",
    written on a Saturday)."""
    sat = datetime(2026, 8, 1, 17, 30, 0, tzinfo=timezone.utc)
    reason = pt._session_conflict("AMZN surged +15.3% today.", now=sat,
                                  row_session=FRI_DAY, card_session=FRI_DAY)
    assert reason and reason.startswith("unresolvable_session_claim"), reason


def test_a_post_with_no_temporal_word_makes_no_session_claim():
    """The degradation path. market_clock returns an EMPTY phrase when no word
    can be justified, so copy legitimately ships with none — and a post that
    claims no session cannot claim the wrong one."""
    assert pt._session_conflict("Tape check. Not touching it yet.", now=MON,
                                row_session=MON_DAY, card_session=MON_DAY) is None


def test_two_wordings_of_the_SAME_session_are_not_a_conflict():
    """Resolution is to a DATE, not to a string — otherwise "today" and "on
    Monday" said on a Monday would read as two sessions and the check would
    reject honest copy. The whole point of resolving before comparing."""
    claims, unresolved = pt._session_claims(
        "Up today. Monday's tape was the tell.", now=MON)
    assert not unresolved
    assert {d.isoformat() for d in claims} == {MON_DAY}, claims
    assert pt._session_conflict("Up today. Monday's tape was the tell.",
                                now=MON, row_session=MON_DAY,
                                card_session=MON_DAY) is None


def test_the_date_claim_regexes_do_not_manufacture_a_false_conflict():
    """A false positive here is TERMINAL — it kills an honest post — so the two
    resolvers are narrowed and pinned.

    "Market 5" must not read as a March date (the `Mar[a-z]*` wildcard shape
    would), and a bare month name with no day number names no session at all.
    The positive controls sit alongside so a regex that matches NOTHING (the
    other way to make this test pass) fails too.
    """
    def claims(s):
        c, u = pt._session_claims(s, now=MON)
        assert not u, (s, u)
        return {d.isoformat() for d in c}

    assert claims("Market 5 names higher.") == set()
    assert claims("Marching 3 names into the group.") == set()
    assert claims("May the trend hold.") == set()
    # positive controls — the shapes market_clock.temporal_vocab actually emits
    assert claims("Ripped on July 31.") == {FRI_DAY}
    assert claims("Ripped on Jul 31.") == {FRI_DAY}
    assert claims("Up today.") == {MON_DAY}
# ─────────────────────────────────────────────────────────────────────────────
# Trend-context enrichment (FSLR postmortem, 2026-08-03): _build_candidates
# stamps _mover_data.trend_context from the same local daily bars the mover
# card renders, so the copywriter's bucket lines can fire. Fail-soft: a store
# with no bars (or a loader crash) must leave the candidate exactly as before.
# ─────────────────────────────────────────────────────────────────────────────

def _washout_closes(n: int = 70) -> tuple[list[str], list[float]]:
    closes = [320.0 - i * (120.0 / (n - 1)) for i in range(n)] + [220.6]
    return ([f"d{i}" for i in range(len(closes))], closes)


def test_build_candidates_stamps_trend_context(monkeypatch, tmp_path):
    import engine.marketing.chart_render as chart_render

    monkeypatch.setattr(chart_render, "load_closes",
                        lambda tkr, root, n=90: _washout_closes())
    overlaid = {"sp500_tiles": [_tile("FSLR", 10.3)], "theme_tiles": [],
                "asof": "2026-08-03"}
    cfg = _cfg()
    # `now` became REQUIRED when the session-claim check landed (defect 2):
    # every candidate resolves its day-words against this clock. MON matches the
    # fixtures' asof, so the mover reads as "today" and no session gate fires.
    cands = pt._build_candidates(
        overlaid, tmp_path, cfg, cfg["publish"]["publish_time_movers"], now=MON)
    movers = [c for c in cands if c.get("type") == "mover"]
    assert movers, "fixture mover should survive min_abs"
    assert movers[0]["_mover_data"]["trend_context"] == "washout_bounce"


def test_build_candidates_survives_a_closes_loader_crash(monkeypatch, tmp_path):
    import engine.marketing.chart_render as chart_render

    def _boom(tkr, root, n=90):
        raise RuntimeError("no store on this host")

    monkeypatch.setattr(chart_render, "load_closes", _boom)
    overlaid = {"sp500_tiles": [_tile("FSLR", 10.3)], "theme_tiles": [],
                "asof": "2026-08-03"}
    cfg = _cfg()
    # `now` became REQUIRED when the session-claim check landed (defect 2):
    # every candidate resolves its day-words against this clock. MON matches the
    # fixtures' asof, so the mover reads as "today" and no session gate fires.
    cands = pt._build_candidates(
        overlaid, tmp_path, cfg, cfg["publish"]["publish_time_movers"], now=MON)
    movers = [c for c in cands if c.get("type") == "mover"]
    assert movers, "a context failure must never cost the post itself"
    assert "trend_context" not in movers[0]["_mover_data"]


def test_every_hard_indexed_lane_key_has_an_in_code_default():
    """Every `pt["key"]` the module hard-indexes must exist in `_DEFAULTS`.

    `resolve()` builds the lane dict as `dict(_DEFAULTS)` overlaid with the YAML
    block, so `_DEFAULTS` -- NOT config/marketing.yml -- is what makes a
    subscript safe. A key added to the code and to the unit fixture but to
    neither would raise KeyError on the first live sweep, and no test in this
    file could see it: `_cfg()` is hand-written, so it only ever proves the code
    agrees with the fixture.

    Asserting against the YAML instead would be wrong in the other direction:
    the block is explicitly designed so an operator can omit a key and take the
    default ("config-driven with an in-code default so an operator can retune it
    without a deploy"), and `require_card` is deliberately absent from the file.

    Derived from the source rather than a hand-kept list, because a hand-kept
    list is the same drift one level up.
    """
    import re
    from pathlib import Path

    src = Path(pt.__file__).read_text()
    # `pt` is the lane-config parameter name throughout the module. Only the
    # unguarded subscripts can raise; `.get(...)` with a default cannot.
    keys = set(re.findall(r'\bpt\["([a-z_]+)"\]', src))
    assert keys, "no hard-indexed lane keys found - has the parameter been renamed?"

    missing = sorted(k for k in keys if k not in pt._DEFAULTS)
    assert not missing, (
        "publish_time_content hard-indexes lane keys with no entry in _DEFAULTS: "
        f"{missing}. resolve() cannot supply them, so the live lane raises "
        "KeyError on its first sweep; the hand-written _cfg() fixture cannot "
        "see this."
    )


# ─────────────────────────────────────────────────────────────────────────────
# The theme's own ticker — the sector ETF / underlying asset (2026-08-05)
#
# Operator, on a live "Commodities Metals bid up" post that named $GFI $AEM $KGC:
#   "for this kind of theme, shouldnt u be prioritizing tagging the underlying
#   major ETF or even the underlying commodity/asset class ... these are much
#   larger tickers that are able to get much more reach than the three u used"
#
# The gate itself is tested in tests/test_marketing_theme_proxy.py. These tests
# cover the WIRING: that a released proxy reaches the post text, that it costs one
# member slot rather than widening the cashtag count, that the arm is stamped on
# both arms, and that the kill switch is a real kill switch.
# ─────────────────────────────────────────────────────────────────────────────

_METALS = {"GFI": 10.2, "AEM": 9.0, "KGC": 8.6, "AU": 8.2,
           "HL": 8.0, "EXK": 7.5, "CDE": 7.3, "PAAS": 7.2}
_PROXY_THEME = "Commodities Metals"


def _write_proxy_bars(tmp: Path, tickers, *, rho: float, seed: int = 5,
                      n: int = 260) -> None:
    """Correlated bars under the curated tree theme_proxy.cohesion reads first.

    Gated, not bare: theme_proxy.cohesion is the one code path in this suite that
    genuinely needs the data stack (it reads the parquet through pandas and means
    the pairwise correlations through numpy — both LAZY inside the module, which
    is why importing publish_time_content still costs only stdlib). The bar
    fixture has to pay what the code under test pays. A bare `import numpy` here
    ERRORS in the thin pytest+pyyaml lane that names this file, which is how nine
    tests turned main red from #4646 onward. The gate makes them skip there; the
    marketing-data lane names this file so they actually execute.
    """
    import math

    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")  # DataFrame.to_parquet needs a parquet engine
    rng = np.random.default_rng(seed)
    d = tmp / "data" / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2025-01-01", periods=n)
    factor = rng.normal(0, 0.01, n)
    load = math.sqrt(max(0.0, min(1.0, rho)))
    for t in tickers:
        r = load * factor + math.sqrt(1 - load ** 2) * rng.normal(0, 0.01, n)
        pd.DataFrame({"date": dates,
                      "close": 100.0 * np.cumprod(1.0 + r)}).to_parquet(d / f"{t}.parquet")


def _write_proxy_map(tmp: Path, *, fund: str = "GDX", basis: str = "holdings",
                     holdings=None) -> None:
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    cand: dict = {"ticker": fund, "basis": basis, "adv20_musd": 1321.0}
    if basis == "holdings":
        held = list(holdings if holdings is not None else _METALS)
        cand.update({"asof": "2026-07-30", "holdings": held,
                     "weights": {t: 5.0 for t in held}})
    (p / "theme_proxy_map.json").write_text(json.dumps({
        "schema": "theme_proxy_map/1",
        "themes": {_PROXY_THEME: {"candidates": [cand]}},
    }), encoding="utf-8")


def _metals_theme(tmp: Path, *, rho: float = 0.85, proxy: bool = True,
                  fund: str = "GDX", basis: str = "holdings",
                  holdings=None) -> None:
    """The shipped post's shape: 8 cohesive miners, a fund that out-trades them.

    ADV mirrors the live numbers ($GFI $117M ... $HL $599M vs $GDX $1,321M), so
    the reach ratio the test exercises is the one the operator was looking at.
    """
    _write_themes(tmp, [_theme_tile(_PROXY_THEME, {t: 0.0 for t in _METALS})])
    _write_snapshot(tmp, {t: (100.0, 100.0 - p, p) for t, p in _METALS.items()})
    _write_tiers(tmp, {"GFI": 117.0, "AEM": 358.0, "KGC": 176.0, "AU": 197.0,
                       "HL": 599.0, "EXK": 46.0, "CDE": 426.0, "PAAS": 169.0,
                       fund: 1321.0})
    _write_proxy_bars(tmp, list(_METALS), rho=rho)
    if proxy:
        _write_proxy_map(tmp, fund=fund, basis=basis, holdings=holdings)


def _only_theme(rep: dict) -> dict:
    tls = [g for g in rep["would_generate"] if g["kind"] == "theme_list"]
    assert tls, (rep["would_generate"], rep["dropped"])
    return tls[0]


def test_a_cohesive_theme_names_its_own_ticker_first(tmp_path):
    """THE OPERATOR'S CASE, end to end.

    $GDX trades 3.7x the biggest name the text would otherwise have named ($AEM
    at $358M) and 11.3x the one it actually led with ($GFI at $117M).
    """
    _metals_theme(tmp_path)
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert "GDX" in named, named


def test_the_proxy_costs_a_member_slot_not_a_cashtag(tmp_path):
    """THE ACCOUNT-SAFETY INVARIANT. The cap is X's spam threshold, not a budget
    to spend on funds: adding the proxy must not make the post 4 cashtags wide.

    Mutation check: append the proxy instead of prepending-and-truncating (drop the
    `[:text_cap - 1]` slice) and the count goes to 4, which is the fingerprint
    max_theme_cashtags_in_text exists to prevent.
    """
    _metals_theme(tmp_path)
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert len(named) <= pt._DEFAULTS["max_theme_cashtags_in_text"], named
    # ...and it is the LEAST-WATCHED member that gives up its slot, not a
    # more-watched one: $HL/$CDE (599/426) stay, $KGC (176) goes.
    assert "HL" in named, named


def test_the_proxy_does_not_evict_every_name(tmp_path):
    """A theme post that names no names is not a theme post. Exactly one slot."""
    _metals_theme(tmp_path)
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert len(named - {"GDX"}) >= 1, named


def test_an_incohesive_theme_names_no_proxy(tmp_path):
    """Same fund, same reach, same holdings — rows that do not move together.

    This is the $XBI shape, and it is the difference between this feature and
    "always tag the sector ETF". Mutation check for the whole gate being wired in
    at all: bypass theme_proxy.resolve and this ships $GDX on an incoherent group.
    """
    _metals_theme(tmp_path, rho=0.02)
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert "GDX" not in named, named


def test_a_declared_commodity_proxy_ships_the_same_way(tmp_path):
    """$GLD on gold miners — the bullion class the operator asked for.

        "When gold goes up, its miners go up, its that simple, don't need to
        overcomplicate and shit."

    Nothing in the copy marks it as a different class; it is a tag like any other.
    """
    _metals_theme(tmp_path, fund="GLD", basis="declared")
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert "GLD" in named, named


def test_the_arm_is_stamped_on_BOTH_arms(tmp_path, monkeypatch, real_card):
    """post_metrics needs a control group, not just a treatment group.

    ADV is a proxy for X reach, not a measurement of it, so the only way this stops
    being an unfalsifiable prior is if both arms are labelled and impressions get
    to settle it. Mutation check: stamp `tag_arm` only when a proxy is released and
    the members_only assertion fails — which is the shape that would leave the
    comparison ungradeable while looking instrumented.
    """
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _metals_theme(tmp_path)
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    item = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    src = item["source"]
    assert src["tag_arm"] == "proxy_lead", src
    assert src["tag_proxy"]["ticker"] == "GDX"
    # The receipts travel with the post: reach ratio, cohesion, coverage.
    r = src["tag_proxy"]["receipts"]
    assert r["reach_ratio"] > 1.0 and r["cohesion_rho"] > 0.65
    assert r["rows_held"] == len(_METALS)


def test_the_control_arm_is_labelled_too(tmp_path, monkeypatch, real_card):
    """The members_only half of the pair above — no map, so no proxy, but the item
    still carries the arm so the two are comparable."""
    monkeypatch.setattr(real_card, "publish_card", _hosted())
    _metals_theme(tmp_path, proxy=False)
    rep = _gen(tmp_path, _cfg())
    assert rep["generated"], rep["dropped"]
    item = next(i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list")
    assert item["source"]["tag_arm"] == "members_only", item["source"]
    assert "tag_proxy" not in item["source"]


def test_the_kill_switch_restores_member_only_tagging(tmp_path):
    """theme_proxy_enabled=false must be a clean revert, not a degraded mode."""
    _metals_theme(tmp_path)
    cfg = _cfg()
    cfg["publish"]["publish_time_movers"]["theme_proxy_enabled"] = False
    on = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    off = _named_cashtags(_only_theme(_gen(tmp_path, cfg, live=False))["text"])
    assert "GDX" in on and "GDX" not in off, (on, off)
    # OFF is the pre-feature behaviour exactly: three members, no fund.
    assert len(off) == pt._DEFAULTS["max_theme_cashtags_in_text"], off


def test_a_proxy_the_card_barely_holds_is_refused_end_to_end(tmp_path):
    """The piggyback shape, wired: a fund holding 1 of 8 rows never reaches a post.

    $SMH on Industrial Automation (1/8 rows, 1.8% of the fund) was a live
    reach-only hit in the sweep. This is its end-to-end refusal.
    """
    _metals_theme(tmp_path, holdings=["GFI"])
    named = _named_cashtags(_only_theme(_gen(tmp_path, _cfg(), live=False))["text"])
    assert "GDX" not in named, named
