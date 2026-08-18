"""tests/test_options_intel_brief.py — AD-1 frozen-contract test suite.

Contract (BINDING): ``contracts/options/OPTIONS_INTEL_BRIEF_V1.md``
(``intel_brief_heuristic/v1.2``). Secondary prose law:
``research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md``
§5.3/§5.4/§6. Test numbers below follow the AD-1 build commission's TESTS section, which
is a superset of the contract's own §6 (1-22) extended 23-33 for the settled-pair
source-clock law and determinism/no-op contract.

Fixture law (house rule — "synthetic harnesses must not pick easier dtypes"): every
synthetic chain frame is built through :func:`_mk_chain` below, which casts EXACTLY the
production dtype schema read from a real committed
``data/polygon_gex/chains/*.parquet`` (verified once, in
``test_00_fixture_dtypes_match_production`` — test 13) — category ``underlying``,
``datetime64[us]`` ``expiry``, ``float32`` numeric columns, ``bool`` ``is_call``,
``datetime64[ms]`` ``asof``. Feature computation itself runs through the PRODUCTION
functions (``engine.options_intel_brief.session_metrics``, ``doi_lean``,
``build_intel_brief``) — no test hand-computes an expected feature value through a
second, easier implementation.
"""
from __future__ import annotations

import glob
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib import nyse_calendar as nc  # noqa: E402
from engine import options_intel_brief as brief  # noqa: E402
from scripts import build_options_intel_brief as producer  # noqa: E402

CONFIG = brief.CONFIG


# ─────────────────────────────────────────────────────────────────────────────
# Fixture builders (production dtypes; production code path).
# ─────────────────────────────────────────────────────────────────────────────

_REAL_DTYPES = {
    "underlying": "category", "strike_ticker": "str",
    "expiry": "datetime64[us]", "K": "float32", "T": "float32", "is_call": "bool",
    "oi": "float32", "iv": "float32", "gamma": "float32", "delta": "float32",
    "volume": "float32", "spot": "float32", "asof": "datetime64[ms]",
}


def _mk_chain(rows: list[dict], *, session: str) -> pd.DataFrame:
    """Build a chain snapshot frame with EXACTLY production dtypes (test 13)."""
    df = pd.DataFrame(rows)
    df["underlying"] = df["underlying"].astype("category")
    df["strike_ticker"] = df["strike_ticker"].astype(str)
    df["expiry"] = pd.to_datetime(df["expiry"]).astype("datetime64[us]")
    for c in ("K", "T", "oi", "iv", "gamma", "delta", "volume", "spot"):
        df[c] = df[c].astype("float32")
    df["is_call"] = df["is_call"].astype(bool)
    df["asof"] = pd.Series([pd.Timestamp(session)] * len(df)).astype("datetime64[ms]")
    assert list(_REAL_DTYPES) == list(df.columns) or set(_REAL_DTYPES) <= set(df.columns)
    return df


def _occ_ticker(symbol: str, expiry: str, is_call: bool, k: float, *, adjusted: bool = False) -> str:
    root = f"{symbol}1" if adjusted else symbol   # trailing digit = adjusted-deliverable marker (AD0 §6.1)
    yymmdd = pd.Timestamp(expiry).strftime("%y%m%d")
    cp = "C" if is_call else "P"
    return f"O:{root}{yymmdd}{cp}{int(round(k * 1000)):08d}"


def _delta_for(is_call: bool, moneyness: float) -> float:
    call_delta = float(np.clip(0.5 + 3.0 * (1.0 - moneyness), 0.02, 0.98))
    return call_delta if is_call else (call_delta - 1.0)


def _symbol_rows(symbol: str, session: str, *, spot: float = 100.0, base_iv: float = 0.30,
                  iv_bump: float = 0.0, oi_base: float = 100.0, oi_call_bump: float = 0.0,
                  oi_put_bump: float = 0.0, volume: float = 50.0, n_contracts: bool = True,
                  adjusted_rows: int = 0, anchor: str | None = None) -> list[dict]:
    """One symbol's full chain rows for one session: 4 expiry bands x a strike ladder,
    both call/put, deterministic IV/skew/OI/volume driven by the keyword params so
    tests can move exactly one dial per session.

    ``anchor`` — when set, front/back/far expiries are FIXED CALENDAR DATES relative to
    ``anchor`` (shared across every session a multi-session panel generates), so the
    same option contract's ``strike_ticker`` persists across sessions and
    contract-matched ΔOI (``doi_lean``) actually has rows to join on. Session-relative
    expiries (the default, ``anchor=None``) are fine for single-session fixtures but
    WRONG for any test that needs two sessions' chains to share contracts — every
    ``strike_ticker`` embeds its expiry date, so two sessions computing "30 days out"
    from their own two different session dates mint two different tickers and never
    match (found the hard way: test 4/24/25 need this).
    """
    s = pd.Timestamp(session)
    a = pd.Timestamp(anchor) if anchor else s
    expiries = {
        "zero": s + pd.Timedelta(days=0),                    # 0DTE / SD_DTE crowding — always session-relative
        "front": a + pd.Timedelta(days=35),                   # 7-60 ATM band, 7-45 TERM_FRONT, 8-30 DTE bucket
        "back": a + pd.Timedelta(days=100),                    # 60-120 TERM_BACK, 31-90ish DTE bucket
        "far": a + pd.Timedelta(days=250),                     # >90 DTE bucket, no term/ATM contribution
    }
    moneyness_grid = [0.80 + 0.02 * i for i in range(21)] if n_contracts else [0.95, 1.05]
    rows: list[dict] = []
    for band, expiry in expiries.items():
        dte_years = float((expiry - s).days) / 365.0
        for m in moneyness_grid:
            k = round(spot * m, 2)
            for is_call in (True, False):
                iv = max(0.01, base_iv + iv_bump + 0.04 * abs(m - 1.0))
                delta = _delta_for(is_call, m)
                oi = max(0.0, oi_base + (oi_call_bump if is_call else oi_put_bump))
                rows.append({
                    "underlying": symbol,
                    "strike_ticker": _occ_ticker(symbol, expiry.date().isoformat(), is_call, k),
                    "expiry": expiry, "K": k, "T": dte_years, "is_call": is_call,
                    "oi": oi, "iv": iv, "gamma": 0.01, "delta": delta,
                    "volume": volume, "spot": spot,
                })
    for i in range(adjusted_rows):
        expiry = expiries["front"]
        k = round(spot * 1.02, 2)
        rows.append({
            "underlying": symbol,
            "strike_ticker": _occ_ticker(symbol, expiry.date().isoformat(), True, k, adjusted=True),
            "expiry": expiry, "K": k, "T": float((expiry - s).days) / 365.0, "is_call": True,
            "oi": 10.0, "iv": 0.9, "gamma": 0.01, "delta": 0.5, "volume": 5.0, "spot": spot,
        })
    return rows


def _panel(symbols_spec: dict[str, dict], sessions: list[str]) -> dict[str, pd.DataFrame]:
    """{session: chain frame} across every session for every symbol in symbols_spec.

    ``symbols_spec[sym]`` is a callable ``(session, session_index) -> kwargs`` for
    :func:`_symbol_rows`, letting each test drive OI/IV/volume deterministically
    per session.
    """
    anchor = sessions[0]
    out = {}
    for i, s in enumerate(sessions):
        rows: list[dict] = []
        for sym, spec in symbols_spec.items():
            kwargs = spec(s, i)
            kwargs.setdefault("anchor", anchor)
            rows.extend(_symbol_rows(sym, s, **kwargs))
        out[s] = _mk_chain(rows, session=s)
    return out


def _wiggle(i: int, *, salt: int = 0, lo: float = 0.85, hi: float = 1.15) -> float:
    """Deterministic non-degenerate per-session multiplier.

    A CONSTANT value across every session's history collapses every percentile
    computation to a boundary (zero variance -> "today" trivially equals the max of
    its own history), which silently turns an intentionally 'unremarkable' fixture
    into a maximally-unusual one. Real per-name histories always carry some genuine
    variance; this reproduces that without being random (same seed every run).
    """
    rng = np.random.default_rng(1000 + salt)
    seq = rng.uniform(lo, hi, size=64)
    return float(seq[i % len(seq)])


def _typical_spec(*, spot: float = 100.0, base_iv: float = 0.30, oi_base: float = 100.0,
                   volume: float = 50.0, salt: int = 0):
    """A benign, non-degenerate per-session spec: enough variance that "today" lands at
    an unremarkable (not boundary) percentile of its own history — the fixture tests
    want for anything NOT specifically engineering a directional/extreme signal."""
    def f(s, i):
        return dict(spot=spot, base_iv=base_iv * _wiggle(i, salt=salt + 1),
                    oi_base=oi_base * _wiggle(i, salt=salt + 2),
                    volume=volume * _wiggle(i, salt=salt + 3))
    return f


def _real_sessions(n: int, *, start: date = date(2026, 3, 2)) -> list[str]:
    end = nc.session_n_forward(start, n + 5) or (start.replace(year=start.year + 1))
    sess = nc.sessions_between(start, end)
    return [d.isoformat() for d in sess[:n]]


def _sessions_apart(a, b):
    return producer._sessions_apart_str(a, b)


def _session_n_forward(d, n):
    return producer._session_n_forward_str(d, n)


