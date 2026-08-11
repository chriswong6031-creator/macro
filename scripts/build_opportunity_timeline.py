"""Publish durable Prophet candidate receipts for the Terminal.

``track_ledger/v1`` is already the durable, forward-measured record of names the
regional boards surfaced.  The Terminal cannot consume those four market-level
ledgers directly, so this builder makes one lossless, per-symbol projection:

    site/factordata/opportunity_timeline.json

The projection does not originate a signal and deliberately has no Oracle or
Prophet-plan vocabulary.  Every event remains a ``candidate`` or ``watch``
receipt, carries its source artifact and price frontier, and keeps the source
row's surfaced date separate from its fill date.  Older ``track_ledger/v1``
files do not serialize the latter, so ``entry_date`` stays null rather than
pretending the surfaced bar was tradable.

The source popups cap their newest rows for bounded UI payloads.  This artifact
is the durable checkpoint: each build merges the last valid timeline by stable
event id, then lets a currently-observed row refresh that receipt's marks.  A
receipt that falls outside a source cap therefore remains present.  A malformed
prior checkpoint is a fail-closed error; the builder will never replace it with
a shorter reconstruction.

CN's track and reversal ledgers intentionally repeat prior/alternate eras.  We
flatten ``rows``, ``prior_record.rows`` and every ``extra_records[].rows``, then
deduplicate on the durable identity requested by the cross-repo contract:

    market + system + definition + ticker + surfaced date

For a duplicate, the definition's canonical ledger wins (the CN reversal
definition belongs to ``cn_reversal_ledger.json``; every other CN definition
belongs to ``cn_track_ledger.json``), then the richer row.  The stable event id
is a hash of exactly that identity, so nightly mark-to-market changes never move
the receipt.

Usage::

    python -m scripts.build_opportunity_timeline
    python -m scripts.build_opportunity_timeline --site /path/to/site
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "opportunity_timeline.v1"
TRACK_SCHEMA = "track_ledger/v1"
DEFAULT_OUTPUT = Path("factordata/opportunity_timeline.json")


# The US/HK v1 ledgers predate per-row board-definition stamps.  ``legacy`` is
# the only honest fallback: using tonight's definition would repaint an older
# admission under a selection instrument that did not exist yet.  New emissions
# carry row ``bd`` and always override this fallback.
SOURCE_SPECS: tuple[dict[str, str], ...] = (
    {
        "market": "US",
        "artifact": "factordata/us_track_ledger.json",
        "fallback_definition": "legacy",
    },
    {
        "market": "CN",
        "artifact": "factordata/cn_track_ledger.json",
        "fallback_definition": "cn_prophet_v3",
    },
    {
        "market": "CN",
        "artifact": "factordata/cn_reversal_ledger.json",
        "fallback_definition": "cn_reversal_watch_v1",
    },
    {
        "market": "HK",
        "artifact": "factordata/hk_track_ledger.json",
        "fallback_definition": "legacy",
    },
)

_CN_TICKER = re.compile(r"^(\d{6})\.(SS|SH|SSE|XSHG|SZ|XSHE)$", re.I)
_HK_TICKER = re.compile(r"^(\d{1,5})\.HK$", re.I)
_US_TICKER = re.compile(r"^[A-Z][A-Z0-9]{0,9}(?:[.\-][A-Z0-9]{1,3})?$", re.I)


def normalize_ticker(value: Any, market: str) -> str | None:
    """Return the Terminal's conservative ticker spelling, or ``None``.

    Only exchange aliases with unambiguous meaning are folded.  In particular,
    bare numeric codes never acquire an exchange suffix and US punctuation is
    preserved; the bridge must not guess an instrument.
    """

    if value is None:
        return None
    ticker = str(value).strip().upper()
    market = str(market).strip().upper()
    if not ticker:
        return None

    if market == "CN":
        match = _CN_TICKER.fullmatch(ticker)
        if not match:
            return None
        code, suffix = match.groups()
        canonical = "SS" if suffix.upper() in {"SS", "SH", "SSE", "XSHG"} else "SZ"
        return f"{code}.{canonical}"

    if market == "HK":
        match = _HK_TICKER.fullmatch(ticker)
        if not match:
            return None
        # Board artifacts have used both 09988.HK and 9988.HK.  Numeric HK
        # aliases are the same listed instrument; the Terminal uses the latter.
        code = match.group(1).lstrip("0") or "0"
        return f"{code}.HK"

    if market == "US" and _US_TICKER.fullmatch(ticker):
        return ticker
    return None


def _finite_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if isinstance(value, int):
        return int(value)
    return number


def _integer(value: Any) -> int | None:
    number = _finite_number(value)
    if number is None or float(number) != int(number):
        return None
    return int(number)


def _date(value: Any) -> str | None:
    """Accept only an ISO date prefix; do not invent time-zone semantics."""

    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    candidate = text[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return None
    return candidate


def _definition(block: Mapping[str, Any], fallback: str) -> str:
    for value in (
        block.get("board_definition"),
        (block.get("summary") or {}).get("board_definition")
        if isinstance(block.get("summary"), Mapping) else None,
        (block.get("meta") or {}).get("board_definition")
        if isinstance(block.get("meta"), Mapping) else None,
    ):
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _system_and_authority(definition: str) -> tuple[str, str]:
    lowered = definition.lower()
    if "reversal_watch" in lowered:
        return "reversal_watch", "watch"
    # A shadow board is explicitly accrual/watch authority even when it shares
    # the Prophet scorer.  Every other historical/current board row is still a
    # candidate receipt — never a plan and never an Oracle signal.
    authority = "watch" if "shadow" in lowered else "candidate"
    return "prophet_board", authority


def _record_blocks(doc: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield doc
    prior = doc.get("prior_record")
    if isinstance(prior, Mapping):
        yield prior
    extras = doc.get("extra_records")
    if isinstance(extras, list):
        for block in extras:
            if isinstance(block, Mapping):
                yield block


def _priced_through(doc: Mapping[str, Any], block: Mapping[str, Any]) -> str | None:
    for owner in (block, block.get("meta"), doc, doc.get("meta")):
        if isinstance(owner, Mapping):
            value = _date(owner.get("priced_through"))
            if value:
                return value
    return None


def _event_id(identity: tuple[str, str, str, str, str]) -> str:
    digest = hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()[:20]
    return f"opp_{digest}"


def _entry_basis(row: Mapping[str, Any], market: str) -> str | None:
    explicit = row.get("eb") or row.get("entry_basis")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    # The US episode scorer's documented fill convention.  Keep it even while
    # an onboard row is waiting for that bar; it says what the pending fill is.
    if market == "US":
        return "next_session_close"
    return None


def _build_event(
    row: Mapping[str, Any],
    *,
    market: str,
    definition: str,
    source_artifact: str,
    source_as_of: str | None,
    priced_through: str | None,
) -> tuple[tuple[str, str, str, str, str], dict[str, Any]] | None:
    ticker = normalize_ticker(row.get("t") or row.get("ticker"), market)
    surfaced = _date(row.get("d") or row.get("surfaced_at"))
    if not ticker or not surfaced:
        return None
    row_definition = row.get("bd") or row.get("board_definition")
    if row_definition is not None and str(row_definition).strip():
        definition = str(row_definition).strip()
    system, authority = _system_and_authority(definition)
    identity = (market, system, definition, ticker, surfaced)
    matured = bool(row.get("m"))
    event = {
        "id": _event_id(identity),
        "market": market,
        "system": system,
        "definition": definition,
        "authority": authority,
        "surfaced_at": surfaced,
        # track_ledger/v1 did not originally serialize the fill date.  Read a
        # future additive key when present, otherwise preserve the honest null.
        "entry_date": _date(row.get("ed") or row.get("entry_date")),
        "entry_basis": _entry_basis(row, market),
        "entry_price": _finite_number(row.get("e")),
        "rank": _integer(row.get("rk")),
        "tier": str(row["tr"]) if row.get("tr") is not None else None,
        "state": str(row.get("st") or "unknown"),
        "maturity": "matured" if matured else "in_flight",
        "latest_price": _finite_number(row.get("l")),
        "return_pct": _finite_number(row.get("p")),
        "excess_pct": _finite_number(row.get("x")),
        "sessions": _integer(row.get("dy")),
        "source_artifact": source_artifact,
        "source_as_of": source_as_of,
        "priced_through": priced_through,
    }
    return identity, event


def _canonical_priority(definition: str, source_artifact: str) -> int:
    is_reversal = "reversal_watch" in definition.lower()
    is_reversal_source = source_artifact.endswith("cn_reversal_ledger.json")
    if is_reversal:
        return 2 if is_reversal_source else 0
    if source_artifact.endswith("cn_track_ledger.json"):
        return 2
    return 1


def _richness(event: Mapping[str, Any]) -> int:
    return sum(value is not None for key, value in event.items()
               if key not in {"id", "source_artifact"})


def build_timeline(sources: Iterable[tuple[dict[str, str], Mapping[str, Any]]]) -> dict[str, Any]:
    """Build an ``opportunity_timeline.v1`` payload from parsed ledgers."""

    chosen: dict[tuple[str, str, str, str, str], tuple[tuple[int, int], dict[str, Any]]] = {}
    source_asofs: list[str] = []
    frontier_by_market: dict[str, list[str]] = {"US": [], "CN": [], "HK": []}

    for spec, doc in sources:
        market = spec["market"]
        artifact = spec["artifact"]
        if doc.get("schema") != TRACK_SCHEMA:
            raise ValueError(f"{artifact}: expected schema {TRACK_SCHEMA!r}")
        stamped_market = str(doc.get("market") or "").upper()
        if stamped_market and stamped_market != market:
            raise ValueError(f"{artifact}: market {stamped_market!r} != {market!r}")
        source_as_of = _date(doc.get("as_of"))
        if source_as_of:
            source_asofs.append(source_as_of)

        for block in _record_blocks(doc):
            definition = _definition(block, spec["fallback_definition"])
            frontier = _priced_through(doc, block)
            if frontier:
                frontier_by_market.setdefault(market, []).append(frontier)
            rows = block.get("rows")
            if rows is None:
                continue
            if not isinstance(rows, list):
                raise ValueError(f"{artifact}: rows must be a list")
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                built = _build_event(
                    row,
                    market=market,
                    definition=definition,
                    source_artifact=f"site/{artifact}",
                    source_as_of=source_as_of,
                    priced_through=frontier,
                )
                if built is None:
                    continue
                identity, event = built
                quality = (_canonical_priority(definition, artifact), _richness(event))
                previous = chosen.get(identity)
                if previous is None or quality > previous[0]:
                    chosen[identity] = (quality, event)

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for identity, (_quality, event) in chosen.items():
        ticker = identity[3]
        by_symbol.setdefault(ticker, []).append(event)

    symbols: dict[str, dict[str, Any]] = {}
    for ticker in sorted(by_symbol):
        events = sorted(
            by_symbol[ticker],
            key=lambda event: (
                event["surfaced_at"], event["system"], event["definition"], event["id"]
            ),
            reverse=True,
        )
        symbols[ticker] = {"symbol": ticker, "events": events}

    # A per-market map avoids claiming that the US price frontier also covers
    # A-shares/HK.  A null means the source ledger did not stamp that provenance.
    priced_through = {
        market: max(values) if values else None
        for market, values in sorted(frontier_by_market.items())
    }
    return {
        "schema": SCHEMA,
        "as_of": max(source_asofs) if source_asofs else None,
        "priced_through": priced_through,
        "symbols": symbols,
    }


def _symbol_market(ticker: str) -> str:
    if ticker.endswith((".SS", ".SZ")):
        return "CN"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def _validated_checkpoint_events(prior: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Validate the last durable checkpoint before using any of it.

    The first generated v1 artifact predated the additive ``market`` field.  Its
    stable ids already included market, so derive and stamp that one field during
    migration; every other identity field remains strict.
    """
    if prior.get("schema") != SCHEMA:
        raise ValueError(f"prior checkpoint schema must be {SCHEMA!r}")
    symbols = prior.get("symbols")
    if not isinstance(symbols, Mapping):
        raise ValueError("prior checkpoint symbols must be an object")

    checked: dict[str, list[dict[str, Any]]] = {}
    for raw_ticker, block in symbols.items():
        if not isinstance(raw_ticker, str) or not isinstance(block, Mapping):
            raise ValueError("prior checkpoint has a malformed symbol block")
        ticker = raw_ticker.strip().upper()
        market = _symbol_market(ticker)
        if normalize_ticker(ticker, market) != ticker:
            raise ValueError(f"prior checkpoint has an invalid ticker {raw_ticker!r}")
        events = block.get("events")
        if not isinstance(events, list):
            raise ValueError(f"prior checkpoint {ticker} events must be an array")
        out: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, Mapping):
                raise ValueError(f"prior checkpoint {ticker} contains a non-object event")
            migrated = dict(event)
            stamped_market = str(migrated.get("market") or market).upper()
            if stamped_market != market:
                raise ValueError(f"prior checkpoint {ticker} carries market {stamped_market!r}")
            migrated["market"] = market
            system = migrated.get("system")
            definition = migrated.get("definition")
            surfaced = _date(migrated.get("surfaced_at"))
            if not all(isinstance(value, str) and value for value in (system, definition)) or not surfaced:
                raise ValueError(f"prior checkpoint {ticker} has an incomplete identity")
            identity = (market, str(system), str(definition), ticker, surfaced)
            if migrated.get("id") != _event_id(identity):
                raise ValueError(f"prior checkpoint {ticker} has a mismatched stable id")
            out.append(migrated)
        checked[ticker] = out
    return checked


