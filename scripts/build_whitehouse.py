"""White House alert desk — monitor → Opus brain → ticker banner + report page.

The hourly sentinel (and the daily build) run this. It:
  1. Pulls the current White House feed items (engine.whitehouse_feed).
  2. For each NEW item, asks the Opus brain (engine.whitehouse_brain) whether it
     is market-significant; an activated item gets a full report appended to the
     append-only ledger data/whitehouse/alerts.jsonl.
  3. Rebuilds, IDEMPOTENTLY (no spurious diffs):
       site/wh_banner.json   — the still-live (non-expired) banners the ticker reads
       site/whitehouse.html  — the report page every banner links into (#wh-<id>)
       site/whdata/<id>.json — the per-alert payload (optional deep link)

Files are only overwritten when their meaningful content changes, so on a quiet
hour the sentinel produces no commit. Degrade-never-raise throughout.

Run:    python -m scripts.build_whitehouse            (normal)
        python -m scripts.build_whitehouse --reeval   (re-run the brain on all
                                                        recent items, ignoring state)

Exit code 10 signals "content changed" (for the sentinel's optional fast-path);
0 = no change / nothing to do.
"""
from __future__ import annotations

import importlib
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import dbase_prefix, inject_text  # noqa: E402
from engine import whitehouse_feed as wf  # noqa: E402
from engine import whitehouse_brain as wb  # noqa: E402

log = logging.getLogger("build_whitehouse")

_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------- #
# ledger (append-only) — every activated alert, newest read last
# --------------------------------------------------------------------------- #
def _ledger_path(root: Path) -> Path:
    return Path(root) / "data" / "whitehouse" / "alerts.jsonl"


def _append_ledger(root: Path, rec: dict) -> None:
    p = _ledger_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("ledger append failed (%s)", e)


def _load_ledger(root: Path) -> list[dict]:
    p = _ledger_path(root)
    out: list[dict] = []
    if not p.exists():
        return out
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict) and d.get("activated"):
                out.append(d)
    except Exception as e:  # noqa: BLE001
        log.warning("ledger read failed (%s)", e)
    # newest-first; a later re-eval of the same id supersedes the earlier row
    by_id: dict[str, dict] = {}
    for d in out:
        by_id[d.get("id")] = d
    rows = list(by_id.values())
    # coalesce to "" so a row with null published AND generated_at can't raise on sort
    rows.sort(key=lambda d: (d.get("published") or d.get("generated_at") or ""), reverse=True)
    return rows


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_dt(s: str | None):
    """Parse an ISO timestamp to a tz-AWARE datetime (assume UTC if the string is
    naive), so comparisons against an aware now() never raise. None on failure."""
    try:
        dt = datetime.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _expires_at(rec: dict) -> datetime | None:
    """Banner lifespan runs from ACTIVATION (generated_at), not the announcement's
    publish time — an item can be new-to-the-brain days after it was published (feed
    lag / sentinel gap / --reeval), and anchoring on published would make a short
    banner born already-expired and never reach the tape. generated_at is frozen in
    the ledger row at evaluation, so expiry stays stable across idempotent re-renders."""
    anchor = _parse_dt(rec.get("generated_at")) or _parse_dt(rec.get("published"))
    days = rec.get("banner_days") or 0
    if anchor is None or not days:
        return None
    try:
        return anchor + timedelta(days=int(days))
    except (TypeError, ValueError):
        return None


def _date_display(s: str | None) -> str:
    dt = _parse_dt(s)
    if dt is None:
        return ""
    return f"{_MON[dt.month - 1]} {dt.day}, {dt.year}"


def _write_if_changed(path: Path, text: str) -> bool:
    """Write only when the content differs — keeps the sentinel from committing an
    identical file every hour. Returns True if it wrote. HTML gets the data-base
    shim injected BEFORE the compare so an unchanged page stays a no-op."""
    try:
        if path.suffix == ".html":
            text = inject_text(text, dbase_prefix(path))
        if path.exists() and path.read_text() == text:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("write %s failed (%s)", path.name, e)
        return False


# --------------------------------------------------------------------------- #
# Treasury Watch lane — same-day TGA refresh + the treasury_watch.v1 panel artifact
# --------------------------------------------------------------------------- #
def _refresh_tga(root: Path) -> None:
    """Best-effort same-day TGA refresh so the hourly sentinel isn't a day behind the DTS.
    Mirrors the daily collect (keyless fiscaldata.treasury.gov); append-only upsert can only
    add rows, never corrupt history. A failure (e.g. no network in CI) leaves the committed
    parquet standing — non-fatal by design."""
    try:
        from collectors.treasury import TreasuryAdapter
        from lib import store as _store
        frames = TreasuryAdapter().fetch()
        for name, df in (frames or {}).items():
            try:
                if df is not None and not df.empty:
                    _store.upsert("treasury", name, df)
            except Exception as e:  # noqa: BLE001
                log.warning("treasury refresh upsert %s failed (%s)", name, e)
    except Exception as e:  # noqa: BLE001
        log.warning("treasury refresh failed (%s) — committed parquet stands", e)


