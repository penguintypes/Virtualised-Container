# Vcontainer

Vcontainer is a small Linux container engine with a Windows interface built on
WSL 2. The runtime is written in C. A local FastAPI service exposes the runtime
to the Windows command-line client and desktop application.

The engine creates containers with Linux namespaces, cgroups v2, OverlayFS,
seccomp, and virtual Ethernet devices. Docker and Podman are not required to run
a container. Skopeo and Umoci handle image downloads and OCI unpacking.

Vcontainer is an educational project. It is useful for learning how container
runtimes work and for testing the project's own container workflow. It has not
had the compatibility or security review required for production workloads.

## What works

- OCI and Docker image pulls
- foreground and detached containers
- start, stop, inspect, remove, exec, and logs
- CPU, memory, and process limits through cgroups v2
- process, network, block I/O, memory, and CPU metrics
- bridge networking with TCP ports published to Windows localhost
- named volumes and persistent writable container layers
- environment variables, hostnames, and command overrides
- Compose files for supported services, volumes, ports, and dependencies
- browser and PyWebView interfaces backed by the same HTTP API

## Requirements

- Windows 10 or Windows 11
- WSL 2 with Ubuntu
- Python 3.12 or newer on Windows
- hardware virtualization
- internet access during installation and image pulls

Install Ubuntu and check its WSL version:

```powershell
wsl --install -d Ubuntu
wsl --list --verbose
```

The Ubuntu row should show version `2`.

## Install

Run the installer from the repository root:

```powershell
python setup.py
```

The installer adds the Linux build dependencies, builds the C engine, installs
the restricted WSL helpers, prepares both `uv` projects, installs the API as a
systemd service, and runs the installation checks.

The default configuration is:

```text
WSL distribution: Ubuntu
WSL user:         vcdev
API:              http://127.0.0.1:8010
```

Set another distribution or user before running the client:

```powershell
$env:VCONTAINER_WSL_DISTRO = "Ubuntu"
$env:VCONTAINER_WSL_USER = "vcdev"
```

## First container

```powershell
python "Vcontainer(win)/vcontainer.py" pull alpine

python "Vcontainer(win)/vcontainer.py" run alpine `
  --name hello `
  -- /bin/echo "Hello from Vcontainer"

python "Vcontainer(win)/vcontainer.py" ps
```

Run Nginx and publish its port to Windows:

```powershell
python "Vcontainer(win)/vcontainer.py" pull nginx
python "Vcontainer(win)/vcontainer.py" run nginx --name web -d -p 8080:80
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080), then stop and remove the
container:

```powershell
python "Vcontainer(win)/vcontainer.py" stop web
python "Vcontainer(win)/vcontainer.py" rm web
```

## Command reference

The root launcher keeps the command stable even though the implementation lives
in `Vcontainer(win)/src/vcontainer_cli`.

### Images

```powershell
python "Vcontainer(win)/vcontainer.py" list
python "Vcontainer(win)/vcontainer.py" pull LOCAL_NAME
python "Vcontainer(win)/vcontainer.py" pull LOCAL_NAME REGISTRY/IMAGE:TAG
python "Vcontainer(win)/vcontainer.py" delete IMAGE
```

Example with a registry reference:

```powershell
python "Vcontainer(win)/vcontainer.py" pull mint ghcr.io/mint-lang/mint:latest
```

### Containers

```powershell
python "Vcontainer(win)/vcontainer.py" ps
python "Vcontainer(win)/vcontainer.py" inspect NAME
python "Vcontainer(win)/vcontainer.py" logs NAME
python "Vcontainer(win)/vcontainer.py" logs -f NAME
python "Vcontainer(win)/vcontainer.py" exec NAME -- COMMAND [ARGS...]
python "Vcontainer(win)/vcontainer.py" start NAME
python "Vcontainer(win)/vcontainer.py" stop NAME
python "Vcontainer(win)/vcontainer.py" rm NAME
```

Create a container with resource limits:

```powershell
python "Vcontainer(win)/vcontainer.py" run alpine `
  --name worker `
  --hostname worker-1 `
  --memory-max 256M `
  --pids-max 64 `
  --cpu-max 50000 100000 `
  -e MODE=development `
  -d `
  -- /bin/sleep 300
```

Supported `run` options:

```text
--name NAME                    required container name
-d, --detach                  run in the background
--hostname NAME                set the container hostname
--memory-max SIZE              set the memory limit, for example 256M
--pids-max COUNT               set the process limit
--cpu-max QUOTA PERIOD         set the cgroup CPU quota and period
--network bridge               attach the container to the bridge
--ip ADDRESS                   request a bridge address
-p, --publish HOST:CONTAINER   publish a TCP port
-v, --volume NAME:/TARGET      mount a named volume
-e, --env NAME=VALUE           set an environment variable
-- COMMAND [ARGS...]           override the image command
```

If `-p` is present without `--network` and `--ip`, the API assigns an available
bridge address.

### Volumes

```powershell
python "Vcontainer(win)/vcontainer.py" volume create app-data
python "Vcontainer(win)/vcontainer.py" volume list
python "Vcontainer(win)/vcontainer.py" volume inspect app-data
python "Vcontainer(win)/vcontainer.py" volume remove app-data
```

Mount a volume:

```powershell
python "Vcontainer(win)/vcontainer.py" run alpine `
  --name volume-demo `
  -v app-data:/data `
  -- /bin/sh -c "echo saved > /data/message.txt"
```

### Compose

Vcontainer uses the bundled Compose-Go parser to normalize YAML before the
Windows client creates containers. The supported subset covers images, commands,
environment variables, named volumes, TCP ports, service dependencies, and
static bridge addresses.

