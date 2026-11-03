# Vcontainer additions and updates

This file records user-visible features and material implementation changes.

## Frameless desktop window

- Added a pywebview JavaScript bridge for minimize, maximize/restore, and close.
- The existing Windows 7-styled HTML title bar is now the explicit desktop drag
  region, while its controls remain hidden in ordinary browser sessions.
- Enabled the frameless, resizable Edge WebView2 window with a native shadow and
  repaired the main application layout around the custom title bar.
- Kept the native pywebview `Window` outside the exposed JavaScript API object to
  prevent recursive WinForms object serialization during desktop startup.

## Repository documentation

- Replaced the placeholder root README with current project goals, requirements,
  installation, CLI and Compose usage, GUI/API access, architecture, runtime storage,
  development, troubleshooting, limitations, and project direction.

## Volumes GUI section

- Added a Volumes entry to the GUI sidebar with volume name and Linux mount source.
- Added volume creation, inspection, and guarded removal controls using the existing
  API; in-use and non-empty volumes remain protected by backend conflict checks.
- Expanded volume inspection with attachment state, attached container names and
  statuses, container mount targets, a copyable storage path, and a context-aware
  removal control that is disabled while the volume is attached.
- Added named-volume selection and an absolute container target path to the Run
  dialog, allowing GUI-created containers to use persistent storage directly.

## Container-only disk usage

- Replaced the Home page's WSL filesystem capacity card with actual container disk
  usage: writable OverlayFS upper layers, container metadata, logs, and state files.
- Base images, named volumes, the OverlayFS merged view, and unrelated WSL files are
  excluded to avoid double-counting and to keep the metric container-specific.
- `/system/disk` now also returns a per-container breakdown and container count.

## Idempotent Compose up

- `compose up` now starts matching stopped containers and leaves matching running
  containers alone instead of trying to create duplicate metadata and colliding
  with their existing bridge IP addresses.
- Rollback remains limited to containers newly created by the current `compose up`;
  pre-existing project containers are never deleted on a later service failure.

## Compose start and stop

- Added `compose stop FILE`, which stops project containers in reverse dependency
  order while preserving their metadata, IP assignments, volumes, and commands.
- Added `compose start FILE`, which starts existing project containers in dependency
  order and directs the user to `compose up` if any project container is missing.

## Image-pull stream error handling

- Replaced the GUI image-pull stream with a normal JSON operation because the GUI
  waits for completion and did not display incremental progress.
- Successful pulls now return HTTP 200 with `status: complete`; failures return an
  appropriate HTTP error containing the helper's actual output instead of an HTTP
  200 stream ending with a generic `Image pull failed` event.

## Completed before this metrics update

- Added read API endpoints for images, containers, details, metrics, logs, and
  processes.
- Added restricted container create, start, stop, and remove endpoints.
- Added streamed image pulls and safe image deletion.
- Added named-volume list, create, inspect, and safe removal endpoints.
- Added named-volume mounts to container creation requests.
- Split privileged access into narrowly scoped, root-owned helpers installed in
  `/usr/local/sbin`.
- Updated the API installer to deploy helpers, sudo policy, and the systemd
  service together.

## Metrics, streaming, and details update

Completed in this update:

- Add CPU usage counters and percentage calculated between samples.
- Add memory usage/limit and process usage/limit.
- Add network receive/transmit byte counters from the container network
  namespace.
- Add aggregated cgroup v2 block-I/O statistics.
- Add Server-Sent Events streams for logs and periodic metrics.
- Route `vcontainer.py logs -f NAME` through the API log stream.
- Expand container details with image, timestamps, exit-code field, network
  address, volumes, resource limits, and saved command.

### Added endpoints

```text
GET /containers/{name}/metrics
GET /containers/{name}/metrics/stream
GET /containers/{name}/logs/stream
```

The stream endpoints use Server-Sent Events. The Windows command
`vcontainer.py logs -f NAME` now consumes the API log stream.

