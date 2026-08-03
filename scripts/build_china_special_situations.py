"""Build the China Special Situations desk page + machine-readable emits.

Runs the special-situations desk engine, writes site/chinaspecialdata/special.json,
renders site/china_special_situations.html. Callable standalone + importable.
CONTEXT-ONLY · never raises. See research/CHINA_INTEL_HUB_MASTERPLAN.md §W2.

Tier gate (docs/TIER_PREVIEW_PATTERN.md)
    The desk is Insider/Pro. The page keeps a free-visible shell — the whole
    overhang read (every plane's state, glance line and counts) plus a small
    preview slice of the two newest-first queues — and the NAMED rows ship
    separately as site/premiumdata/china_special_situations.json, which
    config/site_access.yml enforces as Insider+ today, ahead of the site-wide
    PAYWALL_ENABLED switch. The split is the gate: the shell never receives the
    paid rows, so there is nothing for a hostile client to un-hide.
    Switch: config.yml `china_special_situations.gated` / `preview_rows`.

Ordering dependency (data freshness):
    data/china_filings/filings.parquet freshness is produced by the asia-lane collect
    step that runs collectors/china_filings.py BEFORE this build script is invoked.
    There is NO in-build refresh of china_filings by design — the collector is a
    network-bound step that belongs in the collect phase, not the build phase.
    If this script is run standalone (outside the asia-lane pipeline), the inquiry
    block will read whatever filings.parquet was last written by the collector; the
    asof/status chip will surface staleness honestly.

--no-refresh:
    Re-render the page + payload from the COMMITTED site/chinaspecialdata/special.json
    without running the engine. This is what render.yml's express lane calls, so a
    template or gate fix reaches the baked shell in minutes: the snapshot is reused
    verbatim, so an untouched desk rebakes byte-for-byte and commits nothing, and the
    engine's qledger/sidecar writes stay where they belong (the nightly asia lane).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config, site_assets
from lib.pages import write_page

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js")

# Paid payload for the tier gate. /premiumdata/ is Insider+ at the edge —
# config/site_access.yml `premium.enforced_early` gates the whole prefix today,
# regardless of the PAYWALL_ENABLED launch switch.
PAYLOAD_DIR = "premiumdata"
PAYLOAD_NAME = "china_special_situations.json"
ROWS_PARTIAL = "_china_special_situations_rows.html.j2"

# The two newest-first queues carry the free preview slice: a reader sees the desk
# working on the situations closest in time, without being handed the ranked boards.
# Everything else on this desk is a "top N by magnitude" board — best-first, never
# preview material (docs/TIER_PREVIEW_PATTERN.md).
PREVIEW_PLANES = (("unlocks", "events"), ("inquiry", "letters"))
# Named rows that the free shell never contains at all.
LOCKED_PLANES = (
    ("preannounce", "top_movers"),
    ("buyback", "top"),
    ("pledge", "top"),
    ("st", "top_current"), ("st", "additions"), ("st", "removals"),
    ("block_trades", "top_premium"), ("block_trades", "top_discount"),
)


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _gate_cfg() -> tuple[bool, int]:
    """(gated, preview_rows) from config.yml — the desk's tier-gate switch."""
    cs = (config.load().get("china_special_situations") or {})
    try:
        preview = max(0, int(cs.get("preview_rows", 3)))
    except (TypeError, ValueError):
        preview = 3
    return bool(cs.get("gated", False)), preview


def _rows(blk: object, key: str) -> list:
    return list(blk.get(key) or []) if isinstance(blk, dict) else []


def _split(snap: dict, preview_n: int) -> tuple[dict, dict, dict]:
    """(shell_snapshot, locked_rows_by_plane, gate) — or (snap, {}, None) if nothing is withheld.

    The shell snapshot is a shallow copy whose per-name lists are replaced by the
    preview slice (or emptied). Every count/status/glance/asof key is left alone:
    Free keeps honest totals, and only the names move behind the wall.
    """
    locked: dict[str, list] = {}
    shell = dict(snap)
    for blk_key, list_key in PREVIEW_PLANES:
        rows = _rows(snap.get(blk_key), list_key)
        rest = rows[preview_n:]
        if rest:
            locked[f"{blk_key}.{list_key}"] = rest
            shell[blk_key] = {**snap[blk_key], list_key: rows[:preview_n]}
    for blk_key, list_key in LOCKED_PLANES:
        rows = _rows(snap.get(blk_key), list_key)
        if rows:
            locked[f"{blk_key}.{list_key}"] = rows
            shell[blk_key] = {**shell.get(blk_key, snap.get(blk_key) or {}), list_key: []}
    if not locked:
        return snap, {}, None

    # by_ticker is a per-name rollup of exactly the rows we just withheld. The page
    # never renders it, but the shell has no business carrying it either.
    shell.pop("by_ticker", None)

    planes = sorted({k.split(".", 1)[0] for k in locked})
    n_preview = sum(len(_rows(shell.get(b), k)) for b, k in PREVIEW_PLANES)
    gate = {
        "tier": "essential",
        "payload": f"/{PAYLOAD_DIR}/{PAYLOAD_NAME}",
        "preview": preview_n,
        "n_preview": n_preview,
        "locked": sum(len(v) for v in locked.values()),
        "planes": planes,
    }
    return shell, locked, gate


