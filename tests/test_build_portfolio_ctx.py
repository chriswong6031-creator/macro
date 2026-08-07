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

PSI-W2 additions (charter §5.1/§6/§9 — schema portfolio_ctx.v2):
16. v1 ADDITIVITY golden — the v1 projection of a fully-covered v2 ticker is
    byte-identical (content AND key order) to the pinned v1 block; v1 top-level keys
    and v1 coverage counters do not drift.
17. `tech` — verbatim ext grade / MA booleans / RS numbers / drawdown (unrounded);
    census-dropped fields (atr_z, rvol63) stay ABSENT; washout state word only for the
    names the watcher lists, with no entry implication (DNR:KILL-WASHOUT-TURN).
18. `msens` / `fq` / `pers` / `dossier` — verbatim copies; fq counts fired flags and
    prints 0 as a measurement while an absent flags dict omits the block.
19. Omission honesty — a name with no stockdata emits NO v2 key at all.
20. Coverage counters per new block.
21. `market` — verbatim tape states, no derived/fused key, per-source fail-open, present
    and empty when every source is gone, corrupt shapes never raise.
22. W2 loaders fail open on an empty root; the stockdata reader is lazy, not materialized.
23. Gate-8 budget stamps are printed every run and a breach annotates at line start.
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

# The v2 contract surfaces, named once. `market` is the ONE top-level key W2 added
# (declared in scripts/export_signal_contracts.py, pinned by check_contract_drift);
# the five new coverage counters are the per-block honesty chips (§5.1).
TOP_LEVEL_KEYS = {"schema", "v", "asof", "built", "gate_go", "regime", "sectors",
                  "market", "coverage", "tickers"}
V1_COVERAGE_KEYS = {"tickers", "stage", "themes", "earnings", "insider", "congress",
                    "f13", "entry", "chains"}
W2_COVERAGE_KEYS = {"tech", "msens", "fq", "pers", "dossier"}
COVERAGE_KEYS = V1_COVERAGE_KEYS | W2_COVERAGE_KEYS
W2_TICKER_BLOCKS = ("tech", "msens", "fq", "pers", "dossier")


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
    assert p["schema"] == "portfolio_ctx.v2"
    assert p["v"] == 2
    assert p["asof"] == ASOF
    assert isinstance(p["built"], str) and p["built"].endswith("+00:00")
    assert set(p["coverage"]) == COVERAGE_KEYS
    assert isinstance(p["tickers"], dict)
    assert "gate_go" in p
    # top-level key set is FIXED (contract stability): full and empty bakes match
    assert set(p.keys()) == TOP_LEVEL_KEYS
    empty = {k: ({} if k != "congress" else None) for k in [
        "risk_state", "us_standouts", "subsector", "sector_central", "screener",
        "by_ticker", "insider", "smartmoney", "baskets", "membership", "congress"]}
    assert set(build_ctx(empty, ["NVDA"], ASOF).keys()) == TOP_LEVEL_KEYS


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
    # coverage counts everything present (chains: 0 — _full_sources has no chain_state;
    # the five W2 counters are 0 because _full_sources carries no stockdata either)
    assert p["coverage"] == {"tickers": 1, "stage": 1, "themes": 1, "earnings": 1, "chains": 0,
                             "insider": 1, "congress": 1, "f13": 1, "entry": 1,
                             "tech": 0, "msens": 0, "fq": 0, "pers": 0, "dossier": 0}


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
    assert p["schema"] == "portfolio_ctx.v2"
    assert p["tickers"] == {}          # zero-coverage → omitted
    assert p["gate_go"] is None        # gate_go absent → null (not fabricated False)
    # top-level regime/sectors are STABLE keys (empty dict, never dropped) so the
    # cross-repo contract does not drift when a source is empty
    assert p["regime"] == {}
    assert p["sectors"] == {}
    # W2: `market` is the same kind of STABLE top-level key — present and empty, never
    # dropped and never a fabricated neutral tape state.
    assert p["market"] == {}


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
    assert json.loads(s)["schema"] == "portfolio_ctx.v2"


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
    assert payload["schema"] == "portfolio_ctx.v2"
    assert payload["v"] == 2
    assert payload["asof"] == ASOF
    assert set(payload["coverage"]) == COVERAGE_KEYS
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
    assert payload["schema"] == "portfolio_ctx.v2"
    n = len(payload["tickers"])
    assert n >= 500, f"full universe should be ≥500 tickers, got {n}"
    assert elapsed < 30.0, f"bake must be < 30s (render budget), took {elapsed:.1f}s"
    json.dumps(payload, allow_nan=False)  # no NaN
    # sectors are keyed by GICS-family names only (no Yahoo residue)
    assert "Financial" not in payload["sectors"]
    assert "Information Technology" not in payload["sectors"]


