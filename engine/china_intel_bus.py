"""China Intelligence transmission bus — the connector to the (future) China Mastermind.

LEAF · CONTEXT-ONLY · NEVER A SCORE/SIZE. This is the China sibling of the macro
`engine/master_brain.py` brief: it bundles the four China intelligence surfaces —
News, Central-Bank/Policy Watch, Alternative Data, Divergence Radar — into ONE
schema-versioned, machine-readable rollup that the China Mastermind bot will read as
CONTEXT (exactly as the existing bot reads `site/altdata/*.json` and the master briefs).

It DECOUPLES from each surface by reading their already-emitted JSON artifacts off disk
(so build ordering is the only dependency); every reader degrades to None when its
surface has not been built yet, and NOTHING here ever raises into a build. As each
phase lands, its reader starts returning real data — the contract below does not change.

Emits:
  site/china_intel/briefing.json  — full `china_intel.briefing.v1`
  site/china_intel/digest.json    — compact Opus-optimized plain-text rollup

Nothing in any scoring path imports this; it is a one-way fan-in of display/context
artifacts. See research/CHINA_INTEL_POWERHOUSE.md §5.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_intel.briefing.v1"

DISCLAIMER = (
    "Context only — not a signal, score or trade. A fan-in of four display/context-only "
    "China intelligence surfaces (news, central-bank & policy, alternative data, "
    "divergence radar), bundled for the China Mastermind to read as background. Nothing "
    "here is an input to any score, signal, regime or allocation."
)
DISCLAIMER_ZH = (
    "仅作背景，非信号、评分或交易。这是四个仅供展示／背景的中国情报面板（新闻、央行与政策、"
    "另类数据、背离雷达）的汇总，供中国 Mastermind 作为背景读取。其中没有任何内容会进入任何"
    "评分、信号、区制或配置。"
)


# --------------------------------------------------------------------------- #
# disk helpers — resolve site/ + read a JSON artifact, None on any failure
# --------------------------------------------------------------------------- #
def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _read_json(rel: str) -> dict | list | None:
    """Read a JSON artifact under site/ (or an absolute path). None if absent/bad."""
    try:
        p = Path(rel)
        if not p.is_absolute():
            p = _site_dir() / rel
        if not p.exists():
            # also try data_dir for non-site artifacts (e.g. data/china_policy/latest.json)
            alt = config.ROOT / rel
            if alt.exists():
                p = alt
            else:
                return None
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("china_intel_bus: read %s failed (%s)", rel, e)
        return None


# --------------------------------------------------------------------------- #
# per-surface compact readers — each returns a small dict or None.
# Filled in as each phase lands; the keys are the stable contract.
# --------------------------------------------------------------------------- #
def _news_block() -> dict | None:
    """Phase 1: media-sentiment + event-bus highlights from site/chinanews/*."""
    sent = _read_json("chinanews/sentiment.json")
    feed = _read_json("chinanews/feed.json")
    if not sent and not feed:
        return None
    out: dict = {}
    if isinstance(sent, dict):
        out["sentiment_z"] = sent.get("z")
        out["band"] = sent.get("band")
        out["n_events_7d"] = sent.get("n_events_7d")
    if isinstance(feed, dict):
        out["top_themes"] = feed.get("top_themes") or []
        out["scheduled_ahead"] = feed.get("scheduled_ahead") or []
    return out or None


def _policy_block() -> dict | None:
    """Phase 2: PBoC stance + corridor + predictions from data/china_policy/latest.json."""
    pol = _read_json("data/china_policy/latest.json")
    if not isinstance(pol, dict):
        return None
    return {
        "pboc_stance": pol.get("stance"),
        "lpr_1y": pol.get("lpr_1y"),
        "lpr_5y": pol.get("lpr_5y"),
        "rrr": pol.get("rrr"),
        "fx_reserves": pol.get("fx_reserves"),
        "last_moves": pol.get("last_moves") or [],
        "predictions": pol.get("predictions") or [],
    }


def _altdata_block() -> dict | None:
    """Phase 3: per-ticker convergence extremes from site/chinaaltdata/mastermind.json."""
    ad = _read_json("chinaaltdata/mastermind.json")
    if not isinstance(ad, dict):
        return None
    return {
        "convergence_top": ad.get("convergence_top") or [],
        "convergence_bottom": ad.get("convergence_bottom") or [],
        "crowding_flags": ad.get("crowding_flags") or [],
    }


def _radar_block() -> dict | None:
    """Phase 4: live divergences from site/chinaradar/radar.json."""
    rad = _read_json("chinaradar/radar.json")
    if not isinstance(rad, dict):
        return None
    return {"divergences": rad.get("divergences") or []}


# --------------------------------------------------------------------------- #
# digest — a compact plain-text rollup (Opus-optimized) over whatever is present
# --------------------------------------------------------------------------- #
def _digest_text(b: dict) -> str:
    parts: list[str] = []
    n = b.get("news")
    if n:
        z = n.get("sentiment_z")
        parts.append(f"News: media sentiment {n.get('band','?')}"
                     + (f" (z {z:+.2f})" if isinstance(z, (int, float)) else "")
                     + (f", {n['n_events_7d']} events/7d" if n.get("n_events_7d") else ""))
        if n.get("top_themes"):
            parts.append("  themes: " + ", ".join(str(t) for t in n["top_themes"][:4]))
    p = b.get("policy")
    if p:
        parts.append(f"PBoC: stance {p.get('pboc_stance','?')}; "
                     f"LPR1Y {p.get('lpr_1y','?')} / 5Y {p.get('lpr_5y','?')}; "
                     f"RRR {p.get('rrr','?')}")
        if p.get("last_moves"):
            parts.append("  recent: " + "; ".join(str(m) for m in p["last_moves"][:3]))
    a = b.get("altdata")
    if a and a.get("convergence_top"):
        parts.append("Alt-data accumulation: "
                     + ", ".join(str(x) for x in a["convergence_top"][:5]))
    r = b.get("radar")
    if r and r.get("divergences"):
        ds = r["divergences"][:5]
        parts.append("Radar divergences: "
                     + "; ".join(f"{d.get('sector') or d.get('theme','?')} "
                                 f"{d.get('sign','?')}" for d in ds))
    if not parts:
        return "China intelligence bus: no surfaces built yet."
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# public: assemble + build
# --------------------------------------------------------------------------- #
def briefing(asof: date | str | None = None) -> dict:
    """Assemble the context-only `china_intel.briefing.v1` from on-disk surface emits.
    Always returns a valid dict (empty sections degrade to None). Never raises."""
    b = {
        "schema": SCHEMA,
        "is_context_only": True,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "asof": str(asof) if asof else str(date.today()),
        "news": None, "policy": None, "altdata": None, "radar": None,
        "disclaimer": DISCLAIMER, "disclaimer_zh": DISCLAIMER_ZH,
    }
    for key, fn in (("news", _news_block), ("policy", _policy_block),
                    ("altdata", _altdata_block), ("radar", _radar_block)):
        try:
            b[key] = fn()
        except Exception as e:  # noqa: BLE001 — degrade per-surface, never fatal
            log.debug("china_intel_bus: %s block failed (%s)", key, e)
            b[key] = None
    b["digest"] = _digest_text(b)
    b["surfaces_present"] = [k for k in ("news", "policy", "altdata", "radar") if b.get(k)]
    return b


def build() -> dict | None:
    """Write site/china_intel/{briefing,digest}.json. Returns the briefing or None."""
    try:
        b = briefing()
        outdir = _site_dir() / "china_intel"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "briefing.json").write_text(
            json.dumps(b, ensure_ascii=False, separators=(",", ":"), default=str))
        (outdir / "digest.json").write_text(json.dumps(
            {"schema": "china_intel.digest.v1", "is_context_only": True,
             "generated_utc": b["generated_utc"], "asof": b["asof"],
             "surfaces_present": b["surfaces_present"], "text": b["digest"]},
            ensure_ascii=False, separators=(",", ":"), default=str))
        log.info("china_intel_bus: wrote briefing (%d surfaces)", len(b["surfaces_present"]))
        return b
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_intel_bus build failed (%s)", e)
        return None
