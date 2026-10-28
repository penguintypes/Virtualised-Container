import asyncio
import subprocess
from typing import Any

from fastapi import HTTPException

from .services import runtime

container_tasks: dict[str, asyncio.Task] = {}
ip_reservations: set[str] = set()
ip_lock = asyncio.Lock()


async def restore_runtime_state() -> None:
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


async def reserve_bridge_ip(preferred: str | None = None) -> str:
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
                raise HTTPException(
                    409, f"Bridge address is already in use: {preferred}"
                )
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
    payload: dict[str, Any] | None = None,
) -> None:
    started = False

    try:
        process = (
            await runtime.launch_saved_container(name)
            if payload is None
            else await runtime.launch_container(payload)
        )
        if isinstance(process, subprocess.Popen):
            communication = asyncio.create_task(asyncio.to_thread(process.communicate))
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
                            raise RuntimeError("Published ports require a bridge IP")
                        await asyncio.to_thread(
                            runtime.publish_ports,
                            name,
                            address,
                            payload["ports"],
                        )
                    started = True
                    break
            except runtime.ResourceNotFoundError:
                pass
            await asyncio.sleep(0.05)

        stdout, stderr = await communication
        exit_code = process.returncode
        if exit_code is not None and exit_code < 0:
            exit_code = 128 - exit_code

        try:
            await asyncio.to_thread(runtime.record_exit, name, exit_code)
        except runtime.ResourceNotFoundError:
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
