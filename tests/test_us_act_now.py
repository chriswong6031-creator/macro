"""tests/test_us_act_now.py — US bottoming-watch lane assembler (W-A).

Pins the lane gate, the ordering, the cap, the FT-R1 dual-read id set, the
BUY-quote + trend-gate-conflict flags, the honest null, and the two display
fences that keep a WATCH lane free of buy verbs.

The live receipt (gate G0.2) is `test_gold_miners_case_from_committed_log`:
the real committed `data/sector_cycles/forward_log.parquet` row
`b-gold_miners: Trough, pos=2.0, osc_slope=+1.3, signal=BUY, above200d=False`
must land on the lane with its gate-shut conflict flagged.

Both committed-log receipts pin an EXPLICIT DATE, never `date.max()`. The first
cut of this file pinned the latest row and asserted gold_miners was on the lane;
when the cycle engine graduated it Trough→Recovery on 2026-08-05 the assertion
became false and the suite went red on unchanged code. A receipt for a transient
state must name the session it is a receipt for.

`test_gold_miners_graduation_case_from_committed_log` is that graduation, pinned
as the receipt for the opposite half: off the lane, and carrying the recovering
chip instead.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.us_act_now import (
    BOTTOMING_CAP,
    DISPLAY_FORBIDDEN_FIELDS,
    NULL_DISCLOSURE_EN,
    NULL_DISCLOSURE_ZH,
    RECOVERING_CHIP_EN,
    RECOVERING_CHIP_ZH,
    RECOVERING_DISCLOSURE_EN,
    RECOVERING_DISCLOSURE_ZH,
    RECOVERING_POS_MAX,
    RECOVERING_TIP_EN,
    RECOVERING_TIP_ZH,
    assemble_bottoming_watch,
    canonical_id,
    contains_buy_word,
)

#: The lane's display home. #4599 shipped it as a client-rendered fifth lane inside
#: sector_central.html.j2 (botRow()/actLane('bottom',…)); #4642 transplanted the
#: us_stocks five-lane board over sector_central's own five lanes and deleted that
#: renderer, taking the bottoming lane with it — its summary called the board it
#: replaced "4-lane", but the deleted code ran FIVE actLane() calls including
#: `bottom`. The lane is restored here as a server-rendered strip under the board.
#: These fences therefore point at the partial, NOT at sector_central.html.j2.
BOTTOMING_LANE = ROOT / "templates" / "_us_bottoming_watch.html.j2"
#: The board that hosts the strip and carries the graduation-gap chip on its own rows.
ACT_BOARD = ROOT / "templates" / "_us_act_now_board.html.j2"


# ─────────────────────────────────────── helpers ──────────────────────────────
def _render_lane(payload: dict) -> str:
    """Render the bottoming strip in isolation and return its HTML.

    Substring assertions against template SOURCE cannot tell a live element from a
    commented-out one, and they pass on a macro nobody calls (the #3282 dead-surface
    shape). Rendering the partial and asserting on the OUTPUT is what actually pins
    the display contract, so the fences below use this wherever they can.
    """
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    env.globals.update(tr=lambda en: en, td=lambda en: en, t=lambda en, zh="": en)
    return env.get_template("_us_bottoming_watch.html.j2").render(bottoming=payload)


def _lane_payload(**over):
    """A bottoming payload in the shape build_sector_central passes to the page."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", pos=2.0, slope=1.3, signal="BUY", above200d=False,
              name="Gold Miners")],
        reduce_ids=over.pop("reduce_ids", None),
        names_zh=over.pop("names_zh", None),
    )
    payload = {
        "bottoming_watch": out["bottoming_watch"],
        "dual_read_ids": out["dual_read_ids"],
        "recovering_ids": out["recovering_ids"],
        "bottoming_authority": out["authority"],
        "recovering_rendered": False,
    }
    payload.update(over)
    return payload
def _row(id_="b-x", phase="Trough", pos=5.0, slope=1.0, signal="BUY",
         above200d=False, kind="basket", name=None, timing="COUNTERTREND BOUNCE"):
    return {
        "id": id_, "kind": kind, "name": name or id_, "phase": phase,
        "pos": pos, "osc_slope": slope, "signal": signal,
        "above200d": above200d, "timing_state": timing,
    }


def _ids(out):
    return [r["id"] for r in out["bottoming_watch"]]


# ─────────────────────────────────── the lane gate ────────────────────────────
def test_trough_and_rising_qualifies():
    out = assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)])
    assert _ids(out) == ["b-gold_miners"]


def test_trough_and_falling_does_not_qualify():
    out = assemble_bottoming_watch([_row(slope=-1.3)])
    assert out["bottoming_watch"] == []


def test_trough_and_flat_slope_does_not_qualify():
    """osc_slope == 0 is not rising — the gate is strict."""
    assert assemble_bottoming_watch([_row(slope=0.0)])["bottoming_watch"] == []


def test_non_trough_phase_does_not_qualify():
    for phase in ("Expansion", "Downturn", "Peak", "Recovery"):
        out = assemble_bottoming_watch([_row(phase=phase, slope=2.0)])
        assert out["bottoming_watch"] == [], f"{phase} must not reach the lane"


def test_missing_slope_is_unknown_not_rising():
    """A null slope must never manufacture a bottoming call."""
    assert assemble_bottoming_watch([_row(slope=None)])["bottoming_watch"] == []
    assert assemble_bottoming_watch([_row(slope=float("nan"))])["bottoming_watch"] == []


