from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import catalog, search

settings = get_settings()

app = FastAPI(title="UPlate Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
