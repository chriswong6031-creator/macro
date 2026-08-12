#!/bin/zsh
set -eu
umask 077

readonly OPS_CHECKOUT="/Users/chriswong/options-nbbo-ops-wt"
readonly PYTHON_BIN="/opt/homebrew/Caskroom/miniconda/base/bin/python"
readonly PRIVATE_ROOT="/Users/chriswong/.mastermind_private/momoedge_browser_observe_v1"

cd "$OPS_CHECKOUT"
exec "$PYTHON_BIN" -I "$OPS_CHECKOUT/scripts/momoedge_browser_receiver.py" --private-root "$PRIVATE_ROOT"