```powershell
$config = "C:\path\to\config.yaml"

python "Vcontainer(win)/vcontainer.py" compose config $config
python "Vcontainer(win)/vcontainer.py" compose up $config
python "Vcontainer(win)/vcontainer.py" compose ps $config
python "Vcontainer(win)/vcontainer.py" compose stop $config
python "Vcontainer(win)/vcontainer.py" compose start $config
python "Vcontainer(win)/vcontainer.py" compose down $config
```

`stop` keeps container metadata and volumes. `start` runs the stopped services
again. `down` removes the project containers but keeps named volumes.

## GUI and API

The installer starts the API at these addresses:

- dashboard: [http://127.0.0.1:8010](http://127.0.0.1:8010)
- OpenAPI documentation: [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)

Run the desktop window from the repository root:

```powershell
uv run --project "Vcontainer(win)" vcontainer-gui
```

The dashboard and desktop window use the same static interface and API.

## Standalone Windows executables

PyInstaller can package the CLI and desktop application as single executable
files. A one-file build extracts its Python runtime to a temporary directory when
it starts, so it opens more slowly than a normal Python command.

Build the GUI from the repository root:

```powershell
uv run --project "Vcontainer(win)" pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name vcontainer-gui `
  --paths "Vcontainer(win)/src" `
  --collect-all webview `
  --distpath "Vcontainer(win)" `
  --workpath "Vcontainer(win)/build/pyinstaller-gui" `
  --specpath "Vcontainer(win)/build" `
  "Vcontainer(win)/src/vcontainer_desktop/vcontainer_gui.py"
```

The output is `Vcontainer(win)/vcontainer-gui.exe`.

Build the CLI:

```powershell
cd "Vcontainer(win)"

$engineData = ((Resolve-Path "engine/run_container.sh").Path + ";engine")
$composeData = ((Resolve-Path "vendor/compose/compose.exe").Path + ";vendor/compose")

uv run pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name vcontainer `
  --paths src `
  --add-data $engineData `
  --add-data $composeData `
  --distpath . `
  --workpath "build/pyinstaller-cli-onefile" `
  --specpath build `
  vcontainer.py
```

The output is `Vcontainer(win)/vcontainer.exe`. Return to the repository root
before using commands from the remaining sections:

```powershell
cd ..
```

Run the packaged applications:

```powershell
& "Vcontainer(win)/vcontainer-gui.exe"
& "Vcontainer(win)/vcontainer.exe" ps
```

Install the commands in your user `PATH`:

```powershell
& "Vcontainer(win)/scripts/vcontainer-cli-global.ps1"
```

Open a new PowerShell window. The executables can then be called from any
directory:

```powershell
vcontainer ps
vcontainer list
vcontainer-gui
```

Remove the directory from your user `PATH`:

```powershell
& "Vcontainer(win)/scripts/vcontainer-cli-unglobal.ps1"
```

The unglobal script only changes `PATH`. It does not delete either executable.

The generated executables, PyInstaller work directories, and old onedir output
folders are excluded by `.gitignore`.

## Repository layout

```text
api/                         FastAPI service installed in WSL
helper/vcontainer-helper/    restricted privileged helper package
Vcontainer(win)/
  engine/                    C runtime and Linux wrapper
  src/vcontainer_cli/        Windows CLI and Compose orchestration
  src/vcontainer_desktop/    PyWebView desktop launcher
  vendor/compose/            bundled Compose-Go executable and sources
  machine/                   WSL machine experiments
docs/                        architecture and development notes
tests/                       installation, WSL, and benchmark tests
```

The detailed component and request flows are in
[docs/architecture.md](docs/architecture.md).

## Development commands

Prepare the Python environments:

```powershell
uv sync --project api --all-groups
uv sync --project "Vcontainer(win)" --all-groups
```

Run the API from Windows for development:

```powershell
uv run --project api uvicorn vcontainer_api.main:app `
  --host 127.0.0.1 `
  --port 8000 `
  --reload
```

Run lint and tests:

```powershell
uv run --project api ruff check api/src/vcontainer_api api/tests
uv run --project api pytest api/tests -q

uv run --project "Vcontainer(win)" ruff check `
  "Vcontainer(win)/vcontainer.py" `
  "Vcontainer(win)/src"

uv run --project "Vcontainer(win)" pytest `
  "Vcontainer(win)/tests/test_vcontainer.py" `
  "Vcontainer(win)/tests/test_launcher.py" `
  -q
```

Build the C engine from WSL:

```bash
cd "/mnt/c/path/to/repository/Vcontainer(win)/engine"
make clean
make
```

Run the WSL regression checks from the repository root inside WSL:

```bash
bash tests/verify_install.sh
bash tests/rest_cases.sh
```

Reinstall only the API service after changing API or helper code:

```powershell
python setup_api_service.py
```

## Service diagnostics

```powershell
wsl -d Ubuntu -u root --exec systemctl status vcontainer-api --no-pager
wsl -d Ubuntu -u root --exec journalctl -u vcontainer-api -n 100 --no-pager
wsl -d Ubuntu --exec stat -fc %T /sys/fs/cgroup
wsl --list --verbose
```

Stop or restart the API service:

```powershell
wsl -d Ubuntu -u root --exec systemctl stop vcontainer-api
wsl -d Ubuntu -u root --exec systemctl restart vcontainer-api
```

If `apt` says a repository release file is not valid yet, restart WSL after
correcting the Windows clock:

```powershell
wsl --shutdown
```

## Current limits

- Vcontainer runs Linux containers only.
- The Windows workflow requires WSL 2 and the configured distribution.
- Compose support covers the fields used by this project, not the full Compose
  specification.
- Port publishing and networking are smaller in scope than Docker or Podman.
- Kubernetes pods are not implemented.
- Detached lifecycle supervision and image compatibility still need broader
  testing.
