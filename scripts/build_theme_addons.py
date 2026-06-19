"""Build the Theme Rotation Desk ADD-ONS -> site/basketdata/*.json (display-only).

Three context panels that sit beside the Theme Rotation Desk on the thematic page, each a
new engine over caches we already keep (zero new collection):

  etf_pulse.json        engine.etf_pulse        style / risk / sector rotation strip
  vol_sentiment.json    engine.vol_sentiment    vol-regime + CBOE put/call chip
  theme_extension*.json engine.theme_extension  per-theme ATR "too hot" texture (US + CN/HK/CA)

Standalone and additive (clones build_baskets.py): any engine that fails logs and is
skipped — it can never break the rest of the site. The JSONs are consumed client-side by
site/theme_addons.js (and the ready-to-include templates/_theme_addons.html.j2).

Usage: python -m scripts.build_theme_addons
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_theme_addons")


def _dump(fdir: Path, name: str, payload) -> bool:
    if not payload:
        return False
    (fdir / name).write_text(json.dumps(payload, separators=(",", ":"), default=str))
    return True


def main() -> int:
    fdir = config.ROOT / "site" / "basketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    wrote = []

    try:
        from engine.etf_pulse import compute_etf_pulse
        if _dump(fdir, "etf_pulse.json", compute_etf_pulse()):
            wrote.append("etf_pulse")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("etf_pulse failed: %s", e)

    try:
        from engine.vol_sentiment import compute_vol_sentiment
        if _dump(fdir, "vol_sentiment.json", compute_vol_sentiment()):
            wrote.append("vol_sentiment")
    except Exception as e:  # noqa: BLE001
        log.error("vol_sentiment failed: %s", e)

    # per-theme ATR extension — US always; CN/HK/CA opportunistically (skip on shortfall)
    try:
        from engine.theme_extension import compute_theme_extension
        for region, fname in (("us", "theme_extension.json"), ("cn", "theme_extension_cn.json"),
                              ("hk", "theme_extension_hk.json"), ("ca", "theme_extension_ca.json")):
            try:
                if _dump(fdir, fname, compute_theme_extension(region)):
                    wrote.append(f"theme_extension:{region}")
            except Exception as e:  # noqa: BLE001 — one region failing never blocks the rest
                log.error("theme_extension[%s] failed: %s", region, e)
    except Exception as e:  # noqa: BLE001
        log.error("theme_extension import failed: %s", e)

    log.info("theme add-ons built -> %s (%s)", fdir, ", ".join(wrote) or "nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
