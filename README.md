# vcontainer merged project

A student-sized Docker-like container runtime for WSL2 Ubuntu (tested on 26.04). The C and Bash engine in `backend/runtime/` handles namespaces, cgroups v2, overlayfs, virtual networking, and process lifecycle. The Python adapter, REST API, dashboard, Vcfile parser, samples, and integration tests provide management and visibility.

## Quick Start

```bash
bash install.sh
./start.sh
```

- **Dashboard:** `http://localhost:8080`
- **Start:** `./start.sh` launches only the dashboard. Start the demo containers from Quick start on Home (blog on 8081, runner on 8082), or launch the complete BlogDrop web stack via the dashboard button (gateway on 8085).
- **Install (WSL2 Ubuntu or Linux):** `git clone -b parzivalSr-test https://github.com/penguintypes/Virtualised-Container.git && cd Virtualised-Container && bash install.sh` (the repo is private for now, so cloning needs access).
- **Windows:** run `install.ps1` in PowerShell; it runs `install.sh` inside WSL Ubuntu. `install.exe` is not in the repo; build it locally with `makensis install.nsi` (NSIS offline installer, bundles the local repository during build). `install.ps1` and `install.exe` are tested on Windows (WSL UNC and `C:\` paths). Defender may quarantine `install.exe`, so the supported path stays `git clone` plus `bash install.sh`.

## Architecture

```text
Browser :8080 -> backend/api.py -> backend/engine.py
                      |                   |
                      |            +------+------+
                      |            |             |
                      v            v             v
                  meta.json   sudo -n        sudo -n
                              build_helper   run_container.sh
                                   |             |
                                   |         C Engine
                                   v             v
                       /var/lib/vcontainer/  namespaces/cgroups/overlay
```

## Layout

```text
backend/    api.py, engine.py, core.py, live.py
  runtime/  C engine and Bash scripts (deployed to /usr/local/libexec/vcontainer)
  samples/  blog, runner, blogdrop
  tests/    unit, REST and integration tests
gui/        dashboard (HTML/CSS/JS)
docs/       architecture, API, test cases
windows/    machine/ and scripts/ helpers
root        install.sh, start.sh, install.ps1, install.nsi, var/ (runtime state)
```

Runtime changes are logged in `CHANGE.md`.

## Usage & API

Containers and images can be managed via the Web Dashboard (`http://localhost:8080`) or direct REST API calls:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Capabilities and runtime health |
| GET | `/system` | Host CPU times, load and memory (read from `/proc`, no sudo) |
| GET | `/images` | List cached and built image metadata |
| POST | `/images/build` | Build image from Vcfile: `{"file":"backend/samples/blog/Vcfile","clean":false,"update":false}` |
| POST | `/images/{name}/upload` | Import an image from a `.tar` sent as the request body |
| GET | `/images/{name}/download` | Download an image as a `.tar` |
| DELETE | `/images/{name}` | Remove an image |
| GET | `/containers` | List container records (status `running` or `stopped`) |
| POST | `/containers` | Create/run container: `{"name":"demo","image":"alpine","memory":"250M"}`; `memory` is REQUIRED. Optional arrays: `command`, `volumes`, `env`, `ports`. Optional fields: `cpus`, `pids`, `network`, `ip` |
| GET | `/containers/{name}` | Container details |
| POST | `/containers/{name}` | Start a stopped container (its limits are kept) |
| POST | `/containers/{name}/stop` | Stop a running container |
| DELETE | `/containers/{name}` | Stop if running, then remove state and mounts |
| GET | `/containers/{name}/stats` | Live memory and PID usage with their limits, plus the CPU limit (no CPU usage) |
| GET | `/containers/{name}/logs` | Fetch container stdout/stderr |
| POST | `/containers/{name}/exec` | Run a command in a running container (honors its limits) |

Sample apps (sources in `backend/samples/`):
- **Blog:** Python 3 + SQLite (`http://localhost:8081`)
- **Runner:** Multi-language test runner supporting Python, Node, and C (`http://localhost:8082`)
- **BlogDrop:** multi-user blog run as 4 containers (mysql db, Node/Express backend, static frontend, nginx gateway). Launch it with the dashboard's Launch BlogDrop button, wait about 30 s, then open `http://localhost:8085`. The admin is the account whose email matches `ADMIN_EMAIL`.

Start them from Quick start on Home. Extra instances get `-2`, `-3` names and host ports +100 (8181, 8182, ...).

## Dashboard

Vanilla HTML/CSS/JS in `gui/`, no CDN, works offline. Dark theme with a light toggle (saved in the browser).

- **Home:** counts, host gauges (CPU, memory, process IDs, container memory), Quick start buttons, and two-per-row container cards with usage bars, an Open button and Details / Stop / Delete.
- **Container detail** (`#/containers/<name>`): console (exec), logs, details and live memory/PID stats.
- **Containers and Images:** tables. Images has Upload .tar, Download and Build from Vcfile (with `--clean` and `--update` checkboxes).
- **Offline:** if the backend stops, the boxes stay and show an offline state.

## Security Model

- **Least Privilege:** The Python API server runs as an unprivileged user bound exclusively to `127.0.0.1`.
- **Strict Sudoers Scope:** Privilege escalation is locked down in `/etc/sudoers.d/vcontainer` to two root-owned scripts in `/usr/local/libexec/vcontainer/`. Edits to `backend/runtime/*.sh` take effect only after `sudo install -o root -g root -m 755 backend/runtime/<file> /usr/local/libexec/vcontainer/<file>`:
  1. `backend/runtime/run_container.sh`: Executes isolation primitives (namespaces, cgroup creation, overlay mount).
  2. `backend/runtime/build_helper.sh`: Constrained wrapper for build tasks (`tar`, `install`, `cp`, `chroot`, safe path-checked `rm`).
- **Isolation Layers:** Containers utilize PID, Mount, UTS, IPC, Network, and User namespaces, cgroup v2 limits (memory with swap disabled, pids, cpu), and overlayfs isolation.
- **Seccomp (on by default):** `run_container.sh` passes `--seccomp`, so containers get a deny-list filter (mount, umount2, pivot_root, reboot, init/finit/delete_module, ptrace, unshare, setns) and `no_new_privs`. Checked by running `unshare` inside a container: it is blocked.
- **Known limits:** per-container CPU usage is not exposed (only the limit), so the dashboard CPU gauge is host-wide. Capability dropping beyond `no_new_privs` is not claimed.

## Verification & Testing

Core functionality and isolation checks are documented in `docs/vcontainer_6_test_cases.md`.

To run non-root unit tests:
```bash
python3 -m unittest discover -s backend/tests -p 'test_*.py'
```

To run the six REST cases (the server must be running; takes about a minute):
```bash
bash backend/tests/rest_cases.sh
```

Expected: `RESULT 6/6 passed`.

To check prerequisites and run the root integration checks (`integration.sh` needs root or passwordless sudo):
```bash
bash backend/tests/verify.sh
bash backend/tests/integration.sh
```