# ══════════════════════════════════════════════════════════════════════════════
# PSI-W2 — v2 state blocks, the `market` tape block, coverage counts, budgets
# Charter: research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md §5.1/§6/§9.
#
# The law these pin: the bake is a JOIN. Every W2 value is VERBATIM from a nightly
# artifact — nothing thresholded, rounded, renamed, graded or blended — a block is
# OMITTED (not null-filled) when its source has no data for the name, and every v1 key
# survives byte-identically.
# ══════════════════════════════════════════════════════════════════════════════

# A stockdata blob shaped like the real site/stockdata/<T>.json (field names and value
# vocabulary taken verbatim from the 2026-08-06 census of the production artifacts).
def _stockdata_blob() -> dict:
    return {
        "ticker": "NVDA",
        "asof": "2026-08-06",
        "ext": {"ext": 11.8, "ext_z": -0.1, "grade": "stretched",
                "near_52wh": 0.919, "parabolic": False},
        "tech": {"above50": True, "above200": False, "rs_1m": -3.3, "rs_3m": 3.8,
                 "rs_6m": 0.8, "off_52w_high_pct": -8.1, "atr_pct": 2.99,
                 "hv20": 37.0, "price": 312.41, "rsi14": 47.0},
        "macro_sensitivity": {"tier": "high", "regime": "tailwind",
                              "regime_label": {"en": "rate tailwind", "zh": "利率顺风"},
                              "duration_label": {"en": "Duration-neutral", "zh": "久期中性"},
                              "rate_beta": -0.181},
        "thesis_funnel": {"state": "not_eligible", "flags": {
            "s1_dilution": {"fired": False, "computable": True},
            "s2_moat_falsifier": {"fired": True, "computable": True},
            "s3_solvency": {"fired": False, "computable": True},
            "s4_coverage": {"fired": True, "computable": True},
        }},
        "personality": {"schema": "stock_personality.v1",
                        "base": {"archetype": {"key": "quality_compounder",
                                               "confidence": 0.25}}},
    }


