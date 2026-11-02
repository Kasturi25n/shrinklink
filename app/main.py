from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import analytics, auth, links, redirect, web


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine for a small project. For real schema evolution, switch to Alembic migrations.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="URL Shortener",
    description="Shorten links and track clicks. Includes auth, caching, rate limiting and analytics.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(analytics.router)
app.include_router(web.router)
# Must be last: its /{code} catch-all would otherwise shadow the routes above.
app.include_router(redirect.router)