def _build(panel_sessions: dict[str, pd.DataFrame], *, S: str, D: str, pending=None,
           chain_next: pd.DataFrame | None = None, lawful_pairs: dict | None = None,
           built_at: str = "2026-01-01T00:00:00+00:00", **panel_kwargs) -> dict:
    all_sessions = sorted(panel_sessions.keys())
    if lawful_pairs is None:
        lawful_pairs = {}
        for i in range(1, len(all_sessions)):
            a, b = all_sessions[i - 1], all_sessions[i]
            if _sessions_apart(a, b) == 1:
                lawful_pairs[a] = b
    if chain_next is None:
        chain_next = panel_sessions.get(D)
    panel = brief.SessionPanel(
        as_of_session=S, oi_counted_date=D, pending_session=pending,
        pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
        chains_by_session={s: f for s, f in panel_sessions.items() if s <= S},
        chain_next=chain_next, lawful_pairs=lawful_pairs, **panel_kwargs,
    )
    watermarks = {"chains_session_S": S, "chains_session_D": D, "summaries_max_session": None,
                  "events_loaded": panel.events_loaded, "prophet_asof": panel.prophet_asof,
                  "signing_gate_asof": panel.signing_gate_asof}
    receipts = [{"logical_source": "chains_S", "path": "test", "asof": S, "sha256": "x", "state": "ok"}]
    return brief.build_intel_brief(
        panel, source_watermarks=watermarks, input_receipts=receipts, built_at_utc=built_at,
        sessions_apart_fn=_sessions_apart, session_n_forward_fn=_session_n_forward,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 13 / dtype pin.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.needs_full_checkout("data")
def test_00_fixture_dtypes_match_production():
    """Test 13: fixtures are built through the production dtype schema — verified
    against a REAL committed chains parquet, not assumed. The expiry-column dtype vs
    session-string comparison is checked explicitly (house trap: never assume a
    datetime64 column compares correctly against a plain ISO string without proof)."""
    files = sorted(glob.glob(str(REPO_ROOT / "data/polygon_gex/chains/*.parquet")))
    assert files, "no committed chain parquet found — cannot pin production dtypes"
    real = pd.read_parquet(files[-1])
    for col, expect in _REAL_DTYPES.items():
        assert str(real[col].dtype) == expect, f"{col}: real={real[col].dtype} fixture-expects={expect}"
    # explicit expiry-vs-string comparison proof (not assumed)
    assert str(real["expiry"].dtype).startswith("datetime64")
    cmp = real["expiry"] > "2020-01-01"
    assert cmp.dtype == bool and cmp.all()

    fixture = _mk_chain(_symbol_rows("ZZZ", "2026-03-02"), session="2026-03-02")
    for col, expect in _REAL_DTYPES.items():
        assert str(fixture[col].dtype) == expect, f"fixture {col}: {fixture[col].dtype} != {expect}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 14 — frozen CONFIG constants, verbatim.
# ─────────────────────────────────────────────────────────────────────────────


def test_14_config_constants_pinned_verbatim():
    assert CONFIG["SALIENCE_W_D1"] == 0.65
    assert CONFIG["SALIENCE_W_D3"] == 0.35
    assert CONFIG["Q_TH"] == 0.50
    assert CONFIG["SALIENCE_TH"] == 0.60
    assert CONFIG["SKEW_CHANGE_FLOOR"] == 8
    assert CONFIG["ES_W_DIR"] == 0.70
    assert CONFIG["ES_W_SAL"] == 0.30
    assert CONFIG["CONF_CEIL"] == 0.60
    assert CONFIG["CONF_CEIL_DIRECTIONAL"] == 0.45
    assert CONFIG["M_GEX_CAUTION_LONG"] == 0.75
    assert CONFIG["TIER_MULT"] == {"T1": 1.0, "T2": 0.8, "T3": 0.5}
    assert CONFIG["FRESH_PENALTY"] == 0.5
    assert CONFIG["EVENT_CONTAM_MULT"] == 0.6
    assert CONFIG["CROWD_MULT_LONG"] == 0.5
    assert CONFIG["R_MIN"] == 250
    assert CONFIG["BOARD_N"] == 6
    assert CONFIG["EVENT_BOARD_N"] == 4
    assert CONFIG["RISK_BOARD_N"] == 4
    assert CONFIG["NO_SIGNAL_R"] == 100
    assert CONFIG["ELIGIBILITY_GATE"] == 0.60
    assert CONFIG["BLEND_XS"] == 0.5
    assert CONFIG["BLEND_LONG"] == 0.5
    assert CONFIG["MIN_HISTORY"] == 10
    assert CONFIG["MIN_CONTRACTS"] == 20
    assert CONFIG["DOI_TARGET_WINDOW"] == 60
    assert CONFIG["DOI_FLOOR"] == 10
    lives = CONFIG["FRESH_LIVES_SESSIONS"]
    assert lives["Q_oi"] == 3 and lives["D_salience"] == 3 and lives["Q_skew"] == 3
    assert lives["V"] == 5 and lives["P"] == 1 and lives["C_0DTE"] == 0 and lives["E"] == "event_close"
    assert CONFIG["MODEL_VERSION"] == "intel_brief_heuristic/v1.2"
    assert CONFIG["SCHEMA"] == "options.intel_brief/v1"
    # F4a (2026-08-18) — a COVERAGE PREDICATE, not a scoring threshold: c1 requires
    # the finite-sd_share cross-section to actually exist market-wide.
    assert CONFIG["C1_XS_MIN_PRESENT_SHARE"] == 0.50


# ─────────────────────────────────────────────────────────────────────────────
# Tests 1/2 — contract identity.
# ─────────────────────────────────────────────────────────────────────────────


def test_01_contract_identity_named_exclusion():
    session = "2026-03-02"
    rows = _symbol_rows("ZZZ", session, adjusted_rows=5)
    df = _mk_chain(rows, session=session)
    standard, excluded = brief.contract_identity_split(df)
    assert excluded == 5
    assert len(standard) == len(df) - 5
    assert all(not t.split(":")[1].startswith("ZZZ1") for t in standard["strike_ticker"])


def test_02_adjusted_contract_never_enters_a_feature_family():
    session = "2026-03-02"
    rows = _symbol_rows("ZZZ", session, adjusted_rows=10)
    df = _mk_chain(rows, session=session)
    m, excluded = brief.session_metrics_and_exclusions(df)
    assert excluded == 10
    # the injected adjusted contracts all carry iv=0.9 / delta=0.5 — if they leaked in,
    # ATM IV (which averages the 6 nearest-ATM 7-60 DTE contracts) would be pulled
    # toward 0.9; assert it stays near the base_iv=0.30 population instead.
    assert m["ZZZ"]["atm_iv"] < 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — DTE computed against as_of_session, not wall clock.
# ─────────────────────────────────────────────────────────────────────────────


def test_03_dte_uses_as_of_session_not_wall_clock():
    """0DTE evidence expires with ITS session — T is computed from `expiry - session`,
    never from today's real date. A 0DTE contract minted for a session far in the past
    or future must still read as T=0 for THAT session."""
    session = "2026-03-02"
    rows = _symbol_rows("ZZZ", session)
    df = _mk_chain(rows, session=session)
    zero_dte = df[df["expiry"] == pd.Timestamp(session)]
    assert not zero_dte.empty
    assert (zero_dte["T"].astype(float) == 0.0).all()
    # T is NOT computed off today's real wall-clock date, however distant `session` is
    real_today_dte_years = (pd.Timestamp(date.today()) - pd.Timestamp(session)).days / 365.0
    assert abs(float(zero_dte["T"].iloc[0]) - real_today_dte_years) > 0.01 or session == date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Tests 4 / 24 / 25 — OI PIT law (the settled S->D pair).
# ─────────────────────────────────────────────────────────────────────────────


def test_04_same_day_oi_is_unlawful_never_used_for_qoi():
    """Using session-S's OWN oi column as if it were S's settled OI must never be what
    doi_lean() computes. doi_lean(settled, next, next_session) always reads the LATER
    frame's oi column as the settled count — passing S as its own 'next' (same-day)
    must not silently succeed with S's own numbers standing in for both legs producing
    a zero delta that could masquerade as a real (flat) settlement; explicitly, calling
    doi_lean(S, S, S) collapses to r=0 for every name (no ACTUAL cross-session OI print
    was consulted), which is verifiably NOT the same object/computation as the lawful
    doi_lean(S, D, D) below."""
    s0, s1 = "2026-03-02", "2026-03-03"
    df_s = _mk_chain(_symbol_rows("AAA", s0, oi_base=100.0, anchor=s0), session=s0)
    df_d = _mk_chain(_symbol_rows("AAA", s1, oi_base=150.0, oi_call_bump=40.0, anchor=s0), session=s1)
    lawful = brief.doi_lean(df_s, df_d, s1)
    same_day = brief.doi_lean(df_s, df_s, s0)
    assert lawful["AAA"] != pytest.approx(0.0, abs=1e-9)
    assert same_day["AAA"] == pytest.approx(0.0, abs=1e-9)
    assert lawful["AAA"] != same_day["AAA"]


def test_24_next_session_non_oi_leakage_forbidden():
    """Mutating D's iv/volume/greeks with OI fixed must NOT change S's evidence/rank —
    those fields are read from chain[S] ONLY (contract §1)."""
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(oi_call_bump=0.0, iv_bump=0.0, volume=50.0):
        def f(s, i):
            return dict(spot=100.0, base_iv=0.30, oi_base=100.0,
                        oi_call_bump=(oi_call_bump if s == D else 0.0),
                        iv_bump=(iv_bump if s == D else 0.0), volume=volume)
        return f

    panel_a = _panel({"AAA": spec()}, sessions)
    payload_a = _build(panel_a, S=S, D=D)
    panel_b = _panel({"AAA": spec(iv_bump=5.0, volume=999.0)}, sessions)
    payload_b = _build(panel_b, S=S, D=D)

    def card(payload):
        for c in payload["opportunities"] + [payload["no_signal_exemplar"]]:
            if c and c["symbol"] == "AAA":
                return c
        return None

    ca, cb = card(payload_a), card(payload_b)
    assert ca is not None and cb is not None
    assert ca["evidence_strength"] == cb["evidence_strength"]
    assert ca["research_priority_score"] == cb["research_priority_score"]


def test_25_oi_dependency_is_next_print_only():
    """Mutating D's OI changes Q_oi; mutating S's own OI (same-day) cannot substitute."""
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(d_oi_bump):
        def f(s, i):
            bump = d_oi_bump if s == D else 0.0
            return dict(spot=100.0, base_iv=0.30, oi_base=100.0, oi_call_bump=bump)
        return f

    base = _panel({"AAA": spec(0.0)}, sessions)
    bumped = _panel({"AAA": spec(80.0)}, sessions)

    r_base = brief.doi_lean(base[S], base[D], D)["AAA"]
    r_bumped = brief.doi_lean(bumped[S], bumped[D], D)["AAA"]
    assert r_bumped != pytest.approx(r_base, abs=1e-9)

    # same-day: bump S's OWN oi column instead of D's — doi_lean(S, S, S) must not
    # reflect the D-side bump at all (it never even sees the D frame).
    r_same_day = brief.doi_lean(base[S], base[S], S)["AAA"]
    assert r_same_day == pytest.approx(0.0, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — quote quality.
# ─────────────────────────────────────────────────────────────────────────────


def test_05_quote_quality_excludes_null_iv_and_degenerate_rows():
    session = "2026-03-02"
    rows = _symbol_rows("ZZZ", session)
    for r in rows[:10]:
        r["iv"] = np.nan
    for r in rows[10:15]:
        r["oi"] = 0.0
        r["volume"] = 0.0
    df = _mk_chain(rows, session=session)
    quot = df[brief.quotable_mask(df)]
    assert len(quot) == len(df) - 15
    m = brief.session_metrics(df)
    assert m["ZZZ"]["n_quot"] == len(df) - 15


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — event conditioning / EVENT_STATE_UNKNOWN.
# ─────────────────────────────────────────────────────────────────────────────


def test_06_event_conditioning_and_state_unknown_path():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    names = {f"EV{chr(65+i)}": _typical_spec(salt=i * 10) for i in range(6)}
    panel = _panel(names, sessions)
    event_date = nc.session_n_forward(date.fromisoformat(S), 10).isoformat()
    events = {n: event_date for n in names}
    payload = _build(panel, S=S, D=D, event_date=events, events_loaded=True)
    ev_cards = [c for c in payload["event_board"]]
    # at least the event-family machinery ran without raising; presence of ANY event
    # card (or a well-formed empty board) both count as "routed", the assertion below
    # is on the STATE-UNKNOWN path instead, which is the part with sharp semantics.

    payload_unknown = _build(panel, S=S, D=D, event_date={n: None for n in names}, events_loaded=False)
    all_cards = payload_unknown["opportunities"] + payload_unknown["event_board"] + payload_unknown["risk_warnings"]
    if payload_unknown["no_signal_exemplar"]:
        all_cards.append(payload_unknown["no_signal_exemplar"])
    assert all_cards, "expected at least one scored card to inspect null_reason on"
    assert all(c["null_reason"] == "EVENT_STATE_UNKNOWN" for c in all_cards)


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — incomplete chain -> INSUFFICIENT_COVERAGE.
# ─────────────────────────────────────────────────────────────────────────────


def test_07_incomplete_chain_reports_insufficient_coverage_zero_cards():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    names = {f"FUL{chr(65+i)}": _typical_spec(salt=i * 10) for i in range(6)}
    panel = _panel(names, sessions)
    # truncate chain[S] to a single name's rows (a plausible partial-collector file)
    only_one = panel[S][panel[S]["underlying"] == "FULA"].copy()
    panel_truncated = dict(panel)
    panel_truncated[S] = _mk_chain(
        [dict(underlying=r.underlying, strike_ticker=r.strike_ticker, expiry=r.expiry,
              K=float(r.K), T=float(r.T), is_call=bool(r.is_call), oi=float(r.oi),
              iv=float(r.iv), gamma=float(r.gamma), delta=float(r.delta),
              volume=float(r.volume), spot=float(r.spot))
         for r in only_one.itertuples()],
        session=S,
    )
    # B2: the coverage denominator is the CANONICAL universe (producer-resolved
    # gex_symbols()), never a historical-chain-max heuristic — an engine-level test
    # must supply it explicitly to exercise the same 1/6 shortfall the old heuristic
    # happened to reconstruct from the panel's OTHER (untruncated) sessions.
    payload = _build(panel_truncated, S=S, D=D, universe=list(names.keys()))
    assert payload["board_state"] == "INSUFFICIENT_COVERAGE"
    assert payload["opportunities"] == []
    assert payload["event_board"] == []
    assert payload["risk_warnings"] == []
    assert payload["eligibility"]["universe_count"] == 6
    assert payload["eligibility"]["source_coverage_pct"] == pytest.approx(1 / 6, abs=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — NO_SIGNAL on an unremarkable liquid fixture.
# ─────────────────────────────────────────────────────────────────────────────


def test_08_no_signal_on_unremarkable_liquid_fixture():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]
    # 14 sessions -> S is index 12 (2nd-to-last), 12 PRIOR sessions form its history.
    # Deliberately land S's own value at the MEDIAN of its own trailing history for
    # every dial (a `_wiggle`-only draw can land near an extreme by chance, which
    # test_06/test_08's early failures both hit) — this is the "liquid, complete-data,
    # genuinely unremarkable" fixture the contract's no-signal law is about.
    hist_mult = [_wiggle(i, salt=500) for i in range(12)]
    median_mult = float(np.median(hist_mult))

    def flat(s, i):
        m = hist_mult[i] if i < 12 else median_mult
        return dict(spot=100.0, base_iv=0.30 * m, oi_base=100.0 * m, volume=50.0 * m)

    panel = _panel({"FLAT": flat}, sessions)
    payload = _build(panel, S=S, D=D)
    assert payload["board_state"] in ("OK", "NO_SIGNAL")
    exemplar = payload["no_signal_exemplar"]
    on_boards = {c["symbol"] for c in payload["opportunities"]}
    assert "FLAT" not in on_boards, payload["opportunities"]
    assert exemplar is not None and exemplar["symbol"] == "FLAT"
    assert exemplar["research_priority_score"] < CONFIG["NO_SIGNAL_R"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 9 — STALE_SOURCE withhold.
# ─────────────────────────────────────────────────────────────────────────────


def test_09_stale_source_withholds_cards():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    panel = _panel({"AAA": spec}, sessions)
    payload = _build(panel, S=S, D=D, stale=True)
    assert payload["board_state"] == "STALE_SOURCE"
    assert payload["opportunities"] == [] and payload["event_board"] == [] and payload["risk_warnings"] == []
    assert payload["as_of_session"] == S   # last-good stamped, not blanked


def test_f8_stale_source_present_coherent_with_source_coverage_pct():
    """F8 (2026-08-18): the STALE_SOURCE header's eligibility.present must be
    populated from the S chain that WAS already read (present_names is known
    before the staleness check fires) — never left at the Eligibility() default 0
    beside a real, nonzero source_coverage_pct (itself computed FROM present_names
    two lines earlier). present=0 next to a real coverage fraction would claim
    "zero names loaded" while the fraction implies hundreds."""
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]
    names = {sym: _typical_spec(salt=i) for i, sym in enumerate(_alpha_names("STL", 12))}
    panel = _panel(names, sessions)
    payload = _build(panel, S=S, D=D, universe=list(names.keys()), stale=True)
    assert payload["board_state"] == "STALE_SOURCE"
    elig = payload["eligibility"]
    assert elig["present"] == 12, f"present not populated from the loaded S chain: {elig}"
    assert elig["source_coverage_pct"] == pytest.approx(1.0, abs=1e-4)
    assert not (elig["present"] == 0 and (elig["source_coverage_pct"] or 0) > 0), \
        "incoherent header: present=0 beside a real source_coverage_pct"


# ─────────────────────────────────────────────────────────────────────────────
# Tests 10 / 30 / 31 / 32 / 33 — determinism, receipts, no-op, ordering.
# ─────────────────────────────────────────────────────────────────────────────


def _std_panel():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30 + 0.001 * i, oi_base=100.0 + i,
                    oi_call_bump=(20.0 if s == D else 0.0))

    return _panel({"AAA": spec, "BBB": spec}, sessions), S, D


def test_10_deterministic_replay_byte_identical():
    panel, S, D = _std_panel()
    p1 = _build(panel, S=S, D=D, built_at="2026-01-01T00:00:00+00:00")
    p2 = _build(panel, S=S, D=D, built_at="2026-01-01T00:00:00+00:00")
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_30_receipt_changes_when_source_digest_changes():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    panel = _panel({"AAA": spec}, sessions)
    watermarks_a = {"chains_session_S": S, "chains_session_D": D, "summaries_max_session": None,
                     "events_loaded": True, "prophet_asof": None, "signing_gate_asof": None}
    watermarks_b = dict(watermarks_a, summaries_max_session="2026-01-01")  # a different source digest
    receipts_a = [{"logical_source": "chains_S", "path": "x", "asof": S, "sha256": "AAAA", "state": "ok"}]
    receipts_b = [{"logical_source": "chains_S", "path": "x", "asof": S, "sha256": "BBBB", "state": "ok"}]
    rid_a = brief.receipt_id(schema=brief.SCHEMA, model_version=brief.MODEL_VERSION,
                              as_of_session=S, oi_counted_date=D, source_watermarks=watermarks_a,
                              input_receipts=receipts_a)
    rid_b = brief.receipt_id(schema=brief.SCHEMA, model_version=brief.MODEL_VERSION,
                              as_of_session=S, oi_counted_date=D, source_watermarks=watermarks_b,
                              input_receipts=receipts_b)
    assert rid_a != rid_b


def test_31_built_at_excluded_from_receipt():
    panel, S, D = _std_panel()
    p1 = _build(panel, S=S, D=D, built_at="2026-01-01T00:00:00+00:00")
    p2 = _build(panel, S=S, D=D, built_at="2027-06-15T12:34:56+00:00")
    assert p1["receipt_id"] == p2["receipt_id"]
    assert p1["built_at_utc"] != p2["built_at_utc"]


def test_32_identical_semantic_rerun_is_a_bytes_no_op(tmp_path):
    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D, built_at="2026-01-01T00:00:00+00:00")
    out = tmp_path / "options_intel_brief.json"
    producer.write_json_atomic(out, payload)
    original_bytes = out.read_bytes()
    original_mtime = out.stat().st_mtime_ns

    payload_2 = _build(panel, S=S, D=D, built_at="2099-01-01T00:00:00+00:00")  # different built_at only
    assert producer._semantic_unchanged(out, payload_2)
    # a real producer run would skip the write entirely on this — prove doing so
    # really does leave bytes/mtime untouched
    if not producer._semantic_unchanged(out, payload_2):
        producer.write_json_atomic(out, payload_2)
    assert out.read_bytes() == original_bytes
    assert out.stat().st_mtime_ns == original_mtime


