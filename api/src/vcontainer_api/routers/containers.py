import asyncio
import re
import subprocess

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..dependencies import read_runtime, validate_name
from ..schemas import (
    ContainerCreate,
    ResourceUpdate,
)
from ..services import runtime
from ..services.metrics import metric_data
from ..services.streaming import server_event
from ..supervisor import container_tasks, monitor_container, reserve_bridge_ip

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get("")
def containers():
    return {"containers": read_runtime(runtime.get_containers)}


@router.post("", status_code=202)
async def create_container(request: ContainerCreate):
    if (request.cpu_quota is None) != (request.cpu_period is None):
        raise HTTPException(422, "CPU quota and period must be provided together")
    if (request.network is None) != (request.ip is None):
        raise HTTPException(
            422, "Bridge network and IP address must be provided together"
        )
    host_ports = [mapping.host_port for mapping in request.ports]
    if len(host_ports) != len(set(host_ports)):
        raise HTTPException(422, "Published host ports must be unique")
    if request.command is not None and any(
        not argument or "\0" in argument or len(argument) > 4096
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
            raise HTTPException(
                422, "Volume targets must be unique safe absolute paths"
            )
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
            raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "name": request.name,
        "status": "starting",
    }


@router.get("/{name}")
def container(name: str):
    validate_name(name)
    data = read_runtime(runtime.get_container, name)

    if data.get("status") == "unknown":
        raise HTTPException(404, "Container not found")

    return data


@router.get("/{name}/metrics")
def metrics(name: str):
    return metric_data(container(name))


@router.patch("/{name}/resources")
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


@router.get("/{name}/metrics/stream")
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

                    yield server_event("metrics", payload)

                except runtime.ResourceNotFoundError as error:
                    yield server_event("error", {"message": str(error)})
                    return

                except (
                    RuntimeError,
                    OSError,
                    subprocess.TimeoutExpired,
                ) as error:
                    yield server_event("error", {"message": str(error)})
                    return

                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{name}/logs")
def logs(name: str):
    container(name)

    return {
        "name": name,
        "output": read_runtime(runtime.get_logs, name),
    }


@router.get("/{name}/logs/stream")
async def stream_logs(name: str):
    validate_name(name)

    try:
        await asyncio.to_thread(runtime.get_container, name)
    except runtime.ResourceNotFoundError as error:
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


@router.get("/{name}/processes")
def processes(name: str):
    validate_name(name)
    return {
        "name": name,
        "processes": read_runtime(runtime.get_processes, name),
    }


@router.post("/{name}/start", status_code=202)
async def start_container(name: str):
    validate_name(name)
    try:
        data = await asyncio.to_thread(runtime.get_container, name)
    except runtime.ResourceNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise HTTPException(503, str(error)) from error
    if data.get("status") == "running" or name in container_tasks:
        raise HTTPException(409, "Container is already running")

    task = asyncio.create_task(monitor_container(name))
    container_tasks[name] = task
    return {"name": name, "status": "starting"}


@router.post("/{name}/stop")
def stop_container(name: str):
    validate_name(name)
    return read_runtime(runtime.stop_container, name)


@router.delete("/{name}")
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
            except asyncio.TimeoutError as error:
                raise HTTPException(
                    504,
                    "Container supervisor did not finish after stop",
                ) from error

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
            except (runtime.ConflictError, RuntimeError, OSError) as error:
                remove_error = error
                if attempt == 9:
                    raise
                await asyncio.sleep(0.5)

        raise remove_error

    except runtime.ResourceNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except runtime.ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            504,
            "Container deletion timed out",
        ) from error
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error)) from error