def test_phase_match_is_exact():
    """'Trough' only — no substring/case slop that would widen the gate."""
    for phase in ("trough", "TROUGH", "Trough Watch", "Pre-Trough"):
        out = assemble_bottoming_watch([_row(phase=phase, slope=2.0)])
        assert out["bottoming_watch"] == [], f"{phase!r} must not pass the gate"


# ─────────────────────────────────── ordering + cap ───────────────────────────
def test_sorted_by_pos_ascending():
    """Deepest in the cycle low first."""
    rows = [_row(id_=f"b-{p}", pos=p, slope=1.0) for p in (18.6, 2.0, 12.3, 3.5)]
    out = assemble_bottoming_watch(rows)
    assert [r["pos"] for r in out["bottoming_watch"]] == [2.0, 3.5, 12.3, 18.6]


def test_unknown_pos_sorts_last_not_first():
    """A missing pos must not be treated as 0 and jump the queue."""
    out = assemble_bottoming_watch(
        [_row(id_="b-none", pos=None, slope=1.0), _row(id_="b-deep", pos=9.0, slope=1.0)]
    )
    assert _ids(out) == ["b-deep", "b-none"]


def test_cap_respected_and_disclosed():
    rows = [_row(id_=f"b-{i}", pos=float(i), slope=1.0) for i in range(20)]
    out = assemble_bottoming_watch(rows)
    assert len(out["bottoming_watch"]) == BOTTOMING_CAP == 8
    # the deepest 8 survive, in order
    assert _ids(out) == [f"b-{i}" for i in range(8)]
    # the truncation is disclosed, never silent
    assert any("capped" in n for n in out["notes"]), out["notes"]


def test_cap_is_overridable_and_no_note_when_nothing_dropped():
    rows = [_row(id_=f"b-{i}", pos=float(i), slope=1.0) for i in range(3)]
    out = assemble_bottoming_watch(rows, cap=2)
    assert len(out["bottoming_watch"]) == 2
    full = assemble_bottoming_watch(rows)
    assert full["notes"] == []


