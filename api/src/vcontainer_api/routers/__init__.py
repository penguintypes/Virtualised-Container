from .containers import router as containers_router
from .health import router as health_router
from .images import router as images_router
from .system import router as system_router
from .volumes import router as volumes_router

__all__ = [
    "containers_router",
    "health_router",
    "images_router",
    "system_router",
    "volumes_router",
]
