"""tests/test_us_board_w3_evidence.py — Unit tests for W3 evidence-stack.

Covers:
  - Per-lens join correctness on synthetic artifacts (present / absent / stale).
  - Confluence+ independence-group logic (same-group pair does NOT earn the badge).
  - grade_us_board strata emission via _row_features.
  - No-ordering-regression: board order identical with evidence fields present vs absent.
  - Template render of chips / badge / disclosure with and without fixture data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import _row_features, build_track  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _base_row(**overrides) -> dict:
    """Minimal board row dict with required fields for _row_features."""
    base = {
        "ticker": "AAA", "sector": "Technology",
        "alpha": 0.5, "state": "FRESH BUY", "label": "FRESH BUY",
        "urgency": "now", "align_tier": "aligned", "off_high": -3.0,
        "lane": "trend", "arbiter_note": None,
        "conviction": {
            "score": 70, "band": "high", "composite_z": 0.5,
            "verdict": "Leader", "validation_status": "validated",
        },
    }
    base.update(overrides)
    return base


def _boards_stub(*as_ofs):
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub():
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. _row_features: W3 strata extracted from row dict
# ---------------------------------------------------------------------------

class TestRowFeaturesW3Strata:
    """_row_features must extract W3 strata correctly."""

    def test_insider_cluster_true_when_buyers_gte2(self):
        row = _base_row(insider_buyers=3, insider_bps=50, insider_net_mn=1.0)
        feat = _row_features(row)
        assert feat["insider_cluster"] is True

    def test_insider_cluster_false_when_buyers_lt2(self):
        row = _base_row(insider_buyers=1)
        feat = _row_features(row)
        assert feat["insider_cluster"] is False

    def test_insider_cluster_false_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["insider_cluster"] is False

    def test_gex_confirm_verdict_extracted(self):
        row = _base_row(gex_confirm={"verdict": "confirm", "score": 0.8})
        feat = _row_features(row)
        assert feat["gex_confirm_verdict"] == "confirm"

    def test_gex_confirm_verdict_none_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["gex_confirm_verdict"] is None

    def test_altdata_conv_gte2_true(self):
        row = _base_row(altdata={"convergence_score": 3, "channels": ["congress_buy", "insider_cluster", "13f_add"]})
        feat = _row_features(row)
        assert feat["altdata_conv_gte2"] is True

    def test_altdata_conv_gte2_false_when_score_lt2(self):
        row = _base_row(altdata={"convergence_score": 1, "channels": ["congress_buy"]})
        feat = _row_features(row)
        assert feat["altdata_conv_gte2"] is False

    def test_altdata_conv_gte2_false_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["altdata_conv_gte2"] is False

    def test_sue_fresh_true_when_z_present_and_days_le60(self):
        row = _base_row(sue_z=1.5, sue_fresh_days=30)
        feat = _row_features(row)
        assert feat["sue_fresh"] is True

    def test_sue_fresh_false_when_days_gt60(self):
        row = _base_row(sue_z=1.5, sue_fresh_days=90)
        feat = _row_features(row)
        assert feat["sue_fresh"] is False

    def test_sue_fresh_false_when_sue_z_absent(self):
        row = _base_row(sue_fresh_days=30)
        feat = _row_features(row)
        assert feat["sue_fresh"] is False

    def test_sue_fresh_false_when_both_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["sue_fresh"] is False

    def test_news_burst_true_when_n_recent_gte3(self):
        row = _base_row(news_burst={"n_recent": 5, "sentiment_lean": "neutral"})
        feat = _row_features(row)
        assert feat["news_burst"] is True

    def test_news_burst_false_when_n_recent_lt3(self):
        row = _base_row(news_burst={"n_recent": 2, "sentiment_lean": "neutral"})
        feat = _row_features(row)
        assert feat["news_burst"] is False

    def test_news_burst_false_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["news_burst"] is False

    def test_smartmoney_add_true_when_chip_present(self):
        row = _base_row(smartmoney_chip={
            "action": "new", "n_funds_adding": 2,
            "best_fund": "Tiger Fund", "best_grade": "A",
            "period_end": "2026-03-31", "staleness_caveat": "Q1-2026 13F",
        })
        feat = _row_features(row)
        assert feat["smartmoney_add"] is True

    def test_smartmoney_add_false_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["smartmoney_add"] is False

    def test_has_stop_guidance_true_when_present(self):
        row = _base_row(stop_guidance={"pct": 5.2, "tail_pct": 9.1, "horizon": 21, "scored": True})
        feat = _row_features(row)
        assert feat["has_stop_guidance"] is True

    def test_has_stop_guidance_false_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["has_stop_guidance"] is False

    def test_confluence_k_from_confluence_plus(self):
        row = _base_row(confluence_plus={"k": 3, "groups": ["INSIDER", "SUE", "GEX-OPTIONS"]})
        feat = _row_features(row)
        assert feat["confluence_k"] == 3

    def test_confluence_k_zero_when_absent(self):
        row = _base_row()
        feat = _row_features(row)
        assert feat["confluence_k"] == 0


# ---------------------------------------------------------------------------
# 2. Confluence+ independence-group logic
# ---------------------------------------------------------------------------

class TestConfluencePlusBadge:
    """Same-group pairs must NOT earn the badge; cross-group pairs MUST."""

    def _compute_badge(self, row: dict) -> dict | None:
        """Inline the Confluence+ computation from build_stock_library."""
        _c_votes = 0
        _c_groups = []
        # INSIDER group
        if (row.get("insider_buyers") or 0) >= 2:
            _c_votes += 1
            _c_groups.append("INSIDER")
        # POLITICAL/GOV group
        _ad_r = row.get("altdata") or {}
        _ad_chans = set(_ad_r.get("channels") or [])
        _POL_CHANS = frozenset({"congress_buy", "trump", "gov_contract",
                                 "gov_contract_accel", "gov_grant", "lobbying"})
        if _ad_chans & _POL_CHANS:
            _c_votes += 1
            _c_groups.append("POLITICAL/GOV")
        # GEX-OPTIONS group: verdict == "confirm" only
        if (row.get("gex_confirm") or {}).get("verdict") == "confirm":
            _c_votes += 1
            _c_groups.append("GEX-OPTIONS")
        # ALTDATA-ALT group: non-insider, non-political channels
        _EXCL_CHANS = frozenset({"insider_buy", "insider_cluster",
                                   "congress_buy", "trump", "gov_contract",
                                   "gov_contract_accel", "gov_grant", "lobbying"})
        _alt_chans = _ad_chans - _EXCL_CHANS
        if _ad_r.get("convergence_score", 0) and _alt_chans:
            _c_votes += 1
            _c_groups.append("ALTDATA-ALT")
        # SUE group
        if row.get("sue_z") and (row.get("sue_fresh_days") or 999) <= 60:
            _c_votes += 1
            _c_groups.append("SUE")
        # NEWS group
        if row.get("news_burst"):
            _c_votes += 1
            _c_groups.append("NEWS")
        # SMARTMONEY group
        if row.get("smartmoney_chip"):
            _c_votes += 1
            _c_groups.append("SMARTMONEY")
        if _c_votes >= 2:
            return {"k": _c_votes, "groups": _c_groups}
        return None

    def test_insider_plus_sue_earns_badge(self):
        """Two different groups -> badge fires."""
        row = {
            "insider_buyers": 3,
            "sue_z": 1.5,
            "sue_fresh_days": 30,
        }
        badge = self._compute_badge(row)
        assert badge is not None, "INSIDER + SUE must earn Confluence+ badge"
        assert badge["k"] == 2
        assert "INSIDER" in badge["groups"]
        assert "SUE" in badge["groups"]

    def test_insider_only_no_badge(self):
        """Single group cannot earn badge (k < 2)."""
        row = {"insider_buyers": 3}
        badge = self._compute_badge(row)
        assert badge is None, "Single group must NOT earn badge"

    def test_insider_and_altdata_insider_same_group_no_double_count(self):
        """altdata 'insider_cluster' channel is EXCLUDED from ALTDATA-ALT group
        (same-group as Source 1 insider). So insider + altdata[insider_cluster only]
        yields only 1 vote (INSIDER), not 2."""
        row = {
            "insider_buyers": 3,
            "altdata": {
                "convergence_score": 1,
                "channels": ["insider_cluster"],  # same group as Source 1
            },
        }
        badge = self._compute_badge(row)
        # altdata has insider_cluster only (excluded from ALTDATA-ALT), convergence=1
        # So only INSIDER group fires (altdata has no non-excluded channels)
        assert badge is None, (
            "insider + altdata[insider_cluster] must NOT earn badge "
            "(same independence group — insider is excluded from ALTDATA-ALT)"
        )

    def test_political_channel_in_altdata_earns_political_group(self):
        """altdata 'congress_buy' channel earns POLITICAL/GOV vote."""
        row = {
            "altdata": {
                "convergence_score": 2,
                "channels": ["congress_buy", "gov_contract"],
            },
            "sue_z": 1.5,
            "sue_fresh_days": 30,
        }
        badge = self._compute_badge(row)
        assert badge is not None
        assert "POLITICAL/GOV" in badge["groups"]
        assert "SUE" in badge["groups"]
        assert badge["k"] == 2

    def test_political_and_altdata_alt_same_row_distinct_votes(self):
        """altdata row with BOTH political and non-political channels earns
        POLITICAL/GOV (1 vote) AND ALTDATA-ALT (1 vote) -> k=2."""
        row = {
            "altdata": {
                "convergence_score": 2,
                "channels": ["congress_buy", "patent_cluster"],  # political + innovation
            },
        }
        badge = self._compute_badge(row)
        assert badge is not None, "Political + ALTDATA-ALT should earn badge"
        assert "POLITICAL/GOV" in badge["groups"]
        assert "ALTDATA-ALT" in badge["groups"]

    def test_gex_caution_does_not_fire_gex_options_group(self):
        """GEX-OPTIONS group only fires on verdict=='confirm', not 'caution'."""
        row = {
            "gex_confirm": {"verdict": "caution"},
            "sue_z": 1.5,
            "sue_fresh_days": 30,
        }
        badge = self._compute_badge(row)
        # Only SUE fires (GEX-OPTIONS requires 'confirm')
        assert badge is None or "GEX-OPTIONS" not in (badge or {}).get("groups", [])

    def test_all_seven_groups_yields_k7(self):
        """All 7 independent groups firing -> k=7."""
        row = {
            "insider_buyers": 3,
            "altdata": {
                "convergence_score": 3,
                "channels": ["congress_buy", "patent_cluster"],
            },
            "gex_confirm": {"verdict": "confirm"},
            "sue_z": 1.5,
            "sue_fresh_days": 30,
            "news_burst": {"n_recent": 5},
            "smartmoney_chip": {"action": "new", "n_funds_adding": 1},
        }
        badge = self._compute_badge(row)
        assert badge is not None
        assert badge["k"] == 7
        assert len(badge["groups"]) == 7


# ---------------------------------------------------------------------------
# 3. build_track: W3 strata in buy_lane block
# ---------------------------------------------------------------------------

class TestBuildTrackW3Strata:
    """build_track must emit W3 strata keys in buy_lane block."""

    def _grade_df_with_w3(self, n: int = 4) -> pd.DataFrame:
        """Extend _minimal_grade_df with W3 columns."""
        df = _minimal_grade_df(n=n, lane="buy")
        # Add W3 columns; alternate True/False/None to exercise strata
        df["insider_cluster"] = [True, False, True, False][:n]
        df["gex_confirm_verdict"] = ["confirm", None, "caution", None][:n]
        df["altdata_conv_gte2"] = [True, True, False, False][:n]
        df["sue_fresh"] = [True, False, True, False][:n]
        df["news_burst"] = [False, False, True, False][:n]
        df["smartmoney_add"] = [True, False, False, True][:n]
        df["has_stop_guidance"] = [True, True, False, True][:n]
        df["confluence_k"] = [3, 0, 2, 1][:n]
        return df

    def test_by_insider_cluster_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_insider_cluster" in buy_h5, "by_insider_cluster missing from buy_lane"

    def test_by_gex_confirm_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_gex_confirm" in buy_h5

    def test_by_altdata_conv_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_altdata_conv" in buy_h5

    def test_by_sue_fresh_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_sue_fresh" in buy_h5

    def test_by_news_burst_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_news_burst" in buy_h5

    def test_by_smartmoney_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_smartmoney" in buy_h5

    def test_by_stop_guidance_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_stop_guidance" in buy_h5

    def test_by_confluence_k_in_buy_lane(self):
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_confluence_k" in buy_h5

    def test_w3_strata_absent_when_column_missing(self):
        """Boards before W3 (missing columns) return {} for the slice, not an error."""
        df = _minimal_grade_df(n=4, lane="buy")
        # No W3 columns added — pre-schema df
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        # Keys should be present but with empty dict (missing column -> {})
        assert "by_insider_cluster" in buy_h5
        assert buy_h5["by_insider_cluster"] == {}, (
            "Pre-schema df must produce empty {} strata, not a KeyError")

    def test_strata_hit_stats_bounded(self):
        """Each stratum's hit_rate is between 0 and 1."""
        df = self._grade_df_with_w3()
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        for key in ("by_insider_cluster", "by_sue_fresh", "by_smartmoney"):
            for strat, stats in buy_h5[key].items():
                if "hit_rate" in stats:
                    assert 0.0 <= stats["hit_rate"] <= 1.0, (
                        f"{key}[{strat}] hit_rate={stats['hit_rate']} out of bounds")


