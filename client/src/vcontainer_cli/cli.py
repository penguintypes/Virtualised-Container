import http.client
import json
import os
import subprocess
import sys
import time

from .api import api_error, api_request, server_events
from .config import (
    API_HOST,
    API_PORT,
    ENGINE_RUN,
    KEEP_ALIVE_API,
    START_API,
    WSL_DISTRO,
    WSL_USER,
)
from .errors import VcontainerApiError
from .parsing import parse_run

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def api_get(path, distro):
    ensure_backend(distro)
    return api_request(path, 30)


def backend_ready():
    try:
        data = api_request("/health", 0.5)

        return (
            isinstance(data, dict)
            and data.get("service") == "vcontainer"
            and data.get("status") == "ok"
        )
    except (OSError, RuntimeError, http.client.HTTPException):
        return False


def ensure_wsl_keepalive(distro):
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "wsl.exe",
            "-d",
            distro,
            "-u",
            "root",
            "--exec",
            *KEEP_ALIVE_API,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )


def ensure_backend(distro):
    ensure_wsl_keepalive(distro)
    if backend_ready():
        return

    print("Starting Vcontainer...", file=sys.stderr)

    try:
        subprocess.run(
            [
                "wsl.exe",
                "-d",
                distro,
                "-u",
                "root",
                "--exec",
                *START_API,
            ],
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"Could not start backend: {error}") from error

    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        if backend_ready():
            return
        time.sleep(0.2)

    raise RuntimeError(
        "Backend did not become ready. Check journalctl -u vcontainer-api"
    )


def list_images(distro):
    data = api_get("/images", distro)

    print(f"{'IMAGE':<16} ROOTFS")

    for image in data["images"]:
        print(f"{image['name']:<16} {image['rootfs']}")

    return 0


def list_containers(distro):
    data = api_get("/containers", distro)
    print(f"{'NAME':<20} {'STATUS':<10} {'MAIN PID':<12} COMMAND")

    for container in data["containers"]:
        pids = container.get("host_pids", [])
        main_pid = str(pids[0]) if pids else "-"
        command = " ".join(container.get("command", [])) or "-"
        print(
            f"{container['name']:<20} {container['status']:<10} "
            f"{main_pid:<12} {command}"
        )

    return 0


def inspect_container(name, distro):
    data = api_get(f"/containers/{name}", distro)
    print(json.dumps(data, indent=2))
    return 0


def show_logs(name, distro):
    data = api_get(f"/containers/{name}/logs", distro)
    output = data.get("output", "")
    if output:
        print(output)
    return 0


def follow_logs(name, distro):
    ensure_backend(distro)
    connection = http.client.HTTPConnection(API_HOST, API_PORT, timeout=None)
    try:
        connection.request("GET", f"/containers/{name}/logs/stream")
        response = connection.getresponse()
        if response.status >= 400:
            raise api_error(response)

        for event_name, event_data in server_events(response):
            if event_name not in ("log", "error"):
                continue

            is_error = event_name == "error"
            fallback = "Log stream failed" if is_error else ""
            output = sys.stderr if is_error else sys.stdout
            print(event_data.get("message", fallback), file=output, flush=True)

            if is_error:
                return 1
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        connection.close()


def load_compose(filename):
    directory = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    executable = os.path.join(
        directory,
        "vendor",
        "compose",
        "compose.exe",
    )

    if not os.path.isfile(executable):
        raise RuntimeError(f"Compose executable not found: {executable}")

    try:
        result = subprocess.run(
            [
                executable,
                "-format",
                "json",
                os.path.abspath(filename),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"Compose command failed: {error}") from error

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Invalid Compose configuration"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Compose executable returned invalid JSON"
        ) from error


def compose_container_name(project, service_name, service):
    explicit = service.get("container_name")
    if explicit:
        return explicit

    project_name = project.get("name") or "compose"
    name = f"{project_name}-{service_name}"
    valid_characters = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
    )
    if (
        len(name) > 63
        or not name[0].isalnum()
        or any(character not in valid_characters for character in name)
    ):
        raise ValueError(f"Invalid generated container name: {name}")
    return name


