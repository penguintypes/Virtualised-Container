"""Unit tests for the Windows Vcontainer CLI; WSL is always mocked."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "vcontainer.py"
sys.path.insert(0, str(LAUNCHER_PATH.parent / "src"))

from vcontainer_cli import cli as vcontainer  # noqa: E402


def test_command_constants_are_preserved():
    assert vcontainer.KEEP_ALIVE_API == (
        "flock",
        "-n",
        "/run/vcontainer-windows-keepalive.lock",
        "sleep",
        "infinity",
    )
    assert vcontainer.START_API == ("systemctl", "start", "vcontainer-api")
    assert vcontainer.ENGINE_RUN == ("/opt/vcontainer/bin/vcontainer-cli",)


def test_parse_run_supports_container_options():
    payload = vcontainer.parse_run(
        [
            "run",
            "nginx",
            "--name",
            "web",
            "--hostname",
            "website",
            "--memory-max",
            "256M",
            "--pids-max",
            "64",
            "--cpu-max",
            "50000",
            "100000",
            "--network",
            "bridge",
            "--ip",
            "10.88.0.20",
            "-e",
            "MODE=production",
            "-v",
            "site:/usr/share/nginx/html",
            "-p",
            "8080:80",
            "--",
            "nginx",
            "-g",
            "daemon off;",
        ]
    )

    assert payload == {
        "image": "nginx",
        "name": "web",
        "hostname": "website",
        "memory_max": "256M",
        "pids_max": 64,
        "cpu_quota": 50000,
        "cpu_period": 100000,
        "network": "bridge",
        "ip": "10.88.0.20",
        "environment": {"MODE": "production"},
        "volumes": [{"name": "site", "target": "/usr/share/nginx/html"}],
        "ports": [{"host_port": 8080, "container_port": 80}],
        "command": ["nginx", "-g", "daemon off;"],
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["run", "alpine"], "--name is required"),
        (["run", "alpine", "--name"], "Missing value"),
        (
            ["run", "alpine", "--name", "demo", "-e", "INVALID"],
            "Environment variable must use NAME=VALUE",
        ),
        (
            ["run", "alpine", "--name", "demo", "-v", "data"],
            "Volume must use NAME:/TARGET",
        ),
        (
            ["run", "alpine", "--name", "demo", "-p", "8080"],
            "Published port must use HOST_PORT:CONTAINER_PORT",
        ),
        (
            ["run", "alpine", "--name", "demo", "--"],
            "Command is missing after --",
        ),
    ],
)
def test_parse_run_rejects_invalid_arguments(arguments, message):
    with pytest.raises(ValueError, match=message):
        vcontainer.parse_run(arguments)


def test_api_request_returns_decoded_json(monkeypatch):
    response = Mock(status=200)
    response.read.return_value = json.dumps({"status": "ok"}).encode()
    connection = Mock()
    connection.getresponse.return_value = response
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(vcontainer.http.client, "HTTPConnection", constructor)

    result = vcontainer.api_request(
        "/containers",
        10,
        method="POST",
        payload={"name": "demo"},
    )

    assert result == {"status": "ok"}
    constructor.assert_called_once_with("127.0.0.1", 8010, timeout=10)
    connection.request.assert_called_once_with(
        "POST",
        "/containers",
        body=json.dumps({"name": "demo"}),
        headers={"Content-Type": "application/json"},
    )
    connection.close.assert_called_once()


def test_api_request_raises_backend_detail(monkeypatch):
    response = Mock(status=409)
    response.read.return_value = b'{"detail":"Container already exists"}'
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(
        vcontainer.http.client,
        "HTTPConnection",
        Mock(return_value=connection),
    )

    with pytest.raises(
        vcontainer.VcontainerApiError,
        match="Container already exists",
    ) as error:
        vcontainer.api_request("/containers", 10)

    assert error.value.status == 409
    assert error.value.detail == "Container already exists"
    connection.close.assert_called_once()


def test_server_events_decodes_sse_messages():
    response = Mock()
    response.readline.side_effect = [
        b"event: log\n",
        b'data: {"message":"ready"}\n',
        b"\n",
        b"event: error\n",
        b'data: {"message":"stopped"}\n',
        b"",
    ]

    assert list(vcontainer.server_events(response)) == [
        ("log", {"message": "ready"}),
        ("error", {"message": "stopped"}),
    ]


def test_ensure_backend_returns_when_service_is_healthy(monkeypatch):
    keepalive = Mock()
    run = Mock()
    monkeypatch.setattr(vcontainer, "ensure_wsl_keepalive", keepalive)
    monkeypatch.setattr(vcontainer, "backend_ready", Mock(return_value=True))
    monkeypatch.setattr(vcontainer.subprocess, "run", run)

    vcontainer.ensure_backend("Ubuntu")

    keepalive.assert_called_once_with("Ubuntu")
    run.assert_not_called()


def test_ensure_backend_starts_systemd_service(monkeypatch):
    monkeypatch.setattr(vcontainer, "ensure_wsl_keepalive", Mock())
    monkeypatch.setattr(
        vcontainer,
        "backend_ready",
        Mock(side_effect=[False, True]),
    )
    run = Mock()
    monkeypatch.setattr(vcontainer.subprocess, "run", run)
    monkeypatch.setattr(vcontainer.time, "monotonic", Mock(return_value=0))
    monkeypatch.setattr(vcontainer.time, "sleep", Mock())

    vcontainer.ensure_backend("Ubuntu")

    run.assert_called_once_with(
        [
            "wsl.exe",
            "-d",
            "Ubuntu",
            "-u",
            "root",
            "--exec",
            "systemctl",
            "start",
            "vcontainer-api",
        ],
        check=True,
        timeout=120,
    )


def test_compose_service_order_respects_dependencies():
    project = {
        "services": {
            "gateway": {"depends_on": {"backend": {}}},
            "backend": {"depends_on": {"database": {}}},
            "database": {},
        },
    }

    ordered = vcontainer.compose_service_order(project)

    assert [name for name, _ in ordered] == ["database", "backend", "gateway"]


def test_compose_service_order_rejects_cycles():
    project = {
        "services": {
            "one": {"depends_on": {"two": {}}},
            "two": {"depends_on": {"one": {}}},
        },
    }

    with pytest.raises(ValueError, match="Circular Compose dependency"):
        vcontainer.compose_service_order(project)


def test_compose_payload_converts_supported_fields():
    project = {"name": "blog"}
    service = {
        "image": "nginx",
        "environment": {"MODE": "test", "EMPTY": None},
        "command": "nginx -g 'daemon off;'",
        "volumes": [
            {"type": "volume", "source": "html", "target": "/site"},
        ],
        "ports": [{"published": "8080", "target": 80, "protocol": "tcp"}],
        "networks": {"default": {"ipv4_address": "10.88.0.25"}},
        "mem_limit": 268435456,
        "pids_limit": 64,
        "cpus": 0.5,
    }

    payload = vcontainer.compose_payload(
        project,
        "frontend",
        service,
        {"html": "blog-html"},
    )

    assert payload["name"] == "blog-frontend"
    assert payload["environment"] == {"MODE": "test", "EMPTY": ""}
    assert payload["command"] == ["/bin/sh", "-c", "nginx -g 'daemon off;'"]
    assert payload["volumes"] == [{"name": "blog-html", "target": "/site"}]
    assert payload["ports"] == [{"host_port": 8080, "container_port": 80}]
    assert payload["network"] == "bridge"
    assert payload["ip"] == "10.88.0.25"
    assert payload["memory_max"] == "268435456"
    assert payload["pids_max"] == 64
    assert payload["cpu_quota"] == 50000
    assert payload["cpu_period"] == 100000


def test_compose_up_rolls_back_containers_after_failure(monkeypatch):
    project = {
        "name": "demo",
        "services": {
            "first": {"image": "alpine"},
            "second": {"image": "alpine"},
        },
    }
    request = Mock(
        side_effect=[
            {"containers": []},
            {"name": "demo-first", "status": "starting"},
            RuntimeError("create failed"),
            {},
        ],
    )
    monkeypatch.setattr(vcontainer, "ensure_backend", Mock())
    monkeypatch.setattr(vcontainer, "load_compose", Mock(return_value=project))
    monkeypatch.setattr(vcontainer, "api_request", request)

    with pytest.raises(RuntimeError, match="create failed"):
        vcontainer.compose_up("compose.yaml", "Ubuntu")

    assert request.call_args_list[-1].args == ("/containers/demo-first", 60)
    assert request.call_args_list[-1].kwargs == {"method": "DELETE"}


def test_compose_up_replaces_only_selected_service(monkeypatch):
    project = {
        "name": "demo",
        "services": {
            "database": {"image": "mysql"},
            "backend": {"image": "node"},
        },
    }
    request = Mock(
        side_effect=[
            {
                "containers": [
                    {"name": "demo-database", "status": "running"},
                    {"name": "demo-backend", "status": "running"},
                ]
            },
            {},
            {"name": "demo-backend", "status": "starting"},
        ],
    )
    monkeypatch.setattr(vcontainer, "ensure_backend", Mock())
    monkeypatch.setattr(vcontainer, "load_compose", Mock(return_value=project))
    monkeypatch.setattr(vcontainer, "api_request", request)

    assert (
        vcontainer.compose_up(
            "compose.yaml",
            "Ubuntu",
            "backend",
            True,
        )
        == 0
    )
    assert request.call_args_list[1].args == ("/containers/demo-backend", 60)
    assert request.call_args_list[1].kwargs == {"method": "DELETE"}
    assert request.call_args_list[2].args == ("/containers", 60)
    assert request.call_args_list[2].kwargs["method"] == "POST"
    assert request.call_args_list[2].kwargs["payload"]["name"] == (
        "demo-backend"
    )


def test_compose_up_options_accepts_service_replacement():
    assert vcontainer.compose_up_options(
        [
            "compose",
            "up",
            "compose.yaml",
            "--service",
            "backend",
            "--replace",
        ]
    ) == ("compose.yaml", "backend", True)


@pytest.mark.parametrize(
    ("action", "expected_path", "method", "timeout"),
    [
        ("start", "/containers/demo/start", "POST", 30),
        ("stop", "/containers/demo/stop", "POST", 60),
        ("rm", "/containers/demo", "DELETE", 30),
    ],
)
def test_main_dispatches_container_actions(
    monkeypatch,
    action,
    expected_path,
    method,
    timeout,
):
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER_PATH), action, "demo"])
    monkeypatch.setattr(vcontainer, "ensure_backend", Mock())
    request = Mock(return_value={"message": "done"})
    monkeypatch.setattr(vcontainer, "api_request", request)

    assert vcontainer.main() == 0
    request.assert_called_once_with(expected_path, timeout, method=method)


def test_main_preserves_shell_fallback_arguments(monkeypatch):
    arguments = ["exec", "demo", "--", "/bin/echo", "hello world"]
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER_PATH), *arguments])
    monkeypatch.setenv("VCONTAINER_WSL_DISTRO", "machine")
    monkeypatch.setenv("VCONTAINER_WSL_USER", "alex")
    call = Mock(return_value=7)
    monkeypatch.setattr(vcontainer.subprocess, "call", call)

    assert vcontainer.main() == 7
    call.assert_called_once_with(
        [
            "wsl.exe",
            "-d",
            "machine",
            "-u",
            "root",
            "--cd",
            str(LAUNCHER_PATH.parent),
            "--exec",
            "env",
            "SUDO_USER=alex",
            "/opt/vcontainer/bin/vcontainer-cli",
            *arguments,
        ]
    )
