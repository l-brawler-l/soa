-- ClickHouse schema for movie analytics pipeline
-- This script runs automatically on ClickHouse startup

CREATE DATABASE IF NOT EXISTS movie_analytics;

-- ============================================================
-- 1. Kafka Engine table: reads raw events from Kafka topic
-- ============================================================
CREATE TABLE IF NOT EXISTS movie_analytics.movie_events_kafka (
    event_id String,
    user_id String,
    movie_id String,
    event_type String,
    timestamp DateTime64(3, 'UTC'),
    device_type String,
    session_id String,
    progress_seconds Int32
) ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka-1:29092,kafka-2:29092',
    kafka_topic_list = 'movie-events',
    kafka_group_name = 'clickhouse_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_max_block_size = 1048576;

-- ============================================================
-- 2. MergeTree table: permanent storage for raw events
--    Partitioned by month, sorted by (user_id, timestamp)
--    for efficient user-centric queries
-- ============================================================
CREATE TABLE IF NOT EXISTS movie_analytics.movie_events (
    event_id String,
    user_id String,
    movie_id String,
    event_type String,
    timestamp DateTime64(3, 'UTC'),
    device_type String,
    session_id String,
    progress_seconds Int32,
    event_date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (user_id, timestamp, event_id)
TTL event_date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- ============================================================
-- 3. Materialized View: auto-transfer from Kafka to MergeTree
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS movie_analytics.movie_events_mv
TO movie_analytics.movie_events AS
SELECT
    event_id,
    user_id,
    movie_id,
    event_type,
    timestamp,
    device_type,
    session_id,
    progress_seconds
FROM movie_analytics.movie_events_kafka;

-- ============================================================
-- 4. Aggregation tables for business metrics
-- ============================================================

-- DAU (Daily Active Users)
CREATE TABLE IF NOT EXISTS movie_analytics.daily_active_users (
    event_date Date,
    dau UInt64,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (event_date);

-- Average view duration per day
CREATE TABLE IF NOT EXISTS movie_analytics.daily_avg_view_duration (
    event_date Date,
    avg_duration Float64,
    total_finished UInt64,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (event_date);

-- Top movies by views per day
CREATE TABLE IF NOT EXISTS movie_analytics.daily_top_movies (
    event_date Date,
    movie_id String,
    view_count UInt64,
    rank UInt32,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (event_date, movie_id);

-- View conversion rate per day
CREATE TABLE IF NOT EXISTS movie_analytics.daily_view_conversion (
    event_date Date,
    view_started UInt64,
    view_finished UInt64,
    conversion_rate Float64,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (event_date);

-- Retention D1, D7
CREATE TABLE IF NOT EXISTS movie_analytics.daily_retention (
    cohort_date Date,
    day_offset UInt32,
    cohort_size UInt64,
    retained_users UInt64,
    retention_rate Float64,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (cohort_date, day_offset);

-- Device distribution per day
CREATE TABLE IF NOT EXISTS movie_analytics.daily_device_distribution (
    event_date Date,
    device_type String,
    event_count UInt64,
    user_count UInt64,
    computed_at DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (event_date, device_type);
