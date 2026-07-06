"""Build the US Intelligence Hub — the central-command fusion of all five signal desks
(news · alt-data · divergence radar · factor buy-board · policy intent).

Emits site/intel_hub/hub.json (the command data the page + the future US Mastermind read)
AND renders site/intelligence_hub.html. Run AFTER build_intelligence + build_briefing +
build_policy_watch + build_radar_plus (so every feeder artifact exists). Standalone,
degrade-safe — absent inputs degrade to empty panels, never breaks the build.

Also builds the China Lens module (W0.2): reads site/china_intel/briefing.json and emits
site/intel_hub/regions/china.json (schema intelligence_hub.region.v1). Degrade-safe —
absent or unparseable briefing → china=None, module omitted.

Run:  python -m scripts.build_intel_hub
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from engine import intel_hub, hub_track_record, desk_grader  # noqa: E402
from engine.qledger_ui import chips_for_desks, load_track_record  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# China Lens (W0.2) — reads briefing.json, derives a compact display packet.
# No LLM, no new scoring: strings and counts only. Degrade-safe.
# ---------------------------------------------------------------------------
_CHINA_BRIEFING_PATH = Path("site/china_intel/briefing.json")
_STALE_SURFACE_DAYS = 3   # surface marked stale if older than this (aligns with bus news-staleness gate)


def _days_old(iso_date: str | None, reference: date | None = None) -> int | None:
    """Return calendar days between iso_date and reference (today if None).
    Returns None if iso_date is absent or unparseable."""
    if not iso_date:
        return None
    try:
        ref = reference or date.today()
        d = datetime.fromisoformat(iso_date).date()
        return (ref - d).days
    except Exception:  # noqa: BLE001
        return None


def _derive_headline(briefing: dict) -> str:
    """Derive a headline string mechanically from what_changed + top conviction row.
    No LLM, no invented text — copies fields only."""
    wc = briefing.get("what_changed") or {}
    parts: list[str] = []

    stance = wc.get("stance_change")
    if stance and isinstance(stance, dict):
        parts.append(f"Stance: {stance.get('from','?')} → {stance.get('to','?')}")

    band = wc.get("sentiment_band_change")
    if band and isinstance(band, dict):
        parts.append(f"Sentiment: {band.get('from','?')} → {band.get('to','?')}")

    new_acc = wc.get("new_accumulation") or []
    if new_acc:
        parts.append(f"+{len(new_acc)} accumulation")

    new_fires = wc.get("new_radar_fires") or []
    if new_fires:
        parts.append(f"+{len(new_fires)} radar fire{'s' if len(new_fires) != 1 else ''}")

    sched = wc.get("new_scheduled_within_3d") or []
    if sched:
        names = [s.get("name_en", "") for s in sched[:2] if isinstance(s, dict)]
        parts.append("Upcoming: " + ", ".join(n for n in names if n))

    if parts:
        return " · ".join(parts)

    # Fallback: top conviction row's rationale_en (already a short English string)
    conviction = briefing.get("conviction") or []
    if conviction:
        top = conviction[0]
        if not isinstance(top, dict):
            return "No changes flagged"
        sector = top.get("sector_en") or ""
        stage = top.get("stage") or ""
        if sector and stage:
            return f"Top theme: {sector} ({stage})"
        if sector:
            return f"Top theme: {sector}"

    return "No changes flagged"


def build_china_packet(briefing_path: Path | None = None,
                       reference_date: date | None = None) -> dict | None:
    """Read briefing.json and return a compact display packet, or None on failure.

    The packet is degrade-safe: absent file, missing keys, or JSON errors all
    return None. No new scores, no LLM — only string/count copies from the briefing.
    """
    path = briefing_path or _CHINA_BRIEFING_PATH
    try:
        raw = Path(path).read_text(encoding="utf-8")
        b = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        log.debug("china_packet: briefing.json absent or unparseable: %s", e)
        return None

    if not isinstance(b, dict):
        log.debug("china_packet: briefing.json is not a dict")
        return None

    try:
        ref = reference_date or date.today()
        asof = b.get("asof") or b.get("generated_utc", "")
        # Normalise to date-only (strip time component if present)
        asof_date = asof[:10] if asof else ""
        asof_age = _days_old(asof_date, ref)
        # Clamp to 0 — a future-dated briefing must not produce a negative age
        if asof_age is not None and asof_age < 0:
            asof_age = 0

        # Per-surface freshness
        surface_asof_raw = b.get("surface_asof") or {}
        surfaces: dict = {}
        for name, iso in surface_asof_raw.items():
            if iso is None:
                surfaces[name] = {"asof": None, "stale": False}
                continue
            age = _days_old(iso, ref)
            surfaces[name] = {"asof": iso, "stale": age is not None and age > _STALE_SURFACE_DAYS}

        # Top-2 conviction rows (sector, stage, edge_remaining only — no new scoring)
        # Dedup on displayed fields (sector_en, stage, edge_remaining) before the [:2] slice
        conviction_raw = b.get("conviction") or []
        seen_conviction: set[tuple] = set()
        top_conviction: list[dict] = []
        for row in conviction_raw:
            if not isinstance(row, dict):
                continue
            key = (row.get("sector_en", ""), row.get("stage", ""), row.get("edge_remaining"))
            if key in seen_conviction:
                continue
            seen_conviction.add(key)
            top_conviction.append({
                "sector_en": row.get("sector_en", ""),
                "sector_zh": row.get("sector_zh", ""),
                "stage": row.get("stage", ""),
                "stage_zh": row.get("stage_zh", ""),
                "edge_remaining": row.get("edge_remaining"),
            })
            if len(top_conviction) >= 2:
                break

        # Regime chips
        regime_raw = b.get("regime") or {}
        regime = {
            "roro_state": regime_raw.get("roro_state", "") if isinstance(regime_raw, dict) else "",
            "band_en": regime_raw.get("band_en", "") if isinstance(regime_raw, dict) else "",
            "band_zh": regime_raw.get("band_zh", "") if isinstance(regime_raw, dict) else "",
            "risk_tilt": regime_raw.get("risk_tilt") if isinstance(regime_raw, dict) else None,
        }

        # Policy
        policy_raw = b.get("policy") or {}
        policy = {
            "pboc_stance": policy_raw.get("pboc_stance", ""),
            "stance_label_en": policy_raw.get("stance_label_en", ""),
            "stance_label_zh": policy_raw.get("stance_label_zh", ""),
            "stale": bool(policy_raw.get("stale", False)),
        }

        # News band
        news_raw = b.get("news") or {}
        news = {
            "band": news_raw.get("band", ""),
            "band_label_en": news_raw.get("band_label_en", ""),
            "band_label_zh": news_raw.get("band_label_zh", ""),
        }

        headline = _derive_headline(b)
        flagged_ticker_count = len(b.get("flagged_tickers") or [])

        packet = {
            "schema": "intelligence_hub.region.v1",
            "region": "CN",
            "as_of": asof_date,
            "asof_age_days": asof_age,
            "mode": "context_only",
            "headline": headline,
            "regime": regime,
            "policy": policy,
            "news": news,
            "conviction": top_conviction,
            "flagged_ticker_count": flagged_ticker_count,
            "surfaces": surfaces,
            "links": {"detail": "china_intel.html"},
        }
        return packet
    except Exception as e:  # noqa: BLE001
        log.warning("china_packet: unexpected error building packet: %s", e)
        return None


def _attach_live_prices(hub: dict, root, asof: str) -> None:
    """Best-effort nightly close on the SURFACED names only (~60, not the whole universe), so
    the live.js progressive-enhancement layer can patch them to ~15-min-delayed / live prices
    intraday and flag any name whose live price breaches its nightly band. Degrade-safe."""
    try:
        from engine.ai_desk import _level_asof
    except Exception as e:  # noqa: BLE001
        log.debug("live-price helper unavailable: %s", e)
        return
    cache: dict[str, float | None] = {}

    def px(t: str):
        if t not in cache:
            try:
                cache[t] = _level_asof(t, root, asof)
            except Exception:  # noqa: BLE001
                cache[t] = None
        return cache[t]

    lists = ([hub.get("command") or []]
             + [hub.get(k) or [] for k in ("emerging", "exhausted", "catalysts", "discovery")])
    for lst in lists:
        for d in lst:
            t = d.get("ticker")
            if t and "price" not in d:                 # always set the key (None or float) so the
                d["price"] = px(t)                     # template's `d.price is not none` guard is safe


def build(write: bool = True) -> dict:
    hub = intel_hub.load_and_build(top=30)
    _attach_live_prices(hub, config.ROOT, hub.get("as_of") or date.today().isoformat())
    # FALSIFIABLE TRACK-RECORD: record today's claims, grade matured ones (degrade-safe)
    track = {}
    try:
        today = date.today()
        n_new = hub_track_record.snapshot(hub.get("track_rows"), today)
        track = hub_track_record.compute(today)
        log.info("hub track-record: +%d snapshots, %d total, %d matured-any",
                 n_new, track.get("n_snapshots", 0), sum(1 for h in (track.get("horizons") or {}).values() if h.get("n_matured")))
    except Exception as e:  # noqa: BLE001
        log.warning("hub track-record step failed: %s", e)
    hub.pop("track_rows", None)                    # heavy; not part of the published command view
    hub["track_record"] = track
    # UNIFIED FORWARD DESK GRADER (5/10/20/30/60/90d). intel_hub uses the ADAPTER over the
    # existing hub ledger (no double-snapshot) — real matured numbers immediately. Degrade-safe.
    try:
        desk_grader.seed_notes()
        hub["desk_grader"] = desk_grader.compute("intel_hub", date.today())
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader (intel_hub) step failed: %s", e)
        hub["desk_grader"] = {}

    # CHINA LENS (W0.2) — build china packet from briefing.json. Degrade-safe: None if absent.
    root = config.ROOT
    china_briefing_abs = root / _CHINA_BRIEFING_PATH
    china = build_china_packet(china_briefing_abs)
    if china:
        log.info("china lens: asof=%s, age=%sd, surfaces=%s",
                 china.get("as_of"), china.get("asof_age_days"), list(china.get("surfaces", {}).keys()))
    else:
        log.info("china lens: briefing absent or unparseable — module will be omitted")

    if not write:
        return hub
    site = root / config.load()["storage"]["site_dir"]
    (site / "intel_hub").mkdir(parents=True, exist_ok=True)
    (site / "intel_hub" / "hub.json").write_text(json.dumps(hub, default=str))
    (site / "intel_hub" / "track_record.json").write_text(json.dumps(track, default=str))

    # Write china region JSON regardless of write flag (it's a standalone artifact)
    if china:
        regions_dir = site / "intel_hub" / "regions"
        regions_dir.mkdir(parents=True, exist_ok=True)
        (regions_dir / "china.json").write_text(json.dumps(china, default=str, ensure_ascii=False))
        log.info("built site/intel_hub/regions/china.json")

    log.info("built site/intel_hub/hub.json — %d universe, %d actionable, EE=%d CT=%d",
             hub.get("n_universe", 0), hub.get("n_actionable", 0),
             hub.get("counts", {}).get("early_edge", 0), hub.get("counts", {}).get("crowded_top", 0))
    if not hub.get("command"):                 # surface an empty fuse in the daily.yml logs
        log.warning("intel hub: empty command — feeders (intelligence/policy/radar) may be missing")

    # qledger honesty chips: derive UNGRADED/ACCRUING/GRADED state for each desk
    # rendered on the intelligence hub.  Never fatal — absent ledger → UNGRADED chips.
    qledger_chips: dict = {}
    try:
        tr = load_track_record(root)
        qledger_chips = chips_for_desks(
            ["alt_data", "radar", "intel_hub", "policy", "news", "standout"], tr
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("qledger chips skipped (%s)", exc)

    # render the page
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(loader=FileSystemLoader(str(root / "templates")),
                          autoescape=select_autoescape(["html", "xml"]))
        html = env.get_template("intelligence_hub.html.j2").render(
            hub=hub, built=datetime.now(timezone.utc).isoformat(), mode="intel_hub",
            qledger_chips=qledger_chips, china=china)
        write_page(site / "intelligence_hub.html", html)
        log.info("built site/intelligence_hub.html")
    except Exception as e:  # noqa: BLE001
        log.error("intelligence_hub render failed: %s", e)
    return hub


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_intel_hub failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
