"""Render tests for templates/winner_health.html.j2 + the page builder.

Two jobs. First, spec §8.7: the template must render — without raising — against
the full board, the three honest-null modes, and four degenerate rows (no analog,
a thin analog, a 2-point spark, an episode high above every visible close).
Second, spec §9: the four traps found while designing the surface are pinned here
as REGRESSIONS, because each one shipped a page that looked fine from the console.

Everything runs on tiny in-memory fixtures — no data store, no network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import build_winner_health_page as bwh  # noqa: E402

#: Word-boundary patterns, matched against VISIBLE TEXT only. Substring matching
#: over raw HTML reads CSS comments and class names and fails on "reserved for
#: short labels" — a banned-word gate has to scan what a reader can actually see.
BANNED = (r"validated", r"falsifi\w*", r"refut\w*", r"证伪", r"\bsell\b", r"\bshort\b",
          r"\btrim\b", r"\bexit\b", r"\bprereg\w*", r"\bgauntlet\b", r"\bTOPA\b",
          r"\bAUC\b", r"\bprobabilit\w*", r"\bhazard\b")


def _visible_text(html: str, own_copy: bool = False) -> str:
    """What a reader can see: no <style>, no <script>, no comments, no markup.

    `own_copy=True` slices to `.wrap`, this page's own content. The shared product
    header is a different surface with its own vocabulary law (it carries e.g.
    "short ratio" for the Dark Pool desk), and a page-copy gate that reads the nav
    is testing somebody else's copy.
    """
    if own_copy:
        i = html.find('<div class="wrap">')
        assert i > 0, "page wrap not found"
        html = html[i:]
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _leg(key="updown_volume"):
    return {"key": key,
            "words_en": "selling days now heavier", "words_zh": "下跌日成交更重",
            "tip_en": "Down-day volume has outweighed up-day volume in 12 of the last 21 sessions.",
            "tip_zh": "最近 21 个交易日中，有 12 天的下跌日成交量超过了上涨日。"}


def _row(ticker="NVDA", r126=0.62, legs=None, analog="full", spark=None,
         episode_high=142.87):
    if analog == "full":
        ag = {"n": 41, "topped_63td": 14, "median_further_gain": 0.11,
              "median_drop_from_high": -0.24, "track": "W"}
    elif analog == "thin":
        ag = {"n": 5, "topped_63td": 2, "median_further_gain": None,
              "median_drop_from_high": None, "track": "D"}
    else:
        ag = None
    return {
        "ticker": ticker, "name": "NVIDIA", "name_zh": None,
        "href": f"/stocks/{ticker}.html", "r126": r126, "r21": 0.08,
        "days_in_episode": 88, "state": "extended_watch",
        "spark": spark if spark is not None else [100 + i * 0.4 for i in range(63)],
        "episode_high": episode_high,
        "legs": legs if legs is not None else [_leg()],
        "analog": ag,
    }


def _ctx(states=None, **kw):
    base = {
        "schema": "winner_health.v1", "asof": "2026-08-10",
        "data_last_day": "2026-08-08", "universe_n": 1506, "extended_n": 0,
        "null_state": False,
        "macro_backdrop": {"froth_quadrant": "narrowing_top", "stage3_count": 37},
        "library": {"track": "W", "window_start": "2021-07", "window_end": "2026-08",
                    "horizon_td": 63, "drawdown_pct": 20},
        "states": {"extended_healthy": [], "extended_watch": [], "thinning": [],
                   "breaking": []},
        "theme_counts": [{"basket": "AI Semiconductors", "basket_zh": "人工智能半导体",
                          "extended": 19, "watch": 4, "thinning": 2, "breaking": 1}],
    }
    if states:
        base["states"].update(states)
    base["extended_n"] = sum(len(v) for v in base["states"].values())
    base.update(kw)
    return base


def _render(tmp_path, ctx):
    """Render through the real builder, via its fixture path."""
    if ctx is None:
        return bwh.render(REPO, fixture=tmp_path / "does_not_exist.json")
    p = tmp_path / "wh.json"
    p.write_text(json.dumps(ctx, ensure_ascii=False))
    return bwh.render(REPO, fixture=p)


# ══════════════════════════════════════════════════════════════════════════════
# spec §8.7 — the eight required renders
# ══════════════════════════════════════════════════════════════════════════════
def test_full_board_renders(tmp_path):
    ctx = _ctx({
        "extended_healthy": [_row("AVGO", 0.54, legs=[]), _row("MSFT", 0.51, legs=[])],
        "extended_watch": [_row("MU", 0.71)],
        "thinning": [_row("SMCI", 0.44, legs=[_leg("rs_peak_lag"), _leg("rs_decel"),
                                              _leg("vol_asymmetry")])],
        "breaking": [_row("APP", 0.33, legs=[_leg("below_50d"),
                                             _leg("drawdown_from_high")])],
    })
    html = _render(tmp_path, ctx)
    assert "Winner Health" in html
    assert "Still running" in html and "Character changed" in html
    for tk in ("AVGO", "MSFT", "MU", "SMCI", "APP"):
        assert tk in html


def test_clear_mode_renders_the_signature(tmp_path):
    """Names extended, nothing maturing -> the page-scale high-water picture."""
    html = _render(tmp_path, _ctx({"extended_healthy": [_row("AVGO", 0.54, legs=[])]}))
    assert "Nothing is maturing tonight" in html
    assert "flatline" in html
    assert "Still running" in html          # the group still renders below


def test_none_mode_renders(tmp_path):
    html = _render(tmp_path, _ctx())
    assert "No US name is extended right now" in html
    assert "1,506" in html                   # universe_n, thousands-separated


def test_warm_mode_renders_when_artifact_absent(tmp_path):
    html = _render(tmp_path, None)
    assert "has not landed yet" in html
    assert "nothing is being withheld" in html.lower()


def test_warm_mode_on_explicit_null_state(tmp_path):
    html = _render(tmp_path, _ctx(null_state=True, null_reason="store unreadable"))
    assert "has not landed yet" in html
    assert "store unreadable" not in html    # the reason is diagnostics, never copy


def test_row_without_analog_renders_no_match(tmp_path):
    html = _render(tmp_path, _ctx({"extended_watch": [_row(analog=None)]}))
    assert "no match" in html
    assert "like this" not in html


def test_thin_analog_prints_the_honest_floor_not_a_rate(tmp_path):
    html = _render(tmp_path, _ctx({"extended_watch": [_row(analog="thin")]}))
    assert "too few to read as a pattern" in html
    assert "dropped 20% or more" not in html
    # track D -> the curated-sample disclosure, not the delisting one
    assert "under-represented" in html


def test_two_point_spark_renders_the_no_history_null(tmp_path):
    html = _render(tmp_path, _ctx({"extended_watch": [_row(spark=[101.0, 102.0])]}))
    assert "no history" in html
    assert "<svg class=\"sp\"" not in html


def test_episode_high_above_every_visible_close(tmp_path):
    """The run's high predates the window: the WHOLE window is underwater."""
    ctx = _ctx({"extended_watch": [_row(spark=[100.0 - i * 0.1 for i in range(63)],
                                        episode_high=400.0)]})
    html = _render(tmp_path, ctx)
    assert "sp-uw" in html                   # the underwater path is drawn
    assert 'd="M0.0,4' in html               # ...and it starts at x=0


