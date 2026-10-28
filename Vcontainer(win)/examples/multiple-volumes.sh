#!/usr/bin/env bash
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$project_dir/engine/run_container.sh" volume create app-data || true
"$project_dir/engine/run_container.sh" volume create app-logs || true

"$project_dir/engine/run_container.sh" run kali \
  --name multi-volume-example \
  --volume app-data:/data \
  --volume app-logs:/logs \
  -- /bin/sh -lc 'echo application-data > /data/example.txt; echo application-log > /logs/example.log'
