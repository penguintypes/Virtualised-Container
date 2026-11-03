
    
  
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT
API = PROJECT / "backend" / "api"
CLIENT = PROJECT / "client"
ENGINE = PROJECT / "backend" / "runtime"
GUI = PROJECT / "gui"
DISTRO = "Ubuntu"
USER = "vcdev"


def run(*command, cwd=None, capture=False, input_text=None):
    print("Running:", " ".join(command), flush=True)

    if input_text is not None:
        input_bytes = input_text.replace("\r\n", "\n").encode("utf-8")

        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            input=input_bytes,
            capture_output=capture,
        )

    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )

def ubuntu(*command, user="root", capture=False, input_text=None):
    return run(
        "wsl.exe",
        "-d", DISTRO,
        "-u", user,
        "--exec",
        *command,
        capture=capture,
        input_text=input_text,
    )


def linux_path(path):
    result = ubuntu(
        "wslpath", "-a", "-u", str(path),
        capture=True,
    )
    return result.stdout.strip()


def setup_linux():
    engine_path = linux_path(ENGINE)

    script = r"""
set -euo pipefail

user="$1"
engine="$2"

echo "Installing Linux dependencies..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    --no-install-recommends \
    build-essential libseccomp-dev \
    skopeo umoci iproute2 iptables util-linux socat \
    python3 sudo uidmap curl ca-certificates

echo "Preparing development user..."
if ! id "$user" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$user"
fi
usermod -aG sudo "$user"

# Require usable subordinate UID/GID ranges.
for file in /etc/subuid /etc/subgid; do
    if ! awk -F: -v user="$user" \
        '$1 == user && $3 >= 65535 { found=1 }
         END { exit !found }' "$file"; then
        echo "Missing subordinate range for $user in $file." >&2
        echo "Configure an unused range, then rerun setup." >&2
        exit 1
    fi
done

echo "Checking kernel features..."
test "$(stat -fc %T /sys/fs/cgroup)" = "cgroup2fs"
grep -qw overlay /proc/filesystems
for controller in cpu memory pids; do

