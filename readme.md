# Vcontainer

Vcontainer is a small Linux container engine for Windows through WSL 2. The
runtime is written in C and uses Linux namespaces, cgroups v2, OverlayFS,
seccomp and virtual Ethernet devices. A FastAPI service connects the runtime to
the Windows CLI, browser dashboard and PyWebView desktop application.

Docker and Podman are not required. Vcontainer uses Skopeo and Umoci to pull and
unpack OCI images.

This is an educational container runtime. It is suitable for learning,
experimentation and testing this project's workflow. It has not received the
compatibility or security review expected from a production container engine.

## Goal

The project keeps the Windows workflow simple while leaving the Linux runtime
visible. Users can work from the CLI or GUI, and developers can inspect how the
engine creates namespaces, applies resource limits, mounts filesystems and
configures networking.

## Features

- OCI and Docker image pulls
- foreground and detached containers
- start, stop, remove, inspect, exec and logs
- CPU, memory and process limits with cgroups v2
- bridge networking and TCP ports published to Windows localhost
- named volumes for persistent data
- environment variables, hostnames and command overrides
- CPU, memory, process, network and block-I/O metrics
- process details with host and container PIDs
- Compose YAML validation and project lifecycle controls
- browser dashboard and PyWebView desktop GUI
- storage accounting for images, volumes and container writable data
- saved container commands for restart after WSL restarts

## Requirements

- Windows 10 or Windows 11
- WSL 2 with Ubuntu
- Python 3.12 or newer on Windows
- hardware virtualization enabled
- internet access during installation and image pulls

Install Ubuntu and confirm that it uses WSL 2:

```powershell
wsl --install -d Ubuntu
wsl --list --verbose
```

The Ubuntu row should show version `2`.

## Configuration

Edit `vcontainer.config` in the repository root before installation:

```ini
[api]
host = 127.0.0.1
port = 8010

[wsl]
distribution = Ubuntu
user = vcdev
```

Keep `host = 127.0.0.1` unless the API has been secured for network access.
Vcontainer's API can create, stop and remove containers, so exposing it to a
network without authentication is unsafe.

The CLI, desktop launcher and API installer read this file. Environment
variables override it when a temporary value is needed:

```powershell
$env:VCONTAINER_API_PORT = "9000"
$env:VCONTAINER_WSL_DISTRO = "Ubuntu"
$env:VCONTAINER_WSL_USER = "vcdev"
```

## Install

Run the complete installer from the repository root:

```powershell
python setup.py
```

The installer:

1. checks WSL, cgroups v2 and OverlayFS;
2. installs the required Ubuntu packages;
3. creates the configured WSL user if needed;
4. builds and installs the C runtime;
5. prepares the Windows client with `uv`;
6. installs the restricted runtime helpers;
7. installs and starts the API as a systemd service;
8. runs the installation checks.

Reinstall only the API, helpers and GUI after changing those files or changing
the configured API port:

```powershell
python setup_api_service.py
```

The installed service starts automatically with WSL. You do not need to run
Uvicorn manually for normal use.

## Browser GUI

Open the configured address. With the default configuration:

```powershell
Start-Process "http://127.0.0.1:8010/"
```

API documentation:

```powershell
Start-Process "http://127.0.0.1:8010/docs"
```

If the port in `vcontainer.config` is changed to `8011`, reinstall the API and
open the matching URL:

```powershell
python setup_api_service.py
Start-Process "http://127.0.0.1:8011/"
```

The JavaScript uses relative API paths, so it automatically follows the host
and port that served the page.

## Desktop GUI

Start the PyWebView application from the repository root:

```powershell
uv run --project client vcontainer-gui
```

The desktop application uses the same GUI and API as the browser. Containers
created in either interface are visible in the other interface and the CLI.

The GUI provides:

- container cards with status, resource use and published ports;
- image pull and deletion;
- volume creation, inspection and removal;
- logs, process information and resource editing;
- Compose YAML editing, validation, start, stop, restart and removal;
- live CPU, RAM and storage information.

## CLI

Run the Python client from the repository root:

```powershell
python "client/vcontainer.py" COMMAND
```

### Images

```powershell
python "client/vcontainer.py" list
python "client/vcontainer.py" pull alpine
python "client/vcontainer.py" pull redis docker.io/library/redis:7-alpine
python "client/vcontainer.py" delete redis
```

`LOCAL_NAME` is the short name used by Vcontainer. The optional second value is
the registry reference.

### Containers

