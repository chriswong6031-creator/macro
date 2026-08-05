"""Dark-pool signal layer — the metrics the desk ranks and describes on.

WHY THIS MODULE EXISTS
----------------------
The desk previously derived everything from two numbers: off-exchange participation
(`oe_share`) and the FINRA short-marked ratio. Four defects followed from that, all
measured on the live store on 2026-08-05:

  1. RANKED A CONSTANT. The desk sorted by the raw participation LEVEL. A variance
     decomposition over the 47-date panel put 42.7% of `oe_share` variance in a fixed
     per-name effect (top-20 overlap day-over-day 45%; cross-sectional rank autocorr
     0.58 at lag 1, 0.45 at lag 20). Retail-heavy and thinly-traded names print more
     off-exchange every day, so ranking by level spends the front of the board on
     structure rather than news. `unusualness` here ranks each name against ITS OWN
     norm, which is the part that actually moves.

  2. IN-SAMPLE Z. `oe_z` used the mean and population σ of the entire available
     series INCLUDING the current observation, over an expanding window. A genuinely
     big day inflates its own σ and drags the mean toward itself, suppressing the very
     z-score meant to flag it. `trailing_z` below excludes the current observation and
     uses a fixed lookback with median/MAD, which fat-tailed participation needs.

  3. ONE-DAY MEMORY. A single spike and a ten-session campaign scored identically.
     Desks read the campaign. `streak` counts consecutive sessions above the name's
     own trailing median.

  4. NO PRICE, SO NO CONFLUENCE. The builder read only the `volume` column. Without
     price you cannot tell heavy hidden volume meeting supply from heavy hidden volume
     chasing strength — which is exactly why the old module's direction call had no
     basis to stand on.

HOUSE LAW (binding — read before adding any directional wording here)
---------------------------------------------------------------------
`research/DO_NOT_REBUILD.md` (PSS-AF1 row) and the PSS-AF1 charter:

    "FINRA short volume is not short interest, net selling, or institutional buying.
     Raw short ratio/off-exchange share remains forbidden as a standalone direction
     signal."

So nothing in this module emits a direction. `pattern` names the CONJUNCTION that was
observed (heavy hidden volume + which way price went over the same stretch) and stops
there. That is a description of settled facts, not a call, and it is not standalone —
which is the whole reason price had to come in. Everything here is deterministic
threshold arithmetic on already-observed data: no model, no LLM origination, no score
with authority (display tier only). The word "validated" is never emitted.

MEASUREMENT STATUS (honest null — printed, not hidden)
------------------------------------------------------
The predecessor's accumulation/distribution tag was walk-forward tested on the panel
available at 2026-08-05 (47 dates, n=86 accumulation / 61 distribution events):

    horizon   acc-minus-dist    t      p
    1d            +0.22%       0.33   0.74
    5d            -0.87%      -0.63   0.53
    10d           -0.10%      -0.05   0.96

The sign flips across horizons and nothing approaches significance. That is NOT a
refutation — 47 dates cannot refute anything — it is an absence of any basis for the
directional copy the page was shipping. `data/darkpool/ledger/` now accrues a forward
record so the question becomes answerable instead of assumed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── windows + floors (deterministic; surfaced in the page methodology) ──────────
Z_WINDOW      = 252    # trailing sessions for the participation baseline (~1y)
Z_MIN_OBS     = 40     # below this the z is None (honest null, never forced to 0)
STREAK_WINDOW = 60     # baseline window for the "above own norm" streak
PRICE_WINDOW  = 5      # sessions of price change paired with the participation read
MAD_SCALE     = 1.4826 # MAD → σ-equivalent for a normal

# pattern thresholds
HEAVY_Z       = 1.5    # participation this far above own norm = "heavy"
PRICE_FLAT_PCT = 1.0   # |move| under this over PRICE_WINDOW = "going nowhere"

# level break in a participation series ⇒ the share units changed under it (a split).
# Market-wide drift is ~1.2x/3y, so 1.8 has wide margin against firing on a real trend.
SPLIT_BREAK_FACTOR = 1.8


# ── robust statistics ──────────────────────────────────────────────────────────

def trailing_z(values: pd.Series | np.ndarray | list, *,
               window: int = Z_WINDOW, min_obs: int = Z_MIN_OBS,
               robust: bool = True) -> float | None:
    """z of the LAST value against the `window` observations BEFORE it.

    Excluding the current observation is the point: including it lets a spike inflate
    its own dispersion and shift its own centre, which is precisely backwards for an
    outlier detector. Returns None (never 0.0) when history is too thin — a null here
    means "not enough history to say", and the desk must render it as such.

    robust=True uses median/MAD, which off-exchange participation needs (fat right
    tail on index-rebalance and block days). Falls back to mean/σ when MAD is 0,
    which happens on near-constant series.
    """
    s = pd.Series(values, dtype="float64").dropna()
    if len(s) < min_obs + 1:
        return None
    cur = float(s.iloc[-1])
    hist = s.iloc[-(window + 1):-1]          # trailing baseline, current EXCLUDED
    if len(hist) < min_obs:
        return None

    if robust:
        med = float(hist.median())
        mad = float((hist - med).abs().median())
        scale = mad * MAD_SCALE
        if scale > 0:
            return round((cur - med) / scale, 2)

    mu = float(hist.mean())
    sd = float(hist.std(ddof=0))
    if sd <= 0:
        return None
    return round((cur - mu) / sd, 2)


def share_break_index(values: pd.Series, *, window: int = 20,
                      factor: float = SPLIT_BREAK_FACTOR) -> int | None:
    """Index of the LAST sustained level break in a participation series, or None.

    WHY THIS IS NECESSARY — the split trap.
    Participation is (FINRA off-exchange shares ÷ consolidated shares). The numerator
    comes from FINRA's daily file exactly as reported on the day. The denominator comes
    from the price vendor, which RETROACTIVELY split-adjusts its volume history. After
    an N:1 split, every pre-split day therefore reads participation ÷ N.

    Measured on the 3-year panel (2026-08-05), 7 of 225 names carried a corrupted
    baseline, and they are precisely the known splitters:

        BKNG 30.9x   ORLY 21.4x   LRCX 11.4x   KLAC 10.5x
        AVGO 10.1x   SMCI  8.8x   MSTR  7.8x

    BKNG read 1.0% participation in 2023 against 31.7% now — which then produced a
    z-score of +53 for a day that was actually BELOW the name's own norm, because the
    bimodal history made the MAD meaningless.

    This is invisible on a short panel (no split falls inside 47 days), so it only
    surfaced once real history landed — and any future split silently re-creates it.

    Detection, not correction: the true split factor is not recoverable from the store
    (both vendor price columns are already split-adjusted; they differ only by
    dividends). Callers truncate the baseline at the break instead, so a name is only
    ever compared against history measured in the same share units.

    The market's own secular drift is ~1.2x over three years, so a 1.8x threshold has
    wide margin against firing on a genuine trend.
    """
    s = pd.Series(values, dtype="float64").dropna()
    if len(s) < window * 2 + 1:
        return None
    med = s.rolling(window, min_periods=max(5, window // 2)).median()
    last: int | None = None
    for i in range(window, len(s)):
        pre, post = med.iloc[i - window], med.iloc[i]
        if pre and post and pre > 0:
            ratio = post / pre
            if ratio >= factor or ratio <= 1.0 / factor:
                last = i
    return last


def usable_history(values: pd.Series) -> pd.Series:
    """The tail of a participation series that is comparable to its current value.

    Returns everything after the last share-count break (see share_break_index), or the
    whole series when none is found. Short results are the honest outcome — trailing_z
    returns None below its min_obs floor rather than scoring against mixed units.
    """
    s = pd.Series(values, dtype="float64").dropna()
    idx = share_break_index(s)
    return s.iloc[idx:] if idx is not None else s


def streak_above_norm(values: pd.Series | np.ndarray | list,
                      *, window: int = STREAK_WINDOW) -> int:
    """Consecutive sessions (ending today) at or above the trailing median.

    A campaign, not a spike: institutions working a position leave a run of elevated
    sessions. The median is recomputed at each step from the sessions strictly before
    it, so the streak never reads a value against a baseline it helped set.

    Comparison is STRICTLY above the median. With `>=`, a perfectly flat series scores
    a maximal streak (every value ties its own median), which would then inflate that
    name's `unusualness` ranking for having done nothing at all.
    """
    s = pd.Series(values, dtype="float64").dropna()
    if len(s) < 5:
        return 0
    n = 0
    for i in range(len(s) - 1, -1, -1):
        hist = s.iloc[max(0, i - window):i]
        if len(hist) < 5:
            break
        if float(s.iloc[i]) > float(hist.median()):
            n += 1
        else:
            break
    return n


# ── per-name metrics ───────────────────────────────────────────────────────────

@dataclass
class NameMetrics:
    """Everything the desk knows about one name's off-exchange footprint."""
    ticker: str
    participation: float | None = None      # off-exchange share of consolidated volume
    participation_z: float | None = None    # vs OWN trailing norm (current excluded)
    participation_norm: float | None = None # the trailing median it is measured against
    participation_5d: float | None = None   # 5-session mean
    participation_trend_pp: float | None = None  # 5d mean minus 40d mean, in pp
    streak: int = 0                         # consecutive sessions above own norm
    offex_dollars: float | None = None      # off-exchange notional traded, USD
    short_rate: float | None = None         # short-marked share of the off-exchange tape
    short_rate_z: float | None = None
    short_trend_pp: float | None = None     # recent-minus-baseline, pp
    exempt_rate: float | None = None        # short-exempt share (was collected, never used)
    exempt_z: float | None = None
    price_change_pct: float | None = None   # over PRICE_WINDOW sessions
    pattern: str | None = None              # conjunction label — NOT a direction
    ats_frac: float | None = None           # ATS ÷ (ATS + non-ATS) off-exchange shares
    ats_block_shares: float | None = None   # avg ATS print size
    nonats_block_shares: float | None = None
    avg_print_price: float | None = None
    top_ats_venue: str | None = None
    top_nonats_firm: str | None = None
    n_obs: int = 0
    history_rebased: bool = False   # baseline restarted after a share-count break (split)
    n_usable: int = 0               # comparable observations behind the z
    extras: dict = field(default_factory=dict)


