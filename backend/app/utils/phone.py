"""菲律宾手机号归一化与校验。

规则（见 人才池数据模型演进方案.md 第 5.1 节）：
- normalize_ph_phone：严格认移动号码，返回 09XXXXXXXXX / 089[5-8]XXXXXXX，非移动号返回 None
- normalize_phone：尽力归一化（清理空白/括号/短横线并转换 +63/63 前缀），保留原始非标准串供模糊检索
- is_valid_phone：校验是否为合法菲律宾移动号码
"""

import re

_PHONE_NOISE = re.compile(r"[\s\-()]")
_PH_MOBILE = re.compile(r"^(?:63|0)?(9\d{9}|89[5-8]\d{7})$")


def normalize_ph_phone(raw: str | None) -> str | None:
    """返回 09XXXXXXXXX（含 DITO 0895-0898）；非移动号码返回 None。"""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    match = _PH_MOBILE.fullmatch(digits)
    if not match:
        return None
    return "0" + match.group(1)


def normalize_phone(value: str | None) -> str:
    """尽力归一化菲律宾手机号（用于搜索关键字清理）：

    0917 123 4567 / 0917-123-4567 / +639171234567 / 639171234567
    → 统一为 09171234567
    非法或残缺输入去除分隔符后原样返回（是否拒绝由调用方决定）。
    """
    s = _PHONE_NOISE.sub("", value or "")
    if s.startswith("+63"):
        s = "0" + s[3:]
    elif s.startswith("63") and len(s) == 12:
        s = "0" + s[2:]
    return s


def is_valid_phone(value: str | None) -> bool:
    """判断是否为合法菲律宾移动号码。"""
    return normalize_ph_phone(value) is not None
