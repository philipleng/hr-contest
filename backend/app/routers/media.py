"""短时效签名媒体读取（本地上传兜底路径）

local/ 对象只能经 /api/media/{token} 读取；token 由带 JWT 的
/api/applicant/{id}/media-url 签发，TTL 10 分钟，浏览器可直接用于 <img>/<video>。
hr/ 对象（OSS）不走这里：签发时直接给 OSS 预签名 URL。
"""

import logging
import mimetypes
import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.routers.oss import UPLOAD_DIR
from app.utils.media_token import TOKEN_TTL_SECONDS, verify_media_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

LOCAL_PREFIX = "local/"


@router.get("/{token}")
def serve_media(token: str):
    key = verify_media_token(token)
    # 无效/过期/伪造令牌与未授权读取统一 404，不暴露对象是否存在
    if key is None or not key.startswith(LOCAL_PREFIX):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found or link expired.")

    local_root = os.path.realpath(os.path.join(UPLOAD_DIR, "local"))
    path = os.path.realpath(os.path.join(local_root, key[len(LOCAL_PREFIX):]))
    if not path.startswith(local_root + os.sep) or not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media file not found.")

    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            # 令牌有效期内浏览器可复用；令牌过期后 URL 失效，缓存自然过期
            "Cache-Control": f"private, max-age={TOKEN_TTL_SECONDS}",
            "X-Content-Type-Options": "nosniff",
        },
    )
