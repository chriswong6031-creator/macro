"""Hermetic P0B zero-FOUC contracts for the HK and Canada dashboards.

This suite reads only source-controlled template, composer, stylesheet, and
loader bytes.  It belongs in the PR ``gate: code`` lane.  Assertions over
generated pages and their current data populations live separately in
``test_stock_dashboard_first_frame_data.py`` so they remain in ``gate: data``.
"""

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]
BROWSER_RECEIPT = ROOT / "scripts" / "verify_stock_dashboard_mobile_layout.cjs"
FIXTURE_RECIPE = ROOT / "scripts" / "render_stock_dashboard_fixture.py"
EVIDENCE_DIR = ROOT / "mockups" / "evidence" / "prophet-p0b-zero-fouc"
FIXTURE_ASSETS = EVIDENCE_DIR / "inputs" / "browser-data"

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
    assert "renderActNow" not in text, (
        f"{market}: the composer must adopt the server-owned action DOM, not render it"
    )
    for generator in ("anRowHtml", "anLaneHtml", "anLaneItems"):
        assert f"function {generator}" not in text, (
            f"{market}: action rows and lanes must have exactly one server owner"
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
    ("market", "owner_selector", "board_phrase"),
    (
        ("hk", "#hk-owner-population-proof", "stage board"),
        ("ca", "#ca-v36-card-grid", "board"),
    ),
)
def test_result_copy_requires_an_identity_proven_unique_population(
    market: str, owner_selector: str, board_phrase: str
) -> None:
    """A combined current-name total is admitted only by the server union proof."""
    text = _read(MARKETS[market]["composer"])
    watch = re.search(r"function watchPopulation\b.*?(?=\n  function )", text, re.S)
    assert watch, f"{market}: watchPopulation() missing"
    assert f'qs("{owner_selector}")' in watch.group(0)
    assert 'getAttribute("data-owner-watch-population")' in watch.group(0)

    unique = re.search(r"function uniquePopulation\b.*?(?=\n  function )", text, re.S)
    assert unique, f"{market}: uniquePopulation() missing"
    assert f'qs("{owner_selector}")' in unique.group(0)
    assert 'getAttribute("data-owner-unique-population")' in unique.group(0)

    apply = _function_source(text, "applyFilter")
    population_copy = _function_source(text, "populationCopy")
    body = apply + population_copy
    assert "watchPopulation()" in body
    assert "uniquePopulation()" in body
    assert "watch === null" in body
    assert "unique === null" in body
    assert "current names (" in body
    assert "unique total unavailable" in body
    assert board_phrase in body
    assert "watch unavailable" in body
    assert "当前共" in body
    assert "去重总数暂不可用" in body
    assert "观察名单暂不可用" in body
    assert "total + watch" not in population_copy
    assert "board + watch" not in population_copy
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
  qs = function (selector) {
    if (selector !== "#hk-owner-population-proof" || ownerText === null) return null;
    return {getAttribute: function (name) {
      return name === "data-owner-board-population" ? ownerText : null;
    }};
  };
  qsa = function () { return []; };
  return ownerPopulation();
})));
""",
    )
    assert observed == [None, None, 0, 39]


def test_canada_board_count_requires_the_server_owner_marker() -> None:
    template = _read(MARKETS["ca"]["template"])
    assert "{% if _ca_owner.board_valid %}" in template
    assert 'data-owner-population="{{ _ca_board_n }}"' in template

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


_MISSING = object()


def _render_canada_owner_fixture(
    setups: object = _MISSING, actions: object = _MISSING
) -> BeautifulSoup:
    """Render Canada from the bounded frozen-fixture context used by P0B."""
    from engine import i18n
    from scripts.render_stock_dashboard_fixture import (
        TEMPLATES,
        TrackingLoader,
        canada_context,
        load_owner_fixture,
    )

    frozen_setups, _owner_path = load_owner_fixture("ca")
    vm = canada_context(frozen_setups)
    if setups is _MISSING:
        vm.pop("setups")
    else:
        vm["setups"] = setups
    if actions is not _MISSING:
        vm["actions"] = actions
    env = Environment(loader=TrackingLoader(TEMPLATES), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("canada.html.j2").render(**vm)
    return BeautifulSoup(html, "html.parser")


def test_canada_static_first_frame_counts_both_proven_owner_lists() -> None:
    """The JS-free first frame names Top and the complete 9+8 estate."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert "5 actionable cards shown" in copy
    assert "17 current names (9 stage board + 8 watch)" in copy
    assert grid.get("data-owner-population") == "9"
    assert grid.get("data-owner-watch-population") == "8"
    assert grid.get("data-owner-unique-population") == "17"
    assert len(soup.select("#standouts .watch-strip .watch-grid a[href]")) == 8


def test_canada_static_first_frame_preserves_explicit_empty_owner_lists() -> None:
    """An explicit empty list is the only shape allowed to prove owner zero."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    setups = {**setups, "buy": [], "watch": []}
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert "0 actionable cards shown" in copy
    assert "0 current names (0 stage board + 0 watch)" in copy
    assert grid.get("data-owner-population") == "0"
    assert grid.get("data-owner-watch-population") == "0"
    assert grid.get("data-owner-unique-population") == "0"


def test_canada_static_first_frame_refuses_an_overlapping_owner_union() -> None:
    """The same ticker on board and watch can never be counted twice as current."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    setups["watch"][0]["ticker"] = setups["buy"][0]["ticker"]
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert "9 stage-board names · 8 watch names · unique total unavailable" in copy
    assert "current names" not in copy
    assert grid.get("data-owner-population") == "9"
    assert grid.get("data-owner-watch-population") == "8"
    assert grid.get("data-owner-unique-population") is None


