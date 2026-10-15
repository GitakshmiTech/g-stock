"""Configuration management for the NSE Market Data Pipeline."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Application Settings
    app_env: str = Field(default="development", alias="APP_ENV")
    app_timezone: str = Field(default="Asia/Kolkata", alias="APP_TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database Configuration
    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_database: str = Field(default="nse_market_data", alias="MYSQL_DATABASE")
    mysql_user: str = Field(default="nse_app", alias="MYSQL_USER")
    mysql_password: str = Field(default="replace_with_secret", alias="MYSQL_PASSWORD")
    db_dialect: str = Field(default="mysql", alias="DB_DIALECT")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    mysql_url: str | None = Field(default=None, alias="MYSQL_URL")
    mysql_connection_string: str | None = Field(default=None, alias="MYSQL_CONNECTION_STRING")

    # SQLite fallback
    sqlite_db_path: str = Field(default="./data/nse_market_data.db", alias="SQLITE_DB_PATH")
    use_sqlite_fallback: bool = Field(default=True, alias="USE_SQLITE_FALLBACK")

    # MongoDB Configuration (Compass & Analytics Storage)
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="nse_market_data", alias="MONGODB_DATABASE")
    enable_mongodb: bool = Field(default=True, alias="ENABLE_MONGODB")

    # Date Limits
    data_start_date: str = Field(default="2001-01-01", alias="DATA_START_DATE")
    data_end_date: str = Field(default="2026-10-08", alias="DATA_END_DATE")
    backfill_batch_days: int = Field(default=30, alias="BACKFILL_BATCH_DAYS")

    # Storage Directories
    raw_data_dir: str = Field(default="./data/raw", alias="RAW_DATA_DIR")
    processed_data_dir: str = Field(default="./data/processed", alias="PROCESSED_DATA_DIR")
    quarantine_dir: str = Field(default="./data/quarantine", alias="QUARANTINE_DIR")
    exports_dir: str = Field(default="./data/exports", alias="EXPORTS_DIR")

    # Scheduler and Ingestion Timing
    daily_update_time: str = Field(default="16:00", alias="DAILY_UPDATE_TIME")
    daily_retry_max_wait_minutes: int = Field(default=60, alias="DAILY_RETRY_MAX_WAIT_MINUTES")
    daily_retry_initial_seconds: int = Field(default=60, alias="DAILY_RETRY_INITIAL_SECONDS")
    daily_retry_max_seconds: int = Field(default=600, alias="DAILY_RETRY_MAX_SECONDS")
    download_timeout_seconds: int = Field(default=60, alias="DOWNLOAD_TIMEOUT_SECONDS")
    max_download_retries: int = Field(default=5, alias="MAX_DOWNLOAD_RETRIES")

    # Notifications
    alert_email_enabled: bool = Field(default=False, alias="ALERT_EMAIL_ENABLED")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    alert_recipients: str = Field(default="admin@example.com", alias="ALERT_RECIPIENTS")

    @property
    def recipient_list(self) -> list[str]:
        return [r.strip() for r in self.alert_recipients.split(",") if r.strip()]

    @property
    def mysql_connection_url(self) -> str:
        url = self.database_url or self.mysql_url or self.mysql_connection_string
        if url:
            url = url.strip()
            if url.startswith("mysql://"):
                url = "mysql+pymysql://" + url[len("mysql://"):]
            elif not url.startswith("mysql+pymysql://") and "://" not in url:
                url = f"mysql+pymysql://{url}"
            return url

        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sqlite_connection_url(self) -> str:
        db_path = Path(self.sqlite_db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    def ensure_directories(self) -> None:
        """Create required data directories if they do not exist."""
        for d in [self.raw_data_dir, self.processed_data_dir, self.quarantine_dir, self.exports_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
