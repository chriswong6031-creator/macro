"""tests/test_marketing_ad_plane_o.py — Ad Central Plane O: owned-inventory split tests.

The thing this file exists to protect: **the browser and the engine must assign
the same visitor to the same arm.** If they drift, visitors are counted in one
arm and shown another — and the test does not go red, it goes *quiet*. Every
number stays plausible while measuring nothing. So parity is pinned three ways,
deliberately overlapping:

  1. `PINNED` vectors asserted in pure Python — cannot be skipped, ever.
  2. the real `templates/adtest.js` executed under node and compared to Python.
  3. a source check on the JS constants, so an edited algorithm is caught even
     on a runner with no node.

If node is missing, (1) and (3) still hold, so the gate degrades rather than
disappearing — a skipped parity test that silently protects nothing is how this
class of bug ships.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.marketing import ad_arena
from engine.marketing.ad_arena import _unit_hash


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
SHIM = ROOT / "templates" / "adtest.js"
SITE_SHIM = ROOT / "site" / "adtest.js"

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

# Generated from the Python implementation and verified against node at authoring
# time. These are the contract: if a change makes one of these move, the change
# invalidates every arena that has already assigned a visitor.
PINNED: dict[tuple[str, str, str], float] = {
    ("hero-1", "u-0", "arm"): 0.8124478161334991,
    ("hero-1", "u-0", "holdout"): 0.1185434884391725,
    ("hero-1", "u-1", "arm"): 0.38484673434868455,
    ("hero-promise-vs-proof", "6f4b2c1e-aaaa", "arm"): 0.23505399003624916,
    ("", "", ""): 0.8859056187793612,
    ("a", "b", ""): 0.9780699382536113,
    ("竞价-中文", "访客-1", "arm"): 0.8909773477353156,      # BMP CJK
    ("hero-🚀", "u-🎯", "arm"): 0.9613627628423274,          # astral: 2 UTF-16 units in JS
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Python side, pinned — never skipped
# ═══════════════════════════════════════════════════════════════════════════

def test_the_hash_is_pinned():
    for (arena_id, unit, salt), expected in PINNED.items():
        assert _unit_hash(arena_id, unit, salt) == expected, (
            f"the assignment hash moved for {(arena_id, unit, salt)!r}. Every arena "
            f"that has already assigned a visitor is invalidated by this change."
        )


def test_the_hash_is_a_uniform_draw():
    values = [_unit_hash("arena", f"u-{i}", "arm") for i in range(20000)]
    assert all(0.0 <= v < 1.0 for v in values)
    # Ten buckets, none more than 15% off its expected share.
    buckets = [0] * 10
    for v in values:
        buckets[min(9, int(v * 10))] += 1
    for i, n in enumerate(buckets):
        assert 1700 < n < 2300, f"bucket {i} got {n} of 20000 — the hash is not uniform"


def test_the_salt_decorrelates_the_two_draws():
    """Without a per-purpose salt, held-out units would all come from one arm's band."""
    same = sum(
        1 for i in range(5000)
        if abs(_unit_hash("a", f"u-{i}", "arm") - _unit_hash("a", f"u-{i}", "holdout")) < 0.01
    )
    assert same < 150, "the arm and holdout draws move together"


def test_astral_characters_count_as_two_units_like_js():
    """Python iterates code points, JS iterates UTF-16 code units. The rocket is one
    Python character and two JS ones; `_utf16_units` is what keeps them agreeing."""
    assert len(ad_arena._utf16_units("🚀")) == 2
    assert len(ad_arena._utf16_units("a")) == 1
    assert len(ad_arena._utf16_units("中")) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. JS side, executed
# ═══════════════════════════════════════════════════════════════════════════

def _node(script: str) -> str:
    out = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, f"node failed:\n{out.stderr}"
    return out.stdout


@needs_node
def test_the_shipped_js_loads_outside_a_browser():
    """It must import cleanly in node or nothing below can check it."""
    got = _node("console.log(Object.keys(require('./templates/adtest.js')).sort().join(','))")
    assert got.strip() == "HOLDOUT,assign,hashUnit"


@needs_node
def test_js_matches_python_on_the_pinned_vectors():
    cases = [list(k) for k in PINNED]
    got = json.loads(_node(
        "const m=require('./templates/adtest.js');"
        f"const c={json.dumps(cases)};"
        "console.log(JSON.stringify(c.map(([a,u,s])=>m.hashUnit(a,u,s))));"
    ))
    for (key, expected), js_value in zip(PINNED.items(), got):
        assert js_value == expected, f"JS and Python disagree on {key!r}"


@needs_node
def test_js_matches_python_across_many_units():
    """A handful of vectors can agree by luck; 600 cannot."""
    units = [f"u-{i}" for i in range(300)] + [f"{i}-访客-🎯" for i in range(300)]
    got = json.loads(_node(
        "const m=require('./templates/adtest.js');"
        f"const u={json.dumps(units)};"
        "console.log(JSON.stringify(u.map(x=>[m.hashUnit('hero-1',x,'arm'),"
        "m.hashUnit('hero-1',x,'holdout')])));"
    ))
    for unit, (js_arm, js_hold) in zip(units, got):
        assert js_arm == _unit_hash("hero-1", unit, "arm"), f"arm draw differs for {unit!r}"
        assert js_hold == _unit_hash("hero-1", unit, "holdout"), f"holdout differs for {unit!r}"


