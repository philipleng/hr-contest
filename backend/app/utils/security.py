"""JWT 签发/验证 + bcrypt 密码工具（不用 passlib，兼容 Python 3.13）"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# ---------- 密码 ----------

def hash_password(plain: str) -> str:
    """生成 bcrypt 密码哈希"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------- JWT ----------

def create_access_token(payload: dict) -> str:
    """签发 JWT，自动附加过期时间"""
    data = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    data.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(data, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """验证并解析 JWT，失败返回 None"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