def _load_treasury_watch(site: Path) -> dict | None:
    """Read the committed site/whdata/treasury_watch.json (the panel/bot contract). None on
    absence/parse error — the panel is simply omitted."""
    try:
        p = site / "whdata" / "treasury_watch.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else None
    except Exception as e:  # noqa: BLE001
        log.warning("treasury_watch.json read failed (%s)", e)
        return None


def _write_treasury_watch(root: Path, site: Path, now: datetime) -> None:
    """Assemble + write site/whdata/treasury_watch.json (schema treasury_watch.v1). SENTINEL
    LANE ONLY (never page-only — page-only stays a pure read-only re-render). snapshot() is a
    pure read (parquet + committed JSON, no writes/network); events[] are the treasury rows
    from the committed ledger. Monotonic in as_of (never regress to older data) + idempotent
    (write-if-changed, no wall-clock fields), so a quiet hour is a no-op / no commit."""
    try:
        from engine import treasury_watch as _tw
        snap = _tw.snapshot(root)
    except Exception as e:  # noqa: BLE001 — degrade-never-raise
        log.warning("treasury snapshot failed (%s) — panel artifact skipped", e)
        return
    # events: the treasury rows from the ledger (id 'tw-…' or section 'treasury'), newest first
    try:
        tre: list[dict] = []
        for r in _load_ledger(root):
            rid = str(r.get("id") or "")
            if not (rid.startswith("tw-") or str(r.get("section") or "") == "treasury"):
                continue
            exp = _expires_at(r)
            kind = ("tga_release" if rid.endswith("tga-release")
                    else "tga_build" if rid.endswith("tga-build") else None)
            tre.append({
                "id": rid,
                "published": r.get("published"),
                "kind": kind,
                "banner_title": r.get("banner_title") or r.get("source_title"),
                "banner_title_zh": r.get("banner_title_zh"),
                "tone": r.get("tone", "neutral"),
                "importance": r.get("importance"),
                "live": bool(exp and now < exp),
            })
        tre.sort(key=lambda a: (a.get("published") or ""), reverse=True)
        snap["events"] = tre[:8]
    except Exception as e:  # noqa: BLE001
        log.warning("treasury events assembly failed (%s)", e)
        snap.setdefault("events", [])
    # monotonic guard: an in-process refresh that fails mustn't revert a committed fresher day
    try:
        existing = _load_treasury_watch(site)
        if (existing and existing.get("as_of") and snap.get("as_of")
                and str(existing["as_of"]) > str(snap["as_of"])):
            log.info("treasury_watch: committed as_of %s newer than %s — keeping committed",
                     existing["as_of"], snap["as_of"])
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        if _write_if_changed(site / "whdata" / "treasury_watch.json",
                             json.dumps(snap, separators=(",", ":"), default=str)):
            log.info("treasury_watch.json: as_of=%s events=%d",
                     snap.get("as_of"), len(snap.get("events") or []))
    except Exception as e:  # noqa: BLE001
        log.warning("treasury_watch.json write failed (%s)", e)


# --------------------------------------------------------------------------- #
# artifact builders
# --------------------------------------------------------------------------- #
def _banner_payload(rows: list[dict], now: datetime, max_alerts: int = 6) -> dict:
    """The live (non-expired) banners, slimmed to what the ticker tape renders.
    No wall-clock `generated_at` — the file changes only when an alert is added or
    crosses its expiry, so a quiet hour is a no-op. A single bad row is skipped, never
    fatal. Capped to the top `max_alerts` by importance so an accumulated week of
    alerts can't produce an unreadable tape (the full set stays on whitehouse.html)."""
    alerts = []
    for r in rows:
        try:
            exp = _expires_at(r)
            if exp is None or now >= exp:
                continue
            alerts.append({
                "id": r.get("id"),
                "title": r.get("banner_title") or r.get("source_title"),
                "title_zh": r.get("banner_title_zh"),
                "href": f"whitehouse.html#{r.get('id')}",
                "importance": r.get("importance"),
                "tone": r.get("tone", "neutral"),
                "published_at": r.get("published"),
                "expires_at": exp.isoformat(),
                "tickers": [
                    {"symbol": t.get("symbol"), "direction": t.get("direction"),
                     "chg_pct": t.get("chg_pct")}
                    for t in (r.get("tickers") or [])
                ],
            })
        except Exception as e:  # noqa: BLE001 — one bad row must not nuke the tape
            log.warning("banner row skipped (%s): %s", r.get("id"), e)
    # most important first → it leads the tape; cap to keep the tape readable
    alerts.sort(key=lambda a: (a.get("importance") or 0), reverse=True)
    if max_alerts and len(alerts) > max_alerts:
        log.info("banner: %d live alerts capped to top %d by importance", len(alerts), max_alerts)
        alerts = alerts[:max_alerts]
    return {"schema": "wh_banner.v1", "alerts": alerts}


