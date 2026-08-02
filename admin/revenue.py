"""admin/revenue.py — operator billing/revenue analytics (Stripe-computed, live).

The admin-side READ surface over the money: MRR/ARR, active/trialing/canceled counts,
real collected cash, forward projections, and comp give-away counts. One JSON payload,
computed live from Stripe on demand (~60s in-process cache so panel refreshes don't hammer
the API), mirroring the ``admin/entitlements.py`` idiom exactly:

  * plain functions + a lazy ``_billing()`` bridge so this module imports without the
    Stripe dep / keys and tests can monkeypatch ``app.billing`` symbols on the module object;
  * Stripe read via ``billing._stripe()`` (Subscription.list / Invoice.list auto-paging);
  * comp counts via the Management-API PAT path (``users._query`` — read-only SELECT), the
    SAME read plane as the entitlements roster.

The honesty crux (masterplan §3.2, carried over from entitlements):
  * **MRR is what Stripe actually charges**, never plans.yml. We normalize each ACTIVE
    subscription item's real Stripe amount to a monthly figure (monthly→amount, annual→
    amount/12) and sum. plans.yml is the *catalog*; the truth of revenue is the live price
    on the sub.
  * **Trials are NOT counted in MRR.** A trialing sub hasn't paid, so its normalized value is
    surfaced SEPARATELY as "pending" MRR — never folded into MRR/ARR.
  * **Cash is paid invoices only.** The collections series counts real ``amount_paid`` and
    EXCLUDES $0 trial invoices from the cash figures (they are counted as trial-starts instead).
  * **Projections are labeled projections.** Every projection object carries {method,
    assumptions[]} — no naked forward number. The trial-conversion rate is derived from the
    sub history (converted / total-ended trials); with n<5 ended trials it falls back to 0.4
    and flags the assumption.

Stripe unconfigured → {"ok": false, "error": "stripe not configured"} so the panel shows an
honest empty state (same graceful-degrade contract as the rest of the console).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from . import users

log = logging.getLogger("macro.admin.revenue")

# The catalog's entitlement tiers. `_sub_tier` resolves through
# billing._lookup_key_to_tier, so a subscription still sitting on a pre-rename PRICE
# already reports the current tier and lands in these buckets rather than "other".
_TIERS = ("essential", "pro")
_INTERVALS = ("monthly", "annual")
_TRIALING_ACTIVE = ("active", "trialing")

# Trial-conversion fallback when the sub history has too few ended trials to estimate from.
_CONVERSION_FALLBACK = 0.4
_CONVERSION_MIN_N = 5           # need >=5 ended trials before we trust the empirical rate
_TRIAL_SOON_DAYS = 7            # trial_end histogram bucket: converting within a week

# Collections windows + monthly-series depth.
_CASH_WINDOWS = (30, 90)        # rolling paid-invoice cash windows (days)
_CASH_MONTHS = 6               # months in the small cash series
_INVOICE_LOOKBACK_DAYS = 90    # invoice pull window (covers 30/90d cash + recent trial-starts)

# In-process cache — the panel refresh button + auto-polls shouldn't re-hit Stripe every click.
_CACHE_TTL_S = 60.0
_CACHE: dict | None = None
_CACHE_TS = 0.0
_CACHE_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# billing-spine bridge (lazy — mirrors entitlements._billing)
# --------------------------------------------------------------------------- #
def _billing():
    from app import billing  # noqa: PLC0415
    return billing


def _stripe_configured() -> bool:
    """True iff Stripe can actually be called (key present + SDK importable).

    Mirrors billing._stripe's own preconditions (STRIPE_SECRET_KEY set) but WITHOUT raising —
    revenue surfaces an honest ok:false empty state rather than a 503, so we probe first.
    """
    if not os.environ.get("STRIPE_SECRET_KEY", "").strip():
        return False
    try:
        import stripe  # noqa: F401,PLC0415
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Stripe field readers (tolerate dict OR StripeObject, like app/billing.py)
# --------------------------------------------------------------------------- #
def _g(obj, key, default=None):
    """Read a field off a Stripe object whether it's a dict or an attr-style StripeObject."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _iter_all(listable, **kw):
    """Auto-page a Stripe list endpoint.

    Prefer the SDK's ``auto_paging_iter`` (what the mission asks for); fall back to the single
    page's ``.data`` when the fake/stub in tests doesn't implement auto-paging.
    """
    resp = listable.list(**kw)
    it = getattr(resp, "auto_paging_iter", None)
    if callable(it):
        return list(it())
    return list(_g(resp, "data", []) or [])


