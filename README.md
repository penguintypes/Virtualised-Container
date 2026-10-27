# Vcontainer

Vcontainer is a lightweight, educational Linux container engine with a Windows
workflow powered by WSL 2. It combines a small C runtime with a Python CLI, a
FastAPI management service, and a browser GUI.

The runtime creates containers directly with Linux namespaces, cgroups v2,
OverlayFS, seccomp, virtual Ethernet devices, and pivot-root isolation. It does
not depend on Docker or Podman to run containers.

> Vcontainer is an experimental and educational project. It is not currently a
> production replacement for Docker, Podman, containerd, or Kubernetes.

## Goals

- Learn and demonstrate the Linux primitives behind containers.
- Provide a simple Windows experience through WSL 2.
- Keep the container execution engine small and daemonless.
- Support images, volumes, networking, limits, logs, metrics, and Compose.
- Expose the runtime through a CLI, HTTP API, and browser GUI.
- Remain understandable enough for students to inspect and extend.

## Features

- OCI/Docker image import using Skopeo and Umoci.
- PID, mount, UTS, IPC, network, and user namespace isolation.
- cgroups v2 CPU, memory, and process limits.
- OverlayFS writable layers and persistent container state.
- Seccomp syscall filtering.
- Bridge networking and TCP port publishing to Windows localhost.
- Named persistent volumes, environment variables, and custom commands.
- Start, stop, remove, logs, inspection, and process information.
- CPU, memory, process, network, block-I/O, and container disk metrics.
- Compose validation and lifecycle commands.
- FastAPI/OpenAPI management API and browser GUI.

## Requirements

- Windows 10 or Windows 11 with WSL 2.
- Ubuntu installed as a WSL 2 distribution.
- Windows Python 3.12 or newer.
- An internet connection during setup and image pulls.
- Hardware virtualization enabled.

Install Ubuntu when necessary:

```powershell
wsl --install -d Ubuntu
```

Confirm that it uses WSL 2:

```powershell
wsl --list --verbose
```

## Installation

Run the installer from this repository directory using Windows Python:

```powershell
python setup.py
```

The installer checks WSL and kernel features, prepares the `vcdev` Linux user,
installs build and image dependencies, builds the C engine, creates the Python
environment with `uv`, installs restricted helpers, starts the API service, and
runs verification tests.

Defaults:

```text
WSL distribution: Ubuntu
Linux user:        vcdev
API address:       http://127.0.0.1:8010
```

Override launcher settings when needed:

```powershell
$env:VCONTAINER_WSL_DISTRO = "Ubuntu"
$env:VCONTAINER_WSL_USER = "vcdev"
```

## Quick start

Commands below assume PowerShell is open in this repository directory.

```powershell
# Pull an image
python "Vcontainer(win)/vcontainer.py" pull alpine

# Run a foreground command
python "Vcontainer(win)/vcontainer.py" run alpine --name hello -- /bin/echo "Hello from Vcontainer"

# Run a web server and publish it to Windows
python "Vcontainer(win)/vcontainer.py" run nginx --name web -d -p 8080:80

# List images and containers
python "Vcontainer(win)/vcontainer.py" list
python "Vcontainer(win)/vcontainer.py" ps
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) for the Nginx example.

Pull a registry image under a local name:

```powershell
python "Vcontainer(win)/vcontainer.py" pull mint ghcr.io/mint-lang/mint:latest
```

## CLI commands

The Windows launcher is:

```powershell
python "Vcontainer(win)/vcontainer.py" COMMAND
```

### Images

```powershell
python "Vcontainer(win)/vcontainer.py" list
python "Vcontainer(win)/vcontainer.py" pull LOCAL_NAME [REMOTE_REFERENCE]
python "Vcontainer(win)/vcontainer.py" delete IMAGE
```

### Containers

```powershell
python "Vcontainer(win)/vcontainer.py" ps
python "Vcontainer(win)/vcontainer.py" inspect NAME
python "Vcontainer(win)/vcontainer.py" logs NAME
python "Vcontainer(win)/vcontainer.py" logs -f NAME
python "Vcontainer(win)/vcontainer.py" exec NAME -- /bin/sh
python "Vcontainer(win)/vcontainer.py" start NAME
python "Vcontainer(win)/vcontainer.py" stop NAME
python "Vcontainer(win)/vcontainer.py" rm NAME
```

### Run options

```text
--name NAME                    Required container name
-d, --detach                  Run in the background
--hostname NAME                Container hostname
--memory-max 512M              Memory limit
--pids-max 128                 Process limit
--cpu-max QUOTA PERIOD         CPU quota and period
--network bridge               Attach to the Vcontainer bridge
--ip 10.88.0.20                Static bridge address
-p, --publish 8080:80          Publish a TCP port
-v, --volume NAME:/TARGET      Mount a named volume
-e, --env NAME=VALUE           Set an environment variable
-- COMMAND [ARGS...]           Override the image command
```

Example with limits and environment:

```powershell
python "Vcontainer(win)/vcontainer.py" run alpine `
  --name worker `
  --memory-max 256M `
  --pids-max 64 `
  --cpu-max 50000 100000 `
  -e MODE=development `
  -- /bin/sleep 300
```

When a published port is requested without explicit networking, the API allocates
a bridge address automatically.

## Persistent volumes

```powershell
python "Vcontainer(win)/vcontainer.py" volume create app-data
python "Vcontainer(win)/vcontainer.py" volume list
python "Vcontainer(win)/vcontainer.py" volume inspect app-data
```

Mount it inside a container:

```powershell
python "Vcontainer(win)/vcontainer.py" run alpine `
  --name volume-demo `
  -d `
  -v app-data:/data `
  -- /bin/sleep 300
