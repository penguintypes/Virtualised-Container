from vcontainer_api.main import app


def test_streaming_routes_are_registered():
    paths = app.openapi()["paths"]
    assert "/containers/{name}/logs/stream" in paths
    assert "/containers/{name}/metrics/stream" in paths