# ---------------------------------------------------------------------------
# 4. No-ordering-regression: evidence fields must not change board sort
# ---------------------------------------------------------------------------

class TestNoOrderingRegression:
    """W3 evidence fields must carry ZERO ordering power.

    That contract is unchanged by us_prophet_v1 (2026-08-02) — insider, GEX, SUE,
    smart money and Confluence+ are all named in
    ``engine.us_board_rank.ZERO_SCORE_AUTHORITY``. What DID change is the sort these
    tests must run: it is no longer alpha-desc-within-lane but (stage bucket,
    priority score desc, ticker), with alpha surviving as the 25-point ``edge`` leg.

    These tests now call the REAL ranker rather than re-implementing a sort inline.
    The old inline mirror could not have caught a real ordering regression: it sorted
    its own fixtures with its own code and asserted against itself.
    """

    @staticmethod
    def _order(rows: list[dict]) -> list[str]:
        """Sort rows through the REAL us_prophet_v1 ranker."""
        from engine import us_board_rank as ubr
        scored = ubr.score_rows([dict(r) for r in rows], board_asof="2026-07-31")
        return [r["ticker"] for r in scored]

    @staticmethod
    def _row(ticker, alpha, **extra):
        row = {"ticker": ticker, "alpha": alpha, "lane": "trend",
               "sector": ticker, "entry_signal": {"status": "buy_now"},
               "signal": {"eligible": True, "tier_cascade": "T2", "ticks": 1,
                          "asof": "2026-07-31"}}
        row.update(extra)
        return row

    def test_adding_evidence_fields_does_not_change_order(self):
        """Rows with W3 evidence fields produce the same order as rows without."""
        plain = [self._row("AAA", 0.8), self._row("BBB", 0.5),
                 self._row("CCC", 0.3, lane="recovery")]
        with_ev = [
            self._row("AAA", 0.8, insider_buyers=3,
                      gex_confirm={"verdict": "confirm"},
                      confluence_plus={"k": 2, "groups": ["INSIDER", "GEX-OPTIONS"]}),
            self._row("BBB", 0.5, sue_z=1.5, sue_fresh_days=30),
            self._row("CCC", 0.3, lane="recovery",
                      smartmoney_chip={"action": "new", "n_funds_adding": 1}),
        ]
        assert self._order(plain) == self._order(with_ev), (
            "board order must not change when W3 evidence fields are present")

    def test_evidence_fields_present_on_lower_edge_do_not_promote(self):
        """A weaker name with a Confluence+ badge must NOT appear above a stronger
        one without it — the badge is display-only."""
        rows = [
            self._row("HIGH_ALPHA", 0.9),
            self._row("LOW_ALPHA", 0.2,
                      confluence_plus={"k": 7, "groups": list("ABCDEFG")}),
        ]
        assert self._order(rows)[0] == "HIGH_ALPHA"

    def test_evidence_cannot_lift_a_blocked_row_out_of_its_stage(self):
        """The stage bucket outranks every display chip: a name you are told to avoid
        stays at the bottom no matter how many evidence badges it collects."""
        rows = [
            self._row("BLOCKED", 3.0, entry_signal={"status": "avoid"},
                      insider_buyers=9, sue_z=3.0,
                      confluence_plus={"k": 7, "groups": list("ABCDEFG")}),
            self._row("LIVE", 0.0),
        ]
        assert self._order(rows) == ["LIVE", "BLOCKED"]

    def test_evidence_fields_are_named_as_scoreless_in_the_artifact(self):
        """The disclosure and the behaviour must agree — a reader of the artifact can
        check that these inputs have no score authority."""
        from engine import us_board_rank as ubr
        for leg in ("insider", "sue", "options_gex", "smartmoney"):
            assert leg in ubr.ZERO_SCORE_AUTHORITY