def _pattern(participation_z: float | None, price_change_pct: float | None) -> str | None:
    """Name the observed CONJUNCTION. Never a direction — see HOUSE LAW above.

    Only fires when participation is genuinely heavy vs the name's own norm AND a
    price change is available. Anything else is None so the desk can say so plainly.
    """
    if participation_z is None or price_change_pct is None:
        return None
    if participation_z < HEAVY_Z:
        return None
    if price_change_pct <= -PRICE_FLAT_PCT:
        return "heavy_into_weakness"
    if price_change_pct >= PRICE_FLAT_PCT:
        return "heavy_into_strength"
    return "heavy_price_flat"


def compute_name_metrics(
    ticker: str,
    finra: pd.DataFrame,
    consolidated_vol: pd.Series | None,
    close: pd.Series | None,
    venue: dict | None = None,
) -> NameMetrics:
    """Build one name's metrics from its FINRA rows + consolidated volume + price.

    `finra` needs columns date/short_vol/short_exempt/total_vol/short_ratio.
    `consolidated_vol` and `close` are date-indexed; either may be None, and every
    metric that depends on a missing input stays None rather than being faked.
    """
    m = NameMetrics(ticker=ticker)
    if finra.empty:
        return m

    f = finra.drop_duplicates("date", keep="last").set_index("date").sort_index()
    m.n_obs = len(f)

    # short-marked rate on the off-exchange tape + its own norm
    if "short_ratio" in f.columns:
        ratios = f["short_ratio"].astype("float64")
        m.short_rate = round(float(ratios.iloc[-1]), 4)
        m.short_rate_z = trailing_z(ratios)
        r5 = f.tail(5); r40 = f.tail(40)
        if r5["total_vol"].sum() > 0 and r40["total_vol"].sum() > 0:
            recent = r5["short_vol"].sum() / r5["total_vol"].sum()
            base = r40["short_vol"].sum() / r40["total_vol"].sum()
            m.short_trend_pp = round(float((recent - base) * 100), 2)

    # short-EXEMPT rate — present in the panel since day one, never read until now.
    # Exempt marks sit outside the uptick-rule regime (bona-fide market making,
    # certain arbitrage), so a jump is a change in WHO is working the tape.
    if "short_exempt" in f.columns:
        tv = f["total_vol"].astype("float64")
        ex = (f["short_exempt"].astype("float64") / tv.where(tv > 0)).dropna()
        if not ex.empty:
            m.exempt_rate = round(float(ex.iloc[-1]), 5)
            m.exempt_z = trailing_z(ex)

    # off-exchange participation — exact-date inner join, never reindex/ffill
    if consolidated_vol is not None and not consolidated_vol.empty:
        j = f[["total_vol"]].join(consolidated_vol.rename("cons"), how="inner")
        j = j[j["cons"] > 0]
        if not j.empty:
            part_raw = (j["total_vol"] / j["cons"]).dropna()
            if not part_raw.empty:
                # Compare a name only against history in the SAME share units — a split
                # re-bases the vendor's volume history but not FINRA's. See
                # share_break_index for the seven names this was silently corrupting.
                part = usable_history(part_raw)
                m.history_rebased = len(part) < len(part_raw)
                m.n_usable = len(part)

                m.participation = round(float(part.iloc[-1]), 4)
                m.participation_z = trailing_z(part)
                hist = part.iloc[-(STREAK_WINDOW + 1):-1]
                if len(hist) >= 5:
                    m.participation_norm = round(float(hist.median()), 4)
                m.streak = streak_above_norm(part)
                t5, t40 = part.tail(5), part.tail(40)
                if len(t5) >= 1:
                    m.participation_5d = round(float(t5.mean()), 4)
                if len(t5) >= 1 and len(t40) >= 5:
                    m.participation_trend_pp = round(float((t5.mean() - t40.mean()) * 100), 2)
                m.extras["spark"] = [round(float(v), 3) for v in part.tail(20).tolist()]
                m.extras["part_dates"] = [str(d.date()) for d in part.tail(20).index]

    # dollar participation + price change (needs close)
    if close is not None and not close.empty:
        last_dt = f.index[-1]
        if last_dt in close.index:
            px = float(close.loc[last_dt])
            m.offex_dollars = round(float(f["total_vol"].iloc[-1]) * px, 2)
        cw = close.loc[close.index <= last_dt]
        if len(cw) > PRICE_WINDOW:
            a, b = float(cw.iloc[-(PRICE_WINDOW + 1)]), float(cw.iloc[-1])
            if a > 0:
                m.price_change_pct = round((b / a - 1) * 100, 2)

    m.pattern = _pattern(m.participation_z, m.price_change_pct)

    if venue:
        m.ats_frac = venue.get("ats_frac")
        m.ats_block_shares = venue.get("ats_block_shares")
        m.nonats_block_shares = venue.get("nonats_block_shares")
        m.avg_print_price = venue.get("avg_print_price")
        m.top_ats_venue = venue.get("top_ats_venue")
        m.top_nonats_firm = venue.get("top_nonats_firm")

    return m


