# B1 natural-acceptance probe

Read-only evidence tooling for closing Prophet V4 B1's natural-production acceptance gate.
It asserts the B1 acceptance contract against a real generation using **B1's own canonical
reader**, so it cannot drift from the plane it is checking: if `load_candidate_episode_store_snapshot`
changes its validation, this probe inherits the change.

## Why it exists

B1 acceptance requires proving a specific list against real production bytes — valid atomic
`HEAD.json`, the referenced immutable generation, manifest/member hash validation, JSON/Parquet
twin agreement, canonical-reader resolution of exactly the HEAD-selected generation, at least one
ACTIVE episode, at least one newly `OPENED` episode, idempotence, canonical suppression
ownership, and no rank/gate/size/`ENTRY_OPEN` authority. Doing that by hand invites both
false accepts and false rejects.

## How to run it

The episode store lands as a nightly commit on `main`, so the probe materialises it out of git
with `git archive` and never touches the index. That matters in a sparse worktree, where
`data/` is deliberately absent — no full checkout is needed.

```bash
python3 b1_acceptance_probe.py --repo <worktree-path> --ref origin/main
```

Point `--root` at a directory instead when checking a store you already have on disk.

## Status when this was written

Validated against a real generation produced by B1's own nightly test
(`tests/test_us_candidate_episode_reconciler.py::test_natural_nightly_opens_once_and_publishes_exact_derived_targets`
run with `--basetemp`), which passed **30 checks, 0 fail**, leaving the tree clean. Run against
`origin/main` it correctly reports the store as absent, because no natural generation existed yet.

Two checks double as contract probes rather than pass/fail gates: the episode is asserted to
carry `opened_at` + `opened_session` (the inputs amendment A8 binds `decision_cut` to) and to
mint **no** decision or tradability clock (A8's premise, and the reason `tradable_at` is
`NOT_ASSERTED` until V4-B4 exists).

## What this probe does NOT cover — read this before calling B1 accepted

A green probe is a floor, not acceptance. It covers the store-shaped half of the
acceptance contract and is silent on the rest. Four items must be proven separately, and
naming them here is deliberate: a probe that looks comprehensive while quietly omitting
acceptance criteria is worse than no probe at all.

1. **Run identity and ancestry.** That the run is `event=schedule`, that `et_gate` kept it,
   and that its **HEAD SHA contains the B1 merge** are run-level facts this probe never sees.
   Check them against the run, and confirm the job log's actual `##[group]Run` list contains
   the `reconcile_us_candidate_episodes` step — checkout ancestry is not proof the step ran.
2. **Binding the receipt to that run.** The probe asserts the receipt carries
   `source_hashes`, `source_receipts`, `ledger_sha256` and `projection_hashes`, but not that
   those hashes match the inputs that particular run consumed. Compare them against the
   committed `episode_inputs/turn_watch/<session>.json` the run actually read.
3. **Duplicate / idempotence / retry semantics.** The probe checks that event ids are unique
   and content-addressed. It does not exercise a retry, and B1's keep-first contract is about
   what happens on the second write, not the first.
4. **Provisional Radar lineage staying staged and unarmed.** B1 accepts a Radar relation only
   as provisional (`DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS` R3). Nothing here checks that
   it has not been quietly promoted. Note `data/entry_radar/forward.parquet` is absent from
   `main`, so the Radar intake is expected to degrade to `UNREADABLE_SOURCE` — an expected
   honest degradation, not a fault.

A fresh independent critic must attack the full evidence packet, including these four.

## Interpreting a failure

