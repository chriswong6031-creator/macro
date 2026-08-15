"""Commercial-path alerting ledger — GATE-4 / WS-4.

The money path had no human-watched alarms (research/MASTERMIND_LAUNCH_GATES.md
GATE-4). Data freshness is already covered by scripts/freshness_sentinel.py; this
module is the commercial sibling: emit points in the API process append fail-soft
JSONL events under MACRO_API_STATE_DIR, and the 30-minute sentinel pass evaluates
them and pages through the EXISTING Telegram / Discord / email transport.

No new observability vendor. Never raises — a broken ledger must not take down
checkout, webhooks, auth, or the brain.

Event kinds (emit):
  webhook.ok / webhook.error
  checkout.ok / checkout.fail
  auth.502
  llm.spend
  quota.fail_open

Alert kinds (evaluate) — one per GATE-4 pass condition:
  webhook_silence   — no successful webhook after a live checkout, or N-hour silence
                      once the money path is armed
  webhook_errors    — error count / rate in the window
  checkout_fail     — hosted Checkout create failures
  auth_502          — require_user 502 spike (Supabase degradation)
  llm_spend         — daily brain spend above the defense-in-depth ceiling
  quota_fail_open   — the existing ::error:: brain_gateway fail-open line
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "commercial_path.event.v1"
ALERT_KINDS = (
    "webhook_silence",
    "webhook_errors",
    "checkout_fail",
    "auth_502",
    "llm_spend",
    "quota_fail_open",
)
INJECT_KINDS = ALERT_KINDS


def _utc(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def state_dir(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("MACRO_API_STATE_DIR", "/var/lib/macro-api")) / "commercial_path"


def events_path(day: datetime, root: Path | None = None) -> Path:
    return state_dir(root) / "events" / f"{_utc(day).strftime('%Y-%m-%d')}.jsonl"


def state_path(root: Path | None = None) -> Path:
    return state_dir(root) / "state.json"


@dataclass(frozen=True)
class Thresholds:
    webhook_silence_hours: float = 12.0
    webhook_followup_minutes: float = 30.0
    webhook_error_window_minutes: float = 60.0
    webhook_error_min_count: int = 3
    webhook_error_rate: float = 0.5
    checkout_fail_window_minutes: float = 30.0
    checkout_fail_min_count: int = 2
    auth_502_window_minutes: float = 10.0
    auth_502_min_count: int = 8
    llm_daily_usd: float = 25.0
    realert_hours: float = 6.0

    @classmethod
    def from_env(cls) -> "Thresholds":
        def _f(name: str, default: float) -> float:
            raw = (os.environ.get(name) or "").strip()
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        def _i(name: str, default: int) -> int:
            return int(_f(name, float(default)))

        return cls(
            webhook_silence_hours=_f("COMMERCIAL_WEBHOOK_SILENCE_HOURS", 12.0),
            webhook_followup_minutes=_f("COMMERCIAL_WEBHOOK_FOLLOWUP_MIN", 30.0),
            webhook_error_window_minutes=_f("COMMERCIAL_WEBHOOK_ERROR_WINDOW_MIN", 60.0),
            webhook_error_min_count=_i("COMMERCIAL_WEBHOOK_ERROR_MIN", 3),
            webhook_error_rate=_f("COMMERCIAL_WEBHOOK_ERROR_RATE", 0.5),
            checkout_fail_window_minutes=_f("COMMERCIAL_CHECKOUT_FAIL_WINDOW_MIN", 30.0),
            checkout_fail_min_count=_i("COMMERCIAL_CHECKOUT_FAIL_MIN", 2),
            auth_502_window_minutes=_f("COMMERCIAL_AUTH_502_WINDOW_MIN", 10.0),
            auth_502_min_count=_i("COMMERCIAL_AUTH_502_MIN", 8),
            llm_daily_usd=_f("COMMERCIAL_LLM_DAILY_USD", 25.0),
            realert_hours=_f("COMMERCIAL_REALERT_HOURS", 6.0),
        )


@dataclass(frozen=True)
class Alert:
    kind: str
    title: str
    body: str
    severity: str = "crit"
    evidence: dict[str, Any] = field(default_factory=dict)

    def message(self) -> str:
        return f"COMMERCIAL PATH — {self.title}\n{self.body}"


def emit(kind: str, *, now: datetime | None = None, root: Path | None = None,
         **fields: Any) -> bool:
    """Append one event. Never raises. Returns True on a durable write."""
    try:
        ts = _utc(now)
        row = {
            "schema": SCHEMA,
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": str(kind),
        }
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                row[key] = value
            else:
                row[key] = str(value)
        path = events_path(ts, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except Exception:  # noqa: BLE001 — fail-soft: alerting must never break the money path
        return False


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
    except OSError:
        return []
    return out


def load_events(*, now: datetime | None = None, root: Path | None = None,
                lookback_hours: float = 48.0) -> list[dict]:
    """Load day-sharded events covering ``lookback_hours`` ending at ``now``."""
    now = _utc(now)
    start = now - timedelta(hours=lookback_hours)
    days = []
    cursor = start.date()
    end = now.date()
    while cursor <= end:
        days.append(cursor)
        cursor = cursor + timedelta(days=1)
    rows: list[dict] = []
    for day in days:
        day_dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        rows.extend(_read_jsonl(events_path(day_dt, root)))
    kept: list[dict] = []
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if ts is None or ts < start or ts > now + timedelta(seconds=2):
            continue
        kept.append(row)
    kept.sort(key=lambda r: str(r.get("ts") or ""))
    return kept


def load_state(root: Path | None = None) -> dict:
    path = state_path(root)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def save_state(state: dict, root: Path | None = None) -> bool:
    path = state_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001
        return False


def _in_window(events: Iterable[dict], kind: str, now: datetime,
               minutes: float) -> list[dict]:
    start = now - timedelta(minutes=minutes)
    out = []
    for row in events:
        if row.get("kind") != kind:
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is not None and ts >= start:
            out.append(row)
    return out


def _last(events: Iterable[dict], kind: str) -> dict | None:
    last = None
    for row in events:
        if row.get("kind") == kind:
            last = row
    return last


def _usd(row: dict) -> float:
    try:
        return float(row.get("usd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def evaluate(events: list[dict], now: datetime | None = None,
             thresholds: Thresholds | None = None) -> list[Alert]:
    """Return every GATE-4 condition that is currently true. Pure."""
    now = _utc(now)
    th = thresholds or Thresholds()
    alerts: list[Alert] = []

    checkout_ok = [r for r in events if r.get("kind") == "checkout.ok"]
    webhook_ok = [r for r in events if r.get("kind") == "webhook.ok"]
    last_checkout = _last(events, "checkout.ok")
    last_webhook = _last(events, "webhook.ok")
    last_checkout_ts = _parse_ts((last_checkout or {}).get("ts"))
    last_webhook_ts = _parse_ts((last_webhook or {}).get("ts"))
    armed = bool(checkout_ok or webhook_ok)

    silence_reasons: list[str] = []
    if last_checkout_ts is not None:
        followup = last_checkout_ts + timedelta(minutes=th.webhook_followup_minutes)
        if now >= followup and (last_webhook_ts is None or last_webhook_ts < last_checkout_ts):
            age_min = (now - last_checkout_ts).total_seconds() / 60.0
            silence_reasons.append(
                f"hosted Checkout created {age_min:.0f}m ago with no webhook.ok after it "
                f"(follow-up budget {th.webhook_followup_minutes:.0f}m). "
                f"Stripe is not confirming the sale."
            )
    if armed and (last_webhook_ts is None or
                  (now - last_webhook_ts) >= timedelta(hours=th.webhook_silence_hours)):
        if last_webhook_ts is None:
            silence_reasons.append(
                f"money path is armed (checkout or prior webhook) but no webhook.ok "
                f"has landed in the lookback. Silence budget is {th.webhook_silence_hours:.0f}h."
            )
        else:
            age_h = (now - last_webhook_ts).total_seconds() / 3600.0
            silence_reasons.append(
                f"last webhook.ok was {age_h:.1f}h ago "
                f"(silence budget {th.webhook_silence_hours:.0f}h)."
            )
    # Dedup the two silence shapes when they describe the same gap.
    if silence_reasons:
        alerts.append(Alert(
            kind="webhook_silence",
            title="Stripe webhook silence",
            body=" ".join(dict.fromkeys(silence_reasons))
                 + " Customers may have paid while entitlement never landed.",
            evidence={
                "last_checkout_ts": (last_checkout or {}).get("ts"),
                "last_webhook_ts": (last_webhook or {}).get("ts"),
                "armed": armed,
            },
        ))

    err = _in_window(events, "webhook.error", now, th.webhook_error_window_minutes)
    ok = _in_window(events, "webhook.ok", now, th.webhook_error_window_minutes)
    total = len(err) + len(ok)
    rate = (len(err) / total) if total else 0.0
    if len(err) >= th.webhook_error_min_count or (
            total >= th.webhook_error_min_count and rate >= th.webhook_error_rate):
        last_reason = (err[-1].get("reason") if err else "unknown")
        alerts.append(Alert(
            kind="webhook_errors",
            title="Stripe webhook errors",
            body=(
                f"{len(err)} webhook error(s) in the last {th.webhook_error_window_minutes:.0f}m "
                f"({rate:.0%} of {total} attempts; min count {th.webhook_error_min_count}, "
                f"rate floor {th.webhook_error_rate:.0%}). Last reason: {last_reason}. "
                f"Signature rejects, invalid payloads, or handler crashes — "
                f"entitlements are not converging."
            ),
            evidence={"errors": len(err), "ok": len(ok), "rate": rate,
                      "last_reason": last_reason},
        ))

    fails = _in_window(events, "checkout.fail", now, th.checkout_fail_window_minutes)
    if len(fails) >= th.checkout_fail_min_count:
        last_reason = fails[-1].get("reason") or "unknown"
        alerts.append(Alert(
            kind="checkout_fail",
            title="Checkout creation failing",
            body=(
                f"{len(fails)} hosted Checkout create(s) failed in the last "
                f"{th.checkout_fail_window_minutes:.0f}m "
                f"(threshold {th.checkout_fail_min_count}). "
                f"Customers cannot start a paid subscription. Last error: {last_reason}."
            ),
            evidence={"failures": len(fails), "last_reason": last_reason},
        ))

    spikes = _in_window(events, "auth.502", now, th.auth_502_window_minutes)
    if len(spikes) >= th.auth_502_min_count:
        last_reason = spikes[-1].get("reason") or "unknown"
        alerts.append(Alert(
            kind="auth_502",
            title="require_user 502 spike",
            body=(
                f"{len(spikes)} Supabase auth 502(s) in the last "
                f"{th.auth_502_window_minutes:.0f}m "
                f"(threshold {th.auth_502_min_count}). "
                f"Signed-in product routes are failing. Last upstream: {last_reason}."
            ),
            evidence={"count": len(spikes), "last_reason": last_reason},
        ))

    day_key = now.strftime("%Y-%m-%d")
    spend_rows = [
        r for r in events
        if r.get("kind") == "llm.spend" and str(r.get("ts") or "").startswith(day_key)
    ]
    spend = sum(_usd(r) for r in spend_rows)
    if spend >= th.llm_daily_usd:
        alerts.append(Alert(
            kind="llm_spend",
            title="LLM daily spend above threshold",
            body=(
                f"Brain gateway spend today is ${spend:.2f} "
                f"(ceiling ${th.llm_daily_usd:.2f}). "
                f"Defense-in-depth behind the per-user quota ledger — "
                f"a runaway loop or a broken cap will hit this before the bill does."
            ),
            evidence={"usd": round(spend, 4), "rows": len(spend_rows)},
        ))

    fail_opens = [r for r in events if r.get("kind") == "quota.fail_open"]
    if fail_opens:
        last = fail_opens[-1]
        alerts.append(Alert(
            kind="quota_fail_open",
            title="brain_gateway quota fail-open",
            body=(
                f"The quota ledger failed open ({last.get('reason') or 'unknown'}). "
                f"This is the existing ::error::brain_gateway fail-open line — "
                f"usage is uncapped until the state dir is writable. "
                f"{len(fail_opens)} event(s) in the lookback."
            ),
            evidence={"count": len(fail_opens), "reason": last.get("reason")},
        ))

    return alerts


def decide_alerts(active: list[Alert], state: dict, now: datetime | None = None,
                  thresholds: Thresholds | None = None) -> tuple[list[Alert], list[str], dict]:
    """Apply the re-alert window. Returns (to_send, recoveries, new_state)."""
    now = _utc(now)
    th = thresholds or Thresholds()
    last = dict(state.get("last_alert") or {})
    active_kinds = {a.kind for a in active}
    to_send: list[Alert] = []
    recoveries: list[str] = []

    for alert in active:
        prev = _parse_ts(last.get(alert.kind))
        if prev is None or (now - prev) >= timedelta(hours=th.realert_hours):
            to_send.append(alert)
            last[alert.kind] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    previously = set(state.get("active") or [])
    for kind in sorted(previously - active_kinds):
        recoveries.append(f"RECOVERED — commercial path {kind} cleared.")
        last.pop(kind, None)

    new_state = dict(state)
    new_state["last_alert"] = last
    new_state["active"] = sorted(active_kinds)
    new_state["last_run_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return to_send, recoveries, new_state


def inject(kind: str, *, now: datetime | None = None, root: Path | None = None,
           thresholds: Thresholds | None = None) -> list[dict]:
    """Write a synthetic episode that MUST trip ``kind``. Returns the rows written."""
    if kind not in INJECT_KINDS:
        raise ValueError(f"unknown inject kind {kind!r}; expected one of {INJECT_KINDS}")
    now = _utc(now)
    th = thresholds or Thresholds()
    written: list[dict] = []

    def _emit(event_kind: str, when: datetime, **fields: Any) -> None:
        emit(event_kind, now=when, root=root, injected=True, **fields)
        written.append({"kind": event_kind, "ts": when.strftime("%Y-%m-%dT%H:%M:%SZ"), **fields})

    if kind == "webhook_silence":
        _emit("checkout.ok", now - timedelta(hours=th.webhook_silence_hours, minutes=15),
              session_id="cs_inject_silence")
    elif kind == "webhook_errors":
        n = max(th.webhook_error_min_count, 3)
        for i in range(n):
            _emit("webhook.error", now - timedelta(minutes=n - i),
                  reason="invalid_signature")
    elif kind == "checkout_fail":
        n = max(th.checkout_fail_min_count, 2)
        for i in range(n):
            _emit("checkout.fail", now - timedelta(minutes=n - i),
                  reason="StripeError", tier="pro")
    elif kind == "auth_502":
        n = max(th.auth_502_min_count, 8)
        for i in range(n):
            _emit("auth.502", now - timedelta(minutes=min(n - i, th.auth_502_window_minutes - 1)),
                  reason="URLError")
    elif kind == "llm_spend":
        _emit("llm.spend", now - timedelta(minutes=5),
              usd=round(th.llm_daily_usd + 5.0, 2), lane="pro", tokens=200000)
    elif kind == "quota_fail_open":
        _emit("quota.fail_open", now - timedelta(seconds=30),
              reason="dir_unavailable")
    return written
