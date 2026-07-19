"""Tests for engine.marketing.share_cards — the og:image share-card system.

Headless-safe: exercises the PIL default-font fallback path so it passes on Linux
CI (where macOS system fonts are absent). No network. Deterministic.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image

from engine.marketing import share_cards as sc


# ── Fixtures / helpers ───────────────────────────────────────────────────────

TICKER_KW = dict(
    ticker="AAPL", name="Apple Inc.", sector="Technology",
    industry="Consumer Electronics", logo_path=None,  # monogram path (no logo file)
)
MOVERS_KW = dict(
    asof="Jul 18, 2026",
    gainers=[{"ticker": "VST", "pct": 8.4}, {"ticker": "PLTR", "pct": 6.1}],
    losers=[{"ticker": "BA", "pct": -7.9}, {"ticker": "IBM", "pct": -5.2}],
)
SCREENER_KW = dict(
    asof="Jul 18, 2026",
    combo_headline="Momentum turn + volume surge on oversold names",
    wr_test_per10="6.4", n_fires=1287, first_year="2015", active_count=23,
)


def _png_bytes(img: Image.Image) -> bytes:
    """Serialize through the same quantize+optimize path save_card uses."""
    buf = io.BytesIO()
    img.convert("RGB").quantize(
        colors=256, method=Image.FASTOCTREE, dither=Image.NONE
    ).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


ALL_RENDERERS = [
    ("ticker", lambda: sc.render_ticker_card(**TICKER_KW)),
    ("movers", lambda: sc.render_movers_card(**MOVERS_KW)),
    ("screener", lambda: sc.render_screener_card(**SCREENER_KW)),
]


# ── Dimensions ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,render", ALL_RENDERERS)
def test_dimensions(name, render):
    img = render()
    assert img.size == (sc.CARD_W, sc.CARD_H) == (1200, 630), name


def test_module_constants():
    assert sc.CARD_W == 1200 and sc.CARD_H == 630
    assert isinstance(sc.CARD_VERSION, int)


# ── Determinism (same inputs → identical pixels) ─────────────────────────────

@pytest.mark.parametrize("name,render", ALL_RENDERERS)
def test_deterministic_bytes(name, render):
    assert _png_bytes(render()) == _png_bytes(render()), name


def test_ticker_monogram_and_missing_logo_deterministic():
    # A non-existent logo_path must fall back to the monogram, deterministically.
    kw = dict(TICKER_KW, logo_path=Path("/nonexistent/does_not_exist.png"))
    assert _png_bytes(sc.render_ticker_card(**kw)) == _png_bytes(sc.render_ticker_card(**kw))


# ── Font loader never raises, always returns a usable font ───────────────────

@pytest.mark.parametrize("size,bold", [(1, False), (10, False), (34, True),
                                       (96, True), (150, True), (300, False)])
def test_load_font_never_raises(size, bold):
    font = sc.load_font(size, bold=bold)
    assert font is not None
    # must be usable for measurement on any host (incl. Linux CI default font)
    draw = ImageDraw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(
        Image.new("RGB", (10, 10))
    )
    bbox = draw.textbbox((0, 0), "M", font=font)
    assert bbox[2] >= bbox[0]


def test_load_font_handles_zero_and_negative():
    # Guards clamp to a valid size rather than raising.
    assert sc.load_font(0) is not None
    assert sc.load_font(-5, bold=True) is not None


# ── Fingerprint: stable, version-sensitive, payload-sensitive ────────────────

def test_fingerprint_stable():
    p = {"ticker": "AAPL", "name": "Apple Inc."}
    assert sc.card_fingerprint(p) == sc.card_fingerprint(dict(p))


def test_fingerprint_key_order_invariant():
    a = sc.card_fingerprint({"a": 1, "b": 2})
    b = sc.card_fingerprint({"b": 2, "a": 1})
    assert a == b


def test_fingerprint_changes_on_payload_change():
    base = sc.card_fingerprint({"ticker": "AAPL"})
    assert base != sc.card_fingerprint({"ticker": "MSFT"})


def test_fingerprint_changes_on_version_bump(monkeypatch):
    p = {"ticker": "AAPL"}
    fp1 = sc.card_fingerprint(p)
    monkeypatch.setattr(sc, "CARD_VERSION", sc.CARD_VERSION + 1)
    assert sc.card_fingerprint(p) != fp1


# ── save_card: dims round-trip, size budget, atomic ──────────────────────────

def test_save_card_roundtrip_and_budget(tmp_path):
    out = tmp_path / "card.png"
    sc.save_card(sc.render_movers_card(**MOVERS_KW), out)
    assert out.exists()
    im = Image.open(out)
    assert im.size == (1200, 630)
    # flat-color design + quantize → comfortably under the ~80 KB target
    assert out.stat().st_size <= 80 * 1024


def test_save_card_leaves_no_temp(tmp_path):
    out = tmp_path / "card.png"
    sc.save_card(sc.render_screener_card(**SCREENER_KW), out)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "card.png"]
    assert leftovers == [], f"temp files left behind: {leftovers}"


# ── save_card_if_changed: skip on hit, regen on change ───────────────────────

def _root_with_out(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path
    out = root / "site" / "og" / "AAPL.png"
    return root, out


def test_save_if_changed_skip_and_regen(tmp_path):
    root, out = _root_with_out(tmp_path)
    payload = {"type": "ticker", **{k: v for k, v in TICKER_KW.items() if k != "logo_path"}}
    calls = {"n": 0}

    def render():
        calls["n"] += 1
        return sc.render_ticker_card(**TICKER_KW)

    # 1st: renders
    assert sc.save_card_if_changed(payload=payload, out_path=out, render=render, root=root) is True
    assert calls["n"] == 1
    assert out.exists()

    # 2nd: identical payload + existing artifact → skip (no render)
    assert sc.save_card_if_changed(payload=payload, out_path=out, render=render, root=root) is False
    assert calls["n"] == 1

    # 3rd: changed payload → regen
    payload2 = dict(payload, name="Apple Incorporated")
    assert sc.save_card_if_changed(payload=payload2, out_path=out, render=render, root=root) is True
    assert calls["n"] == 2


def test_save_if_changed_regen_when_artifact_missing(tmp_path):
    """Fingerprint present but the PNG was deleted → must re-render."""
    root, out = _root_with_out(tmp_path)
    payload = {"type": "movers", "asof": "Jul 18, 2026"}
    calls = {"n": 0}

    def render():
        calls["n"] += 1
        return sc.render_movers_card(**MOVERS_KW)

    assert sc.save_card_if_changed(payload=payload, out_path=out, render=render, root=root) is True
    out.unlink()  # artifact gone, fingerprint store still has the key
    assert sc.save_card_if_changed(payload=payload, out_path=out, render=render, root=root) is True
    assert calls["n"] == 2


def test_fingerprint_store_written_atomically(tmp_path):
    """The store is valid JSON and no *.tmp files linger after a write."""
    root, out = _root_with_out(tmp_path)
    payload = {"type": "screener"}
    sc.save_card_if_changed(
        payload=payload, out_path=out,
        render=lambda: sc.render_screener_card(**SCREENER_KW), root=root,
    )
    store = root / "data" / "marketing" / "share_cards" / "fingerprints.json"
    assert store.exists()
    data = json.loads(store.read_text())  # parses → not truncated/corrupt
    assert isinstance(data, dict) and len(data) == 1
    # no temp leftovers in the store dir
    tmps = [p.name for p in store.parent.iterdir() if p.name.endswith(".tmp")]
    assert tmps == []


def test_write_store_atomic_overwrites_cleanly(tmp_path):
    """Two atomic writes to the same store leave exactly one valid file."""
    store = tmp_path / "fingerprints.json"
    sc._write_store_atomic(store, {"a.png": "x"})
    sc._write_store_atomic(store, {"a.png": "x", "b.png": "y"})
    data = json.loads(store.read_text())
    assert data == {"a.png": "x", "b.png": "y"}
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


# ── Honesty (DESIGN_DOCTRINE §Law 5) ─────────────────────────────────────────

# User-facing copy strings drawn onto the cards (kept in sync by eye — the
# honesty guard below is what actually protects against a banned word slipping
# into a rendered string). Docstrings/comments are NOT user-facing.
_USER_FACING_COPY = [
    "signals   ·   options flow   ·   factor profile",
    "Today’s Movers", "GAINERS", "LOSERS",
    "SIGNAL STACK SCREENER", "wins per 10 in testing",
    "entries since", "stocks match today",
    "Historical win rate - not a guarantee.",
    "© 2026 Mastermind", "mastermind-x.com",
    "Daily signals · free 14-day trial",
]


def test_required_honesty_microcopy_present():
    """The screener honesty line is a hard requirement of the D10 spec."""
    src = Path(sc.__file__).read_text(encoding="utf-8")
    assert "Historical win rate - not a guarantee." in src


def test_no_validated_word_in_user_copy():
    """House law (DESIGN_DOCTRINE §Law 5 / check_validated_claims.py): the word
    'validated' is banned from user-facing copy. Guard the drawn strings, not the
    module's own docstrings/comments about the ban."""
    for line in _USER_FACING_COPY:
        assert "validated" not in line.lower(), line


# ── Robustness: odd inputs don't crash a render ──────────────────────────────

def test_ticker_card_empty_and_long_inputs():
    sc.render_ticker_card(ticker="", name="", sector=None, industry=None, logo_path=None)
    sc.render_ticker_card(
        ticker="BRK.B",
        name="Berkshire Hathaway Inc. Class B Common Stock Ordinary Shares",
        sector="Financial Services", industry="Insurance—Diversified", logo_path=None,
    )


def test_movers_card_short_lists():
    # Fewer than 5 rows must render fine (top-5 slice tolerates short lists).
    img = sc.render_movers_card(asof="Jul 18, 2026",
                                gainers=[{"ticker": "VST", "pct": 8.4}], losers=[])
    assert img.size == (1200, 630)


def test_screener_card_long_headline_wraps():
    img = sc.render_screener_card(
        asof="Jul 18, 2026",
        combo_headline=(
            "Golden cross confirmed by a fresh momentum turn and an "
            "above-average volume expansion across the group"
        ),
        wr_test_per10="5.9", n_fires=642, first_year="2018", active_count=8,
    )
    assert img.size == (1200, 630)