A red check here is not automatically a B1 defect. Distinguish, per the failure taxonomy:
a store that is absent (the run did not execute the writer step — check the job log's actual
`##[group]Run` list, not checkout ancestry) from one that is present but invalid (a real B1
defect), and from a store whose episodes are all suppressed by Data OS identity resolution
(an upstream identity condition, which the receipt's suppression reasons will name).

## The probe

```python
#!/usr/bin/env python3
"""B1 natural-acceptance probe — READ-ONLY.

Materialises data/us_prophet_rank/episodes/ from a git ref into a temp dir and
asserts the B1 acceptance contract against it using B1's OWN canonical reader.

Usage:
  python3 b1_acceptance_probe.py --repo <path> --ref origin/main
  python3 b1_acceptance_probe.py --repo <path> --root /some/episodes/dir
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

STORE_PATH = "data/us_prophet_rank/episodes"
RESULTS: list[tuple[str, str, str]] = []  # (verdict, check, detail)


def record(ok: bool | None, check: str, detail: str = "") -> None:
    verdict = "PASS" if ok is True else ("FAIL" if ok is False else "INFO")
    RESULTS.append((verdict, check, detail))


def materialise(repo: Path, ref: str, dest: Path) -> Path:
    """git archive the episode store out of `ref` without touching the index."""
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "-C", str(repo), "archive", ref, STORE_PATH],
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode()[:200].strip()
        record(False, "episode store present in ref", f"git archive: {err}")
        return dest / STORE_PATH
    tar = subprocess.run(["tar", "-x", "-C", str(dest)], input=proc.stdout, capture_output=True)
    if tar.returncode != 0:
        raise SystemExit(f"tar failed: {tar.stderr.decode()[:400]}")
    return dest / STORE_PATH


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--root", default="")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))

    if args.root:
        root = Path(args.root)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="b1probe-"))
        root = materialise(repo, args.ref, tmp)
    record(root.exists(), "episode store present", str(root))
    if not root.exists():
        return emit()

    from engine.us_candidate_episode import (  # noqa: E402
        ACTIVE_STATE,
        EPISODE_STATES,
        HEAD_SCHEMA,
        canonical_json,
        load_candidate_episode_store_snapshot,
    )
    from hashlib import sha256  # noqa: E402

    # --- HEAD.json -------------------------------------------------------
    head_path = root / "HEAD.json"
    record(head_path.is_file(), "HEAD.json exists", str(head_path))
    head = json.loads(head_path.read_text()) if head_path.is_file() else {}
    record(head.get("schema") == HEAD_SCHEMA, "HEAD schema", repr(head.get("schema")))
    gen_id = str(head.get("generation_id", ""))
    import re
    record(bool(re.fullmatch(r"peg:[0-9a-f]{64}", gen_id)), "HEAD generation_id shape", gen_id)
    rest = {k: v for k, v in head.items() if k != "content_sha256"}
    expect = sha256(canonical_json(rest).encode("utf-8")).hexdigest()
    record(head.get("content_sha256") == expect, "HEAD content_sha256 self-hash", "")

    # --- canonical reader: validates manifest + payload cross-checks ------
    try:
        snap = load_candidate_episode_store_snapshot(root)
        record(True, "canonical reader load_candidate_episode_store_snapshot", "validated")
    except Exception as exc:  # noqa: BLE001
        record(False, "canonical reader load_candidate_episode_store_snapshot", f"{type(exc).__name__}: {exc}")
        return emit()

    record(snap.generation_id == gen_id,
           "reader resolves exactly the HEAD-selected generation",
           f"reader={snap.generation_id} head={gen_id}")

    # --- orphan / non-HEAD generations ------------------------------------
    gens_dir = root / "generations"
    gens = sorted(p.name for p in gens_dir.iterdir() if p.is_dir()) if gens_dir.is_dir() else []
    record(gen_id in gens, "HEAD generation present on disk", f"{len(gens)} generation(s)")
    orphans = [g for g in gens if g != gen_id]
    record(None, "non-HEAD generations (noncanonical by contract)",
           ", ".join(orphans) if orphans else "none")

    # --- episodes ---------------------------------------------------------
    gen = snap.generation
    episodes = _episodes_of(gen)
    record(len(episodes) > 0, "at least one episode exists", f"{len(episodes)} episode(s)")
    active = [e for e in episodes if e.get("episode_state") == ACTIVE_STATE]
    record(len(active) > 0, "at least one ACTIVE episode", f"{len(active)} active")
    bad_state = [e for e in episodes if e.get("episode_state") not in EPISODE_STATES]
    record(not bad_state, "all episode states in EPISODE_STATES",
           ", ".join(sorted({str(e.get('episode_state')) for e in bad_state})) or "ok")

    events = _events_of(gen)
    opened = [e for e in events if e.get("event_type") == "OPENED"]
    record(len(opened) > 0, "at least one newly OPENED episode event", f"{len(opened)} OPENED")
    ids = [e.get("event_id") for e in events]
    record(len(ids) == len(set(ids)), "event ids unique (idempotence/keep-first)",
           f"{len(ids)} events / {len(set(ids))} unique")
    record(all(str(i).startswith("pee:") for i in ids), "event ids content-addressed 'pee:'", "")

    ep_ids = [e.get("episode_id") for e in episodes]
    record(all(str(i).startswith("pe:") for i in ep_ids), "episode ids canonical 'pe:'", "")
    record(len(ep_ids) == len(set(ep_ids)), "episode ids unique", "")

    # --- suppressions + receipt ------------------------------------------
    supps = list(getattr(gen, "suppressions", ()) or ())
    record(None, "suppressions emitted", f"{len(supps)}")
    from engine.us_candidate_episode import SUPPRESSION_REASONS, SUPPRESSION_SCHEMA
    bad_reason = sorted({str(s_.get("reason")) for s_ in supps
                         if s_.get("reason") not in SUPPRESSION_REASONS})
    record(not bad_reason, "all suppression reasons canonical", ", ".join(bad_reason) or "ok")
    bad_schema = sorted({str(s_.get("schema")) for s_ in supps
                         if s_.get("schema") not in (SUPPRESSION_SCHEMA, None)})
    record(not bad_schema, "suppression schema canonical", ", ".join(bad_schema) or "ok")

    receipt = getattr(gen, "receipt", {}) or {}
    record(bool(receipt), "reconcile receipt present", ", ".join(sorted(receipt)[:12]))
    for key in ("ledger_sha256", "projection_hashes", "source_hashes", "source_receipts"):
        record(bool(receipt.get(key)), f"receipt carries {key}", "")
    record(receipt.get("mode") == "nightly", "receipt mode is nightly", str(receipt.get("mode")))
    record(bool(receipt.get("durable_write")), "receipt records a durable write",
           str(receipt.get("durable_write")))

    # --- A8 inputs present / no decision clock minted -------------------
    ep0 = episodes[0] if episodes else {}
    record(bool(ep0.get("opened_at")) and bool(ep0.get("opened_session")),
           "episode carries opened_at + opened_session (A8 decision_cut inputs)",
           f"{ep0.get('opened_at')} / {ep0.get('opened_session')}")
    minted = sorted(k for k in ep0 if k in ("decision_at", "tradable_at", "decision_cut"))
    record(not minted, "episode mints NO decision/tradability clock (A8 premise)",
           ", ".join(minted) or "none - tradable_at must be NOT_ASSERTED")

    # --- authority fence ---------------------------------------------------
    forbidden = {"rank", "score", "gate", "size", "weight", "entry_open", "priority"}
    leaked: set[str] = set()
    for e in episodes[:500]:
        leaked |= {k for k in e if k.lower() in forbidden}
    record(not leaked, "no rank/gate/size/ENTRY_OPEN fields on episodes",
           ", ".join(sorted(leaked)) or "clean")

    return emit()


def _episodes_of(gen) -> list[dict]:
    return list(getattr(gen, "episodes", ()) or ())


def _events_of(gen) -> list[dict]:
    return list(getattr(gen, "events", ()) or ())


def emit() -> int:
    width = max((len(c) for _, c, _ in RESULTS), default=10)
    fails = 0
    print()
    for verdict, check, detail in RESULTS:
        if verdict == "FAIL":
            fails += 1
        print(f"  [{verdict:4}] {check.ljust(width)}  {detail}")
    print(f"\n  {len(RESULTS)} checks, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
```
