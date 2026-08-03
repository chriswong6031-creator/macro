"""The IV-rank band must never render through a directional token.

M2 regression (found during PR #4123's adversarial-review round). `IVRANK` (the
old site/gex.js) carried a `cls` of "down" for "Vol rich" and "up" for
"Cheap"/"Very cheap"; BOTH consumers — `ivrCell()` (the board's IV-rank column)
and `moodReadHTML()` (the "IV30" chip) — mapped that cls onto var(--down)/
var(--up).

site/theme.css swaps exactly that pair under html[data-lang="zh"] (the
red-rises/green-falls convention for the Chinese audience), so the SAME
non-directional reading rendered red in EN and green in ZH — a visible i18n
colour inversion, not a cosmetic nit. The fix moves the colour ONTO the band in
the direction-neutral family theme.css documents as un-flipped, leaving no cls
for a consumer to re-map.

WHY THIS FILE NOW READS A TEMPLATE (OIP W1.6-B): site/gex.js is deleted.
gex.html is a redirect stub into the Options workspace, so nothing loads that
file any more — and a test pinning a deleted file is a test about nothing. The
map SURVIVED the move: `IVR_BAND` in templates/options.html.j2 is the workspace's
own copy, carrying the same five bands with the same words. The law it is held
to is unchanged, so it moves here rather than retiring with the file.

What these pins protect:
  · the band map itself carries no directional token, and still says all five
    words in BOTH languages
  · EVERY consumer of IVR_BAND renders from the band's own colour — a second
    reader that re-invents a band->token ternary fails here (the original bug was
    reported against one consumer while a second carried it identically)
  · at runtime, all five real bands resolve to a non-directional token
  · the tokens the bands DO use are provably not redefined under any
    html[data-lang="zh"] rule — the root-cause pin, now scanned across BOTH
    site/theme.css and the workspace page's own <style>, because the band
    reaches for a token (--oew-accent) that the page itself defines
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKSPACE = REPO / "templates" / "options.html.j2"
THEME_CSS = REPO / "site" / "theme.css"

BAND_WORDS = ("Vol rich", "Elevated", "Normal", "Cheap", "Very cheap")
BAND_WORDS_ZH = ("波动偏贵", "偏高", "正常", "偏低", "便宜")
BAND_KEYS = ("rich", "elevated", "normal", "cheap", "very_cheap")

_needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not on PATH"
)


@pytest.fixture(scope="module")
def src() -> str:
    return WORKSPACE.read_text(encoding="utf-8")


def _block(src: str, opener: str, closer: str) -> str:
    """Slice from `opener` through the first `closer` after it (inclusive)."""
    start = src.index(opener)
    end = src.index(closer, start) + len(closer)
    return src[start:end]


def _ivrank_block(src: str) -> str:
    return _block(src, "var IVR_BAND = {", "\n};")


def test_the_map_did_not_move_or_vanish(src):
    """Guard the guard. This suite followed the map from a deleted file into a
    template; if it moves again, everything below would slice an empty string
    and pass. `_ivrank_block` raising is the intended failure — this names it."""
    assert "var IVR_BAND = {" in src, (
        "IVR_BAND is no longer in templates/options.html.j2 — find where the "
        "IV-rank band map lives now and repoint this file, do not delete it"
    )


# ─────────────────────────────────────────────────────────────────────────────
# the map
# ─────────────────────────────────────────────────────────────────────────────
def test_iv_rank_band_never_reaches_a_directional_token(src):
    """The band map may not name --up/--down, and must still carry all five
    words (a fix that silently dropped a band would also 'pass' the ban).

    The colour-per-band requirement is what keeps the --up/--down ban from being
    VACUOUS: the pre-fix map stored an indirect `cls: "down"` and let each
    consumer map it to a token, so scanning the map alone for the literal
    "--down" found nothing while the page still rendered inverted. Requiring the
    colour to live ON the band — and banning the cls indirection outright — is
    what actually closes the hole."""
    block = _ivrank_block(src)
    assert "--up" not in block, block
    assert "--down" not in block, block
    assert "cls" not in block, (
        "band carries a cls indirection again — a consumer can map it back "
        f"onto a directional token:\n{block}"
    )
    for word in BAND_WORDS:
        assert word in block, f"missing band word: {word}\n{block}"
    for word in BAND_WORDS_ZH:
        assert word in block, f"missing ZH band word: {word}\n{block}"
    for key in BAND_KEYS:
        assert re.search(rf"\b{key}\s*:", block), f"missing band key: {key}\n{block}"
    # one resolved colour per band, declared on the band itself
    assert len(re.findall(r"var\(--", block)) == len(BAND_KEYS), (
        f"expected {len(BAND_KEYS)} per-band colour declarations\n{block}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# every reader, not just the reported one
# ─────────────────────────────────────────────────────────────────────────────
def test_every_iv_rank_consumer_renders_from_the_band_colour(src):
    """The reported bug named one consumer while a second carried it
    identically. Pin the CLASS of defect: every site that reads IVR_BAND[...]
    must take the band's own colour and must not re-map onto a token."""
    lines = src.splitlines()
    hits = [i for i, ln in enumerate(lines) if "IVR_BAND[" in ln]
    assert hits, "no IVR_BAND consumer found — this check would be vacuous"

    for i in hits:
        # the colour is resolved within a few lines of the lookup
        window = "\n".join(lines[i:i + 6])
        assert "--up" not in window and "--down" not in window, (
            f"IVR_BAND consumer at line {i + 1} resolves a directional token:\n{window}"
        )
        assert re.search(r"\bband\[2\]", window), (
            f"IVR_BAND consumer at line {i + 1} does not render from the band's "
            f"own colour (band[2]):\n{window}"
        )


