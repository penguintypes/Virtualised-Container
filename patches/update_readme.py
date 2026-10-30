import re

with open('README.md', 'r') as f:
    content = f.read()

# Update Quick Start to mention BlogDrop
content = content.replace(
    "- **Start:** `./start.sh` launches only the dashboard. Start the demo containers from Quick start on Home (blog on 8081, runner on 8082).",
    "- **Start:** `./start.sh` launches only the dashboard. Start the demo containers from Quick start on Home (blog on 8081, runner on 8082), or launch the complete BlogDrop web stack via the dashboard button (gateway on 8085)."
)

# Update the POST /containers API documentation to reflect the new memory requirement and payload format
content = re.sub(
    r'\| POST \| `/containers` \| Create/run container: `\{"name":"demo","image":"alpine","command":\["/bin/sh","-c","\.\.\."\]\}`; optional `memory`, `cpus`, `pids`, `port` \|',
    r'| POST | `/containers` | Create/run container: `{"name":"demo","image":"alpine","memory":"250M"}`; `memory` is REQUIRED. Optional arrays: `command`, `volumes`, `env`, `ports`. Optional fields: `cpus`, `pids`, `network`, `ip` |',
    content
)

with open('README.md', 'w') as f:
    f.write(content)