### Verification

- Verified two point-in-time CPU samples and CPU percentage calculation.
- Verified periodic metrics SSE events at a 0.5-second interval.
- Verified live memory and process counts.
- Verified bridge-network RX/TX counters.
- Verified block-I/O fields from cgroup v2.
- Verified live log lines through `vcontainer.py logs -f`.
- Verified image, network address, limits, saved command, and lifecycle fields.
- Verified create, start, and stop timestamps using a temporary container.
- Removed all temporary containers, images, and volumes created by these tests.

### Previous exit-code limitation

Detached containers originally had no process waiting to collect their natural
exit status. The API supervision update below resolves this for containers
created or started through the running API service.

## API process supervision update

- API-created and restarted containers now run through a foreground C runtime
  process monitored by the systemd-managed FastAPI service.
- Natural container exit codes and stop times are written to `lifecycle.json`.
- Container start now uses the same asynchronous supervision path as create.
- Signal termination is reported using the conventional `128 + signal` exit
  status, such as `143` for SIGTERM.
- Create and start return HTTP 202 while execution continues in the background.
- Restarting `vcontainer-api.service` still loses supervision of containers that
  were already running. A separate persistent supervisor would be required to
  preserve monitoring across API service restarts.

## Per-process information update

- Added the PID visible inside the container alongside the WSL host PID.
- Added parent PIDs in both the container and host PID namespaces.
- Added total CPU time and lifetime-average CPU percentage for each process.
- Added resident memory usage in bytes from `/proc/HOST_PID/status`.
- Added each process start time as a UTC timestamp.
- Preserved process name, state, UID, and command arguments.
- Process records are read only for PIDs assigned to the container's cgroup and
  are sorted by container PID.

### Process information verification

- Verified `GET /containers/nginx-test/processes` with the Nginx master and
  worker processes.
- Verified container PID, host PID, parent PID, CPU, memory, and start-time
  fields are returned successfully.

## Web dashboard integration

- Added the static HTML, CSS, and JavaScript dashboard to the FastAPI service.
- Updated the dashboard for the current image and container response objects.
- Connected container create, start, stop, remove, logs, metrics, and process
  actions to their current API endpoints.
- Replaced the unsupported image-build and published-port controls with refresh,
  resource-limit, and bridge-address controls.
- Escaped API-provided text before inserting it into generated HTML.
- Verified the page and JavaScript return HTTP 200 and the live container list
  is available from the dashboard backend.

## Native localhost port publishing

- Added validated `ports` mappings to container creation requests.
- Added Docker-style `--publish HOST_PORT:CONTAINER_PORT` and `-p` parsing to
  the Windows launcher.
- Published services bind only to `127.0.0.1` through restricted, transient
  systemd-managed `socat` units.
- Saved mappings in each container's `ports.json` and exposed them through
  container inspection and the dashboard.
- Container start restores saved port mappings automatically.
- Container stop, removal, and natural exit stop their forwarding units.
- Routed Windows create, start, stop, and remove operations through FastAPI so
  lifecycle and port behavior remain consistent.
- Added a lock-protected hidden WSL keepalive launched by `vcontainer.py`, which
  keeps API-supervised browser services available after the launcher exits.
- Added `socat` to fresh installation dependencies and restored the dashboard's
  published-port input and service link.

### Port publishing verification

- Created the official Nginx container with `--publish 8080:80`.
- Verified `http://127.0.0.1:8080` returned HTTP 200 and the Nginx welcome page.
- Verified one `vcontainer.py stop nginx-test` command stopped the container and
  closed port 8080 without a manual WSL or systemctl command.
- Verified `vcontainer.py start nginx-test` restored the saved mapping and the
  Nginx page.

SQLite is an embedded database and does not listen on a network port. SQLite
database files should be persisted through a named volume instead of a published
port.

## Automatic bridge address allocation

- A published port no longer requires the caller to provide `--network bridge`
  and `--ip` manually.
