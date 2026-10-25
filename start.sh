#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
echo "dashboard: http://localhost:8080"
PYTHONPATH="$root" exec python3 -m backend.api
