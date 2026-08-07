"""The US track-record era boundary: the stamp, the frozen pre-era block, and the guard.

Era break ruled by the Fable main loop 2026-08-07
(``research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`` §0.1). ``_ob_mask`` inherited PR
#4732's absolute session anchor by direct import, which moved every published number in
``site/factordata/us_track_ledger.json`` without appearing in that PR's diff, its
blast-radius report, or R5's era-stamp channel. These tests pin the three things that
close it:

  §0.2  the era string is carried IN the artifact, not only in a commit message;
  §0.3  the pre-era headline is preserved and shown — including across repeated
        recomputes, which is where the obvious implementation self-erases;
  ruling the writer REFUSES a headline move that carries no matching stamp, and says so
        with a line-start ::error annotation.

The guard tests drive the REAL ``engine.track_ledger.atomic_write``. A test that
re-implements the comparison would stay green with the guard deleted.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from engine import track_era as te
from engine import track_ledger as tl

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "site" / "factordata" / "us_track_ledger.json"
SNAPSHOT = ROOT / te.US_TRACK_PRE_ERA_SNAPSHOT


def _shipped() -> dict:
    return json.loads(LEDGER.read_text())


# --------------------------------------------------------------------------- #
# §0.2 — the era string is carried in the artifact
# --------------------------------------------------------------------------- #
def test_shipped_artifact_carries_the_active_era_stamp():
    meta = _shipped()["meta"]
    assert meta.get("anchor_era") == te.US_TRACK_ANCHOR_ERA, (
        "site/factordata/us_track_ledger.json must name the construction that produced "
        "its numbers. An unstamped artifact is the state the 2026-08-07 ruling closed."
    )
    assert meta.get("era_from") == te.US_TRACK_ERA_FROM


def test_emit_path_stamps_the_era_on_the_degenerate_return_too():
    """A provenance field with holes is a field a reader must already know to trust."""
    from scripts.grade_us_board import emit_ledger

    doc = emit_ledger([], None, None)
    assert doc["meta"]["anchor_era"] == te.US_TRACK_ANCHOR_ERA
    assert doc["meta"]["pre_era"]["summary"]["win_pct"] == 63.6


# --------------------------------------------------------------------------- #
# §0.3 — the pre-era headline is preserved, and stays preserved
# --------------------------------------------------------------------------- #
def test_pre_era_block_matches_the_committed_frozen_snapshot():
    """The constant is pinned to the committed evidence file, not to itself.

    ``reports/us_track_ledger_pre_era_2026-07-31.json`` is the last artifact published
    under the retired construction, byte-copied. If someone edits the constant to make a
    number nicer, this fails.
    """
    assert SNAPSHOT.exists(), f"missing frozen pre-era snapshot: {te.US_TRACK_PRE_ERA_SNAPSHOT}"
    snap = json.loads(SNAPSHOT.read_text())
    assert snap["as_of"] == te.US_TRACK_PRE_ERA_AS_OF
    assert snap["summary"] == te.US_TRACK_PRE_ERA_SUMMARY, (
        "the frozen pre-era summary and the committed snapshot have diverged"
    )
    # The named headline the ruling preserves, spelled out so a silent edit is loud.
    assert te.US_TRACK_PRE_ERA_SUMMARY["expectancy_pct"] == 1.19
    assert te.US_TRACK_PRE_ERA_SUMMARY["win_pct"] == 63.6
    assert te.US_TRACK_PRE_ERA_SUMMARY["ci_lo_pct"] == 55.6
    assert te.US_TRACK_PRE_ERA_SUMMARY["ci_hi_pct"] == 69.8


def test_shipped_artifact_preserves_the_pre_era_headline():
    pre = _shipped()["meta"]["pre_era"]
    assert pre["anchor_era"] == te.US_TRACK_PRE_ERA_NAME
    assert pre["as_of"] == te.US_TRACK_PRE_ERA_AS_OF
    assert pre["summary"] == te.US_TRACK_PRE_ERA_SUMMARY
    assert pre["snapshot"] == te.US_TRACK_PRE_ERA_SNAPSHOT


def test_pre_era_block_is_byte_stable_across_repeated_recomputes(tmp_path):
    """The failure this design exists to prevent.

    The obvious implementation — "on write, copy the OUTGOING file's summary into
    meta.pre_era" — is self-erasing: the second recompute preserves the FIRST
    recompute's numbers and the genuine pre-era headline is gone after one night. Three
    successive writes with three different headlines must leave ``pre_era`` identical.
    """
    path = tmp_path / "us_track_ledger.json"
    seen = []
    for i, win in enumerate((59.4, 61.0, 44.2)):
        doc = tl.build_shell(
            "US", f"2026-08-0{i + 1}", "scored", {"code": "SPY", "en": "S&P 500", "zh": "标普500"},
            summary={"win_pct": win, "expectancy_pct": 0.75 + i, "n_matured": 300 + i},
            rows=[], grain="episode", extra_meta=te.us_era_meta(),
        )
        assert tl.atomic_write(path, doc) is True
        seen.append(json.loads(path.read_text())["meta"]["pre_era"])

    assert seen[0] == seen[1] == seen[2] == te.us_pre_era_block()
    assert seen[-1]["summary"]["win_pct"] == 63.6, "the genuine pre-era headline was overwritten"


def test_us_pre_era_block_hands_out_an_isolated_copy():
    """A caller mutating the returned block must not poison the next write."""
    a = te.us_pre_era_block()
    a["summary"]["win_pct"] = 99.9
    a["as_of"] = "tampered"
    b = te.us_pre_era_block()
    assert b["summary"]["win_pct"] == 63.6
    assert b["as_of"] == te.US_TRACK_PRE_ERA_AS_OF


# --------------------------------------------------------------------------- #
# The guard — driven through the real writer
# --------------------------------------------------------------------------- #
def _seed(tmp_path) -> tuple[Path, dict]:
    """A published, correctly stamped ledger on disk + the doc that produced it."""
    doc = tl.build_shell(
        "US", "2026-07-31", "scored", {"code": "SPY", "en": "S&P 500", "zh": "标普500"},
        summary={"win_pct": 59.4, "expectancy_pct": 0.75, "profit_factor": 1.38,
                 "capture": 0.38, "ci_lo_pct": 52.6, "ci_hi_pct": 64.9, "n_matured": 374},
        rows=[], grain="episode", extra_meta=te.us_era_meta(),
    )
    path = tmp_path / "us_track_ledger.json"
    assert tl.atomic_write(path, doc) is True
    return path, doc


def test_guard_refuses_an_unstamped_write_that_moves_the_headline(tmp_path, capsys):
    path, doc = _seed(tmp_path)
    bad = copy.deepcopy(doc)
    bad["meta"].pop("anchor_era")
    bad["summary"]["win_pct"] = 71.0

    assert tl.atomic_write(path, bad) is False, "an unstamped headline move must not publish"
    assert json.loads(path.read_text())["summary"]["win_pct"] == 59.4, (
        "the previously published file must be left in place on refusal"
    )

    out = capsys.readouterr().out
    err_lines = [ln for ln in out.splitlines() if "track-ledger-era" in ln]
    assert err_lines, "the refusal must be visible in the Actions summary"
    # House law: annotations must START the line, emitted by a bare print. A logger would
    # prefix the level and GitHub would silently drop it.
    assert err_lines[0].startswith("::error title=track-ledger-era::"), err_lines[0]
    assert "REFUSED" in err_lines[0]


def test_guard_refuses_a_stale_stamp_that_moves_the_headline(tmp_path, capsys):
    """A stamp naming some OTHER construction is not a matching stamp."""
    path, doc = _seed(tmp_path)
    bad = copy.deepcopy(doc)
    bad["meta"]["anchor_era"] = "series-first-legacy"
    bad["summary"]["expectancy_pct"] = 2.4

    assert tl.atomic_write(path, bad) is False
    assert json.loads(path.read_text())["summary"]["expectancy_pct"] == 0.75
    assert any(ln.startswith("::error title=track-ledger-era::")
               for ln in capsys.readouterr().out.splitlines())


def test_guard_publishes_a_stamped_headline_move(tmp_path):
    """The nightly must keep working: accrual moves the headline every night."""
    path, doc = _seed(tmp_path)
    ok = copy.deepcopy(doc)
    ok["summary"]["win_pct"] = 61.9
    ok["summary"]["n_matured"] = 402

    assert tl.atomic_write(path, ok) is True
    assert json.loads(path.read_text())["summary"]["win_pct"] == 61.9


def test_guard_ignores_counts_moving_on_their_own(tmp_path):
    """Sample counts grow nightly by ordinary accrual — not the silent re-bake."""
    path, doc = _seed(tmp_path)
    same = copy.deepcopy(doc)
    same["meta"].pop("anchor_era")
    same["summary"]["n_matured"] = 999

    assert tl.atomic_write(path, same) is True


def test_guard_does_not_fence_the_other_three_markets(tmp_path):
    """CN / HK / CA carry no ruled era boundary and must be untouched by this guard."""
    doc = tl.build_shell("CN", "2026-07-31", "scored", {"code": "000300"},
                         summary={"win_pct": 50.0}, rows=[], grain="board_day")
    p = tmp_path / "cn_track_ledger.json"
    assert tl.atomic_write(p, doc) is True
    moved = copy.deepcopy(doc)
    moved["summary"]["win_pct"] = 80.0
    assert tl.atomic_write(p, moved) is True
    assert json.loads(p.read_text())["summary"]["win_pct"] == 80.0


def test_guard_allows_a_first_write_with_no_predecessor(tmp_path):
    """Nothing on disk means nothing has moved — a first write is never a re-bake."""
    doc = tl.build_shell("US", "2026-07-31", "scored", {"code": "SPY"},
                         summary={"win_pct": 59.4}, rows=[], grain="episode")
    assert tl.atomic_write(tmp_path / "us_track_ledger.json", doc) is True


def test_guard_fails_closed_when_it_cannot_run(tmp_path, monkeypatch, capsys):
    """A guard that could not RUN is not a guard that passed — for the fenced artifact.

    The other three markets still publish, so a broken US guard cannot wedge their
    nightly.
    """
    path, doc = _seed(tmp_path)
    import builtins

    real_import = builtins.__import__

    def _boom(name, *a, **kw):
        if name == "engine" and "track_era" in (a[2] or ()) if len(a) > 2 and a[2] else False:
            raise ImportError("simulated")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(te, "check_publish",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated")))
    moved = copy.deepcopy(doc)
    moved["summary"]["win_pct"] = 71.0
    assert tl.atomic_write(path, moved) is False
    assert json.loads(path.read_text())["summary"]["win_pct"] == 59.4
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "track-ledger-era" in ln]
    assert lines and lines[0].startswith("::error title=track-ledger-era::")

    cn = tl.build_shell("CN", "2026-07-31", "scored", {"code": "000300"},
                        summary={"win_pct": 50.0}, rows=[], grain="board_day")
    assert tl.atomic_write(tmp_path / "cn_track_ledger.json", cn) is True


def test_guarded_basename_constants_agree():
    """The fail-closed branch runs when track_era could not be imported, so it carries its
    own copy of the fenced filename. Pin the two equal."""
    assert tl.ERA_GUARDED_LEDGER == te.GUARDED_BASENAME == "us_track_ledger.json"


@pytest.mark.parametrize("prev,new,expect", [
    ({"win_pct": None}, {"win_pct": None}, []),                 # null vs null is not a move
    ({"win_pct": 59.4}, {"win_pct": 59.43}, []),                # inside one rounding step
    ({"win_pct": 59.4}, {"win_pct": 59.5}, ["win_pct"]),
    ({"win_pct": None}, {"win_pct": 59.4}, ["win_pct"]),        # a number appearing is a move
    ({"win_pct": 59.4}, {"win_pct": None}, ["win_pct"]),        # and so is one vanishing
    ({"capture": 0.38}, {"capture": 0.42}, ["capture"]),        # ratios get a tighter floor
    ({"n_matured": 173}, {"n_matured": 374}, []),               # counts are not the headline
])
def test_headline_moves_tolerance(prev, new, expect):
    assert te.headline_moves(prev, new) == expect


# --------------------------------------------------------------------------- #
# Surfaces — the old numbers are SHOWN, not just stored (§0.3)
# --------------------------------------------------------------------------- #
_PRIOR = {"as_of": "2026-07-31", "era_from": "2026-08-07",
          "win_pct": 63.6, "expectancy_pct": 1.19, "n_matured": 173}

#: Internal vocabulary that must never reach a reader on these surfaces. "era break" and
#: "anchor" are this program's own words; "validated" is CI-guarded house-wide; the
#: falsifier family is banned front-facing by standing operator order (2026-07-27).
_BANNED = ("era break", "anchor_era", "abs-session", "_ob_mask", "StochRSI", "resample",
           "validated", "falsifier", "refuted", "证伪", "re-bake")


def _visible_text(html: str) -> str:
    """Rendered copy a reader can actually see or hover, minus script/style blocks."""
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return body


def _render_track_record_page(**over) -> str:
    import jinja2

    vm = dict(
        as_of="2026-08-07", outcomes_as_of="2026-07-31", sb_as_of="2026-08-07",
        win_rate_pct=59.4, avg_pct=0.75, n_outcomes=374, n_running=200, n_stopped=0,
        n_skipped=3, hero_ci=(52.6, 64.9), hero_board_days=18, hero_horizon=10,
        hero_inflight=200, hero_exp_lo=-0.1, hero_exp_hi=1.46,
        prior_era=dict(_PRIOR), era_from="2026-08-07",
        horizon_ladder=[], chart_series_h5_json="[]", chart_series_h10_json="[]",
        board_series=[], board_series_accruing=True, outcomes_rows=[],
        failure_mix_data_gap=True, failure_mix={}, coverage_monitor={}, gate_suppressed={},
        buy_lane_rows=0, all_lanes_rows=0, survivorship={}, cohort_accruing=False,
        track_history={},
    )
    vm.update(over)
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
                             autoescape=True)
    return env.get_template("us_track_record.html.j2").render(**vm)


def test_track_record_page_shows_both_measurements_side_by_side():
    html = _render_track_record_page()
    assert '<div class="tr-basis">' in html
    block = html.split('<div class="tr-basis">', 1)[1].split("<!-- ── Section 2", 1)[0]

    # BOTH columns, both headline numbers, in one place a reader can compare.
    assert "Before · to 2026-07-31" in block and "此前 · 截至 2026-07-31" in block
    assert ">Now<" in block or "Now</span>" in block
    assert ">64%<" in block and ">+1.2%<" in block and ">173<" in block   # prior
    assert ">59%<" in block and ">+0.8%<" in block and ">374<" in block   # current

    # The reason, in plain words, in both languages.
    assert "Measurement updated" in block and "计量方式已更新" in block
    assert "How picks are chosen, bought and sold has not changed." in block
    assert "选股、买入和卖出的规则没有任何改动。" in block
    # And the honest caveat that the count moved too — without it a reader reads the
    # whole drop as the measurement change, which is false.
    assert "374 trades have finished now against 173" in block
    assert "现已走完 374 笔交易" in block


def test_track_record_page_block_is_absent_without_a_prior_measurement():
    html = _render_track_record_page(prior_era=None, era_from=None)
    assert '<div class="tr-basis">' not in html


def test_track_record_page_block_is_absent_while_the_record_is_accruing():
    """No current headline means nothing to compare against."""
    html = _render_track_record_page(win_rate_pct=None, avg_pct=None, n_outcomes=None)
    assert '<div class="tr-basis">' not in html


def test_track_record_page_stance_follows_the_average_trade_interval():
    """A 59% win rate does not earn a following verdict while the honest range for what a
    trade returns still reaches below zero — the same rule the dialog applies."""
    html = _render_track_record_page()
    assert "still reaches below zero" in html
    assert "仍可能低于零" in html
    assert "More winners than losers — watch, do not chase new entries." not in html
    # ... and the ordinary branch is untouched when the interval clears zero.
    clear = _render_track_record_page(hero_exp_lo=0.4)
    assert "More winners than losers — watch, do not chase new entries." in clear


def test_track_record_page_copy_carries_no_internal_vocabulary():
    text = _visible_text(_render_track_record_page())
    for term in _BANNED:
        assert term.lower() not in text.lower(), f"internal vocabulary reached the page: {term}"


def test_track_record_dialog_shows_the_comparison_and_the_chip_receipt():
    from tests.test_track_record_dlg import _render_partial, _scored_trd

    html = _render_partial(_scored_trd(
        stats=dict(win_pct=59.4, expectancy_pct=0.75, n_matured=374, n_inflight=200,
                   n_board_days=18, exp_lo_pct=-0.1, exp_hi_pct=1.46, ci_lo_pct=52.6,
                   ci_hi_pct=64.9, horizon=10, metric="pnl"),
        prior_era=dict(_PRIOR)))

    # Dialog: full side-by-side.
    assert '<div class="trd-basis">' in html
    assert "Before · to 2026-07-31" in html and "此前 · 截至 2026-07-31" in html
    assert ">64%<" in html and ">+1.19%<" in html and ">173<" in html
    assert ">59%<" in html and ">+0.75%<" in html and ">374<" in html

    # Chip: a Tier-2 receipt, not a copy dump. The visible label is two words; the old
    # numbers and the reason live in the hover.
    m = re.search(r'<span class="trd-basis-chip"(.*?)>'
                  r'<span class="l-en">(.*?)</span><span class="l-zh">(.*?)</span></span>',
                  html, re.S)
    assert m, "the chip receipt marker did not render"
    attrs, label_en, label_zh = m.groups()
    assert "data-tip-en=" in attrs and "data-tip-zh=" in attrs
    assert "64% made money" in attrs and "盈利占比 64%" in attrs
    # The visible label stays at glance tier — every number lives in the hover.
    assert label_en == "measurement updated" and label_zh == "計量已更新".replace("計", "计")
    assert not re.search(r"\d", label_en + label_zh)


def test_track_record_dialog_comparison_is_optional_and_type_safe():
    from tests.test_track_record_dlg import _render_partial, _scored_trd

    assert '<div class="trd-basis">' not in _render_partial(_scored_trd())
    # A producer field of the wrong type must degrade, never take the host page down.
    for bad in ("nope", 123, [], 0, {}, {"as_of": "x"}):
        html = _render_partial(_scored_trd(prior_era=bad))
        assert '<div class="trd-basis">' not in html
        assert 'class="trd-basis-chip"' not in html


def test_track_record_dialog_keeps_translated_text_out_of_title_attributes():
    """House law, CI-guarded elsewhere — re-pinned here because this PR adds ZH copy."""
    from tests.test_track_record_dlg import _render_partial, _scored_trd

    html = _render_partial(_scored_trd(prior_era=dict(_PRIOR)))
    for attr in re.findall(r'\btitle="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", attr), f"CJK inside title=: {attr!r}"


def test_track_record_dialog_copy_carries_no_internal_vocabulary():
    from tests.test_track_record_dlg import _render_partial, _scored_trd

    text = _visible_text(_render_partial(_scored_trd(prior_era=dict(_PRIOR))))
    for term in _BANNED:
        assert term.lower() not in text.lower(), f"internal vocabulary reached the chip: {term}"


def _us_ledger(meta: dict) -> dict:
    return {
        "schema": "track_ledger/v1", "market": "US", "as_of": "2026-07-31",
        "state": "scored",
        "summary": {"metric": "pnl", "horizon": 10, "win_pct": 59.4,
                    "expectancy_pct": 0.75, "n_matured": 374, "n_inflight": 200,
                    "n_board_days": 18, "exp_lo_pct": -0.1, "exp_hi_pct": 1.46,
                    "ci_lo_pct": 52.6, "ci_hi_pct": 64.9, "median_hold": 10},
        "rows": [], "meta": meta,
    }


def test_dashboard_host_passes_the_prior_measurement_to_the_partial():
    """The host contract: meta.pre_era on the artifact -> trd.prior_era on the chip."""
    from tests.test_track_record_dlg import _US_OUTCOMES, _render_dashboard

    html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES,
                             us_track_ledger=_us_ledger({
                                 "grain": "episode",
                                 "anchor_era": te.US_TRACK_ANCHOR_ERA,
                                 "era_from": "2026-08-07",
                                 "pre_era": {"anchor_era": te.US_TRACK_PRE_ERA_NAME,
                                             "as_of": "2026-07-31",
                                             "summary": dict(te.US_TRACK_PRE_ERA_SUMMARY)}}))
    assert 'class="trd-basis-chip"' in html
    assert '<div class="trd-basis">' in html
    assert "此前 · 截至 2026-07-31" in html
    assert ">64%<" in html and ">173<" in html


def test_dashboard_host_survives_an_artifact_with_no_pre_era_block():
    """Every other market's ledger, and any pre-2026-08-07 US artifact, has no pre_era."""
    from tests.test_track_record_dlg import _US_OUTCOMES, _render_dashboard

    for meta in ({"grain": "episode"},
                 {"grain": "episode", "pre_era": "not a dict"},
                 {"grain": "episode", "pre_era": {"as_of": "2026-07-31"}}):
        html = _render_dashboard("stocks", us_board_outcomes=_US_OUTCOMES,
                                 us_track_ledger=_us_ledger(meta))
        assert 'id="trd-btn"' in html, "the chip itself must still render"
        assert 'class="trd-basis-chip"' not in html
        assert '<div class="trd-basis">' not in html