def _sub_items(sub):
    items = _g(sub, "items", {})
    return _g(items, "data", []) or []


def _price_interval_months(price) -> float | None:
    """Months-per-billing-cycle for a Stripe price, from recurring.interval(+count).

    monthly→1, annual→12, weekly→~0.2301, daily→~0.0329. Returns None if not recurring so the
    caller can skip a one-off/unpriced item rather than mis-normalize it.
    """
    rec = _g(price, "recurring", None)
    interval = _g(rec, "interval", None) if rec is not None else _g(price, "interval", None)
    count = _g(rec, "interval_count", 1) if rec is not None else _g(price, "interval_count", 1)
    try:
        count = int(count or 1)
    except (TypeError, ValueError):
        count = 1
    per = {"month": 1.0, "year": 12.0, "week": 12.0 / 52.0, "day": 12.0 / 365.0}.get(interval)
    if per is None:
        return None
    return per * count


def _sub_interval_label(sub) -> str:
    """'monthly' | 'annual' | 'other' for the interval breakdown, from the first item's price."""
    items = _sub_items(sub)
    if not items:
        return "other"
    price = _g(items[0], "price", None)
    rec = _g(price, "recurring", None) if price is not None else None
    interval = _g(rec, "interval", None) if rec is not None else _g(price, "interval", None)
    return {"month": "monthly", "year": "annual"}.get(interval, "other")


def _sub_tier(sub) -> str | None:
    """Resolve a subscription's tier from its item price lookup_keys via the billing catalog.

    Reuses billing._lookup_key_to_tier so tier resolution matches the entitlement spine exactly
    (highest-ranked mapped tier across items; unknown-only → None, fail closed)."""
    b = _billing()
    try:
        lk2t = b._lookup_key_to_tier()
        rank = b._tier_rank()
    except Exception:  # noqa: BLE001 — catalog unreadable → tier unknown
        return None
    found: list[str] = []
    for it in _sub_items(sub):
        price = _g(it, "price", None)
        lk = _g(price, "lookup_key", None)
        if lk and lk in lk2t:
            found.append(lk2t[lk])
    if not found:
        return None
    return max(found, key=lambda t: rank.index(t) if t in rank else -1)


def _sub_monthly_cents(sub) -> int:
    """Normalized MONTHLY value of a subscription in cents, from its items' REAL Stripe amounts.

    Per item: unit_amount × quantity, divided by the item's billing-cycle length in months
    (monthly→/1, annual→/12). This is the MRR contribution of one sub — computed from what
    Stripe charges, never plans.yml. A non-recurring / unpriced item contributes 0.
    """
    total = 0.0
    for it in _sub_items(sub):
        price = _g(it, "price", None)
        if price is None:
            continue
        amount = _g(price, "unit_amount", None)
        if amount is None:
            continue
        qty = _g(it, "quantity", 1) or 1
        months = _price_interval_months(price)
        if not months:
            continue
        total += (float(amount) * float(qty)) / months
    return int(round(total))