def _write_premium_payload(env, gate: dict | None, snap: dict, locked: dict) -> None:
    """Render the paid remainder of the desk into site/premiumdata/.

    Written on every build — including the ungated one, where it is an empty
    payload — so flipping `gated` off never leaves a stale full board readable
    at the payload URL.
    """
    out = _site_dir() / PAYLOAD_DIR
    out.mkdir(parents=True, exist_ok=True)
    built = str((snap or {}).get("generated_utc") or "")
    if gate is None:
        doc = {"schema": "tier_payload.v1", "gated": False, "built": built}
    else:
        r = env.get_template(ROWS_PARTIAL).module
        st_locked = {
            "additions": locked.get("st.additions", []),
            "removals": locked.get("st.removals", []),
            "top_current": locked.get("st.top_current", []),
        }
        bt_locked = {
            "top_premium": locked.get("block_trades.top_premium", []),
            "top_discount": locked.get("block_trades.top_discount", []),
        }
        inq = snap.get("inquiry") or {}
        n_shown = len(_rows(inq, "letters"))
        doc = {
            "schema": "tier_payload.v1",
            "gated": True,
            "required_tier": gate["tier"],
            "built": built,
            "preview": gate["preview"],
            "locked": gate["locked"],
            "planes": gate["planes"],
            # Rendered from the SAME partial the shell used, so the hydrated desk
            # and the preview slice can never drift apart.
            "unlocks_html": str(r.unlock_rows(locked.get("unlocks.events", []))),
            "inquiry_html": str(r.inquiry_rows(locked.get("inquiry.letters", []))),
            "inquiry_note_html": str(r.inquiry_note(n_shown, inq.get("n_letters") or n_shown)),
            "movers_html": str(r.preannounce_movers(
                {"top_movers": locked.get("preannounce.top_movers", [])})),
            "buyback_html": str(r.buyback_body(
                {**(snap.get("buyback") or {}), "top": locked.get("buyback.top", [])})),
            "pledge_html": str(r.pledge_body(
                {**(snap.get("pledge") or {}), "top": locked.get("pledge.top", [])})),
            "st_html": str(r.st_named(st_locked)),
            "blocks_html": str(r.block_tables(bt_locked)),
        }
    (out / PAYLOAD_NAME).write_text(
        json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("wrote %s/%s (gated=%s)", out, PAYLOAD_NAME, doc["gated"])


def _read_committed_snapshot() -> dict | None:
    p = _site_dir() / "chinaspecialdata" / "special.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("build_china_special_situations: --no-refresh could not read %s (%s)", p, e)
        return None


def build(refresh: bool = True) -> dict | None:
    import importlib
    import os

    if refresh:
        from engine import china_special_situations as css

        # Best-effort collector refresh when running in the asia-close lane.
        # Idempotency gates inside each collector make repeat calls cheap no-ops.
        if os.environ.get("CN_LANE", "") == "asia":
            for mod_name, fn_name in (
                ("collectors.china_unlocks",     "refresh"),
                # china_inquiry retired (W4): inquiry letters now read from
                # collectors/china_filings.py → data/china_filings/filings.parquet
                # (category=='inquiry_letter'). china_inquiry.py is kept for history.
                ("collectors.china_preannounce", "refresh"),
                ("collectors.china_st",          "refresh"),
            ):
                try:
                    mod = importlib.import_module(mod_name)
                    getattr(mod, fn_name)()
                except Exception as e:  # noqa: BLE001
                    log.warning("build_china_special_situations: %s.%s failed (%s)", mod_name, fn_name, e)

        snap = css.build()   # writes site/chinaspecialdata/special.json
    else:
        snap = _read_committed_snapshot()
        if not snap:
            # Bail rather than bake the "warming up" shell over a good page — the
            # express lane must never be able to blank the desk.
            log.error("build_china_special_situations: --no-refresh has no snapshot to "
                      "render; leaving the baked desk untouched")
            return None

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

    # ---- tier gate (docs/TIER_PREVIEW_PATTERN.md) ---------------------------
    gated, preview_n = _gate_cfg()
    shell_snap, locked, gate = (snap or {}), {}, None
    if gated and snap:
        shell_snap, locked, gate = _split(snap, preview_n)

    # render with the shell snapshot (or empty dict so the template degrades gracefully)
    html = env.get_template("china_special_situations.html.j2").render(
        special=shell_snap or {}, gate=gate
    )
    write_page(site / "china_special_situations.html", html)
    _write_premium_payload(env, gate, snap or {}, locked)

    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            site_assets.copy_asset(a, src, site)

    log.info("wrote %s/china_special_situations.html (%d KB, gated=%s)",
             site, len(html) // 1024, bool(gate))
    return snap


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-refresh", action="store_true",
                    help="re-render page + payload from the committed special.json (render lane)")
    args = ap.parse_args()
    build(refresh=not args.no_refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