def _w2_sources() -> dict:
    """_full_sources() + every W2 source, all covering NVDA."""
    src = _full_sources()
    src["stockdata"] = {"NVDA": _stockdata_blob()}
    src["washout_turn"] = {"NVDA": {"state": "WASHOUT_TURN", "since": "2026-06-05",
                                    "depth_pctile": 43.9}}
    src["dossier_index"] = {"NVDA"}
    src["regime_latest"] = {
        "asof": "2026-08-05", "quad": "Q2", "quad_name": "Reflation",
        "cycle_tag": "mid", "transition_state": "TRANSITIONING",
        "liquidity_overlay": "contracting",
        "risk_radar": {"asof": "2026-08-05", "state": "caution",
                       "dominant_scare": "bubble", "cap_leadership": False,
                       "dominant_label_en": "Bubble / blow-off unwind",
                       "dominant_label_zh": "泡沫/见顶回吐",
                       "top_score": 67.0},
        "vol_regime": {"asof": "2026-08-03", "regime": "normalizing",
                       "ts_slope_state": "contango",
                       "vrp_state": "thin (vol underpriced — fragile)",
                       "vvix_state": "complacent", "fragility_confluence": 1},
    }
    src["dispersion"] = {"as_of": "2026-08-06", "state": "lean_in",
                         "dispersion_pctile": 0.82, "avg_corr": 0.07,
                         "label": "Selection pays — high dispersion",
                         "label_zh": "选股有效 — 高离散度"}
    src["rates_command"] = {"asof": "2026-08-05", "schema": "rates_command.v1",
                            "stance": {"en": "Easing pressure is building.",
                                       "zh": "宽松压力积聚。"}}
    src["group_flow"] = {"as_of": "2026-07-31",
                         "sectors": [{"id": "Energy", "name": "Energy",
                                      "name_zh": "能源", "stage": "emerging",
                                      "flow_score": 1.332}],
                         "baskets": [{"id": "ai_soft", "name": "AI Software",
                                      "name_zh": "AI软件", "stage": "confirmed",
                                      "flow_score": 1.283}]}
    src["subsector_rotation"] = {"asof": "2026-08-07", "sectors": [
        {"key": "XLY", "name": "Cons Discretionary", "name_zh": "可选消费",
         "quadrant": "improving", "rs_ratio": -0.25}]}
    src["covariance_spine"] = {"as_of": "2026-08-06", "blocks": {
        "factors": {"effective_factor_bets_pr": 2.5964},
        "dispersion": {"effective_universe_bets_pr": 21.79},
        "lobes": {"effective_independent_lobes": 1.0,
                  "same_bet_warning": {"active": False}}}}
    src["crossasset"] = {"asof": "2026-08-06", "regime": "mixed / no clear trend",
                         "correlation": "concentrated", "breadth": 0.31}
    return src


# ── 16. v1 ADDITIVITY: every v1 key survives byte-identically ─────────────────
# Gate 7: `portfolio_ctx` v2 is ADDITIVE — Terminal PR #170 and the shipped brain tool are
# built against v1. This is the golden: the v1 PROJECTION of a fully-covered v2 ticker
# (drop the five new keys) must equal the v1 block exactly, in the same key ORDER, and the
# v1 top-level keys must be untouched. A change here means additivity broke — fix the
# code, never this literal.

_V1_GOLDEN_NVDA = {
    "sector": "Technology",
    "themes": [{"id": "ai_soft", "name": "AI Software", "name_zh": "AI软件",
                "reco": "accumulate", "rank": 3, "lane": None}],
    "stage": {"n": 2, "label": "2A Breakout", "weeks": 8, "fresh": True},
    "entry": {"status": "buy_now", "act_level": 2, "urgency": "now",
              "label": "BUY ZONE", "state": "FRESH BUY"},
    "earnings": {"next": "2026-08-27", "days_to": 35},
    "insider": {"buyers": 2, "sellers": 5, "net_mn": -12.3, "bps": None},
    "congress": [{"side": "buy", "chamber": "house", "party": "R",
                  "tx_date": "2026-07-21", "filed": "2026-07-22",
                  "amount_mid": 8000.0}],
    "f13": {"holders": 7, "adds": 3, "trims": 1, "direction": "accumulating",
            "asof": "2026-03-31"},
}


def test_v1_blocks_are_byte_stable_under_v2():
    """The v1 projection of a fully-covered v2 ticker is byte-identical to the v1 golden."""
    v2 = build_ctx(_w2_sources(), ["NVDA"], ASOF)["tickers"]["NVDA"]
    projection = {k: v for k, v in v2.items() if k not in W2_TICKER_BLOCKS}
    # same content AND same key order → same bytes
    assert json.dumps(projection, ensure_ascii=False) == \
        json.dumps(_V1_GOLDEN_NVDA, ensure_ascii=False)
    # the v2 keys are strictly appended after the v1 ones
    assert list(v2)[:len(_V1_GOLDEN_NVDA)] == list(_V1_GOLDEN_NVDA)