# ─────────────────────────────── FT-R1 dual read ──────────────────────────────
def test_dual_read_ids_match_across_the_b_prefix():
    """forward-log 'b-gold_miners' must find theme id 'gold_miners'."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", slope=1.3)],
        reduce_ids=["gold_miners", "housing", "crypto"],
    )
    assert set(out["dual_read_ids"]) == {"b-gold_miners", "gold_miners"}


def test_dual_read_excludes_non_reduce_rows():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", pos=1.0, slope=1.3),
         _row(id_="b-us_sector_comm", pos=2.0, slope=2.7)],
        reduce_ids=["gold_miners"],
    )
    assert set(out["dual_read_ids"]) == {"b-gold_miners", "gold_miners"}
    assert "us_sector_comm" not in out["dual_read_ids"]


def test_sector_etf_row_has_no_theme_counterpart():
    """'xlu' must not dual-read against the theme id 'us_sector_utilities'."""
    out = assemble_bottoming_watch(
        [_row(id_="xlu", kind="sector", slope=1.3)],
        reduce_ids=["us_sector_utilities"],
    )
    assert out["dual_read_ids"] == []
    assert _ids(out) == ["xlu"]


def test_dual_read_empty_without_reduce_ids():
    out = assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)])
    assert out["dual_read_ids"] == []


def test_dual_read_ids_are_sorted_and_json_safe():
    out = assemble_bottoming_watch(
        [_row(id_="b-z", pos=1.0, slope=1.0), _row(id_="b-a", pos=2.0, slope=1.0)],
        reduce_ids=["z", "a"],
    )
    assert out["dual_read_ids"] == sorted(out["dual_read_ids"])
    json.dumps(out)  # must not raise


# ─────────────────────────── bilingual names (G0.5) ──────────────────────────
def test_name_zh_resolves_by_canonical_and_raw_id():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", pos=1.0, slope=1.3, name="Gold Miners"),
         _row(id_="xlu", kind="sector", pos=2.0, slope=1.3, name="Utilities")],
        names_zh={"gold_miners": "黄金矿业", "xlu": "公用事业"},
    )
    assert [r["name_zh"] for r in out["bottoming_watch"]] == ["黄金矿业", "公用事业"]


def test_missing_name_zh_is_none_not_a_slug():
    """No zh name → None, so the template falls back to the English display name."""
    r = assemble_bottoming_watch([_row(id_="b-mystery", slope=1.0)])["bottoming_watch"][0]
    assert r["name_zh"] is None


def test_template_falls_back_to_english_when_name_zh_absent():
    """Bilingual law: an absent zh name renders the English one, never a blank.

    Was `x.name_zh||x.name` inside botRow(); the restored strip expresses the same
    law as `(x.name_zh or x.name)`. Asserted on RENDERED output — a row with no zh
    name must still paint a non-empty zh span.
    """
    html = _render_lane(_lane_payload())          # names_zh omitted → name_zh is None
    assert '<span class="l-zh">Gold Miners</span>' in html, (
        "the zh layer fell back to nothing — an absent name_zh must render the "
        "English display name, not an empty span"
    )
    # …and when a zh name IS supplied it must win.
    html_zh = _render_lane(_lane_payload(names_zh={"gold_miners": "黄金矿业"}))
    assert '<span class="l-zh">黄金矿业</span>' in html_zh


def test_canonical_id():
    assert canonical_id("b-gold_miners") == "gold_miners"
    assert canonical_id("xlc") == "xlc"
    assert canonical_id(None) == ""


# ──────────────────── BUY quote + trend-gate conflict flags ───────────────────
def test_buy_signal_is_quoted_and_gate_conflict_set():
    out = assemble_bottoming_watch([_row(signal="BUY", above200d=False, slope=1.3)])
    r = out["bottoming_watch"][0]
    assert r["cycle_signal"] == "BUY"
    assert r["gate_conflict"] is True


def test_buy_signal_above_trend_has_no_conflict():
    r = assemble_bottoming_watch(
        [_row(signal="BUY", above200d=True, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["cycle_signal"] == "BUY"
    assert r["gate_conflict"] is False


def test_non_buy_signal_carries_no_cycle_signal():
    r = assemble_bottoming_watch(
        [_row(signal="SELL", above200d=False, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["cycle_signal"] is None
    # no cycle turn was signalled, so there is no conflict to print
    assert r["gate_conflict"] is False


def test_unknown_above200d_does_not_fabricate_a_conflict():
    """None is UNKNOWN, not False — an unknown trend gate must not print 'gate shut'."""
    r = assemble_bottoming_watch(
        [_row(signal="BUY", above200d=None, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["above200d"] is None
    assert r["gate_conflict"] is False


# ───────────────────────── empty log → empty lane + null ──────────────────────
def test_absent_log_yields_empty_lane_with_note():
    out = assemble_bottoming_watch(None)
    assert out["bottoming_watch"] == []
    assert out["dual_read_ids"] == []
    assert any("absent" in n for n in out["notes"]), out["notes"]


def test_empty_log_yields_empty_lane_without_absent_note():
    out = assemble_bottoming_watch([])
    assert out["bottoming_watch"] == []
    assert out["notes"] == []


def test_null_disclosure_always_present():
    """Honest null (G0.4) rides the payload whether or not the lane has rows."""
    for rows in (None, [], [_row(slope=1.0)]):
        auth = assemble_bottoming_watch(rows)["authority"]
        assert auth["null_disclosure_en"] == NULL_DISCLOSURE_EN
        assert auth["null_disclosure_zh"] == NULL_DISCLOSURE_ZH
        assert auth["null_disclosure_en"].strip()
        assert auth["null_disclosure_zh"].strip()


def test_authority_block_is_display_tier_with_zero_powers():
    """G0.1 — nothing in this lane may rank, gate, size, or escalate."""
    auth = assemble_bottoming_watch([_row(slope=1.0)])["authority"]
    assert auth["tier"] == "display"
    for k in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert auth[k] is False, k


def test_malformed_rows_are_skipped_not_fatal():
    out = assemble_bottoming_watch(["not a dict", None, 42, _row(slope=1.0)])
    assert len(out["bottoming_watch"]) == 1


# ───────────────────── never-buy-words discipline (display) ───────────────────
def test_contains_buy_word_detects_the_forward_log_vocabulary():
    assert contains_buy_word("FRESH BUY")
    assert contains_buy_word("BUY")
    assert contains_buy_word("clean entry")
    assert not contains_buy_word("COUNTERTREND BOUNCE")
    assert not contains_buy_word("cycle turn signal — watch only")
    assert not contains_buy_word(None)


def test_rendered_lane_copy_carries_no_buy_verb():
    """Every fixed string the lane renders must be watch vocabulary."""
    rendered = [
        "Bottoming watch", "cycle lows forming — watch, don't chase",
        "cycle turn signal — watch only", "below 200-day trend — gate shut",
        "no basing candidates tonight", "may be bottoming",
        NULL_DISCLOSURE_EN,
    ]
    for s in rendered:
        assert not contains_buy_word(s), f"buy verb in rendered copy: {s!r}"


def test_row_name_is_the_only_free_text_field_rendered():
    """`signal` and `timing_state` carry buy words — they must stay payload-only.

    This test pins WHY the fence exists: the real vocabulary of `timing_state`
    includes the literal value "FRESH BUY".
    """
    r = assemble_bottoming_watch(
        [_row(signal="BUY", timing="FRESH BUY", slope=1.0)]
    )["bottoming_watch"][0]
    assert contains_buy_word(r["timing_state"])
    assert contains_buy_word(r["signal"])
    assert set(DISPLAY_FORBIDDEN_FIELDS) == {"signal", "timing_state"}


@pytest.mark.parametrize("field", DISPLAY_FORBIDDEN_FIELDS)
def test_template_bottoming_row_never_renders_a_buy_word_field(field):
    """The fence is only real if the renderer actually omits these fields.

    Checked against the RENDERED strip, with the forbidden field carrying a value
    that is unmistakable in the output. Source-grepping for `x.signal` would miss a
    row that reached the same value by another spelling; rendering cannot.
    """
    payload = _lane_payload()
    sentinel = "FRESH BUY" if field == "timing_state" else "BUY"
    payload["bottoming_watch"][0][field] = sentinel
    html = _render_lane(payload)
    assert sentinel not in html, (
        f"the strip rendered {field}={sentinel!r}, putting a buy verb on a "
        f"watch-only lane"
    )
    # The field must still RIDE the payload — the fence is "never displayed",
    # not "never carried"; a renderer that drops it would hide the receipt.
    assert payload["bottoming_watch"][0][field] == sentinel


def test_template_lane_declares_the_watch_caption_in_both_languages():
    """The lane's fixed copy, in both languages, on the surface that ships it.

    These exact strings are the lane's content contract (#4599). They moved from
    sector_central's botRow()/actLane() call to the restored strip verbatim — the
    assertion is unchanged, only its target is.
    """
    src = BOTTOMING_LANE.read_text(encoding="utf-8")
    for s in ("Bottoming watch", "筑底观察",
              "cycle lows forming", "周期底部形成中",
              "cycle turn signal — watch only", "周期转折信号——仅观察",
              "below 200-day trend — gate shut", "低于200日趋势——闸门关闭",
              "no basing candidates tonight", "今晚无筑底候选",
              "may be bottoming", "或正筑底"):
        assert s in src, f"missing lane string: {s!r}"


def test_a_us_surface_actually_renders_the_bottoming_lane():
    """THE #4642 REGRESSION GUARD — the whole display chain, link by link.

    This lane went dark for two days with a perfectly healthy engine, builder and
    payload: #4642 transplanted the us_stocks five-lane board over sector_central's
    own five lanes, and because BOTH boards had five lanes the swap read as
    like-for-like. Every assembler test in this file stayed green the entire time.

    A payload nothing renders is not a shipped lane, so the chain is pinned end to
    end. Break any single link and this fails LOUDLY instead of the lane silently
    vanishing again:

      1. the strip template exists
      2. the shared act board includes it
      3. sector_central hosts that board
      4. build_sector_central actually passes the payload to the render
      5. and the strip really paints rows for a live payload
    """
    assert BOTTOMING_LANE.exists(), (
        "the bottoming strip template is gone — the lane has no renderer again"
    )
    board_src = ACT_BOARD.read_text(encoding="utf-8")
    assert BOTTOMING_LANE.name in board_src, (
        f"{ACT_BOARD.name} no longer includes {BOTTOMING_LANE.name} — the strip "
        f"exists but nothing renders it (this is exactly how #4642 went dark)"
    )
    page = (ROOT / "templates" / "sector_central.html.j2").read_text(encoding="utf-8")
    assert ACT_BOARD.name in page, (
        "sector_central no longer hosts the act board, so the strip cannot reach a page"
    )
    builder = (ROOT / "scripts" / "build_sector_central.py").read_text(encoding="utf-8")
    assert "bottoming=" in builder, (
        "build_sector_central stopped passing the bottoming payload — the strip "
        "would self-hide on every render with no error anywhere"
    )
    # …and the strip is not merely wired, it paints.
    html = _render_lane(_lane_payload(names_zh={"gold_miners": "黄金矿业"}))
    assert 'id="ab-bottom"' in html and "Gold Miners" in html, (
        "the strip rendered no lane for a live payload"
    )
    assert html.count('class="actitem"') == 1


def test_template_has_no_translated_title_attribute():
    """House law: no translated text in title= attributes — hover copy ships as
    data-tip-en/data-tip-zh so the language switch can reach it.

    Asserted on the rendered strip rather than on source, so a title= that only
    appears once Jinja has run is still caught.
    """
    html = _render_lane(_lane_payload(names_zh={"gold_miners": "黄金矿业"}))
    assert "title=" not in html, "the strip emitted a title= attribute"
    assert "data-tip-en=" in html and "data-tip-zh=" in html, (
        "hover copy must ship as data-tip-en/data-tip-zh"
    )


# ──────────────────── G0.3 — the existing lanes stay untouched ────────────────
def test_assembler_never_mutates_the_reduce_lane_input():
    reduce_ids = ["gold_miners", "housing"]
    snapshot = list(reduce_ids)
    assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)], reduce_ids=reduce_ids)
    assert reduce_ids == snapshot


def test_wiring_leaves_buy_wait_reduce_membership_byte_identical():
    """G0.3 — the W-A wiring may only ADD keys to act_now.

    Replays exactly what scripts/build_baskets.py does to a real act_now payload
    and asserts the three pre-existing lanes are unchanged, member for member.
    """
    from engine.us_act_now import assemble_bottoming_watch as _asm

    act_now = {
        "buy": [{"id": "robotics_automation", "name": "Robotics", "score": 71}],
        "add_on_pullback": [{"id": "mag7", "name": "Mag 7", "score": 63}],
        "reduce": [{"id": "gold_miners", "name": "Gold Miners", "score": 31},
                   {"id": "crypto_rails", "name": "Crypto Rails", "score": 28}],
        "conflicted": [],
    }
    before = json.dumps(act_now, sort_keys=True)

    bw = _asm([_row(id_="b-gold_miners", pos=2.0, slope=1.3)],
              reduce_ids=[x["id"] for x in act_now["reduce"]])
    act_now["bottoming_watch"] = bw["bottoming_watch"]
    act_now["dual_read_ids"] = bw["dual_read_ids"]
    act_now["bottoming_authority"] = bw["authority"]

    after = {k: act_now[k] for k in ("buy", "add_on_pullback", "reduce", "conflicted")}
    assert json.dumps(after, sort_keys=True) == before
    # and the new keys really did land
    assert act_now["bottoming_watch"] and act_now["dual_read_ids"]


# ───────────────────── G0.2 — the live gold_miners receipt ────────────────────
def _committed_rows(date_str: str) -> list[dict]:
    """Rows of the committed forward log for ONE named session.

    Deliberately not `date.max()`: these receipts pin transient states, so they
    must name their session or they expire the next time the engine moves.
    """
    pd = pytest.importorskip("pandas")
    p = ROOT / "data" / "sector_cycles" / "forward_log.parquet"
    if not p.exists():
        pytest.skip("forward_log.parquet not present in this checkout")
    df = pd.read_parquet(p)
    sel = df[df["date"].astype(str).str.startswith(date_str)]
    if sel.empty:
        pytest.skip(f"forward log has no {date_str} session in this checkout")
    return sel.to_dict(orient="records")


def test_gold_miners_case_from_committed_log():
    """The §2 D9 case, reproduced from the real committed forward log.

    `b-gold_miners` on 2026-08-04: Trough, pos=2.0, osc_slope=+1.3, signal=BUY,
    above200d=False — the row the Act board buried on reduce/avoid.
    """
    rows = _committed_rows("2026-08-04")

    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners", "crypto_rails"])
    by_id = {r["id"]: r for r in out["bottoming_watch"]}

    assert "b-gold_miners" in by_id, (
        "gold_miners must reach the bottoming lane — this is the whole point of W-A"
    )
    g = by_id["b-gold_miners"]
    assert g["name"] == "Gold Miners"
    assert g["cid"] == "gold_miners"
    assert g["kind"] == "BASKET"
    assert g["pos"] == pytest.approx(2.0)
    assert g["osc_slope"] == pytest.approx(1.3)
    assert g["cycle_signal"] == "BUY"
    assert g["above200d"] is False
    assert g["gate_conflict"] is True, "the D10 trend-gate conflict must be flagged"
    assert g["href"] == "basket/gold_miners.html"

    # deepest low first — gold_miners at pos=2.0 leads the lane
    assert out["bottoming_watch"][0]["id"] == "b-gold_miners"
    # and it dual-reads against its reduce/avoid row
    assert "gold_miners" in out["dual_read_ids"]

    # every row on the lane genuinely satisfies the gate
    for r in out["bottoming_watch"]:
        src = next(x for x in rows if str(x["id"]) == r["id"])
        assert src["phase"] == "Trough"
        assert float(src["osc_slope"]) > 0


def test_committed_log_rows_are_json_serializable():
    """pandas/numpy scalars must be coerced at the boundary or the artifact breaks."""
    pd = pytest.importorskip("pandas")
    p = ROOT / "data" / "sector_cycles" / "forward_log.parquet"
    if not p.exists():
        pytest.skip("forward_log.parquet not present in this checkout")
    df = pd.read_parquet(p)
    rows = df[df["date"] == df["date"].max()].to_dict(orient="records")
    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners"])
    json.dumps(out, ensure_ascii=False)  # must not raise
    for r in out["bottoming_watch"]:
        assert isinstance(r["pos"], (float, type(None)))
        assert isinstance(r["above200d"], (bool, type(None)))
        assert isinstance(r["gate_conflict"], bool)
    assert all(isinstance(i, str) for i in out["recovering_ids"])


# ═════════════ the graduation gap — reduce/avoid rows on NO lane ══════════════
# The cycle engine graduates a basket Trough→Recovery the session its phase
# turns, so it leaves the lane at once. The Act board's momentum label keeps it
# on reduce/avoid until its 20d relative flips positive. Between those two events
# the basket sits on no lane at all. These pin the bridge.

def test_recovering_row_on_the_reduce_lane_is_chipped():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["gold_miners"],
    )
    assert out["bottoming_watch"] == [], "a graduated row must NOT be on the lane"
    assert set(out["recovering_ids"]) == {"b-gold_miners", "gold_miners"}


def test_recovering_requires_the_row_to_be_on_the_reduce_lane():
    """The chip exists to un-bury a reduce/avoid row. No reduce row, no chip."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["housing"],
    )
    assert out["recovering_ids"] == []


