"""W5-B integration tests: CONFIRM-path wiring of the survivorship-honest re-derivation
stats onto the CN Reversal Sleeve page + product promotion.

Covers:
  T1 -- template render: rederive block present when stats JSON available (CONFIRM verdict)
  T2 -- template render: rederive block omitted gracefully when stats JSON absent
  T3 -- template render: noindex meta tag ABSENT (page is now linked)
  T4 -- template render: link to cn_reversal_sleeve.html present in baskets_china
  T5 -- template render: dual-span (l-en / l-zh) in rederive block
  T6 -- builder: rederive_stats key present in compute() payload; None when file absent
  T7 -- builder: _load_rederive_stats returns None gracefully on corrupt JSON
  T8 -- check_title_i18n passes on cn_reversal_sleeve.html.j2 (no CJK in title= attrs)
  T9 -- check_title_i18n passes on baskets_china.html.j2
  T10 -- sleeve build end-to-end smoke: build() completes without exception (sibling build intact)
  T11 -- ASCII attribute delimiters: no Chinese characters inside HTML attribute values
         in the edited portion of cn_reversal_sleeve.html.j2 (data-*-zh bilingual
         carrier attributes exempt — placeholder/tooltip relabel idiom)
  T12 -- sleeve template: backcast section still present and labeled 'upper bound'
  T13 -- rederive_stats JSON has required keys (sanity of the committed artifact)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

TEMPLATES = config.ROOT / "templates"
SLEEVE_TEMPLATE = TEMPLATES / "cn_reversal_sleeve.html.j2"
BASKETS_CHINA_TEMPLATE = TEMPLATES / "baskets_china.html.j2"
REDERIVE_STATS = config.ROOT / "research" / "china_alpha" / "w5" / "w5a_rederive_stats.json"

# --------------------------------------------------------------------------- #
#  helpers                                                                     #
# --------------------------------------------------------------------------- #

def _render_sleeve(tmp_path, rederive_stats=None, backcast=None) -> str:
    """Render cn_reversal_sleeve.html.j2 with a minimal synthetic payload."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    tmpl = env.get_template("cn_reversal_sleeve.html.j2")
    payload = {
        "as_of": "2026-07-03",
        "data_through": "2026-07-03",
        "n_members": 12,
        "n_universe": 60,
        "equal_weight": 1 / 12,
        "construction": {"gate": "none", "weighting": "equal",
                         "rebalance": "monthly", "unit": "deepest_quintile"},
        "screened": {"st": 0, "mcap": 0, "adv": 0},
        "sectors": {"Tech": 3, "Health": 3, "Industrials": 3, "Financials": 3},
        "members": [],
        "n_members_with_context": 0,
        "sizing": {"sleeve_factor": 0.9, "radar_state": "caution", "can_force": False,
                   "radar_as_of": "2026-07-03"},
        "rederive_stats": rederive_stats,
        "backcast": backcast,
        "ledger": {"rows": 2, "artifact": "sleeve.parquet",
                   "conventions": "CSI300-rel", "graded": {"available": False}},
        "presentation": {
            "maxdd_disclosure_pct": -37.6,
            "expected_monthly_hit_pct": 56.0,
            "one_bet_note": "test note",
            "fill_note": "fill note",
            "backcast_caveat": None,
            "passport": {"basis": "measured", "frame": "monthly", "n": 349},
        },
        "reference": {"excess_mo_pct": 0.56, "sharpe": 0.58, "maxdd_pct": -37.6,
                      "hit_pct": 56.0, "n_rebalances": 388},
    }
    return tmpl.render(d=payload, built="2026-07-03 00:00 UTC")


def _minimal_rederive_stats() -> dict:
    """The minimal shape the template consumes."""
    return {
        "verdict": "CONFIRM-ON-AVAILABLE-PLANE",
        "primary": {
            "full": {"n": 349, "mean_pct": 0.426, "t_hac": 3.29, "sharpe": 0.57,
                     "maxdd_pct": -62.8, "hit": 0.539},
            "early": {"n": 138, "mean_pct": 0.597, "t_hac": 2.97},
            "late": {"n": 211, "mean_pct": 0.314, "t_hac": 1.92},
            "post_2024": {"n": 29, "mean_pct": -0.772, "t_hac": -1.6},
        },
        "csi300_reference": {"n": 169, "mean_pct": 1.052, "t_hac": 2.49, "sharpe": 0.67},
        "ls_spread": {"mean_pct": 0.686, "t_hac": 2.52, "sharpe": 0.44},
        "fill_tax": {"close_to_close_pct": 0.51, "fill_realistic_pct": 0.426},
        "per_name_drawdown": {"p1_pct": -26.6, "p5_pct": -17.3, "worst_pct": -62.1},
        "placebo": {"perm_p": 0.0005, "real_t_hac": 3.29},
        "upper_bound_qualifier": "upper bound note",
    }