def test_v1_top_level_keys_unchanged_by_v2():
    """v1 top-level keys keep their exact values whether or not the W2 sources exist."""
    v1_only = build_ctx(_full_sources(), ["NVDA"], ASOF)
    v2 = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    for k in ("gate_go", "regime", "sectors"):
        assert v1_only[k] == v2[k], f"v1 top-level key {k} drifted under v2"
    for k in V1_COVERAGE_KEYS:
        assert v1_only["coverage"][k] == v2["coverage"][k], \
            f"v1 coverage counter {k} drifted under v2"


# ── 17. tech block: verbatim join, no thresholding ───────────────────────────

def test_tech_block_verbatim_join():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    tech = p["tickers"]["NVDA"]["tech"]
    assert tech == {
        "ext": "stretched",                                  # ext.grade, verbatim word
        "ma": {"m50": True, "m200": False},                  # tech.above50 / above200
        "rs": {"m1": -3.3, "m3": 3.8, "m6": 0.8},            # tech.rs_1m/3m/6m, verbatim
        "dd252": -8.1,                                       # tech.off_52w_high_pct, NOT rounded
        "washout": "WASHOUT_TURN",                           # washout_turn state word
    }
    # census-dropped fields are ABSENT, never fabricated (no source prints them)
    for dropped in ("atr_z", "rvol63"):
        assert dropped not in tech


def test_tech_block_copies_the_grade_word_it_is_given():
    """No re-grading: whatever `ext.grade` says is what ships, including new vocabulary."""
    for word in ("intrend", "steady", "stretched", "parabolic", "some_future_grade"):
        src = _w2_sources()
        src["stockdata"]["NVDA"]["ext"]["grade"] = word
        assert build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]["ext"] == word


def test_tech_dd252_is_not_rounded():
    """§5.1 sketched a whole number; the source prints 1dp — the copy stays verbatim."""
    src = _w2_sources()
    src["stockdata"]["NVDA"]["tech"]["off_52w_high_pct"] = -29.47
    assert build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]["dd252"] == -29.47


def test_tech_partial_source_drops_only_the_missing_subkeys():
    src = _w2_sources()
    del src["stockdata"]["NVDA"]["tech"]["above200"]
    del src["stockdata"]["NVDA"]["tech"]["rs_6m"]
    src["stockdata"]["NVDA"]["ext"] = {}          # no grade
    tech = build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]
    assert "ext" not in tech
    assert tech["ma"] == {"m50": True}             # the present half survives alone
    assert tech["rs"] == {"m1": -3.3, "m3": 3.8}
    assert tech["dd252"] == -8.1


def test_washout_word_only_for_names_the_watcher_lists():
    """The watcher covers ~120 names; everyone else gets NO washout key (never 'none')."""
    src = _w2_sources()
    src["washout_turn"] = {}
    tech = build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]
    assert "washout" not in tech
    # and a name the watcher lists carries the state word VERBATIM, with no entry
    # implication tagging along (DNR:KILL-WASHOUT-TURN — display state only)
    src["washout_turn"] = {"NVDA": {"state": "TURN_WATCH", "weekly_cb": True,
                                    "depth_pctile": 11.9}}
    tech = build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]
    assert tech["washout"] == "TURN_WATCH"
    assert set(tech) <= {"ext", "ma", "rs", "dd252", "washout"}


# ── 18. msens / fq / pers / dossier ──────────────────────────────────────────

def test_msens_block_verbatim_and_bilingual():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["msens"] == {
        "rate_tier": "high",
        "read": {"en": "rate tailwind", "zh": "利率顺风"},
    }


def test_msens_omitted_without_the_source_block():
    src = _w2_sources()
    del src["stockdata"]["NVDA"]["macro_sensitivity"]
    assert "msens" not in build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]


def test_fq_counts_fired_flags_only():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["fq"] == {"flags": 2}   # s2_moat_falsifier + s4_coverage


