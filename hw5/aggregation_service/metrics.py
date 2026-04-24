"""Business metrics computation from ClickHouse data."""

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from aggregation_service.database import ClickHouseClient, PostgresClient

logger = logging.getLogger(__name__)


class MetricsComputer:
    """Computes business metrics from ClickHouse and stores in PostgreSQL."""

    def __init__(self, ch_client: ClickHouseClient, pg_client: PostgresClient):
        self.ch = ch_client
        self.pg = pg_client

    def compute_all_metrics(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Compute all business metrics for a given date.
        Returns a summary of computed metrics.
        """
        if target_date is None:
            target_date = date.today()

        start_time = time.time()
        logger.info("Starting metrics computation for %s", target_date)

        results = {}

        try:
            results["dau"] = self._compute_dau(target_date)
            results["avg_view_duration"] = self._compute_avg_view_duration(target_date)
            results["top_movies"] = self._compute_top_movies(target_date)
            results["view_conversion"] = self._compute_view_conversion(target_date)
            results["retention"] = self._compute_retention(target_date)
            results["device_distribution"] = self._compute_device_distribution(target_date)

            # Export to PostgreSQL
            self._export_to_postgres(target_date, results)

            elapsed = time.time() - start_time
            logger.info(
                "Metrics computation complete for %s: %.2fs elapsed, results=%s",
                target_date, elapsed, {k: type(v).__name__ for k, v in results.items()},
            )
            return results

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "Metrics computation failed for %s after %.2fs: %s",
                target_date, elapsed, e,
            )
            raise

    def _compute_dau(self, target_date: date) -> int:
        """DAU: count of unique users for the day."""
        result = self.ch.query(
            """
            SELECT uniq(user_id) AS dau
            FROM movie_analytics.movie_events
            WHERE toDate(timestamp) = %(target_date)s
            """,
            parameters={"target_date": target_date.isoformat()},
        )
        dau = result.result_rows[0][0] if result.result_rows else 0

        # Store in ClickHouse aggregation table
        self.ch.command(
            """
            INSERT INTO movie_analytics.daily_active_users (event_date, dau)
            VALUES (%(event_date)s, %(dau)s)
            """,
            parameters={"event_date": target_date.isoformat(), "dau": dau},
        )

        logger.info("DAU for %s: %d", target_date, dau)
        return dau

    def _compute_avg_view_duration(self, target_date: date) -> Dict[str, Any]:
        """Average view duration for completed views."""
        result = self.ch.query(
            """
            SELECT
                avg(progress_seconds) AS avg_duration,
                count() AS total_finished
            FROM movie_analytics.movie_events
            WHERE toDate(timestamp) = %(target_date)s
              AND event_type = 'VIEW_FINISHED'
              AND progress_seconds > 0
            """,
            parameters={"target_date": target_date.isoformat()},
        )

        if result.result_rows and result.result_rows[0][1] > 0:
            avg_dur = float(result.result_rows[0][0])
            total = int(result.result_rows[0][1])
        else:
            avg_dur = 0.0
            total = 0

        self.ch.command(
            """
            INSERT INTO movie_analytics.daily_avg_view_duration (event_date, avg_duration, total_finished)
            VALUES (%(event_date)s, %(avg_duration)s, %(total_finished)s)
            """,
            parameters={
                "event_date": target_date.isoformat(),
                "avg_duration": avg_dur,
                "total_finished": total,
            },
        )

        logger.info("Avg view duration for %s: %.1fs (%d finished)", target_date, avg_dur, total)
        return {"avg_duration": avg_dur, "total_finished": total}

    def _compute_top_movies(self, target_date: date, limit: int = 10) -> List[Dict]:
        """Top movies by view count."""
        result = self.ch.query(
            """
            SELECT
                movie_id,
                count() AS view_count,
                row_number() OVER (ORDER BY count() DESC) AS rank
            FROM movie_analytics.movie_events
            WHERE toDate(timestamp) = %(target_date)s
              AND event_type IN ('VIEW_STARTED', 'VIEW_FINISHED')
            GROUP BY movie_id
            ORDER BY view_count DESC
            LIMIT %(limit)s
            """,
            parameters={"target_date": target_date.isoformat(), "limit": limit},
        )

        movies = []
        for row in result.result_rows:
            movie_id, view_count, rank = row[0], int(row[1]), int(row[2])
            movies.append({"movie_id": movie_id, "view_count": view_count, "rank": rank})

            self.ch.command(
                """
                INSERT INTO movie_analytics.daily_top_movies (event_date, movie_id, view_count, rank)
                VALUES (%(event_date)s, %(movie_id)s, %(view_count)s, %(rank)s)
                """,
                parameters={
                    "event_date": target_date.isoformat(),
                    "movie_id": movie_id,
                    "view_count": view_count,
                    "rank": rank,
                },
            )

        logger.info("Top movies for %s: %d movies ranked", target_date, len(movies))
        return movies

    def _compute_view_conversion(self, target_date: date) -> Dict[str, Any]:
        """View conversion: VIEW_FINISHED / VIEW_STARTED ratio."""
        result = self.ch.query(
            """
            SELECT
                countIf(event_type = 'VIEW_STARTED') AS started,
                countIf(event_type = 'VIEW_FINISHED') AS finished
            FROM movie_analytics.movie_events
            WHERE toDate(timestamp) = %(target_date)s
              AND event_type IN ('VIEW_STARTED', 'VIEW_FINISHED')
            """,
            parameters={"target_date": target_date.isoformat()},
        )

        started = int(result.result_rows[0][0]) if result.result_rows else 0
        finished = int(result.result_rows[0][1]) if result.result_rows else 0
        rate = (finished / started * 100) if started > 0 else 0.0

        self.ch.command(
            """
            INSERT INTO movie_analytics.daily_view_conversion
                (event_date, view_started, view_finished, conversion_rate)
            VALUES (%(event_date)s, %(started)s, %(finished)s, %(rate)s)
            """,
            parameters={
                "event_date": target_date.isoformat(),
                "started": started,
                "finished": finished,
                "rate": rate,
            },
        )

        logger.info(
            "View conversion for %s: %d started, %d finished, %.1f%%",
            target_date, started, finished, rate,
        )
        return {"view_started": started, "view_finished": finished, "conversion_rate": rate}

    def _compute_retention(self, target_date: date) -> List[Dict]:
        """
        Retention D0-D7: for each cohort (first activity date),
        compute the fraction of users who returned on day N.
        """
        result = self.ch.query(
            """
            WITH
                first_seen AS (
                    SELECT
                        user_id,
                        min(toDate(timestamp)) AS cohort_date
                    FROM movie_analytics.movie_events
                    GROUP BY user_id
                ),
                cohort_activity AS (
                    SELECT
                        fs.cohort_date,
                        toDate(me.timestamp) AS activity_date,
                        me.user_id
                    FROM movie_analytics.movie_events me
                    INNER JOIN first_seen fs ON me.user_id = fs.user_id
                    WHERE fs.cohort_date >= %(start_date)s
                      AND fs.cohort_date <= %(target_date)s
                )
            SELECT
                cohort_date,
                dateDiff('day', cohort_date, activity_date) AS day_offset,
                uniq(user_id) AS retained_users
            FROM cohort_activity
            WHERE dateDiff('day', cohort_date, activity_date) BETWEEN 0 AND 7
            GROUP BY cohort_date, day_offset
            ORDER BY cohort_date, day_offset
            """,
            parameters={
                "target_date": target_date.isoformat(),
                "start_date": (target_date.replace(day=max(1, target_date.day - 14))).isoformat(),
            },
        )

        # Get cohort sizes (day 0 users)
        cohort_sizes = {}
        retention_data = []

        for row in result.result_rows:
            cohort_dt = row[0]
            day_offset = int(row[1])
            retained = int(row[2])

            if isinstance(cohort_dt, datetime):
                cohort_dt = cohort_dt.date()

            if day_offset == 0:
                cohort_sizes[cohort_dt] = retained

        for row in result.result_rows:
            cohort_dt = row[0]
            day_offset = int(row[1])
            retained = int(row[2])

            if isinstance(cohort_dt, datetime):
                cohort_dt = cohort_dt.date()

            cohort_size = cohort_sizes.get(cohort_dt, retained)
            rate = (retained / cohort_size * 100) if cohort_size > 0 else 0.0

            retention_data.append({
                "cohort_date": cohort_dt,
                "day_offset": day_offset,
                "cohort_size": cohort_size,
                "retained_users": retained,
                "retention_rate": rate,
            })

            self.ch.command(
                """
                INSERT INTO movie_analytics.daily_retention
                    (cohort_date, day_offset, cohort_size, retained_users, retention_rate)
                VALUES (%(cohort_date)s, %(day_offset)s, %(cohort_size)s, %(retained)s, %(rate)s)
                """,
                parameters={
                    "cohort_date": cohort_dt.isoformat(),
                    "day_offset": day_offset,
                    "cohort_size": cohort_size,
                    "retained": retained,
                    "rate": rate,
                },
            )

        logger.info("Retention computed for %s: %d data points", target_date, len(retention_data))
        return retention_data

    def _compute_device_distribution(self, target_date: date) -> List[Dict]:
        """Device distribution: events and users per device type."""
        result = self.ch.query(
            """
            SELECT
                device_type,
                count() AS event_count,
                uniq(user_id) AS user_count
            FROM movie_analytics.movie_events
            WHERE toDate(timestamp) = %(target_date)s
            GROUP BY device_type
            ORDER BY event_count DESC
            """,
            parameters={"target_date": target_date.isoformat()},
        )

        devices = []
        for row in result.result_rows:
            device_type = row[0]
            event_count = int(row[1])
            user_count = int(row[2])
            devices.append({
                "device_type": device_type,
                "event_count": event_count,
                "user_count": user_count,
            })

            self.ch.command(
                """
                INSERT INTO movie_analytics.daily_device_distribution
                    (event_date, device_type, event_count, user_count)
                VALUES (%(event_date)s, %(device_type)s, %(event_count)s, %(user_count)s)
                """,
                parameters={
                    "event_date": target_date.isoformat(),
                    "device_type": device_type,
                    "event_count": event_count,
                    "user_count": user_count,
                },
            )

        logger.info("Device distribution for %s: %d device types", target_date, len(devices))
        return devices

    def _export_to_postgres(self, target_date: date, results: Dict[str, Any]) -> None:
        """
        Export computed metrics to PostgreSQL.
        Uses UPSERT (ON CONFLICT UPDATE) for idempotency.
        """
        now = datetime.now(timezone.utc)
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                # DAU
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "dau", float(results["dau"]), now),
                )

                # Average view duration
                avg_data = results["avg_view_duration"]
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "avg_view_duration", avg_data["avg_duration"], now),
                )
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "total_finished_views", float(avg_data["total_finished"]), now),
                )

                # View conversion
                conv_data = results["view_conversion"]
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "view_conversion_rate", conv_data["conversion_rate"], now),
                )
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "view_started_count", float(conv_data["view_started"]), now),
                )
                self.pg.execute(
                    """
                    INSERT INTO metrics (metric_date, metric_name, metric_value, computed_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (metric_date, metric_name)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  computed_at = EXCLUDED.computed_at
                    """,
                    (target_date, "view_finished_count", float(conv_data["view_finished"]), now),
                )

                # Top movies (store as JSON-like entries)
                for movie in results["top_movies"]:
                    metric_name = f"top_movie_rank_{movie['rank']}"
                    self.pg.execute(
                        """
                        INSERT INTO metrics (metric_date, metric_name, metric_value, extra_data, computed_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (metric_date, metric_name)
                        DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                      extra_data = EXCLUDED.extra_data,
                                      computed_at = EXCLUDED.computed_at
                        """,
                        (
                            target_date,
                            metric_name,
                            float(movie["view_count"]),
                            movie["movie_id"],
                            now,
                        ),
                    )

                # Retention
                for ret in results["retention"]:
                    cohort_date = ret["cohort_date"]
                    metric_name = f"retention_d{ret['day_offset']}"
                    self.pg.execute(
                        """
                        INSERT INTO metrics (metric_date, metric_name, metric_value, extra_data, computed_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (metric_date, metric_name)
                        DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                      extra_data = EXCLUDED.extra_data,
                                      computed_at = EXCLUDED.computed_at
                        """,
                        (
                            cohort_date,
                            metric_name,
                            ret["retention_rate"],
                            f"cohort_size={ret['cohort_size']},retained={ret['retained_users']}",
                            now,
                        ),
                    )

                # Device distribution
                for dev in results["device_distribution"]:
                    metric_name = f"device_{dev['device_type'].lower()}_events"
                    self.pg.execute(
                        """
                        INSERT INTO metrics (metric_date, metric_name, metric_value, extra_data, computed_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (metric_date, metric_name)
                        DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                      extra_data = EXCLUDED.extra_data,
                                      computed_at = EXCLUDED.computed_at
                        """,
                        (
                            target_date,
                            metric_name,
                            float(dev["event_count"]),
                            f"users={dev['user_count']}",
                            now,
                        ),
                    )

                logger.info("Metrics exported to PostgreSQL for %s", target_date)
                return

            except Exception as e:
                logger.error(
                    "Failed to export to PostgreSQL (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2

        logger.error("Failed to export metrics to PostgreSQL after %d retries", max_retries)
