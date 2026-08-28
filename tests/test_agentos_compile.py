"""Agent OS Phase 3 — `agentos.py compile-context`.

A context bundle is TESTIMONY: a session acts on it without opening the sources.  So the
properties worth pinning are the ones that make it trustworthy rather than merely
plausible, and every one of them is asserted against a NEGATIVE fixture — an exclusion
rule with nothing to exclude is untested, and reads identically to no rule at all.

* **Every line is cited.**  On the real seeded store, every item in every section carries
  a `path` and a `why_included`.  An uncited line is a claim the reader cannot check.
* **Exclusion is by FIELD and is NAMED.**  A superseded decision, an expired discovery,
  an uncited-and-stale discovery, an older handoff and a malformed record each land in
  `excluded` with the specific reason — never silently absent, never co-equal in a
  section.
* **The boundary is structural.**  Records belonging to another program cannot appear at
  all: search hits only VOTE for a workstream, and content comes from the graph walk.
* **The cap is honest, and it never costs a constraint.**  When the budget binds,
  `omitted_due_to_budget` is a LIST with token costs, and the bundle still fits.  A silent
  truncation reads exactly like a smaller store.  HIGHER LAW is exempt from the cap
  alongside the workstream block: a bundle that spent its last tokens on file pointers
  while dropping the rows a session may not violate is worse than one that overran.
* **I4, both directions.**  Naming an unknown or malformed workstream exits 1
  (fail-CLOSED on schema); a missing sibling repo, a missing active_builds.json and a
  missing index all exit 0 with `degraded` populated (fail-OPEN on join).
* **I1 and read-only.**  Nothing here can gate anything, and the store is byte-identical
  after a run.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "agentos"
CLI = REPO / "scripts" / "agentos.py"

FROZEN = "2026-08-12T14:00:00Z"
SEED_KEYS = (
    sorted(path.stem[3:] for path in (STORE / "workstreams").glob("WS-*.md"))
    if STORE.exists() else []
)

# Agent worktrees here are frequently CONE-MODE SPARSE, and a directory outside the cone
# is simply absent.  CI checks out the full tree, so this never skips there.  The guard is
# on the KEY LIST, not merely on the directory: a cone that carries `agentos/` but not
# `agentos/workstreams/` leaves SEED_KEYS empty, and the tests that index `SEED_KEYS[0]`
# would then die with IndexError — a crash that reads like a broken compiler rather than a
# partial checkout.
pytestmark = [
    pytest.mark.skipif(
        not STORE.exists(),
        reason="agentos/ outside this sparse checkout — run: git sparse-checkout add agentos",
    ),
    pytest.mark.skipif(
        not SEED_KEYS,
        reason="agentos/workstreams/ holds no records in this checkout — "
               "run: git sparse-checkout add agentos",
    ),
]


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI with the sibling checkouts pinned ABSENT.

    Otherwise the result depends on which repos happen to exist on the machine running
    the suite — green here and red on a runner, or the reverse.
    """
    environ = dict(os.environ)
    environ.setdefault("MACRO_TERMINAL_REPO", "/nonexistent-terminal-checkout")
    environ.setdefault("MACRO_MASTERMIND_REPO", "/nonexistent-mastermind-checkout")
    if env:
        environ.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, cwd=REPO, env=environ,
    )


