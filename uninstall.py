import argparse
import configparser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "vcontainer.config"


def settings():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH, encoding="utf-8")
    distro = os.getenv(
        "VCONTAINER_WSL_DISTRO",
        config.get("wsl", "distribution", fallback="Ubuntu"),
    )
    user = os.getenv(
        "VCONTAINER_WSL_USER",
        config.get("wsl", "user", fallback="vcdev"),
    )
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user) or user == "root":
        raise SystemExit("Invalid WSL user in vcontainer.config.")
    return distro, user


def remove_user_path_entry():
    script = ROOT / "client" / "scripts" / "vcontainer-cli-unglobal.ps1"
    if not script.is_file() or not shutil.which("powershell.exe"):
        return
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=True,
    )


def uninstall_linux(distro, user, keep_data):
    script = r"""
set -euo pipefail

user="$1"
keep_data="$2"

echo "Stopping Vcontainer services..."
systemctl disable --now vcontainer-api.service >/dev/null 2>&1 || true

for unit_path in /etc/systemd/system/vcontainer-port-*.service; do
    [ -f "$unit_path" ] || continue
    unit_name=${unit_path##*/}
    systemctl disable --now "$unit_name" >/dev/null 2>&1 || true
    rm -f -- "$unit_path"
done

if [ -d /sys/fs/cgroup/vcontainer ]; then
    for group in /sys/fs/cgroup/vcontainer/*; do
        [ -d "$group" ] || continue
        if [ -w "$group/cgroup.kill" ]; then
            printf '1\n' > "$group/cgroup.kill" || true
        fi
    done
    sleep 1
    for group in /sys/fs/cgroup/vcontainer/*; do
        [ -d "$group" ] || continue
        rmdir -- "$group" 2>/dev/null || true
    done
    rmdir /sys/fs/cgroup/vcontainer 2>/dev/null || true
fi

home=$(getent passwd "$user" | cut -d: -f6 || true)
if [ -n "$home" ]; then
    api_dir="$home/vcontainer-api"
    case "$api_dir" in
        /home/*/vcontainer-api) rm -rf -- "$api_dir" ;;
        *) echo "Refusing unexpected API directory: $api_dir" >&2; exit 1 ;;
    esac
fi

rm -f -- /etc/systemd/system/vcontainer-api.service
rm -f -- /etc/sudoers.d/vcontainer-read
rm -f -- /usr/local/sbin/vcontainer-read
rm -f -- /usr/local/sbin/vcontainer-control
rm -f -- /usr/local/sbin/vcontainer-image-control
rm -f -- /usr/local/sbin/vcontainer-volume-control
if [ -d /usr/local/sbin/__pycache__ ]; then
    find /usr/local/sbin/__pycache__ -maxdepth 1 -type f \
        -name 'vcontainer-*.pyc' -delete
fi
rm -rf -- /opt/vcontainer
rm -f -- /run/vcontainer-windows-keepalive.lock

if [ "$keep_data" = "no" ]; then
    rm -rf -- /var/lib/vcontainer
else
    echo "Preserved /var/lib/vcontainer"
fi

systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true
echo "Vcontainer Linux components removed."
"""
    subprocess.run(
        [
            "wsl.exe",
            "-d",
            distro,
            "-u",
            "root",
            "--exec",
            "bash",
            "-s",
            "--",
            user,
            "yes" if keep_data else "no",
        ],
        input=script.replace("\r\n", "\n").encode("utf-8"),
        check=True,
    )


def confirmation(distro, keep_data):
    print(f"WSL distribution: {distro}")
    print("The API service, runtime, helpers and port services will be removed.")
    if keep_data:
        print("Images, volumes, containers and Compose projects will be preserved.")
    else:
        print("Images, volumes, containers and Compose projects will be deleted.")
    print("The WSL distribution, WSL user, source files and shared packages remain.")
    return input('Type "REMOVE VCONTAINER" to continue: ').strip() == (
        "REMOVE VCONTAINER"
    )


def main():
    parser = argparse.ArgumentParser(description="Uninstall Vcontainer from WSL")
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="preserve /var/lib/vcontainer images, volumes and state",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive confirmation",
    )
    arguments = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("Run this uninstaller using Windows Python.")
    if not shutil.which("wsl.exe"):
        raise SystemExit("wsl.exe was not found.")

    distro, user = settings()
    if not arguments.yes and not confirmation(distro, arguments.keep_data):
        raise SystemExit("Uninstall cancelled.")

    remove_user_path_entry()
    uninstall_linux(distro, user, arguments.keep_data)
    print("Uninstall complete. Open a new terminal to refresh PATH.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"Uninstall stopped: command exited with code {error.returncode}"
        ) from error
    except OSError as error:
        raise SystemExit(f"Uninstall stopped: {error}") from error
