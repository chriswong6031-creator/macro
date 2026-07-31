"""site/gex.js — the IV-rank band must never render through a directional token.

M2 regression (found during PR #4123's adversarial-review round, fixed here).
`IVRANK` (site/gex.js) carried a `cls` of "down" for "Vol rich" and "up" for
"Cheap"/"Very cheap"; BOTH consumers — `ivrCell()` (the board's IV-rank column)
and `moodReadHTML()` (the "IV30" chip on the "The mood — what options cost"
card) — mapped that cls onto var(--down)/var(--up).

site/theme.css swaps exactly that pair under html[data-lang="zh"] (the
red-rises/green-falls convention for the Chinese audience), so the SAME
non-directional reading rendered red in EN and green in ZH — a visible i18n
colour inversion, not a cosmetic nit.

IV rank is "how expensive are options right now", not which way price leans; it
is not one of the two sanctioned direction instruments (tape_flow, ΔOI). The fix
moves the colour ONTO the band (`col:`) in the direction-neutral family
theme.css documents as un-flipped, leaving no cls for a consumer to re-map.
Mirrors IVR_BAND in templates/options.html.j2.

What these pins protect:
  · the band map itself carries no directional token, and still says all five words
  · EVERY consumer of IVRANK renders from the band's own colour — a third
    reader that re-invents a cls→token ternary fails here (the original bug was
    reported against one consumer while a second carried it identically)
  · at runtime, all five real bands resolve to a non-directional token
  · the tokens the bands DO use are provably not redefined under any
    html[data-lang="zh"] rule in theme.css — the root-cause pin
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GEX_JS = REPO / "site" / "gex.js"
THEME_CSS = REPO / "site" / "theme.css"

BAND_WORDS = ("Vol rich", "Elevated", "Normal", "Cheap", "Very cheap")
BAND_KEYS = ("rich", "elevated", "normal", "cheap", "very_cheap")

_needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not on PATH"
)


@pytest.fixture(scope="module")
def src() -> str:
    return GEX_JS.read_text(encoding="utf-8")


def _block(src: str, opener: str, closer: str) -> str:
    """Slice from `opener` through the first `closer` after it (inclusive)."""
    start = src.index(opener)
    end = src.index(closer, start) + len(closer)
    return src[start:end]


def _ivrank_block(src: str) -> str:
    return _block(src, "var IVRANK = {", "\n  };")


# ─────────────────────────────────────────────────────────────────────────────
# the map
# ─────────────────────────────────────────────────────────────────────────────
def test_iv_rank_band_never_reaches_a_directional_token(src):
    """The band map may not name --up/--down, and must still carry all five
    words (a fix that silently dropped a band would also 'pass' the ban).

    The `col:`-per-band requirement is what keeps the --up/--down ban from
    being VACUOUS here: the pre-fix map stored an indirect `cls: "down"` and
    let each consumer map it to a token, so scanning the map alone for the
    literal "--down" found nothing while the page still rendered inverted.
    Requiring the colour to live ON the band — and banning the cls
    indirection outright — is what actually closes the hole."""
    block = _ivrank_block(src)
    assert "--up" not in block, block
    assert "--down" not in block, block
    assert "cls" not in block, (
        "band carries a cls indirection again — a consumer can map it back "
        f"onto a directional token:\n{block}"
    )
    for word in BAND_WORDS:
        assert word in block, f"missing band word: {word}\n{block}"
    for key in BAND_KEYS:
        assert re.search(rf"\b{key}\s*:", block), f"missing band key: {key}\n{block}"
    # one resolved colour per band, declared on the band itself
    assert len(re.findall(r"\bcol\s*:\s*\"var\(--", block)) == len(BAND_KEYS), (
        f"expected {len(BAND_KEYS)} per-band `col:` declarations\n{block}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# every reader, not just the reported one
# ─────────────────────────────────────────────────────────────────────────────
def test_every_iv_rank_consumer_renders_from_the_band_colour(src):
    """The reported bug named moodReadHTML(), but ivrCell() carried it
    identically. Pin the CLASS of defect: every site that reads IVRANK[...]
    must take the band's own colour and must not re-map onto a token."""
    lines = src.splitlines()
    hits = [i for i, ln in enumerate(lines) if "IVRANK[" in ln]
    assert len(hits) >= 2, f"expected both known consumers, found {len(hits)}"

    for i in hits:
        # the colour is resolved within a couple of lines of the lookup
        window = "\n".join(lines[i:i + 4])
        assert "--up" not in window and "--down" not in window, (
            f"IVRANK consumer at line {i + 1} resolves a directional token:\n{window}"
        )
        assert ".col" in window, (
            f"IVRANK consumer at line {i + 1} does not render from the band's "
            f"own colour:\n{window}"
        )


