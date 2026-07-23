"""tests/test_build_portfolio_ctx.py — portfolio_ctx.v1 bake (Portfolio-Aware W0).

Unit tests run entirely on hand-built synthetic source dicts (no reads of the real
data/ or site/ trees, no parquet) — build_ctx is a pure function of the sources dict.
One integration smoke test runs main() against the real committed repo files.

Covered (spec §Tests):
1. Schema invariants (schema/v/asof/built/coverage/tickers keys; top-level shape).
2. Join correctness for one fully-covered synthetic ticker.
3. Fail-open: each source empty → block omitted, no placeholder nulls/zeros.
4. Zero-coverage ticker omitted from `tickers`.
5. Verbatim vocabulary: stance strings pass through unmodified.
6. Congress window: ReportDate filtered relative to asof; cap 5; side incl. "Sale (Partial)".
7. No-NaN: json.dumps(allow_nan=False) succeeds on a full payload.
8. Determinism: same inputs + same asof → byte-identical output.
+ integration smoke: main() against real files → parses + schema key correct.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_portfolio_ctx import build_ctx, main  # noqa: E402


ASOF = "2026-07-23"


def _full_sources() -> dict:
    """A synthetic sources dict where NVDA is fully covered across every desk."""
    return {
        "risk_state": {
            "score": 77, "verdict": "RISK_ON", "label_en": "Risk-on",
            "label_zh": "风险偏好", "color": "green",
            "band_changed": False,  # extra key must NOT leak into the regime block
        },
        "us_standouts": {
            "gate_go": True,
            "buy": [{
                "ticker": "NVDA", "sector": "Technology",
                "label": "BUY ZONE", "state": "FRESH BUY",
                "entry_signal": {"status": "buy_now", "act_level": 2,
                                 "urgency": "now", "headline": "ignored"},
            }],
            "watch": [],
            "laggards": [],
        },
        "subsector": {
            "sectors": [
                {"kind": "sector", "sector": "Technology", "label": "Technology",
                 "class": "tailwind"},
                {"kind": "sector", "sector": "Energy", "label": "Energy",
                 "class": "entry_now"},
            ]
        },
        "sector_central": {
            "sectors": [
                {"name": "Technology",
                 "conviction": {"label_en": "Accumulate", "label_zh": "积极配置"},
                 "rotation": {"state_plain_en": "trend running"}},
            ]
        },
        "screener": {  # loader normalizes to {TICKER: row}; inject already-indexed here
            "NVDA": {"ticker": "NVDA", "region": "USA", "source": "live",
                     "stage": 2, "stage_label": "2A Breakout",
                     "weeks_in_stage": 8, "fresh": True, "sector": "Technology"},
        },
        "by_ticker": {
            "NVDA": {"next_earnings": "2026-08-27", "days_to_earnings": 35},
        },
        "insider": {
            "NVDA": {"buyers": 2, "sellers": 5, "net_mn": -12.3, "bps": None},
        },
        "smartmoney": {
            "NVDA": {"n_holders": 7, "n_buying": 3, "n_selling": 1,
                     "trend": {"direction": "accumulating"}, "as_of": "2026-03-31"},
        },
        "baskets": {
            "ai_soft": {"id": "ai_soft", "name": "AI Software",
                        "name_zh": "AI软件", "reco": "accumulate", "rank": 3},
        },
        "membership": {"NVDA": ["ai_soft"]},
        "congress": [
            {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Representatives",
             "Party": "R", "TransactionDate": "2026-07-21", "ReportDate": "2026-07-22",
             "Amount": 8000.0},
        ],
    }


# ── 1. schema invariants ────────────────────────────────────────────────────

def test_schema_invariants():
    p = build_ctx(_full_sources(), ["NVDA"], ASOF)
    assert p["schema"] == "portfolio_ctx.v1"
    assert p["v"] == 1
    assert p["asof"] == ASOF
    assert isinstance(p["built"], str) and p["built"].endswith("+00:00")
    assert set(p["coverage"]) == {"tickers", "stage", "themes", "earnings",
                                  "insider", "congress", "f13", "entry"}
    assert isinstance(p["tickers"], dict)
    assert "gate_go" in p
    # top-level key set is FIXED (contract stability): full and empty bakes match
    fixed = {"schema", "v", "asof", "built", "gate_go", "regime", "sectors",
             "coverage", "tickers"}
    assert set(p.keys()) == fixed
    empty = {k: ({} if k != "congress" else None) for k in [
        "risk_state", "us_standouts", "subsector", "sector_central", "screener",
        "by_ticker", "insider", "smartmoney", "baskets", "membership", "congress"]}
    assert set(build_ctx(empty, ["NVDA"], ASOF).keys()) == fixed


# ── 2. join correctness (fully-covered ticker) ──────────────────────────────

def test_full_ticker_join():
    p = build_ctx(_full_sources(), ["NVDA"], ASOF)
    nvda = p["tickers"]["NVDA"]
    assert nvda["sector"] == "Technology"
    assert nvda["stage"] == {"n": 2, "label": "2A Breakout", "weeks": 8, "fresh": True}
    assert nvda["entry"] == {"status": "buy_now", "act_level": 2,
                             "urgency": "now", "label": "BUY ZONE", "state": "FRESH BUY"}
    assert nvda["earnings"] == {"next": "2026-08-27", "days_to": 35}
    assert nvda["insider"] == {"buyers": 2, "sellers": 5, "net_mn": -12.3, "bps": None}
    assert nvda["f13"] == {"holders": 7, "adds": 3, "trims": 1,
                           "direction": "accumulating", "asof": "2026-03-31"}
    assert nvda["themes"] == [{"id": "ai_soft", "name": "AI Software",
                               "name_zh": "AI软件", "reco": "accumulate",
                               "rank": 3, "lane": None}]
    assert nvda["congress"] == [{"side": "buy", "chamber": "house", "party": "R",
                                 "tx_date": "2026-07-21", "filed": "2026-07-22",
                                 "amount_mid": 8000.0}]
    assert p["gate_go"] is True
    assert p["regime"] == {"us": {"score": 77, "verdict": "RISK_ON",
                                  "label_en": "Risk-on",
                                  "label_zh": "风险偏好",
                                  "color": "green"}}
    # coverage counts everything present
    assert p["coverage"] == {"tickers": 1, "stage": 1, "themes": 1, "earnings": 1,
                             "insider": 1, "congress": 1, "f13": 1, "entry": 1}


def test_regime_extra_keys_do_not_leak():
    p = build_ctx(_full_sources(), ["NVDA"], ASOF)
    assert "band_changed" not in p["regime"]["us"]


# ── 3. fail-open per source ─────────────────────────────────────────────────

@pytest.mark.parametrize("drop,missing_block", [
    ("screener", ("stage",)),
    ("by_ticker", ("earnings",)),
    ("insider", ("insider",)),
    ("smartmoney", ("f13",)),
    ("membership", ("themes",)),
    ("congress", ("congress",)),
    ("us_standouts", ("entry",)),
])
def test_fail_open_each_source(drop, missing_block):
    src = _full_sources()
    src[drop] = {} if drop != "congress" else None
    p = build_ctx(src, ["NVDA"], ASOF)
    # bake still succeeds; NVDA still present (other desks cover it)
    assert "NVDA" in p["tickers"]
    nvda = p["tickers"]["NVDA"]
    for blk in missing_block:
        assert blk not in nvda, f"{blk} should be omitted when {drop} is empty"
    # no placeholder null/zero values anywhere in the block
    assert None not in [v for v in nvda.values() if not isinstance(v, (dict, list))]


def test_all_sources_empty_bakes_ok():
    empty = {k: ({} if k != "congress" else None) for k in [
        "risk_state", "us_standouts", "subsector", "sector_central", "screener",
        "by_ticker", "insider", "smartmoney", "baskets", "membership", "congress"]}
    p = build_ctx(empty, ["NVDA"], ASOF)
    assert p["schema"] == "portfolio_ctx.v1"
    assert p["tickers"] == {}          # zero-coverage → omitted
    assert p["gate_go"] is None        # gate_go absent → null (not fabricated False)
    # top-level regime/sectors are STABLE keys (empty dict, never dropped) so the
    # cross-repo contract does not drift when a source is empty
    assert p["regime"] == {}
    assert p["sectors"] == {}


# ── 4. zero-coverage ticker omitted ─────────────────────────────────────────

def test_zero_coverage_ticker_omitted():
    src = _full_sources()
    p = build_ctx(src, ["NVDA", "ZZZZ"], ASOF)
    assert "NVDA" in p["tickers"]
    assert "ZZZZ" not in p["tickers"], "ticker with no desk coverage must be omitted"
    assert p["coverage"]["tickers"] == 1


def test_sector_only_ticker_omitted():
    """A ticker with a sector but NO desk block is metadata-only → omitted."""
    src = _full_sources()
    # give ORCL a board sector row but strip it from every desk source
    src["us_standouts"]["watch"] = [{"ticker": "ORCL", "sector": "Technology"}]
    p = build_ctx(src, ["ORCL"], ASOF)
    assert "ORCL" not in p["tickers"]


# ── 5. verbatim vocabulary ──────────────────────────────────────────────────

def test_verbatim_stance_strings():
    src = _full_sources()
    src["sector_central"]["sectors"][0]["conviction"]["label_en"] = "Take profits"
    src["sector_central"]["sectors"][0]["rotation"]["state_plain_en"] = "extended — watch"
    src["baskets"]["ai_soft"]["reco"] = "trim_into_strength"
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["sectors"]["Technology"]["conviction_en"] == "Take profits"
    assert p["sectors"]["Technology"]["rotation_state"] == "extended — watch"
    assert p["tickers"]["NVDA"]["themes"][0]["reco"] == "trim_into_strength"


# ── 6. congress window / cap / side mapping ─────────────────────────────────

def test_congress_window_cap_and_side_mapping():
    rows = [
        # in-window buy (filed 2026-07-22, asof 2026-07-23 → 1 day old)
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-01", "ReportDate": "2026-07-22", "Amount": 1000.0},
        # in-window partial sale → side "sell"
        {"Ticker": "NVDA", "Transaction": "Sale (Partial)", "House": "Representatives",
         "Party": "D", "TransactionDate": "2026-06-30", "ReportDate": "2026-07-10",
         "Amount": 5000.0},
        # in-window exchange → side "other"
        {"Ticker": "NVDA", "Transaction": "Exchange", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-06-01", "ReportDate": "2026-06-05", "Amount": None},
        # OUT of window: filed >90 days before asof (2026-04-01 < cutoff 2026-04-24)
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-01-01", "ReportDate": "2026-04-01", "Amount": 1.0},
        # OUT of window: filed AFTER asof (future disclosure)
        {"Ticker": "NVDA", "Transaction": "Sale", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-25", "ReportDate": "2026-07-30", "Amount": 1.0},
    ]
    src = _full_sources()
    src["congress"] = rows
    p = build_ctx(src, ["NVDA"], ASOF)
    cong = p["tickers"]["NVDA"]["congress"]
    assert len(cong) == 3  # two out-of-window rows dropped
    sides = {c["filed"]: c["side"] for c in cong}
    assert sides["2026-07-22"] == "buy"
    assert sides["2026-07-10"] == "sell"     # "Sale (Partial)"
    assert sides["2026-06-05"] == "other"    # "Exchange"
    # sorted by filed desc
    assert [c["filed"] for c in cong] == ["2026-07-22", "2026-07-10", "2026-06-05"]
    # amount_mid float or null; chamber/party mapped
    exch = next(c for c in cong if c["filed"] == "2026-06-05")
    assert exch["amount_mid"] is None
    assert exch["chamber"] == "senate"
    part = next(c for c in cong if c["filed"] == "2026-07-10")
    assert part["chamber"] == "house" and part["party"] == "D"


def test_congress_cap_five():
    rows = [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-0%d" % (i % 9 + 1),
         "ReportDate": "2026-07-%02d" % (10 + i), "Amount": float(i)}
        for i in range(8)
    ]
    src = _full_sources()
    src["congress"] = rows
    p = build_ctx(src, ["NVDA"], ASOF)
    assert len(p["tickers"]["NVDA"]["congress"]) == 5


def test_congress_window_relative_to_asof():
    """Same rows, earlier asof → window slides; a row that was in-window drops out."""
    rows = [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-05-01", "ReportDate": "2026-05-02", "Amount": 1.0},
    ]
    src = _full_sources()
    src["congress"] = rows
    # asof far in the future → 2026-05-02 is >90 days old → dropped
    p_far = build_ctx(src, ["NVDA"], "2026-09-01")
    assert "congress" not in p_far["tickers"].get("NVDA", {})
    # asof near the report date → in window
    p_near = build_ctx(src, ["NVDA"], "2026-05-20")
    assert len(p_near["tickers"]["NVDA"]["congress"]) == 1


# ── 7. no NaN ───────────────────────────────────────────────────────────────

def test_no_nan_serialization():
    p = build_ctx(_full_sources(), ["NVDA", "AAPL", "XOM"], ASOF)
    # must not raise
    s = json.dumps(p, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    assert "NaN" not in s
    # round-trips
    assert json.loads(s)["schema"] == "portfolio_ctx.v1"


def test_congress_nan_amount_coerced_to_null():
    """A float NaN Amount (parquet with a missing value) must become null, not NaN."""
    src = _full_sources()
    src["congress"] = [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-01", "ReportDate": "2026-07-22",
         "Amount": float("nan")},
    ]
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["congress"][0]["amount_mid"] is None
    json.dumps(p, allow_nan=False)  # must not raise


# ── 8. determinism ──────────────────────────────────────────────────────────

def test_determinism_same_inputs_same_asof():
    a = build_ctx(_full_sources(), ["NVDA"], ASOF)
    b = build_ctx(_full_sources(), ["NVDA"], ASOF)
    # `built` is wall-clock; compare everything else byte-identically
    a.pop("built"); b.pop("built")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ── integration smoke (real repo files) ─────────────────────────────────────

def test_integration_smoke_real_files(tmp_path):
    """main() against the REAL committed sources → parseable, schema key correct.

    Skips gracefully if a committed source is missing (fresh worktree / CI runner).
    """
    required = [
        ROOT / "site" / "factordata" / "us_standouts.json",
        ROOT / "site" / "stagedata" / "screener.json",
    ]
    if not all(p.exists() for p in required):
        pytest.skip("committed source(s) absent in this environment")

    out = tmp_path / "portfolio_ctx.json"
    rc = main(["--tickers", "NVDA,AAPL,XOM", "--asof", ASOF,
               "--out", str(out), "--root", str(ROOT)])
    assert rc == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "portfolio_ctx.v1"
    assert payload["v"] == 1
    assert payload["asof"] == ASOF
    assert set(payload["coverage"]) == {"tickers", "stage", "themes", "earnings",
                                        "insider", "congress", "f13", "entry"}
    # the artifact must serialize without NaN
    json.dumps(payload, allow_nan=False)