```

Data written to `/data` remains after the container is stopped or removed. Volume
removal is rejected while the volume is in use or non-empty.

```powershell
python "Vcontainer(win)/vcontainer.py" volume remove app-data
```

## Compose

Vcontainer uses its bundled Compose-Go executable to validate and normalize YAML.
The supported subset includes images, commands, environment variables, named
volumes, published TCP ports, dependencies, and static bridge addresses.

```powershell
$config = "C:\path\to\config.yaml"

python "Vcontainer(win)/vcontainer.py" compose config $config
python "Vcontainer(win)/vcontainer.py" compose up $config
python "Vcontainer(win)/vcontainer.py" compose ps $config
python "Vcontainer(win)/vcontainer.py" compose stop $config
python "Vcontainer(win)/vcontainer.py" compose start $config
python "Vcontainer(win)/vcontainer.py" compose down $config
```

- `up` creates missing containers and starts stopped containers.
- `stop` stops services in reverse dependency order and preserves metadata.
- `start` starts existing services in dependency order.
- `down` removes project containers but preserves named volumes.
- `ps` groups service names, container names, and current states.

`compose up` is idempotent: it leaves running containers alone, starts matching
stopped containers, and creates only missing containers.

## Browser GUI

After installation, open:

- GUI: [http://127.0.0.1:8010](http://127.0.0.1:8010)
- API documentation: [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)

The GUI supports container lifecycle and resource controls, images, named volumes,
persistent volume attachments, logs, process information, metrics, published-port
links, container-only disk usage, and light/dark themes.

## Architecture

```text
Windows
├── vcontainer.py                 CLI and Compose workflow
└── Browser GUI                   Management interface
        │
        │ HTTP on 127.0.0.1:8010
        ▼
WSL 2 / Ubuntu
├── vcontainer-api.service        FastAPI management service (vcdev)
│   └── restricted sudo helpers   Validated privileged operations
│
├── /opt/vcontainer/bin/
│   ├── vcontainer                C container runtime
│   └── vcontainer-cli            Linux command wrapper
│
├── Linux isolation
│   ├── namespaces
│   ├── cgroups v2
│   ├── OverlayFS
│   ├── seccomp
│   └── bridge/veth networking
│
└── /var/lib/vcontainer/          Persistent runtime data
```

### Execution flow

1. The CLI or GUI sends a validated request to the local API.
2. The API invokes a narrowly scoped privileged helper.
3. The helper converts the request into approved runtime arguments.
4. The C engine creates namespaces, cgroups, mounts, networking, and the child.
5. Runtime state is saved under `/var/lib/vcontainer` and exposed through the API.

### Daemonless engine and management service

The C execution engine is daemonless: containers are normal Linux processes and do
not require a long-running engine daemon. The FastAPI systemd service is a local
management plane for the Windows CLI and GUI. It reads state and performs validated
lifecycle operations, but it is not the parent runtime for every container.

## Runtime storage

```text
/opt/vcontainer/bin/                 Installed engine and CLI wrapper
/opt/vcontainer/libexec/             Linux runtime scripts
/usr/local/sbin/vcontainer-*         Restricted API helpers
/var/lib/vcontainer/images/          Imported image root filesystems
/var/lib/vcontainer/containers/      Container state and writable layers
/var/lib/vcontainer/volumes/         Named persistent volumes
/var/lib/vcontainer/oci/             OCI image working data
/home/vcdev/vcontainer-api/          Installed API environment and sources
```

Container state can include configuration, saved launch arguments, lifecycle data,
logs, port data, and OverlayFS `upper`, `work`, and `merged` directories.

## API overview

```text
GET    /health
GET    /system/disk

GET    /images
POST   /images/pull
DELETE /images/{name}

GET    /containers
POST   /containers
GET    /containers/{name}
POST   /containers/{name}/start
POST   /containers/{name}/stop
PATCH  /containers/{name}/resources
DELETE /containers/{name}

GET    /containers/{name}/logs
GET    /containers/{name}/logs/stream
GET    /containers/{name}/metrics
GET    /containers/{name}/metrics/stream
GET    /containers/{name}/processes

GET    /volumes
POST   /volumes
GET    /volumes/{name}
DELETE /volumes/{name}
```

See `/docs` for schemas and interactive requests.

## Development

Rebuild and reinstall the project:

```powershell
python setup.py
```

Update only the API service:

```powershell
python setup_api_service.py
```

Run the API in Windows development mode:

```powershell
cd api
uv sync
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Run integration tests from WSL:

```bash
bash tests/verify_install.sh
bash tests/rest_cases.sh
```

## Troubleshooting

```powershell
wsl -d Ubuntu -u root --exec systemctl status vcontainer-api --no-pager
wsl -d Ubuntu -u root --exec journalctl -u vcontainer-api -n 100 --no-pager
wsl --list --verbose
wsl -d Ubuntu --exec stat -fc %T /sys/fs/cgroup
```

If Ubuntu reports repository metadata as “not valid yet,” synchronize the Windows
clock and restart WSL before running setup again.

## Current limitations

- Linux containers only; Windows containers are not supported.
- WSL 2 and the configured Ubuntu distribution are required on Windows.
- Compose supports a practical subset rather than every Compose key.
- Networking and port publishing are simpler than mature production engines.
- Kubernetes-compatible pod support is not currently implemented.
- Security hardening and compatibility coverage remain experimental.

## Project direction

Planned work includes a GUI Compose/project view, broader image compatibility,
stronger lifecycle supervision, expanded tests, performance measurement, and
continued reduction of startup and management overhead.
