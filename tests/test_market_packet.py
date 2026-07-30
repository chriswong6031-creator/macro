"""Live Market State Packet (engine.neuralweb.market_packet).

The packet is the brain's per-turn grounding: whatever it prints, the model will
state as current fact. So these pin the three things that make it trustworthy —

  1. the ARITHMETIC is the source's own (Yahoo's x10 yield convention, change in
     bp, the mean of index change percents) and a junk print is DROPPED rather
     than rendered,
  2. every rendered block carries its own as-of stamp and the header tells the
     truth about the tape's basis (live / delayed / last session's close), and
  3. a missing or corrupt source removes THAT block only — it never raises, never
     blanks the digest, and never borrows a neighbour's stamp.

Plus the two standing house rules: no numeric confidence ever reaches a prompt,
and the wire rail carries headlines/timestamps only (TI-R5 — no authored effect
or beneficiary chain in a brain feed).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.neuralweb import market_packet as mp

# ---------------------------------------------------------------------------
# Fixture plumbing
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)


def _write(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _q(price: float, chg: float | None = None, prev: float | None = None,
       delay: float = 1.0) -> dict:
    row: dict = {"price": price, "delayMin": delay, "basis": "regular"}
    if chg is not None:
        row["changePct"] = chg
    if prev is not None:
        row["prevClose"] = prev
    return row


def quotes_payload(asof: datetime | None = None, delay: float = 1.0) -> dict:
    """A full risk-off tape: every tracked group present, all four tenors, and
    numbers chosen so each divergence flag fires with round, checkable figures.
    Index mean is exactly -1.9%; 30Y is exactly +12.9bp."""
    return {
        "ts": int((asof or NOW).timestamp() * 1000),
        "asof": _iso(asof or (NOW - timedelta(minutes=2))),
        "source": "snapshot",
        "quotes": {
            "^GSPC": _q(6100.0, -1.7, delay=delay),
            "^IXIC": _q(19800.0, -2.2, delay=delay),
            "^DJI": _q(52210.0, -2.3, delay=delay),
            "^RUT": _q(2948.0, -1.4, delay=delay),
            "ES=F": _q(7448.0, -1.5, delay=delay),
            "NQ=F": _q(28161.0, -2.0, delay=delay),
            "^VIX": _q(21.4, 18.0, delay=delay),
            "CL=F": _q(81.98, 7.0, delay=delay),
            "BZ=F": _q(87.83, 6.5, delay=delay),
            "GC=F": _q(4076.3, 0.9, delay=delay),
            "HG=F": _q(6.39, -1.1, delay=delay),
            "SI=F": _q(58.675, 0.3, delay=delay),
            "DX-Y.NYB": _q(101.514, 0.6, delay=delay),
            "BTC-USD": _q(64503.03, -3.1, delay=delay),
            # Yahoo yield indexes as the spark feed actually delivers them:
            # the yield percent DIRECTLY (probed live from the VPS 2026-07-29 —
            # ^TNX 4.622 = 4.622%). The CBOE ×10 convention arrives only via
            # other paths and is normalized by _yield_pct scale detection
            # (covered by test_yield_scale_detection_handles_both_conventions).
            "^IRX": _q(4.20, prev=4.25, delay=delay),     # 4.2%,   -5bp
            "^FVX": _q(4.10, prev=4.05, delay=delay),     # 4.1%,   +5bp
            "^TNX": _q(4.692, prev=4.606, delay=delay),   # 4.692%, +8.6bp
            "^TYX": _q(5.00, prev=4.871, delay=delay),    # 5.0%,   +12.9bp
        },
    }


def risk_payload(*, open_: bool = True, stale: bool = False) -> dict:
    return {
        "schema": "risk_state.v1",
        "session": {"region": "us", "open": open_, "local_time": "2026-07-27 14:31 EDT"},
        "stale": stale,
        "stale_reason": "market closed" if stale else "",
    }


def breadth_payload() -> dict:
    return {
        "schema": "live.breadth.v1",
        "asof": _iso(NOW - timedelta(minutes=5)),
        "delay_min": 15,
        "session": "post",
        "tiers": [
            {"key": "large", "univ": "S&P 500", "adv": 322, "dec": 179,
             "adv_pct": 64.27, "nh": 33, "nl": 2},
            {"key": "mid", "univ": "S&P 400", "adv": 245, "dec": 155, "adv_pct": 61.25},
            {"key": "small", "univ": "S&P 600", "adv": 362, "dec": 239, "adv_pct": 60.23},
        ],
    }


def basket_pulse_payload(mode: str = "live", asof: object = "") -> dict:
    """Intraday basket pulse — the LEADERS source.

    Shaped so the selection has to work for its answer: four positive groups (only
    three may print), four negative (same), one exactly flat, and one honest
    coverage null. tape_rank is present but deliberately mis-ordered relative to
    the moves, because the block must sort on the number it PRINTS.
    """
    return {
        "schema": "basket_pulse.v1", "market": "us", "session": "rth", "mode": mode,
        "as_of_quotes": asof if asof != "" else _iso(NOW - timedelta(minutes=3)),
        "as_of_utc": _iso(NOW - timedelta(minutes=1)),
        "delay_min_median": 1.0, "coverage_pct": 99.4,
        "baskets": [
            {"id": "ai_semiconductors", "live_ew_chg_pct": 2.1, "tape_rank": 1},
            {"id": "us_sector_energy", "live_ew_chg_pct": 1.83, "tape_rank": 2},
            {"id": "power_grid", "live_ew_chg_pct": 1.2, "tape_rank": 3},
            {"id": "retail", "live_ew_chg_pct": 0.4, "tape_rank": 4},
            {"id": "big_pharma", "live_ew_chg_pct": 0.0, "tape_rank": 5},
            {"id": "insurance", "live_ew_chg_pct": None, "tape_rank": None},
            {"id": "housing", "live_ew_chg_pct": -0.35, "tape_rank": 6},
            {"id": "us_sector_utilities", "live_ew_chg_pct": -0.7, "tape_rank": 7},
            {"id": "us_sector_staples", "live_ew_chg_pct": -0.92, "tape_rank": 8},
            {"id": "memory_storage", "live_ew_chg_pct": -1.42, "tape_rank": 9},
        ],
    }


def drivers_payload(confidence: object = "medium") -> dict:
    return {
        "asof": "2026-07-24", "window_d": 5,
        "verdict": "clear", "verdict_zh": "明确",
        "primary_label": "Fed repricing", "primary_label_zh": "美联储重定价",
        "direction": "hawkish repricing, cuts priced out",
        "direction_zh": "鹰派重定价",
        "confidence": confidence, "confidence_zh": "中",
    }


def master_brief_payload() -> dict:
    return {
        "state_asof": "2026-07-28",
        "regime_read": "Goldilocks holds but growth cooled to the edge.",
        "summary": "The regime is fraying as AI stocks unwind.",
        "rotation_check": "The unwind leg of the liquidity playbook is running.",
        "forward_read": "The immediate hurdle is the FOMC decision.",
        "conflicts": ["Equity vs bonds: the stock tape is risk-on, bonds late-cycle."],
        "watch_items": ["FOMC (Jul 29): a hawkish surprise deepens the sell-off."],
        # forward_watch rows are DICTS in production, not strings.
        "forward_watch": [
            {"date": "2026-07-29", "label": "FOMC rate decision", "kind": "FOMC",
             "note": "A hawkish dot shift could amplify the tech sell-off."},
        ],
    }


def world_state_payload() -> dict:
    return {"regime": {"quad": "Q1", "quad_name": "Goldilocks", "label": "Q1",
                       "confidence": 0.183, "asof": "2026-07-28"}}


def rates_payload() -> dict:
    return {
        "schema": "rates_command.v1", "asof": "2026-07-28", "curve_regime_key": None,
        "board": {
            "rate_path_row": {"asof": "2026-07-28", "policy_rate": 3.63,
                              "implied_path": {"m1": 3.67, "m3": 3.84, "m12": 4.15}},
            "inflation_row": {"breakeven_10y": 2.2, "regime": "above target"},
            "risk_row": {"curve_regime_key": "bear_steepener",
                         "curve_regime_label_en": "Bear steepener",
                         "term_premium_dir": "rising"},
        },
    }


def vol_payload() -> dict:
    return {"schema": "vol_regime.v1", "asof": "2026-07-28",
            "snapshot": {"available": True, "asof": "2026-07-28",
                         "regime": "normalizing", "risk_score": 0.155,
                         "vix": 18.21, "ts_slope_state": "contango", "move": 76.1}}


def crossasset_payload() -> dict:
    return {"date": "2026-07-28", "asof": "2026-07-28",
            "regime": "mixed / no clear trend", "correlation": "concentrated",
            "favored": ["equity_us", "equity_sm", "copper", "dollar", "equity_intl"]}


def shock_payload(active: bool = True) -> dict:
    return {"schema": "shock_deescalation.v1", "active": active,
            "since": "2026-07-27", "expires": "2026-07-31",
            "note": "Shock de-escalation window: scores capped while the tape resets."}


def wires_payload(items: list[dict] | None = None) -> dict:
    if items is None:
        items = [
            {"id": "a", "ts": _iso(NOW - timedelta(minutes=20)), "en": "Fed holds rates",
             "zh": "美联储维持利率", "salience": 90, "class": "policy",
             "source_name": "wire", "corroboration": "2 sources"},
            {"id": "b", "ts": _iso(NOW - timedelta(minutes=10)),
             "en": "Chipmaker guides lower", "salience": 50, "class": "earnings"},
        ]
    return {"schema": "wires.v1", "updated_at": _iso(NOW), "items": items}


def make_root(tmp_path: Path, **overrides: object) -> Path:
    """Write the full source set into tmp_path. Pass name=None to omit a file."""
    live = tmp_path / "site" / "live"
    spec: dict[str, tuple[Path, object]] = {
        "quotes": (live / "quotes.json", quotes_payload()),
        "risk_state": (live / "risk_state.json", risk_payload()),
        "breadth": (live / "breadth.json", breadth_payload()),
        "basket_pulse": (live / "basket_pulse.json", basket_pulse_payload()),
        "market_drivers": (live / "market_drivers.json", drivers_payload()),
        "shock_state": (live / "shock_state.json", shock_payload()),
        "wires": (live / "wires.json", wires_payload()),
        "master_brief": (tmp_path / "site" / "master_brief.json", master_brief_payload()),
        "world_state": (tmp_path / "data" / "neuralweb" / "world_state.json",
                        world_state_payload()),
        "rates": (tmp_path / "data" / "rates_command" / "latest.json", rates_payload()),
        "vol": (tmp_path / "site" / "vol" / "regime.json", vol_payload()),
        "crossasset": (tmp_path / "data" / "crossasset" / "latest.json",
                       crossasset_payload()),
    }
    for name, (path, payload) in spec.items():
        if name in overrides:
            payload = overrides[name]
            if payload is None:
                continue
            if isinstance(payload, str):        # raw text => corrupt-file case
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
                continue
        _write(path, payload)
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_live_dir(monkeypatch, tmp_path):
    """Pin the live-dir ladder to the repo fallback and empty the digest cache, so
    a real $MACRO_LIVE_DIR or a live VPS mount can't reach into the tests."""
    monkeypatch.delenv(mp._LIVE_DIR_ENV, raising=False)
    monkeypatch.setattr(mp, "_VPS_LIVE_DIR", tmp_path / "__no_such_vps_dir__")
    mp._CACHE.clear()
    yield
    mp._CACHE.clear()


