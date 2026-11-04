import configparser
import os
import sys
from pathlib import Path


def find_config_file() -> Path | None:
    configured = os.getenv("VCONTAINER_CONFIG")
    if configured:
        return Path(configured)

    candidates = [
        Path.cwd() / "vcontainer.config",
        Path(sys.executable).resolve().parent / "vcontainer.config",
        Path(__file__).resolve().parents[3] / "vcontainer.config",
    ]
    return next((path for path in candidates if path.is_file()), None)


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    path = find_config_file()
    if path is not None:
        config.read(path, encoding="utf-8")
    return config


CONFIG = load_config()
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
WSL_DISTRO = os.getenv(
    "VCONTAINER_WSL_DISTRO",
    CONFIG.get("wsl", "distribution", fallback="Ubuntu"),
)
WSL_USER = os.getenv(
    "VCONTAINER_WSL_USER",
    CONFIG.get("wsl", "user", fallback="vcdev"),
)
KEEP_ALIVE_API = (
    "flock",
    "-n",
    "/run/vcontainer-windows-keepalive.lock",
    "sleep",
    "infinity",
)
START_API = ("systemctl", "start", "vcontainer-api")
ENGINE_RUN = ("/opt/vcontainer/bin/vcontainer-cli",)
