import subprocess 

import json 
import os

DISTRO = os.getenv("VCONTAINER_WSL_DISTRO", "Ubuntu")
USER = os.getenv("VCONTAINER_WSL_USER", "vcdev")


class ResourceNotFound(RuntimeError):
    pass


def run_command(action, *args):
    if action in ("images", "ps", "inspect", "logs"):
        command = [
            "wsl.exe",
            "-d", DISTRO,
            "-u", USER,
            "--exec",
            "sudo", "-n",
            "/usr/local/sbin/vcontainer-read",
            action, *args,
        ]
    else:
        raise ValueError("Unsupported command")



    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or 'Runtime command failed'
        if action in ('inspect', 'logs') and message in ('Container not found', 'No logs found'):
            raise ResourceNotFound(message)
        raise RuntimeError(
            result.stderr.strip() or "Runtime command failed"
        )


    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError('Helper returned invalid JSON') from error


def get_images():
    return run_command('images')


def get_containers():
    return run_command("ps")


def get_container(name):
    return run_command("inspect", name)


def get_logs(name):
    return run_command("logs", name)




