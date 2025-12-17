"""Main FastAPI application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.storage.database import init_db, close_db
from app.api.routes import projects, chat, sandbox, files, settings as settings_routes
from app.api.websocket.streaming_manager import streaming_manager

# Import all models to register them with SQLAlchemy Base before init_db
import app.models.database  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("Initializing database...")
    await init_db()
    print("Database initialized successfully")

    # Start streaming manager
    print("Starting streaming manager...")
    await streaming_manager.start()
    print("Streaming manager started successfully")

    yield

    # Shutdown
    print("Stopping streaming manager...")
    await streaming_manager.stop()
    print("Streaming manager stopped successfully")

    print("Closing database connections...")
    await close_db()
    print("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Open Claude UI Backend",
    description="Backend API for Open Claude UI",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(sandbox.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(settings_routes.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Open Claude UI Backend",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    import os

    # Only watch app code, not workspace data directories
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reload_dirs = [os.path.join(backend_dir, "app")]

    # Explicitly exclude data directories from file watching (use relative patterns)
    reload_excludes = [
        "data/**",
        "*.db",
        "*.db-*",
    ]

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_dirs=reload_dirs,
        reload_excludes=reload_excludes,
    )
