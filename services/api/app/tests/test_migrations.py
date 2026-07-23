"""Migration integrity: the Alembic chain must apply and roll back cleanly."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

SERVICE_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "providers",
    "manufacturers",
    "brands",
    "machine_models",
    "documents",
    "model_documents",
}


def _alembic_config(db_path: Path) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return config


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {name for (name,) in rows}


def test_upgrade_creates_full_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "migrations.db"
    command.upgrade(_alembic_config(db_path), "head")
    assert _tables(db_path) >= EXPECTED_TABLES


def test_downgrade_removes_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "migrations.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert _tables(db_path) & EXPECTED_TABLES == set()


def test_migration_schema_matches_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The migration chain and Base.metadata must describe the same tables."""
    from app.database.base import Base

    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "migrations.db"
    command.upgrade(_alembic_config(db_path), "head")
    migrated = _tables(db_path) - {"alembic_version"}
    assert migrated == set(Base.metadata.tables)
