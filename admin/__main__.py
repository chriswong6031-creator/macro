"""Entry point:  python -m admin [--host 127.0.0.1] [--port 8787] [--open] [--deployed]"""
from __future__ import annotations

import argparse
import os

from .server import serve


def main() -> None:
    ap = argparse.ArgumentParser(prog="admin", description="Admin console for the macro site")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (loopback only)")
    ap.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    ap.add_argument("--deployed", action="store_true",
                    help="run in deployed mode (auth required, behind a reverse proxy); "
                         "equivalent to ADMIN_DEPLOYED=1")
    args = ap.parse_args()

    if args.deployed:
        os.environ["ADMIN_DEPLOYED"] = "1"

    if args.open:
        import threading
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
