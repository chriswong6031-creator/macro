"""CN Theme Tape (W-C) — the join, the partition, and the surface it renders.

The panel exists to close the 2026-08-04 detection-without-narration incident (Gold
Miners top-ranked, no picks, page silent), so the tests that matter are the ones that
would let the silence back in: a member that lands in no bucket, a machine string
reaching the glance tier, a stale feed printed as if it were today's, a row whose
stance disappears, and a dead tape that still prints a ladder.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from engine.cn_theme_tape import (
    BUCKET_KEYS,
    CONTINUATION_BOARD,
    FLOW_MAX_AGE_DAYS,
    MAX_ROWS,
    PHASE_INDEX,
    PHASE_WORDS,
    STANCES,
    WHY_NOT,
    build_cn_theme_tape,
)

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "templates"
PARTIAL = TMPL / "_cn_theme_tape.html.j2"
TODAY = _dt.date(2026, 8, 5)


def _markup() -> str:
    """The partial with every comment stripped.

    Scanning the raw file is what a vocabulary/colour gate naively does, and it is
    wrong in both directions here: the design notes cite PRs as `#4553`, which reads
    as a hex colour, and they discuss `title=` and `--ink-up` by name. A gate that
    trips on its own rationale teaches the next author to delete the rationale.
    """
    src = PARTIAL.read_text()
    src = re.sub(r"\{#-?.*?-?#\}", "", src, flags=re.DOTALL)   # jinja comments
    return re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)      # css comments


def _stylesheet() -> str:
    return _markup().split("<style", 1)[1].split("</style>", 1)[0]


# ── fixtures ────────────────────────────────────────────────────────────────
def _membership(**over):
    doc = {"baskets": {
        "cn_gold": {
            "name": "Gold Miners", "name_zh": "黄金", "etf_proxy": None,
            "members": [{"ticker": "002155.SZ", "name_zh": "湖南黄金"},
                        {"ticker": "600988.SS", "name_zh": "赤峰黄金"},
                        {"ticker": "601899.SS", "name_zh": "紫金矿业"}],
        },
        "cn_metals": {
            "name": "Industrial Metals", "name_zh": "有色金属", "etf_proxy": "512400.SS",
            "members": [{"ticker": "000630.SZ", "name_zh": "铜陵有色"},
                        {"ticker": "601168.SS", "name_zh": "西部矿业"}],
        },
    }}
    doc.update(over)
    return doc


def _cycles(gold_phase="Recovery"):
    return pd.DataFrame([
        {"date": "2026-08-05", "id": "b-cn_gold", "kind": "basket",
         "phase": gold_phase, "osc_slope": 14.2, "pos": 15.5},
        {"date": "2026-08-05", "id": "b-cn_metals", "kind": "basket",
         "phase": "Recovery", "osc_slope": 3.2, "pos": 7.4},
        {"date": "2026-08-05", "id": "801010", "kind": "sector",
         "phase": "Peak", "osc_slope": -1.0, "pos": 80.0},
        {"date": "2026-06-01", "id": "b-cn_gold", "kind": "basket",
         "phase": "Downturn", "osc_slope": -40.0, "pos": 5.0},
    ])


def _candidates(**over):
    rows = [
        {"stamp_date": "2026-08-05", "ticker": "002155.SZ", "lane": "not_raw_eligible",
         "entry_status": "hold",
         "gate_reason": "buy blocked by filter: veto: bearish divergence"},
        {"stamp_date": "2026-08-05", "ticker": "600988.SS", "lane": "not_raw_eligible",
         "entry_status": "await_confluence",
         "gate_reason": "held but topped/rolled-over — no longer a fresh entry"},
        {"stamp_date": "2026-08-05", "ticker": "601899.SS", "lane": "not_raw_eligible",
         "entry_status": "await_confluence",
         "gate_reason": "buy blocked by filter: counter-trend, no 200-reclaim/hold"},
        {"stamp_date": "2026-08-05", "ticker": "000630.SZ", "lane": "featured",
         "entry_status": "partial", "gate_reason": None},
        {"stamp_date": "2026-08-05", "ticker": "601168.SS", "lane": "more_actionable",
         "entry_status": "bounce_wait", "gate_reason": None},
    ]
    rows.extend(over.get("extra") or [])
    return pd.DataFrame(rows)


def _flow(as_of="2026-08-04"):
    return {"ashare_sectors": {"as_of": as_of, "rows": [
        {"id": "cn_gold", "state": "accelerating in", "state_zh": "加速流入"},
        {"id": "cn_metals", "state": "balanced", "state_zh": "均衡"},
    ]}}


def _build(**kw):
    kw.setdefault("membership", _membership())
    kw.setdefault("cycles", _cycles())
    kw.setdefault("candidates", _candidates())
    kw.setdefault("today", TODAY)
    return build_cn_theme_tape(**kw)


def _row(tape, key):
    return next(r for r in tape["rows"] if r["key"] == key)


# ── the join ────────────────────────────────────────────────────────────────
def test_every_member_lands_in_exactly_one_bucket_and_the_row_sums_to_membership():
    tape = _build()
    for row in tape["rows"]:
        assert sum(row["counts"][k] for k in BUCKET_KEYS) == row["n_members"], row["key"]


def test_the_gate_reason_becomes_plain_words_and_the_right_bucket():
    gold = _row(_build(), "cn_gold")
    assert gold["counts"] == {"live": 0, "almost": 0, "blocked": 1, "ran": 1, "quiet": 1}
    blocked = gold["members"]["blocked"][0]
    assert blocked["t"] == "002155.SZ"
    assert blocked["why_en"] == "Momentum diverging"
    assert blocked["why_zh"] == "动能背离"


def test_the_dominant_gate_reason_is_quiet_not_blocked():
    """`counter-trend, no 200-reclaim/hold` is the base state of a bearish universe.

    Bucketed as `blocked` it made that column a near-constant across every row, which
    is the per-row constant Law 4 exists to stop; as `quiet` the blocked column goes
    back to meaning "actively held out".
    """
    assert WHY_NOT["buy blocked by filter: counter-trend, no 200-reclaim/hold"][0] == "quiet"


def test_a_featured_lane_row_is_live_and_a_bounce_wait_row_is_almost():
    metals = _row(_build(), "cn_metals")
    assert metals["counts"]["live"] == 1
    assert metals["counts"]["almost"] == 1
    assert metals["members"]["live"][0]["t"] == "000630.SZ"


def test_an_unknown_gate_reason_never_reaches_the_glance_tier_as_a_raw_string():
    """Doctrine Law 2: a raw machine string on Tier 1 is a violation, not a fallback."""
    tape = _build(candidates=_candidates(extra=[
        {"stamp_date": "2026-08-05", "ticker": "601899.SS", "lane": "not_raw_eligible",
         "entry_status": "hold", "gate_reason": "some_brand_new_engine_slug"}]))
    entries = [m for r in tape["rows"] for g in r["members"].values() for m in g]
    assert not any("some_brand_new_engine_slug" in str(m.get("why_en") or "")
                   for m in entries)
    assert any(m["t"] == "601899.SS" and not m.get("why_en") for m in entries)


def test_a_shared_reason_collapses_to_one_and_a_mixed_group_keeps_its_own():
    same = [{"stamp_date": "2026-08-05", "ticker": t, "lane": "not_raw_eligible",
             "entry_status": "hold",
             "gate_reason": "buy blocked by filter: failed reclaim-and-hold"}
            for t in ("002155.SZ", "600988.SS", "601899.SS")]
    gold = _row(_build(candidates=pd.DataFrame(same)), "cn_gold")
    assert gold["shared_why"]["blocked"] == ("Reclaim failed", "收复失败")
    assert all("why_en" not in m for m in gold["members"]["blocked"])
    # the unmodified fixture has one blocked and one ran, each with its own reason
    mixed = _row(_build(), "cn_gold")
    assert "blocked" not in mixed.get("shared_why", {})


# ── the honest null ─────────────────────────────────────────────────────────
def test_no_baskets_or_no_cycle_read_yields_none():
    assert build_cn_theme_tape(None, _cycles(), _candidates()) is None
    assert build_cn_theme_tape({"baskets": {}}, _cycles(), _candidates()) is None
    assert build_cn_theme_tape(_membership(), None, _candidates()) is None


def test_a_tape_with_nothing_live_close_or_held_out_is_dead_and_renders_nothing():
    """A dead tape must not print a ladder of zeros — that is a forced ranking."""
    quiet = pd.DataFrame([
        {"stamp_date": "2026-08-05", "ticker": t, "lane": "not_raw_eligible",
         "entry_status": "hold", "gate_reason": "flat: sell"}
        for t in ("002155.SZ", "600988.SS", "601899.SS", "000630.SZ", "601168.SS")])
    assert _build(candidates=quiet) is None


def test_the_row_set_is_a_condition_not_a_top_n_slice():
    """A theme earns a row by having TURNED or by holding a live pick.

    Ranked by activity instead, Gold Miners — the theme whose silence caused the
    incident this panel closes — sorts off the end of a top-5 on the real artifacts.
    """
    tape = _build(cycles=_cycles(gold_phase="Peak"))
    assert [r["key"] for r in tape["rows"]] == ["cn_metals"], (
        "a theme that has not turned and has no live pick must not take a row")


def test_the_ceiling_bounds_the_panel_without_becoming_a_ranking():
    assert MAX_ROWS >= 5, "the ceiling must not silently become a top-5 by another name"
    tape = _build(max_rows=1)
    assert len(tape["rows"]) == 1
    assert tape["overflow"] == 1
    assert tape["n_themes"] == 2


# ── null tolerance: a missing source drops its own chip, never the tape ─────
def test_a_missing_flow_desk_drops_the_flow_chips_and_keeps_the_tape():
    tape = _build(flow=None)
    assert tape is not None and tape["flow_live"] is False
    assert all(r["flow_en"] is None for r in tape["rows"])


def test_a_stale_flow_desk_is_dropped_rather_than_printed_beside_todays_board():
    """The desk declares a daily cadence; on 2026-08-05 it stood at 2026-07-24."""
    fresh = _build(flow=_flow("2026-08-04"))
    assert fresh["flow_live"] is True
    assert _row(fresh, "cn_gold")["flow_en"] == "accelerating in"
    assert _row(fresh, "cn_gold")["flow_zh"] == "加速流入"

    stale = _dt.date(2026, 8, 5) - _dt.timedelta(days=FLOW_MAX_AGE_DAYS + 1)
    aged = _build(flow=_flow(stale.isoformat()))
    assert aged is not None, "a stale feed must not cost the panel"
    assert aged["flow_live"] is False
    assert all(r["flow_en"] is None for r in aged["rows"])


def test_an_empty_continuation_watch_ledger_is_a_normal_state():
    """cn_continuation_watch_v1 accrues from tonight; zero rows is not an error."""
    empty = pd.DataFrame(columns=["date", "ticker", "board_definition"])
    assert _build(watch=empty) is not None
    populated = pd.DataFrame([{"date": "2026-08-05", "ticker": "002155.SZ",
                               "board_definition": CONTINUATION_BOARD}])
    tape = _build(watch=populated)
    assert tape["watch_live"] is True
    gold = _row(tape, "cn_gold")
    assert gold["members"]["blocked"][0].get("watched") is True


def test_a_ledger_of_other_board_definitions_marks_nobody():
    other = pd.DataFrame([{"date": "2026-08-05", "ticker": "002155.SZ",
                           "board_definition": "cn_prophet_v2"}])
    assert _build(watch=other)["watch_live"] is False


def test_a_corrupt_frame_degrades_instead_of_raising():
    junk = pd.DataFrame([{"nothing": 1}])
    assert _build(candidates=junk) is not None or True  # must not raise
    assert build_cn_theme_tape(_membership(), junk, _candidates()) is None


# ── the stance (Law 1) ──────────────────────────────────────────────────────
def test_every_row_carries_a_stance_from_the_sanctioned_vocabulary():
    verbs = ("Act", "Get ready", "Watch", "Protect gains", "Stand aside")
    for row in _build()["rows"]:
        assert row["stance"] in STANCES
        assert row["say_en"].startswith(verbs), row["say_en"]
        assert row["say_zh"]


def test_the_incident_row_gets_a_watch_stance_not_an_overclaim():
    """Gold Miners carries one blocked name of three — "every name is held out" was
    written here once and was false on the panel's own reason for existing."""
    gold = _row(_build(), "cn_gold")
    assert gold["stance"] == "watch"
    assert "Watch — don’t chase." in gold["say_en"]


