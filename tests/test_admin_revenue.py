"""tests/test_admin_revenue.py — admin/revenue.py (billing/revenue analytics suite).

Fully offline. The two data planes are stubbed at their seams, exactly like
test_admin_entitlements.py:
  * Stripe   → monkeypatch ``app.billing._stripe`` to a fake exposing Subscription.list /
    Invoice.list with a scripted set of subs/invoices (auto-paging + .data both supported).
    Prices carry real ``lookup_key`` + ``unit_amount`` + ``recurring.interval`` so the module's
    MRR normalization runs against genuine Stripe-shaped amounts (never plans.yml).
  * Comps    → monkeypatch ``admin.users._query`` (the Management-API PAT SELECT) + force
    ``users.status()`` configured, so the comp-count read exercises real plumbing, no network.

Coverage maps to the mission's test asks:
  - MRR math: monthly amount counts as-is, annual amount ÷ 12 (real Stripe amounts).
  - trial pending MRR is SEPARATE from MRR (trials never counted in MRR/ARR).
  - conversion-rate fallback flag (n<5 ended trials → assumed 0.4).
  - every projection object carries {method, assumptions[]}.
  - cash series excludes $0 (trial) invoices; counts them as trial-starts.
  - stripe unconfigured → {ok: false, error: "stripe not configured"}.
  - live server: 401 for an unauthenticated GET /api/revenue.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import auth, revenue, users  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake Stripe shapes (attr-style StripeObjects; revenue._g tolerates dict or attr)
# --------------------------------------------------------------------------- #
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _price(lookup_key, unit_amount, interval, interval_count=1):
    return _Obj(lookup_key=lookup_key, unit_amount=unit_amount,
                recurring=_Obj(interval=interval, interval_count=interval_count))


def _item(price, quantity=1):
    return _Obj(price=price, quantity=quantity)


def _sub(status, *items, trial_end=None, canceled_at=None):
    return _Obj(status=status, items=_Obj(data=list(items)),
                trial_end=trial_end, canceled_at=canceled_at)


def _invoice(amount_paid, paid_at):
    return _Obj(amount_paid=amount_paid,
                status_transitions=_Obj(paid_at=paid_at), created=paid_at)


class _ListEndpoint:
    def __init__(self, rows):
        self._rows = rows

    def list(self, **kw):
        rows = list(self._rows)
        return _Obj(data=rows, auto_paging_iter=lambda: iter(rows))


class _FakeStripe:
    def __init__(self, subs=None, invoices=None):
        self.Subscription = _ListEndpoint(subs or [])
        self.Invoice = _ListEndpoint(invoices or [])


# real plans.yml lookup_keys + amounts (cents)
INSIDER_M = _price("insider_monthly", 6900, "month")
INSIDER_A = _price("insider_annual", 58800, "year")
PRO_M = _price("pro_monthly", 9900, "month")
PRO_A = _price("pro_annual", 82800, "year")

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def _epoch(dt):
    return int(dt.timestamp())


@pytest.fixture(autouse=True)
def _bust_cache():
    """Every test starts with a cold cache and a configured-Stripe env."""
    revenue._CACHE = None
    revenue._CACHE_TS = 0.0
    old = os.environ.get("STRIPE_SECRET_KEY")
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
    yield
    revenue._CACHE = None
    revenue._CACHE_TS = 0.0
    if old is None:
        os.environ.pop("STRIPE_SECRET_KEY", None)
    else:
        os.environ["STRIPE_SECRET_KEY"] = old


@pytest.fixture
def wired(monkeypatch):
    """Wire billing._stripe to a fake and comps to an empty roster. Returns a setter."""
    from app import billing

    holder = {"fake": _FakeStripe()}
    monkeypatch.setattr(revenue, "_stripe_configured", lambda: True)
    monkeypatch.setattr(billing, "_stripe", lambda: holder["fake"])
    # comps default: configured Supabase, no comp rows (individual tests override _query)
    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(users, "_query", lambda sql: [])

    def _set(subs=None, invoices=None):
        holder["fake"] = _FakeStripe(subs=subs, invoices=invoices)
        monkeypatch.setattr(billing, "_stripe", lambda: holder["fake"])
        return holder["fake"]

    return _set


def _compute(subs=None, invoices=None):
    """Run the pure compute at the fixed NOW (bypasses the cache/config gate)."""
    return revenue._compute(now=NOW)


# ===========================================================================
# MRR math — monthly counts as-is, annual ÷ 12 (real Stripe amounts)
# ===========================================================================
def test_mrr_monthly_and_annual_normalization(wired, monkeypatch):
    wired(subs=[
        _sub("active", _item(INSIDER_M)),   # 6900/mo  -> 6900
        _sub("active", _item(PRO_A)),       # 82800/yr -> 82800/12 = 6900
    ])
    out = revenue._compute(now=NOW)
    # 6900 + 6900 = 13800 cents = $138.00
    assert out["mrr"]["mrr_usd"] == pytest.approx(138.00)
    assert out["mrr"]["arr_usd"] == pytest.approx(138.00 * 12)
    # by-interval split: monthly leg $69, annual leg $69 (82800/12)
    assert out["mrr"]["by_interval_usd"]["monthly"] == pytest.approx(69.00)
    assert out["mrr"]["by_interval_usd"]["annual"] == pytest.approx(69.00)
    # by-tier: essential $69 (monthly), pro $69 (annual/12). The fixture prices carry
    # PRE-RENAME lookup_keys on purpose — _sub_tier resolves them through the catalog's
    # legacy_lookup_keys, so a grandfathered subscription lands in the current tier bucket
    # instead of the "other" one.
    assert out["mrr"]["by_tier_usd"]["essential"] == pytest.approx(69.00)
    assert out["mrr"]["by_tier_usd"]["pro"] == pytest.approx(69.00)
    # counts land in the right tier×interval buckets
    ai = out["now"]["active_by_tier_interval"]
    assert ai["essential"]["monthly"] == 1 and ai["pro"]["annual"] == 1
    assert out["now"]["active_total"] == 2


def test_annual_divided_by_twelve_exact(wired):
    wired(subs=[_sub("active", _item(INSIDER_A))])   # 58800/yr -> 4900/mo = $49.00
    out = revenue._compute(now=NOW)
    assert out["mrr"]["mrr_usd"] == pytest.approx(49.00)


# ===========================================================================
# Trial pending MRR is SEPARATE (trials never counted in MRR/ARR)
# ===========================================================================
def test_trialing_pending_is_separated_from_mrr(wired):
    wired(subs=[
        _sub("active", _item(PRO_M)),                                  # 9900 -> MRR
        _sub("trialing", _item(PRO_M), trial_end=_epoch(NOW + timedelta(days=3))),   # pending only
    ])
    out = revenue._compute(now=NOW)
    # only the active sub is in MRR
    assert out["mrr"]["mrr_usd"] == pytest.approx(99.00)
    # the trial's normalized monthly value is pending, NOT in MRR
    assert out["mrr"]["trialing_pending_usd"] == pytest.approx(99.00)
    assert out["now"]["trialing"] == 1
    # trial_end within 7d -> counted in the convert-soon histogram bucket
    assert out["now"]["trialing_convert_within_7d"] == 1


def test_trial_ending_far_out_not_in_soon_bucket(wired):
    wired(subs=[
        _sub("trialing", _item(INSIDER_M), trial_end=_epoch(NOW + timedelta(days=30))),
    ])
    out = revenue._compute(now=NOW)
    assert out["now"]["trialing"] == 1
    assert out["now"]["trialing_convert_within_7d"] == 0
    assert out["mrr"]["mrr_usd"] == pytest.approx(0.0)   # no active subs


# ===========================================================================
# Conversion-rate fallback flag (n<5 ended trials -> assumed 0.4)
# ===========================================================================
def test_conversion_rate_fallback_flag_when_few_ended_trials(wired):
    # one active sub whose trial already ended (1 ended trial < 5 -> assumed)
    wired(subs=[
        _sub("active", _item(PRO_M), trial_end=_epoch(NOW - timedelta(days=10))),
    ])
    out = revenue._compute(now=NOW)
    conv = out["conversion"]
    assert conv["assumed"] is True
    assert conv["rate"] == pytest.approx(0.4)
    assert conv["trials_ended"] == 1
    # the projection surfaces the assumed flag too
    assert out["projections"]["trial_adjusted"]["conversion_assumed"] is True


def test_conversion_rate_empirical_when_enough_history(wired):
    # 6 ended trials: 3 converted (active/past_due), 3 not (canceled) -> rate 0.5, NOT assumed
    past = _epoch(NOW - timedelta(days=20))
    subs = []
    for _ in range(3):
        subs.append(_sub("active", _item(PRO_M), trial_end=past))       # converted
    for _ in range(3):
        subs.append(_sub("canceled", _item(PRO_M), trial_end=past))     # not converted
    wired(subs=subs)
    out = revenue._compute(now=NOW)
    conv = out["conversion"]
    assert conv["assumed"] is False
    assert conv["trials_ended"] == 6 and conv["trials_converted"] == 3
    assert conv["rate"] == pytest.approx(0.5)


# ===========================================================================
# Every projection object carries {method, assumptions[]}
# ===========================================================================
def test_projections_carry_method_and_assumptions(wired):
    # >=3 monthly cash points so growth_projection produces a value
    invs = []
    for i, m in enumerate((3, 4, 5, 6, 7)):   # May..Jul 2026 within window
        invs.append(_invoice(10000 + i * 1000, _epoch(datetime(2026, m, 15, tzinfo=timezone.utc))))
    wired(subs=[_sub("active", _item(PRO_M))], invoices=invs)
    out = revenue._compute(now=NOW)
    proj = out["projections"]
    for key in ("naive_12mo", "trial_adjusted", "growth_projection"):
        assert key in proj, key
        assert "method" in proj[key] and proj[key]["method"], key
        assert isinstance(proj[key]["assumptions"], list) and proj[key]["assumptions"], key
    # naive = MRR($99) × 12
    assert proj["naive_12mo"]["value_usd"] == pytest.approx(99.00 * 12)
    # growth had >=3 points -> a real number (not None)
    assert proj["growth_projection"]["value_usd"] is not None


def test_growth_projection_none_with_too_few_points(wired):
    # only 2 months with cash -> growth cannot fit (needs >=3)
    invs = [
        _invoice(5000, _epoch(datetime(2026, 6, 10, tzinfo=timezone.utc))),
        _invoice(7000, _epoch(datetime(2026, 7, 10, tzinfo=timezone.utc))),
    ]
    wired(subs=[_sub("active", _item(INSIDER_M))], invoices=invs)
    out = revenue._compute(now=NOW)
    assert out["projections"]["growth_projection"]["value_usd"] is None
    assert out["projections"]["growth_projection"]["assumptions"]   # still explains why


# ===========================================================================
# Cash series excludes $0 (trial) invoices; counts them as trial-starts
# ===========================================================================
def test_cash_series_excludes_zero_invoices_counts_trial_starts(wired):
    invs = [
        _invoice(0, _epoch(NOW - timedelta(days=2))),        # $0 trial-start -> excluded from cash
        _invoice(0, _epoch(NOW - timedelta(days=5))),        # another trial-start
        _invoice(12000, _epoch(NOW - timedelta(days=3))),    # $120 real cash (in 30d)
        _invoice(8000, _epoch(NOW - timedelta(days=60))),    # $80 real cash (in 90d, not 30d)
    ]
    wired(subs=[], invoices=invs)
    out = revenue._compute(now=NOW)
    coll = out["collections"]
    # 30d cash = only the $120 (the $0s excluded)
    assert coll["windows_usd"]["30d"] == pytest.approx(120.00)
    # 90d cash = $120 + $80 = $200
    assert coll["windows_usd"]["90d"] == pytest.approx(200.00)
    # the two $0 invoices are surfaced as trial-starts, not cash
    assert coll["trial_start_invoices_90d"] == 2
    assert coll["paid_invoice_count_90d"] == 2   # only the two non-zero ones
    # monthly series is present and never includes the $0 rows
    assert len(coll["monthly_series"]) == revenue._CASH_MONTHS
    july = next(m for m in coll["monthly_series"] if m["month"] == "2026-07")
    assert july["cash_usd"] == pytest.approx(120.00)


# ===========================================================================
# Comps — count by tier via users._query (revenue-zero give-aways)
# ===========================================================================
def test_comps_counted_by_tier(wired, monkeypatch):
    monkeypatch.setattr(users, "_query",
                        lambda sql: [{"tier": "insider", "n": 2}, {"tier": "pro", "n": 1}])
    wired(subs=[], invoices=[])
    out = revenue._compute(now=NOW)
    comps = out["comps"]
    assert comps["ok"] is True
    assert comps["by_tier"] == {"insider": 2, "pro": 1}
    assert comps["total"] == 3


def test_comps_degrade_when_supabase_unconfigured(wired, monkeypatch):
    monkeypatch.setattr(users, "status", lambda: {"configured": False, "reason": "no PAT"})
    wired(subs=[], invoices=[])
    out = revenue._compute(now=NOW)
    assert out["comps"]["ok"] is False
    # the rest of the payload is still fine (comps are a secondary row)
    assert out["ok"] is True


# ===========================================================================
# canceled-this-month
# ===========================================================================
def test_canceled_this_month_counts_current_calendar_month(wired):
    wired(subs=[
        _sub("canceled", _item(PRO_M), canceled_at=_epoch(datetime(2026, 7, 5, tzinfo=timezone.utc))),   # this month
        _sub("canceled", _item(PRO_M), canceled_at=_epoch(datetime(2026, 6, 20, tzinfo=timezone.utc))),  # last month
    ])
    out = revenue._compute(now=NOW)
    assert out["now"]["canceled_this_month"] == 1


# ===========================================================================
# Stripe unconfigured -> honest empty state
# ===========================================================================
def test_unconfigured_returns_ok_false(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    out = revenue.summary()
    assert out == {"ok": False, "error": "stripe not configured"}


def test_summary_uses_cache(wired, monkeypatch):
    calls = {"n": 0}
    payload = {"ok": True, "generated_at": NOW.isoformat()}

    def _fake_compute(now=None):
        calls["n"] += 1
        return dict(payload)

    monkeypatch.setattr(revenue, "_compute", _fake_compute)
    revenue._CACHE = None
    revenue._CACHE_TS = 0.0
    a = revenue.summary()
    b = revenue.summary()           # within TTL -> cached, no second compute
    assert a["ok"] and b["ok"] and calls["n"] == 1
    c = revenue.summary(force=True)  # force -> recompute
    assert c["ok"] and calls["n"] == 2


# ===========================================================================
# Live server auth — 401 (no session) for GET /api/revenue
# ===========================================================================
def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                __import__("admin.server", fromlist=["Handler"]).Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _req(port, path, method="GET", body=None, headers=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=10)


def test_revenue_route_requires_auth(monkeypatch):
    old = {k: os.environ.get(k) for k in ("ADMIN_DEPLOYED", "ADMIN_PASSWORD", "ADMIN_SESSION_SECRET")}
    os.environ.update({"ADMIN_DEPLOYED": "1", "ADMIN_PASSWORD": "s3cret", "ADMIN_SESSION_SECRET": "it-secret"})
    auth._attempts.clear()
    httpd, port = _server()
    try:
        try:
            _req(port, "/api/revenue")
            raise AssertionError("expected 401 for unauthenticated GET /api/revenue")
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        httpd.shutdown(); httpd.server_close()
        auth._attempts.clear()
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
