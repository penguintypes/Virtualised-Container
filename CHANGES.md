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
- docs: README documents Ubuntu version and the root-owned deploy rule
- fix: install.sh wrote alpine meta.json with escaped quotes, which made the file invalid JSON
- fix: install.sh asks for the sudoers NOPASSWD rule via /dev/tty when piped (curl | bash); defaults to no when there is no terminal, VC_SUDOERS=y overrides
- fix: backend/engine.py run() accepts command as a string (shlex.split) as well as a list; string form raised bad_request
- fix: backend/engine.py remove() stops a running container before rm, so API and dashboard delete work on running containers
- fix: samples/blog/index.html poll() ignores empty server responses, so the default post text no longer disappears
- test: added tests/rest_cases.sh (one-command run of 6 REST cases incl. memory limit) and rewrote vcontainer_6_test_cases.md for the REST API with list commands
- fix: engine/src/cgroup.sh sets memory.swap.max to 0 with the memory limit, so an over-limit process is killed instead of swapped (WSL2)
- docs: README install section now says clone + bash install.sh (removed the one-line curl installer, which cannot work), notes install.exe is built locally with makensis, and points to engine-arm/
- fix: backend api forwards clean and update flags to engine.build
- feat: grouped run actions into a split-button dropdown in GUI
- feat: GUI build asks for --clean and --update via confirm() prompts
- fix: corrected GUI dropdown CSS inline override to restore toggle visibility
- fix: engine.remove catches rm exceptions to prevent ghost containers
- chore: removed one-off patch scripts (patch_images.py)
- fix: engine.build() strips only trailing --clean/--update flags, so Vcfile paths with spaces work
- fix: engine exec joins the container cgroup (--cgroup), so exec honors memory and pid limits
- fix: run_container.sh cleanup checks cgroup.procs with sudo cat (-n); -s is always false on kernel files
- chore: removed duplicated JS/CSS blocks in gui/app.js and gui/style.css
- chore: removed fix_install.py, fix_dropdown.py, cleanup.py, vcontainer-source-dump.txt, and install.exe
- fix: gui show() replaces the view with 'Failed to load <kind>: <error>' when a request fails, so no stale container list remains
- docs: ARCHITECTURE.md names run_container.sh instead of a stray backticked phrase
- fix: run_container.sh no longer compiles the C engine into /tmp/vcontainer-work on every start; only the .sh helpers are copied there
- fix: install.nsi uses ExecWait so sudo can prompt, and excludes .git, install.exe and engine-arm from the bundle; install.ps1 honors VC_DISTRO, stops if install.sh fails, and waits for :8080 instead of sleeping 12 s (untested on Windows)
- fix: install.ps1 converts backslashes to slashes and strips the \\wsl.localhost prefix before calling bash; tested by running it from PowerShell (install.exe and C:\ paths still untested)
- fix: catch BrokenPipeError on client disconnect (api.py)
- test: verify install.exe works on Windows
- docs: mark C:\ path installation as verified
- refactor: de-golf api.py for better human readability
- feat: start.sh launches only the dashboard without auto-starting demo containers
- fix: resolve test imports, stop loop, mojibake, and security leaks
- fix: persist container resource limits (memory, cpus, pids) in engine.json and restore them on restart
- fix: run_container.sh passes --seccomp by default, so containers block mount, pivot_root, ptrace, unshare, setns and module syscalls and set no_new_privs
- feat: Portainer-inspired dashboard (Home, container detail with logs/stats/exec, images upload/download, dark/light theme)
- feat: Portainer-inspired dashboard (Home, container detail with logs/stats/exec, images upload/download, dark/light theme)
- feat: Home container cards with exec and details, single-page container detail, sidebar system panel, fix PIDs limit display
- feat: minimal two-column Home cards with usage bars and Open button
- feat: lavender/pink theme, host gauges on Home, GET /system endpoint
- feat: Home keeps gauges when backend is offline, boxed sidebar tabs, clearer tables, compact detail page
- fix: Quick start creates a new container each click, responsive tables and detail page, larger Details, equal header buttons
- feat: logs above console with last-lines view, Open button in details, livelier Images table, status pills on Home, Image storage tile
