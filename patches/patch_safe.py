import re

# 1. Patch api.py (Issue 20 & 22)
with open("backend/api.py", "r") as f: lines = f.readlines()
for i, line in enumerate(lines):
    if "res = engine.run(" in line:
        indent = line[:len(line) - len(line.lstrip())]
        lines.insert(i, indent + "if not req_data.get('memory'): return self.respond_with_json(400, {'error': 'memory is required'})\n")
        break

api_text = "".join(lines)
boot_code = """
try:
    import os, json
    if os.path.exists('var/engine.json'):
        with open('var/engine.json', 'r+') as f:
            db = json.load(f)
            changed = False
            for n, c in db.get('containers', {}).items():
                if c.get('status') == 'running' and not os.path.exists(f'/sys/fs/cgroup/vcontainer/{n}'):
                    c['status'] = 'stopped'
                    changed = True
            if changed:
                f.seek(0); f.truncate(); json.dump(db, f)
except Exception: pass
"""
api_text = re.sub(r"(if __name__\s*==\s*['\"]__main__['\"]\:)", boot_code + r"\n\1", api_text)
with open("backend/api.py", "w") as f: f.write(api_text)

# 2. Patch engine.py (Issue 21)
with open("backend/engine.py", "r") as f: elines = f.readlines()
for i, line in enumerate(elines):
    if "meta = core.get_image_metadata" in line:
        indent = line[:len(line) - len(line.lstrip())]
        elines.insert(i+1, indent + "if not command:\n" + indent + "    cmd = meta.get('config', {}).get('Cmd')\n" + indent + "    command = cmd if cmd else ['/bin/sh']\n")
        break
with open("backend/engine.py", "w") as f: f.writelines(elines)

# 3. Patch gui/index.html
with open("gui/index.html", "r") as f: html = f.read()
html = re.sub(r'(<input\s+id="name"[^>]+required\s*/>\s*</label>)', r'\1\n        <label>Memory Limit<input id="memory" name="memory" value="250M" required /></label>', html)
html = html.replace('<div class="header-right">', '<div class="header-right">\n        <button id="launch-blogdrop">Launch BlogDrop</button>')
with open("gui/index.html", "w") as f: f.write(html)

# 4. Patch gui/app.js
with open("gui/app.js", "r") as f: js = f.read()
js = js.replace('const payload = {', 'const payload = { memory: $("#memory").value,')
bd_code = """
async function launchBlogDrop() {
  const btn = document.getElementById("launch-blogdrop");
  if(!btn) return;
  btn.disabled = true; btn.textContent = "Launching...";
  try {
    await api("/containers", { method: "POST", body: { name: "blogdrop-db", image: "mysql", command: ["docker-entrypoint.sh", "mysqld"], memory: "1G", pids: 256, ip: "10.88.0.30", env: ["MYSQL_ROOT_PASSWORD=change-root-password", "MYSQL_DATABASE=blogdrop_db", "MYSQL_USER=blogdrop", "MYSQL_PASSWORD=change-database-password"], volumes: ["blogdrop-db:/var/lib/mysql", "blogdrop-db-init:/docker-entrypoint-initdb.d"], network: "bridge" }});
    await new Promise(r => setTimeout(r, 2000));
    await api("/containers", { method: "POST", body: { name: "blogdrop-backend", image: "node", command: ["/bin/sh", "-c", "test -d /app/node_modules || npm --prefix /app install --omit=dev; exec node /app/server.js"], memory: "512M", pids: 128, ip: "10.88.0.31", env: ["PORT=3000", "DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "SESSION_SECRET=dev-secret-key"], volumes: ["blogdrop-backend:/app"], network: "bridge" }});
    await api("/containers", { method: "POST", body: { name: "blogdrop-frontend", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.32", volumes: ["blogdrop-frontend:/usr/share/nginx/html"], network: "bridge" }});
    await api("/containers", { method: "POST", body: { name: "blogdrop-nginx", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.33", ports: ["8085:80"], volumes: ["blogdrop-nginx:/etc/nginx/conf.d"], network: "bridge" }});
    if(typeof refresh === 'function') refresh();
  } catch(e) { alert("Launch failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Launch BlogDrop";
}
document.getElementById("launch-blogdrop")?.addEventListener("click", launchBlogDrop);
"""
with open("gui/app.js", "w") as f: f.write(js + "\n" + bd_code)
