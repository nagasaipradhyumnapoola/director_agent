#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
if [ -x .venv/bin/python ]; then
  SITE="$(.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"
  rm -f "$SITE/director-src.pth"
fi
if [ "${1:-}" = "--remove-venv" ] && [ -d .venv ]; then
  rm -rf .venv
fi
echo "Uninstalled the local source-path entry."
echo "Project state under .director/, research files and generated adapters were NOT deleted."
