"""Share-count unit-artifact detector + PIT-honest repair for the EDGAR panel.

The frames-API share scan in collectors/edgar.py occasionally lands on the wrong
fact for a (cik, fy): a count reported in thousands/millions (GRMN 2013-17 carries
1.9e5 for a ~1.9e8 company), a placeholder registration count (OGS's pre-spin
"100 shares" next to $4B of assets), a different entity/share-class count (ED
fy2010-2015 carries 2.2e7 while ConEd had ~2.9e8 throughout), or a pre-IPO
founder/preferred count for a later-IPO name (ROKU fy2016 = 4.8M vs ~100M traded).
Each corrupts PIT mktcap = price x shares by 3-1000x for every backtest rebalance
that selects the row — independent of the known split-basis defect
(reports/pit-mktcap-split-defect-materiality.md, PR #2122), which this pass
deliberately does NOT touch: a real split changes the share basis with a matching
real event; a unit artifact has no event behind it.

Detection is structural (segment the per-ticker share history at >=1.8x jumps,
compare suspect segments against their nearest CLEAN flanking values) plus two
matter-of-record references fetched keylessly from yfinance and cached in
data/edgar/share_quality_reference.json: first-trade dates (a fiscal year that
ended before the ticker traded cannot describe the traded share class) and split
histories (a boundary that matches a real split is a basis change, not an
artifact — the split lane's job, not ours).

Repair discipline (PIT-honest): a row may only be repaired from data knowable at
its asof_date — the row's own value times a power of ten (scale typo), the same
fiscal year's DEI cover-page count (shares_dei, same filing family), or the last
clean PRIOR year's count (carry-forward). Detection may look at later rows
(comparing to the next fiscal year is how an artifact is recognized at all), but
a repair VALUE never comes from the future; where no PIT-legal repair exists the
shares are nulled so mktcap goes NaN instead of wrong. Original values are
preserved in shares_raw with the category in share_flag.

Flag categories
---------------
pre_public       row's fiscal year ended >30d before the ticker first traded —
                 the cover count describes a pre-public capital structure (NULL)
placeholder      shares < 1e5 with assets >= $1e8 — registration-statement
                 placeholder counts, no real filer is capitalized on <100k shares
                 (scale-snap repair if a x10^k lands on a clean flank, else NULL)
unit_scale       whole segment is a power-of-1000 off its clean flank(s) —
                 in-thousands / in-millions typos (repair = value x 10^k)
unit_level       interior segment >=3x off BOTH agreeing clean flanks, equity
                 continuous through the segment, no matching real split —
                 wrong-fact picks like ED (repair = same-FY shares_dei, else
                 carry-forward of last clean prior count, else NULL)
unit_extreme     segment >=100x off its clean flank(s) — never a real corporate
                 action (largest real split on record is 50:1) — but with no
                 confident power-of-ten snap and no level-repair evidence
                 (RTX fy2009 carries 1.38e6, junk that is not a clean x1000
                 either): NULL, honest NaN beats a guessed repair
pre_public_tiny  leading segment entirely < 15M shares, >=3x below everything
                 after it, equity discontinuous at the exit — SPAC founder /
                 pre-IPO counts that outlive the IPO by a filing lag, e.g. AHCO
                 fy2017-19 (NULL; a reverse split near the segment exempts it —
                 CPF's post-1:20 fy2010 count is real)

Known residuals (documented, conservative by design): trailing/leading LEVEL
artifacts without a power-of-10 signature are indistinguishable from real
corporate actions without a right flank and stay unflagged (trailing rows
self-resolve when the next fiscal year arrives); wrong-share-class picks with
discontinuous equity (VCTR fy2020) stay unflagged; the dead-name panel
(collectors/edgar_deadnames.py) has its own build path and is not covered here.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SEG_JUMP = 1.8              # consecutive-FY ratio that starts a new level segment
ART_RATIO = 3.0             # segment-vs-flank disagreement that marks an artifact
FLANK_AGREE = 1.6           # flanks (or snap-vs-flank) must agree within this
EQ_CONT_MAX = 2.0           # equity continuity bound for unit_level boundaries
EQ_JUMP_MIN = 2.5           # equity discontinuity floor for pre_public_tiny exits
TINY_MAX = 15e6             # pre_public_tiny: whole leading segment below this
TINY_MAX_ROWS = 4           # ... and at most this many rows: a sub-15M count that
                            # survives 5+ annual filings is a real traded basis
                            # (Skyline Corp held 8.39M shares 2011-2017), while
                            # founder/SPAC counts outlive the IPO by 1-3 filings
PUBLIC_LONG_BEFORE_DAYS = 730   # pre_public_tiny is exempt when the ticker was
                            # already trading 2y+ before the segment's first
                            # fiscal end — a real listed micro-cap's tiny count
                            # (ADAM fy2011) is not a founder-share artifact; the
                            # SPAC/IPO cases (AHCO, BFAM) all have first_trade
                            # at or after the segment start
PLACEHOLDER_MAX = 1e5       # placeholder: shares below this ...
PLACEHOLDER_MIN_ASSETS = 1e8  # ... while assets at least this
MIN_SCALE_RATIO = 100.0     # scale-snap only when raw value is >=100x off flanks
SNAP_ADJ_TOL = 1.35         # snapped row ADJACENT to the clean flank must land
                            # this close: true scaled counts track their neighbor
                            # (GRMN x1e3 lands 1.0002 away), junk facts land
                            # randomly (RTX fy2009 x1e3 lands 1.50 away -> null)
SCALE_KS = (3, 6, 9, -3, -6, -9)   # candidate powers of ten for scale repairs
PRE_PUBLIC_MARGIN_DAYS = 30
SPLIT_WINDOW_DAYS = 550     # cover counts can lead/lag the split date by ~1y
SPLIT_RATIO_TOL = 1.25      # boundary jump within 25% of a real split ratio

_REFERENCE_NAME = "share_quality_reference.json"


# --------------------------------------------------------------------------- #
# reference store: first-trade dates + split histories (yfinance, cached)
# --------------------------------------------------------------------------- #
def _reference_path():
    p = config.data_dir() / "edgar" / _REFERENCE_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_reference(path=None) -> dict:
    p = path or _reference_path()
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — absent/corrupt cache = empty reference
        return {"tickers": {}}


def suspicious_tickers(panel: pd.DataFrame) -> list[str]:
    """Tickers whose share history warrants a reference lookup: any >=3x jump
    between adjacent segment levels, any sub-15M count, or a panel history that
    starts within the last 5 fiscal years (possible recent IPO with no
    post-IPO row yet)."""
    out: set[str] = set()
    latest_fy = int(panel["fy"].max())
    for t, g in panel.groupby("ticker"):
        nn = g.sort_values("fy")
        nn = nn[nn["shares"].notna() & (nn["shares"] > 0)]
        if nn.empty:
            continue
        vals = nn["shares"].to_numpy(dtype=float)
        segs = _segments(vals)
        if any(_ratio(segs[i][2], segs[i + 1][2]) >= ART_RATIO
               for i in range(len(segs) - 1)):
            out.add(str(t))
        elif (vals < TINY_MAX).any():
            out.add(str(t))
        elif int(nn["fy"].min()) >= latest_fy - 4:
            out.add(str(t))
    return sorted(out)


def build_reference(tickers: list[str], path=None, refresh: bool = False,
                    pace_s: float = 0.15) -> dict:
    """Ensure reference entries (first_trade, splits) exist for `tickers`,
    fetching missing ones from yfinance (keyless). Existing entries are kept
    unless `refresh`. Never raises — on any failure the current cache is
    returned and absent tickers simply have no entry (the detector treats them
    conservatively)."""
    p = path or _reference_path()
    ref = load_reference(p)
    entries = ref.setdefault("tickers", {})
    todo = [t for t in tickers if refresh or t not in entries]
    if not todo:
        return ref
    try:
        import yfinance as yf
    except Exception as e:  # noqa: BLE001
        log.warning("share_quality: yfinance unavailable (%s) — reference not built", e)
        return ref
    n_ok = 0
    for t in todo:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="max", interval="1mo", auto_adjust=True)
            first = str(hist.index[0].date()) if len(hist) else None
            splits = tk.splits
            entries[t] = {
                "first_trade": first,
                "splits": {str(d.date()): float(r) for d, r in splits.items()
                           if float(r) > 0} if splits is not None else {},
                "fetched": datetime.now(timezone.utc).date().isoformat(),
            }
            n_ok += 1
        except Exception as e:  # noqa: BLE001 — per-ticker tolerance
            log.warning("share_quality reference fetch failed %s: %s", t, e)
        time.sleep(pace_s)
    ref["built"] = datetime.now(timezone.utc).isoformat()
    try:
        p.write_text(json.dumps(ref, indent=0, sort_keys=True))
    except Exception as e:  # noqa: BLE001
        log.warning("share_quality: reference write failed: %s", e)
    log.info("share_quality reference: +%d/%d fetched (%d total)",
             n_ok, len(todo), len(entries))
    return ref


# --------------------------------------------------------------------------- #
# detection helpers
# --------------------------------------------------------------------------- #
def _ratio(a, b) -> float:
    """Symmetric ratio max(a/b, b/a); NaN when either side is missing/<=0."""
    if a is None or b is None:
        return np.nan
    a, b = float(a), float(b)
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0 or b <= 0:
        return np.nan
    return max(a / b, b / a)


def _segments(vals: np.ndarray) -> list[list]:
    """[start, end_inclusive, median] level segments split at >=SEG_JUMP moves."""
    segs, start = [], 0
    for i in range(1, len(vals)):
        r = _ratio(vals[i], vals[i - 1])
        if np.isfinite(r) and r >= SEG_JUMP:
            segs.append([start, i - 1, float(np.median(vals[start:i]))])
            start = i
    segs.append([start, len(vals) - 1, float(np.median(vals[start:]))])
    return segs


def _snap_k(vals: np.ndarray, target: float, adj_val: float | None = None,
            adj_pos: int | None = None) -> int | None:
    """Power of ten k such that every value x10^k lands within FLANK_AGREE of
    target AND, when (adj_val, adj_pos) given, the segment row at adj_pos lands
    within SNAP_ADJ_TOL of adj_val — the flank-adjacent row of a true scale typo
    tracks its neighbor closely; junk facts land at random distances."""
    for k in SCALE_KS:
        if all(_ratio(v * 10.0 ** k, target) <= FLANK_AGREE for v in vals):
            if (adj_val is None
                    or _ratio(vals[adj_pos] * 10.0 ** k, adj_val) <= SNAP_ADJ_TOL):
                return k
    return None


def _split_near(splits: dict, jump: float, pe_lo, pe_hi) -> bool:
    """True when a real split whose ratio matches `jump` (either direction,
    within SPLIT_RATIO_TOL) falls within SPLIT_WINDOW_DAYS of the boundary
    period_ends [pe_lo, pe_hi]."""
    if not splits or not np.isfinite(jump):
        return False
    lo = pd.Timestamp(pe_lo) - pd.Timedelta(days=SPLIT_WINDOW_DAYS)
    hi = pd.Timestamp(pe_hi) + pd.Timedelta(days=SPLIT_WINDOW_DAYS)
    for d, r in splits.items():
        try:
            ts, r = pd.Timestamp(d), float(r)
        except Exception:  # noqa: BLE001
            continue
        if r <= 0 or not (lo <= ts <= hi):
            continue
        eff = max(r, 1.0 / r)
        if max(eff / jump, jump / eff) <= SPLIT_RATIO_TOL:
            return True
    return False


def _reverse_split_near(splits: dict, pe_lo, pe_hi) -> bool:
    """True when any reverse split of at least SEG_JUMP falls near the window
    (a real reverse split makes a tiny share count legitimate — CPF fy2010)."""
    if not splits:
        return False
    lo = pd.Timestamp(pe_lo) - pd.Timedelta(days=SPLIT_WINDOW_DAYS)
    hi = pd.Timestamp(pe_hi) + pd.Timedelta(days=SPLIT_WINDOW_DAYS)
    for d, r in splits.items():
        try:
            ts, r = pd.Timestamp(d), float(r)
        except Exception:  # noqa: BLE001
            continue
        if 0 < r <= 1.0 / SEG_JUMP and lo <= ts <= hi:
            return True
    return False


def _eq_continuous(eq: np.ndarray, i: int, j: int) -> bool:
    """Equity continuity between adjacent rows i, j: both present, same sign,
    ratio within EQ_CONT_MAX. Missing equity = NOT continuous (conservative:
    level repairs need positive evidence)."""
    a, b = eq[i], eq[j]
    if not (np.isfinite(a) and np.isfinite(b)):
        return False
    if (a <= 0) != (b <= 0):
        return False
    r = _ratio(abs(a), abs(b))
    return np.isfinite(r) and r <= EQ_CONT_MAX


# --------------------------------------------------------------------------- #
# core detector
# --------------------------------------------------------------------------- #
def detect(panel: pd.DataFrame, reference: dict | None = None) -> pd.DataFrame:
    """Scan the panel and return one row per flagged panel row:
    [index, ticker, fy, flag, shares, repair, note]; `repair` NaN means null the
    shares. Pure pandas/numpy — the reference dict is the only external input."""
    ref_t = (reference or {}).get("tickers", {})
    flags: list[dict] = []

    need = {"ticker", "fy", "shares", "equity", "assets", "period_end"}
    missing = need - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns {sorted(missing)}")

    for t, g in panel.groupby("ticker"):
        g = g.sort_values("fy")
        nn = g[g["shares"].notna() & (g["shares"] > 0)]
        if nn.empty:
            continue
        vals = nn["shares"].to_numpy(dtype=float)
        fys = nn["fy"].to_numpy()
        eq = pd.to_numeric(nn["equity"], errors="coerce").to_numpy(dtype=float)
        assets = pd.to_numeric(nn["assets"], errors="coerce").to_numpy(dtype=float)
        pe = pd.to_datetime(nn["period_end"], errors="coerce")
        idx = nn.index.to_numpy()
        dei = (pd.to_numeric(nn["shares_dei"], errors="coerce").to_numpy(dtype=float)
               if "shares_dei" in nn.columns else np.full(len(nn), np.nan))
        entry = ref_t.get(str(t)) or {}
        splits = entry.get("splits") or {}
        rowflag: dict[int, tuple] = {}      # position -> (flag, repair, note)

        def _mark(i, flag, repair, note):
            rowflag.setdefault(i, (flag, repair, note))

        # ---- pre_public: fiscal year ended before the ticker traded ---------
        ft = entry.get("first_trade")
        if ft:
            cut = pd.Timestamp(ft) - pd.Timedelta(days=PRE_PUBLIC_MARGIN_DAYS)
            for i in range(len(vals)):
                if pd.notna(pe.iloc[i]) and pe.iloc[i] < cut:
                    _mark(i, "pre_public", np.nan, f"period_end<{cut.date()}")

        segs = _segments(vals)

        def _clean(seg) -> bool:
            return not any(i in rowflag for i in range(seg[0], seg[1] + 1))

        def _clean_left(si):
            return next((s for s in reversed(segs[:si]) if _clean(s)), None)

        def _clean_right(si):
            return next((s for s in segs[si + 1:] if _clean(s)), None)

        # ---- placeholder: sub-100k counts on a >= $100M filer ---------------
        for i in range(len(vals)):
            if i in rowflag or vals[i] >= PLACEHOLDER_MAX:
                continue
            if not (np.isfinite(assets[i]) and assets[i] >= PLACEHOLDER_MIN_ASSETS):
                continue
            si = next(j for j, s in enumerate(segs) if s[0] <= i <= s[1])
            lg, rg = _clean_left(si), _clean_right(si)
            repair, note = np.nan, "no clean flank snap"
            for flank, side in ((rg, "right"), (lg, "left")):
                if flank is None:
                    continue
                adj = vals[flank[0]] if side == "right" else vals[flank[1]]
                k = _snap_k(vals[i:i + 1], adj, adj_val=adj, adj_pos=0)
                if k is not None and k > 0:
                    repair, note = vals[i] * 10.0 ** k, f"x1e{k} vs {side} flank"
                    break
            _mark(i, "placeholder", repair, note)

        # ---- unit_scale / unit_level: segment-vs-clean-flank analysis -------
        # pass 1: interior candidates by raw disagreement with adjacent values
        cand: set[int] = set()
        for si in range(1, len(segs) - 1):
            a, b, _med = segs[si]
            if any(i in rowflag for i in range(a, b + 1)):
                continue
            rl, rr = _ratio(vals[a], vals[a - 1]), _ratio(vals[b], vals[b + 1])
            if not (np.isfinite(rl) and np.isfinite(rr)):
                continue
            same_side = (vals[a] > vals[a - 1]) == (vals[b] > vals[b + 1])
            if same_side and ((rl >= ART_RATIO and rr >= ART_RATIO)
                              or (rl >= MIN_SCALE_RATIO and rr >= MIN_SCALE_RATIO)):
                cand.add(si)

        # pass 2: re-evaluate each candidate against nearest NON-candidate,
        # unflagged flanks (handles alternating-artifact tickers like SXI).
        # Level repairs are only COLLECTED here and assigned after all flag
        # decisions, so carry-forward can use the nearest truly-unflagged
        # prior row — not a candidate-filtered segment end (an ASTH-class
        # noisy history otherwise carries a decade-stale count forward).
        level_marks: list[tuple[int, int, float]] = []
        for si in sorted(cand):
            a, b, _med = segs[si]
            lg = next((segs[j] for j in range(si - 1, -1, -1)
                       if j not in cand and _clean(segs[j])), None)
            rg = next((segs[j] for j in range(si + 1, len(segs))
                       if j not in cand and _clean(segs[j])), None)
            if lg is None or rg is None:
                continue
            lval, rval = vals[lg[1]], vals[rg[0]]        # adjacent clean values
            r_l, r_r = _ratio(vals[a], lval), _ratio(vals[b], rval)
            if not (np.isfinite(r_l) and np.isfinite(r_r)):
                continue
            flanks_agree = _ratio(lval, rval) <= FLANK_AGREE

            # scale-snap: power-of-ten typo (needs no equity/split evidence —
            # no real corporate action moves shares 100-1000x and back); the
            # end row adjacent to a clean flank must land within SNAP_ADJ_TOL
            if r_l >= MIN_SCALE_RATIO and r_r >= MIN_SCALE_RATIO:
                seg_vals = vals[a:b + 1]
                k = None
                if flanks_agree:
                    target = float(np.sqrt(lval * rval))
                    k = (_snap_k(seg_vals, target, adj_val=lval, adj_pos=0)
                         or _snap_k(seg_vals, target, adj_val=rval, adj_pos=len(seg_vals) - 1))
                if k is None:
                    k = (_snap_k(seg_vals, lval, adj_val=lval, adj_pos=0)
                         or _snap_k(seg_vals, rval, adj_val=rval, adj_pos=len(seg_vals) - 1))
                if k is not None:
                    for i in range(a, b + 1):
                        _mark(i, "unit_scale", vals[i] * 10.0 ** k, f"x1e{k}")
                    continue

            extreme = r_l >= MIN_SCALE_RATIO and r_r >= MIN_SCALE_RATIO

            # level artifact: >=3x off both AGREEING flanks, same side
            if not flanks_agree or r_l < ART_RATIO or r_r < ART_RATIO:
                if extreme:     # >=100x off both flanks is never a real action;
                    for i in range(a, b + 1):   # unrepairable -> honest NaN
                        _mark(i, "unit_extreme", np.nan, "no confident repair")
                continue
            if (vals[a] > lval) != (vals[b] > rval):
                if extreme:
                    for i in range(a, b + 1):
                        _mark(i, "unit_extreme", np.nan, "no confident repair")
                continue
            # a real split at either boundary means basis change, not artifact
            jump_in = _ratio(vals[a], vals[a - 1])
            jump_out = _ratio(vals[b], vals[b + 1])
            if (_split_near(splits, jump_in, pe.iloc[a - 1], pe.iloc[a])
                    or _split_near(splits, jump_out, pe.iloc[b], pe.iloc[b + 1])):
                continue
            # equity must ride THROUGH the segment untouched (ED: shares 13x
            # low, book equity seamless) — anything else could be real
            if not (_eq_continuous(eq, a - 1, a) and _eq_continuous(eq, b, b + 1)):
                if extreme:
                    for i in range(a, b + 1):
                        _mark(i, "unit_extreme", np.nan, "no confident repair")
                continue
            level_marks.append((a, b, float(np.sqrt(lval * rval))))

        # assign unit_level repairs against the FINAL flag state: the pending
        # level rows themselves are excluded as carry-forward sources
        pending = set().union(*(range(a, b + 1) for a, b, _t in level_marks)) \
            if level_marks else set()
        for a, b, target in level_marks:
            prior = next((vals[j] for j in range(a - 1, -1, -1)
                          if j not in rowflag and j not in pending), np.nan)
            for i in range(a, b + 1):
                if np.isfinite(dei[i]) and dei[i] > 0 and _ratio(dei[i], target) <= FLANK_AGREE:
                    _mark(i, "unit_level", dei[i], "same-FY DEI cover count")
                elif np.isfinite(prior) and prior > 0:
                    _mark(i, "unit_level", prior, "carry-forward last clean prior")
                else:
                    _mark(i, "unit_level", np.nan, "no PIT-legal repair source")

        # ---- leading / trailing scale-snap (one clean flank only) -----------
        # Only the MINORITY end (fewer rows than the rest of the ticker's
        # history) may be treated as the artifact: when a whole end is 1000x
        # off, both "lead is junk" and "tail is junk" snap onto each other
        # symmetrically, and the majority side is the ticker's real level
        # (CPK: 12 correct leading rows anchor 3 trailing x1000 rows).
        # phase 1: confident power-of-ten snap -> repair; phase 2: still
        # unflagged and >=100x off the clean flank -> honest NaN.
        if len(segs) >= 2:
            ends = ((0, "lead"), (len(segs) - 1, "trail"))
            for phase in (1, 2):
                for si, side in ends:
                    a, b, _med = segs[si]
                    if any(i in rowflag for i in range(a, b + 1)):
                        continue
                    if not (b - a + 1) < (len(vals) - (b - a + 1)):
                        continue                    # not the minority side
                    flank = _clean_right(si) if side == "lead" else _clean_left(si)
                    if flank is None:
                        continue
                    adj = vals[flank[0]] if side == "lead" else vals[flank[1]]
                    r = min(_ratio(vals[a], adj), _ratio(vals[b], adj))
                    if not (np.isfinite(r) and r >= MIN_SCALE_RATIO):
                        continue
                    if phase == 1:
                        adj_pos = (b - a) if side == "lead" else 0
                        k = _snap_k(vals[a:b + 1], adj, adj_val=adj, adj_pos=adj_pos)
                        if k is not None:
                            for i in range(a, b + 1):
                                _mark(i, "unit_scale", vals[i] * 10.0 ** k,
                                      f"x1e{k} ({side})")
                    else:
                        for i in range(a, b + 1):
                            _mark(i, "unit_extreme", np.nan,
                                  f"no confident repair ({side})")

        # ---- pre_public_tiny: founder/SPAC counts that outlive the IPO ------
        # (no already-flagged guard: pre_public often catches the EARLY rows of
        # the same segment while the IPO-filing-lag tail needs this rule — AHCO
        # fy2017 is pre_public, fy2018-19 land here; _mark keeps earlier flags)
        if len(segs) >= 2:
            a, b, med = segs[0]
            rg = _clean_right(0)
            later_ok = all(_ratio(med, s[2]) >= ART_RATIO and s[2] > med
                           for s in segs[1:])
            long_public = (ft is not None and pd.notna(pe.iloc[a])
                           and (pe.iloc[a] - pd.Timestamp(ft)).days
                           > PUBLIC_LONG_BEFORE_DAYS)
            if (rg is not None and not long_public
                    and max(vals[a:b + 1]) < TINY_MAX and later_ok
                    and (b - a + 1) <= TINY_MAX_ROWS
                    and _ratio(vals[b], vals[rg[0]]) >= ART_RATIO
                    and vals[rg[0]] > vals[b]
                    and not _reverse_split_near(splits, pe.iloc[a], pe.iloc[b])):
                e0, e1 = eq[b], (eq[b + 1] if b + 1 < len(eq) else np.nan)
                sign_chg = (np.isfinite(e0) and np.isfinite(e1)
                            and (e0 <= 0) != (e1 <= 0))
                eq_r = _ratio(abs(e0), abs(e1))
                if sign_chg or not np.isfinite(eq_r) or eq_r >= EQ_JUMP_MIN:
                    for i in range(a, b + 1):
                        _mark(i, "pre_public_tiny", np.nan,
                              f"leading segment <{TINY_MAX:.0e}")

        for i, (fl, rep, note) in sorted(rowflag.items()):
            flags.append({"index": idx[i], "ticker": t, "fy": int(fys[i]),
                          "flag": fl, "shares": vals[i], "repair": rep,
                          "note": note})

    cols = ["index", "ticker", "fy", "flag", "shares", "repair", "note"]
    return pd.DataFrame(flags, columns=cols)


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #
def apply_share_quality(panel: pd.DataFrame, reference: dict | None = None,
                        max_rounds: int = 6) -> tuple[pd.DataFrame, dict]:
    """Return (panel copy with shares repaired/nulled, audit dict). Adds
    `shares_raw` (original as-fetched counts, preserved across re-runs) and
    `share_flag` (category or None).

    Runs detect->repair to a FIXED POINT: a repair changes the segmentation
    its neighbors see, which can expose artifacts the first pass hid (ROP's
    in-thousands rows straddle the placeholder cutoff — fy2013 at 99,312
    repairs as a placeholder, and only then do fy2014/15 at ~100k become a
    visible interior scale segment). Convergence is 2-3 rounds in practice;
    `max_rounds` is a runaway backstop. The fixed point makes the function
    idempotent: re-applying to a healed panel finds nothing new."""
    out = panel.copy()
    if "shares_raw" not in out.columns:
        out["shares_raw"] = out["shares"]
    if "share_flag" not in out.columns:
        out["share_flag"] = None

    all_found: list[pd.DataFrame] = []
    for _round in range(max_rounds):
        found = detect(out, reference=reference)
        if found.empty:
            break
        for _, f in found.iterrows():
            i = f["index"]
            out.at[i, "share_flag"] = f["flag"]
            out.at[i, "shares"] = f["repair"] if pd.notna(f["repair"]) else np.nan
        all_found.append(found)
    else:
        log.warning("share_quality: no fixed point after %d rounds", max_rounds)
    found = (pd.concat(all_found, ignore_index=True)
             .drop_duplicates(subset=["index"], keep="last")
             if all_found
             else pd.DataFrame(columns=["index", "ticker", "fy", "flag",
                                        "shares", "repair", "note"]))

    audit = {
        "applied": datetime.now(timezone.utc).isoformat(),
        "rows_flagged": int(len(found)),
        "tickers_flagged": int(found["ticker"].nunique()) if len(found) else 0,
        "by_flag": {k: int(v) for k, v in
                    found.groupby("flag").size().items()} if len(found) else {},
        "repaired": int(found["repair"].notna().sum()) if len(found) else 0,
        "nulled": int(found["repair"].isna().sum()) if len(found) else 0,
        "rows": [{"ticker": r["ticker"], "fy": r["fy"], "flag": r["flag"],
                  "shares_raw": float(out.at[r["index"], "shares_raw"]),
                  "repair": (None if pd.isna(r["repair"]) else float(r["repair"])),
                  "note": r["note"]}
                 for _, r in found.iterrows()],
    }
    if len(found):
        log.info("share_quality: %d rows on %d tickers (%s) — %d repaired, %d nulled",
                 audit["rows_flagged"], audit["tickers_flagged"],
                 audit["by_flag"], audit["repaired"], audit["nulled"])
    return out, audit
