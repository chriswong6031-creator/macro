"""Regression tests for four truth fixes on the China Special Situations desk.

The engine (engine/china_special_situations.py) and templates are FROZEN — this
file only pins the already-implemented contract so a regression cannot silently
return. Four contracts, each with the assertion that catches its regression named
in that test's docstring:

  1. GOODWILL DIMENSIONAL CONTRACT — _goodwill_row() units live in the field name,
     never re-derived from magnitude (money stays money, a fraction is scaled to
     percent exactly once).
  2. UNLOCK POPULATION vs DISPLAY — n_large_30d/n_large_7d are computed from the
     full forward population BEFORE the _MAX_ROWS display slice, never from the
     capped `events` list.
  3. INQUIRY REPLY IDENTITY — reply state is resolved per (issuer, named inquiry
     thread), never per issuer alone; an unnamed inquiry is 'undetermined', never
     silently 'replied' or 'open'.
  4. STALE PLANE AUTHORITY — a stale-but-readable plane keeps its last reading on
     screen but is excluded from the hero's aggregate elevated/active tallies and
     from the "board is complete" copy.

Render tests use the same jinja2 Environment pattern as
tests/test_china_special_situations_gate.py's `_env()` helper (autoescape=False,
mirroring scripts/build_china_special_situations.py exactly).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


# ── shared helpers ───────────────────────────────────────────────────────────

def _make_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _env():
    from jinja2 import Environment, FileSystemLoader

    # autoescape=False mirrors scripts/build_china_special_situations.py exactly —
    # this page's t()/tw() macros assume it. Same pattern as test_china_special_
    # situations_gate.py's _env().
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=lambda en: en, tr=lambda en: en,
                        t=lambda en, zh=None: en)
    return env


def _wire(tmp_path, monkeypatch):
    """Point lib.config at an isolated tmp_path data/site tree (house pattern)."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr("lib.config.data_dir", lambda: data_dir)
    monkeypatch.setattr("lib.config.load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    return data_dir


def _filings_row(
    sec_code: str,
    sec_name: str,
    title: str,
    publish_ts: str,
    kind: str = "letter",
    announcement_id: str = "test-001",
) -> dict:
    """Minimal filings.parquet row, matching collectors/china_filings.py schema.

    Same shape as tests/test_china_special_situations_filings_migration.py's
    _filings_row helper (kept local — this file owns no shared fixture module).
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "announcementId": announcement_id,
        "sec_code": sec_code,
        "sec_name": sec_name,
        "org_id": "",
        "title": title,
        "publish_ts": publish_ts,
        "exchange": "szse",
        "category": "inquiry_letter",
        "kind": kind,
        "announcement_type_raw": "问询函",
        "adjunct_url": "/x/PDF.pdf",
        "adjunct_type": "PDF",
        "_collected_at": now,
    }


def _plane(status: str | None, level: str, asof: str = "2026-08-19",
           en: str = "e", zh: str = "z") -> dict:
    """One hand-built plane block for direct _build_hero() unit tests."""
    return {"status": status, "asof": asof, "glance": {"level": level, "en": en, "zh": zh}}


def _base_planes(**overrides) -> dict:
    planes = {
        "unlocks":      _plane("ok", "quiet"),
        "inquiry":      _plane("ok", "quiet"),
        "preannounce":  _plane("ok", "quiet"),
        "buyback":      _plane("ok", "quiet"),
        "pledge":       _plane("ok", "quiet"),
        "st":           _plane("ok", "quiet"),
        "block_trades": _plane("ok", "quiet"),
    }
    planes.update(overrides)
    return planes


def _minimal_snap(hero: dict, planes: dict) -> dict:
    """A full china_special_situations.html.j2 `special=` payload, shaped like
    scan()'s output but built from hand-crafted plane blocks — no parquet I/O.
    """
    return {
        "schema": "china_special_sits.v1", "asof": "2026-08-19",
        "generated_utc": "2026-08-19T00:00:00",
        "hero": hero,
        "unlocks":      {**planes["unlocks"], "events": [], "weekly_strip": []},
        "inquiry":      {**planes["inquiry"], "letters": []},
        "preannounce":  {**planes["preannounce"], "by_type": {}, "top_movers": []},
        "buyback":      {**planes["buyback"], "top": []},
        "pledge":       {**planes["pledge"], "top": []},
        "st":           {**planes["st"], "count": 0, "additions": [], "removals": [], "top_current": []},
        "block_trades": {**planes["block_trades"], "top_premium": [], "top_discount": []},
        "goodwill": None,
        "by_ticker": {},
        "track": None,
        "disclaimer": "Context only", "disclaimer_zh": "仅作背景",
    }


# ═════════════════════════════════════════════════════════════════════════════
# CONTRACT 1 — Goodwill dimensional contract
# ═════════════════════════════════════════════════════════════════════════════

def test_goodwill_row_money_fields_preserve_sign_and_scale():
    """商誉/商誉减值/净资产/净利润规模 map to *_cny, absolute yuan, sign preserved.

    Regression this catches: units re-derived from magnitude instead of the field
    name would either drop the sign or apply the wrong scale.
    """
    from engine.china_special_situations import _goodwill_row

    raw = {
        "商誉": 6.0e10,               # positive
        "商誉减值": -51245300029.7,    # NEGATIVE — must stay negative
        "净资产": 3.0e11,
        "净利润规模": 0.0,             # zero — must stay 0.0, not None
        "商誉占净资产比例": 0.1,
        "商誉减值占净资产比例": 0.1,
        "商誉减值占净利润比例": 0.1,
        "报告期": "2025Q3",
    }
    row = _goodwill_row(raw, "2026-08-19")
    assert row["goodwill_cny"] == 6.0e10
    # THE regression-catching assertion: sign must survive the projection.
    assert row["impairment_cny"] == -51245300029.7
    assert row["net_assets_cny"] == 3.0e11
    assert row["net_profit_cny"] == 0.0          # zero, not None
    assert row["period"] == "2025Q3"


def test_goodwill_row_fraction_scaled_to_percent_exactly_once():
    """商誉占净资产比例 etc. are FRACTIONS (1.0 == 100%); engine multiplies by 100
    exactly once.

    Regression this catches: a double-scale (×100 twice) or a re-derivation from
    magnitude would silently corrupt every ratio on the page (the historical bug:
    2.58% rendered as 0.03%).
    """
    from engine.china_special_situations import _goodwill_row

    raw = {"商誉占净资产比例": 0.025777727056, "报告期": "2025Q3"}
    row = _goodwill_row(raw, "2026-08-19")
    assert abs(row["goodwill_to_net_assets_pct"] - 2.5777727056) < 1e-9


def test_goodwill_row_missing_impairment_yields_none_not_zero():
    """A field the source omits (missing key / '' / NaN) must emit None, never
    0.0 and never ''.

    Regression this catches: a missing impairment silently rendering as a real
    zero (implying "no impairment") instead of "no data".
    """
    from engine.china_special_situations import _goodwill_row

    for missing_variant in ({}, {"商誉减值": ""}, {"商誉减值": float("nan")}):
        row = _goodwill_row(missing_variant, "2026-08-19")
        assert row["impairment_cny"] is None
        assert row["impairment_cny"] != 0.0


def test_goodwill_row_ratio_over_100pct_not_clamped():
    """A ratio > 1.0 (source fraction) passes through as > 100%, never clamped.

    Regression this catches: a defensive min(x, 100) clamp that would silently
    hide a genuinely oversized ratio.
    """
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({"商誉减值占净资产比例": 1.5}, "2026-08-19")
    assert row["impairment_to_net_assets_pct"] == 150.0


def test_goodwill_row_zero_ratio_stays_zero_not_none():
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({"商誉减值占净利润比例": 0.0}, "2026-08-19")
    assert row["impairment_to_net_profit_pct"] == 0.0
    assert row["impairment_to_net_profit_pct"] is not None


def _goodwill_snap(row: dict) -> dict:
    planes = _base_planes()
    snap = _minimal_snap(None, planes)
    snap["goodwill"] = {"status": "ok", "asof": "2026-08-19", "annual_rows": [row]}
    return snap


def test_goodwill_rendered_impairment_is_money_in_yi_with_no_percent_sign():
    """RENDERED: a -51245300029.7 impairment cell shows '-512' (亿, sign kept) and
    carries no '%' — money must never be printed as if it were a ratio.

    Regression this catches: the original bug where the template guessed units
    from magnitude and printed '-51245300029.70%'.
    """
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({"商誉减值": -51245300029.7, "报告期": "2025Q3"}, "2026-08-19")
    html = _env().get_template("china_special_situations.html.j2").render(
        special=_goodwill_snap(row), gate=None)

    m = re.search(r"商誉减值（亿）</span></span><b>([^<]+)</b>", html)
    assert m, "impairment pill not found in rendered goodwill section"
    assert m.group(1) == "-512"
    assert "%" not in m.group(1)
    # THE regression-catching assertion: the literal old-bug string must be absent.
    assert "-51245300029.70%" not in html
    assert "-51245300029.7%" not in html


def test_goodwill_rendered_ratio_is_percent_not_raw_fraction():
    """RENDERED: a 0.025777727056 ratio (2.5777727056 after engine ×100) shows
    '2.58%', never '0.03%' (the historical double-scale bug).
    """
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({"商誉占净资产比例": 0.025777727056, "报告期": "2025Q3"}, "2026-08-19")
    html = _env().get_template("china_special_situations.html.j2").render(
        special=_goodwill_snap(row), gate=None)

    m = re.search(r"商誉占净资产比例</span></span><b>([^<]+)</b>", html)
    assert m, "ratio pill not found in rendered goodwill section"
    assert m.group(1) == "2.58%"
    # THE regression-catching assertion.
    assert "0.03%" not in html


def test_goodwill_rendered_missing_value_is_em_dash():
    """RENDERED: a missing field (net_profit_cny=None) prints '—', never '0' or
    blank.
    """
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({"报告期": "2025Q3"}, "2026-08-19")  # net_profit missing
    assert row["net_profit_cny"] is None
    html = _env().get_template("china_special_situations.html.j2").render(
        special=_goodwill_snap(row), gate=None)

    m = re.search(r"净利润规模（亿）</span></span><b>([^<]+)</b>", html)
    assert m
    assert m.group(1) == "—"


def test_goodwill_rendered_en_view_never_leaks_raw_chinese_source_keys():
    """RENDERED, EN + ZH: the EN half of every goodwill label must be a plain-word
    English label, never a raw Chinese source-column key such as 净利润规模 or
    商誉占净资产比例 (those are legitimate ONLY inside the l-zh twin).

    Regression this catches: a template that emitted the raw dict key as the
    label instead of a translated {en, zh} twin.
    """
    from engine.china_special_situations import _goodwill_row

    row = _goodwill_row({
        "商誉": 1.0, "商誉减值": -1.0, "净资产": 1.0, "净利润规模": 1.0,
        "商誉占净资产比例": 0.1, "商誉减值占净资产比例": 0.1,
        "商誉减值占净利润比例": 0.1, "报告期": "2025Q3",
    }, "2026-08-19")
    html = _env().get_template("china_special_situations.html.j2").render(
        special=_goodwill_snap(row), gate=None)

    start = html.find("Annual figures")
    end = html.find("</details>", start)
    section = html[start:end]
    raw_keys = ["净利润规模", "商誉占净资产比例", "商誉减值占净资产比例",
                "商誉减值占净利润比例", "商誉减值", "净资产"]
    for m in re.finditer(r'<span class="l-en">([^<]*)</span>', section):
        en_text = m.group(1)
        for raw_key in raw_keys:
            assert raw_key not in en_text, (
                f"raw Chinese source key {raw_key!r} leaked into an EN label: {en_text!r}")
    # sanity: the ZH twins ARE present (they're legitimate on the l-zh side)
    assert "净利润规模" in section
    assert "商誉占净资产比例" in section


# ═════════════════════════════════════════════════════════════════════════════
# CONTRACT 2 — Unlock population vs display cap
# ═════════════════════════════════════════════════════════════════════════════

def _today_plus(n: int) -> str:
    return (pd.Timestamp.today().normalize() + pd.Timedelta(days=n)).strftime("%Y-%m-%d")


# 12 large events (float_pct 5.5%..11.0%, strictly distinct so sort order is
# deterministic), 7 inside the next-7-days window (days 1-7), 5 beyond it
# (days 10,15,20,25,29). Chosen so the display slice (_MAX_ROWS=8, sorted desc)
# is exactly the 7 in-week events plus the single next-largest out-of-week event
# — every displayed row is large_flag=True, which is what makes the mutation
# guard below meaningful (a buggy "count from events" would read 8, the true
# population is 12).
_LARGE_UNLOCKS = [
    (11.0, 1), (10.5, 2), (10.0, 3), (9.5, 4), (9.0, 5), (8.5, 6), (8.0, 7),
    (7.5, 10), (7.0, 15), (6.5, 20), (6.0, 25), (5.5, 29),
]
_SMALL_UNLOCKS = [(2.0, 1), (2.0, 3), (2.0, 10), (2.0, 20), (2.0, 29)]


def _write_unlock_fixture(data_dir: Path, large=_LARGE_UNLOCKS, small=_SMALL_UNLOCKS) -> None:
    today_s = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    rows = []
    for i, (pct, day) in enumerate(large):
        rows.append({"ticker": f"L{i}.SZ", "简称": f"Large{i}", "解禁时间": _today_plus(day),
                     "限售股类型": "首发原股东限售股", "占解禁前流通市值比例": pct / 100.0,
                     "实际解禁市值": 1e8, "asof": today_s})
    for i, (pct, day) in enumerate(small):
        rows.append({"ticker": f"S{i}.SZ", "简称": f"Small{i}", "解禁时间": _today_plus(day),
                     "限售股类型": "首发原股东限售股", "占解禁前流通市值比例": pct / 100.0,
                     "实际解禁市值": 1e8, "asof": today_s})
    _make_parquet(data_dir / "china_unlocks" / "detail.parquet", rows)


def test_unlock_population_counts_exceed_display_cap(tmp_path, monkeypatch):
    """n_large_30d/n_events_30d/n_large_7d/n_events_7d are POPULATION counts,
    computed before the _MAX_ROWS display truncation.

    Regression this catches: n_large_30d saturating at _MAX_ROWS (8) instead of
    reporting the true population size (12).
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir)

    from engine import china_special_situations as css
    snap = css.scan()
    u = snap["unlocks"]

    assert len(u["events"]) == css._MAX_ROWS == 8
    # THE regression-catching assertion: population strictly exceeds the cap.
    assert u["n_large_30d"] == 12
    assert u["n_large_30d"] > css._MAX_ROWS
    assert u["n_events_30d"] == 17
    assert u["n_events_7d"] == 9
    assert u["n_large_7d"] == 7


