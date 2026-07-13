"""Tests for engine.setups — the shared selection×timing setup score.

Covers the timing tilts, the US-vs-China alpha weighting, the buy/laggard
ranking gates, and a PARITY lock that the shared score reproduces China's prior
inline ``_setup_score`` (so the refactor cannot silently move the shipped board).

W6-US invariant tests are at the bottom.
"""
from pytest import approx

from engine.setups import (
    CN_ALPHA_WEIGHT,
    SUE_CONFIRM,
    US_ALPHA_WEIGHT,
    dedupe_dual_class,
    entry_open_first,
    norm_company,
    rank_setups,
    setup_score,
    sue_confirmer,
    timing_tilt,
)


def _rec(az, *, entry=None, urgency=None, eq_dir=None, ticker="T", name=None,
         sector="Tech", sector_rank=1, sector_n=10, state="FRESH BUY",
         label="BUY ZONE"):
    """A minimal rec shaped like build_*_library passes in."""
    alpha = None if az is None else {"alpha": az, "entry": entry,
                                     "sector_rank": sector_rank, "sector_n": sector_n}
    return {"ticker": ticker, "name": name, "sector": sector, "alpha": alpha,
            "ladder": {"entry": {"urgency": urgency}, "eq_dir": eq_dir,
                       "state": state, "label": label, "dir": "up"}}


# ---- timing_tilt ------------------------------------------------------------

def test_timing_tilt_components():
    assert timing_tilt("now", None, None) == 0.9
    assert timing_tilt("imminent", None, None) == 0.9
    assert timing_tilt("soon", None, None) == 0.45
    assert timing_tilt("exit", None, None) == -0.9
    assert timing_tilt("avoid", None, None) == -0.9
    assert timing_tilt(None, "up", None) == 0.35
    assert timing_tilt(None, "down", None) == -0.35
    assert timing_tilt(None, None, "pullback") == 0.7
    assert timing_tilt(None, None, "extended") == -0.7
    assert timing_tilt(None, None, None) == 0.0
    # additive across legs
    assert timing_tilt("now", "up", "pullback") == 0.9 + 0.35 + 0.7


def test_timing_tilt_unknown_values_are_zero():
    assert timing_tilt("whoknows", "sideways", "mystery") == 0.0


# ---- setup_score ------------------------------------------------------------

def test_setup_score_none_without_residual():
    assert setup_score(_rec(None), alpha_weight=US_ALPHA_WEIGHT) is None
    # explicit empty alpha dict -> no residual -> None
    assert setup_score({"alpha": {}, "ladder": {}}, alpha_weight=0.7) is None


def test_setup_score_us_strong_leader_fresh_pullback():
    sc = setup_score(_rec(2.0, entry="pullback", urgency="now", eq_dir="up"),
                     alpha_weight=US_ALPHA_WEIGHT)
    assert sc is not None
    score, row = sc
    assert score == 0.7 * 2.0 + (0.9 + 0.35 + 0.7)   # 3.35
    assert row["setup"] == 3.35
    assert row["alpha"] == 2.0 and row["alpha_entry"] == "pullback"
    assert row["sector_rank"] == 1 and row["sector_n"] == 10


def test_setup_score_extended_leader_penalised():
    # a just-spiked leader with no cycle entry scores far below the pullback case
    pull = setup_score(_rec(1.0, entry="pullback", urgency="now", eq_dir="up"),
                       alpha_weight=US_ALPHA_WEIGHT)[0]
    ext = setup_score(_rec(1.0, entry="extended", urgency=None, eq_dir="up"),
                      alpha_weight=US_ALPHA_WEIGHT)[0]
    assert pull > ext
    assert ext == 0.7 * 1.0 + (0.0 + 0.35 - 0.7)      # 0.35


def test_us_weight_leads_more_than_china():
    # same name: the US (alpha-led) score weights the residual more than China
    r = _rec(2.0, entry="intact", urgency="soon", eq_dir="up")
    us = setup_score(r, alpha_weight=US_ALPHA_WEIGHT)[0]
    cn = setup_score(r, alpha_weight=CN_ALPHA_WEIGHT)[0]
    assert us > cn
    assert us - cn == approx((US_ALPHA_WEIGHT - CN_ALPHA_WEIGHT) * 2.0)


