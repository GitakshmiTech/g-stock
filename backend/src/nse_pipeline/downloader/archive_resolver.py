"""NSE Archive URL and Filename Resolver."""

from datetime import date

from nse_pipeline.core.clock import parse_date
from nse_pipeline.core.constants import (
    NSE_LEGACY_BHAVCOPY_URL_TEMPLATE,
    NSE_UDIFF_BHAVCOPY_URL_TEMPLATE,
    UDIFF_TRANSITION_DATE,
    SourceFormat,
)


class ArchiveResolver:
    """Resolves correct archive URLs and expected filenames for any NSE trading date."""

    TRANSITION_DATE = parse_date(UDIFF_TRANSITION_DATE)

    @classmethod
    def get_source_format_for_date(cls, trade_date: date) -> SourceFormat:
        if trade_date >= cls.TRANSITION_DATE:
            return SourceFormat.UDIFF_BHAVCOPY
        return SourceFormat.LEGACY_BHAVCOPY

    @classmethod
    def resolve_filename(cls, trade_date: date) -> str:
        """Determines expected archive filename for the date."""
        if trade_date >= cls.TRANSITION_DATE:
            date_compact = trade_date.strftime("%Y%m%d")
            return f"BhavCopy_NSE_CM_0_0_0_{date_compact}_F_0000.csv.zip"
        else:
            day = trade_date.strftime("%d")
            month = trade_date.strftime("%b").upper()
            year = trade_date.strftime("%Y")
            return f"cm{day}{month}{year}bhav.csv.zip"

    @classmethod
    def resolve_urls(cls, trade_date: date) -> list[str]:
        """Returns ordered candidate URLs to try for a given trading date."""
        urls = []
        if trade_date >= cls.TRANSITION_DATE:
            date_compact = trade_date.strftime("%Y%m%d")
            # Primary UDiFF link
            urls.append(
                NSE_UDIFF_BHAVCOPY_URL_TEMPLATE.format(date_compact=date_compact)
            )
            # Alternative domain mirror
            urls.append(
                f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_compact}_F_0000.csv.zip"
            )
        else:
            day = trade_date.strftime("%d")
            month = trade_date.strftime("%b").upper()
            year = trade_date.strftime("%Y")
            urls.append(
                NSE_LEGACY_BHAVCOPY_URL_TEMPLATE.format(day=day, month=month, year=year)
            )

        # Fallback daily full bhavdata CSV
        day_month_year = trade_date.strftime("%d%m%Y")
        urls.append(
            f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{day_month_year}.csv"
        )

        return urls
