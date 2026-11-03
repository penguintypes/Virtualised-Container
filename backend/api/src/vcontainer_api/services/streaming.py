import orjson


def server_event(event: str, payload: dict) -> bytes:
    return b"event: " + event.encode() + b"\ndata: " + orjson.dumps(payload) + b"\n\n"
