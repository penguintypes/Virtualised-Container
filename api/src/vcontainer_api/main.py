from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from .lifecycle import lifespan
from .routers import (
    containers_router,
    health_router,
    images_router,
    system_router,
    volumes_router,
)

STATIC_DIRECTORY = Path(__file__).with_name("static")


app = FastAPI(
    title="Vcontainer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(system_router)
app.include_router(images_router)
app.include_router(volumes_router)
app.include_router(containers_router)


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIRECTORY / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
