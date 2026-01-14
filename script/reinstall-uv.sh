#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Reinstalling agj with uv (editable) from: ${ROOT_DIR}"

if command -v uv >/dev/null 2>&1; then
  uv tool uninstall agj >/dev/null 2>&1 || true
  uv tool install "${ROOT_DIR}" --editable --force
  echo "Done. If agj still looks old, run: hash -r"
else
  echo "uv not found on PATH."
  exit 1
fi
