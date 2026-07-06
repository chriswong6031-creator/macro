"""China Intelligence transmission bus — contract tests (pure, network-free).

The bus is a context-only fan-in of four surface JSON emits. It must ALWAYS return a
valid, schema-versioned, JSON-serializable briefing — even with zero surfaces built —
and NEVER raise into a build.
"""
from __future__ import annotations

import json

from engine import china_intel_bus as bus


def test_briefing_shape(monkeypatch):
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)   # no surfaces built
    b = bus.briefing(asof="2026-06-20")
    assert b["schema"] == "china_intel.briefing.v6"
    assert b["is_context_only"] is True
    assert b["asof"] == "2026-06-20"
    for k in ("news", "policy", "altdata", "radar", "analysis"):
        assert k in b
    # v2 hoisted synthesis keys always present
    for k in ("conviction", "cross_surface", "flagged_tickers", "what_changed", "salience",
              "surface_asof", "max_staleness_days"):
        assert k in b
    # v6: analogs key always present (may be None)
    assert "analogs" in b
    assert isinstance(b["digest"], str) and b["digest"]
    assert b["disclaimer"] and b["disclaimer_zh"]


def test_briefing_is_json_serializable():
    json.dumps(bus.briefing(), default=str)  # must not raise


def test_digest_text_synthesis_led():
    b = {
        "analysis": {
            "what_matters": [{"label_en": "Brokers divergence (positive)", "detail_en": "stacked"}],
            "conviction": [{"sector_en": "Brokers", "radar_sign": "positive",
                            "context_conviction": 34, "surfaces_confirming": ["radar", "news"]}],
            "what_changed": {"stance_change": {"from": "neutral", "to": "easing"}},
        },
        "news": {"band": "supportive", "sentiment_z": 0.8, "n_events_7d": 12,
                 "flagged_baskets": [{"name_en": "Brokers", "hits": 3}]},
        "policy": {"pboc_stance": "easing", "lpr_1y": 3.0, "lpr_5y": 3.5, "rrr": 6.0},
        "altdata": {"accumulate": [{"name": "中信证券", "ticker": "600030.SS"}]},
        "radar": {"divergences": [{"signal_en": "PBoC easing", "sector": "Brokers", "sign": "positive"}],
                  "ledger": {"grade": "unproven"}},
    }
    txt = bus._digest_text(b)
    assert "WHAT MATTERS MOST" in txt
    assert "CHANGED TODAY" in txt and "neutral→easing" in txt
    assert "STACKED READS" in txt and "Brokers" in txt
    assert "中信证券(600030.SS)" in txt          # names, not bare codes
    assert "unproven" in txt


def test_digest_text_empty_when_nothing_present():
    assert "no surfaces" in bus._digest_text({}).lower()


# ── v4: policy_phrase block ───────────────────────────────────────────────────

def test_policy_phrase_block_missing_file(monkeypatch):
    """Missing communique_diff/latest.json → block returns None, no exception."""
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    result = bus._policy_phrase_block()
    assert result is None


def test_policy_phrase_block_empty_events(monkeypatch):
    """File present but events=[] (cold-start day) → block present with n=0."""
    payload = {
        "schema": "communique_diff.v1",
        "asof": "2026-07-02",
        "events": [],
        "cold_start_organs": ["pboc", "ndrc"],
        "counts": {"n_events": 0, "n_appeared": 0, "n_dropped": 0,
                   "n_lead_shift": 0, "n_cold_start_organs": 2},
    }
    monkeypatch.setattr(bus, "_read_json", lambda rel: payload if "communique_diff" in rel else None)
    result = bus._policy_phrase_block()
    assert result is not None
    assert result["n_events_recent"] == 0
    assert result["cold_start_organs"] == ["pboc", "ndrc"]
    assert result["is_context_only"] is True


