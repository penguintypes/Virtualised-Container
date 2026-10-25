# vcontainer merged project

A student-sized Docker-like container runtime for WSL2 Ubuntu (tested on 26.04). The C and Bash engine in `engine/` handles namespaces, cgroups v2, overlayfs, virtual networking, and process lifecycle. The Python adapter, REST API, dashboard, Vcfile parser, samples, and integration tests provide management and visibility.

## Quick Start

```bash
bash install.sh
./start.sh
```

- **Dashboard:** `http://localhost:8080`
- **Install (WSL2 Ubuntu or Linux):** `git clone -b parzivalSr-test https://github.com/penguintypes/Virtualised-Container.git && cd Virtualised-Container && bash install.sh` (the repo is private for now, so cloning needs access).
- **Windows:** run `install.ps1` in PowerShell; it runs `install.sh` inside WSL Ubuntu. `install.exe` is not in the repo; build it locally with `makensis install.nsi` (NSIS web installer, downloads the source at install time).

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

`engine-arm/` is retained as an unmerged ARM reference. Custom runtime adaptations are documented in `patches/`.

## Usage & API

Containers and images can be managed via the Web Dashboard (`http://localhost:8080`) or direct REST API calls:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Capabilities and runtime health |
| GET | `/images` | List cached and built image metadata |
| POST | `/images/build` | Build image from Vcfile: `{"file":"samples/blog/Vcfile"}` |
| DELETE | `/images/{name}` | Remove an image |
| GET | `/containers` | List active and exited container records |
| POST | `/containers` | Create/run container: `{"name":"demo","image":"alpine","command":"..."}` |
| POST | `/containers/{name}/stop` | Stop a running container |
| DELETE | `/containers/{name}` | Remove container state and mounts |
| GET | `/containers/{name}/stats` | Live cgroup v2 CPU and memory statistics |
| GET | `/containers/{name}/logs` | Fetch container stdout/stderr |
| POST | `/containers/{name}/exec` | Execute command in existing container |

Sample containers:
- **Blog:** Python 3 + SQLite (`http://localhost:8081`)
- **Runner:** Multi-language test runner supporting Python, Node, and C (`http://localhost:8082`)

## Security Model

- **Least Privilege:** The Python API server runs as an unprivileged user bound exclusively to `127.0.0.1`.
- **Strict Sudoers Scope:** Privilege escalation is locked down in `/etc/sudoers.d/vcontainer` to two root-owned scripts in `/usr/local/libexec/vcontainer/`. Edits to `engine/*.sh` take effect only after `sudo install -o root -g root -m 755 engine/<file> /usr/local/libexec/vcontainer/<file>`:
  1. `engine/run_container.sh`: Executes isolation primitives (namespaces, cgroup creation, overlay mount).
  2. `engine/build_helper.sh`: Constrained wrapper for build tasks (`tar`, `install`, `cp`, `chroot`, safe path-checked `rm`).
- **Isolation Layers:** Containers utilize PID, Mount, UTS, IPC, Network, and User namespaces, cgroup v2 limits (memory with swap disabled, pids, cpu), and overlayfs isolation.

## Verification & Testing

Core functionality and isolation checks are documented in `vcontainer_6_test_cases.md`.

To run non-root unit tests:
```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

To run end-to-end integration checks:
```bash
bash verify.sh
bash tests/integration.sh
```
