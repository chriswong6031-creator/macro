"""The us_stocks.html tier gate — the split IS the boundary.

Before this fix, us_stocks.html server-rendered ALL of us_standouts.buy into
#us-stocktable-data (a JSON <script> block) and the .nbgrid card grid, while
templates/tier_preview.js only capped rows CLIENT-SIDE (anon=1, free=3). Every
row — ticker, conviction score, alpha, entry status, the whole ranked board —
was one view-source away from an anonymous visitor. docs/TIER_PREVIEW_PATTERN.md
is explicit: "Hiding rows with CSS or a JS tier check is a marketing wall, not a
gate... If the content is what you charge for, the shipped bytes have to differ."

The fix follows the ratified split (reference implementation:
templates/special_situations.html.j2 / scripts/build_site.py's _etf_gated /
_write_etf_payload): the shell bakes only `preview_rows` of us_standouts.buy
(system order preserved, never resorted); the withheld remainder renders into
site/premiumdata/us_stocks.json from the SAME partial
(templates/_us_board_cards.html.j2) the shell {% include %}s, so the two can
never drift apart.

Two layers, deliberately (mirrors tests/test_etfs_gate.py):

* the SPLIT is proven hermetically (fake rows, real templates), so the contract
  holds even before a render lane has rebaked the desk;
* the SHIPPED BYTES are then checked against the same invariant, skipping
  (loudly) until the desk has actually been rebaked in the gated shape.

Kept import-light where possible (jinja2-only template checks import nothing
from scripts.build_site); the splitter/payload-writer tests import
scripts.build_site, which pulls pandas/plotly, so those are guarded with
pytest.importorskip the same way test_etfs_gate.py's builder test is.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHELL = ROOT / "site" / "us_stocks.html"
PAYLOAD = ROOT / "site" / "premiumdata" / "us_stocks.json"

from tests.test_dashboard_template_render import _env, _board_row, _base_vm  # noqa: E402

# A card's identity is its whole rendered body (the `<a class="pvcard …">…</a>`
# block: ticker, name, price, verb, edge, marks — everything), NOT its ticker.
# This is a single flat board (unlike the ETF/China multi-panel desks where one
# ticker legitimately appears in several boards), so ticker and row happen to
# coincide here — but keying on the full body is still what
# docs/TIER_PREVIEW_PATTERN.md's checklist step 7 requires, and it is what
# actually catches a markup regression that keys the wrong span.
CARD_ROW = re.compile(r'<a class="pvcard.*?</a>', re.S)
TICKER_ATTR = re.compile(r'data-ticker="([^"]*)"')
SCRIPT_TAG = re.compile(r'<script\b.*?</script>', re.S)


def _strip_scripts(html: str) -> str:
    """dashboard.html.j2 carries a client-side card builder (W-L1 board-state
    JS, ~line 18704) whose JS source literally contains the text
    `<a class="pvcard …" … data-ticker="'+_pvcE(c.tk)+'"` as a template-string
    literal — a real match for CARD_ROW that is not a rendered card at all.
    Strip <script> blocks before hunting for cards so JS source can never be
    mistaken for shipped markup."""
    return SCRIPT_TAG.sub("", html)


def _keys(html: str) -> list[str]:
    return [" ".join(m.group(0).split()) for m in CARD_ROW.finditer(_strip_scripts(html))]


def _tickers_in(html: str) -> set[str]:
    """Tickers carried by actual server-rendered CARDS only — not any bare
    `data-ticker="…"` substring, which also appears inside inlined JS source
    (see _strip_scripts)."""
    out = set()
    for card in CARD_ROW.finditer(_strip_scripts(html)):
        m = TICKER_ATTR.search(card.group(0))
        if m:
            out.add(m.group(1))
    return out


# ── fixtures ────────────────────────────────────────────────────────────────
# lane path (stage=None) exercises the legacy `_render_list` construction the
# same way _base_vm's own ACME/ZEUS fixture rows do; one row (lane=None) takes
# the ungrouped branch, matching ZEUS.
_LANES = ["bottoming", "continuation", "trend", "recovery", "watch", None, "bottoming"]


def _rows(n: int = 7) -> list[dict]:
    return [_board_row(ticker=f"TIC{i}", name=f"Ticker {i} Inc",
                       lane=_LANES[i % len(_LANES)], price=10.0 + i)
            for i in range(n)]


# priority-engine path (G0.1): a row carrying `stage` flips `_sg.any` true and
# takes the stage_hd grouping + the #us-stage-filter chip bar — a different
# branch from the legacy lane path _rows() exercises above.
_STAGES = ["live", "setting_up", "ran", "basing", "blocked", "live", "setting_up"]


def _rows_with_stage(n: int = 7) -> list[dict]:
    return [_board_row(ticker=f"TIC{i}", name=f"Ticker {i} Inc",
                       lane=_LANES[i % len(_LANES)], stage=_STAGES[i % len(_STAGES)],
                       price=10.0 + i)
            for i in range(n)]


def _render_shell(us_standouts: dict, gate: dict | None) -> str:
    """The exact build_site.py override shape for the stocks-mode render call —
    vm["us_standouts"] replaced by the shallow-copied shell, `gate` added."""
    vm = _base_vm()
    vm["us_standouts"] = us_standouts
    vm["gate"] = gate
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


# ── the split (hermetic) ────────────────────────────────────────────────────

def test_split_shell_has_only_preview_rows_payload_has_exact_remainder():
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    assert gate is not None
    assert [r["ticker"] for r in shell_su["buy"]] == ["TIC0", "TIC1", "TIC2"]
    assert [r["ticker"] for r in locked] == ["TIC3", "TIC4", "TIC5", "TIC6"]
    assert gate["preview"] == 3 and gate["locked"] == 4 and gate["total"] == 7
    # the original object is untouched — vm["us_standouts"] is shared with
    # other page renders (macro.html)
    assert len(rows) == 7 and rows[0]["ticker"] == "TIC0"


def test_shell_html_contains_only_the_preview_rows():
    """End-to-end through the real template: renders dashboard.html.j2 with the
    sliced shell + gate exactly the way build_site.py's stocks-mode call does,
    and checks the shipped bytes — both surfaces named in the mission
    (#us-stocktable-data JSON and the .nbgrid card grid)."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    html = _render_shell(shell_su, gate)

    preview_tickers = {"TIC0", "TIC1", "TIC2"}
    locked_tickers = {"TIC3", "TIC4", "TIC5", "TIC6"}

    # .nbgrid card grid
    card_tickers = _tickers_in(html)
    assert card_tickers == preview_tickers, (
        f"card grid leaked/lost rows: {card_tickers ^ preview_tickers}")
    for tk in locked_tickers:
        assert tk not in html, f"{tk} is withheld content but reached the shell"

    # #us-stocktable-data JSON block
    m = re.search(r'<script type="application/json" id="us-stocktable-data">(.*?)</script>',
                  html, re.S)
    assert m, "the stocktable JSON block must still be present, just sliced"
    payload = json.loads(m.group(1))
    json_tickers = {r["ticker"] for r in payload["rows"]}
    assert json_tickers == preview_tickers, (
        f"#us-stocktable-data leaked/lost rows: {json_tickers ^ preview_tickers}")


def test_ungated_path_writes_empty_payload_and_leaves_the_board_whole():
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board, _write_us_payload

    rows = _rows(7)
    original = {"buy": rows, "eligible": 7}
    shell_su, gate, locked = _split_us_board(original, 3, gated=False)
    assert gate is None and locked == []
    assert shell_su is original, "ungated path must ship the board whole, untouched"

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        site = Path(td)
        _write_us_payload(_env(), site, gate, locked_rows=locked,
                          us_standouts=original, top_setups=None, built="2026-08-17 00:00")
        payload = json.loads((site / "premiumdata" / "us_stocks.json").read_text())
        assert payload["gated"] is False
        assert payload["rows"] == []
        assert payload["cards_html"] == ""
        assert payload["schema"] == "tier_payload.v1"
        assert payload["page"] == "us_stocks"

    # and the shell itself renders the whole board when there is no gate
    html = _render_shell(original, None)
    assert _tickers_in(html) == {f"TIC{i}" for i in range(7)}


def test_board_smaller_than_the_preview_cap_ships_whole():
    """preview_rows >= len(rows): nothing withheld, so this must ship the board
    whole rather than bake a wall over nothing — same rule the ETF board's
    "genuinely empty" branch enforces."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 100, gated=True)
    assert gate is None and locked == []
    assert shell_su["buy"] == rows


def test_us_board_gate_cfg_reads_config_yml_and_is_fail_soft():
    """Config read is fail-soft and the switch actually works — the same shape
    scripts.build_site._etf_gated() is modelled on."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _us_board_gate_cfg
    import scripts.build_site as bs

    cfg = _us_board_gate_cfg()
    assert cfg == {"gated": True, "preview_rows": 3,
                   "panels": True, "panel_preview_rows": 3}, (
        "config.yml us_board_gate must be {gated: true, preview_rows: 3, "
        "panels: true, panel_preview_rows: 3} — update this test deliberately "
        "if that switch changes")

    real_config = bs.config

    class _Boom:
        @staticmethod
        def load():
            raise RuntimeError("config unreadable")

    try:
        bs.config = _Boom()
        assert _us_board_gate_cfg() == {"gated": False, "preview_rows": 3,
                                        "panels": False,
                                        "panel_preview_rows": 3}, (
            "a config read must NEVER fail the render")
    finally:
        bs.config = real_config


# ── the leak check, keyed on the row ────────────────────────────────────────

def test_payload_cards_never_leak_into_the_shell_row_identity():
    """The mission-critical check: no withheld row's rendered body reaches the
    shell. Keyed on the row (docs/TIER_PREVIEW_PATTERN.md checklist step 7),
    paired with a coverage assertion so a markup change can never quietly turn
    this vacuous."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board, _us_board_group_items

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    shell_html = _render_shell(shell_su, gate)

    items = _us_board_group_items(locked, sg_any=False, stage_counts=gate["stage_counts"])
    cards_html = _env().get_template("_us_board_cards.html.j2").render(
        items=items, sg_any=False, bs_adj=False, xu_allfeat=False, trg_map={},
        rw_en="", rw_zh="")

    locked_keys = set(_keys(cards_html))
    assert locked_keys, "fixture produced no locked cards — vacuous test"
    assert len(locked_keys) == gate["locked"], (
        "row identities must cover the whole locked remainder or this check is "
        f"vacuous: keyed {len(locked_keys)} of {gate['locked']} locked rows")
    leaked = locked_keys & set(_keys(shell_html))
    assert leaked == [] or leaked == set(), f"locked rows readable in the free shell: {leaked}"


def test_the_leak_check_can_actually_see_a_duplicated_row():
    """A control, so the assertion above can never pass because the keying
    stopped matching the markup. Plant one locked row into a copy of the shell:
    it must bite (mirrors tests/test_etfs_gate.py's equivalent control)."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board, _us_board_group_items

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    shell_html = _render_shell(shell_su, gate)

    items = _us_board_group_items(locked, sg_any=False, stage_counts=gate["stage_counts"])
    cards_html = _env().get_template("_us_board_cards.html.j2").render(
        items=items, sg_any=False, bs_adj=False, xu_allfeat=False, trg_map={},
        rw_en="", rw_zh="")
    one_card = CARD_ROW.search(cards_html)
    assert one_card, "fixture markup changed — the card pattern no longer matches"

    planted = shell_html + one_card.group(0)
    leaked = set(_keys(cards_html)) & set(_keys(planted))
    assert leaked, "control failed to plant a detectable duplicate — the leak check is vacuous"


# ── honest totals ───────────────────────────────────────────────────────────

def test_honest_totals_survive_the_gate():
    """docs/TIER_PREVIEW_PATTERN.md: "state and totals are free, names are
    paid." The shown-count line and every bucket heading must report the TRUE
    full-board count, never the preview count."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    rows = _rows(7)
    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    html = _render_shell(shell_su, gate)

    assert '<span class="muted" id="us-board-sub"' in html
    m = re.search(r'id="us-board-sub"[^>]*>\s*(\d+)\s', html)
    assert m, "shown-count line not found"
    assert int(m.group(1)) == 7, (
        f"shown-count must report the TRUE total (7), not the preview slice: {m.group(1)}")
    assert ">3<" not in html.split('id="us-board-sub"')[1][:40]

    # every rendered lane heading must carry the TRUE bucket count, not the
    # number of preview cards that happen to sit under it
    for lane, true_count in (("bottoming", 2), ("continuation", 1), ("trend", 1),
                             ("recovery", 1), ("watch", 1)):
        m = re.search(r'<div class="nb-lane-hd">\s*<span class="l-en">'
                      + re.escape(lane.title() if lane != "watch" else "Watch")
                      + r" · (\d+)</span>", html)
        if m:  # heading only renders when at least one PREVIEW row is in that bucket
            assert int(m.group(1)) == true_count, (
                f"{lane} heading shows {m.group(1)}, true full-board count is {true_count}")


def test_ungated_shell_shows_the_same_true_total_the_gated_shell_does():
    """Sanity: the honest-total fix must not change the ungated number."""
    rows = _rows(7)
    html = _render_shell({"buy": rows, "eligible": 7}, None)
    m = re.search(r'id="us-board-sub"[^>]*>\s*(\d+)\s', html)
    assert m and int(m.group(1)) == 7


# ── controls stay inert while gated ─────────────────────────────────────────

def test_stage_filter_bar_is_baked_full_and_marked_inert_while_gated():
    """#us-stage-filter only exists on the priority (`stage`) path — rows must
    carry `stage` to exercise it, unlike the honest-totals tests above which
    use the legacy lane fixture."""
    rows = _rows_with_stage(7)
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    gated_html = _render_shell(shell_su, gate)
    ungated_html = _render_shell({"buy": rows, "eligible": 7}, None)

    assert 'id="us-stage-filter"' in gated_html and 'id="us-stage-filter"' in ungated_html, (
        "controls must be baked on BOTH builds, never omitted for the gated one")
    assert 'class="pbf-bar gated"' in gated_html
    assert 'class="pbf-bar gated"' not in ungated_html
    assert 'id="us-gate-note"' in gated_html and 'id="us-gate-note"' not in ungated_html


def test_stages_missing_from_the_preview_still_bake_a_hidden_chip():
    """A stage the preview slice happens not to contain still exists on the
    withheld board. Omitting its chip (the pre-fix behaviour, `{% if _sc[_sk] %}`
    over the SLICED board) leaves a hydrated paid viewer holding cards no control
    can filter to — measured on the real 69-row board, `setting_up` alone was 31
    of them. Bake it hidden and let the hydrate recount reveal it."""
    rows = _rows_with_stage(7)
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    html = _render_shell(shell_su, gate)

    preview_stages = {r["stage"] for r in shell_su["buy"]}
    locked_only = {r["stage"] for r in locked} - preview_stages
    assert locked_only, "fixture must leave at least one stage entirely withheld"

    for stage in locked_only:
        chip = re.search(
            r'<button type="button" data-stagepick="%s"(?P<hidden>\s+hidden)?' % re.escape(stage),
            html)
        assert chip, (
            f"stage {stage!r} exists on the withheld board but bakes no chip — a "
            "hydrated paid viewer could never filter to those cards")
        assert chip.group("hidden"), (
            f"stage {stage!r} has no preview rows, so its chip must ship hidden — "
            "a visible chip reading 0 would filter the board to nothing")

    # and the counting law still holds for what IS shown
    for stage in preview_stages:
        chip = re.search(
            r'data-stagepick="%s"(?P<hidden>\s+hidden)?' % re.escape(stage), html)
        assert chip and not chip.group("hidden"), (
            f"stage {stage!r} has preview rows on screen, so its chip must be visible")


def test_hydrate_recounts_the_stage_chips():
    """The baked counts describe the preview. Hydration makes the bar interactive
    over the WHOLE board, so it must re-derive them from the elements the
    data-stagef CSS actually filters — otherwise the chip states exactly the
    defect the baked counts exist to avoid."""
    rows = _rows_with_stage(7)
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, _ = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    html = _render_shell(shell_su, gate)

    assert "recountStageChips" in html, "hydrate path must re-derive the chip counts"
    # counted from the DOM the filter acts on, headings (which also carry
    # data-stage) excluded — not from the payload, so markup drift cannot
    # desynchronise the chip from the filtered result.
    assert "[data-stage]:not(.nb-stage-hd)" in html
    assert re.search(r"bar\.classList\.remove\('gated'\);\s*recountStageChips\(bar\)", html), (
        "the recount must run when the bar becomes interactive")


def test_tier_wall_and_hydrate_script_present_only_when_gated():
    rows = _rows(7)
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _split_us_board

    shell_su, gate, locked = _split_us_board({"buy": rows, "eligible": 7}, 3, gated=True)
    gated_html = _render_shell(shell_su, gate)
    ungated_html = _render_shell({"buy": rows, "eligible": 7}, None)

    assert 'id="us-tier-wall"' in gated_html
    assert "4 more names" in gated_html or ">4</span>" in gated_html
    assert 'id="us-tier-wall"' not in ungated_html
    assert "See plans" in gated_html and "查看方案" in gated_html
    assert 'id="us-tw-signin"' in gated_html


# ── shipped artifacts ───────────────────────────────────────────────────────

def _shipped_payload():
    if not PAYLOAD.exists():
        pytest.skip("us_stocks not yet rebaked in the gated shape "
                    "(render.yml emits site/premiumdata/us_stocks.json)")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated"):
        pytest.skip("us_stocks is running ungated (config.yml us_board_gate.gated=false)")
    return payload


def test_shipped_shell_leaks_no_locked_ticker():
    payload = _shipped_payload()
    if not SHELL.exists():
        pytest.skip("site/us_stocks.html not built in this checkout")
    shell = SHELL.read_text(encoding="utf-8")
    locked_tickers = {r["ticker"] for r in payload.get("rows", []) if r.get("ticker")}
    assert locked_tickers, "a gated payload with no locked rows is a vacuous pass"
    leaked = sorted(tk for tk in locked_tickers if f'data-ticker="{tk}"' in shell)
    assert leaked == [], f"locked tickers reachable in the shipped shell: {leaked[:5]}"


def _shell_board_blocks():
    """The shell's TWO renderings of the same preview slice: the card grid
    (`data-ticker` attrs, from _us_board_cards.html.j2) and the StockTable JSON
    island (#us-stocktable-data). Both iterate `us_standouts.buy`, so in any real
    render they carry the SAME tickers in the SAME order."""
    payload = _shipped_payload()
    if not SHELL.exists():
        pytest.skip("site/us_stocks.html not built in this checkout")
    shell = SHELL.read_text(encoding="utf-8")
    cards = re.findall(r'<a class="pvcard[^"]*" href="stock\.html#[A-Z0-9.\-]+"\s*\n?\s*'
                       r'data-ticker="([^"]+)"', shell)
    start = shell.find('id="us-stocktable-data"')
    table = (re.findall(r'"ticker":\s*"([^"]+)"', shell[start:shell.find("</script>", start)])
             if start >= 0 else [])
    return payload, cards, table


def test_shipped_shell_stocktable_leaks_no_locked_ticker():
    """The card grid is not the only place the board ships. #us-stocktable-data
    serializes the SAME rows flat — ticker, conviction score, alpha, factor_z,
    sue_z, entry status — so a locked row reaching that island is the paid record
    itself in view-source, not merely a name. The `data-ticker=` assertion above
    cannot see it (the island spells the key `"ticker"`), which is exactly how the
    2026-08-18 splice shipped ONTO's full row while only the grid tripped CI."""
    payload, _cards, table = _shell_board_blocks()
    locked = {r["ticker"] for r in payload.get("rows", []) if r.get("ticker")}
    assert locked, "a gated payload with no locked rows is a vacuous pass"
    leaked = sorted(set(table) & locked)
    assert leaked == [], f"locked tickers in the shipped #us-stocktable-data: {leaked[:5]}"


def test_shipped_shell_board_blocks_agree_with_the_payload_split():
    """A GIT MERGE can publish a board no render ever produced.

    Every render lane pushes via `git pull --rebase --autostash -X theirs origin
    main`. `-X theirs` only decides CONFLICTING hunks, so when two renders of this
    page race, non-conflicting hunks from BOTH survive and git assembles a shell
    that is neither generation. Measured 2026-08-18 (33f7bdde0c3a): the grid held
    FOUR cards against the payload's own `preview: 3`, the 4th being locked row 0,
    while #us-stocktable-data still held the previous generation's three.

    No per-block leak check catches that shape on its own — each block can look
    individually plausible. The invariant that does is AGREEMENT: both blocks
    render `us_standouts.buy`, and the split guarantees its length is `preview`.
    A shell whose two board blocks disagree has been spliced, whether or not this
    particular splice happened to expose a paid row. `.gitattributes` marks these
    shells `-merge` so a rebase takes one render whole; this is the assertion that
    fails if that ever regresses."""
    payload, cards, table = _shell_board_blocks()
    assert cards == table, (
        "the shell's card grid and #us-stocktable-data disagree — the page is a "
        f"merge of two renders, not one render: grid={cards[:6]} table={table[:6]}")
    assert len(cards) == payload["preview"], (
        f"shell ships {len(cards)} board rows against payload preview="
        f"{payload['preview']} (locked={payload['locked']}, total={payload['total']})")


def test_shipped_payload_declares_the_contract():
    payload = _shipped_payload()
    assert payload["schema"] == "tier_payload.v1"
    assert payload["page"] == "us_stocks"
    assert payload["required_tier"] == "essential"
    assert payload["locked"] > 0
    assert payload["cards_html"], "payload is missing cards_html — hydration would half-restore"


# ── the serving boundary ─────────────────────────────────────────────────────

def test_us_stocks_page_is_public_and_payload_prefix_is_enforced_early():
    """us_stocks.html stays anonymous-public (docs/TIER_PREVIEW_PATTERN.md: "The
    US Stocks and Research Vault shells are likewise public acquisition
    surfaces"); the new payload rides the /premiumdata/ prefix that already
    enforces Essential+ regardless of PAYWALL_ENABLED — config/site_access.yml
    needs NO change for this gate to be real."""
    import yaml

    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    assert "/us_stocks.html" in policy["public"]["exact"]
    prefixes = policy["premium"]["enforced_early"]["prefixes"]
    assert "/premiumdata/" in prefixes
    public = policy["public"]
    assert "/premiumdata/us_stocks.json" not in (public.get("exact") or [])
    assert not any(p.startswith("/premiumdata") for p in (public.get("prefixes") or []))


# ══ the four ADJACENT panels ═════════════════════════════════════════════════
# PR #5840 gated `us_standouts.buy` and nothing else. Four sibling panels on the
# same page are fed by DIFFERENT artifacts, so the board's split never reached
# them and they stayed gated only by templates/tier_preview.js — a DOM overlay,
# every row readable in view-source (measured live 2026-08-17: 24 `tr.ts-row`,
# 43 `.actitem`, 12 `.pbr-r`, 15 `.tt-names`). Plus #plv-names, a ticker ->
# company-name island built from watch u buy u leaders u laggards, which
# re-published by name every leader the leaders strip withholds.

TS_ROW = re.compile(r'<tr class="ts-row".*?</tr>', re.S)
PBR_ROW = re.compile(r'<a class="pbr-r.*?</a>', re.S)
ACT_ROW = re.compile(r'<a class="actitem.*?</a>', re.S)
TT_LIST = re.compile(r'<span class="tt-names" data-ttl="([^"]+)">(.*?)</span>\s*</div>', re.S)
TT_LOCKED = re.compile(r'<div class="tt-locked" data-ttl="([^"]+)">(.*?)</div>', re.S)


def _panel_vm(*, setups=12, leaders=11, ran=9, actnow=7, watch=6, laggards=5):
    """A view-model with every adjacent panel populated past the preview cap.

    Deliberately distinct ticker namespaces per panel (TSX/LEDX/RANX/ACTX/WCHX/
    LAGX and the ZMSFTZ tape symbols) so a leak assertion names the panel that
    leaked instead of reporting a bare 'a ticker appears twice'."""
    vm = _base_vm()
    vm["top_setups"] = {"buy": [
        {"ticker": f"TSX{i}", "name": f"Setup {i}", "sector": "Financials",
         "alpha": 1.0 + i, "sector_rank": i + 1, "sector_n": 262,
         "signal": {"tier_cascade": "T1"}, "label": "up", "alpha_entry": "pullback",
         "factor_z": 0.5, "setup": 1.2, "insider_buyers": None,
         "insider_net_mn": None, "sue_z": None} for i in range(setups)]}
    su = dict(vm["us_standouts"])
    su["buy"] = [dict(_board_row(ticker=f"BRD{i}", name=f"Board {i}"), stage="live")
                 for i in range(8)]
    su["ran"] = [{"ticker": f"RANX{i}", "name": f"Ran {i}", "pct_since": 3.0,
                  "sessions_since": 4, "anchor": "marker", "theme": None,
                  "theme_confirmed": False} for i in range(ran)]
    su["leaders"] = [{"ticker": f"LEDX{i}", "name": f"Lead {i}", "sector": "Industrials",
                      "alpha": 2.0, "off_high": -1.0, "label": "trend",
                      "entry_signal": None, "ext_z": 0.1, "theme": None,
                      "theme_confirmed": False} for i in range(leaders)]
    su["watch"] = [{"ticker": f"WCHX{i}", "name": f"Watch {i}"} for i in range(watch)]
    su["laggards"] = [{"ticker": f"LAGX{i}", "name": f"Lag {i}"} for i in range(laggards)]
    vm["us_standouts"] = su
    vm["action_board"] = {
        "buy_now": [{"kind": "sector", "ticker": f"ACTX{i}", "name": f"Act {i}",
                     "href": "x.html", "label": "L"} for i in range(actnow)],
        "buy_soon": [], "on_the_run": [], "take_profits": [], "hold": [], "avoid": []}
    vm["theme_tape"] = {"as_of": "2026-08-17", "rank_of": 8, "rows": [
        {"name": "Software", "name_zh": "软件", "rank": 1, "n_members": 60,
         "n_on_board": 6, "say_en": "act", "say_zh": "行动",
         "counts": {"live": 2, "quiet": 50},
         "members": {"live": [{"t": "ZMSFTZ"}, {"t": "ZNOWZ"}]},
         "quiet_sample": ["QQAX", "QQBX"], "quiet_more": 5}]}
    return vm


def _render_panels(vm, pgate):
    """The exact build_site override shape for the stocks-mode render call with
    the adjacent-panel gate applied — the board itself left whole, so a failure
    here can only be about the panels."""
    return _env().get_template("dashboard.html.j2").render(
        **{**vm, "gate": None, "pgate": pgate}, mode="stocks")


def _split_panels(vm, preview=3, gated=True):
    from scripts.build_site import _split_us_panels
    return _split_us_panels(vm, preview, gated=gated)


def test_every_adjacent_panel_ships_only_its_preview_slice():
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    assert pgate, "a page with every panel over the cap must produce a gate"
    html = _render_panels(vm, pgate)

    # .topsetups (fresh triggers) + .topsetups.leaders-strip share the ts-row class,
    # so the two tables are counted together against their two previews.
    assert len(TS_ROW.findall(_strip_scripts(html))) == \
        pgate["setups"]["preview"] + pgate["leaders"]["preview"]
    assert len(PBR_ROW.findall(_strip_scripts(html))) == pgate["ran"]["preview"]
    assert len(ACT_ROW.findall(_strip_scripts(html))) == pgate["actnow"]["preview"]
    # The tape's lists are REPLACED by their count, not truncated, so the slot
    # count is unchanged and what must be gone is the member markup.
    assert '<span class="tt-n">' not in html and 'class="tt-sym"' not in html

    for key, n in (("setups", 7), ("leaders", 8), ("ran", 6), ("actnow", 4)):
        assert pgate[key]["locked"] == n, (key, pgate[key])
        assert len(locked[key] if key != "actnow"
                   else [r for L in locked[key] for r in L["rows"]]) == n


def test_no_withheld_panel_row_survives_in_the_shell():
    """The split IS the gate: a withheld row must not be in the shipped bytes at
    all. Keyed on the row's own identity (its whole rendered block), not on the
    ticker — docs/TIER_PREVIEW_PATTERN.md checklist step 7."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    shell = _strip_scripts(_render_panels(vm, pgate))

    withheld = ([r["ticker"] for r in locked["setups"]]
                + [r["ticker"] for r in locked["leaders"]]
                + [r["ticker"] for r in locked["ran"]]
                + [r["ticker"] for L in locked["actnow"] for r in L["rows"]]
                + ["ZMSFTZ", "ZNOWZ", "QQAX", "QQBX"]
                + sorted(locked["plv_names"]))
    assert len(withheld) >= 30, "a vacuous fixture would pass this test for free"
    leaked = sorted({t for t in withheld if t in shell})
    assert leaked == [], f"withheld rows reachable in the shell: {leaked[:8]}"


def test_the_panel_leak_check_can_actually_see_a_leak():
    """Hermetic control for the assertion above: a shell rendered WITHOUT the gate
    must trip it, or the check is vacuous and would pass on a reopened leak."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    ungated = _strip_scripts(_render_panels(vm, None))
    withheld = ([r["ticker"] for r in locked["setups"]]
                + [r["ticker"] for r in locked["leaders"]]
                + [r["ticker"] for r in locked["ran"]]
                + [r["ticker"] for L in locked["actnow"] for r in L["rows"]]
                + ["ZMSFTZ", "QQAX"])
    assert sorted({t for t in withheld if t in ungated}) == sorted(set(withheld)), (
        "the ungated shell must carry every row the gated one withholds — "
        "otherwise the leak assertion is testing nothing")


def test_the_payload_carries_exactly_what_the_shell_withheld():
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _render_us_panel_payload
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    blocks = _render_us_panel_payload(_env(), pgate, locked, vm)

    assert set(blocks) == {"setups_html", "leaders_html", "ran_html",
                           "actnow_html", "tape_html", "plv_names"}
    assert len(TS_ROW.findall(blocks["setups_html"])) == pgate["setups"]["locked"]
    assert len(TS_ROW.findall(blocks["leaders_html"])) == pgate["leaders"]["locked"]
    assert len(PBR_ROW.findall(blocks["ran_html"])) == pgate["ran"]["locked"]
    assert len(ACT_ROW.findall(blocks["actnow_html"])) == pgate["actnow"]["locked"]
    for tk in ("ZMSFTZ", "ZNOWZ", "QQAX", "QQBX"):
        assert tk in blocks["tape_html"]
    # The payload is rows, never chrome: shipping the panel CSS to every hydrating
    # reader is how a 500-byte block becomes a 25 KB one.
    assert "<style" not in blocks["actnow_html"]
    assert "<style" not in blocks["tape_html"]
    assert "id=\"action-board\"" not in blocks["actnow_html"]


def test_tape_payload_lists_are_byte_identical_to_the_ungated_panel():
    """The tape renders from ONE source in three shapes. If the names-only mode
    ever drifts from the panel's own markup, a hydrated reader silently gets a
    different member list from the one a full server render would have produced."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _render_us_panel_payload
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    tape_html = _render_us_panel_payload(_env(), pgate, locked, vm)["tape_html"]
    ungated = _env().get_template("_theme_tape.html.j2").render(
        theme_tape=vm["theme_tape"])

    panel = dict(TT_LIST.findall(ungated))
    paid = dict(TT_LOCKED.findall(tape_html))
    assert panel and panel.keys() == paid.keys(), (sorted(panel), sorted(paid))
    for slot, markup in panel.items():
        assert markup == paid[slot], f"tape list {slot} drifted between the two renders"


def test_panel_headings_and_counts_stay_honest():
    """State and totals are free, names are paid — every count on a gated panel
    reports the FULL list, exactly as the board's own split does."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, _ = _split_panels(vm)
    html = _render_panels(vm, pgate)

    # "Recently fired" header count = every ran row, not the three shown.
    assert f'<span class="pbr-n">{len(vm["us_standouts"]["ran"])}</span>' in html
    # Act-Now lane heading count = the whole lane.
    assert f'<span class="acth-count">{len(vm["action_board"]["buy_now"])}</span>' in html
    # The tape keeps every count on its ladder — the panel's whole argument.
    assert 'class="tt-quiet">50/60<' in html
    # Each gated panel says how many names it is holding back, in both languages.
    for n in (pgate["setups"]["locked"], pgate["leaders"]["locked"], pgate["ran"]["locked"]):
        assert f'{n} more names here' in html
    assert '此处还有' in html


def test_plv_name_island_withholds_the_locked_population():
    """#plv-names is a ticker -> COMPANY NAME map over watch u buy u leaders u
    laggards. Gating the leaders strip while this island still names every leader
    would be a wall with a door beside it."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, locked = _split_panels(vm)
    html = _render_panels(vm, pgate)
    island = json.loads(re.search(r'id="plv-names">(.*?)</script>', html, re.S).group(1))

    assert not any(k.startswith(("WCHX", "LAGX")) for k in island), (
        "watch/laggard names have no panel on this page and must not ship")
    shown = {f"LEDX{i}" for i in range(pgate["leaders"]["preview"])}
    assert {k for k in island if k.startswith("LEDX")} == shown, (
        "the island must name the leaders the document shows, and only those")
    assert set(locked["plv_names"]) & set(island) == set(), (
        "no withheld label may appear on both sides of the wall")
    assert len(locked["plv_names"]) == 8 + 6 + 5, "locked leaders + watch + laggards"


def test_ungated_build_renders_the_page_exactly_as_before():
    """`panels: false` (and every host that passes no pgate at all) must produce
    byte-identical output — the switch can always be flipped back."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    overrides, pgate, locked = _split_panels(vm, gated=False)
    assert (overrides, pgate, locked) == ({}, None, {})
    assert _render_panels(vm, None) == _render_panels(vm, pgate)


def test_a_panel_at_or_under_the_cap_grows_no_wall():
    """docs/TIER_PREVIEW_PATTERN.md: a plane with nothing withheld must not grow a
    skeleton. Here that means no disclosure line and no payload block for it."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    from scripts.build_site import _render_us_panel_payload
    vm = _panel_vm(setups=2, leaders=1, ran=3, actnow=3, watch=0, laggards=0)
    _, pgate, locked = _split_panels(vm)
    assert pgate is None or not any(k in pgate for k in ("setups", "leaders", "ran", "actnow")), pgate
    if pgate:
        assert set(_render_us_panel_payload(_env(), pgate, locked, vm)) <= {"tape_html"}


def test_act_now_board_is_untouched_for_its_other_host():
    """_us_act_now_board.html.j2 is a SHARED include — sector_central.html renders
    the same board and passes no pgate. Gating one host must not thin the other."""
    ab = {"buy_now": [{"kind": "sector", "ticker": f"S{i}", "name": f"N {i}",
                       "href": "x.html", "label": "L"} for i in range(7)],
          "buy_soon": [], "on_the_run": [], "take_profits": [], "hold": [], "avoid": []}
    tpl = _env().get_template("_us_act_now_board.html.j2")
    assert len(ACT_ROW.findall(tpl.render(action_board=ab))) == 7
    assert len(ACT_ROW.findall(tpl.render(action_board=ab, pgate={"actnow": {"preview": 3}}))) == 3


def test_fold_controls_are_suppressed_while_gated_and_rebuilt_on_hydrate():
    """A "Show more (4)" button over a lane holding three rows promises content
    the document does not contain. It goes while gated and the hydration script
    rebuilds it from the rows that actually arrived."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, _ = _split_panels(vm)
    gated = _render_panels(vm, pgate)
    plain = _render_panels(vm, None)
    assert '<button class="lst-more act-more"' in plain
    assert '<button class="lst-more act-more"' not in gated
    assert "function restoreFold(" in gated
    assert "hydratePanels(payload)" in gated


def test_hydration_targets_every_panel_it_withholds():
    """Each withheld block needs a landing site, or a paying reader hydrates into a
    half-restored page and the gate reads as data loss."""
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    vm = _panel_vm()
    _, pgate, _ = _split_panels(vm)
    html = _render_panels(vm, pgate)
    for block, target in (
            ("payload.setups_html", "#us-standouts .topsetups:not(.leaders-strip) .ts-tbl tbody"),
            ("payload.leaders_html", "#us-standouts .topsetups.leaders-strip .ts-tbl tbody"),
            ("payload.ran_html", "#us-standouts .pbr-l")):
        assert block in html and target in html
    assert "data-ab-lane" in html and ".tt-locked[data-ttl]" in html
    assert "payload.plv_names" in html and "window.__plvNames" in html
    # every act-now lane the splitter can fill must exist as a DOM id
    for _key, dest, _wrap in __import__("scripts.build_site", fromlist=["x"])._US_ACTNOW_LANES:
        assert f'id="{dest}"' in html, dest


def test_shipped_shell_leaks_no_locked_panel_row():
    payload = _shipped_payload()
    panels = payload.get("panels") or {}
    if not panels:
        pytest.skip("us_stocks not yet rebaked with the adjacent-panel gate")
    if not SHELL.exists():
        pytest.skip("site/us_stocks.html not built in this checkout")
    shell = _strip_scripts(SHELL.read_text(encoding="utf-8"))
    leaked = []
    for block in ("setups_html", "leaders_html", "ran_html", "actnow_html"):
        for m in re.finditer(r'data-tkr="([^"]+)"|href="stock\.html#([^"]+)"',
                             payload.get(block) or ""):
            tk = m.group(1) or m.group(2)
            if tk and (f'data-tkr="{tk}"' in shell or f'>{tk}</span>' in shell):
                leaked.append(tk)
    assert leaked == [], f"locked panel rows reachable in the shipped shell: {leaked[:5]}"
    for tk in (payload.get("plv_names") or {}):
        assert f'"{tk}"' not in re.search(
            r'id="plv-names">(.*?)</script>', SHELL.read_text(encoding="utf-8"), re.S).group(1)


def test_tier_preview_leaves_a_server_collapsed_tape_list_alone():
    """templates/tier_preview.js collapses `#theme-tape .tt-names` to "N names" by
    COUNTING the .tt-n spans. On a gated build those spans are not in the document,
    so an unguarded pass would rewrite a truthful "7 names" to "0 names" — and would
    stash that text, letting a later pass restore it over the names hydration just
    put back. Both halves are the same one-line guard, so both are pinned here."""
    for path in (ROOT / "templates" / "tier_preview.js", ROOT / "site" / "tier_preview.js"):
        js = path.read_text(encoding="utf-8")
        fn = js[js.index("function applyTapeMembers()"):js.index("function placeSurfaceGates(")]
        assert 'if (!list.querySelector(".tt-n")) return;' in fn, path
        # ...and it has to come BEFORE the stash, or the restore path still fires.
        assert fn.index('if (!list.querySelector(".tt-n")) return;') < \
               fn.index('list.setAttribute("data-mx-old-html"'), path