def test_policy_phrase_block_happy_path(monkeypatch):
    """File with recent events → block populated correctly."""
    from datetime import date, timedelta
    today = date.today()
    recent_date = (today - timedelta(days=3)).isoformat()
    payload = {
        "schema": "communique_diff.v1",
        "asof": recent_date,
        "events": [
            {"event_id": "cd_abc", "kind": "APPEARED", "organ": "pboc",
             "phrase": "适度宽松", "gloss": "moderately loose", "domain": "monetary",
             "polarity": 0, "review_status": "PROVISIONAL",
             "asof": recent_date, "evidence_url": "http://pboc.gov.cn/1"},
            {"event_id": "cd_def", "kind": "DROPPED", "organ": "state_council",
             "phrase": "房住不炒", "gloss": "housing not for speculation", "domain": "real_estate",
             "polarity": 0, "review_status": "PROVISIONAL",
             "asof": recent_date, "evidence_url": ""},
        ],
        "cold_start_organs": [],
        "counts": {"n_events": 2, "n_appeared": 1, "n_dropped": 1,
                   "n_lead_shift": 0, "n_cold_start_organs": 0},
    }
    monkeypatch.setattr(bus, "_read_json", lambda rel: payload if "communique_diff" in rel else None)
    result = bus._policy_phrase_block()
    assert result is not None
    assert result["n_events_recent"] == 2
    assert result["n_appeared"] == 1
    assert result["n_dropped"] == 1
    assert result["n_lead_shift"] == 0
    assert "pboc" in result["organs_covered"]
    assert len(result["recent_events"]) == 2
    assert result["claim_family"] == "communique_diff"


def test_policy_phrase_old_events_excluded(monkeypatch):
    """Events older than 14d are excluded from recent_events count.

    NOTE: this exercises the defensive 14d filter path. In production,
    communique_diff stamps all events with the run asof (same as the top-level asof),
    so the filter is a no-op — this payload fabricates a per-event asof older than
    the top-level asof, which the producer cannot currently emit.
    """
    payload = {
        "schema": "communique_diff.v1",
        "asof": "2026-07-02",
        "events": [
            {"event_id": "cd_old", "kind": "APPEARED", "organ": "pboc",
             "phrase": "适度宽松", "gloss": "test", "domain": "monetary",
             "polarity": 0, "review_status": "PROVISIONAL",
             "asof": "2026-06-01",  # much older than 14d from 2026-07-02
             "evidence_url": ""},
        ],
        "cold_start_organs": [],
        "counts": {"n_events": 1, "n_appeared": 1, "n_dropped": 0,
                   "n_lead_shift": 0, "n_cold_start_organs": 0},
    }
    monkeypatch.setattr(bus, "_read_json", lambda rel: payload if "communique_diff" in rel else None)
    result = bus._policy_phrase_block()
    assert result is not None
    assert result["n_events_recent"] == 0  # old event filtered out (defensive path)


# ── v4: narrative_divergence block ───────────────────────────────────────────

def test_narrative_divergence_block_no_parquet(monkeypatch, tmp_path):
    """Missing parquet → block returns None, no exception."""
    import engine.china_intel_bus as _bus
    # Patch config.ROOT so the path doesn't exist
    import types
    fake_config = types.SimpleNamespace(ROOT=tmp_path)
    monkeypatch.setattr(_bus, "config", fake_config)
    result = _bus._narrative_divergence_block()
    assert result is None


def test_narrative_divergence_block_happy_path(monkeypatch, tmp_path):
    """Valid parquet → block returns z, trend, risk_flag."""
    import pandas as pd
    import math
    # Write a stub parquet
    parquet_dir = tmp_path / "data" / "missing_tape"
    parquet_dir.mkdir(parents=True)
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03",
                 "2026-07-04", "2026-07-05", "2026-07-06"],
        "zh_tone": [1.0, 1.2, 1.5, 1.8, 2.0, 2.5],
        "en_tone": [-0.2, -0.3, -0.5, -0.4, -0.6, -0.8],
        "spread": [1.2, 1.5, 2.0, 2.2, 2.6, 3.3],
        "spread_expanding_z": [float("nan"), float("nan"), float("nan"),
                               float("nan"), float("nan"), 2.1],
        "fetch_status": ["ok"] * 6,
    })
    df.to_parquet(parquet_dir / "tone_divergence.parquet", index=False)

    import types
    fake_config = types.SimpleNamespace(ROOT=tmp_path)
    monkeypatch.setattr(bus, "config", fake_config)
    result = bus._narrative_divergence_block()
    assert result is not None
    assert result["divergence_z"] == pytest.approx(2.1, abs=0.01)
    assert result["risk_flag"] is True  # z > 1.5
    assert result["direction_proven"] is False
    assert result["asof"] == "2026-07-06"


