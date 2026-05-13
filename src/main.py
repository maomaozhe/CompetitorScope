"""FastAPI app entry point with lifespan management."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import router as api_router
from src.services.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and workflow graph at startup; clean up at shutdown."""
    await init_db()
    yield
    await close_db()


app = FastAPI(title="CompetitorScope", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
