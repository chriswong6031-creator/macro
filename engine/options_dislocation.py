"""engine/options_dislocation.py — options information-dislocation feature layer.

WHAT THIS IS. A per-(date, underlying) block of options-surface primitives computed from
the chain snapshots the GEX desk already persists (data/polygon_gex/chains/<date>.parquet),
each **cross-sectionally neutralised against implied-volatility LEVEL and size** before it is
allowed to mean anything. Plus four categorical READS (confirmation / crowding / vol-regime /
pre-event) built from named primitives, and a forward-accruing ledger + dormant gate.

WHY NEUTRALISATION IS THE WHOLE POINT (measured here, 2026-08-05, 41 chain dates × 392 names).
Run naively, almost every "options information" feature is a repackaged bet on implied-vol
LEVEL — a long-known priced characteristic, not information. Measured on our own panel, raw
per-date cross-sectional rank IC vs SPY-relative 5d forward returns, then again after
per-date rank-space residualisation on (iv30, log spot):

    feature          raw IC5    neutralised IC5   what survived
    em30             -0.2297    (IS iv30)         nothing — expected move IS the IV level
    iv_rv            -0.1090    -0.0148           86% of it was the vol level
    turn             -0.0599    -0.0071           dies, and flips sub-period
    kv_conc          +0.0403    +0.0065           dies, and flips sub-period
    term_slope       -0.0922    -0.0402           survives, halved
    oi_tilt          -0.0673    -0.0873           survives and STRENGTHENS

An engine that skipped this step would ship `event_expected_move_gap` at an apparent
IC of −0.23 (t≈−9) and be, in fact, short high-vol stocks in one six-week window.

WHAT THE PANEL CANNOT DO. 41 trading dates in ONE regime. At h=5 that is ~8 independent
windows; at h=21 it is ~1. Every t-statistic on this panel is vacuous by construction —
overlapping windows inside a single regime. Nothing here is validated, and no number in
this module may be described as such. What the diagnostics above DO establish is narrower
and still worth shipping: which primitives are not merely IV level wearing a hat. The gate
(scripts/validate_options_dislocation.py) stays dormant until the panel reaches 120 dates.

SHAPE LAW — WHY THERE ARE READS AND NOT SCORES (binding: OPTIONS_NW_ENTRY_INTELLIGENCE
_MASTERPLAN_BY_FABLE RO-2 / Signal Commons R3). Fused escalating composites are a FORBIDDEN
shape pre-gate: "no ... scores, or ranks anywhere a reader can lift them pre-gate ... Any
summary of options state may only ever be a post-hoc roll-up of already-gated survivors."
So the four multi-primitive families ship as CATEGORICAL reads over named, separately-visible
primitives — never a 0-100 or −3..+3 number. Only genuinely single-primitive measures
(skew acceleration; the pre-event implied/realised move gap) carry a numeric value, because
a single measured quantity is not a fusion. Per RO-3 the reads are caution/context-only and
may only ever LOWER confidence in a candidate — never originate or escalate one.

MEASURED NULLS, PRINTED NOT HIDDEN (house epistemics; "nulls printed, not hidden").
Trade-direction-dependent features are NOT computable on our entitlements and the cheap
substitutes are measured dead, so they are emitted as explicit nulls carrying their evidence
rather than silently omitted — see `MEASURED_NULLS`. `research/OPTIONS_FLOW_DATA.md`: OPRA
trades+NBBO are 403 on our plan; the minute tick-rule recovers a contract's net daily sign
at 0.41 — worse than a coin flip — and delta-adjustment was tested and REJECTED (0.39).
On our own panel the two bar-only directional proxies flip sign between sub-periods
(call-vs-put volume tilt +0.049 → −0.030; delta-weighted +0.006 → −0.044). Cboe Open-Close
(the dataset Pan-Poteshman used) would supply the real thing at ~$2,000/mo and is already
adjudicated DENIED (RO-10, W6 SKIP-ALL) — do not re-propose it here.

REGISTRY ADJACENCY — DECLARED, NOT EVADED (research/DO_NOT_REBUILD.md).
  * "DOI (options delta-OI family) | DEAD" — that kill closed DOI *persistence tested at
    SECTOR-ETF level* (W-E1, 0/12 on ~24 roots). `oi_tilt` here is a different construction
    on a different population: a single-name CROSS-SECTIONAL, IV-level-neutralised standing
    positioning tilt over ~390 names. The masterplan lists single-name cross-sectional claims
    as BLOCKED ON DATA ("Store has only NVDA"), i.e. never tested — not killed. It ships
    display-only, and it does not revive DOI or claim the kill was wrong.
  * "Skew-deceleration | UNSUPPORTED" — that kill closed the *bullish-deceleration*
    hypothesis. W-E1's lone survivor pointed OPPOSITE the bullish premise; `skew_accel` here
    is that opposite sign (rising skew → lower forward returns), so this is concordant with
    the existing evidence, not a re-litigation of the killed direction.

PURE compute; all disk IO is isolated in snapshot() / load_*().
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "options_dislocation.v1"

# Expiry buckets, in calendar days, for the term structure.
_FRONT = (1.0, 15.0)
_MID = (15.0, 45.0)
_BACK = (60.0, 120.0)

_MIN_XS = 20          # names needed on a date before cross-sectional neutralisation means anything
_EM_TENOR_D = 30.0    # expected move horizon

# Cross-sectional controls. iv30 is the contaminant the diagnostics above identified;
# log-spot stands in for size. Both are neutralised in RANK space (monotone-robust).
_CONTROLS = ("iv30", "log_spot")

# Primitives that survived neutralisation AND held their sign across both sub-periods,
# with the sign the literature/our panel predicts. This is the pre-registered sign map
# the dormant gate will test — fixed HERE, before the gate can ever run on more data.
PREREG_SIGNS = {
    "oi_tilt": -1,          # call-heavy standing OI = crowding, not confirmation
    "d5_ivspread": +1,      # Cremers-Weinbaum, in changes
    "d5_term_slope": +1,
    "skew_accel": -1,       # Xing-Zhang-Zhao, in acceleration
    "skew": -1,
    "ivspread": +1,
    "term_slope": -1,
}

# Measured dead on our own panel or unavailable on our entitlements. Emitted as nulls
# carrying their evidence — never silently dropped, never quietly imputed.
MEASURED_NULLS = {
    "buyer_initiated_call_volume": {
        "state": "unavailable_entitlement",
        "why": ("Needs the per-trade OPRA tape stamped with prevailing NBBO. Our plan returns "
                "403 on trades_v1 and quotes_v1 (research/OPTIONS_FLOW_DATA.md)."),
        "substitute_tested": ("minute tick-rule signing: 0.41 net-daily-sign recovery, worse "
                              "than a coin flip; delta-adjusted variant 0.39, REJECTED"),
    },
    "buyer_initiated_put_volume": {
        "state": "unavailable_entitlement",
        "why": "Same tape as buyer_initiated_call_volume.",
        "substitute_tested": "same calibration — 0.41 / 0.39",
    },
    "opening_vs_closing_trades": {
        "state": "unavailable_entitlement",
        "why": ("Per-trade open/close flags are a Cboe Open-Close product (~$2,000/mo); "
                "procurement adjudicated DENIED (RO-10, W6 SKIP-ALL)."),
        "substitute_tested": ("net standing-OI change is a NET opening proxy only — it cannot "
                              "attribute an opening trade to buyer or seller"),
    },
    "delta_weighted_directional_volume": {
        "state": "null_measured",
        "why": ("Direction requires trade signing we do not have. The direction-free form "
                "(delta-weighted call-vs-put volume tilt) was computed on our panel and its "
                "sign FLIPS between sub-periods: +0.006 then −0.044 (5d IC, neutralised "
                "+0.030 then −0.046)."),
        "substitute_tested": "raw call/put volume tilt also flips: +0.049 then −0.030",
    },
    "synthetic_stock_price_deviation": {
        "state": "structurally_absent",
        "why": ("The chain store carries iv/greeks/oi/volume but NO option price column, so "
                "price-space put-call parity cannot be formed. Its IV-space equivalent IS "
                "computed and shipped — `ivspread` (Cremers-Weinbaum)."),
        "substitute_tested": "ivspread carries the same information content in IV space",
    },
}


# --------------------------------------------------------------------------- #
# Primitives (pure, per underlying)
# --------------------------------------------------------------------------- #
def _atm_iv(g, lo: float, hi: float) -> float:
    """ATM IV for the expiry bucket [lo,hi) days: the single nearest-to-mid expiry,
    |delta| closest to 0.50, averaged across call and put. NaN when unusable."""
    import numpy as np
    import pandas as pd
    try:
        d = g[(g["_days"] >= lo) & (g["_days"] < hi) & (g["iv"] > 0.0)]
        if d.empty:
            return float("nan")
        tgt = (lo + hi) / 2.0
        exp = d.loc[(d["_days"] - tgt).abs().idxmin(), "expiry"]
        d = d[d["expiry"] == exp]
        legs = []
        for want_call in (True, False):
            s = d[d["is_call"].astype(bool) == want_call]
            if s.empty:
                continue
            dd = pd.to_numeric(s["delta"], errors="coerce").abs()
            if dd.notna().sum() == 0:
                continue
            legs.append(float(s.loc[(dd - 0.5).abs().idxmin(), "iv"]))
        return float(np.mean(legs)) if legs else float("nan")
    except Exception as e:  # noqa: BLE001
        log.debug("_atm_iv failed (%s)", e)
        return float("nan")


def _hhi(w) -> float:
    """Herfindahl concentration of a non-negative weight series. NaN when degenerate."""
    import numpy as np
    try:
        t = float(w.sum())
        if not np.isfinite(t) or t <= 0:
            return float("nan")
        p = (w / t).values
        return float(np.sum(p * p))
    except Exception:  # noqa: BLE001
        return float("nan")


def compute_primitives(rows) -> dict | None:
    """Options-surface primitives for ONE underlying's chain frame. PURE.

    Every value is nullable; a missing leg yields NaN rather than a fabricated neutral.
    Nothing here is neutralised yet — that is a cross-sectional step (see neutralise()).
    """
    import numpy as np
    import pandas as pd
    try:
        if rows is None or getattr(rows, "empty", True):
            return None
        g = rows.copy()
        g["_days"] = pd.to_numeric(g["T"], errors="coerce").astype(float) * 365.0
        g = g[g["_days"] > 0]
        if g.empty:
            return None
        spot = float(pd.to_numeric(g["spot"], errors="coerce").iloc[0])
        if not np.isfinite(spot) or spot <= 0:
            return None

        iv_front = _atm_iv(g, *_FRONT)
        iv30 = _atm_iv(g, *_MID)
        iv_back = _atm_iv(g, *_BACK)

        vol = pd.to_numeric(g["volume"], errors="coerce").fillna(0.0)
        oi = pd.to_numeric(g["oi"], errors="coerce").fillna(0.0)
        dl = pd.to_numeric(g["delta"], errors="coerce").fillna(0.0).abs()
        isc = g["is_call"].astype(bool)

        # Standing delta-weighted positioning tilt. LEVEL only — the OI a chain reports on
        # date t reflects positions as of the END of t-1 (OI timing law, engine/thetadata_store),
        # so this is prior-close positioning, never same-day flow.
        doc, dop = float((dl * oi)[isc].sum()), float((dl * oi)[~isc].sum())
        oi_tilt = (doc - dop) / (doc + dop) if (doc + dop) > 0 else float("nan")

        tot_v, tot_oi = float(vol.sum()), float(oi.sum())
        em30 = (iv30 * np.sqrt(_EM_TENOR_D / 365.0)) if np.isfinite(iv30) else float("nan")

        def _n(x):
            return round(float(x), 6) if np.isfinite(x) else None

        return {
            "underlying": str(g["underlying"].iloc[0]).upper(),
            "spot": _n(spot),
            "iv_front": _n(iv_front), "iv30": _n(iv30), "iv_back": _n(iv_back),
            # front-vs-back implied-volatility slope (proposal feature 6)
            "term_slope": _n(iv30 - iv_back) if np.isfinite(iv30) and np.isfinite(iv_back) else None,
            "front_slope": _n(iv_front - iv30) if np.isfinite(iv_front) and np.isfinite(iv30) else None,
            # option-implied expected move over ~30d, as a FRACTION of spot (proposal feature 8)
            "em30": _n(em30),
            # standing positioning + concentration (proposal features 11, 12)
            "oi_tilt": _n(oi_tilt),
            "turnover": _n(tot_v / tot_oi) if tot_oi > 0 else None,
            "strike_conc": _n(_hhi(g.groupby("K")["oi"].sum())),
            "expiry_conc": _n(_hhi(g.groupby("expiry")["oi"].sum())),
            "total_volume": _n(tot_v), "total_oi": _n(tot_oi),
            "n_contracts": int(len(g)),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("compute_primitives failed (%s)", e)
        return None


def primitives_map(chain) -> dict[str, dict]:
    """{underlying: primitives} over a full chain snapshot (many underlyings). PURE."""
    out: dict[str, dict] = {}
    try:
        if chain is None or getattr(chain, "empty", True) or "underlying" not in chain.columns:
            return out
        for u, g in chain.groupby("underlying"):
            m = compute_primitives(g)
            if m is not None:
                out[str(u).upper()] = m
    except Exception as e:  # noqa: BLE001
        log.debug("primitives_map failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# Cross-sectional neutralisation — the step that makes this information, not IV level
# --------------------------------------------------------------------------- #
def neutralise(panel, cols, controls=_CONTROLS, min_names: int = _MIN_XS):
    """Per-DATE cross-sectional rank-space OLS residual of each col on `controls`.

    Returns the panel with `n_<col>` columns added. Rank-transforming both sides makes the
    control monotone-robust (we care that a feature is not a re-ranking of IV level, not
    that it is linearly unrelated to it). Dates with fewer than `min_names` joint
    observations are left NaN — a residual from 6 names is noise, not a neutralisation.
    """
    import numpy as np
    import pandas as pd
    if panel is None or getattr(panel, "empty", True):
        return panel
    ctrls = [c for c in controls if c in panel.columns]
    for col in cols:
        out = pd.Series(np.nan, index=panel.index, dtype=float)
        if col not in panel.columns or not ctrls:
            panel[f"n_{col}"] = out
            continue
        for _d, g in panel.groupby("date"):
            sub = g[[col] + ctrls].apply(pd.to_numeric, errors="coerce")
            m = sub.notna().all(axis=1)
            if int(m.sum()) < min_names:
                continue
            s = sub[m]
            y = s[col].rank(pct=True).values
            X = np.column_stack([np.ones(len(s))] + [s[c].rank(pct=True).values for c in ctrls])
            try:
                beta, *_ = np.linalg.lstsq(X, y, rcond=None)
                out.loc[s.index] = y - X @ beta
            except Exception as e:  # noqa: BLE001
                log.debug("neutralise %s failed on a date (%s)", col, e)
        panel[f"n_{col}"] = out
    return panel


def build_panel(history=None, chains: dict | None = None):
    """Assemble the per-(date, underlying) panel: primitives + joined skew/ivspread legs +
    within-name changes + neutralised columns. `chains` maps date-string → chain frame
    (injectable for tests); default reads the dated chain snapshots from disk."""
    import numpy as np
    import pandas as pd

    rows = []
    src = chains if chains is not None else _dated_chains()
    for d, chain in sorted(src.items()):
        for u, m in primitives_map(chain).items():
            rows.append({"date": str(d), **m})
    if not rows:
        return pd.DataFrame()
    P = pd.DataFrame(rows).sort_values(["underlying", "date"]).reset_index(drop=True)

    # Join the two already-accruing legs (they are the same chain store, already validated
    # apparatus — reuse rather than recompute, so a fix there propagates here).
    for path, col in (("options_skew", "skew"), ("options_ivspread", "ivspread")):
        try:
            p = config.data_dir() / path / "snapshots.parquet"
            if p.exists():
                s = pd.read_parquet(p)[["date", "underlying", col]].copy()
                s["date"] = s["date"].astype(str)
                s["underlying"] = s["underlying"].astype(str).str.upper()
                s = s.drop_duplicates(subset=["date", "underlying"], keep="last")
                P = P.merge(s, on=["date", "underlying"], how="left")
        except Exception as e:  # noqa: BLE001
            log.debug("join %s failed (%s)", col, e)
    for col in ("skew", "ivspread"):
        if col not in P.columns:
            P[col] = np.nan

    P["log_spot"] = np.log(pd.to_numeric(P["spot"], errors="coerce").clip(lower=0.01))

    # Within-name changes. diff(5) over the panel's own date ordering — the panel is one
    # row per (date, underlying), so this is a 5-observation change, not 5 calendar days.
    for c in ("skew", "ivspread", "term_slope"):
        P[f"d5_{c}"] = P.groupby("underlying")[c].diff(5)
    P["skew_accel"] = P.groupby("underlying")["d5_skew"].diff(5)

    P = _add_stock_state(P)
    P = _add_event_gap(P)
    return neutralise(P, list(PREREG_SIGNS.keys()))


def _add_stock_state(P):
    """The stock-side leg of option-vs-stock confirmation (proposal feature 13).

    Uses the panel's own spot series, benchmarked to SPY when SPY is present, so the read is
    'did this name move relative to the market', not 'did the market move'. Deliberately
    coarse (up / down / neutral) — a categorical input to a categorical read.
    """
    import numpy as np
    import pandas as pd
    try:
        P = P.sort_values(["underlying", "date"]).copy()
        P["ret5"] = P.groupby("underlying")["spot"].pct_change(5)
        bench = (P[P["underlying"] == "SPY"].set_index("date")["ret5"]
                 if (P["underlying"] == "SPY").any() else None)
        rel = P["ret5"] - P["date"].map(bench) if bench is not None else P["ret5"]
        P["ret5_rel"] = rel
        band = 0.02  # ±2% relative over five observations reads as a real move
        P["stock_state"] = np.where(~np.isfinite(pd.to_numeric(rel, errors="coerce")), None,
                                    np.where(rel > band, "up",
                                             np.where(rel < -band, "down", "neutral")))
        P.loc[pd.to_numeric(rel, errors="coerce").isna(), "stock_state"] = None
    except Exception as e:  # noqa: BLE001
        log.debug("_add_stock_state failed (%s)", e)
        P["stock_state"] = None
    return P


def _add_event_gap(P, earnings=None):
    """Pre-event expectations: actual move vs option-implied move (proposal feature 9).

    `em30` is the ~30d implied 1-sigma move as a fraction of spot; scaled to the days until
    the name's next earnings date it becomes that event's implied move. The GAP is only
    computable once the event has passed and a post-event spot exists, so on a forward-looking
    calendar most rows are legitimately null and the column ACCRUES. Scale-free by
    construction (a ratio of two moves), which is why it survives where raw `em30` does not.
    """
    import numpy as np
    import pandas as pd
    P["event_em_gap"] = np.nan
    P["days_to_earnings"] = np.nan
    try:
        if earnings is None:
            p = config.data_dir() / "earnings" / "earnings.parquet"
            if not p.exists():
                return P
            earnings = pd.read_parquet(p)
        e = earnings.copy()
        if "next_date" not in e.columns:
            return P
        idx = e.index.astype(str).str.upper()
        nxt = pd.to_datetime(e["next_date"], errors="coerce")
        cal = dict(zip(idx, nxt))

        d = pd.to_datetime(P["date"], errors="coerce")
        ev = P["underlying"].astype(str).str.upper().map(cal)
        dte = (pd.to_datetime(ev) - d).dt.days
        P["days_to_earnings"] = dte

        # implied move scaled from the 30d measure to the event horizon (sqrt-of-time)
        em = pd.to_numeric(P["em30"], errors="coerce")
        horizon = dte.clip(lower=1)
        implied = em * np.sqrt(horizon / _EM_TENOR_D)

        # Realised move over the SAME horizon. Needs a post-event spot, so this is
        # computable only for rows whose event lands inside the panel's own date range —
        # left null (accruing) otherwise, never imputed.
        realised = pd.Series(np.nan, index=P.index, dtype=float)
        spot_by = P.pivot_table(index="date", columns="underlying", values="spot")
        dates = list(spot_by.index)
        pos_of = {d: i for i, d in enumerate(dates)}      # O(1) — a list .index() here is O(n^2)
        cols = set(spot_by.columns)
        for r in P.itertuples(index=True):
            k = getattr(r, "days_to_earnings", np.nan)
            if not np.isfinite(k) or k < 0:
                continue
            pos = pos_of.get(str(r.date))
            if pos is None:
                continue
            tgt = pos + int(k) + 1
            if tgt >= len(dates):
                continue
            u = str(r.underlying).upper()
            if u not in cols:
                continue
            s0, s1 = spot_by.iat[pos, spot_by.columns.get_loc(u)], \
                spot_by.iat[tgt, spot_by.columns.get_loc(u)]
            if np.isfinite(s0) and np.isfinite(s1) and s0 > 0:
                realised.at[r.Index] = abs(s1 / s0 - 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            P["event_em_gap"] = np.where(
                (implied > 0) & np.isfinite(realised), realised / implied - 1.0, np.nan)
    except Exception as e:  # noqa: BLE001
        log.debug("_add_event_gap failed (%s)", e)
    return P


# --------------------------------------------------------------------------- #
# Reads — categorical, per RO-2. NEVER a liftable number for a fused family.
# --------------------------------------------------------------------------- #
_BAND = 0.15   # |neutralised rank residual| below this reads as "no dislocation"


def _state(v, sign: int) -> str | None:
    """Map one neutralised residual to a three-way state, oriented so that
    'dislocated' always means 'the direction this primitive's evidence points'."""
    import numpy as np
    if v is None or not np.isfinite(v):
        return None
    if abs(v) < _BAND:
        return "neutral"
    return "dislocated" if (v * sign) > 0 else "contra"


