"""Tests for the Oracle database layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.core.config import DatabaseConfig
from quartermaster.core.database import Database


@pytest.fixture
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        dsn="localhost:1521/quartermaster_test_pdb",
        user="qm",
        password="test_pw",
    )


@pytest.mark.asyncio
async def test_database_connect_and_close(db_config: DatabaseConfig) -> None:
    """Test that database can connect and close (mocked)."""
    with patch("quartermaster.core.database.oracledb") as mock_ora:
        mock_pool = MagicMock()
        # create_pool_async is synchronous in oracledb 3.4.2 — returns pool directly
        mock_ora.create_pool_async = MagicMock(return_value=mock_pool)
        mock_pool.close = AsyncMock()

        db = Database(db_config)
        await db.connect()
        assert db.is_connected

        await db.close()
        mock_pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_execute(db_config: DatabaseConfig) -> None:
    """Test execute returns results (mocked)."""
    with patch("quartermaster.core.database.oracledb") as mock_ora:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # create_pool_async is synchronous in oracledb 3.4.2
        mock_ora.create_pool_async = MagicMock(return_value=mock_pool)
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.release = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[(1, "test")])
        # cursor.close() is synchronous in oracledb 3.4.2
        mock_cursor.close = MagicMock()

        db = Database(db_config)
        await db.connect()
        rows = await db.fetch_all("SELECT 1, 'test' FROM dual")
        assert rows == [(1, "test")]