def test_fq_zero_is_a_measurement_not_a_placeholder():
    """Covered-and-nothing-fired is 0; NO flags dict at all is an omitted block."""
    src = _w2_sources()
    for f in src["stockdata"]["NVDA"]["thesis_funnel"]["flags"].values():
        f["fired"] = False
    assert build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["fq"] == {"flags": 0}

    src = _w2_sources()
    del src["stockdata"]["NVDA"]["thesis_funnel"]
    assert "fq" not in build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]


def test_pers_archetype_verbatim():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["pers"] == {"arch": "quality_compounder"}
    src = _w2_sources()
    src["stockdata"]["NVDA"]["personality"] = {"base": {}}
    assert "pers" not in build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]


def test_dossier_flag_is_membership_only():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    assert p["tickers"]["NVDA"]["dossier"] is True
    src = _w2_sources()
    src["dossier_index"] = set()
    # absent → the key is GONE, never `false` (absence = "no dossier page", not a state)
    assert "dossier" not in build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]


# ── 19. omission honesty: a name with no stockdata emits NO v2 key ───────────

def test_ticker_without_stockdata_emits_no_v2_block():
    """The coverage-honesty law: absence is silence, never a null-filled block."""
    src = _w2_sources()
    src["stockdata"] = {}          # nobody covered
    src["washout_turn"] = {}
    src["dossier_index"] = set()
    blk = build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]
    for k in W2_TICKER_BLOCKS:
        assert k not in blk, f"{k} must be omitted when its source has no data"
    # ...and the v1 blocks are all still there
    assert set(blk) == set(_V1_GOLDEN_NVDA)


def test_mixed_coverage_across_tickers():
    """One covered name, one uncovered — each gets exactly what its sources support."""
    src = _w2_sources()
    src["insider"]["AAA"] = {"buyers": 1, "sellers": 0}   # v1-only coverage
    p = build_ctx(src, ["NVDA", "AAA"], ASOF)
    assert all(k in p["tickers"]["NVDA"] for k in W2_TICKER_BLOCKS)
    assert not any(k in p["tickers"]["AAA"] for k in W2_TICKER_BLOCKS)
    assert p["coverage"]["tech"] == 1 and p["coverage"]["dossier"] == 1


# ── 20. coverage counters for the new blocks ─────────────────────────────────

def test_w2_coverage_counts():
    p = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    for k in W2_COVERAGE_KEYS:
        assert p["coverage"][k] == 1, f"coverage.{k} should count the covered ticker"
    src = _w2_sources()
    src["stockdata"] = {}
    src["washout_turn"] = {}
    src["dossier_index"] = set()
    zero = build_ctx(src, ["NVDA"], ASOF)
    for k in W2_COVERAGE_KEYS:
        assert zero["coverage"][k] == 0


def test_w2_block_alone_is_desk_coverage():
    """A universe name whose ONLY read is a v2 block is included, not dropped."""
    src = {"stockdata": {"TECHONLY": _stockdata_blob()}}
    p = build_ctx(src, ["TECHONLY"], ASOF)
    assert "TECHONLY" in p["tickers"]
    assert p["coverage"]["tickers"] == 1


# ── 21. the `market` tape block (§9) ─────────────────────────────────────────

def test_market_block_verbatim_states():
    m = build_ctx(_w2_sources(), ["NVDA"], ASOF)["market"]
    assert m["regime"] == {"quad": "Q2", "quad_name": "Reflation", "cycle_tag": "mid",
                           "transition_state": "TRANSITIONING",
                           "liquidity_overlay": "contracting", "asof": "2026-08-05"}
    assert m["risk_radar"] == {"state": "caution", "dominant_scare": "bubble",
                               "label_en": "Bubble / blow-off unwind",
                               "label_zh": "泡沫/见顶回吐", "asof": "2026-08-05"}
    assert m["vol_regime"]["vrp_state"] == "thin (vol underpriced — fragile)"
    assert m["concentration"] == {"cap_leadership": False}
    assert m["dispersion"]["state"] == "lean_in"
    assert m["dispersion"]["label_en"] == "Selection pays — high dispersion"
    assert m["effective_bets"] == {"factor_bets": 2.5964, "universe_bets": 21.79,
                                   "lobes": 1.0, "same_bet_warning": False,
                                   "asof": "2026-08-06"}
    assert m["crossasset"]["regime"] == "mixed / no clear trend"
    assert m["rates"]["stance"] == {"en": "Easing pressure is building.",
                                    "zh": "宽松压力积聚。"}
    assert m["flow"]["sectors"] == [{"id": "Energy", "name": "Energy",
                                     "name_zh": "能源", "stage": "emerging"}]
    assert m["flow"]["baskets"][0]["id"] == "ai_soft"
    assert m["rotation"]["sectors"] == [{"key": "XLY", "name": "Cons Discretionary",
                                         "name_zh": "可选消费", "quadrant": "improving"}]


