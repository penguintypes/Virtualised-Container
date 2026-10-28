# Vcontainer architecture

Vcontainer separates the Windows interface from the Linux runtime. Windows owns
the user-facing commands and desktop window. WSL owns the API, privileged helper
programs, container state, and C engine.

## Components

```text
Windows
  vcontainer.py / vcontainer.ps1
           │
           ├──────── HTTP 127.0.0.1:8010 ────────┐
           │                                      │
  PyWebView desktop                               │
           │                                      ▼
           └────────────────────────── FastAPI service
                                                  │
                                       restricted sudo helpers
                                                  │
                                       Linux wrapper and C engine
                                                  │
                        namespaces, cgroups, mounts, seccomp, veth
```

### Windows client

`Vcontainer(win)/src/vcontainer_cli` contains the Python client. It handles CLI
arguments, API requests, Compose normalization, service ordering, and WSL
fallback commands. `Vcontainer(win)/vcontainer.py` is a compatibility launcher,
so existing commands do not depend on the package's internal location.

The desktop package is in `Vcontainer(win)/src/vcontainer_desktop`. PyWebView
opens the web interface in a native window. It starts the same backend used by
the command-line client and does not maintain separate container state.

### HTTP service

The FastAPI package is in `api/src/vcontainer_api` and runs inside WSL as
`vcontainer-api.service`.

```text
main.py              application construction and static UI mount
lifecycle.py         startup reconciliation
schemas.py           request validation models
errors.py            runtime error types
supervisor.py        detached launch tracking and bridge IP reservations
routers/             HTTP endpoints grouped by resource
services/runtime.py  WSL helper and subprocess calls
services/metrics.py  cgroup metric normalization and CPU sampling
services/streaming.py server-sent event encoding
```

The service runs as the normal WSL user. Operations that need root access pass
through a small set of commands installed in `/usr/local/sbin`.

### Privileged helpers

The helper source is kept in `helper/vcontainer-helper`. Setup installs the
helpers and creates narrow sudo rules for their exact paths. The API cannot send
an arbitrary shell command through these helpers. Each helper accepts a fixed
action set and validates resource names and arguments before calling the Linux
wrapper.

The installed helpers cover read operations, container control, image control,
volume control, port publishing, and metadata recording.

### C engine

The C source and Linux wrapper are under `Vcontainer(win)/engine`.

The engine creates:

- user, mount, PID, UTS, IPC, and network namespaces
- cgroups v2 limits and accounting
- OverlayFS mounts for container writable layers
- a pivoted container root filesystem
- seccomp filters
- bridge and veth networking when requested

The engine is daemonless. A container is a Linux process placed in the selected
namespaces and cgroup. The FastAPI service is a management process, not a parent
daemon that must remain alive for every container.

## Request flows

### Create a container

```text
CLI or GUI
  │ POST /containers
  ▼
containers router
  │ validates the request and reserves an address when needed
  ▼
supervisor
  │ starts the runtime and waits for the container state to appear
  ▼
restricted helper
  │ converts validated fields into Linux wrapper arguments
  ▼
C engine
  │ creates isolation, mounts, cgroups, and the child process
  ▼
/var/lib/vcontainer/containers/NAME
```

The API returns `202 Accepted` while the supervisor checks startup. Immediate
launch failures are returned to the client. For detached containers, the
supervisor records start and exit metadata and restores published ports after an
API restart.

### Read state and metrics

```text
CLI or GUI
  │ GET /containers, /metrics, /processes, or /logs
  ▼
FastAPI router
  ▼
vcontainer-read
  ├── /sys/fs/cgroup/vcontainer
  ├── /proc
  └── /var/lib/vcontainer
```

Read requests use a dedicated helper instead of the general control path. Live
logs and metrics use server-sent events. Disconnecting a browser cancels its
stream loop without stopping the container.

### Stop and remove

`stop` signals every process in the container cgroup and waits for it to empty.
The metadata and writable layer remain, so `start` can use the saved launch
arguments. `rm` first stops a running container, waits for the supervisor, and
then removes the stopped container's state. Named volumes are separate and are
not removed with a container.

