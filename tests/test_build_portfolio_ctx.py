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

W1 additions (spec §7):
9.  Universe union: each source contributes tickers when --tickers omitted.
10. Ticker hygiene: junk / foreign-shape codes dropped from the universe.
11. Congress single-pass index: same window/cap/order/side semantics as W0.
12. Sector rename table: Yahoo class lands under GICS key; unknown → verbatim; no value rewrite.
13. Theme-lane join: present → lane string; missing side-artifact → W0 null behavior.
14. Full-universe determinism (no --tickers).
15. Integration: real files → ≥500 tickers, elapsed < 30s.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_portfolio_ctx import (  # noqa: E402
    build_ctx,
    main,
    _valid_ticker,
    _build_congress_index,
    _congress_block,
    _gics_sector_name,
    _YAHOO_TO_GICS_SECTOR,
)


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
                                  "insider", "congress", "f13", "entry", "chains"}
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
    # coverage counts everything present (chains: 0 — _full_sources has no chain_state)
    assert p["coverage"] == {"tickers": 1, "stage": 1, "themes": 1, "earnings": 1, "chains": 0,
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
                                        "insider", "congress", "f13", "entry", "chains"}
    # the artifact must serialize without NaN
    json.dumps(payload, allow_nan=False)


# ══════════════════════════════════════════════════════════════════════════════
# W1 — full-universe union, hygiene, single-pass congress, sector rename, lanes
# ══════════════════════════════════════════════════════════════════════════════

# ── 9. universe union: each source contributes tickers (no --tickers) ────────

def test_universe_union_each_source_contributes():
    """With tickers=None the universe = union of validated ticker keys across the
    loaded sources; every desk that carries a distinct ticker gets it included."""
    src = {
        # each source carries a DISTINCT ticker so we can assert per-source contribution
        "screener": {"SCRN": {"ticker": "SCRN", "region": "USA", "source": "live",
                              "stage": 1, "stage_label": "1 Base"}},
        "insider": {"INSD": {"buyers": 1, "sellers": 0}},
        "smartmoney": {"SMRT": {"n_holders": 2, "n_buying": 1}},
        "by_ticker": {"ERNS": {"next_earnings": "2026-09-01", "days_to_earnings": 40}},
        "membership": {"MEMB": ["thm1"]},
        "baskets": {"thm1": {"id": "thm1", "name": "Theme One"}},
        "us_standouts": {"buy": [{"ticker": "BORD", "sector": "Energy",
                                  "entry_signal": {"status": "buy_now"}}]},
        "congress": [
            {"Ticker": "CNGR", "Transaction": "Purchase", "House": "Senate",
             "Party": "R", "TransactionDate": "2026-07-01", "ReportDate": "2026-07-22",
             "Amount": 1000.0},
        ],
    }
    p = build_ctx(src, None, ASOF)
    got = set(p["tickers"])
    # each source contributed its unique ticker (all have desk coverage)
    for tk in ("SCRN", "INSD", "SMRT", "ERNS", "MEMB", "BORD", "CNGR"):
        assert tk in got, f"{tk} missing — its source did not contribute to the union"


def test_universe_union_stub_only_when_tickers_given():
    """An explicit --tickers list overrides the union (dev/stub path)."""
    src = _full_sources()
    p = build_ctx(src, ["NVDA"], ASOF)
    assert set(p["tickers"]) == {"NVDA"}


# ── 10. ticker hygiene: junk / foreign-shape codes dropped ───────────────────

def test_valid_ticker_gate():
    assert _valid_ticker("nvda") == "NVDA"          # uppercased
    assert _valid_ticker("BRK.B") == "BRK.B"        # dotted share class ok
    assert _valid_ticker("BRK-B") == "BRK-B"        # dashed share class ok
    assert _valid_ticker("N/A") is None             # placeholder junk (slash)
    assert _valid_ticker("NAN") is None             # junk word
    assert _valid_ticker("") is None
    assert _valid_ticker(None) is None
    assert _valid_ticker("123") is None             # must start with a letter
    assert _valid_ticker("TOOLONGTICKER") is None   # > shape length
    assert _valid_ticker("A B") is None             # space


def test_universe_hygiene_drops_junk():
    """Junk keys in a source map never enter the universe."""
    src = {
        "insider": {"AAA": {"buyers": 1}, "N/A": {"buyers": 9}, "": {"buyers": 9},
                    "123": {"buyers": 9}},
    }
    p = build_ctx(src, None, ASOF)
    assert "AAA" in p["tickers"]
    for junk in ("N/A", "", "123"):
        assert junk not in p["tickers"]


# ── 11. congress single-pass index correctness ───────────────────────────────