@needs_node
def test_js_assignment_matches_python_assignment():
    """The hash agreeing is not enough — the cumulative walk over arms must too."""
    ids = ["adc-aaa", "adc-bbb", "adc-ccc"]
    arena = ad_arena.create(
        arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
        primary_metric="signup_rate", creative_ids=ids, holdout=0.15,
    )
    cfg = {
        "arena_id": arena.arena_id,
        "holdout": arena.holdout,
        "arms": [{"id": cid, "w": arena.assignment_weights[cid]} for cid in ids],
    }
    units = [f"v-{i}" for i in range(1500)]
    got = json.loads(_node(
        "const m=require('./templates/adtest.js');"
        f"const cfg={json.dumps(cfg)};const u={json.dumps(units)};"
        "console.log(JSON.stringify(u.map(x=>m.assign(cfg,x))));"
    ))
    mismatches = [
        (u, js, ad_arena.assign(arena, u))
        for u, js in zip(units, got)
        if js != ad_arena.assign(arena, u)
    ]
    assert not mismatches, f"{len(mismatches)} assignment mismatches, e.g. {mismatches[:3]}"
    # And the agreed assignment is actually a split, not everyone in one arm.
    assert len(set(got)) == 4                       # three arms + the holdout
    assert got.count(ad_arena.HOLDOUT) > 150


@needs_node
def test_js_weighted_assignment_respects_uneven_weights():
    ids = ["a", "b"]
    arena = ad_arena.create(
        arena_id="w-1", hypothesis="h", plane="owned", unit="visitor",
        primary_metric="m", creative_ids=ids,
    )
    arena.assignment_weights = {"a": 0.8, "b": 0.2}
    cfg = {"arena_id": "w-1", "holdout": 0,
           "arms": [{"id": "a", "w": 0.8}, {"id": "b", "w": 0.2}]}
    units = [f"v-{i}" for i in range(4000)]
    got = json.loads(_node(
        "const m=require('./templates/adtest.js');"
        f"const cfg={json.dumps(cfg)};const u={json.dumps(units)};"
        "console.log(JSON.stringify(u.map(x=>m.assign(cfg,x))));"
    ))
    assert got == [ad_arena.assign(arena, u) for u in units]
    assert 0.76 < got.count("a") / len(got) < 0.84


# ═══════════════════════════════════════════════════════════════════════════
# 3. Source guard — holds even with no node
# ═══════════════════════════════════════════════════════════════════════════

def test_the_js_still_carries_the_agreed_algorithm():
    src = SHIM.read_text(encoding="utf-8")
    for token in ("0x811c9dc5", "0x01000193", "Math.imul", "charCodeAt", "4294967296"):
        assert token in src, f"{token} vanished from adtest.js — the hash was rewritten"
    assert "crypto.subtle" not in src, (
        "Web Crypto is Promise-only; an async hash renders the control first and "
        "swaps, which biases the metric being measured"
    )
    # The two salts must both survive, or holdout and arm draws collapse together.
    assert "'holdout'" in src and "'arm'" in src


def test_the_shim_refuses_to_run_a_shadow_or_planned_arena():
    src = SHIM.read_text(encoding="utf-8")
    assert "cfg.status !== 'running'" in src
    assert "cfg.mode !== 'live'" in src


def _js_code_only(src: str) -> str:
    """Strip comments so a source guard cannot match the prose explaining itself.

    (A guard that reads its own docstring is a guard that passes forever — this
    one did exactly that on the first run.)
    """
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end == -1 else end
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def test_the_shim_does_not_read_the_visitor_cookie():
    """Identity is the SERVER's to stamp. If the shim ever starts sending its own
    idea of who the visitor is, the denominator becomes forgeable."""
    code = _js_code_only(SHIM.read_text(encoding="utf-8"))
    assert "mm_aid" not in code


def test_the_comment_stripper_actually_strips():
    """The guard above is only as good as this — proven, not assumed."""
    assert _js_code_only("var a=1; /* mm_aid */ var b=2;").strip() == "var a=1;  var b=2;"
    assert "mm_aid" not in _js_code_only("// mm_aid\nvar x=1;")
    assert "mm_aid" in _js_code_only("var k='mm_aid';")


def test_template_and_site_copies_are_byte_identical():
    """Plain-copy pairs are a CI-guarded house law; the site copy is what ships."""
    assert SITE_SHIM.exists(), "site/adtest.js is missing — the VPS serves site/, not templates/"
    assert SHIM.read_bytes() == SITE_SHIM.read_bytes()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Behaviour, in a stubbed DOM
# ═══════════════════════════════════════════════════════════════════════════

_HARNESS = r"""
const path = require('path');
const cfg = JSON.parse(process.argv[1] || '{}');
const slots = JSON.parse(process.argv[2] || '[]');
const calls = [];
const els = slots.map(s => ({ _slot: s, textContent: '(original)',
                              getAttribute(k) { return k === 'data-adtest-slot' ? this._slot : null; } }));
global.window = {
  localStorage: (() => { const m = {}; return { getItem: k => m[k] || null,
                                                setItem: (k, v) => { m[k] = String(v); } }; })(),
  crypto: { randomUUID: () => 'FIXED-UNIT-ID' },
  mmTrack: (type, extra) => calls.push([type, extra]),
};
global.document = {
  readyState: 'complete',
  cookie: '',
  getElementById: id => (cfg.__present === false ? null
    : (id === 'mm-adtest' ? { textContent: JSON.stringify(cfg) } : null)),
  querySelectorAll: () => els,
  addEventListener: () => {},
};
global.setTimeout = (fn) => fn();
require(path.join(process.cwd(), 'templates', 'adtest.js'));
console.log(JSON.stringify({ calls, slots: els.map(e => e.textContent),
                             state: global.window.mmAdtest || null }));
"""


