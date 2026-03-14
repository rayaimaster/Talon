"""
Date/time tool — provides current time, timezone conversion, and formatting.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfoNotFoundError, available_timezones

logger = logging.getLogger(__name__)


async def get_datetime(timezone_name: str = "UTC") -> str:
    """
    Return the current date and time in the requested timezone.

    Args:
        timezone_name: IANA timezone name, e.g. "UTC", "US/Eastern",
                       "Europe/London", "Asia/Tokyo".

    Returns:
        A formatted string with date, time, timezone, and day of week.
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %r, falling back to UTC", timezone_name)
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("UTC")
        timezone_name = "UTC (fallback — original timezone not found)"

    now = datetime.now(tz)

    return (
        f"Current date/time:\n"
        f"  Date:      {now.strftime('%Y-%m-%d')}\n"
        f"  Time:      {now.strftime('%H:%M:%S')}\n"
        f"  Timezone:  {timezone_name}\n"
        f"  Day:       {now.strftime('%A')}\n"
        f"  ISO 8601:  {now.isoformat()}\n"
        f"  Unix ts:   {int(now.timestamp())}"
    )
