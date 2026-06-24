import datetime
import logging
from typing import Protocol
import pytz

logger = logging.getLogger(__name__)


class MarketCalendarProvider(Protocol):
    def is_trading_day(self, market: str, date: datetime.date) -> bool: ...  # noqa
    def is_post_close(self, market: str, dt: datetime.datetime) -> bool: ...  # noqa
    def get_latest_close_date(self, market: str, dt: datetime.datetime) -> datetime.date: ...  # noqa


class SimpleMarketCalendarProvider:
    """A simple provider that uses weekdays as a fallback, until exchange_calendars is added."""

    def __init__(self):
        self.market_tz = {
            "sh": pytz.timezone("Asia/Shanghai"),
            "hk": pytz.timezone("Asia/Hong_Kong"),
            "us": pytz.timezone("America/New_York"),
        }
        self.close_times = {
            "sh": datetime.time(15, 0),
            "hk": datetime.time(16, 0),
            "us": datetime.time(16, 0),
        }

    def is_trading_day(self, market: str, date: datetime.date) -> bool:
        # Weekdays only fallback
        return date.weekday() < 5

    def is_post_close(self, market: str, dt: datetime.datetime) -> bool:
        tz = self.market_tz.get(market, pytz.UTC)
        local_dt = dt.astimezone(tz)

        if not self.is_trading_day(market, local_dt.date()):
            return True

        close_t = self.close_times.get(market, datetime.time(16, 0))
        return local_dt.time() >= close_t

    def get_latest_close_date(self, market: str, dt: datetime.datetime) -> datetime.date:
        tz = self.market_tz.get(market, pytz.UTC)
        local_dt = dt.astimezone(tz)
        current_date = local_dt.date()

        if self.is_trading_day(market, current_date):
            if self.is_post_close(market, dt):
                return current_date

        # find previous trading day
        prev = current_date - datetime.timedelta(days=1)
        while not self.is_trading_day(market, prev):
            prev -= datetime.timedelta(days=1)
        return prev


class MarketCloseSchedule:
    def __init__(self, provider: MarketCalendarProvider = None):
        self.provider = provider or SimpleMarketCalendarProvider()

    def get_target_refresh_date(self, market_group: str, dt: datetime.datetime = None) -> datetime.date | None:
        """
        market_group can be 'cn_hk' or 'us'.
        Returns the date that should be refreshed if the markets are closed, else None.
        """
        if dt is None:
            dt = datetime.datetime.now(pytz.UTC)

        if market_group == "cn_hk":
            # Both SH and HK need to be post-close
            sh_date = self.provider.get_latest_close_date("sh", dt)
            hk_date = self.provider.get_latest_close_date("hk", dt)
            # Use the most recent common date, typically they are the same
            if sh_date == hk_date:
                # Ensure it's currently post-close for today if we are returning today
                if self.provider.is_post_close("sh", dt) and self.provider.is_post_close("hk", dt):
                    return sh_date
            return min(sh_date, hk_date)

        elif market_group == "us":
            us_date = self.provider.get_latest_close_date("us", dt)
            if self.provider.is_post_close("us", dt):
                return us_date
            else:
                # Return previous trading day
                prev = us_date - datetime.timedelta(days=1)
                while not self.provider.is_trading_day("us", prev):
                    prev -= datetime.timedelta(days=1)
                return prev

        return None