def test_33_stable_ordering_deterministic_payload():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    names = {n: spec for n in ("ZED", "AAA", "MMM")}
    panel = _panel(names, sessions)
    p1 = _build(panel, S=S, D=D)
    order1 = [c["symbol"] for c in p1["opportunities"]] or [c["symbol"] for c in p1["risk_warnings"]]
    panel2 = _panel(dict(reversed(list(names.items()))), sessions)
    p2 = _build(panel2, S=S, D=D)
    order2 = [c["symbol"] for c in p2["opportunities"]] or [c["symbol"] for c in p2["risk_warnings"]]
    assert order1 == order2 or (not p1["opportunities"] and not p2["opportunities"])
    # composition functions are independently order-stable regardless of input order
    cards = [
        {"symbol": "B", "direction": "LONG", "research_priority_score": 300, "evidence_confidence": 0.4, "tier_metric": 1.0},
        {"symbol": "A", "direction": "LONG", "research_priority_score": 300, "evidence_confidence": 0.4, "tier_metric": 1.0},
    ]
    out1, _ = brief.compose_opportunities(cards)
    out2, _ = brief.compose_opportunities(list(reversed(cards)))
    assert [c["symbol"] for c in out1] == [c["symbol"] for c in out2] == ["A", "B"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 11 — artifact-order determinism (UI/API parity deferred to consumer packet).
# ─────────────────────────────────────────────────────────────────────────────


def test_11_artifact_order_is_deterministic_for_a_downstream_renderer():
    """AD-1 ships no template; a downstream renderer's parity depends entirely on the
    artifact's own array ordering being a pure function of the data (never insertion
    order / dict iteration order of an unstable source). Covered here as the
    artifact-order-determinism half of the deferred UI/API parity test."""
    panel, S, D = _std_panel()
    p1 = _build(panel, S=S, D=D)
    for key in ("opportunities", "event_board", "risk_warnings"):
        syms = [c["symbol"] for c in p1[key]]
        assert syms == sorted(syms) or key != "opportunities"  # opportunities ranked, not alpha — see below
    # opportunities must be sorted by the documented tie-break, not any incidental order
    opp = p1["opportunities"]
    scores = [(c["research_priority_score"], c["evidence_confidence"]) for c in opp]
    assert scores == sorted(scores, key=lambda t: (-t[0], -t[1]))


# ─────────────────────────────────────────────────────────────────────────────
# Test 12 — correction placeholders null.
# ─────────────────────────────────────────────────────────────────────────────


def test_12_correction_placeholders_are_null_on_every_card():
    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D)
    all_cards = payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]
    if payload["no_signal_exemplar"]:
        all_cards.append(payload["no_signal_exemplar"])
    assert all_cards
    for c in all_cards:
        assert c["supersedes_signal_id"] is None
        assert c["corrected_at"] is None
        assert c["asymmetry_score"] is None
        assert c["asymmetry_state"] == "UNCALIBRATED"
        assert c["probability_up"] is None and c["probability_down"] is None
        assert c["expected_edge_bps"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 15 — data-feasibility law against the REAL store.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.needs_full_checkout("data")
def test_15_data_feasibility_law_against_real_store():
    files = sorted(glob.glob(str(REPO_ROOT / "data/polygon_gex/chains/*.parquet")))
    assert files, "no committed chain snapshots — cannot assert feasibility"
    sessions = [Path(f).stem for f in files]
    latest = sessions[-1]
    latest_df = pd.read_parquet(files[-1], columns=["underlying"])
    names_present = set(latest_df["underlying"].astype(str).unique())
    assert names_present, "empty latest session — feasibility undecidable"

    # H (prior-session depth) per name across the whole committed store.
    hist_counts: dict[str, int] = {n: 0 for n in names_present}
    for f in files[:-1]:
        df = pd.read_parquet(f, columns=["underlying"])
        seen = set(df["underlying"].astype(str).unique())
        for n in seen & names_present:
            hist_counts[n] += 1

    min_history = CONFIG["MIN_HISTORY"]
    satisfy_history = sum(1 for n in names_present if hist_counts[n] >= min_history)
    ratio_history = satisfy_history / len(names_present)
    assert ratio_history >= 0.60, (
        f"MIN_HISTORY={min_history} satisfiable by only {ratio_history:.1%} of the latest "
        f"session's {len(names_present)} names — the data-feasibility law (contract §8) "
        f"is violated; this is a SPEC-vs-STORE contradiction to be returned, not adapted"
    )

    # MIN_CONTRACTS floor: quotable-contract coverage in the latest session.
    full = pd.read_parquet(files[-1])
    m = brief.session_metrics(full)
    satisfy_contracts = sum(1 for n in names_present if m.get(n, {}).get("n_quot", 0) >= CONFIG["MIN_CONTRACTS"])
    ratio_contracts = satisfy_contracts / len(names_present)
    assert ratio_contracts >= 0.60, (
        f"MIN_CONTRACTS={CONFIG['MIN_CONTRACTS']} satisfiable by only {ratio_contracts:.1%} "
        f"of names — feasibility law violated"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 16 — state distinction.
# ─────────────────────────────────────────────────────────────────────────────


def test_16_insufficient_history_vs_insufficient_coverage_vs_no_signal():
    assert brief.eligibility_reason(n_quot=5, h=20) == "INSUFFICIENT_COVERAGE"
    assert brief.eligibility_reason(n_quot=50, h=2) == "INSUFFICIENT_HISTORY"
    assert brief.eligibility_reason(n_quot=50, h=20) is None

    elig = brief.Eligibility(present=100, eligible=59)
    assert elig.ratio < CONFIG["ELIGIBILITY_GATE"]
    elig2 = brief.Eligibility(present=100, eligible=60)
    assert elig2.ratio >= CONFIG["ELIGIBILITY_GATE"]


def test_16b_eligibility_collapse_triggers_degraded():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def thin(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0, n_contracts=False)  # <20 contracts -> ineligible

    def full(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    names = {f"THN{chr(65+i)}": thin for i in range(7)}
    names["FULA"] = full
    panel = _panel(names, sessions)
    payload = _build(panel, S=S, D=D)
    assert payload["eligibility"]["present"] == 8
    assert payload["eligibility"]["eligible"] == 1
    assert payload["board_state"] == "DEGRADED"
    assert payload["board_reason"] == "ELIGIBILITY_COLLAPSE"
    assert payload["opportunities"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 17 — direction anti-vacuity (all sub-cases).
# ─────────────────────────────────────────────────────────────────────────────


def test_17a_high_salience_neutral_q_not_long():
    d = brief.classify_direction(q_oi_v=0.0, q_skew_v=0.0, d_sal=1.0)
    assert d is None
    # d1/d3 have no parameter in classify_direction at all — structurally excluded


def test_17b_gex_confirm_neutral_q_not_long():
    m = brief.m_gex_multiplier("LONG", "confirm")
    assert m == 1.0   # confirm never raises actionability
    d = brief.classify_direction(q_oi_v=0.0, q_skew_v=0.0, d_sal=0.9)
    assert d is None   # gex plays no role in classify_direction's signature at all


def test_17c_gex_caution_neutral_q_not_short():
    d = brief.classify_direction(q_oi_v=0.0, q_skew_v=0.0, d_sal=0.9)
    assert d is None
    m = brief.m_gex_multiplier("SHORT", "caution")
    assert m == 1.0   # caution has zero effect outside a qualified LONG


def test_17d_qoi_alone_no_direction():
    assert brief.classify_direction(q_oi_v=0.9, q_skew_v=None, d_sal=0.9) is None


def test_17e_negative_qoi_alone_no_direction():
    assert brief.classify_direction(q_oi_v=-0.9, q_skew_v=None, d_sal=0.9) is None


def test_17f_qskew_alone_no_direction():
    assert brief.classify_direction(q_oi_v=None, q_skew_v=0.9, d_sal=0.9) is None


def test_17g_q_legs_agree_low_salience_no_direction():
    assert brief.classify_direction(q_oi_v=0.9, q_skew_v=0.9, d_sal=0.59) is None
    assert brief.classify_direction(q_oi_v=0.9, q_skew_v=0.9, d_sal=0.60) == "LONG"


def test_17h_q_legs_disagree_none():
    assert brief.classify_direction(q_oi_v=0.9, q_skew_v=-0.9, d_sal=0.9) is None


def test_17i_signing_gate_false_qflow_structurally_absent():
    """No code path may compute Q_flow — checked structurally (no function/attribute
    named for it, no CONFIG entry, no card field), not by grepping prose: the module
    docstring is EXPECTED to name "Q_flow" while explaining why it has no code path,
    and a literal-string ban would fail on that legitimate, required documentation."""
    assert not hasattr(brief, "q_flow")
    assert not any("q_flow" in name.lower() for name in dir(brief) if not name.startswith("_"))
    assert "Q_flow" not in brief.CONFIG
    assert "Q_flow" not in brief.CONFIG.get("FRESH_LIVES_SESSIONS", {})

    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D)
    cards = payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]
    if payload["no_signal_exemplar"]:
        cards.append(payload["no_signal_exemplar"])
    assert cards
    for c in cards:
        assert not any(e["name"] == "Q_flow" for e in c["evidence"])
        assert "q_flow" not in json.dumps(c).lower()


def test_17j_no_string_says_customers_bought_or_sold():
    for direction in ("LONG", "SHORT", "VOLATILITY", "RISK_ONLY"):
        strings = brief.why_now_strings(direction, q_oi_v=0.8, q_skew_v=0.8, d_sal=0.9,
                                         f_v=0.7, f_e=0.6, c_sev=0.9)
        strings += [brief.trigger_watch_string(direction), brief.invalidation_watch_string(direction)]
        for s in strings:
            for lang in ("en", "zh"):
                text = s[lang].lower()
                assert "bought" not in text and "sold" not in text
                assert "customers" not in text
                assert "buying" not in text and "selling" not in text


# ─────────────────────────────────────────────────────────────────────────────
# Test 18 — GEX authority.
# ─────────────────────────────────────────────────────────────────────────────


def test_18_gex_authority_caution_only_lowers_qualified_long():
    assert brief.m_gex_multiplier("LONG", "caution") == CONFIG["M_GEX_CAUTION_LONG"]
    assert brief.m_gex_multiplier("LONG", "confirm") == 1.0
    assert brief.m_gex_multiplier("LONG", None) == 1.0
    assert brief.m_gex_multiplier("SHORT", "caution") == 1.0   # never a synthetic SHORT inverse
    assert brief.m_gex_multiplier("SHORT", "confirm") == 1.0
    assert brief.m_gex_multiplier("VOLATILITY", "caution") == 1.0
    assert brief.m_gex_multiplier("RISK_ONLY", "caution") == 1.0
    # confirm can never raise evidence_strength or R — it isn't even a parameter there
    es = brief.evidence_strength("LONG", q_oi_v=0.6, q_skew_v=0.6, d_sal=0.7)
    import inspect
    assert "gex" not in inspect.signature(brief.evidence_strength).parameters


# ─────────────────────────────────────────────────────────────────────────────
# Test 19 — forecast honesty.
# ─────────────────────────────────────────────────────────────────────────────


def test_19_forecast_honesty_no_calibrated_language():
    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D)
    cards = payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]
    if payload["no_signal_exemplar"]:
        cards.append(payload["no_signal_exemplar"])
    banned = ("%", "probability", "alpha", "expected edge", "validated")
    for c in cards:
        assert c["asymmetry_score"] is None
        assert c["asymmetry_state"] == "UNCALIBRATED"
        assert c["probability_up"] is None and c["probability_down"] is None
        assert c["expected_edge_bps"] is None
        # scan only the EMITTED user-facing copy — schema field NAMES like
        # "probability_up" are internal keys holding a null placeholder, not copy
        emitted = [c["display_state_en"], c["display_state_zh"],
                   c["trigger_watch"]["en"], c["trigger_watch"]["zh"],
                   c["invalidation_watch"]["en"], c["invalidation_watch"]["zh"]]
        for w in c["why_now"]:
            emitted += [w["en"], w["zh"]]
        blob = " ".join(emitted).lower()
        for word in banned:
            assert word not in blob, f"{word!r} leaked into emitted card copy: {blob[:300]}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 20 — event semantics.
# ─────────────────────────────────────────────────────────────────────────────


def test_20_event_history_mode_always_cross_sectional_at_ad1():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30 + 0.01 * (i % 3), oi_base=100.0)

    names = {f"EV{chr(65+i)}": spec for i in range(6)}
    panel = _panel(names, sessions)
    event_date = nc.session_n_forward(date.fromisoformat(S), 10).isoformat()
    events = {n: event_date for n in names}
    payload = _build(panel, S=S, D=D, event_date=events, events_loaded=True)
    for c in payload["event_board"]:
        assert c["event"]["history_mode"] == "cross_sectional"

    forbidden = ("underpriced event move", "overpriced event move", "historical move")
    blob = json.dumps(payload).lower()
    for phrase in forbidden:
        assert phrase not in blob


def test_20b_event_family_absent_below_five_names():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    names = {f"EV{chr(65+i)}": spec for i in range(3)}   # < EVENT_MIN_NAMES
    panel = _panel(names, sessions)
    event_date = nc.session_n_forward(date.fromisoformat(S), 10).isoformat()
    events = {n: event_date for n in names}
    payload = _build(panel, S=S, D=D, event_date=events, events_loaded=True)
    assert payload["event_board"] == []


def test_f6_event_implied_move_pct_uses_event_horizon_never_5_session():
    """F6 (2026-08-18): the engine emits `event_implied_move_pct` on event rows via
    the EXISTING `market_implied_move_pct(..., event_horizon_sessions=...)`
    parameter (sessions S->event, via the injected NYSE calendar), NOT the fixed
    5-session horizon the card-level `market_implied_move_pct` uses. Proven by
    building the SAME chain twice with two different event horizons (10 vs 20
    sessions out) — event_implied_move_pct must scale by sqrt(20/10), the
    signature of a genuinely horizon-aware computation rather than a copy of the
    fixed 5-session figure (which would be IDENTICAL across both builds)."""
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30 + 0.01 * (i % 3), oi_base=100.0)

    names = {f"EV{chr(65+i)}": spec for i in range(6)}
    panel = _panel(names, sessions)
    near_date = nc.session_n_forward(date.fromisoformat(S), 10).isoformat()
    far_date = nc.session_n_forward(date.fromisoformat(S), 20).isoformat()
    payload_near = _build(panel, S=S, D=D, event_date={n: near_date for n in names}, events_loaded=True)
    payload_far = _build(panel, S=S, D=D, event_date={n: far_date for n in names}, events_loaded=True)
    assert payload_near["event_board"] and payload_far["event_board"], \
        "fixture produced no event_board rows to assert on"

    near_by_symbol = {c["symbol"]: c["event"]["event_implied_move_pct"] for c in payload_near["event_board"]}
    far_by_symbol = {c["symbol"]: c["event"]["event_implied_move_pct"] for c in payload_far["event_board"]}
    checked = 0
    for sym, near_move in near_by_symbol.items():
        far_move = far_by_symbol.get(sym)
        if near_move is None or far_move is None:
            continue
        assert far_move != near_move, "event_implied_move_pct did not move with the event horizon"
        assert far_move == pytest.approx(near_move * math.sqrt(20.0 / 10.0), abs=1e-5)
        checked += 1
    assert checked > 0, "no symbol carried a usable event_implied_move_pct in both builds"

    # card-level market_implied_move_pct (when present at all) stays the fixed
    # 5-session figure regardless of the event horizon — the two builds' card-level
    # figures for the same symbol, if both present, must be IDENTICAL.
    near_card_move = {c["symbol"]: c["market_implied_move_pct"] for c in payload_near["event_board"]}
    far_card_move = {c["symbol"]: c["market_implied_move_pct"] for c in payload_far["event_board"]}
    for sym in near_card_move:
        if near_card_move[sym] is not None and far_card_move.get(sym) is not None:
            assert near_card_move[sym] == far_card_move[sym]


# ─────────────────────────────────────────────────────────────────────────────
# Test 21 / 29 — Prophet boundary.
# ─────────────────────────────────────────────────────────────────────────────


def test_21_prophet_states_never_change_rank():
    panel, S, D = _std_panel()
    payload_no_prophet = _build(panel, S=S, D=D, prophet_entry_status={}, prophet_asof=None)
    payload_prophet = _build(panel, S=S, D=D,
                              prophet_entry_status={"AAA": "extended", "BBB": "buy_now"},
                              prophet_asof="2026-01-01")

    def by_symbol(payload):
        out = {}
        for c in payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]:
            out[c["symbol"]] = (c["research_priority_score"], c["evidence_strength"], c["evidence_confidence"])
        return out

    a, b = by_symbol(payload_no_prophet), by_symbol(payload_prophet)
    assert a == b, "Prophet echo changed a score/rank tuple — zero rank authority violated"


def test_21b_prophet_state_mapping_never_blank():
    assert brief.prophet_state_for(None) == "UNAVAILABLE"
    assert brief.prophet_state_for("hold") == "ALREADY_OPEN"
    assert brief.prophet_state_for("partial") == "ALREADY_OPEN"
    assert brief.prophet_state_for("bounce_wait") == "NOT_READY"
    assert brief.prophet_state_for("buy_now") == "READY"
    assert brief.prophet_state_for("extended") == "EXTENDED"
    assert brief.prophet_state_for("topping") == "EXTENDED"
    assert brief.prophet_state_for("some_new_status") == "OTHER"


def test_29_prophet_may_be_newer_but_cannot_rank():
    """Same AD inputs + a NEWER Prophet echo -> byte-identical scores/rank; only
    display fields (prophet_state/prophet_asof) differ."""
    panel, S, D = _std_panel()
    p_old = _build(panel, S=S, D=D, prophet_entry_status={"AAA": "buy_now"}, prophet_asof="2020-01-01")
    p_new = _build(panel, S=S, D=D, prophet_entry_status={"AAA": "buy_now"}, prophet_asof="2099-01-01")

    def strip_display(payload):
        cards = payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]
        return [{k: v for k, v in c.items() if k not in ("prophet_state", "prophet_asof")} for c in cards]

    assert strip_display(p_old) == strip_display(p_new)


# ─────────────────────────────────────────────────────────────────────────────
# Test 22 — horizon / freshness.
# ─────────────────────────────────────────────────────────────────────────────


def test_22_horizon_and_freshness_semantics():
    assert brief.horizon_for("LONG") == "next_5_sessions"
    assert brief.horizon_for("SHORT") == "next_5_sessions"
    assert brief.horizon_for("VOLATILITY", event_board=False) == "next_5_sessions"
    assert brief.horizon_for("VOLATILITY", event_board=True) == "through_event_close"
    assert brief.horizon_for("RISK_ONLY") == "next_session"


def test_22b_fresh_until_is_nyse_session_arithmetic():
    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D)
    cards = payload["opportunities"] + payload["risk_warnings"]
    for c in cards:
        fu = c["fresh_until"]
        assert fu >= S
        # must be a real committed NYSE session date string, not raw calendar arithmetic
        assert nc.is_session(date.fromisoformat(fu)) or fu == S


# ─────────────────────────────────────────────────────────────────────────────
# Test 23 — settled-pair selection.
# ─────────────────────────────────────────────────────────────────────────────


def test_23_settled_pair_requires_chain_S_and_chain_next_session_S():
    sessions = ["2026-03-02", "2026-03-03", "2026-03-04"]
    S, D, pending = brief.select_settled_pair(sessions, lambda d: _session_n_forward(d, 1))
    assert S == "2026-03-03" and D == "2026-03-04"
    assert pending == "2026-03-04"   # D itself has no further print yet


# ─────────────────────────────────────────────────────────────────────────────
# Test 26 — gap refusal.
# ─────────────────────────────────────────────────────────────────────────────