# ══════════════════════════════════════════════════════════════════════════════
# spec §9 — the four traps, pinned as regressions
# ══════════════════════════════════════════════════════════════════════════════
def test_trap1_no_lens_block_is_hosted_inside_a_paragraph():
    """`lens()` emits block-level <div>s; a <div> auto-closes an open <p>, which
    un-hides every Tier-2 card. Any element hosting lens() must be a <div>."""
    src = (REPO / "templates" / "winner_health.html.j2").read_text()
    # Jinja comments are not markup — and this template's own trap note contains
    # the literal string "<p>", which is exactly what the scan is hunting for.
    src = re.sub(r"\{#.*?#\}", " ", src, flags=re.S)
    depth = 0
    for m in re.finditer(r"<p\b|</p>|lens\.lens\(", src):
        tok = m.group(0)
        if tok == "</p>":
            depth = max(0, depth - 1)
        elif tok.startswith("<p"):
            depth += 1
        elif depth > 0:
            pytest.fail(f"lens() called inside an open <p> at offset {m.start()}")


def test_trap2_no_interpolated_attribute_fragments():
    """`{{ ' class=\"on\"' if c else '' }}` ships &#34;on&#34; under autoescape."""
    src = (REPO / "templates" / "winner_health.html.j2").read_text()
    bad = re.findall(r"\{\{\s*'[^']*=\s*\\?\"", src)
    assert not bad, f"interpolated attribute fragment(s): {bad}"


def test_trap2_wear_marks_actually_carry_their_class(tmp_path):
    html = _render(tmp_path, _ctx({"extended_watch": [_row()]}))
    assert '<i class="on">' in html
    assert "&#34;on&#34;" not in html