def _line(text: str, prefix: str) -> str:
    for line in text.split("\n"):
        if line.startswith(prefix):
            return line
    raise AssertionError(f"no line starting {prefix!r} in:\n{text}")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_renders_every_section_in_priority_order(tmp_path):
    root = make_root(tmp_path)
    text = mp.digest(root)

    assert text.split("\n")[0].startswith("[CURRENT DASHBOARD STATE —")
    heads = [ln.split(" (")[0].split(":")[0] for ln in text.split("\n")]
    for want in ("TAPE", "CURVE", "FLAGS", "SHOCK WINDOW", "EVENTS", "DRIVERS",
                 "RATES DESK", "VOL", "BREADTH", "LEADERS", "CROSS-ASSET",
                 "DESK READ", "WATCH"):
        assert want in heads, want
    # Priority order is the render order.
    order = [h for h in heads if h in ("TAPE", "CURVE", "FLAGS", "SHOCK WINDOW",
                                       "EVENTS", "DRIVERS", "RATES DESK", "VOL",
                                       "BREADTH", "LEADERS", "CROSS-ASSET",
                                       "DESK READ", "WATCH")]
    assert order == ["TAPE", "CURVE", "FLAGS", "SHOCK WINDOW", "EVENTS", "DRIVERS",
                     "RATES DESK", "VOL", "BREADTH", "LEADERS", "CROSS-ASSET",
                     "DESK READ", "WATCH"]


def test_tape_line_carries_every_group_with_its_stamp_and_basis(tmp_path):
    text = mp.digest(make_root(tmp_path))
    tape = _line(text, "TAPE (")
    assert re.match(r"^TAPE \(\d\d-\d\d \d\d:\d\dZ, live\): ", tape), tape
    body = tape.split("): ", 1)[1]
    assert body == (
        "SPX −1.7% · NDX −2.2% · DJI −2.3% · RUT −1.4% | ES −1.5% · NQ −2% "
        "| VIX 21.4 (+18%) | WTI +7% · Brent +6.5% · Gold +0.9% · Copper −1.1% "
        "· Silver +0.3% | DXY +0.6% | BTC −3.1%"
    ), body


def test_exact_flag_lines_and_curve_read(tmp_path):
    text = mp.digest(make_root(tmp_path))
    curve = _line(text, "CURVE (")
    assert curve.split("): ", 1)[1] == (
        "3M −5 · 5Y +5 · 10Y +8.6 · 30Y +12.9 "
        "→ bear steepener (long end selling off while the front end holds)"
    ), curve
    flags = _line(text, "FLAGS (")
    assert flags.split("): ", 1)[1] == (
        "stocks and long bonds down together (indices −1.9% avg, 30Y +12.9bp) "
        "· dollar and gold both up (DXY +0.6%, Gold +0.9%) "
        "· oil shock day (WTI +7%) "
        "· volatility spike (VIX +18%, now 21.4)"
    ), flags


def test_nightly_desk_lines_match_the_digest_they_replace(tmp_path):
    text = mp.digest(make_root(tmp_path))
    assert _line(text, "DRIVERS (") == (
        "DRIVERS (2026-07-24, 5d window): Fed repricing — hawkish repricing, "
        "cuts priced out (desk confidence: medium; attribution: clear)"
    )
    assert _line(text, "BREADTH (").split("): ", 1)[1] == (
        "S&P 500 64% advancing (322 adv / 179 dec) · S&P 400 61% · S&P 600 60% "
        "· 33 new highs / 2 new lows"
    )
    assert _line(text, "RATES DESK (") == (
        "RATES DESK (2026-07-28): policy 3.63% · implied path m3 3.84% "
        "· curve: bear steepener · 10Y breakeven 2.2% · term premium rising"
    )
    assert _line(text, "VOL (") == (
        "VOL (2026-07-28): normalizing — VIX 18.21, futures contango, MOVE 76.1"
    )
    assert _line(text, "CROSS-ASSET (") == (
        "CROSS-ASSET (2026-07-28): mixed / no clear trend "
        "· favored: US equity, small caps, copper · correlation concentrated"
    )
    assert _line(text, "DESK READ") == "DESK READ (2026-07-28)"
    assert "Cross-asset regime: Goldilocks" in text     # plain word, never the "Q1" code
    assert "Q1" not in text
    # forward_watch rows are dicts — they must read as prose, not a dict repr.
    ahead = _line(text, "Ahead: ")
    assert "2026-07-29 FOMC rate decision — A hawkish dot shift" in ahead
    assert "{" not in ahead and "'date'" not in ahead


