"""
FastAPI application entry point.
Manages lifespan (DB pool + Kafka producer) and mounts all routers.
"""

import logging
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webhooks import router as webhook_router
from app.core.kafka import kafka_producer
from app.db.session import close_db_pool, init_db_pool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    await init_db_pool()
    await kafka_producer.start()
    logger.info("Customer Success FTE API started.")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────
    await kafka_producer.stop()
    await close_db_pool()
    logger.info("Customer Success FTE API shut down.")


app = FastAPI(
    title="Customer Success FTE API",
    description="24/7 AI-powered customer support across Email, WhatsApp, and Web",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "channels": {
            "email": os.getenv("GMAIL_ENABLED", "true"),
            "whatsapp": os.getenv("WHATSAPP_ENABLED", "true"),
            "web_form": os.getenv("WEBFORM_ENABLED", "true"),
        },
    }
