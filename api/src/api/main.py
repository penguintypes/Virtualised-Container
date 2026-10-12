import re
import subprocess

from fastapi import FastAPI, HTTPException

from . import runtime

app = FastAPI(title="Vcontainer API", version="0.1.0")

def validate_name(name):
    if(
        name in (".","..")
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
    ):
        raise HTTPException(400, "Invalid container name")

def read_runtime(function, *args):
    try:
        return function(*args)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Runtime request timed out")
    except runtime.ResourceNotFound as error:
        raise HTTPException(404, str(error))
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/images")
def images():
    return {"images": read_runtime(runtime.get_images)}

@app.get("/containers")
def containers():
    return  {
        "containers": read_runtime(runtime.get_containers)
    }

@app.get("/containers/{name}")
def container(name: str):
    validate_name(name)
    data = read_runtime(runtime.get_container, name)

    if data.get("status") == "unknown":
        raise HTTPException(404, "Container not found")
    
    return data

@app.get("/containers/{name}/metrics")
def metrics(name: str):
    data = container(name)

    def number(key):
        value = data.get(key)
        return int(value) if value and value.isdigit() else None

    return {
        "name": name,
        "status": data.get("status"),
        "memory_used_bytes": number("memory_current"),
        "memory_limit_bytes": number("memory_max"),
        "process_count": number("pids_current"),
        "process_limit": number("pids_max"),
        "cpu_limit": data.get("cpu_max"),
    }

@app.get("/containers/{name}/logs")
def logs(name: str):
    container(name)

    return {
        "name": name,
        "output": read_runtime(runtime.get_logs, name),
    }