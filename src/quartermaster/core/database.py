"""Oracle database connection pool."""

from typing import Any

import oracledb
import structlog

from quartermaster.core.config import DatabaseConfig

logger = structlog.get_logger()


def _output_type_handler(
    cursor: Any, metadata: Any
) -> Any:
    """Convert LOB and JSON columns to Python strings automatically.

    Without this, Oracle returns CLOB as AsyncLOB objects and JSON as
    oracledb JSON objects — both require special handling at each call
    site. This handler makes all text-like columns return as ``str``.
    """
    if metadata.type_code is oracledb.DB_TYPE_CLOB:
        return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
    if metadata.type_code is oracledb.DB_TYPE_JSON:
        return cursor.var(str, arraysize=cursor.arraysize)
    return None


class Database:
    """Async Oracle database connection pool.

    Wraps python-oracledb's async pool for connection management.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: oracledb.AsyncConnectionPool | None = None

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        self._pool = oracledb.create_pool_async(
            user=self._config.user,
            password=self._config.password,
            dsn=self._config.dsn,
            min=self._config.pool_min,
            max=self._config.pool_max,
        )
        logger.info("database_connected", dsn=self._config.dsn)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("database_closed")

    async def _acquire(self) -> Any:
        """Acquire a connection with the output type handler set."""
        if self._pool is None:
            raise RuntimeError("Database not connected — call connect() first")
        conn = await self._pool.acquire()
        conn.outputtypehandler = _output_type_handler
        return conn

    async def fetch_all(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[tuple[Any, ...]]:
        """Execute a query and return all rows."""
        conn = await self._acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            rows: list[tuple[Any, ...]] = await cursor.fetchall()
            cursor.close()
            return rows
        finally:
            await self._pool.release(conn)

    async def fetch_one(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[Any, ...] | None:
        """Execute a query and return one row."""
        conn = await self._acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            row: tuple[Any, ...] | None = await cursor.fetchone()
            cursor.close()
            return row
        finally:
            await self._pool.release(conn)

    async def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> int:
        """Execute a DML statement and return rows affected."""
        conn = await self._acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            await conn.commit()
            rowcount: int = cursor.rowcount
            cursor.close()
            return rowcount
        finally:
            await self._pool.release(conn)

    async def execute_many(
        self, sql: str, params_list: list[dict[str, Any]]
    ) -> None:
        """Execute a DML statement with multiple parameter sets."""
        conn = await self._acquire()
        try:
            cursor = conn.cursor()
            await cursor.executemany(sql, params_list)
            await conn.commit()
            cursor.close()
        finally:
            await self._pool.release(conn)