def test_iv_rank_bands_use_only_direction_neutral_tokens(src):
    """Positive form of the ban: name the family that is allowed, so a future
    edit reaching for some other token has to come back through this test."""
    tokens = set(re.findall(r"var\((--[a-z0-9-]+)\)", _ivrank_block(src)))
    assert tokens, "band map declares no colours at all"
    allowed = {"--warn", "--orange", "--muted", "--info", "--oew-accent"}
    assert tokens <= allowed, f"non-neutral token(s): {sorted(tokens - allowed)}"


# ─────────────────────────────────────────────────────────────────────────────
# root cause: what actually flips with language
# ─────────────────────────────────────────────────────────────────────────────
def _language_flipped_properties(css: str) -> set[str]:
    """Every custom property any html[data-lang="zh"] rule redefines."""
    flipped: set[str] = set()
    for sel, body in re.findall(r"([^{}]*?)\{([^{}]*)\}", css):
        if 'data-lang="zh"' not in sel:
            continue
        flipped.update(re.findall(r"(--[a-z0-9-]+)\s*:", body))
    return flipped


def test_band_tokens_are_not_redefined_under_the_zh_language_flip(src):
    """The real law. Rather than trusting a hand-kept list of 'directional'
    tokens, read the stylesheets and collect every custom property any
    html[data-lang="zh"] rule redefines — that IS the set whose meaning changes
    with language. No colour an IV-rank band uses may be in it.

    Both sheets are scanned: site/theme.css owns --up/--down, and the workspace
    page's own <style> owns --oew-accent, which this map now uses. Scanning only
    theme.css would be green about a token it never sees."""
    flipped = _language_flipped_properties(THEME_CSS.read_text(encoding="utf-8"))
    flipped |= _language_flipped_properties(src)

    # sanity: if this ever comes back empty the scan broke and the test is vacuous
    assert {"--up", "--down"} <= flipped, (
        f"stylesheet scan did not find the known zh flip; got {sorted(flipped)}"
    )

    # non-vacuity: a band map that declared no var() at all would satisfy the
    # disjointness below for free (the pre-fix map did exactly that).
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", _ivrank_block(src)))
    assert used, "band map resolves no colour tokens — this check would be vacuous"

    assert not (used & flipped), (
        f"IV-rank band uses language-flipped token(s): {sorted(used & flipped)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# runtime
# ─────────────────────────────────────────────────────────────────────────────
@_needs_node
def test_iv_rank_band_colour_is_never_directional_at_runtime(src):
    """Behavioural companion to the static pins: drive the REAL band map through
    the REAL richOrCheapHTML() for all five bands and read the colour it
    actually emits into the style attribute."""
    harness = (
        _block(src, "function esc(s){", "\n}")
        + "\n"
        + re.search(r"^function bi\(en, zh\).*$", src, re.M).group(0)
        + "\n"
        + re.search(r"^function num\(v\).*$", src, re.M).group(0)
        + "\n"
        + _ivrank_block(src)
        + "\n"
        + _block(src, "function filmOrdinal(n){", "\n}")
        + "\n"
        + _block(src, "function richOrCheapHTML(tk, gx){", "\n}")
        + "\n"
        "var out = {};\n"
        "['" + "','".join(BAND_KEYS) + "'].forEach(function (b) {\n"
        "  out[b] = richOrCheapHTML('NVDA', { summary: { iv_rank: "
        "{ band: b, rank_pct: 50, n_days: 40, low_confidence: false } } });\n"
        "});\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    res = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=30
    )
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"

    rendered = json.loads(res.stdout)
    for band in BAND_KEYS:
        html = rendered[band]
        m = re.search(r'class="oew-rich-band" style="color:([^;"]+)', html)
        assert m, f"band={band}: no colour rendered — {html!r}"
        colour = m.group(1)
        assert "--up" not in colour and "--down" not in colour, (
            f"band={band}: directional token {colour!r}"
        )
        assert colour != "", f"band={band}: empty colour"


@_needs_node
def test_runtime_bands_are_visually_distinguishable(src):
    """Non-vacuity control for the runtime pin: if every band resolved to the
    same colour the ban above would pass while the ladder said nothing. The map
    is a deliberate FOUR-weight ladder over five bands (normal and cheap share
    var(--muted) by design, PR #4123 review round 2), so the assertion is >= 3
    distinct colours, not 5 — a real constraint that a collapse to one still
    fails."""
    harness = (
        _ivrank_block(src)
        + "\nprocess.stdout.write(JSON.stringify(IVR_BAND));\n"
    )
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
    bands = json.loads(res.stdout)
    assert set(bands) == set(BAND_KEYS), f"band keys drifted: {sorted(bands)}"
    colours = {bands[k][2] for k in BAND_KEYS}
    assert len(colours) >= 3, f"the band ladder collapsed to {sorted(colours)}"
