"""OSS 直传上传会话令牌

用途：让匿名/员工每次投递拿到一个短时效、限定前缀的 STS 凭证，
避免一张 1 小时、可写整个 hr/ 前缀的凭证被反复滥用。

令牌与服务端 HMAC 签发，不需要落库；过期时间 15 分钟。
"""

import hashlib
import hmac
import time
import uuid

from app.config import settings

SESSION_TTL_SECONDS = 900
_PURPOSE = "upload-session-v1"


def new_upload_session() -> tuple[str, str]:
    """返回 (token, prefix)；prefix 形如 hr/1a2b3c4d5e6f7890/"""
    session_id = uuid.uuid4().hex[:16]
    exp = int(time.time()) + SESSION_TTL_SECONDS
    token = f"{session_id}.{exp:x}.{_mac(session_id, exp)}"
    return token, f"hr/{session_id}/"


def verify_upload_session(token: str | None) -> str | None:
    """校验并返回 prefix；无效、过期、签名不符返回 None"""
    if not token:
        return None
    try:
        session_id, exp_hex, mac = token.split(".")
        exp = int(exp_hex, 16)
    except (ValueError, AttributeError):
        return None
    if exp < int(time.time()):
        return None
    if not hmac.compare_digest(mac, _mac(session_id, exp)):
        return None
    return f"hr/{session_id}/"


def _mac(session_id: str, exp: int) -> str:
    msg = f"{_PURPOSE}:{session_id}:{exp}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
