import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from . import core

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("/usr/local/libexec/vcontainer/run_container.sh")
HELPER = "/usr/local/libexec/vcontainer/build_helper.sh"
STATE = ROOT / "var" / "engine.json"
_cpu_cache = {}

def _call(*args, timeout=30):
    if shutil.which("sudo") is None:
        raise RuntimeError("sudo is required to run the Linux engine")
    result = subprocess.run(["sudo", "-n", str(SCRIPT), *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        error = result.stderr.strip() or result.stdout.strip() or "engine command failed"
        if "password" in error.lower() or "a terminal is required" in error.lower():
            raise RuntimeError("sudo needs a password; run install.sh and choose the personal NOPASSWD rule")
        raise RuntimeError(error)
    return result.stdout.strip()

def _load():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, indent=2))

def _parse(text):
    data = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            data[key.strip()] = value.strip()
    return data

def _record(container, **changes):
    data = _load(); data.setdefault(container, {}).update(changes); _save(data); return data[container]

def capabilities():
    cgroup = Path("/sys/fs/cgroup")
    filesystems = Path("/proc/filesystems").read_text(errors="ignore")
    namespace_probe = subprocess.run(["unshare", "-Ur", "true"], capture_output=True) if shutil.which("unshare") else None
    return {"namespaces": bool(namespace_probe and namespace_probe.returncode == 0),
            "cgroups_v2": (cgroup / "cgroup.controllers").exists(),
            "cgroups_writable": os.access(cgroup, os.W_OK),
            "overlayfs": "overlay" in filesystems,
            "network_tools": all(shutil.which(x) for x in ("ip", "socat"))}

def images():
    _call("list")
    out = []
    for path in sorted(core.STORE.glob("*/rootfs")):
        if path.is_dir():
            out.append(core.read_meta(path.parent.name))
    return out

from contextlib import contextmanager

@contextmanager
def _tmp():
    temp = tempfile.mkdtemp()
    try: yield temp
    finally: subprocess.run(["sudo", "-n", HELPER, "rm", "-rf", temp])

def build(path, clean=False, update=False):
    import json
    import re
    flags = re.findall(r"\s--(clean|update)\b", " " + str(path))
    clean = clean or "clean" in flags
    update = update or "update" in flags
    path = re.sub(r"\s+--(clean|update)\b", "", str(path)).strip()
    spec = core.parse_vcfile(path)
    name = Path(path).parent.name
    core.valid_name(name)
    context = Path(path).parent
    live_rootfs = core.STORE / name / "rootfs"
    state_file = core.STORE / name / ".vcbuild.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else ({"from": spec["from"], "run": spec["run"]} if live_rootfs.is_dir() else None)
    try:
        stop(name)
    except Exception:
        pass
    if live_rootfs.is_dir() and not clean and state and state.get("from") == spec["from"]:
        for source, target in spec["copy"]:
            subprocess.run(["sudo", "-n", HELPER, "install", "-D", "-m", "644", str(context / source), str(live_rootfs / target.lstrip("/"))], check=True)
        old_runs = state.get("run", [])
        new_runs = spec["run"] if update else [c for c in spec["run"] if c not in old_runs]
        if update or new_runs:
            subprocess.run(["sudo", "-n", HELPER, "write_file", str(live_rootfs / "etc" / "resolv.conf")], input="nameserver 1.1.1.1\nnameserver 8.8.8.8\n", text=True, stdout=subprocess.DEVNULL, check=True)
            if update:
                subprocess.run(["sudo", "-n", HELPER, "run_chroot", str(live_rootfs), "/bin/sh", "-c", "apk update && apk upgrade"], check=False, timeout=300)
            for command in new_runs:
                subprocess.run(["sudo", "-n", HELPER, "run_chroot", str(live_rootfs), "/bin/sh", "-c", command], check=True, timeout=300)
        subprocess.run(["sudo", "-n", HELPER, "write_file", str(state_file)], input=json.dumps({"from": spec["from"], "run": spec["run"]}), text=True, stdout=subprocess.DEVNULL, check=True)
    else:
        if spec["from"] != "scratch" and (clean or not (core.STORE / spec["from"] / "rootfs").is_dir()):
            if clean and (core.STORE / spec["from"] / "rootfs").is_dir():
                _call("delete", spec["from"], timeout=30)
            try: _call("pull", spec["from"], timeout=300)
            except RuntimeError as e:
                if "already exists" not in str(e): raise
        with _tmp() as temp:
            rootfs = Path(temp) / "rootfs"; rootfs.mkdir()
            if spec["from"] != "scratch":
                subprocess.run(["sudo", "-n", HELPER, "cp", "-a", f"{core.STORE}/{spec['from']}/rootfs/.", str(rootfs)], check=True, timeout=60)
            for source, target in spec["copy"]:
                subprocess.run(["sudo", "-n", HELPER, "install", "-D", "-m", "644", str(context / source), str(rootfs / target.lstrip("/"))], check=True)
            subprocess.run(["sudo", "-n", HELPER, "write_file", str(rootfs / "etc" / "resolv.conf")], input="nameserver 1.1.1.1\nnameserver 8.8.8.8\n", text=True, stdout=subprocess.DEVNULL, check=True)
            for command in spec["run"]:
                subprocess.run(["sudo", "-n", HELPER, "run_chroot", str(rootfs), "/bin/sh", "-c", command], check=True, timeout=300)
            archive = Path(temp) / f"{name}.tar"
            subprocess.run(["sudo", "-n", HELPER, "tar", "-C", str(rootfs), "-cf", str(archive), *[i.name for i in rootfs.iterdir()]], check=True)
            _call("delete", name, timeout=30)
            _call("import", name, str(archive), timeout=300)
        subprocess.run(["sudo", "-n", HELPER, "write_file", str(state_file)], input=json.dumps({"from": spec["from"], "run": spec["run"]}), text=True, stdout=subprocess.DEVNULL, check=True)
    meta = {"id": name, "name": name, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "size": 0, "cmd": spec["cmd"], "env": spec["env"]}
    size = subprocess.run(["sudo", "-n", HELPER, "du", "-sb", str(core.STORE / name / "rootfs")], capture_output=True, text=True, check=True)
    meta["size"] = int(size.stdout.split()[0])
    subprocess.run(["sudo", "-n", HELPER, "mkdir", "-p", str(core.STORE / name)], check=True)
    subprocess.run(["sudo", "-n", HELPER, "write_file", str(core.STORE / name / "meta.json")], input=json.dumps(meta), text=True, check=True, stdout=subprocess.DEVNULL)
    return meta

