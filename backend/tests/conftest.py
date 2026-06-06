from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.base import Base


@pytest.fixture
def db_session() -> Session:
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://osemosys:osemosys@localhost:5432/osemosys",
    )
    schema_name = f"test_{uuid.uuid4().hex}"
    engine = create_engine(
        database_url,
        execution_options={
            "schema_translate_map": {"core": schema_name, "osemosys": schema_name}
        },
    )
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        try:
            from app.visualization.catalog_cache import warm_catalog_cache
            from app.visualization.catalog_seed import seed_visualization_catalog

            seed_visualization_catalog(session)
            warm_catalog_cache(session)
            yield session
        finally:
            session.close()
            Base.metadata.drop_all(engine)
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL no disponible para tests de catálogo: {exc}")
    finally:
        try:
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        except OperationalError:
            pass
        engine.dispose()
