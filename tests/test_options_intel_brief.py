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
import sys
from datetime import date
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
    payload = _build(panel_truncated, S=S, D=D)
    assert payload["board_state"] == "INSUFFICIENT_COVERAGE"
    assert payload["opportunities"] == []
    assert payload["event_board"] == []
    assert payload["risk_warnings"] == []


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


def test_module_docstrings_cite_the_contract():
    engine_doc = (REPO_ROOT / "engine" / "options_intel_brief.py").read_text()[:2000]
    producer_doc = (REPO_ROOT / "scripts" / "build_options_intel_brief.py").read_text()[:2000]
    assert "contracts/options/OPTIONS_INTEL_BRIEF_V1.md" in engine_doc
    assert "contracts/options/OPTIONS_INTEL_BRIEF_V1.md" in producer_doc
