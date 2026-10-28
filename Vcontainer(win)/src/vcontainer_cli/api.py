import http.client
import json
from typing import Any

from .config import API_HOST, API_PORT
from .errors import VcontainerApiError


def api_request(
    path: str,
    timeout: float | None,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    connection = http.client.HTTPConnection(
        API_HOST, API_PORT, timeout=timeout
    )
    request_body = json.dumps(payload) if payload is not None else None
    headers = (
        {"Content-Type": "application/json"} if payload is not None else {}
    )

    try:
        connection.request(method, path, body=request_body, headers=headers)
        response = connection.getresponse()
        response_body = response.read()
    finally:
        connection.close()

    try:
        data = json.loads(response_body) if response_body else {}
    except json.JSONDecodeError as error:
        raise RuntimeError("Backend returned invalid JSON") from error

    if response.status >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        raise VcontainerApiError(response.status, detail)
    return data


def api_error(response: http.client.HTTPResponse) -> VcontainerApiError:
    response_body = response.read()
    try:
        error_data = json.loads(response_body)
    except json.JSONDecodeError:
        error_data = {}
    detail = error_data.get("detail") if isinstance(error_data, dict) else None
    return VcontainerApiError(response.status, detail)


def server_events(response: http.client.HTTPResponse):
    event_name = None
    while line := response.readline():
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if text.startswith("event: "):
            event_name = text[7:]
            continue
        if text.startswith("data: "):
            yield event_name, json.loads(text[6:])
