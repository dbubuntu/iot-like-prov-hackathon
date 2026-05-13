import logging
import sys

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IoT Provisioning Server",
    description="Token-based device enrollment via mutual trust flow",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/device/token", summary="Get or create a provisioning token for a device")
async def device_token(id: str = Query(..., description="Device identifier")):
    token = store.get_or_create_token(id)
    print(f" TOKEN  {token}  for device={id}", file=sys.stderr, flush=True)
    return {"token": token}


class ApproveRequest(BaseModel):
    token: str
    device_id: str


@app.post("/v1/app/approve", summary="Approve a device using token + device_id")
async def app_approve(body: ApproveRequest):
    success = store.approve(body.token, body.device_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Invalid or expired token/device_id combination.",
        )
    logger.info(f"Device approved: device_id={body.device_id}")
    return {"success": True}


@app.get("/v1/device/status/{device_id}", summary="Poll the approval status of a device")
async def device_status(device_id: str):
    approved = store.get_status(device_id)
    return {"approved": approved}


@app.get("/health")
async def health():
    return {"status": "ok"}
