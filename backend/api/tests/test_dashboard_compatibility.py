from vcontainer_api.schemas import ContainerCreate


def test_parizval_dashboard_container_fields_are_normalized():
    request = ContainerCreate.model_validate(
        {
            "name": "dashboard-web",
            "image": "nginx",
            "memory": "250M",
            "pids": 64,
            "env": ["MODE=demo"],
            "volumes": ["site:/usr/share/nginx/html"],
            "ports": ["8080:80"],
            "network": "bridge",
            "ip": "10.88.0.20",
        }
    )

    assert request.memory_max == "250M"
    assert request.pids_max == 64
    assert request.environment == {"MODE": "demo"}
    assert request.volumes[0].name == "site"
    assert request.ports[0].host_port == 8080
