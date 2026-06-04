import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.sessions import router as sessions_router
from api.routes.stream import router as stream_router
from config import settings

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

app = FastAPI(title="AutoQA Prompt Optimizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router, prefix="/api")
app.include_router(stream_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