def test_market_block_carries_no_derived_state():
    """Composition only (MSP-R2): no fused/blended key beyond the per-home sub-blocks."""
    m = build_ctx(_w2_sources(), ["NVDA"], ASOF)["market"]
    assert set(m) == {"regime", "risk_radar", "vol_regime", "concentration",
                      "dispersion", "effective_bets", "crossasset", "rates",
                      "flow", "rotation"}


@pytest.mark.parametrize("drop,missing_keys", [
    ("regime_latest", ("regime", "risk_radar", "vol_regime", "concentration")),
    ("dispersion", ("dispersion",)),
    ("rates_command", ("rates",)),
    ("group_flow", ("flow",)),
    ("subsector_rotation", ("rotation",)),
    ("covariance_spine", ("effective_bets",)),
    ("crossasset", ("crossasset",)),
])
def test_market_block_fails_open_per_source(drop, missing_keys):
    """One dead source drops ONLY its own key — the rest of the tape still prints."""
    src = _w2_sources()
    src[drop] = {}
    m = build_ctx(src, ["NVDA"], ASOF)["market"]
    for k in missing_keys:
        assert k not in m, f"{k} must be omitted when {drop} is empty"
    assert m, "the surviving sources must still produce a market block"
    # the per-ticker join is untouched by a dead market source
    assert build_ctx(src, ["NVDA"], ASOF)["tickers"]["NVDA"]["tech"]["ext"] == "stretched"


def test_market_block_survives_corrupt_shapes():
    """Non-dict / non-list sources never raise — they just yield no key."""
    src = _w2_sources()
    src["regime_latest"] = {"risk_radar": "not-a-dict", "vol_regime": None}
    src["group_flow"] = {"sectors": "nope", "baskets": None}
    src["subsector_rotation"] = {"sectors": [None, {"no_quadrant": 1}]}
    src["covariance_spine"] = {"blocks": "nope"}
    m = build_ctx(src, ["NVDA"], ASOF)["market"]
    for k in ("risk_radar", "vol_regime", "concentration", "flow", "rotation",
              "effective_bets"):
        assert k not in m


def test_market_block_is_present_and_empty_when_every_source_is_gone():
    p = build_ctx(_full_sources(), ["NVDA"], ASOF)   # no W2 sources at all
    assert p["market"] == {}
    assert "market" in p


def test_market_block_determinism_and_no_nan():
    a = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    b = build_ctx(_w2_sources(), ["NVDA"], ASOF)
    a.pop("built"); b.pop("built")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    json.dumps(a, allow_nan=False)


# ── 22. loaders fail open (fresh worktree / missing render output) ────────────

def test_w2_loaders_fail_open_on_empty_root(tmp_path):
    from scripts.build_portfolio_ctx import (  # noqa: PLC0415
        load_stockdata, load_washout_turn, load_dossier_index, load_regime_latest,
        load_dispersion, load_rates_command, load_group_flow, load_subsector_rotation,
        load_covariance_spine, load_crossasset,
    )
    assert load_stockdata(tmp_path) == {}
    assert load_washout_turn(tmp_path) == {}
    assert load_dossier_index(tmp_path) == set()
    for fn in (load_regime_latest, load_dispersion, load_rates_command, load_group_flow,
               load_subsector_rotation, load_covariance_spine, load_crossasset):
        assert fn(tmp_path) == {}, f"{fn.__name__} must fail open to {{}}"


