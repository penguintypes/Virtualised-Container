import asyncio
import subprocess

from vcontainer_api.routers import compose as compose_router
from vcontainer_api.schemas import ContainerCreate
from vcontainer_api.services import compose


def test_parse_compose_uses_linux_helper(monkeypatch, tmp_path):
    helper = tmp_path / "vcontainer-compose"
    helper.write_bytes(b"helper")
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"name":"demo","services":{"web":{"image":"nginx"}}}',
        stderr="",
    )
    monkeypatch.setattr(compose, "COMPOSE_HELPER", helper)
    monkeypatch.setattr(compose.subprocess, "run", lambda *args, **kwargs: completed)

    project = compose.parse_compose("services:\n  web:\n    image: nginx\n")

    assert project["name"] == "demo"
    assert project["services"]["web"]["image"] == "nginx"


def test_container_request_converts_normalized_service():
    project = {"name": "demo"}
    service = {
        "image": "nginx",
        "command": ["nginx", "-g", "daemon off;"],
        "environment": {"MODE": "test"},
        "ports": [{"published": "8080", "target": 80, "protocol": "tcp"}],
        "volumes": [
            {"type": "volume", "source": "html", "target": "/usr/share/nginx/html"}
        ],
    }

    request = compose.container_request(project, "web", service, {"html": "demo-html"})

    assert request.name == "demo-web"
    assert request.ports[0].host_port == 8080
    assert request.volumes[0].name == "demo-html"


def test_service_order_places_dependencies_first():
    project = {
        "services": {
            "web": {"image": "nginx", "depends_on": {"database": {}}},
            "database": {"image": "mysql"},
        }
    }

    ordered = compose.service_order(project)

    assert [name for name, _ in ordered] == ["database", "web"]


def test_save_and_load_project_uses_private_files(monkeypatch, tmp_path):
    monkeypatch.setattr(compose, "COMPOSE_DIRECTORY", tmp_path)
    source = "name: demo\nservices:\n  web:\n    image: nginx\n"
    project = {"name": "demo", "services": {"web": {"image": "nginx"}}}

    assert compose.save_project(source, project) == "demo"
    assert compose.load_project("demo") == project
    assert (tmp_path / "demo" / "compose.yaml").read_text() == source


def test_compose_start_starts_stopped_containers(monkeypatch):
    containers = [ContainerCreate(name="demo-web", image="nginx")]

    async def current():
        return {"demo-web": {"name": "demo-web", "status": "stopped"}}

    async def start(name):
        return {"name": name, "status": "starting"}

    monkeypatch.setattr(
        compose_router,
        "stored_project",
        lambda name: ({"name": name}, containers),
    )
    monkeypatch.setattr(compose_router, "current_containers", current)
    monkeypatch.setattr(compose_router, "start_container", start)

    result = asyncio.run(compose_router.compose_start("demo"))

    assert result["status"] == "starting"
    assert result["containers"] == [{"name": "demo-web", "status": "starting"}]


def test_compose_stop_uses_reverse_service_order(monkeypatch):
    containers = [
        ContainerCreate(name="demo-db", image="mysql"),
        ContainerCreate(name="demo-web", image="nginx"),
    ]
    stopped = []

    async def current():
        return {
            container.name: {"name": container.name, "status": "running"}
            for container in containers
        }

    monkeypatch.setattr(
        compose_router,
        "stored_project",
        lambda name: ({"name": name}, containers),
    )
    monkeypatch.setattr(compose_router, "current_containers", current)
    monkeypatch.setattr(compose_router, "stop_container", stopped.append)

    result = asyncio.run(compose_router.compose_stop("demo"))

    assert stopped == ["demo-web", "demo-db"]
    assert result["status"] == "stopped"