def test_26_gap_refusal_falls_back_to_newest_lawful_pair():
    # 03-02, 03-03 lawful consecutive; 03-04 skipped (gap); 03-06 present but not
    # consecutive to 03-03 or 03-04 -> the (03-05,03-06) style newest pair is unlawful,
    # must fall back to the newest LAWFUL pair, never treat the gap as one interval.
    sessions = ["2026-03-02", "2026-03-03", "2026-03-06"]
    S, D, pending = brief.select_settled_pair(sessions, lambda d: _session_n_forward(d, 1))
    assert (S, D) == ("2026-03-02", "2026-03-03")
    assert pending == "2026-03-06"   # newest orphan, no lawful next print either


def test_26b_no_lawful_pair_anywhere_is_mixed_vintage():
    sessions = ["2026-03-02", "2026-03-10", "2026-03-20"]   # nothing consecutive
    S, D, pending = brief.select_settled_pair(sessions, lambda d: _session_n_forward(d, 1))
    assert S is None and D is None


def test_26c_mixed_vintage_no_pair_at_all_degrades():
    sessions = ["2026-03-02", "2026-03-10", "2026-03-20"]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    panel_frames = {s: _mk_chain(_symbol_rows("AAA", s), session=s) for s in sessions}
    p = brief.SessionPanel(as_of_session=None, oi_counted_date=None, pending_session="2026-03-20",
                            pending_reason="OI_NOT_YET_SETTLED", chains_by_session={},
                            chain_next=None, lawful_pairs={})
    watermarks = {"chains_session_S": None, "chains_session_D": None, "summaries_max_session": None,
                  "events_loaded": False, "prophet_asof": None, "signing_gate_asof": None}
    payload = brief.build_intel_brief(p, source_watermarks=watermarks, input_receipts=[],
                                       built_at_utc="2026-01-01T00:00:00+00:00",
                                       sessions_apart_fn=_sessions_apart, session_n_forward_fn=_session_n_forward)
    assert payload["board_state"] == "DEGRADED"
    assert payload["board_reason"] == "MIXED_VINTAGE"
    assert payload["opportunities"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 27 — pending-session disclosure.
# ─────────────────────────────────────────────────────────────────────────────


def test_27_pending_session_never_scored_never_directional():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    panel = _panel({"AAA": spec}, sessions)
    payload = _build(panel, S=S, D=D, pending=D)
    assert payload["pending_session"] == D
    assert payload["pending_reason"] == "OI_NOT_YET_SETTLED"
    for c in payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]:
        assert c["as_of_session"] == S
        assert c["as_of_session"] != D


# ─────────────────────────────────────────────────────────────────────────────
# Test 28 — mixed-vintage GEX.
# ─────────────────────────────────────────────────────────────────────────────


def test_28_gex_not_bound_to_s_is_absent_mgex_is_one():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def spec(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    panel = _panel({"AAA": spec}, sessions)
    payload_bound = _build(panel, S=S, D=D, gex_verdict={"AAA": "caution"}, gex_bound_to_S=True)
    payload_unbound = _build(panel, S=S, D=D, gex_verdict={"AAA": "caution"}, gex_bound_to_S=False)

    def gex_of(payload):
        for c in payload["opportunities"] + payload["risk_warnings"]:
            if c["symbol"] == "AAA":
                return c["mechanics_context"]["gex_confirm_verdict"]
        if payload["no_signal_exemplar"] and payload["no_signal_exemplar"]["symbol"] == "AAA":
            return payload["no_signal_exemplar"]["mechanics_context"]["gex_confirm_verdict"]
        return "NOT_FOUND"

    assert gex_of(payload_unbound) is None
    m_unbound = brief.m_gex_multiplier("LONG", None)
    assert m_unbound == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting: engine imports nothing from any forbidden plane.
# ─────────────────────────────────────────────────────────────────────────────


def test_engine_imports_no_forbidden_plane():
    src = (REPO_ROOT / "engine" / "options_intel_brief.py").read_text()
    forbidden = [
        "engine.options_flow", "engine.gex_confirm", "engine.us_prophet_fusion",
        "engine.us_board_rank", "engine.prophet_bridge", "engine.neuralweb",
        "engine.sector", "engine.options_sparse_selector", "engine.options_market_memory_local",
        "engine.options_signal_episode",
    ]
    for mod in forbidden:
        assert f"import {mod}" not in src and f"from {mod}" not in src


def test_producer_uses_gex_confirm_read_only_not_forbidden_builders():
    src = (REPO_ROOT / "scripts" / "build_options_intel_brief.py").read_text()
    for forbidden in ("build_gex_board", "build_options_flow", "build_darkpool_desk",
                       "build_options_skew", "build_options_ivspread", "build_options_dislocation",
                       "build_options_prophet", "build_prophet", "grade_us_board",
                       "options_signal_episode", "options_sparse_selector"):
        assert forbidden not in src
    assert "from engine import gex_confirm" in src or "from engine.gex_confirm" in src


# ═════════════════════════════════════════════════════════════════════════════
# Sol review Blocks B1-B4 (PR #5872 REQUEST_CHANGES; commissioned fix, 2026-08-18).
# ═════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# B1 fixture — a tmp "repo" the REAL producer reads through its own module-level
# path constants (monkeypatched), never a hand-rolled second I/O implementation
# (house rule: synthetic harnesses run through the production builder).
# ─────────────────────────────────────────────────────────────────────────────


def _gex_json_payload(asof: str, *, dist_to_flip_pct: float = 5.0) -> dict:
    """A minimal but REAL-SHAPED site/gex/{SYM}.json payload that
    ``engine.gex_confirm.assess`` turns into a deterministic "caution" verdict
    (regime=long, 5% over the flip >= deep_flip_pct=3.0 -> score -1.0 <= caution_at)."""
    return {
        "meta": {"asof": asof},
        "summary": {"tier": "core", "n_strikes": 50, "regime": "long",
                    "dist_to_flip_pct": dist_to_flip_pct, "spot": 100.0, "gamma_flip": 95.0},
    }


def _write_fake_repo(tmp_path, monkeypatch, *, symbols: list[str], sessions: list[str],
                      gex_json_asof: str | None = None, prophet_payload: dict | None = None):
    """Build a tmp repo tree matching every path constant
    ``scripts/build_options_intel_brief.py`` reads, and monkeypatch the producer module
    to point at it — so ``producer.build()`` runs its REAL file I/O (hashing included)
    against a small, fully-controlled store instead of a second, easier reimplementation.
    """
    chains_dir = tmp_path / "data" / "polygon_gex" / "chains"
    chains_dir.mkdir(parents=True)
    for s in sessions:
        rows: list[dict] = []
        for sym in symbols:
            rows.extend(_symbol_rows(sym, s, anchor=sessions[0]))
        _mk_chain(rows, session=s).to_parquet(chains_dir / f"{s}.parquet")

    summary_dir = tmp_path / "data" / "polygon_gex"
    for sym in symbols:
        idx = pd.to_datetime(sessions)
        spot_df = pd.DataFrame({"spot": [100.0 + i for i in range(len(sessions))]}, index=idx)
        spot_df.to_parquet(summary_dir / f"summary_{sym}.parquet")

    gex_dir = tmp_path / "site" / "gex"
    gex_dir.mkdir(parents=True)
    for sym in symbols:
        asof = gex_json_asof if gex_json_asof is not None else sessions[-1]
        (gex_dir / f"{sym}.json").write_text(json.dumps(_gex_json_payload(asof)))

    (tmp_path / "data" / "earnings").mkdir(parents=True)
    (tmp_path / "data" / "options_flow").mkdir(parents=True)
    prophet_dir = tmp_path / "site" / "prophet"
    prophet_dir.mkdir(parents=True)
    if prophet_payload is not None:
        (prophet_dir / "index.json").write_text(json.dumps(prophet_payload))

    monkeypatch.setattr(producer, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(producer, "CHAINS_DIR", chains_dir)
    monkeypatch.setattr(producer, "SUMMARY_GLOB", str(summary_dir / "summary_{sym}.parquet"))
    monkeypatch.setattr(producer, "GEX_JSON_GLOB", str(gex_dir / "{sym}.json"))
    monkeypatch.setattr(producer, "EARNINGS_PATH", tmp_path / "data" / "earnings" / "earnings.parquet")
    monkeypatch.setattr(producer, "PROPHET_INDEX_PATH", prophet_dir / "index.json")
    monkeypatch.setattr(producer, "SIGNING_GATE_PATH", tmp_path / "data" / "options_flow" / "signing_gate.json")
    # B2: default the canonical universe to exactly this fixture's symbols (100%
    # coverage) so a B1/B3/B4 test with no OWN opinion on coverage doesn't trip
    # INSUFFICIENT_COVERAGE against the real repo's ~375-name universe. Tests that
    # exercise B2 itself (test_b2_4) re-patch this afterward.
    monkeypatch.setattr(producer.options_universe, "gex_symbols", lambda: list(symbols))
    # F2a: default the fail-closed probe's OWN config read to include_baskets=False
    # so a test with no opinion on F2a never trips UNIVERSE_RESOLUTION_FAILED against
    # the REAL repo config.yml (include_baskets: true, ~25 real anchors vs this
    # fixture's handful of fake symbols — a false positive on every other test in
    # this fixture family). Tests that exercise F2a itself re-patch this afterward.
    monkeypatch.setattr(producer, "_gex_cfg", lambda: {"include_baskets": False})
    return chains_dir, summary_dir, gex_dir


def _fake_repo_sessions(n: int = 14):
    sessions = _real_sessions(n)
    return sessions, sessions[-2], sessions[-1]   # sessions, S, D


def _alpha_names(prefix: str, n: int) -> list[str]:
    """``n`` distinct symbol names using ONLY letters after ``prefix`` (up to 26*26).

    The fixture ticker-identity regex (``_STANDARD_TICKER_RE`` = ``[A-Za-z.]+`` for the
    OCC root) requires a letters-only symbol — a digit-suffixed name like ``COV00``
    fails to match at all, so EVERY row for that symbol gets silently excluded as
    "adjusted/nonstandard" by ``contract_identity_split``, zeroing the whole chain for
    that name with no error. Found the hard way building the B2 coverage tests below.
    """
    import string
    letters = string.ascii_uppercase
    return [f"{prefix}{letters[i // 26]}{letters[i % 26]}" for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# B1 — receipt closure / source_manifest.
# ─────────────────────────────────────────────────────────────────────────────


def test_b1_1_mutating_consumed_summary_changes_payload_and_receipt(tmp_path, monkeypatch):
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)
    p1 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    # mutate the summary spot series of ONE consumed symbol (changes its RV -> v2)
    summary_dir = tmp_path / "data" / "polygon_gex"
    fp = summary_dir / f"summary_{symbols[0]}.parquet"
    idx = pd.to_datetime(sessions)
    mutated = pd.DataFrame({"spot": [50.0 + 3.0 * i for i in range(len(sessions))]}, index=idx)
    mutated.to_parquet(fp)
    p2 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    assert p1["receipt_id"] != p2["receipt_id"]
    assert p1["source_manifest"]["gex_summary"]["root"] != p2["source_manifest"]["gex_summary"]["root"]
    assert p1["source_manifest"]["gex_summary"]["files"][str(fp.relative_to(tmp_path))] != \
        p2["source_manifest"]["gex_summary"]["files"][str(fp.relative_to(tmp_path))]


def test_b1_2_mutating_s_bound_gex_json_changes_context_and_receipt(tmp_path, monkeypatch):
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions, gex_json_asof=S)
    p1 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    gex_dir = tmp_path / "site" / "gex"
    fp = gex_dir / f"{symbols[0]}.json"
    fp.write_text(json.dumps(_gex_json_payload(S, dist_to_flip_pct=0.0)))  # long, shallow -> different verdict
    p2 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    assert p1["receipt_id"] != p2["receipt_id"]
    assert p1["source_manifest"]["gex_confirm"]["root"] != p2["source_manifest"]["gex_confirm"]["root"]

    def verdict_of(payload, sym):
        for c in payload["opportunities"] + payload["risk_warnings"]:
            if c["symbol"] == sym:
                return c["mechanics_context"]["gex_confirm_verdict"]
        exemplar = payload.get("no_signal_exemplar")
        if exemplar and exemplar["symbol"] == sym:
            return exemplar["mechanics_context"]["gex_confirm_verdict"]
        return "NOT_FOUND"

    v1, v2 = verdict_of(p1, symbols[0]), verdict_of(p2, symbols[0])
    assert v1 != "NOT_FOUND" and v2 != "NOT_FOUND"
    assert v1 != v2, f"gex verdict unchanged across a genuinely different S-bound payload: {v1!r}"


def test_b1_3_unconsumed_gex_payload_never_touches_the_receipt(tmp_path, monkeypatch):
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)
    # a gex json for a symbol OUTSIDE the universe/chain — never read by _load_gex_verdicts
    # (which only ever iterates present_names, the chain[S] symbol set)
    gex_dir = tmp_path / "site" / "gex"
    (gex_dir / "GHOST.json").write_text(json.dumps(_gex_json_payload(S)))
    p1 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    (gex_dir / "GHOST.json").write_text(json.dumps(_gex_json_payload(S, dist_to_flip_pct=99.0)))
    p2 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    assert p1["receipt_id"] == p2["receipt_id"]
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
    assert "GHOST" not in json.dumps(p1["source_manifest"])


def test_b1_4_identical_rerun_is_a_byte_level_no_op(tmp_path, monkeypatch):
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p1 = producer.build(now=now, ignore_staleness=True)
    out = tmp_path / "out.json"
    producer.write_json_atomic(out, p1)
    original_bytes, original_mtime = out.read_bytes(), out.stat().st_mtime_ns

    p2 = producer.build(now=datetime(2099, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert producer._semantic_unchanged(out, p2)
    assert out.read_bytes() == original_bytes and out.stat().st_mtime_ns == original_mtime


def test_b1_5_manifest_enumerates_every_consumed_file_closure(tmp_path, monkeypatch):
    """F7t rewrite (2026-08-18): a spy instruments file-OPEN level (``_load_chain``,
    never just the hasher) so the closure claim actually covers what the producer
    reads, not merely what it eventually hashes; a second spy on ``_sha256_file``
    keeps the pre-existing gex_summary/gex_confirm closure check. The test FAILS if
    a consumed path is left unbound anywhere in source_manifest — proven both by the
    set-closure assertions below AND by literally replaying the F1 blocker attack
    (mutating a HISTORICAL, non-S/D chain and requiring receipt_id to move)."""
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    chains_dir, summary_dir, gex_dir = _write_fake_repo(
        tmp_path, monkeypatch, symbols=symbols, sessions=sessions, gex_json_asof=S)

    opened_chains: list[Path] = []
    real_load_chain = producer._load_chain

    def spy_load_chain(session):
        opened_chains.append(producer.CHAINS_DIR / f"{session}.parquet")
        return real_load_chain(session)

    monkeypatch.setattr(producer, "_load_chain", spy_load_chain)

    hashed: list[Path] = []
    real_hasher = producer._sha256_file

    def spy_hash(path):
        hashed.append(path)
        return real_hasher(path)

    monkeypatch.setattr(producer, "_sha256_file", spy_hash)
    payload = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    # F1 closure: EVERY chain file the producer actually opened (S, D, and every
    # historical session <= S used for d1/d3/Q_oi/skew history) must be bound into
    # source_manifest.chains — this is the exact set the pre-fix attack exploited
    # (a historical session was opened/scored but never bound anywhere).
    opened_chain_relpaths = {str(p.relative_to(tmp_path)) for p in opened_chains}
    assert opened_chain_relpaths, "fixture never opened a chain file — test is vacuous"
    chains_manifest_files = set(payload["source_manifest"]["chains"]["files"].keys())
    unbound = opened_chain_relpaths - chains_manifest_files
    assert not unbound, f"chain file(s) opened but never bound into source_manifest.chains: {unbound}"

    expected_summary = {str((summary_dir / f"summary_{s}.parquet").relative_to(tmp_path)) for s in symbols}
    expected_gex = {str((gex_dir / f"{s}.json").relative_to(tmp_path)) for s in symbols}

    manifest_summary = set(payload["source_manifest"]["gex_summary"]["files"].keys())
    manifest_gex = set(payload["source_manifest"]["gex_confirm"]["files"].keys())
    assert manifest_summary == expected_summary
    assert manifest_gex == expected_gex

    hashed_summary = {str(p.relative_to(tmp_path)) for p in hashed if "summary_" in p.name}
    hashed_gex = {str(p.relative_to(tmp_path)) for p in hashed
                  if p.name.endswith(".json") and p.parent.name == "gex"}
    assert hashed_summary == expected_summary
    assert hashed_gex == expected_gex
    assert payload["source_manifest"]["gex_summary"]["member_count"] == len(expected_summary)
    assert payload["source_manifest"]["gex_confirm"]["member_count"] == len(expected_gex)

    # Attack-1 replay (F1 blocker, converted from test_attack_receipt.py): mutate a
    # HISTORICAL (< S, not D) chain — a session opened above but not S/D — and prove
    # the closure is real by requiring receipt_id to actually move.
    historical = sorted(s for s in sessions if s < S)[0]
    df = pd.read_parquet(chains_dir / f"{historical}.parquet")
    mask = df["underlying"].astype(str) == symbols[0]
    df.loc[mask, "volume"] = (df.loc[mask, "volume"] * 100.0).astype("float32")
    df.loc[mask, "oi"] = (df.loc[mask, "oi"] * 7.0).astype("float32")
    df.to_parquet(chains_dir / f"{historical}.parquet")
    payload2 = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert payload["receipt_id"] != payload2["receipt_id"], \
        "F1 BLOCKER: mutating a historical (non-S/D) chain moved the payload but not receipt_id"


# ─────────────────────────────────────────────────────────────────────────────
# B2 — two gates (SOURCE_COVERAGE_GATE 0.90 vs ELIGIBILITY_GATE 0.60).
# ─────────────────────────────────────────────────────────────────────────────


def test_b2_1_coverage_below_90_pct_insufficient_coverage_even_with_excellent_eligibility():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]
    names = {sym: _typical_spec(salt=i) for i, sym in enumerate(_alpha_names("COV", 89))}   # all clean/eligible
    panel = _panel(names, sessions)
    universe = list(names.keys()) + _alpha_names("MISS", 11)   # 89/100 = 89%
    payload = _build(panel, S=S, D=D, universe=universe)
    assert payload["board_state"] == "INSUFFICIENT_COVERAGE"
    assert payload["eligibility"]["universe_count"] == 100
    assert payload["eligibility"]["source_coverage_pct"] == pytest.approx(0.89, abs=1e-4)
    assert payload["opportunities"] == []


def test_b2_2_coverage_at_90_pct_but_eligibility_59_pct_eligibility_collapse():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]

    def thin(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0, n_contracts=False)  # ineligible (<20 contracts)

    def full(s, i):
        return dict(spot=100.0, base_iv=0.30, oi_base=100.0)

    names = {sym: thin for sym in _alpha_names("THN", 41)}
    names.update({sym: full for sym in _alpha_names("FUL", 59)})   # 59/100 eligible = 59% < 60%
    panel = _panel(names, sessions)
    # coverage denominator must itself clear 90% independent of eligibility -> present==universe (100%)
    universe = list(names.keys())
    payload = _build(panel, S=S, D=D, universe=universe)
    assert payload["eligibility"]["universe_count"] == 100
    assert payload["eligibility"]["source_coverage_pct"] == pytest.approx(1.0, abs=1e-4)
    assert payload["eligibility"]["present"] == 100
    assert payload["eligibility"]["eligible"] == 59
    assert payload["board_state"] == "DEGRADED"
    assert payload["board_reason"] == "ELIGIBILITY_COLLAPSE"
    assert payload["opportunities"] == []


