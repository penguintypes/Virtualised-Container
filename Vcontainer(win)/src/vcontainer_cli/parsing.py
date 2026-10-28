from typing import Any


def split_option(
    value: str,
    separator: str,
    error_message: str,
) -> tuple[str, str]:
    left, found, right = value.partition(separator)
    if not found:
        raise ValueError(error_message)
    return left, right


def apply_run_option(
    payload: dict[str, Any],
    option: str,
    value: str,
) -> None:
    fields = {
        "--name": "name",
        "--hostname": "hostname",
        "--memory-max": "memory_max",
        "--network": "network",
        "--ip": "ip",
    }
    field = fields.get(option)
    if field is not None:
        payload[field] = value
        return
    if option == "--pids-max":
        payload["pids_max"] = int(value)
        return
    if option in ("--volume", "-v"):
        volume, target = split_option(
            value,
            ":",
            "Volume must use NAME:/TARGET",
        )
        payload["volumes"].append({"name": volume, "target": target})
        return
    if option in ("--env", "-e"):
        name, environment_value = split_option(
            value,
            "=",
            "Environment variable must use NAME=VALUE",
        )
        if not name:
            raise ValueError("Environment variable name is missing")
        payload["environment"][name] = environment_value
        return
    host_port, container_port = split_option(
        value,
        ":",
        "Published port must use HOST_PORT:CONTAINER_PORT",
    )
    payload["ports"].append(
        {
            "host_port": int(host_port),
            "container_port": int(container_port),
        }
    )


def parse_run(arguments: list[str]) -> dict[str, Any]:
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
        if option == "--cpu-max":
            if index + 2 >= len(arguments):
                raise ValueError("--cpu-max requires QUOTA PERIOD")
            payload["cpu_quota"] = int(arguments[index + 1])
            payload["cpu_period"] = int(arguments[index + 2])
            index += 3
            continue
        supported = (
            "--name",
            "--hostname",
            "--memory-max",
            "--pids-max",
            "--network",
            "--ip",
            "--volume",
            "-v",
            "--env",
            "-e",
            "--publish",
            "-p",
        )
        if option not in supported:
            raise ValueError(f"Unsupported run option: {option}")
        if index + 1 >= len(arguments):
            raise ValueError(f"Missing value for {option}")
        value = arguments[index + 1]
        index += 2
        apply_run_option(payload, option, value)

    if index < len(arguments):
        command = arguments[index + 1 :]
        if not command:
            raise ValueError("Command is missing after --")
        payload["command"] = command

    if not payload.get("name"):
        raise ValueError("--name is required")
    return payload
