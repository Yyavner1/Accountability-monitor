"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)
engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db() -> None:
    # Import models so their tables register on the metadata before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    """Additive migration for SQLite: add any columns missing from existing
    tables so upgrading to a newer schema doesn't error. For additive changes
    only; use Alembic for anything more involved in production.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        for table in SQLModel.metadata.tables.values():
            rows = conn.execute(text(f'PRAGMA table_info("{table.name}")')).all()
            existing = {r[1] for r in rows}
            if not existing:
                continue  # table is new; create_all already made it fully
            for col in table.columns:
                if col.name in existing:
                    continue
                affinity = _sqlite_affinity(col)
                default = _sqlite_default(col)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {affinity}'
                if default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))


def _sqlite_affinity(col) -> str:
    t = col.type.__class__.__name__.lower()
    if "int" in t or "bool" in t:
        return "INTEGER"
    if "float" in t or "numeric" in t or "real" in t:
        return "REAL"
    return "TEXT"


def _sqlite_default(col):
    d = getattr(col, "default", None)
    if d is not None and getattr(d, "is_scalar", False):
        v = d.arg
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
    return None


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
