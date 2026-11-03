#!/usr/bin/env bash
set -eu

runtime=/opt/vcontainer/bin/vcontainer-cli

"$runtime" volume create app-data || true
"$runtime" volume create app-logs || true

"$runtime" run kali \
  --name multi-volume-example \
  --volume app-data:/data \
  --volume app-logs:/logs \
  -- /bin/sh -lc 'echo application-data > /data/example.txt; echo application-log > /logs/example.log'
