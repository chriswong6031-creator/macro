"""app/billing_emails.py — billing + lifecycle email content (SEE W3, masterplan §4 W3).

Five transactional messages, all composed here and delivered through the ONE send path
(``app.mailer.send``):

  ``billing_purchase``        new subscription — trial started, or a straight first charge
  ``billing_upgrade``         tier went up (or the cadence moved monthly -> annual)
  ``billing_payment_failed``  a renewal charge was declined
  ``billing_cancellation``    the subscription ended
  ``trial_ending``            behaviour-triggered T-2 reminder (the sweeper, not a drip)

Design
------
* **The webhook is the single trigger.** ``app/billing.py::_handle_event`` calls
  :func:`on_event` AFTER the entitlement upsert — the DB write is the source of truth and
  email is a side effect that must never block or break it. The call site wraps this
  module, and :func:`on_event` wraps itself, so a composition bug can never 5xx the
  webhook (Stripe would then retry the same event forever).

* **Purchase fires on ``customer.subscription.created``, not
  ``checkout.session.completed``.** The estate has TWO buy lanes: hosted Checkout and the
  Elements sheet (``/api/billing/subscribe/complete``, which calls
  ``stripe.Subscription.create`` directly). Only the hosted lane produces a
  ``checkout.session.completed``; BOTH produce exactly one
  ``customer.subscription.created``. Keying the receipt off ``created`` therefore covers
  both lanes exactly once, and keying it off ``checkout.session.completed`` would have
  left every Elements buyer with no receipt at all. Handling both would double-send,
  because the idempotency key is per EVENT id and the two events have different ids.
  (docs/ops/stripe-setup.md already recorded the matching rule: send from the webhook
  only, never the pre-webhook ``/subscribe/complete`` fast path.)

* **Idempotency (SEE-R3).** ``idem_key = f"stripe:{event_id}:{template}"`` for webhook
  sends and ``f"trial_ending:{user_id}:{period_end_date}"`` for the sweeper (re-armable
  per period, never twice for the same period). ``mailer.send`` is ledger-first, so a
  replayed event returns ``'duplicate'`` without touching SMTP. This has to be its OWN
  key: ``billing._record_event`` only writes the ``stripe_events`` row AFTER a successful
  handle, so a crash between the send and that write would otherwise re-send.

* **Every number is real.** Amounts, currencies, dates and intervals are read off the
  live Stripe objects the handler already has; plan display names and the tier ordering
  come from ``config/plans.yml``. Nothing about money or plans is hardcoded here — the
  catalog is the source and prices change.

* **Class: transactional.** Receipts, dunning and cancellations are information the
  reader is owed, so they are never suppressed by a marketing opt-out and never carry an
  unsubscribe link (PIN §6.7).

Content follows ``mockups/support_email/PIN.md`` §7 (the binding per-template skeletons).
The visual base is whatever ``app.mailer.render_email`` currently is — W2 swaps the W1
functional base for the pinned one, and the only thing that has to change here is
:func:`_render`.
"""
from __future__ import annotations

import calendar
import json
import logging
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app import billing, mailer
from lib.tiers import normalize_tier

log = logging.getLogger("macro.billing_emails")

# --------------------------------------------------------------------------- #
# Links
#
# PIN §7 pins the billing CTA at the www host; app/billing.py's MM_SITE_BASE is the apex
# (its Checkout return_url). Keep them separate rather than reusing the wrong one, and
# let the operator override with one env var if the public host ever moves.
# --------------------------------------------------------------------------- #
_DEFAULT_SITE_BASE = "https://www.mastermind-x.com"


def _site_base() -> str:
    return (os.environ.get("MAIL_SITE_BASE") or _DEFAULT_SITE_BASE).strip().rstrip("/")


def portal_url() -> str:
    """Plain URL that lands a signed-in reader in the Stripe billing portal.

    Email cannot run JS, so the CTA is an ordinary link; ``templates/plans.html.j2``
    reads ``?billing=portal`` and calls the authed ``GET /api/billing/portal`` on arrival.
    """
    return f"{_site_base()}/plans.html?billing=portal"


def plans_url() -> str:
    return f"{_site_base()}/plans.html"


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
# Stripe amounts are minor units of their currency EXCEPT for these, where the amount is
# already the major unit (a ¥1200 charge arrives as 1200, not 120000).
_ZERO_DECIMAL = frozenset({
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg",
    "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
})
_SYMBOL = {
    "usd": "US$", "eur": "€", "gbp": "£", "jpy": "¥", "cny": "CN¥", "hkd": "HK$",
    "aud": "A$", "cad": "CA$", "nzd": "NZ$", "sgd": "S$", "twd": "NT$", "krw": "₩",
}
_ZH_CURRENCY = {
    "usd": "美元", "eur": "欧元", "gbp": "英镑", "jpy": "日元", "cny": "元",
    "hkd": "港元", "aud": "澳元", "cad": "加元", "nzd": "新西兰元", "sgd": "新元",
    "twd": "新台币", "krw": "韩元", "chf": "瑞士法郎",
}


def _amount_str(minor: int, currency: str) -> str:
    """Bare number, correctly scaled for the currency ('12.00', '1,200')."""
    cur = (currency or "").lower()
    if cur in _ZERO_DECIMAL:
        return f"{int(minor):,}"
    return f"{minor / 100:,.2f}"


def money_en(minor: int | None, currency: str | None) -> str:
    """'US$12.00' · '€12.00' · '¥1,200' · '12.00 SEK' for anything unmapped."""
    if minor is None:
        return ""
    cur = (currency or "").lower()
    num = _amount_str(minor, cur)
    sym = _SYMBOL.get(cur)
    if sym:
        return f"{sym}{num}"
    return f"{num} {cur.upper()}" if cur else num


def money_zh(minor: int | None, currency: str | None) -> str:
    """'12.00 美元' · '1,200 日元' · '12.00 SEK' for anything unmapped."""
    if minor is None:
        return ""
    cur = (currency or "").lower()
    num = _amount_str(minor, cur)
    name = _ZH_CURRENCY.get(cur)
    if name:
        return f"{num} {name}"
    return f"{num} {cur.upper()}" if cur else num


# --------------------------------------------------------------------------- #
# Dates
#
# Stripe epochs are UTC; the reader's local date can differ by a few hours near midnight.
# We print the UTC calendar date because that is the date Stripe itself will show on the
# invoice, and a receipt that disagrees with the card statement is worse than one that is
# a few hours off for one reader.
# --------------------------------------------------------------------------- #
_MONTH_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_NUM_EN = ("zero", "one", "two", "three", "four", "five", "six", "seven",
           "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen")
_NUM_ZH = ("零", "一", "二", "三", "四", "五", "六", "七",
           "八", "九", "十", "十一", "十二", "十三", "十四")


def _num_en(n: int) -> str:
    return _NUM_EN[n] if 0 <= n < len(_NUM_EN) else str(n)


def _num_zh(n: int) -> str:
    return _NUM_ZH[n] if 0 <= n < len(_NUM_ZH) else str(n)


