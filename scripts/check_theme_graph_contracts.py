"""Guard: the theme graph's edge contract holds (law_id ``theme_graph.edge_contract``).

WHAT IT PROTECTS. The graph is the substrate every later GMI wave reads, and its
failure modes are all quiet ones — a column that drifted, an evidence ref pointing at
nothing, a closed interval that stopped resolving, an identity epoch nobody ratified.
None of those raise; they just make the answers wrong. So they are checked structurally,
against the committed contracts in ``contracts/theme_graph/``.

CHECKS
  1. Exact column set AND order on all three stores, plus dtype families.
  2. jsonschema on an evenly-spaced sample (<=200 rows per store) — the schemas are the
     contract, not a hand-copied field list — plus a VECTORIZED full-scan for every enum
     and for the company-id grammar, so a bad row outside the sample cannot hide.
  3. Semantic leakage, general form (masterplan §4.4): every edge carries >=1
     evidence_ref, and every ref resolves to an evidence row with a parseable dated
     ``published_at``. Undatable evidence is knowledge from nowhere.
  4. ``source_class=llm_proposed_ratified`` with no dated evidence is refused. Zero such
     rows exist today; the check is structural on purpose — the point is that the first
     one cannot land quietly.
  5. ``identity_epoch >= 2`` requires a matching ratified row in
     ``config/theme_graph_identity_breaks.yml``. A builder may not decide on its own
     that two listings are different companies.
  6. Closed-edge survivorship: every edge_id that appears anywhere in the FULL history
     carrying a ``valid_to`` still resolves in the latest-belief view. A closed
     membership must be findable, not merely absent.

VERDICTS. A missing store is INDETERMINATE (``::notice``, rc 0) — a sparse checkout
carries no ``data/``, and the state before the first run is not a breach. A breach
prints one ``::warning`` and returns 0 by default (advisory, so a nightly collect lane
is never taken down by a display-tier plane); ``--strict`` turns breaches into rc 1 for
CI. ``--selftest`` rebuilds each incident as a fixture and proves the guard still sees it.

Run: python -m scripts.check_theme_graph_contracts [--strict] [--selftest]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import identity, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("check_theme_graph_contracts")

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts" / "theme_graph"
SAMPLE_MAX = 200

#: column -> dtype family. "str"/"int"/"bool" are enforced on NON-NULL values only, so
#: an all-null reserved column (the W2 exposure axes) is not forced into a type it will
#: only acquire when it is measured.
NODE_DTYPES: dict[str, str] = {
    "node_id": "str", "kind": "str", "name_en": "str", "name_zh": "str",
    "market_scope": "str", "tier": "str", "status": "str", "merged_into": "str",
    "birth_date": "str", "retire_date": "str", "identity_epoch": "int",
    "external_ids": "str", "provenance": "str", "computed_at": "str",
    "engine_version": "str",
}
EDGE_DTYPES: dict[str, str] = {
    "edge_id": "str", "type": "str", "src": "str", "dst": "str", "valid_from": "str",
    "valid_to": "str", "evidence_time": "str", "belief_time": "str", "era": "str",
    "source_class": "str", "date_provenance": "str", "evidence_refs": "list",
    "confidence_basis": "str",
    "economic_share": "num", "trading_beta": "num", "attention_share": "num",
    "economic_share_formula_id": "str", "trading_beta_formula_id": "str",
    "attention_share_formula_id": "str", "economic_share_display": "str",
    "trading_beta_display": "str", "attention_share_display": "str",
    "computed_at": "str", "engine_version": "str",
}
EVIDENCE_DTYPES: dict[str, str] = {
    "evidence_id": "str", "kind": "str", "published_at": "str", "effective_at": "str",
    "source_ref": "str", "licensing_internal_ok": "bool",
    "licensing_display_ok": "bool", "licensing_redistribution_ok": "bool",
    "retention": "str", "computed_at": "str",
}

#: Enum columns scanned in FULL (the sample proves shape, the scan proves values).
NODE_ENUMS: dict[str, set[str]] = {
    "kind": {"theme", "company", "etf", "catalyst", "policy_program", "commodity",
             "participant_class", "market", "basket"},
    "status": {"candidate", "canonical", "retired", "merged"},
}
EDGE_ENUMS: dict[str, set[str]] = {
    "type": {"MEMBER_OF", "EXPRESSES", "SAME_AS", "TRANSLATES_TO", "PARENT_OF",
             "RELATED", "SUPPLIES", "ENABLES", "BOTTLENECK_OF", "BENEFITS_FROM",
             "CATALYST_OF", "TRACKS", "HEDGES"},
    "era": {"reconstruction", "observed"},
    "source_class": {"curated", "scrape", "filing", "co_movement",
                     "llm_proposed_ratified"},
    "date_provenance": {"curated_changelog", "seed_constant", "raw_snapshot",
                        "crosswalk"},
    "economic_share_display": {"none", "weak", "core"},
    "trading_beta_display": {"none", "weak", "core"},
    "attention_share_display": {"none", "weak", "core"},
}
EVIDENCE_ENUMS: dict[str, set[str]] = {
    "kind": {"filing", "xbrl", "8k_counterparty", "scrape_receipt", "scrape",
             "news_item", "operator_curation", "comovement_stat"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_null(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, tuple, set)) or hasattr(v, "__len__") and not isinstance(v, str):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):  # pragma: no cover — exotic scalars
        return False


def _jsonable(row: dict) -> dict:
    """A parquet row as plain JSON types, so jsonschema sees what the contract describes."""
    out: dict = {}
    for k, v in row.items():
        if hasattr(v, "tolist") and not isinstance(v, str):
            v = v.tolist()
        if isinstance(v, (list, tuple)):
            out[k] = [None if x is None else str(x) for x in v]
        elif _is_null(v):
            out[k] = None
        elif isinstance(v, bool):
            out[k] = bool(v)
        elif hasattr(v, "item") and not isinstance(v, str):
            out[k] = v.item()
        else:
            out[k] = v
    return out


def _sample(df: pd.DataFrame, n: int = SAMPLE_MAX) -> pd.DataFrame:
    """Evenly-spaced rows — deterministic, so a failure reproduces on the next run."""
    if len(df) <= n:
        return df
    step = max(1, len(df) // n)
    return df.iloc[::step].head(n)


def _dated(v: object) -> bool:
    if _is_null(v):
        return False
    try:
        date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return False
    return True


def _check_columns(df: pd.DataFrame, expected: tuple[str, ...], label: str) -> list[str]:
    got = tuple(df.columns)
    if got == expected:
        return []
    missing = [c for c in expected if c not in got]
    extra = [c for c in got if c not in expected]
    if missing or extra:
        return [f"{label}: column set drift — missing {missing}, unexpected {extra}"]
    return [f"{label}: column ORDER drift — the writer's column tuple is the contract "
            f"(got {list(got)})"]


def _check_dtypes(df: pd.DataFrame, families: dict[str, str], label: str) -> list[str]:
    out: list[str] = []
    for col, fam in families.items():
        if col not in df.columns:
            continue
        values = [v for v in df[col].tolist() if not _is_null(v)]
        if not values:
            continue
        if fam == "str":
            bad = [v for v in values if not isinstance(v, str)]
        elif fam == "int":
            bad = [v for v in values if isinstance(v, bool) or not float(v).is_integer()]
        elif fam == "bool":
            bad = [v for v in values if not isinstance(v, (bool,))]
        elif fam == "num":
            bad = [v for v in values if isinstance(v, (str, bytes))]
        elif fam == "list":
            bad = [v for v in values if isinstance(v, (str, bytes))
                   or not hasattr(v, "__len__")]
        else:  # pragma: no cover — unknown family is a coding error
            bad = []
        if bad:
            out.append(f"{label}.{col}: {len(bad)} value(s) are not {fam} "
                       f"(first: {bad[0]!r})")
    return out


def _check_enums(df: pd.DataFrame, enums: dict[str, set[str]], label: str) -> list[str]:
    out: list[str] = []
    for col, allowed in enums.items():
        if col not in df.columns:
            continue
        seen = {str(v) for v in df[col].tolist() if not _is_null(v)}
        bad = sorted(seen - allowed)
        if bad:
            out.append(f"{label}.{col}: values outside the contract enum: {bad}")
    return out


def _check_schema(df: pd.DataFrame, schema_name: str, label: str) -> list[str]:
    path = CONTRACTS / f"{schema_name}.v1.schema.json"
    if not path.exists():
        return [f"{label}: contract {path.name} is missing — the schema IS the contract"]
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:  # pragma: no cover — CI installs it
        return []
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    out: list[str] = []
    for rec in _sample(df).to_dict("records"):
        errs = sorted(validator.iter_errors(_jsonable(rec)), key=lambda e: e.path)
        if errs:
            out.append(f"{label}: row {rec.get(df.columns[0])!r} violates "
                       f"{path.name}: {errs[0].message}")
            if len(out) >= 5:
                break
    return out


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(store_dir: Path, breaks_file: Path) -> tuple[list[str], list[str]]:
    """(breaches, notices) for the store rooted at ``store_dir``."""
    breaches: list[str] = []
    notices: list[str] = []

    paths = {"nodes": store_dir / "nodes.parquet",
             "edges": store_dir / "edges.parquet",
             "evidence": store_dir / "evidence.parquet"}
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        notices.append(
            f"theme graph store incomplete at {store_dir} (missing: {', '.join(missing)})"
            " — pre-first-run and sparse checkouts are INDETERMINATE, never a breach")
        return breaches, notices

    frames: dict[str, pd.DataFrame] = {}
    for key, p in paths.items():
        try:
            frames[key] = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            breaches.append(f"{key}.parquet unreadable: {exc}")
    if breaches:
        return breaches, notices
    nodes, edges, evidence = frames["nodes"], frames["edges"], frames["evidence"]

    breaches += _check_columns(nodes, store.NODE_COLUMNS, "nodes")
    breaches += _check_columns(edges, store.EDGE_COLUMNS, "edges")
    breaches += _check_columns(evidence, store.EVIDENCE_COLUMNS, "evidence")
    breaches += _check_dtypes(nodes, NODE_DTYPES, "nodes")
    breaches += _check_dtypes(edges, EDGE_DTYPES, "edges")
    breaches += _check_dtypes(evidence, EVIDENCE_DTYPES, "evidence")
    breaches += _check_enums(nodes, NODE_ENUMS, "nodes")
    breaches += _check_enums(edges, EDGE_ENUMS, "edges")
    breaches += _check_enums(evidence, EVIDENCE_ENUMS, "evidence")
    breaches += _check_schema(nodes, "nodes", "nodes")
    breaches += _check_schema(edges, "edges", "edges")
    breaches += _check_schema(evidence, "evidence", "evidence")

    # --- company id grammar, full scan --------------------------------------
    if "kind" in nodes.columns and "node_id" in nodes.columns:
        co = nodes[nodes["kind"].astype(str) == "company"]["node_id"].astype(str)
        bad = sorted(co[~co.str.match(identity.COMPANY_ID_RE)].tolist())
        if bad:
            breaches.append(
                f"{len(bad)} company node id(s) outside the permanent-identity grammar "
                f"{identity.COMPANY_ID_RE.pattern} (first: {bad[0]!r})")

    # --- semantic leakage: every edge cites dated evidence -------------------
    dated_ids: set[str] = set()
    if {"evidence_id", "published_at"} <= set(evidence.columns):
        for eid, pub in zip(evidence["evidence_id"], evidence["published_at"]):
            if _dated(pub):
                dated_ids.add(str(eid))
    known_ids = {str(v) for v in evidence.get("evidence_id", pd.Series(dtype=object))}

    no_refs, orphan, undated, llm_bad = [], [], [], []
    for row in edges.to_dict("records"):
        refs = row.get("evidence_refs")
        refs = list(refs) if refs is not None and not _is_null(refs) else []
        refs = [str(r) for r in refs]
        eid = str(row.get("edge_id"))
        if not refs:
            no_refs.append(eid)
            continue
        if not any(r in known_ids for r in refs):
            orphan.append(eid)
            continue
        if not any(r in dated_ids for r in refs):
            undated.append(eid)
        if str(row.get("source_class")) == "llm_proposed_ratified" \
                and not any(r in dated_ids for r in refs):
            llm_bad.append(eid)
    for label, bad in (("carry no evidence_ref at all", no_refs),
                       ("cite an evidence_id that resolves to no evidence row", orphan),
                       ("cite no evidence row with a parseable dated published_at", undated)):
        if bad:
            breaches.append(f"{len(bad)} edge(s) {label} (first: {bad[0]!r}) — "
                            f"an edge whose evidence cannot be dated is knowledge from "
                            f"nowhere (semantic-leakage law, §4.4)")
    if llm_bad:
        breaches.append(
            f"{len(llm_bad)} llm_proposed_ratified edge(s) with no dated evidence "
            f"(first: {llm_bad[0]!r}) — an LLM-assisted edge may cite only dated "
            f"documents (G0.6)")

    # --- identity epochs are ratified, not minted ---------------------------
    ratified: set[tuple[str, str]] = set()
    if breaks_file.exists():
        doc = yaml.safe_load(breaks_file.read_text(encoding="utf-8")) or {}
        for r in doc.get("breaks") or []:
            ratified.add((str(r.get("market", "")).strip().lower(),
                          str(r.get("symbol", "")).strip().upper(),))
    if {"identity_epoch", "node_id"} <= set(nodes.columns):
        for row in nodes.to_dict("records"):
            try:
                epoch = int(row.get("identity_epoch") or 1)
            except (TypeError, ValueError):
                breaches.append(f"node {row.get('node_id')!r}: unreadable identity_epoch")
                continue
            if epoch < 2:
                continue
            nid = str(row.get("node_id"))
            parts = nid.split(":")
            market = parts[1] if len(parts) > 2 else ""
            symbol = parts[2].split("#")[0].upper() if len(parts) > 2 else ""
            if (market, symbol) not in ratified:
                breaches.append(
                    f"node {nid!r} claims identity_epoch {epoch} with no ratified row in "
                    f"{breaks_file.name} — an identity break is a curated act, never a "
                    f"builder's decision")

    # --- closed-edge survivorship -------------------------------------------
    if {"edge_id", "valid_to", "belief_time"} <= set(edges.columns):
        closed = {str(e) for e, v in zip(edges["edge_id"], edges["valid_to"])
                  if not _is_null(v)}
        if closed:
            ordered = edges.sort_values(["edge_id", "belief_time", "computed_at"],
                                        kind="stable")
            latest = ordered.drop_duplicates(subset=["edge_id"], keep="last")
            resolvable = {str(e) for e in latest["edge_id"]}
            vanished = sorted(closed - resolvable)
            if vanished:
                breaches.append(
                    f"{len(vanished)} closed edge(s) do not resolve in the latest-belief "
                    f"view (first: {vanished[0]!r}) — a closed membership must stay "
                    f"findable; dead members never leave the denominator")

    return breaches, notices


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run(*, strict: bool, store_dir: Path | None = None,
        breaks_file: Path | None = None) -> int:
    sdir = store_dir or store.store_dir()
    bfile = breaks_file or identity.breaks_path()
    breaches, notices = audit(sdir, bfile)
    for n in notices:
        # Bare print, line-start, flushed: a logger prefixes the line and GitHub
        # silently drops the annotation (tests/test_gh_annotation_line_start.py).
        print(f"::notice title=theme graph indeterminate::{n}", flush=True)
    if not breaches:
        if not notices:
            print("theme graph contracts OK — columns, schemas, enums, evidence "
                  "resolution, identity epochs and closed-edge survivorship all hold")
        return 0
    print("::warning title=theme graph contract breach::"
          + "; ".join(breaches[:8])
          + (f" (+{len(breaches) - 8} more)" if len(breaches) > 8 else "")
          + ". The graph is display-tier, so nothing decides on it — but every one of "
            "these is a QUIET failure: a drifted column, an evidence ref pointing at "
            "nothing, or a closed membership that stopped resolving does not raise, it "
            "just makes the answers wrong.", flush=True)
    return 1 if strict else 0


# ---------------------------------------------------------------------------
# Selftest — each incident rebuilt as a fixture
# ---------------------------------------------------------------------------

def _fixture(tmp: Path, *, nodes: list[dict], edges: list[dict],
             evidence: list[dict]) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(nodes).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
        tmp / "nodes.parquet", index=False)
    pd.DataFrame(edges).reindex(columns=list(store.EDGE_COLUMNS)).to_parquet(
        tmp / "edges.parquet", index=False)
    pd.DataFrame(evidence).reindex(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
        tmp / "evidence.parquet", index=False)
    return tmp


def _clean_rows() -> tuple[list[dict], list[dict], list[dict]]:
    """A minimal, contract-clean store. Dates are FIXTURE constants with no relation to
    the wall clock — a guard that drifts red on a calendar boundary is a scheduled red."""
    stamp = "2024-01-02T00:00:00Z"
    ev = [{"evidence_id": "ev:0000000000000001", "kind": "operator_curation",
           "published_at": "2024-01-01", "effective_at": None,
           "source_ref": "fixture://membership.json",
           "licensing_internal_ok": True, "licensing_display_ok": True,
           "licensing_redistribution_ok": True, "retention": None,
           "computed_at": stamp}]
    nodes = [
        {"node_id": "co:us:AAA", "kind": "company", "name_en": "AAA", "name_zh": None,
         "market_scope": "us", "tier": None, "status": "canonical", "merged_into": None,
         "birth_date": None, "retire_date": None, "identity_epoch": 1,
         "external_ids": "{}", "provenance": "fixture", "computed_at": stamp,
         "engine_version": store.ENGINE_VERSION},
        {"node_id": "basket:baskets:demo", "kind": "basket", "name_en": "Demo",
         "name_zh": None, "market_scope": "us", "tier": None, "status": "canonical",
         "merged_into": None, "birth_date": None, "retire_date": None,
         "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
         "computed_at": stamp, "engine_version": store.ENGINE_VERSION},
    ]
    edge = {"edge_id": "member_of:co:us:AAA->basket:baskets:demo@2024-01-01",
            "type": "MEMBER_OF", "src": "co:us:AAA", "dst": "basket:baskets:demo",
            "valid_from": "2024-01-01", "valid_to": None, "evidence_time": "2024-01-01",
            "belief_time": "2024-01-02", "era": "reconstruction",
            "source_class": "curated", "date_provenance": "curated_changelog",
            "evidence_refs": ["ev:0000000000000001"],
            "confidence_basis": "membership_doc.v1",
            "computed_at": stamp, "engine_version": store.ENGINE_VERSION}
    for f in store.RESERVED_EDGE_FIELDS:
        edge[f] = None
    return nodes, [edge], ev


def selftest(tmp_root: Path | None = None) -> int:
    import tempfile  # noqa: PLC0415

    tmp_root = tmp_root or Path(tempfile.mkdtemp(prefix="theme_graph_selftest_"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    empty_breaks = tmp_root / "no_breaks.yml"
    empty_breaks.write_text("breaks: []\n", encoding="utf-8")
    checks: list[tuple[bool, str]] = []

    nodes, edges, ev = _clean_rows()
    clean = _fixture(tmp_root / "clean", nodes=nodes, edges=edges, evidence=ev)
    b, n = audit(clean, empty_breaks)
    checks.append((not b and not n, f"a contract-clean store must pass cleanly: {b or n}"))

    b, n = audit(tmp_root / "absent", empty_breaks)
    checks.append((not b and bool(n),
                   "a missing store is INDETERMINATE, never a breach"))

    nodes, edges, ev = _clean_rows()
    edges[0]["evidence_refs"] = ["ev:doesnotexist0000"]
    d = _fixture(tmp_root / "orphan", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("resolves to no evidence row" in x for x in audit(d, empty_breaks)[0]),
                   "an evidence ref pointing at nothing must breach"))

    nodes, edges, ev = _clean_rows()
    ev[0]["published_at"] = "not-a-date"
    edges[0]["source_class"] = "llm_proposed_ratified"
    d = _fixture(tmp_root / "llm", nodes=nodes, edges=edges, evidence=ev)
    breaches = audit(d, empty_breaks)[0]
    checks.append((any("llm_proposed_ratified" in x for x in breaches),
                   "an LLM-ratified edge with undated evidence must breach"))
    checks.append((any("dated published_at" in x for x in breaches),
                   "undated evidence must breach for ANY source_class, not only LLM ones"))

    nodes, edges, ev = _clean_rows()
    nodes[0]["identity_epoch"] = 2
    nodes[0]["node_id"] = "co:us:AAA#2"
    edges[0]["src"] = "co:us:AAA#2"
    edges[0]["edge_id"] = "member_of:co:us:AAA#2->basket:baskets:demo@2024-01-01"
    d = _fixture(tmp_root / "epoch", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("no ratified row" in x for x in audit(d, empty_breaks)[0]),
                   "identity_epoch 2 without a ratified break row must breach"))

    # A closed edge that no longer resolves: a LATER belief re-opened the same edge_id,
    # so the closure exists in history but not in the view any consumer reads.
    nodes, edges, ev = _clean_rows()
    closed = dict(edges[0])
    closed["valid_to"] = "2024-02-01"
    closed["belief_time"] = "2024-02-02"
    closed["edge_id"] = "member_of:co:us:AAA->basket:baskets:demo@2024-01-02"
    d = _fixture(tmp_root / "vanished", nodes=nodes, edges=[*edges, closed], evidence=ev)
    before = audit(d, empty_breaks)[0]
    checks.append((not before, f"the two-row control must be clean: {before}"))
    dropped = pd.read_parquet(d / "edges.parquet")
    dropped = dropped[dropped["valid_to"].isna()]
    survivor = dict(closed)
    survivor["valid_to"] = None
    survivor["belief_time"] = "2024-03-03"
    d2 = _fixture(tmp_root / "vanished2", nodes=nodes,
                  edges=[*dropped.to_dict("records"), closed], evidence=ev)
    pd.DataFrame([*dropped.to_dict("records"), closed, survivor]).reindex(
        columns=list(store.EDGE_COLUMNS)).to_parquet(d2 / "edges.parquet", index=False)
    checks.append((not audit(d2, empty_breaks)[0],
                   "a re-opened edge is legal — the closure row survives on disk"))

    bad = [m for ok, m in checks if not ok]
    for m in bad:
        print(f"selftest FAIL: {m}")
    print("check_theme_graph_contracts selftest: "
          + ("OK" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="return 1 on a breach (CI); default is advisory rc 0")
    ap.add_argument("--selftest", action="store_true",
                    help="rebuild each incident as a fixture and prove the guard sees it")
    a = ap.parse_args(argv)
    return selftest() if a.selftest else run(strict=a.strict)


if __name__ == "__main__":
    raise SystemExit(main())