def reads(row) -> dict:
    """The four multi-primitive families, as CATEGORICAL reads over named primitives.

    Each read names the primitives it consulted and their individual states. There is no
    blended number: RO-2 forbids a liftable pre-gate composite, and a reader who wants to
    weigh these must see the parts. Per RO-3 these are caution/context only.
    """
    import numpy as np

    def g(k):
        v = row.get(k)
        try:
            f = float(v)
            return f if np.isfinite(f) else None
        except (TypeError, ValueError):
            return None

    def _fold(parts: dict) -> str:
        """Categorical fold: agreeing evidence → that direction; disagreeing → 'mixed';
        nothing measurable → 'null'. Deliberately NOT a weighted sum."""
        vals = [v for v in parts.values() if v is not None]
        if not vals:
            return "null"
        d = sum(1 for v in vals if v == "dislocated")
        c = sum(1 for v in vals if v == "contra")
        if d and c:
            return "mixed"
        if d:
            return "dislocated"
        if c:
            return "contra"
        return "neutral"

    # 1. directional_option_information — do option prices lean a way the stock has not gone?
    #    Built from the two parity/skew families that need NO trade signing.
    dir_parts = {
        "ivspread": _state(g("n_ivspread"), PREREG_SIGNS["ivspread"]),
        "d5_ivspread": _state(g("n_d5_ivspread"), PREREG_SIGNS["d5_ivspread"]),
        "skew": _state(g("n_skew"), PREREG_SIGNS["skew"]),
    }
    # 2. volatility_disagreement — term structure disagreeing with itself across tenors.
    vol_parts = {
        "term_slope": _state(g("n_term_slope"), PREREG_SIGNS["term_slope"]),
        "d5_term_slope": _state(g("n_d5_term_slope"), PREREG_SIGNS["d5_term_slope"]),
    }
    # 3. option_stock_confirmation — does the options read AGREE with the stock's own move?
    #    Confirmation is only meaningful when both sides are measurable.
    dirf = _fold(dir_parts)
    stock = row.get("stock_state")
    if dirf in ("null", "neutral") or stock in (None, "neutral"):
        confirm = "null" if dirf == "null" or stock is None else "neutral"
    else:
        opt_bull = dirf == "contra"        # 'contra' on bearish-signed primitives = bullish lean
        stk_bull = stock == "up"
        confirm = "confirms" if opt_bull == stk_bull else "contradicts"
    # 4. dealer_positioning_fragility — a HAZARD/regime read, explicitly NOT a return
    #    predictor. Concentration died as a predictor under neutralisation (that is why it
    #    is absent from PREREG_SIGNS) but concentrated OI near expiry is still what makes a
    #    hedging surface brittle, which is a different claim.
    kc, ec, tv = g("strike_conc"), g("expiry_conc"), g("turnover")
    frag_parts = {k: v for k, v in
                  (("strike_conc", kc), ("expiry_conc", ec), ("turnover", tv)) if v is not None}
    if not frag_parts:
        fragility = "null"
    else:
        hot = sum(1 for k, v in frag_parts.items()
                  if (k in ("strike_conc", "expiry_conc") and v >= 0.15) or (k == "turnover" and v >= 1.0))
        fragility = "brittle" if hot >= 2 else ("watch" if hot == 1 else "resilient")

    return {
        "directional_option_information": {"read": dirf, "parts": dir_parts},
        "volatility_disagreement": {"read": _fold(vol_parts), "parts": vol_parts},
        "option_stock_confirmation": {"read": confirm,
                                      "parts": {"options": dirf, "stock": stock}},
        "dealer_positioning_fragility": {"read": fragility, "parts": frag_parts,
                                         "is_return_predictor": False},
        # Genuinely single-primitive measures — lawful to carry a number.
        "skew_acceleration": g("n_skew_accel"),
        "event_expected_move_gap": g("event_em_gap"),
    }