def test_recovering_requires_a_rising_oscillator():
    for slope in (-1.5, 0.0):
        out = assemble_bottoming_watch(
            [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=slope)],
            reduce_ids=["gold_miners"],
        )
        assert out["recovering_ids"] == [], f"slope={slope} must not chip"


def test_recovering_unknown_slope_is_not_rising():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=None)],
        reduce_ids=["gold_miners"],
    )
    assert out["recovering_ids"] == []


def test_recovering_respects_the_position_fence():
    """`Recovery` spans pos 2.3→31.9 on one night. The chip says "recovering from
    cycle low", so it may only fire while the row is still AT the low."""
    inside = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=RECOVERING_POS_MAX, slope=1.0)],
        reduce_ids=["a"],
    )
    outside = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=RECOVERING_POS_MAX + 0.1, slope=1.0)],
        reduce_ids=["a"],
    )
    assert set(inside["recovering_ids"]) == {"b-a", "a"}, "the fence is inclusive"
    assert outside["recovering_ids"] == []


def test_recovering_unknown_pos_cannot_claim_the_low():
    """A missing position must never manufacture the claim the chip's copy makes."""
    out = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=None, slope=1.0)], reduce_ids=["a"]
    )
    assert out["recovering_ids"] == []


def test_recovering_phase_match_is_exact():
    for phase in ("recovery", "RECOVERY", "Recovering", "Trough"):
        out = assemble_bottoming_watch(
            [_row(id_="b-a", phase=phase, pos=2.0, slope=1.0)], reduce_ids=["a"]
        )
        assert out["recovering_ids"] == [], f"phase={phase!r} must not chip"


