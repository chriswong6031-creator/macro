#!/usr/bin/env python3
"""Light/dark screenshot sweep for user-facing pages (DESIGN_DOCTRINE §5.8 proof).

Captures full-page headless-Chrome screenshots of site pages in BOTH themes so a
light-mode design pass can be judged as a design, not as "does it render".
Off the render path — run locally during design work, never in the nightly.

The pages default the theme from localStorage (absent = dark), so light is
forced by serving a temp copy with data-theme="light" stamped on <html>.
Headless Chrome writes the PNG and then hangs on this site's live timers, so
each capture polls for the output file and then kills its own Chrome profile.

Usage:
  python3 scripts/light_mode_sweep.py --pages us_stocks,subsectors,macro --out /tmp/sweep
  python3 scripts/light_mode_sweep.py --pages baskets --themes light --pairs
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP_PREFIX = "_lm_sweep_tmp_"


def serve(site_dir: Path) -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def capture(url: str, out_png: Path, profile: Path, size: str, timeout_s: int = 75) -> bool:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if out_png.exists():
        out_png.unlink()
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={size}", f"--user-data-dir={profile}",
         f"--screenshot={out_png}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout_s
    ok = False
    while time.time() < deadline:
        # Chrome writes the PNG atomically-enough; a short settle after first
        # sight avoids reading a partial file.
        if out_png.exists() and out_png.stat().st_size > 10_000:
            time.sleep(2)
            ok = True
            break
        time.sleep(1.5)
    try:
        proc.send_signal(signal.SIGKILL)
    except ProcessLookupError:
        pass
    subprocess.run(["pkill", "-f", str(profile)], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="site")
    ap.add_argument("--pages", required=True,
                    help="comma list of page names without .html (e.g. us_stocks,macro)")
    ap.add_argument("--out", default="/tmp/light_mode_sweep")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--size", default="1440,6200")
    ap.add_argument("--tag", default="", help="filename suffix (e.g. before/after)")
    ap.add_argument("--pairs", action="store_true",
                    help="also write dark-over-light pair composites (needs PIL)")
    args = ap.parse_args()

    site = Path(args.site_dir).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    pages = [p.strip().removesuffix(".html") for p in args.pages.split(",") if p.strip()]
    tag = f"_{args.tag}" if args.tag else ""

    tmp_files: list[Path] = []
    httpd, port = serve(site)
    failures: list[str] = []
    try:
        for page in pages:
            src = site / f"{page}.html"
            if not src.exists():
                print(f"::warning title=light-mode-sweep::missing page {page}.html", flush=True)
                failures.append(page)
                continue
            for theme in themes:
                if theme == "light":
                    tmp = site / f"{TMP_PREFIX}{page}.html"
                    html = src.read_text(encoding="utf-8")
                    stamped = html.replace('<html lang="en">',
                                           '<html lang="en" data-theme="light">', 1)
                    if stamped == html:
                        print(f"::warning title=light-mode-sweep::no <html lang=\"en\"> "
                              f"anchor in {page}.html — light not forced", flush=True)
                    # Seed localStorage BEFORE any boot script runs: some pages
                    # (hub) set data-theme unconditionally from storage/auto-hour
                    # and would override the attribute stamp above.
                    seed = ("<script>try{localStorage.setItem('theme','light');"
                            "localStorage.removeItem('themeAuto');}catch(e){}</script>")
                    if "<head>" in stamped:
                        stamped = stamped.replace("<head>", "<head>" + seed, 1)
                    else:
                        stamped = stamped.replace("</title>", "</title>" + seed, 1)
                    tmp.write_text(stamped, encoding="utf-8")
                    tmp_files.append(tmp)
                    url = f"http://127.0.0.1:{port}/{tmp.name}"
                else:
                    url = f"http://127.0.0.1:{port}/{page}.html"
                png = out / f"{page}_{theme}{tag}.png"
                profile = out / f".prof_{page}_{theme}"
                ok = capture(url, png, profile, args.size.replace(" ", ""))
                print(f"{'ok ' if ok else 'FAIL'} {png.name}", flush=True)
                if not ok:
                    failures.append(f"{page}:{theme}")
                shutil.rmtree(profile, ignore_errors=True)
            if args.pairs and len(themes) == 2:
                try:
                    from PIL import Image
                    a = Image.open(out / f"{page}_{themes[0]}{tag}.png")
                    b = Image.open(out / f"{page}_{themes[1]}{tag}.png")
                    combo = Image.new("RGB", (a.width, a.height + b.height + 6), (255, 0, 0))
                    combo.paste(a, (0, 0))
                    combo.paste(b, (0, a.height + 6))
                    combo.save(out / f"{page}_pair{tag}.png")
                except Exception as e:  # noqa: BLE001 — pairs are a convenience
                    print(f"pair skipped for {page}: {e}", flush=True)
    finally:
        for tmp in tmp_files:
            tmp.unlink(missing_ok=True)
        httpd.shutdown()

    if failures:
        print(f"::warning title=light-mode-sweep::{len(failures)} capture(s) failed: "
              f"{', '.join(failures)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
