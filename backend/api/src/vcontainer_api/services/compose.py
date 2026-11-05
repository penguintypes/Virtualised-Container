import json
import os
import re
import subprocess
import tempfile
import shutil
from pathlib import Path

from ..schemas import ContainerCreate

COMPOSE_HELPER = Path(
    os.getenv(
        "VCONTAINER_COMPOSE_HELPER",
        "/opt/vcontainer/libexec/vcontainer-compose",
    )
)
COMPOSE_DIRECTORY = Path(
    os.getenv(
        "VCONTAINER_COMPOSE_DIR",
        "/var/lib/vcontainer/compose",
    )
)
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


class ComposeValidationError(ValueError):
    pass


class ComposeHelperError(RuntimeError):
    pass


class ComposeProjectNotFoundError(FileNotFoundError):
    pass


def parse_compose(source: str) -> dict:
    if not COMPOSE_HELPER.is_file():
        raise ComposeHelperError("Compose helper is not installed")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".yaml",
            delete=False,
        ) as file:
            file.write(source)
            temporary_path = Path(file.name)

        result = subprocess.run(
            [
                str(COMPOSE_HELPER),
                "-format",
                "json",
                "-no-path-resolution",
                str(temporary_path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ComposeHelperError(f"Compose helper failed: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    if result.returncode != 0:
        message = result.stderr.strip() or "Invalid Compose configuration"
        raise ComposeValidationError(message)

    try:
        project = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ComposeHelperError("Compose helper returned invalid JSON") from error

    if not isinstance(project, dict):
        raise ComposeHelperError("Compose helper returned an invalid project")
    services = project.get("services")
    if not isinstance(services, dict) or not services:
        raise ComposeValidationError("Compose project requires services")
    return project


def container_name(project: dict, service_name: str, service: dict) -> str:
    explicit = service.get("container_name")
    if explicit:
        return explicit
    return f"{project.get('name') or 'compose'}-{service_name}"


def project_name(project: dict) -> str:
    name = project.get("name") or "compose"
    validate_project_name(name)
    return name


def validate_project_name(name: str) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise ComposeValidationError(f"Invalid Compose project name: {name}")


def save_project(source: str, project: dict) -> str:
    name = project_name(project)
    directory = COMPOSE_DIRECTORY / name
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    _write_private(directory / "compose.yaml", source)
    _write_private(
        directory / "project.json",
        json.dumps(project, indent=2, sort_keys=True) + "\n",
    )
    return name


def load_project(name: str) -> dict:
    validate_project_name(name)
    path = COMPOSE_DIRECTORY / name / "project.json"
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ComposeProjectNotFoundError(
            f"Compose project not found: {name}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ComposeHelperError(
            f"Could not load Compose project {name}: {error}"
        ) from error
    if not isinstance(project, dict):
        raise ComposeHelperError(f"Stored Compose project is invalid: {name}")
    return project


def load_source(name: str) -> str:
    validate_project_name(name)
    path = COMPOSE_DIRECTORY / name / "compose.yaml"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ComposeProjectNotFoundError(
            f"Compose project not found: {name}"
        ) from error
    except OSError as error:
        raise ComposeHelperError(
            f"Could not load Compose YAML for {name}: {error}"
        ) from error

def remove_project(name: str) -> None:
    validate_project_name(name)
    directory = COMPOSE_DIRECTORY / name

    if not directory.is_dir():
        raise ComposeProjectNotFoundError(
            f"Compose project not found: {name}"
        )

    shutil.rmtree(directory)

def list_project_names() -> list[str]:
    if not COMPOSE_DIRECTORY.is_dir():
        return []
    try:
        return sorted(
            path.name
            for path in COMPOSE_DIRECTORY.iterdir()
            if path.is_dir()
            and NAME_PATTERN.fullmatch(path.name)
            and (path / "project.json").is_file()
        )
    except OSError as error:
        raise ComposeHelperError(
            f"Could not list Compose projects: {error}"
        ) from error


def _write_private(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            descriptor = -1
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def container_request(
    project: dict,
    service_name: str,
    service: dict,
    volume_names: dict[str, str],
) -> ContainerCreate:
    if "image" not in service or not service["image"]:
        raise ComposeValidationError(
            f"Compose service requires an image: {service_name}"
        )

    payload = {
        "name": container_name(project, service_name, service),
        "image": service["image"],
        "environment": {
            key: "" if value is None else str(value)
            for key, value in service.get("environment", {}).items()
        },
        "volumes": [],
        "ports": [],
    }

    command = service.get("command")
    if isinstance(command, str):
        payload["command"] = ["/bin/sh", "-c", command]
    elif command:
        payload["command"] = list(command)

    limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
    memory = service.get("mem_limit") or limits.get("memory")
    pids = service.get("pids_limit") or limits.get("pids")
    cpus = service.get("cpus") or limits.get("cpus")
    if memory:
        payload["memory_max"] = str(memory).upper()
    if pids:
        payload["pids_max"] = int(pids)
    if cpus:
        payload["cpu_period"] = 100_000
        payload["cpu_quota"] = round(float(cpus) * 100_000)

    for volume in service.get("volumes", []):
        source = volume.get("source")
        target = volume.get("target")
        mount_type = volume.get("type")
        read_only = bool(volume.get("read_only", False))

        if not source or not target:
            raise ComposeValidationError(
                f"Invalid mount configuration: {service_name}"
            )

        if mount_type == "volume":
            payload["volumes"].append({
                "type": "volume",
                "name": volume_names.get(source, source),
                "target": target,
                "read_only": read_only,
            })
        elif mount_type == "bind":
            payload["volumes"].append({
                "type": "bind",
                "source": source,
                "target": target,
                "read_only": read_only,
            })
        else:
            raise ComposeValidationError(
                f"Unsupported mount type: {mount_type}"
            )

    for port in service.get("ports", []):
        published = port.get("published")
        if port.get("protocol", "tcp") != "tcp" or not published:
            raise ComposeValidationError(
                f"Only published TCP ports are supported: {service_name}"
            )
        payload["ports"].append(
            {
                "host_port": int(published),
                "container_port": int(port["target"]),
            }
        )

    networks = service.get("networks", {})
    if isinstance(networks, dict):
        for network in networks.values():
            if not isinstance(network, dict):
                continue
            address = network.get("ipv4_address")
            if address:
                payload["network"] = "bridge"
                payload["ip"] = address
                break

    return ContainerCreate.model_validate(payload)


def service_order(project: dict) -> list[tuple[str, dict]]:
    services = project["services"]
    states = {}
    ordered = []

    def visit(name: str) -> None:
        if states.get(name) == "done":
            return
        if states.get(name) == "visiting":
            raise ComposeValidationError(
                f"Circular Compose dependency involving: {name}"
            )
        if name not in services:
            raise ComposeValidationError(f"Unknown Compose dependency: {name}")

        states[name] = "visiting"
        dependencies = services[name].get("depends_on", {})
        for dependency in dependencies:
            visit(dependency)
        states[name] = "done"
        ordered.append((name, services[name]))

    for name in services:
        visit(name)
    return ordered


def volume_names(project: dict) -> dict[str, str]:
    return {
        name: (configuration or {}).get("name") or name
        for name, configuration in project.get("volumes", {}).items()
    }


def validated_requests(project: dict) -> list[ContainerCreate]:
    names = volume_names(project)
    return [
        container_request(project, service_name, service, names)
        for service_name, service in service_order(project)
    ]
