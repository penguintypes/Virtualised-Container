#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cli="$root/engine/run_container.sh"
[ "$(id -u)" -eq 0 ] || { echo 'integration tests require root or passwordless sudo'; exit 2; }
"$cli" run alpine --name itest --detach --memory-max 64M --pids-max 8 -- sh -c 'hostname; echo secret >/tmp/inside; sleep 3600'
"$cli" inspect itest | tee /tmp/vcontainer-inspect
host=$(hostname); grep -q 'status=running' /tmp/vcontainer-inspect; ! grep -q "hostname=$host" /tmp/vcontainer-inspect || true
"$cli" exec itest -- sh -c 'test -f /tmp/inside'
"$cli" logs itest || true
"$cli" stop itest; "$cli" rm itest
! find /sys/fs/cgroup/vcontainer -mindepth 1 -maxdepth 1 -name itest -print -quit 2>/dev/null | grep -q .
python3 - <<'PY'
import urllib.request
for port in (8081, 8082):
    urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=3)
PY
curl -fsS http://127.0.0.1:8082/run -H 'Content-Type: application/json' -d '{"language":"python","code":"print(2+2)"}'