def dt_from_epoch(epoch: Any) -> datetime | None:
    try:
        if epoch in (None, "", 0):
            return None
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def dt_from_iso(value: Any) -> datetime | None:
    """Parse the ISO strings we store in ``user_entitlements.current_period_end``."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def date_en(d: datetime | None) -> str:
    return f"{d.day} {_MONTH_EN[d.month - 1]} {d.year}" if d else ""


def date_zh(d: datetime | None) -> str:
    return f"{d.year} 年 {d.month} 月 {d.day} 日" if d else ""


def range_en(a: datetime | None, b: datetime | None) -> str:
    """'1 Aug – 1 Sep 2026' when the year matches, both years otherwise."""
    if not a or not b:
        return date_en(a) or date_en(b)
    if a.year == b.year:
        return f"{a.day} {_MONTH_EN[a.month - 1]} – {b.day} {_MONTH_EN[b.month - 1]} {b.year}"
    return f"{date_en(a)} – {date_en(b)}"


def range_zh(a: datetime | None, b: datetime | None) -> str:
    """'2026 年 8 月 1 日 – 9 月 1 日' when the year matches, both years otherwise."""
    if not a or not b:
        return date_zh(a) or date_zh(b)
    if a.year == b.year:
        return f"{date_zh(a)} – {b.month} 月 {b.day} 日"
    return f"{date_zh(a)} – {date_zh(b)}"


def add_interval(d: datetime, interval: str | None) -> datetime:
    """One billing period after ``d``. Day-of-month clamps, exactly like Stripe's anchor.

    31 Jan + 1 month -> 28/29 Feb; 29 Feb + 1 year -> 28 Feb. Used only for the "that
    covers" window on a subscription whose NEXT period Stripe has not created yet.
    """
    months = 12 if (interval or "").lower() in ("annual", "year", "yearly") else 1
    y, m = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# --------------------------------------------------------------------------- #
# Catalog (config/plans.yml is the source — never a literal price or plan name)
# --------------------------------------------------------------------------- #
def plan_name(tier: str | None) -> str:
    """Display name for a tier, from the catalog ('essential' -> 'Essential').

    Normalised first: a row written before the rename still carries the old wire value,
    and an unmatched tier would fall through to ``t.title()`` — printing the RETIRED
    product name on a live receipt.
    """
    t = normalize_tier(tier)
    try:
        for prod in billing._catalog().get("products", {}).values():
            if prod.get("tier") == t:
                return str(prod.get("name") or t.title())
    except Exception as exc:  # noqa: BLE001 — a missing catalog must not break a receipt
        log.debug("billing_emails: catalog read failed (%s)", type(exc).__name__)
    return t.title() if t else ""


# TODO(SEE): move these into config/plans.yml as a `name_zh` beside each feature's `name`
# WHEN A FOURTH FEATURE LANDS. At three keys a hand-maintained table is cheaper than a
# schema change and the fallback below (catalog `name`, never the slug) is honest; past
# that the table starts drifting from the catalog it mirrors.
_FEATURE_ZH = {
    "site_full": "整站访问权限",
    "terminal_live_options": "终端实时期权数据",
    "chat_opus": "Opus 模型的 Mastermind 对话",
}


def _feature_label(key: str) -> tuple[str, str] | None:
    """(en, zh) label for an entitlement feature key, or None when we cannot name it.

    EN comes from ``config/plans.yml``'s ``features[].name``. ZH comes from the table
    above, falling back to the catalog NAME — never to the key. A raw slug
    (``terminal_live_options``) is banned from user-facing copy by DESIGN_DOCTRINE, and
    an English slug dropped into a Chinese sentence is worse still, so a feature we
    cannot name in words is OMITTED from the sentence rather than printed as a slug.
    """
    en = ""
    try:
        for f in billing._catalog().get("features", []) or []:
            if f.get("key") == key:
                en = str(f.get("name") or "").strip()
                break
    except Exception:  # noqa: BLE001
        pass
    if not en:
        log.debug("billing_emails: feature %r has no catalog name — omitted from copy", key)
        return None
    return en, _FEATURE_ZH.get(key) or en


def _tier_rank_of(tier: str | None) -> int:
    """Position in ``tier_rank``, or -1 for anything the catalog does not carry.

    Normalised first for the same reason as :func:`plan_name`, and it matters more here:
    an un-normalised pre-rename tier ranks -1, which reads as "not a paid plan" and would
    silently SUPPRESS the receipt / upgrade mail for exactly the grandfathered customers.
    """
    rank = billing._tier_rank()
    t = normalize_tier(tier)
    return rank.index(t) if t in rank else -1


def is_upgrade(prev: dict | None, new: dict | None) -> bool:
    """True when (prev -> new) is a plan UPGRADE worth confirming by email.

    Ordering comes from ``config/plans.yml``'s ``tier_rank`` via ``billing._tier_rank()``,
    so inserting a new tier into the catalog changes this comparison without a code edit.

    A move OFF the free tier is deliberately NOT an upgrade: that is a purchase, and it
    already has its own receipt from ``customer.subscription.created``. Requiring the
    previous tier to be paid also makes an out-of-order webhook (``updated`` landing
    before the row for ``created`` exists) fail closed instead of double-sending.
    """
    prev, new = prev or {}, new or {}
    pr, nr = _tier_rank_of(prev.get("tier")), _tier_rank_of(new.get("tier"))
    if pr <= 0:
        return False
    if nr > pr:
        return True
    if nr == pr:
        pi, ni = prev.get("interval"), new.get("plan_interval") or new.get("interval")
        if pi and ni and pi != ni:
            return billing._INTERVAL_RANK.get(ni, -1) > billing._INTERVAL_RANK.get(pi, -1)
    return False


# --------------------------------------------------------------------------- #
# Stripe object readers (webhook payloads are plain dicts; SDK objects are attrs)
# --------------------------------------------------------------------------- #
def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def sub_price(sub: Any) -> tuple[int | None, str | None]:
    """(unit_amount, currency) off a subscription's first item price."""
    items = billing._sub_items(sub)
    if not items:
        return None, None
    price = _get(items[0], "price")
    if price is None:
        return None, None
    return _get(price, "unit_amount"), _get(price, "currency")


def _pricing(sub: Any) -> tuple[int | None, str | None]:
    """Money for this message, taken ONLY from the live Stripe object.

    There is deliberately no ``config/plans.yml`` fallback. The catalog records its
    amounts in the catalog's OWN currency and nothing tells us the customer is billed in
    it (a multi-currency price, a legacy price, a migrated account). Telling a customer
    charged in euros that they will pay "US$69.00" is a worse failure than telling them
    nothing: every money row is omitted when this returns ``(None, None)``, and the copy
    around it drops the amount rather than guessing.
    """
    return sub_price(sub) if sub is not None else (None, None)


def _interval_words(interval: str | None) -> dict[str, str]:
    annual = (interval or "").lower() in ("annual", "year", "yearly")
    return {
        "cadence_en": "annual" if annual else "monthly",
        "cadence_zh": "按年" if annual else "按月",
        "per_en": "per year" if annual else "per month",
        "per_zh": "每年" if annual else "每月",
        "each_en": "each year" if annual else "each month",
        "each_zh": "按年" if annual else "按月",
    }


# --------------------------------------------------------------------------- #
# The message spec — one dataclass carrying every PIN §7 slot
#
# The W1 base has no eyebrow/preheader slot, so those two travel on the spec unused for
# now; when W2 lands the pinned base from mockups/support_email/email_base.html, _render
# starts feeding them and nothing else in this module changes.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EmailSpec:
    template: str
    eyebrow: str
    subject_en: str
    subject_zh: str
    preheader_en: str
    preheader_zh: str
    headline_en: str
    headline_zh: str
    lede_en: str
    lede_zh: str
    why_en: str
    why_zh: str
    # (key_en, value_en, key_zh, value_zh) — the PIN §6.5 detail slip, in order
    slip: tuple[tuple[str, str, str, str], ...] = ()
    cta_en: str = ""
    cta_zh: str = ""
    cta_url: str = ""
    fine_en: str = ""
    fine_zh: str = ""
    # Idempotency key. Empty => the caller keys on the EVENT id, which is right whenever
    # one event means one message. Builders whose event can legitimately repeat (Stripe
    # emits invoice.payment_failed once per retry attempt, and subscription.updated on
    # every unrelated field change) set a STABLE key on the underlying object instead.
    idem: str = ""
    meta: dict = field(default_factory=dict, compare=False)


def _row(k_en: str, v_en: str, k_zh: str, v_zh: str) -> tuple[str, str, str, str] | None:
    """One slip row, or None when either language has no value.

    Empty scaffolding reads as a bug to the reader — "Price:  per month" with a missing
    amount is worse than a slip with one fewer row — so an incomplete row is dropped
    rather than printed.
    """
    if not str(v_en or "").strip() or not str(v_zh or "").strip():
        return None
    return (k_en, v_en, k_zh, v_zh)


def _slip(*rows: tuple[str, str, str, str] | None) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(r for r in rows if r is not None)


