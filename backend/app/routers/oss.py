"""OSS 相关接口：STS 签发 + 本地开发上传兜底"""

import logging
import os
import shutil
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app.config import settings
from app.models import Staff
from app.schemas import ApiResponse
from app.utils.auth_deps import get_optional_staff
from app.utils.oss import generate_sts_token
from app.utils.ratelimit import (
    check_daily_quota,
    client_ip,
    rate_limit_identity,
    record_daily_bytes,
)
from app.utils.tz import today_local
from app.utils.upload_session import new_upload_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oss", tags=["oss"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 简历含姓名/电话/住址，属于 PII：放在静态目录之外，只能经带 JWT 的下载接口读取。
# 未做 OSS 期间简历固定落本地私有目录，即使以后启用 OSS 也不会变成可公开直连的对象。
PRIVATE_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "private_uploads"
)
os.makedirs(PRIVATE_UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

# 只允许图片、视频与简历文档。
# 严禁 .html / .svg / .py 等可执行或可渲染类型，否则 /uploads 会变成
# 同源钓鱼页托管点（存储型 XSS / 读取 localStorage 里的 JWT）。
# .docm / .xlsm 带宏，一律不收。
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic",
    ".mp4", ".mov", ".webm",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}

# 简历文档的 MIME（安卓文件选择器经常把 docx/xlsx 报成 octet-stream，靠扩展名兜底）
DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# 手机相机拍摄的文件名可能没有扩展名，此时按 MIME 推断
MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".webm",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


@router.post("/session", response_model=ApiResponse)
def create_upload_session(
    request: Request,
    staff: Staff | None = Depends(get_optional_staff),
):
    """签发上传会话：15 分钟 STS + 会话前缀 + 单对象 100MB 上限

    前端先取会话，再按 prefix 生成对象 key；提交时带上 session_token 供后端校验。
    """
    # 匿名按 IP 限制；已登录 staff 的扫楼代录不限次数
    if staff is None:
        rate_limit_identity(
            request, "oss_session", f"ip:{client_ip(request)}", 10, window=60
        )

    if not settings.OSS_ACCESS_KEY_ID or not settings.OSS_BUCKET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Upload service is not available right now. Please try again later.",
        )

    session_token, prefix = new_upload_session()
    try:
        token = generate_sts_token(prefix)
    except Exception:
        # OSS 已配置但签发失败（RAM 配置错、欠费、网络抖动、响应结构异常）：
        # 必须记录堆栈，否则前端退回本地上传后问题会被静默吞掉
        logger.exception("OSS STS issuance failed, falling back to local upload")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Upload service is not available right now. Please try again later.",
        )
    return ApiResponse(data={**token, "session_token": session_token, "prefix": prefix})


@router.post("/upload", response_model=ApiResponse)
def local_upload(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("media"),
    staff: Staff | None = Depends(get_optional_staff),
):
    """本地上传兜底（生产请用 OSS 直传）

    kind=media  → 照片/视频，落私有目录，经签名 URL 读取
    kind=resume → 简历附件，落私有目录，只能经 /api/applicant/{id}/resume 鉴权下载

    限流只针对匿名流量：已登录 staff 的扫楼代录不限次数；
    磁盘水位对所有人生效（保护整机，不是业务限制）。
    """
    identity = f"ip:{client_ip(request)}"
    if staff is None:
        rate_limit_identity(
            request, "oss_upload", identity, settings.UPLOAD_ANON_PER_MINUTE, window=60
        )
        check_daily_quota(
            request,
            "oss_upload",
            identity,
            settings.UPLOAD_ANON_DAILY_REQUESTS,
            settings.UPLOAD_ANON_DAILY_BYTES,
        )

    if kind not in ("media", "resume"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid upload kind.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = (file.content_type or "").lower()

    is_media = content_type.startswith(("image/", "video/"))
    # 安卓/部分文件管理器上传文档时给的是 application/octet-stream，此时靠扩展名白名单把关
    is_document = content_type in DOCUMENT_MIME_TYPES or content_type in ("", "application/octet-stream")
    if not (is_media or is_document):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only photo, video, or resume files (PDF, Word, Excel) are allowed.",
        )

    if not ext:
        # 手机原生相机做 `<input capture>` 时可能不给扩展名，按 MIME 补齐
        ext = MIME_TO_EXT.get(content_type, "")

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"File type {ext or '(no extension)'} is not allowed. "
            "Please upload a photo, video, or resume file (PDF, Word, Excel).",
        )

    if kind == "resume" and ext in VIDEO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Resume must be a document or an image.",
        )

    today = today_local().strftime("%Y/%m/%d")
    if kind == "resume":
        key = f"resume/{today}/{uuid.uuid4().hex[:16]}{ext}"
        base_dir = PRIVATE_UPLOAD_DIR
    else:
        key = f"local/{today}/{uuid.uuid4().hex[:16]}{ext}"
        base_dir = UPLOAD_DIR

    # 磁盘水位：宁可拒收新上传，也不让整机被写满（对 staff 同样生效）
    if shutil.disk_usage(base_dir).free < settings.UPLOAD_MIN_FREE_DISK_BYTES:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Upload storage is temporarily unavailable. Please try again later.",
        )

    save_path = os.path.join(base_dir, key)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 流式写入并实际计数，不依赖 file.size（该值在流式上传时可能为 None）
    written = 0
    try:
        with open(save_path, "wb") as out:
            while True:
                chunk = file.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "File is too large. Maximum size is 100MB.",
                    )
                out.write(chunk)
    except HTTPException:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise
    except Exception:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save the file. Please try again.")

    if staff is None:
        record_daily_bytes(request, "oss_upload", identity, written)

    data = {"key": key, "size": written}
    return ApiResponse(data=data)
