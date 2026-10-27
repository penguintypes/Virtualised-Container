import re
import subprocess
import asyncio
import threading
import time
from contextlib import asynccontextmanager
from ipaddress import IPv4Address
from typing import Literal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, ORJSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
import orjson


container_tasks: dict[str, asyncio.Task] = {}
ip_reservations: set[str] = set()
ip_lock = asyncio.Lock()

from . import runtime
STATIC_DIRECTORY = Path(__file__).with_name("static")


async def restore_runtime_state():
    """Restore host-side services for containers surviving an API restart."""
    try:
        existing = await asyncio.to_thread(runtime.get_containers)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Could not reconcile existing containers: {error}")
        return

    for item in existing:
        if item.get("status") != "running" or not item.get("ports"):
            continue
        try:
            await asyncio.to_thread(runtime.republish_ports, item["name"])
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            print(f"Could not restore ports for {item['name']}: {error}")


@asynccontextmanager
async def lifespan(_app):
    await restore_runtime_state()
    yield

app = FastAPI(
    title="Vcontainer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIRECTORY / "index.html")

metric_samples = {}
metric_lock = threading.Lock()


class VolumeMount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    target: str = Field(min_length=2, max_length=4095)

class PortMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_port: int = Field(ge=1024, le=65535)
    container_port: int = Field(ge=1, le=65535)

class ContainerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    image: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    command: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    hostname: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$",
    )
    memory_max: str | None = Field(
        default=None,
        pattern=r"^(?:max|[1-9][0-9]*[KMG]?)$",
    )
    pids_max: int | None = Field(default=None, ge=1, le=32768)
    cpu_quota: int | None = Field(default=None, ge=1000, le=1000000000)
    cpu_period: int | None = Field(default=None, ge=1000, le=1000000)
    network: Literal["bridge"] | None = None
    ip: IPv4Address | None = None
    volumes: list[VolumeMount] = Field(default_factory=list, max_length=16)
    ports: list[PortMapping] = Field(
        default_factory=list,
        max_length=16,
    )
    environment: dict[str, str] = Field(
        default_factory=dict,
        max_length=128,
    )


class ImagePull(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]*$",
    )


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_max: str | None = Field(
        default=None,
        pattern=r"^(?:max|[1-9][0-9]*[KMG]?)$",
    )
    pids_max: int | None = Field(default=None, ge=1, le=32768)
    cpu_quota: int | None = Field(default=None, ge=1000, le=1000000000)
    cpu_period: int | None = Field(default=None, ge=1000, le=1000000)


class VolumeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


def validate_name(name, resource="container"):
    if(
        name in (".","..")
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
    ):
        raise HTTPException(400, f"Invalid {resource} name")

def read_runtime(function, *args):
    try:
        return function(*args)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Runtime request timed out")
    except runtime.ResourceNotFound as error:
        raise HTTPException(404, str(error))
    except runtime.Conflict as error:
        raise HTTPException(409, str(error))
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error))


def metric_data(data):
    def number(value):
        if isinstance(value, int):
            return value
        return int(value) if isinstance(value, str) and value.isdigit() else None

    usage = number(data.get("cpu", {}).get("usage_usec"))
    now = time.monotonic()
    cpu_percent = None
    with metric_lock:
        previous = metric_samples.get(data["name"])
        if usage is not None:
            metric_samples[data["name"]] = (now, usage)
    if previous is not None and usage is not None:
        seconds = now - previous[0]
        delta = usage - previous[1]
        if seconds > 0 and delta >= 0:
            cpu_percent = round(delta / (seconds * 10000), 2)

    return {
        "name": data["name"],
        "status": data.get("status"),
        "cpu_usage_usec": usage,
        "cpu_percent": cpu_percent,
        "memory_used_bytes": number(data.get("memory_current")),
        "memory_limit_bytes": number(data.get("memory_max")),
        "process_count": number(data.get("pids_current")),
        "process_limit": number(data.get("pids_max")),
        "network_rx_bytes": number(data.get("network", {}).get("rx_bytes")) or 0,
        "network_tx_bytes": number(data.get("network", {}).get("tx_bytes")) or 0,
        "block_read_bytes": number(data.get("block_io", {}).get("rbytes")) or 0,
        "block_write_bytes": number(data.get("block_io", {}).get("wbytes")) or 0,
        "block_read_operations": number(data.get("block_io", {}).get("rios")) or 0,
        "block_write_operations": number(data.get("block_io", {}).get("wios")) or 0,
        "cpu_limit": data.get("cpu_max"),
    }


