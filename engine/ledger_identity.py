"""Ticker-rename identity for the append-only per-ticker ledgers.

WHY THIS EXISTS (2026-08-12 — the EchoStar double count)
--------------------------------------------------------
A ticker STRING is not a stable identity, and the ledgers under
``data/signal_archive/`` are keyed on one: ``(ticker, date, type)``. When a company
renames, the new string is a key with NO logged history — so every guard that asks
"have I logged this before?" answers no, and the same physical fires are appended a
SECOND time under the new name. Append-only turns that into a permanent
over-weighting rather than a migration.

Measured on ``data/signal_archive/track_record.parquet`` (2026-08-12; 58,660 rows,
247 tickers). EchoStar Corporation renamed SATS->ECHO effective 2026-06-24. The
bare-string price fetch minted ``data/stocks/ECHO.parquet`` holding EchoStar's FULL
spliced history back to 2008; ``build_signal_quality`` rendered
``site/signals/ECHO.json`` carrying the same 112 markers as ``SATS.json``; and the
2026-06-29 ledger build (55,404 of the ledger's rows carry that
``first_seen_asof``) walked BOTH files in ONE pass. Result:

  * SATS 128 rows, ECHO 128 rows;
  * ``(date, type)`` key sets IDENTICAL — same 2008-11-25 -> 2026-04-23 span,
    zero SATS-only keys, zero ECHO-only keys;
  * all 39 identity/entry columns byte-identical (same ``entry_price``, same
    ``first_seen_asof`` 2026-06-29, same quality/reason/species_id/archetype/
    anchor_era) — conclusive that these are one physical fire logged twice;
  * only maturation diverges, and ONLY in ECHO's favour (``fwd_ret_60`` nulls
    SATS 2 / ECHO 0; ``fwd_ret_180`` nulls SATS 4 / ECHO 3), because
    ``data/stocks/SATS.parquet`` no longer exists and SATS is absent from the
    dead-name registry, so ``_load_close('SATS')`` resolves nothing and the SATS
    copies can never mature again.

Every per-row statistic over the ledger — hit rate, forward-return and drawdown
distributions, the published track-record surface, the spine/personality readers —
weights EchoStar TWICE. This is NOT the survivorship trap (a missing name); it is a
live OVER-weighting of a present one.

WHY THE EXISTING GUARDS CANNOT SEE IT
-------------------------------------
* ``engine.track_record._blocked_by_era_floor`` (R-SQ8) is the ledger's duplication
  guard, and it is scoped per-ticker-STRING: it refuses a pre-floor key only for a
  ticker that ALREADY HAS logged rows. A renamed ticker has none — it reads as "a
  fresh build, or a newly covered name" and the whole re-dated history is admitted.
  On 2026-06-29 the case was even harder: BOTH strings were new in the SAME run, and
  ``_era_index`` is snapshotted BEFORE ingestion by design, so neither could see the
  other no matter what the floor value was.
* ``scripts/audit_reused_tickers.py`` owns the identity doctrine and the ratified
  acks — but it audits the per-ticker price STORES (``data/stocks/``,
  ``data/baskets/ohlcv/``) and has no view of any ledger. Acking ECHO silenced the
  store alarm; nothing downstream ever asked what the rename did to the ledgers.
* The ack text itself IS the key-migration record the house law requires
  (``ticker-rename-is-a-key-migration``, #4622) — but it is PROSE. Nothing could
  read "under its 2026-06-24 SATS->ECHO rename" and act on it.

This module is the missing machine-readable half: ``quality.ticker_key_migrations``
in ``config.yml`` (old key -> the key the stack now stores the entity under), plus
the detector and the resolution helpers that read it.

WHERE THIS SEAM IS *NOT*
------------------------
* NOT ``lib/ticker_aliases`` — its own docstring forbids it: "NOT a display map.
  Site copy, page slugs and ledger keys keep the membership ticker; this only ever
  decides what string goes to the vendor." That is the VENDOR boundary.
* NOT ``sp500.ticker_fixups`` — same relation ("one join key per company"), but
  scoped to the S&P 500 constituent scrape. Its comment states this module's law
  exactly: "flipping the key splits a company's history across two symbols … That
  flip is a migration, not an edit."
* NOT ``config/theme_graph_identity_breaks.yml`` — that records identity BREAKS
  (one symbol, two different companies: the node must SPLIT). This records identity
  CONTINUATIONS (two symbols, one company: the keys must MERGE). Opposite relations;
  both curated, never detector-written.

DETECTORS PROPOSE, CURATION RATIFIES (mirroring the identity-breaks doctrine): the
undeclared-duplicate scan below produces CANDIDATES. It never writes the map, and a
candidate is not an identity until an operator writes the row with its evidence.

Dependencies: pandas ONLY. Python 3.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

import pandas as pd

logger = logging.getLogger(__name__)

#: The ledger key. Mirrors ``engine.track_record._KEY``.
KEY_COLS = ("ticker", "date", "type")

#: An identical ``(date, type)`` key set shared by two DIFFERENT tickers is an identity
#: claim once it is this large; below it, it is coincidence — two names in the same
#: sector firing on the same day.
#:
#: Measured separation on the 2026-08-12 ledger (247 tickers, exhaustive pairwise scan):
#: exactly TWO groups share an identical key set — AMCX/SSP at **1** key (two media names
#: that happened to fire once on the same date; unrelated issuers) and SATS/ECHO at
#: **128** (the EchoStar rename). Nothing sits in between. The nearest non-identical
#: near-miss is GOOG/GOOGL at Jaccard 0.769 — genuinely two instruments (two share
#: classes, different prices, different forward returns), and it must NEVER trip this:
#: the signature is EXACT key-set equality, not overlap.
MIN_IDENTICAL_KEYS = 5

#: Columns recording WHEN THIS LEDGER DID SOMETHING, not what the market did.
#:
#: Two copies of one physical fire legitimately disagree here — they were written and
#: re-visited by different nightly runs — so a divergence is NOT evidence that the two
#: keys are different entities, and it must not veto a key migration. Measured on the
#: SATS/ECHO pair: the ONLY cells that disagree at all are three `last_backfill_asof`
#: stamps (SATS frozen at 2026-06-29 because its price store is gone; ECHO still
#: advancing, 2026-07-07/2026-07-15). Every measured cell — entry price, regime, forward
#: returns, drawdowns, exits — is byte-identical.
#:
#: Kept deliberately SHORT and enumerated, never a pattern: a column that records a
#: measurement must always be able to veto a merge, and the way that protection rots is
#: by someone widening this tuple. Divergences here are still REPORTED
#: (`provenance_divergences`), just not treated as identity evidence.
PROVENANCE_COLS = ("first_seen_asof", "last_backfill_asof")


# ---------------------------------------------------------------------------
# The ratified map
# ---------------------------------------------------------------------------

def load_migrations(quality_raw: Mapping[str, Any] | None = None) -> dict[str, str]:
    """``{superseded ticker: current ticker}`` from ``quality.ticker_key_migrations``.

    ``quality_raw`` injects the raw config ``quality:`` block (tests); None reads
    ``config.yml``. Chains are resolved transitively (``{A: B, B: C}`` -> ``A``
    and ``B`` both resolve to ``C``), so a name renamed twice still lands on one key.

    Never raises for a config issue: a malformed entry is dropped with a warning and
    the rest of the map still loads. A map that cannot be read at all yields ``{}`` —
    which degrades every caller to today's per-string behaviour (disclosure goes
    dark, ingest stops de-duplicating), never to a crash.
    """
    if quality_raw is None:
        try:
            from lib import config  # local import: keeps this module import-light
            quality_raw = config.load().get("quality") or {}
        except Exception as exc:  # noqa: BLE001 — absence degrades, never crashes
            logger.warning("[ledger_identity] config unreadable (%s) — no migrations", exc)
            return {}
    raw = (quality_raw or {}).get("ticker_key_migrations") or {}
    if not isinstance(raw, Mapping):
        logger.warning("[ledger_identity] ticker_key_migrations is not a mapping — ignored")
        return {}

    direct: dict[str, str] = {}
    for old, new in raw.items():
        old_s, new_s = str(old).strip().upper(), str(new).strip().upper()
        if not old_s or not new_s or old_s == new_s:
            logger.warning("[ledger_identity] dropping degenerate migration %r -> %r", old, new)
            continue
        direct[old_s] = new_s

    resolved: dict[str, str] = {}
    for old in direct:
        seen = {old}
        cur = direct[old]
        while cur in direct:
            if cur in seen:  # cycle: refuse the whole chain rather than loop forever
                logger.warning("[ledger_identity] migration cycle at %r — chain dropped", cur)
                cur = None
                break
            seen.add(cur)
            cur = direct[cur]
        if cur:
            resolved[old] = cur
    return resolved


def current_key(ticker: str, migrations: Mapping[str, str]) -> str:
    """The key ``ticker`` is stored under today (identity when not superseded)."""
    return migrations.get(str(ticker).strip().upper(), ticker)


def superseded_keys(migrations: Mapping[str, str]) -> set[str]:
    """Every ticker string that is no longer a valid ledger key."""
    return set(migrations)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _key_sets(df: pd.DataFrame) -> dict[str, frozenset[tuple[str, str]]]:
    """``ticker -> frozenset((date, type))``. Everything stringified, matching the
    ledger's own key construction (``engine.track_record._key_tuple`` stringifies)."""
    if df is None or df.empty:
        return {}
    missing = [c for c in KEY_COLS if c not in df.columns]
    if missing:
        logger.warning("[ledger_identity] frame missing key columns %s — no scan", missing)
        return {}
    out: dict[str, frozenset[tuple[str, str]]] = {}
    for ticker, g in df.groupby(df["ticker"].astype(str), sort=True):
        out[str(ticker)] = frozenset(
            zip(g["date"].astype(str), g["type"].astype(str))
        )
    return out