def test_b2_3_both_gates_pass_scoring_proceeds():
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]
    names = {sym: _typical_spec(salt=i) for i, sym in enumerate(_alpha_names("OKX", 95))}
    panel = _panel(names, sessions)
    universe = list(names.keys()) + _alpha_names("MISS", 2)   # 95/97 ~= 97.9%
    payload = _build(panel, S=S, D=D, universe=universe)
    assert payload["eligibility"]["source_coverage_pct"] >= CONFIG["SOURCE_COVERAGE_GATE"]
    assert payload["board_state"] in ("OK", "NO_SIGNAL")
    assert payload["board_reason"] is None


def test_b2_4_universe_membership_change_moves_the_denominator_no_historical_max(tmp_path, monkeypatch):
    """Producer-level: patching engine.options_universe.gex_symbols (as imported into
    the producer module) changes the coverage denominator directly — never a chain-store
    historical-max fallback."""
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)

    monkeypatch.setattr(producer.options_universe, "gex_symbols", lambda: list(symbols))
    p_full = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert p_full["eligibility"]["universe_count"] == 6
    assert p_full["eligibility"]["source_coverage_pct"] == pytest.approx(1.0, abs=1e-4)
    assert p_full["board_state"] != "INSUFFICIENT_COVERAGE"

    bigger_universe = list(symbols) + _alpha_names("OTHER", 10)
    monkeypatch.setattr(producer.options_universe, "gex_symbols", lambda: bigger_universe)
    p_shrunk_coverage = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert p_shrunk_coverage["eligibility"]["universe_count"] == 16
    assert p_shrunk_coverage["eligibility"]["source_coverage_pct"] == pytest.approx(6 / 16, abs=1e-4)
    assert p_shrunk_coverage["board_state"] == "INSUFFICIENT_COVERAGE"
    # F1 (2026-08-18) supersedes the old "universe never participates in receipt_id"
    # premise: a `universe_resolution` input_receipts entry now binds
    # sha256(canonical_json(sorted(universe_list))) + count, same as every other §2
    # source — a different resolved universe MUST move receipt_id.
    assert p_full["receipt_id"] != p_shrunk_coverage["receipt_id"]
    full_receipt = next(r for r in p_full["input_receipts"] if r["logical_source"] == "universe_resolution")
    shrunk_receipt = next(r for r in p_shrunk_coverage["input_receipts"] if r["logical_source"] == "universe_resolution")
    assert full_receipt["count"] == 6 and shrunk_receipt["count"] == 16
    assert full_receipt["sha256"] != shrunk_receipt["sha256"]


def test_b2_5_universe_resolution_failed_fails_closed_on_swallowed_basket_error(tmp_path, monkeypatch):
    """F2a (2026-08-18, converted from ATTACK 3's real locus — the reviewer's
    engine-level shrunk-universe scenario stays lawful at the engine level per the
    ruling's own text, since an EXPLICIT universe there is a legitimate engine
    input; the fix is entirely in the PRODUCER's resolution of that universe).
    ``engine/options_universe.py::baskets_universe()`` swallows any read failure and
    returns ``[]`` (by design, never crashes the build) — but a producer that then
    quietly scores against just the anchor list while still claiming
    ``include_baskets`` succeeded was failing OPEN. Simulated here by making
    ``gex_symbols()`` resolve to exactly the (fixture-sized) anchor list while
    ``_gex_cfg()`` reports ``include_baskets: true`` — the SAME observable signature
    a real swallowed ``baskets_universe()`` exception produces."""
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)

    monkeypatch.setattr(producer, "_gex_cfg", lambda: {"include_baskets": True, "symbols": list(symbols)})
    monkeypatch.setattr(producer.options_universe, "gex_symbols", lambda: list(symbols))
    payload = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert payload["board_state"] == "DEGRADED"
    assert payload["board_reason"] == "UNIVERSE_RESOLUTION_FAILED"
    assert payload["opportunities"] == [] and payload["risk_warnings"] == [] and payload["event_board"] == []
    assert payload["source_manifest"]["chains"]["member_count"] > 0   # chains already loaded, still bound


def test_b2_6_universe_resolution_succeeds_when_baskets_actually_widen_it(tmp_path, monkeypatch):
    """Negative control for F2a: the SAME include_baskets=true config does NOT trip
    the fail-closed path when the resolved universe genuinely grew beyond the
    anchors (a healthy basket resolution) — proves the check is the OBSERVABLE
    signature (universe <= anchors), never a blanket "include_baskets=true always
    degrades" regression."""
    sessions, S, D = _fake_repo_sessions()
    symbols = [f"SYM{chr(65+i)}" for i in range(6)]
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions)

    anchors = symbols[:2]
    monkeypatch.setattr(producer, "_gex_cfg", lambda: {"include_baskets": True, "symbols": anchors})
    monkeypatch.setattr(producer.options_universe, "gex_symbols", lambda: list(symbols))  # 6 > 2 anchors
    payload = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)
    assert payload["board_reason"] != "UNIVERSE_RESOLUTION_FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# B3 — evidence-derived freshness (fresh_until_for). Direct unit tests assert the
# exact ruling formulas against real NYSE-session arithmetic; the end-to-end tests
# further down prove they are actually WIRED into a real scored card.
# ─────────────────────────────────────────────────────────────────────────────


def test_b3_1_long_baseline_vs_gex_caution_one_session_life():
    S = "2026-03-16"
    baseline = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward)
    assert baseline == _session_n_forward(S, 3)   # Q_oi(3) + Q_skew(3) + D_salience(3)

    with_gex = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward,
                                      gex_active=True)
    assert with_gex == _session_n_forward(S, 1)   # P/GEX mechanics life 1 wins the min
    assert with_gex < baseline


def test_b3_2_long_crowd_cut_same_day_c1_vs_c3():
    S = "2026-03-16"
    same_day = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward,
                                      crowd_fired_legs=["c1"])
    assert same_day == S   # C_0DTE life 0 -> current-session expiry

    via_c3 = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward,
                                    crowd_fired_legs=["c3"])
    assert via_c3 == _session_n_forward(S, 3)   # min(D=3, V=5) = 3 -> ties the LONG baseline

    via_c2 = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward,
                                    crowd_fired_legs=["c2"])
    assert via_c2 == _session_n_forward(S, 3)   # min(D=3,Q=3,Q=3, c2-life=5) = 3, c2 never widens it


def test_b3_3_event_driven_volatility_uses_event_close():
    S = "2026-03-16"
    event_date = _session_n_forward(S, 10)
    fu = brief.fresh_until_for(direction="VOLATILITY", S=S, session_n_forward_fn=_session_n_forward,
                                f_e_active=True, event_date=event_date)
    assert fu == event_date

    # the confidence d3 persist-bonus is ALSO salience evidence (life 3) -> the earlier
    # of the two candidates wins
    fu_with_bonus = brief.fresh_until_for(direction="VOLATILITY", S=S, session_n_forward_fn=_session_n_forward,
                                           f_e_active=True, event_date=event_date, d3_bonus_applied=True)
    assert fu_with_bonus == _session_n_forward(S, 3)
    assert fu_with_bonus < event_date


def test_b3_4_v_driven_non_event_volatility_life_five():
    S = "2026-03-16"
    fu = brief.fresh_until_for(direction="VOLATILITY", S=S, session_n_forward_fn=_session_n_forward,
                                f_e_active=False)
    assert fu == _session_n_forward(S, 5)


def test_b3_5_risk_only_same_day_vs_non_same_day_crowd_legs():
    S = "2026-03-16"
    same_day = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                      crowd_fired_legs=["c1"])
    assert same_day == S

    via_c2 = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                    crowd_fired_legs=["c2"])
    assert via_c2 == _session_n_forward(S, 5)

    via_c3 = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                    crowd_fired_legs=["c3"])
    assert via_c3 == _session_n_forward(S, 3)

    # every fired leg contributes -> the MIN across them (a same-day c1 anywhere in the
    # fired set forces the whole card to current-session expiry)
    all_three = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                       crowd_fired_legs=["c1", "c2", "c3"])
    assert all_three == S


def test_b3_6_neutral_and_display_only_background_never_shortens():
    S = "2026-03-16"
    assert brief.fresh_until_for(direction="NEUTRAL", S=S, session_n_forward_fn=_session_n_forward) == S
    # a Prophet echo / absent-family background carries no `lives` contribution at all —
    # there is no parameter for it in fresh_until_for's signature (structural, not just
    # untested): confirms "display-only background never shortens" by construction.
    import inspect
    params = set(inspect.signature(brief.fresh_until_for).parameters)
    assert "prophet" not in " ".join(params).lower()
    assert not (params & {"absent_families", "prophet_state", "prophet_chip"})


def test_b3_7_stale_contributing_evidence_end_to_end_multi_family_degradation():
    """F7t rewrite (2026-08-18): the ORIGINAL fixture never actually landed HOT on
    its engineered LONG/c1 path (every session's ``_symbol_rows`` spreads ``volume``
    UNIFORMLY across all 4 expiry bands, so same-day share never differentiated
    cross-sectionally) — it silently exercised only the vacuous ``>= S`` fallback
    every run, proving nothing. This version hand-builds HOT's chain rows with a
    massively inflated same-day (``zero``-band) volume relative to 9 flat peers
    (deterministic, same ``_wiggle`` seeding as the rest of this file) so c1
    genuinely fires cross-sectionally, and binds a ``caution`` GEX verdict — an
    EXACT ``fresh_until`` is asserted, never the old ``>= S`` escape hatch, and the
    fixture's actual outcome (RISK_ONLY route, c1 fired) is asserted explicitly
    rather than assumed, so a fixture regression fails loudly instead of silently
    re-opening the vacuous branch."""
    sessions = _real_sessions(30)
    S, D = sessions[-2], sessions[-1]
    peer_names = [f"PR{chr(65+j)}" for j in range(9)]

    def _hot_rows(s: str, i: int) -> list[dict]:
        rows = _symbol_rows("HOT", s, spot=100.0, base_iv=0.30 * _wiggle(i, salt=900),
                             oi_base=100.0, oi_call_bump=(80.0 if s == D else 0.0),
                             volume=10.0, anchor=sessions[0])
        zero_vol = 5000.0 if s == S else 20.0   # same-day tape spikes ONLY on S itself
        ss = pd.Timestamp(s)
        for r in rows:
            if r["expiry"] == ss:
                r["volume"] = zero_vol
        return rows

    panel_sessions: dict[str, pd.DataFrame] = {}
    for i, s in enumerate(sessions):
        rows = _hot_rows(s, i)
        for j, sym in enumerate(peer_names):
            rows.extend(_symbol_rows(sym, s, spot=100.0, base_iv=0.30 * _wiggle(i, salt=910 + j),
                                      oi_base=100.0, volume=10.0, anchor=sessions[0]))
        panel_sessions[s] = _mk_chain(rows, session=s)

    payload = _build(panel_sessions, S=S, D=D, universe=["HOT"] + peer_names,
                      gex_verdict={"HOT": "caution"})
    hot = None
    for c in payload["opportunities"] + payload["risk_warnings"] + payload["directional_watch"]:
        if c["symbol"] == "HOT":
            hot = c
    if hot is None and payload["no_signal_exemplar"] and payload["no_signal_exemplar"]["symbol"] == "HOT":
        hot = payload["no_signal_exemplar"]
    assert hot is not None, "HOT never scored — fixture failed to produce a card to assert on"
    assert hot["direction"] == "RISK_ONLY", f"fixture landed on {hot['direction']!r}, not the engineered RISK_ONLY/c1 path"
    assert hot["crowding"] is not None and "c1" in hot["crowding"]["fired"], \
        f"fixture never fired c1: {hot['crowding']!r}"
    assert hot["fresh_until"] == S   # same-day (life 0) leg present -> forced to current session, EXACT


def test_b3_8_plain_long_baseline_through_the_real_pipeline():
    """F7t (2026-08-18): the original ``for``-loop body never executed at all if no
    card matched the predicate, silently passing vacuously — ``_std_panel()``'s AAA/BBB
    always resolve VOLATILITY, never LONG/SHORT, so this test ALWAYS passed
    vacuously. Replaced with a hand-built fixture (:func:`_engineered_long_panel`)
    that deliberately flattens AAA's downside skew at S alone (put-side IV dropped
    only in the S session's "front" 7-60 DTE band, everywhere else held at a normal
    smile) while bumping call ΔOI at D — the same OI-bump idiom every other fixture
    in this file uses — so AAA genuinely qualifies LONG with no crowding/GEX
    contribution, and asserts the exact baseline fresh_until (S+3 sessions)."""
    sessions, S, D, panel_sessions = _engineered_long_panel()
    payload = _build(panel_sessions, S=S, D=D, universe=["AAA", "BBB"])
    aaa = next((c for c in payload["opportunities"] + payload["directional_watch"] if c["symbol"] == "AAA"), None)
    assert aaa is not None, "fixture produced no AAA card to assert on"
    assert aaa["direction"] in ("LONG", "SHORT"), f"fixture landed on {aaa['direction']!r}, not directional"
    assert aaa["crowding"] is None
    assert aaa["mechanics_context"]["gex_confirm_verdict"] is None
    assert aaa["fresh_until"] == _session_n_forward(S, 3)


# ─────────────────────────────────────────────────────────────────────────────
# F3 — event contamination joins fresh_until's min-set for LONG/SHORT (a); the
# VOLATILITY branch keeps V(5) whenever F_V genuinely contributed, not merely
# whenever F_E is absent (b). Converted from the reviewer's test_attack_fresh.py.
# ─────────────────────────────────────────────────────────────────────────────


