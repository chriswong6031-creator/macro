"""ONE-SHOT: seed china/hk market-state score logs from git-history nightly prints.

The mx5 hero "11-session path" reads data/<mkt>_market_state/score_log.parquet,
which only started accruing when the score-log append shipped (china 2026-07-15,
hk never — the block landed 2026-07-16 23:00Z, after that day's asia-close run).
But build_china/build_hk have baked the SAME market-state score into their pages
every asia-close night since 2026-06-28 (#650/#657) — so the honest point-in-time
prints already exist in git, one per nightly "engine: asia dashboards" commit.

This recovers them: walk those commits, extract the baked score/date/color from
site/china.html and site/hk.html, and merge into the score logs. Rows already
accrued by the nightly lane always win over recovered rows for the same date.
Recovered rows carry source="git_backfill" for provenance; lane-accrued rows
have no source value.

NOT on any lane — run once by hand, commit the parquets, delete nothing:
    python -m scripts.backfill_ms_score_log_from_git          # dry-run census
    python -m scripts.backfill_ms_score_log_from_git --write  # write parquets
"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

# color -> verdict enum, same map as templates/risk_state_live.js COLOR (inverted)
_VERDICT = {"green": "RISK_ON", "yellow": "MIXED", "red": "RISK_OFF"}

_RE_SCORE = re.compile(r'id="ms-score"[^>]*>(\d+)<')
_RE_DATE = re.compile(r'id="ms-date"[^>]*>[^<]*?(\d{4}-\d{2}-\d{2})')
# hero color: old shared board era `ms-front ms ms-red`, mx5 era `ms-front ms-red`
_RE_COLOR = re.compile(r'ms-front (?:ms )?ms-(green|yellow|red)')


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=config.ROOT, check=True).stdout


def _asia_commits(page: str) -> list[str]:
    """Nightly asia-close commits touching site/<page>, oldest first."""
    out = _git("log", "--format=%H|%s", "--", f"site/{page}")
    shas = [line.split("|", 1)[0] for line in out.splitlines()
            if line.split("|", 1)[1].startswith("engine: asia dashboards")]
    return list(reversed(shas))


def _recover(page: str) -> list[dict]:
    rows: dict[str, dict] = {}
    for sha in _asia_commits(page):
        try:
            html = _git("show", f"{sha}:site/{page}")
        except subprocess.CalledProcessError:
            continue
        m_score, m_date = _RE_SCORE.search(html), _RE_DATE.search(html)
        m_color = _RE_COLOR.search(html)
        if not (m_score and m_date and m_color):
            print(f"  {sha[:11]} {page}: no baked score panel — skipped")
            continue
        date, score, color = m_date.group(1), int(m_score.group(1)), m_color.group(1)
        # first print for a session wins (a later commit re-baking the same date
        # would be a stale page carried forward, not a fresh nightly print)
        if date not in rows:
            rows[date] = {"date": date, "score": score, "color": color,
                          "verdict": _VERDICT[color], "source": "git_backfill"}
    return [rows[d] for d in sorted(rows)]


def main() -> int:
    write = "--write" in sys.argv
    for mkt, page, cols in (
        ("china", "china.html", ["date", "score", "verdict", "color", "source"]),
        ("hk", "hk.html", ["date", "score", "source"]),
    ):
        recovered = _recover(page)
        df_new = pd.DataFrame(recovered)[cols] if recovered else pd.DataFrame(columns=cols)
        if mkt == "hk" and not df_new.empty:
            df_new["score"] = df_new["score"].astype(float)  # lane writes float rows
        path = config.data_dir() / f"{mkt}_market_state" / "score_log.parquet"
        if path.exists():
            existing = pd.read_parquet(path)
            merged = pd.concat([df_new, existing], ignore_index=True)
            # keep="last" -> lane-accrued rows (concatenated after) win on date clash
            merged = merged.drop_duplicates(subset=["date"], keep="last")
        else:
            merged = df_new
        merged = merged.sort_values("date").reset_index(drop=True)
        print(f"\n== {mkt}: {len(recovered)} recovered, {len(merged)} total ==")
        print(merged.to_string())
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            merged.to_parquet(path, index=False)
            print(f"wrote {path}")
    if not write:
        print("\nDRY-RUN — pass --write to persist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
