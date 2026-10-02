import stat

from app.db.session import create_database_engine


def test_sqlite_database_is_restricted_to_owner(tmp_path):
    database_path = tmp_path / "credentials.db"
    engine = create_database_engine(f"sqlite:///{database_path}")

    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600
    engine.dispose()