def test_digest_stays_inside_the_default_budget(tmp_path):
    text = mp.digest(make_root(tmp_path))
    assert 0 < len(text) <= mp.DEFAULT_CHAR_BUDGET
    assert mp.DEFAULT_CHAR_BUDGET == 4200


# ---------------------------------------------------------------------------
# Curve: feed-scale normalization, sanity gate, label matrix
# ---------------------------------------------------------------------------

def test_yield_levels_and_bp_from_the_percent_direct_feed(tmp_path):
    """The production spark feed delivers percent directly; levels pass through
    unscaled and a bp move is the level difference × 100 (live.js:105 is the
    browser's reference formula). The shipped ÷10 (W1 diagnosis, 2026-07-29)
    rendered 10Y as 0.46% INSIDE the sanity band — silently wrong in every
    grounding turn — and understated bp moves 10×, so no curve FLAG could fire."""
    packet = mp.build_packet(make_root(tmp_path))
    tenors = packet["curve"]["tenors"]
    assert tenors["10Y"]["level_pct"] == pytest.approx(4.692)
    assert tenors["10Y"]["change_bp"] == pytest.approx(8.6)
    assert tenors["3M"]["level_pct"] == pytest.approx(4.2)
    assert tenors["3M"]["change_bp"] == pytest.approx(-5.0)
    assert tenors["30Y"]["change_bp"] == pytest.approx(12.9)
    assert packet["curve"]["front_tenor"] == "3M"
    assert packet["curve"]["long_tenor"] == "30Y"


def test_yield_scale_detection_handles_both_conventions(tmp_path):
    """Units are FEED-DEPENDENT (spark = percent-direct, /ws/tape relay = CBOE
    ×10) so _yield_pct scale-detects at >15, mirroring live.js tnxPct(). Both
    encodings of the same market must produce identical curve facts — including
    the exact numbers probed live from the VPS on 2026-07-29 (^TNX 4.622,
    prev 4.604 = +1.8bp)."""
    q = quotes_payload()
    q["quotes"]["^TNX"] = _q(4.622, prev=4.604)         # percent-direct (probe)
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    direct = packet["curve"]["tenors"]["10Y"]
    assert direct["level_pct"] == pytest.approx(4.622)
    assert direct["change_bp"] == pytest.approx(1.8)

    q = quotes_payload()
    q["quotes"]["^TNX"] = _q(46.22, prev=46.04)         # same market, ×10 units
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    x10 = packet["curve"]["tenors"]["10Y"]
    assert x10["level_pct"] == pytest.approx(4.622)
    assert x10["change_bp"] == pytest.approx(1.8)


def test_yield_scale_detection_is_pair_level_across_the_threshold(tmp_path):
    """A ×10 low-yield print can straddle the 15 threshold (1.45%/1.55% quotes
    as 14.5/15.5). Per-VALUE detection would normalize only the >15 side and
    fabricate a -1320bp junk move (dropped, tenor lost); pair-level detection
    (either value >15 → both ÷10) renders the truth: 1.45%, a real -10bp move.
    Peer-review note from the Analyst OS session, hardened one step further."""
    q = quotes_payload()
    q["quotes"]["^IRX"] = _q(14.5, prev=15.5)           # ×10 straddle pair
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    front = packet["curve"]["tenors"]["3M"]
    assert front["level_pct"] == pytest.approx(1.45)
    assert front["change_bp"] == pytest.approx(-10.0)
    assert not any("3M" in g for g in packet["gaps"])   # never junk-gated


def test_a_junk_tenor_move_is_dropped_and_noted(tmp_path):
    q = quotes_payload()
    q["quotes"]["^FVX"] = _q(60.5, prev=40.5)          # a 200bp "move"
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    assert "5Y" not in packet["curve"]["tenors"]
    assert "10Y" in packet["curve"]["tenors"]           # neighbours survive
    assert any("5Y" in g and "sanity" in g for g in packet["gaps"]), packet["gaps"]
    assert "5Y" not in mp.render_digest(packet)


def test_an_out_of_band_tenor_level_is_dropped(tmp_path):
    q = quotes_payload()
    q["quotes"]["^TNX"] = _q(0.0, prev=0.0)            # stale zero print
    q["quotes"]["^TYX"] = _q(250.0, prev=250.0)        # 25% — impossible
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    assert set(packet["curve"]["tenors"]) == {"3M", "5Y"}
    assert sum("sanity" in g for g in packet["gaps"]) == 2


@pytest.mark.parametrize("front_bp,long_bp,expect", [
    (-1.0, 10.0, "bear_steepener"),      # long end sells off
    (-8.0, -1.0, "bull_steepener"),      # front end rallies
    (10.0, 1.0, "bear_flattener"),       # front end sells off
    (-1.0, -8.0, "bull_flattener"),      # long end rallies
    (-5.0, 5.0, "bear_steepener"),       # both qualify -> the selling leg names it
    (1.0, 2.0, None),                    # inside the band
    (0.0, 3.0, None),                    # spread == +3 exactly, not > +3
    (0.0, -3.0, None),                   # spread == -3 exactly, not < -3
    (-1.5, 2.0, None),                   # steepening, but no leg moved enough
    (2.0, -1.5, None),                   # flattening, but no leg moved enough
    (None, 10.0, None),                  # a missing leg names nothing
    (10.0, None, None),
])
def test_curve_shape_matrix(front_bp, long_bp, expect):
    assert mp.curve_shape(front_bp, long_bp) == expect


def test_curve_falls_back_to_the_next_tenor_on_each_end(tmp_path):
    """Front = 3M else 5Y; long = 30Y else 10Y — the code handles any subset."""
    q = quotes_payload()
    del q["quotes"]["^IRX"]
    del q["quotes"]["^TYX"]
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    assert packet["curve"]["front_tenor"] == "5Y"
    assert packet["curve"]["long_tenor"] == "10Y"
    assert "10Y +8.6bp" in _line(mp.render_digest(packet), "FLAGS (")


def test_only_ten_year_present_still_renders(tmp_path):
    """Today's committed snapshot flows one tenor at most — no crash, no flag."""
    q = quotes_payload()
    for sym in ("^IRX", "^FVX", "^TYX"):
        del q["quotes"][sym]
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    assert set(packet["curve"]["tenors"]) == {"10Y"}
    assert packet["curve"]["front_tenor"] is None
    curve = _line(mp.render_digest(packet), "CURVE (")
    assert curve.endswith("10Y +8.6")           # no shape read without a front leg
    assert not any(f["name"] in mp._CURVE_GLOSS for f in packet["flags"])


def test_a_tenor_with_no_prior_close_never_rides_under_a_delta_header(tmp_path):
    q = quotes_payload()
    for sym in ("^IRX", "^FVX", "^TYX"):
        del q["quotes"][sym]
    q["quotes"]["^TNX"] = _q(46.92)             # price, no prevClose
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    curve = _line(mp.render_digest(packet), "CURVE (")
    assert "level): 10Y 4.692%" in curve and "Δbp" not in curve


# ---------------------------------------------------------------------------
# Divergence flags at their threshold edges
# ---------------------------------------------------------------------------

def _tape(indices=(), *, dxy=None, gold=None, wti=None, vix=None):
    block: dict = {"indices": [{"sym": "^GSPC", "label": "SPX", "change_pct": c}
                               for c in indices],
                   "futures": [], "commodities": [], "crypto": [],
                   "vix": None, "dollar": None, "asof": None}
    if dxy is not None:
        block["dollar"] = {"sym": "DX-Y.NYB", "label": "DXY", "change_pct": dxy}
    for sym, label, v in (("GC=F", "Gold", gold), ("CL=F", "WTI", wti)):
        if v is not None:
            block["commodities"].append({"sym": sym, "label": label, "change_pct": v})
    if vix is not None:
        block["vix"] = {"sym": "^VIX", "label": "VIX", "change_pct": vix, "price": 21.4}
    return block


def _curve(long_bp):
    return {"tenors": {"30Y": {"change_bp": long_bp, "level_pct": 5.0}},
            "front_tenor": None, "long_tenor": "30Y"}


def _names(flags):
    return {f["name"] for f in flags}


