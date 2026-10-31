# vContainer

vContainer is a Docker-like container runtime for WSL2 Ubuntu (tested on 26.04). A C and Bash engine handles namespaces, cgroups v2, overlayfs, bridge networking and process lifecycle. A Python REST API, a web dashboard, a Vcfile image builder and three sample apps sit on top of it.

## Quick Start

```bash
bash install.sh
./start.sh
```

- **Dashboard:** `http://localhost:8080`
- **Start:** `./start.sh` launches only the dashboard. Start the sample containers from Quick start on Home, or launch the complete BlogDrop stack with the Launch BlogDrop button.
- **Install (WSL2 Ubuntu or Linux):** `git clone -b parzivalSr-test https://github.com/penguintypes/Virtualised-Container.git && cd Virtualised-Container && bash install.sh` (the repo is private for now, so cloning needs access).
- **Windows:** run `install.ps1` in PowerShell; it runs `install.sh` inside WSL Ubuntu. `install.exe` is not in the repo; build it locally with `makensis install.nsi` (NSIS offline installer, bundles the local repository during build). Defender may quarantine `install.exe`, so the supported path stays `git clone` plus `bash install.sh`.

## Features

- Isolation with PID, mount, UTS, IPC, network and user namespaces.
- Memory, CPU and PID limits through cgroup v2 (memory swap disabled so limits are enforced).
- Overlayfs images built from a Vcfile (`FROM`, `RUN`, `COPY`, `CMD`), with `--clean` and `--update` build options.
- Bridge networking (`vcbr0`, `10.88.0.1/24`) with host port publishing.
- Named volumes, image upload and download, container logs and exec.
- Seccomp filter on by default.
- Web dashboard with live host and container graphs, light and dark themes.

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
docs/       architecture overview and test cases
windows/    machine/ and scripts/ helpers
root        install.sh, start.sh, install.ps1, install.nsi, var/ (runtime state)
```

Changes are logged in `CHANGE.md`.

## Dashboard

Vanilla HTML, CSS and JS in `gui/`, no CDN, works offline.

- **Home:** four number tiles (Running, Stopped, Images, Disk), four live graphs (CPU and memory, host and containers) that turn orange and then red as usage rises, Quick start buttons (Run Blog, Run Runner, Launch BlogDrop) and container cards, three per row.
- **Container details:** console (exec), logs, live memory and PID stats, and Stop / Start / Delete buttons.
- **Containers, Images and Volumes:** tables. Images has Upload .tar, Download and Build from Vcfile.
- **Top bar:** Run Container, Kill all containers and Kill server.
- **Offline:** if the backend stops, the dashboard stays up and shows an offline state.

## Sample Apps

Sources are in `backend/samples/`.

- **Blog:** Python 3 + SQLite.
- **Runner:** multi-language test runner for Python, Node and C.
- **BlogDrop:** a multi-user blog run as four containers (MySQL, Node/Express backend, static frontend, nginx gateway). Launch it from the dashboard, wait about 30 seconds, then open `http://localhost:8085`. The admin is the account whose email matches `ADMIN_EMAIL`.

Blog and Runner start from Quick start on Home. Each click creates a new container (for example `blog-x7k2`) on the first free host port from 8081 upward.

## REST API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Capabilities and runtime health |
| GET | `/system` | Host CPU times, load and memory (read from `/proc`, no sudo) |
| GET | `/system/live` | Live usage sample for the dashboard graphs |
| GET | `/system/disk` | Disk usage of the image and volume stores |
| GET | `/images` | List cached and built image metadata |
| POST | `/images/build` | Build an image from a Vcfile: `{"file":"backend/samples/blog/Vcfile","clean":false,"update":false}` |
| POST | `/images/pull` | Pull an image from a registry |
| POST | `/images/{name}/upload` | Import an image from a `.tar` sent as the request body |
| GET | `/images/{name}/download` | Download an image as a `.tar` |
| DELETE | `/images/{name}` | Remove an image |
| GET | `/volumes` | List named volumes |
| GET | `/containers` | List container records (status `running` or `stopped`) |
| POST | `/containers` | Create and run a container: `{"name":"demo","image":"alpine","memory":"250M"}`. `memory` is required. Optional arrays: `command`, `volumes`, `env`, `ports`. Optional fields: `cpus`, `pids`, `network`, `ip` |
| GET | `/containers/{name}` | Container details |
| POST | `/containers/{name}` | Start a stopped container (its limits are kept) |
| POST | `/containers/{name}/stop` | Stop a running container |
| DELETE | `/containers/{name}` | Stop if running, then remove state and mounts |
| GET | `/containers/{name}/stats` | Live memory and PID usage with their limits, plus the CPU limit |
| GET | `/containers/{name}/metrics` | Metrics for the dashboard graphs (zeroed if the container is stopping) |
| GET | `/containers/{name}/logs` | Container stdout and stderr |
| POST | `/containers/{name}/exec` | Run a command in a running container (honors its limits) |
| POST | `/killserver` | Stop the API server |

## Security Model

- **Least privilege:** the Python API runs as an unprivileged user bound to `127.0.0.1`.
- **Strict sudoers scope:** `/etc/sudoers.d/vcontainer` allows only two root-owned scripts in `/usr/local/libexec/vcontainer/`: `run_container.sh` (namespaces, cgroups, overlay mounts) and `build_helper.sh` (a constrained wrapper for build tasks with path-checked `rm`). After editing `backend/runtime/*.sh`, redeploy with `sudo install -o root -g root -m 755 backend/runtime/<file> /usr/local/libexec/vcontainer/<file>`.
- **Isolation layers:** PID, mount, UTS, IPC, network and user namespaces, cgroup v2 limits and overlayfs.
- **Seccomp (on by default):** a deny-list filter blocks mount, umount2, pivot_root, reboot, init/finit/delete_module, ptrace, unshare and setns, and `no_new_privs` is set.
- **Known limits:** per-container CPU usage is not exposed (only the limit), so the dashboard CPU graph for the host is host-wide. Capability dropping beyond `no_new_privs` is not claimed.

## Testing

Core functionality and isolation checks are documented in `docs/vcontainer_6_test_cases.md`.

Unit tests (no root needed):

```bash
python3 -m unittest discover -s backend/tests -p 'test_*.py'
```

The six REST cases (the server must be running; takes about a minute). Expected result: `RESULT 6/6 passed`.

```bash
bash backend/tests/rest_cases.sh
```

Prerequisite and root integration checks (`integration.sh` needs root or passwordless sudo):

```bash
bash backend/tests/verify.sh
bash backend/tests/integration.sh
```
