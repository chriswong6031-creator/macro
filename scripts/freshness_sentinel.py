"""External freshness sentinel — the dead-man switch that lives OUTSIDE GitHub.

Masterplan W1 (research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md,
acceptance gate §0.1). The 2026-08-06 outage left the boards frozen for six days
because every alarm lived inside GitHub Actions — the thing that was failing. A red
run in a channel nobody watches is indistinguishable from silence; this sentinel
makes silence impossible by checking the LIVE estate from the VPS that serves it
(app/deploy/macro-sentinel.timer, every 30 minutes), on infrastructure that fails
independently of GitHub.

What it checks (the user-visible truth, not the pipeline's own claims):
  * page bake stamps — HTTP ``Last-Modified`` of the live us_stocks / china /
    intelligence_hub pages. The nightly re-bakes them every day (max observed gap
    over 60 days: 23.2h), so a stamp older than 26h means the render→merge→
    VPS-pull chain is dead somewhere.
  * the board's own delay disclosure — us_stocks renders ``… prices as of
    YYYY-MM-DD`` ONLY when the engine itself knows the board lags current prices
    (templates/dashboard.html.j2 ``_su.staleness.delayed``; absent on a healthy
    bake, weekends included). This is the check the bake stamp cannot make: the
    Jul-31→Aug-6 outage re-baked the page every single day while the board froze,
    so Last-Modified stayed green throughout. A page-wide "as of" scrape cannot
    make it either — the page carries a dozen per-panel as-of dates on their own
    cadences (options ceilings, rotation tooltips) that stay fresh while the
    board freezes, which is why this anchors on the ONE string the delayed board
    emits and breaches when that self-reported lag exceeds its budget.
    china.html emits the same disclosure from the same shape of engine input —
    templates/china.html.j2 ``board_staleness.delayed``, computed by
    scripts/build_china_library.compute_board_staleness against the A-share
    session calendar in lib/cn_calendar.py. It is deliberately placed OUTSIDE
    that template's macro/stocks mode split, because china.html renders no
    setups board and a disclosure nested in the stocks-only half would leave
    THIS surface silent during the very freeze it announces. Its budget is 12
    days rather than 4 — see the SURFACES comment; mainland Golden Week and
    Spring Festival are legitimately ~10 sessionless calendar days.
  * R2 publish time — ``Last-Modified`` of ``massive_stock_day/_manifest.json``
    on the public R2 base, the same anchor scripts/audit_r2.py + daily.yml
    already budget at 26h (the manifest is put unconditionally on every
    successful full publish, no-delta days included).

Verdict discipline (borrowed from scripts/audit_r2.py): a definitive server answer
(HTTP 200 with an over-budget stamp) is a BREACH and alerts immediately; a network
error or non-200 is INDETERMINATE and only escalates to a "sentinel is blind"
alert after BLIND_AFTER consecutive passes. Blindness can never masquerade as
recovery: a surface already in breach that stops answering STAYS in the breach
set, and the recovery notice is sent only when every breached surface has read
definitively fresh. Breach alerts repeat every REALERT_HOURS while the condition
persists — immediately only when a NEW surface joins (set churn or shrink rides
the window, so a flapping fetch cannot page every pass) — and alerts are
dispatched BEFORE the state files are written, so a full disk cannot silence the
alarm it should be raising.

Outputs:
  * operator alert via, in order of attempt: Telegram (TELEGRAM_BOT_TOKEN +
    TELEGRAM_CHAT_ID), Discord webhook (DISCORD_WEBHOOK_URL or
    DISCORD_WEBHOOK_WATCHLIST), and email through app.mailer (MAIL_SMTP_* from
    /etc/macro-api.env; recipient MAIL_SENTINEL_TO falling back to
    MAIL_SUPPORT_TO). Any one succeeding counts as delivered; all three failing
    is logged loudly and the run exits non-zero either way.
  * machine-readable staleness state at <public-dir>/live/staleness.json, written
    by atomic rename (the live-plane convention) and served read-only at
    /live/staleness.json — the input a later wave's on-site staleness banner
    reads. ``ok`` there is the honest tri-state fold: false when anything is in
    active breach OR the sentinel has been blind past threshold — "I can't tell"
    must never render as "fresh".
  * private counters (consecutive failures, last-alert stamps) at
    <state-dir>/state.json so the 30-minute cadence can hold the re-alert window.

Stdlib-only ON PURPOSE (urllib, json, re): the sentinel must not depend on the
venv contents, the engine tree, or lib.config being healthy — it is the observer
of last resort, so its import closure is as small as honesty allows (app.mailer,
itself stdlib-only, is imported lazily and failure-guarded).

Falsifier law (masterplan B5): >2 false-positive pages in a month means the
budgets are wrong — fix the budgets, never mute the sentinel.

Usage:
  python -m scripts.freshness_sentinel                  # one sentinel pass
  python -m scripts.freshness_sentinel --dry-run        # report only, no state/alert
  python -m scripts.freshness_sentinel --now 2026-08-08T05:00:00+00:00
      # clock override — the §0.1 acceptance drill: point the clock one simulated
      # day past the last bake and watch the alert fire without killing anything.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Cloudflare's WAF 403s python-default User-Agents on the public r2.dev host
# (scripts/audit_r2.py, same constant class).
UA = "macro-freshness-sentinel/1.0"

DEFAULT_BASE = "https://www.mastermind-x.com"
# Same public data-plane base templates/data_base.js and scripts/audit_r2.py pin.
DEFAULT_R2_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
DEFAULT_PUBLIC_DIR = "/var/lib/macro-live/public"
DEFAULT_STATE_DIR = "/var/lib/macro-sentinel"

#: Consecutive INDETERMINATE passes (per surface) before the sentinel reports its
#: own blindness. 6 passes at the 30-minute cadence ≈ 3 hours without a
#: definitive read.
BLIND_AFTER = 6
#: While a breach persists, repeat the alert this often (hours) instead of every pass.
REALERT_HOURS = 6.0
#: Nightly bake budget (masterplan W1: 26h). daily.yml fires 22:30 UTC seven days
#: a week; max observed inter-bake gap on these pages over 60 days is 23.2h.
BAKE_BUDGET_HOURS = 26.0
#: Page body cap. The biggest board page is ~1 MB; hitting the cap means the read
#: was truncated and the verdict would be built on a partial body → INDETERMINATE.
BODY_CAP = 2_000_000

# Per-surface freshness budgets. ``delay_budget_days`` applies to the board's own
# delayed-board disclosure (see module docstring): the marker only renders when
# the ENGINE says prices lag, so its presence is already trading-day aware —
# weekends and holidays never print it. 4 calendar days ≈ two missed sessions
# past a long weekend; the Jul-31 freeze would have paged on Aug 4 while the
# bake stamp stayed green the whole time. None = the page has no board stamp to
# anchor on.
#
# china is 12, not 4, and the difference is a calendar fact rather than a weaker
# standard. The mainland exchanges close for Spring Festival and National Day
# Golden Week, each of which runs ~9-10 CALENDAR days with no session at all — a
# 4-day budget would page every October and every February on a board that is
# behaving exactly as it should. 12 clears the longest legitimate closure with
# two days to spare. It is also the budget that absorbs the deliberate
# imprecision in lib/cn_calendar.py: that holiday table is minimal ON PURPOSE
# (a missing entry reads as a false "stale", never a silently-wrong "fresh"), so
# the china board may legitimately print its disclosure part-way through a long
# holiday. Printing it is honest — the prices really are 10 days old — and the
# budget is what decides whether that is a holiday or an outage.
# Consequence to accept: a China board that dies the day Golden Week starts is
# caught ~12 days later, not ~4. The bake-stamp check still covers that surface
# at 26h; only the board-lag check waits.
SURFACES: list[dict] = [
    {
        "id": "us_stocks",
        "kind": "page",
        "path": "/us_stocks.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": 4,
    },
    {
        "id": "china",
        "kind": "page",
        "path": "/china.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": 12,
    },
    {
        "id": "hub",
        "kind": "page",
        "path": "/intelligence_hub.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": None,
    },
    {
        "id": "r2_massive_stock_day",
        "kind": "r2",
        "path": "/massive_stock_day/_manifest.json",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": None,
    },
]

# The English renderings of the delayed-board marker. us_stocks
# (templates/dashboard.html.j2): "dots reflect prices as of D" and "Board is
# delayed — prices are as of D". china (templates/china.html.j2): "BOARD
# DELAYED — prices as of D". Both pages ship the l-en span in every bake
# regardless of the reader's language, so matching the English form is
# sufficient; the zh twin carries no ISO date in this phrase.
_DELAY_RE = re.compile(r"prices (?:are )?as of (20\d{2}-\d{2}-\d{2})", re.IGNORECASE)


@dataclass
class FetchResult:
    """One HTTP observation of a surface. ``error`` set ⇒ nothing else is trusted."""

    status: int | None = None
    last_modified: datetime | None = None
    body: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# Fetching (real transport — tests inject FetchResults instead)
# --------------------------------------------------------------------------- #
def fetch(url: str, *, want_body: bool, timeout: float = 20.0) -> FetchResult:
    """GET (pages, for the delay-marker parse) or HEAD (R2 manifest) one surface.

    Any network-layer failure — and a body that hits BODY_CAP, which would make
    every downstream parse a guess — lands in ``error``; the caller maps it to
    INDETERMINATE, never to a breach.
    """
    req = urllib.request.Request(
        url, method="GET" if want_body else "HEAD", headers={"User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            lm_raw = resp.headers.get("Last-Modified")
            lm = None
            if lm_raw:
                try:
                    lm = parsedate_to_datetime(lm_raw)
                    if lm.tzinfo is None:
                        lm = lm.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    lm = None
            body = None
            if want_body:
                raw = resp.read(BODY_CAP + 1)
                if len(raw) > BODY_CAP:
                    return FetchResult(
                        status=resp.status,
                        error=f"body exceeded {BODY_CAP} byte cap — truncated read",
                    )
                body = raw.decode("utf-8", errors="replace")
            return FetchResult(status=resp.status, last_modified=lm, body=body)
    except urllib.error.HTTPError as exc:
        return FetchResult(status=exc.code, error=f"HTTP {exc.code} {exc.reason}")
    except Exception as exc:  # noqa: BLE001 — DNS/timeout/TLS all become INDETERMINATE
        return FetchResult(error=f"{type(exc).__name__}: {exc}")


def board_delay_stamp(body: str) -> str | None:
    """The board's self-reported price-through date, or None when not delayed.

    Oldest match on purpose (they should agree — both render from the same
    ``_su.staleness.price_through``): if a second marker family ever appears,
    the oldest is the honest one. A page-wide max over every "as of" string is
    exactly wrong here — see the module docstring.
    """
    dates = _DELAY_RE.findall(body or "")
    return min(dates) if dates else None


# --------------------------------------------------------------------------- #
# Pure evaluation core
# --------------------------------------------------------------------------- #
def check_surface(surface: dict, fr: FetchResult, now: datetime) -> dict:
    """One surface → {id, status ∈ ok|stale|indeterminate, ages, detail}."""
    out: dict = {
        "id": surface["id"],
        "kind": surface["kind"],
        "status": "ok",
        "bake_budget_hours": surface["bake_budget_hours"],
        "delay_budget_days": surface["delay_budget_days"],
        "bake_stamp": None,
        "bake_age_hours": None,
        "board_delayed": False,
        "board_price_through": None,
        "board_delay_days": None,
        "detail": "",
    }
    if fr.error or fr.status != 200:
        out["status"] = "indeterminate"
        out["detail"] = fr.error or f"HTTP {fr.status}"
        return out

    problems: list[str] = []

    if fr.last_modified is None:
        # A 200 with no parseable Last-Modified is a serving-config regression —
        # the sentinel cannot do its job. Indeterminate (not a staleness
        # verdict), so it escalates through the blindness counter rather than
        # paging as an outage.
        out["status"] = "indeterminate"
        out["detail"] = "no Last-Modified header on a 200 response"
        return out

    bake_age_h = (now - fr.last_modified).total_seconds() / 3600.0
    out["bake_stamp"] = fr.last_modified.isoformat()
    out["bake_age_hours"] = round(bake_age_h, 1)
    if bake_age_h > surface["bake_budget_hours"]:
        problems.append(
            f"bake stamp {bake_age_h:.1f}h old (budget {surface['bake_budget_hours']:.0f}h)"
        )

    if surface["delay_budget_days"] is not None and fr.body is not None:
        stamp = board_delay_stamp(fr.body)
        if stamp is not None:
            out["board_delayed"] = True
            out["board_price_through"] = stamp
            try:
                stamp_dt = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                delay_d = (now - stamp_dt).total_seconds() / 86400.0
                out["board_delay_days"] = round(delay_d, 1)
                if delay_d > surface["delay_budget_days"]:
                    msg = (
                        f"board reports itself delayed — prices as of {stamp},"
                        f" {delay_d:.1f}d old (budget {surface['delay_budget_days']}d)"
                    )
                    if bake_age_h <= surface["bake_budget_hours"]:
                        # The re-stamp trap: the page kept re-baking while the
                        # board froze — the failure mode Last-Modified alone
                        # cannot see (Jul-31→Aug-6 re-baked every day).
                        msg += "; page re-bakes are landing, board data is not"
                    problems.append(msg)
            except ValueError:
                problems.append(f"unparseable board price-through date {stamp!r}")

    if problems:
        out["status"] = "stale"
        out["detail"] = "; ".join(problems)
    return out


def evaluate(results: dict[str, FetchResult], now: datetime,
             surfaces: list[dict] | None = None) -> dict:
    """All surfaces → this pass's report. ``ok`` here is the single-pass
    staleness verdict only; run() folds active-breach and blindness into the
    SERVED ok before publishing."""
    surfaces = SURFACES if surfaces is None else surfaces
    checked = {s["id"]: check_surface(s, results[s["id"]], now) for s in surfaces}
    stale = sorted(sid for sid, c in checked.items() if c["status"] == "stale")
    indeterminate = sorted(
        sid for sid, c in checked.items() if c["status"] == "indeterminate"
    )
    return {
        "generated_at": now.isoformat(),
        "ok": not stale,
        "stale_surfaces": stale,
        "indeterminate_surfaces": indeterminate,
        "surfaces": checked,
    }


def decide_alerts(report: dict, state: dict, now: datetime) -> tuple[list[str], dict]:
    """Report + prior counters → (alert messages to send now, next counters).

    Three alert classes:
      * BREACH — definitive staleness. First detection alerts immediately; a NEW
        surface joining the breach re-alerts immediately; otherwise the alert
        repeats every REALERT_HOURS. A breached surface that turns INDETERMINATE
        stays in the breach set (sticky) — blindness must never read as
        recovery, and a flapping fetch must not churn the set into an alert
        storm.
      * BLIND — a surface has been indeterminate BLIND_AFTER consecutive passes;
        same re-alert window.
      * RECOVERED — sent once, when every breached surface has read definitively
        fresh (status ok — not merely "stopped answering").
    """
    state = dict(state or {})
    blind_counts = dict(state.get("blind_counts") or {})
    alerts: list[str] = []

    # -- blindness counters -------------------------------------------------
    for sid, c in report["surfaces"].items():
        if c["status"] == "indeterminate":
            blind_counts[sid] = int(blind_counts.get(sid, 0)) + 1
        else:
            blind_counts.pop(sid, None)
    blind_now = sorted(s for s, n in blind_counts.items() if n >= BLIND_AFTER)

    def _window_open(last_iso: str | None) -> bool:
        if not last_iso:
            return True
        try:
            last = datetime.fromisoformat(last_iso)
        except ValueError:
            return True
        return (now - last).total_seconds() / 3600.0 >= REALERT_HOURS

    # -- breach (sticky through blindness) -----------------------------------
    prev = set(filter(None, (state.get("breach_key") or "").split(",")))
    stale = set(report["stale_surfaces"])
    indet = set(report["indeterminate_surfaces"])
    effective = stale | (prev & indet)

    if effective:
        new_surfaces = effective - prev
        if new_surfaces or _window_open(state.get("breach_alerted_at")):
            lines = [
                "STALE LIVE ESTATE — dead-man sentinel breach "
                f"({len(effective)} surface(s)):"
            ]
            for sid in sorted(effective):
                c = report["surfaces"].get(sid)
                if c is None:
                    continue
                note = c["detail"]
                if c["status"] == "indeterminate":
                    note = f"in breach, no definitive read this pass ({note})"
                lines.append(f"  • {sid}: {note}")
            lines.append(
                "Nightly render→merge→pull chain is not delivering. This check"
                " runs on the VPS and repeats every"
                f" {REALERT_HOURS:.0f}h until the estate is fresh."
            )
            alerts.append("\n".join(lines))
            state["breach_alerted_at"] = now.isoformat()
        state["breach_key"] = ",".join(sorted(effective))
    else:
        # Empty ONLY when every previously-breached surface read a definitive
        # non-stale verdict this pass — sticky membership above guarantees a
        # blind pass cannot land here.
        if prev and state.get("breach_alerted_at"):
            alerts.append(
                "RECOVERED — live estate fresh again (previously stale: "
                f"{','.join(sorted(prev))})."
            )
        state["breach_key"] = ""
        state.pop("breach_alerted_at", None)

    # -- blindness -----------------------------------------------------------
    blind_key = ",".join(blind_now)
    prev_blind_key = state.get("blind_key") or ""
    if blind_key:
        if blind_key != prev_blind_key or _window_open(state.get("blind_alerted_at")):
            details = "; ".join(
                f"{sid}: {report['surfaces'][sid]['detail']}"
                for sid in blind_now
                if sid in report["surfaces"]
            )
            alerts.append(
                "SENTINEL BLIND — no definitive read on "
                f"{blind_key} for {BLIND_AFTER}+ consecutive passes (~"
                f"{BLIND_AFTER * 0.5:.0f}h). Last errors: {details}. The estate may"
                " be down or unreachable; treat as an outage until a pass succeeds."
            )
            state["blind_alerted_at"] = now.isoformat()
        state["blind_key"] = blind_key
    else:
        if prev_blind_key and state.get("blind_alerted_at"):
            alerts.append(
                f"RECOVERED — sentinel can see {prev_blind_key} again."
            )
        state["blind_key"] = ""
        state.pop("blind_alerted_at", None)

    state["blind_counts"] = blind_counts
    state["last_run_at"] = now.isoformat()
    return alerts, state


# --------------------------------------------------------------------------- #
# Alert transports (all best-effort; ANY success counts as delivered)
# --------------------------------------------------------------------------- #
def _post_json(url: str, payload: dict, timeout: float = 20.0) -> bool:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception as exc:  # noqa: BLE001 — transport failure is a fact to report, not a crash
        print(f"sentinel: transport POST failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return False


def send_telegram(msg: str) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not (token and chat):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": msg, "disable_web_page_preview": True},
    )


def send_discord(msg: str) -> bool:
    url = (
        os.environ.get("DISCORD_WEBHOOK_URL")
        or os.environ.get("DISCORD_WEBHOOK_WATCHLIST")
        or ""
    ).strip()
    if not url:
        return False
    return _post_json(url, {"content": msg[:1990]})


def send_email(msg: str, now: datetime) -> bool:
    """Operator email through the estate's one send path (app.mailer, stdlib-only).

    Lazy, failure-guarded import: the sentinel must survive a broken app tree.
    idem_key = (message digest, REALERT_HOURS bucket): a crash-loop resending the
    SAME alert in one window collapses to a single email via the ledger, while a
    different alert in the same window (breach then recovery) still goes out.
    """
    to_addr = (
        os.environ.get("MAIL_SENTINEL_TO") or os.environ.get("MAIL_SUPPORT_TO") or ""
    ).strip()
    if not to_addr:
        return False
    try:
        from app import mailer  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"sentinel: app.mailer unavailable ({type(exc).__name__})", file=sys.stderr)
        return False
    import hashlib  # noqa: PLC0415 — stdlib, kept with its one caller

    bucket = int(now.timestamp()) // int(REALERT_HOURS * 3600)
    digest = hashlib.sha256(msg.encode()).hexdigest()[:12]
    status = mailer.send(
        template="freshness_sentinel",
        cls="transactional",
        to_email=to_addr,
        subject="Mastermind freshness sentinel alert",
        html="",
        text=msg,
        idem_key=f"freshness-sentinel:{bucket}:{digest}",
    )
    return status in ("sent", "duplicate")


def notify_operator(msg: str, now: datetime,
                    transports: list | None = None) -> list[str]:
    """Fan the alert across every configured transport; return who delivered."""
    transports = transports if transports is not None else [
        ("telegram", lambda m: send_telegram(m)),
        ("discord", lambda m: send_discord(m)),
        ("email", lambda m: send_email(m, now)),
    ]
    delivered = [name for name, fn in transports if fn(msg)]
    return delivered


# --------------------------------------------------------------------------- #
# State I/O
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, payload: dict) -> None:
    """tmp + rename in the target dir — the live-plane publish convention, so a
    reader (Caddy, the future banner fetch) never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_state(state_dir: Path) -> dict:
    p = state_dir / "state.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run(now: datetime, base: str, r2_base: str, public_dir: Path, state_dir: Path,
        dry_run: bool = False, fetcher=fetch) -> int:
    results: dict[str, FetchResult] = {}
    for s in SURFACES:
        root = r2_base if s["kind"] == "r2" else base
        results[s["id"]] = fetcher(
            root.rstrip("/") + s["path"], want_body=s["delay_budget_days"] is not None
        )

    report = evaluate(results, now)
    for sid, c in sorted(report["surfaces"].items()):
        print(
            f"{sid}: {c['status']}"
            f" | bake {c['bake_age_hours'] if c['bake_age_hours'] is not None else '?'}h"
            f" | board {'delayed@' + c['board_price_through'] if c['board_delayed'] else 'current'}"
            + (f" | {c['detail']}" if c["detail"] else "")
        )

    if dry_run:
        print("dry-run: no state written, no alert sent")
        return 0 if report["ok"] else 1

    alerts, new_state = decide_alerts(report, load_state(state_dir), now)

    # ALERTS FIRST, state files second: a full disk or a permissions break on
    # /var/lib must never silence the alarm it should be raising.
    delivered_any = True
    for msg in alerts:
        delivered = notify_operator(msg, now)
        print(f"sentinel alert ({', '.join(delivered) or 'NO TRANSPORT DELIVERED'}):\n{msg}")
        if not delivered:
            delivered_any = False
    if alerts and not delivered_any:
        print(
            "sentinel: ALERT UNDELIVERED — configure TELEGRAM_BOT_TOKEN/"
            "TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL, or MAIL_SENTINEL_TO"
            " (+ MAIL_SMTP_*)",
            file=sys.stderr,
        )

    # The SERVED verdict is the honest tri-state fold: active breach holds
    # (sticky through blindness) and threshold blindness reads as not-ok — the
    # banner must never render "I can't tell" as "fresh".
    active_breach = sorted(filter(None, (new_state.get("breach_key") or "").split(",")))
    blind_now = sorted(
        s for s, n in (new_state.get("blind_counts") or {}).items() if n >= BLIND_AFTER
    )
    report["active_breach"] = active_breach
    report["blind_surfaces"] = blind_now
    report["ok"] = not active_breach and not blind_now
    report["alerting"] = {
        "breach_alerted_at": new_state.get("breach_alerted_at"),
        "blind_alerted_at": new_state.get("blind_alerted_at"),
    }
    for target, payload in (
        (public_dir / "live" / "staleness.json", report),
        (state_dir / "state.json", new_state),
    ):
        try:
            _atomic_write_json(target, payload)
        except OSError as exc:
            # Next pass re-derives counters from scratch at worst (re-alert
            # rather than silence — the right failure direction).
            print(f"sentinel: could not write {target} ({exc})", file=sys.stderr)

    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dead-man freshness sentinel (masterplan W1)")
    ap.add_argument("--now", default=None,
                    help="ISO clock override — the §0.1 simulated-dead-nightly drill")
    ap.add_argument("--base", default=os.environ.get("SENTINEL_BASE", DEFAULT_BASE))
    ap.add_argument("--r2-base", default=os.environ.get("SENTINEL_R2_BASE", DEFAULT_R2_BASE))
    ap.add_argument("--public-dir",
                    default=os.environ.get("SENTINEL_PUBLIC_DIR", DEFAULT_PUBLIC_DIR))
    ap.add_argument("--state-dir",
                    default=os.environ.get("SENTINEL_STATE_DIR", DEFAULT_STATE_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.now:
        now = datetime.fromisoformat(args.now)
        # Naive stamps are UTC BY CONTRACT here (the repo-wide #2463 convention),
        # not local time. Without this, `--now 2026-08-08T05:00:00` from the
        # runbook silently means 05:00 in whatever zone the operator's shell is
        # in — an hours-wide shift in the very drill that is supposed to prove
        # the budgets, and it would read as a budget bug rather than a clock one.
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    return run(
        now=now,
        base=args.base,
        r2_base=args.r2_base,
        public_dir=Path(args.public_dir),
        state_dir=Path(args.state_dir),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