def _engineered_long_panel(*, n_sessions: int = 20):
    """AAA deterministically qualifies LONG (Q_oi/Q_skew/D_salience all clear
    threshold) with no crowding/GEX contribution; BBB is a plain VOLATILITY peer.
    Shared by test_b3_8 and the F3 wiring tests below — same construction, single
    source of truth for "how this suite engineers a real qualified LONG card"."""
    sessions = _real_sessions(n_sessions)
    S, D = sessions[-2], sessions[-1]
    put_lo, put_hi = CONFIG["SKEW_PUT_DELTA"]
    call_lo, call_hi = CONFIG["SKEW_CALL_DELTA"]
    front_expiry = pd.Timestamp(sessions[0]) + pd.Timedelta(days=35)

    def _aaa_rows(s: str) -> list[dict]:
        rows = _symbol_rows("AAA", s, spot=100.0, base_iv=0.30, oi_base=100.0,
                             oi_call_bump=(80.0 if s == D else 0.0), volume=50.0, anchor=sessions[0])
        for r in rows:
            if r["expiry"] != front_expiry:
                continue
            d = r["delta"]
            if not r["is_call"] and put_lo <= d <= put_hi:
                r["iv"] = 0.15 if s == S else 0.45   # downside skew flattens ONLY at S
            elif r["is_call"] and call_lo <= d <= call_hi:
                r["iv"] = 0.30
        return rows

    panel_sessions: dict[str, pd.DataFrame] = {}
    for s in sessions:
        rows = _aaa_rows(s) + _symbol_rows("BBB", s, spot=100.0, base_iv=0.30, oi_base=100.0,
                                            volume=50.0, anchor=sessions[0])
        panel_sessions[s] = _mk_chain(rows, session=s)
    return sessions, S, D, panel_sessions


def test_f3a_attack_fresh_2b_long_ignores_event_for_directional_defeated():
    """ATTACK 2b (test_attack_fresh_until_for_ignores_event_for_directional)
    defeated: the LONG/SHORT branch of ``fresh_until_for`` now consumes
    ``f_e_active``/``event_date`` — when the caller marks the event contamination
    as having entered M_ad, the event close must join the min-set, never be
    structurally dropped."""
    S = "2026-03-16"
    ev = _session_n_forward(S, 1)
    fu = brief.fresh_until_for(direction="LONG", S=S, session_n_forward_fn=_session_n_forward,
                                gex_active=False, crowd_fired_legs=[],
                                f_e_active=True, event_date=ev, d3_bonus_applied=True)
    assert fu <= ev, "LONG branch structurally drops the event contribution"
    assert fu == ev   # min(S+3, ev=S+1) == ev exactly


def test_f3a_attack_fresh_1_event_imminent_wiring_end_to_end(monkeypatch):
    """ATTACK 1 (test_attack_event_imminent_long_freshness) defeated, converted to a
    call-site WIRING proof rather than an exposed-board assertion: a genuinely
    qualified LONG's own contamination-cut R (event_mult=0.6x, contract-frozen)
    structurally can fall below R_MIN — asserting through opportunities/
    directional_watch would be circular (the SAME fix that must widen fresh_until
    also shrinks R below the board cut for a card this close to the floor). A spy
    on ``brief.fresh_until_for`` instead proves the real pipeline call for AAA (the
    deterministic engineered LONG fixture) passes ``f_e_active=True,
    event_date=<the event>`` ONLY when the event actually entered M_ad
    (event_imminent), and ``f_e_active=False`` with no event."""
    sessions, S, D, panel_sessions = _engineered_long_panel()
    ev = _session_n_forward(S, 1)   # 1 session out -> within EVENT_CONTAM_SESSIONS(2)

    calls: list[dict] = []
    real_fresh_until_for = brief.fresh_until_for

    def spy(**kwargs):
        calls.append(kwargs)
        return real_fresh_until_for(**kwargs)

    monkeypatch.setattr(brief, "fresh_until_for", spy)
    try:
        base = _build(panel_sessions, S=S, D=D, universe=["AAA", "BBB"])
        calls.clear()
        with_ev = _build(panel_sessions, S=S, D=D, universe=["AAA", "BBB"],
                          event_date={"AAA": ev, "BBB": None}, events_loaded=True)
    finally:
        monkeypatch.setattr(brief, "fresh_until_for", real_fresh_until_for)

    long_calls_with_ev = [c for c in calls if c.get("direction") == "LONG"]
    assert len(long_calls_with_ev) == 1, f"expected exactly one LONG call, got {long_calls_with_ev}"
    assert long_calls_with_ev[0]["f_e_active"] is True
    assert long_calls_with_ev[0]["event_date"] == ev

    aaa_base = next(c for c in base["opportunities"] + base["directional_watch"] if c["symbol"] == "AAA")
    aaa_with_ev_card = next((c for c in with_ev["opportunities"] + with_ev["directional_watch"]
                              if c["symbol"] == "AAA"), None)
    # the event contamination structurally lowers R (event_mult=0.6, contract-frozen)
    # -- proving it "entered M_ad" the same way the original attack script did,
    # WITHOUT relying on the card surviving R_MIN afterward.
    if aaa_with_ev_card is not None:
        assert aaa_with_ev_card["research_priority_score"] < aaa_base["research_priority_score"]
        assert not (aaa_with_ev_card["fresh_until"] > ev), "FRESHNESS OVERSTATED past the contaminating event"
    else:
        assert aaa_base["research_priority_score"] >= CONFIG["R_MIN"], \
            "baseline R was never above R_MIN -- the contamination-drop premise doesn't hold"


def test_f3b_attack_fresh_2c_volatility_v_life_never_exclusively_event():
    """ATTACK 2c (test_attack_volatility_fv_routed_with_far_event) defeated,
    adapted for the fixed function's real signature: the VOLATILITY branch appends
    V(5) whenever the V family genuinely contributed (``f_v_active=True``, F3b),
    never exclusively because an event is absent — a GIS-class row (both F_E and
    F_V contributing) becomes ``min(event_close, V(5), d3-bonus-life)``, so a FAR
    event (outside V's own 5-session life) must not silently drop V's tighter
    life."""
    S = "2026-03-16"
    far = "2026-04-28"   # ~30 sessions out, inside the 45d event window
    fu = brief.fresh_until_for(direction="VOLATILITY", S=S, session_n_forward_fn=_session_n_forward,
                                f_e_active=True, event_date=far, f_v_active=True, d3_bonus_applied=False)
    assert fu <= _session_n_forward(S, 5), "V-family life dropped when a far event also exists"
    assert fu == _session_n_forward(S, 5)   # min(V(5), far) == V(5) since far >> S+5


def test_f3b_pre_existing_event_driven_volatility_unaffected_when_f_v_inactive():
    """Negative control for F3b: a PURELY event-driven VOLATILITY card (F_E present,
    F_V never contributed -- ``f_v_active`` defaults False) still gets event-close
    alone, exactly the pre-existing b3_3 behavior -- the F3b widening is additive,
    never a regression on the case it doesn't apply to."""
    S = "2026-03-16"
    event_date = _session_n_forward(S, 10)
    fu = brief.fresh_until_for(direction="VOLATILITY", S=S, session_n_forward_fn=_session_n_forward,
                                f_e_active=True, event_date=event_date)
    assert fu == event_date


# ─────────────────────────────────────────────────────────────────────────────
# F4a — c1's cross-section coverage predicate (C1_XS_MIN_PRESENT_SHARE). Converted
# from the reviewer's attack_crowd.py, which called session_metrics_and_exclusions
# / percentile_xs directly against the real store; this synthetic version
# reproduces the same shape deterministically.
# ─────────────────────────────────────────────────────────────────────────────


def test_f4a_thin_session_c1_predicate_attack_crowd_converted():
    """ATTACK 4 (attack_crowd.py) converted: a THIN session — a finite-sd_share
    population well below C1_XS_MIN_PRESENT_SHARE (50%) of present names, even
    though it clears the OLD absolute MIN_HISTORY(10) floor comfortably (12 >= 10)
    — must resolve c1 = None universe-wide, never let a couple of names
    self-certify as crowded against a near-empty cross-section (the same pre-fix
    shape the crowding-percentile ruling closed for mass-ties, here reproduced via
    genuine sparse coverage instead)."""
    session = "2026-03-02"
    names = _alpha_names("THN", 30)
    finite_names = set(names[:12])   # 12/30 = 40% < C1_XS_MIN_PRESENT_SHARE (50%)
    hot = names[0]

    rows: list[dict] = []
    for sym in names:
        sym_rows = _symbol_rows(sym, session, spot=100.0, base_iv=0.30, oi_base=100.0, volume=50.0)
        ss = pd.Timestamp(session)
        for r in sym_rows:
            if r["expiry"] != ss:
                continue
            if sym not in finite_names:
                r["volume"] = 0.0            # no same-day tape -> sd_share = None
            elif sym == hot:
                r["volume"] = 5000.0         # extreme same-day concentration
        rows.extend(sym_rows)
    df = _mk_chain(rows, session=session)

    m, _ = brief.session_metrics_and_exclusions(df)
    xs_sd = {n: m[n]["sd_share"] for n in m}
    finite_count = sum(1 for v in xs_sd.values() if v is not None)
    assert finite_count == 12, f"fixture didn't produce the expected 12 finite members: {finite_count}"

    # OLD behaviour (plain percentile_xs against the absolute MIN_HISTORY(10) floor
    # only): 12 >= 10 clears the floor, so `hot` self-certifies as maximally
    # crowded against just its 11 finite peers — the exact pre-F4a false positive.
    old_c1 = brief.percentile_xs(xs_sd, hot)
    assert old_c1 is not None and old_c1 >= CONFIG["C1_TH"], \
        "fixture doesn't reproduce the pre-fix false-positive shape"

    # NEW behaviour: the coverage predicate itself.
    present_n = len(names)
    c1_xs_present = finite_count >= CONFIG["C1_XS_MIN_PRESENT_SHARE"] * present_n
    assert not c1_xs_present, "fixture's coverage share unexpectedly clears the F4a predicate"


def test_f4a_thin_session_c1_none_through_the_real_pipeline():
    """Same THIN-coverage shape as above, wired through the REAL build_intel_brief
    pipeline (10+ history sessions so eligibility clears) — `hot`'s own crowding
    must come back None despite the same extreme same-day concentration that would
    have fired c1 pre-fix."""
    sessions = _real_sessions(14)
    S, D = sessions[-2], sessions[-1]
    names = _alpha_names("THN", 30)
    finite_names = set(names[:12])
    hot = names[0]

    def _rows_for_session(s: str, i: int) -> list[dict]:
        rows: list[dict] = []
        for sym in names:
            sym_rows = _symbol_rows(sym, s, spot=100.0, base_iv=0.30 * _wiggle(i, salt=abs(hash(sym)) % 1000),
                                     oi_base=100.0, volume=50.0, anchor=sessions[0])
            ss = pd.Timestamp(s)
            for r in sym_rows:
                if r["expiry"] != ss:
                    continue
                if sym not in finite_names:
                    r["volume"] = 0.0
                elif sym == hot and s == S:
                    r["volume"] = 5000.0
            rows.extend(sym_rows)
        return rows

    panel_sessions = {s: _mk_chain(_rows_for_session(s, i), session=s) for i, s in enumerate(sessions)}
    payload = _build(panel_sessions, S=S, D=D, universe=names)

    hot_card = None
    for c in payload["opportunities"] + payload["risk_warnings"] + payload["directional_watch"]:
        if c["symbol"] == hot:
            hot_card = c
    if hot_card is None and payload["no_signal_exemplar"] and payload["no_signal_exemplar"]["symbol"] == hot:
        hot_card = payload["no_signal_exemplar"]
    assert hot_card is not None, "fixture never scored `hot` at all"
    assert hot_card["crowding"] is None, \
        f"c1 fired on a thin (12/30) cross-section: {hot_card['crowding']!r}"


# ─────────────────────────────────────────────────────────────────────────────
# B4 — canonical Prophet context (two domains: plans[] + intake.receipts.groups).
# ─────────────────────────────────────────────────────────────────────────────


def _real_shaped_prophet_index(*, asof: str, plans: list[dict], groups: list[dict]) -> dict:
    """A prophet.index/v1 fixture carrying the same top-level shape the real artifact
    does (``site/prophet/index.json``) for the two fields B4 reads: ``plans[]`` and
    ``intake.receipts.groups`` (copies the real structure's group-entry shape —
    ``{reason, en, zh, near, n, names:[{ticker,name,score,why}]}``)."""
    return {"schema": "prophet.index/v1", "asof": asof, "plans": plans,
            "intake": {"receipts": {"groups": groups}}}


def _plan(asset, *, entry_status=None, lifecycle_state="entered", closed=False):
    return {"asset": asset, "entry_status": entry_status, "lifecycle_state": lifecycle_state, "closed": closed}


def _group(reason, tickers):
    return {"reason": reason, "en": reason, "zh": reason, "near": True, "n": len(tickers),
            "names": [{"ticker": t, "name": t, "score": 50.0, "why": [reason]} for t in tickers]}


def test_b4_1_engine_precedence_extended_beats_not_ready_biib_class_collision():
    # plans[] says bounce_wait (-> NOT_READY); receipts.groups says ran_too_far
    # (-> EXTENDED) for the SAME symbol — the real BIIB collision (2026-08-18 artifact:
    # entry_status="bounce_wait" AND groups reason="ran_too_far"). EXTENDED must win.
    plan_state = brief.prophet_plan_state("bounce_wait", "entered", False, has_plan=True)
    group_state = brief.prophet_group_state("ran_too_far")
    assert plan_state == "NOT_READY"
    assert group_state == "EXTENDED"
    assert brief.prophet_state_combined(plan_state, group_state) == "EXTENDED"


def test_f13_attack_group_bucket_order_beats_ruled_precedence(tmp_path, monkeypatch):
    """ATTACK 5 (test_attack_group_bucket_order_beats_ruled_precedence) defeated:
    the SAME ticker in TWO intake.receipts.groups buckets in one file must resolve
    by the ruled precedence (EXTENDED > ALREADY_OPEN > NOT_READY > READY > OTHER),
    never by file/array order. ``not_ready`` appears BEFORE the ruled-higher
    ``ran_too_far`` in this payload — a plain keep-first (`setdefault`) would keep
    NOT_READY; the precedence-aware keep must overwrite it to EXTENDED."""
    payload = {
        "schema": "prophet.index/v1", "asof": "2026-08-17", "plans": [],
        "intake": {"receipts": {"groups": [
            _group("not_ready", ["BIIB"]),      # earlier in file order -> NOT_READY
            _group("ran_too_far", ["BIIB"]),    # ruled EXTENDED, must win
        ]}},
    }
    fp = tmp_path / "index.json"
    fp.write_text(json.dumps(payload))
    monkeypatch.setattr(producer, "PROPHET_INDEX_PATH", fp)
    es, ls, cl, gr, asof = producer._load_prophet()
    assert gr.get("BIIB") == "ran_too_far", f"file order beat ruled precedence: kept {gr.get('BIIB')!r}"
    state = brief.prophet_state_combined(None, brief.prophet_group_state(gr.get("BIIB")))
    assert state == "EXTENDED", "a ran_too_far name renders as NOT_READY ('Entry not ready yet')"


def test_f13_precedence_holds_regardless_of_which_bucket_is_declared_first(tmp_path, monkeypatch):
    """Negative control: reversing the array order (ran_too_far first, not_ready
    second) must land on the SAME EXTENDED result — proving the keep is genuinely
    precedence-driven, not merely "second write always wins"."""
    payload = {
        "schema": "prophet.index/v1", "asof": "2026-08-17", "plans": [],
        "intake": {"receipts": {"groups": [
            _group("ran_too_far", ["BIIB"]),
            _group("not_ready", ["BIIB"]),
        ]}},
    }
    fp = tmp_path / "index.json"
    fp.write_text(json.dumps(payload))
    monkeypatch.setattr(producer, "PROPHET_INDEX_PATH", fp)
    es, ls, cl, gr, asof = producer._load_prophet()
    assert gr.get("BIIB") == "ran_too_far"


def test_b4_2_wait_pullback_and_bounce_wait_map_not_ready():
    assert brief.prophet_group_state("not_ready") == "NOT_READY"
    assert brief.prophet_group_state("wait_pullback") == "NOT_READY"
    assert brief.prophet_group_state("bounce_wait") == "NOT_READY"
    assert brief.prophet_plan_state("bounce_wait", None, False, has_plan=True) == "NOT_READY"


def test_b4_3_already_open_group_maps_already_open():
    assert brief.prophet_group_state("already_open") == "ALREADY_OPEN"
    assert brief.prophet_state_combined(None, "ALREADY_OPEN") == "ALREADY_OPEN"


def test_b4_4_other_lawful_buckets_map_other_never_blank():
    for reason in ("stood_down", "conviction_low", "pointing_down", "plan_not_built"):
        assert brief.prophet_group_state(reason) == "OTHER"
    assert brief.prophet_state_combined(None, None) == "UNAVAILABLE"


def test_b4_5_precedence_order_exhaustive():
    order = ["EXTENDED", "ALREADY_OPEN", "NOT_READY", "READY", "OTHER"]
    for i, high in enumerate(order):
        for low in order[i + 1:]:
            assert brief.prophet_state_combined(high, low) == high
            assert brief.prophet_state_combined(low, high) == high


