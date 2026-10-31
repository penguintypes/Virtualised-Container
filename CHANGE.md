# Changes

## Phase 1: Engine patches
The friend’s WSL launcher and C engine remain the execution authority; only the listed bug fixes and socat port forwarding were added.
- `engine/src/image.sh`: changed image and OCI stores from `/tmp` to `/var/lib/vcontainer` so the API and CLI share images.
- `engine/run_container.sh`: lists all image directories, waits before cgroup removal, unmounts overlay state, avoids clean rebuilds, validates unknown commands, adds `-p` and socat cleanup.
- `engine/src/vcontainer.c`: defaults hostname to the container name, uses the persistent image store, and confirms detached `execvp` through a CLOEXEC pipe.
- `engine/vcontainer.py`: debug command output is opt-in.
- sec: established strict root-owned security boundary in /usr/local/libexec/vcontainer
- sys: installed uidmap and configured subordinate UID/GID ranges for user namespaces
- fix: removed deadlocking runtime recompilation and fixed image JSON parsing
- fix: restored execution script syntax and patched absolute path for C binary
- fix: build_helper.sh cp kept trailing /. so rootfs copies no longer nest and etc/resolv.conf is present; source must be under /var/lib/vcontainer/
- fix: run_container.sh cleanup trap keeps socat while the container's cgroup.procs is non-empty, so detached 8081/8082 stay reachable
- fix: engine/src/cgroup.sh sets memory.swap.max to 0 with the memory limit, so an over-limit process is killed instead of swapped (WSL2)
- fix: engine.remove catches rm exceptions to prevent ghost containers
- fix: engine.build() strips only trailing --clean/--update flags, so Vcfile paths with spaces work
- fix: engine exec joins the container cgroup (--cgroup), so exec honors memory and pid limits
- fix: run_container.sh cleanup checks cgroup.procs with sudo cat (-n); -s is always false on kernel files
- fix: run_container.sh no longer compiles the C engine into /tmp/vcontainer-work on every start; only the .sh helpers are copied there
- fix: persist container resource limits (memory, cpus, pids) in engine.json and restore them on restart
- fix: run_container.sh passes --seccomp by default, so containers block mount, pivot_root, ptrace, unshare, setns and module syscalls and set no_new_privs
- fix: engine.inspect pops cgroup pids to prevent shadowing the saved pids limit
- sec: replace hardcoded /tmp/vcontainer-work with mktemp -d to prevent collision and symlink attacks

## Phase 2: Adapter and API
The old Python lifecycle runtime was removed from the merged design. The adapter translates API operations to the friend CLI and keeps only user-facing metadata locally. `backend/engine.py` delegates lifecycle, limits, namespaces, logs, exec, and image import/pull work to the friend launcher. `backend/core.py` only parses Vcfiles and reads image metadata. `backend/api.py` is the only server and serves the dashboard.
- fix: backend/engine.py run() accepts command as a string (shlex.split) as well as a list; string form raised bad_request
- fix: backend/engine.py remove() stops a running container before rm, so API and dashboard delete work on running containers
- fix: backend api forwards clean and update flags to engine.build
- fix: catch BrokenPipeError on client disconnect (api.py)
- fix: resolve test imports, stop loop, mojibake, and security leaks
- refactor: de-golf api.py for better human readability

## Phase 3: Samples and Dashboard (UI)
Vcfile `RUN`, persisted `meta.json`, Alpine blog/runner images, the two sample UIs, and the vanilla dashboard were added. The blog and runner are Alpine Vcfiles with `RUN`; the blog uses SQLite comments and Markdown preview, and the runner uses Python, Node, and C. Java was omitted to keep the sample image smaller. The dashboard supports run, start, stop, logs, delete, build, stats, and published-port links.
- fix: repaired alpine meta.json (invalid JSON made GET /images return 400)
- fix: samples/blog/index.html poll() ignores empty server responses, so the default post text no longer disappears
- feat: grouped run actions into a split-button dropdown in GUI
- feat: GUI build asks for --clean and --update via confirm() prompts
- fix: corrected GUI dropdown CSS inline override to restore toggle visibility
- fix: gui show() replaces the view with 'Failed to load <kind>: <error>' when a request fails, so no stale container list remains
- feat: Portainer-inspired dashboard (Home, container detail with logs/stats/exec, images upload/download, dark/light theme)
- feat: Home container cards with exec and details, single-page container detail, sidebar system panel, fix PIDs limit display
- feat: minimal two-column Home cards with usage bars and Open button
- feat: lavender/pink theme, host gauges on Home, GET /system endpoint
- feat: Home keeps gauges when backend is offline, boxed sidebar tabs, clearer tables, compact detail page
- fix: Quick start creates a new container each click, responsive tables and detail page, larger Details, equal header buttons
- feat: logs above console with last-lines view, Open button in details, livelier Images table, status pills on Home, Image storage tile
- feat: aligned detail page grid, colour-filled Details/Start/Stop/Delete buttons
- fix: stable card and detail layout for stopped containers, Details as its own table column
- fix: tighter top and bottom spacing so Home has no scrollbar with two containers