def _render(spec: EmailSpec) -> tuple[str, str, str]:
    """(subject, html, text) for a spec. THE base-swap seam.

    W2 replaces ``mailer.render_email``'s functional base with the pinned
    ``email_base.html``; this function is the only thing that has to follow it.
    """
    blocks: list[dict] = [{"en": spec.lede_en, "zh": spec.lede_zh}]
    if spec.slip:
        blocks.append({
            "kind": "kv",
            "en": [(k, v) for k, v, _, _ in spec.slip],
            "zh": [(k, v) for _, _, k, v in spec.slip],
        })
    if spec.cta_url and spec.cta_en:
        blocks.append({"kind": "button", "en": spec.cta_en, "zh": spec.cta_zh, "url": spec.cta_url})
    if spec.fine_en or spec.fine_zh:
        blocks.append({"en": spec.fine_en, "zh": spec.fine_zh})
    blocks.append({"en": spec.why_en, "zh": spec.why_zh})
    html, text = mailer.render_email(spec.headline_en, spec.headline_zh, blocks)
    return f"{spec.subject_en} · {spec.subject_zh}", html, text


# --------------------------------------------------------------------------- #
# Builders — one per event, each returning a spec or None ("nothing to say")
# --------------------------------------------------------------------------- #
def spec_purchase(sub: Any, ent: dict, event_at: datetime | None) -> EmailSpec | None:
    """PIN §7.1 — trial started, or a straight first charge when there is no trial."""
    tier = billing._sub_tier(sub) or (ent or {}).get("tier")
    if _tier_rank_of(tier) <= 0:
        return None                      # an unrecognised / free subscription earns no receipt
    interval = billing._sub_interval(sub) or (ent or {}).get("plan_interval")
    name = plan_name(tier)
    w = _interval_words(interval)
    amount, currency = _pricing(sub)
    m_en, m_zh = money_en(amount, currency), money_zh(amount, currency)

    trial_end = dt_from_epoch(_get(sub, "trial_end"))
    trial_start = dt_from_epoch(_get(sub, "trial_start")) or event_at
    period_start = dt_from_epoch(_get(sub, "current_period_start")) or trial_start
    period_end = dt_from_epoch(billing._sub_period_end(sub))
    started = event_at or trial_start or period_start

    plan_row = _row("Plan", f"{name} — {w['cadence_en']}", "方案", f"{name} — {w['cadence_zh']}")
    price_row = _row("Price", f"{m_en} {w['per_en']}" if m_en else "",
                     "价格", f"{w['per_zh']} {m_zh}" if m_zh else "")

    if trial_end and (not trial_start or trial_end > trial_start):
        days = 0
        if trial_start:
            days = max(0, round((trial_end - trial_start).total_seconds() / 86400))
        if not days:
            days = billing._tier_trial_days(tier or "")
        covers_end = add_interval(trial_end, interval)
        day_word_en = "day" if days == 1 else "days"
        return EmailSpec(
            template="billing_purchase",
            eyebrow="TRIAL",
            subject_en=f"Your {name} trial has started",
            subject_zh=f"{name} 试用已开始",
            preheader_en=f"Free until {date_en(trial_end)}. Cancel before then and you are not charged.",
            preheader_zh=f"免费至 {date_zh(trial_end)}。在此之前取消，不会扣款。",
            headline_en=f"Your {name} trial has started.",
            headline_zh=f"你的 {name} 试用已开始。",
            lede_en=(f"You have full {name} access for the next {_num_en(days)} {day_word_en}. "
                     f"Nothing is charged until the trial ends — cancel before "
                     f"{date_en(trial_end)} and you pay nothing."),
            lede_zh=(f"接下来{_num_zh(days)}天，你可以使用 {name} 的全部功能。"
                     f"试用结束前不会扣款——在 {date_zh(trial_end)}前取消，你无需支付任何费用。"),
            slip=_slip(
                plan_row,
                price_row,
                _row("Free until", f"{date_en(trial_end)} ({days}-{day_word_en} trial)",
                     "免费至", f"{date_zh(trial_end)}（{days} 天试用）"),
                _row("First charge", f"{date_en(trial_end)} · {m_en}" if m_en else date_en(trial_end),
                     "首次扣款", f"{date_zh(trial_end)} · {m_zh}" if m_zh else date_zh(trial_end)),
                _row("That covers", range_en(trial_end, covers_end),
                     "对应周期", range_zh(trial_end, covers_end)),
            ),
            cta_en="Manage billing", cta_zh="管理账单", cta_url=portal_url(),
            fine_en=(f"Cancel any time before {date_en(trial_end)} and you are not charged. "
                     f"If you do nothing, {name} renews {w['each_en']} until you cancel."),
            fine_zh=(f"{date_zh(trial_end)}前可随时取消，不会产生任何扣费。"
                     f"若不作任何操作，{name} 将{w['each_zh']}自动续订，直到你取消为止。"),
            why_en=f"You received this because you started {_a_en(name)} {name} trial on {date_en(started)}.",
            why_zh=f"你收到这封邮件，是因为你在 {date_zh(started)}开始了 {name} 试用。",
            meta={"tier": tier, "interval": interval, "amount": amount, "currency": currency},
        )

    # No trial: the subscription bills immediately for the period Stripe just opened.
    next_charge = period_end or (add_interval(period_start, interval) if period_start else None)
    return EmailSpec(
        template="billing_purchase",
        eyebrow="RECEIPT",
        subject_en=f"Your {name} plan is active",
        subject_zh=f"{name} 订阅已开通",
        preheader_en=(f"{m_en} {w['per_en']}. Next charge {date_en(next_charge)}." if m_en
                      else f"{name} is active. Next charge {date_en(next_charge)}."),
        preheader_zh=(f"{w['per_zh']} {m_zh}。下次扣款 {date_zh(next_charge)}。" if m_zh
                      else f"{name} 已开通。下次扣款 {date_zh(next_charge)}。"),
        headline_en=f"Your {name} plan is active.",
        headline_zh=f"你的 {name} 订阅已开通。",
        lede_en=(f"You have full {name} access now. The charge below covers the period shown; "
                 f"after that it renews {w['each_en']} until you cancel."),
        lede_zh=(f"你现在可以使用 {name} 的全部功能。以下扣款对应下方所示周期；"
                 f"之后将{w['each_zh']}自动续订，直到你取消为止。"),
        slip=_slip(
            plan_row,
            price_row,
            _row("Started", date_en(period_start), "开始时间", date_zh(period_start)),
            _row("That covers", range_en(period_start, next_charge),
                 "对应周期", range_zh(period_start, next_charge)),
            _row("Next charge", f"{date_en(next_charge)} · {m_en}" if m_en else date_en(next_charge),
                 "下次扣款", f"{date_zh(next_charge)} · {m_zh}" if m_zh else date_zh(next_charge)),
        ),
        cta_en="Manage billing", cta_zh="管理账单", cta_url=portal_url(),
        fine_en="Cancel any time in billing. Access runs to the end of the period you have paid for.",
        fine_zh="你可以随时在账单中心取消。已付费周期结束前，访问权限保持不变。",
        why_en=f"You received this because you started {_a_en(name)} {name} subscription on {date_en(started)}.",
        why_zh=f"你收到这封邮件，是因为你在 {date_zh(started)}开通了 {name} 订阅。",
        meta={"tier": tier, "interval": interval, "amount": amount, "currency": currency},
    )


def proration_charged_now(sub: Any) -> tuple[bool | None, int | None, str | None]:
    """Did the plan switch bill the customer IMMEDIATELY? (verdict, amount, currency).

    ``True`` only on positive evidence: an EXPANDED ``latest_invoice`` on the updated
    subscription that is already paid for a non-zero amount. ``None`` means we cannot
    tell — a webhook payload carries ``latest_invoice`` as a bare id string, which is the
    normal case — and the caller must then use wording that is true either way.

    Why this matters: this deployment runs TWO switch paths with DIFFERENT proration
    settings. ``POST /api/billing/upgrade`` uses ``always_invoice`` (billed on the spot);
    the customer portal is configured ``create_prorations``
    (``scripts/stripe_bootstrap.py::PORTAL_PRORATION_BEHAVIOR``, docs/ops/stripe-setup.md
    §5), where the credit and charge lines land on the NEXT invoice. Both arrive here as
    the same ``customer.subscription.updated`` event, so asserting an immediate charge
    would be a lie for every portal switch.
    """
    inv = _get(sub, "latest_invoice")
    if not isinstance(inv, dict):
        return None, None, None            # bare id (or absent) — no evidence either way
    status = inv.get("status")
    paid = inv.get("amount_paid")
    if status == "paid" and isinstance(paid, int) and paid > 0:
        return True, paid, inv.get("currency")
    if status in ("draft", "open") or paid == 0:
        return False, None, None
    return None, None, None