# ── venue split: institutional dark pools vs wholesaler internalization ────────

def venue_split(ats: pd.DataFrame | None, nonats: pd.DataFrame | None) -> dict[str, dict]:
    """Per-ticker ATS-vs-non-ATS breakdown of the off-exchange tape.

    Off-exchange volume is ATS (registered dark pools) PLUS non-ATS OTC (wholesaler
    and broker internalization, predominantly retail marketable flow). The desk used
    to attribute all of it to "dark pool" while showing only the ATS venue table — so
    the table could never account for the headline. Measured week 2026-06-22, ATS was
    16-31% of each name's off-exchange total (AAPL 31.4%, NVDA 23.5%, TSLA 26.0%,
    GME 24.5%, F 16.5%), i.e. the table was explaining roughly a quarter of the number
    printed above it.

    `ats_frac` = ATS ÷ (ATS + non-ATS) is therefore how much of a name's hidden volume
    ran through institutional venues rather than being internalized against retail flow.

    NOTE non-ATS rows carry an EMPTY `mpid` (FINRA publishes the firm NAME only for
    non-ATS), so this keys non-ATS on `venue_name`. Any filter of the form
    `mpid.str.len() > 0` silently drops every non-ATS row.
    """
    out: dict[str, dict] = {}

    def _agg(df: pd.DataFrame | None, key: str) -> dict[str, dict]:
        if df is None or df.empty:
            return {}
        d = df.copy()
        if "notional" not in d.columns:      # weeks stored before 2026-08-05
            d["notional"] = np.nan
        g = d.groupby("ticker").agg(
            shares=("shares", "sum"),
            trades=("trades", "sum"),
            notional=("notional", "sum"),
        )
        top = (d.sort_values("shares", ascending=False)
                 .drop_duplicates("ticker")
                 .set_index("ticker")[key])
        res: dict[str, dict] = {}
        for tk, row in g.iterrows():
            res[str(tk)] = {
                "shares": float(row["shares"]),
                "trades": int(row["trades"]),
                "notional": float(row["notional"]) if pd.notna(row["notional"]) else None,
                "top": str(top.get(tk)) if tk in top.index else None,
            }
        return res

    a = _agg(ats, "venue_name")
    n = _agg(nonats, "venue_name")

    for tk in set(a) | set(n):
        ai, ni = a.get(tk), n.get(tk)
        ash = ai["shares"] if ai else 0.0
        nsh = ni["shares"] if ni else 0.0
        tot = ash + nsh
        rec: dict = {
            "ats_shares": ash or None,
            "nonats_shares": nsh or None,
            "ats_frac": round(ash / tot, 4) if tot > 0 else None,
            "ats_block_shares": round(ai["shares"] / ai["trades"], 1) if ai and ai["trades"] else None,
            "nonats_block_shares": round(ni["shares"] / ni["trades"], 1) if ni and ni["trades"] else None,
            "top_ats_venue": ai["top"] if ai else None,
            "top_nonats_firm": ni["top"] if ni else None,
        }
        # Average print price must divide notional by the shares of the SAME legs that
        # supplied that notional. Weeks stored before 2026-08-05 carry no `notional`
        # column, so during the changeover one leg has it and the other does not —
        # dividing a one-leg notional by both legs' shares understated AAPL's average
        # print price as $195.60 against a ~$285 tape. Legs without notional are
        # excluded from BOTH sides of the ratio instead.
        num = den = 0.0
        for leg, sh in ((ai, ash), (ni, nsh)):
            if leg and leg["notional"] and sh > 0:
                num += leg["notional"]
                den += sh
        if num > 0 and den > 0:
            rec["avg_print_price"] = round(num / den, 2)
            rec["avg_print_price_partial"] = bool(den < tot)   # only one leg contributed
        out[tk] = rec
    return out


