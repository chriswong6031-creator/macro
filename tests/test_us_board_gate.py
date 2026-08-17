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
    assert cfg == {"gated": True, "preview_rows": 3}, (
        "config.yml us_board_gate must be {gated: true, preview_rows: 3} — "
        "update this test deliberately if that switch changes")

    real_config = bs.config

    class _Boom:
        @staticmethod
        def load():
            raise RuntimeError("config unreadable")

    try:
        bs.config = _Boom()
        assert _us_board_gate_cfg() == {"gated": False, "preview_rows": 3}, (
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
