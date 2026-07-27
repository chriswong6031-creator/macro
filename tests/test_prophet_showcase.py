"""tests/test_prophet_showcase.py — landing showcase slice (build_prophet.py).

The showcase payload is the public teaser the marketing landing
(templates/index.html #f-prophet) renders. It is a DELAYED-WINNERS slice
(operator order 2026-07-24): winning calls from the freshest fully-graded
board in data/us_board_ledger — never the live board. Card derivation must
MIRROR the pv_card cx construction in templates/dashboard.html.j2 — these
tests pin that mirror and the selection contract.

Coverage:
  1.  Verb mapping: every entry_signal.status → the board verb, incl. the
      dir-based fallback when status is absent.
  2.  Stage mapping: lane → 1..4, absent/unknown lane → 0.
  3.  Zone kinds: active/readd/muted with a zone; confirm/none without.
  4.  Zone formatting: $%.2f, lo omitted when absent.
  5.  Not-showable rows (no ticker / price / spark) → None.
  6.  Flags: 'accounting watch' dropped, zh pairing with EN fallback,
      ext_z / earnings_soon / sector_stance / base-broken folds.
  7.  Selection: winners only (ret > 0), ranked by return desc, capped at
      limit, since_pct stamped; boards without a snapshot are skipped in
      favour of the freshest one that has both grades and a snapshot;
      < min_winners → None (callers keep the previous payload).
  8.  write_showcase round-trip: schema v2 keys, board as_of passthrough,
      no affirmative 'validated' in payload-authored copy, fail-soft keeps
      the previous file on missing inputs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_prophet import (  # noqa: E402
    SHOWCASE_HORIZON,
    SHOWCASE_LIMIT,
    build_showcase_payload,
    derive_showcase_card,
    write_showcase,
)

SPARK = '<svg class="nch" viewBox="0 0 240 42"><polyline points="0,42 1,1"/></svg>'


def test_landing_stage_labels_survive_browser_minimum_font_scaling():
    """The equal-width stage rail must not rely on sub-8px long labels fitting.

    Some browsers/accessibility settings promote micro-copy to a larger minimum
    font size. Compact glance labels keep all four stages collision-free while
    the rail's aria-label retains the current-stage meaning for assistive tech.
    """
    root = Path(__file__).resolve().parent.parent
    expected = (
        '<span class="stg" data-zh="筑底">Base</span>'
        '<span class="stg" data-zh="转折">Turn</span>'
        '<span class="stg on" data-zh="就绪">Ready</span>'
        '<span class="stg" data-zh="趋势">Trend</span>'
    )
    for rel in ("templates/index.html", "site/index.html"):
        html = (root / rel).read_text(encoding="utf-8")
        compact = "".join(line.strip() for line in html.splitlines())
        assert expected in compact, f"{rel} regressed to labels that can collide"
        assert 'class="psc-stages" aria-label="Setup stage: Ready"' in html


def test_landing_prophet_belt_is_faster_only_on_mobile():
    """Mobile gets a shorter drift cycle without changing the desktop cadence."""
    root = Path(__file__).resolve().parent.parent
    for rel in ("templates/landing.css", "site/landing.css"):
        css = (root / rel).read_text(encoding="utf-8")
        assert ".ph-track.run{animation:phDrift 95s linear infinite}" in css
        assert (
            "@media (max-width:640px){\n"
            "  .psec .ph-head{grid-template-columns:1fr;gap:12px}\n"
            "  .ph-track.run{animation-duration:60s}\n"
        ) in css


def _row(**over) -> dict:
    """A minimal showable us_standouts.buy row; override freely."""
    base = {
        "ticker": "TEST",
        "name": "Test Corp",
        "sector": "Industrials",
        "price": 100.0,
        "spark_svg": SPARK,
        "lane": "bottoming",
        "dir": "up",
        "entry_signal": {"status": "buy_now", "buy_zone": {"low": 95.0, "high": 99.0}},
        "conviction": {"score_edge": 88, "cautions": [], "cautions_zh": []},
        "signal": {"asof": "2026-07-21"},
    }
    base.update(over)
    return base


# ── 1. verb mapping ─────────────────────────────────────────────────────────

def test_verb_mapping_mirrors_board():
    expect = {
        "buy_now": "buy", "partial": "buy",
        "buy_soon": "near", "await_confluence": "near",
        "hold": "hold", "topping": "hold",
        "exit": "avoid", "avoid": "avoid",
        "some_future_status": "wait",
    }
    for status, verb in expect.items():
        card = derive_showcase_card(_row(entry_signal={"status": status}))
        assert card is not None
        assert card["verb"] == verb, f"status={status}"


def test_verb_fallback_on_missing_status_uses_dir():
    assert derive_showcase_card(_row(entry_signal={}, dir="up"))["verb"] == "near"
    assert derive_showcase_card(_row(entry_signal={}, dir="down"))["verb"] == "avoid"
    assert derive_showcase_card(_row(entry_signal={}, dir=None))["verb"] == "wait"


# ── 2. stage mapping ────────────────────────────────────────────────────────

def test_stage_mapping():
    for lane, stage in [("bottoming", 1), ("recovery", 2),
                        ("continuation", 3), ("trend", 4),
                        (None, 0), ("mystery_lane", 0)]:
        assert derive_showcase_card(_row(lane=lane))["stage"] == stage


# ── 3+4. zone kinds and formatting ──────────────────────────────────────────

def test_zone_kinds_with_zone():
    z = {"low": 95.0, "high": 99.0}
    for status, kind in [("buy_now", "active"), ("buy_soon", "active"),
                         ("hold", "readd"), ("some_wait", "muted")]:
        card = derive_showcase_card(_row(entry_signal={"status": status, "buy_zone": z}))
        assert card["zone_kind"] == kind, f"status={status}"
        assert card["zone_lo"] == "$95.00"
        assert card["zone_hi"] == "$99.00"


def test_zone_kinds_without_zone():
    card = derive_showcase_card(_row(entry_signal={"status": "some_wait"}))
    assert card["zone_kind"] == "confirm"
    assert card["zone_lo"] is None and card["zone_hi"] is None
    card = derive_showcase_card(_row(entry_signal={"status": "exit"}))
    assert card["zone_kind"] == "none"
    # zone with high but no low: hi renders, lo stays None
    card = derive_showcase_card(
        _row(entry_signal={"status": "buy_now", "buy_zone": {"high": 99.5}}))
    assert card["zone_kind"] == "active"
    assert card["zone_lo"] is None and card["zone_hi"] == "$99.50"


# ── 5. not showable ─────────────────────────────────────────────────────────

def test_unshowable_rows_return_none():
    assert derive_showcase_card(_row(ticker=None)) is None
    assert derive_showcase_card(_row(price=None)) is None
    assert derive_showcase_card(_row(spark_svg=None)) is None


# ── 6. flags ────────────────────────────────────────────────────────────────

def test_flags_fold_and_zh_pairing():
    card = derive_showcase_card(_row(
        conviction={"score_edge": 50,
                    "cautions": ["accounting watch", "sector below trend"],
                    "cautions_zh": ["会计观察", "板块低于趋势"]},
        ext_z=2.4,
        earnings_soon={"days_to": 5, "chip_en": "Earnings in 5d", "chip_zh": "财报还有5天"},
        sector_stance="Reduce", sector_stance_zh="减持",
        hold={"state": "broken"},
    ))
    texts = [f[0] for f in card["flags"]]
    assert "accounting watch" not in texts           # dropped, like the board
    assert "sector below trend" in texts
    assert any("Extended 2.4σ" in t for t in texts)
    assert "Earnings in 5d" in texts
    assert any(t.startswith("Sector stance: Reduce") for t in texts)
    assert any(t.startswith("Base broken") for t in texts)
    # zh side paired; EN fallback when cautions_zh is short
    zh = dict(card["flags"])["sector below trend"]
    assert zh == "板块低于趋势"
    card2 = derive_showcase_card(_row(
        conviction={"score_edge": 50, "cautions": ["only en"], "cautions_zh": []}))
    assert card2["flags"][0] == ["only en", "only en"]


# ── 7. delayed-winners selection ────────────────────────────────────────────

def _grades(rows):
    """rows: (as_of, ticker, ret) at buy-lane, SHOWCASE_HORIZON."""
    return pd.DataFrame([
        {"as_of": a, "ticker": t, "ret": r, "lane": "buy",
         "horizon": SHOWCASE_HORIZON} for a, t, r in rows
    ])


def _snap(tickers):
    return {"buy": [_row(ticker=t) for t in tickers]}


def test_selection_winners_only_ranked_with_since_pct():
    grades = _grades([
        ("2026-07-06", "WIN2", 0.05), ("2026-07-06", "LOSER", -0.08),
        ("2026-07-06", "WIN1", 0.223), ("2026-07-06", "FLAT", 0.0),
        ("2026-07-06", "WIN3", 0.01), ("2026-07-06", "WIN4", 0.02),
        ("2026-07-06", "WIN5", 0.03), ("2026-07-06", "WIN6", 0.04),
    ])
    snaps = {"2026-07-06": _snap(["WIN1", "WIN2", "WIN3", "WIN4", "WIN5",
                                  "WIN6", "LOSER", "FLAT"])}
    payload = build_showcase_payload(grades, snaps, min_winners=6)
    assert payload is not None
    tks = [c["tk"] for c in payload["cards"]]
    assert tks == ["WIN1", "WIN2", "WIN6", "WIN5", "WIN4", "WIN3"]  # ret desc
    assert "LOSER" not in tks and "FLAT" not in tks
    assert payload["cards"][0]["since_pct"] == 22.3
    assert all(c["since_pct"] > 0 for c in payload["cards"])
    assert payload["schema"] == "prophet.showcase/v2"
    assert payload["kind"] == "delayed_winners"
    assert payload["as_of"] == "2026-07-06"
    assert payload["window_sessions"] == SHOWCASE_HORIZON


def test_selection_prefers_freshest_board_with_snapshot():
    grades = _grades(
        [("2026-07-10", f"N{i}", 0.05) for i in range(8)]      # no snapshot
        + [("2026-07-06", f"O{i}", 0.04) for i in range(8)])   # snapshot ✓
    snaps = {"2026-07-06": _snap([f"O{i}" for i in range(8)])}
    payload = build_showcase_payload(grades, snaps, min_winners=6)
    assert payload is not None and payload["as_of"] == "2026-07-06"


def test_selection_caps_at_limit_and_needs_min_winners():
    many = _grades([("2026-07-06", f"W{i:02d}", 0.01 + i / 100)
                    for i in range(SHOWCASE_LIMIT + 5)])
    snaps = {"2026-07-06": _snap([f"W{i:02d}"
                                  for i in range(SHOWCASE_LIMIT + 5)])}
    payload = build_showcase_payload(many, snaps, min_winners=6)
    assert payload["count"] == len(payload["cards"]) == SHOWCASE_LIMIT
    # too few winners → None (caller keeps the previous payload)
    few = _grades([("2026-07-06", "A", 0.05), ("2026-07-06", "B", -0.02)])
    assert build_showcase_payload(few, {"2026-07-06": _snap(["A", "B"])},
                                  min_winners=6) is None


def test_selection_ignores_other_lanes_and_horizons():
    df = _grades([("2026-07-06", f"W{i}", 0.05) for i in range(6)])
    other = pd.DataFrame([
        {"as_of": "2026-07-06", "ticker": "WATCHY", "ret": 0.5,
         "lane": "watch", "horizon": SHOWCASE_HORIZON},
        {"as_of": "2026-07-06", "ticker": "SHORTH", "ret": 0.5,
         "lane": "buy", "horizon": 5},
    ])
    grades = pd.concat([df, other], ignore_index=True)
    snaps = {"2026-07-06": _snap([f"W{i}" for i in range(6)]
                                 + ["WATCHY", "SHORTH"])}
    payload = build_showcase_payload(grades, snaps, min_winners=6)
    tks = [c["tk"] for c in payload["cards"]]
    assert "WATCHY" not in tks and "SHORTH" not in tks


# ── 8. write round-trip ─────────────────────────────────────────────────────

def _write_fixture_ledger(tmp_path, n_winners=6):
    gpath = tmp_path / "retro_grades.parquet"
    spath = tmp_path / "snapshots.jsonl"
    _grades([("2026-07-06", f"W{i}", 0.02 + i / 100)
             for i in range(n_winners)]).to_parquet(gpath)
    spath.write_text(json.dumps(
        {"as_of": "2026-07-06",
         "buy": [_row(ticker=f"W{i}") for i in range(n_winners)]}) + "\n",
        encoding="utf-8")
    return gpath, spath


def test_write_showcase_roundtrip(tmp_path):
    gpath, spath = _write_fixture_ledger(tmp_path)
    out = tmp_path / "showcase.json"
    payload = write_showcase(grades_path=gpath, snapshots_path=spath,
                             out_path=out)
    assert payload is not None and out.exists()
    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["schema"] == "prophet.showcase/v2"
    assert disk["kind"] == "delayed_winners"
    assert disk["as_of"] == "2026-07-06"
    assert disk["authority_tier"] == "display"
    assert disk["count"] == 6
    card = disk["cards"][0]
    for key in ("tk", "name", "sec", "sec_zh", "price_txt", "verb", "edge",
                "stage", "zone_kind", "zone_lo", "zone_hi", "date", "flags",
                "triage", "spark", "since_pct"):
        assert key in card, key
    # payload-authored copy never claims 'validated'
    assert "validated" not in disk["note"].lower()


def test_write_showcase_fail_soft_keeps_previous(tmp_path):
    out = tmp_path / "showcase.json"
    out.write_text('{"schema":"prophet.showcase/v2","cards":[1]}',
                   encoding="utf-8")
    prev = out.read_text(encoding="utf-8")
    # missing grades file → None AND the previous payload survives untouched
    assert write_showcase(grades_path=tmp_path / "missing.parquet",
                          snapshots_path=tmp_path / "missing.jsonl",
                          out_path=out) is None
    assert out.read_text(encoding="utf-8") == prev