## Phase 4: Installer and Tests
The WSL installer, PowerShell/NSIS launchers, verification checklist, no-root unit tests, and rootful integration script were added.
- fix: install.sh wrote alpine meta.json with escaped quotes, which made the file invalid JSON
- fix: install.sh asks for the sudoers NOPASSWD rule via /dev/tty when piped (curl | bash); defaults to no when there is no terminal, VC_SUDOERS=y overrides
- fix: install.nsi uses ExecWait so sudo can prompt, and excludes .git, install.exe and engine-arm from the bundle; install.ps1 honors VC_DISTRO, stops if install.sh fails, and waits for :8080 instead of sleeping 12 s (untested on Windows)
- fix: install.ps1 converts backslashes to slashes and strips the \wsl.localhost prefix before calling bash; tested by running it from PowerShell (install.exe and C:\ paths still untested)
- feat: start.sh launches only the dashboard without auto-starting demo containers
- test: added tests/rest_cases.sh (one-command run of 6 REST cases incl. memory limit) and rewrote vcontainer_6_test_cases.md for the REST API with list commands
- test: verify install.exe works on Windows
- test: rest_cases.sh runs cases in the doc order (B1, B2, C1, C2, A1, A2); vcontainer_6_test_cases.md C1 now uses the API stop like the script

## Documentation
- docs: README documents Ubuntu version and the root-owned deploy rule
- docs: README install section now says clone + bash install.sh (removed the one-line curl installer, which cannot work), notes install.exe is built locally with makensis, and points to engine-arm/
- docs: ARCHITECTURE.md names run_container.sh instead of a stray backticked phrase
- docs: mark C:\ path installation as verified
- docs: README and ARCHITECTURE.md describe seccomp default, the dashboard, GET /system, image upload/download, start route and the 6 REST cases

## Chores and Cleanup
- chore: removed one-off patch scripts (patch_images.py)
- chore: removed duplicated JS/CSS blocks in gui/app.js and gui/style.css
- chore: removed fix_install.py, fix_dropdown.py, cleanup.py, vcontainer-source-dump.txt, and install.exe
- chore: ignore vcontainer_source_dump.txt in git
## 2026-10-29 - change04
- Merged friend's GUI layout and features into stdlib backend
- Added /system/disk and /volumes API endpoints using Python 3.14 stdlib
- Stripped desktop window/pywebview bindings from GUI for clean browser support

## 2026-10-29 - change05
- fix: removed duplicate setTheme() declaration in gui/app.js; verified JavaScript syntax with node --check gui/app.js (exit code 0).

## 2026-10-29 - change06
- fix: restored dashboard render error visibility and added console diagnostics to investigate the blank screen.

## 2026-10-29 - change07
- fix: removed the obsolete pywebview window/title-bar shell from gui/index.html; visually verified the dashboard renders correctly in the browser.
- 2026-10-29 19:12 fix: remove obsolete window shell from index.html, restore render error diagnostics, validate volume name before removal, clean whitespace
- 2026-10-30 12:19 fix: repair backend run_volume to use engine script for safe deletion
- 2026-10-30 12:19 feat: patch C engine to support --env and create standard /dev nodes

## 2026-10-31 - change08
- feat: Added live graphs, compact cards, and Details routes to dashboard GUI
- feat: Added /images/pull and /system/live API routes for dashboard metrics
- feat: API POST /containers now requires a `memory` parameter to prevent host OOM
- feat: Added "Launch BlogDrop" quick-action to dashboard to spin up standard stack
- feat: Added default command fallbacks for mysql, nginx, and node images in engine
- fix: API automatically marks missing/ghost containers as stopped on boot
- fix: Start-handler preserves volumes, env, network, and IP across restarts
- fix: Preserved explicit --ip arguments when -p (ports) are passed
- fix: Changed engine default cpu_quota to "max" (unlimited) and fixed CPU % cache
- fix: Corrected userns map to cover root and standard user identities correctly
- fix: Engine stop path retries rmdir up to 50 times to bypass cgroup kernel locks
- fix: Cleaned up stop/inspect response parsing to strip trailing whitespace keys
- fix: Added fflush(stderr) in C engine die() to prevent swallowed error outputs
- almost05: Added .mailmap to standardize author identity.
- almost05: Fixed javascript syntax crash in gui/app.js causing dashboard hang.
- almost06: Reorganized file hierarchy, moved loose script files into `patches/`.
- almost06: Fixed `backend/api.py` POST payload syntax error blocking server boot.
- almost06: Fixed `backend/engine.py` "string indices must be integers" by supporting dictionary payload parsing.
- almost06: Fixed "list object has no attribute items" error by properly parsing env array iterations.
- almost06: Fixed the Node backend crash by injecting `sh -c "cd /app && npm start"` because engine lacks working directory support.
- almost06: Resolved Nginx container launch failure by properly naming the `blogdrop-nginx` volume.

## 2026-10-31 14:40 - change09
- refactor: moved engine/ to backend/runtime/, samples and tests into backend/, machine/ and scripts/ into windows/; removed engine-arm/
- refactor: root keeps only README.md, CHANGE.md, install.sh, start.sh, install.ps1, install.nsi, var/, backend/, gui/, docs/, windows/
- chore: patches/ is local only and gitignored (supersedes the almost06 note about moving scripts into patches/)
- fix: install.sh stages backend/samples/{blog,runner} to /var/lib/vcontainer/samples before building, so build_helper.sh accepts the source path
- fix: run_container.sh trap quoting inside bash -c (pull and import), which caused "work: unbound variable"
- fix: backend/tests/rest_cases.sh sends "memory" in every create payload, as POST /containers requires it
- fix: backend/tests/rest_cases.sh reads the "output" key from the logs route, not "logs"
- test: rest_cases.sh 6/6 passed after the restructure
- feat: BlogDrop account page, admin users table with Reset/Delete, Admin tag, locked admin email
- feat: BlogDrop duplicate username/email checks (case, dots, +tag)
- feat: BlogDrop comment delete (commenter, blog author, admin) and per-user view counting
- feat: dashboard Kill all containers and Kill server buttons
- docs: README paths updated for the new layout

## 2026-10-31 15:11 - change10
- fix: GET /containers/{name}/metrics returns zeroed metrics instead of a 400 when the container dies during inspect (mountinfo read race)
