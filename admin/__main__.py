"""Entry point:  python -m admin [--host 127.0.0.1] [--port 8787] [--open]"""
from __future__ import annotations

import argparse

from .server import serve


def main() -> None:
    ap = argparse.ArgumentParser(prog="admin", description="Local admin dashboard for the macro site")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (default localhost-only)")
    ap.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    args = ap.parse_args()

    if args.open:
        import threading
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
