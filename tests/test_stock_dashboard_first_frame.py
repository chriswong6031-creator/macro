"""Hermetic P0B zero-FOUC contracts for the HK and Canada dashboards.

This suite reads only source-controlled template, composer, stylesheet, and
loader bytes.  It belongs in the PR ``gate: code`` lane.  Assertions over
generated pages and their current data populations live separately in
``test_stock_dashboard_first_frame_data.py`` so they remain in ``gate: data``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BROWSER_RECEIPT = ROOT / "scripts" / "verify_stock_dashboard_mobile_layout.cjs"

MARKETS = {
    "hk": {
        "template": ROOT / "templates" / "hk.html.j2",
        "composer": ROOT / "site" / "hk-stock-v36.js",
        "main": "hk-v37",
        "landmarks": (
            "hk-v37-head",
            "hk-v37-actnow",
            "hk-v37-prophet",
            "hk-v37-leadership",
            "hk-v37-evidence",
            "hk-v37-tools",
        ),
        "owner_actnow": "act-now",
        "owner_board": "standouts",
        "owner_evidence": "track-record",
        "owner_evidence_marker": 'id="track-record"',
        "mounted": "hk-v37-mounted",
    },
    "ca": {
        "template": ROOT / "templates" / "canada.html.j2",
        "composer": ROOT / "site" / "canada-stock-v36.js",
        "main": "ca-v36",
        "landmarks": (
            "ca-v36-head",
            "ca-v36-actnow",
            "ca-v36-prophet",
            "ca-v36-leadership",
            "ca-v36-evidence",
            "ca-v36-tools",
        ),
        "owner_actnow": "act-now",
        "owner_board": "standouts",
        "owner_evidence": "ca-track-record",
        "owner_evidence_marker": "ca_track_record_surface()",
        "mounted": "ca-v36-mounted",
    },
}


def _read(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"sparse checkout omits {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _function_source(text: str, name: str) -> str:
    match = re.search(
        rf"  function {re.escape(name)}\b.*?(?=\n  function |\n  if \(document\.readyState)",
        text,
        re.S,
    )
    assert match, f"{name}() missing"
    return match.group(0)


def _run_node_function(text: str, name: str, program: str) -> object:
    """Execute the real production function with tiny DOM-owner fixtures."""
    node = shutil.which("node")
    assert node, "node is required for the stock-dashboard code gate"
    harness = "\n".join(
        (
            "let qs, qsa, state;",
            "function bi(en, _zh) { return en; }",
            _function_source(text, name),
            program,
        )
    )
    run = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _template_shell(market: str) -> str:
    spec = MARKETS[market]
    text = _read(spec["template"])
    marker = f'id="{spec["main"]}"'
    start = text.index("<main", text.index(marker) - 100)
    end = text.index("</main>", start)
    return text[start:end]


@pytest.mark.parametrize("market", MARKETS)
def test_template_owns_one_static_canonical_main(market: str) -> None:
    """The deployable source, not JavaScript, owns the complete page skeleton."""
    spec = MARKETS[market]
    template = _read(spec["template"])
    shell = _template_shell(market)
    assert template.count("<main") == 1
    assert f'id="{spec["main"]}"' in shell
    assert "mx-stockdash" in shell
    assert f"mx-stockdash--{market}" in shell
    positions = [shell.index(f'id="{node_id}"') for node_id in spec["landmarks"]]
    assert positions == sorted(positions), (
        f"{market}: first-frame order must be header -> action -> Prophet -> "
        "leadership -> evidence -> tools"
    )


@pytest.mark.parametrize("market", MARKETS)
def test_owner_surfaces_are_inside_their_static_canonical_landmarks(market: str) -> None:
    """P0B composes owner HTML in place; no hidden source page feeds a clone."""
    spec = MARKETS[market]
    shell = _template_shell(market)
    placements = (
        (spec["landmarks"][1], f'id="{spec["owner_actnow"]}"'),
        (spec["landmarks"][2], f'id="{spec["owner_board"]}"'),
        (spec["landmarks"][4], spec["owner_evidence_marker"]),
    )
    for landmark_id, owner_marker in placements:
        start = shell.index(f'id="{landmark_id}"')
        later = [
            shell.find(f'id="{candidate}"', start + 1)
            for candidate in spec["landmarks"]
        ]
        end = min(pos for pos in later if pos > start)
        assert owner_marker in shell[start:end], (
            f"{market}: owner marker {owner_marker!r} is not statically "
            f"composed inside #{landmark_id}"
        )


@pytest.mark.parametrize("market", MARKETS)
def test_template_loads_governed_shell_css_statically(market: str) -> None:
    """A failed composer request cannot remove the first-frame presentation."""
    template = _read(MARKETS[market]["template"])
    assert '<link id="mx-stockdash-css" rel="stylesheet" href="stock-dashboard.css">' in template


def test_governed_shell_assets_are_static_and_deployable() -> None:
    """The deploy pair is byte-identical and loader success never admits paint."""
    for asset in ("stock-dashboard.css", "dashboard-icons.js"):
        assert _read(ROOT / "templates" / asset) == _read(ROOT / "site" / asset)

    loader = _read(ROOT / "templates" / "dashboard-icons.js")
    assert "ensureStockDashCss" not in loader
    assert "stock-dashboard.css" not in loader
    assert loader.count("function inject()") >= 2


@pytest.mark.parametrize("market", MARKETS)
def test_static_shell_accessible_labels_are_plain_attribute_text(market: str) -> None:
    """The bilingual ``t()`` helper emits markup and must never enter an attribute."""
    shell = _template_shell(market)
    assert 'aria-label="{{ t(' not in shell


@pytest.mark.parametrize("market", MARKETS)
def test_composer_only_enhances_existing_dom_in_place(market: str) -> None:
    """Ban every carrier of the superseded replacement-page architecture."""
    spec = MARKETS[market]
    text = _read(spec["composer"])
    assert not re.search(r"createElement\(\s*['\"]main['\"]\s*\)", text)
    assert spec["mounted"] not in text
    for token in (
        'insertAdjacentElement("afterend", main)',
        "insertAdjacentElement('afterend', main)",
        "grid.insertBefore(card",
        "appendChild(tableWrap)",
        "appendChild(trk)",
        "evBody.appendChild",
    ):
        assert token not in text, f"{market}: composer still migrates owner DOM via {token}"

    build = re.search(r"function buildShell\b.*?(?=\n  function )", text, re.S)
    assert build, f"{market}: buildShell() missing"
    assert f'qs("#{spec["main"]}")' in build.group(0), (
        f"{market}: buildShell() must bind the server-owned #{spec['main']}"
    )


def test_canada_optional_fetches_cannot_admit_or_delay_the_shell() -> None:
    """Canada paints/binds first; basket and pulse JSON enhance Leadership later."""
    text = _read(MARKETS["ca"]["composer"])
    start = re.search(r"function start\b.*?(?=\n  if \(document\.readyState)", text, re.S)
    assert start, "Canada start() body missing"
    body = start.group(0)
    bind_at = body.find("buildShell(payload)")
    fetch_at = body.find("Promise.all")
    assert 0 <= bind_at < fetch_at, (
        "Canada must bind the static shell before optional basket/pulse fetches"
    )
    assert "setTimeout(function () { if (!done)" not in body


def test_canada_top_picks_remains_the_first_five_owner_cards() -> None:
    """P0B must not reinterpret the established nine-name board population."""
    text = _read(MARKETS["ca"]["composer"])
    assert "state.cards.slice(0, 5)" in text
    assert 'card.classList.toggle("ca-v36-top-pick", i < 5)' in text


@pytest.mark.parametrize(
    ("market", "board_phrase"),
    (("hk", "stage board"), ("ca", "board")),
)
def test_result_copy_counts_watch_population_dynamically(
    market: str, board_phrase: str
) -> None:
    """Result copy reports the whole estate without inventing a missing watch zero."""
    text = _read(MARKETS[market]["composer"])
    watch = re.search(r"function watchPopulation\b.*?(?=\n  function )", text, re.S)
    assert watch, f"{market}: watchPopulation() missing"
    assert 'qs("#standouts .watch-strip .watch-grid")' in watch.group(0)
    assert 'qsa("a[href]", grid).length' in watch.group(0)

    apply = _function_source(text, "applyFilter")
    population_copy = _function_source(text, "populationCopy")
    body = apply + population_copy
    assert "watchPopulation()" in body
    assert "watch === null" in body
    assert "current names (" in body
    assert board_phrase in body
    assert "watch unavailable" in body
    assert "当前共" in body
    assert "观察名单暂不可用" in body
    assert "47 current names" not in text
    assert "17 current names" not in text


def test_hk_stage_owner_count_is_fail_closed_and_preserves_numeric_zero() -> None:
    text = _read(MARKETS["hk"]["composer"])
    observed = _run_node_function(
        text,
        "ownerPopulation",
        """