def test_narrative_divergence_block_negative_z_no_flag(monkeypatch, tmp_path):
    """Negative z (e.g. -2.0) must NOT set risk_flag — semantics are one-sided (high = suspect)."""
    import pandas as pd
    parquet_dir = tmp_path / "data" / "missing_tape"
    parquet_dir.mkdir(parents=True)
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03",
                 "2026-07-04", "2026-07-05", "2026-07-06"],
        "zh_tone": [-1.0, -1.2, -1.5, -1.8, -2.0, -2.5],
        "en_tone": [0.2, 0.3, 0.5, 0.4, 0.6, 0.8],
        "spread": [-1.2, -1.5, -2.0, -2.2, -2.6, -3.3],
        "spread_expanding_z": [float("nan"), float("nan"), float("nan"),
                               float("nan"), float("nan"), -2.0],
        "fetch_status": ["ok"] * 6,
    })
    df.to_parquet(parquet_dir / "tone_divergence.parquet", index=False)

    import types
    fake_config = types.SimpleNamespace(ROOT=tmp_path)
    monkeypatch.setattr(bus, "config", fake_config)
    result = bus._narrative_divergence_block()
    assert result is not None
    assert result["divergence_z"] == pytest.approx(-2.0, abs=0.01)
    assert result["risk_flag"] is False  # negative z = offshore quieter, not domestic suppression


def test_narrative_divergence_block_all_nan_z(monkeypatch, tmp_path):
    """All-NaN z-scores (cold-start) → block returns None (no z to show)."""
    import pandas as pd
    parquet_dir = tmp_path / "data" / "missing_tape"
    parquet_dir.mkdir(parents=True)
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02"],
        "zh_tone": [1.0, 1.2],
        "en_tone": [-0.2, -0.3],
        "spread": [1.2, 1.5],
        "spread_expanding_z": [float("nan"), float("nan")],
        "fetch_status": ["ok", "ok"],
    })
    df.to_parquet(parquet_dir / "tone_divergence.parquet", index=False)

    import types
    fake_config = types.SimpleNamespace(ROOT=tmp_path)
    monkeypatch.setattr(bus, "config", fake_config)
    result = bus._narrative_divergence_block()
    assert result is None


# ── v4 integration: new blocks surface in briefing ───────────────────────────

def test_briefing_includes_v4_blocks(monkeypatch):
    """briefing() always has policy_phrase and narrative_divergence keys (may be None)."""
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")
    assert "policy_phrase" in b
    assert "narrative_divergence" in b
    # both None when no data
    assert b["policy_phrase"] is None
    assert b["narrative_divergence"] is None


def test_digest_text_includes_policy_phrase_count():
    """digest text mentions policy phrase events when present."""
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=2)).isoformat()
    b = {
        "policy_phrase": {
            "asof": recent,
            "n_events_recent": 3,
            "n_appeared": 2,
            "n_dropped": 1,
            "n_lead_shift": 0,
            "organs_covered": ["pboc", "ndrc"],
            "is_context_only": True,
        },
        "narrative_divergence": None,
    }
    txt = bus._digest_text(b)
    assert "3 events" in txt
    assert "appeared" in txt.lower()
    assert "salience-only" in txt.lower()


def test_digest_text_includes_divergence_z():
    """digest text mentions onshore/offshore divergence z when present."""
    b = {
        "policy_phrase": None,
        "narrative_divergence": {
            "divergence_z": 2.3,
            "trend_5d": "rising",
            "risk_flag": True,
        },
    }
    txt = bus._digest_text(b)
    assert "2.3" in txt or "+2.30" in txt
    assert "direction=0" in txt


import pytest


# ── v5: special_situations block ─────────────────────────────────────────────

def test_special_situations_block_missing_file(monkeypatch):
    """Missing chinaspecialdata/special.json → block returns None, no exception."""
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    result = bus._special_situations_block()
    assert result is None


def test_special_situations_block_happy_path(monkeypatch):
    """Valid special.json → block returns compact summary."""
    payload = {
        "schema": "china_special_sits.v1",
        "asof": "2026-07-06",
        "unlocks": {"n_events_30d": 5, "n_large": 2, "events": [
            {"ticker": "600000.SS", "name": "浦发银行", "unlock_date": "2026-07-15",
             "float_ratio": 8.2, "large_flag": True, "mktcap_yi": 12.5}
        ]},
        "inquiry": {"n_letters": 3, "letters": [
            {"secCode": "000001", "secName": "平安银行", "title": "关注函",
             "date": "2026-07-05", "has_reply": False, "kind": "letter"}
        ]},
        "preannounce": {"n_total": 45},
        "buyback": {"n_active": 12},
        "pledge": {"n_high": 8},
        "st": {"count": 211},
        "block_trades": {"n_names": 50},
    }
    monkeypatch.setattr(bus, "_read_json",
                        lambda rel: payload if "chinaspecialdata" in rel else None)
    result = bus._special_situations_block()
    assert result is not None
    assert result["asof"] == "2026-07-06"
    assert result["n_unlocks"] == 5
    assert result["n_inquiry"] == 3
    assert result["n_st"] == 211
    assert result["top_unlock"]["ticker"] == "600000.SS"
    assert result["top_unlock"]["large_flag"] is True
    assert result["newest_letter"]["secCode"] == "000001"
    assert result["is_context_only"] is True


