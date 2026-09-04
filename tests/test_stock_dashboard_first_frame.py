"""P0B zero-FOUC contracts for the HK and Canada stock dashboards.

The templates are the deployable source of the canonical ``<main>`` and its
ordered landmarks.  The checked-in generated artifacts remain the owner-data
baseline used to pin population/equation truth; a real generator run and browser
matrix provide the rendered proof for each delivery candidate.

The composer checks below are narrow architecture bans.  Semantic composer tests
remain in their market-specific suites; this file only prevents a return to the
superseded second-page/mounted-class/owner-node-migration design.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]

MARKETS = {
    "hk": {
        "page": ROOT / "site" / "hk_stocks.html",
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
        "page": ROOT / "site" / "canada_stocks.html",
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


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(_read(path), "html.parser")


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


@pytest.mark.parametrize("market", MARKETS)
def test_zero_cards_do_not_abort_static_shell_enhancement(market: str) -> None:
    text = _read(MARKETS[market]["composer"])
    start = re.search(r"function start\b.*?(?=\n  if \(document\.readyState)", text, re.S)
    assert start
    assert "if (!state.cards.length) return" not in start.group(0)


def test_hk_static_shell_preserves_full_owner_stage_equation() -> None:
    """The generated owner baseline pins the complete protected population.

    Static-shell ownership is asserted against the deployable template above.
    The checked-in page can legitimately lag that source between publish runs,
    so this assertion reads only its owner data and never treats generated HTML
    as a second source of shell authority.
    """
    soup = _soup(MARKETS["hk"]["page"])
    bar = soup.find(id="hk-stage-filter")
    assert bar is not None
    counts = {
        button.get("data-stagepick"): int(button.find(class_="pbf-n").get_text(strip=True))
        for button in bar.find_all("button", attrs={"data-stagepick": True})
    }
    assert set(counts) >= {"all", "live", "setting_up", "ran", "blocked"}
    assert counts == {
        "all": 39,
        "live": 2,
        "setting_up": 13,
        "ran": 12,
        "blocked": 12,
    }
    assert counts["all"] == sum(
        counts[key] for key in ("live", "setting_up", "ran", "blocked")
    )
    owner_cards = soup.select("#standouts .pvcard")
    assert counts["all"] > len(owner_cards), (
        "the canonical shell collapsed the full owner population to the "
        ".pvcard subset harvested by the old composer"
    )
    stage_surfaces = Counter(
        node.get("data-stage")
        for node in soup.select(
            "#standouts .nb-stage-hd[data-stage], "
            "#standouts .pbr[data-stage], "
            "#standouts .pbv[data-stage]"
        )
    )
    assert all(
        stage_surfaces[key] >= 1
        for key in ("live", "setting_up", "ran", "blocked")
    )


def test_canada_static_shell_preserves_owner_board_population() -> None:
    """The generated owner baseline keeps row/card membership identical."""
    soup = _soup(MARKETS["ca"]["page"])
    payload = soup.find("script", id="stocktable-data")
    assert payload is not None
    rows = json.loads(payload.string or "{}").get("rows", [])
    cards = soup.select("#standouts .pvcard")
    assert rows, "Canada owner board unexpectedly rendered zero rows"
    assert len(rows) == len(cards), (
        "Canada static composition changed owner membership between serialized "
        "table rows and rendered cards"
    )
    groups = Counter(row.get("group") for row in rows)
    assert sum(groups.values()) == len(rows)


@pytest.mark.parametrize("market", MARKETS)
def test_generated_ids_remain_unique_after_static_composition(market: str) -> None:
    soup = _soup(MARKETS[market]["page"])
    ids = [node.get("id") for node in soup.find_all(attrs={"id": True})]
    duplicates = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
    assert not duplicates, f"{market}: duplicate generated ids: {duplicates}"
