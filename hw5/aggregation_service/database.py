"""Database connections for ClickHouse and PostgreSQL."""

import logging
import time
from typing import Any, Dict, List, Optional

import clickhouse_connect
import psycopg2
import psycopg2.extras

from aggregation_service.config import Config

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """ClickHouse client wrapper with retry logic."""

    def __init__(self, config: Config):
        self.config = config
        self._client = None

    def connect(self) -> None:
        """Connect to ClickHouse with retries."""
        max_retries = 10
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self._client = clickhouse_connect.get_client(
                    host=self.config.CLICKHOUSE_HOST,
                    port=int(self.config.CLICKHOUSE_PORT),
                    database=self.config.CLICKHOUSE_DB,
                    username=self.config.CLICKHOUSE_USER,
                    password=self.config.CLICKHOUSE_PASSWORD,
                )
                # Test connection
                result = self._client.query("SELECT 1")
                logger.info("Connected to ClickHouse at %s:%s", self.config.CLICKHOUSE_HOST, self.config.CLICKHOUSE_PORT)
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to ClickHouse (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30)

        raise ConnectionError("Failed to connect to ClickHouse after retries")

    def query(self, sql: str, parameters: Optional[Dict] = None) -> Any:
        """Execute a query and return results."""
        if not self._client:
            raise RuntimeError("Not connected to ClickHouse")
        return self._client.query(sql, parameters=parameters)

    def command(self, sql: str, parameters: Optional[Dict] = None) -> None:
        """Execute a command (INSERT, CREATE, etc.)."""
        if not self._client:
            raise RuntimeError("Not connected to ClickHouse")
        self._client.command(sql, parameters=parameters)

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()


class PostgresClient:
    """PostgreSQL client wrapper with retry logic."""

    def __init__(self, config: Config):
        self.config = config
        self._conn = None

    def connect(self) -> None:
        """Connect to PostgreSQL with retries."""
        max_retries = 10
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self._conn = psycopg2.connect(
                    host=self.config.POSTGRES_HOST,
                    port=self.config.POSTGRES_PORT,
                    dbname=self.config.POSTGRES_DB,
                    user=self.config.POSTGRES_USER,
                    password=self.config.POSTGRES_PASSWORD,
                )
                self._conn.autocommit = False
                logger.info("Connected to PostgreSQL at %s:%s", self.config.POSTGRES_HOST, self.config.POSTGRES_PORT)
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to PostgreSQL (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30)

        raise ConnectionError("Failed to connect to PostgreSQL after retries")

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Execute a SQL statement."""
        if not self._conn:
            raise RuntimeError("Not connected to PostgreSQL")
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise

    def execute_many(self, sql: str, params_list: List[tuple]) -> None:
        """Execute a SQL statement with multiple parameter sets."""
        if not self._conn:
            raise RuntimeError("Not connected to PostgreSQL")
        try:
            with self._conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, sql, params_list)
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise

    def fetch_all(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute a query and return all rows as dicts."""
        if not self._conn:
            raise RuntimeError("Not connected to PostgreSQL")
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