def merge_checkpoint(current: Mapping[str, Any], prior: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a durable union where current source observations refresh old receipts."""
    if prior is None:
        return dict(current)
    previous = _validated_checkpoint_events(prior)
    observed = _validated_checkpoint_events(current)

    def freshness(event: Mapping[str, Any]) -> tuple[bool, str, bool, str]:
        """Price frontier first, then source build date; missing never beats known."""
        priced = _date(event.get("priced_through"))
        source = _date(event.get("source_as_of"))
        return (priced is not None, priced or "", source is not None, source or "")

    # First merge exact stable identities.  A stale source artifact must not roll a
    # fresher checkpoint mark backwards while the top-level frontier stays newer.
    grouped: dict[tuple[str, str, str, str, str], dict[str, dict[str, Any]]] = {}
    for is_current, blocks in ((False, previous), (True, observed)):
        for ticker, events in blocks.items():
            for event in events:
                logical = (
                    str(event["market"]), str(event["system"]), ticker,
                    str(event["surfaced_at"]), str(event.get("source_artifact") or ""),
                )
                bucket = grouped.setdefault(logical, {})
                event_id = str(event["id"])
                old = bucket.get(event_id)
                if old is None or (is_current and freshness(event) >= freshness(old)):
                    bucket[event_id] = dict(event)

    # One-time definition migration.  US/HK v1 rows initially lacked per-admission
    # definitions and were honestly checkpointed as `legacy`.  Once their source emits
    # the authoritative `bd`, the stable id changes because definition is part of the
    # identity.  Treat exactly one non-legacy receipt in the same source/date as the
    # canonical spelling, while retaining the freshest marks from either spelling.
    # Ambiguous multi-definition groups remain separate rather than guessing.
    merged_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for logical, by_id in grouped.items():
        market, system, ticker, surfaced, _source = logical
        events = list(by_id.values())
        canonical = [event for event in events if str(event.get("definition")) != "legacy"]
        legacy = [event for event in events if str(event.get("definition")) == "legacy"]
        if len(canonical) == 1 and legacy:
            identity_event = canonical[0]
            freshest = max([identity_event, *legacy], key=freshness)
            resolved = dict(freshest)
            # Definition/system authority comes from the authoritative admission stamp;
            # mark-to-market fields and their provenance come from the freshest receipt.
            for field in ("id", "market", "system", "definition", "authority", "surfaced_at"):
                resolved[field] = identity_event[field]
            events = [resolved]
        merged_by_symbol.setdefault(ticker, []).extend(events)

    symbols: dict[str, dict[str, Any]] = {}
    for ticker in sorted(merged_by_symbol):
        events = sorted(
            merged_by_symbol[ticker],
            key=lambda event: (
                str(event.get("surfaced_at") or ""), str(event.get("system") or ""),
                str(event.get("definition") or ""), str(event.get("id") or ""),
            ),
            reverse=True,
        )
        symbols[ticker] = {"symbol": ticker, "events": events}

    as_ofs = [_date(current.get("as_of")), _date(prior.get("as_of"))]
    prior_frontier = prior.get("priced_through")
    current_frontier = current.get("priced_through")
    if not isinstance(prior_frontier, Mapping) or not isinstance(current_frontier, Mapping):
        raise ValueError("checkpoint priced_through must be an object")
    markets = set(prior_frontier) | set(current_frontier)
    priced_through: dict[str, str | None] = {}
    for market in sorted(markets):
        dates = [_date(prior_frontier.get(market)), _date(current_frontier.get(market))]
        priced_through[str(market)] = max((d for d in dates if d), default=None)
    return {
        "schema": SCHEMA,
        "as_of": max((d for d in as_ofs if d), default=None),
        "priced_through": priced_through,
        "symbols": symbols,
    }


def load_sources(site: Path) -> list[tuple[dict[str, str], Mapping[str, Any]]]:
    loaded: list[tuple[dict[str, str], Mapping[str, Any]]] = []
    for spec in SOURCE_SPECS:
        path = site / spec["artifact"]
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - caller must leave last-good output untouched
            raise ValueError(f"cannot read required source {path}: {exc}") from exc
        if not isinstance(doc, Mapping):
            raise ValueError(f"{path}: top level must be an object")
        loaded.append((spec, doc))
    return loaded


def atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode()
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.out or (args.site / DEFAULT_OUTPUT)
    try:
        current = build_timeline(load_sources(args.site))
        prior = None
        if output.exists():
            prior = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(prior, Mapping):
                raise ValueError("prior checkpoint top level must be an object")
        payload = merge_checkpoint(current, prior)
        atomic_write(output, payload)
    except Exception as exc:  # noqa: BLE001 - additive publication keeps last-good artifact
        print(f"::warning title=opportunity-timeline::{exc}", flush=True)
        return 1
    n_events = sum(len(block["events"]) for block in payload["symbols"].values())
    print(f"opportunity timeline: wrote {output} ({len(payload['symbols'])} symbols, "
          f"{n_events} receipts)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