def run(name, image, command=None, memory=None, cpus=None, pids=None, port=None, volumes=None, env=None, network=None, ip=None):
    core.valid_name(name); meta = core.read_meta(image)
    try: remove(name)
    except Exception: pass
    import shlex
    import shlex
    if isinstance(command, str): command = shlex.split(command)
    if command is None:
        command = meta.get("cmd")
    if not command:
        command = {"mysql": ["docker-entrypoint.sh", "mysqld"], "nginx": ["nginx", "-g", "daemon off;"], "node": ["node"]}.get(image, ["/bin/sh"])
    args = ["run", image, "--name", name, "--detach"]
    if memory: args += ["--memory-max", str(memory)]
    if pids: args += ["--pids-max", str(pids)]
    if cpus and "/" in str(cpus): args += ["--cpu-max", *str(cpus).split("/", 1)]
    if port: args += ["-p", str(port)]
    if volumes:
        for v in volumes:
            if isinstance(v, dict):
                args += ["--volume", f"{v.get('name', '')}:{v.get('target', '')}"]
            else:
                args += ["--volume", str(v)]
    if env:
        if isinstance(env, dict):
            for k, v in env.items(): args += ["--env", f"{k}={v}"]
        elif isinstance(env, list):
            for e in env: args += ["--env", str(e)]
    if network == "bridge" and ip:
        args += ["--network", "bridge", "--ip", str(ip)]
    args += ["--"] + command
    output = _call(*args, timeout=60)
    return _record(name, id=name, name=name, image=image, status="running", pid=None, created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ports=[port] if port else [], command=command, output=output, memory=memory, cpus=cpus, pids=pids, volumes=volumes, env=env, network=network, ip=ip)

