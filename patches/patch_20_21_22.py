import re, os
api_path = "backend/api.py"
engine_path = "backend/engine.py"
html_path = "gui/index.html"
js_path = "gui/app.js"

# --- 1. backend/api.py: POST /containers requires memory (Issue 20) ---
with open(api_path, "r") as f: api = f.read()
if "if 'memory' not in body:" not in api:
    api = re.sub(
        r"(def do_POST\(self\):\n\s+try:\n\s+body = .+\n\s+parsed_path = .+\n)",
        r"\1\n            if parsed_path == '/containers':\n                if 'memory' not in body:\n                    return self.respond_with_json(400, {'error': 'memory is required'})\n",
        api
    )
    with open(api_path, "w") as f: f.write(api)

# --- 2. backend/engine.py: Fallback to default CMD (Issue 21) ---
with open(engine_path, "r") as f: engine = f.read()
if "meta.get('config', {}).get('Cmd')" not in engine:
    engine = re.sub(
        r"(def run\(name, image, memory, pids=64, network=None, ip=None, volumes=None, env=None, command=None\):\n\s+core\.valid_name\(name\)\n\s+meta = core\.get_image_metadata\(image\))",
        r"\1\n    if not command:\n        cmd = meta.get('config', {}).get('Cmd')\n        command = cmd if cmd else ['/bin/sh']",
        engine
    )
    with open(engine_path, "w") as f: f.write(engine)

# --- 3. gui/index.html: Require memory in form & add BlogDrop button ---
with open(html_path, "r") as f: html = f.read()
if 'id="memory"' not in html:
    html = re.sub(
        r'(<input\s+id="name"\s+name="name"\s+pattern="\[a-zA-Z0-9_\]\+"\s+required\s+/>\s*</label>)',
        r'\1\n        <label>Memory Limit (e.g. 250M, 1G)<input id="memory" name="memory" value="250M" required /></label>',
        html
    )
if 'id="launch-blogdrop"' not in html:
    html = html.replace(
        '<div class="header-right">',
        '<div class="header-right">\n        <button id="launch-blogdrop">Launch BlogDrop</button>'
    )
with open(html_path, "w") as f: f.write(html)

# --- 4. gui/app.js: Pass memory & bind BlogDrop button ---
with open(js_path, "r") as f: js = f.read()
if 'memory: $("#memory").value' not in js:
    js = js.replace(
        'const payload = { name: $("#name").value, image: $("#image").value };',
        'const payload = { name: $("#name").value, image: $("#image").value, memory: $("#memory").value };'
    )
if 'launchBlogDrop' not in js:
    bd_code = """
async function launchBlogDrop() {
  const btn = $("#launch-blogdrop");
  btn.disabled = true; btn.textContent = "Launching...";
  try {
    const net = { network: "bridge" };
    await api("/containers", { method: "POST", body: { name: "blogdrop-db", image: "mysql", command: ["docker-entrypoint.sh", "mysqld"], memory: "1G", pids: 256, ip: "10.88.0.30", env: ["MYSQL_ROOT_PASSWORD=change-root-password", "MYSQL_DATABASE=blogdrop_db", "MYSQL_USER=blogdrop", "MYSQL_PASSWORD=change-database-password"], volumes: ["blogdrop-db:/var/lib/mysql", "blogdrop-db-init:/docker-entrypoint-initdb.d"], ...net }});
    await new Promise(r => setTimeout(r, 2000));
    await api("/containers", { method: "POST", body: { name: "blogdrop-backend", image: "node", command: ["/bin/sh", "-c", "test -d /app/node_modules || npm --prefix /app install --omit=dev; exec node /app/server.js"], memory: "512M", pids: 128, ip: "10.88.0.31", env: ["PORT=3000", "DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "SESSION_SECRET=dev-secret-key"], volumes: ["blogdrop-backend:/app"] }});
    await api("/containers", { method: "POST", body: { name: "blogdrop-frontend", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.32", volumes: ["blogdrop-frontend:/usr/share/nginx/html"] }});
    await api("/containers", { method: "POST", body: { name: "blogdrop-nginx", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.33", ports: ["8085:80"], volumes: ["blogdrop-nginx:/etc/nginx/conf.d"] }});
    refresh();
  } catch(e) { alert("BlogDrop launch failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Launch BlogDrop";
}
$("#launch-blogdrop")?.addEventListener("click", launchBlogDrop);
"""
    js = js.replace('$("#run-form").addEventListener("submit", createContainer);', '$("#run-form").addEventListener("submit", createContainer);\n' + bd_code)
with open(js_path, "w") as f: f.write(js)

print("Patched Issues 20, 21, and 22.")
