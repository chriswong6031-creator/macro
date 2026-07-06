"""Build the bottom-sensor QA display page.

Amendment 1, Lane B0, PR-2.  Display-only.  Reads:
  - site/neuralwebdata/bottom_sensors.json   (written by build_bottom_sensors.py)
  - data/neuralweb/bottom_sensors.parquet    (fallback)

Writes:
  - site/qa_bottom_sensors.html              (via write_page for data-base shim)

The page is reachable by URL only — NO nav/menu changes are made (nav chrome is
shared and hand-duplicated; adding it is explicitly out of scope per the spec).

Usage:
    python -m scripts.build_qa_bottom_sensors [--root /path/to/repo]
    python scripts/build_qa_bottom_sensors.py
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger(__name__)

TEMPLATE_NAME = "qa_bottom_sensors.html.j2"
PAGE_OUT = "qa_bottom_sensors.html"

# State display order — most actionable first
STATE_ORDER = [
    "HOLD_LAUNCHED",
    "FRESH_FIRE_DURABLE_CAND",
    "FRESH_FIRE_TACTICAL",
    "EARLY_WATCH",
    "CHASE_RISK",
    "DEAD_MONEY_RISK",
    "KNIFE_RISK",
    "WATCH",
]


def _site_dir() -> Path:
    try:
        sd = Path(config.load()["storage"]["site_dir"])
        return sd if sd.is_absolute() else (config.ROOT / sd)
    except Exception:  # noqa: BLE001
        return config.ROOT / "site"


def _load_payload(root: Path) -> dict:
    """Load bottom_sensors payload from JSON (preferred) or parquet fallback."""
    json_path = root / "site" / "neuralwebdata" / "bottom_sensors.json"
    if json_path.exists():
        log.info("loading %s", json_path)
        return json.loads(json_path.read_text())

    # parquet fallback — convert to the same payload shape
    pq_path = root / "data" / "neuralweb" / "bottom_sensors.parquet"
    if pq_path.exists():
        log.info("json not found, falling back to %s", pq_path)
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(pq_path)
        records = []
        for rec in df.to_dict(orient="records"):
            clean: dict = {}
            for k, v in rec.items():
                if v is None:
                    clean[k] = None
                elif isinstance(v, float) and v != v:  # NaN
                    clean[k] = None
                elif isinstance(v, (bool, int, str, float)):
                    clean[k] = v
                else:
                    clean[k] = str(v)
            records.append(clean)
        return {
            "as_of": str(df.attrs.get("as_of", "")),
            "labels_version": str(df.attrs.get("labels_version", "labels_v1")),
            "is_display_only": True,
            "n_rows": len(records),
            "rows": records,
        }

    raise FileNotFoundError(
        f"Neither {json_path} nor {pq_path} exists. "
        "Run build_bottom_sensors.py first."
    )


def build(root: Path | None = None) -> Path:
    """Render qa_bottom_sensors.html and return the output path."""
    if root is None:
        root = config.ROOT

    payload = _load_payload(root)
    rows = payload.get("rows", [])
    n_rows = payload.get("n_rows", len(rows))
    as_of = payload.get("as_of", "")
    labels_version = payload.get("labels_version", "labels_v1")

    # Infer computed_at from first row; fall back to as_of
    computed_at = rows[0].get("computed_at", as_of) if rows else as_of

    # ── Summary counts ──
    state_counts: dict[str, int] = {}
    for s in STATE_ORDER:
        cnt = sum(1 for r in rows if r.get("bottom_state") == s)
        if cnt:
            state_counts[s] = cnt

    # Overlay flag counts — split multi-flag values so 'COILED,EVENT_BLACKOUT'
    # is counted as two separate flags, consistent with how the template splits on ','.
    raw_overlays: Counter = Counter()
    for r in rows:
        for flag in (r.get("overlay_flags") or "").split(","):
            flag = flag.strip()
            if flag:
                raw_overlays[flag] += 1
    overlay_counts: dict[str, int] = dict(raw_overlays)
    # Also count coiled / star / event_blackout from boolean fields for the strip
    coiled_cnt = sum(1 for r in rows if r.get("coiled"))
    star_cnt = sum(1 for r in rows if r.get("star"))
    if coiled_cnt and "COILED" not in overlay_counts:
        overlay_counts["COILED"] = coiled_cnt
    if star_cnt and "STAR" not in overlay_counts:
        overlay_counts["STAR"] = star_cnt

    # ── Sponsorship coverage counts (PR-C1) ──
    sponsorship_populated = sum(
        1 for r in rows
        if r.get("sponsorship_state") and r.get("sponsorship_state") != "unavailable"
    )
    sponsorship_unavailable = sum(
        1 for r in rows
        if not r.get("sponsorship_state") or r.get("sponsorship_state") == "unavailable"
    )

    log.info(
        "bottom_sensors: n_rows=%d state_counts=%s overlay_counts=%s "
        "sponsorship_populated=%d sponsorship_unavailable=%d",
        n_rows, state_counts, overlay_counts,
        sponsorship_populated, sponsorship_unavailable,
    )

    # ── Jinja render ──
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001
        pass  # i18n globals optional — template defines its own t() macro

    html = env.get_template(TEMPLATE_NAME).render(
        rows=rows,
        n_rows=n_rows,
        as_of=as_of,
        labels_version=labels_version,
        computed_at=computed_at,
        state_counts=state_counts,
        overlay_counts=overlay_counts,
        sponsorship_populated=sponsorship_populated,
        sponsorship_unavailable=sponsorship_unavailable,
    )

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    out = site / PAGE_OUT
    write_page(out, html)
    log.info("wrote %s (%d KB)", out, len(html) // 1024)
    return out


def main() -> int:
    import argparse  # noqa: PLC0415
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build bottom-sensor QA page")
    ap.add_argument("--root", default=None, help="Repo root (default: inferred)")
    args = ap.parse_args()
    root = Path(args.root) if args.root else _REPO_ROOT
    try:
        out = build(root)
        print(f"OK: {out}")
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
