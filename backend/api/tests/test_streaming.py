from vcontainer_api.main import STATIC_DIRECTORY, app


def test_streaming_routes_are_registered():
    paths = app.openapi()["paths"]
    assert "/containers/{name}/logs/stream" in paths
    assert "/containers/{name}/metrics/stream" in paths


def test_parizval_gui_and_live_metrics_are_registered():
    assert (STATIC_DIRECTORY / "index.html").is_file()
    assert STATIC_DIRECTORY.name == "gui"
    assert "/system/live" in app.openapi()["paths"]
    assert any(
        getattr(route, "name", None) == "dashboard-static"
        for route in app.routes
    )
