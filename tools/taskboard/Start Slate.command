#!/bin/bash
# Double-click to run Slate as a local web app (installable, offline-capable).
# Keep this window open while using the app; close it to stop the server.
cd "$(dirname "$0")"
PORT=8123
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  if curl -s --max-time 2 "http://localhost:$PORT" | grep -q "<title>Slate</title>"; then
    echo "Slate is already running at http://localhost:$PORT — opening it."
    open "http://localhost:$PORT"
    exit 0
  fi
  echo "Port $PORT is in use by something else."
  echo "NOTE: browser data is tied to the port — on a different port Slate starts empty"
  echo "(use Export/Import in the gear menu to move data). Trying the next free port…"
  while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
    PORT=$((PORT + 1))
  done
fi
( sleep 1; open "http://localhost:$PORT" ) &
echo "Slate is running at http://localhost:$PORT — press Ctrl+C or close this window to stop."
exec python3 -m http.server "$PORT"
