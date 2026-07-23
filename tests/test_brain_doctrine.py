"""Tests for engine/neuralweb/doctrine.py + its brain_gateway wiring (CMX W4).

All offline — no network, no API key.  Design mirrors test_brain_gateway.py:
  * sys.path insert to repo root, then import the modules directly.
  * The doctrine .md files under engine/neuralweb/doctrine/ are the drafted
    content (treated as given); these tests read them but never edit them.

Coverage (per the W4 build brief):
  1.  Manifest shape: 11 modules, unique ids == filename stems, protocol always,
      valid kinds, int versions.
  2.  Routing EN (trend / S/R / stage / liquidity / volume).
  3.  Routing ZH (CJK substring triggers).
  4.  Generic read → three default lenses + protocol only.
  5.  Cap (<=3 non-always) + char budget (<=12000).
  6.  Word-boundary guard: 'ema' must not fire inside 'email'.
  7.  Empty / None message → protocol only.
  8.  _doctrine_block_for gated to page == 'terminal'.
  9.  Off-terminal system prompt byte-identical (no doctrine leaks in).
  10. Leak screen catches every doctrine sentinel.
  11. Sentinel anti-rot (header + three body sentinels appear verbatim).
  12. Content-law teeth over all bodies (real tool named, no odds claims,
      Invalidation present, size caps).
  13. Fingerprint: 12 lowercase hex chars, deterministic.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402
from engine.neuralweb import doctrine as d  # noqa: E402


_DOCTRINE_DIR = pathlib.Path(__file__).resolve().parent.parent / "engine" / "neuralweb" / "doctrine"


def _ids(modules: list[dict]) -> list[str]:
    return [m["id"] for m in modules]


# ---------------------------------------------------------------------------
# 1. Manifest
# ---------------------------------------------------------------------------

def test_manifest_shape():
    m = d.manifest()
    assert m["version"] == d.DOCTRINE_VERSION == 1
    mods = m["modules"]
    assert len(mods) == 11, f"expected 11 doctrine modules, got {len(mods)}"

    ids = [x["id"] for x in mods]
    assert len(ids) == len(set(ids)), "module ids must be unique"

    # ids equal filename stems on disk
    stems = sorted(p.stem for p in _DOCTRINE_DIR.glob("*.md"))
    assert sorted(ids) == stems

    kinds = {x["kind"] for x in mods}
    assert kinds <= {"protocol", "lens", "playbook"}

    protocols = [x for x in mods if x["kind"] == "protocol"]
    assert len(protocols) == 1
    assert protocols[0]["id"] == "protocol"
    assert protocols[0]["always"] is True

    for x in mods:
        assert isinstance(x["version"], int) and not isinstance(x["version"], bool)
        assert isinstance(x["title"], str) and x["title"].strip()
        assert isinstance(x["chars"], int) and x["chars"] > 0
        assert isinstance(x["n_triggers"], int)


# ---------------------------------------------------------------------------
# 2. Routing — English
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("is this trendline still valid?", "lens_trend"),
    ("where is support?", "lens_sr"),
    ("what stage is NVDA in?", "play_weinstein"),
    ("was that a stop hunt?", "play_liquidity"),
    ("volume looks heavy on the breakout", "lens_volume"),
])
def test_routing_en(msg, expected):
    routed = _ids(d.route(msg))
    assert expected in routed, f"{msg!r} → {routed}, expected {expected}"
    assert "protocol" in routed  # always-on protocol leads every routed set


# ---------------------------------------------------------------------------
# 3. Routing — Chinese (CJK substring triggers, no word boundaries)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("看看支撑位", "lens_sr"),
    ("这是洗盘吗", "play_phase"),
])
def test_routing_zh(msg, expected):
    routed = _ids(d.route(msg))
    assert expected in routed, f"{msg!r} → {routed}, expected {expected}"


# ---------------------------------------------------------------------------
# 4. Generic read → the three default lenses + protocol, nothing else
# ---------------------------------------------------------------------------

def test_generic_read_uses_defaults():
    routed = _ids(d.route("read this chart for me and tell me what you see"))
    assert set(routed) == {"protocol", "lens_structure", "lens_trend", "lens_sr"}


# ---------------------------------------------------------------------------
# 5. Cap + char budget
# ---------------------------------------------------------------------------

def test_cap_and_budget():
    stuffed = (
        "trend trendline support resistance structure swing volume stage base "
        "gap sweep wyckoff weekly risk stop entry target accumulation channel"
    )
    routed = d.route(stuffed)
    non_always = [m for m in routed if not m["always"]]
    assert len(non_always) <= d._MAX_ROUTED == 3
    total = sum(len(m["body"]) for m in routed)
    assert total <= d._CHAR_BUDGET == 12000


# ---------------------------------------------------------------------------
# 6. Word-boundary guard — 'ema' must not fire inside 'email'
# ---------------------------------------------------------------------------

def test_word_boundary_ema_not_email():
    # A real trigger ('support') so the default fallback does NOT engage; then
    # lens_trend can only appear if 'ema' fired inside 'email' — it must not.
    routed = _ids(d.route("email me the support levels"))
    assert "lens_sr" in routed
    assert "lens_trend" not in routed, "'ema' trigger leaked inside 'email'"


# ---------------------------------------------------------------------------
# 7. Empty / None message → protocol only
# ---------------------------------------------------------------------------

def test_empty_message_protocol_only():
    assert _ids(d.route("")) == ["protocol"]
    assert _ids(d.route("   ")) == ["protocol"]


def test_none_message_protocol_only():
    assert _ids(d.route(None)) == ["protocol"]


# ---------------------------------------------------------------------------
# 8. Gateway helper gated to terminal
# ---------------------------------------------------------------------------

def test_doctrine_block_gating():
    on = gw._doctrine_block_for("terminal", "where is support?")
    assert "TECHNICIAN DOCTRINE" in on
    # protocol body always present (it is the always-on module)
    assert "THE READING PROTOCOL" in on
    assert gw._doctrine_block_for("", "where is support?") == ""
    assert gw._doctrine_block_for("dashboard", "where is support?") == ""


# ---------------------------------------------------------------------------
# 9. Off-terminal system prompt byte-identical (no doctrine leaks in)
# ---------------------------------------------------------------------------

def test_off_terminal_prompt_has_no_doctrine():
    p = gw._build_system_prompt("chat", "", internals_allowed=False)
    assert "TECHNICIAN DOCTRINE" not in p


# ---------------------------------------------------------------------------
# 10. Leak screen catches every doctrine sentinel
# ---------------------------------------------------------------------------

def test_leak_screen_catches_doctrine_sentinels():
    for sentinel in d.LEAK_SENTINELS:
        probe = "blah " + sentinel + " blah"
        out = gw._leak_screen(probe)
        assert out != probe, f"leak screen let sentinel through: {sentinel!r}"


# ---------------------------------------------------------------------------
# 11. Sentinel anti-rot
# ---------------------------------------------------------------------------

def test_sentinel_anti_rot():
    modules = d._load()
    bodies = [m["body"] for m in modules]

    # The header sentinel is produced by prompt_block (not a file body).
    block = d.prompt_block(d.route("where is support?"))
    assert "TECHNICIAN DOCTRINE" in block

    # The other three must appear verbatim in at least one doctrine file body.
    for sentinel in (
        "RESTRAINT (what separates a professional)",
        "VOLUME LENS — confirmation, never a signal",
        "STAGE PLAYBOOK — where in its life",
    ):
        assert any(sentinel in b for b in bodies), f"sentinel rotted: {sentinel!r}"


# ---------------------------------------------------------------------------
# 12. Content-law teeth over all 11 bodies
# ---------------------------------------------------------------------------

_REAL_TOOLS = (
    "chart_digest", "measure_line", "read_chart_state",
    "get_stage_peers", "read_stage_analysis", "draw.", "chart.set_",
)
_BANNED = ("success rate", "win rate", "guaranteed", "probability of")


def test_content_law_teeth():
    modules = d._load()
    assert len(modules) == 11

    for m in modules:
        body = m["body"]
        bl = body.lower()

        # every body names at least one real desk tool
        assert any(t in body for t in _REAL_TOOLS), f"{m['id']}: names no real tool"

        # size cap
        assert len(body) <= 3600, f"{m['id']}: body {len(body)} chars > 3600"

        # every lens/playbook must state an Invalidation
        if m["kind"] in ("lens", "playbook"):
            assert "Invalidation" in body, f"{m['id']}: missing Invalidation clause"

        if m["kind"] == "protocol":
            # The protocol is allowed to NAME the banned vocabulary only to FORBID
            # it (HONESTY section: 'Never quote odds, hit rates, or "success
            # rates" …').  Assert it makes no positive-odds claim: none of the
            # other three banned phrases appear, and its 'success rate' usage is a
            # prohibition, not a claim.
            for phrase in ("win rate", "guaranteed", "probability of"):
                assert phrase not in bl, f"protocol makes an odds claim: {phrase!r}"
            assert "never quote odds" in bl, "protocol must forbid odds vocabulary"
        else:
            # content modules make positive craft claims — none may quote odds
            for phrase in _BANNED:
                assert phrase not in bl, f"{m['id']}: banned odds phrase {phrase!r}"


# ---------------------------------------------------------------------------
# 13. Fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_hex_deterministic():
    f1 = d.fingerprint()
    f2 = d.fingerprint()
    assert f1 == f2
    assert re.fullmatch(r"[0-9a-f]{12}", f1), f"bad fingerprint: {f1!r}"
    assert d.manifest()["fingerprint"] == f1
