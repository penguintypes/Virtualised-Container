with open("backend/engine.py", "r") as f: lines = f.readlines()
for i, line in enumerate(lines):
    if 'if not command:' in line and 'command = ["/bin/sh"]' in lines[i+1]:
        indent = line[:len(line) - len(line.lstrip())]
        lines[i+1] = indent + '    command = {"mysql": ["docker-entrypoint.sh", "mysqld"], "nginx": ["nginx", "-g", "daemon off;"], "node": ["node"]}.get(image, ["/bin/sh"])\n'
        break
with open("backend/engine.py", "w") as f: f.writelines(lines)