def _compile(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return _run("compile-context", "--now", FROZEN, *args, **kwargs)


def _bundle(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _load_cli():
    """Import scripts/agentos.py as a module, so the search seam can be injected."""
    spec = importlib.util.spec_from_file_location("agentos_compile_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _items(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for section in bundle["sections"] for item in section["items"]]


def _section(bundle: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(section for section in bundle["sections"] if section["id"] == ident)


def _tokens(item: dict[str, Any]) -> int:
    """One item's packing cost, MIRRORED not imported.

    Importing the estimator under test would make the budget arithmetic here agree with
    the compiler by construction — including when both are wrong.  The WHOLE item is
    priced, not its excerpt: path, locator, why_included, kind, key, status and
    authority_class ship with it, and they are most of a short item's bytes.
    """
    return max(1, len(json.dumps(item, ensure_ascii=False)) // 4)


def _tails(bundle: dict[str, Any]) -> int:
    """The envelope tails' cost, mirrored the same way.

    The overrun note is filtered out: the compiler prices the tails and THEN, if the total
    overran, appends the note that says so — pricing a message whose existence depends on
    the price would be circular.  Filtering it here pins that ordering, and pins the
    note's prefix as part of the contract.
    """
    return max(1, len(json.dumps({
        "excluded": bundle["excluded"],
        "omitted_due_to_budget": bundle["omitted_due_to_budget"],
        "degraded": [row for row in bundle["degraded"]
                     if not row.startswith("token_estimate ")],
        "candidates": bundle["target"]["candidates"],
    }, ensure_ascii=False)) // 4)


def _budget_is_honest(bundle: dict[str, Any], label: str = "") -> None:
    """Either the bundle fits its cap, or the overrun is NAMED — never a bare number."""
    if bundle["token_estimate"] <= bundle["token_budget"]:
        return
    assert [row for row in bundle["degraded"] if row.startswith("token_estimate ")], (
        f"{label}: estimate {bundle['token_estimate']} exceeds budget "
        f"{bundle['token_budget']} with nothing in `degraded` saying so"
    )


# ------------------------------------------------------------- fixture builders
#
# Records are written as real files rather than mocked, because the compiler's whole job
# is to read this format — a fixture that skipped the frontmatter contract would test a
# different program.  `program` values are REAL keys from config/mastermind_programs.yml
# (validate hard-fails an unknown program, which would make every fixture malformed).

PROGRAM = "prophet-us"
OTHER_PROGRAM = "agentic-media"

# A REAL row in config/compiled_kill_registry.yml.  An unresolvable key degrades loudly
# and emits NOTHING, which would leave the higher-law fixture carrying only its program
# row — a fixture that silently stopped exercising the class it exists to pin.
DNR_KEY = "KILL-FUSED-SHIELD"


def _write(path: Path, front: dict[str, Any], body: str = "Fixture body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(front, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{dumped}---\n\n{body}", encoding="utf-8")


def _workstream(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "title": f"{key} in one line",
        "objective": "Ship the thing and prove it shipped.",
        "status": "active",
        "program": PROGRAM,
        "repos": ["macro"],
        "owner": "coo-fable",
        "class": "research",
        "blast_radius": "reversible",
        "ambiguity": "open",
        "waves": [{"id": "W0", "title": "First wave", "status": "todo"}],
        "next_action": "Run the next command.",
    }
    front.update(extra)
    _write(root / "workstreams" / f"WS-{key}.md", front)


def _decision(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "question": f"Should we {key.lower()}?",
        "answer": "Yes, with the stated bound.",
        "rationale": "Because the measured alternative cost more and proved less.",
        "alternatives": [{"option": "Do nothing", "why_not": "The defect recurs nightly."}],
        "evidence": ["tests/test_agentos_compile.py — this fixture"],
        "affects": ["WS:TARGET"],
        "confidence": "high",
        "reversibility": "easy",
        "decided_by": "fixture",
        "decided_at": "2026-08-01",
    }
    front.update(extra)
    _write(root / "decisions" / f"DEC-{key}.md", front)


def _discovery(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "claim": f"{key} behaves as described under the named repro.",
        "falsifier": "pytest tests/test_agentos_compile.py — a pass disproves it.",
        "so_what": "A future session stops re-deriving this.",
        "kind": "architecture",
        "verified_at": "2026-08-10",
        "verified_by": "pytest tests/test_agentos_compile.py",
        "scope": ["WS:TARGET"],
        "confidence": "verified",
    }
    front.update(extra)
    _write(root / "discoveries" / f"DSC-{key}.md", front)


def _handoff(root: Path, stem: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "workstream": "WS:TARGET",
        "session": "claude/fixture",
        "model": "opus",
        "mission": "Land the first wave.",
        "state_before": "Nothing existed.",
        "changed": [{"path": "scripts/agentos.py", "what": "added the compiler"}],
        "verified": [{"claim": "suite green",
                      "command": "pytest tests/test_agentos_compile.py"}],
        "unverified": [],
        "unresolved": ["Whether the budget floor is right."],
        "next_actions": ["Run the suite."],
        "do_not_redo": ["The resolution design — settled in DEC:AGENTOS-NO-TASK-STORE."],
        "danger_areas": ["The budget packer."],
        "ended_because": "complete",
    }
    front.update(extra)
    _write(root / "handoffs" / f"{stem}.md", front, "Handoff body, self-contained.\n")


@pytest.fixture()
def simple(tmp_path: Path) -> Path:
    """One workstream, one decision, one discovery — the happy shape."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"])
    _decision(root, "KEEP")
    _discovery(root, "KEEP")
    return root


@pytest.fixture()
def overfull(tmp_path: Path) -> Path:
    """Far more reachable records than any small budget can carry."""
    root = tmp_path / "agentos"
    padding = "This rationale is deliberately long so the budget binds. " * 12
    keys = [f"BULK{index:02d}" for index in range(12)]
    _workstream(
        root, "TARGET",
        decisions=[f"DEC:{key}" for key in keys],
        discoveries=[f"DSC:{key}" for key in keys],
    )
    for key in keys:
        _decision(root, key, rationale=padding)
        _discovery(root, key, claim=padding)
    return root


@pytest.fixture()
def constrained(tmp_path: Path) -> Path:
    """An EXPENSIVE workstream block sitting above cheap pointers, plus higher law.

    `overfull` cannot exercise this: its workstream block costs ~72 tokens, so higher law
    fits under any budget above the floor and the rule would be untested.  The inversion
    needs the shape of a REAL record — one that carries landmines — so that greedy
    packing reaches HIGHER LAW with only change left, and ARTIFACTS is cheap enough to
    spend it.
    """
    root = tmp_path / "agentos"
    landmine = "A landmine stated at the length a real landmine is stated at. " * 5
    padding = "This rationale is deliberately long so the budget binds. " * 12
    keys = [f"BULK{index:02d}" for index in range(6)]
    _workstream(
        root, "TARGET",
        landmines=[f"{landmine}({index})" for index in range(4)],
        do_not_redo=[f"Settled — the resolution design is closed; see DNR:{DNR_KEY}."],
        artifacts=[f"research/POINTER_{index}.md" for index in range(3)],
        decisions=[f"DEC:{key}" for key in keys],
        discoveries=[f"DSC:{key}" for key in keys],
    )
    for key in keys:
        _decision(root, key, rationale=padding)
        _discovery(root, key, claim=padding)
    return root


# --------------------------------------------------------------- the real store


def test_every_seeded_workstream_compiles_and_every_line_is_cited() -> None:
    """The acceptance gate, on real data: bounded, and nothing uncited.

    `why_included` is not decoration.  A bundle is read by a session that will not open
    the sources, so an item that cannot say why it is present is an assertion with no
    provenance — exactly what §8's "everything is cited" exists to forbid.
    """
    assert SEED_KEYS, "the seeded store has no workstreams to compile"
    # Parse and validate the committed store once, then exercise the same pure
    # compiler over every target.  Spawning the CLI once per workstream reparsed
    # all 863 records 49 times; exact-head #6505 measured that single test at
    # more than 50 minutes on pc-ci-3.  Representative CLI-routing tests below
    # still cross the process/argument/JSON boundary.  This acceptance gate
    # retains every workstream and every assertion; it only removes quadratic
    # fixture transport.
    module = _load_cli()
    store = module.load_store(STORE, module._load_programs())
    active_builds_degraded = module.Degraded()
    builds = module.load_active_builds(active_builds_degraded)
    now = module._parse_moment(FROZEN)
    assert now is not None
    # This gate asserts graph coverage, citations, authority and budget behavior;
    # it does not assert Git-history timestamps.  Resolving those timestamps here
    # spawned thousands of `git log` processes over the same records and made the
    # all-workstream proof the pack's hidden hour-long tail.  The status contract
    # test separately proves that real tracked records resolve Git-derived dates.
    module.git_dates = lambda _path: (None, None)
    repo_sha = module._repo_sha()
    module._repo_sha = lambda: repo_sha
    for key in SEED_KEYS:
        degraded = module.Degraded()
        degraded.items.extend(active_builds_degraded.items)
        bundle = module.compile_bundle(
            store,
            workstream=key,
            now=now,
            builds=builds,
            degraded=degraded,
        )
        assert bundle["schema"] == "context_bundle.v1"
        assert bundle["target"]["workstream"] == f"WS:{key}"
        assert bundle["target"]["resolution"] == "explicit"
        _budget_is_honest(bundle, key)
        items = _items(bundle)
        assert items, f"{key} compiled to an empty bundle"
        for item in items:
            assert item["path"], f"{key}: uncited item {item['kind']}"
            assert item["why_included"], f"{key}: unexplained item {item['path']}"
            assert item["authority_class"], f"{key}: unranked item {item['path']}"
        assert _section(bundle, "workstream")["items"], f"{key} lost its own record"


def test_the_section_order_is_the_authority_order() -> None:
    """Presentation order IS the contract (WP-E) — law above evidence, always."""
    bundle = _bundle(_compile("--workstream", SEED_KEYS[0]))
    assert [section["id"] for section in bundle["sections"]] == [
        "higher_law", "workstream", "decisions", "discoveries", "handoff", "artifacts",
    ]


def test_workstream_mode_never_imports_the_retrieval_engine() -> None:
    """The index import is LAZY, and that is load-bearing, not an optimisation.

    `--workstream` must work in a checkout where `engine/` was never checked out — which
    is the normal state of a sparse agent worktree.  A module-level import would make the
    whole subcommand unusable there.
    """
    source = CLI.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            assert "engine" not in line, f"engine imported at module scope: {line!r}"
    probe = (
        "import sys; sys.path.insert(0, %r); import importlib;"
        "m = importlib.import_module('scripts.agentos');"
        "print('LOADED:' + ','.join(k for k in sys.modules if 'context_index' in k))"
        % str(REPO)
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            cwd=REPO)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LOADED:", result.stdout


# ------------------------------------------------------------------- the budget


def test_the_budget_binds_and_says_what_it_dropped(overfull: Path) -> None:
    """A cap that truncates silently is indistinguishable from a smaller store."""
    bundle = _bundle(_compile("--root", str(overfull), "--workstream", "TARGET",
                              "--budget", "700"))
    assert bundle["token_budget"] == 700
    omitted = bundle["omitted_due_to_budget"]
    assert omitted, "24 padded records fit in 700 tokens — the packer did not run"
    for row in omitted:
        assert row["path"] and row["tokens"] > 0
        assert isinstance(row["rank"], int)
    assert _section(bundle, "workstream")["items"], (
        "the target's own record was dropped — it is the one item that never may be"
    )
    # PACKING binds, and the SELECTED items stay inside the cap.  The reported estimate
    # may still exceed it, because the accounting tails — the omission list this very test
    # demands, plus `excluded` and `degraded` — are payload the caller pays for and can
    # never be dropped.  Reporting them is the honest half; whenever they push the total
    # over, the overrun is named rather than left as a bare number.
    packed = sum(_tokens(item) for item in _items(bundle))
    assert packed <= 700, "the packed items overran the cap"
    assert bundle["token_estimate"] == packed + _tails(bundle), (
        "the reported estimate is not the payload it claims to be"
    )
    _budget_is_honest(bundle)


def test_an_overrun_is_never_a_bare_number(constrained: Path) -> None:
    """The one thing a caller cannot act on is an unexplained number.

    `token_estimate > token_budget` is legal — the always-included constraint set and the
    accounting tails are not tradable — but a bundle that only PRINTS the overrun tells a
    reader the compiler is broken.  It must also say what overran, in both renderers.
    """
    bundle = _bundle(_compile("--root", str(constrained), "--workstream", "TARGET",
                              "--budget", "500"))
    assert bundle["token_estimate"] > bundle["token_budget"], (
        "the fixture stopped overrunning — this test now proves nothing"
    )
    named = [row for row in bundle["degraded"] if row.startswith("token_estimate ")]
    assert len(named) == 1, f"overrun not named exactly once: {bundle['degraded']}"
    for part in ("always-included constraint context", "accounting tails", "raise --budget"):
        assert part in named[0], f"the overrun note does not name {part!r}: {named[0]}"

    text = _compile("--root", str(constrained), "--workstream", "TARGET",
                    "--budget", "500", "--text")
    assert text.returncode == 0, text.stdout + text.stderr
    header = next(line for line in text.stdout.splitlines() if line.startswith("budget: "))
    assert "OVER BUDGET, see DEGRADED" in header, (
        f"the text header showed a bare overrun: {header!r}"
    )
    # Whitespace-normalised: the renderer wraps degraded messages at 70 columns, so the
    # phrase legitimately spans lines.
    assert "always-included constraint context" in " ".join(text.stdout.split())


def test_a_binding_cap_never_costs_a_constraint(constrained: Path) -> None:
    """HIGHER LAW is not tradable against ARTIFACTS.

    Greedy-with-continuation alone emptied the constraint class while the pointer class
    still rendered: the cheap tail fits in the change the expensive head leaves behind.
    A bundle exists to tell a cold session which constraints it may not violate, so
    losing them to a cap while keeping file paths inverts the whole point of the
    document.  Higher law therefore joins the workstream block in the always-include set,
    and the documented degenerate-budget exception extends to it — `token_estimate` may
    exceed `token_budget` only when those two packs ALONE exceed it.
    """
    def compile_at(budget: str) -> dict[str, Any]:
        return _bundle(_compile("--root", str(constrained), "--workstream", "TARGET",
                                "--budget", budget))

    uncapped = compile_at("100000")
    law = _section(uncapped, "higher_law")["items"]
    assert {item["kind"] for item in law} == {"dnr", "program"}, (
        f"the fixture stopped exercising higher law: {law}"
    )
    assert not uncapped["omitted_due_to_budget"], "100k tokens should omit nothing"

    # Tiny cap: the always-include set alone overruns it — the documented exception.
    tight = compile_at("500")
    assert _section(tight, "higher_law")["items"] == law, (
        "the cap dropped a constraint-class item"
    )
    assert tight["omitted_due_to_budget"], "12 padded records fit in 500 tokens"
    assert not [row for row in tight["omitted_due_to_budget"]
                if row["kind"] in {"dnr", "p0", "program"}], "higher law was omitted"
    assert not _section(tight, "artifacts")["items"], (
        "a pointer outlived a constraint — the exact inversion this rule forbids"
    )
    always = (_section(tight, "workstream")["items"]
              + _section(tight, "higher_law")["items"])
    assert tight["token_estimate"] == sum(_tokens(item) for item in always) + _tails(tight), (
        "the exception is bounded to the always-include set plus the accounting tails; "
        "no OPTIONAL item may overrun"
    )
    _budget_is_honest(tight)

    # Roomier cap: with space for the always-include set, packing binds as before and the
    # selected items stay inside it.  The reported total may still carry the tails over —
    # `_budget_is_honest` is what forbids that being silent.  1800 rather than 900 because
    # the always-include set alone is ~1250 tokens once whole items are priced, so 900 is
    # a SECOND degenerate cap and would have proved the degenerate case twice.
    roomy = compile_at("1800")
    assert _section(roomy, "higher_law")["items"] == law
    assert sum(_tokens(item) for item in _items(roomy)) <= 1800, (
        "the packed items overran a non-degenerate cap"
    )
    assert roomy["omitted_due_to_budget"], "the packer did not run"
    _budget_is_honest(roomy)


def test_an_always_included_constraint_is_capped_per_entry(tmp_path: Path) -> None:
    """The always-include set is exempt from the BUDGET, never from `_clip`.

    Landmines are one-liners by convention and nothing enforced it, so one 2,000-char
    entry rendered whole inside the pack that the cap may not touch — the only unbounded
    thing in a document that advertises itself as bounded.  Per-entry capping keeps the
    head (which is the part that warns) and says it was cut.
    """
    root = tmp_path / "agentos"
    huge = "A landmine written at essay length, which is exactly the shape nobody bounds. " * 30
    _workstream(root, "TARGET", landmines=[huge])
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))

    constraints = [item for item in _items(bundle) if item["kind"] == "constraint"]
    assert len(constraints) == 1, "the fixture stopped emitting a constraint"
    excerpt = constraints[0]["excerpt"]
    assert excerpt.startswith("[LANDMINE] A landmine written at essay length")
    assert excerpt.endswith("…"), "a silent cut reads as the whole entry"
    assert len(excerpt) < 450, f"the constraint excerpt was not capped: {len(excerpt)}"


def test_the_budget_floor_refuses_a_degenerate_cap(overfull: Path) -> None:
    """`--budget 0` must not render an empty bundle that looks like an empty store."""
    bundle = _bundle(_compile("--root", str(overfull), "--workstream", "TARGET",
                              "--budget", "0"))
    assert bundle["token_budget"] == 500
    assert _section(bundle, "workstream")["items"]


# --------------------------------------------------------------- the exclusions


def test_a_superseded_decision_is_excluded_and_named(tmp_path: Path) -> None:
    """Supersession is why BOTH records survive; a bundle listing them as peers undoes it."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:OLD", "DEC:NEW"])
    _decision(root, "OLD", superseded_by="DEC:NEW", decided_at="2026-07-01")
    _decision(root, "NEW", supersedes=["DEC:OLD"], decided_at="2026-08-05")
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))

    keys = [item["key"] for item in _items(bundle)]
    assert "DEC:NEW" in keys
    assert "DEC:OLD" not in keys, "a superseded decision was rendered as current"
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:OLD"]
    assert dropped, "the superseded record vanished instead of being named"
    assert "superseded_by DEC:NEW" in dropped[0]["reason"]

    survivor = next(item for item in _items(bundle) if item["key"] == "DEC:NEW")
    assert "supersedes DEC:OLD" in survivor["excerpt"], (
        "provenance is allowed and useful; co-equality is not"
    )


def test_an_unresolvable_supersession_retains_the_record_and_says_so(
    tmp_path: Path
) -> None:
    """`superseded_by` is the only field that DELETES a record from every bundle.

    It therefore may not fire on a citation nobody can open: retiring a decision in favour
    of a replacement that does not exist loses the reasoning outright, and loses it
    silently — the record is simply absent from the one document a cold session reads.
    Eviction now needs a citation that is well-shaped AND resolves; anything else keeps the
    record and prints the problem.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:KEEP"])
    _decision(root, "KEEP", superseded_by="DEC:GONE")

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    assert "DEC:KEEP" in [item["key"] for item in _items(bundle)], (
        "a live decision was deleted by a superseded_by nobody can resolve"
    )
    assert not [row for row in bundle["excluded"] if row["key"] == "DEC:KEEP"]
    assert [row for row in bundle["degraded"]
            if "DEC:KEEP carries unresolvable superseded_by 'DEC:GONE' — retained" in row], (
        f"the broken field left no trace: {bundle['degraded']}"
    )


@pytest.mark.parametrize("junk", ["no", False, 0, ""])
def test_truthy_junk_never_evicts_a_decision(tmp_path: Path, junk: Any) -> None:
    """The field used to be read by TRUTHINESS, so it meant two opposite things.

    `superseded_by: "no"` — a plausible thing to type — evicted a current decision from
    every bundle forever while `validate` exited 0, and `false`/`0`/`""` did not evict at
    all.  All four are now refused as records, and none of them may masquerade as a real
    supersession in the bundle.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:KEEP"])
    _decision(root, "KEEP", superseded_by=junk)

    assert _run("validate", "--root", str(root)).returncode == 1, (
        f"superseded_by: {junk!r} validated clean"
    )
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    superseded = [row for row in bundle["excluded"]
                  if row["key"] == "DEC:KEEP" and "superseded_by" in row["reason"]]
    assert not superseded, f"{junk!r} was read as a real supersession: {superseded}"


def test_stale_discoveries_are_excluded_with_the_specific_reason(tmp_path: Path) -> None:
    """Both staleness rules, each with its own negative fixture and its own wording."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=["DSC:FRESH", "DSC:EXPIRED"])
    _discovery(root, "FRESH", verified_at="2026-08-10")
    _discovery(root, "EXPIRED", expires="2026-05-01", verified_at="2026-04-01")
    # Reachable by SCOPE only, so its inbound citation count is genuinely zero.
    _discovery(root, "ANCIENT", verified_at="2026-01-01", scope=["WS:TARGET"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    keys = [item["key"] for item in _items(bundle)]
    assert "DSC:FRESH" in keys
    assert "DSC:EXPIRED" not in keys
    assert "DSC:ANCIENT" not in keys

    reasons = {row["key"]: row["reason"] for row in bundle["excluded"]}
    assert reasons["DSC:EXPIRED"] == "expired 2026-05-01"
    assert reasons["DSC:ANCIENT"].startswith("uncited and ")
    assert reasons["DSC:ANCIENT"].endswith("d old")


def test_an_expired_discovery_the_target_cites_is_named_not_just_dropped(
    tmp_path: Path
) -> None:
    """RULING: an explicit `expires` evicts even when cited — and the citer is TOLD.

    The schema's "if never cited" clause modifies the 90-day default, not an author's
    explicit date: a finding whose author wrote "untrue after May" does not become true
    again because somebody cited it.  But to the workstream that cites it, a silent
    exclusion is indistinguishable from a finding that never existed, so citation buys
    visibility instead of survival.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=["DSC:CITEDEXPIRED"])
    _discovery(root, "CITEDEXPIRED", expires="2026-05-01", verified_at="2026-04-01")

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    assert "DSC:CITEDEXPIRED" not in [item["key"] for item in _items(bundle)]
    reasons = {row["key"]: row["reason"] for row in bundle["excluded"]}
    assert reasons["DSC:CITEDEXPIRED"] == "expired 2026-05-01"
    assert [row for row in bundle["degraded"]
            if "DSC:CITEDEXPIRED cited by this workstream but expired 2026-05-01" in row], (
        f"the citer was not told its own citation expired: {bundle['degraded']}"
    )


def test_a_cited_old_discovery_survives_the_staleness_rule(tmp_path: Path) -> None:
    """Citation is the freshness signal — an old finding someone still reads is alive.

    This pins the half of the rule that is easy to lose: age alone must not evict.  A
    discovery whose only reader is a HANDOFF counts as cited, which is exactly the case
    `check_references` was fixed for and the one a second implementation would miss.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=[])
    _discovery(root, "OLDBUTCITED", verified_at="2026-01-01", scope=["WS:TARGET"])
    _handoff(root, "TARGET-2026-08-11", discoveries=["DSC:OLDBUTCITED"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    assert "DSC:OLDBUTCITED" in [item["key"] for item in _items(bundle)]
    assert not [row for row in bundle["excluded"] if row["key"] == "DSC:OLDBUTCITED"]


def test_only_the_latest_handoff_survives(tmp_path: Path) -> None:
    """Older handoffs are excluded, never merged into a composite nobody wrote."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET")
    _handoff(root, "TARGET-2026-08-01", mission="The older session.")
    _handoff(root, "TARGET-2026-08-11", mission="The newer session.")

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    handoffs = _section(bundle, "handoff")["items"]
    assert len(handoffs) == 1
    assert "The newer session." in handoffs[0]["excerpt"]
    dropped = [row for row in bundle["excluded"] if row["key"] == "TARGET-2026-08-01"]
    assert dropped and "older_handoff (latest: TARGET-2026-08-11)" in dropped[0]["reason"]


