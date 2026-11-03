API_HOST = "127.0.0.1"
API_PORT = 8010
KEEP_ALIVE_API = (
    "flock",
    "-n",
    "/run/vcontainer-windows-keepalive.lock",
    "sleep",
    "infinity",
)
START_API = ("systemctl", "start", "vcontainer-api")
ENGINE_RUN = ("/opt/vcontainer/bin/vcontainer-cli",)
