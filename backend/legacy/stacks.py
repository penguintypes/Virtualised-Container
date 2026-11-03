import json
import os
import re
import secrets
import string
import subprocess
from pathlib import Path
from . import engine

STACKS_DIR = Path("/var/lib/vcontainer/stacks")
HELPER = "/usr/local/libexec/vcontainer/build_helper.sh"

def _generate_secret(rule):
    chars = string.ascii_letters + string.digits
    length = 32 if rule == "random_string_32" else 16
    return ''.join(secrets.choice(chars) for _ in range(length))

def _resolve_inputs(template_inputs, user_inputs, existing_inputs):
    resolved = dict(existing_inputs)
    for k, v in user_inputs.items():
        if k not in template_inputs:
            raise ValueError(f"Unknown input parameter: {k}")
        v_str = str(v)
        if "\n" in v_str or "\r" in v_str:
            raise ValueError(f"Newlines not allowed in input {k}")
        pattern = template_inputs[k].get("pattern")
        if pattern and not re.match(pattern, v_str):
            raise ValueError(f"Input {k} does not match required pattern: {pattern}")
        resolved[k] = v_str
        
    for k, spec in template_inputs.items():
        if k not in resolved:
            if "generate" in spec:
                resolved[k] = _generate_secret(spec["generate"])
            elif "default" in spec:
                resolved[k] = spec["default"]
            else:
                raise ValueError(f"Missing required input: {k}")
    return resolved

def _apply_template(services, inputs):
    text = json.dumps(services)
    for k, v in inputs.items():
        text = text.replace(f"${{{k}}}", str(v))
    return json.loads(text)

def _sort_services(services):
    ordered = []
    pending = {s["name"]: s for s in services}
    while pending:
        ready = [name for name, s in pending.items() if not any(dep in pending for dep in s.get("depends_on", []))]
        if not ready:
            raise ValueError("Circular dependency detected in stack services")
        for name in sorted(ready):
            ordered.append(pending.pop(name))
    return ordered

def get_stack(name):
    stack_file = STACKS_DIR / f"{name}.json"
    try:
        res = subprocess.run(["sudo", "-n", "cat", str(stack_file)], capture_output=True, text=True)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception:
        pass
    return None

def _write_stack(name, state):
    subprocess.run(["sudo", "-n", "mkdir", "-p", str(STACKS_DIR)], check=True)
    subprocess.run(["sudo", "-n", "chmod", "700", str(STACKS_DIR)], check=True)
    stack_file = STACKS_DIR / f"{name}.json"
    subprocess.run(["sudo", "-n", HELPER, "write_file", str(stack_file)], input=json.dumps(state, indent=2), text=True, check=True)
    subprocess.run(["sudo", "-n", "chmod", "600", str(stack_file)], check=True)

def list_stacks():
    res = subprocess.run(["sudo", "-n", "ls", "-1", str(STACKS_DIR)], capture_output=True, text=True)
    if res.returncode != 0:
        return []
    stacks = []
    for f in res.stdout.splitlines():
        if f.endswith(".json"):
            stacks.append(f[:-5])
    return stacks

def up(name, template, user_inputs):
    existing = get_stack(name)
    existing_inputs = existing.get("inputs", {}) if existing else {}
    
    resolved_inputs = _resolve_inputs(template.get("inputs", {}), user_inputs, existing_inputs)
    templated_services = _apply_template(template.get("services", []), resolved_inputs)
    ordered_services = _sort_services(templated_services)
    
    state = {"name": name, "inputs": resolved_inputs, "services": ordered_services}
    _write_stack(name, state)
    
    launched = []
    engine_state = engine._load()
    try:
        for s in ordered_services:
            cname = s["name"]
            prev_s = next((x for x in existing.get("services", []) if x["name"] == cname), None) if existing else None
            needs_recreate = (existing is None) or (prev_s != s)
            
            c_status = engine_state.get(cname, {}).get("status")
            
            if needs_recreate or c_status != "running":
                engine.remove(cname)
                run_kwargs = {k: v for k, v in s.items() if k not in ("depends_on", "ready_log")}
                if "env" in run_kwargs and isinstance(run_kwargs["env"], list):
                    env_dict = {}
                    for e in run_kwargs["env"]:
                        if "=" in e:
                            ek, ev = e.split("=", 1)
                            env_dict[ek] = ev
                    run_kwargs["env"] = env_dict
                if "ports" in run_kwargs:
                    ports = run_kwargs.pop("ports")
                    if ports: run_kwargs["port"] = ports[0] if isinstance(ports, list) else ports
                engine.run(**run_kwargs)
                launched.append(cname)

    except Exception as e:
        for cname in launched:
            engine.remove(cname)
        raise e

def down(name):
    stack = get_stack(name)
    if not stack:
        return
    for s in reversed(stack.get("services", [])):
        engine.remove(s["name"])
    subprocess.run(["sudo", "-n", "rm", "-f", str(STACKS_DIR / f"{name}.json")])

def start(name):
    stack = get_stack(name)
    if stack:
        up(name, stack, stack.get("inputs", {}))

def stop(name):
    stack = get_stack(name)
    if not stack:
        return
    for s in reversed(stack.get("services", [])):
        engine.stop(s["name"])
