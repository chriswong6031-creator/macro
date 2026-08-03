"""Frozen basket levels + membership hash — W3.8 substrate.

Writes an append-only, immutable-per-(date,bid) wide parquet:

  data/basket_levels/<domain>.parquet
    index : date (datetime64[ns], one row per calendar day the build ran)
    columns (wide, one group per basket_id):
      <bid>__level_price   float64   equal-weight index on PRICE basis
      <bid>__level_tr      float64   equal-weight index on TR (total-return) basis
      <bid>__mhash         object    membership hash for THIS basket on THIS date
      <bid>__n_members     int       active member count at freeze time
      <bid>__anchor        object    ISO date the level's CHAIN SEGMENT is based on
    row-level column:
      __freeze_schema      int       writer schema version (2 as of 2026-08)

Domains: us, china, china_ths, hk, canada.

IMMUTABILITY CONTRACT (keep-FIRST) + CHAIN CONTRACT (schema v2, 2026-08):
  A frozen (date, bid) cell is NEVER overwritten. The writer only appends rows for
  dates NOT yet in the store (it never touches existing rows).

  Immutability alone was NOT enough to make cross-date ratios meaningful. The level
  series this store freezes is an equal-weight cumprod that the engine recomputes
  nightly over a ROLLING price window (engine/baskets.py:_ew_level rebases at the
  window's own first_valid_index, which advances every night). Freezing "tonight's
  last value" therefore put every frozen row on a DIFFERENT base: each row is a true
  PIT observation of that night's index, but row_b / row_a is NOT the return from a
  to b — it carries the returns of whatever days fell out of the window in between.
  (Measured on the US store 2026-08: +7.99% mean drift 22 rows back, decaying to ~0
  at the newest row; a mag7 07-02→07-31 frozen ratio read −6.13% against a true
  +1.15% move.)

  As of schema v2 the writer CHAIN-LINKS instead. Tonight's row is
  ``prior_frozen_value × (tonight_series[today] / tonight_series[prior_date])`` —
  both legs read off ONE consistent series, so the ratio is exactly tonight's move
  over that span and cross-date ratios WITHIN a chain segment are true returns by
  construction. ``<bid>__anchor`` names the first date of the segment the row belongs
  to; ``return_valid_start(domain, bid)`` reads it back. A chain BREAKS (new anchor =
  that row's own date) when tonight's series cannot reach back to the prior frozen
  date, or when the prior value/base is degenerate.

  LEGACY DECLARATION (not re-derivable): rows written before v2 were each frozen on
  that night's rolling-window base. They are PERMANENTLY unreliable for cross-date
  return math and are DECLARED so rather than repaired — re-deriving them from
  today's tape would fabricate PIT history that was never observed. Consumers must
  gate return math on ``return_valid_start()``; the first chained row anchors on the
  last legacy row (that single ratio IS exact, because both legs come from tonight's
  one consistent series), so the usable span starts there, not at the store's first
  row. Levels themselves stay immutable either way.

TRUNCATION GUARD:
  If the live membership for a basket shrinks > CHURN_ALERT_PCT (15%) vs the prior
  frozen n_members for that basket, the whole domain's freeze is SKIPPED (not written)
  for that run and a loud alert fires (same PruneGuardError-style pattern as
  scripts/reconcile_membership.py). The rest of the domains are still attempted.

SURVIVORSHIP HOLE DECLARATION (D4-N3):
  Levels before the first freeze date are PERMANENTLY survivorship-contaminated
  (membership.json is curated with knowledge of the period; the EW level is built
  on current membership projected backward). Graders MUST NOT grade calls whose
  forward window falls entirely before the first frozen row — they declare
  "accruing from <freeze_start>" instead. The freeze is prospective-only.

BASIS NOTE (W2.2 compatibility):
  basket members' `close` column from the breadth / china_search caches is already
  dividend-adjusted total return (yfinance auto_adjust=True). We label
  level_tr accordingly. A separate price-basis (unadjusted) series would require the
  dual-basis migration (D4-W1) that is underway but not complete for all members, so
  level_price is computed from the same `close` column with an honest coverage note:
  where `close_price` (price-basis) is available per member it is preferred for
  level_price; where not, `close` (TR) is used and a `price_basis_coverage` fraction
  is logged. This is the honest bootstrap: level_tr is the definitive grading series;
  level_price is structural/best-effort and will improve as D4-W1 rolls out.
  The price basis is chained off its OWN prior frozen price value, using the price
  series' asof-ratio when closes_price is supplied and the TR series' ratio when it
  is not (mirroring the level_price = level_tr fallback that predates v2). There is
  ONE shared `<bid>__anchor` per basket and it is driven by the TR chain — the
  definitive one. A price row that rides the TR ratio is exactly as best-effort as
  the level it falls back to; treat `<bid>__anchor` as a statement about level_tr.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import date as date_type
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

CHURN_ALERT_PCT = 0.15      # >15% shrink in active members vs last frozen → refuse
DOMAIN_DIR = "basket_levels"   # relative to data_dir()
FREEZE_SCHEMA = 2           # writer version stamped on every row (v2 = chain-linked)
SCHEMA_COL = "__freeze_schema"

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

class FreezeSkipped(RuntimeError):
    """Raised (and caught by callers) when a domain's freeze is refused.

    This is intentionally non-fatal: the caller catches it, logs it and
    fires the notify channels, then continues with other domains.
    """


def membership_hash(members: list[dict]) -> str:
    """Canonical membership hash — sorted active ticker identifiers only.

    Sorted so order changes don't flip the hash; equal-weight means weights
    are irrelevant. Uses 'ticker' key (US/CN/HK/THS all use 'ticker').
    Returns the first 16 hex chars of SHA1 (collision probability negligible
    for basket sizes ≤ 300 members).
    """
    ids = sorted(
        m.get("ticker") or m.get("code") or ""
        for m in members
        if not m.get("removed")                  # active-only
    )
    ids = [i for i in ids if i]                  # drop blanks
    return hashlib.sha1("|".join(ids).encode()).hexdigest()[:16]


def active_members(members: list[dict], as_of: date_type | None = None) -> list[dict]:
    """Filter to active (non-removed) members as of `as_of` date.

    `as_of` is used for date-gated removal checks; if None the member is
    included iff it has no `removed` date at all (current live membership).
    """
    result = []
    for m in members:
        rem = m.get("removed")
        if not rem:
            result.append(m)
            continue
        if as_of is not None:
            try:
                if pd.Timestamp(rem).date() > as_of:
                    result.append(m)
            except Exception:  # noqa: BLE001
                pass
    return result


def freeze_domain(
    domain: str,
    baskets_payload: dict | None,
    closes_tr: pd.DataFrame | None,
    membership_raw: dict | None,
    *,
    closes_price: pd.DataFrame | None = None,
    as_of_date: str | None = None,
) -> dict:
    """Freeze one domain's basket levels for today's build.

    Parameters
    ----------
    domain
        One of {us, china, china_ths, hk}.
    baskets_payload
        The dict returned by compute_*_baskets() for this domain — used
        ONLY to extract the chart level series that the engine already
        computed (so we don't recompute). Keys: chart.dates + chart.baskets
        (basket_id → level list).  If None/empty we fall back to computing
        from closes_tr + membership_raw.
    closes_tr
        Wide [Date × ticker] TOTAL-RETURN adjusted closes.  Used when
        baskets_payload is unavailable or for direct member-level hash.
    membership_raw
        The raw membership dict (data/<region>/membership.json parsed).
        Used to derive mhash + n_members for each basket.
    closes_price
        Optional wide [Date × ticker] PRICE-BASIS closes (D4-W1 dual-basis
        rollout). Used for level_price where coverage > 0; else falls back to
        closes_tr (which equals TR, noted in coverage log).
    as_of_date
        ISO date string override (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    dict with keys:
        domain          str
        date            str (YYYY-MM-DD)
        n_frozen        int  number of baskets frozen this run
        n_skipped_churn int  baskets skipped due to truncation churn
        freeze_skipped  bool True if the whole domain was refused
        skip_reason     str | None
        price_basis_coverage float  fraction of level_price cells backed by close_price
    """
    result: dict = {
        "domain": domain, "date": as_of_date or str(date_type.today()),
        "n_frozen": 0, "n_skipped_churn": 0,
        "freeze_skipped": False, "skip_reason": None,
        "price_basis_coverage": 0.0,
    }
    try:
        return _freeze_domain_inner(
            domain, baskets_payload, closes_tr, membership_raw,
            closes_price=closes_price, as_of_date=as_of_date, result=result,
        )
    except FreezeSkipped:
        raise   # propagate — caller decides whether to alert
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[%s]: unexpected error: %s", domain, e)
        result["freeze_skipped"] = True
        result["skip_reason"] = f"unexpected_error: {e}"
        return result


def read_frozen(domain: str) -> pd.DataFrame | None:
    """Read the frozen basket-levels parquet for a domain.

    Returns a wide DataFrame indexed by date, or None if the file doesn't
    exist yet (the 'accruing from <freeze_start>' case for graders).
    """
    p = _store_path(domain)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("basket_freeze: could not read %s: %s", p, e)
        return None


def frozen_level_series(domain: str, bid: str, basis: str = "tr") -> pd.Series | None:
    """Return the frozen level Series for one basket.

    basis : 'tr' (default, for return grading) or 'price' (for structure math).
    Returns None if the domain file doesn't exist or the basket isn't there.

    RETURN MATH: the raw series spans schema versions. Ratios across it are true
    returns ONLY from ``return_valid_start(domain, bid)`` onward — clamp to that
    date before dividing any two points (pre-v2 rows each sat on their own base).
    """
    df = read_frozen(domain)
    if df is None:
        return None
    col = f"{bid}__level_{basis}"
    if col not in df.columns:
        return None
    return df[col].dropna()


def frozen_mhash_series(domain: str, bid: str) -> pd.Series | None:
    """Return the frozen membership-hash Series for one basket.

    Used by graders to detect composition changes mid forward window.
    """
    df = read_frozen(domain)
    if df is None:
        return None
    col = f"{bid}__mhash"
    if col not in df.columns:
        return None
    return df[col].dropna()


def return_valid_start(domain: str, bid: str) -> str | None:
    """Earliest date from which cross-date ratios of the frozen level series are
    true returns (the chain anchor of the newest chained row, which may be the
    last pre-v2 row). None when the store/basket is absent or not yet chained."""
    return _return_valid_start_from(read_frozen(domain), bid)


def _return_valid_start_from(df: pd.DataFrame | None, bid: str) -> str | None:
    """return_valid_start() against an already-read frame (graders read once, ask N times)."""
    if df is None or df.empty:
        return None
    lvl_col, anc_col = f"{bid}__level_tr", f"{bid}__anchor"
    if lvl_col not in df.columns or anc_col not in df.columns:
        return None
    lvl = df[lvl_col].dropna()
    if lvl.empty:
        return None
    anchored = df[[lvl_col, anc_col]].dropna()
    if anchored.empty:
        return None
    # Fail closed: a legacy tail newer than the last anchored row means the chain
    # stopped being maintained — no span of this series is trustworthy any more.
    if lvl.index[-1] > anchored.index[-1]:
        return None
    val = anchored[anc_col].iloc[-1]
    return str(val) if val is not None else None


def freeze_start_date(domain: str) -> str | None:
    """First date in the frozen store for a domain (the earliest PIT record).

    Graders use this to declare the pre-freeze survivorship hole:
    any call whose forward window starts before this date is not gradable.
    Returns ISO string or None if no frozen data yet.
    """
    df = read_frozen(domain)
    if df is None or df.empty:
        return None
    return str(df.index[0].date())


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _store_path(domain: str) -> Path:
    p = config.data_dir() / DOMAIN_DIR / f"{domain}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ew_level_from_closes(
    closes: pd.DataFrame, members: list[dict], as_of: date_type | None = None,
) -> tuple[pd.Series, float]:
    """Compute an EW level Series from a closes matrix + membership list.

    Returns (level_series, price_basis_coverage_fraction).
    Coverage fraction: fraction of active members whose column was drawn from
    the closes matrix (always 1.0 here; factored for price/tr swap logic above).
    """
    active = active_members(members, as_of=as_of)
    tickers = [m.get("ticker") or m.get("code") for m in active if m.get("ticker") or m.get("code")]
    present = [t for t in tickers if t in closes.columns]
    if len(present) < 3:
        return pd.Series(dtype="float64"), float(len(present)) / max(len(tickers), 1)

    idx = closes.index
    mask = pd.DataFrame(False, index=idx, columns=present)
    for m in active:
        t = m.get("ticker") or m.get("code")
        if t not in present:
            continue
        start = idx >= pd.Timestamp(m["added"])
        rem = m.get("removed")
        if rem:
            start = start & (idx < pd.Timestamp(rem))
        mask[t] = start

    rets = closes[present].pct_change(fill_method=None)
    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return pd.Series(dtype="float64"), float(len(present)) / max(len(tickers), 1)
    lvl = pd.Series(float("nan"), index=idx, dtype="float64")
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    coverage = float(len(present)) / max(len(tickers), 1)
    return lvl, coverage


def _series_from_chart(chart_dates: list, values: list) -> pd.Series:
    """Tonight's level SERIES as the engine already computed it (chart payload).

    The scalar last value is not enough to chain — the chain needs the value this
    same series carried on the PRIOR frozen date. None → NaN; unparseable dates or
    an empty overlap yield an empty Series (callers fall back to the closes path).
    """
    try:
        pairs = list(zip(chart_dates or [], values or []))
        if not pairs:
            return pd.Series(dtype="float64")
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in pairs])
        vals = [float("nan") if v is None else float(v) for _, v in pairs]
        return pd.Series(vals, index=idx, dtype="float64").sort_index()
    except Exception as e:  # noqa: BLE001 — malformed payload → closes fallback
        log.warning("basket_freeze: chart series unusable: %s", e)
        return pd.Series(dtype="float64")


def _asof(series: pd.Series | None, ts: pd.Timestamp) -> float | None:
    """Last finite value of `series` at index ≤ ts (calendar-day granularity).

    Calendar-aware on purpose: a Saturday freeze asks for Saturday and gets Friday's
    value, so a weekend row chains at ratio 1.0 off Friday — the byte-identical
    weekend repeat the store has always written.
    """
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty:
        return None
    try:
        s = s[pd.DatetimeIndex(s.index).normalize() <= pd.Timestamp(ts).normalize()]
    except Exception:  # noqa: BLE001
        return None
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if math.isfinite(v) else None


def _last_value(series: pd.Series | None) -> float | None:
    """Last finite value of the whole series (the pre-v2 'tonight's raw last value')."""
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if math.isfinite(v) else None


def _last_frozen_point(frozen_df: pd.DataFrame | None,
                       col: str) -> tuple[pd.Timestamp, float] | None:
    """(date, value) of the last non-null frozen cell for a column, or None."""
    if frozen_df is None or frozen_df.empty or col not in frozen_df.columns:
        return None
    s = frozen_df[col].dropna()
    if s.empty:
        return None
    try:
        v = float(s.iloc[-1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return s.index[-1], v


def _prior_anchor(frozen_df: pd.DataFrame | None, bid: str,
                  prior_date: pd.Timestamp) -> str | None:
    """The chain anchor stamped on the prior frozen row, or None (pre-v2 row)."""
    if frozen_df is None or frozen_df.empty:
        return None
    col = f"{bid}__anchor"
    if col not in frozen_df.columns:
        return None
    try:
        val = frozen_df[col].loc[prior_date]
    except (KeyError, IndexError):
        return None
    if isinstance(val, pd.Series):
        val = val.dropna()
        val = val.iloc[-1] if not val.empty else None
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return str(val)


def _chained_level(series: pd.Series | None,
                   prior_point: tuple[pd.Timestamp, float] | None,
                   today_ts: pd.Timestamp) -> tuple[float | None, bool]:
    """Chain tonight's level onto the prior frozen value.

    Returns (level, chained). `chained` True → the value is prior × tonight's own
    asof-ratio over [prior_date, today], so the prior row's anchor carries forward.
    `chained` False → the chain (re)starts here on tonight's raw last value: no
    prior row, no overlap with tonight's series, or a degenerate base.
    """
    cur = _asof(series, today_ts)
    if cur is None:
        return None, False                       # nothing frozen tonight → None, no anchor
    raw_last = _last_value(series)
    if prior_point is None:
        return raw_last, False                   # chain start
    prior_ts, prior_val = prior_point
    base = _asof(series, prior_ts)
    if base is None or base <= 0 or not math.isfinite(prior_val):
        return raw_last, False                   # CHAIN BREAK — re-anchor on tonight
    return prior_val * (cur / base), True


def _prior_n_members(frozen_df: pd.DataFrame | None, bid: str) -> int | None:
    """Last known n_members for bid from the frozen store."""
    if frozen_df is None or frozen_df.empty:
        return None
    col = f"{bid}__n_members"
    if col not in frozen_df.columns:
        return None
    s = frozen_df[col].dropna()
    if s.empty:
        return None
    return int(s.iloc[-1])


def _freeze_domain_inner(
    domain: str,
    baskets_payload: dict | None,
    closes_tr: pd.DataFrame | None,
    membership_raw: dict | None,
    *,
    closes_price: pd.DataFrame | None = None,
    as_of_date: str | None = None,
    result: dict,
) -> dict:
    today_str = as_of_date or str(date_type.today())
    today_ts = pd.Timestamp(today_str)

    # Load existing frozen store (may be None on first run)
    store_path = _store_path(domain)
    frozen_df = read_frozen(domain)

    # Check if today's row already exists (keep-FIRST; never overwrite)
    if frozen_df is not None and not frozen_df.empty:
        existing_dates = frozen_df.index.normalize()
        if today_ts.normalize() in existing_dates:
            log.info("basket_freeze[%s]: %s already frozen — skipping (keep-first)", domain, today_str)
            result["n_frozen"] = 0
            return result

    # Extract basket list from membership_raw
    if not membership_raw or not membership_raw.get("baskets"):
        result["freeze_skipped"] = True
        result["skip_reason"] = "no membership data"
        return result

    bdict = membership_raw["baskets"]
    items: list[tuple[str, dict]] = (
        list(bdict.items()) if isinstance(bdict, dict)
        else [(b["id"], b) for b in bdict]
    )

    # ── TRUNCATION GUARD: check churn before touching the store ──────────────
    # Per basket: compute current active count and compare to last frozen value.
    # If ANY basket in this domain exceeds CHURN_ALERT_PCT shrink → refuse whole domain.
    churn_violations: list[str] = []
    today_date = pd.Timestamp(today_str).date()
    for bid, b in items:
        members = b.get("members", [])
        cur_active = active_members(members, as_of=today_date)
        cur_n = len(cur_active)
        prior_n = _prior_n_members(frozen_df, bid)
        if prior_n is None or prior_n == 0:
            continue   # no prior freeze yet; nothing to compare
        shrink_rate = (prior_n - cur_n) / prior_n
        if shrink_rate > CHURN_ALERT_PCT:
            churn_violations.append(
                f"{bid} shrank {prior_n}→{cur_n} ({shrink_rate:.0%} > {CHURN_ALERT_PCT:.0%})"
            )

    if churn_violations:
        msg = (
            f"basket_freeze[{domain}]: TRUNCATION GUARD TRIGGERED — "
            f"membership shrank >15% for {len(churn_violations)} basket(s): "
            + "; ".join(churn_violations[:5])
        )
        log.error(msg)
        result["freeze_skipped"] = True
        result["skip_reason"] = f"churn_guard: {'; '.join(churn_violations[:3])}"
        result["n_skipped_churn"] = len(churn_violations)
        # Fire notify via the W6b push spine.
        # push_ops_alert() dispatches raw even when alert_push.enabled=false
        # (dedup/ledger skipped, transport fires — liveness alerts are never silenced).
        # W6b: replaces the former direct send_telegram/send_discord call.
        try:
            from engine.alert_triage import push_ops_alert  # noqa: PLC0415
            alert_msg = f"⚠️ BASKET FREEZE SKIPPED [{domain.upper()}]\n{msg}"
            push_ops_alert(
                source="basket_freeze",
                type_="churn_guard",
                message=alert_msg,
                severity="critical",
                lane="basket_freeze",
            )
        except Exception:  # noqa: BLE001
            pass
        raise FreezeSkipped(msg)

    # ── Extract level series (prefer from baskets_payload if available) ───────
    chart = (baskets_payload or {}).get("chart") or {}
    chart_dates = chart.get("dates")
    chart_baskets = chart.get("baskets") or {}

    new_rows: dict[str, object] = {"date": today_ts, SCHEMA_COL: FREEZE_SCHEMA}
    price_coverage_fracs: list[float] = []

    for bid, b in items:
        members = b.get("members", [])
        cur_active = active_members(members, as_of=today_date)
        n_members = len(cur_active)
        mhash = membership_hash(cur_active)

        # ── tonight's level SERIES (not just the scalar — the chain needs the base) ──
        # Prefer the already-computed baskets_payload chart; else recompute from closes.
        series_tr: pd.Series | None = None
        if chart_dates and bid in chart_baskets:
            s = _series_from_chart(chart_dates, chart_baskets[bid])
            if not s.dropna().empty:
                series_tr = s
        if series_tr is None and closes_tr is not None and not closes_tr.empty:
            lvl_s, cov = _ew_level_from_closes(closes_tr, members, as_of=today_date)
            if not lvl_s.dropna().empty:
                series_tr = lvl_s
            price_coverage_fracs.append(cov)

        # ── TR chain (the definitive basis) ──────────────────────────────────
        prior_tr = _last_frozen_point(frozen_df, f"{bid}__level_tr")
        level_tr, chained = _chained_level(series_tr, prior_tr, today_ts)

        anchor: str | None = None
        if level_tr is not None:
            if chained and prior_tr is not None:
                prior_ts = prior_tr[0]
                # A prior row with no anchor is the v1→v2 boundary: anchor the new
                # segment on that legacy row's date. The boundary ratio itself IS
                # exact — both legs are read off tonight's one consistent series.
                anchor = _prior_anchor(frozen_df, bid, prior_ts) or str(pd.Timestamp(prior_ts).date())
            else:
                anchor = str(today_ts.date())
        # level_tr is None → no anchor written for this bid this row. A None gap does
        # NOT break the chain: the next night chains off the last non-null row, and
        # the asof product across the gap stays exact.

        # ── price basis: chained off its OWN prior frozen price value ─────────
        price_series: pd.Series | None = None
        have_price_input = closes_price is not None and not closes_price.empty
        if have_price_input:
            lvl_p, cov_p = _ew_level_from_closes(closes_price, members, as_of=today_date)
            if not lvl_p.dropna().empty:
                price_series = lvl_p
                price_coverage_fracs.append(cov_p)
        # No price-basis input at all → TR stands in (the pre-v2 level_price = level_tr
        # fallback, now expressed as "ride the TR ratio"). Input present but this basket
        # has no price series → honest None, exactly as before.
        price_src = price_series if price_series is not None else (
            None if have_price_input else series_tr)
        level_price: float | None = None
        if price_src is not None:
            level_price, _ = _chained_level(
                price_src, _last_frozen_point(frozen_df, f"{bid}__level_price"), today_ts)

        new_rows[f"{bid}__level_tr"] = level_tr
        new_rows[f"{bid}__level_price"] = level_price
        new_rows[f"{bid}__mhash"] = mhash
        new_rows[f"{bid}__n_members"] = n_members
        new_rows[f"{bid}__anchor"] = anchor

    result["price_basis_coverage"] = (
        float(sum(price_coverage_fracs) / len(price_coverage_fracs))
        if price_coverage_fracs else 0.0
    )

    # ── Append new row to store (keep-FIRST: append-only, never overwrite) ───
    new_df = pd.DataFrame([new_rows]).set_index("date")
    new_df.index = pd.DatetimeIndex(new_df.index)

    if frozen_df is not None and not frozen_df.empty:
        # Align columns (new baskets may appear; existing columns kept)
        combined = pd.concat([frozen_df, new_df], axis=0)
        # keep-FIRST: never overwrite past rows
        combined = combined[~combined.index.duplicated(keep="first")]
        combined = combined.sort_index()
    else:
        combined = new_df

    combined.to_parquet(store_path)
    n_basket_cols = len([c for c in new_df.columns if c.endswith("__level_tr")])
    result["n_frozen"] = n_basket_cols
    log.info(
        "basket_freeze[%s]: froze %d baskets for %s (price_basis_coverage=%.0f%%)",
        domain, n_basket_cols, today_str, result["price_basis_coverage"] * 100,
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: freeze all four domains in one call
# ──────────────────────────────────────────────────────────────────────────────

def freeze_all_domains(as_of_date: str | None = None) -> dict[str, dict]:
    """Freeze all four basket domains (us, china, china_ths, hk).

    Each domain is independent — a churn guard on one does not block the others.
    Returns a dict of domain → freeze result.  Never raises.
    """
    results: dict[str, dict] = {}

    # ── US ────────────────────────────────────────────────────────────────────
    try:
        from engine.baskets import compute_baskets, _membership as us_membership
        from engine.equity_factors import _closes as us_closes
        us_payload = compute_baskets()
        us_mem = us_membership()
        try:
            us_cl = us_closes()
        except Exception:  # noqa: BLE001
            us_cl = None
        results["us"] = freeze_domain("us", us_payload, us_cl, us_mem, as_of_date=as_of_date)
    except FreezeSkipped as e:
        results["us"] = {"domain": "us", "freeze_skipped": True, "skip_reason": str(e),
                         "n_frozen": 0, "n_skipped_churn": 0}
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[us]: failed: %s", e)
        results["us"] = {"domain": "us", "freeze_skipped": True, "skip_reason": str(e),
                         "n_frozen": 0, "n_skipped_churn": 0}

    # ── China (curated) ───────────────────────────────────────────────────────
    try:
        from engine.baskets_china import compute_china_baskets, _membership as cn_membership, _closes as cn_closes
        cn_payload = compute_china_baskets()
        cn_mem = cn_membership()
        try:
            cn_cl = cn_closes()
        except Exception:  # noqa: BLE001
            cn_cl = None
        results["china"] = freeze_domain("china", cn_payload, cn_cl, cn_mem, as_of_date=as_of_date)
    except FreezeSkipped as e:
        results["china"] = {"domain": "china", "freeze_skipped": True, "skip_reason": str(e),
                            "n_frozen": 0, "n_skipped_churn": 0}
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[china]: failed: %s", e)
        results["china"] = {"domain": "china", "freeze_skipped": True, "skip_reason": str(e),
                            "n_frozen": 0, "n_skipped_churn": 0}

    # ── China THS ─────────────────────────────────────────────────────────────
    try:
        from engine.baskets_china import compute_china_ths_baskets, _ths_membership, _closes as cn_closes_ths
        ths_payload = compute_china_ths_baskets()
        ths_mem = _ths_membership()
        try:
            ths_cl = cn_closes_ths()
        except Exception:  # noqa: BLE001
            ths_cl = None
        results["china_ths"] = freeze_domain("china_ths", ths_payload, ths_cl, ths_mem, as_of_date=as_of_date)
    except FreezeSkipped as e:
        results["china_ths"] = {"domain": "china_ths", "freeze_skipped": True, "skip_reason": str(e),
                                "n_frozen": 0, "n_skipped_churn": 0}
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[china_ths]: failed: %s", e)
        results["china_ths"] = {"domain": "china_ths", "freeze_skipped": True, "skip_reason": str(e),
                                "n_frozen": 0, "n_skipped_churn": 0}

    # ── HK ────────────────────────────────────────────────────────────────────
    try:
        from engine.baskets_hk import compute_hk_baskets, _membership as hk_membership, _closes as hk_closes
        hk_payload = compute_hk_baskets()
        hk_mem = hk_membership()
        try:
            hk_cl = hk_closes()
        except Exception:  # noqa: BLE001
            hk_cl = None
        results["hk"] = freeze_domain("hk", hk_payload, hk_cl, hk_mem, as_of_date=as_of_date)
    except FreezeSkipped as e:
        results["hk"] = {"domain": "hk", "freeze_skipped": True, "skip_reason": str(e),
                         "n_frozen": 0, "n_skipped_churn": 0}
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[hk]: failed: %s", e)
        results["hk"] = {"domain": "hk", "freeze_skipped": True, "skip_reason": str(e),
                         "n_frozen": 0, "n_skipped_churn": 0}

    return results
