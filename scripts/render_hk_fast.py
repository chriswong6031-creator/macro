"""DEV-ONLY fast re-render of hk.html / hk_stocks.html from a cached view-model.

A full `python -m scripts.build_hk` re-runs the HK collectors + engine (~10+ min).
While iterating on templates/hk.html.j2 / CSS that loop is far too slow. This
re-renders both HK dashboards from a pickled view-model in well under a second.

Usage:
    # once: produce the cache (a normal full build, but it also dumps the VM)
    HK_VM_DUMP=1 python -m scripts.build_hk
    # then, after every templates/hk.html.j2 edit:
    HK_FAST_RENDER=1 python -m scripts.render_hk_fast

The template is re-read from disk on every run, so edits show up immediately. This is
NOT on the daily/commit path — build_hk remains the source of truth; this only
re-renders using its last cached data. Re-run the HK_VM_DUMP build whenever the VM
shape changes (new context keys in build_hk.py).
"""
import pickle
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    cache = config.data_dir() / "_dev_hk_vm.pkl"
    if not cache.exists():
        print(f"no VM cache at {cache}\n"
              f"run once: HK_VM_DUMP=1 python -m scripts.build_hk", file=sys.stderr)
        return 1
    with open(cache, "rb") as fh:
        vm = pickle.load(fh)

    # Mirror build_hk.py's Jinja env exactly (autoescape=False + td/tr/t globals).
    env = Environment(loader=FileSystemLoader(
        str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    tmpl = env.get_template("hk.html.j2")

    for mode, name in (("macro", "hk.html"), ("stocks", "hk_stocks.html")):
        out = site / name
        write_page(out, tmpl.render(**vm, mode=mode))
        print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
