# Architecture overview

The Windows CLI and preserved Parizval dashboard call the FastAPI service in
`backend/api`. The service runs as the unprivileged `vcdev` user in WSL. It
uses four narrowly scoped, root-owned helpers in `backend/helpers`; container
isolation itself is implemented by the C runtime in `backend/runtime`.

## Request path

Browser or CLI -> `localhost:8010` -> FastAPI -> restricted helper -> C engine
-> Linux namespaces, cgroups v2, overlayfs, networking, and seccomp.

## Lifecycle

1. Pull stores persistent image root filesystems under `/var/lib/vcontainer/images`.
2. Run creates namespaces, overlay mounts, cgroups, networking, and saved launch state.
3. Observe reads state, logs, processes, network counters, and cgroup metrics.
4. Stop preserves metadata so the saved command can be started again.
5. Remove stops a running container before deleting its state.

## Dashboard

The unchanged Parizval HTML, CSS, and JavaScript live in `gui/`. Installation
copies those assets beside the API and sets `VCONTAINER_GUI_DIR`, so `/` serves
the same dashboard from WSL and from the desktop shell.

## Host stats

`GET /system/live` reads `/proc` and cgroup counters without sudo. Container
detail routes expose CPU, memory, processes, network traffic, block I/O, logs,
mounts, limits, and saved commands.

## Privilege model

- The API binds to `127.0.0.1:8010` and runs without root privileges.
- Sudoers grants access only to the installed read, control, image, and volume helpers.
- The C runtime supplies PID, mount, UTS, IPC, network, and user namespaces,
  cgroup v2 resource control, overlayfs, bridge networking, and seccomp.
