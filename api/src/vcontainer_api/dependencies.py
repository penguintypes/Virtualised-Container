import re
import subprocess
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from .services import runtime


def validate_name(name: str, resource: str = "container") -> None:
    if name in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise HTTPException(400, f"Invalid {resource} name")


def read_runtime(function: Callable[..., Any], *args: Any) -> Any:
    try:
        return function(*args)
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "Runtime request timed out") from error
    except runtime.ResourceNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except runtime.ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error)) from error
