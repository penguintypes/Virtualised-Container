with open('backend/engine.py', 'r') as f:
    lines = f.readlines()

with open('backend/engine.py', 'w') as f:
    for line in lines:
        if "for v in volumes: args +=" in line:
            indent = line[:len(line) - len(line.lstrip())]
            f.write(indent + "for v in volumes:\n")
            f.write(indent + "    if isinstance(v, dict):\n")
            f.write(indent + "        args += [\"--volume\", f\"{v.get('name', '')}:{v.get('target', '')}\"]\n")
            f.write(indent + "    else:\n")
            f.write(indent + "        args += [\"--volume\", str(v)]\n")
        elif "for e in environment: args +=" in line:
            indent = line[:len(line) - len(line.lstrip())]
            f.write(indent + "for e in environment:\n")
            f.write(indent + "    if isinstance(e, dict):\n")
            f.write(indent + "        args += [\"--env\", f\"{e.get('name', '')}={e.get('value', '')}\"]\n")
            f.write(indent + "    else:\n")
            f.write(indent + "        args += [\"--env\", str(e)]\n")
        else:
            f.write(line)
