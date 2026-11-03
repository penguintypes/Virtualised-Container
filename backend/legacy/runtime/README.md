# vContainer runtime

The C and Bash engine behind vContainer. It creates the namespaces, cgroup v2 limits, overlayfs mounts, bridge networking and seccomp filter for each container. The Python API in `backend/` drives it through `sudo -n`.

## Prerequisites

- Ubuntu on WSL2 (or Linux) with cgroup v2 and OverlayFS.
- A normal user with sudo and subordinate UID/GID ranges.
- Packages: `build-essential libseccomp-dev skopeo umoci iproute2 iptables util-linux python3 curl socat` (installed by `install.sh`).

## Layout

- `run_container.sh`: entry point called by `backend/engine.py`.
- `build_helper.sh`: constrained wrapper for image build tasks; sources must be under `/var/lib/vcontainer/`.
- `src/`: C sources and helper scripts (`cgroup.sh`, `image.sh`, `network.sh`).
- `include/`: shared headers.
- `tests/`: C test programs.
- `examples/`: runnable examples.
- `build/`: generated binaries, not tracked in git.
- `vcontainer.ps1`, `vcontainer.py`: optional Windows launchers that forward arguments to `run_container.sh` inside WSL (`VCONTAINER_WSL_DISTRO`, `VCONTAINER_WSL_USER`).

## Build and deploy

`install.sh` compiles the engine with `make` and installs the scripts root-owned into `/usr/local/libexec/vcontainer/`. The deployed copies are the ones that run, so after editing a script run:

```bash
sudo install -o root -g root -m 755 backend/runtime/<file> /usr/local/libexec/vcontainer/<file>
```

## Storage and networking

- Images: `/var/lib/vcontainer/images/<name>`; containers: `/var/lib/vcontainer/containers/<name>`.
- Named volumes: `/var/lib/vcontainer/volumes/<name>/_data`.
- Bridge `vcbr0` on `10.88.0.1/24`; published ports are forwarded to the container IP with `socat`.
- Seccomp is on by default.
