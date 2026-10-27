import os
import subprocess
import sys
import json
import http.client

import time


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


API_HOST = "127.0.0.1"
API_PORT = 8010


def api_request(path, timeout, method="GET", payload=None):
    connection = http.client.HTTPConnection(API_HOST, API_PORT, timeout=timeout)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()

    try:
        data = json.loads(body) if body else {}
    except (TypeError, ValueError) as error:
        raise RuntimeError("Backend returned invalid JSON") from error

    if response.status >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        raise RuntimeError(detail or f"API request failed ({response.status})")

    return data


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
    except (OSError, ValueError, RuntimeError, http.client.HTTPException):
        return False


def ensure_wsl_keepalive(distro):
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "wsl.exe", "-d", distro, "-u", "root", "--exec",
            "flock", "-n", "/run/vcontainer-windows-keepalive.lock",
            "sleep", "infinity",
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

    print("Starting Vcontainer....", file=sys.stderr)


    try:
        subprocess.run(
             [
                "wsl.exe", "-d", distro, "-u", "root",
                "--exec", "systemctl", "start", "vcontainer-api",
            ],
            check=True,
            timeout=120,
        )
    except subprocess.SubprocessError as error:
        raise RuntimeError(f"Could not start backend: {error}") from error

    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        if backend_ready():
            return 
        time.sleep(0.2)

    raise RuntimeError(
        "Backend did not become ready. "
        "Check journalctl -u vcontainer-api"
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
            body = response.read()
            try:
                detail = json.loads(body).get("detail")
            except (TypeError, ValueError, AttributeError):
                detail = None
            raise RuntimeError(detail or f"API request failed ({response.status})")

        event = None
        while True:
            line = response.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if text.startswith("event: "):
                event = text[7:]
            elif text.startswith("data: "):
                data = json.loads(text[6:])
                if event == "log":
                    print(data.get("message", ""), flush=True)
                elif event == "error":
                    print(data.get("message", "Log stream failed"), file=sys.stderr)
                    return 1
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        connection.close()


def parse_run(arguments):
    if len(arguments) < 2 or arguments[0] != "run":
        raise ValueError("Use: run IMAGE --name NAME [OPTIONS] -- COMMAND")

    payload = {
        "image": arguments[1],
        "volumes": [],
        "ports": [],
        "environment": {},
    }
    index = 2
    while index < len(arguments) and arguments[index] != "--":
        option = arguments[index]
        if option in ("--detach", "-d"):
            index += 1
            continue
        if option in ("--name", "--hostname", "--memory-max", "--pids-max",
                      "--network", "--ip", "--volume", "-v", "--env", "-e",
                      "--publish", "-p"):
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing value for {option}")
            value = arguments[index + 1]
            index += 2
            if option == "--name":
                payload["name"] = value
            elif option == "--hostname":
                payload["hostname"] = value
            elif option == "--memory-max":
                payload["memory_max"] = value
            elif option == "--pids-max":
                payload["pids_max"] = int(value)
            elif option == "--network":
                payload["network"] = value
            elif option == "--ip":
                payload["ip"] = value
            elif option in ("--volume", "-v"):
                volume, separator, target = value.partition(":")
                if not separator:
                    raise ValueError("Volume must use NAME:/TARGET")
                payload["volumes"].append({"name": volume, "target": target})
            elif option in ("--env", "-e"):
                name, separator, value = value.partition("=")

                if not separator:
                    raise ValueError(
                        "Environment variable must use NAME=VALUE"
                    )

                if not name:
                    raise ValueError(
                        "Environment variable name is missing"
                    )

                payload["environment"][name] = value
            else:
                host, separator, container = value.partition(":")
                if not separator:
                    raise ValueError(
                        "Published port must use HOST_PORT:CONTAINER_PORT"
                    )
                payload["ports"].append({
                    "host_port": int(host),
                    "container_port": int(container),
                })
            continue
        if option == "--cpu-max":
            if index + 2 >= len(arguments):
                raise ValueError("--cpu-max requires QUOTA PERIOD")
            payload["cpu_quota"] = int(arguments[index + 1])
            payload["cpu_period"] = int(arguments[index + 2])
            index += 3
            continue
        raise ValueError(f"Unsupported run option: {option}")

    if index < len(arguments):
        if arguments[index] != "--":
            raise ValueError("Container command must follow --")

        command = arguments[index + 1:]

        if not command:
            raise ValueError("Command is missing after --")

        payload["command"] = command

    if not payload.get("name"):
        raise ValueError("--name is required")
    return payload

def load_compose(filename):
    directory = os.path.dirname(os.path.abspath(__file__))
    executable = os.path.join(
        directory,
        "compose",
        "compose.exe",
    )

    if not os.path.isfile(executable):
        raise RuntimeError(
            f"Compose executable not found: {executable}"
        )

    result = subprocess.run(
        [
            executable,
            "-format", "json",
            os.path.abspath(filename),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or "Invalid Compose configuration"
        )

    try: 
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Compose executable returned invalid JSON"
        ) from error

def compose_config(filename):
    project = load_compose(filename)
    print(json.dumps(project, indent=2))
    return 0


def compose_container_name(project, service_name, service):
    explicit = service.get("container_name")
    if explicit:
        return explicit

    project_name = project.get("name") or "compose"
    name = f"{project_name}-{service_name}"
    if (
        len(name) > 63
        or not name[0].isalnum()
        or any(character not in
               "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
               for character in name)
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
        payload["command"] = (
            ["/bin/sh", "-c", command]
            if isinstance(command, str)
            else list(command)
        )

    for volume in service.get("volumes", []):
        if volume.get("type") != "volume" or not volume.get("source"):
            raise ValueError("Only named Compose volumes are supported")
        payload["volumes"].append({
            "name": volume_names.get(volume["source"], volume["source"]),
            "target": volume["target"],
        })

    for port in service.get("ports", []):
        if port.get("protocol", "tcp") != "tcp" or not port.get("published"):
            raise ValueError("Only published TCP Compose ports are supported")
        payload["ports"].append({
            "host_port": int(port["published"]),
            "container_port": int(port["target"]),
        })

    for network in service.get("networks", {}).values():
        if isinstance(network, dict) and network.get("ipv4_address"):
            payload["network"] = "bridge"
            payload["ip"] = network["ipv4_address"]
            break

    return payload


def ensure_compose_volumes(project):
    for name, configuration in project.get("volumes", {}).items():
        configuration = configuration or {}
        volume_name = configuration.get("name") or name
        try:
            api_request(
                "/volumes", 30, method="POST",
                payload={"name": volume_name},
            )
        except RuntimeError as error:
            if "exists" not in str(error).lower():
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


def compose_up(filename, distro):
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

    created = []
    try:
        for service_name, service in compose_service_order(project):
            payload = compose_payload(
                project, service_name, service, volume_names,
            )
            name = payload["name"]
            existing = current.get(name)

            if existing is not None:
                if existing.get("status") == "running":
                    print(f"{name}: already running")
                    continue
                result = api_request(
                    f"/containers/{name}/start", 60, method="POST",
                )
                print(result.get("message") or f"{name}: starting")
                continue

            result = api_request(
                "/containers", 60, method="POST", payload=payload,
            )
            created.append(result["name"])
            current[result["name"]] = result
            print(f"{result['name']}: {result['status']}")
    except Exception:
        for name in reversed(created):
            try:
                api_request(f"/containers/{name}", 60, method="DELETE")
                print(f"{name}: rolled back", file=sys.stderr)
            except RuntimeError as rollback_error:
                print(
                    f"{name}: rollback failed: {rollback_error}",
                    file=sys.stderr,
                )
        raise
    return 0


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
                f"/containers/{name}/stop", 60, method="POST",
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
    missing = [
        compose_container_name(project, service_name, service)
        for service_name, service in ordered
        if compose_container_name(project, service_name, service) not in current
    ]
    if missing:
        raise RuntimeError(
            "Compose containers have not been created: " + ", ".join(missing)
            + ". Run compose up first."
        )

    for service_name, service in ordered:
        name = compose_container_name(project, service_name, service)
        if current[name].get("status") == "running":
            print(f"{name}: already running")
            continue
        result = api_request(
            f"/containers/{name}/start", 60, method="POST",
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

def main():
    distro = os.getenv("VCONTAINER_WSL_DISTRO", "Ubuntu")
    user = os.getenv("VCONTAINER_WSL_USER", "vcdev")
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
            "/containers", 60, method="POST", payload=payload,
        )
        print(f"container {data['name']} {data['status']}")
        return 0
    if len(arguments) == 2 and arguments[0] in ("start", "stop", "rm"):
        ensure_backend(distro)
        action, name = arguments
        if action == "start":
            path, method, timeout = f"/containers/{name}/start", "POST", 30
        elif action == "stop":
            path, method, timeout = f"/containers/{name}/stop", "POST", 60
        else:
            path, method, timeout = f"/containers/{name}", "DELETE", 30
        data = api_request(path, timeout, method=method)
        print(data.get("message") or f"{action}: {name}")
        return 0

    if (
        len(arguments) == 3
        and arguments[:2] == ["compose", "config"]
    ):
        return compose_config(arguments[2])
    if len(arguments) == 3 and arguments[:2] == ["compose", "up"]:
        return compose_up(arguments[2], distro)
    if len(arguments) == 3 and arguments[:2] == ["compose", "start"]:
        return compose_start(arguments[2], distro)
    if len(arguments) == 3 and arguments[:2] == ["compose", "stop"]:
        return compose_stop(arguments[2], distro)
    if len(arguments) == 3 and arguments[:2] == ["compose", "down"]:
        return compose_down(arguments[2], distro)
    if len(arguments) == 3 and arguments[:2] == ["compose", "ps"]:
        return compose_ps(arguments[2], distro)

    directory = os.path.dirname(os.path.abspath(__file__))
    # WSL's Windows owner can launch root directly. API permissions remain
    # restricted to the read-only helper; no blanket sudo rule is installed.
    # WSL accepts a Windows path for --cd. This avoids launching wslpath
    # and a separate user check on every invocation; setup validates the user.
    return subprocess.call([
        "wsl.exe", "-d", distro, "-u", "root",
        "--cd", directory,
        "--exec", "env", f"SUDO_USER={user}",
        "bash", "./run_container.sh", *sys.argv[1:],
    ])


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