# --------------------------------------------------------------------------- #
#  T1 — rederive block present when stats available                            #
# --------------------------------------------------------------------------- #
def test_rederive_block_present_when_stats_available(tmp_path):
    html = _render_sleeve(tmp_path, rederive_stats=_minimal_rederive_stats())
    assert "rederive-block" in html
    assert "CONFIRM-ON-AVAILABLE-PLANE" in html
    assert "survivorship-honest" in html.lower() or "rederive" in html.lower()


# --------------------------------------------------------------------------- #
#  T2 — rederive block omitted when stats absent                               #
# --------------------------------------------------------------------------- #
def test_rederive_block_omitted_when_stats_absent(tmp_path):
    html = _render_sleeve(tmp_path, rederive_stats=None)
    assert "rederive-block" not in html
    # page must still render without error
    assert "CN Reversal Sleeve" in html


# --------------------------------------------------------------------------- #
#  T3 — noindex meta tag absent                                                #
# --------------------------------------------------------------------------- #
def test_noindex_absent_from_sleeve_template():
    src = SLEEVE_TEMPLATE.read_text()
    # The meta noindex line must be gone; only a comment about its removal is allowed
    assert '<meta name="robots" content="noindex">' not in src
    # confirm the page does not emit noindex in a render
    html = _render_sleeve(None)
    assert 'content="noindex"' not in html


# --------------------------------------------------------------------------- #
#  T4 — cn_reversal_sleeve.html linked from baskets_china template             #
# --------------------------------------------------------------------------- #
def test_sleeve_linked_from_baskets_china_template():
    src = BASKETS_CHINA_TEMPLATE.read_text()
    assert "cn_reversal_sleeve.html" in src


# --------------------------------------------------------------------------- #
#  T5 — dual-span in the rederive block                                        #
# --------------------------------------------------------------------------- #
def test_rederive_block_has_dual_span(tmp_path):
    html = _render_sleeve(tmp_path, rederive_stats=_minimal_rederive_stats())
    # The rederive section should contain at least one l-en / l-zh pair
    rd_section_start = html.find("rederive-block")
    assert rd_section_start != -1
    section = html[rd_section_start:rd_section_start + 4000]
    assert 'class="l-en"' in section or "l-en" in section
    assert 'class="l-zh"' in section or "l-zh" in section


# --------------------------------------------------------------------------- #
#  T6 — builder: rederive_stats in compute() payload                           #
# --------------------------------------------------------------------------- #
def test_builder_includes_rederive_stats_key(monkeypatch):
    """compute() must return a dict with a 'rederive_stats' key (value may be None
    if the committed JSON file does not exist in the test environment)."""
    # Patch the heavy loaders to return quickly — the key-presence check is what matters.
    import scripts.build_cn_reversal_sleeve as builder
    monkeypatch.setattr(builder, "_load_plane", lambda: None)
    monkeypatch.setattr(builder, "_sizing", lambda: {
        "sleeve_factor": 1.0, "radar_state": None, "can_force": False})
    monkeypatch.setattr(builder, "_member_context", lambda: {})
    result = builder.compute()
    assert "rederive_stats" in result
    # value is either the loaded dict or None — both are valid
    assert result["rederive_stats"] is None or isinstance(result["rederive_stats"], dict)


