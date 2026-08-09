"""Per-name extension / exhaustion read for the Top-Picks board (display-only).

The Top-Picks rank stays the validated `alpha_led` conviction blend — momentum is the
edge and folding mean-reversion/value INTO the rank measurably hurts (reports/top-picks-
phase0.md). But the rank's top is, by construction, the most-extended momentum names, and
the user's worry is "sharp pullbacks, especially in a bubble." That is a per-name RISK
question. We answer it with an extension axis that NEVER touches the score.

What the Phase-0 downside test established (reports/top-picks-freshness-phase0.md,
138 PIT rebalances, long-only, drawdown-aware):
  * NO basket screen reduces drawdown — requiring "freshness / near-highs" actually makes
    it WORSE (it just concentrates the book). So there is no honest "fresh-leaders rotation"
    to sell; the extension read is a PER-NAME risk-placement lens, not a return claim.
  * The danger is concentrated and per-name: the PARABOLIC tail (ext_z > 2 — more than 2σ
    above the name's own normal distance from its 200-day average) is radioactive — in the
    backtest that cohort ran 9% return on 50% vol with a −94% drawdown, −1.37 skew and
    1.64 crashes/yr, vs the full top cohort's 18.9% / 25% / −49% / 0.41. THAT stark gap is
    the validated basis for the parabolic flag.

So this module is descriptive, graded, honest:

  ext_z      price/SMA200 − 1, z-scored vs the name's OWN trailing 252d  (own-history extension)
  near_52wh  price / trailing-252d max                                   (George-Hwang proximity)
  id_score   −[sgn(PRET)·(%neg − %pos)] over the 12-1 window             (frog-in-the-pan continuity)
  grade      in-trend / steady / stretched / parabolic                   (the display chip)
  val        current earnings-yield vs the name's own ~3y history        (valuation-vs-own, coarse)

All from the daily close matrix the page already loads — NO new data, NEVER scored.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

# grade thresholds — ext_z>2 is the validated parabolic flag; 1..2 stretched.
PARABOLIC_Z = 2.0
STRETCHED_Z = 1.0
INTREND_NEAR = 0.85        # within 15% of its own 52w high
INTREND_MAX_Z = 1.0        # ...and not stretched vs its own trend

# grade: (label_en, label_zh, css, is_caution)
GRADES = {
    "intrend":   ("In-trend",  "趋势内", "ex-intrend",   False),  # leader in its range, not stretched
    "steady":    ("Steady",    "平稳",   "ex-steady",    False),
    "stretched": ("Stretched", "拉伸",   "ex-stretched", True),
    "parabolic": ("Parabolic", "抛物",   "ex-parabolic", True),   # the validated radioactive flag
    "na":        ("—",         "—",      "ex-na",        False),
}

VAL_LABELS = {
    # label key: (en, zh, css)
    "cheap":    ("Cheap vs own", "相对自身偏低", "val-cheap"),
    "rich":     ("Rich vs own",  "相对自身偏高", "val-rich"),
    "richest":  ("Richest in 3y", "近3年最贵",   "val-richest"),
}

# ---- where the read is anchored: VINTAGE, and it is fail-closed -------------
# ext_z is a PER-NAME own-history quantity: each name's distance from its own 200-day
# average, z-scored against its OWN trailing 252 days along the DATE axis. It is not a
# cross-sectional score, so nothing here is about small-n sigma or one shared
# distribution. What the board does need is that a reading stamped "today" IS today's,
# because consumers score on it with hard cutoffs (us_board_rank's runway leg and the
# parabolic veto; cohort_stretch's median and tier thresholds below).
#
# Measured defect (US board, run of 2026-08-06): the equity close panel's newest row
# held 6 of 3,034 members — a partial price advance caught mid-refresh; the artifact's
# staleness block read `panel.through=2026-08-07, majority_through=2026-08-06,
# members_at_through=6, mixed_vintage=true`. `.iloc[-1]` read that row, so the
# extension map collapsed to those 6 names and all 69 buy-lane rows came back
# `ext_z=None`.
#
# Walking back to the last well-covered row heals that — but a walk-back that is not
# bounded and not disclosed just swaps a visible outage for an invisible one: an OLDER
# session's ext_z served as if it were current, into legs that cannot see its age. So
# the anchor is bounded on both sides:
#
#   * COVERAGE decides WHICH row, and it is measured on the RESOLVABILITY of ext_z (the
#     quantity actually served), never on close presence. A panel can be 100% covered in
#     closes and resolve ext_z for nobody — 210 rows of gapless prices serve 0 names,
#     because ext_z needs EXT_Z_MIN_ROWS. A floor read off `px.notna()` cannot see that.
#   * AGE decides WHETHER to serve at all. Past ANCHOR_MAX_AGE rows the value is NOT
#     served — omitted with a printed reason — so no consumer can score a stale read
#     unknowingly. Every served row carries `ext_asof` AND `ext_age`.
ANCHOR_COVERAGE_FLOOR = 0.60
# 0.60 is not a snapshot pick. Replayed over the committed close stores
# (tests/test_extension.py::TestTheFloorIsCalibratedOnRealSessions), ~2,000 real
# single-calendar sessions never resolve below 95% of live members, and the broken
# shapes sit at 0.2% (the partial advance above) and 50% (a 5-session equity calendar
# sharing one panel with 24/7 crypto). The floor sits in an EMPTY band between them, so
# any value in roughly (0.55, 0.95) behaves identically on the evidence — the constant
# is a choice inside a gap, not a threshold fitted to one draw.
#
# The anchor may be at most this many panel rows behind the newest row. One row is the
# measured mid-refresh partial advance; two covers a partial advance that straddles a
# calendar boundary. THREE consecutive uncovered rows is not a refresh race, it is an
# outage, and an outage must not be dressed as today's reading: past this the read is
# withheld entirely rather than backdated.
ANCHOR_MAX_AGE = 2
# The coverage floor is a statement about a PANEL. Below this many live members it
# stops being one: at n_live=3 a single absent name is 33 points of coverage, so the
# 60% floor becomes a per-name gate wearing a panel's clothes — one name goes quiet and
# all three, including the one that DID print, get read off the previous row. Small
# frames (`intl_equity_risk` passes ONE column; `replay_standout_pipeline` passes one
# per ticker) therefore skip the walk-back entirely and read their newest row, exactly
# as they did before the anchor existed. At 20 members one absence moves coverage by 5
# points, so the floor stands 8 names clear of any single member.
ANCHOR_MIN_LIVE = 20
# Disclosure band for an anchor whose coverage sits just above the floor. The floor is
# a cliff and this module holds no cross-build state to hysterese against (that would
# need a persisted anchor ledger); what it CAN do is say when the choice is unstable —
# measured, one extra absent name flips names-served 61 -> 100 and the anchor back a
# session. Inside this band the build log says so.
ANCHOR_MARGIN_NOTE = 0.10
# Liveness is the coverage DENOMINATOR and nothing else: which columns count as members
# of this panel. Judged over a quarter, not over the anchor window — if it were judged
# over the same 2-3 rows, a panel that went dark would redefine its membership down to
# the handful of survivors and read 100% covered, and the broken panel would look
# healthy. A quarter with no print is dead or suspended; three sessions with no print is
# an outage, and an outage has to be able to fail the floor.
LIVE_LOOKBACK = 63
# Rows a GAPLESS column needs before ext_z resolves at all: 100 for sma200's
# min_periods, then 120 more for the 252d z's min_periods. Below this, an empty return
# is the documented "too little history" degradation; at or above it, an empty return
# means something is wrong and is announced. Pinned by measurement, not by arithmetic —
# see test_ext_z_first_resolves_exactly_at_EXT_Z_MIN_ROWS.
EXT_Z_MIN_ROWS = 219


def grade(ext_z: float | None, near_52wh: float | None) -> str:
    """Descriptive extension grade from own-history extension. Risk-placement, not a
    return/drawdown claim (the Phase-0 test showed freshness does NOT cut drawdown)."""
    if ext_z is None or (isinstance(ext_z, float) and np.isnan(ext_z)):
        return "na"
    if ext_z >= PARABOLIC_Z:
        return "parabolic"
    if ext_z >= STRETCHED_Z:
        return "stretched"
    if near_52wh is not None and not np.isnan(near_52wh) \
            and near_52wh >= INTREND_NEAR and ext_z < 0.5:
        return "intrend"
    return "steady"


def _latest(s: pd.Series) -> float | None:
    if s is None or s.empty:
        return None
    v = s.iloc[-1]
    return float(v) if pd.notna(v) else None


def _row_label(index: pd.Index, pos: int) -> str | None:
    """Human/JSON label for the anchored row — the session the read is FROM."""
    if index is None or pos < 0 or pos >= len(index):
        return None
    v = index[pos]
    if isinstance(index, pd.DatetimeIndex) or isinstance(v, pd.Timestamp):
        return str(pd.Timestamp(v).date())
    return str(v)


class _Anchor(NamedTuple):
    """Which row the read is taken from, and everything needed to disclose it.

    `pos < 0` means NOTHING IS SERVED — the fail-closed outcome. `reason` is the
    machine-readable form of why, and it is what selects the build-log annotation.
    """
    pos: int              # row position to read; < 0 == withheld
    age: int              # panel rows between the anchor and the newest row (0 == current)
    asof: str | None      # label of the anchored row (of the newest row when withheld)
    newest_cov: float     # resolvability coverage of the newest row
    anchor_cov: float     # ...and of the anchored row
    n_live: int           # coverage denominator: members resolvable in the last quarter
    skipped: int          # members that DID resolve on a row the anchor walked past
    reason: str           # current | shifted | small_panel | uncovered | unresolvable | empty


def _anchor_row(ez: pd.DataFrame, max_age: int) -> _Anchor:
    """Choose the row the read is taken from, on the RESOLVABILITY of ext_z.

    `ez` is the ext_z matrix — the quantity actually served — not the close matrix.
    Gating on `px.notna()` measures the wrong thing: a 300-name panel with 210 rows of
    gapless closes is 100% "covered" and resolves ext_z for nobody.

    The rules, in order:
      * nothing resolvable anywhere in the last quarter -> withheld (`unresolvable`);
      * fewer than ANCHOR_MIN_LIVE live members -> the newest row, no walk-back, because
        a fraction floor over a handful of names is a per-name gate (`small_panel`);
      * otherwise the most recent row within `max_age` rows clearing
        ANCHOR_COVERAGE_FLOOR (`current` when that is the newest row, else `shifted`);
      * no such row -> withheld (`uncovered`). NOT "read the newest anyway": that is
        what published a partial advance as a board-wide blank, and NOT "reach further
        back", which publishes a stale cross-section as today's.

    "Live members" = columns resolving ext_z at least once in the last LIVE_LOOKBACK
    rows, so names delisted or suspended months ago never sit in the denominator and
    drag the floor out of reach on a perfectly healthy session.
    """
    n = len(ez.index)
    if n == 0:
        return _Anchor(-1, 0, None, 0.0, 0.0, 0, 0, "empty")
    newest = n - 1
    label = _row_label(ez.index, newest)
    ok = ez.notna()
    live = ok.iloc[-min(LIVE_LOOKBACK, n):].any(axis=0)
    n_live = int(live.sum())
    if n_live == 0:
        return _Anchor(-1, 0, label, 0.0, 0.0, 0, 0, "unresolvable")
    cov = (ok.loc[:, live].sum(axis=1) / n_live).to_numpy(dtype=float)
    newest_cov = float(cov[newest])
    if n_live < ANCHOR_MIN_LIVE:
        return _Anchor(newest, 0, label, newest_cov, newest_cov, n_live, 0, "small_panel")
    for p in range(newest, max(0, newest - max(0, int(max_age))) - 1, -1):
        if cov[p] >= ANCHOR_COVERAGE_FLOOR:
            skipped = int(ok.iloc[p + 1:].any(axis=0).sum()) if p < newest else 0
            return _Anchor(p, newest - p, _row_label(ez.index, p), newest_cov,
                           float(cov[p]), n_live, skipped,
                           "current" if p == newest else "shifted")
    return _Anchor(-1, 0, label, newest_cov, 0.0, n_live, 0, "uncovered")


def extension_signals(closes: pd.DataFrame, *,
                      max_age: int = ANCHOR_MAX_AGE) -> dict[str, dict]:
    """Per-ticker {ext, ext_z, near_52wh, id_score, grade, parabolic, ext_asof, ext_age}
    from a daily close matrix (date × ticker). Mirrors scripts/top_picks_freshness_phase0.
    price_signals so the live chip equals the back-tested quantity. Names with too little
    history are omitted (the page degrades to no chip).

    The read is anchored by COVERAGE, not by position — see the note beside
    ANCHOR_COVERAGE_FLOOR for the 6-of-3,034 partial price advance this exists to
    survive — and the anchor is bounded by AGE:

      * `ext_asof` is the session the reading is from and `ext_age` is how many panel
        rows behind the newest row that is (0 on a normal build). Both are on EVERY
        served row, so a consumer that scores on ext_z can see the vintage it is
        scoring.
      * past `max_age` rows the value is NOT SERVED. An empty return plus a printed
        reason is the honest outcome; a stale reading dressed as today's is not.
      * `max_age=0` is STRICT: current session or nothing. Any caller that stamps a
        reading into a dated history — a percentile ledger, a forward log — must pass
        it, because such a caller labels the value with ITS OWN asof and the age is
        lost the moment it is written.

    A name with no resolvable ext_z ON the anchored row is still omitted, one name at a
    time. Nothing here is ever filled forward, and no name is ever read off a different
    row than the rest of the panel.

    The vintage trade, stated plainly: when the anchor is `shifted`, the rows it walked
    past failed the coverage floor, so they are mid-refresh fragments rather than
    sessions — a member that happened to print on one of them is read off the anchor
    like everyone else (the alternative, serving it its own newer value, would mix
    vintages WITHIN the panel and is worse). ANCHOR_MIN_LIVE is what keeps that
    defensible: it stops the fraction floor from ever acting on a handful of names."""
    if closes is None or closes.empty:
        return {}
    px = closes.sort_index()
    R = px.pct_change(fill_method=None)

    sma200 = px.rolling(200, min_periods=100).mean()
    ext = px / sma200 - 1.0
    ext_z = (ext - ext.rolling(252, min_periods=120).mean()) \
        / ext.rolling(252, min_periods=120).std().replace(0, np.nan)
    near = px / px.rolling(252, min_periods=120).max()

    pret = px.shift(21) / px.shift(252) - 1.0
    sgn = np.sign(R)
    win = 252 - 21
    up_frac = (sgn > 0).rolling(win, min_periods=120).mean().shift(21)
    dn_frac = (sgn < 0).rolling(win, min_periods=120).mean().shift(21)
    id_score = -(np.sign(pret) * (dn_frac - up_frac))

    a = _anchor_row(ext_z, max_age)
    if a.reason == "unresolvable":
        # A PANEL that resolves nothing is a defect and must not be silent — this is the
        # shape a close-presence gate cannot see (300 names × 210 rows of gapless closes
        # is 100% "covered" and serves nobody). A one- or few-column frame resolving
        # nothing is the documented per-name degradation, and stays quiet: those callers
        # ask per ticker and would turn an ordinary short history into annotation spam.
        if px.shape[1] >= ANCHOR_MIN_LIVE:
            print(f"::warning title=extension-unresolvable::no ticker resolves ext_z on "
                  f"{px.shape[0]} rows × {px.shape[1]} columns through {a.asof}: closes "
                  f"can be complete and ext_z still resolve for nobody, because it needs "
                  f"{EXT_Z_MIN_ROWS} rows of a NAME'S OWN history (200d average, then a "
                  f"252d z over it); serving no extension read", flush=True)
        return {}
    if a.reason == "uncovered":
        print(f"::warning title=extension-anchor-uncovered::no row within "
              f"{max_age} of {a.asof} resolves ext_z for {ANCHOR_COVERAGE_FLOOR:.0%} of "
              f"{a.n_live} live members (newest {a.newest_cov:.1%}); serving NO extension "
              f"read rather than a reading older than {max_age} session(s) stamped as "
              f"today's — the panel needs the fix", flush=True)
        return {}
    if a.reason == "shifted":
        print(f"::warning title=extension-anchor-shifted::extension read anchored to "
              f"{a.asof}, {a.age} row(s) behind the newest panel row: that row resolves "
              f"ext_z for {a.newest_cov:.1%} of {a.n_live} live members, under the "
              f"{ANCHOR_COVERAGE_FLOOR:.0%} floor. {a.skipped} member(s) that did resolve "
              f"on the skipped row(s) are read off {a.asof} too — every served row carries "
              f"ext_age={a.age}", flush=True)
    if a.reason in ("current", "shifted") \
            and a.anchor_cov < ANCHOR_COVERAGE_FLOOR + ANCHOR_MARGIN_NOTE:
        print(f"::warning title=extension-anchor-marginal::the anchor at {a.asof} clears "
              f"the {ANCHOR_COVERAGE_FLOOR:.0%} floor by only {a.anchor_cov - ANCHOR_COVERAGE_FLOOR:.1%} "
              f"({a.anchor_cov:.1%} of {a.n_live} live members), so a few more absent "
              f"names would move it back a session and change how many names are served",
              flush=True)

    ext_l, ez_l, near_l, id_l = (ext.iloc[a.pos], ext_z.iloc[a.pos],
                                 near.iloc[a.pos], id_score.iloc[a.pos])
    out: dict[str, dict] = {}
    for t in px.columns:
        ez = ez_l.get(t)
        nr = near_l.get(t)
        # per-name null: a name with no resolvable ext_z on the anchored session stays
        # unknown rather than borrowing an older one — the floor heals the PANEL, not
        # the name.
        if ez is None or pd.isna(ez):
            continue
        g = grade(float(ez), float(nr) if pd.notna(nr) else None)
        out[t] = {
            "ext": round(float(ext_l[t]) * 100, 1) if pd.notna(ext_l.get(t)) else None,
            "ext_z": round(float(ez), 2),
            "near_52wh": round(float(nr), 3) if pd.notna(nr) else None,
            "id_score": round(float(id_l[t]), 3) if pd.notna(id_l.get(t)) else None,
            "grade": g,
            "parabolic": g == "parabolic",
            # vintage, unconditionally on the schema: a consumer that reads neither is
            # no worse off than before, and one that reads either cannot be surprised.
            "ext_asof": a.asof,        # which session this reading is from
            "ext_age": a.age,          # ...and how many panel rows back that is
        }
    return out


def valuation_vs_history(closes: pd.DataFrame, panel: pd.DataFrame) -> dict[str, dict]:
    """Per-ticker current earnings-yield percentile vs the name's OWN history over the
    price window available. EY_t = EPS_known_at_t / price_t, where EPS steps on each annual
    filing (PIT via asof_date) — so it reflects both price AND earnings, not price alone.

    Returns {ticker: {ey_pctile, val_label}} only for names where the read is meaningful
    (>=120 daily obs). Coarse (annual EPS) and window-limited — a display/context flag,
    never scored. `val_label` is set only at the tails (cheap / rich / richest)."""
    if closes is None or closes.empty or panel is None or panel.empty:
        return {}
    p = panel.dropna(subset=["asof_date"]).copy()
    p["asof_date"] = pd.to_datetime(p["asof_date"])
    p = p.sort_values("asof_date")
    px = closes.sort_index()
    idx = px.index
    out: dict[str, dict] = {}
    for t, grp in p.groupby("ticker"):
        if t not in px.columns:
            continue
        price = px[t].dropna()
        if len(price) < 120:
            continue
        g = grp[["asof_date", "ni", "shares"]].dropna()
        g = g[(g["shares"] > 0)]
        if g.empty:
            continue
        # step EPS series aligned to the price index (latest filing with asof_date <= date)
        eps = (g.set_index("asof_date")["ni"] / g.set_index("asof_date")["shares"])
        eps = eps[~eps.index.duplicated(keep="last")].sort_index()
        eps_daily = eps.reindex(idx, method="ffill")
        ey = (eps_daily / price).replace([np.inf, -np.inf], np.nan).dropna()
        ey = ey[ey != 0]
        if len(ey) < 120:
            continue
        cur = ey.iloc[-1]
        pct = float((ey <= cur).mean() * 100)        # high pct = cheap (high earnings yield)
        label = None
        if pct >= 66:
            label = "cheap"
        elif pct <= 10:
            label = "richest"
        elif pct <= 33:
            label = "rich"
        out[t] = {"ey_pctile": round(pct), "val_label": label}
    return out


def cohort_stretch(readings: list[dict]) -> dict:
    """Board-level fragility gauge from the top-conviction cohort's extension readings.
    DISPLAY-ONLY sizing context — crowding/stretch raises crash *probability*, it does not
    time the market (Asness: factor timing is hard). Never a fade, never gates the rank.

    `readings` = per-name dicts (the top-conviction slice) with ext_z / near_52wh / grade.
    Returns {state, median_ext_z, pct_parabolic, pct_stretched, pct_at_highs, n,
    asof, age, mixed_vintage}.

    The tiers below are hard cutoffs on ext_z, so the gauge carries the VINTAGE of the
    readings it tiered — it is the first consumer that would otherwise score a stale
    read blind. `age` is the OLDEST reading in the slice (worst case, not average), and
    `mixed_vintage` is true when the slice spans more than one session: a caller that
    unions two independently anchored panels (build_stock_library reads equities and
    crypto off separate calendars, by design) can hand this function a cohort that has
    no single asof, and that has to be visible rather than averaged away."""
    ez = [r["ext_z"] for r in readings if r.get("ext_z") is not None]
    asofs = {r.get("ext_asof") for r in readings if r.get("ext_z") is not None}
    ages = [r["ext_age"] for r in readings
            if r.get("ext_z") is not None and r.get("ext_age") is not None]
    vintage = {
        "asof": next(iter(asofs)) if len(asofs) == 1 else None,
        "age": max(ages) if ages else None,
        "mixed_vintage": len(asofs) > 1,
    }
    if len(ez) < 8:
        return {"state": "na", "n": len(ez), **vintage}
    n = len(ez)
    med = float(np.median(ez))
    pct_parab = 100 * sum(1 for r in readings if r.get("grade") == "parabolic") / n
    pct_stretch = 100 * sum(1 for r in readings
                            if r.get("grade") in ("stretched", "parabolic")) / n
    pct_highs = 100 * sum(1 for r in readings
                          if (r.get("near_52wh") or 0) >= 0.95) / n
    # state: descriptive tiers on how stretched the leadership cohort is vs its own norms
    if med >= 1.0 or pct_stretch >= 45 or pct_parab >= 12:
        state = "stretched"
    elif med >= 0.5 or pct_stretch >= 30:
        state = "elevated"
    else:
        state = "normal"
    return {"state": state, "median_ext_z": round(med, 2),
            "pct_parabolic": round(pct_parab), "pct_stretched": round(pct_stretch),
            "pct_at_highs": round(pct_highs), "n": n, **vintage}
