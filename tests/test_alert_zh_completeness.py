"""The zh half of a macro alert body must be fully Chinese.

Six rules used to interpolate an English-valued token straight into their
`message_zh` f-string, so the wrapper punctuation and the surrounding nouns
translated while the clause inside them did not — the shape that shipped

    EN  GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)
    ZH  GEX：net GEX changed sign（净 +79bn，现价相对翻转点 -0.7%）

to the landing hub's "What changed" rows and the macro dashboard's
`ms-sig-detail`. The emitter is the only path the dashboard has (it renders
freshly-evaluated Alert objects, never the log), so a leak there is unrecoverable
downstream.

Three properties are pinned here:

  1. no English prose survives in an emitted `message_zh`;
  2. the emitter and `_translate_macro_detail` — build_vector's backlog translator
     for rows that predate the `message_zh` column — produce the SAME Chinese for
     the same alert. They disagreed for six rules, the emitter (which wins) was
     the wrong one, and nothing noticed;
  3. the already-baked half-translated rows in alerts_log.parquet still render
     fully Chinese through the hub's resolution, because log_and_dedup keys on
     (date, rule, message) and the English message never changes — no corrected
     row will ever supersede them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import alerts  # noqa: E402
from engine.alerts import (  # noqa: E402
    _GEX_WHAT_ZH,
    _HOLDINGS_VERB_ZH,
    _RECESSION_BAND_ZH,
    _RISK_STATE_ZH,
    _TS_PLAIN_ZH,
)
from engine.i18n import LEX as _LEX  # noqa: E402
from scripts.build_vector import (  # noqa: E402
    _ZH_HALF_TRANSLATED_RULES,
    _translate_macro_detail,
)

# Latin that is a NAME keeps its letters by design: tickers (XLRE, PSA), funds,
# quoted source slugs, and the few indicator names the Chinese copy also uses
# untranslated (NFCI, GEX, Sahm, RS, gamma, contango, and pp/bn/dma units).
_NAME_LIKE = re.compile(
    r"'[^']*'"                                          # 'sentiment_naaim'
    r"|\bgamma\b|\bcontango\b|\bpp\b|\bbn\b|\bdma\b|\bSahm\b")

# ALL-CAPS is NOT evidence of a name: the state labels that leaked here are also
# all-caps (WEAKENING, UNCONFIRMED TURN, RISK-OFF), so exempting uppercase runs
# wholesale would blind this check to half the defect. Tickers are separated from
# state labels by membership in the finite display vocabulary instead — every
# label below has a Chinese rendering and must never survive into zh copy.
_MUST_TRANSLATE_LABELS = frozenset(
    set(_TS_PLAIN_ZH) | set(_RISK_STATE_ZH)
    | {k for k in _LEX if isinstance(k, str) and k.isupper() and len(k) > 2})

_LOWER_PROSE = re.compile(r"[a-z]{3,}")


def _english_prose_in(zh: str) -> list[str]:
    """English left in a Chinese string: lowercase prose, or a finite-vocab label
    that has a Chinese rendering and should have been used."""
    found = _LOWER_PROSE.findall(_NAME_LIKE.sub(" ", zh))
    found += sorted(lbl for lbl in _MUST_TRANSLATE_LABELS if lbl in zh)
    return found


def _mk_hist(states: list[str]) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(states))
    return pd.DataFrame({
        "quad": "Q1", "transition_state": states, "n_flags": [3] * len(states),
        "growth_confidence": 0.5, "inflation_confidence": 0.5,
    }, index=idx)


# --------------------------------------------------------------------------- #
# Drive each formerly-leaking rule to a fired Alert.
# --------------------------------------------------------------------------- #

def _gex(monkeypatch, crossed_flip: bool):
    g = pd.DataFrame({
        "net_gex_bn":       [-40.0, 79.0] if not crossed_flip else [50.0, 60.0],
        "spot_vs_flip_pct": [-0.7, -0.9] if not crossed_flip else [0.8, -0.7],
    })
    monkeypatch.setattr(alerts.store, "read", lambda *a, **k: g)
    return alerts.gex_flip_cross(None, pd.DataFrame())


def _holdings(monkeypatch, chg_pct: float):
    ch = pd.DataFrame(
        {"active_chg_pct": [chg_pct],
         "window_start": ["2026-07-24"], "window_end": ["2026-07-31"]},
        index=["FIG"])
    import collectors.holdings as ch_mod
    monkeypatch.setattr(ch_mod, "active_changes", lambda t: ch if t == "ARKK" else None)
    return alerts.holdings_active_changes(None, pd.DataFrame())


def _sector(monkeypatch, direction: str):
    sig = {"fund": "XLRE", "ticker": "PSA", "active_change": 0.26,
           "direction": direction, "est_flow_mn": 23.0, "confirmed": True,
           "t0": "2026-07-17", "t1": "2026-07-24",
           "ladder": {"label": "UNCONFIRMED TURN", "action": "HIGH-RISK · NIMBLE ONLY"}}
    import engine.holdings_signals as hs
    monkeypatch.setattr(hs, "all_accumulation_signals", lambda: [sig])
    return alerts.sector_holdings_accumulation(None, pd.DataFrame())


def _recession(monkeypatch, prev_score: float, cur_score: float):
    monkeypatch.setattr(alerts, "_conditions_frame",
                        lambda f: pd.DataFrame({"recession_risk": [prev_score, cur_score]}))
    return alerts.conditions_recession_state_change(None, pd.DataFrame())


def _risk_state(monkeypatch, cur: float):
    import engine.risk_state as rs
    bands = rs._cfg()["bands"]
    monkeypatch.setattr(rs, "core_series",
                        lambda f: pd.Series([float(bands["elevated"]) - 5.0, cur]))
    return alerts.risk_state_elevated(None, pd.DataFrame())


def _fired(monkeypatch) -> list:
    """One fired Alert per formerly-leaking rule, both branches where they differ."""
    out = [
        alerts.transition_state_change(_mk_hist(["STABLE"] * 5 + ["WEAKENING"]), pd.DataFrame()),
        alerts.transition_state_change(_mk_hist(["WEAKENING"] * 5 + ["NEW_REGIME"]), pd.DataFrame()),
        _gex(monkeypatch, crossed_flip=False),
        _gex(monkeypatch, crossed_flip=True),
        *_holdings(monkeypatch, -100.0),
        *_holdings(monkeypatch, +45.0),
        *_sector(monkeypatch, "accumulating"),
        *_sector(monkeypatch, "trimming"),
    ]
    rc = alerts.config.load()["engine"]["conditions"]["recession"]
    out.append(_recession(monkeypatch, rc["elevated_score"] - 10, rc["high_score"] + 5))
    out.append(_recession(monkeypatch, rc["high_score"] + 5, rc["elevated_score"] - 10))
    bands = __import__("engine.risk_state", fromlist=["x"])._cfg()["bands"]
    out.append(_risk_state(monkeypatch, float(bands["risk_off"]) + 2))
    out.append(_risk_state(monkeypatch, float(bands["elevated"]) + 1))
    fired = [a for a in out if a is not None]
    assert len(fired) == len(out), "a fixture stopped firing — the rule shapes moved"
    return fired


# --------------------------------------------------------------------------- #

def test_emitted_zh_carries_no_english_prose(monkeypatch):
    """Property 1 — the defect itself."""
    leaked = {}
    for a in _fired(monkeypatch):
        words = _english_prose_in(a.message_zh)
        if words:
            leaked[a.rule] = (a.message_zh, words)
    assert not leaked, (
        "message_zh interpolates untranslated English — the half-translated shape "
        "that reaches the hub feed and ms-sig-detail:\n"
        + "\n".join(f"  {r}: {zh}\n      leaked: {w}" for r, (zh, w) in leaked.items()))


def test_emitter_agrees_with_backlog_translator(monkeypatch):
    """Property 2 — the two zh paths must not drift apart again.

    build_vector._translate_macro_detail rebuilds zh from the canonical English
    for rows that predate the message_zh column. When it and the emitter disagree
    one of them is wrong, and the stored value silently wins on the hub.
    """
    drift = {}
    for a in _fired(monkeypatch):
        rebuilt = _translate_macro_detail(a.message)
        if not rebuilt:
            continue          # rule has no backlog branch — nothing to agree with
        if rebuilt != a.message_zh:
            drift[a.rule] = (a.message_zh, rebuilt)
    assert not drift, (
        "engine/alerts.py and scripts/build_vector._translate_macro_detail render "
        "the same alert differently:\n"
        + "\n".join(f"  {r}\n    emitter   : {e}\n    translator: {t}"
                    for r, (e, t) in drift.items()))


def test_state_vocabularies_cover_the_emitters_domain():
    """Property 1, statically — a new state must not fall through to English."""
    # transition_state_change's own severity map is the state domain
    src = __import__("inspect").getsource(alerts.transition_state_change)
    states = set(re.findall(r'"([A-Z_]{4,})":\s*"(?:info|warn|act)"', src))
    assert states, "severity map shape moved — this test can no longer see the domain"
    assert states <= set(_TS_PLAIN_ZH), (
        f"transition states with no Chinese: {sorted(states - set(_TS_PLAIN_ZH))}")

    gex_src = __import__("inspect").getsource(alerts.gex_flip_cross)
    whats = set(re.findall(r'what = "([^"]+)" if crossed_flip else "([^"]+)"', gex_src)[0])
    assert whats <= set(_GEX_WHAT_ZH), (
        f"GEX clauses with no Chinese: {sorted(whats - set(_GEX_WHAT_ZH))}")

    assert {"added", "cut"} <= set(_HOLDINGS_VERB_ZH)
    assert {"low", "elevated", "high"} <= set(_RECESSION_BAND_ZH)
    assert {"RISK-OFF", "ELEVATED"} <= set(_RISK_STATE_ZH)


def test_hub_feed_heals_baked_half_translated_rows(monkeypatch):
    """Property 3, through the REAL resolution — not a re-implementation of it.

    Drives scripts.build_vector.home_alert_feed over a parquet of poisoned rows,
    so emptying _ZH_HALF_TRANSLATED_RULES or dropping the heal branch reds here.
    """
    import scripts.build_vector as bv

    poisoned = pd.DataFrame([
        {"date": "2026-08-04", "rule": "gex_flip_cross", "severity": "warn",
         "message": "GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)",
         "message_zh": "GEX：net GEX changed sign（净 +79bn，现价相对翻转点 -0.7%）"},
        {"date": "2026-08-03", "rule": "transition_state_change", "severity": "act",
         "message": "Transition state WEAKENING -> TRANSITIONING (3 flags active)",
         "message_zh": "转换状态 WEAKENING -> TRANSITIONING（3 个预警激活）"},
        {"date": "2026-08-02", "rule": "sector_holdings_accumulation", "severity": "warn",
         "message": ("XLRE: PSA weight +0.26pp beyond price (≈+$23M est. rebalance flow) "
                     "(accumulating), 2026-07-17..2026-07-24 — cycle UNCONFIRMED TURN·"
                     "HIGH-RISK · NIMBLE ONLY"),
         "message_zh": ("XLRE：PSA 权重较价格多变动 +0.26pp（≈+$23M 估算再平衡资金流）（增持），"
                        "2026-07-17..2026-07-24 — 周期 UNCONFIRMED TURN·HIGH-RISK · NIMBLE ONLY")},
    ])
    monkeypatch.setattr(bv.pd, "read_parquet", lambda *a, **k: poisoned)

    feed = [i for i in bv.home_alert_feed() if i["source"] == "macro"]
    assert len(feed) == len(poisoned), "the poisoned rows did not reach the feed"
    bad = [f"  {i['type']}: {i['detail_zh']}\n      leaked: {_english_prose_in(i['detail_zh'])}"
           for i in feed if _english_prose_in(i["detail_zh"])]
    assert not bad, (
        "home_alert_feed still serves the stored half-translated zh — the heal "
        "branch or _ZH_HALF_TRANSLATED_RULES stopped covering these rules:\n"
        + "\n".join(bad))


def test_baked_log_rows_still_render_chinese():
    """The real shipped log, so a row shape the translator cannot parse is caught."""
    pytest.importorskip("pyarrow")
    p = ROOT / "data" / "alerts" / "alerts_log.parquet"
    if not p.exists():
        pytest.skip("alerts_log.parquet not present")
    df = pd.read_parquet(p)
    bad = []
    for _, r in df[df["rule"].isin(_ZH_HALF_TRANSLATED_RULES)].iterrows():
        stored = str(r.get("message_zh", "") or "").strip()
        resolved = _translate_macro_detail(r["message"]) or stored or r["message"]
        words = _english_prose_in(resolved)
        if words:
            bad.append(f"  {r['rule']} [{r['date']}]: {resolved}\n      leaked: {words}")
    assert not bad, (
        "half-translated backlog rows still reach the hub feed — the translator "
        "lost a branch these rows depend on:\n" + "\n".join(bad[:8]))


def test_leaky_rule_set_matches_the_translator_coverage():
    """Every rule listed as needing the heal must actually have a branch to heal with."""
    samples = {
        "gex_flip_cross": "GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)",
        "transition_state_change": "Transition state WEAKENING -> TRANSITIONING (3 flags active)",
        "conditions_recession_state_change": "Recession-risk band low -> elevated (score 62/100)",
        "risk_state_elevated": (
            "Equity risk-state crossed into RISK-OFF (78/100) — positioning/vol/breadth "
            "fragility building; de-gross, favor entries over chasing leaders"),
        "holdings_active_change": (
            "ARKK: manager cut FIG by -100% of position "
            "(2026-07-24..2026-07-31, flow-normalized)"),
        "sector_holdings_accumulation": (
            "XLRE: PSA weight +0.26pp beyond price (≈+$23M est. rebalance flow) "
            "(accumulating), 2026-07-17..2026-07-24 — cycle UNCONFIRMED TURN·"
            "HIGH-RISK · NIMBLE ONLY"),
    }
    assert set(samples) == set(_ZH_HALF_TRANSLATED_RULES), (
        "_ZH_HALF_TRANSLATED_RULES changed — update the sample messages so the "
        "heal stays covered")
    for rule, msg in samples.items():
        zh = _translate_macro_detail(msg)
        assert zh, f"{rule}: translator has no branch, so the heal is a no-op"
        assert not _english_prose_in(zh), f"{rule}: heal output still English: {zh}"