def test_unlock_mutation_guard_large_count_not_recomputed_from_display_slice(tmp_path, monkeypatch):
    """MUTATION-STYLE GUARD: n_large_30d must differ from a naive recount over the
    DISPLAY slice (`events`), because every displayed row in this fixture is
    itself large_flag=True (len 8) while the true population is 12.

    If a future change swapped `n_large_30d = int(fwd["_large"].sum())` for
    something recomputed off `events` (e.g. `len([e for e in events if
    e["large_flag"]])`), this assertion would start passing on a wrong value —
    catching exactly that regression class.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir)

    from engine import china_special_situations as css
    snap = css.scan()
    u = snap["unlocks"]

    naive_recount_from_display = len([e for e in u["events"] if e["large_flag"]])
    assert naive_recount_from_display == 8          # sanity: display slice is all-large
    # THE regression-catching assertion.
    assert u["n_large_30d"] != naive_recount_from_display
    assert u["n_large_30d"] == 12


def test_unlock_glance_names_7day_window_when_large_event_in_week(tmp_path, monkeypatch):
    """The glance sentence's number equals n_large_7d and its wording names the
    7-day window when any large event falls inside it.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir)

    from engine import china_special_situations as css
    snap = css.scan()
    u = snap["unlocks"]

    assert u["n_large_7d"] == 7
    assert f"{u['n_large_7d']} large unlock" in u["glance"]["en"]
    assert f"in the next {css._WEEK_DAYS} days" in u["glance"]["en"]
    assert "30 days" not in u["glance"]["en"]