def test_stockdata_reader_is_lazy_and_fail_open(tmp_path):
    """The nightly reader parses one blob at a time and never raises on junk."""
    from scripts.build_portfolio_ctx import load_stockdata  # noqa: PLC0415
    d = tmp_path / "site" / "stockdata"
    d.mkdir(parents=True)
    (d / "NVDA.json").write_text(json.dumps(_stockdata_blob()), encoding="utf-8")
    (d / "BAD.json").write_text("{ not json", encoding="utf-8")
    (d / "LIST.json").write_text("[1,2,3]", encoding="utf-8")
    sd = load_stockdata(tmp_path)
    assert sd.get("NVDA")["ticker"] == "NVDA"
    assert sd.get("BAD") is None          # corrupt → None
    assert sd.get("LIST") is None         # non-dict → None
    assert sd.get("MISSING") is None      # absent file → None
    # it is a reader, not a materialized dict: nothing was loaded up front
    assert not hasattr(sd, "keys")


def test_washout_and_dossier_loaders_read_real_shapes(tmp_path):
    from scripts.build_portfolio_ctx import (  # noqa: PLC0415
        load_washout_turn, load_dossier_index,
    )
    d = tmp_path / "site" / "stockdata"
    d.mkdir(parents=True)
    (d / "washout_turn.json").write_text(json.dumps({
        "schema": "washout_turn.v1", "as_of": "2026-08-06",
        "tickers": {"ABT": {"state": "WASHOUT_TURN"}}}), encoding="utf-8")
    assert load_washout_turn(tmp_path) == {"ABT": {"state": "WASHOUT_TURN"}}
    s = tmp_path / "site" / "stocks"
    s.mkdir(parents=True)
    (s / "NVDA.html").write_text("<html>", encoding="utf-8")
    (s / "brk.b.html").write_text("<html>", encoding="utf-8")
    assert load_dossier_index(tmp_path) == {"NVDA", "BRK.B"}


# ── 23. gate-8 budget stamps are PRINTED by the bake ─────────────────────────

def test_bake_prints_budget_stamps(tmp_path, capsys):
    """Charter §0.8: the bake reports BOTH budgets in its log, every run."""
    from scripts.build_portfolio_ctx import BUDGET_SECONDS, BUDGET_BYTES  # noqa: PLC0415
    assert BUDGET_SECONDS == 60.0
    assert BUDGET_BYTES == 2.5 * 1024 * 1024
    rc = main(["--tickers", "NVDA", "--asof", ASOF,
               "--out", str(tmp_path / "ctx.json"), "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[portfolio_ctx budget]" in out
    line = next(ln for ln in out.splitlines() if ln.startswith("[portfolio_ctx budget]"))
    assert "/ 60s" in line and "/ 2.5 MB" in line
    assert "[portfolio_ctx coverage]" in out
    # under budget → no annotation; the guard only speaks on a breach
    assert "::warning" not in out


def test_budget_breach_emits_a_line_start_annotation(tmp_path, capsys, monkeypatch):
    """A breach must be VISIBLE in the Actions summary: bare print, line-start, flushed."""
    import scripts.build_portfolio_ctx as mod  # noqa: PLC0415
    monkeypatch.setattr(mod, "BUDGET_BYTES", 1)      # any artifact breaches
    monkeypatch.setattr(mod, "BUDGET_SECONDS", -1.0)
    rc = mod.main(["--tickers", "NVDA", "--asof", ASOF,
                   "--out", str(tmp_path / "ctx.json"), "--root", str(tmp_path)])
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    warns = [ln for ln in lines if "::warning" in ln]
    assert len(warns) == 2, "both the time and the size breach must annotate"
    for ln in warns:
        # the #3587 defect: a logger prefix ("WARNING ::warning …") makes GitHub drop it
        assert ln.startswith("::warning title=portfolio-ctx-budget::"), ln
