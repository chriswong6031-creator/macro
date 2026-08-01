"""Build the Government Revenue Foresight desk.

The page is a static, client-rendered evidence terminal backed by the compact
``company_government_revenue.v1`` artifact.  The deterministic domain engine is
the only place calculations live; this builder only serializes the payload and
renders the shell.

Missing award/action detail is an honest degraded state, not a build failure:
the monthly USAspending aggregate still renders while the page marks capacity,
modification, and recompete fields unavailable.

Usage::

    python -m scripts.build_government_revenue
    python -m scripts.build_government_revenue --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue import build_payload  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_government_revenue")


def build(root: Path, *, as_of: str | None = None) -> tuple[Path, Path, Path]:
    """Build canonical JSON, its site twin, and the HTML page."""
    root = root.resolve()
    payload = build_payload(root=root, as_of=as_of)
    if not isinstance(payload, dict) or payload.get("schema_version") != "company_government_revenue.v1":
        raise ValueError("government revenue engine returned an invalid schema")

    canonical_dir = root / "data" / "government_revenue"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = canonical_dir / "latest.json"

    site_dir = root / "site"
    data_dir = site_dir / "government-revenue-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / "latest.json"
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    canonical_path.write_text(raw, encoding="utf-8")
    json_path.write_text(raw, encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    html = env.get_template("government_revenue.html.j2").render(
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        as_of=payload.get("as_of"),
        known_at=payload.get("known_at"),
    )
    # Shared includes predate the repository's whitespace gate. Keep this new
    # generated artifact deterministic and diff-clean without rewriting them.
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    html_path = site_dir / "government_revenue.html"
    write_page(html_path, html)
    log.info(
        "wrote %s, %s and %s (%d companies)",
        html_path,
        canonical_path,
        json_path,
        len(payload.get("companies") or []),
    )
    return html_path, canonical_path, json_path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build Government Revenue Foresight")
    parser.add_argument("--root", default=str(_ROOT))
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)
    try:
        build(Path(args.root), as_of=args.as_of)
    except Exception as exc:  # noqa: BLE001
        log.error("government revenue build failed: %s", exc, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