def test_unlock_glance_names_30day_window_when_large_only_beyond_week(tmp_path, monkeypatch):
    """When large events exist ONLY at days 8..30, the glance names the 30-day
    window and uses n_large_30d, never the 7-day wording.

    Regression this catches: the glance defaulting to the 7-day sentence (or to
    n_large_7d=0) when the only large supply sits just outside the week.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir, large=[(6.0, 10), (6.0, 15), (6.0, 20)], small=[])

    from engine import china_special_situations as css
    snap = css.scan()
    u = snap["unlocks"]

    assert u["n_large_7d"] == 0
    assert u["n_large_30d"] == 3
    assert f"{u['n_large_30d']} large unlock" in u["glance"]["en"]
    assert "in the next 30 days" in u["glance"]["en"]
    assert f"in the next {css._WEEK_DAYS} days" not in u["glance"]["en"]


def test_unlock_week_boundary_day7_inside_day8_outside(tmp_path, monkeypatch):
    """Boundary test: a large unlock exactly _WEEK_DAYS (7) out is INSIDE the
    week; one at day 8 is OUTSIDE it.

    Regression this catches: an off-by-one in the week-window comparison
    (`<=` vs `<`) either including day 8 or excluding day 7.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir, large=[(6.0, 7), (6.0, 8)], small=[])

    from engine import china_special_situations as css
    assert css._WEEK_DAYS == 7
    snap = css.scan()
    u = snap["unlocks"]

    assert u["n_large_30d"] == 2
    # THE regression-catching assertion: only the day-7 event counts as in-week.
    assert u["n_large_7d"] == 1
    assert u["n_events_7d"] == 1


