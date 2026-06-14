"""Translate the single-stock analyzer's company blurbs to 简体中文 — CACHED + idempotent.

The "Business profile" description on stock.html is sourced English free text
(Wikipedia/SEC, via collectors/equity_profile.py → data/profile/profiles.parquet).
It can't be dual-emitted like the rest of the i18n, so this OPTIONAL job machine-
translates it once via engine.translate (DeepSeek/Anthropic, gated) and caches the
result in data/profile/descriptions_zh.parquet keyed by ticker + a hash of the English.

Idempotent + cheap: only NEW or CHANGED descriptions hit the API; a failed item simply
stays English and is retried next run. _load_profiles() joins this cache so the analyzer
can `lz(description, description_zh)`. No key / disabled ⇒ clean no-op (English stays).

Usage:  python -m scripts.translate_profiles   (needs the configured api_key_env set, e.g.
        DEEPSEEK_API_KEY in .env)
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import translate  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("translate_profiles")

CACHE_NAME = "descriptions_zh.parquet"


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_cache(path: Path) -> dict[str, dict]:
    """ticker -> {en_hash, description_zh}. Empty / best-effort (a corrupt cache must not
    block a build; it just means everything re-translates)."""
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("cache unreadable (%s) — starting fresh", e)
        return {}
    out: dict[str, dict] = {}
    for t, row in df.iterrows():
        out[str(t)] = {"en_hash": str(row.get("en_hash", "")),
                       "description_zh": row.get("description_zh")}
    return out


def main() -> int:
    cfg = config.load().get("profile_translation", {})
    prof_path = config.data_dir() / "profile" / "profiles.parquet"
    cache_path = config.data_dir() / "profile" / CACHE_NAME
    if not prof_path.exists():
        log.info("no profiles.parquet — nothing to translate")
        return 0
    if not translate.is_enabled(cfg):
        log.info("profile_translation disabled or no %s key — skipping (blurbs stay English)",
                 cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
        return 0

    df = pd.read_parquet(prof_path)
    if "description" not in df.columns:
        log.info("profiles.parquet has no description column — nothing to translate")
        return 0

    cache = load_cache(cache_path)
    # which descriptions are new or changed since we last translated them?
    todo: list[tuple[str, str, str]] = []  # (ticker, english, en_hash)
    current_hashes: dict[str, str] = {}
    for t, row in df.iterrows():
        en = row["description"]
        if not isinstance(en, str) or not en.strip():
            continue
        t = str(t)
        h = _hash(en)
        current_hashes[t] = h
        hit = cache.get(t)
        if hit and hit.get("en_hash") == h and hit.get("description_zh"):
            continue  # already translated this exact text
        todo.append((t, en, h))

    log.info("%d blurbs total · %d already cached · %d to translate",
             len(current_hashes), len(current_hashes) - len(todo), len(todo))
    if todo:
        zh = translate.translate_to_zh([en for _, en, _ in todo], cfg)
        ok = 0
        for (t, _en, h), z in zip(todo, zh):
            if z:
                cache[t] = {"en_hash": h, "description_zh": z}
                ok += 1
        log.info("translated %d/%d (the rest stay English, retried next run)", ok, len(todo))

    # rebuild the cache frame from whatever we now hold (prune tickers no longer in profiles)
    rows = [{"ticker": t, "en_hash": v["en_hash"], "description_zh": v["description_zh"]}
            for t, v in cache.items() if t in current_hashes and v.get("description_zh")]
    if rows:
        out = pd.DataFrame(rows).set_index("ticker")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path)
        log.info("wrote %s (%d cached translations)", cache_path, len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