def find_declared_duplicates(
    df: pd.DataFrame, migrations: Mapping[str, str]
) -> list[dict]:
    """Rows filed under a SUPERSEDED key while the current key also carries rows.

    These are the actionable ones: the entity is ratified as one company, so both
    copies are the same fires and the ledger double-weights it until the keys are
    merged. Reported per (superseded, current) pair, most rows first.
    """
    keys = _key_sets(df)
    findings: list[dict] = []
    for old, new in sorted(migrations.items()):
        old_keys, new_keys = keys.get(old), keys.get(new)
        if not old_keys:
            continue  # superseded key carries nothing — already migrated, or never logged
        shared = (old_keys & new_keys) if new_keys else frozenset()
        dates = sorted(d for d, _ in old_keys)
        findings.append({
            "superseded": old,
            "current": new,
            "superseded_rows": int((df["ticker"].astype(str) == old).sum()),
            "current_rows": int((df["ticker"].astype(str) == new).sum()),
            "shared_keys": len(shared),
            "superseded_only_keys": len(old_keys - (new_keys or frozenset())),
            "current_only_keys": len((new_keys or frozenset()) - old_keys),
            "span": [dates[0], dates[-1]] if dates else None,
            "current_key_absent": new_keys is None,
        })
    findings.sort(key=lambda f: -f["superseded_rows"])
    return findings


