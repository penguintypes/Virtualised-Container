from vcontainer_api.routers import volumes


def test_list_volumes(monkeypatch):
    monkeypatch.setattr(volumes.runtime, "run_volume", lambda action: [])
    assert volumes.volumes() == {"volumes": []}
