#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

if [ "${1:-}" != "--no-venv" ]; then
  if [ ! -d .venv ]; then
    "$PYTHON" -m venv .venv
  fi
  PYTHON="$ROOT/.venv/bin/python"
  SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "$ROOT/src" > "$SITE/director-src.pth"
  echo "Installed source path into $SITE/director-src.pth (offline; no global changes)."
else
  export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
  echo "No venv created; PYTHONPATH is set for this session only."
fi

"$PYTHON" -m director --version
echo "Next: python -m director init --root . --name my-project --domain general"
echo "Then: python -m director doctor"
