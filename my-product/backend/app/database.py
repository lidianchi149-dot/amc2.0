from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from .config import get_settings


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


engine = build_engine()


def get_connection() -> Generator[Connection, None, None]:
    with engine.connect() as connection:
        yield connection
