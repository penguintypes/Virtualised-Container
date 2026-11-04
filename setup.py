import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = ROOT / "backend" / "api"
CLIENT = ROOT / "client"
ENGINE = ROOT / "backend" / "runtime"
CONFIG_PATH = ROOT / "vcontainer.config"

CONFIG = configparser.ConfigParser()
CONFIG.read(CONFIG_PATH, encoding="utf-8")
DISTRO = os.getenv(
    "VCONTAINER_WSL_DISTRO",
    CONFIG.get("wsl", "distribution", fallback="Ubuntu"),
)
USER = os.getenv(
    "VCONTAINER_WSL_USER",
    CONFIG.get("wsl", "user", fallback="vcdev"),
)
API_HOST = os.getenv(
    "VCONTAINER_API_HOST",
    CONFIG.get("api", "host", fallback="127.0.0.1"),
)
API_PORT = int(
    os.getenv(
        "VCONTAINER_API_PORT",
        CONFIG.get("api", "port", fallback="8010"),
    )
)


def run(*command, cwd=None, capture=False, input_text=None):
    print("Running:", " ".join(command), flush=True)
    if input_text is not None:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            input=input_text.replace("\r\n", "\n").encode("utf-8"),
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
        "-d",
        DISTRO,
        "-u",
        user,
        "--exec",
        *command,
        capture=capture,
        input_text=input_text,
    )


def linux_path(path):
    result = ubuntu("wslpath", "-a", "-u", str(path), capture=True)
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

for file in /etc/subuid /etc/subgid; do
    if ! awk -F: -v user="$user" \
        '$1 == user && $3 >= 65535 { found=1 }
         END { exit !found }' "$file"; then
        echo "Missing subordinate range for $user in $file." >&2
        exit 1
    fi
done

echo "Checking kernel features..."
test "$(stat -fc %T /sys/fs/cgroup)" = "cgroup2fs"
grep -qw overlay /proc/filesystems
for controller in cpu memory pids; do
    grep -qw "$controller" /sys/fs/cgroup/cgroup.controllers
done

echo "Building C engine..."
work=$(mktemp -d /tmp/vcontainer-build.XXXXXX)
trap 'rm -rf "$work"' EXIT
cp -R "$engine/src" "$engine/include" "$work/"
cp "$engine/Makefile" "$work/"
find "$work/src" "$work/include" -type f -exec sed -i 's/\r$//' {} +
sed -i 's/\r$//' "$work/Makefile"
make -C "$work"

install -d -o root -g root -m 0755 /opt/vcontainer/bin
install -o root -g root -m 0755 \
    "$work/build/vcontainer" /opt/vcontainer/bin/vcontainer
install -o root -g root -m 0755 \
    "$engine/run_container.sh" /opt/vcontainer/bin/vcontainer-cli
sed -i 's/\r$//' /opt/vcontainer/bin/vcontainer-cli

install -d -o root -g root -m 0755 /opt/vcontainer/libexec
for helper_name in cgroup.sh network.sh image.sh; do
    install -o root -g root -m 0755 \
        "$work/src/$helper_name" "/opt/vcontainer/libexec/$helper_name"
done
install -d -o root -g root -m 0755 \
    /var/lib/vcontainer/images /var/lib/vcontainer/oci

for pair in "vcontainer-images images" "vcontainer-oci oci"; do
    read -r old new <<< "$pair"
    if [ -d "/tmp/$old" ]; then
        for directory in "/tmp/$old"/*; do
            [ -d "$directory" ] || continue
            target="/var/lib/vcontainer/$new/${directory##*/}"
            [ -e "$target" ] || cp -a "$directory" "$target"
        done
    fi
done
echo "Linux engine setup complete."
"""
    ubuntu("bash", "-s", "--", USER, engine_path, input_text=script)


def setup_python():
    print("Preparing the Windows client...")
    uv_command = shutil.which("uv")
    if uv_command:
        uv = [uv_command]
    else:
        run(sys.executable, "-m", "pip", "install", "uv")
        uv = [sys.executable, "-m", "uv"]
    run(*uv, "sync", "--locked", "--no-dev", cwd=CLIENT)


def verify():
    print("Checking passwordless helper access...")
    for action in ("images", "ps"):
        result = ubuntu(
            "sudo",
            "-n",
            "/usr/local/sbin/vcontainer-read",
            action,
            user=USER,
            capture=True,
        )
        data = json.loads(result.stdout)
        print(f"{action}: {len(data)} entries")

    verification = ROOT / "tests" / "verify_install.sh"
    if not verification.is_file():
        raise RuntimeError(f"Installation verification is missing: {verification}")
    print("Running post-install verification...")
    ubuntu("bash", linux_path(verification))


def validate_configuration():
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", USER) or USER == "root":
        raise SystemExit("Choose a normal WSL user in vcontainer.config.")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", API_HOST):
        raise SystemExit("Invalid API host in vcontainer.config.")
    if not 1024 <= API_PORT <= 65535:
        raise SystemExit("API port must be between 1024 and 65535.")


def main():
    if sys.platform != "win32":
        raise SystemExit("Run this installer using Windows Python.")
    validate_configuration()

    required = (
        CONFIG_PATH,
        API / "pyproject.toml",
        CLIENT / "pyproject.toml",
        ENGINE / "Makefile",
        ENGINE / "run_container.sh",
        ROOT / "tests" / "verify_install.sh",
        ROOT / "setup_api_service.py",
    )
    for path in required:
        if not path.is_file():
            raise SystemExit(f"Required file missing: {path}")

    if not shutil.which("wsl.exe"):
        raise SystemExit(
            f"Install {DISTRO} on WSL 2 first: wsl --install -d {DISTRO}"
        )

    print("Checking WSL...")
    run("wsl.exe", "--list", "--verbose")
    ubuntu("uname", "-m")
    setup_linux()
    setup_python()
    run(sys.executable, str(ROOT / "setup_api_service.py"))
    verify()

    print("\nSetup complete.")
    print(f"WSL distribution: {DISTRO}")
    print(f"WSL user: {USER}")
    print(f"Browser GUI: http://{API_HOST}:{API_PORT}/")
    print(f"API documentation: http://{API_HOST}:{API_PORT}/docs")
    print(f"\nIf {USER} was newly created, set its password:")
    print(f"  wsl -d {DISTRO} -u root --exec passwd {USER}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise SystemExit(
            f"Setup stopped: command exited with code {error.returncode}"
        ) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Setup stopped: {error}") from error