# ── v5 integration: block surfaces in briefing ──────────────────────────────

def test_briefing_includes_v5_blocks(monkeypatch):
    """briefing() always has special_situations key (may be None)."""
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")
    assert "special_situations" in b
    assert b["special_situations"] is None  # None when artifact absent


def test_briefing_schema_is_v6(monkeypatch):
    """Schema string must be v6."""
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")
    assert b["schema"] == "china_intel.briefing.v6"


# ── v6 integration: bus↔template contract integration test (BLOCKER 2) ────────

def test_template_renders_command_section(tmp_path, monkeypatch):
    """Integration test: fixture command.json + builder + template → cmd-tbl appears.

    This test was designed to FAIL against the pre-fix code (bus block carried top10
    but template guarded on b.command.command which didn't exist in the bus payload).
    Post-fix: builder loads cmd_full separately and passes it to the template.

    Steps:
    1. Write a fixture command.json to tmp_path/china_intel/command.json
    2. Run china_intel_bus.briefing() with _read_json monkeypatched to serve the fixture
    3. Load cmd_full exactly as build_china_intel._load_cmd_full() does
    4. Render the actual template with (b=b, cmd_full=cmd_full)
    5. Assert <table class="cmd-tbl">, Discovery Queue header, and (with analogs) analogs card
    """
    import json as _json
    from jinja2 import Environment, FileSystemLoader
    from lib import config
    from scripts.build_china_intel import _load_cmd_full

    # ── 1. Write fixture command.json ──────────────────────────────────────
    cmd_dir = tmp_path / "china_intel"
    cmd_dir.mkdir(parents=True)
    fixture_command = {
        "schema": "china_intel.command.v1",
        "is_context_only": True,
        "as_of": "2026-07-06",
        "n_universe": 5,
        "command": [
            {
                "ticker": "000563.SZ", "name": "武汉银行", "stage": "early",
                "opportunity_score": 82.2, "edge_remaining": 0.93,
                "edge_drivers": ["not on buy-board"], "edge_components": 2,
                "leading_gap": 1, "lead_up": 1, "lag_up": 0, "signal_core": 0.768,
                "falsifier": None, "falsifier_penalty": 1.0,
                "directions": {"altdata": 1, "radar": None, "news": None, "board": None},
                "desk_matrix": {
                    "news": {"present": False, "dir": None},
                    "altdata": {"present": True, "dir": 1},
                    "radar": {"present": False, "dir": None},
                    "board": {"present": False, "dir": None},
                    "special": {"present": False, "dir": None},
                },
                "off_desk": True, "veto_blind": False,
                "traj": {"ret_20d": 5.2, "rs_20d": 3.1, "rs_60d": 1.2,
                         "off_high_pct": -8.5, "rolling_over": False},
                "read": "A leading desk is ahead of the crowd — early, ~93% edge remaining.",
            },
            {
                # veto-blind row: traj is None and MUST NOT crash the render
                # (missing traj keys pass `is not none` as Undefined then crash on compare)
                "ticker": "832000.BJ", "name": "无价名", "stage": "early",
                "opportunity_score": 61.0, "edge_remaining": None,
                "edge_drivers": [], "edge_components": 0,
                "leading_gap": 1, "lead_up": 1, "lag_up": 0, "signal_core": 0.61,
                "falsifier": None, "falsifier_penalty": 1.0,
                "directions": {"altdata": 1, "radar": None, "news": None, "board": None},
                "desk_matrix": {
                    "news": {"present": False, "dir": None},
                    "altdata": {"present": True, "dir": 1},
                    "radar": {"present": False, "dir": None},
                    "board": {"present": False, "dir": None},
                    "special": {"present": False, "dir": None},
                },
                "off_desk": True, "veto_blind": True,
                "traj": None,
                "read": "Leading signal, no price plane — veto blind.",
            },
        ],
        "discovery": [
            {
                "ticker": "000001.SZ", "name": "平安银行", "disc_score": 0.65,
                "source": "lhb_first_seat", "reason": "First LHB seat in 90+ days",
                "off_desk": True, "experimental": False, "lhb_date": "2026-07-06",
            },
        ],
        "analogs": None,
        "desks": {"news": {"live": False}, "altdata": {"live": True},
                  "radar": {"live": False}, "board": {"live": False}, "special": {"live": False}},
        "counts": {"emerging": 0, "early": 1, "consensus": 0, "exhausted": 0,
                   "faltering": 0, "distribution": 0, "quiet": 0, "board_members": 0,
                   "with_price": 1, "veto_blind": 0, "board_only_unranked": 0},
    }
    (cmd_dir / "command.json").write_text(_json.dumps(fixture_command, ensure_ascii=False))

    # Also write a fixture analogs.json to test analogs card
    fixture_analogs = {
        "schema": "china_intel.analogs.v1",
        "as_of": "2026-07-06",
        "coverage": "CSI300 2010-2026",
        "query": {"quad": "Q2", "quad_name": "Bull", "liquidity": "easing", "cycle": "mid"},
        "fan": {"h20": {"p25": 0.01, "median": 0.03, "p75": 0.06, "n": 12}},
        "analogs": [{"date": "2015-06-01", "quad": "Q2", "fwd_shcomp": {"h20": 0.04}}],
        "method_note": "Cosine similarity on macro fingerprint.",
        "disclaimer_en": "Descriptive fan only.",
        "disclaimer_zh": "仅描述性分布。",
    }
    (cmd_dir / "analogs.json").write_text(_json.dumps(fixture_analogs, ensure_ascii=False))

    # ── 2. Run briefing() with _read_json reading from tmp_path ───────────
    def _mock_read_json(rel: str):
        p = tmp_path / rel
        if p.exists():
            return _json.loads(p.read_text())
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    b = bus.briefing(asof="2026-07-06")

    # ── 3. Load cmd_full exactly as the builder does ───────────────────────
    cmd_full = _json.loads((cmd_dir / "command.json").read_text())

    # ── 4. Render the actual template ─────────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:
        # i18n may fail without full data; provide stub
        env.globals.update(td=lambda k, zh="": k, tr=lambda k, zh="": k,
                           t=lambda k, zh="": k)
    html = env.get_template("china_intel.html.j2").render(b=b, cmd_full=cmd_full)

    # ── 5. Assertions ──────────────────────────────────────────────────────
    # K2: command table rendered
    assert 'class="cmd-tbl"' in html, "cmd-tbl table not found — K2 command section not rendered"
    # K2: ticker in table
    assert "000563.SZ" in html, "fixture ticker not found in rendered HTML"
    # K3: Discovery Queue header present
    assert "Discovery Queue" in html or "发现队列" in html, \
        "Discovery Queue header not found — K3 not rendered"
    # K3: discovery ticker present
    assert "000001.SZ" in html, "discovery ticker not found in rendered HTML"

    # Analogs card: b.analogs is set (from fixture analogs.json via _mock_read_json)
    assert b.get("analogs") is not None, "b.analogs should be non-None with fixture analogs.json"
    assert "Cycle Context" in html or "周期背景" in html, \
        "Analogs card not rendered — K4 not present even with b.analogs set"