@pytest.mark.parametrize(
    ("lane", "unavailable", "known_attr"),
    (
        ("buy", "board unavailable", "data-owner-watch-population"),
        ("watch", "watch unavailable", "data-owner-population"),
    ),
)
def test_canada_static_first_frame_rejects_duplicate_owner_identities(
    lane: str, unavailable: str, known_attr: str
) -> None:
    """An owner lane with duplicate stable identities is not a known population."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    setups[lane][1]["ticker"] = setups[lane][0]["ticker"]
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert unavailable in copy
    assert "current names" not in copy
    assert grid.get(known_attr) is not None
    assert grid.get("data-owner-unique-population") is None


def _render_hk_owner_fixture(
    setups: object, actions: object = _MISSING
) -> BeautifulSoup:
    """Render HK from the bounded frozen-fixture context used by P0B."""
    from engine import i18n
    from scripts.render_stock_dashboard_fixture import (
        TEMPLATES,
        TrackingLoader,
        hk_context,
    )

    env = Environment(loader=TrackingLoader(TEMPLATES), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    vm = hk_context(setups)
    if actions is not _MISSING:
        vm["actions"] = actions
    html = env.get_template("hk.html.j2").render(**vm)
    return BeautifulSoup(html, "html.parser")


@pytest.mark.parametrize(
    ("market", "prophet_id", "view_attr", "expected_source", "expected_shown"),
    (
        ("ca", "ca-v36-prophet", "data-ca-view", "top", 5),
        ("hk", "hk-v37-prophet", "data-hk-view", "all", 3),
    ),
)
def test_static_prophet_source_and_chrome_are_truthful_before_composer(
    market: str,
    prophet_id: str,
    view_attr: str,
    expected_source: str,
    expected_shown: int,
) -> None:
    """One header owns source/view/help/vintage before deferred JS can run."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture(market)
    soup = (
        _render_canada_owner_fixture(setups, _actions())
        if market == "ca"
        else _render_hk_owner_fixture(setups, _actions())
    )
    prophet = soup.find(id=prophet_id)
    assert prophet is not None
    assert prophet.get("data-initial-source") == expected_source
    assert prophet.get("data-source-owner-state") == "available"
    selected = prophet.select_one(
        f"[data-{market}-source][aria-selected='true']"
    )
    assert selected is not None
    assert selected.get(f"data-{market}-source") == expected_source
    assert f"{expected_shown} actionable cards shown" in prophet.select_one(
        f"#{market}-v36-result" if market == "ca" else "#hk-v37-result"
    ).get_text(" ", strip=True)

    assert len(prophet.select(":scope > .ca-v36-sec-hd h2, :scope > .hk-v37-sec-hd h2")) == 1
    assert not prophet.select("#standouts > h2")
    assert len(prophet.select("[data-prophet-owner-context]")) == 1
    assert len(prophet.select("[data-prophet-vintage]")) == 1
    assert len(prophet.select("[data-prophet-help]")) == 1

    view_controls = prophet.select("[data-prophet-view-control]")
    assert len(view_controls) == 1
    assert not prophet.select("#st-view-toggle, #st-btn-grid, #st-btn-table")
    view_buttons = view_controls[0].select(f"button[{view_attr}]")
    assert len(view_buttons) == 2
    assert view_buttons[0].get("aria-selected") == "true"
    assert view_buttons[1].get("aria-selected") == "false"
    assert view_buttons[1].has_attr("disabled")
    assert "StockTable._setView" in view_buttons[0].get("onclick", "")
    assert "StockTable._setView" in view_buttons[1].get("onclick", "")


def test_hk_static_source_uses_owner_featured_identity_when_present() -> None:
    """HK Top is the owner pv-featured cohort; zero featured falls back to All."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    setups["buy"][0]["featured"] = True
    setups["buy"][1]["featured"] = True
    soup = _render_hk_owner_fixture(setups, _actions())
    prophet = soup.find(id="hk-v37-prophet")
    assert prophet is not None
    assert prophet.get("data-initial-source") == "top"
    assert prophet.get("data-initial-top-count") == "2"
    assert prophet.select_one("[data-hk-source='top']").get("aria-selected") == "true"
    assert "2 actionable cards shown" in prophet.select_one(
        "#hk-v37-result"
    ).get_text(" ", strip=True)
    assert len(prophet.select("#standouts .pvcard.pv-featured")) == 2


@pytest.mark.parametrize("market", ("ca", "hk"))
def test_static_grid_and_table_share_one_ordered_source_identity(market: str) -> None:
    """The server serializes the exact card cohort StockTable must project."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture(market)
    soup = (
        _render_canada_owner_fixture(setups, _actions())
        if market == "ca"
        else _render_hk_owner_fixture(setups, _actions())
    )
    prophet = soup.find(id="ca-v36-prophet" if market == "ca" else "hk-v37-prophet")
    cards = prophet.select("#standouts .pvcard")
    card_ids = [card.get("data-ticker") for card in cards]
    payload = json.loads(prophet.select_one("#stocktable-data").get_text())
    row_ids = [row["ticker"] for row in payload["rows"]]
    top_row_ids = [row["ticker"] for row in payload["rows"] if row["_top"]]
    top_card_ids = (
        card_ids[:5]
        if market == "ca"
        else [card.get("data-ticker") for card in cards if "pv-featured" in card.get("class", [])]
    )
    assert row_ids == card_ids
    assert top_row_ids == top_card_ids
    expected_visible = top_card_ids if prophet.get("data-initial-source") == "top" else card_ids
    assert int(prophet.get("data-initial-top-count")) == len(top_card_ids)
    assert f"{len(expected_visible)} actionable cards shown" in prophet.select_one(
        "#ca-v36-result" if market == "ca" else "#hk-v37-result"
    ).get_text(" ", strip=True)