def _run_shim(cfg: dict, slots: list[str]) -> dict:
    out = subprocess.run(
        ["node", "-e", _HARNESS, json.dumps(cfg), json.dumps(slots)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, f"node failed:\n{out.stderr}"
    return json.loads(out.stdout)


def _live_cfg(**kw) -> dict:
    base = {
        "arena_id": "hero-1", "status": "running", "mode": "live", "holdout": 0.0,
        "arms": [
            {"id": "adc-a", "w": 0.5, "copy": {"headline": "A headline", "cta": "A cta"}},
            {"id": "adc-b", "w": 0.5, "copy": {"headline": "B headline", "cta": "B cta"}},
        ],
    }
    base.update(kw)
    return base


@needs_node
def test_a_live_arena_rewrites_the_slots_and_reports_the_exposure():
    r = _run_shim(_live_cfg(), ["headline", "cta"])
    assert r["state"] is not None
    chosen = r["state"]["creative"]
    assert chosen in ("adc-a", "adc-b")
    letter = chosen[-1].upper()
    assert r["slots"] == [f"{letter} headline", f"{letter} cta"]
    assert r["calls"] == [["ad_exposure", {"meta": {
        "arena": "hero-1", "creative": chosen, "slots": 2}}]]


@needs_node
def test_the_reported_arm_is_the_arm_python_would_have_picked():
    """The exposure row is the assignment record — it must not disagree with the engine."""
    r = _run_shim(_live_cfg(), ["headline"])
    arena = ad_arena.create(
        arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
        primary_metric="m", creative_ids=["adc-a", "adc-b"],
    )
    assert r["state"]["creative"] == ad_arena.assign(arena, "FIXED-UNIT-ID")


@needs_node
@pytest.mark.parametrize("cfg,why", [
    ({"__present": False}, "no config element on the page"),
    ({"arena_id": "x", "status": "planned", "mode": "live", "arms": [{"id": "a", "w": 1}]},
     "a planned arena is a pre-registration, not an experiment"),
    ({"arena_id": "x", "status": "running", "mode": "shadow", "arms": [{"id": "a", "w": 1}]},
     "shadow mode must never touch a real visitor"),
    ({"arena_id": "x", "status": "running", "mode": "live", "arms": []}, "no arms"),
    ({"status": "running", "mode": "live", "arms": [{"id": "a", "w": 1}]}, "no arena id"),
])
def test_the_shim_is_inert_unless_the_arena_is_running_and_live(cfg, why):
    r = _run_shim(cfg, ["headline"])
    assert r["calls"] == [], f"reported an exposure when {why}"
    assert r["slots"] == ["(original)"], f"rewrote the page when {why}"
    assert r["state"] is None


@needs_node
def test_a_holdout_visitor_keeps_the_original_copy_but_is_still_counted():
    """The holdout is the no-ad baseline. It must be recorded, or the arms are
    compared against nothing and the whole test loses its floor."""
    r = _run_shim(_live_cfg(holdout=1.0), ["headline"])
    assert r["slots"] == ["(original)"]
    assert r["state"]["creative"] == ad_arena.HOLDOUT
    assert r["calls"][0][1]["meta"]["creative"] == ad_arena.HOLDOUT


@needs_node
def test_a_half_specified_variant_falls_back_to_the_authored_copy():
    """A missing slot must leave the HTML alone rather than blanking the hero."""
    cfg = _live_cfg(arms=[
        {"id": "adc-a", "w": 1.0, "copy": {"headline": "only the headline"}},
    ])
    r = _run_shim(cfg, ["headline", "cta"])
    assert r["slots"] == ["only the headline", "(original)"]
    assert r["state"]["slots"] == 1


@needs_node
def test_malformed_config_does_not_throw():
    out = subprocess.run(
        ["node", "-e", _HARNESS.replace("JSON.stringify(cfg)", "'{not json'"),
         json.dumps(_live_cfg()), json.dumps(["headline"])],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, f"a malformed config crashed the page:\n{out.stderr}"
    assert json.loads(out.stdout)["calls"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Nightly ingest — analytics_events → arena ledgers
# ═══════════════════════════════════════════════════════════════════════════

from engine.marketing import ad_ingest  # noqa: E402


def _seed_arena(tmp_path, ids=("adc-a", "adc-b")):
    arena = ad_arena.create(
        arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
        primary_metric="signup_rate", creative_ids=list(ids),
        control_creative_id=ids[0],
    )
    arena.status, arena.mode = "running", "live"
    ad_arena.save_arena(arena, root=tmp_path)
    return arena


def _exposure(visitor, creative, at, arena="hero-1", user_id=None, row_id=""):
    return {"id": row_id or f"{visitor}-{at}", "type": "ad_exposure", "visitor_id": visitor,
            "user_id": user_id, "created_at": at, "meta": {"arena": arena, "creative": creative}}


def _pageview(visitor, at, user_id=None, row_id=""):
    return {"id": row_id or f"pv-{visitor}-{at}", "type": "pageview", "visitor_id": visitor,
            "user_id": user_id, "created_at": at}


def test_ingest_keys_units_on_the_server_stamped_visitor(tmp_path):
    _seed_arena(tmp_path)
    rows = [_exposure("v1", "adc-a", "2026-07-26T10:00:00Z"),
            _exposure("v2", "adc-b", "2026-07-26T10:01:00Z")]
    r = ad_ingest.ingest(rows, root=tmp_path)
    assert r["ok"] and r["assignments"] == 2
    ledger = ad_arena.read_jsonl(tmp_path / ad_arena.DEFAULT_LEDGER_DIR / ad_arena.ASSIGNMENTS_FILE)
    assert {x["unit_key"] for x in ledger} == {"v1", "v2"}


def test_a_client_cannot_invent_an_arm():
    """The browser may pick among the arms; it may not add one."""
    arena = ad_arena.create(arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
                            primary_metric="signup_rate", creative_ids=["adc-a", "adc-b"])
    rows = [_exposure("v1", "adc-a", "t1"),
            _exposure("v2", "adc-EVIL", "t2"),
            _exposure("v3", ad_arena.HOLDOUT, "t3")]
    new, anomalies = ad_ingest.fold_exposures(rows, [arena])
    assert [x["unit_key"] for x in new] == ["v1", "v3"]      # holdout is a legal arm
    assert anomalies["exposure_for_unknown_creative"] == 1


def test_an_exposure_for_an_arena_we_do_not_run_is_dropped():
    arena = ad_arena.create(arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
                            primary_metric="signup_rate", creative_ids=["adc-a"])
    new, anomalies = ad_ingest.fold_exposures(
        [_exposure("v1", "adc-a", "t1", arena="some-other-arena")], [arena])
    assert new == [] and anomalies["exposure_for_unknown_arena"] == 1


def test_the_first_exposure_wins_and_later_ones_are_counted():
    arena = ad_arena.create(arena_id="hero-1", hypothesis="h", plane="owned", unit="visitor",
                            primary_metric="signup_rate", creative_ids=["adc-a", "adc-b"])
    rows = [_exposure("v1", "adc-b", "2026-07-26T11:00:00Z"),
            _exposure("v1", "adc-a", "2026-07-26T10:00:00Z")]     # earlier, out of order
    new, anomalies = ad_ingest.fold_exposures(rows, [arena])
    assert len(new) == 1 and new[0]["creative_id"] == "adc-a"     # sorted by server time
    assert anomalies["duplicate_exposure"] == 1


def test_ingest_is_idempotent(tmp_path):
    _seed_arena(tmp_path)
    rows = [_exposure("v1", "adc-a", "2026-07-26T10:00:00Z"),
            _pageview("v1", "2026-07-26T10:05:00Z", user_id="u-1")]
    first = ad_ingest.ingest(rows, root=tmp_path)
    second = ad_ingest.ingest(rows, root=tmp_path)
    assert first["assignments"] == 1 and first["outcomes"] == 1
    assert second["assignments"] == 0 and second["outcomes"] == 0, "a re-run double-counted"


def test_dry_run_computes_but_writes_nothing(tmp_path):
    _seed_arena(tmp_path)
    rows = [_exposure("v1", "adc-a", "2026-07-26T10:00:00Z")]
    r = ad_ingest.ingest(rows, root=tmp_path, dry_run=True)
    assert r["assignments"] == 1 and r["written_assignments"] == 0
    assert ad_arena.read_jsonl(
        tmp_path / ad_arena.DEFAULT_LEDGER_DIR / ad_arena.ASSIGNMENTS_FILE) == []


def test_a_signup_after_exposure_counts_and_one_before_does_not():
    assignments = [{"arena_id": "hero-1", "unit_key": "v1", "at": "2026-07-26T10:00:00Z"},
                   {"arena_id": "hero-1", "unit_key": "v2", "at": "2026-07-26T10:00:00Z"}]
    rows = [
        _exposure("v1", "adc-a", "2026-07-26T10:00:00Z"),
        _pageview("v1", "2026-07-26T12:00:00Z", user_id="u-1"),        # converted
        _exposure("v2", "adc-b", "2026-07-26T10:00:00Z", user_id="u-2"),  # already had an account
        _pageview("v2", "2026-07-26T12:00:00Z", user_id="u-2"),
    ]
    out, anomalies = ad_ingest.fold_signups(rows, assignments)
    assert [x["unit_key"] for x in out] == ["v1"]
    assert anomalies["already_signed_in_at_exposure"] == 1


def test_a_visitor_exposed_earlier_can_convert_later(tmp_path):
    """Conversions join against the whole assignment history, not just tonight's."""
    _seed_arena(tmp_path)
    ad_ingest.ingest([_exposure("v1", "adc-a", "2026-07-20T10:00:00Z")], root=tmp_path)
    r = ad_ingest.ingest([_pageview("v1", "2026-07-26T10:00:00Z", user_id="u-1")], root=tmp_path)
    assert r["outcomes"] == 1


def test_ingest_feeds_a_readout_end_to_end(tmp_path):
    arena = _seed_arena(tmp_path)
    rows = []
    for i in range(400):
        cid = ad_arena.assign(arena, f"v-{i}")
        rows.append(_exposure(f"v-{i}", cid, f"2026-07-26T10:{i // 60:02d}:{i % 60:02d}Z"))
        if i % (12 if cid == "adc-b" else 25) == 0:
            rows.append(_pageview(f"v-{i}", "2026-07-26T20:00:00Z", user_id=f"u-{i}"))
    r = ad_ingest.ingest(rows, root=tmp_path)
    assert r["ok"] and r["assignments"] == 400

    loaded = ad_arena.load_arenas(root=tmp_path)[0]
    tally = ad_arena.tally_from_ledgers(loaded, root=tmp_path)
    assert sum(a.assigned for a in tally.arms) == 400
    assert not tally.anomalies, tally.anomalies
    read = ad_arena.readout(loaded, tally)
    assert read["verdict"] in ("separated", "null", "seeding")
    assert read["plain"].strip()


def test_ingest_reports_plainly(tmp_path):
    _seed_arena(tmp_path)
    quiet = ad_ingest.ingest([], root=tmp_path)
    assert "No new split-test activity" in quiet["plain"]
    busy = ad_ingest.ingest(
        [_exposure("v1", "adc-a", "t1"), _exposure("v2", "adc-NOPE", "t2")], root=tmp_path)
    assert "Recorded 1 new visitor" in busy["plain"]
    assert "unknown creative" in busy["plain"]


def test_ingest_never_raises_on_junk(tmp_path):
    _seed_arena(tmp_path)
    r = ad_ingest.ingest(
        [{"type": "ad_exposure"}, {"type": "ad_exposure", "visitor_id": "v", "meta": "not-a-dict"},
         {"nonsense": True}], root=tmp_path)
    assert r["ok"] is True and r["assignments"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. The nightly runner + its wiring
# ═══════════════════════════════════════════════════════════════════════════

from scripts import ad_ingest_run  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"


def test_the_runner_is_actually_wired_into_the_nightly():
    """A nightly script nobody calls is dead code that looks like a feature."""
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts.ad_ingest_run" in wf, "the ingest step is not in daily.yml"
    assert "SUPABASE_ACCESS_TOKEN" in wf and "SUPABASE_PROJECT_REF" in wf
    # …and the ledgers it advances must actually be committed, or every night's
    # work is discarded when the runner's checkout is thrown away.
    assert "git add data/marketing/ad_central" in wf, (
        "the arena ledgers are written but never committed — the ledger would "
        "reset to empty every night"
    )


def test_the_query_window_is_clamped_and_static():
    """All SQL is authored here; the only interpolated value is an int-clamped window."""
    seen = {}

    def fake_sql(q):
        seen["q"] = q
        return []

    ad_ingest_run.fetch_rows(9999, sql=fake_sql)
    assert "interval '365 days'" in seen["q"]
    ad_ingest_run.fetch_rows(-5, sql=fake_sql)
    assert "interval '1 days'" in seen["q"]
    # The window is the ONLY interpolated value, and it must be an int or nothing.
    with pytest.raises(ValueError):
        ad_ingest_run.fetch_rows("7; drop table analytics_events", sql=fake_sql)
    assert "drop table" not in seen["q"]


def test_the_query_asks_only_for_what_the_fold_needs():
    seen = {}

    def fake_sql(q):
        seen["q"] = q
        return []

    ad_ingest_run.fetch_rows(7, sql=fake_sql)
    q = seen["q"]
    assert "ad_exposure" in q
    # Restricted to visitors that actually have an exposure — otherwise this drags
    # the whole events table back every night.
    assert "exposed" in q and "visitor_id in (select visitor_id from exposed)" in q
    for col in ("visitor_id", "user_id", "created_at", "meta"):
        assert col in q
    assert f"limit {ad_ingest_run.MAX_ROWS}" in q


def test_a_non_list_response_degrades_to_no_rows():
    assert ad_ingest_run.fetch_rows(7, sql=lambda q: {"error": "nope"}) == []


def test_no_credential_is_a_skip_not_a_failure(tmp_path, monkeypatch, capsys):
    """A nightly that hard-fails on a missing optional secret is a broken pipeline."""
    monkeypatch.setattr(ad_ingest_run, "PAT", "")
    assert ad_ingest_run.main(["--root", str(tmp_path)]) == 0
    assert "skipping" in capsys.readouterr().out
    assert not (tmp_path / ad_arena.DEFAULT_LEDGER_DIR).exists()


def test_a_read_failure_warns_and_does_not_fail_the_nightly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ad_ingest_run, "PAT", "sbp_test")
    monkeypatch.setattr(ad_ingest_run, "fetch_rows",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    assert ad_ingest_run.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "::warning" in out and "403" in out


def test_the_runner_advances_the_ledger_end_to_end(tmp_path, monkeypatch, capsys):
    arena = _seed_arena(tmp_path)
    rows = []
    for i in range(120):
        cid = ad_arena.assign(arena, f"v-{i}")
        rows.append(_exposure(f"v-{i}", cid, f"2026-07-27T10:{i // 60:02d}:{i % 60:02d}Z"))
    rows.append(_pageview("v-0", "2026-07-27T20:00:00Z", user_id="u-0"))

    monkeypatch.setattr(ad_ingest_run, "PAT", "sbp_test")
    monkeypatch.setattr(ad_ingest_run, "fetch_rows", lambda *a, **k: rows)
    assert ad_ingest_run.main(["--root", str(tmp_path)]) == 0
    assert "Recorded 120 new visitors" in capsys.readouterr().out

    tally = ad_arena.tally_from_ledgers(ad_arena.load_arenas(root=tmp_path)[0], root=tmp_path)
    assert sum(a.assigned for a in tally.arms) == 120
    assert sum(a.converted for a in tally.arms) == 1


def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    arena = _seed_arena(tmp_path)
    rows = [_exposure("v-1", ad_arena.assign(arena, "v-1"), "2026-07-27T10:00:00Z")]
    monkeypatch.setattr(ad_ingest_run, "PAT", "sbp_test")
    monkeypatch.setattr(ad_ingest_run, "fetch_rows", lambda *a, **k: rows)
    assert ad_ingest_run.main(["--root", str(tmp_path), "--dry-run"]) == 0
    assert "Would record" in capsys.readouterr().out
    assert ad_arena.read_jsonl(
        tmp_path / ad_arena.DEFAULT_LEDGER_DIR / ad_arena.ASSIGNMENTS_FILE) == []


def test_the_runner_carries_the_waf_user_agent():
    """api.supabase.com sits behind a WAF that 403s the default urllib UA — a failure
    that looks like an auth problem and is not (same fix as scripts/geo_enrich.py)."""
    src = (ROOT / "scripts" / "ad_ingest_run.py").read_text(encoding="utf-8")
    assert "User-Agent" in src and "Mozilla/5.0" in src


# ═══════════════════════════════════════════════════════════════════════════
# 7. Rich copy: markup-preserving + bilingual
# ═══════════════════════════════════════════════════════════════════════════

_RICH_HARNESS = r"""
const path = require('path');
const cfg = JSON.parse(process.argv[1]);
const langFirst = process.argv[2] === 'lang-first';
const calls = [];
const el = {
  _html: '<b>control</b> copy', _attrs: { 'data-adtest-slot': 'headline', 'data-zh': '控制文案' },
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = v; },
  getAttribute(k) { return this._attrs[k] == null ? null : this._attrs[k]; },
  setAttribute(k, v) { this._attrs[k] = v; },
  set textContent(v) { this._html = v; }, get textContent() { return this._html; },
};
// The landing's switcher: caches the English ONCE, then rewrites from it.
function applyLang(l) {
  if (el.__en == null) el.__en = el.innerHTML;
  el.innerHTML = (l === 'zh') ? el.getAttribute('data-zh') : el.__en;
}
if (langFirst) applyLang('en');          // switcher ran BEFORE the shim
global.window = {
  localStorage: (() => { const m = {}; return { getItem: k => m[k] || null, setItem: (k, v) => { m[k] = String(v); } }; })(),
  crypto: { randomUUID: () => 'FIXED-UNIT-ID' },
  mmTrack: (t, e) => calls.push([t, e]),
};
global.document = {
  readyState: 'complete', cookie: '',
  getElementById: id => (id === 'mm-adtest' ? { textContent: JSON.stringify(cfg) } : null),
  querySelectorAll: () => [el], addEventListener: () => {},
};
global.setTimeout = (fn) => fn();
require(path.join(process.cwd(), 'templates', 'adtest.js'));
const afterApply = el.innerHTML;
applyLang('zh'); const zhView = el.innerHTML;
applyLang('en'); const backToEn = el.innerHTML;
console.log(JSON.stringify({ afterApply, zhView, backToEn, dataZh: el.getAttribute('data-zh'),
                             creative: (global.window.mmAdtest || {}).creative, calls }));
"""


def _run_rich(cfg: dict, *, lang_first: bool = False) -> dict:
    out = subprocess.run(
        ["node", "-e", _RICH_HARNESS, json.dumps(cfg), "lang-first" if lang_first else "-"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, f"node failed:\n{out.stderr}"
    return json.loads(out.stdout)


def _rich_cfg(**kw) -> dict:
    base = {
        "arena_id": "hero-1", "status": "running", "mode": "live", "holdout": 0.0,
        "arms": [{"id": "adc-only", "w": 1.0, "copy": {"headline": {
            "html": "Variant<br><span class=\"dim\">line two.</span>", "zh": "变体<br>第二行。"}}}],
    }
    base.update(kw)
    return base


@needs_node
def test_rich_copy_preserves_markup_instead_of_flattening_it():
    """textContent would strip the <br> and the dim span — changing typography as
    well as words, so the test would no longer measure copy alone."""
    r = _run_rich(_rich_cfg())
    assert r["afterApply"] == 'Variant<br><span class="dim">line two.</span>'


@needs_node
def test_rich_copy_updates_the_chinese_too():
    """Otherwise every zh visitor reads the control while counted in the variant."""
    r = _run_rich(_rich_cfg())
    assert r["dataZh"] == "变体<br>第二行。"
    assert r["zhView"] == "变体<br>第二行。"


@needs_node
def test_a_language_toggle_does_not_revert_the_variant():
    """The switcher caches the English once. If it ran first, that cache holds the
    CONTROL — and zh→en would silently put the visitor back on the control arm."""
    r = _run_rich(_rich_cfg(), lang_first=True)
    assert r["afterApply"] == 'Variant<br><span class="dim">line two.</span>'
    assert r["backToEn"] == 'Variant<br><span class="dim">line two.</span>', (
        "toggling zh and back restored the control copy — the visitor is now on a "
        "different arm than the one they are counted in"
    )


@needs_node
def test_plain_string_slots_still_work():
    cfg = _rich_cfg(arms=[{"id": "adc-only", "w": 1.0, "copy": {"headline": "just text"}}])
    r = _run_rich(cfg)
    assert r["afterApply"] == "just text"


@needs_node
def test_a_malformed_slot_value_leaves_the_authored_copy_alone():
    for bad in ({}, {"zh": "只有中文"}, {"html": ""}, 42, None):
        cfg = _rich_cfg(arms=[{"id": "adc-only", "w": 1.0, "copy": {"headline": bad}}])
        r = _run_rich(cfg)
        assert r["afterApply"] == "<b>control</b> copy", f"{bad!r} overwrote the hero"


# ═══════════════════════════════════════════════════════════════════════════
# 8. The live landing hero — page config must match the ledger
# ═══════════════════════════════════════════════════════════════════════════

LANDING = ROOT / "templates" / "index.html"
SITE_LANDING = ROOT / "site" / "index.html"


def _page_config() -> dict:
    html = LANDING.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="mm-adtest">(.*?)</script>', html, re.S)
    assert m, "the landing carries no mm-adtest config block"
    return json.loads(m.group(1))


def test_the_landing_config_matches_the_arena_ledger():
    """The page config is what actually assigns visitors; the ledger is what scores
    them. Drift between the two is the same silent failure as a hash mismatch."""
    cfg = _page_config()
    arena = next((a for a in ad_arena.load_arenas(root=ROOT)
                  if a.arena_id == cfg["arena_id"]), None)
    assert arena is not None, f"{cfg['arena_id']} is on the page but not in the ledger"
    assert cfg["status"] == arena.status
    assert cfg["mode"] == arena.mode
    assert cfg["holdout"] == arena.holdout
    assert [a["id"] for a in cfg["arms"]] == arena.arm_creative_ids, (
        "arm ORDER differs — the cumulative walk visits arms in list order, so a "
        "reordering silently reassigns everyone"
    )
    for arm in cfg["arms"]:
        assert arm["w"] == arena.assignment_weights[arm["id"]]


def test_only_one_hero_arena_is_live():
    """Two live arenas on one page would assign the same visitor twice and both
    would score the other's traffic."""
    live = [a for a in ad_arena.load_arenas(root=ROOT)
            if a.plane == "owned" and a.status == "running" and a.mode == "live"]
    assert len(live) <= 1, f"{[a.arena_id for a in live]} are all live on owned inventory"


def test_every_live_arm_carries_both_languages():
    """A variant that updates only English leaves zh visitors on the control copy
    while counted in the variant's arm."""
    for arm in _page_config()["arms"]:
        for slot, value in arm["copy"].items():
            assert isinstance(value, dict), f"{arm['id']}/{slot} is not a rich slot"
            assert value.get("html"), f"{arm['id']}/{slot} has no English"
            assert value.get("zh"), f"{arm['id']}/{slot} has no Chinese"


def test_the_variants_differ_only_in_words_not_structure():
    """An A/B test that changes two things measures neither. Both arms must keep the
    same tags, so the test isolates copy from typography and layout."""
    arms = _page_config()["arms"]
    assert len(arms) == 2
    for slot in ("hero_headline", "hero_sub"):
        shapes = []
        for arm in arms:
            html = arm["copy"][slot]["html"]
            shapes.append(sorted(re.findall(r"<(\w+)", html)))
        assert shapes[0] == shapes[1], (
            f"{slot}: arms use different markup {shapes} — the test would be measuring "
            f"a typography change as well as a copy change"
        )


def test_the_control_arm_is_the_copy_already_on_the_page():
    """The control must be what shipped, or 'lift vs control' is lift against a
    variant nobody has been seeing."""
    cfg = _page_config()
    arena = next(a for a in ad_arena.load_arenas(root=ROOT) if a.arena_id == cfg["arena_id"])
    control = next(a for a in cfg["arms"] if a["id"] == arena.control_creative_id)
    html = LANDING.read_text(encoding="utf-8")
    # NB: not `<h1 ...[^>]*>` — the data-zh attribute VALUE contains "<br>" and a
    # span, so an attribute-scanning regex closes the tag inside the attribute and
    # captures the tail of the Chinese string. Slice to </h1> and match the end.
    start = html.find('<h1 data-adtest-slot="hero_headline"')
    assert start != -1, "the hero h1 carries no adtest slot"
    body = html[start:html.index("</h1>", start)]
    assert body.endswith(control["copy"]["hero_headline"]["html"]), (
        "the control arm's copy is not what the page ships — 'lift vs control' would "
        "be lift against a variant nobody has been seeing"
    )


def test_the_landing_loads_the_shim_after_the_slots():
    """Loaded in <head> it would find no slots; deferred it would paint the control
    first. It has to sit after the block it rewrites."""
    html = LANDING.read_text(encoding="utf-8")
    slot_at = html.index('data-adtest-slot="hero_headline"')
    script_at = html.index('<script src="adtest.js">')
    assert slot_at < script_at, "adtest.js loads before the slots it rewrites"
    assert "defer" not in html[script_at:script_at + 60]


def test_the_landing_pair_stays_byte_identical():
    assert LANDING.read_bytes() == SITE_LANDING.read_bytes()


# ═══════════════════════════════════════════════════════════════════════════
# 9. The exposure actually leaves the page
# ═══════════════════════════════════════════════════════════════════════════

_BEACON_HARNESS = r"""
const path = require('path');
const cfg = JSON.parse(process.argv[1]);
const host = process.argv[2];
const withMmTrack = process.argv[3] === 'with-mmtrack';
const useSendBeacon = process.argv[4] !== 'no-sendbeacon';
const sent = [], tracked = [];
const el = { _html: 'control', getAttribute: k => (k === 'data-adtest-slot' ? 'headline' : null),
             setAttribute() {}, set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; },
             set textContent(v) { this._html = v; }, get textContent() { return this._html; } };
global.Blob = class { constructor(parts) { this.parts = parts; } };
// Node >=21 ships a read-only `navigator` global, so `global.navigator = {...}`
// is silently ignored — the first version of this harness "proved" no beacon was
// sent when the shim had actually fallen through to fetch. Define it properly.
Object.defineProperty(globalThis, 'navigator', {
  value: useSendBeacon ? { sendBeacon: (url, body) => { sent.push([url, String(body.parts[0])]); return true; } } : {},
  configurable: true, writable: true,
});
global.fetch = (url, opts) => { sent.push([url, String(opts && opts.body)]); return Promise.resolve(); };
global.location = { hostname: host, pathname: '/' };
global.window = {
  localStorage: (() => { const m = {}; return { getItem: k => m[k] || null, setItem: (k, v) => { m[k] = String(v); } }; })(),
  crypto: { randomUUID: () => 'FIXED-UNIT-ID' },
  location: global.location,
};
if (withMmTrack) global.window.mmTrack = (t, e) => tracked.push([t, e]);
global.document = {
  readyState: 'complete', cookie: '',
  getElementById: id => (id === 'mm-adtest' ? { textContent: JSON.stringify(cfg) } : null),
  querySelectorAll: () => [el], addEventListener: () => {},
};
global.setTimeout = (fn) => fn();
require(path.join(process.cwd(), 'templates', 'adtest.js'));
console.log(JSON.stringify({ sent, tracked, arm: (global.window.mmAdtest || {}).creative }));
"""


def _run_beacon(host: str, *, with_mmtrack: bool = False, send_beacon: bool = True) -> dict:
    cfg = {"arena_id": "hero-1", "status": "running", "mode": "live", "holdout": 0.0,
           "arms": [{"id": "adc-only", "w": 1.0, "copy": {"headline": "variant"}}]}
    out = subprocess.run(
        ["node", "-e", _BEACON_HARNESS, json.dumps(cfg), host,
         "with-mmtrack" if with_mmtrack else "-",
         "-" if send_beacon else "no-sendbeacon"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, f"node failed:\n{out.stderr}"
    return json.loads(out.stdout)


@needs_node
def test_the_exposure_is_sent_even_with_no_mmtrack():
    """THE LANDING DOES NOT LOAD theme.js. An earlier version waited for mmTrack and
    gave up quietly — the hero test assigned visitors, rewrote copy, and recorded
    ZERO exposures. A page that looks perfect while measuring nothing."""
    r = _run_beacon("www.mastermind-x.com")
    assert r["arm"] == "adc-only"
    assert len(r["sent"]) == 1, "no exposure left the page"
    url, body = r["sent"][0]
    assert url == "/api/collect"
    payload = json.loads(body)["events"][0]
    assert payload["type"] == "ad_exposure"
    assert payload["meta"]["arena"] == "hero-1"
    assert payload["meta"]["creative"] == "adc-only"
    # The row carries no identity of its own — the server stamps visitor_id.
    assert "visitor_id" not in payload and "u" not in payload


@needs_node
def test_mmtrack_is_still_preferred_where_it_exists():
    """Pages that DO load theme.js keep batching through it — one row, not two."""
    r = _run_beacon("www.mastermind-x.com", with_mmtrack=True)
    assert len(r["tracked"]) == 1 and r["tracked"][0][0] == "ad_exposure"
    assert r["sent"] == [], "double-reported: batched AND beaconed"


@needs_node
def test_no_beacon_off_the_canonical_origin():
    """/api/collect is served only by the canonical host; a preview run must record
    nothing rather than fire at an endpoint that is not there."""
    for host in ("localhost", "127.0.0.1", "example.com", "mastermind-x.com.evil.test"):
        r = _run_beacon(host)
        assert r["sent"] == [], f"beaconed from {host}"
        assert r["arm"] == "adc-only", f"{host}: copy should still be applied"


def test_the_landing_carries_no_dependency_on_theme_js():
    """A guard for the actual defect: the landing pulls only onboard.js + adtest.js,
    so anything here that needs window.mmTrack is dead code on this page."""
    html = LANDING.read_text(encoding="utf-8")
    srcs = re.findall(r'<script[^>]*src="([^"]+)"', html)
    assert not any("theme.js" in s for s in srcs), (
        "the landing now loads theme.js — re-check whether adtest.js should defer "
        "to mmTrack batching instead of beaconing directly"
    )
    code = _js_code_only(SHIM.read_text(encoding="utf-8"))
    assert "/api/collect" in code, "the shim cannot report without theme.js"


@needs_node
def test_the_fetch_fallback_carries_same_origin_credentials():
    """Without sendBeacon the shim posts with fetch — and the request must send the
    mm_aid cookie, or the server has no identity to stamp on the row."""
    r = _run_beacon("www.mastermind-x.com", send_beacon=False)
    assert len(r["sent"]) == 1, "no exposure left the page on the fetch path"
    url, body = r["sent"][0]
    assert url == "/api/collect"
    assert json.loads(body)["events"][0]["type"] == "ad_exposure"
    code = _js_code_only(SHIM.read_text(encoding="utf-8"))
    assert "credentials: 'same-origin'" in code