def spec_upgrade(sub: Any, prev: dict, ent: dict, event_at: datetime | None) -> EmailSpec | None:
    """PIN §7.2 — tier went up, or the cadence moved monthly -> annual."""
    if not is_upgrade(prev, ent):
        return None
    tier = ent.get("tier")
    interval = ent.get("plan_interval") or billing._sub_interval(sub)
    name = plan_name(tier)
    w = _interval_words(interval)
    amount, currency = _pricing(sub)
    m_en, m_zh = money_en(amount, currency), money_zh(amount, currency)
    changed = event_at or datetime.now(timezone.utc)
    next_bill = dt_from_iso(ent.get("current_period_end")) or dt_from_epoch(billing._sub_period_end(sub))

    # What is newly available, named as a capability rather than a tier (PIN §7.2).
    gained = [f for f in (ent.get("features") or []) if f not in set(prev.get("features") or [])]
    labels = [lbl for lbl in (_feature_label(k) for k in gained) if lbl]
    if labels:
        lede_en = "You now have " + _join_en([en for en, _ in labels]) + "."
        lede_zh = "你现在拥有" + _zh_lead("、".join(zh for _, zh in labels)) + "。"
    elif prev.get("interval") and interval and prev["interval"] != interval:
        lede_en = (f"Same plan, new billing cadence — {name} is now billed {w['cadence_en']} "
                   f"instead of {_interval_words(prev['interval'])['cadence_en']}.")
        lede_zh = (f"方案不变，只是结算周期改了——{name} 现在{w['cadence_zh']}结算，"
                   f"而不是{_interval_words(prev['interval'])['cadence_zh']}。")
    else:
        lede_en = f"{name} is active on your account."
        lede_zh = f"{name} 已在你的账户中生效。"

    trialing = (ent.get("status") or _get(sub, "status")) == "trialing"
    charged_now, paid_amount, paid_currency = proration_charged_now(sub)
    if trialing:
        fine_en = ("Nothing was charged for the switch — you are still in your trial. "
                   f"{name} billing starts when the trial ends.")
        fine_zh = f"本次变更未产生扣款——你仍在试用期内。试用结束后才会按 {name} 开始计费。"
    elif charged_now:
        paid_en, paid_zh = money_en(paid_amount, paid_currency), money_zh(paid_amount, paid_currency)
        fine_en = (f"We credited the unused time on your old plan and charged the difference "
                   f"for the rest of this period — {paid_en} today. Your next full bill is "
                   f"{date_en(next_bill)}.")
        fine_zh = (f"我们已把旧方案中尚未使用的时间折算成抵扣，并对本周期剩余时间收取差额"
                   f"——今天扣款 {paid_zh}。下一次完整账单为 {date_zh(next_bill)}。")
    else:
        # Ambiguous or explicitly deferred: say WHAT happens to the money, never WHEN it
        # is collected, because that differs between the in-app lane and the portal.
        fine_en = ("We credit the unused time on your old plan and charge only the difference "
                   "for the rest of this period. The exact adjustment shows up in your "
                   f"billing history; your next full bill is {date_en(next_bill)}.")
        fine_zh = ("我们会把旧方案中尚未使用的时间折算成抵扣，只对本周期剩余时间收取差额。"
                   f"具体金额可在账单记录中查看；下一次完整账单为 {date_zh(next_bill)}。")

    return EmailSpec(
        template="billing_upgrade",
        eyebrow="UPGRADE",
        subject_en=f"You're on {name} now",
        subject_zh=f"你已升级到 {name}",
        preheader_en=f"{name} is active. Your next bill is {date_en(next_bill)}.",
        preheader_zh=f"{name} 已生效。下次账单 {date_zh(next_bill)}。",
        headline_en=f"You're on {name} now.",
        headline_zh=f"你已升级到 {name}。",
        lede_en=lede_en,
        lede_zh=lede_zh,
        slip=_slip(
            _row("Plan", f"{name} — {w['cadence_en']}", "方案", f"{name} — {w['cadence_zh']}"),
            _row("Price", f"{m_en} {w['per_en']}" if m_en else "",
                 "价格", f"{w['per_zh']} {m_zh}" if m_zh else ""),
            _row("Changed on", date_en(changed), "变更日期", date_zh(changed)),
            _row("Next bill", date_en(next_bill), "下次账单", date_zh(next_bill)),
        ),
        cta_en="Manage billing", cta_zh="管理账单", cta_url=portal_url(),
        fine_en=fine_en, fine_zh=fine_zh,
        why_en=f"You received this because you changed your plan on {date_en(changed)}.",
        why_zh=f"你收到这封邮件，是因为你在 {date_zh(changed)}变更了订阅方案。",
        meta={"tier": tier, "interval": interval, "amount": amount, "currency": currency,
              "charged_now": charged_now},
    )


def spec_payment_failed(invoice: Any, prev: dict, ent: dict,
                        event_at: datetime | None) -> EmailSpec | None:
    """PIN §7.3 — a renewal charge was declined. No blame, no urgency theatre.

    ONE email per invoice, on the FIRST attempt only. Stripe's Smart Retries emit
    ``invoice.payment_failed`` again for every retry (each with its own event id, so the
    event-scoped idempotency key cannot collapse them), and a customer whose card is
    dead would otherwise get the identical message four times over a week. The retry
    schedule is already stated in the first message, and the terminal outcome has its own
    email from the cancellation path — so attempts 2..n are silent by design.
    """
    attempt = _get(invoice, "attempt_count")
    if isinstance(attempt, int) and attempt > 1:
        log.info("billing_emails: payment_failed attempt %s — already mailed, staying quiet", attempt)
        return None

    # The tier survives on the PRE-upsert row: our reducer treats `past_due` as
    # unentitled, so by the time this runs the recomputed row already reads 'free'.
    tier = ent.get("tier") if _tier_rank_of(ent.get("tier")) > 0 else prev.get("tier")
    interval = ent.get("plan_interval") or prev.get("interval")
    name = plan_name(tier) if _tier_rank_of(tier) > 0 else ""
    # "Your Pro access" when the plan is known, plain "Your access" when it is not — never
    # "Your your plan access". The ZH form keeps the Latin/Hanzi space the house uses.
    owned_en = f"Your {name} access" if name else "Your access"
    owned_zh = f"{name} 的访问权限" if name else "你的访问权限"
    plan_en, plan_zh = name or "Your plan", name or "你的方案"
    w = _interval_words(interval)

    amount = _get(invoice, "amount_due")
    if amount is None:
        amount = _get(invoice, "total")
    currency = _get(invoice, "currency")
    m_en, m_zh = money_en(amount, currency), money_zh(amount, currency)

    attempted = dt_from_epoch(_get(invoice, "created")) or event_at or datetime.now(timezone.utc)
    retry = dt_from_epoch(_get(invoice, "next_payment_attempt"))

    # Honest access line. `past_due` is unentitled in _entitlement_from_state, so the
    # usual outcome here is that access is ALREADY paused — say so rather than promising
    # a grace window the product does not give.
    still_on = dt_from_iso(ent.get("current_period_end")) if _tier_rank_of(ent.get("tier")) > 0 else None
    if still_on:
        access_en, access_zh = f"On until {date_en(still_on)}", f"保留至 {date_zh(still_on)}"
        pre_en = f"Access stays on until {date_en(still_on)}. Update the card to keep it."
        pre_zh = f"访问权限保留至 {date_zh(still_on)}。更新银行卡即可继续使用。"
        lede_en = (f"{owned_en} stays on until {date_en(still_on)}. "
                   f"Updating the card before then keeps it.")
        lede_zh = (f"{owned_zh}保留至 {date_zh(still_on)}。"
                   f"在此之前更新银行卡即可继续使用。")
    else:
        access_en, access_zh = "Paused until the payment goes through", "已暂停，直到扣款成功"
        pre_en = "Access is paused until the payment goes through. Updating the card turns it back on."
        pre_zh = "访问权限已暂停，直到扣款成功。更新银行卡后会立即恢复。"
        lede_en = (f"{owned_en} is paused until the payment goes through. "
                   f"Updating the card turns it straight back on — nothing else is lost.")
        lede_zh = (f"{owned_zh}已暂停，直到扣款成功。"
                   f"更新银行卡后会立即恢复，其他数据不受影响。")

    # Wording covers the WHOLE retry schedule, not just the next attempt — this is the
    # only payment-failed email the customer gets, so it cannot imply "one more try".
    if retry:
        fine_en = (f"We try the card again on {date_en(retry)}, and a few more times after that "
                   f"if it keeps failing. If none of the attempts go through, the plan is "
                   f"cancelled and you can restart it any time. We will not email again about "
                   f"this payment.")
        fine_zh = (f"我们会在 {date_zh(retry)}再次尝试扣款，若仍未成功还会再试几次。"
                   f"如果都没有成功，订阅将被取消，你随时可以重新订阅。这笔扣款我们不会再发邮件提醒。")
    else:
        fine_en = ("We will not try this card again automatically. Update it in billing to "
                   "restart the plan.")
        fine_zh = "我们不会再自动尝试这张卡。请在账单中心更新银行卡以恢复订阅。"

    # Keyed on the INVOICE, not the event: belt-and-braces behind the attempt_count gate
    # above, so even a Stripe behaviour change that re-fires attempt 1 cannot double-send.
    invoice_id = str(_get(invoice, "id") or "")

    return EmailSpec(
        template="billing_payment_failed",
        eyebrow="PAYMENT",
        subject_en="Your card was declined",
        subject_zh="银行卡扣款失败",
        preheader_en=pre_en,
        preheader_zh=pre_zh,
        headline_en="Your card was declined.",
        headline_zh="银行卡扣款失败。",
        lede_en=lede_en, lede_zh=lede_zh,
        slip=_slip(
            _row("Plan", f"{plan_en} — {w['cadence_en']}" if name else plan_en,
                 "方案", f"{plan_zh} — {w['cadence_zh']}" if name else plan_zh),
            _row("Amount", m_en, "金额", m_zh),
            _row("Attempted on", date_en(attempted), "扣款时间", date_zh(attempted)),
            _row("Access", access_en, "访问权限", access_zh),
        ),
        cta_en="Update card", cta_zh="更新银行卡", cta_url=portal_url(),
        fine_en=fine_en, fine_zh=fine_zh,
        why_en="You received this because a payment on your account did not go through.",
        why_zh="你收到这封邮件，是因为你账户上的一笔扣款没有成功。",
        idem=f"stripe:{invoice_id}:billing_payment_failed" if invoice_id else "",
        meta={"tier": tier, "interval": interval, "amount": amount, "currency": currency},
    )