@pytest.mark.parametrize("market", ("ca", "hk"))
def test_malformed_source_owner_fails_to_typed_full_view(market: str) -> None:
    """Duplicate owner identities cannot leave a synthetic Top selection active."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture(market)
    setups["buy"][1]["ticker"] = setups["buy"][0]["ticker"]
    soup = (
        _render_canada_owner_fixture(setups, _actions())
        if market == "ca"
        else _render_hk_owner_fixture(setups, _actions())
    )
    prophet = soup.find(id="ca-v36-prophet" if market == "ca" else "hk-v37-prophet")
    assert prophet.get("data-source-owner-state") == "unavailable"
    assert prophet.get("data-initial-source") == "all"
    assert prophet.select_one(f"[data-{market}-source='all']").get("aria-selected") == "true"
    top = prophet.select_one(f"[data-{market}-source='top']")
    assert top.has_attr("disabled")
    assert top.get("aria-disabled") == "true"
    result = prophet.select_one("#ca-v36-result" if market == "ca" else "#hk-v37-result")
    assert "stage board unavailable" in result.get_text(" ", strip=True)


@pytest.mark.parametrize(
    ("market", "enhanced_attr", "prophet_id", "static_selector"),
    (
        (
            "ca",
            "data-ca-enhanced",
            "ca-v36-prophet",
            ".pvcard:nth-of-type(n+6)",
        ),
        (
            "hk",
            "data-hk-enhanced",
            "hk-v37-prophet",
            ".pvcard:not(.pv-featured)",
        ),
    ),
)
def test_static_top_projection_is_css_owned_until_composer_adopts_it(
    market: str, enhanced_attr: str, prophet_id: str, static_selector: str
) -> None:
    css = _read(ROOT / "templates" / "stock-dashboard.css")
    assert f':not([{enhanced_attr}="true"])' in css
    assert f'#{prophet_id}[data-initial-source="top"]' in css
    assert static_selector in css


@pytest.mark.parametrize(
    ("market", "composer", "view_attr", "event_name"),
    (
        ("ca", "canada-stock-v36.js", "data-ca-view", "stocktable:ca-view"),
        ("hk", "hk-stock-v36.js", "data-hk-view", "stocktable:hk-view"),
    ),
)
def test_composer_adopts_server_source_and_single_stocktable_view_transition(
    market: str, composer: str, view_attr: str, event_name: str
) -> None:
    text = _read(ROOT / "site" / composer)
    start = _function_source(text, "start")
    set_view = _function_source(text, "setView")
    assert "data-initial-source" in start
    assert "state.source" in start
    assert event_name in text
    assert "StockTable._setView" in set_view
    assert f'closest("[{view_attr}]")' not in _function_source(text, "bind")


_ACTION_LANES = (
    "buy_now",
    "buy_soon",
    "on_the_run",
    "take_profits",
    "hold",
    "avoid",
)


def _actions(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {lane: [] for lane in _ACTION_LANES}
    payload.update(overrides)
    return payload


def _action_row(ticker: str, name: str = "Fixture sector") -> dict[str, object]:
    return {
        "ticker": ticker,
        "name": name,
        "label": "Fixture action",
        "days": 2,
        "dir": "up",
    }


def _render_action_fixture(market: str, actions: object) -> BeautifulSoup:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture(market)
    if market == "ca":
        return _render_canada_owner_fixture(setups, actions)
    return _render_hk_owner_fixture(setups, actions)


@pytest.mark.parametrize("market", MARKETS)
@pytest.mark.parametrize(
    "actions",
    (
        _MISSING,
        None,
        [],
        {},
        _actions(buy_now=None),
        _actions(avoid="not-a-list"),
        _actions(buy_soon={"ticker": "not-a-list"}),
    ),
)
def test_action_owner_unavailable_never_masquerades_as_healthy_empty(
    market: str, actions: object
) -> None:
    """Missing/non-mapping/mixed-invalid owner state is unavailable, never zero."""
    if actions is _MISSING:
        from scripts.render_stock_dashboard_fixture import load_owner_fixture

        setups, _owner_path = load_owner_fixture(market)
        vm_actions = None
        if market == "ca":
            from engine import i18n
            from scripts.render_stock_dashboard_fixture import (
                TEMPLATES,
                TrackingLoader,
                canada_context,
            )

            vm = canada_context(setups)
            vm.pop("actions")
            env = Environment(loader=TrackingLoader(TEMPLATES), autoescape=False)
            env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
            soup = BeautifulSoup(
                env.get_template("canada.html.j2").render(**vm), "html.parser"
            )
        else:
            from engine import i18n
            from scripts.render_stock_dashboard_fixture import (
                TEMPLATES,
                TrackingLoader,
                hk_context,
            )

            vm = hk_context(setups)
            vm.pop("actions")
            env = Environment(loader=TrackingLoader(TEMPLATES), autoescape=False)
            env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
            soup = BeautifulSoup(
                env.get_template("hk.html.j2").render(**vm), "html.parser"
            )
        assert vm_actions is None
    else:
        soup = _render_action_fixture(market, actions)

    panel = soup.find(id="act-now")
    assert panel is not None
    assert panel.get("data-action-owner-state") == "unavailable"
    copy = panel.get_text(" ", strip=True)
    assert "Action owner unavailable" in copy
    assert "No sector actions are open" not in copy
    assert not panel.select("[data-hk-lead-id], [data-ca-lead-id]")


@pytest.mark.parametrize("market", MARKETS)
def test_explicit_empty_action_owner_is_the_only_healthy_empty_state(
    market: str,
) -> None:
    soup = _render_action_fixture(market, _actions())
    panel = soup.find(id="act-now")
    assert panel is not None
    assert panel.get("data-action-owner-state") == "empty"
    copy = panel.get_text(" ", strip=True)
    assert "No sector actions are open" in copy
    assert "Action owner unavailable" not in copy
    tabs = panel.select(f"[data-{market}-an-lane]")
    lanes = panel.select("[data-action-lane-body]")
    assert len(tabs) == 4
    assert len(lanes) == 4
    assert [tab.get("data-hk-an-lane") or tab.get("data-ca-an-lane") for tab in tabs] == [
        "buy",
        "near",
        "wait",
        "avoid",
    ]
    assert [tab.select_one(".l-en").get_text(strip=True) for tab in tabs] == [
        "Buy Now",
        "In Favour",
        "Bottoming Watch",
        "Reduce / Avoid",
    ]
    assert [tab.select_one("b").get_text(strip=True) for tab in tabs] == ["0"] * 4
    assert not panel.select("[role='tablist'], [role='tab']")
    assert all(not tab.has_attr("aria-selected") for tab in tabs)
    assert all(not tab.has_attr("aria-controls") for tab in tabs)
    assert [tab.has_attr(f"data-{market}-an-default") for tab in tabs] == [True, False, False, False]
    assert [lane.get("data-action-lane-body") for lane in lanes] == [
        "buy",
        "near",
        "wait",
        "avoid",
    ]
    assert [lane.get("data-action-lane-body") for lane in lanes if "is-current" in lane.get("class", [])] == ["buy"]


@pytest.mark.parametrize("market", MARKETS)
@pytest.mark.parametrize(
    ("actions", "selected", "counts", "identities"),
    (
        (_actions(buy_now=[_action_row("buy-a")]), "buy", [1, 0, 0, 0], [["BUY-A"], [], [], []]),
        (_actions(on_the_run=[_action_row("near-a")]), "near", [0, 1, 0, 0], [[], ["NEAR-A"], [], []]),
        (_actions(buy_soon=[_action_row("wait-a")]), "wait", [0, 0, 1, 0], [[], [], ["WAIT-A"], []]),
        (_actions(avoid=[_action_row("avoid-a")]), "avoid", [0, 0, 0, 1], [[], [], [], ["AVOID-A"]]),
        (
            _actions(
                hold=[_action_row("near-a"), _action_row("near-b")],
                buy_soon=[_action_row("wait-a")],
                take_profits=[_action_row("avoid-a")],
            ),
            "near",
            [0, 2, 1, 1],
            [[], ["NEAR-A", "NEAR-B"], ["WAIT-A"], ["AVOID-A"]],
        ),
        (_actions(), "buy", [0, 0, 0, 0], [[], [], [], []]),
    ),
)
def test_server_elects_and_wires_the_complete_action_selector(
    market: str,
    actions: dict[str, object],
    selected: str,
    counts: list[int],
    identities: list[list[str]],
) -> None:
    """The first frame owns lane order, counts, identity, and deterministic election."""
    soup = _render_action_fixture(market, actions)
    panel = soup.find(id="act-now")
    assert panel is not None
    tabs = panel.select(f"[data-{market}-an-lane]")
    lanes = panel.select("[data-action-lane-body]")
    assert len(tabs) == len(lanes) == 4
    assert [int(tab.select_one("b").get_text(strip=True)) for tab in tabs] == counts
    assert [tab.get("href") for tab in tabs] == [f"#{lane.get('id')}" for lane in lanes]
    assert len({tab.get("href") for tab in tabs}) == 4
    assert not panel.select("[role='tablist'], [role='tab']")
    assert all(not tab.has_attr("aria-selected") for tab in tabs)
    assert all(not tab.has_attr("aria-controls") for tab in tabs)
    assert all(not tab.has_attr("aria-current") for tab in tabs)
    assert [
        tab.get(f"data-{market}-an-default") == "true" for tab in tabs
    ].count(True) == 1
    assert next(
        tab.get(f"data-{market}-an-lane")
        for tab in tabs
        if tab.get(f"data-{market}-an-default") == "true"
    ) == selected
    assert [lane.get("data-action-lane-body") for lane in lanes if "is-current" in lane.get("class", [])] == [selected]
    assert [
        [row.get("data-action-id") for row in lane.select("[data-action-id]")]
        for lane in lanes
    ] == identities
    assert not panel.select(".lst-wrap, .lst-collapse, .lst-more")


@pytest.mark.parametrize(
    ("market", "body_id", "row_class", "hook", "count"),
    (
        ("hk", "hk-v37-an-body", "hk-v37-an-row", "data-hk-lead-id", "2"),
        ("ca", "ca-v36-an-body", "ca-v36-an-row", "data-ca-lead-id", "2"),
    ),
)
def test_static_action_rows_bind_only_identity_proven_membership(
    market: str, body_id: str, row_class: str, hook: str, count: str
) -> None:
    actions = _actions(
        buy_now=[
            _action_row("fixture-sector"),
            _action_row("unknown-sector", "Unknown sector"),
        ]
    )
    soup = _render_action_fixture(market, actions)
    panel = soup.find(id="act-now")
    body = soup.find(id=body_id)
    assert panel is not None and body is not None
    assert panel.get("data-action-owner-state") == "available"
    assert len(body.select(f"[data-{market}-an-lane]")) == 4
    assert len(body.select("[data-action-lane-body]")) == 4

    known = body.select_one(f".{row_class}-w[data-action-id='FIXTURE-SECTOR']")
    unknown = body.select_one(f".{row_class}-w[data-action-id='UNKNOWN-SECTOR']")
    assert known is not None and unknown is not None
    assert known.select_one(f"[{hook}='FIXTURE-SECTOR']") is not None
    assert f"{count} · Prophet" in known.get_text(" ", strip=True)
    assert unknown.select_one(f"[{hook}]") is None
    assert "Prophet" not in unknown.get_text(" ", strip=True)
    route = unknown.find("a", href="sectors/unknown-sector.html")
    assert route is not None


@pytest.mark.parametrize(
    ("market", "selector"),
    (("hk", "#standouts .nbgrid"), ("ca", "#standouts .cards")),
)
def test_canonical_prophet_host_has_one_visibility_owner(
    market: str, selector: str
) -> None:
    """Generic show-more must never hide a card selected by dashboard filters."""
    soup = _render_action_fixture(market, _actions())
    host = soup.select_one(selector)
    assert host is not None
    assert host.get("data-showmore") is None
    assert host.get("data-showmore-rows") is None


def test_canada_static_quote_header_is_neutral_until_quote_plane_confirms() -> None:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    soup = _render_canada_owner_fixture(setups, _actions())
    status = soup.find(id="ca-v36-quote-status")
    assert status is not None
    assert status.get("data-quote-state") == "unavailable"
    copy = status.get_text(" ", strip=True)
    assert "Quotes unavailable" in copy
    assert "LIVE QUOTES" not in copy
    assert status.select_one(".ca-v36-live-dot") is None


def test_canada_quote_plane_requires_complete_typed_dom_receipts() -> None:
    """A header claim is admitted only when every owner card has one valid receipt."""
    text = _read(MARKETS["ca"]["composer"])
    observed = _run_node_function(
        text,
        "quotePlaneState",
        """