def test_trap3_receipt_items_hold_short_tokens_only(tmp_path):
    """`.lens-receipt .r-i` is nowrap: a sentence-length value is silently clipped.
    The survivorship disclosure belongs in the wrapping note."""
    html = _render(tmp_path, _ctx({"extended_watch": [_row()]}))
    for item in re.findall(r'<span class="r-i">(.*?)</span>\s*(?=<span class="r-i"|</div>)',
                           html, re.S):
        text = re.sub(r"<[^>]+>", "", item).strip()
        assert len(text) <= 60, f"receipt item too long for a nowrap cell: {text!r}"
    assert "later delisted" in html          # ...and the disclosure IS present


def test_trap4_underwater_fill_starts_at_the_high_not_the_left_edge(tmp_path):
    """A fill anchored at x=0 makes every extended name look equally worn."""
    spark = [100.0 + i for i in range(40)] + [140.0 - i * 0.5 for i in range(23)]
    html = _render(tmp_path, _ctx({"extended_watch": [_row(spark=spark,
                                                           episode_high=139.0)]}))
    m = re.search(r'class="sp-uw" d="M([\d.]+),', html)
    assert m, "underwater path missing"
    assert float(m.group(1)) > 0.0, "fill starts at the left edge (trap 4)"


# ══════════════════════════════════════════════════════════════════════════════
# doctrine gates
# ══════════════════════════════════════════════════════════════════════════════
def test_no_banned_vocabulary_on_a_full_board(tmp_path):
    ctx = _ctx({
        "extended_healthy": [_row("AVGO", 0.54, legs=[])],
        "extended_watch": [_row("MU", 0.71)],
        "thinning": [_row("SMCI", 0.44, legs=[_leg("rs_peak_lag"), _leg("rs_decel"),
                                              _leg("vol_asymmetry")])],
        "breaking": [_row("APP", 0.33, legs=[_leg("below_50d")])],
    })
    text = _visible_text(_render(tmp_path, ctx), own_copy=True)
    for pat in BANNED:
        hit = re.search(pat, text, re.I)
        assert not hit, f"banned vocabulary in visible copy: {hit.group(0)!r}"


def test_no_translated_text_in_attributes():
    """CI law (scripts/check_title_i18n.py): no CJK in title=/aria-label=."""
    src = (REPO / "templates" / "winner_health.html.j2").read_text()
    for attr in re.findall(r'(?:title|aria-label)="([^"]*)"', src):
        assert not re.search(r"[一-鿿]", attr), f"CJK in an attribute: {attr!r}"


def test_state_keys_never_reach_the_page(tmp_path):
    """Enum keys may live in an anchor id; they must never be READABLE copy."""
    text = _visible_text(_render(tmp_path, _ctx({"extended_watch": [_row()]})),
                         own_copy=True)
    for key in ("extended_healthy", "extended_watch", "thinning", "breaking",
                "rs_peak_lag", "updown_volume", "drawdown_from_high"):
        assert key not in text, f"raw enum key in visible copy: {key}"


def test_unknown_froth_slug_is_omitted_never_printed_raw(tmp_path):
    html = _render(tmp_path, _ctx({"extended_watch": [_row()]},
                                  macro_backdrop={"froth_quadrant": "brand_new_slug",
                                                  "stage3_count": 12}))
    assert "brand_new_slug" not in html


def _throwaway_root(tmp_path):
    """A repo-shaped root that owns nothing but the templates.

    Writing into the repo's own site/ would leave an untracked page behind on
    every run and dirty the ship gate.
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "templates").symlink_to(REPO / "templates")
    return root


def test_builder_writes_a_page_and_never_raises(tmp_path):
    out = bwh.build(_throwaway_root(tmp_path))
    assert out == tmp_path / "repo" / "site" / "winner_health.html"
    assert out.exists() and out.stat().st_size > 2000
    assert "Has your winner changed character?" in out.read_text()


def test_builder_falls_open_to_the_warm_null_when_the_data_root_is_empty(tmp_path,
                                                                         monkeypatch):
    """No artifact under the data root -> the designed `warm` state, via build().

    `_data_dir` is pinned to its own documented fallback here on purpose. The
    house resolver (`lib.config.data_dir`, mirrored from
    `scripts/build_stage_analysis_page.py`) is anchored to the REPO that imported
    it, not to the root passed in — so a throwaway root still reads the repo's
    real artifact, and asserting the warm null without this seam passes only on a
    checkout that happens never to have run the engine.
    """
    root = _throwaway_root(tmp_path)
    monkeypatch.setattr(bwh, "_data_dir", lambda r: r / "data")
    out = bwh.build(root)
    assert "has not landed yet" in out.read_text()
