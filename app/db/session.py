from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path


def create_database_engine(database_url: str) -> Engine:
    options = {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, hide_parameters=True, **options)
    if database_url.startswith("sqlite") and engine.url.database not in {None, ":memory:"}:
        database_path = Path(engine.url.database).resolve()
        with engine.connect():
            database_path.chmod(0o600)
    return engine


def create_session_factory(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