def _alert_view(r: dict) -> dict:
    """Enrich a ledger row for the report template."""
    v = dict(r)
    v["date_display"] = _date_display(r.get("published"))
    exp = _expires_at(r)
    v["expires_display"] = _date_display(exp.isoformat()) if exp else ""
    v["live"] = bool(exp and datetime.now(timezone.utc) < exp)
    # analysis → paragraphs (template escapes each — XSS-safe)
    a = (r.get("analysis") or "").strip()
    v["paragraphs"] = [p.strip() for p in a.split("\n") if p.strip()]
    v["benefit"] = [t for t in (r.get("tickers") or []) if t.get("direction") == "benefit"]
    v["hurt"] = [t for t in (r.get("tickers") or []) if t.get("direction") == "hurt"]
    return v


def _render_page(root: Path, rows: list[dict], treasury: dict | None = None) -> str:
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    views = []
    for r in rows:
        try:
            views.append(_alert_view(r))
        except Exception as e:  # noqa: BLE001 — one bad row must not blank the page
            log.warning("alert view skipped (%s): %s", r.get("id"), e)
    html = env.get_template("whitehouse.html.j2").render(
        alerts=views, treasury=treasury, disclaimer=wb.DISCLAIMER,
        provider=wb.provider_label(), active_section="research", active_page="whitehouse")
    # self-include the alert banner (whitehouse.html is at site root → prefix "") so the
    # page is stable across renders and the daily inject pass skips it (marker present).
    try:
        from scripts.inject_wh_banner import inject_text
        html = inject_text(html, "")
    except Exception:  # noqa: BLE001
        pass
    return html


# --------------------------------------------------------------------------- #
# pipeline
# --------------------------------------------------------------------------- #
def _health_line(items: list[dict], state: dict, evaluated: list[dict],
                 n_activated: int, provider: str) -> dict:
    """run_status-style health record written at end of every sentinel run.

    Makes dark-vs-quiet permanently distinguishable:
      posts_seen   — items currently on the WH feed (4-day window)
      evaluated    — items that reached the brain this run (0 when no provider)
      gate_scores  — importance histogram for evaluated items [{importance, activated}]
      activated    — how many fired a banner this run
      provider     — which auth path was used, or '' when absent (THE dark signal)
      as_of        — UTC timestamp of this run
    """
    return {
        "schema": "wh_health.v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "posts_seen": len(items),
        "seen_total": len((state or {}).get("seen", {})),
        "evaluated": len(evaluated),
        "activated": n_activated,
        "provider": provider,
        "gate_scores": [
            {"id": r.get("id"), "importance": r.get("importance"),
             "activated": bool(r.get("activated")), "degraded_reason": r.get("degraded_reason")}
            for r in evaluated
        ],
    }


