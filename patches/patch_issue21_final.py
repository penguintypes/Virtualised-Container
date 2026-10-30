with open("backend/engine.py", "r") as f: text = f.read()
text = text.replace(
    "cmd = meta.get('config', {}).get('Cmd')\n    command = cmd if cmd else ['/bin/sh']",
    "command = meta.get('cmd') or {'mysql': ['docker-entrypoint.sh', 'mysqld'], 'nginx': ['nginx', '-g', 'daemon off;'], 'node': ['node']}.get(image, ['/bin/sh'])"
)
with open("backend/engine.py", "w") as f: f.write(text)
