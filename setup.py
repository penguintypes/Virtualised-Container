import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Works whether setup.py is in the outer or inner folder.
PROJECT = ROOT
'''if not (PROJECT / "api").is_dir():
    PROJECT = ROOT / "Virtualised-Container-vcontainer-arm-_backend" '''

API = PROJECT / "api"
ENGINE = PROJECT / "Vcontainer(win)"
HELPER = API / "helpers" / "vcontainer-read"

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
    helper_path = linux_path(HELPER)

    script = r"""
set -euo pipefail

user="$1"
engine="$2"
helper="$3"

echo "Installing Linux dependencies..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential libseccomp-dev \
    skopeo umoci iproute2 iptables util-linux \
    python3 sudo uidmap

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
    grep -qw "$controller" /sys/fs/cgroup/cgroup.controllers
done

echo "Installing read-only API helper..."
install -o root -g root -m 0755 \
    "$helper" /usr/local/sbin/vcontainer-read

# Normalize Windows line endings in the installed copy.
sed -i 's/\r$//' /usr/local/sbin/vcontainer-read
python3 -m py_compile /usr/local/sbin/vcontainer-read

echo "Configuring restricted sudo permission..."
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT

printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vcontainer-read\n' \
    "$user" > "$policy"

visudo -cf "$policy"
install -o root -g root -m 0440 \
    "$policy" /etc/sudoers.d/vcontainer-read
visudo -c

echo "Building C engine in the Linux filesystem..."
work=$(mktemp -d /tmp/vcontainer-build.XXXXXX)
trap 'rm -f "$policy"; rm -rf "$work"' EXIT

cp -R "$engine/src" "$engine/include" "$work/"
cp "$engine/Makefile" "$work/"

find "$work/src" "$work/include" -type f \
    -exec sed -i 's/\r$//' {} +
sed -i 's/\r$//' "$work/Makefile"

make -C "$work"

install -d -o root -g root -m 0755 /opt/vcontainer/bin
install -o root -g root -m 0755 \
    "$work/build/vcontainer" /opt/vcontainer/bin/vcontainer

echo "Linux setup complete."
"""

    ubuntu(
        "bash", "-s", "--", USER, engine_path, helper_path,
        input_text=script,
    )


def setup_python():
    print("Installing uv if needed...")

    uv_command = shutil.which("uv")

    if uv_command:
        uv = [uv_command]
    else:
        run(sys.executable, "-m", "pip", "install", "uv")
        uv = [sys.executable, "-m", "uv"]

    # Dependencies come from api/pyproject.toml and uv.lock.
    run(*uv, "sync", cwd=API)

    run(
        *uv, "run", "python", "-c",
        "from api.main import app; print('API imports successfully')",
        cwd=API,
    )


def verify():
    print("Checking passwordless helper access...")

    for action in ("images", "ps"):
        result = ubuntu(
            "sudo", "-n",
            "/usr/local/sbin/vcontainer-read", action,
            user=USER,
            capture=True,
        )
        data = json.loads(result.stdout)
        print(f"{action}: {len(data)} entries")


def main():
    if sys.platform != "win32":
        raise SystemExit("Run this installer using Windows Python.")

    for path in (API / "pyproject.toml", ENGINE / "Makefile", HELPER):
        if not path.is_file():
            raise SystemExit(f"Required file missing: {path}")

    if not shutil.which("wsl.exe"):
        raise SystemExit(
            "Install Ubuntu on WSL 2 first: wsl --install -d Ubuntu"
        )

    print("Checking WSL...")
    run("wsl.exe", "--list", "--verbose")

    # Confirm Ubuntu can start before making changes.
    ubuntu("uname", "-m")

    setup_linux()
    setup_python()
    verify()

    print("\nSetup complete.")
    print(f"API directory: {API}")
    print("Start the API from that directory:")
    print(
        "uv run uvicorn api.main:app "
        "--host 127.0.0.1 --port 8001 --reload"
    )
    print("\nIf vcdev was newly created, set its password in Ubuntu:")
    print("  wsl -d Ubuntu -u root --exec passwd vcdev")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise SystemExit(
            f"Setup stopped: command exited with code {error.returncode}"
        )
    except (OSError, ValueError) as error:
        raise SystemExit(f"Setup stopped: {error}")