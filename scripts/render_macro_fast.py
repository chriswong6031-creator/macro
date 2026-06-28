"""DEV-ONLY fast re-render of macro.html / us_stocks.html from a cached view-model.

A full `python -m scripts.build_site` is ~4 minutes. While iterating on the
dashboard template / CSS, that loop is too slow. This re-renders both dashboards
from a pickled view-model in well under a second.

Usage:
    # once: produce the cache (a normal full build, but it also dumps the VM)
    MACRO_DUMP_VM=1 python -m scripts.build_site
    # then, after every template/theme.css edit:
    python -m scripts.render_macro_fast
    cp templates/theme.css site/theme.css   # if you edited theme.css

The template + theme.css are re-read from disk on every run, so edits show up
immediately. This is NOT on the daily/commit path — build_site remains the source
of truth; this only re-renders using its last cached data.
"""
import pickle
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import i18n  # noqa: E402
from engine.i18n import td as _td  # noqa: E402
from engine.i18n import tr as _tr  # noqa: E402
from lib import config  # noqa: E402


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    cache = config.data_dir() / "_dev_macro_vm.pkl"
    if not cache.exists():
        print(f"no VM cache at {cache}\n"
              f"run once: MACRO_DUMP_VM=1 python -m scripts.build_site", file=sys.stderr)
        return 1
    with open(cache, "rb") as fh:
        blob = pickle.load(fh)
    vm = blob["vm"]

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    tmpl = env.get_template("dashboard.html.j2")

    for mode, name in (("macro", "macro.html"), ("stocks", "us_stocks.html")):
        out = site / name
        out.write_text(tmpl.render(**vm, mode=mode))
        print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    out = site / "news.html"
    out.write_text(env.get_template("news.html.j2").render(**vm))
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    out = site / "macro_signals.html"
    out.write_text(env.get_template("macro_signals.html.j2").render(**vm))
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
