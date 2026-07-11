"""procutil — process-lifecycle helpers.

hard_exit() exists because of a macOS shutdown deadlock in pyarrow's C++ core
(pinned 2026-07-10 on the Mac Studio, pyarrow 24.0.0: ~1-in-3 hang rate for a
parquet-reading `python3 -c` one-shot). At interpreter exit, __cxa_finalize
runs the static destructor of Arrow's global ThreadPool; its Shutdown() waits
on a condition variable until every worker deregisters — and a worker wedged
in pthread bootstrap/teardown (racing the exiting main thread for dyld's
locks) never does. Symptoms: the process prints its final output then sits at
0% CPU forever; threading.enumerate() shows only MainThread (Arrow workers
are native); faulthandler prints nothing (Python is already finalized); even
lldb/sample cannot attach. SIGABRT crash-report stacks: main thread in
exit → __cxa_finalize_ranges → arrow::internal::ThreadPool::Shutdown → cv
wait, plus one frameless worker blocking the workers_.empty() predicate.

Exposure: any short-lived step whose LAST act reads parquet
(pandas.read_parquet spawns Arrow IO+CPU workers milliseconds before exit)
can stall a CI lane until timeout-minutes. Long-lived builders are
effectively immune — their workers finished bootstrap long before exit.
Arrow ships the mitigation (skip destructor shutdown) on Windows only, and
pyarrow exposes no pool-shutdown API, so the correct ending for a one-shot
is to skip C-runtime teardown entirely.
"""
from __future__ import annotations

import os
import sys


def hard_exit(code: int = 0) -> None:
    """Flush stdio and os._exit(code), skipping atexit/GC/C-static destructors.

    Append as the LAST statement of parquet-touching one-shot entrypoints.
    os._exit bypasses the interpreter-exit flush of any OTHER buffered file
    objects — close/flush your own writes first. Never call in long-lived
    processes or library code."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)
