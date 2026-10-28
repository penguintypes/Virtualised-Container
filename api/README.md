# Vcontainer API

Install or update the restricted Linux backend from the project directory:

```powershell
python setup_api_service.py
```

The main `setup.py` also invokes this installer. It requires the Linux user and
restricted read helper to be provisioned first. API sources are copied into
`/home/vcdev/vcontainer-api`, with their own Linux uv environment. The systemd
service runs as `vcdev` and listens on `127.0.0.1:8010`.

The Windows CLI uses this backend for `list`, `ps`, `inspect`, and non-following
`logs`. Runtime-changing CLI commands still use the WSL wrapper. API requests
inside Linux call narrowly scoped read, container-control, and image-control
helpers. The Windows API development mode remains supported.

Image pulls stream newline-delimited JSON (`application/x-ndjson`). Each line is
an independent event with `type` set to `progress`, `complete`, or `error`:

```text
POST /images/pull
DELETE /images/{name}
```

The pull request body contains `name` and an optional remote `reference`.

Container details and metrics are available through:

```text
GET /containers/{name}
GET /containers/{name}/metrics
GET /containers/{name}/metrics/stream?interval=1
GET /containers/{name}/logs
GET /containers/{name}/logs/stream
GET /containers/{name}/processes
```

The two `/stream` routes use Server-Sent Events (`text/event-stream`). CPU
percentage is calculated between samples, so the first metrics response can
contain `null`. Detached containers do not yet have a persistent exit-status
supervisor; `exit_code` therefore remains `null` rather than reporting an
unreliable value.

Named volumes are available through:

```text
GET    /volumes
POST   /volumes
GET    /volumes/{name}
DELETE /volumes/{name}
```

Pass `volumes` when creating a container to mount an existing named volume:

```json
{
  "name": "demo",
  "image": "alpine",
  "command": ["/bin/sleep", "300"],
  "volumes": [{"name": "app-data", "target": "/data"}]
}
```

```powershell
wsl -d Ubuntu -u root --exec systemctl status vcontainer-api --no-pager
wsl -d Ubuntu -u root --exec journalctl -u vcontainer-api -n 50 --no-pager
```

Open `http://localhost:8010/docs` to test it. After changing API sources, rerun
the installer to update the Linux copy and restart the service.

This service alone does not keep WSL alive. If WSL stops, the CLI can boot it
and start the API again. No separate keep-alive process is installed here.
