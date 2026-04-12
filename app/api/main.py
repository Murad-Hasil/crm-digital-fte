"""
FastAPI application entry point.
Manages lifespan (DB pool + Kafka/local producer) and mounts all routers.

When USE_LOCAL_QUEUE=true (Hugging Face Spaces):
  - asyncio.Queue replaces Kafka
  - A background task drains the queue and calls process_message()
  - Gmail credentials are written from GMAIL_CREDENTIALS_JSON env var
  - Everything runs in a single process on port 7860
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webhooks import router as webhook_router
from app.channels.web_form_handler import router as web_form_router
from app.core.kafka import kafka_producer
from app.db.session import close_db_pool, init_db_pool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_USE_LOCAL_QUEUE = os.getenv("USE_LOCAL_QUEUE", "false").lower() == "true"


def _write_gmail_credentials_from_env() -> None:
    """
    HF Spaces: write Gmail credentials JSON from env var to file.
    Set GMAIL_CREDENTIALS_JSON to the full contents of gmail_credentials.json.
    """
    creds_json = os.getenv("GMAIL_CREDENTIALS_JSON", "").strip()
    if not creds_json:
        return
    creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json")
    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    with open(creds_path, "w") as f:
        f.write(creds_json)
    logger.info("Gmail credentials written from env var → %s", creds_path)


async def _local_queue_consumer(queue: asyncio.Queue) -> None:
    """
    Drains the local asyncio.Queue and calls process_message() for each item.
    Runs as a background task when USE_LOCAL_QUEUE=true.
    """
    from app.worker.message_processor import process_message
    logger.info("Local queue consumer started.")
    while True:
        try:
            msg = await queue.get()
            await process_message(msg)
        except asyncio.CancelledError:
            logger.info("Local queue consumer cancelled.")
            break
        except Exception as exc:
            logger.error("Local queue consumer error: %s", exc)
        finally:
            try:
                queue.task_done()
            except Exception:
                pass


async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    _write_gmail_credentials_from_env()
    await init_db_pool()
    await kafka_producer.start()

    consumer_task: asyncio.Task | None = None

    if _USE_LOCAL_QUEUE:
        # Initialise agent (normally done by worker process, here we do it inline)
        from app.agents.customer_success_agent import init_agent
        init_agent()
        queue = kafka_producer.get_local_queue()
        consumer_task = asyncio.create_task(_local_queue_consumer(queue))
        logger.info("HF Spaces mode: local queue consumer running in background.")

    logger.info("Customer Success FTE API started.")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    await kafka_producer.stop()
    await close_db_pool()
    logger.info("Customer Success FTE API shut down.")


app = FastAPI(
    title="Customer Success FTE API — CloudScale AI",
    description="24/7 AI-powered customer support across Email, WhatsApp, and Web Form",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(web_form_router)


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "mode": "local_queue" if _USE_LOCAL_QUEUE else "kafka",
        "channels": {
            "email": os.getenv("GMAIL_ENABLED", "true"),
            "whatsapp": os.getenv("WHATSAPP_ENABLED", "true"),
            "web_form": os.getenv("WEBFORM_ENABLED", "true"),
        },
    }
