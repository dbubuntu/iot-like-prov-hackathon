import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.enroll import router as enroll_router
from .store import store


CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "60"))


async def cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        removed = store.cleanup_expired()
        if removed:
            print(f"[CLEANUP] Removed {removed} expired enrollment(s).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(
    title="IoT Provisioning Server",
    description="Mutual Trust Flow — Token-based device enrollment",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enroll_router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
