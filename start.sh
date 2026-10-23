#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
PYTHONPATH="$root" python3 - <<'PY'
from backend import engine
for n, p in (("blog", "8081:8081"), ("runner", "8082:8082")):
    for f in (engine.stop, engine.remove):
        try: f(n)
        except Exception: pass
    engine.run(n, n, port=p)
PY
echo "blog:      http://localhost:8081"
echo "runner:    http://localhost:8082"
echo "dashboard: http://localhost:8080"
PYTHONPATH="$root" exec python3 -m backend.api
