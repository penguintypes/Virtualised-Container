from fastapi import APIRouter

from ..dependencies import read_runtime, validate_name
from ..schemas import VolumeCreate
from ..services import runtime

router = APIRouter(prefix="/volumes", tags=["volumes"])


@router.get("")
def volumes():
    return {"volumes": read_runtime(runtime.run_volume, "list")}


@router.post("", status_code=201)
def create_volume(request: VolumeCreate):
    return read_runtime(runtime.run_volume, "create", request.name)


@router.get("/{name}")
def inspect_volume(name: str):
    validate_name(name, "volume")
    return read_runtime(runtime.run_volume, "inspect", name)


@router.delete("/{name}")
def remove_volume(name: str):
    validate_name(name, "volume")
    return read_runtime(runtime.run_volume, "remove", name)
