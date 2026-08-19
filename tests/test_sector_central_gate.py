"""Tier-preview gate for the Act-Now board on sector_central.html.

WHY THIS SUITE EXISTS. `templates/_us_act_now_board.html.j2` is a SHARED include:
`scripts/build_site.py` renders it on us_stocks.html and
`scripts/build_sector_central.py` renders it here, reading the board back off
`site/basketdata/action_board.json`. PR #5846 gave the include its three-shape
split (full / gated shell / rows-only) and gated the us_stocks host — which
removed those rows from THAT page's bytes and left them fully readable one click
away on this one. Measured anonymously on the live site 2026-08-17:

    curl -s https://www.mastermind-x.com/sector_central.html | grep -c 'class="actitem'
    -> 45          (and NO tier_preview.js on the page at all, so not even the
                    client-side overlay us_stocks had before its gate)

So the regression this suite pins is not "the gate is missing" — it is the more
expensive shape: a page gated on ONE host while a second host serves the same
rows whole. Every test below is about the SPLIT (docs/TIER_PREVIEW_PATTERN.md):
the shell must not contain what the payload contains, the free half must keep
honest totals, and flipping the switch off must return the page byte-for-byte.

IMPORT-LIGHT ON PURPOSE. scripts/build_sector_central.py keeps every engine
import inside a function, so this suite needs only jinja2 + pyyaml and runs in
the `tier-gate` job beside the other gate suites. test_import_stays_light pins
that: a module-scope pandas/plotly import creeping in here would not fail the
suite, it would make it SKIP everywhere, which is how a gate test goes dark.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEMPLATES = ROOT / "templates"
BOARD_TPL = TEMPLATES / "_us_act_now_board.html.j2"
PAGE_TPL = TEMPLATES / "sector_central.html.j2"

pytest.importorskip("jinja2")
import jinja2  # noqa: E402

from scripts.build_sector_central import (  # noqa: E402
    _ACTNOW_LANES,
    _SC_PAYLOAD_URL,
    _gate_cfg,
    split_actnow,
    write_payload,
)

#: Row counts per lane for the fixture board. Deliberately mixed: `on_the_run`
#: sits UNDER the preview cap (it must ship whole — a wall over two rows is
#: worse than no wall), and hold+avoid share one .actbody so their combined
#: preview has to equal every other lane's.
LANE_SIZES = {"buy_now": 7, "buy_soon": 5, "on_the_run": 2,
              "take_profits": 9, "hold": 4, "avoid": 6}
PREVIEW = 3


def _board(sizes: dict | None = None) -> dict:
    """A five-lane board whose every row is identifiable by a UNIQUE token.

    That token is the DISPLAY NAME, and the choice is load-bearing. A `kind:
    theme` row prints neither its ticker nor its slug — only its name — so a
    ticker-keyed leak check would pass over every theme row on the board (two of
    the five lanes here), which is a gate test that cannot see half the leak it
    exists to catch. `dispshort()` abbreviates a handful of real sector names, so
    the fixture stays clear of them.
    """
    sizes = LANE_SIZES if sizes is None else sizes
    out = {}
    for lane, n in sizes.items():
        kind = "theme" if lane in ("buy_soon", "hold") else "sector"
        out[lane] = [{"kind": kind, "ticker": f"TK{lane}{i}".upper(),
                      "name": f"Zrow {lane} {i}", "slug": f"sc-{lane}-{i}"}
                     for i in range(n)]
    return out


def _tokens(board: dict) -> dict:
    """lane key -> [unique display token per row], in board order."""
    return {k: [r["name"] for r in v] for k, v in board.items()}


def _env() -> "jinja2.Environment":
    # autoescape=True mirrors scripts/build_sector_central.py's env exactly; the
    # shell and the payload must be rendered by the SAME env or the two halves
    # can escape identical content differently.
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals.update(td=lambda en: en, tr=lambda en: en,
                       t=lambda en, zh="": en)
    return env


def _render_board(board: dict, pgate=None, locked=None) -> str:
    kw = {"action_board": board}
    if pgate is not None:
        kw["pgate"] = pgate
    if locked is not None:
        kw["ab_locked"] = locked
    return _env().get_template(BOARD_TPL.name).render(**kw)


def _render_page(board: dict, pgate="__absent__") -> str:
    kw = dict(flows_html=None, bottoming=None, theme_context=None,
              factor_season=None, flow=None, basket_member_syms=[],
              action_board=board, generated_utc="2026-08-18T00:00:00Z")
    if pgate != "__absent__":
        kw["pgate"] = pgate
    return _env().get_template(PAGE_TPL.name).render(**kw)


def _rows(html: str) -> int:
    """Board rows actually in the document. `class="actitem` and not the bare
    substring: the include ships its own <style> whose selectors mention
    `.actitem` too, and counting those inflates every figure here by ~16."""
    return html.count('class="actitem')


def _present(token: str, html: str) -> bool:
    return re.search(r"\b" + re.escape(token) + r"\b", html) is not None


# ── the split itself ─────────────────────────────────────────────────────────

def test_split_withholds_everything_past_the_preview_and_nothing_else():
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    assert pgate is not None
    got = {}
    for lane in locked:
        got.setdefault(lane["lane"], []).extend(r["name"] for r in lane["rows"])
    tok = _tokens(board)
    # Four independent lanes: everything past row 3 is withheld, in order.
    assert got["ab-buy-fold"] == tok["buy_now"][PREVIEW:]
    assert got["ab-soon-fold"] == tok["buy_soon"][PREVIEW:]
    assert got["ab-trim-fold"] == tok["take_profits"][PREVIEW:]
    # `on_the_run` has 2 rows, under the cap -> it must not appear at all.
    assert "ab-run-fold" not in got
    # Stand aside is ONE .actbody: hold spends the budget first, avoid takes the
    # remainder, so exactly PREVIEW rows survive across BOTH arrays.
    assert got["dash-hold-fold"] == tok["hold"][PREVIEW:] + tok["avoid"]
    assert pgate["actnow"]["total"] == sum(LANE_SIZES.values())
    assert pgate["actnow"]["locked"] == sum(len(v) for v in got.values())
    assert pgate["payload"] == _SC_PAYLOAD_URL
    assert pgate["tier"] == "essential"


def test_stand_aside_preview_equals_every_other_lane():
    """hold+avoid feed one .actbody, so a naive per-array cap would show 6 rows
    there and 3 everywhere else — twice the free product on the one lane whose
    rows are the reduce-side read."""
    board = _board({"hold": 1, "avoid": 9})
    pgate, locked = split_actnow(board, PREVIEW)
    withheld = sum(len(L["rows"]) for L in locked)
    assert (1 + 9) - withheld == PREVIEW


def test_ungated_and_small_boards_withhold_nothing():
    board = _board()
    assert split_actnow(board, PREVIEW, gated=False) == (None, [])
    assert split_actnow(None, PREVIEW) == (None, [])
    # Every lane at or under the cap -> no gate at all, not an empty gate.
    assert split_actnow(_board({"buy_now": 3, "hold": 2}), PREVIEW) == (None, [])


def test_gate_cfg_reads_config_yml_and_is_fail_soft(monkeypatch):
    cfg = _gate_cfg()
    assert cfg["gated"] is True, "config.yml sector_central_gate.gated must ship on"
    assert cfg["preview_rows"] >= 1
    import scripts.build_sector_central as B

    def boom():
        raise RuntimeError("no config")

    monkeypatch.setattr(B.config, "load", boom)
    # Fail-soft in the SAFE direction for this builder: it is additive-and-never-
    # fatal, so an unreadable switch must not crash the page. It re-opens the
    # board, which is the pre-gate behaviour and visible, not silent.
    assert B._gate_cfg() == {"gated": False, "preview_rows": 3}


# ── the shell must not contain what the payload contains ─────────────────────

def test_shell_holds_only_the_preview_rows_and_no_withheld_row():
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    shell = _render_board(board, pgate=pgate)
    withheld = [r["name"] for L in locked for r in L["rows"]]
    leaked = [tk for tk in withheld if _present(tk, shell)]
    assert leaked == [], f"withheld rows still in the free shell: {leaked}"
    assert _rows(shell) == sum(LANE_SIZES.values()) - len(withheld)


def test_the_leak_check_can_actually_see_a_withheld_row():
    """Mutation guard for the assertion above. If `_present` or the fixture ever
    stops being able to find a row, the leak test passes on an OPEN board — the
    exact silent-green shape a gate test must not have."""
    board = _board()
    _, locked = split_actnow(board, PREVIEW)
    ungated_shell = _render_board(board)          # the pre-gate page, all rows
    withheld = [r["name"] for L in locked for r in L["rows"]]
    assert withheld, "fixture withholds nothing — the leak test proves nothing"
    assert all(_present(tk, ungated_shell) for tk in withheld)


def test_payload_carries_exactly_the_withheld_rows_and_no_chrome():
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    payload = _render_board(board, locked=locked)
    withheld = [r["name"] for L in locked for r in L["rows"]]
    assert _rows(payload) == len(withheld)
    assert all(_present(tk, payload) for tk in withheld)
    # Rows only. CSS, panel chrome and lane headings are not withheld content,
    # and shipping them here would paint a second board over the first.
    for chrome in ("<style", "actcol", "acth-name", "actiongrid"):
        assert chrome not in payload, f"payload carries page chrome: {chrome}"


def test_payload_groups_rows_by_the_actbody_they_came_from():
    board = _board()
    _, locked = split_actnow(board, PREVIEW)
    payload = _render_board(board, locked=locked)
    lanes = re.findall(r'data-ab-lane="([^"]+)"', payload)
    assert lanes == [L["lane"] for L in locked]
    # The stand-aside lane's TS-R5 wrapper is part of the row's contract (the
    # client-side auto-expand queries it), not decoration.
    assert 'data-theme-id="sc-hold-3"' in payload


def test_lane_ids_exist_in_the_template_that_owns_them():
    src = BOARD_TPL.read_text(encoding="utf-8")
    for _key, dest, _wrap in _ACTNOW_LANES:
        assert f'id="{dest}"' in src, (
            f"{dest} is not an .actbody id in {BOARD_TPL.name} — hydration would "
            f"drop that lane's rows on the floor")


def test_lane_table_matches_build_sites_copy():
    """The two hosts split the same board, so their lane tables must agree.
    Parsed, not imported: scripts/build_site.py pulls plotly at module scope."""
    tree = ast.parse((ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8"))
    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_US_ACTNOW_LANES"
                for t in node.targets):
            found = ast.literal_eval(node.value)
    assert found is not None, "_US_ACTNOW_LANES vanished from scripts/build_site.py"
    assert [tuple(x) for x in found] == [tuple(x) for x in _ACTNOW_LANES]


# ── what the free reader keeps ───────────────────────────────────────────────

def test_lane_headings_keep_the_true_full_board_counts():
    """State and totals are free; names are paid. A heading that shrinks to the
    preview size tells a Free reader the board is small instead of gated."""
    board = _board()
    pgate, _ = split_actnow(board, PREVIEW)
    shell = _render_board(board, pgate=pgate)
    full = _render_board(board)
    for lane, cls in (("buy_now", "act-buy"), ("buy_soon", "act-soon"),
                      ("take_profits", "act-trim")):
        head = lambda h: h.split(f'class="actcol {cls}"')[1][:900]  # noqa: E731
        assert f">{LANE_SIZES[lane]}<" in head(shell), lane
        assert f">{LANE_SIZES[lane]}<" in head(full), lane


def test_every_withholding_lane_discloses_how_many_are_missing():
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    shell = _render_board(board, pgate=pgate)
    # One line per withholding .actbody (stand aside's two groups share one).
    assert shell.count('class="pg-more"') == len({L["lane"] for L in locked})
    assert "plans.html" in shell
    for n in (LANE_SIZES["buy_now"] - PREVIEW, LANE_SIZES["take_profits"] - PREVIEW):
        assert f"{n} more here" in shell


def test_fold_buttons_are_suppressed_while_gated():
    """A "Show more (N)" control over rows that are not in the document is a
    control over nothing — and its N would state the withheld count out loud in
    a place the reader can click."""
    board = _board()
    pgate, _ = split_actnow(board, PREVIEW)
    assert 'class="lst-more' not in _render_board(board, pgate=pgate)
    assert 'class="lst-more' in _render_board(board)


# ── the page ─────────────────────────────────────────────────────────────────

def test_gated_page_ships_the_hydrate_script_and_the_payload_url():
    board = _board()
    pgate, _ = split_actnow(board, PREVIEW)
    page = _render_page(board, pgate=pgate)
    assert _SC_PAYLOAD_URL in page
    assert "data-ab-lane" in page          # the hydrate loop
    assert '"tier_payload.v1"' in page or "tier_payload.v1" in page
    assert "sector_central" in page
    assert ".pg-more {" in page            # the disclosure line's styling
    # The board's own rows are the only thing gated; the page still renders.
    assert _rows(page) == _rows(_render_board(board, pgate=pgate))


def test_hydrate_script_targets_this_pages_payload_not_us_stocks():
    """Both pages render the same include in the same rows-only shape, so a
    copied hydrate that accepted `page: 'us_stocks'` would happily paint the
    OTHER page's board — built at a different time from a different generation."""
    src = PAGE_TPL.read_text(encoding="utf-8")
    assert "us_stocks.json" not in src
    assert "payload.page !== 'sector_central'" in src


