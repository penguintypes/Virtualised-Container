# vcontainer merged project

A student-sized Docker-like runtime for WSL2 Ubuntu 24.04. The friend’s C and Bash engine in `engine/` performs the real namespace, cgroup, overlay, network, and process work. The Python adapter, REST API, dashboard, Vcfile parser, samples, and tests are mine.

## Quick start

```bash
bash install.sh
./start.sh
```

Dashboard: `http://localhost:8080`. The curl form is `curl -fsSL https://raw.githubusercontent.com/<YOUR-USERNAME>/vcontainer-merged/main/install.sh | bash` (replace the placeholder URL with a trusted project URL). Windows users can run `install.ps1`; `install.exe` is built with `makensis install.nsi`. The unsigned executable can trigger SmartScreen.

## Architecture

```text
Browser :8080 -> backend/api.py -> backend/engine.py -> sudo -n engine/run_container.sh
                                      |                         |
                                   meta.json              friend C engine
                                      |              namespaces/cgroups/overlay
                              /var/lib/vcontainer/images
```

`Vcontainer(arm)` is retained untouched as a reference. Every friend-engine edit has a corresponding file in `patches/`.

## Usage

```bash
vc pull alpine
vc run alpine --name demo --detach -- echo hello
vc ps
vc logs demo
vc stop demo && vc rm demo
```

Build samples through the dashboard or API, then run them with `-p 8081:8081` and `-p 8082:8082`. Blog uses Python and SQLite. Runner supports Python, Node, and C; Java is intentionally omitted to reduce image size.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | capabilities |
| GET | `/images` | image metadata |
| POST | `/images/build` | `{"file":".../Vcfile"}` |
| DELETE | `/images/{name}` | delete image |
| GET | `/containers` | container records |
| POST | `/containers` | create detached container |
| POST | `/containers/{id}` | start |
| POST | `/containers/{id}/stop` | stop |
| DELETE | `/containers/{id}` | remove |
| GET | `/containers/{id}/stats` | live limits and usage |
| GET | `/containers/{id}/logs` | logs |
| POST | `/containers/{id}/exec` | `{"command":[...]}` |

Errors are JSON objects with `error` and `code`; CORS is enabled for the dashboard.

## Security model

The engine runs as a normal WSL user and uses narrowly scoped `sudo -n` calls. The optional sudoers rule is intended only for a personal development machine. Containers get user, mount, UTS, IPC, PID, and network namespaces, cgroup limits, an overlay root, optional seccomp, and a read-only API path is not exposed by this adapter. Do not run untrusted workloads with the optional broad development rule without reviewing it.

## Tests and verification

No rootful namespaces, cgroups, overlay mounts, iptables, or socat networking were run in this sandbox. They are **UNVERIFIED**, not planned. Run `python3 -m unittest discover -s tests -p 'test_*.py'` for no-root tests, then run `bash verify.sh` and `bash tests/integration.sh` inside WSL2 Ubuntu. The integration script checks isolation, limits, samples, port publishing, and CLI/API agreement.

The sandbox also lacks `libseccomp-dev`, so the final WSL build was not attempted successfully here; `install.sh` installs it before compiling. NSIS was unavailable, so `install.nsi` is delivered instead of a compiled `install.exe`; build it with `makensis install.nsi` on Windows.
