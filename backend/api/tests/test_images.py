from vcontainer_api.routers import images


def test_list_images(monkeypatch):
    monkeypatch.setattr(images.runtime, "get_images", lambda: [])
    assert images.images() == {"images": []}