const cases = [null, "unavailable", "0", "39"];
console.log(JSON.stringify(cases.map(function (ownerText) {
  state = {rows: new Array(91), cards: new Array(5)};
  qs = function () { return ownerText === null ? null : {textContent: ownerText}; };
  qsa = function () { return []; };
  return ownerPopulation();
})));
""",
    )
    assert observed == [None, None, 0, 39]


def test_canada_board_count_requires_the_server_owner_marker() -> None:
    template = _read(MARKETS["ca"]["template"])
    assert 'data-owner-population="{{ setups.buy|length }}"' in template

    text = _read(MARKETS["ca"]["composer"])
    observed = _run_node_function(
        text,
        "boardPopulation",
        """
const cases = [null, "unavailable", "0", "9"];
console.log(JSON.stringify(cases.map(function (ownerCount) {
  qs = function (selector) {
    if (selector !== "#ca-v36-card-grid" || ownerCount === null) return null;
    return {getAttribute: function () { return ownerCount; }};
  };
  qsa = function () { return []; };
  state = {cards: new Array(99)};
  return boardPopulation();
})));
""",
    )
    assert observed == [None, None, 0, 9]


@pytest.mark.parametrize(
    ("market", "cases", "expected"),
    (
        (
            "hk",
            [[3, 39, 8], [3, None, 8], [3, None, None], [0, 0, 8]],
            [
                "3 actionable cards shown · 47 current names (39 stage board + 8 watch)",
                "3 actionable cards shown · stage board unavailable · 8 watch names",
                "3 actionable cards shown · stage board unavailable · watch unavailable",
                "0 actionable cards shown · 8 current names (0 stage board + 8 watch)",
            ],
        ),
        (
            "ca",
            [[3, 9, 8], [3, None, 8], [3, None, None], [0, 0, 8]],
            [
                "3 cards shown · 17 current names (9 board + 8 watch)",
                "3 cards shown · board unavailable · 8 watch names",
                "3 cards shown · board unavailable · watch unavailable",
                "0 cards shown · 8 current names (0 board + 8 watch)",
            ],
        ),
    ),
)
def test_population_copy_never_adds_an_unknown_owner_count(
    market: str, cases: list[list[int | None]], expected: list[str]
) -> None:
    text = _read(MARKETS[market]["composer"])
    observed = _run_node_function(
        text,
        "populationCopy",
        f"console.log(JSON.stringify({json.dumps(cases)}.map(function (args) {{ return populationCopy.apply(null, args); }})));",
    )
    assert observed == expected


@pytest.mark.parametrize(
    "selector", (".ca-v36-result", ".hk-v37-result")
)
def test_complete_population_copy_wraps_on_mobile(selector: str) -> None:
    """The longer honest population read must not widen the 390px canvas."""
    css = _read(ROOT / "templates" / "stock-dashboard.css")
    rule = selector + " { width: 100%; white-space: normal; }"
    assert rule in css


def test_hk_mobile_owner_surfaces_cannot_widen_the_document() -> None:
    """The full screener becomes readable cards instead of a crushed wide table."""
    css = _read(ROOT / "templates" / "stock-dashboard.css")
    template = _read(MARKETS["hk"]["template"])
    assert ".mx-stockdash--hk .flows-grid > .flow-col { min-width: 0; }" in css
    assert ".mx-stockdash--hk #hk-screener .tbl-scroll > .sb-table" in css
    assert ".mx-stockdash--hk #hk-screener > .sb-table" in css
    assert "display: block; width: 100%; max-width: 100%; table-layout: auto;" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "content: attr(data-label-en);" in css
    assert "content: attr(data-label-zh);" in css
    assert 'data-label-en="' in template
    assert 'data-label-zh="' in template


def test_mobile_layout_receipt_has_valid_javascript() -> None:
    node = shutil.which("node")
    assert node, "node is required for the stock-dashboard code gate"
    run = subprocess.run(
        [node, "--check", str(BROWSER_RECEIPT)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize("market", MARKETS)
def test_zero_cards_do_not_abort_static_shell_enhancement(market: str) -> None:
    text = _read(MARKETS[market]["composer"])
    start = re.search(r"function start\b.*?(?=\n  if \(document\.readyState)", text, re.S)
    assert start
    assert "if (!state.cards.length) return" not in start.group(0)
