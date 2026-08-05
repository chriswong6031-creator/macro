#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone full backfill of the 减持 store. Run this directly.

    python3 scripts/_download_cn_holder.py

This used to be a hand-copied fork of `collectors/cn_holder_sale_calendar` — its own
pager, its own `_clean`, and its own `_suffix`. The two copies drifted, which is how the
Beijing bug came to need fixing twice: both mapped Shanghai with a bare
`code.startswith("6")` and swept 92xxxx (Beijing, post-2023 renumbering) and 900xxx
(Shanghai B-shares) into `.SZ`. It is now a thin wrapper, so there is exactly one
producer of `data/cn_holder_sales/` and one mapper behind it
(`collectors.china_ths_concepts.to_suffixed`).

`collect(force=True)` is a strict superset of what this script used to do: same
endpoint, same filter, same cleaning, and it also writes `windows.parquet` (the fork
only ever wrote `raw.parquet`, leaving the window panel stale behind it).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.cn_holder_sale_calendar import collect  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    collect(force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
