from fastapi import APIRouter, HTTPException, Query

from ..store import store

router = APIRouter(prefix="/v1/enroll", tags=["enrollment"])


class InitRequest:
    pass


@router.post("/init", summary="Initialize enrollment for a device")
async def enroll_init(device_id: str = Query(..., description="The unique device identifier")):
    result = store.init_enrollment(device_id)
    return result


@router.get("/token/{device_id}", summary="Fetch the assigned token for a device")
async def enroll_token(device_id: str):
    result = store.get_token(device_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No enrollment found for device '{device_id}'. Call /init first.",
        )
    return result


@router.post("/approve", summary="Approve a device provisioning with token")
async def enroll_approve(token: str = Query(..., description="The 6-character token from the QR code"),
                          device_id: str = Query(..., description="The device identifier")):
    result = store.approve(token, device_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Invalid or expired token/device_id combination.",
        )
    return result


@router.get("/status/{device_id}", summary="Poll provisioning status for a device")
async def enroll_status(device_id: str):
    result = store.get_status(device_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No enrollment found for device '{device_id}'.",
        )
    return result
