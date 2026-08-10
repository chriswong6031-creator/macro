"""Build the Fed & Policy Watch page -> site/policy_watch.html.

A realpolitik, interest-driven intelligence layer on the Fed and the Administration.
Reads a curated, source-grounded substrate (data/policy/intel.json) and renders:
  - the coordinated-regime thesis + market-relevant narrative-vs-revealed divergence,
  - the Fed under Warsh (profile + 5 reform task forces as dated, falsifiable items),
  - the Administration's grand strategy (verified levers + clearly-labeled priors),
  - a capital-rotation map (targeted vs starved, mechanism + proxy tickers),
  - an ACCOUNTABLE falsifiable-prediction ledger (each with a check-by date + status),
  - a monitor list of highest-signal sources, plus sources & honest caveats.

Everything is display-only / context-only and labels FACT vs INFERENCE vs PRIOR. The
prediction ledger is the accountability spine: outcomes get scored over time so the
qualitative layer earns (or loses) a track record instead of being vibes.

Additive — if intel.json is missing the page is skipped, never breaking the build.

Usage: python -m scripts.build_policy_watch
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_policy_watch")


def brief(text: object, limit: int = 160) -> str:
    """Return one readable sentence for the glance layer.

    The policy substrate intentionally keeps full research notes.  The public
    page should not dump those notes into every card, so this helper preserves
    the first complete thought and applies a word-safe cap when that thought is
    still too long.  Full records remain available in the closed detail layer.
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value or len(value) <= limit:
        return value
    sentence = re.split(r"(?<=[.!?。！？])\s*", value, maxsplit=1)[0].strip()
    candidate = sentence if 24 <= len(sentence) <= limit else value[: limit + 1]
    if len(candidate) <= limit:
        return candidate
    clipped = candidate[:limit].rstrip()
    if " " in clipped and not re.search(r"[\u3400-\u9fff]", clipped):
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:，；：") + "…"


def source_label(url: object) -> str:
    """Turn a source URL into a short publisher label."""
    host = urlparse(str(url or "")).netloc.lower().split(":", 1)[0]
    host = host.removeprefix("www.")
    known = {
        "federalreserve.gov": "Federal Reserve",
        "home.treasury.gov": "U.S. Treasury",
        "treasury.gov": "U.S. Treasury",
        "whitehouse.gov": "White House",
        "energy.gov": "Energy Department",
        "sec.gov": "SEC",
        "nato.int": "NATO",
        "congress.gov": "Congress",
        "supremecourt.gov": "Supreme Court",
        "cmegroup.com": "CME Group",
    }
    if host in known:
        return known[host]
    return host or "Source"


def _verified_labels(as_of: object) -> tuple[str, str]:
    raw = str(as_of or "").strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return raw, raw
    return parsed.strftime("%b %-d, %Y"), f"{parsed.year}年{parsed.month}月{parsed.day}日"


def _featured_predictions(preds: list[dict], dates: object, limit: int = 6) -> list[dict]:
    """Put overdue and open calls ahead of the long technical ledger."""
    date_rows = (dates or {}).get("predictions", {}) if isinstance(dates, dict) else {}

    def decorated(pred: dict) -> dict:
        date_row = date_rows.get(pred.get("id"), {}) or {}
        # P44's ceasefire premise broke before its deadline; it is no longer a
        # clean active forecast and should stay in review until rewritten.
        needs_review = bool(date_row.get("overdue")) or pred.get("id") == "P44"
        return {**pred, "needs_review": needs_review}

    rows = [decorated(pred) for pred in preds]

    def rank(pred: dict) -> tuple[int, str, str]:
        if pred["needs_review"]:
            bucket = 0
        elif pred.get("status") == "open":
            bucket = 1
        else:
            bucket = 2
        return bucket, str(pred.get("check_by") or "9999-12-31"), str(pred.get("id") or "")

    return sorted(rows, key=rank)[:limit]


