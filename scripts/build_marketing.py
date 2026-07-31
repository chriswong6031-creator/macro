"""scripts/build_marketing.py — Thin orchestrator for the Marketing lobe governor.

Usage:
    python -m scripts.build_marketing

Mirrors the prophet builder shape; no R2 needed v1.
Never-raise: exits 0 with a warning message on error so the pipeline continues.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    try:
        from engine.neuralweb.marketing_governor import build_and_write
        result = build_and_write()
    except Exception as exc:  # noqa: BLE001
        log.warning("build_marketing: governor import/run failed: %s", exc)
        print(f"marketing_governor: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0

    if result.get("error"):
        print(
            f"marketing_governor: WARN (never-raise) — {result['error']}",
            file=sys.stderr,
        )
        return 0

    print(
        f"marketing_governor: ok — "
        f"state={result.get('state_path')} "
        f"lobe={result.get('lobe_path')}"
    )

    # Telemetry roll-up (never-raise; runs after governor)
    try:
        from engine.marketing.telemetry import (
            unconfirmed_sends as _unconfirmed_sends,
            write_rollup,
        )
        s = write_rollup(root=None)
        if s.get("error"):
            print(
                f"marketing_telemetry: WARN (never-raise) — {s['error']}",
                file=sys.stderr,
            )
        else:
            # THE INVERSE SCAN, run alongside the roll-up (2026-07-31).
            # `orphans` above walks METRICS ROWS and flags any with no outbox
            # item — "we measured something we did not plan". The opposite and
            # more damaging case, "we marked it posted and it never went out",
            # produces no metrics row to walk, so nothing was looking for it.
            # `posted` means Buffer ACCEPTED the item, not that it reached X.
            _uc = _unconfirmed_sends(root=None)
            print(
                f"marketing_telemetry: ok — "
                f"posts={s.get('n_posts', 0)} "
                f"rows={s.get('n_rows', 0)} "
                f"orphans={s.get('n_orphans', 0)} "
                f"unmeasured={s.get('n_unmeasured', 0)} "
                f"send_confirmed={_uc.get('confirmed', 0)}/{_uc.get('posted', 0)} "
                f"unconfirmed={_uc.get('unconfirmed', 0)} "
                f"pending={_uc.get('pending', 0)}"
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("build_marketing: telemetry write_rollup failed: %s", exc)
        print(f"marketing_telemetry: WARN (never-raise) — {exc}", file=sys.stderr)

    # Hot Tape nightly context pack (never-raise; masterplan §3.1 — heavy compute
    # nightly so the 5-minute intraday radar stays a light json join).
    # root is EXPLICIT here, unlike the two blocks above: hot_tape_pack.build_pack
    # does Path(root) with no default, so a None would fail-soft into an empty
    # pack every night. cfg makes config/hot_tape.yml's universe block operative.
    try:
        from pathlib import Path
        from engine.marketing.hot_tape import load_config
        from engine.marketing.hot_tape_pack import write_pack
        _root = Path(__file__).resolve().parent.parent
        s = write_pack(_root, cfg=load_config(_root))
        if s.get("error"):
            print(
                f"hot_tape_pack: WARN (never-raise) — {s['error']}",
                file=sys.stderr,
            )
        else:
            print(
                f"hot_tape_pack: ok — "
                f"n={s.get('n_tickers', 0)} "
                f"path={s.get('path')}"
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("build_marketing: hot_tape_pack write_pack failed: %s", exc)
        print(f"hot_tape_pack: WARN (never-raise) — {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
