"""DEV-ONLY fast re-render of china.html / china_stocks.html from a cached view-model.

A full `python -m scripts.build_china` re-runs the China collectors + engine (~10 min).
While iterating on templates/china.html.j2 / CSS that loop is far too slow. This
re-renders both China dashboards from a pickled view-model in well under a second.

Usage:
    # once: produce the cache (a normal full build, but it also dumps the VM)
    CHINA_VM_DUMP=1 python -m scripts.build_china
    # then, after every templates/china.html.j2 edit:
    python -m scripts.render_china_fast

The template is re-read from disk on every run, so edits show up immediately. This is
NOT on the daily/commit path — build_china remains the source of truth; this only
re-renders using its last cached data. Re-run the CHINA_VM_DUMP build whenever the VM
shape changes (new context keys in build_china.py).
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
    cache = config.data_dir() / "_dev_china_vm.pkl"
    if not cache.exists():
        print(f"no VM cache at {cache}\n"
              f"run once: CHINA_VM_DUMP=1 python -m scripts.build_china", file=sys.stderr)
        return 1
    with open(cache, "rb") as fh:
        vm = pickle.load(fh)

    # Mirror build_china.py's Jinja env exactly (autoescape=False + td/tr/t globals).
    env = Environment(loader=FileSystemLoader(
        str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    tmpl = env.get_template("china.html.j2")

    for mode, name in (("macro", "china.html"), ("stocks", "china_stocks.html")):
        out = site / name
        write_page(out, tmpl.render(**vm, mode=mode))
        print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