```powershell
python "client/vcontainer.py" ps
python "client/vcontainer.py" inspect NAME
python "client/vcontainer.py" logs NAME
python "client/vcontainer.py" logs -f NAME
python "client/vcontainer.py" exec NAME -- COMMAND ARGUMENTS
python "client/vcontainer.py" start NAME
python "client/vcontainer.py" stop NAME
python "client/vcontainer.py" rm NAME
```

Run Alpine in the foreground:

```powershell
python "client/vcontainer.py" pull alpine
python "client/vcontainer.py" run alpine `
  --name hello `
  -- /bin/echo "Hello from Vcontainer"
```

Run nginx in the background and publish it to Windows:

```powershell
python "client/vcontainer.py" pull nginx
python "client/vcontainer.py" run nginx `
  --name web `
  --detach `
  --publish 8080:80
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

### Run options

```text
--name NAME                    required container name
-d, --detach                  run in the background
--hostname NAME               set the container hostname
--memory-max SIZE             memory limit, such as 256M or 1G
--pids-max COUNT              maximum number of processes
--cpu-max QUOTA PERIOD        cgroup CPU quota and period
--network bridge              attach to the Vcontainer bridge
--ip ADDRESS                  request a static bridge address
-p, --publish HOST:CONTAINER  publish a TCP port to Windows
-v, --volume NAME:/TARGET     mount a named volume
-e, --env NAME=VALUE          set an environment variable
-- COMMAND [ARGS...]           override the image command
```

The GUI accepts CPU limits as cores, such as `0.5`, `1` or `2`, and converts
them to cgroup quota and period values. It rejects limits greater than the CPUs
available to WSL.

Example with limits and environment variables:

```powershell
python "client/vcontainer.py" run alpine `
  --name worker `
  --memory-max 256M `
  --pids-max 64 `
  --cpu-max 50000 100000 `
  --env MODE=development `
  --detach `
  -- /bin/sleep 300
```

## Volumes

Create and inspect a named volume:

```powershell
python "client/vcontainer.py" volume create app-data
python "client/vcontainer.py" volume list
python "client/vcontainer.py" volume inspect app-data
```

Mount it inside a container:

```powershell
python "client/vcontainer.py" run alpine `
  --name volume-demo `
  --volume app-data:/data `
  -- /bin/sh -c "echo saved > /data/message.txt"
```

The target is the path inside the container. Common targets include:

| Image | Target |
|---|---|
| Redis | `/data` |
| MySQL | `/var/lib/mysql` |
| PostgreSQL | `/var/lib/postgresql/data` |
| nginx website | `/usr/share/nginx/html` |
| Node application | `/app` |

Remove an unused volume:

```powershell
python "client/vcontainer.py" volume remove app-data
```

## Environment variables

The CLI accepts repeated `--env` options:

```powershell
python "client/vcontainer.py" run alpine `
  --name env-demo `
  --env MODE=development `
  --env LOG_LEVEL=info `
  -- /usr/bin/env
```

In the GUI, enter one assignment per line:

```text
DB_HOST=10.88.0.30
DB_NAME=example
LOG_LEVEL=info
```

## Compose

Vcontainer uses a bundled Compose-Go parser. The supported subset includes:

- images and command overrides;
- environment variables;
- named volumes;
- TCP port publishing;
- service dependencies;
- memory, CPU and PID limits;
- static bridge addresses.

CLI commands:

```powershell
$config = "C:\path\to\compose.yaml"

python "client/vcontainer.py" compose config $config
python "client/vcontainer.py" compose up $config
python "client/vcontainer.py" compose ps $config
python "client/vcontainer.py" compose stop $config
python "client/vcontainer.py" compose start $config
python "client/vcontainer.py" compose down $config
```

`stop` keeps container metadata and volumes. `start` runs the stopped services
again. `down` removes the project containers and keeps named volumes.

In the GUI, the equivalent destructive action is labeled **Remove**. Compose
startup is asynchronous, so the page follows the project until all services
reach their reported state.

Service order does not guarantee service readiness. A backend that depends on a
database should retry temporary connection failures. MySQL may need several
seconds after its container starts before it accepts connections.

## Build Windows executables

Install the client development dependencies:

```powershell
uv sync --project client --all-groups
```

Build the desktop application as a single executable:

```powershell
uv run --project client pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name vcontainer-gui `
  --paths "client/src" `
  --collect-all webview `
  --distpath "client" `
  --workpath "client/build/pyinstaller-gui" `
  --specpath "client/build" `
  "client/src/vcontainer_desktop/vcontainer_gui.py"
```

