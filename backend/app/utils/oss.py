"""阿里云 OSS STS 临时凭证签发"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from aliyunsdkcore.client import AcsClient
from aliyunsdksts.request.v20150401 import AssumeRoleRequest

from app.config import settings

STS_TTL_SECONDS = 900


def build_sts_policy(bucket: str, prefix: str) -> dict:
    """构造只允许写入会话前缀的 STS Policy

    注意：不在此处设置 oss:ContentLengthRange Condition——阿里云 RAM/STS AssumeRole
    Policy 语法不支持 oss:ContentLengthRange（该条件仅存在于 OSS PostObject Policy，
    且 RAM Condition 必须带条件操作符，否则调用 AssumeRole 会报 InvalidParameter.PolicyGrammar）。
    单文件大小上限由 Nginx client_max_body_size 与后端配额把关，STS 负责 15 分钟 TTL 与会话级 Resource 前缀隔离。
    """
    return {
        "Version": "1",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "oss:PutObject",
                # 前端改用分片上传，弱网重试需要能中止已废弃的分片任务
                "oss:AbortMultipartUpload",
            ],
            "Resource": [f"acs:oss:*:*:{bucket}/{prefix}*"],
        }],
    }


def generate_sts_token(prefix: str) -> dict:
    """生成 OSS 直传 STS 临时凭证（15 分钟，限定 prefix）"""
    client = AcsClient(
        settings.OSS_ACCESS_KEY_ID,
        settings.OSS_ACCESS_KEY_SECRET,
        settings.OSS_REGION,
    )

    request = AssumeRoleRequest.AssumeRoleRequest()
    request.set_RoleArn(settings.OSS_ROLE_ARN)
    request.set_RoleSessionName(f"hr-upload-{uuid.uuid4().hex[:8]}")
    request.set_DurationSeconds(STS_TTL_SECONDS)
    request.set_Policy(json.dumps(build_sts_policy(settings.OSS_BUCKET, prefix)))

    response = client.do_action_with_exception(request)
    result = json.loads(response)

    credentials = result["Credentials"]
    expiration = datetime.now(timezone.utc) + timedelta(seconds=STS_TTL_SECONDS)

    return {
        "access_key_id": credentials["AccessKeyId"],
        "access_key_secret": credentials["AccessKeySecret"],
        "security_token": credentials["SecurityToken"],
        "expiration": expiration.isoformat(),
        "bucket": settings.OSS_BUCKET,
        "region": settings.OSS_REGION,
        "endpoint": settings.OSS_ENDPOINT,
    }


def generate_oss_key(prefix: str = "photo") -> str:
    """生成 OSS 对象键：hr/2026/10/15/uuid.jpg"""
    today = datetime.now(timezone.utc)
    ext = ".jpg" if prefix == "photo" else ".mp4"
    return f"hr/{today.strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:16]}{ext}"


def generate_presigned_url(key: str, expires: int = 600) -> str:
    """为私有读 bucket 的对象生成 GET 预签名 URL

    媒体与简历同属个人数据：bucket 应为私有读，后台读取统一走预签名。
    未配置 OSS 时抛 ValueError，由调用方转 404。
    """
    if not (settings.OSS_ACCESS_KEY_ID and settings.OSS_BUCKET):
        raise ValueError("OSS is not configured")

    import oss2

    endpoint = settings.OSS_ENDPOINT or f"https://oss-{settings.OSS_REGION}.aliyuncs.com"
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, endpoint, settings.OSS_BUCKET)
    return bucket.sign_url("GET", key, expires)