def find_undeclared_duplicates(
    df: pd.DataFrame,
    migrations: Mapping[str, str] | None = None,
    min_keys: int = MIN_IDENTICAL_KEYS,
) -> list[dict]:
    """Ticker groups sharing an IDENTICAL ``(date, type)`` key set — identity candidates.

    The signature the EchoStar rename left behind, found WITHOUT knowing the rename:
    two strings whose logged fires coincide exactly, at every date and type, over a
    span no coincidence explains. Exact set equality on purpose — an overlap test
    would sweep in genuine dual-class pairs (GOOG/GOOGL, Jaccard 0.769) that are two
    real instruments with two real forward returns.

    Pairs the ratified map already explains are excluded (they surface through
    ``find_declared_duplicates`` with a remedy attached). CANDIDATES ONLY — this
    proposes, curation ratifies.
    """
    migrations = migrations or {}
    keys = _key_sets(df)
    buckets: dict[frozenset[tuple[str, str]], list[str]] = {}
    for ticker, kset in keys.items():
        if len(kset) < min_keys:
            continue
        buckets.setdefault(kset, []).append(ticker)

    out: list[dict] = []
    for kset, tickers in buckets.items():
        if len(tickers) < 2:
            continue
        # One entity under the ratified map -> already declared, not a candidate.
        if len({current_key(t, migrations) for t in tickers}) == 1:
            continue
        dates = sorted(d for d, _ in kset)
        out.append({
            "tickers": sorted(tickers),
            "n_keys": len(kset),
            "span": [dates[0], dates[-1]],
        })
    out.sort(key=lambda f: -f["n_keys"])
    return out


