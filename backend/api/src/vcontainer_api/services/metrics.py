import threading
import time
from typing import Any

metric_samples: dict[str, tuple[float, int]] = {}
metric_lock = threading.Lock()


def _number(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else None


def metric_data(data: dict[str, Any]) -> dict[str, Any]:
    usage = _number(data.get("cpu", {}).get("usage_usec"))
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

    block_io = data.get("block_io", {})
    network = data.get("network", {})
    return {
        "name": data["name"],
        "status": data.get("status"),
        "cpu_usage_usec": usage,
        "cpu_percent": cpu_percent,
        "memory_used_bytes": _number(data.get("memory_current")),
        "memory_limit_bytes": _number(data.get("memory_max")),
        "process_count": _number(data.get("pids_current")),
        "process_limit": _number(data.get("pids_max")),
        "network_rx_bytes": _number(network.get("rx_bytes")) or 0,
        "network_tx_bytes": _number(network.get("tx_bytes")) or 0,
        "block_read_bytes": _number(block_io.get("rbytes")) or 0,
        "block_write_bytes": _number(block_io.get("wbytes")) or 0,
        "block_read_operations": _number(block_io.get("rios")) or 0,
        "block_write_operations": _number(block_io.get("wios")) or 0,
        "cpu_limit": data.get("cpu_max"),
    }