def test_b4_6_open_vs_closed_plan_domain_conditions():
    assert brief.prophet_plan_state("hold", "entered", False, has_plan=True) == "ALREADY_OPEN"
    assert brief.prophet_plan_state("hold", "entered", True, has_plan=True) == "OTHER"
    assert brief.prophet_plan_state(None, "entered", False, has_plan=True) == "ALREADY_OPEN"
    assert brief.prophet_plan_state(None, "entered", True, has_plan=True) == "OTHER"
    assert brief.prophet_plan_state(None, "ready", False, has_plan=True) == "OTHER"
    assert brief.prophet_plan_state(None, None, False, has_plan=False) is None
    # buy_now/extended resolve unconditionally (the contract's open-condition is stated
    # only for hold/partial and the None-status case)
    assert brief.prophet_plan_state("buy_now", "resolved", True, has_plan=True) == "READY"
    assert brief.prophet_plan_state("extended", "resolved", True, has_plan=True) == "EXTENDED"


def test_b4_7_producer_end_to_end_real_shaped_fixture_biib_class(tmp_path, monkeypatch):
    sessions, S, D = _fake_repo_sessions()
    # BIIB is a real ticker (no digits, matches the OCC-root regex); OPEN/WAIT are
    # letters-only stand-ins (a digit-suffixed test symbol like "OPEN1" silently zeroes
    # its whole chain through contract_identity_split — see _alpha_names' docstring).
    symbols = ["BIIB", "OPEN", "WAIT"]
    prophet = _real_shaped_prophet_index(
        asof=S,
        plans=[
            _plan("BIIB", entry_status="bounce_wait", lifecycle_state="entered", closed=False),
            _plan("OPEN", entry_status="hold", lifecycle_state="entered", closed=False),
        ],
        groups=[
            _group("ran_too_far", ["BIIB"]),
            _group("not_ready", ["WAIT"]),
        ],
    )
    _write_fake_repo(tmp_path, monkeypatch, symbols=symbols, sessions=sessions, prophet_payload=prophet)
    payload = producer.build(now=datetime(2026, 1, 1, tzinfo=timezone.utc), ignore_staleness=True)

    def prophet_of(sym):
        for c in payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]:
            if c["symbol"] == sym:
                return c["prophet_state"]
        exemplar = payload.get("no_signal_exemplar")
        if exemplar and exemplar["symbol"] == sym:
            return exemplar["prophet_state"]
        return "NOT_FOUND"

    assert prophet_of("BIIB") == "EXTENDED"      # collision: plans=NOT_READY, groups=EXTENDED -> EXTENDED wins
    assert prophet_of("OPEN") == "ALREADY_OPEN"
    assert prophet_of("WAIT") == "NOT_READY"
    assert payload["opportunities"] or payload["risk_warnings"] or payload["event_board"] \
        or payload["no_signal_exemplar"], "fixture produced no cards at all — assertions above are vacuous"


def test_b4_8_prophet_context_never_moves_score_rank_or_confidence():
    panel, S, D = _std_panel()
    p_no_prophet = _build(panel, S=S, D=D, prophet_entry_status={}, prophet_group_reason={},
                           prophet_lifecycle_state={}, prophet_plan_closed={}, prophet_asof=None)
    p_with_prophet = _build(panel, S=S, D=D,
                             prophet_entry_status={"AAA": "hold"},
                             prophet_lifecycle_state={"AAA": "entered"},
                             prophet_plan_closed={"AAA": False},
                             prophet_group_reason={"AAA": "ran_too_far", "BBB": "not_ready"},
                             prophet_asof="2026-01-01")

    def by_symbol(payload):
        out = {}
        for c in payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]:
            out[c["symbol"]] = (c["research_priority_score"], c["evidence_strength"], c["evidence_confidence"])
        return out

    assert by_symbol(p_no_prophet) == by_symbol(p_with_prophet)

    def prophet_state_of(payload, sym):
        for c in payload["opportunities"] + payload["event_board"] + payload["risk_warnings"]:
            if c["symbol"] == sym:
                return c["prophet_state"]
        return None

    # and the collision DID actually change AAA's displayed prophet_state (else the
    # equality above would be a vacuous no-op — proving "unchanged" on a field that
    # never changed to begin with)
    assert prophet_state_of(p_with_prophet, "AAA") == "EXTENDED"   # hold(ALREADY_OPEN) vs ran_too_far(EXTENDED)
    assert prophet_state_of(p_no_prophet, "AAA") == "UNAVAILABLE"


def test_module_docstrings_cite_the_contract():
    engine_doc = (REPO_ROOT / "engine" / "options_intel_brief.py").read_text()[:2000]
    producer_doc = (REPO_ROOT / "scripts" / "build_options_intel_brief.py").read_text()[:2000]
    assert "contracts/options/OPTIONS_INTEL_BRIEF_V1.md" in engine_doc
    assert "contracts/options/OPTIONS_INTEL_BRIEF_V1.md" in producer_doc


# ─────────────────────────────────────────────────────────────────────────────
# AD-1 B5 (product exposure) — the nine projection fields (contract §5a).
# Composition-function-level fixtures (hand-built card dicts), same precedented
# style as test_33's compose_opportunities order-stability check: these are pure
# functions operating on `cards: Sequence[Mapping]`, so a synthetic list with
# controlled research_priority_score/direction is a faithful, deterministic way
# to pin the board-position law without re-deriving Q_oi/Q_skew through the full
# chain pipeline for every rank.
# ─────────────────────────────────────────────────────────────────────────────


def _b5_card(symbol: str, *, direction: str, score: int, ec: float = 0.40, tier_metric: float = 1.0) -> dict:
    return {"symbol": symbol, "direction": direction, "research_priority_score": score,
            "evidence_confidence": ec, "tier_metric": tier_metric}


def _b5_ranked_fixture() -> list[dict]:
    """14 eligible cards, strictly decreasing R so board position is unambiguous.
    Directional (LONG/SHORT) names sit at ranks 7, 9 and 12 — everything else is
    VOLATILITY — mirroring the design packet's own worked example (AMD/XOM/MU)."""
    directions = {7: "LONG", 9: "SHORT", 12: "LONG"}
    cards = []
    for i in range(1, 15):
        d = directions.get(i, "VOLATILITY")
        cards.append(_b5_card(f"P{i:02d}", direction=d, score=2000 - 100 * i))
    return cards


def test_b5_1_board_rank_contiguous_on_opportunities():
    cards = _b5_ranked_fixture()
    opportunities, overflow = brief.compose_opportunities(cards)
    assert [c["board_rank"] for c in opportunities] == [1, 2, 3, 4, 5, 6]
    assert [c["symbol"] for c in opportunities] == ["P01", "P02", "P03", "P04", "P05", "P06"]
    assert overflow == len(cards) - 6


def test_b5_2_directional_watch_carries_real_gapped_ordinals_never_renumbered():
    cards = _b5_ranked_fixture()
    watch, watch_overflow = brief.compose_directional_watch(cards)
    # ranks 7, 9, 12 qualify (LONG/SHORT below the BOARD_N=6 cut); the gaps (8, 10,
    # 11 are VOLATILITY, never shown here) are the point — never renumbered 1,2,3.
    assert [c["board_rank"] for c in watch] == [7, 9, 12]
    assert [c["symbol"] for c in watch] == ["P07", "P09", "P12"]
    assert [c["direction"] for c in watch] == ["LONG", "SHORT", "LONG"]
    assert watch_overflow == 0


def test_b5_3_directional_watch_emission_capped_at_board_n_with_overflow():
    # 9 directional names below the cut (ranks 7-15) — cap reuses the existing
    # CONFIG["BOARD_N"] (6), no new constant; the 10th is emitted count 6 + overflow 3.
    # Six VOLATILITY fillers occupy the entire top-6 grid so all 9 D-cards land
    # strictly below the cut (rank > 6).
    cards = [_b5_card(f"V{i:02d}", direction="VOLATILITY", score=3000 - i) for i in range(1, 7)]
    for i in range(1, 10):
        cards.append(_b5_card(f"D{i:02d}", direction=("LONG" if i % 2 else "SHORT"), score=1800 - i))
    watch, overflow = brief.compose_directional_watch(cards)
    assert len(watch) == CONFIG["BOARD_N"] == 6
    assert overflow == 9 - 6
    # order-preserved: emitted watch rows are the highest-R-ranked 6 of the 9
    assert [c["symbol"] for c in watch] == [f"D{i:02d}" for i in range(1, 7)]


def test_b5_4_directional_qualified_count_is_cap_independent():
    # 2 directional names inside the top 6 AND 3 more below the cut: the
    # cap-independent count is the FULL eligible-set total (5), never just the
    # below-cut remainder compose_directional_watch reports (3).
    cards = [
        _b5_card("A", direction="LONG", score=2000),
        _b5_card("B", direction="SHORT", score=1900),
        _b5_card("C", direction="VOLATILITY", score=1800),
        _b5_card("D", direction="VOLATILITY", score=1700),
        _b5_card("E", direction="VOLATILITY", score=1600),
        _b5_card("F", direction="VOLATILITY", score=1500),  # rank 6 — cut line
        _b5_card("G", direction="LONG", score=1400),
        _b5_card("H", direction="VOLATILITY", score=1300),
        _b5_card("I", direction="SHORT", score=1200),
        _b5_card("J", direction="LONG", score=1100),
    ]
    watch, watch_overflow = brief.compose_directional_watch(cards)
    assert len(watch) + watch_overflow == 3          # below-cut-only count
    assert brief.directional_qualified_count(cards) == 5   # whole eligible set


def test_b5_5_event_and_risk_board_overflow_counts():
    events = [{"symbol": f"E{i}", "f_e": 1.0 - 0.01 * i} for i in range(7)]
    board, overflow = brief.compose_event_board(events)
    assert len(board) == CONFIG["EVENT_BOARD_N"] == 4
    assert overflow == 7 - 4

    risks = [{"symbol": f"R{i}", "evidence_strength": 1.0 - 0.01 * i} for i in range(6)]
    rboard, roverflow = brief.compose_risk_board(risks)
    assert len(rboard) == CONFIG["RISK_BOARD_N"] == 4
    assert roverflow == 6 - 4


def test_b5_6_no_boards_beyond_cap_silently_drop_members_overflow_is_exact():
    events = [{"symbol": f"E{i}", "f_e": 0.9} for i in range(4)]   # exactly at cap
    board, overflow = brief.compose_event_board(events)
    assert len(board) == 4 and overflow == 0


def test_b5_7_ordering_law_watch_and_boards_are_order_stable_not_insertion_order():
    """Mutate insertion order of the input fixture; the composed order (a pure
    function of R / |F_E| / evidence_strength, never dict/list insertion order)
    must be identical either way — the parity a downstream renderer depends on."""
    cards = _b5_ranked_fixture()
    watch_a, _ = brief.compose_directional_watch(cards)
    watch_b, _ = brief.compose_directional_watch(list(reversed(cards)))
    assert [c["symbol"] for c in watch_a] == [c["symbol"] for c in watch_b] == ["P07", "P09", "P12"]

    events = [{"symbol": "AMD", "f_e": 0.9}, {"symbol": "LLY", "f_e": 0.5}, {"symbol": "ORCL", "f_e": 0.2}]
    board_a, _ = brief.compose_event_board(events)
    board_b, _ = brief.compose_event_board(list(reversed(events)))
    assert [c["symbol"] for c in board_a] == [c["symbol"] for c in board_b] == ["AMD", "LLY", "ORCL"]

    risks = [{"symbol": "TSLA", "evidence_strength": 0.9}, {"symbol": "NFLX", "evidence_strength": 0.5}]
    risk_a, _ = brief.compose_risk_board(risks)
    risk_b, _ = brief.compose_risk_board(list(reversed(risks)))
    assert [c["symbol"] for c in risk_a] == [c["symbol"] for c in risk_b] == ["TSLA", "NFLX"]


def test_b5_8_no_signal_reason_state_closed_vocabulary():
    """F5 (2026-08-18): 4-entry closed vocabulary — legs both active AND agreeing in
    sign (the direction law's OWN Q-leg predicate satisfied) is a materially
    different state (SALIENCE_FAIL) from a genuinely quiet leg pair
    (LEGS_BELOW_THRESHOLD): the FORMER means classify_direction's salience gate (or
    a downstream low-R cut) withheld the hypothesis, never "the legs are inside
    their normal range"."""
    # both legs active (>= Q_TH), opposite sign -> disagree
    assert brief.no_signal_reason_state(0.6, -0.6) == "DISAGREE"
    assert brief.no_signal_reason_state(-0.7, 0.55) == "DISAGREE"
    # exactly one leg active -> one-sided
    assert brief.no_signal_reason_state(0.6, 0.1) == "ONE_SIDED"
    assert brief.no_signal_reason_state(None, 0.6) == "ONE_SIDED"
    # neither active -> legs genuinely below threshold
    assert brief.no_signal_reason_state(0.1, -0.2) == "LEGS_BELOW_THRESHOLD"
    assert brief.no_signal_reason_state(None, None) == "LEGS_BELOW_THRESHOLD"
    # both active AND agreeing in sign (Q-pass) -> the F5 4th entry, never WEAK
    assert brief.no_signal_reason_state(0.6, 0.6) == "SALIENCE_FAIL"
    assert brief.no_signal_reason_state(-0.55, -0.9) == "SALIENCE_FAIL"


def test_b5_9_no_signal_exemplar_attaches_reason_from_its_own_evidence():
    def card(symbol, q_oi, q_skew, *, tier_metric=1.0):
        return {
            "symbol": symbol, "board_state_symbol": "NO_SIGNAL", "coverage_complete": True,
            "tier_metric": tier_metric,
            "evidence": [{"name": "Q_oi", "value": q_oi}, {"name": "Q_skew", "value": q_skew}],
        }

    disagree = brief.no_signal_exemplar([card("DIS", 0.6, -0.6, tier_metric=3.0)])
    assert disagree["no_signal_reason"]["en"] == "the two readings disagree and activity is normal"
    assert disagree["no_signal_reason"]["zh"] == "两项读数不一致，活跃度正常"

    one_sided = brief.no_signal_exemplar([card("ONE", 0.6, 0.1, tier_metric=3.0)])
    assert one_sided["no_signal_reason"]["en"] == "only one reading moved and activity is normal"
    assert one_sided["no_signal_reason"]["zh"] == "仅一项读数变动，活跃度正常"

    weak = brief.no_signal_exemplar([card("WEK", 0.1, -0.1, tier_metric=3.0)])
    assert weak["no_signal_reason"]["en"] == "both readings are inside their normal range"
    assert weak["no_signal_reason"]["zh"] == "两项读数均在正常区间内"

    # highest-tier-metric selection law is unaffected — reason is computed on
    # whichever card the pre-existing selection rule already picked
    best = brief.no_signal_exemplar([card("LOW", 0.1, 0.1, tier_metric=1.0), card("HIGH", 0.6, -0.6, tier_metric=9.0)])
    assert best["symbol"] == "HIGH"
    assert best["no_signal_reason"]["en"] == "the two readings disagree and activity is normal"


def test_b5_9b_salience_fail_and_activity_normal_clause_gated_on_d_salience():
    """F5 (2026-08-18): (a) both Q legs active + agreeing renders the NEW
    SALIENCE_FAIL text, never the LEGS_BELOW_THRESHOLD wording; (b) the "...and
    activity is normal" clause on ONE_SIDED/DISAGREE may ONLY render when the
    exemplar's own D_salience reading is ACTUALLY below SALIENCE_TH — an elevated
    D_salience beside a one-sided/disagreeing leg pair must not claim "activity is
    normal" (that claim would be false: salience is why nothing fired, not the
    legs)."""
    def card(symbol, q_oi, q_skew, d_sal, *, tier_metric=1.0):
        return {
            "symbol": symbol, "board_state_symbol": "NO_SIGNAL", "coverage_complete": True,
            "tier_metric": tier_metric,
            "evidence": [{"name": "Q_oi", "value": q_oi}, {"name": "Q_skew", "value": q_skew},
                         {"name": "D_salience", "value": d_sal}],
        }

    # legs agree and both pass Q_TH, salience genuinely low -> SALIENCE_FAIL
    sal_fail = brief.no_signal_exemplar([card("SFL", 0.65, 0.7, 0.2, tier_metric=3.0)])
    assert sal_fail["no_signal_reason"]["en"] == "readings agree but activity is ordinary"
    assert sal_fail["no_signal_reason"]["zh"] == "读数一致，但活跃度平平"

    # legs agree and pass Q_TH but D_salience is ALSO high (qualified direction, low
    # R elsewhere) -> still SALIENCE_FAIL text; no "activity is normal" claim exists
    # on this entry to falsely gate.
    sal_fail_high = brief.no_signal_exemplar([card("SFH", 0.7, 0.75, 0.95, tier_metric=3.0)])
    assert sal_fail_high["no_signal_reason"]["en"] == "readings agree but activity is ordinary"

    # ONE_SIDED with salience genuinely low -> the normal-activity clause renders
    one_sided_low_sal = brief.no_signal_exemplar([card("OSL", 0.6, 0.1, 0.2, tier_metric=3.0)])
    assert one_sided_low_sal["no_signal_reason"]["en"] == "only one reading moved and activity is normal"

    # ONE_SIDED with an ELEVATED D_salience -> claiming "activity is normal" would
    # be false; the clause must NOT render.
    one_sided_high_sal = brief.no_signal_exemplar([card("OSH", 0.6, 0.1, 0.9, tier_metric=3.0)])
    assert one_sided_high_sal["no_signal_reason"]["en"] == "only one reading moved"
    assert "activity is normal" not in one_sided_high_sal["no_signal_reason"]["en"]

    # DISAGREE with an ELEVATED D_salience -> same gate.
    disagree_high_sal = brief.no_signal_exemplar([card("DGH", 0.6, -0.6, 0.9, tier_metric=3.0)])
    assert disagree_high_sal["no_signal_reason"]["en"] == "the two readings disagree"
    assert "，活跃度正常" not in disagree_high_sal["no_signal_reason"]["zh"]


