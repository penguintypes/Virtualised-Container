from vcontainer_api.routers import containers


def test_list_containers(monkeypatch):
    monkeypatch.setattr(containers.runtime, "get_containers", lambda: [])
    assert containers.containers() == {"containers": []}