def compose_payload(project, service_name, service, volume_names=None):
    volume_names = volume_names or {}
    image = service.get("image")
    if not image:
        raise ValueError(f"Compose service requires an image: {service_name}")

    payload = {
        "name": compose_container_name(project, service_name, service),
        "image": image,
        "environment": {
            key: "" if value is None else str(value)
            for key, value in service.get("environment", {}).items()
        },
        "volumes": [],
        "ports": [],
    }

    command = service.get("command")
    if command:
        if isinstance(command, str):
            payload["command"] = ["/bin/sh", "-c", command]
        else:
            payload["command"] = list(command)

    memory_limit = service.get("mem_limit")
    pid_limit = service.get("pids_limit")
    cpu_limit = service.get("cpus")
    deploy_limits = (
        service.get("deploy", {}).get("resources", {}).get("limits", {})
    )
    memory_limit = memory_limit or deploy_limits.get("memory")
    pid_limit = pid_limit or deploy_limits.get("pids")
    cpu_limit = cpu_limit or deploy_limits.get("cpus")

    if memory_limit:
        payload["memory_max"] = str(memory_limit).upper()
    if pid_limit:
        payload["pids_max"] = int(pid_limit)
    if cpu_limit:
        payload["cpu_period"] = 100000
        payload["cpu_quota"] = round(float(cpu_limit) * 100000)

    for volume in service.get("volumes", []):
        source = volume.get("source")
        if volume.get("type") != "volume" or not source:
            raise ValueError("Only named Compose volumes are supported")
        payload["volumes"].append(
            {
                "name": volume_names.get(source, source),
                "target": volume["target"],
            }
        )

    for port in service.get("ports", []):
        if port.get("protocol", "tcp") != "tcp" or not port.get("published"):
            raise ValueError("Only published TCP Compose ports are supported")
        payload["ports"].append(
            {
                "host_port": int(port["published"]),
                "container_port": int(port["target"]),
            }
        )

    for network in service.get("networks", {}).values():
        if not isinstance(network, dict):
            continue
        address = network.get("ipv4_address")
        if not address:
            continue
        payload["network"] = "bridge"
        payload["ip"] = address
        break

    return payload


def ensure_compose_volumes(project):
    for name, configuration in project.get("volumes", {}).items():
        configuration = configuration or {}
        volume_name = configuration.get("name") or name
        try:
            api_request(
                "/volumes",
                30,
                method="POST",
                payload={"name": volume_name},
            )
        except VcontainerApiError as error:
            if error.status != 409:
                raise


def compose_service_order(project):
    services = project.get("services", {})
    states = {}
    ordered = []

    def visit(name):
        if states.get(name) == "done":
            return
        if states.get(name) == "visiting":
            raise ValueError(f"Circular Compose dependency involving: {name}")
        if name not in services:
            raise ValueError(f"Unknown Compose dependency: {name}")

        states[name] = "visiting"
        for dependency in services[name].get("depends_on", {}):
            visit(dependency)
        states[name] = "done"
        ordered.append((name, services[name]))

    for name in services:
        visit(name)
    return ordered


def compose_up(filename, distro, service_name=None, replace=False):
    ensure_backend(distro)
    project = load_compose(filename)
    ensure_compose_volumes(project)
    volume_names = {
        name: (configuration or {}).get("name") or name
        for name, configuration in project.get("volumes", {}).items()
    }
    current = {
        container["name"]: container
        for container in api_request("/containers", 30).get("containers", [])
    }

    services = compose_service_order(project)
    if service_name is not None:
        services = [
            (name, service)
            for name, service in services
            if name == service_name
        ]
        if not services:
            raise ValueError(f"Unknown Compose service: {service_name}")

    created = []
    completed = False
    try:
        for current_service_name, service in services:
            created_name = start_compose_service(
                project,
                current_service_name,
                service,
                volume_names,
                current,
                replace=replace,
            )
            if created_name is not None:
                created.append(created_name)
        completed = True
    finally:
        if not completed:
            rollback_containers(created)
    return 0


def start_compose_service(
    project,
    service_name,
    service,
    volume_names,
    current,
    replace=False,
):
    payload = compose_payload(project, service_name, service, volume_names)
    name = payload["name"]
    existing = current.get(name)

    if existing is not None and replace:
        api_request(f"/containers/{name}", 60, method="DELETE")
        current.pop(name)
        print(f"{name}: replacing")
        existing = None

    if existing is not None:
        if existing.get("status") == "running":
            print(f"{name}: already running")
            return None
        result = api_request(
            f"/containers/{name}/start",
            60,
            method="POST",
        )
        print(result.get("message") or f"{name}: starting")
        return None

    result = api_request(
        "/containers",
        60,
        method="POST",
        payload=payload,
    )
    current[result["name"]] = result
    print(f"{result['name']}: {result['status']}")
    return result["name"]


def rollback_containers(container_names):
    for name in reversed(container_names):
        try:
            api_request(f"/containers/{name}", 60, method="DELETE")
            print(f"{name}: rolled back", file=sys.stderr)
        except (
            OSError,
            http.client.HTTPException,
            RuntimeError,
        ) as rollback_error:
            print(
                f"{name}: rollback failed: {rollback_error}",
                file=sys.stderr,
            )


def compose_down(filename, distro):
    ensure_backend(distro)
    project = load_compose(filename)

    for service_name, service in reversed(compose_service_order(project)):
        name = compose_container_name(project, service_name, service)
        try:
            api_request(f"/containers/{name}", 30, method="DELETE")
            print(f"{name}: removed")
        except RuntimeError as error:
            print(f"{name}: {error}", file=sys.stderr)
    return 0


