"""Hydration must MERGE the withheld board cards into the groups the shell drew.

THE BUG (reported on the live board 2026-08-20, reproduced against the shipped
site/us_stocks.html + site/premiumdata/us_stocks.json): the US Prophet board
showed "LIVE NOW · 13" twice — once over three cards, then again over ten
different ones — with "Setting up · 38" below both.

Neither side of the tier wall was wrong on its own. Both render from the same
partial (templates/_us_board_cards.html.j2) and each groups ITS OWN rows: the
shell heads the preview slice, the tier payload heads the locked remainder, and
both stamp the TRUE full-board count (build_site._us_board_group_items — that is
deliberate, so a gated shell's heading stays honest while only the preview shows
under it). The defect was purely in how the two were joined:
`grid.insertAdjacentHTML('beforeend', payload.cards_html)` appended the payload's
whole heading-bearing block after the shell's, so

  * every stage present on BOTH sides drew its heading twice, and
  * every withheld group landed after every shell group, so a preview that
    spanned two stages put the withheld "Live now" BELOW "Setting up".

These tests run the SHIPPED merge — sliced out of the rendered page, not
reimplemented — against a stub DOM (tests/us_board_hydrate_harness.js), plus the
markup-contract pins that keep the join key alive on both sides of the wall.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHELL = ROOT / "site" / "us_stocks.html"
PAYLOAD = ROOT / "site" / "premiumdata" / "us_stocks.json"
HARNESS = Path(__file__).with_name("us_board_hydrate_harness.js")
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

STAGE_HD = re.compile(r'<div class="nb-stage-hd[^"]*"[^>]*data-stage="([^"]+)"')

from tests.test_us_board_gate import (  # noqa: E402
    _render_shell, _rows_with_stage, _rows,
)


def _merge_source(html: str) -> str:
    """The BOARD_STAGES / groupKey / stageRank / mergeBoardCards block, sliced
    out of a rendered page. Bounded by two markers rather than brace-counted:
    if either moves, this fails loudly instead of silently testing nothing."""
    start = html.find("var BOARD_STAGES")
    end = html.find("function hydrate(payload){", start if start >= 0 else 0)
    assert start >= 0, "rendered shell carries no BOARD_STAGES block"
    assert end > start, "BOARD_STAGES block must sit above hydrate()"
    src = html[start:end]
    for name in ("function groupKey(", "function stageRank(", "function mergeBoardCards("):
        assert name in src, f"{name} missing from the sliced merge block"
    return src


def _run_merge(tmp_path: Path, merge_js: str, shell: str, payload: str) -> dict:
    js = tmp_path / "merge.js"
    js.write_text(merge_js, encoding="utf-8")
    scene = tmp_path / "scene.json"
    scene.write_text(json.dumps({"shell": shell, "payload": payload}), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(HARNESS), str(scene), str(js)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def _grid_inner(html: str) -> str:
    """The board grid's own children, sliced by matching `<div>` depth rather
    than by a `.*?</div>` regex — the grid holds cards full of nested divs, so a
    lazy match stops inside the first card and hands the harness truncated
    markup that parses into phantom top-level nodes."""
    open_tag = '<div class="nbgrid" data-showmore-rows="3">'
    start = html.find(open_tag)
    assert start >= 0, "shipped shell has no board grid"
    i = start + len(open_tag)
    depth, out_start = 1, i
    for m in re.finditer(r"<div\b|</div>", html[i:]):
        depth += 1 if m.group(0) != "</div>" else -1
        if depth == 0:
            return html[out_start:i + m.start()]
    raise AssertionError("unbalanced <div> in the board grid")


def _hd(stage: str, count: int = 13) -> str:
    return (f'<div class="nb-stage-hd sg-{stage}" data-stage="{stage}">'
            f'<span class="sh-n">{count}</span></div>')


def _card(ticker: str, stage: str = "live") -> str:
    return (f'<a class="pvcard" data-ticker="{ticker}" data-stage="{stage}">'
            f'<span class="nb-tk">{ticker}</span></a>')


@pytest.fixture(scope="module")
def merge_js() -> str:
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, _ = _split_us_board({"buy": _rows_with_stage(7), "eligible": 7},
                                        3, gated=True)
    return _merge_source(_render_shell(shell_su, gate))


# ── the merge itself (executable, against the shipped source) ───────────────

@needs_node
def test_a_stage_on_both_sides_of_the_wall_keeps_one_heading(tmp_path, merge_js):
    """THE REPORTED BUG. The shell's "Live now" and the payload's "Live now" are
    one group: one heading, preview names first, withheld names after."""
    out = _run_merge(
        tmp_path, merge_js,
        shell=_hd("live") + _card("BIIB") + _card("JNJ") + _card("TRGP"),
        payload=_hd("live") + _card("HWM") + _card("GNW")
                + _hd("setting_up", 38) + _card("ANDE", "setting_up"),
    )
    assert [g["key"] for g in out["groups"]] == ["stage:live", "stage:setting_up"]
    assert out["groups"][0]["tickers"] == ["BIIB", "JNJ", "TRGP", "HWM", "GNW"]
    assert out["groups"][1]["tickers"] == ["ANDE"]
    assert out["headings"] == 2, "a stage may never draw two headings"


@needs_node
def test_withheld_group_is_placed_by_stage_rank_not_appended(tmp_path, merge_js):
    """The ordering half of the same defect: a preview holding only a LATE stage
    must not push the withheld earlier stages underneath it."""
    out = _run_merge(
        tmp_path, merge_js,
        shell=_hd("blocked", 5) + _card("SHELL1", "blocked"),
        payload=_hd("live") + _card("HWM")
                + _hd("ran", 5) + _card("WMB", "ran")
                + _hd("blocked", 5) + _card("NNN", "blocked"),
    )
    assert [g["key"] for g in out["groups"]] == [
        "stage:live", "stage:ran", "stage:blocked",
    ], "withheld stages must land at their own rank, not after the shell's"
    # the shell's own card still leads its group
    assert out["groups"][-1]["tickers"] == ["SHELL1", "NNN"]


@needs_node
def test_stages_the_shell_never_drew_arrive_whole_and_in_order(tmp_path, merge_js):
    out = _run_merge(
        tmp_path, merge_js,
        shell=_hd("live") + _card("BIIB"),
        payload=_hd("setting_up", 38) + _card("ANDE", "setting_up")
                + _hd("basing", 2) + _card("IART", "basing")
                + _hd("blocked", 5) + _card("NNN", "blocked"),
    )
    assert [g["key"] for g in out["groups"]] == [
        "stage:live", "stage:setting_up", "stage:basing", "stage:blocked",
    ]
    assert out["cards"] == 4


@needs_node
def test_an_empty_payload_changes_nothing(tmp_path, merge_js):
    """Ungated builds ship `cards_html: ""` — the merge must be a clean no-op
    rather than an exception that strands hydratePanels' work."""
    shell = _hd("live") + _card("BIIB") + _card("JNJ")
    out = _run_merge(tmp_path, merge_js, shell=shell, payload="")
    assert [g["key"] for g in out["groups"]] == ["stage:live"]
    assert out["groups"][0]["tickers"] == ["BIIB", "JNJ"]


