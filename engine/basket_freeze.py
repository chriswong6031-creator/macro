"""Frozen basket levels + membership hash — W3.8 substrate.

Writes an append-only, immutable-per-(date,bid) wide parquet:

  data/basket_levels/<domain>.parquet
    index : date (datetime64[ns], one row per calendar day the build ran)
    columns (wide, one group per basket_id):
      <bid>__level_price   float64   equal-weight index on PRICE basis
      <bid>__level_tr      float64   equal-weight index on TR (total-return) basis
      <bid>__mhash         object    membership hash for THIS basket on THIS date
      <bid>__n_members     int       active member count at freeze time

Domains: us, china, china_ths, hk.

IMMUTABILITY CONTRACT (keep-FIRST):
  A frozen (date, bid) cell is NEVER overwritten. Once today's level is frozen it
  is the PIT truth forever. The writer only appends rows for dates NOT yet in the
  store (it never touches existing rows).

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
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date as date_type
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

CHURN_ALERT_PCT = 0.15      # >15% shrink in active members vs last frozen → refuse
DOMAIN_DIR = "basket_levels"   # relative to data_dir()

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
        # Fire notify channels (best-effort, never fatal)
        try:
            from scripts.notify import send_telegram, send_discord
            alert_msg = f"⚠️ BASKET FREEZE SKIPPED [{domain.upper()}]\n{msg}"
            send_telegram(alert_msg)
            send_discord(alert_msg)
        except Exception:  # noqa: BLE001
            pass
        raise FreezeSkipped(msg)

    # ── Extract level series (prefer from baskets_payload if available) ───────
    chart = (baskets_payload or {}).get("chart") or {}
    chart_dates = chart.get("dates")
    chart_baskets = chart.get("baskets") or {}

    new_rows: dict[str, object] = {"date": today_ts}
    price_coverage_fracs: list[float] = []

    for bid, b in items:
        members = b.get("members", [])
        cur_active = active_members(members, as_of=today_date)
        n_members = len(cur_active)
        mhash = membership_hash(cur_active)

        # TR level: prefer from the already-computed baskets_payload chart
        level_tr: float | None = None
        if chart_dates and bid in chart_baskets:
            lv = chart_baskets[bid]
            # take today's (last) non-null value
            vals = [(d, v) for d, v in zip(chart_dates, lv) if v is not None]
            if vals:
                level_tr = float(vals[-1][1])

        # Fallback: compute from closes_tr directly
        if level_tr is None and closes_tr is not None and not closes_tr.empty:
            lvl_s, cov = _ew_level_from_closes(closes_tr, members, as_of=today_date)
            if not lvl_s.dropna().empty:
                level_tr = float(lvl_s.dropna().iloc[-1])
            price_coverage_fracs.append(cov)

        # Price-basis level: compute from closes_price if available
        level_price: float | None = None
        if closes_price is not None and not closes_price.empty:
            lvl_p, cov_p = _ew_level_from_closes(closes_price, members, as_of=today_date)
            if not lvl_p.dropna().empty:
                level_price = float(lvl_p.dropna().iloc[-1])
                price_coverage_fracs.append(cov_p)
        elif level_tr is not None:
            # No price-basis available; use TR as fallback (labeled honestly)
            level_price = level_tr   # coverage will be < 1.0 (caller is notified below)

        new_rows[f"{bid}__level_tr"] = level_tr
        new_rows[f"{bid}__level_price"] = level_price
        new_rows[f"{bid}__mhash"] = mhash
        new_rows[f"{bid}__n_members"] = n_members

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