def compose_stop(filename, distro):
    ensure_backend(distro)
    project = load_compose(filename)
    current = {
        item["name"]: item
        for item in api_request("/containers", 30).get("containers", [])
    }

    for service_name, service in reversed(compose_service_order(project)):
        name = compose_container_name(project, service_name, service)
        container = current.get(name)
        if container is None:
            print(f"{name}: not created")
        elif container.get("status") != "running":
            print(f"{name}: already stopped")
        else:
            result = api_request(
                f"/containers/{name}/stop",
                60,
                method="POST",
            )
            print(result.get("message") or f"{name}: stopped")
    return 0


def compose_start(filename, distro):
    ensure_backend(distro)
    project = load_compose(filename)
    ordered = compose_service_order(project)
    current = {
        item["name"]: item
        for item in api_request("/containers", 30).get("containers", [])
    }
    service_names = [
        compose_container_name(project, service_name, service)
        for service_name, service in ordered
    ]
    missing = [name for name in service_names if name not in current]
    if missing:
        raise RuntimeError(
            "Compose containers have not been created: "
            + ", ".join(missing)
            + ". Run compose up first."
        )

    for name in service_names:
        if current[name].get("status") == "running":
            print(f"{name}: already running")
            continue
        result = api_request(
            f"/containers/{name}/start",
            60,
            method="POST",
        )
        print(result.get("message") or f"{name}: starting")
    return 0


def compose_ps(filename, distro):
    ensure_backend(distro)
    project = load_compose(filename)
    current = {
        item["name"]: item
        for item in api_request("/containers", 30).get("containers", [])
    }

    print(f"{'SERVICE':<20} {'CONTAINER':<32} STATUS")
    for service_name, service in compose_service_order(project):
        name = compose_container_name(project, service_name, service)
        status = current.get(name, {}).get("status", "not-created")
        print(f"{service_name:<20} {name:<32} {status}")
    return 0


def container_action(action, name, distro):
    routes = {
        "start": (f"/containers/{name}/start", "POST", 30),
        "stop": (f"/containers/{name}/stop", "POST", 60),
        "rm": (f"/containers/{name}", "DELETE", 30),
    }
    path, method, timeout = routes[action]
    ensure_backend(distro)
    data = api_request(path, timeout, method=method)
    print(data.get("message") or f"{action}: {name}")
    return 0


def compose_up_options(arguments):
    if len(arguments) == 3:
        return arguments[2], None, False
    if len(arguments) == 6 and arguments[3] == "--service":
        if arguments[5] != "--replace":
            raise ValueError("Expected --replace after the service name")
        return arguments[2], arguments[4], True
    raise ValueError(
        "Usage: vcontainer compose up FILE [--service SERVICE --replace]"
    )


def compose_command(action, filename, distro):
    commands = {
        "up": compose_up,
        "start": compose_start,
        "stop": compose_stop,
        "down": compose_down,
        "ps": compose_ps,
    }
    if action == "config":
        print(json.dumps(load_compose(filename), indent=2))
        return 0
    if action not in commands:
        return None
    return commands[action](filename, distro)


def main():
    distro = WSL_DISTRO
    arguments = sys.argv[1:]

    if arguments == ["list"]:
        return list_images(distro)
    if arguments == ["ps"]:
        return list_containers(distro)
    if len(arguments) == 2 and arguments[0] == "inspect":
        return inspect_container(arguments[1], distro)
    if len(arguments) == 2 and arguments[0] in ("log", "logs"):
        return show_logs(arguments[1], distro)
    if (
        len(arguments) == 3
        and arguments[0] in ("log", "logs")
        and arguments[1] == "-f"
    ):
        return follow_logs(arguments[2], distro)
    if arguments and arguments[0] == "run":
        ensure_backend(distro)
        payload = parse_run(arguments)
        data = api_request(
            "/containers",
            60,
            method="POST",
            payload=payload,
        )
        print(f"container {data['name']} {data['status']}")
        return 0
    if len(arguments) == 2 and arguments[0] in ("start", "stop", "rm"):
        return container_action(arguments[0], arguments[1], distro)

    if arguments[:2] == ["compose", "up"]:
        filename, service_name, replace = compose_up_options(arguments)
        return compose_up(filename, distro, service_name, replace)

    if len(arguments) == 3 and arguments[0] == "compose":
        result = compose_command(arguments[1], arguments[2], distro)
        if result is not None:
            return result

    user = WSL_USER
    directory = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return subprocess.call(
        [
            "wsl.exe",
            "-d",
            distro,
            "-u",
            "root",
            "--cd",
            directory,
            "--exec",
            "env",
            f"SUDO_USER={user}",
            *ENGINE_RUN,
            *arguments,
        ]
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        http.client.HTTPException,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"vcontainer: {error}", file=sys.stderr)
        sys.exit(1)
