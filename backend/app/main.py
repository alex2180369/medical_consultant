"""FastAPI application for the local medical AI navigator."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_settings
from app.database import initialize_database
from app.routers import (
    auth,
    complaints,
    consultations,
    documents,
    labs,
    nutrition,
    profile,
)
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize local resources before the API starts."""
    initialize_database()
    yield


settings = load_settings()
app = FastAPI(
    title=settings.app_name,
    description=(
        "Local personal medical assistant. Informational support only; "
        "not a substitute for in-person medical care."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(labs.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(complaints.router, prefix="/api")
app.include_router(consultations.router, prefix="/api")
app.include_router(nutrition.router, prefix="/api")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return backend health status."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
    )
