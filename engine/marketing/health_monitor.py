"""engine/marketing/health_monitor.py — per-account health + network tripwire (XG-W6).

**This module is the M1->M2 precondition.** Charter §0 (XG-W4 gate) and §5:
"the per-account health monitor + network tripwire (XG-W6) are a hard
precondition for ANY dial flip above M1 — failures must be able to halt one
account without halting seven." That sentence is the whole design brief, and it
is why there is NO fleet-halt code path in this file. A halt is always a row
keyed by ONE account id. Even the fleet-level network tripwire expresses itself
by writing one halt row per implicated account, so "halt six but not the
seventh" is not a feature that has to be remembered — it is the only shape the
registry can hold.

**Every input is deterministic telemetry. The LLM never scores** (charter §2
amendment 9, extended to every critic including persona/readability/engagement).
Nothing here imports a model client and nothing may; ``tests/
test_marketing_learning.py`` walks this module's AST to keep that true.

The four per-account monitors:

  approval_rate        operator approvals / (approvals + rejections) on the
                       reply desk. A desk the operator keeps rejecting is not
                       producing what it thinks it is.
  rejection_reason_mix which reasons dominate. A mix tilted at a SINGLE reason
                       is a fixable defect; a flat mix is a taste gap. The two
                       need different responses, so the shape is reported, not
                       just the rate.
  engagement_trend     recent median engagement against the trailing baseline,
                       from the labels store (which reads the LIVE metrics
                       poll). A collapse is the observable half of a
                       reach penalty.
  last_nine            the profile-conversion floor's last-nine-post diagnostic
                       (charter §3 item 6): of the last nine posts a visitor
                       would see, how many carry a receipt (chart/media), how
                       many are duplicates of each other, and how many are
                       unmeasured. This is what a profile visitor actually
                       judges, so it is measured on the same window they see.

The network tripwire (fleet level, per-account effect):

  simultaneous_collapse  N+ accounts whose engagement collapsed on the SAME day.
                         One account falling is weather; six falling together is
                         the fleet-linkage signal the charter's risk register
                         names.
  cross_account_corr     rank correlation of daily engagement across account
                         pairs. Independently-run desks should not move in
                         lockstep; lockstep is the shape a shared limiter
                         leaves behind.

Halt semantics: a tripped account halts THAT ACCOUNT ONLY. ``is_halted`` is
consulted by ``scripts/marketing_publisher.py`` (the post rail) and
``engine/marketing/reply_export.py`` (the reply rail). A halt is cleared only by
an operator, never by the monitor itself — a monitor that could un-halt its own
trip would silence itself the moment the underlying condition became
intermittent.

Public API:
    METRICS / TRIPWIRES / DEFAULTS
    halts_path(root) / load_halts(root)
    is_halted(account, *, root=None, halts=None) -> bool
    halt_record(account, *, root=None, halts=None) -> dict | None
    halted_accounts(root=None) -> list[str]
    trip(account, *, reason, evidence, now, root=None, actor=...) -> dict
    clear(account, *, actor, now, note=None, root=None) -> dict
    evaluate_account(account, *, labels, reply_state, decisions, now, cfg) -> dict
    evaluate_fleet(per_account, *, labels, now, cfg) -> dict
    run(*, now, root=None, store=None, cfg=None, apply_halts=True) -> dict
    health_path(root) / load_health(root)
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import statistics
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

HEALTH_SCHEMA = "marketing.account_health/v1"
HALTS_SCHEMA = "marketing.account_halts/v1"

METRICS: tuple[str, ...] = (
    "approval_rate", "rejection_reason_mix", "engagement_trend", "last_nine",
)

TRIPWIRES: tuple[str, ...] = ("simultaneous_collapse", "cross_account_corr")

_DAY_FMT = "%Y-%m-%d"

#: EVERY THRESHOLD IS A CONFIG KEY (charter §8). Overridden by
#: ``config/marketing.yml`` ``learning.health:``.
DEFAULTS: dict[str, Any] = {
    # Windows.
    "recent_days": 7,
    "baseline_days": 28,
    # Below this many observations a metric reports null, never a verdict.
    # A thin window is not a healthy window and it is not an unhealthy one.
    "min_observations": 5,
    # approval_rate below this is a WARN for the account.
    "approval_rate_warn": 0.40,
    # A single rejection reason holding this share of rejections is a
    # concentrated (fixable) defect rather than a diffuse taste gap.
    "reason_concentration_warn": 0.60,
    # Recent median engagement below this multiple of the trailing baseline is
    # a collapse. 0.35 = "lost two thirds", not "a slow week".
    "engagement_collapse_ratio": 0.35,
    # The profile-conversion floor's window (charter §3 item 6).
    "last_nine_window": 9,
    # Of the last nine, at least this many must carry a receipt (chart/media).
    "last_nine_receipt_floor": 3,
    # ...and no more than this many may be unmeasured (no impressions yet).
    "last_nine_unmeasured_ceiling": 6,
    # What an account-level WARN does. "halt" is deliberately NOT the default:
    # a single soft metric should surface to the operator, not silence a desk.
    "account_action": "warn",
    "network_tripwire": {
        # How many accounts must collapse on the same day to trip the wire.
        "min_accounts": 3,
        # Rank correlation at or above this counts as lockstep.
        "corr_threshold": 0.90,
        # ...over at least this many shared days.
        "corr_min_days": 10,
        # How many correlated PAIRS trip the wire.
        "corr_min_pairs": 3,
        # What a fleet trip does. `halt_implicated` writes ONE HALT ROW PER
        # IMPLICATED ACCOUNT — there is no global switch to set, by design.
        "action": "halt_implicated",
    },
}


def _cfg(cfg: dict | None) -> dict:
    raw = (((cfg or {}).get("learning") or {}).get("health") or {})
    out = dict(DEFAULTS)
    for key, val in raw.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val
    return out


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _day(value: object) -> str:
    return str(value or "")[:10]


# ---------------------------------------------------------------------------
# Paths + the halt registry
# ---------------------------------------------------------------------------
def _root_path(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parent.parent.parent
    return Path(root)


def _dir(root: Path | str | None) -> Path:
    return _root_path(root) / "data" / "marketing" / "learning"


def halts_path(root: Path | str | None = None) -> Path:
    """The halt registry.

    TRACKED, deliberately — same posture as
    ``data/marketing/account_overrides.json`` (the desk on/off switch the admin
    already writes). A halt has to be visible to BOTH rails, and those rails run
    on different machines: the publisher runs in the marketing-publish workflow
    and the reply exporter runs on the M1. A committed file reaches both through
    the VPS's three-minute pull; host state reaches neither.
    """
    return _dir(root) / "halts.json"


def health_path(root: Path | str | None = None) -> Path:
    return _dir(root) / "health.json"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — an unreadable registry must not wedge a rail
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hm-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: cannot write %s: %s", path, exc)
        return False


def load_halts(root: Path | str | None = None) -> dict[str, dict]:
    """{account_id: halt_record} for accounts currently halted.

    FAIL-OPEN, and that is a deliberate, argued choice. A halt is a safety
    brake; an unreadable brake could equally be argued to mean "stop
    everything". It does not, because this registry is READ ON EVERY POST and
    a corrupt file would then silence all seven desks with no operator action
    and no way to tell why — the exact fleet-wide outage the per-account design
    exists to prevent. An unreadable registry is announced loudly instead.
    """
    path = halts_path(root)
    if not path.exists():
        return {}
    blob = _read_json(path)
    if not blob:
        print(
            f"::warning title=halt-registry::{path} exists but did not parse — "
            "treating as NO halts; a halted account may be posting. Fix the file.",
            flush=True,
        )
        return {}
    accounts = blob.get("accounts")
    if not isinstance(accounts, dict):
        return {}
    out: dict[str, dict] = {}
    for acc, rec in accounts.items():
        if isinstance(rec, dict) and rec.get("state") == "halted":
            out[str(acc)] = rec
    return out


def halt_record(account: str, *, root: Path | str | None = None,
                halts: dict[str, dict] | None = None) -> dict | None:
    """The live halt row for one account, or None."""
    table = load_halts(root) if halts is None else halts
    return table.get(str(account))


def is_halted(account: str, *, root: Path | str | None = None,
              halts: dict[str, dict] | None = None) -> bool:
    """Is THIS ONE account halted? The question both rails ask.

    Pass ``halts`` (from one ``load_halts`` call) when checking many accounts in
    a loop, so a per-item gate does not re-read the registry per item.
    """
    return halt_record(account, root=root, halts=halts) is not None


def halted_accounts(root: Path | str | None = None) -> list[str]:
    return sorted(load_halts(root))


def _registry(root: Path | str | None) -> dict:
    blob = _read_json(halts_path(root))
    if blob.get("schema") != HALTS_SCHEMA:
        blob = {"schema": HALTS_SCHEMA, "accounts": {}, "log": []}
    blob.setdefault("accounts", {})
    blob.setdefault("log", [])
    return blob


def trip(
    account: str,
    *,
    reason: str,
    evidence: dict | None = None,
    now: datetime,
    root: Path | str | None = None,
    actor: str = "health_monitor",
) -> dict:
    """Halt ONE account. Returns the halt record.

    Idempotent: re-tripping an already-halted account refreshes the evidence and
    appends a log row but does not restart the clock, so an operator reading
    "halted since" gets the truth about how long the desk has been dark.
    """
    acc = str(account).strip()
    if not acc:
        return {"ok": False, "error": "account required"}
    ts = _as_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = _registry(root)
    existing = blob["accounts"].get(acc)
    if isinstance(existing, dict) and existing.get("state") == "halted":
        since = existing.get("since") or ts
    else:
        since = ts
    record = {
        "account": acc,
        "state": "halted",
        "reason": str(reason),
        "evidence": dict(evidence or {}),
        "since": since,
        "updated_at": ts,
        "actor": actor,
        "clearable_by": "operator",
    }
    blob["accounts"][acc] = record
    blob["log"] = (blob.get("log") or [])[-199:] + [
        {"at": ts, "account": acc, "action": "halt", "reason": str(reason), "actor": actor}
    ]
    if not _write_json_atomic(halts_path(root), blob):
        return {"ok": False, "error": "write_failed", "account": acc}
    print(
        f"::warning title=account-halted::{acc} HALTED ({reason}) — that account's "
        "posts and replies are blocked; every other desk keeps running. Clear it "
        "from the admin health panel once the cause is understood.",
        flush=True,
    )
    return {"ok": True, **record}


def clear(
    account: str,
    *,
    actor: str,
    now: datetime,
    note: str | None = None,
    root: Path | str | None = None,
) -> dict:
    """Operator-clears one halt. The ONLY way a halt ends.

    The monitor cannot clear its own trip. An intermittent condition would
    otherwise let the desk flap between halted and live with nobody ever seeing
    it, which is indistinguishable from the monitor not working.
    """
    acc = str(account).strip()
    if not acc:
        return {"ok": False, "error": "account required"}
    if not str(actor or "").strip():
        return {"ok": False, "error": "actor required — a cleared halt needs an owner"}
    ts = _as_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = _registry(root)
    record = blob["accounts"].get(acc)
    if not isinstance(record, dict) or record.get("state") != "halted":
        return {"ok": False, "error": "not_halted", "account": acc}
    record = dict(record)
    record.update({
        "state": "cleared",
        "cleared_at": ts,
        "cleared_by": str(actor),
        "clear_note": (str(note).strip() if note else None),
    })
    blob["accounts"][acc] = record
    blob["log"] = (blob.get("log") or [])[-199:] + [
        {"at": ts, "account": acc, "action": "clear", "actor": str(actor), "note": note}
    ]
    if not _write_json_atomic(halts_path(root), blob):
        return {"ok": False, "error": "write_failed", "account": acc}
    return {"ok": True, "account": acc, "state": "cleared", "cleared_at": ts}


# ---------------------------------------------------------------------------
# Per-account monitors — all deterministic
# ---------------------------------------------------------------------------
def _null(metric: str, reason: str, **extra: Any) -> dict:
    """A metric that could not be measured. PRINTED, never hidden or defaulted.

    A null is not a pass and it is not a fail (house epistemics law:
    endpoint-null is not one half). Anything reading these dicts must branch on
    ``value is None`` rather than comparing a substituted zero.
    """
    return {"metric": metric, "value": None, "verdict": "null", "reason": reason, **extra}


def approval_rate(decisions: dict, *, cfg: dict | None = None) -> dict:
    """Operator approvals over approvals+rejections on the reply desk.

    ``decisions`` = {"approved": n, "rejected": n, "held": n}. Holds are counted
    separately and deliberately excluded from the denominator: a hold is "not
    yet", not "no", and folding it into the rejection side would make a careful
    operator look like a failing desk.
    """
    conf = _cfg(cfg)
    approved = _int(decisions.get("approved"))
    rejected = _int(decisions.get("rejected"))
    n = approved + rejected
    if n < _int(conf["min_observations"], 5):
        return _null("approval_rate", f"n={n} below min_observations="
                     f"{_int(conf['min_observations'], 5)}", n=n)
    rate = round(approved / n, 4)
    warn = float(conf["approval_rate_warn"])
    return {
        "metric": "approval_rate", "value": rate, "n": n,
        "held": _int(decisions.get("held")),
        "threshold": warn,
        "verdict": "warn" if rate < warn else "ok",
    }


def rejection_reason_mix(reasons: Sequence[str], *, cfg: dict | None = None) -> dict:
    """The SHAPE of the rejections, not just their count.

    A mix dominated by one reason is a fixable defect (one gate is
    mis-tuned). A flat mix is a taste gap (the desk is producing the wrong kind
    of thing). Same rejection rate, opposite response, so the concentration is
    reported as its own signal.
    """
    conf = _cfg(cfg)
    counts: dict[str, int] = {}
    for raw in reasons:
        key = str(raw or "unspecified").strip().lower() or "unspecified"
        counts[key] = counts.get(key, 0) + 1
    n = sum(counts.values())
    if n < _int(conf["min_observations"], 5):
        return _null("rejection_reason_mix", f"n={n} below min_observations="
                     f"{_int(conf['min_observations'], 5)}", n=n, mix=counts)
    top, top_n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    share = round(top_n / n, 4)
    warn = float(conf["reason_concentration_warn"])
    return {
        "metric": "rejection_reason_mix", "value": share, "n": n,
        "top_reason": top, "mix": dict(sorted(counts.items())),
        "threshold": warn,
        "verdict": "warn" if share >= warn else "ok",
        "shape": "concentrated" if share >= warn else "diffuse",
    }


def engagement_trend(rows: Sequence[dict], *, now: datetime, cfg: dict | None = None) -> dict:
    """Recent median engagement against the trailing baseline.

    Both halves are MEDIANS, not means: one viral post is exactly the event that
    must not paper over a collapsed week, and a mean lets it.
    """
    conf = _cfg(cfg)
    recent_days = _int(conf["recent_days"], 7)
    baseline_days = _int(conf["baseline_days"], 28)
    ts = _as_utc(now)
    recent_cut = (ts - timedelta(days=recent_days)).strftime(_DAY_FMT)
    base_cut = (ts - timedelta(days=baseline_days)).strftime(_DAY_FMT)

    recent: list[float] = []
    baseline: list[float] = []
    for row in rows:
        day = _day(row.get("as_of"))
        if not day or day < base_cut:
            continue
        obs = row.get("observed") or {}
        eng = float(_int(obs.get("likes")) + _int(obs.get("reposts"))
                    + _int(obs.get("comments")))
        if obs.get("author_replied") is not None:
            eng += 1.0 if obs.get("author_replied") else 0.0
        (recent if day >= recent_cut else baseline).append(eng)

    floor = _int(conf["min_observations"], 5)
    if len(recent) < floor or len(baseline) < floor:
        return _null(
            "engagement_trend",
            f"recent n={len(recent)}, baseline n={len(baseline)} — need {floor} of each",
            n_recent=len(recent), n_baseline=len(baseline),
        )
    base_med = statistics.median(baseline)
    recent_med = statistics.median(recent)
    if base_med <= 0:
        return _null("engagement_trend", "baseline median is zero — a ratio against "
                     "zero engagement is undefined, not infinite",
                     n_recent=len(recent), n_baseline=len(baseline))
    ratio = round(recent_med / base_med, 4)
    collapse = float(conf["engagement_collapse_ratio"])
    return {
        "metric": "engagement_trend", "value": ratio,
        "recent_median": recent_med, "baseline_median": base_med,
        "n_recent": len(recent), "n_baseline": len(baseline),
        "threshold": collapse,
        "verdict": "warn" if ratio < collapse else "ok",
        "collapsed": ratio < collapse,
    }


def last_nine(rows: Sequence[dict], *, cfg: dict | None = None) -> dict:
    """The profile-conversion floor's last-nine-post diagnostic (charter §3.6).

    A visitor who lands on the profile sees a grid of the last nine posts and
    decides in about four seconds. So the diagnostic is measured on exactly that
    window: how many carry a receipt (a chart or media), how many read as the
    same post twice (identical hook family AND format on the same day), and how
    many we have no measurement for at all.
    """
    conf = _cfg(cfg)
    window = _int(conf["last_nine_window"], 9)
    posts = [r for r in rows if r.get("surface") == "post"]
    posts.sort(key=lambda r: (_day(r.get("as_of")), str(r.get("subject_id"))), reverse=True)
    recent = posts[:window]
    if not recent:
        return _null("last_nine", "no posts observed in the labels store", n=0)

    with_receipt = sum(1 for r in recent if (r.get("features") or {}).get("has_media"))
    unmeasured = sum(1 for r in recent if r.get("label") is None)
    seen: set[tuple[str, str, str]] = set()
    dupes = 0
    for r in recent:
        key = (_day(r.get("as_of")), str(r.get("hook_family")), str(r.get("format")))
        if key in seen:
            dupes += 1
        seen.add(key)

    receipt_floor = _int(conf["last_nine_receipt_floor"], 3)
    unmeasured_ceiling = _int(conf["last_nine_unmeasured_ceiling"], 6)
    problems: list[str] = []
    if with_receipt < receipt_floor:
        problems.append(f"only {with_receipt}/{len(recent)} of the visible grid carries "
                        f"a receipt (floor {receipt_floor})")
    if unmeasured > unmeasured_ceiling:
        problems.append(f"{unmeasured}/{len(recent)} posts have no measurement yet "
                        f"(ceiling {unmeasured_ceiling})")
    if dupes:
        problems.append(f"{dupes} near-repeat(s) in the visible grid")
    return {
        "metric": "last_nine", "value": len(recent), "n": len(recent),
        "with_receipt": with_receipt, "unmeasured": unmeasured, "repeats": dupes,
        "thresholds": {"receipt_floor": receipt_floor,
                       "unmeasured_ceiling": unmeasured_ceiling},
        "verdict": "warn" if problems else "ok",
        "problems": problems,
    }


def evaluate_account(
    account: str,
    *,
    labels: Sequence[dict],
    decisions: dict,
    reason_list: Sequence[str],
    now: datetime,
    cfg: dict | None = None,
) -> dict:
    """One account's full health card. Pure — no I/O, no halting."""
    rows = [r for r in labels if str(r.get("account") or "") == str(account)]
    metrics = {
        "approval_rate": approval_rate(decisions, cfg=cfg),
        "rejection_reason_mix": rejection_reason_mix(reason_list, cfg=cfg),
        "engagement_trend": engagement_trend(rows, now=now, cfg=cfg),
        "last_nine": last_nine(rows, cfg=cfg),
    }
    warns = [m for m, v in metrics.items() if v.get("verdict") == "warn"]
    nulls = [m for m, v in metrics.items() if v.get("verdict") == "null"]
    return {
        "account": str(account),
        "n_rows": len(rows),
        "metrics": metrics,
        "warns": warns,
        "nulls": nulls,
        # A null is NOT a pass. An account whose every metric is null is
        # "unmeasured", which is a different operator instruction from "ok".
        "verdict": ("warn" if warns else ("unmeasured" if len(nulls) == len(metrics) else "ok")),
    }