def inspect(name):
    data = _parse(_call("inspect", name))
    record = _load().get(name, {"id": name, "name": name})
    pids = data.pop("pids", "").split()
    record.update(status="exited" if data.get("status") == "stopped" else data.get("status", "unknown"), pid=int(pids[0]) if pids else None)
    try:
        from pathlib import Path
        stat_text = Path(f"/sys/fs/cgroup/vcontainer/{name}/cpu.stat").read_text()
        usec = int([line.split()[1] for line in stat_text.splitlines() if line.startswith("usage_usec")][0])
        now = time.time()
        last_now, last_usec = _cpu_cache.get(name, (now - 1.0, usec))
        dt = now - last_now
        if dt >= 1.0:
            _cpu_cache[name] = (now, usec)
            _cpu_cache[name + ":pct"] = max(0.0, (usec - last_usec) / 1000000.0 / dt * 100)
        data["cpu_pct"] = round(_cpu_cache.get(name + ":pct", 0.0), 1)
    except Exception:
        data["cpu_pct"] = 0.0
    return record | data

def containers():
    return [inspect(name) for name in sorted(_load())]

def stop(name):
    result = _record(name, status="exited", output="")
    _call("stop", name)
    return result

def remove(name):
    try: _call("stop", name)
    except Exception: pass
    try: _call("rm", name)
    except Exception: pass
    data = _load(); data.pop(name, None); _save(data)

def logs(name): return {"logs": _call("logs", name)}
def execute(name, command):
    result = subprocess.run(["sudo", "-n", str(SCRIPT), "exec", name, "--", *command], capture_output=True, text=True, timeout=30)
    if result.returncode and "password" in result.stderr.lower():
        raise RuntimeError("sudo needs a password; run install.sh and choose the personal NOPASSWD rule")
    return {"code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
def stats(name):
    data = inspect(name)
    return {"memory_bytes": _number(data.get("memory_current")), "memory_limit_bytes": _number(data.get("memory_max")), "pids": _number(data.get("pids_current")), "pid_limit": _number(data.get("pids_max")), "cpu_limit": data.get("cpu_max"), "status": data.get("status")}
def _number(value):
    try: return int(value) if value and value != "max" else None
    except ValueError: return None

def export_image(name):
    core.valid_name(name)
    a = Path(tempfile.mkdtemp()) / f"{name}.tar"
    subprocess.run(["sudo", "-n", HELPER, "tar", "-C", f"{core.STORE}/{name}/rootfs", "-cf", str(a), "."], check=True)
    return a

def upload_image(name, path):
    core.valid_name(name)
    _call("import", name, path, timeout=300)
    m = {"id": name, "name": name, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "size": 0}
    s = subprocess.run(["sudo", "-n", HELPER, "du", "-sb", f"{core.STORE}/{name}/rootfs"], capture_output=True, text=True, check=True)
    m["size"] = int(s.stdout.split()[0])
    subprocess.run(["sudo", "-n", HELPER, "mkdir", "-p", f"{core.STORE}/{name}"], check=True)
    subprocess.run(["sudo", "-n", HELPER, "write_file", f"{core.STORE}/{name}/meta.json"], input=json.dumps(m), text=True, check=True, stdout=subprocess.DEVNULL)
    return m


def host_stats():
    import os
    meminfo = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        meminfo[key] = int(rest.split()[0]) * 1024
    cpu_times = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return {"cpus": os.cpu_count(), "cpu_times": cpu_times, "load": list(os.getloadavg()),
            "mem_total": meminfo.get("MemTotal"), "mem_available": meminfo.get("MemAvailable")}

def get_disk_usage():
    import subprocess
    volumes_dir = "/var/lib/vcontainer/volumes"
    containers_dir = "/var/lib/vcontainer/containers"
    images_dir = "/var/lib/vcontainer/images"
    total_bytes = 0
    container_count = len(_load())
    for d in [volumes_dir, containers_dir, images_dir]:
        if os.path.exists(d):
            res = subprocess.run(["sudo", "-n", "du", "-sb", d], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    total_bytes += int(res.stdout.split()[0])
                except ValueError:
                    pass
    return {"used_bytes": total_bytes, "container_count": container_count}

def run_volume(action, name=None):
    if action == "list":
        out = _call("volume", "list")
        return [{"name": n, "mount_source": f"/var/lib/vcontainer/volumes/{n}/_data"} for n in out.splitlines() if n]
    elif action == "create" and name:
        core.valid_name(name)
        _call("volume", "create", name)
        return {"name": name, "mount_source": f"/var/lib/vcontainer/volumes/{name}/_data"}
    elif action == "inspect" and name:
        core.valid_name(name)
        return _parse(_call("volume", "inspect", name))
    elif action == "remove" and name:
        core.valid_name(name)
        _call("volume", "remove", name)
        return {"status": "removed"}
    return []