async def reserve_bridge_ip(preferred: str | None = None) -> str:
    """Reserve one address until the container launch has finished."""
    async with ip_lock:
        try:
            containers = await asyncio.to_thread(runtime.get_containers)
        except subprocess.TimeoutExpired as error:
            raise HTTPException(504, "Runtime request timed out") from error
        except (RuntimeError, OSError) as error:
            raise HTTPException(503, str(error)) from error

        used = {
            str(container["network_address"])
            for container in containers
            if container.get("network_address")
        }
        used.update(ip_reservations)

        if preferred is not None:
            if preferred in used:
                raise HTTPException(409, f"Bridge address is already in use: {preferred}")
            ip_reservations.add(preferred)
            return preferred

        for host in range(2, 255):
            address = f"10.88.0.{host}"
            if address not in used:
                ip_reservations.add(address)
                return address

    raise HTTPException(409, "No bridge addresses are available")

async def monitor_container(
    name: str,
    payload: dict | None = None,
) -> None:
    started = False

    try:
        if payload is None:
            process = await runtime.launch_saved_container(name)
        else:
            process = await runtime.launch_container(payload)

        if isinstance(process, subprocess.Popen):
            communication = asyncio.create_task(
                asyncio.to_thread(process.communicate)
            )
        else:
            communication = asyncio.create_task(process.communicate())

        for _ in range(100):
            if communication.done():
                break
            try:
                data = await asyncio.to_thread(runtime.get_container, name)
                if data.get("status") == "running":
                    await asyncio.to_thread(runtime.record_started, name)
                    if payload is None:
                        await asyncio.to_thread(runtime.republish_ports, name)
                    elif payload.get("ports"):
                        address = data.get("network_address") or payload.get("ip")
                        if not address:
                            raise RuntimeError(
                                "Published ports require a bridge IP"
                            )
                        await asyncio.to_thread(
                            runtime.publish_ports,
                            name,
                            address,
                            payload["ports"],
                        )
                    started = True
                    break
            except runtime.ResourceNotFound:
                pass
            await asyncio.sleep(0.05)

        stdout, stderr = await communication

        exit_code = process.returncode
        if exit_code is not None and exit_code < 0:
            exit_code = 128 - exit_code

        try:
            await asyncio.to_thread(runtime.record_exit, name, exit_code)
        except runtime.ResourceNotFound:
            if exit_code == 0:
                raise

        if stdout:
            print(stdout.decode(errors="replace").strip())

        if stderr:
            print(stderr.decode(errors="replace").strip())

        if exit_code != 0 and not started:
            message = stderr.decode(errors="replace").strip()
            raise RuntimeError(message or f"Container launch failed ({exit_code})")

        print(f"Container {name} exited with code {exit_code}")

    except Exception as error:
        print(f"Failed to supervise {name}: {error!r}")
        if not started:
            raise

    finally:
        if payload is not None and payload.get("ip"):
            async with ip_lock:
                ip_reservations.discard(str(payload["ip"]))
        container_tasks.pop(name, None)

@app.get("/health")
def health():
    return {"service": "vcontainer", "status": "ok"}

@app.get("/system/disk")
def disk_usage():
    return read_runtime(runtime.get_disk_usage)


@app.get("/images")
def images():
    return {"images": read_runtime(runtime.get_images)}


@app.post("/images/pull")
def pull_image(request: ImagePull):
    return read_runtime(
        runtime.pull_image,
        request.name,
        request.reference,
    )


