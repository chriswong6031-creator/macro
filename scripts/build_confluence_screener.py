"""scripts.build_confluence_screener — render the free signal-stack screener page + og:image card.

Reads site/factordata/tech_confluence.json.
Writes site/confluence_screener.html and site/og/confluence_screener.png.

Usage:
    python -m scripts.build_confluence_screener
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# CTA URL
# ─────────────────────────────────────────────────────────────────────────────

def _cta_url() -> str:
    # TODO(D07): route through engine/marketing/links.py tagged CTA builder once D07 merges (campaign=confluence_screener).
    return "https://app.mastermind-x.com/"


# ─────────────────────────────────────────────────────────────────────────────
# build_context — pure function, testable
# ─────────────────────────────────────────────────────────────────────────────

def build_context(raw: dict | None, name_map: dict) -> dict:
    """Build the Jinja context dict from the tech_confluence artifact.

    GATING LAW: gated combos (rank 2 and 3) MUST NOT expose tickers in the
    context. Only rank-1 (`is_free=True`) receives `active_tickers`. For gated
    combos only `len(c["active_now"])` is called — the ticker list is discarded.
    """
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if raw is None:
        return {
            "generated_utc": generated_utc,
            "asof": None,
            "universe_n": 0,
            "split_date": "2018-01-01",
            "n_active_total": 0,
            "combos": [],
            "cta_url": _cta_url(),
        }

    # Derive asof from generated_utc field in artifact
    artifact_utc = raw.get("generated_utc")
    asof: str | None = None
    if artifact_utc:
        try:
            asof = str(artifact_utc)[:10]
        except Exception:  # noqa: BLE001
            asof = None

    universe_n = raw.get("universe_n", 0) or 0
    split_date = raw.get("split_date") or "2018-01-01"

    # Filter long combos: non-empty active_now AND non-null h21.wr_mc_test and h21.wr_mc_train
    longs = (raw.get("combos") or {}).get("long") or []
    legs_list = raw.get("legs") or []

    eligible: list[dict] = []
    for c in longs:
        if not c.get("active_now"):
            continue
        h21 = c.get("h21") or {}
        if h21.get("wr_mc_test") is None or h21.get("wr_mc_train") is None:
            continue
        eligible.append(c)

    n_active_total = len(eligible)

    # Sort by rank_score descending, take top 3
    eligible_sorted = sorted(eligible, key=lambda x: x.get("rank_score", 0), reverse=True)
    top3 = eligible_sorted[:3]

    combos: list[dict] = []
    for rank_idx, c in enumerate(top3):
        rank = rank_idx + 1
        is_free = (rank == 1)
        h21 = c.get("h21") or {}

        # Build legs from the legs_list using the combo's leg indices
        leg_indices = c.get("legs") or []
        legs_built = []
        for li in leg_indices:
            try:
                leg_data = legs_list[li]
                legs_built.append({
                    "en": leg_data.get("display_en", ""),
                    "zh": leg_data.get("display_zh", ""),
                    "tf": leg_data.get("tf", "D"),
                })
            except (IndexError, TypeError):
                continue

        # GATING LAW: only rank-1 exposes active_tickers
        active_now = c.get("active_now") or []
        if is_free:
            active_tickers = [
                {"ticker": t, "name": name_map.get(t, "")}
                for t in active_now
            ]
        else:
            # Gated: call len() only, never iterate tickers into the context
            active_tickers = []

        combo_entry = {
            "rank": rank,
            "combo_id": c.get("id", ""),
            "name_en": c.get("name_en", ""),
            "name_zh": c.get("name_zh", ""),
            "legs": legs_built,
            "wr_test_pct": (h21.get("wr_mc_test") or 0) * 100,
            "wr_train_pct": (h21.get("wr_mc_train") or 0) * 100,
            "n_test": h21.get("n_test") or 0,
            "months_test": h21.get("months_test") or 0,
            "n_train": h21.get("n_train") or 0,
            "months_train": h21.get("months_train") or 0,
            "n_fires": c.get("n_fires") or 0,
            "first_fire": c.get("first_fire") or "",
            "last_fire": c.get("last_fire") or "",
            "fires_per_year": c.get("fires_per_year") or 0.0,
            "edge_test_pp": (c.get("edge_wr_test") or 0) * 100,
            "consistent": bool(c.get("consistent")),
            "is_free": is_free,
            "active_count": len(active_now),
            "active_tickers": active_tickers,
        }
        combos.append(combo_entry)

    return {
        "generated_utc": generated_utc,
        "asof": asof,
        "universe_n": universe_n,
        "split_date": split_date,
        "n_active_total": n_active_total,
        "combos": combos,
        "cta_url": _cta_url(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# render_html — pure Jinja render
# ─────────────────────────────────────────────────────────────────────────────

def render_html(root: Path, ctx: dict) -> str:
    """Render confluence_screener.html.j2 with the given context. Pure."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n  # noqa: PLC0415

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    tpl = env.get_template("confluence_screener.html.j2")
    return tpl.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# render — I/O entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def render(root: Path) -> None:
    """Load artifact, build context, write page and share card."""
    t0 = time.perf_counter()

    # Load artifact (fail-soft)
    artifact_path = root / "site" / "factordata" / "tech_confluence.json"
    raw: dict | None = None
    if artifact_path.exists():
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = None
        except Exception:  # noqa: BLE001
            raw = None

    # Load name_map from sp500_heatmap.json.
    # Actual structure: top-level "tiles" list with {t, name, ...} entries.
    # (The spec says "sectors[].tiles[]" but the file has a flat top-level "tiles" array.)
    name_map: dict[str, str] = {}
    heatmap_path = root / "site" / "marketdata" / "sp500_heatmap.json"
    if heatmap_path.exists():
        try:
            heatmap = json.loads(heatmap_path.read_text(encoding="utf-8"))
            if isinstance(heatmap, dict):
                tiles = heatmap.get("tiles") or []
                for tile in tiles:
                    t_sym = tile.get("t")
                    t_name = tile.get("name")
                    if t_sym and t_name:
                        name_map[t_sym] = t_name
        except Exception:  # noqa: BLE001
            pass

    ctx = build_context(raw, name_map)

    # Render HTML
    html = render_html(root, ctx)

    from lib.pages import write_page  # noqa: PLC0415
    write_page(root / "site" / "confluence_screener.html", html)

    # Share card (only when combos present)
    combos = ctx.get("combos") or []
    if combos:
        try:
            from engine.marketing.share_cards import render_screener_card, save_card  # noqa: PLC0415
            top = combos[0]
            asof = ctx.get("asof") or ""
            # wr_test_per10: convert win-rate-pct to "X.X" wins-per-10
            wr_test_pct = top.get("wr_test_pct", 0)
            wr_test_per10 = f"{wr_test_pct / 10:.1f}"
            img = render_screener_card(
                asof=asof,
                combo_headline=top.get("name_en", ""),
                wr_test_per10=wr_test_per10,
                n_fires=top.get("n_fires", 0),
                first_year=(top.get("first_fire") or "")[:4],
                active_count=top.get("active_count", 0),
            )
            card_out = root / "site" / "og" / "confluence_screener.png"
            save_card(img, card_out)
        except Exception:  # noqa: BLE001
            pass  # card failure is non-fatal; page was already written

    elapsed = time.perf_counter() - t0
    print(f"[confluence_screener] page+card in {elapsed:.1f}s (combos={len(combos)})")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        render(_ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=confluence_screener::{exc}")
        sys.exit(0)


if __name__ == "__main__":
    main()