def test_template_command_pre_fix_would_fail(tmp_path, monkeypatch):
    """Demonstrate that WITHOUT cmd_full the old template guard fails silently.

    This test proves the pre-fix behavior: b.command is a compact dict with top10/discovery_n
    but no .command/.discovery keys, so K2/K3 render nothing.
    """
    import json as _json
    from jinja2 import Environment, FileSystemLoader
    from lib import config

    # monkeypatch: no artifacts on disk → bus command block returns compact form
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")

    # Inject a fake bus-style command block (as the OLD code would have returned)
    b["command"] = {
        "asof": "2026-07-06", "n_universe": 5, "counts": {},
        "top10": [{"ticker": "000563.SZ", "stage": "early"}],
        "discovery_n": 1, "is_context_only": True,
        # note: NO .command key, NO .discovery key
    }

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:
        env.globals.update(td=lambda k, zh="": k, tr=lambda k, zh="": k,
                           t=lambda k, zh="": k)

    # Render WITHOUT cmd_full (cmd_full=None simulates the old template behavior)
    html = env.get_template("china_intel.html.j2").render(b=b, cmd_full=None)

    # K2 must NOT render — cmd_full is None so the guard `{%- if cmd_full and cmd_full.command %}` fails
    assert 'class="cmd-tbl"' not in html, \
        "cmd-tbl should NOT be present when cmd_full=None (pre-fix behavior)"
