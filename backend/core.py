import json
import os
import re
from pathlib import Path

STORE = Path(os.getenv("VCONTAINER_IMAGE_STORE", "/var/lib/vcontainer/images"))
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

def valid_name(value):
    if not value or value in (".", "..") or not NAME.fullmatch(value):
        raise ValueError("invalid name")
    return value

def parse_vcfile(path):
    path = Path(path)
    spec = {"from": "alpine", "copy": [], "run": [], "cmd": None, "env": {}}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        op, _, arg = line.partition(" ")
        op = op.upper()
        arg = arg.strip()
        if op == "FROM":
            spec["from"] = valid_name(arg)
        elif op == "COPY":
            source, sep, target = arg.partition(" ")
            if not sep or not source or not target.startswith("/"):
                raise ValueError("COPY requires SOURCE /absolute/target")
            spec["copy"].append((source, target))
        elif op == "RUN":
            if not arg:
                raise ValueError("RUN requires a command")
            spec["run"].append(arg)
        elif op == "CMD":
            spec["cmd"] = json.loads(arg)
            if not isinstance(spec["cmd"], list) or not all(isinstance(x, str) for x in spec["cmd"]):
                raise ValueError("CMD must be a JSON string array")
        elif op == "ENV":
            key, sep, value = arg.partition("=")
            if not sep or not NAME.fullmatch(key):
                raise ValueError("ENV requires KEY=value")
            spec["env"][key] = value
        else:
            raise ValueError(f"unsupported Vcfile instruction: {op}")
    return spec

def read_meta(name):
    valid_name(name)
    path = STORE / name / "meta.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {"id": name, "name": name, "created": None, "size": 0}