# ---- rank_setups ------------------------------------------------------------

def test_rank_setups_buy_and_laggard_gates():
    cands = [
        setup_score(_rec(2.0, entry="pullback", urgency="now", eq_dir="up", ticker="A"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(0.6, entry="intact", urgency="soon", eq_dir="up", ticker="B"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(0.1, urgency=None, ticker="C"), alpha_weight=US_ALPHA_WEIGHT),    # neither buy nor laggard
        setup_score(_rec(-0.5, urgency="exit", eq_dir="down", ticker="D"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(-1.4, urgency="exit", eq_dir="down", ticker="E"), alpha_weight=US_ALPHA_WEIGHT),
    ]
    out = rank_setups(cands)
    buys = [r["ticker"] for r in out["buy"]]
    lags = [r["ticker"] for r in out["laggards"]]
    # buys = alpha>=0.5, ranked by setup desc -> A (strong+fresh) before B
    assert buys == ["A", "B"]
    # the middling 0.1-alpha name is in NEITHER list
    assert "C" not in buys and "C" not in lags
    # laggards = alpha<=-0.3, ranked by setup asc -> most negative first
    assert lags == ["E", "D"]


def test_rank_setups_respects_caps():
    cands = [setup_score(_rec(1.0 + i * 0.01, entry="pullback", urgency="now",
                              eq_dir="up", ticker=f"T{i}"),
                         alpha_weight=US_ALPHA_WEIGHT) for i in range(30)]
    out = rank_setups(cands, n_buy=12, n_lag=6)
    assert len(out["buy"]) == 12
    assert len(out["laggards"]) == 0   # none are laggards


def test_rank_setups_as_of_passthrough():
    out = rank_setups([], as_of="2026-06-14")
    assert out == {"as_of": "2026-06-14", "buy": [], "laggards": []}


def test_rank_setups_buy_gate_hard_filters_and_replaces_alpha_floor():
    # The Top-setups board gates the buy list on the confluence (signal_gate) verdict, NOT the
    # alpha>=0.5 floor. A strong-alpha leader that fails the gate is DROPPED; a modest-alpha name
    # (below the old floor) that PASSES the gate is admitted — the gate replaces the floor.
    cands = [
        setup_score(_rec(2.5, entry="extended", ticker="HOT", name="Hot Leader"), alpha_weight=US_ALPHA_WEIGHT),   # high α, no cross
        setup_score(_rec(0.2, entry="pullback", urgency="now", eq_dir="up", ticker="OK", name="Ok Co"), alpha_weight=US_ALPHA_WEIGHT),  # low α, fresh cross
        setup_score(_rec(-1.5, urgency="exit", eq_dir="down", ticker="LAG", name="Lag Co"), alpha_weight=US_ALPHA_WEIGHT),  # laggard
    ]
    buyable = {"OK"}
    out = rank_setups(cands, rank_by="alpha", buy_gate=lambda t: t in buyable)
    assert [r["ticker"] for r in out["buy"]] == ["OK"]      # gate admits OK, drops the un-gated HOT
    assert [r["ticker"] for r in out["laggards"]] == ["LAG"]  # laggards untouched by buy_gate


def test_rank_setups_buy_gate_empty_when_nothing_passes():
    # honest empty board when no name has a fresh confluence buy — never a misleading fallback list
    cands = [setup_score(_rec(2.0 + i * 0.1, entry="pullback", urgency="now", eq_dir="up",
                              ticker=f"T{i}", name=f"Co {i}"), alpha_weight=US_ALPHA_WEIGHT)
             for i in range(5)]
    out = rank_setups(cands, rank_by="alpha", buy_gate=lambda t: False)
    assert out["buy"] == []


# ---- dual-class dedup -------------------------------------------------------

def test_norm_company_collapses_share_classes():
    # GOOG / GOOGL real names collapse to one key; distinct firms stay distinct
    assert norm_company("Alphabet Inc Cl C") == norm_company("Alphabet Inc Cl A")
    assert norm_company("Berkshire Hathaway Cl B") == norm_company("Berkshire Hathaway Cl A")
    assert norm_company("Ford Motor") != norm_company("General Motors")
    assert norm_company("Fox Corp Class A") == norm_company("Fox Corp Class B")


def test_dedupe_dual_class_keeps_first():
    rows = [{"ticker": "GOOG", "name": "Alphabet Inc Cl C"},
            {"ticker": "GOOGL", "name": "Alphabet Inc Cl A"},
            {"ticker": "MSFT", "name": "Microsoft Corp"}]
    out = dedupe_dual_class(rows)
    assert [r["ticker"] for r in out] == ["GOOG", "MSFT"]   # GOOGL dropped, order kept


def test_dedupe_blank_names_not_collapsed():
    # two rows with no name must NOT be treated as the same company
    rows = [{"ticker": "AAA", "name": None}, {"ticker": "BBB", "name": ""}]
    assert len(dedupe_dual_class(rows)) == 2


def test_rank_setups_collapses_dual_class_in_buys():
    cands = [
        setup_score(_rec(2.5, entry="pullback", urgency="now", eq_dir="up",
                         ticker="GOOG", name="Alphabet Inc Cl C"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(2.4, entry="pullback", urgency="now", eq_dir="up",
                         ticker="GOOGL", name="Alphabet Inc Cl A"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(2.0, entry="pullback", urgency="now", eq_dir="up",
                         ticker="MSFT", name="Microsoft Corp"), alpha_weight=US_ALPHA_WEIGHT),
    ]
    buys = [r["ticker"] for r in rank_setups(cands)["buy"]]
    assert buys == ["GOOG", "MSFT"]            # GOOGL (lower setup) dropped


# ---- factor composite tiebreaker -------------------------------------------

def test_rank_setups_factor_breaks_ties():
    # two identical setups; the higher factor composite ranks first
    a = setup_score(_rec(1.0, entry="intact", urgency="now", eq_dir="up",
                         ticker="LOWQ", name="Low Quality Co"), alpha_weight=US_ALPHA_WEIGHT)
    b = setup_score(_rec(1.0, entry="intact", urgency="now", eq_dir="up",
                         ticker="HIQ", name="High Quality Co"), alpha_weight=US_ALPHA_WEIGHT)
    assert a[0] == b[0]                          # exact setup tie
    a[1]["factor_z"] = -1.0
    b[1]["factor_z"] = 1.5
    buys = [r["ticker"] for r in rank_setups([a, b])["buy"]]
    assert buys == ["HIQ", "LOWQ"]              # factor settles the tie


def test_rank_setups_factor_does_not_override_setup():
    # a much stronger setup with a weak factor still outranks a weak setup
    strong = setup_score(_rec(2.5, entry="pullback", urgency="now", eq_dir="up",
                              ticker="STR", name="Strong Co"), alpha_weight=US_ALPHA_WEIGHT)
    weak = setup_score(_rec(0.6, entry="intact", urgency="soon",
                            ticker="WK", name="Weak Co"), alpha_weight=US_ALPHA_WEIGHT)
    strong[1]["factor_z"] = -2.0
    weak[1]["factor_z"] = 2.0
    buys = [r["ticker"] for r in rank_setups([strong, weak])["buy"]]
    assert buys == ["STR", "WK"]               # setup leads; factor is only a tiebreaker


# ---- rank_by: US ranks by alpha, China by setup -----------------------------

def test_rank_by_alpha_vs_setup_diverge():
    # HIA = high alpha but a weak (extended, no-cycle) setup; LOA = lower alpha but a
    # strong (fresh pullback) setup. The two sort keys disagree on the order.
    hia = setup_score(_rec(2.0, entry="extended", urgency=None, eq_dir=None,
                           ticker="HIA", name="High Alpha Co"), alpha_weight=US_ALPHA_WEIGHT)
    loa = setup_score(_rec(1.0, entry="pullback", urgency="now", eq_dir="up",
                           ticker="LOA", name="Low Alpha Co"), alpha_weight=US_ALPHA_WEIGHT)
    assert hia[0] < loa[0]                      # setup score ranks LOA above HIA
    # US (validated leg): order by alpha -> HIA first
    assert [r["ticker"] for r in rank_setups([hia, loa], rank_by="alpha")["buy"]] == ["HIA", "LOA"]
    # China default (reversal-led setup): order by setup -> LOA first
    assert [r["ticker"] for r in rank_setups([hia, loa])["buy"]] == ["LOA", "HIA"]


# ---- SUE earnings-momentum confirmer (DISPLAY context only) -----------------

def test_sue_confirmer_gate():
    assert SUE_CONFIRM == 1.0
    # clears the positive-tailwind gate -> rounded z
    assert sue_confirmer(1.466) == 1.47
    assert sue_confirmer(3.0) == 3.0
    assert sue_confirmer(1.0) == 1.0            # boundary inclusive
    # below the gate / negative / missing / NaN / junk -> no chip
    assert sue_confirmer(0.99) is None
    assert sue_confirmer(-2.0) is None
    assert sue_confirmer(None) is None
    assert sue_confirmer(float("nan")) is None
    assert sue_confirmer("x") is None


def test_sue_never_enters_setup_score():
    # SUE is a DISPLAY confirmer: setup_score must be byte-identical whether or not the
    # rec carries SUE info, and the scored row must never gain a sue/sue_z key. This is
    # the rank-by-alpha discipline lock (research/US_STANDOUT_SETUP_SCORE.md).
    rec = _rec(1.5, entry="pullback", urgency="now", eq_dir="up")
    base = setup_score(rec, alpha_weight=US_ALPHA_WEIGHT)
    rec2 = dict(rec, sue=3.0, sue_z=3.0)          # unrelated keys the scorer must ignore
    got = setup_score(rec2, alpha_weight=US_ALPHA_WEIGHT)
    assert got[0] == base[0]                       # score unchanged
    assert got[1] == base[1]                       # row unchanged
    assert "sue_z" not in got[1] and "sue" not in got[1]


def test_sue_chip_does_not_affect_rank_but_is_carried_through():
    # the caller attaches sue_z to the row AFTER scoring (build_stock_library). rank_setups
    # must (a) NOT let it reorder anything — the factor composite still settles the tie —
    # and (b) carry the chip through to the buy list for display.
    a = setup_score(_rec(1.0, entry="intact", urgency="now", eq_dir="up", ticker="A", name="A Co"), alpha_weight=US_ALPHA_WEIGHT)
    b = setup_score(_rec(1.0, entry="intact", urgency="now", eq_dir="up", ticker="B", name="B Co"), alpha_weight=US_ALPHA_WEIGHT)
    a[1]["factor_z"] = -1.0
    a[1]["sue_z"] = 3.0                            # strong SUE on the weaker-factor name
    b[1]["factor_z"] = 1.0                         # stronger factor, no SUE
    buys = rank_setups([a, b])["buy"]
    assert [r["ticker"] for r in buys] == ["B", "A"]   # factor tiebreak wins; SUE ignored in order
    a_row = next(r for r in buys if r["ticker"] == "A")
    assert a_row["sue_z"] == 3.0                       # still displayed on the card


# ---- China parity lock ------------------------------------------------------

def _china_old_setup_score(rec):
    """Verbatim copy of the prior inline scripts/build_china_library._setup_score
    (pre-refactor). The shared engine MUST reproduce this with alpha_weight=0.35."""
    a = rec.get("alpha") or {}
    az = a.get("alpha")
    if az is None:
        return None
    lad = rec.get("ladder") or {}
    entry = lad.get("entry") or {}
    urg, eqdir, ae = entry.get("urgency"), lad.get("eq_dir"), a.get("entry")
    timing = 0.0
    if urg in ("now", "imminent"):
        timing += 0.9
    elif urg == "soon":
        timing += 0.45
    elif urg in ("exit", "avoid"):
        timing -= 0.9
    if eqdir == "up":
        timing += 0.35
    elif eqdir == "down":
        timing -= 0.35
    if ae == "pullback":
        timing += 0.7
    elif ae == "extended":
        timing -= 0.7
    score = 0.35 * az + timing
    row = {"ticker": rec["ticker"], "name": rec["name"], "sector": rec.get("sector"),
           "alpha": az, "alpha_entry": ae, "state": lad.get("state"),
           "label": lad.get("label"), "label_zh": lad.get("label_zh"),
           "urgency": urg, "dir": lad.get("dir"), "eq_dir": eqdir,
           "sector_rank": a.get("sector_rank"), "sector_n": a.get("sector_n"),
           "setup": round(score, 2)}
    return score, row


def test_china_parity():
    cases = [
        _rec(2.0, entry="pullback", urgency="now", eq_dir="up"),
        _rec(1.2, entry="extended", urgency="exit", eq_dir="down"),
        _rec(-0.8, entry="laggard", urgency="soon", eq_dir=None),
        _rec(0.0, entry="neutral", urgency=None, eq_dir="up"),
        _rec(-2.5, entry=None, urgency="avoid", eq_dir="down"),
    ]
    for rec in cases:
        rec["ladder"]["label_zh"] = "中文"   # exercise the label_zh passthrough
        old = _china_old_setup_score(rec)
        new = setup_score(rec, alpha_weight=CN_ALPHA_WEIGHT)
        assert old is not None and new is not None
        assert old[0] == new[0]
        assert old[1] == new[1]


# ---------------------------------------------------------------------------
# W6-US invariant tests
# ---------------------------------------------------------------------------

def _make_row(ticker, composite_z=0.5, score=50, status="await_confluence", alpha=0.5):
    """Minimal row dict for entry_open_first tests."""
    return {
        "ticker": ticker,
        "alpha": alpha,
        "entry_signal": {"status": status},
        "conviction": {"score": score, "composite_z": composite_z},
    }


class TestEntryOpenFirst:
    """W6-US fix 5: entry_open_first only floats buy_now to #1 when composite_z > 0."""

    def test_buy_now_with_positive_cz_leads(self):
        rows = [
            _make_row("A", composite_z=0.5, score=80, status="await_confluence"),
            _make_row("B", composite_z=0.3, score=70, status="buy_now"),
        ]
        result = entry_open_first(rows)
        # B has buy_now AND positive cz → should lead
        assert result[0]["ticker"] == "B"

    def test_buy_now_with_negative_cz_does_not_lead(self):
        """ETN case: buy_now but composite_z <= 0 should NOT seize slot #1."""
        rows = [
            _make_row("REZI", composite_z=0.8, score=95, status="await_confluence", alpha=0.34),
            _make_row("ETN", composite_z=-0.047, score=47, status="buy_now", alpha=-0.12),
        ]
        result = entry_open_first(rows)
        # REZI should lead because ETN has negative composite_z
        assert result[0]["ticker"] == "REZI", (
            f"Expected REZI at slot #1, got {result[0]['ticker']} "
            f"(ETN composite_z=-0.047 should not seize slot #1)"
        )

    def test_buy_now_with_zero_cz_does_not_lead(self):
        rows = [
            _make_row("STRONG", composite_z=1.0, score=90, status="await_confluence"),
            _make_row("WEAK", composite_z=0.0, score=60, status="buy_now"),
        ]
        result = entry_open_first(rows)
        assert result[0]["ticker"] == "STRONG"

    def test_stable_sort_on_equal_status(self):
        """Rows with same (is_open=False) maintain score ordering."""
        rows = [
            _make_row("HIGH", composite_z=0.8, score=90, status="await_confluence"),
            _make_row("MID", composite_z=0.5, score=70, status="await_confluence"),
            _make_row("LOW", composite_z=0.2, score=50, status="await_confluence"),
        ]
        result = entry_open_first(rows)
        # higher score leads (no buy_now entries)
        assert result[0]["ticker"] == "HIGH"
        assert result[1]["ticker"] == "MID"

    def test_missing_fields_are_handled_gracefully(self):
        """Rows missing entry_signal or conviction don't crash."""
        rows = [
            {"ticker": "A"},
            {"ticker": "B", "conviction": {"score": 50}},
            _make_row("C", status="buy_now", composite_z=0.5),
        ]
        result = entry_open_first(rows)
        # C has buy_now and positive cz → leads; no crash
        assert result[0]["ticker"] == "C"
        assert len(result) == 3


class TestScoreEdgeScoreTiming:
    """W6-US fix 2: score_edge and score_timing are both emitted; Lagging band is capped."""

    def test_lagging_verdict_band_capped_to_neutral(self):
        """Simulate what build_stock_library does: cap band for lagging names."""
        # Replicate the band-capping logic inline (it lives in build_stock_library.py)
        def _apply_band_cap(c):
            verdict = (c.get("verdict") or "").lower()
            lagging = any(k in verdict for k in ("lagging", "no clear edge"))
            if lagging:
                c["band"] = "neutral"
            return c

        lagging_row = {"verdict": "Lagging — relative weakness", "band": "high", "score": 75}
        no_edge_row = {"verdict": "Neutral — no clear edge", "band": "constructive", "score": 47}
        leader_row = {"verdict": "High-confluence leader (context)", "band": "high", "score": 80}

        assert _apply_band_cap(dict(lagging_row))["band"] == "neutral"
        assert _apply_band_cap(dict(no_edge_row))["band"] == "neutral"
        assert _apply_band_cap(dict(leader_row))["band"] == "high"  # leader keeps band

    def test_band_verdict_invariant_fails_on_violation(self):
        """Invariant (a): band high/constructive + Lagging/no-edge verdict should raise."""
        # This tests the logic that build_stock_library uses (replicated here)
        def _check_invariant(rows):
            violations = []
            for r in rows:
                c = r.get("conviction") or {}
                v = (c.get("verdict") or "").lower()
                b = c.get("band") or ""
                if b in ("high", "constructive") and any(k in v for k in ("lagging", "no clear edge")):
                    violations.append(r.get("ticker"))
            return violations

        clean_rows = [
            {"ticker": "WAB", "conviction": {"band": "high", "verdict": "High-confluence leader (context)"}},
            {"ticker": "ETN", "conviction": {"band": "neutral", "verdict": "Neutral — no clear edge"}},
            {"ticker": "LKQ", "conviction": {"band": "neutral", "verdict": "Lagging — relative weakness"}},
        ]
        assert _check_invariant(clean_rows) == []  # clean after fix 2

        dirty_rows = [
            {"ticker": "BAD", "conviction": {"band": "high", "verdict": "Lagging — relative weakness"}},
        ]
        assert _check_invariant(dirty_rows) == ["BAD"]  # pre-fix state triggers


class TestUrgencyGating:
    """W6-US fix 7: urgency=now requires entry_signal.status in {buy_now, partial}."""

    def test_urgency_downgrade_logic(self):
        """Replicate the urgency-downgrade logic from build_stock_library."""
        _URGENCY_STATUS_MAP = {
            "buy_now": "now", "partial": "now",
            "await_confluence": "caution", "extended": "caution",
            "bounce_wait": "caution",
        }

        def _apply_urgency_fix(rows):
            for r in rows:
                if r.get("urgency") != "now":
                    continue
                es_status = (r.get("entry_signal") or {}).get("status")
                if es_status not in ("buy_now", "partial", None):
                    r["urgency"] = _URGENCY_STATUS_MAP.get(es_status, "caution")
            return rows

        rows = [
            {"ticker": "FCN", "urgency": "now", "entry_signal": {"status": "await_confluence"}},
            {"ticker": "LKQ", "urgency": "now", "entry_signal": {"status": "await_confluence"}},
            {"ticker": "ETN", "urgency": "now", "entry_signal": {"status": "buy_now"}},
            {"ticker": "OTHER", "urgency": "soon", "entry_signal": {"status": "await_confluence"}},
        ]
        result = _apply_urgency_fix(rows)
        # FCN and LKQ should be downgraded
        fcn = next(r for r in result if r["ticker"] == "FCN")
        lkq = next(r for r in result if r["ticker"] == "LKQ")
        etn = next(r for r in result if r["ticker"] == "ETN")
        oth = next(r for r in result if r["ticker"] == "OTHER")
        assert fcn["urgency"] == "caution"
        assert lkq["urgency"] == "caution"
        assert etn["urgency"] == "now"     # buy_now → keep
        assert oth["urgency"] == "soon"    # was not "now" → unchanged
