"""Render the Capital Structure observed-filing-state desk.

The browser receives its issuer rows and filing evidence only through the
authenticated Capital Structure API. This builder deliberately writes no data
projection and never opens a storage artifact, with ONE exception (B-F09-4):
it reads the nightly-written `premium_featured.json` receipt so the desk can
show one classified deal's dated premium. That receipt is server-rendered into
the anonymously-fetchable HTML shell specifically because the page's live API
is paid-gated (`site_full` — app/capital_structure.py:53), so an API-delivered
premium could never be anonymously verified. The builder still writes no
projection of its own and still copies only `_ASSETS`.

Usage:
    python -m scripts.build_capital_structure_page
    python -m scripts.build_capital_structure_page --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
_ASSETS = ("capital_structure_boot.js", "capital_structure.css", "capital_structure.js")
_PREMIUM_RECEIPT = ("data", "special_situations", "premium_featured.json")


def _featured_premium(root: Path) -> dict | None:
    """Read the nightly premium receipt. Returns None when the receipt is absent,
    unreadable, or not the expected schema — the shell then prints its plain-word null."""
    path = root.joinpath(*_PREMIUM_RECEIPT)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != "special_situations.premium.v1":
        return None
    return payload


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(destination)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def render(root: Path) -> Path:
    """Write a data-free desk shell plus exact CSS/JS companions."""
    root = root.resolve()
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
        undefined=StrictUndefined,
    )
    html = env.get_template("capital_structure.html.j2").render(
        active_section="research",
        active_page="capital_structure",
        premium=_featured_premium(root),
    )
    # Shared navigation templates intentionally contain indentation around
    # conditional blocks. Normalize generated-only blank-line whitespace so the
    # committed shell remains diff-clean without modifying global nav output.
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    # write_page owns the depth-aware data-base shim. Use its result through a
    # temporary file so even a standalone builder cannot expose a partial page.
    from lib.pages import write_page  # noqa: PLC0415

    page = site / "capital_structure.html"
    temp = _temp_sibling(page)
    try:
        write_page(temp, html)
        os.replace(temp, page)
    finally:
        temp.unlink(missing_ok=True)
    for asset in _ASSETS:
        _atomic_copy(root / "templates" / asset, site / asset)
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        page = render(args.root)
    except Exception as exc:  # noqa: BLE001 — precise non-zero helps shared render diagnose a missing desk asset
        print(f"::error title=capital_structure_page::build failed ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