Build the CLI:

```powershell
cd client
$composeData = ((Resolve-Path "vendor/compose/compose.exe").Path + ";vendor/compose")

uv run pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name vcontainer `
  --paths src `
  --add-data $composeData `
  --distpath . `
  --workpath "build/pyinstaller-cli" `
  --specpath build `
  vcontainer.py
cd ..
```

Add the generated commands to the Windows user `PATH`:

```powershell
& "client/scripts/vcontainer-cli-global.ps1"
```

Open a new terminal, then run:

```powershell
vcontainer ps
vcontainer-gui
```

Remove the path entry:

```powershell
& "client/scripts/vcontainer-cli-unglobal.ps1"
```

Place `vcontainer.config` beside packaged executables, or set
`VCONTAINER_CONFIG` to the full configuration path.

## Architecture

```text
Windows CLI / browser / desktop GUI
                 |
                 v
       FastAPI on WSL localhost
                 |
                 v
       restricted sudo helpers
                 |
                 v
          C container runtime
                 |
       namespaces + cgroups v2
       OverlayFS + seccomp + veth
```

Repository layout:

```text
backend/
  api/                    FastAPI service
  runtime/                C runtime and Linux wrapper
  helpers/                restricted privileged helpers
  legacy/                 archived implementation
client/
  src/vcontainer_cli/     Windows CLI
  src/vcontainer_desktop/ PyWebView launcher
  vendor/compose/         Compose parser executable
gui/                      browser and desktop interface
docs/                     architecture notes
tests/                    installation and runtime checks
setup.py                  complete installer
setup_api_service.py      API/helper/GUI reinstall
uninstall.py              safe uninstaller
vcontainer.config         shared configuration
```

See [docs/architecture.md](docs/architecture.md) for component details.

## Diagnostics

Check the configured service:

```powershell
wsl -d Ubuntu -u root --exec systemctl status vcontainer-api --no-pager
wsl -d Ubuntu -u root --exec journalctl -u vcontainer-api -n 100 --no-pager
```

Restart it:

```powershell
wsl -d Ubuntu -u root --exec systemctl restart vcontainer-api
```

If a changed port still serves the old address, regenerate the systemd service:

```powershell
python setup_api_service.py
```

Container diagnostics:

```powershell
python "client/vcontainer.py" ps
python "client/vcontainer.py" inspect NAME
python "client/vcontainer.py" logs NAME
```

Common errors:

| Error | Meaning |
|---|---|
| `ECONNREFUSED` | the destination service is not accepting connections yet |
| `Address already in use` | another container or API process owns the port |
| exit code `1` | the application returned an error |
| exit code `137` | the process was killed, commonly by a memory limit |
| Compose helper missing | the API was started on Windows instead of inside WSL |

## Development

Prepare environments:

```powershell
uv sync --project backend/api --all-groups
uv sync --project client --all-groups
```

Reinstall API and helper changes:

```powershell
python setup_api_service.py
```

Build the C runtime inside WSL:

```bash
cd /mnt/c/path/to/project/backend/runtime
make clean
make
```

## Uninstall

Remove Vcontainer and its stored data:

```powershell
python uninstall.py
```

The command requires typing `REMOVE VCONTAINER` before deletion.

Preserve `/var/lib/vcontainer`, including images, volumes and container state:

```powershell
python uninstall.py --keep-data
```

The uninstaller removes the API service, runtime, helpers, sudo policy, port
services and installed API environment. It does not unregister WSL, remove the
WSL user, uninstall shared Ubuntu packages or delete the source repository.

## Recent changes

- Added shared configuration through `vcontainer.config`.
- Added browser and PyWebView interfaces backed by the same API.
- Added Compose project listing, editing and lifecycle controls.
- Added friendly CPU-core input and WSL-capacity validation in the GUI.
- Added full Vcontainer disk-utilization reporting by category.
- Added image and storage caching to avoid repeated filesystem scans.
- Reduced duplicate runtime requests during dashboard refreshes.
- Added multiline environment-variable input and readable API validation errors.
- Added `uninstall.py` with optional data preservation.

## Current limits

- Vcontainer runs Linux containers only.
- The Windows workflow requires WSL 2.
- Compose support is a subset of the full Compose specification.
- Only TCP port publishing is implemented.
- Kubernetes pods are not implemented.
- Network and image compatibility need broader testing.
- The API has no authentication and should remain bound to localhost.