function node(stateValue, titleValue) {
  return {getAttribute: function (name) {
    return name === "data-live" ? stateValue : (name === "title" ? titleValue : null);
  }};
}
const cases = [
  [],
  [node(null, null)],
  [node("1", "not a quote receipt")],
  [node("1", "live · FixtureFeed · Sep 5, 10:30 ET")],
  [node("delayed", "≥15-min delayed · Yahoo · 15m ago")],
  [node("stale", "stale · Yahoo · 41m ago")],
  [node("closed", "market closed · Yahoo · 481m ago")],
  [node("1", "live · FixtureFeed · 0m ago"), node(null, null)],
  [node("1", "live · FixtureFeed · 0m ago"), node("stale", "stale · FixtureFeed · 41m ago")]
];
console.log(JSON.stringify(cases.map(quotePlaneState)));
""",
    )
    assert observed == [
        {"state": "unavailable", "detail": ""},
        {"state": "unavailable", "detail": ""},
        {"state": "unavailable", "detail": ""},
        {"state": "live", "detail": "live · FixtureFeed · Sep 5, 10:30 ET"},
        {"state": "delayed", "detail": "≥15-min delayed · Yahoo · 15m ago"},
        {"state": "stale", "detail": "stale · Yahoo · 41m ago"},
        {"state": "closed", "detail": "market closed · Yahoo · 481m ago"},
        {"state": "unavailable", "detail": ""},
        {"state": "unavailable", "detail": ""},
    ]


def test_hk_owner_marker_binds_disjoint_identity_proven_populations() -> None:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    soup = _render_hk_owner_fixture(setups)
    proof = soup.find(id="hk-owner-population-proof")
    assert proof is not None
    assert proof.get("data-owner-board-population") == "39"
    assert proof.get("data-owner-watch-population") == "8"
    assert proof.get("data-owner-unique-population") == "47"


def test_hk_owner_marker_refuses_an_overlapping_owner_union() -> None:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    setups["watch"][0]["ticker"] = setups["buy"][0]["ticker"]
    soup = _render_hk_owner_fixture(setups)
    proof = soup.find(id="hk-owner-population-proof")
    assert proof is not None
    assert proof.get("data-owner-board-population") == "39"
    assert proof.get("data-owner-watch-population") == "8"
    assert proof.get("data-owner-unique-population") is None


def test_hk_owner_marker_rejects_a_duplicate_board_identity() -> None:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    setups["ripening"][0]["ticker"] = setups["buy"][0]["ticker"]
    soup = _render_hk_owner_fixture(setups)
    proof = soup.find(id="hk-owner-population-proof")
    assert proof is not None
    assert proof.get("data-owner-board-population") is None
    assert proof.get("data-owner-watch-population") == "8"
    assert proof.get("data-owner-unique-population") is None


def test_hk_owner_marker_rejects_a_duplicate_watch_identity() -> None:
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    setups["watch"][1]["ticker"] = setups["watch"][0]["ticker"]
    soup = _render_hk_owner_fixture(setups)
    proof = soup.find(id="hk-owner-population-proof")
    assert proof is not None
    assert proof.get("data-owner-board-population") == "39"
    assert proof.get("data-owner-watch-population") is None
    assert proof.get("data-owner-unique-population") is None


def test_hk_owner_marker_requires_every_priority_lane_to_be_explicit() -> None:
    """A missing lane is unknown, not proof that the lane is empty."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("hk")
    setups.pop("ran")
    soup = _render_hk_owner_fixture(setups)
    proof = soup.find(id="hk-owner-population-proof")
    assert proof is not None
    assert proof.get("data-owner-board-population") is None
    assert proof.get("data-owner-watch-population") == "8"
    assert proof.get("data-owner-unique-population") is None