# ── market-wide gauge ──────────────────────────────────────────────────────────

def market_gauge(metrics: list[NameMetrics]) -> dict:
    """Dollar-weighted market-wide off-exchange participation for the session.

    Share-count weighting lets a $3 name count the same as a $300 name; desks weight
    by notional. This is a DESCRIPTIVE gauge of how much of the day's dollar volume
    printed away from the lit tape — it carries no direction and no authority.

    Returns nulls (never 0) when the inputs are missing, so the page can say so.
    """
    usable = [m for m in metrics if m.participation is not None and m.offex_dollars]
    if not usable:
        return {"participation_dollar_wtd": None, "participation_median": None,
                "n_names": 0, "n_heavy": 0, "offex_dollars_total": None}

    total_dollars = sum(m.offex_dollars for m in usable)
    # off-exchange dollars ÷ implied consolidated dollars (offex_dollars / participation)
    implied_consolidated = sum(
        m.offex_dollars / m.participation for m in usable if m.participation and m.participation > 0
    )
    dw = (total_dollars / implied_consolidated) if implied_consolidated > 0 else None

    parts = [m.participation for m in metrics if m.participation is not None]
    heavy = [m for m in metrics if m.participation_z is not None and m.participation_z >= HEAVY_Z]
    return {
        "participation_dollar_wtd": round(dw, 4) if dw else None,
        "participation_median": round(float(np.median(parts)), 4) if parts else None,
        "n_names": len(parts),
        "n_heavy": len(heavy),
        "offex_dollars_total": round(total_dollars, 2),
    }


# ── ranking ────────────────────────────────────────────────────────────────────

def unusualness(m: NameMetrics) -> float:
    """Display-only ordering key: how far off its OWN norm this name is trading.

    NOT a score, NOT a signal, NOT calibrated — an ordering so the board leads with
    what changed rather than with the same structurally-dark names every session
    (42.7% of raw participation variance is a fixed per-name effect).

    Deliberately does NOT include the raw participation level; that is the structural
    part we are trying to rank around. Streak and dollar size break ties toward the
    names a desk would actually look at first.
    """
    if m.participation_z is None:
        return -1.0
    v = float(m.participation_z)
    v += min(m.streak, 10) * 0.06                      # sustained > one-off
    if m.offex_dollars:                                 # size tiebreak, log-damped
        v += min(np.log10(max(m.offex_dollars, 1.0)) / 10.0, 1.0)
    if m.short_rate_z is not None:
        v += min(abs(float(m.short_rate_z)), 3.0) * 0.05  # either-way tape shift
    return round(v, 4)
