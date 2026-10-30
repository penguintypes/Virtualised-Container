import re
with open("gui/app.js", "r") as f: js = f.read()

# 1. Add missing memory limit to Quick Start buttons
js = js.replace('image: button.dataset.img,', 'image: button.dataset.img,\n          memory: "250M",')

# 2. Rewrite Launch BlogDrop to use proper native fetch + JSON.stringify
old_bd = re.search(r'(window\.)?launchBlogDrop = async function\(\) \{.*?\}', js, re.DOTALL)

new_bd = """window.launchBlogDrop = async function() {
  const btn = document.getElementById("launch-blogdrop");
  if(!btn) return;
  btn.disabled = true; btn.textContent = "Launching...";
  const doReq = async (p) => {
    const r = await fetch("/containers", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(p) });
    if (!r.ok) throw new Error((await r.json()).error || "Failed");
  };
  try {
    await doReq({ name: "blogdrop-db", image: "mysql", command: ["docker-entrypoint.sh", "mysqld"], memory: "1G", pids: 256, ip: "10.88.0.30", env: ["MYSQL_ROOT_PASSWORD=change-root-password", "MYSQL_DATABASE=blogdrop_db", "MYSQL_USER=blogdrop", "MYSQL_PASSWORD=change-database-password"], volumes: ["blogdrop-db:/var/lib/mysql", "blogdrop-db-init:/docker-entrypoint-initdb.d"], network: "bridge" });
    await new Promise(r => setTimeout(r, 2000));
    await doReq({ name: "blogdrop-backend", image: "node", command: ["/bin/sh", "-c", "test -d /app/node_modules || npm --prefix /app install --omit=dev; exec node /app/server.js"], memory: "512M", pids: 128, ip: "10.88.0.31", env: ["PORT=3000", "DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "SESSION_SECRET=dev-secret-key"], volumes: ["blogdrop-backend:/app"], network: "bridge" });
    await doReq({ name: "blogdrop-frontend", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.32", volumes: ["blogdrop-frontend:/usr/share/nginx/html"], network: "bridge" });
    await doReq({ name: "blogdrop-nginx", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "128M", pids: 64, ip: "10.88.0.33", ports: ["8085:80"], volumes: ["blogdrop-nginx:/etc/nginx/conf.d"], network: "bridge" });
    if(typeof refresh === 'function') refresh();
  } catch(e) { alert("Launch failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Launch BlogDrop";
}"""

if old_bd:
    js = js.replace(old_bd.group(0), new_bd)
else:
    js += "\n" + new_bd

with open("gui/app.js", "w") as f: f.write(js)
