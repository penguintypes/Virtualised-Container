from fastapi import APIRouter

from ..dependencies import read_runtime, validate_name
from ..schemas import ImagePull
from ..services import runtime

router = APIRouter(prefix="/images", tags=["images"])


@router.get("")
def images():
    return {"images": read_runtime(runtime.get_images)}


@router.post("/pull")
def pull_image(request: ImagePull):
    return read_runtime(runtime.pull_image, request.name, request.reference)


@router.delete("/{name}")
def delete_image(name: str):
    validate_name(name, "image")
    return read_runtime(runtime.delete_image, name)
