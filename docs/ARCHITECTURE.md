# Architecture

`backend/engine.py` owns state and lifecycle, delegating to the `run_container.sh` Bash engine. `backend/core.py` parses Vcfiles. `backend/api.py` is the REST adapter over the engine and serves the static dashboard in `gui/`.

## Request path

Browser :8080 -> `backend/api.py` -> `backend/engine.py` -> `sudo -n` -> `run_container.sh` / `build_helper.sh` (root-owned in `/usr/local/libexec/vcontainer/`) -> C engine (namespaces, cgroups v2, overlayfs, seccomp).

## Lifecycle

1. Build: `POST /images/build` parses the Vcfile (`core.py`) and builds the rootfs through `build_helper.sh` under `/var/lib/vcontainer/images/<name>`. Images can also be uploaded or downloaded as `.tar`.
2. Run: `POST /containers` calls `run_container.sh` with the image, command, limits and optional port. The engine sets up the namespaces, a cgroup under `/sys/fs/cgroup/vcontainer/<name>`, the overlay mount and, with a port, a socat forwarder. Limits are saved in `var/engine.json`, so a restart keeps them.
3. Observe: logs and stats come from the container state directory and its cgroup (memory, PIDs, CPU limit).
4. Stop and delete: stop ends the container; delete stops it first, then removes state and mounts.
5. Exec: the command joins the container's namespaces and cgroup, so it honors the same limits.

## Dashboard

Vanilla HTML/CSS/JS, no CDN, works offline. Hash routes: `#/home`, `#/containers`, `#/containers/<id>`, `#/images`. Poll intervals: host gauges 3 s, health 10 s, detail stats 2 s, detail logs 4 s, container list 5 s. The theme is stored in the browser (`vc-theme`).

## Host stats

`GET /system` reads `/proc/meminfo`, `/proc/stat` and the load average, without sudo. The dashboard computes CPU % from two `/proc/stat` samples: `100 * (1 - dIdle / dTotal)`. The API exposes only a container's CPU limit, not its usage, so the CPU gauge is host-wide.

## Privilege model

- The API runs unprivileged and binds to `127.0.0.1`. Sudoers allows only `run_container.sh` and `build_helper.sh`, installed root-owned in `/usr/local/libexec/vcontainer/`.
- Isolation: PID, mount, UTS, IPC, network and user namespaces; cgroup v2 limits for memory (swap disabled), PIDs and CPU; overlayfs; bridge `vcbr0` (10.88.0.1/24) with veth pairs.
- Seccomp is on by default: `--seccomp` is passed in the final run call. It blocks mount, umount2, pivot_root, reboot, init_module, finit_module, delete_module, ptrace, unshare and setns, and sets `no_new_privs`.
- Capability dropping beyond `no_new_privs` is not claimed.