@pytest.mark.parametrize("mean_pct,long_bp,fires", [
    (-0.81, 4.1, True),
    (-0.8, 4.1, False),      # mean at the threshold, not below it
    (-0.81, 4.0, False),     # long bp at the threshold, not above it
    (-2.0, 12.9, True),
])
def test_stocks_and_long_bonds_both_down_edges(mean_pct, long_bp, fires):
    flags = mp._flags_block(_tape((mean_pct,)), _curve(long_bp))
    assert ("stocks_and_long_bonds_both_down" in _names(flags)) is fires


def test_stocks_and_long_bonds_needs_a_long_tenor():
    assert mp._flags_block(_tape((-2.0,)), None) == []


@pytest.mark.parametrize("dxy,gold,fires", [
    (0.51, 0.51, True), (0.5, 0.6, False), (0.6, 0.5, False), (0.6, -0.6, False),
])
def test_dollar_and_gold_both_up_edges(dxy, gold, fires):
    flags = mp._flags_block(_tape(dxy=dxy, gold=gold), None)
    assert ("dollar_and_gold_both_up" in _names(flags)) is fires


@pytest.mark.parametrize("wti,fires,direction", [
    (4.1, True, "up"), (4.0, False, None), (-4.1, True, "down"), (-3.9, False, None),
])
def test_oil_shock_day_edges_carry_direction(wti, fires, direction):
    flags = mp._flags_block(_tape(wti=wti), None)
    hit = [f for f in flags if f["name"] == "oil_shock_day"]
    assert bool(hit) is fires
    if fires:
        assert hit[0]["direction"] == direction
        assert "oil shock day" in mp._flag_text(hit[0])


@pytest.mark.parametrize("vix,fires", [(15.1, True), (15.0, False), (-20.0, False)])
def test_vix_spike_edges(vix, fires):
    assert ("vix_spike" in _names(mp._flags_block(_tape(vix=vix), None))) is fires


def test_a_quiet_tape_fires_nothing(tmp_path):
    q = quotes_payload()
    for sym, chg in (("^GSPC", 0.1), ("^IXIC", 0.2), ("^DJI", 0.1), ("^RUT", 0.3),
                     ("CL=F", 0.4), ("GC=F", 0.1), ("DX-Y.NYB", 0.1), ("^VIX", -2.0)):
        q["quotes"][sym]["changePct"] = chg
    for sym in ("^IRX", "^FVX", "^TNX", "^TYX"):
        q["quotes"][sym] = _q(q["quotes"][sym]["price"], prev=q["quotes"][sym]["price"])
    packet = mp.build_packet(make_root(tmp_path, quotes=q))
    assert packet.get("flags") is None
    assert "FLAGS" not in mp.render_digest(packet)


# ---------------------------------------------------------------------------
# Staleness law
# ---------------------------------------------------------------------------

def test_closed_market_says_last_session(tmp_path):
    text = mp.digest(make_root(tmp_path, risk_state=risk_payload(open_=False, stale=True)))
    assert "last session's tape (market closed)" in text.split("\n")[0]
    assert _line(text, "TAPE (").split(", ")[1].startswith("last session's tape")


def test_session_open_but_flagged_stale_still_says_closed(tmp_path):
    """risk_state.stale is authoritative on its own — an 'open' session whose feed
    the risk builder marked stale is not a live tape."""
    text = mp.digest(make_root(tmp_path, risk_state=risk_payload(open_=True, stale=True)))
    assert "last session's tape (market closed)" in text.split("\n")[0]


def test_delayed_basis_when_the_used_rows_are_old(tmp_path):
    root = make_root(tmp_path, quotes=quotes_payload(delay=152.2))
    text = mp.digest(root)
    assert "≈15-min delayed" in text.split("\n")[0]
    assert "≈15-min delayed" in _line(text, "TAPE (")
    assert mp._STALE_PREFIX not in text          # delayed is not the same as stale


