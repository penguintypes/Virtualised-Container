# Changes

## Phase 1: engine patches

The friend’s WSL launcher and C engine remain the execution authority; only the listed bug fixes and socat port forwarding were added.

## Phase 2: adapter and API

The old Python lifecycle runtime was removed from the merged design. The adapter translates API operations to the friend CLI and keeps only user-facing metadata locally.

## Phase 3: sample images and dashboard

Vcfile `RUN`, persisted `meta.json`, Alpine blog/runner images, the two sample UIs, and the vanilla dashboard were added.

## Phase 4: installer and tests

The WSL installer, PowerShell/NSIS launchers, verification checklist, no-root unit tests, and rootful integration script were added.

## Engine patches

- `engine/src/image.sh`: changed image and OCI stores from `/tmp` to `/var/lib/vcontainer` so the API and CLI share images.
- `engine/run_container.sh`: lists all image directories, waits before cgroup removal, unmounts overlay state, avoids clean rebuilds, validates unknown commands, adds `-p` and socat cleanup.
- `engine/src/vcontainer.c`: defaults hostname to the container name, uses the persistent image store, and confirms detached `execvp` through a CLOEXEC pipe.
- `engine/vcontainer.py`: debug command output is opt-in.

## Adapter and API

`backend/engine.py` delegates lifecycle, limits, namespaces, logs, exec, and image import/pull work to the friend launcher. `backend/core.py` only parses Vcfiles and reads image metadata. `backend/api.py` is the only server and serves the dashboard.

## Samples and UI

The blog and runner are Alpine Vcfiles with `RUN`; the blog uses SQLite comments and Markdown preview, and the runner uses Python, Node, and C. Java was omitted to keep the sample image smaller. The dashboard supports run, start, stop, logs, delete, build, stats, and published-port links.
- sec: established strict root-owned security boundary in /usr/local/libexec/vcontainer
- sys: installed uidmap and configured subordinate UID/GID ranges for user namespaces
- fix: removed deadlocking runtime recompilation and fixed image JSON parsing
- fix: restored execution script syntax and patched absolute path for C binary
- fix: build_helper.sh cp kept trailing /. so rootfs copies no longer nest and etc/resolv.conf is present; source must be under /var/lib/vcontainer/
- fix: run_container.sh cleanup trap keeps socat while the container's cgroup.procs is non-empty, so detached 8081/8082 stay reachable
- fix: repaired alpine meta.json (invalid JSON made GET /images return 400)
- docs: README installer URL set to the raw install.sh link, Ubuntu version and root-owned deploy rule documented
- fix: install.sh wrote alpine meta.json with escaped quotes, which made the file invalid JSON
- fix: install.sh asks for the sudoers NOPASSWD rule via /dev/tty when piped (curl | bash); defaults to no when there is no terminal, VC_SUDOERS=y overrides
- fix: backend/engine.py run() accepts command as a string (shlex.split) as well as a list; string form raised bad_request
- fix: backend/engine.py remove() stops a running container before rm, so API and dashboard delete work on running containers
- fix: samples/blog/index.html poll() ignores empty server responses, so the default post text no longer disappears