def spec_cancel_scheduled(sub: Any, ent: dict, event_at: datetime | None) -> EmailSpec | None:
    """PIN §7.4, the REACHABLE form — the customer pressed cancel in the portal.

    The portal is configured ``subscription_cancel.mode = at_period_end``
    (``scripts/stripe_bootstrap.py``), so a user-facing cancellation does NOT emit
    ``customer.subscription.deleted`` at the moment it happens — it emits
    ``customer.subscription.updated`` with ``cancel_at_period_end=true`` and then, weeks
    later, the delete. Without this builder the single most common cancellation in the
    product sends nothing at all until the period ends.

    Keyed on the SUBSCRIPTION plus the end date, not the event: ``updated`` fires for
    every unrelated field change, so repeated updates while the flag stays true collapse
    to one message, while a re-cancel that moves the date legitimately re-arms.
    """
    if not _get(sub, "cancel_at_period_end"):
        return None                      # every other kind of update is not a cancellation

    tier = billing._sub_tier(sub) or ent.get("tier")
    interval = billing._sub_interval(sub) or ent.get("plan_interval")
    name = plan_name(tier)
    full_en = f"full {name} access" if name else "full access"
    full_zh = f"{name} 的全部功能" if name else "全部功能"
    plan_en, plan_zh = name or "Your plan", name or "你的方案"
    w = _interval_words(interval)

    now = event_at or datetime.now(timezone.utc)
    cancelled_at = dt_from_epoch(_get(sub, "canceled_at")) or now
    access_end = (dt_from_epoch(_get(sub, "cancel_at"))
                  or dt_from_epoch(billing._sub_period_end(sub)))
    if access_end is None:
        return None                      # no end date to promise — say nothing rather than guess

    sub_id = str(_get(sub, "id") or "")
    return EmailSpec(
        template="billing_cancellation_scheduled",
        eyebrow="CANCELLATION",
        subject_en="Your plan is cancelled",
        subject_zh="订阅已取消",
        preheader_en=f"You keep full access until {date_en(access_end)}. Nothing more will be charged.",
        preheader_zh=f"在 {date_zh(access_end)}之前仍可正常使用。不会再产生任何扣款。",
        headline_en="Your plan is cancelled.",
        headline_zh="订阅已取消。",
        lede_en=(f"You keep {full_en} until {date_en(access_end)}. "
                 f"Nothing more will be charged."),
        lede_zh=f"在 {date_zh(access_end)}之前，{full_zh}仍可使用。不会再产生任何扣款。",
        slip=_slip(
            _row("Plan", f"{plan_en} — {w['cadence_en']}" if name else plan_en,
                 "方案", f"{plan_zh} — {w['cadence_zh']}" if name else plan_zh),
            _row("Cancelled on", date_en(cancelled_at), "取消日期", date_zh(cancelled_at)),
            _row("Access until", date_en(access_end), "访问权限至", date_zh(access_end)),
        ),
        cta_en="Manage billing", cta_zh="管理账单", cta_url=portal_url(),
        fine_en=(f"Changed your mind? Turn the plan back on in billing any time before "
                 f"{date_en(access_end)} and nothing changes — same plan, no gap, no new charge "
                 f"until the usual date."),
        fine_zh=(f"改变主意了？在 {date_zh(access_end)}之前随时可以在账单中心恢复订阅——"
                 f"方案不变、不中断，也不会提前扣款。"),
        why_en=f"You received this because you cancelled your plan on {date_en(cancelled_at)}.",
        why_zh=f"你收到这封邮件，是因为你在 {date_zh(cancelled_at)}取消了订阅。",
        idem=(f"stripe:{sub_id}:cancel_sched:{access_end.date().isoformat()}" if sub_id else ""),
        meta={"tier": tier, "interval": interval, "access_end": access_end.isoformat()},
    )


