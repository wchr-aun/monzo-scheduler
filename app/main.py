from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.config import Settings
from app.db.session import create_database_engine, create_session_factory
from app.routers import health, monzo, tasks


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database_engine = engine or create_database_engine(settings.database_url)
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.start()
        application.state.scheduler = scheduler
        application.state.settings = settings
        application.state.database_engine = database_engine
        application.state.session_factory = create_session_factory(database_engine)
        application.state.oauth_states = set()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            if engine is None:
                database_engine.dispose()

    application = FastAPI(title="Monzo Scheduler", lifespan=lifespan)
    application.include_router(health.router)
    application.include_router(tasks.router)
    application.include_router(monzo.router)
    return application


app = create_app()