@needs_node
def test_legacy_lane_headings_merge_on_data_lane(tmp_path, merge_js):
    """The legacy `lane` grouping takes the same path — that is what data-lane
    on .nb-lane-hd is for (templates/_us_board_cards.html.j2)."""
    out = _run_merge(
        tmp_path, merge_js,
        shell='<div class="nb-lane-hd" data-lane="bottoming">Bottoming</div>' + _card("SHELL1"),
        payload='<div class="nb-lane-hd" data-lane="bottoming">Bottoming</div>' + _card("P1")
                + '<div class="nb-lane-hd" data-lane="trend">Trend</div>' + _card("P2"),
    )
    assert [g["key"] for g in out["groups"]] == ["lane:bottoming", "lane:trend"]
    assert out["groups"][0]["tickers"] == ["SHELL1", "P1"]


@needs_node
def test_a_keyless_heading_degrades_to_appending_not_to_collapsing(tmp_path, merge_js):
    """A payload cached from before data-lane shipped has lane headings with no
    join key. That must degrade to the OLD append behaviour (a repeated heading,
    visible but harmless) — never to merging two different lanes into one."""
    out = _run_merge(
        tmp_path, merge_js,
        shell='<div class="nb-lane-hd">Bottoming</div>' + _card("SHELL1"),
        payload='<div class="nb-lane-hd">Bottoming</div>' + _card("P1")
                + '<div class="nb-lane-hd">Trend</div>' + _card("P2"),
    )
    assert out["cards"] == 3, "no card may be dropped by the fallback"
    assert out["headings"] == 3, "keyless headings append; they must not be joined"