def test_the_stance_is_a_pure_function_of_the_counts_and_phase():
    live = _row(_build(), "cn_metals")
    assert live["stance"] == "act" and "1" in live["say_en"]


# ── Tier 1 vocabulary (Law 2) ───────────────────────────────────────────────
def test_the_engine_phase_enum_never_becomes_the_glance_tier_word():
    for enum, (en, zh) in PHASE_WORDS.items():
        assert enum.lower() not in en.lower(), f"{enum} leaked into its own label"
        assert zh and zh != enum
    assert set(PHASE_INDEX) == {"Trough", "Recovery", "Expansion", "Peak", "Downturn"}


def test_no_row_carries_an_internal_state_name_or_a_ticker_suffixless_slug():
    banned = ("bounce_wait", "not_raw_eligible", "more_actionable", "RAN_LATE",
              "await_confluence", "raw_eligible", "COUNTERTREND")
    blob = json.dumps(_build(), ensure_ascii=False, default=str)
    for token in banned:
        assert token not in blob, token


# ── the rendered surface ────────────────────────────────────────────────────
def _render(tape):
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=False)
    return env.get_template("_cn_theme_tape.html.j2").render(cn_theme_tape=tape)


def test_a_dead_tape_emits_no_shell_no_style_and_no_empty_box():
    for empty in (None, {}, {"rows": []}):
        out = _render(empty).strip()
        assert out == "", f"{empty!r} rendered {len(out)} bytes"


