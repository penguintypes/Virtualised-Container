import time
from contextlib import suppress
from pathlib import Path
from threading import Lock

ROOT = Path("/sys/fs/cgroup/vcontainer")
_prev = {}
_snapshot_lock = Lock()


def _read(path):
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def _snapshot():
    now = time.time()
    lines = _read("/proc/stat").splitlines()
    fields = [int(x) for x in lines[0].split()[1:9]] if lines else [0] * 8
    total = sum(fields)
    idle = fields[3] + fields[4] if len(fields) > 4 else 0
    mem = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            mem[key] = int(parts[0]) * 1024
    mem_total = mem.get("MemTotal", 0)
    mem_used = mem_total - mem.get("MemAvailable", 0)
    cont_mem = cont_usec = count = 0
    if ROOT.is_dir():
        for d in ROOT.iterdir():
            if not d.is_dir():
                continue
            count += 1
            with suppress(ValueError):
                cont_mem += int(_read(d / "memory.current").strip() or 0)
            for line in _read(d / "cpu.stat").splitlines():
                if line.startswith("usage_usec"):
                    cont_usec += int(line.split()[1])
    host_cpu = cont_cpu = 0.0
    prev = _prev.get("v")
    if prev and now > prev[0]:
        dtot = total - prev[1]
        if dtot > 0:
            host_cpu = 100.0 * (1 - (idle - prev[2]) / dtot)
        cont_cpu = max(0, cont_usec - prev[3]) / 1e6 / (now - prev[0]) * 100
    _prev["v"] = (now, total, idle, cont_usec)
    return {
        "host_cpu_percent": round(min(100.0, max(0.0, host_cpu)), 1),
        "container_cpu_percent": round(cont_cpu, 1),
        "host_memory_used_bytes": mem_used,
        "host_memory_total_bytes": mem_total,
        "container_memory_bytes": cont_mem,
        "container_count": count,
    }


def snapshot():
    with _snapshot_lock:
        return _snapshot()