# --------------------------------------------------------------------------- #
#  T7 — _load_rederive_stats returns None on corrupt JSON                      #
# --------------------------------------------------------------------------- #
def test_load_rederive_stats_returns_none_on_corrupt(tmp_path, monkeypatch):
    import scripts.build_cn_reversal_sleeve as builder
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{bad json")
    monkeypatch.setattr(builder, "_REDERIVE_STATS", corrupt)
    assert builder._load_rederive_stats() is None


def test_load_rederive_stats_returns_none_when_absent(tmp_path, monkeypatch):
    import scripts.build_cn_reversal_sleeve as builder
    monkeypatch.setattr(builder, "_REDERIVE_STATS", tmp_path / "nonexistent.json")
    assert builder._load_rederive_stats() is None


def test_load_rederive_stats_returns_none_missing_verdict_key(tmp_path, monkeypatch):
    import scripts.build_cn_reversal_sleeve as builder
    p = tmp_path / "nostats.json"
    p.write_text('{"primary": {}}')   # missing 'verdict' key
    monkeypatch.setattr(builder, "_REDERIVE_STATS", p)
    assert builder._load_rederive_stats() is None


def test_load_rederive_stats_returns_dict_when_valid(tmp_path, monkeypatch):
    import scripts.build_cn_reversal_sleeve as builder
    p = tmp_path / "stats.json"
    p.write_text(json.dumps({"verdict": "CONFIRM-ON-AVAILABLE-PLANE", "primary": {}}))
    monkeypatch.setattr(builder, "_REDERIVE_STATS", p)
    result = builder._load_rederive_stats()
    assert isinstance(result, dict)
    assert result["verdict"] == "CONFIRM-ON-AVAILABLE-PLANE"


# --------------------------------------------------------------------------- #
#  T8 — check_title_i18n passes on sleeve template                             #
# --------------------------------------------------------------------------- #
def test_check_title_i18n_sleeve_template():
    from scripts.check_title_i18n import find_violations
    violations = find_violations([str(SLEEVE_TEMPLATE)])
    assert violations == [], f"title= i18n violations in sleeve template: {violations}"


# --------------------------------------------------------------------------- #
#  T9 — check_title_i18n passes on baskets_china template                      #
# --------------------------------------------------------------------------- #
def test_check_title_i18n_baskets_china_template():
    from scripts.check_title_i18n import find_violations
    violations = find_violations([str(BASKETS_CHINA_TEMPLATE)])
    assert violations == [], f"title= i18n violations in baskets_china template: {violations}"


# --------------------------------------------------------------------------- #
#  T10 — sleeve build smoke (sibling build intact)                             #
# --------------------------------------------------------------------------- #
def test_sleeve_build_smoke(tmp_path, monkeypatch):
    """build() completes without exception on a synthetic environment where the
    plane is unavailable — returns a dict and doesn't raise.  This proves the
    sibling build still works after the W5-B edits."""
    from lib import config
    import scripts.build_cn_reversal_sleeve as builder

    # Point data_dir at tmp: the plane really IS unavailable (matching the
    # docstring), and compute() early-returns before the ledger append — so
    # data/cn_reversal_sleeve_track/ is never written (MM_DATA_GUARD).
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    result = builder.build(write=False, site=tmp_path)
    assert isinstance(result, dict)
    # the shadow/no_data status is fine when the plane is missing — the point is no exception
    assert result.get("status") in ("ok", "no_data")


# --------------------------------------------------------------------------- #
#  T11 — ASCII attribute delimiters: no CJK inside HTML attribute values       #
# --------------------------------------------------------------------------- #
_CJK_RE = re.compile(r"[一-鿿㐀-䶿　-〿＀-￯]")
_ATTR_RE = re.compile(r'(class|id|href|src|data-[\w-]+|style|aria-[\w-]+)\s*=\s*"([^"]*)"')


def test_no_cjk_in_html_attributes_sleeve_template():
    """No Chinese characters inside HTML attribute values in the sleeve template.
    t() / dual-span is the channel for CJK text, EXCEPT `data-*-zh` carrier
    attributes (e.g. data-ph-zh, data-tip-zh): placeholder/tooltip text cannot
    hold l-en/l-zh spans, so pages store the ZH string in a data attribute and
    relabel on langchange (same idiom china.html.j2 uses).  title= attributes
    stay guarded separately via check_title_i18n (T8/T9)."""
    src = SLEEVE_TEMPLATE.read_text()
    violations = []
    for m in _ATTR_RE.finditer(src):
        attr, val = m.group(1), m.group(2)
        if attr.endswith("-zh"):
            continue
        if _CJK_RE.search(val):
            violations.append(f"CJK in attribute near: {m.group(0)[:80]!r}")
    assert not violations, f"CJK found in HTML attributes:\n" + "\n".join(violations)


# --------------------------------------------------------------------------- #
#  T12 — backcast section still present and relabeled 'upper bound'            #
# --------------------------------------------------------------------------- #
def test_backcast_section_still_present_and_labeled_upper_bound():
    src = SLEEVE_TEMPLATE.read_text()
    # The backcast section heading now includes 'upper bound'
    assert "upper bound" in src.lower() or "上界" in src


def test_sleeve_template_has_backcast_nav_section():
    src = SLEEVE_TEMPLATE.read_text()
    # Core backcast NAV SVG / polyline is still in the template
    assert "bc-stats" in src
    assert "nav.sleeve" in src or "nav_wrap" in src or "nav-wrap" in src


# --------------------------------------------------------------------------- #
#  T13 — committed rederive stats JSON has required keys                       #
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REDERIVE_STATS.exists(), reason="w5a_rederive_stats.json not committed")
def test_committed_rederive_stats_has_required_keys():
    data = json.loads(REDERIVE_STATS.read_text())
    assert "verdict" in data
    assert "primary" in data
    assert "full" in data["primary"]
    assert "fill_tax" in data
    assert "per_name_drawdown" in data
    assert "placebo" in data
    # primary.full must have the key metrics
    full = data["primary"]["full"]
    for k in ("mean_pct", "t_hac", "sharpe", "n"):
        assert k in full, f"primary.full missing key: {k}"


# --------------------------------------------------------------------------- #
#  T14 — RETIRED (was: china.html.j2 links to cn_reversal_sleeve.html)         #
#  PR #1337 "Simplify dashboard copy and footers" deliberately condensed the   #
#  long board caveat that carried the sleeve deep-link; the sleeve page stays  #
#  linked (page not orphaned) via baskets_china.html.j2 — guarded by T4.       #
# --------------------------------------------------------------------------- #
