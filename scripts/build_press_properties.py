"""scripts/build_press_properties.py — build the W1.5 press property trees.

    python -m scripts.build_press_properties                    # build all
    python -m scripts.build_press_properties --publications news,research
    python -m scripts.build_press_properties --check            # drift check
    python -m scripts.build_press_properties --root /path/to/repo

Renders every publication in config/press.yml that carries a `property_tree`
(today: properties/news and properties/research) from the append-only press
ledger plus the .md archive.  This is the SAME renderer scripts/run_press.py
--emit calls in-lane; running it separately is how the front pages, feeds and
sitemaps get rebuilt after the ledger has moved — which is why
.github/workflows/press-publish.yml runs it immediately after the emit step.

It is safe to run at any time and on any checkout: it reads two committed
artifacts and writes only under the configured property trees.

--check renders into a temp directory and byte-compares against the committed
trees, exactly like `scripts/build_free_content --check` does for the estate.
That comparison is only possible because engine/press/properties.py reads no
wall clock: every timestamp on every page comes from the ledger or from
frontmatter, so a rebuild of an unchanged ledger is byte-identical.  Drift is
reported in both directions — a file the build did not produce is reported as
EXTRA rather than deleted, because the ledger is append-only and a file with no
row behind it is evidence of a hand edit, not garbage to sweep up.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import desk_planner, properties  # noqa: E402


def _annotate(level: str, title: str, message: str) -> None:
    """GitHub annotation.  Bare print, line-start, flushed — a logger would
    prefix the line and GitHub would silently drop it (house law)."""
    print(f"::{level} title={title}::{message}", flush=True)


def resolve_publications(cfg: dict, requested: str) -> list[str]:
    """Map the CLI's short names onto publication keys.

    `--publications news,research` is the ergonomic spelling an operator will
    actually type; the config keys are `mastermind_news` / `mastermind_research`.
    Both are accepted, and an unknown name is an error rather than a silent
    empty build — "it printed nothing" is not a report.
    """
    available = properties.publications_with_trees(cfg)
    names = [n.strip() for n in str(requested or "").split(",") if n.strip()]
    if not names:
        return available

    by_alias: dict[str, str] = {}
    for key in available:
        by_alias[key] = key
        if key.startswith("mastermind_"):
            by_alias[key[len("mastermind_"):]] = key

    out: list[str] = []
    unknown: list[str] = []
    for name in names:
        key = by_alias.get(name)
        if key is None:
            unknown.append(name)
        elif key not in out:
            out.append(key)
    if unknown:
        raise SystemExit(
            f"unknown publication(s): {', '.join(unknown)} — "
            f"available: {', '.join(sorted(by_alias))}"
        )
    return out


def _tree_files(tree: Path) -> set[str]:
    if not tree.exists():
        return set()
    return {str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file()}


def check(root: Path, cfg: dict, pub_keys: list[str]) -> int:
    """Byte-compare a fresh render against the committed trees.  0 == clean."""
    drifted: list[str] = []
    for key in pub_keys:
        committed = properties.property_tree_path(root, cfg, key)
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "tree"
            properties.render_property(root, cfg, key, dest=fresh)
            built = _tree_files(fresh)
            for rel in sorted(built):
                target = committed / rel
                if not target.exists():
                    drifted.append(f"MISSING in {committed.name}/: {rel}")
                elif target.read_bytes() != (fresh / rel).read_bytes():
                    drifted.append(f"DIFFERS in {committed.name}/: {rel}")
            for rel in sorted(_tree_files(committed) - built):
                drifted.append(f"EXTRA in {committed.name}/: {rel}")

    if drifted:
        print("DRIFT DETECTED — press property trees do not match a fresh build:",
              file=sys.stderr)
        for line in drifted:
            print(f"  {line}", file=sys.stderr)
        _annotate("error", "press_properties_drift",
                  f"press property trees drifted from a fresh build "
                  f"({len(drifted)} path(s)) — run "
                  f"`python -m scripts.build_press_properties` and commit the result")
        return 1
    print(f"press properties: no drift across {len(pub_keys)} publication(s)")
    return 0


def build(root: Path, cfg: dict, pub_keys: list[str]) -> int:
    total = 0
    for key in pub_keys:
        written = properties.render_property(root, cfg, key)
        total += len(written)
        tree = properties.property_tree_path(root, cfg, key)
        print(f"press properties: {key} -> {tree.relative_to(root)} "
              f"({len(written)} file(s))")
    _annotate("notice", "press_properties",
              f"press properties: built {len(pub_keys)} publication(s), "
              f"{total} file(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the per-publication press property trees (W1.5).")
    ap.add_argument("--publications", default="",
                    help="comma-separated publications (news, research, or the "
                         "full config keys). Default: every publication with a "
                         "property_tree.")
    ap.add_argument("--check", action="store_true",
                    help="render to a temp dir and byte-compare against the "
                         "committed trees; exit 1 on drift")
    ap.add_argument("--root", default="", help="repo root override (tests)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _REPO
    cfg = desk_planner.load_config(root)
    if not cfg:
        _annotate("error", "press_config",
                  "config/press.yml is missing or unparsable — cannot build press "
                  "properties")
        return 1

    pub_keys = resolve_publications(cfg, args.publications)
    if not pub_keys:
        _annotate("warning", "press_properties_none",
                  "no publication in config/press.yml carries a property_tree — "
                  "nothing to build")
        return 0

    return check(root, cfg, pub_keys) if args.check else build(root, cfg, pub_keys)


if __name__ == "__main__":
    sys.exit(main())
