#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
[ "$(uname -s)" = Linux ] || { echo 'Run inside WSL2 Ubuntu.' >&2; exit 2; }
command -v apt-get >/dev/null || { echo 'Ubuntu apt-get is required.' >&2; exit 2; }
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential libseccomp-dev skopeo umoci iproute2 iptables util-linux python3 curl socat
user=${SUDO_USER:-$USER}
grep -q "^$user:" /etc/subuid || sudo usermod --add-subuids 100000-165535 "$user"
grep -q "^$user:" /etc/subgid || sudo usermod --add-subgids 100000-165535 "$user"
find "$root/backend/runtime" -type f -name '*.sh' -exec sed -i 's/\r$//' {} + -exec chmod 755 {} +
getent hosts dl-cdn.alpinelinux.org >/dev/null || echo 'DNS check failed: fix WSL DNS, then rerun install.sh.' >&2
make -C "$root/backend/runtime"
sudo mkdir -p /var/lib/vcontainer/images /var/lib/vcontainer/containers /var/lib/vcontainer/volumes

# --- PATH 2 SECURITY BOUNDARY ---
sudo rm -rf /usr/local/libexec/vcontainer
sudo mkdir -p /usr/local/libexec/vcontainer
sudo cp -a "$root/backend/runtime/." "/usr/local/libexec/vcontainer/"
sudo chown -R root:root /usr/local/libexec/vcontainer
sudo chmod -R 755 /usr/local/libexec/vcontainer
target="$HOME/vcontainer"

if [ "$root" != "$target" ]; then mkdir -p "$target"; cp -a "$root"/. "$target"/; fi
if [ -t 0 ]; then read -r -p "Install personal-machine sudoers NOPASSWD rule for vcontainer? [y/N] " answer; elif [ -r /dev/tty ]; then read -r -p "Install personal-machine sudoers NOPASSWD rule for vcontainer? [y/N] " answer </dev/tty; else answer=${VC_SUDOERS:-N}; fi
if [[ ${answer:-N} =~ ^[Yy]$ ]]; then echo "$user ALL=(root) NOPASSWD: /usr/local/libexec/vcontainer/run_container.sh, /usr/local/libexec/vcontainer/build_helper.sh" | sudo tee /etc/sudoers.d/vcontainer >/dev/null; sudo chmod 440 /etc/sudoers.d/vcontainer; fi
if ! sudo test -d /var/lib/vcontainer/images/alpine/rootfs; then sudo "$root/backend/runtime/src/image.sh" pull alpine; fi
sudo chmod -R a+rX /var/lib/vcontainer/images
echo '{"id":"alpine","name":"alpine","created":"2026-10-23T00:00:00Z","size":8427299,"cmd":["/bin/sh"],"env":{}}' | sudo tee /var/lib/vcontainer/images/alpine/meta.json > /dev/null
sudo rm -rf /var/lib/vcontainer/samples
sudo mkdir -p /var/lib/vcontainer/samples
sudo cp -a "$root/backend/samples/blog" "$root/backend/samples/runner" /var/lib/vcontainer/samples/
sudo chmod -R a+rX /var/lib/vcontainer/samples
# seed blogdrop volumes
seed() { v="/var/lib/vcontainer/volumes/$1/_data"; sudo mkdir -p "$v"; if [ -d "$2" ] && [ -z "$(sudo ls -A "$v")" ]; then sudo cp -a "$2"/. "$v"/; fi; }
bd="$root/backend/samples/blogdrop"
seed blogdrop-db ""
seed blogdrop-db-init "$bd/db-init"
seed blogdrop-frontend "$bd/frontend"
seed blogdrop-nginx "$bd/nginx"
seed blogdrop-backend "$bd/backend"
# end seed
PYTHONPATH="$root" python3 - <<'PY'
import os
from backend import engine
root = os.environ.get("PYTHONPATH", ".")
try: engine._call("delete", "blog")
except Exception: pass
try: engine._call("delete", "runner")
except Exception: pass
engine.build("/var/lib/vcontainer/samples/blog/Vcfile")
engine.build("/var/lib/vcontainer/samples/runner/Vcfile")
PY
sudo tee /usr/local/bin/vc >/dev/null <<EOF
#!/usr/bin/env bash
exec /usr/local/libexec/vcontainer/run_container.sh "\$@"
EOF
sudo chmod 755 /usr/local/bin/vc
printf 'Installed. Run: %s\n' "$target/backend/tests/verify.sh"