def test_another_programs_records_cannot_enter_the_bundle(tmp_path: Path) -> None:
    """The boundary is STRUCTURAL, not a relevance threshold.

    The decoy records share the target's vocabulary on purpose: if the walk were replaced
    by a similarity score, this is precisely the fixture that would start leaking.
    """
    root = tmp_path / "agentos"
    tempting = "Ship the thing and prove it shipped — first wave, next command."
    _workstream(root, "TARGET", decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"],
                owns_paths=["engine/prophet/**"])
    _decision(root, "KEEP")
    _discovery(root, "KEEP")
    _workstream(root, "DECOY", program=OTHER_PROGRAM, objective=tempting,
                decisions=["DEC:DECOYONLY"], discoveries=["DSC:DECOYONLY"])
    _decision(root, "DECOYONLY", affects=["WS:DECOY"], rationale=tempting)
    _discovery(root, "DECOYONLY", scope=["WS:DECOY"], claim=tempting)
    # The third declared form of `affects`/`scope`: a path glob.  Overlapping the target's
    # `owns_paths` is a REASON to attach; a glob in a neighbouring tree is not, and a
    # matcher that could not tell them apart would re-open the boundary this test guards.
    _decision(root, "GLOBHIT", affects=["engine/prophet/entry.py"])
    _decision(root, "GLOBMISS", affects=["engine/rates/**"])
    _discovery(root, "GLOBHIT", scope=["engine/prophet/**"])
    _discovery(root, "GLOBMISS", scope=["site/assets/**"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    serialized = json.dumps(bundle)
    assert "DECOY" not in serialized, "an unrelated program's records reached the bundle"
    assert "KEEP" in serialized, "the fixture proves nothing if the target is empty too"
    assert "GLOBMISS" not in serialized, "a glob outside owns_paths reached the bundle"

    hits = [item for item in _items(bundle) if item["key"] in {"DEC:GLOBHIT", "DSC:GLOBHIT"}]
    assert len(hits) == 2, (
        f"a path glob the target owns was dropped: {[i['key'] for i in _items(bundle)]}"
    )
    for item in hits:
        assert "paths this workstream owns" in item["why_included"]
        assert "engine/prophet" in item["why_included"], (
            f"the overlap is unexplained: {item['why_included']}"
        )


def test_a_repo_wide_scope_does_not_attach_through_the_path_door(tmp_path: Path) -> None:
    """`scope: [macro]` must stay repo-wide-and-therefore-inert, globs or not.

    `_owns_overlap` is prefix-coarse by design, so a bare repo name overlaps any owned
    path that starts with it — `terminal` matches `terminal/components/**` — and the
    repo-name strip is the only thing standing between that and attaching every finding in
    a repo to every workstream in it.  Before path globs were matched the strip was
    decorative; it is now load-bearing, so deleting it must break something.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=[], owns_paths=["macro/pipeline/**"])
    _discovery(root, "REPOWIDE", scope=["macro"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    assert "DSC:REPOWIDE" not in [item["key"] for item in _items(bundle)], (
        "a repo-wide scope attached through glob matching"
    )


# ------------------------------------------------------------- artifact pointers


def test_pointer_authority_comes_from_the_index_config(tmp_path: Path) -> None:
    """A pointer must not claim a rank the corpus registration would not give it.

    Three hardcoded suffix rules disagreed with `config/context_index.yml`, the file that
    owns the question, and the disagreement was visible INSIDE one bundle:
    `research/DO_NOT_REBUILD.md` rendered as an A1 `dnr` item and as an A3 artifact at the
    same time, and `CLAUDE.md` — the repo constitution, A0 — was demoted to A3.  Authority
    now resolves against the config, first matching source winning in list order.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", artifacts=[
        "research/DO_NOT_REBUILD.md",     # A1 — listed before the A3 research catch-all
        "CLAUDE.md",                      # A0 — the constitution
        "docs/ACTIVE_BUILD_MAP.md",       # A4 — listed before the A3 docs catch-all
        "notes/nothing-indexes-this.txt",  # unindexed — the neutral default
    ])
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    ranks = {item["path"]: item["authority_class"]
             for item in _section(bundle, "artifacts")["items"]}
    assert ranks == {
        "research/DO_NOT_REBUILD.md": "A1",
        "CLAUDE.md": "A0",
        "docs/ACTIVE_BUILD_MAP.md": "A4",
        "notes/nothing-indexes-this.txt": "A3",
    }


