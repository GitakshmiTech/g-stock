"""Constants and Enums for the NSE Market Data Pipeline."""

from enum import StrEnum


class SourceFormat(StrEnum):
    LEGACY_BHAVCOPY = "legacy_bhavcopy"
    UDIFF_BHAVCOPY = "udiff_bhavcopy"
    CSV = "csv"
    ZIP = "zip"
    GZIP = "gzip"
    PAID_FEED = "paid_feed"


class JobType(StrEnum):
    DAILY = "DAILY"
    BACKFILL = "BACKFILL"
    MANUAL = "MANUAL"
    RECOVERY = "RECOVERY"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class FileStatus(StrEnum):
    PENDING = "PENDING"
    DOWNLOADED = "DOWNLOADED"
    PARSED = "PARSED"
    IMPORTED = "IMPORTED"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SeverityLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CorporateActionEventType(StrEnum):
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    DIVIDEND = "DIVIDEND"
    RIGHTS = "RIGHTS"
    MERGER = "MERGER"
    DEMERGER = "DEMERGER"
    OTHER = "OTHER"


# Standard NSE equity series
STANDARD_EQUITY_SERIES = ("EQ", "BE", "BZ", "SM", "ST")

# Transition date from legacy bhavcopy to UDiFF bhavcopy
UDIFF_TRANSITION_DATE = "2024-07-08"

# NSE URL templates
NSE_LEGACY_BHAVCOPY_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES/{year}/{month}/cm{day}{month}{year}bhav.csv.zip"
)
NSE_UDIFF_BHAVCOPY_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_compact}_F_0000.csv.zip"
)
NSE_HOME_URL = "https://www.nseindia.com"

# Default User-Agent to avoid aggressive automated bot blocking
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
