"""Render the data-free BioCatalyst Intelligence workbench shell.

Clinical-trial facts are intentionally *not* baked into ``site/``.  The page
loads its current, verified ClinicalTrials.gov projection only from the
same-origin, site-full-protected BioCatalyst API at runtime.  That keeps a
registered preview useful without turning a static render or the public git
tree into a trial-data distribution channel.

Usage::

    python -m scripts.build_biocatalyst
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_copy(source: Path, destination: Path) -> None:
    """Copy a public shell asset without exposing a partial browser response."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(destination)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def render_shell(root: Path) -> Path:
    """Atomically render the static shell and its paired client assets only."""
    root = Path(root)
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    html = env.get_template("biocatalyst.html.j2").render(
        generated_utc="runtime-api",
        active_section="research",
        active_page="biocatalyst",
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    page = site / "biocatalyst.html"
    page_temp = _temp_sibling(page)
    try:
        write_page(page_temp, html)
        os.replace(page_temp, page)
    finally:
        page_temp.unlink(missing_ok=True)

    for name in ("biocatalyst.css", "biocatalyst.js"):
        _atomic_copy(root / "templates" / name, site / name)
    return page


def render_from_state(root: Path) -> Path:
    """Compatibility hook for the main renderer; no state is read or emitted."""
    return render_shell(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=config.ROOT)
    args = parser.parse_args(argv)
    page = render_shell(args.root)
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