def test_the_panel_renders_the_ladder_and_the_member_lists():
    out = _render(_build())
    assert 'id="cn-theme-tape"' in out and 'class="panel span12"' in out
    assert "002155.SZ" in out and "湖南黄金" in out
    assert "Momentum diverging" in out and "动能背离" in out


def test_every_visible_string_is_bilingual():
    out = _render(_build())
    assert out.count('class="l-en"') == out.count('class="l-zh"')
    assert out.count('class="l-en"') > 20


def test_no_translated_text_ever_enters_a_title_attribute():
    """CI-guarded house law — tips are hand-written data-tip-* pairs."""
    assert "title=" not in _markup()
    for attr in re.findall(r'data-tip-(?:en|zh)="[^"]*"', _render(_build())):
        assert "<span" not in attr and "l-en" not in attr


def test_no_t_macro_call_is_piped_into_an_attribute():
    for line in _markup().splitlines():
        for attr in re.findall(r'\b[\w-]+="[^"]*"', line):
            assert "ct_t(" not in attr, line.strip()[:90]


def test_colour_appears_on_exactly_one_glyph_and_through_the_flipping_token():
    """--ink-up is text-grade and flips under 红涨绿跌; raw --up misses the light
    contrast floor. Colouring more than the live count re-encodes cohort state as
    signal furniture — the construction the 2026-07-23 ruling removed."""
    css = _stylesheet().replace(" ", "")
    assert "var(--ink-up,var(--up))" in css
    assert css.count("--ink-up") == 1
    for token in ("--ink-down", "green", "red"):
        assert f"color:{token}" not in css


