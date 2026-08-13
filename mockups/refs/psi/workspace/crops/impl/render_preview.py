"""Render templates/watchlist.html.j2 into the worktree's site/ as a scratch preview.

Not part of the build — this exists so the W2 visual gate shoots the REAL template
through the REAL page scripts, with the same three globals scripts/build_site.py
injects. The output file is untracked and deleted before commit.
"""
import json, pathlib, re, sys

ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/wp-w2-flagship-shell"
sys.path.insert(0, ROOT)
from jinja2 import Environment, FileSystemLoader  # noqa: E402
from engine.cycles import STATE_DISPLAY  # noqa: E402

env = Environment(loader=FileSystemLoader(ROOT + "/templates"), autoescape=False)
html = env.get_template("watchlist.html.j2").render(
    generated_utc="2026-08-12 14:00",
    state_display_json=json.dumps(STATE_DISPLAY),
    supabase_cfg_json="null",
    wri_regime_json=json.dumps({
        "state": "calm",
        "dominant_label_en": "Liquidity easing",
        "dominant_label_zh": "流动性宽松",
        "asof": "2026-08-12",
    }),
    starters_json=json.dumps(["NVDA", "MSFT", "GLD", "TLT"]),
)
# CACHEBUST: the page ships hand-authored ?v=N stamps, so a browser that already
# loaded v=N keeps the stale body across renders. The preview appends a per-render
# token so every shoot sees the file just written. Preview-only.
import time
_tok = str(int(time.time()))
html = re.sub(r'(src|href)="([a-z_0-9.]+\.(?:js|css))(\?v=\d+)?"',
              lambda m: '%s="%s?cb=%s"' % (m.group(1), m.group(2), _tok), html)

# the seed helper loads FIRST so a crop can set up its book before the page scripts run
html = html.replace("<head>", '<head>\n<script src="__w2seed.js"></script>', 1)

out = pathlib.Path(ROOT) / "site" / "__w2preview.html"
out.write_text(html)
print("rendered", len(html), "bytes ->", out)

# ANONYMOUS variant — the four account-gated scripts are REMOVED, not disabled. That
# is exactly what production does: config/site_access.yml keeps stockdata.js,
# watchlist_risk.js, risk_core.js and factor_exposure.js off the public plane, so
# their tags 401 and never execute. Reproducing the wall (rather than faking it with
# a flag) is what makes the anonymous crops evidence.
GATED = ["stockdata.js", "watchlist_risk.js", "risk_core.js", "factor_exposure.js"]
anon = html
for g in GATED:
    anon = re.sub(r'<script src="%s[^"]*"></script>\n?' % re.escape(g), "", anon)
for g in GATED:
    assert ('src="%s' % g) not in anon, g
outa = pathlib.Path(ROOT) / "site" / "__w2preview_anon.html"
outa.write_text(anon)
print("rendered anon", len(anon), "bytes ->", outa)