def test_unlock_n_large_is_alias_of_n_large_30d(tmp_path, monkeypatch):
    """Back-compat `n_large` key is an alias of n_large_30d (the true population
    count), never the old display-slice count.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    _write_unlock_fixture(data_dir)

    from engine import china_special_situations as css
    snap = css.scan()
    u = snap["unlocks"]
    assert u["n_large"] == u["n_large_30d"] == 12


# ═════════════════════════════════════════════════════════════════════════════
# CONTRACT 3 — Inquiry reply identity
# ═════════════════════════════════════════════════════════════════════════════

# Curated real-style inquiry topics. IMPORTANT: digit-suffixed formulaic topics
# (e.g. f"事项{i}的问询函") get eaten by _INQ_FILLER_RE (which strips "事项") and
# fall under the 6-char minimum key length — discovered while prototyping this
# fixture. These topics are pre-verified against the real _inquiry_thread_keys().
_TOPIC_ANNUAL_REPORT = "2025年年度报告的信息披露监管问询函"
_TOPIC_RESTRUCTURE = "重大资产重组事项的问询函"
_TOPIC_RELATED_PARTY = "关联交易事项的问询函"
_TOPIC_CONTROL_CHANGE = "控股股东股权变动的问询函"
_TOPIC_FORECAST_REVISION = "业绩预告更正的问询函"
_TOPIC_FUND_USE = "募集资金使用情况的问询函"
_TOPIC_TRADING_ANOMALY = "股票交易异常波动的问询函"


def _letter_title(issuer: str, topic: str) -> str:
    return f"关于收到深圳证券交易所《关于{issuer}{topic}》的公告"


def _reply_title(issuer: str, topic: str) -> str:
    return f"{issuer}关于深圳证券交易所《关于{issuer}{topic}》的回复公告"


def test_inquiry_doc_role_classifies_reply_side_and_deferral():
    """Pure-function sanity for the document-role predicate.

    `kind` alone cannot carry this: collectors.china_filings.classify_kind
    defaults to "letter", so reply-side filings are stored as letters, and a
    延期回复 notice is stored as a reply.
    """
    from engine.china_special_situations import _inquiry_doc_role

    assert _inquiry_doc_role("关于收到深圳证券交易所《关于甲公司年报的问询函》的公告") == "letter"
    # Reply-side organ/adviser forms — 意见 is matched broadly on purpose.
    for t in ("甲公司独立董事关于年度报告信息披露监管问询函所涉事项的独立董事意见",
              "天健会计师事务所关于甲公司审核问询函中有关财务事项的说明",
              "北京市炜衡律师事务所关于《问询函》相关问题的专项法律意见",
              "董事会审计委员会关于公司问询函所涉问题的相关意见",
              "甲公司关于问询函的回复公告"):
        assert _inquiry_doc_role(t) == "reply_side", t
    # A deferral says the reply has NOT been filed.
    assert _inquiry_doc_role("关于延期回复《关于甲公司重大资产重组的问询函》的公告") == "deferral"


def test_inquiry_reply_side_doc_stored_as_letter_is_not_an_open_inquiry(tmp_path, monkeypatch):
    """A reply-side filing stored with kind='letter' must NOT be published as an
    unanswered inquiry — and must instead count as reply evidence.

    Regression this catches: trusting `kind` alone. classify_kind defaults to
    "letter", so on the real store 100 of 140 "letters" are 说明/意见/回复
    filings; counting them as letters asserts open regulatory questions that were
    never asked, while simultaneously discarding the reply evidence they carry.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "甲证科技"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600111", issuer, _letter_title(issuer, _TOPIC_ANNUAL_REPORT),
                     today, kind="letter", announcement_id="l1"),
        # Stored kind='letter' by the collector's default, but plainly reply-side,
        # and it names the SAME inquiry thread as the letter above.
        _filings_row("600111", issuer,
                     f"{issuer}独立董事关于深圳证券交易所《关于{issuer}{_TOPIC_ANNUAL_REPORT}》所涉事项的独立董事意见",
                     today, kind="letter", announcement_id="l2"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    inq = snap["inquiry"]
    # THE regression-catching assertions: the 独立董事意见 is not a letter …
    assert inq["n_letters"] == 1, inq["letters"]
    assert all("意见" not in ltr["title"] for ltr in inq["letters"])
    # … and it DOES answer the genuine letter it names.
    assert inq["n_replied"] == 1
    assert inq["letters"][0]["reply_state"] == "replied"


def test_inquiry_deferral_notice_does_not_mark_a_letter_replied(tmp_path, monkeypatch):
    """A 延期回复 notice must NOT resolve its inquiry to 'replied'.

    Regression this catches: 延期回复 contains 回复 and every such notice in the
    real store is stored kind='reply', so a naive reply-side test would let the
    filing that announces the reply is POSTPONED mark the inquiry answered.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "乙证科技"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600222", issuer, _letter_title(issuer, _TOPIC_RESTRUCTURE),
                     today, kind="letter", announcement_id="l1"),
        _filings_row("600222", issuer,
                     f"{issuer}关于延期回复深圳证券交易所《关于{issuer}{_TOPIC_RESTRUCTURE}》的公告",
                     today, kind="reply", announcement_id="d1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    inq = snap["inquiry"]
    assert inq["n_letters"] == 1, inq["letters"]
    # THE regression-catching assertion: a postponement is not an answer.
    assert inq["letters"][0]["reply_state"] == "open"
    assert inq["letters"][0]["has_reply"] is False
    assert inq["n_open"] == 1


def test_inquiry_thread_keys_extracted_from_book_quoted_title():
    """Pure-function sanity: a 《》-quoted inquiry name produces a non-empty,
    normalised key.
    """
    from engine.china_special_situations import _inquiry_thread_keys

    keys = _inquiry_thread_keys(_letter_title("示例公司", _TOPIC_ANNUAL_REPORT), "示例公司")
    assert keys == ["2025年年度报告信息披露监管问询函"]


def test_inquiry_one_issuer_one_letter_one_matching_reply_is_replied(tmp_path, monkeypatch):
    """Same issuer, one letter, one reply naming the SAME inquiry -> replied."""
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "国投中鲁"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600962", issuer, _letter_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="letter", announcement_id="l1"),
        _filings_row("600962", issuer, _reply_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="reply", announcement_id="r1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    letters = snap["inquiry"]["letters"]
    assert len(letters) == 1
    assert letters[0]["reply_state"] == "replied"
    assert letters[0]["has_reply"] is True


def test_inquiry_two_letters_same_issuer_only_one_reply_flips_only_that_one(tmp_path, monkeypatch):
    """CORE REGRESSION CASE: one issuer, TWO different inquiry letters, a reply
    to only ONE of them. Exactly one letter flips to replied; the other stays
    open.

    Under the OLD ticker-keyed code (has_reply = "does this secCode have any
    reply, regardless of which inquiry"), BOTH letters would have flipped to
    replied. THIS is the assertion that catches that regression: the letter
    with no matching reply must remain 'open'.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "国投中鲁"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600962", issuer, _letter_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="letter", announcement_id="l1"),
        _filings_row("600962", issuer, _letter_title(issuer, _TOPIC_RESTRUCTURE), today,
                     kind="letter", announcement_id="l2"),
        # Reply answers ONLY the annual-report letter.
        _filings_row("600962", issuer, _reply_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="reply", announcement_id="r1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    letters = {l["title"]: l["reply_state"] for l in snap["inquiry"]["letters"]}
    assert letters[_letter_title(issuer, _TOPIC_ANNUAL_REPORT)] == "replied"
    # THE regression-catching assertion: the OTHER letter must stay open, never
    # silently flip because a reply exists for the same ticker.
    assert letters[_letter_title(issuer, _TOPIC_RESTRUCTURE)] == "open"


def test_inquiry_unrelated_reply_naming_different_inquiry_leaves_letter_open(tmp_path, monkeypatch):
    """A reply document exists for the issuer, but it names a DIFFERENT inquiry
    than the letter — the letter stays open.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "国投中鲁"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600962", issuer, _letter_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="letter", announcement_id="l1"),
        _filings_row("600962", issuer, _reply_title(issuer, _TOPIC_RESTRUCTURE), today,
                     kind="reply", announcement_id="r1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    letters = snap["inquiry"]["letters"]
    assert len(letters) == 1
    assert letters[0]["reply_state"] == "open"
    assert letters[0]["has_reply"] is False


def test_inquiry_reply_naming_no_inquiry_does_not_mark_letter_replied(tmp_path, monkeypatch):
    """A reply-side filing whose title names NO inquiry cannot be tied to
    anything — the letter it might have answered stays un-replied.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "国投中鲁"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600962", issuer, _letter_title(issuer, _TOPIC_ANNUAL_REPORT), today,
                     kind="letter", announcement_id="l1"),
        # Reply names no inquiry at all — no 《》, no well-formed bare span.
        _filings_row("600962", issuer, f"{issuer}关于问询函的回复公告", today,
                     kind="reply", announcement_id="r1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    letters = snap["inquiry"]["letters"]
    assert len(letters) == 1
    # THE regression-catching assertion: an unnamed reply must never be treated
    # as evidence the letter was answered.
    assert letters[0]["reply_state"] != "replied"
    assert letters[0]["has_reply"] is False


def test_inquiry_letter_naming_no_inquiry_is_undetermined(tmp_path, monkeypatch):
    """A letter whose title names no inquiry -> 'undetermined', and has_reply is
    False (never an optimistic 'replied' guess, never an accusatory 'open').
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "国投中鲁"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        # A genuine receipt whose title is too bare to name WHICH inquiry: the
        # extracted span normalises to under the minimum key length, so no thread
        # identity exists. (It must not contain a reply-side token such as 说明 or
        # 意见, or it would be a reply-side filing rather than a letter at all.)
        _filings_row("600962", issuer, "关于收到问询函的公告", today,
                     kind="letter", announcement_id="l1"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    letters = snap["inquiry"]["letters"]
    assert len(letters) == 1
    # THE regression-catching assertion.
    assert letters[0]["reply_state"] == "undetermined"
    assert letters[0]["has_reply"] is False


def test_inquiry_duplicate_reply_and_attachment_rows_no_double_count(tmp_path, monkeypatch):
    """Duplicate reply-side rows (a 'reply' AND an 'attachment') for the SAME
    thread must still resolve to exactly one replied letter — no double
    counting.
    """
    data_dir = _wire(tmp_path, monkeypatch)
    # Issuer name must not itself contain a reply-side token (回复/意见/说明…) —
    # the letter title embeds the issuer, so such a name would make the LETTER
    # read as a reply-side filing.
    issuer = "双证科技"
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600700", issuer, _letter_title(issuer, _TOPIC_FUND_USE), today,
                     kind="letter", announcement_id="l1"),
        _filings_row("600700", issuer, _reply_title(issuer, _TOPIC_FUND_USE), today,
                     kind="reply", announcement_id="r1"),
        # A third-party attachment (专项核查意见) referencing the same thread.
        _filings_row("600700", issuer,
                     f"{issuer}关于深圳证券交易所《关于{issuer}{_TOPIC_FUND_USE}》回复的专项核查意见",
                     today, kind="attachment", announcement_id="r2"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    inq = snap["inquiry"]
    assert inq["n_letters"] == 1
    assert inq["n_replied"] == 1
    assert inq["letters"][0]["reply_state"] == "replied"


def test_inquiry_same_issuer_consecutive_dates_resolved_independently(tmp_path, monkeypatch):
    """Two letters from the same issuer on consecutive dates, different
    inquiries — each resolves independently (one replied, one open).
    """
    data_dir = _wire(tmp_path, monkeypatch)
    issuer = "连续两日公司"
    today_ts = pd.Timestamp.today()
    day0 = today_ts.strftime("%Y-%m-%dT09:00:00+08:00")
    day1_ago = (today_ts - pd.Timedelta(days=1)).strftime("%Y-%m-%dT09:00:00+08:00")
    rows = [
        _filings_row("600800", issuer, _letter_title(issuer, _TOPIC_RESTRUCTURE), day1_ago,
                     kind="letter", announcement_id="c1"),
        _filings_row("600800", issuer, _reply_title(issuer, _TOPIC_RESTRUCTURE), day0,
                     kind="reply", announcement_id="c1r"),
        _filings_row("600800", issuer, _letter_title(issuer, _TOPIC_RELATED_PARTY), day0,
                     kind="letter", announcement_id="c2"),
    ]
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    by_title = {l["title"]: l["reply_state"] for l in snap["inquiry"]["letters"]}
    assert by_title[_letter_title(issuer, _TOPIC_RESTRUCTURE)] == "replied"
    assert by_title[_letter_title(issuer, _TOPIC_RELATED_PARTY)] == "open"


def test_inquiry_population_counts_exceed_display_slice(tmp_path, monkeypatch):
    """n_letters, n_open, n_replied, n_undetermined are POPULATION counts over
    the whole window, not the _MAX_ROWS display slice — and they sum to
    n_letters.

    Regression this catches: counts computed off the display slice instead of
    the full letter population (n_letters=10 while len(letters)==8 proves the
    population is bigger than what's shown).
    """
    data_dir = _wire(tmp_path, monkeypatch)
    today = pd.Timestamp.today().strftime("%Y-%m-%dT09:00:00+08:00")

    open_topics = [_TOPIC_RESTRUCTURE, _TOPIC_RELATED_PARTY, _TOPIC_CONTROL_CHANGE]
    replied_topics = [_TOPIC_ANNUAL_REPORT, _TOPIC_FORECAST_REVISION]

    rows = []
    for i in range(5):
        code = f"U{i:03d}"
        # Bare receipt: a real letter, but names no identifiable inquiry.
        rows.append(_filings_row(code, f"未命名公司{i}", "关于收到问询函的公告", today,
                                 kind="letter", announcement_id=f"und{i}"))
    for i, topic in enumerate(open_topics):
        code = f"O{i:03d}"
        # Issuer names deliberately free of reply-side tokens (see above).
        issuer = f"开放科技{i}"
        rows.append(_filings_row(code, issuer, _letter_title(issuer, topic), today,
                                 kind="letter", announcement_id=f"open{i}"))
    for i, topic in enumerate(replied_topics):
        code = f"R{i:03d}"
        issuer = f"回应科技{i}"
        rows.append(_filings_row(code, issuer, _letter_title(issuer, topic), today,
                                 kind="letter", announcement_id=f"rep_l{i}"))
        rows.append(_filings_row(code, issuer, _reply_title(issuer, topic), today,
                                 kind="reply", announcement_id=f"rep_r{i}"))
    _make_parquet(data_dir / "china_filings" / "filings.parquet", rows)

    from engine import china_special_situations as css
    snap = css.scan()
    inq = snap["inquiry"]

    assert inq["n_letters"] == 10
    # THE regression-catching assertion: population exceeds the display slice.
    assert inq["n_letters"] > len(inq["letters"]) == css._MAX_ROWS == 8
    assert inq["n_open"] == 3
    assert inq["n_replied"] == 2
    assert inq["n_undetermined"] == 5
    assert inq["n_open"] + inq["n_replied"] + inq["n_undetermined"] == inq["n_letters"]
    assert inq["n_unreplied"] == inq["n_open"]


def test_inquiry_hero_notable_never_headlines_an_undetermined_letter():
    """hero.notable never headlines an 'undetermined' letter as an unanswered
    question — only a positively-established 'open' letter may be the headline.
    """
    from engine import china_special_situations as css

    blocks = {
        "unlocks": {"status": "ok", "events": []},
        "inquiry": {"status": "ok", "letters": [
            {"reply_state": "undetermined", "secCode": "600000", "secName": "Undetermined Co", "has_reply": False},
        ]},
        "st": {"status": "ok", "additions": []},
        "pledge": {"status": "ok", "top": [], "n_high": 0},
    }
    hero = css._build_hero(blocks)
    # THE regression-catching assertion.
    assert hero["notable"] is None


def test_inquiry_hero_notable_headlines_a_genuinely_open_letter():
    """Sanity companion: a genuinely 'open' letter DOES become the notable item
    (proves the guard above is discriminating, not just always-None)."""
    from engine import china_special_situations as css

    blocks = {
        "unlocks": {"status": "ok", "events": []},
        "inquiry": {"status": "ok", "letters": [
            {"reply_state": "open", "secCode": "600000", "secName": "Open Co", "has_reply": False},
        ]},
        "st": {"status": "ok", "additions": []},
        "pledge": {"status": "ok", "top": [], "n_high": 0},
    }
    hero = css._build_hero(blocks)
    assert hero["notable"] is not None
    assert hero["notable"]["ticker"] == "600000"


def test_inquiry_rendered_undetermined_letter_shows_unconfirmed_tag_en_zh():
    """RENDERED, EN + ZH: an 'undetermined' letter renders the neutral
    `ssx-tag unknown` chip, NOT `ssx-tag replied`.

    Regression this catches: the template's default-to-open/replied fallback
    (`ltr.reply_state | default('open' if not ltr.has_reply else 'replied')`)
    mis-tagging an undetermined letter because reply_state was dropped upstream.
    """
    from engine.china_special_situations import _inquiry_note

    letter = {
        "secCode": "600000", "secName": "Undetermined Co", "title": "关于问询函的说明",
        "date": "2026-08-15", "pdf_url": "", "reply_state": "undetermined",
        "has_reply": False, "type_name": "问询函", "note": _inquiry_note("undetermined"),
    }
    mod = _env().get_template("_china_special_situations_rows.html.j2").module
    html = str(mod.inquiry_rows([letter]))

    assert 'class="ssx-tag unknown"' in html
    assert 'class="ssx-tag replied"' not in html
    assert 'class="ssx-tag open"' not in html
    # EN + ZH twin, both present.
    assert '<span class="l-en">unconfirmed</span>' in html
    assert '<span class="l-zh">状态未确认</span>' in html


# ═════════════════════════════════════════════════════════════════════════════
# CONTRACT 4 — Stale plane authority
# ═════════════════════════════════════════════════════════════════════════════

def test_hero_all_planes_current_all_fresh_and_no_stale(tmp_path, monkeypatch):
    """(a) All planes current -> all_fresh True, n_stale=0, n_unreadable=0."""
    from engine import china_special_situations as css

    hero = css._build_hero(_base_planes())
    assert hero["freshness"]["all_fresh"] is True
    assert hero["n_stale"] == 0
    assert hero["freshness"]["n_unreadable"] == 0
    assert hero["freshness"]["n_fresh"] == hero["freshness"]["n_planes"] == 7


def test_hero_active_plane_stale_excluded_from_n_active():
    """(b) One ACTIVE plane goes stale -> excluded from n_active, all_fresh False.

    Regression this catches: a stale plane still contributing to the aggregate
    n_active tally because the fresh-gate was dropped.
    """
    from engine import china_special_situations as css

    planes = _base_planes(buyback=_plane("ok", "active"),
                          pledge=_plane("stale", "active", asof="2026-08-10"))
    hero = css._build_hero(planes)
    # THE regression-catching assertion: only the FRESH active plane counts.
    assert hero["n_active"] == 1
    assert hero["freshness"]["all_fresh"] is False
    pledge_seg = next(s for s in hero["segments"] if s["key"] == "pledge")
    assert pledge_seg["stale"] is True
    assert pledge_seg["counts_toward_state"] is False


def test_hero_elevated_plane_stale_excluded_and_state_drops(tmp_path, monkeypatch):
    """(c) One ELEVATED plane goes stale, and it was the ONLY elevated plane ->
    excluded from n_elevated, and the aggregate `state` drops from 'elevated'.

    Regression this catches: the aggregate state staying 'elevated' off a stale
    reading that should no longer carry authority.
    """
    from engine import china_special_situations as css

    planes = _base_planes(inquiry=_plane("stale", "elevated", asof="2026-08-05"))
    hero = css._build_hero(planes)
    # THE regression-catching assertion.
    assert hero["n_elevated"] == 0
    assert hero["state"] == "quiet"
    inq_seg = next(s for s in hero["segments"] if s["key"] == "inquiry")
    assert inq_seg["stale"] is True
    assert inq_seg["counts_toward_state"] is False


def test_hero_missing_plane_is_unreadable_quiet_and_counted():
    """(d) A missing plane reads quiet, counts toward nothing (not elevated, not
    active), but IS tallied in n_unreadable.
    """
    from engine import china_special_situations as css

    planes = _base_planes(st={"status": "missing", "asof": None})
    hero = css._build_hero(planes)
    assert hero["freshness"]["n_unreadable"] == 1
    st_seg = next(s for s in hero["segments"] if s["key"] == "st")
    assert st_seg["readable"] is False
    assert st_seg["level"] == "quiet"
    assert st_seg["counts_toward_state"] is False
    assert hero["n_elevated"] == 0
    assert hero["n_active"] == 0


def test_hero_plane_recovers_next_day_counts_again():
    """(e) A plane that was stale yesterday is fresh again today -> counts toward
    the aggregate again, all_fresh returns to True.
    """
    from engine import china_special_situations as css

    day1_planes = _base_planes(buyback=_plane("stale", "active", asof="2026-08-17"))
    day1_hero = css._build_hero(day1_planes)
    assert day1_hero["freshness"]["all_fresh"] is False
    assert day1_hero["n_active"] == 0

    day2_planes = _base_planes(buyback=_plane("ok", "active", asof="2026-08-19"))
    day2_hero = css._build_hero(day2_planes)
    # THE regression-catching assertion: recovery must restore both the tally
    # and the all_fresh flag, not leave the plane permanently excluded.
    assert day2_hero["freshness"]["all_fresh"] is True
    assert day2_hero["n_active"] == 1


def test_hero_rendered_stale_segment_has_is_stale_class_and_no_stalemark_when_fresh():
    """RENDERED: a stale segment's div carries the `is-stale` CSS class and the
    ⏱ stalemark; a fresh segment carries neither.
    """
    from engine import china_special_situations as css

    planes = _base_planes(pledge=_plane("stale", "active", asof="2026-08-10"))
    hero = css._build_hero(planes)
    snap = _minimal_snap(hero, planes)
    html = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=None)

    m = re.search(r'<div class="ssx-seg lv-\w+ is-stale"[^>]*>.*?</div>', html, re.S)
    assert m, "stale segment with is-stale class not found"
    assert "Pledge stress" in m.group(0)
    assert '<span class="stalemark" aria-hidden="true">⏱</span>' in m.group(0)

    # A fresh segment (unlocks) must not carry is-stale.
    m2 = re.search(r'<div class="ssx-seg lv-\w+"[^>]*>.*?Unlock supply.*?</div>', html, re.S)
    assert m2
    assert "is-stale" not in m2.group(0)
    assert "stalemark" not in m2.group(0)


def test_hero_rendered_no_live_and_complete_claim_when_any_plane_stale():
    """RENDERED, gated build: when any plane is stale, the page must NOT claim
    'Every plane above is live and complete', and must instead show the
    coverage line naming the count of current planes and the stale plane's
    asof date.

    Regression this catches: the strongest completeness copy on the page
    (the tier-gate note) contradicting the smallest per-plane chip.
    """
    from engine import china_special_situations as css

    planes = _base_planes(pledge=_plane("stale", "active", asof="2026-08-10"))
    hero = css._build_hero(planes)
    snap = _minimal_snap(hero, planes)
    gate = {"n_preview": 3, "locked": 4, "planes": [], "tier": "essential", "payload": "/x"}
    html = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=gate)

    # THE regression-catching assertion.
    assert "Every plane above is live and complete" not in html
    assert "6 of 7 planes are current" in html
    assert "2026-08-10" in html


def test_hero_rendered_live_and_complete_present_when_all_fresh_and_gated():
    """RENDERED, gated build: when every plane is fresh, the 'live and complete'
    copy IS present and no ssx-coverage staleness line is emitted.
    """
    from engine import china_special_situations as css

    planes = _base_planes()
    hero = css._build_hero(planes)
    snap = _minimal_snap(hero, planes)
    gate = {"n_preview": 3, "locked": 4, "planes": [], "tier": "essential", "payload": "/x"}
    html = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=gate)

    assert "Every plane above is live and complete" in html
    assert 'class="ssx-coverage"' not in html


def test_hero_rendered_freshness_copy_consistent_across_free_and_entitled_render():
    """(f) The FREE gated shell (gate=<dict>) and the ENTITLED/ungated render
    (gate=None) both carry the SAME coverage receipt — the freshness statement
    lives outside the tier gate, so a stale plane is disclosed identically to
    both a free reader and a paying one.

    Regression this catches: any combination where copy claims completeness
    while a plane is stale, in either render.
    """
    from engine import china_special_situations as css

    planes = _base_planes(pledge=_plane("stale", "active", asof="2026-08-10"))
    hero = css._build_hero(planes)
    snap = _minimal_snap(hero, planes)
    gate = {"n_preview": 3, "locked": 4, "planes": [], "tier": "essential", "payload": "/x"}

    html_free = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=gate)
    html_entitled = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=None)

    for html in (html_free, html_entitled):
        assert "Every plane above is live and complete" not in html
        assert "6 of 7 planes are current" in html
        assert "2026-08-10" in html

    # Extract the ssx-coverage paragraph from each and confirm they match —
    # the receipt does not vary with entitlement.
    def _coverage(html):
        m = re.search(r'<p class="ssx-coverage">.*?</p>', html, re.S)
        assert m
        return m.group(0)

    assert _coverage(html_free) == _coverage(html_entitled)


def test_hero_rendered_stance_tally_gate_and_chip_all_agree_when_stale():
    """No combination where the hero tally, stance sentence, gate copy, and
    per-plane chip disagree: when a plane is stale, the tally excludes it
    (n_active reflects only fresh planes), the stance sentence says the board
    is partially stale, the gate note matches, and the chip shows the stale
    status.
    """
    from engine import china_special_situations as css

    planes = _base_planes(buyback=_plane("ok", "active"),
                          pledge=_plane("stale", "active", asof="2026-08-10"))
    hero = css._build_hero(planes)
    snap = _minimal_snap(hero, planes)
    gate = {"n_preview": 3, "locked": 4, "planes": [], "tier": "essential", "payload": "/x"}
    html = _env().get_template("china_special_situations.html.j2").render(special=snap, gate=gate)

    assert hero["n_active"] == 1                       # tally excludes the stale plane
    assert "Part of the board is not current" in hero["stance"]["en"]   # stance caveat
    assert "Part of the board is not current" in html   # rendered stance matches
    assert "Every plane above is live and complete" not in html         # gate copy matches
    assert 'ssx-chip stale">stale</span>' in html        # per-plane chip agrees