- The API selects the first unused address from `10.88.0.2` through
  `10.88.0.254`, considering both saved containers and concurrent launches.
- Explicit bridge addresses remain supported and duplicate addresses return an
  HTTP 409 conflict.
- The Windows launcher and dashboard now accept a port mapping by itself, for
  example `vcontainer.py run nginx --name web -p 8080:80`.
- Leaving the dashboard command empty now uses the image's configured default
  command instead of forcing `/bin/sh`.

## Persistent API container logs

- Added a C runtime `--log` option that redirects container stdout and stderr to
  its persistent `container.log` without detaching the runtime supervisor.
- API-created and API-restarted containers enable `--log` automatically.
- Added `log` as a friendly alias for the existing `logs` and `logs -f` Windows
  launcher commands.
- Fixed the image configuration JSON error handler typo in the privileged
  control helper.

## Versioned runtime helper package

- Removed privileged helper sources from the main application tree.
- Added a shared installer module that downloads helper release `v0.1.0` from
  GitHub and verifies its pinned SHA-256 checksum before extraction.
- Extraction allowlists the four expected helper filenames, limits archive
  size, rejects duplicate and unsafe paths, and removes temporary files.
- Updated both `setup.py` and `setup_api_service.py` to install helpers from the
  verified release rather than `api/helpers`.

## Container environment variables and CLI aliases

- Added repeatable `-e` and `--env NAME=VALUE` parsing to the Windows launcher.
- Added API validation for environment names, NUL bytes, value length, and the
  maximum number of variables.
- Added `-v` as an alias for named-volume mounts and `-d` as a compatibility
  alias; API-launched containers remain supervised in the background by default.
- Added OCI image environment loading in the separate helper project, with
  explicit user variables overriding image defaults.
- Added C runtime validation and `setenv()` application before the container
  command is executed.
- Environment values are not added to container inspection responses.
- Configured Windows launcher output as UTF-8 with replacement fallback so
  application logs containing Unicode characters cannot crash the CLI.

## Compose executable integration

- Added the native `compose.exe` parser built from `compose-go` as the Compose
  validation and normalization layer for the Windows launcher.
- Added `vcontainer.py compose config FILE` to print the normalized project.
- Added `compose up` translation for images, commands, environment variables,
  named volumes, published TCP ports, container names, and static IPv4 addresses.
- Added automatic creation of top-level named volumes when they do not exist.
- Added basic `depends_on` topological ordering with unknown-dependency and
  circular-dependency validation; `down` uses the reverse dependency order.
- Added `compose down`, which stops and removes services in reverse order.
- Compose bind mounts, anonymous volumes, UDP ports, builds, health-based startup,
  and automatic container-name DNS are not yet supported.

## Standard container devices

- Fixed the empty `/dev` runtime setup by mounting only the host's standard
  `null`, `zero`, `random`, and `urandom` devices into the private container
  `/dev` tmpfs.
- This allows non-root image processes such as MySQL to use `/dev/null` without
  exposing the host's complete `/dev` tree.
- Added `/dev/fd`, `/dev/stdin`, `/dev/stdout`, and `/dev/stderr` links to the
  container's private `/proc/self/fd`, supporting entrypoint process substitution.

## BlogDrop four-container deployment

- Added and validated a Compose configuration for MySQL, a Node backend, a
  static Nginx frontend, and an Nginx gateway published on localhost port 8080.
- Added dependency ordering, fixed bridge addresses, persistent data/source
  volumes, database initialization SQL, and gateway reverse-proxy configuration.
- Separated static frontend serving from the Node API and bound the backend to
  `0.0.0.0:3000`.
- Populated all WSL volumes and initialized the MySQL schema and application user.
- Verified the frontend returns HTTP 200 and `/api/health` returns HTTP 200 with
  a successful database connection.
- The Node dependency audit currently reports one high-severity dependency issue;
  it was reported but not automatically modified during deployment.

## REST integration tests

