"""Compose the tenant-neutral ``ontology_explorer_snapshot.v1`` (F04-X1).

WHAT THIS IS
------------
A pure, request-time READER. It answers one question for one transmission
chain — what does the owner-observed path actually say right now — and it
answers it by composing artifacts that other owners already produced:

    knowledge/transmission/<chain>.yaml     the path definition (canonical)
    data/transmission/chain_state.json      the compiled owner observation
    data/transmission/chain_episodes.jsonl  recorded transitions, when present

It creates no graph, no causal model, no truth store, no cache and no second
evaluation of anything. ``/transmission.html`` remains the canonical rates/TXI
owner surface; this module composes read-only on top of it.

WHY IT DOES NOT CALL THE CANONICAL EVALUATOR
--------------------------------------------
``engine.transmission_chains.run()`` defaults to ``write=True`` and APPENDS
``chain_episodes.jsonl``. A request-time consumer that reached for it would
mutate an owner artifact on a GET, and would re-derive state the nightly has
already derived. So this module reads the compiled artifact and never evaluates.

It also does not call ``validate_chain()``. That validator is the NIGHTLY's
gate: it raises on the first structural violation, and it already guarantees in
production that hops form a simple path in declared-node order. A request-time
composer needs the opposite disposition — it must DEGRADE with a typed, legible
state rather than raise a compiler error at a researcher, and it must not
silently change product semantics the next time the nightly's strictness moves.
So the structural questions this surface actually depends on — path order, cycle
freedom, node coverage, revision coherence, size bounds — are asked here,
directly, against the bytes that were read.

WHAT IT REFUSES TO SAY
----------------------
Three refusals are load-bearing, and each exists because the plausible-looking
alternative is false:

  * A confirmed DOWNSTREAM leg never activates a false upstream one. The frozen
    reference case has a true terminal leg over three false upstream legs; that
    is a contradiction to report, not partial activation and not an attribution.
  * An absent baseline is NOT "nothing changed". Zero recorded transitions means
    the comparison cannot be made, so the answer is ``comparison_unavailable``.
  * Freshness is never claimed. This process reads the checkout it runs in and
    cannot observe what the deployed canonical surface serves, so it reports the
    source age it can actually measure and marks the comparison unavailable.

Frequencies and episode counts are historical context, never confidence, and
this surface carries no rank, gate, size or trade authority.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

SCHEMA_ID = "ontology_explorer_snapshot.v1"
#: The manifest answers "did two responses see the same thing". Two responses can
#: read byte-identical sources and still differ, because the meaning is produced
#: by THIS code — so the method that read them is part of what the digest binds.
#: It is still a read receipt, never a native owner generation.
COMPOSER_METHOD = "ontology_explorer.compose.v2"
ERROR_SCHEMA_ID = "ontology_explorer_error.v1"
DEFAULT_CHAIN = "oil_inflation_duration_derate"

#: Compiled-state schemas this composer knows how to read. A state file built
#: under any other schema is refused rather than guessed at.
COMPATIBLE_STATE_SCHEMAS = frozenset({"transmission_chains.v1"})

#: Response bound. Long paths are not "big responses" here, they are evidence
#: that the input is not the simple path this surface is designed to explain, so
#: the bound fails closed instead of truncating into a half-answer.
MAX_PATH_LEGS = 12

#: Bytes, not rows: a bound that counts only nodes leaves the payload unbounded.
MAX_SOURCE_BYTES = 2_000_000
MAX_EPISODE_ROWS = 5_000

#: fullmatch below, not match: `$` also matches before a trailing newline.
_CHAIN_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_]{0,80}")

#: distinct from a present-but-null field — "never written" and "written as null"
#: are different owner statements and neither is a verdict.
_MISSING = object()

_KNOWLEDGE_REL = "knowledge/transmission"
_STATE_REL = "data/transmission/chain_state.json"
_EPISODES_REL = "data/transmission/chain_episodes.jsonl"


class SourceUnavailable(RuntimeError):
    """A required owner artifact is absent or unreadable. Serve a typed 503."""


class SourceIncoherent(RuntimeError):
    """The artifacts were readable but cannot be trusted together.

    Two distinct classes land here, and conflating them would hide one:
    a MID-READ MUTATION (the bytes moved under the read), and a STABLE BUT
    MIXED GENERATION (nothing moved, but the sources describe different
    revisions or reference nodes that do not exist).
    """


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def _read_source(path: Path) -> bytes:
    """The single seam through which every source byte is read.

    Kept as one function so the post-composition re-verification reads exactly
    the way the first pass did, and so a test can prove the mutation detector
    actually fires.
    """
    return path.read_bytes()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def manifest_hash_for(reads: list[dict[str, Any]], *,
                      method: str = COMPOSER_METHOD) -> str:
    """Reproduce the manifest hash from the receipts alone.

    A caller comparing two responses must be able to decide whether they saw the
    same owner generation without trusting either response's own summary, so the
    hash is a pure function of ``(path, sha256)`` pairs in sorted order.
    """
    joined = "\n".join([method] + [f"{r['path']}:{r['sha256']}"
                                   for r in sorted(reads, key=lambda r: r["path"])])
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _bilingual(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict) and isinstance(value.get("en"), str):
        return {"en": value["en"], "zh": value.get("zh") or value["en"]}
    if isinstance(value, str):
        return {"en": value, "zh": value}
    return None


# ---------------------------------------------------------------------------
# path structure
# ---------------------------------------------------------------------------
def _walk_path(hops: list[dict]) -> tuple[list[str], list[str]]:
    """Return (sequence, cycle_nodes) from the ORDERED hop list.

    Order comes from the hops and nothing else. The node mapping in a knowledge
    file is unordered by construction, and any score-derived ordering would let
    a large receipt jump the queue ahead of the leg that actually blocks.
    """
    if not hops:
        return [], []
    inbound: dict[str, int] = {}
    for hop in hops:
        inbound.setdefault(str(hop.get("from")), 0)
        inbound[str(hop.get("to"))] = inbound.get(str(hop.get("to")), 0) + 1
    nxt: dict[str, str] = {}
    for hop in hops:
        nxt.setdefault(str(hop.get("from")), str(hop.get("to")))
    start = str(hops[0].get("from"))
    for node_id, count in inbound.items():
        if count == 0:
            start = node_id
            break
    sequence: list[str] = []
    seen: set[str] = set()
    cursor: str | None = start
    cycle: list[str] = []
    while cursor is not None:
        if cursor in seen:
            # Re-entering a node means the "path" loops. Record the loop members
            # and stop; a repeated node in the sequence would let one leg be
            # counted twice and inflate the state.
            cycle = sequence[sequence.index(cursor):]
            break
        seen.add(cursor)
        sequence.append(cursor)
        cursor = nxt.get(cursor)
    return sequence, cycle


def _unreached_nodes(definition_hops: list[dict], declared_nodes: dict,
                     sequence: list[str]) -> list[str]:
    referenced: set[str] = set()
    for hop in definition_hops:
        referenced.update((str(hop.get("from")), str(hop.get("to"))))
    return sorted((referenced | set(declared_nodes)) - set(sequence))


def _require_simple_path(definition_hops: list[dict], declared_nodes: dict,
                        sequence: list[str]) -> None:
    """Refuse anything that is not one continuous path through every node.

    `_walk_path` follows a single successor chain from one root. That is the
    right reading of a simple path and a silently WRONG reading of anything
    else: a hop list of `n1->n2` and `n3->n4` walks to `['n1','n2']`, and every
    downstream calculation — coverage, activation, the bound, the legs — then
    describes two legs as if they were the whole path. With `n3` and `n4`
    observed FALSE, this surface answered `state: active` about a path it had
    not read. Branching does the same thing more quietly, because the second
    out-edge is dropped when the successor map is built.

    The nightly's `validate_chain` does enforce continuity, and every live chain
    is a simple path today, so this is latent rather than firing. It is still
    ours to check: this module deliberately does not call that validator, it is
    a REQUEST-TIME reader, and a hop edit that does not bump `rev` reaches a
    reader before any nightly runs. Failing closed is the only answer that
    cannot mislead — a partial path presented as a whole one is worse than a
    typed 503.
    """
    out_degree: dict[str, int] = {}
    referenced: set[str] = set()
    for hop in definition_hops:
        src, dst = str(hop.get("from")), str(hop.get("to"))
        out_degree[src] = out_degree.get(src, 0) + 1
        referenced.update((src, dst))
    branching = sorted(node for node, degree in out_degree.items() if degree > 1)
    if branching:
        raise SourceIncoherent(f"path_branches:{branching[0]}")
    undeclared = sorted(referenced - set(declared_nodes))
    if undeclared:
        # A hop pointing at a node the file never declares is an incoherent
        # file, not an unpublished reading. Reported as the latter it invented a
        # positional title for the phantom and told the researcher to wait for a
        # reading that can never arrive.
        raise SourceIncoherent(f"undeclared_node:{undeclared[0]}")
    unreached = _unreached_nodes(definition_hops, declared_nodes, sequence)
    if unreached:
        raise SourceIncoherent(f"path_disconnected:{unreached[0]}")


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------
def compose_snapshot(root: Path | str, *, chain: str = DEFAULT_CHAIN,
                     now: datetime | None = None) -> dict[str, Any]:
    """Compose one ``ontology_explorer_snapshot.v1`` for ``chain``."""
    root = Path(root)
    if not _CHAIN_SLUG_RE.fullmatch(chain or ""):
        raise SourceUnavailable(f"unknown_chain:{chain!r}")

    yaml_rel = f"{_KNOWLEDGE_REL}/{chain}.yaml"
    rels = [yaml_rel, _STATE_REL]
    if (root / _EPISODES_REL).exists():
        rels.append(_EPISODES_REL)

    raws: dict[str, bytes] = {}
    for rel in rels:
        path = root / rel
        try:
            raws[rel] = _read_source(path)
        except OSError as exc:
            raise SourceUnavailable(f"unreadable_source:{rel}") from exc
        if len(raws[rel]) > MAX_SOURCE_BYTES:
            raise SourceIncoherent(
                f"source_exceeds_bound:{rel}:{len(raws[rel])}>{MAX_SOURCE_BYTES}")
    digests = {rel: _digest(raw) for rel, raw in raws.items()}

    try:
        definition = yaml.safe_load(raws[yaml_rel].decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise SourceUnavailable(f"unparseable_source:{yaml_rel}") from exc
    try:
        state_doc = json.loads(raws[_STATE_REL].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceUnavailable(f"unparseable_source:{_STATE_REL}") from exc
    if not isinstance(definition, dict) or not isinstance(state_doc, dict):
        raise SourceUnavailable("malformed_source")

    snapshot = _build(definition, state_doc, raws.get(_EPISODES_REL), chain=chain,
                      now=now or datetime.now(UTC))

    # Re-verify AFTER composing, by re-reading rather than by trusting a stat
    # taken beforehand. This catches any source rewritten after this process
    # read it. It does NOT catch a source rewritten just BEFORE its own read,
    # because that read returns the newer generation and every digest then stays
    # stable — that window is closed by the revision coherence check above, not
    # by the digest, which is why both checks exist.
    for rel, expected in digests.items():
        try:
            current = _digest(_read_source(root / rel))
        except OSError as exc:
            raise SourceIncoherent(f"mid_read_mutation:{rel}:disappeared") from exc
        if current != expected:
            raise SourceIncoherent(f"mid_read_mutation:{rel}")

    reads = [{"path": rel, "sha256": digests[rel], "bytes": len(raws[rel])} for rel in rels]
    snapshot["source"]["reads"] = reads
    snapshot["source"]["source_manifest_hash"] = manifest_hash_for(reads)
    snapshot["source"]["composer_method"] = COMPOSER_METHOD
    return snapshot


def _build(definition: dict, state_doc: dict, episodes_raw: bytes | None, *,
           chain: str, now: datetime) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    state_schema = state_doc.get("schema")
    if state_schema not in COMPATIBLE_STATE_SCHEMAS:
        raise SourceIncoherent(f"schema_incompatible:{state_schema!r}")

    entries = state_doc.get("chains")
    if not isinstance(entries, list):
        raise SourceUnavailable("malformed_source:chains")
    matches = [c for c in entries if isinstance(c, dict) and c.get("chain") == chain]
    if not matches:
        raise SourceUnavailable(f"chain_absent_from_state:{chain}")
    if len(matches) > 1:
        # Taking matches[0] made every later row invisible — including a row at a
        # different rev with a different state, which also walked straight past
        # the rev-coherence check below, since that check only ever saw row 0.
        raise SourceIncoherent(f"duplicate_chain_rows:{len(matches)}")
    observed = matches[0]

    if definition.get("chain") != chain:
        raise SourceIncoherent(f"chain_mismatch:{definition.get('chain')!r}")
    if definition.get("rev") != observed.get("rev"):
        raise SourceIncoherent(
            f"rev_mismatch:knowledge={definition.get('rev')!r}:state={observed.get('rev')!r}")

    declared_nodes = definition.get("nodes")
    if not isinstance(declared_nodes, dict) or not declared_nodes:
        # The file was present, readable and parsed. That is a coherence failure,
        # not an availability one, and calling it "absent" misdescribes it.
        raise SourceIncoherent("malformed_nodes")
    definition_hops = definition.get("hops")
    if not isinstance(definition_hops, list) or not definition_hops:
        raise SourceIncoherent("malformed_hops")

    observed_nodes = {n["id"]: n for n in observed.get("nodes", [])
                      if isinstance(n, dict) and isinstance(n.get("id"), str)}
    unknown = sorted(set(observed_nodes) - set(declared_nodes))
    if unknown:
        raise SourceIncoherent(f"unknown_node:{unknown[0]}")

    observed_node_rows = [n for n in observed.get("nodes", []) if isinstance(n, dict)]
    row_ids = [n.get("id") for n in observed_node_rows if isinstance(n.get("id"), str)]
    if len(row_ids) != len(set(row_ids)):
        raise SourceIncoherent(f"duplicate_node_rows:{len(row_ids) - len(set(row_ids))}")

    sequence, cycle_nodes = _walk_path(definition_hops)
    if not cycle_nodes:
        _require_simple_path(definition_hops, declared_nodes, sequence)
    else:
        # A cycle already forces `unknown`, so this degrades rather than raises —
        # but it must still be SEEN. Skipping the completeness check entirely
        # under a cycle left a whole disconnected component invisible.
        unreached = _unreached_nodes(definition_hops, declared_nodes, sequence)
        if unreached:
            gaps.append({"kind": "path_incomplete", "unreached": unreached})
    # The bound is measured against the FILE, not against the walk. Measuring the
    # walk let a file with 80 declared nodes and 40 disjoint hop pairs compose as
    # "2 of 12 legs" while returning 40 rendered hop rows.
    declared_size = max(len(sequence), len(definition_hops) + 1, len(declared_nodes))
    if declared_size > MAX_PATH_LEGS:
        raise SourceIncoherent(f"path_exceeds_bound:{declared_size}>{MAX_PATH_LEGS}")

    observed_hops = {h["id"]: h for h in observed.get("hops", [])
                     if isinstance(h, dict) and isinstance(h.get("id"), str)}

    legs = _legs(sequence, declared_nodes, observed_nodes, gaps)
    hops = _hops(definition_hops, observed_hops, gaps)
    invalidators = _invalidators(definition, gaps)
    exposure_screens = _exposure_screens(definition, gaps)

    # "unresolved" is not "observed". Counting it as observed produced a snapshot
    # that said all four legs were observed while its own blocking-leg block said
    # that very leg had no reading.
    unobserved = [leg["node_id"] for leg in legs if leg["observation"] != "observed"]
    confirmed_hop_count = sum(1 for h in hops if h["confirmed"] is True)
    activation = bool(sequence) and not cycle_nodes and not unobserved and all(
        leg["confirmed"] is True for leg in legs)

    if cycle_nodes or unobserved:
        state_code = "unknown"
    elif activation:
        state_code = "active"
    else:
        state_code = "dormant"

    first_blocking = _first_blocking_leg(legs) if not activation else None
    contradiction = _contradiction(legs, first_blocking)

    payload = {
        "schema": SCHEMA_ID,
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": _source_block(definition, state_doc, observed, chain=chain,
                                now=now, gaps=gaps),
        "state": {
            "code": state_code,
            "label": _state_label(state_code),
            "activation": activation,
            "owner_state": observed.get("state"),
            "owner_state_label": _reader_text(
                observed.get("state_label"), kind=IDENTITY,
                where="state_label", gaps=gaps),
            "tier": observed.get("tier"),
            "display_only": bool(observed.get("display_only", True)),
            "confirmed_hop_count": confirmed_hop_count,
            "hop_count": len(hops),
            "coverage": {
                "legs_declared": len(sequence),
                "legs_observed": len(sequence) - len(unobserved),
                "legs_unobserved": unobserved,
            },
        },
        "path": {
            "title": _reader_text(
                definition.get("title"), kind=IDENTITY, where="title", gaps=gaps,
                fallback={"en": "Transmission path", "zh": "\u4f20\u5bfc\u8def\u5f84"}),
            "sequence": sequence,
            "legs": legs,
            "hops": hops,
            "cycle": {"detected": bool(cycle_nodes), "nodes": cycle_nodes},
        },
        "first_blocking_leg": first_blocking,
        "contradiction": contradiction,
        "what_changed": _what_changed(episodes_raw, chain=chain,
                                      rev=observed.get("rev"),
                                      cutoff=state_doc.get("asof"), gaps=gaps),
        "why_it_matters": _why_it_matters(hops, contradiction),
        "next_action": _next_action(state_code, first_blocking, contradiction, unobserved, legs),
        "evidence": _evidence(episodes_raw, legs, chain=chain,
                              rev=observed.get("rev"), cutoff=state_doc.get("asof")),
        "clocks": _clocks(observed, state_doc, hops, now=now),
        "invalidators": invalidators,
        "exposure_screens": exposure_screens,
        "display_permission": {
            "status": "not_determined_here",
            "policy": "site_full entitlement, enforced at the transport layer",
        },
        "gaps": gaps,
        "bounds": {"legs": len(sequence), "max_legs": MAX_PATH_LEGS, "truncated": False},
    }
    # Last, because the composers above are still appending to `gaps` while the
    # payload literal is being built.
    _label_gaps(gaps, legs)
    return payload


def _state_label(code: str) -> dict[str, str]:
    return {
        "active": {"en": "Active", "zh": "运行中"},
        "dormant": {"en": "Dormant", "zh": "休眠"},
        "unknown": {"en": "Unknown", "zh": "未知"},
    }[code]


def _read_leg_verdict(node_id: str, seen: dict,
                      gaps: list[dict]) -> tuple[bool | None, str]:
    """Read one leg's verdict under the owner's TYPED semantics.

    Truthiness is not a reading. `bool("false")` is True, so a string in the
    owner artifact could ACTIVATE a leg the owners had marked as not holding;
    `bool(None)` is False, so an unwritten verdict became a definite negative;
    and defaulting `resolved` to True asserted a judgement the owners may simply
    not have made. Each of those invents market state out of a Python
    conversion. Only a real bool is a verdict, only a real bool `resolved` is a
    judgement, and everything else preserves UNKNOWN and says which kind it is.
    """
    resolved = seen.get("resolved", _MISSING)
    if resolved is _MISSING or not isinstance(resolved, bool):
        gaps.append({"kind": "node_incomplete", "node_id": node_id})
        return None, "incomplete"
    if not resolved:
        gaps.append({"kind": "node_unresolved", "node_id": node_id})
        return None, "unresolved"
    verdict = seen.get("confirmed", _MISSING)
    if verdict is None or verdict is _MISSING:
        gaps.append({"kind": "node_unjudged", "node_id": node_id})
        return None, "incomplete"
    if not isinstance(verdict, bool):
        gaps.append({"kind": "node_unreadable", "node_id": node_id,
                     "reason": "confirmed_not_boolean"})
        return None, "unreadable"
    return verdict, "observed"


def _legs(sequence: list[str], declared: dict, observed: dict,
          gaps: list[dict]) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for index, node_id in enumerate(sequence, start=1):
        spec = declared.get(node_id) or {}
        seen = observed.get(node_id)
        if seen is None:
            gaps.append({"kind": "node_unobserved", "node_id": node_id})
            confirmed: bool | None = None
            observation = "unobserved"
            receipts: list[dict[str, Any]] = []
        else:
            receipts = [r for r in seen.get("receipts", []) if isinstance(r, dict)]
            confirmed, observation = _read_leg_verdict(node_id, seen, gaps)
        legs.append({
            "node_id": node_id,
            "index": index,
            "title": _reader_text(
                spec.get("title"), kind=IDENTITY, where=f"nodes.{node_id}.title",
                gaps=gaps,
                fallback={"en": f"Step {index}", "zh": f"\u7b2c {index} \u73af\u8282"}),
            "src": spec.get("src"),
            "observation": observation,
            "confirmed": confirmed,
            "receipts": receipts,
        })
    return legs


def _hops(definition_hops: list[dict], observed_hops: dict,
          gaps: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hop in definition_hops:
        hop_id = f"{hop.get('from')}->{hop.get('to')}"
        seen = observed_hops.get(hop_id) or {}
        lag = hop.get("lag_d") if isinstance(hop.get("lag_d"), list) else seen.get("lag_d")
        if not isinstance(lag, list) or len(lag) != 2:
            gaps.append({"kind": "clock_absent", "hop_id": hop_id})
            lag = None
        base = seen.get("base_rate")
        base_block = None
        if isinstance(base, dict) and isinstance(base.get("n"), int):
            # Frequency is historical context. It is never a confidence, and it
            # is labelled so a client cannot render it as one by accident.
            base_block = {
                "p_confirm": base.get("p_confirm"),
                "n": base["n"],
                "interpretation": "historical_context",
                "regime_split": base.get("regime_split"),
            }
        out.append({
            "hop_id": hop_id,
            "from": hop.get("from"),
            "to": hop.get("to"),
            "sign": hop.get("sign"),
            "label": _reader_text(hop.get("label"), kind=IDENTITY,
                                  where=f"hops.{hop_id}.label", gaps=gaps),
            "condition": _reader_text(hop.get("condition"), kind=PROSE,
                                      where=f"hops.{hop_id}.condition", gaps=gaps),
            "mechanism": _reader_text(hop.get("mechanism"), kind=PROSE,
                                      where=f"hops.{hop_id}.mechanism", gaps=gaps),
            "lag_d": lag,
            "confirmed": seen.get("confirmed") if "confirmed" in seen else None,
            "confirmed_asof": seen.get("asof"),
            "value_receipt": [r for r in seen.get("value_receipt", []) if isinstance(r, dict)],
            "base_rate": base_block,
        })
    return out


def _first_blocking_leg(legs: list[dict]) -> dict[str, Any] | None:
    """The FIRST leg in path order that is not confirmed true.

    Path order, not receipt magnitude and not a score: the leg nearest the root
    is the one whose failure explains every leg behind it, whatever the size of
    the shortfall further down.
    """
    for leg in legs:
        if leg["confirmed"] is True:
            continue
        reason = {
            "observed": "condition_false",
            "unresolved": "not_resolved",
            "incomplete": "not_judged",
            "unreadable": "not_readable",
            "unobserved": "not_observed",
        }[leg["observation"]]
        return {
            "node_id": leg["node_id"],
            "index": leg["index"],
            "title": leg["title"],
            "basis": "path_order",
            "reason": reason,
            "receipts": leg["receipts"],
        }
    return None


def _contradiction(legs: list[dict], first_blocking: dict | None) -> dict[str, Any] | None:
    """Confirmed legs BEHIND the first blocker.

    This is the frozen reference case: the terminal leg reads true while the
    root is false. It is reported as a contradiction — something that needs a
    different explanation — and never as the path partly firing, because a true
    downstream leg is not evidence for the upstream one and cannot license the
    attribution the chain's name suggests.
    """
    if first_blocking is None:
        return None
    if first_blocking["reason"] != "condition_false":
        # The note this function publishes says a later leg reads true "while an
        # earlier one does not". If the earlier leg was never read, that sentence
        # is false: nothing is in tension, the coverage is simply incomplete, and
        # the state is already `unknown` for exactly that reason.
        return None
    downstream = [leg["node_id"] for leg in legs
                  if leg["index"] > first_blocking["index"] and leg["confirmed"] is True]
    if not downstream:
        return None
    return {
        "code": "downstream_true_without_upstream",
        "confirmed_downstream": downstream,
        "blocking_upstream": first_blocking["node_id"],
        "note": {
            "en": "A later leg reads true while an earlier one does not. The later "
                  "reading has its own causes; it does not activate the path and it "
                  "does not attribute back to the chain's root.",
            "zh": "后段环节为真而前段为否。后段读数有其自身成因，"
                  "既不代表路径已启动，也不能回溯归因于链条起点。",
        },
    }


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _episode_rows(episodes_raw: bytes | None, *, chain: str, rev: Any,
                  cutoff: Any = None,
                  gaps: list[dict] | None = None) -> list[dict[str, Any]]:
    """Recorded transitions for THIS chain at THIS revision.

    A row written under a different revision describes a different definition of
    the path. Presenting one as the current change is a category error: it read
    as "here is what moved" about a chain whose legs may since have been
    redefined.
    """
    rows: list[dict[str, Any]] = []
    foreign = unreadable = malformed = after_cutoff = 0
    seen_lines = 0
    truncated = False
    if episodes_raw:
        for line in episodes_raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            seen_lines += 1
            if seen_lines > MAX_EPISODE_ROWS:
                # A ledger too long to read is not a ledger full of bad rows.
                # Counting it as `malformed` told the reader the owners had
                # written corrupt data, when the truth is that this surface
                # stopped reading — a limitation of ours, disclosed as ours.
                truncated = True
                break
            try:
                row = json.loads(line)
            except ValueError:
                # Silently dropping a corrupt line hides the fact that the
                # comparison was made over an incomplete ledger.
                unreadable += 1
                continue
            if not isinstance(row, dict) or row.get("chain") != chain:
                continue
            row_rev = row.get("rev")
            if isinstance(row_rev, int) and row_rev != rev:
                foreign += 1
                continue
            if not isinstance(row.get("transition"), str) or not _is_iso_date(row.get("asof")):
                # Owner-native transition identity: a row without a transition
                # and a date is not a transition, whatever else it carries.
                malformed += 1
                continue
            if cutoff and str(row["asof"]) > str(cutoff):
                # The artifact cannot have observed a change dated after its own
                # effective date.
                after_cutoff += 1
                continue
            rows.append(row)
    if gaps is not None:
        for count, kind in ((foreign, "transitions_from_another_revision"),
                            (unreadable, "transitions_unreadable"),
                            (malformed, "transitions_malformed"),
                            (after_cutoff, "transitions_after_cutoff")):
            if count:
                gaps.append({"kind": kind, "count": count})
        if truncated:
            gaps.append({"kind": "episode_ledger_truncated",
                         "read_rows": MAX_EPISODE_ROWS,
                         "reason": "exceeds_read_bound"})
    return rows


def _what_changed(episodes_raw: bytes | None, *, chain: str, rev: Any,
                  cutoff: Any, gaps: list[dict]) -> dict[str, Any]:
    """Only OWNER-RECORDED transitions count as change.

    An empty ledger is not evidence that the underlying conditions held still —
    it is the absence of a baseline to compare against, which is a different
    statement and the only one the data supports.
    """
    rows = _episode_rows(episodes_raw, chain=chain, rev=rev, cutoff=cutoff, gaps=gaps)
    if not rows:
        return {
            "status": "comparison_unavailable",
            "reason": "no_recorded_transition",
            "items": [],
            "note": {
                "en": "The owners have recorded no transition for this path, so there "
                      "is no accepted earlier print to compare against. That is a "
                      "missing comparison, not a finding that the conditions held still.",
                "zh": "所有者未记录该路径的任何状态转换，因此没有可比对的既往认定读数。"
                      "这是比较缺失，而非条件未变动的结论。",
            },
        }
    rows.sort(key=lambda r: str(r.get("asof") or ""))
    latest = rows[-1]
    return {
        "status": "recorded_transition",
        "reason": None,
        "items": [{
            "transition": latest.get("transition"),
            "hop": latest.get("hop"),
            "asof": latest.get("asof"),
            "episode_id": latest.get("episode_id"),
            "rev": latest.get("rev", rev),
        }],
        "note": None,
    }


def _why_it_matters(hops: list[dict], contradiction: dict | None) -> dict[str, Any]:
    """Mechanism, carried through from the knowledge file — not a narrative.

    The chain's own prose says how the legs are SUPPOSED to connect. Repeating
    it is legitimate; converting it into a claim that they ARE connecting now,
    or into a market story, is not.
    """
    return {
        "basis": "chain_mechanism",
        "legs": [{
            "hop_id": hop["hop_id"],
            "mechanism": hop["mechanism"],
            "condition": hop["condition"],
            "observed": hop["confirmed"],
        } for hop in hops],
        "caution": {
            "en": "Mechanism describes how these legs are theorised to connect. It is "
                  "not a measurement that they are connecting now, and this surface "
                  "carries no rank, sizing or trade authority.",
            "zh": "机制说明的是各环节理论上的连接方式，"
                  "并非当前确实连通的度量；本页面不提供排名、仓位或交易依据。",
        },
        "contradiction_present": contradiction is not None,
    }


def _next_action(state_code: str, first_blocking: dict | None,
                 contradiction: dict | None, unobserved: list[str],
                 legs: list[dict]) -> dict[str, Any]:
    """Exactly one action, chosen by what the researcher can actually do next.

    Every branch names a ``handler`` the client actually implements and a
    ``target`` that resolves to something on the page. An action the reader
    cannot perform is a caption pretending to be a control, so there is no
    branch here for a comparison this vertical has not built: an inverse-path
    switch would need a proven inverse path, and none is defined.
    """
    titles = {leg["node_id"]: leg["title"] for leg in legs}

    def _named(node_id: str) -> dict[str, str]:
        # Reader-facing text never carries a raw node id. The title is the
        # owner's own bilingual name for that leg; falling back to the slug
        # would put an internal identifier on a customer surface.
        title = titles.get(node_id)
        return title if title else {"en": "that step", "zh": "该环节"}

    if unobserved:
        name = _named(unobserved[0])
        return {
            "code": "wait_for_named_condition",
            "handler": "focus_leg",
            "target": unobserved[0],
            "label": {"en": f"See what is missing for {name['en']}",
                      "zh": f"查看{name['zh']}缺少什么"},
        }
    if contradiction is not None:
        return {
            "code": "inspect_contradiction",
            "handler": "focus_leg",
            "target": contradiction["confirmed_downstream"][0],
            "label": {
                "en": "Inspect what is driving the later leg on its own terms",
                "zh": "按其自身逻辑查证后段环节的驱动因素",
            },
        }
    if first_blocking is not None:
        return {
            "code": "inspect_blocking_leg",
            "handler": "focus_leg",
            "target": first_blocking["node_id"],
            "label": {"en": "Open the evidence behind the first blocking leg",
                      "zh": "查看首个受阻环节背后的证据"},
        }
    return {
        "code": "open_owner_workspace",
        "handler": "open_transmission",
        "target": None,
        "label": {"en": "Open the canonical transmission surface",
                  "zh": "打开传导链规范页面"},
    }


def _evidence(episodes_raw: bytes | None, legs: list[dict], *,
              chain: str, rev: Any, cutoff: Any) -> dict[str, Any]:
    """K1 binding, plus the owner receipts that stand in its place.

    The K1 vocabulary admits ``txi.episode_transition`` as an owner store and
    lists ``txi.chain_state`` as an EXCLUDED DERIVED HEAD. So the current head
    this surface reads is not, by the contract's own terms, referenceable — and
    a path with no recorded transition has no eligible transition to reference
    either. The limitation is emitted as a machine-readable reason rather than
    papered over with a synthesised reference; a real reference is emitted only
    where a genuine eligible transition exists.
    """
    transitions = len(_episode_rows(episodes_raw, chain=chain, rev=rev, cutoff=cutoff))
    # A recorded transition is a TRANSITION. A reference is a reference that
    # resolved against the K1 contract. The first version conflated them and
    # declared K1 "available" off a row count while creating and validating no
    # EvidenceRef at all — so any JSON object carrying a matching chain name
    # manufactured evidence, and the client then hid the binding limitation.
    # This module resolves no references (building a second evidence library is
    # forbidden), so the reference count is zero and the status stays
    # unavailable; only the REASON changes once an eligible transition exists.
    k1 = {
        "status": "unavailable_for_object",
        "reason_code": ("eligible_transition_not_k1_resolved" if transitions
                        else "excluded_derived_head_no_eligible_transition"),
        "refs": [],
        "refs_count": 0,
        "recorded_transitions": transitions,
        "detail": {
            "current_head": "txi.chain_state",
            "current_head_class": "excluded_derived_head",
            "eligible_owner_store": "txi.episode_transition",
            "eligible_transitions_found": transitions,
            "resolver": "none_in_this_module",
        },
    }
    return {
        "k1": k1,
        "receipts": [{"node_id": leg["node_id"], "receipts": leg["receipts"]}
                     for leg in legs],
    }


def _clocks(observed: dict, state_doc: dict, hops: list[dict], *,
            now: datetime) -> dict[str, Any]:
    return {
        "asof": state_doc.get("asof"),
        "built": state_doc.get("built"),
        "composed_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "episode_id": observed.get("episode_id"),
        "hop_windows": [{"hop_id": hop["hop_id"], "lag_d": hop["lag_d"],
                         "confirmed_asof": hop["confirmed_asof"]} for hop in hops],
    }


#: Vocabulary that must never reach a user surface. Tripwires keep evaluating in
#: the background; what the reader is shown is what is being watched, never a
#: thesis being refuted. Enforced here rather than by prose review because the
#: text comes from owner files this surface does not control.
_REFUTATION_TERMS = ("falsif", "refut", "disprov", "invalidat", "thesis is",
                     "validated", "\u8bc1\u4f2a", "\u63a8\u7ffb", "\u5df2\u9a8c\u8bc1")

#: A lowercase_with_underscores token is an internal identifier, not English.
_SLUGLIKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


#: How a failed screen is handled depends on what the string is FOR.
#: PROSE is optional explanation — withholding it costs the reader nothing they
#: cannot get from the structured facts beside it. IDENTITY names a thing on the
#: page; blanking it silently would leave an unlabelled step, so a law violation
#: is replaced by an honest positional label and a named gap, and a merely
#: untranslated label is kept while still being reported.
PROSE = "prose"
IDENTITY = "identity"


def _screen_note(note: Any) -> tuple[dict[str, str] | None, str | None]:
    """Decide whether an owner-authored string may be shown to a reader.

    Measured against the live WTI chain, one falsifier note carried three
    defects at once: the word "falsified" on a user surface, the raw node id
    `yield_rise`, and no Chinese at all — so a zh reader was served untranslated
    English. But the note was never the only way in. An adversarial pass put the
    same words into `path.title`, a node title, a hop label, a hop mechanism and
    an exposure-screen note, and every one of them reached the reader, because
    the screen guarded exactly one field. The live chain is clean in those
    fields TODAY, which is precisely why testing against it gave false comfort:
    the leak fires the first time somebody edits a knowledge file. Every
    owner-authored string a reader can see now goes through here.
    """
    pair = _bilingual(note)
    if pair is None:
        return None, "absent"
    blob = f"{pair['en']} {pair['zh']}".lower()
    if any(term in blob for term in _REFUTATION_TERMS):
        return None, "refutation_vocabulary"
    if _SLUGLIKE.search(blob):
        return None, "raw_identifier"
    if pair["zh"] == pair["en"]:
        return None, "untranslated"
    return pair, None


def _reader_text(value: Any, *, kind: str, where: str, gaps: list[dict],
                 fallback: dict[str, str] | None = None) -> dict[str, str] | None:
    """Screen one owner-authored string on its way to the reader."""
    pair, reason = _screen_note(value)
    if reason is None:
        return pair
    if reason == "absent":
        return fallback
    if reason == "untranslated" and kind == IDENTITY:
        # A short label that was never translated is a content-quality defect,
        # not a law violation. Blanking the path title over it would make the
        # page unusable, so it is kept and reported.
        gaps.append({"kind": "text_untranslated", "where": where})
        return _bilingual(value)
    gaps.append({"kind": "text_withheld", "where": where, "reason": reason})
    return fallback


_GAP_WHERE_LABELS = (
    ("nodes.", ".title", {"en": "A step's name", "zh": "某环节的名称"}),
    ("hops.", ".label", {"en": "A link's name", "zh": "某链接的名称"}),
    ("hops.", ".condition", {"en": "A link's condition", "zh": "某链接的条件"}),
    ("hops.", ".mechanism", {"en": "A link's mechanism note", "zh": "某链接的机制说明"}),
    ("exposure_screens.", ".label", {"en": "An exposure name", "zh": "某敞口类别名称"}),
    ("exposure_screens.", ".note", {"en": "An exposure note", "zh": "某敞口类别说明"}),
)

_GAP_WHERE_EXACT = {
    "title": {"en": "The path name", "zh": "路径名称"},
    "state_label": {"en": "The state name", "zh": "状态名称"},
    "chain_state.built": {"en": "The artifact build stamp", "zh": "产物构建时间戳"},
    "chain_state.asof": {"en": "The reading date", "zh": "读数日期"},
}

_GAP_REASON_LABELS = {
    "refutation_vocabulary": {
        "en": "worded as a verdict on the thesis rather than as a condition",
        "zh": "措辞是对论点的裁定，而非对条件的描述"},
    "raw_identifier": {"en": "contains an internal identifier",
                       "zh": "含有内部标识符"},
    "untranslated": {"en": "published in one language only", "zh": "仅以单一语言发布"},
    "exceeds_read_bound": {"en": "longer than this page reads in one request",
                           "zh": "长度超出本页面单次请求的读取上限"},
    "confirmed_not_boolean": {"en": "the recorded verdict is not a true/false value",
                              "zh": "已记录的判定不是真/假值"},
}


def _gap_where_label(where: Any) -> dict[str, str] | None:
    """A reader-facing name for the place a gap sits.

    The machine path stays on the payload for machine consumers, but it cannot
    be what the page prints: `falsifiers[0].note` is an internal field path AND
    carries the refutation family this product forbids on a reader surface, so
    printing it to make the gap "reachable" would trade one law for another.
    The label names the location by family, never by node id.
    """
    if not isinstance(where, str) or not where:
        return None
    exact = _GAP_WHERE_EXACT.get(where)
    if exact is not None:
        return dict(exact)
    if where.startswith("falsifiers[") and where.endswith("].note"):
        inner = where[len("falsifiers["):-len("].note")]
        if inner.isdigit():
            n = int(inner) + 1
            return {"en": f"What we are watching \u00b7 note {n}",
                    "zh": f"我们正在观察 \u00b7 备注 {n}"}
        return {"en": "What we are watching", "zh": "我们正在观察"}
    for prefix, suffix, label in _GAP_WHERE_LABELS:
        if where.startswith(prefix) and where.endswith(suffix):
            return dict(label)
    return None


def _label_gaps(gaps: list[dict], legs: list[dict]) -> None:
    """Give every gap a reader-facing location and reason, in place.

    Done as one pass over the finished list rather than at each append site, so
    a gap minted by a future code path cannot arrive unlabelled and fall back to
    printing its raw field path.
    """
    by_node = {leg["node_id"]: leg for leg in legs}
    for gap in gaps:
        node_id = gap.get("node_id")
        if node_id is not None and "where_label" not in gap:
            leg = by_node.get(node_id)
            if leg is not None:
                title = leg.get("title") or {}
                gap["where_label"] = {
                    "en": f"Step {leg['index']} \u00b7 {title.get('en', '')}".strip(" \u00b7"),
                    "zh": f"第 {leg['index']} 环节 \u00b7 {title.get('zh', '')}".strip(" \u00b7"),
                }
            else:
                # The step is not on the page at all, which is itself the gap.
                # Naming it by slug would put an internal id on the surface.
                gap["where_label"] = {"en": "A step not shown on this page",
                                      "zh": "未在本页面展示的环节"}
        if "where_label" not in gap:
            label = _gap_where_label(gap.get("where"))
            if label is not None:
                gap["where_label"] = label
        reason = gap.get("reason")
        if isinstance(reason, str) and "reason_label" not in gap:
            known = _GAP_REASON_LABELS.get(reason)
            if known is not None:
                gap["reason_label"] = dict(known)


def _watched_condition(when: Any) -> dict[str, Any] | None:
    """The condition itself, as facts rather than as prose."""
    if not isinstance(when, dict):
        return None
    return {
        "series": when.get("series"),
        "vs": when.get("vs"),
        "metric": when.get("metric"),
        "window": when.get("window"),
        "op": when.get("op"),
        "value": when.get("value"),
    }


def _invalidators(definition: dict, gaps: list[dict]) -> list[dict[str, Any]]:
    raw = definition.get("falsifiers")
    if not isinstance(raw, list) or not raw:
        gaps.append({"kind": "invalidators_absent"})
        return []
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        note, withheld = _screen_note(item.get("note"))
        if withheld and withheld != "absent":
            # Every reader-facing withholding is visible in ONE place. The
            # per-invalidator fields below stay for machine consumers, but a
            # reader who is shown the condition instead of the note is entitled
            # to find out why in the same list as every other named gap.
            gaps.append({"kind": "text_withheld",
                         "where": f"falsifiers[{i}].note", "reason": withheld})
        out.append({
            "id": f"invalidator_{i}",
            "when": item.get("when"),
            "watched": _watched_condition(item.get("when")),
            "src": item.get("src"),
            "note": note,
            "note_status": "published" if note else "withheld",
            "note_withheld_reason": withheld,
        })
    return out


def _exposure_screens(definition: dict, gaps: list[dict]) -> list[dict[str, Any]]:
    """The knowledge file's `exposure_screens` — and nothing more.

    These are valuation / refinancing / capex / FCF EXPOSURE context: which kinds
    of company the leg would bear on. They are not permission to display source
    data. Mapping them to a field called `rights` invented a license status the
    owners never granted, and put it where a reader would take it for one.
    Display permission is decided by the existing entitlement policy, not here,
    so this surface reports it as undetermined rather than answering it.
    """
    raw = definition.get("exposure_screens")
    if not isinstance(raw, dict) or not raw:
        gaps.append({"kind": "exposure_screens_absent"})
        return []
    return [{
        "id": key,
        "label": _reader_text(screen.get("label"), kind=IDENTITY,
                              where=f"exposure_screens.{key}.label", gaps=gaps,
                              fallback={"en": "Unnamed screen", "zh": "\u672a\u547d\u540d\u7b5b\u9009"}),
        "note": _reader_text(screen.get("note"), kind=PROSE,
                             where=f"exposure_screens.{key}.note", gaps=gaps),
    } for key, screen in raw.items() if isinstance(screen, dict)]


def _parse_build_stamp(built: Any) -> datetime | None:
    """Parse the owner's build stamp, or return None.

    The compiled artifact stamps ``built`` in the house format
    ``"2026-09-05 02:10 UTC"``, which ``fromisoformat`` cannot read. An earlier
    revision of this function caught that failure and fell back to an age of
    zero — which renders as "built just now", the most reassuring possible
    reading of a stamp it had failed to understand. Returning None instead is
    the whole point: an age that cannot be computed is reported as absent.
    """
    text = str(built or "").strip()
    if not text:
        return None
    for parse in (
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
        lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC),
        lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=UTC),
    ):
        try:
            stamp = parse(text)
        except (TypeError, ValueError):
            continue
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    return None


def _source_block(definition: dict, state_doc: dict, observed: dict, *,
                  chain: str, now: datetime, gaps: list[dict]) -> dict[str, Any]:
    built = state_doc.get("built")
    stamp = _parse_build_stamp(built)
    if stamp is None:
        age_seconds, age_basis = None, "unparseable_build_stamp"
    else:
        delta = (now - stamp).total_seconds()
        if delta < 0:
            # `max(0, ...)` re-opened the very defect the parser above was written
            # to close: a stamp we cannot make sense of rendering as "built just
            # now". A stamp in the future is not an age of zero.
            age_seconds, age_basis = None, "build_stamp_in_future"
            gaps.append({"kind": "build_stamp_in_future", "where": "chain_state.built"})
        else:
            age_seconds, age_basis = int(delta), "chain_state.built"
    observation_age_days: int | None = None
    try:
        observed_on = datetime.strptime(str(state_doc.get("asof")), "%Y-%m-%d").replace(tzinfo=UTC)
        observation_age_days = max(0, (now - observed_on).days)
    except (TypeError, ValueError):
        gaps.append({"kind": "unparseable_observation_date", "where": "chain_state.asof"})
    return {
        "chain": chain,
        "rev": observed.get("rev"),
        "state_schema": state_doc.get("schema"),
        "asof": state_doc.get("asof"),
        "built": built,
        "receipt_kind": "composed_read",
        "composer_method": COMPOSER_METHOD,
        "reads": [],
        "source_manifest_hash": None,
        "freshness": {
            # This process can measure how old the artifact IN THIS CHECKOUT is.
            # It cannot see what the deployed canonical surface is serving, and
            # the deployed checkout may lag in either direction, so no comparison
            # is asserted.
            "status": "verification_unavailable",
            "compared_against": None,
            # Two different clocks, deliberately separated. GENERATION age is how
            # long ago this artifact was built; OBSERVATION age is how old the
            # data it observed is. A freshly generated old observation is not a
            # current one, and reporting only the first would say it was.
            "source_age_seconds": age_seconds,
            "source_age_basis": age_basis,
            "generation_age_seconds": age_seconds,
            "generation_age_basis": age_basis,
            "observation_asof": state_doc.get("asof"),
            "observation_age_days": observation_age_days,
            "observation_age_basis": ("chain_state.asof" if observation_age_days is not None
                                      else "unparseable_asof"),
            "note": {
                "en": "Age is measured against this build's own artifact stamp. Whether "
                      "it matches what the canonical transmission page is serving cannot "
                      "be observed from here.",
                "zh": "此处的时效以本次构建自身的产物时间戳衡量；"
                      "能否与规范传导页面所提供的内容一致，无法在此判定。",
            },
        },
    }