def main() -> int:
    site = config.ROOT / "site"
    site.mkdir(exist_ok=True)
    intel_path = config.data_dir() / "policy" / "intel.json"
    if not intel_path.exists():
        # fall back to a repo-tracked copy if the data dir isn't seeded
        alt = config.ROOT / "data" / "policy" / "intel.json"
        intel_path = alt if alt.exists() else intel_path
    if not intel_path.exists():
        log.warning("policy intel.json missing (%s) — skipping (additive)", intel_path)
        return 0

    intel = json.loads(intel_path.read_text())

    preds = intel.get("predictions", [])
    counts = {
        "total": len(preds),
        "open": sum(1 for p in preds if p.get("status") == "open"),
        "hit": sum(1 for p in preds if p.get("status") == "hit"),
        "miss": sum(1 for p in preds if p.get("status") == "miss"),
        "policy_action": sum(1 for p in preds if p.get("tier") == "policy-action"),
        "market_outcome": sum(1 for p in preds if p.get("tier") == "market-outcome"),
    }
    resolved = counts["hit"] + counts["miss"]
    counts["hit_rate"] = (counts["hit"] / resolved) if resolved else None

    # the LLM intent desk output (generated in CI by engine.policy_intent_desk; absent
    # locally -> the section simply hides). Drop raw_text defensively.
    desk = None
    try:
        dj = json.loads((site / "policy_intent.json").read_text())
        desk = {k: v for k, v in dj.items() if k != "raw_text"}
    except Exception:  # noqa: BLE001
        desk = None

    # explicit Fed reaction-function read (display-only) from the regime latest.json
    fed_stance = None
    fed_hist = {}
    try:
        from engine import fed_stance as _fs
        latest = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        fed_stance = _fs.snapshot(latest)
        fed_hist = _fs.history_summary()    # PRIOR streak (today's stance is in the panel)
        _fs.append_history(fed_stance)      # record today for the timeline
    except Exception as e:  # noqa: BLE001
        log.warning("fed_stance skipped: %s", e)

    # rotation realized-check — grade each targeted theme's proxies vs SPY (coincident),
    # accrue it forward (idempotent per day) + read back a per-theme trailing hit-rate.
    rot = None
    rot_hist = {}
    try:
        from engine import policy_rotation_check as _rotc
        rot = _rotc.check(intel)
        rot_hist = _rotc.history_summary()   # PRIOR accrued reads (today's verdict is in the chip)
        _rotc.append_history(rot)            # then record today for future reads
    except Exception as e:  # noqa: BLE001
        log.warning("rotation check skipped: %s", e)

    # live dating: intel staleness + task-force countdowns + overdue-prediction flags
    dates = None
    try:
        from engine import policy_dates as _pd
        dates = _pd.annotate(intel)
    except Exception as e:  # noqa: BLE001
        log.warning("policy dates skipped: %s", e)

    # catalyst spine — stamp each dated event with a live days-to / past flag so the
    # forward calendar counts down on the page (additive; absent block -> section hides)
    catalysts = None
    try:
        cat = intel.get("catalysts")
        if cat and cat.get("spine"):
            from datetime import date as _date
            # the spine is an all-ET calendar (8:30am prints, 2pm decisions) — count down
            # against the US/Eastern date so it doesn't roll over after ~8pm ET (UTC midnight)
            try:
                from zoneinfo import ZoneInfo
                today = datetime.now(ZoneInfo("America/New_York")).date()
            except Exception:  # noqa: BLE001 — fall back to UTC if tz db is unavailable
                today = datetime.now(timezone.utc).date()
            rows = []
            for ev in cat["spine"]:
                try:
                    d = _date.fromisoformat(ev.get("date", ""))
                    days_to = (d - today).days
                except Exception:  # noqa: BLE001
                    days_to = None
                rows.append({**ev, "days_to": days_to,
                             "past": days_to is not None and days_to < 0})
            catalysts = {**cat, "spine": rows}
    except Exception as e:  # noqa: BLE001
        log.warning("catalyst spine skipped: %s", e)

    # unified accountability scorecard (predictions / rotation / stance / freshness) +
    # the sharpest divergence (a targeted theme that is actually lagging worst).
    scorecard = None
    try:
        from engine import policy_summary as _psum
        scorecard = _psum.summarize(counts, rot, fed_hist, dates)
    except Exception as e:  # noqa: BLE001
        log.warning("scorecard skipped: %s", e)

    verified_en, verified_zh = _verified_labels(intel.get("as_of"))
    source_links = [{"url": url, "label": source_label(url)} for url in intel.get("sources", [])]
    featured_predictions = _featured_predictions(preds, dates)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("policy_watch.html.j2").render(
        intel=intel, counts=counts, desk=desk, fed_stance=fed_stance, fed_hist=fed_hist,
        rot=rot, rot_hist=rot_hist, dates=dates, catalysts=catalysts, scorecard=scorecard,
        generated_utc=built, verified_en=verified_en, verified_zh=verified_zh,
        source_links=source_links, featured_predictions=featured_predictions, brief=brief,
        active_section="research", active_page="policy_watch",
    )
    # Jinja's language branches leave indentation on otherwise-empty lines.
    # Normalize it here so the committed artifact stays diff-clean after every build.
    html = re.sub(r"[ \t]+(?=\n)", "", html)
    write_page(site / "policy_watch.html", html)
    log.info("wrote %s/policy_watch.html (%d preds, %d task forces, %d KB)",
             site, counts["total"], len(intel.get("fed", {}).get("task_forces", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