def build(reeval: bool = False, page_only: bool = False) -> int:
    """Refresh the White House desk. page_only=True (the DAILY build's mode) skips the
    feed poll, the brain, and ALL ledger/state writes — it only RE-RENDERS the banner
    JSON + report page from the already-committed ledger. That makes the hourly sentinel
    the SOLE writer of the ledger/processed.json, so the two workflows can never race to
    append-then-`-X theirs`-clobber an alert or revert the dedupe state (double-spend)."""
    root = config.ROOT
    cfg = wb._cfg()
    site = root / config.load().get("storage", {}).get("site_dir", "site")
    now = datetime.now(timezone.utc)

    n_new_active = 0
    if page_only:
        log.info("whitehouse: page-only re-render (no feed/brain/ledger writes)")
        return _rebuild_artifacts(root, site, cfg, now, n_new_active)

    items = wf.collect()
    log.info("whitehouse feed: %d recent items", len(items))
    # —— Treasury Watch lane: refresh TGA in-process, then inject the current TGA episode as
    # a feed-item so it flows through the IDENTICAL dedupe→brain→ledger→banner pipeline. The
    # episode id is anchored to the trailing-window extremum (quarter-end preferred), so the
    # processed.json guid dedupe fires the brain once per episode. All best-effort/non-fatal.
    _refresh_tga(root)
    try:
        from engine import treasury_watch as _tw
        _tre_items = _tw.detect_events(root)
        if _tre_items:
            items = list(items) + _tre_items
            log.info("treasury watch: +%d TGA event(s) injected", len(_tre_items))
    except Exception as e:  # noqa: BLE001
        log.warning("treasury watch detect failed (%s)", e)
    state = wf.load_processed(root)
    todo = items if reeval else wf.new_items(items, state)
    cap = int(cfg.get("max_new_per_run", 6))
    if len(todo) > cap:
        log.info("capping brain calls: %d new → %d (max_new_per_run)", len(todo), cap)
        todo = todo[:cap]

    provider_label = wb.provider_label(cfg)
    if not wb.enabled():
        log.info("whitehouse_brain disabled — skipping evaluation")
        todo = []
    elif not provider_label:
        log.warning(
            "whitehouse_brain: NO provider available "
            "(CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY all absent) "
            "— %d unseen items will be marked seen/inactive this run; "
            "set one of those secrets to activate the desk",
            len(todo),
        )

    evaluated: list[dict] = []
    for it in todo:
        rec = wb.evaluate(it, cfg, root)
        evaluated.append(rec)
        wf.mark_seen(state, it, activated=rec.get("activated", False),
                     importance=rec.get("importance"))
        if rec.get("activated"):
            _append_ledger(root, rec)
            _register_wh_claim(rec, root)           # qledger adapter (W5)
            try:
                (site / "whdata").mkdir(parents=True, exist_ok=True)
                (site / "whdata" / f"{rec['id']}.json").write_text(
                    json.dumps(rec, default=str))
            except Exception as e:  # noqa: BLE001
                log.warning("per-alert json failed (%s)", e)
            n_new_active += 1
            log.info("ALERT %s (imp=%s, %s): %s", rec["id"], rec["importance"],
                     rec["tone"], rec["banner_title"])
        else:
            log.info("skip %s (imp=%s, not activated, reason=%s)",
                     it["id"], rec.get("importance"), rec.get("degraded_reason"))
    wf.save_processed(root, state)

    # W5: health record — makes dark-vs-quiet permanently distinguishable
    health = _health_line(items, state, evaluated, n_new_active, provider_label)
    try:
        hp = root / "data" / "whitehouse" / "health.json"
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(json.dumps(health, indent=2, default=str))
        log.info(
            "WH health: posts_seen=%d evaluated=%d activated=%d provider=%r",
            health["posts_seen"], health["evaluated"], health["activated"],
            health["provider"] or "(none — desk dark)",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("health.json write failed (%s)", e)

    # Treasury Watch panel artifact (sentinel lane only — page-only stays read-only).
    _write_treasury_watch(root, site, now)

    return _rebuild_artifacts(root, site, cfg, now, n_new_active)


def _register_wh_claim(rec: dict, root: Path) -> None:
    """qledger adapter (W5): register one qledger claim per activated WH alert.

    Scope: entity (named ticker) when tickers are present, else macro.
    Direction: from tone (tailwind→+1, headwind→-1, mixed/neutral→0).
    Timestamp quality: PUBLISHER_STATED (WH RSS pubDate has a stated TZ, W0 #12 fixed).
    Claim family: whitehouse (registered in config/qual_ladder.yml at SHADOW).

    One claim per ticker; a tone-only (no tickers) alert registers one macro claim.
    All claims are context/display; none feed scoring arithmetic.
    """
    # W5 ITEM 5: qledger is a hard prod dependency of the WH desk. The ONLY quiet
    # skip is the module itself being absent (stripped/partial checkout) — proven
    # by ModuleNotFoundError.name, not by string-matching the message. Everything
    # else (missing/poisoned transitive dep like numpy, ABI mismatch, None in
    # sys.modules, broken module init) is a production failure and must be loud.
    # importlib.import_module is used instead of `from engine import qledger`
    # because the from-form re-raises a missing submodule as a generic
    # "cannot import name" ImportError, losing the ModuleNotFoundError.name signal.
    try:
        ql = importlib.import_module("engine.qledger")
    except ModuleNotFoundError as _ie:
        if _ie.name in ("engine", "engine.qledger"):
            log.debug("qledger module absent from this checkout — skipping WH claim "
                      "registration (never expected in prod, where engine/qledger.py ships)")
            return
        log.error(
            "engine.qledger failed to import because dependency %r is missing/broken — "
            "qledger is a REQUIRED production dependency of the WH desk, this is NOT "
            "the optional no-qledger path. Claims for %s will NOT be registered. "
            "Error: %s", _ie.name, rec.get("id"), _ie, exc_info=True)
        return
    except ImportError as _ie:
        log.error(
            "engine.qledger failed to import — qledger is a REQUIRED production "
            "dependency of the WH desk, this is NOT the optional no-qledger path. "
            "Claims for %s will NOT be registered. Error: %s",
            rec.get("id"), _ie, exc_info=True)
        return

    tone_dir = {"tailwind": 1, "headwind": -1}.get(rec.get("tone", ""), 0)
    published = (rec.get("published") or rec.get("generated_at") or "")[:10]
    if not published:
        log.debug("wh qledger: no published date on %s, skipping", rec.get("id"))
        return

    tickers = rec.get("tickers") or []
    claims_to_register = []
    if tickers:
        for t in tickers:
            sym = (t.get("symbol") or "").strip().upper()
            if not sym:
                continue
            direction = {"benefit": 1, "hurt": -1}.get(t.get("direction", ""), tone_dir)
            claims_to_register.append(ql.make_claim(
                desk="whitehouse",
                asof=published,
                scope_type="entity",
                scope_key=sym,
                direction=direction,
                horizon_d=int(rec.get("banner_days") or 3) * 1,
                timestamp_quality="PUBLISHER_STATED",
                claim_family="whitehouse",
                extra={
                    "source_id": rec.get("id"),
                    "source_url": rec.get("source_url"),
                    "tone": rec.get("tone"),
                    "importance": rec.get("importance"),
                    "is_context_only": True,
                },
            ))
    else:
        # no tickers — register a single macro/salience claim so the activation is
        # tracked in the ledger even without entity-level grading
        claims_to_register.append(ql.make_claim(
            desk="whitehouse",
            asof=published,
            scope_type="macro",
            scope_key="WH_POLICY",
            direction=tone_dir,
            horizon_d=int(rec.get("banner_days") or 3),
            timestamp_quality="PUBLISHER_STATED",
            bench="SPY",
            claim_family="whitehouse",
            extra={
                "source_id": rec.get("id"),
                "source_url": rec.get("source_url"),
                "tone": rec.get("tone"),
                "importance": rec.get("importance"),
                "is_context_only": True,
            },
        ))

    n_ok = 0
    for claim in claims_to_register:
        try:
            stored = ql.register(claim, root)
            if stored.get("status") != "rejected":
                n_ok += 1
        except Exception as e:  # noqa: BLE001 — isolate one bad claim, never crash the render
            # LOUD by design (W5 doctrine, same as the import guard above): a
            # register failure silently zeroing the ledger is a production bug,
            # not a benign skip. ERROR + exc_info so CI/prod log scans catch it
            # instead of it hiding at WARNING behind a healthy-looking render.
            log.error("qledger register FAILED for %s — claim dropped from the ledger (%s)",
                      claim.get("scope", {}).get("key"), e, exc_info=True)
    log.info("wh qledger: registered %d/%d claims for %s", n_ok, len(claims_to_register), rec.get("id"))


def _rebuild_artifacts(root: Path, site: Path, cfg: dict, now: datetime,
                       n_new_active: int) -> int:
    """Re-render site/wh_banner.json + site/whitehouse.html from the committed ledger,
    IDEMPOTENTLY (only writes on real change). Shared by the sentinel (after appending)
    and the daily page-only re-render. Returns 10 on change, else 0."""
    rows = _load_ledger(root)
    changed = False
    banner = _banner_payload(rows, now, int(cfg.get("max_banner_alerts", 6)))
    if _write_if_changed(site / "wh_banner.json",
                         json.dumps(banner, separators=(",", ":"), default=str)):
        changed = True
        log.info("wh_banner.json: %d live banner(s)", len(banner["alerts"]))
    treasury = _load_treasury_watch(site)   # committed contract (both sentinel + page-only)
    try:
        if _write_if_changed(site / "whitehouse.html", _render_page(root, rows, treasury)):
            changed = True
    except Exception as e:  # noqa: BLE001 — page render must never crash the pipeline
        log.error("whitehouse.html render failed (%s)", e)

    log.info("done: %d new activated alert(s), %d total in ledger, changed=%s",
             n_new_active, len(rows), changed)
    return 10 if (changed or n_new_active) else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    reeval = "--reeval" in sys.argv
    page_only = "--page-only" in sys.argv
    try:
        return build(reeval=reeval, page_only=page_only)
    except Exception as e:  # noqa: BLE001 — the desk must never break the build
        log.error("build_whitehouse failed: %s", e)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
