with open('backend/engine.py', 'r') as f:
    lines = f.readlines()

with open('backend/engine.py', 'w') as f:
    for line in lines:
        if "for k, v in env.items(): args +=" in line:
            indent = line[:len(line) - len(line.lstrip())]
            f.write(indent + "if isinstance(env, dict):\n")
            f.write(indent + "    for k, v in env.items(): args += [\"--env\", f\"{k}={v}\"]\n")
            f.write(indent + "elif isinstance(env, list):\n")
            f.write(indent + "    for e in env: args += [\"--env\", str(e)]\n")
        else:
            f.write(line)
