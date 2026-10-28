from vcontainer_api.routers.health import health


def test_health():
    assert health() == {"service": "vcontainer", "status": "ok"}