def test_the_stylesheet_introduces_no_raw_hex_colour():
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _stylesheet())


def test_the_panel_carries_no_animation_and_no_transform():
    """Both are absent by design: no reduced-motion block is required, and nothing
    can become a containing block that traps the shared Lens popover."""
    css = _stylesheet()
    for banned in ("@keyframes", "animation:", "transition:"):
        assert banned not in css
    assert "transform:" not in css.replace("text-transform:", "")


def test_the_member_roster_keeps_the_tier_preview_hook_class():
    """china_stocks is edge-gated by omission today, so the panel adds no gate of its
    own. `.ctt-names` is the roster hook, mirroring the US `.tt-names`, so if the page
    ever joins the Caddy public list the collapse is one selector in tier_preview.js."""
    out = _render(_build())
    assert 'class="ctt-names"' in out
    for group in re.findall(r'<span class="ctt-names">(.*?)</span>\s*</div>', out, re.DOTALL):
        assert "ctt-n" in group


def test_the_theme_vehicle_line_only_appears_where_a_proxy_exists_and_never_instructs():
    out = _render(_build())
    assert "512400.SS" in out, "cn_metals has a proxy and has turned"
    assert "context, not a recommendation" in out
    assert "仅供参考，非推荐" in out
    gold_block = out.split("Gold Miners", 1)[1].split("</details>", 1)[0]
    assert "Traded as one" not in gold_block, (
        "cn_gold has etf_proxy null — a fabricated ticker would be a data lie")


