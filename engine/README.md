# Vcontainer for Windows with WSL 2

The PowerShell launcher runs the Linux C engine inside WSL 2. This directory
contains its own sources and helpers. Generated ARM binaries are not included.

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
The current engine expects execution through sudo by that normal user.

## From Windows PowerShell

Open PowerShell in this directory and run:

```powershell
.\vcontainer.ps1 list
.\vcontainer.ps1 run alpine --name windows-smoke -- /bin/echo "Hello from Windows"
.\vcontainer.ps1 inspect windows-smoke
```

The launcher converts its adjacent Bash script's Windows path using `wslpath`.
No separate Ubuntu source copy is required. The Bash wrapper stages sources and
helpers in `/tmp/vcontainer-work`, compiles there, and runs through sudo.
Enter the Linux user's password when prompted.

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

Run `bash /path/to/Vcontainer\(win\)/run_container.sh ...` as the normal user.
The script resolves its own source directory; do not run the Lima wrapper.

## Lifecycle and volumes

```powershell
.\vcontainer.ps1 run alpine --name background --detach -- /bin/sh -c "echo started; sleep 300"
.\vcontainer.ps1 ps
.\vcontainer.ps1 logs background
.\vcontainer.ps1 exec background -- /bin/echo "Exec works"
.\vcontainer.ps1 stop background
.\vcontainer.ps1 rm background

.\vcontainer.ps1 volume create app-data
.\vcontainer.ps1 run alpine --name volume-test --volume app-data:/data -- /bin/sh -c "echo persisted > /data/example.txt"
```

Named volume data and container metadata live under `/var/lib/vcontainer` in
Ubuntu. Images live under `/tmp/vcontainer-images` and OCI downloads under
`/tmp/vcontainer-oci`; these temporary stores may be cleared by Linux.

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

This remains an experimental runtime. Detached startup does not yet confirm
successful command execution to the parent. Validate lifecycle and networking
in WSL before relying on them.