def test_an_artifact_entry_that_is_not_a_path_is_named(tmp_path: Path) -> None:
    """A skipped pointer reads exactly like a record that never listed it."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", artifacts=["DEC:WANDERED-IN", "https://example.invalid/x",
                                           "research/REAL.md"])
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))

    paths = [item["path"] for item in _section(bundle, "artifacts")["items"]]
    assert paths == ["research/REAL.md"]
    for entry in ("DEC:WANDERED-IN", "https://example.invalid/x"):
        assert [row for row in bundle["degraded"]
                if row == f"artifact entry not a repo path — skipped: {entry}"], (
            f"{entry} was dropped in silence: {bundle['degraded']}"
        )


# ---------------------------------------------------------------- I4, both ways


def test_missing_joins_degrade_and_still_compile(simple: Path, tmp_path: Path) -> None:
    """Fail-OPEN: no active_builds.json, no Mastermind checkout — the bundle still exists.

    This is also the CI shape: the sibling repo is never present on a runner, so a
    compiler that needed it would be red on every PR in the fleet.
    """
    _workstream(simple, "TARGET", p0="US_PROPHET_ENTRY_TIMING",
                decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"],
                waves=[{"id": "W0", "title": "First wave", "status": "done", "pr": 5370}])
    result = _compile("--root", str(simple), "--workstream", "TARGET",
                      "--active-builds", str(tmp_path / "no-such-file.json"),
                      env={"MACRO_MASTERMIND_REPO": str(tmp_path / "gone")})
    bundle = _bundle(result)
    assert bundle["degraded"], "two unreadable inputs reported as clean"
    assert any("PR state unknown" in item for item in bundle["degraded"])
    assert any("p0 ids unvalidated" in item for item in bundle["degraded"])
    assert _items(bundle), "a missing join blanked the bundle"
    # The PR join degrades to a stated "unknown", never to a confident wrong state.
    assert "PR #5370 unknown" in _section(bundle, "workstream")["items"][0]["excerpt"]


def test_a_malformed_sibling_is_excluded_while_the_bundle_still_compiles(
    simple: Path
) -> None:
    """Fail-OPEN on a sibling record: named in both `excluded` and `degraded`, never rendered."""
    broken = simple / "decisions" / "DEC-KEEP.md"
    broken.write_text(
        broken.read_text(encoding="utf-8").replace("rationale:", "rationale_typo:", 1),
        encoding="utf-8",
    )
    bundle = _bundle(_compile("--root", str(simple), "--workstream", "TARGET"))
    assert "DEC:KEEP" not in [item["key"] for item in _items(bundle)]
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:KEEP"]
    assert dropped and "malformed" in dropped[0]["reason"]
    assert any("malformed" in item and "DEC:KEEP" in item for item in bundle["degraded"])


def test_a_dangling_citation_on_the_target_degrades_rather_than_refusing(
    simple: Path
) -> None:
    """A CROSS-RECORD problem is a join failure, and joins fail OPEN (I4).

    `check_references` attributes `dangling-ref` to the CITING record, so a workstream
    whose own frontmatter is perfect was refused outright because a sibling it cites was
    renamed in an in-flight PR — the single most common transient state in this fleet.
    The bundle compiles around the hole and NAMES it, twice: once in `excluded` for the
    citation that resolved to nothing, once in `degraded` for the reader.

    This is the mutation guard for the fatal-rule filter: widening `fatal` back to every
    hard problem on the target's path turns this exit 0 into exit 1.
    """
    _workstream(simple, "TARGET", decisions=["DEC:KEEP", "DEC:GONE"],
                discoveries=["DSC:KEEP"])
    result = _compile("--root", str(simple), "--workstream", "TARGET")
    bundle = _bundle(result)

    assert "DEC:KEEP" in [item["key"] for item in _items(bundle)], (
        "the valid half of the record was lost with the invalid half"
    )
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:GONE"]
    assert dropped and "dangling citation" in dropped[0]["reason"]
    assert [row for row in bundle["degraded"]
            if "cross-record problem on WS:TARGET" in row and "dangling-ref" in row], (
        f"the unresolved citation left no trace for the reader: {bundle['degraded']}"
    )


def test_an_unparseable_sibling_does_not_refuse_the_target(simple: Path) -> None:
    """A sibling that is not even YAML is excluded; the target still compiles.

    Distinct from the malformed-sibling case: an unparseable record never enters the store
    at all, so it becomes a DANGLING citation on the target — a hard problem attributed to
    the target's own path, which is exactly the shape that used to fail closed.
    """
    broken = simple / "decisions" / "DEC-KEEP.md"
    broken.write_text("no frontmatter fence at all\n", encoding="utf-8")
    bundle = _bundle(_compile("--root", str(simple), "--workstream", "TARGET"))

    assert "DEC:KEEP" not in [item["key"] for item in _items(bundle)]
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:KEEP"]
    assert dropped, "the unparseable sibling vanished instead of being named"
    assert _section(bundle, "workstream")["items"], "the target lost its own record"


def test_a_dependency_cycle_compiles_from_both_endpoints(tmp_path: Path) -> None:
    """WS-ALPHA <-> WS-BETA is symmetric; the compiler's answer must be too.

    The cycle detector reports one node — whichever the DFS entered from — so one endpoint
    used to exit 1 and the other exited 0 on the SAME defect, which reads as a flaky
    compiler rather than a bad pair of records.  Both now compile, and both carry the
    cycle as a degraded note: the validator attributes it to every member.
    """
    root = tmp_path / "agentos"
    _workstream(root, "ALPHA", depends_on=["WS:BETA"])
    _workstream(root, "BETA", depends_on=["WS:ALPHA"])

    for key, other in (("ALPHA", "BETA"), ("BETA", "ALPHA")):
        bundle = _bundle(_compile("--root", str(root), "--workstream", key))
        assert bundle["target"]["workstream"] == f"WS:{key}"
        assert [row for row in bundle["degraded"]
                if "workstream-cycle" in row and f"WS:{key}" in row], (
            f"{key} compiled with no sign of the cycle: {bundle['degraded']}"
        )
        assert f"WS:{other}" in [item["key"] for item in _items(bundle)], (
            f"{key} lost its dependency stub — a cycle is not a reason to hide the edge"
        )


@pytest.mark.parametrize(("rule", "anchor", "replacement"), [
    ("bad-enum", "status: active", "status: humming"),
    ("required-field", "objective:", "objective_typo:"),
    ("bad-wave", "- id: W0", "- ident: W0"),
])
def test_a_malformed_target_fails_closed(
    simple: Path, rule: str, anchor: str, replacement: str
) -> None:
    """Fail-CLOSED on schema: compiling around a record that lies about the org is worse
    than refusing, because the refusal is visible and the bundle would not be.

    Record-LOCAL rules only, and that is the whole distinction the fatal filter draws: an
    enum the record itself got wrong, a field it never wrote, a wave it malformed.  A
    citation that does not resolve is somebody ELSE's record and degrades instead (see the
    dangling-citation test above) — parametrized here so the filter cannot be "fixed" by
    letting everything through.
    """
    target = simple / "workstreams" / "WS-TARGET.md"
    text = target.read_text(encoding="utf-8")
    assert anchor in text, f"mutation anchor missing: {anchor!r}"
    target.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

    result = _compile("--root", str(simple), "--workstream", "TARGET")
    assert result.returncode == 1, result.stdout
    assert rule in result.stdout
    assert "fail-closed" in result.stdout
    for line in result.stdout.splitlines():
        if "::error" in line or "::warning" in line:
            assert line.startswith("::"), f"annotation does not start the line: {line!r}"


def test_a_target_whose_key_is_corrupt_fails_closed_one_gate_earlier(simple: Path) -> None:
    """A corrupted `key` is still fail-CLOSED — it just fails at a different gate.

    The record stops answering to the name the caller used, so it is caught as an UNKNOWN
    workstream rather than a malformed one.  Both exit 1; the rules that broke the record
    are still printed, so the caller is not left guessing which of the two it is.
    """
    target = simple / "workstreams" / "WS-TARGET.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("key: TARGET", "key: target lower", 1),
        encoding="utf-8",
    )
    result = _compile("--root", str(simple), "--workstream", "TARGET")
    assert result.returncode == 1
    assert "unknown workstream WS:TARGET" in result.stdout
    assert "bad-key" in result.stdout


def test_an_unknown_target_fails_closed(simple: Path) -> None:
    result = _compile("--root", str(simple), "--workstream", "NO-SUCH-THING")
    assert result.returncode == 1
    assert "unknown workstream WS:NO-SUCH-THING" in result.stdout


def test_an_absent_store_answers_the_question_it_was_asked(tmp_path: Path) -> None:
    """The two modes ask different questions, so an absent store gets two answers.

    `--workstream X` ASSERTS that X exists; against a store that does not exist that is
    the same caller error as naming a workstream that does not exist, and gets the same
    exit 1.  Free text ASKS a question, and "this repo has no record store" is an honest
    answer to it — a not-yet-adopted repo is a normal state, which is why `validate` warns
    and exits 0 there too.  A crash or an empty-looking bundle would be neither.
    """
    absent = tmp_path / "no-such-store"

    named = _compile("--root", str(absent), "--workstream", "TARGET")
    assert named.returncode == 1
    assert "no agentos/ store" in named.stdout
    assert "WS:TARGET" in named.stdout

    asked = _compile("--root", str(absent), "what should I pick up next")
    bundle = _bundle(asked)
    assert bundle["target"]["resolution"] == "unresolved"
    assert bundle["target"]["workstream"] is None
    assert bundle["sections"] == [], "an unresolved bundle must carry no content"
    assert [row for row in bundle["degraded"] if "no agentos/ store" in row], (
        f"the absent store was not reported: {bundle['degraded']}"
    )
    assert "no workstreams" in bundle["no_answer_reason"]


def test_the_key_prefix_is_optional(simple: Path) -> None:
    """`KEY`, `WS-KEY` and `WS:KEY` name the same record, so all three must resolve."""
    for spelling in ("TARGET", "WS-TARGET", "WS:TARGET"):
        bundle = _bundle(_compile("--root", str(simple), "--workstream", spelling))
        assert bundle["target"]["workstream"] == "WS:TARGET", spelling


# -------------------------------------------------------------- free-text tasks


def test_a_task_naming_a_key_resolves_without_the_index(simple: Path) -> None:
    """The cheapest path: a cited key is an exact answer, so no retrieval runs at all."""
    bundle = _bundle(_compile(
        "--root", str(simple), "finish the WS-TARGET first wave before the bake",
        env={"MACRO_CONTEXT_INDEX_DIR": "/nonexistent-index-dir"},
    ))
    assert bundle["target"]["resolution"] == "cited-key"
    assert bundle["target"]["workstream"] == "WS:TARGET"
    assert bundle["target"]["task"].startswith("finish the WS-TARGET")
    assert _items(bundle)


def test_free_text_resolves_through_the_existing_index(simple: Path) -> None:
    """Search hits VOTE; they never become content.

    The injected packet contains a decision path and an owned source path — neither is an
    Agent OS workstream record — and the vote still lands on the workstream that cites
    and owns them.  That is the join key doing the work retrieval could not.
    """
    agentos = _load_cli()
    store = agentos.load_store(simple, agentos._load_programs())
    seen: list[str] = []

    def fake_search(query: str) -> dict[str, Any]:
        seen.append(query)
        return {
            "schema": "context_packet.v1",
            "index_stale": False,
            "results": [
                {"path": "docs/UNRELATED.md"},
                {"path": str((simple / "decisions" / "DEC-KEEP.md"))},
                {"path": "agentos/decisions/DEC-KEEP.md"},
            ],
        }

    bundle = agentos.compile_bundle(
        store, task="why did we keep it", now=agentos._parse_moment(FROZEN),
        search_fn=fake_search,
    )
    assert seen == ["why did we keep it"], "the seam was not used"
    assert bundle["target"]["resolution"] == "search"
    assert bundle["target"]["workstream"] == "WS:TARGET"
    assert "docs/UNRELATED.md" not in json.dumps(bundle), (
        "a search hit became bundle content instead of a vote"
    )


def test_two_close_candidates_refuse_to_guess(tmp_path: Path) -> None:
    """An ambiguous resolution is a FEATURE.

    Picking one of two plausible workstreams hands the next session a confident bundle
    about the wrong work — strictly worse than no bundle, because it looks right.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET")
    _workstream(root, "RIVAL")
    agentos = _load_cli()
    store = agentos.load_store(root, agentos._load_programs())

    def fake_search(query: str) -> dict[str, Any]:
        return {"results": [
            {"path": "agentos/workstreams/WS-TARGET.md"},
            {"path": "agentos/workstreams/WS-RIVAL.md"},
        ]}

    bundle = agentos.compile_bundle(
        store, task="the ambiguous one", now=agentos._parse_moment(FROZEN),
        search_fn=fake_search,
    )
    assert bundle["target"]["resolution"] == "ambiguous"
    assert bundle["target"]["workstream"] is None
    assert bundle["sections"] == [], "an unresolved bundle must carry no content"
    candidates = {row["key"]: row["score"] for row in bundle["target"]["candidates"]}
    assert candidates == {"WS:TARGET": 20, "WS:RIVAL": 19}
    assert "pick one with --workstream" in bundle["no_answer_reason"]