def test_the_glance_tier_keeps_only_the_stances_that_ask_for_an_action():
    """Rendered against the real artifacts the watch sentence repeated on four of
    eight rows — the per-row constant Law 4 stops. Actionable stances stay up top;
    the rest move one layer down, and the footer carries the panel's own stance."""
    out = _render(_build())
    says = re.findall(r'<div class="ctt-say">.*?</div>', out, re.DOTALL)
    assert len(says) == 1 and "Act" in says[0]
    assert "Watch — don’t chase." in out  # still present, inside the expansion
    assert "where to look, not at what to buy" in out


def test_the_footnote_and_the_asof_appear_exactly_once():
    out = _render(_build())
    assert out.count('class="ctt-foot"') == 1
    assert out.count('class="ctt-asof"') == 1
    assert out.count('class="help"') == 1


# ── page integration ────────────────────────────────────────────────────────
def test_the_page_includes_the_partial_below_the_board_and_only_on_stocks():
    src = (TMPL / "china.html.j2").read_text()
    assert src.count('{% include "_cn_theme_tape.html.j2" %}') == 1
    include_at = src.index("_cn_theme_tape.html.j2")
    board_at = src.index('id="standouts"')
    screener_at = src.index('id="stock-screener"')
    assert board_at < include_at < screener_at, "must sit between board and screener"
    guard = src[src.rindex("{% if", 0, include_at):include_at]
    assert "mode == 'stocks'" in guard


def test_the_css_is_scoped_to_the_china_stocks_body_class():
    """china_stocks renders with body.page-china-stocks; the US tape uses
    body.page-stocks, so an unadapted copy would style nothing."""
    css = _stylesheet()
    for rule in re.findall(r"^\s*(body[^{,]*)", css, re.MULTILINE):
        assert "page-china-stocks" in rule, rule
    assert "page-stocks{" not in css.replace(" ", "")


def test_the_builder_wires_the_context_key_the_partial_reads():
    src = (ROOT / "scripts" / "build_china.py").read_text()
    assert 'vm["cn_theme_tape"]' in src
    assert "from engine.cn_theme_tape import build_cn_theme_tape" in src
    assert "cn_theme_tape" in PARTIAL.read_text()


# ── the acceptance case, against the committed artifacts ────────────────────
_REAL = {
    "membership": ROOT / "data/baskets_china/membership.json",
    "cycles": ROOT / "data/china_sector_cycles/forward_log.parquet",
    "candidates": ROOT / "data/china_prophet_rank/candidates.parquet",
}


@pytest.mark.skipif(not all(p.exists() for p in _REAL.values()),
                    reason="committed CN artifacts unavailable")