def test_recovering_matches_a_sector_etf_without_the_b_prefix():
    out = assemble_bottoming_watch(
        [_row(id_="xlc", phase="Recovery", pos=6.7, slope=5.0, kind="sector")],
        reduce_ids=["xlc"],
    )
    assert out["recovering_ids"] == ["xlc"]


def test_recovering_ids_are_sorted_and_json_safe():
    out = assemble_bottoming_watch(
        [_row(id_="b-z", phase="Recovery", pos=1.0, slope=1.0),
         _row(id_="b-a", phase="Recovery", pos=2.0, slope=1.0)],
        reduce_ids=["z", "a"],
    )
    assert out["recovering_ids"] == sorted(out["recovering_ids"])
    json.dumps(out, ensure_ascii=False)


def test_recovering_note_counts_names_not_id_spellings():
    """A basket contributes two spellings ('b-x','x'), a sector ETF one."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="xlc", phase="Recovery", pos=6.7, slope=5.0, kind="sector")],
        reduce_ids=["gold_miners", "xlc"],
    )
    assert any("recovering-from-low chips: 2" in n for n in out["notes"]), out["notes"]


# ── the two id sets must never be confused for one another ───────────────────
def test_dual_read_and_recovering_sets_are_disjoint():
    """FT-R1's chip says "also on Bottoming watch". The recovering chip fires for
    rows that are on NO lane. A row in both sets would render a false sentence."""
    out = assemble_bottoming_watch(
        [_row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4),
         _row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["uranium_miners", "gold_miners"],
    )
    assert set(out["dual_read_ids"]) == {"b-uranium_miners", "uranium_miners"}
    assert set(out["recovering_ids"]) == {"b-gold_miners", "gold_miners"}
    assert not set(out["dual_read_ids"]) & set(out["recovering_ids"])


def test_dual_read_ids_stay_a_subset_of_the_lane_and_recovering_never_joins_it():
    """The invariant every consumer of `dual_read_ids` relies on."""
    out = assemble_bottoming_watch(
        [_row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4),
         _row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["uranium_miners", "gold_miners"],
    )
    lane = {r["id"] for r in out["bottoming_watch"]} | {
        r["cid"] for r in out["bottoming_watch"]
    }
    assert set(out["dual_read_ids"]) <= lane
    assert not set(out["recovering_ids"]) & lane


def test_recovering_ids_present_even_when_the_lane_is_empty():
    """The whole point: the lane can be empty while a graduated row still needs
    its chip. An absent key here would be the re-blindness this closes."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["gold_miners"],
    )
    assert out["bottoming_watch"] == []
    assert out["recovering_ids"]


