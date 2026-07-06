"""Tests for the SRSS Phase 4 UI (display-only, shadow tier):

  * engine.subsector_sponsorship.load_display_rows / plain_language — the
    light read+join used by BOTH site-rendering call sites (the
    subsector_rotation.html "Neural Web sponsorship" rails and the
    stock.html.j2 per-ticker chip).
  * scripts.build_subsector_rotation.build_sponsorship_rails — bucketing into
    the 3 rails the template renders.
  * templates/subsector_rotation.html.j2 renders without crashing on both
    populated and empty sponsorship data.
  * no "validated" language (unhedged) and no translated text inside a
    title= attribute anywhere in the new markup.

Covers Phase 4 only — the join/classification rules themselves (SRSS Phase 0
research harness + Phase 2 production adapter) are already tested in
tests/test_sponsorship_phase0.py and tests/test_spine_subsector_sponsorship.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from engine import spine
from engine import subsector_sponsorship as ssp
from scripts.build_subsector_rotation import build_sponsorship_rails
from scripts.check_title_i18n import find_violations

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path


_SNAPS = [
    # widgets: TAILWIND-eligible (leading, rs_mom>0, score>=1, n_members>=3)
    {"date": "2026-07-01", "key": "widgets", "name": "Widgets", "theme": "Industrials",
     "score": 2.0, "rs_mom": 1.5, "accel": 0.5, "quadrant": "leading", "stage": "leading",
     "lean": 1, "members": ["AAA", "BBB", "FFF"]},
    # gadgets: HEADWIND (lagging)
    {"date": "2026-07-01", "key": "gadgets", "name": "Gadgets", "theme": "Tech",
     "score": -1.0, "rs_mom": -2.0, "accel": -1.0, "quadrant": "lagging", "stage": "lagging",
     "lean": -1, "members": ["CCC", "DDD", "EEE"]},
    # gizmos: ROLLOVER (weakening, rs_mom<0, score>0)
    {"date": "2026-07-01", "key": "gizmos", "name": "Gizmos", "theme": "Tech",
     "score": 0.5, "rs_mom": -0.3, "accel": -0.2, "quadrant": "weakening", "stage": "weakening",
     "lean": -1, "members": ["GGG", "HHH", "III"]},
]


def _write_rotation_snapshot(root: Path, rows: list[dict]) -> None:
    p = root / "data" / "subsector_rotation" / "snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed(root: Path) -> None:
    _write_rotation_snapshot(root, _SNAPS)
    fires = [
        {"ticker": "AAA", "as_of": "2026-07-02", "direction": "long", "lane": "buy"},
        {"ticker": "CCC", "as_of": "2026-07-02", "direction": "long", "lane": "buy"},
        {"ticker": "GGG", "as_of": "2026-07-02", "direction": "short", "lane": "avoid"},
    ]
    report = spine.write_subsector_sponsorship(root=root, fires=fires)
    assert report["rows_in"] == 3


# --------------------------------------------------------------------------- #
# engine.subsector_sponsorship.load_display_rows / plain_language
# --------------------------------------------------------------------------- #
def test_load_display_rows_joins_name_theme_and_momentum(root):
    _seed(root)
    rows = ssp.load_display_rows(root=root)
    by_ticker = {r["ticker"]: r for r in rows}
    assert set(by_ticker) == {"AAA", "CCC", "GGG"}
    assert by_ticker["AAA"]["sponsorship_state"] == "TAILWIND"
    assert by_ticker["AAA"]["name"] == "Widgets"
    assert by_ticker["AAA"]["rs_mom"] == pytest.approx(1.5)
    assert by_ticker["CCC"]["sponsorship_state"] == "HEADWIND"
    assert by_ticker["GGG"]["sponsorship_state"] == "ROLLOVER"
    # display_only propagated, never a fabricated read
    assert all(r["display_only"] for r in rows)


def test_load_display_rows_empty_on_missing_parquet(tmp_path):
    empty_root = tmp_path / "no_data"
    (empty_root / "data").mkdir(parents=True)
    assert ssp.load_display_rows(root=empty_root) == []


def test_load_display_rows_zh_lookup(root):
    _seed(root)
    zh = {"widgets": {"name_zh": "小部件", "theme_zh": "工业"}}
    rows = ssp.load_display_rows(root=root, zh_lookup=zh)
    aaa = next(r for r in rows if r["ticker"] == "AAA")
    assert aaa["name_zh"] == "小部件"
    # a key with no zh_lookup entry falls back to the English name (never blank)
    ccc = next(r for r in rows if r["ticker"] == "CCC")
    assert ccc["name_zh"] == ccc["name"]


def test_plain_language_never_says_validated():
    en, zh = ssp.plain_language("V-SaaS", "垂直SaaS", "EARLY_REPAIR", 2.17)
    assert "repair" in en.lower()
    assert "+2.17" in en
    for text in (en, zh, ssp.EPISTEMIC_CAVEAT_EN, ssp.EPISTEMIC_CAVEAT_ZH):
        low = text.lower()
        assert "validated" not in low or "not" in low or "尚未验证" in text or "未验证" in text


# --------------------------------------------------------------------------- #
# scripts.build_subsector_rotation.build_sponsorship_rails
# --------------------------------------------------------------------------- #
def test_build_sponsorship_rails_buckets_by_state(root, monkeypatch):
    _seed(root)
    # build_sponsorship_rails calls engine.subsector_sponsorship.load_display_rows(root=None)
    # internally (config.ROOT default) -- patch config.ROOT so it resolves to our tmp fixture.
    import lib.config as config
    monkeypatch.setattr(config, "ROOT", root)
    payload = {"asof": "2026-07-02", "subsectors": [
        {"key": "widgets", "name": "Widgets", "name_zh": "小部件", "theme": "Industrials", "theme_zh": "工业"},
    ]}
    out = build_sponsorship_rails(payload)
    assert out["total_rows"] == 3
    tickers = {row["ticker"] for row in out["rails"]["repair"]}
    assert "AAA" in tickers
    assert {row["ticker"] for row in out["rails"]["headwind"]} == {"CCC"}
    assert {row["ticker"] for row in out["rails"]["rollover"]} == {"GGG"}
    # zh_lookup passed through from payload["subsectors"]
    aaa = next(r for r in out["rails"]["repair"] if r["ticker"] == "AAA")
    assert aaa["name_zh"] == "小部件"
    assert "plain_en" in aaa and "plain_zh" in aaa


def test_build_sponsorship_rails_degrades_on_bad_payload(tmp_path, monkeypatch):
    # payload missing "subsectors" entirely, AND no parquet on disk -- must not
    # raise, must degrade to empty rails (isolated root: no repo data leaks in).
    import lib.config as config
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(config, "ROOT", tmp_path)
    out = build_sponsorship_rails({})
    assert out["rails"] == {"repair": [], "headwind": [], "rollover": []}
    assert out["total_rows"] == 0


# --------------------------------------------------------------------------- #
# template render smoke — populated + empty
# --------------------------------------------------------------------------- #
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(ROOT / "templates")))


def _sponsorship_vm() -> dict:
    row = {
        "ticker": "AAA", "as_of": "2026-07-02", "rotation_key": "widgets",
        "name": "Widgets", "name_zh": "小部件", "theme": "Industrials", "theme_zh": "工业",
        "sponsorship_state": "TAILWIND", "confidence_tier": "high", "sponsorship_score": 1.2,
        "n_members": 8, "rotation_asof": "2026-07-02", "rs_mom": 1.5, "accel": 0.5,
        "source_lane": "buy", "stale": False, "display_only": True,
        "plain_en": "Group tailwind: Widgets improving, +1.50 RS momentum",
        "plain_zh": "板块顺风：小部件 改善中，相对强度动量 +1.50",
    }
    return {"asof": "2026-07-02", "total_rows": 1,
            "rails": {"repair": [row], "headwind": [], "rollover": []}}


def test_subsector_rotation_renders_with_populated_sponsorship():
    html = _env().get_template("subsector_rotation.html.j2").render(
        generated_utc="2026-07-05", sponsorship=_sponsorship_vm(),
        epi_en=ssp.EPISTEMIC_CAVEAT_EN, epi_zh=ssp.EPISTEMIC_CAVEAT_ZH)
    assert len(html) > 1000
    assert "Neural Web sponsorship" in html
    assert "AAA" in html
    assert 'stock.html#AAA' in html
    assert "rotation/widgets.html" in html


def test_subsector_rotation_renders_with_empty_sponsorship():
    html = _env().get_template("subsector_rotation.html.j2").render(
        generated_utc="2026-07-05", sponsorship={}, epi_en="", epi_zh="")
    assert len(html) > 1000
    assert "Neural Web sponsorship" in html


def test_subsector_rotation_renders_with_no_sponsorship_kwarg_at_all():
    # build_site.py always passes sponsorship=..., but the template must not
    # crash even if a caller forgets (lenient Undefined, not StrictUndefined).
    html = _env().get_template("subsector_rotation.html.j2").render(generated_utc="2026-07-05")
    assert len(html) > 1000


def test_stock_page_renders_with_sponsorship_markup_present():
    html = _env().get_template("stock.html.j2").render()
    assert 'id="r_sponsorship_wrap"' in html
    assert 'id="r_sponsorship"' in html
    assert "renderSponsorship" in html


# --------------------------------------------------------------------------- #
# epistemic + i18n hygiene on the NEW markup only
# --------------------------------------------------------------------------- #
def test_no_unearned_validated_claim_in_new_templates():
    from scripts import check_validated_claims as cvc
    unearned = cvc.scan()
    mine = [u for u in unearned if u["file"] in
            ("templates/subsector_rotation.html.j2", "templates/stock.html.j2")]
    assert mine == [], mine


def test_no_translated_text_in_title_attr_new_templates():
    violations = find_violations([
        str(ROOT / "templates" / "subsector_rotation.html.j2"),
        str(ROOT / "templates" / "stock.html.j2"),
    ])
    assert violations == [], violations


def test_sponsorship_section_uses_data_tip_pattern_not_title():
    src = (ROOT / "templates" / "subsector_rotation.html.j2").read_text(encoding="utf-8")
    start = src.index('class="nws-section"')
    section = src[start:start + 6000]
    assert "data-tip-en=" in section
    assert "data-tip-zh=" in section

    js_src = (ROOT / "templates" / "stock.html.j2").read_text(encoding="utf-8")
    spo_start = js_src.index("function renderSponsorship")
    spo_fn = js_src[spo_start:spo_start + 1500]
    assert "data-tip-en" in spo_fn
    assert "data-tip-zh" in spo_fn