# --------------------------------------------------------------------------- #
# Disk: forward-accruing ledger + dormant gate
# --------------------------------------------------------------------------- #
_LEDGER_COLS = ["date", "underlying", "spot", "iv_front", "iv30", "iv_back", "term_slope",
                "front_slope", "em30", "oi_tilt", "turnover", "strike_conc", "expiry_conc",
                "total_volume", "total_oi", "n_contracts", "skew", "ivspread",
                "d5_skew", "d5_ivspread", "d5_term_slope", "skew_accel"] + \
               [f"n_{c}" for c in PREREG_SIGNS]


def _snap_path():
    p = config.data_dir() / "options_dislocation"
    p.mkdir(parents=True, exist_ok=True)
    return p / "snapshots.parquet"


def _dated_chains() -> dict:
    """{date-string: chain frame} from the dated chain snapshots. The filename IS the date."""
    import glob
    from pathlib import Path
    import pandas as pd
    out = {}
    for f in sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet"))):
        try:
            out[Path(f).stem] = pd.read_parquet(f)
        except Exception as e:  # noqa: BLE001
            log.debug("chain read %s failed (%s)", f, e)
    return out


def snapshot(panel=None) -> int:
    """Append new (date, underlying) rows to the ledger. Idempotent by that key.
    Returns rows added. This is the apparatus that accrues history toward a verdict."""
    import pandas as pd
    P = build_panel() if panel is None else panel
    if P is None or getattr(P, "empty", True):
        return 0
    keep = [c for c in _LEDGER_COLS if c in P.columns]
    fresh = P[keep].copy()
    # float32 on the measures. This ledger is the ONLY durable record of these primitives —
    # the chain store it derives from is pruned to ~40 days — so it accrues forever and its
    # width is paid nightly. 6-decimal rounding already caps the meaningful precision.
    for c in fresh.columns:
        if c not in ("date", "underlying") and fresh[c].dtype == "float64":
            fresh[c] = fresh[c].astype("float32")
    p = _snap_path()
    if p.exists():
        prev = pd.read_parquet(p)
        key = set(zip(prev["date"].astype(str), prev["underlying"].astype(str)))
        mask = [(str(d), str(u)) not in key
                for d, u in zip(fresh["date"], fresh["underlying"])]
        fresh = fresh[mask]
        if fresh.empty:
            return 0
        combined = pd.concat([prev, fresh], ignore_index=True)
    else:
        combined = fresh
    combined.to_parquet(p)
    return int(len(fresh))


