"""Guards against the classic failure: models edited, migration forgotten.

Alembic offline mode (`upgrade head --sql`) renders Postgres DDL without connecting,
so this runs in plain CI with no database.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rendered_ddl() -> str:
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/placeholder",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    return result.stdout


def test_every_model_table_is_created_by_a_migration(rendered_ddl: str) -> None:
    missing = [name for name in Base.metadata.tables if f"CREATE TABLE {name} " not in rendered_ddl]

    assert missing == []


@pytest.mark.parametrize(
    "table_name", sorted(Base.metadata.tables), ids=sorted(Base.metadata.tables)
)
def test_every_model_column_is_created_by_a_migration(rendered_ddl: str, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    body = rendered_ddl.split(f"CREATE TABLE {table_name} ", 1)[1].split(");", 1)[0]

    missing = [column.name for column in table.columns if column.name not in body]

    assert missing == []


def test_the_chat_message_audit_column_uses_jsonb_on_postgres(rendered_ddl: str) -> None:
    body = rendered_ddl.split("CREATE TABLE chat_messages ", 1)[1].split(");", 1)[0]

    assert "tool_calls JSONB" in body
