import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from .lifecycle import lifespan
from .routers import (
    compose_router,
    containers_router,
    health_router,
    images_router,
    system_router,
    volumes_router,
)


def find_static_directory():
    configured = os.getenv("VCONTAINER_GUI_DIR")
    if configured:
        directory = Path(configured)
        if not (directory / "index.html").is_file():
            raise RuntimeError(f"GUI entry point is missing: {directory}")
        return directory

    for parent in Path(__file__).resolve().parents:
        directory = parent / "gui"
        if (directory / "index.html").is_file():
            return directory

    return Path(__file__).with_name("static")


STATIC_DIRECTORY = find_static_directory()


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
app.include_router(compose_router)
app.include_router(containers_router)


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIRECTORY / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
app.mount(
    "/",
    StaticFiles(directory=STATIC_DIRECTORY, html=True),
    name="dashboard-static",
)


def run():
    uvicorn.run(
        "vcontainer_api.main:app",
        host="127.0.0.1",
        port=8010,
    )
