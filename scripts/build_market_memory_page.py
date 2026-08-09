"""Render the data-free Market Memory shell to ``site/market_memory.html``.

All analytical reads remain behind the authenticated Market Memory API.  The
builder therefore needs no market artifacts and is deterministic in CI.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

log = logging.getLogger("build_market_memory_page")
_REPO_ROOT = Path(__file__).resolve().parent.parent


def render(root: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(str(Path(root) / "templates")),
        autoescape=True,
        undefined=Undefined,
    )
    return env.get_template("market_memory.html.j2").render()


def render_to_site(root: Path) -> Path:
    from lib.pages import write_page

    root = Path(root)
    output = root / "site" / "market_memory.html"
    write_page(output, render(root))
    log.info("wrote %s", output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Market Memory page")
    parser.add_argument("--root", default=None, help="Repository root")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    render_to_site(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