@app.delete("/images/{name}")
def delete_image(name: str):
    validate_name(name, "image")
    return read_runtime(runtime.delete_image, name)


@app.get("/volumes")
def volumes():
    return {"volumes": read_runtime(runtime.run_volume, "list")}


@app.post("/volumes", status_code=201)
def create_volume(request: VolumeCreate):
    return read_runtime(runtime.run_volume, "create", request.name)


@app.get("/volumes/{name}")
def inspect_volume(name: str):
    validate_name(name, "volume")
    return read_runtime(runtime.run_volume, "inspect", name)


@app.delete("/volumes/{name}")
def remove_volume(name: str):
    validate_name(name, "volume")
    return read_runtime(runtime.run_volume, "remove", name)

@app.get("/containers")
def containers():
    return  {
        "containers": read_runtime(runtime.get_containers)
    }


@app.post("/containers", status_code=202)
async def create_container(request: ContainerCreate):
    if (request.cpu_quota is None) != (request.cpu_period is None):
        raise HTTPException(422, "CPU quota and period must be provided together")
    if (request.network is None) != (request.ip is None):
        raise HTTPException(422, "Bridge network and IP address must be provided together")
    host_ports = [mapping.host_port for mapping in request.ports]
    if len(host_ports) != len(set(host_ports)):
        raise HTTPException(422, "Published host ports must be unique")
    if request.command is not None and any(
        not argument
        or "\0" in argument
        or len(argument) > 4096
        for argument in request.command
    ):
        raise HTTPException(
            422,
            "Command arguments must be non-empty and at most 4096 characters",
        )
    environment_name = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for name, value in request.environment.items():
        if not environment_name.fullmatch(name):
            raise HTTPException(
                422,
                f"Invalid environment variable name: {name}",
            )
        if "\0" in value or len(value) > 8192:
            raise HTTPException(
                422,
                f"Invalid value for environment variable: {name}",
            )
    targets = set()
    for volume in request.volumes:
        parts = volume.target[1:].split("/") if volume.target.startswith("/") else []
        if (
            not parts
            or volume.target.endswith("/")
            or any(part in ("", ".", "..") for part in parts)
            or volume.target in targets
        ):
            raise HTTPException(422, "Volume targets must be unique safe absolute paths")
        targets.add(volume.target)

    if request.name in container_tasks:
        raise HTTPException(
            status_code=409,
            detail="Container is already being supervised",
        )

    payload = request.model_dump(exclude_none=True, mode="json")
    if request.network == "bridge":
        payload["ip"] = await reserve_bridge_ip(str(request.ip))
    elif request.ports:
        payload["network"] = "bridge"
        payload["ip"] = await reserve_bridge_ip()

    task = asyncio.create_task(monitor_container(request.name, payload))
    container_tasks[request.name] = task

    # Give the helper a brief opportunity to report an immediate error.
    await asyncio.sleep(0.1)

    if task.done():
        try:
            await task
        except Exception as error:
            raise HTTPException(status_code=503, detail=str(error))

    return {
        "name": request.name,
        "status": "starting",
    }

@app.get("/containers/{name}")
def container(name: str):
    validate_name(name)
    data = read_runtime(runtime.get_container, name)

    if data.get("status") == "unknown":
        raise HTTPException(404, "Container not found")
    
    return data

@app.get("/containers/{name}/metrics")
def metrics(name: str):
    return metric_data(container(name))


@app.patch("/containers/{name}/resources")
def update_container_resources(name: str, request: ResourceUpdate):
    validate_name(name)
    current = read_runtime(runtime.get_container, name)
    if current.get("status") == "running":
        raise HTTPException(409, "Stop the container before editing resources")
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(422, "At least one resource limit is required")
    if (request.cpu_quota is None) != (request.cpu_period is None):
        raise HTTPException(422, "CPU quota and period must be provided together")
    return read_runtime(
        runtime.update_resources,
        name,
        payload,
    )