def migration_receipt(
    df: pd.DataFrame, superseded: str, current: str, *, key_cols: Iterable[str] = KEY_COLS
) -> dict:
    """Is merging ``superseded`` onto ``current`` LOSSLESS? The ratification receipt.

    A key migration on an append-only ledger must destroy no measurement. This
    answers that literally, cell by cell, and is the evidence a repair carries into
    its PR body rather than an assurance:

      ``keys_without_counterpart``  superseded keys with no row under ``current``
                                    (these would have to be RE-KEYED, not dropped);
      ``cells_lost``                cells where the superseded row holds a value and
                                    its ``current`` counterpart is NULL — measurement
                                    that a keep-FIRST merge onto ``current`` would
                                    lose;
      ``identity_conflicts``        cells where BOTH hold a value and they DISAGREE —
                                    if any exist the two keys are not one measurement
                                    and the migration must not proceed unexamined.

    ``lossless`` is true only when all three are empty.
    """
    key_cols = tuple(key_cols)
    sub = df[df["ticker"].astype(str).isin({superseded, current})]
    value_cols = [c for c in df.columns if c not in key_cols]

    old = sub[sub["ticker"].astype(str) == superseded]
    new = sub[sub["ticker"].astype(str) == current]

    def _keyed(frame: pd.DataFrame) -> list[tuple[tuple[str, str], dict]]:
        recs = frame.to_dict(orient="records")
        return [((str(r["date"]), str(r["type"])), r) for r in recs]

    # Plain dict, NOT a tuple-keyed index: `.loc[("2026-04-02", "buy")]` is read by pandas
    # as (row, column) selection and raises KeyError on the type string.
    new_by_key: dict[tuple[str, str], dict] = {}
    for k, r in _keyed(new):
        new_by_key.setdefault(k, r)      # keep-FIRST if `current` itself has dupe keys

    orphans: list[list[str]] = []
    cells_lost: list[dict] = []
    conflicts: list[dict] = []
    provenance: list[dict] = []
    for k, row in _keyed(old):
        counterpart = new_by_key.get(k)
        if counterpart is None:
            orphans.append([k[0], k[1]])
            continue
        for col in value_cols:
            a, b = row.get(col), counterpart.get(col)
            a_null, b_null = pd.isna(a), pd.isna(b)
            if a_null or (not b_null and str(a) == str(b)):
                continue
            cell = {"key": [k[0], k[1]], "column": col, "superseded_value": str(a)}
            if col in PROVENANCE_COLS:
                # Bookkeeping, not measurement — reported, never a veto (see PROVENANCE_COLS).
                provenance.append({**cell, "current_value": None if b_null else str(b)})
            elif b_null:
                cells_lost.append(cell)
            else:
                conflicts.append({**cell, "current_value": str(b)})

    return {
        "superseded": superseded,
        "current": current,
        "superseded_rows": int(len(old)),
        "current_rows": int(len(new)),
        "keys_without_counterpart": orphans,
        "cells_lost": cells_lost,
        "identity_conflicts": conflicts,
        "provenance_divergences": provenance,
        "lossless": not orphans and not cells_lost and not conflicts,
    }


def audit(df: pd.DataFrame, migrations: Mapping[str, str] | None = None) -> dict:
    """Full ledger-identity read: declared duplicates + undeclared candidates.

    Disclosure-shaped (CSP-R1): returns findings, never raises for a data issue and
    never decides anything. Callers annotate; the repair stays a separate, gated act.
    """
    migrations = load_migrations() if migrations is None else dict(migrations)
    declared = find_declared_duplicates(df, migrations)
    for f in declared:
        if f["shared_keys"]:
            try:
                f["receipt"] = migration_receipt(df, f["superseded"], f["current"])
            except Exception as exc:  # noqa: BLE001 — a receipt failure darkens one row
                logger.warning("[ledger_identity] receipt failed for %s->%s: %s",
                               f["superseded"], f["current"], exc)
                f["receipt_error"] = str(exc)
    return {
        "migrations": dict(sorted(migrations.items())),
        "declared_duplicates": declared,
        "undeclared_candidates": find_undeclared_duplicates(df, migrations),
        "min_identical_keys": MIN_IDENTICAL_KEYS,
    }
