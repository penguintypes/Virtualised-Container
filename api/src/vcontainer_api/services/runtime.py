import asyncio
import os
import subprocess

import orjson

from ..errors import ConflictError, ResourceNotFoundError

DISTRO = os.getenv("VCONTAINER_WSL_DISTRO", "Ubuntu")
USER = os.getenv("VCONTAINER_WSL_USER", "vcdev")


def run_command(action, *args):
    if action not in ("disk", "images", "ps", "inspect", "logs", "processes"):
        raise ValueError("Unsupported command")

    command = ["sudo", "-n", "/usr/local/sbin/vcontainer-read", action, *args]
    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or "Runtime command failed"
        if action in ("inspect", "logs", "processes") and message in (
            "Container not found",
            "No logs found",
        ):
            raise ResourceNotFoundError(message)
        raise RuntimeError(result.stderr.strip() or "Runtime command failed")

    try:
        return orjson.loads(result.stdout)
    except orjson.JSONDecodeError as error:
        raise RuntimeError("Helper returned invalid JSON") from error


def get_images():
    return run_command("images")


def get_containers():
    return run_command("ps")


def get_container(name):
    return run_command("inspect", name)


def get_logs(name):
    return run_command("logs", name)


def get_processes(name):
    return run_command("processes", name)


async def stop_stream_process(process):
    if process.returncode is not None:
        return

    try:
        process.terminate()
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            return

        await process.wait()


async def stream_logs(name):
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-read",
        "logs-follow",
        name,
    ]

    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        assert process.stdout is not None

        while True:
            line = await process.stdout.readline()

            if not line:
                break

            yield (
                b"event: log\n"
                b"data: "
                + orjson.dumps(
                    {
                        "message": line.decode(errors="replace").rstrip("\r\n"),
                    }
                )
                + b"\n\n"
            )

        returncode = await process.wait()
        event = "end" if returncode == 0 else "error"

        yield (
            f"event: {event}\n".encode()
            + b"data: "
            + orjson.dumps(
                {
                    "name": name,
                    "returncode": returncode,
                }
            )
            + b"\n\n"
        )

    except asyncio.CancelledError:
        raise

    finally:
        await stop_stream_process(process)


def run_control(action, name=None, payload=None):
    if action not in (
        "stop",
        "remove",
        "started",
        "resources",
        "publish",
        "republish",
    ):
        raise ValueError("Unsupported control command")

    command = ["sudo", "-n", "/usr/local/sbin/vcontainer-control", action]
    if name is not None:
        command.append(name)
    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    request = None
    if payload is not None:
        request = orjson.dumps(payload).decode("utf-8")

    result = subprocess.run(
        command,
        input=request,
        capture_output=True,
        text=True,
        timeout=300 if action == "create" else 30,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Runtime command failed"
        lowered = message.lower()
        if "not found" in lowered:
            raise ResourceNotFoundError(message)
        if (
            "already running" in lowered
            or "already exists" in lowered
            or "container is running" in lowered
        ):
            raise ConflictError(message)
        raise RuntimeError(message)

    try:
        return orjson.loads(result.stdout)
    except orjson.JSONDecodeError as error:
        raise RuntimeError("Control helper returned invalid JSON") from error


async def launch_container(payload):
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-control",
        "create",
    ]

    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    if os.name == "nt":
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        process.stdin.write(orjson.dumps(payload))
        process.stdin.close()
        # communicate() otherwise tries to flush the already closed stream.
        process.stdin = None
        return process

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert process.stdin is not None

    process.stdin.write(orjson.dumps(payload))
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()

    return process


async def launch_saved_container(name):
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-control",
        "start",
        name,
    ]
    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    if os.name == "nt":
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    return await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


def record_started(name):
    return run_control("started", name=name)


def publish_ports(name, address, ports):
    return run_control(
        "publish",
        name=name,
        payload={"address": address, "ports": ports},
    )


def republish_ports(name):
    return run_control("republish", name=name)


def record_exit(name, exit_code):
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-control",
        "finish",
        name,
        str(exit_code),
    ]

    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]

    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Could not save container exit code"
        )

    try:
        return orjson.loads(result.stdout)
    except orjson.JSONDecodeError as error:
        raise RuntimeError("Exit-code helper returned invalid JSON") from error


def stop_container(name):
    return run_control("stop", name=name)


def remove_container(name):
    return run_control("remove", name=name)


def update_resources(name, resources):
    return run_control(
        "resources",
        name=name,
        payload=resources,
    )


def image_command(action, name, reference=None):
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-image-control",
        action,
        name,
    ]
    if reference is not None:
        command.append(reference)
    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]
    return command


def pull_image(name, reference=None):
    result = subprocess.run(
        image_command("pull", name, reference),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=900,
    )
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode != 0:
        if "already exists" in output.lower():
            raise ConflictError(output)
        raise RuntimeError(output or "Image pull failed")
    return {
        "name": name,
        "status": "complete",
        "output": output,
    }


def delete_image(name):
    result = subprocess.run(
        image_command("delete", name),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        message = (
            result.stderr.strip() or result.stdout.strip() or "Image deletion failed"
        )
        lowered = message.lower()
        if "not found" in lowered:
            raise ResourceNotFoundError(message)
        if "referenced by a container" in lowered:
            raise ConflictError(message)
        raise RuntimeError(message)
    return {
        "name": name,
        "message": result.stdout.strip() or f"Deleted image: {name}",
    }


def run_volume(action, name=None):
    if action not in ("list", "create", "inspect", "remove"):
        raise ValueError("Unsupported volume command")
    command = [
        "sudo",
        "-n",
        "/usr/local/sbin/vcontainer-volume-control",
        action,
    ]
    if name is not None:
        command.append(name)
    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            DISTRO,
            "-u",
            USER,
            "--exec",
            *command,
        ]
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Volume operation failed"
        lowered = message.lower()
        if "not found" in lowered:
            raise ResourceNotFoundError(message)
        if "already exists" in lowered or "in use" in lowered or "not empty" in lowered:
            raise ConflictError(message)
        raise RuntimeError(message)
    try:
        return orjson.loads(result.stdout)
    except orjson.JSONDecodeError as error:
        raise RuntimeError("Volume helper returned invalid JSON") from error


def get_disk_usage():
    """Return writable-layer, metadata, and log usage for containers only."""
    return run_command("disk")