def _congress_rows_sample():
    return [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-01", "ReportDate": "2026-07-22", "Amount": 1000.0},
        {"Ticker": "NVDA", "Transaction": "Sale (Partial)", "House": "Representatives",
         "Party": "D", "TransactionDate": "2026-06-30", "ReportDate": "2026-07-10",
         "Amount": 5000.0},
        {"Ticker": "NVDA", "Transaction": "Exchange", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-06-01", "ReportDate": "2026-06-05", "Amount": None},
        # AAPL row so the index proves it groups by ticker
        {"Ticker": "AAPL", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-01", "ReportDate": "2026-07-20", "Amount": 42.0},
        # out of window (filed >90d before asof)
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-01-01", "ReportDate": "2026-04-01", "Amount": 1.0},
        # future disclosure (filed after asof)
        {"Ticker": "NVDA", "Transaction": "Sale", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-25", "ReportDate": "2026-07-30", "Amount": 1.0},
        # junk ticker — must be dropped by the index hygiene gate
        {"Ticker": "N/A", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-01", "ReportDate": "2026-07-15", "Amount": 1.0},
    ]


def test_congress_index_groups_and_windows():
    idx = _build_congress_index(_congress_rows_sample(), ASOF)
    assert set(idx) == {"NVDA", "AAPL"}          # junk + no other tickers
    assert len(idx["NVDA"]) == 3                 # 2 out-of-window rows dropped
    assert len(idx["AAPL"]) == 1


def test_congress_block_from_index_matches_w0_semantics():
    """Same window/cap/order/side result via the single-pass index as W0's rescan."""
    idx = _build_congress_index(_congress_rows_sample(), ASOF)
    cong = _congress_block("NVDA", idx)
    # sorted by filed desc, cap 5
    assert [c["filed"] for c in cong] == ["2026-07-22", "2026-07-10", "2026-06-05"]
    sides = {c["filed"]: c["side"] for c in cong}
    assert sides["2026-07-22"] == "buy"
    assert sides["2026-07-10"] == "sell"          # "Sale (Partial)"
    assert sides["2026-06-05"] == "other"         # "Exchange"
    exch = next(c for c in cong if c["filed"] == "2026-06-05")
    assert exch["amount_mid"] is None and exch["chamber"] == "senate"


def test_congress_index_cap_five():
    rows = [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-07-0%d" % (i % 9 + 1),
         "ReportDate": "2026-07-%02d" % (10 + i), "Amount": float(i)}
        for i in range(8)
    ]
    idx = _build_congress_index(rows, ASOF)
    assert len(_congress_block("NVDA", idx)) == 5


def test_congress_index_window_relative_to_asof():
    rows = [
        {"Ticker": "NVDA", "Transaction": "Purchase", "House": "Senate", "Party": "R",
         "TransactionDate": "2026-05-01", "ReportDate": "2026-05-02", "Amount": 1.0},
    ]
    # asof far in the future → out of window
    assert _build_congress_index(rows, "2026-09-01").get("NVDA") is None
    # asof near the report date → in window
    assert len(_build_congress_index(rows, "2026-05-20")["NVDA"]) == 1


# ── 12. sector rename table ───────────────────────────────────────────────────

def test_gics_rename_table_maps_and_falls_through():
    # Yahoo → GICS-family (the join key). Technology → Technology (identity, matches
    # sector_central) NOT "Information Technology".
    assert _gics_sector_name("Technology") == "Technology"
    assert _gics_sector_name("Financial") == "Financials"
    assert _gics_sector_name("Healthcare") == "Health Care"
    assert _gics_sector_name("Consumer Cyclical") == "Consumer Discretionary"
    assert _gics_sector_name("Consumer Defensive") == "Consumer Staples"
    assert _gics_sector_name("Basic Materials") == "Materials"
    # identity rows
    for s in ("Energy", "Utilities", "Industrials", "Real Estate",
              "Communication Services"):
        assert _gics_sector_name(s) == s
    # unknown name kept verbatim (never dropped, never guessed)
    assert _gics_sector_name("Weird Custom Sector") == "Weird Custom Sector"
    # table has no value that would split Technology across two keys
    assert "Information Technology" not in _YAHOO_TO_GICS_SECTOR.values()


def test_sector_block_yahoo_and_central_merge_under_one_gics_key():
    """subsector (Yahoo 'Technology' class) + sector_central ('Technology') land under
    ONE key 'Technology'; values pass through verbatim (no rewriting)."""
    src = {
        "subsector": {"sectors": [
            {"kind": "sector", "sector": "Technology", "label": "Technology",
             "class": "tailwind"},
            {"kind": "sector", "sector": "Financial", "label": "Financial",
             "class": "entry_now"},
        ]},
        "sector_central": {"sectors": [
            {"name": "Technology",
             "conviction": {"label_en": "Accumulate", "label_zh": "积极配置"},
             "rotation": {"state_plain_en": "trend running"}},
        ]},
    }
    p = build_ctx(src, ["NVDA"], ASOF)
    sec = p["sectors"]
    # single unified Technology key with BOTH class (from Yahoo) + central fields
    assert sec["Technology"] == {"class": "tailwind", "conviction_en": "Accumulate",
                                 "conviction_zh": "积极配置",
                                 "rotation_state": "trend running"}
    # Yahoo "Financial" renamed to GICS "Financials" key; value verbatim
    assert "Financials" in sec and sec["Financials"]["class"] == "entry_now"
    assert "Financial" not in sec           # the Yahoo name never survives as a key
    # no "Information Technology" split key
    assert "Information Technology" not in sec


def test_sector_block_unknown_name_kept_verbatim():
    src = {"subsector": {"sectors": [
        {"kind": "sector", "sector": "Frontier Widgets", "label": "Frontier Widgets",
         "class": "tailwind"}]}}
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["sectors"]["Frontier Widgets"] == {"class": "tailwind"}


# ── 13. theme-lane join ───────────────────────────────────────────────────────

def test_theme_lane_join_present():
    """theme_lanes present → the lane string is joined by theme id."""
    src = _full_sources()
    src["theme_lanes"] = {"ai_soft": "working"}
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["themes"][0]["lane"] == "working"


def test_theme_lane_join_missing_is_null():
    """No theme_lanes source (fail-open) → lane is None (W0 behavior)."""
    src = _full_sources()          # _full_sources has NO theme_lanes key
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["themes"][0]["lane"] is None
    # a theme id absent from a present map is also None (not fabricated)
    src["theme_lanes"] = {"other_theme": "caution"}
    p2 = build_ctx(src, ["NVDA"], ASOF)
    assert p2["tickers"]["NVDA"]["themes"][0]["lane"] is None


# ── 13b. basket-keyed lane join (PR-A1) ───────────────────────────────────────
# Story ids key the ledgers, basket ids key membership, and only 7 of 18 are spelled
# the same — the same-id join read null for the rest. `basket_lanes` is the explicit
# crosswalk projection; the same-id lookup stays as the fallback.

def test_basket_lane_join_resolves_a_differently_spelled_story():
    """A basket whose story id differs (the 11-of-18 case) now resolves its lane."""
    src = _full_sources()
    # story `some_story` owns basket `ai_soft`; the same-id map cannot see it.
    src["theme_lanes"] = {"some_story": "early"}
    src["basket_lanes"] = {"ai_soft": "early"}
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["themes"][0]["lane"] == "early"


def test_basket_lane_join_is_a_strict_superset():
    """basket_lanes absent/empty → the legacy same-id join still resolves (no regression)."""
    src = _full_sources()
    src["theme_lanes"] = {"ai_soft": "working"}
    for empty in ({}, None):
        src["basket_lanes"] = empty
        p = build_ctx(src, ["NVDA"], ASOF)
        assert p["tickers"]["NVDA"]["themes"][0]["lane"] == "working"


def test_basket_lane_join_fabricates_nothing():
    """A basket in neither map stays None; a non-string value is not passed through."""
    src = _full_sources()
    src["theme_lanes"] = {}
    src["basket_lanes"] = {"other_basket": "caution"}
    p = build_ctx(src, ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["themes"][0]["lane"] is None
    src["basket_lanes"] = {"ai_soft": {"lane": "working"}}   # malformed
    p2 = build_ctx(src, ["NVDA"], ASOF)
    assert p2["tickers"]["NVDA"]["themes"][0]["lane"] is None


# ── 14. full-universe determinism ────────────────────────────────────────────

def test_full_universe_determinism():
    src = _full_sources()
    a = build_ctx(src, None, ASOF)
    b = build_ctx(_full_sources(), None, ASOF)
    a.pop("built"); b.pop("built")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ── 15. integration: real files, ≥500 tickers, < 30s ─────────────────────────

def test_integration_full_universe_real_files(tmp_path):
    """main() with NO --tickers against the real committed sources → the full
    universe bakes in well under the 30s render budget with ≥500 tickers."""
    import time
    required = [
        ROOT / "site" / "factordata" / "us_standouts.json",
        ROOT / "site" / "stagedata" / "screener.json",
    ]
    if not all(p.exists() for p in required):
        pytest.skip("committed source(s) absent in this environment")

    out = tmp_path / "portfolio_ctx.json"
    t0 = time.perf_counter()
    rc = main(["--asof", ASOF, "--out", str(out), "--root", str(ROOT)])
    elapsed = time.perf_counter() - t0
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "portfolio_ctx.v1"
    n = len(payload["tickers"])
    assert n >= 500, f"full universe should be ≥500 tickers, got {n}"
    assert elapsed < 30.0, f"bake must be < 30s (render budget), took {elapsed:.1f}s"
    json.dumps(payload, allow_nan=False)  # no NaN
    # sectors are keyed by GICS-family names only (no Yahoo residue)
    assert "Financial" not in payload["sectors"]
    assert "Information Technology" not in payload["sectors"]
