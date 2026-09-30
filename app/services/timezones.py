"""Conversion between stored timestamps and the viewer's local time.

Every timestamp in the database is naive UTC (see models.utcnow). The
browser reports its IANA timezone in the ``tz`` cookie (set by base.html),
and everything shown to or typed in by the user is converted through it,
so the whole UI uses browser time, just like the chart does.
"""

from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import has_request_context, request

TZ_COOKIE = "tz"


def current_tz():
    """The viewer's timezone, or UTC if unknown (no cookie yet, bad value, no request)."""
    name = request.cookies.get(TZ_COOKIE) if has_request_context() else None
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return timezone.utc


def to_local(dt):
    """Stored naive-UTC datetime -> aware datetime in the viewer's timezone."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(current_tz())


def local_to_utc(dt):
    """Datetime typed into a form (naive, viewer's local time) -> naive UTC for storage."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=current_tz())
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def aware_to_utc(dt):
    """API timestamps: offset-aware values are converted to UTC; naive ones are already UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_iso(dt):
    """ISO string with an explicit Z, so JavaScript's Date.parse doesn't read it as local time."""
    return dt.isoformat() + "Z"


def localtime_filter(dt, fmt="%Y-%m-%d %H:%M %Z"):
    local = to_local(dt)
    return local.strftime(fmt) if local else ""
