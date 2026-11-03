from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"service": "vcontainer", "status": "ok", "ok": True}