def test_ungated_page_is_byte_identical_to_a_page_that_never_had_a_gate():
    """Flipping sector_central_gate.gated to false must be a true revert, not a
    page that merely looks the same — otherwise the switch cannot be trusted in
    an incident."""
    board = _board()
    assert _render_page(board) == _render_page(board, pgate=None)
    assert _rows(_render_page(board)) == sum(LANE_SIZES.values())
    for marker in (_SC_PAYLOAD_URL, "data-ab-lane", ".pg-more {"):
        assert marker not in _render_page(board), marker


# ── the payload file + the policy that gates it ──────────────────────────────

def test_payload_is_written_even_when_nothing_is_withheld(tmp_path):
    """An unwritten payload is not a no-op: it leaves YESTERDAY's rows on disk
    for a paying reader to hydrate onto a board that no longer holds them."""
    write_payload(_env(), tmp_path, None, [], _board(), built="2026-08-18")
    doc = json.loads((tmp_path / "premiumdata" / "sector_central.json").read_text())
    assert doc["schema"] == "tier_payload.v1"
    assert doc["page"] == "sector_central"
    assert doc["gated"] is False
    assert "actnow_html" not in doc


def test_written_payload_matches_the_shell_it_was_split_from(tmp_path):
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    write_payload(_env(), tmp_path, pgate, locked, board, built="2026-08-18")
    doc = json.loads((tmp_path / "premiumdata" / "sector_central.json").read_text())
    assert doc["gated"] is True
    assert doc["required_tier"] == "essential"
    assert doc["panels"]["actnow"] == pgate["actnow"]
    shell = _render_board(board, pgate=pgate)
    assert _rows(doc["actnow_html"]) + _rows(shell) == sum(LANE_SIZES.values())


