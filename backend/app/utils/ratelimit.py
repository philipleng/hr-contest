"""进程内简易限流与每日配额

说明：
- 单机单进程足够用；多 worker 部署时各进程独立计数，实际额度会放大（已知限制）。
- 不手动解析 X-Forwarded-For，避免客户端伪造该头绕过限流。
  uvicorn 默认 proxy_headers=True 且只信任 127.0.0.1，同机 Nginx 转发时会自动
  把 request.client.host 改写为真实客户端 IP；容器部署需通过
  --forwarded-allow-ips 指定可信代理网段。
- 每日配额只用于匿名流量；已登录 staff 的扫楼代录不限次数（由调用方判断）。
"""

from time import time

from fastapi import HTTPException, Request, status

from app.utils.tz import today_local

# key = "bucket:identity"，value = 该身份最近的请求时间戳列表
_buckets: dict[str, list[float]] = {}
# key = "bucket:identity"，value = (日期串, 请求次数, 已用字节数)
_daily: dict[str, tuple[str, int, int]] = {}

_PRUNE_THRESHOLD = 5000
_PRUNE_IDLE_SECONDS = 3600


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    """字典过大时清理长期无活动的桶，防止内存无限增长"""
    stale = [k for k, v in _buckets.items() if not v or now - v[-1] > _PRUNE_IDLE_SECONDS]
    for k in stale:
        _buckets.pop(k, None)

    today = today_local().isoformat()
    stale_daily = [k for k, v in _daily.items() if v[0] != today]
    for k in stale_daily:
        _daily.pop(k, None)


def rate_limit_identity(
    request: Request,
    bucket: str,
    identity: str,
    max_times: int,
    window: int = 60,
) -> None:
    """同一身份在 window 秒内对同一 bucket 最多 max_times 次，超出抛 429"""
    now = time()
    key = f"{bucket}:{identity}"

    times = [t for t in _buckets.get(key, []) if now - t < window]
    if len(times) >= max_times:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests. Please wait a minute and try again.",
        )
    times.append(now)
    _buckets[key] = times

    if len(_buckets) > _PRUNE_THRESHOLD:
        _prune(now)


def rate_limit(request: Request, bucket: str, max_times: int, window: int = 60) -> None:
    """按客户端 IP 的分钟级限流（保留旧签名）"""
    rate_limit_identity(request, bucket, client_ip(request), max_times, window)


def check_daily_quota(
    request: Request,
    bucket: str,
    identity: str,
    max_requests: int,
    max_bytes: int,
) -> None:
    """同一身份在自然日内超过请求数或字节数上限时抛 429，否则计数 +1"""
    today = today_local().isoformat()
    key = f"{bucket}:{identity}"
    day, count, used = _daily.get(key, (today, 0, 0))
    if day != today:
        day, count, used = today, 0, 0

    if count >= max_requests:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily upload limit reached. Please try again tomorrow.",
        )
    if used >= max_bytes:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily upload limit reached. Please try again tomorrow.",
        )

    _daily[key] = (day, count + 1, used)

    if len(_daily) > _PRUNE_THRESHOLD:
        _prune(time())


def record_daily_bytes(request: Request, bucket: str, identity: str, n: int) -> None:
    """上传成功后累加实际写入字节数"""
    today = today_local().isoformat()
    key = f"{bucket}:{identity}"
    day, count, used = _daily.get(key, (today, 0, 0))
    if day != today:
        day, count, used = today, 0, 0
    _daily[key] = (day, count, used + n)