def test_iv_rank_bands_use_only_direction_neutral_tokens(src):
    """Positive form of the ban: name the family that is allowed, so a future
    edit reaching for some other token has to come back through this test."""
    tokens = set(re.findall(r"var\((--[a-z0-9-]+)\)", _ivrank_block(src)))
    assert tokens, "band map declares no colours at all"
    allowed = {"--warn", "--orange", "--muted", "--info"}
    assert tokens <= allowed, f"non-neutral token(s): {sorted(tokens - allowed)}"


# ─────────────────────────────────────────────────────────────────────────────
# root cause: what theme.css actually flips
# ─────────────────────────────────────────────────────────────────────────────
def test_band_tokens_are_not_redefined_under_the_zh_language_flip(src):
    """The real law. Rather than trusting a hand-kept list of 'directional'
    tokens, read site/theme.css and collect every custom property any
    html[data-lang="zh"] rule redefines — that IS the set whose meaning changes
    with language. No colour an IV-rank band uses may be in it."""
    css = THEME_CSS.read_text(encoding="utf-8")
    flipped: set[str] = set()
    for sel, body in re.findall(r"([^{}]*?)\{([^{}]*)\}", css):
        if 'data-lang="zh"' not in sel:
            continue
        flipped.update(re.findall(r"(--[a-z0-9-]+)\s*:", body))

    # sanity: if this ever comes back empty the scan broke and the test is vacuous
    assert {"--up", "--down"} <= flipped, (
        f"theme.css scan did not find the known zh flip; got {sorted(flipped)}"
    )

    # non-vacuity: an IVRANK block that declares no var() at all would satisfy
    # the disjointness below for free (the pre-fix map did exactly that).
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", _ivrank_block(src)))
    assert used, "band map resolves no colour tokens — this check would be vacuous"

    assert not (used & flipped), (
        f"IV-rank band uses language-flipped token(s): {sorted(used & flipped)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# runtime
# ─────────────────────────────────────────────────────────────────────────────
@_needs_node
def test_iv_rank_cell_colour_is_never_directional_at_runtime(src):
    """Behavioural companion to the static pins: drive the REAL band map through
    the REAL ivrCell() for all five bands and read the colour it actually
    emits into the style attribute."""
    harness = (
        "function lz(en, zh) { return en || ''; }\n"
        "function esc(s) { return String(s); }\n"
        + _ivrank_block(src)
        + "\n"
        + _block(src, "function ivrCell(m) {", "\n  }")
        + "\n"
        "var out = {};\n"
        "['" + "','".join(BAND_KEYS) + "'].forEach(function (b) {\n"
        "  out[b] = ivrCell({ iv_rank_band: b });\n"
        "});\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    res = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=30
    )
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"

    import json

    rendered = json.loads(res.stdout)
    for band in BAND_KEYS:
        html = rendered[band]
        m = re.search(r'style="color:([^;"]+)', html)
        assert m, f"band={band}: no colour rendered — {html!r}"
        colour = m.group(1)
        assert "--up" not in colour and "--down" not in colour, (
            f"band={band}: directional token {colour!r}"
        )
        assert colour != "", f"band={band}: empty colour"