def test_a_failing_payload_render_never_aborts_the_build(tmp_path, monkeypatch):
    board = _board()
    pgate, locked = split_actnow(board, PREVIEW)
    env = _env()
    monkeypatch.setattr(env, "get_template",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    write_payload(env, tmp_path, pgate, locked, board, built="x")
    doc = json.loads((tmp_path / "premiumdata" / "sector_central.json").read_text())
    # Rows stay withheld — which is what a locked reader sees anyway — and the
    # page still ships. The failure is loud in the log, not in the exit code.
    assert doc["actnow_html"] == ""


def test_the_payload_prefix_is_enforced_early():
    """Gating the page is theatre if the payload is anonymously fetchable.
    /premiumdata/ must stay under premium.enforced_early, which app/paywall.py
    honours regardless of PAYWALL_ENABLED."""
    yaml = pytest.importorskip("yaml")
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    prefixes = (((policy or {}).get("premium") or {}).get("enforced_early") or {}).get("prefixes") or []
    assert "/premiumdata/" in prefixes
    assert _SC_PAYLOAD_URL.startswith("premiumdata/")
    # And the board's OTHER machine-readable copy stays gated too: gating the
    # page while basketdata/action_board.json answers anonymously would move the
    # same rows one fetch away instead of one click.
    pub = ((policy or {}).get("public") or {})
    assert "/basketdata/action_board.json" not in (pub.get("exact") or [])
    assert not any((pub.get("prefixes") or []) and p == "/basketdata/" for p in (pub.get("prefixes") or []))


def test_import_stays_light():
    """A module-scope pandas/plotly import in build_sector_central would not fail
    this suite — it would make the whole gate SKIP in the import-light lane."""
    src = (ROOT / "scripts" / "build_sector_central.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top = {n.module.split(".")[0] for n in tree.body
           if isinstance(n, ast.ImportFrom) and n.module}
    top |= {a.name.split(".")[0] for n in tree.body
            if isinstance(n, ast.Import) for a in n.names}
    heavy = top & {"pandas", "numpy", "plotly", "pyarrow", "engine", "collectors"}
    assert not heavy, f"module-scope heavy imports would dark this suite: {heavy}"
