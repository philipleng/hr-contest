"""手机号归一化用例：普通号段、DITO、座机与伪 08 号段"""

from app.schemas import is_valid_phone as schema_is_valid_phone
from app.schemas import normalize_phone as schema_normalize_phone
from app.utils.phone import is_valid_phone, normalize_ph_phone, normalize_phone


def test_normalizes_common_formats():
    assert normalize_ph_phone("09171234567") == "09171234567"
    assert normalize_ph_phone("+63 917 123 4567") == "09171234567"
    assert normalize_ph_phone("63 917 123 4567") == "09171234567"
    assert normalize_ph_phone("9171234567") == "09171234567"
    assert normalize_ph_phone("0917-123-4567") == "09171234567"


def test_accepts_dito_prefixes():
    assert normalize_ph_phone("08951234567") == "08951234567"
    assert normalize_ph_phone("+63 898 123 4567") == "08981234567"
    # DITO 的 0991-0994 属于普通 9 开头号段，同样应通过
    assert normalize_ph_phone("09911234567") == "09911234567"


def test_rejects_non_mobile_numbers():
    assert normalize_ph_phone("02 8123 4567") is None      # 座机
    assert normalize_ph_phone("0917123456") is None        # 少一位
    assert normalize_ph_phone("N/A") is None
    assert normalize_ph_phone("") is None
    assert normalize_ph_phone(None) is None


def test_rejects_non_dito_08_prefix():
    """080/081 等不是 DITO 号段，不能洗成合法手机号。"""
    assert normalize_ph_phone("08005868099") is None
    assert normalize_ph_phone("+63 801 234 5678") is None


def test_normalize_phone_and_is_valid_phone_consolidated():
    """normalize_phone 与 is_valid_phone 统一收口到 utils/phone.py，schemas 保留兼容导出。"""
    assert normalize_phone("0917-123-4567") == "09171234567"
    assert normalize_phone("+63 917 123 4567") == "09171234567"
    assert normalize_phone("639171234567") == "09171234567"
    assert normalize_phone("0917-123") == "0917123"
    assert normalize_phone("") == ""

    assert is_valid_phone("+63 917-123-4567") is True
    assert is_valid_phone("08951234567") is True
    assert is_valid_phone("02 8123 4567") is False
    assert is_valid_phone("12345") is False

    assert schema_normalize_phone is normalize_phone
    assert schema_is_valid_phone is is_valid_phone
