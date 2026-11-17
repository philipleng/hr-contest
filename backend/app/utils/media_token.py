"""媒体读取的短时效签名令牌

媒体文件不再公开可读：admin 前端经带 JWT 的 /api/applicant/{id}/media-url
换取签名 URL，TTL 内可直接用于 <img>/<video>（浏览器标签无法带 Authorization 头）。
令牌与 JWT 共用密钥但加了用途前缀，两种令牌不可互换。
"""

import base64
import hashlib
import hmac
import time

from app.config import settings

TOKEN_TTL_SECONDS = 600
_PURPOSE = "media-url-v1"


def sign_media_token(key: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    exp = int(time.time()) + ttl
    key_b64 = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
    return f"{key_b64}.{exp:x}.{_mac(key, exp)}"


def verify_media_token(token: str) -> str | None:
    """校验并返回原始 key；无效、过期或签名不符返回 None"""
    try:
        key_b64, exp_hex, mac = token.split(".")
        exp = int(exp_hex, 16)
        key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if exp < int(time.time()):
        return None
    if not hmac.compare_digest(mac, _mac(key, exp)):
        return None
    return key


def _mac(key: str, exp: int) -> str:
    msg = f"{_PURPOSE}:{key}:{exp}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
