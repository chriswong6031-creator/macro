"""Alert-rule tests: engineered frames + a real historical slice."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.alerts import (  # noqa: E402
    _regime_history,
    alert_view,
    hy_oas_widening,
    net_liquidity_roc_flip,
    transition_state_change,
)


def _mk_hist(states: list[str]) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(states))
    return pd.DataFrame({
        "quad": "Q1", "transition_state": states,
        "n_flags": [2] * len(states),
        "growth_confidence": 0.5, "inflation_confidence": 0.5,
    }, index=idx)


def test_transition_change_fires() -> None:
    hist = _mk_hist(["STABLE"] * 5 + ["WEAKENING"])
    a = transition_state_change(hist, pd.DataFrame())
    assert a is not None and "STABLE -> WEAKENING" in a.message


def test_transition_no_change_silent() -> None:
    hist = _mk_hist(["STABLE"] * 6)
    assert transition_state_change(hist, pd.DataFrame()) is None


def test_transition_view_plainifies_message() -> None:
    # Presentation tier (doctrine Law 2): the raw enum message is rewritten to
    # plain words in the rendered view; the stored row keeps the raw string.
    v = alert_view("transition_state_change", "act",
                   "Transition state STABLE -> WEAKENING (2 flags active)")
    assert v["message"] == ("The regime's footing went from steady to weakening "
                            "(2 warning flags active)")
    assert v["message_zh"] == "周期状态由「稳定」转为「走弱」（2 个预警激活）"
    # singular flag count and a non-matching message pass through untouched
    v1 = alert_view("transition_state_change", "info",
                    "Transition state WEAKENING -> STABLE (1 flags active)")
    assert "1 warning flag active" in v1["message"]
    other = alert_view("transition_state_change", "info", "some other shape", "原文")
    assert other["message"] == "some other shape" and other["message_zh"] == "原文"


def test_liquidity_flip_fires() -> None:
    idx = pd.bdate_range("2024-01-01", periods=60)
    nl = pd.Series(np.linspace(0, 100, 60), index=idx)   # rising RoC
    nl.iloc[-2:] = nl.iloc[-22] - 40                      # last 2 days: 20d change sharply negative,
                                                          # holds >=confirm days and clears the deadband
    f = pd.DataFrame({"net_liquidity_bn": nl})
    a = net_liquidity_roc_flip(None, f)
    assert a is not None and "contracting" in a.message


def test_oas_widening_fires() -> None:
    idx = pd.bdate_range("2023-01-01", periods=300)
    oas = pd.Series(3.5 + np.random.default_rng(1).normal(0, 0.02, 300), index=idx)
    oas.iloc[-1] = oas.iloc[-2] + 0.5                     # half-point single-day widening
    f = pd.DataFrame({"hy_oas": oas})
    a = hy_oas_widening(None, f)
    assert a is not None and "sigma" in a.message


def test_oas_quiet_day_silent() -> None:
    idx = pd.bdate_range("2023-01-01", periods=300)
    oas = pd.Series(3.5 + np.random.default_rng(2).normal(0, 0.02, 300), index=idx)
    f = pd.DataFrame({"hy_oas": oas})
    assert hy_oas_widening(None, f) is None


def test_breaker_views_collapse_count_aware() -> None:
    """N same-day dark sources must render ONE count-aware headline ("6 data
    sources went dark"), not N stacked singulars (design review 2026-07-13)."""
    from engine.alerts import alert_views
    msg = ("Source '{s}' marked dead after 3 consecutive failures — collector "
           "skipped until it recovers; affected signals degrade")
    raw = [{"rule": "hy_oas_widening", "severity": "act", "message": "HY OAS ..."}]
    raw += [{"rule": "circuit_breaker_open", "severity": "warn",
             "message": msg.format(s=s)} for s in ("fred", "cboe", "yahoo")]
    views = alert_views(raw)
    cbs = [v for v in views if v["rule"] == "circuit_breaker_open"]
    assert len(cbs) == 1
    assert cbs[0]["plain_en"] == "3 data sources went dark"
    assert cbs[0]["plain_zh"] == "3 个数据源中断"
    for s in ("fred", "cboe", "yahoo"):
        assert f"'{s}'" in cbs[0]["message"] and f"'{s}'" in cbs[0]["message_zh"]
    assert views[0]["rule"] == "hy_oas_widening"          # order preserved
    assert len(views) == 2


def test_breaker_views_single_stays_singular() -> None:
    from engine.alerts import alert_views
    views = alert_views([{"rule": "circuit_breaker_open", "severity": "warn",
                          "message": "Source 'fred' marked dead after 3 consecutive "
                                     "failures — collector skipped until it recovers; "
                                     "affected signals degrade"}])
    assert len(views) == 1
    assert views[0]["plain_en"] == "A data source went dark"


def test_every_fired_rule_has_plain_copy() -> None:
    """No rule that can reach the macro alerts VM may fall back to the generic
    default headline (the "Macro signal fired" class, design review 2026-07-13).
    event_risk is appended by scripts/build_site.py, not evaluate(); the two
    confidence-floor rules are named via an f-string the regex cannot see."""
    import re as _re
    from engine import alerts as A
    src = Path(A.__file__).read_text()
    fired = set(_re.findall(r"Alert\(\s*[\"']([a-z0-9_]+)[\"']", src))
    fired |= {"event_risk", "growth_confidence_floor", "inflation_confidence_floor"}
    missing_meta = sorted(fired - set(A.ALERT_META))
    missing_conv = sorted(fired - set(A.ALERT_CONVICTION))
    assert not missing_meta, f"rules without ALERT_META: {missing_meta}"
    assert not missing_conv, f"rules without ALERT_CONVICTION: {missing_conv}"


def test_regional_breaker_views_collapse(tmp_path, monkeypatch) -> None:
    """Drive the PRODUCTION path (today_views over the append-only log): the
    per-rule same-day dedup must NOT swallow the per-source breaker rows before
    the count-aware collapse sees them."""
    from engine import china_alerts, hk_alerts
    day = "2026-07-13"
    for mod, rule, prefix, plural_en, plural_zh in [
            (china_alerts, "china_circuit_breaker", "China source",
             "2 China data sources went dark", "2 个中国数据源中断"),
            (hk_alerts, "hk_circuit_breaker", "HK source",
             "2 HK data sources went dark", "2 个香港数据源中断")]:
        rows = [{"date": day, "rule": "market_driver_clear", "severity": "info",
                 "message": "wording v1", "message_zh": "旧措辞"},
                {"date": day, "rule": "market_driver_clear", "severity": "info",
                 "message": "wording v2", "message_zh": "新措辞"}]
        rows += [{"date": day, "rule": rule, "severity": "high",
                  "message": f"{prefix} '{s}' marked dead after 3 consecutive failures "
                             f"— collector skipped until it recovers; affected signals "
                             f"degrade",
                  "message_zh": f"数据源 '{s}' 连续 3 次失败后被标记为中断"}
                 for s in ("src_a", "src_b")]
        p = tmp_path / f"{rule}_log.parquet"
        pd.DataFrame(rows).to_parquet(p)
        monkeypatch.setattr(mod, "_log_path", lambda p=p: p)
        views = mod.today_views(day)
        cbs = [v for v in views if v["rule"] == rule]
        assert len(cbs) == 1, f"{rule}: expected one merged view, got {len(cbs)}"
        assert cbs[0]["plain_en"] == plural_en
        assert cbs[0]["plain_zh"] == plural_zh
        assert "'src_a'" in cbs[0]["message"] and "'src_b'" in cbs[0]["message"]
        # the wording-drift dedup still holds for ordinary rules
        others = [v for v in views if v["rule"] == "market_driver_clear"]
        assert len(others) == 1 and others[0]["message"] == "wording v2"


def test_historical_state_changes_detectable() -> None:
    """Replay the rule at real state-change dates in stored history."""
    hist = _regime_history()
    if hist is None or len(hist) < 100:
        print("  (no stored history — skipped)")
        return
    chg = hist["transition_state"].ne(hist["transition_state"].shift())
    change_dates = hist.index[chg][-5:]
    fired = 0
    for d in change_dates:
        sub = hist.loc[:d]
        if len(sub) < 2:
            continue
        if transition_state_change(sub, pd.DataFrame()) is not None:
            fired += 1
    assert fired >= max(1, len(change_dates) - 1), f"only {fired} fired of {len(change_dates)}"


def test_alert_anchor_ids_exist_in_templates() -> None:
    """Every non-empty ALERT_META anchor must be a literal id="" on its rendered
    surface (dashboard.html.j2 for macro/us_stocks anchors incl. dlg-* dialogs,
    or the cross-page template named in ANCHOR_PAGE). The v5 board moved panel
    detail inside dialogs — a stale anchor renders a "View ↓" that scrolls
    nowhere, which is exactly the drift this guards against."""
    import engine.alerts as A
    root = Path(__file__).resolve().parent.parent
    dash = (root / "templates" / "dashboard.html.j2").read_text()
    page_src = {
        "us_stocks.html": dash,   # us_stocks renders from the same template
        "macro_context.html": (root / "templates" / "macro_context.html.j2").read_text(),
    }
    for rule, meta in A.ALERT_META.items():
        anchor = meta["anchor"]
        if not anchor:
            continue
        src = page_src.get(A.ANCHOR_PAGE.get(anchor, ""), dash)
        assert f'id="{anchor}"' in src, (
            f"{rule}: anchor '{anchor}' is not an id on its rendered surface")


def test_alert_href_routing() -> None:
    """alert_href routes cross-page anchors to their page, everything else to macro."""
    import engine.alerts as A
    assert A.alert_href("") == "macro.html"
    assert A.alert_href("dlg-risk") == "macro.html#dlg-risk"
    assert A.alert_href("regime-radar") == "macro.html#regime-radar"
    assert A.alert_href("holdings") == "us_stocks.html#holdings"
    assert A.alert_href("board") == "macro_context.html#board"


if __name__ == "__main__":
    # test_regional_breaker_views_collapse needs pytest fixtures — run via pytest
    for fn in [test_transition_change_fires, test_transition_no_change_silent,
               test_liquidity_flip_fires, test_oas_widening_fires,
               test_oas_quiet_day_silent, test_breaker_views_collapse_count_aware,
               test_breaker_views_single_stays_singular,
               test_every_fired_rule_has_plain_copy,
               test_historical_state_changes_detectable,
               test_alert_anchor_ids_exist_in_templates,
               test_alert_href_routing]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all alert tests passed")
