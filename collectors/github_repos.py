"""GitHub repo-momentum collector — developer-adoption proxy for software/AI names.

For software/AI/robotics names a flagship open-source repo's star/fork VELOCITY is a non-price
read on developer mindshare. This snapshots stargazers/forks for curated repos
(data/github/repo_ticker.json), folds repos up to a ticker (its busiest repo), and stores a daily
snapshot so the engine can derive WoW star velocity (the github_momentum channel).

Source: GET https://api.github.com/repos/{owner}/{repo} (stargazers_count, forks_count). Works
keyless at 60 req/hr; a free GITHUB_TOKEN raises it to 5,000/hr. Output:
data/github/repo_stars.parquet — append-only daily snapshots. Degrades gracefully (rate-limit /
missing repo -> skip). Low-weight context channel.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

API = "https://api.github.com/repos"
PACE_S = 0.3


def _repo_map() -> dict[str, list[str]]:
    p = config.data_dir() / "github" / "repo_ticker.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("repos", {})
    except Exception:  # noqa: BLE001
        return {}


class GithubReposAdapter(Adapter):
    name = "github_repos"
    group = "github"
    stale_after_days = 3

    def __init__(self) -> None:
        self.token = config.secret("GITHUB_TOKEN")  # optional — anon 60/hr is enough for ~40 repos/day

    def _repo(self, full: str) -> dict | None:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = self.http_get(f"{API}/{full}", headers=headers, retries=2, timeout=30)
        return r.json()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        rmap = _repo_map()
        if not rmap:
            raise ValueError("github_repos: repo_ticker.json missing or empty")
        today = datetime.now(timezone.utc).date().isoformat()
        rows, errors = [], 0
        for ticker, repos in rmap.items():
            stars = forks = 0
            got = False
            for full in repos:
                try:
                    j = self._repo(full) or {}
                    s, f = int(j.get("stargazers_count") or 0), int(j.get("forks_count") or 0)
                    if s > stars:  # represent the ticker by its busiest repo
                        stars, forks = s, f
                    got = got or bool(j)
                    time.sleep(PACE_S)
                except Exception as e:  # noqa: BLE001
                    if is_connection_error(e):
                        raise
                    errors += 1
                    log.debug("github_repos %s/%s: %s", ticker, full, e)
                    continue
            if got and stars > 0:
                rows.append({"ticker": ticker, "stars": stars, "forks": forks, "snapshot_date": today})
        if not rows:
            raise RuntimeError(f"github_repos: no repos returned ({len(rmap)} tickers, {errors} errors)")
        new = pd.DataFrame(rows)
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / "github" / "repo_stars.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        combined = combined.drop_duplicates(subset=["ticker", "snapshot_date"], keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        log.info("github_repos: %d tickers @ %s, %d total rows, %d errors", len(rows), today, len(combined), errors)
        ingest = pd.DataFrame({"tickers": [len(rows)], "total_rows": [len(combined)]},
                              index=[pd.Timestamp(today)])
        return {"github_repos__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    GithubReposAdapter().fetch()