@pytest.mark.parametrize("rows", [None, []])
def test_recovering_ids_is_always_a_list(rows):
    assert assemble_bottoming_watch(rows)["recovering_ids"] == []


def test_recovering_assembler_never_mutates_the_reduce_lane_input():
    reduce_ids = ["gold_miners", "housing"]
    snapshot = list(reduce_ids)
    assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=reduce_ids,
    )
    assert reduce_ids == snapshot


# ── the graduation receipt (the case this bridge was built for) ───────────────
def test_gold_miners_graduation_case_from_committed_log():
    """`b-gold_miners` on 2026-08-05: Trough→Recovery, pos=2.3, osc_slope=+1.5,
    signal=BUY, above200d=False.

    The session it left the lane. Its board row still read `deteriorating/avoid`
    (20d relative −8.14%), so without the chip it sat on no lane at all.
    """
    rows = _committed_rows("2026-08-05")
    src = next(r for r in rows if str(r["id"]) == "b-gold_miners")
    assert src["phase"] == "Recovery", "fixture drift — this pins the graduation"
    assert float(src["pos"]) == pytest.approx(2.3)
    assert float(src["osc_slope"]) == pytest.approx(1.5)
    assert str(src["signal"]).upper() == "BUY"
    assert bool(src["above200d"]) is False

    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners", "crypto_rails"])

    # it has LEFT the lane — the CN-faithful gate is untouched by this bridge
    assert "b-gold_miners" not in {r["id"] for r in out["bottoming_watch"]}
    # ...and the chip is what now carries it
    assert "gold_miners" in out["recovering_ids"]
    assert "b-gold_miners" in out["recovering_ids"]
    # the lane itself still works on the same night
    assert "b-uranium_miners" in {r["id"] for r in out["bottoming_watch"]}


def test_committed_graduation_keeps_the_two_chip_sets_disjoint():
    """Belt-and-braces on the real night both chips were live."""
    out = assemble_bottoming_watch(
        _committed_rows("2026-08-05"),
        reduce_ids=["gold_miners", "uranium_miners", "crypto_rails"],
    )
    assert set(out["dual_read_ids"]) & set(out["recovering_ids"]) == set()
    # uranium_miners is Trough+rising and on reduce → the FT-R1 chip
    assert "uranium_miners" in out["dual_read_ids"]
    # gold_miners graduated → the recovering chip
    assert "gold_miners" in out["recovering_ids"]


# ── never-buy words + bilingual law for the new copy ──────────────────────────
def test_recovering_copy_carries_no_buy_verb():
    for s in (RECOVERING_CHIP_EN, RECOVERING_TIP_EN, RECOVERING_DISCLOSURE_EN):
        assert not contains_buy_word(s), f"buy verb in rendered copy: {s!r}"


def test_recovering_copy_is_bilingual_and_non_empty():
    for en, zh in ((RECOVERING_CHIP_EN, RECOVERING_CHIP_ZH),
                   (RECOVERING_TIP_EN, RECOVERING_TIP_ZH),
                   (RECOVERING_DISCLOSURE_EN, RECOVERING_DISCLOSURE_ZH)):
        assert en.strip() and zh.strip()
        assert zh != en, "zh copy must actually be translated"


def test_recovering_copy_uses_no_house_jargon_or_raw_slugs():
    """Glance-tier vocabulary law: no internal state names, no raw slugs."""
    banned = ("Trough", "Recovery", "osc_slope", "forward_log", "phase==",
              "FT-R1", "W-A", "pos<=", "b-")
    for s in (RECOVERING_CHIP_EN, RECOVERING_TIP_EN, RECOVERING_DISCLOSURE_EN):
        for b in banned:
            assert b not in s, f"house jargon {b!r} in user copy: {s!r}"