- Added `tests/rest_cases.sh`, adapted from the separate test project to the
  current FastAPI service on port 8010 and its current JSON response fields.
- Removed dependencies on the custom `blog` and `runner` images; the suite uses
  Alpine by default and supports `VCONTAINER_TEST_IMAGE` and
  `VCONTAINER_API_URL` overrides.
- Added checks for command execution and logs, stop/start lifecycle,
  environment variables, root filesystem isolation, hostname isolation, and
  memory-limit enforcement.
- Added bounded polling, cleanup before and after each case, API/image
  preflight checks, and a final pass/fail summary.

## Installation verification

- Added `tests/verify_install.sh`, a read-only verification command for cgroup
  v2, overlayfs, installed runtime/helper files, the API systemd service,
  storage directories, the health endpoint, and required Linux programs.

## Runtime, Compose, installer, and dashboard hardening

- Completed the private OCI-style device layout with `/dev/full`, `/dev/tty`,
  a private `devpts` mount and `/dev/ptmx`, `/dev/shm`, and `/dev/mqueue` in
  both Windows/WSL and ARM source trees.
- Kept the standard descriptor links and device bind mounts isolated from the
  rest of the host `/dev` tree.
- Made custom seccomp deny lists additive to the mandatory default deny list;
  custom rules can no longer accidentally re-enable mount, namespace, ptrace,
  reboot, or kernel-module operations.
- Added API startup reconciliation for saved published ports belonging to
  containers that remain running across an API service restart.
- Added project-scoped default Compose container names, `compose ps`, and
  reverse-order rollback when a multi-service `compose up` fails partway.
- Simplified `compose down` to use the API's stop-and-remove DELETE behavior.
- Made `setup.py` run the read-only installation verification automatically.
- Ported the useful design patterns from the separate test dashboard: a
  responsive sidebar, Home summary, dark/light themes, container cards,
  detailed resources/logs/processes, image pull/delete, environment input,
  and published-service links. Vcfile build/upload controls were intentionally
  excluded.
- Expanded the REST suite with direct deletion of a running container and a
  combined standard-device, virtual-filesystem, and seccomp check.
- Verified both C source trees compile with `-Wall -Wextra -Werror`, installer
  checks pass 20/20, REST checks pass 8/8, dashboard assets return HTTP 200,
  the BlogDrop Compose project reports all four services running, port 8080
  survives an API restart, and log-stream cancellation leaves no helper
  process behind.

### Privileged-helper follow-up

- Persistent final cgroup statistics, durable transitional states, automatic
  container-name DNS, bind mounts, health-aware Compose dependencies, and
  capability/device-cgroup policy require changes to the separately versioned
  privileged helper package. They were not faked in the unprivileged API or
  silently substituted for the pinned helper release.

## Lightweight performance benchmark

- Added `tests/lightweight_benchmark.ps1`, which measures API memory and
  latency, warm Alpine startup, incremental memory for idle containers,
  BlogDrop HTTP latency, runtime/API installation size, and image/state size.
- The benchmark always deletes its temporary containers and writes a reusable
  Markdown report to `performance_report.md`.
- On the current warm WSL system with four BlogDrop containers already running,
  the API used 60.64 MiB, warm Alpine startup averaged 172.94 ms, five idle
  Alpine containers added approximately 4.27 MiB to the WSL working set, and
  the compiled runtime binary was 120.31 KiB.
- The current WSL instance exposes 12 processors with no configured memory cap;
  these results establish a baseline but are not presented as a controlled
  one-core/one-gigabyte low-end-machine result.

## Controlled low-end benchmark

- Added `tests/controlled_low_end_benchmark.ps1`. It temporarily applies a
  1 GiB RAM, one-processor, 256 MiB swap WSL profile, restarts WSL, runs the
  benchmark, and restores the user's original `.wslconfig` in a `finally`
  block. The machine had no original `.wslconfig`, and that absence was
  restored after the test.
