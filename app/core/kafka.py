"""
Kafka producer for publishing normalized ticket events.
Topic: fte.tickets.incoming
"""

import json
import logging
import os
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

TOPIC_TICKETS_INCOMING = "fte.tickets.incoming"


class KafkaProducer:
    """Async Kafka producer wrapper. Call start() on app startup, stop() on shutdown."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            acks="all",          # Wait for all in-sync replicas to acknowledge
            enable_idempotence=True,
        )
        await self._producer.start()
        logger.info("Kafka producer started (bootstrap=%s).", bootstrap)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped.")

    async def publish(self, topic: str, event: dict) -> None:
        """Publish a single event dict to the given topic."""
        if self._producer is None:
            raise RuntimeError("KafkaProducer is not started. Call start() first.")
        event.setdefault("published_at", datetime.now(timezone.utc).isoformat())
        await self._producer.send_and_wait(topic, event)
        logger.debug("Published event to %s: channel=%s", topic, event.get("channel"))

    async def publish_ticket(self, event: dict) -> None:
        """Convenience method — publishes to the unified incoming ticket topic."""
        await self.publish(TOPIC_TICKETS_INCOMING, event)


# Module-level singleton — initialised during FastAPI lifespan
kafka_producer = KafkaProducer()