def spec_cancellation(sub: Any, ent: dict, event_at: datetime | None) -> EmailSpec | None:
    """PIN §7.4, the FINAL fact — the subscription has ended. One honest exit.

    A different fact from :func:`spec_cancel_scheduled` at a different time: that one
    says "you keep access until X", this one says "access has now ended". Both firing for
    one cancellation is correct — the customer scheduled it weeks ago and this is the
    day it took effect.

    Keyed on the SUBSCRIPTION so a redelivered delete cannot re-send.
    """
    # The deleted subscription object still carries its own price items, so the plan it
    # names is the plan that ended — not whatever the recomputed row now says.
    tier = billing._sub_tier(sub) or ent.get("tier")
    interval = billing._sub_interval(sub) or ent.get("plan_interval")
    name = plan_name(tier)
    owned_en = f"your {name} access" if name else "your access"
    owned_zh = f"{name} 的访问权限" if name else "你的访问权限"
    plan_en, plan_zh = name or "Your plan", name or "你的方案"
    w = _interval_words(interval)

    now = event_at or datetime.now(timezone.utc)
    cancelled_at = dt_from_epoch(_get(sub, "canceled_at")) or now
    access_end = (dt_from_epoch(_get(sub, "ended_at"))
                  or dt_from_epoch(billing._sub_period_end(sub))
                  or now)

    sub_id = str(_get(sub, "id") or "")
    return EmailSpec(
        template="billing_cancellation",
        eyebrow="CANCELLATION",
        subject_en="Your access has ended",
        subject_zh="访问权限已结束",
        preheader_en=f"Access ended {date_en(access_end)}. Nothing more will be charged.",
        preheader_zh=f"访问权限已于 {date_zh(access_end)}结束。不会再产生任何扣款。",
        headline_en="Your access has ended.",
        headline_zh="访问权限已结束。",
        lede_en=(f"{owned_en[0].upper()}{owned_en[1:]} ended on {date_en(access_end)}. "
                 f"Nothing more will be charged."),
        lede_zh=f"{owned_zh}已于 {date_zh(access_end)}结束。不会再产生任何扣款。",
        slip=_slip(
            _row("Plan", f"{plan_en} — {w['cadence_en']}" if name else plan_en,
                 "方案", f"{plan_zh} — {w['cadence_zh']}" if name else plan_zh),
            _row("Cancelled on", date_en(cancelled_at), "取消日期", date_zh(cancelled_at)),
            _row("Access ended", date_en(access_end), "访问权限结束于", date_zh(access_end)),
        ),
        cta_en="Start again", cta_zh="重新订阅", cta_url=plans_url(),
        fine_en=("Your account stays open on the free plan. Saved watchlists and settings are "
                 "kept — subscribe again whenever you want and they are where you left them."),
        fine_zh=("你的账户会保留在免费方案上。已保存的自选股和设置不会被删除——"
                 "随时重新订阅，它们都还在。"),
        why_en=f"You received this because your subscription ended on {date_en(access_end)}.",
        why_zh=f"你收到这封邮件，是因为你的订阅已于 {date_zh(access_end)}结束。",
        idem=f"stripe:{sub_id}:cancel_final" if sub_id else "",
        meta={"tier": tier, "interval": interval},
    )


def spec_trial_ending(*, tier: str | None, interval: str | None, period_end: datetime,
                      amount: int | None, currency: str | None,
                      now: datetime) -> EmailSpec:
    """PIN §7.5 — behaviour-triggered T-2 reminder (trialing AND period_end within 2 days)."""
    name = plan_name(tier)
    w = _interval_words(interval)
    m_en, m_zh = money_en(amount, currency), money_zh(amount, currency)
    covers_end = add_interval(period_end, interval)
    days = max(0, math.ceil((period_end - now).total_seconds() / 86400))

    if days <= 1:
        subj_en, subj_zh = "Your trial ends tomorrow", "试用明天结束"
    else:
        subj_en, subj_zh = f"Your trial ends in {days} days", f"试用还有 {days} 天结束"

    if m_en:
        pre_en = (f"First charge {date_en(period_end)}, {m_en}. "
                  f"Cancel before then and you pay nothing.")
        pre_zh = f"首次扣款 {date_zh(period_end)}，{m_zh}。在此之前取消不用付费。"
        lede_en = (f"On {date_en(period_end)} we charge {m_en} for the next period. "
                   f"Doing nothing means that charge happens — cancel before then and you "
                   f"pay nothing.")
        lede_zh = (f"我们将在 {date_zh(period_end)}扣款 {m_zh}，对应下一个周期。"
                   f"如果不做任何操作，这笔扣款就会发生——在此之前取消，你无需支付任何费用。")
    else:
        # No live price available — say what happens without inventing an amount (m4).
        pre_en = (f"First charge {date_en(period_end)}. "
                  f"Cancel before then and you pay nothing.")
        pre_zh = f"首次扣款 {date_zh(period_end)}。在此之前取消不用付费。"
        lede_en = (f"On {date_en(period_end)} the first charge for the next period is taken. "
                   f"Doing nothing means that charge happens — cancel before then and you "
                   f"pay nothing. The exact amount is on your plan in billing.")
        lede_zh = (f"我们将在 {date_zh(period_end)}进行首次扣款，对应下一个周期。"
                   f"如果不做任何操作，这笔扣款就会发生——在此之前取消，你无需支付任何费用。"
                   f"具体金额可在账单中心查看。")

    return EmailSpec(
        template="trial_ending",
        eyebrow="TRIAL",
        subject_en=subj_en, subject_zh=subj_zh,
        preheader_en=pre_en, preheader_zh=pre_zh,
        headline_en=f"Your {name} trial ends on {date_en(period_end)}.",
        headline_zh=f"你的 {name} 试用将于 {date_zh(period_end)}结束。",
        lede_en=lede_en, lede_zh=lede_zh,
        slip=_slip(
            _row("Plan", f"{name} — {w['cadence_en']}", "方案", f"{name} — {w['cadence_zh']}"),
            _row("First charge", date_en(period_end), "首次扣款", date_zh(period_end)),
            _row("Amount", m_en, "金额", m_zh),
            _row("That covers", range_en(period_end, covers_end),
                 "对应周期", range_zh(period_end, covers_end)),
        ),
        cta_en="Manage billing", cta_zh="管理账单", cta_url=portal_url(),
        fine_en=(f"Cancelling works right up to the moment of the charge. After that, {name} "
                 f"renews {w['each_en']} until you cancel."),
        fine_zh=(f"在扣款发生之前，你都可以取消。之后 {name} 会{w['each_zh']}自动续订，"
                 f"直到你取消为止。"),
        why_en=f"You received this because your {name} trial ends on {date_en(period_end)}.",
        why_zh=f"你收到这封邮件，是因为你的 {name} 试用将于 {date_zh(period_end)}结束。",
        meta={"tier": tier, "interval": interval, "amount": amount, "currency": currency},
    )


def _zh_lead(s: str) -> str:
    """Space a Latin word off the Hanzi before it — the house convention on every surface."""
    return f" {s}" if s[:1].isascii() and s[:1].isalnum() else s


def _a_en(word: str) -> str:
    """'a' / 'an' for a plan name — the catalog owns the names, so this cannot be baked in."""
    return "an" if (word or "")[:1].lower() in "aeiou" else "a"