def test_live_basis_when_fresh_and_open(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    assert packet["basis"] == "live"
    assert packet["stale_warn"] is False


def test_stale_during_an_open_session_prefixes_the_tape(tmp_path):
    """A 'live'-basis file that stopped updating is the dangerous case: the rows
    look current and are not."""
    old = quotes_payload(asof=NOW - timedelta(minutes=90))
    old["asof"] = _iso(NOW - timedelta(minutes=90))
    packet = mp.build_packet(make_root(tmp_path, quotes=old))
    assert packet["basis"] == "live" and packet["stale_warn"] is True
    text = mp.render_digest(packet)
    assert _line(text, mp._STALE_PREFIX).startswith(
        "STALE — treat as last known, not current: TAPE (")


def test_a_closed_market_is_not_double_flagged_as_stale(tmp_path):
    old = quotes_payload(asof=NOW - timedelta(minutes=900))
    old["asof"] = _iso(NOW - timedelta(minutes=900))
    packet = mp.build_packet(
        make_root(tmp_path, quotes=old, risk_state=risk_payload(open_=False)))
    assert packet["stale_warn"] is False
    assert mp._STALE_PREFIX not in mp.render_digest(packet)


def test_no_tape_at_all_says_so_in_the_header(tmp_path):
    text = mp.digest(make_root(tmp_path, quotes=None))
    assert "nightly desk state, no live tape" in text.split("\n")[0]
    assert "TAPE" not in text and "CURVE" not in text
    assert "DESK READ" in text                   # the nightly blocks still ride


def test_every_rendered_section_carries_a_stamp(tmp_path):
    text = mp.digest(make_root(tmp_path))
    stamp = re.compile(r"\((\d{4}-\d\d-\d\d|\d\d-\d\d \d\d:\d\dZ)")
    for line in text.split("\n"):
        head = line.split(":")[0]
        if not head.isupper() or head.startswith("["):
            continue
        if line.startswith("EVENTS"):
            assert re.search(r"\d\d:\d\d UTC", line), line     # per-item stamps
            continue
        if line.startswith("SHOCK WINDOW"):
            assert "2026-07-27 → 2026-07-31" in line
            continue
        assert stamp.search(line), line


def test_stamp_shapes():
    assert mp._stamp("2026-07-27T22:32:09.883727+00:00") == "07-27 22:32Z"
    assert mp._stamp("2026-07-27T21:19:20Z") == "07-27 21:19Z"
    assert mp._stamp("2026-07-27 22:31:49 UTC") == "07-27 22:31Z"
    assert mp._stamp("2026-07-28") == "2026-07-28"
    assert mp._stamp(None) == ""


# ---------------------------------------------------------------------------
# Fail-soft: one source per case, missing then corrupt
# ---------------------------------------------------------------------------

_SOURCES = [
    ("quotes", "TAPE ("), ("breadth", "BREADTH ("), ("market_drivers", "DRIVERS ("),
    ("shock_state", "SHOCK WINDOW ("), ("wires", "EVENTS ("),
    ("rates", "RATES DESK ("), ("vol", "VOL ("), ("crossasset", "CROSS-ASSET ("),
    ("basket_pulse", "LEADERS ("), ("world_state", "Cross-asset regime:"),
]


@pytest.mark.parametrize("name,marker", _SOURCES)
@pytest.mark.parametrize("bad", [None, "{not json", "[]", '{"quotes": null}'])
def test_a_missing_or_corrupt_source_only_removes_its_own_section(tmp_path, name,
                                                                 marker, bad):
    root = make_root(tmp_path, **{name: bad})
    text = mp.digest(root)                       # must not raise
    assert marker not in text
    # Every OTHER section still renders.
    for other, other_marker in _SOURCES:
        if other != name:
            assert other_marker in text, other
    assert "CURRENT DASHBOARD STATE" in text


def test_a_corrupt_master_brief_falls_through_to_the_regime_copy(tmp_path):
    root = make_root(tmp_path, master_brief="{not json")
    _write(root / "data" / "regime" / "master_brief.json", master_brief_payload())
    text = mp.digest(root)
    assert "DESK READ (2026-07-28)" in text and "WATCH (2026-07-28)" in text


def test_both_master_brief_copies_absent_keeps_the_rest(tmp_path):
    text = mp.digest(make_root(tmp_path, master_brief=None))
    assert "WATCH (" not in text
    assert "TAPE (" in text and "Cross-asset regime: Goldilocks" in text
    # The nightly prose is gone but the regime label remains, so DESK READ must
    # stand on the world_state's OWN as-of rather than an empty stamp.
    assert _line(text, "DESK READ") == "DESK READ (2026-07-28)"
    assert "Regime:" not in text and "Rotation:" not in text


def test_a_world_state_without_an_asof_is_not_stamped_with_a_guess(tmp_path):
    ws = {"regime": {"quad_name": "Goldilocks"}}
    text = mp.digest(make_root(tmp_path, master_brief=None, world_state=ws))
    assert _line(text, "DESK READ") == "DESK READ"
    assert "Cross-asset regime: Goldilocks" in text


def test_an_inactive_shock_window_is_not_a_fact_about_now(tmp_path):
    text = mp.digest(make_root(tmp_path, shock_state=shock_payload(active=False)))
    assert "SHOCK" not in text


def test_build_packet_never_raises_on_hostile_input(tmp_path):
    for payload in ("", "null", "[1,2,3]", '{"quotes": 5}', '{"tiers": "x"}'):
        root = tmp_path / f"r{abs(hash(payload))}"
        for rel in ("site/live/quotes.json", "site/live/breadth.json",
                    "site/live/market_drivers.json", "site/live/risk_state.json",
                    "site/live/shock_state.json", "site/live/wires.json",
                    "site/master_brief.json", "data/neuralweb/world_state.json",
                    "data/rates_command/latest.json", "site/vol/regime.json",
                    "data/crossasset/latest.json"):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
        packet = mp.build_packet(root)
        assert isinstance(packet, dict)
        assert isinstance(mp.render_digest(packet), str)


def test_empty_world_renders_nothing(tmp_path):
    assert mp.digest(tmp_path) == ""
    assert mp.render_digest({}) == ""
    assert mp.render_digest({"gaps": ["x"], "basis": "live"}) == ""
    assert mp.render_digest(None) == ""          # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live-dir resolution ladder
# ---------------------------------------------------------------------------

def test_live_dir_env_override_wins(tmp_path, monkeypatch):
    vps = tmp_path / "vps"
    vps.mkdir()
    override = tmp_path / "override"
    monkeypatch.setattr(mp, "_VPS_LIVE_DIR", vps)
    monkeypatch.setenv(mp._LIVE_DIR_ENV, str(override))
    assert mp._live_dir(tmp_path / "root") == override


def test_live_dir_uses_the_vps_path_only_when_it_exists(tmp_path, monkeypatch):
    root = tmp_path / "root"
    vps = tmp_path / "vps"
    monkeypatch.delenv(mp._LIVE_DIR_ENV, raising=False)
    monkeypatch.setattr(mp, "_VPS_LIVE_DIR", vps)
    assert mp._live_dir(root) == root / "site" / "live"      # absent -> fallback
    vps.mkdir()
    assert mp._live_dir(root) == vps


def test_live_dir_falls_back_to_the_repo_checkout(tmp_path, monkeypatch):
    monkeypatch.delenv(mp._LIVE_DIR_ENV, raising=False)
    monkeypatch.setattr(mp, "_VPS_LIVE_DIR", tmp_path / "nope")
    assert mp._live_dir(tmp_path) == tmp_path / "site" / "live"


def test_the_ladder_is_what_actually_reads_the_live_files(tmp_path, monkeypatch):
    """Not just resolvable — the override dir must be where the quotes come from."""
    root = make_root(tmp_path, quotes=None, breadth=None)
    override = tmp_path / "vps_live"
    _write(override / "quotes.json", quotes_payload())
    _write(override / "breadth.json", breadth_payload())
    monkeypatch.setenv(mp._LIVE_DIR_ENV, str(override))
    mp._CACHE.clear()
    text = mp.digest(root)
    assert "TAPE (" in text and "BREADTH (" in text


def test_wires_falls_back_to_the_repo_press_sink(tmp_path):
    root = make_root(tmp_path, wires=None)
    _write(root / "data" / "marketing" / "press" / "wires.json", wires_payload())
    assert "EVENTS (live wire): " in mp.digest(root)


# ---------------------------------------------------------------------------
# EVENTS wire
# ---------------------------------------------------------------------------

def test_events_order_by_salience_then_recency_and_cap_at_three(tmp_path):
    items = [
        {"id": "low", "ts": _iso(NOW - timedelta(minutes=1)), "en": "Low salience",
         "salience": 10},
        {"id": "top", "ts": _iso(NOW - timedelta(minutes=50)), "en": "Top salience",
         "salience": 90},
        {"id": "mid", "ts": _iso(NOW - timedelta(minutes=30)), "en": "Mid salience",
         "salience": 50},
        {"id": "old", "ts": _iso(NOW - timedelta(minutes=90)), "en": "Older tie",
         "salience": 50},
        {"id": "x", "ts": _iso(NOW - timedelta(minutes=5)), "en": "No salience"},
    ]
    line = _line(mp.digest(make_root(tmp_path, wires=wires_payload(items))), "EVENTS ")
    assert line.count(" · ") == 2                       # exactly three items
    assert [t for t in ("Top salience", "Mid salience", "Older tie", "Low salience")
            if t in line] == ["Top salience", "Mid salience", "Older tie"]
    assert line.index("Top salience") < line.index("Mid salience") < line.index("Older")


def test_events_drops_anything_past_the_freshness_window(tmp_path):
    items = [
        {"id": "fresh", "ts": _iso(NOW - timedelta(hours=11)), "en": "Inside window",
         "salience": 10},
        {"id": "stale", "ts": _iso(NOW - timedelta(hours=13)), "en": "Outside window",
         "salience": 99},
    ]
    text = mp.digest(make_root(tmp_path, wires=wires_payload(items)))
    assert "Inside window" in text and "Outside window" not in text


def test_events_section_is_omitted_when_nothing_is_live(tmp_path):
    for payload in (wires_payload([]),
                    wires_payload([{"id": "s", "ts": _iso(NOW - timedelta(hours=48)),
                                    "en": "Ancient", "salience": 99}]),
                    wires_payload([{"id": "n", "ts": _iso(NOW), "en": ""}])):
        mp._CACHE.clear()
        assert "EVENTS" not in mp.digest(make_root(tmp_path, wires=payload))


def test_events_headline_is_truncated_to_ninety_chars(tmp_path):
    long_en = "Fed officials signal a longer hold as core inflation stays sticky " \
              "and the labour market cools more slowly than expected this quarter"
    assert len(long_en) > mp.EVENTS_TEXT_CHARS
    items = [{"id": "a", "ts": _iso(NOW), "en": long_en, "salience": 50}]
    line = _line(mp.digest(make_root(tmp_path, wires=wires_payload(items))), "EVENTS ")
    rendered = line.split(" UTC ", 1)[1]
    assert len(rendered) <= mp.EVENTS_TEXT_CHARS
    assert rendered.endswith("…")
    assert rendered[:40] == long_en[:40]


def test_events_carries_headline_and_stamp_only(tmp_path):
    """TI-R5: an authored effect / beneficiary chain must never enter a brain feed,
    even when the wire item happens to carry one."""
    items = [{"id": "a", "ts": _iso(NOW), "en": "Fed holds rates", "salience": 90,
              "effect": "buy semiconductors", "beneficiaries": ["NVDA", "AMD"],
              "impact_chain": "rates down -> multiples up"}]
    text = mp.digest(make_root(tmp_path, wires=wires_payload(items)))
    assert "Fed holds rates" in text
    for leak in ("buy semiconductors", "NVDA", "AMD", "multiples up", "impact"):
        assert leak not in text, leak


def test_events_line_shape(tmp_path):
    line = _line(mp.digest(make_root(tmp_path)), "EVENTS ")
    assert line.startswith("EVENTS (live wire): ")
    assert re.match(r"^EVENTS \(live wire\): \d\d:\d\d UTC Fed holds rates · "
                    r"\d\d:\d\d UTC Chipmaker guides lower$", line), line


# ---------------------------------------------------------------------------
# Char budget
# ---------------------------------------------------------------------------

def test_sections_drop_from_the_bottom_of_the_priority_list(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    text = mp.render_digest(packet, 100_000)
    for marker in ("WATCH (", "DESK READ", "CROSS-ASSET (", "LEADERS (", "BREADTH (",
                   "VOL (", "RATES DESK (", "DRIVERS (", "EVENTS (", "SHOCK WINDOW (",
                   "FLAGS (", "CURVE ("):
        assert marker in text, marker
        nxt = mp.render_digest(packet, len(text) - 1)
        assert marker not in nxt, f"{marker} should have been the next to go"
        text = nxt
    assert "CURRENT DASHBOARD STATE" in text and "TAPE (" in text


def test_header_and_tape_are_never_dropped(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    text = mp.render_digest(packet, 1)
    assert text.startswith("[CURRENT DASHBOARD STATE")
    assert "TAPE (" in text
    assert len(text.split("\n")) == 2
    assert mp._NEVER_DROP == frozenset({"HEADER", "TAPE"})


def test_a_header_with_nothing_under_it_is_not_a_digest(tmp_path):
    """No tape and a budget that clears every nightly block -> "" , never a
    header promising state it did not print."""
    packet = mp.build_packet(make_root(tmp_path, quotes=None))
    assert mp.render_digest(packet, 1) == ""


def test_budget_is_respected_when_droppable_sections_exist(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    for budget in (600, 900, 1500, 2500):
        assert len(mp.render_digest(packet, budget)) <= budget, budget


def test_a_junk_budget_falls_back_to_the_default(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    assert mp.render_digest(packet, "x") == mp.render_digest(  # type: ignore[arg-type]
        packet, mp.DEFAULT_CHAR_BUDGET)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_invalidates_when_a_source_mtime_moves(tmp_path):
    root = make_root(tmp_path)
    first = mp.digest(root)
    q = quotes_payload()
    q["quotes"]["^GSPC"]["changePct"] = -9.9
    path = root / "site" / "live" / "quotes.json"
    _write(path, q)
    os.utime(path, (path.stat().st_atime + 10, path.stat().st_mtime + 10))
    second = mp.digest(root)
    assert "SPX −9.9%" in second and "SPX −9.9%" not in first


def test_cache_invalidates_when_a_source_appears(tmp_path):
    root = make_root(tmp_path, wires=None)
    assert "EVENTS" not in mp.digest(root)
    _write(root / "site" / "live" / "wires.json", wires_payload())
    assert "EVENTS (live wire): " in mp.digest(root)


def test_cache_serves_a_hit_then_expires_at_sixty_seconds(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    clock = {"t": 1_000.0}
    monkeypatch.setattr(mp, "_clock", lambda: clock["t"])

    first = mp.digest(root)
    assert "SPX −1.7%" in first

    # Rewrite the CONTENT but restore the mtime, so only the TTL can notice.
    path = root / "site" / "live" / "quotes.json"
    st = path.stat()
    q = quotes_payload()
    q["quotes"]["^GSPC"]["changePct"] = -4.4
    _write(path, q)
    os.utime(path, (st.st_atime, st.st_mtime))

    clock["t"] = 1_030.0                     # inside the 60 s ceiling -> cached
    assert mp.digest(root) == first
    clock["t"] = 1_061.0                     # past it -> rebuilt
    assert "SPX −4.4%" in mp.digest(root)
    assert mp._CACHE_TTL_S == 60.0


def test_cache_is_keyed_on_the_budget(tmp_path):
    root = make_root(tmp_path)
    assert len(mp.digest(root, 700)) <= 700
    assert len(mp.digest(root)) > 700


# ---------------------------------------------------------------------------
# House rule: no numeric confidence in a prompt
# ---------------------------------------------------------------------------

_NUMERIC_CONFIDENCE = re.compile(r"confidence[:=]\s*0?\.\d+")


def test_no_numeric_confidence_reaches_the_prompt(tmp_path):
    text = mp.digest(make_root(tmp_path))
    assert "desk confidence: medium" in text          # the qualitative word rides
    assert _NUMERIC_CONFIDENCE.search(text) is None


@pytest.mark.parametrize("conf", [0.75, "0.75", ".82", 1, True])
def test_a_numeric_confidence_is_dropped_not_printed(tmp_path, conf):
    text = mp.digest(make_root(tmp_path, market_drivers=drivers_payload(conf)))
    assert _NUMERIC_CONFIDENCE.search(text) is None
    assert "confidence" not in _line(text, "DRIVERS (")
    assert "Fed repricing" in text                    # the read itself survives


def test_the_regime_confidence_float_never_leaks(tmp_path):
    text = mp.digest(make_root(tmp_path))
    assert "0.183" not in text
    assert _NUMERIC_CONFIDENCE.search(text) is None


def test_no_probability_shaped_score_leaks_from_any_source(tmp_path):
    """The sources are full of internal floats (risk_score 0.155, absorption
    percentiles, regime confidence). None of them is a fact the desk stands
    behind in a sentence, so none may be rendered."""
    text = mp.digest(make_root(tmp_path))
    for leak in ("0.155", "0.183", "risk_score", "absorption", "display_only"):
        assert leak not in text, leak


# ── ETF stand-ins (integration follow-up): SPY/QQQ label-honest fallback ─────
# The same-origin display snapshot (site/live/quotes.json) carries SPY/QQQ, not
# ^GSPC/^IXIC. An ETF is not the index, so it renders under its OWN name — and
# only when the corresponding cash-index row is absent.

def test_tape_etf_standins_when_cash_indices_absent(tmp_path):
    payload = quotes_payload()
    for cash in ("^GSPC", "^IXIC"):
        payload["quotes"].pop(cash, None)
    payload["quotes"]["SPY"] = _q(739.0, -1.7)
    payload["quotes"]["QQQ"] = _q(682.0, -2.2)
    root = make_root(tmp_path, quotes=payload)
    text = mp.digest(root)
    tape = next(ln for ln in text.split("\n") if ln.startswith("TAPE"))
    assert "SPY −1.7%" in tape and "QQQ −2.2%" in tape
    assert "SPX" not in tape and "NDX" not in tape


def test_tape_no_etf_duplicate_when_cash_index_present(tmp_path):
    payload = quotes_payload()
    payload["quotes"]["SPY"] = _q(739.0, -1.7)
    root = make_root(tmp_path, quotes=payload)
    text = mp.digest(root)
    tape = next(ln for ln in text.split("\n") if ln.startswith("TAPE"))
    assert "SPX −1.7%" in tape
    assert "SPY" not in tape


# ---------------------------------------------------------------------------
# LEADERS — "what is leading / lagging" without a tool call
# ---------------------------------------------------------------------------
# The block SELECTS from the pulse's own equal-weight day move; it computes no
# ranking of its own. So these pin (a) that the selection is by the number that
# gets PRINTED, (b) that a group with no honest move is skipped rather than
# imputed, and (c) that no basket slug ever reaches the prompt.

def _leaders(text: str) -> str:
    return _line(text, "LEADERS (")


def test_leaders_line_carries_both_halves_strongest_first(tmp_path):
    text = mp.digest(make_root(tmp_path))
    line = _leaders(text)
    assert re.match(r"^LEADERS \(\d\d-\d\d \d\d:\d\dZ\): ", line), line
    assert line.split("): ", 1)[1] == (
        "up — AI semiconductors +2.1% · energy sector +1.8% "
        "· power & grid buildout +1.2% "
        "| down — memory & storage −1.4% · staples sector −0.9% "
        "· utilities sector −0.7%"
    ), line
    # Fourth-place movers, the exactly-flat group and the coverage null all sit
    # outside the print — and tape_rank, which disagrees with the moves in the
    # fixture, did not drive the order.
    for excluded in ("retail", "big pharma", "insurance", "housing"):
        assert excluded not in line, excluded


def test_leaders_prints_at_most_three_a_side(tmp_path):
    packet = mp.build_packet(make_root(tmp_path))
    assert len(packet["leaders"]["up"]) == mp.LEADERS_PER_SIDE
    assert len(packet["leaders"]["down"]) == mp.LEADERS_PER_SIDE
    assert mp.LEADERS_PER_SIDE == 3


def test_leaders_renders_only_the_up_half_when_nothing_is_down(tmp_path):
    """An all-green tape must not promote three flat/least-green groups to
    'down' — a half with nothing in it is simply not printed."""
    payload = basket_pulse_payload()
    payload["baskets"] = [
        {"id": "us_sector_energy", "live_ew_chg_pct": 1.4},
        {"id": "big_pharma", "live_ew_chg_pct": 0.6},
        {"id": "retail", "live_ew_chg_pct": 0.0},
        {"id": "housing", "live_ew_chg_pct": None},
    ]
    line = _leaders(mp.digest(make_root(tmp_path, basket_pulse=payload)))
    assert line.split("): ", 1)[1] == "up — energy sector +1.4% · big pharma +0.6%"
    assert "down" not in line
    assert "retail" not in line and "housing" not in line


def test_leaders_renders_only_the_down_half_when_nothing_is_up(tmp_path):
    payload = basket_pulse_payload()
    payload["baskets"] = [{"id": "memory_storage", "live_ew_chg_pct": -2.5},
                          {"id": "crypto", "live_ew_chg_pct": -1.1}]
    line = _leaders(mp.digest(make_root(tmp_path, basket_pulse=payload)))
    assert line.split("): ", 1)[1] == (
        "down — memory & storage −2.5% · crypto & digital assets −1.1%")
    assert "up —" not in line


def test_leaders_is_omitted_when_every_group_is_flat_or_null(tmp_path):
    payload = basket_pulse_payload()
    payload["baskets"] = [{"id": "retail", "live_ew_chg_pct": 0.0},
                          {"id": "housing", "live_ew_chg_pct": None}]
    root = make_root(tmp_path, basket_pulse=payload)
    packet = mp.build_packet(root)
    assert "leaders" not in packet
    assert "LEADERS" not in mp.digest(root)
    assert any(g.startswith("leaders:") for g in packet["gaps"]), packet["gaps"]


@pytest.mark.parametrize("mode,note", [
    ("live", ""),                       # the stamp already says it
    ("delayed", "delayed quotes"),
    ("last_rth", "last full session"),
    ("eod", "last close"),
    ("some_new_mode", ""),              # never leak an unmapped slug
])
def test_leaders_mode_qualifies_the_stamp_in_plain_words(tmp_path, mode, note):
    root = make_root(tmp_path, basket_pulse=basket_pulse_payload(mode=mode))
    line = _leaders(mp.digest(root))
    head = line.split("): ", 1)[0] + ")"
    assert (", " + note) in head if note else head.count(",") == 0, head
    if mode not in note:            # 'delayed' legitimately reads inside its note
        assert mode not in line     # 'last_rth' / an unmapped mode never do
    assert "_" not in line          # no slug shape reaches the prompt at all


def test_leaders_without_an_asof_renders_the_bare_head(tmp_path):
    """Mirrors the DESK READ / FLAGS law: no as-of anywhere in the source means a
    bare header, never a borrowed or implied stamp."""
    payload = basket_pulse_payload(asof=None)
    payload.pop("as_of_utc", None)
    text = mp.digest(make_root(tmp_path, basket_pulse=payload))
    line = _line(text, "LEADERS")
    assert line.startswith("LEADERS: up — AI semiconductors +2.1%"), line
    assert "LEADERS (" not in text


def test_leaders_falls_back_to_the_build_stamp_when_the_quote_stamp_is_absent(tmp_path):
    payload = basket_pulse_payload(asof=None)
    payload["as_of_utc"] = "2026-07-28T14:05:00+00:00"
    line = _leaders(mp.digest(make_root(tmp_path, basket_pulse=payload)))
    assert line.startswith("LEADERS (07-28 14:05Z): "), line


def test_leaders_junk_move_is_dropped_and_noted(tmp_path):
    """A 10x glitch must never reach the prompt as a leadership fact."""
    payload = basket_pulse_payload()
    payload["baskets"].append({"id": "quantum_computing", "live_ew_chg_pct": 210.0})
    packet = mp.build_packet(make_root(tmp_path, basket_pulse=payload))
    assert "quantum" not in mp.render_digest(packet)
    assert any("quantum_computing move 210.0% outside sanity band" in g
               for g in packet["gaps"]), packet["gaps"]
    # The rest of the line is untouched.
    assert "AI semiconductors +2.1%" in mp.render_digest(packet)


def test_leaders_unknown_slug_degrades_to_plain_words(tmp_path):
    """An upstream basket with no label entry still reports — underscores become
    spaces rather than the group vanishing or a raw slug printing."""
    payload = basket_pulse_payload()
    payload["baskets"] = [{"id": "fusion_power_startups", "live_ew_chg_pct": 3.0}]
    line = _leaders(mp.digest(make_root(tmp_path, basket_pulse=payload)))
    assert line.endswith("up — fusion power startups +3%"), line
    assert "_" not in line


def test_leaders_needs_a_baskets_list(tmp_path):
    for payload in ({"schema": "basket_pulse.v1", "mode": "live"},
                    {"schema": "basket_pulse.v1", "baskets": []},
                    {"schema": "basket_pulse.v1", "baskets": "nope"}):
        root = make_root(tmp_path, basket_pulse=payload)
        assert "LEADERS" not in mp.digest(root)
        assert "TAPE (" in mp.digest(root)       # never degrades a neighbour


def test_leaders_survives_hostile_basket_rows(tmp_path):
    payload = basket_pulse_payload()
    payload["baskets"] = [
        "not a dict", None, 17, {"live_ew_chg_pct": 1.0},        # no id
        {"id": "retail"},                                        # no move
        {"id": "crypto", "live_ew_chg_pct": "1.5"},              # string, not a number
        {"id": "big_pharma", "live_ew_chg_pct": True},           # bool is not a move
        {"id": "us_sector_energy", "live_ew_chg_pct": 0.9},      # the only real row
    ]
    line = _leaders(mp.digest(make_root(tmp_path, basket_pulse=payload)))
    assert line.split("): ", 1)[1] == "up — energy sector +0.9%", line


def test_leaders_sits_between_breadth_and_crossasset(tmp_path):
    text = mp.digest(make_root(tmp_path))
    heads = [ln.split(" (")[0] for ln in text.split("\n")]
    assert heads.index("BREADTH") < heads.index("LEADERS") < heads.index("CROSS-ASSET")
    assert mp._SECTION_ORDER.index("LEADERS") == mp._SECTION_ORDER.index("BREADTH") + 1
    assert mp._SECTION_ORDER.index("CROSSASSET") == mp._SECTION_ORDER.index("LEADERS") + 1


def test_leaders_source_is_in_the_cache_key(tmp_path):
    """A pulse refresh must invalidate the digest cache like any other source."""
    root = make_root(tmp_path)
    assert "basket_pulse.json" in mp._LIVE_SOURCES
    first = mp.digest(root)
    payload = basket_pulse_payload()
    payload["baskets"] = [{"id": "cybersecurity", "live_ew_chg_pct": 5.0}]
    _write(root / "site" / "live" / "basket_pulse.json", payload)
    os.utime(root / "site" / "live" / "basket_pulse.json", (1, 1))
    second = mp.digest(root)
    assert second != first
    assert "cybersecurity +5%" in second


# ---------------------------------------------------------------------------
# Real-artifact smoke: the committed vintage, not a fixture
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_artifacts_render_a_packet_inside_the_budget():
    """The fixtures prove the shapes; this proves the FIELD NAMES still match the
    artifacts on disk. Freshness is deliberately not asserted — the committed
    vintage ages, and a stale-but-parsed source is exactly what the stamps exist
    to disclose."""
    packet = mp.build_packet(_REPO_ROOT)
    text = mp.render_digest(packet)
    assert 0 < len(text) <= mp.DEFAULT_CHAR_BUDGET, len(text)

    pulse = _REPO_ROOT / "site" / "live" / "basket_pulse.json"
    if not pulse.exists():
        pytest.skip("site/live/basket_pulse.json is not in this checkout")
    movers = [b for b in (json.loads(pulse.read_text(encoding="utf-8")).get("baskets")
                          or [])
              if isinstance(b, dict) and isinstance(b.get("live_ew_chg_pct"), (int, float))
              and not isinstance(b.get("live_ew_chg_pct"), bool)
              and b["live_ew_chg_pct"]]
    if not movers:
        pytest.skip("this basket_pulse vintage carries no non-flat group")
    line = _leaders(text)
    assert " — " in line and "%" in line, line
    # No raw slug survived the label map / _humanize degrade.
    assert not re.search(r"[a-z]+_[a-z]+", line), line


# ── zh render branch (Analyst OS W1): desk-precomputed Chinese only ──────────
# Narrow by design (audit 2026-07-30): only fields whose zh the DESK already
# computed switch — drivers labels, wire item zh, the curve-regime label — plus the
# finite quad STATE NAMES in the prose sections (W2.1 fix 2, tests further down).
# All other text stays EN; the gateway LANGUAGE directive governs the reply.

def test_zh_drivers_render_uses_desk_translations(tmp_path):
    root = make_root(tmp_path)
    zh = mp.digest(root, lang="zh")
    assert "美联储重定价" in zh and "鹰派重定价" in zh
    assert "置信度: 中" in zh and "归因: 明确" in zh
    assert "hawkish repricing" not in zh


def test_zh_events_prefer_wire_zh_with_en_fallback(tmp_path):
    root = make_root(tmp_path)
    zh = mp.digest(root, lang="zh")
    assert "美联储维持利率" in zh          # item a has zh
    assert "Chipmaker guides lower" in zh  # item b has none — EN fallback


def test_zh_rates_curve_uses_canonical_label(tmp_path):
    rp = rates_payload()
    rp["board"]["risk_row"]["curve_regime_label_zh"] = "熊市变陡"
    root = make_root(tmp_path, rates=rp)
    zh = mp.digest(root, lang="zh")
    en = mp.digest(root, lang="en")
    assert "curve: 熊市变陡" in zh
    assert "curve: bear steepener" in en


def test_en_default_identical_to_explicit_en(tmp_path):
    root = make_root(tmp_path)
    assert mp.digest(root) == mp.digest(root, lang="en")


def test_render_lang_never_mutates_caller_packet(tmp_path):
    root = make_root(tmp_path)
    packet = mp.build_packet(root)
    mp.render_digest(packet, lang="zh")
    assert "_render_lang" not in packet


def test_zh_and_en_cached_separately(tmp_path):
    root = make_root(tmp_path)
    zh = mp.digest(root, lang="zh")
    en = mp.digest(root, lang="en")
    assert zh != en
    # Second reads hit the cache and stay language-correct.
    assert mp.digest(root, lang="zh") == zh
    assert mp.digest(root, lang="en") == en


# ── zh quad-state names in the English-prose sections (W2.1 fix 2) ───────────
# Live zh probe 2026-07-30 answered with a bare "Goldilocks" ×3 because the zh
# digest itself fed the model "Cross-asset regime: Goldilocks" / "…flip us into
# Reflation": the model copies its own input over the language directive. The
# prose stays English (the directive owns that) — only the finite quad state
# NAMES switch, to the desk-canonical forms (see mp._ZH_STATE_TOKENS).

def test_zh_prose_sections_carry_canonical_state_words(tmp_path):
    """No bare English quad name survives a zh render; 理想增长 / 再通胀 appear instead."""
    mb = master_brief_payload()
    mb["regime_read"] = ("We are still in Goldilocks, but one nudge lower flips us "
                         "into Reflation.")
    mb["watch_items"] = ["Small caps: a break lower flips the macro regime to Reflation."]
    root = make_root(tmp_path, master_brief=mb)
    zh = mp.digest(root, lang="zh")

    assert "Goldilocks" not in zh
    assert "Reflation" not in zh
    assert "理想增长" in zh          # DESK READ  (Regime line)
    assert "再通胀" in zh            # DESK READ + WATCH
    # The world_state line is the one the live probe copied — it must switch too.
    assert "Cross-asset regime: 理想增长" in zh
    assert "理想增长" in _line(zh, "WATCH (") or "再通胀" in _line(zh, "WATCH (")


def test_en_digest_is_byte_identical_to_before_the_zh_substitution(tmp_path):
    """The EN render never sees the map: same fixture, English state words intact."""
    mb = master_brief_payload()
    mb["regime_read"] = ("We are still in Goldilocks, but one nudge lower flips us "
                         "into Reflation.")
    root = make_root(tmp_path, master_brief=mb)
    en = mp.digest(root, lang="en")
    assert "Goldilocks" in en and "Reflation" in en
    assert "理想增长" not in en and "再通胀" not in en
    # The EN path is untouched by lang= plumbing at all.
    assert mp.digest(root) == en


def test_zh_state_substitution_is_whole_token_only():
    """A state name inside a longer word is NOT replaced; one against punctuation is."""
    # Never a substring: the trailing letters make it a different word.
    assert mp._zh_state_words("Reflationary pressures") == "Reflationary pressures"
    assert mp._zh_state_words("Deflationary spiral") == "Deflationary spiral"
    # Case-sensitive: the generic lowercase noun is prose, not a state name.
    assert mp._zh_state_words("confirms if inflation is truly cooling") == (
        "confirms if inflation is truly cooling")
    # Whole tokens do switch, including against punctuation and at the edges.
    assert mp._zh_state_words("Goldilocks") == "理想增长"
    assert mp._zh_state_words("regime: Goldilocks.") == "regime: 理想增长."
    assert mp._zh_state_words("flips to Reflation, then Stagflation") == (
        "flips to 再通胀, then 滞胀")
    # Longest form wins over its own prefix (leftmost-first alternation order).
    assert mp._zh_state_words("Growth-scare/Deflation") == "增长恐慌／通缩"
    assert mp._zh_state_words("") == ""


def test_zh_state_map_is_the_desk_canonical_vocabulary():
    """Goldilocks → 理想增长: engine/master_brain.py::_ZH_LEXICON_FIXUPS normalizes
    translated 中文 TO this form (金发姑娘 is the retired variant it replaces), and
    engine/i18n.py::LEX agrees. alert_triage._QUAD_ZH's 金发经济 is overruled."""
    from engine import i18n

    assert mp._ZH_STATE_MAP["Goldilocks"] == i18n.LEX["Goldilocks"] == "理想增长"
    assert mp._ZH_STATE_MAP["Reflation"] == i18n.LEX["Reflation"]
    assert mp._ZH_STATE_MAP["Stagflation"] == i18n.LEX["Stagflation"]
    assert mp._ZH_STATE_MAP["Deflation"] == i18n.LEX["Deflation"]
    assert mp._ZH_STATE_MAP["Growth-scare/Deflation"] == i18n.LEX["Growth-scare/Deflation"]
    assert mp._ZH_STATE_MAP["Growth scare"] == i18n.LEX["Growth scare"]
    # Inflation / Disinflation have no LEX key — alert_triage is the house source.
    from engine import alert_triage

    assert mp._ZH_STATE_MAP["Inflation"] == alert_triage._QUAD_ZH["Inflation"]
    assert mp._ZH_STATE_MAP["Disinflation"] == alert_triage._QUAD_ZH["Disinflation"]
    # FROZEN + FINITE: generic macro nouns are deliberately NOT in the map.
    for word in ("Growth", "Slowdown", "Recovery", "Contraction"):
        assert word not in mp._ZH_STATE_MAP


def test_zh_desk_precomputed_paths_are_untouched_by_the_substitution(tmp_path):
    """The already-working zh fields (drivers _zh, curve_regime_zh, wire zh) still
    render exactly as before — this fix is additive on the remaining English prose."""
    rp = rates_payload()
    rp["board"]["risk_row"]["curve_regime_label_zh"] = "熊市变陡"
    root = make_root(tmp_path, rates=rp)
    zh = mp.digest(root, lang="zh")
    assert "美联储重定价" in zh and "置信度: 中" in zh and "归因: 明确" in zh
    assert "curve: 熊市变陡" in zh
    assert "美联储维持利率" in zh
