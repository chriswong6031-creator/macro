#!/usr/bin/env python3
"""scripts/marketing_golden_set.py — XG-W5 golden-set CLI.

Three commands, all read-only against the engine:

    export   assemble a stratified, deterministic labeling batch from the
             ingested press corpus and write it as JSONL for a labeling session.
    eval     precision@k for the XG-W5 rank ordering vs the incumbent
             salience-only ordering, over whatever labels exist. Prints the
             honest "no labels yet" state rather than a fabricated pass.
    stats    what is in the label store and the corpus right now.

WHERE THE CORPUS COMES FROM. ``data/marketing/press/ingest_corpus.jsonl`` is
written by the press daemon on the VPS and is GITIGNORED — there is no ingested
corpus snapshot in the repo. Run `export` ON THE HOST and carry the batch back:

    ssh <vps> 'cd /srv/macro-dashboard && python3 scripts/marketing_golden_set.py \
        export --n 200 --out /tmp/golden_batch.jsonl'
    scp <vps>:/tmp/golden_batch.jsonl .

Then label the rows (fill each row's "label" with one of garbage / useful /
post_worthy / viral_grade) and land them in the label store with `import`.

THE LABEL STORE IS OPERATOR/FABLE-AUTHORED and committed by hand, like
config/reply_targets.yml. No engine path writes it, and the nightly does not
advance it — it is ground truth, not a forward ledger.

Exit codes: 0 on success (including "no labels yet"), 1 on a usage/IO error.
`eval --require-labels` is the opt-in strict mode for a future CI gate: it exits
1 when the comparison cannot be made. It is NOT wired into CI while the label
store is empty — a gate that can only be red is not a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repo root from {p}")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import golden_set as gs  # noqa: E402


def _load_corpus(args) -> tuple[list[dict], list[Path]]:
    if args.corpus:
        paths = [Path(args.corpus)]
    else:
        paths = gs.corpus_paths(ROOT)
        if args.allow_outbox_fallback:
            paths.append(ROOT / "data" / "marketing" / "outbox" / "items.jsonl")
    return gs.read_corpus(paths), paths


def cmd_export(args) -> int:
    rows, paths = _load_corpus(args)
    if not rows:
        print("no corpus rows found. Looked in:", flush=True)
        for path in paths:
            print(f"  {path} (exists={path.exists()})", flush=True)
        print("The ingested corpus is RUNTIME-ONLY (gitignored, VPS-side). "
              "Run this command on the press host — see the module docstring.",
              flush=True)
        return 0

    labels = gs.load_labels(ROOT, path=args.labels)
    batch = gs.export_batch(rows, n=args.n, labeled=labels.keys(), seed=args.seed,
                            now=datetime.now(tz=timezone.utc))
    out = Path(args.out) if args.out else (
        ROOT / "data" / "marketing" / "press" / f"golden_batch_{batch['batch_id']}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for item in batch["items"]:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"batch_id       : {batch['batch_id']}", flush=True)
    print(f"corpus rows    : {batch['corpus_rows']}", flush=True)
    print(f"already labeled: {batch['already_labeled']}", flush=True)
    print(f"returned       : {batch['returned']} / {batch['requested']}", flush=True)
    print(f"strata         : {batch['strata']}", flush=True)
    print(f"written        : {out}", flush=True)
    return 0


def cmd_import(args) -> int:
    """Fold a labeled batch file into the label store (append-only JSONL)."""
    src = Path(args.batch)
    if not src.exists():
        print(f"batch file not found: {src}", flush=True)
        return 1
    store = Path(args.labels) if args.labels else ROOT / gs.DEFAULT_LABEL_PATH
    store.parent.mkdir(parents=True, exist_ok=True)

    accepted, skipped, invalid = 0, 0, 0
    with store.open("a", encoding="utf-8") as out:
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            label = str(row.get("label", "")).strip()
            if not label:
                skipped += 1
                continue
            record = gs.make_label_row(
                row.get("item_id", ""), label, labeler=args.labeler,
                notes=str(row.get("notes", "")), headline=str(row.get("headline", "")),
                source=str(row.get("source", "")), batch_id=str(row.get("batch_id", "")),
            )
            errors = gs.validate_label_row(record)
            if errors:
                print(f"::warning title=golden-set-import::{row.get('item_id')}: "
                      f"{errors[0]}", flush=True)
                invalid += 1
                continue
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            accepted += 1

    print(f"accepted: {accepted}  unlabeled-skipped: {skipped}  invalid: {invalid}",
          flush=True)
    print(f"store   : {store}", flush=True)
    print("The label store is a COMMITTED artifact — review the diff and commit it.",
          flush=True)
    return 0


def cmd_eval(args) -> int:
    rows, paths = _load_corpus(args)
    labels = gs.load_labels(ROOT, path=args.labels)
    report = gs.evaluate(rows, labels, k=args.k)
    print(gs.format_report(report), flush=True)
    if not rows:
        print("  corpus paths   : " + ", ".join(str(p) for p in paths), flush=True)
    if args.json:
        print(json.dumps(report, indent=2), flush=True)
    if args.require_labels and report["state"] != "ok":
        print(f"::error title=golden-set-eval::state={report['state']} — "
              "the precision@k comparison could not be made", flush=True)
        return 1
    return 0


def cmd_stats(args) -> int:
    rows, paths = _load_corpus(args)
    labels = gs.load_labels(ROOT, path=args.labels)
    counts = {name: 0 for name in gs.LABELS}
    for row in labels.values():
        name = str(row.get("label", ""))
        if name in counts:
            counts[name] += 1
    with_components = sum(1 for r in rows if r.get("_components"))
    print(f"corpus rows        : {len(rows)}", flush=True)
    print(f"  with _components : {with_components}", flush=True)
    print(f"  paths            : " + ", ".join(str(p) for p in paths), flush=True)
    print(f"labels in store    : {len(labels)}  {counts}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", help="label-store path override")
    parser.add_argument("--corpus", help="corpus JSONL path override")
    parser.add_argument("--allow-outbox-fallback", action="store_true",
                        help="also read data/marketing/outbox/items.jsonl "
                             "(EMITTED items only — survivorship-biased)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="write a labeling batch")
    p_export.add_argument("--n", type=int, default=200)
    p_export.add_argument("--seed", default="xg-w5")
    p_export.add_argument("--out")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="fold a labeled batch into the store")
    p_import.add_argument("batch")
    p_import.add_argument("--labeler", default="operator")
    p_import.set_defaults(func=cmd_import)

    p_eval = sub.add_parser("eval", help="precision@k: rank ordering vs salience")
    p_eval.add_argument("--k", type=int, default=20)
    p_eval.add_argument("--json", action="store_true")
    p_eval.add_argument("--require-labels", action="store_true",
                        help="exit 1 when the comparison cannot be made")
    p_eval.set_defaults(func=cmd_eval)

    p_stats = sub.add_parser("stats", help="label store + corpus census")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
