import re

with open('gui/app.js', 'r') as f:
    content = f.read()

# The previous patch was truncated. We strip the broken function and rewrite it entirely.
start_idx = content.find('window.launchBlogDrop = async function()')
if start_idx != -1:
    content = content[:start_idx]

new_func = """window.launchBlogDrop = async function() {
  const btn = document.getElementById("launch-blogdrop");
  if(!btn) return;
  btn.disabled = true; btn.textContent = "Launching...";
  
  const doReq = async (p) => {
    const r = await fetch("/containers", { 
      method: "POST", 
      headers: {"Content-Type": "application/json"}, 
      body: JSON.stringify(p) 
    });
    if (!r.ok) throw new Error((await r.json()).error || "Failed");
  };

  try {
    await doReq({ name: "blogdrop-db", image: "mysql", command: ["docker-entrypoint.sh", "mysqld"], memory: "1G", pids: 256, ip: "10.88.0.30", env: ["MYSQL_ROOT_PASSWORD=change-root-password", "MYSQL_DATABASE=blogdrop_db", "MYSQL_USER=blogdrop", "MYSQL_PASSWORD=change-database-password"], volumes: ["blogdrop-db:/var/lib/mysql", "blogdrop-db-init:/docker-entrypoint-initdb.d"], network: "bridge" });
    await doReq({ name: "blogdrop-backend", image: "node", command: ["npm", "start"], memory: "500M", pids: 256, ip: "10.88.0.31", env: ["DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "PORT=3000"], network: "bridge" });
    await doReq({ name: "blogdrop-frontend", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "250M", pids: 256, ip: "10.88.0.32", volumes: ["blogdrop-frontend:/usr/share/nginx/html"], network: "bridge" });
    await doReq({ name: "blogdrop-gateway", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "250M", pids: 256, ip: "10.88.0.33", ports: [{ host_port: 8085, container_port: 80 }], volumes: ["blogdrop-gateway:/etc/nginx/conf.d"], network: "bridge" });
    alert("BlogDrop launched! Gateway available on port 8085.");
  } catch (err) {
    alert("Launch failed: " + err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Launch BlogDrop";
    if(typeof loadContainers === 'function') loadContainers();
  }
};
"""

with open('gui/app.js', 'w') as f:
    f.write(content + new_func)
