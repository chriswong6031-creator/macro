"""tests/test_prophet_showcase.py — landing showcase slice (build_prophet.py).

The showcase payload is the public teaser the marketing landing
(templates/index.html #f-prophet) fetches instead of the ~1MB
us_standouts.json. Its card derivation must MIRROR the pv_card cx
construction in templates/dashboard.html.j2 — these tests pin that mirror.

Coverage:
  1.  Verb mapping: every entry_signal.status → the board verb, incl. the
      dir-based fallback when status is absent.
  2.  Stage mapping: lane → 1..4, absent/unknown lane → 0.
  3.  Zone kinds: active/readd/muted with a zone; confirm/none without.
  4.  Zone formatting: $%.2f, lo omitted when absent.
  5.  Not-showable rows (no ticker / price / spark) → None.
  6.  Flags: 'accounting watch' dropped, zh pairing with EN fallback,
      ext_z / earnings_soon / sector_stance / base-broken folds.
  7.  Curation: board order preserved; wait+hold vocabulary breadth is
      guaranteed by tail swaps when the top slice is all-green.
  8.  write_showcase round-trip: schema keys, as_of passthrough, no
      affirmative 'validated' in payload-authored copy, fail-soft on a
      missing standouts file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_prophet import (  # noqa: E402
    SHOWCASE_LIMIT,
    build_showcase_payload,
    derive_showcase_card,
    write_showcase,
)

SPARK = '<svg class="nch" viewBox="0 0 240 42"><polyline points="0,42 1,1"/></svg>'


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


# ── 7. curation ─────────────────────────────────────────────────────────────

def test_curation_keeps_board_order_and_guarantees_breadth():
    rows = [_row(ticker=f"B{i:02d}") for i in range(SHOWCASE_LIMIT + 3)]
    rows.append(_row(ticker="WAITER", entry_signal={"status": "cooling"}))
    rows.append(_row(ticker="HOLDER", entry_signal={"status": "hold"}))
    payload = build_showcase_payload({"as_of": "2026-07-22", "buy": rows})
    cards = payload["cards"]
    assert payload["count"] == len(cards) == SHOWCASE_LIMIT
    verbs = {c["verb"] for c in cards}
    assert {"wait", "hold"} <= verbs
    # head of the slice is untouched board order
    assert [c["tk"] for c in cards[:SHOWCASE_LIMIT - 2]] == \
        [f"B{i:02d}" for i in range(SHOWCASE_LIMIT - 2)]


def test_curation_no_swap_when_breadth_already_present():
    rows = [
        _row(ticker="A", entry_signal={"status": "buy_now"}),
        _row(ticker="B", entry_signal={"status": "cooling"}),
        _row(ticker="C", entry_signal={"status": "hold"}),
    ]
    payload = build_showcase_payload({"as_of": "2026-07-22", "buy": rows})
    assert [c["tk"] for c in payload["cards"]] == ["A", "B", "C"]


# ── 8. write round-trip ─────────────────────────────────────────────────────

def test_write_showcase_roundtrip(tmp_path):
    src = tmp_path / "us_standouts.json"
    src.write_text(json.dumps({"as_of": "2026-07-22", "buy": [_row()]}),
                   encoding="utf-8")
    out = tmp_path / "showcase.json"
    payload = write_showcase(standouts_path=src, out_path=out)
    assert payload is not None and out.exists()
    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["schema"] == "prophet.showcase/v1"
    assert disk["as_of"] == "2026-07-22"
    assert disk["authority_tier"] == "display"
    assert disk["count"] == 1
    card = disk["cards"][0]
    for key in ("tk", "name", "sec", "sec_zh", "price_txt", "verb", "edge",
                "stage", "zone_kind", "zone_lo", "zone_hi", "date", "flags",
                "triage", "spark"):
        assert key in card, key
    # payload-authored copy never claims 'validated'
    assert "validated" not in disk["note"].lower()


def test_write_showcase_fail_soft(tmp_path):
    out = tmp_path / "showcase.json"
    assert write_showcase(standouts_path=tmp_path / "missing.json",
                          out_path=out) is None
    assert not out.exists()
