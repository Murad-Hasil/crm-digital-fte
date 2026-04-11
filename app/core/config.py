"""
Central configuration loaded from environment variables.
Import `settings` anywhere in the app.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Database
    database_url: str = field(default_factory=lambda: os.environ["DATABASE_URL"])

    # LLM
    groq_api_key: str = field(default_factory=lambda: os.environ["GROQ_API_KEY"])
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"))
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"))

    # Kafka
    kafka_bootstrap_servers: str = field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))

    # Channels
    gmail_enabled: bool = field(default_factory=lambda: os.getenv("GMAIL_ENABLED", "true").lower() == "true")
    whatsapp_enabled: bool = field(default_factory=lambda: os.getenv("WHATSAPP_ENABLED", "true").lower() == "true")
    webform_enabled: bool = field(default_factory=lambda: os.getenv("WEBFORM_ENABLED", "true").lower() == "true")

    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_whatsapp_number: str = field(default_factory=lambda: os.getenv("TWILIO_WHATSAPP_NUMBER", ""))

    gmail_credentials_path: str = field(default_factory=lambda: os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json"))
    gmail_pubsub_topic: str = field(default_factory=lambda: os.getenv("GMAIL_PUBSUB_TOPIC", ""))

    # App
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    cors_origins: list = field(default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))
    max_email_length: int = field(default_factory=lambda: int(os.getenv("MAX_EMAIL_LENGTH", "2000")))
    max_whatsapp_length: int = field(default_factory=lambda: int(os.getenv("MAX_WHATSAPP_LENGTH", "1600")))
    max_webform_length: int = field(default_factory=lambda: int(os.getenv("MAX_WEBFORM_LENGTH", "1000")))


settings = Settings()