# --------------------------------------------------------------------------- #
# Comp counts (Management-API PAT read — same plane as the entitlements roster)
# --------------------------------------------------------------------------- #
def _comp_counts() -> dict:
    """Count comp entitlement rows by tier (revenue-zero give-aways), via users._query.

    Returns {"ok": bool, "by_tier": {tier: n}, "total": n}. Degrades to ok:false (no PAT /
    query error) without failing the whole payload — comps are a secondary panel row.
    """
    st = users.status()
    if not st.get("configured"):
        return {"ok": False, "by_tier": {}, "total": 0, "reason": st.get("reason")}
    try:
        rows = users._query(
            "select coalesce(e.tier,'free') as tier, count(*)::int as n "
            "from public.user_entitlements e where e.source = 'comp' group by 1 order by 1")
        by_tier = {r["tier"]: r["n"] for r in (rows or [])}
        return {"ok": True, "by_tier": by_tier, "total": sum(by_tier.values())}
    except Exception as exc:  # noqa: BLE001
        log.warning("revenue: comp count failed (%s)", exc)
        return {"ok": False, "by_tier": {}, "total": 0, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Pure reducers (side-effect-free → unit-testable without any network)
# --------------------------------------------------------------------------- #
def _month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _recent_month_keys(n: int, *, now: datetime) -> list[str]:
    """The last `n` month keys (YYYY-MM), oldest→newest, ending in `now`'s month."""
    keys: list[str] = []
    y, m = now.year, now.month
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y -= 1
            m = 12
    return list(reversed(keys))


def _linear_slope(ys: list[float]) -> float:
    """Least-squares slope of ys over x=0..n-1 (per-step). 0 for n<2 or degenerate."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return num / denom


def _projections(mrr_dollars: float, trial_pending_dollars: float,
                 conversion_rate: float, conversion_assumed: bool,
                 conversion_n: int, monthly_cash_series: list[dict]) -> dict:
    """Build the three labeled projections. Every value carries {method, assumptions[]}.

    naive_12mo      = current MRR × 12.
    trial_adjusted  = (MRR + trialing_pending_MRR × conversion_rate) × 12.
    growth_projection = linear slope on the monthly cash series (needs ≥3 points), extended
                        12 months from the last point, clamped ≥0.
    """
    naive = {
        "value_usd": round(mrr_dollars * 12, 2),
        "method": "current MRR × 12",
        "assumptions": ["MRR stays flat for 12 months", "no churn, no new subscriptions"],
    }

    conv_assumptions = [
        f"trialing pending MRR (${round(trial_pending_dollars, 2)}/mo) converts at "
        f"{round(conversion_rate * 100)}%",
        "converted trial revenue is added to current MRR, then annualized",
    ]
    if conversion_assumed:
        conv_assumptions.append(
            f"conversion rate ASSUMED at {round(_CONVERSION_FALLBACK * 100)}% "
            f"(only {conversion_n} ended trial(s) in history; need {_CONVERSION_MIN_N})")
    else:
        conv_assumptions.append(
            f"conversion rate {round(conversion_rate * 100)}% derived from {conversion_n} "
            f"ended trial(s) in Stripe history")
    trial_adjusted = {
        "value_usd": round((mrr_dollars + trial_pending_dollars * conversion_rate) * 12, 2),
        "method": "(MRR + trialing_pending_MRR × conversion_rate) × 12",
        "conversion_rate": round(conversion_rate, 4),
        "conversion_assumed": conversion_assumed,
        "assumptions": conv_assumptions,
    }

    # growth_projection — fit a line on the monthly cash points, extend 12 months. The ≥3 gate
    # counts months that ACTUALLY collected cash (non-zero): fitting a slope through leading
    # zero-filled buckets would invent a trend that isn't there. Once ≥3 real months exist, we
    # fit over the CONTIGUOUS tail from the first non-zero month so the run-up isn't distorted
    # by pre-launch zeros.
    all_ys = [float(p.get("cash_usd") or 0.0) for p in monthly_cash_series]
    nonzero_pts = sum(1 for y in all_ys if y > 0)
    first_nz = next((i for i, y in enumerate(all_ys) if y > 0), None)
    cash_ys = all_ys[first_nz:] if first_nz is not None else []
    if nonzero_pts >= 3:
        slope = _linear_slope(cash_ys)
        last = cash_ys[-1]
        # extend 12 months past the last observed month, clamped at 0 (no negative revenue)
        projected = max(0.0, last + slope * 12)
        growth = {
            "value_usd": round(projected, 2),
            "method": ("linear least-squares fit on the last "
                       f"{len(cash_ys)} months of collected cash, extended 12 months"),
            "monthly_slope_usd": round(slope, 2),
            "assumptions": [
                "recent collected-cash trend continues linearly",
                "projects the 12-months-ahead monthly cash run-rate (clamped ≥ 0)",
            ],
        }
    else:
        growth = {
            "value_usd": None,
            "method": "linear fit on monthly cash (needs ≥3 months with cash)",
            "assumptions": [f"insufficient history: only {nonzero_pts} month(s) with collected cash"],
        }

    return {"naive_12mo": naive, "trial_adjusted": trial_adjusted, "growth_projection": growth}


# --------------------------------------------------------------------------- #
# Live compute (the one place we touch Stripe)
# --------------------------------------------------------------------------- #
def _compute(now: datetime | None = None) -> dict:
    """Compute the full revenue payload from live Stripe state. Assumes Stripe is configured."""
    now = now or datetime.now(timezone.utc)
    b = _billing()
    stripe = b._stripe()

    # ---- subscriptions (status=all, expand item price data), auto-paged ----------------------
    subs = _iter_all(stripe.Subscription, status="all", limit=100,
                     expand=["data.items.data.price"])

    # per-tier × per-interval active counts; trialing counts; trial_end histogram; canceled-this-month
    active_counts: dict[str, dict[str, int]] = {t: {i: 0 for i in _INTERVALS} for t in _TIERS}
    active_counts_other = {"other": 0}
    trialing_count = 0
    trialing_convert_soon = 0            # trial_end within _TRIAL_SOON_DAYS
    canceled_this_month = 0
    mrr_cents = 0
    trial_pending_cents = 0
    mrr_by_tier_cents: dict[str, int] = {t: 0 for t in _TIERS}
    mrr_by_interval_cents: dict[str, int] = {i: 0 for i in _INTERVALS}
    mrr_by_interval_cents["other"] = 0

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    soon_cutoff = now + timedelta(days=_TRIAL_SOON_DAYS)

    # trial-conversion estimate from history: a trial "ended" if it left 'trialing' behind.
    trials_ended = 0
    trials_converted = 0

    for s in subs:
        status = _g(s, "status")
        tier = _sub_tier(s)
        interval = _sub_interval_label(s)
        monthly_cents = _sub_monthly_cents(s)

        if status == "active":
            if tier in active_counts and interval in _INTERVALS:
                active_counts[tier][interval] += 1
            else:
                active_counts_other["other"] += 1
            mrr_cents += monthly_cents
            if tier in mrr_by_tier_cents:
                mrr_by_tier_cents[tier] += monthly_cents
            if interval in mrr_by_interval_cents:
                mrr_by_interval_cents[interval] += monthly_cents
            else:
                mrr_by_interval_cents["other"] += monthly_cents
        elif status == "trialing":
            trialing_count += 1
            trial_pending_cents += monthly_cents
            te = _g(s, "trial_end")
            if te:
                try:
                    te_dt = datetime.fromtimestamp(int(te), tz=timezone.utc)
                    if now <= te_dt <= soon_cutoff:
                        trialing_convert_soon += 1
                except (TypeError, ValueError, OSError):
                    pass

        # canceled-this-month: canceled_at within the current calendar month
        cancel_at = _g(s, "canceled_at")
        if cancel_at:
            try:
                ca_dt = datetime.fromtimestamp(int(cancel_at), tz=timezone.utc)
                if ca_dt >= month_start:
                    canceled_this_month += 1
            except (TypeError, ValueError, OSError):
                pass

        # conversion history: any sub that has a trial_end in the past (trial concluded).
        te = _g(s, "trial_end")
        if te:
            try:
                te_dt = datetime.fromtimestamp(int(te), tz=timezone.utc)
                if te_dt < now:
                    trials_ended += 1
                    # converted = the trial ended AND the sub is now paying / was not canceled
                    # during the trial (active, or past_due/canceled *after* a paid period began).
                    if status in ("active", "past_due"):
                        trials_converted += 1
            except (TypeError, ValueError, OSError):
                pass

    # ---- invoices (last 90d, paid), auto-paged: real cash + trial-starts ----------------------
    since = int((now - timedelta(days=_INVOICE_LOOKBACK_DAYS)).timestamp())
    invoices = _iter_all(stripe.Invoice, status="paid", limit=100, created={"gte": since})

    window_cash_cents = {w: 0 for w in _CASH_WINDOWS}
    window_cutoffs = {w: now - timedelta(days=w) for w in _CASH_WINDOWS}
    month_keys = _recent_month_keys(_CASH_MONTHS, now=now)
    month_cash_cents = {k: 0 for k in month_keys}
    trial_start_invoices = 0             # $0 paid invoices = trial starts (excluded from cash)
    paid_invoice_count = 0

    for inv in invoices:
        amount_paid = _g(inv, "amount_paid", 0) or 0
        # timestamp: prefer status_transitions.paid_at, else created
        paid_at = None
        stx = _g(inv, "status_transitions", None)
        if stx is not None:
            paid_at = _g(stx, "paid_at", None)
        if not paid_at:
            paid_at = _g(inv, "created", None)
        try:
            paid_dt = datetime.fromtimestamp(int(paid_at), tz=timezone.utc) if paid_at else None
        except (TypeError, ValueError, OSError):
            paid_dt = None

        if amount_paid <= 0:
            # $0 trial invoice — count as a trial-start, EXCLUDE from the cash series.
            trial_start_invoices += 1
            continue

        paid_invoice_count += 1
        for w in _CASH_WINDOWS:
            if paid_dt is not None and paid_dt >= window_cutoffs[w]:
                window_cash_cents[w] += amount_paid
        if paid_dt is not None:
            mk = _month_key(paid_dt)
            if mk in month_cash_cents:
                month_cash_cents[mk] += amount_paid

    # ---- assemble ----------------------------------------------------------------------------
    def _usd(cents) -> float:
        return round(cents / 100.0, 2)

    mrr_usd = _usd(mrr_cents)
    trial_pending_usd = _usd(trial_pending_cents)

    conversion_assumed = trials_ended < _CONVERSION_MIN_N
    if conversion_assumed:
        conversion_rate = _CONVERSION_FALLBACK
    else:
        conversion_rate = (trials_converted / trials_ended) if trials_ended else _CONVERSION_FALLBACK

    monthly_cash_series = [{"month": k, "cash_usd": _usd(month_cash_cents[k])} for k in month_keys]

    active_total = sum(active_counts[t][i] for t in _TIERS for i in _INTERVALS) + active_counts_other["other"]

    payload = {
        "ok": True,
        "generated_at": now.isoformat(),
        "now": {
            "active_by_tier_interval": active_counts,
            "active_other": active_counts_other["other"],
            "active_total": active_total,
            "trialing": trialing_count,
            "trialing_convert_within_7d": trialing_convert_soon,
            "canceled_this_month": canceled_this_month,
        },
        "mrr": {
            "mrr_usd": mrr_usd,
            "arr_usd": round(mrr_usd * 12, 2),
            "by_tier_usd": {t: _usd(mrr_by_tier_cents[t]) for t in _TIERS},
            "by_interval_usd": {k: _usd(v) for k, v in mrr_by_interval_cents.items()},
            "trialing_pending_usd": trial_pending_usd,
            "note": ("MRR = Σ active subs normalized to monthly from REAL Stripe amounts "
                     "(annual ÷ 12); trials are pending, NOT counted in MRR."),
        },
        "collections": {
            "windows_usd": {f"{w}d": _usd(window_cash_cents[w]) for w in _CASH_WINDOWS},
            "monthly_series": monthly_cash_series,
            "paid_invoice_count_90d": paid_invoice_count,
            "trial_start_invoices_90d": trial_start_invoices,
            "note": ("real cash = paid invoice amount_paid; $0 trial invoices excluded from "
                     "cash and counted as trial-starts."),
        },
        "projections": _projections(
            mrr_usd, trial_pending_usd, conversion_rate, conversion_assumed,
            trials_ended, monthly_cash_series),
        "conversion": {
            "rate": round(conversion_rate, 4),
            "assumed": conversion_assumed,
            "trials_ended": trials_ended,
            "trials_converted": trials_converted,
        },
        "comps": _comp_counts(),
    }
    return payload


# --------------------------------------------------------------------------- #
# Public entrypoint (GET /api/revenue) — cached ~60s
# --------------------------------------------------------------------------- #
def summary(*, force: bool = False) -> dict:
    """The GET /api/revenue payload: live Stripe revenue analytics, ~60s in-process cache.

    Stripe unconfigured → {"ok": false, "error": "stripe not configured"} (honest empty state).
    Any Stripe/compute error → {"ok": false, "error": <msg>} rather than a 500 — the panel then
    renders a not-connected card, never a broken dashboard.
    """
    global _CACHE, _CACHE_TS
    if not _stripe_configured():
        return {"ok": False, "error": "stripe not configured"}

    now = time.monotonic()
    if not force:
        with _CACHE_LOCK:
            if _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL_S:
                return _CACHE

    try:
        payload = _compute()
    except Exception as exc:  # noqa: BLE001
        log.warning("revenue: compute failed (%s)", exc)
        return {"ok": False, "error": str(exc)}

    with _CACHE_LOCK:
        _CACHE = payload
        _CACHE_TS = time.monotonic()
    return payload
