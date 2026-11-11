"""Application configuration. Everything sensitive comes from environment variables."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")  # set to "production" on Render
    SECRET_KEY = os.environ.get("SECRET_KEY")  # auto-generated and persisted if missing
    DATABASE = os.environ.get("DATABASE_PATH", str(INSTANCE_DIR / "tracker.db"))
    TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
    SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    LOG_DIR = os.environ.get("LOG_DIR", str(BASE_DIR / "logs"))
    PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "15"))

    # Session / cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("APP_ENV", "development") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 1024 * 1024
