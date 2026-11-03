"""Install the restricted FastAPI backend inside an already provisioned WSL distro.

Run from Windows: python setup_api_service.py
Uses VCONTAINER_WSL_DISTRO / VCONTAINER_WSL_USER (Ubuntu / vcdev by default).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from helper_package import downloaded_helpers

SCRIPT = r'''
set -euo pipefail
user="$1"
source="$2"
helper="$3"
control="$4"
wrapper="$5"
image_control="$6"
volume_control="$7"
gui_source="$8"
compose_helper="$9"
test "$(id -u "$user")" -ne 0
home=$(getent passwd "$user" | cut -d: -f6)
group=$(id -gn "$user")
api_dir="$home/vcontainer-api"
install -d -o "$user" -g "$group" -m 0700 /var/lib/vcontainer/compose
install -o root -g root -m 0755 "$helper" /usr/local/sbin/vcontainer-read
sed -i 's/\r$//' /usr/local/sbin/vcontainer-read
python3 -m py_compile /usr/local/sbin/vcontainer-read
install -o root -g root -m 0755 "$control" /usr/local/sbin/vcontainer-control
sed -i 's/\r$//' /usr/local/sbin/vcontainer-control
python3 -m py_compile /usr/local/sbin/vcontainer-control
install -o root -g root -m 0755 "$image_control" /usr/local/sbin/vcontainer-image-control
sed -i 's/\r$//' /usr/local/sbin/vcontainer-image-control
python3 -m py_compile /usr/local/sbin/vcontainer-image-control
install -o root -g root -m 0755 "$volume_control" /usr/local/sbin/vcontainer-volume-control
sed -i 's/\r$//' /usr/local/sbin/vcontainer-volume-control
python3 -m py_compile /usr/local/sbin/vcontainer-volume-control
install -o root -g root -m 0755 "$wrapper" /opt/vcontainer/bin/vcontainer-cli
sed -i 's/\r$//' /opt/vcontainer/bin/vcontainer-cli
install -d -o root -g root -m 0755 /opt/vcontainer/libexec
install -o root -g root -m 0755 \
    "$compose_helper" /opt/vcontainer/libexec/vcontainer-compose

policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vcontainer-read\n' "$user" > "$policy"
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vcontainer-control\n' "$user" >> "$policy"
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vcontainer-image-control\n' "$user" >> "$policy"
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vcontainer-volume-control\n' "$user" >> "$policy"
visudo -cf "$policy"
install -o root -g root -m 0440 "$policy" /etc/sudoers.d/vcontainer-read
visudo -c
runuser -u "$user" -- sudo -n /usr/local/sbin/vcontainer-read images >/dev/null

if ! command -v curl >/dev/null || ! command -v socat >/dev/null; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates socat
fi

install -d -o "$user" -g "$group" "$api_dir" "$api_dir/src" "$api_dir/gui"
cp -R "$source/src/." "$api_dir/src/"
cp -R "$gui_source/." "$api_dir/gui/"
cp "$source/pyproject.toml" "$source/uv.lock" "$source/README.md" "$api_dir/"
chown -R "$user:$group" "$api_dir"

runuser -u "$user" -- env HOME="$home" bash -s -- "$api_dir" <<'USER_SETUP'
set -euo pipefail
if [ ! -x "$HOME/.local/bin/uv" ]; then
    installer=$(mktemp)
    trap 'rm -f "$installer"' EXIT
    curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o "$installer"
    UV_NO_MODIFY_PATH=1 sh "$installer"
fi
cd "$1"
"$HOME/.local/bin/uv" sync --locked --no-dev --python 3.12
.venv/bin/python -c 'from vcontainer_api.main import app; print("Linux API imports successfully")'
USER_SETUP

cat > /etc/systemd/system/vcontainer-api.service <<UNIT
[Unit]
Description=Vcontainer API
After=network.target

[Service]
Type=simple
User=$user
WorkingDirectory=$api_dir
Environment=PYTHONUNBUFFERED=1
Environment=VCONTAINER_GUI_DIR=$api_dir/gui
ExecStart="$api_dir/.venv/bin/python" -m uvicorn vcontainer_api.main:app --host 127.0.0.1 --port 8010
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 /etc/systemd/system/vcontainer-api.service
systemctl daemon-reload
systemctl enable vcontainer-api.service
systemctl restart vcontainer-api.service

if ! runuser -u "$user" -- "$api_dir/.venv/bin/python" - <<'VERIFY'
import json
import time
import urllib.request

last_error = None
for _ in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=1) as response:
            data = json.load(response)
        if data.get('service') == 'vcontainer' and data.get('status') == 'ok':
            break
        raise RuntimeError('Unexpected health response')
    except (OSError, ValueError, RuntimeError) as error:
        last_error = error
        time.sleep(0.5)
else:
    raise SystemExit(f'API failed readiness check: {last_error}')

for path in ('images', 'containers'):
    with urllib.request.urlopen(f'http://127.0.0.1:8010/{path}', timeout=30) as response:
        data = json.load(response)
    print(f'{path}: {len(data[path])} entries')
VERIFY
then
    journalctl -u vcontainer-api.service -n 40 --no-pager >&2
    exit 1
fi
systemctl is-active vcontainer-api.service
'''


def install():
    if sys.platform != "win32":
        raise SystemExit("Run this installer from Windows Python.")
    distro = os.getenv("VCONTAINER_WSL_DISTRO", "Ubuntu")
    user = os.getenv("VCONTAINER_WSL_USER", "vcdev")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user) or user == "root":
        raise SystemExit("Choose a normal Linux user for VCONTAINER_WSL_USER.")
    root = Path(__file__).resolve().parent
    source = root / "backend" / "api"
    wrapper = root / "backend" / "runtime" / "run_container.sh"
    compose_helper = root / "backend" / "helpers" / "vcontainer-compose"
    gui = root / "gui"
    for name in (
        "pyproject.toml",
        "uv.lock",
        "src/vcontainer_api/main.py",
    ):
        if not (source / name).is_file():
            raise SystemExit(f"Missing API source: {source / name}")
    for path in (wrapper, compose_helper, gui / "index.html"):
        if not path.is_file():
            raise SystemExit(f"Missing installation source: {path}")
    wsl = ["wsl.exe", "-d", distro, "-u", "root", "--exec"]
    linux_source = subprocess.check_output(
        wsl + ["wslpath", "-a", "-u", str(source)], text=True,
    ).strip()
    linux_wrapper = subprocess.check_output(
        wsl + ["wslpath", "-a", "-u", str(wrapper)], text=True,
    ).strip()
    linux_gui = subprocess.check_output(
        wsl + ["wslpath", "-a", "-u", str(gui)], text=True,
    ).strip()
    linux_compose_helper = subprocess.check_output(
        wsl + ["wslpath", "-a", "-u", str(compose_helper)], text=True,
    ).strip()
    with downloaded_helpers() as helpers:
        linux_helpers = subprocess.check_output(
            wsl + ["wslpath", "-a", "-u", str(helpers)], text=True,
        ).strip()
        subprocess.run(
            wsl + [
                "bash", "-s", "--", user, linux_source,
                f"{linux_helpers}/vcontainer-read",
                f"{linux_helpers}/vcontainer-control",
                linux_wrapper,
                f"{linux_helpers}/vcontainer-image-control",
                f"{linux_helpers}/vcontainer-volume-control",
                linux_gui,
                linux_compose_helper,
            ],
            input=SCRIPT.replace("\r\n", "\n").encode("utf-8"),
            check=True,
        )
    print("API service installed: http://localhost:8010/docs")


if __name__ == "__main__":
    try:
        install()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"API service installation failed: {error}")
