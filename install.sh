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
find "$root/engine" -type f -name '*.sh' -exec sed -i 's/\r$//' {} + -exec chmod 755 {} +
getent hosts dl-cdn.alpinelinux.org >/dev/null || echo 'DNS check failed: fix WSL DNS, then rerun install.sh.' >&2
make -C "$root/engine"
sudo mkdir -p /var/lib/vcontainer/images /var/lib/vcontainer/containers /var/lib/vcontainer/volumes

# --- PATH 2 SECURITY BOUNDARY ---
sudo rm -rf /usr/local/libexec/vcontainer
sudo mkdir -p /usr/local/libexec/vcontainer
sudo cp -a "$root/engine/." "/usr/local/libexec/vcontainer/"
sudo chown -R root:root /usr/local/libexec/vcontainer
sudo chmod -R 755 /usr/local/libexec/vcontainer
target="$HOME/vcontainer"

if [ "$root" != "$target" ]; then mkdir -p "$target"; cp -a "$root"/. "$target"/; fi
if [ -t 0 ]; then read -r -p 'Install personal-machine sudoers NOPASSWD rule for vcontainer? [y/N] ' answer; else answer=Y; fi
if [[ ${answer:-N} =~ ^[Yy]$ ]]; then echo "$user ALL=(root) NOPASSWD: /usr/local/libexec/vcontainer/run_container.sh, /usr/local/libexec/vcontainer/build_helper.sh" | sudo tee /etc/sudoers.d/vcontainer >/dev/null; sudo chmod 440 /etc/sudoers.d/vcontainer; fi
if ! sudo test -d /var/lib/vcontainer/images/alpine/rootfs; then sudo "$root/engine/src/image.sh" pull alpine; fi
sudo chmod -R a+rX /var/lib/vcontainer/images
echo '{"id":"alpine","name":"alpine","created":"2026-10-23T00:00:00Z","size":8427299,"cmd":["/bin/sh"],"env":{}}' | sudo tee /var/lib/vcontainer/images/alpine/meta.json > /dev/null
PYTHONPATH="$root" python3 - <<'PY'
import os
from backend import engine
root = os.environ.get("PYTHONPATH", ".")
try: engine.upload_image("blog", os.path.join(root, "samples/blog/blog.tar"))
except RuntimeError: pass
try: engine.upload_image("runner", os.path.join(root, "samples/runner/runner.tar"))
except RuntimeError: pass
PY
sudo tee /usr/local/bin/vc >/dev/null <<EOF
#!/usr/bin/env bash
exec /usr/local/libexec/vcontainer/run_container.sh "\$@"
EOF
sudo chmod 755 /usr/local/bin/vc
printf 'Installed. Run: %s\n' "$target/verify.sh"
