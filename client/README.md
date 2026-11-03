# Vcontainer client

This project contains the Windows CLI and PyWebView desktop application. Both
use the FastAPI service in WSL and fall back to the installed Linux wrapper for
commands that are not exposed through HTTP.

## Prerequisites

- Ubuntu on WSL 2, with cgroup v2 and OverlayFS available.
- A normal Linux user with sudo access and subordinate UID/GID ranges.
  The default launcher user is `vcdev`.
- Inside Ubuntu, install:

```bash
sudo apt update
sudo apt install -y build-essential libseccomp-dev skopeo umoci iproute2 iptables util-linux
```

Check the user's ranges with `grep '^vcdev:' /etc/subuid /etc/subgid`.
The engine requires the configured user's subordinate ranges. The Windows launcher supplies that user through SUDO_USER while running the engine as WSL root.

## From Windows PowerShell

Open PowerShell in this directory and run:

```powershell
uv run vcontainer list
uv run vcontainer run alpine --name windows-smoke -- /bin/echo "Hello from Windows"
uv run vcontainer inspect windows-smoke
```

Run `python setup.py` from the repository root first. Setup installs the engine
and helpers under `/opt/vcontainer`; commands never compile the engine on
launch.
The Windows launcher enters WSL as root and sets `SUDO_USER` to the configured
normal user for UID/GID mapping. This CLI has root privileges in the selected
distribution. The API uses separate restricted sudo helpers for reads and container controls.

Warm launcher timings measured locally fell from approximately 534 ms to
251 ms for help and from 587 ms to 259 ms for image listing (three samples
per command, median). These are launcher measurements, not container-start
benchmarks. The first invocation in the optimized test took about 4.2 seconds;
WSL startup overhead is still present. A persistent backend is the next step
for eliminating repeated WSL process launches from GUI requests.

To select another installation or user:

```powershell
$env:VCONTAINER_WSL_DISTRO = 'Ubuntu'
$env:VCONTAINER_WSL_USER = 'vcdev'
```

If PowerShell blocks the script, a policy change for the current session only is:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## From Ubuntu

Run `/opt/vcontainer/bin/vcontainer-cli ...` as the normal user. The setup
process installs this wrapper and the C engine into WSL.

## Lifecycle and volumes

```powershell
uv run vcontainer run alpine --name background --detach -- /bin/sh -c "echo started; sleep 300"
uv run vcontainer ps
uv run vcontainer logs background
uv run vcontainer exec background -- /bin/echo "Exec works"
uv run vcontainer stop background
uv run vcontainer start background
uv run vcontainer stop background
uv run vcontainer rm background

uv run vcontainer volume create app-data
uv run vcontainer run alpine --name volume-test --volume app-data:/data -- /bin/sh -c "echo persisted > /data/example.txt"
```

Named volume data and container metadata live under `/var/lib/vcontainer` in
Ubuntu. Images live under `/var/lib/vcontainer/images` and OCI downloads under
`/var/lib/vcontainer/oci`. Setup copies legacy temporary images into these stores
when the persistent destination is absent; it leaves the originals intact.

`start NAME` is implemented in the C engine. It reads `launch.argv`, restores
the original options and command, and reuses the existing writable filesystem.
The saved `--detach` option determines whether it starts in the background.
Only containers created with launch-state saving support can be started this
way; older containers report missing launch state. An existing cgroup must be
stopped and cleaned up with `stop NAME` before starting. Starting launches a new
process; it does not restore the previous process's memory. Python forwards the
command without implementing restart logic itself.

Bridge networking is optional: add `--network bridge --ip 10.88.0.2` before
the command separator. Windows access to container services is not configured
by this wrapper; published ports remain future work.

## WSL changes

- Management commands execute locally in WSL instead of using Lima.
- Arguments after `--` are preserved as container command arguments.
- Image and container names reject `.` and `..` in management paths.
- Shell validation runs inside the rootfs, supporting Alpine's absolute symlink.
- The child closes the inherited synchronization pipe write end.
- The child creates its cgroup namespace after parent attachment.

Detached startup waits for successful exec before printing a started message.
This confirms executable launch, not application health or service readiness.
`stop NAME` kills the entire cgroup and waits up to five seconds for removal;
it does not accept an extra PID. `ps` shows saved stopped containers as well as
running containers, with host PIDs and the saved command. Multiple PIDs represent
the main process and its child processes. The runtime remains experimental.