def test_no_index_is_unresolved_not_a_crash(simple: Path, tmp_path: Path) -> None:
    """Fail-OPEN on retrieval: an unbuilt index degrades to 'name it yourself'."""
    empty = tmp_path / "empty-index"
    empty.mkdir()
    bundle = _bundle(_compile(
        "--root", str(simple), "reduce late entry in the prophet",
        env={"MACRO_CONTEXT_INDEX_DIR": str(empty)},
    ))
    assert bundle["target"]["resolution"] == "unresolved"
    assert bundle["sections"] == []
    assert any("context index unavailable" in item for item in bundle["degraded"])
    assert "pass --workstream" in bundle["no_answer_reason"]
    assert [row["key"] for row in bundle["target"]["candidates"]] == ["WS:TARGET"]


# --------------------------------------------------------- determinism, no writes


def _tree_digest(root: Path) -> list[tuple[str, str]]:
    return sorted(
        (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in root.rglob("*") if path.is_file()
    )


def test_the_same_inputs_produce_byte_identical_output(overfull: Path) -> None:
    """One clock, sorted iteration, integer weights — nothing may wobble run to run."""
    first = _compile("--root", str(overfull), "--workstream", "TARGET", "--budget", "900")
    second = _compile("--root", str(overfull), "--workstream", "TARGET", "--budget", "900")
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    text_one = _compile("--root", str(overfull), "--workstream", "TARGET",
                        "--budget", "900", "--text")
    text_two = _compile("--root", str(overfull), "--workstream", "TARGET",
                        "--budget", "900", "--text")
    assert text_one.stdout == text_two.stdout


def test_unordered_yaml_collections_render_in_a_fixed_order(tmp_path: Path) -> None:
    """The determinism guarantee has to survive the collection types YAML can hand back.

    Two of them wobble and neither is exotic.  A `!!set` is legal YAML and `safe_load`
    returns a real `set`, whose iteration order for strings is PER-PROCESS (hash
    randomisation) — so two runs of one command over one store rendered different bytes,
    invisibly, until somebody diffed them.  A mapping is insertion-ordered, so its wobble
    is the opposite kind: stable per run and stable in the WRONG order, which is why
    sorting it was untested — byte-identity across runs cannot see it.  Both are asserted
    against a fixture whose authored order is deliberately not the sorted one.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:UNORDERED"])
    _decision(root, "UNORDERED", answer={"zulu": 1, "alpha": 2, "mike": 3})
    # `yaml.safe_dump` refuses to write a set, so the tag is patched in afterwards.
    record = root / "decisions" / "DEC-UNORDERED.md"
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "rationale: Because the measured alternative cost more and proved less.",
            "rationale: !!set\n  ? zulu\n  ? alpha\n  ? mike\n",
            1,
        ),
        encoding="utf-8",
    )
    assert _run("validate", "--root", str(root)).returncode == 0, "the fixture is invalid"

    runs = [_compile("--root", str(root), "--workstream", "TARGET") for _ in range(2)]
    assert runs[0].stdout == runs[1].stdout, "a collection rendered in hash order"
    excerpt = next(item["excerpt"] for item in _items(_bundle(runs[0]))
                   if item["key"] == "DEC:UNORDERED")
    assert "answer: alpha=2; mike=3; zulu=1" in excerpt, (
        f"mapping keys were not sorted: {excerpt!r}"
    )
    assert "rationale: alpha | mike | zulu" in excerpt, (
        f"set members were not sorted: {excerpt!r}"
    )


def test_compiling_context_writes_nothing(simple: Path) -> None:
    """Read-only is a GUARANTEE, not an intention (I1): the store is a source, not a log."""
    before = _tree_digest(simple)
    assert _compile("--root", str(simple), "--workstream", "TARGET").returncode == 0
    assert _compile("--root", str(simple), "--workstream", "TARGET", "--text").returncode == 0
    assert _tree_digest(simple) == before, "compile-context modified the record store"


# ------------------------------------------------------------------ the text form


def test_text_output_states_its_authority_framings(tmp_path: Path) -> None:
    """The framings are the presentation contract: a reader must be able to tell law
    from evidence without opening the architecture doc."""
    root = tmp_path / "agentos"
    padding = "Long enough to force the packer to drop something. " * 14
    _workstream(root, "TARGET", decisions=["DEC:OLD", "DEC:NEW"] +
                [f"DEC:BULK{i}" for i in range(6)])
    _decision(root, "OLD", superseded_by="DEC:NEW")
    _decision(root, "NEW", supersedes=["DEC:OLD"])
    for index in range(6):
        _decision(root, f"BULK{index}", rationale=padding)

    result = _compile("--root", str(root), "--workstream", "TARGET",
                      "--budget", "600", "--text")
    assert result.returncode == 0, result.stdout + result.stderr
    text = result.stdout
    for framing in (
        "HIGHER LAW — outranks every Agent OS record below",
        "WORKSTREAM STATE (authoritative for state, not for permission)",
        "DECISIONS (institutional reasoning — do not override higher law)",
        "DISCOVERIES (evidence, not policy)",
        "LATEST HANDOFF (transfer state, not strategy)",
        "ARTIFACTS (pointers — read the primary source)",
    ):
        assert framing in text, f"missing authority framing: {framing}"

    assert "WS:TARGET · " in text and "WS-TARGET.md" in text, "no item citation rendered"
    assert "EXCLUDED (1)" in text and "superseded_by DEC:NEW" in text
    assert "OMITTED — BUDGET (" in text
    assert "tokens (rank " in text, "an omitted item was announced without its cost"
    assert "DEGRADED (" in text


def test_json_is_the_default_and_text_is_opt_in(simple: Path) -> None:
    """Mirrors context_index_query.py EXACTLY: `json if args.json or not args.text`.

    Including the collision.  Two CLIs in one repo that resolve `--json --text` opposite
    ways is a difference nobody can hold in their head and nobody documents, so the
    precedence is copied rather than re-decided: JSON wins in both.
    """
    default = _compile("--root", str(simple), "--workstream", "TARGET")
    explicit = _compile("--root", str(simple), "--workstream", "TARGET", "--json")
    assert json.loads(default.stdout)["schema"] == "context_bundle.v1"
    assert default.stdout == explicit.stdout, "--json is an alias, not a second format"
    assert not _compile("--root", str(simple), "--workstream", "TARGET",
                        "--text").stdout.lstrip().startswith("{")

    both = _compile("--root", str(simple), "--workstream", "TARGET", "--json", "--text")
    assert both.stdout == default.stdout, (
        "`--json --text` resolves to JSON in context_index_query.py; it must here too"
    )


# --------------------------------------------------------------------- I1 / usage


def test_neither_or_both_targets_is_a_usage_error(simple: Path) -> None:
    assert _compile("--root", str(simple)).returncode == 2
    assert _compile("--root", str(simple), "a task", "--workstream", "TARGET").returncode == 2


def test_compile_context_holds_no_scheduling_vocabulary() -> None:
    """I1, checkable by a reviewer: nothing here can start, stop, or claim work.

    SCOPED TO THE PHASE 3 BLOCK — everything after the `Phase 3: context compilation`
    banner — not to the whole file, and that scoping is deliberate rather than lazy.  The
    module's two sanctioned subprocess sites, `_git` and `git_dates`, are defined ABOVE the
    banner and are read-only local git; the compiler reaches them by call, so a new
    `subprocess.Popen` appearing below the banner is a new capability, which is exactly
    what this refuses.
    """
    source = CLI.read_text(encoding="utf-8")
    body = source.split("Phase 3: context compilation", 1)[1]
    assert "def _git(" not in body and "def git_dates(" not in body, (
        "the sanctioned subprocess helpers moved below the banner — this scan now has a "
        "hole in it; re-scope it or move them back"
    )
    for forbidden in ("def dispatch", "def assign", "def schedule", "def lease",
                      "def acquire", "subprocess.Popen", "os.system", "urllib",
                      "requests.", "socket."):
        assert forbidden not in body, f"{forbidden} has no business in a knowledge plane"


def test_the_store_this_suite_compiles_is_the_committed_one(tmp_path: Path) -> None:
    """The real store must stay valid, or every bundle above is compiled from a lie.

    `tmp_path`, never a fixed scratch directory: parallel sessions share one TMPDIR on
    this host, and a shared path turns two green suites into one flaky pair.
    """
    scratch = tmp_path / "agentos"
    shutil.copytree(STORE, scratch)
    assert _run("validate", "--root", str(scratch)).returncode == 0
