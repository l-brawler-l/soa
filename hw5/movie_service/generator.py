"""Synthetic event generator that simulates realistic user behavior."""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from movie_service.config import Config
from movie_service.producer import MovieEventProducer

logger = logging.getLogger(__name__)

DEVICE_TYPES = ["MOBILE", "DESKTOP", "TV", "TABLET"]
DEVICE_WEIGHTS = [0.4, 0.3, 0.15, 0.15]


class UserSession:
    """Tracks state of a simulated user session."""

    def __init__(self, user_id: str, movie_id: str, device_type: str):
        self.user_id = user_id
        self.movie_id = movie_id
        self.device_type = device_type
        self.session_id = str(uuid4())
        self.progress_seconds = 0
        self.state = "idle"  # idle, watching, paused, finished
        self.movie_duration = random.randint(60 * 60, 3 * 60 * 60)  # 1-3 hours


class EventGenerator:
    """Generates realistic synthetic movie events."""

    def __init__(self, producer: MovieEventProducer, config: Optional[Config] = None):
        self.producer = producer
        self.config = config or Config()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Generate user and movie IDs
        self.user_ids = [f"user_{i:04d}" for i in range(1, self.config.GENERATOR_NUM_USERS + 1)]
        self.movie_ids = [f"movie_{i:03d}" for i in range(1, self.config.GENERATOR_NUM_MOVIES + 1)]

        # Active sessions per user
        self.active_sessions: Dict[str, UserSession] = {}

        # Track first activity dates for retention simulation
        self.user_first_seen: Dict[str, datetime] = {}

    def start(self) -> None:
        """Start the event generator in background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._generate_loop())
        logger.info(
            "Event generator started: %d users, %d movies, interval=%dms",
            self.config.GENERATOR_NUM_USERS,
            self.config.GENERATOR_NUM_MOVIES,
            self.config.GENERATOR_INTERVAL_MS,
        )

    async def stop(self) -> None:
        """Stop the event generator."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event generator stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _generate_loop(self) -> None:
        """Main generation loop."""
        interval = self.config.GENERATOR_INTERVAL_MS / 1000.0

        # Generate some historical data first (for retention metrics)
        await self._generate_historical_data()

        while self._running:
            try:
                self._generate_event()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error generating event: %s", e)
                await asyncio.sleep(1)

    async def _generate_historical_data(self) -> None:
        """Generate events for the past 10 days to populate retention data."""
        logger.info("Generating historical data for past 10 days...")
        now = datetime.now(timezone.utc)

        for days_ago in range(10, 0, -1):
            base_time = now - timedelta(days=days_ago)
            # Each day, some subset of users are active
            daily_active = random.sample(
                self.user_ids,
                k=random.randint(
                    len(self.user_ids) // 3,
                    len(self.user_ids),
                ),
            )

            for user_id in daily_active:
                if user_id not in self.user_first_seen:
                    self.user_first_seen[user_id] = base_time

                movie_id = random.choice(self.movie_ids)
                device = random.choices(DEVICE_TYPES, weights=DEVICE_WEIGHTS, k=1)[0]
                session_id = str(uuid4())
                event_time = base_time + timedelta(
                    hours=random.randint(8, 22),
                    minutes=random.randint(0, 59),
                )

                # Generate a viewing session
                progress = 0
                self.producer.publish_event(
                    user_id=user_id,
                    movie_id=movie_id,
                    event_type="VIEW_STARTED",
                    device_type=device,
                    session_id=session_id,
                    progress_seconds=progress,
                    timestamp=event_time,
                )

                # Some users pause
                if random.random() < 0.3:
                    progress += random.randint(300, 1800)
                    event_time += timedelta(seconds=progress)
                    self.producer.publish_event(
                        user_id=user_id,
                        movie_id=movie_id,
                        event_type="VIEW_PAUSED",
                        device_type=device,
                        session_id=session_id,
                        progress_seconds=progress,
                        timestamp=event_time,
                    )

                    event_time += timedelta(minutes=random.randint(1, 30))
                    self.producer.publish_event(
                        user_id=user_id,
                        movie_id=movie_id,
                        event_type="VIEW_RESUMED",
                        device_type=device,
                        session_id=session_id,
                        progress_seconds=progress,
                        timestamp=event_time,
                    )

                # Most users finish watching
                if random.random() < 0.6:
                    progress += random.randint(1800, 7200)
                    event_time += timedelta(seconds=random.randint(1800, 7200))
                    self.producer.publish_event(
                        user_id=user_id,
                        movie_id=movie_id,
                        event_type="VIEW_FINISHED",
                        device_type=device,
                        session_id=session_id,
                        progress_seconds=progress,
                        timestamp=event_time,
                    )

                # Some users like the movie
                if random.random() < 0.4:
                    event_time += timedelta(seconds=random.randint(1, 60))
                    self.producer.publish_event(
                        user_id=user_id,
                        movie_id=movie_id,
                        event_type="LIKED",
                        device_type=device,
                        session_id=session_id,
                        progress_seconds=0,
                        timestamp=event_time,
                    )

                # Some users search
                if random.random() < 0.2:
                    self.producer.publish_event(
                        user_id=user_id,
                        movie_id=random.choice(self.movie_ids),
                        event_type="SEARCHED",
                        device_type=device,
                        session_id=session_id,
                        progress_seconds=0,
                        timestamp=event_time + timedelta(seconds=random.randint(1, 300)),
                    )

            self.producer.flush(timeout=10)
            # Small delay to not overwhelm Kafka
            await asyncio.sleep(0.1)

        logger.info("Historical data generation complete")

    def _generate_event(self) -> None:
        """Generate a single realistic event."""
        user_id = random.choice(self.user_ids)
        now = datetime.now(timezone.utc)

        if user_id not in self.user_first_seen:
            self.user_first_seen[user_id] = now

        session = self.active_sessions.get(user_id)

        if session is None or session.state == "finished":
            # Start a new session
            movie_id = random.choice(self.movie_ids)
            device = random.choices(DEVICE_TYPES, weights=DEVICE_WEIGHTS, k=1)[0]
            session = UserSession(user_id, movie_id, device)
            self.active_sessions[user_id] = session

            session.state = "watching"
            self.producer.publish_event(
                user_id=user_id,
                movie_id=session.movie_id,
                event_type="VIEW_STARTED",
                device_type=session.device_type,
                session_id=session.session_id,
                progress_seconds=0,
                timestamp=now,
            )
        elif session.state == "watching":
            # Progress the session
            session.progress_seconds += random.randint(30, 300)

            action = random.choices(
                ["continue", "pause", "finish", "like", "search"],
                weights=[0.3, 0.15, 0.25, 0.15, 0.15],
                k=1,
            )[0]

            if action == "pause":
                session.state = "paused"
                self.producer.publish_event(
                    user_id=user_id,
                    movie_id=session.movie_id,
                    event_type="VIEW_PAUSED",
                    device_type=session.device_type,
                    session_id=session.session_id,
                    progress_seconds=session.progress_seconds,
                    timestamp=now,
                )
            elif action == "finish" or session.progress_seconds >= session.movie_duration:
                session.state = "finished"
                self.producer.publish_event(
                    user_id=user_id,
                    movie_id=session.movie_id,
                    event_type="VIEW_FINISHED",
                    device_type=session.device_type,
                    session_id=session.session_id,
                    progress_seconds=session.progress_seconds,
                    timestamp=now,
                )
            elif action == "like":
                self.producer.publish_event(
                    user_id=user_id,
                    movie_id=session.movie_id,
                    event_type="LIKED",
                    device_type=session.device_type,
                    session_id=session.session_id,
                    progress_seconds=0,
                    timestamp=now,
                )
            elif action == "search":
                self.producer.publish_event(
                    user_id=user_id,
                    movie_id=random.choice(self.movie_ids),
                    event_type="SEARCHED",
                    device_type=session.device_type,
                    session_id=session.session_id,
                    progress_seconds=0,
                    timestamp=now,
                )
        elif session.state == "paused":
            session.state = "watching"
            self.producer.publish_event(
                user_id=user_id,
                movie_id=session.movie_id,
                event_type="VIEW_RESUMED",
                device_type=session.device_type,
                session_id=session.session_id,
                progress_seconds=session.progress_seconds,
                timestamp=now,
            )