@pytest.mark.parametrize(
    ("owner", "value"),
    (
        ("buy", _MISSING),
        ("buy", None),
        ("buy", "not-a-list"),
        ("buy", {"ticker": "not-a-list"}),
        ("watch", _MISSING),
        ("watch", None),
        ("watch", "not-a-list"),
        ("watch", {"ticker": "not-a-list"}),
    ),
)
def test_canada_static_first_frame_never_coerces_malformed_owner_to_zero(
    owner: str, value: object
) -> None:
    """Missing/null/string/mapping owners render unavailable without exceptions."""
    from scripts.render_stock_dashboard_fixture import load_owner_fixture

    setups, _owner_path = load_owner_fixture("ca")
    setups = dict(setups)
    if value is _MISSING:
        setups.pop(owner)
    else:
        setups[owner] = value
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert f"{owner if owner == 'watch' else 'board'} unavailable" in copy
    assert "17 current names" not in copy
    if owner == "buy":
        assert grid.get("data-owner-population") is None
    else:
        assert grid.get("data-owner-watch-population") is None
    assert grid.get("data-owner-unique-population") is None


@pytest.mark.parametrize("setups", (_MISSING, None))
def test_canada_static_first_frame_missing_setups_is_unavailable(
    setups: object,
) -> None:
    soup = _render_canada_owner_fixture(setups)
    result = soup.find(id="ca-v36-result")
    grid = soup.find(id="ca-v36-card-grid")
    assert result is not None and grid is not None
    copy = result.get_text(" ", strip=True)
    assert "board unavailable" in copy
    assert "watch unavailable" in copy
    assert grid.get("data-owner-population") is None
    assert grid.get("data-owner-watch-population") is None
    assert grid.get("data-owner-unique-population") is None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rendered_fixture_recipe_is_committed_self_binding_and_deterministic(
    tmp_path: Path,
) -> None:
    """Browser inputs reproduce from candidate templates and checked-in fixtures."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    receipts = []
    for out_dir in (first, second):
        receipt = out_dir / "rendered-fixture.json"
        run = subprocess.run(
            [
                sys.executable,
                str(FIXTURE_RECIPE),
                "--market",
                "all",
                "--out-dir",
                str(out_dir),
                "--receipt",
                str(receipt),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        receipts.append(json.loads(receipt.read_text(encoding="utf-8")))

    assert receipts[0] == receipts[1]
    receipt = receipts[0]
    assert receipt == json.loads(_read(EVIDENCE_DIR / "rendered-fixture.json"))
    assert receipt["schema"] == "mastermind.stock_dashboard_rendered_fixture.v1"
    assert receipt["proof_class"] == "rendered_fixture"
    assert receipt["transform"] == (
        "jinja2_candidate_template_render_from_frozen_owner_and_action_fixtures"
    )
    assert receipt["ambient_inputs"] == []
    for market, expected in (("hk", (39, 8, 47)), ("ca", (9, 8, 17))):
        page = first / receipt["markets"][market]["output"]
        assert _sha256(page) == receipt["markets"][market]["output_sha256"]
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        assert len(soup.find_all("main")) == 1
        ids = [node.get("id") for node in soup.find_all(attrs={"id": True})]
        assert len(ids) == len(set(ids)), f"{market}: rendered fixture has duplicate ids"
        assert receipt["markets"][market]["owner_population"] == {
            "board": expected[0],
            "watch": expected[1],
            "intersection": [],
            "unique_total": expected[2],
        }
        if market == "hk":
            all_count = soup.select_one(
                '#hk-stage-filter [data-stagepick="all"] .pbf-n'
            )
            assert all_count is not None and all_count.get_text(strip=True) == "39"
            stage_counts = {
                button["data-stagepick"]: button.select_one(".pbf-n").get_text(
                    strip=True
                )
                for button in soup.select(
                    "#hk-stage-filter [data-stagepick]:not([data-stagepick='all'])"
                )
            }
            assert stage_counts == {
                "live": "2",
                "setting_up": "13",
                "ran": "12",
                "blocked": "12",
            }
        input_paths = {item["path"] for item in receipt["markets"][market]["inputs"]}
        assert f"templates/{'hk' if market == 'hk' else 'canada'}.html.j2" in input_paths
        owner_name = (
            "hk-owner-fixture.json" if market == "hk" else "canada-owner-fixture.json"
        )
        assert (
            f"mockups/evidence/prophet-p0b-zero-fouc/inputs/{owner_name}"
            in input_paths
        )
        action_name = (
            "hk-action-fixture.json"
            if market == "hk"
            else "canada-action-fixture.json"
        )
        assert (
            f"mockups/evidence/prophet-p0b-zero-fouc/inputs/{action_name}"
            in input_paths
        )
        assert not any(path.startswith("site/factordata/") for path in input_paths)
        for item in receipt["markets"][market]["inputs"]:
            assert _sha256(ROOT / item["path"]) == item["sha256"]


@pytest.mark.parametrize(
    ("market", "receipt_name", "composer"),
    (
        ("hk", "mobile-layout.json", "hk-stock-v36.js"),
        ("ca", "mobile-layout-canada.json", "canada-stock-v36.js"),
    ),
)
def test_committed_browser_receipts_are_self_binding_fixture_proof(
    market: str, receipt_name: str, composer: str
) -> None:
    """Each checked-in browser claim binds bytes, assets, tool, and lineage."""
    fixture = json.loads(
        _read(EVIDENCE_DIR / "rendered-fixture.json")
    )
    browser = json.loads(_read(EVIDENCE_DIR / receipt_name))
    assert browser["proof_class"] == "browser_fixture_proof_reproducible"
    assert browser["claims"] == {
        "source_contract": "browser_fixture",
        "browser_fixture": "reproducible",
        "canonical_build": "unavailable",
        "production": "none",
    }
    assert browser["fixture_market"] == market
    assert browser["verifier"] == {
        "path": "scripts/verify_stock_dashboard_mobile_layout.cjs",
        "sha256": _sha256(BROWSER_RECEIPT),
    }
    assert browser["fixture_receipt"]["sha256"] == _sha256(
        EVIDENCE_DIR / "rendered-fixture.json"
    )
    assert browser["fixture_assets_root"] == (
        "mockups/evidence/prophet-p0b-zero-fouc/inputs/browser-data"
    )
    assert browser["input_html"]["sha256"] == fixture["markets"][market]["output_sha256"]
    template = "hk.html.j2" if market == "hk" else "canada.html.j2"
    assert browser["construction_inputs"][f"templates/{template}"] == _sha256(
        ROOT / "templates" / template
    )
    for relative, digest in browser["loaded_assets"].items():
        assert _sha256(ROOT / relative) == digest
    assert browser["loaded_assets"]["site/stock-dashboard.css"] == _sha256(
        ROOT / "site" / "stock-dashboard.css"
    )
    assert browser["loaded_assets"][f"site/{composer}"] == _sha256(
        ROOT / "site" / composer
    )
    action_fixture = (
        "hk-action-fixture.json"
        if market == "hk"
        else "canada-action-fixture.json"
    )
    action_path = (
        "mockups/evidence/prophet-p0b-zero-fouc/inputs/" + action_fixture
    )
    assert browser["construction_inputs"][action_path] == _sha256(
        ROOT / action_path
    )
    frozen_requests = {
        "canadabasketdata/baskets.json",
        "canadabasketdata/sector_pulse_canada.json",
        "live/overlay.json",
        "live/quotes.json",
        "marketdata/rotation_events_hk.json",
    }
    assert not frozen_requests.intersection(
        path.removeprefix("site/") for path in browser["loaded_assets"]
    )
    loaded_fixture_assets = {
        str((ROOT / path).relative_to(FIXTURE_ASSETS))
        for path in browser["loaded_assets"]
        if (ROOT / path).is_relative_to(FIXTURE_ASSETS)
    }
    expected_frozen_assets = {
        "hk": {
            "live/overlay.json",
            "live/quotes.json",
            "marketdata/rotation_events_hk.json",
        },
        "ca": {
            "canadabasketdata/baskets.json",
            "canadabasketdata/sector_pulse_canada.json",
            "live/overlay.json",
            "live/quotes.json",
        },
    }
    assert loaded_fixture_assets == expected_frozen_assets[market]
    assert {row["state"] for row in browser["states"]} >= {
        "en-dark",
        "en-light",
        "zh-dark",
        "zh-light",
        "js-disabled",
        "composer-failed",
        "composer-pending",
    }
    assert browser["pass"] is True
    assert all(row["pass"] and row["behavior"]["pass"] for row in browser["states"])
    expected_initial_source = "all" if market == "hk" else "top"
    states = {row["state"]: row for row in browser["states"]}
    for row in states.values():
        behavior = row["behavior"]
        source = behavior["source_contract"]
        assert source["pass"] is True
        assert source["initial_source"] == expected_initial_source
        assert source["active_source"] == expected_initial_source
        assert source["selected_source"] == expected_initial_source
        assert source["visible_grid"] == source["expected_grid"]
        assert "actionable cards shown" in source["result_copy"]
        assert "current names" in source["result_copy"]
        assert behavior["prophet_chrome"] == {
            "title_count": 1,
            "result_count": 1,
            "owner_context_count": 1,
            "vintage_count": 1,
            "help_count": 1,
            "legacy_view_count": 0,
            "pass": True,
        }
        view_owner = behavior["view_owner"]
        assert view_owner["control_count"] == 1
        assert view_owner["button_count"] == 2
        assert view_owner["selected"] == "grid"
        assert view_owner["pass"] is True

        wtaon = behavior["wtaon"]
        assert wtaon["selected_lane_key"] == "buy"
        assert wtaon["button_count"] == 4
        assert wtaon["visible_lane_body_count"] == 1
        assert set(wtaon["per_lane_owner_count"]) == {"buy", "near", "wait", "avoid"}
        assert wtaon["rendered_visible_row_count"] >= 0
        assert isinstance(wtaon["expanded"], bool)
        loaded = row["composer"] == "loaded" and row["javascript_enabled"] is True
        assert wtaon["enhanced"] is loaded
        assert wtaon["selector_count"] == (1 if loaded else 0)
        assert wtaon["aria_controls"] == (
            {"unique": 4, "valid": True}
            if loaded
            else {"unique": 0, "valid": False}
        )
        hashes = wtaon["identity_hashes"]
        assert re.fullmatch(r"[0-9a-f]{64}", hashes["before"])
        assert hashes["after"] == hashes["before"]
        identity = wtaon["node_identity"]
        assert identity["pass"] is True
        if row["javascript_enabled"]:
            assert identity["captured"] is True
            assert identity["captured_before_composer"] is True
            assert identity["same_host"] is True
            assert identity["same_controls"] is True
            assert identity["same_lanes"] is True
            assert identity["same_lists"] is True
            assert identity["same_rows"] is True
            assert identity["child_list_mutations"] == 0
            assert identity["payload_hash_after"] == identity["payload_hash_before"]
        else:
            assert identity == {
                "captured": False,
                "reason": "javascript_disabled",
                "pass": True,
            }
        assert wtaon["pass"] is True

    for name in ("en-dark", "en-light", "zh-dark", "zh-light"):
        keyboard = states[name]["behavior"]["wtaon"]["focus_keyboard"]
        assert keyboard["exercised"] is True
        assert keyboard["pass"] is True
        assert keyboard["sequence"] == ["near", "avoid", "buy", "avoid", "wait"]
        assert keyboard["focus_visible"] == [True, True, True, True, True]

    for name in ("js-disabled", "composer-failed", "composer-pending"):
        behavior = states[name]["behavior"]
        wtaon = behavior["wtaon"]
        assert wtaon["focus_keyboard"]["exercised"] is False
        assert wtaon["focus_keyboard"]["focus_visible"] == []
        assert wtaon["expanded"] is False
        fallback = behavior["static_anchor_fallback"]
        assert fallback["pass"] is True
        assert [case["lane"] for case in fallback["cases"]] == [
            "buy", "near", "wait", "avoid"
        ]
        assert all(case["pass"] for case in fallback["cases"])
        assert all(case["enhanced"] is False for case in fallback["cases"])
        assert all(case["highlighted_control"] == case["lane"] for case in fallback["cases"])
        assert all(case["owner_count"] == case["owner_row_count"] for case in fallback["cases"])
        assert all(case["semantics"]["container_role"] is None for case in fallback["cases"])
        assert all(
            all(value is None for value in case["semantics"][field])
            for case in fallback["cases"]
            for field in ("tab_roles", "aria_selected", "aria_current", "aria_controls")
        )

    fragment = browser["fragment_navigation"]
    assert fragment["pass"] is True
    assert [case["label"] for case in fragment["cases"]] == [
        "direct-valid", "click-with-fragment", "second-click", "back", "forward", "direct-invalid"
    ]
    assert all(case["pass"] for case in fragment["cases"])
    assert fragment["console_exceptions"] == []
    assert fragment["node_identity"]["valid_page"]["pass"] is True
    assert fragment["node_identity"]["invalid_page"]["pass"] is True

    expansion = browser["expansion_reachability"]
    assert expansion["pass"] is True
    assert expansion["expected_cases"] == 8
    assert expansion["passed_cases"] == 8
    assert len(expansion["cases"]) == 8
    assert {
        (case["viewport_width"], case["mode"])
        for case in expansion["cases"]
    } == {
        (width, mode)
        for width in (390, 1440)
        for mode in ("js-disabled", "composer-failed", "composer-pending", "loaded")
    }
    for case in expansion["cases"]:
        assert case["market"] == market
        assert case["pass"] is True
        assert case["console_exceptions"] == []
        for phase, visible, opened in (
            ("before", 3, False),
            ("after_click", 4, True),
            ("after_click_close", 3, False),
            ("after_enter", 4, True),
            ("after_enter_close", 3, False),
            ("after_space", 4, True),
        ):
            observed = case[phase]
            assert observed["total"] == 4
            assert observed["visible"] == visible
            assert observed["rich_rows"] == 4
            assert observed["disclosure_count"] == 1
            assert observed["disclosure_open"] is opened
            assert observed["summary_tag"] == "SUMMARY"
            assert observed["other_open_count"] == 0
            assert observed["same_lane"] is True
            assert observed["same_disclosure"] is True
            assert observed["same_summary"] is True
            assert observed["same_rows"] is True
            assert observed["same_payload"] is True
            assert observed["child_list_mutations"] == 0
            assert observed["document_width"] <= observed["viewport_width"]
            if phase != "before":
                assert observed["focus_on_summary"] is True

    for name in ("en-dark", "en-light", "zh-dark", "zh-light"):
        ownership = states[name]["behavior"]["view_all"]["ownership"]
        assert ownership == {
            "same_summary": True,
            "same_disclosure": True,
            "same_list": True,
            "same_parent": True,
            "focus_retained": True,
            "disclosure_stayed_in_lane": True,
            "list_stayed_in_lane": True,
            "global_overlay_count": 0,
        }

    disabled_view = states["js-disabled"]["behavior"]["view_owner"]
    assert disabled_view["stocktable_ready"] is False
    assert disabled_view["table_disabled"] is True
    failed_transition = states["composer-failed"]["behavior"]["view_transition"]
    assert failed_transition["pass"] is True
    assert failed_transition["visible_table"] == failed_transition["expected"]
    assert failed_transition["selected_view"] == "table"
    assert failed_transition["owner_active_view"] == "table"
    assert failed_transition["grid_restored"] is True

    desktop = browser["desktop"]
    assert desktop["pass"] is True
    assert desktop["initial"]["action_panel_height"] <= 240
    assert desktop["initial"]["prophet_top"] < 900
    assert desktop["initial"]["visible_lane_count"] == 4
    assert max(desktop["initial"]["lane_rows"].values()) <= 3
    assert desktop["initial"]["generic_showmore_attribute"] is False
    assert desktop["initial"]["generic_showmore_bar_count"] == 0
    assert desktop["initial"]["initial_source"] == expected_initial_source
    assert desktop["initial"]["selected_source"] == expected_initial_source
    assert desktop["initial"]["source_manifest"]["pass"] is True
    assert desktop["initial"]["source_manifest"]["visible"] == (
        desktop["initial"]["source_manifest"]["expected"]
    )
    assert desktop["initial"]["title_count"] == 1
    assert desktop["initial"]["result_count"] == 1
    assert desktop["initial"]["owner_context_count"] == 1
    assert desktop["initial"]["vintage_count"] == 1
    assert desktop["initial"]["help_count"] == 1
    assert desktop["initial"]["view_control_count"] == 1
    assert desktop["initial"]["legacy_view_count"] == 0
    sequence = {row["label"]: row for row in desktop["sequence"]}
    assert set(sequence) == {
        "initial-table",
        "persisted-table-startup",
        "top-grid",
        "top-table",
        "all-grid",
        "all-table",
        "group",
        "clear",
        "resized-390",
        "resized-1440",
        "legacy-class-healed",
    }
    assert all(row["pass"] for row in sequence.values())
    assert sequence["persisted-table-startup"]["persisted_view"] == "table"
    for source_name in ("top", "all"):
        grid = sequence[f"{source_name}-grid"]
        table = sequence[f"{source_name}-table"]
        assert grid["source"] == source_name
        assert table["source"] == source_name
        assert grid["visible"] == grid["expected"]
        assert table["visible"] == table["expected"]
        assert table["visible_table"] == table["expected"]
        assert grid["owner_active_view"] == "grid"
        assert table["owner_active_view"] == "table"
        assert grid["view_control_count"] == 1
        assert table["view_control_count"] == 1
    assert sequence["group"]["source_unchanged"] is True
    assert len(sequence["group"]["visible"]) == 2
    assert sequence["legacy-class-healed"]["selected_sm_hidden"] == []
    assert sequence["legacy-class-healed"]["animation_delay_residue"] is False
    if market == "ca":
        quote_cases = {row["name"]: row for row in desktop["quote_cases"]}
        expected_quote_states = {
            "missing": "unavailable",
            "malformed": "unavailable",
            "live": "live",
            "delayed": "delayed",
            "stale": "stale",
            "closed": "closed",
        }
        assert {
            name: quote_cases[name].get("state")
            for name in expected_quote_states
        } == expected_quote_states
        assert all(row["pass"] for row in quote_cases.values())
    degraded = {
        row["state"]: row["screenshot"]
        for row in browser["states"]
        if row["state"] in {"js-disabled", "composer-failed"}
    }
    assert set(degraded) == {"js-disabled", "composer-failed"}
    for screenshot in degraded.values():
        assert _sha256(ROOT / screenshot["path"]) == screenshot["sha256"]


def test_visual_manifest_names_fixture_only_provenance() -> None:
    """The 16-cell capture cannot be mistaken for a canonical or live build."""
    fixture_path = EVIDENCE_DIR / "rendered-fixture.json"
    fixture = json.loads(_read(fixture_path))
    manifest = json.loads(_read(EVIDENCE_DIR / "manifest.json"))
    smells = json.loads(_read(EVIDENCE_DIR / "ux-smells.json"))
    target = manifest["target"]
    assert target["kind"] == "rendered_fixture"
    assert target["proof_class"] == "browser_fixture_proof_reproducible"
    assert target["canonical_build_proof"] == "unavailable"
    assert target["production_proof"] == "none"
    assert target["fixture_receipt"] == {
        "path": "mockups/evidence/prophet-p0b-zero-fouc/rendered-fixture.json",
        "sha256": _sha256(fixture_path),
    }
    assert {
        route: row["sha256"]
        for route, row in target["rendered_pages"].items()
    } == {
        spec["route"]: spec["output_sha256"]
        for spec in fixture["markets"].values()
    }
    assert smells["target"] == target
    assert manifest["totals"] == {
        "pages": 2,
        "states_attempted": 16,
        "states_captured": 16,
    }
    for page in manifest["pages"]:
        for state in page["states"]:
            screenshot = EVIDENCE_DIR / state["file"]
            assert screenshot.is_file()
            assert _sha256(screenshot) == state["sha256"]


@pytest.mark.parametrize(
    ("market", "cases", "expected"),
    (
        (
            "hk",
            [
                [3, 39, 8, 47],
                [3, 39, 8, None],
                [3, None, 8, None],
                [3, None, None, None],
                [0, 0, 8, 8],
            ],
            [
                "3 actionable cards shown · 47 current names (39 stage board + 8 watch)",
                "3 actionable cards shown · 39 stage-board names · 8 watch names · unique total unavailable",
                "3 actionable cards shown · stage board unavailable · 8 watch names",
                "3 actionable cards shown · stage board unavailable · watch unavailable",
                "0 actionable cards shown · 8 current names (0 stage board + 8 watch)",
            ],
        ),
        (
            "ca",
            [
                [3, 9, 8, 17],
                [3, 9, 8, None],
                [3, None, 8, None],
                [3, None, None, None],
                [0, 0, 8, 8],
            ],
            [
                "3 actionable cards shown · 17 current names (9 stage board + 8 watch)",
                "3 actionable cards shown · 9 stage-board names · 8 watch names · unique total unavailable",
                "3 actionable cards shown · stage board unavailable · 8 watch names",
                "3 actionable cards shown · stage board unavailable · watch unavailable",
                "0 actionable cards shown · 8 current names (0 stage board + 8 watch)",
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
