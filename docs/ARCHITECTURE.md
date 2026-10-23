# Architecture

`backend/core.py` owns state and lifecycle. `backend/cli.py` and `backend/api.py` are thin adapters over those same functions, so behavior stays consistent. The GUI is static content served by the API.

## Lifecycle

1. `create_image` creates an image directory and metadata entry.
2. `create_container` copies an image rootfs to a container directory and records config.
3. `start` starts the command with Linux namespace flags where permitted and captures logs.
4. `stats` reads `/proc` and reports whether cgroup limits are enforceable.
5. `stop`, `kill`, `delete`, and `exec` operate on the same state record.

## Privilege model

Namespace creation is attempted with `os.unshare`. cgroup, network, mount, and security hardening are capability-gated rather than silently faked. A privileged deployment should add a dedicated cgroup subtree under `/sys/fs/cgroup`, configure a bridge/veth pair, and apply seccomp/no-new-privs before exec.