- Improved benchmark diagnostics so failed API calls include their HTTP method
  and path, and made cleanup retry bounded and explicit.
- Startup samples now use a two-second workload and allow it to exit naturally;
  this measures startup without mixing forced-stop cgroup teardown into the
  timing result.
- Under the controlled profile, the API used 35.23 MiB current and 41.83 MiB
  peak memory. Container-list requests averaged 62.79 ms (79.45 ms p95), warm
  Alpine startup averaged 317.09 ms (409.20 ms p95), and five idle Alpine
  containers used 1.55 MiB in their cgroups.
- The compiled runtime remained 120.31 KiB and its installed runtime directory
  was 0.14 MiB. The Python API environment occupied 37.26 MiB; downloaded
  images, at 1174.23 MiB, are the main disk-space cost.
- The stress run exposed a reproducible lifecycle weakness: forced deletion of
  a newly started container can observe an empty cgroup before it is removable
  on a single CPU. The API now waits for the stopped state and retries metadata
  removal, but the privileged runtime/helper still needs an authoritative
  teardown acknowledgement to eliminate this race completely.
- All `perf-*` containers left by failed stress iterations were removed after
  WSL restarted. No benchmark container remains.

## Dashboard visual refresh

- Integrated the supplied dashboard's visual language into the served GUI
  without importing its incompatible API calls.
- Added gradient navigation, grouped sidebar controls, colored summary tiles,
  aggregate CPU/memory/process gauges, image markers, richer container cards,
  and per-container memory and process meters.
- Preserved the existing Vcontainer API contract for container names, metrics,
  logs, image pulling, resource limits, environment variables, port mappings,
  and lifecycle actions.
- Unsupported VC File build, image upload/download, `/system`, `/stats`, and
  exec-console controls were intentionally not introduced.
- Fixed GUI container launches when Uvicorn runs directly on Windows. Windows
  now uses `subprocess.Popen` for the long-running WSL control process because
  the active Uvicorn event loop can reject `asyncio.create_subprocess_exec`.
  Native Linux/WSL service execution retains the asyncio subprocess path.
- Startup supervision now logs exception types and propagates failures that
  happen before a container reaches `running`, preventing a misleading 202
  response followed by a missing container.

## Live resource-limit updates

- Added `PATCH /containers/{name}/resources` with narrowly validated memory,
  PID, and CPU quota/period fields.
- Extended the privileged control helper with a `resources NAME` operation.
  It updates `memory.max` for a running container and atomically updates both
  the readable container configuration and the NUL-delimited saved launch
  arguments so the new limit survives stop/start cycles.
- Added an **Edit resources** dialog to the container-details card for memory,
  PID limit, and CPU quota/period.
- Resource editing is available only for stopped containers. The GUI hides the
  action while running, and both the API and privileged helper independently
  reject running-container updates with a clear stop-first error.
- Confirmed `blogdrop-db` was at 262,066,176 of 262,144,000 bytes (effectively
  100% of its old 250M cgroup limit). A 512M trial also reached 496 MiB during
  InnoDB initialization, so its persistent/live limit is now 1G
  (1,073,741,824 bytes).
- Raised `blogdrop-db` from 64 to 128 PIDs and from half a CPU
  (`50000/100000`) to one CPU (`100000/100000`). All three live cgroup values
  and their saved restart values were verified.
- Development setup now prefers the separately checked-out local helper package
  when present, avoiding both stale release helpers and unnecessary downloads.
  A new helper release must be published before standalone installations can
  receive this operation without the sibling helper checkout.
# Python package restructuring