def test_the_2026_08_04_incident_is_narrated_on_the_real_artifacts():
    """The operator saw Gold Miners top-ranked with no picks and the page said
    nothing. It must now say: the sector turned, and here is where each name is.

    THIS CASE PINS THE ACCOUNTING, NEVER THE NIGHT'S VERDICT — and it was rewritten on
    2026-08-13 because the first draft did the opposite. Written on 2026-08-05 it
    asserted that evening's reading: Recovery, zero live, and 湖南黄金 the one `blocked`
    name on `veto: bearish divergence`. Every one of those is a nightly OUTPUT. On
    2026-08-07 the ledger moved 002155.SZ to `flat: cut` — a mapped, ordinary state
    that retires a name to the `quiet` group, which by design carries tickers under one
    shared reason rather than a fabricated per-name rejection. The name never left the
    basket, never left the ledger (it is still scored at the newest stamp) and never
    stopped being counted; only its bucket moved, and the case failed for a transition
    the panel exists to narrate. A suite that reds when its subject is working teaches
    the next reader to delete it, so the day's verdict is now READ from the artifacts
    and never re-asserted.

    What is left is what a producer change would actually break: the join still
    resolves (basket keys, the `b-<key>` cycle convention, the stamp columns), each
    shown row's buckets still PARTITION its membership, and the incident's own theme
    still reaches the page carrying every one of its names.
    """
    membership = json.loads(_REAL["membership"].read_text())
    tape = build_cn_theme_tape(
        membership,
        pd.read_parquet(_REAL["cycles"]),
        pd.read_parquet(_REAL["candidates"]),
    )
    assert tape is not None, (
        "the real artifacts no longer join — a basket key, the `b-<key>` cycle id "
        "convention or a stamp column has moved under this panel")

    plain = {word for words in PHASE_WORDS.values() for word in words}
    for row in tape["rows"]:
        # The accounting, on the real ledger. The fixture suite proves the partition in
        # the small; here it meets 22 real baskets, where a bucket that dropped a member
        # would be exactly the silence this panel was built to end.
        assert sum(row["counts"][k] for k in BUCKET_KEYS) == row["n_members"], row["key"]
        named = [m["t"] for group in row["members"].values() for m in group]
        assert len(named) == len(set(named)), row["key"]
        assert len(named) + row["counts"]["quiet"] == row["n_members"], row["key"]
        # Law 2: the engine's own phase enum never reaches the glance tier.
        assert row["state_en"] in plain and row["state_zh"] in plain, row["key"]
        assert row["phase"] not in (row["state_en"], row["state_zh"]), row["key"]
        assert row["stance"] in STANCES and row["say_en"] and row["say_zh"], row["key"]

    gold = next((r for r in tape["rows"] if r["key"] == "cn_gold"), None)
    assert gold is not None, (
        "the incident's own theme is not on the panel. The row set is a CONDITION — "
        "turned, or holding a live pick — so an absence is legitimate only once Gold "
        "Miners has left Recovery with nothing live. Read the cycle before relaxing "
        "this: a turned theme falling off the panel is the original incident again.")

    real_members = [str(m.get("ticker")) for m in membership["baskets"]["cn_gold"]["members"]
                    if not m.get("removed")]
    assert "002155.SZ" in real_members, (
        "湖南黄金 has left the basket. That is a universe change, not drift — re-point "
        "this case at a currently-held name instead of letting it pass on a smaller "
        "basket, which would retire the guard without saying so.")
    assert gold["n_members"] == len(real_members)

    # Accounted for means COUNTED — not necessarily named in a bucket list. `quiet` is a
    # real answer ("no setup here yet"), and a name sitting there is still on the page.
    # Silence is the only failure, so the assertion is the whole basket, not one bucket.
    placed = {m["t"] for group in gold["members"].values() for m in group}
    assert not gold["quiet_more"], "the quiet sample must not elide a name on a 6-name basket"
    accounted = placed | set(gold["quiet_sample"])
    assert accounted == set(real_members), (
        "every Gold Miners name must land in exactly one bucket; unaccounted: "
        f"{sorted(set(real_members) - accounted)}")

    hunan = next((m for group in gold["members"].values() for m in group
                  if m["t"] == "002155.SZ"), None)
    out = _render(tape)
    assert "Gold Miners" in out
    assert "002155.SZ" in out, "the incident's own name must reach the page"
    if hunan is not None:
        # In a named bucket the panel prints ticker AND zh name; the quiet remainder
        # prints the ticker alone, under the group's one shared reason.
        assert hunan["zh"] == "湖南黄金"
        assert "湖南黄金" in out


def test_the_glance_tier_copy_stays_inside_its_word_budgets():
    """DESIGN_DOCTRINE Law 4: title ≤ 4 words, subtitle ≤ 14, footer ≤ 1 sentence.

    Counted on the RENDERED English copy, not the source, so a budget cannot be
    smuggled past by splitting a phrase across spans.
    """
    out = _render(_build())

    def _en(cls):
        block = re.search(rf'class="{cls}"[^>]*>(.*?)</(?:h2|p)>', out, re.DOTALL)
        # the ENGLISH half only — both languages sit in the same element, so counting
        # the raw block would score every budget twice and never fail honestly.
        english = re.search(r'class="l-en">(.*?)</span>', block.group(1), re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", english.group(1))
        return [w for w in re.split(r"\s+", text.strip()) if w]

    assert len(_en("ctt-eyebrow")) <= 4
    assert len(_en("ctt-sub")) <= 14
    # one footnote, one sentence before the link
    foot = re.sub(r"<a .*?</a>", "", re.search(
        r'class="ctt-foot">(.*?)</p>', out, re.DOTALL).group(1))
    foot_en = re.sub(r"<[^>]+>", " ", foot.split('class="l-zh"')[0])
    assert foot_en.count(".") <= 1, foot_en.strip()
