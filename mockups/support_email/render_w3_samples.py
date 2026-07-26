"""Render the W3 billing emails with realistic fixture data (SEE W3 visual proof).

    python3 mockups/support_email/render_w3_samples.py [<out-dir>]

Writes one .html + one .txt per template into ``<out-dir>`` (a temp directory by default —
it never dirties the repo). Open the HTML raw in a browser and compare with
``email_receipt_sample.html``: that is the check the W2 base swap has to keep passing,
since ``app/billing_emails.py::_render`` is the only place the base is chosen. The
committed proof of the current output is in ``crops/w3_billing/``.

The fixtures deliberately mix currencies and cadences: a USD monthly trial, a EUR annual
receipt, a USD mid-period upgrade, a USD dunning notice with a retry date, a USD annual
cancellation, and a JPY (zero-decimal) trial-ending reminder. If any of those render
wrong, the money/date helpers are wrong.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
       else Path(tempfile.gettempdir()) / "w3_email_samples")
sys.path.insert(0, str(REPO))
OUT.mkdir(parents=True, exist_ok=True)

from app import billing_emails as be  # noqa: E402


def ep(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def sub(*, status, lookup_key, unit_amount, currency, cpe,
        trial_start=None, trial_end=None, period_start=None, **extra):
    o = {
        "id": "sub_9F3A", "object": "subscription", "customer": "cus_9F3A", "status": status,
        "current_period_start": period_start,
        "items": {"data": [{
            "id": "si_1",
            "price": {"id": "price_1", "lookup_key": lookup_key, "unit_amount": unit_amount,
                      "currency": currency, "interval": lookup_key.rsplit("_", 1)[-1]},
            "current_period_end": cpe,
        }]},
        "metadata": {"mm_user_id": "6d1a-user"},
    }
    if trial_start:
        o["trial_start"] = trial_start
    if trial_end:
        o["trial_end"] = trial_end
    o.update(extra)
    return o


SAMPLES: list[tuple[str, be.EmailSpec]] = []

# 1 — purchase / trial start (Insider monthly, USD, 7-day trial)
SAMPLES.append(("billing_purchase_trial", be.spec_purchase(
    sub(status="trialing", lookup_key="insider_monthly", unit_amount=6900, currency="usd",
        cpe=ep(2026, 8, 1), trial_start=ep(2026, 7, 25), trial_end=ep(2026, 8, 1),
        period_start=ep(2026, 7, 25)),
    {"tier": "insider", "status": "trialing", "current_period_end": "2026-08-01T00:00:00+00:00",
     "features": ["site_full", "terminal_live_options"], "plan_interval": "monthly"},
    datetime(2026, 7, 25, tzinfo=timezone.utc))))

# 2 — purchase, NO trial, non-USD, non-$69 (proves nothing is hardcoded)
SAMPLES.append(("billing_purchase_receipt_eur", be.spec_purchase(
    sub(status="active", lookup_key="pro_annual", unit_amount=74400, currency="eur",
        cpe=ep(2027, 7, 26), period_start=ep(2026, 7, 26)),
    {"tier": "pro", "status": "active", "current_period_end": "2027-07-26T00:00:00+00:00",
     "features": ["site_full", "terminal_live_options", "chat_opus"], "plan_interval": "annual"},
    datetime(2026, 7, 26, tzinfo=timezone.utc))))

# 3 — upgrade insider·monthly -> pro·monthly, mid-period (proration invoiced)
SAMPLES.append(("billing_upgrade", be.spec_upgrade(
    sub(status="active", lookup_key="pro_monthly", unit_amount=9900, currency="usd",
        cpe=ep(2026, 8, 14), period_start=ep(2026, 7, 14)),
    {"tier": "insider", "status": "active", "interval": "monthly",
     "features": ["site_full", "terminal_live_options"],
     "current_period_end": "2026-08-14T00:00:00+00:00"},
    {"tier": "pro", "status": "active", "plan_interval": "monthly",
     "features": ["site_full", "terminal_live_options", "chat_opus"],
     "current_period_end": "2026-08-14T00:00:00+00:00"},
    datetime(2026, 7, 26, tzinfo=timezone.utc))))

# 4 — payment failed, FIRST attempt (the only one that mails); access already paused
SAMPLES.append(("billing_payment_failed", be.spec_payment_failed(
    {"id": "in_1", "object": "invoice", "customer": "cus_9F3A", "amount_due": 9900,
     "currency": "usd", "created": ep(2026, 7, 26), "attempt_count": 1,
     "next_payment_attempt": ep(2026, 7, 29), "customer_email": "reader@example.com"},
    {"tier": "pro", "status": "active", "interval": "monthly",
     "current_period_end": "2026-08-14T00:00:00+00:00"},
    {"tier": "free", "status": "past_due", "plan_interval": None, "current_period_end": None},
    datetime(2026, 7, 26, tzinfo=timezone.utc))))

# 5a — cancellation SCHEDULED: what the portal's Cancel button actually emits
SAMPLES.append(("billing_cancellation_scheduled", be.spec_cancel_scheduled(
    sub(status="active", lookup_key="pro_annual", unit_amount=82800, currency="usd",
        cpe=ep(2026, 12, 1), period_start=ep(2025, 12, 1),
        cancel_at_period_end=True, cancel_at=ep(2026, 12, 1), canceled_at=ep(2026, 7, 26)),
    {"tier": "pro", "status": "active", "plan_interval": "annual",
     "current_period_end": "2026-12-01T00:00:00+00:00"},
    datetime(2026, 7, 26, tzinfo=timezone.utc))))

# 5b — access ENDED: the same cancellation, months later
SAMPLES.append(("billing_cancellation", be.spec_cancellation(
    sub(status="canceled", lookup_key="pro_annual", unit_amount=82800, currency="usd",
        cpe=ep(2026, 7, 26), period_start=ep(2025, 7, 26),
        canceled_at=ep(2026, 7, 20), ended_at=ep(2026, 7, 26)),
    {"tier": "free", "status": "canceled", "plan_interval": None, "current_period_end": None},
    datetime(2026, 7, 26, tzinfo=timezone.utc))))

# 6 — trial ending T-2 (yen, zero-decimal currency)
SAMPLES.append(("trial_ending", be.spec_trial_ending(
    tier="insider", interval="monthly",
    period_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
    amount=9800, currency="jpy",
    now=datetime(2026, 7, 30, tzinfo=timezone.utc))))

index = []
for slug, spec in SAMPLES:
    subject, html, text = be._render(spec)
    (OUT / f"{slug}.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        f'<title>{subject}</title>{html}', encoding="utf-8")
    (OUT / f"{slug}.txt").write_text(f"SUBJECT: {subject}\n\n{text}", encoding="utf-8")
    index.append((slug, subject, spec.eyebrow, spec.preheader_en))
    print(f"== {slug}\n   subject : {subject}\n   eyebrow : {spec.eyebrow}\n"
          f"   preheader: {spec.preheader_en}")

print(f"\nwrote {len(index)} samples to {OUT}")
