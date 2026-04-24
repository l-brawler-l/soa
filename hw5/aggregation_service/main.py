"""Aggregation Service - FastAPI application for computing and exporting metrics."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import asyncio
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from aggregation_service.config import Config
from aggregation_service.database import ClickHouseClient, PostgresClient
from aggregation_service.metrics import MetricsComputer
from aggregation_service.s3_exporter import S3Exporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
ch_client = ClickHouseClient(config)
pg_client = PostgresClient(config)
metrics_computer: MetricsComputer | None = None
s3_exporter: S3Exporter | None = None
scheduler_task: asyncio.Task | None = None


def run_migrations():
    """Run PostgreSQL migrations using Alembic."""
    import subprocess
    import os

    alembic_dir = os.path.join(os.path.dirname(__file__), "..")
    logger.info("Running Alembic migrations...")

    # Set DATABASE_URL for Alembic env.py
    env = os.environ.copy()
    env["DATABASE_URL"] = config.postgres_dsn

    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=alembic_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0:
            logger.info("Migrations applied successfully")
        else:
            logger.error("Migration failed: %s", result.stderr)
            # Try to create tables directly as fallback
            _create_tables_fallback()
    except Exception as e:
        logger.warning("Alembic migration failed: %s, using fallback", e)
        _create_tables_fallback()


def _create_tables_fallback():
    """Create PostgreSQL tables directly if Alembic fails."""
    logger.info("Creating PostgreSQL tables via fallback...")
    pg_client.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id SERIAL PRIMARY KEY,
            metric_date DATE NOT NULL,
            metric_name VARCHAR(255) NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            extra_data TEXT,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (metric_date, metric_name)
        )
    """)
    pg_client.execute("""
        CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics (metric_date)
    """)
    pg_client.execute("""
        CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics (metric_name)
    """)
    logger.info("PostgreSQL tables created via fallback")


async def scheduler_loop():
    """Periodic aggregation scheduler."""
    interval = config.AGGREGATION_INTERVAL_MINUTES * 60
    logger.info("Aggregation scheduler started, interval=%d minutes", config.AGGREGATION_INTERVAL_MINUTES)

    # Wait a bit for data to accumulate
    await asyncio.sleep(30)

    while True:
        try:
            today = date.today()
            logger.info("Scheduler: computing metrics for %s", today)
            metrics_computer.compute_all_metrics(today)

            # Also export to S3
            s3_exporter.export_daily(today)

        except Exception as e:
            logger.error("Scheduler error: %s", e)

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect to databases, start scheduler."""
    global metrics_computer, s3_exporter, scheduler_task

    logger.info("Starting Aggregation Service...")

    # Connect to databases
    ch_client.connect()
    pg_client.connect()

    # Run migrations
    run_migrations()

    # Initialize components
    metrics_computer = MetricsComputer(ch_client, pg_client)
    s3_exporter = S3Exporter(pg_client, config)
    s3_exporter.connect()

    # Start scheduler
    scheduler_task = asyncio.create_task(scheduler_loop())

    yield

    # Shutdown
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

    ch_client.close()
    pg_client.close()
    logger.info("Aggregation Service stopped")


app = FastAPI(
    title="Aggregation Service",
    description="Computes business metrics from ClickHouse and exports to PostgreSQL/S3",
    version="1.0.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    status: str
    clickhouse_connected: bool
    postgres_connected: bool


class ComputeResponse(BaseModel):
    status: str
    date: str
    metrics: dict


class ExportResponse(BaseModel):
    status: str
    date: str
    s3_path: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    ch_ok = False
    pg_ok = False

    try:
        ch_client.query("SELECT 1")
        ch_ok = True
    except Exception:
        pass

    try:
        pg_client.fetch_all("SELECT 1")
        pg_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if (ch_ok and pg_ok) else "degraded",
        clickhouse_connected=ch_ok,
        postgres_connected=pg_ok,
    )


@app.post("/compute", response_model=ComputeResponse)
async def compute_metrics(
    target_date: date = Query(default=None, description="Date to compute metrics for (YYYY-MM-DD)"),
):
    """
    Manually trigger metrics computation for a specific date.
    If no date is provided, computes for today.
    """
    if target_date is None:
        target_date = date.today()

    try:
        results = metrics_computer.compute_all_metrics(target_date)

        # Simplify results for response
        summary = {
            "dau": results["dau"],
            "avg_view_duration": results["avg_view_duration"]["avg_duration"],
            "total_finished_views": results["avg_view_duration"]["total_finished"],
            "view_conversion_rate": results["view_conversion"]["conversion_rate"],
            "top_movies_count": len(results["top_movies"]),
            "retention_data_points": len(results["retention"]),
            "device_types": len(results["device_distribution"]),
        }

        return ComputeResponse(
            status="success",
            date=target_date.isoformat(),
            metrics=summary,
        )
    except Exception as e:
        logger.error("Compute failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export", response_model=ExportResponse)
async def export_to_s3(
    target_date: date = Query(default=None, description="Date to export (YYYY-MM-DD)"),
):
    """
    Export metrics for a specific date to S3.
    If no date is provided, exports for today.
    """
    if target_date is None:
        target_date = date.today()

    try:
        s3_path = s3_exporter.export_daily(target_date)
        return ExportResponse(
            status="success" if s3_path else "no_data",
            date=target_date.isoformat(),
            s3_path=s3_path,
        )
    except Exception as e:
        logger.error("Export failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics(
    target_date: date = Query(default=None, description="Date to get metrics for"),
    metric_name: str = Query(default=None, description="Filter by metric name"),
):
    """Get stored metrics from PostgreSQL."""
    if target_date is None:
        target_date = date.today()

    try:
        if metric_name:
            rows = pg_client.fetch_all(
                "SELECT * FROM metrics WHERE metric_date = %s AND metric_name = %s ORDER BY metric_name",
                (target_date, metric_name),
            )
        else:
            rows = pg_client.fetch_all(
                "SELECT * FROM metrics WHERE metric_date = %s ORDER BY metric_name",
                (target_date,),
            )

        return {
            "date": target_date.isoformat(),
            "count": len(rows),
            "metrics": rows,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