def _join_en(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


# --------------------------------------------------------------------------- #
# Recipient resolution
# --------------------------------------------------------------------------- #
def _stripe_customer_email(customer_id: str | None) -> str | None:
    if not customer_id:
        return None
    try:
        cust = billing._stripe().Customer.retrieve(customer_id)
    except Exception as exc:  # noqa: BLE001 — no Stripe, no key, deleted customer
        log.debug("billing_emails: customer email lookup failed (%s)", type(exc).__name__)
        return None
    if _get(cust, "deleted"):
        return None
    email = _get(cust, "email")
    return str(email).strip() if email else None


def _supabase_user_email(user_id: str | None) -> str | None:
    """Fall back to the Supabase auth record when Stripe has no address on file."""
    key = billing.SUPABASE_SERVICE_ROLE_KEY
    if not user_id or not key:
        return None
    req = urllib.request.Request(
        f"{billing.SUPABASE_URL}/auth/v1/admin/users/{urllib.parse.quote(str(user_id))}",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            row = json.loads(resp.read() or b"{}")
    except Exception as exc:  # noqa: BLE001
        log.debug("billing_emails: supabase email lookup failed (%s)", type(exc).__name__)
        return None
    email = (row or {}).get("email")
    return str(email).strip() if email else None


def resolve_recipient(obj: Any, customer_id: str | None, user_id: str | None) -> str | None:
    """Best address for this event: the object's own, then Stripe's, then Supabase's."""
    for candidate in (_get(obj, "customer_email"), _get(obj, "receipt_email")):
        if candidate:
            return str(candidate).strip()
    return _stripe_customer_email(customer_id) or _supabase_user_email(user_id)


# --------------------------------------------------------------------------- #
# The webhook hook
# --------------------------------------------------------------------------- #
# Events whose email needs to know what the entitlement looked like BEFORE the
# recompute: an upgrade is a comparison, and a failed payment has already been
# downgraded to free by the time we run.
NEEDS_PRE_SNAPSHOT = frozenset({"customer.subscription.updated", "invoice.payment_failed"})


def _updated_spec(sub: Any, prev: dict, ent: dict, at: datetime | None) -> EmailSpec | None:
    """`customer.subscription.updated` is the busiest event Stripe sends — dispatch it.

    It fires for a plan switch, a cancellation scheduled at period end, a trial
    converting, a card being replaced, and a dozen silent field changes.

    **The UPGRADE is checked first, and the order is load-bearing.** A subscription keeps
    ``cancel_at_period_end`` set after the customer changes their mind and upgrades:
    ``_live_subscription`` selects ``status in ("active", "trialing")``, which includes a
    cancel-flagged sub, so ``POST /api/billing/upgrade`` accepts it and bills the
    proration immediately under ``always_invoice``. Checking cancellation first would
    return the scheduled-cancel spec, whose idem key was already claimed when they
    pressed cancel — the send would come back ``duplicate`` and the customer would be
    charged with no receipt at all. Nothing is lost by this order: the scheduled-cancel
    email went out when they pressed cancel, and a later unrelated update re-derives the
    same key and stays silent.
    """
    if is_upgrade(prev, ent):
        return spec_upgrade(sub, prev, ent, at)
    return spec_cancel_scheduled(sub, ent, at)


# THE dispatch table — read by build_spec, so it can never drift out of use.
#
# `checkout.session.completed` is deliberately ABSENT (see the module docstring):
# `customer.subscription.created` is the one event BOTH buy lanes emit, exactly once, so
# adding checkout.session.completed here would double-send to every hosted-Checkout buyer.
# Anything not in this map is acknowledged by the webhook and sends nothing.
_BUILDERS: dict[str, Any] = {
    "customer.subscription.created": lambda sub, prev, ent, at: spec_purchase(sub, ent, at),
    "customer.subscription.updated": _updated_spec,
    "invoice.payment_failed": lambda inv, prev, ent, at: spec_payment_failed(inv, prev, ent, at),
    "customer.subscription.deleted": lambda sub, prev, ent, at: spec_cancellation(sub, ent, at),
}


def pre_upsert_snapshot(etype: str, user_id: str | None) -> dict | None:
    """Entitlement row as it stands BEFORE the webhook's recompute, when needed.

    Called by ``billing._handle_event`` ahead of the upsert. Returns None for every event
    that does not need it, so the common webhook path costs no extra round trip.
    """
    if etype not in NEEDS_PRE_SNAPSHOT or not user_id:
        return None
    try:
        return billing.read_entitlement(user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing_emails: pre-snapshot failed for %s (%s)", user_id, type(exc).__name__)
        return None


def build_spec(event: dict, *, ent: dict, pre: dict | None) -> EmailSpec | None:
    """The pure part: (event, entitlement state) -> spec, or None when nothing is owed."""
    builder = _BUILDERS.get(str(event.get("type") or ""))
    if builder is None:
        return None
    obj = ((event.get("data") or {}).get("object")) or {}
    return builder(obj, pre or {}, ent or {}, dt_from_epoch(event.get("created")))


@dataclass(frozen=True)
class Outbox:
    """A decided message, ready to send. The hand-off between :func:`prepare` (inside the
    caller's per-user lock) and :func:`deliver` (outside it)."""
    spec: EmailSpec
    idem_key: str
    obj: dict
    user_id: str | None = None
    customer_id: str | None = None


def _prepare(event: dict, *, user_id: str | None, customer_id: str | None,
             ent: dict, pre: dict | None) -> Outbox | None:
    if not billing_mail_enabled():
        log.info("billing_emails: MAIL_BILLING_ENABLED is off — %s not mailed", event.get("type"))
        return None
    spec = build_spec(event, ent=ent, pre=pre)
    if spec is None:
        return None
    # A spec that names its own key does so because its EVENT can legitimately repeat
    # (a dunning retry, an unrelated subscription update); everything else is one event,
    # one message, and keys on the event id.
    idem_key = spec.idem
    if not idem_key:
        event_id = str(event.get("id") or "")
        if not event_id:
            log.warning("billing_emails: %s has no event id — cannot key idempotency, skipping",
                        event.get("type"))
            return None
        idem_key = f"stripe:{event_id}:{spec.template}"
    return Outbox(spec=spec, idem_key=idem_key,
                  obj=((event.get("data") or {}).get("object")) or {},
                  user_id=user_id, customer_id=customer_id)


def prepare(event: dict, *, user_id: str | None = None, customer_id: str | None = None,
            ent: dict | None = None, pre: dict | None = None) -> Outbox | None:
    """DECIDE what this event owes. Cheap and side-effect-free; NEVER raises.

    Runs inside ``billing._handle_event``'s per-user lock, because the upgrade decision
    is a comparison against the pre-upsert entitlement and must not straddle another
    event's write. Everything slow — resolving the address, rendering, SMTP — is
    :func:`deliver`'s job and happens with the lock released.
    """
    try:
        return _prepare(event, user_id=user_id, customer_id=customer_id,
                        ent=ent or {}, pre=pre)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing_emails: %s could not be prepared (%s: %s)",
                    (event or {}).get("type"), type(exc).__name__, exc)
        return None


def deliver(outbox: Outbox | None) -> str | None:
    """SEND a prepared message. NEVER raises (G2/G7).

    Safe outside the per-user lock: ``mailer.send`` is ledger-first on a UNIQUE
    ``idem_key``, so two racing deliveries of the same decision produce one send and one
    ``'duplicate'``. Keeping the SMTP conversation (up to ~21.5s with its retry) plus two
    Supabase round trips out of the critical section matters because a failed renewal
    routinely delivers ``invoice.payment_failed`` and ``customer.subscription.updated``
    together: the second would otherwise wait out the first's entire send while holding
    an anyio threadpool token, and that 40-token limiter is the real concurrency budget
    of an app with ~30 sync routes.
    """
    if outbox is None:
        return None
    try:
        to_email = resolve_recipient(outbox.obj, outbox.customer_id, outbox.user_id)
        if not to_email:
            log.warning("billing_emails: no address for %s (customer=%s user=%s) — skipped",
                        outbox.spec.template, outbox.customer_id, outbox.user_id)
            return None
        subject, html, text = _render(outbox.spec)
        return mailer.send(
            template=outbox.spec.template,
            cls="transactional",       # PIN §6.7 — never suppressed, never an unsubscribe link
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
            idem_key=outbox.idem_key,
            user_id=outbox.user_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("billing_emails: %s could not be delivered (%s: %s)",
                    outbox.spec.template, type(exc).__name__, exc)
        return None


def on_event(event: dict, *, user_id: str | None = None, customer_id: str | None = None,
             ent: dict | None = None, pre: dict | None = None) -> str | None:
    """prepare + deliver in one call. NEVER raises (G2/G7).

    The convenience form for callers with no lock to release — the webhook uses the two
    halves separately so the send lands outside its critical section.
    """
    return deliver(prepare(event, user_id=user_id, customer_id=customer_id,
                           ent=ent, pre=pre))


# --------------------------------------------------------------------------- #
# Trial-ending sweeper (behaviour-triggered lifecycle, NOT a drip)
#
# Cursor-free by construction: it re-derives the whole eligible set from
# user_entitlements every wake and lets email_log's unique idem_key decide what has
# already gone out. A restart mid-sweep therefore costs nothing — the next wake picks up
# exactly where it would have, and every already-sent row returns 'duplicate'.
# --------------------------------------------------------------------------- #
TRIAL_WINDOW_HOURS = 48
_SWEEP_LIMIT = 500


def _sweep_pricing(customer_id: str | None) -> tuple[int | None, str | None]:
    """The live subscription price, or (None, None) when Stripe cannot tell us.

    No catalog fallback, for the reason in :func:`_pricing`: the catalog's currency is
    not evidence about THIS customer's currency. When Stripe is unreachable the reminder
    still goes out — it just states the date and that a charge is coming, and points at
    billing for the amount, instead of asserting a number that might be in the wrong
    currency.
    """
    if not customer_id:
        return None, None
    try:
        sub = billing._live_subscription(customer_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing_emails: sweep sub lookup failed (%s)", type(exc).__name__)
        return None, None
    return sub_price(sub) if sub is not None else (None, None)


def trial_ending_candidates(now: datetime, window_hours: int = TRIAL_WINDOW_HOURS) -> list[dict]:
    """Trialing entitlement rows whose period ends inside the window (never in the past).

    Ordered soonest-first so the LIMIT is deterministic: an unordered cap would let
    PostgREST return an arbitrary 500 every wake, which could starve the same rows
    forever if the window ever held more than that. Soonest-first means the most urgent
    reminders are always the ones that make the cut, and the rest are picked up next wake.
    """
    lo = now.isoformat()
    hi = (now + timedelta(hours=window_hours)).isoformat()
    path = (
        "user_entitlements?status=eq.trialing"
        f"&current_period_end=gte.{urllib.parse.quote(lo, safe='')}"
        f"&current_period_end=lte.{urllib.parse.quote(hi, safe='')}"
        "&select=user_id,stripe_customer_id,tier,plan_interval,current_period_end"
        "&order=current_period_end.asc"
        f"&limit={_SWEEP_LIMIT}"
    )
    return billing._pg("GET", path) or []


def sweep_trial_ending(*, now: datetime | None = None,
                       window_hours: int = TRIAL_WINDOW_HOURS) -> dict:
    """Send the T-2 reminder to every trial ending inside the window. Never raises.

    Returns a small census: ``{"scanned", "sent", "duplicate", "skipped", "failed"}``.
    """
    now = now or datetime.now(timezone.utc)
    out = {"scanned": 0, "sent": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    if not billing_mail_enabled():
        log.info("billing_emails: MAIL_BILLING_ENABLED=0 — trial sweep did nothing")
        return out
    try:
        rows = trial_ending_candidates(now, window_hours)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing_emails: trial sweep query failed (%s)", type(exc).__name__)
        out["failed"] += 1
        return out

    for row in rows:
        out["scanned"] += 1
        try:
            user_id = row.get("user_id")
            period_end = dt_from_iso(row.get("current_period_end"))
            if not user_id or not period_end:
                out["skipped"] += 1
                continue
            customer_id = row.get("stripe_customer_id")
            tier, interval = row.get("tier"), row.get("plan_interval")
            to_email = _stripe_customer_email(customer_id) or _supabase_user_email(user_id)
            if not to_email:
                log.warning("billing_emails: no address for trial_ending user=%s — skipped", user_id)
                out["skipped"] += 1
                continue
            amount, currency = _sweep_pricing(customer_id)
            spec = spec_trial_ending(tier=tier, interval=interval, period_end=period_end,
                                     amount=amount, currency=currency, now=now)
            subject, html, text = _render(spec)
            status = mailer.send(
                template=spec.template, cls="transactional", to_email=to_email,
                subject=subject, html=html, text=text,
                # Re-armable per period: a second trial for the same user later keys on a
                # different period_end date and is allowed to send again.
                idem_key=f"trial_ending:{user_id}:{period_end.date().isoformat()}",
                user_id=user_id,
            )
            if status == "duplicate":
                out["duplicate"] += 1
            elif status in ("sent", "skipped_no_smtp"):
                out["sent"] += 1
            else:
                out["failed"] += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not end the sweep
            log.warning("billing_emails: trial_ending row failed (%s)", type(exc).__name__)
            out["failed"] += 1
    if out["scanned"]:
        log.info("billing_emails: trial sweep %s", out)
    return out


# --------------------------------------------------------------------------- #
# Lifecycle loop (in-process, env-gated, default OFF)
# --------------------------------------------------------------------------- #
LIFECYCLE_INTERVAL_SEC = 6 * 3600     # four wakes a day — the window is 48h wide
_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def lifecycle_enabled() -> bool:
    """Read at CALL time (mailer._env idiom) so a systemd env reload takes effect."""
    return (os.environ.get("MAIL_LIFECYCLE_ENABLED") or "").strip().lower() in _TRUTHY


_BILLING_SWITCH_LOGGED = False


def billing_mail_enabled() -> bool:
    """Master switch for THIS module's sends. Default ON, so receipts work the moment the
    relay lands — the operator should not have to arm two things to get a receipt.

    Exists so a misbehaving billing email can be silenced WITHOUT taking down support
    mail: ``MAIL_BILLING_ENABLED=0`` stops every webhook receipt and the trial reminder,
    while ticket acknowledgements and operator replies (app/support.py, the admin
    console) keep flowing through the same app/mailer.py.

    UNSET means ON; every other value must be on an explicit list. An unrecognised value
    resolves to **OFF**, because this is an emergency kill switch: an operator who types
    ``flase`` at 3am has told us they want the mail stopped, and silently leaving it on
    is the one outcome that cannot be recovered from. The parsed verdict is logged once
    per process so the runbook can prove which way it landed.
    """
    global _BILLING_SWITCH_LOGGED
    raw = (os.environ.get("MAIL_BILLING_ENABLED") or "").strip()
    if not raw:
        enabled, why = True, "unset — ON (default)"
    elif raw.lower() in _TRUTHY:
        enabled, why = True, f"{raw!r} — ON"
    elif raw.lower() in _FALSY:
        enabled, why = False, f"{raw!r} — OFF"
    else:
        enabled, why = False, (f"{raw!r} is not a recognised value — OFF (a kill switch "
                               f"fails closed; use one of {_TRUTHY + _FALSY})")
    if not _BILLING_SWITCH_LOGGED:
        _BILLING_SWITCH_LOGGED = True
        log.info("billing_emails: MAIL_BILLING_ENABLED=%s", why)
    return enabled


def _lifecycle_interval() -> int:
    try:
        return max(60, int(os.environ.get("MAIL_LIFECYCLE_INTERVAL_SEC") or LIFECYCLE_INTERVAL_SEC))
    except ValueError:
        return LIFECYCLE_INTERVAL_SEC


def register_lifecycle(app: Any) -> bool:
    """Attach the sweeper loop to a FastAPI app. No-op unless MAIL_LIFECYCLE_ENABLED.

    Returns whether the loop was armed, so the caller can log it. Deliberately decided at
    mount time: a background task that can appear mid-process is a debugging trap, and
    flipping the env is already a `systemctl restart macro-api` step in the runbook.
    """
    # Log the billing switch here too, so both verdicts land in the startup log.
    billing_mail_enabled()
    if not lifecycle_enabled():
        # Log the OFF state AND the raw value. A silent no-op makes "the operator chose
        # not to arm it" and "the env never reached the droplet" look identical in
        # journalctl, which is exactly what the runbook's verification step has to tell
        # apart — and saying "not set" would be a lie for a value that IS set but is not
        # on the truthy list (``Y``, ``enabled``), where the runbook's `grep -c` reports
        # the secret as delivered (docs/ops/email-support-setup.md §5b).
        log.info("billing_emails: lifecycle sweeper not enabled "
                 "(MAIL_LIFECYCLE_ENABLED=%r; enable with one of %s)",
                 (os.environ.get("MAIL_LIFECYCLE_ENABLED") or "").strip(), _TRUTHY)
        return False
    import asyncio  # noqa: PLC0415 — only needed on the armed path

    interval = _lifecycle_interval()

    async def _loop() -> None:
        # Sleep FIRST: a restart loop must never turn into a send loop, and nothing here
        # is urgent to within six hours.
        while True:
            try:
                await asyncio.sleep(interval)
                # The sweep is blocking I/O (PostgREST + SMTP) — keep it off the event loop.
                await asyncio.to_thread(sweep_trial_ending)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a bad wake must not kill the loop
                log.warning("billing_emails: lifecycle wake failed (%s)", type(exc).__name__)

    async def _start() -> None:
        app.state.mail_lifecycle_task = asyncio.create_task(_loop())
        log.info("billing_emails: lifecycle sweeper armed (every %ds)", interval)

    async def _stop() -> None:
        task = getattr(app.state, "mail_lifecycle_task", None)
        if task is None:
            return
        task.cancel()
        # Await the cancellation so shutdown does not race a half-torn-down task (and so
        # asyncio does not log "Task was destroyed but it is pending" on every restart).
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.debug("billing_emails: lifecycle task ended with %s", type(exc).__name__)

    app.add_event_handler("startup", _start)
    app.add_event_handler("shutdown", _stop)
    return True


# --------------------------------------------------------------------------- #
# CLI — `python -m app.billing_emails --sweep` (manual/operator run)
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Billing + lifecycle email")
    ap.add_argument("--sweep", action="store_true",
                    help="run the trial-ending sweep once and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.sweep:
        print(json.dumps(sweep_trial_ending()))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
