from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid6

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from cryptography.fernet import Fernet
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db.session import create_database_engine, create_session_factory
from app.observability import configure_logging, get_logger
from app.rate_limit import RequestRateLimiter
from app.routers import health, monzo, resources, tasks
from app.services.scheduler import restore_scheduled_transfers

logger = get_logger(__name__)


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    configure_logging()
    settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not settings.token_encryption_key:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
        try:
            Fernet(settings.token_encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if len(settings.jwt_secret_key.encode()) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes")
        if not 1 <= settings.jwt_expiration_seconds <= 3600:
            raise RuntimeError("JWT_EXPIRATION_SECONDS must be between 1 and 3600")
        database_engine = engine or create_database_engine(settings.database_url)
        session_factory = create_session_factory(database_engine)
        scheduler = BackgroundScheduler(timezone="UTC")
        restore_scheduled_transfers(scheduler, session_factory, settings)
        scheduler.start()
        application.state.scheduler = scheduler
        application.state.settings = settings
        application.state.database_engine = database_engine
        application.state.session_factory = session_factory
        application.state.oauth_states = {}
        application.state.request_rate_limiter = RequestRateLimiter()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            if engine is None:
                database_engine.dispose()

    application = FastAPI(title="Schedzo", lifespan=lifespan)

    @application.middleware("http")
    async def log_request_failures(request: Request, call_next):
        request_id = uuid6().hex
        request.state.request_id = request_id
        started_at = monotonic()
        client_host = request.client.host if request.client is not None else "unknown"
        if not request.app.state.request_rate_limiter.allow(client_host):
            response = JSONResponse(status_code=429, content={"detail": "Too many requests"})
            response.headers["X-Request-ID"] = request_id
            response.headers["Retry-After"] = "60"
            _add_security_headers(response, request)
            return response
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed request_id=%s method=%s path=%s "
                "exception_type=%s duration_ms=%d",
                request_id,
                request.method,
                request.url.path,
                type(exc).__name__,
                round((monotonic() - started_at) * 1000),
            )
            raise

        response.headers["X-Request-ID"] = request_id
        _add_security_headers(response, request)
        if response.status_code >= 400:
            log = logger.error if response.status_code >= 500 else logger.warning
            log(
                "request_completed_with_error request_id=%s method=%s path=%s "
                "status_code=%d duration_ms=%d",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                round((monotonic() - started_at) * 1000),
            )
        return response

    application.include_router(health.router)
    application.include_router(tasks.router)
    application.include_router(monzo.router)
    application.include_router(resources.router)
    return application


def _add_security_headers(response, request: Request) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )


app = create_app()