def test_recovering_copy_ships_from_the_engine_authority_block():
    """The page must not carry its own wording — one source, no drift."""
    auth = assemble_bottoming_watch([])["authority"]
    assert auth["recovering_chip_en"] == RECOVERING_CHIP_EN
    assert auth["recovering_chip_zh"] == RECOVERING_CHIP_ZH
    assert auth["recovering_tip_en"] == RECOVERING_TIP_EN
    assert auth["recovering_tip_zh"] == RECOVERING_TIP_ZH
    assert auth["recovering_disclosure_en"] == RECOVERING_DISCLOSURE_EN
    assert auth["recovering_disclosure_zh"] == RECOVERING_DISCLOSURE_ZH


def test_recovering_tip_does_not_claim_bottoming_lane_membership():
    """The defect this design avoids: FT-R1's tip says "also on Bottoming watch".
    These rows are on no lane, so that sentence would send the reader to a lane
    the name has left."""
    assert "Bottoming watch" not in RECOVERING_TIP_EN
    assert "筑底观察" not in RECOVERING_TIP_ZH


# ── template pinning ─────────────────────────────────────────────────────────
# The graduation-gap chip rides the BOARD's own reduce-side rows (a recovering name
# has LEFT the bottoming lane, so it cannot be shown inside the strip). Its render
# path is _us_act_now_board.html.j2's ab_recov() macro; its id→row join is
# scripts.build_sector_central.build_bottoming_context().
def _board_src() -> str:
    return ACT_BOARD.read_text(encoding="utf-8")


def _render_board(board: dict) -> str:
    """Render the shared act board and return its HTML.

    Source-grepping for `ab_recov(x)` does NOT prove the chip ships: that substring
    also occurs in the macro's own `{%- macro ab_recov(x) -%}` header, so deleting
    every call site leaves the assertion green — the exact #3282 dead-macro shape
    this fence exists to catch (caught here by mutation test 4). Render instead.
    """
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=False,
    )
    env.globals.update(tr=lambda en: en, td=lambda en: en)
    full = {"buy_now": [], "buy_soon": [], "on_the_run": [],
            "take_profits": [], "hold": [], "avoid": [], "more": {}}
    full.update(board)
    return env.get_template("_us_act_now_board.html.j2").render(action_board=full)


def _stamped_board(recovering=("b-gold_miners", "gold_miners"), lane="avoid"):
    """Run the real join and return (board, bottoming-context)."""
    from scripts.build_sector_central import build_bottoming_context

    board = {lane: [{"kind": "theme", "slug": "gold_miners", "ticker": "gold_miners",
                     "name": "Gold Miners"}]}
    act_now = {
        "bottoming_watch": [],
        "dual_read_ids": [],
        "recovering_ids": list(recovering),
        "bottoming_authority": assemble_bottoming_watch([])["authority"],
    }
    ctx = build_bottoming_context(act_now, board)
    return board, ctx


def test_template_renders_the_recovering_chip_from_the_engine_copy():
    """The chip's words must come from the engine, not be re-typed on the page."""
    src = _board_src()
    assert "macro ab_recov(" in src, "the graduation-gap chip macro is gone"
    for token in ("recovering_chip_en", "recovering_chip_zh",
                  "recovering_tip_en", "recovering_tip_zh"):
        assert token in src, f"the chip must render engine copy {token}"
    # The stamped values really are the engine's, character for character…
    board, _ = _stamped_board()
    item = board["avoid"][0]
    assert item["recovering_chip_en"] == RECOVERING_CHIP_EN
    assert item["recovering_chip_zh"] == RECOVERING_CHIP_ZH
    assert item["recovering_tip_en"] == RECOVERING_TIP_EN
    assert item["recovering_tip_zh"] == RECOVERING_TIP_ZH
    # …and the macro is INVOKED, not merely defined. Asserted on rendered output:
    # a source grep for "ab_recov(x)" also matches the macro's own header, so it
    # stays green with every call site deleted (mutation-verified).
    html = _render_board(board)
    assert RECOVERING_CHIP_EN in html and RECOVERING_CHIP_ZH in html, (
        "ab_recov is defined but never rendered on a row — the #3282 dead-surface "
        "shape, where a macro nobody calls keeps a substring assertion green"
    )
    # Compared after unescaping: the tip is emitted through |e, so its apostrophe
    # ships as &#39; and the raw constant is deliberately not a literal substring.
    from html import unescape
    assert RECOVERING_TIP_EN in unescape(html), (
        "the chip shipped without its hover receipt"
    )
    # A row with no stamp must not fabricate an empty chip.
    clean = _render_board({"avoid": [{"kind": "theme", "slug": "x", "name": "X"}]})
    assert RECOVERING_CHIP_EN not in clean


def test_template_gives_a_row_one_chip_not_two():
    """The one-chip-per-row guarantee, pinned where it is now decided.

    actRow() used to enforce it in the renderer (`!x._conflicted && !BOT_DUAL.has`).
    With that renderer gone the guarantee is structural: the assembler never puts an
    id in both sets, and the chip is only ever stamped on a reduce-side row that is
    NOT on the bottoming lane. Both halves are asserted.
    """
    bw = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4)],
        reduce_ids=["gold_miners", "uranium_miners"],
    )
    assert bw["recovering_ids"] and bw["dual_read_ids"]
    assert not (set(bw["recovering_ids"]) & set(bw["dual_read_ids"])), (
        "an id in both sets would render two chips on one row"
    )
    on_lane = {r["id"] for r in bw["bottoming_watch"]}
    assert not (set(bw["recovering_ids"]) & on_lane), (
        "a recovering id must have LEFT the bottoming lane"
    )
    # An already-chipped row is never re-stamped.
    from scripts.build_sector_central import build_bottoming_context
    board = {"avoid": [{"kind": "theme", "slug": "gold_miners",
                        "recovering_chip_en": "PRE-EXISTING"}]}
    build_bottoming_context(
        {"bottoming_watch": [], "recovering_ids": ["gold_miners"],
         "bottoming_authority": bw["authority"]}, board)
    assert board["avoid"][0]["recovering_chip_en"] == "PRE-EXISTING"