- Renamed the FastAPI package to `vcontainer_api`.
- Split API routes into container, image, system, and volume routers.
- Split API metrics and container supervision into service modules.
- Moved shared API validation and runtime error translation to `dependencies.py`.
- Kept the root Windows `vcontainer.py` as a compatible launcher.
- Moved the Windows implementation into the `vcontainer_cli` package.
- Split Windows constants, API transport, errors, and run parsing into focused modules.
- Preserved all API paths, CLI commands, and launcher behavior.
- Fixed the metrics SSE endpoint so it returns its streaming response.
- Consolidated the Windows CLI and desktop application into one `uv` project.
- Moved Windows Python packages under `Vcontainer(win)/src`.
- Moved the C engine under `Vcontainer(win)/engine`.
- Moved the Compose executable and sources under `Vcontainer(win)/vendor`.
- Moved Windows launch scripts under `Vcontainer(win)/scripts` while retaining
  root compatibility launchers.
- Moved the installable WSL helper repository under `helper/vcontainer-helper`.
- Added API unit tests and repository-level architecture documentation.
- Rewrote the root README as an installation, usage, command, development, and
  troubleshooting guide for the reorganized repository.
- Expanded `docs/architecture.md` with component boundaries, runtime flows,
  storage, networking, Compose behavior, privilege boundaries, and known limits.
- Documented standalone PyInstaller builds for the Windows CLI and GUI.
- Added repository and Windows-project ignore rules for Python environments,
  caches, PyInstaller work files, and generated executables.
- Added `scripts/vcontainer-cli-global.ps1` and
  `scripts/vcontainer-cli-unglobal.ps1` for adding or removing the standalone
  commands from the current Windows user's `PATH`.
- Fixed local WSL helper discovery after moving `vcontainer-helper` into the
  repository, avoiding an unnecessary release download during setup.
- Rebuilt `vcontainer-helpers-v0.2.0.zip` from the active helper sources and
  updated the installer checksum.

# Compose service replacement

- Added `compose up FILE --service SERVICE --replace` to recreate one changed
  service without stopping the rest of the Compose project.
- Replacement removes only the selected container. Named volumes are preserved
  and reused by the recreated container.

# Compose resource limits

- Compose services now pass `mem_limit`, `pids_limit`, and `cpus` into the
  Vcontainer API when a container is created.
- `deploy.resources.limits` is also accepted as a fallback.
- BlogDrop now has explicit CPU, memory, and process limits for every service.

# Faster first installation

- Removed the unused Windows API environment. The API environment is now
  created only inside WSL, where the service runs.
- Production setup uses `uv sync --locked --no-dev` for the Windows client and
  WSL API, avoiding PyInstaller, pytest, Ruff, and their dependencies.
- Curl and certificates are installed in the first Linux package transaction,
  avoiding a second `apt-get update` during API setup.
- APT uses `--no-install-recommends` to skip unrelated optional packages.

# Parizval layout migration

- Updated `gui/` from `penguintypes/Virtualised-Container` on GitHub and kept
  the previous files under `backend/legacy/gui-before-github`.
- Restored the PyWebView application titlebar, window controls, drag region,
  and edge-resize bridge that were absent from the downloaded GUI.
- Added image size and creation timestamps to the restricted image-listing
  response so the GUI Images table displays numeric information.
- Removed the GUI Quick Start card and its Blog, Runner, and BlogDrop-specific
  launch code.
- Removed the GUI Kill server control and its unused request handler.
- Made the frameless desktop application and custom titlebar fill the complete
  PyWebView client area without gaps at the window edges.
- Renamed `windows/client` to `client`, removed the unused machine experiment,
  and removed the duplicate `vcontainer.ps1` wrappers.
- Removed the obsolete `install.sh`, `start.sh`, and `install.nsi` entry points;
  installation now starts with `setup.py` or its `install.ps1` wrapper.
- Preserved the Parizval dashboard in `gui/`.
- Moved the current C engine to `backend/runtime` and the FastAPI project to
  `backend/api`.
- Added the restricted WSL helpers under `backend/helpers`.
- Moved the Windows CLI and desktop projects under `windows/client`.
- Updated setup to install the preserved GUI alongside the WSL API service.
- Added API compatibility for Parizval live metrics and dashboard launch
  payloads.
- Archived the earlier Parizval Python backend under `backend/legacy`.