# ---------------------------------------------------------------------------
# The network tripwire — fleet level, per-account effect
# ---------------------------------------------------------------------------
def _daily_engagement(rows: Sequence[dict]) -> dict[str, dict[str, float]]:
    """{account: {day: engagement}} from the labels store."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        acc = str(row.get("account") or "")
        day = _day(row.get("as_of"))
        if not acc or not day:
            continue
        obs = row.get("observed") or {}
        eng = float(_int(obs.get("likes")) + _int(obs.get("reposts"))
                    + _int(obs.get("comments")))
        bucket = out.setdefault(acc, {})
        bucket[day] = bucket.get(day, 0.0) + eng
    return out


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks (ties share the mean rank). Stdlib only, by design."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Spearman rank correlation. None when it is undefined.

    Undefined, not zero: a constant series has no variance to correlate, and
    reporting 0.0 there would read as "independent" when the truth is "we
    cannot tell".
    """
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = _rank(list(a)), _rank(list(b))
    try:
        sa, sb = statistics.pstdev(ra), statistics.pstdev(rb)
    except statistics.StatisticsError:
        return None
    if sa == 0 or sb == 0:
        return None
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / len(ra)
    return round(cov / (sa * sb), 4)


def evaluate_fleet(
    per_account: dict[str, dict],
    *,
    labels: Sequence[dict],
    now: datetime,
    cfg: dict | None = None,
) -> dict:
    """The network tripwire. Names the IMPLICATED accounts; halts nothing itself.

    Returning a list of implicated account ids (rather than a boolean) is the
    load-bearing shape: the caller writes one halt row per implicated account,
    so a fleet-level alarm can never become a fleet-level switch.
    """
    conf = _cfg(cfg)["network_tripwire"]
    min_accounts = _int(conf.get("min_accounts"), 3)
    corr_threshold = float(conf.get("corr_threshold", 0.90))
    corr_min_days = _int(conf.get("corr_min_days"), 10)
    corr_min_pairs = _int(conf.get("corr_min_pairs"), 3)

    # (1) Simultaneous collapse.
    collapsed = sorted(
        acc for acc, card in per_account.items()
        if (card.get("metrics") or {}).get("engagement_trend", {}).get("collapsed")
    )
    collapse_fired = len(collapsed) >= min_accounts

    # (2) Cross-account correlation on daily engagement.
    daily = _daily_engagement(labels)
    pairs: list[dict] = []
    accounts = sorted(daily)
    for i, a in enumerate(accounts):
        for b in accounts[i + 1:]:
            shared = sorted(set(daily[a]) & set(daily[b]))
            if len(shared) < corr_min_days:
                continue
            rho = spearman([daily[a][d] for d in shared], [daily[b][d] for d in shared])
            if rho is not None and rho >= corr_threshold:
                pairs.append({"a": a, "b": b, "rho": rho, "days": len(shared)})
    corr_fired = len(pairs) >= corr_min_pairs
    corr_accounts = sorted({p["a"] for p in pairs} | {p["b"] for p in pairs})

    implicated = sorted(set(collapsed if collapse_fired else []) |
                        set(corr_accounts if corr_fired else []))
    return {
        "tripped": bool(collapse_fired or corr_fired),
        "action": str(conf.get("action") or "halt_implicated"),
        "implicated": implicated,
        "signals": {
            "simultaneous_collapse": {
                "fired": collapse_fired,
                "accounts": collapsed,
                "threshold_accounts": min_accounts,
            },
            "cross_account_corr": {
                "fired": corr_fired,
                "pairs": pairs,
                "threshold_rho": corr_threshold,
                "min_days": corr_min_days,
                "min_pairs": corr_min_pairs,
            },
        },
        "note": (
            "A fleet signal halts each IMPLICATED account individually. There is "
            "no global halt switch in this module by design (charter §5: a failure "
            "must be able to halt one account without halting seven)."
        ),
    }


