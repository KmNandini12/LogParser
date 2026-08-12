"""Main FastAPI ASGI application entrypoint."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.session import init_db
from src.retrieval.seed_incidents import seed_incidents
from src.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown hooks."""
    logger.info("Starting up LogParser Engine...")
    try:
        init_db()
        seed_incidents()
        logger.info("Database and incidents verified.")
    except Exception as e:
        logger.warning(f"Startup database initialization: {e}")
    yield
    logger.info("Shutting down LogParser Engine...")


app = FastAPI(
    title="Automated Cloud Incident & Log Root-Cause Analyzer",
    description="A production-grade, zero-cost observability and root-cause analysis (RCA) pipeline.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for open accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
