"""Tests for the DISPLAY-ONLY offshore-attention chip (P2): the wiki_pageviews
collector parse + title map, the abnormal-attention z compute, the display-only
invariant (never scored), and the bilingual discovery chip with the CN/HK caveat.
Synthetic fixtures, no network. See research/WIKI_ATTENTION_CHIP_SPEC.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import wiki_pageviews as wp  # noqa: E402
from engine import i18n  # noqa: E402
from scripts import build_site as bs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


# ---- 1. collector parse ------------------------------------------------------
def test_parse_shape():
    payload = {"items": [
        {"timestamp": "2026050100", "article": "Apple_Inc.", "views": 6966},
        {"timestamp": "2026050200", "article": "Apple_Inc.", "views": 6327},
    ]}
    df = wp._parse(payload)
    assert list(df.columns) == ["views", "log_views"]     # 2-col -> dodges outlier guard
    assert isinstance(df.index, pd.DatetimeIndex) and df.index.is_monotonic_increasing
    assert pd.api.types.is_numeric_dtype(df["views"])
    assert df["views"].iloc[0] == 6966
    # the adapter's validate() accepts it
    out = wp.WikiPageviewsAdapter().validate("AAPL", df)
    assert not out.empty and "views" in out.columns
    assert wp._parse({"items": []}).empty


# ---- 2. ticker->title map + empty-run guard ----------------------------------
def test_ticker_titles_skips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(wp.config, "data_dir", lambda: tmp_path)
    pdir = tmp_path / "profile"
    pdir.mkdir()
    # no wiki_title column at all -> empty map, no exception
    pd.DataFrame({"name": ["Apple"]}, index=["AAPL"]).to_parquet(pdir / "profiles.parquet")
    assert wp._ticker_titles() == {}
    # some titles present, some NaN -> only the resolved ones returned
    pd.DataFrame({"wiki_title": ["Apple_Inc.", None, "Nvidia"]},
                 index=["AAPL", "ZZZ", "NVDA"]).to_parquet(pdir / "profiles.parquet")
    assert wp._ticker_titles() == {"AAPL": "Apple_Inc.", "NVDA": "Nvidia"}


def test_fetch_raises_when_no_titles(monkeypatch):
    monkeypatch.setattr(wp, "_ticker_titles", lambda: {})
    with pytest.raises(ValueError):
        wp.WikiPageviewsAdapter().fetch()


# ---- 3. chip compute / shape -------------------------------------------------
def test_attention_z_and_build(tmp_path, monkeypatch):
    monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
    adir = tmp_path / "attention"
    adir.mkdir()
    idx = pd.bdate_range("2025-11-01", periods=120)
    rng = np.random.default_rng(0)
    spike = pd.Series(1000.0 + rng.normal(0, 20, 120), index=idx)
    spike.iloc[-3:] = 5000.0                               # viral -> high z
    quiet = pd.Series(800.0 + rng.normal(0, 15, 120), index=idx)   # no abnormal attention
    for tk, v in (("LOUD", spike), ("QUIET", quiet)):
        pd.DataFrame({"views": v, "log_views": np.log1p(v)}).to_parquet(adir / f"{tk}.parquet")
    # _attention_z is causal + clipped
    z_loud = bs._attention_z(spike)
    z_quiet = bs._attention_z(quiet)
    assert z_loud is not None and 0 <= z_loud <= 6.0       # clip bound
    assert z_loud > 2.0 and abs(z_quiet) < 2.0
    # build_attention_data writes the json with the right shape
    out = bs.build_attention_data(tmp_path / "site")
    assert set(out["LOUD"]) == {"z", "views", "asof"}
    assert out["LOUD"]["z"] == round(z_loud, 2)
    assert isinstance(out["LOUD"]["views"], int)


# ---- 4. display-only invariant (critical guard) ------------------------------
def test_never_scored():
    for f in ("engine/axes.py", "engine/setups.py", "engine/residual_alpha.py",
              "engine/regime.py"):
        src = (ROOT / f).read_text()
        for tok in ("attention", "wiki_pageviews", "attn_z"):
            assert tok not in src, f"{tok} leaked into {f}"


# ---- 5. bilingual discovery chip + CN/HK caveat ------------------------------
# Renders main's actual discovery `conv(r)` macro (the already-merged `.cchip.attn`
# offshore-attention chip that consumes the attention.json this port produces).
def _render_attn_chip(r):
    from jinja2 import Environment, FileSystemLoader
    src = (TEMPLATES / "discovery.html.j2").read_text()
    pre = src[: src.index("<!DOCTYPE")]                    # t()/help()/conv() macros
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, LEG_LBL={}, tilt_legs=[], attn_threshold=2.0)
    row = {"legs": {}, "ins_buyers": 0, "val_label": None, **r}
    return env.from_string(pre + "{{ conv(r) }}").render(r=row)


def test_chip_bilingual_us():
    html = _render_attn_chip({"ticker": "AAPL", "attn_z": 2.5})
    assert "l-en" in html and "l-zh" in html              # both language spans emitted
    assert "👁" in html and "+2.5σ" in html
    assert "short-horizon reversal" in html and "短期反转" in html
    assert "cchip attn" in html                           # the display-only caution idiom
    assert "intl only" not in html and "仅境外" not in html  # US ticker -> no CN/HK caveat


def test_chip_cnhk_caveat():
    html = _render_attn_chip({"ticker": "600519.SS", "attn_z": 2.5})
    assert "intl only" in html and "仅境外" in html        # CN/HK -> international-attention-only caveat


def test_chip_absent_below_threshold():
    assert "cchip attn" not in _render_attn_chip({"ticker": "AAPL", "attn_z": 1.2})
    assert "cchip attn" not in _render_attn_chip({"ticker": "AAPL", "attn_z": None})