# ---------------------------------------------------------------------------
# Reply-desk decision inputs (deterministic reads of the host store)
# ---------------------------------------------------------------------------
def reply_decisions(store: Path | str | None = None) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Per-account approval counts and rejection reasons from the reply desk.

    Reads the desk's OWN host-state ledgers. Approvals and rejections are
    ledger transitions; holds are decision rows. Fail-soft: an absent desk
    yields empty dicts, which every metric above reports as a NULL rather than
    a clean bill of health.
    """
    counts: dict[str, dict] = {}
    reasons: dict[str, list[str]] = {}
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        state = _rq.fold_state(store)
        items = state.get("items") or {}
        seen_approved: set[str] = set()
        for row in _rq.read_ledger(store):
            iid = str(row.get("id") or "")
            acc = str((items.get(iid) or {}).get("account") or "")
            if not acc:
                continue
            block = counts.setdefault(acc, {"approved": 0, "rejected": 0, "held": 0})
            to = str(row.get("to") or "")
            if to == "approved" and iid not in seen_approved:
                # An item that goes approved -> queued -> approved was approved
                # ONCE by a human; counting the re-arm again would inflate the
                # rate every time a lease expired.
                seen_approved.add(iid)
                block["approved"] += 1
            elif to == "rejected":
                block["rejected"] += 1
            elif row.get("row") == "decision" and row.get("decision") == "hold":
                block["held"] += 1
        for rej in _rq.read_rejections(store):
            acc = str(rej.get("account") or "")
            if acc:
                reasons.setdefault(acc, []).append(str(rej.get("reason") or "unspecified"))
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor.reply_decisions: reply store unavailable: %s", exc)
    return counts, reasons


# ---------------------------------------------------------------------------
# The nightly run
# ---------------------------------------------------------------------------
def run(
    *,
    now: datetime,
    root: Path | str | None = None,
    store: Path | str | None = None,
    cfg: dict | None = None,
    accounts: Sequence[str] | None = None,
    apply_halts: bool = True,
) -> dict[str, Any]:
    """Evaluate every account, run the tripwire, write health.json, trip halts.

    Runs AFTER ``labels.consolidate`` in the nightly (the health card is a read
    of the labels store, so evaluating first would grade yesterday).
    ``apply_halts=False`` gives the operator a dry-run: identical evaluation,
    no registry writes.
    """
    from engine.marketing import labels as _labels  # noqa: PLC0415

    rows = _labels.load_labels(root)
    counts, reasons = reply_decisions(store)

    ids = list(accounts) if accounts is not None else sorted(
        {str(r.get("account") or "") for r in rows if r.get("account")} | set(counts)
    )
    per_account = {
        acc: evaluate_account(
            acc, labels=rows, decisions=counts.get(acc) or {},
            reason_list=reasons.get(acc) or [], now=now, cfg=cfg,
        )
        for acc in ids
    }
    fleet = evaluate_fleet(per_account, labels=rows, now=now, cfg=cfg)

    tripped: list[str] = []
    conf = _cfg(cfg)
    if apply_halts:
        # Per-account action first. Default is "warn": one soft metric surfaces
        # to the operator rather than silencing a desk.
        if str(conf.get("account_action") or "warn").lower() == "halt":
            for acc, card in per_account.items():
                if card["verdict"] == "warn" and not is_halted(acc, root=root):
                    trip(acc, reason=f"account_health:{','.join(card['warns'])}",
                         evidence=card["metrics"], now=now, root=root)
                    tripped.append(acc)
        # Fleet action: ONE HALT ROW PER IMPLICATED ACCOUNT.
        if fleet["tripped"] and fleet["action"] == "halt_implicated":
            for acc in fleet["implicated"]:
                if not is_halted(acc, root=root):
                    trip(acc, reason="network_tripwire",
                         evidence=fleet["signals"], now=now, root=root)
                    tripped.append(acc)

    report = {
        "schema": HEALTH_SCHEMA,
        "produced_by": "engine/marketing/health_monitor.py",
        "as_of": _as_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": list(METRICS),
        "tripwires": list(TRIPWIRES),
        "accounts": [per_account[a] for a in sorted(per_account)],
        "network_tripwire": fleet,
        "halted": halted_accounts(root),
        "tripped_this_run": sorted(set(tripped)),
        "apply_halts": bool(apply_halts),
        "note": (
            "Operator console artifact. Every input is deterministic telemetry — "
            "no model scores anything here (charter §2 amendment 9). Nothing on "
            "this surface is user-facing."
        ),
    }
    _write_json_atomic(health_path(root), report)
    return report


def load_health(root: Path | str | None = None) -> dict:
    return _read_json(health_path(root))


__all__ = [
    "HEALTH_SCHEMA", "HALTS_SCHEMA", "METRICS", "TRIPWIRES", "DEFAULTS",
    "halts_path", "health_path", "load_halts", "load_health",
    "is_halted", "halt_record", "halted_accounts", "trip", "clear",
    "approval_rate", "rejection_reason_mix", "engagement_trend", "last_nine",
    "evaluate_account", "evaluate_fleet", "spearman", "reply_decisions", "run",
]