# ── the markup contract the merge joins on ─────────────────────────────────

def test_the_shell_no_longer_blind_appends_the_payload_block(merge_js):
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, _ = _split_us_board({"buy": _rows_with_stage(7), "eligible": 7},
                                        3, gated=True)
    html = _render_shell(shell_su, gate)
    assert "mergeBoardCards(grid, payload.cards_html)" in html
    assert "insertAdjacentHTML('beforeend', payload.cards_html)" not in html, (
        "blind-appending the payload block is the defect — it re-draws every "
        "heading the shell already drew"
    )


def test_both_heading_idioms_carry_a_join_key():
    """A heading with no data-stage/data-lane cannot be merged, so the fix
    silently reverts to the bug. Pin the attribute on the partial itself."""
    src = (ROOT / "templates" / "_us_board_cards.html.j2").read_text(encoding="utf-8")
    assert 'class="nb-stage-hd sg-{{ _sk }}" data-stage="{{ _sk }}"' in src
    assert 'class="nb-lane-hd" data-lane="{{ n.lane }}"' in src


def test_the_lane_path_still_renders_its_heading_label():
    """data-lane is additive: the legacy heading must keep its bilingual label
    and count, or the attribute traded a duplicate heading for a blank one."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, _ = _split_us_board({"buy": _rows(7), "eligible": 7}, 3, gated=True)
    html = _render_shell(shell_su, gate)
    m = re.search(r'<div class="nb-lane-hd" data-lane="(\w+)">(.*?)</div>', html, re.S)
    assert m, "lane heading missing or lost its data-lane"
    assert "l-en" in m.group(2) and "l-zh" in m.group(2) and "·" in m.group(2)


# ── the shipped artifacts ──────────────────────────────────────────────────

def test_the_shipped_pair_really_does_repeat_a_heading():
    """Proof the merge is load-bearing and not guarding a hypothetical: on the
    bytes actually served, at least one stage is headed on BOTH sides of the
    wall — which is exactly what used to render twice."""
    if not SHELL.exists() or not PAYLOAD.exists():
        pytest.skip("us_stocks not yet rebaked in the gated shape")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated") or not payload.get("cards_html"):
        pytest.skip("board is ungated in this build — nothing to merge")
    shell_stages = set(STAGE_HD.findall(SHELL.read_text(errors="ignore")))
    payload_stages = set(STAGE_HD.findall(payload["cards_html"]))
    assert shell_stages, "gated shell must still head its preview slice"
    assert shell_stages & payload_stages, (
        "the shell and the payload no longer share a stage heading — if the "
        "split changed shape, re-derive what the merge has to join"
    )


@needs_node
def test_the_shipped_pair_merges_to_one_heading_per_stage(tmp_path, merge_js):
    """End-to-end on the served bytes: hydrating the real payload into the real
    shell yields exactly one heading per stage, in stage order, with every
    withheld card present."""
    if not SHELL.exists() or not PAYLOAD.exists():
        pytest.skip("us_stocks not yet rebaked in the gated shape")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated") or not payload.get("cards_html"):
        pytest.skip("board is ungated in this build — nothing to merge")
    shell_cards = _grid_inner(SHELL.read_text(errors="ignore"))
    out = _run_merge(tmp_path, merge_js, shell=shell_cards, payload=payload["cards_html"])
    keys = [g["key"] for g in out["groups"]]
    assert len(keys) == len(set(keys)), f"a stage drew two headings: {keys}"
    order = ["stage:live", "stage:setting_up", "stage:ran", "stage:basing", "stage:blocked"]
    assert keys == [k for k in order if k in keys], f"stages out of order: {keys}"
    assert out["cards"] == payload["total"], (
        f"{out['cards']} cards on the merged board, payload declares "
        f"{payload['total']} — hydration dropped or duplicated rows"
    )
