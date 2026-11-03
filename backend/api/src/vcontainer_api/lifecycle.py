from contextlib import asynccontextmanager

from fastapi import FastAPI

from .supervisor import restore_runtime_state


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await restore_runtime_state()
    yield
