"""
Kafka producer for publishing normalized ticket events.
Topic: fte.tickets.incoming

When USE_LOCAL_QUEUE=true (e.g. Hugging Face Spaces deployment), an
asyncio.Queue is used instead of a real Kafka broker — no Java required.
The FastAPI lifespan drains the queue in a background task.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TOPIC_TICKETS_INCOMING = "fte.tickets.incoming"

_USE_LOCAL = os.getenv("USE_LOCAL_QUEUE", "false").lower() == "true"


class KafkaProducer:
    """
    Async producer wrapper.

    In Kafka mode  : wraps AIOKafkaProducer.
    In local mode  : wraps asyncio.Queue — used by FastAPI lifespan consumer.
    """

    def __init__(self) -> None:
        self._producer = None
        self._local_queue: asyncio.Queue | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if _USE_LOCAL:
            self._local_queue = asyncio.Queue()
            logger.info("Local asyncio queue started (Kafka bypass — HF Spaces mode).")
            return

        from aiokafka import AIOKafkaProducer

        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()
        logger.info("Kafka producer started (bootstrap=%s).", bootstrap)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped.")
        if self._local_queue is not None:
            logger.info("Local queue stopped.")

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, topic: str, event: dict) -> None:
        """Publish a single event dict to the given topic."""
        event.setdefault("published_at", datetime.now(timezone.utc).isoformat())

        if _USE_LOCAL:
            if self._local_queue is None:
                raise RuntimeError("Local queue not started. Call start() first.")
            await self._local_queue.put(event)
            logger.debug("Queued local event: channel=%s", event.get("channel"))
            return

        if self._producer is None:
            raise RuntimeError("KafkaProducer is not started. Call start() first.")
        await self._producer.send_and_wait(topic, event)
        logger.debug("Published event to %s: channel=%s", topic, event.get("channel"))

    async def publish_ticket(self, event: dict) -> None:
        """Convenience method — publishes to the unified incoming ticket topic."""
        await self.publish(TOPIC_TICKETS_INCOMING, event)

    # ------------------------------------------------------------------
    # Local queue access (used by main.py lifespan consumer)
    # ------------------------------------------------------------------

    def get_local_queue(self) -> "asyncio.Queue | None":
        return self._local_queue


# Module-level singleton — initialised during FastAPI lifespan
kafka_producer = KafkaProducer()
