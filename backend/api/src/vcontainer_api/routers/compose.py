import asyncio
from contextlib import suppress

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..dependencies import read_runtime
from ..schemas import ComposeRequest, ContainerCreate, VolumeCreate
from ..services import runtime
from ..services.compose import (
    ComposeHelperError,
    ComposeProjectNotFoundError,
    ComposeValidationError,
    list_project_names,
    load_source,
    parse_compose,
    project_name,
    save_project,
    service_order,
    validated_requests,
    volume_names,
)
from ..services.compose import load_project as load_saved_project
from ..services.compose import remove_project
from .containers import (
    create_container,
    remove_container,
    start_container,
    stop_container,
)
from .volumes import create_volume

router = APIRouter(prefix="/compose", tags=["compose"])


def load_project(source: str) -> tuple[dict, list[ContainerCreate]]:
    try:
        project = parse_compose(source)
        return project, validated_requests(project)
    except ComposeValidationError as error:
        raise HTTPException(422, str(error)) from error
    except ComposeHelperError as error:
        raise HTTPException(503, str(error)) from error
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise HTTPException(422, str(error)) from error


def stored_project(name: str) -> tuple[dict, list[ContainerCreate]]:
    try:
        project = load_saved_project(name)
        return project, validated_requests(project)
    except ComposeProjectNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except ComposeValidationError as error:
        raise HTTPException(422, str(error)) from error
    except ComposeHelperError as error:
        raise HTTPException(503, str(error)) from error
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise HTTPException(422, str(error)) from error


async def current_containers() -> dict[str, dict]:
    items = await asyncio.to_thread(read_runtime, runtime.get_containers)
    return {item["name"]: item for item in items}


def project_view(
    name: str,
    project: dict,
    containers: list[ContainerCreate],
    current: dict[str, dict],
    yaml_source: str | None = None,
) -> dict:
    service_names = [service_name for service_name, _ in service_order(project)]
    services = []
    running = 0
    missing = 0
    for service_name, container in zip(service_names, containers, strict=True):
        state = current.get(container.name)
        status = "missing" if state is None else state.get("status", "unknown")
        running += status == "running"
        missing += status == "missing"
        services.append(
            {
                "name": service_name,
                "container": container.name,
                "status": status,
            }
        )

    if running == len(services):
        status = "running"
    elif running:
        status = "partial"
    elif missing == len(services):
        status = "missing"
    else:
        status = "stopped"

    result = {
        "name": name,
        "status": status,
        "service_count": len(services),
        "running": running,
        "stopped": len(services) - running - missing,
        "missing": missing,
        "services": services,
    }
    if yaml_source is not None:
        result["yaml"] = yaml_source
    return result


@router.get("")
async def compose_projects():
    current = await current_containers()
    projects = []
    for name in list_project_names():
        project, containers = stored_project(name)
        projects.append(project_view(name, project, containers, current))
    return {"projects": projects}


@router.get("/{name}")
async def compose_project(name: str):
    project, containers = stored_project(name)
    current = await current_containers()
    try:
        source = load_source(name)
    except ComposeProjectNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except ComposeHelperError as error:
        raise HTTPException(503, str(error)) from error
    return project_view(name, project, containers, current, source)


@router.put("/{name}")
async def update_compose_project(name: str, request: ComposeRequest):
    project, containers = load_project(request.yaml)
    parsed_name = project_name(project)
    if parsed_name != name:
        raise HTTPException(
            409,
            f"Compose project name must remain {name}",
        )
    save_project(request.yaml, project)
    current = await current_containers()
    result = project_view(name, project, containers, current, request.yaml)
    result["applied"] = False
    return result


@router.post("/validate")
def validate_compose(request: ComposeRequest):
    project, containers = load_project(request.yaml)
    return {
        "valid": True,
        "name": project.get("name") or "compose",
        "services": [container.name for container in containers],
    }


@router.post("/up", status_code=202)
async def compose_up(request: ComposeRequest):
    project, containers = load_project(request.yaml)

    for name in volume_names(project).values():
        try:
            create_volume(VolumeCreate(name=name))
        except HTTPException as error:
            if error.status_code != 409:
                raise

    current = await current_containers()
    created = []
    results = []
    try:
        for container in containers:
            existing = current.get(container.name)
            if existing and existing.get("status") == "running":
                results.append({"name": container.name, "status": "running"})
                continue
            if existing:
                result = await start_container(container.name)
            else:
                result = await create_container(container)
                created.append(container.name)
            results.append(result)
    except HTTPException:
        for name in reversed(created):
            with suppress(HTTPException):
                await remove_container(name)
        raise

    name = save_project(request.yaml, project)
    return {
        "name": name,
        "status": "starting",
        "containers": results,
    }
    
@router.post("/{name}/down")
async def compose_down(name: str):
    _, containers = stored_project(name)

    removed = []

    for container in reversed(containers):
        try:
            await remove_container(container.name)
            removed.append(container.name)
        except HTTPException as error:
            if error.status_code != 404:
                raise

    remove_project(name)

    return {
        "name": name,
        "status": "removed",
        "containers": removed,
        "volumes_preserved": True,
    }


@router.post("/{name}/start", status_code=202)
async def compose_start(name: str):
    _, containers = stored_project(name)
    current = await current_containers()
    missing = [
        container.name for container in containers if container.name not in current
    ]
    if missing:
        raise HTTPException(
            409,
            f"Compose containers are missing: {', '.join(missing)}. Run up first.",
        )

    results = []
    for container in containers:
        if current[container.name].get("status") == "running":
            results.append({"name": container.name, "status": "running"})
        else:
            results.append(await start_container(container.name))
    return {"name": name, "status": "starting", "containers": results}


@router.post("/{name}/stop")
async def compose_stop(name: str):
    _, containers = stored_project(name)
    current = await current_containers()
    results = []
    for container in reversed(containers):
        existing = current.get(container.name)
        if existing is None:
            results.append({"name": container.name, "status": "missing"})
        elif existing.get("status") == "running":
            await asyncio.to_thread(stop_container, container.name)
            results.append({"name": container.name, "status": "stopped"})
        else:
            results.append({"name": container.name, "status": "stopped"})
    return {"name": name, "status": "stopped", "containers": results}


@router.post("/{name}/restart", status_code=202)
async def compose_restart(name: str):
    await compose_stop(name)
    result = await compose_start(name)
    result["status"] = "restarting"
    return result
