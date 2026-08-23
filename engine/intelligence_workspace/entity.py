"""Data OS identity consumer for the W1-A request edge.

No identifiers are minted here.  Every security is looked up through the current
``store`` alias space and the committed security master.  Current alias lookup is
only an input convenience; it never becomes historical symbol evidence.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
import json
from pathlib import Path
from typing import Any

from lib.dataos.identity import (
    IdentityError,
    IssuerMaster,
    VendorAliasTable,
    XASE,
    XNAS,
    XNYS,
    parse_id,
)

from .contracts import CanonicalEntity, EntityRequest


REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_MASTER = Path("data/reference/security_master.parquet")
VENDOR_ALIASES = Path("data/reference/vendor_aliases.parquet")
INDUSTRY_RANKS = Path("data/stage_analysis/industry_ranks.json")
CURRENT_EDGE_VENDOR = "store"
US_EQUITY_MICS = frozenset({XASE, XNAS, XNYS})


class IdentityResolutionError(ValueError):
    """Canonical identity could not be proved from current owner artifacts."""


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise IdentityResolutionError(f"required Data OS identity artifact missing: {path}")
    try:
        import pandas as pd

        return pd.read_parquet(path).to_dict("records")
    except Exception as exc:  # noqa: BLE001
        raise IdentityResolutionError(f"Data OS identity artifact unreadable: {path}: {exc}") from exc


def _security_sources(root: Path) -> tuple[IssuerMaster, VendorAliasTable, dict[str, dict[str, Any]]]:
    master_rows = _records(root / SECURITY_MASTER)
    ids = [str(row.get("security_id") or "") for row in master_rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise IdentityResolutionError("security master contains missing or duplicate security_id")
    alias_rows = _records(root / VENDOR_ALIASES)
    try:
        issuer_master = IssuerMaster.from_records(master_rows)
        aliases = VendorAliasTable.from_records(alias_rows)
    except IdentityError as exc:
        raise IdentityResolutionError(f"Data OS identity contract invalid: {exc}") from exc
    return issuer_master, aliases, {security_id: row for security_id, row in zip(ids, master_rows, strict=True)}


def _nonnull(value: object) -> str | None:
    if value is None or (isinstance(value, float) and value != value):  # noqa: PLR0124
        return None
    text = str(value).strip()
    return text or None


def _security_state(
    security_id: str,
    issuer_master: IssuerMaster,
    master_rows: dict[str, dict[str, Any]],
) -> str:
    if security_id not in master_rows:
        raise IdentityResolutionError(f"unknown canonical security: {security_id}")
    state = _nonnull(issuer_master.security_state_of(security_id))
    superseded_by = _nonnull(issuer_master.superseded_by_of(security_id))
    if superseded_by or (state and "SUPERSEDED" in state.upper()):
        return "superseded"
    if state:
        # The current owner enum contains supersession only.  Any future non-null
        # terminal state must remain unavailable until this consumer is amended.
        return "retired"
    return "active"


def _validate_us_equity_security_id(security_id: str) -> None:
    """Prove the canonical ID belongs to the frozen US-equity universe."""
    try:
        kind, listing = parse_id(security_id)
    except IdentityError as exc:
        raise IdentityResolutionError(
            f"malformed canonical security id: {security_id!r}"
        ) from exc
    if kind != "security":
        raise IdentityResolutionError(
            f"entity id is not a SEC:* security: {security_id!r}"
        )
    if listing.country != "US" or listing.mic not in US_EQUITY_MICS:
        raise IdentityResolutionError(
            f"canonical security is outside frozen us_equity scope: {security_id!r}"
        )


def load_current_symbol_map(
    root: str | Path = REPO_ROOT,
    vendor: str = CURRENT_EDGE_VENDOR,
    *,
    on: date | None = None,
) -> dict[str, str]:
    """Read one current vendor space into ``SEC:* -> symbol``.

    Callers should invoke this through ``RequestContext.memoize``.  The function
    deliberately carries no process cache: W1-A owns no cross-request identity or
    value cache.
    """
    root_path = Path(root)
    rows = _records(root_path / VENDOR_ALIASES)
    try:
        table = VendorAliasTable.from_records(rows)
    except IdentityError as exc:
        raise IdentityResolutionError(f"Data OS alias table invalid: {exc}") from exc
    current = on or date.today()
    security_ids = sorted({row.security_id for row in table.rows if row.vendor == vendor})
    result: dict[str, str] = {}
    for security_id in security_ids:
        symbol = table.vendor_symbol_for(vendor, security_id, current)
        if symbol is not None:
            result[security_id] = symbol
    return result


def current_symbol_resolver(
    root: str | Path = REPO_ROOT,
    vendor: str = CURRENT_EDGE_VENDOR,
    *,
    on: date | None = None,
) -> Callable[[CanonicalEntity], str | None]:
    """Return a callable over one freshly loaded current catalog.

    Construct this at a request boundary.  Batch adapters should prefer
    :func:`load_current_symbol_map` through ``RequestContext.memoize``.
    """
    symbols = load_current_symbol_map(root, vendor, on=on)
    return lambda entity: symbols.get(entity.id) if entity.type == "security" else None


def _industry_ids(root: Path) -> frozenset[str]:
    path = root / INDUSTRY_RANKS
    if not path.is_file():
        raise IdentityResolutionError(f"current Stage industry identity artifact missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityResolutionError(f"current Stage industry identity artifact unreadable: {exc}") from exc
    if payload.get("schema") != "stage_industry_ranks.v1":
        raise IdentityResolutionError("current Stage industry identity schema is invalid")
    rows = (payload.get("regions") or {}).get("USA")
    if not isinstance(rows, list):
        raise IdentityResolutionError("current Stage industry artifact has no USA region rows")
    ids = [str(row.get("industry_id") or "").strip() for row in rows if isinstance(row, dict)]
    if not all(ids) or len(ids) != len(set(ids)):
        raise IdentityResolutionError("current Stage industry artifact has missing/duplicate industry_id")
    return frozenset(ids)


class DataOSIdentityNormalizer:
    """Request-scoped canonicalizer over current Data OS and Stage identity."""

    def __init__(
        self,
        root: str | Path = REPO_ROOT,
        *,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.root = Path(root)
        self._today = today or date.today

    def normalize_many(self, entities: Sequence[EntityRequest]) -> tuple[CanonicalEntity, ...]:
        needs_security = any(entity.type == "security" for entity in entities)
        needs_industry = any(entity.type == "industry" for entity in entities)
        issuer_master: IssuerMaster | None = None
        aliases: VendorAliasTable | None = None
        master_rows: dict[str, dict[str, Any]] = {}
        industry_ids: frozenset[str] = frozenset()
        if needs_security:
            issuer_master, aliases, master_rows = _security_sources(self.root)
        if needs_industry:
            industry_ids = _industry_ids(self.root)

        current = self._today()
        result: list[CanonicalEntity] = []
        for entity in entities:
            if entity.type == "security":
                assert issuer_master is not None and aliases is not None
                if entity.symbol is not None:
                    symbol = str(entity.symbol).strip().upper()
                    security_id = aliases.resolve(CURRENT_EDGE_VENDOR, symbol, current)
                    if security_id is None:
                        raise IdentityResolutionError(
                            f"current symbol alias is unknown in Data OS {CURRENT_EDGE_VENDOR!r}: {symbol!r}"
                        )
                    alias_interpretation = "current_alias_only"
                else:
                    security_id = str(entity.id or "").strip()
                    alias_interpretation = None
                _validate_us_equity_security_id(security_id)
                state = _security_state(security_id, issuer_master, master_rows)
                result.append(
                    CanonicalEntity(
                        type="security",
                        id=security_id,
                        universe="us_equity",
                        state=state,
                        alias_interpretation=alias_interpretation,
                    )
                )
            elif entity.type == "industry":
                industry_id = str(entity.id or "").strip()
                if industry_id not in industry_ids:
                    raise IdentityResolutionError(
                        f"industry id is not present in current Stage USA identity: {industry_id!r}"
                    )
                result.append(CanonicalEntity("industry", industry_id, "us_industry"))
            else:
                raise IdentityResolutionError(f"unsupported entity type: {entity.type!r}")
        return tuple(result)
