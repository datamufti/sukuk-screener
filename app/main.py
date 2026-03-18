"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, TEMPLATES_DIR
from app.database import setup_database
from app.routers import pages, api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting sukuk-screener…")
    conn = setup_database()
    app.state.db = conn
    logger.info("Database ready.")
    yield
    conn.close()
    logger.info("Database closed. Goodbye.")


app = FastAPI(
    title="Sukuk Screener",
    description="Daily tracker and screener for Emirates Islamic sukuk",
    version="0.1.0",
    lifespan=lifespan,
)

# Static files (CSS / JS)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routers
app.include_router(pages.router)
app.include_router(api.router, prefix="/api")
