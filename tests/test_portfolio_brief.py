"""tests/test_portfolio_brief.py — portfolio_brief.v1 composer (Portfolio-Aware W1).

The composer (engine/portfolio_brief.py) is a pure function of (ctx, holdings, today,
generated_at). These tests run entirely on a synthetic portfolio_ctx.v1 fixture + the
charter's 3 synthetic books (§6): concentrated-semis, diversified-defensive,
single-name. Golden briefs are committed at tests/golden/portfolio_brief/<book>.json
and compared byte-exact (json.dumps sort_keys, fixed today/generated_at).

Covered (spec §Tests E):
  * Golden-file byte-exactness for the 3 books.
  * Weighting: positions-vs-equal + duplicate-ticker merge.
  * Stale weekday math (Fri asof → Mon today boundary).
  * Empty book (n==0) + zero-covered book (covered==0, n>0) headlines/empty sections.
  * Uncovered listing.
  * Section omission when a desk block is absent.
  * Cap rules (entry cap 4, congress cap 3, lanes cap 5).
  * zh present + non-empty on every line.
  * ADVERSARIAL: no composed en line (any golden book) matches an ask_brain advice
    pattern; "validated" appears nowhere.

The endpoint smoke tests (TestClient) live in the same file, guarded so they skip
cleanly when fastapi/httpx are unavailable (keeps the composer tests dependency-free).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.portfolio_brief import NOT_COMPUTED_KEYS, compose_brief  # noqa: E402

GOLDEN_DIR = ROOT / "tests" / "golden" / "portfolio_brief"
TODAY = "2026-07-23"          # a Thursday — fixed so golden output is deterministic
GENERATED_AT = "2026-07-23T14:00:00+00:00"
ASOF = "2026-07-23"


# ── synthetic portfolio_ctx.v1 fixture ───────────────────────────────────────
# Clean taxonomy: the per-ticker `sector` matches a key in `sectors` exactly, so the
# fixture exercises the stance join without the real-data alias reconciliation (which
# has its own dedicated unit test below). Vocabulary strings mirror the real artifact.

def _ctx() -> dict:
    return {
        "schema": "portfolio_ctx.v1",
        "v": 1,
        "asof": ASOF,
        "gate_go": False,
        "regime": {"us": {"score": 77, "verdict": "RISK_ON",
                          "label_en": "Risk-on", "label_zh": "风险偏好", "color": "green"}},
        "sectors": {
            "Technology": {"class": "neutral", "conviction_en": "Cautious",
                           "conviction_zh": "谨慎", "rotation_state": "bounce, not a turn"},
            "Energy": {"class": "entry_now", "conviction_en": "Cautious",
                       "conviction_zh": "谨慎", "rotation_state": "trend running"},
            "Financial": {"class": "headwind", "conviction_en": "Reduce",
                          "conviction_zh": "减配", "rotation_state": "extended — watch"},
            "Consumer Defensive": {"class": "tailwind", "conviction_en": "Accumulate",
                                   "conviction_zh": "积极配置", "rotation_state": "watching for entry"},
            "Utilities": {"class": "tailwind", "conviction_en": "Accumulate",
                          "conviction_zh": "积极配置"},  # no rotation_state → omit paren
        },
        "coverage": {"tickers": 7},
        "tickers": {
            "NVDA": {
                "sector": "Technology",
                "themes": [
                    {"id": "ai_semiconductors", "name": "AI Semiconductors",
                     "name_zh": "AI半导体", "reco": "accumulate", "rank": 19, "lane": None},
                    {"id": "mag7", "name": "Magnificent Seven",
                     "name_zh": "七巨头", "reco": "hold", "rank": 20, "lane": None},
                ],
                "stage": {"n": 2, "label": "2X Catch", "weeks": 13, "fresh": True},
                "entry": {"status": "bounce_wait", "act_level": 0, "urgency": "caution",
                          "label": "UNCONFIRMED TURN", "state": "COUNTERTREND BOUNCE"},
                "insider": {"buyers": 0, "sellers": 10, "net_mn": -787.26, "bps": -1.5},
                "congress": [
                    {"side": "buy", "chamber": "senate", "party": "R",
                     "tx_date": "2026-07-15", "filed": "2026-07-22", "amount_mid": 50001.0},
                    {"side": "sell", "chamber": "house", "party": "D",
                     "tx_date": "2026-07-10", "filed": "2026-07-18", "amount_mid": 1001.0},
                ],
                "f13": {"holders": 15, "adds": 6, "trims": 2, "direction": "accumulating",
                        "asof": "2026-06-30"},
            },
            "AVGO": {
                "sector": "Technology",
                "themes": [
                    {"id": "ai_semiconductors", "name": "AI Semiconductors",
                     "name_zh": "AI半导体", "reco": "accumulate", "rank": 19, "lane": None},
                ],
                "stage": {"n": 2, "label": "2X Catch", "weeks": 9, "fresh": True},
                "entry": {"status": "buy_now", "act_level": 2, "urgency": "now",
                          "label": "BUY ZONE", "state": "FRESH BREAKOUT"},
                "earnings": {"next": "2026-07-29", "days_to": 6},
                "insider": {"buyers": 1, "sellers": 3, "net_mn": -12.0, "bps": -0.2},
                "f13": {"holders": 12, "adds": 2, "trims": 5, "direction": "distributing",
                        "asof": "2026-06-30"},
            },
            "SMCI": {
                "sector": "Technology",
                "themes": [
                    {"id": "ai_semiconductors", "name": "AI Semiconductors",
                     "name_zh": "AI半导体", "reco": "accumulate", "rank": 19, "lane": None},
                ],
                "stage": {"n": 4, "label": "4 Decline", "weeks": 5, "fresh": False},
                "earnings": {"next": "2026-08-01", "days_to": 9},
                "insider": {"buyers": 2, "sellers": 2, "net_mn": 4.5, "bps": 0.1},
            },
            "XOM": {
                "sector": "Energy",
                "themes": [
                    {"id": "energy_complex", "name": "US Energy Complex",
                     "name_zh": "美国能源综合", "reco": "hold", "rank": 2, "lane": None},
                ],
                "stage": {"n": 2, "label": "2X Catch", "weeks": 37, "fresh": False},
                "earnings": {"next": "2026-08-07", "days_to": 15},
                "insider": {"buyers": 0, "sellers": 1, "net_mn": -2.4, "bps": None},
                "congress": [
                    {"side": "sell", "chamber": "house", "party": "D",
                     "tx_date": "2026-07-20", "filed": "2026-07-20", "amount_mid": 15001.0},
                ],
            },
            "JPM": {
                "sector": "Financial",
                "themes": [],
                "stage": {"n": 3, "label": "3 Top", "weeks": 6, "fresh": False},
                "insider": {"buyers": 0, "sellers": 4, "net_mn": -30.0, "bps": -0.1},
                "f13": {"holders": 20, "adds": 3, "trims": 8, "direction": "distributing",
                        "asof": "2026-06-30"},
            },
            "KO": {
                "sector": "Consumer Defensive",
                "themes": [],
                "stage": {"n": 1, "label": "1 Base", "weeks": 12, "fresh": False},
                "insider": {"buyers": 3, "sellers": 0, "net_mn": 8.0, "bps": 0.05},
            },
            "DUK": {
                "sector": "Utilities",
                "themes": [],
                "stage": {"n": 2, "label": "2X Catch", "weeks": 20, "fresh": False},
            },
        },
    }


# ── the charter's 3 synthetic books (§6) ─────────────────────────────────────

BOOKS = {
    # concentrated-semis: cost-basis weighted, heavy in Technology semis.
    "concentrated-semis": [
        {"ticker": "NVDA", "shares": 100, "entry_price": 120.0},
        {"ticker": "AVGO", "shares": 40, "entry_price": 300.0},
        {"ticker": "SMCI", "shares": 30, "entry_price": 40.0},
        {"ticker": "XOM", "shares": 20, "entry_price": 110.0},
    ],
    # diversified-defensive: equal-weighted watchlist (no shares/entry) across sectors,
    # incl. one uncovered name (FOO) to exercise the uncovered listing.
    "diversified-defensive": [
        {"ticker": "KO", "shares": None, "entry_price": None},
        {"ticker": "DUK", "shares": None, "entry_price": None},
        {"ticker": "JPM", "shares": None, "entry_price": None},
        {"ticker": "XOM", "shares": None, "entry_price": None},
        {"ticker": "FOO", "shares": None, "entry_price": None},
    ],
    # single-name: one position.
    "single-name": [
        {"ticker": "NVDA", "shares": 10, "entry_price": 100.0},
    ],
}


# The population each book actually came from (A8). The two cost-basis books are
# position books; diversified-defensive is the watchlist-union shape (no shares/entry on
# any row), so the goldens lock the disclosure on BOTH paths rather than only the one the
# happy path happens to take.
BOOK_POPULATION = {
    "concentrated-semis": "positions",
    "diversified-defensive": "watchlist_union",
    "single-name": "positions",
}


def _compose(book_key: str) -> dict:
    return compose_brief(_ctx(), BOOKS[book_key], TODAY, GENERATED_AT,
                         population=BOOK_POPULATION[book_key])


def _all_lines(brief: dict) -> list[dict]:
    out = [brief["headline"]]
    for s in brief.get("sections", []):
        out.extend(s.get("lines", []))
    return out


# ── golden-file byte-exactness ───────────────────────────────────────────────

@pytest.mark.parametrize("book", sorted(BOOKS))
def test_golden(book: str):
    got = _compose(book)
    golden_path = GOLDEN_DIR / f"{book}.json"
    assert golden_path.exists(), (
        f"golden missing: {golden_path} — regenerate with "
        f"scripts/_regen_portfolio_brief_goldens.py")
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    # Byte-exact via canonical dump (sort_keys) so key ordering can't cause a false diff.
    assert (json.dumps(got, sort_keys=True, ensure_ascii=False)
            == json.dumps(expected, sort_keys=True, ensure_ascii=False)), (
        f"{book} brief drifted from golden — if intentional, regenerate the golden file")


# ── weighting ────────────────────────────────────────────────────────────────

def test_positions_mode_cost_basis_weight():
    b = _compose("concentrated-semis")
    assert b["weighting"]["mode"] == "positions"
    assert b["weighting"]["label_en"] == "by cost basis"
    assert b["weighting"]["label_zh"] == "按成本权重"
    # NVDA 100*120=12000, AVGO 40*300=12000, SMCI 30*40=1200, XOM 20*110=2200
    # total 27400; Technology = (12000+12000+1200)/27400 ≈ 92%.
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    assert "92%" in exp["lines"][0]["en"]
    assert "Technology" in exp["lines"][0]["en"]


def test_equal_mode_watchlist():
    b = _compose("diversified-defensive")
    assert b["weighting"]["mode"] == "equal"
    assert b["weighting"]["label_en"] == "equal-weighted"
    assert b["weighting"]["label_zh"] == "等权"


def test_duplicate_ticker_merged_positions():
    holdings = [
        {"ticker": "NVDA", "shares": 50, "entry_price": 100.0},
        {"ticker": "nvda", "shares": 50, "entry_price": 100.0},  # dupe, lowercase
        {"ticker": "XOM", "shares": 100, "entry_price": 100.0},
    ]
    b = compose_brief(_ctx(), holdings, TODAY, GENERATED_AT)
    # 2 unique names; NVDA cost 10000, XOM 10000 → 50/50.
    assert b["book"]["n"] == 2
    assert b["weighting"]["mode"] == "positions"
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    # Technology (NVDA) and Energy (XOM) each 50% → tie broken by share desc then name;
    # both 50%, top is alphabetical-first sector "Energy".
    assert "50%" in exp["lines"][0]["en"]


def test_mixed_positions_and_watchlist_uses_positions():
    # Any row with shares>0 & entry>0 flips the whole book to positions mode.
    holdings = [
        {"ticker": "NVDA", "shares": 10, "entry_price": 100.0},
        {"ticker": "XOM", "shares": None, "entry_price": None},
    ]
    b = compose_brief(_ctx(), holdings, TODAY, GENERATED_AT)
    assert b["weighting"]["mode"] == "positions"
    # XOM carries 0 cost basis → NVDA is 100% of cost-weighted book.
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    assert "100%" in exp["lines"][0]["en"]


# ── stale weekday math ───────────────────────────────────────────────────────

def test_stale_false_same_day():
    assert _compose("single-name")["stale"] is False


def test_stale_friday_to_monday_not_stale():
    # asof Fri 2026-07-17, today Mon 2026-07-20 → 1 weekday gap (Sat/Sun skipped) → fresh.
    ctx = _ctx()
    ctx["asof"] = "2026-07-17"
    b = compose_brief(ctx, BOOKS["single-name"], "2026-07-20", GENERATED_AT)
    assert b["stale"] is False


def test_stale_two_weekdays_boundary():
    # asof Mon 2026-07-20, today Wed 2026-07-22 → exactly 2 weekdays → NOT stale (>2).
    ctx = _ctx()
    ctx["asof"] = "2026-07-20"
    assert compose_brief(ctx, BOOKS["single-name"], "2026-07-22", GENERATED_AT)["stale"] is False
    # today Thu 2026-07-23 → 3 weekdays → stale.
    assert compose_brief(ctx, BOOKS["single-name"], "2026-07-23", GENERATED_AT)["stale"] is True


def test_stale_friday_to_wednesday_is_stale():
    # asof Fri 2026-07-17, today Wed 2026-07-22 → Mon,Tue,Wed = 3 weekdays → stale.
    ctx = _ctx()
    ctx["asof"] = "2026-07-17"
    b = compose_brief(ctx, BOOKS["single-name"], "2026-07-22", GENERATED_AT)
    assert b["stale"] is True


# ── empty / zero-covered books ───────────────────────────────────────────────

def test_empty_book():
    b = compose_brief(_ctx(), [], TODAY, GENERATED_AT)
    assert b["book"] == {"n": 0, "covered": 0, "uncovered": []}
    assert b["sections"] == []
    assert "watchlist" in b["headline"]["en"].lower()
    assert b["headline"]["zh"]  # non-empty zh


def test_zero_covered_book():
    b = compose_brief(_ctx(), [{"ticker": "FOO"}, {"ticker": "BAR"}], TODAY, GENERATED_AT)
    assert b["book"]["n"] == 2
    assert b["book"]["covered"] == 0
    assert sorted(b["book"]["uncovered"]) == ["BAR", "FOO"]
    assert b["sections"] == []
    assert "coverage" in b["headline"]["en"].lower()
    assert b["headline"]["zh"]


def test_uncovered_listed():
    b = _compose("diversified-defensive")
    assert b["book"]["uncovered"] == ["FOO"]
    assert b["book"]["covered"] == 4


# ── section omission ─────────────────────────────────────────────────────────

def test_section_omitted_when_no_earnings_desk():
    # A book of names with NO earnings blocks → no earnings section.
    ctx = _ctx()
    for t in ctx["tickers"].values():
        t.pop("earnings", None)
    b = compose_brief(ctx, BOOKS["single-name"], TODAY, GENERATED_AT)
    keys = {s["key"] for s in b["sections"]}
    assert "earnings" not in keys


def test_regime_section_present_but_no_regime_block_omits_section():
    ctx = _ctx()
    ctx["regime"] = {}
    b = compose_brief(ctx, [{"ticker": "JPM"}], TODAY, GENERATED_AT)
    # JPM sector Financial is a headwind → regime section would still have a 2nd line;
    # but with no us block the first line is gone. It intersects a headwind so section
    # survives on the "leans against" line only.
    regime = [s for s in b["sections"] if s["key"] == "regime"]
    if regime:
        for ln in regime[0]["lines"]:
            assert "/100" not in ln["en"]  # no daily-read line without a score


def test_filings_section_omitted_when_no_filings():
    # DUK has no congress/insider/f13 → filings section absent for a DUK-only book.
    b = compose_brief(_ctx(), [{"ticker": "DUK"}], TODAY, GENERATED_AT)
    keys = {s["key"] for s in b["sections"]}
    assert "filings" not in keys


# ── cap rules ────────────────────────────────────────────────────────────────

def test_entry_reads_capped_at_4():
    # Build a ctx with 5 names all carrying an entry block.
    ctx = _ctx()
    base_entry = {"status": "buy_now", "act_level": 2, "urgency": "now",
                  "label": "BUY ZONE", "state": "FRESH"}
    for i, t in enumerate(["A1", "A2", "A3", "A4", "A5"]):
        ctx["tickers"][t] = {"sector": "Technology",
                             "entry": dict(base_entry, act_level=i),
                             "stage": {"n": 2, "fresh": False}}
    holdings = [{"ticker": t} for t in ["A1", "A2", "A3", "A4", "A5"]]
    b = compose_brief(ctx, holdings, TODAY, GENERATED_AT)
    sig = next(s for s in b["sections"] if s["key"] == "signals")
    entry_lines = [ln for ln in sig["lines"] if ln["en"].startswith(("A1", "A2", "A3", "A4", "A5"))]
    assert len(entry_lines) == 4


def test_congress_capped_at_3():
    ctx = _ctx()
    ctx["tickers"]["NVDA"]["congress"] = [
        {"side": "buy", "filed": f"2026-07-2{i}", "chamber": "house", "party": "R"}
        for i in range(0, 4)  # 4 rows all within 7 days of 2026-07-23
    ]
    b = compose_brief(ctx, [{"ticker": "NVDA"}], TODAY, GENERATED_AT)
    fil = next(s for s in b["sections"] if s["key"] == "filings")
    cong = [ln for ln in fil["lines"] if "Congress" in ln["en"]]
    assert len(cong) == 3


def test_lanes_capped_at_5():
    # 6 distinct held sectors → the "on the board" line lists at most 5.
    ctx = _ctx()
    ctx["sectors"]["Healthcare"] = {"class": "neutral", "conviction_en": "Neutral",
                                    "conviction_zh": "中性"}
    for i, (t, sec) in enumerate([("H1", "Technology"), ("H2", "Energy"),
                                  ("H3", "Financial"), ("H4", "Consumer Defensive"),
                                  ("H5", "Utilities"), ("H6", "Healthcare")]):
        ctx["tickers"][t] = {"sector": sec, "stage": {"n": 2, "fresh": False}}
    holdings = [{"ticker": t} for t in ["H1", "H2", "H3", "H4", "H5", "H6"]]
    b = compose_brief(ctx, holdings, TODAY, GENERATED_AT)
    lanes = next(s for s in b["sections"] if s["key"] == "lanes")
    board_line = lanes["lines"][0]["en"]
    # 5 of the 6 held sectors are listed; the 6th (lowest book weight) is capped out.
    # Count sector names present in the board line rather than " — " (a rotation_state
    # like "extended — watch" also contains " — ").
    all_secs = ["Technology", "Energy", "Financial", "Consumer Defensive",
                "Utilities", "Healthcare"]
    listed = [s for s in all_secs if s in board_line]
    assert len(listed) == 5


# ── bilingual completeness ───────────────────────────────────────────────────

@pytest.mark.parametrize("book", sorted(BOOKS))
def test_every_line_has_nonempty_zh_and_en(book: str):
    b = _compose(book)
    for ln in _all_lines(b):
        assert isinstance(ln.get("en"), str) and ln["en"].strip(), f"empty en in {book}: {ln}"
        assert isinstance(ln.get("zh"), str) and ln["zh"].strip(), f"empty zh in {book}: {ln}"
    for s in b["sections"]:
        assert s["title_en"].strip() and s["title_zh"].strip()


# ── sector-alias reconciliation (real-data taxonomy) ─────────────────────────

def test_sector_alias_reconciles_information_technology():
    # A held name carrying the stockdata taxonomy ("Information Technology") reads the
    # rotation board's "Technology" stance block, but keeps its own sector name.
    ctx = _ctx()
    ctx["tickers"]["NVDA"]["sector"] = "Information Technology"
    b = compose_brief(ctx, [{"ticker": "NVDA"}], TODAY, GENERATED_AT)
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    line = exp["lines"][0]["en"]
    assert "Information Technology" in line       # keeps the held name's sector
    assert "Cautious" in line                     # read the Technology block's stance


def test_sector_no_read_when_no_block_match():
    ctx = _ctx()
    ctx["tickers"]["NVDA"]["sector"] = "Mystery Sector"
    b = compose_brief(ctx, [{"ticker": "NVDA"}], TODAY, GENERATED_AT)
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    assert "no desk read" in exp["lines"][0]["en"].lower()


# ── v2 is ADDITIVE: the v1 contract both live clients read is intact ─────────

def test_v2_keeps_every_v1_key_the_live_clients_read():
    """v2 may only ADD. The terminal's PortfolioBriefPanel (via lib/portfolioBrief.ts)
    reads asof / generated_at / stale / weighting{mode,label_en,label_zh} /
    book{n,covered,uncovered} / headline{en,zh} / sections[{key,title_en,title_zh,
    lines[{en,zh}]}], and the Brain tool get_portfolio_brief returns the same payload
    verbatim. Dropping or retyping any of these breaks a shipped client, so the shape is
    pinned here rather than trusted to review."""
    for book in BOOKS:
        b = _compose(book)
        assert isinstance(b["asof"], str)
        assert isinstance(b["generated_at"], str)
        assert isinstance(b["stale"], bool)
        for k in ("mode", "label_en", "label_zh"):
            assert isinstance(b["weighting"][k], str)
        assert isinstance(b["book"]["n"], int)
        assert isinstance(b["book"]["covered"], int)
        assert isinstance(b["book"]["uncovered"], list)
        assert isinstance(b["headline"]["en"], str) and isinstance(b["headline"]["zh"], str)
        for s in b["sections"]:
            assert isinstance(s["key"], str)
            assert isinstance(s["title_en"], str) and isinstance(s["title_zh"], str)
            for ln in s["lines"]:
                assert isinstance(ln["en"], str) and isinstance(ln["zh"], str)


def test_v1_section_keys_are_unchanged():
    """The terminal re-asserts a canonical SECTION_ORDER over these keys; a renamed key
    would fall to the end of its panel instead of its designed slot."""
    seen = {s["key"] for book in BOOKS for s in _compose(book)["sections"]}
    assert seen <= {"exposure", "lanes", "signals", "regime", "earnings", "filings"}


def test_since_section_is_opt_in_so_live_clients_are_unaffected():
    """The `since` section only appears when a caller passes a prior digest. Neither live
    consumer does, so neither sees a section its SECTION_ORDER does not know."""
    from engine.portfolio_changes import snapshot_state  # noqa: PLC0415
    b = _compose("concentrated-semis")
    assert not any(s["key"] == "since" for s in b["sections"])
    prev = snapshot_state(_ctx(), ["NVDA"])
    with_prev = compose_brief(_ctx(), BOOKS["concentrated-semis"], TODAY, GENERATED_AT,
                              population="positions", previous=prev)
    assert with_prev["sections"][0]["key"] == "since"


# ── A8: population disclosure (W6) ───────────────────────────────────────────
# The program's founding defect was a surface describing one population while showing
# another. These pin the fix at the composer: the population is a first-class field, it
# is never guessed, and the prose agrees with it.

def test_population_is_a_first_class_field():
    b = _compose("concentrated-semis")
    pop = b["population"]
    assert pop["mode"] == "positions"
    assert pop["n"] == 4
    assert pop["label_en"] and pop["label_zh"]
    assert pop["disclosure_en"] and pop["disclosure_zh"]
    assert b["data"]["book"]["population"] == "positions"


def test_watchlist_population_uses_a8s_exact_label():
    """A8 mandates the wording for equal-weighted watchlist analysis, verbatim."""
    b = _compose("diversified-defensive")
    assert b["population"]["mode"] == "watchlist_union"
    assert b["population"]["label_en"] == "Watchlist structure — equal weighted"
    assert b["population"]["label_zh"] == "观察列表结构 — 等权"


def test_an_undeclared_population_says_so_rather_than_assuming_positions():
    """The whole point of A8: silence must be visible, not resolved to a default. A
    caller that forgets gets `unspecified` and a line that admits it — never a brief
    that calls an unknown set "your book"."""
    b = compose_brief(_ctx(), BOOKS["concentrated-semis"], TODAY, GENERATED_AT)
    assert b["population"]["mode"] == "unspecified"
    assert "not declared" in b["population"]["disclosure_en"]
    assert "your book" not in b["headline"]["en"].lower()


def test_summarizing_prose_never_calls_a_watchlist_a_book():
    """Every EN sentence that summarizes the set names the set. A watchlist population
    must not produce the phrase "your book" anywhere in the payload."""
    b = _compose("diversified-defensive")
    blob = json.dumps(b, ensure_ascii=False).lower()
    assert "your book" not in blob
    assert "你的持仓" not in json.dumps(b, ensure_ascii=False)
    # ...and the positive form is present.
    assert "your watchlist" in blob


def test_positions_book_still_reads_as_a_book():
    b = _compose("concentrated-semis")
    assert "your book" in b["headline"]["en"].lower()
    exp = next(s for s in b["sections"] if s["key"] == "exposure")
    assert "of your book is" in exp["lines"][0]["en"]


def test_every_in_repo_call_site_declares_its_population():
    """`unspecified` is the honest fallback for a caller who cannot know — it is NOT a
    licence for our own call sites to skip the argument. Every compose_brief( call in
    engine/ app/ scripts/ must pass population= explicitly. Derived by walking the tree,
    so a NEW call site is covered the day it lands rather than when someone remembers to
    update a list."""
    import ast as _ast  # noqa: PLC0415

    offenders: list[str] = []
    for base in ("engine", "app", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            try:
                tree = _ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.Call):
                    continue
                fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if fname != "compose_brief":
                    continue
                if not any(kw.arg == "population" for kw in node.keywords):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        "these compose_brief call sites do not declare a population (A8) — the brief "
        "would ship saying `unspecified`: %s" % offenders)


def test_population_and_weighting_are_independent_axes():
    """A positions population weighted equally (positions carrying no cost basis) must
    report population=positions AND weighting=equal — conflating the two axes is how the
    original confusion started."""
    holdings = [{"ticker": "NVDA", "shares": None, "entry_price": None},
                {"ticker": "XOM", "shares": None, "entry_price": None}]
    b = compose_brief(_ctx(), holdings, TODAY, GENERATED_AT, population="positions")
    assert b["population"]["mode"] == "positions"
    assert b["weighting"]["mode"] == "equal"


# ── v2 `data` block ──────────────────────────────────────────────────────────

def test_data_block_concentration_is_plain_arithmetic():
    b = _compose("concentrated-semis")
    conc = b["data"]["concentration"]
    # NVDA 12000, AVGO 12000, SMCI 1200, XOM 2200 → total 27400.
    assert conc["top_name_pct"] == 44          # 12000/27400
    assert conc["top3_pct"] == 96              # (12000+12000+2200)/27400
    assert 0 < conc["hhi"] <= 1
    assert conc["sectors"][0]["name"] == "Technology"


def test_data_block_omits_legs_it_cannot_see_rather_than_nulling_them():
    """PSI §5.2's posture/correlation/options/score legs need machinery this composer
    does not have. A null would read as "the desk abstained"; absence is the honest
    encoding, and the follow-up is named in the PR."""
    data = _compose("concentrated-semis")["data"]
    for absent in ("posture", "correlation", "options", "score", "tape"):
        assert absent not in data


def test_omission_is_declared_not_merely_silent():
    """Reviewer: omission-over-null is right, but invisible. Without `not_computed` a
    machine consumer cannot tell "this composer does not compute posture" from "posture
    computed empty" from "a proxy dropped the key"."""
    data = _compose("concentrated-semis")["data"]
    nc = data["not_computed"]
    assert set(nc["keys"]) == set(NOT_COMPUTED_KEYS)
    assert nc["reason_en"].strip() and nc["reason_zh"].strip()
    # The declared-absent keys really are absent — the disclosure cannot drift from fact.
    for key in nc["keys"]:
        assert key not in data


def test_concentration_declares_its_two_denominators():
    """G1. Sector shares partition the covered book and total 100; theme shares are over
    the THEMED part and a name in two themes counts in both, so they routinely exceed 100
    (the single-name golden reaches 200). A client that assumed one basis would render a
    144% stacked bar. Stating the basis is A8's own law one layer down."""
    conc = _compose("concentrated-semis")["data"]["concentration"]
    basis = conc["basis"]
    for k in ("sectors_en", "sectors_zh", "themes_en", "themes_zh"):
        assert basis[k].strip()
    assert sum(s["pct"] for s in conc["sectors"]) == 100
    # The over-100 case is real, and declared rather than "fixed" into a false 100.
    single = _compose("single-name")["data"]["concentration"]
    assert sum(t["pct"] for t in single["themes"]) > 100
    assert "need not total 100" in single["basis"]["themes_en"]


def test_cursor_scope_is_disclosed_on_the_brief_too():
    """B4 — the per-device limitation rides the payload, not just the PR body."""
    for book in BOOKS:
        cur = _compose(book)["data"]["cursor"]
        assert cur["scope"] == "device"
        assert cur["note_en"].strip() and cur["note_zh"].strip()


def test_every_response_carries_a_state_digest_even_on_a_degenerate_book():
    """A client stores the digest each visit; losing the cursor on an empty night would
    silently reset "since your last visit"."""
    for holdings in ([], [{"ticker": "ZZZZ"}]):
        b = compose_brief(_ctx(), holdings, TODAY, GENERATED_AT, population="positions")
        assert b["data"]["state_digest"]["schema"] == "portfolio_state_digest.v1"


# ── ADVERSARIAL: advice filter + validated ───────────────────────────────────

def test_no_line_matches_advice_filter():
    """Every composed line (en AND zh) across all 3 golden books must pass the
    ask_brain advice filter untouched by construction (spec §Tests E ADVERSARIAL)."""
    from engine.neuralweb.ask_brain import _ADVICE_PATTERNS  # noqa: PLC0415
    offenders: list[tuple[str, str, str]] = []
    for book in BOOKS:
        b = _compose(book)
        for ln in _all_lines(b):
            for field in ("en", "zh"):
                s = ln[field]
                for p in _ADVICE_PATTERNS:
                    if p.search(s):
                        offenders.append((book, p.pattern, s))
    assert not offenders, f"advice-filter matches: {offenders}"


def test_no_validated_anywhere():
    for book in BOOKS:
        b = _compose(book)
        blob = json.dumps(b, ensure_ascii=False).lower()
        assert "validated" not in blob
        assert "已验证" not in json.dumps(b, ensure_ascii=False)


# ── nothing prescriptive: no imperative second-person orders ─────────────────

def test_no_imperative_you_should():
    for book in BOOKS:
        b = _compose(book)
        for ln in _all_lines(b):
            low = ln["en"].lower()
            assert "you should" not in low
            assert "we recommend" not in low
            assert "price target" not in low


# ── endpoint smoke (guarded: skips when fastapi/httpx unavailable) ────────────

def _load_app_client(monkeypatch, tmp_path, *, tier="pro", status="active",
                     holdings=None, ctx=None, population="positions"):
    """Import app.main with a monkeypatched auth/tier/holdings/ctx and return a
    TestClient. Skips the test cleanly if fastapi/httpx aren't installed."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient  # noqa: PLC0415

    # Point REPO at a tmp dir carrying the ctx artifact on disk.
    repo = tmp_path
    (repo / "site" / "data").mkdir(parents=True, exist_ok=True)
    if ctx is not None:
        (repo / "site" / "data" / "portfolio_ctx.json").write_text(
            json.dumps(ctx, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("MACRO_REPO", str(repo))
    # Force a fresh import so REPO picks up the env var.
    for mod in list(sys.modules):
        if mod == "app.main" or mod.startswith("app.main."):
            del sys.modules[mod]
    import app.main as m  # noqa: PLC0415

    # Bypass Supabase auth: require_user returns a fixed user.
    m.app.dependency_overrides[m.require_user] = lambda: {"id": "u-test", "email": "t@x.co"}

    # Stub tier + holdings loaders on the module. The holdings loader returns
    # (rows, population) since W6 — the population is the loader's to report (A8).
    monkeypatch.setattr(m, "_portfolio_resolve_tier", lambda uid: {"tier": tier, "status": status})
    monkeypatch.setattr(m, "_portfolio_load_holdings",
                        lambda uid: ((holdings or []), population))

    client = TestClient(m.app)
    return m, client


def test_endpoint_200_pro(monkeypatch, tmp_path):
    ctx = _ctx()
    holdings = [{"ticker": "NVDA", "shares": 10, "entry_price": 100.0}]
    m, client = _load_app_client(monkeypatch, tmp_path, tier="pro", status="active",
                                 holdings=holdings, ctx=ctx)
    r = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema"] == "portfolio_brief.v2"
    assert body["book"]["n"] == 1
    # A8: the endpoint states the population it read, and it is the loader's answer.
    assert body["population"]["mode"] == "positions"
    assert body["data"]["book"]["population"] == "positions"
    assert r.headers.get("Cache-Control") == "private, no-store"
    m.app.dependency_overrides.clear()


def test_endpoint_reports_watchlist_population_when_that_is_what_it_read(monkeypatch, tmp_path):
    """The founding defect, pinned at the endpoint: a book loaded from WATCHLISTS must
    not come back describing positions. The loader reports `watchlist_union` and every
    summarizing string on the way out says so."""
    ctx = _ctx()
    holdings = [{"ticker": "NVDA", "shares": None, "entry_price": None},
                {"ticker": "XOM", "shares": None, "entry_price": None}]
    m, client = _load_app_client(monkeypatch, tmp_path, tier="pro", status="active",
                                 holdings=holdings, ctx=ctx,
                                 population="watchlist_union")
    r = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["population"]["mode"] == "watchlist_union"
    assert body["population"]["label_en"] == "Watchlist structure — equal weighted"
    assert "watchlist" in body["headline"]["en"].lower()
    assert "your book" not in body["headline"]["en"].lower()
    m.app.dependency_overrides.clear()


def test_endpoint_403_non_pro(monkeypatch, tmp_path):
    ctx = _ctx()
    m, client = _load_app_client(monkeypatch, tmp_path, tier="free", status="active",
                                 holdings=[], ctx=ctx)
    r = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["detail"]["error"] == "pro_required"
    assert body["detail"]["tier"] == "free"
    m.app.dependency_overrides.clear()


def test_endpoint_503_missing_ctx(monkeypatch, tmp_path):
    # No ctx written to disk → 503.
    m, client = _load_app_client(monkeypatch, tmp_path, tier="pro", status="active",
                                 holdings=[{"ticker": "NVDA"}], ctx=None)
    r = client.get("/api/portfolio/brief", headers={"Authorization": "Bearer x"})
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "ctx_unavailable"
    m.app.dependency_overrides.clear()