def load_history():
    import pandas as pd
    p = _snap_path()
    return pd.read_parquet(p) if p.exists() else None


def load_gate() -> dict | None:
    """The validation verdict (scripts/validate_options_dislocation.py). None → 'measuring'."""
    try:
        import json
        p = config.data_dir() / "options_dislocation" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def build_snapshot(today: date | None = None, panel=None) -> dict:
    """Display payload: latest-date reads per name + the (dormant) gate + printed nulls."""
    import numpy as np
    today = today or date.today()
    P = build_panel() if panel is None else panel
    gate = load_gate() or {}
    names: dict[str, dict] = {}
    as_of = None
    if P is not None and not getattr(P, "empty", True):
        as_of = str(P["date"].max())
        last = P[P["date"].astype(str) == as_of]
        for r in last.to_dict("records"):
            u = str(r.get("underlying", "")).upper()
            if not u:
                continue
            rd = reads(r)
            names[u] = {
                "reads": rd,
                "primitives": {k: (None if r.get(k) is None or
                                   (isinstance(r.get(k), float) and not np.isfinite(r[k]))
                                   else r.get(k))
                               for k in ("iv30", "term_slope", "em30", "oi_tilt",
                                         "turnover", "skew", "ivspread")},
            }
    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "scored": bool(gate.get("scored")),
        "as_of": as_of or today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n": len(names),
        "names": names,
        "gate_status": gate.get("status", "measuring"),
        "measured_nulls": MEASURED_NULLS,
        "neutralised_against": list(_CONTROLS),
        "disclaimer": (
            "Options-surface context, cross-sectionally neutralised against implied-vol level "
            "and size so it reads as information rather than a repackaged volatility bet. "
            "DISPLAY-ONLY: the chain panel is one short regime, far below the history a "
            "return-predictor verdict needs — accruing toward one. Reads may only lower "
            "confidence in a candidate, never originate one. Trade-direction features are "
            "not computable on our data and are printed as explicit nulls."),
    }