@app.get("/containers/{name}/metrics/stream")
async def stream_metrics(
    name: str,
    request: Request,
    interval: float = Query(default=1.0, ge=0.25, le=60.0),
):
    validate_name(name)

    async def events():
        try:
            while not await request.is_disconnected():
                try:
                    data = await asyncio.to_thread(
                        runtime.get_container,
                        name,
                    )
                    payload = metric_data(data)

                    yield (
                        b"event: metrics\n"
                        + b"data: "
                        + orjson.dumps(payload)
                        + b"\n\n"
                    )

                except runtime.ResourceNotFound as error:
                    yield (
                        b"event: error\n"
                        + b"data: "
                        + orjson.dumps({"message": str(error)})
                        + b"\n\n"
                    )
                    return

                except (
                    RuntimeError,
                    OSError,
                    subprocess.TimeoutExpired,
                ) as error:
                    yield (
                        b"event: error\n"
                        + b"data: "
                        + orjson.dumps({"message": str(error)})
                        + b"\n\n"
                    )
                    return

                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            return


@app.get("/containers/{name}/logs")
def logs(name: str):
    container(name)

    return {
        "name": name,
        "output": read_runtime(runtime.get_logs, name),
    }


@app.get("/containers/{name}/logs/stream")
async def stream_logs(name: str):
    validate_name(name)

    try:
        await asyncio.to_thread(runtime.get_container, name)
    except runtime.ResourceNotFound as error:
        raise HTTPException(404, str(error)) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "Runtime request timed out") from error
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error)) from error

    return StreamingResponse(
        runtime.stream_logs(name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/containers/{name}/processes")
def processes(name: str):
    validate_name(name)
    return {
        "name": name,
        "processes": read_runtime(runtime.get_processes, name),
    }


@app.post("/containers/{name}/start", status_code=202)
async def start_container(name: str):
    validate_name(name)
    try:
        data = await asyncio.to_thread(runtime.get_container, name)
    except runtime.ResourceNotFound as error:
        raise HTTPException(404, str(error)) from error
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise HTTPException(503, str(error)) from error
    if data.get("status") == "running" or name in container_tasks:
        raise HTTPException(409, "Container is already running")

    task = asyncio.create_task(monitor_container(name))
    container_tasks[name] = task
    return {"name": name, "status": "starting"}


@app.post("/containers/{name}/stop")
def stop_container(name: str):
    validate_name(name)
    return read_runtime(runtime.stop_container, name)


@app.delete("/containers/{name}")
async def remove_container(name: str):
    validate_name(name)

    try:
        data = await asyncio.to_thread(runtime.get_container, name)
        stop_error = None

        if data.get("status") == "running":
            try:
                await asyncio.to_thread(runtime.stop_container, name)
            except RuntimeError as error:
                # The foreground runtime and stop helper can race to remove
                # the empty cgroup. Confirm the resulting state before
                # deciding whether stop actually failed.
                stop_error = error

        task = container_tasks.get(name)

        if task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=15,
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    504,
                    "Container supervisor did not finish after stop",
                )

        if stop_error is not None:
            for attempt in range(20):
                current = await asyncio.to_thread(runtime.get_container, name)
                if current.get("status") != "running":
                    break
                if attempt == 19:
                    raise stop_error
                await asyncio.sleep(0.25)

        # Cgroup release can trail process exit briefly, especially when WSL
        # is restricted to one CPU. Retry only after the container is known
        # to be stopped; this never retries deletion of a running container.
        remove_error = None
        for attempt in range(10):
            try:
                return await asyncio.to_thread(runtime.remove_container, name)
            except (runtime.Conflict, RuntimeError, OSError) as error:
                remove_error = error
                if attempt == 9:
                    raise
                await asyncio.sleep(0.5)

        raise remove_error

    except runtime.ResourceNotFound as error:
        raise HTTPException(404, str(error)) from error
    except runtime.Conflict as error:
        raise HTTPException(409, str(error)) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            504,
            "Container deletion timed out",
        ) from error
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error)) from error

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
