"""S3 exporter: exports daily aggregates from PostgreSQL to MinIO/S3."""

import csv
import io
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from minio import Minio
from minio.error import S3Error

from aggregation_service.config import Config
from aggregation_service.database import PostgresClient

logger = logging.getLogger(__name__)


class S3Exporter:
    """Exports daily metrics from PostgreSQL to S3-compatible storage (MinIO)."""

    def __init__(self, pg_client: PostgresClient, config: Optional[Config] = None):
        self.pg = pg_client
        self.config = config or Config()
        self._minio_client: Optional[Minio] = None

    def connect(self) -> None:
        """Initialize MinIO client."""
        max_retries = 5
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self._minio_client = Minio(
                    self.config.MINIO_ENDPOINT,
                    access_key=self.config.MINIO_ACCESS_KEY,
                    secret_key=self.config.MINIO_SECRET_KEY,
                    secure=self.config.MINIO_SECURE,
                )
                # Test connection
                self._minio_client.bucket_exists(self.config.MINIO_BUCKET)
                logger.info("Connected to MinIO at %s", self.config.MINIO_ENDPOINT)
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to MinIO (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2

        raise ConnectionError("Failed to connect to MinIO after retries")

    def export_daily(self, target_date: date) -> str:
        """
        Export all metrics for a given date to S3 as JSON.
        Returns the S3 object path.

        Path format: daily/YYYY-MM-DD/aggregates.json
        Overwrites existing file for idempotency.
        """
        if not self._minio_client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                # Fetch metrics from PostgreSQL
                metrics = self.pg.fetch_all(
                    """
                    SELECT metric_date, metric_name, metric_value, extra_data, computed_at
                    FROM metrics
                    WHERE metric_date = %s
                    ORDER BY metric_name
                    """,
                    (target_date,),
                )

                if not metrics:
                    logger.warning("No metrics found for %s, skipping export", target_date)
                    return ""

                # Build export data
                export_data = {
                    "date": target_date.isoformat(),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "metrics_count": len(metrics),
                    "metrics": [],
                }

                for m in metrics:
                    export_data["metrics"].append({
                        "metric_date": m["metric_date"].isoformat() if isinstance(m["metric_date"], date) else str(m["metric_date"]),
                        "metric_name": m["metric_name"],
                        "metric_value": float(m["metric_value"]),
                        "extra_data": m["extra_data"],
                        "computed_at": m["computed_at"].isoformat() if isinstance(m["computed_at"], datetime) else str(m["computed_at"]),
                    })

                # Serialize to JSON
                json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
                data_bytes = json_data.encode("utf-8")

                # Upload to S3
                object_name = f"daily/{target_date.isoformat()}/aggregates.json"
                self._minio_client.put_object(
                    bucket_name=self.config.MINIO_BUCKET,
                    object_name=object_name,
                    data=io.BytesIO(data_bytes),
                    length=len(data_bytes),
                    content_type="application/json",
                )

                logger.info(
                    "Exported %d metrics for %s to s3://%s/%s",
                    len(metrics), target_date, self.config.MINIO_BUCKET, object_name,
                )
                return f"s3://{self.config.MINIO_BUCKET}/{object_name}"

            except S3Error as e:
                logger.error(
                    "S3 error during export (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2
            except Exception as e:
                logger.error(
                    "Export failed (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2

        logger.error("Failed to export metrics for %s after %d retries", target_date, max_retries)
        return ""