### Pull an image

```text
POST /images/pull
  ▼
vcontainer-image-control
  ▼
Skopeo copies the image to OCI storage
  ▼
Umoci unpacks the image root filesystem
  ▼
/var/lib/vcontainer/images/LOCAL_NAME
```

The local name is independent of the registry reference. Pulling
`docker.io/library/nginx:latest` as `nginx` lets subsequent run commands use the
short local name.

## Storage

Persistent runtime data stays in WSL rather than `/tmp`:

```text
/opt/vcontainer/bin/vcontainer             installed C engine
/opt/vcontainer/bin/vcontainer-cli         installed Linux wrapper
/opt/vcontainer/libexec/                    engine shell helpers
/usr/local/sbin/vcontainer-*                restricted API helpers
/var/lib/vcontainer/images/                 unpacked image root filesystems
/var/lib/vcontainer/containers/             container state and writable layers
/var/lib/vcontainer/volumes/                named volumes
/var/lib/vcontainer/oci/                    temporary OCI image data
/home/vcdev/vcontainer-api/                 installed API source and environment
/sys/fs/cgroup/vcontainer/                  live container cgroups
```

A container state directory can hold the saved command, launch arguments, PID,
timestamps, logs, network settings, port mappings, resource limits, and
OverlayFS directories. A stopped container has metadata but no process in its
cgroup.

## Networking

Bridge containers use the `10.88.0.0/24` network. The API reserves addresses
during launch to prevent two concurrent requests from selecting the same IP.
The Linux networking helper creates the veth pair, assigns the address and
default route, and configures forwarding.

Published ports are forwarded from Windows localhost to the container address.
Port metadata is stored with the container, which allows the API to restore the
forwarders after a service restart.

## Compose

The executable under `Vcontainer(win)/vendor/compose` uses Compose-Go to parse
and normalize YAML. It returns JSON to the Python client. The client then creates
named volumes, orders services by `depends_on`, and submits ordinary container
API requests. Compose does not introduce another runtime object. The resulting
services are normal Vcontainer containers grouped by project naming.

## Trust boundaries

- The API listens on `127.0.0.1`; it is not intended for network exposure.
- Pydantic models validate HTTP payloads before a runtime call.
- Resource names and mount targets receive additional validation at the API and
  helper layers.
- Passwordless sudo rules name individual installed helper paths.
- The helper action lists prevent arbitrary command execution as root.
- The C engine applies namespace isolation, cgroup limits, and seccomp inside
  the container.

These boundaries reduce accidental privilege exposure. They do not amount to a
complete security audit, and the project should still be treated as
experimental.

## Startup and lifetime

The Windows client checks `/health` before each API-backed command. If the API is
down, it starts `vcontainer-api.service` through WSL and waits for the health
response. A small WSL keepalive process prevents the distribution from shutting
down between closely spaced commands.

Starting the API does not start a container engine daemon. Containers continue
as Linux processes if the API restarts. WSL itself must remain running for those
processes to exist.

## Repository map

```text
setup.py                       Windows and WSL installation
setup_api_service.py           API/helper service deployment
api/                           WSL HTTP service project
helper/vcontainer-helper/      privileged helper project
Vcontainer(win)/
  pyproject.toml               unified Windows Python project
  src/vcontainer_cli/          CLI implementation
  src/vcontainer_desktop/      desktop launcher
  engine/                      C runtime
  machine/                     WSL machine work
  scripts/                     Windows launch scripts
  vendor/compose/              Compose-Go parser
docs/                          design and usage notes
tests/                         installation and end-to-end tests
```

## Known design limits

The runtime supports one bridge network and a practical subset of OCI images and
Compose. It does not implement Kubernetes pods, rootless containers, multiple
network drivers, registry authentication workflows, or the complete Docker and
Podman command surfaces. Those limits keep the current engine small enough to
study, but they also restrict compatibility.