def test_b5_10_empty_header_builders_carry_the_nine_fields_at_empty_defaults():
    """Every degraded/insufficient/stale payload must ship the nine B5 fields at
    their empty defaults — never absent-by-branch (contract §5a closing note)."""
    panel = brief.SessionPanel(as_of_session=None, oi_counted_date=None, pending_session=None,
                                pending_reason=None, chains_by_session={}, chain_next=None, lawful_pairs={})
    payload = brief._degraded_payload(reason="MIXED_VINTAGE", panel=panel, source_watermarks={},
                                       input_receipts=[], built_at_utc="2026-01-01T00:00:00+00:00")
    assert payload["directional_watch"] == [] and payload["directional_watch_overflow"] == 0
    assert payload["directional_qualified_count"] == 0
    assert payload["event_board_overflow"] == 0 and payload["risk_board_overflow"] == 0
    assert payload["no_signal_exemplar"] is None
    # F1: the "chains" domain exists at the empty shape too — never a two-domain
    # source_manifest that only MIXED_VINTAGE (or any other empty-header path) forgot.
    assert payload["source_manifest"]["chains"] == {"root": None, "member_count": 0, "files": {}}


def test_f2a_degraded_payload_public_wrapper_matches_internal_shape():
    """F2a: `brief.degraded_payload` is the public seam a producer-side check uses
    to reach the same DEGRADED shape the engine's own internal short-circuits
    produce — proven here to be byte-identical (besides receipt_id inputs) to
    `_degraded_payload` for the same reason/panel/receipts."""
    panel = brief.SessionPanel(as_of_session="2026-03-16", oi_counted_date="2026-03-17",
                                pending_session=None, pending_reason=None,
                                chains_by_session={}, chain_next=None, lawful_pairs={})
    kwargs = dict(panel=panel, source_watermarks={"chains_session_S": "2026-03-16"},
                  input_receipts=[{"logical_source": "x", "path": "y", "asof": "2026-03-16",
                                    "sha256": "z", "state": "ok"}],
                  built_at_utc="2026-01-01T00:00:00+00:00")
    internal = brief._degraded_payload(reason="UNIVERSE_RESOLUTION_FAILED", **kwargs)
    public = brief.degraded_payload(reason="UNIVERSE_RESOLUTION_FAILED", **kwargs)
    assert internal == public
    assert public["board_state"] == "DEGRADED"
    assert public["board_reason"] == "UNIVERSE_RESOLUTION_FAILED"
    assert public["opportunities"] == [] and public["risk_warnings"] == [] and public["event_board"] == []


def test_b5_11_end_to_end_artifact_carries_the_nine_fields_with_correct_types():
    """Full-pipeline smoke test (contract §5a wiring): a real `_build()` payload
    exposes every new top-level/nested key with the right shape, whatever the
    session happened to qualify."""
    panel, S, D = _std_panel()
    payload = _build(panel, S=S, D=D)
    assert isinstance(payload["directional_watch"], list)
    assert isinstance(payload["directional_watch_overflow"], int)
    assert isinstance(payload["directional_qualified_count"], int)
    assert isinstance(payload["event_board_overflow"], int)
    assert isinstance(payload["risk_board_overflow"], int)
    for c in payload["opportunities"]:
        assert isinstance(c["board_rank"], int) and c["board_rank"] >= 1
    for c in payload["directional_watch"]:
        assert isinstance(c["board_rank"], int) and c["board_rank"] > CONFIG["BOARD_N"]
        assert c["direction"] in ("LONG", "SHORT")
    opp_ranks_by_symbol = {c["symbol"]: c["board_rank"] for c in payload["opportunities"]}
    for c in payload["event_board"] + payload["risk_warnings"]:
        assert "board_rank" in c
        if c["symbol"] in opp_ranks_by_symbol:
            assert c["board_rank"] == opp_ranks_by_symbol[c["symbol"]]
        else:
            assert c["board_rank"] is None
    if payload["no_signal_exemplar"]:
        reason = payload["no_signal_exemplar"]["no_signal_reason"]
        assert set(reason) == {"en", "zh"}
    # opportunities board_rank stays contiguous 1..N regardless of how many
    # qualified this particular fixture (never re-derived from loop.index downstream)
    assert [c["board_rank"] for c in payload["opportunities"]] == list(range(1, len(payload["opportunities"]) + 1))


# ─────────────────────────────────────────────────────────────────────────────
# Crowding-defect ruling (AD-1, 2026-08-18; Fable-adjudicated, debugger-proven).
#
# Plain `(arr <= v).mean()` in `percentile_xs` assigned every member of a tied
# block the TOP-of-block rank. On the real store, sd_share mass-ties at 0.0 on
# most sessions (14/18 sampled; 369/372 names on S=2026-08-12), so that block's
# every member scored ~0.99 and c1 fired for the whole eligible universe
# (356/356 on 2026-08-12; true crowded set: 3). Fix has two parts: (1)
# `percentile_xs` adopts MIDRANK tie handling (a tied block ranks at its
# MIDPOINT, never the top); (2) `sd_share` becomes None — not 0.0 — when a
# name's own same-day (<=SD_DTE) volume sum is exactly zero, since a literal
# same-day share of 0 is "no same-day tape", not same-day crowding.
# `percentile_long` and d1/d3 aggregation are explicitly UNTOUCHED (out of
# scope for this ruling; d1's own inflation is recorded as a known limit,
# contract §9).
# ─────────────────────────────────────────────────────────────────────────────


def test_cd_1_midrank_mass_tie_ranks_at_block_midpoint():
    """The exact defect fixture: 369 zeros + 3 nonzero (S=2026-08-12 real-store
    shape). A zero member now ranks at the tied block's MIDPOINT (~0.5·369/372
    ~= 0.496), never the top (~0.99 under the old plain `<=` comparison) — and
    so no longer clears C1_TH on its own."""
    peers = {f"P{i}": 0.0 for i in range(369)}
    peers["A"], peers["B"], peers["C"] = 0.5, 0.8, 1.0
    p = brief.percentile_xs(peers, "P0")
    assert p == pytest.approx(0.5 * 369 / 372, abs=1e-9)
    assert p < CONFIG["C1_TH"]
    # every member of the tied block gets the SAME rank (block-uniform, not
    # insertion-order- or identity-dependent)
    assert brief.percentile_xs(peers, "P200") == pytest.approx(p, abs=1e-9)
    # the genuinely-extreme nonzero members still rank correctly (unaffected by
    # the tie-handling rewrite when they carry no ties of their own)
    assert brief.percentile_xs(peers, "C") == pytest.approx(371.5 / 372, abs=1e-9)


def test_cd_2_midrank_never_exceeds_old_top_of_block_ceiling():
    """Strict property: no member of a tied block may rank above
    `(count_strictly_less + block_size) / n` — the OLD plain-`<=` value is the
    CEILING a midrank member may never reach (it lands at the block's own
    midpoint, strictly below whenever the block has more than one member)."""
    peers = {f"P{i}": 0.0 for i in range(20)}
    peers.update({f"Q{i}": 1.0 for i in range(5)})
    n = len(peers)
    block_size = 20
    ceiling = (0 + block_size) / n
    p = brief.percentile_xs(peers, "P0")
    assert p < ceiling
    assert p == pytest.approx(0.5 * block_size / n, abs=1e-9)


def test_cd_3_continuous_input_regression_matches_old_within_one_over_n():
    """On a fully-distinct (no-tie) 350-name cross-section, midrank and the old
    plain-`<=` percentile differ by at most 1/n per name — the rewrite changes
    tie handling only; it is a no-op (up to the trivial 0.5-vs-1.0 count-equal
    term) whenever nothing is actually tied."""
    rng = np.random.default_rng(42)
    vals = rng.choice(np.linspace(0.0, 1.0, 10_000), size=350, replace=False)
    peers = {f"N{i}": float(v) for i, v in enumerate(vals)}
    arr = np.array(list(peers.values()))
    n = len(arr)
    for name, v in peers.items():
        new_p = brief.percentile_xs(peers, name)
        old_p = float((arr <= v).mean())
        assert abs(new_p - old_p) <= 1.0 / n + 1e-9


def test_cd_4_zero_same_day_volume_gives_none_sd_share_never_fires_c1():
    """A name with genuinely zero <=SD_DTE volume gets `sd_share = None`, not
    `0.0` — and c1 is None for it regardless of how extreme its peers are
    (an empty/zero-volume same-day slice is definitionally not same-day
    crowding)."""
    session = "2026-03-02"
    band_size = 21 * 2   # moneyness_grid(21) x call/put -- _symbol_rows' "zero" band
    rows = _symbol_rows("ZEROVOL", session, volume=80.0)
    for r in rows[:band_size]:            # zero out ONLY the <=SD_DTE band
        r["volume"] = 0.0
    hot_rows = _symbol_rows("HOT", session, volume=10.0)
    for r in hot_rows[:band_size]:        # concentrate volume in the same-day band
        r["volume"] = 500.0
    peer_rows: list[dict] = []
    for i in range(12):   # letters only -- _STANDARD_TICKER_RE root is [A-Za-z.]+
        peer_rows.extend(_symbol_rows(f"PEER{chr(65 + i)}", session, volume=50.0))
    df = _mk_chain(rows + hot_rows + peer_rows, session=session)
    m = brief.session_metrics(df)
    assert m["ZEROVOL"]["sd_share"] is None
    assert m["HOT"]["sd_share"] is not None and m["HOT"]["sd_share"] > 0.9
    xs = {n: m[n]["sd_share"] for n in m}
    assert sum(1 for v in xs.values() if v is not None) >= CONFIG["MIN_HISTORY"]
    assert brief.percentile_xs(xs, "ZEROVOL") is None
    # HOT's own extreme peer value fires normally -- proves ZEROVOL's None is
    # not an artifact of a starved cross-section
    assert brief.percentile_xs(xs, "HOT") >= CONFIG["C1_TH"]


def test_cd_5_below_floor_finite_members_c1_none_for_everyone():
    """Fewer than MIN_HISTORY (10) finite `sd_share` members -> c1 is None
    universe-wide, even though every member's own value is a genuine
    (non-degenerate) same-day share -- honest family absence, not a fired
    leg."""
    session = "2026-03-02"
    rows: list[dict] = []
    for i in range(5):   # < MIN_HISTORY(10); letters only, see _STANDARD_TICKER_RE
        rows.extend(_symbol_rows(f"NM{chr(65 + i)}", session, volume=50.0))
    df = _mk_chain(rows, session=session)
    m = brief.session_metrics(df)
    xs = {n: m[n]["sd_share"] for n in m}
    assert 0 < sum(1 for v in xs.values() if v is not None) < CONFIG["MIN_HISTORY"]
    for n in m:
        assert brief.percentile_xs(xs, n) is None


def test_cd_6_fresh_until_reverts_to_family_life_when_c1_leg_vanishes():
    """B3 knock-on (fresh_until_for, direct unit level -- same style as the b3_*
    suite): a RISK_ONLY card jointly fired by c1 (same-day, life 0) AND c2 (V
    family, life 5) was forced to the CURRENT session by the min-of-mins rule.
    Once the spurious c1 leg vanishes (this ruling), the SAME card -- now only
    c2-fired -- reverts to c2's own V-family life (S+5 sessions), not S."""
    S = "2026-03-16"
    before = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                    crowd_fired_legs=["c1", "c2"])
    assert before == S   # c1's life-0 wins the min -- crowd-shortened to today
    after = brief.fresh_until_for(direction="RISK_ONLY", S=S, session_n_forward_fn=_session_n_forward,
                                   crowd_fired_legs=["c2"])
    assert after == _session_n_forward(S, CONFIG["FRESH_LIVES_SESSIONS"]["V"])
    assert after > S     # returned to its family life, no longer crowd-shortened


@pytest.mark.needs_full_checkout("data")
def test_cd_7_real_store_recurrence_guard_2026_08_12(tmp_path, monkeypatch):
    """Real-store recurrence guard, pinned to the debugger's exact exemplar
    session (S=2026-08-12, D=2026-08-13) via a filtered CHAINS_DIR snapshot --
    so this stays anchored to the known-defect session regardless of how much
    the committed store grows later (``producer.build`` otherwise always picks
    the NEWEST lawful pair). Asserts (a) the fired-crowding count the real
    pipeline now produces is <=40 (post-fix expectation ~27: c2/c3 only -- this
    session structurally has too few finite sd_share peers for c1 to fire at
    all, an honest absence) and (b) that bound is corroborated by an
    INDEPENDENT recomputation straight from `session_metrics`/`percentile_xs`
    on the real chain (not a re-read of the artifact's own counters)."""
    S, D = "2026-08-12", "2026-08-13"
    real_chains = REPO_ROOT / "data" / "polygon_gex" / "chains"
    s_file, d_file = real_chains / f"{S}.parquet", real_chains / f"{D}.parquet"
    if not (s_file.exists() and d_file.exists()):
        pytest.skip(f"real store no longer carries the {S}/{D} exemplar snapshots")

    # producer.build() computes input-receipt paths via `fp.relative_to(_REPO_ROOT)`,
    # so the pinned snapshot dir must live UNDER the repo root, not the system tmp
    # dir pytest's own `tmp_path` fixture uses.
    import shutil
    import tempfile
    scratch = Path(tempfile.mkdtemp(dir=REPO_ROOT, prefix=".cd7_scratch_"))
    try:
        pinned_dir = scratch / "chains"
        pinned_dir.mkdir()
        for f in sorted(real_chains.glob("*.parquet")):
            if f.stem <= D:
                (pinned_dir / f.name).symlink_to(f)
        monkeypatch.setattr(producer, "CHAINS_DIR", pinned_dir)

        payload = producer.build(now=datetime.now(timezone.utc), out_path=tmp_path / "artifact.json",
                                  ignore_staleness=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    assert payload["as_of_session"] == S
    assert payload["oi_counted_date"] == D

    total_fired = len(payload["risk_warnings"]) + payload["risk_board_overflow"]

    # Independent recomputation: straight from the engine primitives on the
    # real S-day chain, not from re-reading the artifact.
    day_S = pd.read_parquet(s_file)
    metrics_S, _ = brief.session_metrics_and_exclusions(day_S)
    sd_xs = {n: metrics_S[n]["sd_share"] for n in metrics_S}
    finite_sd = [v for v in sd_xs.values() if v is not None]
    c1_fired_recomputed = {
        n for n in metrics_S
        if (c1 := brief.percentile_xs(sd_xs, n)) is not None and c1 >= CONFIG["C1_TH"]
    }
    # the debugger's own exemplar (369/372 zero sd_share) -- fewer than
    # MIN_HISTORY finite same-day-volume names this session, so c1 is an
    # honest universe-wide absence, never a fired leg.
    assert len(finite_sd) < CONFIG["MIN_HISTORY"]
    assert c1_fired_recomputed == set()

    # every card the real pipeline actually exposes must agree: none of them
    # carry a fired c1 leg this session.
    for grp in ("opportunities", "directional_watch", "event_board", "risk_warnings"):
        for c in payload[grp]:
            cw = c.get("crowding")
            if cw is not None:
                assert "c1" not in cw["fired"]

    assert total_fired <= 40, (
        f"post-fix crowding fire count {total_fired} exceeds the debugger's bound "
        f"(expected ~27: c2/c3 only -- c1 is an honest absence this session, "
        f"recomputed independently above)"
    )
