"""Tests for engine/neuralweb/analyst_doctrine.py — the Market Analyst doctrine.

All offline — no network, no API key.  Design mirrors test_brain_doctrine.py:
  * sys.path insert to repo root, then import the modules directly.
  * The doctrine .md files under engine/neuralweb/analyst/ are the drafted
    content (treated as given); these tests read them but never edit them.

This suite is deliberately gateway-free: the analyst library ships standalone
(the gateway wiring — block placement, lane dial append, leak-screen extension —
lands with the surface that consumes it), so nothing here imports brain_gateway.

Coverage:
  1.  Manifest shape: 9 modules, unique ids == filename stems, protocol always,
      valid kinds, int versions — and every .md on disk actually parses (none
      silently skipped by the frontmatter validator).
  2.  Routing EN (rates / regime / cross-asset / catalyst / forward / stress /
      tape / portfolio).
  3.  Routing ZH (CJK substring triggers).
  4.  Generic read → the single default lens + protocol only.
  5.  Word-boundary guard: 'fed' must not fire inside 'federal'.
  6.  Empty / None message → protocol alone.
  7.  Cap (<=3 non-always) + char budget (<=12000), and the drop order (lowest
      rank first, always-modules never dropped).
  8.  prompt_block: header, protocol body first, titled separators, empty → "".
  9.  Leak sentinels: header sentinel in the block, body sentinels verbatim in
      the files, and the header never inside a body.
  10. lane_dial: fast / pro+research / unknown.
  11. Fingerprint: 12 lowercase hex chars, deterministic.
  12. Epistemics: no invented odds/probability claims in any body.
  13. The technician library is unaffected — both import, distinct fingerprints,
      distinct headers, no sentinel bleed either way.
  14. Fail-soft: a missing directory is an empty library, never an exception.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import analyst_doctrine as a  # noqa: E402
from engine.neuralweb import doctrine as tech  # noqa: E402


_ANALYST_DIR = pathlib.Path(__file__).resolve().parent.parent / "engine" / "neuralweb" / "analyst"


def _ids(modules: list[dict]) -> list[str]:
    return [m["id"] for m in modules]


# ---------------------------------------------------------------------------
# 1. Manifest + frontmatter validity of all 9 real files
# ---------------------------------------------------------------------------

def test_manifest_shape():
    m = a.manifest()
    assert m["version"] == a.ANALYST_DOCTRINE_VERSION == 1
    mods = m["modules"]
    assert len(mods) == 9, f"expected 9 analyst doctrine modules, got {len(mods)}"

    ids = [x["id"] for x in mods]
    assert len(ids) == len(set(ids)), "module ids must be unique"

    # ids equal filename stems on disk — i.e. every file parsed, none skipped
    stems = sorted(p.stem for p in _ANALYST_DIR.glob("*.md"))
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


def test_every_file_on_disk_parses():
    """A malformed module is skipped with a warning, not a crash — which would
    silently shrink the library.  Pin file count == loaded count."""
    on_disk = sorted(p.name for p in _ANALYST_DIR.glob("*.md"))
    assert len(on_disk) == 9, f"expected 9 .md files, found {on_disk}"
    loaded = a._load()
    assert len(loaded) == 9, f"{len(loaded)} of {len(on_disk)} files parsed"

    for m in loaded:
        # every lens/playbook carries triggers; the always-on protocol needs none
        if m["kind"] == "protocol":
            assert m["always"] is True
        else:
            assert m["triggers"], f"{m['id']}: no triggers — unroutable"
            assert m["always"] is False


# ---------------------------------------------------------------------------
# 2. Routing — English
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("why is TLT down today", ["lens_rates_curve", "lens_catalyst"]),
    ("why is the market selling off", ["lens_regime"]),
    ("what does the curve say about the fed", ["lens_rates_curve"]),
    ("gold and the dollar are both up", ["lens_cross_asset"]),
    ("what happened just now", ["lens_catalyst"]),
    ("will oil keep going next week", ["lens_projection"]),
    ("bonds and stocks both down, nowhere to hide", ["play_stress_day"]),
    ("here is the data from my screen", ["play_tape_reading"]),
    ("my portfolio", ["play_portfolio"]),
    ("should I buy more or hedge", ["play_portfolio"]),
])
def test_routing_en(msg, expected):
    routed = _ids(a.route(msg))
    for want in expected:
        assert want in routed, f"{msg!r} → {routed}, expected {want}"
    assert "protocol" in routed  # always-on protocol leads every routed set


# ---------------------------------------------------------------------------
# 3. Routing — Chinese (CJK substring triggers, no word boundaries)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("看这些数据 都在跌", ["play_tape_reading", "play_stress_day"]),
    ("为什么美元和黄金一起涨", ["lens_cross_asset", "lens_catalyst"]),
    ("股债双杀 无处可藏", ["play_stress_day"]),
    ("美联储会降息吗", ["lens_rates_curve"]),
    ("我的持仓要不要对冲", ["play_portfolio"]),
    ("后市展望怎么看", ["lens_projection"]),
    ("今天大跌是怎么回事", ["lens_regime"]),
])
def test_routing_zh(msg, expected):
    routed = _ids(a.route(msg))
    for want in expected:
        assert want in routed, f"{msg!r} → {routed}, expected {want}"


# ---------------------------------------------------------------------------
# 4. Generic read → the default lens + protocol, nothing else
# ---------------------------------------------------------------------------

def test_generic_read_uses_defaults():
    routed = _ids(a.route("read the market for me please"))
    assert set(routed) == {"protocol", "lens_regime"}


# ---------------------------------------------------------------------------
# 5. Word-boundary guard — short ASCII triggers must not fire inside a word
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,forbidden", [
    # 'my portfolio' is a real trigger so the default fallback does NOT engage;
    # then the named module can only appear if a short trigger leaked in a word.
    ("my portfolio in a federal shutdown", "lens_rates_curve"),   # 'fed' in 'federal'
    ("my portfolio stopped out here", "lens_projection"),         # 'top' in 'stopped'
])
def test_word_boundary_guard(msg, forbidden):
    routed = _ids(a.route(msg))
    assert "play_portfolio" in routed
    assert forbidden not in routed, f"short trigger leaked inside a word → {routed}"


# ---------------------------------------------------------------------------
# 6. Empty / None message → protocol alone
# ---------------------------------------------------------------------------

def test_empty_message_protocol_only():
    assert _ids(a.route("")) == ["protocol"]
    assert _ids(a.route("   ")) == ["protocol"]


def test_none_message_protocol_only():
    assert _ids(a.route(None)) == ["protocol"]


# ---------------------------------------------------------------------------
# 7. Cap + char budget (+ drop order)
# ---------------------------------------------------------------------------

_STUFFED = (
    "regime risk-off selloff yields TLT curve fed oil gold dollar VIX credit "
    "today why is breaking outlook target next week everything down 60/40 "
    "nowhere to hide screenshot watchlist my portfolio hedge these numbers"
)


def test_cap_and_budget():
    routed = a.route(_STUFFED)
    non_always = [m for m in routed if not m["always"]]
    assert len(non_always) <= a._MAX_ROUTED == 3
    total = sum(len(m["body"]) for m in routed)
    assert total <= a._CHAR_BUDGET == 12000

    # header (205) + at most 3 titled separators fit inside a 500-char overhead
    assert len(a.prompt_block(routed)) <= a._CHAR_BUDGET + 500


def test_budget_drops_lowest_rank_first():
    """_apply_budget trims from the tail (the lowest-ranked routed module) and
    never drops an always-module — pinned on synthetic bodies so the assertion
    does not move when the drafted text is edited."""
    def mod(mid, chars, always=False):
        return {"id": mid, "always": always, "body": "x" * chars}

    always = [mod("protocol", 4000, always=True)]
    routed = [mod("first", 5000), mod("second", 5000), mod("third", 5000)]

    # 4000 + 5000 * 3 = 19000 → drops 'third' (14000) then 'second' (9000)
    kept = a._apply_budget(always, routed)
    assert _ids(kept) == ["protocol", "first"]

    # a lone always-module over budget is still never dropped
    assert _ids(a._apply_budget([mod("protocol", 99000, always=True)], [])) == ["protocol"]

    # under budget → nothing is dropped, order preserved
    small = [mod("first", 100), mod("second", 100), mod("third", 100)]
    assert _ids(a._apply_budget(always, small)) == ["protocol", "first", "second", "third"]


# ---------------------------------------------------------------------------
# 8. Prompt assembly
# ---------------------------------------------------------------------------

def test_prompt_block_shape():
    assert a.prompt_block([]) == ""

    routed = a.route("why is TLT down today")
    block = a.prompt_block(routed)

    protocol = [m for m in routed if m["kind"] == "protocol"]
    assert len(protocol) == 1
    # header first, protocol body directly after it (no separator for the protocol)
    assert block.startswith(a._PROMPT_HEADER + protocol[0]["body"])
    assert "--- " + protocol[0]["title"].upper() + " ---" not in block

    # every other module gets its titled separator and its body, in routed order
    others = [m for m in routed if m["kind"] != "protocol"]
    assert others, "expected at least one routed lens for this message"
    cursor = len(a._PROMPT_HEADER) + len(protocol[0]["body"])
    for m in others:
        chunk = "\n\n--- " + m["title"].upper() + " ---\n\n" + m["body"]
        assert block[cursor:cursor + len(chunk)] == chunk, f"{m['id']}: bad separator/body"
        cursor += len(chunk)
    assert cursor == len(block), "block carries content beyond the routed modules"


# ---------------------------------------------------------------------------
# 9. Leak sentinels — anti-rot
# ---------------------------------------------------------------------------

def test_leak_sentinels_present():
    bodies = [m["body"] for m in a._load()]
    assert len(a.LEAK_SENTINELS) == 5

    # The first sentinel is produced by prompt_block (the header), not a file body.
    block = a.prompt_block(a.route("why is TLT down today"))
    assert "MARKET ANALYST DOCTRINE" in block

    # The rest must appear verbatim in at least one installed .md body.
    for sentinel in a.LEAK_SENTINELS[1:]:
        assert any(sentinel in b for b in bodies), f"sentinel rotted: {sentinel!r}"

    # Every sentinel is reachable from the assembled prompt of SOME message.
    for sentinel, msg in (
        ("THE ANALYST PROTOCOL", ""),
        ("REGIME LENS — the pattern across assets", "why is the market selling off"),
        ("STRESS-DAY PLAYBOOK — when everything is red", "bonds and stocks both down"),
        ("CATALYST LENS — infer the regime from prices first", "what happened just now"),
    ):
        assert sentinel in a.prompt_block(a.route(msg)), f"unreachable sentinel: {sentinel!r}"


def test_header_never_inside_a_body():
    """The never-reveal header is assembled, never authored into a module — a body
    that carried it would survive a doctrine edit that dropped the header."""
    for m in a._load():
        assert a._PROMPT_HEADER not in m["body"], f"{m['id']}: header text in body"
        assert "internal investigation guide" not in m["body"], f"{m['id']}: header phrase in body"


# ---------------------------------------------------------------------------
# 10. Lane dial
# ---------------------------------------------------------------------------

def test_lane_dial():
    fast = a.lane_dial("fast")
    deep = a.lane_dial("pro")
    assert fast.startswith("DISCIPLINE FOR THIS TURN:")
    assert "keep tool spend tight" in fast
    assert deep.startswith("DEPTH FOR THIS TURN:")
    assert "room to go deeper" in deep
    assert fast != deep

    # research mode forces the pro lane upstream → same dial
    assert a.lane_dial("research") == deep

    # unknown / empty / junk → no dial, never an exception
    for lane in ("", "   ", "bogus", "FAST-ish", None, 7, [], {}):
        assert a.lane_dial(lane) == "", f"unexpected dial for {lane!r}"

    # case/whitespace tolerant on the known lanes
    assert a.lane_dial(" Fast ") == fast
    assert a.lane_dial("PRO") == deep


# ---------------------------------------------------------------------------
# 11. Fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_hex_deterministic():
    f1 = a.fingerprint()
    f2 = a.fingerprint()
    assert f1 == f2
    assert re.fullmatch(r"[0-9a-f]{12}", f1), f"bad fingerprint: {f1!r}"
    assert a.manifest()["fingerprint"] == f1


# ---------------------------------------------------------------------------
# 12. Epistemics — no invented odds anywhere in the library
# ---------------------------------------------------------------------------

# The house law bans invented probabilities: the desk's calibrated readings carry
# the record, and where there is no reading the answer says so.
_ODDS_RE = re.compile(r"\b\d{1,3}\s?%\s?(chance|probability|odds)\b|\bodds of\b", re.IGNORECASE)


def test_no_invented_odds():
    for m in a._load():
        hit = _ODDS_RE.search(m["body"])
        assert hit is None, f"{m['id']}: odds claim {hit.group(0)!r}"

    # the guard actually fires (anti-rot on the regex itself)
    assert _ODDS_RE.search("there is a 70% chance of a bounce")
    assert _ODDS_RE.search("the odds of a cut are good")


# ---------------------------------------------------------------------------
# 13. The technician library is unaffected
# ---------------------------------------------------------------------------

def test_two_libraries_stay_separate():
    assert a.fingerprint() != tech.fingerprint()
    assert a._PROMPT_HEADER != tech._PROMPT_HEADER
    assert a.ANALYST_DOCTRINE_VERSION == tech.DOCTRINE_VERSION == 1

    # technician still routes its own modules, unchanged by the refactor
    tech_routed = _ids(tech.route("where is support?"))
    assert "protocol" in tech_routed and "lens_sr" in tech_routed
    assert len(tech._load()) == 11
    assert len(a._load()) == 9

    # no id bleed except the shared 'protocol' stem, and no body bleed at all
    a_ids, t_ids = {m["id"] for m in a._load()}, {m["id"] for m in tech._load()}
    assert a_ids & t_ids == {"protocol"}
    a_bodies = {m["id"]: m["body"] for m in a._load()}
    t_bodies = {m["id"]: m["body"] for m in tech._load()}
    assert a_bodies["protocol"] != t_bodies["protocol"]

    # each block carries ONLY its own header, and neither library's sentinels
    # appear in the other's bodies
    a_block = a.prompt_block(a.route("why is TLT down today"))
    t_block = tech.prompt_block(tech.route("where is support?"))
    assert "MARKET ANALYST DOCTRINE" in a_block and "TECHNICIAN DOCTRINE" not in a_block
    assert "TECHNICIAN DOCTRINE" in t_block and "MARKET ANALYST DOCTRINE" not in t_block
    for sentinel in tech.LEAK_SENTINELS:
        assert not any(sentinel in b for b in a_bodies.values()), f"technician sentinel in analyst: {sentinel!r}"
    for sentinel in a.LEAK_SENTINELS:
        assert not any(sentinel in b for b in t_bodies.values()), f"analyst sentinel in technician: {sentinel!r}"


# ---------------------------------------------------------------------------
# 14. Fail-soft — never raises to callers
# ---------------------------------------------------------------------------

def test_fail_soft_missing_dir_and_junk_input(tmp_path):
    assert a._load(tmp_path / "does_not_exist") == []
    assert a._load(tmp_path) == []  # empty dir, no *.md

    for msg in (None, "", "   ", "\x00\x01", "?" * 5000, "🙂🙂🙂"):
        routed = a.route(msg)
        assert isinstance(routed, list)
        assert isinstance(a.prompt_block(routed), str)
