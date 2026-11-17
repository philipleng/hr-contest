"""统一业务时区工具（默认 Asia/Manila）

库表 DATETIME 列统一存储无 tzinfo 的业务墙上时间（naive local Manila datetime）。
Windows 宿主机通常未安装 tzdata，ZoneInfo("Asia/Manila") 会抛出 ZoneInfoNotFoundError；
因此这里内置纯标准库固定偏移回退，避免引入额外第三方依赖。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings

_FIXED_TZ_HOURS: dict[str, int] = {
    "UTC": 0,
    "ETC/UTC": 0,
    "GMT": 0,
    "ETC/GMT": 0,
    "ASIA/MANILA": 8,
    "ASIA/SHANGHAI": 8,
    "ASIA/SINGAPORE": 8,
    "ASIA/TAIPEI": 8,
    "ASIA/HONG_KONG": 8,
}

_OFFSET_PATTERN = re.compile(
    r"^(?:(?:UTC|GMT)\s*)?([+-])(\d{1,2})(?::?(\d{2}))?$",
    re.IGNORECASE,
)


def _fallback_tz(tz_name: str) -> tzinfo:
    upper = tz_name.upper()
    if upper in _FIXED_TZ_HOURS:
        hours = _FIXED_TZ_HOURS[upper]
        if hours == 0:
            return timezone.utc
        return timezone(timedelta(hours=hours), name=tz_name)

    match = _OFFSET_PATTERN.fullmatch(tz_name)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3) or 0)
        if hours >= 24 or minutes >= 60:
            raise ValueError(f"Invalid timezone offset: {tz_name}")
        delta = sign * timedelta(hours=hours, minutes=minutes)
        if delta == timedelta(0):
            return timezone.utc
        return timezone(delta, name=tz_name)

    raise ValueError(f"Unsupported timezone: {tz_name}")


@lru_cache(maxsize=16)
def resolve_timezone(tz_name: str) -> tzinfo:
    """将时区名解析为 tzinfo；缺失 tzdata 时回退纯标准库固定偏移。"""
    cleaned = tz_name.strip()
    if not cleaned:
        raise ValueError("Timezone name cannot be empty.")
    try:
        return ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, KeyError, OSError):
        return _fallback_tz(cleaned)


def get_app_tz(tz_name: str | None = None) -> tzinfo:
    """获取当前配置的业务时区对象。"""
    name = tz_name if tz_name is not None else settings.app_timezone
    return resolve_timezone(name)


def now_local() -> datetime:
    """返回当前业务时区的 naive 墙上时间（对齐库表 DATETIME）。"""
    return datetime.now(get_app_tz()).replace(tzinfo=None)


def today_local() -> date:
    """返回当前业务时区的自然日日期。"""
    return now_local().date()


def day_start(d: date) -> datetime:
    """返回指定日期的 00:00:00（半开区间左端点）。"""
    return datetime.combine(d, time.min)


def next_day_start(d: date) -> datetime:
    """返回指定日期次日的 00:00:00（半开区间右端点，禁止使用 time.max）。"""
    return datetime.combine(d + timedelta(days=1), time.min)


def day_range(d: date | None = None) -> tuple[datetime, datetime]:
    """返回 [当天 00:00:00, 次日 00:00:00) 半开时间区间。"""
    target = d if d is not None else today_local()
    return day_start(target), next_day_start(target)