def test_template_populates_the_recovering_set_and_footnote():
    """The builder reads recovering_ids, and the disclosure prints only when a chip
    is actually on the page — a footnote must never explain an absent chip."""
    board, ctx = _stamped_board()
    assert board["avoid"][0]["recovering_chip_en"], "the join stamped no row"
    assert ctx["recovering_rendered"] is True

    # No matching row on the board → no chip, so no disclosure.
    _, ctx_none = _stamped_board(recovering=("b-nothing_here", "nothing_here"))
    assert ctx_none["recovering_rendered"] is False
    html = _render_lane(_lane_payload(
        recovering_rendered=False,
        bottoming_authority=dict(assemble_bottoming_watch([])["authority"]),
    ))
    assert RECOVERING_DISCLOSURE_EN not in html, (
        "the graduation-gap disclosure printed with no chip on the page"
    )
    # …and it DOES print once a chip was rendered.
    html2 = _render_lane(_lane_payload(
        recovering_rendered=True,
        bottoming_authority=dict(assemble_bottoming_watch([])["authority"]),
    ))
    assert RECOVERING_DISCLOSURE_EN in html2


def test_template_recovering_chip_has_no_translated_title_attribute():
    """House law: no translated text in title= attributes."""
    src = _board_src()
    m = re.search(r"\{%- macro ab_recov\(x\) -%\}(.*?)\{%- endmacro -%\}", src, re.S)
    assert m, "ab_recov() not found — did the graduation-gap chip get renamed?"
    assert "title=" not in m.group(1)
    assert "data-tip-en=" in m.group(1) and "data-tip-zh=" in m.group(1)


def test_wiring_adds_recovering_ids_without_touching_the_other_lanes():
    """G0.3 — the bridge may only ADD a key."""
    act_now = {
        "buy": [{"id": "robotics_automation", "name": "Robotics", "score": 71}],
        "add_on_pullback": [{"id": "mag7", "name": "Mag 7", "score": 63}],
        "reduce": [{"id": "gold_miners", "name": "Gold Miners", "score": 34},
                   {"id": "uranium_miners", "name": "Uranium", "score": 36}],
        "conflicted": [],
    }
    before = json.dumps(act_now, sort_keys=True)
    bw = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4)],
        reduce_ids=[x["id"] for x in act_now["reduce"]],
    )
    act_now["bottoming_watch"] = bw["bottoming_watch"]
    act_now["dual_read_ids"] = bw["dual_read_ids"]
    act_now["recovering_ids"] = bw["recovering_ids"]
    act_now["bottoming_authority"] = bw["authority"]

    after = {k: act_now[k] for k in ("buy", "add_on_pullback", "reduce", "conflicted")}
    assert json.dumps(after, sort_keys=True) == before
    assert act_now["recovering_ids"] and act_now["dual_read_ids"]


def test_build_wiring_ships_the_recovering_key():
    """The engine key is inert unless the builder actually writes it."""
    src = (ROOT / "scripts" / "build_baskets.py").read_text(encoding="utf-8")
    assert '_an_ba["recovering_ids"] = _bw["recovering_ids"]' in src


# ───────────────────── help "?" tooltip framework twin (2026-08-06) ─────────────────────

def test_help_tip_framework_is_byte_identical_in_both_copies():
    """The legacy help() "?" hover framework (.help/.tip hide + :hover open) lives
    INLINE in dashboard.html.j2 — deliberately not in theme.css (cache-stamp blast
    radius; theme.css only carries span.help glyph metrics + .help-upgraded popover
    overrides). The shared board include renders on hosts that have no page-level
    copy: on sector_central the board h2's entire Tier-2 explainer sentence rendered
    permanently inline next to the heading (doctrine violation, found 2026-08-06
    while working #4735). The include therefore carries its own copy of the
    framework, fenced by help-tip-framework:BEGIN/END markers in both files.

    Byte-equality is the whole contract: identical selectors + identical
    declarations mean the duplicate emission on us_stocks can never conflict, only
    repeat — and any future edit to one copy must be mirrored or this pins red.
    """
    begin, end = "/* help-tip-framework:BEGIN", "/* help-tip-framework:END */"
    slices = {}
    for path in (TEMPLATES / "dashboard.html.j2", ACT_BOARD):
        text = path.read_text(encoding="utf-8")
        assert text.count(begin) == 1, f"{path.name}: expected exactly one BEGIN marker"
        assert text.count(end) == 1, f"{path.name}: expected exactly one END marker"
        slices[path.name] = text.split(begin, 1)[1].split(end, 1)[0]
    dash, board = slices["dashboard.html.j2"], slices["_us_act_now_board.html.j2"]
    assert dash == board, (
        "help/tip framework drifted between dashboard.html.j2 and the board include —"
        " copy the edited block verbatim into the other file (markers inclusive)"
    )
    # Non-vacuous: the fenced slice must actually be the hide/open framework, not an
    # empty or displaced pair of markers.
    assert ".help .tip { display: none;" in dash, "framework slice lost the hide rule"
    assert ".help:hover .tip" in dash and "display: block" in dash, (
        "framework slice lost the hover-open rule"
    )