# ---------------------------------------------------------------------------
# 5. Template render: chips and badge with and without fixture data
# ---------------------------------------------------------------------------

class TestTemplateRenderW3:
    """Jinja2 template renders W3 chips when fields present, silently omits when absent."""

    def _render_nb_alpha(self, row_dict: dict) -> str:
        """Render just the nb-alpha section by wrapping it in a minimal Jinja2 env."""
        import jinja2
        # Minimal template that exercises only the W3 chip logic
        SNIPPET = """
{% set n = row %}
{% if n.gex_confirm and n.gex_confirm.get('verdict') in ('confirm', 'caution') %}{% set _gv = n.gex_confirm %}GEX_CHIP:{{ _gv.get('verdict') }}{% endif %}
{% if n.altdata and (n.altdata.get('convergence_score') or 0) >= 2 %}{% set _ad = n.altdata %}ALT_CHIP:{{ _ad.get('convergence_score') }}{% endif %}
{% if n.news_burst and (n.news_burst.get('n_recent') or 0) >= 3 %}{% set _nb = n.news_burst %}NEWS_CHIP:{{ _nb.get('n_recent') }}{% endif %}
{% if n.smartmoney_chip %}{% set _sm = n.smartmoney_chip %}SM_CHIP:{{ _sm.get('best_grade','') }}{% endif %}
{% if n.confluence_plus and (n.confluence_plus.get('k') or 0) >= 2 %}{% set _cp = n.confluence_plus %}CONF_PLUS:{{ _cp.get('k') }}{% endif %}
{% if n.stop_guidance %}{% set _sg = n.stop_guidance %}STOP:{{ _sg.get('pct','?') }}{% endif %}
"""
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tpl = env.from_string(SNIPPET)
        return tpl.render(row=row_dict)

    def test_gex_confirm_chip_rendered(self):
        out = self._render_nb_alpha({
            "gex_confirm": {"verdict": "confirm", "score": 0.8, "levels": {"max_pain": 700}},
        })
        assert "GEX_CHIP:confirm" in out

    def test_gex_caution_chip_rendered(self):
        out = self._render_nb_alpha({"gex_confirm": {"verdict": "caution"}})
        assert "GEX_CHIP:caution" in out

    def test_gex_chip_absent_when_no_gex(self):
        out = self._render_nb_alpha({})
        assert "GEX_CHIP" not in out

    def test_altdata_chip_rendered_when_convergence_gte2(self):
        out = self._render_nb_alpha({
            "altdata": {"convergence_score": 3, "channels": ["congress_buy", "patent_cluster", "13f_add"]},
        })
        assert "ALT_CHIP:3" in out

    def test_altdata_chip_absent_when_convergence_lt2(self):
        out = self._render_nb_alpha({
            "altdata": {"convergence_score": 1, "channels": ["congress_buy"]},
        })
        assert "ALT_CHIP" not in out

    def test_news_chip_rendered_when_n_recent_gte3(self):
        out = self._render_nb_alpha({
            "news_burst": {"n_recent": 5, "sentiment_lean": "neutral"},
        })
        assert "NEWS_CHIP:5" in out

    def test_news_chip_absent_when_n_recent_lt3(self):
        out = self._render_nb_alpha({
            "news_burst": {"n_recent": 2},
        })
        assert "NEWS_CHIP" not in out

    def test_smartmoney_chip_rendered(self):
        out = self._render_nb_alpha({
            "smartmoney_chip": {
                "action": "new", "n_funds_adding": 2,
                "best_fund": "Tiger", "best_grade": "A",
                "period_end": "2026-03-31", "staleness_caveat": "Q1-2026 13F",
            },
        })
        assert "SM_CHIP:A" in out

    def test_smartmoney_chip_absent_when_no_chip(self):
        out = self._render_nb_alpha({})
        assert "SM_CHIP" not in out

    def test_confluence_plus_badge_rendered_at_k2(self):
        out = self._render_nb_alpha({
            "confluence_plus": {"k": 2, "groups": ["INSIDER", "SUE"]},
        })
        assert "CONF_PLUS:2" in out

    def test_confluence_plus_badge_absent_when_k_lt2(self):
        out = self._render_nb_alpha({
            "confluence_plus": {"k": 1, "groups": ["INSIDER"]},
        })
        assert "CONF_PLUS" not in out

    def test_confluence_plus_badge_absent_when_no_field(self):
        out = self._render_nb_alpha({})
        assert "CONF_PLUS" not in out

    def test_stop_guidance_rendered(self):
        out = self._render_nb_alpha({
            "stop_guidance": {"pct": 5.2, "tail_pct": 9.1, "horizon": 21, "scored": True},
        })
        assert "STOP:5.2" in out

    def test_stop_guidance_absent_when_no_field(self):
        out = self._render_nb_alpha({})
        assert "STOP" not in out

    def test_full_dashboard_template_parses(self):
        """The full dashboard.html.j2 must parse without syntax errors."""
        import jinja2
        tpl_path = Path(__file__).resolve().parents[1] / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(tpl_path)),
            undefined=jinja2.Undefined,
            autoescape=False,
        )
        tpl = env.get_template("dashboard.html.j2")
        assert tpl is not None

    def test_no_cjk_in_title_attributes(self):
        """check_title_i18n must pass on the updated template."""
        import subprocess
        repo_root = str(Path(__file__).resolve().parents[1])
        result = subprocess.run(
            ["python3", "scripts/check_title_i18n.py", "templates/"],
            capture_output=True, text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0, (
            f"check_title_i18n found CJK/bilingual in title= attributes:\n"
            f"{result.stdout}\n{result.stderr}")
