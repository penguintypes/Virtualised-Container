import re

with open('gui/app.js', 'r') as f:
    content = f.read()

# Fix Node Backend: Mount blogdrop-backend to /app and run npm start from inside it
content = re.sub(
    r'await doReq\(\{ name: "blogdrop-backend".*?\);',
    r'await doReq({ name: "blogdrop-backend", image: "node", command: ["sh", "-c", "cd /app && npm start"], memory: "500M", pids: 256, ip: "10.88.0.31", env: ["DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "PORT=3000"], volumes: ["blogdrop-backend:/app"], network: "bridge" });',
    content
)

# Fix Gateway: Map the existing blogdrop-nginx volume instead of the non-existent blogdrop-gateway volume, and fix port syntax
content = re.sub(
    r'await doReq\(\{ name: "blogdrop-gateway".*?\);',
    r'await doReq({ name: "blogdrop-gateway", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "250M", pids: 256, ip: "10.88.0.33", ports: ["8085:80"], volumes: ["blogdrop-nginx:/etc/nginx/conf.d"], network: "bridge" });',
    content
)

with open('gui/app.js', 'w') as f:
    f.write(content)
