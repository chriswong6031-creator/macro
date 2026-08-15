"""Keep-first, first_seen evidence-store helpers — the house PIT write contract.

This is NOT a new dialect. It is the write path already used by
``collectors/china_trade_detail.write_rows`` (keep-FIRST on identity so a later
vendor revision cannot silently replace the first vintage) plus the
``first_seen`` / atomic-replace / abort-if-unreadable discipline from
``collectors/china_holder_counts``.

``collectors/_drip.append_snapshot`` is a different contract (keep-LAST per
session date, no first_seen). Do not use it for evidence studies.

Contract:
  * append-only across keys
  * keep-FIRST on the identity key — the first payload wins in full
  * ``first_seen`` is immutable (restored from the existing store)
  * a present-but-unreadable store ABORTS rather than being replaced
  * writes go through a tmp sibling + os.replace
  * idempotent: a duplicated fetch returns 0 net-new and does not multiply rows
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

log = logging.getLogger("first_seen_store")

SCHEMA_VERSION = 1
_EMPTY_FIRST_SEEN = ("", "nan", "None", "NaT", "<NA>")


def read_store(path: Path, columns: tuple[str, ...]) -> pd.DataFrame | None:
    """Canonical-schema frame when ABSENT (empty), None when PRESENT but UNREADABLE.

    Three facts, same as china_holder_counts._read_store: "absent" is the first
    night (seed freely); "present but unreadable" means accrued history is still
    on disk and we cannot see it — taking the empty-store branch would replace
    it with tonight's buffer. The caller ABORTS on None.
    """
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        return pd.read_parquet(path).reindex(columns=list(columns))
    except Exception as e:  # noqa: BLE001
        log.error("first_seen_store: %s is present but UNREADABLE (%s)", path.name, e)
        return None


def atomic_write(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` via a tmp sibling + os.replace — never a truncated store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — never leave a half-written sibling behind
        tmp.unlink(missing_ok=True)
        raise


def restore_first_seen(merged: pd.DataFrame, existing: pd.DataFrame,
                       key: list[str]) -> pd.DataFrame:
    """Carry each key's ORIGINAL first_seen through a merge. Pure.

    Keys absent from ``existing`` keep tonight's stamp. Empty / NaN prior stamps
    do not overwrite a real one.
    """
    if existing.empty or "first_seen" not in existing.columns:
        return merged
    prior = existing[[*key, "first_seen"]].astype(str)
    prior = prior[prior["first_seen"].str.strip().ne("")
                  & ~prior["first_seen"].isin(_EMPTY_FIRST_SEEN)]
    if prior.empty:
        return merged
    prior = prior.sort_values("first_seen").drop_duplicates(subset=key, keep="first")
    lookup = dict(zip(zip(*(prior[c] for c in key)), prior["first_seen"]))
    out = merged.copy()
    out["first_seen"] = [
        lookup.get(k, cur)
        for k, cur in zip(zip(*(out[c].astype(str) for c in key)), out["first_seen"])
    ]
    return out


def accrue_keep_first(
    path: Path,
    rows: list[dict] | pd.DataFrame,
    *,
    columns: tuple[str, ...],
    key: list[str],
    sort_by: list[str] | None = None,
) -> int:
    """Append ``rows`` keep-FIRST on ``key``. Returns the count of net-new keys.

    Never raises on the collector path: a store failure is logged and the night
    degrades to 0 net-new. An existing-but-UNREADABLE store ABORTS (returns 0,
    file left in place) rather than being replaced by tonight's buffer.
    """
    if rows is None:
        return 0
    new_df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if new_df is None or new_df.empty:
        return 0
    try:
        existing = read_store(path, columns)
        if existing is None:
            log.error("first_seen_store: ABORTING the %s append — the accrued store "
                      "is unreadable and is left untouched for manual recovery",
                      path.name)
            return 0
        new_df = new_df.reindex(columns=list(columns))
        if "first_seen" in new_df.columns and "fetched_at" in new_df.columns:
            new_df["first_seen"] = new_df["first_seen"].fillna(new_df["fetched_at"])
        for c in key:
            new_df[c] = new_df[c].fillna("").astype(str)
        if existing.empty:
            merged = new_df.drop_duplicates(subset=key, keep="first")
            net_new = len(merged)
        else:
            for c in key:
                existing[c] = existing[c].fillna("").astype(str)
            pre = len(existing.drop_duplicates(subset=key))
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=key, keep="first")
            merged = restore_first_seen(merged, existing, key)
            net_new = len(merged) - pre
        order = sort_by or list(key)
        order = [c for c in order if c in merged.columns]
        if order:
            merged = merged.sort_values(order, kind="stable").reset_index(drop=True)
        else:
            merged = merged.reset_index(drop=True)
        atomic_write(merged, path)
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("first_seen_store.accrue_keep_first(%s) failed: %s", path, e)
        return 0
