from fastapi import APIRouter

from ..dependencies import read_runtime
from ..services import runtime

router = APIRouter(tags=["system"])


@router.get("/system/disk")
def disk_usage():
    return read_runtime(runtime.get_disk_usage)
