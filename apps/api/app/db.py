from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    # MySQL/MariaDB: validate pooled connections and recycle them well before
    # the server's wait_timeout so a long-idle worker/API does not hand out a
    # dead socket ("MySQL server has gone away") on the first request after idle.
    return {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    # sqlite (tests/dev) bootstraps directly; MySQL/prod schema is owned by Alembic
    # (`alembic upgrade head`, run by the API container before serving).
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
